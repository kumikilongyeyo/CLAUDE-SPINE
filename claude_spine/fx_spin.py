"""Spin moments for ``fx_recipe``: ``near_miss``, ``spin_blur``, ``turbo_spin`` and ``screen_shake``, the FX around a spin
that complement ``reel_stop`` and ``anticipation_reel`` (fx_reels.py).

Same rules as fx_recipes.py (procedural textures, one group bone per recipe, closed-form keys, ``art=`` roles, additive
blend). Like fx_reels, the recipes that MOVE the game's bones (turbo_spin's grid ripple, screen_shake) never key a bone
the artist owns: they drive pure-translation carrier bones inserted above it (``fx_reels._carrier``), and add onto keys
an earlier recipe left on the same carrier in the same clip (``fx_reels._merge_keys``), so a screen_shake on top of three
reel_stop shakes sums with them.

Exaggerated real physics:

* ``near_miss``: the symbol brakes toward the payline with constant deceleration, y = miss + (dy - miss)(1 - t/tc)^2,
  and its halo brightens like a light source coming closer: I = (L^2 + miss^2) / (L^2 + d^2) (inverse square with a
  softening length L = miss/2, exactly 1 at the closest point). The ring and the core breathe faster as it nears (pulse
  frequency follows I). At the fizzle the halo IMPLODES: ring and glow contract with ease-in r = r0 (1 - v^2) (sucked
  in, accelerating), the ring spins up as it shrinks (angular momentum: w ~ 1/r^2), motes are dragged inward and
  stretched along their speed, the colour drains to grey, and at the centre a tiny dim pop throws a puff of sparks that
  fall on exact gravity parabolas.
* ``spin_blur``: blur streaks over a spinning reel. The reel speed is a motor ramp (spin-up), a cruise, and a constant-
  deceleration brake to 0 at ``stop``. The streaks follow the reel through a first-order lag, s' = (v - s) / lag
  (integrated exactly for piecewise-linear input), so they trail during the spin and CATCH UP after the stop: they keep
  sliding by lag * s(stop) while s decays e^(-t/lag). Length = speed x shutter (motion blur is exposure x velocity),
  opacity follows the speed. Rows of each streak are clamped to the reel window, so a streak slides in under the top
  edge and out under the bottom one; wraps hide inside alpha 0. ``mode=loop`` is a cruise segment that closes exactly.
* ``turbo_spin``: speed lines framing the reels, each with its own speed, stretched to speed x shutter; the speed ramps
  in and out. A travelling wave runs through the symbol grid: psi(p, t) = A e^(-p/reach) e^(-s/ring) sin(2 pi f s),
  s = t - p/c (phase velocity c, amplitude decaying with distance travelled and ringing down at each point). It drives
  carrier bones above the symbol bones you name (``bones=``), or its own grid of bones, with a light riding the crest.
* ``screen_shake``: a kicked damped spring on two axes, x and y = A e^(-k t) sin(2 pi f t), with the x frequency
  ``ratio`` times y (the golden ratio by default: incommensurate, so the path never closes into a clean figure); the
  slam pushes DOWN first. A white flash with a 1/t tail, and a chromatic split: red and cyan glows that start apart and
  converge like a critically damped spring, d = d0 (1 + w t) e^(-w t) (no overshoot), adding up to white as they meet.

Registered into fx_recipes.RECIPES / ROLES at import (fx_recipes must import this module at its end).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from .fx import _rgba
from .fx_recipes import (Ctx, RECIPES, ROLES, _grid, _hexn, _mix, _rgb, ease_out, hexa, smooth, smooth_arr,
                         tex_rune_ring, times_dense)
from .fx_reels import _carrier, _merge_keys

GOLDEN = (1 + 5 ** 0.5) / 2


# ------------------------------------------------------------------ textures (white; tinted per slot)
def tex_spin_streak(w: int = 48, h: int = 256) -> Image.Image:
    """A motion-blur streak: a box-blurred highlight, i.e. a plateau along its length with soft ramps at both ends,
    a thin bright core across with a soft halo."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = y / (h - 1)
    across = np.exp(-(xn / 0.2) ** 2) + 0.3 * np.exp(-(xn / 0.55) ** 2)
    along = smooth_arr(yn, 0.0, 0.32) * smooth_arr(1 - yn, 0.0, 0.32)
    a = across * along * np.clip((1 - np.abs(xn)) / 0.1, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(0.85 * a, 0, 1))


def tex_spin_line(w: int = 32, h: int = 256) -> Image.Image:
    """A speed line for downward motion: bright head at the BOTTOM, a tail thinning and fading upward."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    v = y / (h - 1)                                       # 0 = top (tail end), 1 = bottom (head)
    width = 0.14 + 0.32 * v
    a = (np.exp(-(xn / (width * 0.4)) ** 2) + 0.3 * np.exp(-(xn / width) ** 2)) * v ** 1.6 * smooth_arr(1 - v, 0.0, 0.05)
    a *= np.clip((1 - np.abs(xn)) / 0.1, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def tex_spin_disc(n: int = 192) -> Image.Image:
    """A flash disc with a firmer edge than fx/glow (a flatter top), so two offset copies show coloured fringes."""
    x, y = _grid(n)
    d = np.hypot(x, y)
    a = 0.8 * np.exp(-(d / 0.6) ** 4) + 0.2 * np.exp(-(d / 0.28) ** 2)
    a *= np.clip((1 - d) / 0.06, 0, 1)
    return _rgba(np.ones((n, n)), np.clip(a, 0, 1))


TEX = {"fx/spin_streak": tex_spin_streak, "fx/spin_line": tex_spin_line, "fx/spin_disc": tex_spin_disc}


# ------------------------------------------------------------------ helpers
def _window(c: Ctx, slot: str, u0: float, u1: float) -> None:
    """Show `slot` from u0 to u1 only."""
    pts = [(0.0, None), (c.T(u0), "fx")] if c.T(u0) > 0 else [(0.0, "fx")]
    c.ab.slot_attachment(slot, pts + [(c.T(u1), None)])


def _grey(col: str, k: float = 0.72) -> tuple:
    r_, g_, b_ = _rgb(col)
    y = (0.299 * r_ + 0.587 * g_ + 0.114 * b_) * k
    return (y, y, y)


def _hex(rgb: tuple) -> str:
    return "%02X%02X%02X" % tuple(int(round(max(0.0, min(255.0, v)))) for v in rgb)


def _cumtrapz(t: np.ndarray, f: np.ndarray) -> np.ndarray:
    out = np.zeros_like(f)
    out[1:] = np.cumsum(0.5 * (f[1:] + f[:-1]) * np.diff(t))
    return out


def _lag(t: np.ndarray, v: np.ndarray, tau: float) -> np.ndarray:
    """First-order lag s' = (v - s) / tau, integrated EXACTLY for v linear between the samples (first-order hold)."""
    s = np.empty_like(v)
    s[0] = v[0]
    for n in range(len(t) - 1):
        dt = t[n + 1] - t[n]
        a = (v[n + 1] - v[n]) / dt
        s[n + 1] = v[n + 1] - a * tau + (s[n] - v[n] + a * tau) * math.exp(-dt / tau)
    return s


def _wraps(X: np.ndarray, t: np.ndarray, period: float, phase: float, lo: float, hi: float) -> list[float]:
    """Times at which X(t)/period + phase crosses an integer (a looping streak respawns), inside (lo, hi)."""
    q = X / period + phase
    out = []
    for m in range(int(math.floor(q[0])) + 1, int(math.floor(q[-1])) + 1):
        k = int(np.searchsorted(q, m))
        if 0 < k < len(q):
            f = (m - q[k - 1]) / max(q[k] - q[k - 1], 1e-12)
            tw = float(t[k - 1] + f * (t[k] - t[k - 1]))
            if lo < tw < hi:
                out.append(tw)
    return out


def _with_wraps(ts: list[float], wraps: list[float], eps: float = 0.001) -> list[float]:
    s = set(ts)
    for w in wraps:
        s.update([w - eps, w + eps])
    return sorted(s)


# ------------------------------------------------------------------ near_miss
def near_miss(c: Ctx, P: dict) -> dict:
    """A scatter's halo brightens as it brakes toward the payline, hangs there hopefully, then collapses with a sad
    little implosion (ring and glow sucked inward, colour drains to grey, a puff of sparks falls)."""
    col = _hexn(P["color"], "FFD54A")
    size = float(P["size"])
    dy, miss = float(P["dy"]), float(P["miss"])
    tc, tf = float(P["closest"]), float(P["fizzle"])
    if dy == 0 or miss == 0 or (dy > 0) != (miss > 0) or abs(miss) >= abs(dy):
        raise ValueError("dy (start) and miss (rest) are offsets from the payline on the same side, with |miss| < |dy| "
                         "(miss = 0 would be a hit, not a near miss)")
    if tc <= 0:
        raise ValueError("closest must be > 0 seconds")
    if tf < tc:
        raise ValueError("fizzle must be at or after closest (the hope dies after the symbol stops)")
    TC = 0.32                                            # collapse time
    ti = tf + TC                                         # implosion
    D = ti + 0.9
    n = int(P["count"])
    rng = np.random.default_rng(c.seed + 301)
    col_rgb, grey = _rgb(col), _grey(col)
    L = 0.5 * abs(miss)

    def ypath(u):
        return miss + (dy - miss) * (1 - np.minimum(u, tc) / tc) ** 2

    def I(u):
        d = ypath(u)
        return (L * L + miss * miss) / (L * L + d * d)

    g = np.linspace(0, D, 2001)                          # pulse phase: frequency 2 Hz far away, 8 Hz on the line
    phase = 2 * math.pi * _cumtrapz(g, 2.0 + 6.0 * I(g))
    pulse = lambda u: 0.5 + 0.5 * math.sin(float(np.interp(u, g, phase)))  # noqa: E731
    v_ = lambda u: min(1.0, max(0.0, (u - tf) / TC))  # noqa: E731   collapse progress
    shrink = lambda u: max(0.04, 1 - v_(u) ** 2)  # noqa: E731   ease-in contraction
    att = lambda u: smooth(u, 0, 0.08)  # noqa: E731
    tint = lambda u, k=1.0: _hex(_mix(col_rgb, grey, min(1.0, k * v_(u))))  # noqa: E731

    grp = c.bone("miss", c.group, 0, 0)
    halo = c.bone("halo", grp, 0, 0)
    b_glow, b_ring, b_core = c.bone("glow", halo), c.bone("ring", halo), c.bone("core", halo)
    s_glow = c.slot(b_glow, "fx/glow", size * 1.7, role="halo")
    s_ring = c.slot(b_ring, f"fx/rune_ring_{col}", size * 1.15, make=lambda: tex_rune_ring(col), role="ring")
    s_core = c.slot(b_core, "fx/glow", size * 0.75, role="core")
    motes = []
    for i in range(6):
        ang = 2 * math.pi * (i + float(rng.uniform(-0.25, 0.25))) / 6
        bn = c.bone(f"m{i}", halo, 0, 0, rot=math.degrees(ang))
        sl = c.slot(bn, "fx/mote", size * float(rng.uniform(0.12, 0.18)), ox=0.0, role="mote")
        motes.append(dict(b=bn, s=sl, ang=ang, R=size * float(rng.uniform(0.75, 0.95))))
    b_pop = c.bone("pop", halo)
    s_pop = c.slot(b_pop, "fx/glow", size * 0.8, role="pop")
    sparks = []
    for i in range(n):
        th = math.radians(float(rng.uniform(25, 155)))
        sp = size / 170 * float(rng.uniform(170, 290))
        bn = c.bone(f"sp{i}", halo)
        sl = c.slot(bn, "fx/spark", size * float(rng.uniform(0.13, 0.2)), role="spark")
        sparks.append(dict(b=bn, s=sl, vx=sp * math.cos(th), vy=sp * math.sin(th), rot=float(rng.uniform(-200, 200)),
                           life=float(rng.uniform(0.65, 0.88))))
    gravity = 1500.0 * size / 170

    ts = sorted(set(times_dense(0, D, 60)) | {tc, tf, ti})
    c.show([s_glow, s_ring, s_core], 0, ti + 0.02)
    if P["follow"]:
        c.bone_keys(halo, "translate", ts, lambda u: (0.0, float(ypath(u))))
    # halo: brightness is the approach law itself (the test reads it back); sucked inward at the fizzle
    c.color_keys(s_glow, ts, lambda u: hexa(tint(u), c.a(0.45 * att(u) * float(I(u)) * (1 - v_(u)) ** 0.6)))
    c.bone_keys(b_glow, "scale", ts, lambda u: ((0.75 + 0.25 * float(I(u))) * shrink(u),) * 2)
    # the ring breathes (faster as it nears), then contracts with ease-in and spins up (w ~ 1/r^2)
    w0 = float(P["spin"])
    gr = np.array(ts)
    sh = np.array([shrink(u) for u in gr])
    ang = _cumtrapz(gr, w0 / np.maximum(sh, 0.2) ** 2)
    c.bone_keys(b_ring, "rotate", ts, lambda u: -float(np.interp(u, gr, ang)))
    c.bone_keys(b_ring, "scale", ts, lambda u: ((0.88 + 0.08 * float(I(u)) + 0.05 * float(I(u)) * pulse(u)) * shrink(u),) * 2)
    c.color_keys(s_ring, ts, lambda u: hexa(tint(u), c.a(att(u) * (0.03 + 0.8 * float(I(u)) ** 1.5) * (1 - v_(u) ** 3))))
    c.bone_keys(b_core, "scale", ts, lambda u: ((0.6 + 0.4 * float(I(u)) * (0.8 + 0.2 * pulse(u))) * shrink(u),) * 2)
    c.color_keys(s_core, ts, lambda u: hexa(_hex(_mix(_mix(col_rgb, (255, 255, 255), 0.6), grey, v_(u))),
                                            c.a(att(u) * 0.45 * float(I(u)) ** 1.5 * (0.7 + 0.3 * pulse(u)) * (1 - v_(u)))))
    # motes dragged inward with the ring, stretched along their speed (they point at the centre)
    tm = times_dense(tf, ti, 60)
    for m in motes:
        _window(c, m["s"], tf, ti)
        c.bone_keys(m["b"], "translate", tm, lambda u, m=m: (math.cos(m["ang"]) * m["R"] * (1 - v_(u) ** 2),
                                                             math.sin(m["ang"]) * m["R"] * (1 - v_(u) ** 2)))
        c.bone_keys(m["b"], "scale", tm, lambda u: (1 + 2.6 * v_(u), max(0.3, 1 - 0.6 * v_(u))))
        c.color_keys(m["s"], tm, lambda u: hexa(tint(u, 0.8), c.a(0.85 * math.sin(math.pi * v_(u)) ** 0.7)))
    # the sad little pop at the centre: tiny, dim, already grey, a 1/t flash
    tp = times_dense(ti, ti + 0.35, 60)
    _window(c, s_pop, ti, ti + 0.35)
    c.color_keys(s_pop, tp, lambda u: hexa(_hex(_mix(grey, (255, 255, 255), 0.25)),
                                           c.a(0.7 * smooth(u, ti, ti + 0.02) / (1 + 30 * max(0.0, u - ti - 0.02))
                                               * (1 - smooth(u, ti + 0.2, ti + 0.35)))))
    c.bone_keys(b_pop, "scale", tp, lambda u: (0.4 + 0.6 * ease_out((u - ti) / 0.2, 2.5),) * 2)
    # a puff of sparks that falls on exact parabolas
    for sp in sparks:
        t1 = min(D, ti + sp["life"])
        tsp = times_dense(ti, t1, 60)
        _window(c, sp["s"], ti, t1)
        c.bone_keys(sp["b"], "translate", tsp, lambda u, sp=sp: (sp["vx"] * (u - ti),
                                                                 sp["vy"] * (u - ti) - 0.5 * gravity * (u - ti) ** 2))
        c.bone_keys(sp["b"], "rotate", tsp, lambda u, sp=sp: sp["rot"] * (u - ti))
        c.bone_keys(sp["b"], "scale", tsp, lambda u, sp=sp, t1=t1: (max(0.05, 1 - 0.6 * (u - ti) / (t1 - ti)),) * 2)
        c.color_keys(sp["s"], tsp, lambda u, t1=t1: hexa(_hex(_mix(_mix(col_rgb, grey, 0.45), grey, (u - ti) / (t1 - ti))),
                                                         c.a(0.9 * smooth(u, ti, ti + 0.02) * (1 - (u - ti) / (t1 - ti)) ** 0.8)))
    c.ab.event(c.T(tc), "fx_near_miss_closest")
    c.ab.event(c.T(tf), "fx_near_miss_fizzle")
    return c.result(duration=D * c.k, closest_at=c.T(tc), fizzle_at=c.T(tf), implode_at=c.T(ti), sparks=n, halo_bone=halo,
                    gravity=gravity)


# ------------------------------------------------------------------ spin_blur
def _reel_speed(t: np.ndarray, vmax: float, up: float, stop: float, brake: float) -> np.ndarray:
    """Motor ramp (smoothstep) to vmax over `up`, cruise, constant deceleration to 0 at `stop`, then 0."""
    v = vmax * smooth_arr(t, 0.0, up)
    return np.where(t > stop - brake, vmax * np.clip((stop - t) / brake, 0, 1), v)


def spin_blur(c: Ctx, P: dict) -> dict:
    """Motion-blur streaks over a spinning reel that trail it (first-order lag), stretch with speed and catch up and
    fade when it stops. mode=loop: a cruise segment that loops exactly."""
    mode = str(P["mode"])
    if mode not in ("spin", "loop"):
        raise ValueError(f"mode must be spin | loop, got {mode!r}")
    direction = str(P["direction"])
    if direction not in ("down", "up"):
        raise ValueError(f"direction must be down | up, got {direction!r}")
    sgn = -1.0 if direction == "down" else 1.0
    col = _hexn(P["color"], "FFFFFF")
    W, H = float(P["width"]), float(P["height"])
    vmax, tau, shutter = float(P["speed"]), float(P["lag"]), float(P["shutter"])
    up, brake = float(P["spinup"]), float(P["brake"])
    if vmax <= 0 or tau <= 0 or shutter < 0:
        raise ValueError("speed and lag must be > 0, shutter >= 0")
    n = int(P["count"])
    if n < 1:
        raise ValueError("count (streaks) must be >= 1")
    Pd = 1.5 * H                                          # respawn period: a streak is fully outside the window at the wrap
    Lmax, L0 = 0.5 * H, 6.0
    tail = max(0.3, 6 * tau)
    if mode == "spin":
        stop = float(P["stop"]) or float(P["duration"]) - tail
        if up <= 0 or brake <= 0 or stop < up + brake:
            raise ValueError("need spinup > 0, brake > 0 and stop >= spinup + brake (the reel must reach speed before it brakes)")
        D = stop + tail
        t = np.linspace(0, D, int(round(D * 1000)) + 1)
        v = _reel_speed(t, vmax, up, stop, brake)
        s = _lag(t, v, tau)
    else:
        D = float(P["duration"])
        cycles = max(1, int(round(vmax * D / Pd)))
        vmax = cycles * Pd / D                            # snapped so every streak advances a whole number of periods
        stop = None
        t = np.linspace(0, D, int(round(D * 1000)) + 1)
        v = s = np.full_like(t, vmax)
    X = _cumtrapz(t, s)
    sp = lambda u: float(np.interp(u, t, s))  # noqa: E731
    Xa = lambda u: float(np.interp(u, t, X))  # noqa: E731
    length = lambda u: min(Lmax, L0 + shutter * sp(u))  # noqa: E731
    end_fade = (lambda u: 1 - smooth(u, D - 0.08, D - 0.02)) if mode == "spin" else (lambda u: 1.0)  # noqa: E731

    rng = np.random.default_rng(c.seed + 311)
    grp = c.bone("blur", c.group, 0, 0)
    smear = float(P["smear"])
    s_sm = None
    if smear > 0:
        b_sm = c.bone("smear", grp)
        s_sm = c.slot(b_sm, "fx/column", W * 1.05, height=H, role="smear", stretch=True)
    rows, h0 = 8, 100.0
    streaks = []
    for k in range(n):
        x = -W / 2 + W * (k + 0.5) / n + float(rng.uniform(-0.2, 0.2)) * W / n
        w = W / 150 * float(rng.uniform(22, 40))
        x = max(-W / 2 + w * 0.3, min(W / 2 - w * 0.3, x))
        sl, nodes = c.strand(grp, "fx/spin_streak", w, h0, rows, x=x, make=TEX["fx/spin_streak"], tag=f"st{k}", role="streak")
        streaks.append(dict(s=sl, nodes=nodes, ph=(0.13 + k * (GOLDEN - 1) + float(rng.uniform(-0.06, 0.06))) % 1.0,
                            a=float(rng.uniform(0.35, 0.6))))
    slots = ([s_sm] if s_sm else []) + [st["s"] for st in streaks]
    c.show(slots, 0, D if mode == "spin" else None)

    base_ts = times_dense(0, D, 60)
    if mode == "spin":
        base_ts = sorted(set(base_ts) | {stop, D - 0.02})
    inset = 2.0
    for st in streaks:
        wr = _wraps(X, t, Pd, st["ph"], 0.003, D - 0.003)
        ts = _with_wraps(base_ts, wr)

        def centre(u, st=st):
            q = (Xa(u) / Pd + st["ph"]) % 1.0
            return -sgn * (0.75 * H - q * Pd)              # down: from +0.75H to -0.75H

        def row_y(u, i, st=st):
            if mode == "spin" and u >= D - 1e-9:
                return -h0 / 2 + i * h0 / (rows - 1)      # rest pose at the very end (hidden)
            y = centre(u) + (i / (rows - 1) - 0.5) * length(u)
            return min(H / 2 - inset, max(-H / 2 + inset, y))

        for i, nb in enumerate(st["nodes"]):
            y0 = -h0 / 2 + i * h0 / (rows - 1)
            c.bone_keys(nb, "translate", ts, lambda u, i=i, y0=y0: (0.0, row_y(u, i) - y0))

        def alpha(u, st=st):
            L = length(u)
            inside = (H / 2 + L / 2 - abs(centre(u))) / (0.2 * H)
            return st["a"] * (sp(u) / vmax) ** 0.8 * smooth(inside, 0.0, 1.0) * end_fade(u)
        c.color_keys(st["s"], ts, lambda u: hexa(col, c.a(alpha(u))))
    if s_sm:
        c.color_keys(s_sm, base_ts, lambda u: hexa(col, c.a(smear * sp(u) / vmax * end_fade(u))))
    out = dict(duration=D, mode=mode, speed=round(vmax, 3), lag=tau, streaks=n)
    if mode == "spin":
        s_stop = float(np.interp(stop, t, s))
        c.ab.event(c.T(stop), "fx_spin_blur_stop")
        out.update(stop_at=c.T(stop), catch_up=round(tau * s_stop, 3), lag_speed_at_stop=round(s_stop, 3))
    else:
        out.update(loop=D, cycles=int(round(vmax * D / Pd)))
    return c.result(**out)


# ------------------------------------------------------------------ turbo_spin
def turbo_spin(c: Ctx, P: dict) -> dict:
    """Turbo: speed lines streak down both sides of the reels (length = speed x shutter), side glows, and a travelling
    wave ripples through the symbol grid (carrier bones above your symbols, or our own grid)."""
    D = float(P["duration"])
    col = _hexn(P["color"], "7FE8FF")
    hot = _hexn(P["color2"], "FFFFFF")
    W, H = float(P["width"]), float(P["height"])
    vmax, shutter, ramp = float(P["speed"]), float(P["shutter"]), float(P["ramp"])
    wave = str(P["wave"])
    if wave not in ("across", "down"):
        raise ValueError(f"wave must be across | down, got {wave!r}")
    if vmax <= 0 or ramp <= 0 or 2 * ramp >= D:
        raise ValueError("speed and ramp must be > 0 and the window must hold the ramp in and out (duration > 2 x ramp)")
    c_w, f_w, ring, reach = float(P["wave_speed"]), float(P["freq"]), float(P["ring"]), float(P["reach"])
    if c_w <= 0 or f_w <= 0 or ring <= 0 or reach <= 0:
        raise ValueError("wave_speed, freq, ring and reach must be > 0")
    amp, kick = float(P["amp"]), float(P["kick"])
    n = int(P["count"])
    rng = np.random.default_rng(c.seed + 321)
    grp = c.bone("turbo", c.group, 0, 0)

    t = np.linspace(0, D, int(round(D * 1000)) + 1)
    v = vmax * smooth_arr(t, 0.0, ramp) * (1 - smooth_arr(t, D - ramp, D))
    X = _cumtrapz(t, v)
    vel = lambda u: float(np.interp(u, t, v))  # noqa: E731
    Xa = lambda u: float(np.interp(u, t, X))  # noqa: E731

    # side glows (the energy along the frame), then the lines
    gap, band = float(P["gap"]), float(P["band"])
    edges = []
    for side in (-1.0, 1.0):
        bn = c.bone(f"edge{'lr'[side > 0]}", grp, side * (W / 2 + gap + band / 2), 0)
        edges.append(c.slot(bn, "fx/column", band * 2.2, height=H * 1.08, role="edge", stretch=True))
    L0, Pd = 10.0, 1.6 * H
    lines = []
    for i in range(n):
        side = -1.0 if i % 2 == 0 else 1.0
        bn = c.bone(f"ln{i}", grp, side * (W / 2 + gap + float(rng.uniform(0.1, 0.9)) * band), 0)
        sl = c.slot(bn, "fx/spin_line", float(rng.uniform(10, 18)), height=100.0, oy=50.0, make=TEX["fx/spin_line"], role="line")
        m = float(rng.uniform(0.75, 1.3))
        lines.append(dict(b=bn, s=sl, m=m, ph=(0.07 + i * (GOLDEN - 1)) % 1.0, a=float(rng.uniform(0.5, 0.9)),
                          hot=rng.random() < 0.35))
    c.show(edges + [ln["s"] for ln in lines], 0, D)
    ts0 = times_dense(0, D, 60)
    c.color_keys(edges[0], ts0, lambda u: hexa(col, c.a(0.28 * vel(u) / vmax * (0.85 + 0.15 * math.sin(2 * math.pi * 9 * u)))))
    c.color_keys(edges[1], ts0, lambda u: hexa(col, c.a(0.28 * vel(u) / vmax * (0.85 + 0.15 * math.sin(2 * math.pi * 9 * u + 2.0)))))
    for ln in lines:
        wr = _wraps(X * ln["m"], t, Pd, ln["ph"], 0.003, D - 0.003)
        ts = _with_wraps(ts0, wr)
        q = lambda u, ln=ln: (Xa(u) * ln["m"] / Pd + ln["ph"]) % 1.0  # noqa: E731
        c.bone_keys(ln["b"], "translate", ts, lambda u, q=q: (0.0, 0.8 * H - q(u) * Pd))
        c.bone_keys(ln["b"], "scale", ts, lambda u, ln=ln: (1.0, min(0.9 * H, L0 + shutter * ln["m"] * vel(u)) / 100.0))
        c.color_keys(ln["s"], ts, lambda u, q=q, ln=ln: hexa(hot if ln["hot"] else col,
                                                             c.a(ln["a"] * vel(u) / vmax * math.sin(math.pi * q(u)) ** 0.6
                                                                 * smooth(q(u), 0, 0.05) * smooth(1 - q(u), 0, 0.05))))

    # the grid ripple: a travelling, decaying wave
    names = [str(b) for b in (P["bones"] or [])]
    w = c.sk.world()
    gw = w[c.group]
    pts = []
    if names:
        for b in names:
            if not c.sk.has_bone(b):
                raise ValueError(f"no bone {b!r} to ripple")
            pts.append((b, *gw.to_local(w[b].x, w[b].y)))
    else:
        cols, rws = int(P["cols"]), int(P["rows"])
        if cols < 1 or rws < 1:
            raise ValueError("cols and rows must be >= 1")
        px, py = float(P["pitch"]), float(P["row_pitch"])
        for i in range(cols):
            for j in range(rws):
                pts.append((None, (i - (cols - 1) / 2) * px, ((rws - 1) / 2 - j) * py))
    xs, ys = [p[1] for p in pts], [p[2] for p in pts]
    dist = [(x - min(xs)) if wave == "across" else (max(ys) - y) for x, y in zip(xs, ys)]
    taper = lambda u: 1 - smooth(u, D - 0.15, D)  # noqa: E731

    def psi(u, p):
        s_ = u - kick - p / c_w
        if s_ <= 0:
            return 0.0
        return math.exp(-p / reach) * math.exp(-s_ / ring) * math.sin(2 * math.pi * f_w * s_) * taper(u)
    tr = times_dense(0, D, 90)
    glow = float(P["glow"])
    carriers, grid, arrivals = [], [], {}
    for k, ((bone, x, y), p) in enumerate(zip(pts, dist)):
        if bone:
            car = _carrier(c, bone, "ripple")
            _merge_keys(c, car, "translate", tr, lambda u, p=p: (0.0, amp * c.S * psi(u, p)), "add")
            carriers.append(car)
            arrivals[bone] = c.T(kick + p / c_w)
        if bone and glow <= 0:
            continue
        gb = c.bone(f"cell{k}", grp, x, y)
        if not bone:
            grid.append(gb)
            arrivals[gb] = c.T(kick + p / c_w)
            c.bone_keys(gb, "translate", tr, lambda u, p=p: (0.0, amp * psi(u, p)))
        if glow > 0:
            sl = c.slot(gb, "fx/glow", float(P["pitch"]) * 0.95, role="glow")
            c.show([sl], 0, D)
            c.color_keys(sl, tr, lambda u, p=p: hexa(col, c.a(glow * abs(psi(u, p)))))
            c.bone_keys(gb, "scale", tr, lambda u, p=p: (1.0, 0.8 + 0.4 * abs(psi(u, p))))
    c.ab.event(c.T(kick), "fx_turbo_ripple")
    return c.result(duration=D, lines=n, ripple_at=c.T(kick), wave_speed=c_w, ripple_bones=carriers, grid_bones=grid,
                    arrivals=arrivals)


# ------------------------------------------------------------------ screen_shake
def screen_shake(c: Ctx, P: dict) -> dict:
    """Damped-spring screen shake on two incommensurate axes, a white 1/t flash and a converging red/cyan split."""
    amp, hz, ratio, decay = float(P["amp"]), float(P["hz"]), float(P["ratio"]), float(P["decay"])
    if hz <= 0 or decay <= 0 or amp < 0:
        raise ValueError("hz and decay must be > 0, amp >= 0")
    if ratio <= 0 or abs(ratio - round(ratio)) < 0.05:
        raise ValueError("ratio (x frequency / y frequency) must be > 0 and not a whole number: commensurate axes lock "
                         "into a clean repeating figure (default: the golden ratio)")
    D = max(0.75, 5.5 / decay)
    col = _hexn(P["color"], "FFFFFF")
    red, cyan = _hexn(P["red"], "FF2A3C"), _hexn(P["cyan"], "2AE8FF")
    size, split, conv = float(P["size"]), float(P["split"]), float(P["converge"])
    if conv <= 0:
        raise ValueError("converge must be > 0 seconds")
    grp = c.bone("shake", c.group, 0, 0)
    if P["shake"]:
        target = _carrier(c, str(P["shake"]), "shake")
        A = amp * c.S                                     # the carrier is outside the group: scale by hand
    else:
        target = c.bone("shaker", grp)
        A = amp
    taper = lambda u: 1 - smooth(u, 0.8 * D, D)  # noqa: E731
    xk = float(P["xamp"])

    def sh(u):
        e = math.exp(-decay * u) * taper(u)
        return (xk * A * e * math.sin(2 * math.pi * hz * ratio * u), -A * e * math.sin(2 * math.pi * hz * u))
    _merge_keys(c, target, "translate", times_dense(0, D, 240), sh, "add")

    # chromatic split (red / cyan converging), then the white flash on top
    w_ = 1.0 / conv
    d = lambda u: split * (1 + w_ * u) * math.exp(-w_ * u)  # noqa: E731
    chroma = float(P["chroma"])
    flash = float(P["flash"])
    b_r, b_c, b_f = c.bone("red", grp), c.bone("cyan", grp), c.bone("flash", grp)
    s_r = c.slot(b_r, "fx/spin_disc", size * 0.5, make=TEX["fx/spin_disc"], role="split")
    s_c = c.slot(b_c, "fx/spin_disc", size * 0.5, make=TEX["fx/spin_disc"], role="split")
    s_f = c.slot(b_f, "fx/glow", size, role="flash")
    c.show([s_r, s_c, s_f], 0, D)
    tf = sorted(set(times_dense(0, D, 90)) | {0.02})
    tail = lambda u, t0: smooth(u, 0, 0.02) / (1 + max(0.0, u - 0.02) / t0)  # noqa: E731   instant attack, 1/t tail
    c.bone_keys(b_r, "translate", tf, lambda u: (-d(u), 0.3 * d(u)))
    c.bone_keys(b_c, "translate", tf, lambda u: (d(u), -0.3 * d(u)))
    for b in (b_r, b_c):
        c.bone_keys(b, "scale", tf, lambda u: (0.85 + 0.25 * ease_out(u / 0.3, 2.5),) * 2)
    c.color_keys(s_r, tf, lambda u: hexa(red, c.a(chroma * tail(u, 0.06) * (1 - smooth(u, 0.35 * D, 0.9 * D)))))
    c.color_keys(s_c, tf, lambda u: hexa(cyan, c.a(chroma * tail(u, 0.06) * (1 - smooth(u, 0.35 * D, 0.9 * D)))))
    c.color_keys(s_f, tf, lambda u: hexa(col, c.a(flash * tail(u, 0.035) * (1 - smooth(u, 0.45 * D, D)))))
    c.bone_keys(b_f, "scale", tf, lambda u: (0.9 + 0.3 * ease_out(u / 0.4, 2.0),) * 2)
    return c.result(duration=D * c.k, shake_bone=target, flash_peak_at=c.T(0.02))


# ------------------------------------------------------------------ registry
RECIPES.update({
    "near_miss": dict(
        fn=near_miss, duration=2.02, kind="one-shot", color="FFD54A", count=7,
        summary="Near miss: a scatter's halo brightens as the symbol brakes toward the payline (constant deceleration; inverse-"
                "square brightness with a softening length, breathing faster as it nears), hangs there, then collapses with a sad "
                "little implosion: ring and glow sucked inward with ease-in (the ring spins up, w ~ 1/r^2), motes dragged in, "
                "colour drains to grey, a tiny dim pop and a puff of sparks falling on gravity parabolas. Events fx_near_miss, "
                "fx_near_miss_closest, fx_near_miss_fizzle.",
        anchor="The payline point the symbol should have landed on (follow=true), or the symbol's own centre (follow=false, "
               "parent= the symbol bone).",
        options=dict(size=(170.0, "halo diameter (a symbol cell)"),
                     dy=(330.0, "where the symbol starts, offset from the payline (+ above, - below)"),
                     miss=(150.0, "where it stops, offset from the payline on the same side (one row = the cell pitch)"),
                     closest=(0.55, "seconds until the symbol stops at its closest point (event fx_near_miss_closest)"),
                     fizzle=(0.8, "seconds when the hope dies and the halo implodes (event fx_near_miss_fizzle); "
                                  "the clip ends fizzle + 1.22"),
                     follow=(True, "the halo rides the approach path; false: it stays put (parent it to the symbol bone) and "
                                   "only its brightness follows the path"),
                     spin=(50.0, "ring spin before the collapse (deg/s); it spins up as the ring shrinks"))),
    "spin_blur": dict(
        fn=spin_blur, duration=1.62, kind="window", color="FFFFFF", count=6,
        summary="Motion-blur streaks over a spinning reel: the reel spins up, cruises and brakes to 0 at `stop`; the streaks "
                "follow through a first-order lag (they trail, then catch up after the stop, sliding lag x speed further while "
                "their speed decays e^-t/lag), stretch to speed x shutter and fade with the speed. Rows are clamped to the reel "
                "window. mode=loop is an exactly closed cruise segment. Events fx_spin_blur, fx_spin_blur_stop.",
        anchor="Reel window centre (width x height).",
        options=dict(width=(150.0, "reel width"), height=(450.0, "reel window height"),
                     mode=("spin", "spin (spin-up, cruise, brake, stop) | loop (cruise only, loops exactly; duration = loop)"),
                     stop=(0.0, "seconds when the reel stops (start reel_stop there); 0 = duration - the catch-up tail. "
                                "The window is stop + max(0.3, 6 x lag)"),
                     speed=(2400.0, "cruise speed (units/s); snapped in loop mode so the loop closes"),
                     spinup=(0.22, "spin-up time (s)"), brake=(0.35, "braking time before the stop (constant deceleration)"),
                     lag=(0.07, "first-order lag of the streaks behind the reel (s)"),
                     shutter=(0.05, "exposure: streak length = speed x shutter (capped at height/2)"),
                     direction=("down", "down | up"), smear=(0.1, "soft glow over the whole reel, follows the speed (0 = off)"))),
    "turbo_spin": dict(
        fn=turbo_spin, duration=1.6, kind="window", color="7FE8FF", count=16,
        summary="Turbo spin: speed lines streak down both sides of the reels, each stretched to its speed x shutter, side glows "
                "ride the speed (ramps in and out), and a travelling wave ripples through the symbol grid (phase velocity "
                "wave_speed, amplitude decaying with distance and ringing down), driving carrier bones above your symbol bones "
                "(bones=) or its own grid bones with a light on the crest. Events fx_turbo_spin, fx_turbo_ripple.",
        anchor="Centre of the reel area (width x height); speed lines run outside its sides.",
        options=dict(width=(486.0, "reel area width"), height=(450.0, "reel area height"), color2=("FFFFFF", "hot line colour"),
                     speed=(2600.0, "line speed (units/s); each line gets 0.75..1.3 of it"),
                     shutter=(0.06, "line length = its speed x shutter"), ramp=(0.18, "seconds to speed up and to slow down"),
                     gap=(10.0, "gap between the reel area and the line bands"), band=(44.0, "width of each line band"),
                     bones=([], "symbol (or reel) bones to ripple through carriers fx_ripple_<bone>; empty: own grid bones"),
                     cols=(3, "own grid columns"), rows=(3, "own grid rows"), pitch=(162.0, "own grid column pitch (and glow size)"),
                     row_pitch=(150.0, "own grid row pitch"),
                     wave=("across", "across (left to right, symbols bob up and down) | down (top to bottom of each reel)"),
                     amp=(22.0, "ripple amplitude (units) at the wave's origin"), wave_speed=(800.0, "phase velocity (units/s)"),
                     freq=(5.0, "ripple frequency (Hz)"), ring=(0.15, "ring-down time at each point (s)"),
                     reach=(900.0, "distance over which the amplitude falls by e"),
                     kick=(0.0, "seconds into the window when the ripple launches (event fx_turbo_ripple)"),
                     glow=(0.45, "light riding the crest on each cell (0 = off)"))),
    "screen_shake": dict(
        fn=screen_shake, duration=0.75, kind="one-shot", color="FFFFFF",
        summary="Screen shake + chromatic flash: a kicked damped spring on two axes at incommensurate frequencies (y ~12 Hz, "
                "x = ratio x y, amplitude e^-kt, the slam pushes down first), a white flash with a 1/t tail, and red/cyan glows "
                "that start split apart and converge like a critically damped spring. Moves a game bone through carrier "
                "fx_shake_<bone> (shake=), adding onto any shake already on it in the clip (reel_stop's). tiers= small..epic. "
                "Event fx_screen_shake.",
        anchor="The impact / screen centre (the flash sits here).",
        options=dict(shake=("", "bone to shake (the screen or reels container, not root). Empty: the result's shake_bone is a "
                                "bone to parent the screen under"),
                     amp=(8.0, "shake amplitude (units)"), hz=(12.0, "vertical shake frequency (Hz)"),
                     ratio=(GOLDEN, "x frequency / y frequency (not a whole number; golden ratio default)"),
                     xamp=(0.6, "sideways amplitude relative to vertical"),
                     decay=(9.0, "amplitude decay rate k in e^-kt (1/s); the clip lasts max(0.75, 5.5/k) s"),
                     flash=(0.5, "white flash peak alpha"), size=(1100.0, "flash size (cover the screen)"),
                     chroma=(0.4, "red/cyan flash peak alpha"), split=(26.0, "red/cyan offset at the start (units)"),
                     converge=(0.09, "time constant of the red/cyan convergence (s)"),
                     red=("FF2A3C", "red channel colour"), cyan=("2AE8FF", "cyan channel colour")),
        tiers={"small": dict(amp=3.0, decay=12.0, flash=0.2, chroma=0.2, split=10.0),
               "big": dict(amp=14.0, decay=7.0, flash=0.6, chroma=0.5, split=36.0),
               "mega": dict(amp=20.0, hz=11.0, decay=5.5, flash=0.75, chroma=0.6, split=48.0),
               "epic": dict(amp=28.0, hz=10.0, decay=4.5, flash=0.9, chroma=0.7, split=64.0, converge=0.1)}),
})
ROLES.update({
    "near_miss": {"halo": "the outer halo glow", "ring": "the rune ring around the symbol, square, centred", "core": "the core glow",
                  "mote": "one mote dragged inward (it is stretched toward the centre: draw it round)", "pop": "the tiny implosion pop",
                  "spark": "one falling spark"},
    "spin_blur": {"streak": "one blur streak, a tall strip, centred (stretched as a mesh)", "smear": "the soft glow over the reel, tall (stretched)"},
    "turbo_spin": {"line": "one speed line, HEAD at the BOTTOM, tail fading upward", "edge": "the side glow, tall (stretched)",
                   "glow": "the light riding the ripple crest on each cell"},
    "screen_shake": {"flash": "the white flash", "split": "the chromatic glows (white art; tinted red and cyan)"},
})
for _n, _d in ROLES.items():
    if _n in RECIPES:
        RECIPES[_n]["roles"] = _d
