"""Build the win-banner demo: the same recipe at tier big, mega and epic, one after the other. Writes to ./out/banner
and refreshes docs/win_banner.gif.

    python examples/build_banner_demo.py
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx_recipes, qa, render, runtime  # noqa: E402
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton  # noqa: E402
from claude_spine.project import Project  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "banner"
shutil.rmtree(out, ignore_errors=True)
BG = (22, 18, 32, 255)


def font(px):
    for f in ("impact.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def plate(word: str, fill, edge) -> Image.Image:
    s = 3
    w, h = 420, 150
    im = Image.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([6 * s, 18 * s, (w - 6) * s, (h - 18) * s], 40 * s, fill=(70, 12, 30), outline=edge, width=8 * s)
    d.text((w * s / 2, h * s / 2 - 4 * s), f"{word} WIN", font=font(78 * s), anchor="mm", fill=fill, stroke_width=6 * s, stroke_fill=(90, 30, 0))
    return im.resize((w, h), Image.LANCZOS)


frames_all = []
pad = 40
view = (-330, -300, 330, 330)
W = 440
H = int(W * (view[3] - view[1]) / (view[2] - view[0]))
for tier, word, fill, edge in (("big", "BIG", (255, 220, 90), (255, 196, 64)), ("mega", "MEGA", (255, 170, 60), (255, 140, 40)),
                               ("epic", "EPIC", (255, 240, 200), (200, 120, 255))):
    sk = new_skeleton(f"banner_{tier}", 720, 720)
    p = Project(out / tier / f"banner_{tier}.json", sk)
    sk.bones.append(Bone(name="banner", parent="root", y=30))
    p.write_image("plate", plate(word, fill, edge))
    sk.add_slot(Slot(name="plate", bone="banner", attachment="plate"))
    sk.set_attachment("plate", "plate", RegionAttachment(path="plate", width=420, height=150))
    res = fx_recipes.apply(p, "win_banner", y=30, tier=tier, options=dict(banner="banner"))
    v = qa.validate(sk)
    assert v["ok"], v["errors"]
    b = qa.budget(sk, "desktop")
    p.save()
    print(tier, res["parts"], "| end", res["end"], "| slots", len(res["slots"]), "| draw calls", b["metrics"]["draw_calls"])
    dump = runtime.run(p, animations=[res["animation"]], fps=20, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems"), dump.get("problems")
    pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
    fr = [render.render_frame(f["draws"], pages, view, (W, H), BG) for f in dump["animations"][res["animation"]]["frames"]]
    frames_all += fr + [fr[-1]] * 6
    idx = np.linspace(0, len(fr) - 1, 8).round().astype(int)
    sheet = Image.new("RGBA", (W * 4, H * 2))
    for k, j in enumerate(idx):
        sheet.alpha_composite(fr[j], ((k % 4) * W, (k // 4) * H))
    sheet.save(out / f"{tier}_sheet.png")

gif = out / "win_banner.gif"
pal = [f.convert("RGB").quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames_all]
pal[0].save(gif, save_all=True, append_images=pal[1:], duration=50, loop=0, disposal=2)
shutil.copy(gif, root / "docs" / "win_banner.gif")
print("frames", len(frames_all), "| gif", gif, f"{gif.stat().st_size / 1e6:.1f} MB")
