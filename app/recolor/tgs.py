"""Safe Lottie-aware TGS recoloring that preserves unknown JSON fields."""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path
from typing import Any, cast

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

    # Files downloaded from Telegram already satisfy these constraints. Keep
    # every original number and keyframe byte-for-byte at the JSON value level:
    # rewriting integer frame times as floats makes complex TGS documents fail
    # Telegram's stricter server-side sticker validator.
    if frame_rate == 60.0 and span <= 180.0 + 1e-6:
        output["tgs"] = 1
        validate_tgs_document(output)
        return output

    scale = min(60.0 / frame_rate, 180.0 / span)

    def scaled_frame(value: int | float) -> int | float:
        scaled = float(value) * scale
        rounded = round(scaled)
        if abs(scaled - rounded) <= 1e-9:
            return int(rounded)
        return scaled

    def scale_frames(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"ip", "op", "st", "t", "tm", "dr"} and isinstance(
                    child, (int, float)
                ):
                    value[key] = scaled_frame(child)
                else:
                    scale_frames(child)
        elif isinstance(value, list):
            for child in value:
                scale_frames(child)

    scale_frames(output)
    output["fr"] = 60
    # Telegram identifies animated sticker payloads by this format marker.
    # Some exported Lottie files omit it even though their remaining structure
    # is valid, which makes Bot API uploads fail with ``wrong file type``.
    output["tgs"] = 1
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


def _slot_references(value: Any) -> tuple[set[str], dict[str, int]]:
    color_slots: set[str] = set()
    gradient_slots: dict[str, int] = {}

    def walk(child: Any) -> None:
        if isinstance(child, dict):
            color = child.get("c")
            if isinstance(color, dict) and isinstance(color.get("sid"), str):
                color_slots.add(color["sid"])
            gradient = child.get("g")
            if isinstance(gradient, dict):
                points = gradient.get("p")
                prop = gradient.get("k")
                if (
                    isinstance(points, int)
                    and points > 0
                    and isinstance(prop, dict)
                    and isinstance(prop.get("sid"), str)
                ):
                    gradient_slots[prop["sid"]] = points
            for nested in child.values():
                walk(nested)
        elif isinstance(child, list):
            for nested in child:
                walk(nested)

    walk(value)
    return color_slots, gradient_slots


def _slot_property(document: dict[str, Any], slot_id: str) -> dict[str, Any] | None:
    slots = document.get("slots")
    if not isinstance(slots, dict):
        return None
    slot = slots.get(slot_id)
    if not isinstance(slot, dict):
        return None
    prop = slot.get("p")
    return prop if isinstance(prop, dict) else None


def _collect_slot_colors(document: dict[str, Any], colors: list[list[float]]) -> None:
    color_slots, gradient_slots = _slot_references(document)
    for slot_id in color_slots:
        prop = _slot_property(document, slot_id)
        if prop is not None:
            _collect_property(prop, colors)
    for slot_id, points in gradient_slots.items():
        prop = _slot_property(document, slot_id)
        if prop is not None:
            _collect_gradient({"p": points, "k": prop}, colors)


def _recolor_slots(document: dict[str, Any], target: ParsedColor, midpoint: float) -> None:
    color_slots, gradient_slots = _slot_references(document)
    for slot_id in color_slots:
        prop = _slot_property(document, slot_id)
        if prop is not None:
            _recolor_property(prop, target, midpoint)
    for slot_id, points in gradient_slots.items():
        prop = _slot_property(document, slot_id)
        if prop is not None:
            _recolor_gradient({"p": points, "k": prop}, target, midpoint)


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


def _transform_walk(
    value: Any, transform: Any, *, radial_gradient_transform: Any | None = None
) -> None:
    if isinstance(value, dict):
        color = value.get("c")
        if isinstance(color, dict):
            _transform_property(color, transform)
        gradient = value.get("g")
        if isinstance(gradient, dict):
            gradient_transform = (
                radial_gradient_transform(gradient)
                if value.get("t") == 2 and radial_gradient_transform is not None
                else transform
            )
            _transform_gradient(gradient, gradient_transform)
        for child in value.values():
            _transform_walk(
                child,
                transform,
                radial_gradient_transform=radial_gradient_transform,
            )
    elif isinstance(value, list):
        for child in value:
            _transform_walk(
                child,
                transform,
                radial_gradient_transform=radial_gradient_transform,
            )


def _radial_gradient_slot_ids(value: Any) -> set[str]:
    result: set[str] = set()

    def walk(child: Any) -> None:
        if isinstance(child, dict):
            gradient = child.get("g")
            if child.get("t") == 2 and isinstance(gradient, dict):
                prop = gradient.get("k")
                if isinstance(prop, dict) and isinstance(prop.get("sid"), str):
                    result.add(prop["sid"])
            for nested in child.values():
                walk(nested)
        elif isinstance(child, list):
            for nested in child:
                walk(nested)

    walk(value)
    return result


def _transform_slots(
    document: dict[str, Any],
    transform: Any,
    *,
    radial_gradient_transform: Any | None = None,
) -> None:
    color_slots, gradient_slots = _slot_references(document)
    radial_slots = (
        _radial_gradient_slot_ids(document)
        if radial_gradient_transform is not None
        else set()
    )
    for slot_id in color_slots:
        prop = _slot_property(document, slot_id)
        if prop is not None:
            _transform_property(prop, transform)
    for slot_id, points in gradient_slots.items():
        prop = _slot_property(document, slot_id)
        if prop is not None:
            gradient = {"p": points, "k": prop}
            gradient_transform = (
                radial_gradient_transform(gradient)
                if slot_id in radial_slots and radial_gradient_transform is not None
                else transform
            )
            _transform_gradient(gradient, gradient_transform)


def strong_tint_tgs_document(
    document: dict[str, Any], target: ParsedColor, *, strength: float = 1.0
) -> dict[str, Any]:
    output = copy.deepcopy(document)
    colors: list[list[float]] = []
    _collect_walk(output, colors)
    _collect_slot_colors(output, colors)
    midpoint = palette_lightness_midpoint(colors)

    def transform(color: list[float]) -> list[float]:
        return recolor_normalized_color(
            color,
            target,
            source_midpoint=midpoint,
            chroma_scale=1.35,
            contrast_scale=0.62,
            strength=strength,
        )

    _transform_walk(output, transform)
    _transform_slots(output, transform)
    return output


def _adaptive_density(
    color: list[float], low: float, midpoint: float, high: float
) -> float:
    if high - low < 0.06:
        return 1.0
    current = float(
        srgb_to_oklab(np.asarray(color[:3], dtype=np.float64).reshape(1, 3))[0, 0]
    )
    if current <= midpoint:
        distance = float(np.clip((midpoint - current) / max(midpoint - low, 0.04), 0.0, 1.0))
        smooth = distance * distance * (3.0 - 2.0 * distance)
        return 0.82 + 0.18 * smooth
    distance = float(np.clip((current - midpoint) / max(high - midpoint, 0.04), 0.0, 1.0))
    smooth = distance * distance * (3.0 - 2.0 * distance)
    return 0.06 + 0.76 * (1.0 - smooth)


def _adaptive_gradient_array(
    values: list[Any], points: int, low: float, midpoint: float, high: float
) -> list[Any]:
    """Turn a Lottie gradient into a white mask with per-stop opacity.

    Gradient colors do not have sibling opacity properties like regular fills
    and strokes. Lottie stores optional opacity stops after the color stops in
    the same array, so preserving contour depth requires writing the source
    lightness into that opacity tail.
    """

    color_length = points * 4
    if len(values) < color_length:
        return list(values)
    color_values = list(values[:color_length])
    opacity_values = values[color_length:]
    opacity_stops: list[tuple[float, float]] = []
    if len(opacity_values) % 2 == 0:
        for start in range(0, len(opacity_values), 2):
            position, opacity = opacity_values[start : start + 2]
            if isinstance(position, (int, float)) and isinstance(
                opacity, (int, float)
            ):
                opacity_stops.append(
                    (
                        float(position),
                        float(np.clip(float(opacity), 0.0, 1.0)),
                    )
                )
    opacity_stops.sort(key=lambda stop: stop[0])

    def source_opacity(position: float) -> float:
        if not opacity_stops:
            return 1.0
        positions = [stop[0] for stop in opacity_stops]
        opacities = [stop[1] for stop in opacity_stops]
        return float(np.interp(position, positions, opacities))

    mask_opacity: list[float] = []
    for start in range(0, color_length, 4):
        position = color_values[start]
        channels = color_values[start + 1 : start + 4]
        if not isinstance(position, (int, float)) or not _is_color(channels):
            return list(values)
        numeric_color = [float(channel) for channel in channels]
        color_values[start + 1 : start + 4] = [1.0, 1.0, 1.0]
        mask_opacity.extend(
            [
                float(position),
                source_opacity(float(position))
                * _adaptive_density(numeric_color, low, midpoint, high),
            ]
        )
    return [*color_values, *mask_opacity]


def _adaptive_gradient_payload(
    value: Any,
    points: int,
    low: float,
    midpoint: float,
    high: float,
) -> Any:
    if isinstance(value, list) and value and all(
        isinstance(item, (int, float)) for item in value
    ):
        return _adaptive_gradient_array(value, points, low, midpoint, high)
    if isinstance(value, list):
        return [
            _adaptive_gradient_payload(item, points, low, midpoint, high)
            for item in value
        ]
    return value


def _adaptive_gradient(
    gradient: dict[str, Any], low: float, midpoint: float, high: float
) -> None:
    points = gradient.get("p")
    prop = gradient.get("k")
    if not isinstance(points, int) or points <= 0 or not isinstance(prop, dict):
        return
    keyframes = prop.get("k")
    if isinstance(keyframes, list) and keyframes and all(
        isinstance(item, (int, float)) for item in keyframes
    ):
        prop["k"] = _adaptive_gradient_array(
            keyframes, points, low, midpoint, high
        )
    elif isinstance(keyframes, list):
        for frame in keyframes:
            if not isinstance(frame, dict):
                continue
            for name in ("s", "e"):
                if name in frame:
                    frame[name] = _adaptive_gradient_payload(
                        frame[name], points, low, midpoint, high
                    )


def _apply_adaptive_gradients(
    value: Any, low: float, midpoint: float, high: float
) -> None:
    if isinstance(value, dict):
        gradient = value.get("g")
        if isinstance(gradient, dict):
            _adaptive_gradient(gradient, low, midpoint, high)
        for child in value.values():
            _apply_adaptive_gradients(child, low, midpoint, high)
    elif isinstance(value, list):
        for child in value:
            _apply_adaptive_gradients(child, low, midpoint, high)


def _apply_adaptive_slot_gradients(
    document: dict[str, Any], low: float, midpoint: float, high: float
) -> None:
    _, gradient_slots = _slot_references(document)
    for slot_id, points in gradient_slots.items():
        prop = _slot_property(document, slot_id)
        if prop is not None:
            _adaptive_gradient(
                {"p": points, "k": prop}, low, midpoint, high
            )


def _scale_opacity_payload(value: Any, factor: float) -> Any:
    if isinstance(value, (int, float)):
        return float(np.clip(float(value) * factor, 0.0, 100.0))
    if isinstance(value, list):
        return [_scale_opacity_payload(item, factor) for item in value]
    return value


def _scale_opacity_property(prop: dict[str, Any], factor: float) -> None:
    keyframes = prop.get("k")
    if isinstance(keyframes, (int, float)):
        prop["k"] = _scale_opacity_payload(keyframes, factor)
    elif isinstance(keyframes, list):
        for frame in keyframes:
            if not isinstance(frame, dict):
                continue
            for name in ("s", "e"):
                if name in frame:
                    frame[name] = _scale_opacity_payload(frame[name], factor)


def _first_color(value: Any) -> list[float] | None:
    if _is_color(value):
        return [float(channel) for channel in value]
    if isinstance(value, list):
        for item in value:
            color = _first_color(item)
            if color is not None:
                return color
    return None


def _animated_adaptive_opacity(
    color_prop: dict[str, Any],
    *,
    base_opacity: float,
    low: float,
    midpoint: float,
    high: float,
) -> dict[str, Any] | None:
    keyframes = color_prop.get("k")
    if not isinstance(keyframes, list) or _is_color(keyframes):
        return None
    output: list[dict[str, Any]] = []
    found_color = False
    for frame in keyframes:
        if not isinstance(frame, dict):
            continue
        opacity_frame = {
            name: copy.deepcopy(frame[name])
            for name in ("t", "h")
            if name in frame
        }
        for name in ("i", "o"):
            easing = frame.get(name)
            if not isinstance(easing, dict):
                continue
            scalar_easing: dict[str, list[float]] = {}
            for axis in ("x", "y"):
                values = easing.get(axis)
                if isinstance(values, (int, float)):
                    scalar_easing[axis] = [float(values)]
                elif isinstance(values, list) and values and isinstance(
                    values[0], (int, float)
                ):
                    scalar_easing[axis] = [float(values[0])]
            if scalar_easing:
                opacity_frame[name] = scalar_easing
        for name in ("s", "e"):
            color = _first_color(frame.get(name))
            if color is None:
                continue
            found_color = True
            opacity_frame[name] = [
                100.0
                * base_opacity
                * _adaptive_density(color, low, midpoint, high)
            ]
        output.append(opacity_frame)
    if not found_color or not output:
        return None
    return {"a": 1, "k": output}


def _apply_adaptive_shape_opacity(
    value: Any, low: float, midpoint: float, high: float
) -> None:
    if isinstance(value, dict):
        if value.get("ty") in {"fl", "st"}:
            color_prop = value.get("c")
            opacity_prop = value.get("o")
            if isinstance(color_prop, dict):
                static_color = color_prop.get("k")
                if _is_color(static_color):
                    factor = _adaptive_density(
                        cast(list[float], static_color), low, midpoint, high
                    )
                    if isinstance(opacity_prop, dict):
                        _scale_opacity_property(opacity_prop, factor)
                    else:
                        value["o"] = {"a": 0, "k": 100.0 * factor}
                elif not isinstance(opacity_prop, dict) or isinstance(
                    opacity_prop.get("k"), (int, float)
                ):
                    base = (
                        float(opacity_prop["k"]) / 100.0
                        if isinstance(opacity_prop, dict)
                        and isinstance(opacity_prop.get("k"), (int, float))
                        else 1.0
                    )
                    animated = _animated_adaptive_opacity(
                        color_prop,
                        base_opacity=base,
                        low=low,
                        midpoint=midpoint,
                        high=high,
                    )
                    if animated is not None:
                        value["o"] = animated
        for child in value.values():
            _apply_adaptive_shape_opacity(child, low, midpoint, high)
    elif isinstance(value, list):
        for child in value:
            _apply_adaptive_shape_opacity(child, low, midpoint, high)


def adaptive_tgs_document(document: dict[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(document)
    colors: list[list[float]] = []
    _collect_walk(output, colors)
    _collect_slot_colors(output, colors)
    if not colors:
        return output
    lightness = srgb_to_oklab(np.asarray(colors, dtype=np.float64))[..., 0]
    low, midpoint, high = (
        float(value) for value in np.quantile(lightness, (0.01, 0.50, 0.99))
    )
    _apply_adaptive_shape_opacity(output, low, midpoint, high)
    _apply_adaptive_gradients(output, low, midpoint, high)
    _apply_adaptive_slot_gradients(output, low, midpoint, high)

    def transform(color: list[float]) -> list[float]:
        # Preserve the original channel count. Adding a synthetic fourth color
        # channel makes some otherwise valid Telegram TGS documents fail format
        # validation; Lottie fill/stroke opacity lives in the sibling ``o``
        # property and is adjusted above.
        return [1.0, 1.0, 1.0, *list(color[3:])]

    _transform_walk(output, transform)
    _transform_slots(output, transform)
    return output


def recolor_tgs_document(
    document: dict[str, Any], target: ParsedColor, *, strength: float = 1.0
) -> dict[str, Any]:
    output = copy.deepcopy(document)
    colors: list[list[float]] = []
    _collect_walk(output, colors)
    _collect_slot_colors(output, colors)
    midpoint = palette_lightness_midpoint(colors)
    if strength == 1.0:
        _walk(output, target, midpoint)
        _recolor_slots(output, target, midpoint)
    else:
        def transform(color: list[float]) -> list[float]:
            return recolor_normalized_color(
                color,
                target,
                source_midpoint=midpoint,
                strength=strength,
            )

        def radial_transform(gradient: dict[str, Any]) -> Any:
            # A document-wide midpoint flattens small radial gradients. Use the
            # gradient's own palette so its dark body stays deep while its top
            # stop remains a visible specular highlight.
            gradient_colors: list[list[float]] = []
            _collect_gradient(gradient, gradient_colors)
            local_midpoint = (
                palette_lightness_midpoint(gradient_colors)
                if gradient_colors
                else midpoint
            )
            radial_midpoint = float(
                np.clip(
                    local_midpoint + max(0.0, strength - 1.0) * 0.20,
                    0.08,
                    0.92,
                )
            )

            def transform_color(color: list[float]) -> list[float]:
                return recolor_normalized_color(
                    color,
                    target,
                    source_midpoint=radial_midpoint,
                    contrast_scale=1.15,
                    strength=strength,
                )

            return transform_color

        _transform_walk(
            output,
            transform,
            radial_gradient_transform=radial_transform,
        )
        _transform_slots(
            output,
            transform,
            radial_gradient_transform=radial_transform,
        )
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
    intensity: float = 1.0,
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
        result = strong_tint_tgs_document(normalized, target, strength=intensity)
    else:
        result = recolor_tgs_document(normalized, target, strength=intensity)
    return save_tgs(result, destination)
