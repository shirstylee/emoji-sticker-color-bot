from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from app.recolor.color_math import (
    oklab_to_srgb,
    parse_color,
    recolor_rgb,
    srgb_to_oklab,
)
from app.recolor.raster import recolor_image


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#FF00AA", "#FF00AA"),
        ("ff00aa", "#FF00AA"),
        ("#F0A", "#FF00AA"),
        ("f0a", "#FF00AA"),
        ("rgb(255, 0, 170)", "#FF00AA"),
        ("255, 0, 170", "#FF00AA"),
    ],
)
def test_color_parsing_and_normalization(value: str, expected: str) -> None:
    assert parse_color(value).hex == expected


@pytest.mark.parametrize(
    "value",
    ["", "#12", "#GG00AA", "256, 0, 1", "rgb(-1,0,0)", "1,2,3 trailing", "rgba(1,2,3,4)"],
)
def test_invalid_color_is_rejected_completely(value: str) -> None:
    with pytest.raises(ValueError):
        parse_color(value)


def test_oklab_round_trip() -> None:
    values = np.array([[[0.0, 0.0, 0.0], [1.0, 1.0, 1.0], [0.2, 0.5, 0.9]]])
    restored = oklab_to_srgb(srgb_to_oklab(values))
    np.testing.assert_allclose(restored, values, atol=2e-6)


def test_recolor_preserves_gradient_order() -> None:
    gray = np.array([[[20, 20, 20], [80, 80, 80], [150, 150, 150], [235, 235, 235]]], dtype=np.uint8)
    output = recolor_rgb(gray, parse_color("#8B5CF6"))
    lightness = srgb_to_oklab(output.astype(np.float64) / 255.0)[0, :, 0]
    assert np.all(np.diff(lightness) > 0.02)
    chroma = np.hypot(*np.moveaxis(srgb_to_oklab(output.astype(np.float64) / 255.0)[..., 1:3], -1, 0))
    assert float(chroma.max()) > 0.05


def test_saturated_target_keeps_white_highlight_visibly_colored() -> None:
    white = np.array([[[255, 255, 255]]], dtype=np.uint8)

    output = recolor_rgb(white, parse_color("#9C27B0"))
    lab = srgb_to_oklab(output.astype(np.float64) / 255.0)[0, 0]

    assert float(lab[0]) < 0.72
    assert float(np.hypot(lab[1], lab[2])) > 0.12


@pytest.mark.parametrize("target", ["#000000", "#FFFFFF"])
def test_achromatic_targets_keep_visible_contrast(target: str) -> None:
    gray = np.array([[[10, 10, 10], [60, 60, 60], [130, 130, 130], [245, 245, 245]]], dtype=np.uint8)
    output = recolor_rgb(gray, parse_color(target))
    lightness = srgb_to_oklab(output.astype(np.float64) / 255.0)[0, :, 0]
    assert np.all(np.diff(lightness) > 0.01)
    assert float(np.ptp(lightness)) > 0.20


def test_raster_alpha_is_bit_exact() -> None:
    rgba = np.array(
        [
            [[255, 0, 0, 0], [0, 255, 0, 1]],
            [[0, 0, 255, 127], [255, 255, 255, 255]],
        ],
        dtype=np.uint8,
    )
    image = Image.fromarray(rgba, "RGBA")
    output = np.asarray(recolor_image(image, parse_color("#FF9800")))
    np.testing.assert_array_equal(output[..., 3], rgba[..., 3])


def test_colored_recolor_removes_source_hue() -> None:
    source = np.array([[[255, 0, 0], [0, 255, 0], [0, 0, 255]]], dtype=np.uint8)
    output = recolor_rgb(source, parse_color("#2196F3"))
    lab = srgb_to_oklab(output.astype(np.float64) / 255.0)[0]
    hues = np.arctan2(lab[:, 2], lab[:, 1])
    assert float(np.ptp(hues)) < 0.02
