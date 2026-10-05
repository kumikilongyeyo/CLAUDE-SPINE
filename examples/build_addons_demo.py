"""Build the chain-rig and add-on demo: a koi (rig_serpent swim / turn / idle_float), a tentacle (reach), a bird
(rig_flier perch -> takeoff -> flap -> glide -> land) and the procedural host with ears + tail + wings attached
(attach_rig), plus the other add-ons (horns + fur + glow, digitigrade legs, mermaid tail, snake hair). Everything is
rendered through the spine-core runtime. Writes to ./out/addons and refreshes docs/addons*.gif.

    python examples/build_addons_demo.py
"""
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import qa, render, rig_addons, rig_chain, runtime  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "addons"
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


def report(name, p):
    sk = p.data
    v = qa.validate(sk)
    assert v["ok"], v["errors"]
    b = qa.budget(sk, "mobile_character")
    print(f"{name:12s} bones {len(sk.bones):3d} | slots {len(sk.slots):3d} | ik {len(sk.ik)} | transform {len(sk.transform)} "
          f"| physics {len(sk.physics):2d} | budget mobile_character {'ok' if b['ok'] else b['over_budget']} "
          f"(verts {b['metrics']['vertices']}, draw calls {b['metrics']['draw_calls']})")
    p.save()


class Panel:
    """One project's clips, posed by spine-core, framed once for all of them."""

    def __init__(self, p, clips, W, H=None, pad=0.06):
        self.dump = runtime.run(p, animations=clips, fps=FPS, geometry=True)
        assert self.dump.get("ok", True) and not self.dump.get("problems"), self.dump.get("problems")
        self.pages = render._Pages(self.dump["_page_files"], self.dump.get("_pma", False))
        x0, y0, x1, y1 = render.union_bounds(self.dump, clips, pad)
        self.W = W
        self.H = H or int(W * (y1 - y0) / (x1 - x0))
        # widen the view to the panel's aspect so nothing is squeezed
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

    def draw(self, item, label=True):
        clip, f = item
        im = render.render_frame(f["draws"], self.pages, self.view, (self.W, self.H), BG)
        if label:
            ImageDraw.Draw(im).text((8, 6), clip, font=font(15), fill=(235, 230, 250, 255))
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


def grid(seqs, panels, cols, W):
    """Play several sequences side by side; the shorter ones loop (all clips loop exactly or end on setup)."""
    n = max(len(s) for s in seqs)
    rows = (len(seqs) + cols - 1) // cols
    hs = [max(panels[r * cols + c].H for c in range(cols) if r * cols + c < len(panels)) for r in range(rows)]
    out_ = []
    for i in range(n):
        im = Image.new("RGBA", (W, sum(hs)), BG)
        for k, (s, p) in enumerate(zip(seqs, panels)):
            r_, c = divmod(k, cols)
            im.alpha_composite(p.draw(s[i % len(s)]), (c * (W // cols), sum(hs[:r_])))
        out_.append(im)
    return out_


# ------------------------------------------------------------------ build the rigs (what the MCP tools do)
koi = rig_chain.make_sample_serpent(out / "koi")
rk = rig_chain.rig_serpent(koi)
report("koi", koi)
ten = rig_chain.make_sample_serpent(out / "tentacle", "tentacle")
rt = rig_chain.rig_serpent(ten, mode="tentacle", n_bones=10)
report("tentacle", ten)
bird = rig_chain.make_sample_flier(out / "bird")
rb = rig_chain.rig_flier(bird)
report("bird", bird)
host = rig_addons.make_sample_host(out / "host", ("ears", "tail", "wings"))
for k in ("ears", "tail", "wings"):
    r_ = rig_addons.attach_rig(host, k)
    print(f"  attach {k}:", ", ".join(f"{c} {v['length']}s {v['mode']}" for c, v in r_["clips"].items()))
report("host", host)
more = {}
for kinds in (("horns", "fur", "glow"), ("digitigrade",), ("mermaid",), ("snake_hair",)):
    p = rig_addons.make_sample_host(out / ("host_" + "_".join(kinds)), kinds)
    for k in kinds:
        rig_addons.attach_rig(p, k)
    report("+".join(kinds)[:12], p)
    more[kinds] = p

# ------------------------------------------------------------------ render through spine-core
print("rendering")
pk = Panel(koi, ["swim", "turn", "idle_float"], 560)
pt = Panel(ten, ["swim", "reach"], 180)
pb = Panel(bird, ["perch", "takeoff", "flap", "glide", "land"], 280)
ph = Panel(host, ["idle", "walk", "ear_perk", "ear_swivel", "ear_flatten", "tail_angry", "excited", "win"], 280)
sheet(pk, ["swim", "turn", "idle_float"], out / "serpent_sheet.png")
sheet(pt, ["swim", "reach"], out / "tentacle_sheet.png")
sheet(pb, ["perch", "takeoff", "flap", "glide", "land"], out / "flier_sheet.png")
sheet(ph, ["idle", "walk", "ear_perk", "ear_swivel", "ear_flatten", "tail_angry", "excited", "win"], out / "host_sheet.png")

s_koi = sequence(pk, [("swim", 3), ("turn", 1), ("idle_float", 1)])
s_ten = sequence(pt, [("swim", 2), ("reach", 1)])
s_bird = sequence(pb, [("perch", 1), ("takeoff", 1), ("flap", 3), ("glide", 1), ("land", 1), ("perch", 1)])
s_host = sequence(ph, [("idle", 1), ("ear_perk", 1), ("ear_swivel", 1), ("walk", 2), ("excited", 2), ("win", 1)])
save_gif([pk.draw(f) for f in s_koi], out / "addons_serpent.gif")
save_gif([pb.draw(f) for f in s_bird], out / "addons_flier.gif")
save_gif([ph.draw(f) for f in s_host], out / "addons_host.gif")

pm = [Panel(more[("horns", "fur", "glow")], ["idle", "fur_ruffle"], 140, 210), Panel(more[("digitigrade",)], ["walk"], 140, 210),
      Panel(more[("mermaid",)], ["swim", "idle"], 140, 210), Panel(more[("snake_hair",)], ["idle", "snake_look"], 140, 210)]
s_more = [sequence(pm[0], [("idle", 1), ("fur_ruffle", 1)]), sequence(pm[1], [("walk", 3)]),
          sequence(pm[2], [("swim", 1), ("idle", 1)]), sequence(pm[3], [("idle", 1), ("snake_look", 1)])]
save_gif(grid(s_more, pm, 4, 560), out / "addons_more.gif")
for p_, c_, nm in zip(pm, (["idle", "fur_ruffle"], ["walk"], ["swim", "idle"], ["idle", "snake_look"]),
                      ("horns_fur_glow", "digitigrade", "mermaid", "snake_hair")):
    sheet(p_, c_, out / f"{nm}_sheet.png")

# the overview: koi on top; bird, host and tentacle below
pk2 = Panel(koi, ["swim", "idle_float"], 560, 170, pad=0.03)
pb2 = Panel(bird, ["perch", "takeoff", "flap", "glide", "land"], 210, 230)
ph2 = Panel(host, ["idle", "walk", "ear_perk", "ear_swivel", "ear_flatten", "tail_angry", "excited", "win"], 210, 230)
pt2 = Panel(ten, ["swim", "reach"], 140, 230)
top = sequence(pk2, [("swim", 5), ("idle_float", 1)])
row = [sequence(pb2, [("flap", 3), ("glide", 1), ("land", 1), ("perch", 1), ("takeoff", 1)]),
       sequence(ph2, [("idle", 1), ("ear_perk", 1), ("walk", 2), ("excited", 2), ("ear_swivel", 1)]),
       sequence(pt2, [("swim", 2), ("reach", 1), ("swim", 1)])]
n = max(len(top), *[len(s) for s in row])
frames = []
for i in range(n):
    im = Image.new("RGBA", (560, 170 + 230), BG)
    im.alpha_composite(pk2.draw(top[i % len(top)]), (0, 0))
    x = 0
    for s, p_ in zip(row, (pb2, ph2, pt2)):
        im.alpha_composite(p_.draw(s[i % len(s)]), (x, 170))
        x += p_.W
    frames.append(im)
save_gif(frames, out / "addons.gif")
for g in ("addons.gif", "addons_serpent.gif", "addons_flier.gif", "addons_host.gif", "addons_more.gif"):
    shutil.copy(out / g, root / "docs" / g)
print("done:", out)
