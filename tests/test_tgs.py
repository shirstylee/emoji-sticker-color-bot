from __future__ import annotations

import gzip
import json
from pathlib import Path

import numpy as np
import pytest

from app.recolor.color_math import parse_color, srgb_to_oklab
from app.recolor.tgs import (
    TgsError,
    load_tgs,
    recolor_tgs_document,
    save_tgs,
)


def sample_document() -> dict[str, object]:
    return {
        "v": "5.7.4",
        "fr": 60,
        "ip": 0,
        "op": 60,
        "w": 512,
        "h": 512,
        "layers": [
            {
                "ty": 4,
                "shapes": [
                    {"ty": "fl", "c": {"a": 0, "k": [1.0, 0.0, 0.0, 1.0]}},
                    {
                        "ty": "st",
                        "c": {
                            "a": 1,
                            "k": [
                                {
                                    "t": 0,
                                    "s": [0.0, 1.0, 0.0, 1.0],
                                    "e": [0.0, 0.0, 1.0, 1.0],
                                    "i": {"x": [0.1], "y": [0.2]},
                                }
                            ],
                        },
                    },
                    {
                        "ty": "gf",
                        "g": {
                            "p": 2,
                            "k": {"a": 0, "k": [0.0, 1.0, 1.0, 1.0, 1.0, 0.1, 0.1, 0.1]},
                        },
                    },
                ],
            }
        ],
        "unknown_extension": {"keep": [1, 2, 3], "colorish": [1, 0, 0, 1]},
    }


def test_tgs_static_animated_and_gradient_colors() -> None:
    source = sample_document()
    output = recolor_tgs_document(source, parse_color("#8B5CF6"))
    shapes = output["layers"][0]["shapes"]  # type: ignore[index]
    assert shapes[0]["c"]["k"] != [1.0, 0.0, 0.0, 1.0]
    assert shapes[1]["c"]["k"][0]["s"] != [0.0, 1.0, 0.0, 1.0]
    gradient = shapes[2]["g"]["k"]["k"]
    assert gradient[0] == 0.0 and gradient[4] == 1.0
    assert gradient[1:4] != [1.0, 1.0, 1.0]
    assert gradient[5:8] != [0.1, 0.1, 0.1]


def test_tgs_uses_one_palette_midpoint_and_preserves_dark_contours() -> None:
    output = recolor_tgs_document(sample_document(), parse_color("#E68D7E"))
    gradient = output["layers"][0]["shapes"][2]["g"]["k"]["k"]  # type: ignore[index]
    light_rgb = np.asarray(gradient[1:4], dtype=np.float64)
    dark_rgb = np.asarray(gradient[5:8], dtype=np.float64)
    lightness = srgb_to_oklab(np.stack([dark_rgb, light_rgb]))[..., 0]
    assert float(lightness[1] - lightness[0]) > 0.30


def test_unknown_tgs_fields_are_preserved() -> None:
    source = sample_document()
    output = recolor_tgs_document(source, parse_color("#FF0000"))
    assert output["unknown_extension"] == source["unknown_extension"]
    assert output["layers"][0]["shapes"][1]["c"]["k"][0]["i"] == {  # type: ignore[index]
        "x": [0.1],
        "y": [0.2],
    }


def test_tgs_gzip_load_save_roundtrip(tmp_path: Path) -> None:
    destination = tmp_path / "animation.tgs"
    save_tgs(sample_document(), destination)
    assert destination.read_bytes().startswith(b"\x1f\x8b")
    assert load_tgs(destination) == sample_document()


def test_corrupted_tgs_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.tgs"
    path.write_bytes(b"not gzip")
    with pytest.raises(TgsError):
        load_tgs(path)


def test_tgs_decompressed_limit(tmp_path: Path) -> None:
    path = tmp_path / "large.tgs"
    payload = json.dumps(sample_document()).encode() + b" " * 2048
    with gzip.open(path, "wb") as target:
        target.write(payload)
    with pytest.raises(TgsError, match="exceeds"):
        load_tgs(path, max_decompressed=512)
