"""Small images made in a test, so the test knows exactly what is in them."""

from __future__ import annotations

from pathlib import Path

from PIL import Image


def make_png(path: Path, size=(400, 500), color=(240, 235, 225), mode="RGB") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fill = color if mode == "RGB" else (*color[:3], color[3] if len(color) > 3 else 255)
    Image.new(mode, size, fill).save(path)
    return path
