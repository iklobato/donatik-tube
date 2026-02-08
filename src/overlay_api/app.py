"""
Internal API: write Donor, RankingEntry, PIXAlert. Atomic/transactional per overlay-data-writes contract.
"""

import logging
from datetime import datetime

from flask import Flask, Response, jsonify, request
from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import get_settings
from stream_workers.db import Donor, PIXAlert, RankingEntry, get_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


@app.route("/donors", methods=["POST"])
def create_donor() -> tuple[Response, int]:
    """Create or update donor. Body: identifier, amount, currency (optional)."""
    data = request.get_json() or {}
    identifier = data.get("identifier")
    amount = data.get("amount")
    if identifier is None or amount is None:
        return jsonify({"error": "identifier and amount required"}), 400
    engine = get_engine()
    with Session(engine) as session:
        donor = Donor(
            identifier=str(identifier),
            amount=float(amount),
            currency=data.get("currency"),
        )
        session.add(donor)
        session.commit()
        session.refresh(donor)
        return jsonify({"id": donor.id}), 201


@app.route("/alerts", methods=["POST"])
def create_alert() -> tuple[Response, int]:
    """Create PIX alert. Body: message, show_at, hide_at (ISO), donor_id (optional)."""
    data = request.get_json() or {}
    message = data.get("message")
    show_at = data.get("show_at")
    hide_at = data.get("hide_at")
    if not message or not show_at or not hide_at:
        return jsonify({"error": "message, show_at, hide_at required"}), 400
    engine = get_engine()
    with Session(engine) as session:
        alert = PIXAlert(
            message=message,
            donor_id=data.get("donor_id"),
            show_at=datetime.fromisoformat(show_at.replace("Z", "+00:00")),
            hide_at=datetime.fromisoformat(hide_at.replace("Z", "+00:00")),
        )
        session.add(alert)
        session.commit()
        session.refresh(alert)
        return jsonify({"id": alert.id}), 201


@app.route("/ranking", methods=["POST"])
def update_ranking() -> tuple[Response, int]:
    """Recompute and replace Top 10 ranking atomically. Body: list of {position, donor_id, amount, identifier}."""
    data = request.get_json() or {}
    entries = data.get("entries", [])
    if len(entries) > 10:
        return jsonify({"error": "max 10 entries"}), 400
    engine = get_engine()
    with Session(engine) as session:
        session.execute(text("DELETE FROM ranking_entries"))
        for e in entries:
            session.add(
                RankingEntry(
                    position=e["position"],
                    donor_id=e["donor_id"],
                    amount=e["amount"],
                    identifier=e["identifier"],
                )
            )
        session.commit()
        return jsonify({"ok": True}), 200


def run() -> None:
    s = get_settings()
    app.run(host=s.api.host, port=s.api.port)


if __name__ == "__main__":
    run()
