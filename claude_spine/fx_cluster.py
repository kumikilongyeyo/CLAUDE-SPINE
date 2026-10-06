"""Cluster-pays family for ``fx_recipe``: the win flow of a candy cluster slot, lifted from a reference clip (4x4 board in
a jelly frame): the board darkens around the winning cluster, a COMBO title punches (or zooms) in over a magenta flare,
the win amount drops into the win bar, the winning symbols turn to jelly cubes and vanish, and the scatters glint.

Everything is native Spine (one-shot keys on the shared piñata picture kit plus four pictures of its own: a cell
panel, a jelly cube and two plates standing in for the title and the amount art). Two parts LOOK better from After
Effects and the results say how (``ae_hint``): the glitter inside the cubes (template ``sparkle``) and the coin /
candy spray out of the bar (template ``burst``); bring them in with ``ae_fx_to_spine``, ``copies=`` for one glitter
per cell sharing the frames. Every picture is an ``art=`` role by name; ``gain`` / ``thick`` retune a texture pack.

Positions are relative to the anchor (default: the clip's board, anchor at the frame centre, 720 x 742 units).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .fx_pinata import PICS, PIC_ROLES, backout, bell
from .fx_recipes import RECIPES, ROLES, Ctx, _hexn, ease_out, hexa, smooth, times_dense

FPS = 30
COLS = [-187.0, -69.0, 50.0, 172.0]
ROWS = [207.0, 95.0, -17.0, -129.0]
CELL = 120.0
BAR = [0.0, -333.0, 492.0, 56.0]
COMBO = [9.0, 47.0]
AMOUNT = [9.0, -15.0]
BOARD = [[x, y] for y in ROWS for x in COLS]
CLUSTER = [[COLS[c], ROWS[r]] for c in (0, 1) for r in range(4)]
SCATTERS = [[COLS[3], ROWS[0]], [COLS[2], ROWS[2]]]
PINK, MAGENTA, GOLD, WHITE = "FF6FD8", "E040C8", "FFC94A", "FFFFFF"


# ------------------------------------------------------------------ the family's own pictures
def _rounded(w, h, r, fill, outline=None, width=0, pad=2):
    im = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle((8, 8, w * 4 - 8, h * 4 - 8), r * 4, fill=fill, outline=outline, width=width * 4)
    out = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    out.paste(im.resize((w, h), Image.LANCZOS), (pad, pad))
    return out


def _cube() -> Image.Image:
    n = 128
    im = Image.new("RGBA", (n * 4, n * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((8, 8, n * 4 - 8, n * 4 - 8), 104, fill=(226, 120, 230, 235), outline=(255, 220, 255, 255), width=12)
    d.rounded_rectangle((56, 48, n * 4 - 56, 176), 56, fill=(246, 178, 250, 200))
    d.rounded_rectangle((88, 72, 232, 104), 16, fill=(255, 255, 255, 210))
    d.ellipse((n * 4 - 136, n * 4 - 136, n * 4 - 80, n * 4 - 80), fill=(255, 255, 255, 170))
    out = Image.new("RGBA", (n + 4, n + 4), (0, 0, 0, 0))
    out.paste(im.resize((n, n), Image.LANCZOS), (2, 2))
    return out


def _plate(w, h, top, bottom, stroke) -> Image.Image:
    im = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((6, 6, w * 4 - 6, h * 4 - 6), h * 2 - 6, fill=stroke)
    d.rounded_rectangle((26, 26, w * 4 - 26, h * 4 - 26), h * 2 - 26, fill=bottom)
    d.rounded_rectangle((26, 26, w * 4 - 26, h * 2), h * 2 - 26, fill=top)
    out = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
    out.paste(im.resize((w, h), Image.LANCZOS), (2, 2))
    return out


OWN = {
    "panel": lambda: _rounded(128, 128, 22, (255, 255, 255, 255)),
    "jelly_cube": _cube,
    "combo_plate": lambda: _plate(256, 72, (196, 120, 255, 255), (140, 60, 230, 255), (60, 10, 110, 255)),
    "amount_plate": lambda: _plate(256, 64, (255, 236, 120, 255), (255, 176, 40, 255), (120, 50, 0, 255)),
}
CPICS = {**PICS, **OWN}
CPIC_ROLES = {**PIC_ROLES, "panel": "rounded cell panel, white (tinted dark to dim a cell)",
              "jelly_cube": "the jelly cube a winning symbol turns into (normal blend)",
              "combo_plate": "the COMBO title art (normal blend)", "amount_plate": "the win amount art (normal blend)"}
NORMAL = {"panel", "jelly_cube", "combo_plate", "amount_plate", "coin", "smoke_puff"}


def _s(c: Ctx, bone: str, pic: str, width: float, height: float | None = None, blend: str = "additive",
       color: str = "FFFFFFFF", ox: float = 0.0) -> str:
    path = f"fx/pinata_{pic}" if pic in PICS else f"fx/cluster_{pic}"     # kit pictures are shared with the piñata family
    nm = c.slot(bone, path, width, height=height, make=CPICS[pic], blend=blend, role=pic, stretch=height is not None,
                color=color, ox=ox)
    c.__dict__.setdefault("_pic", {})[nm] = pic
    return nm


def _finish(c: Ctx, P: dict, **extra) -> dict:
    gain, thick = dict(P.get("gain") or {}), dict(P.get("thick") or {})
    bad = [k for k in [*gain, *thick] if k not in CPICS]
    if bad:
        raise ValueError(f"gain/thick name unknown picture(s) {bad}; pictures: {sorted(CPICS)}")
    an = c.sk.animations.get(c.anim)
    for slot, pic in c.__dict__.get("_pic", {}).items():
        if pic in thick:
            att = c.sk.attachment(slot, "fx")
            wx, hy = (list(thick[pic]) + [1.0, 1.0])[:2]
            att.width, att.height = round(att.width * float(wx), 2), round(att.height * float(hy), 2)
            att.x, att.y = round(att.x * float(wx), 2), round(att.y * float(hy), 2)
        g = float(gain.get(pic, 1.0))
        if g != 1.0 and an is not None:
            for k in an.slots.get(slot, {}).get("rgba", []):
                k.color = k.color[:6] + "%02X" % max(0, min(255, round(int(k.color[6:8], 16) * g)))
    return c.result(**extra)


def _pts(P, key):
    return [(float(a), float(b)) for a, b in P[key]]


def _h(c: Ctx, col: str, a: float) -> str:
    return hexa(col, c.a(max(0.0, a)))


# ====================================================================== recipes
def cluster_dim(c: Ctx, P: dict) -> dict:
    """The cluster is found: every OTHER board cell darkens in 2 frames, the winning cells get a breathing rim glow and
    twinkles. Loops while the win shows."""
    D, CL = float(P["duration"]), float(P["cell"])
    col = _hexn(P["color"], WHITE)
    dim = _hexn(P["dim_color"], "1A0A2E")
    win = _pts(P, "cells")
    winset = {(round(x, 1), round(y, 1)) for x, y in win}
    others = [(x, y) for x, y in _pts(P, "board") if (round(x, 1), round(y, 1)) not in winset]
    dims, rims, stars = [], [], []
    for i, (x, y) in enumerate(others):
        b = c.bone(f"d{i}", x=x, y=y)
        dims.append(_s(c, b, "panel", CL * 1.02, blend="normal", color=dim + "FF"))
    rng = np.random.default_rng(c.seed + 3)
    for i, (x, y) in enumerate(win):
        b = c.bone(f"r{i}", x=x, y=y)
        rims.append(_s(c, b, "glow_soft", CL * 1.25))
        sb = c.bone(f"s{i}", b, float(rng.uniform(-0.35, 0.35)) * CL, float(rng.uniform(-0.35, 0.35)) * CL)
        stars.append((sb, _s(c, sb, "flare_star", 34.0), float(rng.uniform(0, 2 * math.pi))))
    c.show(dims + rims + [s for _, s, _ in stars], 0, None)
    ts = times_dense(0, D, FPS)
    per = D / max(1, round(D / 0.6))                   # breathing period: a whole number per loop
    DA = min(1.0, float(P["dim"]))
    rim = lambda t, i: 0.35 + 0.15 * math.sin(2 * math.pi * t / per + i)  # noqa: E731
    for s in dims:                                      # the LOOP holds full values: first frame == last frame
        c.color_keys(s, [0.0, D], lambda t: hexa(dim, DA))
    for i, s in enumerate(rims):
        c.color_keys(s, ts, lambda t, i=i: _h(c, col, rim(t, i)))
    for b, s, ph in stars:
        k = lambda t, ph=ph: max(0.0, math.sin(2 * math.pi * t / per + ph)) ** 6  # noqa: E731
        c.color_keys(s, ts, lambda t, k=k: _h(c, WHITE, k(t)))
        c.bone_keys(b, "scale", ts, lambda t, k=k: (0.4 + 0.8 * k(t),) * 2)
    # the fade-in lives in its own short animation (<loop>_in, 2-3 frames): play it, then the loop. Inside the loop it
    # would blink the dim off and on at every repeat.
    from .timeline import AnimBuilder
    intro = f"{c.anim}_in"
    ab = AnimBuilder(c.sk, intro, replace=True)
    TI = 0.08
    ti = times_dense(0, TI, FPS)
    for s in dims + rims + [s for _, s, _ in stars]:
        ab.slot_attachment(s, [(0.0, "fx")])
    for s in dims:
        ab.slot_color(s, [(t, hexa(dim, DA * smooth(t, 0.0, TI))) for t in ti], "linear")
    for i, s in enumerate(rims):
        ab.slot_color(s, [(t, _h(c, col, rim(0.0, i) * smooth(t, 0.0, TI))) for t in ti], "linear")
    for b, s, ph in stars:
        ab.slot_color(s, [(0.0, hexa(WHITE, 0.0)), (TI, _h(c, WHITE, max(0.0, math.sin(ph)) ** 6))], "linear")
    ab.event(0.0, "cluster_found")
    return _finish(c, P, duration=D, loop=D, intro=intro, intro_duration=TI, dimmed=len(dims), winners=len(win))


def _backdrop(c: Ctx, P: dict, t0: float, D: float, cx: float, cy: float):
    col = _hexn(P["color"], MAGENTA)
    b_gl, b_halo = c.bone("bloom", x=cx, y=cy), c.bone("halo", x=cx, y=cy)
    b_core, b_st = c.bone("core", x=cx + 40, y=cy + 10), c.bone("streak", x=cx, y=cy - 10)
    s_gl = _s(c, b_gl, "glow_soft", 520.0, height=340.0)
    s_halo = _s(c, b_halo, "glow_soft", 360.0, height=240.0)
    s_core = _s(c, b_core, "glow_core", 300.0)
    s_st = _s(c, b_st, "light_streak", 640.0, height=70.0)
    rng = np.random.default_rng(c.seed + 8)
    sp = []
    for i in range(6):
        b = c.bone(f"sp{i}", x=cx + float(rng.uniform(-200, 200)), y=cy + float(rng.uniform(-70, 70)))
        sp.append((b, _s(c, b, "flare_star", float(rng.uniform(22, 40))), float(rng.uniform(0, 2 * math.pi))))
    c.show([s_gl, s_halo, s_core, s_st] + [s for _, s, _ in sp], t0, D)
    ts = times_dense(0, D, FPS)
    on = lambda t: smooth(t, t0, t0 + 0.08)  # noqa: E731
    c.color_keys(s_gl, ts, lambda t: _h(c, col, 0.85 * on(t) * (0.9 + 0.1 * math.sin(6 * t))))
    c.color_keys(s_halo, ts, lambda t: _h(c, "FF4FC8", 0.9 * on(t)))
    c.color_keys(s_core, ts, lambda t: _h(c, PINK, 0.95 * on(t) * (0.85 + 0.15 * math.sin(9 * t + 1))))
    c.bone_keys(b_st, "scale", ts, lambda t: (0.3 + 0.7 * ease_out(max(0.0, t - t0) / 0.2), 1.0))
    c.color_keys(s_st, ts, lambda t: _h(c, "FF9AF0", 0.8 * on(t)))
    for b, s, ph in sp:
        k = lambda t, ph=ph: max(0.0, math.sin(2 * math.pi * t / 0.7 + ph)) ** 5  # noqa: E731
        c.color_keys(s, ts, lambda t, k=k: _h(c, WHITE, on(t) * k(t)))
        c.bone_keys(b, "scale", ts, lambda t, k=k: (0.3 + 0.9 * k(t),) * 2)


def combo_banner(c: Ctx, P: dict) -> dict:
    """COMBO title + win amount over a magenta flare. style=punch (COMBO 1: both punch in with overshoot) or zoom (COMBO
    2+: the title flies in from the camera, 3.2x -> 1x in ~4 frames, with ghost copies standing in for motion blur)."""
    D = 1.0
    TX, TY = (float(v) for v in P["title"])
    AX, AY = (float(v) for v in P["amount"])
    style = P["style"]
    if style not in ("punch", "zoom"):
        raise ValueError("combo_banner style must be punch | zoom")
    T1 = 0.14 if style == "zoom" else 0.05
    _backdrop(c, P, T1, D, (TX + AX) / 2, (TY + AY) / 2)
    ghosts = []
    if style == "zoom":
        for g in range(3, 0, -1):
            b = c.bone(f"ghost{g}")
            ghosts.append((g, b, _s(c, b, "combo_plate", 200.0, blend="normal")))
    bt, ba = c.bone("title"), c.bone("amount")
    st = _s(c, bt, "combo_plate", 200.0, blend="normal")
    sa = _s(c, ba, "amount_plate", 230.0, blend="normal")
    ts = times_dense(0, D, FPS * 2)
    c.bone_keys(bt, "translate", ts, lambda t: (TX, TY))
    c.bone_keys(ba, "translate", ts, lambda t: (AX, AY))
    if style == "punch":
        c.show([st, sa], 0.05, D)
        c.bone_keys(bt, "scale", ts, lambda t: (backout((t - 0.05) / 0.12, 2.6) if t > 0.05 else 0.0,) * 2)
        c.bone_keys(ba, "scale", ts, lambda t: (backout((t - 0.09) / 0.12, 2.6) if t > 0.09 else 0.0,) * 2)
    else:
        land = lambda t, lag=0.0: ease_out(min(max((t - lag) / T1, 0), 1), 2.2)  # noqa: E731

        def zscale(t, lag=0.0):
            return 3.2 - 2.2 * land(t, lag) + (0.08 * math.sin(math.pi * min(max((t - T1) / 0.1, 0), 1)) if t > T1 else 0.0)
        c.show([s for *_, s in ghosts], 0.0, T1 + 0.08)
        c.show([st], 0.0, D)
        c.show([sa], 0.1, D)
        c.bone_keys(bt, "scale", ts, lambda t: (zscale(t),) * 2)
        c.color_keys(st, ts, lambda t: _h(c, WHITE, 0.4 + 0.6 * land(t)))
        for g, b, s in ghosts:
            c.bone_keys(b, "translate", ts, lambda t: (TX, TY))
            c.bone_keys(b, "scale", ts, lambda t, g=g: (zscale(t, -0.025 * g) * (1 + 0.12 * g),) * 2)
            c.color_keys(s, ts, lambda t, g=g: _h(c, WHITE, 0.32 / g * (1 - smooth(t, T1 - 0.02, T1 + 0.08))))
        c.bone_keys(ba, "scale", ts, lambda t: (backout((t - 0.1) / 0.12, 2.6) if t > 0.1 else 0.0,) * 2)
    c.ab.event(c.T(T1), "combo_land")
    return _finish(c, P, duration=D * c.k, style=style, lands_at=c.T(T1))


def amount_to_bar(c: Ctx, P: dict) -> dict:
    """The win amount drops into the win bar (ease in, ~6 frames, shrinking), the bar blooms white, a shine sweeps it,
    coins burst up out of it and fall back (Spine). ae_hint: the clip's richer coin / candy spray (AE burst template).
    Event bar_hit = update the bar number."""
    D, T1 = 1.0, 0.26
    AX, AY = (float(v) for v in P["amount"])
    bx, by, bw, bh = (float(v) for v in P["bar"])
    b_am = c.bone("amount")
    s_am = _s(c, b_am, "amount_plate", 230.0, blend="normal")
    rng = np.random.default_rng(c.seed + 21)
    coins = []                                          # normal run (amount + coins), then the additive run
    for k in range(int(P["count"])):
        b = c.bone(f"coin{k}", x=bx + float(rng.uniform(-0.3, 0.3)) * bw, y=by)
        a = math.radians(float(rng.uniform(60, 120)))
        coins.append((b, _s(c, b, "coin", float(rng.uniform(26, 38)), blend="normal"), a, float(rng.uniform(380, 620)),
                      float(rng.uniform(0, 0.08)), float(rng.uniform(14, 22))))
    b_bl, b_sh, b_ln = c.bone("bloom", x=bx, y=by), c.bone("shine", rot=-18.0), c.bone("line", x=bx, y=by + bh * 0.5)
    s_bl = _s(c, b_bl, "glow_soft", bw * 1.15, height=bh * 3.0)
    s_sh = _s(c, b_sh, "shine_band", 120.0, height=bh * 1.8)
    s_ln = _s(c, b_ln, "light_streak", bw * 1.1, height=40.0)
    c.show([s_am], 0, T1 + 0.02)
    c.show([s_bl, s_sh, s_ln], T1 - 0.02, D)
    ts = times_dense(0, D, FPS * 2)
    u = lambda t: smooth(t, 0.0, T1) ** 1.7  # noqa: E731
    c.bone_keys(b_am, "translate", ts, lambda t: (AX + (bx - AX) * u(t), AY + (by - AY) * u(t)))
    c.bone_keys(b_am, "scale", ts, lambda t: (1.0 - 0.3 * u(t),) * 2)
    hit = lambda t: smooth(t, T1 - 0.02, T1 + 0.03) * math.exp(-max(0.0, t - T1) / 0.35)  # noqa: E731
    c.color_keys(s_bl, ts, lambda t: _h(c, "FFE6FF", 0.9 * hit(t)))
    c.color_keys(s_ln, ts, lambda t: _h(c, WHITE, hit(t)))
    c.bone_keys(b_sh, "translate", ts, lambda t: (bx - bw * 0.55 + bw * 1.1 * smooth(t, T1, T1 + 0.45), by))
    c.color_keys(s_sh, ts, lambda t: _h(c, WHITE, 0.9 * bell(t, T1, 0.05, 0.4)))
    g = -1400.0
    for b, s, a, sp, d, spin in coins:
        t0 = T1 + d
        tt = times_dense(t0, min(D, t0 + 0.6), FPS)
        c.show([s], t0, min(D, t0 + 0.6))
        c.bone_keys(b, "translate", tt, lambda t, a=a, sp=sp, t0=t0: (math.cos(a) * sp * (t - t0), math.sin(a) * sp * (t - t0) + 0.5 * g * (t - t0) ** 2))
        c.bone_keys(b, "scale", tt, lambda t, t0=t0, spin=spin: (math.cos(spin * (t - t0)), 1.0))
        c.color_keys(s, tt, lambda t, t0=t0: _h(c, WHITE, 1 - smooth(t, t0 + 0.4, t0 + 0.6)))
    c.ab.event(c.T(T1), "bar_hit")
    hint = dict(template="burst", params=dict(size=512, duration=0.9, n=26, color="FFC23A", color2="FF8A2A", particle=22,
                                              particle_var=0.45, speed=520, speed_var=0.35, angle=90, spread=110,
                                              gravity=1100, life=0.75, shape="dot", stretch=1.0, glow=0.6,
                                              center_x=0.5, center_y=0.78),
                mode="alpha", x=bx, y=by + 512 * 0.9 * 0.28, scale=0.9, start=c.T(T1 - 0.02), parent=c.group,
                note="the clip's coin / candy spray: ae_template burst with these params -> ae_fx_to_spine with these args "
                     "(animation = this one); drop count= to 0 once it is in")
    return _finish(c, P, duration=D * c.k, hit_at=c.T(T1), ae_hint=hint)


def jelly_pop(c: Ctx, P: dict) -> dict:
    """The winning symbols turn to jelly and vanish: a white puff swallows each symbol (hide it at the event jelly), a
    jelly cube pops in with twinkles, turns purple and shrinks away (jelly_gone), coins fly into the win bar.
    ae_hint: glitter inside every cube (AE sparkle), one sequence shared by all cells (ae_fx_to_spine copies=)."""
    D, CL = 1.0, float(P["cell"])
    T_CUBE, T_PURPLE, T_GONE = 0.08, 0.28, 0.42
    purple = _hexn(P["color"], "B060FF")
    cells = _pts(P, "cells")
    bx, by, bw, bh = (float(v) for v in P["bar"])
    rng = np.random.default_rng(c.seed + 11)
    puffs, cubes, tw, coins = [], [], [], []
    groups = []
    for i, (x, y) in enumerate(cells):
        g = c.bone(f"c{i}", x=x, y=y)
        groups.append(g)
        bc = c.bone(f"q{i}", g)
        cubes.append((bc, _s(c, bc, "jelly_cube", CL * 0.92, blend="normal")))
    for k in range(int(P["count"])):                       # coins: still in the normal run
        b = c.bone(f"coin{k}")
        x, y = cells[k % len(cells)]
        coins.append((b, _s(c, b, "coin", float(rng.uniform(34, 46)), blend="normal"), (x, y),
                      (bx + float(rng.uniform(-0.35, 0.35)) * bw, by), 0.06 + 0.025 * k, float(rng.uniform(0.3, 0.42))))
    for i, g in enumerate(groups):                          # the additive run: puffs and twinkles
        bp = c.bone(f"p{i}", g)
        puffs.append((bp, _s(c, bp, "glow_soft", CL * 1.5)))
        for j in range(int(P["twinkles"])):
            bt = c.bone(f"t{i}_{j}", g, float(rng.uniform(-0.3, 0.3)) * CL, float(rng.uniform(-0.3, 0.3)) * CL)
            tw.append((bt, _s(c, bt, "flare_star", float(rng.uniform(16, 28))), float(rng.uniform(0, 1))))
    ts = times_dense(0, D, FPS * 2)
    c.show([s for _, s in puffs], 0.0, T_CUBE + 0.12)
    c.show([s for _, s in cubes] + [s for _, s, _ in tw], T_CUBE, T_GONE + 0.04)
    for b, s in puffs:
        c.color_keys(s, ts, lambda t: _h(c, WHITE, smooth(t, 0.0, 0.04) * (1 - smooth(t, T_CUBE, T_CUBE + 0.1))))
        c.bone_keys(b, "scale", ts, lambda t: (0.6 + 0.5 * ease_out(t / 0.1),) * 2)
    for b, s in cubes:
        c.bone_keys(b, "scale", ts, lambda t: ((backout((t - T_CUBE) / 0.1, 2.2) if t > T_CUBE else 0.0) * (1 - 0.35 * smooth(t, T_PURPLE, T_GONE)),) * 2)
        c.color_keys(s, ts, lambda t: hexa(purple if t > T_PURPLE + 0.05 else "FFFFFF", c.a(1 - smooth(t, T_PURPLE + 0.04, T_GONE))))
    for b, s, ph in tw:
        k = lambda t, ph=ph: max(0.0, math.sin(2 * math.pi * (t - T_CUBE) / 0.18 + ph * 6.28)) ** 4  # noqa: E731
        c.color_keys(s, ts, lambda t, k=k: _h(c, WHITE, k(t) * (1 - smooth(t, T_PURPLE, T_GONE))))
        c.bone_keys(b, "rotate", ts, lambda t: 240.0 * t)
    for b, s, p0, p1, t0, tr in coins:
        tt = times_dense(t0, t0 + tr, FPS * 2)
        ctrl = ((p0[0] + p1[0]) / 2 + float(rng.uniform(-60, 60)), max(p0[1], p1[1]) + float(rng.uniform(60, 140)))
        c.show([s], t0, t0 + tr)

        def pos(t, p0=p0, p1=p1, ctrl=ctrl, t0=t0, tr=tr):
            v = ((t - t0) / tr) ** 1.3
            return ((1 - v) ** 2 * p0[0] + 2 * (1 - v) * v * ctrl[0] + v * v * p1[0],
                    (1 - v) ** 2 * p0[1] + 2 * (1 - v) * v * ctrl[1] + v * v * p1[1])
        c.bone_keys(b, "translate", tt, pos)
        c.bone_keys(b, "scale", tt, lambda t, t0=t0: (math.cos(18 * (t - t0)), 1.0))
    c.ab.event(c.T(0.0), "jelly")
    c.ab.event(c.T(T_GONE), "jelly_gone")
    (x0, y0), rest = cells[0], cells[1:]
    hint = dict(template="sparkle", params=dict(size=256, duration=1.0, color="FFD6F6", core_color="FFFFFF", count=9,
                                                min_star=0.07, max_star=0.17, spread=0.36),
                mode="additive", seq_mode="loop", x=x0, y=y0, scale=0.6, start=c.T(T_CUBE), until=c.T(T_GONE),
                parent=c.group, max_size=128, copies=[[x, y] for x, y in rest],
                note="glitter inside every cube: ae_template sparkle -> ae_fx_to_spine with these args (copies = one per other "
                     "cell, all sharing the frames); lower twinkles= to 0 once it is in")
    return _finish(c, P, duration=D * c.k, cells=len(cells), gone_at=c.T(T_GONE), ae_hint=hint)


def scatter_shine(c: Ctx, P: dict) -> dict:
    """Idle glint on scatters: a white comet streak sweeps across each (heading `angle`, ~0.3 s), a star winks at its
    head; each next scatter follows `stagger` later."""
    D = 1.0
    a = math.radians(float(P["angle"]))
    stag = float(P["stagger"])
    for i, (x, y) in enumerate(_pts(P, "cells")):
        t0, tr = 0.1 + stag * i, 0.32
        g = c.bone(f"g{i}", x=x, y=y)
        b = c.bone(f"comet{i}", g)
        s = _s(c, b, "energy_trail", 230.0, height=56.0, ox=-95.0)
        bs = c.bone(f"star{i}", g)
        ss = _s(c, bs, "flare_star", 70.0)
        c.show([s, ss], t0, min(D, t0 + tr + 0.05))
        tt = times_dense(t0, min(D, t0 + tr + 0.05), FPS * 2)
        path = lambda t, t0=t0, tr=tr: -70 + 190 * smooth(t, t0, t0 + tr)  # noqa: E731
        c.bone_keys(b, "translate", tt, lambda t, path=path: (math.cos(a) * path(t), math.sin(a) * path(t)))
        c.bone_keys(b, "rotate", tt, lambda t: math.degrees(a))
        c.color_keys(s, tt, lambda t, t0=t0, tr=tr: _h(c, WHITE, 0.95 * bell(t, t0, 0.06, tr)))
        c.bone_keys(bs, "translate", tt, lambda t, path=path: (math.cos(a) * path(t), math.sin(a) * path(t)))
        c.bone_keys(bs, "rotate", tt, lambda t: 200.0 * t)
        c.color_keys(ss, tt, lambda t, t0=t0, tr=tr: _h(c, WHITE, bell(t, t0 + 0.05, 0.06, tr * 0.6)))
    return _finish(c, P, duration=D * c.k)


# ------------------------------------------------------------------ registry
_GT = dict(gain=({}, "{picture: alpha multiplier}, e.g. {glow_soft: 0.5} for a fuller texture pack"),
           thick=({}, "{picture: [width x, height x]} for thin stretched pictures"))


def _o(**kw):
    return {**kw, **_GT}


RECIPES.update({
    "cluster_dim": dict(
        fn=cluster_dim, duration=1.2, kind="loop", color=WHITE, normal_blend=True,
        summary="Cluster win found: every OTHER board cell darkens (dark panels, normal blend), the winning cells get a "
                "breathing rim glow and twinkles. Two animations: <name>_in (the 2-frame fade-in, event cluster_found) then "
                "<name> (a seamless loop while the win shows).",
        anchor="Board centre; cells relative to it.",
        options=_o(cells=(CLUSTER, "[[x, y], ...] the winning cells"), board=(BOARD, "[[x, y], ...] every board cell"),
                   cell=(CELL, "cell size"), dim=(0.72, "how dark the other cells get"), dim_color=("1A0A2E", "dim tint"))),
    "combo_banner": dict(
        fn=combo_banner, duration=1.0, kind="one-shot", color=MAGENTA, normal_blend=True,
        summary="COMBO title + win amount over a magenta bloom, lens streak and sparkles. style=punch (both punch in with "
                "overshoot) or zoom (the title flies in from the camera in ~4 frames; ghost copies stand in for motion blur). "
                "Play it over cluster_dim: additive magenta over a bright magenta board washes out. Event combo_land.",
        anchor="Board centre; title / amount relative to it.",
        options=_o(style=("punch", "punch | zoom"), title=(COMBO, "[x, y] title centre"), amount=(AMOUNT, "[x, y] amount centre"))),
    "amount_to_bar": dict(
        fn=amount_to_bar, duration=1.0, kind="one-shot", color=GOLD, count=8, normal_blend=True,
        summary="The win amount drops into the win bar (ease in, shrinking), the bar blooms white, a shine sweeps it, coins "
                "burst up and fall back. ae_hint = the clip's coin / candy spray (AE burst). Event bar_hit.",
        anchor="Board centre; amount / bar relative to it.",
        options=_o(amount=(AMOUNT, "[x, y] where the amount starts"), bar=(BAR, "[x, y, w, h] the win bar"))),
    "jelly_pop": dict(
        fn=jelly_pop, duration=1.0, kind="one-shot", color="B060FF", count=10, normal_blend=True,
        summary="Winning symbols turn to jelly and vanish: white puff (hide the symbol at event jelly), a jelly cube pops in "
                "with twinkles, turns purple and shrinks away (jelly_gone), coins fly into the bar. ae_hint = AE glitter in "
                "every cube, one shared sequence (ae_fx_to_spine copies=).",
        anchor="Board centre; cells / bar relative to it.",
        options=_o(cells=(CLUSTER, "[[x, y], ...] the winning cells"), bar=(BAR, "[x, y, w, h] the win bar"),
                   cell=(CELL, "cell size"), twinkles=(2, "Spine twinkles per cube (0 once the AE glitter is in)"))),
    "scatter_shine": dict(
        fn=scatter_shine, duration=1.0, kind="one-shot", color=WHITE,
        summary="Idle glint on scatters: a white comet streak sweeps across each, a star winks at its head, staggered.",
        anchor="Board centre; cells relative to it.",
        options=_o(cells=(SCATTERS, "[[x, y], ...] the scatters"), angle=(140.0, "streak heading, degrees (140 = up-left)"),
                   stagger=(0.12, "seconds between scatters"))),
})
CLUSTER_RECIPES = ("cluster_dim", "combo_banner", "amount_to_bar", "jelly_pop", "scatter_shine")
for _n in CLUSTER_RECIPES:
    ROLES[_n] = dict(CPIC_ROLES)
    RECIPES[_n]["roles"] = ROLES[_n]
