"""FastAPI-Dashboard: API + Frontend."""
from __future__ import annotations

import datetime as dt
import logging
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from .categorizer import learn_from_override
from .config import settings
from .db import get_db
from .models import Account, Category, Rule, Transaction
from .scheduler import start_scheduler, stop_scheduler
from .banks.base import TanRequired

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

_sync_jobs: dict[str, dict] = {}
_sync_executor: ThreadPoolExecutor | None = None


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Regel-Seeds idempotent anlegen + offene Tx kategorisieren (frische DBs sind sonst leer)
    from .db import SessionLocal
    from .seed_rules import seed_rules
    from .categorizer import apply_to_pending
    try:
        db = SessionLocal()
        n = seed_rules(db)
        if n:
            logger.info("Seed-Regeln angelegt: %d", n)
        categorized = apply_to_pending(db)
        if categorized:
            logger.info("Nachträglich kategorisiert: %d Transaktionen", categorized)
        db.close()
    except Exception:
        logger.exception("Seed/Categorize beim Startup fehlgeschlagen — fahre trotzdem hoch.")
    start_scheduler()
    yield
    stop_scheduler()


def _tx_json(t: Transaction) -> dict:
    return {
        "id": t.id,
        "buchungsdatum": str(t.buchungsdatum),
        "valutadatum": str(t.valutadatum) if t.valutadatum else None,
        "betrag": float(t.betrag),
        "waehrung": t.waehrung,
        "partner_name": t.partner_name,
        "verwendungszweck": t.verwendungszweck,
        "category_id": t.category_id,
        "category_name": t.category.name if t.category else "Unassigned",
        "account_id": t.account_id,
        "account_bank": t.account.bank_name,
    }


def _run_sync_job(job_id: str, banks: list[str]) -> None:
    try:
        from .etl import sync_all

        result = sync_all(days_back=90, banks=banks)
        _sync_jobs[job_id] = {"status": "done", "result": result}
    except TanRequired:
        _sync_jobs[job_id] = {
            "status": "tan_required",
            "hint": "TAN-Interaktion über CLI nötig: python scripts/fints_probe.py --bank X",
        }
    except Exception as e:
        _sync_jobs[job_id] = {"status": "error", "error": str(e)}


def create_app() -> FastAPI:
    app = FastAPI(title="Finance Tracker", lifespan=_lifespan)
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    executor = ThreadPoolExecutor(max_workers=1)

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request):
        return templates.TemplateResponse(request=request, name="index.html", context={})

    @app.get("/api/kpis")
    def kpis(db: Session = Depends(get_db)):
        total_balance = db.query(func.coalesce(func.sum(Account.balance), 0)).scalar()
        month_start = dt.date.today().replace(day=1)
        txs = db.query(Transaction.betrag).filter(
            Transaction.buchungsdatum >= month_start
        ).all()
        income = sum(float(b[0]) for b in txs if b[0] and b[0] > 0)
        expenses = sum(float(b[0]) for b in txs if b[0] and b[0] < 0)
        return {
            "total_balance": float(total_balance or 0),
            "income_month": round(income, 2),
            "expenses_month": round(expenses, 2),
            "net_cashflow": round(income + expenses, 2),
        }

    @app.get("/api/timeline")
    def timeline(
        granularity: str = Query("monthly", pattern="^(monthly|yearly)$"),
        db: Session = Depends(get_db),
    ):
        fmt = "%Y-%m" if granularity == "monthly" else "%Y"
        rows = db.query(
            func.strftime(fmt, Transaction.buchungsdatum).label("period"),
            Transaction.betrag,
        ).all()
        agg: dict[str, dict] = {}
        for period, betrag in rows:
            b = float(betrag or 0)
            d = agg.setdefault(period, {"income": 0.0, "expenses": 0.0})
            if b > 0:
                d["income"] += b
            else:
                d["expenses"] += b
        return [
            {"period": p, "income": round(v["income"], 2), "expenses": round(v["expenses"], 2)}
            for p, v in sorted(agg.items())
        ]

    @app.get("/api/categories/breakdown")
    def breakdown(db: Session = Depends(get_db)):
        rows = (
            db.query(Category.name, func.sum(Transaction.betrag))
            .join(Transaction, Transaction.category_id == Category.id)
            .filter(Transaction.betrag < 0)
            .group_by(Category.id)
            .all()
        )
        unassigned = (
            db.query(func.sum(Transaction.betrag))
            .filter(Transaction.betrag < 0, Transaction.category_id.is_(None))
            .scalar()
        )
        out = [
            {"category": name, "total": round(abs(float(total or 0)), 2)}
            for name, total in rows
        ]
        if unassigned:
            out.append({"category": "Unassigned", "total": round(abs(float(unassigned)), 2)})
        return out

    @app.get("/api/transactions")
    def transactions(
        search: str = "",
        category_id: int | None = None,
        account_id: int | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        page: int = 1,
        per_page: int = Query(25, le=100),
        db: Session = Depends(get_db),
    ):
        q = db.query(Transaction)
        if search:
            like = f"%{search}%"
            q = q.filter(
                (Transaction.partner_name.ilike(like))
                | (Transaction.verwendungszweck.ilike(like))
            )
        if category_id is not None:
            q = q.filter(Transaction.category_id == category_id)
        if account_id is not None:
            q = q.filter(Transaction.account_id == account_id)
        if date_from:
            q = q.filter(Transaction.buchungsdatum >= date_from)
        if date_to:
            q = q.filter(Transaction.buchungsdatum <= date_to)
        total = q.count()
        rows = (
            q.order_by(Transaction.buchungsdatum.desc(), Transaction.id.desc())
            .offset((max(page, 1) - 1) * per_page)
            .limit(per_page)
            .all()
        )
        return {"total": total, "page": page, "per_page": per_page,
                "items": [_tx_json(t) for t in rows]}

    @app.patch("/api/transactions/{tx_id}/category")
    def set_category(tx_id: int, body: dict, db: Session = Depends(get_db)):
        tx = db.get(Transaction, tx_id)
        if tx is None:
            raise HTTPException(404, "Transaktion nicht gefunden")
        cat = db.get(Category, int(body.get("category_id", 0)))
        if cat is None:
            raise HTTPException(404, "Kategorie nicht gefunden")
        rule = learn_from_override(db, tx_id, cat.id)
        return {"ok": True, "category": cat.name,
                "rule_created": bool(rule and rule.created_from_manual_override)}

    @app.get("/api/categories")
    def list_categories(db: Session = Depends(get_db)):
        return [{"id": c.id, "name": c.name, "type": c.type, "parent_id": c.parent_id}
                for c in db.query(Category).order_by(Category.name).all()]

    @app.post("/api/categories", status_code=201)
    def add_category(body: dict, db: Session = Depends(get_db)):
        name = (body.get("name") or "").strip()
        if not name:
            raise HTTPException(422, "Name erforderlich")
        if db.query(Category).filter_by(name=name).first():
            raise HTTPException(409, "Kategorie existiert bereits")
        cat = Category(name=name, type=body.get("type", "expense"))
        db.add(cat)
        db.commit()
        return {"id": cat.id, "name": cat.name, "type": cat.type}

    @app.delete("/api/categories/{cat_id}")
    def delete_category(cat_id: int, db: Session = Depends(get_db)):
        cat = db.get(Category, cat_id)
        if cat is None:
            raise HTTPException(404, "Kategorie nicht gefunden")
        db.query(Transaction).filter_by(category_id=cat_id).update(
            {Transaction.category_id: None}
        )
        db.query(Rule).filter_by(category_id=cat_id).delete()
        db.delete(cat)
        db.commit()
        return {"ok": True}

    @app.get("/api/rules")
    def list_rules(db: Session = Depends(get_db)):
        rows = (db.query(Rule, Category.name)
                .join(Category, Rule.category_id == Category.id)
                .order_by(Rule.priority.desc(), Rule.id).all())
        return [{"id": r.id, "pattern": r.pattern, "match_field": r.match_field,
                 "category": cname, "priority": r.priority,
                 "created_from_manual_override": r.created_from_manual_override}
                for r, cname in rows]

    @app.post("/api/rules", status_code=201)
    def add_rule(body: dict, db: Session = Depends(get_db)):
        pattern = (body.get("pattern") or "").strip()
        if not pattern:
            raise HTTPException(422, "pattern erforderlich")
        cat = db.get(Category, int(body.get("category_id", 0)))
        if cat is None:
            raise HTTPException(404, "Kategorie nicht gefunden")
        rule = Rule(pattern=pattern,
                    match_field=body.get("match_field", "partner_name"),
                    category_id=cat.id,
                    priority=int(body.get("priority", 0)),
                    created_from_manual_override=False)
        db.add(rule)
        db.commit()
        return {"id": rule.id}

    @app.delete("/api/rules/{rule_id}")
    def delete_rule(rule_id: int, force: bool = False, db: Session = Depends(get_db)):
        rule = db.get(Rule, rule_id)
        if rule is None:
            raise HTTPException(404, "Regel nicht gefunden")
        if rule.created_from_manual_override and not force:
            raise HTTPException(409, "Gelernte Regel — ?force=true nötig")
        db.delete(rule)
        db.commit()
        return {"ok": True}

    @app.get("/api/accounts")
    def accounts(db: Session = Depends(get_db)):
        return [{"id": a.id, "bank_name": a.bank_name, "iban": a.iban,
                 "balance": float(a.balance or 0), "last_synced_at": str(a.last_synced_at)}
                for a in db.query(Account).all()]

    @app.post("/api/sync")
    def trigger_sync(body: dict | None = None):
        banks = (body or {}).get("banks") or settings.banks or ["mock"]
        job_id = str(uuid.uuid4())
        _sync_jobs[job_id] = {"status": "running"}
        executor.submit(_run_sync_job, job_id, banks)
        return {"job_id": job_id, "banks": banks}

    @app.get("/api/sync/status/{job_id}")
    def sync_status(job_id: str):
        job = _sync_jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "Job unbekannt")
        return job

    @app.get("/api/mock-seed")
    def mock_seed():
        if settings.TAN_MODE != "mock" and not os.getenv("DEBUG"):
            raise HTTPException(403, "Nur im Mock/DEBUG-Modus")
        from .etl import sync_all

        return sync_all(days_back=90, banks=["mock"])

    return app