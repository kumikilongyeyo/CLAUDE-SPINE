"""Reel moments for ``fx_recipe``: ``reel_stop`` and ``anticipation_reel``, the two FX that play on every spin.

Same rules as fx_recipes.py (procedural textures, one group bone per recipe, closed-form keys, ``art=`` roles), plus
one new thing: these recipes MOVE the game's own bones (the reel strip squashes and bounces, the screen shakes). They
never key a bone the artist owns. They insert a pure-translation carrier bone above it (``rig.insert_parent``, the
trick the juice presets use), so the artist's keys, constraints and weights stay untouched, and a scale on the
carrier pivots where the carrier sits: the BASE of the reel strip, so the strip squashes onto its floor. Several
reels stopping in one clip each add their shake to the same carrier instead of overwriting it.

Exaggerated real physics:

* ``reel_stop``: the strip arrives at speed and is caught by an underdamped spring, x(t) = -(v/wd) e^(-z w t) sin(wd t),
  with v solved so the deepest point is exactly ``overshoot``. Squash follows the spring's compression (shorter while
  below rest, stretched on the rebound, half area-preserving because a reel is boxed in by its frame). Dust is kicked
  out sideways from under the strip with air drag, x = v/k (1 - e^-kt), and rises on the warm air; two tiny
  Sedov-Taylor shock rings (r ~ t^0.4) and a 1/t flash at the base; the screen shakes as a damped spring at ~13 Hz.
* ``anticipation_reel``: a heartbeat that ACCELERATES. Each beat's period is the last one times ``accel`` (down to
  ``min_period``), every beat is a lub-dub pair of alpha-function pulses, and the beats grow stronger as the
  stop nears. The frame glow, the column of light inside the reel and the edge FX all ride the same pulse, the
  neighbours darken a little more on every beat, and each lub fires ``fx_anticipation_beat`` for a heartbeat sound.

Registered into fx_recipes.RECIPES / ROLES at import (fx_recipes imports this module at its end).
"""
from __future__ import annotations

import math

import numpy as np

from .fx_recipes import Ctx, RECIPES, ROLES, _frame_glow, _hexn, _mix, _rgb, _uniq, ease_out, hexa, smooth, times_dense
from .rig import insert_parent


# ------------------------------------------------------------------ carrier bones (move the game's bones safely)
def _carrier(c: Ctx, bone: str, tag: str, at: tuple[float, float] | None = None) -> str:
    """A pure-translation bone between ``bone`` and its parent, at world ``at`` (default: the bone's own origin).
    Made once and reused by later calls, so every reel_stop on one reel drives the same carrier."""
    sk = c.sk
    if not sk.has_bone(bone):
        raise ValueError(f"no bone {bone!r} to {tag}")
    b = sk.bone(bone)
    if b.parent is None:
        raise ValueError(f"{bone!r} is the root bone; pass the bone the reels hang from (a carrier is inserted above it)")
    base = f"fx_{tag}_{bone}"
    if b.parent.startswith(base):
        return b.parent
    w = sk.world()
    x, y = at if at is not None else (w[bone].x, w[bone].y)
    name = sk.unique_name(base)
    insert_parent(sk, name, b.parent, [bone], x, y)
    return name


def _merge_keys(c: Ctx, bone: str, timeline: str, ts, fn, op: str) -> None:
    """Key ``bone`` like Ctx.bone_keys, combined with keys an earlier call left on it in this animation: op "add"
    (translate) sums the two motions, op "mul" (scale) multiplies them. Times outside either motion hold its rest."""
    rest = 0.0 if op == "add" else 1.0
    new = [(c.T(u), *fn(u)) for u in ts]
    old = c.ab.a.bones.get(bone, {}).get(timeline)
    if old:
        val = lambda k, f: rest if getattr(k, f, None) is None else float(getattr(k, f))  # noqa: E731  saved files drop defaults
        ot = np.array([k.time for k in old])
        ox, oy = np.array([val(k, "x") for k in old]), np.array([val(k, "y") for k in old])
        nt = np.array([p[0] for p in new])
        nx, ny = np.array([p[1] for p in new]), np.array([p[2] for p in new])
        times = sorted(set(np.round(np.concatenate([ot, nt]), 4).tolist()))
        pts = []
        for t in times:
            ax, ay = np.interp(t, ot, ox), np.interp(t, ot, oy)
            bx, by = (np.interp(t, nt, nx), np.interp(t, nt, ny)) if t >= nt[0] - 1e-9 and t <= nt[-1] + 1e-9 else (rest, rest)
            pts.append((t, ax + bx, ay + by) if op == "add" else (t, ax * bx, ay * by))
        new = pts
    c.ab.bone(bone, timeline, _uniq(new), "linear")


def _spring(overshoot: float, hz: float, zeta: float):
    """Underdamped spring caught at rest with speed v: x(t) = -(v/wd) e^(-z w t) sin(wd t), v chosen so the deepest
    point is exactly ``overshoot`` below rest. Returns x(t)."""
    zeta = min(max(zeta, 0.02), 0.95)
    w0 = 2 * math.pi * hz
    wd = w0 * math.sqrt(1 - zeta * zeta)
    tp = math.atan2(wd, zeta * w0) / wd
    peak = math.exp(-zeta * w0 * tp) * math.sin(wd * tp) / wd
    v = overshoot / peak
    return lambda t: -v * math.exp(-zeta * w0 * t) * math.sin(wd * t) / wd if t > 0 else 0.0


# ------------------------------------------------------------------ reel_stop
def reel_stop(c: Ctx, P: dict) -> dict:
    """The thud when a reel lands: the strip overshoots, squashes onto its floor and springs back; dust kicks out from
    under it, two tiny shock rings and a flash at the base, the screen shakes."""
    D = 0.9
    col = _hexn(P["color"], "FFE6A8")
    dust_c = _hexn(P["color2"], "B9A58A")
    W, H = float(P["width"]), float(P["height"])
    A, sq = float(P["overshoot"]), float(P["squash"])
    n = int(P["count"])
    if not 0 < float(P["damping"]) < 1:
        raise ValueError("damping must be between 0 and 1 (an underdamped spring is what wobbles)")
    rng = np.random.default_rng(c.seed + 191)
    by = -H / 2
    grp = c.bone("stop", c.group, 0, 0)

    # the strip: the game's reel under a carrier at the reel base, or our own bone to parent the reel art under
    if P["reel"]:
        bx, byw = c.sk.world()[c.group].to_world(0, by)
        strip = _carrier(c, str(P["reel"]), "squash", (bx, byw))
        amp = A * c.S                                           # the carrier is outside the group: scale by hand
    else:
        strip = c.bone("strip", c.group, 0, by)
        amp = A
    x = _spring(1.0, float(P["bounce"]), float(P["damping"]))  # unit overshoot; x in [-1, ~0.4]
    land = lambda u: x(u) * (1 - smooth(u, 0.7 * D, D))  # noqa: E731   ends exactly at rest
    ts = times_dense(0, D, 60)
    _merge_keys(c, strip, "translate", ts, lambda u: (0.0, amp * land(u)), "add")

    def scl(u):
        sy = max(0.5, 1 + sq * land(u))                         # compressed below rest, stretched on the rebound
        return (sy ** -0.5, sy)
    _merge_keys(c, strip, "scale", ts, scl, "mul")

    # dust kicked out sideways from under the strip (normal blend, drawn first so the additive layers batch together)
    b_dust = c.bone("dust", grp, 0, by)
    puffs = []
    for i in range(n):
        side = -1.0 if i % 2 == 0 else 1.0
        bn = c.bone(f"d{i}", b_dust, side * W * float(rng.uniform(0.1, 0.45)), float(rng.uniform(-4, 6)))
        sl = c.slot(bn, "fx/cloud", W * float(rng.uniform(0.3, 0.46)), blend="normal", role="dust")
        puffs.append(dict(b=bn, s=sl, side=side, v=W * float(rng.uniform(1.6, 3.0)), k=float(rng.uniform(5.0, 8.0)),
                          rise=float(rng.uniform(14, 34)), g=float(rng.uniform(1.3, 2.0)), rot=float(rng.uniform(-60, 60)),
                          dl=float(rng.uniform(0.0, 0.05)), life=float(rng.uniform(0.5, 0.8))))
    b_fl = c.bone("flash", grp, 0, by, sy=0.4)
    s_fl = c.slot(b_fl, "fx/glow", W * 1.9, role="flash")
    rings = []
    for i, (d0, k_) in enumerate(((0.0, 1.0), (0.06, 0.7))):
        bn = c.bone(f"ring{i}", grp, 0, by, sy=0.26)
        rings.append((bn, c.slot(bn, "fx/ring", W * 1.7, role="ring"), d0, k_))

    c.show([s_fl] + [r_[1] for r_ in rings], 0, D)
    tf = times_dense(0, D, 40)
    fl = lambda u: smooth(u, 0, 0.02) / (1 + 32 * max(0.0, u - 0.02))  # noqa: E731
    c.color_keys(s_fl, tf, lambda u: hexa(col, c.a(min(1.0, 1.1 * fl(u)))))
    c.bone_keys(b_fl, "scale", tf, lambda u: (0.5 + 0.8 * ease_out(u / 0.18, 2.5),) * 2)
    sedov = lambda u: (max(0.0, u) / 0.55) ** 0.4  # noqa: E731
    for bn, sl, d0, k_ in rings:
        c.bone_keys(bn, "scale", tf, lambda u, d0=d0, k_=k_: ((0.12 + 1.0 * k_ * min(1.0, sedov(u - d0))),) * 2 if u >= d0 else (0.0, 0.0))
        c.color_keys(sl, tf, lambda u, d0=d0, k_=k_: hexa(col if k_ == 1.0 else "FFFFFF",
                                                          c.a(0.9 * k_ * max(0.0, 1 - sedov(u - d0)) ** 1.5 * smooth(u, d0, d0 + 0.02))))
    for pf in puffs:
        dl, L = pf["dl"], pf["life"]
        tp = times_dense(dl, min(D, dl + L), 40)
        q = lambda u, dl=dl: max(0.0, u - dl)  # noqa: E731
        c.bone_keys(pf["b"], "translate", tp, lambda u, pf=pf, q=q: (pf["side"] * pf["v"] / pf["k"] * (1 - math.exp(-pf["k"] * q(u))),
                                                                     pf["rise"] * (1 - math.exp(-3.0 * q(u)))))
        c.bone_keys(pf["b"], "scale", tp, lambda u, pf=pf, q=q: ((0.35 + (pf["g"] - 0.35) * ease_out(q(u) / 0.5, 2.2)),
                                                                 0.6 * (0.35 + (pf["g"] - 0.35) * ease_out(q(u) / 0.5, 2.2))))
        c.bone_keys(pf["b"], "rotate", tp, lambda u, pf=pf, q=q: pf["rot"] * ease_out(q(u) / L, 1.6))
        c.color_keys(pf["s"], tp, lambda u, dl=dl, L=L: hexa(dust_c, c.a(0.75 * smooth(u, dl, dl + 0.04) * (1 - smooth(u, dl + 0.2, dl + L)))))
        c.ab.slot_attachment(pf["s"], [(0.0, None), (c.T(dl), "fx"), (c.T(min(D, dl + L)), None)] if c.T(dl) > 0
                             else [(0.0, "fx"), (c.T(min(D, dl + L)), None)])

    shaker = ""
    if P["shake"]:
        shaker = _carrier(c, str(P["shake"]), "shake")
        sa, hz, tau = float(P["shake_amp"]), float(P["shake_hz"]), 0.11
        tss = times_dense(0, 0.6, 120)

        def sh(u):
            e = math.exp(-u / tau) * (1 - smooth(u, 0.42, 0.6))
            return (0.35 * sa * e * math.sin(2 * math.pi * hz * 1.37 * u),       # sideways at an off frequency: no clean line
                    -sa * e * math.sin(2 * math.pi * hz * u))                  # the slam pushes the screen DOWN first
        _merge_keys(c, shaker, "translate", tss, sh, "add")
    return c.result(duration=D * c.k, squash_bone=strip, shake_bone=shaker, dust=n)


# ------------------------------------------------------------------ anticipation_reel
def _beats(D: float, lead: float, period: float, accel: float, min_period: float) -> list[tuple[float, float]]:
    """Heartbeat schedule: (time, period) for each beat; every period is the last one times accel, floored."""
    out, t, k = [], lead, 0
    while t < D - 0.15:
        p = max(min_period, period * accel ** k)
        out.append((t, p))
        t += p
        k += 1
    return out


def anticipation_reel(c: Ctx, P: dict) -> dict:
    """The last spinning reel glows with an accelerating heartbeat: frame glow, a column of light inside it, flames or
    sparks along its edges, and the neighbouring reels dim (darker on every beat)."""
    D = float(P["duration"])
    col = _hexn(P["color"], "FFB43C")
    hot = _hexn(P["color2"], "FFF2C8")
    W, H = float(P["width"]), float(P["height"])
    edge = str(P["edge"])
    if edge not in ("flames", "sparks", "none"):
        raise ValueError(f"edge must be flames | sparks | none, got {edge!r}")
    if not 0 < float(P["accel"]) <= 1:
        raise ValueError("accel must be in (0, 1]: each beat's period is the last one times accel")
    beats = _beats(D, float(P["lead"]), float(P["period"]), float(P["accel"]), float(P["min_period"]))
    N = len(beats)
    rng = np.random.default_rng(c.seed + 211)
    grp = c.bone("antic", c.group, 0, 0)

    def pulse(u):
        """Sum of lub-dub alpha-function pulses, (s/tau) e^(1 - s/tau), peak 1 at s = tau, stronger toward the end."""
        v = 0.0
        for i, (tb, p) in enumerate(beats):
            a = 0.55 + 0.45 * (i / max(1, N - 1))
            tau = min(0.075, 0.2 * p)
            for off, w in ((0.0, 1.0), (0.3 * p, 0.5)):
                s = u - tb - off
                if 0 < s < 12 * tau:
                    v += a * w * (s / tau) * math.exp(1 - s / tau)
        return min(1.3, v)
    env = lambda u: smooth(u, 0, 0.25) * (1 - smooth(u, D - 0.18, D))  # noqa: E731
    ts = sorted(set(times_dense(0, D, 50)) | {r_ for tb, p in beats for r_ in (tb, tb + min(0.075, 0.2 * p))})

    # the neighbours dim (normal blend; first in the run so the additive layers that follow share one batch)
    dims = P["dim"]
    if dims is None:
        g = float(P["gap"])
        dims = [[-(W + g), 0, W, H], [W + g, 0, W, H]]
    dim_a = float(P["dim_alpha"])
    dim_slots = []
    for i, d in enumerate(dims):
        dx, dy, w, h = (float(v) for v in d)
        b = c.bone(f"dim{i}", grp, dx, dy)
        s, _ = c.slice9(b, "fx/cellfill", w, h, 48.0, color="000000FF", tag=f"dim{i}", blend="normal", role="dim")
        dim_slots.append(s)
    # the reel itself: a column of light inside it, a frame glow hugging it
    b_col = c.bone("col", grp)
    s_col = c.slot(b_col, "fx/column", W * 1.15, height=H * 1.04, role="column", stretch=True)
    s_fr = _frame_glow(c, grp, W, H, tag="frame", role="frame")
    b_fr = c.sk.slot(s_fr).bone
    c.show(dim_slots + [s_col, s_fr], 0, D)
    for s in dim_slots:
        c.color_keys(s, ts, lambda u: hexa("000000", min(1.0, env(u) * (dim_a + 0.1 * pulse(u)))))
    c.color_keys(s_col, ts, lambda u: hexa(col, c.a(env(u) * (0.1 + 0.22 * pulse(u)))))   # additive over light reels saturates fast
    c.bone_keys(b_col, "scale", ts, lambda u: (1.0 + 0.08 * pulse(u), 1.0))
    c.color_keys(s_fr, ts, lambda u: hexa(col, c.a(env(u) * (0.5 + 0.5 * pulse(u)))))
    c.bone_keys(b_fr, "scale", ts, lambda u: (1.0 + 0.03 * pulse(u),) * 2)

    hint = None
    tongues = sparks = 0
    if edge == "flames":
        tongues = _edge_flames(c, grp, W, H, D, int(P["count"]), col, hot, env, pulse, rng)
        hint = dict(parent=c.group, front_of=c.slots[-1], mode="additive", seq_mode="loop", until=c.T(D),
                    note="realistic flames: ae_template fire params={edge_fade: true} -> ae_fx_to_spine with these args, one "
                         "tongue per edge (x = -width/2 and +width/2), sequence index offset per clone")
    elif edge == "sparks":
        sparks = _edge_sparks(c, grp, W, H, beats, int(P["sparks"]), hot, rng)
        hint = dict(parent=c.group, front_of=c.slots[-1], mode="additive", seq_mode="loop", until=c.T(D),
                    note="lightning line: ae_template electric_frame params={width: %g, height: %g} -> ae_fx_to_spine with these args" % (W, H))
    for tb, _ in beats:
        c.ab.event(c.T(tb), "fx_anticipation_beat")
    out = dict(duration=D, beats=[c.T(tb) for tb, _ in beats], periods=[round(p, 4) for _, p in beats],
               dimmed=len(dim_slots), tongues=tongues, sparks=sparks)
    if hint:
        out["ae_hint"] = hint
    return c.result(**out)


def _edge_flames(c: Ctx, grp: str, W: float, H: float, D: float, n: int, col: str, hot: str, env, pulse, rng) -> int:
    """Flame tongues licking up both side edges: each one is born hot at a point on the edge, accelerates upward on its
    own buoyancy (y ~ a t^2), stretches as it speeds up, cools white -> colour -> red and dies, then respawns while
    invisible. Brighter on every beat."""
    hot_rgb, col_rgb, red = _rgb(hot), _rgb(col), (255, 70, 20)
    made = 0
    for side in (-1.0, 1.0):
        for i in range(n):
            L = float(rng.uniform(0.36, 0.56))
            ph = float(rng.uniform(0, L))
            y0 = -H / 2 + (i + float(rng.uniform(0.1, 0.9))) / n * H * 0.92
            rise = H * float(rng.uniform(0.14, 0.24))
            lean = side * float(rng.uniform(4, 12))
            bn = c.bone(f"fl{'lr'[side > 0]}{i}", grp, side * W / 2, y0)
            sl = c.slot(bn, "fx/smoke", W * float(rng.uniform(0.32, 0.46)), role="flame")
            q = lambda u, L=L, ph=ph: ((u + ph) / L) % 1.0  # noqa: E731
            tsd = set(times_dense(0, D, 30))
            j = 1
            while j * L - ph < D:
                w_ = j * L - ph
                if w_ > 0.003:
                    tsd.update([w_ - 0.002, w_])
                j += 1
            tsd = sorted(t for t in tsd if 0 <= t <= D)

            def colour(u, q=q):
                f = q(u)
                rgb = _mix(hot_rgb, col_rgb, min(1.0, f / 0.45)) if f < 0.45 else _mix(col_rgb, red, min(1.0, (f - 0.45) / 0.4))
                return "%02X%02X%02X" % tuple(int(v) for v in rgb)
            c.bone_keys(bn, "translate", tsd, lambda u, q=q, rise=rise, lean=lean: (lean * q(u), rise * (0.35 * q(u) + 0.65 * q(u) ** 2)))
            c.bone_keys(bn, "scale", tsd, lambda u, q=q: (max(0.05, 0.9 - 0.45 * q(u)), 0.7 + 0.9 * q(u)))
            c.color_keys(sl, tsd, lambda u, q=q, colour=colour: hexa(colour(u), c.a(env(u) * (0.5 + 0.5 * min(1.0, pulse(u)))
                                                                                    * math.sin(math.pi * q(u)) ** 0.8)))
            c.show([sl], 0, D)
            made += 1
    return made


def _edge_sparks(c: Ctx, grp: str, W: float, H: float, beats, pool: int, hot: str, rng) -> int:
    """Electric sparks crackling along both side edges ON the beat: a pool of spark slots, each one reused at a new point
    (it jumps while hidden). More sparks per beat as the beats speed up."""
    N = len(beats)
    slots = []
    for i in range(pool):
        bn = c.bone(f"sp{i}", grp)
        slots.append(dict(b=bn, s=c.slot(bn, "fx/spark", float(rng.uniform(34, 70)), color=hexa(hot, 1.0), role="spark"),
                          free=0.0, tr=[], sc=[], ro=[], att=[(0.0, None)]))
    for k, (tb, p) in enumerate(beats):
        m = 2 + (2 * k) // max(1, N)                  # 2 per beat, 3 near the end
        for _ in range(m):
            sp = min(slots, key=lambda s_: s_["free"])
            t0 = tb + float(rng.uniform(0.0, 0.05))
            if sp["free"] > t0:
                continue
            life = float(rng.uniform(0.12, 0.22))
            x = (-1 if rng.random() < 0.5 else 1) * W / 2
            y = float(rng.uniform(-H / 2, H / 2))
            sp["tr"] += [(c.T(t0), x, y), (c.T(t0 + life), x, y)]
            sp["sc"] += [(c.T(t0), 0, 0), (c.T(t0 + life * 0.35), 1, 1), (c.T(t0 + life), 0, 0)]
            sp["ro"] += [(c.T(t0), 0), (c.T(t0 + life), float(rng.uniform(-80, 80)))]
            sp["att"] += [(c.T(t0), "fx"), (c.T(t0 + life), None)]
            sp["free"] = t0 + life + 0.01
    used = 0
    for sp in slots:
        if len(sp["att"]) == 1:
            c.ab.slot_attachment(sp["s"], sp["att"])
            continue
        used += 1
        c.ab.bone(sp["b"], "translate", _uniq(sp["tr"]), "linear")
        c.ab.bone(sp["b"], "scale", _uniq(sp["sc"]), "quad_in_out")
        c.ab.bone(sp["b"], "rotate", _uniq(sp["ro"]), "linear")
        c.ab.slot_attachment(sp["s"], sp["att"])
    return used


# ------------------------------------------------------------------ registry
RECIPES.update({
    "reel_stop": dict(
        fn=reel_stop, duration=0.9, kind="one-shot", color="FFE6A8", count=8, normal_blend=True,
        summary="Reel stop thud with exaggerated spring physics: the strip overshoots past its rest, squashes onto its floor and "
                "springs back (underdamped spring, overshoot solved exactly); dust kicks out sideways from under it with air drag, "
                "two tiny Sedov shock rings and a 1/t flash at the base, a damped ~13 Hz screen shake. Moves your bones through "
                "inserted carrier bones (reel=, shake=), never your own keys. Event fx_reel_stop.",
        anchor="Reel strip centre (width x height); the floor is height/2 below.",
        options=dict(width=(150.0, "reel strip width"), height=(450.0, "reel strip height"),
                     reel=("", "bone of the reel strip: a carrier is inserted above it at the strip's base and squashed/bounced "
                               "(your keys stay untouched). Empty: the result's squash_bone is a bone to parent the reel under"),
                     shake=("", "bone to micro-shake (the reels container or a screen bone; not root). Empty: no shake"),
                     overshoot=(30.0, "how far the strip drops past rest before springing back (design units)"),
                     bounce=(4.5, "spring frequency in Hz"), damping=(0.3, "damping ratio, 0..1 (lower wobbles longer)"),
                     squash=(0.14, "squash at the deepest point (0.14 = 14% shorter); it stretches on the rebound"),
                     color2=("B9A58A", "dust colour"), shake_amp=(7.0, "shake amplitude (units)"),
                     shake_hz=(13.0, "shake frequency (Hz)"))),
    "anticipation_reel": dict(
        fn=anticipation_reel, duration=2.4, kind="window", color="FFB43C", normal_blend=True,
        summary="Anticipation on the last spinning reel: a heartbeat that ACCELERATES (each period = the last x accel; lub-dub "
                "pulses that grow stronger), driving a frame glow, a column of light inside the reel and flames or electric sparks "
                "along its edges, while the neighbouring reels dim and darken on every beat. Events fx_anticipation_reel and "
                "fx_anticipation_beat (one per beat, for the heartbeat sound). ae_hint for AE fire / lightning.",
        anchor="Reel centre (width x height); dim panels are offsets from it.",
        options=dict(width=(150.0, "reel width"), height=(450.0, "reel height"), color2=("FFF2C8", "hot colour (flame cores, sparks)"),
                     edge=("flames", "flames | sparks | none"), period=(0.62, "first beat period (s)"),
                     accel=(0.82, "period multiplier per beat (< 1 speeds up)"), min_period=(0.2, "fastest beat period (s)"),
                     lead=(0.12, "seconds before the first beat"),
                     dim=(None, "[[dx, dy, w, h], ...] panels to darken (default: one reel each side, gap apart)"),
                     gap=(12.0, "gap between reels for the default dim panels"), dim_alpha=(0.55, "how dark the neighbours get"),
                     sparks=(12, "spark pool for edge=sparks"))),
})
RECIPES["anticipation_reel"]["count"] = 7         # count= is flame tongues per side
ROLES.update({
    "reel_stop": {"dust": "one dust puff (normal blend), roughly round, centred", "flash": "the impact light at the base",
                  "ring": "the two shock rings"},
    "anticipation_reel": {"dim": "9-slice dim panel art (give slice and px)", "column": "the light inside the reel, tall (stretched to the height)",
                          "frame": "9-slice glow hugging the reel (give slice and px)", "flame": "one flame tongue, centred",
                          "spark": "one spark"},
})
for _n, _d in ROLES.items():
    if _n in RECIPES:
        RECIPES[_n]["roles"] = _d
