import argparse
import logging
import os
import signal
import subprocess
import sys
from dataclasses import dataclass

import av
from PIL import Image
from pydantic import BaseModel, model_validator

from config.settings import EncodingSettings, get_settings
from overlay_api import youtube as youtube_module
from stream_workers import demux, encode, overlay, pts_dts, rtmp_out

logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)

FFMPEG_STOP_TIMEOUT = 5.0


class StreamDemoConfig(BaseModel):
    video_file: str
    payment_url: str
    payment_label: str = "Donate"
    loop: bool = False
    encoding: EncodingSettings

    @model_validator(mode="after")
    def _video_file_exists(self) -> "StreamDemoConfig":
        if not os.path.isfile(self.video_file):
            raise ValueError(f"File not found: {self.video_file}")
        return self


@dataclass
class PipelineState:
    encoder: av.CodecContext | None
    rtmp_proc: subprocess.Popen[bytes] | None


class StreamPipeline:
    def __init__(self, config: StreamDemoConfig) -> None:
        self.config = config
        self._state: PipelineState | None = None

    def run(self, shutdown: list[bool]) -> int:
        overlay.set_overlay_data(
            ranking=[],
            alerts=[],
            payment_link={"url": self.config.payment_url, "label": self.config.payment_label},
        )

        rtmp_proc = self._start_rtmp()
        if rtmp_proc is None:
            logger.error("Failed to start FFmpeg. Is ffmpeg installed?")
            return 1

        self._state = PipelineState(encoder=None, rtmp_proc=rtmp_proc)
        while not shutdown[0]:
            if self._process_file(shutdown) or not self.config.loop:
                break
        self._stop_ffmpeg(self._state.rtmp_proc)
        return 0

    def _start_rtmp(self) -> subprocess.Popen[bytes] | None:
        urls = youtube_module.get_ingestion_urls()
        if not urls:
            logger.error(
                "No YouTube ingestion URL. Set YOUTUBE__CLIENT_ID, YOUTUBE__CLIENT_SECRET, "
                "YOUTUBE__REFRESH_TOKENS (e.g. from /youtube/connect)."
            )
            return None
        return rtmp_out.start_rtmp_process(urls[0])

    def _stop_ffmpeg(self, proc: subprocess.Popen[bytes] | None) -> None:
        if proc is None or proc.stdin is None:
            return
        proc.stdin.close()
        proc.wait(timeout=FFMPEG_STOP_TIMEOUT)

    def _process_file(self, shutdown: list[bool]) -> bool:
        assert self._state is not None
        container = demux.open_input(self.config.video_file)
        stream = demux.get_video_stream(container)
        if not stream:
            logger.error("No video stream in file")
            container.close()
            return True

        if self._state.encoder is None:
            c = self.config.encoding
            self._state.encoder = encode.create_video_encoder(
                width=stream.width or c.default_width,
                height=stream.height or c.default_height,
                fps=c.fps,
            )

        for packet in demux.iter_packets(container):
            if shutdown[0]:
                container.close()
                return True
            for frame in packet.decode():
                if isinstance(frame, av.VideoFrame):
                    self._process_frame(frame)
        container.close()
        return False

    def _process_frame(self, frame: av.VideoFrame) -> None:
        assert self._state is not None
        encoder = self._state.encoder
        rtmp_proc = self._state.rtmp_proc
        if encoder is None or rtmp_proc is None or rtmp_proc.stdin is None:
            return

        rgb = frame.reformat(format="rgb24")
        pil = Image.frombytes("RGB", (rgb.width, rgb.height), rgb.planes[0].to_bytes())
        pil = overlay.render_overlay_on_image(pil)
        out_rgb = av.VideoFrame(frame.width, frame.height, format="rgb24")
        out_rgb.planes[0].update(pil.tobytes())
        out_frame = out_rgb.reformat(format="yuv420p")
        pts_dts.rewrite_pts_dts(out_frame)

        for pkt in encode.encode_frame(encoder, out_frame):
            if self._state.rtmp_proc is None:
                return
            if not rtmp_out.write_packet(self._state.rtmp_proc, bytes(pkt)):
                self._state.rtmp_proc = None
                return


def main() -> int:
    parser = argparse.ArgumentParser(description="Stream a video file to YouTube Live with payment link overlay.")
    parser.add_argument("video_file", help="Path to video file (e.g. .mp4)")
    parser.add_argument("--payment-url", required=True, help="Payment URL for overlay")
    parser.add_argument("--payment-label", default="Donate", help="Label for payment link")
    parser.add_argument("--loop", action="store_true", help="Restart video when it ends")
    args = parser.parse_args()
    config = StreamDemoConfig(
        video_file=args.video_file,
        payment_url=args.payment_url,
        payment_label=args.payment_label,
        loop=args.loop,
        encoding=get_settings().encoding,
    )

    shutdown: list[bool] = [False]

    def on_sigint(_sig: int, _frame: object) -> None:
        shutdown[0] = True

    signal.signal(signal.SIGINT, on_sigint)
    return StreamPipeline(config).run(shutdown)


if __name__ == "__main__":
    sys.exit(main())
