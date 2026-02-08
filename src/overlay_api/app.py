"""
Internal API: write Donor, RankingEntry, PIXAlert, OverlayPaymentLink; Stripe webhook; YouTube OAuth and push refresh.
"""

import html
import json
import logging
from datetime import datetime
from typing import cast

import stripe
from flask import Flask, Response, jsonify, redirect, request
from sqlalchemy import text
from sqlalchemy.orm import Session

from config.settings import get_settings
from overlay_api import youtube as youtube_module
from stream_workers.db import (
    Donor,
    OverlayPaymentLink,
    PIXAlert,
    RankingEntry,
    get_engine,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)


def _require_payment_link_auth() -> tuple[Response, int] | None:
    """If API__payment_link_api_key is set, require Bearer or X-API-Key; return 401/403 or None to proceed."""
    key = get_settings().api.payment_link_api_key
    if not key:
        return None
    auth_header = request.headers.get("Authorization")
    api_key_header = request.headers.get("X-API-Key")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif api_key_header:
        token = api_key_header
    if not token or token != key:
        return jsonify({"error": "Unauthorized"}), 401
    return None


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


@app.route("/payment-link", methods=["GET"])
def get_payment_link() -> tuple[Response, int]:
    """Return current overlay payment link (global single row). FR-6: backend auth when API__payment_link_api_key set."""
    auth_fail = _require_payment_link_auth()
    if auth_fail is not None:
        return auth_fail
    engine = get_engine()
    with Session(engine) as session:
        row = session.get(OverlayPaymentLink, 1)
        if row is None:
            return jsonify({"url": None, "label": None, "active": False}), 200
        return (
            jsonify(
                {
                    "url": row.url,
                    "label": row.label,
                    "active": row.active,
                }
            ),
            200,
        )


@app.route("/payment-link", methods=["PUT"])
def put_payment_link() -> tuple[Response, int]:
    """Create or update the single overlay payment link. FR-6: backend auth when API__payment_link_api_key set."""
    auth_fail = _require_payment_link_auth()
    if auth_fail is not None:
        return auth_fail
    data = request.get_json() or {}
    url = data.get("url")
    label = data.get("label")
    active = data.get("active")
    if url is not None:
        url = str(url).strip() if url else None
    if url and (not url.startswith("https://") or len(url) > 2048):
        return jsonify({"error": "url must be https and max 2048 chars"}), 400
    if label is not None and len(str(label)) > 64:
        return jsonify({"error": "label max 64 chars"}), 400
    engine = get_engine()
    with Session(engine) as session:
        row = session.get(OverlayPaymentLink, 1)
        if row is None:
            row = OverlayPaymentLink(
                id=1,
                url=url,
                label=label or None,
                active=active if active is not None else bool(url),
            )
            session.add(row)
        else:
            if url is not None:
                row.url = url or None
            if label is not None:
                row.label = label or None
            if active is not None:
                row.active = bool(active)
            if url is not None and not url and row.active:
                row.active = False
        session.commit()
        session.refresh(row)
        return (
            jsonify(
                {
                    "url": row.url,
                    "label": row.label,
                    "active": row.active,
                }
            ),
            200,
        )


_processed_stripe_event_ids: set[str] = set()


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook() -> tuple[Response, int]:
    """Stripe webhook: verify signature, on checkout.session.completed create Donor; deduplicate by event id."""
    secret = get_settings().stripe.webhook_secret
    if not secret:
        return jsonify({"error": "webhook not configured"}), 400
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)  # type: ignore[no-untyped-call]
    except (ValueError, stripe.SignatureVerificationError):
        return jsonify({"error": "Invalid signature"}), 400
    if event["id"] in _processed_stripe_event_ids:
        return jsonify({"received": True}), 200
    _processed_stripe_event_ids.add(event["id"])
    if event["type"] == "checkout.session.completed":
        session_data = event.get("data", {}).get("object", {})
        amount_total = session_data.get("amount_total") or 0
        amount_float = amount_total / 100.0
        customer_email = session_data.get("customer_email") or session_data.get("customer_details", {}).get("email") or ""
        identifier = customer_email or f"Stripe-{session_data.get('id', 'unknown')}"
        engine = get_engine()
        with Session(engine) as session:
            donor = Donor(identifier=identifier, amount=amount_float, currency="brl")
            session.add(donor)
            session.commit()
    return jsonify({"received": True}), 200


@app.route("/youtube/connect", methods=["GET"])
def youtube_connect() -> tuple[Response, int] | Response:
    """Redirect to Google OAuth for YouTube. Optional: require payment-link auth."""
    auth_fail = _require_payment_link_auth()
    if auth_fail is not None:
        return auth_fail
    redirect_uri = request.url_root.rstrip("/") + "/youtube/callback"
    url = youtube_module.build_connect_url(redirect_uri=redirect_uri)
    if not url:
        return jsonify({"error": "YOUTUBE__CLIENT_ID not set"}), 400
    return cast(Response, redirect(url))


@app.route("/youtube/callback", methods=["GET"])
def youtube_callback() -> tuple[Response, int] | Response:
    """Exchange code for tokens; show page with refresh_token to add to .env."""
    code = request.args.get("code")
    if not code:
        return jsonify({"error": "missing code"}), 400
    redirect_uri = request.url_root.rstrip("/") + "/youtube/callback"
    tokens = youtube_module.exchange_code_for_tokens(code=code, redirect_uri=redirect_uri)
    if not tokens:
        return jsonify({"error": "token exchange failed"}), 400
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return jsonify({"error": "no refresh_token in response"}), 400
    access_token = tokens.get("access_token")
    channel_id = youtube_module.get_channel_id(access_token) if access_token else None
    if not channel_id:
        channel_id = "UC_unknown"
    env_line = f"YOUTUBE__REFRESH_TOKENS={json.dumps({channel_id: refresh_token})}"
    env_escaped = html.escape(env_line)
    html_body = f"""
    <!DOCTYPE html>
    <html><body style="font-family:sans-serif;max-width:640px;margin:2em auto;">
    <h1>YouTube connected</h1>
    <p>Add this to your <code>.env</code> (merge into existing YOUTUBE__REFRESH_TOKENS JSON if you have other channels):</p>
    <pre style="background:#eee;padding:1em;overflow:auto;">{env_escaped}</pre>
    <p>Then restart the overlay API.</p>
    </body></html>
    """
    return Response(html_body, mimetype="text/html")


def run() -> None:
    s = get_settings()
    if s.youtube.client_id and s.youtube.refresh_tokens.strip():
        try:
            urls = youtube_module.get_ingestion_urls()
            youtube_module.write_push_conf(urls)
            youtube_module.reload_nginx()
        except Exception as e:
            logger.warning("YouTube initial push refresh: %s", e)
        youtube_module.start_youtube_push_refresh_thread()
    app.run(host=s.api.host, port=s.api.port)


if __name__ == "__main__":
    run()
