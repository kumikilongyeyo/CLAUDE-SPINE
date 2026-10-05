"""Feature triggers: wild_land (gravity drop, restitution bounces, area-preserving squash, sticky hold loop),
expanding_wild (liquid fill: 9-slice front, Poiseuille bulge, damped standing waves), scatter_trigger (land rings,
sequential locks, constant-speed beams, capacitor charge, burst) and free_spins_transition (exponential infall with
conserved angular momentum, puff, spring back to rest)."""
import math

import numpy as np
import pytest

from claude_spine import fx_features, fx_recipes as R, qa, runtime
from claude_spine.ir import Bone, Slot, new_skeleton
from claude_spine.project import Project
from claude_spine.timeline import AnimBuilder
from conftest import needs_node

FEATURES = ["wild_land", "expanding_wild", "scatter_trigger", "free_spins_transition"]


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


@pytest.fixture
def game(tmp_path):
    """A backdrop on root, then a 'machine' bone with a reel bg, a wild symbol and a cabinet slot."""
    p = Project(tmp_path / "g.json", new_skeleton("g", 720, 720))
    sk = p.data
    sk.add_slot(Slot(name="backdrop", bone="root"))
    sk.bones.append(Bone(name="machine", parent="root", y=10))
    sk.bones.append(Bone(name="wild", parent="machine", x=162, y=0))
    for nm, bn in (("reelbg", "machine"), ("wild", "wild"), ("cabinet", "machine")):
        sk.add_slot(Slot(name=nm, bone=bn))
    return p


def _tl(p, anim, bone, timeline, rest):
    keys = p.data.animations[anim].bones[bone][timeline]
    t = np.array([k.time for k in keys])
    if timeline == "rotate":
        return t, np.array([rest if getattr(k, "value", None) is None else float(k.value) for k in keys])
    v = lambda k, f: rest if getattr(k, f, None) is None else float(getattr(k, f))  # noqa: E731
    return t, np.array([v(k, "x") for k in keys]), np.array([v(k, "y") for k in keys])


def _alpha(p, anim, slot):
    keys = p.data.animations[anim].slots[slot]["rgba"]
    return np.array([k.time for k in keys]), np.array([int(k.color[6:8], 16) / 255 for k in keys])


def _events(p, anim, name):
    return [e for e in p.data.animations[anim].events if e.name == name]


# ---------------------------------------------------------------- every recipe
def test_features_are_registered_with_roles():
    for n in FEATURES:
        assert n in R.RECIPES and R.RECIPES[n]["roles"] == R.ROLES[n]
        assert n in R.list_recipes()


@pytest.mark.parametrize("name", FEATURES)
def test_each_feature_builds_validates_and_hides_its_slots(proj, name):
    res = R.apply(proj, name)
    assert res["animation"] == f"fx_{name}" and res["event"] == f"fx_{name}"
    assert _events(proj, res["animation"], f"fx_{name}")[0].time == 0
    sk = proj.data
    assert all(s.attachment is None for s in sk.slots), "FX slots must be hidden in the setup pose"
    nb = R.RECIPES[name].get("normal_blend", False)
    assert all(s.blend == "additive" or (nb and s.blend == "normal") for s in sk.slots)
    v = qa.validate(sk)
    assert v["ok"], v["errors"]


@pytest.mark.parametrize("name", ["wild_land", "scatter_trigger"])
def test_light_only_features_are_one_batch(proj, name):
    R.apply(proj, name)
    assert {s.blend for s in proj.data.slots} == {"additive"}
    assert qa.budget(proj.data, "desktop")["metrics"]["draw_calls"] == 1


def test_expanding_wild_puts_the_liquid_first(proj):
    res = R.apply(proj, "expanding_wild")
    blends = [proj.data.slot(s).blend for s in res["slots"]]
    assert blends[:2] == ["normal", "normal"] and set(blends[2:]) == {"additive"}, "fill + surface band, then the light"
    assert qa.budget(proj.data, "desktop")["metrics"]["draw_calls"] == 2


@needs_node
@pytest.mark.parametrize("name", FEATURES)
def test_each_feature_plays_in_the_spine_core_runtime(proj, name):
    res = R.apply(proj, name)
    proj.save()
    anims = [res["animation"]] + ([res["hold_anim"]] if res.get("hold_anim") else [])
    dump = runtime.run(proj, animations=anims, fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    for a in anims:
        assert dump["animations"][a]["frames"]


@needs_node
def test_features_on_game_bones_play_together_in_the_runtime(game):
    AnimBuilder(game.data, "feature", replace=False).bone("wild", "rotate", [(0, 0), (0.4, 8)])
    R.apply(game, "wild_land", x=162, into="feature", options=dict(wild="wild"))
    R.apply(game, "scatter_trigger", start=0.5, into="feature", options=dict(centre=[0, 300]))
    R.apply(game, "free_spins_transition", start=3.0, into="feature", options=dict(screen="machine"))
    assert qa.validate(game.data)["ok"]
    game.save()
    dump = runtime.run(game, animations=["feature", "feature_hold"], fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    assert dump["animations"]["feature"]["duration"] == pytest.approx(3.0 + 2.52, abs=0.02)


def test_start_into_and_retime(proj):
    R.apply(proj, "scatter_trigger", start=1.0, into="intro")
    ev = _events(proj, "intro", "fx_scatter_trigger")
    assert ev[0].time == 1.0
    res = R.apply(proj, "wild_land", duration=R.RECIPES["wild_land"]["duration"] * 2, name="slow")
    assert res["impact_at"] == pytest.approx(0.76) and res["hold_period"] == pytest.approx(1.6)


# ---------------------------------------------------------------- wild_land
def test_wild_falls_on_a_gravity_parabola_and_lands_on_time(proj):
    res = R.apply(proj, "wild_land", options=dict(drop=400, fall=0.4))
    g = 2 * 400 / 0.4 ** 2
    assert res["gravity"] == pytest.approx(g, rel=1e-3) and res["impact_at"] == pytest.approx(0.4)
    t, _, y = _tl(proj, "fx_wild_land", res["drop_bone"], "translate", 0.0)
    fall = t <= 0.4
    assert np.allclose(y[fall], 400 - 0.5 * g * t[fall] ** 2, atol=0.6), "y = h - g t^2 / 2"
    assert y[0] == pytest.approx(400) and np.interp(0.4, t, y) == pytest.approx(0, abs=0.6)
    ev = _events(proj, "fx_wild_land", "fx_wild_impact")
    assert [e.time for e in ev] == [0.4]


def test_wild_bounces_with_restitution_and_squashes_area_preserving(proj):
    res = R.apply(proj, "wild_land", options=dict(drop=480, fall=0.38, bounce=0.4, squash=0.3))
    t, x, y = _tl(proj, "fx_wild_land", res["drop_bone"], "translate", 0.0)
    c = res["contacts"]
    assert len(c) >= 3 and res["bounces"] == len(c)
    h1 = y[(t > c[0]) & (t < c[1])].max()
    h2 = y[(t > c[1]) & (t < c[2])].max()
    assert h1 == pytest.approx(480 * 0.4 ** 2, rel=0.02), "first bounce = e^2 x the drop"
    assert h2 / h1 == pytest.approx(0.4 ** 2, rel=0.06)
    ts, sx, sy = _tl(proj, "fx_wild_land", res["drop_bone"], "scale", 1.0)
    assert np.allclose(sx * sy, 1.0, atol=0.01), "area-preserving squash and stretch"
    assert sy.min() == pytest.approx(0.7, abs=0.005), "the first squash is exactly `squash`"
    assert sy[(ts > 0.2) & (ts < 0.37)].max() > 1.15, "stretched along its speed as it falls"
    deepest = [sy[(ts >= a) & (ts <= a + 0.12)].min() for a in c]
    assert deepest == sorted(deepest) and deepest[-1] > 0.95, "softer hits squash less"
    assert (y[-1], sx[-1], sy[-1]) == (0, 1, 1) and t[-1] == pytest.approx(res["rest_at"])
    assert len(_events(proj, "fx_wild_land", "fx_wild_bounce")) == len(c) - 1


def test_wild_carrier_moves_the_game_wild_without_touching_its_keys(game):
    sk = game.data
    before = (sk.world()["wild"].x, sk.world()["wild"].y)
    AnimBuilder(sk, "drop", replace=False).bone("wild", "rotate", [(0, 0), (0.5, 12)])
    res = R.apply(game, "wild_land", x=162, y=0, parent="machine", into="drop", options=dict(wild="wild", height=150))
    car = res["drop_bone"]
    assert sk.bone("wild").parent == car and sk.bone(car).parent == "machine"
    w = sk.world()
    assert (w["wild"].x, w["wild"].y) == pytest.approx(before), "inserting the carrier moves nothing"
    assert (w[car].x, w[car].y) == pytest.approx((162, 10 - 75)), "the carrier sits at the cell's base: it squashes onto the floor"
    assert [k.time for k in sk.animations["drop"].bones["wild"]["rotate"]] == [0, 0.5]
    assert set(sk.animations["drop"].bones[car]) == {"translate", "scale"}


def test_wild_sticky_glow_hands_over_to_a_closed_hold_loop(proj):
    res = R.apply(proj, "wild_land", options=dict(pulse=0.7, hold=2))
    hold = res["hold_anim"]
    assert hold == "fx_wild_land_hold" and res["hold_period"] == pytest.approx(0.7)
    line = [s for s in res["slots"] if "_line" in s][0]
    t, a = _alpha(proj, "fx_wild_land", line)
    th, ah = _alpha(proj, hold, line)
    assert ah[0] == pytest.approx(ah[-1], abs=1 / 255) and th[-1] == pytest.approx(0.7), "the loop closes exactly"
    assert a[-1] == pytest.approx(ah[0], abs=1 / 255), "the clip ends on the loop's first frame"
    assert t[-1] == pytest.approx(res["duration"]) and res["duration"] == pytest.approx(res["hold_from"] + 1.4)
    assert a[np.argmin(np.abs(t - res["impact_at"] - 0.04))] > 0.9, "it snaps on bright at the impact"
    att = proj.data.animations[hold].slots[line]["attachment"]
    assert [(k.time, k.name) for k in att] == [(0, "fx")]
    tf, sf, _ = _tl(proj, "fx_wild_land", [b for b in proj.data.animations["fx_wild_land"].bones if b.endswith("_frame")][0], "scale", 1.0)
    assert sf.max() > 1.2 and sf.min() == pytest.approx(1 - 0.28 * 0.25, abs=0.01), "spring snap with exact overshoot"
    assert sf[-1] == 1
    assert "electric_frame" in res["ae_hint"]["note"] and res["ae_hint"]["animation"] == hold


def test_wild_bad_options(proj, game):
    with pytest.raises(ValueError, match="restitution"):
        R.apply(proj, "wild_land", options=dict(bounce=1.2))
    with pytest.raises(ValueError, match="drop and fall"):
        R.apply(proj, "wild_land", options=dict(fall=0))
    with pytest.raises(ValueError, match="no bone"):
        R.apply(game, "wild_land", options=dict(wild="nope"))
    with pytest.raises(ValueError, match="root"):
        R.apply(game, "wild_land", options=dict(wild="root"))


# ---------------------------------------------------------------- expanding_wild
def test_expanding_wild_front_fills_the_reel_from_its_cell(proj):
    res = R.apply(proj, "expanding_wild", options=dict(height=450, cell=150, fill=0.6))
    a = proj.data.animations["fx_expanding_wild"]
    surf = [b for b in a.bones if b.endswith("_surf")][0]
    t, _, y = _tl(proj, "fx_expanding_wild", surf, "translate", 0.0)
    assert y[0] == pytest.approx(450 - 150), "starts one cell below the top (the front is keyed back from the full reel)"
    assert np.interp(0.6, t, y) == pytest.approx(0, abs=0.01) and np.all(np.diff(y) <= 1e-6), "falls monotonically to the floor"
    assert np.interp(0.3, t, y) == pytest.approx(150, abs=1), "eased: halfway in height at half the fill time"
    for k in res["front_corners"]:
        ct, _, cy = _tl(proj, "fx_expanding_wild", res["corner_bones"][k], "translate", 0.0)
        assert cy[0] > y[0] and cy[-1] == 0, "the mesh front trails the wavy surface, then lands on rest (full size)"
    assert [e.time for e in _events(proj, "fx_expanding_wild", "fx_expanding_wild_full")] == [res["full_at"]] == [0.6]


def test_expanding_wild_leads_in_the_middle_then_sloshes_and_settles(proj):
    res = R.apply(proj, "expanding_wild", duration=3.0, options=dict(fill=0.6, bulge=16, wobble=9, damping=0.14))
    rows = res["surface_bones"]
    assert len(rows) == 9
    t, wall, _ = _tl(proj, "fx_expanding_wild", rows[0], "translate", 0.0)
    _, mid, _ = _tl(proj, "fx_expanding_wild", rows[4], "translate", 0.0)
    during = (t > 0.05) & (t < 0.55)
    assert np.allclose(wall[during], 0, atol=0.05), "Poiseuille: the liquid is pinned at the walls while it flows"
    assert mid[during].max() == pytest.approx(16, abs=0.5) and np.interp(0.3, t, mid) == pytest.approx(16, abs=0.5), "fastest flow, biggest lead"
    after = t > 0.6
    flips = np.sum(np.diff(np.sign(mid[after & (np.abs(mid) > 0.05)])) != 0)
    assert flips >= 4, "standing waves: the centre swings back and forth"
    early = np.abs(mid[(t > 0.6) & (t < 0.95)]).max()
    late = np.abs(mid[(t > 1.3) & (t < 1.65)]).max()
    assert late < 0.6 * early, "damped"
    assert np.abs(wall[after]).max() > 3, "the walls slosh too once the front has landed"
    assert mid[-1] == 0 and wall[-1] == 0, "flat at the end"


def test_expanding_wild_upward_and_bad_options(proj):
    res = R.apply(proj, "expanding_wild", options=dict(direction="up"))
    assert res["front_corners"] == ["tl", "tr"]
    surf = [b for b in proj.data.animations["fx_expanding_wild"].bones if b.endswith("_surf")][0]
    assert proj.data.bone(surf).rotation == 90
    with pytest.raises(ValueError, match="direction"):
        R.apply(proj, "expanding_wild", name="b", options=dict(direction="left"))
    with pytest.raises(ValueError, match="cell"):
        R.apply(proj, "expanding_wild", name="c", options=dict(cell=60))
    with pytest.raises(ValueError, match="damping"):
        R.apply(proj, "expanding_wild", name="d", options=dict(damping=1.5))
    with pytest.raises(ValueError, match="fill"):
        R.apply(proj, "expanding_wild", name="e", duration=0.5)


# ---------------------------------------------------------------- scatter_trigger
SC = [[-300.0, 150.0, 0.0], [0.0, -150.0, 0.35], [300.0, 150.0, 0.7]]


def test_scatters_land_lock_in_order_and_fire_the_bonus(proj):
    res = R.apply(proj, "scatter_trigger", options=dict(scatters=SC, centre=[0, 0], stagger=0.25, lock_delay=0.35))
    assert res["triggered"] and res["lands"] == [0.0, 0.35, 0.7]
    lands = _events(proj, "fx_scatter_trigger", "fx_scatter_land")
    assert [e.time for e in lands] == [0.0, 0.35, 0.7] and [e.int for e in lands] == [1, 2, 3]
    locks = _events(proj, "fx_scatter_trigger", "fx_scatter_lock")
    assert [e.time for e in locks] == pytest.approx([1.05, 1.3, 1.55]) and [e.int for e in locks] == [1, 2, 3]
    bonus = _events(proj, "fx_scatter_trigger", "fx_scatter_bonus")
    assert [e.time for e in bonus] == [res["trigger_at"]] and res["trigger_at"] == pytest.approx(max(res["arrivals"]) + 0.1, abs=1e-3)


def test_beams_travel_at_one_constant_speed(proj):
    res = R.apply(proj, "scatter_trigger", options=dict(scatters=SC, beam_speed=1500))
    for i, (x, y, _) in enumerate(SC):
        d = math.hypot(x, y)
        assert res["arrivals"][i] - res["fires"][i] == pytest.approx(d / 1500, abs=2e-4), "arrival = fire + distance / speed"
        head = [b for b in proj.data.animations["fx_scatter_trigger"].bones if b.endswith(f"_s{i}_head")][0]
        t, hx, hy = _tl(proj, "fx_scatter_trigger", head, "translate", 0.0)
        go = (t >= res["fires"][i]) & (t <= res["arrivals"][i])
        r = np.hypot(hx[go], hy[go])
        v = np.diff(r) / np.diff(t[go])
        assert np.allclose(v, 1500, rtol=0.02), "the beam front is light: constant speed"
        assert np.hypot(hx[-1], hy[-1]) == pytest.approx(d, abs=0.5), "and it ends at the centre"


def test_centre_charges_like_a_capacitor_then_bursts(proj):
    tau = 0.12
    res = R.apply(proj, "scatter_trigger", options=dict(scatters=SC, charge_tau=tau))
    glow = [s for s in res["slots"] if s.endswith("_c_glow")][0]
    t, a = _alpha(proj, "fx_scatter_trigger", glow)
    arr = sorted(res["arrivals"])
    Q = lambda u: sum(1 - math.exp(-(u - x) / tau) for x in arr if u > x) / 3  # noqa: E731
    for u in (arr[0] + 0.08, arr[1] - 0.005, arr[1] + 0.2, arr[2] + 0.06):
        assert np.interp(u, t, a) == pytest.approx(0.15 + 0.65 * Q(u), abs=0.02)
    T = res["trigger_at"]
    assert np.interp(T + 0.03, t, a) > np.interp(T - 0.01, t, a) + 0.3, "the discharge flash"
    assert a[-1] == 0


def test_too_few_scatters_only_ring(proj):
    res = R.apply(proj, "scatter_trigger", options=dict(scatters=SC[:2], need=3))
    assert not res["triggered"] and "trigger_at" not in res
    assert len(_events(proj, "fx_scatter_trigger", "fx_scatter_land")) == 2
    assert not _events(proj, "fx_scatter_trigger", "fx_scatter_lock") and not _events(proj, "fx_scatter_trigger", "fx_scatter_bonus")
    assert not [s for s in res["slots"] if "_beam" in s or "_ret" in s]


def test_scatter_land_ring_is_a_spring_with_exact_overshoot(proj):
    res = R.apply(proj, "scatter_trigger", options=dict(scatters=[[0, 0, 0.5]], need=1, lock_delay=1.0))
    rune = [b for b in proj.data.animations["fx_scatter_trigger"].bones if b.endswith("_s0_rune")][0]
    t, sx, _ = _tl(proj, "fx_scatter_trigger", rune, "scale", 1.0)
    pre = t < res["locks"][0] - 0.25
    assert sx[pre].max() == pytest.approx(0.2 + 0.8 * 1.22, abs=0.01), "22% overshoot of the step"


def test_scatter_bad_options(proj):
    with pytest.raises(ValueError, match="scatter"):
        R.apply(proj, "scatter_trigger", options=dict(scatters=[[1, 2]]))
    with pytest.raises(ValueError, match="centre"):
        R.apply(proj, "scatter_trigger", options=dict(centre=[1]))
    with pytest.raises(ValueError, match="need"):
        R.apply(proj, "scatter_trigger", options=dict(need=0))
    with pytest.raises(ValueError, match="land_time"):
        R.apply(proj, "scatter_trigger", options=dict(scatters=[[0, 0, -1]]))


# ---------------------------------------------------------------- free_spins_transition
def test_free_spins_infall_is_exponential_and_conserves_angular_momentum(proj):
    res = R.apply(proj, "free_spins_transition", options=dict(pull_at=0.35, pull=0.9, tau=0.28, core=0.1, swirl=720))
    pb = res["pull_bone"]
    t, sx, sy = _tl(proj, "fx_free_spins_transition", pb, "scale", 1.0)
    p0, T_in = res["pull_from"], res["in_at"]
    assert T_in == pytest.approx(1.25) and np.interp(T_in, t, sx) == pytest.approx(0, abs=1e-3)
    q = (t > p0 + 0.2) & (t < T_in - 0.05)                 # (keys hold 3 decimals: skip where 1 - s is tiny)
    k = (1 - sx[q]) / (np.exp((t[q] - p0) / 0.28) - 1)
    assert np.allclose(k, k.mean(), rtol=0.01), "1 - s grows like e^(t/tau) - 1: an accelerating infall"
    tr, rot = _tl(proj, "fx_free_spins_transition", pb, "rotate", 0.0)
    m = (tr > p0) & (tr <= T_in)
    tm, rm = tr[m], rot[m]
    w = np.diff(rm) / np.diff(tm)
    s_mid = np.interp((tm[1:] + tm[:-1]) / 2, t, sx)
    L = w * (s_mid + 0.1) ** 2
    good = np.diff(tm) > 0.004
    assert np.allclose(L[good], L[good].mean(), rtol=0.04), "omega (s + core)^2 is conserved"
    assert abs(w[-1]) > 20 * abs(w[0]), "it whips round as it shrinks"
    assert np.interp(T_in, tr, rot) == pytest.approx(-720, abs=1), "clockwise, `swirl` degrees in all"
    assert [e.time for e in _events(proj, "fx_free_spins_transition", "fx_free_spins_in")] == [T_in]
    assert [e.time for e in _events(proj, "fx_free_spins_transition", "fx_free_spins_out")] == [res["out_at"]]


def test_free_spins_screen_springs_back_and_ends_on_rest(proj):
    res = R.apply(proj, "free_spins_transition", options=dict(overshoot=0.14))
    t, sx, _ = _tl(proj, "fx_free_spins_transition", res["pull_bone"], "scale", 1.0)
    tr, rot = _tl(proj, "fx_free_spins_transition", res["pull_bone"], "rotate", 0.0)
    gone = (t > res["in_at"]) & (t < res["out_at"])
    assert np.all(sx[gone] == 0), "the swap happens while the screen is gone"
    assert sx[t > res["out_at"]].max() == pytest.approx(1.14, abs=0.005), "emerges with the exact overshoot"
    assert (sx[-1], rot[-1]) == (1, 0) and t[-1] == pytest.approx(res["duration"]), "ends on rest: the next screen starts clean"


def test_free_spins_portal_goes_behind_the_screen_and_the_puff_in_front(game):
    res = R.apply(game, "free_spins_transition", x=0, y=10, options=dict(screen="machine"))
    sk = game.data
    order = [s.name for s in sk.slots]
    pa, pz = res["portal_run"]
    qa_, qz = res["puff_run"]
    assert order.index("backdrop") < order.index(pa) < order.index(pz) < order.index("reelbg"), "portal behind the screen"
    assert order.index("cabinet") < order.index(qa_) < order.index(qz), "puff in front of the screen"
    for a, z in (res["portal_run"], res["puff_run"]):
        run = [sk.slot(s).blend for s in order[order.index(a):order.index(z) + 1]]
        assert run == sorted(run, key=lambda b: b != "normal"), "each run: normal first, then the light"
    car = res["pull_bone"]
    assert sk.bone("machine").parent == car and (sk.world()[car].x, sk.world()[car].y) == pytest.approx((0, 10))
    assert res["ae_hint"]["parent"].endswith("_portal") and "portal_ring" in res["ae_hint"]["note"]
    assert "smoke_haze" in res["smoke_hint"]["note"] and res["smoke_hint"]["start"] == res["out_at"]
    assert qa.validate(sk)["ok"]


def test_free_spins_merge_adds_to_earlier_spins_on_the_same_carrier(game):
    a = R.apply(game, "free_spins_transition", into="two", options=dict(screen="machine"))
    b = R.apply(game, "free_spins_transition", start=3.0, into="two", name="again", options=dict(screen="machine"))
    assert a["pull_bone"] == b["pull_bone"]
    t, rot = _tl(game, "two", a["pull_bone"], "rotate", 0.0)
    assert np.interp(1.25, t, rot) == pytest.approx(-720, abs=1) and np.interp(4.25, t, rot) == pytest.approx(-720, abs=1)
    assert rot[-1] == 0


def test_free_spins_bad_options(proj, game):
    with pytest.raises(ValueError, match="root"):
        R.apply(game, "free_spins_transition", options=dict(screen="root"))
    with pytest.raises(ValueError, match="tau"):
        R.apply(proj, "free_spins_transition", options=dict(tau=0))
    with pytest.raises(ValueError, match="gap"):
        R.apply(proj, "free_spins_transition", options=dict(gap=0))
    with pytest.raises(ValueError, match="overshoot"):
        R.apply(proj, "free_spins_transition", options=dict(overshoot=1.5))


def test_art_roles_swap_pictures(proj, tmp_path):
    from PIL import Image
    f = tmp_path / "star.png"
    Image.new("RGBA", (64, 64), (255, 0, 0, 255)).save(f)
    res = R.apply(proj, "scatter_trigger", art={"rune": str(f)})
    assert res["art"] == {"rune": "fx/art_scatter_trigger_rune"}
    with pytest.raises(ValueError, match="art role"):
        R.apply(proj, "wild_land", art={"nope": str(f)})
    assert fx_features.tex_surface().size == (64, 256)
