"""Collect / payout prop recipes for ``fx_recipe``: a prop the artist rigged (a jar, a chest, a totem, a pot) takes
part in the payout. Like ``fx_props`` they drive YOUR bones only through inserted carrier bones (``fx_reels._carrier``;
translate and scale merge with any earlier recipe's keys on the same carrier), never your own keys; without a bone
option they use a bone of their own (parent your art to it).

* ``prop_absorb``          items (coins or glow orbs) spiral into the prop's mouth, accelerating and shrinking; the prop
                           gulps (squash pulse) on every arrival, the mouth flashes. Event prop_absorb_hit per arrival.
* ``prop_overflow``        coins pop out of the opening on parabolas: the first fall back onto a growing heap, the next
                           spill over the rim, hit the floor, hop once and skid to rest, the last few land on the rim
                           and spin down (scaleX = cos) until they lie face-on. Event prop_overflow.
* ``counter_plate``        a number plate ticks up: an accelerating run of punches, each with a glint and a shake that
                           grows with the value, the last a big punch with a flash. Events counter_tick, counter_done.
* ``prop_multiplier_slam`` crouch, leap, hang at the apex, slam down (accelerating), squash on impact; shockwave ring,
                           dust puffs, flash, and an "xN" stamp plate punches in with overshoot. Event prop_slam.
* ``prop_charge``          a meter on the prop fills with light from the bottom up, cracks of light split open near
                           full, the pulse quickens, then it overloads into a burst; `level` < 1 stops and breathes.
                           Event prop_charged.
* ``gem_glint``            seamless loop: a narrow slanted light band sweeps across the prop, star twinkles on facets,
                           a periodic hard glint; `sync_tilt` times the sweep to prop_idle's tilt peak.

Positions are relative to the anchor; with a bone option the anchor is that bone's origin (x, y become an offset).
Pictures are the pinata kit (``fx_pinata.PICS``) plus one of our own (``crack``); every picture is an ``art=`` role.
Translate keys are offsets from the setup pose, so every bone that moves is created at 0, 0 and keyed absolutely.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .fx import _rgba
from .fx_pinata import _GT, PIC_ROLES, PICS, _finish, backout
from .fx_recipes import RECIPES, ROLES, Ctx, _blur, _hexn, _uniq, ease_out, hexa, smooth, times_dense
from .ir import ClippingAttachment, Slot

FPS = 30
GOLD = "FFC94A"

# ---------------------------------------------------------------- prop_absorb
ABSORB_POP = 0.12        # s: an item pops into view at its source (back-out scale) before the pull takes it
ABSORB_FLIGHT = 0.62     # s from the source to the mouth (option flight)
ABSORB_EASE = 2.2        # path progress s = u^EASE: starts at rest and accelerates all the way in (a pull, not a throw)
ABSORB_WIND = 1.5        # the angle catches up late (s^WIND): items fall more straight first, then whirl round the mouth
ABSORB_SHRINK = 0.2      # size at the mouth, x its size at the source
ABSORB_SPIN = 1.6        # coin flips per second while it flies (scaleX = cos)
ABSORB_TRAIL_V = 900.0   # speed (units/s) at which the trail streak reaches its full length
ABSORB_TAIL = 0.55       # s after the last arrival: the last gulp settles, the ring spreads, the glow dies
THUMP_HZ = 6.5           # the prop's gulp per arrival: a damped squash, first lobe ~1 frame after contact
THUMP_DECAY = 0.075      # s (1/e) for the gulp to die

# ---------------------------------------------------------------- prop_overflow
OVER_G = 2400.0          # gravity, design units / s^2 (a ~150-unit hop is up and down in ~0.7 s: snappy, not floaty)
OVER_E = 0.35            # restitution: a spilled coin leaves the floor at 35 % of its impact speed (one low hop)
OVER_HOP_VX = 0.55       # the hop keeps 55 % of the sideways speed (friction at the contact)
OVER_SLIDE = 0.16        # s: after the hop the coin skids to rest under constant friction
OVER_LAUNCH = 0.9        # s over which the coins come out: the heap first, then the spill, the edge coins last
OVER_PILE = 0.35         # fraction of the coins that fall back onto the heap in the opening
OVER_HEAP = 0.32         # heap height when it is done, x the rim width
OVER_FLIP = 2.2          # edge coins: flips per second in the air (scaleX = cos)
OVER_SPIN_T = 0.75       # s an edge coin spins down on the rim (decelerating) before it lies face-on
OVER_FADE = 0.3          # s: everything fades out at the end
OVER_HOLD = 0.35         # s everything lies still before the fade

# ---------------------------------------------------------------- counter_plate
COUNT_GAP = 0.2          # s between the first two ticks
COUNT_ACCEL = 0.86       # each gap is 86 % of the previous one: the count speeds up as it climbs
COUNT_HZ = 6.0           # per-tick punch: damped scale kick
COUNT_DECAY = 0.07       # s
SHAKE_HZ = (24.0, 19.0)  # the plate shakes on x and y at these rates on every tick, amplitude growing with the value
SHAKE_DECAY = 0.09       # s
FINAL_HZ = 3.2           # the last tick: a slower, bigger punch
FINAL_DECAY = 0.18       # s
COUNT_TAIL = 0.65        # s after the last tick

# ---------------------------------------------------------------- prop_multiplier_slam
SLAM_ANTIC = 0.16        # s: the crouch before the leap
SLAM_UP = 0.38           # s: rise + hang. y = H (1 - (1-v)^4): fast off the ground, then hangs a long time near the top
SLAM_DROP = 0.10         # s: the slam. y = H (1 - u^2.6): starts at rest, accelerates harder than gravity
SLAM_SQUASH = 0.30       # squash at impact (scaleY 1 - 0.30); springs back through a stretch
SLAM_HZ = 4.5            # impact spring
SLAM_DECAY = 0.12        # s
STAMP_DELAY = 0.03       # s after impact the stamp starts to come down
STAMP_FALL = 0.08        # s the stamp falls in from 2.3x (accelerating) before it hits
DUST_DRAG = 6.0          # 1/s: dust puffs decelerate (x = v/k (1 - e^-kt))
SLAM_TAIL = 0.85         # s after impact

# ---------------------------------------------------------------- prop_charge
CHARGE_EASE = 1.7        # a full charge accelerates in: L = (t / fill)^EASE (faster and faster toward overload)
CHARGE_CRACKS = (0.72, 0.8, 0.87, 0.93)   # fill levels at which the cracks of light split open
CHARGE_HZ = (1.6, 9.0)   # pulse rate when empty and when full (Hz): f = lo + (hi - lo) L^2, integrated (no phase jumps)
CHARGE_BREATH = 0.9      # Hz: a partial charge breathes at this rate once it stops
CHARGE_OPEN = 0.08       # s: a crack splits open to its full length

# ---------------------------------------------------------------- gem_glint
GEM_IDLE = 0.755         # prop_idle's loop (s); its tilt peaks at u = 0.45
GEM_TILT_U = 0.45
GEM_REACH = 0.5          # the band travels from -REACH to +REACH x the width (the prop's sides), fading at both
GEM_TWINKLE = 0.4        # s life of a twinkle
GEM_GLINT_RISE = 0.035   # s: the hard glint is up in one frame ...
GEM_GLINT_DECAY = 0.14   # s: ... and decays this fast


# ================================================================ shared helpers
def _crack() -> Image.Image:
    """A branching crack of light: a jagged hot line with two side branches and a soft glow. White; clear border."""
    n, S = 256, 4
    img = Image.new("L", (n * S, n * S), 0)
    d = ImageDraw.Draw(img)
    rng = np.random.default_rng(5)

    def walk(x, y, ang, steps, step, w, wander):
        pts = [(x, y)]
        a0 = ang
        for _ in range(steps):
            ang = a0 + float(np.clip(ang - a0 + rng.uniform(-wander, wander), -0.5, 0.5))
            x, y = x + math.cos(ang) * step, y + math.sin(ang) * step
            pts.append((x, y))
        d.line(pts, fill=255, width=w, joint="curve")
        return pts
    N = n * S
    main = walk(N * 0.16, N / 2, 0.0, 16, N * 0.043, int(4.0 * S), 1.0)
    for k, sgn in ((5, -1), (10, 1)):
        walk(*main[k], sgn * 0.9, 6, N * 0.035, int(2.6 * S), 0.9)
    base = np.asarray(img, np.float32) / 255
    a = np.clip(_blur(base, 0.8 * S) * 1.4 + _blur(base, 6 * S) * 1.3, 0, 1)
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8), "L").resize((n, n), Image.LANCZOS), np.float32) / 255
    y, x = np.mgrid[0:n, 0:n]
    x, y = (x - (n - 1) / 2) / (n / 2), (y - (n - 1) / 2) / (n / 2)
    a *= np.clip((1 - np.maximum(np.abs(x), np.abs(y))) / 0.12, 0, 1)        # exactly 0 at the border
    return _rgba(np.ones(a.shape), np.clip(a, 0, 1))


OWN_PICS = {"crack": _crack}
OWN_ROLES = {"crack": "a crack of light, horizontal, centred (additive, white)",
             "plate": "the number plate (normal blend; the game's own plate is better: plate= its bone)",
             "stamp": "the 'xN' stamp plate (normal blend)"}


def _s(c: Ctx, bone: str, pic: str, width: float, height: float | None = None, blend: str = "additive",
       role: str | None = None, anchor: str = "center") -> str:
    """A slot showing kit picture `pic` (fx_pinata's PICS or our own), replaceable through art role `role` (default pic)."""
    tex = f"fx/pinata_{pic}" if pic in PICS else f"fx/props_{pic}"
    ox = {"right": -width / 2, "left": width / 2}.get(anchor, 0.0)
    oy = {"bottom": (height or width) / 2, "top": -(height or width) / 2}.get(anchor, 0.0)
    nm = c.slot(bone, tex, width, height=height, make=PICS.get(pic) or OWN_PICS[pic], blend=blend, role=role or pic,
                stretch=height is not None, ox=ox, oy=oy, anchor=anchor)
    if pic in PICS and (role or pic) == pic:
        c.__dict__.setdefault("_pic", {})[nm] = pic          # gain= / thick= apply to it
    return nm


def _h(c: Ctx, col: str, a: float) -> str:
    return hexa(col, c.a(max(0.0, min(1.0, a))))


def _kick(tau: float, hz: float, decay: float) -> float:
    """Impulse response of a damped spring, 0 before the hit, first lobe peaking at exactly 1."""
    if tau <= 0:
        return 0.0
    w = 2 * math.pi * hz
    tp = math.atan(w * decay) / w
    peak = math.exp(-tp / decay) * math.sin(w * tp)
    return math.exp(-tau / decay) * math.sin(w * tau) / peak


def _bone_opt(c: Ctx, P: dict, key: str) -> str:
    name = str(P.get(key) or "")
    if name and not c.sk.has_bone(name):
        raise ValueError(f"no bone {name!r} for the {key}")
    return name


def _mount(c: Ctx, bone: str, ride: bool) -> None:
    """Put the group bone on `bone`'s origin (x, y stay an offset). ride=True parents it to the bone, so the FX follow
    everything the bone does (its carriers included); otherwise the group keeps its parent (the FX stay in the world)."""
    g = c.sk.bone(c.group)
    if ride:
        g.parent = bone
        return
    w = c.sk.world()
    lx, ly = w[g.parent].to_local(w[bone].x, w[bone].y)
    g.x, g.y = round(lx + g.x, 3), round(ly + g.y, 3)


def _prop(c: Ctx, P: dict, key: str = "prop", ride: bool = False, own_pivot: tuple[float, float] = (0.0, 0.0)):
    """(bone, world pivot, own?): the artist's bone named by option `key` (the group moves onto it), or a bone of our
    own under the group. The pivot is option `pivot` (world) or the bone's origin."""
    name = _bone_opt(c, P, key)
    if name:
        _mount(c, name, ride)
        own = False
    else:
        name = c.bone(key, x=own_pivot[0], y=own_pivot[1])
        own = True
    w = c.sk.world()
    pv = P.get("pivot")
    pivot = (float(pv[0]), float(pv[1])) if pv and not own else (w[name].x, w[name].y)
    return name, pivot, own


def _drive_scale(c: Ctx, bone: str, tag: str, pivot, ts, fn) -> str:
    from .fx_reels import _carrier, _merge_keys
    car = _carrier(c, bone, tag, pivot)
    _merge_keys(c, car, "scale", ts, fn, "mul")
    return car


def _drive_move(c: Ctx, bone: str, tag: str, ts, fn) -> str:
    from .fx_reels import _carrier, _merge_keys
    car = _carrier(c, bone, tag)
    _merge_keys(c, car, "translate", ts, fn, "add")
    return car


def _pts(P: dict, key: str) -> list[tuple[float, float]]:
    try:
        return [(float(a), float(b)) for a, b in P[key]]
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be [[x, y], ...]") from None


# ================================================================ prop_absorb
def prop_absorb(c: Ctx, P: dict) -> dict:
    src = _pts(P, "sources")
    if not src:
        raise ValueError("sources: give at least one [x, y]")
    item = str(P["item"])
    if item not in ("coin", "orb"):
        raise ValueError(f"item must be coin | orb, got {item!r}")
    mx, my = (float(v) for v in P["at"])
    stagger, flight, size = float(P["stagger"]), float(P["flight"]), float(P["size"])
    swirl, A = math.radians(float(P["swirl"])), float(P["thump"])
    if flight <= 0 or size <= 0 or stagger < 0:
        raise ValueError("flight and size must be > 0, stagger >= 0")
    col = _hexn(P["color"], GOLD)
    prop, pivot, own = _prop(c, P)

    items = []
    for i, (sx, sy) in enumerate(src):
        t0 = i * stagger
        r0, th0 = math.hypot(sx - mx, sy - my), math.atan2(sy - my, sx - mx)
        items.append(dict(t0=t0, ta=t0 + ABSORB_POP + flight, r0=r0, th0=th0, src=(sx, sy)))
    arr = [it["ta"] for it in items]
    D = max(arr) + ABSORB_TAIL

    def prog(it, t):                       # path progress 0..1, accelerating
        u = min(max((t - it["t0"] - ABSORB_POP) / flight, 0.0), 1.0)
        return u ** ABSORB_EASE

    def pos(it, t):
        s = prog(it, t)
        r = it["r0"] * (1 - s)
        th = it["th0"] + swirl * s ** ABSORB_WIND
        return mx + r * math.cos(th), my + r * math.sin(th)

    def size_at(it, t):
        return backout((t - it["t0"]) / ABSORB_POP, 2.2) * (1 - (1 - ABSORB_SHRINK) * prog(it, t))

    # slots: the items first (coins are normal blend), then every light (additive)
    for i, it in enumerate(items):
        it["b"] = c.bone(f"item{i}")
        it["s"] = (_s(c, it["b"], "coin", size, blend="normal") if item == "coin"
                   else _s(c, it["b"], "glow_core", size * 2.8))
    for i, it in enumerate(items):
        it["bt"] = c.bone(f"trail{i}")
        it["st"] = _s(c, it["bt"], "spark", size * 2.6, height=size * 0.55, anchor="right")
    b_g, b_f, b_r = c.bone("mouth_glow", x=mx, y=my), c.bone("mouth_star", x=mx, y=my), c.bone("mouth_ring", x=mx, y=my)
    s_g = _s(c, b_g, "glow_soft", size * 4.0)
    s_f = _s(c, b_f, "flare_star", size * 2.6)
    s_r = _s(c, b_r, "ring", size * 3.2)

    for it in items:
        t0, ta = it["t0"], it["ta"]
        tt = times_dense(t0, ta, FPS)
        c.show([it["s"]], t0, ta)
        c.bone_keys(it["b"], "translate", tt, lambda t, it=it: pos(it, t))
        if item == "coin":
            c.bone_keys(it["b"], "scale", tt, lambda t, it=it: (size_at(it, t) * math.cos(2 * math.pi * ABSORB_SPIN * (t - it["t0"])),
                                                                 size_at(it, t)))
        else:
            c.bone_keys(it["b"], "scale", tt, lambda t, it=it: (size_at(it, t),) * 2)
            c.color_keys(it["s"], tt, lambda t, it=it: _h(c, col, 1.0))
        # the trail: points back along the velocity, as long and as bright as the item is fast
        tf = times_dense(t0 + ABSORB_POP, ta, FPS)
        h = 1e-3
        vel = [((pos(it, t + h)[0] - pos(it, t - h)[0]) / (2 * h), (pos(it, t + h)[1] - pos(it, t - h)[1]) / (2 * h)) for t in tf]
        vel[-1] = vel[-2] if len(vel) > 1 else vel[-1]          # the path ends at the mouth: keep the last heading
        ang = np.degrees(np.unwrap([math.atan2(vy, vx) for vx, vy in vel])).tolist()
        spd = [math.hypot(*v) for v in vel]
        c.show([it["st"]], t0 + ABSORB_POP, ta)
        c.ab.bone(it["bt"], "translate", _uniq([(c.T(t), *pos(it, t)) for t in tf]), "linear")
        c.ab.bone(it["bt"], "rotate", _uniq([(c.T(t), round(a, 2)) for t, a in zip(tf, ang)]), "linear")
        c.ab.bone(it["bt"], "scale", _uniq([(c.T(t), min(1.3, v / ABSORB_TRAIL_V), size_at(it, t)) for t, v in zip(tf, spd)]), "linear")
        c.ab.slot_color(it["st"], _uniq([(c.T(t), _h(c, col, 0.9 * min(1.0, v / ABSORB_TRAIL_V))) for t, v in zip(tf, spd)]), "linear")

    ts = times_dense(0, D, FPS)
    ts = sorted(set(ts) | set(arr))
    hits = lambda t, tau: sum(math.exp(-(t - a) / tau) for a in arr if t >= a)  # noqa: E731
    fade = lambda t: 1 - smooth(t, D - 0.3, D)  # noqa: E731
    c.show([s_g, s_f], 0, D)
    c.color_keys(s_g, ts, lambda t: _h(c, col, (0.3 * smooth(t, 0, arr[0]) + 0.55 * hits(t, 0.14)) * fade(t)))
    c.bone_keys(b_g, "scale", ts, lambda t: (0.8 + 0.25 * min(1.5, hits(t, 0.14)),) * 2)
    c.color_keys(s_f, ts, lambda t: _h(c, "FFF6D8", min(1.0, hits(t, 0.07)) * fade(t)))
    c.bone_keys(b_f, "scale", ts, lambda t: (0.3 + 0.8 * min(1.3, hits(t, 0.1)),) * 2)
    c.bone_keys(b_f, "rotate", ts, lambda t: 140.0 * t)
    aL = arr[-1]
    tr = times_dense(aL, min(D, aL + 0.5), FPS)
    c.show([s_r], aL, min(D, aL + 0.5))
    c.bone_keys(b_r, "scale", tr, lambda t: (0.25 + 1.5 * ease_out((t - aL) / 0.45, 2.5),) * 2)
    c.color_keys(s_r, tr, lambda t: _h(c, col, 0.85 * (1 - smooth(t - aL, 0.0, 0.45))))

    # the gulp: a squash pulse per arrival (the last one bigger), through a carrier above the prop
    weights = [1.0] * (len(arr) - 1) + [1.7]
    q = lambda t: sum(w * _kick(t - a, THUMP_HZ, THUMP_DECAY) for w, a in zip(weights, arr))  # noqa: E731
    car = _drive_scale(c, prop, "propsquash", pivot, ts, lambda t: (1 + A * q(t), 1 - A * q(t)))
    for i, a in enumerate(arr):
        c.ab.event(c.T(a), "prop_absorb_hit", int=i)
    return _finish(c, P, duration=D * c.k, arrivals=[c.T(a) for a in arr], carrier=car, prop_bone=prop, own_prop=own)


# ================================================================ prop_overflow
def prop_overflow(c: Ctx, P: dict) -> dict:
    rx, ry, rw = (float(v) for v in P["rim"])
    floor_y = float(P["floor"]) if P["floor"] is not None else ry - 260.0
    size = float(P["size"])
    N, n_edge = int(P["count"]), int(P["edge"])
    if N < 1:
        raise ValueError("count must be >= 1")
    if N > 60:
        raise ValueError(f"count={N}: keep Spine coins <= 60; heavier showers belong to the game's particle emitter")
    if rw <= 0 or size <= 0:
        raise ValueError("rim width and size must be > 0")
    if floor_y >= ry:
        raise ValueError("floor must be below the rim (floor < rim y)")
    col = _hexn(P["color"], GOLD)
    if _bone_opt(c, P, "prop"):
        _mount(c, str(P["prop"]), ride=False)                 # anchor only: the coins fly in the world
    rng = np.random.default_rng(c.seed + 613)
    G = OVER_G
    n_edge = max(0, min(n_edge, N))
    n_pile = min(N - n_edge, int(round(N * OVER_PILE)))
    kinds = ["pile"] * n_pile + ["spill"] * (N - n_pile - n_edge) + ["edge"] * n_edge
    side0 = 1 if rng.random() < 0.5 else -1
    coins = []
    for i, kind in enumerate(kinds):
        t0 = OVER_LAUNCH * (i / max(1, N - 1)) ** 0.9 + (float(rng.uniform(0, 0.03)) if i else 0.0)
        side = side0 * (1 if i % 2 == 0 else -1)
        y0 = ry - 0.2 * size
        cn = dict(kind=kind, t0=t0, side=side, w=float(rng.uniform(220, 520)) * side)
        if kind == "pile":
            j = i
            x0 = rx + float(rng.uniform(-0.28, 0.28)) * rw
            xt = rx + float(rng.uniform(-0.36, 0.36)) * rw * (1 - 0.4 * j / max(1, n_pile))
            heap = OVER_HEAP * rw * (j + 1) / max(1, n_pile)
            yt = ry + heap * max(0.15, 1 - ((xt - rx) / (0.5 * rw)) ** 2)
            hgt = max(float(rng.uniform(80, 150)), yt - y0 + 30)
        elif kind == "spill":
            x0 = rx + side * float(rng.uniform(0.05, 0.3)) * rw
            xt, yt = rx + side * (rw / 2 + float(rng.uniform(40, 200))), floor_y + 0.5 * size
            hgt = float(rng.uniform(130, 230))
        else:
            x0 = rx + side * float(rng.uniform(0.0, 0.18)) * rw
            xt, yt = rx + side * rw * 0.5, ry + 0.42 * size     # resting on the lip of the rim
            hgt = float(rng.uniform(100, 160))
        vy = math.sqrt(2 * G * hgt)
        for _ in range(40):                               # a spilled coin must clear the rim: push it further out
            T = (vy + math.sqrt(max(vy * vy - 2 * G * (yt - y0), 0.0))) / G
            vx = (xt - x0) / T
            if kind != "spill":
                break
            tx = (rx + side * rw / 2 - x0) / vx
            if vy * tx - 0.5 * G * tx * tx + y0 > ry + 0.6 * size:
                break
            xt += side * 25.0
        cn.update(x0=x0, y0=y0, vx=vx, vy=vy, T=T, xt=xt, yt=yt)
        if kind == "spill":
            cn["t_rim"] = (rx + side * rw / 2 - x0) / vx
            v_land = vy - G * T
            cn["vy2"], cn["vx2"] = -OVER_E * v_land, OVER_HOP_VX * vx
            cn["T2"] = 2 * cn["vy2"] / G
            cn["x2"] = xt + cn["vx2"] * cn["T2"]
            cn["end"] = T + cn["T2"] + OVER_SLIDE
        elif kind == "edge":
            om = 2 * math.pi * OVER_FLIP
            phL = om * T
            m = max(math.floor(phL / (2 * math.pi)) + 1, round((phL + om * OVER_SPIN_T / 2) / (2 * math.pi)))
            cn["Ts"] = 2 * (2 * math.pi * m - phL) / om          # decelerate so the spin stops exactly face-on
            cn["end"] = T + cn["Ts"]
        else:
            cn["end"] = T
        coins.append(cn)

    def state(cn, tau):
        """(x, y, rotation, scaleX) of a coin tau seconds after its launch."""
        T, w = cn["T"], cn["w"]
        if tau <= T:
            x, y = cn["x0"] + cn["vx"] * tau, cn["y0"] + cn["vy"] * tau - 0.5 * G * tau * tau
            sx = math.cos(2 * math.pi * OVER_FLIP * tau) if cn["kind"] == "edge" else 1.0
            return x, y, w * tau * (0.25 if cn["kind"] == "edge" else 1.0), sx
        if cn["kind"] == "pile":
            return cn["xt"], cn["yt"], w * T, 1.0
        if cn["kind"] == "spill":
            T2, t2 = cn["T2"], tau - T
            if t2 <= T2:                                       # the one hop
                return (cn["xt"] + cn["vx2"] * t2, cn["yt"] + cn["vy2"] * t2 - 0.5 * G * t2 * t2,
                        w * T + 0.5 * w * t2, 1.0)
            t3 = min(tau - T - T2, OVER_SLIDE)                 # skid to rest
            v3 = 0.5 * cn["vx2"]
            return (cn["x2"] + v3 * (t3 - t3 * t3 / (2 * OVER_SLIDE)), cn["yt"],
                    w * T + 0.5 * w * T2 + 0.3 * w * (t3 - t3 * t3 / (2 * OVER_SLIDE)), 1.0)
        Ts, t2 = cn["Ts"], min(tau - T, cn["Ts"])              # edge coin: spins down on the rim
        om = 2 * math.pi * OVER_FLIP
        ph = om * T + om * t2 - om * t2 * t2 / (2 * Ts)
        rot0 = w * T * 0.25
        wob = 9.0 * math.sin(2 * math.pi * 2.5 * t2) * (1 - t2 / Ts)
        return cn["xt"], cn["yt"], rot0 * (1 - smooth(t2, 0, Ts)) + wob, math.cos(ph)

    end = max(cn["t0"] + cn["end"] for cn in coins)
    D = end + OVER_HOLD + OVER_FADE

    # slots: coins (normal) back to front in launch order, then the lights
    for i, cn in enumerate(coins):
        cn["b"] = c.bone(f"coin{i}")
        cn["s"] = _s(c, cn["b"], "coin", size * float(rng.uniform(0.9, 1.1)), blend="normal")
    b_rg = c.bone("rim_glow", x=rx, y=ry)
    s_rg = _s(c, b_rg, "glow_soft", rw * 1.6, height=rw * 0.75)
    glints = []
    picks = [cn for cn in coins if cn["kind"] == "edge"] + [cn for cn in coins if cn["kind"] == "spill"][:3]
    for k, cn in enumerate(picks):
        b = c.bone(f"glint{k}", x=cn["xt"], y=cn["yt"] + 0.2 * size)
        glints.append((b, _s(c, b, "flare_star", size * 2.0), cn["t0"] + cn["T"]))

    fade_on = lambda t: 1 - smooth(t, D - OVER_FADE, D)  # noqa: E731
    for cn in coins:
        t0 = cn["t0"]
        contacts = [t0 + cn["T"]] + ([t0 + cn["T"] + cn["T2"]] if cn["kind"] == "spill" else [])
        tt = sorted(set(times_dense(t0, t0 + cn["end"], FPS)) | set(contacts))
        c.show([cn["s"]], t0, D)
        st = [state(cn, t - t0) for t in tt]
        c.ab.bone(cn["b"], "translate", _uniq([(c.T(t), round(s[0], 2), round(s[1], 2)) for t, s in zip(tt, st)]), "linear")
        c.ab.bone(cn["b"], "rotate", _uniq([(c.T(t), round(s[2], 2)) for t, s in zip(tt, st)]), "linear")
        if cn["kind"] == "edge":
            c.ab.bone(cn["b"], "scale", _uniq([(c.T(t), round(s[3], 4), 1.0) for t, s in zip(tt, st)]), "linear")
        c.ab.slot_color(cn["s"], [(c.T(D - OVER_FADE), "FFFFFFFF"), (c.T(D), "FFFFFF00")], "linear")

    ts = times_dense(0, D, FPS)
    launches = [cn["t0"] for cn in coins]
    c.show([s_rg], 0, D)
    c.color_keys(s_rg, ts, lambda t: _h(c, col, min(0.85, 0.12 * smooth(t, 0, 0.1) + sum(
        0.3 * math.exp(-((t - a) / 0.12) ** 2) for a in launches)) * fade_on(t)))
    c.bone_keys(b_rg, "scale", ts, lambda t: (1.0, 0.85 + 0.3 * min(1.0, sum(math.exp(-((t - a) / 0.15) ** 2) for a in launches))))
    for b, s, ta in glints:
        th = times_dense(ta - 0.02, min(D, ta + 0.4), FPS)
        c.show([s], ta - 0.02, min(D, ta + 0.4))
        c.bone_keys(b, "scale", th, lambda t, ta=ta: (0.3 + 0.9 * ease_out((t - ta) / 0.12),) * 2)
        c.bone_keys(b, "rotate", th, lambda t, ta=ta: 120.0 * (t - ta))
        c.color_keys(s, th, lambda t, ta=ta: _h(c, "FFF4C8", smooth(t, ta - 0.02, ta) * math.exp(-max(0.0, t - ta) / 0.12)))
    spills = [cn["t0"] + cn["t_rim"] for cn in coins if cn["kind"] == "spill"]
    t_over = min(spills) if spills else (coins[-1]["t0"] + coins[-1]["T"])
    c.ab.event(c.T(t_over), "prop_overflow")
    return _finish(c, P, duration=D * c.k, overflow_at=c.T(t_over),
                   coins=[dict(bone=cn["b"], kind=cn["kind"], launch=c.T(cn["t0"]), land=c.T(cn["t0"] + cn["T"])) for cn in coins])


# ================================================================ counter_plate
def counter_plate(c: Ctx, P: dict) -> dict:
    N = int(P["steps"])
    if not 1 <= N <= 40:
        raise ValueError("steps must be 1..40")
    pw, ph = (float(v) for v in P["size"])
    punch, final, shake = float(P["punch"]), float(P["final"]), float(P["shake"]) * c.S
    col = _hexn(P["color"], "FFE08A")
    rng = np.random.default_rng(c.seed + 727)
    name = _bone_opt(c, P, "plate")
    if name:
        _mount(c, name, ride=True)                           # our glints ride the plate (and its punches)
        plate, host, own = name, c.group, False
    else:
        plate = c.bone("plate")
        host, own = plate, True
    gaps = [COUNT_GAP * COUNT_ACCEL ** i for i in range(max(0, N - 1))]
    ticks = [0.1 + sum(gaps[:i]) for i in range(N)]
    tN = ticks[-1]
    D = tN + COUNT_TAIL

    # slots: our plate (normal) first, then the lights
    s_plate = _s(c, plate, "mult_number", pw, height=ph, blend="normal", role="plate") if own else None
    gl = []
    for i in range(N):
        b = c.bone(f"glint{i}", host, float(rng.uniform(-0.4, 0.4)) * pw, float(rng.uniform(-0.25, 0.3)) * ph)
        gl.append((b, _s(c, b, "flare_star", ph * float(rng.uniform(1.3, 1.6)))))
    b_gw, b_fl, b_rg = c.bone("glow", host), c.bone("flash", host), c.bone("ring", host)
    s_gw = _s(c, b_gw, "glow_soft", pw * 2.0, height=ph * 2.6)
    s_fl = _s(c, b_fl, "flash_burst", pw * 1.3)
    s_rg = _s(c, b_rg, "ring", pw * 1.4)

    amp = [shake * (i + 1) / N * (1.5 if i == N - 1 else 1.0) for i in range(N)]
    pop = [punch * (1 + 0.6 * i / max(1, N - 1)) for i in range(N - 1)]

    def scale(t):
        v = sum(p * _kick(t - a, COUNT_HZ, COUNT_DECAY) for p, a in zip(pop, ticks[:-1]))
        return 1 + v + final * _kick(t - tN, FINAL_HZ, FINAL_DECAY)

    def move(t):
        x = sum(a_ * math.exp(-(t - a) / SHAKE_DECAY) * math.sin(2 * math.pi * SHAKE_HZ[0] * (t - a)) for a_, a in zip(amp, ticks) if t >= a)
        y = sum(0.6 * a_ * math.exp(-(t - a) / SHAKE_DECAY) * math.sin(2 * math.pi * SHAKE_HZ[1] * (t - a) + 1.0)
                for a_, a in zip(amp, ticks) if t >= a)
        return x, y

    ts = sorted(set(times_dense(0, D, FPS * 2)) | set(ticks))      # 60 samples/s: the shake is 24 Hz
    car_s = _drive_scale(c, plate, "platepop", None, ts, lambda t: (scale(t), scale(t)))
    car_m = _drive_move(c, plate, "plateshake", ts, move)
    if own:
        c.show([s_plate], 0, D)
        c.color_keys(s_plate, [0, 0.1, D - 0.2, D], lambda t: _h(c, "FFFFFF", smooth(t, 0, 0.1) * (1 - smooth(t, D - 0.2, D))))
    for i, ((b, s), a) in enumerate(zip(gl, ticks)):
        th = times_dense(a - 0.02, min(D, a + 0.3), FPS)
        c.show([s], a - 0.02, min(D, a + 0.3))
        big = 1.6 if i == N - 1 else 1.0
        c.bone_keys(b, "scale", th, lambda t, a=a, big=big: (big * (0.2 + 0.9 * ease_out((t - a) / 0.1)),) * 2)
        c.bone_keys(b, "rotate", th, lambda t, a=a: 150.0 * (t - a))
        c.color_keys(s, th, lambda t, a=a: _h(c, "FFFFFF", smooth(t, a - 0.02, a) * math.exp(-max(0.0, t - a) / 0.13)))
    tg = times_dense(0, D, FPS)
    c.show([s_gw], 0, D)
    def glow(t):                                         # each tick flares it, brighter as the value climbs
        g = sum(0.35 * (0.5 + 0.5 * i / max(1, N - 1)) * math.exp(-(t - a) / 0.12) for i, a in enumerate(ticks) if t >= a)
        g += 0.5 * math.exp(-(t - tN) / 0.3) if t >= tN else 0.0
        return (0.15 + g) * smooth(t, 0, 0.1) * (1 - smooth(t, D - 0.25, D))
    c.color_keys(s_gw, tg, lambda t: _h(c, col, glow(t)))
    tf = times_dense(tN - 0.02, D, FPS)
    c.show([s_fl, s_rg], tN - 0.02, D)
    c.bone_keys(b_fl, "scale", tf, lambda t: (0.4 + 0.8 * ease_out((t - tN) / 0.12),) * 2)
    c.color_keys(s_fl, tf, lambda t: _h(c, "FFFFFF", smooth(t, tN - 0.02, tN) * math.exp(-max(0.0, t - tN) / 0.09)))
    c.bone_keys(b_rg, "scale", tf, lambda t: (0.4 + 1.2 * ease_out((t - tN) / 0.4, 2.5),) * 2)
    c.color_keys(s_rg, tf, lambda t: _h(c, col, 0.9 * smooth(t, tN - 0.02, tN) * (1 - smooth(t - tN, 0, 0.45))))
    for i, a in enumerate(ticks):
        c.ab.event(c.T(a), "counter_tick", int=i + 1)
    c.ab.event(c.T(tN), "counter_done")
    return _finish(c, P, duration=D * c.k, ticks=[c.T(a) for a in ticks], carriers=[car_m, car_s], plate_bone=plate, own_plate=own)


# ================================================================ prop_multiplier_slam
def prop_multiplier_slam(c: Ctx, P: dict) -> dict:
    H = float(P["height"]) * c.S
    if H <= 0:
        raise ValueError("height must be > 0")
    gy = float(P["ground"])
    sx_, sy_ = (float(v) for v in P["stamp"])
    ssz, R = float(P["stamp_size"]), float(P["ring"])
    col = _hexn(P["color"], "FFB347")
    dust_c = _hexn(P["dust"], "D9C7A6")
    rng = np.random.default_rng(c.seed + 811)
    prop, pivot, own = _prop(c, P, own_pivot=(0.0, gy))
    t_up = SLAM_ANTIC
    t_top = t_up + SLAM_UP
    t_imp = t_top + SLAM_DROP
    t_st = t_imp + STAMP_DELAY
    t_hit = t_st + STAMP_FALL
    D = t_imp + SLAM_TAIL

    def y(t):
        if t <= t_up or t >= t_imp:
            return 0.0
        if t <= t_top:
            return H * (1 - (1 - (t - t_up) / SLAM_UP) ** 4)
        return H * (1 - ((t - t_top) / SLAM_DROP) ** 2.6)

    def squash(t):
        """(scaleX, scaleY) about the base: crouch, stretch off the ground, stretch into the slam, squash + spring."""
        antic = smooth(t, 0, SLAM_ANTIC * 0.7) * (1 - smooth(t, SLAM_ANTIC * 0.7, SLAM_ANTIC))
        st = 0.0
        if t_up < t <= t_top:
            st = 0.14 * smooth(t, t_up, t_up + 0.04) * math.exp(-(t - t_up) / (0.25 * SLAM_UP))
        elif t_top < t < t_imp:
            st = 0.16 * ((t - t_top) / SLAM_DROP) ** 2
        sq = 0.0
        if t >= t_imp:
            tau = t - t_imp
            sq = SLAM_SQUASH * math.exp(-tau / SLAM_DECAY) * math.cos(2 * math.pi * SLAM_HZ * tau)
        return 1 - 0.5 * st + 0.7 * sq + 0.1 * antic, 1 + st - sq - 0.16 * antic

    # slots: dust and the stamp (normal) first, then the lights
    dust = []
    for i in range(6):
        side = -1 if i % 2 == 0 else 1
        b = c.bone(f"dust{i}")
        dust.append(dict(b=b, s=_s(c, b, "smoke_puff", 110.0 * float(rng.uniform(0.8, 1.2)), blend="normal"), side=side,
                         x0=side * float(rng.uniform(30, 80)), y0=gy + float(rng.uniform(5, 25)),
                         v=float(rng.uniform(420, 820)), rise=float(rng.uniform(25, 60)), t0=t_imp + float(rng.uniform(0, 0.05))))
    b_st = c.bone("stamp", x=sx_, y=sy_)
    s_st = _s(c, b_st, "x5_label", ssz, blend="normal", role="stamp")
    b_ring, b_gl, b_fl = c.bone("ring", x=0, y=gy), c.bone("glow", x=0, y=gy + 30), c.bone("flash", x=0, y=gy + 40)
    s_ring = _s(c, b_ring, "ring", R * 2.6)
    s_gl = _s(c, b_gl, "glow_soft", R * 2.2)
    s_fl = _s(c, b_fl, "flash_burst", R * 1.2)
    b_sg = c.bone("stamp_glint", x=sx_ + ssz * 0.32, y=sy_ + ssz * 0.18)
    s_sg = _s(c, b_sg, "flare_star", ssz * 0.9)

    ts = sorted(set(times_dense(0, D, FPS)) | set(times_dense(t_top, t_imp, 120)))   # the 3-frame slam keyed at 120/s
    car_m = _drive_move(c, prop, "propmove", ts, lambda t: (0.0, y(t)))
    car_s = _drive_scale(c, prop, "propsquash", pivot, ts, squash)
    for d in dust:
        t0 = d["t0"]
        td = times_dense(t0, D, FPS)
        k = DUST_DRAG
        c.show([d["s"]], t0, min(D, t0 + 0.8))
        c.bone_keys(d["b"], "translate", td, lambda t, d=d: (d["x0"] + d["side"] * d["v"] / k * (1 - math.exp(-k * (t - d["t0"]))),
                                                             d["y0"] + d["rise"] * (1 - math.exp(-3 * (t - d["t0"])))))
        c.bone_keys(d["b"], "scale", td, lambda t, d=d: (0.35 + 0.95 * ease_out((t - d["t0"]) / 0.6),) * 2)
        c.bone_keys(d["b"], "rotate", td, lambda t, d=d: -d["side"] * 50.0 * (t - d["t0"]))
        c.color_keys(d["s"], td, lambda t, d=d: _h(c, dust_c, 0.9 * smooth(t, d["t0"], d["t0"] + 0.04) * (1 - smooth(t, d["t0"] + 0.15, d["t0"] + 0.75))))
    # the stamp falls in (accelerating, from 2.3x), hits, squashes and springs back with overshoot; holds to the end
    tsp = sorted(set(times_dense(t_st, D, FPS)) | set(times_dense(t_st, t_hit, 120)))

    def st_scale(t):
        if t <= t_hit:
            u = (t - t_st) / STAMP_FALL
            return 1 + 1.3 * (1 - u * u)
        return 1 - 0.22 * _kick(t - t_hit, 4.0, 0.12)
    c.show([s_st], t_st, None)
    c.bone_keys(b_st, "scale", tsp, lambda t: (st_scale(t),) * 2)
    c.bone_keys(b_st, "rotate", tsp, lambda t: -16 + 10 * min(1.0, (t - t_st) / STAMP_FALL) + (
        4 * math.exp(-(t - t_hit) / 0.15) * math.sin(2 * math.pi * 3 * (t - t_hit)) if t > t_hit else 0.0))
    c.color_keys(s_st, [t_st, t_st + 0.03], lambda t: _h(c, "FFFFFF", smooth(t, t_st, t_st + 0.03)))
    ti = times_dense(t_imp - 0.02, D, FPS)
    c.show([s_ring, s_gl, s_fl], t_imp - 0.02, D)
    c.bone_keys(b_ring, "scale", ti, lambda t: (0.2 + 0.9 * ease_out((t - t_imp) / 0.5, 2.6), 0.32 * (0.2 + 0.9 * ease_out((t - t_imp) / 0.5, 2.6))))
    c.color_keys(s_ring, ti, lambda t: _h(c, col, 0.95 * smooth(t, t_imp - 0.02, t_imp) * (1 - smooth(t - t_imp, 0.0, 0.55))))
    c.bone_keys(b_gl, "scale", ti, lambda t: (1.0, 0.6))
    c.color_keys(s_gl, ti, lambda t: _h(c, col, 0.85 * smooth(t, t_imp - 0.02, t_imp) * math.exp(-max(0.0, t - t_imp) / 0.3)))
    c.bone_keys(b_fl, "scale", ti, lambda t: (0.5 + 0.8 * ease_out((t - t_imp) / 0.12),) * 2)
    c.color_keys(s_fl, ti, lambda t: _h(c, "FFF4D6", smooth(t, t_imp - 0.02, t_imp) * math.exp(-max(0.0, t - t_imp) / 0.09)))
    tg = times_dense(t_hit, min(D, t_hit + 0.45), FPS)
    c.show([s_sg], t_hit, min(D, t_hit + 0.45))
    c.bone_keys(b_sg, "scale", tg, lambda t: (0.2 + 0.9 * ease_out((t - t_hit) / 0.12),) * 2)
    c.bone_keys(b_sg, "rotate", tg, lambda t: 110.0 * (t - t_hit))
    c.color_keys(s_sg, tg, lambda t: _h(c, "FFFFFF", math.exp(-(t - t_hit) / 0.13)))
    c.ab.event(c.T(t_imp), "prop_slam")
    return _finish(c, P, duration=D * c.k, impact=c.T(t_imp), stamp_hit=c.T(t_hit), carriers=[car_m, car_s], prop_bone=prop,
                   own_prop=own)


# ================================================================ prop_charge
def prop_charge(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    W, Hm = float(P["width"]), float(P["height"])
    bx, by = (float(v) for v in P["base"])
    level, fill = float(P["level"]), float(P["fill"])
    if not 0 < level <= 1:
        raise ValueError("level must be in (0, 1]")
    if W <= 0 or Hm <= 0 or fill <= 0:
        raise ValueError("width, height and fill must be > 0")
    full = level >= 1.0
    T_f = fill if full else fill * max(level, 0.2)
    if T_f > D - (0.6 if full else 0.0):
        raise ValueError(f"duration {D:g}s is too short: the fill takes {T_f:.2f}s" + (" and the overload 0.6s" if full else ""))
    col = _hexn(P["color"], "4FE3FF")
    hot = "".join(f"{round(v * 0.45 + 255 * 0.55):02X}" for v in (int(col[i:i + 2], 16) for i in (0, 2, 4)))   # col, near white
    rng = np.random.default_rng(c.seed + 919)
    prop, pivot, own = _prop(c, P, ride=True)

    def L(t):
        u = min(max(t / T_f, 0.0), 1.0)
        return u ** CHARGE_EASE if full else level * u * u * (3 - 2 * u)

    ts = sorted(set(times_dense(0, D, FPS)) | {T_f})
    # the pulse: its rate follows the fill (integrated, so it quickens without a jump); a partial charge then breathes
    fr = [CHARGE_HZ[0] + (CHARGE_HZ[1] - CHARGE_HZ[0]) * L(t) ** 2 if (t <= T_f or full) else CHARGE_BREATH for t in ts]
    ph = np.concatenate([[0.0], np.cumsum([2 * math.pi * 0.5 * (fr[i] + fr[i + 1]) * (ts[i + 1] - ts[i]) for i in range(len(ts) - 1)])])
    pulse = lambda t: 0.5 + 0.5 * math.cos(float(np.interp(t, ts, ph)))  # noqa: E731
    after = (lambda t: 1 - smooth(t, T_f, T_f + 0.35)) if full else (lambda t: 1.0)  # noqa: E731   the overload drains it

    b_col = c.bone("column", x=bx, y=by)
    s_fill = _s(c, b_col, "shine_band", W * 2.2, height=Hm, anchor="bottom")      # the wide coloured body of light
    s_col = _s(c, b_col, "shine_band", W * 0.8, height=Hm, anchor="bottom")       # its hot core
    b_bg = c.bone("base_glow", x=bx, y=by)
    s_bg = _s(c, b_bg, "glow_soft", W * 2.4)
    b_sf = c.bone("surface")
    s_sf = _s(c, b_sf, "light_streak", W * 2.0, height=W * 0.7)
    cracks = []
    for k, th in enumerate(CHARGE_CRACKS):
        if th > level + 1e-9:
            continue
        side = 1 if k % 2 == 0 else -1                       # each crack splits outward from the column's edge
        b = c.bone(f"crack{k}", x=bx + side * 0.3 * W, y=by + Hm * float(rng.uniform(0.35, max(0.4, th - 0.05))),
                   rot=(0.0 if side > 0 else 180.0) + float(rng.uniform(-35, 35)))
        cracks.append((b, _s(c, b, "crack", W * float(rng.uniform(1.3, 1.6)), anchor="left"), th))
    over = []
    if full:
        cy = by + Hm * 0.6
        for nm, pic, wd in (("ob_glow", "glow_core", W * 3.4), ("ob_rays", "rays", W * 4.4), ("ob_ring", "ring", W * 2.6),
                            ("ob_flash", "flash_burst", W * 2.6)):
            b = c.bone(nm, x=bx, y=cy)
            over.append((b, _s(c, b, pic, wd)))

    c.show([s_fill, s_col, s_bg, s_sf], 0, T_f + 0.4 if full else None)
    on = lambda t: min(1.0, L(t) * 8)  # noqa: E731
    c.bone_keys(b_col, "scale", ts, lambda t: (0.85 + 0.15 * pulse(t) * on(t), max(0.0, L(t))))
    c.color_keys(s_fill, ts, lambda t: _h(c, col, (0.45 + 0.35 * pulse(t)) * on(t) * after(t)))
    c.color_keys(s_col, ts, lambda t: _h(c, hot, (0.5 + 0.4 * pulse(t)) * on(t) * after(t)))
    c.bone_keys(b_sf, "translate", ts, lambda t: (bx, by + L(t) * Hm))
    c.bone_keys(b_sf, "scale", ts, lambda t: (0.8 + 0.25 * pulse(t), 1.0))
    c.color_keys(s_sf, ts, lambda t: _h(c, "FFFFFF", (0.55 + 0.45 * pulse(t)) * on(t) * after(t)))
    c.bone_keys(b_bg, "translate", ts, lambda t: (bx, by + 0.5 * L(t) * Hm))
    c.bone_keys(b_bg, "scale", ts, lambda t: (0.7 + 0.3 * L(t), 0.5 + 1.3 * L(t)))
    c.color_keys(s_bg, ts, lambda t: _h(c, col, (0.2 + 0.45 * L(t) * (0.6 + 0.4 * pulse(t))) * smooth(t, 0, 0.15) * after(t)))
    for b, s, th in cracks:
        t_on = T_f * ((th / level) ** (1 / CHARGE_EASE) if full else 0.5 - math.sin(math.asin(1 - 2 * min(1.0, th / level)) / 3))
        tc = [t for t in ts if t >= t_on] or [t_on]
        tc = sorted(set(tc) | {t_on})
        c.show([s], t_on, T_f + 0.3 if full else None)
        c.bone_keys(b, "scale", tc, lambda t, t_on=t_on: (0.15 + 0.85 * ease_out((t - t_on) / CHARGE_OPEN, 2.0), 1.0))
        c.color_keys(s, tc, lambda t, t_on=t_on: _h(c, hot, smooth(t, t_on, t_on + 0.03) * (0.45 + 0.55 * pulse(t))
                                                         * (1 - smooth(t, T_f + 0.05, T_f + 0.3) if full else 1.0)))
    if full:
        to = times_dense(T_f - 0.02, D, FPS)
        c.show([s for _, s in over], T_f - 0.02, D)
        decay = dict(ob_glow=0.3, ob_rays=0.35, ob_ring=0.3, ob_flash=0.09)
        for (b, s), nm in zip(over, ("ob_glow", "ob_rays", "ob_ring", "ob_flash")):
            tau = decay[nm]
            c.color_keys(s, to, lambda t, tau=tau, nm=nm: _h(c, "FFFFFF" if nm == "ob_flash" else col,
                                                              smooth(t, T_f - 0.02, T_f) * math.exp(-max(0.0, t - T_f) / tau)
                                                              * (1 - smooth(t, D - 0.15, D))))
            if nm == "ob_ring":
                c.bone_keys(b, "scale", to, lambda t: (0.3 + 1.6 * ease_out((t - T_f) / 0.5, 2.5),) * 2)
            elif nm == "ob_rays":
                c.bone_keys(b, "scale", to, lambda t: (0.4 + 0.8 * ease_out((t - T_f) / 0.25),) * 2)
                c.bone_keys(b, "rotate", to, lambda t: -60.0 * (t - T_f))
            else:
                c.bone_keys(b, "scale", to, lambda t: (0.5 + 0.7 * ease_out((t - T_f) / 0.12),) * 2)
    # the prop throbs with the pulse (stronger as it fills) and jolts at the overload
    car = _drive_scale(c, prop, "proppulse", pivot, ts, lambda t: (
        1 + 0.035 * L(t) * (2 * pulse(t) - 1) * after(t) + (0.14 * _kick(t - T_f, 3.5, 0.15) if full else 0.0),) * 2)
    c.ab.event(c.T(T_f), "prop_charged")
    return _finish(c, P, duration=D, charged_at=c.T(T_f), carrier=car, prop_bone=prop, own_prop=own,
                   loop=(None if full else D))


# ================================================================ gem_glint
def gem_glint(c: Ctx, P: dict) -> dict:
    D = float(P["duration"])
    W, Hs = (float(v) for v in P["size"])
    slant, sweep = float(P["slant"]), float(P["sweep"])
    gx, gy = (float(v) for v in P["glint"])
    n_tw = int(P["twinkles"])
    if sweep <= 0 or W <= 0 or Hs <= 0:
        raise ValueError("sweep and size must be > 0")
    if P["sync_tilt"]:
        D = max(1, round(D / GEM_IDLE)) * GEM_IDLE             # a whole number of prop_idle loops: both stay in step
        t_c = GEM_TILT_U * GEM_IDLE                            # the band crosses the centre at the tilt's peak
    else:
        t_c = 0.15 * D + sweep / 2
    if sweep > D * 0.8:
        raise ValueError(f"sweep {sweep:g}s does not fit the loop ({D:g}s)")
    col = _hexn(P["color"], "EAF6FF")
    rng = np.random.default_rng(c.seed + 1031)
    name = _bone_opt(c, P, "prop")
    if name:
        _mount(c, name, ride=True)                             # the shine rides the prop (prop_idle's tilt and swell)

    def wrap(t, at):
        """Signed time from `at`, wrapped into [-D/2, D/2); t = D gives exactly what t = 0 gives (the loop closes)."""
        t = 0.0 if t >= D - 1e-9 else t
        return ((t - at + D / 2) % D) - D / 2

    b_band, b_thin = c.bone("band", rot=slant), c.bone("band_thin", rot=slant)
    s_band = _s(c, b_band, "shine_band", W * 0.3, height=Hs)
    s_thin = _s(c, b_thin, "shine_band", W * 0.09, height=Hs)
    tw = []
    for i in range(n_tw):
        a, rr = float(rng.uniform(0, 2 * math.pi)), math.sqrt(float(rng.uniform(0.05, 1.0)))
        b = c.bone(f"tw{i}", x=math.cos(a) * rr * 0.4 * W, y=math.sin(a) * rr * 0.4 * Hs)
        tw.append((b, _s(c, b, "flare_star", W * float(rng.uniform(0.3, 0.45))), (i + float(rng.uniform(0.15, 0.85))) / max(1, n_tw) * D))
    b_gs, b_gf, b_gc = c.bone("glint_streak", x=gx, y=gy), c.bone("glint_star", x=gx, y=gy), c.bone("glint_core", x=gx, y=gy)
    s_gs = _s(c, b_gs, "light_streak", W * 1.1, height=W * 0.14)
    s_gf = _s(c, b_gf, "flare_star", W * 0.7)
    s_gc = _s(c, b_gc, "glow_core", W * 0.55)
    t_g = float(P["glint_at"]) % 1.0 * D

    # the bands are chords of the prop's ellipse (half-axes ea, eb): each is cut to the silhouette and centred on its
    # chord, so a slanted band never pokes out of the prop (a clipped look without a clipping mask)
    ea, eb = GEM_REACH * W, GEM_REACH * Hs
    th = math.radians(slant)
    dx, dy = -math.sin(th), math.cos(th)                     # the band's long axis
    qa_ = dx * dx / ea ** 2 + dy * dy / eb ** 2
    x_max = ea * eb * math.sqrt(qa_) / max(abs(dy), 1e-6)    # beyond this a line in that direction misses the ellipse

    def band(t, lead=0.0):
        """(centre x, centre y, length factor, alpha) of a band `lead` x W ahead of the sweep."""
        u = wrap(t, t_c) / sweep + 0.5
        uu = min(max(u, 0.0), 1.0)
        x = -x_max + 2 * x_max * (0.5 - 0.5 * math.cos(math.pi * uu)) + lead * W
        qb, qc = 2 * x * dx / ea ** 2, x * x / ea ** 2 - 1
        disc = qb * qb - 4 * qa_ * qc
        if disc <= 0 or not 0 < u < 1:
            return x, 0.0, 0.05, 0.0
        sm, ln = -qb / (2 * qa_), math.sqrt(disc) / qa_
        full = 2 / math.sqrt(qa_)                            # the longest chord (through the centre)
        return x + sm * dx, sm * dy, max(0.05, ln / Hs), (ln / full) ** 0.6 * smooth(u, 0.0, 0.1) * (1 - smooth(u, 0.9, 1.0))

    def glint(t):
        tau = wrap(t, t_g)
        return smooth(tau, -GEM_GLINT_RISE, 0.0) * math.exp(-max(0.0, tau) / GEM_GLINT_DECAY), tau

    ts = times_dense(0, D, FPS)
    c.show([s_band, s_thin] + [s for _, s, _ in tw] + [s_gs, s_gf, s_gc], 0, None)
    for bn, sl, lead, gain, tint in ((b_band, s_band, 0.0, 0.75, col), (b_thin, s_thin, 0.2, 0.9, "FFFFFF")):
        c.bone_keys(bn, "translate", ts, lambda t, lead=lead: band(t, lead)[:2])
        c.bone_keys(bn, "scale", ts, lambda t, lead=lead: (1.0, band(t, lead)[2]))
        c.color_keys(sl, ts, lambda t, lead=lead, gain=gain, tint=tint: _h(c, tint, gain * band(t, lead)[3]))
    for b, s, t_i in tw:
        def tw_v(t, t_i=t_i):
            tau = wrap(t, t_i)
            return math.sin(math.pi * tau / GEM_TWINKLE) ** 0.8 if 0 < tau < GEM_TWINKLE else 0.0, tau
        c.bone_keys(b, "scale", ts, lambda t, f=tw_v: (f(t)[0],) * 2)
        c.bone_keys(b, "rotate", ts, lambda t, f=tw_v: 90.0 * min(max(f(t)[1], 0.0), GEM_TWINKLE) / GEM_TWINKLE)
        c.color_keys(s, ts, lambda t, f=tw_v: _h(c, "FFFFFF", f(t)[0]))
    c.bone_keys(b_gs, "scale", ts, lambda t: (0.2 + 1.0 * glint(t)[0], 1.0))
    c.color_keys(s_gs, ts, lambda t: _h(c, col, glint(t)[0]))
    c.bone_keys(b_gf, "scale", ts, lambda t: (0.3 + 0.9 * glint(t)[0],) * 2)
    c.bone_keys(b_gf, "rotate", ts, lambda t: 45.0 * glint(t)[0])
    c.color_keys(s_gf, ts, lambda t: _h(c, "FFFFFF", glint(t)[0]))
    c.color_keys(s_gc, ts, lambda t: _h(c, col, 0.9 * glint(t)[0]))
    res = dict(duration=D, loop=D, sweep_center=t_c, glint_at=t_g)
    if P["clip"]:                                            # a real mask: the bands and stars stay inside the prop
        clip = P["clip"]
        if isinstance(clip, (int, float)):
            verts = []
            for i in range(16):
                a = 2 * math.pi * i / 16
                verts += [round(float(clip) * math.cos(a), 2), round(float(clip) * math.sin(a), 2)]
        else:
            verts = [round(float(v), 2) for pt in clip for v in pt]
        nm = c.sk.unique_name(f"fx_clip_{c.prefix}", "slot")
        c.sk.add_slot(Slot(name=nm, bone=c.group, attachment=nm), before=s_band)
        c.sk.set_attachment(nm, nm, ClippingAttachment(end=c.slots[-1], vertexCount=len(verts) // 2, vertices=verts))
        res["clip_slot"] = nm
    return _finish(c, P, **res)


# ================================================================ registry
def _o(**kw) -> dict:
    return {**kw, **_GT}


_PROP = ("", "the prop's bone (empty: a bone of the recipe's own; parent your art to it). The anchor moves onto it")
_PIVOT = (None, "[x, y] world pivot of the squash (default: the bone's origin; rig the prop bone at its base)")

RECIPES.update({
    "prop_absorb": dict(
        fn=prop_absorb, duration=1.89, kind="one-shot", color=GOLD, normal_blend=True,
        summary="The prop sucks items in: each (coin or glow orb) pops up at its source and spirals into the mouth on an "
                "accelerating path (starts at rest, ease in), shrinking, a speed streak behind it; the prop gulps (squash pulse "
                "through a carrier) on EVERY arrival, the last one bigger, the mouth flashes, a ring on the last. Event "
                "prop_absorb_hit (int = item) per arrival.",
        anchor="The prop bone's origin (prop=) or x, y; sources and `at` are relative to it.",
        options=_o(prop=_PROP, pivot=_PIVOT,
                   sources=([[-260.0, 180.0], [250.0, 140.0], [-300.0, -20.0], [290.0, 40.0], [-120.0, 290.0], [140.0, 300.0]],
                            "[[x, y], ...] where the items start, in arrival order"),
                   at=([0.0, 0.0], "[x, y] the mouth"), item=("coin", "coin (normal blend) | orb (additive glow)"),
                   stagger=(0.12, "seconds between items"), flight=(ABSORB_FLIGHT, "seconds from source to mouth"),
                   swirl=(120.0, "degrees each item winds round the mouth (sign = direction)"), size=(64.0, "item size"),
                   thump=(0.09, "the prop's squash per arrival (0.09 = 9 %)"))),
    "prop_overflow": dict(
        fn=prop_overflow, duration=2.99, kind="one-shot", color=GOLD, count=18, normal_blend=True,
        summary="Coins pile up and spill over the rim: they pop out of the opening on true parabolas (gravity); the first fall "
                "back onto a growing heap, the next clear the rim, hit the floor, hop once (restitution) and skid to rest, the "
                "last few land on the rim and spin down (scaleX = cos) until they lie face-on. Glints on the landings, a glow at "
                "the rim. Coins one normal run, lights one additive run. Event prop_overflow (first coin over the rim).",
        anchor="The prop bone's origin (prop=) or x, y; rim and floor are relative to it.",
        options=_o(prop=("", "the prop's bone: only anchors the effect (nothing of yours is keyed)"),
                   rim=([0.0, 90.0, 200.0], "[x, y, width] the opening (y = its lip)"),
                   floor=(None, "y of the floor the spill lands on (default rim y - 260)"),
                   edge=(3, "coins that end on the rim, spinning down"), size=(56.0, "coin size"))),
    "counter_plate": dict(
        fn=counter_plate, duration=1.68, kind="one-shot", color="FFE08A", normal_blend=True,
        summary="A number plate ticks up: `steps` punches (scale kick through a carrier), each tick sooner than the last, a glint "
                "on each, the shake growing with the value; the last tick is a big slow punch with flash, glow and ring. Events "
                "counter_tick (int = value step 1..steps), counter_done. Change the digits at counter_tick.",
        anchor="The plate bone's origin (plate=) or x, y.",
        options=_o(plate=("", "the plate's bone (empty: our own plate picture, art role plate)"),
                   steps=(8, "number of ticks"), size=([260.0, 110.0], "[w, h] of the plate"),
                   punch=(0.1, "scale kick per tick (grows 60 % toward the last)"), final=(0.32, "the last tick's punch"),
                   shake=(6.0, "shake amplitude at the last tick (units); it grows from 1/steps of it"))),
    "prop_multiplier_slam": dict(
        fn=prop_multiplier_slam, duration=1.49, kind="one-shot", color="FFB347", normal_blend=True,
        summary="The prop crouches, leaps (stretch), hangs at the apex, slams down accelerating (faster than gravity), squashes "
                "on impact and springs back; a flat shockwave ring, dust puffs that decelerate (drag), a flash, then an 'xN' "
                "stamp falls in from 2.3x, hits and punches with overshoot, a glint on it. Drives prop= through carriers. Event "
                "prop_slam (impact).",
        anchor="The prop bone's origin (prop=) or x, y; ground and stamp are relative to it.",
        options=_o(prop=_PROP, pivot=_PIVOT, height=(150.0, "leap height"), ground=(0.0, "y of the ground (ring, dust)"),
                   stamp=([0.0, 150.0], "[x, y] where the stamp lands"), stamp_size=(150.0, "stamp width"),
                   ring=(220.0, "shockwave size"), dust=("D9C7A6", "dust colour"))),
    "prop_charge": dict(
        fn=prop_charge, duration=2.4, kind="window", color="4FE3FF",
        summary="A meter on the prop fills with light from the bottom up (a column rising within `height`, a bright surface "
                "line, a glow), accelerating; cracks of light split open as it nears full; a pulse quickens with the fill (the "
                "prop throbs with it through a carrier); then it overloads: flash, ring, rays, the prop jolts, the meter drains. "
                "level < 1 fills to that level, stops and breathes. Event prop_charged.",
        anchor="The prop bone's origin (prop=, the meter rides the prop) or x, y; base is relative to it.",
        options=_o(prop=_PROP, pivot=_PIVOT, base=([0.0, -120.0], "[x, y] bottom of the meter"),
                   height=(240.0, "meter height"), width=(110.0, "meter width"),
                   level=(1.0, "0..1: fill to this level; 1 = full and overload"), fill=(1.3, "seconds for a full fill"))),
    "gem_glint": dict(
        fn=gem_glint, duration=round(3 * GEM_IDLE, 3), kind="loop", color="EAF6FF",
        summary="A gem / glossy prop catching the light, seamless loop: a narrow slanted light band (with a thin second one) "
                "sweeps across, star twinkles pop on facets, a periodic hard glint (streak + star + core, up in one frame). "
                "Default length = 3 prop_idle loops; sync_tilt puts the sweep on prop_idle's tilt peak. clip= adds a real mask.",
        anchor="The prop bone's origin (prop=, the shine rides the prop) or x, y; glint is relative to it.",
        options=_o(prop=("", "the prop's bone: the shine rides it (nothing of yours is keyed)"),
                   size=([220.0, 240.0], "[w, h] of the shiny area"), slant=(-30.0, "band angle, degrees"),
                   sweep=(0.55, "seconds the band takes to cross"), glint=([-55.0, 60.0], "[x, y] of the hard glint"),
                   glint_at=(0.72, "0..1 of the loop: when the hard glint fires"), twinkles=(5, "star twinkles per loop"),
                   sync_tilt=(False, "time the sweep to prop_idle's tilt peak (u 0.45 of 0.755 s); the loop becomes whole idle loops"),
                   clip=(0.0, "radius or [[x, y], ...] polygon (group space): clip the shine to the prop; 0 = none"))),
})

_ROLE = {**PIC_ROLES, **OWN_ROLES}
ROLES.update({
    "prop_absorb": {k: _ROLE[k] for k in ("coin", "glow_core", "spark", "glow_soft", "flare_star", "ring")},
    "prop_overflow": {k: _ROLE[k] for k in ("coin", "glow_soft", "flare_star")},
    "counter_plate": {k: _ROLE[k] for k in ("plate", "flare_star", "glow_soft", "flash_burst", "ring")},
    "prop_multiplier_slam": {k: _ROLE[k] for k in ("smoke_puff", "stamp", "ring", "glow_soft", "flash_burst", "flare_star")},
    "prop_charge": {k: _ROLE[k] for k in ("shine_band", "glow_soft", "light_streak", "crack", "glow_core", "rays", "ring", "flash_burst")},
    "gem_glint": {k: _ROLE[k] for k in ("shine_band", "flare_star", "light_streak", "glow_core")},
})
COLLECT_RECIPES = ("prop_absorb", "prop_overflow", "counter_plate", "prop_multiplier_slam", "prop_charge", "gem_glint")
for _n in COLLECT_RECIPES:
    RECIPES[_n]["roles"] = ROLES[_n]
