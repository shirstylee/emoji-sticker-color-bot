"""Safe Lottie-aware TGS recoloring that preserves unknown JSON fields."""

from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path
from typing import Any

from app.recolor.color_math import ParsedColor, recolor_normalized_color


class TgsError(ValueError):
    """TGS data is unsafe, malformed, or outside Telegram requirements."""


def load_tgs(path: Path, *, max_decompressed: int = 5 * 1024 * 1024) -> dict[str, Any]:
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
    validate_tgs_document(document)
    return document


def validate_tgs_document(document: dict[str, Any]) -> None:
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
    if frame_rate <= 0 or frame_rate > 60 or duration <= 0 or duration > 3.01:
        raise TgsError("TGS timing exceeds Telegram requirements")
    if int(document["w"]) != 512 or int(document["h"]) != 512:
        raise TgsError("Telegram TGS canvas must be 512x512")


def _is_color(value: object) -> bool:
    return (
        isinstance(value, list)
        and 3 <= len(value) <= 4
        and all(isinstance(channel, (int, float)) for channel in value)
        and all(0.0 <= float(channel) <= 1.0 for channel in value)
    )


def _recolor_color_payload(value: Any, target: ParsedColor) -> Any:
    if _is_color(value):
        return recolor_normalized_color(value, target)
    if isinstance(value, list):
        return [_recolor_color_payload(item, target) for item in value]
    return value


def _recolor_property(prop: dict[str, Any], target: ParsedColor) -> None:
    if "k" not in prop:
        return
    keyframes = prop["k"]
    if _is_color(keyframes):
        prop["k"] = recolor_normalized_color(keyframes, target)
        return
    if isinstance(keyframes, list):
        for frame in keyframes:
            if not isinstance(frame, dict):
                continue
            for name in ("s", "e"):
                if name in frame:
                    frame[name] = _recolor_color_payload(frame[name], target)


def _recolor_gradient_array(values: list[Any], points: int, target: ParsedColor) -> list[Any]:
    result = list(values)
    color_length = min(len(result), points * 4)
    for start in range(0, color_length, 4):
        if start + 3 >= len(result):
            break
        channels = result[start + 1 : start + 4]
        if _is_color(channels):
            result[start + 1 : start + 4] = recolor_normalized_color(channels, target)[:3]
    return result


def _recolor_gradient_payload(value: Any, points: int, target: ParsedColor) -> Any:
    if isinstance(value, list) and value and all(isinstance(item, (int, float)) for item in value):
        return _recolor_gradient_array(value, points, target)
    if isinstance(value, list):
        return [_recolor_gradient_payload(item, points, target) for item in value]
    return value


def _recolor_gradient(gradient: dict[str, Any], target: ParsedColor) -> None:
    points = gradient.get("p")
    prop = gradient.get("k")
    if not isinstance(points, int) or points <= 0 or not isinstance(prop, dict):
        return
    keyframes = prop.get("k")
    if isinstance(keyframes, list) and keyframes and all(
        isinstance(item, (int, float)) for item in keyframes
    ):
        prop["k"] = _recolor_gradient_array(keyframes, points, target)
    elif isinstance(keyframes, list):
        for frame in keyframes:
            if not isinstance(frame, dict):
                continue
            for name in ("s", "e"):
                if name in frame:
                    frame[name] = _recolor_gradient_payload(frame[name], points, target)


def _walk(value: Any, target: ParsedColor) -> None:
    if isinstance(value, dict):
        color = value.get("c")
        if isinstance(color, dict):
            _recolor_property(color, target)
        gradient = value.get("g")
        if isinstance(gradient, dict):
            _recolor_gradient(gradient, target)
        for child in value.values():
            _walk(child, target)
    elif isinstance(value, list):
        for child in value:
            _walk(child, target)


def recolor_tgs_document(document: dict[str, Any], target: ParsedColor) -> dict[str, Any]:
    output = copy.deepcopy(document)
    _walk(output, target)
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
    source: Path, destination: Path, target: ParsedColor, *, max_decompressed: int
) -> Path:
    return save_tgs(recolor_tgs_document(load_tgs(source, max_decompressed=max_decompressed), target), destination)
