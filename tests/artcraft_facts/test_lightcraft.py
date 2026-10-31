"""What lightcraft-cli does that SKILL.md relies on. Each test names the SKILL.md section whose sentence it backs; when one fails after an update, change or delete that sentence rather than loosening the test."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from support.tools import lightcraft, lines

pytestmark = pytest.mark.slow
PHOTOS = Path(__file__).resolve().parents[1] / "fixtures" / "photos"


@pytest.fixture
def jpeg(tmp_path) -> Path:
    y, x = np.mgrid[0:300, 0:400]
    Image.fromarray(np.dstack([x * 255 / 400, y * 255 / 300, np.full_like(x, 120.0)]).astype("uint8")).save(tmp_path / "grad.jpg", quality=95)
    return tmp_path / "grad.jpg"


def render(src: Path, out: Path, *args: str) -> np.ndarray:
    r = lightcraft("render", str(src), "-o", str(out), *args)
    assert r.returncode == 0, r.stderr
    return np.asarray(Image.open(out).convert("RGB"), dtype=float)


def test_jpeg_white_balance_temperature_6500_is_neutral(jpeg):
    """Photos: on a JPEG, wb.temp is an absolute temperature with 6500 as no change (the app's slider shows it relative)."""
    base = render(jpeg, jpeg.with_name("base.png"))
    assert np.abs(render(jpeg, jpeg.with_name("6500.png"), "--set", "wb.temp=6500") - base).mean() == 0
    assert np.abs(render(jpeg, jpeg.with_name("4000.png"), "--set", "wb.temp=4000") - base).mean() > 5


def test_a_value_out_of_range_is_clamped_without_an_error(jpeg):
    """How the CLIs fail quietly: LightCraft clamps an out-of-range slider value to its limit and says nothing."""
    huge = render(jpeg, jpeg.with_name("99.png"), "--set", "light.exposure=99")
    top = render(jpeg, jpeg.with_name("5.png"), "--set", "light.exposure=5")
    assert np.abs(huge - top).mean() == 0


def test_a_settings_file_ignores_unknown_keys_while_set_refuses_them(jpeg):
    """How the CLIs fail quietly: an unknown key in a develop-settings file is dropped silently (the known ones still apply); --set with an unknown control is an error."""
    base = render(jpeg, jpeg.with_name("base.png"))
    settings = jpeg.with_name("s.json")
    settings.write_text(json.dumps({"noSuchKey": 1, "light": {"exposure": 1.0}}))
    assert np.abs(render(jpeg, jpeg.with_name("s.png"), "--settings", str(settings)) - base).mean() > 5
    r = lightcraft("render", str(jpeg), "-o", str(jpeg.with_name("x.png")), "--set", "no.such=3")
    assert r.returncode != 0 and "unknown control" in r.stderr


def test_sam3_prompt_masks_understand_english_only():
    """Photos: a Describe (prompt) mask finds "person" and finds nothing for the same request in Korean."""
    status = lines(lightcraft("run", "segment.model.status").stdout)
    if not status or not status[0].get("result", {}).get("installed"):
        pytest.skip("SAM 3 is not installed in LightCraft")
    r = lightcraft("run", "--import", str(PHOTOS / "one.jpg"), "mask.add", "kind=prompt", "text=person", "mask.add", "kind=prompt", "text=사람", "--keep-going", timeout=600)
    english, korean = [d for d in lines(r.stdout) if d.get("command") == "mask.add"]
    assert english["ok"] is True
    assert korean["ok"] is False and "nothing matching" in korean["error"]
