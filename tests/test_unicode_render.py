from pathlib import Path

from PIL import Image

from app.services import unicode_emoji


def test_fixed_strike_color_font_falls_back_and_centers(
    tmp_path: Path, monkeypatch
) -> None:
    font_path = tmp_path / "NotoColorEmoji.ttf"
    font_path.write_bytes(b"font")
    attempted: list[int] = []

    def render(_grapheme: str, _font_path: Path, size: int) -> Image.Image:
        attempted.append(size)
        if size != 109:
            raise OSError("invalid pixel size")
        return Image.new("RGBA", (80, 60), (255, 80, 0, 255))

    monkeypatch.setattr(unicode_emoji, "_render_with_font_size", render)
    destination = tmp_path / "emoji.png"

    unicode_emoji.render_emoji("🦆", destination, font_path, side=512)

    assert 109 in attempted
    with Image.open(destination) as result:
        assert result.size == (512, 512)
        assert result.mode == "RGBA"
        assert result.getbbox() is not None
