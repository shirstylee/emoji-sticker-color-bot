"""Cancellation-aware, frame-streamed FFmpeg WEBM recoloring."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import numpy as np

from app.constants import TELEGRAM_VIDEO_MAX_DURATION_SECONDS, TELEGRAM_VIDEO_MAX_FPS
from app.recolor.color_math import ParsedColor, recolor_rgb

DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
VIDEO_RE = re.compile(
    r"Video:\s*(?P<codec>[^,\s]+).*?\b(?P<width>\d{2,5})x(?P<height>\d{2,5})\b"
    r".*?(?P<fps>\d+(?:\.\d+)?)\s*fps",
    re.DOTALL,
)


class WebmError(ValueError):
    """WEBM probing, decoding, recoloring, or encoding failed safely."""


@dataclass(frozen=True, slots=True)
class WebmInfo:
    width: int
    height: int
    fps: float
    duration: float
    codec: str
    has_audio: bool
    has_alpha: bool


def ffmpeg_executable() -> Path:
    path = Path(imageio_ffmpeg.get_ffmpeg_exe())
    if not path.is_file():
        raise WebmError("FFmpeg executable is unavailable")
    return path


async def _run_capture(arguments: list[str], timeout: float) -> tuple[int, bytes, bytes]:
    process = await asyncio.create_subprocess_exec(
        *arguments,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
    except TimeoutError:
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
        raise WebmError("FFmpeg operation timed out") from None
    return process.returncode or 0, stdout, stderr


async def probe_webm(path: Path, *, timeout: float = 20) -> WebmInfo:
    with path.open("rb") as source:
        signature = source.read(4)
    if signature != b"\x1aE\xdf\xa3":
        raise WebmError("File is not WEBM/EBML")
    _, _, stderr = await _run_capture(
        [str(ffmpeg_executable()), "-hide_banner", "-i", str(path)], timeout
    )
    report = stderr.decode("utf-8", errors="replace")
    duration_match = DURATION_RE.search(report)
    video_match = VIDEO_RE.search(report)
    if not duration_match or not video_match:
        raise WebmError("FFmpeg could not identify the WEBM video stream")
    hours, minutes, seconds = duration_match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return WebmInfo(
        width=int(video_match.group("width")),
        height=int(video_match.group("height")),
        fps=float(video_match.group("fps")),
        duration=duration,
        codec=video_match.group("codec").lower(),
        has_audio=bool(re.search(r"Stream #[^\r\n]+:\s*Audio:", report)),
        has_alpha="alpha_mode" in report or "yuva" in report,
    )


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        process.kill()
        await process.wait()


async def recolor_webm_file(
    source: Path,
    destination: Path,
    target: ParsedColor,
    *,
    side: int,
    cancel_event: asyncio.Event,
    timeout: float = 180,
    crf: int = 34,
) -> Path:
    info = await probe_webm(source)
    if info.duration > TELEGRAM_VIDEO_MAX_DURATION_SECONDS + 0.01:
        raise WebmError("Video duration exceeds Telegram's 3-second limit")
    fps = min(info.fps, float(TELEGRAM_VIDEO_MAX_FPS))
    ratio = min(side / info.width, side / info.height)
    width = max(2, round(info.width * ratio / 2) * 2)
    height = max(2, round(info.height * ratio / 2) * 2)
    frame_size = width * height * 4
    ffmpeg = str(ffmpeg_executable())
    decoder = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-v",
        "error",
        "-i",
        str(source),
        "-an",
        "-vf",
        f"fps={fps:.4f},scale={width}:{height}:flags=lanczos",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "pipe:1",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoder = await asyncio.create_subprocess_exec(
        ffmpeg,
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{fps:.4f}",
        "-i",
        "pipe:0",
        "-vf",
        f"pad={side}:{side}:(ow-iw)/2:(oh-ih)/2:color=black@0",
        "-an",
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p",
        "-auto-alt-ref",
        "0",
        "-deadline",
        "good",
        "-cpu-used",
        "2",
        "-crf",
        str(crf),
        "-b:v",
        "0",
        "-y",
        str(destination),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    decoder_stdout = decoder.stdout
    encoder_stdin = encoder.stdin
    if decoder_stdout is None or encoder_stdin is None:
        await _stop_process(decoder)
        await _stop_process(encoder)
        raise WebmError("FFmpeg streaming pipes are unavailable")

    async def process_frames() -> None:
        while True:
            if cancel_event.is_set():
                raise asyncio.CancelledError
            try:
                payload = await decoder_stdout.readexactly(frame_size)
            except asyncio.IncompleteReadError as error:
                if error.partial:
                    raise WebmError("FFmpeg returned an incomplete RGBA frame") from error
                break
            frame = np.frombuffer(payload, dtype=np.uint8).reshape(height, width, 4)
            alpha = frame[..., 3].copy()
            recolored = await asyncio.to_thread(
                recolor_rgb,
                frame[..., :3],
                target,
                weights=alpha.astype(np.float64) / 255.0,
            )
            output = np.empty_like(frame)
            output[..., :3] = recolored
            output[..., 3] = alpha
            encoder_stdin.write(output.tobytes())
            await encoder_stdin.drain()
        encoder_stdin.close()
        await encoder_stdin.wait_closed()
        await decoder.wait()
        await encoder.wait()
        if decoder.returncode or encoder.returncode:
            raise WebmError("FFmpeg failed to transcode the WEBM video")

    try:
        await asyncio.wait_for(process_frames(), timeout=timeout)
    except (TimeoutError, asyncio.CancelledError):
        await _stop_process(decoder)
        await _stop_process(encoder)
        if destination.exists():
            destination.unlink()
        if cancel_event.is_set():
            raise asyncio.CancelledError from None
        raise WebmError("FFmpeg processing timed out") from None
    except BaseException:
        await _stop_process(decoder)
        await _stop_process(encoder)
        if destination.exists():
            destination.unlink()
        raise
    return destination


async def optimize_webm(
    source: Path,
    destination: Path,
    target: ParsedColor,
    *,
    side: int,
    maximum_bytes: int,
    cancel_event: asyncio.Event,
    timeout: float,
) -> Path:
    for attempt, crf in enumerate((30, 34, 38, 42), 1):
        candidate = destination.with_name(f"{destination.stem}_{attempt}{destination.suffix}")
        await recolor_webm_file(
            source,
            candidate,
            target,
            side=side,
            cancel_event=cancel_event,
            timeout=timeout,
            crf=crf,
        )
        if candidate.stat().st_size <= maximum_bytes:
            candidate.replace(destination)
            return destination
        candidate.unlink(missing_ok=True)
    raise WebmError("WEBM cannot be optimized under Telegram's size limit")
