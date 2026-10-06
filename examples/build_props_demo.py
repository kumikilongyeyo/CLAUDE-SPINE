"""Build the prop-recipe demo: a procedural potion symbol rigged the way an artist would (a bottle bone, a liquid bone
on the surface line, plain layers), then given life by two recipes: prop_idle (grow + clockwise tilt + counter-tilt
overshoot + pulsing glow) and liquid_slosh (world-space surface swing + clipping mask). Writes ./out/props and
refreshes docs/potion.gif.

    python examples/build_props_demo.py
"""
import math
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_recipes as R, qa, render, runtime  # noqa: E402
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "props"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
PX = 512
R_IN = 118.0


# ---------------------------------------------------------------- stand-in art (all 512 x 512, bottle centre = canvas centre)
def canvas():
    return Image.new("RGBA", (PX * 2, PX * 2), (0, 0, 0, 0))


def done(im, blur=0):
    im = im.resize((PX, PX), Image.LANCZOS)
    return im.filter(ImageFilter.GaussianBlur(blur)) if blur else im


C = PX  # centre in the 2x canvas


def art_glow():
    a = np.zeros((PX, PX), np.float32)
    y, x = np.mgrid[0:PX, 0:PX]
    r = np.hypot(x - PX / 2, y - PX / 2)
    a = np.exp(-((r - 132) / 26) ** 2) * 0.9 + np.exp(-((r - 120) / 60) ** 2) * 0.35
    a *= np.clip((PX / 2 - r) / 20, 0, 1)
    rgb = np.ones((PX, PX, 3), np.float32)
    return Image.fromarray((np.dstack([rgb, np.clip(a, 0, 1)]) * 255).astype(np.uint8), "RGBA")


def art_bottle_back():
    im = canvas(); d = ImageDraw.Draw(im)
    d.ellipse((C - 250, C - 250, C + 250, C + 250), fill=(70, 30, 110, 210))
    return done(im)


def art_liquid():
    """Liquid body much bigger than the bottle (the clip trims it): pink-magenta, darker at the bottom, its TOP edge at
    the canvas centre line, so the liquid bone sits on the surface."""
    im = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    a = np.zeros((PX, PX, 4), np.float32)
    y, x = np.mgrid[0:PX, 0:PX]
    below = y >= PX / 2 + 6 * np.sin(x / PX * 2 * math.pi * 1.5)          # gentle wave on the surface
    depth = np.clip((y - PX / 2) / (PX / 2), 0, 1)
    a[..., 0] = 0.95 - 0.25 * depth
    a[..., 1] = 0.35 - 0.2 * depth
    a[..., 2] = 0.78 - 0.15 * depth
    a[..., 3] = below * 0.96
    rng = np.random.default_rng(3)                                          # little bubbles / speckles
    for _ in range(40):
        bx, by = rng.uniform(40, PX - 40), rng.uniform(PX * 0.6, PX - 30)
        rr = np.hypot(x - bx, y - by) < rng.uniform(2, 5)
        a[rr, :3] = (0.75, 0.25, 0.6)
    return Image.fromarray((np.clip(a, 0, 1) * 255).astype(np.uint8), "RGBA")


def art_surface():
    """The lit foam line along the liquid surface (light pink, soft)."""
    im = Image.new("RGBA", (PX, 48), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    pts = [(x, 24 + 6 * math.sin(x / PX * 2 * math.pi * 1.5)) for x in range(0, PX + 4, 4)]
    d.line(pts, fill=(255, 210, 230, 255), width=14)
    return im.filter(ImageFilter.GaussianBlur(2))


def art_inner_flask():
    im = canvas(); d = ImageDraw.Draw(im)
    d.ellipse((C - 150, C - 120, C + 60, C + 80), fill=(110, 70, 220, 230), outline=(180, 160, 255, 255), width=10)
    d.rounded_rectangle((C - 90, C - 300, C - 10, C - 100), 30, fill=(120, 110, 220, 200), outline=(180, 160, 255, 255), width=8)
    d.ellipse((C - 80, C - 30, C - 20, C + 30), fill=(180, 170, 255, 200))
    return done(im)


def art_bottle_front():
    im = canvas(); d = ImageDraw.Draw(im)
    d.ellipse((C - 256, C - 256, C + 256, C + 256), outline=(255, 120, 240, 255), width=26)
    d.ellipse((C - 236, C - 236, C + 236, C + 236), outline=(90, 200, 220, 160), width=8)
    return done(im)


def art_shine():
    im = canvas(); d = ImageDraw.Draw(im)
    d.arc((C - 210, C - 210, C + 210, C + 210), 200, 250, fill=(255, 255, 255, 230), width=26)
    d.ellipse((C - 170, C - 40, C - 120, C + 10), fill=(255, 255, 255, 220))
    return done(im, 1.5)


def art_handle():
    im = canvas(); d = ImageDraw.Draw(im)
    d.arc((C - 300, C - 560, C + 300, C - 100), 190, 350, fill=(90, 160, 210, 255), width=46)
    d.arc((C - 300, C - 560, C + 300, C - 100), 190, 350, fill=(150, 210, 240, 255), width=14)
    d.arc((C - 120, C - 520, C + 60, C - 340), 30, 300, fill=(90, 160, 210, 255), width=36)
    return done(im)


def art_cork(left):
    im = canvas(); d = ImageDraw.Draw(im)
    cx = C - 150 if left else C + 190
    cy = C - 300 if left else C - 230
    d.rounded_rectangle((cx - 70, cy - 60, cx + 70, cy + 60), 26, fill=(230, 150, 220, 255), outline=(90, 110, 200, 255), width=12)
    return done(im).rotate(-25 if left else 30, center=(cx / 2, cy / 2), resample=Image.BICUBIC)


def art_gem():
    im = canvas(); d = ImageDraw.Draw(im)
    cx, cy = C - 110, C - 380
    pts = [(cx + math.cos(a) * (46 if i % 2 == 0 else 22), cy + math.sin(a) * (46 if i % 2 == 0 else 22))
           for i, a in enumerate(np.linspace(-math.pi / 2, 1.5 * math.pi, 11)[:-1])]
    d.polygon(pts, fill=(220, 70, 50, 255), outline=(120, 30, 20, 255))
    return done(im)


LAYERS = [  # name, maker, blend
    ("glow", art_glow, "additive"), ("bottle_back", art_bottle_back, "normal"), ("liquid", art_liquid, "normal"),
    ("surface", art_surface, "normal"), ("inner_flask", art_inner_flask, "normal"),
    ("bottle_front", art_bottle_front, "normal"), ("handle", art_handle, "normal"),
    ("cork_l", lambda: art_cork(True), "normal"), ("cork_r", lambda: art_cork(False), "normal"), ("gem", art_gem, "normal"),
    ("shine", art_shine, "additive"),          # on top: additive layers at the two ends = 3 draw calls
]


LAYERS = [("bottle_back", art_bottle_back), ("liquid", art_liquid), ("surface", art_surface), ("inner_flask", art_inner_flask),
          ("bottle_front", art_bottle_front), ("handle", art_handle), ("cork_l", lambda: art_cork(True)),
          ("cork_r", lambda: art_cork(False)), ("gem", art_gem), ("shine", art_shine)]

# 1. the artist's rig: no animation at all
p = Project(out / "potion.json", new_skeleton("potion", PX, PX))
sk = p.data
sk.bones += [Bone(name="bottle", parent="root", length=60), Bone(name="liquid", parent="bottle", y=6.0)]
for n, make in LAYERS:
    p.write_image(n, make())
    sk.add_slot(Slot(name=n, bone="liquid" if n in ("liquid", "surface") else "bottle", attachment=n,
                     blend="additive" if n == "shine" else "normal"))
    w, h = p.image(n).size
    sk.set_attachment(n, n, RegionAttachment(path=n, width=w, height=h))

# 2. the recipes, into one animation
R.apply(p, "prop_idle", into="idle", color="FF4FE0", options={"prop": "bottle", "glow": 640.0})
R.apply(p, "liquid_slosh", into="idle", options={"liquid": "liquid", "clip": R_IN})
v = qa.validate(p.data)
assert v["ok"], v["errors"]
p.save()

FPS, W = 30, 320
VIEW = (-300.0, -280.0, 300.0, 340.0)
H = int(W * (VIEW[3] - VIEW[1]) / (VIEW[2] - VIEW[0]))
dump = runtime.run(p, animations=["idle"], fps=FPS, geometry=True)
assert not dump.get("problems"), dump.get("problems")
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
frames = [render.render_frame(f["draws"], pages, VIEW, (W, H), (16, 6, 20, 255)).convert("RGB") for f in dump["animations"]["idle"]["frames"]]
shutil.rmtree(Path(next(iter(dump["_page_files"].values()))).parent, ignore_errors=True)
frames = frames * 3
frames[0].save(out / "potion.gif", save_all=True, append_images=frames[1:], duration=int(1000 / FPS), loop=0)
idx = np.linspace(0, len(frames) // 3 - 1, 6).round().astype(int)
sheet = Image.new("RGB", (W * 3, H * 2))
for k, j in enumerate(idx):
    sheet.paste(frames[j], ((k % 3) * W, (k // 3) * H))
sheet.save(out / "potion_sheet.png")
shutil.copy(out / "potion.gif", root / "docs" / "potion.gif")
print("docs/potion.gif", round((root / "docs" / "potion.gif").stat().st_size / 1e6, 2), "MB")
