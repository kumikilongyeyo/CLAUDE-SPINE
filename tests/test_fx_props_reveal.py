"""The reveal prop recipes (peek, shake, open, hit, upgrade, shatter): they move the artist's chest only through
carriers, and the motion is the physics they claim: a lid that falls shut and bounces lower each time, a rattle that
speeds up and grows, a lid thrown open that overshoots by exactly `overshoot` and settles, a squash along the blow,
a pop that peaks at exactly `grow`, cracks that grow in jerks and a prop that vanishes at the burst."""
import math

import numpy as np
import pytest
from PIL import Image

from claude_spine import fx_props_reveal as X, fx_recipes as R, qa, runtime
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project
from conftest import needs_node

NAMES = ["prop_peek", "prop_shake", "prop_open", "prop_hit", "prop_upgrade", "prop_shatter"]


def chest(tmp_path, lid_under_body=True):
    """An artist's chest: body bone at the base centre, lid bone at the hinge (back-left top corner)."""
    p = Project(tmp_path / "c.json", new_skeleton("c", 720, 720))
    sk = p.data
    sk.bones += [Bone(name="chest", parent="root", y=-100),
                 Bone(name="lid", parent="chest" if lid_under_body else "root", x=-120, y=140 if lid_under_body else 40)]
    for n, b, w, h, x, y in (("body", "chest", 240, 140, 0, 70), ("lidart", "lid", 240, 60, 120, 30)):
        p.write_image(n, Image.new("RGBA", (w, h), (150, 90, 40, 255)))
        sk.add_slot(Slot(name=n, bone=b, attachment=n))
        sk.set_attachment(n, n, RegionAttachment(path=n, x=x, y=y, width=w, height=h))
    return p


def val(keys, t, field="value", rest=0.0):
    """A linear timeline's value at time t (saved files drop default fields)."""
    ts = [k.time for k in keys]
    vs = [rest if getattr(k, field, None) is None else float(getattr(k, field)) for k in keys]
    return float(np.interp(t, ts, vs))


def series(keys, field="value", rest=0.0):
    return [(k.time, rest if getattr(k, field, None) is None else float(getattr(k, field))) for k in keys]


def runs(sk, slots):
    order = [s for s in sk.slots if s.name in set(slots)]
    return sum(1 for i, s in enumerate(order) if i == 0 or s.blend != order[i - 1].blend)


def artist_untouched(p, anim):
    an = p.data.animations[anim]
    assert "chest" not in an.bones and "lid" not in an.bones, "the artist's bones are never keyed"
    assert not ({"body", "lidart"} & set(an.slots)), "the artist's slots are never keyed"


# ---------------------------------------------------------------- prop_peek
def test_peek_lid_teases_in_two_tries_falls_shut_and_bounces_lower_each_time(tmp_path):
    p = chest(tmp_path)
    res = R.apply(p, "prop_peek", options={"lid": "lid", "prop": "chest"})
    an = p.data.animations[res["animation"]]
    artist_untouched(p, res["animation"])
    assert p.data.bone("lid").parent == res["lid_bone"], "a hinge carrier sits above the lid"
    rot = an.bones[res["lid_bone"]]["rotate"]
    A = 18.0
    assert val(rot, 0.45) == pytest.approx(0.55 * A, abs=0.8), "first try stops at about half"
    assert val(rot, 0.9) == pytest.approx(A, abs=0.1), "second try reaches the angle"
    shut = X.PEEK_SHUT + X.PEEK_FALL
    assert res["shut_at"] == pytest.approx(shut) and any(e.name == "prop_peek_shut" and e.time == pytest.approx(shut) for e in an.events)
    # free fall: accelerating (more angle lost in the second half of the fall than in the first)
    a0, am, a1 = val(rot, X.PEEK_SHUT), val(rot, X.PEEK_SHUT + X.PEEK_FALL / 2), val(rot, shut)
    assert a1 == pytest.approx(0, abs=1e-3) and (am - a1) > (a0 - am) * 2.5
    after = [(t, v) for t, v in series(rot) if t > shut]
    assert min(v for _, v in after) >= -1e-3, "the lid never goes through the rim"
    peak1 = max(v for _, v in after)
    assert peak1 == pytest.approx(X.PEEK_E ** 2 * A, rel=0.08), "rebound height = e^2 x the drop (restitution)"
    assert after[-1][1] == pytest.approx(0, abs=1e-3)
    # the eyes are gone before the lid falls
    for s in res["eyes"]:
        att = an.slots[s]["attachment"]
        assert att[-1].name is None and att[-1].time <= X.PEEK_SHUT + 1e-6
    assert runs(p.data, res["slots"]) == 1 and qa.validate(p.data)["ok"]


def test_peek_hinge_on_the_right_swings_clockwise_and_glint_mode(tmp_path):
    p = chest(tmp_path)
    res = R.apply(p, "prop_peek", options={"lid": "lid", "pivot": [120, 40], "look": "glint"})
    rot = p.data.animations[res["animation"]].bones[res["lid_bone"]]["rotate"]
    assert min(v for _, v in series(rot)) == pytest.approx(-18.0, abs=0.7) and "glint" in res
    with pytest.raises(ValueError, match="look"):
        R.apply(p, "prop_peek", name="x", options={"look": "wink"})


# ---------------------------------------------------------------- prop_shake
def test_shake_rattle_grows_faster_and_harder_then_holds_crouched_and_releases(tmp_path):
    p = chest(tmp_path)
    D, hold = 1.2, 0.2
    res = R.apply(p, "prop_shake", options={"prop": "chest"})
    an = p.data.animations[res["animation"]]
    artist_untouched(p, res["animation"])
    car = res["prop_bone"]
    rot = series(an.bones[car]["rotate"])
    early = [abs(v) for t, v in rot if t < D / 3]
    late = [abs(v) for t, v in rot if 2 * D / 3 < t < D]
    assert max(late) > 2.5 * max(early) and max(late) == pytest.approx(6.0, rel=0.1), "amplitude builds to `amp`"
    lands = res["landings"]
    gaps = np.diff(lands)
    assert gaps[-1] < 0.5 * gaps[0], "frequency rises: landings come faster"
    assert lands[-1] == pytest.approx(D, abs=1e-3), "the rattle ends on a landing (flat), not mid-tilt"
    # rocking on a corner: lifted by (w/2)|sin(angle)| so the low corner stays on the floor
    tr = an.bones[car]["translate"]
    for t in (0.6, 0.9, 1.1):
        assert val(tr, t, "y") == pytest.approx(120 * abs(math.sin(math.radians(val(an.bones[car]["rotate"], t)))), abs=0.3)
    sc = an.bones[car]["scale"]
    assert all(abs(val(an.bones[car]["rotate"], t)) < 1e-3 for t in np.linspace(D, D + hold, 7)), "still during the hold"
    assert val(sc, D + hold / 2, "y", 1.0) < 0.96, "crouched (tension) during the hold"
    assert max(v for t, v in series(sc, "y", 1.0) if t > D + hold) > 1.01, "springs back past rest on release"
    assert val(sc, res["duration"], "y", 1.0) == pytest.approx(1.0, abs=1e-3)
    # squash deepens: landing squash late is deeper than early
    sy = series(sc, "y", 1.0)
    assert min(v for t, v in sy if t < D / 3) > min(v for t, v in sy if 2 * D / 3 < t < D) + 0.03
    assert any(e.name == "prop_shake_release" and e.time == pytest.approx(D + hold) for e in an.events)
    # dust: normal blend, first, behind the chest; corners alternate
    names = [s.name for s in p.data.slots]
    assert names.index(res["slots"][-1]) < names.index("body"), "glow and dust sit behind the art"
    dust = [s for s in res["slots"] if p.data.slot(s).blend == "normal"]
    assert len(dust) == 4 and runs(p.data, res["slots"]) == 2
    xs = [p.data.bone(p.data.slot(s).bone).x for s in dust]
    assert {np.sign(x) for x in xs} == {-1.0, 1.0}, "dust kicks out at both corners"
    assert qa.validate(p.data)["ok"]


def test_shake_window_length_and_no_dust(tmp_path):
    p = chest(tmp_path)
    res = R.apply(p, "prop_shake", duration=2.0, options={"prop": "chest", "dust": 0, "hold": 0.3})
    assert res["release_at"] == pytest.approx(2.3) and res["dust"] == 0
    assert all(p.data.slot(s).blend == "additive" for s in res["slots"])


# ---------------------------------------------------------------- prop_open
def test_open_lid_is_thrown_overshoots_exactly_and_settles_while_the_body_crouches_then_stretches(tmp_path):
    p = chest(tmp_path)
    res = R.apply(p, "prop_open", options={"lid": "lid", "prop": "chest"})
    an = p.data.animations[res["animation"]]
    artist_untouched(p, res["animation"])
    rot = series(an.bones[res["lid_bone"]]["rotate"])
    P0, A = X.OPEN_POP, 75.0
    assert max(v for t, v in rot if t < P0) <= 2.05, "only a pressure tremble before the pop"
    assert max(v for _, v in rot) == pytest.approx(A * 1.15, abs=0.4), "overshoot is exactly `overshoot` of the angle"
    assert min(v for t, v in rot if t > P0 + 0.3) < A - 0.5, "it swings back under the angle (a real spring)"
    assert rot[-1][1] == pytest.approx(A, abs=0.05)
    # thrown against gravity: fastest at the start of the throw
    v0 = val(an.bones[res["lid_bone"]]["rotate"], P0 + 0.02) - val(an.bones[res["lid_bone"]]["rotate"], P0)
    v1 = val(an.bones[res["lid_bone"]]["rotate"], P0 + X.OPEN_THROW) - val(an.bones[res["lid_bone"]]["rotate"], P0 + X.OPEN_THROW - 0.02)
    assert v0 > 2 * v1 > 0
    st = res["settled_at"]
    assert all(abs(v - A) <= 0.02 * A + 0.05 for t, v in rot if t >= st)
    sy = an.bones[res["body_bone"]]["scale"]
    assert val(sy, P0, "y", 1.0) == pytest.approx(0.9, abs=0.005), "crouched by `windup` at the pop"
    assert max(v for t, v in series(sy, "y", 1.0)) == pytest.approx(1.06, abs=0.004), "stretches 0.6 x windup past rest"
    ev = {e.name: e.time for e in an.events}
    assert ev["prop_open"] == pytest.approx(P0) and ev["prop_open_settled"] == pytest.approx(st) and P0 < st < 1.2
    coins = [s for s in res["slots"] if p.data.slot(s).blend == "normal"]
    assert len(coins) == 8 and res["slots"][:8] == coins and runs(p.data, res["slots"]) == 2
    assert qa.validate(p.data)["ok"]


def test_open_coins_arc_up_and_land_on_the_floor(tmp_path):
    p = chest(tmp_path)
    res = R.apply(p, "prop_open", options={"lid": "lid", "prop": "chest"})
    an = p.data.animations[res["animation"]]
    for s in [s for s in res["slots"] if p.data.slot(s).blend == "normal"]:
        b = p.data.slot(s).bone
        ys = [v for _, v in series(an.bones[b]["translate"], "y")]
        assert max(ys) > 120, "up out of the opening"
        assert min(ys) < -140, "down to the floor (base is 140 below the opening)"


def test_open_gives_a_separate_lid_the_body_squash_and_retimes(tmp_path):
    p = chest(tmp_path, lid_under_body=False)
    res = R.apply(p, "prop_open", duration=4.8, options={"lid": "lid", "prop": "chest"})
    chain = []
    b = p.data.bone("lid").parent
    while b != "root":
        chain.append(b)
        b = p.data.bone(b).parent
    assert any(c.startswith("fx_open_lidsq_") for c in chain), "the lid gets the body's squash about the same base"
    an = p.data.animations[res["animation"]]
    assert {e.name: e.time for e in an.events}["prop_open"] == pytest.approx(2 * X.OPEN_POP)
    with pytest.raises(ValueError, match="overshoot"):
        R.apply(p, "prop_open", name="bad", options={"overshoot": 0.9})


# ---------------------------------------------------------------- prop_hit
def test_hit_squashes_along_the_blow_kicks_and_springs_back(tmp_path):
    p = chest(tmp_path)
    res = R.apply(p, "prop_hit", options={"prop": "chest"})
    an = p.data.animations[res["animation"]]
    artist_untouched(p, res["animation"])
    kick, d1, sq, d2 = res["carriers"]
    assert p.data.bone("chest").parent == d2 and p.data.bone(d2).parent == sq and p.data.bone(sq).parent == d1
    assert (p.data.bone(d1).rotation or 0) == pytest.approx(0) and (p.data.bone(d2).rotation or 0) == pytest.approx(0)
    sx = series(an.bones[sq]["scale"], "x", 1.0)
    assert min(v for _, v in sx) == pytest.approx(1 - 0.22, abs=0.01), "squash along the blow peaks at `squash`"
    t_min = min(sx, key=lambda kv: kv[1])[0]
    assert t_min < 0.06, "the squash peaks within 2 frames of contact"
    assert max(v for _, v in sx) > 1.02, "and rebounds into a stretch"
    tx = series(an.bones[kick]["translate"], "x")
    assert max(v for _, v in tx) == pytest.approx(18.0, abs=0.5) and min(v for _, v in tx) < -3, "kick, then swings back past rest"
    rz = series(an.bones[kick]["rotate"])
    first = next(v for _, v in rz if abs(v) > 0.5)
    assert first < 0, "a hit above the centre pushing right spins it clockwise (torque r x F)"
    for tl, f, rest in ((an.bones[sq]["scale"], "x", 1.0), (an.bones[kick]["translate"], "x", 0.0), (an.bones[kick]["rotate"], "value", 0.0)):
        assert val(tl, res["duration"], f, rest) == pytest.approx(rest, abs=1e-3)
    assert any(e.name == "prop_hit" and e.time == 0 for e in an.events)
    assert all(p.data.slot(s).blend == "additive" for s in res["slots"]) and qa.validate(p.data)["ok"]


def test_hit_direction_turns_the_squash_chain_and_sparks_fly_back(tmp_path):
    p = chest(tmp_path)
    res = R.apply(p, "prop_hit", options={"prop": "chest", "direction": -90})
    kick, d1, sq, d2 = res["carriers"]
    assert p.data.bone(d1).rotation == pytest.approx(-90) and p.data.bone(d2).rotation == pytest.approx(90)
    an = p.data.animations[res["animation"]]
    ty = series(an.bones[kick]["translate"], "y")
    assert min(v for _, v in ty) == pytest.approx(-18.0, abs=0.5), "pushed down"
    sparks = [s for s in res["slots"] if "_sp" in p.data.slot(s).bone]
    ups = [max(v for _, v in series(an.bones[p.data.slot(s).bone]["translate"], "y")) for s in sparks]
    assert np.mean(ups) > 40, "sparks fly back up toward the hitter"


# ---------------------------------------------------------------- prop_upgrade
def test_upgrade_crouches_flashes_at_the_swap_and_pops_exactly_grow_then_settles(tmp_path):
    p = chest(tmp_path)
    res = R.apply(p, "prop_upgrade", options={"prop": "chest"})
    an = p.data.animations[res["animation"]]
    artist_untouched(p, res["animation"])
    sc = an.bones[res["prop_bone"]]["scale"]
    SW = X.UP_SWAP
    assert val(sc, SW - 0.01, "y", 1.0) == pytest.approx(1 - X.UP_CROUCH, abs=0.004), "crouched charging"
    after = [(t, v) for t, v in series(sc, "y", 1.0) if t >= SW]
    peak_t, peak = max(after, key=lambda kv: kv[1])
    assert peak == pytest.approx(1.10, abs=0.003) and peak_t < SW + 0.15
    assert min(v for t, v in after if t > peak_t) < 0.985, "undershoots (spring), then settles"
    assert after[-1][1] == pytest.approx(1.0, abs=1e-3)
    assert any(e.name == "prop_upgrade_swap" and e.time == pytest.approx(SW) for e in an.events)
    names = [s.name for s in p.data.slots]
    behind = [s for s in res["slots"] if names.index(s) < names.index("body")]
    front = [s for s in res["slots"] if names.index(s) > names.index("lidart")]
    assert len(behind) == 3 and len(front) == len(res["slots"]) - 3, "glows behind the art, light over it"
    glow2 = an.slots[behind[1]]["rgba"]
    assert {k.color[:6] for k in glow2} == {"7DF4FF"}, "the new glow is color2"
    assert qa.validate(p.data)["ok"]


# ---------------------------------------------------------------- prop_shatter
def test_shatter_cracks_grow_in_jerks_then_the_prop_vanishes_and_shards_fall(tmp_path):
    p = chest(tmp_path)
    res = R.apply(p, "prop_shatter", options={"prop": "chest"})
    an = p.data.animations[res["animation"]]
    artist_untouched(p, res["animation"])
    SB = X.SH_BURST
    ev = {e.name: e.time for e in an.events}
    assert ev["prop_crack"] == 0 and ev["prop_shatter"] == pytest.approx(SB)
    sc = an.bones[res["prop_bone"]]["scale"]
    assert val(sc, SB - 0.01, "x", 1.0) == 1.0 and val(sc, SB, "x", 1.0) == 0 and val(sc, X.SH_D, "y", 1.0) == 0
    cracks = sorted({p.data.slot(s).bone for s in res["slots"] if "crack" in p.data.slot(s).bone})
    assert len(cracks) == res["cracks"] >= 7
    for b in cracks:
        g = [v for t, v in series(an.bones[b]["scale"], "x", 1.0) if t <= SB]
        assert all(b2 >= b1 - 1e-9 for b1, b2 in zip(g, g[1:])) and g[-1] == pytest.approx(1.0, abs=1e-3)
        speed = np.diff(g)
        assert (speed < 1e-6).sum() >= 3, "it pauses between bursts"
    shards = [s for s in res["slots"] if p.data.slot(s).blend == "normal"]
    assert len(shards) == 14 and res["slots"][:14] == shards and runs(p.data, res["slots"]) == 2
    for s in shards:
        b = p.data.slot(s).bone
        ys = series(an.bones[b]["translate"], "y")
        assert ys[-1][1] < max(v for _, v in ys) - 50, "ballistic: it comes down after its peak"
        assert abs(series(an.bones[b]["rotate"])[-1][1]) > 100, "and spins"
    assert qa.validate(p.data)["ok"]


def test_new_pictures_fade_out_before_their_edges():
    for make in X.EXTRA.values():
        a = np.asarray(make(), float)[..., 3]
        assert a.max() > 200
        assert a[0].max() == a[-1].max() == a[:, 0].max() == a[:, -1].max() == 0


# ---------------------------------------------------------------- shared
@pytest.mark.parametrize("name", NAMES)
def test_own_bones_when_no_bone_is_given(tmp_path, name):
    p = chest(tmp_path)
    res = R.apply(p, name)
    own = [b.name for b in p.data.bones if b.name.startswith(f"fx_{name}_") and b.name.endswith(("_prop", "_art", "_lid"))]
    assert own, "a bone of the recipe's own to parent the art to"
    assert p.data.bone("chest").parent == "root" and p.data.bone("lid").parent == "chest", "the artist's rig is left alone"
    assert runs(p.data, res["slots"]) <= 3
    assert all(s.attachment is None for s in p.data.slots if s.name in res["slots"])


@needs_node
def test_all_six_play_in_the_runtime_and_the_hit_squash_follows_the_blow(tmp_path):
    p = chest(tmp_path)
    for n in NAMES:
        opts = {"prop": "chest"}
        if n in ("prop_peek", "prop_open"):
            opts["lid"] = "lid"
        R.apply(p, n, options=opts)
    R.apply(p, "prop_hit", name="hit_down", options={"prop": "chest", "direction": -90})
    p.save()
    anims = [f"fx_{n}" for n in NAMES] + ["fx_hit_down"]
    d = runtime.run(p, animations=anims, fps=30, geometry=True)
    assert not d.get("problems")

    def body_box(anim, i):
        v = next(dr["v"] for dr in d["animations"][anim]["frames"][i]["draws"] if dr["slot"] == "body")
        xs, ys = v[0::2], v[1::2]
        return max(xs) - min(xs), max(ys) - min(ys)
    w0, h0 = body_box("fx_prop_hit", 0)
    w1, h1 = body_box("fx_prop_hit", 1)
    assert w1 < 0.88 * w0 and h1 > h0, "a blow to the right squashes the width"
    w2, h2 = body_box("fx_hit_down", 1)
    assert h2 < 0.88 * h0 and w2 > w0, "a blow downward squashes the height"
    sh = d["animations"]["fx_prop_shatter"]["frames"]
    i_after = int(math.ceil(X.SH_BURST * 30)) + 1
    assert not any(dr["slot"] == "body" and max(dr["v"]) - min(dr["v"]) > 1 for dr in sh[i_after]["draws"]), "the art is gone after the burst"
