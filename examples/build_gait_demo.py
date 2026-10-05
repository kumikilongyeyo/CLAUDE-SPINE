"""Build the gait demo: the procedural dog rigged by rig_quadruped (digitigrade) walking, trotting, galloping and
bounding over a ground that scrolls at the gait's own speed (a planted paw must stay glued to its tick mark), its
idle / alert / pounce / sleep / shake clips, and the generic gait on two test rigs (an insect tripod and a biped
walk / run). Renders through the official spine-core runtime and writes to ./out/gait, refreshing docs/gait.gif,
docs/gait_moves.gif and docs/gait_rigs.gif.

    python examples/build_gait_demo.py
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import qa, render, rig_gait as G, runtime  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "gait"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)

BG = (30, 32, 40)
GROUND = (70, 74, 86)
FPS = 25            # GIF frame rate
RT_FPS = 50         # runtime sampling (2 runtime frames per GIF frame)
LOOP_S = 4.0        # every GIF lasts this long


def font(px):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def dump(p, anims):
    d = runtime.run(p, animations=anims, fps=RT_FPS, geometry=True)
    assert d.get("ok", True) and not d.get("problems"), d.get("problems")
    return d


class Panel:
    """One looping cell of a GIF: a clip of a dump, framed on a fixed view, with an optional scrolling ground."""

    def __init__(self, dmp, anim, view, label, speed=0.0, facing=1, ground_y=0.0, skip=0.0, hold=0.5, oneshot=False):
        self.d, self.anim, self.view, self.label = dmp, anim, view, label
        self.speed, self.facing, self.gy = speed, facing, ground_y
        self.skip, self.hold, self.oneshot = skip, hold, oneshot
        self.frames = dmp["animations"][anim]["frames"]
        self.dur = dmp["animations"][anim]["duration"]
        self.pages = render._Pages(dmp["_page_files"], dmp.get("_pma", False))

    def frame_at(self, t):
        if self.oneshot:
            tt = t % (self.dur + self.hold)
            tt = min(tt, self.dur)
        else:
            span = self.dur - self.skip
            tt = self.skip + (t % span)
        i = int(round(tt * RT_FPS))
        return self.frames[min(i, len(self.frames) - 1)], tt

    def render(self, t, size):
        W, H = size
        f, tt = self.frame_at(t)
        bg = Image.new("RGBA", size, BG + (255,))
        x0, y0, x1, y1 = self.view
        s = min(W / (x1 - x0), H / (y1 - y0))
        ox = (W - (x1 - x0) * s) / 2
        oy = (H - (y1 - y0) * s) / 2
        gy = H - ((self.gy - y0) * s + oy)
        dr = ImageDraw.Draw(bg)
        dr.rectangle([0, gy, W, H], fill=(40, 43, 54, 255))
        dr.line([0, gy, W, gy], fill=GROUND + (255,), width=2)
        if self.speed:
            # ground ticks scroll backwards at the gait speed: a planted paw rides its tick
            spacing = 40.0
            shift = (-self.facing * self.speed * t) % spacing
            x = x0 + shift - spacing
            while x < x1 + spacing:
                px = (x - x0) * s + ox
                dr.line([px, gy, px - 6, gy + 9], fill=GROUND + (255,), width=2)
                x += spacing
        fig = render.render_frame(f["draws"], self.pages, self.view, size, (0, 0, 0, 0))
        bg.alpha_composite(fig)
        dr = ImageDraw.Draw(bg)
        dr.text((8, 6), self.label, font=font(15), fill=(235, 235, 240, 255))
        return bg


def gif(panels, cols, cell, path, sheet_path=None):
    rows = (len(panels) + cols - 1) // cols
    W, H = cols * cell[0], rows * cell[1]
    frames = []
    for k in range(int(LOOP_S * FPS)):
        t = k / FPS
        im = Image.new("RGBA", (W, H), BG + (255,))
        for j, pnl in enumerate(panels):
            im.alpha_composite(pnl.render(t, cell), ((j % cols) * cell[0], (j // cols) * cell[1]))
        frames.append(im)
    pal = [f.convert("RGB").quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
           for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=int(1000 / FPS), loop=0, disposal=2)
    if sheet_path:
        idx = np.linspace(0, len(frames) - 1, 6).round().astype(int)
        sh = Image.new("RGBA", (W * 3, H * 2), BG + (255,))
        for i, j in enumerate(idx):
            sh.alpha_composite(frames[j], ((i % 3) * W, (i // 3) * H))
        sh.save(sheet_path)
    print(path.name, f"{path.stat().st_size / 1e6:.2f} MB", len(frames), "frames")
    return frames


# ------------------------------------------------------------------ the dog
dog = G.make_sample_quadruped(out / "dog")
rep = G.rig_quadruped(dog, leg_type="digitigrade", seed=7)
q = dog._quad
# long demo copies of the gaits so the physics strands reach steady state before the panel starts showing them
for g in ("walk", "trot", "gallop", "bound"):
    n = int(np.ceil(6.0 / rep["clips"][g]["duration"]))
    G._clip_gait(dog.data, q, g, None, 1.0, cycles=n, name=f"demo_{g}")
v = qa.validate(dog.data)
assert v["ok"], v["errors"]
b = qa.budget(dog.data, "mobile_character")
dog.save()
print("dog:", rep["counts"], "| budget ok", b["ok"], b["metrics"])
for c, r in rep["clips"].items():
    print(f"  {c:7s}", {k: r[k] for k in ("duration", "frequency_hz", "stride", "speed") if k in r})

anims = [f"demo_{g}" for g in ("walk", "trot", "gallop", "bound")] + ["idle", "alert", "pounce", "sleep", "shake"]
dd = dump(dog, anims)
view = (-250, -12, 290, 330)
cell = (280, 196)
gp = []
for g in ("walk", "trot", "gallop", "bound"):
    r = rep["clips"][g]
    gp.append(Panel(dd, f"demo_{g}", view, f"{g}  {r['frequency_hz']:.1f} Hz", speed=r["speed"], skip=2.0))
gif(gp, 2, cell, out / "gait.gif", out / "gait_sheet.png")
mp = [Panel(dd, "idle", view, "idle"), Panel(dd, "alert", view, "alert", oneshot=True, hold=0.4),
      Panel(dd, "pounce", view, "pounce", oneshot=True, hold=0.3), Panel(dd, "sleep", view, "sleep"),
      Panel(dd, "shake", view, "shake", oneshot=True, hold=0.4)]
gif(mp, 2, cell, out / "gait_moves.gif", out / "gait_moves_sheet.png")

# ------------------------------------------------------------------ generic gait on test rigs
bug = G.make_gait_test_rig(out / "bug", "hexapod")
legs6 = [f"ik_{s}{k}" for s in "LR" for k in (1, 2, 3)]
r6 = G.gait(bug, legs6, "body", "tripod", name="tripod")
r6w = G.gait(bug, legs6, "body", "wave", name="wave")
bug.save()
bip = G.make_gait_test_rig(out / "biped", "biped")
rb = G.gait(bip, ["ik_L", "ik_R"], "body", "walk", name="walk")
rr = G.gait(bip, ["ik_L", "ik_R"], "body", "run", name="run")
bip.save()
for pr in (bug, bip):
    v = qa.validate(pr.data)
    assert v["ok"], v["errors"]
db = dump(bug, ["tripod", "wave"])
dbp = dump(bip, ["walk", "run"])
cell2 = (280, 170)
rp = [Panel(db, "tripod", (-140, -14, 150, 140), f"tripod  {r6['frequency_hz']:.1f} Hz", speed=r6["speed"]),
      Panel(db, "wave", (-140, -14, 150, 140), f"wave  {r6w['frequency_hz']:.1f} Hz", speed=r6w["speed"]),
      Panel(dbp, "walk", (-110, -14, 120, 240), f"biped walk  {rb['frequency_hz']:.1f} Hz", speed=rb["speed"]),
      Panel(dbp, "run", (-110, -14, 120, 240), f"biped run  {rr['frequency_hz']:.1f} Hz", speed=rr["speed"])]
gif(rp, 2, cell2, out / "gait_rigs.gif", out / "gait_rigs_sheet.png")

for n in ("gait.gif", "gait_moves.gif", "gait_rigs.gif"):
    shutil.copy(out / n, root / "docs" / n)
print("done")
