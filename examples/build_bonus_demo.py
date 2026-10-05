"""Build the bonus-game demo: four little procedural scenes, one per recipe of claude_spine/fx_bonus.py, rendered through
spine-core and joined into one GIF. Writes to ./out/bonus and refreshes docs/bonus.gif.

    python examples/build_bonus_demo.py

1. pick_reveal: three tiles. The left one is the GAME's tile (its own bone and slot, flipped through a carrier, its
   attachment swapped at the edge-on moment); the middle one is a bad pick (smoke), the right one a bad pick (ice).
2. hold_respin: a 5x3 board with three locked coins; the counter ticks 3, 2, a coin lands, refill, 3, 2, 1, 0.
3. jackpot_wheel: the game's wheel art spins on a carrier, the procedural pointer clacks, it stops on segment 5.
4. meter_fill: four energy orbs fire drops into a meter that fills, sloshes, bubbles and overflows.
"""
import math
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_bonus, fx_recipes, qa, render, runtime  # noqa: E402
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402
from claude_spine.timeline import AnimBuilder  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "bonus"
shutil.rmtree(out, ignore_errors=True)
BG = (22, 18, 32, 255)
W, H = 560, 400
FPS = 10


def region(p: Project, slot: str, bone: str, img: str, im: Image.Image, w: float, h: float, x=0.0, y=0.0, show=True):
    p.write_image(img, im)
    p.data.add_slot(Slot(name=slot, bone=bone, attachment=img if show else None))
    p.data.set_attachment(slot, img, RegionAttachment(path=img, x=x, y=y, width=w, height=h))


def panel(w: int, h: int, wells=None, fill=(40, 30, 64), rim=(255, 196, 64)) -> Image.Image:
    s = 2
    im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w * s - 1, h * s - 1], 26 * s, fill=fill, outline=rim, width=6 * s)
    for (cx, cy, cw, ch) in wells or []:
        x0, y0 = (w / 2 + cx - cw / 2) * s, (h / 2 - cy - ch / 2) * s
        d.rounded_rectangle([x0, y0, x0 + cw * s, y0 + ch * s], 14 * s, fill=(14, 10, 26), outline=(90, 70, 130), width=2 * s)
    return im.resize((w, h), Image.LANCZOS)


def coin(n: int = 120) -> Image.Image:
    s = 3
    im = Image.new("RGBA", (n * s, n * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = n * s / 2
    d.ellipse([c - 50 * s, c - 50 * s, c + 50 * s, c + 50 * s], fill=(150, 90, 10), outline=(90, 50, 0), width=3 * s)
    d.ellipse([c - 44 * s, c - 46 * s, c + 44 * s, c + 42 * s], fill=(255, 200, 50))
    d.ellipse([c - 32 * s, c - 34 * s, c + 32 * s, c + 30 * s], outline=(200, 130, 20), width=4 * s)
    pts = [(c + math.cos(-math.pi / 2 + k * math.pi / 5) * (22 if k % 2 == 0 else 9) * s,
            c - 2 * s + math.sin(-math.pi / 2 + k * math.pi / 5) * (22 if k % 2 == 0 else 9) * s) for k in range(10)]
    d.polygon(pts, fill=(255, 245, 200))
    return im.resize((n, n), Image.LANCZOS)


def wheel_art(N: int, R: int) -> Image.Image:
    s = 2
    n = 2 * R + 40
    im = Image.new("RGBA", (n * s, n * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = n * s / 2
    cols = [(200, 30, 60), (250, 190, 40), (90, 40, 170), (30, 150, 220)]
    seg = 360 / N
    d.ellipse([c - (R + 16) * s, c - (R + 16) * s, c + (R + 16) * s, c + (R + 16) * s], fill=(120, 70, 10))
    d.ellipse([c - (R + 10) * s, c - (R + 10) * s, c + (R + 10) * s, c + (R + 10) * s], fill=(255, 200, 70))
    for j in range(N):
        # PIL angles are clockwise from +x; segment j is centred at 90 - j*seg (y up) = -90 + j*seg in PIL
        a0 = -90 + j * seg - seg / 2
        d.pieslice([c - R * s, c - R * s, c + R * s, c + R * s], a0, a0 + seg, fill=cols[j % 4], outline=(255, 245, 220), width=2 * s)
        am = math.radians(-90 + j * seg)
        px, py = c + math.cos(am) * R * 0.66 * s, c + math.sin(am) * R * 0.66 * s
        d.ellipse([px - 16 * s, py - 16 * s, px + 16 * s, py + 16 * s], fill=(255, 250, 235), outline=(60, 30, 10), width=2 * s)
        k = j % 3
        if k == 0:
            d.ellipse([px - 8 * s, py - 8 * s, px + 8 * s, py + 8 * s], fill=(230, 160, 20))
        elif k == 1:
            d.polygon([(px, py - 10 * s), (px + 9 * s, py), (px, py + 10 * s), (px - 9 * s, py)], fill=(40, 140, 230))
        else:
            d.rectangle([px - 7 * s, py - 7 * s, px + 7 * s, py + 7 * s], fill=(200, 40, 60))
        ab = math.radians(-90 + j * seg - seg / 2)
        qx, qy = c + math.cos(ab) * (R + 4) * s, c + math.sin(ab) * (R + 4) * s
        d.ellipse([qx - 6 * s, qy - 6 * s, qx + 6 * s, qy + 6 * s], fill=(250, 250, 250), outline=(80, 60, 30), width=2 * s)
    d.ellipse([c - 34 * s, c - 34 * s, c + 34 * s, c + 34 * s], fill=(255, 205, 70), outline=(120, 70, 10), width=4 * s)
    d.ellipse([c - 16 * s, c - 16 * s, c + 16 * s, c + 16 * s], fill=(200, 30, 60))
    return im.resize((n, n), Image.LANCZOS)


def orb(n: int = 64) -> Image.Image:
    s = 3
    im = Image.new("RGBA", (n * s, n * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = n * s / 2
    d.ellipse([c - 28 * s, c - 28 * s, c + 28 * s, c + 28 * s], fill=(20, 90, 140), outline=(160, 240, 255), width=3 * s)
    d.ellipse([c - 18 * s, c - 20 * s, c + 14 * s, c + 12 * s], fill=(80, 210, 255))
    d.ellipse([c - 12 * s, c - 16 * s, c - 2 * s, c - 6 * s], fill=(235, 255, 255))
    return im.resize((n, n), Image.LANCZOS)


def scene_pick():
    p = Project(out / "pick" / "pick.json", new_skeleton("pick", 720, 720))
    sk = p.data
    region(p, "board", "root", "pick_board", panel(640, 250, fill=(34, 26, 58)), 640, 250)
    sk.bones.append(Bone(name="tile0", parent="root", x=-200))
    back = fx_bonus.tex_tile("back", "2A6FD0")
    prize = fx_bonus.tex_tile("good", "FFC23A")
    p.write_image("tile_back", back)
    p.write_image("tile_prize", prize)
    sk.add_slot(Slot(name="tile0", bone="tile0", attachment="tile_back"))
    sk.set_attachment("tile0", "tile_back", RegionAttachment(path="tile_back", width=150, height=150))
    sk.set_attachment("tile0", "tile_prize", RegionAttachment(path="tile_prize", width=150, height=150))
    fx_recipes.apply(p, "pick_reveal", x=-200, start=0.15, into="pick", front_of="tile0", seed=3,
                     options=dict(tile="tile0", swap_slot="tile0", swap_to="tile_prize"))
    fx_recipes.apply(p, "pick_reveal", x=0, start=0.75, into="pick", front_of="tile0", seed=4, options=dict(good=False, bad="smoke"))
    fx_recipes.apply(p, "pick_reveal", x=200, start=1.35, into="pick", front_of="tile0", seed=5, options=dict(good=False, bad="ice"))
    # the two procedural tiles show their back before their flip starts
    return p, "pick", (-330, -170, 330, 230)


def scene_hold():
    p = Project(out / "hold" / "hold.json", new_skeleton("hold", 720, 720))
    sk = p.data
    pitch, cw = 130, 120
    wells = [((c_ - 2) * pitch, (1 - r_) * pitch, cw, cw) for r_ in range(3) for c_ in range(5)]
    region(p, "board", "root", "hold_board", panel(5 * pitch + 30, 3 * pitch + 30, wells=[(x, y, w, h) for x, y, w, h in wells]),
           5 * pitch + 30, 3 * pitch + 30)
    locked = [(1, 0), (3, 1), (0, 2)]
    cells = []
    for i, (c_, r_) in enumerate(locked):
        x, y = (c_ - 2) * pitch, (1 - r_) * pitch
        sk.bones.append(Bone(name=f"coin{i}", parent="root", x=x, y=y))
        region(p, f"coin{i}", f"coin{i}", "coin", coin(), 100, 100)
        cells.append([x, y, cw, cw])
    # the coin that lands during respin 2 (the counter resets): it pops in on the game's own keys
    nx, ny = (2 - 2) * pitch, (1 - 2) * pitch
    sk.bones.append(Bone(name="coin_new", parent="root", x=nx, y=ny))
    region(p, "coin_new", "coin_new", "coin", coin(), 100, 100, show=False)
    res = fx_recipes.apply(p, "hold_respin", y=-10, into="hold", front_of="coin_new", seed=8,
                           options=dict(cells=[[x, y + 10, w, h] for x, y, w, h in cells], respins=3, period=1.0, resets=[2],
                                        ring_y=205 + 10 + 80, ring_size=124))
    t_new = res["fills"][1]
    ab = AnimBuilder(sk, "hold", replace=False)
    ab.slot_attachment("coin_new", [(0, None), (t_new - 0.05, "coin")])
    ab.bone("coin_new", "scale", [(t_new - 0.05, 1.6, 1.6), (t_new + 0.1, 0.9, 0.9), (t_new + 0.25, 1, 1)], "linear")
    return p, "hold", (-345, -215, 345, 375)


def scene_wheel():
    p = Project(out / "wheel" / "wheel.json", new_skeleton("wheel", 720, 720))
    sk = p.data
    R = 200
    sk.bones.append(Bone(name="wheel", parent="root"))
    art = wheel_art(12, R)
    region(p, "wheel", "wheel", "wheel_art", art, art.size[0], art.size[1])
    fx_recipes.apply(p, "jackpot_wheel", into="wheel", front_of="wheel", start=0.2, seed=2, duration=4.6,
                     options=dict(segments=12, winner=5, spins=3, radius=R, wheel="wheel"))
    return p, "wheel", (-290, -240, 290, 330)


def scene_meter():
    p = Project(out / "meter" / "meter.json", new_skeleton("meter", 720, 720))
    sk = p.data
    MW, MH = 70, 320
    region(p, "glass", "root", "meter_glass", panel(MW + 26, MH + 26, fill=(12, 16, 30), rim=(120, 150, 190)), MW + 26, MH + 26)
    srcs = [[-250.0, 150.0], [240.0, 190.0], [-230.0, -60.0], [235.0, -20.0]]
    for i, (x, y) in enumerate(srcs):
        sk.bones.append(Bone(name=f"orb{i}", parent="root", x=x, y=y))
        region(p, f"orb{i}", f"orb{i}", "orb", orb(), 56, 56)
    fx_recipes.apply(p, "meter_fill", into="meter", front_of="glass", start=0.1, seed=6,
                     options=dict(width=MW, height=MH, sources=srcs))
    # the glass front: a rim drawn over the liquid
    rim = Image.new("RGBA", ((MW + 26) * 2, (MH + 26) * 2), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle([0, 0, rim.size[0] - 1, rim.size[1] - 1], 52, outline=(255, 210, 90), width=12)
    region(p, "rim", "root", "meter_rim", rim.resize((MW + 26, MH + 26), Image.LANCZOS), MW + 26, MH + 26)
    return p, "meter", (-320, -200, 320, 375)


frames_all, sheets = [], []
for build in (scene_pick, scene_hold, scene_wheel, scene_meter):
    p, anim, view = build()
    v = qa.validate(p.data)
    assert v["ok"], v["errors"]
    b = qa.budget(p.data, "mobile_banner")
    p.save()
    dump = runtime.run(p, animations=[anim], fps=FPS, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems"), dump.get("problems")
    pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
    # render at 2x and downsample: antialiased edges, and minified textures never sample past their atlas region
    frames = [render.render_frame(f["draws"], pages, view, (2 * W, 2 * H), BG).resize((W, H), Image.LANCZOS)
              for f in dump["animations"][anim]["frames"]]
    print(f"{anim}: validate ok, draw calls {b['metrics']['draw_calls']}, bones {len(p.data.bones)}, slots {len(p.data.slots)}, "
          f"{len(frames)} frames, {dump['animations'][anim]['duration']:.2f} s")
    frames_all += frames
    idx = np.linspace(0, len(frames) - 1, 8).round().astype(int)
    sheet = Image.new("RGBA", (W * 4, H * 2))
    for k, j in enumerate(idx):
        sheet.alpha_composite(frames[j], ((k % 4) * W, (k // 4) * H))
    sheet.save(out / f"{anim}_sheet.png")
    sheets.append(sheet.resize((W * 2, H)))
combo = Image.new("RGBA", (W * 2, H * len(sheets)))
for i, s_ in enumerate(sheets):
    combo.alpha_composite(s_, (0, i * H))
combo.save(out / "bonus_sheet.png")
gif = out / "bonus.gif"
pal = [f.convert("RGB").quantize(colors=80, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames_all]
pal[0].save(gif, save_all=True, append_images=pal[1:], duration=int(1000 / FPS), loop=0, disposal=2)
shutil.copy(gif, root / "docs" / "bonus.gif")
print("frames", len(frames_all), "| gif", gif, f"{gif.stat().st_size / 1e6:.1f} MB")
