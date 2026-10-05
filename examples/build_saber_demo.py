"""Build the saber demo: the Spine half of the Saber port in six styles (lightsaber, neon frame, electric arc, fire
ring, laser, energy path), each drawing on then looping. Writes to ./out/saber and refreshes docs/saber.gif.

    python examples/build_saber_demo.py
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_recipes, qa, render, runtime  # noqa: E402
from claude_spine.ir import new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "saber"
shutil.rmtree(out, ignore_errors=True)
BG = (14, 12, 22, 255)
TILE = (-300, -150, 300, 150)                        # each beam's view, design units
CELLS = [
    ("default", dict(core="line", start=[-240, -60], end=[230, 70])),
    ("neon", dict(core="rect", rect=[440, 200, 40])),
    ("electric", dict(core="line", start=[-250, 0], end=[250, 0])),
    ("fire", dict(core="circle", radius=105)),
    ("laser", dict(core="line", start=[-260, 30], end=[260, -30])),
    ("energy", dict(core="points", points=[[-240, -50], [-120, 60], [0, -40], [120, 60], [240, -50]])),
]
W, H = 280, 140
frames_by_cell = []
for name, opts in CELLS:
    p = Project(out / name / f"{name}.json", new_skeleton(name, 600, 300))
    T = 2.0
    fx_recipes.apply(p, "saber", duration=T, name="on", options=dict(preset=name, draw="on", draw_time=0.6, **opts))
    fx_recipes.apply(p, "saber", duration=T, name="loop", options=dict(preset=name, **opts))
    v = qa.validate(p.data)
    assert v["ok"], v["errors"]
    p.save()
    dump = runtime.run(p, animations=["fx_on", "fx_loop"], fps=20, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems"), dump.get("problems")
    pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
    fr = []
    for anim in ("fx_on", "fx_loop"):
        for f in dump["animations"][anim]["frames"]:
            big = render.render_frame(f["draws"], pages, TILE, (W * 2, H * 2), BG)
            fr.append(big.resize((W, H), Image.LANCZOS))
    frames_by_cell.append((name, fr))
    print(name, "| draw calls", qa.budget(p.data, "desktop")["metrics"]["draw_calls"], "| bones", len(p.data.bones))

n = min(len(f) for _, f in frames_by_cell)
cols = 2
rows = (len(CELLS) + cols - 1) // cols
frames = []
for i in range(n):
    im = Image.new("RGBA", (W * cols, H * rows), BG)
    for k, (_, fr) in enumerate(frames_by_cell):
        im.alpha_composite(fr[i], ((k % cols) * W, (k // cols) * H))
    frames.append(im)
idx = np.linspace(0, n - 1, 6).round().astype(int)
sheet = Image.new("RGBA", (W * cols * 3, H * rows * 2), BG)
for j, i in enumerate(idx):
    sheet.alpha_composite(frames[i], ((j % 3) * W * cols, (j // 3) * H * rows))
sheet.save(out / "saber_sheet.png")
gif = out / "saber.gif"
pal = [f.convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
pal[0].save(gif, save_all=True, append_images=pal[1:], duration=50, loop=0, disposal=2)
shutil.copy(gif, root / "docs" / "saber.gif")
print("frames", n, "| gif", f"{gif.stat().st_size / 1e6:.1f} MB")
