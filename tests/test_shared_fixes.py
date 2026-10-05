"""Fixes to shared FX code found while building the recipe families."""
import math

import numpy as np
import pytest

from claude_spine import fx, fx_recipes as R
from claude_spine.ir import new_skeleton
from claude_spine.project import Project


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


@pytest.mark.parametrize("recipe,event", [("shine", "fx_shine"), ("puff", "fx_puff")])
def test_recipes_fire_their_event_once(proj, recipe, event):
    R.apply(proj, recipe)
    names = [e.name for e in proj.data.animations[f"fx_{recipe}"].events]
    assert names.count(event) == 1


def test_frame_glow_texture_is_zero_on_its_border():
    a = np.asarray(R.tex_rrglow())[..., 3].astype(int)
    assert a[0].max() == a[-1].max() == a[:, 0].max() == a[:, -1].max() == 0
    assert a.max() > 200


def test_shine_sweep_travels_across_its_band(symbol):
    res = fx.generate(symbol, "shine_sweep", slot="gem", angle=25)
    sk = symbol.data
    ks = sk.animations[res["animation"]].bones[res["bone"]]["translate"]
    get = lambda k, f: 0.0 if getattr(k, f, None) is None else float(getattr(k, f))  # noqa: E731
    d = np.array([get(ks[-1], "x") - get(ks[0], "x"), get(ks[-1], "y") - get(ks[0], "y")])
    parent = sk.world()[sk.bone(res["bone"]).parent]
    w0, w1 = parent.to_world(0, 0), parent.to_world(*d)
    wd = np.array(w1) - np.array(w0)
    band = np.array([math.cos(math.radians(115)), math.sin(math.radians(115))])
    assert abs(np.dot(wd / np.linalg.norm(wd), band)) < 1e-3, "the travel is perpendicular to the band"


def test_a_32px_region_keeps_its_size_on_save(tmp_path):
    from claude_spine.ir import RegionAttachment, Slot, SkeletonData
    p = Project(tmp_path / "s.json", new_skeleton("s", 100, 100))
    p.data.add_slot(Slot(name="dot", bone="root", attachment="dot"))
    p.data.set_attachment("dot", "dot", RegionAttachment(path="dot", width=32, height=32))
    d = p.data.to_dict()
    att = d["skins"][0]["attachments"]["dot"]["dot"]
    assert (att["width"], att["height"]) == (32, 32), "spine-core has no default for a region's size"
    back = SkeletonData.model_validate(d) if hasattr(SkeletonData, "model_validate") else None
    if back is not None:
        assert back.skins[0].attachments["dot"]["dot"].width == 32
