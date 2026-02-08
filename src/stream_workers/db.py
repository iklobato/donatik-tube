"""
SQLAlchemy models and overlay state read. Donor, RankingEntry, PIXAlert per data-model.
Single function returns ranking (top 10) and active PIX alerts in one transaction (atomic snapshot).
When DB is unreachable, get_overlay_snapshot raises; caller keeps last known data (overlay contract).
"""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from config.settings import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class Donor(Base):
    __tablename__ = "donors"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    identifier: Mapped[str] = mapped_column(nullable=False)
    amount: Mapped[float] = mapped_column(nullable=False)
    currency: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class RankingEntry(Base):
    __tablename__ = "ranking_entries"
    position: Mapped[int] = mapped_column(primary_key=True)
    donor_id: Mapped[int] = mapped_column(nullable=False)
    amount: Mapped[float] = mapped_column(nullable=False)
    identifier: Mapped[str] = mapped_column(nullable=False)


class PIXAlert(Base):
    __tablename__ = "pix_alerts"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message: Mapped[str] = mapped_column(nullable=False)
    donor_id: Mapped[int | None] = mapped_column(nullable=True)
    show_at: Mapped[datetime] = mapped_column(nullable=False)
    hide_at: Mapped[datetime] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=lambda: datetime.now(UTC))


class OverlayPaymentLink(Base):
    """Single global payment link for overlay (one row, id=1)."""

    __tablename__ = "overlay_payment_link"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    url: Mapped[str | None] = mapped_column(nullable=True)
    label: Mapped[str | None] = mapped_column(nullable=True)
    active: Mapped[bool] = mapped_column(nullable=False, default=False)


_engine_holder: list[Engine | None] = [None]


def get_engine() -> Engine:
    eng = _engine_holder[0]
    if eng is not None:
        return eng
    eng = create_engine(
        get_settings().db.database_url(), pool_pre_ping=True
    )
    _engine_holder[0] = eng
    return eng


def get_overlay_snapshot() -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None
]:
    """
    Return (ranking, active_pix_alerts, payment_link) in one transaction.
    payment_link is {"url": str, "label": str} when overlay_payment_link has url and active true, else None.
    Raises on DB error; caller keeps last known overlay data when unreachable.
    """
    engine = get_engine()
    now = datetime.now(UTC)
    with Session(engine) as session:
        ranking = []
        for row in session.execute(
            text(
                "SELECT position, identifier, amount FROM ranking_entries ORDER BY position LIMIT 10"
            )
        ).fetchall():
            ranking.append({"position": row[0], "identifier": row[1], "amount": row[2]})
        alerts = []
        for row in session.execute(
            text(
                "SELECT id, message FROM pix_alerts WHERE show_at <= :now AND hide_at > :now ORDER BY created_at"
            ),
            {"now": now},
        ).fetchall():
            alerts.append({"id": row[0], "message": row[1]})
        link_row = session.get(OverlayPaymentLink, 1)
        payment_link: dict[str, Any] | None = None
        if (
            link_row is not None
            and link_row.url
            and link_row.active
        ):
            payment_link = {
                "url": link_row.url,
                "label": link_row.label or "",
            }
        return (ranking, alerts, payment_link)
