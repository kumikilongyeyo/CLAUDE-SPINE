"""Build the prop-bundle demo: an artist-style chest (a body bone at the base, a lid bone at the hinge, no animation)
given a whole bonus moment by ONE call, bonus_chest_reveal (peek -> shake -> open + coin fountain -> upgrade), chained on
the members' events. Writes ./out/props_bundle and refreshes docs/props.gif.

    python examples/build_props_bundle_demo.py
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_recipes as R, qa, render, runtime  # noqa: E402
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "props_bundle"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)


def body_png():
    im = Image.new("RGBA", (244, 144), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((2, 2, 241, 141), 10, fill=(120, 66, 30, 255), outline=(60, 30, 10, 255), width=4)
    for x in (30, 200):
        d.rectangle((x, 2, x + 14, 141), fill=(220, 170, 60, 255))
    d.rectangle((2, 4, 241, 18), fill=(220, 170, 60, 255))
    d.rounded_rectangle((104, 30, 140, 74), 6, fill=(240, 200, 80, 255), outline=(120, 80, 20, 255), width=3)
    return im


def lid_png():
    im = Image.new("RGBA", (244, 64), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle((2, 2, 241, 80), 26, fill=(140, 78, 36, 255), outline=(60, 30, 10, 255), width=4)
    for x in (30, 200):
        d.rectangle((x, 6, x + 14, 61), fill=(220, 170, 60, 255))
    d.rectangle((2, 48, 241, 61), fill=(220, 170, 60, 255))
    return im


def chest(path):
    p = Project(path, new_skeleton("chest", 720, 720))
    sk = p.data
    # artist bones: chest at the base centre, lid at the hinge (back-left top corner), not at the art centres
    sk.bones += [Bone(name="chest", parent="root", x=0, y=-100, length=40), Bone(name="lid", parent="chest", x=-120, y=140, length=60)]
    p.write_image("body", body_png()); p.write_image("lidart", lid_png())
    sk.add_slot(Slot(name="body", bone="chest", attachment="body"))
    sk.set_attachment("body", "body", RegionAttachment(path="body", x=0, y=70, width=244, height=144))
    sk.add_slot(Slot(name="lid", bone="lid", attachment="lidart"))
    sk.set_attachment("lid", "lidart", RegionAttachment(path="lidart", x=120, y=30, width=244, height=64))
    return p


p = chest(out / "chest.json")
res = R.apply(p, "bonus_chest_reveal", options={"prop": "chest", "lid": "lid", "pivot": [-120, 40]})
v = qa.validate(p.data)
assert v["ok"], v["errors"]
p.save()
FPS, W = 20, 360
VIEW = (-380.0, -300.0, 380.0, 460.0)
H = int(W * (VIEW[3] - VIEW[1]) / (VIEW[2] - VIEW[0]))
dump = runtime.run(p, animations=[res["animation"]], fps=FPS, geometry=True)
assert not dump.get("problems"), dump.get("problems")
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
frames = [render.render_frame(f["draws"], pages, VIEW, (W, H), (18, 15, 26, 255)).convert("RGB")
          for f in dump["animations"][res["animation"]]["frames"]]
shutil.rmtree(Path(next(iter(dump["_page_files"].values()))).parent, ignore_errors=True)
frames[0].save(out / "props.gif", save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0)
idx = np.linspace(0, len(frames) - 1, 12).round().astype(int)
sheet = Image.new("RGB", (W // 2 * 6, H // 2 * 2))
for k, j in enumerate(idx):
    sheet.paste(frames[j].resize((W // 2, H // 2)), ((k % 6) * (W // 2), (k // 6) * (H // 2)))
sheet.save(out / "props_sheet.png")
shutil.copy(out / "props.gif", root / "docs" / "props.gif")
print(res["parts"], "end", res["end"], "docs/props.gif", round((root / "docs" / "props.gif").stat().st_size / 1e6, 2), "MB")
