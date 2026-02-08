"""
Stream worker entrypoint: demux → overlay → PTS/DTS rewrite → encode.
On source unavailability: hold last frame until source returns; recover automatically (spec).
Overlay: periodic read from DB (5–10 s); when DB unreachable keep last known (spec).
"""

import logging
import sys
import threading
import time

import av

from config.settings import get_settings
from stream_workers import demux, encode, overlay, pts_dts, rtmp_out

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Stub overlay data until DB connected; then refresh loop updates it
overlay.set_overlay_data(
    [{"position": i, "identifier": f"Donor{i}", "amount": 100 - i} for i in range(1, 11)],
    [{"message": "PIX received from Donor1"}],
)

_last_frame_holder: list[av.VideoFrame | None] = [None]


def _overlay_refresh_loop() -> None:
    """Periodic overlay state read from DB; on failure keep last known (contract)."""
    try:
        from stream_workers import db as db_module
    except ImportError:
        return
    while True:
        time.sleep(get_settings().worker.overlay_refresh_interval_seconds)
        try:
            ranking, alerts, payment_link = db_module.get_overlay_snapshot()
            overlay.set_overlay_data(ranking, alerts, payment_link)
        except Exception as e:
            logger.debug("Overlay DB unreachable, keeping last known: %s", e)


def run_pipeline(input_path: str) -> None:
    """Run demux → overlay → PTS/DTS → encode. Hold last frame when source unavailable. Optional RTMP out."""
    enc = None
    rtmp_proc = None
    t = threading.Thread(target=_overlay_refresh_loop, daemon=True)
    t.start()
    rtmp_url = get_settings().worker.rtmp_output_url.strip()
    while True:
        container = None
        try:
            container = demux.open_input(input_path)
            video_stream = demux.get_video_stream(container)
            if not video_stream:
                raise ValueError("No video stream")
            enc_cfg = get_settings().encoding
            enc = encode.create_video_encoder(
                width=video_stream.width or enc_cfg.default_width,
                height=video_stream.height or enc_cfg.default_height,
                fps=enc_cfg.fps,
            )
            if rtmp_url and rtmp_proc is None:
                rtmp_proc = rtmp_out.start_rtmp_process(rtmp_url)
            for packet in demux.iter_packets(container):
                for frame in packet.decode():
                    if isinstance(frame, av.VideoFrame):
                        _last_frame_holder[0] = frame
                        pts_dts.rewrite_pts_dts(frame)
                        for pkt in encode.encode_frame(enc, frame):
                            if rtmp_proc and rtmp_proc.stdin is not None:
                                if not rtmp_out.write_packet(rtmp_proc, bytes(pkt)):
                                    rtmp_proc = None
        except Exception as e:
            logger.warning("%s", e)
            if container is None:
                time.sleep(get_settings().worker.source_retry_interval_seconds)
                continue
        finally:
            if container is not None:
                container.close()
            if rtmp_proc is not None and rtmp_proc.stdin is not None:
                try:
                    rtmp_proc.stdin.close()
                except OSError:
                    pass
                rtmp_proc.wait(timeout=5)
                rtmp_proc = None
        time.sleep(0.1)


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        run_pipeline(get_settings().worker.default_input_url)
    else:
        run_pipeline(sys.argv[1])
