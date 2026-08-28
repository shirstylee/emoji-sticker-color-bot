"""Vectorized sRGB ↔ OKLab conversion and perceptual monochrome tinting."""

from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

HEX_RE = re.compile(r"#?(?P<hex>[0-9a-fA-F]{6}|[0-9a-fA-F]{3})")
RGB_RE = re.compile(
    r"(?:rgb\(\s*)?(?P<r>\d{1,3})\s*,\s*(?P<g>\d{1,3})\s*,\s*(?P<b>\d{1,3})(?:\s*\))?",
    re.IGNORECASE,
)

FloatArray = NDArray[np.float64]

M1 = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ],
    dtype=np.float64,
)
M2 = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ],
    dtype=np.float64,
)
M1_INV = np.array(
    [
        [4.0767416621, -3.3077115913, 0.2309699292],
        [-1.2684380046, 2.6097574011, -0.3413193965],
        [-0.0041960863, -0.7034186147, 1.7076147010],
    ],
    dtype=np.float64,
)
M2_INV = np.array(
    [
        [1.0, 0.3963377774, 0.2158037573],
        [1.0, -0.1055613458, -0.0638541728],
        [1.0, -0.0894841775, -1.2914855480],
    ],
    dtype=np.float64,
)


@dataclass(frozen=True, slots=True)
class ParsedColor:
    red: int
    green: int
    blue: int

    @property
    def hex(self) -> str:
        return f"#{self.red:02X}{self.green:02X}{self.blue:02X}"

    @property
    def rgb(self) -> tuple[int, int, int]:
        return self.red, self.green, self.blue


def parse_color(value: str) -> ParsedColor:
    stripped = value.strip()
    hex_match = HEX_RE.fullmatch(stripped)
    if hex_match:
        digits = hex_match.group("hex")
        if len(digits) == 3:
            digits = "".join(char * 2 for char in digits)
        return ParsedColor(*(int(digits[index : index + 2], 16) for index in (0, 2, 4)))
    rgb_match = RGB_RE.fullmatch(stripped)
    if not rgb_match:
        raise ValueError("Invalid HEX/RGB color")
    channels = tuple(int(rgb_match.group(name)) for name in ("r", "g", "b"))
    if any(channel > 255 for channel in channels):
        raise ValueError("RGB channels must be between 0 and 255")
    return ParsedColor(*channels)


def srgb_to_linear(rgb: FloatArray) -> FloatArray:
    rgb = np.asarray(rgb, dtype=np.float64)
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(rgb: FloatArray) -> FloatArray:
    rgb = np.asarray(rgb, dtype=np.float64)
    safe = np.maximum(rgb, 0.0)
    return np.where(safe <= 0.0031308, 12.92 * safe, 1.055 * safe ** (1 / 2.4) - 0.055)


def linear_rgb_to_oklab(rgb: FloatArray) -> FloatArray:
    lms = np.matmul(rgb, M1.T)
    return np.asarray(np.matmul(np.cbrt(lms), M2.T), dtype=np.float64)


def oklab_to_linear_rgb(lab: FloatArray) -> FloatArray:
    lms_root = np.matmul(lab, M2_INV.T)
    return np.asarray(np.matmul(lms_root**3, M1_INV.T), dtype=np.float64)


def srgb_to_oklab(rgb: FloatArray) -> FloatArray:
    return linear_rgb_to_oklab(srgb_to_linear(rgb))


def oklab_to_srgb(lab: FloatArray) -> FloatArray:
    return linear_to_srgb(oklab_to_linear_rgb(lab))


def _map_lightness(source_l: FloatArray, midpoint: float, target_l: float) -> FloatArray:
    if target_l < 0.04:
        lower = 0.11 - (midpoint - source_l) / max(midpoint, 1e-6) * 0.095
        upper = 0.11 + (source_l - midpoint) / max(1.0 - midpoint, 1e-6) * 0.36
        return np.clip(np.where(source_l <= midpoint, lower, upper), 0.015, 0.47)
    if target_l > 0.96:
        lower = 0.91 - (midpoint - source_l) / max(midpoint, 1e-6) * 0.36
        upper = 0.91 + (source_l - midpoint) / max(1.0 - midpoint, 1e-6) * 0.075
        return np.clip(np.where(source_l <= midpoint, lower, upper), 0.55, 0.985)
    lower_scale = target_l / max(midpoint, 1e-6)
    upper_scale = (1.0 - target_l) / max(1.0 - midpoint, 1e-6)
    mapped = np.where(
        source_l <= midpoint,
        target_l - (midpoint - source_l) * lower_scale * 0.86,
        target_l + (source_l - midpoint) * upper_scale * 0.86,
    )
    return np.clip(mapped, 0.015, 0.99)


def gamut_map_oklab(lab: FloatArray, iterations: int = 10) -> FloatArray:
    """Reduce chroma in OKLab until every pixel is inside linear-sRGB gamut."""

    result = np.asarray(lab, dtype=np.float64).copy()
    original_ab = result[..., 1:3].copy()
    low = np.zeros(result.shape[:-1], dtype=np.float64)
    high = np.ones(result.shape[:-1], dtype=np.float64)
    rgb = oklab_to_linear_rgb(result)
    in_gamut = np.all((rgb >= -1e-7) & (rgb <= 1.0000001), axis=-1)
    low[in_gamut] = 1.0
    for _ in range(iterations):
        mid = (low + high) / 2.0
        candidate = result.copy()
        candidate[..., 1:3] = original_ab * mid[..., None]
        rgb = oklab_to_linear_rgb(candidate)
        valid = np.all((rgb >= 0.0) & (rgb <= 1.0), axis=-1)
        low = np.where(valid, mid, low)
        high = np.where(valid, high, mid)
    result[..., 1:3] = original_ab * low[..., None]
    return result


def palette_lightness_midpoint(
    colors: list[list[float]] | list[tuple[float, ...]],
) -> float:
    """Return one stable OKLab lightness midpoint for a vector/TGS color palette."""

    if not colors:
        return 0.5
    normalized = np.asarray([color[:3] for color in colors], dtype=np.float64)
    if normalized.max(initial=0.0) > 1.0:
        normalized /= 255.0
    lightness = srgb_to_oklab(np.clip(normalized, 0.0, 1.0))[..., 0]
    return float(np.clip(np.median(lightness), 0.08, 0.92))


def recolor_rgb(
    rgb: NDArray[np.uint8] | FloatArray,
    target: ParsedColor | tuple[int, int, int],
    *,
    weights: FloatArray | None = None,
    source_midpoint: float | None = None,
) -> NDArray[np.uint8]:
    """Remove source hue while retaining perceptual lightness and local contrast."""

    source = np.asarray(rgb)
    normalized = source.astype(np.float64)
    if normalized.size == 0:
        return normalized.astype(np.uint8)
    if normalized.max(initial=0.0) > 1.0:
        normalized /= 255.0
    source_lab = srgb_to_oklab(np.clip(normalized, 0.0, 1.0))
    source_l = source_lab[..., 0]
    if source_midpoint is None:
        visible = source_l.reshape(-1)
        if weights is not None:
            flat_weights = np.asarray(weights, dtype=np.float64).reshape(-1)
            visible = visible[flat_weights > 0.01]
        midpoint = float(np.median(visible)) if visible.size else 0.5
        midpoint = float(np.clip(midpoint, 0.08, 0.92))
    else:
        midpoint = float(np.clip(source_midpoint, 0.08, 0.92))

    target_rgb = target.rgb if isinstance(target, ParsedColor) else target
    target_normalized = np.array(target_rgb, dtype=np.float64) / 255.0
    target_lab = srgb_to_oklab(target_normalized)
    target_l = float(target_lab[0])
    target_chroma = float(np.hypot(target_lab[1], target_lab[2]))
    mapped_l = _map_lightness(source_l, midpoint, target_l)

    output_lab = np.zeros_like(source_lab)
    output_lab[..., 0] = mapped_l
    if target_chroma >= 0.012:
        direction = target_lab[1:3] / target_chroma
        # Chroma naturally tapers near black and white, preserving clean highlights/outlines.
        lightness_taper = np.clip(np.sin(np.pi * mapped_l), 0.0, 1.0) ** 0.7
        chroma = target_chroma * lightness_taper
        output_lab[..., 1:3] = chroma[..., None] * direction
    output_lab = gamut_map_oklab(output_lab)
    recolored = np.clip(oklab_to_srgb(output_lab), 0.0, 1.0)
    return np.rint(recolored * 255.0).astype(np.uint8)


def recolor_normalized_color(
    color: list[float] | tuple[float, ...],
    target: ParsedColor,
    *,
    source_midpoint: float | None = None,
) -> list[float]:
    if len(color) < 3:
        return list(color)
    source = np.array(color[:3], dtype=np.float64).reshape(1, 1, 3)
    recolored = (
        recolor_rgb(source, target, source_midpoint=source_midpoint)
        .reshape(3)
        .astype(np.float64)
        / 255.0
    )
    return [*recolored.tolist(), *list(color[3:])]
