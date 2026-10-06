"""Piñata-slot family for ``fx_recipe``: twelve effects lifted from a candy / piñata slot's free-spins clip (WILD
glow and transform, blue multiplier cells and streak, WILDs merging into a multiplier, coins into the win bar, the
piñata hit with fireballs, a grid of jars bursting into an X5 flare, the win-banner backdrop, confetti).

Every effect is built from a shared kit of 23 neutral pictures (``PICS``): white glows that Spine tints, plus normal-blend
confetti, coin, smoke and two label placeholders. Each picture is also an ``art=`` role, so an artist's texture pack
drops in by name (``art={"glow_soft": "pack/glow_soft.png", ...}``); the motion stays the same.

A pack is rarely tuned like the generated kit: a fuller glow turns overlapping glows into white blobs, a hairline streak
disappears. Two shared options fix that without repainting: ``gain={picture: alpha multiplier}`` and
``thick={picture: [width x, height x]}``. Measured on the first real pack: gain glow_soft 0.5, rays 0.6, flash_burst
0.7, smoke_puff 0.6, glow_core 0.85; thick light_streak [1, 2.4], shine_band [2.6, 1].

Two scales of recipe:
* cell recipes (wild_glow, wild_transform, mult_cell_glow, cell_pop, confetti_burst) are centred on the anchor; one
  cell = ``cell`` units (144). The game plays one per cell.
* board recipes (mult_streak, wild_merge, coins_to_bar, bar_sweep, jar_burst, banner_backdrop) take positions relative
  to the anchor; the defaults are the clip's 5x4 layout on a 721 x 1200 screen with the anchor at the screen centre.
  pinata_hit is anchored on the piñata.

Translate keys are offsets from the setup pose, so every bone that moves is created at 0, 0 and keyed absolutely.
"""
from __future__ import annotations

import math
from typing import Any, Callable

import numpy as np
from PIL import Image, ImageDraw

from .fx import _rgba
from .fx_recipes import RECIPES, ROLES, Ctx, _bez, _hexn, ease_out, hexa, smooth, times_dense

FPS = 30
CELL = 144.0
COLS = [-292.0, -144.0, 4.0, 152.0, 300.0]           # the clip's reels, measured (frame 577 x 960 px x 1.25)
ROWS = [191.0, 43.0, -106.0, -254.0]
BAR = [0.0, -362.0, 625.0, 70.0]                       # win bar x, y, w, h
SIGN = [2.0, 309.0]                                    # the multiplier sign above the reels
PINATA = (248.0, 462.0)
CONFETTI = ["confetti_strip", "confetti_wave", "confetti_circle", "confetti_star", "confetti_curl", "confetti_diamond"]
PALETTE = ["FF4FA3", "FFD23F", "5BE37D", "3FC8FF", "A86BFF", "FF8A3D"]
PINK, CYAN, GOLD, ORANGE, WHITE = "FF5CE6", "38D8FF", "FFC94A", "FF8A2A", "FFFFFF"


# ------------------------------------------------------------------ the picture kit (deterministic, neutral white)
def _g(w: int, h: int):
    y, x = np.mgrid[0:h, 0:w]
    return (x - (w - 1) / 2) / (w / 2), (y - (h - 1) / 2) / (h / 2)


def _white(a: np.ndarray) -> Image.Image:
    return _rgba(np.ones(a.shape), a)


def _rr_sdf(x, y, k=0.55, r=0.25):
    qx, qy = np.abs(x) - k + r, np.abs(y) - k + r
    return np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r


def _rays_alpha(n=512, rays=18, seed=3):
    x, y = _g(n, n)
    r, th = np.hypot(x, y), np.arctan2(y, x)
    rng = np.random.default_rng(seed)
    a = np.zeros_like(r)
    for _ in range(rays):
        c, wd = rng.uniform(-np.pi, np.pi), rng.uniform(0.03, 0.09)
        a += np.exp(-(np.angle(np.exp(1j * (th - c))) / wd) ** 2) * rng.uniform(0.5, 1)
    return np.clip(a, 0, 1) * np.clip(1 - r, 0, 1) ** 1.3 * np.clip(r / 0.15, 0, 1) * 0.9


def _shape(w, h, draw) -> Image.Image:
    """Draw at 4x, downsample, and pad 2 px of clear border (no picture may touch its own edge)."""
    im = Image.new("RGBA", (w * 4, h * 4), (0, 0, 0, 0))
    draw(ImageDraw.Draw(im), w * 4, h * 4)
    out = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
    out.paste(im.resize((w, h), Image.LANCZOS), (2, 2))
    return out


def _star_pts(W, H, n=5, inner=0.43):
    return [(W / 2 + math.cos(a) * W * (0.46 if i % 2 == 0 else 0.46 * inner), H / 2 + math.sin(a) * H * (0.46 if i % 2 == 0 else 0.46 * inner))
            for i, a in enumerate(np.linspace(-np.pi / 2, 1.5 * np.pi, 2 * n + 1)[:-1])]


def _coin() -> Image.Image:
    def d(dr, W, H):
        dr.ellipse((8, 8, W - 8, H - 8), fill=(196, 120, 20, 255))
        dr.ellipse((40, 40, W - 40, H - 40), fill=(255, 196, 58, 255))
        dr.ellipse((70, 70, W - 70, H - 70), fill=(246, 170, 36, 255))
        dr.rounded_rectangle((W / 2 - 22, H / 2 - 120, W / 2 + 22, H / 2 + 120), 20, fill=(255, 226, 120, 255))
    return _shape(128, 128, d)


def _plate(w, h) -> Image.Image:
    """A gold label plate: stands in for the game's number / multiplier art (no font, so it renders anywhere)."""
    def d(dr, W, H):
        dr.rounded_rectangle((6, 6, W - 6, H - 6), H // 2, fill=(150, 70, 10, 255))
        dr.rounded_rectangle((22, 22, W - 22, H - 22), H // 2 - 16, fill=(255, 214, 90, 255))
        dr.rounded_rectangle((40, H * 0.3, W - 40, H * 0.42), 12, fill=(255, 240, 180, 255))
    return _shape(w, h, d)


def _smoke() -> Image.Image:
    x, y = _g(256, 256)
    rng = np.random.default_rng(1)
    a = np.zeros_like(x)
    for _ in range(9):
        cx, cy, s = rng.uniform(-0.35, 0.35), rng.uniform(-0.3, 0.3), rng.uniform(0.25, 0.4)
        a = np.maximum(a, np.exp(-(np.hypot(x - cx, y - cy) / s) ** 4))
    shade = np.clip(0.95 - 0.35 * (y + 0.5), 0.55, 1)
    return _rgba(shade, a * 0.9)


def _pics() -> dict[str, Callable[[], Image.Image]]:
    def glow_soft():
        x, y = _g(256, 256); r = np.hypot(x, y)
        return _white(np.exp(-(r / 0.42) ** 2) * 0.85 * (r < 1))

    def glow_core():
        x, y = _g(256, 256); r = np.hypot(x, y)
        return _white((np.exp(-(r / 0.12) ** 2) + np.exp(-(r / 0.35) ** 2) * 0.35) * (r < 1))

    def cell_glow():
        x, y = _g(256, 256); d = _rr_sdf(x, y)
        return _white(np.exp(-(np.abs(d) / 0.09) ** 2) * 0.9 + np.exp(-(np.maximum(d, 0) / 0.22) ** 2) * 0.35 * (d > 0))

    def light_streak():
        x, y = _g(512, 64)
        return _white(np.exp(-(y / 0.18) ** 2) * np.exp(-(x / 0.55) ** 2) + np.exp(-(y / 0.6) ** 2) * np.exp(-(x / 0.3) ** 2) * 0.3)

    def flare_star():
        x, y = _g(256, 256); r = np.hypot(x, y)
        s = np.exp(-np.abs(y) / 0.03) * np.exp(-np.abs(x) / 0.45) + np.exp(-np.abs(x) / 0.03) * np.exp(-np.abs(y) / 0.45)
        return _white((s * 0.9 + np.exp(-(r / 0.12) ** 2)) * (r < 1))

    def ring():
        x, y = _g(256, 256); r = np.hypot(x, y)
        return _white((np.exp(-((r - 0.75) / 0.06) ** 2) * 0.9 + np.exp(-((r - 0.75) / 0.2) ** 2) * 0.25) * (r < 1))

    def flash_burst():
        x, y = _g(512, 512); r, th = np.hypot(x, y), np.arctan2(y, x)
        edge = 0.45 + 0.12 * np.cos(7 * th) + 0.07 * np.cos(13 * th + 1)
        return _white(np.clip((edge - r) / 0.12, 0, 1) * 0.95 + np.exp(-(r / 0.6) ** 2) * 0.3 * (r < 1))

    def spark():
        x, y = _g(128, 32)
        head = np.where(x > 0.55, np.exp(-((x - 0.55) / 0.15) ** 2), np.exp(-((x - 0.55) / 0.9) ** 2))
        return _white(np.exp(-(y / 0.25) ** 2) * head * np.clip((1 - np.abs(x)) / 0.15, 0, 1) * np.clip((1 - np.abs(y)) / 0.3, 0, 1))

    def energy_trail():
        x, y = _g(512, 64); t = (x + 1) / 2
        a = np.exp(-(y / (0.08 + 0.4 * t)) ** 2) * t ** 1.5 + np.exp(-(np.hypot((x - 0.8) * 4, y) / 0.55) ** 2)
        return _white(a * np.clip((1 - np.abs(x)) / 0.1, 0, 1) * np.clip((1 - np.abs(y)) / 0.25, 0, 1))

    def swirl():
        x, y = _g(256, 256); r, th = np.hypot(x, y), np.arctan2(y, x)
        return _white((0.5 + 0.5 * np.cos(3 * th + 9 * r)) ** 4 * np.clip(1 - r, 0, 1) * np.clip(r / 0.2, 0, 1) * 0.9)

    def bubble_rim():
        x, y = _g(256, 256); r = np.hypot(x, y)
        rim = np.exp(-((r - 0.9) / 0.05) ** 2) * 0.8 + np.clip((r - 0.55) / 0.35, 0, 1) ** 3 * 0.35 * (r < 0.92)
        return _white((rim + np.exp(-(np.hypot(x + 0.4, y + 0.45) / 0.18) ** 2) * 0.9) * (r < 1))

    def shine_band():
        x, y = _g(128, 512)
        return _white((np.exp(-(x / 0.35) ** 2) * 0.9 + np.exp(-(x / 0.08) ** 2) * 0.4) * np.clip((1 - np.abs(y)) / 0.1, 0, 1))

    pics: dict[str, Callable[[], Image.Image]] = dict(
        glow_soft=glow_soft, glow_core=glow_core, cell_glow=cell_glow, light_streak=light_streak, flare_star=flare_star,
        ring=ring, rays=lambda: _white(_rays_alpha()), flash_burst=flash_burst, spark=spark, energy_trail=energy_trail,
        swirl=swirl, bubble_rim=bubble_rim, shine_band=shine_band, smoke_puff=_smoke, coin=_coin,
        mult_number=lambda: _plate(256, 128), x5_label=lambda: _plate(224, 160))
    white = (255, 255, 255, 255)
    pics.update(
        confetti_strip=lambda: _shape(24, 48, lambda d, W, H: d.rounded_rectangle((8, 4, W - 8, H - 4), 10, fill=white)),
        confetti_wave=lambda: _shape(48, 32, lambda d, W, H: d.line([(8 + i * (W - 16) / 12, H / 2 + math.sin(i / 12 * 2 * math.pi) * H * 0.28) for i in range(13)], fill=white, width=22, joint="curve")),
        confetti_circle=lambda: _shape(32, 32, lambda d, W, H: d.ellipse((4, 4, W - 4, H - 4), fill=white)),
        confetti_star=lambda: _shape(40, 40, lambda d, W, H: d.polygon(_star_pts(W, H), fill=white)),
        confetti_curl=lambda: _shape(32, 48, lambda d, W, H: d.arc((8, 8, W * 2 - 30, H - 8), 100, 260, fill=white, width=22)),
        confetti_diamond=lambda: _shape(36, 36, lambda d, W, H: d.polygon([(W / 2, 4), (W - 4, H / 2), (W / 2, H - 4), (4, H / 2)], fill=white)))
    return pics


PICS = _pics()
PIC_ROLES = {
    "glow_soft": "round soft glow, wide falloff, white", "glow_core": "small hot centre with a faint halo",
    "cell_glow": "glowing rounded-square outline (the cell frame)", "light_streak": "thin horizontal light line, fades at both ends",
    "flare_star": "4-point sparkle star", "ring": "thin soft ring", "rays": "uneven sunburst, empty centre",
    "flash_burst": "spiky white blast", "spark": "dot with a short tail, head on the RIGHT",
    "energy_trail": "comet: bright head on the RIGHT, tapering tail", "swirl": "spiral arms, empty centre",
    "bubble_rim": "glass bubble edge + one highlight", "shine_band": "soft vertical light bar",
    "smoke_puff": "grey cloud (normal blend)", "coin": "the game's coin (normal blend)",
    "mult_number": "the multiplier number art (normal blend)", "x5_label": "the X-multiplier label art (normal blend)",
    **{n: f"confetti piece ({n.split('_')[1]}), white, normal blend" for n in CONFETTI},
}


# ------------------------------------------------------------------ helpers
def _s(c: Ctx, bone: str, pic: str, width: float, height: float | None = None, blend: str = "additive",
       anchor: str = "center") -> str:
    """A slot showing kit picture `pic` (or the user's art for that role). Remembers the picture for gain / thick."""
    ox = -width / 2 if anchor == "right" else 0.0
    nm = c.slot(bone, f"fx/pinata_{pic}", width, height=height, make=PICS[pic], blend=blend, role=pic,
                stretch=height is not None, ox=ox, anchor=anchor)
    c.__dict__.setdefault("_pic", {})[nm] = pic
    return nm


def _h(c: Ctx, col: str, a: float) -> str:
    return hexa(col, c.a(max(0.0, a)))


def _finish(c: Ctx, P: dict, **extra) -> dict:
    """Apply the shared gain / thick options to this recipe's own slots, then return the result."""
    gain, thick = dict(P.get("gain") or {}), dict(P.get("thick") or {})
    bad = [k for k in [*gain, *thick] if k not in PICS]
    if bad:
        raise ValueError(f"gain/thick name unknown picture(s) {bad}; pictures: {sorted(PICS)}")
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


def backout(u: float, s: float = 1.9) -> float:
    u = min(max(u, 0.0), 1.0) - 1
    return 1 + (s + 1) * u ** 3 + s * u ** 2


def bell(t: float, t0: float, rise: float, fall: float) -> float:
    return smooth(t, t0, t0 + rise) * (1 - smooth(t, t0 + rise, t0 + rise + fall))


def bez(p0, p1, p2, u):
    return tuple(float(v) for v in _bez(p0, p1, p2, u)[:2])


def _cells(P: dict, key: str = "cells") -> list[tuple[float, float]]:
    return [(float(a), float(b)) for a, b in P[key]]


# ====================================================================== cell recipes (centred on the anchor)
def wild_glow(c: Ctx, P: dict) -> dict:
    D, CL = float(P["duration"]), float(P["cell"])
    col = _hexn(P["color"], PINK)
    b_g, b_c = c.bone("glow"), c.bone("core")
    s_g = _s(c, b_g, "glow_soft", CL * 1.9)
    s_c = _s(c, b_c, "glow_core", CL * 1.2)
    tilt_deg = float(P["tilt"])
    piv = c.bone("orbit", rot=tilt_deg, sy=float(P["squash"]))
    b_r = c.bone("ring", piv)
    s_r = _s(c, b_r, "ring", CL * 1.3)
    stars = []
    for i in range(int(P["stars"])):
        b = c.bone(f"star{i}")
        stars.append((b, _s(c, b, "flare_star", 46.0), 2 * math.pi * i / max(1, int(P["stars"]))))
    c.show([s_g, s_c, s_r] + [s for _, s, _ in stars], 0, None)
    ts = times_dense(0, D, FPS)
    w = lambda t: math.sin(2 * math.pi * t / D)  # noqa: E731
    c.bone_keys(b_g, "scale", ts, lambda t: (1 + 0.1 * w(t),) * 2)
    c.color_keys(s_g, ts, lambda t: _h(c, col, 0.65 + 0.25 * w(t)))
    c.bone_keys(b_c, "scale", ts, lambda t: (0.9 + 0.1 * w(t),) * 2)
    c.color_keys(s_c, ts, lambda t: _h(c, "FFE0F6", 0.35 + 0.15 * w(t)))
    c.bone_keys(b_r, "scale", ts, lambda t: (1 + 0.05 * w(t),) * 2)
    c.color_keys(s_r, ts, lambda t: _h(c, col, 0.55 + 0.2 * w(t)))
    rad, tilt, sq = CL * 0.65, math.radians(tilt_deg), float(P["squash"])
    for b, s, ph in stars:
        def pos(t, ph=ph):
            a = 2 * math.pi * t / D + ph
            x, y = rad * math.cos(a), rad * sq * math.sin(a)
            return (x * math.cos(tilt) - y * math.sin(tilt), x * math.sin(tilt) + y * math.cos(tilt))
        c.bone_keys(b, "translate", ts, pos)
        c.bone_keys(b, "rotate", ts, lambda t: 90.0 * t / D)            # a 4-point star: 90 degrees per loop is seamless
        c.color_keys(s, ts, lambda t, ph=ph: _h(c, WHITE, 0.45 + 0.5 * max(0.0, -math.sin(2 * math.pi * t / D + ph))))
    return _finish(c, P, duration=D, loop=D)


def _wild_flash(c: Ctx, P: dict) -> dict:
    """The WILD transform as the reference clip plays it: the cell flashes white with a pink rim (peak in 1-2 frames),
    sparkles fly, the WILD art pops in with overshoot (option wild= its bone, through a carrier), and the pink glow it
    leaves equals wild_glow's first frame (seamless hand-off)."""
    D, POP, CL = 0.6, 0.04, float(P["cell"])
    col2 = _hexn(P["color2"], PINK)
    b_pk = c.bone("after")
    s_pk = _s(c, b_pk, "glow_soft", CL * 1.9)
    b_cf, b_co, b_ri = c.bone("cellflash"), c.bone("core"), c.bone("ring")
    s_cf = _s(c, b_cf, "cell_glow", CL * 1.18)
    s_co = _s(c, b_co, "glow_core", CL * 1.5)
    s_ri = _s(c, b_ri, "ring", CL * 1.25)
    rng = np.random.default_rng(c.seed + 3)
    stars = []
    for i in range(6):
        a = 2 * math.pi * (i + 0.5) / 6 + rng.uniform(-0.25, 0.25)
        bn = c.bone(f"st{i}")
        stars.append((bn, _s(c, bn, "flare_star", float(rng.uniform(34, 50))), a))
    c.show([s_pk], 0, None)
    c.show([s_cf, s_co, s_ri] + [s for _, s, _ in stars], 0, D)
    ts = times_dense(0, D, FPS)
    fl = lambda t: smooth(t, 0.0, POP) * math.exp(-max(0.0, t - POP) / 0.09)  # noqa: E731   1-2 frame rise, fast decay
    c.color_keys(s_cf, ts, lambda t: _h(c, WHITE if t < 0.12 else col2, max(fl(t), 0.8 * bell(t, 0.02, 0.05, 0.35))))
    c.bone_keys(b_cf, "scale", ts, lambda t: (1.12 - 0.12 * ease_out(t / 0.2, 3),) * 2)
    c.color_keys(s_co, ts, lambda t: _h(c, "FFF4FC", fl(t)))
    c.bone_keys(b_co, "scale", ts, lambda t: (0.6 + 0.5 * ease_out(t / 0.15),) * 2)
    c.bone_keys(b_ri, "scale", ts, lambda t: (0.4 + 0.9 * ease_out(t / 0.4, 2.4),) * 2)
    c.color_keys(s_ri, ts, lambda t: _h(c, "FFB8F2", 0.85 * bell(t, 0.0, 0.04, 0.36)))
    c.color_keys(s_pk, ts, lambda t: _h(c, col2, 0.65 * smooth(t, 0.04, D) + 0.35 * bell(t, 0.0, 0.05, 0.3)))
    c.bone_keys(b_pk, "scale", ts, lambda t: (1.0 + 0.25 * bell(t, 0.0, 0.05, 0.4),) * 2)
    for bn, s, a in stars:
        rr = lambda t: CL * (0.3 + 0.5 * ease_out(t / 0.45, 2.5))  # noqa: E731
        c.bone_keys(bn, "translate", ts, lambda t, a=a: (math.cos(a) * rr(t), math.sin(a) * rr(t)))
        c.bone_keys(bn, "rotate", ts, lambda t: 150.0 * t)
        c.color_keys(s, ts, lambda t: _h(c, WHITE, bell(t, 0.01, 0.05, 0.4)))
    if P.get("wild"):
        from .fx_reels import _carrier, _merge_keys
        car = _carrier(c, str(P["wild"]), "wildpop")
        _merge_keys(c, car, "scale", ts, lambda t: (backout(t / 0.18, 2.4) if t > 0 else 0.0,) * 2, "mul")
    c.ab.event(c.T(POP), "wild_pop")
    return _finish(c, P, duration=D * c.k, pop_at=c.T(POP), style="flash")


def wild_transform(c: Ctx, P: dict) -> dict:
    if P.get("style", "flash") == "flash":
        return _wild_flash(c, P)
    if P["style"] != "bubble":
        raise ValueError("wild_transform style must be flash | bubble")
    D, POP, CL = 1.2, 0.62, float(P["cell"])
    col, col2 = _hexn(P["color"], CYAN), _hexn(P["color2"], PINK)
    b_bg, b_pk = c.bone("bg"), c.bone("after")
    s_bg = _s(c, b_bg, "glow_soft", CL * 1.7)
    s_pk = _s(c, b_pk, "glow_soft", CL * 1.9)                            # = wild_glow's glow at its t=0: seamless hand-off
    b_bub = c.bone("bubble")
    b_sw, b_sw2 = c.bone("swirl", b_bub), c.bone("swirl2", b_bub)
    s_sw = _s(c, b_sw, "swirl", CL * 0.95)
    s_sw2 = _s(c, b_sw2, "swirl", CL * 0.7)
    s_bub = _s(c, b_bub, "bubble_rim", CL * 1.05)
    b_fl, b_co, b_ri = c.bone("flash"), c.bone("core"), c.bone("ring")
    s_ri = _s(c, b_ri, "ring", CL * 1.3)
    s_fl = _s(c, b_fl, "flash_burst", CL * 1.6)
    s_co = _s(c, b_co, "glow_core", CL * 1.6)
    rng = np.random.default_rng(c.seed + 3)
    sparks = []
    for i in range(10):
        a = 2 * math.pi * i / 10 + rng.uniform(-0.2, 0.2)
        b = c.bone(f"sp{i}", rot=math.degrees(a))
        sparks.append((b, _s(c, b, "spark", float(rng.uniform(50, 80))), a, float(rng.uniform(0.8, 1.2)) * CL * 0.85))
    c.show([s_bg, s_pk, s_sw, s_sw2, s_bub], 0, None)
    c.show([s_ri, s_fl, s_co] + [s for _, s, _, _ in sparks], POP - 0.02, D)
    ts = times_dense(0, D, FPS)
    grow = lambda t: backout(t / 0.3)  # noqa: E731
    gone = lambda t: smooth(t, POP, POP + 0.12)  # noqa: E731
    squeeze = lambda t: 0.07 * math.sin(math.pi * min(max((t - 0.32) / (POP - 0.32), 0), 1)) ** 2  # noqa: E731
    c.bone_keys(b_bub, "scale", ts, lambda t: ((grow(t) + squeeze(t)) * (1 + 0.3 * gone(t)), (grow(t) - squeeze(t) * 0.6) * (1 + 0.3 * gone(t))))
    c.color_keys(s_bub, ts, lambda t: _h(c, "9FEFFF", 0.95 * min(1.0, t / 0.08) * (1 - gone(t))))
    c.bone_keys(b_sw, "rotate", ts, lambda t: -900.0 * t)
    c.bone_keys(b_sw2, "rotate", ts, lambda t: 520.0 * t)
    c.color_keys(s_sw, ts, lambda t: _h(c, col, 0.95 * min(1.0, t / 0.1) * (1 - gone(t))))
    c.color_keys(s_sw2, ts, lambda t: _h(c, WHITE, 0.5 * min(1.0, t / 0.1) * (1 - gone(t))))
    c.bone_keys(b_bg, "scale", ts, lambda t: (0.6 + 0.4 * grow(t) + 0.2 * gone(t),) * 2)
    c.color_keys(s_bg, ts, lambda t: _h(c, col, 0.6 * min(1.0, t / 0.15) * (1 - smooth(t, POP, POP + 0.3))))
    c.color_keys(s_pk, ts, lambda t: _h(c, col2, 0.65 * smooth(t, POP + 0.05, D) + 0.35 * bell(t, POP, 0.05, 0.3)))
    c.bone_keys(b_pk, "scale", ts, lambda t: (1.0 + 0.25 * bell(t, POP, 0.05, 0.4),) * 2)
    tp = times_dense(POP - 0.02, D, FPS)
    q = lambda t: max(0.0, t - POP)  # noqa: E731
    on = lambda t: smooth(t, POP - 0.02, POP + 0.02)  # noqa: E731
    c.bone_keys(b_fl, "scale", tp, lambda t: (0.3 + 0.95 * ease_out(q(t) / 0.22, 2.5),) * 2)
    c.bone_keys(b_fl, "rotate", tp, lambda t: 40.0 * q(t))
    c.color_keys(s_fl, tp, lambda t: _h(c, WHITE, on(t) * math.exp(-q(t) / 0.12)))
    c.bone_keys(b_co, "scale", tp, lambda t: (0.5 + 0.8 * ease_out(q(t) / 0.15),) * 2)
    c.color_keys(s_co, tp, lambda t: _h(c, "FFF0FA", on(t) * math.exp(-q(t) / 0.18)))
    c.bone_keys(b_ri, "scale", tp, lambda t: (0.3 + 1.4 * ease_out(q(t) / 0.45, 2.4),) * 2)
    c.color_keys(s_ri, tp, lambda t: _h(c, "FFB8F2", 0.9 * smooth(t, POP - 0.02, POP + 0.03) * (1 - smooth(q(t), 0.05, 0.45))))
    for b, s, a, dist in sparks:
        r_ = lambda t, dist=dist: 0.25 * CL + dist * ease_out(q(t) / 0.45, 2.2)  # noqa: E731
        c.bone_keys(b, "translate", tp, lambda t, a=a, r_=r_: (math.cos(a) * r_(t), math.sin(a) * r_(t)))
        c.bone_keys(b, "scale", tp, lambda t: (1.2 - 0.9 * smooth(q(t), 0.0, 0.45), 1.0 - 0.5 * smooth(q(t), 0.1, 0.45)))
        c.color_keys(s, tp, lambda t: _h(c, "FFE6FA", 1 - smooth(q(t), 0.15, 0.45)))
    c.ab.event(c.T(POP), "wild_pop")
    return _finish(c, P, duration=D * c.k, pop_at=c.T(POP))


def mult_cell_glow(c: Ctx, P: dict) -> dict:
    D, CL = float(P["duration"]), float(P["cell"])
    col = _hexn(P["color"], CYAN)
    b_g, b_f = c.bone("glow"), c.bone("frame")
    s_g = _s(c, b_g, "glow_soft", CL * 1.6)
    s_f = _s(c, b_f, "cell_glow", CL * 1.18)
    rng = np.random.default_rng(c.seed + 4)
    tw = []
    for i in range(int(P["twinkles"])):
        b = c.bone(f"tw{i}", x=float(rng.uniform(-0.42, 0.42)) * CL, y=float(rng.uniform(-0.42, 0.42)) * CL)
        tw.append((b, _s(c, b, "flare_star", float(rng.uniform(26, 40))), float(rng.uniform(0, 2 * math.pi))))
    c.show([s_g, s_f] + [s for _, s, _ in tw], 0, None)
    ts = times_dense(0, D, FPS)
    w = lambda t: math.sin(2 * math.pi * t / D)  # noqa: E731
    c.color_keys(s_f, ts, lambda t: _h(c, col, 0.72 + 0.25 * w(t)))
    c.bone_keys(b_f, "scale", ts, lambda t: (1 + 0.02 * w(t),) * 2)
    c.color_keys(s_g, ts, lambda t: _h(c, col, 0.35 + 0.15 * w(t)))
    for b, s, ph in tw:
        k = lambda t, ph=ph: max(0.0, math.sin(2 * math.pi * t / D + ph)) ** 6  # noqa: E731
        c.color_keys(s, ts, lambda t, k=k: _h(c, WHITE, k(t)))
        c.bone_keys(b, "scale", ts, lambda t, k=k: (0.4 + 0.8 * k(t),) * 2)
        c.bone_keys(b, "rotate", ts, lambda t: 90.0 * t / D)
    return _finish(c, P, duration=D, loop=D)


def cell_pop(c: Ctx, P: dict) -> dict:
    D, CL = 0.6, float(P["cell"])
    col = _hexn(P["color"], GOLD)
    b_g, b_f, b_r = c.bone("glow"), c.bone("frame"), c.bone("ring")
    s_g = _s(c, b_g, "glow_soft", CL * 1.8)
    s_f = _s(c, b_f, "cell_glow", CL * 1.18)
    s_r = _s(c, b_r, "ring", CL * 1.2)
    st = []
    for i in range(6):
        b = c.bone(f"st{i}")
        st.append((b, _s(c, b, "flare_star", 40.0), 2 * math.pi * (i + 0.5) / 6))
    c.show([s_g, s_f, s_r] + [s for _, s, _ in st], 0, D)
    ts = times_dense(0, D, FPS)
    c.color_keys(s_g, ts, lambda t: _h(c, col, 0.8 * bell(t, 0, 0.05, 0.4)))
    c.bone_keys(b_f, "scale", ts, lambda t: (1.25 - 0.25 * ease_out(t / 0.25, 3),) * 2)
    c.color_keys(s_f, ts, lambda t: _h(c, "FFF2C0" if t < 0.12 else col, bell(t, 0, 0.03, 0.5)))
    c.bone_keys(b_r, "scale", ts, lambda t: (0.5 + 1.0 * ease_out(t / 0.45, 2.4),) * 2)
    c.color_keys(s_r, ts, lambda t: _h(c, col, 0.85 * bell(t, 0, 0.03, 0.42)))
    for b, s, a in st:
        rr = lambda t: CL * (0.35 + 0.45 * ease_out(t / D, 2.5))  # noqa: E731
        c.bone_keys(b, "translate", ts, lambda t, a=a: (math.cos(a) * rr(t), math.sin(a) * rr(t)))
        c.bone_keys(b, "rotate", ts, lambda t: 120.0 * t)
        c.color_keys(s, ts, lambda t: _h(c, WHITE, bell(t, 0.02, 0.06, 0.45)))
    return _finish(c, P, duration=D * c.k)


def _confetti(c: Ctx, rng, i: int, size: tuple[float, float], palette: list[str]):
    shape = CONFETTI[i % len(CONFETTI)]
    b = c.bone(f"cf{i}")
    s = _s(c, b, shape, float(rng.uniform(*size)) * (0.8 if shape == "confetti_circle" else 1.0), blend="normal")
    return (b, s, palette[int(rng.integers(len(palette)))], float(rng.uniform(-540, 540)), float(rng.uniform(5, 11)),
            float(rng.uniform(0, 2 * math.pi)), float(rng.uniform(10, 26)))


def confetti_burst(c: Ctx, P: dict) -> dict:
    D, N = 2.4, int(P["count"])
    pal = [_hexn(x, "FFFFFF") for x in P["palette"]]
    rng = np.random.default_rng(c.seed + 6)
    g, k = -1500.0, 3.2
    lo, hi = P["spread"]
    for i in range(N):
        b, s, col, spin, flip, ph, sway = _confetti(c, rng, i, (26, 40), pal)
        ang = math.radians(float(rng.uniform(lo, hi)))
        sp = float(rng.uniform(500, 1050)) * float(P["power"])
        vx, vy = sp * math.cos(ang), sp * math.sin(ang)
        d = float(rng.uniform(0, 0.06))
        c.show([s], d, D)
        ts = times_dense(d, D, FPS)

        def pos(t, vx=vx, vy=vy, d=d, ph=ph, sway=sway):
            q = max(0.0, t - d)
            e = (1 - math.exp(-k * q)) / k
            return (vx * e + sway * math.sin(6.0 * q + ph) * smooth(q, 0.3, 0.8), (vy + g / k) * e - g * q / k)
        c.bone_keys(b, "translate", ts, pos)
        c.bone_keys(b, "rotate", ts, lambda t, spin=spin, d=d: spin * (t - d))
        c.bone_keys(b, "scale", ts, lambda t, flip=flip, ph=ph, d=d: (math.cos(flip * (t - d) + ph), 1.0))
        c.color_keys(s, ts, lambda t, col=col: _h(c, col, 1 - smooth(t, D - 0.5, D)))
    return _finish(c, P, duration=D * c.k, pieces=N)


# ====================================================================== board recipes (positions relative to the anchor)
def mult_streak(c: Ctx, P: dict) -> dict:
    D, CL = 1.8, float(P["cell"])
    col = _hexn(P["color"], CYAN)
    cells = _cells(P)
    Y = sum(y for _, y in cells) / len(cells)
    xs = [x for x, _ in cells]
    if P["to"] not in ("bar", "sign"):
        raise ValueError("mult_streak to must be bar | sign")
    tgt = P["sign"] if P["to"] == "sign" else P["bar"][:2]
    NX, SX, SY = float(P["number"][0]), float(tgt[0]), float(tgt[1])
    NY = float(P["number"][1]) if P["number"][1] is not None else Y
    span = (max(xs) - min(xs)) + CL * 1.6
    parts = []
    for i, (x, y) in enumerate(sorted(cells)):
        b = c.bone(f"cell{i}", x=x, y=y)
        bg = c.bone(f"cellg{i}", b)
        parts.append((b, _s(c, bg, "glow_soft", CL * 1.5), _s(c, b, "cell_glow", CL * 1.15), 0.05 * i))
    b_long = c.bone("long", x=(max(xs) + min(xs)) / 2, y=Y)
    s_long = _s(c, b_long, "light_streak", span * 1.2, height=110.0)
    b_head = c.bone("head")
    s_head = _s(c, b_head, "light_streak", 420.0, height=90.0)
    b_hc = c.bone("headcore", b_head)
    s_hc = _s(c, b_hc, "glow_core", 150.0)
    b_num = c.bone("num")
    b_ng = c.bone("numglow", b_num)
    s_ng = _s(c, b_ng, "glow_soft", 260.0)
    s_num = _s(c, b_num, "mult_number", 130.0, blend="normal")
    b_pf = c.bone("signflash" if P["to"] == "sign" else "barflash", x=SX, y=SY)
    s_pf = _s(c, b_pf, "flash_burst", 220.0)
    c.show([s for _, a, b_, _ in parts for s in (a, b_)] + [s_long, s_head, s_hc], 0, 1.3)
    if P["to"] == "sign":
        c.show([s_ng, s_num], 0.18, 1.62)
        c.show([s_pf], 1.5, D)
    else:
        c.show([s_ng, s_num], 0.05, 1.12)
        c.show([s_pf], 1.03, 1.5)
    ts = times_dense(0, D, FPS)
    for b, sg, sf, d in parts:
        lit = lambda t, d=d: bell(t, d + 0.1, 0.08, 0.95) * (0.8 + 0.2 * math.sin(2 * math.pi * 2.5 * t))  # noqa: E731
        c.color_keys(sf, ts, lambda t, lit=lit: _h(c, col, lit(t)))
        c.color_keys(sg, ts, lambda t, lit=lit: _h(c, col, 0.55 * lit(t)))
        c.bone_keys(b, "scale", ts, lambda t, d=d: (1 + 0.12 * bell(t, d + 0.1, 0.06, 0.25),) * 2)
    x0, x1 = min(xs) - CL, max(xs) + CL
    c.bone_keys(b_head, "translate", ts, lambda t: (x0 + (x1 - x0) * smooth(t, 0.08, 0.55), Y))
    c.color_keys(s_head, ts, lambda t: _h(c, "BFF4FF", bell(t, 0.06, 0.06, 0.5)))
    c.color_keys(s_hc, ts, lambda t: _h(c, WHITE, 0.9 * bell(t, 0.06, 0.06, 0.5)))
    c.bone_keys(b_long, "scale", ts, lambda t: (max(0.001, smooth(t, 0.08, 0.55)), 1.0 - 0.6 * smooth(t, 0.55, 1.2)))
    c.color_keys(s_long, ts, lambda t: _h(c, col, 0.9 * bell(t, 0.08, 0.4, 0.7)))
    if P["to"] == "sign":                       # the number arcs up into the multiplier sign
        fly = lambda t: smooth(t, 1.25, 1.55)  # noqa: E731
        c.bone_keys(b_num, "translate", ts, lambda t: (NX + (SX - NX) * fly(t), NY + (SY - NY) * fly(t) + 60 * math.sin(math.pi * fly(t))))
        c.bone_keys(b_num, "scale", ts, lambda t: ((backout((t - 0.18) / 0.3, 3.0) if t < 1.25 else 1.0) * (1 - 0.55 * fly(t)),) * 2)
        c.color_keys(s_num, ts, lambda t: _h(c, WHITE, 1 - smooth(t, 1.5, 1.6)))
        c.color_keys(s_ng, ts, lambda t: _h(c, GOLD, 0.7 * smooth(t, 0.18, 0.3) * (1 - smooth(t, 1.45, 1.6)) * (0.8 + 0.2 * math.sin(4 * math.pi * t))))
        c.bone_keys(b_pf, "scale", ts, lambda t: (0.3 + 0.9 * ease_out((t - 1.5) / 0.25, 2.5) if t >= 1.5 else 0.3,) * 2)
        c.color_keys(s_pf, ts, lambda t: _h(c, "FFF2C8", math.exp(-max(0.0, t - 1.52) / 0.1) * smooth(t, 1.5, 1.53)))
        c.ab.event(c.T(1.52), "mult_to_sign")
        return _finish(c, P, duration=D * c.k, to="sign")
    # the reference clip: revealed small, punched in (6-11 f, ease out), held, then DROPPED into the win bar
    # (4-5 f, ease in = accelerating, shrinking), the bar flashing on arrival
    R0, P0, P1, F0, F1 = 0.05, 0.5, 0.77, 0.89, 1.06
    drop = lambda t: smooth(t, F0, F1) ** 1.8  # noqa: E731   accelerates into the bar
    def num_scale(t):
        if t < P0:
            return 0.45
        if t < F0:
            return 0.45 + (1.6 - 0.45) * backout((t - P0) / (P1 - P0), 2.0)
        return 1.6 - 1.1 * drop(t)
    c.bone_keys(b_num, "translate", ts, lambda t: (NX + (SX - NX) * drop(t), NY + (SY - NY) * drop(t)))
    c.bone_keys(b_num, "scale", ts, lambda t: (num_scale(t),) * 2)
    c.color_keys(s_num, ts, lambda t: _h(c, WHITE, smooth(t, R0, R0 + 0.03) * (1 - smooth(t, F1, F1 + 0.04))))
    c.color_keys(s_ng, ts, lambda t: _h(c, GOLD, 0.7 * smooth(t, P0, P1) * (1 - smooth(t, F0, F1))))
    c.bone_keys(b_pf, "scale", ts, lambda t: (1.6, 0.25 + 0.5 * ease_out((t - F1) / 0.2, 2.5) if t >= F1 else 0.25))
    c.color_keys(s_pf, ts, lambda t: _h(c, "FFF2C8", smooth(t, F1 - 0.02, F1 + 0.01) * math.exp(-max(0.0, t - F1) / 0.12)))
    c.ab.event(c.T(F1), "mult_to_bar")
    return _finish(c, P, duration=D * c.k, to="bar", lands_at=c.T(F1))


def wild_merge(c: Ctx, P: dict) -> dict:
    D, ARR, CL = 1.6, 0.9, float(P["cell"])
    col = _hexn(P["color"], CYAN)
    src = _cells(P, "sources")
    T = (float(P["target"][0]), float(P["target"][1]))
    rng = np.random.default_rng(c.seed + 8)
    comets = []
    for i, (sx, sy) in enumerate(src):
        bs = c.bone(f"src{i}", x=sx, y=sy)
        s_src = _s(c, bs, "glow_soft", CL * 1.5)
        b = c.bone(f"comet{i}")
        s = _s(c, b, "energy_trail", 320.0, height=80.0, anchor="right")    # the head (right end) sits on the bone
        bh = c.bone(f"chead{i}")
        sh = _s(c, bh, "glow_core", 150.0)
        dx, dy = T[0] - sx, T[1] - sy
        L = math.hypot(dx, dy) or 1.0
        bend = float(rng.choice([-1, 1])) * float(rng.uniform(0.25, 0.45)) * L
        ctrl = ((sx + T[0]) / 2 - dy / L * bend, (sy + T[1]) / 2 + dx / L * bend)
        comets.append((s_src, b, s, bh, sh, (sx, sy), ctrl, 0.22 + 0.05 * i))
    b_gl, b_ri, b_fl = c.bone("tglow", x=T[0], y=T[1]), c.bone("ring", x=T[0], y=T[1]), c.bone("flash", x=T[0], y=T[1])
    s_gl = _s(c, b_gl, "glow_soft", 420.0)
    s_ri = _s(c, b_ri, "ring", 240.0)
    s_fl = _s(c, b_fl, "flash_burst", 300.0)
    b_num = c.bone("num", x=T[0], y=T[1])
    s_num = _s(c, b_num, "mult_number", 150.0, blend="normal")
    ts = times_dense(0, D, FPS)
    tr = 0.5
    for s_src, b, s, bh, sh, p0, ctrl, t0 in comets:
        c.show([s_src], 0, t0 + 0.3)
        c.color_keys(s_src, ts, lambda t, t0=t0: _h(c, col, 0.8 * bell(t, 0, 0.12, t0 + 0.1)))
        c.show([s, sh], t0, t0 + tr + 0.04)
        tt = times_dense(t0, t0 + tr, FPS * 2)
        u = lambda t, t0=t0: smooth(t, t0, t0 + tr) ** 1.3  # noqa: E731
        at = lambda t, p0=p0, ctrl=ctrl, u=u: bez(p0, ctrl, T, u(t))  # noqa: E731
        tan = [_bez(p0, ctrl, T, u(t))[2] for t in tt]
        amap = dict(zip(tt, np.degrees(np.unwrap(np.radians(tan)))))  # unwrapped: no 360-degree flips mid-flight
        c.bone_keys(b, "translate", tt, at)
        c.bone_keys(bh, "translate", tt, at)
        c.bone_keys(b, "rotate", tt, lambda t, amap=amap: float(amap[t]))
        c.bone_keys(b, "scale", tt, lambda t, t0=t0: (0.4 + 0.8 * math.sin(math.pi * min(max((t - t0) / tr, 0), 1)), 1.0))
        c.color_keys(s, tt, lambda t, t0=t0: _h(c, col, min(1.0, (t - t0) / 0.06)))
        c.color_keys(sh, tt, lambda t, t0=t0: _h(c, WHITE, min(1.0, (t - t0) / 0.06)))
    c.show([s_gl, s_ri, s_fl], ARR - 0.05, D)
    c.show([s_num], ARR, D)
    q = lambda t: max(0.0, t - ARR)  # noqa: E731
    c.bone_keys(b_fl, "scale", ts, lambda t: (0.3 + 1.0 * ease_out(q(t) / 0.22, 2.5),) * 2)
    c.color_keys(s_fl, ts, lambda t: _h(c, "D8FAFF", smooth(t, ARR - 0.05, ARR) * math.exp(-q(t) / 0.13)))
    c.bone_keys(b_ri, "scale", ts, lambda t: (0.3 + 1.6 * ease_out(q(t) / 0.5, 2.4),) * 2)
    c.color_keys(s_ri, ts, lambda t: _h(c, col, 0.9 * smooth(t, ARR - 0.05, ARR) * (1 - smooth(q(t), 0.05, 0.5))))
    c.color_keys(s_gl, ts, lambda t: _h(c, col, 0.75 * smooth(t, ARR - 0.05, ARR + 0.05) * (1 - 0.6 * smooth(q(t), 0.1, 0.7))))
    c.bone_keys(b_num, "scale", ts, lambda t: (backout(q(t) / 0.32, 3.0),) * 2)
    c.ab.event(c.T(ARR), "merge_hit")
    return _finish(c, P, duration=D * c.k, hit_at=c.T(ARR))


def coins_to_bar(c: Ctx, P: dict) -> dict:
    D, N = 1.9, int(P["count"])
    col = _hexn(P["color"], GOLD)
    cells = _cells(P)
    bx, by, bw, bh = (float(v) for v in P["bar"])
    rng = np.random.default_rng(c.seed + 9)
    b_bar = c.bone("barglow", x=bx, y=by)
    s_bar = _s(c, b_bar, "glow_soft", bw * 1.15, height=bh * 2.4)
    coins = []
    for i in range(N):
        sx, sy = cells[int(rng.integers(len(cells)))]
        sx, sy = sx + float(rng.uniform(-30, 30)), sy + float(rng.uniform(-30, 30))
        tx = bx + float(rng.uniform(-0.32, 0.32)) * bw
        t0, tr = 0.05 + 0.07 * i + float(rng.uniform(0, 0.04)), float(rng.uniform(0.55, 0.75))
        b = c.bone(f"coin{i}")
        ctrl = ((sx + tx) / 2 + float(rng.uniform(-80, 80)), max(sy, by) + float(rng.uniform(140, 260)))
        coins.append([b, _s(c, b, "coin", float(rng.uniform(62, 80)), blend="normal"), c.bone(f"hit{i}", x=tx, y=by), None,
                      (sx, sy), ctrl, (tx, by), t0, tr, float(rng.uniform(14, 22))])
    for cn in coins:                                   # flashes after ALL coins: one blend run each (draw calls)
        cn[3] = _s(c, cn[2], "flare_star", 90.0)
    arrivals = [cn[7] + cn[8] for cn in coins]
    ts = times_dense(0, D, FPS)
    c.show([s_bar], 0, D)
    c.color_keys(s_bar, ts, lambda t: _h(c, col, min(0.85, sum(0.45 * math.exp(-((t - a) / 0.09) ** 2) for a in arrivals))))
    for b, s, bf, sf, p0, ctrl, p1, t0, tr, spin in coins:
        c.show([s], t0, t0 + tr)
        c.show([sf], t0 + tr - 0.02, t0 + tr + 0.35)
        tt = times_dense(t0, t0 + tr, FPS)
        c.bone_keys(b, "translate", tt, lambda t, p0=p0, ctrl=ctrl, p1=p1, t0=t0, tr=tr: bez(p0, ctrl, p1, ((t - t0) / tr) ** 1.25))
        sz = lambda t, t0=t0, tr=tr: backout((t - t0) / 0.18) * (1 - 0.35 * (t - t0) / tr)  # noqa: E731
        c.bone_keys(b, "scale", tt, lambda t, t0=t0, spin=spin, sz=sz: (math.cos(spin * (t - t0)) * sz(t), sz(t)))
        a0 = t0 + tr
        th = times_dense(a0 - 0.02, a0 + 0.35, FPS)
        c.bone_keys(bf, "scale", th, lambda t, a0=a0: (0.3 + 0.9 * ease_out((t - a0) / 0.15),) * 2)
        c.bone_keys(bf, "rotate", th, lambda t, a0=a0: 90.0 * (t - a0))
        c.color_keys(sf, th, lambda t, a0=a0: _h(c, "FFF4C8", math.exp(-max(0.0, t - a0) / 0.1)))
    return _finish(c, P, duration=D * c.k, arrivals=[c.T(a) for a in sorted(arrivals)])


def bar_sweep(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    col = _hexn(P["color"], GOLD)
    bx, by, bw, bh = (float(v) for v in P["bar"])
    b_b = c.bone("band", rot=float(P["slant"]))
    s_b = _s(c, b_b, "shine_band", 110.0, height=bh * 1.4)
    b_e, b_e2 = c.bone("edge"), c.bone("edge2")
    s_e = _s(c, b_e, "light_streak", 420.0, height=70.0)
    s_e2 = _s(c, b_e2, "light_streak", 420.0, height=60.0)
    c.show([s_b, s_e, s_e2], 0, None)
    ts = times_dense(0, D, FPS)
    x = lambda t: bx - bw * 0.6 + bw * 1.2 * smooth(t, 0.0, 0.85 * D)  # noqa: E731
    a = lambda t: math.sin(math.pi * min(t / (0.85 * D), 1.0)) ** 1.5  # noqa: E731
    c.bone_keys(b_b, "translate", ts, lambda t: (x(t), by))
    c.color_keys(s_b, ts, lambda t: _h(c, "FFF6D8", a(t)))
    c.bone_keys(b_e, "translate", ts, lambda t: (x(t) - 30, by + bh * 0.5))
    c.color_keys(s_e, ts, lambda t: _h(c, col, 0.9 * a(t)))
    c.bone_keys(b_e2, "translate", ts, lambda t: (x(t) + 30, by - bh * 0.5))
    c.color_keys(s_e2, ts, lambda t: _h(c, col, 0.8 * a(t)))
    return _finish(c, P, duration=D, loop=D)


def pinata_hit(c: Ctx, P: dict) -> dict:
    D = 2.0
    col = _hexn(P["color"], ORANGE)
    rng = np.random.default_rng(c.seed + 10)
    smokes = []
    for i in range(6):
        a = 2 * math.pi * i / 6 + float(rng.uniform(-0.4, 0.4))
        b = c.bone(f"smoke{i}")
        smokes.append((b, _s(c, b, "smoke_puff", float(rng.uniform(110, 160)), blend="normal"), a,
                       float(rng.uniform(90, 150)), float(rng.uniform(-60, 60))))
    b_gl, b_ra, b_ri, b_fl, b_co = (c.bone(n) for n in ("glow", "rays", "ring", "flash", "core"))
    s_gl = _s(c, b_gl, "glow_soft", 620.0)
    s_ra = _s(c, b_ra, "rays", 720.0)
    s_ri = _s(c, b_ri, "ring", 260.0)
    s_fl = _s(c, b_fl, "flash_burst", 380.0)
    s_co = _s(c, b_co, "glow_core", 300.0)
    sparks = []
    for i in range(18):
        a = float(rng.uniform(0, 2 * math.pi))
        b = c.bone(f"sp{i}", rot=math.degrees(a))
        sparks.append((b, _s(c, b, "spark", float(rng.uniform(60, 110))), a, float(rng.uniform(700, 1300)), float(rng.uniform(0, 0.05))))
    ts = times_dense(0, D, FPS)
    c.show([s for _, s, *_ in smokes], 0.05, 1.5)
    tt = times_dense(0.05, 1.5, FPS)
    for b, s, a, dist, rise in smokes:
        c.bone_keys(b, "translate", tt, lambda t, a=a, dist=dist, rise=rise: (math.cos(a) * dist * ease_out(t / 0.8, 3), math.sin(a) * dist * ease_out(t / 0.8, 3) + rise * t))
        c.bone_keys(b, "scale", tt, lambda t: (0.35 + 0.95 * ease_out(t / 0.9, 2.5),) * 2)
        c.bone_keys(b, "rotate", tt, lambda t, a=a: 30.0 * t * (1 if a > math.pi else -1))
        c.color_keys(s, tt, lambda t: _h(c, "F2E2D2", 0.85 * smooth(t, 0.05, 0.12) * (1 - smooth(t, 0.5, 1.5))))
    c.show([s_gl, s_ra, s_ri, s_fl, s_co], 0, 1.6)
    c.bone_keys(b_fl, "scale", ts, lambda t: (0.2 + 1.05 * ease_out(t / 0.22, 2.5),) * 2)
    c.bone_keys(b_fl, "rotate", ts, lambda t: 25.0 * t)
    c.color_keys(s_fl, ts, lambda t: _h(c, "FFF6DC", math.exp(-t / 0.16)))
    c.bone_keys(b_co, "scale", ts, lambda t: (0.5 + 0.8 * ease_out(t / 0.15),) * 2)
    c.color_keys(s_co, ts, lambda t: _h(c, WHITE, math.exp(-t / 0.22)))
    c.color_keys(s_gl, ts, lambda t: _h(c, col, 0.9 * smooth(t, 0, 0.04) * math.exp(-t / 0.55)))
    c.bone_keys(b_ra, "scale", ts, lambda t: (0.5 + 0.6 * ease_out(t / 0.4, 2.5),) * 2)
    c.bone_keys(b_ra, "rotate", ts, lambda t: -30.0 * t)
    c.color_keys(s_ra, ts, lambda t: _h(c, GOLD, 0.85 * smooth(t, 0, 0.05) * (1 - smooth(t, 0.3, 1.2))))
    c.bone_keys(b_ri, "scale", ts, lambda t: (0.2 + 2.2 * ease_out(t / 0.5, 2.4),) * 2)
    c.color_keys(s_ri, ts, lambda t: _h(c, "FFE2B0", 0.95 * smooth(t, 0, 0.03) * (1 - smooth(t, 0.05, 0.5))))
    k, g = 3.5, -900.0
    for b, s, a, sp, d in sparks:
        tt = times_dense(d, d + 0.75, FPS)

        def pos(t, a=a, sp=sp, d=d):
            q = max(0.0, t - d)
            e = (1 - math.exp(-k * q)) / k
            return (math.cos(a) * sp * e, math.sin(a) * sp * e + 0.5 * g * q * q)
        c.show([s], d, d + 0.75)
        c.bone_keys(b, "translate", tt, pos)
        c.bone_keys(b, "scale", tt, lambda t, d=d: (1.0 - 0.7 * smooth(t, d, d + 0.75), 1.0))
        c.color_keys(s, tt, lambda t, d=d: _h(c, "FFC060", 1 - smooth(t, d + 0.3, d + 0.75)))
    lands = []
    for j, (lx, ly) in enumerate(_cells(P, "land")):
        t0, tr = 0.3 + 0.12 * j, 0.6
        ctrl = (lx * 0.5 + float(rng.uniform(-60, 60)), max(0.0, ly * 0.3) + 160)
        at = lambda t, t0=t0, lx=lx, ly=ly, ctrl=ctrl: bez((0.0, 0.0), ctrl, (lx, ly), smooth(t, t0, t0 + tr) ** 1.2)  # noqa: E731
        trail = []
        for m in range(6):
            bt = c.bone(f"fb{j}_t{m}")
            trail.append((bt, _s(c, bt, "glow_soft", 150.0 - 16 * m), 0.025 * (m + 1)))
        bh = c.bone(f"fb{j}")
        s_h = _s(c, bh, "glow_core", 160.0)
        bst = c.bone(f"fb{j}_star", bh)
        s_st = _s(c, bst, "flare_star", 120.0)
        bl = c.bone(f"fb{j}_land", x=lx, y=ly)
        s_lg = _s(c, bl, "glow_soft", CELL * 1.6)
        bri = c.bone(f"fb{j}_ring", bl)
        s_lr = _s(c, bri, "ring", CELL * 1.1)
        tt = times_dense(t0, t0 + tr + 0.15, FPS * 2)
        end = lambda t, t0=t0: 1 - smooth(t, t0 + tr, t0 + tr + 0.12)  # noqa: E731
        c.show([s_h, s_st] + [s for _, s, _ in trail], t0, t0 + tr + 0.15)
        c.bone_keys(bh, "translate", tt, at)
        c.bone_keys(bst, "rotate", tt, lambda t: 300.0 * t)
        c.color_keys(s_h, tt, lambda t, end=end: _h(c, "FFD27A", end(t)))
        c.color_keys(s_st, tt, lambda t, end=end: _h(c, WHITE, end(t)))
        for bt, st, lag in trail:
            c.bone_keys(bt, "translate", tt, lambda t, lag=lag, at=at: at(t - lag))
            c.color_keys(st, tt, lambda t, lag=lag, t0=t0, end=end: _h(c, col, (0.85 - 3.5 * lag) * smooth(t, t0, t0 + lag + 0.02) * end(t)))
        a0 = t0 + tr
        tl = times_dense(a0 - 0.02, a0 + 0.6, FPS)
        c.show([s_lg, s_lr], a0 - 0.02, a0 + 0.6)
        c.color_keys(s_lg, tl, lambda t, a0=a0: _h(c, GOLD, 0.85 * bell(t, a0 - 0.02, 0.05, 0.5)))
        c.bone_keys(bri, "scale", tl, lambda t, a0=a0: (0.3 + 1.1 * ease_out((t - a0) / 0.4, 2.4) if t > a0 else 0.3,) * 2)
        c.color_keys(s_lr, tl, lambda t, a0=a0: _h(c, "FFE2B0", 0.9 * bell(t, a0 - 0.02, 0.04, 0.4)))
        c.ab.event(c.T(a0), "fireball_land")
        lands.append(c.T(a0))
    return _finish(c, P, duration=D * c.k, lands=lands)


def jar_burst(c: Ctx, P: dict) -> dict:
    D, XT = 2.6, 0.75
    col = _hexn(P["color"], GOLD)
    CX, CY = (float(v) for v in P["flare"])
    SX, SY = (float(v) for v in P["sign"])
    if P["x_path"] not in ("sign_to_cell", "flare_to_sign"):
        raise ValueError("jar_burst x_path must be sign_to_cell | flare_to_sign")
    rng = np.random.default_rng(c.seed + 11)
    jars = _cells(P)
    smk, parts = [], []
    for i, (x, y) in enumerate(jars):
        t0 = 0.035 * math.hypot(x - CX, y - CY) / 100
        b = c.bone(f"j{i}", x=x, y=y)
        bsm = c.bone(f"j{i}_sm", b)
        smk.append((bsm, _s(c, bsm, "smoke_puff", 130.0, blend="normal"), t0))
        parts.append((b, t0))
    adds = []
    for i, (b, t0) in enumerate(parts):                # all smoke (normal) first, then the additive run
        bg, bf = c.bone(f"j{i}_g", b), c.bone(f"j{i}_f", b)
        sg, sf = _s(c, bg, "glow_soft", 210.0), _s(c, bf, "flash_burst", 170.0)
        deb = []
        for k_ in range(4):
            a = float(rng.uniform(0, 2 * math.pi))
            bd = c.bone(f"j{i}_d{k_}", b, rot=math.degrees(a))
            deb.append((bd, _s(c, bd, "spark", float(rng.uniform(40, 70))), a, float(rng.uniform(90, 160))))
        adds.append((sg, bf, sf, deb, t0))
    bx = c.bone("x5", x=CX, y=CY)
    b_ra, b_ra2, b_gl, b_st, b_sk = (c.bone(n, bx) for n in ("rays", "rays2", "glow", "star", "streak"))
    s_gl = _s(c, b_gl, "glow_soft", 760.0)
    s_ra = _s(c, b_ra, "rays", 820.0)
    s_ra2 = _s(c, b_ra2, "rays", 640.0)
    rings = []
    for i, (rc, off) in enumerate((("FF4A4A", 0.0), ("4AFF7A", 0.03), ("4A7AFF", 0.06))):   # colour-split halo
        b = c.bone(f"ring{i}", bx)
        rings.append((b, _s(c, b, "ring", 300.0), rc, off))
    s_sk = _s(c, b_sk, "light_streak", 1100.0, height=120.0)
    s_st = _s(c, b_st, "flare_star", 460.0)
    b_lab = c.bone("label")
    s_lab = _s(c, b_lab, "x5_label", 170.0, blend="normal")
    b_pf = c.bone("signflash", x=SX, y=SY)
    s_pf = _s(c, b_pf, "flash_burst", 240.0)
    ts = times_dense(0, D, FPS)
    for bsm, s, t0 in smk:
        tt = times_dense(t0, t0 + 1.0, FPS)
        c.show([s], t0, t0 + 1.0)
        c.bone_keys(bsm, "scale", tt, lambda t, t0=t0: (0.4 + 0.9 * ease_out((t - t0) / 0.7, 2.5),) * 2)
        c.bone_keys(bsm, "translate", tt, lambda t, t0=t0: (0.0, 40 * (t - t0)))
        c.color_keys(s, tt, lambda t, t0=t0: _h(c, "F4E6D6", 0.8 * smooth(t, t0, t0 + 0.06) * (1 - smooth(t, t0 + 0.25, t0 + 1.0))))
    for sg, bf, sf, deb, t0 in adds:
        tt = times_dense(t0, t0 + 0.7, FPS)
        c.show([sg, sf] + [s for _, s, _, _ in deb], t0, t0 + 0.7)
        c.bone_keys(bf, "scale", tt, lambda t, t0=t0: (0.15 + 1.0 * ease_out((t - t0) / 0.18, 2.5),) * 2)
        c.bone_keys(bf, "rotate", tt, lambda t, t0=t0: 60.0 * (t - t0))
        c.color_keys(sf, tt, lambda t, t0=t0: _h(c, "FFF4D8", smooth(t, t0, t0 + 0.02) * math.exp(-max(0.0, t - t0) / 0.13)))
        c.color_keys(sg, tt, lambda t, t0=t0: _h(c, col, 0.8 * bell(t, t0, 0.04, 0.5)))
        for bd, sd, a, dist in deb:
            e = lambda t, t0=t0: ease_out((t - t0) / 0.5, 2.2)  # noqa: E731
            c.bone_keys(bd, "translate", tt, lambda t, t0=t0, a=a, dist=dist, e=e: (math.cos(a) * dist * e(t), math.sin(a) * dist * e(t) - 120 * (t - t0) ** 2))
            c.color_keys(sd, tt, lambda t, t0=t0: _h(c, "FFB050", 1 - smooth(t, t0 + 0.2, t0 + 0.6)))
    q = lambda t: max(0.0, t - XT)  # noqa: E731
    on = lambda t: smooth(t, XT - 0.03, XT + 0.02)  # noqa: E731
    out = lambda t: 1 - smooth(t, XT + 0.6, XT + 1.5)  # noqa: E731
    c.show([s_gl, s_ra, s_ra2, s_sk, s_st] + [s for _, s, _, _ in rings], XT - 0.03, D)
    c.bone_keys(b_ra, "scale", ts, lambda t: (0.3 + 0.9 * ease_out(q(t) / 0.35, 2.5),) * 2)
    c.bone_keys(b_ra, "rotate", ts, lambda t: 35.0 * q(t))
    c.color_keys(s_ra, ts, lambda t: _h(c, col, 0.9 * on(t) * out(t)))
    c.bone_keys(b_ra2, "scale", ts, lambda t: (0.3 + 0.8 * ease_out(q(t) / 0.3, 2.5),) * 2)
    c.bone_keys(b_ra2, "rotate", ts, lambda t: 15.0 - 50.0 * q(t))
    c.color_keys(s_ra2, ts, lambda t: _h(c, "FFE6A0", 0.7 * on(t) * out(t)))
    c.bone_keys(b_gl, "scale", ts, lambda t: (0.4 + 0.7 * ease_out(q(t) / 0.25),) * 2)
    c.color_keys(s_gl, ts, lambda t: _h(c, col, 0.95 * on(t) * (1 - 0.45 * smooth(q(t), 0.1, 0.5)) * out(t)))
    c.bone_keys(b_st, "scale", ts, lambda t: ((0.2 + 1.0 * ease_out(q(t) / 0.2, 3)) * (1 + 0.08 * math.sin(6 * math.pi * q(t))),) * 2)
    c.bone_keys(b_st, "rotate", ts, lambda t: 45.0 * ease_out(q(t) / 0.6, 2))
    c.color_keys(s_st, ts, lambda t: _h(c, WHITE, on(t) * out(t)))
    c.bone_keys(b_sk, "scale", ts, lambda t: (0.2 + 0.9 * ease_out(q(t) / 0.25), 1.0))
    c.color_keys(s_sk, ts, lambda t: _h(c, "FFF0C0", on(t) * (1 - smooth(q(t), 0.2, 0.9))))
    for b, s, rc, off in rings:
        c.bone_keys(b, "scale", ts, lambda t, off=off: (0.3 + (1.9 + 3 * off) * ease_out(max(0.0, q(t) - off) / 0.55, 2.4),) * 2)
        c.color_keys(s, ts, lambda t, rc=rc, off=off: _h(c, rc, 0.85 * smooth(t, XT + off - 0.02, XT + off + 0.02) * (1 - smooth(q(t), 0.1, 0.6))))
    if P["x_path"] == "flare_to_sign":          # the label punches in at the flare and arcs up into the sign
        F0, F1 = 1.95, 2.3
        fly = lambda t: smooth(t, F0, F1)  # noqa: E731
        c.show([s_lab], XT, F1 + 0.02)
        c.bone_keys(b_lab, "translate", ts, lambda t: (CX + (SX - CX) * fly(t), CY + (SY - CY) * fly(t) + 80 * math.sin(math.pi * fly(t))))
        c.bone_keys(b_lab, "scale", ts, lambda t: (backout(q(t) / 0.3, 3.2) * (1 + 0.05 * math.sin(4 * math.pi * q(t))) * (1 - 0.6 * fly(t)),) * 2)
        c.show([s_pf], F1 - 0.02, D)
        c.bone_keys(b_pf, "scale", ts, lambda t: (0.3 + 0.9 * ease_out((t - F1) / 0.22, 2.5) if t > F1 else 0.3,) * 2)
        c.color_keys(s_pf, ts, lambda t: _h(c, "FFF2C8", smooth(t, F1 - 0.02, F1 + 0.01) * math.exp(-max(0.0, t - F1) / 0.1)))
        c.ab.event(c.T(XT), "x5_flare")
        c.ab.event(c.T(F1), "x5_to_sign")
        return _finish(c, P, duration=D * c.k, jars=len(jars), flare_at=c.T(XT), x_path="flare_to_sign")
    # the reference clip: the X comes OUT of the sign as the jars burst, blooms over the board with the flare riding
    # behind it, then wanders down an S-curve, shrinking (about 2x -> 0.5x, slight ease in), onto the winning cell
    LX, LY = (float(v) for v in P["land"])
    E0, F0, F1 = XT - 0.25, XT, XT + 0.7
    pts = [(SX, SY), (CX - 0.8 * CELL, CY + 0.9 * CELL), (CX + 1.0 * CELL, CY - 0.4 * CELL), (LX, LY)]

    def path(t):                                # cubic Bezier sign -> board -> win cell
        u = smooth(t, F0, F1) ** 1.15 if t >= F0 else 0.0
        if t < F0:
            k = smooth(t, E0, F0)               # emerging: out of the sign toward the first control point
            return (SX + (pts[1][0] - SX) * 0.25 * k, SY + (pts[1][1] - SY) * 0.25 * k)
        a_, b_, c_, d_ = pts
        m = 1 - u
        x = m ** 3 * a_[0] + 3 * m * m * u * b_[0] + 3 * m * u * u * c_[0] + u ** 3 * d_[0]
        y = m ** 3 * a_[1] + 3 * m * m * u * b_[1] + 3 * m * u * u * c_[1] + u ** 3 * d_[1]
        e0 = (SX + (pts[1][0] - SX) * 0.25, SY + (pts[1][1] - SY) * 0.25)     # continue from where emerging stopped
        w = 1 - smooth(t, F0, F0 + 0.15)
        return (x + (e0[0] - SX) * w * m, y + (e0[1] - SY) * w * m)
    def lab_scale(t):
        if t < F0:
            return 0.4 + 1.2 * backout(smooth(t, E0, F0), 2.2)
        return 1.6 - 1.1 * smooth(t, F0, F1)
    c.bone_keys(bx, "translate", ts, lambda t: (path(t)[0] - CX, path(t)[1] - CY))   # the flare rides behind the X
    c.show([s_lab], E0, F1 + 0.02)
    c.bone_keys(b_lab, "translate", ts, path)
    c.bone_keys(b_lab, "scale", ts, lambda t: (lab_scale(t),) * 2)
    c.bone_keys(b_pf, "translate", ts, lambda t: (LX - SX, LY - SY))       # the landing flash sits on the win cell
    c.show([s_pf], F1 - 0.02, D)
    c.bone_keys(b_pf, "scale", ts, lambda t: (0.25 + 0.6 * ease_out((t - F1) / 0.22, 2.5) if t > F1 else 0.25,) * 2)
    c.color_keys(s_pf, ts, lambda t: _h(c, "FFF2C8", smooth(t, F1 - 0.02, F1 + 0.01) * math.exp(-max(0.0, t - F1) / 0.1)))
    c.ab.event(c.T(XT), "x5_flare")
    c.ab.event(c.T(F1), "x5_to_cell")
    return _finish(c, P, duration=D * c.k, jars=len(jars), flare_at=c.T(XT), lands_at=c.T(F1), x_path="sign_to_cell")


def banner_backdrop(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    col = _hexn(P["color"], GOLD)
    TX, TY = (float(v) for v in P["title"])
    CX, CY = (float(v) for v in P["subject"])
    NX, NY = (float(v) for v in P["number"])
    br = D / max(1, round(D / 2.0))                     # breathing / shine period: ~2 s, a whole number per loop
    rng = np.random.default_rng(c.seed + 12)
    b_ra, b_ra2, b_cg = c.bone("rays", x=CX, y=CY), c.bone("rays2", x=CX, y=CY), c.bone("subjectglow", x=CX, y=CY)
    b_tg, b_nb = c.bone("titleglow", x=TX, y=TY), c.bone("numbar", x=NX, y=NY)
    s_cg = _s(c, b_cg, "glow_soft", 900.0)
    s_ra = _s(c, b_ra, "rays", 1150.0)
    s_ra2 = _s(c, b_ra2, "rays", 950.0)
    s_tg = _s(c, b_tg, "glow_soft", 760.0, height=330.0)
    s_nb = _s(c, b_nb, "light_streak", 820.0, height=150.0)
    b_sh = c.bone("titleshine", rot=-20.0)
    s_sh = _s(c, b_sh, "shine_band", 90.0, height=200.0)
    tw = []
    for i in range(int(P["twinkles"])):
        a = 2 * math.pi * i / max(1, int(P["twinkles"])) + float(rng.uniform(-0.2, 0.2))
        b = c.bone(f"tw{i}", x=TX + math.cos(a) * float(rng.uniform(260, 340)), y=TY + math.sin(a) * float(rng.uniform(70, 110)))
        tw.append((b, _s(c, b, "flare_star", float(rng.uniform(40, 70))), float(rng.uniform(0, 2 * math.pi)), int(rng.integers(2, 5))))
    pal = [_hexn(x, "FFFFFF") for x in P["palette"]]
    top, bot, half = float(P["rain"][0]), float(P["rain"][1]), float(P["rain"][2])
    rain = []
    for i in range(int(P["coins"]) + int(P["count"])):
        period = D / max(1, round(D / float(rng.uniform(2.0, 2.8))))   # each piece recycles a whole number of times per loop
        ph, x0 = float(rng.uniform(0, period)), float(rng.uniform(-half, half))
        if i < int(P["coins"]):
            b = c.bone(f"rc{i}")
            rain.append((b, _s(c, b, "coin", float(rng.uniform(50, 76)), blend="normal"), "FFFFFF", period, ph, x0,
                         float(rng.uniform(10, 18)), 0.0, float(rng.uniform(15, 35))))
        else:
            b, s, rc, spin, flip, _, sway = _confetti(c, rng, i, (26, 40), pal)
            rain.append((b, s, rc, period, ph, x0, flip, spin, sway))
    c.show([s_cg, s_ra, s_ra2, s_tg, s_nb, s_sh] + [s for _, s, _, _ in tw] + [r_[1] for r_ in rain], 0, None)
    ts = times_dense(0, D, 15)
    c.bone_keys(b_ra, "rotate", [0.0, D], lambda t: -360.0 * t / D)
    c.bone_keys(b_ra2, "rotate", [0.0, D], lambda t: 360.0 * t / D)
    w2 = lambda t: math.sin(2 * math.pi * t / br)  # noqa: E731
    c.color_keys(s_ra, ts, lambda t: _h(c, col, 0.4 + 0.12 * w2(t)))
    c.color_keys(s_ra2, ts, lambda t: _h(c, "FFF2C0", 0.22 - 0.07 * w2(t)))
    c.color_keys(s_cg, ts, lambda t: _h(c, col, 0.32 + 0.08 * w2(t)))
    c.bone_keys(b_cg, "scale", ts, lambda t: (1 + 0.05 * w2(t),) * 2)
    c.color_keys(s_tg, ts, lambda t: _h(c, _hexn(P["title_color"], "FF9AE8"), 0.35 + 0.15 * w2(t + br / 4)))
    c.color_keys(s_nb, ts, lambda t: _h(c, col, 0.65 + 0.25 * w2(t + br / 2)))
    c.bone_keys(b_nb, "scale", ts, lambda t: (1 + 0.04 * w2(t + br / 2), 1.0))
    t30 = times_dense(0, D, FPS)
    sx = lambda t: -420 + 840 * smooth(t % br, 0.1 * br, 0.5 * br)  # noqa: E731
    c.bone_keys(b_sh, "translate", t30, lambda t: (TX + sx(t), TY))
    c.color_keys(s_sh, t30, lambda t: _h(c, WHITE, 0.8 * math.sin(math.pi * min(max(((t % br) - 0.1 * br) / (0.4 * br), 0), 1)) ** 1.5))
    for b, s, ph, n in tw:
        k = lambda t, ph=ph, n=n: max(0.0, math.sin(2 * math.pi * n * t / D + ph)) ** 8  # noqa: E731
        c.color_keys(s, t30, lambda t, k=k: _h(c, WHITE, k(t)))
        c.bone_keys(b, "scale", t30, lambda t, k=k: (0.3 + 0.9 * k(t),) * 2)
        c.bone_keys(b, "rotate", t30, lambda t: 90.0 * t / D)
    for b, s, rc, period, ph, x0, flip, spin, sway in rain:
        n = round(D / period)
        # keys on EXACT times either side of each respawn (a rounded wrap time can land before the true wrap, and the
        # piece then slides back up the screen, visibly, between that key and the next)
        wraps = sorted((period - ph) % period + m * period for m in range(n))
        near = [w + e for w in wraps for e in (-0.002, 0.0002) if 0.0 < w + e < D]
        tt = sorted(set([v for v in t30 if all(abs(v - w) > 0.0021 for w in wraps)] + near))
        life = lambda t, ph=ph, period=period: ((t + ph) % period) / period  # noqa: E731
        c.bone_keys(b, "translate", tt, lambda t, life=life, x0=x0, sway=sway: (x0 + sway * math.sin(4 * math.pi * life(t) + x0), top + (bot - top) * life(t)))
        if spin:
            c.bone_keys(b, "rotate", tt, lambda t, life=life, spin=spin, period=period: spin * life(t) * period)
        turns = lambda flip=flip, period=period: max(1, round(flip * period / (2 * math.pi)))  # noqa: E731
        c.bone_keys(b, "scale", tt, lambda t, life=life, turns=turns: (math.cos(2 * math.pi * turns() * life(t)), 1.0))
        # alpha 0 on both sides of every respawn, so the jump from the bottom back to the top is invisible
        c.color_keys(s, tt, lambda t, life=life, rc=rc: _h(c, rc, smooth(life(t), 0.0, 0.04) * (1 - smooth(life(t), 0.94, 0.998))))
    return _finish(c, P, duration=D, loop=D, pieces=len(rain))


def bubble_pop(c: Ctx, P: dict) -> dict:
    """Cascade removal as the reference clip plays it: each removed symbol is wrapped in a cyan glass bubble (1 frame),
    holds ~3 frames, then the bubble swells and bursts into confetti that flies out and falls (~9 frames), with a
    ring and a sparkle. Cells pop in a stagger. Bubbles (additive) are one run, confetti (normal) another."""
    D, CL = 0.75, float(P["cell"])
    col = _hexn(P["color"], CYAN)
    pal = [_hexn(x, "FFFFFF") for x in P["palette"]]
    cells = _cells(P)
    hold, stag = float(P["hold"]), float(P["stagger"])
    rng = np.random.default_rng(c.seed + 41)
    adds, conf, groups = [], [], []
    for i, (x, y) in enumerate(cells):                  # pass 1: every bubble (one additive run)
        t0 = stag * i
        g = c.bone(f"cell{i}", x=x, y=y)
        groups.append((t0, g))
        bb, br = c.bone(f"c{i}_bub", g), c.bone(f"c{i}_ring", g)
        adds.append((t0, bb, _s(c, bb, "bubble_rim", CL * 0.95), br, _s(c, br, "ring", CL * 0.9),
                     _s(c, c.bone(f"c{i}_tint", g), "glow_soft", CL * 1.1)))
    for i, (t0, g) in enumerate(groups):               # pass 2: every confetti piece (one normal run)
        conf.append((t0, g, [_confetti(c, rng, i * 100 + k, (14, 22), pal) for k in range(int(P["pieces"]))]))
    ts = times_dense(0, D, FPS)
    for t0, bb, sb, br, sr, st in adds:
        tb = t0 + hold                                      # the burst
        c.show([sb, st], t0, tb + 0.08)
        c.show([sr], tb - 0.02, tb + 0.35)
        c.bone_keys(bb, "scale", ts, lambda t, t0=t0, tb=tb: (0.9 + 0.08 * smooth(t, t0, tb) + 0.25 * smooth(t, tb, tb + 0.06),) * 2)
        c.color_keys(sb, ts, lambda t, t0=t0, tb=tb: _h(c, "BFF4FF", smooth(t, t0 - 0.01, t0 + 0.01) * (1 - smooth(t, tb, tb + 0.07))))
        c.color_keys(st, ts, lambda t, t0=t0, tb=tb: _h(c, col, 0.35 * smooth(t, t0 - 0.01, t0 + 0.01) * (1 - smooth(t, tb, tb + 0.07))))
        c.bone_keys(br, "scale", ts, lambda t, tb=tb: (0.6 + 0.8 * ease_out((t - tb) / 0.3, 2.4) if t > tb else 0.6,) * 2)
        c.color_keys(sr, ts, lambda t, tb=tb: _h(c, "DFFAFF", 0.8 * bell(t, tb - 0.02, 0.03, 0.3)))
    g_, k_ = -900.0, 4.0
    for t0, g, pieces in conf:
        tb = t0 + hold
        for b, s, pc, spin, flip, ph, _ in pieces:
            a = float(rng.uniform(0, 2 * math.pi))
            sp = float(rng.uniform(220, 420))
            vx, vy = sp * math.cos(a), sp * math.sin(a) + 120.0
            tt = times_dense(tb, min(D, tb + 0.45), FPS)
            c.show([s], tb, min(D, tb + 0.45))

            def pos(t, vx=vx, vy=vy, tb=tb):
                q = max(0.0, t - tb)
                e = (1 - math.exp(-k_ * q)) / k_
                return (vx * e, (vy + g_ / k_) * e - g_ * q / k_)
            c.bone_keys(b, "translate", tt, pos)
            c.bone_keys(b, "rotate", tt, lambda t, spin=spin, tb=tb: spin * (t - tb))
            c.bone_keys(b, "scale", tt, lambda t, flip=flip, ph=ph, tb=tb: (math.cos(flip * (t - tb) + ph), 1.0))
            c.color_keys(s, tt, lambda t, pc=pc, tb=tb: _h(c, pc, 1 - smooth(t, tb + 0.2, tb + 0.45)))
        # the confetti hangs from the cell bone (the pieces were made as root-level fx bones: move them under it)
        for b, *_ in pieces:
            bone = next(x for x in c.sk.bones if x.name == b)
            bone.parent = g
    c.ab.event(c.T(hold), "bubble_burst")
    return _finish(c, P, duration=D * c.k, cells=len(cells), burst_at=c.T(hold))


def tier_swap(c: Ctx, P: dict) -> dict:
    """Win-banner tier change (BIG -> MEGA -> SUPER) as the reference clip plays it, ~9 frames: the current card
    shrinks into a white ribbon ring, the next tier's card pops through it with overshoot, a white flash and a star
    sparkle at the swap. old= / new= are the bones of the two cards' art (scaled through carriers, your keys stay);
    the event tier_swap marks the frame to switch the title / backdrop art."""
    D, R_ = 0.6, float(P["radius"])
    col = _hexn(P["color"], WHITE)
    SW, P1 = 0.1, 0.3                                      # swap moment, new card settled
    b_r1, b_r2 = c.bone("ribbon1"), c.bone("ribbon2")
    s_r1 = _s(c, b_r1, "swirl", R_ * 2.3)
    s_r2 = _s(c, b_r2, "swirl", R_ * 1.9)
    b_ri, b_fl, b_st = c.bone("ring"), c.bone("flash"), c.bone("star")
    s_ri = _s(c, b_ri, "ring", R_ * 2.0)
    s_fl = _s(c, b_fl, "glow_soft", R_ * 2.4)
    s_st = _s(c, b_st, "flare_star", R_ * 1.4)
    c.show([s_r1, s_r2, s_ri, s_fl, s_st], 0, D)
    ts = times_dense(0, D, FPS)
    c.bone_keys(b_r1, "rotate", ts, lambda t: -540.0 * t)
    c.bone_keys(b_r2, "rotate", ts, lambda t: 420.0 * t)
    for b_, sl, k in ((b_r1, s_r1, 1.0), (b_r2, s_r2, 0.8)):
        c.bone_keys(b_, "scale", ts, lambda t, k=k: ((0.55 + 0.15 * smooth(t, 0, SW) + 0.6 * ease_out((t - SW) / 0.35, 2.2) if t > SW else 0.55 + 0.15 * smooth(t, 0, SW)) * k,) * 2)
        c.color_keys(sl, ts, lambda t, k=k: _h(c, col, 0.9 * k * smooth(t, 0, 0.05) * (1 - smooth(t, SW + 0.1, SW + 0.4))))
    c.bone_keys(b_ri, "scale", ts, lambda t: (0.5 + 0.9 * ease_out(max(0.0, t - SW) / 0.4, 2.4),) * 2)
    c.color_keys(s_ri, ts, lambda t: _h(c, col, 0.85 * bell(t, SW - 0.03, 0.03, 0.35)))
    c.color_keys(s_fl, ts, lambda t: _h(c, col, 0.8 * math.exp(-((t - SW) / 0.06) ** 2)))
    c.bone_keys(b_st, "scale", ts, lambda t: (0.2 + 1.0 * ease_out(max(0.0, t - SW) / 0.12),) * 2)
    c.bone_keys(b_st, "rotate", ts, lambda t: 60.0 * t)
    c.color_keys(s_st, ts, lambda t: _h(c, WHITE, bell(t, SW - 0.02, 0.03, 0.25)))
    if P.get("old") or P.get("new"):
        from .fx_reels import _carrier, _merge_keys
        if P.get("old"):
            co = _carrier(c, str(P["old"]), "tier_old")
            _merge_keys(c, co, "scale", ts, lambda t: ((1 - 0.45 * smooth(t, 0, SW) ** 1.6) if t <= SW + 0.02 else 0.0,) * 2, "mul")
        if P.get("new"):
            cn = _carrier(c, str(P["new"]), "tier_new")
            _merge_keys(c, cn, "scale", ts, lambda t: (0.0 if t < SW - 0.03 else 0.55 + 0.45 * backout((t - SW + 0.03) / (P1 - SW + 0.03), 2.6),) * 2, "mul")
    c.ab.event(c.T(SW), "tier_swap")
    return _finish(c, P, duration=D * c.k, swap_at=c.T(SW))


# ------------------------------------------------------------------ registry
_GT = dict(gain=({}, "{picture: alpha multiplier} for this recipe's pictures, e.g. {glow_soft: 0.5} when your glow is fuller"),
           thick=({}, "{picture: [width x, height x]} for thin stretched pictures, e.g. {light_streak: [1, 2.4]}"))
_CELL = dict(cell=(CELL, "one reel cell, design units"))
_GRID = [[x, y] for y in ROWS for x in COLS]


def _o(**kw) -> dict:
    return {**kw, **_GT}


RECIPES.update({
    "wild_glow": dict(
        fn=wild_glow, duration=1.6, kind="loop", color=PINK,
        summary="WILD idle loop: soft glow breathing behind the symbol, a tilted orbit ring, stars riding the orbit (bright on "
                "the near half, dim on the far half). wild_transform hands off to it seamlessly.",
        anchor="Cell centre.", options=_o(**_CELL, tilt=(-18.0, "orbit tilt, degrees"), squash=(0.38, "orbit ellipse height (1 = circle)"),
                                         stars=(2, "stars on the orbit"))),
    "wild_transform": dict(
        fn=wild_transform, duration=1.2, kind="one-shot", color=CYAN,
        summary="A symbol turns WILD, as the reference clip plays it: the cell flashes white with a pink rim (peak in 1-2 "
                "frames), sparkles fly, the WILD art pops in with overshoot (wild= its bone), and it leaves the wild_glow at its "
                "first frame: play wild_glow after. Event wild_pop. style=bubble keeps the earlier swirling-bubble intro (1.2 s).",
        anchor="Cell centre.", options=_o(**_CELL, color2=(PINK, "the glow it hands off to (wild_glow's colour)"),
                                         style=("flash", "flash (the clip) | bubble (swirling bubble intro, then the pop)"),
                                         wild=("", "bone of the WILD symbol art: popped with overshoot through a carrier"))),
    "mult_cell_glow": dict(
        fn=mult_cell_glow, duration=1.2, kind="loop", color=CYAN,
        summary="A multiplier cell's idle loop: glowing rounded-square frame and soft fill pulsing, a few twinkles.",
        anchor="Cell centre.", options=_o(**_CELL, twinkles=(4, "twinkles inside the cell"))),
    "cell_pop": dict(
        fn=cell_pop, duration=0.6, kind="one-shot", color=GOLD,
        summary="A cell frame lands: frame flashes white and settles from 125 %, a ring, a glow and six stars flung out.",
        anchor="Cell centre.", options=_o(**_CELL)),
    "confetti_burst": dict(
        fn=confetti_burst, duration=2.4, kind="one-shot", count=50, normal_blend=True,
        summary="A fan of confetti fired upward: linear drag (terminal fall ~470/s), gravity, sideways flutter after the apex, a "
                "3D flip (scaleX = cos) and spin; six shapes tinted from the palette, normal blend.",
        anchor="Launch point.", options=_o(palette=(PALETTE, "colours drawn at random"), spread=([40.0, 140.0], "launch angles, degrees (90 = up)"),
                                           power=(1.0, "launch speed multiplier"))),
    "mult_streak": dict(
        fn=mult_streak, duration=1.8, kind="one-shot", color=CYAN, normal_blend=True,
        summary="Multiplier collect, as the reference clip plays it: a row of cells flashes in sequence, a light streak shoots "
                "across with a hot head, the number is revealed small, punches in (ease out), holds, then DROPS into the win bar "
                "(4-5 frames, accelerating, shrinking) and the bar flashes (event mult_to_bar). to=sign arcs it up into the "
                "multiplier sign instead (event mult_to_sign).",
        anchor="Board centre (the clip's layout); positions are relative to it.",
        options=_o(**_CELL, cells=([[x, ROWS[1]] for x in COLS], "[[x, y], ...] the cells that flash (one row)"),
                   number=([COLS[2], None], "[x, y] where the number pops (y None = the row)"), sign=(SIGN, "[x, y] the multiplier sign"),
                   to=("bar", "bar (drop into the win bar, the clip) | sign (arc up into the multiplier sign)"),
                   bar=(BAR, "[x, y, w, h] the win bar"))),
    "wild_merge": dict(
        fn=wild_merge, duration=1.6, kind="one-shot", color=CYAN, normal_blend=True,
        summary="Several WILDs feed one multiplier: each source cell glows, a comet (oriented along its curved path) flies to the "
                "target, then a flash, ring and the number pop (event merge_hit).",
        anchor="Board centre; positions relative to it.",
        options=_o(**_CELL, sources=([[COLS[0], ROWS[1]], [COLS[1], ROWS[1]], [COLS[0], ROWS[2]], [COLS[2], ROWS[2]], [COLS[2], ROWS[3]]],
                                     "[[x, y], ...] the WILD cells"), target=([-70.0, -30.0], "[x, y] where they merge"))),
    "coins_to_bar": dict(
        fn=coins_to_bar, duration=1.9, kind="one-shot", count=10, color=GOLD, normal_blend=True,
        summary="Win collect: coins pop out of cells, spin (scaleX = cos) and arc into the win bar; every landing flashes a star "
                "and pulses the bar's glow. Coins are one normal run, flashes one additive run (2 draw calls, not 2 per coin).",
        anchor="Board centre; positions relative to it.",
        options=_o(cells=(_GRID, "[[x, y], ...] cells the coins can start from"), bar=(BAR, "[x, y, w, h] the win bar"))),
    "bar_sweep": dict(
        fn=bar_sweep, duration=1.0, kind="loop", color=GOLD,
        summary="A slanted shine band and two edge streaks sweep across a bar (loops; play once for a single sweep).",
        anchor="Board centre; `bar` is relative to it.", options=_o(bar=(BAR, "[x, y, w, h] the bar"), slant=(-18.0, "band slant, degrees"))),
    "pinata_hit": dict(
        fn=pinata_hit, duration=2.0, kind="one-shot", color=ORANGE, normal_blend=True,
        summary="Something bursts open: starburst flash, turning rays, shockwave ring, six smoke puffs (normal blend), 18 sparks "
                "with drag and gravity, then fireballs with glowing trails arc into cells and flash there (events fireball_land).",
        anchor="The piñata (burst centre); `land` targets are relative to it.",
        options=_o(land=([[COLS[1] - PINATA[0], ROWS[0] - PINATA[1]], [COLS[0] - PINATA[0], ROWS[2] - PINATA[1]],
                          [COLS[2] - PINATA[0], ROWS[1] - PINATA[1]]], "[[dx, dy], ...] where the fireballs land"))),
    "jar_burst": dict(
        fn=jar_burst, duration=2.6, kind="one-shot", color=GOLD, normal_blend=True,
        summary="Every jar on the board bursts, rippling out from the centre (flash, smoke, debris), then a big flare: two "
                "counter-turning ray layers, colour-split rings, streak, star. As in the reference clip the X label comes OUT of "
                "the multiplier sign, the flare riding behind it, and wanders down an S-curve, shrinking, onto the winning cell "
                "(events x5_flare, x5_to_cell). x_path=flare_to_sign: the label punches in at the flare and arcs up into the sign.",
        anchor="Board centre; positions relative to it.",
        options=_o(cells=([[x, y] for (i, y) in enumerate(ROWS) for (j, x) in enumerate(COLS) if not (i == 3 and j in (1, 2, 3))],
                          "[[x, y], ...] the jar cells"), flare=([0.0, -30.0], "[x, y] the flare centre"), sign=(SIGN, "[x, y] the multiplier sign"),
                   x_path=("sign_to_cell", "sign_to_cell (the clip) | flare_to_sign"),
                   land=([COLS[3], ROWS[3]], "[x, y] the winning cell the X lands on"))),
    "banner_backdrop": dict(
        fn=banner_backdrop, duration=8.0, kind="loop", color=GOLD, count=22, normal_blend=True,
        summary="Behind and around a BIG / MEGA / SUPER WIN banner (exact loop): counter-turning rays behind the subject, "
                "breathing glows, twinkles round the title, a shine across the title every ~2 s, a glowing number bar, coins and "
                "confetti raining (each piece respawns a whole number of times per loop, hidden at alpha 0 across the jump).",
        anchor="Screen centre; positions relative to it.",
        options=_o(title=([0.0, 400.0], "[x, y] title centre"), subject=([0.0, 120.0], "[x, y] character centre (rays, glow)"),
                   number=([0.0, -180.0], "[x, y] number bar"), title_color=("FF9AE8", "title glow tint"), twinkles=(9, "twinkles round the title"),
                   coins=(12, "falling coins (count = confetti pieces)"), palette=(PALETTE, "confetti colours"),
                   rain=([640.0, -640.0, 340.0], "[top y, bottom y, half width] of the rain"))),
    "bubble_pop": dict(
        fn=bubble_pop, duration=0.75, kind="one-shot", color=CYAN, normal_blend=True,
        summary="Cascade removal, as the reference clip plays it: every removed symbol is wrapped in a cyan glass bubble (1 frame), "
                "holds ~3 frames, then the bubble swells and bursts into confetti that flies out and falls (~9 frames) with a ring. "
                "Cells pop in a stagger. Event bubble_burst. Hide the symbol art at the event.",
        anchor="Board centre; cells relative to it.",
        options=_o(**_CELL, cells=([[COLS[0], ROWS[1]], [COLS[2], ROWS[1]], [COLS[4], ROWS[2]]], "[[x, y], ...] the cells to pop"),
                   hold=(0.1, "seconds the bubble holds before it bursts"), stagger=(0.0, "seconds between cells"),
                   pieces=(10, "confetti pieces per cell"), palette=(PALETTE, "confetti colours"))),
    "tier_swap": dict(
        fn=tier_swap, duration=0.6, kind="one-shot", color=WHITE,
        summary="Win-banner tier change (BIG -> MEGA -> SUPER), ~9 frames as in the reference clip: the current card shrinks into a "
                "white ribbon ring (two counter-turning swirls), the next card pops through it with overshoot, flash and star at the "
                "swap. old= / new= the two cards' bones (carriers, your keys untouched); event tier_swap = switch title / backdrop.",
        anchor="Card centre.",
        options=_o(radius=(150.0, "ring radius (about half the card)"), old=("", "bone of the current tier's card art"),
                   new=("", "bone of the next tier's card art"))),
})
for _n in ("wild_glow", "wild_transform", "mult_cell_glow", "cell_pop", "confetti_burst", "mult_streak", "wild_merge",
           "coins_to_bar", "bar_sweep", "pinata_hit", "jar_burst", "banner_backdrop", "bubble_pop", "tier_swap"):
    ROLES[_n] = dict(PIC_ROLES)
    RECIPES[_n]["roles"] = ROLES[_n]
PINATA_RECIPES = ("wild_glow", "wild_transform", "mult_cell_glow", "cell_pop", "confetti_burst", "mult_streak", "wild_merge",
                  "coins_to_bar", "bar_sweep", "pinata_hit", "jar_burst", "banner_backdrop", "bubble_pop", "tier_swap")


def pack_tuning() -> dict[str, Any]:
    """gain / thick measured on the first real texture pack (fuller glow, hairline streak and band)."""
    return {"gain": {"glow_soft": 0.5, "rays": 0.6, "flash_burst": 0.7, "smoke_puff": 0.6, "glow_core": 0.85},
            "thick": {"light_streak": [1.0, 2.4], "shine_band": [2.6, 1.0]}}
