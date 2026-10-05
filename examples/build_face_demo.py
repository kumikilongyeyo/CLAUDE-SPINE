"""Build the face-rig demo: the procedural sample face (layers named like a PSD import) rigged by rig_face, doing
idle, the four expressions, talk and a look-around through the lagged look_at chain (eyes -> head -> chest).
Writes to ./out/face and refreshes docs/face.gif.

    python examples/build_face_demo.py
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import qa, render, rig, rig_face, runtime  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "face"
shutil.rmtree(out, ignore_errors=True)
BG = (34, 30, 44, 255)
FPS = 20

# ------------------------------------------------------------------ the sample, a chest bone, the rig
p = rig_face.make_sample_face(out / "sample")
sk = p.data
sk.add_bone_world("chest", "root", 0, 70, 0, length=60)
rig.reparent_slot(sk, "body", "chest")
res = rig_face.rig_face(p, parent="chest", spine="chest", talk_text="Hello! Spin to win, big wins today.")
rig_face.look_at(p, "look_around", gaze=[[0.25, 0.85, 0.05], [1.25, -0.8, 0.25], [2.25, 0.1, -0.6], [3.0, 0.0, 0.0]],
                 duration=3.6, spine="chest")
CLIPS = ["idle", "happy", "sad", "angry", "surprised", "talk", "look_around"]
v = qa.validate(sk)
assert v["ok"], v["errors"]
b = qa.budget(sk, "mobile_character")
p.save()
print("validate ok | bones", len(sk.bones), "| slots", len(sk.slots), "| transform", len(sk.transform), "| ik",
      len(sk.ik), "| physics", len(sk.physics))
print("budget mobile_character ok:", b["ok"], b["metrics"], b["over_budget"])

# ------------------------------------------------------------------ render through spine-core
dump = runtime.run(p, animations=CLIPS, fps=FPS, geometry=True)
assert dump.get("ok", True) and not dump.get("problems"), dump.get("problems") or dump.get("error")
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
view = (-230, 70, 230, 605)
W = 560
H = int(W * (view[3] - view[1]) / (view[2] - view[0]))


def font(px):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


F = font(26)


def palette_for(frames):
    """One shared palette from a mosaic of sampled frames: identical colours keep identical indexes from frame to
    frame, so the GIF stores only the pixels that change (delta frames, disposal 1)."""
    pick = frames[:: max(1, len(frames) // 12)]
    mos = Image.new("RGB", (W, H * len(pick)))
    for i, f in enumerate(pick):
        mos.paste(f.convert("RGB"), (0, i * H))
    return mos.quantize(colors=80, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)


def save_gif(frames, path, pal_img):
    q = [f.convert("RGB").quantize(palette=pal_img, dither=Image.Dither.NONE) for f in frames]
    q[0].save(path, save_all=True, append_images=q[1:], duration=1000 // FPS, loop=0, disposal=1, optimize=False)


per_clip = {}
for clip in CLIPS:
    fr = [render.render_frame(f["draws"], pages, view, (W, H), BG) for f in dump["animations"][clip]["frames"]]
    for im in fr:
        d = ImageDraw.Draw(im)
        d.text((18, 14), clip, font=F, fill=(255, 236, 200, 255))
    g = out / f"face_{clip}.gif"
    save_gif(fr, g, palette_for(fr))
    k = 8
    idx = np.linspace(0, len(fr) - 1, k).round().astype(int)
    tw, th = W // 2, H // 2
    sheet = Image.new("RGBA", (tw * 4, th * 2), BG)
    for i, j in enumerate(idx):
        sheet.alpha_composite(fr[j].resize((tw, th), Image.LANCZOS), ((i % 4) * tw, (i // 4) * th))
    sheet.save(out / f"face_{clip}_sheet.png")
    per_clip[clip] = fr
    print(clip, len(fr), "frames", f"{g.stat().st_size / 1e6:.2f} MB")

# two docs GIFs (each under ~6 MB): the expressions, then talk + look_around
for gname, clips in (("face", ["idle", "happy", "sad", "angry", "surprised"]), ("face_talk", ["talk", "look_around"])):
    frames = [f for c in clips for f in per_clip[c]]
    gif = out / f"{gname}.gif"
    save_gif(frames, gif, palette_for(frames))
    shutil.copy(gif, root / "docs" / f"{gname}.gif")
    print(gname, "frames", len(frames), "| gif", gif, f"{gif.stat().st_size / 1e6:.1f} MB")
