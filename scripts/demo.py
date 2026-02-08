import argparse
import logging
import os
import signal
import subprocess
import sys

import av
from PIL import Image

from config.settings import get_settings
from overlay_api import youtube as youtube_module
from stream_workers import demux, encode, overlay, pts_dts, rtmp_out

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)


def _frame_to_pil(frame: av.VideoFrame) -> Image.Image:
    rgb = frame.reformat(format="rgb24")
    w, h = rgb.width, rgb.height
    data = rgb.planes[0].to_bytes()
    return Image.frombytes("RGB", (w, h), data)


def _pil_to_yuv420p_frame(pil_image: Image.Image, width: int, height: int) -> av.VideoFrame:
    rgb_frame = av.VideoFrame(width, height, format="rgb24")
    rgb_frame.planes[0].update(pil_image.tobytes())
    return rgb_frame.reformat(format="yuv420p")


def _draw_overlay_on_frame(frame: av.VideoFrame) -> av.VideoFrame:
    pil = _frame_to_pil(frame)
    out_pil = overlay.render_overlay_on_image(pil)
    return _pil_to_yuv420p_frame(out_pil, frame.width, frame.height)


def _stop_ffmpeg(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.stdin is None:
        return
    try:
        proc.stdin.close()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


def _process_file(
    file_path: str,
    enc_cfg: object,
    enc: av.CodecContext | None,
    rtmp_proc: subprocess.Popen[bytes] | None,
    shutdown_flag: list[bool],
) -> tuple[av.CodecContext | None, subprocess.Popen[bytes] | None, bool]:
    container = demux.open_input(file_path)
    try:
        video_stream = demux.get_video_stream(container)
        if not video_stream:
            logger.error("No video stream in file")
            return (enc, rtmp_proc, True)
        if enc is None:
            enc = encode.create_video_encoder(
                width=video_stream.width or enc_cfg.default_width,
                height=video_stream.height or enc_cfg.default_height,
                fps=enc_cfg.fps,
            )
        for packet in demux.iter_packets(container):
            if shutdown_flag[0]:
                return (enc, rtmp_proc, True)
            for frame in packet.decode():
                if not isinstance(frame, av.VideoFrame):
                    continue
                overlay_frame = _draw_overlay_on_frame(frame)
                pts_dts.rewrite_pts_dts(overlay_frame)
                for pkt in encode.encode_frame(enc, overlay_frame):
                    if rtmp_proc and rtmp_proc.stdin is not None:
                        if not rtmp_out.write_packet(rtmp_proc, bytes(pkt)):
                            rtmp_proc = None
                            break
        return (enc, rtmp_proc, False)
    finally:
        container.close()


def run_pipeline(
    file_path: str,
    payment_url: str,
    payment_label: str,
    loop: bool,
    shutdown_flag: list[bool],
) -> int:
    overlay.set_overlay_data(ranking=[], alerts=[], payment_link={"url": payment_url, "label": payment_label})

    urls = youtube_module.get_ingestion_urls()
    if not urls:
        logger.error(
            "No YouTube ingestion URL. Set YOUTUBE__CLIENT_ID, YOUTUBE__CLIENT_SECRET, "
            "YOUTUBE__REFRESH_TOKENS (JSON, e.g. from /youtube/connect)."
        )
        return 1

    rtmp_proc = rtmp_out.start_rtmp_process(urls[0])
    if rtmp_proc is None:
        logger.error("Failed to start FFmpeg. Is ffmpeg installed?")
        return 1

    enc_cfg = get_settings().encoding
    enc: av.CodecContext | None = None
    try:
        while not shutdown_flag[0]:
            enc, rtmp_proc, should_exit = _process_file(
                file_path, enc_cfg, enc, rtmp_proc, shutdown_flag
            )
            if should_exit or not loop or shutdown_flag[0]:
                break
    finally:
        _stop_ffmpeg(rtmp_proc)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stream a video file to YouTube Live with payment link overlay (prototype)."
    )
    parser.add_argument("video_file", help="Path to video file (e.g. .mp4)")
    parser.add_argument("--payment-url", required=True, help="Payment/donation URL to show on overlay")
    parser.add_argument("--payment-label", default="Donate", help="Label for the payment link (default: Donate)")
    parser.add_argument("--loop", action="store_true", help="Restart video from start when it ends")
    args = parser.parse_args()

    if not os.path.isfile(args.video_file):
        logger.error("File not found: %s", args.video_file)
        return 1

    shutdown_flag: list[bool] = [False]

    def on_sigint(_signum: int, _frame: object) -> None:
        shutdown_flag[0] = True

    signal.signal(signal.SIGINT, on_sigint)
    return run_pipeline(
        file_path=args.video_file,
        payment_url=args.payment_url,
        payment_label=args.payment_label,
        loop=args.loop,
        shutdown_flag=shutdown_flag,
    )


if __name__ == "__main__":
    sys.exit(main())
