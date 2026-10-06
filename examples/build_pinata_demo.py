"""Build the piñata-family demo on a procedural 5x4 board (the clip's layout): one scene per moment, played back to
back. Writes ./out/pinata (a contact sheet per scene and a GIF) and refreshes docs/pinata.gif.

    python examples/build_pinata_demo.py

1. wild_transform on three cells, then wild_glow (seamless hand-off), and a bubble_pop cascade on four corners
2. mult_cell_glow on two cells + mult_streak across the second row
3. wild_merge: five WILD cells feed one multiplier
4. pinata_hit above the board + coins_to_bar
5. jar_burst: the board bursts from the middle out, then the X5 flare flies into the sign
6. banner_backdrop + confetti_burst + a tier_swap (the loop runs half way)
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_recipes as R, qa, render, runtime  # noqa: E402
from claude_spine.fx_pinata import CELL, COLS, PINATA, ROWS  # noqa: E402
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "pinata"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
FPS, W = 12, 300
VIEW = (-360.5, -600.0, 360.5, 600.0)
H = int(W * (VIEW[3] - VIEW[1]) / (VIEW[2] - VIEW[0]))
BG = (34, 20, 52, 255)


def board() -> Image.Image:
    """A dark candy board: 5x4 rounded cells, a sign above, a win bar below (stands in for the game's art)."""
    s = 0.5
    im = Image.new("RGBA", (int(721 * s), int(1200 * s)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    to = lambda x, y: ((x + 360.5) * s, (600 - y) * s)  # noqa: E731
    for y in ROWS:
        for x in COLS:
            (x0, y0), (x1, y1) = to(x - CELL * 0.46, y + CELL * 0.46), to(x + CELL * 0.46, y - CELL * 0.46)
            d.rounded_rectangle((x0, y0, x1, y1), 10, fill=(70, 44, 96, 255), outline=(120, 86, 150, 255), width=2)
    (x0, y0), (x1, y1) = to(-90, 340), to(90, 280)
    d.rounded_rectangle((x0, y0, x1, y1), 12, fill=(40, 90, 130, 255), outline=(230, 190, 90, 255), width=3)
    (x0, y0), (x1, y1) = to(-312, -327), to(312, -397)
    d.rounded_rectangle((x0, y0, x1, y1), 10, fill=(40, 90, 130, 255), outline=(230, 190, 90, 255), width=3)
    (x0, y0), (x1, y1) = to(PINATA[0] - 50, PINATA[1] + 60), to(PINATA[0] + 50, PINATA[1] - 60)
    d.ellipse((x0, y0, x1, y1), fill=(200, 120, 60, 255), outline=(120, 60, 20, 255), width=3)
    return im


p = Project(out / "pinata.json", new_skeleton("pinata", 721, 1200))
p.write_image("board", board())
p.data.bones.append(Bone(name="board", parent="root"))
p.data.add_slot(Slot(name="board", bone="board", attachment="board"))
p.data.set_attachment("board", "board", RegionAttachment(path="board", width=721, height=1200))

c = lambda i, j: (COLS[i], ROWS[j])  # noqa: E731
SCENES = []


def scene(name, length, *calls):
    for recipe, kw in calls:
        R.apply(p, recipe, into=name, **kw)
    SCENES.append((name, length))


scene("s1_wild", 3.4, *[("wild_transform", dict(x=c(i, j)[0], y=c(i, j)[1], start=0.1 * k, name=f"wt{k}"))
                       for k, (i, j) in enumerate([(1, 1), (3, 1), (2, 2)])],
      *[("wild_glow", dict(x=c(i, j)[0], y=c(i, j)[1], start=0.6 + 0.1 * k, name=f"wg{k}")) for k, (i, j) in enumerate([(1, 1), (3, 1), (2, 2)])],
      ("bubble_pop", dict(start=1.6, options={"cells": [[c(0, 0)[0], c(0, 0)[1]], [c(4, 0)[0], c(4, 0)[1]], [c(0, 3)[0], c(0, 3)[1]], [c(4, 3)[0], c(4, 3)[1]]], "stagger": 0.04})))
scene("s2_mult", 2.0, ("mult_cell_glow", dict(x=c(0, 0)[0], y=c(0, 0)[1], name="mc0")), ("mult_cell_glow", dict(x=c(4, 2)[0], y=c(4, 2)[1], name="mc1")),
      ("mult_streak", {}))
scene("s3_merge", 1.7, ("wild_merge", {}))
scene("s4_hit", 2.6, ("pinata_hit", dict(x=PINATA[0], y=PINATA[1])), ("coins_to_bar", dict(start=0.7)))
scene("s5_jars", 2.7, ("jar_burst", {}))
scene("s6_banner", 4.0, ("banner_backdrop", {}), ("confetti_burst", dict(y=-300, start=0.3)),
      ("tier_swap", dict(y=120, start=2.2, options={"radius": 220.0})))
v = qa.validate(p.data)
assert v["ok"], v["errors"]
p.save()
print("bones", len(p.data.bones), "slots", len(p.data.slots))

dump = runtime.run(p, animations=[n for n, _ in SCENES], fps=FPS, geometry=True)
assert not dump.get("problems"), dump.get("problems")
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
frames = []
for name, length in SCENES:
    fr = dump["animations"][name]["frames"][: int(length * FPS)]
    imgs = [render.render_frame(f["draws"], pages, VIEW, (W, H), BG).convert("RGB") for f in fr]
    frames += imgs
    idx = np.linspace(0, len(imgs) - 1, 6).round().astype(int)
    sheet = Image.new("RGB", (W * 3, H * 2))
    for k, j in enumerate(idx):
        sheet.paste(imgs[j], ((k % 3) * W, (k // 3) * H))
    sheet.save(out / f"{name}_sheet.png")
    print(name, len(imgs), "frames")
shutil.rmtree(Path(next(iter(dump["_page_files"].values()))).parent, ignore_errors=True)
frames[0].save(out / "pinata.gif", save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0)
shutil.copy(out / "pinata.gif", root / "docs" / "pinata.gif")
print("docs/pinata.gif", round((root / "docs" / "pinata.gif").stat().st_size / 1e6, 2), "MB")
