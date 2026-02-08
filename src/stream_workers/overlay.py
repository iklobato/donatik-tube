"""
Overlay rendering: Top 10 donor ranking and PIX alerts via Pillow with antialiasing.
Accepts in-memory data (stub); US3 will plug DB snapshot. Keep last known when DB unreachable.
"""

import logging
from typing import Any

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


# In-memory stub: list of {position, identifier, amount}; list of {message, show_at, hide_at}
class _OverlayState:
    __slots__ = ("ranking", "alerts")

    def __init__(self) -> None:
        self.ranking: list[dict[str, Any]] = []
        self.alerts: list[dict[str, Any]] = []


_overlay_state = _OverlayState()


def set_overlay_data(
    ranking: list[dict[str, Any]], alerts: list[dict[str, Any]]
) -> None:
    """Set current overlay data (stub or from DB). When DB unreachable, keep last known."""
    if not ranking and alerts is None:
        return
    if ranking:
        _overlay_state.ranking = ranking
    if alerts is not None:
        _overlay_state.alerts = alerts


def get_overlay_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (ranking, alerts) for rendering. Uses last known if DB failed."""
    return (_overlay_state.ranking, _overlay_state.alerts)


def render_overlay_on_image(pil_image: Image.Image) -> Image.Image:
    """
    Draw Top 10 ranking and PIX alerts on the image. Uses antialiasing where applicable.
    Returns a new image (or same if no overlay).
    """
    ranking, alerts = get_overlay_data()
    if not ranking and not alerts:
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
    return overlay
