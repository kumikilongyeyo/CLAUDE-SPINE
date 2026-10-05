"""Build the feature-trigger demo: four scenes on a procedural 3x3 machine, one per recipe of fx_features.py.
Writes to ./out/features (a contact sheet per scene, an overall sheet and a GIF) and refreshes docs/features.gif.

    python examples/build_features_demo.py

1. wild_land: a WILD falls onto the right reel through a carrier on its bone, bounces, squashes; the sticky frame
   holds (the clip, then its _hold loop twice).
2. expanding_wild: the middle reel floods with gold from its wild cell; the wild symbol then rides to the centre.
3. scatter_trigger: three scatters land, lock on and beam into the BONUS sign, which bursts.
4. free_spins_transition: the whole machine (screen=machine) is pulled into a portal, swapped while it is gone
   (game keys at fx_free_spins_in) and springs back out of the puff as the free-spins skin.
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_features, fx_recipes, qa, render, runtime  # noqa: E402,F401
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402
from claude_spine.timeline import AnimBuilder  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "features"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)

RW, RH, CELL, GAP = 150, 450, 150, 12
PITCH = RW + GAP
BG = (20, 16, 34, 255)
FPS = 20
VIEW = (-340, -300, 340, 400)
W = 560
H = int(W * (VIEW[3] - VIEW[1]) / (VIEW[2] - VIEW[0]))


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
    elif kind == "wild":
        d.rounded_rectangle([6 * s, 6 * s, N - 6 * s, N - 6 * s], 18 * s, fill=(110, 30, 150), outline=(255, 210, 70), width=6 * s)
        d.text((c, c + 2 * s), "WILD", font=font(42 * s), anchor="mm", fill=(255, 220, 80), stroke_width=4 * s, stroke_fill=(90, 20, 0))
    elif kind == "scatter":
        pts = []
        for k in range(10):
            a = -np.pi / 2 + k * np.pi / 5
            rr = (62 if k % 2 == 0 else 28) * s
            pts.append((c + rr * np.cos(a), c - 6 * s + rr * np.sin(a)))
        d.polygon(pts, fill=(255, 80, 190), outline=(120, 0, 70), width=4 * s)
        d.text((c, c + 54 * s), "SCATTER", font=font(19 * s), anchor="mm", fill=(255, 255, 255), stroke_width=3 * s, stroke_fill=(120, 0, 70))
    return im.resize((CELL, CELL), Image.LANCZOS)


def cabinet(w: int, h: int, frame=(92, 18, 36), trim=(255, 196, 64)) -> Image.Image:
    """The machine front: opaque frame, three transparent reel windows, nothing outside the frame."""
    s = 2
    im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], 40 * s, fill=frame + (255,), outline=trim, width=10 * s)
    d.rounded_rectangle([14 * s, 14 * s, w * s - 15 * s, h * s - 15 * s], 30 * s, outline=(170, 110, 30), width=4 * s)
    cx, cy = w * s / 2, h * s / 2
    for i in range(3):
        x0 = cx + ((i - 1) * PITCH - RW / 2) * s
        y0 = cy - RH / 2 * s
        d.rounded_rectangle([x0 - 6 * s, y0 - 6 * s, x0 + (RW + 6) * s, y0 + (RH + 6) * s], 14 * s, fill=trim)
        d.rounded_rectangle([x0, y0, x0 + RW * s, y0 + RH * s], 10 * s, fill=(0, 0, 0, 0))
    return im.resize((w, h), Image.LANCZOS)


def sign(text: str, fill=(40, 10, 70), trim=(255, 196, 64)) -> Image.Image:
    s = 3
    w, h = 300, 76
    im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], 30 * s, fill=fill + (255,), outline=trim, width=6 * s)
    d.text((w * s / 2, h * s / 2 + 2 * s), text, font=font(38 * s), anchor="mm", fill=(255, 230, 120), stroke_width=3 * s, stroke_fill=(90, 30, 0))
    return im.resize((w, h), Image.LANCZOS)


def backdrop() -> Image.Image:
    rng = np.random.default_rng(3)
    w, h = 720, 760
    y = np.linspace(0, 1, h)[:, None]
    rgb = np.dstack([18 + 30 * y + 0 * np.zeros((h, w)), 14 + 10 * y + 0 * np.zeros((h, w)), 40 + 40 * y + 0 * np.zeros((h, w))])
    im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    d = ImageDraw.Draw(im)
    for _ in range(90):
        x, yy, r_ = rng.uniform(0, w), rng.uniform(0, h), rng.uniform(0.8, 2.2)
        a = int(rng.uniform(90, 230))
        d.ellipse([x - r_, yy - r_, x + r_, yy + r_], fill=(255, 245, 220, a))
    return im.filter(ImageFilter.GaussianBlur(0.4))


CW, CH = 3 * PITCH + 60, RH + 90
GRID = [["cherry", "seven", "bell"], ["bar", "seven", "diamond"], ["diamond", "bell", "cherry"]]


def machine(name: str, grid=GRID):
    """A project with a backdrop (root), and under bone `machine`: reel backgrounds, symbol cells, the cabinet."""
    sk = new_skeleton(name, 720, 720)
    p = Project(out / name / f"{name}.json", sk)
    p.write_image("backdrop", backdrop())
    sk.add_slot(Slot(name="backdrop", bone="root", attachment="backdrop"))
    sk.set_attachment("backdrop", "backdrop", RegionAttachment(path="backdrop", y=50, width=720, height=760))
    sk.bones.append(Bone(name="machine", parent="root"))
    p.write_image("reel_bg", Image.new("RGBA", (8, 8), (36, 26, 60, 255)))    # dark reels: additive light reads
    kinds = sorted({k for col in grid for k in col} | {"wild", "scatter"})
    for k in kinds:
        p.write_image(f"sym_{k}", symbol(k))
    for r_, col in enumerate(grid):
        sk.bones.append(Bone(name=f"reel{r_}", parent="machine", x=(r_ - 1) * PITCH))
        sk.add_slot(Slot(name=f"bg{r_}", bone=f"reel{r_}", attachment="reel_bg"))
        sk.set_attachment(f"bg{r_}", "reel_bg", RegionAttachment(path="reel_bg", width=RW, height=RH))
        for i, k in enumerate(col):
            bn = f"cell{r_}{i}"
            sk.bones.append(Bone(name=bn, parent=f"reel{r_}", y=(1 - i) * CELL))
            sk.add_slot(Slot(name=bn, bone=bn, attachment=f"sym_{k}"))
            sk.set_attachment(bn, f"sym_{k}", RegionAttachment(path=f"sym_{k}", width=CELL, height=CELL))
    p.write_image("cabinet", cabinet(CW, CH))
    sk.add_slot(Slot(name="cabinet", bone="machine", attachment="cabinet"))
    sk.set_attachment("cabinet", "cabinet", RegionAttachment(path="cabinet", width=CW, height=CH))
    return p


def finish(p: Project, anims: list[str], label: str):
    v = qa.validate(p.data)
    assert v["ok"], v["errors"]
    p.save()
    dump = runtime.run(p, animations=anims, fps=FPS, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems"), dump.get("problems")
    pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
    frames = []
    for a in anims:
        for f in dump["animations"][a]["frames"]:
            im = render.render_frame(f["draws"], pages, VIEW, (W, H), BG)
            ImageDraw.Draw(im).text((16, H - 14), label, font=font(17), anchor="ls", fill=(235, 225, 255, 255))
            frames.append(im)
    fd = out / label
    fd.mkdir(parents=True, exist_ok=True)
    for j, im in enumerate(frames):
        im.convert("RGB").save(fd / f"f{j:03d}.png")
    idx = np.linspace(0, len(frames) - 1, 8).round().astype(int)
    sheet = Image.new("RGBA", (W * 4, H * 2))
    for k, j in enumerate(idx):
        sheet.alpha_composite(frames[j], ((k % 4) * W, (k // 4) * H))
    sheet.save(out / f"{label}_sheet.png")
    print(f"{label}: frames {len(frames)} | draw calls {qa.budget(p.data, 'desktop')['metrics']['draw_calls']} | slots {len(p.data.slots)}")
    return frames


ONLY = sys.argv[1:]                                # e.g. `wild_land` to rebuild one scene (no GIF)
all_frames = []


def scene_wild_land():
    """1. wild_land"""
    p = machine("wild")
    sk = p.data
    sk.bones.append(Bone(name="wild", parent="machine", x=PITCH, y=0))
    sk.add_slot(Slot(name="wild", bone="wild"))
    sk.set_attachment("wild", "sym_wild", RegionAttachment(path="sym_wild", width=CELL, height=CELL))
    AnimBuilder(sk, "wild").slot_attachment("wild", [(0, "sym_wild")])
    res = fx_recipes.apply(p, "wild_land", x=PITCH, y=0, parent="machine", into="wild", behind="wild", options=dict(wild="wild"))
    AnimBuilder(sk, res["hold_anim"], replace=False).slot_attachment("wild", [(0, "sym_wild")])
    return finish(p, ["wild", res["hold_anim"], res["hold_anim"]], "wild_land")


def scene_expanding_wild():
    """2. expanding_wild"""
    grid = [GRID[0], ["wild", "seven", "diamond"], GRID[2]]
    p = machine("expand", grid)
    sk = p.data
    res = fx_recipes.apply(p, "expanding_wild", x=0, y=0, parent="machine", into="expand", front_of="cabinet", duration=3.0,
                           options=dict(fade=0.0))
    sk.slots.remove(sk.slot("cell10"))                 # the wild cell rides in front of the liquid
    sk.add_slot(Slot(name="cell10", bone="cell10", attachment="sym_wild"))
    ab = AnimBuilder(sk, "expand", replace=False)
    t_full = res["full_at"]
    ab.bone("cell10", "translate", [(0, 0, 0), (t_full + 0.15, 0, 0), (t_full + 0.75, 0, -CELL)], "cubic_in_out")
    ab.bone("cell10", "scale", [(0, 1, 1), (t_full + 0.15, 1, 1), (t_full + 0.75, 1.25, 1.25)], "back_out")
    return finish(p, ["expand"], "expanding_wild")


def scene_scatter_trigger():
    """3. scatter_trigger"""
    p = machine("scatter")
    sk = p.data
    p.write_image("sign_bonus", sign("BONUS"))
    sk.bones.append(Bone(name="sign", parent="machine", y=318))
    sk.add_slot(Slot(name="sign", bone="sign", attachment="sign_bonus"))
    sk.set_attachment("sign", "sign_bonus", RegionAttachment(path="sign_bonus", width=300, height=76))
    spots = [(0, 0, 0.0), (1, 2, 0.35), (2, 1, 0.7)]          # (reel, row, land time)
    res = fx_recipes.apply(p, "scatter_trigger", parent="machine", into="scatter", front_of="sign",
                           options=dict(scatters=[[(r_ - 1) * PITCH, (1 - i) * CELL, t] for r_, i, t in spots], centre=[0, 318]))
    ab = AnimBuilder(sk, "scatter", replace=False)
    for r_, i, t in spots:
        nm = f"sc{r_}"
        sk.bones.append(Bone(name=nm, parent="machine", x=(r_ - 1) * PITCH, y=(1 - i) * CELL))
        sk.add_slot(Slot(name=nm, bone=nm))
        sk.set_attachment(nm, "sym_scatter", RegionAttachment(path="sym_scatter", width=CELL, height=CELL))
        ab.slot_attachment(nm, [(0, None), (max(0.0, t - 0.12), "sym_scatter")] if t > 0 else [(0, "sym_scatter")])
        ab.bone(nm, "translate", [(0, 0, 60), (max(0.0, t - 0.12), 0, 60), (t, 0, 0)], "quad_in")
        ab.bone(nm, "scale", [(t, 1, 1), (t + 0.06, 1.12, 0.88), (t + 0.2, 1, 1)], "quad_out")
        ab.slot_attachment(f"cell{r_}{i}", [(0, f"sym_{GRID[r_][i]}"), (max(0.0, t - 0.12), None)] if t > 0 else [(0, None)])
    T = res["trigger_at"]
    ab.bone("sign", "scale", [(0, 1, 1), (T, 1, 1), (T + 0.08, 1.25, 1.25), (T + 0.5, 1, 1)], "quad_out")
    return finish(p, ["scatter"], "scatter_trigger")


def scene_free_spins_transition():
    """4. free_spins_transition"""
    p = machine("freespins")
    sk = p.data
    p.write_image("reel_bg_fs", Image.new("RGBA", (8, 8), (14, 48, 72, 255)))
    p.write_image("cabinet_fs", cabinet(CW, CH, frame=(30, 40, 120), trim=(140, 220, 255)))
    p.write_image("sign_fs", sign("FREE SPINS", fill=(20, 30, 90), trim=(140, 220, 255)))
    sk.set_attachment("cabinet", "cabinet_fs", RegionAttachment(path="cabinet_fs", width=CW, height=CH))
    sk.bones.append(Bone(name="sign", parent="machine", y=318))
    sk.add_slot(Slot(name="sign", bone="sign"))
    sk.set_attachment("sign", "sign_fs", RegionAttachment(path="sign_fs", width=300, height=76))
    res = fx_recipes.apply(p, "free_spins_transition", x=0, y=0, into="fs", options=dict(screen="machine"))
    t_in = res["in_at"]
    ab = AnimBuilder(sk, "fs", replace=False)          # the game's swap, keyed on fx_free_spins_in (the screen is at scale 0)
    for r_ in range(3):
        sk.set_attachment(f"bg{r_}", "reel_bg_fs", RegionAttachment(path="reel_bg_fs", width=RW, height=RH))
        ab.slot_attachment(f"bg{r_}", [(0, "reel_bg"), (t_in, "reel_bg_fs")])
        for i in range(3):
            k = ["seven", "diamond", "seven"][i]
            sk.set_attachment(f"cell{r_}{i}", f"sym_{k}", RegionAttachment(path=f"sym_{k}", width=CELL, height=CELL))
            ab.slot_attachment(f"cell{r_}{i}", [(0, f"sym_{GRID[r_][i]}"), (t_in, f"sym_{k}")])
    ab.slot_attachment("cabinet", [(0, "cabinet"), (t_in, "cabinet_fs")])
    ab.slot_attachment("sign", [(0, None), (t_in, "sign_fs")])
    return finish(p, ["fs"], "free_spins_transition")


for nm in ["wild_land", "expanding_wild", "scatter_trigger", "free_spins_transition"]:
    if not ONLY or nm in ONLY:
        all_frames += globals()[f"scene_{nm}"]()
if ONLY:
    sys.exit(0)

# ------------------------------------------------------------------ GIF + overall sheet
gif = out / "features.gif"
# one shared palette (from a strip of frames across all scenes), so static pixels keep their index and every GIF frame
# stores only what changed
pick = all_frames[:: max(1, len(all_frames) // 24)]
strip = Image.new("RGB", (W, H * len(pick)))
for k, f in enumerate(pick):
    strip.paste(f.convert("RGB"), (0, k * H))
ref = strip.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
pal = [f.convert("RGB").quantize(palette=ref, dither=Image.Dither.NONE) for f in all_frames]
pal[0].save(gif, save_all=True, append_images=pal[1:], duration=int(1000 / FPS), loop=0, disposal=1, optimize=False)
shutil.copy(gif, root / "docs" / "features.gif")
print("frames", len(all_frames), "| gif", gif, f"{gif.stat().st_size / 1e6:.1f} MB")
