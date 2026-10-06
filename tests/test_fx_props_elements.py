"""Element props (flame_wick, liquid_bubble, prop_drip, prop_steam, prop_electric, prop_freeze, prop_dissolve,
smoke_wisp): physically motivated motion, seamless loops with hidden respawns, the artist's bones never keyed, and
ae_hints that build with the real templates."""
import math

import numpy as np
import pytest
from PIL import Image

from claude_spine import fx_recipes as R, qa, runtime
from claude_spine.ae_templates import build_script, list_templates
from claude_spine.fx_props_elements import DRIP_G, NAMES, OWN
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project
from claude_spine.timeline import AnimBuilder
from conftest import needs_node

ARTIST = ("prop", "lid")


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


@pytest.fixture
def art(tmp_path):
    """An artist's prop: a body bone with two layers and a lid bone, no animation."""
    p = Project(tmp_path / "a.json", new_skeleton("a", 720, 720))
    sk = p.data
    sk.bones += [Bone(name="prop", parent="root", x=10, y=-20), Bone(name="lid", parent="prop", y=110)]
    for n, b in (("body", "prop"), ("label", "prop"), ("cap", "lid")):
        p.write_image(n, Image.new("RGBA", (64, 64), (255, 255, 255, 255)))
        sk.add_slot(Slot(name=n, bone=b, attachment=n))
        sk.set_attachment(n, n, RegionAttachment(path=n, width=64, height=64))
    return p


def _vals(k):
    return tuple(getattr(k, f) or 0.0 for f in ("x", "y", "value") if hasattr(k, f) or getattr(k, f, None) is not None)


def _closed(p, anim):
    """Every bone timeline and every colour timeline ends where it starts."""
    a = p.data.animations[anim]
    bad = []
    for bn, tls in a.bones.items():
        for tl, ks in tls.items():
            if ks[0].model_dump(exclude={"time", "curve"}) != ks[-1].model_dump(exclude={"time", "curve"}):
                bad.append((bn, tl))
    for sn, tls in a.slots.items():
        if "rgba" in tls and tls["rgba"][0].color != tls["rgba"][-1].color:
            bad.append((sn, "rgba"))
    return bad


def _runs(p):
    runs = []
    for s in p.data.slots:
        if not runs or runs[-1] != s.blend:
            runs.append(s.blend)
    return runs


def _xy(k):
    return (k.x or 0.0), (k.y or 0.0)


def _alpha(k):
    return int(k.color[6:8], 16) / 255


def _at(keys, t, f):
    ts = [k.time for k in keys]
    return float(np.interp(t, ts, [f(k) for k in keys]))


# ---------------------------------------------------------------- shared rules
@pytest.mark.parametrize("name", NAMES)
def test_defaults_build_hidden_grouped_and_valid(proj, name):
    res = R.apply(proj, name)
    assert res["slots"] and res["event"] == f"fx_{name}"
    assert all(s.attachment is None for s in proj.data.slots)
    normal_ok = R.RECIPES[name].get("normal_blend")
    assert all(s.blend == "additive" or (normal_ok and s.blend == "normal") for s in proj.data.slots)
    assert len(_runs(proj)) <= 3
    assert R.RECIPES[name]["roles"] and qa.validate(proj.data)["ok"]
    if R.RECIPES[name]["kind"] == "loop":
        assert _closed(proj, res["animation"]) == [], "a loop must end where it starts"


@pytest.mark.parametrize("name", NAMES)
def test_the_artists_bones_are_never_keyed(art, name):
    opts = {"flame_wick": {"follow": "prop"}, "prop_freeze": {"prop": "prop"}, "prop_dissolve": {"prop": "prop"}}.get(name)
    res = R.apply(art, name, parent="prop" if name not in ("flame_wick", "prop_freeze", "prop_dissolve") else "root",
                  front_of="cap", options=opts)
    a = art.data.animations[res["animation"]]
    assert not set(ARTIST) & set(a.bones), sorted(set(ARTIST) & set(a.bones))
    assert {s.name for s in art.data.slots if s.name in ("body", "label", "cap")} == {"body", "label", "cap"}
    assert qa.validate(art.data)["ok"]


def test_own_pictures_fade_to_nothing_before_their_edges():
    for name, make in OWN.items():
        a = np.asarray(make(), np.float32)[..., 3]
        border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
        assert border.max() == 0, name
        assert a.max() > 200, name


def test_ae_hints_build_with_the_real_templates(proj, tmp_path):
    tpl = list_templates()
    hints = {n: R.apply(proj, n, name=n)["ae_hint"] for n in ("flame_wick", "prop_steam", "prop_electric", "prop_dissolve", "smoke_wisp")}
    built = []
    for n, h in hints.items():
        parts = [h] + ([h["alt"]] if "alt" in h else []) + ([h["embers"]] if "embers" in h else [])
        parts += [dict(template=h["template"], params=v["params"]) for v in h.get("variants", [])]
        for part in parts:
            if part.get("template") and part.get("params"):
                assert part["template"] in tpl
                built.append(build_script(part["template"], part["params"], out_dir=tmp_path / n)["template"])
    assert {"fire", "smoke_puff", "smoke_haze", "lightning", "burst"} <= set(built)
    assert hints["flame_wick"]["params"]["edge_fade"] > 0 and hints["flame_wick"]["params"]["width"] <= 160
    assert hints["prop_dissolve"]["template"] is None and "Fractal Noise" in hints["prop_dissolve"]["note"]


# ---------------------------------------------------------------- flame_wick
def test_flame_flickers_seamlessly_and_sways_when_nothing_moves(proj):
    res = R.apply(proj, "flame_wick")
    a = proj.data.animations[res["animation"]]
    sc = a.bones[res["flame_bone"]]["scale"]
    ys = [k.y for k in sc]
    assert max(ys) - min(ys) > 0.15 and not res["following"]
    assert sc[0].time == 0 and sc[-1].time == pytest.approx(2.0)
    assert _closed(proj, res["animation"]) == []


def test_flame_leans_against_the_props_motion(art):
    AnimBuilder(art.data, "carry").bone("prop", "translate", [(0, 0, 0), (0.5, 110, 0), (1.0, 110, 0), (1.5, -110, 0),
                                                              (2.0, -110, 0), (2.4, 0, 0)], "sine_in_out")
    before = art.data.animations["carry"].bones["prop"]["translate"][:]
    res = R.apply(art, "flame_wick", into="carry", y=110, options={"follow": "prop", "flicker": 0.0})
    a = art.data.animations["carry"]
    assert a.bones["prop"]["translate"] == before, "the artist's keys stay as they were"
    assert art.data.bone(res["group_bone"]).parent == "prop" and res["following"]
    assert res["loop"] == pytest.approx(2.4), "loops with the animation it follows"
    rot = a.bones[res["flame_bone"]]["rotate"]
    v = lambda t: _at(rot, t, lambda k: k.value or 0.0)  # noqa: E731
    assert v(0.3) > 6, "moving right: the tip trails left (CCW)"
    assert v(1.3) < -6, "moving left: the tip trails right"
    assert _closed(art, "carry") == []


# ---------------------------------------------------------------- liquid_bubble
def test_bubbles_rise_grow_and_pop_at_the_surface(proj):
    res = R.apply(proj, "liquid_bubble", options={"area": [0, 0, 160, 220], "surface_y": 90.0})
    a = proj.data.animations[res["animation"]]
    sk = proj.data
    bub = [s for s in res["slots"] if sk.attachment(s, "fx").path.endswith("bubble_rim")]
    rings = [s for s in res["slots"] if sk.attachment(s, "fx").path.endswith("pinata_ring")]
    assert len(bub) == len(rings) == 8 and res["surface_y"] == 90.0
    for sb, sr in zip(bub, rings):
        tr = a.bones[sk.slot(sb).bone]["translate"]
        col = a.slots[sb]["rgba"]
        assert max(k.y or 0 for k in tr) <= 90.0 and min(k.y or 0 for k in tr) < -60, "from the bottom up to the surface"
        # inside a life: y climbs, the bubble grows
        vis = [(k, s_) for k, s_ in zip(tr, a.bones[sk.slot(sb).bone]["scale"]) if _at(col, k.time, _alpha) > 0.5]
        assert len(vis) > 4
        # every respawn (a jump of > 40 units between keys under 3 ms apart) happens at alpha 0 on BOTH sides
        jumps = [(k0, k1) for k0, k1 in zip(tr, tr[1:]) if k1.time - k0.time < 0.003 and abs((k1.y or 0) - (k0.y or 0)) > 40]
        assert jumps, "respawns are keyed at exact times either side of the wrap"
        for k0, k1 in jumps:
            assert _at(col, k0.time, _alpha) == 0 and _at(col, k1.time, _alpha) == 0
        # the ring only shows ON the surface
        rt = a.bones[sk.slot(sr).bone]["translate"]
        assert all((k.y or 0) == pytest.approx(90.0) for k in rt)
        assert max(_alpha(k) for k in a.slots[sr]["rgba"]) > 0.4
    sc = a.bones[sk.slot(bub[0]).bone]["scale"]
    tr = a.bones[sk.slot(bub[0]).bone]["translate"]
    col = a.slots[bub[0]]["rgba"]
    low = [s_.y for k, s_ in zip(tr, sc) if _at(col, k.time, _alpha) > 0.8 and (k.y or 0) < 0]
    high = [s_.y for k, s_ in zip(tr, sc) if _at(col, k.time, _alpha) > 0.8 and 40 < (k.y or 0) < 80]
    assert low and high and np.mean(high) > np.mean(low), "bubbles grow as they rise"
    assert _closed(proj, res["animation"]) == []


def test_round_vessel(proj):
    res = R.apply(proj, "liquid_bubble", count=4, options={"radius": 100.0})
    assert res["surface_y"] == pytest.approx(45.0) and _closed(proj, res["animation"]) == []


# ---------------------------------------------------------------- prop_drip
def test_drip_snaps_then_falls_with_gravity_and_splats(proj):
    res = R.apply(proj, "prop_drip", options={"at": [0, 0], "floor_y": -300.0})
    a = proj.data.animations[res["animation"]]
    ev = {e.name: e.time for e in a.events}
    assert ev["prop_drip_snap"] == res["snap_at"] < ev["prop_drip_splat"] == res["splat_at"]
    fall = next(b for b in a.bones if b.endswith("_fall"))
    hang = next(b for b in a.bones if b.endswith("_hang"))
    tr = a.bones[fall]["translate"]
    before = [k for k in tr if k.time < res["snap_at"]]
    assert len({(k.y or 0) for k in before}) == 1, "nothing falls before the snap"
    during = [k for k in tr if res["snap_at"] <= k.time <= res["splat_at"]]
    t = np.array([k.time for k in during])
    y = np.array([k.y or 0 for k in during])
    acc = np.polyfit(t, y, 2)[0] * 2
    assert acc == pytest.approx(-DRIP_G, rel=0.02), "free fall"
    sc = a.bones[fall]["scale"]
    sy = [_at(sc, tt, lambda k: k.y) for tt in (res["snap_at"] + 0.02, res["splat_at"] - 0.02)]
    assert sy[1] > sy[0] > 0.9, "stretched by its speed"
    hs = a.bones[hang]["scale"]
    k_snap = max((k for k in hs if k.time < res["snap_at"]), key=lambda k: k.time)
    assert k_snap.y > 1.5 and k_snap.x < 0.8, "it necks: long and thin at the pinch"
    assert _at(hs, res["snap_at"] + 0.3, lambda k: k.y) < 0.8, "the stub springs back"
    # the splat lands on the floor and the droplets come back down to it
    splat = next(s for s in res["slots"] if s.endswith("_splat"))
    assert proj.data.bone(proj.data.slot(splat).bone).y == -300.0
    att = a.slots[splat]["attachment"]
    assert [k.time for k in att if k.name == "fx"] == [res["splat_at"]]


def test_drip_loop_closes(proj):
    res = R.apply(proj, "prop_drip", options={"loop": True, "floor_y": -260.0})
    assert res["loop"] and _closed(proj, res["animation"]) == []


def test_drip_floor_above_the_drop_is_an_error(proj):
    with pytest.raises(ValueError, match="floor_y"):
        R.apply(proj, "prop_drip", options={"at": [0, 0], "floor_y": 20.0})


# ---------------------------------------------------------------- prop_steam
def test_steam_builds_to_a_climax_with_a_whistle_jet(proj):
    res = R.apply(proj, "prop_steam", options={"climax": 2.4})
    a = proj.data.animations[res["animation"]]
    assert [e.time for e in a.events if e.name == "prop_steam_climax"] == [res["climax_at"]] == [2.4]
    ts = [t for t, _ in res["emits"]]
    early = np.diff([t for t in ts if t < 1.0]).mean()
    late = np.diff([t for t in ts if t > 2.4]).mean()
    assert late < early / 2.5, "the rhythm quickens"
    big = dict(res["emits"])
    assert np.mean([b for t, b in big.items() if t > 2.4]) > 1.25 * np.mean([b for t, b in big.items() if t < 0.8])
    jet = [s for s in res["slots"] if proj.data.attachment(s, "fx").path.endswith("light_streak")]
    assert len(jet) == 2 and _runs(proj) == ["normal", "additive"]
    for s in jet:
        col = a.slots[s]["rgba"]
        assert _at(col, 2.3, _alpha) == 0 and _at(col, 2.8, _alpha) > 0.5
    puff = next(s for s in res["slots"] if proj.data.slot(s).blend == "normal")
    tr = a.bones[proj.data.slot(puff).bone]["translate"]
    assert max(k.y or 0 for k in tr) > 60, "puffs rise"
    h = res["ae_hint"]
    assert h["template"] == "smoke_puff" and h["copies"] and all(len(cp) == 3 for cp in h["copies"])
    assert h["alt"]["template"] == "smoke_haze"


# ---------------------------------------------------------------- prop_electric
def test_crackles_only_between_the_given_points_and_loop(proj):
    pts = [[-80, 90], [80, 90], [-80, -90], [80, -90], [0, 120]]
    res = R.apply(proj, "prop_electric", count=10, options={"points": pts, "segments": 5})
    a = proj.data.animations[res["animation"]]
    assert len(res["crackles"]) == 10
    for cr in res["crackles"]:
        i, j = cr["pair"]
        assert i != j and 0 <= i < len(pts) and 0 <= j < len(pts) and 2 <= cr["strokes"] <= 3
    allowed = {tuple(map(float, p)) for p in pts}
    ends = [b for b in a.bones if "_r" in b and b.rsplit("_", 1)[-1][-2] == "e"]
    assert ends
    for b in ends:
        for k in a.bones[b]["translate"]:
            assert (round(k.x or 0, 2), round(k.y or 0, 2)) in allowed
    # the first and last segment of every stroke start / end on a given point
    seg0 = [b for b in a.bones if b.endswith("s0")]
    for b in seg0:
        for kt, kr, ks in zip(a.bones[b]["translate"], a.bones[b]["rotate"], a.bones[b]["scale"]):
            L = ks.x * 100.0 / 1.22
            sx = (kt.x or 0) - math.cos(math.radians(kr.value or 0)) * L / 2
            sy = (kt.y or 0) - math.sin(math.radians(kr.value or 0)) * L / 2
            assert min(math.hypot(sx - p[0], sy - p[1]) for p in pts) < 0.05
            assert kt.curve == "stepped" or kt is a.bones[b]["translate"][-1], "a stroke re-jags instantly"
    assert _closed(proj, res["animation"]) == []
    vs = res["ae_hint"]["variants"]
    assert vs and {tuple(sorted(cr["pair"])) for cr in res["crackles"]} == {tuple(v["pair"]) for v in vs}
    assert sum(1 + len(v["args"]["copies"]) for v in vs) == 10


def test_electric_needs_two_points(proj):
    with pytest.raises(ValueError, match="two"):
        R.apply(proj, "prop_electric", options={"points": [[0, 0]]})


# ---------------------------------------------------------------- prop_freeze
def test_freeze_slows_the_idle_to_a_stop_and_shivers(art):
    R.apply(art, "prop_idle", into="idle", options={"prop": "prop"})
    res = R.apply(art, "prop_freeze", options={"prop": "prop", "idle": "idle", "lock": 1.4})
    a = art.data.animations[res["animation"]]
    assert [e.time for e in a.events if e.name == "prop_frozen"] == [res["frozen_at"]] == [1.4]
    tilt = next(b for b in a.bones if b.startswith("fx_proptilt"))
    rk = a.bones[tilt]["rotate"]
    after = {round(k.value or 0, 3) for k in rk if k.time >= 1.4}
    assert len(after) == 1, "locked: the idle stops"
    moving = [abs((k1.value or 0) - (k0.value or 0)) / (k1.time - k0.time) for k0, k1 in zip(rk, rk[1:]) if k1.time < 0.4]
    slowing = [abs((k1.value or 0) - (k0.value or 0)) / (k1.time - k0.time) for k0, k1 in zip(rk, rk[1:]) if 1.1 < k0.time < 1.35]
    assert max(moving) > 3 * max(slowing + [1e-9]), "it slows before it locks"
    sh = a.bones[res["carrier"]]["rotate"]
    win = [k.value or 0 for k in sh if 1.4 < k.time < 1.6]
    assert max(win) > 0.5 and min(win) < -0.5, "a tiny shiver at the lock"
    assert all(abs(k.value or 0) < 0.05 for k in sh if k.time > 1.9), "and it dies out"
    assert "prop" not in a.bones and art.data.bone("prop").parent == res["carrier"]


def test_freeze_mirrors_an_idle_on_the_artists_own_bone_and_thaws(art):
    AnimBuilder(art.data, "idle").bone("prop", "rotate", [(0, 0), (0.5, 10), (1.0, 0)], None)
    res = R.apply(art, "prop_freeze", options={"prop": "prop", "idle": "idle", "thaw": 0.8, "hold": 0.5})
    a = art.data.animations[res["animation"]]
    assert "prop" not in a.bones and res["idle_mirrored"] == ["rotate"]
    rk = a.bones[res["carrier"]]["rotate"]
    assert _at(rk, 0.25, lambda k: k.value or 0) == pytest.approx(5.0, abs=0.6), "the idle replays on the carrier"
    assert res["thaw_at"] == pytest.approx(1.9) and any(e.name == "prop_thaw" for e in a.events)
    thawed = [k.value or 0 for k in rk if k.time > res["thaw_at"] + 0.4]
    assert max(thawed) - min(thawed) > 0.5, "after the thaw it moves again"


# ---------------------------------------------------------------- prop_dissolve
def test_dissolve_clips_the_prop_and_hides_after_the_sweep_starts(art):
    res = R.apply(art, "prop_dissolve", front_of="cap", options={"prop": "prop", "box": [10, 20, 160, 240]})
    a = art.data.animations[res["animation"]]
    t_hide = [e.time for e in a.events if e.name == "prop_dissolve_hide"]
    assert t_hide == [res["hide_at"]] and res["hide_at"] > res["sweep"][0]
    assert res["hide_at"] == pytest.approx(res["sweep"][1]), "with a clip: hide once nothing is left"
    names = [s.name for s in art.data.slots]
    clip = art.data.attachment(res["clip_slot"], "fx")
    assert names.index(res["clip_slot"]) == names.index("body") - 1 and clip.end == "cap"
    assert art.data.slot(res["clip_slot"]).attachment is None, "the clip only acts in this animation"
    wipe = art.data.slot(res["clip_slot"]).bone
    ys = [k.y or 0 for k in a.bones[wipe]["translate"]]
    assert all(b >= a_ - 1e-6 for a_, b in zip(ys, ys[1:])) and ys[0] < -120 and ys[-1] > 120, "sweeps the whole box"
    assert all(s.blend == "additive" for s in art.data.slots if s.name in res["slots"])


def test_dissolve_without_a_prop_hides_mid_sweep_under_a_flash(proj):
    res = R.apply(proj, "prop_dissolve", options={"direction": "left"})
    t0, t1 = res["sweep"]
    assert t0 < res["hide_at"] < t1 and "clip_slot" not in res
    a = proj.data.animations[res["animation"]]
    ember = next(b for b in a.bones if "_em" in b)
    tr = [k for k in a.bones[ember]["translate"] if k.time > 0]
    assert (tr[-1].y or 0) > (tr[0].y or 0) + 60, "embers lift off"
    with pytest.raises(ValueError, match="direction"):
        R.apply(proj, "prop_dissolve", name="bad", options={"direction": "sideways"})


# ---------------------------------------------------------------- smoke_wisp
def test_smoke_wisp_curls_up_widens_and_loops(proj):
    res = R.apply(proj, "smoke_wisp", options={"at": [0, -50]})
    a = proj.data.animations[res["animation"]]
    sk = proj.data
    xs_top = []
    for s in res["slots"]:
        b = sk.slot(s).bone
        tr, sc, col = a.bones[b]["translate"], a.bones[b]["scale"], a.slots[s]["rgba"]
        jumps = [(k0, k1) for k0, k1 in zip(tr, tr[1:]) if k1.time - k0.time < 0.003 and (k0.y or 0) - (k1.y or 0) > 100]
        assert jumps, "each puff respawns at the source"
        for k0, k1 in jumps:
            assert _alpha(col[[k.time for k in col].index(k0.time)]) == 0 and _alpha(col[[k.time for k in col].index(k1.time)]) == 0
        low = [s_.x for k, s_ in zip(tr, sc) if (k.y or 0) < 0]
        high = [s_.x for k, s_ in zip(tr, sc) if (k.y or 0) > 150]
        assert np.mean(high) > 2 * np.mean(low), "widens as it rises"
        xs_top += [k.x or 0 for k in tr if (k.y or 0) > 150]
    assert max(xs_top) - min(xs_top) > 40, "curls sideways up top"
    assert _closed(proj, res["animation"]) == []


# ---------------------------------------------------------------- runtime
@needs_node
def test_all_eight_on_one_prop_play_in_the_runtime(art):
    AnimBuilder(art.data, "show").bone("prop", "translate", [(0, 0, 0), (1.0, 40, 0), (2.0, 0, 0)], "sine_in_out")
    R.apply(art, "flame_wick", into="show", y=120, options={"follow": "lid"})
    R.apply(art, "liquid_bubble", into="show", parent="prop", duration=2.0)
    R.apply(art, "prop_drip", into="show", options={"at": [40, -80], "floor_y": -260})
    R.apply(art, "prop_steam", into="show", duration=2.0, options={"climax": 1.4, "at": [60, 60]})
    R.apply(art, "prop_electric", into="show", parent="prop")
    R.apply(art, "smoke_wisp", into="show", duration=2.0, options={"at": [0, 130]})
    R.apply(art, "prop_freeze", options={"prop": "prop", "idle": "show"})
    R.apply(art, "prop_dissolve", options={"prop": "lid"})
    assert qa.validate(art.data)["ok"]
    art.save()
    anims = ["show", "fx_prop_freeze", "fx_prop_dissolve"]
    d = runtime.run(art, animations=anims, fps=15, geometry=True)
    assert not d.get("problems"), d.get("problems")
    assert all(d["animations"][n]["frames"] for n in anims)
