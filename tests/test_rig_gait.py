"""Gaits (footfall tables -> planted-foot IK paths, Froude-style speed scaling, bob / pitch from the ground reaction
forces) and the quadruped rig (layer convention, leg types, strands with physics, the clip set)."""
import asyncio
import json
import math

import numpy as np
import pytest

from claude_spine import qa, rig_gait as G, runtime
from claude_spine.ir import RegionAttachment, Slot
from claude_spine.mesh import mesh_world_vertices
from claude_spine.rig import setup_hull_world
from conftest import needs_node

GAIT_CLIPS = ("walk", "trot", "gallop", "bound")
LOOPS = ("idle", "sleep", *GAIT_CLIPS)
ONESHOTS = ("alert", "pounce", "shake")
REST = {"rotate": (0.0,), "translate": (0.0, 0.0), "scale": (1.0, 1.0)}
FIELDS = {"rotate": ("value",), "translate": ("x", "y"), "scale": ("x", "y")}


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def dog(tmp_path_factory):
    p = G.make_sample_quadruped(tmp_path_factory.mktemp("dog"))
    rep = G.rig_quadruped(p, "digitigrade", seed=7)
    p.save()
    return p, rep


@pytest.fixture(scope="module")
def dumps(dog):
    p, _ = dog
    if not runtime.available():
        pytest.skip("Node not installed")
    fast = runtime.run(p, animations=list(GAIT_CLIPS), fps=60, geometry=True)
    slow = runtime.run(p, animations=["idle", "alert", "pounce", "sleep", "shake"], fps=30, geometry=True)
    return fast, slow


def _vals(k, tl):
    rest = REST[tl]
    ex = k.model_extra or {}
    return tuple(rest[i] if ex.get(f) is None else float(ex[f]) for i, f in enumerate(FIELDS[tl]))


def _track(keys, tl):
    t = np.array([k.time for k in keys])
    v = np.array([_vals(k, tl) for k in keys])
    return t, v


def _interp(keys, tl, ts):
    t, v = _track(keys, tl)
    return np.stack([np.interp(ts, t, v[:, j]) for j in range(v.shape[1])], 1)


def _slot_verts(frame, slot):
    for d in frame["draws"]:
        if d["slot"] == slot:
            return np.asarray(d["v"], float).reshape(-1, 2)
    raise KeyError(slot)


FOOT_SLOT = {"front_L": "front_foot_L", "front_R": "front_foot_R", "hind_L": "hind_foot_L", "hind_R": "hind_foot_R"}


# ------------------------------------------------------------------ gait tables and maths
def test_footfall_tables_are_the_classic_sequences():
    order = lambda g: [r for r, _ in sorted(G.GAITS[g]["phases"].items(), key=lambda kv: kv[1])]  # noqa: E731
    assert order("walk") == ["LH", "LF", "RH", "RF"], "lateral-sequence 4-beat walk"
    ph = G.GAITS["trot"]["phases"]
    assert ph["LF"] == ph["RH"] and ph["RF"] == ph["LH"] and ph["LF"] != ph["RF"], "trot = diagonal pairs"
    ph = G.GAITS["pace"]["phases"]
    assert ph["LF"] == ph["LH"] and ph["RF"] == ph["RH"], "pace = lateral pairs"
    assert order("gallop") == ["LH", "RH", "RF", "LF"], "rotary gallop goes round the body"
    ph = G.GAITS["bound"]["phases"]
    assert ph["LH"] == ph["RH"] and ph["LF"] == ph["RF"]
    ph = G.GAITS["tripod"]["phases"]
    assert ph["L1"] == ph["R2"] == ph["L3"] and ph["R1"] == ph["L2"] == ph["R3"] and ph["L1"] != ph["R1"]
    assert G.GAITS["walk"]["duty"] > 0.5 > G.GAITS["trot"]["duty"] > G.GAITS["gallop"]["duty"], "duty falls with speed"
    assert G.resolve_gait("walk", 2) == "biped_walk" and G.resolve_gait("walk", 6) == "tripod"
    assert set(G.list_gaits()) == set(G.GAITS)


def test_shape_functions():
    s = np.linspace(0, 1, 2001)
    m = G.minjerk(s)
    assert m[0] == 0 and m[-1] == 1 and np.all(np.diff(m) >= 0)
    assert abs(np.gradient(m, s)[0]) < 1e-2 and abs(np.gradient(m, s)[-1]) < 1e-2, "zero velocity at both ends"
    lift = G.lift_arc(s)
    assert lift.max() == pytest.approx(1, abs=1e-4) and 0.35 < s[lift.argmax()] < 0.5, "peak 1, slightly early"
    assert lift[0] == 0 and lift[-1] == pytest.approx(0, abs=1e-12)
    assert G.roll_arc(s).max() == pytest.approx(1, abs=1e-4)
    z = 0.45
    st = G.spring_step(np.linspace(0, 3, 30001), z, 3.0)
    assert st.max() - 1 == pytest.approx(G.spring_overshoot(z), rel=1e-3), "exact underdamped overshoot"
    assert st[-1] == pytest.approx(1, abs=1e-3)


def test_froude_scaling_of_stride_and_frequency(dog):
    p, rep = dog
    legs = G.quad_gait_legs(p._quad)
    a, _ = G.plan_gait(p, legs, "q_body", "trot", speed=150, fit_reach=False)
    b, _ = G.plan_gait(p, legs, "q_body", "trot", speed=300, fit_reach=False)
    assert b.frequency / a.frequency == pytest.approx(math.sqrt(2), rel=3e-3), "f ~ sqrt(speed)"
    assert b.stride / a.stride == pytest.approx(math.sqrt(2), rel=3e-3), "stride ~ sqrt(speed)"
    assert a.frequency == pytest.approx(G.GAITS["trot"]["c"] * math.sqrt(150 / a.L), rel=3e-3)
    assert a.stride == pytest.approx(150 * a.T, rel=1e-9), "stride = speed / frequency"


def test_stance_moves_back_at_exactly_body_speed_and_swing_lifts_to_clearance(dog):
    p, rep = dog
    sk = p.data
    plan, _ = G.plan_gait(p, G.quad_gait_legs(p._quad), "q_body", "walk")
    a = sk.animations["walk"]
    D = rep["clips"]["walk"]["duration"]
    for i, lg in enumerate(plan.legs):
        t, v = _track(a.bones[lg.target]["translate"], "translate")
        td = (plan.phase[i] % 1) * plan.T
        lo = td + plan.duty * plan.T
        if lo > D:
            td, lo = td - plan.T, lo - plan.T
        inside = (t > td + 1e-3) & (t < lo - 1e-3) & (t > 1e-6) & (t < D - 1e-6)   # the clip ends are keys
        assert not inside.any(), "stance is ONE linear segment (no keys inside it)"
        xs = np.interp([max(td, 0), min(lo, D)], t, v[:, 0])
        speed = (xs[0] - xs[1]) / (min(lo, D) - max(td, 0))
        assert speed == pytest.approx(plan.facing * plan.speed, rel=2e-3), lg.name
        ys = np.interp(np.linspace(max(td, 0) + 2e-4, min(lo, D) - 2e-4, 20), t, v[:, 1])
        assert np.abs(ys).max() < 1e-6, "planted feet stay on the ground"
        assert v[:, 1].max() == pytest.approx(plan.clearance, rel=0.02), "swing lifts to the clearance"
        assert v[:, 1].min() >= 0, "never below the ground"
    on = np.mean([plan.contact(0, t) for t in np.linspace(0, plan.T, 1000, endpoint=False)])
    assert on == pytest.approx(G.GAITS["walk"]["duty"], abs=2e-3)


def test_steps_fire_once_per_leg_per_cycle_at_touchdown(dog):
    p, rep = dog
    sk = p.data
    for g in GAIT_CLIPS:
        ev = [e for e in sk.animations[g].events if e.name == "sfx_step"]
        names = sorted((e.model_extra or {}).get("string") for e in ev)
        assert names == sorted(FOOT_SLOT), (g, names)
        T = rep["clips"][g]["period"]
        for e in ev:
            role = {"front_L": "LF", "front_R": "RF", "hind_L": "LH", "hind_R": "RH"}[e.model_extra["string"]]
            assert e.time == pytest.approx((G.GAITS[g]["phases"][role] % 1) * T, abs=1e-3)
    assert "sfx_step" in sk.events


def test_body_bob_and_pitch_follow_the_ground_reaction_forces(dog):
    p, _ = dog
    legs = G.quad_gait_legs(p._quad)
    for g, sign in (("trot", -1), ("gallop", -1), ("walk", 1)):
        plan, _ = G.plan_gait(p, legs, "q_body", g, fit_reach=False)
        t = np.linspace(0, plan.T, 600, endpoint=False)
        dy, pitch = plan.body_offset(t)
        load = sum(plan.load(i, t) for i in range(4))
        c = np.corrcoef(dy, load)[0, 1]
        assert c * sign > 0.9, f"{g}: {'vault' if sign > 0 else 'bounce'} (corr {c:.2f})"
        assert dy.max() <= 1e-9 and dy.min() == pytest.approx(-2 * plan.bob_amp, rel=1e-2), "only ever lowers"
    plan, _ = G.plan_gait(p, legs, "q_body", "bound", fit_reach=False)
    t = np.linspace(0, plan.T, 600, endpoint=False)
    _, pitch = plan.body_offset(t)
    hind = plan.load(2, t) + plan.load(3, t)
    front = plan.load(0, t) + plan.load(1, t)
    assert np.corrcoef(pitch, hind - front)[0, 1] > 0.99, "nose up while the hinds push"
    assert np.abs(pitch).max() == pytest.approx(plan.pitch_amp, rel=1e-2)


def test_reach_is_respected_and_frequency_rises_when_the_stride_cannot_fit(dog):
    p, rep = dog
    for g in GAIT_CLIPS:
        assert rep["clips"][g]["reach_max"] <= 0.985
    legs = G.quad_gait_legs(p._quad)
    plan, notes = G.plan_gait(p, legs, "q_body", "gallop", speed=1400)
    assert "frequency_raised" in notes and plan.reach_ratio()[0] <= 0.985
    assert notes["frequency_raised"]["to"] > notes["frequency_raised"]["from"]


def test_gait_loops_close_exactly(dog):
    p, rep = dog
    for g in LOOPS:
        a = p.data.animations[g]
        D = rep["clips"][g]["duration"]
        for bone, tls in a.bones.items():
            for tl, ks in tls.items():
                assert ks[0].time == 0 and ks[-1].time == pytest.approx(D, abs=1e-4), (g, bone, tl)
                assert _vals(ks[0], tl) == _vals(ks[-1], tl), (g, bone, tl)


def test_one_shots_end_exactly_on_the_setup_pose(dog):
    p, rep = dog
    for c in ONESHOTS:
        a = p.data.animations[c]
        D = rep["clips"][c]["duration"]
        for bone, tls in a.bones.items():
            for tl, ks in tls.items():
                assert ks[-1].time == pytest.approx(D, abs=1e-4), (c, bone, tl)
                assert _vals(ks[-1], tl) == REST[tl], (c, bone, tl)


# ------------------------------------------------------------------ runtime QA
@needs_node
def test_planted_feet_do_not_slide_in_the_runtime(dog, dumps):
    """World position of every planted paw, measured from the runtime-posed skeleton, is constant over its stance
    in the GROUND frame (the cycle is in place: the ground scrolls back at the gait speed)."""
    p, rep = dog
    fast, _ = dumps
    legs = G.quad_gait_legs(p._quad)
    for g in GAIT_CLIPS:
        plan, _ = G.plan_gait(p, legs, "q_body", g)
        assert plan.T == rep["clips"][g]["period"]
        frames = fast["animations"][g]["frames"]
        checked = 0
        for i, lg in enumerate(plan.legs):
            groups = {}
            for f in frames:
                t = f["t"]
                ph = plan.phi(i, t)
                if ph < plan.duty:
                    groups.setdefault(math.floor(t / plan.T - plan.phase[i] + 1e-9), []).append(
                        _slot_verts(f, FOOT_SLOT[lg.name]) + [plan.facing * plan.speed * t, 0])
            for k, vs in groups.items():
                if len(vs) < 3:
                    continue
                V = np.array(vs)
                dev = np.abs(V - V.mean(0)).max()
                assert dev < 0.05, f"{g} {lg.name}: planted paw slides {dev:.2f} px"
                checked += 1
        assert checked >= 4, g


def _check_reach(sk, dmp, tol=0.3):
    """The paw rides the end of the leg chain; it stays rigid in its target's frame only if the IK reaches."""
    w = sk.world()
    for anim, A in dmp["animations"].items():
        a = sk.animations[anim]
        ts = np.array([f["t"] for f in A["frames"]])
        for leg, slot in FOOT_SLOT.items():
            tgt = f"ik_{leg}"
            tls = a.bones.get(tgt, {})
            tr = _interp(tls["translate"], "translate", ts) if "translate" in tls else np.zeros((len(ts), 2))
            rot = _interp(tls["rotate"], "rotate", ts)[:, 0] if "rotate" in tls else np.zeros(len(ts))
            local = []
            for k, f in enumerate(A["frames"]):
                c, s = math.cos(math.radians(-rot[k])), math.sin(math.radians(-rot[k]))
                d = _slot_verts(f, slot) - [w[tgt].x + tr[k, 0], w[tgt].y + tr[k, 1]]
                local.append(d @ np.array([[c, s], [-s, c]]))
            L = np.array(local)
            dev = np.abs(L - L[0]).max()
            assert dev < tol, f"{anim} {leg}: paw leaves its target by {dev:.2f} px (IK out of reach)"


@needs_node
def test_every_ik_target_is_reached_in_every_clip(dog, dumps):
    p, _ = dog
    for dmp in dumps:
        _check_reach(p.data, dmp)


@needs_node
@pytest.mark.parametrize("leg_type", ["plantigrade", "unguligrade"])
def test_other_leg_types_reach_in_every_clip(tmp_path, leg_type):
    p = G.make_sample_quadruped(tmp_path / leg_type)
    G.rig_quadruped(p, leg_type)
    d = runtime.run(p, fps=30, geometry=True)
    assert d["ok"] and not d["problems"]
    _check_reach(p.data, d)


@needs_node
def test_rig_validates_plays_and_fits_the_mobile_budget(dog, dumps):
    p, rep = dog
    v = qa.validate(p.data)
    assert v["ok"], v["errors"]
    for dmp in dumps:
        assert dmp["ok"] and not dmp["problems"]
    b = qa.budget(p.data, "mobile_character")
    assert b["ok"], b["over_budget"]
    c = rep["counts"]
    assert c["ik"] == 8 and c["transform"] == 4 and c["physics"] >= 10
    fired = {e["name"] for dmp in dumps for A in dmp["animations"].values() for e in A["events"]}
    assert {"sfx_step", "sfx_idle", "sfx_alert", "sfx_pounce", "sfx_sleep", "sfx_shake"} <= fired


@needs_node
def test_rigging_never_moves_the_setup_pose(tmp_path):
    p0 = G.make_sample_quadruped(tmp_path / "a")
    before = {s.name: setup_hull_world(p0, s.name) for s in p0.data.slots}
    d0 = runtime.run(p0, fps=1)
    p = G.make_sample_quadruped(tmp_path / "b")
    G.rig_quadruped(p, clips=[])
    sk = p.data
    w = sk.world()
    for s in sk.slots:
        att = sk.attachment(s.name)
        if isinstance(att, RegionAttachment):
            assert np.abs(setup_hull_world(p, s.name) - before[s.name]).max() < 0.02, s.name
        else:
            mv = mesh_world_vertices(sk, s.name, att, w)
            lo, hi = before[s.name].min(0), before[s.name].max(0)
            assert (mv >= lo - 0.6).all() and (mv <= hi + 0.6).all(), s.name
    d1 = runtime.run(p, fps=1)
    assert np.allclose(d0["setup"]["bounds"], d1["setup"]["bounds"], atol=1.0)


# ------------------------------------------------------------------ quadruped clips
def test_alert_springs_ears_forward_with_the_exact_overshoot_then_releases(dog):
    p, rep = dog
    q = p._quad
    a = p.data.animations["alert"]
    info = rep["clips"]["alert"]
    for bone, fwd in q.ears:
        t, v = _track(a.bones[bone]["rotate"], "rotate")
        peak = (v[:, 0] * fwd).max()
        assert peak == pytest.approx(info["ear_target_deg"] * (1 + info["overshoot"]), rel=4e-3)
        hold = (t > info["snap"] + 0.8) & (t < info["release"])
        assert np.allclose(v[hold, 0] * fwd, info["ear_target_deg"], rtol=0.01), "frozen at the alert pose"
    ev = [e for e in a.events if e.name == "sfx_alert"]
    assert len(ev) == 1 and ev[0].time == pytest.approx(info["snap"])


def test_shake_is_a_damped_sine_travelling_head_to_tail(dog):
    p, rep = dog
    q = p._quad
    a = p.data.animations["shake"]
    info = rep["clips"]["shake"]
    t, v = _track(a.bones["shoulders"]["rotate"], "rotate")
    x = v[:, 0]
    s = (t > info["start"] + 0.1) & (t < info["end"] - 0.3)
    zc = np.nonzero(np.diff(np.sign(x[s])) != 0)[0]
    tz = t[s][zc]
    hz = 1 / (2 * np.mean(np.diff(tz)))
    assert hz == pytest.approx(info["frequency_hz"], rel=0.06), "wet-dog shake frequency"
    peak = np.abs(x).max()
    late = (t > info["end"] - 0.35) & (t < info["end"])
    assert np.abs(x[late]).max() < 0.25 * peak, "the envelope decays"
    # travelling wave: each bone lags the one before by the wave delay
    chain = [q.head, *reversed(q.neck), "shoulders", "spine_front", "spine_back", "hips", *q.tail]
    tt = np.linspace(info["start"] + 0.2, info["end"] - 0.5, 2000)

    def sig(b):
        tb, vb = _track(a.bones[b]["rotate"], "rotate")
        return np.interp(tt, tb, vb[:, 0])
    h, hp = sig("shoulders"), sig("hips")
    dt = tt[1] - tt[0]
    lags = np.arange(0, int(0.9 / (info["frequency_hz"] * dt)))
    best = lags[np.argmax([np.dot(h[: len(h) - L], hp[L:]) for L in lags])] * dt
    k = chain.index("hips") - chain.index("shoulders")
    assert best == pytest.approx(k * info["wave_delay"], abs=2.5 * dt), "the wave runs toward the tail"
    assert [e.name for e in a.events] == ["sfx_shake"]


def test_idle_moments_come_from_a_seeded_timer_and_stay_inside_the_loop(dog, tmp_path):
    p, rep = dog
    m = rep["clips"]["idle"]["moments"]
    kinds = {k for k, _ in m}
    assert {"ear_flick", "tail_swish", "blink"} <= kinds
    D = rep["clips"]["idle"]["duration"]
    assert all(0 < t < D - 0.3 for _, t in m)
    ev = sorted((e.time, e.model_extra["string"]) for e in p.data.animations["idle"].events)
    assert ev == sorted((t, k) for k, t in m)
    p2 = G.make_sample_quadruped(tmp_path / "s")
    r2 = G.rig_quadruped(p2, clips=["idle"], seed=7)
    p3 = G.make_sample_quadruped(tmp_path / "t")
    r3 = G.rig_quadruped(p3, clips=["idle"], seed=99)
    assert r2["clips"]["idle"]["moments"] == m, "same seed, same moments"
    assert r3["clips"]["idle"]["moments"] != m


def test_sleep_and_pounce_poses(dog):
    p, rep = dog
    q = p._quad
    sk = p.data
    sl = sk.animations["sleep"]
    _, by = _track(sl.bones["q_body"]["translate"], "translate")
    assert by[:, 1].max() < -0.5 * q.L, "lying down"
    for e in q.eyes:
        _, sy = _track(sl.bones[e]["scale"], "scale")
        assert sy[:, 1].max() < 0.2, "eyes shut"
    assert [e.name for e in sl.events] == ["sfx_sleep", "sfx_sleep"]
    po = sk.animations["pounce"]
    info = rep["clips"]["pounce"]
    names = [(round(e.time, 3), e.name) for e in po.events]
    assert (round(info["launch"], 3), "sfx_pounce") in names
    assert [n for t, n in names if n == "sfx_step"] and min(t for t, n in names if n == "sfx_step") > info["launch"]
    # the hind feet push heels-off, pivoting on their toes: the toe never moves
    for side in "LR":
        lg = q.legs[f"hind_{side}"]
        tr, rt = po.bones[lg["target"]]["translate"], po.bones[lg["target"]]["rotate"]
        ts = np.array([k.time for k in tr])
        T = _interp(tr, "translate", ts)
        R = np.radians(_interp(rt, "rotate", ts)[:, 0])
        v = np.asarray(lg["toe"]) - np.asarray(lg["ankle"])
        toe = np.c_[lg["ankle"][0] + T[:, 0] + np.cos(R) * v[0] - np.sin(R) * v[1],
                    lg["ankle"][1] + T[:, 1] + np.sin(R) * v[0] + np.cos(R) * v[1]]
        assert np.abs(toe - lg["toe"]).max() < 0.01
        assert np.abs(np.degrees(R)).max() > 20


# ------------------------------------------------------------------ rig structure, leg types, convention
def test_digitigrade_legs_have_three_segments_and_a_hock_target(dog):
    p, rep = dog
    sk = p.data
    for leg, info in rep["legs"].items():
        assert len(info["bones"]) == 4 and "hock_target" in info
        assert sk.bone(info["hock_target"]).parent == info["target"], "the hock hangs off the foot target"
        assert sk.bone(info["target"]).parent == "root", "feet are planted in the world, not on the body"
        tc = next(c for c in sk.transform if c.bones == [info["bones"][-1]])
        assert tc.target == info["target"] and tc.mixRotate == 1 and tc.mixX == 0 and tc.mixY == 0
    assert rep["legs"]["hind_R"]["bend_positive"] != rep["legs"]["front_R"]["bend_positive"], \
        "stifle forward, elbow back"
    assert {"tail", "ear_L", "ear_R", "tuft_chest", "tuft_belly"} <= set(rep["strands"])
    assert rep["strands"]["tail"]["parent"] == "hips" and len(rep["strands"]["tail"]["bones"]) == 4
    w = sk.world()
    tail = rep["strands"]["tail"]["bones"]
    assert w[tail[0]].x > w[tail[-1]].x, "the tail is rooted at the hips"
    ear = rep["strands"]["ear_R"]["bones"]
    assert w[ear[0]].y > w[ear[-1]].y, "a floppy ear is rooted at the top of the head"
    assert rep["attached"] == {"collar": "neck1"}


def test_plantigrade_and_unguligrade(tmp_path):
    p = G.make_sample_quadruped(tmp_path / "pl")
    rep = G.rig_quadruped(p, "plantigrade", clips=["walk"])
    sk = p.data
    assert len(sk.ik) == 4 and not any(b.name.endswith("_mid") for b in sk.bones)
    assert sk.slot("hind_mid_R").bone == "hind_R_foot", "the metatarsus rides the flat foot"
    assert all(len(v["bones"]) == 3 for v in rep["legs"].values())
    p2 = G.make_sample_quadruped(tmp_path / "un")
    rep2 = G.rig_quadruped(p2, "unguligrade", clips=["trot"])
    assert all(v["bones"][-1].endswith("_pastern") for v in rep2["legs"].values())
    assert len(p2.data.ik) == 8
    assert rep2["gait_legs"][0]["roll"] > rep["gait_legs"][0]["roll"], "the fetlock flexes hardest"
    for pr in (p, p2):
        assert qa.validate(pr.data)["ok"]


def test_missing_metapodial_layers_are_split_from_the_lower_leg(tmp_path):
    p = G.make_sample_quadruped(tmp_path / "nm", with_mid=False)
    rep = G.rig_quadruped(p, "digitigrade", clips=["walk"])
    sk = p.data
    for leg, info in rep["legs"].items():
        assert info.get("split_metapodial") and len(info["bones"]) == 4
        att = sk.attachment(f"{leg.split('_')[0]}_lower_{leg[-1]}")
        assert att.type == "mesh" and len(att.vertices) != len(att.uvs), "bent by both bones"
    assert qa.validate(sk)["ok"]


def test_layer_convention_errors_and_optional_parts(tmp_path):
    def drop(sk, names):
        sk.slots = [s for s in sk.slots if s.name not in names]
        for n in names:
            sk.skins[0].attachments.pop(n, None)

    p = G.make_sample_quadruped(tmp_path / "x")
    drop(p.data, ("front_lower_L", "head"))
    with pytest.raises(ValueError, match=r"front_lower_L.*|head"):
        G.rig_quadruped(p)
    p = G.make_sample_quadruped(tmp_path / "y")
    drop(p.data, ("tail", "ear_L", "ear_R", "eye_R", "neck"))
    rep = G.rig_quadruped(p, clips=["idle", "alert", "walk", "shake"])
    assert {"tail", "ears", "eyes", "neck"} <= set(rep["skipped"])
    assert qa.validate(p.data)["ok"]
    # case-insensitive, group prefixes, aliases, extra strands
    p = G.make_sample_quadruped(tmp_path / "z")
    sk = p.data
    for s in sk.slots:
        if s.name.startswith("hind_foot"):
            ren = "legs/Hind_Paw_" + s.name[-1]
            sk.skins[0].attachments[ren] = sk.skins[0].attachments.pop(s.name)
            s.name = ren
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (16, 40), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([0, 0, 15, 39], fill=(200, 60, 60, 255))
    for nm, (x, y) in (("wattle", (200, 205)), ("mane_1", (140, 228))):
        p.write_image(nm, im)
        sk.slots.append(Slot(name=nm, bone="root", attachment=nm))
        sk.set_attachment(nm, nm, RegionAttachment(x=x, y=y, width=16, height=40))
    rep = G.rig_quadruped(p, clips=[])
    assert rep["strands"]["wattle"]["parent"] == "head" and rep["strands"]["wattle"]["physics"]
    assert "mane_1" in rep["strands"]
    assert sk.slot("legs/Hind_Paw_R").bone == "hind_R_foot"


def test_bad_options_raise_clear_errors(dog, tmp_path):
    p, _ = dog
    legs = G.quad_gait_legs(p._quad)
    with pytest.raises(ValueError, match="unknown gait"):
        G.plan_gait(p, legs, "q_body", "moonwalk")
    with pytest.raises(ValueError, match="for 6 legs"):
        G.plan_gait(p, legs, "q_body", "tripod")
    with pytest.raises(ValueError, match="duty"):
        G.plan_gait(p, legs, "q_body", "walk", duty=1.2)
    with pytest.raises(ValueError, match="speed"):
        G.plan_gait(p, legs, "q_body", "walk", speed=-3)
    with pytest.raises(ValueError, match="body bone"):
        G.plan_gait(p, legs, "nope", "walk")
    with pytest.raises(ValueError, match="one leg per role"):
        G.plan_gait(p, [legs[0], legs[0], legs[2], legs[3]], "q_body", "walk")
    with pytest.raises(ValueError, match="side unknown"):
        G.plan_gait(p, ["q_body", "hips", "head", "neck1"], "q_body", "walk")
    q = G.make_sample_quadruped(tmp_path / "b")
    with pytest.raises(ValueError, match="leg_type"):
        G.rig_quadruped(q, "hooved")
    with pytest.raises(ValueError, match="unknown clip"):
        G.rig_quadruped(q, clips=["moonwalk"])
    G.rig_quadruped(q, clips=[])
    with pytest.raises(ValueError, match="already rigged"):
        G.rig_quadruped(q)


def test_quad_from_project_rebuilds_the_description(dog, tmp_path):
    p, _ = dog
    from claude_spine.project import Project
    q2 = G.quad_from_project(Project.open(p.path))
    q = p._quad
    assert q2.facing == q.facing and q2.neck == q.neck and q2.tail == q.tail and q2.eyes == q.eyes
    assert [b for b, _ in q2.ears] == [b for b, _ in q.ears] and q2.leg_type == "digitigrade"
    assert q2.L == pytest.approx(q.L, rel=1e-3)


# ------------------------------------------------------------------ the generic gait on other rigs
@needs_node
@pytest.mark.parametrize("kind,legs,gaits", [
    ("hexapod", [f"ik_{s}{k}" for s in "LR" for k in (1, 2, 3)], ("tripod", "wave")),
    ("biped", ["ik_L", "ik_R"], ("walk", "run")),
])
def test_generic_gait_plants_feet_on_other_rigs(tmp_path, kind, legs, gaits):
    p = G.make_gait_test_rig(tmp_path / kind, kind)
    plans = {}
    for g in gaits:
        res = G.gait(p, legs, "body", g, name=g, return_plan=True)
        plans[g] = res["plan"]
        assert len([e for e in p.data.animations[g].events if e.name == "sfx_step"]) == len(legs)
    v = qa.validate(p.data)
    assert v["ok"], v["errors"]
    d = runtime.run(p, animations=list(gaits), fps=60, geometry=True)
    assert d["ok"] and not d["problems"]
    for g, plan in plans.items():
        for i, lg in enumerate(plan.legs):
            slot = lg.target[3:] + "_foot"
            groups = {}
            for f in d["animations"][g]["frames"]:
                t = f["t"]
                ph = plan.phi(i, t)
                if ph < plan.duty:
                    groups.setdefault(math.floor(t / plan.T - plan.phase[i] + 1e-9), []).append(
                        _slot_verts(f, slot) + [plan.facing * plan.speed * t, 0])
            assert groups
            for vs in groups.values():
                V = np.array(vs)
                assert np.abs(V - V.mean(0)).max() < 0.05, f"{kind} {g} {lg.name} slides"
    if kind == "hexapod":
        plan = plans["tripod"]
        t = np.linspace(0, plan.T, 400, endpoint=False)
        idx = {lg.role: i for i, lg in enumerate(plan.legs)}
        a = [plan.contact(idx[r], t) for r in ("L1", "R2", "L3")]
        assert (a[0] == a[1]).all() and (a[1] == a[2]).all(), "a tripod moves as one"
        assert np.all(sum(plan.contact(i, t) for i in range(6)) >= 3), "always at least one tripod down"


def test_leg_names_are_read_from_bone_names():
    assert G.infer_leg("ik_front_R") == ("R", "F")
    assert G.infer_leg("ik_LH") == ("L", "H")
    assert G.infer_leg("ik_L2") == ("L", "M")
    assert G.infer_leg("hind_left_target") == ("L", "H")
    assert G.infer_leg("FR") == ("R", "F")


# ------------------------------------------------------------------ MCP tools
def test_mcp_tools(tmp_path):
    from claude_spine import tools_gait  # noqa: F401  (registers the tools)
    from claude_spine.server import mcp

    def call(tool, **args):
        res = asyncio.run(mcp.call_tool(tool, args))
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)

    listing = call("gait")
    assert {"walk", "trot", "gallop", "tripod", "biped_run"} <= set(listing["gaits"])
    out = call("make_quadruped_sample", out_dir=str(tmp_path / "d"))
    assert "body" in out["slots"] and "validation_errors" not in out
    r = call("rig_quadruped", project=out["project"], leg_type="digitigrade", clips=["idle", "trot"])
    assert r["budget"]["ok"] and set(r["clips"]) == {"idle", "trot"} and "validation_errors" not in r
    g = call("gait", project=out["project"], legs=[x["target"] for x in r["gait_legs"]], body="q_body",
             gait="canter", speed=300, cycles=2)
    assert g["gait"] == "canter" and g["cycles"] == 2 and len(g["steps"]) == 8 and "validation_errors" not in g
    from claude_spine.project import Project
    sk = Project.open(out["project"]).data
    assert {"idle", "trot", "canter"} <= set(sk.animations)
