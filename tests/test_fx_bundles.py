"""tier= on every recipe, the generic sequence bundle, and the tiered win_banner."""
import asyncio
import json

import numpy as np
import pytest

from claude_spine import fx_recipes as R, qa, runtime
from claude_spine.fx_bundles import BANNER
from claude_spine.ir import Bone, new_skeleton
from claude_spine.project import Project
from conftest import needs_node


@pytest.fixture
def proj(tmp_path):
    p = Project(tmp_path / "t.json", new_skeleton("t", 720, 720))
    p.data.bones.append(Bone(name="banner", parent="root", y=40))
    return p


def _len(p, anim):
    from claude_spine.fx_bundles import anim_end
    return anim_end(p, anim)


# ---------------------------------------------------------------- tiers
def test_tier_scales_size_count_and_time(proj):
    small = R.apply(proj, "hit_burst", name="s", tier="small")
    epic = R.apply(proj, "hit_burst", name="e", tier="epic")
    plain = R.apply(proj, "hit_burst", name="p")
    g = lambda r: proj.data.bone(r["group_bone"]).scaleX  # noqa: E731
    assert g(small) < g(plain) < g(epic) == pytest.approx(1.5)
    assert len(epic["slots"]) > len(plain["slots"]) > len(small["slots"]), "more sparks for a bigger win"
    assert _len(proj, "fx_e") == pytest.approx(0.95 * 1.4, abs=0.02) and _len(proj, "fx_s") < _len(proj, "fx_p")
    medium = R.apply(proj, "hit_burst", name="m", tier="medium")
    assert len(medium["slots"]) == len(plain["slots"]) and g(medium) == 1


def test_tier_respects_explicit_arguments_and_recipe_overrides(proj, monkeypatch):
    res = R.apply(proj, "hit_burst", name="a", tier="epic", count=3, duration=0.5)
    assert len(res["slots"]) == 5 + 3 and _len(proj, "fx_a") == pytest.approx(0.5, abs=0.02)
    monkeypatch.setitem(R.RECIPES["shine"], "tiers", {"epic": {"size": 300.0}})
    R.apply(proj, "shine", name="b", tier="epic")
    R.apply(proj, "shine", name="c", tier="epic", options={"size": 120.0})
    sz = lambda n: proj.data.skins[0].attachments[f"fx_{n}_core"]["fx"].width  # noqa: E731
    assert sz("b") > sz("c"), "the recipe's tier override applies unless the caller set the option"
    assert "tiers" in R.list_recipes()["shine"]


def test_unknown_tier_and_tier_on_old_bundles(proj):
    with pytest.raises(ValueError, match="tier"):
        R.apply(proj, "shine", tier="huge")
    with pytest.raises(ValueError, match="tier is not supported"):
        R.apply(proj, "magic_reveal", tier="big")


# ---------------------------------------------------------------- sequence
def test_sequence_plays_steps_with_offsets_and_chains_draw_order(proj):
    res = R.apply(proj, "sequence", x=10, y=20, scale=2.0, name="choreo", options=dict(steps=[
        dict(recipe="shine"),
        dict(recipe="hit_burst", start=0.4, dx=50, dy=-10, scale=0.5, tier="big"),
        dict(recipe="twinkles", start=0.6, duration=1.0, intensity=0.5)]))
    assert res["animation"] == "choreo" and res["parts"] == ["shine", "hit_burst", "twinkles"]
    sk = proj.data
    hit = [b for b in sk.bones if b.name.startswith("fx_hit_burst") and b.parent == "root"][0]
    assert (hit.x, hit.y) == (10 + 100, 20 - 20) and hit.scaleX == pytest.approx(2.0 * 0.5 * 1.15)
    ev = {e.name: e.time for e in sk.animations["choreo"].events}
    assert ev["fx_hit_burst"] == pytest.approx(0.4) and ev["fx_twinkles"] == pytest.approx(0.6)
    assert ev["fx_choreo_end"] == pytest.approx(res["end"]) and 1.3 < res["end"] <= 1.6 + 1e-6, "ends at the last key"
    names = [s.name for s in sk.slots]
    idx = [names.index(s) for s in res["slots"]]
    assert idx == sorted(idx), "each step is drawn in front of the one before"
    assert qa.validate(sk)["ok"]


def test_sequence_length_and_errors(proj):
    res = R.apply(proj, "sequence", options=dict(length=3.0, steps=[dict(recipe="shine")]))
    assert res["end"] == 3.0 and _len(proj, "sequence") == 3.0
    with pytest.raises(ValueError, match="steps"):
        R.apply(proj, "sequence", options={})
    with pytest.raises(ValueError, match="unknown key"):
        R.apply(proj, "sequence", options=dict(steps=[dict(recipe="shine", when=1)]))
    with pytest.raises(ValueError, match="cannot contain a sequence"):
        R.apply(proj, "sequence", options=dict(steps=[dict(recipe="sequence")]))
    with pytest.raises(ValueError, match="unknown recipe"):
        R.apply(proj, "sequence", options=dict(steps=[dict(recipe="nope")]))


# ---------------------------------------------------------------- win_banner
@pytest.mark.parametrize("tier", ["small", "big", "mega", "epic"])
def test_win_banner_tiers_grow(proj, tier):
    res = R.apply(proj, "win_banner", tier=tier, options=dict(banner="banner"))
    assert res["animation"] == f"win_{tier}" and res["parts"] == [s["recipe"] for s in BANNER[tier]["steps"]]
    assert {"fx_win_banner", "fx_win_banner_land", "fx_win_banner_end"} <= set(res["events"])
    assert qa.validate(proj.data)["ok"]


def test_win_banner_epic_is_the_biggest(tmp_path):
    sizes = {}
    for t in ("big", "mega", "epic"):
        p = Project(tmp_path / f"{t}.json", new_skeleton("t", 720, 720))
        res = R.apply(p, "win_banner", tier=t)
        sizes[t] = (len(res["slots"]), res["end"])
    assert sizes["big"] < sizes["mega"] < sizes["epic"]


def test_win_banner_slams_in_on_a_spring_through_a_carrier(proj):
    from claude_spine.timeline import AnimBuilder
    AnimBuilder(proj.data, "win_mega", replace=True).bone("banner", "rotate", [(0, 0), (1, 5)])
    res = R.apply(proj, "win_banner", tier="mega", into="win_mega", options=dict(banner="banner", squash=0.6))
    car = res["banner_bone"]
    sk = proj.data
    assert sk.bone("banner").parent == car and [k.time for k in sk.animations["win_mega"].bones["banner"]["rotate"]] == [0, 1]
    ks = sk.animations["win_mega"].bones[car]["scale"]
    t = np.array([k.time for k in ks])
    sx = np.array([1.0 if getattr(k, "x", None) is None else k.x for k in ks])
    sy = np.array([1.0 if getattr(k, "y", None) is None else k.y for k in ks])
    land = res["land_at"]
    assert sx[0] == pytest.approx(2.4) and np.interp(land, t, sy) == pytest.approx(1.0, abs=0.01)
    after = t > land
    assert sy[after].min() == pytest.approx(1 - 0.16, abs=0.01), "shorter by the punch"
    i = np.argmin(np.where(after, sy, 9))
    assert sx[i] == pytest.approx(1 + 0.6 * 0.16, abs=0.01), "wider while it squashes"
    assert (sx[-1], sy[-1]) == (1, 1)
    ev = {e.name: e.time for e in sk.animations["win_mega"].events}
    assert ev["fx_explosion"] == pytest.approx(land)


def test_win_banner_epic_strikes_come_before_the_slam(proj):
    res = R.apply(proj, "win_banner", tier="epic", options=dict(banner="banner"))
    ks = proj.data.animations["win_epic"].bones[res["banner_bone"]]["scale"]
    first = [k for k in ks if (getattr(k, "x", 1) or 0) > 0][0]
    hits = sorted(e.time for e in proj.data.animations["win_epic"].events if e.name == "fx_lightning_strike")
    assert len(hits) == 3
    assert all(h >= 0 for h in hits) and hits[0] < first.time < res["land_at"]


def test_win_banner_skip_extra_and_errors(proj):
    res = R.apply(proj, "win_banner", tier="mega", options=dict(skip=["explosion"], extra=[dict(recipe="rune_ring", start=0.5)]))
    assert "explosion" not in res["parts"] and res["parts"][-1] == "rune_ring"
    with pytest.raises(ValueError, match="skip"):
        R.apply(proj, "win_banner", name="x", tier="big", options=dict(skip=["explosion"]))
    with pytest.raises(ValueError, match="before the banner"):
        R.apply(proj, "win_banner", name="y", options=dict(extra=[dict(recipe="shine", start=-1)]))
    with pytest.raises(ValueError, match="unknown option"):
        R.apply(proj, "win_banner", name="z", options=dict(tier="big"))


def test_the_tool_takes_tier_and_lists_the_bundles(tmp_path):
    from claude_spine.server import mcp

    def call(**args):
        res = asyncio.run(mcp.call_tool("fx_recipe", args))
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)
    listing = call()["recipes"]
    assert {"sequence", "win_banner"} <= set(listing) and "epic" in listing["win_banner"]["tiers"]
    p = Project(tmp_path / "t.json", new_skeleton("t", 720, 720))
    p.save()
    out = call(project=str(p.path), recipe="win_banner", tier="epic")
    assert out["animation"] == "win_epic" and "validation_errors" not in out


@needs_node
@pytest.mark.parametrize("tier", ["big", "epic"])
def test_win_banner_plays_in_the_spine_core_runtime(proj, tier):
    res = R.apply(proj, "win_banner", tier=tier, options=dict(banner="banner"))
    proj.save()
    dump = runtime.run(proj, animations=[res["animation"]], fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    assert dump["animations"][res["animation"]]["duration"] == pytest.approx(res["end"], abs=0.01)


def test_win_banner_layers_sit_behind_the_banner_art(proj):
    from claude_spine.ir import RegionAttachment, Slot
    sk = proj.data
    sk.add_slot(Slot(name="plate", bone="banner"))
    sk.add_slot(Slot(name="hud", bone="root"))
    res = R.apply(proj, "win_banner", tier="big", options=dict(banner="banner"))
    names = [s.name for s in sk.slots]
    assert max(names.index(s) for s in res["slots"]) < names.index("plate") < names.index("hud")


def test_tier_overrides_may_set_count_and_duration(proj, monkeypatch):
    monkeypatch.setitem(R.RECIPES["hit_burst"], "tiers", {"epic": {"count": 4, "duration": 0.5, "size": 300.0}})
    res = R.apply(proj, "hit_burst", name="t", tier="epic")
    assert len(res["slots"]) == 5 + 4 and _len(proj, "fx_t") == pytest.approx(0.5, abs=0.02)
    res2 = R.apply(proj, "hit_burst", name="u", tier="epic", count=6)
    assert len(res2["slots"]) == 5 + 6, "the caller's count wins over the tier's"


def test_win_banner_shakes_the_screen_on_the_impact(proj):
    proj.data.bones.append(Bone(name="screen", parent="root"))
    res = R.apply(proj, "win_banner", tier="epic", options=dict(banner="banner", shake="screen"))
    assert res["parts"][-1] == "screen_shake"
    ev = {e.name: e.time for e in proj.data.animations["win_epic"].events}
    assert ev["fx_screen_shake"] == pytest.approx(res["land_at"])
    assert "fx_shake_screen" in proj.data.animations["win_epic"].bones
