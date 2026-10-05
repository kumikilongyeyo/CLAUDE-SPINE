"""FX recipes: hand-tuned, parameterised glow / light / particle layers — the ``fx_recipe`` tool's engine.

``fx.py`` holds generic slot-game presets (explosion, coin_burst, ...). This module holds *authored* looks: each
recipe is one visual element lifted from a real reference clip (a lotus blooming out of a magic book) and rebuilt
as Spine primitives, so it can be placed, recoloured, resized and mixed with any other recipe or any rig.

    rune_ring     gold rune circle on a surface: builds up, flashes white, fades (iso-squashed, counter-rotating)
    burst_flare   anamorphic flare + shock ring + flung sparks, the "pop" moment
    rim_wisps     soft feathery fringe around a footprint
    bloom_aura    coloured halo + inner core + rising light column
    floor_glow    warm glow and streaky reflection underneath a subject
    fireflies     drifting motes, each with its own looping life and twinkle
    twinkles      four-point stars popping and spinning
    magic_reveal  all seven, timed like the reference clip (13.2 s), into one animation

Rules every recipe follows (they are why the output is cheap and drops into a game):

* Procedural textures only, baked white or colourised once; no art is needed and the atlas stays tiny.
* Additive blend everywhere, so all FX slots sit in one batch (1 draw call).
* One group bone per recipe at the *subject centre* (``x``, ``y``); its scale is ``scale``, so every dimension below is
  in design units (a ~720-unit canvas, a subject ~420 wide) and the whole recipe resizes as one piece.
* FX slots have no setup attachment: the animation switches them on and off, so they never show in the setup pose
  or in animations that do not use them.
* Keys are dense *linear* samples of a closed-form function of time (not hand-keyed beziers), so every curve is
  exact and a recipe can be retimed by scaling its time axis.
* Looping lives (fireflies) get explicit keys at every respawn so the position jump hides inside alpha 0.
* ``into=`` merges into an existing animation, ``start=`` shifts it in time; every recipe fires ``fx_<recipe>``.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .fx import tex_glow, tex_ring, tex_spark, _rgba
from .ir import Bone, RegionAttachment, Slot
from .project import Project
from .timeline import AnimBuilder, r


# ------------------------------------------------------------------ colour + texture helpers
def _hexn(c: str | None, default: str) -> str:
    c = (c or default).lstrip("#").upper()
    return c[:6]


def _rgb(c: str) -> tuple[int, int, int]:
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _mix(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(a[i] * (1 - t) + b[i] * t for i in range(3))


def hexa(rgb: str, a: float) -> str:
    return rgb.lstrip("#").upper()[:6] + f"{max(0, min(255, round(a * 255))):02X}"


def _grid(n: int):
    y, x = np.mgrid[0:n, 0:n].astype(float)
    c = (n - 1) / 2
    return (x - c) / c, (y - c) / c


def _blur(a: np.ndarray, rad: float) -> np.ndarray:
    im = Image.fromarray(np.clip(a * 255, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(rad))
    return np.asarray(im, np.float32) / 255


def _colorize(a: np.ndarray, hot: tuple, mid: tuple, edge: tuple | None = None) -> Image.Image:
    """Intensity (0..1) -> RGBA whose colour runs edge -> mid -> hot (near-white core) as it gets brighter."""
    a = np.clip(a, 0, 1)
    edge = edge or mid
    t1 = np.clip(a / 0.5, 0, 1)[..., None]
    t2 = np.clip((a - 0.5) / 0.5, 0, 1)[..., None]
    rgb = np.array(edge) * (1 - t1) + np.array(mid) * t1
    rgb = rgb * (1 - t2) + np.array(hot) * t2
    return _rgba(rgb / 255.0, a)


def _palette(color: str) -> tuple[tuple, tuple, tuple]:
    """(hot, mid, edge) from one colour: white-ish core, the colour itself, a deeper rim."""
    mid = _rgb(color)
    return _mix(mid, (255, 255, 255), 0.82), mid, _mix(mid, (255, 120, 0) if mid[0] > mid[2] else (0, 40, 255), 0.18)


def tex_rune_ring(color: str = "FFCD3C", n: int = 512, runes: int = 12) -> Image.Image:
    """Double ring, rune glyphs between them, tick marks, a spiral at the middle. Drawn at 2x, blurred twice."""
    S = 2
    N = n * S
    img = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(img)
    c = N / 2
    rng = np.random.default_rng(11)
    R = N / 2

    def circle(rad, w):
        d.ellipse([c - rad, c - rad, c + rad, c + rad], outline=255, width=max(1, int(w * S)))

    circle(R * 0.93, 3)
    circle(R * 0.88, 1.4)
    circle(R * 0.60, 2)
    circle(R * 0.565, 1)
    for k in range(runes):
        a = k / runes * 2 * math.pi
        cx, cy = c + math.cos(a) * R * 0.74, c + math.sin(a) * R * 0.74
        ux, uy = math.cos(a), math.sin(a)
        vx, vy = -uy, ux
        g = R * 0.075
        pts = [(cx + ux * rng.uniform(-g, g) + vx * rng.uniform(-g, g),
                cy + uy * rng.uniform(-g, g) + vy * rng.uniform(-g, g)) for _ in range(int(rng.integers(3, 5)))]
        d.line(pts, fill=255, width=int(3.2 * S), joint="curve")
        d.line([(cx - ux * g, cy - uy * g), (cx + ux * g, cy + uy * g)], fill=255, width=int(2 * S))
    for k in range(48):
        a = k / 48 * 2 * math.pi
        r0, r1 = R * 0.885, R * (0.905 if k % 4 else 0.925)
        d.line([(c + math.cos(a) * r0, c + math.sin(a) * r0), (c + math.cos(a) * r1, c + math.sin(a) * r1)],
               fill=255, width=int(1.6 * S))
    pts = []
    for i in range(160):
        t = i / 159
        a = t * 4.2 * math.pi
        rad = R * 0.52 * (1 - t) ** 0.85
        pts.append((c + math.cos(a) * rad, c + math.sin(a) * rad))
    d.line(pts, fill=255, width=int(4 * S), joint="curve")
    for a in (0, math.pi / 2):
        d.line([(c - math.cos(a) * R * 0.1, c - math.sin(a) * R * 0.1), (c + math.cos(a) * R * 0.1, c + math.sin(a) * R * 0.1)],
               fill=255, width=int(3 * S))
    base = np.asarray(img, np.float32) / 255
    a = np.clip(_blur(base, 1.3 * S) * 1.15 + _blur(base, 7 * S) * 0.85, 0, 1)
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8), "L").resize((n, n), Image.LANCZOS), np.float32) / 255
    x, y = _grid(n)
    a *= np.clip((1 - np.hypot(x, y)) / 0.06, 0, 1)         # nothing at the border: the quad edge never shows
    return _colorize(a, *_palette(color))


def tex_flare(color: str = "FFEE8C", w: int = 512, h: int = 128) -> Image.Image:
    """Anamorphic horizontal streak with a hot core; the tails take the colour."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = (y - (h - 1) / 2) / ((h - 1) / 2)
    streak = np.exp(-(yn / 0.10) ** 2) * np.exp(-np.abs(xn) / 0.40)
    thin = np.exp(-(yn / 0.03) ** 2) * np.exp(-np.abs(xn) / 0.7)
    halo = np.exp(-((xn / 0.30) ** 2 + (yn / 0.42) ** 2))
    a = np.clip(streak * 0.95 + thin * 0.9 + halo * 0.55, 0, 1) * np.clip((1 - np.abs(xn)) / 0.06, 0, 1) * np.clip((1 - np.abs(yn)) / 0.1, 0, 1)
    hot, mid, edge = _palette(color)
    return _colorize(a, hot, mid, _mix(edge, (200, 235, 110), 0.35))


def tex_wisp(w: int = 256, h: int = 128, seed: int = 5) -> Image.Image:
    """Soft feathery tuft: base on the left edge, fraying to the right. Fine streaks run along its length.
    (Thresholding the noise to zero made speckle pits and read as gas flames; keep a floor under the streaks.)"""
    rng = np.random.default_rng(seed)

    def stretch(rows, cols):
        lo = rng.random((rows, cols))
        return np.asarray(Image.fromarray((lo * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC), np.float32) / 255

    streak = 0.65 * stretch(h // 9, w // 36 + 2) + 0.35 * stretch(h // 4, w // 18 + 2)
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = x / (w - 1)
    yn = (y - (h - 1) / 2) / ((h - 1) / 2)
    width = 0.95 * (1 - xn ** 1.15) + 0.10
    env = np.exp(-(yn / np.maximum(width, 1e-3)) ** 2)
    a = env * (0.42 + 0.9 * streak) * np.clip(1 - xn, 0, 1) ** 1.5
    a *= np.clip(xn / 0.04, 0, 1) * np.clip((1 - np.abs(yn)) / 0.10, 0, 1)
    return _colorize(a * 1.2, (255, 255, 255), (255, 250, 232), (255, 238, 200))


def tex_beam(w: int = 128, h: int = 512) -> Image.Image:
    """Vertical light column, bright at the bottom, fading up, soft sides."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = 1 - y / (h - 1)
    a = np.exp(-(xn / (0.22 + 0.5 * (1 - yn))) ** 2) * (yn ** 1.6)
    a *= np.clip((1 - np.abs(xn)) / 0.1, 0, 1) * np.clip(y / 30, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def tex_mote(n: int = 64) -> Image.Image:
    x, y = _grid(n)
    d = np.hypot(x, y)
    a = (np.exp(-(d / 0.16) ** 2) + 0.38 * np.exp(-(d / 0.55) ** 2)) * np.clip((1 - d) / 0.12, 0, 1)
    w3 = (255, 255, 255)
    return _colorize(np.clip(a, 0, 1), w3, w3, w3)


def tex_reflect(w: int = 128, h: int = 256) -> Image.Image:
    """Blurred vertical smear fading downward. Soft top edge and low-contrast streaks: a hard top line or strong
    banding reads as a curtain, not a reflection."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = y / (h - 1)
    a = np.exp(-(xn / 0.62) ** 2) * (1 - yn) ** 1.8 * np.clip(yn / 0.18, 0, 1)
    a *= 0.8 + 0.2 * np.cos(xn * 6.5 + 0.4) ** 2
    a *= np.clip((1 - np.abs(xn)) / 0.2, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1) * 0.9)


# texture name -> factory (white textures are tinted per slot; coloured ones are named with their colour)
WHITE_TEX: dict[str, Callable[[], Image.Image]] = {
    "fx/wisp": tex_wisp, "fx/beam": tex_beam, "fx/mote": tex_mote, "fx/reflect": tex_reflect,
    "fx/glow": tex_glow, "fx/ring": tex_ring, "fx/spark": tex_spark,
}


# ------------------------------------------------------------------ math helpers
def smooth(t, a, b):
    u = np.clip((t - a) / max(b - a, 1e-9), 0, 1)
    return float(u * u * (3 - 2 * u))


def ease_out(u, p=3.0):
    return float(1 - (1 - np.clip(u, 0, 1)) ** p)


def times_dense(t0: float, t1: float, rate: float) -> list[float]:
    n = max(2, int(math.ceil((t1 - t0) * rate)) + 1)
    return [float(v) for v in np.linspace(t0, t1, n)]


def _br(t, f, p=0.0):
    return 0.5 + 0.5 * math.sin(2 * math.pi * t * f + p)


# ------------------------------------------------------------------ build context
class Ctx:
    """One recipe application: a group bone at the subject centre, slots in one run, keys into one animation."""

    def __init__(self, p: Project, recipe: str, x: float, y: float, scale: float, start: float, k: float,
                 intensity: float, seed: int, into: str, parent: str, front_of: str, behind: str, name: str):
        self.p, self.sk = p, p.data
        self.recipe = recipe
        self.t0, self.k, self.I, self.seed, self.S = start, k, intensity, seed, scale
        self.anim = into or f"fx_{name or recipe}"
        self.ab = AnimBuilder(self.sk, self.anim, replace=not into)
        self.prefix = name or recipe
        self.front_of, self.behind = front_of, behind
        self.last_slot: str | None = None
        self.slots: list[str] = []
        self.bones: list[str] = []
        self.group = self.bone("grp", parent, x, y, sx=scale, sy=scale, root=True)

    # -- structure
    def bone(self, suffix: str, parent: str | None = None, x: float = 0, y: float = 0, rot: float = 0,
             sx: float = 1, sy: float = 1, root: bool = False) -> str:
        base = f"fx_{self.prefix}" if root else f"fx_{self.prefix}_{suffix}"
        nm = self.sk.unique_name(base)
        self.sk.bones.append(Bone(name=nm, parent=parent or self.group, x=x, y=y, rotation=rot, scaleX=sx, scaleY=sy, length=10))
        self.bones.append(nm)
        return nm

    def tex(self, name: str, make: Callable[[], Image.Image] | None = None) -> tuple[int, int]:
        try:
            im = self.p.image(name)
        except FileNotFoundError:
            im = (make or WHITE_TEX[name])()
            self.p.write_image(name, im)
        return im.size

    def slot(self, bone: str, tex: str, width: float, color: str = "FFFFFFFF", ox: float = 0.0, oy: float = 0.0,
             height: float | None = None, make: Callable[[], Image.Image] | None = None) -> str:
        nm = self.sk.unique_name(bone, "slot")
        s = Slot(name=nm, bone=bone, color=color, blend="additive")
        if self.last_slot is not None:
            self.sk.add_slot(s, after=self.last_slot)
        elif self.behind:
            self.sk.add_slot(s, before=self.behind)
        elif self.front_of:
            self.sk.add_slot(s, after=self.front_of)
        else:
            self.sk.add_slot(s)
        self.last_slot = nm
        tw, th = self.tex(tex, make)
        h = height if height is not None else width * th / tw
        self.sk.set_attachment(nm, "fx", RegionAttachment(path=tex, x=ox, y=oy, width=round(width, 2), height=round(h, 2)))
        self.slots.append(nm)
        return nm

    # -- keys (local time u at design speed -> animation time)
    def T(self, u: float) -> float:
        return r(self.t0 + u * self.k, 4)

    def a(self, v: float) -> float:
        return min(1.0, max(0.0, v * self.I))

    def show(self, slots: list[str], u_on: float, u_off: float | None) -> None:
        for s in slots:
            pts: list = [(0.0, None), (self.T(u_on), "fx")] if self.T(u_on) > 0 else [(0.0, "fx")]
            if u_off is not None:
                pts.append((self.T(u_off), None))
            self.ab.slot_attachment(s, pts)

    def bone_keys(self, bone: str, timeline: str, ts, fn) -> None:
        pts = []
        for u in ts:
            v = fn(u)
            pts.append((self.T(u), *(v if isinstance(v, tuple) else (v,))))
        self.ab.bone(bone, timeline, _uniq(pts), "linear")

    def color_keys(self, slot: str, ts, fn) -> None:
        self.ab.slot_color(slot, _uniq([(self.T(u), fn(u)) for u in ts]), "linear")

    def result(self, **extra) -> dict:
        self.ab.event(self.t0, f"fx_{self.recipe}")
        return {"recipe": self.recipe, "animation": self.anim, "group_bone": self.group, "bones": len(self.bones),
                "slots": list(self.slots), "event": f"fx_{self.recipe}", "start": self.t0, **extra}


def _uniq(pts: list) -> list:
    """Drop keys whose time repeats (retiming can collapse two samples onto one tick)."""
    out: list = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < 1e-6:
            out[-1] = p
        else:
            out.append(p)
    return out


# ------------------------------------------------------------------ the recipes
# Each takes (ctx, params) where params is the merged defaults+overrides dict, and returns a result dict.
def rune_ring(c: Ctx, P: dict) -> dict:
    D = 2.7
    color = _hexn(P["color"], "FFCD3C")
    runes = int(P["runes"])
    tname = f"fx/rune_ring_{color}" + ("" if runes == 12 else f"_{runes}")
    mk = lambda: tex_rune_ring(color, runes=runes)  # noqa: E731
    grp = c.bone("ring", c.group, 8, 24, sx=1, sy=float(P["squash"]))     # iso squash: children rotate in the plane
    b_out, b_in, b_core = c.bone("outer", grp), c.bone("inner", grp), c.bone("core", grp)
    s_glow = c.slot(b_core, "fx/glow", 370)
    s_out = c.slot(b_out, tname, 400, make=mk)
    s_in = c.slot(b_in, tname, 238, make=mk)
    s_flash = c.slot(b_core, "fx/glow", 170)
    ts = times_dense(0, D, 24)
    c.show([s_glow, s_out, s_in, s_flash], 0, D)
    peak = 1.45
    build = lambda u: smooth(u, 0.0, 1.3)  # noqa: E731
    fade = lambda u: 1 - smooth(u, 1.65, D)  # noqa: E731
    flick = lambda u: 0.9 + 0.1 * math.sin(u * 17) * math.sin(u * 5.3)  # noqa: E731
    env = lambda u: (0.08 + 0.92 * build(u)) * fade(u) * flick(u)  # noqa: E731
    spin = float(P["spin"])

    def scl(u):
        s = 0.62 + 0.38 * ease_out(u / 1.0, 2.5)
        if u > 1.45:
            s += 0.22 * smooth(u, 1.45, D)
        return s
    ang = lambda u: -(spin * u + 70 * smooth(u, 0.9, 1.6) * (u - 0.9))  # noqa: E731
    c.bone_keys(b_out, "rotate", ts, ang)
    c.bone_keys(b_out, "scale", ts, lambda u: (scl(u), scl(u)))
    c.bone_keys(b_in, "rotate", ts, lambda u: -1.6 * ang(u))
    c.bone_keys(b_in, "scale", ts, lambda u: (scl(u) * 0.96 + 0.04,) * 2)
    for s in (s_out, s_in):
        c.color_keys(s, ts, lambda u: hexa("FFFFFF", c.a(env(u) * 1.05)))
    core = _hexn(None, color)
    gl = lambda u: (0.12 + 0.5 * build(u) + 0.55 * math.exp(-((u - peak) / 0.16) ** 2)) * fade(u)  # noqa: E731
    c.color_keys(s_glow, ts, lambda u: hexa(core, c.a(gl(u))))
    cs = lambda u: 0.8 + 0.25 * build(u) + 0.3 * math.exp(-((u - peak) / 0.25) ** 2)  # noqa: E731
    c.bone_keys(b_core, "scale", ts, lambda u: (cs(u), cs(u)))
    flash = float(P["flash"])
    c.color_keys(s_flash, ts, lambda u: hexa("FFFBE0", c.a(flash * math.exp(-((u - peak) / 0.12) ** 2))))
    return c.result(duration=D * c.k, peak_at=c.T(peak))


def burst_flare(c: Ctx, P: dict) -> dict:
    D = 1.8
    color = _hexn(P["color"], "FFEE8C")
    ring_color = _hexn(P["ring_color"], "FFE9A0")
    ns = int(P["count"])
    tname = f"fx/flare_{color}"
    mk = lambda: tex_flare(color)  # noqa: E731
    grp = c.bone("flare", c.group, 0, 62)
    b_h, b_v = c.bone("h", grp), c.bone("v", grp, rot=90)
    b_core, b_ring = c.bone("core", grp), c.bone("ring", grp, sy=0.42)
    s_ring = c.slot(b_ring, "fx/ring", 420)
    s_h = c.slot(b_h, tname, 680, make=mk)
    s_v = c.slot(b_v, tname, 330, make=mk)
    s_core = c.slot(b_core, "fx/glow", 280)
    rng = np.random.default_rng(c.seed + 14)
    sp = []
    spread = float(P["spread"])
    for i in range(ns):
        a = rng.uniform(0, 2 * math.pi)
        bn = c.bone(f"sp{i}", grp)
        sl = c.slot(bn, "fx/mote", rng.uniform(26, 44))
        sp.append((bn, sl, a, rng.uniform(150, 320) * spread, rng.uniform(0.7, 1.3), rng.uniform(0, 0.12)))
    ts = times_dense(0, D, 30)
    c.show([s_ring, s_h, s_v, s_core], 0, D)
    att, dec = 0.10, 1.5

    def amp(u):
        if u < att:
            return ease_out(u / att, 2)
        return float(max(0.0, 1 - ((u - att) / (dec - att))) ** 1.8)
    sx = lambda u: 1.2 * ease_out(u / 0.28, 3) * (1 - 0.45 * smooth(u, 0.28, dec))  # noqa: E731
    c.bone_keys(b_h, "scale", ts, lambda u: (sx(u), 0.25 + 0.75 * amp(u) ** 0.6))
    c.color_keys(s_h, ts, lambda u: hexa("FFFFFF", c.a(amp(u))))
    c.bone_keys(b_v, "scale", ts, lambda u: (0.55 * sx(u), 0.2 + 0.6 * amp(u) ** 0.6))
    c.color_keys(s_v, ts, lambda u: hexa(color, c.a(0.8 * amp(u))))
    c.bone_keys(b_core, "scale", ts, lambda u: (0.5 + 0.9 * ease_out(u / 0.35, 2.5),) * 2)
    c.color_keys(s_core, ts, lambda u: hexa("FFF8C8", c.a(1.1 * amp(u))))
    c.bone_keys(b_ring, "scale", ts, lambda u: (0.18 + 1.35 * ease_out(u / 1.1, 2.6),) * 2)
    c.color_keys(s_ring, ts, lambda u: hexa(ring_color, c.a(0.9 * (1 - smooth(u, 0.05, 1.1)) * smooth(u, 0, 0.04))))
    for bn, sl, a, dist, life, delay in sp:
        tts = times_dense(delay, delay + life, 24)

        def pos(u, a=a, dist=dist, delay=delay, life=life):
            q = (u - delay) / life
            e = ease_out(q, 2.4)
            return (math.cos(a) * dist * e, math.sin(a) * dist * e * 0.7 - 70 * q * q + 20 * q)
        c.bone_keys(bn, "translate", tts, pos)
        c.bone_keys(bn, "scale", tts, lambda u, d=delay, L=life: (1.0 - 0.7 * ((u - d) / L),) * 2)
        c.color_keys(sl, tts, lambda u, d=delay, L=life: hexa("FFF2A8", c.a(0.95 * (1 - ((u - d) / L)) ** 1.3)))
        c.ab.slot_attachment(sl, [(0.0, None), (c.T(delay), "fx"), (c.T(delay + life), None)])
    return c.result(duration=D * c.k, sparks=ns)


def rim_wisps(c: Ctx, P: dict) -> dict:
    dur = float(P["duration"])
    n = int(P["count"])
    RX, RY = float(P["rx"]), float(P["ry"])
    tint = _hexn(P["color"], "FFF6DC")
    grp = c.bone("rim", c.group, 4, -6)
    rng = np.random.default_rng(c.seed - 4)
    b_ring = c.bone("ring", grp, sy=RY / RX)
    s_ring = c.slot(b_ring, "fx/ring", 2 * RX / 0.78)
    wl = float(P["length"])
    w = []
    for i in range(n):
        ph = i / n * 2 * math.pi + rng.uniform(-0.06, 0.06)
        x, y = math.cos(ph) * RX, math.sin(ph) * RY
        rot = math.degrees(math.atan2(math.sin(ph) / RY, math.cos(ph) / RX))    # outward normal of the ellipse
        bn = c.bone(f"w{i}", grp, x, y, rot)
        length = rng.uniform(105, 165) * wl
        sl = c.slot(bn, "fx/wisp", length, ox=length / 2, height=length * 0.62)
        w.append((bn, sl, rng.uniform(0, 2 * math.pi), rng.uniform(0.8, 1.15), rng.uniform(1.6, 2.6), rng.uniform(0, 0.5)))
    ts = times_dense(0, dur, 14)
    c.show([s_ring] + [x[1] for x in w], 0, dur)
    ringa = lambda u: ease_out(u / 0.8, 2) * (1 - smooth(u, dur - 1.1, dur)) * (0.38 + 0.12 * math.sin(2 * math.pi * u / 2.2))  # noqa: E731
    c.color_keys(s_ring, ts, lambda u: hexa(tint, c.a(ringa(u))))
    for bn, sl, ph, ln, per, dl in w:
        grow = lambda u, dl=dl: ease_out((u - dl) / 0.7, 2.2)  # noqa: E731
        out = lambda u: 1 - smooth(u, dur - 1.1, dur)  # noqa: E731
        osc = lambda u, per=per, ph=ph: 0.5 + 0.5 * math.sin(2 * math.pi * u / per + ph)  # noqa: E731
        c.bone_keys(bn, "scale", ts, lambda u, grow=grow, osc=osc, ln=ln, per=per, ph=ph: (
            ln * (0.25 + 0.75 * grow(u)) * (0.84 + 0.3 * osc(u)), 0.85 + 0.3 * math.sin(2 * math.pi * u / per * 0.7 + ph * 1.3)))
        c.bone_keys(bn, "rotate", ts, lambda u, per=per, ph=ph: 7 * math.sin(2 * math.pi * u / (per * 1.3) + ph))
        c.color_keys(sl, ts, lambda u, grow=grow, out=out, osc=osc: hexa(tint, c.a(grow(u) * out(u) * (0.42 + 0.5 * osc(u)))))
    return c.result(duration=dur * c.k, tufts=n)


def bloom_aura(c: Ctx, P: dict) -> dict:
    dur = float(P["duration"])
    halo = _hexn(P["color"], "FF4FA6")
    core = _hexn(P["color2"], "C890FF")
    beam_c = _hexn(P["beam_color"], "FFA6DC")
    grp = c.bone("aura", c.group, 0, 105)
    b_big, b_beam = c.bone("big", grp, 0, -15), c.bone("beam", grp, 0, 10)
    b_core, b_hot = c.bone("core", grp, 0, 6), c.bone("hot", grp, 0, 10)
    s_big = c.slot(b_big, "fx/glow", 720)
    s_beam = c.slot(b_beam, "fx/beam", 190, oy=170, height=340) if P["beam"] else None
    s_core = c.slot(b_core, "fx/glow", 270)
    s_hot = c.slot(b_hot, "fx/glow", 90)
    ts = times_dense(0, dur, 16)
    c.show([s for s in (s_big, s_beam, s_core, s_hot) if s], 0, dur)
    inn = lambda u: ease_out(u / 0.9, 2.2)  # noqa: E731
    out = lambda u: 1 - smooth(u, dur - 1.3, dur)  # noqa: E731
    env = lambda u: inn(u) * out(u)  # noqa: E731
    c.color_keys(s_big, ts, lambda u: hexa(halo, c.a(env(u) * (0.55 + 0.25 * _br(u, 0.42)))))
    c.bone_keys(b_big, "scale", ts, lambda u: (0.55 + 0.45 * inn(u) + 0.07 * _br(u, 0.42),) * 2)
    c.color_keys(s_core, ts, lambda u: hexa(core, c.a(env(u) * (0.55 + 0.3 * _br(u, 0.6, 1.1)))))
    c.bone_keys(b_core, "scale", ts, lambda u: (0.7 + 0.35 * inn(u) + 0.1 * _br(u, 0.6, 1.1),) * 2)
    c.color_keys(s_hot, ts, lambda u: hexa("FFE8FF", c.a(env(u) * (0.35 + 0.3 * _br(u, 0.9, 2)))))
    if s_beam:
        c.color_keys(s_beam, ts, lambda u: hexa(beam_c, c.a(env(u) * (0.38 + 0.2 * _br(u, 0.5, 0.4)))))
        c.bone_keys(b_beam, "scale", ts, lambda u: (0.75 + 0.2 * _br(u, 0.5, 0.4), 0.3 + 0.7 * ease_out(u / 1.4, 2) + 0.08 * _br(u, 0.5)))
    return c.result(duration=dur * c.k)


def floor_glow(c: Ctx, P: dict) -> dict:
    dur = float(P["duration"])
    col = _hexn(P["color"], "FFB84A")
    grp = c.bone("floor", c.group, 0, -92)
    b_glow, b_refl, b_pool = c.bone("glow", grp, sy=0.3), c.bone("refl", grp, 0, -20), c.bone("pool", grp, 0, 10, sy=0.2)
    s_glow = c.slot(b_glow, "fx/glow", 640)
    s_refl = c.slot(b_refl, "fx/reflect", 330, oy=-130, height=260) if P["reflection"] else None
    s_pool = c.slot(b_pool, "fx/glow", 420)
    ts = times_dense(0, dur, 10)
    c.show([s for s in (s_glow, s_refl, s_pool) if s], 0, dur)
    inn = lambda u: smooth(u, 0, 1.0)  # noqa: E731
    out = lambda u: 1 - smooth(u, dur - 1.8, dur)  # noqa: E731
    swell = lambda u: 0.45 + 0.55 * smooth(u, dur * 0.12, dur * 0.3) * (1 - 0.6 * smooth(u, dur * 0.75, dur * 0.95))  # noqa: E731
    warm = _mix(_rgb(col), (255, 255, 255), 0.35)
    warm_hex = "%02X%02X%02X" % tuple(int(v) for v in warm)
    refl = "%02X%02X%02X" % tuple(int(v) for v in _mix(_rgb(col), (255, 255, 255), 0.12))
    c.color_keys(s_glow, ts, lambda u: hexa(col, c.a(inn(u) * out(u) * swell(u) * (0.5 + 0.12 * _br(u, 0.35)))))
    c.color_keys(s_pool, ts, lambda u: hexa(warm_hex, c.a(inn(u) * out(u) * swell(u) * (0.45 + 0.15 * _br(u, 0.5, 1)))))
    c.bone_keys(b_glow, "scale", ts, lambda u: (0.9 + 0.12 * swell(u),) * 2)
    if s_refl:
        c.color_keys(s_refl, ts, lambda u: hexa(refl, c.a(inn(u) * out(u) * swell(u) * (0.38 + 0.15 * _br(u, 0.4, 2)))))
        c.bone_keys(b_refl, "scale", ts, lambda u: (0.9 + 0.1 * _br(u, 0.4, 2), 0.8 + 0.25 * swell(u) + 0.06 * _br(u, 0.3)))
    return c.result(duration=dur * c.k)


def fireflies(c: Ctx, P: dict) -> dict:
    dur = float(P["duration"])
    n = int(P["count"])
    palette = [_hexn(x, "FFFFFF") for x in ([P["color"]] if P["color"] else P["palette"])]
    sxr, syr, rise_k, size_k = float(P["spread_x"]), float(P["spread_y"]), float(P["rise"]), float(P["size"])
    grp = c.bone("motes", c.group, 0, 40)
    rng = np.random.default_rng(c.seed + 1)
    motes = []
    for i in range(n):
        bn = c.bone(f"m{i}", grp)
        size = float(rng.choice([rng.uniform(22, 36), rng.uniform(50, 84)], p=[0.7, 0.3])) * size_k
        sl = c.slot(bn, "fx/mote", size)
        rho, a = math.sqrt(rng.uniform(0.04, 1)), rng.uniform(0, 2 * math.pi)
        motes.append(dict(b=bn, s=sl, hx=math.cos(a) * rho * sxr, hy=math.sin(a) * rho * syr + 30, T=rng.uniform(4.2, 7.5),
                          ph=rng.uniform(0, 1), rise=rng.uniform(40, 120) * rise_k, swx=rng.uniform(18, 46), swy=rng.uniform(8, 24),
                          tw=rng.uniform(1.4, 3.0), twph=rng.uniform(0, 6.28), col=str(rng.choice(palette)), amp=rng.uniform(0.55, 1.0)))
    c.show([m["s"] for m in motes], 0, dur)
    glob = lambda u: smooth(u, 0, 1.0) * (1 - smooth(u, dur - 1.4, dur))  # noqa: E731
    for m in motes:
        ts = set(times_dense(0, dur, 8))
        k = 0
        while True:                      # a key pair at every respawn: the jump happens at alpha 0
            k += 1
            wrap = (k - m["ph"]) * m["T"]
            if wrap >= dur:
                break
            if wrap > 0:
                ts.update([wrap - 0.002, wrap])
        ts = sorted(t for t in ts if 0 <= t <= dur)

        def state(u, m=m):
            q = (u / m["T"] + m["ph"]) % 1.0
            env = math.sin(math.pi * q) ** 1.25
            x = m["hx"] + m["swx"] * math.sin(2 * math.pi * (q * 1.3 + m["ph"] * 3))
            y = m["hy"] + m["rise"] * q + m["swy"] * math.sin(2 * math.pi * (q * 2.1 + m["ph"] * 5))
            tw = 0.62 + 0.38 * math.sin(2 * math.pi * m["tw"] * u + m["twph"])
            return x, y, min(1.0, 1.25 * env * tw * m["amp"] * glob(u))
        c.bone_keys(m["b"], "translate", ts, lambda u, m=m: state(u, m)[:2])
        c.color_keys(m["s"], ts, lambda u, m=m: hexa(m["col"], c.a(state(u, m)[2])))
    return c.result(duration=dur * c.k, motes=n)


def twinkles(c: Ctx, P: dict) -> dict:
    dur = float(P["duration"])
    n = int(P["count"])
    palette = [_hexn(x, "FFFFFF") for x in ([P["color"]] if P["color"] else P["palette"])]
    size_k = float(P["size"])
    grp = c.bone("tw", c.group, 0, 120)
    rng = np.random.default_rng(c.seed + 7)
    used = 0
    for i in range(n):
        a, rad = rng.uniform(0, 2 * math.pi), rng.uniform(130, 300)
        bn = c.bone(f"s{i}", grp, math.cos(a) * rad * 1.15, math.sin(a) * rad * 0.8)
        col = str(rng.choice(palette))
        sl = c.slot(bn, "fx/spark", rng.uniform(70, 140) * size_k, color=hexa(col, c.a(1.0)))
        t_start, life = rng.uniform(0.1, 3.6), rng.uniform(0.55, 0.95)
        rot, rep, gap = rng.uniform(40, 90) * rng.choice([-1, 1]), int(rng.integers(2, 4)), rng.uniform(1.1, 1.9)
        sc, ro, att = [], [], [(0.0, None)]
        for q in range(rep):
            s = t_start + q * gap
            e = s + life
            if e > dur:
                break
            att += [(c.T(s), "fx"), (c.T(e), None)]
            sc += [(c.T(s), 0, 0), (c.T(s + life * 0.42), 1.0, 1.0), (c.T(e), 0, 0)]
            ro += [(c.T(s), 0), (c.T(e), rot)]
        if not sc:
            c.slots.remove(sl)
            continue
        used += 1
        c.ab.bone(bn, "scale", _uniq(sc), "quad_in_out")
        c.ab.bone(bn, "rotate", _uniq(ro), "linear")
        c.ab.slot_attachment(sl, att)
    return c.result(duration=dur * c.k, stars=used)


# ------------------------------------------------------------------ registry
# defaults: every recipe also takes the shared args (x, y, scale, start, duration, color, intensity, seed, into,
# parent, front_of, behind, count, name). "duration" is the life window for window recipes and a time-scale
# (duration / default) for the two one-shots. A default of None / "" means "the recipe's own".
RECIPES: dict[str, dict[str, Any]] = {
    "rune_ring": dict(
        fn=rune_ring, duration=2.7, kind="one-shot", color="FFCD3C",
        summary="Gold rune circle flat on a surface: rings counter-rotate, build up, flash white, fade out.",
        anchor="Subject centre; the ring sits 24 up and is squashed to read as lying flat.",
        options=dict(squash=(0.5, "vertical squash of the ring plane (1 = seen from above, 0.3 = grazing)"),
                     runes=(12, "glyphs between the rings"), spin=(34.0, "deg/s of the outer ring (inner goes -1.6x)"),
                     flash=(1.0, "white flash strength at the peak"))),
    "burst_flare": dict(
        fn=burst_flare, duration=1.8, kind="one-shot", color="FFEE8C", count=10,
        summary="Anamorphic flare with a shock ring and flung sparks: the moment something pops into being.",
        anchor="62 above the subject centre.",
        options=dict(ring_color=("FFE9A0", "shock-ring tint"), spread=(1.0, "how far the sparks fly (x)"))),
    "rim_wisps": dict(
        fn=rim_wisps, duration=5.6, kind="window", color="FFF6DC", count=30,
        summary="Soft feathery fringe all around a footprint; every tuft breathes and flickers on its own.",
        anchor="4, -6 from the subject centre; the ellipse is the footprint.",
        options=dict(rx=(212.0, "footprint half-width"), ry=(110.0, "footprint half-height"),
                     length=(1.0, "tuft length multiplier"))),
    "bloom_aura": dict(
        fn=bloom_aura, duration=5.9, kind="window", color="FF4FA6",
        summary="Coloured halo + inner core + hot spot + rising light column, all breathing.",
        anchor="105 above the subject centre (the flower).",
        options=dict(color2=("C890FF", "inner core colour"), beam=(True, "include the light column"),
                     beam_color=("FFA6DC", "light column tint"))),
    "floor_glow": dict(
        fn=floor_glow, duration=9.8, kind="window", color="FFB84A",
        summary="Warm ellipse of light and a soft streaky reflection under a subject; swells at the climax.",
        anchor="92 below the subject centre.",
        options=dict(reflection=(True, "include the streaky reflection"))),
    "fireflies": dict(
        fn=fireflies, duration=8.2, kind="window", count=34,
        summary="Drifting motes, each with its own respawn period, sway and twinkle (never visibly loops).",
        anchor="40 above the subject centre; spread_x/spread_y set the cloud.",
        options=dict(palette=(["FFE890"] * 6 + ["CFFF8E"] * 2 + ["FFFFFF"] * 2, "colours drawn at random (repeat one to weight it)"),
                     spread_x=(330.0, "cloud half-width"), spread_y=(250.0, "cloud half-height"),
                     rise=(1.0, "upward drift multiplier"), size=(1.0, "mote size multiplier"))),
    "twinkles": dict(
        fn=twinkles, duration=5.8, kind="window", count=9,
        summary="Four-point stars that pop, spin and vanish, two or three times each, around the subject.",
        anchor="120 above the subject centre.",
        options=dict(palette=(["FFFFFF", "FFF2B0", "FFD6F2"], "star colours"), size=(1.0, "star size multiplier"))),
}

# magic_reveal: (recipe, start, duration, front/back order) — timed against the 13.2 s reference clip.
REVEAL = [("floor_glow", 0.9, 11.2), ("rim_wisps", 3.75, 5.9), ("bloom_aura", 3.7, 6.0), ("rune_ring", 2.0, None),
          ("burst_flare", 3.55, None), ("fireflies", 3.4, 9.2), ("twinkles", 3.9, 5.4)]
REVEAL_LENGTH = 13.2

SHARED = ("x", "y", "scale", "start", "duration", "color", "intensity", "seed", "into", "parent", "front_of", "behind",
          "count", "name")


def list_recipes() -> dict:
    out: dict[str, Any] = {}
    for n, d in RECIPES.items():
        out[n] = {
            "summary": d["summary"], "kind": d["kind"], "anchor": d["anchor"], "default_duration": d["duration"],
            "default_color": d.get("color", ""), "default_count": d.get("count", 0),
            "options": {k: {"default": v[0], "what": v[1]} for k, v in d["options"].items()},
        }
    out["magic_reveal"] = {
        "summary": "All seven recipes in one animation, timed like the reference clip (ring 2.0s, flare 3.55s, bloom + wisps + "
                   "twinkles from ~3.8s, fireflies from 3.4s, floor glow 0.9-12s). Hook each fx_<recipe> event to a sound.",
        "kind": "bundle", "anchor": "Subject centre", "default_duration": REVEAL_LENGTH,
        "options": {"skip": {"default": [], "what": "recipe names to leave out"},
                    "overrides": {"default": {}, "what": "{recipe: {param: value}} to retune any member"}},
    }
    return out


def _params(recipe: str, color: str, count: int, duration: float, options: dict | None) -> dict:
    d = RECIPES[recipe]
    P = {k: v[0] for k, v in d["options"].items()}
    opts = dict(options or {})
    bad = [k for k in opts if k not in P]
    if bad:
        raise ValueError(f"unknown option(s) {bad} for {recipe!r}; valid: {sorted(P)}")
    P.update(opts)
    P["color"] = color or d.get("color", "")
    P["count"] = count or d.get("count", 0)
    P["duration"] = duration or d["duration"]
    return P


def apply(project: Project, recipe: str, x: float = 0, y: float = 0, scale: float = 1.0, start: float = 0.0,
          duration: float = 0.0, color: str = "", intensity: float = 1.0, seed: int = 7, into: str = "",
          parent: str = "root", front_of: str = "", behind: str = "", count: int = 0, name: str = "",
          options: dict | None = None) -> dict:
    """Add one recipe (or the ``magic_reveal`` bundle) to the project. Does not save."""
    if recipe == "magic_reveal":
        return _reveal(project, x, y, scale, start, into, parent, front_of, behind, intensity, seed, name, options or {})
    if recipe not in RECIPES:
        raise ValueError(f"unknown recipe {recipe!r}; one of {sorted([*RECIPES, 'magic_reveal'])}")
    if scale <= 0:
        raise ValueError("scale must be > 0")
    d = RECIPES[recipe]
    P = _params(recipe, color, count, duration, options)
    # one-shots retime through k; window recipes take the window length directly
    k = (P["duration"] / d["duration"]) if d["kind"] == "one-shot" else 1.0
    c = Ctx(project, recipe, x, y, scale, start, k, intensity, seed, into, parent, front_of, behind, name)
    return d["fn"](c, P)


def _reveal(project: Project, x, y, scale, start, into, parent, front_of, behind, intensity, seed, name, options) -> dict:
    skip = set(options.get("skip", []))
    over = options.get("overrides", {})
    unknown = (skip | set(over)) - set(RECIPES)
    if unknown:
        raise ValueError(f"unknown recipe(s) {sorted(unknown)} in skip/overrides")
    anim = into or f"{name or 'magic_reveal'}"
    parts, last = [], front_of
    first_behind = behind
    for rec, t0, dur in REVEAL:
        if rec in skip:
            continue
        o = dict(over.get(rec, {}))
        o_opts = o.pop("options", None)
        kw = dict(x=x, y=y, scale=scale, start=start + t0, intensity=intensity, seed=seed, into=anim, parent=parent,
                  front_of=last, behind=first_behind if not parts else "", name="", options=o_opts)
        if dur is not None:
            kw["duration"] = dur
        kw.update(o)
        res = apply(project, rec, **kw)
        parts.append(res)
        last = res["slots"][-1] if res["slots"] else last
    AnimBuilder(project.data, anim, replace=False).event(start + REVEAL_LENGTH, "fx_reveal_end")   # fixes the loop length
    out = {"recipe": "magic_reveal", "animation": anim, "length": REVEAL_LENGTH, "parts": [p["recipe"] for p in parts],
           "bones": sum(p["bones"] for p in parts), "slots": [s for p in parts for s in p["slots"]],
           "events": [p["event"] for p in parts] + ["fx_reveal_end"]}
    return out
