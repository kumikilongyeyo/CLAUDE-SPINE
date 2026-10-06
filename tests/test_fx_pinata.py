"""Piñata family: the twelve recipes, the shared gain / thick options, art swapping, loop closure, hand-off and events."""
import math

import numpy as np
import pytest
from PIL import Image

from claude_spine import fx_recipes as R, qa
from claude_spine.fx_pinata import CONFETTI, PICS, PINATA_RECIPES, pack_tuning
from claude_spine.ir import new_skeleton
from claude_spine.project import Project

LOOPS = [n for n in PINATA_RECIPES if R.RECIPES[n]["kind"] == "loop"]
NORMAL_PICS = {"smoke_puff", "coin", "mult_number", "x5_label", *CONFETTI}


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 1200))


def _alpha(k):
    return int(k.color[6:8], 16)


def _pic(p, slot):
    return p.data.attachment(slot, "fx").path.split("/")[-1].replace("pinata_", "")


@pytest.mark.parametrize("name", PINATA_RECIPES)
def test_builds_validates_and_only_the_normal_pictures_are_normal(proj, name):
    res = R.apply(proj, name, options=pack_tuning())
    assert res["animation"] == f"fx_{name}" and res["event"] == f"fx_{name}"
    v = qa.validate(proj.data)
    assert v["ok"], v["errors"]
    for s in proj.data.slots:
        assert (s.blend == "normal") == (_pic(proj, s.name) in NORMAL_PICS), (s.name, s.blend)
        assert s.attachment is None


def test_every_picture_is_an_art_role_and_generates_a_neutral_texture():
    assert set(R.ROLES["wild_glow"]) == set(PICS)
    for n, make in PICS.items():
        im = make()
        a = np.asarray(im)[..., 3]
        assert im.mode == "RGBA" and a.max() > 150, n
        assert max(a[0].max(), a[-1].max(), a[:, 0].max(), a[:, -1].max()) < 40, f"{n} must fade before its edge"


def test_gain_scales_only_that_pictures_alpha(proj, tmp_path):
    q = Project(tmp_path / "q.json", new_skeleton("q", 720, 1200))
    R.apply(proj, "wild_glow")
    R.apply(q, "wild_glow", options={"gain": {"glow_soft": 0.5}})
    a, b = proj.data.animations["fx_wild_glow"].slots, q.data.animations["fx_wild_glow"].slots
    for s in a:
        ka, kb = [_alpha(k) for k in a[s]["rgba"]], [_alpha(k) for k in b[s]["rgba"]]
        if _pic(proj, s) == "glow_soft":
            assert all(abs(y - round(x * 0.5)) <= 1 for x, y in zip(ka, kb))
        else:
            assert ka == kb


def test_thick_stretches_the_hairline_pictures(proj, tmp_path):
    q = Project(tmp_path / "q.json", new_skeleton("q", 720, 1200))
    R.apply(proj, "bar_sweep")
    R.apply(q, "bar_sweep", options={"thick": {"light_streak": [1, 2.4], "shine_band": [2.6, 1]}})
    for s in proj.data.slots:
        a, b = proj.data.attachment(s.name, "fx"), q.data.attachment(s.name, "fx")
        wx, hy = {"light_streak": (1, 2.4), "shine_band": (2.6, 1)}[_pic(proj, s.name)]
        assert b.width == pytest.approx(a.width * wx, abs=0.01) and b.height == pytest.approx(a.height * hy, abs=0.01)


def test_unknown_gain_picture_is_a_clear_error(proj):
    with pytest.raises(ValueError, match="unknown picture"):
        R.apply(proj, "cell_pop", options={"gain": {"glo_soft": 0.5}})


def test_art_swaps_a_picture_and_keeps_the_motion(proj, tmp_path):
    png = tmp_path / "my_glow.png"
    Image.new("RGBA", (64, 32), (255, 255, 255, 128)).save(png)
    plain = Project(tmp_path / "plain.json", new_skeleton("p", 720, 1200))
    R.apply(plain, "mult_cell_glow")
    res = R.apply(proj, "mult_cell_glow", art={"glow_soft": str(png)})
    assert res["art"] == {"glow_soft": "fx/art_mult_cell_glow_glow_soft"}
    g = next(s.name for s in proj.data.slots if "glow" in s.name and proj.data.attachment(s.name, "fx").path.endswith("glow_soft"))
    att = proj.data.attachment(g, "fx")
    assert att.height == pytest.approx(att.width / 2, abs=0.01), "the art keeps its own aspect"
    assert proj.data.animations["fx_mult_cell_glow"].slots[g] == plain.data.animations["fx_mult_cell_glow"].slots[g]


@pytest.mark.parametrize("name", LOOPS)
def test_loops_close(proj, name):
    R.apply(proj, name)
    an = proj.data.animations[f"fx_{name}"]
    D = R.RECIPES[name]["duration"]
    for s, tl in an.slots.items():
        k = tl.get("rgba")
        if k and len(k) > 1 and k[-1].time == pytest.approx(D, abs=1e-3):
            assert abs(_alpha(k[0]) - _alpha(k[-1])) <= 2, s
    hidden_at_ends = {sl.bone for sl in proj.data.slots if (k := an.slots.get(sl.name, {}).get("rgba"))
                      and _alpha(k[0]) <= 2 and _alpha(k[-1]) <= 2}       # a restart while invisible is a closed loop
    for b, tl in an.bones.items():
        k = tl.get("translate")
        if k and len(k) > 1 and k[-1].time == pytest.approx(D, abs=1e-3) and b not in hidden_at_ends:
            assert (k[0].x or 0) == pytest.approx(k[-1].x or 0, abs=0.5) and (k[0].y or 0) == pytest.approx(k[-1].y or 0, abs=0.5), b


def test_wild_transform_hands_off_to_wild_glow(proj, tmp_path):
    q = Project(tmp_path / "q.json", new_skeleton("q", 720, 1200))
    R.apply(proj, "wild_transform")
    R.apply(q, "wild_glow")
    after = proj.data.animations["fx_wild_transform"].slots["fx_wild_transform_after"]["rgba"][-1]
    glow = q.data.animations["fx_wild_glow"].slots["fx_wild_glow_glow"]["rgba"][0]
    assert after.color == glow.color
    assert proj.data.attachment("fx_wild_transform_after", "fx").width == q.data.attachment("fx_wild_glow_glow", "fx").width


@pytest.mark.parametrize("name, events", [
    ("wild_transform", {"wild_pop"}), ("mult_streak", {"mult_to_sign"}), ("wild_merge", {"merge_hit"}),
    ("pinata_hit", {"fireball_land"}), ("jar_burst", {"x5_flare", "x5_to_sign"})])
def test_events(proj, name, events):
    R.apply(proj, name)
    names = {e.name for e in proj.data.animations[f"fx_{name}"].events}
    assert events | {f"fx_{name}"} <= names


def test_fireballs_land_where_asked(proj):
    res = R.apply(proj, "pinata_hit", x=100, y=50, options={"land": [[-200, -300], [0, -400]]})
    assert len(res["lands"]) == 2
    lands = [b for b in proj.data.bones if b.name.endswith("_land")]
    assert [(b.x, b.y) for b in lands] == [(-200, -300), (0, -400)]


def test_coins_and_their_flashes_are_one_blend_run_each(proj):
    R.apply(proj, "coins_to_bar")
    runs = [proj.data.slots[0].blend]
    for s in proj.data.slots[1:]:
        if s.blend != runs[-1]:
            runs.append(s.blend)
    assert runs == ["additive", "normal", "additive"]


def test_comets_never_spin_round(proj):
    R.apply(proj, "wild_merge")
    an = proj.data.animations["fx_wild_merge"]
    for b, tl in an.bones.items():
        if "comet" in b and "rotate" in tl:
            v = [k.value for k in tl["rotate"]]
            assert max(abs(x - y) for x, y in zip(v, v[1:])) < 45, b


def test_banner_rain_respawns_inside_alpha_zero(proj):
    R.apply(proj, "banner_backdrop")
    an = proj.data.animations["fx_banner_backdrop"]
    jumps = 0
    for b, tl in an.bones.items():
        k = tl.get("translate")
        if not k or "rc" not in b and "cf" not in b:
            continue
        slot = next(s.name for s in proj.data.slots if s.bone == b)
        alpha = {round(c.time, 4): _alpha(c) for c in an.slots[slot]["rgba"]}
        for k0, k1 in zip(k, k[1:]):
            if (k1.y or 0) - (k0.y or 0) > 600:                      # bottom -> top respawn
                jumps += 1
                assert alpha[round(k0.time, 4)] == 0 and alpha[round(k1.time, 4)] == 0, (b, k0.time, k1.time)
                assert k1.time - k0.time < 0.003, "the jump must take no visible time"
    assert jumps > 20


def test_mult_streak_cells_option_moves_the_cells(proj):
    R.apply(proj, "mult_streak", options={"cells": [[-100, 10], [100, 10]]})
    cells = sorted((b.x, b.y) for b in proj.data.bones if b.name.startswith("fx_mult_streak_cell") and "cellg" not in b.name)
    assert cells == [(-100, 10), (100, 10)]
