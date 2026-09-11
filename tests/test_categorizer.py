"""Tests: Kategorisierungs-Engine."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.categorizer import RuleMatchEngine, apply_to_pending, learn_from_override
from app.db import Base
from app.models import Category, Rule, Transaction
from app.seed import seed_categories
from app.seed_rules import seed_rules


@pytest.fixture()
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    seed_categories(session)
    return session


def _mk_rule(db, pattern, cat_name, field="partner_name", priority=0, manual=False):
    cat = db.query(Category).filter_by(name=cat_name).first()
    r = Rule(pattern=pattern, match_field=field, category_id=cat.id,
             priority=priority, created_from_manual_override=manual)
    db.add(r)
    db.commit()
    return r


def _mk_tx(db, partner, purpose="", amount="-10.00"):
    acct_id = _ensure_account(db)
    tx = Transaction(external_id=f"ext-{partner}-{amount}-{id(partner)}",
                     account_id=acct_id, buchungsdatum=dt.date(2026, 9, 1),
                     betrag=Decimal(amount), waehrung="EUR",
                     partner_name=partner, verwendungszweck=purpose)
    db.add(tx)
    db.commit()
    return tx


def _ensure_account(db):
    from app.models import Account

    acct = db.query(Account).first()
    if acct is None:
        acct = Account(bank_name="mock", iban="DE123")
        db.add(acct)
        db.commit()
    return acct.id


def test_rule_matching_priority(db):
    # generische Regel zuerst angelegt (niedrige Priorität)
    _mk_rule(db, "Entertainment", "Leisure & Recreation", priority=0)
    # spezifische Regel gewinnt wegen höherer Priorität
    _mk_rule(db, "Netflix Entertainment", "Subscriptions", priority=5)
    eng = RuleMatchEngine(db)
    tx = {"partner_name": "Netflix Entertainment GmbH"}
    assert eng.match(tx) == db.query(Category).filter_by(name="Subscriptions").first().id


def test_regex_vs_keyword(db):
    _mk_rule(db, "/(?i)^rew|SAG", "Groceries")  # Regex
    _mk_rule(db, "netflix", "Subscriptions")    # Keyword (case-insensitive)
    eng = RuleMatchEngine(db)
    assert eng.match({"partner_name": "REWE SAG Köln"}) == (
        db.query(Category).filter_by(name="Groceries").first().id)
    assert eng.match({"partner_name": "NETFLIX Entertainment"}) == (
        db.query(Category).filter_by(name="Subscriptions").first().id)


def test_first_match_wins(db):
    # gleiche Priorität → längeres Pattern gewinnt
    _mk_rule(db, "DB", "Sonstiges", priority=0)
    _mk_rule(db, "Deutsche Bahn", "Leisure & Recreation", priority=0)
    eng = RuleMatchEngine(db)
    assert eng.match({"partner_name": "Deutsche Bahn AG"}) == (
        db.query(Category).filter_by(name="Leisure & Recreation").first().id)


def test_learn_from_override(db):
    seed_rules(db)
    tx = _mk_tx(db, "Amazon Marketplace")
    cat = db.query(Category).filter_by(name="Sonstiges").first()
    rule = learn_from_override(db, tx.id, cat.id)
    assert rule is not None
    assert rule.created_from_manual_override is True
    assert rule.priority == 10
    # Regel greift beim nächsten Match
    eng = RuleMatchEngine(db)
    assert eng.match({"partner_name": "Amazon Marketplace"}) == cat.id


def test_unassigned_flag(db):
    eng = RuleMatchEngine(db)
    assert eng.match({"partner_name": "Unbekannter Shop"}) is None
    tx = _mk_tx(db, "Muster Firma XYZ")
    assert tx.category_id is None  # bleibt "Unassigned"


def test_apply_to_pending(db):
    seed_rules(db)
    txs = [
        _mk_tx(db, "REWE SAG 112"),
        _mk_tx(db, "Netflix"),
        _mk_tx(db, "Völlig Unbekannt"),
    ]
    assert all(t.category_id is None for t in txs)
    count = apply_to_pending(db)
    assert count == 2
    db.refresh(txs[0])
    assert txs[0].category_id is not None
    db.refresh(txs[2])
    assert txs[2].category_id is None