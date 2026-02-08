"""
Encode with libx264 or h264_nvenc: CBR 4500kbps, GOP 2s, profile high, level 4.1, zerolatency.
Uses config.settings encoding. On capacity exceeded: drop frames and log (FR-009).
"""

import logging

import av

from config.settings import get_settings

logger = logging.getLogger(__name__)


def create_video_encoder(
    width: int | None = None,
    height: int | None = None,
    fps: int | None = None,
) -> av.CodecContext:
    """Create H.264 encoder with CBR, GOP 2s, high/4.1, zerolatency."""
    enc = get_settings().encoding
    w = width if width is not None else enc.default_width
    h = height if height is not None else enc.default_height
    f = fps if fps is not None else enc.fps
    codec = av.CodecContext.create(enc.encoder, "w")
    codec.width = w
    codec.height = h
    codec.time_base = (1, f)
    codec.bit_rate = enc.cbr_bitrate_k * 1000
    codec.gop_size = enc.gop_frames
    codec.options = {
        "profile": enc.profile,
        "level": enc.level,
        "tune": enc.tune,
        "nal-hrd": "cbr",
    }
    return codec


def encode_frame(encoder: av.CodecContext, frame: av.VideoFrame) -> list[av.Packet]:
    """
    Encode one frame. On capacity exceeded (e.g. encoder backlog), drop frame and log/alert.
    Stream continues; no silent data loss (FR-009).
    """
    try:
        return list(encoder.encode(frame))
    except (MemoryError, BlockingIOError, BufferError) as e:
        logger.warning("Encode drop (capacity exceeded), stream continues: %s", e)
        return []
