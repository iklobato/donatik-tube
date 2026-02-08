"""
Demux MP4 (H.264/AAC) and RTSP over TCP via PyAV.
Yields decoded video/audio packets for the pipeline.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import av

logger = logging.getLogger(__name__)


def open_input(path_or_url: str, options: dict[str, str] | None = None) -> av.container.InputContainer:
    """Open MP4 file or RTSP URL. RTSP uses TCP when options include 'rtsp_transport': 'tcp'."""
    opts = options or {}
    if not path_or_url.startswith("rtsp://"):
        return av.open(path_or_url, options=opts)
    opts.setdefault("rtsp_transport", "tcp")
    return av.open(path_or_url, options=opts)


def iter_packets(
    container: av.container.InputContainer,
) -> Iterator[av.Packet]:
    """Iterate over packets (demux). Use decode in pipeline for frames."""
    yield from container.demux()


def get_video_stream(container: av.container.InputContainer) -> av.VideoStream | None:
    """Return first video stream (H.264 expected)."""
    if container.streams.video:
        return container.streams.video[0]
    return None


def get_audio_stream(container: av.container.InputContainer) -> av.AudioStream | None:
    """Return first audio stream (AAC expected)."""
    if container.streams.audio:
        return container.streams.audio[0]
    return None
