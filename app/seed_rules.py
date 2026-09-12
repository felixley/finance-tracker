"""Idempotente Seed-Regeln für gängige deutsche Händler/Dienstleister."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Category, Rule

# (pattern, match_field, category_name, priority, is_regex)
SEED_RULES: list[tuple[str, str, str, int, bool]] = [
    # Groceries — spezifische Ketten zuerst
    ("REWE SAG", "partner_name", "Lebensmittel", 3, False),
    ("EDEKA", "partner_name", "Lebensmittel", 3, False),
    ("ALDI", "partner_name", "Lebensmittel", 3, False),
    ("LIDL", "partner_name", "Lebensmittel", 3, False),
    ("Kaufland", "partner_name", "Lebensmittel", 3, False),
    ("Penny", "partner_name", "Lebensmittel", 3, False),
    ("Netto Marken-Discount", "partner_name", "Lebensmittel", 4, False),
    ("dm-drogerie", "partner_name", "Lebensmittel", 3, False),
    ("Rossmann", "partner_name", "Lebensmittel", 3, False),
    # Subscriptions — spezifischer als generisches "Entertainment"
    ("Netflix", "partner_name", "Abos & Abonnements", 5, False),
    ("Spotify", "partner_name", "Abos & Abonnements", 5, False),
    ("Disney", "partner_name", "Abos & Abonnements", 5, False),
    ("DAZN", "partner_name", "Abos & Abonnements", 5, False),
    # Dining Out
    ("McDonald's", "partner_name", "Restaurant & Café", 3, False),
    ("Burger King", "partner_name", "Restaurant & Café", 3, False),
    ("Starbucks", "partner_name", "Restaurant & Café", 3, False),
    ("Vapiano", "partner_name", "Restaurant & Café", 3, False),
    ("L'Osteria", "partner_name", "Restaurant & Café", 3, False),
    ("Lieferando", "partner_name", "Restaurant & Café", 3, False),
    # Leisure & Recreation (Travel/Transport)
    ("Deutsche Bahn", "partner_name", "Freizeit & Unterhaltung", 3, False),
    ("DB Vertrieb", "partner_name", "Freizeit & Unterhaltung", 4, False),
    ("Lufthansa", "partner_name", "Freizeit & Unterhaltung", 3, False),
    ("Ryanair", "partner_name", "Freizeit & Unterhaltung", 3, False),
    # Insurance
    ("Techniker Krankenkasse", "partner_name", "Versicherungen", 3, False),
    ("Barmer", "partner_name", "Versicherungen", 3, False),
    ("AOK", "partner_name", "Versicherungen", 3, False),
    ("Allianz", "partner_name", "Versicherungen", 3, False),
    ("HUK-Coburg", "partner_name", "Versicherungen", 3, False),
    ("Check24", "partner_name", "Versicherungen", 2, False),
    # Housing/Rent
    ("Miete", "verwendungszweck", "Wohnen & Miete", 3, False),
    ("Nebenkosten", "verwendungszweck", "Wohnen & Miete", 3, False),
    ("Hausgeld", "verwendungszweck", "Wohnen & Miete", 3, False),
    # Sonstiges
    ("Rundfunkbeitrag", "verwendungszweck", "Sonstiges", 3, False),
    # Salary (Regex für Varianten)
    ("/(?i)lohn|gehalt|salary", "verwendungszweck", "Gehalt", 3, True),
    # Internal Transfer
    ("/(?i)übertrag|uebertrag", "verwendungszweck", "Interne Umbuchung", 3, True),
]


def seed_rules(db: Session | None = None) -> int:
    own = db is None
    if own:
        db = SessionLocal()
    try:
        cats = {c.name: c.id for c in db.query(Category).all()}
        existing = {
            (r.pattern, r.match_field) for r in db.query(Rule).all()
        }
        created = 0
        for pattern, field, cat_name, prio, is_regex in SEED_RULES:
            if (pattern, field) in existing:
                continue
            cat_id = cats.get(cat_name)
            if cat_id is None:
                continue
            db.add(
                Rule(
                    pattern=pattern,
                    match_field=field,
                    category_id=cat_id,
                    priority=prio,
                    created_from_manual_override=False,
                )
            )
            created += 1
        db.commit()
        return created
    finally:
        if own:
            db.close()


if __name__ == "__main__":
    n = seed_rules()
    print(f"Seed-Regeln OK: {n} neue Regeln angelegt.")