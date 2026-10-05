"""Win presentation: payline (comet along the line), win_highlight (per-symbol frame, burst, pop, sheen),
multiplier_stack (badges fly into the total), win_rollup (coins in, tick pops, glow by tier)."""
import math

import numpy as np
import pytest

from claude_spine import fx_recipes as R, fx_wins as Wn, qa, runtime
from claude_spine.ir import Bone, new_skeleton
from claude_spine.project import Project
from claude_spine.timeline import AnimBuilder
from conftest import needs_node

WINS = ("payline", "win_highlight", "multiplier_stack", "win_rollup")


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


def _xy(keys, rest):
    t = np.array([k.time for k in keys])
    v = lambda k, f: rest if getattr(k, f, None) is None else float(getattr(k, f))  # noqa: E731
    return t, np.array([v(k, "x") for k in keys]), np.array([v(k, "y") for k in keys])


def _alpha(keys):
    return np.array([k.time for k in keys]), np.array([int(k.color[6:8], 16) / 255 for k in keys])


def _events(p, anim, name):
    return [(e.time, getattr(e, "int", 0), getattr(e, "string", "")) for e in p.data.animations[anim].events if e.name == name]


def _slot_of(p, bone):
    return [s.name for s in p.data.slots if s.bone == bone][0]


# ---------------------------------------------------------------- shared rules
@pytest.mark.parametrize("rec", WINS)
def test_every_win_recipe_builds_validates_and_hides_its_slots(proj, rec):
    res = R.apply(proj, rec)
    sk = proj.data
    assert qa.validate(sk)["ok"]
    assert res["slots"] and all(sk.slot(s).attachment is None for s in res["slots"]), "nothing shows in the setup pose"
    blends = [sk.slot(s).blend for s in res["slots"]]
    assert blends == sorted(blends, key=lambda b: b != "normal"), "normal-blend layers (coins) lead the run"
    assert set(blends) <= ({"additive", "normal"} if rec == "win_rollup" else {"additive"})
    assert qa.budget(sk, "desktop")["metrics"]["draw_calls"] <= 2
    assert any(e.name == f"fx_{rec}" for e in sk.animations[res["animation"]].events)
    d = R.RECIPES[rec]
    assert d["roles"] and set(d["tiers"]) == {"small", "big", "mega", "epic"}
    for tier, over in d["tiers"].items():
        assert set(over) <= set(d["options"]), f"{rec} tier {tier} overrides unknown options"
    assert all(s.startswith("fx/") for s in {a.path for sl in res["slots"] for a in sk.skin("default").attachments[sl].values()})


@pytest.mark.parametrize("rec", WINS)
def test_tiers_build(proj, rec):
    for tier, over in R.RECIPES[rec]["tiers"].items():
        R.apply(proj, rec, name=f"{rec}_{tier}", options=dict(over))
    assert qa.validate(proj.data)["ok"]


def test_start_and_into_shift_and_merge(proj):
    AnimBuilder(proj.data, "win").event(0.0, "spin_done")
    res = R.apply(proj, "payline", start=1.5, into="win")
    ev = _events(proj, "win", "fx_payline_hit")
    assert ev[0][0] == pytest.approx(1.5) and res["hit_times"][0] == pytest.approx(1.5)
    assert any(e.name == "spin_done" for e in proj.data.animations["win"].events)


# ---------------------------------------------------------------- payline
def test_payline_head_runs_at_constant_speed_by_arc_length_after_an_eased_start(proj):
    pts = [[-300, 0], [-100, 150], [0, 150], [300, -100]]       # hops of very different lengths
    R.apply(proj, "payline", options=dict(points=pts, speed=1000, ease=0.2))
    t, x, y = _xy(proj.data.animations["fx_payline"].bones["fx_payline_l0_head"]["translate"], 0.0)
    L = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    T = L / 1000 + 0.1
    v = np.hypot(np.diff(x), np.diff(y)) / np.diff(t)
    tm = (t[1:] + t[:-1]) / 2
    cruise = v[(tm > 0.22) & (tm < T - 0.02)]
    assert cruise.min() == pytest.approx(1000, rel=0.03) and cruise.max() == pytest.approx(1000, rel=0.03)
    assert v[0] < 150, "starts from rest"
    early = v[tm < 0.2]
    assert np.all(np.diff(early) > 0), "speed ramps up during the ease"
    assert (x[-1], y[-1]) == pytest.approx((300, -100)) and t[-1] >= T


def test_payline_hit_events_at_each_symbol_with_its_index(proj):
    pts = [[-320, 160], [-160, 0], [0, -160], [160, 0], [320, 160]]
    res = R.apply(proj, "payline", options=dict(points=pts, speed=800, ease=0.1))
    ev = _events(proj, "fx_payline", "fx_payline_hit")
    seg = math.hypot(160, 160)
    want = [0.0] + [(k * seg) / 800 + 0.05 for k in range(1, 5)]
    assert [e[0] for e in ev] == pytest.approx(want, abs=2e-4)
    assert [e[1] for e in ev] == [0, 1, 2, 3, 4] and {e[2] for e in ev} == {"line0"}
    end = _events(proj, "fx_payline", "fx_payline_end")
    assert len(end) == 1 and end[0][0] == pytest.approx(want[-1], abs=2e-4)
    assert [v for h in res["hits"] for v in h[:2]] == pytest.approx([float(v) for p_ in pts for v in p_])
    # the head passes exactly through each symbol centre at its hit time
    t, x, y = _xy(proj.data.animations["fx_payline"].bones["fx_payline_l0_head"]["translate"], 0.0)
    for (px, py), tt in zip(pts, want):
        assert (np.interp(tt, t, x), np.interp(tt, t, y)) == pytest.approx((px, py), abs=0.5)


def test_payline_tail_is_the_heads_past(proj):
    R.apply(proj, "payline", options=dict(points=[[-400, 0], [400, 0]], speed=1000, ease=0.1, tail=0.15))
    a = proj.data.animations["fx_payline"]
    th, xh, _ = _xy(a.bones["fx_payline_l0_head"]["translate"], 0.0)
    tt, xt, _ = _xy(a.bones["fx_payline_l0_tail_n0"]["translate"], 0.0)      # bottom row = the tail end
    for q in (0.3, 0.5, 0.7):
        assert np.interp(q, tt, xt) == pytest.approx(np.interp(q - 0.15, th, xh), abs=1.0)
    assert np.interp(0.5, th, xh) - np.interp(0.5, tt, xt) == pytest.approx(150, abs=2), "tail length = speed x lag"


def test_payline_glow_line_decays_after_the_head_leaves_and_ends_dark(proj):
    res = R.apply(proj, "payline", options=dict(points=[[-300, 0], [0, 0], [300, 0]], speed=1000, ease=0.0, linger=0.9))
    a = proj.data.animations["fx_payline"]
    s0 = _slot_of(proj, "fx_payline_l0_g0")
    t, al = _alpha(a.slots[s0]["rgba"])
    tb = 0.3                                                    # the head leaves the first hop
    assert np.interp(tb, t, al) == pytest.approx(0.8, abs=0.02)
    q = 0.2
    assert np.interp(tb + q * 0.9, t, al) == pytest.approx(0.8 * math.exp(-3 * q), abs=0.02), "phosphor decay e^-3t/linger"
    assert al[-1] == 0
    s1 = _slot_of(proj, "fx_payline_l0_g1")
    t1, al1 = _alpha(a.slots[s1]["rgba"])
    assert np.interp(0.9, t1, al1) > np.interp(0.9, t, al), "the line fades from its start first"
    _, sx, _ = _xy(a.bones["fx_payline_l0_g0"]["scale"], 1.0)
    assert sx[-1] == pytest.approx(1.0) and sx.min() < 0.2, "drawn out by the head"
    assert res["duration"] == pytest.approx(0.6 + 0.9, abs=0.01)


def test_payline_sparks_fly_with_drag_and_fall(proj):
    R.apply(proj, "payline", options=dict(points=[[-200, 0], [200, 0]], sparks=4))
    a = proj.data.animations["fx_payline"]
    sparks = [b for b in a.bones if b.startswith("fx_payline_l0_s0_")]
    assert len(sparks) == 4
    for b in sparks:
        t, x, y = _xy(a.bones[b]["translate"], 0.0)
        v = np.hypot(np.diff(x), np.diff(y)) / np.diff(t)
        vy = np.diff(y) / np.diff(t)
        assert vy[-1] < 0, "gravity wins: every spark ends falling (at its terminal speed g/k)"
        assert np.hypot(np.diff(x), 0)[-1] / np.diff(t)[-1] < np.abs(np.diff(x)[0] / np.diff(t)[0]) + 1e-6, "drag slows them sideways"
        assert v[0] > 100


def test_payline_several_lines_are_staggered(proj):
    lines = [[[-200, 0], [200, 0]], [[-200, 100], [200, 100]], [[-200, -100], [200, -100]]]
    res = R.apply(proj, "payline", options=dict(lines=lines, stagger=0.4, colors=["FFD25A", "FF60C0"]))
    ends = _events(proj, "fx_payline", "fx_payline_end")
    assert [e[1] for e in ends] == [0, 1, 2]
    assert np.diff([e[0] for e in ends]) == pytest.approx([0.4, 0.4], abs=1e-3)
    assert [ln["start"] for ln in res["lines"]] == pytest.approx([0, 0.4, 0.8])
    assert {e[2] for e in _events(proj, "fx_payline", "fx_payline_hit")} == {"line0", "line1", "line2"}
    assert len(res["hits"]) == 6


def test_payline_bad_inputs_are_clear_errors(proj):
    with pytest.raises(ValueError, match="speed"):
        R.apply(proj, "payline", options=dict(speed=0))
    with pytest.raises(ValueError, match="at least 2"):
        R.apply(proj, "payline", options=dict(points=[[0, 0]]))
    with pytest.raises(ValueError, match="coincide"):
        R.apply(proj, "payline", options=dict(points=[[0, 0], [0, 0], [100, 0]]))
    with pytest.raises(ValueError, match="pairs"):
        R.apply(proj, "payline", options=dict(points=[[0, 0], "x"]))


# ---------------------------------------------------------------- win_highlight
def test_win_highlight_pop_overshoots_exactly_and_settles(proj):
    R.apply(proj, "win_highlight", options=dict(hit=0.3, pop=0.15, bounce=6, damping=0.4))
    t, sx, sy = _xy(proj.data.animations["fx_win_highlight"].bones["fx_win_highlight_cell0"]["scale"], 1.0)
    assert sx.max() == pytest.approx(1.15, abs=0.002), "first overshoot is exactly pop"
    w0 = 2 * math.pi * 6
    wd = w0 * math.sqrt(1 - 0.16)
    tp = math.atan2(wd, 0.4 * w0) / wd
    assert t[np.argmax(sx)] == pytest.approx(0.3 + tp, abs=0.012)
    assert sx.min() < 0.99, "underdamped: it rebounds below rest"
    assert sx[-1] == 1 and sy[-1] == 1 and t[-1] == pytest.approx(2.4)


def test_win_highlight_cells_light_at_their_times_with_burst_and_sheen(proj):
    cells = [[-150, 0, 130, 130, 0.2], [0, 0, 130, 130, 0.5], [150, 0, 100, 160, 0.8]]
    res = R.apply(proj, "win_highlight", options=dict(cells=cells, sheen_period=0.6, sheen_time=0.4))
    ev = _events(proj, "fx_win_highlight", "fx_win_highlight_hit")
    assert [e[0] for e in ev] == pytest.approx([0.2, 0.5, 0.8]) and [e[1] for e in ev] == [0, 1, 2]
    for sw, (*_, th) in zip(res["sweeps"], cells):
        assert sw[0] == pytest.approx(th + 0.12) and np.allclose(np.diff(sw), 0.6)
        assert sw[-1] + 0.4 <= 2.4 - 0.15 + 1e-6
    a = proj.data.animations["fx_win_highlight"]
    frame = _slot_of(proj, "fx_win_highlight_c1_frame")
    att = a.slots[frame]["attachment"]
    assert [(k.time, k.name) for k in att] == [(0.0, None), (0.5, "fx"), (2.4, None)]
    core = _slot_of(proj, "fx_win_highlight_c1_core")
    t, al = _alpha(a.slots[core]["rgba"])
    pk = t[np.argmax(al)]
    assert 0.5 < pk <= 0.56, "the burst blooms at the hit"
    assert np.interp(pk + 0.3, t, al) < 0.45 * al.max(), "and decays like 1/t"
    # sheen flipbook: pre-masked, empty first and last frames
    sh = _slot_of(proj, "fx_win_highlight_cell2")
    seq = proj.data.skin("default").attachments[sh]["fx"]
    assert seq.sequence.count == 14 and seq.width == 100 and seq.height == 160
    keys = a.attachments["default"][sh]["fx"]["sequence"]
    assert [k.time for k in keys] == pytest.approx(res["sweeps"][2])


def test_sheen_frames_stay_inside_the_cell():
    fr = Wn.sheen_frames(64, 96, 14)
    al = [np.asarray(f)[..., 3] for f in fr]
    assert al[0].max() == 0 and al[-1].max() == 0
    assert max(a.max() for a in al) > 150
    for a in al:
        assert a[:3].max() == 0 and a[-3:].max() == 0 and a[:, :2].max() == 0 and a[:, -2:].max() == 0
    cx = [np.average(np.nonzero(a)[1]) for a in al[2:-2] if a.any()]
    assert cx == sorted(cx), "the band travels one way"


def test_win_highlight_pops_the_game_symbol_through_a_carrier(proj):
    sk = proj.data
    sk.bones.append(Bone(name="sym0", parent="root", x=-150, y=0))
    AnimBuilder(sk, "win", replace=False).bone("sym0", "rotate", [(0, 0), (0.4, 8)])
    res = R.apply(proj, "win_highlight", x=-150, into="win", options=dict(hit=0.1, pop=0.1, symbols=["sym0"]))
    car = res["symbol_carriers"][0]
    assert sk.bone("sym0").parent == car
    assert [k.time for k in sk.animations["win"].bones["sym0"]["rotate"]] == [0, 0.4], "the artist's keys are untouched"
    _, sx, _ = _xy(sk.animations["win"].bones[car]["scale"], 1.0)
    assert sx.max() == pytest.approx(1.1, abs=0.002) and sx[-1] == 1
    assert qa.validate(sk)["ok"]


def test_win_highlight_bad_inputs_are_clear_errors(proj):
    with pytest.raises(ValueError, match="damping"):
        R.apply(proj, "win_highlight", options=dict(damping=1.2))
    with pytest.raises(ValueError, match="duration"):
        R.apply(proj, "win_highlight", options=dict(hit=3.0))
    with pytest.raises(ValueError, match="cells"):
        R.apply(proj, "win_highlight", options=dict(cells=[[0, 0, 100]]))
    with pytest.raises(ValueError, match="symbols"):
        R.apply(proj, "win_highlight", options=dict(symbols=["a", "b"]))


# ---------------------------------------------------------------- multiplier_stack
def test_multiplier_badges_fly_ballistic_parabolas(proj):
    res = R.apply(proj, "multiplier_stack", options=dict(sources=[[-250, -100], [250, -120]], target=[0, 200], flight=0.5, arc=80))
    a = proj.data.animations["fx_multiplier_stack"]
    for i, (bb, (sx, sy)) in enumerate(zip(res["badge_bones"], [(-250, -100), (250, -120)])):
        assert (proj.data.bone(bb).x, proj.data.bone(bb).y) == (sx, sy), "badge bones start at their sources"
        t, x, y = _xy(a.bones[bb]["translate"], 0.0)
        fl = t <= res["hits"][i] + 1e-6
        t, x, y = t[fl], x[fl], y[fl]
        assert np.allclose(np.diff(t), np.diff(t)[0], atol=2e-4)
        ax, ay = np.diff(x, 2), np.diff(y, 2)
        assert np.ptp(ax) < 0.05 and np.ptp(ay) < 0.05, "constant acceleration: a parabola"
        assert ay.mean() < 0, "the arc bows up and falls into the total"
        assert (sx + x[-1], sy + y[-1]) == pytest.approx((0, 200), abs=0.5)
        _, bsx, _ = _xy(a.bones[bb]["scale"], 1.0)
        assert bsx[-1] == 0, "absorbed into the total"


def test_multiplier_total_pops_with_exact_overshoot_and_kicks_superpose(proj):
    one = R.apply(proj, "multiplier_stack", name="one", options=dict(sources=[[0, -200]], pop=0.2, bounce=5, damping=0.35))
    t1, s1, _ = _xy(proj.data.animations["fx_one"].bones[one["total_bone"]]["scale"], 1.0)
    assert s1.max() == pytest.approx(1.2, abs=0.002) and s1[-1] == 1
    two = R.apply(proj, "multiplier_stack", name="two", options=dict(sources=[[0, -200], [100, -200]], stagger=0.15, pop=0.2, growth=0.5,
                                                                    bounce=5, damping=0.35))
    t2, s2, _ = _xy(proj.data.animations["fx_two"].bones[two["total_bone"]]["scale"], 1.0)
    h0, h1 = two["hits"]
    up = Wn._up(5, 0.35)
    for q in (h1 + 0.03, h1 + 0.1, h1 + 0.2):
        want = 1 + 0.2 * up(q - h0) + 0.3 * up(q - h1)
        assert np.interp(q, t2, s2) == pytest.approx(want, abs=0.004), "a linear spring is the sum of its kicks"
    assert [e[1] for e in _events(proj, "fx_two", "fx_multiplier_hit")] == [0, 1]
    assert [e[0] for e in _events(proj, "fx_two", "fx_multiplier_hit")] == pytest.approx(two["hits"])
    assert _events(proj, "fx_two", "fx_multiplier_total")[0][0] == pytest.approx(h1)
    assert [e[0] for e in _events(proj, "fx_two", "fx_multiplier_launch")] == pytest.approx([0.0, 0.15])


def test_multiplier_rings_grow_like_sedov(proj):
    R.apply(proj, "multiplier_stack", options=dict(sources=[[0, -200]], flight=0.5))
    t, sx, _ = _xy(proj.data.animations["fx_multiplier_stack"].bones["fx_multiplier_stack_hr0"]["scale"], 1.0)
    r = lambda q: np.interp(0.5 + q, t, sx) - 0.12  # noqa: E731
    assert r(0.2) / r(0.05) == pytest.approx(4 ** 0.4, rel=0.03), "r ~ t^0.4"


def test_multiplier_total_carrier_pops_the_game_bone(proj):
    sk = proj.data
    sk.bones.append(Bone(name="hud", parent="root"))
    sk.bones.append(Bone(name="total_txt", parent="hud", x=0, y=170))
    res = R.apply(proj, "multiplier_stack", options=dict(total="total_txt"))
    assert sk.bone("total_txt").parent == res["total_bone"] and sk.bone(res["total_bone"]).parent == "hud"
    w = sk.world()
    assert (w["total_txt"].x, w["total_txt"].y) == pytest.approx((0, 170))
    with pytest.raises(ValueError, match="root"):
        R.apply(proj, "multiplier_stack", options=dict(total="root"))


def test_multiplier_bad_inputs_are_clear_errors(proj):
    with pytest.raises(ValueError, match="sources"):
        R.apply(proj, "multiplier_stack", options=dict(sources=[]))
    with pytest.raises(ValueError, match="target"):
        R.apply(proj, "multiplier_stack", options=dict(target=5))
    with pytest.raises(ValueError, match="flight"):
        R.apply(proj, "multiplier_stack", options=dict(flight=0))


# ---------------------------------------------------------------- win_rollup
def test_rollup_ticks_at_the_rate_and_ends_with_an_exact_pop(proj):
    res = R.apply(proj, "win_rollup", duration=3.0, options=dict(rate=10, settle=1.0, end_pop=0.3, tick_pop=0.03))
    ticks = _events(proj, "fx_win_rollup", "fx_rollup_tick")
    assert len(ticks) == 20 and [e[1] for e in ticks] == list(range(20))
    assert np.allclose(np.diff([e[0] for e in ticks]), 0.1)
    end = _events(proj, "fx_win_rollup", "fx_rollup_end")
    assert end[0][0] == pytest.approx(2.0) and res["end_at"] == pytest.approx(2.0)
    t, sx, _ = _xy(proj.data.animations["fx_win_rollup"].bones[res["counter_bone"]]["scale"], 1.0)
    after = t > 2.0
    assert sx[after].max() == pytest.approx(1.3, abs=0.005), "the landing pop overshoots by exactly end_pop"
    during = (t > 0.5) & (t < 1.9)
    assert 1.01 < sx[during].max() < 1.06, "a small pop on every tick"
    for tt in (0.5, 1.0, 1.5):
        i0 = np.searchsorted(t, tt)
        win = (t >= tt) & (t < tt + 0.1)
        assert sx[win].max() > sx[i0] + 0.01, "each tick kicks the counter up"
    assert sx[-1] == 1 and t[-1] == pytest.approx(3.0)


def test_rollup_coins_fall_in_from_rest_accelerating(proj):
    res = R.apply(proj, "win_rollup", count=10, options=dict(spread=300))
    assert res["coins"] == 10
    a = proj.data.animations["fx_win_rollup"]
    for i in range(10):
        b = f"fx_win_rollup_coin{i}"
        t, x, y = _xy(a.bones[b]["translate"], 0.0)
        v = np.hypot(np.diff(x), np.diff(y)) / np.diff(t)
        assert np.all(np.diff(v) > -1e-6), "speed only grows"
        assert v[0] < 0.1 * v[-1], "starts from rest"
        assert math.hypot(x[0], y[0]) > 150 and (x[-1], y[-1]) == pytest.approx((0, 0), abs=1e-6), "ends in the counter"
        assert t[-1] <= res["end_at"] + 1e-6
    _, sx, _ = _xy(a.bones["fx_win_rollup_coin0"]["scale"], 1.0)
    assert sx.min() < 0 < sx.max(), "the coin spins (x scale through zero)"


def test_rollup_glow_intensifies_with_the_count_and_the_tier(proj):
    tiers = R.RECIPES["win_rollup"]["tiers"]
    lo = R.apply(proj, "win_rollup", name="lo", options=dict(tiers["small"]))
    hi = R.apply(proj, "win_rollup", name="hi", options=dict(tiers["mega"]))
    def under(res, anim):
        s = [x for x in res["slots"] if "_under" in x][0]
        return _alpha(proj.data.animations[anim].slots[s]["rgba"])
    t, a = under(lo, "fx_lo")
    t2, a2 = under(hi, "fx_hi")
    assert np.interp(0.4, t, a) < np.interp(2.0, t, a), "brighter as the count climbs"
    assert np.interp(1.5, t2, a2) > 1.5 * np.interp(1.5, t, a), "a mega win glows harder than a small one"
    assert hi["coins"] > lo["coins"] and hi["ticks"] > lo["ticks"]
    assert a[-1] == 0 and a2[-1] == 0


def test_rollup_counter_carrier_keeps_the_artist_keys(proj):
    sk = proj.data
    sk.bones.append(Bone(name="hud", parent="root", y=-300))
    sk.bones.append(Bone(name="win_text", parent="hud"))
    AnimBuilder(sk, "win", replace=False).bone("win_text", "scale", [(0, 1, 1), (2, 1.1, 1.1)])
    res = R.apply(proj, "win_rollup", y=-300, into="win", options=dict(counter="win_text"))
    car = res["counter_bone"]
    assert sk.bone("win_text").parent == car
    assert [k.time for k in sk.animations["win"].bones["win_text"]["scale"]] == [0, 2]
    again = R.apply(proj, "win_rollup", y=-300, into="win", start=3.2, options=dict(counter="win_text"))
    assert again["counter_bone"] == car, "a second rollup reuses the carrier"
    assert qa.validate(sk)["ok"]


def test_rollup_bad_inputs_are_clear_errors(proj):
    with pytest.raises(ValueError, match="rate"):
        R.apply(proj, "win_rollup", options=dict(rate=0))
    with pytest.raises(ValueError, match="settle"):
        R.apply(proj, "win_rollup", duration=1.0, options=dict(settle=0.9))
    with pytest.raises(ValueError, match="no bone"):
        R.apply(proj, "win_rollup", options=dict(counter="nope"))
    with pytest.raises(ValueError, match="unknown option"):
        R.apply(proj, "win_rollup", options=dict(tier="mega"))


# ---------------------------------------------------------------- runtime
@needs_node
def test_a_whole_win_plays_in_the_spine_core_runtime(proj):
    pl = R.apply(proj, "payline", into="win", options=dict(lines=[[[-280, 140], [-140, 0], [0, -140], [140, 0], [280, 140]],
                                                                  [[-280, 0], [280, 0]]], stagger=0.6))
    R.apply(proj, "win_highlight", into="win", duration=4.0, options=dict(cells=[[x, y, 120, 120, t] for x, y, t in pl["hits"]]))
    R.apply(proj, "multiplier_stack", start=2.0, into="win")
    R.apply(proj, "win_rollup", y=-280, start=2.6, duration=2.5, into="win", options=dict(R.RECIPES["win_rollup"]["tiers"]["big"]))
    assert qa.validate(proj.data)["ok"]
    proj.save()
    dump = runtime.run(proj, animations=["win"], fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    an = dump["animations"]["win"]
    assert an["duration"] == pytest.approx(5.1, abs=0.01)
    names = {e["name"] for e in (an.get("events") or dump.get("events") or [])}
    assert {"fx_payline_hit", "fx_payline_end", "fx_win_highlight_hit", "fx_multiplier_hit", "fx_multiplier_total",
            "fx_rollup_tick", "fx_rollup_end"} <= names
