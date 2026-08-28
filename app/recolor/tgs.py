"""Safe Lottie-aware TGS recoloring that preserves unknown JSON fields."""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path
from typing import Any

import numpy as np

from app.recolor.color_math import (
    ParsedColor,
    palette_lightness_midpoint,
    recolor_normalized_color,
    srgb_to_oklab,
)


class TgsError(ValueError):
    """TGS data is unsafe, malformed, or outside Telegram requirements."""


def load_tgs(
    path: Path,
    *,
    max_decompressed: int = 5 * 1024 * 1024,
    strict_timing: bool = True,
) -> dict[str, Any]:
    try:
        with path.open("rb") as source, gzip.GzipFile(fileobj=source) as archive:
            payload = archive.read(max_decompressed + 1)
        if len(payload) > max_decompressed:
            raise TgsError("TGS decompressed JSON exceeds the configured limit")
        document = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TgsError("TGS is not valid gzip JSON") from error
    if not isinstance(document, dict):
        raise TgsError("TGS root must be an object")
    validate_tgs_document(document, strict_timing=strict_timing)
    return document


def validate_tgs_document(
    document: dict[str, Any], *, strict_timing: bool = True
) -> None:
    required = {"v", "fr", "ip", "op", "w", "h", "layers"}
    if not required.issubset(document):
        raise TgsError("TGS is missing required Lottie fields")
    if not isinstance(document["layers"], list):
        raise TgsError("TGS layers must be an array")
    try:
        frame_rate = float(document["fr"])
        duration = (float(document["op"]) - float(document["ip"])) / frame_rate
    except (TypeError, ValueError, ZeroDivisionError) as error:
        raise TgsError("TGS timing is invalid") from error
    if not np.isfinite(frame_rate) or not np.isfinite(duration) or frame_rate <= 0 or duration <= 0:
        raise TgsError("TGS timing is invalid")
    if strict_timing and (frame_rate != 60 or duration > 3.0 + 1e-6):
        raise TgsError("TGS timing exceeds Telegram requirements")
    if int(document["w"]) != 512 or int(document["h"]) != 512:
        raise TgsError("Telegram TGS canvas must be 512x512")


def normalize_tgs_timing(document: dict[str, Any]) -> dict[str, Any]:
    """Convert a structurally valid source animation to Telegram's 60 FPS/3 s timing."""

    validate_tgs_document(document, strict_timing=False)
    output = copy.deepcopy(document)
    frame_rate = float(output["fr"])
    first = float(output["ip"])
    last = float(output["op"])
    span = last - first
    scale = min(60.0 / frame_rate, 180.0 / span)

    def scale_frames(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"ip", "op", "st", "t"} and isinstance(child, (int, float)):
                    value[key] = float(child) * scale
                else:
                    scale_frames(child)
        elif isinstance(value, list):
            for child in value:
                scale_frames(child)

    scale_frames(output)
    output["fr"] = 60
    validate_tgs_document(output)
    return output


def _is_color(value: object) -> bool:
    return (
        isinstance(value, list)
        and 3 <= len(value) <= 4
        and all(isinstance(channel, (int, float)) for channel in value)
        and all(0.0 <= float(channel) <= 1.0 for channel in value)
    )


def _recolor_color_payload(value: Any, target: ParsedColor, midpoint: float) -> Any:
    if _is_color(value):
        return recolor_normalized_color(value, target, source_midpoint=midpoint)
    if isinstance(value, list):
        return [_recolor_color_payload(item, target, midpoint) for item in value]
    return value


def _recolor_property(prop: dict[str, Any], target: ParsedColor, midpoint: float) -> None:
    if "k" not in prop:
        return
    keyframes = prop["k"]
    if _is_color(keyframes):
        prop["k"] = recolor_normalized_color(
            keyframes, target, source_midpoint=midpoint
        )
        return
    if isinstance(keyframes, list):
        for frame in keyframes:
            if not isinstance(frame, dict):
                continue
            for name in ("s", "e"):
                if name in frame:
                    frame[name] = _recolor_color_payload(frame[name], target, midpoint)


def _recolor_gradient_array(
    values: list[Any], points: int, target: ParsedColor, midpoint: float
) -> list[Any]:
    result = list(values)
    color_length = min(len(result), points * 4)
    for start in range(0, color_length, 4):
        if start + 3 >= len(result):
            break
        channels = result[start + 1 : start + 4]
        if _is_color(channels):
            result[start + 1 : start + 4] = recolor_normalized_color(
                channels, target, source_midpoint=midpoint
            )[:3]
    return result


def _recolor_gradient_payload(
    value: Any, points: int, target: ParsedColor, midpoint: float
) -> Any:
    if isinstance(value, list) and value and all(isinstance(item, (int, float)) for item in value):
        return _recolor_gradient_array(value, points, target, midpoint)
    if isinstance(value, list):
        return [_recolor_gradient_payload(item, points, target, midpoint) for item in value]
    return value


def _recolor_gradient(
    gradient: dict[str, Any], target: ParsedColor, midpoint: float
) -> None:
    points = gradient.get("p")
    prop = gradient.get("k")
    if not isinstance(points, int) or points <= 0 or not isinstance(prop, dict):
        return
    keyframes = prop.get("k")
    if isinstance(keyframes, list) and keyframes and all(
        isinstance(item, (int, float)) for item in keyframes
    ):
        prop["k"] = _recolor_gradient_array(keyframes, points, target, midpoint)
    elif isinstance(keyframes, list):
        for frame in keyframes:
            if not isinstance(frame, dict):
                continue
            for name in ("s", "e"):
                if name in frame:
                    frame[name] = _recolor_gradient_payload(
                        frame[name], points, target, midpoint
                    )


def _collect_color_payload(value: Any, colors: list[list[float]]) -> None:
    if _is_color(value):
        colors.append([float(channel) for channel in value[:3]])
    elif isinstance(value, list):
        for item in value:
            _collect_color_payload(item, colors)


def _collect_property(prop: dict[str, Any], colors: list[list[float]]) -> None:
    if "k" not in prop:
        return
    keyframes = prop["k"]
    if _is_color(keyframes):
        colors.append([float(channel) for channel in keyframes[:3]])
    elif isinstance(keyframes, list):
        for frame in keyframes:
            if not isinstance(frame, dict):
                continue
            for name in ("s", "e"):
                if name in frame:
                    _collect_color_payload(frame[name], colors)


def _collect_gradient_array(values: list[Any], points: int, colors: list[list[float]]) -> None:
    color_length = min(len(values), points * 4)
    for start in range(0, color_length, 4):
        if start + 3 >= len(values):
            break
        channels = values[start + 1 : start + 4]
        if _is_color(channels):
            colors.append([float(channel) for channel in channels])


def _collect_gradient_payload(value: Any, points: int, colors: list[list[float]]) -> None:
    if isinstance(value, list) and value and all(isinstance(item, (int, float)) for item in value):
        _collect_gradient_array(value, points, colors)
    elif isinstance(value, list):
        for item in value:
            _collect_gradient_payload(item, points, colors)


def _collect_gradient(gradient: dict[str, Any], colors: list[list[float]]) -> None:
    points = gradient.get("p")
    prop = gradient.get("k")
    if not isinstance(points, int) or points <= 0 or not isinstance(prop, dict):
        return
    keyframes = prop.get("k")
    if isinstance(keyframes, list) and keyframes and all(
        isinstance(item, (int, float)) for item in keyframes
    ):
        _collect_gradient_array(keyframes, points, colors)
    elif isinstance(keyframes, list):
        for frame in keyframes:
            if not isinstance(frame, dict):
                continue
            for name in ("s", "e"):
                if name in frame:
                    _collect_gradient_payload(frame[name], points, colors)


def _collect_walk(value: Any, colors: list[list[float]]) -> None:
    if isinstance(value, dict):
        color = value.get("c")
        if isinstance(color, dict):
            _collect_property(color, colors)
        gradient = value.get("g")
        if isinstance(gradient, dict):
            _collect_gradient(gradient, colors)
        for child in value.values():
            _collect_walk(child, colors)
    elif isinstance(value, list):
        for child in value:
            _collect_walk(child, colors)


def _walk(value: Any, target: ParsedColor, midpoint: float) -> None:
    if isinstance(value, dict):
        color = value.get("c")
        if isinstance(color, dict):
            _recolor_property(color, target, midpoint)
        gradient = value.get("g")
        if isinstance(gradient, dict):
            _recolor_gradient(gradient, target, midpoint)
        for child in value.values():
            _walk(child, target, midpoint)
    elif isinstance(value, list):
        for child in value:
            _walk(child, target, midpoint)


def _transform_color_payload(value: Any, transform: Any) -> Any:
    if _is_color(value):
        return transform(value)
    if isinstance(value, list):
        return [_transform_color_payload(item, transform) for item in value]
    return value


def _transform_property(prop: dict[str, Any], transform: Any) -> None:
    if "k" not in prop:
        return
    keyframes = prop["k"]
    if _is_color(keyframes):
        prop["k"] = transform(keyframes)
    elif isinstance(keyframes, list):
        for frame in keyframes:
            if not isinstance(frame, dict):
                continue
            for name in ("s", "e"):
                if name in frame:
                    frame[name] = _transform_color_payload(frame[name], transform)


def _transform_gradient(gradient: dict[str, Any], transform: Any) -> None:
    points = gradient.get("p")
    prop = gradient.get("k")
    if not isinstance(points, int) or points <= 0 or not isinstance(prop, dict):
        return

    def transform_array(values: list[Any]) -> list[Any]:
        result = list(values)
        color_length = min(len(result), points * 4)
        for start in range(0, color_length, 4):
            if start + 3 >= len(result):
                break
            channels = result[start + 1 : start + 4]
            if _is_color(channels):
                result[start + 1 : start + 4] = transform(channels)[:3]
        return result

    keyframes = prop.get("k")
    if isinstance(keyframes, list) and keyframes and all(
        isinstance(item, (int, float)) for item in keyframes
    ):
        prop["k"] = transform_array(keyframes)
    elif isinstance(keyframes, list):
        for frame in keyframes:
            if not isinstance(frame, dict):
                continue
            for name in ("s", "e"):
                payload = frame.get(name)
                if isinstance(payload, list) and payload and isinstance(payload[0], list):
                    frame[name] = [transform_array(item) for item in payload]
                elif isinstance(payload, list):
                    frame[name] = transform_array(payload)


def _transform_walk(value: Any, transform: Any) -> None:
    if isinstance(value, dict):
        color = value.get("c")
        if isinstance(color, dict):
            _transform_property(color, transform)
        gradient = value.get("g")
        if isinstance(gradient, dict):
            _transform_gradient(gradient, transform)
        for child in value.values():
            _transform_walk(child, transform)
    elif isinstance(value, list):
        for child in value:
            _transform_walk(child, transform)


def strong_tint_tgs_document(
    document: dict[str, Any], target: ParsedColor
) -> dict[str, Any]:
    output = copy.deepcopy(document)
    rgb = [channel / 255.0 for channel in target.rgb]

    def transform(color: list[float]) -> list[float]:
        return [*rgb, *list(color[3:])]

    _transform_walk(output, transform)
    return output


def adaptive_tgs_document(document: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(document)
    colors: list[list[float]] = []
    _collect_walk(output, colors)
    if not colors:
        return output
    lightness = srgb_to_oklab(np.asarray(colors, dtype=np.float64))[..., 0]
    low, midpoint, high = np.quantile(lightness, (0.02, 0.50, 0.98))
    spread = float(high - low)

    def transform(color: list[float]) -> list[float]:
        alpha = float(color[3]) if len(color) > 3 else 1.0
        if spread >= 0.06:
            current = float(
                srgb_to_oklab(np.asarray(color[:3], dtype=np.float64).reshape(1, 3))[0, 0]
            )
            denominator = (
                max(float(midpoint - low), 0.04)
                if current <= midpoint
                else max(float(high - midpoint), 0.04)
            )
            distance = abs(current - float(midpoint)) / denominator
            detail = float(np.clip((distance - 0.08) / 0.92, 0.0, 1.0))
            alpha *= 1.0 - detail * detail * (3.0 - 2.0 * detail)
        return [1.0, 1.0, 1.0, float(np.clip(alpha, 0.0, 1.0))]

    _transform_walk(output, transform)
    return output


def recolor_tgs_document(document: dict[str, Any], target: ParsedColor) -> dict[str, Any]:
    output = copy.deepcopy(document)
    colors: list[list[float]] = []
    _collect_walk(output, colors)
    midpoint = palette_lightness_midpoint(colors)
    _walk(output, target, midpoint)
    return output


def save_tgs(document: dict[str, Any], destination: Path) -> Path:
    validate_tgs_document(document)
    payload = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        destination.open("wb") as target,
        gzip.GzipFile(fileobj=target, mode="wb", compresslevel=9, mtime=0) as archive,
    ):
        archive.write(payload)
    return destination


def recolor_tgs_file(
    source: Path,
    destination: Path,
    target: ParsedColor,
    *,
    max_decompressed: int,
    adaptive: bool = False,
    strong: bool = False,
) -> Path:
    document = load_tgs(
        source,
        max_decompressed=max_decompressed,
        strict_timing=False,
    )
    normalized = normalize_tgs_timing(document)
    if adaptive:
        result = adaptive_tgs_document(normalized)
    elif strong:
        result = strong_tint_tgs_document(normalized, target)
    else:
        result = recolor_tgs_document(normalized, target)
    return save_tgs(result, destination)
