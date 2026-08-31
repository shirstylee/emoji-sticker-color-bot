"""Unicode grapheme detection and local color-font rendering."""

from __future__ import annotations

from pathlib import Path

import emoji
import regex
from PIL import Image, ImageDraw, ImageFont


class EmojiRenderError(ValueError):
    """A Unicode emoji cannot be safely rendered with the configured font."""


def extract_emojis(value: str) -> list[str] | None:
    """Return every emoji grapheme from an emoji-only message."""

    clusters = [cluster for cluster in regex.findall(r"\X", value.strip()) if not cluster.isspace()]
    if not clusters or any(not emoji.is_emoji(cluster) for cluster in clusters):
        return None
    return [str(cluster) for cluster in clusters]


def extract_single_emoji(value: str) -> str | None:
    clusters = extract_emojis(value)
    if clusters is None or len(clusters) != 1:
        return None
    return clusters[0]


def _render_with_font_size(grapheme: str, font_path: Path, font_size: int) -> Image.Image:
    """Render one grapheme, including fixed-strike color fonts used on Linux."""

    font = ImageFont.truetype(str(font_path), font_size)
    probe = Image.new("RGBA", (font_size * 5, font_size * 5), (0, 0, 0, 0))
    draw = ImageDraw.Draw(probe)
    box = draw.textbbox((0, 0), grapheme, font=font, embedded_color=True)
    width = max(1, round(box[2] - box[0]))
    height = max(1, round(box[3] - box[1]))
    glyph = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    glyph_draw = ImageDraw.Draw(glyph)
    glyph_draw.text((-box[0], -box[1]), grapheme, font=font, embedded_color=True)
    if glyph.getbbox() is None:
        raise ValueError("Emoji font produced an empty glyph")
    return glyph


def render_emoji(value: str, destination: Path, font_path: Path | None, side: int = 512) -> Path:
    grapheme = extract_single_emoji(value)
    if grapheme is None:
        raise EmojiRenderError("Input is not one Unicode emoji grapheme")
    if font_path is None or not font_path.is_file():
        raise EmojiRenderError("Color Emoji font is not configured")
    # Noto Color Emoji on common Linux distributions is a bitmap color font with
    # one or a few fixed strikes. Scalable fonts accept the first size; fixed fonts
    # fall through to their native sizes and are resized only after rendering.
    sizes = [int(side * 0.72), 160, 136, 128, 109, 96, 72, 64]
    glyph: Image.Image | None = None
    last_error: Exception | None = None
    for font_size in dict.fromkeys(sizes):
        try:
            glyph = _render_with_font_size(grapheme, font_path, font_size)
            break
        except (OSError, ValueError) as error:
            last_error = error
    if glyph is None:
        raise EmojiRenderError("The configured Emoji font cannot render this emoji") from last_error

    maximum = max(1, int(side * 0.82))
    scale = min(maximum / glyph.width, maximum / glyph.height)
    size = (max(1, round(glyph.width * scale)), max(1, round(glyph.height * scale)))
    if glyph.size != size:
        glyph = glyph.resize(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(glyph, ((side - glyph.width) // 2, (side - glyph.height) // 2))
    destination.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(destination, "PNG", optimize=True)
    return destination
