"""Chain rigs (rig_serpent, rig_flier) and the attach_rig add-ons: structure, the clip contract (exact loops,
one-shots on setup, merge by name), the modelled physics read back from the keys, and spine-core playback."""
import asyncio
import json
import math

import numpy as np
import pytest

from claude_spine import qa, rig_addons as A, rig_chain as C, runtime
from claude_spine.ir import new_skeleton
from claude_spine.project import Project
from conftest import needs_node


# ---------------------------------------------------------------- helpers
def _vals(k, tl):
    if tl == "rotate":
        return (C.key_val(k, "value", 0.0),)
    if tl in ("translate", "shear"):
        return (C.key_val(k, "x", 0.0), C.key_val(k, "y", 0.0))
    if tl == "scale":
        return (C.key_val(k, "x", 1.0), C.key_val(k, "y", 1.0))
    if tl == "rgba":
        return (k.color,)
    if tl == "attachment":
        return (getattr(k, "name", None),)
    return (getattr(k, "value", 0.0),)


def _shown(sk, a, slot, t):
    ks = a.slots.get(slot, {}).get("attachment")
    if not ks:
        return sk.slot(slot).attachment is not None
    before = [k for k in ks if k.time <= t + 1e-6]
    return getattr(before[-1] if before else ks[0], "name", None) is not None


def assert_loop(sk, anim):
    """Every timeline closes (a bone whose slots are hidden at both ends may differ: nothing shows)."""
    a = sk.animations[anim]
    D = a.duration()
    for bn, tls in a.bones.items():
        mine = [s.name for s in sk.slots if s.bone == bn]
        if mine and not any(_shown(sk, a, s, 0.0) or _shown(sk, a, s, D) for s in mine):
            continue
        for tl, ks in tls.items():
            if len(ks) > 1:                            # a timeline that ends early holds its last value: it must match too
                a0, a1 = _vals(ks[0], tl), _vals(ks[-1], tl)
                if tl == "rotate":                    # whole turns are the same pose
                    a0, a1 = ((a0[0] - a1[0] + 180) % 360 - 180,), (0.0,)
                assert a0 == pytest.approx(a1, abs=1e-3), f"{anim}/{bn}/{tl} does not close"
    for sn, tls in a.slots.items():
        for tl, ks in tls.items():
            if tl == "rgba" and len(ks) > 1:
                assert ks[0].color == ks[-1].color, f"{anim}/{sn} colour does not close"


def assert_rest_at_end(sk, anim, bones=None):
    a = sk.animations[anim]
    for bn, tls in a.bones.items():
        if bones is not None and bn not in bones:
            continue
        for tl, ks in tls.items():
            rest = (1.0, 1.0) if tl == "scale" else ((0.0,) if tl == "rotate" else (0.0, 0.0))
            assert _vals(ks[-1], tl) == pytest.approx(rest, abs=1e-3), f"{anim}/{bn}/{tl} does not end on setup"


def rot(sk, anim, bone):
    ks = sk.animations[anim].bones[bone]["rotate"]
    return np.array([k.time for k in ks]), np.array([C.key_val(k, "value", 0.0) for k in ks])


def run(p, anims, fps=10):
    d = runtime.run(p, animations=anims, fps=fps, geometry=True)
    assert d.get("ok", True) and not d.get("problems"), d.get("problems") or d.get("error")
    return d


def slot_verts(dump, anim, slot):
    out = []
    for f in dump["animations"][anim]["frames"]:
        for dr in f["draws"]:
            if dr["slot"] == slot:
                out.append(np.asarray(dr["v"], float).reshape(-1, 2))
    return out


@pytest.fixture
def koi(tmp_path):
    p = C.make_sample_serpent(tmp_path / "koi")
    return p, C.rig_serpent(p)


@pytest.fixture
def tentacle(tmp_path):
    p = C.make_sample_serpent(tmp_path / "tent", "tentacle")
    return p, C.rig_serpent(p, mode="tentacle", n_bones=10)


@pytest.fixture
def bird(tmp_path):
    p = C.make_sample_flier(tmp_path / "bird")
    return p, C.rig_flier(p)


def host(tmp_path, kinds, parts=None, **opts):
    p = A.make_sample_host(tmp_path / ("h_" + "_".join(kinds)), parts or kinds)
    res = {k: A.attach_rig(p, k, options=opts.get(k)) for k in kinds}
    return p, res


# ================================================================ rig_serpent
def test_serpent_builds_validates_and_recognises_parts(koi):
    p, r = koi
    sk = p.data
    assert qa.validate(sk)["ok"], qa.validate(sk)["errors"]
    assert len(r["bones"]) == 8 and r["riders"] == ["head", "eye"]
    assert set(r["fins"]) == {"fin_dorsal", "fin_pectoral", "tail_fin"} and len(r["physics"]) == 6
    assert r["fins"]["tail_fin"][0] in [b.name for b in sk.bones if b.parent == r["bones"][-1]]
    w = sk.world()
    assert w[r["bones"][0]].x > w[r["bones"][-1]].x, "the chain runs head (right) -> tail"
    assert set(r["clips"]) == {"swim", "idle_float", "turn"}
    assert all(s.blend == "normal" for s in sk.slots)
    b = qa.budget(sk, "mobile_character")
    assert b["ok"], b["over_budget"]


def test_serpent_swim_loops_exactly_and_speed_sets_the_beat(koi, tmp_path):
    p, r = koi
    sk = p.data
    for a in ("swim", "idle_float"):
        assert_loop(sk, a)
    sw = r["clips"]["swim"]
    assert sw["frequency"] == pytest.approx(1.0 / (0.7 * 1.0), rel=1e-3), "f = U / (slip lambda)"
    assert sw["length"] == pytest.approx(2 / sw["frequency"], abs=1e-3)
    ev = [e.time for e in sk.animations["swim"].events if e.name == "sfx_swim"]
    assert np.diff(ev) == pytest.approx([1 / sw["frequency"]], abs=1e-3), "one sfx_swim per tail beat"
    assert sw["tail_amplitude"] == pytest.approx(0.3 * 0.7 * 1.0 / 2 * 1.5 * r["length"], rel=1e-3), "Strouhal 0.3"
    q = C.make_sample_serpent(tmp_path / "fast")
    r2 = C.rig_serpent(q, speed=2.0)
    assert r2["clips"]["swim"]["frequency"] == pytest.approx(2 * sw["frequency"], rel=1e-3)


def test_serpent_wave_grows_toward_the_tail_and_travels_head_to_tail(koi):
    p, r = koi
    sk = p.data
    D = sk.animations["swim"].duration()
    f = r["clips"]["swim"]["frequency"]
    fr = sk.world()[r["frame"]]
    ts = np.linspace(0, D, 141)
    joints = r["bones"] + ["tip"]
    lat = np.zeros((len(ts), len(joints)))
    for i, t in enumerate(ts):
        w = C.pose_world(sk, "swim", t)
        for j, b in enumerate(r["bones"]):
            lat[i, j] = fr.to_local(*w[b].head)[1]
        lat[i, -1] = fr.to_local(*w[r["bones"][-1]].tail)[1]
    amp = lat.max(0) - lat.min(0)
    assert np.all(np.diff(amp[1:]) > 0), f"amplitude grows toward the tail: {amp.round(1)}"
    assert amp[-1] > 4 * amp[0]
    # the crest reaches each joint later: phase from a one-frequency fit, unwrapped along the body
    ph = [math.atan2(*np.linalg.lstsq(np.c_[np.sin(2 * math.pi * f * ts), np.cos(2 * math.pi * f * ts)], lat[:, j], rcond=None)[0][::-1])
          for j in range(len(joints))]
    lagd = np.diff(np.unwrap(ph))
    assert np.all(lagd[2:] < 0) or np.all(lagd[2:] > 0), "the phase moves monotonically down the body (a travelling wave)"


def test_serpent_turn_is_a_c_start_that_ends_on_setup(koi):
    p, r = koi
    sk = p.data
    a = sk.animations["turn"]
    assert_rest_at_end(sk, "turn")
    t1 = r["clips"]["turn"]["stage1_end"]
    bend = sum(C.sample(sk, "turn", b, "rotate", t1)[0] for b in r["bones"][1:])
    share = sum(sk.bone(b).length for b in r["bones"][1:]) / r["length"]
    assert bend == pytest.approx(150 * share, rel=0.02), "stage 1: the body curls into a 150 degree C"
    t2 = r["clips"]["turn"]["stage2_end"]
    back = sum(C.sample(sk, "turn", b, "rotate", t2)[0] for b in r["bones"][1:])
    assert back < 0 < bend, "stage 2: the tail stroke throws the bend the other way"
    assert [e.time for e in a.events if e.name == "sfx_turn"] == [pytest.approx(t1, abs=1e-3)]


def test_tentacle_reach_ik_springs_and_returns(tentacle):
    p, r = tentacle
    sk = p.data
    ik = next(c for c in sk.ik if c.name == r["reach_ik"]["constraint"])
    assert ik.mix == 0, "the setup pose never moves"
    ks = sk.animations["reach"].ik[ik.name]
    mixes = [C.key_val(k, "mix", 0.0) for k in ks]
    assert mixes[0] == 0 and mixes[-1] == 0 and max(mixes) == pytest.approx(1.0, abs=1e-3)
    assert_rest_at_end(sk, "reach")
    t, v = rot(sk, "reach", r["bones"][3])
    turn = r["clips"]["reach"]["turns"][3]
    assert v.max() / turn == pytest.approx(1 + C.spring_overshoot(0.42), rel=0.01), "the strike overshoots like an exact spring"
    assert v.min() < 0, "it winds up the other way first"
    assert [e.name for e in sk.animations["reach"].events] == ["sfx_reach"]
    assert qa.validate(sk)["ok"]


def test_serpent_bad_options_are_clear_errors(tmp_path):
    p = C.make_sample_serpent(tmp_path / "k")
    for kw, msg in ((dict(mode="fly"), "mode"), (dict(speed=0), "speed"), (dict(n_bones=2), "n_bones"),
                    (dict(clips=["dance"]), "unknown clip"), (dict(root_end="up"), "root_end")):
        with pytest.raises(ValueError, match=msg):
            C.rig_serpent(C.make_sample_serpent(tmp_path / f"k{msg}"), **kw)
    empty = Project(tmp_path / "e.json", new_skeleton("e", 100, 100))
    with pytest.raises(ValueError, match="body"):
        C.rig_serpent(empty)


@needs_node
def test_serpent_and_tentacle_play_in_spine_core(koi, tentacle):
    for p, r in (koi, tentacle):
        run(p, list(r["clips"]))


# ================================================================ rig_flier
def test_flier_builds_with_feather_fans_and_a_stabilised_head(bird):
    p, r = bird
    sk = p.data
    assert qa.validate(sk)["ok"], qa.validate(sk)["errors"]
    assert {w["side"] for w in r["wings"].values()} == {"left", "right"}
    for w in r["wings"].values():
        assert len(w["bones"]) == 3 and len(w["feathers"]) == 4
    assert len(r["physics"]) == 8 + 2, "one per feather + the tail"
    tc = next(c for c in sk.transform if c.name == r["head_constraint"])
    assert tc.bones == [r["head_bone"]] and tc.target == r["head_anchor"] and sk.bone(r["head_anchor"]).parent == r["frame"]
    assert sk.slot("head").bone == r["head_bone"] and sk.slot("beak").bone == r["head_bone"]
    assert qa.budget(sk, "mobile_character")["ok"]


def test_flap_shoulder_leads_the_tip_and_the_downstroke_is_longer(bird):
    p, r = bird
    sk = p.data
    f = r["clips"]["flap"]["frequency"]
    right = next(w for w in r["wings"].values() if w["side"] == "right")
    t0, s0 = rot(sk, "flap", right["bones"][0])
    t1, s1 = rot(sk, "flap", right["bones"][1])
    P = 1 / f
    first = t0 < P - 1e-6
    tmax0, tmin0 = t0[first][np.argmax(s0[first])], t0[first][np.argmin(s0[first])]
    assert tmax0 == pytest.approx(0.0, abs=0.02)
    assert tmin0 - tmax0 == pytest.approx(0.58 * P, abs=0.02), "the downstroke takes 58% of the beat"
    tmax1 = t1[first][np.argmax(s1[first])]
    assert tmax1 == pytest.approx(30 / 360 * P, abs=0.02), "the elbow peaks one lag later"
    left = next(w for w in r["wings"].values() if w["side"] == "left")
    _, l0 = rot(sk, "flap", left["bones"][0])
    assert l0 == pytest.approx(-s0, abs=1e-3), "the left wing mirrors"
    ty = [C.sample(sk, "flap", r["body_bone"], "translate", t)[1] for t in (0.0, 0.58 * P)]
    assert ty[0] < 0 < ty[1], "the body is lowest at the top of the stroke, highest after the downstroke (lift)"
    for a in ("flap", "glide", "perch"):
        assert_loop(sk, a)
    assert len([e for e in sk.animations["flap"].events if e.name == "sfx_flap"]) == r["clips"]["flap"]["beats"]


def test_takeoff_ends_on_setup_and_land_ends_on_perch(bird):
    p, r = bird
    sk = p.data
    assert_rest_at_end(sk, "takeoff")
    land, perch = sk.animations["land"], sk.animations["perch"]
    D = land.duration()
    keyed = {(b, tl) for a in (land, perch) for b, tls in a.bones.items() for tl in tls}
    for b, tl in keyed:
        assert C.sample(sk, "land", b, tl, D) == pytest.approx(C.sample(sk, "perch", b, tl, 0.0), abs=1e-3), (b, tl)
    names = {e.name for e in sk.animations["takeoff"].events}
    assert {"sfx_takeoff", "sfx_flap"} <= names and [e.name for e in land.events] == ["sfx_land"]


@needs_node
def test_flier_head_stays_still_while_the_body_bobs(bird):
    p, r = bird
    d = run(p, ["flap", "perch", "glide", "takeoff", "land"], fps=20)
    head = slot_verts(d, "flap", "head")
    body = slot_verts(d, "flap", "body")
    hd = max(float(np.abs(v - head[0]).max()) for v in head)
    bd = max(float(np.abs(v - body[0]).max()) for v in body)
    assert hd < 0.6, f"the head moved {hd:.2f}"
    assert bd > r["clips"]["flap"]["bob"], "while the body bobs"


def test_flier_bad_options(tmp_path):
    with pytest.raises(ValueError, match="downstroke"):
        C.rig_flier(C.make_sample_flier(tmp_path / "a"), downstroke=0.95)
    with pytest.raises(ValueError, match="flap_hz"):
        C.rig_flier(C.make_sample_flier(tmp_path / "b"), flap_hz=0)
    p = C.make_sample_flier(tmp_path / "c")
    for s in list(p.data.slots):
        if s.name.startswith("wing"):
            p.data.slots.remove(s)
    with pytest.raises(ValueError, match="wing_l or wing_r"):
        C.rig_flier(p)


# ================================================================ attach_rig: merge rules
def test_merge_keeps_host_lengths_refits_loops_and_windows_one_shots(tmp_path):
    p, res = host(tmp_path, ["tail"])
    sk = p.data
    clips = res["tail"]["clips"]
    assert clips["idle"] == {**clips["idle"], "length": 2.4, "mode": "loop", "created": False}
    assert clips["walk"]["length"] == 1.0 and clips["win"]["mode"] == "window"
    assert "run" not in clips and "run" not in sk.animations, "a pure reaction is not created"
    assert clips["tail_happy"]["created"] and sk.animations["tail_happy"].duration() == pytest.approx(2.0)
    for a in ("idle", "walk", "tail_happy", "tail_alert", "tail_angry"):
        assert_loop(sk, a)
    assert sk.animations["idle"].duration() == pytest.approx(2.4), "the host clip keeps its length"
    assert sk.animations["walk"].bones["leg_l"], "the host's own keys are still there"
    tail_bones = [res["tail"]["control"], *res["tail"]["bones"]]
    assert_rest_at_end(sk, "win", tail_bones)
    for b in tail_bones:
        assert C.sample(sk, "win", b, "rotate", 0.0) == (0.0,)


def test_attach_rig_errors(tmp_path):
    p = A.make_sample_host(tmp_path / "e", ["ears"])
    with pytest.raises(ValueError, match="unknown kind"):
        A.attach_rig(p, "gills")
    with pytest.raises(ValueError, match="no bone"):
        A.attach_rig(p, "ears", bone="noggin")
    with pytest.raises(ValueError, match="unknown option"):
        A.attach_rig(p, "ears", options={"floppy": True})
    with pytest.raises(ValueError, match="no layers found"):
        A.attach_rig(p, "tail")
    with pytest.raises(ValueError, match="tail_mood"):
        A.attach_rig(A.make_sample_host(tmp_path / "t", ["tail"]), "tail", options={"tail_mood": "sleepy"})
    with pytest.raises(ValueError, match="wing_type"):
        A.attach_rig(A.make_sample_host(tmp_path / "w", ["wings"]), "wings", options={"wing_type": "jet"})
    bare = Project(tmp_path / "b.json", new_skeleton("b", 100, 100))
    with pytest.raises(ValueError, match="name the bone"):
        A.attach_rig(bare, "ears")
    with pytest.raises(ValueError, match="unknown part"):
        A.make_sample_host(tmp_path / "x", ["gills"])


def test_attach_works_on_any_rig_with_the_named_bone(tmp_path):
    """A different skeleton (the classic samples character, bones hip/chest/head) takes ears by bone name."""
    from claude_spine import samples
    p = samples.make_character(tmp_path / "hero")
    r = A.attach_rig(p, "ears", bone="head")
    assert set(r["ears"]) == {"ear_l", "ear_r"} and qa.validate(p.data)["ok"]


# ================================================================ ears
def test_ear_perk_overshoots_exactly_and_ends_on_setup(tmp_path):
    p, res = host(tmp_path, ["ears"], ears={"zeta": 0.3})
    sk = p.data
    e = res["ears"]["ears"]["ear_l"]
    t, v = rot(sk, "ear_perk", e["control"])
    tgt = res["ears"]["clips"]["ear_perk"]["targets"]["ear_l"]
    assert tgt != 0 and (v / tgt).max() == pytest.approx(1 + C.spring_overshoot(0.3), rel=0.01), "step response overshoot"
    assert res["ears"]["clips"]["ear_perk"]["overshoot"] == pytest.approx(C.spring_overshoot(0.3), abs=1e-4)
    for a in ("ear_perk", "ear_flatten", "ear_swivel"):
        assert_rest_at_end(sk, a)
        assert any(ev.name == f"sfx_{a}" for ev in sk.animations[a].events)
    assert_loop(sk, "idle")
    assert len(res["ears"]["physics"]) == 4


def test_ear_swivel_turns_toward_the_sound_and_the_far_ear_lags(tmp_path):
    p, res = host(tmp_path, ["ears"], ears={"sound": [400.0, 80.0]})
    sk = p.data
    E = res["ears"]["ears"]
    assert res["ears"]["clips"]["ear_swivel"]["delays"] == [pytest.approx(0.128, abs=1e-3), 0.0]
    for side in ("ear_l", "ear_r"):
        _, v = rot(sk, "ear_swivel", E[side]["control"])
        assert v[np.argmax(np.abs(v))] < 0, f"{side} turns clockwise, toward a sound on the right"
    tl, vl = rot(sk, "ear_swivel", E["ear_l"]["control"])
    tr, vr = rot(sk, "ear_swivel", E["ear_r"]["control"])
    first = lambda t, v: t[np.argmax(np.abs(v) > 0.5 * np.abs(v).max())]  # noqa: E731
    assert first(tl, vl) - first(tr, vr) == pytest.approx(0.128, abs=0.03)


def test_ear_flatten_holds_folded(tmp_path):
    p, res = host(tmp_path, ["ears"])
    sk = p.data
    c = res["ears"]["ears"]["ear_r"]["control"]
    assert C.sample(sk, "ear_flatten", c, "rotate", 0.5)[0] == pytest.approx(-55.0, abs=0.5), "right ear folds outward (cw)"
    assert C.sample(sk, "ear_flatten", c, "scale", 0.5)[0] == pytest.approx(0.7, abs=0.01), "foreshortened as it folds back"


# ================================================================ tail
def test_tail_moods(tmp_path):
    p, res = host(tmp_path, ["tail"])
    sk = p.data
    bones, ctrl = res["tail"]["bones"], res["tail"]["control"]
    amp = lambda a, b: np.ptp(rot(sk, a, b)[1])  # noqa: E731
    assert amp("tail_happy", bones[-1]) > 20, "happy: slow and wide"
    assert all(amp("tail_alert", b) == 0 for b in [ctrl, *bones]) and C.sample(sk, "tail_alert", ctrl, "rotate", 0)[0] != 0, \
        "alert: held still, raised"
    assert all(amp("tail_angry", b) == 0 for b in bones[:-2]) and amp("tail_angry", bones[-1]) > 20, "angry: only the tip twitches"
    t, v = rot(sk, "tail_happy", bones[0])
    t2, v2 = rot(sk, "tail_happy", bones[-1])
    assert t[np.argmax(v)] < t2[np.argmax(v2)], "the wag travels toward the tip"
    assert res["tail"]["clips"]["tail_happy"]["frequency"] == pytest.approx(1.0)   # 0.8 Hz refit to divide 2.0 s
    q, r2 = host(tmp_path / "angry", ["tail"], tail={"tail_mood": "angry"})
    assert r2["tail"]["clips"]["idle"]["mood"] == "angry"


# ================================================================ wings
def test_wings_breathe_in_idle_and_flutter_when_excited(tmp_path):
    p, res = host(tmp_path, ["wings"])
    sk = p.data
    c = res["wings"]["clips"]
    assert c["idle"]["breaths"] == 1 and c["excited"]["frequency"] == pytest.approx(6.0)
    w = next(iter(res["wings"]["wings"].values()))
    sx, _ = zip(*[C.sample(sk, "idle", w["bones"][0], "scale", t) for t in np.linspace(0, 2.4, 25)])
    assert 0.5 < min(sx) < max(sx) < 0.9, "half folded (foreshortened), breathing"
    for a in ("idle", "excited"):
        assert_loop(sk, a)
    assert len(res["wings"]["physics"]) == 2, "no feathers: the hand trails on physics"
    q = A.make_sample_host(tmp_path / "bug", ["wings"])
    r = A.attach_rig(q, "wings", options={"wing_type": "insect"})
    assert all(len(v["bones"]) == 1 for v in r["wings"].values()) and r["clips"]["excited"]["frequency"] == pytest.approx(11.0)


# ================================================================ horns
def test_horns_are_rigid_with_a_shear_lag(tmp_path):
    p, res = host(tmp_path, ["horns"])
    sk = p.data
    assert len(res["horns"]["horns"]) == 2 and res["horns"]["clips"] == {}
    for c in sk.physics:
        assert (c.rotate, c.shearX, c.x, c.y) == (0, 1, 0, 0), "only shear lags"
        assert sk.bone(c.bone).length > 0
    assert sk.slot("horn_l").bone == res["horns"]["horns"]["horn_l"]


@needs_node
def test_horn_shear_lags_head_turns_by_a_little(tmp_path):
    p, res = host(tmp_path, ["horns"])
    d = run(p, ["idle"], fps=30)

    def corner(v):
        a, b = v[1] - v[0], v[3] - v[0]
        return math.degrees(math.acos(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))))
    ang = [corner(v) for v in slot_verts(d, "idle", "horn_l")]
    dev = max(abs(a - 90) for a in ang)
    assert 0.2 < dev < 10, f"the horn shears a little as the head turns ({dev:.2f} deg)"


# ================================================================ digitigrade
def test_digitigrade_reversed_hock_planted_feet_and_footfalls(tmp_path):
    p, res = host(tmp_path, ["digitigrade"])
    sk = p.data
    L = res["digitigrade"]["legs"]
    for side, leg in L.items():
        assert leg["reversed"], "knee and hock bend opposite ways (the reversed hock)"
        assert len(leg["bones"]) == 3 and len(leg["ik"]) == 2
        assert sk.bone(leg["hock_target"]).parent == leg["foot_target"], "the hock follows the foot"
        assert sk.slot(f"foot_{side}").bone == leg["foot_target"]
    a = sk.animations["walk"]
    assert_loop(sk, "walk")
    ft = L["l"]["foot_target"]
    ts = np.linspace(0, 0.6 * 0.98, 12)
    xy = np.array([C.sample(sk, "walk", ft, "translate", t) for t in ts])
    assert np.abs(xy[:, 1]).max() < 1e-6, "planted: on the ground"
    v = np.diff(xy[:, 0]) / np.diff(ts)
    assert np.ptp(v) < 1.0 and v.mean() < 0, "planted: slides back at constant ground speed"
    steps = [(e.time, e.string) for e in a.events if e.name == "sfx_step"]
    assert steps == [(0.0, "l"), (0.5, "r")], "the legs own the footfalls (host's were replaced)"
    assert qa.validate(sk)["ok"]


# ================================================================ mermaid
def test_mermaid_replaces_the_legs(tmp_path):
    p, res = host(tmp_path, ["mermaid"])
    sk = p.data
    m = res["mermaid"]
    assert set(m["hidden"]) == {"leg_l", "leg_r"} and all(sk.slot(s).attachment is None for s in m["hidden"])
    assert sk.bone(m["frame"]).parent == "hips" and len(m["bones"]) == 6
    assert m["clips"]["idle"]["length"] == 2.4 and not m["clips"]["idle"]["created"]
    for a in ("swim", "idle_float", "idle"):
        assert_loop(sk, a)
    assert m["clips"]["swim"]["frequency"] == pytest.approx(0.8 / (0.7 * 1.2), rel=1e-3)


# ================================================================ snake hair
def test_snake_hair_random_idles_loop_exactly_and_look_together(tmp_path):
    p, res = host(tmp_path, ["snake_hair"])
    sk = p.data
    s = res["snake_hair"]
    assert s["count"] == 10 and "warning" not in s and len(s["ik"]) == 10
    assert all(c.mix == 0 for c in sk.ik), "head-look IK is off in setup"
    cyc = s["clips"]["idle"]["cycles"]
    assert set(cyc) <= {1, 2} and len(set(cyc)) == 2, "randomised, whole cycles per loop"
    assert_loop(sk, "idle")
    first = [rot(sk, "idle", b[0])[1][0] for b in s["snakes"].values()]
    assert len({round(v, 2) for v in first}) > 5, "each snake has its own phase"
    for name in s["ik"]:
        ks = sk.animations["snake_look"].ik[name]
        m = [C.key_val(k, "mix", 0.0) for k in ks]
        assert m[0] == 0 and m[-1] == 0 and 0 < max(m) <= 0.85
    assert any(e.name == "sfx_snake_look" for e in sk.animations["snake_look"].events)
    assert qa.budget(sk, "mobile_character")["ok"]


# ================================================================ fur
def test_fur_outline_bones_physics_and_gust(tmp_path):
    p, res = host(tmp_path, ["fur"])
    sk = p.data
    f = res["fur"]["fur"]["mane"]
    assert len(f["bones"]) == 6 and len(res["fur"]["physics"]) == 6
    assert "chest" in f["weighted_to"]
    from claude_spine.weights import decode_weighted
    att = sk.attachment("mane")
    inf = decode_weighted(att.vertices, len(att.uvs) // 2)
    out_idx = {sk.bone_index(b) for b in f["bones"]}
    hull_on_outline = np.mean([any(bi in out_idx and w > 0.3 for bi, *_, w in v) for v in inf[: att.hull]])
    assert hull_on_outline > 0.5, "the silhouette rides the outline bones"
    ks = sk.animations["fur_ruffle"].physics[res["fur"]["physics"][0]]["wind"]
    wv = [C.key_val(k, "value", 0.0) for k in ks]
    assert wv[0] == 0 and wv[-1] == 0 and max(wv) == pytest.approx(32.0, rel=0.01), "a gust that dies down"


@needs_node
def test_fur_gust_ruffles_the_silhouette(tmp_path):
    p, res = host(tmp_path, ["fur"])
    d = run(p, ["fur_ruffle"], fps=30)
    v = slot_verts(d, "fur_ruffle", "mane")
    assert max(float(np.abs(x - v[0]).max()) for x in v) > 4.0


# ================================================================ glow
def test_glow_tiles_the_fx_pulse_into_the_host_clips(tmp_path):
    p, res = host(tmp_path, ["glow"])
    sk = p.data
    g = res["glow"]
    assert set(g["glows"]) == {"rune", "eye_l", "eye_r"}
    assert g["glows"]["rune"]["recipe"] == "electric_frame" and g["glows"]["eye_l"]["recipe"] == "shine"
    assert g["clips"]["idle"] == {**g["clips"]["idle"], "pulses": 2, "period": 1.2, "length": 2.4}
    fx_slots = [s for gl in g["glows"].values() for s in gl["slots"]]
    for s in fx_slots:
        assert sk.slot(s).attachment is None and sk.slot(s).blend == "additive"
    assert_loop(sk, "idle")
    a = sk.animations["idle"]
    assert len({e.time for e in a.events if e.name == "fx_shine"}) == 2, "one fx_shine per pulse"
    assert not any(n.startswith("fx_") for n in sk.animations), "no stray FX animations"
    # the pulse repeats exactly: a glow colour at t and t + period match
    core = [s for s in g["glows"]["eye_l"]["slots"] if "rgba" in a.slots.get(s, {})]
    assert core
    for s0 in core:
        tt = {round(k.time, 3): k.color for k in a.slots[s0]["rgba"]}
        if 0.0 in tt and 2.4 in tt:
            assert tt[0.0] == tt[1.2] == tt[2.4], s0
    assert sk.slot_index(g["glows"]["rune"]["slots"][0]) == sk.slot_index("rune") + 1, "runes glow right above their part"


# ================================================================ runtime + budget for every kind
@needs_node
@pytest.mark.parametrize("kinds", [["ears", "tail", "wings"], ["horns", "fur", "glow"], ["digitigrade"], ["mermaid"],
                                   ["snake_hair"]])
def test_every_addon_plays_in_spine_core(tmp_path, kinds):
    p, res = host(tmp_path, kinds)
    assert qa.validate(p.data)["ok"], qa.validate(p.data)["errors"]
    b = qa.budget(p.data, "mobile_character")
    assert b["ok"], b["over_budget"]
    run(p, sorted(p.data.animations))


# ================================================================ MCP tools
def test_the_mcp_tools(tmp_path):
    from claude_spine import tools_addons  # noqa: F401  registers the tools
    from claude_spine.server import mcp

    def call(tool, **args):
        res = asyncio.run(mcp.call_tool(tool, args))
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)
    kinds = call("attach_rig")["kinds"]
    assert set(kinds) == set(A.KINDS) and "tail_mood" in kinds["tail"]["options"]
    h = call("make_host_sample", out_dir=str(tmp_path / "h"), parts=["ears", "tail"])
    out = call("attach_rig", project=h["project"], kind="ears")
    assert "validation_errors" not in out and "ear_perk" in Project.open(h["project"]).data.animations
    out = call("attach_rig", project=h["project"], kind="tail", options={"tail_mood": "alert"})
    assert out["clips"]["idle"]["mood"] == "alert"
    s = call("make_serpent_sample", out_dir=str(tmp_path / "s"))
    out = call("rig_serpent", project=s["project"], speed=1.5)
    assert "validation_errors" not in out and out["clips"]["swim"]["frequency"] == pytest.approx(1.5 / 0.7, rel=1e-3)
    f = call("make_flier_sample", out_dir=str(tmp_path / "f"))
    out = call("rig_flier", project=f["project"], clips=["flap", "perch"])
    assert set(out["clips"]) == {"flap", "perch"} and "validation_errors" not in out
