"""Contact sheet of rendered AE comps, one row per comp, 8 frames each, over a dark background.
Judge every comp here BEFORE it goes into Spine.  (clip-to-spine skill starter)

    ~/.local/bin/uvx --from git+https://github.com/kumikilongyeyo/CLAUDE-SPINE@<SHA> python ae_sheet.py OUT.png ae/frames/compA ae/frames/compB ...
"""
import glob
import sys

import numpy as np
from PIL import Image
from claude_spine import ae_bridge as B

out, dirs = sys.argv[1], sys.argv[2:]
rows = []
for d in dirs:
    fs = sorted(glob.glob(f"{d}/*.tif")) or sorted(glob.glob(f"{d}/*.png"))
    if not fs:
        sys.exit(f"no frames in {d}")
    tiles = []
    for j in np.linspace(0, len(fs) - 1, 8).round().astype(int):
        a = B.read_premultiplied(fs[j], "alpha")          # float 0..1 premultiplied RGBA (do NOT divide by 255)
        bg = np.zeros(a.shape[:2] + (3,), np.float32)
        bg[:] = (0.12, 0.1, 0.18)
        im = Image.fromarray((np.clip(a[..., :3] + bg * (1 - a[..., 3:4]), 0, 1) * 255).astype(np.uint8))
        im.thumbnail((180, 240))
        tiles.append(im)
    w, h = max(t.width for t in tiles), max(t.height for t in tiles)
    row = Image.new("RGB", (w * 8, h), (30, 25, 45))
    for i, t in enumerate(tiles):
        row.paste(t, (i * w, 0))
    rows.append(row)
sheet = Image.new("RGB", (max(r.width for r in rows), sum(r.height for r in rows)))
y = 0
for r in rows:
    sheet.paste(r, (0, y))
    y += r.height
sheet.save(out)
print(out)
