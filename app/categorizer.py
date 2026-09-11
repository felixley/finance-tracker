"""Rule-based categorization engine with learning from manual overrides."""
from __future__ import annotations

import re
from decimal import Decimal

from sqlalchemy.orm import Session

from .models import Category, Rule, Transaction

MANUAL_OVERRIDE_PRIORITY = 10  # manual rules beat all seed rules


class RuleMatchEngine:
    """Loads rules once and matches transactions. First hit wins."""

    def __init__(self, db: Session):
        rules = db.query(Rule).all()
        # Priorisierung: priority DESC, dann längeres (spezifischeres) Pattern, dann id ASC
        self._rules = sorted(
            rules,
            key=lambda r: (-r.priority, -len(r.pattern), r.id),
        )
        self._categories = {
            c.id: c for c in db.query(Category).all()
        }

    def match(self, tx: dict) -> int | None:
        """tx: dict mit partner_name, verwendungszweck. Liefert category_id oder None."""
        for rule in self._rules:
            value = tx.get(rule.match_field) or ""
            if not value:
                continue
            if self._pattern_matches(rule.pattern, value):
                return rule.category_id
        return None

    @staticmethod
    def _pattern_matches(pattern: str, value: str) -> bool:
        """Regex wenn Pattern mit '/' beginnt oder '(?i)'-Präfix hat, sonst Keyword."""
        is_regex = pattern.startswith("/") or pattern.startswith("(?i)")
        if is_regex:
            expr = pattern[1:] if pattern.startswith("/") else pattern
            try:
                return re.search(expr, value, re.IGNORECASE) is not None
            except re.error:
                return False
        return pattern.casefold() in value.casefold()

    def apply_to_pending(self, db: Session, only_unassigned: bool = True) -> int:
        """Kategorisiert Transaktionen (neu). Zählt geänderte Zuweisungen."""
        q = db.query(Transaction)
        if only_unassigned:
            q = q.filter(Transaction.category_id.is_(None))
        count = 0
        for tx in q.all():
            cat_id = self.match(
                {
                    "partner_name": tx.partner_name,
                    "verwendungszweck": tx.verwendungszweck,
                }
            )
            if cat_id is not None:
                tx.category_id = cat_id
                count += 1
        db.commit()
        return count


def apply_to_pending(db: Session, only_unassigned: bool = True) -> int:
    """Modul-Level-Wrapper: kategorisiert offene Transaktionen via RuleMatchEngine."""
    return RuleMatchEngine(db).apply_to_pending(db, only_unassigned=only_unassigned)


def learn_from_override(
    db: Session, transaction_id: int, new_category_id: int
) -> Rule | None:
    """Leitet aus einer manuellen Korrektur eine Regel ab (created_from_manual_override)."""
    tx = db.get(Transaction, transaction_id)
    if tx is None:
        return None
    pattern = (tx.partner_name or "").strip()
    if len(pattern) > 25:
        pattern = pattern[:25]
    if not pattern:
        return None
    existing = (
        db.query(Rule)
        .filter(
            Rule.pattern == pattern,
            Rule.match_field == "partner_name",
            Rule.category_id == new_category_id,
        )
        .first()
    )
    if existing:
        existing.priority = max(existing.priority, MANUAL_OVERRIDE_PRIORITY)
        rule = existing
    else:
        rule = Rule(
            pattern=pattern,
            match_field="partner_name",
            category_id=new_category_id,
            priority=MANUAL_OVERRIDE_PRIORITY,
            created_from_manual_override=True,
        )
        db.add(rule)
    tx.category_id = new_category_id
    db.commit()
    return rule