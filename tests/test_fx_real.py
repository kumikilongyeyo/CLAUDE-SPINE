"""Realistic layers (bolt_link, crackle, surface_glow): link bones aimed and stretched exactly, stepped strikes from a
fixed set of pictures, loops that close, the glow twin that follows its slot's face swaps, and the runtime."""
import math

import numpy as np
import pytest
from PIL import Image

from claude_spine import fx_recipes as R, qa, runtime
from claude_spine.fx_real import NAMES, W_BOLT, tex_bolt, tex_crackle, tex_soft_disc
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project
from claude_spine.timeline import AnimBuilder
from conftest import needs_node


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


@pytest.fixture
def coin(tmp_path):
    """A coin whose face swaps to its back half-way through a spin (front / back slots on one bone)."""
    p = Project(tmp_path / "c.json", new_skeleton("c", 720, 720))
    sk = p.data
    sk.bones.append(Bone(name="coin", parent="root", y=20))
    for n in ("face", "back"):
        p.write_image(n, Image.new("RGBA", (64, 64), (230, 180, 60, 255)))
    sk.add_slot(Slot(name="front", bone="coin", attachment="face"))
    sk.set_attachment("front", "face", RegionAttachment(width=200, height=200))
    sk.add_slot(Slot(name="rear", bone="coin"))
    sk.set_attachment("rear", "back", RegionAttachment(width=200, height=200))
    ab = AnimBuilder(sk, "spin")
    ab.slot_attachment("front", [(0.0, "face"), (0.8, None), (1.6, "face")])
    ab.slot_attachment("rear", [(0.0, None), (0.8, "back"), (1.6, None)])
    ab.bone("coin", "scale", [(0, 1, 1), (0.8, 0.02, 1), (1.6, 1, 1)], "linear")
    return p


def _alpha(k):
    return int(k.color[6:8], 16)


def _closed(p, anim, slots):
    a = p.data.animations[anim]
    for s in slots:
        for tl, ks in a.slots[s].items():
            assert ks[0].model_dump(exclude={"time", "curve"}) == ks[-1].model_dump(exclude={"time", "curve"}), (s, tl)
    for b, tls in a.bones.items():
        for tl, ks in tls.items():
            assert ks[0].model_dump(exclude={"time", "curve"}) == ks[-1].model_dump(exclude={"time", "curve"}), (b, tl)


# ---------------------------------------------------------------- shared rules
@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("kit", ["", "realistic"])
def test_defaults_build_hidden_additive_and_valid(proj, name, kit):
    res = R.apply(proj, name, kit=kit)
    assert res["slots"] and res["event"] == f"fx_{name}"
    assert all(s.attachment is None and s.blend == "additive" for s in proj.data.slots)
    assert R.RECIPES[name]["roles"] and qa.validate(proj.data)["ok"]
    assert any(e.name == f"fx_{name}" and e.time == 0 for e in proj.data.animations[res["animation"]].events)


def test_procedural_pictures_fade_to_nothing_before_their_edges():
    for im in (tex_bolt(0), tex_bolt(2), tex_crackle(1), tex_soft_disc()):
        a = np.asarray(im, np.float32)[..., 3]
        assert np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]).max() == 0
        assert a.max() > 200


# ---------------------------------------------------------------- bolt_link
def test_each_link_is_one_bone_aimed_and_stretched_from_a_to_b(proj):
    pts = [[-200, 0], [100, 120], [150, -160]]
    res = R.apply(proj, "bolt_link", options={"points": pts, "links": [[0, 1], [1, 2], [2, 0]], "thick": 0.8})
    assert len(res["links"]) == 3
    for lk in res["links"]:
        (ax, ay), (bx, by) = pts[lk["link"][0]], pts[lk["link"][1]]
        b = proj.data.bone(lk["bone"])
        d = math.hypot(bx - ax, by - ay)
        assert (b.x, b.y) == (ax, ay)
        assert b.rotation == pytest.approx(math.degrees(math.atan2(by - ay, bx - ax)))
        assert b.scaleX == pytest.approx(d / W_BOLT)
        assert b.scaleY == pytest.approx(0.8 * math.sqrt(max(0.5, min(1.0, d / W_BOLT))))
        atts = proj.data.skin().attachments[lk["slot"]]
        assert set(atts) == {"fx", "fx2", "fx3"}
        for att in atts.values():              # starts at the bone, spans exactly the picture length
            assert att.x == pytest.approx(att.width / 2) and att.width == pytest.approx(W_BOLT)


def test_strikes_swap_pictures_mirror_and_flicker_stepped(proj):
    res = R.apply(proj, "bolt_link", duration=2.0, options={"rate": 0.05, "on": 0.7})
    a = proj.data.animations[res["animation"]]
    lk = res["links"][0]
    att = a.slots[lk["slot"]]["attachment"]
    names = [k.name for k in att]
    assert set(names) <= {None, "fx", "fx2", "fx3"} and len({n for n in names if n}) >= 2
    assert names[-1] is None and att[-1].time == pytest.approx(2.0)
    lit = sum(1 for n in names if n)
    assert 0.5 < lit / len(names) < 0.9                     # dark frames between strikes
    gaps = np.diff([k.time for k in att[1:-1]])
    assert gaps.min() >= 0.05 * 0.7 - 1e-3 and gaps.max() <= 0.05 * 1.4 + 1e-3
    assert all(k.curve == "stepped" for k in a.slots[lk["slot"]]["rgba"][:-1])
    sc = a.bones[lk["bone"]]["scale"]
    assert {k.x for k in sc} == {1.0} and min(k.y for k in sc) < 0 < max(k.y for k in sc)   # random mirror
    first = [k for k in a.slots[lk["slot"]]["rgba"]]
    assert _alpha(first[0]) < _alpha(max(first, key=_alpha))                                 # ramps in
    assert len(res["end_flares"]) == 4               # one per terminal of the default chain


def test_bolt_link_loop_closes(proj):
    res = R.apply(proj, "bolt_link", options={"loop": True})
    assert res["loop"] == 1.5
    _closed(proj, res["animation"], res["slots"])
    att = proj.data.animations[res["animation"]].slots[res["slots"][0]]["attachment"]
    assert att[0].time == 0 and att[-1].time == 1.5 and att[0].name == att[-1].name


def test_bolt_link_errors(proj):
    with pytest.raises(ValueError, match="two different points"):
        R.apply(proj, "bolt_link", options={"links": [[0, 9]]})
    with pytest.raises(ValueError, match="at least two"):
        R.apply(proj, "bolt_link", options={"points": [[0, 0]]})
    with pytest.raises(ValueError, match="same place"):
        R.apply(proj, "bolt_link", options={"points": [[0, 0], [0, 0]]})


# ---------------------------------------------------------------- crackle
def test_crackle_ring_turns_and_flickers(proj):
    res = R.apply(proj, "crackle", count=5, options={"radius": 100, "spin": 20})
    a = proj.data.animations[res["animation"]]
    bones = [b for b in proj.data.bones if b.name.startswith("fx_crackle_p")]
    assert res["points"] == 5 and len(bones) == 5
    for b in bones:
        assert math.hypot(b.x, b.y) == pytest.approx(100, abs=0.01)
        ang = math.degrees(math.atan2(b.y, b.x))
        assert (b.rotation - ang - 90) % 360 == pytest.approx(0, abs=1e-6) or \
            (b.rotation - ang - 90) % 360 == pytest.approx(360, abs=1e-6)               # along the rim
        rk = a.bones[b.name]["rotate"]
        assert all(abs(k.value) <= 20 + 1e-6 for k in rk) and len({k.value for k in rk}) > 3
    for s in res["slots"]:
        assert set(proj.data.skin().attachments[s]) == {"fx", "fx2", "fx3", "fx4"}
        names = [k.name for k in a.slots[s]["attachment"]]
        assert None in names[1:-1] and names[-1] is None


def test_crackle_fire_stands_on_its_points_and_faces_out(proj):
    res = R.apply(proj, "crackle", count=4, options={"kind": "fire"})
    assert res["kind"] == "fire"
    for b in (b for b in proj.data.bones if b.name.startswith("fx_crackle_p")):
        up = (-math.sin(math.radians(b.rotation)), math.cos(math.radians(b.rotation)))
        assert up[0] * b.x + up[1] * b.y == pytest.approx(math.hypot(b.x, b.y), rel=1e-6)   # points away from the centre
    for s in res["slots"]:
        for att in proj.data.skin().attachments[s].values():
            assert att.y == pytest.approx(att.height / 2, abs=0.01)                                  # base on the point
    rgba = proj.data.animations[res["animation"]].slots[res["slots"][0]]["rgba"]
    assert rgba[len(rgba) // 2].color.startswith("FFA040")


def test_crackle_given_points_kit_and_loop(proj):
    res = R.apply(proj, "crackle", kit="realistic", options={"points": [[0, 0, 30], [50, 10]], "loop": True})
    assert res["kit"]["roles"] == {"spark_1": "spark_01", "spark_2": "spark_02", "spark_3": "spark_03", "spark_4": "spark_04"}
    assert res["points"] == 2
    _closed(proj, res["animation"], res["slots"])
    with pytest.raises(ValueError, match="kind"):
        R.apply(proj, "crackle", options={"kind": "water"})


# ---------------------------------------------------------------- surface_glow
def test_glow_twin_follows_the_face_swaps(coin):
    res = R.apply(coin, "surface_glow", into="spin", options={"slot": "front", "pair": "rear"})
    names = [s.name for s in coin.data.slots]
    f, b = res["glow_slots"]
    assert names.index(f) == names.index("front") + 1 and names.index(b) == names.index("rear") + 1
    for twin, src in ((f, "front"), (b, "rear")):
        sl = coin.data.slot(twin)
        assert sl.bone == "coin" and sl.blend == "additive" and sl.attachment is None
        assert set(coin.data.skin().attachments[twin]) == set(coin.data.skin().attachments[src])
        a = coin.data.animations["spin"]
        assert [(k.time, k.name) for k in a.slots[twin]["attachment"]] == \
            [(k.time, k.name) for k in a.slots[src]["attachment"]]
        cols = a.slots[twin]["rgba"]
        assert [k.time for k in cols] == [0.0, 0.6, 1.3, 1.7, 2.2]
        assert cols[3].color == "FFF0C8F2" and _alpha(cols[0]) == 0
    assert qa.validate(coin.data)["ok"]


def test_glow_twin_without_keys_uses_the_setup_picture_and_custom_keys(coin):
    res = R.apply(coin, "surface_glow", start=0.5,
                  options={"slot": "front", "keys": [[0, "BFE6FF", 0], [1, "D8F2FF", 0.35], [1.5, "D8F2FF", 0]]})
    a = coin.data.animations[res["animation"]]
    s = res["glow_slots"][0]
    assert [(k.time, k.name) for k in a.slots[s]["attachment"]] == [(0.0, "face")]
    assert [k.time for k in a.slots[s]["rgba"]] == [0.5, 1.5, 2.0]
    assert a.slots[s]["rgba"][1].color == "D8F2FF59"
    assert coin.data.skin().attachments[s]["face"].path == "face"      # the twin still finds the source picture


def test_glow_errors(coin):
    with pytest.raises(ValueError, match="no slot"):
        R.apply(coin, "surface_glow", options={"slot": "nope"})
    with pytest.raises(ValueError, match="pair needs slot"):
        R.apply(coin, "surface_glow", options={"pair": "rear"})
    with pytest.raises(ValueError, match="shows no attachment"):
        R.apply(coin, "surface_glow", options={"slot": "rear", "follow": False})


# ---------------------------------------------------------------- runtime
@needs_node
@pytest.mark.parametrize("kit", ["", "realistic"])
def test_all_three_on_a_spinning_coin_play_in_the_runtime(coin, kit):
    R.apply(coin, "surface_glow", into="spin", kit=kit, options={"slot": "front", "pair": "rear"})
    R.apply(coin, "crackle", into="spin", kit=kit, front_of="rear", options={"radius": 105})
    R.apply(coin, "crackle", into="spin", kit=kit, name="flames", options={"kind": "fire", "radius": 100})
    R.apply(coin, "bolt_link", into="spin", kit=kit, options={"points": [[-260, 0], [0, 20], [260, 0]], "loop": True})
    assert qa.validate(coin.data)["ok"]
    coin.save()
    d = runtime.run(coin, animations=["spin"], fps=20, geometry=True)
    assert not d.get("problems"), d.get("problems")
    assert d["animations"]["spin"]["frames"]
