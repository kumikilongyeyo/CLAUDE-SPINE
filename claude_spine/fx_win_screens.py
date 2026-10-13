"""Win-screen family for ``fx_recipe``: the cascade-win moments and the Big / Mega / Total Win screens of a casual
slot, rebuilt from a reference clip (a hot-air-balloon slot: a cascade win, then Big Win -> Mega Win -> Total Win).

Cell / board moments (placed on a cell or a label):
    ornate_cell_glow   yellow light PAINTED behind a winning symbol (normal blend: a lozenge + a round skirt), an
                       ornate lozenge outline of light, rising motes; grows in 0.17 s, breathes, dims before the pop
    starburst_pop      the winner vanishes: translucent square flash, two starbursts of thin rays, a star core, drifting
                       glints (0.45 s)
    blowout_flash      a symbol that stays (a wild) blows out white for 0.13 s while it re-forms
    label_glint        a label that just changed: warm flare + streak + a light band sweeping across it (0.4 s)
    echo_stamp         a label stamps echo copies down under itself, then one copy drops into a target (art role)
    ghost_pop          a number lands: pops 1.42 -> 0.97 -> 1.0 while a ghost copy swells and fades (art role)
    fire_boost_flare   the Spine half of a "multiplier fire boost": the warm flare on the bar; the fire / smoke column
                       is After Effects (``ae_hint``: the fire + magic_smoke templates, see the guide)
Screens (anchor = the win number's centre):
    win_screen_intro   board dims, a full-screen colour wash floods and clears, a glow burst + ray flare + flung
                       sparks bloom behind the number (1.0 s)
    win_screen_glow    the hold behind a count-up: the glow settles from the intro (``settle`` s) into a breathing glow,
                       a slowly turning fan of streaks, twinkling star dust (loop the tail)
    win_upgrade_flash  tier upgrade (Big -> Mega): flash + star rays at the number, the screen washes A -> B -> A
    beam_sweep         broad soft beams turning behind a title (one beam step per loop = seamless) + glow + dust
    sunburst_intro     a glow gathers on the counter, a bloom fills the screen and settles (0.45 s)
    sunburst_glow      the Total Win sunburst: warm normal-blend light (outer + sun), white-hot core, two counter-turning
                       flickering fans of thin rays, sparkles (seamless loop)
    face_flash         a light that fills one object's face (a gem: shape plate, a coin: shape disc) on a period, with a
                       halo and an optional star glint: chain two with ``delay`` for a gem-then-coin glint

Rules as the other families: procedural textures only (white, coloured by slot colour), one group bone per recipe at
the anchor (its scale = ``scale``), keys are dense linear samples of closed-form curves, every colour from params.
Units = the reference clip's pixels on an 800 x 1396 portrait screen (a ~420-wide subject is a 150-px cell here, so
cell recipes are sized for that; scale to your cells).
"""
from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .fx_recipes import RECIPES, ROLES, Ctx, _hexn, hexa


# ------------------------------------------------------------------ textures (white light, alpha = shape)
def _grid(n, m=None):
    m = m or n
    y, x = np.mgrid[0:m, 0:n].astype(np.float32)
    return (x - (n - 1) / 2) / ((n - 1) / 2), (y - (m - 1) / 2) / ((m - 1) / 2)


def _rgba(a):
    a = np.clip(a, 0, 1)
    out = np.ones(a.shape + (4,), np.float32)
    out[..., 3] = a
    return Image.fromarray(np.round(out * 255).astype(np.uint8), "RGBA")


def _edge(x, y, w=0.06):
    return np.clip((1 - np.hypot(x, y)) / w, 0, 1)


def t_glow(n=256, sigma=0.42):
    x, y = _grid(n)
    return _rgba(np.exp(-(np.hypot(x, y) / sigma) ** 2) * _edge(x, y))


def t_glow_hot(n=256):
    x, y = _grid(n)
    d = np.hypot(x, y)
    a = 0.55 * np.exp(-(d / 0.16) ** 2) + 0.45 * np.exp(-(d / 0.5) ** 2)
    return _rgba(a / a.max() * _edge(x, y))


def t_square(n=256, half=0.52, corner=0.16, soft=0.30):
    x, y = _grid(n)
    qx, qy = np.abs(x) - (half - corner), np.abs(y) - (half - corner)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - corner
    a = np.where(d < 0, 1.0, np.exp(-(d / soft) ** 2))
    a *= np.clip((1 - np.maximum(np.abs(x), np.abs(y))) / 0.08, 0, 1)
    return _rgba(a)


def t_diamond(n=256, r=0.42, soft=0.30):
    x, y = _grid(n)
    d = np.abs(x) + np.abs(y)
    a = np.where(d < r, 1.0, np.exp(-((d - r) / soft) ** 2))
    a *= np.clip((1 - np.maximum(np.abs(x), np.abs(y))) / 0.08, 0, 1)
    return _rgba(a)


def t_ornament(n=512):
    """lozenge with ogee tips round a ring, small curls by each tip: an ornate frame of light"""
    S = 2 * n
    im = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(im)
    c = S / 2
    pts = []
    for i in range(721):
        th = 2 * math.pi * i / 720
        k = (th % (math.pi / 2)) - math.pi / 4
        to_axis = math.pi / 4 - abs(k)
        tip = max(0.0, 1 - to_axis / 0.42) ** 2.2
        scal = 0.035 * math.cos(4 * th) ** 2
        r = 0.36 + 0.115 * tip - scal
        pts.append((c + r * c * math.cos(th), c + r * c * math.sin(th)))
    d.line(pts, fill=255, width=int(S * 0.008))
    rr = 0.27 * c
    d.ellipse([c - rr, c - rr, c + rr, c + rr], outline=200, width=int(S * 0.006))
    for k in range(4):
        th = k * math.pi / 2
        for s in (-1, 1):
            a0 = th + s * 0.33
            px, py = c + 0.40 * c * math.cos(a0), c + 0.40 * c * math.sin(a0)
            rc = 0.045 * c
            d.arc([px - rc, py - rc, px + rc, py + rc], 0, 300, fill=170, width=int(S * 0.005))
    im = im.resize((n, n), Image.LANCZOS)
    line = np.asarray(im, np.float32) / 255
    halo = np.asarray(im.filter(ImageFilter.GaussianBlur(n * 0.012)), np.float32) / 255
    return _rgba(np.clip(line + 1.6 * halo, 0, 1))


def t_rays(n=512, rays=16, seed=3, width=0.016):
    """thin tapered rays of uneven length from the centre (a starburst)"""
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    d = np.hypot(x, y) + 1e-6
    th = np.arctan2(y, x)
    a = np.zeros_like(d)
    for i in range(rays):
        ang = 2 * math.pi * i / rays + rng.uniform(-0.12, 0.12)
        ln = rng.uniform(0.55, 0.98)
        wd = width * rng.uniform(0.7, 1.4)
        dth = np.angle(np.exp(1j * (th - ang)))
        perp = np.abs(dth) * d
        taper = np.clip(1 - d / ln, 0, 1) ** 0.8
        a = np.maximum(a, np.exp(-(perp / (wd * (0.35 + 0.65 * taper + 0.2))) ** 2) * taper * (d > 0.02))
    a = np.maximum(a, np.exp(-(d / 0.07) ** 2))
    return _rgba(a * _edge(x, y))


def t_fan(n=1024, rays=120, seed=11):
    """dense sunburst: many thin rays of random length and width"""
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    d = np.hypot(x, y) + 1e-6
    th = np.arctan2(y, x)
    a = np.zeros_like(d)
    for i in range(rays):
        ang = rng.uniform(-math.pi, math.pi)
        ln = rng.uniform(0.35, 1.0)
        wd = rng.uniform(0.003, 0.009)
        b = rng.uniform(0.35, 1.0)
        perp = np.abs(np.angle(np.exp(1j * (th - ang)))) * d
        a += b * np.exp(-(perp / (wd + 0.004 * d)) ** 2) * np.clip(1 - d / ln, 0, 1) ** 1.1
    a *= np.clip(d / 0.10, 0, 1) ** 0.5
    return _rgba(np.clip(a, 0, 1) * _edge(x, y))


def t_beams(n=512, beams=7, seed=5):
    """a few broad soft beams"""
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    d = np.hypot(x, y) + 1e-6
    th = np.arctan2(y, x)
    a = np.zeros_like(d)
    for i in range(beams):
        ang = 2 * math.pi * i / beams + rng.uniform(-0.25, 0.25)
        wd = rng.uniform(0.05, 0.12)
        b = rng.uniform(0.5, 1.0)
        dth = np.abs(np.angle(np.exp(1j * (th - ang))))
        a += b * np.exp(-(dth / wd) ** 2) * np.clip(1 - d, 0, 1) ** 0.7
    a *= np.clip(d / 0.15, 0, 1)
    return _rgba(np.clip(a, 0, 1) * _edge(x, y))


def t_star4(n=128, thin=0.045):
    x, y = _grid(n)
    d = np.hypot(x, y)
    rays = np.exp(-np.abs(x) / thin) * np.clip(1 - np.abs(y), 0, 1) ** 1.6 + \
        np.exp(-np.abs(y) / thin) * np.clip(1 - np.abs(x), 0, 1) ** 1.6
    return _rgba(np.clip(rays + np.exp(-(d / 0.14) ** 2), 0, 1) * _edge(x, y, 0.1))


def t_streak(w=512, h=64):
    x, y = _grid(w, h)
    return _rgba(np.exp(-(y / 0.22) ** 2) * np.clip(1 - np.abs(x), 0, 1) ** 1.5)


def t_dot(n=48):
    x, y = _grid(n)
    return _rgba(np.exp(-(np.hypot(x, y) / 0.4) ** 2) * _edge(x, y, 0.15))


def t_white(n=16):
    return _rgba(np.ones((n, n), np.float32))


def t_band(w=128, h=256):
    x, y = _grid(w, h)
    return _rgba(np.exp(-(x / 0.28) ** 2) * np.clip(1 - np.abs(y) ** 4, 0, 1))


def t_disc(n=256, r=0.9, feather=0.08):
    """flat disc with a short soft edge, hotter toward the upper left: fills a round face (a coin)"""
    x, y = _grid(n)
    a = np.clip((r - np.hypot(x, y)) / feather + 0.5, 0, 1)
    return _rgba(a * (0.75 + 0.25 * np.clip(1 - np.hypot(x + 0.3, y + 0.3) / 1.2, 0, 1)))


def t_plate(n=256, half=0.82, corner=0.12, feather=0.06):
    """flat rounded square with a short soft edge: fills a cut gem face"""
    x, y = _grid(n)
    qx, qy = np.abs(x) - (half - corner), np.abs(y) - (half - corner)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - corner
    a = np.clip(-d / feather + 0.5, 0, 1)
    return _rgba(a * (0.7 + 0.3 * np.clip(1 - np.hypot(x + 0.35, y + 0.35) / 1.3, 0, 1)))


def t_label(w=256, h=64):
    """placeholder for a label (the game binds its own picture through art=): a soft pill of light"""
    x, y = _grid(w, h)
    qx = np.maximum(np.abs(x) - 0.7, 0) / 0.3
    a = np.clip((1 - np.hypot(qx, y)) / 0.15, 0, 1)
    return _rgba(a * 0.85)


PICS = {
    "glow": t_glow, "glow_hot": t_glow_hot, "square": t_square, "diamond": t_diamond, "ornament": t_ornament,
    "rays": t_rays, "rays20": lambda: t_rays(seed=5, rays=22, width=0.011), "fan": t_fan,
    "fan_b": lambda: t_fan(rays=90, seed=23), "beams": t_beams, "star4": t_star4, "streak": t_streak,
    "dot": t_dot, "white": t_white, "band": t_band, "disc": t_disc, "plate": t_plate, "label": t_label,
}


# ------------------------------------------------------------------ helpers over Ctx
def _sl(c: Ctx, bone: str, pic: str, w: float, h: float | None = None, color: str = "FFFFFF", blend="additive",
        role: str | None = None) -> str:
    return c.slot(bone, f"fx/winscr_{pic}", w, color=hexa(color, 0), height=h, make=PICS[pic], blend=blend, role=role,
                  stretch=(role == "label"))      # a label picture is stretched to the label box


def _al(c: Ctx, slot: str, rgb: str, pts) -> None:
    """(u, alpha) keys at design time u, fixed colour; alpha scaled by intensity"""
    c.ab.slot_color(slot, _dedupe([(c.T(t), hexa(rgb, c.a(a))) for t, a in pts]), "linear")


def _kf(c: Ctx, bone: str, tl: str, pts, ease="linear") -> None:
    """bone keys at design time: (u, v) / (u, x, y) [, ease]"""
    out = []
    for p in pts:
        p = list(p)
        e = p.pop() if isinstance(p[-1], str) else ease
        t, vals = p[0], p[1:]
        if tl == "scale" and len(vals) == 1:
            vals = [vals[0], vals[0]]
        out.append((c.T(t), *vals, e))
    c.ab.bone(bone, tl, _dedupe(out), ease)


def _dedupe(pts):
    out = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < 1e-6:
            out[-1] = p
        else:
            out.append(p)
    return out


def _osc(t0, t1, period, lo, hi, phase=0.0, step=1 / 15):
    n = max(2, int(round((t1 - t0) / step)) + 1)
    return [(round(t0 + (t1 - t0) * i / (n - 1), 4),
             lo + (hi - lo) * (0.5 + 0.5 * math.sin(2 * math.pi * ((t1 - t0) * i / (n - 1)) / period + phase)))
            for i in range(n)]


def _mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (0, 2, 4)]
    b = [int(c2[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(a, b))


def _dust(c: Ctx, n: int, box, color: str, T: float, size=(8, 16), seed=3, rise=40.0, peak=0.9):
    """twinkling star dust in box [x0, y0, x1, y1] (anchor space, y up), each mote on its own looping life"""
    rnd = random.Random(seed)
    x0, y0, x1, y1 = box
    for i in range(n):
        px, py = rnd.uniform(x0, x1), rnd.uniform(y0, y1)
        b = c.bone(f"dust{i}", None, px, py)
        s = _sl(c, b, "star4" if i % 3 else "dot", rnd.uniform(*size), color=color)
        c.show([s], 0, None)
        life = rnd.uniform(0.6, 1.1)
        ph = rnd.uniform(0, T)
        per = T / max(1, round(T / (life + 0.35)))
        starts = [(ph + k * per) % T for k in range(int(round(T / per)))]

        def f(t, starts=starts, life=life):        # twinkle lives wrap round the loop, so f(0) == f(T)
            v = 0.0
            for t0 in starts:
                for sh in (-T, 0.0, T):
                    u = (t - t0 - sh) / life
                    if 0 <= u <= 1:
                        v = max(v, peak * (u / 0.35 if u < 0.35 else (1 - u) / 0.65))
            return v
        ts = {0.0, T}
        for t0 in starts:
            for u in (0.0, 0.35 * life, life):
                ts.add(round((t0 + u) % T, 4))
        pts = [(t, f(t)) for t in sorted(ts)]
        pts[-1] = (T, pts[0][1])
        _al(c, s, color, pts)
        _kf(c, b, "translate", [(0, 0, -rise / 2), (T, rnd.uniform(-10, 10), rise / 2)])  # keys are setup-relative


# ------------------------------------------------------------------ cell / board moments
def ornate_cell_glow(c: Ctx, P: dict) -> dict:
    col, line = _hexn(P["color"], "FFE63C"), _hexn(P["line_color"], "FFF4A8")
    T, S = 1.0, float(P["size"]) / 150.0
    g = c.bone("g")
    soft = _sl(c, g, "glow", 360 * S, color=col, blend="normal", role="paint")
    dia = _sl(c, g, "diamond", 270 * S, color=col, blend="normal")
    hot = _sl(c, g, "glow_hot", 200 * S, color=line)
    ob = c.bone("orn", g)
    orn = _sl(c, ob, "ornament", 236 * S, color=line, role="frame")
    c.show([soft, dia, hot, orn], 0, T if P["off"] else None)
    _kf(c, g, "scale", [(0, 0.8, "cubic_out"), (0.17, 1.0), (T, 1.0)])
    br = _osc(0.17, 0.7, 0.5, 0.0, 1.0)
    fade = [(0.85, 0.55), (T, 0.25)]

    def env(lo, hi):
        return [(0, 0)] + [(t, lo + (hi - lo) * v) for t, v in br] + [(t, lo * k) for t, k in fade]
    _al(c, soft, col, env(0.68, 0.8))
    _al(c, dia, col, env(0.8, 0.92))
    _al(c, hot, line, env(0.25, 0.4))
    _al(c, orn, line, env(0.75, 1.0))
    _kf(c, ob, "rotate", [(0, -8, "cubic_out"), (0.17, 0)])
    rnd = random.Random(4 + c.seed - 7)
    for i in range(int(P["count"])):
        bx, by = rnd.uniform(-60, 60) * S, rnd.uniform(-65, 35) * S
        b = c.bone(f"mote{i}", g, bx, by)
        s = _sl(c, b, "star4" if i % 2 else "dot", rnd.uniform(10, 18) * S, color=line)
        c.show([s], 0, T if P["off"] else None)
        t0, life = rnd.uniform(0.05, 0.4), rnd.uniform(0.4, 0.6)
        pts, tt = [(0, 0)], t0
        while tt < T - 0.05:
            pts += [(round(tt, 3), 0), (round(tt + life * 0.3, 3), 0.9), (round(min(tt + life, T), 3), 0)]
            tt += life + rnd.uniform(0.05, 0.2)
        _al(c, s, line, pts)
        _kf(c, b, "translate", [(0, 0, -10 * S), (T, rnd.uniform(-8, 8) * S, 30 * S)])
    return c.result(duration=T, loop=[0.17, 0.7])


def starburst_pop(c: Ctx, P: dict) -> dict:
    col, hot = _hexn(P["color"], "FFB43A"), _hexn(P["hot_color"], "FFF6D8")
    glint = _hexn(P["glint_color"], "FFF4A8")
    S = float(P["size"]) / 150.0
    g = c.bone("g")
    sq = _sl(c, g, "square", 158 * S, color=col)
    gl = _sl(c, g, "glow", 300 * S, color=col)
    rb = c.bone("rays", g)
    r1 = _sl(c, rb, "rays20", 400 * S, color=col, role="rays")
    rb2 = c.bone("rays2", g, rot=9)
    r2 = _sl(c, rb2, "rays", 330 * S, color=col)
    cb = c.bone("core", g)
    core = _sl(c, cb, "star4", 120 * S, color=hot)
    st = _sl(c, cb, "streak", 230 * S, 22 * S, color=hot)
    c.show([sq, gl, r1, r2, core, st], 0, 0.3)
    _al(c, sq, col, [(0, 0.3), (0.06, 0.2), (0.15, 0)])
    _al(c, gl, col, [(0, 0.38), (0.08, 0.28), (0.2, 0)])
    _kf(c, rb, "scale", [(0, 0.5, "cubic_out"), (0.12, 1.0), (0.2, 1.08)])
    _kf(c, rb, "rotate", [(0, 0), (0.2, 6)])
    _al(c, r1, col, [(0, 0.3), (0.03, 0.55), (0.1, 0.45), (0.18, 0)])
    _kf(c, rb2, "scale", [(0, 0.4, "cubic_out"), (0.1, 0.95), (0.2, 1.05)])
    _kf(c, rb2, "rotate", [(0, 0), (0.2, -5)])
    _al(c, r2, col, [(0, 0.35), (0.05, 0.4), (0.16, 0)])
    _kf(c, cb, "scale", [(0, 0.6, "cubic_out"), (0.08, 1.0), (0.18, 0.8)])
    _al(c, core, hot, [(0, 0.2), (0.05, 0.6), (0.12, 0.4), (0.2, 0)])
    _al(c, st, hot, [(0, 0), (0.06, 0.7), (0.14, 0.3), (0.2, 0)])
    rnd = random.Random(9 + c.seed - 7)
    for i in range(int(P["count"])):
        ang = rnd.uniform(0, 6.283)
        rr = rnd.uniform(35, 75) * S
        x0, y0 = rr * 0.5 * math.cos(ang), rr * 0.5 * math.sin(ang)
        b = c.bone(f"glint{i}", g, x0, y0)
        pic = "streak" if i % 3 == 0 else ("star4" if i % 3 == 1 else "dot")
        w = 34 * S if pic == "streak" else rnd.uniform(7, 13) * S
        s = _sl(c, b, pic, w, 4 * S if pic == "streak" else None, color=glint)
        t0 = rnd.uniform(0.12, 0.18)
        c.show([s], t0, 0.45)
        _al(c, s, glint, [(t0, 0), (t0 + 0.04, 0.85), (0.45, 0)])
        _kf(c, b, "translate", [(t0, 0, 0), (0.45, rr * 0.5 * math.cos(ang), rr * 0.5 * math.sin(ang) + 10 * S)],
            "cubic_out")
    return c.result(glints=int(P["count"]))


def blowout_flash(c: Ctx, P: dict) -> dict:
    col = _hexn(P["color"], "FFF6D8")
    w, h = (float(v) for v in P["size"])
    g = c.bone("g")
    bl = _sl(c, g, "glow_hot", w, h, color=col, role="glow")
    st = _sl(c, g, "star4", w * 1.27, color=col)
    c.show([bl, st], 0.06, 0.2)
    _al(c, bl, col, [(0.06, 0), (0.1, 0.9), (0.14, 0.8), (0.19, 0)])
    _al(c, st, col, [(0.06, 0), (0.1, 0.5), (0.18, 0)])
    _kf(c, g, "scale", [(0.06, 0.7, "cubic_out"), (0.1, 1.0), (0.19, 1.08)])
    return c.result()


def label_glint(c: Ctx, P: dict) -> dict:
    col = _hexn(P["color"], "FFE7A0")
    w, h = (float(v) for v in P["size"])
    g = c.bone("g")
    fl = _sl(c, g, "glow_hot", w * 1.35, h, color=col)
    st = _sl(c, g, "streak", w * 1.25, h * 0.22, color=col)
    sb = c.bone("sweep", g, -w * 0.47)
    sr = c.bone("tilt", sb, rot=-18)
    sw = _sl(c, sr, "band", w * 0.26, h * 0.75, color=col, role="band")
    c.show([fl, st, sw], 0, 0.42)
    _al(c, fl, col, [(0, 0), (0.05, 0.7), (0.4, 0)])
    _al(c, st, col, [(0, 0), (0.05, 0.8), (0.22, 0)])
    _kf(c, sb, "translate", [(0, 0, 0), (0.3, w * 0.94, 0)], "quad_in_out")
    _al(c, sw, col, [(0, 0), (0.04, 0.7), (0.26, 0.6), (0.3, 0)])
    return c.result()


def echo_stamp(c: Ctx, P: dict) -> dict:
    w, h = (float(v) for v in P["size"])
    drop = float(P["drop"])
    g = c.bone("g")
    echoes = []
    for k in (3, 2, 1):
        b = c.bone(f"echo{k}", g)
        s = _sl(c, b, "label", w, h, blend="normal", role="label")
        echoes.append((k, b, s))
    for k, b, s in echoes:
        t0 = 0.03 * k
        c.show([s], t0, 0.24)
        _kf(c, b, "translate", [(t0, 0, 0), (t0 + 0.06, 0, -7 * k), (0.2, 0, -7 * k), (0.24, 0, -3 * k)], "quad_out")
        _al(c, s, "FFFFFF", [(t0, 0.55), (0.16, 0.4), (0.24, 0)])
    fb = c.bone("fly", g)
    fs = _sl(c, fb, "label", w, h, blend="normal", role="label")
    c.show([fs], 0.23, 0.40)
    _kf(c, fb, "translate", [(0.23, 0, 0, "quad_in"), (0.40, 0, -drop)])
    _kf(c, fb, "scale", [(0.23, 1.0), (0.40, 1.12)])
    _al(c, fs, "FFFFFF", [(0.23, 1.0), (0.33, 0.9), (0.40, 0.4)])
    return c.result(label_slots=[s for _, _, s in echoes] + [fs])


def ghost_pop(c: Ctx, P: dict) -> dict:
    w, h = (float(v) for v in P["size"])
    g = c.bone("g")
    gb = c.bone("ghost", g)
    gs = _sl(c, gb, "label", w, h, blend="normal", role="label")
    lb = c.bone("label", g)
    ls = _sl(c, lb, "label", w, h, blend="normal", role="label")
    c.show([gs, ls], 0, 0.4)
    _kf(c, lb, "scale", [(0, float(P["pop"]), "cubic_out"), (0.13, 0.97, "sine_in_out"), (0.2, 1.0), (0.4, 1.0)])
    _al(c, ls, "FFFFFF", [(0, 0.69), (0.07, 1.0), (0.4, 1.0)])
    _kf(c, gb, "scale", [(0, 1.05, "cubic_out"), (0.33, float(P["ghost"]))])
    _al(c, gs, "FFFFFF", [(0, 0), (0.04, 0.55), (0.33, 0)])
    return c.result(label_slots=[gs, ls])


def fire_boost_flare(c: Ctx, P: dict) -> dict:
    col = _hexn(P["color"], "FF9426")
    D = float(P["duration"])
    g = c.bone("g")
    fl = _sl(c, g, "glow", 460, 200, color=col, role="flare")
    c.show([fl], 0, D)
    _al(c, fl, col, [(0, 0), (0.1, 0.55), (D * 0.59, 0.5), (D, 0)])
    return c.result(duration=D, ae_hint={
        "fire": {"template": "fire", "params": dict(width=320, height=448, duration=1, fps=30, hot="FFF6C8",
                                                       mid="FFA23C", cool="E8582A", scale=60, rise=380, lick=0.35,
                                                       flicker=0.25, body=0.55, taper=1.3, flame_height=1.1,
                                                       threshold=0.12, softness=0.85, alpha_cut=0.12, core=0.45,
                                                       turbulence=24, glow=0.8, loop=True, seed=3, edge_fade=0.2,
                                                       contrast=55),
                 "to_spine": dict(mode="alpha", blend="additive", seq_mode="loop", scale=0.95, y=183,
                                  alpha=[(0, 0), (0.08, 0.3), (0.45, 0.32), (D, 0)],
                                  bone_scale=[(0, 1.1, 0.2), (0.25, 1.4, 0.9), (0.6, 1.45, 1.0), (D, 1.5, 1.05)])},
        "smoke": {"template": "magic_smoke", "params": dict(width=448, height=640, duration=1.5, fps=30, luminous=True,
                                                            color="FF7A1E", light="FFE8A0", rise=260, scale=130,
                                                            threads=0.35, curl=60, fine_curl=24, swirl=14,
                                                            spread=0.42, height_fade=0.9, density=1, glow=0.8,
                                                            motes=10, seed=5),
                  "to_spine": dict(mode="additive", tintable=True, tint=col, seq_mode="loop", scale=1.15, y=195.5,
                                   alpha=[(0, 0), (0.1, 0.75), (0.5, 0.8), (D, 0)],
                                   bone_scale=[(0, 1.1, 0.35), (0.3, 1.35, 1.0), (D, 1.45, 1.1)])},
        "note": "both play BEHIND the bar's labels; pass parent=<this recipe's group bone>"})


# ------------------------------------------------------------------ the win screens
def win_screen_intro(c: Ctx, P: dict) -> dict:
    col, core, wash, dim = (_hexn(P["color"], "2ED2FF"), _hexn(P["core_color"], "E6FFFF"),
                            _hexn(P["wash_color"], "2840FF"), _hexn(P["dim_color"], "0A0A30"))
    sw, sh = (float(v) for v in P["screen"])
    ox, oy = (float(v) for v in P["screen_offset"])
    scr = c.bone("screen", None, ox, oy)
    dm = _sl(c, scr, "white", sw, sh, color=dim, blend="normal")
    ws = _sl(c, scr, "white", sw, sh, color=wash, blend="normal")
    c.show([dm], 0, 0.2)
    c.show([ws], 0.08, 0.45)
    _al(c, dm, dim, [(0, 0), (0.1, 0.35), (0.2, 0.35)])
    _al(c, ws, wash, [(0.08, 0), (0.13, 0.82), (0.18, 0.8), (0.21, 0.55), (0.27, 0.3), (0.4, 0.05), (0.45, 0)])
    g = c.bone("burst")
    body = _sl(c, g, "glow", 700, 520, color=col, blend="normal")
    wide = _sl(c, g, "glow", 760, 600, color=col)
    hot = _sl(c, g, "glow_hot", 520, 330, color=core)
    rb = c.bone("rays", g)
    rays = _sl(c, rb, "rays20", 900, color=col, role="rays")
    c.show([body, wide, hot, rays], 0.2, 1.0)
    _al(c, body, col, [(0.2, 0), (0.3, 0.45), (1.0, 0.5)])
    _kf(c, g, "scale", [(0.2, 0.3, "cubic_out"), (0.5, 1.15), (1.0, 1.1)])
    _al(c, wide, col, [(0.2, 0), (0.3, 0.9), (0.55, 1.0), (1.0, 0.9)])
    _al(c, hot, core, [(0.2, 0), (0.3, 0.5), (0.55, 0.7), (1.0, 0.6)])
    _kf(c, rb, "scale", [(0.2, 0.4, "cubic_out"), (0.6, 1.2), (1.0, 1.3)])
    _kf(c, rb, "rotate", [(0.2, 0), (1.0, 14)])
    _al(c, rays, col, [(0.2, 0), (0.3, 0.45), (0.6, 0.4), (1.0, 0.2)])
    rnd = random.Random(12 + c.seed - 7)
    for i in range(int(P["count"])):
        ang = rnd.uniform(0, 2 * math.pi)
        d = rnd.uniform(160, 340)
        b = c.bone(f"spark{i}", g)
        s = _sl(c, b, "star4", rnd.uniform(14, 26), color=core)
        t0 = 0.22 + rnd.uniform(0, 0.08)
        c.show([s], t0, 1.0)
        _kf(c, b, "translate", [(t0, 0, 0), (1.0, d * math.cos(ang), d * math.sin(ang) * 0.8)], "cubic_out")
        _al(c, s, core, [(t0, 0), (t0 + 0.05, 1.0), (0.6, 0.7), (1.0, 0)])
    return c.result()


def win_screen_glow(c: Ctx, P: dict) -> dict:
    col, core, dcol = _hexn(P["color"], "2ED2FF"), _hexn(P["core_color"], "E6FFFF"), _hexn(P["dust_color"], "70ECFF")
    T, L0 = float(P["duration"]), float(P["settle"])
    g = c.bone("g")
    body = _sl(c, g, "glow", 760, 520, color=col, blend="normal")
    wide = _sl(c, g, "glow", 820, 560, color=col)
    hot = _sl(c, g, "glow_hot", 640, 360, color=core)
    rb = c.bone("rays", g)
    rays = _sl(c, rb, "fan_b", 980, color=col, role="rays")
    c.show([body, wide, hot, rays], 0, None)
    pul = _osc(L0, T, 1.0, 0, 1)
    _al(c, wide, col, [(0, 0.95), (L0, 0.8)] + [(t, 0.78 + 0.1 * v) for t, v in pul])
    _al(c, body, col, [(0, 0.5), (L0, 0.42)] + [(t, 0.4 + 0.06 * v) for t, v in pul])
    _al(c, hot, core, [(0, 0.6), (L0, 0.5)] + [(t, 0.48 + 0.1 * v) for t, v in pul])
    _al(c, rays, col, [(0, 0.3), (L0, 0.2)] + [(t, 0.18 + 0.05 * v) for t, v in pul])
    _kf(c, g, "scale", [(0, 1.1), (L0, 0.92)] + [(t, 0.92 + 0.03 * v) for t, v in pul])
    _kf(c, rb, "rotate", [(0, 0), (L0, 10), (T, 10 + (T - L0) * 4.5)])
    if int(P["count"]):
        _dust(c, int(P["count"]), P["dust_box"], dcol, 2.0, seed=5, rise=50)
    return c.result(duration=T, loop=[L0, T])


def win_upgrade_flash(c: Ctx, P: dict) -> dict:
    flash, a, b = _hexn(P["color"], "7FEBFF"), _hexn(P["wash_color"], "FF54D6"), _hexn(P["wash_mid"], "FF7A3C")
    sw, sh = (float(v) for v in P["screen"])
    ox, oy = (float(v) for v in P["screen_offset"])
    g = c.bone("flash")
    fl = _sl(c, g, "glow_hot", 760, 520, color=flash)
    rb = c.bone("rays", g)
    ry = _sl(c, rb, "rays", 900, color=flash, role="rays")
    st = _sl(c, g, "streak", 900, 70, color=flash)
    c.show([fl, ry, st], 0.02, 0.3)
    _al(c, fl, flash, [(0.02, 0), (0.04, 0.95), (0.1, 1.0), (0.2, 0.4), (0.3, 0)])
    _kf(c, rb, "scale", [(0.02, 0.4, "cubic_out"), (0.18, 1.3), (0.3, 1.4)])
    _al(c, ry, flash, [(0.02, 0), (0.05, 0.9), (0.18, 0.5), (0.3, 0)])
    _al(c, st, flash, [(0.02, 0), (0.05, 0.8), (0.16, 0.3), (0.25, 0)])
    scr = c.bone("screen", None, ox, oy)
    ws = _sl(c, scr, "white", sw, sh, color=a, blend="normal")
    c.show([ws], 0.12, 0.46)
    c.ab.slot_color(ws, [(c.T(0.12), hexa(a, 0)), (c.T(0.17), hexa(a, c.a(0.3))), (c.T(0.23), hexa(b, c.a(0.68))),
                         (c.T(0.3), hexa(b, c.a(0.6))), (c.T(0.36), hexa(_mix(b, a, 0.6), c.a(0.3))),
                         (c.T(0.44), hexa(a, 0))], "linear")
    return c.result()


def beam_sweep(c: Ctx, P: dict) -> dict:
    col = _hexn(P["color"], "FF54D6")
    T = float(P["duration"])
    nb = 7
    g = c.bone("g")
    bb = c.bone("beams", g)
    beams = _sl(c, bb, "beams", float(P["size"]), color=col, role="beams")
    body = _sl(c, g, "glow", 760, 560, color=col, blend="normal")
    wide = _sl(c, g, "glow", 820, 600, color=col)
    core = _sl(c, g, "glow_hot", 520, 300, color="FFFFFF")
    c.show([beams, body, wide, core], 0, None)
    _kf(c, bb, "rotate", [(0, 0), (T, -360 / nb)])
    pul = _osc(0, T, T / 2, 0, 1)
    _al(c, beams, col, [(t, 0.45 + 0.12 * v) for t, v in pul])
    _al(c, wide, col, [(t, 0.5 + 0.1 * v) for t, v in pul])
    _al(c, body, col, [(t, 0.42 + 0.06 * v) for t, v in pul])
    _al(c, core, "FFFFFF", [(t, 0.18 + 0.08 * v) for t, v in pul])
    if int(P["count"]):
        _dust(c, int(P["count"]), P["dust_box"], col, T, seed=8, rise=45)
    return c.result(duration=T, loop=[0, T])


def sunburst_intro(c: Ctx, P: dict) -> dict:
    col, core = _hexn(P["color"], "FFB52E"), _hexn(P["core_color"], "FFF3B8")
    sw, sh = (float(v) for v in P["screen"])
    ox, oy = (float(v) for v in P["screen_offset"])
    g = c.bone("g")
    gl = _sl(c, g, "glow_hot", 420, 260, color=col)
    bl = _sl(c, g, "glow_hot", 1700, 1700, color=core, role="bloom")
    scr = c.bone("screen", None, ox, oy)
    ws = _sl(c, scr, "white", sw, sh, color=col, blend="normal")
    c.show([gl], 0, 0.25)
    c.show([bl], 0.12, 0.45)
    c.show([ws], 0.15, 0.4)
    _al(c, gl, col, [(0, 0), (0.13, 0.8), (0.18, 1.0), (0.25, 0)])
    _al(c, bl, core, [(0.12, 0), (0.18, 1.0), (0.24, 0.9), (0.45, 0)])
    _kf(c, g, "scale", [(0.12, 0.5, "cubic_out"), (0.22, 1.0), (0.45, 1.1)])
    _al(c, ws, col, [(0.15, 0), (0.18, 0.35), (0.22, 0.2), (0.4, 0)])
    return c.result()


def sunburst_glow(c: Ctx, P: dict) -> dict:
    col, core = _hexn(P["color"], "FFB52E"), _hexn(P["core_color"], "FFF3B8")
    outer_c = _hexn(P["outer_color"], "") or _mix(col, "FF5A20", 0.45)
    T = float(P["duration"])
    g = c.bone("g")
    outer = _sl(c, g, "glow", 2200, 1800, color=outer_c, blend="normal")
    sun = _sl(c, g, "glow", 1700, 1250, color=col, blend="normal")
    hot = _sl(c, g, "glow_hot", 900, 640, color=core)
    f1 = c.bone("fan1", g)
    fan1 = _sl(c, f1, "fan", 1500, color=core, role="rays")
    f2 = c.bone("fan2", g, rot=7)
    fan2 = _sl(c, f2, "fan_b", 1300, color=col)
    c.show([outer, sun, hot, fan1, fan2], 0, None)
    _al(c, outer, outer_c, [(0, 0.9), (T, 0.9)])
    pul = _osc(0, T, T / 2, 0, 1)
    _al(c, sun, col, [(t, 0.92 + 0.05 * v) for t, v in pul])
    _al(c, hot, core, [(t, 0.45 + 0.1 * v) for t, v in pul])
    _al(c, fan1, core, [(t, 0.3 + 0.15 * v) for t, v in _osc(0, T, T / 8, 0, 1)])
    _al(c, fan2, col, [(t, 0.45 + 0.2 * v) for t, v in _osc(0, T, T / 5, 0, 1, phase=1.3)])
    _kf(c, f1, "rotate", [(0, 0), (T, float(P["turn"]))])
    _kf(c, f2, "rotate", [(0, 7), (T, 7 - float(P["turn"]))])
    if int(P["count"]):
        _dust(c, int(P["count"]), P["dust_box"], core, T, size=(10, 22), seed=21, rise=30)
    return c.result(duration=T, loop=[0, T])


def face_flash(c: Ctx, P: dict) -> dict:
    col = _hexn(P["color"], "FFE45A")
    T, d0 = float(P["duration"]), float(P["delay"])
    size = float(P["size"])
    shape = P["shape"]
    if shape not in ("disc", "plate"):
        raise ValueError("face_flash shape is disc or plate")
    g = c.bone("g", None, 0, 0, rot=float(P["tilt"]))
    face = _sl(c, g, shape, size * (1.0 if shape == "disc" else 0.72), color=col, role="face")
    halo = _sl(c, g, "glow", size * (1.6 if shape == "disc" else 1.5), color=col)
    parts = [face, halo]
    star = None
    if P["star"]:
        sb = c.bone("star", g, -size * 0.2, size * 0.2)
        star = _sl(c, sb, "star4", size * 0.9, color="FFFFFF")
        parts.append(star)
    c.show(parts, 0, None)
    rise, hold_t, fade = (float(v) for v in P["timing"])
    up, peak = d0, d0 + rise
    hold, gone = peak + hold_t, peak + hold_t + fade
    pk = float(P["peak"])
    _al(c, face, col, [(0, 0), (up, 0), (peak, pk), (hold, pk * float(P["hold_level"])), (gone, 0), (T, 0)])
    _al(c, halo, col, [(0, 0), (up, 0), (peak, float(P["halo"])), (gone, 0), (T, 0)])
    if star:
        _al(c, star, "FFFFFF", [(0, 0), (up + 0.04, 0), (peak, 0.8), (peak + 0.1, 0), (T, 0)])
        _kf(c, sb, "scale", [(up + 0.04, 0.3), (peak, 1.0), (peak + 0.1, 0.5)])
        _kf(c, sb, "rotate", [(up + 0.04, 0), (peak + 0.1, 30)])
    return c.result(duration=T, loop=[0, T])


# ------------------------------------------------------------------ registry
_SCREEN = ([840.0, 1440.0], "size of the full-screen wash (units)")
RECIPES.update({
    "ornate_cell_glow": dict(
        fn=ornate_cell_glow, duration=1.0, kind="one-shot", count=8, color="FFE63C",
        summary="Winning-cell highlight: yellow light PAINTED behind the symbol (normal blend lozenge + round skirt), an "
                "ornate lozenge outline of light, rising motes; grows in 0.17 s, breathes, dims over the last 0.3 s "
                "(start it 1.0 s before the pop; result.loop = the breathing span to loop while waiting).",
        anchor="Cell centre; draw it BEHIND the symbol (behind=<symbol slot>).",
        options=dict(line_color=("FFF4A8", "ornament line, core and motes"), size=(150.0, "cell size (units)"),
                     off=(True, "switch off at the end (False: stay on for a looping hold)"))),
    "starburst_pop": dict(
        fn=starburst_pop, duration=0.45, kind="one-shot", count=9, color="FFB43A",
        summary="A winning symbol vanishes: translucent square flash, a 22-ray and a 12-ray starburst shooting out (gone "
                "by 0.2 s), a star core + streak, then `count` glints drifting away (0.45 s).",
        anchor="Cell centre, in front of the symbols.",
        options=dict(hot_color=("FFF6D8", "star core + streak"), glint_color=("FFF4A8", "drifting glints"),
                     size=(150.0, "cell size (units)"))),
    "blowout_flash": dict(
        fn=blowout_flash, duration=0.2, kind="one-shot", color="FFF6D8",
        summary="A symbol that STAYS (a wild) blows out white while it re-forms: hot glow + star, 0.06-0.19 s. Play it "
                "with starburst_pop on the cells that are not removed.",
        anchor="The bright part of the symbol (a wild's heart sits ~33 units above the cell centre).",
        options=dict(size=([150.0, 118.0], "[w, h] of the blow-out glow"))),
    "label_glint": dict(
        fn=label_glint, duration=0.42, kind="one-shot", color="FFE7A0",
        summary="A label that just changed (a multiplier that stepped up): warm flare + streak + a tilted light band "
                "sweeping across it, 0.4 s.",
        anchor="Label centre, in front of it.",
        options=dict(size=([192.0, 120.0], "[w, h] of the label"))),
    "echo_stamp": dict(
        fn=echo_stamp, duration=0.4, kind="one-shot", color="FFFFFF",
        summary="A label joins a total: three echo copies stamp down under it (0-0.24 s), then one copy drops `drop` "
                "units into the target, growing 12% (0.23-0.4 s). Pass the label picture with art={'label': ...} "
                "(the default is a placeholder pill of light).",
        anchor="Label centre.",
        options=dict(size=([192.0, 122.0], "[w, h] of the label"), drop=(138.0, "distance down to the target"))),
    "ghost_pop": dict(
        fn=ghost_pop, duration=0.4, kind="one-shot", color="FFFFFF",
        summary="A number lands: the label pops in at `pop` and settles 0.97 -> 1.0 (0.2 s) while a ghost copy swells "
                "to `ghost` and fades. Pass the label picture with art={'label': ...}.",
        anchor="Number centre.",
        options=dict(size=([425.0, 94.0], "[w, h] of the label"), pop=(1.42, "start scale"),
                     ghost=(1.55, "ghost end scale"))),
    "fire_boost_flare": dict(
        fn=fire_boost_flare, duration=0.85, kind="window", color="FF9426",
        summary="Spine half of a 'multiplier fire boost' (fire and orange smoke rising out of a bar): the warm flare on "
                "the bar. The fire column and the smoke are After Effects: result.ae_hint gives the fire + magic_smoke "
                "template params and how to import them (tintable smoke recolours with one tint).",
        anchor="Bar centre; the flames rise from 8 units above it, behind the bar's labels.",
        options={}),
    "win_screen_intro": dict(
        fn=win_screen_intro, duration=1.0, kind="one-shot", count=16, color="2ED2FF",
        summary="Board -> win screen: the board dims (0-0.1 s), a full-screen colour wash floods (0.13 s) and clears as "
                "the screen fades in (0.45 s); a glow burst + ray flare + `count` flung sparks bloom behind the number "
                "(0.2-1.0 s). Hand over to win_screen_glow.",
        anchor="Win number centre; the burst goes BEHIND the number text.",
        options=dict(core_color=("E6FFFF", "hot core + sparks"), wash_color=("2840FF", "screen wash"),
                     dim_color=("0A0A30", "board dim"), screen=_SCREEN,
                     screen_offset=([-27.0, -134.0], "screen centre relative to the anchor"))),
    "win_screen_glow": dict(
        fn=win_screen_glow, duration=4.2, kind="window", count=22, color="2ED2FF",
        summary="The hold behind a count-up: glow (normal body + additive light + hot core) settles from the intro over "
                "`settle` s into a 1 s breathing glow, a fan of streaks turns slowly, `count` stars twinkle. Loop "
                "result.loop (the tail) while the count-up runs.",
        anchor="Win number centre, behind the number text.",
        options=dict(core_color=("E6FFFF", "hot core"), dust_color=("70ECFF", "star dust"),
                     settle=(2.2, "seconds the glow takes to settle (the loop starts there)"),
                     dust_box=([-317.0, 444.0, 293.0, -336.0], "[x0, y0, x1, y1] dust area round the anchor (any order)"))),
    "win_upgrade_flash": dict(
        fn=win_upgrade_flash, duration=0.46, kind="one-shot", color="7FEBFF",
        summary="Tier upgrade (Big -> Mega): flash + star rays + streak at the number (0.02-0.3 s), the screen washes "
                "wash_color -> wash_mid -> wash_color (0.12-0.44 s) while the game swaps the screen art under it.",
        anchor="Win number centre.",
        options=dict(wash_color=("FF54D6", "wash (the new tier's colour)"), wash_mid=("FF7A3C", "wash peak colour"),
                     screen=_SCREEN, screen_offset=([-27.0, -134.0], "screen centre relative to the anchor"))),
    "beam_sweep": dict(
        fn=beam_sweep, duration=3.0, kind="window", count=20, color="FF54D6",
        summary="Broad soft beams turning behind a title (7 beams, one beam step per loop: seamless), a breathing glow "
                "(normal body + additive), white core, `count` stars.",
        anchor="Win number centre, behind the title / number.",
        options=dict(size=(1500.0, "beam fan diameter"),
                     dust_box=([-317.0, 444.0, 293.0, -436.0], "[x0, y0, x1, y1] dust area round the anchor (any order)"))),
    "sunburst_intro": dict(
        fn=sunburst_intro, duration=0.45, kind="one-shot", color="FFB52E",
        summary="Board -> Total Win: a glow gathers on the counter (0-0.18 s), a bloom fills the screen (0.12-0.45 s) "
                "with a light colour wash. Hand over to sunburst_glow.",
        anchor="The sunburst centre.",
        options=dict(core_color=("FFF3B8", "bloom"), screen=_SCREEN,
                     screen_offset=([0.0, -228.0], "screen centre relative to the anchor"))),
    "sunburst_glow": dict(
        fn=sunburst_glow, duration=4.0, kind="window", count=16, color="FFB52E",
        summary="The Total Win sunburst: warm NORMAL-blend light behind everything (outer + sun: it turns a cool sky "
                "warm, which additive light cannot), white-hot core, two fans of thin rays turning against each other "
                "and flickering, `count` sparkles. Seamless loop.",
        anchor="The sunburst centre (between the title and the prize).",
        options=dict(core_color=("FFF3B8", "core + inner ray fan + sparkles"),
                     outer_color=("", "outer light (default: color mixed 45% toward FF5A20)"),
                     turn=(12.0, "degrees the fans turn per loop"),
                     dust_box=([-340.0, 350.0, 340.0, -350.0], "[x0, y0, x1, y1] sparkle area round the anchor (any order)"))),
    "face_flash": dict(
        fn=face_flash, duration=1.25, kind="window", color="FFE45A",
        summary="A light that fills one object's face on a period: shape disc (a coin) or plate (a cut gem), flat fill "
                "with a short soft edge + halo + optional star glint; peaks `delay` + 0.1 s into each loop. Chain two "
                "(a gem at delay 0.03, a coin at 0.2) for a gem-then-coin glint. Parent it to the object's bone.",
        anchor="Object centre.",
        options=dict(shape=("disc", "disc | plate"), size=(152.0, "object size (units)"), tilt=(0.0, "plate angle"),
                     delay=(0.2, "seconds into the loop the flash starts"), peak=(0.85, "face alpha at the peak"),
                     hold_level=(0.88, "share of the peak still lit at the end of the hold"),
                     timing=([0.1, 0.1, 0.1], "[rise, hold, fade] seconds"), halo=(0.45, "halo alpha at the peak"),
                     star=(True, "star glint at the peak"))),
})
_ROLES = {
    "ornate_cell_glow": {"paint": "soft round glow painted behind the symbol (normal blend)",
                         "frame": "ornate frame of light round the cell (white on transparent)"},
    "starburst_pop": {"rays": "starburst of thin rays (white on transparent)"},
    "label_glint": {"band": "soft vertical band of light"},
    "echo_stamp": {"label": "the label picture that stamps and drops (normal blend)"},
    "ghost_pop": {"label": "the number / label picture (normal blend)"},
    "win_screen_intro": {"rays": "ray flare behind the number"},
    "win_screen_glow": {"rays": "fan of streaks"},
    "win_upgrade_flash": {"rays": "star rays of the flash"},
    "beam_sweep": {"beams": "beam fan (white on transparent)"},
    "sunburst_glow": {"rays": "sunburst ray fan"},
    "face_flash": {"face": "the object's own silhouette in white (fills exactly its face)"},
}
for _n, _r in _ROLES.items():
    ROLES[_n] = _r
    RECIPES[_n]["roles"] = _r
_ROLES2 = {"blowout_flash": {"glow": "the blow-out glow (white, soft)"},
           "fire_boost_flare": {"flare": "the warm flare on the bar"},
           "sunburst_intro": {"bloom": "the screen-filling bloom"}}
for _n, _r in _ROLES2.items():
    ROLES[_n] = _r
    RECIPES[_n]["roles"] = _r
# recipes with normal-blend parts (paint / screen washes / warm light that additive cannot give on pale or cool art)
for _n in ("ornate_cell_glow", "echo_stamp", "ghost_pop", "win_screen_intro", "win_screen_glow", "win_upgrade_flash",
           "beam_sweep", "sunburst_intro", "sunburst_glow"):
    RECIPES[_n]["normal_blend"] = True

WIN_SCREEN_RECIPES = ["ornate_cell_glow", "starburst_pop", "blowout_flash", "label_glint", "echo_stamp", "ghost_pop",
                      "fire_boost_flare", "win_screen_intro", "win_screen_glow", "win_upgrade_flash", "beam_sweep",
                      "sunburst_intro", "sunburst_glow", "face_flash"]
