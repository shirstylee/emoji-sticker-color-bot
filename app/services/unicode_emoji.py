"""Unicode grapheme detection and local color-font rendering."""

from __future__ import annotations

from pathlib import Path

import emoji
import regex
from PIL import Image, ImageDraw, ImageFont


class EmojiRenderError(ValueError):
    """A Unicode emoji cannot be safely rendered with the configured font."""


def extract_single_emoji(value: str) -> str | None:
    stripped = value.strip()
    clusters = regex.findall(r"\X", stripped)
    if len(clusters) != 1 or not emoji.is_emoji(clusters[0]):
        return None
    return str(clusters[0])


def render_emoji(value: str, destination: Path, font_path: Path | None, side: int = 512) -> Path:
    grapheme = extract_single_emoji(value)
    if grapheme is None:
        raise EmojiRenderError("Input is not one Unicode emoji grapheme")
    if font_path is None or not font_path.is_file():
        raise EmojiRenderError("Color Emoji font is not configured")
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    try:
        font = ImageFont.truetype(str(font_path), int(side * 0.72))
        draw = ImageDraw.Draw(canvas)
        box = draw.textbbox((0, 0), grapheme, font=font, embedded_color=True)
        x = (side - (box[2] - box[0])) // 2 - box[0]
        y = (side - (box[3] - box[1])) // 2 - box[1]
        draw.text((x, y), grapheme, font=font, embedded_color=True)
    except (OSError, ValueError) as error:
        raise EmojiRenderError("The configured Emoji font cannot render this emoji") from error
    if canvas.getbbox() is None:
        raise EmojiRenderError("The configured Emoji font produced an empty image")
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, "PNG", optimize=True)
    return destination
