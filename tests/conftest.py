import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import runtime, samples, spine_cli  # noqa: E402

needs_node = pytest.mark.skipif(not runtime.available(), reason="Node not installed")
needs_spine = pytest.mark.skipif(not spine_cli.available(), reason="Spine editor CLI not installed")


@pytest.fixture
def character(tmp_path):
    return samples.make_character(tmp_path / "hero")


@pytest.fixture
def symbol(tmp_path):
    return samples.make_symbol(tmp_path / "gem")


@pytest.fixture
def arm(tmp_path):
    """A 300x60 striped arm on two 140 px bones, weighted by rig_mesh."""
    from PIL import Image, ImageDraw
    from claude_spine.ir import RegionAttachment, Slot, new_skeleton
    from claude_spine.project import Project
    d = tmp_path / "arm"
    (d / "images").mkdir(parents=True)
    im = Image.new("RGBA", (300, 60), (200, 120, 90, 255))
    m = Image.new("L", (300, 60), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, 299, 59], radius=28, fill=255)
    im.putalpha(m)
    im.save(d / "images" / "arm.png")
    sk = new_skeleton(width=300, height=60)
    sk.add_bone_world("upper", "root", -140, 0, 0, length=140)
    sk.add_bone_world("fore", "upper", 0, 0, 0, length=140)
    sk.slots.append(Slot(name="arm", bone="upper", attachment="arm"))
    sk.set_attachment("arm", "arm", RegionAttachment(x=140, y=0, width=300, height=60))
    p = Project(d / "arm.json", sk)
    p.save()
    return p
