"""Living props (prop_bob, prop_blink, prop_breathe_heavy, prop_hover_spin, prop_dangle, prop_sway_wind): seamless loops,
the artist's bones never keyed, and the physics each one claims (figure 8, shadow, blink length, volume, cos turn,
pendulum period, lag ordering along strands and chains)."""
import json
import math

import numpy as np
import pytest

from claude_spine import fx_recipes as R, qa, runtime  # fx_recipes first: it registers the families
from claude_spine import fx_props_life as L
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project
from conftest import needs_node
from PIL import Image

LIFE = ["prop_bob", "prop_blink", "prop_breathe_heavy", "prop_hover_spin", "prop_dangle", "prop_sway_wind"]
ARTIST = ["pot", "eye_l", "eye_r", "lantern", "rope", "tassel_l", "tassel_r", "flag0", "flag1", "flag2", "flag3",
          "leaf0", "leaf1", "leaf2", "leaf3"]


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


@pytest.fixture
def rig(tmp_path):
    """An artist's scene: a pot with eyes, a lantern on a rope with tassels, a flag chain, an upright leaf chain."""
    p = Project(tmp_path / "rig.json", new_skeleton("rig", 720, 720))
    sk = p.data
    sk.bones += [Bone(name="pot", parent="root", x=0, y=-100), Bone(name="eye_l", parent="pot", x=-30, y=110),
                 Bone(name="eye_r", parent="pot", x=30, y=110), Bone(name="rope", parent="root", x=200, y=250),
                 Bone(name="lantern", parent="root", x=200, y=50), Bone(name="tassel_l", parent="lantern", x=-30, y=-150),
                 Bone(name="tassel_r", parent="lantern", x=30, y=-150)]
    sk.add_bone_world("flag0", "root", -150, 190, 0, length=50)
    for i in range(1, 4):
        sk.add_bone_world(f"flag{i}", f"flag{i - 1}", -150 + 50 * i, 190, 0, length=50)
    sk.add_bone_world("leaf0", "root", 120, -200, 90, length=60)
    for i in range(1, 4):
        sk.add_bone_world(f"leaf{i}", f"leaf{i - 1}", 120, -200 + 60 * i, 90, length=60)
    for n, b, y in (("pot", "pot", 90), ("eye_l", "eye_l", 0), ("eye_r", "eye_r", 0), ("rope", "rope", -100),
                    ("lantern", "lantern", -80), ("tassel_l", "tassel_l", -30), ("tassel_r", "tassel_r", -30)):
        p.write_image(n, Image.new("RGBA", (40, 40), (255, 255, 255, 255)))
        sk.add_slot(Slot(name=n, bone=b, attachment=n))
        sk.set_attachment(n, n, RegionAttachment(path=n, y=y, width=40, height=40))
    return p


def vals(keys, f="value", rest=0.0):
    return np.array([rest if getattr(k, f, None) is None else float(getattr(k, f)) for k in keys])


def times(keys):
    return np.array([k.time for k in keys])


def assert_seamless(an, D):
    """Every timeline's first key equals its last, and the last key sits on the loop end."""
    for bone, tls in an.bones.items():
        for tl, ks in tls.items():
            if len(ks) < 2:
                continue
            a, b = ks[0].model_dump(exclude={"time", "curve"}), ks[-1].model_dump(exclude={"time", "curve"})
            assert a == b, (bone, tl, a, b)
            assert ks[-1].time == pytest.approx(D, abs=1e-3), (bone, tl)
    for slot, tls in an.slots.items():
        for tl, ks in tls.items():
            if tl == "attachment" or len(ks) < 2:
                continue
            assert ks[0].color == ks[-1].color, (slot, tl)


def assert_untouched(p, an):
    keyed = [b for b in ARTIST if b in an.bones]
    assert not keyed, f"artist bones keyed: {keyed}"


def carrier(an, prefix):
    return next(b for b in an.bones if b.startswith(prefix))


# ---------------------------------------------------------------- shared
@pytest.mark.parametrize("name", LIFE)
def test_standin_loops_seamlessly_and_is_json(proj, name):
    res = R.apply(proj, name)
    an = proj.data.animations[res["animation"]]
    assert_seamless(an, R.RECIPES[name]["duration"])
    assert res["slots"] and all(s.attachment is None for s in proj.data.slots)
    json.dumps(res)                                              # the MCP returns it as is
    blends = [proj.data.slot(s).blend for s in res["slots"]]
    runs = 1 + sum(a != b for a, b in zip(blends, blends[1:]))
    assert runs <= 3, blends


def test_unknown_bones_and_bad_cycles_are_clear_errors(rig):
    for name, opt in (("prop_bob", {"prop": "nope"}), ("prop_blink", {"eyes": ["nope"]}), ("prop_dangle", {"strands": ["x"]}),
                      ("prop_sway_wind", {"chain": ["x"]}), ("prop_breathe_heavy", {"prop": "nope"})):
        with pytest.raises(ValueError, match="no bone"):
            R.apply(rig, name, name=name + "_e", options=opt)
    with pytest.raises(ValueError, match="whole number"):
        R.apply(rig, "prop_hover_spin", options={"turns": 1.5})
    with pytest.raises(ValueError, match="do not fit"):
        R.apply(rig, "prop_blink", duration=1.0, options={"blinks": 8})


def test_new_zzz_picture_fades_to_zero_before_its_edges():
    a = np.asarray(L._z_letter())[..., 3]
    assert a.max() > 200
    assert a[0].max() == a[-1].max() == a[:, 0].max() == a[:, -1].max() == 0


# ---------------------------------------------------------------- prop_bob
def test_bob_figure_8_tilt_and_shadow(rig):
    res = R.apply(rig, "prop_bob", into="idle", options={"prop": "pot", "trail": 4})
    an = rig.data.animations["idle"]
    D = 4.0
    assert_seamless(an, D)
    assert_untouched(rig, an)
    mv = an.bones[carrier(an, "fx_bob_pot")]["translate"]
    t, x, y = times(mv), vals(mv, "x"), vals(mv, "y")
    w = 2 * math.pi / D
    assert np.allclose(x, 14 * np.sin(w * t), atol=0.02) and np.allclose(y, 11 * np.sin(2 * w * t), atol=0.02), "x at f, y at 2f"
    assert res["frequencies"] == [0.25, 0.5]
    rot = an.bones[carrier(an, "fx_bobtilt_pot")]["rotate"]
    r = vals(rot)
    vx = np.cos(w * times(rot))
    assert np.corrcoef(r, vx)[0, 1] < -0.95, "leans into the sideways speed"
    assert times(rot)[np.argmin(r)] > 0.0, "and a little late (inertia)"
    sh = an.bones[next(b for b in an.bones if b.startswith("fx_prop_bob_shadow"))]
    st, ss = times(sh["scale"]), vals(sh["scale"], "x", 1.0)
    alpha = np.array([int(k.color[6:], 16) for k in an.slots[res["shadow_slot"]]["rgba"]])
    height = 11 * np.sin(2 * w * st)
    assert np.corrcoef(ss, height)[0, 1] < -0.99, "the shadow shrinks as the prop rises"
    assert np.corrcoef(alpha, 11 * np.sin(2 * w * times(an.slots[res["shadow_slot"]]["rgba"])))[0, 1] < -0.99, "and fades"
    assert rig.data.slot(res["shadow_slot"]).blend == "normal"
    names = [s.name for s in rig.data.slots]
    assert names.index(res["shadow_slot"]) < names.index("pot"), "the shadow is under the prop"
    assert qa.validate(rig.data)["ok"]


# ---------------------------------------------------------------- prop_blink
def test_blink_lid_glance_and_hop(rig):
    res = R.apply(rig, "prop_blink", into="idle", options={"prop": "pot", "eyes": ["eye_l", "eye_r"]})
    an = rig.data.animations["idle"]
    D = 5.0
    assert_seamless(an, D)
    assert_untouched(rig, an)
    assert len(res["blink_times"]) == 4, "3 blinks, one of them double"
    lid = an.bones[carrier(an, "fx_blink_eye_l")]["scale"]
    t, sy = times(lid), vals(lid, "y", 1.0)
    assert np.allclose(vals(lid, "x", 1.0), 1.0)
    for s in res["blink_times"]:
        shut = t[(sy < 0.999) & (t > s - 1e-3) & (t < s + 0.2)]   # a double blink restarts 7 frames on
        assert shut.max() - s == pytest.approx(5 / 30, abs=0.01), "1 -> 0.1 -> 1 in 5 frames"
        assert sy[np.argmin(np.abs(t - (s + 2 / 30)))] == pytest.approx(0.1, abs=1e-3), "frame 2 is fully shut"
        assert abs(s * 30 - round(s * 30)) < 0.01, "blinks start on a frame"
    assert all(0 < s < D - 0.2 for s in res["blink_times"] + res["hop_times"]), "never across the seam"
    gl = an.bones[carrier(an, "fx_glance_eye_r")]["translate"]
    assert np.abs(vals(gl, "x")).max() > 6, "the eyes glance"
    sq = an.bones[carrier(an, "fx_hopsquash_pot")]["scale"]
    sx_, sy_ = vals(sq, "x", 1.0), vals(sq, "y", 1.0)
    assert np.allclose(sx_ * sy_, 1.0, atol=3e-3), "squash and stretch keep the volume"
    assert sy_.min() < 0.85 and sy_.max() > 1.05, "landing squash, take-off stretch"
    hop = vals(an.bones[carrier(an, "fx_hop_pot")]["translate"], "y")
    assert hop.max() == pytest.approx(26.0, abs=0.5)
    ev = [e.name for e in an.events]
    assert ev.count("blink") == 4 and ev.count("hop") == ev.count("hop_land") == 1
    assert qa.validate(rig.data)["ok"]


def test_blink_seed_changes_the_timing_not_the_rules(proj):
    a = R.apply(proj, "prop_blink", seed=1, name="a")
    b = R.apply(proj, "prop_blink", seed=2, name="b")
    assert a["blink_times"] != b["blink_times"]
    assert R.apply(proj, "prop_blink", seed=1, name="c")["blink_times"] == a["blink_times"]


# ---------------------------------------------------------------- prop_breathe_heavy
def test_breathe_keeps_volume_and_creaks_at_the_bottom(rig):
    res = R.apply(rig, "prop_breathe_heavy", into="idle", options={"prop": "pot", "breaths": 2, "rising": "dust"})
    an = rig.data.animations["idle"]
    D = 4.5
    assert_seamless(an, D)
    assert_untouched(rig, an)
    sc = an.bones[carrier(an, "fx_breath_pot")]["scale"]
    sx, sy = vals(sc, "x", 1.0), vals(sc, "y", 1.0)
    assert np.allclose(sx * sy, 1.0, atol=3e-3), "sx * sy = 1"
    assert sy.max() == pytest.approx(1.07, abs=0.003) and sy.min() < 1.0, "inhale stretches up, exhale squashes wide"
    rot = an.bones[carrier(an, "fx_creak_pot")]["rotate"]
    t, r = times(rot), vals(rot)
    Tb = D / 2
    for land in res["creak_times"]:
        after = r[(t > land) & (t < land + 0.25)]
        assert np.abs(after).max() > 1.0 and (np.diff(np.sign(after[np.abs(after) > 0.01])) != 0).sum() >= 2, "a fast wobble"
    inhale = r[(t % Tb) < L.BR_IN * Tb]
    assert np.abs(inhale).max() < 1e-3, "quiet while it inhales"
    assert [e.name for e in an.events].count("creak") == 2
    assert res["rising"] == 8 and qa.validate(rig.data)["ok"]


# ---------------------------------------------------------------- prop_hover_spin
def test_hover_spin_cos_turn_edge_and_glints(rig):
    res = R.apply(rig, "prop_hover_spin", into="idle", options={"prop": "pot", "turns": 3})
    an = rig.data.animations["idle"]
    D = 3.0
    assert_seamless(an, D)
    assert_untouched(rig, an)
    sp = an.bones[carrier(an, "fx_spin_pot")]["scale"]
    t, sx = times(sp), vals(sp, "x", 1.0)
    cs = np.cos(2 * math.pi * 3 * t / D)
    want = np.sign(np.where(cs == 0, 1, cs)) * np.maximum(np.abs(cs), L.COIN_EDGE)
    assert np.allclose(sx, want, atol=2e-3), "scaleX = cos(angle), never thinner than the edge"
    assert (np.diff(np.sign(sx)) != 0).sum() == 6, "3 turns = 6 edge-on moments"
    assert np.allclose(vals(sp, "y", 1.0), 1.0)
    edge = an.slots[res["edge_slot"]]["rgba"]
    ea = np.array([int(k.color[6:], 16) for k in edge])
    ec = np.abs(np.cos(2 * math.pi * 3 * times(edge) / D))
    assert ea[ec < 0.1].min() > ea[ec > 0.9].max() + 100, "the edge lights up edge-on"
    ga = an.slots[res["glint_slots"][1]]["rgba"]
    gt = times(ga)[np.array([int(k.color[6:], 16) for k in ga]) > 200]
    assert all(min(abs(g - f) for f in (0, 1, 2, 3)) < 0.03 for g in gt), "glints only when it faces front"
    assert [e.time for e in an.events if e.name == "glint"] == [0.0, 1.0, 2.0]


# ---------------------------------------------------------------- prop_dangle
def test_dangle_pendulum_period_and_lag_ordering(rig):
    res = R.apply(rig, "prop_dangle", into="idle", options={"prop": "lantern", "pivot": [200, 250], "rope_bone": "rope",
                                                           "strands": ["tassel_l", "tassel_r"]})
    an = rig.data.animations["idle"]
    D = 3.6
    assert_seamless(an, D)
    assert_untouched(rig, an)
    T_phys = 2 * math.pi * math.sqrt((200 / L.UNITS_PER_M) / L.GRAVITY)
    assert res["physical_period"] == pytest.approx(T_phys, abs=1e-3) and res["swings"] == round(D / T_phys)
    rope = an.bones[carrier(an, "fx_dangle_lantern")]["rotate"]
    t, r = times(rope), vals(rope)
    nz = r != 0                                                   # an exact zero key is one crossing, not two
    t, r = t[nz], r[nz]
    zc = t[1:][np.diff(np.sign(r)) != 0]
    assert np.allclose(np.diff(zc), res["period"] / 2, atol=0.04), "zero crossings every half period"
    assert an.bones[carrier(an, "fx_dangle_rope")]["rotate"][5].value == rope[5].value, "your rope swings with it"
    curves = [rope, an.bones[carrier(an, "fx_dangle_lag_lantern")]["rotate"]] + \
             [an.bones[s["carrier"]]["rotate"] for s in res["strands"]]
    first_peak = [times(k)[np.argmax(vals(k)[: len(k) // 2])] for k in curves]
    assert all(a < b for a, b in zip(first_peak, first_peak[1:])), f"each later down the chain: {first_peak}"
    amps = [np.abs(vals(k)).max() for k in curves]
    assert amps[0] > amps[1] > amps[2] > amps[3], "and smaller"
    assert [e.name for e in an.events].count("creak") == 2 * res["swings"]
    assert qa.validate(rig.data)["ok"]


def test_dangle_damped_dies_down_and_comes_back(proj):
    res = R.apply(proj, "prop_dangle", options={"steady": False})
    an = proj.data.animations[res["animation"]]
    assert_seamless(an, 3.6)
    r = vals(an.bones[next(b for b in an.bones if b.endswith("_dangle"))]["rotate"])
    n = len(r)
    assert np.abs(r[: n // 3]).max() > 2 * np.abs(r[int(n * 0.6): int(n * 0.75)]).max(), "the swing dies down"


# ---------------------------------------------------------------- prop_sway_wind
def test_sway_wave_travels_to_the_tip_and_leans_downwind(rig):
    leaf = [f"leaf{i}" for i in range(4)]
    res = R.apply(rig, "prop_sway_wind", into="calm", name="calm", options={"chain": leaf, "gusts": 0})
    an = rig.data.animations["calm"]
    D = 4.0
    assert_seamless(an, D)
    assert_untouched(rig, an)
    curves = [an.bones[b]["rotate"] for b in res["links"]]
    peak = [times(k)[np.argmax(vals(k)[: len(k) // 2])] for k in curves]
    assert all(a < b for a, b in zip(peak, peak[1:])), f"phase lag grows toward the tip: {peak}"
    amps = [np.abs(vals(k)).max() for k in curves]
    assert all(a < b for a, b in zip(amps, amps[1:])), "and so does the swing"
    assert sum(amps) == pytest.approx(6.0, rel=0.05), "sway = the tip's total bend"
    gust = R.apply(rig, "prop_sway_wind", into="gust", name="gust", options={"chain": leaf, "gusts": 2})
    lean = np.mean(vals(rig.data.animations["gust"].bones[gust["links"][-1]]["rotate"]))
    assert lean < -0.3, "an upright leaf leans downwind (clockwise for wind to the right)"
    assert_seamless(rig.data.animations["gust"], D)
    assert [e.name for e in rig.data.animations["gust"].events].count("gust") == 2
    left = R.apply(rig, "prop_sway_wind", into="left", name="left", options={"chain": leaf, "wind": -1})
    assert np.mean(vals(rig.data.animations["left"].bones[left["links"][-1]]["rotate"])) > 0.3
    flag = R.apply(rig, "prop_sway_wind", into="flag", name="flag", options={"chain": [f"flag{i}" for i in range(4)]})
    fr = vals(rig.data.animations["flag"].bones[flag["links"][-1]]["rotate"])
    assert abs(np.mean(fr)) < 0.3 * np.abs(fr).max(), "a flag along the wind flutters, it does not lean"
    assert qa.validate(rig.data)["ok"]


def test_sway_standin_ribbon_rides_the_chain(proj):
    res = R.apply(proj, "prop_sway_wind")
    sk = proj.data
    rows = [b for b in sk.bones if "_st_n" in b.name]
    assert len(rows) == len(res["links"]) + 1 and all(b.parent in res["links"] for b in rows)
    assert res["motes"] == 6


# ---------------------------------------------------------------- runtime
@needs_node
def test_all_six_on_an_artist_rig_play_in_the_runtime(rig):
    leaf = [f"leaf{i}" for i in range(4)]
    R.apply(rig, "prop_bob", into="bob", options={"prop": "pot", "trail": 3})
    R.apply(rig, "prop_blink", into="blink", options={"prop": "pot", "eyes": ["eye_l", "eye_r"]})
    R.apply(rig, "prop_breathe_heavy", into="sleep", options={"prop": "pot", "rising": "zzz"})
    R.apply(rig, "prop_hover_spin", into="spin", options={"prop": "lantern"})
    R.apply(rig, "prop_dangle", into="hang", options={"prop": "lantern", "strands": ["tassel_l"], "glow": 200})
    R.apply(rig, "prop_sway_wind", into="wind", options={"chain": leaf, "motes": 3})
    assert qa.validate(rig.data)["ok"]
    rig.save()
    anims = ["bob", "blink", "sleep", "spin", "hang", "wind"]
    d = runtime.run(rig, animations=anims, fps=10, geometry=True)
    assert not d.get("problems")
    for a in anims:
        fr = d["animations"][a]["frames"]
        assert fr
