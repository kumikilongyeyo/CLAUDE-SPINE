"""Spin moments: near_miss (approach-lit halo, implosion), spin_blur (lagging, speed-stretched streaks), turbo_spin
(speed lines + travelling grid ripple through carriers) and screen_shake (damped two-axis spring, 1/t flash, chromatic
split converging)."""
import math

import numpy as np
import pytest

from claude_spine import fx_recipes as R, fx_spin, qa, runtime  # noqa: F401  (fx_spin registers its recipes)
from claude_spine.ir import Bone, new_skeleton
from claude_spine.project import Project
from conftest import needs_node

SPIN = ["near_miss", "spin_blur", "turbo_spin", "screen_shake"]


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


@pytest.fixture
def grid(tmp_path):
    """Three reels under a 'reels' container, 162 apart, each with three symbol bones 150 apart."""
    p = Project(tmp_path / "g.json", new_skeleton("g", 720, 720))
    p.data.bones.append(Bone(name="reels", parent="root", y=20))
    for i in range(3):
        p.data.bones.append(Bone(name=f"reel{i}", parent="reels", x=(i - 1) * 162))
        for j in range(3):
            p.data.bones.append(Bone(name=f"s{i}{j}", parent=f"reel{i}", y=150 - 150 * j))
    return p


def _xy(keys, rest):
    t = np.array([k.time for k in keys])
    v = lambda k, f: rest if getattr(k, f, None) is None else float(getattr(k, f))  # noqa: E731
    return t, np.array([v(k, "x") for k in keys]), np.array([v(k, "y") for k in keys])


def _alpha(keys):
    return np.array([k.time for k in keys]), np.array([int(k.color[6:8], 16) / 255 for k in keys])


def _val(keys, f, rest=0.0):
    return np.array([k.time for k in keys]), np.array([rest if getattr(k, f, None) is None else float(getattr(k, f)) for k in keys])


# ---------------------------------------------------------------- shared contract
@pytest.mark.parametrize("name", SPIN)
def test_each_spin_recipe_builds_validates_is_additive_and_hidden(proj, name):
    res = R.apply(proj, name)
    assert res["animation"] == f"fx_{name}" and res["slots"] and res["event"] == f"fx_{name}"
    assert all(s.blend == "additive" for s in proj.data.slots), "light only: one additive batch"
    assert all(s.attachment is None for s in proj.data.slots), "FX slots must be hidden in the setup pose"
    v = qa.validate(proj.data)
    assert v["ok"], v["errors"]
    assert qa.budget(proj.data, "desktop")["metrics"]["draw_calls"] == 1
    assert set(R.RECIPES[name]["roles"]) and name in R.list_recipes()
    ev = [e.name for e in proj.data.animations[f"fx_{name}"].events]
    assert f"fx_{name}" in ev


@needs_node
@pytest.mark.parametrize("name", SPIN)
def test_each_spin_recipe_plays_in_the_spine_core_runtime(proj, name):
    res = R.apply(proj, name)
    proj.save()
    dump = runtime.run(proj, animations=[res["animation"]], fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    assert dump["animations"][res["animation"]]["frames"]


@needs_node
def test_a_spin_clip_with_all_four_and_reel_stop_plays(grid):
    sym = [f"s{i}{j}" for i in range(3) for j in range(3)]
    R.apply(grid, "turbo_spin", y=20, duration=2.0, into="spin", options=dict(bones=sym))
    for i in range(3):
        R.apply(grid, "spin_blur", x=(i - 1) * 162, y=20, start=0.3, into="spin", options=dict(stop=0.8 + 0.3 * i))
        R.apply(grid, "reel_stop", x=(i - 1) * 162, y=20, start=1.1 + 0.3 * i, into="spin", options=dict(reel=f"reel{i}", shake="reels"))
    R.apply(grid, "screen_shake", start=1.4, into="spin", options=dict(R.RECIPES["screen_shake"]["tiers"]["big"], shake="reels"))
    R.apply(grid, "near_miss", start=1.4, into="spin", parent="s20", options=dict(follow=False))
    assert qa.validate(grid.data)["ok"]
    grid.save()
    dump = runtime.run(grid, animations=["spin"], fps=20, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")


# ---------------------------------------------------------------- near_miss
def test_near_miss_brightness_follows_the_approach_distance(proj):
    res = R.apply(proj, "near_miss", options=dict(dy=330, miss=150, closest=0.55))
    a = proj.data.animations["fx_near_miss"]
    halo = res["halo_bone"]
    t, _, y = _xy(a.bones[halo]["translate"], 0.0)
    assert y[0] == pytest.approx(330) and np.interp(0.55, t, y) == pytest.approx(150, abs=0.1)
    v = -np.diff(y) / np.diff(t)
    early = v[(t[1:] > 0.02) & (t[1:] < 0.5)]
    assert np.all(np.diff(early) < 1e-6) and v[1] > 3 * v[np.searchsorted(t, 0.5)], "constant deceleration: speed falls linearly"
    glow = [s for s in res["slots"] if "_glow" in s][0]
    ta, al = _alpha(a.slots[glow]["rgba"])
    L = 75.0
    for u in (0.15, 0.3, 0.45):                               # alpha ratio = inverse-square law with softening L
        d = np.interp(u, t, y)
        want = (L * L + 150 ** 2) / (L * L + d * d)
        assert np.interp(u, ta, al) / np.interp(0.6, ta, al) == pytest.approx(want, rel=0.04)
    assert np.all(np.diff(al[(ta > 0.1) & (ta < 0.55)]) >= -0.004), "brighter every step it comes closer"


def test_near_miss_implodes_with_ease_in_spin_up_desaturation_and_falling_sparks(proj):
    res = R.apply(proj, "near_miss", options=dict(closest=0.5, fizzle=0.8))
    a = proj.data.animations["fx_near_miss"]
    tf, ti = res["fizzle_at"], res["implode_at"]
    assert (tf, ti) == (0.8, pytest.approx(1.12))
    ring_slot = [s for s in res["slots"] if "_ring" in s][0]
    rb = proj.data.slot(ring_slot).bone
    ts, sx = _val(a.bones[rb]["scale"], "x", 1.0)
    s0, sm, s1 = (np.interp(u, ts, sx) for u in (tf, (tf + ti) / 2, ti - 0.01))
    assert (s0 - sm) < (sm - s1), "ease-in: it is sucked in faster and faster"
    tr, ang = _val(a.bones[rb]["rotate"], "value")
    w = np.abs(np.diff(ang) / np.diff(tr))
    w_before, w_late = np.median(w[tr[1:] < tf]), w[np.searchsorted(tr, ti - 0.04)]
    assert w_late > 5 * w_before, "the ring spins up as it shrinks (angular momentum)"
    cols = [k.color[:6] for k in a.slots[ring_slot]["rgba"]]
    sat = lambda h: max(int(h[i:i + 2], 16) for i in (0, 2, 4)) - min(int(h[i:i + 2], 16) for i in (0, 2, 4))  # noqa: E731
    assert sat(cols[0]) > 100 and sat(cols[-1]) < 10, "the colour drains to grey"
    sparks = [b for b in a.bones if b.startswith("fx_near_miss_sp")]
    assert len(sparks) == R.RECIPES["near_miss"]["count"]
    for b in sparks:
        t, x, y = _xy(a.bones[b]["translate"], 0.0)
        assert t[0] == pytest.approx(ti)
        c2 = np.polyfit(t - ti, y, 2)[0]
        assert c2 == pytest.approx(-res["gravity"] / 2, rel=1e-3), "exact gravity parabola"
        assert np.allclose(x, np.polyval(np.polyfit(t - ti, x, 1), t - ti), atol=0.03), "no force sideways: x is linear in t"
    for s in res["slots"]:
        if s in a.slots and "rgba" in a.slots[s]:
            assert a.slots[s]["rgba"][-1].color.endswith("00"), f"{s} ends invisible"
    ev = {e.name: e.time for e in a.events}
    assert ev["fx_near_miss_closest"] == 0.5 and ev["fx_near_miss_fizzle"] == 0.8


def test_near_miss_follow_false_stays_put_and_bad_options(proj):
    res = R.apply(proj, "near_miss", options=dict(follow=False))
    assert "translate" not in proj.data.animations["fx_near_miss"].bones.get(res["halo_bone"], {})
    with pytest.raises(ValueError, match="same side"):
        R.apply(proj, "near_miss", options=dict(dy=300, miss=-150))
    with pytest.raises(ValueError, match="same side"):
        R.apply(proj, "near_miss", options=dict(dy=100, miss=150))
    with pytest.raises(ValueError, match="fizzle"):
        R.apply(proj, "near_miss", options=dict(closest=0.6, fizzle=0.4))


# ---------------------------------------------------------------- spin_blur
def _rows(sk, a, slot):
    """(times, bottom-row y, top-row y) of a streak, in the group's space."""
    nodes = sorted([b.name for b in sk.bones if b.parent == sk.slot(slot).bone and "_n" in b.name], key=lambda n: int(n.rsplit("_n", 1)[1]))
    out = []
    for nb in (nodes[0], nodes[-1]):
        t, _, y = _xy(a.bones[nb]["translate"], 0.0)
        out.append((t, y + sk.bone(nb).y))
    return out[0][0], out[0][1], out[1][1]


def test_spin_blur_stretch_follows_speed_and_the_streaks_lag_then_catch_up(proj):
    res = R.apply(proj, "spin_blur", count=5, options=dict(stop=1.2, speed=2400, lag=0.07, shutter=0.05, height=450))
    sk, a = proj.data, proj.data.animations["fx_spin_blur"]
    assert res["stop_at"] == 1.2 and res["duration"] == pytest.approx(1.62)
    s_stop = res["lag_speed_at_stop"]
    assert s_stop > 0.1 * 2400, "the streaks still move when the reel has stopped (first-order lag)"
    assert res["catch_up"] == pytest.approx(0.07 * s_stop, rel=1e-3)
    checked_cruise = checked_after = 0
    for sl in [s for s in res["slots"] if "_st" in s]:
        t, yb, yt = _rows(sk, a, sl)
        ins = (yb > -223) & (yt < 223)
        Lk = yt - yb
        for u in t[(t > 0.7) & (t < 0.8)]:
            k = np.searchsorted(t, u)
            if ins[k]:                                      # cruise: length = L0 + shutter x speed
                assert Lk[k] == pytest.approx(6 + 0.05 * 2400, abs=0.6)
                checked_cruise += 1
        k1, k2 = np.searchsorted(t, 1.25), np.searchsorted(t, 1.35)
        if ins[k1] and ins[k2]:                             # after the stop: (L - L0) decays e^(-dt/lag)
            r_ = (Lk[k2] - 6) / (Lk[k1] - 6)
            assert r_ == pytest.approx(math.exp(-(t[k2] - t[k1]) / 0.07), rel=0.03)
            checked_after += 1
        ta, al = _alpha(a.slots[sl]["rgba"])
        assert al[-1] == 0 and ta[-1] == pytest.approx(1.62)
    assert checked_cruise and checked_after
    ev = {e.name: e.time for e in a.events}
    assert ev["fx_spin_blur_stop"] == 1.2


def test_spin_blur_streak_travel_after_the_stop_is_lag_times_speed(proj):
    res = R.apply(proj, "spin_blur", count=8, options=dict(stop=1.0, lag=0.06))
    sk, a = proj.data, proj.data.animations["fx_spin_blur"]
    D = res["duration"]
    moved = []
    for sl in [s for s in res["slots"] if "_st" in s]:
        t, yb, yt = _rows(sk, a, sl)
        c0, c1 = (np.interp(u, t, (yb + yt) / 2) for u in (1.0, D - 0.03))
        if abs(c0) < 120 and abs(c1) < 120:
            moved.append(c0 - c1)
    assert moved, "at least one streak sits mid-window around the stop"
    tail = D - 0.03 - 1.0
    want = res["catch_up"] * (1 - math.exp(-tail / 0.06))
    assert np.median(moved) == pytest.approx(want, rel=0.05), "they catch up by lag x speed, then stop"


def test_spin_blur_loop_closes_exactly_and_rows_stay_in_the_window(proj):
    res = R.apply(proj, "spin_blur", duration=0.5, options=dict(mode="loop", speed=2400, height=450))
    assert res["loop"] == 0.5 and res["cycles"] >= 1
    assert res["speed"] * 0.5 == pytest.approx(res["cycles"] * 675)
    sk, a = proj.data, proj.data.animations["fx_spin_blur"]
    for b, tl in a.bones.items():
        k = tl["translate"]
        assert (k[0].time, k[-1].time) == (0, 0.5)
        assert (k[0].x or 0, k[0].y or 0) == pytest.approx((k[-1].x or 0, k[-1].y or 0), abs=1e-3), b
        if "_n" in b:
            _, _, y = _xy(k, 0.0)
            assert np.all(np.abs(y + sk.bone(b).y) <= 225 + 1e-6), "rows are clamped to the reel window"
    for s, tl in a.slots.items():
        assert tl["rgba"][0].color == tl["rgba"][-1].color


def test_spin_blur_bad_inputs(proj):
    with pytest.raises(ValueError, match="mode"):
        R.apply(proj, "spin_blur", options=dict(mode="fast"))
    with pytest.raises(ValueError, match="stop"):
        R.apply(proj, "spin_blur", options=dict(stop=0.3))
    with pytest.raises(ValueError, match="lag"):
        R.apply(proj, "spin_blur", options=dict(lag=0))
    with pytest.raises(ValueError, match="direction"):
        R.apply(proj, "spin_blur", options=dict(direction="sideways"))


# ---------------------------------------------------------------- turbo_spin
def test_turbo_lines_stretch_with_speed_and_respawn_hidden(proj):
    res = R.apply(proj, "turbo_spin", duration=1.6, count=10, options=dict(ramp=0.2, shutter=0.06, speed=2600, width=486))
    sk, a = proj.data, proj.data.animations["fx_turbo_spin"]
    lines = [s for s in res["slots"] if "_ln" in s]
    assert len(lines) == 10
    xs = {np.sign(sk.bone(sk.slot(s).bone).x) for s in lines}
    assert xs == {-1.0, 1.0} and all(abs(sk.bone(sk.slot(s).bone).x) > 243 for s in lines), "lines frame the reels"
    for s in lines:
        b = sk.slot(s).bone
        ts, sy = _val(a.bones[b]["scale"], "y", 1.0)
        L = sy * 100 - 10
        half = np.interp(0.1, ts, L) / np.interp(0.8, ts, L)
        assert half == pytest.approx(0.5, abs=0.02), "length - L0 is proportional to speed (smoothstep is 1/2 mid-ramp)"
        t, _, y = _xy(a.bones[b]["translate"], 0.0)
        ta, al = _alpha(a.slots[s]["rgba"])
        for j in np.where(np.diff(y) > 50)[0]:              # respawn jump back to the top inside alpha 0
            assert np.interp(t[j], ta, al) < 0.06 and np.interp(t[j + 1], ta, al) < 0.06
        assert al[-1] == 0


def test_turbo_ripple_travels_through_carriers_at_the_phase_velocity_and_decays(grid):
    sym = ["s00", "s10", "s20"]                              # the middle-top row: x = -162, 0, 162
    sk = grid.data
    res = R.apply(grid, "turbo_spin", y=20, options=dict(bones=sym, wave_speed=800, kick=0.1, amp=20, ring=0.15, freq=5))
    assert res["ripple_bones"] == [f"fx_ripple_{b}" for b in sym]
    for b in sym:
        assert sk.bone(b).parent == f"fx_ripple_{b}"
    a = sk.animations["fx_turbo_spin"]
    peaks, amps = [], []
    for b in sym:
        t, _, y = _xy(a.bones[f"fx_ripple_{b}"]["translate"], 0.0)
        first = t[np.argmax(np.abs(y) > 1e-6)]
        peaks.append(first)
        amps.append(np.abs(y).max())
        assert y[-1] == 0 and np.all(y[t < 0.1] == 0)
    assert np.diff(peaks) == pytest.approx([162 / 800] * 2, abs=0.012), "phase velocity: the front lags dx / c"
    assert res["arrivals"][sym[2]] == pytest.approx(0.1 + 324 / 800, abs=1e-3)
    assert amps[0] > amps[1] > amps[2], "the amplitude decays as the wave travels"
    assert amps[1] / amps[0] == pytest.approx(math.exp(-162 / 900), rel=0.03)
    assert qa.validate(sk)["ok"]


def test_turbo_own_grid_and_wave_down(proj):
    res = R.apply(proj, "turbo_spin", options=dict(cols=2, rows=4, wave="down", kick=0.0, wave_speed=600))
    assert len(res["grid_bones"]) == 8 and res["ripple_bones"] == []
    arr = res["arrivals"]
    ys = {b: proj.data.bone(b).y for b in res["grid_bones"]}
    top = max(ys.values())
    for b, y in ys.items():
        assert arr[b] == pytest.approx((top - y) / 600, abs=1e-3), "down: the wave runs from the top row"
    with pytest.raises(ValueError, match="wave"):
        R.apply(proj, "turbo_spin", options=dict(wave="sideways"))
    with pytest.raises(ValueError, match="no bone"):
        R.apply(proj, "turbo_spin", options=dict(bones=["nope"]))


# ---------------------------------------------------------------- screen_shake
def test_screen_shake_is_a_damped_two_axis_spring(grid):
    res = R.apply(grid, "screen_shake", options=dict(shake="reels", amp=10, hz=12, decay=9))
    assert res["shake_bone"] == "fx_shake_reels" and grid.data.bone("reels").parent == "fx_shake_reels"
    t, x, y = _xy(grid.data.animations["fx_screen_shake"].bones["fx_shake_reels"]["translate"], 0.0)
    assert y[np.argmax(np.abs(y) > 0.5)] < 0, "the slam pushes the screen down first"
    m = t < 0.5
    sg = lambda v: np.sign(v[m & (np.abs(v) > 1e-3)])  # noqa: E731   ignore keys rounded to exactly 0
    cy = np.sum(np.diff(sg(y)) != 0)
    cx = np.sum(np.diff(sg(x)) != 0)
    assert cy == pytest.approx(2 * 12 * 0.5, abs=1.5), "~12 Hz vertical"
    assert cx / cy == pytest.approx(R.RECIPES["screen_shake"]["options"]["ratio"][0], rel=0.12), "x at the golden ratio of y"
    k = 9
    for u in (0.05, 0.1, 0.2):
        env = 10 * math.exp(-k * u)
        assert np.interp(u, t, y) == pytest.approx(-env * math.sin(2 * math.pi * 12 * u), abs=0.15), "x(t) = A e^-kt sin(wt)"
    assert (x[-1], y[-1]) == (0, 0) and t[-1] == pytest.approx(0.75)


def test_screen_shake_adds_onto_reel_stop_shake(grid):
    one = Project(grid.path.with_name("one.json"), grid.data.model_copy(deep=True))
    R.apply(one, "reel_stop", into="a", options=dict(reel="reel0", shake="reels"))
    rs = one.data.animations["a"].bones["fx_shake_reels"]["translate"]
    R.apply(grid, "reel_stop", into="spin", options=dict(reel="reel0", shake="reels"))
    R.apply(grid, "screen_shake", start=0.1, into="spin", options=dict(shake="reels"))
    assert [b.name for b in grid.data.bones].count("fx_shake_reels") == 1
    two = Project(grid.path.with_name("two.json"), new_skeleton("two", 720, 720))
    two.data.bones.append(Bone(name="reels", parent="root", y=20))
    R.apply(two, "screen_shake", start=0.1, into="b", options=dict(shake="reels"))
    ss = two.data.animations["b"].bones["fx_shake_reels"]["translate"]
    t, x, y = _xy(grid.data.animations["spin"].bones["fx_shake_reels"]["translate"], 0.0)
    t1, x1, y1 = _xy(rs, 0.0)
    t2, x2, y2 = _xy(ss, 0.0)
    for q in (0.05, 0.13, 0.21, 0.4):
        want = np.interp(q, t1, y1) + (np.interp(q, t2, y2) if q >= 0.1 else 0.0)
        assert np.interp(q, t, y) == pytest.approx(want, abs=0.2), "overlapping shakes sum"


def test_screen_shake_flash_has_a_1_over_t_tail_and_the_split_converges(proj):
    res = R.apply(proj, "screen_shake", options=dict(split=30, converge=0.09))
    a = proj.data.animations["fx_screen_shake"]
    sk = proj.data
    fl = [s for s in res["slots"] if "_flash" in s][0]
    ta, al = _alpha(a.slots[fl]["rgba"])
    assert ta[np.argmax(al)] == pytest.approx(0.02, abs=0.012), "instant attack"
    r_ = np.interp(0.095, ta, al) / np.interp(0.06, ta, al)
    assert r_ == pytest.approx((1 + 0.04 / 0.035) / (1 + 0.075 / 0.035), rel=0.05), "1/t tail"
    red = [s for s in res["slots"] if "_red" in s][0]
    t, x, _ = _xy(a.bones[sk.slot(red).bone]["translate"], 0.0)
    assert x[0] == pytest.approx(-30)
    d = -x
    assert np.all(np.diff(d) <= 1e-6) and np.all(d >= 0), "critically damped: converges without overshoot"
    for u in (0.05, 0.15):
        assert np.interp(u, t, d) == pytest.approx(30 * (1 + u / 0.09) * math.exp(-u / 0.09), abs=0.05)
    assert {k.color[:6] for k in a.slots[red]["rgba"]} == {"FF2A3C"}


def test_screen_shake_tiers_and_bad_inputs(proj):
    tiers = R.RECIPES["screen_shake"]["tiers"]
    opts = R.RECIPES["screen_shake"]["options"]
    assert set(tiers) == {"small", "big", "mega", "epic"}
    amps = [tiers["small"]["amp"], opts["amp"][0], tiers["big"]["amp"], tiers["mega"]["amp"], tiers["epic"]["amp"]]
    assert amps == sorted(amps), "bigger wins shake harder"
    for t_ in tiers.values():
        assert set(t_) <= set(opts)
    res = R.apply(proj, "screen_shake", options=tiers["epic"])
    assert res["duration"] == pytest.approx(5.5 / tiers["epic"]["decay"]), "an epic shake rings longer"
    with pytest.raises(ValueError, match="whole number"):
        R.apply(proj, "screen_shake", options=dict(ratio=2.0))
    with pytest.raises(ValueError, match="root"):
        R.apply(proj, "screen_shake", options=dict(shake="root"))
    with pytest.raises(ValueError, match="decay"):
        R.apply(proj, "screen_shake", options=dict(decay=0))
