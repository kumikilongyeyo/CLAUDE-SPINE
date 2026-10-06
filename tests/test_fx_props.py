"""prop_idle and liquid_slosh: they drive the artist's bones only through carriers, loop seamlessly, keep the liquid
surface on its WORLD-angle curve whatever the prop does, and clip the liquid layers to the vessel."""
import math

import pytest

from claude_spine import fx_recipes as R, qa, runtime
from claude_spine.fx_props import SURF, TILT, keyed
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project
from conftest import needs_node
from PIL import Image


def rig(tmp_path):
    p = Project(tmp_path / "t.json", new_skeleton("t", 512, 512))
    sk = p.data
    sk.bones += [Bone(name="bottle", parent="root", x=10, y=-20), Bone(name="liquid", parent="bottle", y=6)]
    for n, b in (("back", "bottle"), ("liq", "liquid"), ("foam", "liquid"), ("front", "bottle")):
        p.write_image(n, Image.new("RGBA", (64, 64), (255, 255, 255, 255)))
        sk.add_slot(Slot(name=n, bone=b, attachment=n))
        sk.set_attachment(n, n, RegionAttachment(path=n, width=64, height=64))
    return p


def test_prop_idle_drives_carriers_never_the_artists_bone(tmp_path):
    p = rig(tmp_path)
    res = R.apply(p, "prop_idle", into="idle", options={"prop": "bottle", "glow": 300.0})
    an = p.data.animations["idle"]
    assert "bottle" not in an.bones and set(res["carriers"]) <= set(an.bones)
    bottle = next(b for b in p.data.bones if b.name == "bottle")
    assert bottle.parent in res["carriers"], "a carrier sits above the prop"
    rot = an.bones[[c for c in res["carriers"] if "tilt" in c][0]]["rotate"]
    vals = [k.value or 0 for k in rot]
    assert min(vals) == pytest.approx(-14.0, abs=0.5) and max(vals) == pytest.approx(4.0, abs=0.5), "tilt + overshoot"
    assert rot[0].value == rot[-1].value or (rot[0].value or 0) == (rot[-1].value or 0), "seamless loop"
    glow = next(s for s in p.data.slots if s.name == res["glow_slot"])
    assert p.data.slots.index(glow) < [s.name for s in p.data.slots].index("back"), "the glow is under the prop"
    assert qa.validate(p.data)["ok"]


def test_liquid_slosh_holds_the_world_angle_and_clips_the_liquid(tmp_path):
    p = rig(tmp_path)
    R.apply(p, "prop_idle", into="idle", options={"prop": "bottle"})
    res = R.apply(p, "liquid_slosh", into="idle", options={"liquid": "liquid", "clip": 100.0})
    an = p.data.animations["idle"]
    tilt_car = [b for b in an.bones if b.startswith("fx_proptilt")][0]
    D = R.RECIPES["liquid_slosh"]["duration"]
    for k_l, k_t in zip(an.bones[res["carrier"]]["rotate"], an.bones[tilt_car]["rotate"]):
        world = (k_l.value or 0) + (k_t.value or 0)
        assert world == pytest.approx(26.0 * keyed(k_l.time / D, SURF), abs=0.05)
    names = [s.name for s in p.data.slots]
    clip = p.data.attachment(res["clip_slot"], res["clip_slot"])
    assert names.index(res["clip_slot"]) == names.index("liq") - 1 and clip.end == "foam" and clip.vertexCount == 16
    assert next(s for s in p.data.slots if s.name == res["clip_slot"]).bone == "bottle", "the clip rides the vessel"
    assert qa.validate(p.data)["ok"]


def test_polygon_clip_and_errors(tmp_path):
    p = rig(tmp_path)
    res = R.apply(p, "liquid_slosh", options={"liquid": "liquid", "clip": [[-50, -50], [50, -50], [50, 50], [-50, 50]]})
    assert p.data.attachment(res["clip_slot"], res["clip_slot"]).vertexCount == 4
    with pytest.raises(ValueError, match="no bone"):
        R.apply(p, "prop_idle", name="x", options={"prop": "nope"})
    with pytest.raises(ValueError, match="no bone"):
        R.apply(p, "liquid_slosh", name="y", options={"liquid": "nope"})


def test_stepped_holds_every_pose_two_frames(tmp_path):
    p = rig(tmp_path)
    R.apply(p, "prop_idle", into="idle", options={"prop": "bottle", "stepped": True})
    an = p.data.animations["idle"]
    k = an.bones[[b for b in an.bones if b.startswith("fx_proptilt")][0]]["rotate"]
    assert all(kk.curve == "stepped" for kk in k[:-1]) and k[1].time == pytest.approx(2 / 30, abs=1e-3)


@needs_node
def test_plays_in_the_runtime(tmp_path):
    p = rig(tmp_path)
    R.apply(p, "prop_idle", into="idle", options={"prop": "bottle", "glow": 300.0})
    R.apply(p, "liquid_slosh", into="idle", options={"liquid": "liquid", "clip": 100.0})
    p.save()
    d = runtime.run(p, animations=["idle"], fps=10, geometry=True)
    assert not d.get("problems") and d["animations"]["idle"]["frames"]
