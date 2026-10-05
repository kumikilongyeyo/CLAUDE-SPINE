"""rig_biped, the character clip contract, secondary motion, squash & stretch and character QA."""
import asyncio
import json
import math

import numpy as np
import pytest

from claude_spine import qa, render, rig, runtime, samples
from claude_spine import qa_character as QC
from claude_spine import rig_body as RB
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project
from claude_spine.timeline import AnimBuilder
from conftest import needs_node


# ------------------------------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def hero(tmp_path_factory):
    """The sample biped, rigged, with the whole contract (read-only for the tests that share it)."""
    p = RB.make_sample_biped(tmp_path_factory.mktemp("hero"))
    rigres = RB.rig_biped(p)
    clips = RB.clip_set(p)
    p.save()
    return p, rigres, clips


@pytest.fixture(scope="module")
def hero_dump(hero):
    if not runtime.available():
        pytest.skip("Node not installed")
    p = hero[0]
    d = runtime.run(p, fps=30, geometry=True)
    assert d["ok"], d.get("error") or d["problems"][:3]
    return d


def fresh(tmp_path, **kw):
    p = RB.make_sample_biped(tmp_path / "b", **kw)
    RB.rig_biped(p)
    return p


def kv(k, f, d):
    v = (k.model_extra or {}).get(f)
    return d if v is None else float(v)


def series(sk, anim, bone, tl):
    ks = sk.animations[anim].bones[bone][tl]
    t = np.array([k.time for k in ks])
    if tl == "rotate":
        return t, np.array([kv(k, "value", 0.0) for k in ks])
    d = 1.0 if tl == "scale" else 0.0
    return t, np.array([[kv(k, "x", d), kv(k, "y", d)] for k in ks])


def slot_verts(draws, slot):
    for d in draws:
        if d["slot"] == slot:
            return np.asarray(d["v"], float).reshape(-1, 2)
    return None


# ------------------------------------------------------------------------------------------ naming
def test_layer_names_and_sides():
    assert RB.split_side("arm_l") == ("arm", "l")
    assert RB.split_side("left_arm") == ("arm", "l")
    assert RB.split_side(RB._norm("Forearm.R")) == ("forearm", "r")
    assert RB.split_side("ear") == ("ear", None)                      # no underscore: not a side
    sk = new_skeleton()
    for n in ("Body", "HEAD", "Arm L", "arm.r", "Thigh_L", "calf_l", "right_leg", "group/Foot R", "eye_r"):
        sk.slots.append(Slot(name=n, bone="root"))
    f = RB.find_parts(sk)
    assert f["torso"] == "Body" and f["head"] == "HEAD" and f["arm_l"] == "Arm L" and f["arm_r"] == "arm.r"
    assert f["thigh_l"] == "Thigh_L" and f["shin_l"] == "calf_l" and f["leg_r"] == "right_leg"
    assert f["foot_r"] == "group/Foot R" and "eye_r" not in f.values()
    assert RB.missing_parts(f) == []
    assert RB.strand_kind("hair_lock_l") == "hair" and RB.strand_kind("belt_tail") == "leather"
    assert RB.strand_kind("Ponytail") == "hair" and RB.strand_kind("cape") == "cloth" and RB.strand_kind("pouch") == "pouch"
    assert RB.strand_kind("tail") == "tail" and RB.strand_kind("torso") is None


def test_missing_required_layers_is_a_clear_error(tmp_path):
    p = RB.make_sample_biped(tmp_path / "b")
    p.data.slots = [s for s in p.data.slots if s.name not in ("leg_l", "head")]
    with pytest.raises(ValueError) as e:
        RB.rig_biped(p)
    msg = str(e.value)
    assert "leg_l (or thigh_l + shin_l)" in msg and "head" in msg and "BIPED_LAYERS" in msg


def test_bad_options(tmp_path):
    p = RB.make_sample_biped(tmp_path / "b")
    with pytest.raises(ValueError):
        RB.rig_biped(p, facing="up")
    with pytest.raises(ValueError):
        RB.rig_biped(p, spine_twist=2)
    RB.rig_biped(p)
    with pytest.raises(ValueError):
        RB.rig_biped(p)                                                 # already rigged
    with pytest.raises(ValueError):
        RB.clip_set(p, ["dance"])
    with pytest.raises(ValueError):
        RB.clip_set(p, intensity=0)
    with pytest.raises(ValueError):
        RB.clip_set(p, blow_from="above")
    with pytest.raises(ValueError):
        RB.clip_set(p, durations={"walk": 0})
    with pytest.raises(ValueError):
        RB.exact_spring(0.05, 0.15, 2)
    with pytest.raises(ValueError):
        RB.make_sample_biped(tmp_path / "c", facing="up")


# ------------------------------------------------------------------------------------------ rig_biped
def test_rig_builds_the_skeleton(hero):
    p, res, _ = hero
    sk = p.data
    for b in ("ground", "hips", "spine1", "spine2", "spine3", "chest", "neck", "head", "shoulder_l", "upper_arm_r",
              "lower_arm_l", "hand_r", "thigh_l", "shin_r", "foot_l", "ik_foot_r", "ik_hand_l", "look_target"):
        assert sk.has_bone(b), b
    assert sk.bone("ik_foot_l").parent == "ground" and sk.bone("foot_l").parent == "ik_foot_l"
    assert sk.bone("ik_hand_r").parent == "arm_space"
    assert {c.name for c in sk.ik} >= {"ik_leg_l", "ik_leg_r", "ik_arm_l", "ik_arm_r", "ik_look"}
    v = qa.validate(sk)
    assert v["ok"], v["errors"]
    assert res["facing"] == "right"
    # one weighted mesh across each joint
    m = res["meshes"]
    assert m["leg_l"]["bones"] == ["hips", "thigh_l", "shin_l", "foot_l"]
    assert m["arm_r"]["bones"] == ["shoulder_r", "upper_arm_r", "lower_arm_r", "hand_r"]
    assert m["torso"]["bones"] == ["hips", "spine1", "spine2", "spine3", "chest"]
    # bones follow the art: the knee sits in the leg's middle, ahead of the hip→ankle line (the art bends forward)
    w = sk.world()
    hip, knee, ank = (np.array(w[b].head) for b in ("thigh_r", "shin_r", "ik_foot_r"))
    assert abs(knee[1] - (hip[1] + ank[1]) / 2) < 12 and knee[0] > (hip[0] + ank[0]) / 2
    assert abs(np.hypot(*(np.array(w["shin_r"].tail) - ank))) < 1e-3          # IK target at the chain tip
    b = qa.budget(sk, "mobile_character")
    assert b["ok"], b["over_budget"]


def test_bend_direction_from_art_and_default(tmp_path):
    bent = fresh(tmp_path / "a")
    ik = {c.name: c.bendPositive for c in bent.data.ik}
    assert ik["ik_leg_r"] is False and ik["ik_arm_r"] is True                # facing right: knee forward, elbow back
    p = RB.make_sample_biped(tmp_path / "s", straight=True)
    res = RB.rig_biped(p)
    assert res["bend"]["leg_r"] == ("negative", "default") and res["bend"]["arm_r"] == ("positive", "default")
    assert any("straight" in n for n in res["notes"])
    p = RB.make_sample_biped(tmp_path / "left", facing="left")
    res = RB.rig_biped(p)
    ik = {c.name: c.bendPositive for c in p.data.ik}
    assert res["facing"] == "left" and ik["ik_leg_r"] is True and ik["ik_arm_r"] is False


@needs_node
def test_rig_keeps_the_setup_pose(tmp_path):
    p = RB.make_sample_biped(tmp_path / "b")
    before = runtime.run(p, fps=1, geometry=True)
    RB.rig_biped(p)
    p.save()
    after = runtime.run(p, fps=1, geometry=True)
    assert after["ok"], after["problems"][:3]
    view = (-140, -10, 140, 450)
    ims = []
    for d in (before, after):
        pages = render._Pages(d["_page_files"], d.get("_pma", False))
        ims.append(np.asarray(render.render_frame(d["setup"]["draws"], pages, view, (280, 460)), float))
    diff = np.abs(ims[0] - ims[1])
    assert diff.mean() < 1.0 and np.percentile(diff, 99.5) < 60          # same picture, edge pixels aside


@needs_node
def test_feet_stay_pinned_while_the_body_bobs(tmp_path):
    p = fresh(tmp_path)
    AnimBuilder(p.data, "bob").bone("hips", "translate", [(0, 0, 0), (0.5, 6, -22), (1, 0, 0)]) \
        .bone("spine2", "rotate", [(0, 0), (0.5, 12), (1, 0)]).bone("chest", "scale", [(0, 1, 1), (0.5, 1.1, 0.9), (1, 1, 1)])
    d = runtime.run(p, animations=["bob"], fps=10, geometry=True)
    assert d["ok"]
    for foot in ("foot_l", "foot_r"):
        v0 = slot_verts(d["setup"]["draws"], foot)
        for fr in d["animations"]["bob"]["frames"]:
            assert np.abs(slot_verts(fr["draws"], foot) - v0).max() < 0.05
    # while the hips really moved
    mid = d["animations"]["bob"]["frames"][5]
    assert np.abs(slot_verts(mid["draws"], "torso") - slot_verts(d["setup"]["draws"], "torso")).max() > 10


def test_breathing(hero):
    p, res, _ = hero
    sk = p.data
    assert "breathe" in res["clips"] and sk.animations["breathe"].duration() == pytest.approx(4.0)
    t, s = series(sk, "breathe", "chest", "scale")
    assert s[:, 0].max() == pytest.approx(1.02, abs=1e-3) and np.allclose(s[:, 0], s[:, 1])
    assert s[np.argmin(np.abs(t - 1.6)), 0] == s[:, 0].max()                   # inhale 40 % of the breath
    _, n = series(sk, "breathe", "neck", "scale")
    assert np.allclose(n[:, 0] * s[:, 0], 1, atol=2e-3)                        # head keeps its size
    H = RB.setup_bounds(p)[3] - RB.setup_bounds(p)[1]
    _, sh = series(sk, "breathe", "shoulder_r", "translate")
    pw = sk.world()["chest"]
    world_up = sh @ np.array([[pw.a, pw.c], [pw.b, pw.d]])                     # parent frame → world
    assert world_up[:, 1].max() == pytest.approx(0.01 * H, rel=0.05)
    th, hd = series(sk, "breathe", "head", "rotate")
    assert hd.min() < -0.5 and hd.max() <= 1e-9                                # counter-nod: down, facing right
    assert th[np.argmin(hd)] > t[np.argmax(s[:, 0])]                           # lags the chest
    for b in ("chest", "neck", "head", "shoulder_r"):
        for tl, ks in sk.animations["breathe"].bones[b].items():
            assert ks[0].model_dump(exclude={"time", "curve"}) == ks[-1].model_dump(exclude={"time", "curve"})


def test_look_at_follower_lags_two_frames(hero):
    p, res, _ = hero
    sk = p.data
    look = res["look_at"]
    assert look["lag_s"] == pytest.approx(2 / 30, abs=1e-3) and look["spine_twist"] == 0.2
    c = next(c for c in sk.physics if c.bone == "look_follow")
    assert c.x == 1 and c.y == 1 and c.inertia == 1
    assert RB.follower_lag(c.strength, c.damping, c.mass) == pytest.approx(2 / 30, abs=0.05 / 30)
    assert c.damping == pytest.approx(math.exp(-2 * math.sqrt(c.strength) / 60), rel=1e-4)   # critically damped
    tcs = {tc.name: tc for tc in sk.transform}
    assert sum(tcs[f"tc_look_{b}"].mixRotate for b in RB.SPINE_CHAIN) == pytest.approx(0.2)
    assert tcs["tc_look_head"].mixRotate == pytest.approx(0.6) and tcs["tc_look_head"].local and tcs["tc_look_head"].relative
    assert tcs["tc_look_eyes"].mixX > 0 and tcs["tc_look_eyes"].mixRotate == 0


@needs_node
def test_look_at_in_the_runtime(tmp_path):
    p = fresh(tmp_path)
    sk = p.data
    w = sk.world()
    E, T0 = np.array(w["look_aim_base"].head), np.array(w["look_target"].head)
    dist = float(np.hypot(*(T0 - E)))

    def off(deg):
        a = math.radians(deg)
        return (dist * (math.cos(a) - 1), dist * math.sin(a))
    # a step to 25 degrees, held; then a steady ramp of the aim angle (constant angular speed)
    pts = [(0, 0, 0), (0.2, 0, 0), (0.21, *off(25)), (1.0, *off(25))]
    ramp = [(1.0 + i / 30, *off(25 - 30 * i / 30)) for i in range(31)]
    AnimBuilder(sk, "look").bone("look_target", "translate", pts + ramp[1:], "linear")
    d = runtime.run(p, animations=["look"], fps=30, geometry=True)
    assert d["ok"]

    def ang(draws, slot):
        v = slot_verts(draws, slot)
        return math.degrees(math.atan2(v[1, 1] - v[0, 1], v[1, 0] - v[0, 0]))

    def in_head(draws):
        """The eye's centre in the head's own frame (the hat rides the head rigidly)."""
        h = slot_verts(draws, "hat")
        u = (h[1] - h[0]) / np.hypot(*(h[1] - h[0]))
        e = slot_verts(draws, "eye_r").mean(0) - h[0]
        return np.array([e @ u, e @ np.array([-u[1], u[0]])])
    fr = d["animations"]["look"]["frames"]
    ts = np.array([f["t"] for f in fr])
    h0 = ang(d["setup"]["draws"], "hat")
    head = np.array([ang(f["draws"], "hat") - h0 for f in fr])
    eye = np.array([in_head(f["draws"]) for f in fr]) - in_head(d["setup"]["draws"])
    settled = int(np.argmin(np.abs(ts - 0.95)))
    # settled: the head turned 80 % of the aim (60 % own + 20 % spine), toward the target (up = counter-clockwise)
    assert head[settled] == pytest.approx(0.8 * 25, rel=0.08)
    k = int(np.argmin(np.abs(ts - 0.2333)))                                     # first frame after the step
    assert np.hypot(*eye[k]) > 0.9 * np.hypot(*eye[settled])                    # eyes move at once
    assert head[k] < 0.75 * head[settled]                                       # the head is still catching up
    # on the ramp the head runs 2 frames behind the target
    aim = lambda t: np.interp(t, [0, 1.0, 2.0], [25, 25, -5])                  # noqa: E731
    sel = (ts > 1.35) & (ts < 1.95)
    lags = np.linspace(0, 5 / 30, 51)
    err = [np.mean((head[sel] - 0.8 * aim(ts[sel] - L)) ** 2) for L in lags]
    assert lags[int(np.argmin(err))] == pytest.approx(2 / 30, abs=0.5 / 30)


# ------------------------------------------------------------------------------------------ the contract
def test_contract_is_complete_and_valid(hero):
    p, _, clips = hero
    sk = p.data
    assert set(clips["clips"]) == set(RB.CHARACTER_CLIPS) and not clips["skipped"]
    v = qa.validate(sk)
    assert v["ok"], v["errors"]
    for name, spec in RB.CHARACTER_CLIPS.items():
        a = sk.animations[name]
        assert a.duration() == pytest.approx(spec["length"], abs=1e-3), name
        got = [e.name for e in a.events]
        assert sorted(got) == sorted(spec["events"]), (name, got)


def test_loops_close_and_one_shots_end_on_setup(hero):
    p, _, _ = hero
    sk = p.data
    rest = {"rotate": {"value": 0.0}, "translate": {"x": 0.0, "y": 0.0}, "scale": {"x": 1.0, "y": 1.0}}
    for name, spec in RB.CHARACTER_CLIPS.items():
        a = sk.animations[name]
        for bone, tls in a.bones.items():
            for tl, ks in tls.items():
                first, last = ks[0], ks[-1]
                fields = list(rest[tl])
                if spec["loop"]:
                    for fl in fields:
                        assert kv(first, fl, rest[tl][fl]) == pytest.approx(kv(last, fl, rest[tl][fl]), abs=1e-6), (name, bone, tl)
                    assert last.time == pytest.approx(spec["length"])
                else:
                    for fl in fields:
                        assert kv(last, fl, rest[tl][fl]) == pytest.approx(rest[tl][fl], abs=1e-6), (name, bone, tl)
        for sl, tls in a.slots.items():
            for tl, ks in tls.items():
                if tl == "rgba" and not spec["loop"]:
                    assert ks[-1].model_extra["color"] == sk.slot(sl).color.upper()
        # the artist's bones are only keyed through rig bones: no key on a slot's art bone that rig_biped did not make
        assert all(sk.has_bone(b) for b in a.bones)


def test_clip_set_never_moves_the_setup(tmp_path):
    p = fresh(tmp_path)
    w0 = {b.name: (round(v.x, 3), round(v.y, 3), round(v.rotation, 2)) for b, v in
          ((b, p.data.world()[b.name]) for b in p.data.bones)}
    RB.clip_set(p)
    w1 = p.data.world()
    for n, (x, y, r) in w0.items():
        assert (round(w1[n].x, 3), round(w1[n].y, 3)) == (x, y) and abs(_wrapd(w1[n].rotation - r)) < 0.02, n
    assert p.data.bone("spine1").parent == "ss_spine1"                       # the squash carrier, inserted once


def _wrapd(a):
    return (a + 180) % 360 - 180


def test_walk_is_a_treadmill(hero):
    p, _, clips = hero
    sk = p.data
    info = clips["clips"]["walk"]
    v = info["ground_speed"]
    steps = [e for e in sk.animations["walk"].events if e.name == "sfx_step"]
    assert [e.model_extra["string"] for e in steps] == ["foot_r", "foot_l"]
    assert [e.time for e in steps] == [0.0, 0.5]
    assert all(e.model_extra["float"] == pytest.approx(v) for e in steps)
    t, xy = series(sk, "walk", "ik_foot_r", "translate")
    _, rot = series(sk, "walk", "ik_foot_r", "rotate")
    beta = info["stance"]
    flat = (t > 0.12 * beta + 0.02) & (t < beta - 0.3 * beta - 0.02)          # between the heel and toe rockers
    vel = np.diff(xy[flat, 0]) / np.diff(t[flat])
    assert np.allclose(vel, -v, rtol=0.01)                                    # planted foot rides the ground at -v
    assert np.allclose(xy[flat, 1], 0, atol=1e-3) and np.allclose(rot[flat], 0, atol=1e-3)
    # inverted pendulum: hips higher at the passing pose (mid stance) than at the contact
    th, hy = series(sk, "walk", "hips", "translate")
    hy = hy[:, 1]
    assert np.interp(0.3, th, hy) > np.interp(0.06, th, hy) + 3
    assert hy[0] == hy[-1]


def test_run_has_a_ballistic_flight(hero):
    p, _, clips = hero
    sk = p.data
    info = clips["clips"]["run"]
    D, beta = 0.6, info["stance"]
    t, hy = series(sk, "run", "hips", "translate")
    hy = hy[:, 1]
    Ts = beta * D
    fl = (t > Ts + 0.005) & (t < D / 2 - 0.005)
    tt, yy = t[fl], hy[fl]
    c = np.polyfit(tt, yy, 2)
    assert -2 * c[0] == pytest.approx(info["gravity"], rel=0.02)              # constant gravity in the flight
    assert yy.max() > np.interp(Ts / 2, t, hy) + 10                            # highest in the air, lowest mid-stance


def test_land_squash_and_overshoot_are_exact(hero):
    p, _, clips = hero
    sk = p.data
    info = clips["clips"]["land"]
    car = info["carrier"]
    t, s = series(sk, "land", car, "scale")
    along, across = s[:, 0], s[:, 1]
    assert along.min() == pytest.approx(0.85, abs=1e-3) and t[np.argmin(along)] == pytest.approx(info["t_squash"], abs=1e-3)
    after = t > info["t_squash"]
    assert along[after].max() == pytest.approx(1.05, abs=1e-3)
    assert np.allclose(across, along ** -0.5, atol=2e-3)                      # volume kept (a cylinder)
    assert along[-1] == 1 and across[-1] == 1
    zeta = math.log(3) / math.sqrt(math.pi ** 2 + math.log(3) ** 2)
    assert info["zeta"] == pytest.approx(zeta, abs=1e-5)
    assert [e.name for e in sk.animations["land"].events] == ["sfx_land"] and sk.animations["land"].events[0].time == 0


def test_hit_anticipates_against_the_blow(hero):
    p, _, clips = hero
    sk = p.data
    info = clips["clips"]["hit"]
    d = info["blow_dir"]                                                       # -1: from the front, pushes back
    t, r1 = series(sk, "hit", "spine1", "rotate")
    ta = info["impact"]
    ant = r1[(t > 0) & (t < ta)]
    rec = r1[t > ta + 0.03]
    # a lean of +a moves the top toward -x; the recoil goes WITH the push (-d * angle), anticipation against it
    assert np.sign(ant[np.argmax(np.abs(ant))]) == np.sign(d)
    assert np.sign(rec[np.argmax(np.abs(rec))]) == -np.sign(d)
    assert np.abs(rec).max() > 4 * np.abs(ant).max()
    e = sk.animations["hit"].events[0]
    assert e.name == "sfx_hit" and e.time == pytest.approx(2 / 30, abs=1e-3)
    # head whips later than the hips: lag by levels
    th, hr = series(sk, "hit", "head", "rotate")
    assert th[np.argmax(np.abs(hr))] > t[np.argmax(np.abs(r1))]


def test_attack_winds_up_opposite_the_strike(hero):
    p, _, clips = hero
    sk = p.data
    info = clips["clips"]["attack"]
    hand = f"ik_hand_{info['hand']}"
    assert info["hand"] == "r"                                                 # the near arm is drawn in front
    t, xy = series(sk, "attack", hand, "translate")
    assert xy[np.argmin(np.abs(t - info["wind_up"])), 0] < -10                 # pulled back (facing right)
    assert xy[np.argmin(np.abs(t - info["impact"])), 0] > 40                   # struck forward
    ev = {e.name: e.time for e in sk.animations["attack"].events}
    assert ev["sfx_attack"] == ev["attack_hit"] == pytest.approx(info["impact"], abs=1e-3)


def test_jump_and_win_fly_on_parabolas(hero):
    p, _, clips = hero
    sk = p.data
    for name in ("jump", "win"):
        info = clips["clips"][name]
        t, g = series(sk, name, "ground", "translate")
        air = (t > info["take_off"] + 0.01) & (t < info["touch_down"] - 0.01)
        c = np.polyfit(t[air], g[air, 1], 2)
        assert -2 * c[0] == pytest.approx(info["gravity"], rel=0.02)
        assert g[air, 1].max() == pytest.approx(info["apex"], rel=0.03)
        ev = [(e.name, e.time) for e in sk.animations[name].events]
        assert ev[0][1] == pytest.approx(info["take_off"]) and ev[-1] == ("sfx_step", pytest.approx(info["touch_down"]))


def test_strands_get_a_headwind_only_while_moving(hero):
    p, _, _ = hero
    sk = p.data
    a = sk.animations
    cape = next(c.name for c in sk.physics if c.bone.startswith("cape"))
    run = [k.model_extra["value"] for k in a["run"].physics[cape]["wind"]]
    walk = [k.model_extra["value"] for k in a["walk"].physics[cape]["wind"]]
    assert np.mean(run) < np.mean(walk) < 0                                     # blows back (facing right), ~ v^2
    assert np.mean(run) / np.mean(walk) == pytest.approx((332.75 / 107.5) ** 2, rel=0.15)
    assert run[0] == run[-1]
    assert all(k.model_extra["value"] == 0 for k in a["idle"].physics[cape]["wind"])


@needs_node
def test_every_clip_plays_in_spine_core(hero, hero_dump):
    p, _, _ = hero
    d = hero_dump
    assert set(RB.CHARACTER_CLIPS) | {"breathe"} <= set(d["animations"])
    ev = [e["name"] for e in d["animations"]["walk"]["events"]]
    assert ev.count("sfx_step") >= 2
    assert any(e["name"] == "attack_hit" for e in d["animations"]["attack"]["events"])


# ------------------------------------------------------------------------------------------ other rigs
def test_clip_set_on_another_rig_skips_and_reports(tmp_path):
    p = samples.make_character(tmp_path / "mascot")
    rig.add_ik(p.data, ["arm_r1", "arm_r2"])
    rig.add_ik(p.data, ["arm_l1", "arm_l2"])
    res = RB.clip_set(p, bone_map={"hips": "hip", "ik_hand_r": "arm_r2_ik", "ik_hand_l": "arm_l2_ik"})
    assert set(res["skipped"]) == {"walk", "run"}
    assert "thigh_l" in res["skipped"]["walk"] and "ik_foot_r" in res["skipped"]["run"]
    assert {"idle", "idle_fidget", "jump", "land", "hit", "attack", "win", "lose", "talk"} <= set(res["clips"])
    assert p.data.has_bone("ground")                                           # inserted for the hops
    assert qa.validate(p.data)["ok"]
    with pytest.raises(KeyError):
        RB.clip_set(p, bone_map={"hips": "no_such_bone"})


@needs_node
def test_split_limbs_rig_without_cracks(tmp_path):
    p = RB.make_sample_biped(tmp_path / "split", split_limbs=True)
    res = RB.rig_biped(p)
    assert res["parts"]["thigh_l"] == "thigh_l" and res["meshes"]["shin_r"]["bones"] == ["thigh_r", "shin_r", "foot_r"]
    RB.clip_set(p, ["walk", "attack", "land"])
    p.save()
    r = QC.qa_character(p, ["walk", "attack", "land"])
    assert r["worst_crack"] <= 0.08, r["cracks"]
    assert r["worst_slide"] < 1.0, r["foot_slide"]
    assert {"knee_l", "elbow_r"} <= set(r["joints_checked"])


# ------------------------------------------------------------------------------------------ secondary
def test_secondary_finds_strands_by_name_and_shape(tmp_path):
    p = RB.make_sample_biped(tmp_path / "b")
    from claude_spine.rig_body import _part
    _part(p, p.data, "streamer_thing_x", [("capsule", [(60, 200), (110, 196)], 8)], (200, 200, 60), (150, 150, 30))
    _part(p, p.data, "sword", [("capsule", [(-60, 120), (-60, 230)], 8)], (200, 200, 220), (120, 120, 140))
    _part(p, p.data, "unnamed_flag", [("capsule", [(70, 250), (140, 252)], 10)], (60, 60, 200), (30, 30, 120))
    p.save()
    res = RB.rig_biped(p)
    st = res["secondary"]["strands"]
    assert st["ponytail"]["preset"] == "hair" and st["ponytail"]["parent"] == "head" and len(st["ponytail"]["bones"]) == 4
    assert st["cape"]["preset"] == "cloth" and st["cape"]["parent"] == "chest"
    assert st["belt_tail"]["preset"] == "leather" and st["belt_tail"]["parent"] == "hips"
    assert st["pouch"]["preset"] == "pouch" and len(st["pouch"]["bones"]) == 1
    assert st["streamer_thing_x"]["preset"] == "silk"
    assert st["unnamed_flag"]["by"] == "shape" and st["unnamed_flag"]["preset"] == "cloth"
    assert st["unnamed_flag"]["root_end"] == "left"                           # the end that overlaps the body
    assert "sword" not in st
    sk = p.data
    damp = {c.bone: c.damping for c in sk.physics}
    assert damp["cape_1"] < damp["ponytail_1"]                                 # cloth settles faster than hair
    assert RB._preset_values("chain")["strength"] / RB._preset_values("chain")["mass"] < \
        RB._preset_values("hair")["strength"] / RB._preset_values("hair")["mass"]   # a chain swings slower
    assert qa.validate(sk)["ok"]


def test_secondary_presets_and_errors(tmp_path):
    p = RB.make_sample_biped(tmp_path / "b")
    RB.rig_biped(p, secondary_motion=False)
    assert not any(c.bone.startswith("cape") for c in p.data.physics)
    assert p.data.slot("cape").bone != "root"                                   # attached rigidly instead
    with pytest.raises(ValueError):
        RB.secondary(p, presets={"cape": "jelly"})
    res = RB.secondary(p, presets={"cape": "silk"}, slots=["cape"])
    assert res["strands"]["cape"]["preset"] == "silk" and len(res["strands"]["cape"]["bones"]) == 5
    assert set(RB.SECONDARY_PRESETS) >= {"hair", "silk", "leather", "chain", "feather"}
    for k, spec in RB.SECONDARY_PRESETS.items():
        assert spec["base"] in rig.PHYSICS_PRESETS, k


# ------------------------------------------------------------------------------------------ squash_stretch
def _tail_rig(tmp_path):
    sk = new_skeleton()
    sk.bones.append(Bone(name="body", parent="root"))
    rig.add_chain(sk, "tail", [[0, 0], [40, 10], [80, 20], [120, 30]], parent="body")
    p = Project(tmp_path / "t.json", sk)
    return p


def test_squash_stretch_on_any_chain(tmp_path):
    p = _tail_rig(tmp_path)
    sk = p.data
    w0 = {b: sk.world()[b].tail for b in ("tail1", "tail2", "tail3")}
    res = RB.squash_stretch(p, ["tail1", "tail2", "tail3"], "wag", start=0.2, squash=0.8, overshoot=1.1, hz=3)
    car = res["carrier"]
    assert car == "ss_tail1" and sk.bone("tail1").parent == car
    assert sk.world()[car].rotation == pytest.approx(math.degrees(math.atan2(30, 120)), abs=0.01)   # along the chain
    for b, tl in w0.items():
        assert np.allclose(sk.world()[b].tail, tl, atol=1e-3)                  # setup unchanged
    t, s = series(sk, "wag", car, "scale")
    assert s[:, 0].min() == pytest.approx(0.8, abs=1e-3) and s[:, 0].max() == pytest.approx(1.1, abs=1e-3)
    assert t[np.argmin(s[:, 0])] == pytest.approx(res["t_first"], abs=2e-3) and t[0] == pytest.approx(0.2)
    assert np.allclose(s[:, 1], s[:, 0] ** -0.5, atol=2e-3) and tuple(s[-1]) == (1, 1)
    # stretch first, area mode, merged into the same carrier (multiplied)
    r2 = RB.squash_stretch(p, ["tail1", "tail2", "tail3"], "wag", start=0.2, squash=1.2, overshoot=0.9, volume="area")
    assert r2["carrier"] == car and r2["extremes"] == [1.2, 0.9]
    assert qa.validate(sk)["ok"]
    with pytest.raises(ValueError):
        RB.squash_stretch(p, ["tail1"], "x", squash=0.8, overshoot=0.9)       # same side of 1
    with pytest.raises(ValueError):
        RB.squash_stretch(p, ["tail1"], "x", squash=0.9, overshoot=1.2)       # overshoot bigger than the squash
    with pytest.raises(ValueError):
        RB.squash_stretch(p, ["tail1"], "x", volume="4d")
    with pytest.raises(ValueError):
        RB.squash_stretch(p, ["root"], "x")


@needs_node
def test_squash_plays_and_keeps_volume_in_the_runtime(tmp_path):
    from PIL import Image
    p = _tail_rig(tmp_path)
    im = Image.new("RGBA", (40, 120), (200, 80, 60, 255))
    p.write_image("blob", im)
    p.data.slots.append(Slot(name="blob", bone="body", attachment="blob"))
    p.data.set_attachment("blob", "blob", RegionAttachment(x=0, y=60, width=40, height=120))
    rig.add_chain(p.data, "up", [[0, 0], [0, 120]], parent="body")
    from claude_spine.rig import reparent_slot
    reparent_slot(p.data, "blob", "up1")
    RB.squash_stretch(p, ["up1"], "boing", squash=0.85, overshoot=1.05)
    p.save()
    d = runtime.run(p, animations=["boing"], fps=60, geometry=True)
    assert d["ok"]
    hs, ws = [], []
    for fr in d["animations"]["boing"]["frames"]:
        v = slot_verts(fr["draws"], "blob")
        hs.append(np.ptp(v[:, 1]))
        ws.append(np.ptp(v[:, 0]))
    hs, ws = np.array(hs) / 120, np.array(ws) / 40
    assert hs.min() == pytest.approx(0.85, abs=0.01) and ws.max() == pytest.approx(0.85 ** -0.5, abs=0.01)
    assert np.allclose(ws * ws * hs, 1, atol=0.01)                              # volume of a cylinder: r^2 h


# ------------------------------------------------------------------------------------------ character QA
@needs_node
def test_qa_is_clean_on_the_sample(hero, hero_dump):
    p, _, _ = hero
    r = QC.qa_character(p, dump=hero_dump)
    assert r["ok"], r["fix"]
    assert r["worst_slide"] < 1.0 and r["worst_crack"] <= 0.08
    assert len(r["joints_checked"]) == 13 and r["feet_checked"] == ["foot_l", "foot_r"]
    assert r["budget"]["rig_type"] == "biped" and r["budget"]["ok"]


@needs_node
def test_qa_catches_foot_slide(tmp_path):
    p = fresh(tmp_path)
    RB.clip_set(p, ["walk"])
    # a treadmill at 70 % of the declared ground speed: the planted foot skates
    for k in p.data.animations["walk"].bones["ik_foot_r"]["translate"]:
        if "x" in k.model_extra:
            k.model_extra["x"] *= 0.7
    p.save()
    r = QC.qa_character(p, ["walk"])
    bad = {s["foot"]: s for s in r["foot_slide"]}
    assert "foot_r" in bad and "foot_l" not in bad and bad["foot_r"]["max_drift"] > 5
    assert any("foot_r slides" in f for f in r["fix"])


def _two_part_limb(tmp_path, weighted: bool):
    """Two square-ended 24 px bars on a 2-bone chain (or one bar weighted across both), bent 70 degrees."""
    from PIL import Image
    from claude_spine.mesh import rig_mesh
    sk = new_skeleton()
    p = Project(tmp_path / "limb.json", sk)
    sk.add_bone_world("upper", "root", 0, 0, 0, 100)
    sk.add_bone_world("lower", "upper", 100, 0, 0, 100)
    if weighted:
        p.write_image("bar", Image.new("RGBA", (200, 24), (220, 160, 120, 255)))
        sk.slots.append(Slot(name="bar", bone="upper", attachment="bar"))
        sk.set_attachment("bar", "bar", RegionAttachment(x=100, y=0, width=200, height=24))
        rig_mesh(p, "bar", bones=["upper", "lower"])
        joints = [{"name": "elbow", "a": "bar", "b": "bar", "bone": "lower"}]
    else:
        for nm, x in (("a", 50), ("b", 150)):
            p.write_image(nm, Image.new("RGBA", (100, 24), (220, 160, 120, 255)))
        sk.slots.append(Slot(name="a", bone="upper", attachment="a"))
        sk.set_attachment("a", "a", RegionAttachment(x=50, y=0, width=100, height=24))
        sk.slots.append(Slot(name="b", bone="lower", attachment="b"))
        sk.set_attachment("b", "b", RegionAttachment(x=50, y=0, width=100, height=24))
        joints = [{"name": "elbow", "a": "a", "b": "b", "bone": "lower"}]
    AnimBuilder(sk, "bend").bone("lower", "rotate", [(0, 0), (1, 70)], "linear")
    p.save()
    return p, joints


@needs_node
def test_qa_catches_a_joint_crack_and_passes_the_weighted_fix(tmp_path):
    p, joints = _two_part_limb(tmp_path / "split", weighted=False)
    d = runtime.run(p, fps=10, geometry=True)
    cr = QC.joint_cracks(p, d, joints)
    assert not cr[0]["ok"] and cr[0]["crack"] > 0.15 and cr[0]["at"] > 0.3
    p2, joints2 = _two_part_limb(tmp_path / "mesh", weighted=True)
    d2 = runtime.run(p2, fps=10, geometry=True)
    cr2 = QC.joint_cracks(p2, d2, joints2)
    assert cr2[0]["ok"] and cr2[0]["crack"] < 0.05 and cr2[0]["single_mesh"]


def test_bone_budget_per_rig_type():
    assert set(QC.RIG_BUDGETS) == {"biped", "quadruped", "flier", "serpent", "face"}
    sk = new_skeleton()
    rig.add_chain(sk, "seg", [[i * 10, 0] for i in range(60)])
    assert QC.rig_type(sk) == "serpent"
    b = QC.bone_budget(sk)
    assert not b["ok"] and "bones" in b["over_budget"] and "depth" in b["over_budget"] and b["tips"]
    q = new_skeleton()
    for n in ("spine", "front_leg_l", "front_leg_r", "hind_leg_l", "hind_leg_r", "tail1"):
        q.bones.append(Bone(name=n, parent="root"))
    assert QC.rig_type(q) == "quadruped"
    fl = new_skeleton()
    fl.bones.append(Bone(name="wing_l1", parent="root"))
    assert QC.rig_type(fl) == "flier"
    with pytest.raises(ValueError):
        QC.bone_budget(sk, "octopus")


def test_hero_budget(hero):
    p, res, _ = hero
    b = QC.bone_budget(p.data)
    assert b["rig_type"] == "biped" and b["ok"], b["over_budget"]
    assert res["counts"]["bones"] <= QC.RIG_BUDGETS["biped"]["bones"]


# ------------------------------------------------------------------------------------------ MCP tools
def test_mcp_tools(tmp_path):
    from claude_spine import tools_body  # noqa: F401  registers the tools
    from claude_spine.server import mcp

    def call(name, **args):
        res = asyncio.run(mcp.call_tool(name, args))
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)
    made = call("make_biped_sample", out_dir=str(tmp_path / "t"))
    proj = made["project"]
    assert made["parts"]["torso"] == "torso"
    r = call("rig_biped", project=proj)
    assert "validation_errors" not in r and r["facing"] == "right" and r["budget_mobile_character"]["bones"] > 30
    c = call("clip_set", project=proj, clips=["idle", "walk", "land"], intensity=1.2)
    assert set(c["clips"]) == {"idle", "walk", "land"} and "validation_errors" not in c
    s = call("squash_stretch", project=proj, chain=["spine1", "spine2", "spine3", "chest"], clip="boing",
             squash=1.15, overshoot=0.95)
    assert s["carrier"] == "ss_spine1" and s["extremes"] == [1.15, 0.95]
    sec = call("secondary", project=proj, slots=["hat"], presets={"hat": "feather"})
    assert "hat" in sec["strands"] or "hat" in sec["skipped"] or sec["strands"] == {}
    if runtime.available():
        q = call("qa_character", project=proj, animations=["walk", "land"])
        assert q["ok"], q["fix"]
