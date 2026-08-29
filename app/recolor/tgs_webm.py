"""Render Telegram TGS animations to sendable transparent WEBM stickers."""

from __future__ import annotations

import asyncio
import contextlib
import math
from dataclasses import dataclass
from pathlib import Path

from rlottie_python.rlottie_wrapper import LottieAnimation

from app.constants import TELEGRAM_VIDEO_MAX_DURATION_SECONDS, TELEGRAM_VIDEO_MAX_FPS
from app.recolor.webm import ffmpeg_executable


class TgsRenderError(ValueError):
    """A TGS animation could not be rendered as a Telegram video sticker."""


@dataclass(frozen=True, slots=True)
class RenderableAnimation:
    animation: LottieAnimation
    width: int
    height: int
    fps: float
    frames: int
    duration: float

    def render(self, frame: int) -> bytes:
        return self.animation.lottie_animation_render(
            frame_num=frame,
            width=self.width,
            height=self.height,
        )


def _load_animation(source: Path) -> RenderableAnimation:
    try:
        animation = LottieAnimation.from_tgs(str(source))
        width, height = animation.lottie_animation_get_size()
        fps = float(animation.lottie_animation_get_framerate())
        frames = int(animation.lottie_animation_get_totalframe())
        duration = float(animation.lottie_animation_get_duration())
    except (OSError, RuntimeError, UnicodeError, ValueError) as error:
        raise TgsRenderError("TGS renderer could not load the animation") from error
    if width <= 0 or height <= 0:
        raise TgsRenderError("TGS renderer returned invalid dimensions")
    if fps <= 0 or frames <= 0:
        raise TgsRenderError("TGS renderer returned invalid timing")
    if duration > TELEGRAM_VIDEO_MAX_DURATION_SECONDS + 0.01:
        raise TgsRenderError("TGS animation exceeds Telegram's 3-second limit")
    return RenderableAnimation(animation, width, height, fps, frames, duration)


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=5)
    except TimeoutError:
        process.kill()
        await process.wait()


async def _render_attempt(
    source: Path,
    destination: Path,
    *,
    side: int,
    cancel_event: asyncio.Event,
    timeout: float,
    crf: int,
) -> Path:
    animation = await asyncio.to_thread(_load_animation, source)
    source_fps = float(animation.fps)
    output_fps = min(source_fps, float(TELEGRAM_VIDEO_MAX_FPS))
    duration = min(
        float(animation.duration),
        float(animation.frames) / source_fps,
        TELEGRAM_VIDEO_MAX_DURATION_SECONDS,
    )
    output_frames = max(1, math.ceil(duration * output_fps - 1e-9))
    frame_indices = [
        min(animation.frames - 1, int(index * source_fps / output_fps))
        for index in range(output_frames)
    ]
    width, height = animation.width, animation.height
    destination.parent.mkdir(parents=True, exist_ok=True)
    process = await asyncio.create_subprocess_exec(
        str(ffmpeg_executable()),
        "-v",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgra",
        "-s",
        f"{width}x{height}",
        "-r",
        f"{output_fps:.4f}",
        "-i",
        "pipe:0",
        "-vf",
        (
            f"scale={side}:{side}:force_original_aspect_ratio=decrease:flags=lanczos,"
            f"pad={side}:{side}:(ow-iw)/2:(oh-ih)/2:color=black@0"
        ),
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
        stderr=asyncio.subprocess.PIPE,
    )
    writer = process.stdin
    if writer is None:
        await _stop_process(process)
        raise TgsRenderError("FFmpeg input pipe is unavailable")

    async def stream_frames() -> None:
        for frame_index in frame_indices:
            if cancel_event.is_set():
                raise asyncio.CancelledError
            frame = await asyncio.to_thread(animation.render, frame_index)
            if len(frame) != height * width * 4:
                raise TgsRenderError("TGS renderer returned an invalid BGRA frame")
            writer.write(frame)
            await writer.drain()
        writer.close()
        with contextlib.suppress(BrokenPipeError, ConnectionResetError):
            await writer.wait_closed()
        _, stderr = await process.communicate()
        if process.returncode:
            detail = stderr.decode("utf-8", errors="replace").strip()
            raise TgsRenderError(f"FFmpeg could not encode the TGS preview: {detail[-300:]}")

    try:
        await asyncio.wait_for(stream_frames(), timeout=timeout)
    except (TimeoutError, asyncio.CancelledError):
        await _stop_process(process)
        destination.unlink(missing_ok=True)
        if cancel_event.is_set():
            raise asyncio.CancelledError from None
        raise TgsRenderError("TGS preview rendering timed out") from None
    except BaseException:
        await _stop_process(process)
        destination.unlink(missing_ok=True)
        raise
    return destination


async def render_tgs_webm(
    source: Path,
    destination: Path,
    *,
    side: int,
    maximum_bytes: int,
    cancel_event: asyncio.Event,
    timeout: float,
) -> Path:
    """Render a TGS once per quality level without buffering all frames in RAM."""

    for attempt, crf in enumerate((30, 34, 38, 42), 1):
        candidate = destination.with_name(f"{destination.stem}_{attempt}{destination.suffix}")
        await _render_attempt(
            source,
            candidate,
            side=side,
            cancel_event=cancel_event,
            timeout=timeout,
            crf=crf,
        )
        if candidate.stat().st_size <= maximum_bytes:
            candidate.replace(destination)
            return destination
        candidate.unlink(missing_ok=True)
    raise TgsRenderError("Rendered TGS cannot fit Telegram's WEBM size limit")
