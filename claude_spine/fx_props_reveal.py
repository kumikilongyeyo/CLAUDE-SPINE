"""Reveal moments for a rigged prop (a chest, a jar, a box, a gem), for ``fx_recipe``: the beats a slot game plays
when a prop teases, hesitates, opens, takes a hit, levels up or breaks.

They drive YOUR bones only through carrier bones inserted above them (``fx_reels._carrier``; translate and scale merge
with ``_merge_keys``, rotation with ``fx_bonus._merge_rot``), so your keys, constraints and weights stay untouched and
several recipes can share one animation. With no bone option a recipe makes bones of its own (``fx_<recipe>_prop``,
``fx_<recipe>_lid``): parent your art to them. The light is the shared piñata kit (``fx_pinata.PICS``), so every
picture is an ``art=`` role and the ``gain`` / ``thick`` options work as there.

* ``prop_peek``     the lid lifts a little in two hesitant steps, glowing eyes (or a glint) look out of the gap and
                    blink, duck back, and the lid falls shut under gravity and bounces on the rim (restitution arcs).
* ``prop_shake``    anticipation: the prop rocks on its base corners (it lifts so the low corner stays on the floor),
                    amplitude and frequency both rise, it squashes on every landing and a little deeper each time,
                    ends on a still, crouched hold, then springs back (event prop_shake_release at the end of the hold).
* ``prop_open``     wind-up (the body crouches, the lid trembles from the pressure), then the lid is thrown open
                    against gravity and caught by a spring at its open angle (exact overshoot, damped settle); light
                    beams, flash and sparkles pour out of the opening, coins arc out and bounce on the floor.
* ``prop_hit``      struck: squash along the blow (an exact directional squash through a rotate/scale/unrotate carrier
                    chain), kicked along it, spun by the torque of an off-centre hit, all damped springs; white flash
                    on the prop, impact star and sparks thrown back off the contact point.
* ``prop_upgrade``  level up: crouch while a light wipe crosses it, flash at the swap frame, pops ~10 % bigger and
                    settles on a spring, the new glow colour blooms, sparkles and rising streaks.
* ``prop_shatter``  cracks of light run from the impact point in jerks (with branches), the prop trembles harder,
                    then bursts: shards on ballistic paths with spin, a flash, and the reward glow in the middle. With a
                    prop bone its carrier scales to 0 at the burst, so the art disappears without keying your slots.

All six are one-shots measured in design seconds (``duration`` retimes them) except prop_shake, whose ``duration`` is
the build-up length (a window).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .fx_recipes import RECIPES, ROLES, Ctx, _hexn, ease_out, smooth, times_dense  # first: it imports the families
from .fx import _rgba
from .fx_pinata import PIC_ROLES, PICS, _GT, _finish, _h
from .fx_props import _descendants

FPS = 30
FAST = 60                       # key rate for springs and impacts (linear keys between samples)
SIZE = [240.0, 200.0]           # a chest-sized prop, design units (a reel cell is 144)

# ---- prop_peek (design seconds)
PEEK_D = 1.6
PEEK_STEPS = ((0.10, 0.36, 0.55), (0.50, 0.64, 1.0))   # (start, end, fraction of the angle): the lid lifts in 2 tries
PEEK_SHUT = 1.10                # the lid lets go and falls
PEEK_FALL = 0.10                # free fall time, closed under constant angular acceleration
PEEK_E = 0.42                   # restitution of the lid on the rim: each bounce is e^2 as high (2.8 deg, 0.5 deg ...)
PEEK_EYES = (0.56, 1.02)        # eyes on / ducking away (gone before the lid falls)
PEEK_BLINK = 0.82

# ---- prop_shake
SHAKE_HZ = (5.0, 12.0)          # rock frequency at the start and at the end of the build (it accelerates)
SHAKE_AMP = (0.25, 1.0)         # x `amp`: the rock grows from a quarter to full
SHAKE_SETTLE = 0.34             # the release spring after the hold
SHAKE_SPRING = (0.6, 3.4)       # its overshoot (fraction of the crouch it stretches past rest) and frequency (Hz)

# ---- prop_open
OPEN_D = 2.4
OPEN_POP = 0.30                 # end of the wind-up: the lid is thrown open (event prop_open)
OPEN_THROW = 0.11               # the throw: 0 -> angle under constant deceleration
OPEN_LID = (3.0, 0.3)           # the lid's catch spring: Hz, damping ratio (overshoot set by `overshoot`)
OPEN_BODY = (4.2, 0.3)          # the body's stretch spring after the crouch
OPEN_G = 2400.0                 # coin gravity, units/s^2 (a 200-unit chest reads like a ~1 m box)
OPEN_COIN_E = 0.38              # coin bounce restitution on the floor

# ---- prop_hit
HIT_D = 0.8
HIT_SQUASH = (7.0, 0.35)        # squash spring: Hz, damping (peaks ~35 ms after contact)
HIT_KICK = (3.5, 0.22)          # positional kick spring (swings back past rest twice)
HIT_TWIST = (4.0, 0.16)         # torque wobble spring: a rigid box rocks longest
HIT_SPARK = (6.0, 1500.0)       # spark air drag (1/s) and gravity (units/s^2)

# ---- prop_upgrade
UP_D = 1.6
UP_SWAP = 0.5                   # the flash: event prop_upgrade_swap (swap your art here)
UP_POP = (None, 3.2, 0.3)       # push-off from rest (time solved), catch spring Hz, damping (overshoot = `grow`)
UP_CROUCH = 0.05                # how far it sinks while charging

# ---- prop_shatter
SH_D = 1.8
SH_BURST = 0.62                 # event prop_shatter: the prop is gone, shards fly
SH_JERKS = 3                    # a crack runs in bursts (stress builds, releases), not at constant speed
SH_G = 1900.0                   # shard gravity
SH_DRAG = 0.8                   # shard air drag (1/s)


# ------------------------------------------------------------------ physics helpers
def _caught(hz: float, zeta: float):
    """x(t) = e^(-z w t) sin(wd t) / M: a spring caught at rest while moving, scaled so its first peak is exactly 1.
    Returns (x, x'(0)) so a caller can match the speed the thing arrives with."""
    w = 2 * math.pi * hz
    sg, wd = zeta * w, w * math.sqrt(1 - zeta * zeta)
    tp = math.atan2(wd, sg) / wd
    M = math.exp(-sg * tp) * math.sin(wd * tp)
    return (lambda t: math.exp(-sg * t) * math.sin(wd * t) / M if t > 0 else 0.0), wd / M


def _throw(a0: float, a1: float, T: float | None, over: float, hz: float, zeta: float):
    """a0 -> a1 in T under constant deceleration (thrown against gravity), caught by a spring at a1 that swings past it
    by exactly ``over`` (same units as a1 - a0); the speed is continuous at the catch. Returns (f(t), t_settled) with
    t_settled the time after which f stays within 2 % of the swing of a1."""
    x, v1 = _caught(hz, zeta)
    span = a1 - a0
    sgn = 1.0 if span >= 0 else -1.0
    v_arr = sgn * abs(over) * v1                       # arrival speed the spring needs for that overshoot
    if T is None:                                       # from rest: pushed off, accelerating all the way (a jump)
        T = 2 * span / v_arr if v_arr else 0.05
    v0 = 2 * span / T - v_arr                           # constant deceleration: span = (v0 + v_arr) T / 2
    acc = (v_arr - v0) / T

    def f(t):
        if t <= 0:
            return a0
        if t < T:
            return a0 + v0 * t + 0.5 * acc * t * t
        return a1 + sgn * abs(over) * x(t - T)
    ts = np.linspace(T, T + 4.0, 4001)
    off = np.array([abs(f(t) - a1) for t in ts])
    bad = np.nonzero(off > 0.02 * max(abs(span), 1e-9))[0]
    return f, float(ts[bad[-1] + 1] if len(bad) and bad[-1] + 1 < len(ts) else T)


def _bounce_fall(A: float, TC: float, e: float):
    """A lid let go at angle A: falls shut in TC under constant angular acceleration, then rebounds off the rim in
    parabolic arcs, each launched at e times the speed it landed with. Returns (theta(t), contact times)."""
    g = 2 * A / TC ** 2
    arcs, t, v = [], TC, e * 2 * A / TC
    while v * v / (2 * g) > 0.02:
        d = 2 * v / g
        arcs.append((t, v, d))
        t += d
        v *= e

    def th(q):
        if q <= 0:
            return A
        if q < TC:
            return A * (1 - (q / TC) ** 2)
        for t0, v_, d in arcs:
            if q < t0 + d:
                s = q - t0
                return v_ * s - 0.5 * g * s * s
        return 0.0
    return th, [TC] + [t0 + d for t0, _, d in arcs]


# ------------------------------------------------------------------ driving bones
class _Drive:
    """Where a recipe's motion goes: a carrier above the artist's bone (its keys untouched), or a bone of our own at the
    pivot (parent your art to it). Motion is given in the recipe's space (design units, degrees, y up) and converted
    to the bone's parent space, so the group's scale and a rotated or mirrored parent are handled."""

    def __init__(self, c: Ctx, opt, tag: str, pivot, parent: str | None = None, own: str = ""):
        from .fx_reels import _carrier
        self.c = c
        sk = c.sk
        gw = sk.world()[c.group]
        at = gw.to_world(float(pivot[0]), float(pivot[1]))
        if opt:
            if not sk.has_bone(str(opt)):
                raise ValueError(f"no bone {str(opt)!r} for the {tag}")
            self.bone, self.carrier = _carrier(c, str(opt), tag, at), True
        else:
            par = parent or c.group
            lx, ly = sk.world()[par].to_local(*at)
            self.bone, self.carrier = c.bone(own or tag, par, lx, ly), False
        pw = sk.world()[sk.bone(self.bone).parent]
        o = pw.to_local(*gw.to_world(0, 0))
        ex, ey = pw.to_local(*gw.to_world(1, 0)), pw.to_local(*gw.to_world(0, 1))
        self.M = ((ex[0] - o[0], ey[0] - o[0]), (ex[1] - o[1], ey[1] - o[1]))
        flip = (gw.a * gw.d - gw.b * gw.c) * (pw.a * pw.d - pw.b * pw.c)
        self.rs = 1.0 if flip >= 0 else -1.0

    def vec(self, dx: float, dy: float) -> tuple[float, float]:
        (a, b), (cc, d) = self.M
        return a * dx + b * dy, cc * dx + d * dy

    def translate(self, ts, fn) -> None:
        from .fx_reels import _merge_keys
        _merge_keys(self.c, self.bone, "translate", ts, lambda u: self.vec(*fn(u)), "add")

    def scale(self, ts, fn) -> None:
        from .fx_reels import _merge_keys
        _merge_keys(self.c, self.bone, "scale", ts, fn, "mul")

    def rotate(self, ts, fn) -> None:
        from .fx_bonus import _merge_rot
        _merge_rot(self.c, self.bone, ts, lambda u: self.rs * fn(u))


def _prop(c: Ctx, P: dict, tag: str, pivot) -> _Drive:
    return _Drive(c, P.get("prop"), tag, pivot, own="prop")


def _size(P: dict) -> tuple[float, float]:
    w, h = (float(v) for v in (P.get("size") or SIZE))
    if w <= 0 or h <= 0:
        raise ValueError("size must be [width, height] > 0")
    return w, h


def _pt(v, default) -> tuple[float, float]:
    return (float(v[0]), float(v[1])) if v is not None else (float(default[0]), float(default[1]))


def _hinge(P: dict, w: float, h: float) -> tuple[float, float]:
    return _pt(P.get("pivot"), (-w / 2, 0.2 * h))


def _pic(c: Ctx, bone: str, pic: str, width: float, height: float | None = None, blend: str = "additive",
         ox: float = 0.0, oy: float = 0.0) -> str:
    """A slot showing kit picture ``pic`` (or the user's art for that role); fx_pinata._finish applies gain / thick."""
    make = PICS.get(pic) or EXTRA[pic]
    nm = c.slot(bone, f"fx/{'pinata' if pic in PICS else 'prop'}_{pic}", width, height=height, make=make, blend=blend,
                role=pic, stretch=height is not None, ox=ox, oy=oy)
    c.__dict__.setdefault("_pic", {})[nm] = pic
    return nm


def _place(c: Ctx, P: dict, where: str, keys=("prop",)) -> bool:
    """Start a new run of slots behind (before the first) or in front of (after the last) the prop's own layers, unless
    the caller placed the recipe with behind= / front_of= or there is no prop bone. Returns whether it moved."""
    if "_user_place" not in c.__dict__:
        c._user_place = bool(c.behind or c.front_of)
    if c._user_place:
        return False
    under: set[str] = set()
    for k in keys:
        if P.get(k) and c.sk.has_bone(str(P[k])):
            under |= _descendants(c.sk, str(P[k]))
    layers = [sl.name for sl in c.sk.slots if sl.bone in under and sl.name not in c.slots]
    if not layers:
        return False
    c.last_slot = None
    c.behind, c.front_of = (layers[0], "") if where == "behind" else ("", layers[-1])
    return True


def _unwrap(vals: list[float]) -> list[float]:
    return [float(v) for v in np.degrees(np.unwrap(np.radians(vals)))]


def _shard() -> Image.Image:
    """One broken piece: an irregular quad split into a lit and a shaded facet, a bright chipped rim on the lit side.
    White / grey so the slot tints it; 2 px of clear border (alpha 0 well before the edge)."""
    S = 4 * 120
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    p = [(0.10, 0.30), (0.58, 0.06), (0.93, 0.48), (0.40, 0.95)]
    q = [(x * S, y * S) for x, y in p]
    m = ((q[0][0] + q[2][0]) / 2 + 0.05 * S, (q[0][1] + q[2][1]) / 2)
    d.polygon([q[0], q[1], q[2], m], fill=(255, 255, 255, 255))
    d.polygon([q[0], m, q[2], q[3]], fill=(176, 176, 176, 255))
    d.line([q[0], q[1], q[2]], fill=(255, 255, 255, 255), width=10)
    d.line([q[0], q[3], q[2]], fill=(120, 120, 120, 255), width=8)
    out = Image.new("RGBA", (124, 124), (0, 0, 0, 0))
    out.paste(im.resize((120, 120), Image.LANCZOS), (2, 2))
    return out


def _eye() -> Image.Image:
    """A glowing eye: a hot almond with a slit pupil and a soft halo, white (tinted by the slot); fades out before the
    picture's edge."""
    y, x = np.mgrid[0:96, 0:128].astype(float)
    xn, yn = (x - 63.5) / 64, (y - 47.5) / 48
    lim = 0.38 * np.clip(1 - (xn / 0.62) ** 2, 0, 1)      # almond: pointed at both ends
    core = np.clip((lim - np.abs(yn)) / 0.08, 0, 1)
    pupil = np.exp(-(xn / 0.07) ** 2)
    halo = np.exp(-((xn / 0.75) ** 2 + (yn / 0.6) ** 2) * 2.5) * 0.55
    a = np.clip(np.maximum(core * (1 - 0.85 * pupil), halo), 0, 1) * np.clip((1 - np.abs(xn)) / 0.15, 0, 1) * np.clip((1 - np.abs(yn)) / 0.2, 0, 1)
    return _rgba(np.ones(a.shape), a)


EXTRA = {"shard": _shard, "eye": _eye}
ROLE_TEXT = {**PIC_ROLES, "shard": "one broken piece of the prop (normal blend, tinted by shard_color); white/grey facets",
             "eye": "one glowing eye (additive, tinted by color)"}


# ====================================================================== prop_peek
def prop_peek(c: Ctx, P: dict) -> dict:
    """The lid lifts a little (two hesitant tries), something inside looks out of the gap, ducks, and the lid falls shut
    and bounces on the rim."""
    D = PEEK_D
    col = _hexn(P["color"], "FFD84A")
    w, h = _size(P)
    hx, hy = _hinge(P, w, h)
    s = 1.0 if hx <= 0 else -1.0                       # hinge left of centre: the lid swings counter-clockwise
    A = float(P["angle"])
    if A <= 0:
        raise ValueError("angle must be > 0 (how far the lid lifts, degrees)")
    look = str(P["look"])
    if look not in ("eyes", "glint"):
        raise ValueError(f"look must be eyes | glint, got {look!r}")
    lift = float(P["lift"])
    body = _prop(c, P, "peek_body", (0.0, -h / 2)) if (P.get("prop") or not P.get("lid")) else None
    lid = _Drive(c, P.get("lid"), "peek_lid", (hx, hy), parent=None if P.get("lid") or body is None else body.bone, own="lid")
    fall, contacts = _bounce_fall(A, PEEK_FALL, PEEK_E)

    def ang(t):                                         # degrees open (>= 0)
        if t >= PEEK_SHUT:
            return fall(t - PEEK_SHUT)
        v = 0.0
        for t0, t1, f in PEEK_STEPS:
            v = max(v, A * f * smooth(t, t0, t1)) if t >= t0 else v
        creak = 0.6 * math.sin(2 * math.pi * 9 * t) * smooth(t, 0.36, 0.40) * (1 - smooth(t, 0.46, 0.52))
        return v + creak                                # a tiny creak between the two tries
    ts = sorted(set(times_dense(0, D, FAST) + [PEEK_SHUT + q for q in contacts]))
    lid.rotate(ts, lambda t: s * ang(t))
    if lift:
        lid.translate(ts, lambda t: (0.0, lift * ang(t) / A))
    shut = PEEK_SHUT + contacts[0]
    if body is not None:                                # the whole prop jolts when the lid slams: a short squash
        x, _ = _caught(9.0, 0.35)
        body.scale(ts, lambda t: ((1 + 0.03 * x(t - shut)), (1 - 0.05 * x(t - shut))))

    # the gap: where (and how wide) it is at the eyes
    ex = hx + s * 0.66 * w
    gap = abs(ex - hx) * math.tan(math.radians(A))
    ey = hy + 0.42 * gap
    b_leak = c.bone("leak", x=hx, y=hy)
    s_leak = _pic(c, b_leak, "light_streak", w * 1.05, height=max(18.0, 0.5 * gap), ox=s * w * 0.55)
    b_glow = c.bone("gapglow", x=ex, y=hy + 0.25 * gap)
    s_glow = _pic(c, b_glow, "glow_soft", w * 0.9, height=w * 0.32)
    slots = [s_leak, s_glow]
    c.show(slots, PEEK_STEPS[0][0], shut)
    tl = times_dense(0, shut, FAST)
    c.bone_keys(b_leak, "rotate", tl, lambda t: s * ang(t) * 0.5)          # the light fills the wedge
    c.color_keys(s_leak, tl, lambda t: _h(c, col, 0.85 * min(1.0, ang(t) / A) ** 1.5))
    c.color_keys(s_glow, tl, lambda t: _h(c, col, 0.55 * min(1.0, ang(t) / A) ** 2 * (1 + 0.15 * math.sin(2 * math.pi * 7 * t))))
    on, off = PEEK_EYES
    te = times_dense(on - 0.02, off + 0.06, FAST)
    duck = lambda t: smooth(t, off - 0.08, off + 0.04)  # noqa: E731   it ducks down out of the light
    if look == "eyes":
        b_eyes = c.bone("eyes", x=ex, y=ey)
        eyes = []
        for i, dx in enumerate((-0.1 * w, 0.1 * w)):
            b = c.bone(f"eye{i}", b_eyes, dx, 0)
            eyes.append((b, _pic(c, b, "eye", 0.27 * w)))
        c.show([e[1] for e in eyes], on, off + 0.06)

        def gaze(t):                                    # look one way, then the other (eased glances)
            return 0.05 * w * (-smooth(t, 0.62, 0.68) + 1.6 * smooth(t, 0.88, 0.94))
        c.bone_keys(b_eyes, "translate", te, lambda t: (gaze(t), -0.55 * gap * duck(t)))
        blink = lambda t: 1 - 0.9 * math.exp(-((t - PEEK_BLINK) / 0.025) ** 2)  # noqa: E731
        for b, sl in eyes:
            c.bone_keys(b, "scale", te, lambda t: (1.0, max(0.08, blink(t) * (0.35 + 0.65 * smooth(t, on, on + 0.07)))))
            c.color_keys(sl, te, lambda t: _h(c, col, smooth(t, on, on + 0.06) * (1 - duck(t))))
        res_extra = dict(eyes=[e[1] for e in eyes])
    else:
        b_st = c.bone("glint", x=ex, y=ey)
        s_st = _pic(c, b_st, "flare_star", 0.4 * w)
        c.show([s_st], on, off + 0.06)
        c.bone_keys(b_st, "scale", te, lambda t: (0.2 + 0.9 * math.exp(-((t - 0.74) / 0.09) ** 2) * (1 - duck(t)),) * 2)
        c.bone_keys(b_st, "rotate", te, lambda t: -120.0 * (t - on))
        c.color_keys(s_st, te, lambda t: _h(c, "FFFFFF", smooth(t, on, on + 0.05) * (1 - duck(t))))
        res_extra = dict(glint=s_st)
    c.ab.event(c.T(shut), "prop_peek_shut")
    return _finish(c, P, duration=D * c.k, lid_bone=lid.bone, body_bone=body.bone if body else "", shut_at=c.T(shut),
                   angle=A, **res_extra)


# ====================================================================== prop_shake
def _rattle(D: float, hz: tuple[float, float]):
    """Phase of a rock whose frequency rises f0 -> f1 (ease in), rescaled so it ends on a landing (phase = k pi):
    the rattle stops flat, not mid-tilt. Returns (phase(t), landing times)."""
    ts = np.linspace(0, D, 4001)
    f = hz[0] + (hz[1] - hz[0]) * (ts / D) ** 1.5
    ph = np.concatenate([[0.0], np.cumsum((f[1:] + f[:-1]) / 2 * np.diff(ts))]) * 2 * math.pi
    k = max(1, round(ph[-1] / math.pi))
    ph *= k * math.pi / ph[-1]
    lands = [float(np.interp(j * math.pi, ph, ts)) for j in range(1, k + 1)]
    return (lambda t: float(np.interp(min(max(t, 0.0), D), ts, ph))), lands


def prop_shake(c: Ctx, P: dict) -> dict:
    """Anticipation: the prop rocks on its base corners faster and harder, squashing on each landing, holds crouched,
    and springs back on release."""
    D, hold = float(P["duration"]), float(P["hold"])
    if D <= 0.2 or hold < 0:
        raise ValueError("duration must be > 0.2 s and hold >= 0")
    col = _hexn(P["color"], "FFC94A")
    w, h = _size(P)
    amp, sq = float(P["amp"]), float(P["squash"])
    base = _pt(P.get("pivot"), (0.0, -h / 2))
    dr = _prop(c, P, "shake", base)
    phase, lands = _rattle(D, (float(P["hz"][0]), float(P["hz"][1])) if P.get("hz") else SHAKE_HZ)
    E = D + hold + SHAKE_SETTLE
    a = lambda t: amp * (SHAKE_AMP[0] + (SHAKE_AMP[1] - SHAKE_AMP[0]) * (min(t, D) / D) ** 2)  # noqa: E731
    rock = lambda t: a(t) * math.sin(phase(t)) if t < D else 0.0  # noqa: E731
    crouch = lambda t: 0.6 * sq * (min(t, D) / D) ** 2  # noqa: E731   tension: it sinks as the rattle builds
    from .fx_bonus import _step
    back, _ = _step(SHAKE_SPRING[0], SHAKE_SPRING[1])

    def sy(t):
        if t >= D + hold:                               # release: from the crouch back up, past rest, settle
            r = t - D - hold
            return 1 - crouch(D) * back(r) * (1 - smooth(r, SHAKE_SETTLE * 0.7, SHAKE_SETTLE))
        land = (1 - abs(math.sin(phase(t)))) ** 6 if t < D else 0.0   # each landing slams it flat for an instant
        return 1 - crouch(t) - sq * (0.3 + 0.7 * min(t, D) / D) * land
    ts = sorted(set(times_dense(0, E, FAST) + lands))
    dr.rotate(ts, rock)
    # rotating about the base centre would sink one corner into the floor: lift by (w/2)|sin| so it rocks ON a corner
    dr.translate(ts, lambda t: (0.006 * w * a(t) / max(amp, 1e-9) * math.sin(1.7 * phase(t)) if t < D else 0.0,
                                0.5 * w * abs(math.sin(math.radians(rock(t))))))
    dr.scale(ts, lambda t: (sy(t) ** -0.5, sy(t)))

    # dust kicked out at the corner that lands, on the last `dust` landings (normal blend, drawn first)
    rng = np.random.default_rng(c.seed + 301)
    _place(c, P, "behind")                              # glow and dust go behind the prop's art
    n = max(0, int(P["dust"]))
    puffs = []
    late = [t for t in lands if t >= 0.45 * D]          # the hard landings of the second half, back from the last one,
    step = max(1, len(late) // max(n, 1))               # an ODD stride apart so the corners alternate left / right
    step -= 0 if step % 2 else 1
    pick = sorted(late[::-1][::max(1, step)][:n]) if n else []
    for j, tl in enumerate(pick):
        # the corner that comes down is the one that was up: rock > 0 (counter-clockwise) lifts the right corner
        side = 1.0 if rock(tl - 0.25 / SHAKE_HZ[1]) > 0 else -1.0
        b = c.bone(f"dust{j}", x=base[0] + side * 0.45 * w, y=base[1])
        puffs.append((b, _pic(c, b, "smoke_puff", 0.55 * w * float(rng.uniform(0.85, 1.15)), blend="normal"), tl, side,
                      float(rng.uniform(0.9, 1.3))))
    b_gl = c.bone("glow", x=0.0, y=0.0)
    s_gl = _pic(c, b_gl, "glow_soft", 2.4 * max(w, h))     # behind the art: big enough to rim it
    c.show([s_gl], 0, D + hold + 0.2)
    tg = times_dense(0, D + hold + 0.2, FAST)
    beat = lambda t: (1 - abs(math.sin(phase(t)))) ** 4 if t < D else 0.0  # noqa: E731
    c.color_keys(s_gl, tg, lambda t: _h(c, col, (0.8 * (min(t, D) / D) ** 2 * (0.75 + 0.25 * beat(t)) + 0.15 * smooth(t, D, D + 0.04))
                                        * (1 - smooth(t, D + hold, D + hold + 0.2))))
    c.bone_keys(b_gl, "scale", tg, lambda t: (0.8 + 0.25 * (min(t, D) / D) ** 2,) * 2)
    for b, sl, t0, side, k in puffs:
        L = min(0.55, E - t0)
        tp = times_dense(t0, t0 + L, FPS)
        q = lambda t, t0=t0: max(0.0, t - t0)  # noqa: E731
        c.show([sl], t0, t0 + L)
        c.bone_keys(b, "translate", tp, lambda t, q=q, side=side, k=k: (side * 0.4 * w * k * (1 - math.exp(-7 * q(t))),
                                                                         0.12 * h * (1 - math.exp(-3 * q(t)))))
        c.bone_keys(b, "scale", tp, lambda t, q=q: ((0.35 + 0.85 * ease_out(q(t) / L, 2.2)), 0.6 * (0.35 + 0.85 * ease_out(q(t) / L, 2.2))))
        c.color_keys(sl, tp, lambda t, q=q: _h(c, "E6D6C2", 0.8 * smooth(q(t), 0, 0.04) * (1 - smooth(q(t), 0.15, L))))
    c.ab.event(c.T(D + hold), "prop_shake_release")
    return _finish(c, P, duration=E, prop_bone=dr.bone, landings=[c.T(t) for t in lands],
                   release_at=c.T(D + hold), dust=len(puffs))


# ====================================================================== prop_open
def prop_open(c: Ctx, P: dict) -> dict:
    """Wind-up, the lid thrown open and caught by a spring, light pouring out, coins spilling."""
    D = OPEN_D
    col = _hexn(P["color"], "FFD45A")
    w, h = _size(P)
    hx, hy = _hinge(P, w, h)
    s = 1.0 if hx <= 0 else -1.0
    A, os_ = float(P["angle"]), float(P["overshoot"])
    if A <= 0 or not 0 <= os_ < 0.6:
        raise ValueError("angle must be > 0 and overshoot in [0, 0.6)")
    base = _pt(P.get("base"), (0.0, -h / 2))
    mouth = _pt(P.get("opening"), (0.0, hy))
    lid_opt, prop_opt = P.get("lid"), P.get("prop")
    body = _prop(c, P, "open_body", base)
    if lid_opt and prop_opt and str(lid_opt) not in _descendants(c.sk, str(prop_opt)):
        lid_sq = _Drive(c, lid_opt, "open_lidsq", base)            # lid not under the body: give it the body's squash
    else:
        lid_sq = None
    lid = _Drive(c, lid_opt, "open_lid", (hx, hy), parent=None if lid_opt else body.bone, own="lid")

    P0, wind = OPEN_POP, float(P["windup"])
    th, settle = _throw(0.0, A, OPEN_THROW, os_ * A, *OPEN_LID)
    pop, _ = _throw(1 - wind, 1.0, 0.06, 0.6 * wind, *OPEN_BODY)

    def ang(t):
        if t < P0:                                      # pressure inside: the lid trembles up off the rim
            return 2.0 * smooth(t, 0.05, P0) ** 2 * abs(math.sin(2 * math.pi * 16 * t)) * (1 - smooth(t, P0 - 0.04, P0))
        return th(t - P0)

    def sy(t):
        if t < P0:
            return 1 - wind * smooth(t, 0.0, P0 * 0.9)  # crouch (anticipation), eased
        return pop(t - P0)
    ts = sorted(set(times_dense(0, D, FAST) + [P0]))
    lid.rotate(ts, lambda t: s * ang(t))
    sc = lambda t: (sy(t) ** -0.5, sy(t))  # noqa: E731   area-preserving squash about the base
    body.scale(ts, sc)
    if lid_sq is not None:
        lid_sq.scale(ts, sc)

    # ---- the light (coins first: one normal run, then one additive run)
    rng = np.random.default_rng(c.seed + 302)
    floor = base[1]
    coins = []
    for i in range(max(0, int(P["coins"]))):
        b = c.bone(f"coin{i}", x=mouth[0], y=mouth[1])
        t0 = P0 + 0.03 + 0.045 * i + float(rng.uniform(0, 0.03))
        ang_ = math.radians(90 + float(rng.uniform(6, 22)) * (1 if i % 2 else -1))
        v = float(rng.uniform(0.85, 1.1)) * math.sqrt(2 * OPEN_G * 1.0 * h)        # apex ~1 h above the opening
        coins.append(dict(b=b, s=_pic(c, b, "coin", 0.24 * w * float(rng.uniform(0.85, 1.1)), blend="normal"), t0=t0,
                          vx=v * math.cos(ang_), vy=v * math.sin(ang_), spin=float(rng.uniform(5, 9)),
                          fy=floor - mouth[1] - float(rng.uniform(0.0, 0.18)) * h, dx=float(rng.uniform(-0.15, 0.15)) * w))
    b_gl = c.bone("glow", x=mouth[0], y=mouth[1])
    s_gl = _pic(c, b_gl, "glow_soft", 2.0 * w)
    beams = []
    nb = max(1, int(P["beams"]))
    for i in range(nb):
        f = (i / (nb - 1) - 0.5) if nb > 1 else 0.0
        rot = -f * 64 + float(rng.uniform(-5, 5))
        b = c.bone(f"beam{i}", x=mouth[0] + f * 0.55 * w, y=mouth[1], rot=rot)
        L = (2.4 - 1.1 * abs(f)) * h
        sl = _pic(c, b, "shine_band", 0.3 * w, height=L, oy=L / 2)                  # grows from its foot
        si = _pic(c, b, "shine_band", 0.15 * w, height=0.5 * L, oy=0.25 * L)       # a hotter core: brighter at the foot
        beams.append((b, sl, si, rot, float(rng.uniform(0, 6.28)), float(rng.uniform(0.9, 1.4))))
    b_fl = c.bone("flash", x=mouth[0], y=mouth[1])
    s_fl = _pic(c, b_fl, "flash_burst", 1.4 * w)
    b_co = c.bone("core", x=mouth[0], y=mouth[1], sy=0.6)
    s_co = _pic(c, b_co, "glow_core", 1.5 * w)
    motes = []
    for i in range(int(P["count"])):
        b = c.bone(f"mote{i}", x=mouth[0] + float(rng.uniform(-0.35, 0.35)) * w, y=mouth[1])
        motes.append((b, _pic(c, b, "flare_star", 0.36 * w * float(rng.uniform(0.7, 1.2))), P0 + 0.05 + float(rng.uniform(0, 0.9)),
                      float(rng.uniform(1.2, 2.0)) * h, float(rng.uniform(0, 6.28)), float(rng.uniform(0.6, 0.95))))

    q = lambda t: max(0.0, t - P0)  # noqa: E731
    out = lambda t: 1 - smooth(t, 1.5, D)  # noqa: E731
    tl = times_dense(P0 - 0.02, D, FPS)
    c.show([s_gl, s_co] + [x for bm in beams for x in bm[1:3]], P0 - 0.02, D)
    c.bone_keys(b_gl, "scale", tl, lambda t: (0.5 + 0.6 * ease_out(q(t) / 0.3, 2.5), 0.55 * (0.5 + 0.6 * ease_out(q(t) / 0.3, 2.5))))  # a wide pool of light
    c.color_keys(s_gl, tl, lambda t: _h(c, col, (0.95 - 0.3 * smooth(q(t), 0.1, 0.6)) * smooth(t, P0 - 0.02, P0 + 0.03) * out(t)))
    c.color_keys(s_co, tl, lambda t: _h(c, "FFFFFF", (0.25 + 0.75 * math.exp(-q(t) / 0.18)) * smooth(t, P0 - 0.02, P0 + 0.02) * out(t)))
    for b, sl, si, rot, ph, fq in beams:                # beams shoot up (ease out), sway and breathe
        c.bone_keys(b, "scale", tl, lambda t, ph=ph, fq=fq: ((0.7 + 0.3 * smooth(q(t), 0, 0.2)) * (1 + 0.08 * math.sin(2 * math.pi * fq * t + ph)),
                                                              0.05 + 0.95 * ease_out(q(t) / 0.35, 3)))
        c.bone_keys(b, "rotate", tl, lambda t, ph=ph: 3.0 * math.sin(2 * math.pi * 0.7 * t + ph) * smooth(q(t), 0, 0.4))
        fl = lambda t, ph=ph, fq=fq: 0.85 + 0.15 * math.sin(2 * math.pi * 2.3 * fq * t + ph)  # noqa: E731
        c.color_keys(sl, tl, lambda t, fl=fl: _h(c, col, 0.42 * fl(t) * smooth(t, P0, P0 + 0.08) * out(t)))
        c.color_keys(si, tl, lambda t, fl=fl: _h(c, "FFF6DA", 0.5 * fl(t) * smooth(t, P0, P0 + 0.08) * out(t)))
    tf = times_dense(P0 - 0.02, P0 + 0.5, FAST)
    c.show([s_fl], P0 - 0.02, P0 + 0.5)
    c.bone_keys(b_fl, "scale", tf, lambda t: (0.2 + 1.0 * ease_out(q(t) / 0.16, 2.5),) * 2)
    c.bone_keys(b_fl, "rotate", tf, lambda t: 40.0 * q(t))
    c.color_keys(s_fl, tf, lambda t: _h(c, "FFF8E4", smooth(t, P0 - 0.02, P0 + 0.01) * math.exp(-q(t) / 0.1)))
    for b, sl, t0, rise, ph, a0 in motes:               # embers / sparkles ride the warm air up, swaying, twinkling
        L = 1.0
        tm = times_dense(t0, min(D, t0 + L), FPS)
        c.show([sl], t0, min(D, t0 + L))
        c.bone_keys(b, "translate", tm, lambda t, t0=t0, rise=rise, ph=ph: (0.06 * w * math.sin(2 * math.pi * 1.3 * (t - t0) + ph),
                                                                              rise * ease_out((t - t0) / L, 1.6)))
        c.bone_keys(b, "scale", tm, lambda t, t0=t0, ph=ph: (0.5 + 0.5 * abs(math.sin(2 * math.pi * 2.2 * (t - t0) + ph)),) * 2)
        c.bone_keys(b, "rotate", tm, lambda t, t0=t0: 90.0 * (t - t0))
        c.color_keys(sl, tm, lambda t, t0=t0, a0=a0: _h(c, "FFFFFF", a0 * smooth(t, t0, t0 + 0.08) * (1 - smooth(t, t0 + 0.5, t0 + L))))
    for cn in coins:                                    # ballistic, flipping (scaleX = cos), one bounce on the floor
        t0, vx, vy, fy = cn["t0"], cn["vx"], cn["vy"], cn["fy"]
        disc = vy * vy + 2 * OPEN_G * (-fy)             # fy < 0: the floor is below the opening
        t_land = (vy + math.sqrt(max(disc, 0.0))) / OPEN_G
        vy2 = OPEN_COIN_E * (OPEN_G * t_land - vy)
        t_end = t_land + 2 * vy2 / OPEN_G
        x_land = vx * t_land

        def pos(t, t0=t0, vx=vx, vy=vy, fy=fy, t_land=t_land, vy2=vy2, x_land=x_land, cn=cn):
            r = max(0.0, t - t0)
            if r < t_land:
                return vx * r + cn["dx"] * min(1.0, r / 0.15), vy * r - 0.5 * OPEN_G * r * r
            r -= t_land
            return x_land + cn["dx"] + 0.4 * vx * r, fy + max(0.0, vy2 * r - 0.5 * OPEN_G * r * r)
        T1 = min(D, t0 + t_end + 0.25)
        tc = times_dense(t0, T1, FAST)
        c.show([cn["s"]], t0, T1)
        c.bone_keys(cn["b"], "translate", tc, pos)
        flip = lambda t, t0=t0, sp=cn["spin"], tl_=t_land: 2 * math.pi * sp * (  # noqa: E731   spin, slowed by the floor
            t - t0 if t - t0 < tl_ else tl_ + (1 - math.exp(-6 * (t - t0 - tl_))) / 6)
        c.bone_keys(cn["b"], "scale", tc, lambda t, flip=flip: (math.cos(flip(t)), 1.0))
        c.color_keys(cn["s"], tc, lambda t, t0=t0, te=t_end: _h(c, "FFFFFF", smooth(t, t0, t0 + 0.03) * (1 - smooth(t, t0 + te, t0 + te + 0.25))))
    c.ab.event(c.T(P0), "prop_open")
    c.ab.event(c.T(P0 + settle), "prop_open_settled")
    return _finish(c, P, duration=D * c.k, lid_bone=lid.bone, body_bone=body.bone, open_at=c.T(P0),
                   settled_at=c.T(P0 + settle), angle=A, coins=len(coins))


# ====================================================================== prop_hit
def prop_hit(c: Ctx, P: dict) -> dict:
    """Struck along `direction`: squash along the blow, a kick, a torque wobble, all damped springs; flash, star, sparks."""
    D = HIT_D
    col = _hexn(P["color"], "FFB14A")
    w, h = _size(P)
    th = math.radians(float(P["direction"]))
    dx, dy = math.cos(th), math.sin(th)
    if P.get("at") is not None:
        at = _pt(P["at"], (0, 0))
    else:                                               # the point on the box the blow comes in through
        k = min(w / 2 / max(abs(dx), 1e-9), h / 2 / max(abs(dy), 1e-9))
        off = 0.2 * min(w, h)                           # a little off-centre (to the blow's left): it spins, too
        at = (-dx * k * 0.92 - dy * off, -dy * k * 0.92 + dx * off)
    piv = _pt(P.get("pivot"), (0.0, 0.0))
    SQ, KICK, TW = float(P["squash"]), float(P["kick"]), float(P["wobble"])
    torque = max(-1.0, min(1.0, ((at[0] - piv[0]) * dy - (at[1] - piv[1]) * dx) / (0.5 * max(w, h))))

    # carriers, outer -> inner: kick (translate + rotate), then a rotate(+a) / scale / rotate(-a) chain that squashes
    # along the blow exactly, whatever its angle (Spine's world transform composes the full 2x2 matrix)
    kick = _Drive(c, P.get("prop"), "hit_kick", piv, own="kick")
    sk = c.sk
    if P.get("prop"):
        d1 = _Drive(c, P["prop"], "hit_dir", piv)
        sq = _Drive(c, P["prop"], "hit_squash", piv)
        d2 = _Drive(c, P["prop"], "hit_undir", piv)
    else:
        d1 = _Drive(c, None, "hit_dir", piv, parent=kick.bone, own="dir")
        sq = _Drive(c, None, "hit_squash", piv, parent=d1.bone, own="squash")
        d2 = _Drive(c, None, "hit_undir", piv, parent=sq.bone, own="art")
    gw = sk.world()[c.group]
    wv = (gw.a * dx + gw.b * dy, gw.c * dx + gw.d * dy)
    par = sk.world()[sk.bone(d1.bone).parent]
    a_local = math.degrees(math.atan2(wv[1], wv[0])) - par.rotation
    sk.bone(d1.bone).rotation = round(a_local, 3)
    sk.bone(d2.bone).rotation = round(-a_local, 3)

    xs, _ = _caught(*HIT_SQUASH)
    xk, _ = _caught(*HIT_KICK)
    xt, _ = _caught(*HIT_TWIST)
    end = lambda t: 1 - smooth(t, 0.7 * D, D)  # noqa: E731   lands exactly on rest
    ts = times_dense(0, D, FAST)
    sq.scale(ts, lambda t: (1 - SQ * xs(t) * end(t), 1 + 0.6 * SQ * xs(t) * end(t)))       # along / across the blow
    kick.translate(ts, lambda t: (KICK * dx * xk(t) * end(t), KICK * dy * xk(t) * end(t)))
    kick.rotate(ts, lambda t: TW * torque * xt(t) * end(t))

    # light: flash over the prop, impact star + ring + sparks at the contact point
    rng = np.random.default_rng(c.seed + 303)
    b_wf = c.bone("whiteflash")
    s_wf = _pic(c, b_wf, "glow_soft", 1.35 * max(w, h))
    s_cf = _pic(c, b_wf, "glow_soft", 1.6 * max(w, h))
    b_im = c.bone("impact", x=at[0], y=at[1])
    b_fb, b_st, b_ri = (c.bone(n, b_im) for n in ("burst", "star", "ring"))
    s_fb = _pic(c, b_fb, "flash_burst", 0.85 * h)
    s_st = _pic(c, b_st, "flare_star", 1.0 * h)
    s_ri = _pic(c, b_ri, "ring", 0.7 * h)
    sparks = []
    back = math.atan2(-dy, -dx)                          # sparks fly back off the contact, toward the hitter
    for i in range(int(P["count"])):
        a = back + float(rng.uniform(-1.3, 1.3))
        b = c.bone(f"sp{i}", b_im)
        sparks.append((b, _pic(c, b, "spark", 0.55 * h * float(rng.uniform(0.7, 1.15))), a, float(rng.uniform(700, 1250)),
                       float(rng.uniform(0, 0.03))))
    tq = times_dense(0, 0.5, FAST)
    c.show([s_wf, s_cf, s_fb, s_st, s_ri], 0, 0.5)
    c.color_keys(s_wf, tq, lambda t: _h(c, "FFFFFF", 0.95 * math.exp(-t / 0.07)))
    c.color_keys(s_cf, tq, lambda t: _h(c, col, 0.6 * math.exp(-t / 0.16)))
    c.bone_keys(b_wf, "translate", tq, lambda t: (KICK * dx * xk(t), KICK * dy * xk(t)))   # rides the kick
    c.bone_keys(b_fb, "scale", tq, lambda t: (0.3 + 0.9 * ease_out(t / 0.12, 2.5),) * 2)
    c.bone_keys(b_fb, "rotate", tq, lambda t: 70.0 * t)
    c.color_keys(s_fb, tq, lambda t: _h(c, "FFF6E0", math.exp(-t / 0.08)))
    c.bone_keys(b_st, "scale", tq, lambda t: ((0.3 + 0.9 * ease_out(t / 0.06, 2)) * math.exp(-t / 0.25),) * 2)
    c.bone_keys(b_st, "rotate", tq, lambda t: 20.0 + 90.0 * t)
    c.color_keys(s_st, tq, lambda t: _h(c, "FFFFFF", math.exp(-t / 0.14)))
    c.bone_keys(b_ri, "scale", tq, lambda t: (0.3 + 1.5 * ease_out(t / 0.3, 2.4),) * 2)
    c.color_keys(s_ri, tq, lambda t: _h(c, col, 0.9 * (1 - smooth(t, 0.04, 0.3))))
    kd, g = HIT_SPARK
    for b, sl, a, sp, d0 in sparks:
        L = 0.42
        tt = times_dense(d0, d0 + L, FAST)

        def kin(t, a=a, sp=sp, d0=d0):
            q = max(0.0, t - d0)
            e = (1 - math.exp(-kd * q)) / kd
            vx, vy = sp * math.cos(a) * math.exp(-kd * q), sp * math.sin(a) * math.exp(-kd * q) - g * q
            return sp * math.cos(a) * e, sp * math.sin(a) * e - 0.5 * g * q * q, vx, vy
        c.show([sl], d0, d0 + L)
        c.bone_keys(b, "translate", tt, lambda t, kin=kin: kin(t)[:2])
        rots = _unwrap([math.degrees(math.atan2(kin(t)[3], kin(t)[2])) for t in tt])
        c.bone_keys(b, "rotate", tt, lambda t, rots=rots, tt=tt: float(np.interp(t, tt, rots)))
        c.bone_keys(b, "scale", tt, lambda t, kin=kin, sp=sp: (0.35 + 0.9 * min(1.0, math.hypot(*kin(t)[2:]) / sp), 1.0))
        c.color_keys(sl, tt, lambda t, d0=d0: _h(c, "FFD890", 1 - smooth(t, d0 + 0.12, d0 + L)))
    c.ab.event(c.T(0.0), "prop_hit")
    return _finish(c, P, duration=D * c.k, prop_bone=d2.bone if not P.get("prop") else str(P["prop"]),
                   carriers=[kick.bone, d1.bone, sq.bone, d2.bone], at=list(at), torque=round(torque, 3))


# ====================================================================== prop_upgrade
def prop_upgrade(c: Ctx, P: dict) -> dict:
    """Level-up: crouch under a light wipe, flash at the swap frame, pop bigger and settle, the new glow blooms."""
    D, SW = UP_D, UP_SWAP
    col = _hexn(P["color"], "FFD24A")
    col2 = _hexn(P.get("color2"), "7DF4FF")
    w, h = _size(P)
    grow = float(P["grow"])
    if not 0 <= grow < 0.6:
        raise ValueError("grow must be in [0, 0.6)")
    dr = _prop(c, P, "upgrade", _pt(P.get("pivot"), (0.0, -h / 2)))
    T, hz, z = UP_POP
    pop, settle = _throw(1 - UP_CROUCH, 1.0, T, grow, hz, z)

    def scl(t):
        if t < SW:                                      # charging: sinks a little, slightly faster at the end (ease in)
            s = 1 - UP_CROUCH * smooth(t, 0.05, SW) ** 1.5
            return (s ** -0.5, s)
        s = pop(t - SW)
        return (s, s)
    ts = sorted(set(times_dense(0, D, FAST) + [SW]))
    dr.scale(ts, scl)

    rng = np.random.default_rng(c.seed + 304)
    _place(c, P, "behind")                              # the glows and rays behind the art, the light over it
    b_g1 = c.bone("glow_old")
    s_g1 = _pic(c, b_g1, "glow_soft", 1.6 * max(w, h))
    b_g2 = c.bone("glow_new")
    s_g2 = _pic(c, b_g2, "glow_soft", 1.9 * max(w, h))
    b_ra = c.bone("rays")
    s_ra = _pic(c, b_ra, "rays", 2.0 * max(w, h))
    _place(c, P, "front")
    b_wp = c.bone("wipe", rot=-22.0)
    s_wp = _pic(c, b_wp, "shine_band", 0.36 * w, height=1.15 * h)
    s_wp2 = _pic(c, b_wp, "shine_band", 0.1 * w, height=1.1 * h, ox=-0.18 * w)
    b_fl = c.bone("flash")
    s_fl = _pic(c, b_fl, "glow_soft", 1.8 * max(w, h))
    s_fb = _pic(c, b_fl, "flash_burst", 1.3 * max(w, h))
    b_ri = c.bone("ring")
    s_ri = _pic(c, b_ri, "ring", 1.2 * max(w, h))
    streaks = []
    for i in range(4):
        b = c.bone(f"up{i}", x=(i / 3 - 0.5) * 0.8 * w + float(rng.uniform(-0.05, 0.05)) * w, y=-0.3 * h, rot=90.0)
        streaks.append((b, _pic(c, b, "light_streak", 0.7 * h, height=0.07 * w), SW + 0.04 + 0.06 * i + float(rng.uniform(0, 0.04))))
    stars = []
    for i in range(int(P["count"])):
        a = 2 * math.pi * i / max(1, int(P["count"])) + float(rng.uniform(-0.3, 0.3))
        rr = float(rng.uniform(0.45, 0.7))
        b = c.bone(f"st{i}", x=math.cos(a) * rr * w, y=math.sin(a) * rr * h)
        stars.append((b, _pic(c, b, "flare_star", 0.3 * w * float(rng.uniform(0.7, 1.2))), SW + 0.05 + float(rng.uniform(0, 0.55))))

    q = lambda t: max(0.0, t - SW)  # noqa: E731
    tg = times_dense(0, D, FPS)
    c.show([s_g1], 0, SW + 0.15)
    c.color_keys(s_g1, times_dense(0, SW + 0.15, FAST), lambda t: _h(c, col, 0.6 * smooth(t, 0.0, SW) ** 1.5 * (1 - smooth(t, SW, SW + 0.15))))
    c.bone_keys(b_g1, "scale", times_dense(0, SW + 0.15, FAST), lambda t: (0.75 + 0.2 * smooth(t, 0, SW),) * 2)
    c.show([s_wp, s_wp2], 0.06, SW)
    tw = times_dense(0.06, SW, FAST)
    wipe = lambda t: smooth(t, 0.06, SW - 0.04)  # noqa: E731   sweeps left -> right, eased in and out
    c.bone_keys(b_wp, "translate", tw, lambda t: ((-0.6 + 1.2 * wipe(t)) * w, 0.0))
    for sl, a in ((s_wp, 0.75), (s_wp2, 0.95)):                 # bright only while it is over the prop
        c.color_keys(sl, tw, lambda t, a=a: _h(c, "FFFFFF", a * math.sin(math.pi * wipe(t)) ** 1.5))
    c.show([s_g2, s_ra], SW - 0.02, D)
    c.bone_keys(b_g2, "scale", tg, lambda t: (0.55 + 0.55 * ease_out(q(t) / 0.35, 2.5),) * 2)
    c.color_keys(s_g2, tg, lambda t: _h(c, col2, 0.9 * smooth(t, SW - 0.02, SW + 0.06) * (1 - 0.35 * smooth(q(t), 0.2, 0.6)) * (1 - smooth(t, D - 0.45, D))))
    c.bone_keys(b_ra, "scale", tg, lambda t: (0.4 + 0.7 * ease_out(q(t) / 0.45, 2.5),) * 2)
    c.bone_keys(b_ra, "rotate", tg, lambda t: -25.0 * q(t))
    c.color_keys(s_ra, tg, lambda t: _h(c, col2, 0.55 * smooth(t, SW - 0.02, SW + 0.05) * (1 - smooth(t, SW + 0.4, D))))
    tf = times_dense(SW - 0.03, SW + 0.5, FAST)
    c.show([s_fl, s_fb, s_ri], SW - 0.03, SW + 0.5)
    c.color_keys(s_fl, tf, lambda t: _h(c, "FFFFFF", smooth(t, SW - 0.03, SW) * math.exp(-q(t) / 0.09)))
    c.bone_keys(b_fl, "scale", tf, lambda t: (0.6 + 0.5 * ease_out(q(t) / 0.12),) * 2)
    c.color_keys(s_fb, tf, lambda t: _h(c, "FFFFFF", 0.8 * smooth(t, SW - 0.03, SW) * math.exp(-q(t) / 0.07)))
    c.bone_keys(b_ri, "scale", tf, lambda t: (0.4 + 1.1 * ease_out(q(t) / 0.4, 2.4),) * 2)
    c.color_keys(s_ri, tf, lambda t: _h(c, col2, 0.95 * smooth(t, SW - 0.01, SW + 0.02) * (1 - smooth(q(t), 0.05, 0.45))))
    for b, sl, t0 in streaks:                           # rising light: level UP
        L = 0.55
        tt = times_dense(t0, t0 + L, FPS)
        c.show([sl], t0, t0 + L)
        c.bone_keys(b, "translate", tt, lambda t, t0=t0: (0.0, 1.0 * h * ease_out((t - t0) / L, 2.0)))
        c.color_keys(sl, tt, lambda t, t0=t0: _h(c, col2, 0.9 * smooth(t, t0, t0 + 0.06) * (1 - smooth(t, t0 + 0.25, t0 + L))))
    for b, sl, t0 in stars:
        L = 0.4
        tt = times_dense(t0, min(D, t0 + L), FPS)
        c.show([sl], t0, min(D, t0 + L))
        c.bone_keys(b, "scale", tt, lambda t, t0=t0: (math.sin(math.pi * min(1.0, (t - t0) / L)) ** 0.8,) * 2)
        c.bone_keys(b, "rotate", tt, lambda t, t0=t0: 120.0 * (t - t0))
        c.color_keys(sl, tt, lambda t: _h(c, "FFFFFF", 1.0))
    c.ab.event(c.T(SW), "prop_upgrade_swap")
    return _finish(c, P, duration=D * c.k, prop_bone=dr.bone, swap_at=c.T(SW), settled_at=c.T(SW + settle))


# ====================================================================== prop_shatter
def _to_edge(p, a, w, h) -> float:
    """Distance from p along angle a to the edge of the w x h box centred on the origin."""
    dx, dy = math.cos(a), math.sin(a)
    ts = []
    for d, lo, hi, x in ((dx, -w / 2, w / 2, p[0]), (dy, -h / 2, h / 2, p[1])):
        if abs(d) > 1e-9:
            ts.append(max((hi - x) / d, (lo - x) / d))
    return max(1.0, min(ts))


def prop_shatter(c: Ctx, P: dict) -> dict:
    """Cracks of light run from the impact in jerks, the prop trembles, bursts into shards, a flash, the reward glow."""
    D, SB = SH_D, SH_BURST
    col = _hexn(P["color"], "FFE08A")
    col2 = _hexn(P.get("color2"), "FFC93C")
    shc = _hexn(P.get("shard_color"), "C9A46A")
    w, h = _size(P)
    at = _pt(P.get("at"), (0.0, 0.1 * h))
    dr = _prop(c, P, "shatter", (0.0, 0.0))
    rng = np.random.default_rng(c.seed + 305)

    # the prop trembles harder as the cracks spread (a stressed body buzzing), then vanishes at the burst
    shake = lambda t: 0.012 * w * smooth(t, 0.0, SB) ** 1.5  # noqa: E731
    ts = sorted(set(times_dense(0, SB, FAST) + [SB - 0.001, SB, D]))
    dr.translate(ts, lambda t: (shake(t) * math.sin(2 * math.pi * 23 * t), 0.6 * shake(t) * math.sin(2 * math.pi * 31 * t + 1)) if t < SB else (0.0, 0.0))
    dr.rotate(ts, lambda t: 1.6 * smooth(t, 0, SB) ** 2 * math.sin(2 * math.pi * 17 * t) if t < SB else 0.0)
    if P["hide"]:
        dr.scale(ts, lambda t: (1.0, 1.0) if t < SB else (0.0, 0.0))

    # shards first (one normal run), then the light
    shards = []
    for i in range(max(0, int(P["shards"]))):
        sx0, sy0 = float(rng.uniform(-0.38, 0.38)) * w, float(rng.uniform(-0.38, 0.38)) * h
        b = c.bone(f"shard{i}", x=sx0, y=sy0, rot=float(rng.uniform(0, 360)), sx=-1.0 if i % 2 else 1.0)
        rel = (sx0 - at[0], sy0 - at[1])
        dist = math.hypot(*rel) or 1.0
        sp = float(rng.uniform(600, 1000)) * (0.6 + 0.4 * min(1.0, 0.5 * w / dist))   # nearer the impact: faster
        tone = float(rng.uniform(0.8, 1.0))
        tint = "".join(f"{round(int(shc[k:k + 2], 16) * tone):02X}" for k in (0, 2, 4))
        shards.append(dict(b=b, s=_pic(c, b, "shard", 0.42 * min(w, h) * float(rng.uniform(0.7, 1.25)), blend="normal"),
                           vx=sp * rel[0] / dist, vy=sp * rel[1] / dist + float(rng.uniform(250, 520)),
                           spin=float(rng.uniform(380, 900)) * (1 if rng.uniform() < 0.5 else -1), tint=tint,
                           life=float(rng.uniform(0.75, 1.1))))
    b_in = c.bone("inner", x=at[0], y=at[1])
    s_in = _pic(c, b_in, "glow_soft", 0.9 * max(w, h))
    cracks = []
    n = max(1, int(P["count"]))
    a0 = float(rng.uniform(0, 2 * math.pi))
    order = rng.permutation(n)
    for i in range(n):
        a = a0 + 2 * math.pi * i / n + float(rng.uniform(-0.25, 0.25))
        L = _to_edge(at, a, w, h) * float(rng.uniform(0.75, 0.95))
        t0 = 0.02 + 0.035 * float(order[i])            # the cracks start one after another, in a random order
        segs = [(at, a, L, t0)]
        if i % 2 == 0:                                   # a branch forks off past the middle, later
            f = float(rng.uniform(0.45, 0.6))
            bp = (at[0] + math.cos(a) * L * f, at[1] + math.sin(a) * L * f)
            ab = a + math.radians(float(rng.uniform(28, 42))) * (1 if rng.uniform() < 0.5 else -1)
            segs.append((bp, ab, min(0.45 * L, _to_edge(bp, ab, w, h) * 0.85), t0 + 0.18))
        for (p, aa, LL, tt0) in segs:
            b = c.bone(f"crack{len(cracks)}", x=p[0], y=p[1], rot=math.degrees(aa))
            core = _pic(c, b, "light_streak", LL * 1.4, height=0.08 * min(w, h), ox=0.5 * LL)
            halo = _pic(c, b, "light_streak", LL * 1.4, height=0.22 * min(w, h), ox=0.5 * LL)
            cracks.append((b, core, halo, tt0))
    b_fx = c.bone("burst", x=at[0], y=at[1])
    b_fb, b_co, b_ri, b_rw, b_ra = (c.bone(nm_, b_fx) for nm_ in ("flash", "core", "ring", "reward", "rays"))
    s_rw = _pic(c, b_rw, "glow_soft", 1.6 * max(w, h))
    s_ra = _pic(c, b_ra, "rays", 1.9 * max(w, h))
    s_fb = _pic(c, b_fb, "flash_burst", 1.5 * max(w, h))
    s_co = _pic(c, b_co, "glow_core", 1.4 * max(w, h))
    s_ri = _pic(c, b_ri, "ring", 1.0 * max(w, h))

    def grow(t, t0):                                     # SH_JERKS bursts: each a quick ease-out, then a pause
        if t <= t0:
            return 0.0
        span = (SB - 0.05 - t0) / SH_JERKS
        k = min(SH_JERKS - 1, int((t - t0) / span))
        u = (t - t0 - k * span) / (0.35 * span)
        return min(1.0, (k + ease_out(min(1.0, u), 3)) / SH_JERKS)
    tc = times_dense(0, SB + 0.06, FAST)
    for b, core, halo, t0 in cracks:
        c.show([core, halo], t0, SB + 0.06)
        c.bone_keys(b, "scale", tc, lambda t, t0=t0: (max(0.001, grow(t, t0)), 1.0))
        c.color_keys(core, tc, lambda t, t0=t0: _h(c, "FFFFFF" if t > SB - 0.12 else col, smooth(t, t0, t0 + 0.03) * (1 - smooth(t, SB, SB + 0.06))))
        c.color_keys(halo, tc, lambda t, t0=t0: _h(c, col2, 0.55 * smooth(t, t0, t0 + 0.05) * (0.7 + 0.3 * smooth(t, SB - 0.25, SB)) * (1 - smooth(t, SB, SB + 0.06))))
    c.show([s_in], 0, SB + 0.1)
    c.color_keys(s_in, times_dense(0, SB + 0.1, FAST), lambda t: _h(c, col2, (0.25 + 0.6 * smooth(t, 0, SB) ** 2) * (1 + 0.12 * math.sin(2 * math.pi * 11 * t)) * (1 - smooth(t, SB, SB + 0.1))))
    c.bone_keys(b_in, "scale", times_dense(0, SB + 0.1, FAST), lambda t: (0.5 + 0.6 * smooth(t, 0, SB),) * 2)

    q = lambda t: max(0.0, t - SB)  # noqa: E731
    tb = times_dense(SB - 0.02, D, FAST)
    c.show([s_fb, s_co, s_ri, s_rw, s_ra], SB - 0.02, D)
    c.bone_keys(b_fb, "scale", tb, lambda t: (0.3 + 1.0 * ease_out(q(t) / 0.15, 2.5),) * 2)
    c.bone_keys(b_fb, "rotate", tb, lambda t: 30.0 * q(t))
    c.color_keys(s_fb, tb, lambda t: _h(c, "FFFFFF", smooth(t, SB - 0.02, SB) * math.exp(-q(t) / 0.09)))
    c.color_keys(s_co, tb, lambda t: _h(c, "FFFFFF", smooth(t, SB - 0.02, SB) * (0.3 + 0.7 * math.exp(-q(t) / 0.15)) * (1 - smooth(t, D - 0.5, D))))
    c.bone_keys(b_ri, "scale", tb, lambda t: (0.3 + 1.6 * ease_out(q(t) / 0.45, 2.4),) * 2)
    c.color_keys(s_ri, tb, lambda t: _h(c, col, 0.9 * smooth(t, SB - 0.01, SB + 0.02) * (1 - smooth(q(t), 0.05, 0.45))))
    c.bone_keys(b_rw, "scale", tb, lambda t: (0.5 + 0.6 * ease_out(q(t) / 0.4, 2.5),) * 2)
    c.color_keys(s_rw, tb, lambda t: _h(c, col2, 0.85 * smooth(t, SB - 0.02, SB + 0.08) * (1 - smooth(t, D - 0.45, D))))
    c.bone_keys(b_ra, "scale", tb, lambda t: (0.4 + 0.7 * ease_out(q(t) / 0.5, 2.5),) * 2)
    c.bone_keys(b_ra, "rotate", tb, lambda t: 20.0 * q(t))
    c.color_keys(s_ra, tb, lambda t: _h(c, col2, 0.6 * smooth(t, SB, SB + 0.08) * (1 - smooth(t, D - 0.6, D))))
    for sh in shards:                                    # ballistic with light drag, spinning, fading at the end
        L = sh["life"]
        tt = times_dense(SB, min(D, SB + L), FAST)
        k_ = SH_DRAG

        def pos(t, sh=sh):
            r = q(t)
            e = (1 - math.exp(-k_ * r)) / k_
            return sh["vx"] * e, sh["vy"] * e - 0.5 * SH_G * r * r
        c.show([sh["s"]], SB, min(D, SB + L))
        c.bone_keys(sh["b"], "translate", tt, pos)
        c.bone_keys(sh["b"], "rotate", tt, lambda t, sh=sh: sh["spin"] * q(t))
        c.color_keys(sh["s"], tt, lambda t, sh=sh, L=L: _h(c, sh["tint"], 1 - smooth(q(t), 0.55 * L, L)))
    c.ab.event(c.T(0.0), "prop_crack")
    c.ab.event(c.T(SB), "prop_shatter")
    return _finish(c, P, duration=D * c.k, prop_bone=dr.bone, crack_at=c.T(0.0), shatter_at=c.T(SB),
                   cracks=len(cracks), shards=len(shards))


# ------------------------------------------------------------------ registry
_SZ = dict(size=(SIZE, "[w, h] of the prop in design units: places and sizes every FX"))
_PROP = dict(prop=("", "the prop's root bone (driven through carriers; empty: a bone of the recipe's own, parent your art to it)"))
_LID = dict(lid=("", "the lid's bone (driven through a hinge carrier; empty: a bone of the recipe's own)"),
            pivot=(None, "[x, y] the hinge, relative to the anchor (default [-w/2, 0.2 h]: the lid's back-left corner)"))


def _o(**kw) -> dict:
    return {**kw, **_GT}


RECIPES.update({
    "prop_peek": dict(
        fn=prop_peek, duration=PEEK_D, kind="one-shot", color="FFD84A",
        summary="A tease: the lid lifts a little in two hesitant tries (light leaks out of the wedge), glowing eyes look out "
                "of the gap, glance, blink and duck, then the lid falls shut under gravity and bounces on the rim "
                "(restitution arcs; the body jolts if prop= is given). Event prop_peek_shut at the slam.",
        anchor="The prop's centre; pivot and size are relative to it.",
        options=_o(**_LID, **_PROP, **_SZ, angle=(18.0, "how far the lid lifts, degrees"),
                   lift=(0.0, "also lift the lid straight up this far at the top of the tease"),
                   look=("eyes", "eyes (a pair of glowing eyes) | glint (one sparkle)"))),
    "prop_shake": dict(
        fn=prop_shake, duration=1.2, kind="window", color="FFC94A", normal_blend=True,
        summary="Anticipation rattle: the prop rocks on its base corners (lifted so the low corner stays on the floor), "
                "amplitude and frequency both rise over `duration`, it squashes on every landing and deeper each time and "
                "crouches as tension builds, holds still and crouched for `hold`, then springs back (event "
                "prop_shake_release at the end of the hold). Dust puffs kick out at the landing corner; a glow builds.",
        anchor="The prop's centre; pivot and size are relative to it.",
        options=_o(**_PROP, **_SZ, pivot=(None, "[x, y] the base the prop rocks on (default [0, -h/2])"),
                   amp=(6.0, "final rock angle, degrees"), hz=(None, "[start, end] rock frequency, Hz (default [5, 12])"),
                   squash=(0.08, "landing squash at the end of the build (0.08 = 8 %)"),
                   hold=(0.2, "seconds of still, crouched hold before the release"),
                   dust=(4, "dust puffs on the last landings (0 = none)"))),
    "prop_open": dict(
        fn=prop_open, duration=OPEN_D, kind="one-shot", color="FFD45A", count=8, normal_blend=True,
        summary="Chest / jar / box opens: wind-up (the body crouches, the lid trembles from the pressure), the lid is thrown "
                "open against gravity and caught by a spring at `angle` (exact overshoot, damped settle) while the body "
                "stretches back; light beams, flash and sparkles pour out of the opening, coins (normal blend) arc out "
                "on parabolas and bounce once on the floor. Events prop_open (the pop), prop_open_settled.",
        anchor="The prop's centre; pivot, base, opening and size are relative to it.",
        options=_o(**_LID, **_PROP, **_SZ, angle=(75.0, "open angle, degrees (the side away from the hinge swings up)"),
                   overshoot=(0.15, "the lid swings past `angle` by this fraction of it"),
                   windup=(0.1, "how far the body crouches before the pop (0.1 = 10 %)"),
                   base=(None, "[x, y] the body's squash pivot (default [0, -h/2])"),
                   opening=(None, "[x, y] where the light pours out (default the middle of the lid's front edge)"),
                   beams=(5, "light beams"), coins=(8, "coins spilled (0 = none)"))),
    "prop_hit": dict(
        fn=prop_hit, duration=HIT_D, kind="one-shot", color="FFB14A", count=10,
        summary="Reaction to a strike: an exact squash along the blow (`direction`), a kick along it and a wobble from the "
                "torque of an off-centre hit, each a damped spring that swings past rest and settles; a white flash over "
                "the prop, an impact star, ring and sparks thrown back toward the hitter (drag + gravity, oriented along "
                "their path). Event prop_hit at the contact (t = 0).",
        anchor="The prop's centre; at, pivot and size are relative to it.",
        options=_o(**_PROP, **_SZ, direction=(0.0, "the blow's direction, degrees (0 = pushed right, -90 = pushed down)"),
                   at=(None, "[x, y] the contact point (default: where the blow enters the box)"),
                   pivot=(None, "[x, y] the squash / wobble pivot (default the centre)"),
                   squash=(0.22, "squash along the blow at the peak (0.22 = 22 %)"), kick=(18.0, "kick distance, design units"),
                   wobble=(8.0, "torque wobble for a hit at the edge, degrees"))),
    "prop_upgrade": dict(
        fn=prop_upgrade, duration=UP_D, kind="one-shot", color="FFD24A", count=8,
        summary="Level-up: the prop crouches while a slanted light wipe sweeps across it and its glow (color) builds, a white "
                "flash at the swap frame (event prop_upgrade_swap: swap your art there), it pops `grow` bigger with a spring "
                "and settles, the new glow (color2) blooms with rays and a ring, light streaks rise, sparkles twinkle round it.",
        anchor="The prop's centre; pivot and size are relative to it.",
        options=_o(**_PROP, **_SZ, color2=("7DF4FF", "the new level's glow colour"), grow=(0.1, "pop size above rest (0.1 = +10 %)"),
                   pivot=(None, "[x, y] the scale pivot (default the base, [0, -h/2])"))),
    "prop_shatter": dict(
        fn=prop_shatter, duration=SH_D, kind="one-shot", color="FFE08A", count=7, normal_blend=True,
        summary="Breaks open: cracks of light run from the impact point in jerks (with forks), the inner glow and a tremble "
                "build, then it bursts: shards (normal blend, tinted shard_color) fly on ballistic paths with drag and spin, "
                "a white flash and ring, and the reward glow with rays revealed in the middle. Events prop_crack (t = 0), "
                "prop_shatter (the burst: with prop= its carrier scales to 0 there, hiding the art).",
        anchor="The prop's centre; at and size are relative to it.",
        options=_o(**_PROP, **_SZ, at=(None, "[x, y] the impact point the cracks run from (default [0, 0.1 h])"),
                   shards=(14, "shards (0 = none)"), shard_color=("C9A46A", "shard tint (the prop's material)"),
                   color2=("FFC93C", "reward glow colour"), hide=(True, "scale the prop to 0 at the burst (needs prop=)"))),
})
for _n, _pics in {"prop_peek": ("light_streak", "glow_soft", "eye", "flare_star"),
                  "prop_shake": ("smoke_puff", "glow_soft"),
                  "prop_open": ("coin", "glow_soft", "shine_band", "flash_burst", "glow_core", "flare_star"),
                  "prop_hit": ("glow_soft", "flash_burst", "flare_star", "ring", "spark"),
                  "prop_upgrade": ("glow_soft", "rays", "shine_band", "flash_burst", "ring", "light_streak", "flare_star"),
                  "prop_shatter": ("shard", "glow_soft", "light_streak", "rays", "flash_burst", "glow_core", "ring")}.items():
    ROLES[_n] = {p: ROLE_TEXT[p] for p in _pics}
    RECIPES[_n]["roles"] = ROLES[_n]
REVEAL_RECIPES = ("prop_peek", "prop_shake", "prop_open", "prop_hit", "prop_upgrade", "prop_shatter")
