"""
RTMP output via FFmpeg: raw H.264 on stdin, silent audio; outputs FLV to RTMP URL.
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


def start_rtmp_process(rtmp_url: str) -> subprocess.Popen[bytes] | None:
    """Start FFmpeg: -f h264 pipe, anullsrc, -c:v copy -c:a aac -f flv rtmp_url. Returns process or None."""
    cmd = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-f",
        "h264",
        "-i",
        "pipe:0",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-shortest",
        "-f",
        "flv",
        rtmp_url,
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        return proc
    except FileNotFoundError:
        logger.warning("ffmpeg not found; RTMP output disabled")
        return None
    except Exception as e:
        logger.warning("FFmpeg start failed: %s", e)
        return None


def write_packet(proc: subprocess.Popen[bytes], data: bytes) -> bool:
    """Write one H.264 packet to FFmpeg stdin. Returns False if write failed (e.g. process dead)."""
    if proc.stdin is None:
        return False
    try:
        proc.stdin.write(data)
        proc.stdin.flush()
        return True
    except (BrokenPipeError, OSError) as e:
        logger.debug("RTMP write failed: %s", e)
        return False
