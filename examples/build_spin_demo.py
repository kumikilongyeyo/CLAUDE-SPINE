"""Build the spin-moments demo: turbo is pressed (a ripple runs across the symbol grid, speed lines frame the reels),
the three reels spin under spin_blur streaks, the first two land a scatter on the payline (reel_stop thuds, and the
second one hits with a big screen_shake + chromatic flash), and the last reel crawls in with its scatter stopping one
row short: near_miss brightens on the approach and implodes. Writes to ./out/spin and refreshes docs/spin.gif.

    python examples/build_spin_demo.py

The spin is the game's own keys: every reel follows the same speed profile spin_blur models (motor ramp, cruise,
constant-deceleration brake to 0 at the stop), so the streaks lag the strip and catch up exactly as they would over
real game reels. The FX move the game's bones only through carrier bones.
"""
import math
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_recipes, fx_spin, qa, render, runtime  # noqa: E402,F401  (fx_spin registers the spin recipes)
from claude_spine.fx_spin import _reel_speed  # noqa: E402
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402
from claude_spine.timeline import AnimBuilder  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "spin"
shutil.rmtree(out, ignore_errors=True)

RW, RH, CELL, GAP = 150, 450, 150, 12
PITCH = RW + GAP
BG = (22, 18, 32, 255)
SPEED, SPINUP = 2400.0, 0.22
LAUNCH = 0.7
STOPS = [1.7, 2.05, 3.2]
BRAKES = [0.35, 0.35, 0.9]          # the last reel crawls in
CLOSEST, FIZZLE = 0.32, 0.62         # near_miss: seconds after its start


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
            d.ellipse([c + dx * s / 2 - 34 * s, c + 8 * s, c + dx * s / 2 + 34 * s, c + 68 * s], fill=(222, 30, 52), outline=(120, 0, 20), width=3 * s)
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
    elif kind == "scatter":
        pts = []
        for k in range(16):
            r_ = (60 if k % 2 == 0 else 34) * s
            a = math.pi / 2 + k * math.pi / 8
            pts.append((c + r_ * math.cos(a), c - r_ * math.sin(a)))
        d.polygon(pts, fill=(170, 40, 210), outline=(70, 0, 110), width=4 * s)
        d.ellipse([c - 30 * s, c - 30 * s, c + 30 * s, c + 30 * s], fill=(255, 220, 90), outline=(150, 70, 0), width=3 * s)
        d.text((c, c + 2 * s), "S", font=font(44 * s), anchor="mm", fill=(120, 30, 160))
    return im.resize((CELL, CELL), Image.LANCZOS)


def blur_strip(kinds, periods: int = 3) -> Image.Image:
    """`periods` columns tall, content repeating every column, smeared vertically with wrap-around (seamless scroll)."""
    one = Image.new("RGBA", (RW, CELL * len(kinds)), (0, 0, 0, 0))
    for i, k in enumerate(kinds):
        one.alpha_composite(symbol(k), (0, i * CELL))
    a = np.asarray(one).astype(np.float32)
    acc = sum(np.roll(a, k * 3, axis=0) for k in range(28)) / 28
    return Image.fromarray(np.clip(np.concatenate([acc] * periods, 0), 0, 255).astype(np.uint8), "RGBA")


def cabinet(w: int, h: int, margin: int) -> Image.Image:
    s = 2
    W_, H_ = (w + 2 * margin) * s, (h + 2 * margin) * s
    im = Image.new("RGBA", (W_, H_), BG)
    d = ImageDraw.Draw(im)
    m = margin * s
    d.rounded_rectangle([m, m, m + w * s - 1, m + h * s - 1], 40 * s, fill=(30, 22, 70), outline=(120, 220, 255), width=8 * s)
    cx, cy = W_ / 2, H_ / 2
    for i in range(3):
        x0 = cx + ((i - 1) * PITCH - RW / 2) * s
        y0 = cy - RH / 2 * s
        d.rounded_rectangle([x0 - 6 * s, y0 - 6 * s, x0 + (RW + 6) * s, y0 + (RH + 6) * s], 14 * s, fill=(110, 200, 255))
        d.rounded_rectangle([x0, y0, x0 + RW * s, y0 + RH * s], 10 * s, fill=(0, 0, 0, 0))
    # payline markers either side of the middle row
    for side in (-1, 1):
        x = cx + side * (1.5 * PITCH + 4) * s
        d.polygon([(x, cy - 12 * s), (x + side * 18 * s, cy), (x, cy + 12 * s)][::side], fill=(255, 210, 60))
    return im.resize((w + 2 * margin, h + 2 * margin), Image.LANCZOS)


# ------------------------------------------------------------------ the machine
sk = new_skeleton("spin", 720, 720)
p = Project(out / "spin.json", sk)
sk.bones.append(Bone(name="machine", parent="root"))
start_kinds = [["bell", "bar", "cherry"], ["diamond", "cherry", "seven"], ["seven", "bell", "bar"]]
final_kinds = [["cherry", "scatter", "bell"], ["bar", "scatter", "diamond"], ["scatter", "seven", "cherry"]]
below_kinds = [["seven", "bar", "diamond"], ["bell", "seven", "cherry"], ["diamond", "bar", "bell"]]
blur_kinds = [["cherry", "seven", "bell"], ["bar", "seven", "diamond"], ["diamond", "seven", "cherry"]]
p.write_image("reel_bg", Image.new("RGBA", (8, 8), (44, 36, 86, 255)))      # dark reels: additive light reads
for k in {k for col in start_kinds + final_kinds + below_kinds for k in col}:
    p.write_image(f"sym_{k}", symbol(k))
for i in range(3):
    x = (i - 1) * PITCH
    sk.bones.append(Bone(name=f"blur{i}", parent="machine", x=x, y=RH))
    sk.bones.append(Bone(name=f"start{i}", parent="machine", x=x))
    sk.bones.append(Bone(name=f"reel{i}", parent="machine", x=x))
    sk.add_slot(Slot(name=f"bg{i}", bone="machine", attachment="reel_bg"))
    sk.set_attachment(f"bg{i}", "reel_bg", RegionAttachment(path="reel_bg", x=x, width=RW, height=RH))
for i in range(3):
    p.write_image(f"blur{i}", blur_strip(blur_kinds[i]))
    sk.add_slot(Slot(name=f"blur{i}", bone=f"blur{i}"))
    sk.set_attachment(f"blur{i}", f"blur{i}", RegionAttachment(path=f"blur{i}", width=RW, height=RH * 3))


def cells(prefix, parent, kinds, y0, show):
    for j, k in enumerate(kinds):
        bn = f"{prefix}_{j}"
        sk.bones.append(Bone(name=bn, parent=parent, y=y0 - j * CELL))
        sk.add_slot(Slot(name=bn, bone=bn, attachment=f"sym_{k}" if show else None))
        sk.set_attachment(bn, f"sym_{k}", RegionAttachment(path=f"sym_{k}", width=CELL, height=CELL))


for i in range(3):
    cells(f"st{i}", f"start{i}", start_kinds[i], CELL, True)
    cells(f"sym{i}", f"reel{i}", final_kinds[i] + below_kinds[i], CELL, False)
CW, CH = 3 * PITCH + 60, RH + 90
MARGIN = 520
p.write_image("cabinet", cabinet(CW, CH, MARGIN))
sk.add_slot(Slot(name="cabinet", bone="machine", attachment="cabinet"))
sk.set_attachment("cabinet", "cabinet", RegionAttachment(path="cabinet", width=CW + 2 * MARGIN, height=CH + 2 * MARGIN))

# ------------------------------------------------------------------ the spin (the game's own keys, same speed profile)
ab = AnimBuilder(sk, "spin")
for i, (ts, br) in enumerate(zip(STOPS, BRAKES)):
    stop = ts - LAUNCH
    t = np.linspace(0, stop, int(round(stop * 1000)) + 1)
    v = _reel_speed(t, SPEED, SPINUP, stop, br)
    X = np.concatenate([[0], np.cumsum(0.5 * (v[1:] + v[:-1]) * np.diff(t))])
    Xs = X[-1]
    swap = float(np.interp(Xs - 3 * CELL, X, t))         # the final column comes in 3 cells above its rest
    # the old symbols slide away, the blur strip scrolls behind them (seamless every RH), then the final column arrives
    hide_start = float(np.interp(RH * 0.7, X, t))
    tt = np.arange(0, hide_start + 1e-9, 0.01)
    ab.bone(f"start{i}", "translate", [(0, 0, 0)] + [(LAUNCH + u, 0, -float(np.interp(u, t, X))) for u in tt[1:]], "linear")
    pts, q_prev = [(0.0, 0, 0), (LAUNCH, 0, 0)], 0.0
    for u in np.arange(0.01, swap + 1e-9, 0.01):
        xx = float(np.interp(u, t, X))
        q = xx % RH
        if q < q_prev:                                    # wrap: key the jump exactly
            tw = float(np.interp(xx - q, X, t))
            pts += [(LAUNCH + tw - 0.0005, 0, -RH + 1e-3), (LAUNCH + tw, 0, 0)]
        pts.append((LAUNCH + u, 0, -q))
        q_prev = q
    ab.bone(f"blur{i}", "translate", sorted({round(a, 4): (a, b, c) for a, b, c in pts}.values()), "linear")
    ab.slot_attachment(f"blur{i}", [(0, None), (LAUNCH, f"blur{i}"), (LAUNCH + swap, None)])
    for j, k in enumerate(start_kinds[i]):
        ab.slot_attachment(f"st{i}_{j}", [(0, f"sym_{k}"), (LAUNCH + hide_start, None)])
    for j, k in enumerate(final_kinds[i] + below_kinds[i]):
        ab.slot_attachment(f"sym{i}_{j}", [(0, None), (LAUNCH + swap, f"sym_{k}")])
    ra = [(0.0, 0, 3 * CELL)] + [(LAUNCH + u, 0, float(Xs - np.interp(u, t, X)))
                                 for u in np.arange(swap, stop + 1e-9, 0.01)] + [(ts, 0, 0)]
    ab.bone(f"reel{i}", "translate", sorted({round(a, 4): (a, b, c) for a, b, c in ra}.values()), "linear")

# ------------------------------------------------------------------ the FX (what the MCP's fx_recipe tool does)
F = dict(into="spin", parent="machine", front_of="cabinet")
fx_recipes.apply(p, "turbo_spin", start=0.0, duration=STOPS[-1] - 0.15, **F,
                 options=dict(width=3 * PITCH - GAP, height=RH, bones=[f"st{i}_{j}" for i in range(3) for j in range(3)],
                              kick=0.05, ramp=0.3, glow=0.7, amp=26, gap=44, band=40))
for i, (ts, br) in enumerate(zip(STOPS, BRAKES)):
    fx_recipes.apply(p, "spin_blur", x=(i - 1) * PITCH, start=LAUNCH, seed=11 + i, **F,
                     options=dict(width=RW, height=RH, stop=ts - LAUNCH, brake=br, spinup=SPINUP, speed=SPEED))
    fx_recipes.apply(p, "reel_stop", x=(i - 1) * PITCH, start=ts, seed=7 + i, **F,
                     options=dict(reel=f"reel{i}", shake="machine", width=RW, height=RH))
big = fx_recipes.RECIPES["screen_shake"]["tiers"]["big"]
fx_recipes.apply(p, "screen_shake", start=STOPS[1], **F, options=dict(big, shake="machine"))
# the last reel's scatter brakes toward the payline at constant deceleration and stops one row short
br = BRAKES[2]
dy = CELL + SPEED * CLOSEST ** 2 / (2 * br)
fx_recipes.apply(p, "near_miss", start=STOPS[2] - CLOSEST, into="spin", parent="sym2_0", front_of="cabinet",
                 options=dict(dy=dy, miss=CELL, closest=CLOSEST, fizzle=FIZZLE, follow=False))
v = qa.validate(sk)
assert v["ok"], v["errors"]
b = qa.budget(sk, "desktop")
p.save()
print("validate ok; draw calls", b["metrics"]["draw_calls"], "| bones", len(sk.bones), "| slots", len(sk.slots))

# ------------------------------------------------------------------ render through spine-core, framed on the machine
dump = runtime.run(p, animations=["spin"], fps=25, geometry=True)
assert dump.get("ok", True) and not dump.get("problems"), dump.get("problems")
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
pad = 80
view = (-CW / 2 - pad, -CH / 2 - pad, CW / 2 + pad, CH / 2 + pad)
W = 560
H = int(W * (view[3] - view[1]) / (view[2] - view[0]))
frames = [render.render_frame(f["draws"], pages, view, (W, H), BG) for f in dump["animations"]["spin"]["frames"]]
gif = out / "spin.gif"
pal = [f.convert("RGB").quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
pal[0].save(gif, save_all=True, append_images=pal[1:], duration=40, loop=0, disposal=2)
fps = 25
picks = [0.1, 0.25, 0.95, 1.2, 1.75, 2.1, 2.2, 3.0, 3.3, 3.62, 3.92, 4.2]
sheet = Image.new("RGBA", (W * 4, H * 3))
dr = ImageDraw.Draw(sheet)
for k, tt_ in enumerate(picks):
    j = min(len(frames) - 1, int(round(tt_ * fps)))
    sheet.alpha_composite(frames[j], ((k % 4) * W, (k // 4) * H))
    dr.text(((k % 4) * W + 8, (k // 4) * H + 6), f"{tt_:.2f}s", fill=(255, 255, 255, 255), font=font(18))
sheet.save(out / "spin_sheet.png")
if "--frames" in sys.argv:                            # every frame, for zooming in while tuning
    for j, f in enumerate(frames):
        f.save(out / f"f{j:03d}.png")
shutil.copy(gif, root / "docs" / "spin.gif")
print("frames", len(frames), "| gif", gif, f"{gif.stat().st_size / 1e6:.1f} MB")
