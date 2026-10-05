"""Build the body demo: the procedural biped rigged with rig_biped, the whole character contract from clip_set,
checked with qa_character, rendered through spine-core. Writes to ./out/body and refreshes docs/body.gif plus one
GIF per clip family (docs/body_<family>.gif).

    python examples/build_body_demo.py

The floor is drawn as ticks scrolling at the clip's own ground speed (the float of its sfx_step events): a planted
foot must ride its tick exactly. Loops are played three times and the last pass is shown, so the physics (cape,
ponytail, belt strap, pouch) is in its steady state, not starting from rest.
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import qa, render, runtime  # noqa: E402
from claude_spine import qa_character as QC  # noqa: E402
from claude_spine import rig_body as RB  # noqa: E402
from claude_spine.ir import EventKey, Key  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "body"
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
BG = (34, 32, 44, 255)
FPS = 25


def font(px):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def repeat_clip(sk, name: str, n: int, new: str):
    """A demo-only copy of a loop played n times back to back (keys shifted by k * duration)."""
    a = sk.animations[name]
    D = a.duration()
    b = a.model_copy(deep=True)

    def rep(ks):
        outk = []
        for k in range(n):
            for i, key in enumerate(ks):
                if k and i == 0:
                    continue
                c = key.model_copy(deep=True)
                c.time = round(key.time + k * D, 4)
                if isinstance(c.curve, list):
                    c.curve = [round(v + k * D, 4) if j % 2 == 0 else v for j, v in enumerate(c.curve)]
                outk.append(c)
        return outk
    for tls in b.bones.values():
        for tl in list(tls):
            tls[tl] = rep(tls[tl])
    for tls in b.slots.values():
        for tl in list(tls):
            tls[tl] = rep(tls[tl])
    for tls in b.physics.values():
        for tl in list(tls):
            tls[tl] = rep(tls[tl]) if len(tls[tl]) > 1 else tls[tl]
    b.events = [EventKey(time=round(e.time + k * D, 4), name=e.name, **(e.model_extra or {}))
                for k in range(n) for e in a.events if not (k and e.time >= D - 1e-6)]
    sk.animations[new] = b
    return D


# ------------------------------------------------------------------ the character
p = RB.make_sample_biped(out / "hero")
rig = RB.rig_biped(p)
clips = RB.clip_set(p)
sk = p.data
v = qa.validate(sk)
assert v["ok"], v["errors"]
b = qa.budget(sk, "mobile_character")
print("rig:", rig["counts"], "| facing", rig["facing"], "| secondary", sorted(rig["secondary"]["strands"]))
print("mobile_character:", b["ok"], b["metrics"])
print("clips:", {k: v_["duration"] for k, v_ in clips["clips"].items()}, "skipped", clips["skipped"])

LOOPS = {"idle": 1, "walk": 3, "run": 4, "talk": 2}
for c, n in LOOPS.items():
    if n > 1:
        repeat_clip(sk, c, n, f"{c}_x{n}")
p.save()

# ------------------------------------------------------------------ QA (on the real clips)
dump_qa = runtime.run(p, animations=list(RB.CHARACTER_CLIPS), fps=30, geometry=True)
assert dump_qa["ok"], dump_qa.get("error") or dump_qa["problems"][:3]
rep = QC.qa_character(p, dump=dump_qa)
print("qa_character ok:", rep["ok"], "| worst crack", rep["worst_crack"], "| worst slide", rep["worst_slide"], "px",
      "| budget", rep["budget"]["metrics"], rep["budget"]["rig_type"])
for f in rep["fix"]:
    print("  fix:", f)

# ------------------------------------------------------------------ render
play = {c: (f"{c}_x{LOOPS[c]}" if LOOPS.get(c, 1) > 1 else c) for c in RB.CHARACTER_CLIPS}
dump = runtime.run(p, animations=sorted(set(play.values())), fps=FPS, geometry=True)
assert dump["ok"], dump.get("error") or dump["problems"][:3]
pages = render._Pages(dump["_page_files"], dump.get("_pma", False))
speed = {c: QC._ground_speed(sk, c) for c in RB.CHARACTER_CLIPS}
F = 1 if rig["facing"] == "right" else -1


def frames_of(clip: str):
    """(t, draws) of the shown pass: the last loop of a repeated loop, the whole clip otherwise."""
    fr = dump["animations"][play[clip]]["frames"]
    D = RB.CHARACTER_CLIPS[clip]["length"]
    n = LOOPS.get(clip, 1)
    t0 = D * (n - 1)
    sel = [f for f in fr if f["t"] >= t0 - 1e-6]
    return [(f["t"] - t0, f["draws"]) for f in sel]


def panel(draws, t, clip, view, size, label=True):
    W, H = size
    im = Image.new("RGBA", (W, H), BG)
    d = ImageDraw.Draw(im)
    s = min(W / (view[2] - view[0]), H / (view[3] - view[1]))
    ox = (W - (view[2] - view[0]) * s) / 2
    oy = (H - (view[3] - view[1]) * s) / 2
    yf = H - ((rig["floor"] - view[1]) * s + oy)
    d.rectangle([0, yf, W, H], fill=(52, 48, 62, 255))
    d.line([(0, yf), (W, yf)], fill=(150, 140, 170, 255), width=2)
    sp = 40.0
    shift = (-F * speed.get(clip, 0.0) * t) % sp
    x = view[0] - sp + shift
    while x < view[2] + sp:
        sx = (x - view[0]) * s + ox
        d.line([(sx, yf), (sx - 6, yf + 9)], fill=(110, 102, 128, 255), width=2)
        x += sp
    im2 = render.render_frame(draws, pages, view, (W, H), (0, 0, 0, 0))
    im.alpha_composite(im2)
    if label:
        ImageDraw.Draw(im).text((10, 8), clip, font=font(max(12, W // 22)), fill=(255, 236, 170, 255))
    return im


def save_gif(frames, path, ms=1000 // FPS):
    pal = [f.convert("RGB").quantize(colors=96, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=ms, loop=0, disposal=2, optimize=True)
    return path.stat().st_size / 1e6


VIEW = (-250, -30, 250, 600)          # tall enough for the jump apex
SHOW = ["idle", "walk", "run", "jump", "land", "hit", "attack", "win"]

# contact sheets (8 frames per clip)
for c in RB.CHARACTER_CLIPS:
    fr = frames_of(c)
    idx = np.linspace(0, len(fr) - 1, 8).round().astype(int)
    view = (-200, -30, 200, 600) if c in ("jump", "win") else (-200, -30, 200, 470)
    W = 200
    H = int(W * (view[3] - view[1]) / (view[2] - view[0]))
    sheet = Image.new("RGBA", (W * 8, H), BG)
    for k, j in enumerate(idx):
        t, dr = fr[j]
        sheet.alpha_composite(panel(dr, t, f"{c} {t:.2f}", view, (W, H)), (k * W, 0))
    sheet.save(out / f"{c}_sheet.png")

# the showcase: one clip after another
W = 560
H = int(W * (VIEW[3] - VIEW[1]) / (VIEW[2] - VIEW[0]))
show = []
for c in SHOW:
    fr = frames_of(c)
    if c == "idle":
        fr = fr[: int(len(fr) * 0.6)]
    show += [panel(dr, t, c, VIEW, (W, H)) for t, dr in fr]
mb = save_gif(show, out / "body.gif")
print("body.gif", len(show), "frames", f"{mb:.1f} MB")

# one GIF per clip family, clips side by side
FAMILIES = {"idle": ["idle", "idle_fidget", "talk"], "locomotion": ["walk", "run"], "air": ["jump", "land"],
            "combat": ["hit", "attack"], "result": ["win", "lose"]}
fam_files = {}
for fam, cs in FAMILIES.items():
    n = len(cs)
    pw = W // n
    view = (-170, -30, 170, 600) if fam in ("air", "result") else (-170, -30, 170, 470)
    ph = int(pw * (view[3] - view[1]) / (view[2] - view[0]))
    seqs = [frames_of(c) for c in cs]
    loops = [len(s_) - 1 for c, s_ in zip(cs, seqs) if RB.CHARACTER_CLIPS[c]["loop"]]
    if len(loops) == len(cs):
        L = int(np.lcm.reduce(loops))                   # every loop closes on the GIF's own loop point
        L = L if L <= 160 else max(loops)
    else:
        L = max(len(s_) for s_ in seqs) + 8             # one-shots play once, then hold the setup pose
    frames = []
    for i in range(L):
        im = Image.new("RGBA", (pw * n, ph), BG)
        for k, (c, s) in enumerate(zip(cs, seqs)):
            t, dr = s[i % (len(s) - 1)] if RB.CHARACTER_CLIPS[c]["loop"] else s[min(i, len(s) - 1)]
            im.alpha_composite(panel(dr, t, c, view, (pw, ph)), (k * pw, 0))
        frames.append(im)
    path = out / f"body_{fam}.gif"
    mb = save_gif(frames, path)
    fam_files[fam] = path
    print(f"body_{fam}.gif", len(frames), "frames", f"{mb:.1f} MB")

docs = root / "docs"
shutil.copy(out / "body.gif", docs / "body.gif")
for fam, path in fam_files.items():
    shutil.copy(path, docs / path.name)
print("written to", out, "and docs/body*.gif")
