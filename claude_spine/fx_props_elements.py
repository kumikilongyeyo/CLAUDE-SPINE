"""Element props for ``fx_recipe``: fire, liquid, steam, electricity, ice and smoke living ON a prop the artist drew
(a candle, a potion flask, a honey jar, a kettle, a battery, a cauldron).

    flame_wick     a small layered flame that flickers (seamless loop) and LEANS against the prop's motion
    liquid_bubble  bubbles rise inside a vessel, zig-zag, grow as they rise and pop at the surface (ring + droplets)
    prop_drip      a drop swells, necks, snaps off (prop_drip_snap), falls with gravity and splats (prop_drip_splat)
    prop_steam     steam puffs from a spout in rhythm, building to a kettle climax + whistle jet (prop_steam_climax)
    prop_electric  the prop is charged: jagged arcs crackle between pairs of given points (seamless loop)
    prop_freeze    frost creeps over the prop, crystals twinkle, its idle slows and locks with a shiver (prop_frozen)
    prop_dissolve  a glowing edge sweeps across, embers lift off, the prop is wiped away (prop_dissolve_hide)
    smoke_wisp     a slow curling ribbon of smoke rising from a source (seamless loop)

Same rules as the rest of the kit: the shared piñata pictures (``PICS``, every one an ``art=`` role) plus three
procedural ones of this module (a teardrop, a liquid blob, a flame tongue), one group bone at the anchor, closed-form
keys, the artist's bones driven only through inserted carriers (``fx_reels._carrier``). Loops close exactly: periodic
motion has a whole number of cycles per loop, and every respawn is keyed at EXACT times either side of the wrap while
the piece is at alpha 0 (a rounded wrap time makes a piece visibly slide back; see fx_pinata.banner_backdrop).

Registered into fx_recipes.RECIPES / ROLES at import (fx_recipes imports this module at its end).
"""
from __future__ import annotations

import math
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .fx import _rgba
from .fx_pinata import PIC_ROLES, PICS, _finish
from .fx_recipes import RECIPES, ROLES, Ctx, _hexn, ease_out, hexa, smooth, times_dense
from .ir import ClippingAttachment, Slot

FPS = 30
PRE, POST = 0.002, 0.0002            # respawn keys this far either side of the exact wrap time

# ---- flame_wick: a candle flame is ~2.3x taller than wide, flickers at a few Hz with fast licks on top (~10 Hz)
FLAME_H, FLAME_W = 92.0, 40.0
FLICKER_HZ = (1.3, 3.1, 7.4, 12.5)            # slow breathing .. fast licks (rounded to whole cycles per loop)
FLICKER_AMP = (0.06, 0.05, 0.035, 0.02)        # fraction of the flame height per band
LICK_DEG = (2.4, 1.5)                          # tip jitter, degrees, at ~5 and ~9 Hz
LEAN_PER_SPEED = 0.07                          # degrees of lean per unit/s of sideways speed (air drag on the hot gas)
LEAN_MAX = 40.0
LEAN_HZ, LEAN_ZETA = 2.2, 0.32                 # the flame is a spring: it lags the prop and overshoots when it stops
SWAY_DEG = 4.0                                 # no motion to follow: a gentle draught

# ---- liquid_bubble: buoyancy vs drag gives an almost constant rise; bigger bubbles rise faster (v ~ sqrt(r))
BUB_RISE = 115.0                               # terminal speed of an 8-unit bubble (units/s)
BUB_TAU = 0.08                                 # seconds to reach it (buoyancy wins almost at once)
BUB_GROW = 0.35                                # radius grows 35 % over the rise (pressure drops; exaggerated)
BUB_ZIG_HZ, BUB_ZIG = 2.2, 0.55                # path instability: zig-zag at ~2 Hz, amplitude in radii
BUB_HOLD = 0.08                                # a bubble sits under the surface skin before it bursts
POP_T = 0.32                                   # the pop ring and droplets live this long
POP_G = 1500.0                                 # gravity on the pop droplets (units/s^2)

# ---- prop_drip: viscous liquid swells slowly, the neck pinches off fast (Rayleigh-Plateau), gravity does the rest
DRIP_G = 1800.0                                # gravity (units/s^2, ~2x real at a 720-unit screen: reads snappier)
DRIP_FORM = 1.05                               # seconds to swell and neck before it lets go
DRIP_NECK = 0.38                               # the last part of the form: the neck thins, the drop stretches
DRIP_STRETCH = 0.8                             # extra length at the pinch (1.8x)
DRIP_V0 = 60.0                                 # downward speed the pinch gives the drop
FALL_STRETCH = 1 / 1500                        # motion stretch per unit/s of fall speed (capped at +90 %)
STUB = 0.36                                    # what stays hanging, as a fraction of the full drop
STUB_HZ, STUB_ZETA, STUB_KICK = 3.4, 0.24, 1.2  # the stub springs back up: surface tension vs viscosity
SPLAT_T = 0.16                                 # the splat spreads out in this long, then creeps

# ---- prop_steam: a jet that drag slows to the buoyant rise, puffs that expand ~sqrt(t) as they entrain air
STEAM_V0 = 250.0                               # exit speed from the spout (units/s)
STEAM_TAU = 0.32                               # drag time: the jet slows to the buoyant rise in ~1/3 s
STEAM_BUOY = 75.0                              # buoyant rise of the warm vapour (units/s)
STEAM_LIFE = 1.5                               # seconds a puff lives before it evaporates
STEAM_GROW = 1.7                               # width grows 0.3 -> 0.3 + GROW (turbulent entrainment, ~sqrt(t))
STEAM_RATE = (3.0, 11.0)                       # puffs/s at the start (it starts to boil) .. at the climax
CONDENSE = 0.1                                 # the first ~0.1 s is clear vapour: a puff shows a little off the spout
JET_HZ = (17.0, 29.0)                          # the whistle jet vibrates

# ---- prop_electric: a crackle is a few frames long and re-strikes along the same ionised path
ARC_LIFE = (0.12, 0.26)                        # seconds per crackle (4-8 frames)
ARC_FLASHES = (2, 4)                           # 2-3 strokes per crackle, a new jag each
ARC_DECAY = 0.035                              # a stroke's light dies in ~1 frame
ARC_OVER = 1.22                                # a streak is drawn this much longer than its segment (bright joints)
GLOW_H, CORE_H, SEG_W = 26.0, 7.0, 100.0       # streak thickness: coloured glow / white core; base width
POINTS = [[-100.0, 60.0], [95.0, 80.0], [-82.0, -92.0], [108.0, -60.0], [4.0, 136.0], [12.0, -130.0]]

# ---- prop_freeze: the freezing front advances ~t^0.6 (diffusion-limited, slows as it goes)
FRONT_POW = 0.6
SLOW_FROM = 0.3                                # the idle starts slowing at this fraction of the lock time
SHIVER_HZ, SHIVER_DEG, SHIVER_T = 22.0, 1.8, 0.32   # the lock: a tiny fast shiver that dies out
CONTRACT = 0.035                               # it shrinks 3.5 % at the lock (cold contraction, exaggerated)
BOX = [0.0, 0.0, 220.0, 260.0]                 # the prop's box [x, y, w, h] relative to the anchor

# ---- prop_dissolve: embers are lifted by buoyancy against drag and cool from yellow to red as they rise
BAND_H = 34.0                                  # the glowing edge's thickness
EMBER_LIFT, EMBER_DRAG = 1000.0, 2.2           # upward accel (units/s^2) and drag (1/s): they settle at ~LIFT/DRAG
EMBER_V0 = 160.0                               # the plume over the edge throws them up at once
EMBER_LIFE = (0.55, 1.1)

# ---- smoke_wisp: a buoyant plume slows as it mixes (z ~ t^0.75), goes unstable and curls, widens with height
WISP_H = 300.0
WISP_POW = 0.75
WISP_CURL = 38.0                               # sideways curl amplitude at the top (0 at the source)
WISP_LAMBDA = 150.0                            # curl wavelength along the column
WISP_GROW = 2.6                                # a puff grows 0.5 -> 0.5 + GROW by the top (near the source it is stretched up)
WISP_LIFE = 3.4                                # seconds a puff takes to rise and thin away


# ====================================================================== pictures of this module (white, tinted by the slot)
def _teardrop_mask(w: int, h: int, m: float = 1.6, pad: float = 0.1) -> np.ndarray:
    """A teardrop, point at the TOP, round bulb at the bottom (x = sin t * sin(t/2)^m, y = cos t), drawn at 4x."""
    S = 4
    W, H = w * S, h * S
    pts = [(math.sin(a) * math.sin(a / 2) ** m, math.cos(a)) for a in np.linspace(0, 2 * math.pi, 400)]
    xm = max(abs(p[0]) for p in pts)
    poly = [(W / 2 + p[0] / xm * W * (0.5 - pad), H * pad + (1 - p[1]) / 2 * H * (1 - 2 * pad)) for p in pts]
    im = Image.new("L", (W, H), 0)
    ImageDraw.Draw(im).polygon(poly, fill=255)
    return np.asarray(im.resize((w, h), Image.LANCZOS), np.float32) / 255


def _edge0(a: np.ndarray, px: int = 2) -> np.ndarray:
    """Force the outer `px` pixels to alpha 0 (no picture may touch its own edge)."""
    a = a.copy()
    a[:px], a[-px:], a[:, :px], a[:, -px:] = 0, 0, 0, 0
    return a


def tex_drip_drop(w: int = 96, h: int = 144) -> Image.Image:
    """A liquid teardrop, point up: nearly opaque body, darker toward its rim (it reads round), soft 1 px edge."""
    m = _teardrop_mask(w, h, 1.5)
    im = Image.fromarray((m * 255).astype(np.uint8), "L")
    a = np.asarray(im.filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255
    inner = np.asarray(im.filter(ImageFilter.GaussianBlur(w * 0.12)), np.float32) / 255
    y, x = np.mgrid[0:h, 0:w]
    lit = np.clip(1 - np.hypot((x - w * 0.38) / w, (y - h * 0.62) / h) * 2.2, 0, 1)      # light from the upper left
    rgb = np.clip(0.62 + 0.28 * inner + 0.12 * lit, 0, 1)
    return _rgba(np.dstack([rgb, rgb, rgb]), _edge0(a * 0.97))


def tex_drip_blob(n: int = 96) -> Image.Image:
    """A round blob of liquid (the splat and the droplets): opaque body, darker rim, soft edge."""
    y, x = np.mgrid[0:n, 0:n]
    r = np.hypot(x - (n - 1) / 2, y - (n - 1) / 2) / (n / 2)
    a = np.clip((0.86 - r) / 0.06, 0, 1) * 0.97
    rgb = np.clip(0.62 + 0.38 * (1 - r ** 2), 0, 1)
    return _rgba(np.dstack([rgb, rgb, rgb]), _edge0(a))


def tex_flame_tongue(w: int = 96, h: int = 192) -> Image.Image:
    """A soft flame tongue: teardrop (point up), blurred, brightest in the lower middle where a flame burns hottest."""
    m = _teardrop_mask(w, h, 2.1, pad=0.12)
    im = Image.fromarray((m * 255).astype(np.uint8), "L")
    a = np.asarray(im.filter(ImageFilter.GaussianBlur(w * 0.07)), np.float32) / 255
    y, x = np.mgrid[0:h, 0:w]
    hot = np.exp(-(((x - (w - 1) / 2) / (w * 0.22)) ** 2 + ((y - h * 0.66) / (h * 0.22)) ** 2))
    a = np.clip(a * (0.62 + 0.45 * hot), 0, 1)
    return _rgba(np.ones((h, w)), _edge0(a, 3))


OWN: dict[str, Callable[[], Image.Image]] = dict(drip_drop=tex_drip_drop, drip_blob=tex_drip_blob, flame_tongue=tex_flame_tongue)
OWN_ROLES = {"drip_drop": "liquid teardrop, point UP, bulb at the bottom (normal blend, tinted)",
             "drip_blob": "round liquid blob: the splat and the droplets (normal blend, tinted)",
             "flame_tongue": "soft flame tongue, point UP, brightest low in the middle (additive)"}


# ====================================================================== helpers
def _pic(c: Ctx, bone: str, pic: str, width: float, height: float | None = None, blend: str = "additive",
         ox: float = 0.0, oy: float = 0.0) -> str:
    """A slot showing kit picture `pic` (fx_pinata PICS or this module's own), an art= role by the same name."""
    tex = f"fx/pinata_{pic}" if pic in PICS else f"fx/props_{pic}"
    nm = c.slot(bone, tex, width, height=height, make=PICS.get(pic) or OWN[pic], blend=blend, role=pic,
                stretch=height is not None, ox=ox, oy=oy)
    c.__dict__.setdefault("_pic", {})[nm] = pic
    return nm


def _wt(t: float, D: float) -> float:
    """Loop time: the key at D IS the key at 0 (so the loop closes exactly, whatever float error says)."""
    return 0.0 if t >= D - 1e-9 else t


def _noise(D: float, hz, amps, rng) -> Callable[[float], float]:
    """Sum of sines, each a WHOLE number of cycles per loop of D (so it is seamless), random phases."""
    ms = [max(1, round(f * D)) for f in hz]
    ph = [float(rng.uniform(0, 2 * math.pi)) for _ in ms]
    return lambda t: sum(a * math.sin(2 * math.pi * m * t / D + p) for a, m, p in zip(amps, ms, ph))


def _life(t: float, D: float, m: int, ph: float) -> tuple[int, float]:
    """A piece that respawns m times per loop, phase ph (0..1): (which life, 0..m-1; how far into it, 0..1)."""
    s = _wt(t, D) * m / D + ph
    f = math.floor(s)
    return int(f) % m, s - f


def _wraps(D: float, m: int, ph: float) -> list[float]:
    return [(j - ph) * D / m for j in range(1, m + 1) if 0 < (j - ph) * D / m < D]


def _with_wraps(ts, wraps) -> list[float]:
    """Key times plus a key EXACTLY either side of every respawn (the jump happens between them, at alpha 0)."""
    near = [w + e for w in wraps for e in (-PRE, POST)]
    return sorted({t for t in ts if all(abs(t - w) > PRE + 1e-4 for w in wraps)} | {t for t in near if 0 < t})


def _windows(D: float, wins, rate: float, extra=()) -> list[float]:
    """Sparse key times: 0, D, dense inside each [a, b] window (clipped to the loop), plus `extra`."""
    ts = {0.0, D, *[t for t in extra if 0 <= t <= D]}
    for a, b in wins:
        a, b = max(0.0, a), min(D, b)
        if b > a:
            ts.update(times_dense(a, b, rate))
    return sorted(ts)


def _carrier_chain(sk, bone: str) -> list[str]:
    """The carrier bones fx recipes inserted above `bone` (nearest first)."""
    out, b = [], sk.bone(bone).parent
    while b and b.startswith("fx_") and f"_{bone}" in b:
        out.append(b)
        b = sk.bone(b).parent
    return out


def _ancestors(sk, bone: str) -> list[str]:
    out = []
    while bone:
        out.append(bone)
        bone = sk.bone(bone).parent
    return out


def _sample(keys, tl: str, t: float) -> tuple[float, ...]:
    """Linear value of a bone timeline at t (held outside its keys)."""
    rest = {"rotate": (0.0,), "translate": (0.0, 0.0), "scale": (1.0, 1.0), "shear": (0.0, 0.0)}[tl]
    flds = ("value",) if tl == "rotate" else ("x", "y")
    ts = [k.time for k in keys]
    return tuple(float(np.interp(t, ts, [rest[i] if getattr(k, f, None) is None else float(getattr(k, f)) for k in keys]))
                 for i, f in enumerate(flds))


_GT = dict(gain=({}, "{picture: alpha multiplier} to retune a texture pack (kit pictures)"),
           thick=({}, "{picture: [width x, height x]} for thin stretched pictures (kit pictures)"))


def _o(**kw):
    return {**kw, **_GT}


# ====================================================================== flame_wick
def _follow_motion(c: Ctx, follow: str, D: float, gain: float):
    """World motion of the wick (the group bone) in this animation if `follow` or any of its ancestors is keyed there:
    the lean is a damped spring driven by the sideways speed (simulated three loops, the last one kept: periodic)."""
    sk = c.sk
    an = sk.animations.get(c.anim)
    chain = [b for b in _ancestors(sk, follow) if b not in c.bones]
    if an is None or not any(b in an.bones for b in chain):
        return None
    L = max((k.time for b in chain for keys in an.bones.get(b, {}).values() for k in keys), default=0.0)
    if L <= 0.05:
        return None
    from .rig_chain import pose_world
    n = max(16, int(round(L * 120)))
    dt = L / n
    xs, rot = [], []
    parent = sk.bone(c.group).parent
    for i in range(n):
        w = pose_world(sk, c.anim, i * dt)
        xs.append(w[c.group].x)
        pw = w[parent]
        rot.append(math.degrees(math.atan2(pw.c, pw.a)))
    xs, rot = np.array(xs), np.unwrap(np.radians(rot))
    vx = (np.roll(xs, -1) - np.roll(xs, 1)) / (2 * dt)                       # periodic central difference
    target = np.clip(LEAN_PER_SPEED * gain * vx, -LEAN_MAX, LEAN_MAX)       # moving +x: the tip trails to -x (+deg)
    w0 = 2 * math.pi * LEAN_HZ
    th = v = 0.0
    out = np.zeros(n)
    for lap in range(3):
        for i in range(n):
            a_ = w0 * w0 * (target[i] - th) - 2 * LEAN_ZETA * w0 * v
            v += a_ * dt
            th += v * dt
            if lap == 2:
                out[i] = th
    lean = np.append(out, out[0])
    rot = np.degrees(np.append(rot, rot[0]))
    grid = np.linspace(0, L, n + 1)
    return dict(length=L, lean=lambda t: float(np.interp(t, grid, lean)), rot=lambda t: float(np.interp(t, grid, rot)),
                peak=float(np.abs(out).max()))


def flame_wick(c: Ctx, P: dict) -> dict:
    """A candle / torch / lantern flame on a wick at the anchor: a soft tongue, a white-hot core, a blue base and a warm
    haze that flicker together (four noise bands, whole cycles per loop: seamless), a warm ambient glow breathing with it.
    The flame stays upright in the world and leans AGAINST the prop's motion (`follow`), with spring lag and overshoot."""
    D = float(P["duration"])
    size = float(P["size"])
    H, Wf = FLAME_H * size, FLAME_W * size
    col, core_c = _hexn(P["color"], "FF8A1E"), _hexn(P["color2"], "FFF3C4")
    sk = c.sk
    follow = str(P["follow"] or "")
    if follow:
        if not sk.has_bone(follow):
            raise ValueError(f"no bone {follow!r} to follow")
        gb = sk.bone(c.group)
        if gb.parent == "root" and follow != "root":
            gb.parent = follow                       # the wick rides the prop; x, y are then in that bone's space
    motion = _follow_motion(c, follow, D, float(P["lean"])) if follow else None
    if motion:
        D = round(motion["length"], 4)                # loop with the animation the flame follows
    rng = np.random.default_rng(c.seed + 501)
    b_amb = c.bone("ambient", y=H * 0.42)
    b_fl = c.bone("flame")
    s_amb = _pic(c, b_amb, "glow_soft", float(P["glow"])) if float(P["glow"]) > 0 else None
    s_haze = _pic(c, b_fl, "glow_soft", Wf * 2.6, height=H * 1.7, oy=H * 0.52)
    s_tng = _pic(c, b_fl, "flame_tongue", Wf, height=H, oy=H * 0.45)
    s_base = _pic(c, b_fl, "glow_core", Wf * 0.95, height=Wf * 0.75, oy=H * 0.1) if P["base"] else None
    s_core = _pic(c, b_fl, "glow_core", Wf * 0.85, height=H * 0.62, oy=H * 0.3)
    c.show([s for s in (s_amb, s_haze, s_tng, s_base, s_core) if s], 0, None)
    fl = float(P["flicker"])
    nz = _noise(D, FLICKER_HZ, [a * fl for a in FLICKER_AMP], rng)
    slow = _noise(D, FLICKER_HZ[:2], [a * fl for a in FLICKER_AMP[:2]], rng)
    lick = _noise(D, (5.3, 9.1), [a * fl for a in LICK_DEG], rng)
    if motion:
        lean, prot = motion["lean"], motion["rot"]
    else:
        sway = _noise(D, (0.45, 1.1), (float(P["sway"]) * 0.7, float(P["sway"]) * 0.3), rng)
        w = sk.world()
        r0 = math.degrees(math.atan2(w[sk.bone(c.group).parent].c, w[sk.bone(c.group).parent].a))
        lean, prot = sway, (lambda t: r0)
    ts = times_dense(0, D, FPS)
    W = lambda t: _wt(t, D)  # noqa: E731
    c.bone_keys(b_fl, "rotate", ts, lambda t: lean(W(t)) + lick(W(t)) - prot(W(t)))     # upright in the world, leaning
    c.bone_keys(b_fl, "scale", ts, lambda t: (1 - 0.45 * nz(W(t)), 1 + nz(W(t))))       # taller = thinner, about the wick
    br = lambda t: 1 + 1.6 * nz(W(t))  # noqa: E731   a taller flame burns brighter
    c.color_keys(s_haze, ts, lambda t: hexa(col, c.a(0.32 * br(t))))
    c.color_keys(s_tng, ts, lambda t: hexa(col, c.a(0.8 * br(t))))
    c.color_keys(s_core, ts, lambda t: hexa(core_c, c.a(0.92 * br(t))))
    if s_base:
        c.color_keys(s_base, ts, lambda t: hexa("4F7DFF", c.a(0.55 * (1 + 0.5 * nz(W(t))))))
    if s_amb:
        c.color_keys(s_amb, ts, lambda t: hexa(col, c.a(0.3 * (1 + 1.6 * slow(W(t))))))
        c.bone_keys(b_amb, "scale", ts, lambda t: (1 + 0.6 * slow(W(t)),) * 2)
    period = D / max(1, round(D / 1.0))
    hint = dict(template="fire", params=dict(width=128, height=256, duration=round(period, 3), fps=24, hot="FFF6D0", mid=col,
                                             cool="B8300A", scale=16, rise=240, lick=0.6, flicker=0.4, body=0.3, taper=2.0,
                                             flame_height=1.05, threshold=0.24, alpha_cut=0.32, core=0.75, loop=True,
                                             edge_fade=0.32, seed=c.seed),
                mode="alpha", seq_mode="loop", parent=b_fl, front_of=c.slots[-1], x=0.0, y=round(H * 0.5, 2),
                scale=round(H * 1.3 / 256, 4), start=c.T(0.0), until=c.T(D),
                note="a realistic flame: ae_template fire with these params -> ae_fx_to_spine with these args (parent = the "
                     "flame bone, so it leans and flickers with it); keep the ambient glow, drop the tongue/core alphas")
    return _finish(c, P, duration=D, loop=D, flame_bone=b_fl, following=bool(motion),
                   peak_lean=round(motion["peak"], 2) if motion else float(P["sway"]), ae_hint=hint)


# ====================================================================== liquid_bubble
def _vessel(P: dict):
    ax, ay, aw, ah = (float(v) for v in P["area"])
    R = float(P["radius"])
    if R > 0:
        surf = float(P["surface_y"]) if P["surface_y"] is not None else ay + 0.45 * R
        return ax, R * 0.55, surf, (lambda x: ay - math.sqrt(max(R * R - (x - ax) ** 2, 0.0)))
    surf = float(P["surface_y"]) if P["surface_y"] is not None else ay + ah / 2
    return ax, aw * 0.42, surf, (lambda x: ay - ah / 2)


def liquid_bubble(c: Ctx, P: dict) -> dict:
    """Bubbles rise inside a vessel (a box `area` or a circle `radius`), zig-zag, grow as they rise, sit under the
    surface for a beat and pop: a flat ring spreads on the surface and droplets jump and fall back. Seamless loop: each
    bubble lives a whole number of times per loop, hidden at alpha 0 across every respawn."""
    D = float(P["duration"])
    n = int(P["count"])
    col = _hexn(P["color"], "CFF4FF")
    cx, half, surf, bottom = _vessel(P)
    rng = np.random.default_rng(c.seed + 511)
    bub = []
    for i in range(n):
        r0 = float(rng.uniform(5.0, 12.0)) * float(P["size"])
        v = BUB_RISE * float(P["rise"]) * math.sqrt(r0 / 8.0)
        deep = surf - min(bottom(cx - half), bottom(cx), bottom(cx + half)) - r0
        life = deep / v + BUB_TAU + BUB_HOLD + POP_T
        m = max(1, int(D / (life * 1.15)))
        if life > 0.9 * D / m:                      # too slow for the loop: rise faster so the pop still happens
            v *= life / (0.9 * D / m)
        cyc = []
        for _ in range(m):
            x0 = cx + float(rng.uniform(-half, half))
            y0 = bottom(x0) + r0 * 1.2
            y_top = surf - r0 * 0.45
            t_arr = max(y_top - y0, 1.0) / v + BUB_TAU
            cyc.append(dict(x0=x0, y0=y0, top=y_top, arr=t_arr, pop=t_arr + BUB_HOLD, ph=float(rng.uniform(0, 2 * math.pi))))
        bub.append(dict(r0=r0, v=v, m=m, ph=(i + float(rng.uniform(0.1, 0.9))) / n % 1.0, cyc=cyc,
                        drops=[(float(rng.uniform(40, 90)) * s_, float(rng.uniform(170, 250))) for s_ in (-1, 1)]))
    bones = []
    for i, b in enumerate(bub):
        bones.append((c.bone(f"b{i}"), c.bone(f"ring{i}"), [c.bone(f"d{i}_{j}") for j in range(2)]))
    s_b = [_pic(c, bb, "bubble_rim", b["r0"] * 2.2) for b, (bb, _, _) in zip(bub, bones)]
    s_r = [_pic(c, rb, "ring", b["r0"] * 5.0) for b, (_, rb, _) in zip(bub, bones)]
    s_d = [[_pic(c, d, "glow_core", b["r0"] * 1.4) for d in db] for b, (_, _, db) in zip(bub, bones)]
    c.show(s_b + s_r + [s for ds in s_d for s in ds], 0, None)
    alpha = float(P["alpha"])

    def state(b, t):
        k, q = _life(t, D, b["m"], b["ph"])
        cy = b["cyc"][k]
        tau = q * D / b["m"]
        y = min(cy["y0"] + b["v"] * (tau - BUB_TAU * (1 - math.exp(-tau / BUB_TAU))), cy["top"])
        grow = 1 + BUB_GROW * (y - cy["y0"]) / max(cy["top"] - cy["y0"], 1.0)
        r = b["r0"] * grow
        zig = BUB_ZIG * r * math.sin(2 * math.pi * BUB_ZIG_HZ * tau + cy["ph"]) * smooth(tau, 0, 0.2) * (1 - smooth(tau, cy["arr"] - 0.08, cy["arr"]))
        return k, cy, tau, y, grow, zig

    for b, (bb, rb, db), sb, sr, sd in zip(bub, bones, s_b, s_r, s_d):
        wr = _wraps(D, b["m"], b["ph"])
        tsb = _with_wraps(times_dense(0, D, FPS), wr)

        def pos(t, b=b):
            k, cy, tau, y, grow, zig = state(b, t)
            return cy["x0"] + zig, y

        def scl(t, b=b):
            k, cy, tau, y, grow, zig = state(b, t)
            wob = 0.07 * math.sin(4 * math.pi * BUB_ZIG_HZ * tau + cy["ph"])
            born = 0.4 + 0.6 * smooth(tau, 0, 0.12)                       # nucleates small
            flat = 1 - 0.14 * smooth(tau, cy["arr"] - 0.03, cy["arr"] + 0.03)   # flattens under the surface skin
            burst = 1 + 0.35 * smooth(tau, cy["pop"] - 0.02, cy["pop"] + 0.05)
            return grow * born * (1 + wob) * burst / flat ** 0.5, grow * born * (1 - wob) * flat * burst

        def alp(t, b=b):
            k, cy, tau, y, grow, zig = state(b, t)
            return hexa(col, c.a(alpha * smooth(tau, 0, 0.1) * (1 - smooth(tau, cy["pop"], cy["pop"] + 0.05))))
        c.bone_keys(bb, "translate", tsb, pos)
        c.bone_keys(bb, "scale", tsb, scl)
        c.color_keys(sb, tsb, alp)
        # the pop: windows around every burst (sparse keys elsewhere: nothing shows)
        per = D / b["m"]
        wins = [((j - b["ph"]) * per + cy["pop"] - 0.03, (j - b["ph"]) * per + cy["pop"] + POP_T + 0.03)
                for j in range(-1, b["m"] + 1) for cy in [b["cyc"][j % b["m"]]]]
        tsp = _with_wraps(_windows(D, wins, 40), wr)

        def pop_u(t, b=b):
            k, cy, tau, *_ = state(b, t)
            x_pop = cy["x0"]
            return cy, tau - cy["pop"], x_pop

        c.bone_keys(rb, "translate", tsp, lambda t, b=b: (pop_u(t, b)[2], surf))
        c.bone_keys(rb, "scale", tsp, lambda t, b=b: (lambda e: (e, e * 0.3))(0.25 + 0.95 * ease_out(max(0.0, pop_u(t, b)[1]) / POP_T, 2.5)))
        c.color_keys(sr, tsp, lambda t, b=b: hexa(col, c.a(0.85 * smooth(pop_u(t, b)[1], 0, 0.03) * (1 - smooth(pop_u(t, b)[1], 0.06, POP_T)))))
        for (vx, vy), d, s in zip(b["drops"], db, sd):
            land = 2 * vy / POP_G

            def dpos(t, b=b, vx=vx, vy=vy, land=land):
                cy, u, x_pop = pop_u(t, b)
                u = min(max(u, 0.0), land)
                return x_pop + vx * u, surf + vy * u - 0.5 * POP_G * u * u

            c.bone_keys(d, "translate", tsp, dpos)
            c.color_keys(s, tsp, lambda t, b=b, land=land: hexa("FFFFFF", c.a(0.9 * smooth(pop_u(t, b)[1], 0, 0.02) * (1 - smooth(pop_u(t, b)[1], land * 0.8, land)))))
    return _finish(c, P, duration=D, loop=D, bubbles=n, surface_y=surf,
                   lives=[b["m"] for b in bub], pops_per_loop=sum(b["m"] for b in bub))


# ====================================================================== prop_drip
def prop_drip(c: Ctx, P: dict) -> dict:
    """Honey / slime / wax drips: a drop swells at `at` and stretches as its neck thins, snaps off (prop_drip_snap), falls
    with gravity stretched by its speed, splats at `floor_y` (prop_drip_splat: a flattened splash + droplets) while the
    stub left hanging springs back up. Liquid in normal blend, highlights additive. loop=true closes the cycle."""
    D = 2.4
    loop = bool(P["loop"])
    S = float(P["size"])
    ax, ay = (float(v) for v in P["at"])
    fy = float(P["floor_y"])
    col = _hexn(P["color"], "F2A516")
    s0 = STUB if loop else 0.0
    rng = np.random.default_rng(c.seed + 521)
    b_hang = c.bone("hang", x=ax, y=ay)
    b_fall, b_splat = c.bone("fall"), c.bone("splat", x=ax, y=fy)
    nd = max(0, int(P["count"]))
    b_dr = [c.bone(f"drop{j}") for j in range(nd)]
    b_hh = c.bone("hang_hi", b_hang, -0.17 * S, -1.0 * S)
    b_fh = c.bone("fall_hi", b_fall, -0.16 * S, 0.1 * S)
    s_hang = _pic(c, b_hang, "drip_drop", S, height=1.5 * S, blend="normal", oy=-0.75 * S)
    s_fall = _pic(c, b_fall, "drip_drop", S, height=1.5 * S, blend="normal", oy=0.3 * S)
    s_splat = _pic(c, b_splat, "drip_blob", 2.0 * S, blend="normal")
    s_dr = [_pic(c, b, "drip_blob", 0.45 * S, blend="normal") for b in b_dr]
    s_hh = _pic(c, b_hh, "glow_core", 0.5 * S)
    s_fh = _pic(c, b_fh, "glow_core", 0.5 * S)
    # ---- times
    tf = DRIP_FORM
    w0 = 2 * math.pi * STUB_HZ
    wd = w0 * math.sqrt(1 - STUB_ZETA ** 2)

    def neck(t):
        return min(max((t - (tf - DRIP_NECK)) / DRIP_NECK, 0.0), 1.0) ** 2.2

    def hang(t):
        if t < tf:                                   # swell (fed from above), then the neck thins and it stretches
            g = s0 + (1 - s0) * ease_out(t / (tf - DRIP_NECK * 0.4), 2.0)
            st = 1 + DRIP_STRETCH * neck(t)
            return g / math.sqrt(st), g * st
        u = t - tf                                    # the stub recoils on a damped spring and settles at STUB
        osc = STUB_KICK * math.exp(-STUB_ZETA * w0 * u) * math.cos(wd * u) * (1 - smooth(t, D - 0.35, D - 0.02))
        return STUB * (1 - 0.25 * osc), STUB * (1 + osc)

    sy_snap = hang(tf - 1e-6)[1]
    y_s = ay - 1.05 * S * sy_snap                    # the bulb centre at the pinch
    h_fall = y_s - 0.45 * S - fy
    if h_fall <= 0:
        raise ValueError("floor_y must be below the drip point `at`")
    t_hit = tf + (-DRIP_V0 + math.sqrt(DRIP_V0 ** 2 + 2 * DRIP_G * h_fall)) / DRIP_G
    v_hit = DRIP_V0 + DRIP_G * (t_hit - tf)
    if t_hit > D - 0.45:
        D = t_hit + 0.6                              # a long fall: the recipe gets longer, never cut

    def fall(t):
        u = min(max(t - tf, 0.0), t_hit - tf) if t < D - 0.005 else 0.0
        v = DRIP_V0 + DRIP_G * u
        st = 1 + min(0.9, v * FALL_STRETCH)
        return (ax, y_s - DRIP_V0 * u - 0.5 * DRIP_G * u * u), (0.95 / math.sqrt(st), 0.95 * st)

    def splat(t):
        u = t - t_hit
        if u < 0 or t >= D - 0.005:
            return 0.3, 0.6
        spread = 0.45 + 0.8 * ease_out(u / SPLAT_T, 2.6) + 0.12 * smooth(u, SPLAT_T, 1.2)     # then viscous creep
        flat = 0.26 + 0.28 * math.exp(-u / 0.045) + 0.05 * math.exp(-u / 0.15) * math.sin(2 * math.pi * 7 * u)
        return spread, flat

    fade_end = lambda t: 1 - smooth(t, D - 0.32, D - 0.02)  # noqa: E731
    drops = []
    for j in range(nd):
        a = math.radians(float(rng.uniform(40, 75)) if j % 2 else float(rng.uniform(105, 140)))     # both sides
        sp = float(rng.uniform(320, 480)) * min(1.5, max(0.6, v_hit / 700))      # a harder hit throws them further
        drops.append((sp * math.cos(a), sp * math.sin(a), 2 * sp * math.sin(a) / DRIP_G))
    ts = times_dense(0, D, FPS)
    c.show([s_hang, s_hh], 0, None)
    c.show([s_fall, s_fh], tf, t_hit)
    c.show([s_splat], t_hit, D)
    c.show(s_dr, t_hit, D)
    snap = [tf - 0.0005, tf, tf + 0.0005]
    th = sorted(set(ts) | set(snap))
    c.bone_keys(b_hang, "scale", th, hang)
    c.color_keys(s_hang, [0.0, D], lambda t: hexa(col, c.a(1.0)))
    c.color_keys(s_hh, th, lambda t: hexa("FFFFFF", c.a(0.7 * min(1.0, 2.5 * hang(t)[0]))))
    tfall = sorted(set(times_dense(tf, t_hit, 60)) | {0.0, D - 0.006, D})
    c.bone_keys(b_fall, "translate", tfall, lambda t: fall(t)[0])
    c.bone_keys(b_fall, "scale", tfall, lambda t: fall(t)[1])
    c.color_keys(s_fall, [0.0, D], lambda t: hexa(col, c.a(1.0)))
    c.color_keys(s_fh, [0.0, D], lambda t: hexa("FFFFFF", c.a(0.7)))
    tsp = sorted(set(times_dense(t_hit, D, FPS)) | {0.0, D - 0.006, D})
    c.bone_keys(b_splat, "scale", tsp, splat)
    c.color_keys(s_splat, tsp, lambda t: hexa(col, c.a(fade_end(t) * (t >= t_hit))))
    for b, s, (vx, vy, land) in zip(b_dr, s_dr, drops):
        def dpos(t, vx=vx, vy=vy, land=land):
            u = min(max(t - t_hit, 0.0), land) if t < D - 0.005 else 0.0
            return ax + vx * u, fy + 0.1 * S + vy * u - 0.5 * DRIP_G * u * u
        td = sorted(set(times_dense(t_hit, min(D - 0.01, t_hit + land + 0.1), 60)) | {0.0, D - 0.006, D})
        c.bone_keys(b, "translate", td, dpos)
        c.color_keys(s, td, lambda t, land=land: hexa(col, c.a((1 - smooth(t - t_hit, land * 0.85, land + 0.06)) * fade_end(t) * (t >= t_hit))))
    c.ab.event(c.T(tf), "prop_drip_snap")
    c.ab.event(c.T(t_hit), "prop_drip_splat")
    return _finish(c, P, duration=D * c.k, loop=D * c.k if loop else None, snap_at=c.T(tf), splat_at=c.T(t_hit),
                   hit_speed=round(v_hit, 1))


# ====================================================================== prop_steam
def prop_steam(c: Ctx, P: dict) -> dict:
    """Steam puffs from a spout `at` in rhythm: each puff jets out along `angle`, drag slows it to the buoyant rise, it
    expands (~sqrt t), drifts with the wind and evaporates. The rhythm quickens and the puffs grow to a kettle climax at
    `climax` s (prop_steam_climax): a whistle jet (a vibrating stretched streak) and fast, big puffs."""
    D = float(P["duration"])
    climax = min(float(P["climax"]), D - 0.3)
    ax, ay = (float(v) for v in P["at"])
    ang = math.radians(float(P["angle"]))
    ux, uy = math.cos(ang), math.sin(ang)
    size, drift = float(P["size"]), float(P["drift"])
    col = _hexn(P["color"], "F4F8FC")
    rng = np.random.default_rng(c.seed + 531)
    emits, t = [], 0.06
    while t < D - 0.25:
        k = 1.0 if t >= climax else smooth(t, 0, climax) ** 2
        rate = STEAM_RATE[0] + (STEAM_RATE[1] - STEAM_RATE[0]) * k
        emits.append(dict(t=t, big=(1 + 0.45 * k) * float(rng.uniform(0.85, 1.15)), spd=(1 + 0.9 * k) * float(rng.uniform(0.85, 1.1)),
                          life=STEAM_LIFE * (1 + 0.2 * k) * float(rng.uniform(0.85, 1.15)), spin=float(rng.uniform(-60, 60)),
                          rot0=float(rng.uniform(0, 360)), wob=float(rng.uniform(0, 2 * math.pi)), side=float(rng.uniform(-0.12, 0.12)), k=k))
        t += float(rng.uniform(0.85, 1.15)) / rate
    pool: list[list[dict]] = []                       # each slot replays puffs that do not overlap
    for e in emits:
        for lane in pool:
            if lane[-1]["t"] + lane[-1]["life"] <= e["t"] - 0.01:
                lane.append(e)
                break
        else:
            pool.append([e])
    lanes = [(c.bone(f"puff{i}"), lane) for i, lane in enumerate(pool)]
    s_p = [_pic(c, b, "smoke_puff", size, blend="normal") for b, _ in lanes]
    whistle = bool(P["whistle"])
    if whistle:
        b_jet = c.bone("jet", x=ax, y=ay, rot=float(P["angle"]))
        L = 150.0 * size / 70.0
        s_jg = _pic(c, b_jet, "light_streak", L, height=30.0 * size / 70.0, ox=L * 0.45)
        s_jc = _pic(c, b_jet, "light_streak", L * 0.8, height=9.0 * size / 70.0, ox=L * 0.38)
        b_sp = c.bone("spout", x=ax, y=ay)
        s_sp = _pic(c, b_sp, "glow_core", 46.0 * size / 70.0)
    fade_end = lambda t: 1 - smooth(t, D - 0.4, D)  # noqa: E731

    def puff(e, t):
        u = t - e["t"]
        if u < 0:
            u = 0.0
        if u > e["life"]:
            return None
        V = STEAM_V0 * e["spd"]
        jet = V * STEAM_TAU * (1 - math.exp(-u / STEAM_TAU))
        x = ax + jet * (ux - e["side"] * uy) + drift * u + 6 * math.sin(3.0 * u + e["wob"]) * u
        y = ay + jet * (uy + e["side"] * ux) + STEAM_BUOY * u
        s = e["big"] * (0.3 + STEAM_GROW * math.sqrt(u / e["life"]))
        a = 0.55 * (1 - 0.4 * e["k"]) * smooth(u, CONDENSE * 0.5, CONDENSE * 2.2) * (1 - smooth(u, 0.35 * e["life"], e["life"])) * fade_end(t)
        return x, y, s, e["rot0"] + e["spin"] * u, a

    for (b, lane), s in zip(lanes, s_p):
        ts = {0.0, D}
        for e in lane:
            ts.update(times_dense(e["t"], min(D, e["t"] + e["life"]), 20))

        def at(t, lane=lane):
            cur = lane[0]
            for e in lane:
                if e["t"] <= t + 1e-9:
                    cur = e
            st = puff(cur, t)
            if st is None:                           # finished: hold its last place, invisible
                st = puff(cur, cur["t"] + cur["life"] - 1e-6)
                st = (*st[:4], 0.0)
            return st
        tt = sorted(ts)
        c.bone_keys(b, "translate", tt, lambda t, at=at: at(t)[:2])
        c.bone_keys(b, "scale", tt, lambda t, at=at: (at(t)[2],) * 2)
        c.bone_keys(b, "rotate", tt, lambda t, at=at: at(t)[3])
        c.color_keys(s, tt, lambda t, at=at: hexa(col, c.a(at(t)[4])))
    c.show(s_p, 0, D)
    if whistle:
        tj = times_dense(max(0.0, climax - 0.05), D, 60)
        tj = sorted({0.0, *tj})
        on = lambda t: smooth(t, climax, climax + 0.1) * fade_end(t)  # noqa: E731
        vib = lambda t: 0.07 * math.sin(2 * math.pi * JET_HZ[0] * t) + 0.04 * math.sin(2 * math.pi * JET_HZ[1] * t)  # noqa: E731
        c.show([s_jg, s_jc, s_sp], max(0.0, climax - 0.05), D)
        c.bone_keys(b_jet, "scale", tj, lambda t: ((0.3 + 0.7 * ease_out((t - climax) / 0.12, 2)) * (1 + vib(t)) if t >= climax else 0.3,
                                                   1 + 1.8 * vib(t)))
        c.color_keys(s_jg, tj, lambda t: hexa("BFE8FF", c.a(0.75 * on(t))))
        c.color_keys(s_jc, tj, lambda t: hexa("FFFFFF", c.a(0.95 * on(t))))
        c.color_keys(s_sp, tj, lambda t: hexa("E8F6FF", c.a(0.7 * on(t) * (1 + 3 * vib(t)))))
    c.ab.event(c.T(climax), "prop_steam_climax")
    first = emits[0]
    mid = lambda e: puff(e, e["t"] + 0.3 * e["life"])  # noqa: E731
    copies = [[round(mid(e)[0], 2), round(mid(e)[1], 2), round(c.T(e["t"]), 4)] for e in emits[1::2][:24]]
    hint = dict(template="smoke_puff", params=dict(size=256, duration=STEAM_LIFE, fps=24, light="FFFFFF", mid="DCE3EA",
                                                   shadow="98A2AE", start_scale=10, end_scale=110, burst=3, rise=0.35,
                                                   turbulence=26, erode=0.75, shade=0.25, opacity=70, seed=c.seed),
                mode="alpha", seq_mode="once", parent=c.group, x=round(mid(first)[0], 2), y=round(mid(first)[1], 2),
                scale=round(size * 1.8 / 256, 4), start=c.T(first["t"]), copies=copies,
                alt=dict(template="smoke_haze", params=dict(width=160, height=384, duration=2.0, light="FFFFFF", mid="D5DCE4",
                                                            shadow="8C96A2", rise=110, swirl=14, density=0.7, edge=0.2),
                         mode="alpha", seq_mode="loop", note="a steady steam column above the spout instead of puffs"),
                note="realistic steam: ae_template smoke_puff -> ae_fx_to_spine with these args; copies = one per other puff "
                     "(they share the frames); keep the Spine puffs for the jet or drop their alpha")
    return _finish(c, P, duration=D, climax_at=c.T(climax), puffs=len(emits), slots_used=len(lanes),
                   emits=[[c.T(e["t"]), round(e["big"], 3)] for e in emits], ae_hint=hint)


# ====================================================================== prop_electric
def _arc(A, B, nseg: int, jag: float, rng) -> list[tuple[float, float]]:
    """A zig-zag polyline A -> B: interior vertices pushed sideways, alternating sides, strongest mid-way."""
    L = math.hypot(B[0] - A[0], B[1] - A[1]) or 1.0
    nx, ny = -(B[1] - A[1]) / L, (B[0] - A[0]) / L
    side = 1 if rng.random() < 0.5 else -1
    out = [A]
    for k in range(1, nseg):
        s = k / nseg
        off = side * jag * L * float(rng.uniform(0.35, 1.0)) * (0.55 + 0.45 * math.sin(math.pi * s))
        side = -side
        out.append((A[0] + (B[0] - A[0]) * s + nx * off, A[1] + (B[1] - A[1]) * s + ny * off))
    return out + [B]


def prop_electric(c: Ctx, P: dict) -> dict:
    """The prop is charged: crackles arc between random PAIRS of `points` (nearer pairs more often, like real sparks
    jumping the shortest gap). Each crackle is a zig-zag of light_streak segments, coloured glow + white core, that
    re-strikes 2-3 times with a new jag; the ends flare and the prop's charge glow flashes with them. Seamless loop."""
    D = float(P["duration"])
    pts = [(float(p[0]), float(p[1])) for p in P["points"]]
    if len(pts) < 2:
        raise ValueError("points needs at least two [x, y] points")
    n = max(1, int(P["count"]))
    nseg = max(2, int(P["segments"]))
    jag = float(P["jag"])
    col = _hexn(P["color"], "7FD4FF")
    rng = np.random.default_rng(c.seed + 541)
    crackles = []
    span = D - ARC_LIFE[1] - 0.06
    for t0 in [0.03 + span * (q + float(rng.uniform(0.0, 0.85))) / n for q in range(n)]:      # spread through the loop
        i = int(rng.integers(len(pts)))
        others = [j for j in range(len(pts)) if j != i]
        w = np.array([1.0 / max(math.hypot(pts[j][0] - pts[i][0], pts[j][1] - pts[i][1]), 1.0) for j in others])
        j = others[int(rng.choice(len(others), p=w / w.sum()))]
        life = float(rng.uniform(*ARC_LIFE))
        nf = int(rng.integers(*ARC_FLASHES))
        fl = [t0] + sorted(t0 + life * float(f) for f in rng.uniform(0.25, 0.75, nf - 1))
        crackles.append(dict(t0=t0, t1=t0 + life, pair=(i, j), flashes=[(tf, _arc(pts[i], pts[j], nseg, jag, rng)) for tf in fl]))
    rigs: list[list[dict]] = []
    for cr in crackles:
        for rig in rigs:
            if rig[-1]["t1"] + 0.03 <= cr["t0"]:
                rig.append(cr)
                break
        else:
            rigs.append([cr])
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    bx0, bx1, by0, by1 = min(xs), max(xs), min(ys), max(ys)
    b_ch = c.bone("charge", x=(bx0 + bx1) / 2, y=(by0 + by1) / 2)
    s_ch = _pic(c, b_ch, "glow_soft", max(bx1 - bx0, by1 - by0, 120.0) * 1.5)
    built = []
    for r, rig in enumerate(rigs):
        segs = [c.bone(f"r{r}s{k}") for k in range(nseg)]
        ends = [c.bone(f"r{r}e{k}") for k in range(2)]
        glow = [_pic(c, b, "light_streak", SEG_W, height=GLOW_H * float(P["thickness"])) for b in segs]
        core = [_pic(c, b, "light_streak", SEG_W, height=CORE_H * float(P["thickness"])) for b in segs]
        eg = [_pic(c, b, "glow_core", 46.0 * float(P["thickness"])) for b in ends]
        built.append((rig, segs, ends, glow, core, eg))
    c.show([s_ch], 0, None)

    def bright(cr, t):
        if not (cr["t0"] <= t <= cr["t1"]):
            return 0.0
        last = max(tf for tf, _ in cr["flashes"] if tf <= t + 1e-9)
        return max(0.3, math.exp(-(t - last) / ARC_DECAY)) * (1 - smooth(t, cr["t1"] - 0.03, cr["t1"]))

    wins = [(cr["t0"] - 0.01, cr["t1"] + 0.01) for cr in crackles]
    tw = _windows(D, wins, 90, [tf + POST for cr in crackles for tf, _ in cr["flashes"]])
    c.color_keys(s_ch, tw, lambda t: hexa(col, c.a(0.1 + 0.45 * max([bright(cr, t) for cr in crackles] + [0.0]))))
    for rig, segs, ends, glow, core, eg in built:
        steps = [(cr["flashes"][0][0], cr["flashes"][0][1])] + [f for cr in rig for f in cr["flashes"]]
        first = rig[0]["flashes"][0][1]
        key_ts = [0.0] + [tf for tf, _ in steps[1:]] + [D]
        polys = [first] + [poly for _, poly in steps[1:]] + [first]
        for k, b in enumerate(segs):
            def seg(poly, k=k):
                (x0, y0), (x1, y1) = poly[k], poly[k + 1]
                return (x0 + x1) / 2, (y0 + y1) / 2, math.degrees(math.atan2(y1 - y0, x1 - x0)), math.hypot(x1 - x0, y1 - y0)
            g = [seg(p) for p in polys]
            c.ab.bone(b, "translate", [(c.T(t), q[0], q[1]) for t, q in zip(key_ts, g)], "stepped")
            c.ab.bone(b, "rotate", [(c.T(t), q[2]) for t, q in zip(key_ts, g)], "stepped")
            c.ab.bone(b, "scale", [(c.T(t), q[3] * ARC_OVER / SEG_W, 1.0) for t, q in zip(key_ts, g)], "stepped")
        for e, b in enumerate(ends):
            c.ab.bone(b, "translate", [(c.T(t), *(p[0] if e == 0 else p[-1])) for t, p in zip(key_ts, polys)], "stepped")
        att = [(0.0, None)] + [x for cr in rig for x in ((c.T(cr["t0"]), "fx"), (c.T(cr["t1"]), None))]
        for s in glow + core + eg:
            c.ab.slot_attachment(s, att)
        rw = [(cr["t0"] - 0.01, cr["t1"] + 0.01) for cr in rig]
        tr = _windows(D, rw, 90, [tf + POST for cr in rig for tf, _ in cr["flashes"]])
        br = lambda t, rig=rig: max([bright(cr, t) for cr in rig] + [0.0])  # noqa: E731
        for s in glow:
            c.color_keys(s, tr, lambda t, br=br: hexa(col, c.a(0.9 * br(t))))
        for s in core:
            c.color_keys(s, tr, lambda t, br=br: hexa("FFFFFF", c.a(br(t))))
        for s in eg:
            c.color_keys(s, tr, lambda t, br=br: hexa(col, c.a(0.85 * br(t))))
    # AE: one comp over the points' box; a bolt variant per pair (start/end as comp fractions, AE y down), copies in time
    m = 40.0
    cw, chh = bx1 - bx0 + 2 * m, by1 - by0 + 2 * m
    fx_ = lambda p: [round((p[0] - bx0 + m) / cw, 3), round(1 - (p[1] - by0 + m) / chh, 3)]  # noqa: E731
    lead = 0.03
    variants = {}
    for cr in crackles:
        key = tuple(sorted(cr["pair"]))
        variants.setdefault(key, []).append(cr["t0"])
    vlist = [dict(pair=list(k), params=dict(width=int(math.ceil(cw / 8) * 8), height=int(math.ceil(chh / 8) * 8), duration=0.3,
                                            start=fx_(pts[k[0]]), end=fx_(pts[k[1]]), color=col, segments=8, amplitude=0.25,
                                            branching=0.15, bolt_width=0.02, lead=lead, restrikes=1, flash=0.5, seed=c.seed + q),
                  args=dict(mode="additive", seq_mode="once", parent=c.group, x=round((bx0 + bx1) / 2, 2), y=round((by0 + by1) / 2, 2),
                            scale=1.0, start=round(c.T(ts_[0]) - lead, 4), hit_ae=lead, hit_at=c.T(ts_[0]),
                            copies=[[round((bx0 + bx1) / 2, 2), round((by0 + by1) / 2, 2), round(c.T(t) - lead, 4)] for t in ts_[1:]]))
             for q, (k, ts_) in enumerate(sorted(variants.items()))]
    hint = dict(template="lightning", variants=vlist,
                note="AE crackles: render each variant with ae_template lightning (params), then ae_fx_to_spine with its args "
                     "(copies = the later crackles on the same pair, sharing the frames); lower the Spine arc alphas or keep "
                     "them for the stroke flashes")
    return _finish(c, P, duration=D, loop=D, crackles=[dict(t0=c.T(cr["t0"]), t1=c.T(cr["t1"]), pair=list(cr["pair"]),
                                                            strokes=len(cr["flashes"])) for cr in crackles],
                   rigs=len(rigs), ae_hint=hint)


# ====================================================================== prop_freeze
def _warp_idle(c: Ctx, prop: str, idle: str, car: str, speed: Callable[[float], float], D: float, ts) -> dict:
    """Replay the prop's idle with a time warp phase(t) = integral of speed: on the fx carriers above it (ours: their
    idle keys, re-keyed into this animation) and, for keys on the artist's prop bone, mirrored onto our carrier `car`.
    Returns {timeline: fn(t)} of what was mirrored onto `car` (so the shiver adds onto it)."""
    sk = c.sk
    src = sk.animations.get(idle)
    if src is None:
        return {}
    grid = np.linspace(0, D, max(2, int(D * 240)) + 1)
    sp = np.array([speed(t) for t in grid])
    ph = np.concatenate([[0.0], np.cumsum((sp[1:] + sp[:-1]) / 2 * np.diff(grid))])
    phase = lambda t: float(np.interp(t, grid, ph))  # noqa: E731
    mirrored = {}
    for b in _carrier_chain(sk, prop) + [prop]:
        for tl, keys in list(src.bones.get(b, {}).items()):
            if tl not in ("rotate", "translate", "scale") or not keys:
                continue
            L = max(k.time for k in keys) or 1.0
            keys = list(keys)
            fn = lambda t, keys=keys, tl=tl, L=L: _sample(keys, tl, phase(t) % L if phase(t) > L else phase(t))  # noqa: E731
            if b == prop:
                mirrored[tl] = fn
            else:
                c.bone_keys(b, tl, ts, lambda t, fn=fn: fn(t) if len(fn(t)) > 1 else fn(t)[0])
    return mirrored


def prop_freeze(c: Ctx, P: dict) -> dict:
    """Frost creeps over the prop from one edge (the front slows as it goes, ~t^0.6) as icy patches and a bright frost
    front; ice crystals sparkle where it has frozen. The prop's idle (on carriers, or mirrored from its own keys) slows to
    a stop, it contracts with a tiny shiver at the lock and a cold flash fires (prop_frozen). thaw > 0 reverses it."""
    lock = float(P["lock"])
    thaw = float(P["thaw"])
    hold = float(P["hold"])
    D = lock + hold + thaw + 0.3 if thaw > 0 else lock + 0.9
    bx, by, bw, bh = (float(v) for v in P["box"])
    col = _hexn(P["color"], "A8E6FF")
    sk = c.sk
    rng = np.random.default_rng(c.seed + 551)
    frm = str(P["from"])
    rot = {"bottom": 0.0, "top": 180.0, "left": -90.0, "right": 90.0}.get(frm)
    if rot is None:
        raise ValueError("from must be bottom | top | left | right")
    ext, wid = (bh, bw) if frm in ("bottom", "top") else (bw, bh)
    t_thaw = lock + hold
    p = lambda t: (min(max(t / lock, 0.0), 1.0)) ** FRONT_POW  # noqa: E731
    melt = lambda t: smooth(t, t_thaw, t_thaw + thaw) if thaw > 0 else 0.0  # noqa: E731
    # ---- the prop: carriers above it (or a bone of our own)
    if P["prop"]:
        prop = str(P["prop"])
        if not sk.has_bone(prop):
            raise ValueError(f"no bone {prop!r} for the prop")
        from .fx_reels import _carrier
        car = _carrier(c, prop, "freeze")
    else:
        prop = car = c.bone("prop", x=bx, y=by)
    frame = c.bone("frame", x=bx, y=by, rot=rot)       # local +y = the way the frost travels
    b_fl = c.bone("flash", x=bx, y=by)
    b_rim = c.bone("rim", x=bx, y=by, sx=bw / max(bw, bh), sy=bh / max(bw, bh))
    b_front = c.bone("front", frame)
    patches = []
    nP = max(4, int(P["patches"]))
    cols = max(2, round(math.sqrt(nP * wid / max(ext, 1.0))))
    rows = max(2, math.ceil(nP / cols))
    for i in range(rows * cols):
        u = 0.12 + 0.76 * (i % cols + float(rng.uniform(0.25, 0.75))) / cols
        v = 0.1 + 0.8 * (i // cols + float(rng.uniform(0.25, 0.75))) / rows
        d = min(1.0, max(0.0, v + float(rng.uniform(-0.08, 0.08))))
        edge = min(u * wid, (1 - u) * wid, v * ext, (1 - v) * ext)        # a glow_soft shows out to ~0.3 of its width:
        w = min(2.6 * max(wid / cols, ext / rows), (edge + 12.0) / 0.3)   # big and overlapping, but never past the box
        patches.append(dict(b=c.bone(f"p{i}", frame, (u - 0.5) * wid, (v - 0.5) * ext), d=d, t=lock * d ** (1 / FRONT_POW), w=w))
    crystals = []
    for i in range(int(P["count"])):
        u, v = float(rng.uniform(0.08, 0.92)), float(rng.uniform(0.05, 0.95))
        crystals.append(dict(b=c.bone(f"x{i}", frame, (u - 0.5) * wid, (v - 0.5) * ext), t=lock * v ** (1 / FRONT_POW) + 0.05,
                             w=float(rng.uniform(26, 50)), ph=float(rng.uniform(0, 2 * math.pi)), hz=float(rng.uniform(1.2, 2.6))))
    s_pat = [_pic(c, q["b"], "glow_soft", q["w"], blend="normal") for q in patches]     # a pale ice film (normal: it TINTS)
    s_rim = _pic(c, b_rim, "cell_glow", max(bw, bh) * 1.85)          # its outline sits on the box edge
    s_front = _pic(c, b_front, "light_streak", wid * 1.08, height=46.0)
    s_cry = [_pic(c, q["b"], "flare_star", q["w"]) for q in crystals]
    s_fl = _pic(c, b_fl, "glow_soft", math.hypot(bw, bh) * 1.5)
    b_ring = c.bone("ring", x=bx, y=by)
    s_ring = _pic(c, b_ring, "ring", max(bw, bh) * 1.1)
    c.show(s_pat + [s_rim, s_front] + s_cry + [s_fl, s_ring], 0, None)      # frozen stays frozen (hold the last frame)
    ts = times_dense(0, D, FPS)
    for q, s in zip(patches, s_pat):
        on = lambda t, q=q: ease_out((t - q["t"]) / 0.4, 2.2) if t > q["t"] else 0.0  # noqa: E731
        off = lambda t, q=q: 1 - smooth(t, t_thaw + thaw * (1 - q["d"]) * 0.7, t_thaw + thaw * ((1 - q["d"]) * 0.7 + 0.3)) if thaw > 0 else 1.0  # noqa: E731
        c.bone_keys(q["b"], "scale", ts, lambda t, on=on, off=off: (max(0.02, (0.2 + 0.8 * on(t)) * (0.4 + 0.6 * off(t))),) * 2)
        c.color_keys(s, ts, lambda t, on=on, off=off: hexa(_hexn(P["color2"], "D6F2FF"), c.a(0.55 * on(t) * off(t))))
    c.bone_keys(b_front, "translate", ts, lambda t: (0.0, -ext / 2 + ext * p(t)))
    c.color_keys(s_front, ts, lambda t: hexa(col, c.a(0.7 * smooth(t, 0, 0.12) * (1 - smooth(t, lock - 0.15, lock + 0.1)))))
    c.bone_keys(b_front, "scale", ts, lambda t: (1.0, 1 + 0.25 * math.sin(2 * math.pi * 6 * t)))
    c.color_keys(s_rim, ts, lambda t: hexa(col, c.a(0.3 * smooth(t, lock - 0.35, lock) * (1 - melt(t)) + 0.35 * math.exp(-max(0.0, t - lock) / 0.15) * (t >= lock))))
    for q, s in zip(crystals, s_cry):
        def tw(t, q=q):
            if t < q["t"]:
                return 0.0, 0.0
            pop = ease_out((t - q["t"]) / 0.18, 3) * (1 - 0.35 * smooth(t, q["t"] + 0.18, q["t"] + 0.5))
            spark = max(0.0, math.sin(2 * math.pi * q["hz"] * (t - q["t"]) + q["ph"])) ** 6
            return pop * (1 - melt(t)), (0.55 + 0.45 * spark) * (1 - melt(t))
        c.bone_keys(q["b"], "scale", ts, lambda t, tw=tw: (max(0.01, tw(t)[0]),) * 2)
        c.bone_keys(q["b"], "rotate", ts, lambda t, q=q: 45.0 * max(0.0, t - q["t"]))
        c.color_keys(s, ts, lambda t, tw=tw: hexa("FFFFFF", c.a(tw(t)[1] * (tw(t)[0] > 0.011))))
    tl = sorted(set(ts) | set(times_dense(lock - 0.02, min(D, lock + 0.5), 60)))
    c.color_keys(s_fl, tl, lambda t: hexa("E8FBFF", c.a(0.55 * smooth(t, lock - 0.04, lock) * math.exp(-max(0.0, t - lock) / 0.12))))
    c.bone_keys(b_fl, "scale", tl, lambda t: (0.6 + 0.5 * ease_out((t - lock + 0.04) / 0.3, 2),) * 2)
    c.bone_keys(b_ring, "scale", tl, lambda t: (0.5 + 0.8 * ease_out(max(0.0, t - lock) / 0.4, 2.4),) * 2)
    c.color_keys(s_ring, tl, lambda t: hexa(col, c.a(0.8 * smooth(t, lock, lock + 0.03) * (1 - smooth(t, lock + 0.05, lock + 0.4)))))
    # ---- the prop slows to a stop, contracts and shivers at the lock; the thaw starts it again
    speed = lambda t: (1 - smooth(t, SLOW_FROM * lock, lock)) + (smooth(t, t_thaw, t_thaw + thaw) if thaw > 0 else 0.0)  # noqa: E731
    tc = sorted(set(ts) | set(times_dense(lock - 0.02, min(D, lock + SHIVER_T + 0.05), 60)))
    mir = _warp_idle(c, prop, str(P["idle"] or c.anim), car, speed, D, tc) if P["prop"] else {}
    shiver = lambda t: SHIVER_DEG * math.exp(-(t - lock) / (SHIVER_T / 3)) * math.sin(2 * math.pi * SHIVER_HZ * (t - lock)) if t >= lock else 0.0  # noqa: E731
    shrink = lambda t: 1 - CONTRACT * smooth(t, lock - 0.05, lock + 0.03) * (1 - melt(t))  # noqa: E731
    rot0 = mir.get("rotate", lambda t: (0.0,))
    sc0 = mir.get("scale", lambda t: (1.0, 1.0))
    c.bone_keys(car, "rotate", tc, lambda t: rot0(t)[0] + shiver(t))
    c.bone_keys(car, "scale", tc, lambda t: (sc0(t)[0] * shrink(t), sc0(t)[1] * shrink(t)))
    if "translate" in mir:
        c.bone_keys(car, "translate", tc, lambda t: mir["translate"](t))
    c.ab.event(c.T(lock), "prop_frozen")
    if thaw > 0:
        c.ab.event(c.T(t_thaw), "prop_thaw")
    return _finish(c, P, duration=D * c.k, frozen_at=c.T(lock), thaw_at=c.T(t_thaw) if thaw > 0 else None,
                   carrier=car, prop_bone=prop, idle_mirrored=sorted(mir), patches=len(patches))


# ====================================================================== prop_dissolve
def _own_art(sk, prop: str, under: list[str]) -> list[str]:
    """The prop's own layers among `under`: slots with no FX group (fx_* / ae_* bone) between them and the prop bone."""
    parent = {b.name: b.parent for b in sk.bones}
    out = []
    for n in under:
        b = sk.slot(n).bone
        while b and b != prop and not b.startswith(("fx_", "ae_")):
            b = parent.get(b)
        if b == prop:
            out.append(n)
    return out


def prop_dissolve(c: Ctx, P: dict) -> dict:
    """The prop burns away: a glowing edge (white-hot core over an orange band and a heat glow, its line wavering) sweeps
    across the prop's box, embers lift off it on buoyancy and cool as they rise. With `prop` (or `slots`) a clipping
    mask riding the edge wipes the prop's layers away for real (your slot colours untouched); otherwise hide it at
    prop_dissolve_hide, masked by a flash."""
    D = 2.0
    t0, t1 = (float(v) for v in P["sweep"])
    bx, by, bw, bh = (float(v) for v in P["box"])
    col, hot = _hexn(P["color"], "FF7A1C"), _hexn(P["color2"], "FFD36A")
    rot = {"up": 0.0, "down": 180.0, "left": 90.0, "right": -90.0}.get(str(P["direction"]))
    if rot is None:
        raise ValueError("direction must be up | down | left | right")
    ext, wid = (bh, bw) if P["direction"] in ("up", "down") else (bw, bh)
    m = BAND_H
    sk = c.sk
    rng = np.random.default_rng(c.seed + 561)
    layers = None
    if P["slots"]:
        layers = [str(s) for s in P["slots"]][:2]
    elif P["prop"]:
        if not sk.has_bone(str(P["prop"])):
            raise ValueError(f"no bone {P['prop']!r} for the prop")
        from .fx_props import _descendants
        under = [s.name for s in sk.slots if s.bone in _descendants(sk, str(P["prop"]))]
        if not under:
            raise ValueError(f"no slots hang from {P['prop']!r} to dissolve")
        own = _own_art(sk, str(P["prop"]), under) or under    # FX of earlier recipes on the prop are not its art
        layers = [own[0], own[-1]]
    hide_at = float(P["hide_at"]) if P["hide_at"] is not None else (1.0 if layers else 0.5)
    e = lambda t: smooth(t, t0, t1)  # noqa: E731     the edge's progress 0..1 (eases in and out)
    edge_y = lambda t: -ext / 2 - m + (ext + 2 * m) * e(t)  # noqa: E731
    t_hide = t0 + (t1 - t0) * hide_at if hide_at < 1.0 else t1
    if 0 < hide_at < 1:                              # invert the smoothstep: when does the edge reach hide_at
        lo, hi = t0, t1
        for _ in range(40):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if e(mid) < hide_at else (lo, mid)
        t_hide = (lo + hi) / 2
    frame = c.bone("frame", x=bx, y=by, rot=rot)
    wipe = c.bone("wipe", frame)
    b_heat, b_band, b_core = c.bone("heat", wipe), c.bone("band", wipe), c.bone("core", wipe)
    embers = []
    for i in range(int(P["count"])):
        te = t0 + (t1 - t0) * float(rng.beta(1.6, 1.6))
        u = float(rng.uniform(-0.48, 0.48)) * wid
        embers.append(dict(b=c.bone(f"em{i}"), t=te, u=u, life=float(rng.uniform(*EMBER_LIFE)), vx=float(rng.uniform(-40, 40)),
                           sw=float(rng.uniform(8, 22)), hz=float(rng.uniform(1.0, 2.2)), ph=float(rng.uniform(0, 2 * math.pi)),
                           w=float(rng.uniform(10, 22))))
    s_heat = _pic(c, b_heat, "glow_soft", wid * 1.1, height=BAND_H * 4.5, oy=BAND_H * 0.6)
    s_band = _pic(c, b_band, "light_streak", wid * 1.2, height=BAND_H * 1.8)
    s_core = _pic(c, b_core, "light_streak", wid * 1.05, height=BAND_H * 0.5)
    s_em = [_pic(c, q["b"], "glow_core", q["w"]) for q in embers]
    s_cov = None
    if not layers:
        b_cov = c.bone("cover", x=bx, y=by)
        s_cov = _pic(c, b_cov, "glow_soft", math.hypot(bw, bh) * 1.3)
    c.show([s_heat, s_band, s_core], t0 - 0.05, t1 + 0.05)
    c.show(s_em, t0, D)
    ts = times_dense(0, D, FPS)
    wav = _noise(D, (1.7, 4.3, 9.0), (3.0, 1.6, 0.8), rng)
    c.bone_keys(wipe, "translate", ts, lambda t: (0.0, edge_y(t)))
    c.bone_keys(wipe, "rotate", ts, lambda t: wav(t))                                   # the edge line wavers
    inside = m / (ext + 2 * m)                       # the edge is on the prop between e = inside and 1 - inside
    on = lambda t: smooth(e(t), 0.0, inside + 0.06) * (1 - smooth(e(t), 1 - inside - 0.06, 1.0))  # noqa: E731
    c.bone_keys(b_band, "scale", ts, lambda t: (1.0, 1 + 0.3 * math.sin(2 * math.pi * 11 * t) * math.sin(2 * math.pi * 3 * t)))
    c.color_keys(s_heat, ts, lambda t: hexa(col, c.a(0.7 * on(t))))
    c.color_keys(s_band, ts, lambda t: hexa(col, c.a(0.95 * on(t))))
    c.color_keys(s_core, ts, lambda t: hexa("FFF4D6", c.a(on(t))))
    ca, sa = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    for q, s in zip(embers, s_em):
        ly = edge_y(q["t"]) + BAND_H * 0.3
        x0, y0 = bx + ca * q["u"] - sa * ly, by + sa * q["u"] + ca * ly       # spawn on the edge, in group space
        v_edge = (edge_y(q["t"] + 0.01) - edge_y(q["t"] - 0.01)) / 0.02
        q["v0"] = EMBER_V0 + max(0.0, ca * v_edge)                           # the plume rides the front

        def st(t, q=q, x0=x0, y0=y0):
            u = min(max(t - q["t"], 0.0), q["life"])
            vt = EMBER_LIFT / EMBER_DRAG
            y = y0 + vt * u + (q["v0"] - vt) / EMBER_DRAG * (1 - math.exp(-EMBER_DRAG * u))   # thrown up, then drag-limited
            x = x0 + q["vx"] * (1 - math.exp(-EMBER_DRAG * u)) / EMBER_DRAG + q["sw"] * math.sin(2 * math.pi * q["hz"] * u + q["ph"]) * smooth(u, 0, 0.3)
            return x, y, u / q["life"]
        tse = sorted({0.0, D} | set(times_dense(q["t"], min(D, q["t"] + q["life"]), FPS)))
        c.bone_keys(q["b"], "translate", tse, lambda t, st=st: st(t)[:2])
        c.bone_keys(q["b"], "scale", tse, lambda t, st=st: (1.0 - 0.6 * st(t)[2],) * 2)

        def ec(t, q=q, st=st):
            k = st(t)[2]
            if t < q["t"]:
                return hexa(hot, 0.0)
            rgb = hot if k < 0.3 else (col if k < 0.7 else "B8300A")              # cools: yellow -> orange -> red
            return hexa(rgb, c.a(smooth(t - q["t"], 0, 0.05) * (1 - smooth(k, 0.45, 1.0))))
        c.color_keys(s, tse, ec)
    if s_cov:
        c.show([s_cov], max(0.0, t_hide - 0.12), min(D, t_hide + 0.4))
        tcv = times_dense(max(0.0, t_hide - 0.12), min(D, t_hide + 0.4), 60)
        c.color_keys(s_cov, tcv, lambda t: hexa(hot, c.a(0.85 * smooth(t, t_hide - 0.1, t_hide) * (1 - smooth(t, t_hide, t_hide + 0.35)))))
    res: dict = {}
    if layers:                                        # a clip riding the edge: everything past it is gone
        first, last = layers
        names = [s.name for s in sk.slots]
        if first not in names or last not in names:
            raise ValueError(f"slots {layers} not found")
        name = sk.unique_name(f"fx_clip_{first}", "slot")
        sk.add_slot(Slot(name=name, bone=wipe), before=first)
        hw = wid / 2 + 2 * m
        verts = [-hw, 0.0, hw, 0.0, hw, ext + 4 * m, -hw, ext + 4 * m]
        sk.set_attachment(name, "fx", ClippingAttachment(end=last, vertexCount=4, vertices=[round(v, 2) for v in verts]))
        c.show([name], 0.0, None)                     # off before `start`: the wipe bone sits at its setup pose until then
        res.update(clip_slot=name, clipped=[first, last])
        if P["hide_art"]:                             # nothing must survive the sweep (a rim mesh past the box, the wavering edge)
            span = names[names.index(first):names.index(last) + 1]
            if not P["slots"]:                        # with a prop: only its own art, other recipes' FX keep their keys
                span = _own_art(sk, str(P["prop"]), span) or span
            for s in span:
                had = c.ab.a.slots.get(s, {}).get("attachment", [])
                if not had and sk.slot(s).attachment is None:
                    continue                          # never shown in this animation
                c.ab.slot_attachment(s, [(k.time, k.name) for k in had if k.time < c.T(t1)] + [(c.T(t1), None)])
            res.update(art_hidden=span, art_hidden_at=c.T(t1))
    c.ab.event(c.T(t_hide), "prop_dissolve_hide")
    hint = dict(template=None,
                note="no AE template does a dissolve; build this comp by hand and bring it in with ae_fx_to_spine (mode alpha, "
                     "seq_mode once): 1) the prop's art; 2) a Fractal Noise solid (scale ~60, contrast 160) + a Linear Ramp along "
                     f"the sweep ({P['direction']}), multiplied, as the art's LUMA MATTE; 3) a Levels on the matte whose input "
                     f"black rises 0 -> 255 between {c.T(t0)} and {c.T(t1)} s (the threshold eats the art along a noisy edge); "
                     f"4) the same matte through Minimax/edge detect -> Glow in #{col}, additive (the burning rim); 5) embers: "
                     "ae_template burst (params below) parented to the edge.",
                comp=dict(size=[round(bw * 1.2), round(bh * 1.2)], duration=round((t1 - t0) * c.k + 0.4, 3), sweep=[c.T(t0), c.T(t1)],
                          noise=dict(scale=60, contrast=160, evolution_revs=1), edge_color=col, edge_glow=dict(radius=18, intensity=1.6)),
                embers=dict(template="burst", params=dict(size=256, duration=1.2, n=30, color=hot, color2=col, particle=7, speed=120,
                                                          speed_var=0.6, angle=90, spread=70, gravity=-260, life=1.0, shape="dot",
                                                          glow=0.8, delay_spread=0.8, center_y=0.8)))
    return _finish(c, P, duration=D * c.k, sweep=[c.T(t0), c.T(t1)], hide_at=c.T(t_hide), embers=len(embers), ae_hint=hint, **res)


# ====================================================================== smoke_wisp
def smoke_wisp(c: Ctx, P: dict) -> dict:
    """A slow curling ribbon of smoke from `at` (incense, a cauldron, a chimney): puffs rise along a curling path (a
    sideways wave that travels up the column and grows with height), slowing as they mix, widening and thinning away.
    Staggered respawns, each keyed at its exact wrap time while invisible: a seamless loop."""
    D = float(P["duration"])
    n = max(1, int(P["count"]))
    ax, ay = (float(v) for v in P["at"])
    Hh, curl, size, drift = float(P["height"]), float(P["curl"]), float(P["size"]), float(P["drift"])
    col = _hexn(P["color"], "CFC8D6")
    alpha = float(P["alpha"])
    rng = np.random.default_rng(c.seed + 571)
    m = max(1, round(D / WISP_LIFE))                  # lives per loop per puff
    per = D / m
    mw = max(1, round(D / 2.6))                       # the curl wave travels up: whole cycles per loop
    phi = float(rng.uniform(0, 2 * math.pi))
    puffs = [dict(b=c.bone(f"w{i}"), ph=(i + float(rng.uniform(-0.25, 0.25))) / n % 1.0, spin=float(rng.uniform(-35, 35)),
                  k=float(rng.uniform(0.85, 1.15)), j=float(rng.uniform(-6, 6))) for i in range(n)]
    s_w = [_pic(c, q["b"], "smoke_puff", size * q["k"], blend="normal") for q in puffs]
    c.show(s_w, 0, None)

    def st(q, t):
        _, f = _life(t, D, m, q["ph"])
        h = Hh * f ** WISP_POW                        # buoyant plume: z ~ t^0.75
        amp = curl * smooth(h, 0, 0.7 * Hh)
        x = ax + q["j"] * f + drift * f * per + amp * math.sin(2 * math.pi * h / WISP_LAMBDA - 2 * math.pi * mw * _wt(t, D) / D + phi)
        return x, ay + h, f
    for q, s in zip(puffs, s_w):
        ts = _with_wraps(times_dense(0, D, 15), _wraps(D, m, q["ph"]))
        c.bone_keys(q["b"], "translate", ts, lambda t, q=q: st(q, t)[:2])
        c.bone_keys(q["b"], "scale", ts, lambda t, q=q: (lambda f: (0.5 + WISP_GROW * f, (0.5 + WISP_GROW * f) * (1 + 1.2 * (1 - f) ** 3)))(st(q, t)[2]))
        c.bone_keys(q["b"], "rotate", ts, lambda t, q=q: q["spin"] * st(q, t)[2] * per)
        c.color_keys(s, ts, lambda t, q=q: hexa(col, c.a(alpha * smooth(st(q, t)[2], 0, 0.1) * (1 - smooth(st(q, t)[2], 0.4, 1.0)))))
    hint = dict(template="smoke_haze", params=dict(width=160, height=int(math.ceil(Hh * 1.15 / 8) * 8), duration=round(per, 3), fps=24,
                                                   light="EDE9F2", mid=col, shadow="6E6878", scale=70, contrast=80, brightness=20,
                                                   rise=round(Hh / per, 1), swirl=24, turbulence=26, density=0.55, edge=0.22, seed=c.seed),
                mode="alpha", seq_mode="loop", parent=c.group, x=ax, y=round(ay + Hh * 0.55, 2), scale=1.0, start=c.T(0.0), until=c.T(D),
                note="realistic smoke: ae_template smoke_haze with these params -> ae_fx_to_spine with these args; lower alpha= of "
                     "the Spine wisp (or keep it thin on top for the curl)")
    return _finish(c, P, duration=D, loop=D, puffs=n, lives=m, ae_hint=hint)


# ====================================================================== registry
NAMES = ("flame_wick", "liquid_bubble", "prop_drip", "prop_steam", "prop_electric", "prop_freeze", "prop_dissolve", "smoke_wisp")
RECIPES.update({
    "flame_wick": dict(
        fn=flame_wick, duration=2.0, kind="loop", color="FF8A1E",
        summary="Candle / torch / lantern flame on a wick at the anchor: soft tongue + white-hot core + blue base + haze that "
                "flicker together (seamless), a warm ambient glow. Stays upright in the world and LEANS against the prop's "
                "motion (follow=bone, read from this animation, spring lag + overshoot), else sways gently. ae_hint = AE fire.",
        anchor="The wick tip (the flame grows up from it). With follow, x / y are in that bone's space.",
        options=_o(follow=("", "bone the flame rides (parented to it); its world motion in this animation makes the flame lean"),
                   size=(1.0, "flame size (1 = 92 units tall)"), lean=(1.0, "lean per speed multiplier"),
                   sway=(SWAY_DEG, "degrees of draught sway when nothing moves"), flicker=(1.0, "flicker amount"),
                   glow=(260.0, "ambient glow width (0 = none)"), base=(True, "the blue base of a candle flame"),
                   color2=("FFF3C4", "core colour"))),
    "liquid_bubble": dict(
        fn=liquid_bubble, duration=3.0, kind="loop", color="CFF4FF", count=8,
        summary="Bubbles rise inside a vessel (box area or circle radius), zig-zag, grow as they rise, sit under the surface "
                "and pop: a flat ring + two droplets. Seamless loop (whole lives per loop, hidden across each respawn). Pairs "
                "with liquid_slosh (parent= the liquid bone).",
        anchor="Vessel centre; area / surface_y relative to it.",
        options=_o(area=([0.0, 0.0, 160.0, 220.0], "[x, y, w, h] the liquid's box (centre, size)"),
                   radius=(0.0, "> 0: a round vessel of this radius centred on area's x, y (overrides the box)"),
                   surface_y=(None, "the liquid surface (default: the box top, or 0.45 radius up)"),
                   size=(1.0, "bubble size"), rise=(1.0, "rise speed multiplier"), alpha=(0.9, "bubble opacity"))),
    "prop_drip": dict(
        fn=prop_drip, duration=2.4, kind="one-shot", color="F2A516", count=3, normal_blend=True,
        summary="Honey / slime / wax drip: a drop swells at `at`, stretches as its neck thins, snaps off (prop_drip_snap), "
                "falls with gravity stretched by speed, splats at floor_y (prop_drip_splat: a flattened splash + count "
                "droplets); the stub springs back. Liquid normal blend, highlights additive. loop=true closes the cycle.",
        anchor="Prop centre; at / floor_y relative to it.",
        options=_o(at=([0.0, 0.0], "[x, y] where the drop hangs (the underside of a lip / spout)"),
                   floor_y=(-240.0, "where it lands"), size=(34.0, "drop width"),
                   loop=(False, "true: start from the stub and end on it (a seamless drip cycle)"))),
    "prop_steam": dict(
        fn=prop_steam, duration=3.6, kind="window", color="F4F8FC", normal_blend=True,
        summary="Steam from a spout in rhythm: puffs jet out along angle, drag slows them to a buoyant rise, they expand, drift "
                "and evaporate; the rhythm quickens and the puffs grow to a kettle climax (prop_steam_climax) with a vibrating "
                "whistle jet. Puffs normal blend, jet additive. ae_hint = AE smoke_puff (copies per puff) / smoke_haze.",
        anchor="Prop centre; at relative to it.",
        options=_o(at=([0.0, 0.0], "[x, y] the spout"), angle=(60.0, "jet direction, degrees (0 = right, 90 = up)"),
                   climax=(2.6, "seconds to the climax"), size=(70.0, "puff size"), drift=(25.0, "wind, units/s (+ = right)"),
                   whistle=(True, "the whistle jet at the climax"))),
    "prop_electric": dict(
        fn=prop_electric, duration=2.0, kind="loop", color="7FD4FF", count=8,
        summary="The prop is charged: count crackles per loop arc between random PAIRS of points (nearer pairs more often), "
                "each a zig-zag of light_streak segments (coloured glow + white core) re-striking 2-3 times with a new jag, "
                "ends flaring, a charge glow flashing. Seamless loop. ae_hint = AE lightning, a variant per pair + copies.",
        anchor="Prop centre; points relative to it.",
        options=_o(points=(POINTS, "[[x, y], ...] the spots arcs jump between (terminals, rivets, horns)"),
                   segments=(6, "zig-zag segments per arc"), jag=(0.22, "sideways jitter, fraction of the arc length"),
                   thickness=(1.0, "streak thickness multiplier"))),
    "prop_freeze": dict(
        fn=prop_freeze, duration=2.3, kind="one-shot", color="A8E6FF", count=10, normal_blend=True,
        summary="Frost creeps over the prop from one edge (icy patches + a frost front, slowing as it goes), ice crystals "
                "sparkle (ice film normal blend, light additive); the prop's idle (prop_idle carriers, or its own keys mirrored onto a carrier) slows to a stop, it "
                "contracts and shivers at the lock with a cold flash (prop_frozen). thaw > 0 reverses it (prop_thaw).",
        anchor="Prop centre; box relative to it.",
        options=_o(prop=("", "the prop's bone (a carrier above it shivers / replays its idle); empty: a bone of our own"),
                   idle=("", "animation holding the prop's idle (default: the one this recipe writes into)"),
                   box=(BOX, "[x, y, w, h] the prop's box"), **{"from": ("bottom", "bottom | top | left | right: where the frost starts")},
                   lock=(1.4, "seconds to the lock"), hold=(0.8, "with thaw: seconds frozen"),
                   thaw=(0.0, "> 0: thaw over this many seconds after the hold"), patches=(16, "frost patches"),
                   color2=("D6F2FF", "the ice film colour (normal blend over the prop)"))),
    "prop_dissolve": dict(
        fn=prop_dissolve, duration=2.0, kind="one-shot", color="FF7A1C", count=26,
        summary="The prop burns / dissolves away: a glowing wavering edge sweeps across its box, embers lift off and cool as "
                "they rise. With prop / slots a clipping mask riding the edge wipes its layers for real (colours untouched, keyed off "
                "at the sweep end; the mask acts from `start` on and ends at the prop's own last layer); "
                "event prop_dissolve_hide (sweep end with a clip, else mid-sweep under a flash). ae_hint = the AE dissolve comp.",
        anchor="Prop centre; box relative to it.",
        options=_o(box=(BOX, "[x, y, w, h] the prop's box"), direction=("up", "up | down | left | right: the way the edge moves"),
                   prop=("", "the prop's bone: clip every slot under it"), slots=(None, "[first, last] slots to clip instead"),
                   sweep=([0.15, 1.45], "[start, end] seconds of the sweep"),
                   hide_at=(None, "fraction of the sweep for prop_dissolve_hide (default 1 with a clip, 0.5 without)"),
                   hide_art=(True, "with a clip: key the clipped layers off at the sweep end (no sliver survives)"),
                   color2=("FFD36A", "hot ember colour"))),
    "smoke_wisp": dict(
        fn=smoke_wisp, duration=4.0, kind="loop", color="CFC8D6", count=12, normal_blend=True,
        summary="A slow curling ribbon of smoke from `at` (incense, cauldron, chimney): puffs rise along a curl that travels up "
                "the column and grows with height, slowing, widening and thinning away. Seamless loop. ae_hint = AE smoke_haze.",
        anchor="Prop centre; at relative to it.",
        options=_o(at=([0.0, 0.0], "[x, y] the source"), height=(WISP_H, "how high it rises before it is gone"),
                   curl=(WISP_CURL, "sideways curl at the top"), size=(60.0, "puff size"), drift=(0.0, "wind, units/s"),
                   alpha=(0.5, "smoke opacity"))),
})

_USES = {"flame_wick": ("glow_soft", "flame_tongue", "glow_core"), "liquid_bubble": ("bubble_rim", "ring", "glow_core"),
         "prop_drip": ("drip_drop", "drip_blob", "glow_core"), "prop_steam": ("smoke_puff", "light_streak", "glow_core"),
         "prop_electric": ("glow_soft", "light_streak", "glow_core"),
         "prop_freeze": ("glow_soft", "cell_glow", "light_streak", "flare_star", "ring"),
         "prop_dissolve": ("glow_soft", "light_streak", "glow_core"), "smoke_wisp": ("smoke_puff",)}
for _n in NAMES:
    ROLES[_n] = {p: (PIC_ROLES.get(p) or OWN_ROLES[p]) for p in _USES[_n]}
    RECIPES[_n]["roles"] = ROLES[_n]
