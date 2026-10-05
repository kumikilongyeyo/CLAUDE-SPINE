"""Build the reel-moments demo: three procedural reels spin, the first two stop with reel_stop, the last one teases
with anticipation_reel (the two reels on its left dim), then thuds in. Writes to ./out/reels and refreshes
docs/reel_stop.gif.

    python examples/build_reels_demo.py

The spin is the game's own keys (a periodic motion-blurred strip sliding down, then the sharp column arriving at
spin speed); reel_stop takes over through its carrier bones, so none of those keys are touched.
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_recipes, qa, render, runtime  # noqa: E402
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402
from claude_spine.timeline import AnimBuilder  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "reels"
shutil.rmtree(out, ignore_errors=True)

RW, RH, CELL, GAP = 150, 450, 150, 12          # reel width, window height, symbol cell, gap between reels
PITCH = RW + GAP
BG = (22, 18, 32, 255)
SPEED = 1800.0                                  # spin speed, units/s (the strip slides one column per 0.25 s)


def font(px):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def symbol(kind: str) -> Image.Image:
    s = 4
    im = Image.new("RGBA", (CELL * s, CELL * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = CELL * s / 2
    if kind == "cherry":
        for dx in (-70, 70):
            d.ellipse([c + dx * s / 2 - 34 * s, c + 8 * s, c + dx * s / 2 + 34 * s, c + 76 * s - 8 * s], fill=(222, 30, 52), outline=(120, 0, 20), width=3 * s)
        d.line([c - 17 * s, c + 12 * s, c + 4 * s, c - 46 * s, c + 17 * s, c + 12 * s], fill=(40, 150, 40), width=6 * s, joint="curve")
    elif kind == "seven":
        d.text((c, c + 4 * s), "7", font=font(112 * s), anchor="mm", fill=(255, 196, 40), stroke_width=6 * s, stroke_fill=(150, 40, 10))
    elif kind == "diamond":
        d.polygon([(c, c - 52 * s), (c + 46 * s, c - 8 * s), (c, c + 54 * s), (c - 46 * s, c - 8 * s)], fill=(60, 170, 255), outline=(10, 50, 140), width=4 * s)
        d.polygon([(c, c - 52 * s), (c + 18 * s, c - 8 * s), (c, c + 54 * s), (c - 18 * s, c - 8 * s)], fill=(150, 220, 255))
    elif kind == "bar":
        d.rounded_rectangle([c - 56 * s, c - 26 * s, c + 56 * s, c + 26 * s], 10 * s, fill=(30, 30, 30), outline=(250, 250, 250), width=5 * s)
        d.text((c, c + 2 * s), "BAR", font=font(40 * s), anchor="mm", fill=(250, 250, 250))
    elif kind == "bell":
        d.chord([c - 44 * s, c - 50 * s, c + 44 * s, c + 50 * s], 180, 360, fill=(255, 210, 60), outline=(150, 90, 0), width=4 * s)
        d.rectangle([c - 44 * s, c - 2 * s, c + 44 * s, c + 22 * s], fill=(255, 210, 60), outline=(150, 90, 0), width=4 * s)
        d.ellipse([c - 10 * s, c + 18 * s, c + 10 * s, c + 38 * s], fill=(150, 90, 0))
    return im.resize((CELL, CELL), Image.LANCZOS)


def column(kinds) -> Image.Image:
    im = Image.new("RGBA", (RW, CELL * len(kinds)), (0, 0, 0, 0))
    for i, k in enumerate(kinds):
        im.alpha_composite(symbol(k), (0, i * CELL))
    return im


def blur_strip(kinds, periods: int = 3) -> Image.Image:
    """A strip `periods` columns tall whose content repeats every column, smeared vertically WITH wrap-around, so
    sliding it down one column and jumping back is invisible."""
    one = np.asarray(column(kinds)).astype(np.float32)
    acc = np.zeros_like(one)
    taps = 28
    for k in range(taps):
        acc += np.roll(one, k * 3, axis=0)
    acc /= taps
    tall = np.concatenate([acc] * periods, axis=0)
    return Image.fromarray(np.clip(tall, 0, 255).astype(np.uint8), "RGBA")


def cabinet(w: int, h: int, margin: int) -> Image.Image:
    """The machine front plus a background-coloured margin round it: opaque everywhere except the three reel windows,
    so the spinning strips above and below the windows never show."""
    s = 2
    W_, H_ = (w + 2 * margin) * s, (h + 2 * margin) * s
    im = Image.new("RGBA", (W_, H_), BG)
    d = ImageDraw.Draw(im)
    m = margin * s
    d.rounded_rectangle([m, m, m + w * s - 1, m + h * s - 1], 40 * s, fill=(92, 18, 36), outline=(255, 196, 64), width=10 * s)
    d.rounded_rectangle([m + 14 * s, m + 14 * s, m + w * s - 15 * s, m + h * s - 15 * s], 30 * s, outline=(170, 110, 30), width=4 * s)
    cx, cy = W_ / 2, H_ / 2
    for i in range(3):
        x0 = cx + ((i - 1) * PITCH - RW / 2) * s
        y0 = cy - RH / 2 * s
        d.rounded_rectangle([x0 - 6 * s, y0 - 6 * s, x0 + (RW + 6) * s, y0 + (RH + 6) * s], 14 * s, fill=(255, 196, 64))
        d.rounded_rectangle([x0, y0, x0 + RW * s, y0 + RH * s], 10 * s, fill=(0, 0, 0, 0))
    return im.resize((w + 2 * margin, h + 2 * margin), Image.LANCZOS)


# ------------------------------------------------------------------ the machine
sk = new_skeleton("reels", 720, 720)
p = Project(out / "reels.json", sk)
sk.bones.append(Bone(name="machine", parent="root"))
reels = [["cherry", "seven", "bell"], ["bar", "seven", "diamond"], ["diamond", "seven", "cherry"]]
p.write_image("reel_bg", Image.new("RGBA", (8, 8), (245, 238, 225, 255)))
for i, kinds in enumerate(reels):
    sk.bones.append(Bone(name=f"reel{i}", parent="machine", x=(i - 1) * PITCH))
    sk.bones.append(Bone(name=f"blur{i}", parent="machine", x=(i - 1) * PITCH, y=RH))   # 3 columns tall, bottom at the window floor
    sk.add_slot(Slot(name=f"bg{i}", bone="machine", attachment="reel_bg"))
    sk.set_attachment(f"bg{i}", "reel_bg", RegionAttachment(path="reel_bg", x=(i - 1) * PITCH, width=RW, height=RH))
for i, kinds in enumerate(reels):
    p.write_image(f"blur{i}", blur_strip(kinds))
    p.write_image(f"col{i}", column(kinds))
    sk.add_slot(Slot(name=f"blur{i}", bone=f"blur{i}", attachment=f"blur{i}"))
    sk.set_attachment(f"blur{i}", f"blur{i}", RegionAttachment(path=f"blur{i}", width=RW, height=RH * 3))
    sk.add_slot(Slot(name=f"col{i}", bone=f"reel{i}"))
    sk.set_attachment(f"col{i}", f"col{i}", RegionAttachment(path=f"col{i}", width=RW, height=RH))
CW, CH = 3 * PITCH + 60, RH + 90
MARGIN = 420                                    # covers the whole frame and the strips beyond it
p.write_image("cabinet", cabinet(CW, CH, MARGIN))
sk.add_slot(Slot(name="cabinet", bone="machine", attachment="cabinet"))
sk.set_attachment("cabinet", "cabinet", RegionAttachment(path="cabinet", width=CW + 2 * MARGIN, height=CH + 2 * MARGIN))

# ------------------------------------------------------------------ the spin (the game's own keys)
STOPS = [0.55, 0.9, 3.15]
ANTIC = (1.05, 3.15)
ab = AnimBuilder(sk, "spin")
T = RH / SPEED                                   # one column slides by in T seconds
for i, ts in enumerate(STOPS):
    arrive = 160 / SPEED
    off = ts - arrive                            # the blur strip hides, the sharp column comes in from above at spin speed
    pts, t = [], 0.0
    while t + T <= off + 1e-9:
        pts += [(t, 0, 0), (t + T - 1e-3, 0, -RH)]
        t += T
    pts += [(t, 0, 0), (off, 0, -RH * (off - t) / T)]
    ab.bone(f"blur{i}", "translate", pts, "linear")
    ab.slot_attachment(f"blur{i}", [(0, f"blur{i}"), (off, None)])
    ab.slot_attachment(f"col{i}", [(0, None), (off, f"col{i}")])
    ab.bone(f"reel{i}", "translate", [(0, 0, 160), (off, 0, 160), (ts, 0, 0)], "linear")

# ------------------------------------------------------------------ the FX (what the MCP's fx_recipe tool does)
for i, ts in enumerate(STOPS):
    fx_recipes.apply(p, "reel_stop", x=(i - 1) * PITCH, start=ts, into="spin", parent="machine", front_of="cabinet",
                     seed=7 + i, options=dict(reel=f"reel{i}", shake="machine", width=RW, height=RH))
fx_recipes.apply(p, "anticipation_reel", x=PITCH, start=ANTIC[0], duration=ANTIC[1] - ANTIC[0] + 0.1, into="spin",
                 parent="machine", front_of="cabinet",
                 options=dict(width=RW, height=RH, edge="flames", dim=[[-PITCH, 0, RW, RH], [-2 * PITCH, 0, RW, RH]]))
v = qa.validate(sk)
assert v["ok"], v["errors"]
b = qa.budget(sk, "mobile_banner")
p.save()
print("validate ok; draw calls", b["metrics"]["draw_calls"], "| bones", len(sk.bones), "| slots", len(sk.slots))

# ------------------------------------------------------------------ render through spine-core, framed on the machine
dump = runtime.run(p, animations=["spin"], fps=25, geometry=True)
assert dump.get("ok", True) and not dump.get("problems"), dump.get("problems")
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
pad = 70
view = (-CW / 2 - pad, -CH / 2 - pad, CW / 2 + pad, CH / 2 + pad)
W = 560
H = int(W * (view[3] - view[1]) / (view[2] - view[0]))
frames = [render.render_frame(f["draws"], pages, view, (W, H), BG) for f in dump["animations"]["spin"]["frames"]]
gif = out / "reel_stop.gif"
pal = [f.convert("RGB").quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
pal[0].save(gif, save_all=True, append_images=pal[1:], duration=40, loop=0, disposal=2)
sheet_idx = np.linspace(0, len(frames) - 1, 8).round().astype(int)
sheet = Image.new("RGBA", (W * 4, H * 2))
for k, j in enumerate(sheet_idx):
    sheet.alpha_composite(frames[j], ((k % 4) * W, (k // 4) * H))
sheet.save(out / "reel_stop_sheet.png")
shutil.copy(gif, root / "docs" / "reel_stop.gif")
print("frames", len(frames), "| gif", gif, f"{gif.stat().st_size / 1e6:.1f} MB")
