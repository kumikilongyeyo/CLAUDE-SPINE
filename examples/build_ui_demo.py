"""Build the UI-polish demo: six cells on one screen, all in one 4 s animation "demo".

    python examples/build_ui_demo.py

  button_press   a candy SPIN button pressed twice (through a carrier above its bone; its own keys untouched)
  idle_shimmer   a symbol tile with a sheen sweeping across it and a glint (loops)
  focus_glow     a PLAY bar gets focus: enter flash, two breaths, exit fade
  popup          a BIG WIN panel springs in, sits, then anticipates and collapses
  padlock        locks (shackle swings shut, drops, bounces, clicks), then unlocks and pops off with a shine
  padlock break  unlocks, cracks and shatters

Writes to ./out/ui (skeleton, contact sheet, crops, GIF) and refreshes docs/ui.gif.
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_recipes, fx_ui, qa, render, runtime  # noqa: E402,F401  (fx_ui registers its recipes)
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402
from claude_spine.timeline import AnimBuilder  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "ui"
shutil.rmtree(out, ignore_errors=True)
BG = (22, 18, 32, 255)
CW, CH = 330, 280                                # cell size
LEN = 4.0


def font(px):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def rounded(w, h, rad, top, bottom, outline=None, ow=0, s=3, text=None, tcol=(255, 255, 255), tsize=0.45, lip=None):
    """A vertical-gradient rounded box drawn at s x and downsampled (with an optional darker lip and a label)."""
    W, H = w * s, h * s
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    m = Image.new("L", (W, H), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, W - 1, H - 1], rad * s, fill=255)
    g = np.linspace(0, 1, H)[:, None, None]
    col = np.array(top, float) * (1 - g) + np.array(bottom, float) * g
    body = Image.fromarray(np.repeat(col, W, 1).astype(np.uint8), "RGB").convert("RGBA")
    im.paste(body, (0, 0), m)
    d = ImageDraw.Draw(im)
    if lip:
        lm = Image.new("L", (W, H), 0)
        ImageDraw.Draw(lm).rounded_rectangle([0, int(H * 0.78), W - 1, H - 1], rad * s, fill=255)
        lm = Image.fromarray((np.asarray(lm) * (np.asarray(m) > 0)).astype(np.uint8))
        im.paste(Image.new("RGBA", (W, H), lip), (0, 0), lm)
        hi = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(hi).rounded_rectangle([6 * s, 4 * s, W - 6 * s, int(H * 0.36)], rad * s * 0.7, fill=(255, 255, 255, 70))
        im.alpha_composite(hi)
    if outline:
        d.rounded_rectangle([0, 0, W - 1, H - 1], rad * s, outline=outline, width=ow * s)
    if text:
        d.text((W / 2, H * (0.42 if lip else 0.5)), text, font=font(int(h * tsize * s)), anchor="mm", fill=tcol,
               stroke_width=2 * s, stroke_fill=(0, 0, 0, 120))
    return im.resize((w, h), Image.LANCZOS)


def tile(n=150):
    s = 3
    im = rounded(n, n, 26, (120, 60, 200), (52, 20, 110), outline=(255, 210, 90), ow=4)
    big = im.resize((n * s, n * s), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    c = n * s / 2
    d.polygon([(c, c - 50 * s), (c + 44 * s, c - 8 * s), (c, c + 52 * s), (c - 44 * s, c - 8 * s)], fill=(60, 220, 160), outline=(10, 90, 60), width=3 * s)
    d.polygon([(c, c - 50 * s), (c + 16 * s, c - 8 * s), (c, c + 52 * s), (c - 16 * s, c - 8 * s)], fill=(160, 255, 210))
    return big.resize((n, n), Image.LANCZOS)


sk = new_skeleton("ui", 1000, 600)
p = Project(out / "ui.json", sk)
cells = [(-CW, CH / 2), (0, CH / 2), (CW, CH / 2), (-CW, -CH / 2), (0, -CH / 2), (CW, -CH / 2)]
for i, (x, y) in enumerate(cells):
    sk.bones.append(Bone(name=f"cell{i}", parent="root", x=x, y=y))


def art(name, bone, im, x=0.0, y=0.0):
    p.write_image(name, im)
    sk.add_slot(Slot(name=name, bone=bone, attachment=name))
    sk.set_attachment(name, name, RegionAttachment(path=name, x=x, y=y, width=im.size[0], height=im.size[1]))
    return name


# the game's own art
sk.bones.append(Bone(name="btn", parent="cell0", y=-10))
art("btn", "btn", rounded(200, 80, 30, (255, 120, 60), (220, 40, 40), text="SPIN", lip=(150, 20, 30, 255)))
art("tile", "cell1", tile())
art("bar", "cell2", rounded(220, 80, 22, (40, 44, 70), (24, 26, 44), outline=(120, 140, 190), ow=2, text="PLAY", tcol=(220, 235, 255), tsize=0.4))
sk.bones.append(Bone(name="panel", parent="cell3"))
art("panel", "panel", rounded(260, 150, 24, (90, 30, 120), (40, 10, 70), outline=(255, 200, 70), ow=5, text="BIG WIN!", tcol=(255, 220, 90), tsize=0.26))
AnimBuilder(sk, "demo").event(LEN, "demo_end")                     # fixes the clip length

A = dict(into="demo")
fx_recipes.apply(p, "button_press", parent="cell0", y=-10, start=0.45, front_of="btn", options=dict(button="btn", width=200, height=80), **A)
fx_recipes.apply(p, "button_press", parent="cell0", y=-10, start=2.25, front_of="btn", options=dict(button="btn", width=200, height=80), **A)
fx_recipes.apply(p, "idle_shimmer", parent="cell1", start=0.0, front_of="tile", duration=2.0,
                 options=dict(width=150, height=150, corner=26), **A)
fx_recipes.apply(p, "idle_shimmer", parent="cell1", start=2.0, front_of="tile", duration=2.0,
                 options=dict(width=150, height=150, corner=26), **A)
F = dict(width=220, height=80)
fx_recipes.apply(p, "focus_glow", parent="cell2", start=0.3, front_of="bar", options=dict(F, phase="enter"), **A)
fx_recipes.apply(p, "focus_glow", parent="cell2", start=0.65, duration=1.4, front_of="bar", options=dict(F), **A)
fx_recipes.apply(p, "focus_glow", parent="cell2", start=2.05, duration=1.4, front_of="bar", options=dict(F), **A)
fx_recipes.apply(p, "focus_glow", parent="cell2", start=3.45, front_of="bar", options=dict(F, phase="exit"), **A)
fx_recipes.apply(p, "popup", parent="cell3", start=0.3, front_of="panel", options=dict(panel="panel", width=260, height=150, under="panel"), **A)
fx_recipes.apply(p, "popup", parent="cell3", start=3.0, front_of="panel", options=dict(panel="panel", width=260, height=150, phase="out"), **A)
lk = fx_recipes.apply(p, "padlock", parent="cell4", y=-20, start=0.2, options=dict(mode="lock", size=100), **A)
fx_recipes.apply(p, "padlock", parent="cell4", y=-20, start=1.75, options=dict(mode="unlock", size=100), **A)
# the locked padlock hides when its unlocking twin takes over
AnimBuilder(sk, "demo", replace=False)
a = sk.animations["demo"]
for s in lk["slots"]:
    if s in a.slots and "attachment" in a.slots[s]:
        keys = [(k.time, k.name) for k in a.slots[s]["attachment"]]
        if any(n for _, n in keys) and keys[-1][1] is not None:
            AnimBuilder(sk, "demo", replace=False).slot_attachment(s, keys + [(1.75, None)])
fx_recipes.apply(p, "padlock", parent="cell5", y=-20, start=0.6, options=dict(mode="break", size=100), **A)

v = qa.validate(sk)
assert v["ok"], v["errors"]
b = qa.budget(sk, "desktop")
p.save()
print("validate ok; draw calls", b["metrics"]["draw_calls"], "| bones", len(sk.bones), "| slots", len(sk.slots))

dump = runtime.run(p, animations=["demo"], fps=25, geometry=True)
assert dump.get("ok", True) and not dump.get("problems"), dump.get("problems")
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
view = (-1.5 * CW, -CH, 1.5 * CW, CH)
S = 2                                                               # render at 2x for the crops, downsample for the GIF
W = 560
H = int(W * (view[3] - view[1]) / (view[2] - view[0]))
big = [render.render_frame(f["draws"], pages, view, (W * S, H * S), BG) for f in dump["animations"]["demo"]["frames"]]
frames = [f.resize((W, H), Image.LANCZOS) for f in big]
gif = out / "ui.gif"
pal = [f.convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
pal[0].save(gif, save_all=True, append_images=pal[1:], duration=40, loop=0, disposal=2)
idx = np.linspace(0, len(frames) - 1, 12).round().astype(int)
sheet = Image.new("RGBA", (W * 3, H * 4))
for k, j in enumerate(idx):
    sheet.alpha_composite(frames[j], ((k % 3) * W, (k // 3) * H))
sheet.save(out / "ui_sheet.png")
# per-cell close-ups (2x) at chosen moments, for checking details
moments = {0: [0.47, 0.52, 0.6, 0.7, 2.6], 1: [0.4, 0.55, 0.62, 0.75, 0.9], 2: [0.32, 0.4, 0.66, 1.4, 3.6],
           3: [0.35, 0.45, 0.5, 0.7, 3.15], 4: [0.25, 0.5, 0.62, 2.1, 2.7], 5: [0.95, 1.2, 1.45, 1.6, 2.0]}
fps = 25
cw, ch = int(CW / (view[2] - view[0]) * W * S), int(CH / (view[3] - view[1]) * H * S)
for ci, ts in moments.items():
    col, row = ci % 3, ci // 3
    strip = Image.new("RGBA", (cw * len(ts), ch))
    for k, t in enumerate(ts):
        fr = big[min(len(big) - 1, int(round(t * fps)))]
        strip.alpha_composite(fr.crop((col * cw, row * ch, (col + 1) * cw, (row + 1) * ch)), (k * cw, 0))
    strip.save(out / f"cell{ci}.png")
shutil.copy(gif, root / "docs" / "ui.gif")
print("frames", len(frames), "| gif", gif, f"{gif.stat().st_size / 1e6:.1f} MB")
