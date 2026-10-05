"""Build the payouts demo: a 3x3 cascade grid in a cabinet with a coin tray under it.

    python examples/build_payouts_demo.py

Three clips, rendered through spine-core one after another into out/payouts/payouts.gif (copied to docs/payouts.gif):

* ``cascade``: the middle row of red gems wins; cascade_pop shatters the three (shards cut from the gem picture, a
  dust puff and a hit burst each), then the top row and three new symbols from above the window drop one cell
  through carrier bones and land with the restitution hop + squash spring. The game's own keys only hide its gems
  at the start (fx_cascade_pop) and swap nothing else.
* ``fountain``: coin_fountain gushes from the tray: drag parabolas, hang time at the top, tumbling flipbook coins,
  bounces on the tray, a slide, Euler's-disk rattle, shadows.
* ``shower``: the same coins raining in from above the screen.
"""
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_payouts, fx_recipes, qa, render, runtime  # noqa: E402,F401
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402
from claude_spine.timeline import AnimBuilder  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "payouts"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True, exist_ok=True)

CELL, PITCH = 128, 136
GY = 70                                          # grid centre
TRAY = -250                                      # tray (counter) top
BG = (24, 16, 34, 255)


def font(px):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def symbol(kind: str) -> Image.Image:
    s = 4
    n = CELL * s
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = n / 2
    if kind == "gem":
        return fx_payouts.tex_symbol("E8364F", CELL * 2).resize((CELL, CELL), Image.LANCZOS)
    if kind == "seven":
        d.text((c, c + 4 * s), "7", font=font(104 * s), anchor="mm", fill=(255, 196, 40), stroke_width=6 * s, stroke_fill=(150, 40, 10))
    elif kind == "bell":
        d.chord([c - 42 * s, c - 46 * s, c + 42 * s, c + 46 * s], 180, 360, fill=(255, 210, 60), outline=(150, 90, 0), width=4 * s)
        d.rectangle([c - 42 * s, c - 2 * s, c + 42 * s, c + 20 * s], fill=(255, 210, 60), outline=(150, 90, 0), width=4 * s)
        d.ellipse([c - 10 * s, c + 16 * s, c + 10 * s, c + 36 * s], fill=(150, 90, 0))
    elif kind == "clover":
        for ax, ay in ((0, -24), (-24, 0), (24, 0), (0, 24)):
            d.ellipse([c + (ax - 22) * s, c + (ay - 22) * s, c + (ax + 22) * s, c + (ay + 22) * s], fill=(60, 190, 90), outline=(10, 90, 40), width=3 * s)
        d.line([c, c + 20 * s, c + 14 * s, c + 52 * s], fill=(10, 90, 40), width=6 * s)
    elif kind == "bar":
        d.rounded_rectangle([c - 54 * s, c - 24 * s, c + 54 * s, c + 24 * s], 10 * s, fill=(30, 30, 30), outline=(250, 250, 250), width=5 * s)
        d.text((c, c + 2 * s), "BAR", font=font(38 * s), anchor="mm", fill=(250, 250, 250))
    elif kind == "diamond":
        d.polygon([(c, c - 50 * s), (c + 44 * s, c - 8 * s), (c, c + 52 * s), (c - 44 * s, c - 8 * s)], fill=(60, 170, 255), outline=(10, 50, 140), width=4 * s)
        d.polygon([(c, c - 50 * s), (c + 17 * s, c - 8 * s), (c, c + 52 * s), (c - 17 * s, c - 8 * s)], fill=(150, 220, 255))
    return im.resize((CELL, CELL), Image.LANCZOS)


def cabinet(w: int, h: int, margin: int, window: tuple) -> Image.Image:
    """Opaque front (cabinet + background margin) with one window for the grid, a coin tray along the bottom."""
    s = 2
    W_, H_ = (w + 2 * margin) * s, (h + 2 * margin) * s
    im = Image.new("RGBA", (W_, H_), BG)
    d = ImageDraw.Draw(im)
    m = margin * s
    d.rounded_rectangle([m, m, m + w * s - 1, m + h * s - 1], 36 * s, fill=(70, 20, 70), outline=(255, 196, 64), width=8 * s)
    cx, cy = W_ / 2, H_ / 2
    wx0, wy0, wx1, wy1 = window                       # design units, y up, relative to the cabinet centre
    X = lambda v: cx + v * s  # noqa: E731
    Y = lambda v: cy - v * s  # noqa: E731
    d.rounded_rectangle([X(wx0) - 8 * s, Y(wy1) - 8 * s, X(wx1) + 8 * s, Y(wy0) + 8 * s], 16 * s, fill=(255, 196, 64))
    d.rounded_rectangle([X(wx0), Y(wy1), X(wx1), Y(wy0)], 10 * s, fill=(0, 0, 0, 0))
    return im.resize((w + 2 * margin, h + 2 * margin), Image.LANCZOS)


# ------------------------------------------------------------------ the machine
sk = new_skeleton("payouts", 720, 720)
p = Project(out / "payouts.json", sk)
sk.bones.append(Bone(name="machine", parent="root"))
sk.bones.append(Bone(name="grid", parent="machine", y=GY))
p.write_image("cell_bg", Image.new("RGBA", (8, 8), (250, 242, 228, 255)))
win = (-1.5 * PITCH, GY - 1.5 * PITCH, 1.5 * PITCH, GY + 1.5 * PITCH)
sk.add_slot(Slot(name="cell_bg", bone="grid", attachment="cell_bg"))
sk.set_attachment("cell_bg", "cell_bg", RegionAttachment(path="cell_bg", width=3 * PITCH, height=3 * PITCH))
kinds = {}
rows = [["bell", "seven", "clover"], ["gem", "gem", "gem"], ["bar", "diamond", "seven"], ["clover", "bell", "diamond"]]
# row 0 = top, 1 = middle (wins), 2 = bottom, 3 = the new symbols waiting above the window
for r_, row in enumerate(rows):
    for c_, k in enumerate(row):
        if k not in kinds:
            p.write_image(f"sym_{k}", symbol(k))
            kinds[k] = True
        y = {0: PITCH, 1: 0, 2: -PITCH, 3: 2 * PITCH}[r_]
        bn = f"sym_{r_}_{c_}"
        sk.bones.append(Bone(name=bn, parent="grid", x=(c_ - 1) * PITCH, y=y))
        sk.add_slot(Slot(name=bn, bone=bn, attachment=f"sym_{k}"))
        sk.set_attachment(bn, f"sym_{k}", RegionAttachment(path=f"sym_{k}", width=CELL, height=CELL))
CW, CH, MARGIN = 3 * PITCH + 80, 720 - 40, 380
p.write_image("cabinet", cabinet(CW, CH, MARGIN, win))
sk.add_slot(Slot(name="cabinet", bone="machine", attachment="cabinet"))
sk.set_attachment("cabinet", "cabinet", RegionAttachment(path="cabinet", width=CW + 2 * MARGIN, height=CH + 2 * MARGIN))
# the tray: a bar the coins land on (its top edge is TRAY), drawn over the cabinet, under the FX
tray = Image.new("RGBA", (640, 80), (0, 0, 0, 0))
dt = ImageDraw.Draw(tray)
dt.rounded_rectangle([0, 0, 639, 79], 18, fill=(120, 60, 30), outline=(255, 196, 64), width=5)
dt.rectangle([10, 8, 629, 22], fill=(170, 95, 45))
p.write_image("tray", tray)
sk.bones.append(Bone(name="tray", parent="machine", y=TRAY - 40))
sk.add_slot(Slot(name="tray", bone="tray", attachment="tray"))
sk.set_attachment("tray", "tray", RegionAttachment(path="tray", width=640, height=80))
gem_png = out / "gem.png"
symbol("gem").save(gem_png)


# ------------------------------------------------------------------ cascade: the game hides its gems, the FX does the rest
T0 = 0.25
ab = AnimBuilder(sk, "cascade")
for c_ in range(3):
    ab.slot_attachment(f"sym_1_{c_}", [(0, "sym_gem"), (T0, None)])
cells = [[(c_ - 1) * PITCH, 0, CELL, CELL] for c_ in range(3)]
drops = [[f"sym_0_{c_}", PITCH, CELL] for c_ in range(3)] + [[f"sym_3_{c_}", PITCH, CELL] for c_ in range(3)]
res_c = fx_recipes.apply(p, "cascade_pop", x=0, y=GY, start=T0, into="cascade", parent="machine", front_of="tray",
                         art={"symbol": str(gem_png)}, options=dict(cells=cells, drop=drops, stagger=0.06))
AnimBuilder(sk, "cascade", replace=False).event(res_c["end"] + 0.25, "demo_end")


# ------------------------------------------------------------------ fountain and shower onto the tray
SPOUT = TRAY + 50
res_f = fx_recipes.apply(p, "coin_fountain", x=0, y=SPOUT, into="fountain", parent="machine", front_of=res_c["slots"][-1],
                         options=dict(floor=TRAY - SPOUT - 14, width=520, height=440, depth=16))
res_s = fx_recipes.apply(p, "coin_fountain", x=0, y=SPOUT, into="shower", parent="machine", front_of=res_f["slots"][-1],
                         seed=11, options=dict(mode="shower", floor=TRAY - SPOUT - 14, width=520, height=600, depth=16))
v = qa.validate(sk)
assert v["ok"], v["errors"]
p.save()
print("validate ok | bones", len(sk.bones), "| slots", len(sk.slots))
print("cascade breaks", res_c["breaks"], "lands", res_c["lands"])
print("fountain landings", res_f["landings"], "spread", res_f["spread"])


# ------------------------------------------------------------------ render through spine-core
FPS = 20
anims = ["cascade", "fountain", "shower"]
dump = runtime.run(p, animations=anims, fps=FPS, geometry=True)
assert dump.get("ok", True) and not dump.get("problems"), dump.get("problems")
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
view = (-300, -340, 300, 400)
W = 560
H = int(W * (view[3] - view[1]) / (view[2] - view[0]))
frames, per = [], {}
for a in anims:
    fr = [render.render_frame(f["draws"], pages, view, (W, H), BG) for f in dump["animations"][a]["frames"]]
    per[a] = fr
    frames += fr + [fr[-1]] * 6
gif = out / "payouts.gif"
pal = [f.convert("RGB").quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
pal[0].save(gif, save_all=True, append_images=pal[1:], duration=int(1000 / FPS), loop=0, disposal=2)
cols = 5
sheet = Image.new("RGBA", (W * cols, H * len(anims)))
for r_, a in enumerate(anims):
    fr = per[a]
    pick = {"cascade": [0.05, 0.3, 0.42, 0.62, 0.95], "fountain": [0.12, 0.3, 0.45, 0.62, 0.85],
            "shower": [0.12, 0.25, 0.4, 0.55, 0.85]}[a]
    for k, f in enumerate(pick):
        sheet.alpha_composite(fr[min(len(fr) - 1, int(f * len(fr)))], (k * W, r_ * H))
sheet.save(out / "payouts_sheet.png")
for a in anims:
    for k, f in enumerate(per[a]):
        if k % 2 == 0:
            f.save(out / f"{a}_{k:03d}.png")
shutil.copy(gif, root / "docs" / "payouts.gif")
print("frames", len(frames), "| gif", gif, f"{gif.stat().st_size / 1e6:.1f} MB")
