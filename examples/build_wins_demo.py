"""Build the win-presentation demo: a 5 x 3 reel grid lands on two winning lines; payline traces them, win_highlight
lights every winning symbol as the comet passes it, multiplier_stack flies three badges into the total, and
win_rollup counts the win up (tier "big"). Writes to ./out/wins and refreshes docs/wins.gif.

    python examples/build_wins_demo.py

The symbols, badges, total and counter digits are the game's own art (procedural here); the FX pop them only
through carrier bones and the bones the recipes hand back (badge_bones, total_bone, counter_bone).
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_recipes, fx_wins, qa, render, runtime  # noqa: E402,F401
from claude_spine.ir import Bone, RegionAttachment, Sequence, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402
from claude_spine.timeline import AnimBuilder  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "wins"
shutil.rmtree(out, ignore_errors=True)

CELL, PITCH = 128, 140
BG = (20, 14, 30, 255)
COLS, ROWS = 5, 3


def font(px):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def symbol(kind: str) -> Image.Image:
    s = 4
    N = CELL * s
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = N / 2
    d.rounded_rectangle([6 * s, 6 * s, N - 6 * s, N - 6 * s], 18 * s, fill=(48, 30, 70, 255), outline=(90, 60, 120, 255), width=3 * s)
    if kind == "seven":
        d.text((c, c + 4 * s), "7", font=font(100 * s), anchor="mm", fill=(255, 70, 60), stroke_width=6 * s, stroke_fill=(120, 10, 20))
    elif kind == "cherry":
        for dx in (-22, 22):
            d.ellipse([c + dx * s - 24 * s, c + 2 * s, c + dx * s + 24 * s, c + 50 * s], fill=(222, 30, 52), outline=(120, 0, 20), width=3 * s)
        d.line([c - 22 * s, c + 6 * s, c + 2 * s, c - 40 * s, c + 22 * s, c + 6 * s], fill=(40, 170, 40), width=6 * s, joint="curve")
    elif kind == "bell":
        d.chord([c - 38 * s, c - 44 * s, c + 38 * s, c + 44 * s], 180, 360, fill=(255, 210, 60), outline=(150, 90, 0), width=4 * s)
        d.rectangle([c - 38 * s, c - 2 * s, c + 38 * s, c + 20 * s], fill=(255, 210, 60), outline=(150, 90, 0), width=4 * s)
        d.ellipse([c - 9 * s, c + 16 * s, c + 9 * s, c + 34 * s], fill=(150, 90, 0))
    elif kind == "bar":
        d.rounded_rectangle([c - 46 * s, c - 22 * s, c + 46 * s, c + 22 * s], 8 * s, fill=(25, 25, 25), outline=(240, 240, 240), width=5 * s)
        d.text((c, c + 2 * s), "BAR", font=font(34 * s), anchor="mm", fill=(240, 240, 240))
    elif kind == "diamond":
        d.polygon([(c, c - 44 * s), (c + 40 * s, c - 6 * s), (c, c + 46 * s), (c - 40 * s, c - 6 * s)], fill=(60, 170, 255), outline=(10, 50, 140), width=4 * s)
        d.polygon([(c, c - 44 * s), (c + 15 * s, c - 6 * s), (c, c + 46 * s), (c - 15 * s, c - 6 * s)], fill=(150, 220, 255))
    return im.resize((CELL, CELL), Image.LANCZOS)


def label(text: str, w: int, h: int, px: int, fill=(255, 226, 120), stroke=(120, 50, 0), bg=None) -> Image.Image:
    s = 3
    im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if bg:
        d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], h * s // 2, fill=bg, outline=(255, 210, 90), width=3 * s)
    d.text((w * s / 2, h * s / 2 + s), text, font=font(px * s), anchor="mm", fill=fill, stroke_width=4 * s, stroke_fill=stroke)
    return im.resize((w, h), Image.LANCZOS)


def cxy(col, row):
    return (col - 2) * PITCH, (1 - row) * PITCH


# ------------------------------------------------------------------ the grid (the game's art)
grid = [["bell", "cherry", "bar", "diamond", "seven"],
        ["seven", "seven", "seven", "seven", "seven"],
        ["cherry", "bar", "seven", "bell", "diamond"]]
V = [(0, 0), (1, 1), (2, 2), (3, 1), (4, 0)]                 # (col, row): a V line
MID = [(c_, 1) for c_ in range(5)]
for c_, r_ in V:
    grid[r_][c_] = "seven"
sk = new_skeleton("wins", 800, 760)
p = Project(out / "wins.json", sk)
sk.bones.append(Bone(name="board", parent="root"))
p.write_image("panel", Image.new("RGBA", (8, 8), (34, 22, 50, 255)))
sk.add_slot(Slot(name="panel", bone="board", attachment="panel"))
sk.set_attachment("panel", "panel", RegionAttachment(path="panel", width=COLS * PITCH + 20, height=ROWS * PITCH + 20))
kinds = sorted({k for row in grid for k in row})
for k in kinds:
    p.write_image(f"sym_{k}", symbol(k))
for r_ in range(ROWS):
    for c_ in range(COLS):
        x, y = cxy(c_, r_)
        b = f"sym{r_}{c_}"
        sk.bones.append(Bone(name=b, parent="board", x=x, y=y))
        sk.add_slot(Slot(name=b, bone=b, attachment=f"sym_{grid[r_][c_]}"))
        sk.set_attachment(b, f"sym_{grid[r_][c_]}", RegionAttachment(path=f"sym_{grid[r_][c_]}", width=CELL, height=CELL))
last_art = f"sym{ROWS - 1}{COLS - 1}"

# ------------------------------------------------------------------ the FX (what the MCP's fx_recipe tool does)
A = "win"
AnimBuilder(sk, A)
lines = [[list(cxy(c_, r_)) for c_, r_ in V], [list(cxy(c_, r_)) for c_, r_ in MID]]
pl = fx_recipes.apply(p, "payline", into=A, parent="board", front_of=last_art,
                      options=dict(lines=lines, stagger=0.85, colors=["FFD25A", "FF7AD8"]))
seen, cells, syms = set(), [], []
for x, y, t in pl["hits"]:                                    # first pass over each symbol lights it
    key = (round(x), round(y))
    if key in seen:
        continue
    seen.add(key)
    c_, r_ = round(x / PITCH) + 2, 1 - round(y / PITCH)
    cells.append([x, y, CELL + 6, CELL + 6, t])
    syms.append(f"sym{r_}{c_}")
hl = fx_recipes.apply(p, "win_highlight", into=A, parent="board", behind=pl["slots"][0], duration=6.2,
                      options=dict(cells=cells, symbols=syms))
T_MULT, T_ROLL, ROLL_D = 2.55, 3.55, 3.0
TOTAL, COUNTER = (0.0, 292.0), (0.0, -300.0)
srcs = [list(cxy(0, 0)), list(cxy(2, 2)), list(cxy(4, 0))]
ms = fx_recipes.apply(p, "multiplier_stack", start=T_MULT, into=A, parent="board", front_of=pl["slots"][-1],
                      options=dict(sources=srcs, target=list(TOTAL)))
tiers = fx_recipes.RECIPES["win_rollup"]["tiers"]
ro = fx_recipes.apply(p, "win_rollup", x=COUNTER[0], y=COUNTER[1], start=T_ROLL, duration=ROLL_D, into=A, parent="board",
                      front_of=ms["slots"][-1], options=dict(tiers["big"], width=330, height=96))

# the game's badges, total and counter, parented under the bones the recipes hand back
ab = AnimBuilder(sk, A, replace=False)
prev = ro["slots"][-1]
for i, (bb, txt) in enumerate(zip(ms["badge_bones"], ["x2", "x3", "x5"])):
    p.write_image(f"badge{i}", label(txt, 96, 60, 40, bg=(120, 20, 60, 255)))
    sk.add_slot(Slot(name=f"badge{i}", bone=bb), after=prev)
    prev = f"badge{i}"
    sk.set_attachment(prev, f"badge{i}", RegionAttachment(path=f"badge{i}", width=96, height=60))
    ab.slot_attachment(prev, [(0, None), (T_MULT - 0.3, f"badge{i}")])
p.write_image("total", label("x30", 170, 90, 64))
sk.add_slot(Slot(name="total", bone=ms["total_bone"]), after=prev)
sk.set_attachment("total", "total", RegionAttachment(path="total", width=170, height=90))
ab.slot_attachment("total", [(0, None), (ms["hits"][0], "total")])
FINAL = 12450
nt = ro["ticks"]
vals = [round(FINAL * (k / nt) ** 1.4) for k in range(nt)] + [FINAL]
for k, v in enumerate(vals):
    p.write_image(f"num/n{k:02d}", label(f"{v:,}", 320, 90, 66, fill=(255, 240, 190), stroke=(140, 60, 0)))
sk.bones.append(Bone(name="counter", parent=ro["counter_bone"]))
sk.add_slot(Slot(name="counter", bone="counter"), after="total")
sk.set_attachment("counter", "num", RegionAttachment(path="num/n", width=320, height=90, sequence=Sequence(count=len(vals), start=0, digits=2)))
ab.slot_attachment("counter", [(0, None), (T_ROLL, "num")])
ab.sequence("counter", "num", [(t, "hold", k, 0) for k, t in enumerate(ro["tick_times"])] + [(ro["end_at"], "hold", nt, 0)])
END = T_ROLL + ROLL_D + 0.25
ab.event(END, "demo_end")

v = qa.validate(sk)
assert v["ok"], v["errors"]
b = qa.budget(sk, "desktop")
p.save()
print("validate ok; draw calls", b["metrics"]["draw_calls"], "| bones", len(sk.bones), "| slots", len(sk.slots))

# ------------------------------------------------------------------ render through spine-core
dump = runtime.run(p, animations=[A], fps=15, geometry=True)
assert dump.get("ok", True) and not dump.get("problems"), dump.get("problems")
ev = dump["animations"][A].get("events") or dump.get("events") or []
print("events fired:", len(ev))
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
view = (-420, -470, 420, 355)
W = 560
H = int(W * (view[3] - view[1]) / (view[2] - view[0]))
frames = [render.render_frame(f["draws"], pages, view, (W, H), BG) for f in dump["animations"][A]["frames"]]
gif = out / "wins.gif"
pal = [f.convert("RGB").quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
pal[0].save(gif, save_all=True, append_images=pal[1:], duration=67, loop=0, disposal=2)
pick = [0.25, 0.5, 0.8, 1.25, 1.6, 2.2, 2.75, 3.1, 3.5, 4.2, 5.2, 5.9, 6.4, 6.75]
sheet_idx = [min(len(frames) - 1, int(round(t * 15))) for t in pick]
cols = 4
rows = (len(sheet_idx) + cols - 1) // cols
sheet = Image.new("RGBA", (W * cols, H * rows), BG)
for k, j in enumerate(sheet_idx):
    fr = frames[j].copy()
    ImageDraw.Draw(fr).text((8, 6), f"{j / 15:.2f}s", fill=(255, 255, 255, 255))
    sheet.alpha_composite(fr, ((k % cols) * W, (k // cols) * H))
sheet.save(out / "wins_sheet.png")
for t in (0.5, 3.4, 5.75):
    frames[int(round(t * 15))].save(out / f"frame_{t:.2f}.png")
shutil.copy(gif, root / "docs" / "wins.gif")
print("frames", len(frames), "| gif", gif, f"{gif.stat().st_size / 1e6:.1f} MB")
