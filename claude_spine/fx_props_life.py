"""Living props for ``fx_recipe``: idle LOOPS with character for a prop the artist already rigged (a floating gem, a pot
with a face, a sleeping chest, a spinning coin, a hanging lantern, a banner in the wind).

Like ``prop_idle`` they drive YOUR bones only through inserted carrier bones (``fx_reels._carrier``): translate and
scale merge with ``_merge_keys`` (so two recipes on one prop add up), rotations sit on a carrier of their own. Without a
bone option every recipe builds bones of its own (parent your art to the ``prop`` bone it reports) plus a stand-in
picture, so it previews on an empty skeleton.

* ``prop_bob``           floats: a slow figure-8 drift (x at f, y at 2f), a tilt that follows the sideways speed with a
                         little inertia, a dark ground shadow that shrinks and fades as the prop rises, optional sparkles
                         shed along the path.
* ``prop_blink``         a face: blinks (eyelid squash, 5 frames), the odd glance, a little hop with squash and stretch.
                         Event times look random (seeded) but never cross the loop seam. Events blink, hop, hop_land.
* ``prop_breathe_heavy`` sleeps / sits heavy: slow volume-preserving breathing (inhale stretches up, exhale squashes
                         wide, sx * sy = 1), a creaky settle wobble at the bottom of each exhale (event creak), optional
                         rising zzz or dust motes.
* ``prop_hover_spin``    a coin turning on its vertical axis while it floats: scaleX = cos(angle) (never thinner than a
                         real coin's edge), an additive edge light that peaks edge-on, a bob, a glint every time it faces
                         front (event glint).
* ``prop_dangle``        hangs: a pendulum about a pivot ABOVE the prop with the real period 2 pi sqrt(L / g), the prop
                         lagging the rope (follow-through), tassels lagging further (event creak at each extreme).
* ``prop_sway_wind``     banners / flags / plants: base sway plus gusts, a wave travelling root -> tip along a bone chain
                         (more lag and more swing toward the tip), optional motes blown past (event gust).

Every timeline's first key equals its last, and every periodic motion runs a whole number of cycles per loop.
Registered into fx_recipes.RECIPES / ROLES at import (fx_recipes imports this module at its end).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .fx import _rgba
from .fx_pinata import PICS
from .fx_props import _descendants
from .fx_recipes import RECIPES, ROLES, Ctx, _hexn, hexa, smooth

FPS = 30
FINE = 120                 # key rate inside short events (a 5-frame blink needs more than one key per frame)

# prop_bob ------------------------------------------------------------------------------------------------------------
BOB_TAU = 0.18             # s: the prop's rotational inertia, its tilt follows the sideways speed this late (1st-order lag)
SHADOW_SHRINK = 0.22       # contact shadow: +-22 % size and +-40 % darkness across the bob (inverse-square falloff with
SHADOW_FADE = 0.40         # height, linearised and exaggerated so it reads at game size)
SHADOW_ALPHA = 0.55        # darkness of the shadow at the mid height
SPARK_LIFE = 0.9           # s a shed sparkle lives
SPARK_FALL = 40.0          # units / s it sinks (it is left behind in still air, a little heavier than the air)
SPARK_FROM = 0.55          # shed from the prop's underside: this many prop widths below its origin

# prop_blink ----------------------------------------------------------------------------------------------------------
BLINK_CLOSE, BLINK_OPEN = 2 / FPS, 3 / FPS   # 5 frames: the lid drops fast (2), opens slower (3); a human blink is 0.1-0.4 s
LID_MIN = 0.1              # eyelid scaleY when shut (not 0: keeps the eye's line visible)
DOUBLE_GAP = 2 / FPS       # pause inside a double blink
SACCADE = 3 / FPS          # eyes jump to a new target in ~50-100 ms; 3 frames reads on screen
HOP_ANTIC, HOP_FLIGHT, HOP_SETTLE = 0.10, 0.30, 0.45   # crouch, air time, spring back (s)
ANTIC_SQ = 0.86            # scaleY at the bottom of the crouch (scaleX = 1 / scaleY: the volume stays)
HOP_STRETCH = 1.12         # scaleY at take-off speed (stretched along the velocity, back to 1 at the apex)
LAND_SQ = 0.80             # deepest landing squash
SETTLE_HZ, SETTLE_ZETA = 5.0, 0.32                     # the body's jelly spring after landing

# prop_breathe_heavy --------------------------------------------------------------------------------------------------
BR_IN, BR_TOP, BR_OUT = 0.42, 0.08, 0.30   # fractions of a breath: slow inhale, brief top, heavy exhale; rest after
EXHALE_SQ = 0.5            # how far below 1 the exhale squashes, as a share of `depth` (a sleeper rests squashed)
CREAK_HZ, CREAK_ZETA = 7.0, 0.18           # the settle: a stiff, lightly damped wobble excited by the exhale's thump
CREAK_JIGGLE = 0.25        # extra squash of the thump, as a share of `depth`

# prop_hover_spin -----------------------------------------------------------------------------------------------------
COIN_EDGE = 0.07           # edge-on a real coin is ~7 % of its diameter thick, so it never vanishes
EDGE_POWER = 3.0           # edge light ~ (1 - |cos|)^3: a rim catches the light only near edge-on
GLINT_SIGMA = 0.055        # s, width of the front-facing glint (a specular flash)

# prop_dangle ---------------------------------------------------------------------------------------------------------
GRAVITY = 9.81             # m / s^2
UNITS_PER_M = 250.0        # design units per metre (a ~250-unit lantern reads as about 1 m tall)
LAG_AMP, LAG_PHASE = 0.35, 0.9             # the prop's follow-through relative to its rope: 35 % of the swing, 0.9 rad late
STRAND_AMP, STRAND_FALL = 0.8, 0.85        # tassels: 80 % of the prop's lag, each further strand x0.85 and LAG_PHASE later
DAMP_TO = 0.35             # steady=False: the swing dies to 35 % before a breeze pumps it back (smoothly, inside the loop)

# prop_sway_wind ------------------------------------------------------------------------------------------------------
SWAY_GROW = 1.3            # each link toward the tip swings 1.3x its parent's share (lighter and less stiff)
WAVE_LAG = 0.55            # rad of phase per link: the wave travels root -> tip
WAVE_DELAY = 0.06          # s per link: a gust reaches the tip later
FLUTTER = 3                # flutter cycles per base cycle while a gust blows (strong wind whips faster)
GUST_RISE, GUST_FALL = 0.35, 1.0           # s: a gust builds fast and dies slowly


# ------------------------------------------------------------------ helpers
def _ss(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def _grid(D: float, rate: float = FPS, extra=()) -> list[float]:
    n = max(2, int(math.ceil(D * rate)))
    ts = {round(D * i / n, 5) for i in range(n + 1)}
    ts |= {round(min(max(float(t), 0.0), D), 5) for t in extra}
    return sorted(ts)


def _fine(windows, D: float) -> list[float]:
    """Extra key times every 1/FINE s inside each (t0, t1) event window."""
    out = []
    for t0, t1 in windows:
        n = max(2, int(math.ceil((t1 - t0) * FINE)))
        out += [t0 + (t1 - t0) * i / n for i in range(n + 1)]
    return [t for t in out if 0 <= t <= D]


def _closed(fn, D: float):
    """fn sampled so that the key at the loop end is the key at 0 exactly (rounding can never open the seam)."""
    return lambda t: fn(0.0 if t >= D - 1e-7 else t)


def _whole(P: dict, name: str) -> int:
    v = P[name]
    if int(v) != v or int(v) < 1:
        raise ValueError(f"{name} must be a whole number >= 1 (the loop closes only on whole cycles)")
    return int(v)


def _need(c: Ctx, bone: str, what: str) -> str:
    if not c.sk.has_bone(bone):
        raise ValueError(f"no bone {bone!r} for the {what}")
    return bone


def _on_prop(c: Ctx, prop: str) -> None:
    """Put the group bone on the prop's origin, so design offsets below are relative to the prop."""
    sk = c.sk
    w = sk.world()
    gb = sk.bone(c.group)
    gb.x, gb.y = (round(v, 3) for v in w[gb.parent].to_local(w[prop].x, w[prop].y))


def _to_group(c: Ctx, wx: float, wy: float) -> tuple[float, float]:
    return c.sk.world()[c.group].to_local(float(wx), float(wy))


def _drivers(c: Ctx, prop: str, spec) -> tuple[list[str], str]:
    """The bones the motion is keyed on, outermost first. spec = [(tag, (ox, oy)), ...], pivots in design units from the
    prop origin. With `prop`: carriers inserted above the artist's bone at those points (its own keys are never
    touched). Without: bones of our own nested the same way under the group, plus a `prop` bone to parent art to.
    Returns (drivers, holder)."""
    from .fx_reels import _carrier
    if prop:
        g = c.sk.world()[c.group]
        return [_carrier(c, prop, tag, g.to_world(*off)) for tag, off in spec], prop
    out, prev, at = [], c.group, (0.0, 0.0)
    for tag, off in spec:
        b = c.bone(tag, prev, off[0] - at[0], off[1] - at[1])
        out.append(b)
        prev, at = b, off
    return out, c.bone("prop", prev, -at[0], -at[1])


def _conv(c: Ctx, bone: str):
    """Design-unit vector in the group frame -> the same world vector in `bone`'s parent space (translate keys)."""
    w = c.sk.world()
    g, p = w[c.group], w[c.sk.bone(bone).parent]
    det = p.a * p.d - p.b * p.c

    def f(dx, dy):
        gx, gy = g.a * dx + g.b * dy, g.c * dx + g.d * dy
        return (p.d * gx - p.b * gy) / det, (p.a * gy - p.c * gx) / det
    return f


def _units(c: Ctx, bone: str) -> float:
    """Design units -> local units of a bone outside the group (a child of a carrier)."""
    w = c.sk.world()
    g, b = w[c.group], w[bone]
    return math.sqrt(abs(g.a * g.d - g.b * g.c) / max(abs(b.a * b.d - b.b * b.c), 1e-12))


def _move(c: Ctx, bone: str, own: bool, ts, fn, D: float) -> None:
    from .fx_reels import _merge_keys
    f = _closed(fn, D)
    if own:
        c.bone_keys(bone, "translate", ts, f)
    else:
        cv = _conv(c, bone)
        _merge_keys(c, bone, "translate", ts, lambda u: cv(*f(u)), "add")


def _scale(c: Ctx, bone: str, own: bool, ts, fn, D: float) -> None:
    from .fx_reels import _merge_keys
    f = _closed(fn, D)
    if own:
        c.bone_keys(bone, "scale", ts, f)
    else:
        _merge_keys(c, bone, "scale", ts, f, "mul")


def _rotate(c: Ctx, bone: str, ts, fn, D: float) -> None:
    c.bone_keys(bone, "rotate", ts, _closed(fn, D))


def _art_centre(c: Ctx, bone: str):
    """World centre of the region attachments on `bone` itself in the setup pose (the prop's body), or None."""
    from .ir import RegionAttachment
    sk = c.sk
    wb = sk.world()[bone]
    pts = []
    for s in sk.slots:
        if s.bone == bone and s.attachment:
            att = sk.attachment(s.name, s.attachment)
            if isinstance(att, RegionAttachment):
                pts.append(wb.to_world(att.x or 0.0, att.y or 0.0))
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)) if pts else None


def _layer(c: Ctx, holder: str, where: str) -> None:
    """Our slots go behind (where='behind') or in front of the prop's layers, unless the caller placed them."""
    if c.behind or c.front_of:
        return
    under = [s.name for s in c.sk.slots if s.bone in _descendants(c.sk, holder)]
    if under:
        if where == "behind":
            c.behind = under[0]
        else:
            c.front_of = under[-1]


def _pic(c: Ctx, bone: str, pic: str, width: float, height: float | None = None, blend: str = "additive",
         role: str | None = None, ox: float = 0.0, oy: float = 0.0) -> str:
    tex, make = (f"fx/pinata_{pic}", PICS[pic]) if pic in PICS else (f"fx/props_{pic}", NEW_PICS[pic])
    s = c.slot(bone, tex, width, height=height, make=make, blend=blend, role=role or pic, stretch=height is not None,
               ox=ox, oy=oy)
    c.show([s], 0, None)
    return s


def _scatter(rng, n: int, D: float, length: float, gap: float, margin: float = 0.12) -> list[float]:
    """n start times that look random but keep every event (of `length` s) inside the loop and `gap` s apart: the free
    time is cut at random points (stick breaking), so it always fits and never crosses the loop seam."""
    if n <= 0:
        return []
    free = D - 2 * margin - n * length - (n - 1) * gap
    if free < 0:
        raise ValueError(f"{n} events of {length:.2f} s do not fit a {D:.2f} s loop; lengthen duration or ask for fewer")
    cuts = rng.dirichlet(np.ones(n + 1)) * free
    out, t = [], margin
    for i in range(n):
        t += float(cuts[i])
        out.append(t)
        t += length + gap
    return out


def _particles(c: Ctx, D: float, items, rate: float = FPS) -> None:
    """Looping particles. items = [(bone, slot, spawn, life, state, color)], state(age) -> (x, y, scale, rot, alpha) with
    alpha 0 at age 0 and at `life`. Each respawn jump sits between two keys 2 ms apart where alpha is 0."""
    for bone, slot, s0, life, st, col in items:
        life = min(life, D)
        ts = _grid(D, rate, [s0 % D, (s0 - 0.002) % D, (s0 + life) % D])

        def at(t, s0=s0, life=life, st=st):
            age = (t - s0) % D
            return st(age) if age <= life else (*st(life)[:4], 0.0)
        f = _closed(at, D)
        c.bone_keys(bone, "translate", ts, lambda t, f=f: f(t)[:2])
        c.bone_keys(bone, "scale", ts, lambda t, f=f: (f(t)[2],) * 2)
        c.bone_keys(bone, "rotate", ts, lambda t, f=f: f(t)[3])
        c.color_keys(slot, ts, lambda t, f=f, col=col: hexa(col, c.a(f(t)[4])))


def _bell(u: float) -> float:
    """0 -> 1 -> 0 over u in [0, 1], fast in, slow out (a flash or a mote's life)."""
    u = min(max(u, 0.0), 1.0)
    return math.sin(math.pi * u ** 0.6) ** 1.5


# ------------------------------------------------------------------ new picture (fades to alpha 0 before its edges)
def _z_letter() -> Image.Image:
    """A soft, slightly italic Z for the sleeper's zzz, with a halo; a clear margin all round."""
    n, k = 96, 4
    m = n * k
    im = Image.new("L", (m, m), 0)
    d = ImageDraw.Draw(im)
    a, b, sk = 0.27 * m, 0.73 * m, 0.04 * m
    d.line([(a + sk, a), (b + sk, a), (a - sk, b), (b - sk, b)], fill=255, width=int(0.1 * m), joint="curve")
    im = im.resize((n, n), Image.LANCZOS)
    core = np.asarray(im.filter(ImageFilter.GaussianBlur(0.8)), np.float32) / 255
    halo = np.asarray(im.filter(ImageFilter.GaussianBlur(5)), np.float32) / 255
    y, x = np.mgrid[0:n, 0:n]
    edge = np.clip((np.minimum.reduce([x, y, n - 1 - x, n - 1 - y]) - 2) / 6, 0, 1)   # forced to 0 at the border
    return _rgba(np.ones((n, n)), np.clip(np.maximum(core, halo * 0.55), 0, 1) * edge)


NEW_PICS = {"zzz": _z_letter}


# ------------------------------------------------------------------ prop_bob
def prop_bob(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    prop = str(P["prop"] or "")
    own = not prop
    cyc = _whole(P, "cycles")
    ax, ay = (float(v) for v in P["drift"])
    tilt, size = float(P["tilt"]), float(P["size"])
    col = _hexn(P["color"], "FFE9A8")
    w = 2 * math.pi * cyc / D
    lag = math.atan(w * BOB_TAU)                       # phase lag of a first-order follower at this frequency
    pos = lambda t: (ax * math.sin(w * t), ay * math.sin(2 * w * t))  # noqa: E731   Lissajous 1:2 = a lazy figure 8
    lean = lambda t: -tilt * math.cos(w * t - lag)  # noqa: E731   leans into the sideways speed (cos = d/dt sin), a bit late
    if prop:
        _need(c, prop, "prop")
        _on_prop(c, prop)
    (mv, rot), holder = _drivers(c, prop, [("bob", (0.0, 0.0)), ("bobtilt", (0.0, 0.0))])
    ts = _grid(D)
    _move(c, mv, own, ts, pos, D)
    _rotate(c, rot, ts, lean, D)
    gy = -float(P["lift"]) if P["ground"] is None else _to_group(c, c.sk.world()[c.group].x, float(P["ground"]))[1]
    res = dict(duration=D, loop=D, carriers=[] if own else [mv, rot], prop_bone=holder, ground=round(gy, 3),
               cycles=cyc, frequencies=[cyc / D, 2 * cyc / D])
    if prop:
        _layer(c, holder, "behind")                    # shadow and trail under the prop
    sw = float(P["shadow"])
    if sw > 0:
        sb = c.bone("shadow", c.group, 0.0, gy)
        s = _pic(c, sb, "glow_soft", sw, sw * 0.3, blend="normal", role="shadow")
        sc = _hexn(P["shadow_color"], "120A1A")
        n_of = lambda t: pos(t)[1] / max(ay, 1e-9)  # noqa: E731   -1 lowest .. 1 highest
        c.bone_keys(sb, "translate", ts, _closed(lambda t: (pos(t)[0], 0.0), D))
        c.bone_keys(sb, "scale", ts, _closed(lambda t: (1 - SHADOW_SHRINK * n_of(t),) * 2, D))
        c.color_keys(s, ts, _closed(lambda t: hexa(sc, c.a(SHADOW_ALPHA * (1 - SHADOW_FADE * n_of(t)))), D))
        res["shadow_slot"] = s
    if own:                                            # stand-in prop: a soft orb with a hot core
        _pic(c, holder, "glow_soft", size * 1.6, role="body")
        _pic(c, holder, "glow_core", size * 0.9, role="body")
    n = int(P["trail"]) if P["trail"] is not None else (6 if own else 0)
    if n:
        if prop and c.last_slot is not None and not P["trail_behind"]:   # the trail is shed in FRONT of the prop
            under = [s.name for s in c.sk.slots if s.bone in _descendants(c.sk, holder)]
            c.last_slot, c.behind, c.front_of = None, "", under[-1] if under else ""
        rng = np.random.default_rng(c.seed + 409)
        items = []
        for i in range(n):
            s0 = (i + float(rng.uniform(0.15, 0.85))) * D / n
            px, py = pos(s0)
            ox, oy = float(rng.uniform(-0.2, 0.2)) * size, (float(rng.uniform(-0.12, 0.08)) - SPARK_FROM) * size
            dx, spin = float(rng.uniform(-8, 8)), float(rng.uniform(-120, 120))
            pk = float(rng.uniform(0.7, 1.1))
            b = c.bone(f"sp{i}", c.group)
            sl = _pic(c, b, "flare_star", size * 0.34, role="sparkle")

            def st(age, px=px + ox, py=py + oy, dx=dx, spin=spin, pk=pk):
                u = age / SPARK_LIFE
                tw = _bell(u) * (0.75 + 0.25 * math.cos(6 * math.pi * u))     # twinkles as it fades
                return (px + dx * age, py - SPARK_FALL * age, pk * (0.4 + 0.7 * _bell(u)), spin * age, tw)
            items.append((b, sl, s0, SPARK_LIFE, st, col))
        _particles(c, D, items)
        res["sparkles"] = n
    return c.result(**res)


# ------------------------------------------------------------------ prop_blink
def _lid(t: float, starts) -> float:
    """Eyelid scaleY: 1 -> LID_MIN in 2 frames (accelerating), back in 3 (decelerating), for each blink start."""
    v = 1.0
    for s in starts:
        u = t - s
        if 0 <= u < BLINK_CLOSE:
            v = min(v, 1 - (1 - LID_MIN) * (u / BLINK_CLOSE) ** 2)
        elif BLINK_CLOSE <= u <= BLINK_CLOSE + BLINK_OPEN:
            p = (u - BLINK_CLOSE) / BLINK_OPEN
            v = min(v, LID_MIN + (1 - LID_MIN) * (1 - (1 - p) ** 2))
    return v


def _hop(t: float, t0: float, H: float) -> tuple[float, float]:
    """(lift, scaleY) of a hop starting its crouch at t0: crouch, ballistic flight y = v t - g t^2 / 2 (g from height and
    air time), stretched along the speed, a landing squash on a damped spring. scaleX is 1 / scaleY."""
    from .fx_reels import _spring
    u = t - t0
    if u < 0:
        return 0.0, 1.0
    if u < HOP_ANTIC:
        return 0.0, 1 - (1 - ANTIC_SQ) * _ss(u / HOP_ANTIC)
    u -= HOP_ANTIC
    F = HOP_FLIGHT
    if u < F:
        g = 8 * H / F ** 2
        v = g * F / 2
        vy = v - g * u
        st = (HOP_STRETCH - 1) * abs(vy) / v * (1 - smooth(u, F - 2 / FPS, F))
        k = _ss(u / (2 / FPS))                         # 2 frames from the crouch into the stretch
        return v * u - g * u * u / 2, ANTIC_SQ * (1 - k) + (1 + st) * k
    u -= F
    if u < HOP_SETTLE:
        x = _spring(1 - LAND_SQ, SETTLE_HZ, SETTLE_ZETA)
        return 0.0, 1 + x(u) * (1 - smooth(u, 0.6 * HOP_SETTLE, HOP_SETTLE))
    return 0.0, 1.0


HOP_LEN = HOP_ANTIC + HOP_FLIGHT + HOP_SETTLE


def prop_blink(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    prop = str(P["prop"] or "")
    own = not prop
    size = float(P["size"])
    eyes = [str(e) for e in (P["eyes"] or [])]
    nb, ng, nh = int(P["blinks"]), int(P["glances"]), int(P["hops"])
    H, G = float(P["hop"]), float(P["glance"])
    rng = np.random.default_rng(c.seed + 503)
    BL = BLINK_CLOSE + BLINK_OPEN
    snap = lambda t: round(t * FPS) / FPS  # noqa: E731   events start on a frame, so frame 2 of a blink is fully shut
    starts = [snap(s) for s in _scatter(rng, nb, D, 2 * BL + DOUBLE_GAP, 0.45)]   # each slot can hold a double blink
    dbl = int(rng.integers(0, nb)) if (P["double"] and nb) else -1
    blinks = []
    for i, s in enumerate(starts):
        blinks.append(s)
        if i == dbl:
            blinks.append(s + BL + DOUBLE_GAP)
    gl = []
    for s in _scatter(rng, ng, D, 2 * SACCADE + 1.0, 0.3):
        s, hold = snap(s), snap(float(rng.uniform(0.5, 1.0)))
        ang = float(rng.choice([0.0, math.pi])) + float(rng.uniform(-0.35, 0.35))   # mostly sideways, a little up/down
        gl.append((s, hold, G * math.cos(ang), G * math.sin(ang)))
    hops = [snap(s) for s in _scatter(rng, nh, D, HOP_LEN, 0.3)]

    def glance(t):
        x = y = 0.0
        for s, hold, gx, gy in gl:
            k = _ss((t - s) / SACCADE) * (1 - _ss((t - s - SACCADE - hold) / SACCADE))
            x, y = x + gx * k, y + gy * k
        return x, y

    def hop(t):
        y, sy = 0.0, 1.0
        for s in hops:
            dy, k = _hop(t, s, H)
            y, sy = y + dy, sy * k
        return y, sy

    if prop:
        _need(c, prop, "prop")
        _on_prop(c, prop)
    for e in eyes:
        _need(c, e, "eye")
    base = (0.0, 0.0) if P["base"] is None else _to_group(c, *P["base"])
    (mv, sq), holder = _drivers(c, prop, [("hop", (0.0, 0.0)), ("hopsquash", base)])
    wins = [(s, s + BL) for s in blinks] + [(s, s + SACCADE) for s, *_ in gl] + \
           [(s + SACCADE + h, s + 2 * SACCADE + h) for s, h, *_ in gl] + [(s, s + HOP_LEN) for s in hops]
    ts = _grid(D, FPS, _fine(wins, D))
    _move(c, mv, own, ts, lambda t: (0.0, hop(t)[0]), D)
    _scale(c, sq, own, ts, lambda t: (1 / hop(t)[1], hop(t)[1]), D)
    res = dict(duration=D, loop=D, prop_bone=holder, blink_times=[round(s, 4) for s in blinks],
               glance_times=[round(g[0], 4) for g in gl], hop_times=[round(s, 4) for s in hops],
               carriers=[] if own else [mv, sq])
    eye_drv = []
    if eyes:                                           # your eyes: a glance carrier, then a blink carrier at each eye
        from .fx_reels import _carrier
        for e in eyes:
            eye_drv.append((_carrier(c, e, "glance"), _carrier(c, e, "blink"), False))
    elif own:                                          # stand-in face: a body glow and two star glints for eyes
        _pic(c, holder, "glow_soft", size * 1.5, role="body", oy=size * 0.5)
        for i, sx in enumerate((-1, 1)):
            g_ = c.bone(f"eye{i}_glance", holder, sx * 0.2 * size, 0.6 * size)
            b_ = c.bone(f"eye{i}_blink", g_)
            _pic(c, b_, "flare_star", size * 0.42, role="eye")
            eye_drv.append((g_, b_, True))
    for g_, b_, mine in eye_drv:
        _move(c, g_, mine, ts, glance, D)
        _scale(c, b_, mine, ts, lambda t: (1.0, _lid(t, blinks)), D)
        if not mine:
            res["carriers"] += [g_, b_]
    res["eye_bones"] = [b_ for _, b_, _ in eye_drv]
    for s in blinks:
        c.ab.event(c.T(s), "blink")
    for s in hops:
        c.ab.event(c.T(s + HOP_ANTIC), "hop")
        c.ab.event(c.T(s + HOP_ANTIC + HOP_FLIGHT), "hop_land")
    return c.result(**res)


# ------------------------------------------------------------------ prop_breathe_heavy
def _breath(u: float) -> float:
    """0 (exhaled, squashed) .. 1 (inhaled, stretched) over one breath u in [0, 1): a slow smooth inhale, a brief top,
    an exhale that falls under its own weight (1 - p^2: it lands moving, the thump that sets off the creak), rest."""
    u %= 1.0
    if u < BR_IN:
        return _ss(u / BR_IN)
    if u < BR_IN + BR_TOP:
        return 1.0
    if u < BR_IN + BR_TOP + BR_OUT:
        p = (u - BR_IN - BR_TOP) / BR_OUT
        return 1 - p * p
    return 0.0


def prop_breathe_heavy(c: Ctx, P: dict) -> dict:
    from .fx_reels import _spring
    D = float(P["duration"])
    prop = str(P["prop"] or "")
    own = not prop
    nb = _whole(P, "breaths")
    depth, creak, size = float(P["depth"]), float(P["creak"]), float(P["size"])
    Tb = D / nb
    t_land = BR_IN + BR_TOP + BR_OUT                    # fraction of a breath where the exhale bottoms out
    rest = (1 - t_land) * Tb
    wob = _spring(1.0, CREAK_HZ, CREAK_ZETA)           # unit damped wobble starting at rest with speed

    def settle(t):
        u = (t % Tb) - t_land * Tb
        if u < 0:
            return 0.0
        return wob(u) * (1 - smooth(u, 0.6 * rest, 0.95 * rest))   # dies inside the rest, exactly 0 before the inhale

    def sy(t):
        b = _breath(t / Tb)
        return 1 - depth * EXHALE_SQ + depth * (1 + EXHALE_SQ) * b + depth * CREAK_JIGGLE * settle(t)
    if prop:
        _need(c, prop, "prop")
        _on_prop(c, prop)
    base = (0.0, 0.0) if P["pivot"] is None else _to_group(c, *P["pivot"])
    (rot, sc), holder = _drivers(c, prop, [("creak", base), ("breath", base)])
    lands = [k * Tb + t_land * Tb for k in range(nb)]
    ts = _grid(D, FPS, _fine([(t, t + rest) for t in lands], D))
    _rotate(c, rot, ts, lambda t: creak * settle(t), D)
    _scale(c, sc, own, ts, lambda t: (1 / sy(t), sy(t)), D)      # sx * sy = 1: the volume stays
    for t in lands:
        c.ab.event(c.T(t), "creak")
    res = dict(duration=D, loop=D, breaths=nb, prop_bone=holder, creak_times=[round(t, 4) for t in lands],
               carriers=[] if own else [rot, sc])
    if own:
        _pic(c, holder, "glow_soft", size * 1.7, role="body", oy=size * 0.5)
    else:
        _layer(c, holder, "front")
    kind = str(P["rising"]) if P["rising"] is not None else ("zzz" if own else "")
    if kind not in ("", "zzz", "dust"):
        raise ValueError("rising must be zzz | dust | empty")
    if kind:
        n = int(P["rising_count"]) or (3 if kind == "zzz" else 8)
        col = _hexn(P["color"], "D8E8FF" if kind == "zzz" else "FFE2A0")
        rng = np.random.default_rng(c.seed + 617)
        mx, my = (float(v) for v in P["mouth"])
        items = []
        for i in range(n):
            b = c.bone(f"r{i}", c.group)
            if kind == "zzz":                           # one z per exhale, extra ones 0.4 s apart; they drift up-wind
                s0 = (i % nb) * Tb + (BR_IN + BR_TOP) * Tb + (i // nb) * 0.4
                life = min(D, 2.4)
                sl = _pic(c, b, "zzz", size * 0.32, role="zzz")
                ph = float(rng.uniform(0, 2 * math.pi))

                def st(age, life=life, ph=ph, k=0.85 + 0.3 * (i % 3) / 2):
                    u = age / life
                    return (mx + 0.35 * size * u + 8 * math.sin(2 * math.pi * 1.2 * age + ph), my + 0.9 * size * u,
                            k * (0.45 + 0.75 * u), 14 * math.sin(2 * math.pi * 0.6 * age + ph), _bell(u))
            else:                                       # dust motes lifting off the top in the warm air
                s0 = (i + float(rng.uniform(0, 1))) * D / n
                life = min(D, float(rng.uniform(1.4, 2.2)))
                sl = _pic(c, b, "glow_core", size * float(rng.uniform(0.1, 0.18)), role="mote")
                x0, ph = float(rng.uniform(-0.45, 0.45)) * size, float(rng.uniform(0, 2 * math.pi))

                def st(age, life=life, x0=x0, ph=ph):
                    u = age / life
                    return (x0 + 10 * math.sin(2 * math.pi * 0.8 * age + ph), my * 0.85 + 0.6 * size * u,
                            0.7 + 0.5 * math.sin(math.pi * u), 0.0, _bell(u) * 0.8)
            items.append((b, sl, s0, life, st, col))
        _particles(c, D, items)
        res["rising"] = n
    return c.result(**res)


# ------------------------------------------------------------------ prop_hover_spin
def prop_hover_spin(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    prop = str(P["prop"] or "")
    own = not prop
    turns, bc = _whole(P, "turns"), _whole(P, "bob_cycles")
    size, amp = float(P["size"]), float(P["bob"])
    col = _hexn(P["color"], "FFE7A0")
    ang = lambda t: 2 * math.pi * turns * t / D  # noqa: E731   steady spin: a coin on its axis keeps its speed

    def sx(t):
        cs = math.cos(ang(t))
        return math.copysign(max(abs(cs), COIN_EDGE), cs if cs != 0 else 1.0)
    bob = lambda t: (0.0, amp * math.sin(2 * math.pi * bc * t / D))  # noqa: E731
    fronts = [k * D / turns for k in range(turns)]

    def dfront(t):                                      # signed time to the nearest front-facing moment (wrapped)
        return min((((t - f) + D / 2) % D - D / 2 for f in fronts), key=abs)

    def glint(t):                                       # a flash centred on every front-facing moment
        return math.exp(-(dfront(t) / GLINT_SIGMA) ** 2)
    if prop:
        _need(c, prop, "prop")
        _on_prop(c, prop)
    (mv, sp), holder = _drivers(c, prop, [("spinbob", (0.0, 0.0)), ("spin", (0.0, 0.0))])
    ts = _grid(D, 2 * FPS, [f + d for f in fronts for d in (-2 * GLINT_SIGMA, -GLINT_SIGMA, 0, GLINT_SIGMA, 2 * GLINT_SIGMA)]
               + [D + f - 2 * GLINT_SIGMA for f in fronts[:1]])
    _move(c, mv, own, ts, bob, D)
    _scale(c, sp, own, ts, lambda t: (sx(t), 1.0), D)
    res = dict(duration=D, loop=D, turns=turns, prop_bone=holder, glint_times=[round(f, 4) for f in fronts],
               carriers=[] if own else [mv, sp])
    if own:
        _pic(c, holder, "coin", size, blend="normal", role="coin")
    else:
        _layer(c, holder, "front")
    k = 1.0 if own else _units(c, mv)                  # the lights ride the bob, not the turn
    if P["edge"]:
        eb = c.bone("edge", mv, 0, 0)
        s = _pic(c, eb, "shine_band", size * 0.34 * k, size * 1.08 * k, role="edge")
        c.color_keys(s, ts, _closed(lambda t: hexa(col, c.a(0.9 * (1 - abs(math.cos(ang(t)))) ** EDGE_POWER)), D))
        res["edge_slot"] = s
    if P["glint"]:
        gb = c.bone("glint", mv, -0.22 * size * k, 0.22 * size * k)
        s1 = _pic(c, gb, "glow_core", size * 0.5 * k, role="glint")
        s2 = _pic(c, gb, "flare_star", size * 0.7 * k, role="glint")
        c.bone_keys(gb, "scale", ts, _closed(lambda t: (0.35 + 0.75 * glint(t),) * 2, D))
        c.bone_keys(gb, "rotate", ts, _closed(lambda t: -20 * dfront(t) / GLINT_SIGMA * glint(t), D))   # the star turns through the flash
        for s_, a_ in ((s1, 0.7), (s2, 1.0)):
            c.color_keys(s_, ts, _closed(lambda t, a_=a_: hexa(col, c.a(a_ * glint(t))), D))
        res["glint_slots"] = [s1, s2]
    for f in fronts:
        c.ab.event(c.T(f), "glint")
    return c.result(**res)


# ------------------------------------------------------------------ prop_dangle
def prop_dangle(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    prop = str(P["prop"] or "")
    own = not prop
    A, size = float(P["swing"]), float(P["size"])
    strands = [str(s) for s in (P["strands"] or [])]
    col = _hexn(P["color"], "FFC86A")
    if prop:
        _need(c, prop, "prop")
        _on_prop(c, prop)
    for s in strands:
        _need(c, s, "strand")
    if P["pivot"] is not None:                          # your pivot: the rope is the distance to the prop's origin
        piv = _to_group(c, *P["pivot"])
        rope = math.hypot(*piv)
        if rope < 1e-6:
            raise ValueError("pivot is on the prop's origin; it must be ABOVE the prop (the rope's top)")
    else:
        rope = float(P["rope"])
        piv = (0.0, rope)
    gw = c.sk.world()[c.group]
    L_m = rope * math.sqrt(abs(gw.a * gw.d - gw.b * gw.c)) / UNITS_PER_M   # world rope length in metres
    T_phys = 2 * math.pi * math.sqrt(L_m / GRAVITY)
    n = max(1, round(D / T_phys))                       # whole swings per loop: the period closest to the real one
    T = D / n
    w = 2 * math.pi / T
    steady = bool(P["steady"])

    def env(t):                                         # steady: 1; else dies to DAMP_TO, a breeze pumps it back at the end
        if steady:
            return 1.0
        u = t / D
        k = -math.log(DAMP_TO) / 0.75
        return math.exp(-k * min(u, 0.75)) + (1 - DAMP_TO) * _ss((u - 0.75) / 0.25)
    rope_rot = lambda t: A * env(t) * math.sin(w * t)  # noqa: E731
    lag_rot = lambda t: A * LAG_AMP * env(t) * math.sin(w * t - LAG_PHASE)  # noqa: E731
    (sw, lg), holder = _drivers(c, prop, [("dangle", piv), ("dangle_lag", (0.0, 0.0))])
    ts = _grid(D)
    _rotate(c, sw, ts, rope_rot, D)
    _rotate(c, lg, ts, lag_rot, D)
    res = dict(duration=D, loop=D, prop_bone=holder, pivot=list(gw.to_world(*piv)), rope=round(rope, 3),
               period=round(T, 4), physical_period=round(T_phys, 4), swings=n, carriers=[] if own else [sw, lg])
    if P["rope_bone"]:                                  # your rope: swings with the rope carrier (not the prop's lag)
        from .fx_reels import _carrier
        rb_ = _need(c, str(P["rope_bone"]), "rope")
        rc = _carrier(c, rb_, "dangle", gw.to_world(*piv))
        _rotate(c, rc, ts, rope_rot, D)
        res["carriers"].append(rc)
    st_info = []
    if strands:
        from .fx_reels import _carrier
        for i, s in enumerate(strands):
            car = _carrier(c, s, "dangle_strand")
            a_i, ph = A * LAG_AMP * STRAND_AMP * STRAND_FALL ** i, LAG_PHASE * (i + 2)
            _rotate(c, car, ts, lambda t, a_i=a_i, ph=ph: a_i * env(t) * math.sin(w * t - ph), D)
            st_info.append(dict(bone=s, carrier=car, amplitude=round(a_i, 3), phase=round(ph, 3)))
            res["carriers"].append(car)
    res["strands"] = st_info
    glow = float(P["glow"]) if P["glow"] is not None else (size * 1.5 if own else 0.0)
    if own:                                             # stand-in: the rope (a stretched light line) under the swing bone
        rb = c.bone("rope", sw, 0, 0, rot=math.degrees(math.atan2(-piv[1], -piv[0])))
        _pic(c, rb, "light_streak", rope * 1.12, 10.0, role="rope", ox=rope * 0.5)
    elif glow:
        _layer(c, holder, "behind")
    if glow:                                            # the lantern's light: flickers on whole cycles of the loop
        k = 1.0 if own else _units(c, lg)
        ctr = None if own else _art_centre(c, holder)  # on the body, not on the hanging point
        gx, gy = c.sk.world()[lg].to_local(*ctr) if ctr else (0.0, 0.0)
        gb = c.bone("glow", lg, round(gx, 3), round(gy, 3))
        s1 = _pic(c, gb, "glow_soft", glow * k, role="glow")
        s2 = _pic(c, gb, "glow_core", glow * 0.45 * k, role="glow")
        f1, f2 = max(1, round(5 * D / 4)), max(1, round(11 * D / 4))

        def fl(t):
            return 0.78 + 0.12 * math.sin(2 * math.pi * f1 * t / D) + 0.08 * math.sin(2 * math.pi * f2 * t / D + 1.3)
        for s_, a_ in ((s1, 0.8), (s2, 1.0)):
            c.color_keys(s_, ts, _closed(lambda t, a_=a_: hexa(col, c.a(a_ * fl(t))), D))
        res["glow_slots"] = [s1, s2]
    for k_ in range(2 * n):                             # the rope creaks at each extreme of the swing
        c.ab.event(c.T((math.pi / 2 + k_ * math.pi) / w), "creak")
    return c.result(**res)


# ------------------------------------------------------------------ prop_sway_wind
def prop_sway_wind(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    chain = [str(b) for b in (P["chain"] or [])]
    own = not chain
    cyc, ng = _whole(P, "cycles"), int(P["gusts"])
    sway, gust = float(P["sway"]), float(P["gust"])
    wind = 1.0 if float(P["wind"]) >= 0 else -1.0
    col = _hexn(P["color"], "FFF4D0")
    rng = np.random.default_rng(c.seed + 733)
    sk = c.sk
    if chain:
        for b in chain:
            _need(c, b, "chain")
        _on_prop(c, chain[0])
        w0 = sk.world()
        tip = w0[chain[-1]].to_world(w0[chain[-1]].length or 0.0, 0.0)         # the last bone's tail
        dirx, diry = tip[0] - w0[chain[0]].x, tip[1] - w0[chain[0]].y
        if math.hypot(dirx, diry) < 1e-6:
            dirx, diry = 0.0, 1.0                       # one bone with no length: assume it stands up
            tip = (w0[chain[0]].x, w0[chain[0]].y + 1.0)
        cl = _to_group(c, *tip)                         # root -> tip in design units (the group sits on the root)
    else:
        nl, h = int(P["links"]), float(P["height"])
        if nl < 2:
            raise ValueError("links must be >= 2")
        dirx, diry = 0.0, 1.0
        cl = (0.0, h)
    if not chain:
        seg = h / nl
        links, prev = [], c.group
        for i in range(nl):
            prev = c.bone(f"link{i}", prev, 0.0, 0.0 if i == 0 else seg)
            links.append(prev)
    else:
        from .fx_reels import _carrier
        links = [_carrier(c, b, "sway") for b in chain]
    n = len(links)
    norm = math.hypot(dirx, diry) or 1.0
    # wind torque only acts across the chain: an upright plant leans downwind, a flag streaming along the wind only flutters
    lean_sign = -wind * (diry / norm)
    along = abs(dirx) / norm                           # ... what does not lean flutters: a flag streaming along the wind
    flut = gust * (0.35 + 0.9 * along)                 # ripples all the time (its flapping instability), harder in gusts
    wts = [SWAY_GROW ** i for i in range(n)]
    shares = [x / sum(wts) for x in wts]               # the options are the TIP's total bend; links share it, more at the tip
    gl = GUST_RISE + GUST_FALL
    if ng * gl > D:
        raise ValueError(f"{ng} gusts of {gl:.2f} s do not fit a {D:.2f} s loop")
    shift = float(rng.uniform(0, D))                   # gusts are periodic, so they may straddle the seam: rotate the lot
    starts = sorted((s + shift) % D for s in _scatter(rng, ng, D, gl, 0.1, margin=0.0))

    def env(t):                                        # periodic gust envelope (a gust may straddle the loop seam)
        v = 0.0
        for s in starts:
            u = (t - s) % D
            if u < GUST_RISE:
                v += _ss(u / GUST_RISE)
            elif u < gl:
                v += 1 - _ss((u - GUST_RISE) / GUST_FALL)
        return v
    wb, wf = 2 * math.pi * cyc / D, 2 * math.pi * cyc * FLUTTER / D

    def rot(i):
        def f(t):
            td = t - i * WAVE_DELAY
            e = env(td % D)
            ripple = math.sin(wf * t - i * 1.6 * WAVE_LAG)
            return shares[i] * (sway * ((1 - along) * math.sin(wb * t - i * WAVE_LAG) + along * ripple)
                                + e * (gust * lean_sign + flut * ripple))
        return f
    ts = _grid(D)
    for i, b in enumerate(links):
        _rotate(c, b, ts, rot(i), D)
    res = dict(duration=D, loop=D, links=links, gust_times=[round(s, 4) for s in starts], carriers=[] if own else links,
               shares=[round(s, 4) for s in shares], phase_lag=WAVE_LAG)
    if own:                                            # a ribbon whose rows ride our chain (a strand, rows re-parented)
        rows = n + 1
        rib, nodes = c.strand(c.group, "fx/pinata_shine_band", float(P["width"]), h, rows,
                              make=PICS["shine_band"], role="ribbon")
        sk.bone(sk.bone(nodes[0]).parent).y = h / 2    # the strand spans 0 .. h from the chain root
        for i, nd in enumerate(nodes):
            bn = sk.bone(nd)
            bn.parent, bn.x, bn.y = (links[i], 0.0, 0.0) if i < n else (links[-1], 0.0, seg)
        c.show([rib], 0, None)
        c.color_keys(rib, ts, _closed(lambda t: hexa(col, c.a(0.75 + 0.25 * min(1.0, env(t)))), D))
        res["ribbon"] = rib
    else:
        holder = chain[0]
        _layer(c, holder, "front")
    m = int(P["motes"]) if P["motes"] is not None else (6 if own else 0)
    if m:
        W = float(P["spread"])
        span = math.hypot(*cl)
        y_lo, y_hi = min(0.0, cl[1]) - 0.2 * span, max(0.0, cl[1]) + 0.2 * span   # blown past the chain, not above it
        items = []
        for i in range(m):
            b = c.bone(f"m{i}", c.group)
            sl = _pic(c, b, "spark", float(rng.uniform(34, 50)), role="mote")
            life = min(D, float(rng.uniform(0.9, 1.4)))
            s0 = (i + float(rng.uniform(0, 1))) * D / m
            y0, ph = float(rng.uniform(y_lo, y_hi)), float(rng.uniform(0, 2 * math.pi))

            def st(age, life=life, y0=y0, ph=ph):
                u = age / life
                x = cl[0] / 2 + wind * (-W / 2 + W * u)
                vy = 2 * math.pi * 1.1 * 14 * math.cos(2 * math.pi * 1.1 * age + ph)
                a = math.degrees(math.atan2(vy, wind * W / life))
                return (x, y0 + 14 * math.sin(2 * math.pi * 1.1 * age + ph), 1.0, a + (180 if wind < 0 else 0),
                        math.sin(math.pi * u) ** 1.2 * 0.9)
            items.append((b, sl, s0, life, st, col))
        _particles(c, D, items)
        res["motes"] = m
    for s in starts:
        c.ab.event(c.T(s), "gust")
    return c.result(**res)


# ------------------------------------------------------------------ registry
_PROP = ("", "the prop's root bone (empty: a bone of the recipe's own; parent your art to it)")
RECIPES.update({
    "prop_bob": dict(
        fn=prop_bob, duration=4.0, kind="loop", color="FFE9A8", normal_blend=True,
        summary="A floating prop: slow figure-8 drift (x at f, y at 2f), a tilt that follows the sideways speed a little late "
                "(inertia), a dark ground shadow that shrinks and fades as the prop rises (normal blend), optional sparkles "
                "shed along the path. Drives your bone through carriers. Seamless loop of `duration`.",
        anchor="With prop: ignored (the group sits on the prop's origin). Without: the prop centre.",
        options=dict(prop=_PROP, drift=([14.0, 11.0], "[x, y] half-size of the figure 8, design units"),
                     cycles=(1, "figure-8 laps per loop (whole number)"), tilt=(6.0, "lean at full sideways speed, degrees"),
                     ground=(None, "world y of the ground for the shadow (default: `lift` below the prop's origin)"),
                     lift=(150.0, "height of the prop's origin above the ground when `ground` is not given"),
                     shadow=(170.0, "shadow width (0 = no shadow)"), shadow_color=("", "shadow tint (default near-black)"),
                     size=(120.0, "the prop's width, sizes the sparkles and the stand-in"),
                     trail=(None, "sparkles shed per loop (default 0 with a prop, 6 for the stand-in)"),
                     trail_behind=(False, "draw the sparkles behind the prop (default: in front)"))),
    "prop_blink": dict(
        fn=prop_blink, duration=5.0, kind="loop", color="FFFFFF",
        summary="A prop with a face (pot, totem, mascot): blinks (eyelid scaleY 1 -> 0.1 -> 1 in 5 frames, one double "
                "blink), an occasional glance (eyes jump, hold, jump back), a little hop with crouch / stretch / landing "
                "squash (volume kept). Event times are seeded pseudo-random and never cross the loop seam. Events "
                "blink, hop, hop_land. Without bones: a stand-in body and two star glints for eyes.",
        anchor="With prop: ignored. Without: the prop's base (it hops from here).",
        options=dict(prop=_PROP, eyes=([], "eye bones (each gets a glance and a blink carrier)"),
                     base=(None, "[x, y] world point the hop squashes onto (default: the prop's origin)"),
                     blinks=(3, "blinks per loop"), double=(True, "make one of them a double blink"),
                     glances=(1, "glances per loop"), glance=(8.0, "how far the eyes move, design units"),
                     hops=(1, "hops per loop"), hop=(26.0, "hop height, design units"),
                     size=(120.0, "the prop's width (stand-in size)"))),
    "prop_breathe_heavy": dict(
        fn=prop_breathe_heavy, duration=4.5, kind="loop", color="",
        summary="A sleeping / treasure-heavy prop: slow squashy breathing (inhale stretches up, exhale squashes wide, "
                "sx * sy = 1), a creaky settle (tiny fast damped wobble) where each exhale lands (event creak), optional "
                "rising zzz or dust motes. Drives your bone through carriers pivoting on its base.",
        anchor="With prop: ignored. Without: the prop's base.",
        options=dict(prop=_PROP, pivot=(None, "[x, y] world point it squashes onto (its base; default the prop's origin)"),
                     breaths=(1, "breaths per loop (whole number)"), depth=(0.07, "stretch at full inhale (0.07 = +7 % tall)"),
                     creak=(1.6, "settle wobble, degrees"), rising=(None, "zzz | dust | '' (default zzz for the stand-in)"),
                     rising_count=(0, "how many (0 = 3 z or 8 motes)"),
                     mouth=([45.0, 110.0], "where the zzz start, design units from the prop's origin"),
                     size=(140.0, "the prop's width (stand-in, zzz and mote size)"))),
    "prop_hover_spin": dict(
        fn=prop_hover_spin, duration=3.0, kind="loop", color="FFE7A0", normal_blend=True,
        summary="A coin / token spinning on its vertical axis while it floats: scaleX = cos(angle) (never thinner than a real "
                "coin's edge), an additive edge light brightest edge-on, a bob, a glint flash each time it faces front "
                "(event glint). Without a prop: a stand-in coin (normal blend).",
        anchor="With prop: ignored. Without: the coin centre.",
        options=dict(prop=_PROP, turns=(2, "turns per loop (whole number)"), bob=(10.0, "bob height, design units"),
                     bob_cycles=(1, "bobs per loop (whole number)"), size=(150.0, "the coin's diameter, sizes the lights"),
                     edge=(True, "edge light"), glint=(True, "front-facing glint"))),
    "prop_dangle": dict(
        fn=prop_dangle, duration=3.6, kind="loop", color="FFC86A",
        summary="A hanging prop (lantern, piñata, sign): pendulum swing about a pivot ABOVE it with the real period "
                "2 pi sqrt(L / g) (rounded to whole swings per loop), the prop lagging its rope (follow-through), tassels "
                "(strands) lagging further and smaller; steady or dying down and pumped back. Event creak at each "
                "extreme. Without bones: a rope line and a glowing bob.",
        anchor="With prop: ignored. Without: the bob (the pivot is `rope` above it).",
        options=dict(prop=_PROP, pivot=(None, "[x, y] world point the rope hangs from (default: `rope` above the prop)"),
                     rope=(200.0, "rope length, design units (ignored when pivot is given)"),
                     rope_bone=("", "your rope's bone (a sibling of the prop, origin at the pivot): swings with the rope"),
                     swing=(9.0, "swing amplitude, degrees"), steady=(True, "constant swing; false = dies down, a breeze revives it"),
                     strands=([], "tassel / ribbon bones, each swung a little later and smaller"),
                     glow=(None, "> 0: a flickering light this wide on the prop (default on for the stand-in)"),
                     size=(120.0, "the prop's width (stand-in size)"))),
    "prop_sway_wind": dict(
        fn=prop_sway_wind, duration=4.0, kind="loop", color="FFF4D0",
        summary="Banners / flags / plants in the wind: base sway plus gust envelopes (lean downwind and flutter), a wave "
                "travelling root -> tip along `chain` (each link later and swinging more), optional motes blown past. "
                "Event gust. Without bones: a chain of our own with a ribbon.",
        anchor="With chain: ignored (the group sits on the chain root). Without: the chain root.",
        options=dict(chain=([], "bones root -> tip (each gets a rotate carrier)"),
                     sway=(6.0, "base sway at the tip, degrees (shared along the chain)"),
                     gust=(16.0, "extra lean at the tip during a gust, degrees"), gusts=(2, "gusts per loop"),
                     cycles=(2, "base sway cycles per loop (whole number)"), wind=(1.0, "+1 wind to the right, -1 to the left"),
                     motes=(None, "motes blown past (default 0 with a chain, 6 for the stand-in)"),
                     spread=(420.0, "how far the motes travel"), links=(5, "stand-in chain links"),
                     height=(300.0, "stand-in chain length"), width=(70.0, "stand-in ribbon width"))),
})
ROLES["prop_bob"] = {"shadow": "the ground shadow: soft dark ellipse (normal blend)", "body": "the stand-in prop glow",
                     "sparkle": "one shed sparkle"}
ROLES["prop_blink"] = {"body": "the stand-in body glow", "eye": "one stand-in eye (a star glint)"}
ROLES["prop_breathe_heavy"] = {"body": "the stand-in body glow", "zzz": "one z (soft letter, centred)", "mote": "one dust mote"}
ROLES["prop_hover_spin"] = {"coin": "the stand-in coin (normal blend)", "edge": "the edge light: soft vertical bar",
                            "glint": "the front-facing glint (glow and star)"}
ROLES["prop_dangle"] = {"rope": "the stand-in rope: a horizontal line (turned along the rope)", "glow": "the lantern light"}
ROLES["prop_sway_wind"] = {"ribbon": "the stand-in ribbon: a tall strip, bent as a mesh", "mote": "one mote, head on the RIGHT"}
for _n in ("prop_bob", "prop_blink", "prop_breathe_heavy", "prop_hover_spin", "prop_dangle", "prop_sway_wind"):
    RECIPES[_n]["roles"] = ROLES[_n]
