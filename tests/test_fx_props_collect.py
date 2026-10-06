"""Collect / payout props (prop_absorb, prop_overflow, counter_plate, prop_multiplier_slam, prop_charge, gem_glint):
they drive the artist's bones only through carriers, the motion is physical (accelerating pulls, gravity parabolas,
accelerating slams, monotonic fills), the events line up with the motion, and the loop closes."""
import math

import numpy as np
import pytest
from PIL import Image

from claude_spine import fx_recipes as R, qa, runtime
from claude_spine.fx_props_collect import (ABSORB_SHRINK, CHARGE_CRACKS, COLLECT_RECIPES, GEM_IDLE, OVER_G, _crack)
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project
from conftest import needs_node

ART = ("jar", "lid", "plate")


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


@pytest.fixture
def rig(tmp_path):
    """An artist's jar: a jar bone at its base, a lid on it, a number plate above; plain layers, no animation."""
    p = Project(tmp_path / "jar.json", new_skeleton("jar", 720, 720))
    sk = p.data
    sk.bones += [Bone(name="jar", parent="root", x=10, y=-150), Bone(name="lid", parent="jar", y=260),
                 Bone(name="plate", parent="root", y=240)]
    for n, b in (("body", "jar"), ("lid", "lid"), ("plate", "plate")):
        p.write_image(n, Image.new("RGBA", (64, 64), (200, 90, 60, 255)))
        sk.add_slot(Slot(name=n, bone=b, attachment=n))
        sk.set_attachment(n, n, RegionAttachment(path=n, width=64, height=64))
    return p


def _runs(p):
    runs = []
    for s in p.data.slots:
        if s.name.startswith("fx_") and (not runs or runs[-1] != s.blend):
            runs.append(s.blend)
    return runs


def _v(k, f, rest=0.0):
    v = getattr(k, f, None)
    return rest if v is None else float(v)


def _alpha(k):
    return int(k.color[6:8], 16)


def _events(p, anim, name):
    return [e for e in p.data.animations[anim].events if e.name == name]


def _no_artist_keys(p, anim):
    an = p.data.animations[anim]
    assert not set(ART) & set(an.bones), "the artist's bones must never be keyed"


# ------------------------------------------------------------------ all six
@pytest.mark.parametrize("name", COLLECT_RECIPES)
def test_builds_on_an_empty_skeleton_in_few_blend_runs(proj, name):
    res = R.apply(proj, name)
    assert res["slots"] and res["event"] == f"fx_{name}" and qa.validate(proj.data)["ok"]
    assert all(s.attachment is None for s in proj.data.slots)
    assert len(_runs(proj)) <= 2
    assert R.RECIPES[name].get("normal_blend") or {s.blend for s in proj.data.slots} == {"additive"}
    assert set(R.ROLES[name]) and R.RECIPES[name]["roles"] is R.ROLES[name]


OPTS = {"prop_absorb": {"prop": "jar", "at": [0, 260]}, "prop_overflow": {"prop": "jar", "rim": [0, 260, 180], "floor": 0},
        "counter_plate": {"plate": "plate"}, "prop_multiplier_slam": {"prop": "jar"},
        "prop_charge": {"prop": "jar", "base": [0, 40]}, "gem_glint": {"prop": "jar", "size": [200, 240]}}


@pytest.mark.parametrize("name", COLLECT_RECIPES)
def test_drives_the_artists_bones_only_through_carriers(rig, name):
    res = R.apply(rig, name, options=OPTS[name])
    _no_artist_keys(rig, res["animation"])
    assert len(_runs(rig)) <= 2 and qa.validate(rig.data)["ok"]
    for car in res.get("carriers", []) + ([res["carrier"]] if "carrier" in res else []):
        assert rig.data.bone(car).rotation == 0 and car in rig.data.animations[res["animation"]].bones


def test_the_crack_picture_fades_before_its_edge():
    a = np.asarray(_crack())[..., 3]
    assert a.max() > 200 and max(a[0].max(), a[-1].max(), a[:, 0].max(), a[:, -1].max()) == 0


def test_unknown_bones_and_bad_options_are_clear_errors(rig):
    with pytest.raises(ValueError, match="no bone"):
        R.apply(rig, "prop_absorb", options={"prop": "nope"})
    with pytest.raises(ValueError, match="no bone"):
        R.apply(rig, "counter_plate", options={"plate": "nope"})
    with pytest.raises(ValueError, match="item"):
        R.apply(rig, "prop_absorb", options={"item": "gem"})
    with pytest.raises(ValueError, match="floor"):
        R.apply(rig, "prop_overflow", options={"rim": [0, 0, 100], "floor": 10})
    with pytest.raises(ValueError, match="level"):
        R.apply(rig, "prop_charge", options={"level": 1.5})
    with pytest.raises(ValueError, match="steps"):
        R.apply(rig, "counter_plate", options={"steps": 0})


# ------------------------------------------------------------------ prop_absorb
def test_absorb_items_arrive_in_order_accelerating_and_the_prop_gulps_on_each(rig):
    src = [[-260, 180], [250, 140], [-300, -20], [290, 40]]
    res = R.apply(rig, "prop_absorb", options={"prop": "jar", "at": [0, 260], "sources": src, "stagger": 0.15})
    an = rig.data.animations[res["animation"]]
    arr = res["arrivals"]
    assert arr == sorted(arr) and len(set(arr)) == len(src)
    hits = _events(rig, res["animation"], "prop_absorb_hit")
    assert [e.time for e in hits] == pytest.approx(arr) and [e.int for e in hits] == list(range(len(src)))
    g = rig.data.bone(res["group_bone"])
    assert (g.x, g.y) == (10, -150), "the anchor is the jar's origin"
    items = [b.name for b in rig.data.bones if b.name.startswith("fx_prop_absorb_item")]
    assert len(items) == len(src)
    for b, a in zip(items, arr):
        k = an.bones[b]["translate"]
        pts = np.array([(_v(q, "x"), _v(q, "y")) for q in k])
        d = np.hypot(pts[:, 0] - 0, pts[:, 1] - 260)
        assert all(np.diff(d) <= 1e-6), "always closing in on the mouth"
        assert d[-1] == pytest.approx(0, abs=0.5) and k[-1].time == pytest.approx(a, abs=1e-3)
        t = np.array([q.time for q in k])
        v = np.hypot(*np.diff(pts, axis=0).T) / np.diff(t)
        n3 = len(v) // 3
        assert v[-n3:].mean() > 2.5 * v[:n3].mean(), "the pull accelerates (ease in)"
        sc = an.bones[b]["scale"]
        assert abs(_v(sc[-1], "y", 1)) == pytest.approx(ABSORB_SHRINK, abs=0.02), "it shrinks as it arrives"
    car = rig.data.bone("jar").parent
    assert car.startswith("fx_propsquash")
    ks = an.bones[car]["scale"]
    for a in arr:                                   # a squash right after every arrival
        near = [q for q in ks if a < q.time <= a + 0.08]
        assert max(_v(q, "x", 1) for q in near) > 1.05 and min(_v(q, "y", 1) for q in near) < 0.95
    assert _v(ks[0], "x", 1) == pytest.approx(1) and _v(ks[-1], "x", 1) == pytest.approx(1, abs=0.01)


def test_absorb_orbs_are_all_additive(proj):
    R.apply(proj, "prop_absorb", options={"item": "orb"})
    assert {s.blend for s in proj.data.slots} == {"additive"}


# ------------------------------------------------------------------ prop_overflow
def test_overflow_coins_obey_gravity_spill_over_the_rim_hop_once_and_settle(rig):
    res = R.apply(rig, "prop_overflow", count=16, options={"prop": "jar", "rim": [0, 260, 180], "floor": 0, "size": 50})
    an = rig.data.animations[res["animation"]]
    coins = res["coins"]
    kinds = [c["kind"] for c in coins]
    assert kinds.count("edge") == 3 and kinds.index("spill") > kinds.index("pile") and kinds[-1] == "edge"
    for cn in coins:
        k = an.bones[cn["bone"]]["translate"]
        fl = [q for q in k if cn["launch"] - 1e-6 <= q.time <= cn["land"] + 1e-6]
        t = np.array([q.time - cn["launch"] for q in fl])
        y = np.array([_v(q, "y") for q in fl])
        x = np.array([_v(q, "x") for q in fl])
        assert np.polyfit(t, y, 2)[0] == pytest.approx(-OVER_G / 2, rel=1e-3), "a true parabola under gravity"
        assert np.polyfit(t, x, 1)[0] == pytest.approx(np.polyfit(t, x, 2)[1], rel=1e-2) or abs(np.polyfit(t, x, 2)[0]) < 1e-3
        if cn["kind"] == "spill":
            after = [q for q in k if q.time > cn["land"] + 1e-6]
            ya = [_v(q, "y") for q in after]
            assert abs(_v(k[-1], "x")) > 90 + 25, "it lands outside the rim"
            assert ya[-1] == pytest.approx(25, abs=0.01), "it rests on the floor (floor + half a coin)"
            sg = np.sign([d for d in np.diff(ya) if d != 0])
            assert max(ya) > 25 + 1 and (sg[1:] != sg[:-1]).sum() == 1 and sg[0] > 0, "one hop (up, then down), then rest"
            assert _v(k[-1], "x") == pytest.approx(_v(k[-2], "x"), abs=0.5), "skidded to rest"
        if cn["kind"] == "edge":
            sc = an.bones[cn["bone"]]["scale"]
            xs = [_v(q, "x", 1) for q in sc]
            assert min(xs) < -0.5 and xs[-1] == pytest.approx(1.0, abs=1e-3), "spins (scaleX = cos) and ends face-on"
            assert abs(_v(k[-1], "x")) == pytest.approx(90, abs=0.5), "it settles on the rim's edge"
    ev = _events(rig, res["animation"], "prop_overflow")
    assert len(ev) == 1 and ev[0].time == pytest.approx(res["overflow_at"])
    assert _runs(rig) == ["normal", "additive"]


# ------------------------------------------------------------------ counter_plate
def test_counter_ticks_speed_up_shake_grows_and_ends_with_a_big_punch(rig):
    res = R.apply(rig, "counter_plate", options={"plate": "plate", "steps": 6, "shake": 8.0})
    an = rig.data.animations[res["animation"]]
    ticks = res["ticks"]
    ev = _events(rig, res["animation"], "counter_tick")
    assert len(ev) == 6 and [e.int for e in ev] == [1, 2, 3, 4, 5, 6] and [e.time for e in ev] == pytest.approx(ticks)
    done = _events(rig, res["animation"], "counter_done")
    assert len(done) == 1 and done[0].time == pytest.approx(ticks[-1])
    gaps = np.diff(ticks)
    assert all(np.diff(gaps) < 0), "the count speeds up"
    mv = next(c for c in res["carriers"] if c.startswith("fx_plateshake"))
    sc = next(c for c in res["carriers"] if c.startswith("fx_platepop"))
    km, ks = an.bones[mv]["translate"], an.bones[sc]["scale"]
    win = lambda keys, a, b, f, rest: max(abs(_v(q, f, rest) - rest) for q in keys if a <= q.time < b)  # noqa: E731
    shakes = [win(km, a, a + 0.08, "x", 0.0) for a in ticks]
    assert all(np.diff(shakes) > 0), f"the shake grows with the value {shakes}"
    pops = [win(ks, a, a + 0.12, "x", 1.0) for a in ticks]
    assert pops[-1] > 2 * max(pops[:-1]), "the last tick is the big punch"
    assert rig.data.bone(res["group_bone"]).parent == "plate", "our glints ride the plate"
    _no_artist_keys(rig, res["animation"])


def test_counter_without_a_plate_brings_its_own(proj):
    res = R.apply(proj, "counter_plate")
    assert res["own_plate"] and _runs(proj) == ["normal", "additive"]
    assert proj.data.skin("default").attachments[res["slots"][0]]["fx"].path == "fx/pinata_mult_number"


# ------------------------------------------------------------------ prop_multiplier_slam
def test_slam_crouches_leaps_hangs_slams_accelerating_and_squashes(rig):
    res = R.apply(rig, "prop_multiplier_slam", options={"prop": "jar", "height": 150})
    an = rig.data.animations[res["animation"]]
    mv = next(c for c in res["carriers"] if c.startswith("fx_propmove"))
    sq = next(c for c in res["carriers"] if c.startswith("fx_propsquash"))
    assert rig.data.bone("jar").parent == sq and rig.data.bone(sq).parent == mv, "squash under the move: it squashes where it is"
    imp = res["impact"]
    ev = _events(rig, res["animation"], "prop_slam")
    assert len(ev) == 1 and ev[0].time == pytest.approx(imp)
    k = an.bones[mv]["translate"]
    t = np.array([q.time for q in k])
    y = np.array([_v(q, "y") for q in k])
    assert y.max() == pytest.approx(150, abs=0.5) and y[-1] == 0
    top = t[y.argmax()]
    drop = (t >= top) & (t <= imp + 1e-6)
    v = -np.diff(y[drop]) / np.diff(t[drop])
    assert len(v) >= 2 and all(np.diff(v) > 0), "the slam accelerates all the way down"
    up = (t > 0.16) & (t <= top)
    vu = np.diff(y[up]) / np.diff(t[up])
    assert vu[0] > 4 * vu[-1] > 0, "fast off the ground, hangs at the top"
    ks = an.bones[sq]["scale"]
    pre = [q for q in ks if q.time < 0.16]
    assert min(_v(q, "y", 1) for q in pre) < 0.9, "anticipation: it crouches first"
    at = min(ks, key=lambda q: abs(q.time - imp))
    assert _v(at, "y", 1) < 0.75 and _v(at, "x", 1) > 1.15, "squash on impact"
    st = an.bones[next(b.name for b in rig.data.bones if b.name.startswith("fx_prop_multiplier_slam_stamp") and "glint" not in b.name)]["scale"]
    sv = [_v(q, "x", 1) for q in st]
    assert sv[0] > 2.0 and sv[-1] == pytest.approx(1, abs=0.01) and min(sv) < 0.9, "stamp falls in and punches with overshoot"
    fall = [q for q in st if q.time <= res["stamp_hit"] + 1e-6]
    df = -np.diff([_v(q, "x", 1) for q in fall]) / np.diff([q.time for q in fall])
    assert len(df) >= 4 and all(np.diff(df) > 0), "the stamp accelerates onto the prop"


# ------------------------------------------------------------------ prop_charge
@pytest.mark.parametrize("level", [1.0, 0.55])
def test_charge_rises_monotonically_to_its_level(rig, level):
    res = R.apply(rig, "prop_charge", options={"prop": "jar", "level": level})
    an = rig.data.animations[res["animation"]]
    col = next(b.name for b in rig.data.bones if b.name.startswith("fx_prop_charge_column"))
    sy = [_v(q, "y", 1) for q in an.bones[col]["scale"]]
    assert all(np.diff(sy) >= -1e-9) and sy[0] == 0 and sy[-1] == pytest.approx(level, abs=1e-3)
    ev = _events(rig, res["animation"], "prop_charged")
    assert len(ev) == 1 and ev[0].time == pytest.approx(res["charged_at"])
    reached = next(q.time for q in an.bones[col]["scale"] if _v(q, "y", 1) >= level - 1e-3)
    assert reached == pytest.approx(res["charged_at"], abs=0.04)
    cracks = [s for s in res["slots"] if "crack" in s]
    assert len(cracks) == sum(1 for th in CHARGE_CRACKS if th <= level)
    over = [s for s in res["slots"] if "_ob_" in s]
    assert bool(over) == (level >= 1) and (res["loop"] is None) == (level >= 1)
    assert rig.data.bone(res["group_bone"]).parent == "jar", "the meter rides the prop"
    _no_artist_keys(rig, res["animation"])


def test_charge_pulse_quickens_as_it_fills(proj):
    res = R.apply(proj, "prop_charge")
    an = proj.data.animations[res["animation"]]
    car = res["carrier"]
    k = an.bones[car]["scale"]
    t = np.array([q.time for q in k])
    s = np.array([_v(q, "x", 1) for q in k]) - 1
    tf = res["charged_at"]

    def peaks(a, b):
        m = (t > a) & (t < b)
        w = s[m]
        return sum(1 for i in range(1, len(w) - 1) if w[i] > w[i - 1] and w[i] >= w[i + 1] and w[i] > 0)
    assert peaks(tf * 0.6, tf) > peaks(0, tf * 0.4)


# ------------------------------------------------------------------ gem_glint
def _first_last_equal(an):
    for tls in list(an.bones.values()) + list(an.slots.values()):
        for name, keys in tls.items():
            if name == "attachment":
                continue
            a, b = keys[0], keys[-1]
            for f in ("x", "y", "value", "color"):
                assert getattr(a, f, None) == getattr(b, f, None), (name, f)


def test_gem_glint_loop_closes_and_rides_the_prop(rig):
    R.apply(rig, "prop_idle", into="idle", options={"prop": "jar"})
    res = R.apply(rig, "gem_glint", into="idle", options={"prop": "jar"})
    an = rig.data.animations["idle"]
    _first_last_equal(an)
    assert rig.data.bone(res["group_bone"]).parent == "jar"
    _no_artist_keys(rig, "idle")
    assert res["loop"] == pytest.approx(3 * GEM_IDLE)


def test_gem_glint_sync_tilt_crosses_the_centre_at_the_tilt_peak(proj):
    res = R.apply(proj, "gem_glint", duration=2.0, options={"sync_tilt": True})
    assert res["loop"] == pytest.approx(3 * GEM_IDLE) and res["sweep_center"] == pytest.approx(0.45 * GEM_IDLE)
    an = proj.data.animations[res["animation"]]
    band = next(b.name for b in proj.data.bones if b.name.endswith("_band"))
    k = an.bones[band]["translate"]
    near = min(k, key=lambda q: abs(_v(q, "x")))
    assert near.time == pytest.approx(0.45 * GEM_IDLE, abs=0.04)
    _first_last_equal(an)


def test_gem_glint_bands_stay_inside_the_prop_and_clip_adds_a_mask(proj):
    res = R.apply(proj, "gem_glint", options={"size": [200, 240], "slant": -30.0})
    an = proj.data.animations[res["animation"]]
    band = next(b.name for b in proj.data.bones if b.name.endswith("_band"))
    sl = next(s.name for s in proj.data.slots if s.bone == band)
    H = proj.data.attachment(sl, "fx").height
    th = math.radians(-30.0)
    for kt, ks, kc in zip(an.bones[band]["translate"], an.bones[band]["scale"], an.slots[sl]["rgba"]):
        if _alpha(kc) == 0:
            continue
        half = 0.5 * H * _v(ks, "y", 1)
        for e in (-1, 1):                              # both ends of the band lie on or inside the ellipse
            ex, ey = _v(kt, "x") - e * half * math.sin(th), _v(kt, "y") + e * half * math.cos(th)
            assert (ex / 100) ** 2 + (ey / 120) ** 2 <= 1.01          # keys are rounded to 0.01
    res2 = R.apply(proj, "gem_glint", name="clipped", options={"clip": 90.0})
    clip = proj.data.attachment(res2["clip_slot"], res2["clip_slot"])
    assert clip.vertexCount == 16 and clip.end == res2["slots"][-1]
    assert qa.validate(proj.data)["ok"]


# ------------------------------------------------------------------ runtime
@needs_node
def test_all_six_play_on_the_artist_rig_in_the_runtime(rig):
    anims = []
    for n in COLLECT_RECIPES:
        anims.append(R.apply(rig, n, options=OPTS[n])["animation"])
    assert qa.validate(rig.data)["ok"]
    rig.save()
    d = runtime.run(rig, animations=anims, fps=10, geometry=True)
    assert not d.get("problems")
    assert all(d["animations"][a]["frames"] for a in anims)
