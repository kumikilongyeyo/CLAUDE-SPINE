"""Previews: plays <PROJECT>.json in the real spine-core runtime over frames of the reference clip (dimmed so the
effects read) and writes previews/<animation>.gif + _sheet.png.  (clip-to-spine skill starter)

    ~/.local/bin/uvx --from git+https://github.com/kumikilongyeyo/CLAUDE-SPINE@<SHA> python render.py [animation ...]

reference_frames/<name>.jpg are CLEAN frames of the clip (no flash, no transition: a transition frame used as a
background makes every effect look wrong). BG maps each animation to its background.
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from claude_spine import render, runtime
from claude_spine.project import Project

ROOT = Path(__file__).resolve().parent
NAME = "<PROJECT>"
FPS, W = 20, 360
SCREEN = (720, 1089)                         # same as build.py
VIEW = (-SCREEN[0] / 2, -SCREEN[1] / 2, SCREEN[0] / 2, SCREEN[1] / 2)
H = int(W * SCREEN[1] / SCREEN[0])
BG = {"example_hit": "board"}                # animation -> reference_frames/<name>.jpg
DIM = 0.6                                    # darken the clip so the effects read

p = Project.open(ROOT / f"{NAME}.json")
want = sys.argv[1:] or list(BG)
dump = runtime.run(p, animations=want, fps=FPS, geometry=True)
assert not dump.get("problems"), dump.get("problems")
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
out = ROOT / "previews"
out.mkdir(exist_ok=True)
x0, y0, x1, y1 = VIEW
s = W / (x1 - x0)
for n in want:
    bg = np.asarray(Image.open(ROOT / "reference_frames" / f"{BG[n]}.jpg").convert("RGB").resize((W, H), Image.LANCZOS),
                    np.float32) / 255 * DIM
    frames = []
    for f in dump["animations"][n]["frames"]:
        acc = np.concatenate([bg, np.ones((H, W, 1), np.float32)], 2)
        for d in f["draws"]:
            page = pages.arr.get(d["page"])
            if page is None:
                continue
            PH, PW = page.shape[:2]
            v = np.asarray(d["v"], float).reshape(-1, 2)
            scr = np.c_[(v[:, 0] - x0) * s, H - (v[:, 1] - y0) * s]
            res = render._rasterize(scr, np.asarray(d["uv"], float).reshape(-1, 2) * [PW, PH],
                                    np.asarray(d["tri"], int).reshape(-1, 3), page, W, H)
            if res is None:
                continue
            py, px, layer = res
            col = np.array(d["color"], np.float32)
            if d.get("dark") is not None:     # two-colour tint (tintable imports), as spine-webgl (premultiplied)
                dk, ta = np.array(d["dark"], np.float32), layer[..., 3:4]
                layer[..., :3] = ((ta - layer[..., :3]) * dk + layer[..., :3] * col[:3]) * col[3]
                layer[..., 3:4] = ta * col[3]
            else:
                layer *= np.r_[col[:3] * col[3], col[3]]
            dst = acc[py:py + layer.shape[0], px:px + layer.shape[1]]
            if d.get("blend", "normal") == "additive":
                dst[..., :3] += layer[..., :3]
            else:
                dst[:] = layer + dst * (1 - layer[..., 3:4])
        frames.append(Image.fromarray((np.clip(acc[..., :3], 0, 1) * 255).astype(np.uint8)))
    frames[0].save(out / f"{n}.gif", save_all=True, append_images=frames[1:], duration=1000 // FPS, loop=0)
    idx = np.linspace(0, len(frames) - 1, 8).round().astype(int)
    sheet = Image.new("RGB", (W // 2 * 4, H // 2 * 2))
    for i, j in enumerate(idx):
        sheet.paste(frames[j].resize((W // 2, H // 2), Image.LANCZOS), ((i % 4) * (W // 2), (i // 4) * (H // 2)))
    sheet.save(out / f"{n}_sheet.png")
    print(n, len(frames), "frames")
shutil.rmtree(Path(next(iter(dump["_page_files"].values()))).parent, ignore_errors=True)
