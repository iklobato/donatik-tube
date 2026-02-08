"""
Overlay rendering: Top 10 donor ranking and PIX alerts via Pillow with antialiasing.
Accepts in-memory data (stub); US3 will plug DB snapshot. Keep last known when DB unreachable.
"""

import logging
from typing import Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# In-memory stub: list of {position, identifier, amount}; list of {message}; optional payment_link {url, label}
class _OverlayState:
    __slots__ = ("ranking", "alerts", "payment_link")

    def __init__(self) -> None:
        self.ranking: list[dict[str, Any]] = []
        self.alerts: list[dict[str, Any]] = []
        self.payment_link: dict[str, Any] | None = None


_overlay_state = _OverlayState()


def set_overlay_data(
    ranking: list[dict[str, Any]],
    alerts: list[dict[str, Any]],
    payment_link: dict[str, Any] | None = None,
) -> None:
    """Set current overlay data (stub or from DB). When DB unreachable, keep last known."""
    if not ranking and alerts is None and payment_link is None:
        return
    if ranking:
        _overlay_state.ranking = ranking
    if alerts is not None:
        _overlay_state.alerts = alerts
    _overlay_state.payment_link = payment_link


def get_overlay_data() -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], dict[str, Any] | None
]:
    """Return (ranking, alerts, payment_link) for rendering. Uses last known if DB failed."""
    return (_overlay_state.ranking, _overlay_state.alerts, _overlay_state.payment_link)


def render_overlay_on_image(pil_image: Image.Image) -> Image.Image:
    """
    Draw Top 10 ranking, PIX alerts, and payment link (when present) on the image.
    When payment_link is None, no payment link area is drawn (no placeholder).
    """
    ranking, alerts, payment_link = get_overlay_data()
    if not ranking and not alerts and not payment_link:
        return pil_image
    overlay = pil_image.copy()
    draw = ImageDraw.Draw(overlay, "RGBA")
    font = ImageFont.load_default()
    y = 10
    for i, entry in enumerate(ranking[:10], 1):
        text = f"#{i} {entry.get('identifier', '')} {entry.get('amount', '')}"
        draw.text((10, y), text, fill=(255, 255, 255, 220), font=font)
        y += 20
    for a in alerts:
        draw.text((10, y), a.get("message", ""), fill=(255, 255, 0, 220), font=font)
        y += 20
    if payment_link:
        label = payment_link.get("label") or "Donate"
        url = payment_link.get("url") or ""
        draw.text((10, y), label, fill=(200, 255, 200, 220), font=font)
        y += 20
        if url:
            draw.text((10, y), url, fill=(200, 255, 200, 200), font=font)
    return overlay
