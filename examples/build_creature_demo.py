"""Build the creature demo: every rig_creature kind (slime, golem, ghost, tentacle beast, dragon, insect, plant, mimic)
from its procedural sample, each clip posed by the spine-core runtime (physics stepping) and rendered. Writes contact
sheets and GIFs to ./out/creature and refreshes docs/creature*.gif.

    python examples/build_creature_demo.py [kind ...]
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import qa, render, rig_creature, runtime  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "creature"
only = sys.argv[1:]
if not only:
    shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True, exist_ok=True)
BG = (34, 32, 44, 255)
FPS = 25

# kind -> (clips to render, the GIF plan: (clip, loops))
PLAN = {
    "slime": (["idle", "hop", "hit", "win"], [("idle", 1), ("hop", 1), ("hit", 1), ("win", 1)]),
    "golem": (["idle", "stomp", "hit"], [("idle", 1), ("stomp", 1), ("hit", 1)]),
    "ghost": (["idle", "swoop", "fade_out", "fade_in"], [("idle", 1), ("swoop", 1), ("fade_out", 1), ("fade_in", 1)]),
    "tentacle": (["idle", "reach", "slam"], [("idle", 1), ("reach", 1), ("slam", 1)]),
    "dragon": (["idle", "walk", "fly", "breath", "roar"], [("idle", 1), ("walk", 2), ("fly", 2), ("breath", 1), ("roar", 1)]),
    "insect": (["idle", "walk", "fly"], [("idle", 1), ("walk", 2), ("fly", 3)]),
    "plant": (["grow", "idle", "attack"], [("grow", 1), ("idle", 1), ("attack", 1)]),
    "mimic": (["idle", "open", "bite", "land", "win"], [("idle", 1), ("open", 1), ("bite", 1), ("land", 1), ("win", 1)]),
}
SIGNATURE = {"slime": "hop", "golem": "stomp", "ghost": "swoop", "tentacle": "reach", "dragon": "breath", "insect": "walk",
             "plant": "grow", "mimic": "open"}


def font(px):
    for f in ("arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def report(name, p, res):
    sk = p.data
    v = qa.validate(sk)
    assert v["ok"], v["errors"]
    b = qa.budget(sk, "mobile_character")
    m = b["metrics"]
    print(f"{name:9s} bones {len(sk.bones):3d} | slots {len(sk.slots):3d} | ik {len(sk.ik)} | transform {len(sk.transform)} "
          f"| physics {len(sk.physics):2d} | verts {m['vertices']:4d} | draw calls {m['draw_calls']} | "
          f"mobile_character {'ok' if b['ok'] else b['over_budget']}")
    p.save()


class Panel:
    """One project's clips, posed by spine-core, framed once for all of them."""

    def __init__(self, p, clips, W, H=None, pad=0.06):
        self.dump = runtime.run(p, animations=clips, fps=FPS, geometry=True)
        assert self.dump.get("ok", True) and not self.dump.get("problems"), self.dump.get("problems") or self.dump.get("error")
        self.pages = render._Pages(self.dump["_page_files"], self.dump.get("_pma", False))
        x0, y0, x1, y1 = render.union_bounds(self.dump, clips, pad)
        self.W = W
        self.H = H or int(W * (y1 - y0) / (x1 - x0))
        cx, cy, vw, vh = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
        if vw / vh < self.W / self.H:
            vw = vh * self.W / self.H
        else:
            vh = vw * self.H / self.W
        self.view = (cx - vw / 2, cy - vh / 2, cx + vw / 2, cy + vh / 2)

    def frames(self, clip, loops=1):
        fr = self.dump["animations"][clip]["frames"]
        seq = fr[:-1] * loops + fr[-1:] if loops > 1 else fr
        return [(clip, f) for f in seq]

    def draw(self, item, label=True, title=""):
        clip, f = item
        im = render.render_frame(f["draws"], self.pages, self.view, (self.W, self.H), BG)
        if label:
            ImageDraw.Draw(im).text((8, 6), f"{title} {clip}".strip(), font=font(14), fill=(235, 230, 250, 255))
        return im


def sequence(panel, plan):
    seq = []
    for clip, loops in plan:
        seq += panel.frames(clip, loops)
    return seq


def save_gif(frames, path, colors=128):
    pal = [f.convert("RGB").quantize(colors=colors, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    pal[0].save(path, save_all=True, append_images=pal[1:], duration=int(1000 / FPS), loop=0, disposal=2)
    print(f"  {path.name}: {len(frames)} frames, {path.stat().st_size / 1e6:.2f} MB")


def sheet(panel, clips, path, n=8):
    rows = []
    for c in clips:
        fr = panel.dump["animations"][c]["frames"]
        idx = np.linspace(0, len(fr) - 1, n).round().astype(int)
        row = Image.new("RGBA", (panel.W * n, panel.H), BG)
        for k, j in enumerate(idx):
            row.alpha_composite(panel.draw((c, fr[j]), label=(k == 0)), (k * panel.W, 0))
        rows.append(row)
    im = Image.new("RGBA", (panel.W * n, panel.H * len(rows)), BG)
    for i, r_ in enumerate(rows):
        im.alpha_composite(r_, (0, i * panel.H))
    im.save(path)


def grid(seqs, panels, titles, cols, W):
    """Several sequences side by side; the shorter ones loop (every clip loops exactly or ends on its setup)."""
    n = max(len(s) for s in seqs)
    rows = (len(seqs) + cols - 1) // cols
    hs = [max(panels[r * cols + c].H for c in range(cols) if r * cols + c < len(panels)) for r in range(rows)]
    frames = []
    for i in range(n):
        im = Image.new("RGBA", (W, sum(hs)), BG)
        for k, (s, p, t) in enumerate(zip(seqs, panels, titles)):
            r_, c = divmod(k, cols)
            im.alpha_composite(p.draw(s[i % len(s)], title=t), (c * (W // cols), sum(hs[:r_])))
        frames.append(im)
    return frames


# ------------------------------------------------------------------ build the rigs (what the MCP tools do)
kinds = only or list(rig_creature.KINDS)
projects = {}
for k in kinds:
    p = rig_creature.make_sample_creature(out / k, k)
    res = rig_creature.rig_creature(p, k)
    report(k, p, res)
    projects[k] = (p, res)

# ------------------------------------------------------------------ render through spine-core
print("rendering")
panels = {}
for k in kinds:
    clips, plan = PLAN[k]
    pw = 280 if k not in ("dragon", "tentacle") else 400
    panels[k] = Panel(projects[k][0], clips, pw)
    sheet(panels[k], clips, out / f"{k}_sheet.png")

if only:
    print("done (partial):", out)
    sys.exit(0)

GROUPS = {"creature_blobs.gif": ["slime", "golem", "ghost"], "creature_beasts.gif": ["tentacle", "dragon"],
          "creature_critters.gif": ["insect", "plant", "mimic"]}
for gif, ks in GROUPS.items():
    W = 560
    ps = [Panel(projects[k][0], PLAN[k][0], W // len(ks), 250 if len(ks) == 3 else 300) for k in ks]
    seqs = [sequence(p_, PLAN[k][1]) for p_, k in zip(ps, ks)]
    save_gif(grid(seqs, ps, ks, len(ks), W), out / gif)

# the overview: every creature, idle then its signature clip
ps = [Panel(projects[k][0], ["idle", SIGNATURE[k]], 140, 160, pad=0.04) for k in kinds]
seqs = [sequence(p_, [("idle", 1), (SIGNATURE[k], 1)]) for p_, k in zip(ps, kinds)]
save_gif(grid(seqs, ps, kinds, 4, 560), out / "creature.gif")
for g in ("creature.gif", *GROUPS):
    shutil.copy(out / g, root / "docs" / g)
print("done:", out)
