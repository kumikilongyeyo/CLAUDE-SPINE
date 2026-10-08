import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_look, server
from test_ae_bridge import blob_frames


def test_hit_with_anticipation():
    en = [0, 0, 1, 2, 3, 10, 9, 6, 4, 2, 1, 0.5]
    ht = [0, 0, 0, 0, 0.01, 0.2, 0.05, 0, 0, 0, 0, 0]
    b = ae_look.find_beats(en, ht)
    assert b["kind"] == "hit"
    assert b["beats"] == {"anticipation_end": 4, "impact": 5, "mid_decay": 8, "residual": 11}


def test_hit_that_opens_on_its_flash_shows_the_spread():
    en = [8, 9, 10, 7, 4, 2, 1]
    ht = [0.3, 0.1, 0.0, 0, 0, 0, 0]
    b = ae_look.find_beats(en, ht)
    assert b["kind"] == "hit" and b["beats"] == {"impact": 0, "spread": 2, "mid_decay": 4, "residual": 6}


def test_hit_without_white_hot_pixels_uses_the_biggest_rise():
    b = ae_look.find_beats([0, 1, 2, 8, 9, 3, 1])
    assert b["beats"]["impact"] == 3 and b["beats"]["anticipation_end"] == 2


def test_build_and_loop():
    b = ae_look.find_beats([0, 1, 3, 5, 8, 9.6, 10, 10, 9.8])
    assert b["kind"] == "build"
    assert b["beats"] == {"start": 1, "half_built": 3, "fully_built": 5, "end": 8}
    b = ae_look.find_beats([8, 9, 10, 9, 8, 9, 10, 9, 8])
    assert b["kind"] == "loop" and list(b["beats"].values()) == [0, 2, 4, 6]


def test_empty_frames_are_a_clear_error():
    with pytest.raises(ValueError, match="empty"):
        ae_look.find_beats([0, 0, 0])


def test_sheet_from_frames_with_art(tmp_path):
    d = blob_frames(tmp_path / "fr", n=10, lead=2, trail=1)
    art = tmp_path / "coin.png"
    Image.new("RGBA", (20, 20), (220, 170, 40, 255)).save(art)
    plain = ae_look.quick_look(frames_dir=str(d), fps=24, out=str(tmp_path / "a.png"), tile=120)
    scene = ae_look.quick_look(frames_dir=str(d), fps=24, art=str(art), out=str(tmp_path / "b.png"), tile=120)
    a, b = Image.open(plain["sheet"]), Image.open(scene["sheet"])
    assert b.height > a.height and a.width == b.width                    # the scene row is added
    assert plain["kind"] in ("hit", "build") and plain["visible"] == [2, 8]
    assert all(0 <= v["frame"] <= 9 and v["time"] == pytest.approx(v["frame"] / 24, abs=1e-4)
               for v in plain["beats"].values())
    # the scene row shows the art: its centre pixel in a tile is the coin colour or the effect over it
    px = np.asarray(b.convert("RGB"), np.int16)
    assert (np.abs(px - [220, 170, 40]).sum(2) < 30).any()


def test_tool_is_registered(tmp_path):
    d = blob_frames(tmp_path / "fr", n=8, lead=1, trail=1)
    res = server.ae_quick_look(frames_dir=str(d), fps=30, out=str(tmp_path / "s.png"), art_offset=[2, -3])
    assert res["sheet"].endswith("s.png") and len(res["beats"]) == 4
    with pytest.raises(ValueError, match="aep"):
        server.ae_quick_look(fps=30)


def test_a_breathing_loop_is_a_loop_not_a_build():
    en = [8, 9, 10, 9.5, 8, 6, 5, 5.2, 6.5, 7.8]          # swells, dips to half, comes back to where it started
    assert ae_look.find_beats(en)["kind"] == "loop"
