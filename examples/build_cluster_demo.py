"""Build the cluster-pays family demo on a procedural 4x4 candy board: the whole win flow, back to back.
Writes ./out/cluster (a contact sheet per scene and a GIF) and refreshes docs/cluster.gif.

    python examples/build_cluster_demo.py

1. cluster_dim_in + cluster_dim: the board darkens around an 8-cell cluster, rim glows breathe
2. combo_banner (zoom) over the dim, then amount_to_bar: the amount drops into the bar, coins burst
3. jelly_pop: the cluster turns to jelly cubes and vanishes, coins fly to the bar
4. scatter_shine: comet glints on two scatters
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_recipes as R, qa, render, runtime  # noqa: E402
from claude_spine.fx_cluster import BAR, CLUSTER, COLS, ROWS, SCATTERS  # noqa: E402
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "cluster"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
FPS, W = 15, 300
VIEW = (-360.0, -371.0, 360.0, 371.0)
H = int(W * 742 / 720)
BG = (60, 30, 90, 255)


def board() -> Image.Image:
    s = 0.5
    im = Image.new("RGBA", (360, 371), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    to = lambda x, y: ((x + 360) * s, (371 - y) * s)  # noqa: E731
    cols = [(255, 90, 120), (80, 200, 90), (70, 140, 255), (255, 170, 50)]
    rng = np.random.default_rng(2)
    d.rectangle((*to(-250, 270), *to(235, -190)), fill=(150, 90, 220, 255))
    for j, y in enumerate(ROWS):
        for i, x in enumerate(COLS):
            (x0, y0), (x1, y1) = to(x - 40, y + 40), to(x + 40, y - 40)
            c = cols[int(rng.integers(4))]
            if [x, y] in SCATTERS:
                d.ellipse((x0, y0, x1, y1), fill=(170, 110, 60, 255), outline=(255, 230, 160, 255), width=3)
            else:
                d.rounded_rectangle((x0, y0, x1, y1), 12, fill=c + (255,))
    bx, by, bw, bh = BAR
    d.rounded_rectangle((*to(bx - bw / 2, by + bh / 2), *to(bx + bw / 2, by - bh / 2)), 10, fill=(70, 50, 160, 255),
                        outline=(200, 160, 255, 255), width=2)
    return im


p = Project(out / "cluster.json", new_skeleton("cluster", 720, 742))
p.write_image("board", board())
p.data.bones.append(Bone(name="board", parent="root"))
p.data.add_slot(Slot(name="board", bone="board", attachment="board"))
p.data.set_attachment("board", "board", RegionAttachment(path="board", width=720, height=742))

R.apply(p, "cluster_dim", into="s1_dim")
R.apply(p, "cluster_dim", into="s2_combo", name="dim2")
R.apply(p, "combo_banner", into="s2_combo", options={"style": "zoom"})
R.apply(p, "amount_to_bar", into="s2_combo", start=0.9)
R.apply(p, "jelly_pop", into="s3_jelly")
R.apply(p, "scatter_shine", into="s4_shine")
v = qa.validate(p.data)
assert v["ok"], v["errors"]
p.save()
SCENES = [("s1_dim_in", 0.1), ("s1_dim", 1.2), ("s2_combo", 1.9), ("s3_jelly", 0.9), ("s4_shine", 0.7)]
dump = runtime.run(p, animations=[n for n, _ in SCENES], fps=FPS, geometry=True)
assert not dump.get("problems"), dump.get("problems")
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
frames = []
for name, length in SCENES:
    fr = dump["animations"][name]["frames"][: max(1, int(length * FPS))]
    imgs = [render.render_frame(f["draws"], pages, VIEW, (W, H), BG).convert("RGB") for f in fr]
    frames += imgs
    idx = np.linspace(0, len(imgs) - 1, min(6, len(imgs))).round().astype(int)
    sheet = Image.new("RGB", (W * 3, H * 2))
    for k, j in enumerate(idx):
        sheet.paste(imgs[j], ((k % 3) * W, (k // 3) * H))
    sheet.save(out / f"{name}_sheet.png")
    print(name, len(imgs), "frames")
shutil.rmtree(Path(next(iter(dump["_page_files"].values()))).parent, ignore_errors=True)
frames[0].save(out / "cluster.gif", save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0)
shutil.copy(out / "cluster.gif", root / "docs" / "cluster.gif")
print("docs/cluster.gif", round((root / "docs" / "cluster.gif").stat().st_size / 1e6, 2), "MB")
