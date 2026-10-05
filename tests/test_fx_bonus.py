"""Bonus-game moments: pick_reveal (flip with an exact spring overshoot behind a puff), hold_respin (clock-like respin
counter ring + breathing locked cells), jackpot_wheel (Coulomb + viscous friction stopping exactly on the winner, pointer
ticks), meter_fill (drops, sloshing standing waves, Stokes bubbles, overflow)."""
import math

import numpy as np
import pytest

from claude_spine import fx_bonus, fx_recipes as R, qa, runtime  # noqa: F401  (fx_bonus registers the recipes)
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project
from claude_spine.timeline import AnimBuilder
from conftest import needs_node

BONUS = ("pick_reveal", "hold_respin", "jackpot_wheel", "meter_fill")


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


def _xy(keys, rest):
    t = np.array([k.time for k in keys])
    v = lambda k, f: rest if getattr(k, f, None) is None else float(getattr(k, f))  # noqa: E731
    return t, np.array([v(k, "x") for k in keys]), np.array([v(k, "y") for k in keys])


def _val(keys, rest=0.0):
    return np.array([k.time for k in keys]), np.array([rest if getattr(k, "value", None) is None else float(k.value) for k in keys])


def _alpha(keys):
    return np.array([k.time for k in keys]), np.array([int(k.color[6:8], 16) / 255 for k in keys])


def _events(p, anim, name):
    return [e for e in p.data.animations[anim].events if e.name == name]


# ---------------------------------------------------------------- all four: the house rules
@pytest.mark.parametrize("rec", BONUS)
def test_builds_validates_hidden_in_setup_and_normal_blend_first(proj, rec):
    res = R.apply(proj, rec)
    sk = proj.data
    assert qa.validate(sk)["ok"]
    assert res["slots"] and all(sk.slot(s).attachment is None for s in res["slots"]), "FX slots are hidden in the setup pose"
    blends = [sk.slot(s).blend for s in res["slots"]]
    assert blends == sorted(blends, key=lambda b: b != "normal"), "normal-blend layers lead the run, then additive"
    idx = [sk.slot_index(s) for s in res["slots"]]
    assert idx == list(range(idx[0], idx[0] + len(idx))), "one contiguous run"
    assert qa.budget(sk, "desktop")["metrics"]["draw_calls"] <= 2
    assert _events(proj, res["animation"], f"fx_{rec}"), "every recipe fires fx_<recipe>"
    assert R.RECIPES[rec].get("normal_blend", False) == ("normal" in blends), "the registry flags runs with normal blend"
    assert set(R.RECIPES[rec]["roles"]) == set(R.ROLES[rec])


def test_tiers_only_override_real_options():
    for rec in BONUS:
        for tier, over in R.RECIPES[rec].get("tiers", {}).items():
            assert set(over) <= set(R.RECIPES[rec]["options"]), (rec, tier)


def test_into_and_start_shift_everything(proj):
    AnimBuilder(proj.data, "bonus").event(0.0, "game")
    res = R.apply(proj, "pick_reveal", start=1.0, into="bonus")
    a = proj.data.animations["bonus"]
    assert {e.name for e in a.events} >= {"game", "fx_pick_reveal", "fx_pick_swap"}
    assert res["swap_at"] == pytest.approx(1.16)
    assert [e.time for e in a.events if e.name == "fx_pick_reveal"] == [1.0]


# ---------------------------------------------------------------- pick_reveal
def test_pick_flip_goes_through_zero_and_overshoots_exactly(proj):
    res = R.apply(proj, "pick_reveal", options=dict(overshoot=0.2, flip=0.2, bounce=3.0))
    t, sx, sy = _xy(proj.data.animations["fx_pick_reveal"].bones[res["flip_bone"]]["scale"], 1.0)
    assert sx[np.argmin(np.abs(t - 0.2))] == pytest.approx(0.0, abs=1e-3), "edge-on exactly at the swap moment"
    assert np.interp(0.1, t, sx) == pytest.approx(math.cos(math.pi / 8), abs=2e-3), "theta = 90 (t/t_flip)^2: a flick"
    assert sx.max() == pytest.approx(1.2, abs=2e-3), "the face pops past full width by exactly overshoot"
    assert t[np.argmax(sx)] == pytest.approx(res["peak_at"], abs=0.012)
    assert 0 < res["zeta"] < 1
    # the face leaves edge-on at the speed the flip arrived with (a rigid rotation: |cos| has a symmetric kink)
    dt = 0.004
    v_in = (np.interp(0.2 - dt, t, sx) - 0) / dt
    v_out = (np.interp(0.2 + dt, t, sx) - 0) / dt
    assert v_out == pytest.approx(v_in, rel=0.12)
    assert (sx[-1], sy[-1]) == (1, 1), "ends exactly at rest"
    assert sy[np.argmin(np.abs(t - 0.2))] == pytest.approx(1.1, abs=1e-3), "the near edge grows while it is edge-on"


def test_pick_puff_hides_the_swap_and_good_pick_shines(proj):
    res = R.apply(proj, "pick_reveal")
    sk, a = proj.data, proj.data.animations["fx_pick_reveal"]
    swap = res["swap_at"]
    assert [e.time for e in _events(proj, "fx_pick_reveal", "fx_pick_swap")] == [swap]
    assert _events(proj, "fx_pick_reveal", "fx_shine") and _events(proj, "fx_pick_reveal", "fx_pick_good")
    faces = [s for s in res["slots"] if "_face" in s]
    clouds = [s for s in res["slots"] if sk.slot(s).blend == "normal" and s not in faces]
    assert len(faces) == 2 and clouds
    assert all(sk.slot_index(c_) > max(sk.slot_index(f) for f in faces) for c_ in clouds), "the puff is in front of the tile"
    best = max(float(np.interp(swap, *_alpha(a.slots[c_]["rgba"]))) for c_ in clouds)
    assert best > 0.6, "an opaque cloud covers the tile at the swap moment"
    back, front = faces
    att_b = [(k.time, k.name) for k in a.slots[back]["attachment"]]
    att_f = [(k.time, k.name) for k in a.slots[front]["attachment"]]
    assert att_b == [(0.0, "fx"), (swap, None)] and att_f == [(0.0, None), (swap, "fx")]
    assert len(_events(proj, "fx_pick_reveal", "fx_puff")) == 1, "member events are not doubled"


def test_pick_on_the_games_tile_uses_a_carrier_and_swaps_its_attachment(tmp_path):
    p = Project(tmp_path / "g.json", new_skeleton("g", 720, 720))
    sk = p.data
    sk.bones.append(Bone(name="tiles", parent="root"))
    sk.bones.append(Bone(name="tile", parent="tiles", x=40, y=10))
    sk.add_slot(Slot(name="tile", bone="tile", attachment="back"))
    for n in ("back", "prize"):
        sk.set_attachment("tile", n, RegionAttachment(path=n, width=150, height=150))
    AnimBuilder(sk, "pick").bone("tile", "rotate", [(0, 0), (0.3, 5)])
    res = R.apply(p, "pick_reveal", x=40, y=10, into="pick", front_of="tile", options=dict(tile="tile", swap_slot="tile", swap_to="prize"))
    car = res["flip_bone"]
    assert sk.bone("tile").parent == car and sk.bone(car).parent == "tiles"
    w = sk.world()
    assert (w["tile"].x, w["tile"].y) == pytest.approx((40, 10)) and (w[car].x, w[car].y) == pytest.approx((40, 10))
    a = sk.animations["pick"]
    assert [k.time for k in a.bones["tile"]["rotate"]] == [0, 0.3], "the artist's keys are untouched"
    assert [(k.time, k.name) for k in a.slots["tile"]["attachment"]] == [(res["swap_at"], "prize")]
    assert not [s for s in res["slots"] if "_face" in s], "no procedural tile when the game's tile flips"
    assert qa.validate(sk)["ok"]


def test_pick_bad_smoke_shakes_no_and_bad_ice_shatters_the_tile(proj):
    res = R.apply(proj, "pick_reveal", name="s", options=dict(good=False, bad="smoke"))
    t, x, _ = _xy(proj.data.animations["fx_s"].bones[res["flip_bone"]]["translate"], 0.0)
    assert np.sum(np.diff(np.sign(x[np.abs(x) > 0.05])) != 0) >= 3, "a 'no' shake reverses several times"
    assert np.abs(x[t > res["swap_at"] + 0.3]).max() < 0.5 * np.abs(x).max(), "it decays"
    assert x[-1] == 0
    assert _events(proj, "fx_s", "fx_pick_bad") and not _events(proj, "fx_s", "fx_shine")
    a = proj.data.animations["fx_s"]
    clouds = [s for s in res["slots"] if proj.data.slot(s).blend == "normal" and "_face" not in s]
    assert clouds and all(k.color[:6] == "5E5866" for s in clouds for k in a.slots[s]["rgba"]), "a bad pick is dark smoke"
    res2 = R.apply(proj, "pick_reveal", name="i", options=dict(good=False, bad="ice"))
    # (ice_shatter's own fx_<recipe> event shares the name, at its start; the last one is the break)
    assert [e.time for e in _events(proj, "fx_i", "fx_ice_shatter")][-1] == res2["shatter_at"]
    front = [s for s in res2["slots"] if "_face" in s][1]
    att = [(k.time, k.name) for k in proj.data.animations["fx_i"].slots[front]["attachment"]]
    assert att[-1] == (res2["shatter_at"], None), "the face is gone when the ice breaks"


def test_pick_bad_inputs_are_clear_errors(proj):
    with pytest.raises(ValueError, match="bad must be"):
        R.apply(proj, "pick_reveal", options=dict(good=False, bad="fire"))
    with pytest.raises(ValueError, match="overshoot"):
        R.apply(proj, "pick_reveal", options=dict(overshoot=0))
    with pytest.raises(ValueError, match="too small"):
        R.apply(proj, "pick_reveal", options=dict(overshoot=0.01, flip=0.05, bounce=1.0))
    with pytest.raises(ValueError, match="go together"):
        R.apply(proj, "pick_reveal", options=dict(swap_slot="x"))
    with pytest.raises(ValueError, match="no bone"):
        R.apply(proj, "pick_reveal", options=dict(tile="nope"))


# ---------------------------------------------------------------- hold_respin
def _hand_sweep(p, res, N):
    """Remaining fraction from the ring's hand row (row 0): its world angle is 90 - 360 (1 - S)."""
    a = p.data.animations["fx_hold_respin"]
    hand = [b for b in a.bones if b.endswith("_r0")][0]
    t, v = _val(a.bones[hand]["rotate"])
    return t, 1 - (90 - (90 + v)) / 360.0


def test_respin_counter_ticks_down_resets_and_fires_events(proj):
    res = R.apply(proj, "hold_respin", options=dict(respins=3, period=1.0, resets=[2]))
    assert res["counts"] == [2, 1, 2, 1, 0], "3 -> 2 -> 1, a coin lands: refill, 3 -> 2 -> 1 -> 0"
    assert np.allclose(np.diff(res["ticks"]), 1.0)
    ev = _events(proj, "fx_hold_respin", "fx_respin_tick")
    assert [e.time for e in ev] == res["ticks"] and [e.int for e in ev] == res["counts"], "tick events carry the respins left"
    assert len(_events(proj, "fx_hold_respin", "fx_respin_reset")) == 1
    assert [e.time for e in _events(proj, "fx_hold_respin", "fx_respin_end")] == [res["end_at"]]
    t, S = _hand_sweep(proj, res, 3)
    for tk, cnt in zip(res["ticks"], res["counts"]):
        after = (t > tk + 0.56) & (t < tk + 0.59)
        if after.any():
            assert S[after].mean() == pytest.approx(cnt / 3, abs=2e-3), "the ring shows exactly the respins left"
    assert S[0] == pytest.approx(0.0, abs=1e-3) and S[-1] == pytest.approx(0.0, abs=1e-3)


def test_respin_tick_is_a_spring_with_an_exact_overshoot(proj):
    res = R.apply(proj, "hold_respin", options=dict(respins=4, period=1.0, recoil=0.3))
    t, S = _hand_sweep(proj, res, 4)
    tk, cnt = res["ticks"][0], res["counts"][0]
    win = (t >= tk) & (t < tk + 0.3)
    assert S[win].min() == pytest.approx(cnt / 4 - 0.3 / 4, abs=2e-3), "it swings past the new value by recoil x one segment"
    assert S[(t > tk + 0.56) & (t < tk + 0.6)].mean() == pytest.approx(cnt / 4, abs=1e-3)


def test_locked_cells_breathe_in_an_exact_loop(proj):
    res = R.apply(proj, "hold_respin", options=dict(cells=[[-100, 0, 120, 120], [100, 0, 120, 120]], period=1.2, breaths=2))
    assert res["duration"] / 1.2 == pytest.approx(round(res["duration"] / 1.2)), "the window is a whole number of respins"
    a = proj.data.animations["fx_hold_respin"]
    locks = [s for s in res["slots"] if "_lock" in s]
    unders = [s for s in res["slots"] if "electric_frame_under" in s or "electric_frame_frame" in s]
    assert len(locks) == 2 and unders
    for s in locks + unders:
        t, al = _alpha(a.slots[s]["rgba"])
        for q in np.linspace(1.25, 2.35, 9):                 # inside the window, away from the fades
            assert np.interp(q, t, al) == pytest.approx(np.interp(q + 1.2, t, al), abs=0.01), s
    assert all(proj.data.slot(s).blend == "additive" for s in res["slots"]), "all additive: one batch"


def test_respin_bad_inputs_are_clear_errors(proj):
    with pytest.raises(ValueError, match="respins"):
        R.apply(proj, "hold_respin", options=dict(respins=0))
    with pytest.raises(ValueError, match="period"):
        R.apply(proj, "hold_respin", options=dict(period=0.2))
    with pytest.raises(ValueError, match="each cell"):
        R.apply(proj, "hold_respin", options=dict(cells=[[0, 0, 0, 10]]))
    with pytest.raises(ValueError, match="breaths"):
        R.apply(proj, "hold_respin", options=dict(breaths=0))


# ---------------------------------------------------------------- jackpot_wheel
def test_wheel_friction_is_coulomb_plus_viscous_and_stops_exactly_on_the_winner(proj):
    res = R.apply(proj, "jackpot_wheel", duration=5.0, options=dict(segments=12, winner=5, spins=3, viscous=0.8, kick=0.35))
    seg = 30.0
    assert res["turned"] == pytest.approx(3 * 360 + (-5 * seg) % 360)
    a = proj.data.animations["fx_jackpot_wheel"]
    spin = [b for b in a.bones if b.endswith("_spin")][0]
    t, rot = _val(a.bones[spin]["rotate"])
    phi = -rot
    assert phi[-1] == pytest.approx(res["turned"], abs=0.01) and t[-1] == pytest.approx(5.0)
    assert ((90 - 5 * seg + rot[-1]) - 90) % 360 == pytest.approx(0, abs=0.01), "the winner's centre ends under the pointer"
    h = 0.1                                                  # key times are rounded to 0.1 ms: differentiate on a 0.1 s grid
    g = np.arange(0.6, 4.8, h)
    ph = lambda q: np.interp(q, t, phi)  # noqa: E731
    w = (ph(g + h) - ph(g - h)) / (2 * h)
    dw = (ph(g + h) - 2 * ph(g) + ph(g - h)) / (h * h)
    law = dw + 0.8 * w                                       # w' + k w = -a, a constant
    assert np.allclose(law, -res["coulomb"], rtol=0.05, atol=3.0)
    assert np.all(np.diff(w) < 0), "always slowing down"
    w_kick = (ph(0.36) - ph(0.34)) / 0.02
    assert w_kick == pytest.approx(res["omega0"], rel=0.03)
    assert (ph(5.0) - ph(4.98)) / 0.02 < 0.05 * res["omega0"], "it comes to rest at duration"


def test_wheel_ticks_on_every_peg_and_the_pointer_recoils_exactly(proj):
    res = R.apply(proj, "jackpot_wheel", options=dict(segments=8, winner=2, spins=2, recoil=20, pointer_damping=0.25))
    a = proj.data.animations["fx_jackpot_wheel"]
    seg = 45.0
    spin = [b for b in a.bones if b.endswith("_spin")][0]
    t, rot = _val(a.bones[spin]["rotate"])
    ev = _events(proj, "fx_jackpot_wheel", "fx_wheel_tick")
    assert len(ev) == len(res["ticks"]) == int(res["turned"] / seg - 0.5) + 1
    for m, e in enumerate(ev):
        assert -np.interp(e.time, t, rot) == pytest.approx((m + 0.5) * seg, abs=0.5), "a tick when a peg passes the pointer"
    assert ev[-1].int == 2 and _events(proj, "fx_jackpot_wheel", "fx_wheel_stop")[0].int == 2
    ptr = res["pointer_bone"]
    tp, th = _val(a.bones[ptr]["rotate"])
    assert th.max() == pytest.approx(20.0, abs=1e-3), "each peg pushes the pointer to recoil"
    last = res["ticks"][-1]
    os = math.exp(-0.25 * math.pi / math.sqrt(1 - 0.25 ** 2))
    assert th[tp > last].min() == pytest.approx(-20.0 * os, abs=0.05), "it springs back past rest by the exact undershoot"
    assert th[-1] == 0


def test_wheel_segment_glow_trails_the_pointer(proj):
    res = R.apply(proj, "jackpot_wheel", options=dict(segments=12, winner=0, spins=2, trail=0.2, boom=False))
    a = proj.data.animations["fx_jackpot_wheel"]
    wedges = [s for s in res["slots"] if "_seg" in s]
    assert len(wedges) == 12
    ticks, under = res["ticks"], res["segments_passed"]
    i = len(ticks) - 3                                         # a slow pass near the end
    j, t_in, t_out = under[i], ticks[i], ticks[i + 1]
    s = [w for w in wedges if w.endswith(f"_seg{j}")][0]
    t, al = _alpha(a.slots[s]["rgba"])
    peak = np.interp((t_in + t_out) / 2, t, al)
    assert peak == pytest.approx(0.62, abs=0.01), "lit while it is under the pointer"
    assert np.interp(t_out + 0.2, t, al) == pytest.approx(peak / math.e, abs=0.02), "then it decays e^(-t/trail)"


def test_wheel_turns_the_games_wheel_through_a_carrier(tmp_path):
    p = Project(tmp_path / "w.json", new_skeleton("w", 720, 720))
    p.data.bones.append(Bone(name="stage", parent="root"))
    p.data.bones.append(Bone(name="wheel", parent="stage", y=-20))
    p.data.bones.append(Bone(name="flap", parent="stage", y=200))
    AnimBuilder(p.data, "spin").bone("wheel", "scale", [(0, 1, 1), (0.2, 1.05, 1.05)])
    res = R.apply(p, "jackpot_wheel", y=-20, into="spin", options=dict(wheel="wheel", pointer="flap"))
    a = p.data.animations["spin"]
    car = res["wheel_bone"]
    assert p.data.bone("wheel").parent == car and p.data.bone("flap").parent == res["pointer_bone"]
    assert [k.time for k in a.bones["wheel"]["scale"]] == [0, 0.2], "the artist's keys are untouched"
    _, r_car = _val(a.bones[car]["rotate"])
    assert -r_car[-1] == pytest.approx(res["turned"], abs=0.01)
    assert not [s for s in res["slots"] if "_pointer" in s], "no procedural pointer when the game's pointer ticks"
    assert qa.validate(p.data)["ok"]


def test_wheel_bad_inputs_are_clear_errors(proj):
    with pytest.raises(ValueError, match="winner"):
        R.apply(proj, "jackpot_wheel", options=dict(winner=12))
    with pytest.raises(ValueError, match="segments"):
        R.apply(proj, "jackpot_wheel", options=dict(segments=1))
    with pytest.raises(ValueError, match="kick"):
        R.apply(proj, "jackpot_wheel", duration=1.0, options=dict(kick=0.8))
    with pytest.raises(ValueError, match="must turn"):
        R.apply(proj, "jackpot_wheel", options=dict(spins=0, winner=0))


# ---------------------------------------------------------------- meter_fill
def test_meter_level_rises_per_drop_and_ends_full_and_flat(proj):
    res = R.apply(proj, "meter_fill", options=dict(height=300, levels=[0.3, 0.6, 1.0], wobble=6))
    a = proj.data.animations["fx_meter_fill"]
    tops = res["surface_bones"]
    ev = _events(proj, "fx_meter_fill", "fx_meter_drop")
    assert [e.time for e in ev] == res["hits"] and [e.int for e in ev] == [1, 2, 3]
    assert [e.time for e in _events(proj, "fx_meter_fill", "fx_meter_full")] == [res["full_at"]]
    for i, lv in enumerate([0.3, 0.6]):
        q = res["hits"][i + 1] - 0.01
        ys = [np.interp(q, *_xy(a.bones[b]["translate"], 0.0)[::2]) for b in tops]
        assert np.mean(ys) == pytest.approx(300 * lv, abs=4.0)
    ends = [_xy(a.bones[b]["translate"], 0.0)[2][-1] for b in tops]
    assert ends == pytest.approx([300.0] * len(tops), abs=1e-3), "full, and the surface is at rest"
    body = [s for s in res["slots"] if proj.data.slot(s).blend == "normal"]
    assert len(body) == 1 and a.slots[body[0]]["attachment"][-1].name == "fx", "the meter stays full after the clip"


def test_meter_surface_sloshes_as_standing_waves_with_water_dispersion(proj):
    res = R.apply(proj, "meter_fill", options=dict(width=80, height=300, levels=[0.5], slosh_hz=3.0, wobble=8))
    k1 = math.pi / 80
    assert math.sqrt(res["slosh_g"] * k1 * math.tanh(k1 * 150)) == pytest.approx(2 * math.pi * 3.0, rel=1e-3)
    a = proj.data.animations["fx_meter_fill"]
    tops = res["surface_bones"]
    h = res["hits"][0]
    curves = [_xy(a.bones[b]["translate"], 0.0) for b in tops]
    ts = np.linspace(h + 0.02, h + 0.5, 60)
    left = np.array([np.interp(q, curves[0][0], curves[0][2]) for q in ts])
    right = np.array([np.interp(q, curves[-1][0], curves[-1][2]) for q in ts])
    level = np.array([np.mean([np.interp(q, c_[0], c_[2]) for c_ in curves]) for q in ts])
    dl, dr = left - level, right - level
    assert np.abs(dl).max() > 2, "the surface is kicked into waves"
    late = ts > h + 0.4
    assert np.abs(dl[late]).max() < np.abs(dl).max(), "and they die down"
    assert np.sum(np.diff(np.sign(dl - dl.mean())) != 0) >= 2, "it oscillates"


def test_meter_bubbles_rise_by_stokes_and_pop_under_the_surface(proj):
    res = R.apply(proj, "meter_fill", count=12, options=dict(levels=[0.4, 0.8, 1.0], height=320))
    assert res["bubbles"] > 4
    a = proj.data.animations["fx_meter_fill"]
    mid = res["surface_bones"][len(res["surface_bones"]) // 2]
    st, _, sy_ = _xy(a.bones[mid]["translate"], 0.0)
    sizes, speeds = [], []
    for b, tl in a.bones.items():
        if "_bub" not in b or "translate" not in tl:
            continue
        t, x, y = _xy(tl["translate"], 0.0)
        _, sc, _ = _xy(tl["scale"], 1.0)
        gaps = np.where(np.diff(y) < -5)[0]                    # a new life starts back at the floor (while hidden)
        for seg in np.split(np.arange(len(t)), gaps + 1):
            if len(seg) < 4:
                continue
            tt, yy = t[seg], y[seg]
            assert np.all(np.diff(yy) >= -1e-6), "bubbles only rise"
            assert yy[-1] <= np.interp(tt[-1], st, sy_) + 8, "they pop at (not above) the surface"
            sizes.append(sc[seg][0])
            speeds.append((yy[-3] - yy[0]) / (tt[-3] - tt[0]))
    assert len(sizes) >= 4
    assert np.corrcoef(sizes, speeds)[0, 1] > 0.5, "Stokes: the bigger bubbles rise faster"


def test_meter_not_full_means_no_overflow(proj):
    res = R.apply(proj, "meter_fill", options=dict(levels=[0.2, 0.5]))
    assert res["full_at"] is None and not _events(proj, "fx_meter_fill", "fx_meter_full")
    assert not _events(proj, "fx_meter_fill", "fx_light_beam")


def test_meter_bad_inputs_are_clear_errors(proj):
    with pytest.raises(ValueError, match="go down"):
        R.apply(proj, "meter_fill", options=dict(levels=[0.5, 0.3]))
    with pytest.raises(ValueError, match="levels"):
        R.apply(proj, "meter_fill", options=dict(levels=[1.5]))
    with pytest.raises(ValueError, match="source"):
        R.apply(proj, "meter_fill", options=dict(sources=[[1, 2, 3]]))


# ---------------------------------------------------------------- runtime
@needs_node
def test_all_four_play_in_the_spine_core_runtime(tmp_path):
    p = Project(tmp_path / "b.json", new_skeleton("b", 720, 720))
    R.apply(p, "pick_reveal", x=-200, into="bonus")
    R.apply(p, "pick_reveal", x=0, start=0.4, into="bonus", options=dict(good=False, bad="ice"))
    R.apply(p, "hold_respin", y=-200, into="hold", options=dict(resets=[1], period=0.8))
    R.apply(p, "jackpot_wheel", into="wheel", duration=3.0, options=dict(spins=2, winner=4))
    R.apply(p, "meter_fill", into="meter")
    assert qa.validate(p.data)["ok"]
    p.save()
    dump = runtime.run(p, animations=["bonus", "hold", "wheel", "meter"], fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    assert dump["animations"]["wheel"]["duration"] == pytest.approx(3.0 + 1.9, abs=0.01)
    assert all(len(dump["animations"][a_]["frames"]) > 5 for a_ in ("bonus", "hold", "wheel", "meter"))
