"""Cluster-pays family (cluster_dim, combo_banner, amount_to_bar, jelly_pop, scatter_shine) and ae_bridge sequence
copies that share frames."""
import math

import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_bridge as B, fx_recipes as R, qa
from claude_spine.fx_cluster import BAR, BOARD, CLUSTER, CLUSTER_RECIPES, CPICS
from claude_spine.ir import new_skeleton
from claude_spine.project import Project


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 742))


def _runs(p):
    runs = []
    for s in p.data.slots:
        if not runs or runs[-1] != s.blend:
            runs.append(s.blend)
    return runs


def _alpha(k):
    return int(k.color[6:8], 16)


@pytest.mark.parametrize("name", CLUSTER_RECIPES)
def test_builds_validates_and_draws_in_at_most_two_blend_runs(proj, name):
    res = R.apply(proj, name)
    assert qa.validate(proj.data)["ok"] and res["event"] == f"fx_{name}"
    assert len(_runs(proj)) <= 2
    assert set(R.ROLES[name]) == set(CPICS)


def test_every_own_picture_fades_before_its_edge():
    for n in ("panel", "jelly_cube", "combo_plate", "amount_plate"):
        a = np.asarray(CPICS[n]())[..., 3]
        assert a.max() > 200 and max(a[0].max(), a[-1].max(), a[:, 0].max(), a[:, -1].max()) == 0, n


def test_cluster_dim_darkens_only_the_other_cells(proj):
    res = R.apply(proj, "cluster_dim")
    assert res["dimmed"] == len(BOARD) - len(CLUSTER) and res["winners"] == len(CLUSTER)
    dims = [b for b in proj.data.bones if b.name.startswith("fx_cluster_dim_d")]
    win = {(round(x), round(y)) for x, y in CLUSTER}
    assert not {(round(b.x), round(b.y)) for b in dims} & win
    an = proj.data.animations["fx_cluster_dim_in"]
    k = an.slots[next(s.name for s in proj.data.slots if s.bone == dims[0].name)]["rgba"]
    assert _alpha(k[-1]) == pytest.approx(0.72 * 255, abs=2) and k[-1].time <= 0.09, "dark within ~2 frames"


def test_cluster_dim_is_an_intro_then_a_seamless_loop(proj):
    res = R.apply(proj, "cluster_dim")
    an = proj.data.animations["fx_cluster_dim"]
    for s, tl in an.slots.items():
        k = tl.get("rgba")
        if k:
            assert k[0].color == k[-1].color and k[-1].time == pytest.approx(1.2), s
    intro = proj.data.animations[res["intro"]]
    dim_slot = next(s.name for s in proj.data.slots if "_d" in s.name)
    ki = intro.slots[dim_slot]["rgba"]
    assert _alpha(ki[0]) == 0 and ki[-1].color == an.slots[dim_slot]["rgba"][0].color, "the intro ends where the loop starts"
    assert "cluster_found" in {e.name for e in intro.events}


def test_combo_zoom_lands_from_big_with_ghosts(proj, tmp_path):
    res = R.apply(proj, "combo_banner", options={"style": "zoom"})
    an = proj.data.animations["fx_combo_banner"]
    sc = an.bones["fx_combo_banner_title"]["scale"]
    assert sc[0].x == pytest.approx(3.2, abs=0.01) and [k for k in sc if k.time >= 0.25][0].x == pytest.approx(1.0, abs=0.06)
    assert sum(1 for b in proj.data.bones if "ghost" in b.name) == 3 and res["lands_at"] == pytest.approx(0.14)
    q = Project(tmp_path / "q.json", new_skeleton("q", 720, 742))
    R.apply(q, "combo_banner")
    assert not any("ghost" in b.name for b in q.data.bones)
    with pytest.raises(ValueError, match="punch \\| zoom"):
        R.apply(q, "combo_banner", name="x", options={"style": "spin"})


def test_amount_drops_into_the_bar_accelerating(proj):
    res = R.apply(proj, "amount_to_bar", count=0)
    k = proj.data.animations["fx_amount_to_bar"].bones["fx_amount_to_bar_amount"]["translate"]
    end = [kk for kk in k if kk.time >= 0.26][0]
    assert (end.x or 0, end.y or 0) == pytest.approx((BAR[0], BAR[1]), abs=1)
    ys = [kk.y or 0 for kk in k if kk.time <= 0.26]
    steps = np.diff(ys)
    assert steps[-1] < steps[1] < 0, "eases in"
    assert res["ae_hint"]["template"] == "burst" and "bar_hit" in {e.name for e in proj.data.animations["fx_amount_to_bar"].events}


def test_jelly_pop_hint_shares_one_glitter_sequence_across_cells(proj, tmp_path):
    res = R.apply(proj, "jelly_pop", options={"twinkles": 0})
    h = res["ae_hint"]
    assert h["template"] == "sparkle" and len(h["copies"]) == len(CLUSTER) - 1
    d = tmp_path / "frames"
    d.mkdir()
    for i in range(4):
        Image.new("RGBA", (64, 64), (255, 255, 255, 60 * (i + 1))).save(d / f"g_{i:02d}.png")
    kw = {k: v for k, v in h.items() if k not in ("template", "params", "note")}
    out = B.fx_to_spine(proj, "glitter", frames_dir=str(d), fps=24, animation=res["animation"], **kw)
    assert len(out["copies"]) == len(CLUSTER) - 1
    assert len(list((proj.images_dir / "ae").glob("glitter_*.png"))) == out["frames_out"], "one set of frames"
    an = proj.data.animations[res["animation"]]
    for s in out["copies"]:
        assert an.slots[s]["attachment"][1].time == pytest.approx(h["start"]) and s in an.slots
    assert qa.validate(proj.data)["ok"]


def test_copy_sequence_follows_a_parent_and_rejects_a_missing_one(proj, tmp_path):
    from claude_spine.ir import Bone
    d = tmp_path / "f"
    d.mkdir()
    Image.new("RGBA", (8, 8), (255, 255, 255, 255)).save(d / "a_0.png")
    proj.data.bones.append(Bone(name="aim", parent="root", rotation=90))
    res = B.fx_to_spine(proj, "s", frames_dir=str(d), fps=24, parent="aim")
    slot = B.copy_sequence(proj, res, x=10, y=0, start=0.5)
    bn = next(b for b in proj.data.bones if b.name == next(s.bone for s in proj.data.slots if s.name == slot))
    assert bn.parent == "aim" and (bn.x, bn.y) == (10, 0)
    with pytest.raises(ValueError, match="no bone"):
        B.copy_sequence(proj, res, parent="nope")


def test_scatter_shine_staggers_each_scatter(proj):
    R.apply(proj, "scatter_shine", options={"cells": [[0, 0], [100, 0], [200, 0]], "stagger": 0.1})
    an = proj.data.animations["fx_scatter_shine"]
    firsts = sorted(tl["attachment"][1].time for s, tl in an.slots.items() if "comet" in s)
    assert np.allclose(np.diff(firsts), 0.1, atol=1e-3)
