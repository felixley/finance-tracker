from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)

    accounts: Mapped[list["Account"]] = relationship(back_populates="owner")


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bank_name: Mapped[str] = mapped_column(String(100), nullable=False)
    iban: Mapped[str] = mapped_column(String(34), nullable=False)
    owner_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("persons.id"), nullable=True
    )
    balance: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    last_synced_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
    owner: Mapped["Person | None"] = relationship(back_populates="accounts")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # income | expense
    parent_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("categories.id"), nullable=True
    )

    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
    rules: Mapped[list["Rule"]] = relationship(back_populates="category")


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Eindeutige Transaktions-ID vom Bank-Backend (für Dedupe)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    buchungsdatum: Mapped[dt.date] = mapped_column(Date, nullable=False)
    valutadatum: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    betrag: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    waehrung: Mapped[str] = mapped_column(String(3), nullable=False, default="EUR")
    partner_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    verwendungszweck: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True
    )
    raw_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    account: Mapped[Account] = relationship(back_populates="transactions")
    category: Mapped[Category | None] = relationship(back_populates="transactions")


class Rule(Base):
    __tablename__ = "rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pattern: Mapped[str] = mapped_column(String(255), nullable=False)
    match_field: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # partner_name | verwendungszweck
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_from_manual_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    category: Mapped[Category] = relationship(back_populates="rules")