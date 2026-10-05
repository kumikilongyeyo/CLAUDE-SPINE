"""Build the ambient demo: one tile per screen-level atmosphere recipe (weather rain / snow / embers / petals, god_rays,
water_surface, heat_shimmer, fog_roll fog / sand, lightning_storm), each over a procedural backdrop, rendered through
spine-core. Writes to ./out/ambient (a project per tile, a contact sheet, a GIF) and refreshes docs/ambient.gif.

    python examples/build_ambient_demo.py

Only the Spine halves are shown; the After Effects halves (god_rays, caustics, heat_shimmer, fog_roll, lightning) come
from each result's ae_hint.
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_ambient, fx_recipes, qa, render, runtime  # noqa: E402,F401  fx_ambient registers the recipes
from claude_spine.ir import RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "ambient"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)

VW, VH = 760.0, 543.0                    # design units per tile
TW, TH = 280, 200                        # pixels per tile
FPS, SECONDS = 12.5, 4.0
NF = int(SECONDS * FPS)


def font(px):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def gradient(top, bottom, w=380, h=272, extra=None) -> Image.Image:
    t = np.linspace(0, 1, h)[:, None, None]
    rgb = np.array(top, float) * (1 - t) + np.array(bottom, float) * t
    im = Image.fromarray(np.repeat(rgb, w, 1).astype(np.uint8), "RGB").convert("RGBA")
    if extra:
        extra(ImageDraw.Draw(im), w, h)
    return im


def hills(color):
    def draw(d, w, h):
        pts = [(0, h)] + [(x, h * 0.78 - 18 * np.sin(x / w * 7.0) - 10 * np.sin(x / w * 17.0 + 1)) for x in range(0, w + 9, 8)] + [(w, h)]
        d.polygon(pts, fill=color)
    return draw


def city(d, w, h):
    rng = np.random.default_rng(3)
    x = 0
    while x < w:
        bw, bh = int(rng.integers(20, 46)), int(rng.integers(40, 130))
        d.rectangle([x, h - bh, x + bw, h], fill=(22, 26, 40))
        for wy in range(h - bh + 8, h - 6, 12):
            for wx in range(x + 5, x + bw - 5, 9):
                if rng.random() < 0.3:
                    d.rectangle([wx, wy, wx + 3, wy + 4], fill=(150, 130, 70))
        x += bw + int(rng.integers(2, 8))


def fire_pit(d, w, h):
    for k in range(24, 0, -1):                         # a low fire glow on the ground, brightest in the middle
        r = k * 7
        c = (min(255, 40 + (24 - k) * 8), min(255, 14 + (24 - k) * 3), 8)
        d.ellipse([w / 2 - r * 1.3, h * 0.97 - r * 0.32, w / 2 + r * 1.3, h * 0.97 + r * 0.32], fill=c)


def heat_scene(d, w, h):
    for i in range(0, w, 16):                          # a striped wall behind (what the AE shimmer would bend)
        d.rectangle([i, 0, i + 7, h * 0.8], fill=(70, 52, 44))
    d.rectangle([0, h * 0.8, w, h], fill=(30, 20, 16))
    for k in range(12, 0, -1):                         # a flame: teardrop layers, hot inside
        r = k * 3.6
        cx, by = w / 2, h * 0.84
        d.polygon([(cx - r * 0.8, by), (cx - r * 0.55, by - r * 1.2), (cx, by - r * 2.6), (cx + r * 0.55, by - r * 1.2), (cx + r * 0.8, by)],
                  fill=(255, min(255, 60 + (12 - k) * 16), min(255, 10 + (12 - k) * 14)))


def interior(d, w, h):
    d.rectangle([0, h * 0.82, w, h], fill=(30, 24, 22))
    for i in range(6):
        x = 40 + i * 62
        d.rectangle([x, h * 0.35, x + 26, h * 0.82], fill=(44, 34, 30))


def reels_water(d, w, h):
    cols = [(255, 196, 40), (60, 170, 255), (222, 30, 52), (40, 190, 90), (190, 90, 255)]
    for i in range(5):
        for j in range(3):
            cx, cy = w / 2 + (i - 2) * 75, h / 2 + (j - 1) * 75
            d.rounded_rectangle([cx - 26, cy - 26, cx + 26, cy + 26], 8, fill=cols[(i + j) % 5], outline=(250, 250, 250), width=2)


def tile(name, recipe, backdrop, x=0.0, y=0.0, **kw):
    sk = new_skeleton(name, 720, 720)
    p = Project(out / name / f"{name}.json", sk)
    p.write_image("backdrop", backdrop)
    sk.add_slot(Slot(name="backdrop", bone="root", attachment="backdrop"))
    sk.set_attachment("backdrop", "backdrop", RegionAttachment(path="backdrop", width=VW, height=VH))
    res = fx_recipes.apply(p, recipe, x=x, y=y, front_of="backdrop", **kw)
    v = qa.validate(sk)
    assert v["ok"], v["errors"]
    p.save()
    dump = runtime.run(p, animations=[res["animation"]], fps=FPS, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems"), dump.get("problems")
    pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
    view = (-VW / 2, -VH / 2, VW / 2, VH / 2)
    fr = [render.render_frame(f["draws"], pages, view, (TW, TH), (0, 0, 0, 255)) for f in dump["animations"][res["animation"]]["frames"]]
    print(f"{name:16s} slots {len(res['slots']):3d}  frames {len(fr)}")
    fr = fr[:-1] if len(fr) > NF else fr                       # t = D repeats t = 0 in a loop
    return name, [fr[i % len(fr)] for i in range(NF)], res


H2 = VH / 2
tiles = [
    tile("rain", "weather", gradient((14, 20, 38), (30, 40, 64), extra=city), duration=4.0, options=dict(kind="rain", width=VW + 60, height=VH + 40)),
    tile("snow", "weather", gradient((20, 28, 48), (58, 70, 96), extra=hills((200, 210, 228))), duration=4.0,
         options=dict(kind="snow", width=VW + 40, height=VH + 40)),
    tile("embers", "weather", gradient((10, 6, 8), (50, 18, 10), extra=fire_pit), duration=4.0,
         options=dict(kind="embers", width=VW * 0.7, height=VH + 20)),
    tile("petals", "weather", gradient((60, 40, 86), (180, 110, 130), extra=hills((52, 36, 60))), duration=4.0,
         options=dict(kind="petals", width=VW + 60, height=VH + 40)),
    tile("god_rays", "god_rays", gradient((16, 12, 10), (36, 28, 24), extra=interior), x=-VW / 2 + 60, y=H2 - 10, duration=4.0,
         options=dict(angle=-58, length=720, spread=46, width=120)),
    tile("water_surface", "water_surface", gradient((6, 40, 60), (4, 22, 40), extra=reels_water), duration=4.0,
         options=dict(lands=[[(i - 2) * 150.0, (j - 1) * 150.0 - 50.0, 0.3 + 0.35 * i] for i in range(5) for j in range(3)], life=1.3, size=170)),
    tile("heat_shimmer", "heat_shimmer", gradient((24, 16, 14), (40, 26, 20), extra=heat_scene), y=30, duration=4.0,
         options=dict(height=230, width=130, alpha=0.24)),
    tile("fog", "fog_roll", gradient((24, 30, 44), (60, 70, 88), extra=hills((26, 30, 40))), y=-VH * 0.22, duration=4.0,
         options=dict(kind="fog", height=260, width=VW + 200)),
    tile("sand", "fog_roll", gradient((120, 70, 40), (200, 140, 80), extra=hills((110, 70, 40))), y=-VH * 0.12, duration=4.0,
         options=dict(kind="sand", height=360, width=VW + 200)),
    tile("lightning_storm", "lightning_storm", gradient((8, 10, 22), (26, 30, 52), extra=hills((10, 12, 20))), duration=4.0, seed=6,
         options=dict(rate=1.2, min_gap=0.3, width=VW, height=VH, length=430, distance=[0.6, 2.5])),
]

# ------------------------------------------------------------------ grid GIF + contact sheet
COLS = 2
ROWS = (len(tiles) + COLS - 1) // COLS
lab = font(13)
frames = []
for k in range(NF):
    im = Image.new("RGBA", (TW * COLS, TH * ROWS), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    for i, (name, fr, _) in enumerate(tiles):
        x0, y0 = (i % COLS) * TW, (i // COLS) * TH
        im.alpha_composite(fr[k], (x0, y0))
        d.text((x0 + 7, y0 + 5), name.replace("_", " "), font=lab, fill=(255, 255, 255, 230), stroke_width=2, stroke_fill=(0, 0, 0, 200))
    frames.append(im)
gif = out / "ambient.gif"
# one global 256-colour palette from a montage of frames: per-frame palettes over ten different scenes band and recolour
pick = frames[::5]
mont = Image.new("RGB", (frames[0].width, frames[0].height * len(pick)))
for i, f in enumerate(pick):
    mont.paste(f.convert("RGB"), (0, i * f.height))
palette = mont.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
pal = [f.convert("RGB").quantize(palette=palette, dither=Image.Dither.NONE) for f in frames]
pal[0].save(gif, save_all=True, append_images=pal[1:], duration=int(1000 / FPS), loop=0, disposal=2)
for i, (name, fr, _) in enumerate(tiles):                       # one contact sheet per tile (8 moments) to judge each recipe
    sheet = Image.new("RGBA", (TW * 4, TH * 2))
    for j, idx in enumerate(np.linspace(0, NF - 1, 8).round().astype(int)):
        sheet.alpha_composite(fr[idx], ((j % 4) * TW, (j // 4) * TH))
    sheet.save(out / f"sheet_{name}.png")
big = Image.new("RGBA", (TW * COLS * 2, TH * ROWS))             # overview: two moments of every tile side by side
for i, (name, fr, _) in enumerate(tiles):
    for j, idx in enumerate((NF // 4, (3 * NF) // 4)):
        big.alpha_composite(fr[idx], ((i % COLS) * 2 * TW + j * TW, (i // COLS) * TH))
big.save(out / "ambient_sheet.png")
shutil.copy(gif, root / "docs" / "ambient.gif")
print("frames", NF, "| gif", gif, f"{gif.stat().st_size / 1e6:.1f} MB")
