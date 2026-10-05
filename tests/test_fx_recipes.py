"""FX recipes: every recipe builds, validates, renders in the runtime, and honours the shared arguments."""
import asyncio
import json
from pathlib import Path

import pytest

from claude_spine import fx_recipes as R, qa, runtime
from claude_spine.ir import RegionAttachment, new_skeleton
from claude_spine.project import Project
from conftest import needs_node

ALL = list(R.RECIPES)


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


def _dur(p, anim):
    a = p.data.animations[anim]
    ts = [0.0]
    for tl in a.bones.values():
        for keys in tl.values():
            ts += [k.time for k in keys]
    for tl in a.slots.values():
        for keys in tl.values():
            ts += [k.time for k in keys]
    return max(ts)


@pytest.mark.parametrize("name", ALL)
def test_each_recipe_builds_and_validates(proj, name):
    res = R.apply(proj, name)
    assert res["animation"] == f"fx_{name}" and res["slots"] and res["event"] == f"fx_{name}"
    assert all(s.blend == "additive" for s in proj.data.slots)
    assert all(s.attachment is None for s in proj.data.slots), "FX slots must be hidden in the setup pose"
    v = qa.validate(proj.data)
    assert v["ok"], v["errors"]


@needs_node
@pytest.mark.parametrize("name", ALL + ["magic_reveal"])
def test_each_recipe_plays_in_the_spine_core_runtime(proj, name):
    res = R.apply(proj, name)
    proj.save()
    dump = runtime.run(proj, animations=[res["animation"]], fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    assert dump["animations"][res["animation"]]["frames"]


def test_unknown_recipe_or_option_is_a_clear_error(proj):
    with pytest.raises(ValueError, match="unknown recipe"):
        R.apply(proj, "nope")
    with pytest.raises(ValueError, match="unknown option"):
        R.apply(proj, "rune_ring", options={"colour": "red"})
    with pytest.raises(ValueError, match="scale"):
        R.apply(proj, "rune_ring", scale=0)


def test_x_y_scale_land_on_the_group_bone(proj):
    res = R.apply(proj, "bloom_aura", x=120, y=-40, scale=1.5)
    g = proj.data.bone(res["group_bone"])
    assert (g.x, g.y, g.scaleX, g.scaleY) == (120, -40, 1.5, 1.5)
    assert g.parent == "root"


def test_parent_and_draw_order(proj):
    from claude_spine.ir import Bone, Slot
    proj.data.bones.append(Bone(name="hand", parent="root", x=50))
    proj.data.add_slot(Slot(name="art", bone="hand"))
    proj.data.add_slot(Slot(name="top", bone="hand"))
    res = R.apply(proj, "twinkles", parent="hand", front_of="art")
    assert proj.data.bone(res["group_bone"]).parent == "hand"
    names = [s.name for s in proj.data.slots]
    assert names.index("art") + 1 == names.index(res["slots"][0]) and names.index("top") > names.index(res["slots"][-1])
    res2 = R.apply(proj, "twinkles", behind="art", name="back")
    names = [s.name for s in proj.data.slots]
    assert names.index(res2["slots"][-1]) + 1 == names.index("art")


def test_color_bakes_its_own_texture(proj):
    a = R.apply(proj, "rune_ring")
    b = R.apply(proj, "rune_ring", color="5AE0FF", name="cyan")
    pa = proj.data.skin("default").attachments[a["slots"][1]]["fx"].path
    pb = proj.data.skin("default").attachments[b["slots"][1]]["fx"].path
    assert pa == "fx/rune_ring_FFCD3C" and pb == "fx/rune_ring_5AE0FF"
    import numpy as np

    def tint(path):
        im = np.asarray(proj.image(path), float)
        w = im[..., 3:4]
        return (im[..., :3] * w).sum((0, 1)) / w.sum()
    ta, tb = tint(pa), tint(pb)
    assert ta[0] > ta[2] + 50 and tb[2] > tb[0] + 20, (ta, tb)    # gold stays warm, cyan goes cool


def test_start_shifts_and_into_merges_into_an_existing_animation(proj):
    from claude_spine.timeline import AnimBuilder
    AnimBuilder(proj.data, "win").bone("root", "rotate", [(0, 0), (1.2, 10)])
    res = R.apply(proj, "burst_flare", into="win", start=0.5)
    a = proj.data.animations["win"]
    assert res["animation"] == "win" and "root" in a.bones and a.bones["root"]["rotate"][-1].time == 1.2
    flare_bones = [b for b in proj.data.bones if b.name.startswith("fx_burst_flare")]
    first = min(k.time for b in flare_bones if b.name in a.bones for tl in a.bones[b.name].values() for k in tl)
    assert first >= 0.5
    assert any(e.name == "fx_burst_flare" and e.time == 0.5 for e in a.events)


def test_one_shot_duration_is_a_time_scale_and_window_duration_is_a_length(proj):
    a = R.apply(proj, "rune_ring")
    b = R.apply(proj, "rune_ring", duration=5.4, name="slow")
    assert _dur(proj, b["animation"]) == pytest.approx(2 * _dur(proj, a["animation"]), rel=0.02)
    c = R.apply(proj, "fireflies", duration=4.0)
    assert _dur(proj, c["animation"]) == pytest.approx(4.0, abs=0.01)


def test_count_and_seed(proj, tmp_path):
    assert len(R.apply(proj, "fireflies", count=12)["slots"]) == 12
    assert R.apply(proj, "rim_wisps", count=8)["tufts"] == 8
    q1 = Project(tmp_path / "a.json", new_skeleton("a", 720, 720))
    q2 = Project(tmp_path / "b.json", new_skeleton("b", 720, 720))
    q3 = Project(tmp_path / "c.json", new_skeleton("c", 720, 720))
    for q, sd in ((q1, 7), (q2, 7), (q3, 9)):
        R.apply(q, "fireflies", seed=sd)
    dump = lambda q: json.dumps(q.data.model_dump(mode="json", exclude_none=True), sort_keys=True)  # noqa: E731
    assert dump(q1) == dump(q2) and dump(q1) != dump(q3)


def test_intensity_scales_alpha(proj):
    a = R.apply(proj, "bloom_aura", name="a")
    b = R.apply(proj, "bloom_aura", name="b", intensity=0.5)
    def peak(anim, slot):
        ks = proj.data.animations[anim].slots[slot]["rgba"]
        return max(int(k.color[6:8], 16) for k in ks)
    assert peak(b["animation"], b["slots"][0]) < peak(a["animation"], a["slots"][0])


def test_fireflies_respawn_hides_inside_alpha_zero(proj):
    res = R.apply(proj, "fireflies", count=6)
    a = proj.data.animations[res["animation"]]
    for s in res["slots"]:
        keys = a.slots[s]["rgba"]
        # every key pair closer than 5 ms is a respawn: both sides must be invisible
        for k0, k1 in zip(keys, keys[1:]):
            if k1.time - k0.time < 0.005:
                assert int(k0.color[6:8], 16) <= 6 and int(k1.color[6:8], 16) <= 6


def test_magic_reveal_bundle(proj):
    res = R.apply(proj, "magic_reveal", scale=0.8, x=10)
    assert res["parts"] == [n for n, *_ in R.REVEAL] and res["animation"] == "magic_reveal"
    assert _dur(proj, "magic_reveal") <= R.REVEAL_LENGTH + 1e-6
    ev = {e.name: e.time for e in proj.data.animations["magic_reveal"].events}
    assert ev["fx_rune_ring"] == 2.0 and ev["fx_burst_flare"] == 3.55 and ev["fx_reveal_end"] == R.REVEAL_LENGTH
    b = qa.budget(proj.data, "desktop")
    assert b["metrics"]["draw_calls"] == 1 and b["metrics"]["clipping"] == 0 and b["metrics"]["weighted_vertices"] == 0
    names = [s.name for s in proj.data.slots]
    assert len(names) == len(set(names))
    assert {s.blend for s in proj.data.slots} == {"additive"}


def test_magic_reveal_skip_and_overrides(proj):
    res = R.apply(proj, "magic_reveal", options={"skip": ["fireflies", "twinkles"],
                                                 "overrides": {"rune_ring": {"color": "5AE0FF"}}})
    assert "fireflies" not in res["parts"] and "twinkles" not in res["parts"]
    assert proj.image_path("fx/rune_ring_5AE0FF")
    with pytest.raises(ValueError, match="unknown recipe"):
        R.apply(proj, "magic_reveal", options={"skip": ["nope"]})


def test_the_mcp_tool_lists_returns_the_guide_and_applies(tmp_path):
    from claude_spine.server import mcp

    def call(**args):
        res = asyncio.run(mcp.call_tool("fx_recipe", args))
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)
    listing = call()
    assert set(R.RECIPES) | {"magic_reveal"} <= set(listing["recipes"])
    assert "Fork" in call(recipe="guide")["guide"]
    p = Project(tmp_path / "t.json", new_skeleton("t", 720, 720))
    p.save()
    out = call(project=str(p.path), recipe="rune_ring", x=5, y=5)
    assert out["animation"] == "fx_rune_ring" and "validation_errors" not in out
    assert "fx_rune_ring" in Project.open(p.path).data.animations


def test_docs_guide_mirrors_the_tool_guide():
    from claude_spine.fx_recipes_guide import GUIDE
    doc = Path(__file__).resolve().parents[1] / "docs" / "FX_RECIPES.md"
    assert doc.read_text() == GUIDE
