"""Cancellation-aware, frame-streamed FFmpeg WEBM recoloring."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import numpy as np

from app.constants import (
    TELEGRAM_VIDEO_MAX_DURATION_SECONDS,
    TELEGRAM_VIDEO_MAX_FPS,
    TELEGRAM_VIDEO_SAFE_DURATION_SECONDS,
)
from app.recolor.color_math import (
    ParsedColor,
    adaptive_alpha,
    recolor_rgb,
    recolor_texture_rgb,
)
from app.recolor.raster import is_textured_image

DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
VIDEO_RE = re.compile(
    r"Video:\s*(?P<codec>[^,\s]+)[^\r\n]*?"
    r"\b(?P<width>\d{2,5})x(?P<height>\d{2,5})\b[^\r\n]*"
)
FPS_RE = re.compile(r"(?P<fps>\d+(?:\.\d+)?)\s*fps")
TBR_RE = re.compile(r"(?P<tbr>\d+(?:\.\d+)?)\s*tbr")
OUT_TIME_RE = re.compile(r"out_time=(\d+):(\d+):(\d+(?:\.\d+)?)")
FRAME_RE = re.compile(r"^frame=(\d+)$", re.MULTILINE)


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
    if not video_match:
        raise WebmError("FFmpeg could not identify the WEBM video stream")
    video_line = video_match.group(0)
    fps_match = FPS_RE.search(video_line) or TBR_RE.search(video_line)
    duration = _timestamp_seconds(duration_match.groups()) if duration_match else 0.0
    fps = 0.0
    if fps_match:
        fps_value = fps_match.groupdict().get("fps") or fps_match.groupdict().get("tbr")
        if fps_value is not None:
            fps = float(fps_value)

    if duration <= 0 or fps <= 0:
        # Some valid Telegram WEBM files omit the container Duration field and
        # expose only ``tbr`` instead of ``fps``. Scan at most 3.2 seconds and
        # use FFmpeg's machine-readable progress rather than rejecting them.
        scan_arguments = [
            str(ffmpeg_executable()),
            "-v",
            "error",
            "-progress",
            "pipe:1",
            "-nostats",
        ]
        if video_match.group("codec").lower() == "vp9":
            scan_arguments.extend(("-c:v", "libvpx-vp9"))
        scan_arguments.extend(
            (
                "-i",
                str(path),
                "-map",
                "0:v:0",
                "-t",
                f"{TELEGRAM_VIDEO_MAX_DURATION_SECONDS + 0.2:.1f}",
                "-f",
                "null",
                "-",
            )
        )
        scan_code, stdout, scan_stderr = await _run_capture(scan_arguments, timeout)
        progress = stdout.decode("utf-8", errors="replace")
        if scan_code:
            detail = scan_stderr.decode("utf-8", errors="replace").strip()
            raise WebmError(detail or "FFmpeg could not decode the WEBM video stream")
        time_matches = OUT_TIME_RE.findall(progress)
        if duration <= 0 and time_matches:
            duration = _timestamp_seconds(time_matches[-1])
        frames = FRAME_RE.findall(progress)
        frame_count = int(frames[-1]) if frames else 0
        if fps <= 0 and duration > 0 and frame_count > 0:
            fps = frame_count / duration
        if duration <= 0 and fps > 0 and frame_count > 0:
            duration = frame_count / fps
    if duration <= 0 or fps <= 0:
        raise WebmError("FFmpeg could not determine WEBM timing")
    return WebmInfo(
        width=int(video_match.group("width")),
        height=int(video_match.group("height")),
        fps=fps,
        duration=duration,
        codec=video_match.group("codec").lower(),
        has_audio=bool(re.search(r"Stream #[^\r\n]+:\s*Audio:", report)),
        has_alpha="alpha_mode" in report or "yuva" in report,
    )


def _timestamp_seconds(parts: Sequence[str]) -> float:
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


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
    adaptive: bool = False,
    strong: bool = False,
    intensity: float = 1.0,
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
    decoder_arguments = [ffmpeg, "-v", "error"]
    if info.codec == "vp9":
        # FFmpeg's native VP9 decoder discards WebM BlockAdditional alpha on
        # several builds. libvpx-vp9 reconstructs the actual RGBA frames.
        decoder_arguments.extend(("-c:v", "libvpx-vp9"))
    decoder_arguments.extend((
        "-i",
        str(source),
        "-t",
        f"{TELEGRAM_VIDEO_SAFE_DURATION_SECONDS:.2f}",
        "-an",
        "-vf",
        f"fps={fps:.4f},scale={width}:{height}:flags=lanczos",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "pipe:1",
    ))
    decoder = await asyncio.create_subprocess_exec(
        *decoder_arguments,
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
        texture_mode: bool | None = None
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
            output = np.empty_like(frame)
            if adaptive:
                output[..., :3] = 255
                output[..., 3] = await asyncio.to_thread(
                    adaptive_alpha, frame[..., :3], alpha
                )
            elif strong:
                output[..., :3] = await asyncio.to_thread(
                    recolor_rgb,
                    frame[..., :3],
                    target,
                    weights=alpha.astype(np.float64) / 255.0,
                    chroma_scale=1.35,
                    contrast_scale=0.62,
                    strength=intensity,
                )
                output[..., 3] = alpha
            else:
                if texture_mode is None:
                    texture_mode = await asyncio.to_thread(
                        is_textured_image, frame[..., :3], alpha
                    )
                if texture_mode:
                    output[..., :3] = await asyncio.to_thread(
                        recolor_texture_rgb,
                        frame[..., :3],
                        target,
                        strength=float(np.clip(0.72 * intensity, 0.0, 1.0)),
                    )
                else:
                    output[..., :3] = await asyncio.to_thread(
                        recolor_rgb,
                        frame[..., :3],
                        target,
                        weights=alpha.astype(np.float64) / 255.0,
                        strength=intensity,
                    )
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
    adaptive: bool = False,
    strong: bool = False,
    intensity: float = 1.0,
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
            adaptive=adaptive,
            strong=strong,
            intensity=intensity,
        )
        if candidate.stat().st_size <= maximum_bytes:
            candidate.replace(destination)
            return destination
        candidate.unlink(missing_ok=True)
    raise WebmError("WEBM cannot be optimized under Telegram's size limit")
