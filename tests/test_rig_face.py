"""rig_face: part recognition, the rig (turn base, clamped eyes, lids, brows, jaw, cheeks, hair), the clips and
their physics (springs, blinks, Poisson timers, loop closure, brow lead, anticipation), look_at, lipsync, the MCP
tools, and spine-core playback."""
import asyncio
import json
import math

import numpy as np
import pytest

from claude_spine import qa, rig_face as F, runtime, samples
from claude_spine.ir import MeshAttachment
from claude_spine.mesh import mesh_world_vertices
from claude_spine.project import Project
from claude_spine.rig import setup_hull_world
from claude_spine.timeline import AnimBuilder
from claude_spine.weights import decode_weighted
from conftest import needs_node

FPS = 30


@pytest.fixture(scope="module")
def rigged(tmp_path_factory):
    p = F.make_sample_face(tmp_path_factory.mktemp("face") / "s")
    sk = p.data
    sk.add_bone_world("chest", "root", 0, 70, 0, length=60)
    from claude_spine.rig import reparent_slot
    reparent_slot(sk, "body", "chest")
    before = {s.name: setup_hull_world(p, s.name) for s in sk.slots}
    res = F.rig_face(p, parent="chest", spine="chest")
    p.save()
    return p, res, before


@pytest.fixture
def sample(tmp_path):
    return F.make_sample_face(tmp_path / "s")


def _keys(sk, anim, bone, tl):
    return sk.animations[anim].bones[bone][tl]


def _vals(ks, fields=("x", "y")):
    return np.array([[float(getattr(k, f, 0) or 0) for f in fields] for k in ks])


def _at(ks, t, fields=("x", "y"), rest=(0.0, 0.0)):
    return F.sample_timeline(ks, fields, np.array([t]), rest)[0]


# ------------------------------------------------------------------------------------------- recognition
def test_sample_names_follow_the_psd_convention(sample):
    names = [s.name for s in sample.data.slots]
    assert "face/head" in names and "face/eye_L/lid_upper" in names and "face/mouth/A" in names
    assert "hair/bangs" in names and all(sample.data.slot(n).bone == "root" for n in names)
    parts = F.find_face_parts(sample.data)
    assert parts["missing"] == [] and parts["unrecognised"] == ["body"]
    assert set(parts["mouth"]) == set(F.VISEMES) | {"smile", "frown"}
    assert len(parts["strands"]) == 2


def test_names_are_case_insensitive_with_side_variants(sample):
    sk = sample.data
    F.rename_slot(sk, "face/eye_L/white", "Face/Left Eye/WHITE")
    F.rename_slot(sk, "face/brow_R", "FACE/Brow-Right")
    F.rename_slot(sk, "face/mouth/O", "Face/Mouth/o")
    F.rename_slot(sk, "face/head", "Skin")
    roles = F.find_face_parts(sk)["roles"]
    assert roles["eye_L_white"] == "Face/Left Eye/WHITE" and roles["brow_R"] == "FACE/Brow-Right"
    assert roles["face"] == "Skin"
    assert F.find_face_parts(sk)["mouth"]["O"] == "Face/Mouth/o"


def test_missing_head_is_a_clear_error_and_optional_parts_are_skipped(sample):
    sk = sample.data
    F.rename_slot(sk, "face/head", "blob")
    with pytest.raises(ValueError, match="no face base layer"):
        F.find_face_parts(sk)
    F.rename_slot(sk, "blob", "face/head")
    for n in ["face/cheek_L", "face/jaw", "face/eye_R/lid_lower", "hair/bangs"]:
        sk.slots.remove(sk.slot(n))
        sk.skin().attachments.pop(n)
    parts = F.find_face_parts(sk)
    assert {"cheek_L", "jaw", "eye_R_lid_lower", "bangs"} <= set(parts["missing"])
    res = F.rig_face(sample, clips=["idle"])
    assert any("eye_R" in s and "lid_lower" in s for s in res["skipped"])
    assert qa.validate(sk)["ok"]


def test_conflicts_are_errors(sample):
    sk = sample.data
    F.rename_slot(sk, "body", "face/nose2")
    F.rename_slot(sk, "face/nose2", "nose")
    with pytest.raises(ValueError, match="two slots"):
        F.find_face_parts(sk)


def test_bad_options(sample):
    with pytest.raises(ValueError, match="unknown clip"):
        F.rig_face(sample, clips=["dance"])
    with pytest.raises(ValueError, match="features"):
        F.rig_face(sample, features={"nope": 1.0}, clips=[])
    with pytest.raises(ValueError, match="no face rig"):
        F.add_face_clip(sample, "happy")


# ------------------------------------------------------------------------------------------- the rig
def test_rig_keeps_the_setup_pose_and_validates(rigged):
    p, res, before = rigged
    sk = p.data
    assert qa.validate(sk)["ok"]
    renamed = res["renamed"]
    for old, h0 in before.items():
        new = renamed.get(old, old)
        if old.startswith("face/mouth/"):
            continue
        h1 = setup_hull_world(p, new)
        lo0, hi0 = h0.min(0), h0.max(0)
        lo1, hi1 = h1.min(0), h1.max(0)
        assert np.abs(lo0 - lo1).max() < 2.5 and np.abs(hi0 - hi1).max() < 2.5, new
    names = [s.name for s in sk.slots]
    assert names.index("eye_L_white") < names.index("eye_L_iris") < names.index("eye_L_pupil") \
        < names.index("eye_L_lid_lower") < names.index("eye_L_lid_upper")
    assert sk.slot("mouth").attachment == "M" and set(F.VISEMES) <= set(sk.skin().attachments["mouth"])
    assert res["counts"]["bones"] <= qa.PROFILES["mobile_character"]["bones"]


def test_budget_mobile_character(rigged):
    b = qa.budget(rigged[0].data, "mobile_character")
    assert b["ok"], b["over_budget"]
    assert b["metrics"]["draw_calls"] == 1 and b["metrics"]["max_influences"] <= 4


def test_scales_are_stored_in_bone_lengths(rigged):
    sk = rigged[0].data
    info = F.face_info(sk)
    assert info["R_look"] > 0 and info["turn_range"] > 0 and info["U"] > 0
    for S in "LR":
        e = info["eyes"][S]
        up, lo = e["lid_upper"]["travel"], e["lid_lower"]["travel"]
        # the upper lid covers 70% of the opening and the lower lid 30% (plus a small overlap each)
        assert 0.3 < lo / up < 0.62


def test_face_mesh_weights_jaw_and_cheeks(rigged):
    p, res, _ = rigged
    sk = p.data
    att = sk.attachment("face")
    inf = decode_weighted(att.vertices, len(att.uvs) // 2)
    pts = mesh_world_vertices(sk, "face", att)
    ij, ic = sk.bone_index("face_jaw"), sk.bone_index("cheek_L")
    jaw = np.array([sum(w for b, *_, w in v if b in (ij, sk.bone_index("face_jaw_turn"))) for v in inf])
    chk = np.array([sum(w for b, *_, w in v if b == ic) for v in inf])
    lip = sk.world()["face_jaw"].y
    assert jaw[pts[:, 1] < lip - 40].min() > 0.95          # the chin is all jaw
    assert jaw[pts[:, 1] > lip + 40].max() < 1e-6          # the upper face never is
    assert chk.max() > 0.4 and all(len(v) <= 4 for v in inf)
    for v in inf:
        assert abs(sum(w for *_, w in v) - 1) < 2e-3


def test_eye_clamp_is_an_ik_compress_inside_a_scaled_space(rigged):
    sk = rigged[0].data
    ik = next(c for c in sk.ik if c.name == "eye_L_clamp")
    assert ik.compress and not ik.stretch and ik.bones == ["eye_L_ik"] and ik.target == "eye_L_aim"
    sp = sk.bone("eye_L_space")
    rx = sk.bone("eye_L_ik").length
    assert sp.scaleY < 1 and rx > 0
    tc = next(t for t in sk.transform if t.name == "eye_L_ball_tc")
    assert tc.target == "eye_L_tip" and not tc.local and tc.mixRotate == 0


# ------------------------------------------------------------------------------------------- clips: physics
def test_idle_is_an_exact_loop(rigged):
    sk = rigged[0].data
    a = sk.animations["idle"]
    T = a.duration()
    for bn, tls in a.bones.items():
        for tl, ks in tls.items():
            assert ks[0].time == 0 and abs(ks[-1].time - T) < 1e-6, (bn, tl)
            f = ("value",) if tl == "rotate" else ("x", "y")
            assert np.allclose(_vals(ks[:1], f), _vals(ks[-1:], f), atol=1e-9), (bn, tl)


def test_blinks_are_80ms_down_160ms_up_lower_lid_30_percent(rigged):
    sk = rigged[0].data
    info = F.face_info(sk)
    blinks = [e.time for e in sk.animations["idle"].events if e.name == "sfx_blink"]
    assert blinks
    up, lo = info["eyes"]["L"]["lid_upper"], info["eyes"]["L"]["lid_lower"]
    ku = _keys(sk, "idle", up["bone"], "translate")
    kl = _keys(sk, "idle", lo["bone"], "translate")
    for t0 in blinks:
        assert abs(_at(ku, t0)[1]) < 1e-3                               # open at the start
        assert abs(_at(ku, t0 + 0.08)[1] + up["travel"]) < 1e-3         # closed after 80 ms
        assert abs(_at(kl, t0 + 0.08)[1] - lo["travel"]) < 1e-3
        assert abs(_at(ku, t0 + 0.24)[1]) < 1e-3                        # open again 160 ms later
        assert abs(_at(ku, t0 + 0.04)[1]) < 0.3 * up["travel"]          # accelerating down (quad in: 25% at half time)
        assert abs(_at(ku, t0 + 0.16)[1]) < 0.3 * up["travel"]          # decelerating up (quad out)


def test_poisson_timers_are_seeded(tmp_path):
    r1 = F.poisson_times(np.random.default_rng(3), 1.0, 0, 50, 0.3)
    r2 = F.poisson_times(np.random.default_rng(3), 1.0, 0, 50, 0.3)
    r3 = F.poisson_times(np.random.default_rng(4), 1.0, 0, 50, 0.3)
    assert r1 == r2 and r1 != r3
    gaps = np.diff(r1)
    assert gaps.min() >= 0.3 and 0.6 < gaps.mean() < 2.0          # mean gap ~ 1/rate (thinned a little)


def test_saccades_are_instant_and_the_head_follows_100ms_later(rigged):
    sk = rigged[0].data
    info = F.face_info(sk)
    a = sk.animations["idle"]
    look = a.bones["face_look"]["translate"]
    head = a.bones[info["turn"]]["translate"]
    # a saccade is a jump between two keys 1 ms apart
    jumps = [(k0.time, k1.time) for k0, k1 in zip(look, look[1:]) if k1.time - k0.time < 0.0015
             and np.hypot(*(_vals([k1]) - _vals([k0]))[0]) > 0.5]
    assert jumps
    t = jumps[0][1]
    h = F.sample_timeline(head, ("x", "y"), np.array([t, t + 0.099, t + 0.2]), (0, 0))
    assert np.hypot(*(h[1] - h[0])) < 0.05 * max(np.hypot(*(h[2] - h[1])), 1e-6) + 1e-3   # dead time of 100 ms


def test_spring_overshoot_is_exact():
    for z in (0.3, 0.45, 0.7):
        t = np.linspace(0, 3, 30001)
        s = F.spring_step(t, 2.0, z)
        assert abs(s.max() - 1 - F.overshoot(z)) < 1e-4
    assert F.spring_step(np.array([-1.0, 0.0]), 2, 0.5).tolist() == [0.0, 0.0]


@pytest.mark.parametrize("clip", ["happy", "sad", "angry", "surprised", "talk"])
def test_one_shots_end_exactly_on_the_setup_pose(rigged, clip):
    sk = rigged[0].data
    a = sk.animations[clip]
    T = a.duration()
    for bn, tls in a.bones.items():
        for tl, ks in tls.items():
            f = ("value",) if tl == "rotate" else ("x", "y")
            rest = (1.0, 1.0) if tl == "scale" else (0.0,) * len(f)
            v = _vals(ks[-1:], f)[0]
            if tl == "scale":
                v = np.array([float(getattr(ks[-1], "x", 1) if getattr(ks[-1], "x", None) is not None else 1),
                              float(getattr(ks[-1], "y", 1) if getattr(ks[-1], "y", None) is not None else 1)])
            assert np.allclose(v, rest, atol=1e-3), (clip, bn, tl, v)
            assert ks[-1].time <= T + 1e-6
    att = a.slots.get("mouth", {}).get("attachment")
    if att:
        assert (att[-1].model_extra or {}).get("name") == sk.slot("mouth").attachment


@pytest.mark.parametrize("clip", ["happy", "sad", "angry", "surprised"])
def test_brows_lead_every_expression_by_a_frame(rigged, clip):
    sk = rigged[0].data
    a = sk.animations[clip]

    t = np.arange(0, 0.5, 1 / 960)

    def start(ks, fields, rest):
        V = F.sample_timeline(ks, fields, t, rest)
        moving = np.nonzero(np.abs(V - np.array(rest)).max(1) > 1e-4)[0]
        return t[moving[0]] if len(moving) else 99.0
    brow = min(start(ks, ("x", "y"), (0, 0)) for bn, tls in a.bones.items() if bn.startswith("brow_")
               for ks in tls.values())
    rest_ = []
    for bn, tls in a.bones.items():
        if bn.startswith("brow_"):
            continue
        for tl, ks in tls.items():
            f = ("value",) if tl == "rotate" else ("x", "y")
            r0 = (1.0, 1.0) if tl == "scale" else (0.0,) * len(f)
            rest_.append(start(ks, f, r0))
    assert abs(min(rest_) - brow - 1 / FPS) < 2 / 960, (brow, min(rest_))


def test_inner_brow_raise_is_exaggerated_in_sad(rigged):
    sk = rigged[0].data
    a = sk.animations["sad"]
    up = {part: _vals(a.bones[f"brow_L_{part}"]["translate"])[:, 1].max() for part in ("inner", "mid")}
    assert up["inner"] > 2.5 * up["mid"] > 0


def test_surprised_anticipates_two_frames_then_overshoots(rigged):
    sk = rigged[0].data
    ks = sk.animations["surprised"].bones["face_rig"]["scale"]
    t = np.round(np.arange(0, 1.0, 1 / 240), 5)
    sy = F.sample_timeline(ks, ("x", "y"), t, (1, 1))[:, 1]
    sx = F.sample_timeline(ks, ("x", "y"), t, (1, 1))[:, 0]
    squashed = t[sy < 1 - 1e-4]
    assert 0.066 < squashed.max() - squashed.min() + 1 / 240 < 0.11       # 2 frames down, ~1 frame back through rest
    k0 = np.argmin(sy)
    assert abs(t[k0] - (2 / FPS + 2 / FPS)) < 1 / 120                     # deepest exactly at the end of the 2 frames
    assert sy.min() < 0.93 and sy.max() > 1.08                           # squash, then a stretch that overshoots
    hold = F.sample_timeline(ks, ("x", "y"), np.array([1.1]), (1, 1))[0, 1]
    assert sy.max() > hold + 0.01
    k = np.argmax(sy)
    assert abs(sx[k] - sy[k] ** -0.5) < 2e-3                              # volume kept: sx = sy^-1/2


def test_angry_shakes_and_happy_tilts(rigged):
    sk = rigged[0].data
    rot = _vals(sk.animations["angry"].bones["face_rig"]["rotate"], ("value",))[:, 0]
    assert (np.diff(np.sign(rot[np.abs(rot) > 0.05])) != 0).sum() >= 3     # it oscillates
    tilt = _vals(sk.animations["happy"].bones["face_rig"]["rotate"], ("value",))[:, 0]
    assert tilt.max() > 5


def test_happy_smiles_with_the_cheeks_and_squints(rigged):
    sk = rigged[0].data
    a = sk.animations["happy"]
    sm = _vals(a.bones["face_smile"]["translate"])[:, 1]
    assert sm.max() > 0.9 * sk.bone("face_smile_base").length
    lid = _vals(a.bones["eye_L_lid_lower"]["translate"])[:, 1]
    assert lid.max() > 0.25 * sk.bone("eye_L_lid_lower").length          # the cheek pushes the lower lid: a squint
    names = [(k.model_extra or {}).get("name") for k in a.slots["mouth"]["attachment"]]
    assert "smile" in names
    push = next(t for t in sk.transform if t.name == "eye_L_lid_lower_push_tc")
    assert push.target == "face_smile" and push.mixY > 0
    assert any(t.target == "face_smile" and t.bones == ["cheek_L"] for t in sk.transform)
    assert any(t.target == "face_jaw" and t.bones == ["cheek_L"] for t in sk.transform)


# ------------------------------------------------------------------------------------------- lipsync
def test_g2p_and_schedule():
    assert [v for v, _ in F.g2p("hello")] == ["E", "L", "O"]
    assert [v for v, _ in F.g2p("bump")] == ["M", "U", "M"]
    assert [v for v, _ in F.g2p("fish")] == ["F", "I", "E"]
    s = F.speech_schedule("one two three four five six", wpm=120)
    assert abs(s[-1]["t"] + s[-1]["dur"] - 6 * 0.5) < 0.05
    s2 = F.speech_schedule("hi, there.", wpm=150)
    assert [p["viseme"] for p in s2 if p["viseme"] == "rest"] == ["rest", "rest"]
    ph = F.speech_schedule(phonemes=["HH", "AH0", "L", "OW1", ["sil", 0.3], "M"])
    assert [p["viseme"] for p in ph] == ["E", "A", "L", "O", "rest", "M"]
    assert abs(ph[4]["dur"] - 0.3) < 1e-9 and ph[1]["dur"] > ph[0]["dur"]
    with pytest.raises(ValueError, match="unknown phoneme"):
        F.speech_schedule(phonemes=["QQ"])
    with pytest.raises(ValueError):
        F.speech_schedule("...")
    with pytest.raises(ValueError, match="exactly one"):
        F.speech_schedule()


def test_lipsync_keys_visemes_stepped_and_the_jaw_eased(rigged):
    p = rigged[0]
    sk = p.data
    res = F.lipsync(p, phonemes=[["M", 0.1], ["A", 0.2], ["O", 0.2], ["F", 0.1], ["rest", 0.2]], animation="ls",
                    start=0.5, lead=0.0)
    a = sk.animations["ls"]
    att = [(k.time, (k.model_extra or {}).get("name")) for k in a.slots["mouth"]["attachment"]]
    assert att == [(0.5, "M"), (0.6, "A"), (0.8, "O"), (1.0, "F"), (1.1, "M")]
    jaw = a.bones["face_jaw"]["scale"]
    ys = _vals(jaw)[:, 1]
    assert abs(ys.max() - (1 + F.JAW_OPEN)) < 1e-3 and ys[0] == 1 and ys[-1] == 1
    assert all(isinstance(k.curve, list) for k in jaw[:-1])               # eased (bezier), not stepped
    k = int(np.argmax(ys))
    assert abs(float(jaw[k].x) - ys[k] ** -0.5) < 1e-3                   # squash of the lower face
    ev = [e.name for e in a.events]
    assert ev[0] == "sfx_talk" and ev[-1] == "talk_end" and res["end"] == 1.3


def test_lipsync_text_words_fire_events_and_fallbacks(tmp_path):
    p = F.make_sample_face(tmp_path / "f")
    F.rig_face(p, clips=[])
    sk = p.data
    del sk.skin().attachments["mouth"]["L"]
    res = F.lipsync(p, text="Hello world", animation="hw", wpm=100)
    words = [e for e in sk.animations["hw"].events if e.name == "talk_word"]
    assert [e.model_extra.get("string") for e in words] == ["Hello", "world"]
    assert abs(words[1].time - 0.6) < 1e-3                                # 60 / 100 wpm
    names = {(k.model_extra or {}).get("name") for k in sk.animations["hw"].slots["mouth"]["attachment"]}
    assert "L" not in names and "E" in names                               # L falls back to E
    with pytest.raises(ValueError, match="nothing to lipsync"):
        F.lipsync(Project(tmp_path / "e.json", __import__("claude_spine.ir", fromlist=["x"]).new_skeleton()), text="hi")


# ------------------------------------------------------------------------------------------- look_at
def test_look_at_lags_by_level_and_counter_rolls(rigged):
    p = rigged[0]
    sk = p.data
    info = F.face_info(sk)
    F.look_at(p, "la", gaze=[[0.5, 1.0, 0.0]], duration=2.0, spine="chest")
    a = sk.animations["la"]
    eye = a.bones["face_look"]["translate"]
    head = a.bones[info["turn"]]["translate"]
    carrier = sk.bone("chest").parent
    assert carrier.startswith("look_chest")
    body = a.bones[carrier]["rotate"]
    R = info["R_look"]
    e = F.sample_timeline(eye, ("x", "y"), np.array([0.499, 0.5, 1.99]), (0, 0))[:, 0] / R
    assert abs(e[0]) < 1e-3 and abs(e[1] - 1.0) < 1e-3                   # instant saccade
    assert abs(e[2] - (1 - 0.4 - 0.15)) < 0.02                            # counter-rolled to gaze - head - spine
    h = F.sample_timeline(head, ("x", "y"), np.array([0.599, 0.62, 1.99]), (0, 0))[:, 0]
    assert abs(h[0]) < 1e-2 and h[1] > 0 and abs(h[2] - 0.4 * info["turn_range"]) < 0.02 * info["turn_range"]
    b = F.sample_timeline(body, ("value",), np.array([0.6 + 2 / 30 - 0.002, 0.7 + 2 / 30, 1.99]), (0,))[:, 0]
    assert abs(b[0]) < 1e-2 and b[1] < 0 and abs(b[2] + 0.15 * 5) < 0.05   # spine twist 2 frames after the head
    assert "rotate" not in a.bones.get("chest", {})                     # the artist's bone is never keyed


def test_look_at_limits_and_generic_bones(tmp_path, character):
    p = character
    lv = [{"bone": "head", "channel": "rotate", "range": [30, 0], "weight": 0.5, "lag": 0.1, "limit": 6},
          {"bone": "chest", "channel": "rotate", "range": [10, 0], "weight": 0.3, "lag": 0.2}]
    res = F.look_at(p, "body_look", levels=lv, gaze=[[0.1, 1, 0], [1.5, 0, 0]], duration=3.0)
    sk = p.data
    hk = sk.animations["body_look"].bones[res["levels"][0]["bone"]]["rotate"]
    assert np.abs(_vals(hk, ("value",))).max() <= 6 + 1e-6             # clamped by the limit
    with pytest.raises(ValueError, match="no bone"):
        F.look_at(p, "x", levels=[{"bone": "nope"}], gaze=[[0, 1, 0]])
    with pytest.raises(ValueError, match="channel"):
        F.look_at(p, "x", levels=[{"bone": "head", "channel": "scale"}], gaze=[[0, 1, 0]])
    with pytest.raises(ValueError, match="gaze"):
        F.look_at(p, "x", levels=lv)


def test_look_at_follows_a_keyed_target_bone_and_loops(rigged):
    p = rigged[0]
    sk = p.data
    R = sk.bone("face_look_base").length
    AnimBuilder(sk, "tgt").bone("face_look", "translate", [(0, 0, 0), (1, R, 0), (2, 0, 0)], "sine_in_out")
    F.look_at(p, "tgt", target="face_look", loop=True)
    a = sk.animations["tgt"]
    for ks in (a.bones["face_look"]["translate"], a.bones[F.face_info(sk)["turn"]]["translate"]):
        assert np.allclose(_vals(ks[:1]), _vals(ks[-1:]), atol=1e-6)


# ------------------------------------------------------------------------------------------- other art
def test_rig_face_on_the_sample_character(character):
    res = F.rig_face(character, parent="head")
    sk = character.data
    assert res["eyes"]["L"]["simple"] and "bangs" in res["slots"] and res["hair"]["strands"]
    assert qa.validate(sk)["ok"]
    info = F.face_info(sk)
    assert info["eyes"]["L"]["simple"] and info["mouth"] == "mouth"
    ks = sk.animations["idle"].bones[info["eyes"]["L"]["socket"]]["scale"]
    assert _vals(ks)[:, 1].min() < 0.2                                  # one-layer eyes blink by squash


# ------------------------------------------------------------------------------------------- runtime
@needs_node
def test_every_clip_plays_in_spine_core(rigged):
    p = rigged[0]
    d = runtime.run(p, animations=list(F.CLIPS), fps=10, geometry=True)
    assert d["ok"] and not d["problems"], d.get("problems") or d.get("error")
    ev = {n: {e["name"] for e in a["events"]} for n, a in d["animations"].items()}
    assert "sfx_blink" in ev["idle"] and "sfx_happy" in ev["happy"] and "sfx_surprised" in ev["surprised"]
    assert {"sfx_talk", "talk_word", "talk_end"} <= ev["talk"]
    # the setup pose is exactly the first frame of every one-shot
    s0 = {dr["slot"]: np.asarray(dr["v"]) for dr in d["setup"]["draws"]}
    for clip in ("happy", "sad", "angry", "surprised"):
        last = {dr["slot"]: np.asarray(dr["v"]) for dr in d["animations"][clip]["frames"][-1]["draws"]}
        for sl, v in last.items():
            if sl.startswith(("hair_", "bangs")):
                continue                                                 # physics may still be swinging
            assert np.abs(v - s0[sl]).max() < 0.05, (clip, sl)


@needs_node
def test_the_iris_never_leaves_the_socket_ellipse(rigged):
    p = rigged[0]
    sk = p.data
    R = sk.bone("face_look_base").length
    # keys half a frame before the sampled frames (Spine stores times as float32)
    pts = [(0, 0, 0), (0.1, 0.2 * R, 0), (0.3, 5 * R, 0), (0.5, 0, 5 * R), (0.7, -4 * R, -4 * R), (0.9, 3 * R, 4 * R),
           (1.0, 3 * R, 4 * R)]
    AnimBuilder(sk, "probe").bone("face_look", "translate", pts, "stepped")
    d = runtime.run(p, animations=["probe"], fps=5, geometry=True)
    assert d["ok"]
    del sk.animations["probe"]
    c0 = np.asarray(next(dr for dr in d["setup"]["draws"] if dr["slot"] == "eye_L_iris")["v"]).reshape(-1, 2).mean(0)
    rx = sk.bone("eye_L_ik").length
    ry = rx * sk.bone("eye_L_space").scaleY
    gx = next(t for t in sk.transform if t.name == "eye_L_aim_tc").mixX
    for fr in d["animations"]["probe"]["frames"]:
        c = np.asarray(next(dr for dr in fr["draws"] if dr["slot"] == "eye_L_iris")["v"]).reshape(-1, 2).mean(0)
        dx, dy = c - c0
        assert (dx / rx) ** 2 + (dy / ry) ** 2 <= 1 + 0.02, (fr["t"], dx, dy)
        if abs(fr["t"] - 0.2) < 1e-6:                                   # inside the ellipse it is proportional
            assert abs(dx - gx * 0.2 * R) < 0.05 and abs(dy) < 0.05
        if abs(fr["t"] - 0.4) < 1e-6:                                   # far outside it sits on the rim
            assert abs(dx - rx) < 0.05


@needs_node
def test_blink_closes_the_eye_in_the_runtime(rigged):
    p = rigged[0]
    sk = p.data
    t0 = next(e.time for e in sk.animations["idle"].events if e.name == "sfx_blink")
    d = runtime.run(p, animations=["idle"], fps=100, geometry=True)
    fr = min(d["animations"]["idle"]["frames"], key=lambda f: abs(f["t"] - (t0 + 0.08)))
    up = next(dr for dr in fr["draws"] if dr["slot"] == "eye_L_lid_upper")
    lo = next(dr for dr in fr["draws"] if dr["slot"] == "eye_L_lid_lower")
    wv = np.asarray(next(dr for dr in d["setup"]["draws"] if dr["slot"] == "eye_L_white")["v"]).reshape(-1, 2)
    cx = wv[:, 0].mean()
    ub = np.asarray(up["v"]).reshape(-1, 2)
    lb = np.asarray(lo["v"]).reshape(-1, 2)
    near = lambda P: P[np.abs(P[:, 0] - cx) < 4]  # noqa: E731
    assert near(ub)[:, 1].min() <= near(lb)[:, 1].max() + 0.5           # the lids meet in the middle


# ------------------------------------------------------------------------------------------- MCP tools
def _call(tool, **args):
    from claude_spine import tools_face  # noqa: F401
    from claude_spine.server import mcp
    res = asyncio.run(mcp.call_tool(tool, args))
    content = res[0] if isinstance(res, tuple) else res
    return json.loads(content[0].text)


def test_mcp_tools(tmp_path):
    out = _call("make_face_sample", out_dir=str(tmp_path / "f"))
    proj = out["project"]
    assert "face/head" in out["slots"] and out["recognised"]["missing"] == []
    r = _call("rig_face", project=proj, clips=["idle", "happy"])
    assert "validation_errors" not in r and set(r["clips"]) == {"idle", "happy"}
    r = _call("face_clip", project=proj, clip="surprised", intensity=1.2)
    assert r["animation"] == "surprised" and "validation_errors" not in r
    r = _call("lipsync", project=proj, text="Big win!", animation="say")
    assert r["words"] == 2 and "validation_errors" not in r
    r = _call("look_at", project=proj, animation="glance", gaze=[[0.2, 0.7, 0.1], [1.0, 0, 0]], duration=1.6)
    assert len(r["levels"]) == 2 and "validation_errors" not in r
    sk = Project.open(proj).data
    assert {"idle", "happy", "surprised", "say", "glance"} <= set(sk.animations)
    conv = _call("rig_face", project="", clips=[])
    assert "FACE_LAYERS" in json.dumps(conv) or "convention" in conv
