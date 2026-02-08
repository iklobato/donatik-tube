"""
Linear, monotonic PTS/DTS rewrite across loop and source changes (FR-004).
Avoids visible discontinuities or jitter to YouTube Live when file loops or source switches.
"""

import logging

import av

logger = logging.getLogger(__name__)


# Running base for continuous timestamps (time_base units).
class _PTSState:
    __slots__ = ("next_pts", "next_dts")

    def __init__(self) -> None:
        self.next_pts = 0
        self.next_dts = 0


_pts_state = _PTSState()


def get_time_base() -> tuple[int, int]:
    """Return time_base for 30fps video (e.g. 1/30)."""
    return (1, 30)


def rewrite_pts_dts(frame: av.VideoFrame | av.AudioFrame) -> None:
    """
    Rewrite frame PTS/DTS to be linear and monotonic.
    Mutates frame in place; uses module-level running counters.
    """
    if frame.pts is None and frame.dts is None:
        return
    if frame.pts is not None:
        frame.pts = _pts_state.next_pts
        _pts_state.next_pts += 1
    if frame.dts is not None:
        frame.dts = _pts_state.next_dts
        _pts_state.next_dts += 1


def reset_pts_dts() -> None:
    """Reset running counters (e.g. on intentional stream restart)."""
    _pts_state.next_pts = 0
    _pts_state.next_dts = 0
