"""Feature triggers for ``fx_recipe``: ``wild_land``, ``expanding_wild``, ``scatter_trigger``, ``free_spins_transition``.

The four moments that announce a slot feature. Same rules as fx_recipes.py (procedural textures, one group bone per
recipe, closed-form keys, ``art=`` roles, normal-blend layers first in their run) and, like fx_reels.py, two of them
move the GAME's own bones through inserted carrier bones (``wild=`` for the falling wild, ``screen=`` for the screen
pulled into the portal), so the artist's keys, constraints and weights are never touched.

Exaggerated real physics:

* ``wild_land``: the wild falls from rest under gravity, y = h - g t^2 / 2, with g solved so it lands exactly at ``fall``
  seconds. It bounces with a coefficient of restitution (every rebound speed is ``bounce`` x the last, so every bounce
  is ``bounce``^2 as high), the contact time grows as the hits soften (Hertz contact, tau ~ v^-1/5), it stretches
  along its speed in the air and squashes on every contact, area-preserving (sx = 1 / sy), the first squash exactly
  ``squash``. A motion-blur streak whose length is the speed, a 1/t flash, Sedov shock rings (r ~ t^0.4) and sparks
  on drag parabolas at the impact. The sticky frame snaps on with an underdamped spring of exact overshoot, then
  breathes; the breathing is also written as its own loop animation (``<anim>_hold``) that starts on the clip's last
  frame and closes exactly, so the wild stays sticky across spins.
* ``expanding_wild``: liquid fills the reel. The front height is eased; while it flows, the front LEADS in the middle
  with a parabolic Poiseuille profile (a channel flow is fastest at its centre, zero at the walls), scaled by the flow
  speed. When it reaches the end the bulge collapses into standing waves on the surface: modes cos(n pi x / W) with
  deep-water dispersion (omega_n ~ sqrt(n)), the symmetric ones from the collapse plus a ``tilt`` of the side-to-side
  mode, each damped e^(-zeta omega t). The fill is a 9-slice mesh whose front corner bones move; the surface is a strand
  mesh whose row bones carry the wave. A light column rises with the fill; the frame flashes on when it is full.
* ``scatter_trigger``: each scatter rings on landing (rune halo on a step spring of exact overshoot, Sedov ring, 1/t
  flash). With ``need`` or more, they lock on in order (a reticle drops in spinning and snaps, like ``crosshair``) and
  each fires a beam to the centre whose front travels at ONE constant speed (light), so the far ones arrive last. The
  centre charges like a capacitor, every arriving beam adds 1/N that settles as 1 - e^(-t/tau); when the last one is in
  it discharges in a ``shine``-style burst (1/t bloom, counter-turning rays, Sedov rings) and the scatter halos spend
  their light with it.
* ``free_spins_transition``: a portal opens behind the reels (step spring), then the screen is pulled in by an
  ACCELERATING infall, scale s(t) = a - b e^(t/tau) reaching exactly 0, while it swirls with conserved angular momentum:
  omega (s + core)^2 = constant, so it whips round faster and faster as it shrinks (the angle is the exact integral).
  The portal collapses with a flash, a cartoon puff bursts in front, and the screen springs back out of it (step spring,
  exact overshoot) unwinding to rest, so the next screen starts clean: the carrier ends at scale 1, rotation 0.

Events: ``fx_<recipe>`` at the start of each, plus ``fx_wild_impact`` / ``fx_wild_bounce`` (contacts),
``fx_expanding_wild_full``, ``fx_scatter_land`` (int = how many have landed) / ``fx_scatter_lock`` (int = order) /
``fx_scatter_bonus`` (the burst; ``fx_scatter_trigger`` is the recipe's start), ``fx_free_spins_in`` (the screen is gone: swap it now) / ``fx_free_spins_out``.

Registered into fx_recipes.RECIPES / ROLES at import.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from .fx import _rgba
from .fx_recipes import (Ctx, RECIPES, ROLES, _frame_glow, _grid, _hexn, _mix, _rgb, _uniq, ease_out, hexa, rr_point, smooth,
                         smooth_arr, tex_comet, tex_disc, tex_frame9, tex_rays, tex_reticle, tex_rune_ring, tex_starburst,
                         tex_strand, tex_swirl, tex_trail, times_dense)
from .fx_reels import _carrier, _merge_keys
from .timeline import AnimBuilder


# ------------------------------------------------------------------ textures (new ones are prefixed fx/features_)
def tex_surface(w: int = 64, h: int = 256) -> Image.Image:
    """The liquid's surface band, laid out for a strand: across (x) runs from the fill side (x=0, fades in so it melts into
    the fill) through an opaque body to a soft front edge (x=1); along (y) the ends taper. White; tint with the slot."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    u, v = x / (w - 1), y / (h - 1)
    a = smooth_arr(u, 0.0, 0.3) * (1 - smooth_arr(u, 0.72, 1.0)) * np.minimum(smooth_arr(v, 0.0, 0.07), smooth_arr(1 - v, 0.0, 0.07))
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def tex_liquid(n: int = 192) -> Image.Image:
    """9-slice source for the liquid fill: an OPAQUE rounded rectangle (soft 2 px rim), so the fill and the surface band,
    both tinted the same, overlap without a seam. White; tint with the slot."""
    from .fx_recipes import _rr_sdf
    d = _rr_sdf(n, 0.97, 0.97, 0.2)                 # reaches the reel walls (cellfill is inset ~20%)
    a = np.clip(0.5 - d / 0.022, 0, 1)
    return _rgba(np.ones((n, n)), a)


def tex_halo_runes(color: str = "FFC83C", n: int = 512) -> Image.Image:
    """The rune ring with its middle cleared (no spiral over the symbol it circles)."""
    im = tex_rune_ring(color, n=n)
    x, y = _grid(n)
    arr = np.asarray(im, np.float32)
    arr[..., 3] *= smooth_arr(np.hypot(x, y), 0.5, 0.58)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA")


# ------------------------------------------------------------------ shared maths
def _step(overshoot: float, hz: float):
    """Underdamped step response 0 -> 1 whose first peak is exactly 1 + overshoot (zeta solved from the overshoot)."""
    if not 0 < overshoot < 1:
        raise ValueError("overshoot must be between 0 and 1 (fraction past the target on the first swing)")
    L = math.log(overshoot)
    z = -L / math.sqrt(math.pi ** 2 + L * L)
    w0 = 2 * math.pi * hz
    wd = w0 * math.sqrt(1 - z * z)
    f = lambda t: 0.0 if t <= 0 else 1 - math.exp(-z * w0 * t) * (math.cos(wd * t) + z * w0 / wd * math.sin(wd * t))  # noqa: E731
    f.peak_t = math.pi / wd
    return f


def _step_at(overshoot: float, t_peak: float):
    """The same step response, timed so its first peak (1 + overshoot) is at t_peak."""
    L = math.log(overshoot)
    z = -L / math.sqrt(math.pi ** 2 + L * L)
    return _step(overshoot, (math.pi / t_peak) / math.sqrt(1 - z * z) / (2 * math.pi))


def _flash(s: float, k: float = 30.0, att: float = 0.02) -> float:
    """Impulse light: attack in ``att`` seconds, then decays like 1/t."""
    return 0.0 if s < 0 else smooth(s, 0, att) / (1 + k * max(0.0, s - att))


def _sedov(s: float, life: float) -> float:
    return (max(0.0, s) / life) ** 0.4


def _merge_rot(c: Ctx, bone: str, ts, fn) -> None:
    """Rotation keys on ``bone``, ADDED to rotation keys an earlier call left in this animation (rest 0 outside each)."""
    new = [(c.T(u), float(fn(u))) for u in ts]
    old = c.ab.a.bones.get(bone, {}).get("rotate")
    if old:
        ot = np.array([k.time for k in old])
        ov = np.array([0.0 if getattr(k, "value", None) is None else float(k.value) for k in old])
        nt, nv = np.array([p[0] for p in new]), np.array([p[1] for p in new])
        pts = []
        for t in sorted(set(np.round(np.concatenate([ot, nt]), 4).tolist())):
            b = float(np.interp(t, nt, nv)) if nt[0] - 1e-9 <= t <= nt[-1] + 1e-9 else 0.0
            pts.append((t, float(np.interp(t, ot, ov)) + b))
        new = pts
    c.ab.bone(bone, "rotate", _uniq(new), "linear")


def _hexmix(a: str, b: str, t: float) -> str:
    return "%02X%02X%02X" % tuple(int(round(v)) for v in _mix(_rgb(a), _rgb(b), min(1.0, max(0.0, t))))


def _vec(v, n: int, what: str) -> list[float]:
    try:
        out = [float(x) for x in v]
    except (TypeError, ValueError):
        raise ValueError(f"{what} must be a list of {n} numbers, got {v!r}") from None
    if len(out) != n:
        raise ValueError(f"{what} must be a list of {n} numbers, got {v!r}")
    return out


# ------------------------------------------------------------------ wild_land
def _bounces(h0: float, Tf: float, e: float, tau_c: float, min_h: float = 1.0) -> dict:
    """Free fall from rest at height h0, landing at Tf, then bounces with restitution e. Contacts last tau_c at the
    first hit and longer as the hits soften (Hertz: tau ~ v^-1/5). Returns g, v0, the flights and the contacts."""
    g = 2 * h0 / (Tf * Tf)
    v0 = g * Tf
    flights = [(0.0, Tf, h0, 0.0)]            # (t0, t1, y0, vy0): y = y0 + vy0 s - g s^2 / 2
    contacts = []                              # (t0, t1, v_in, v_out)
    t, v = Tf, v0
    while True:
        vout = e * v
        if vout * vout / (2 * g) < min_h:
            vout = 0.0
        tc = tau_c * min(2.0, (v / v0) ** -0.2)
        contacts.append((t, t + tc, v, vout))
        t += tc
        if vout == 0.0:
            break
        air = 2 * vout / g
        flights.append((t, t + air, 0.0, vout))
        t += air
        v = vout
    return dict(g=g, v0=v0, flights=flights, contacts=contacts, rest=t)


def wild_land(c: Ctx, P: dict) -> dict:
    """The wild drops from above with gravity, bounces and squashes; impact flash, rings, sparks; a sticky frame glow
    snaps on and keeps breathing (plus a loop animation that holds it)."""
    col = _hexn(P["color"], "FFC93C")
    hot = _hexn(P["color2"], "FFF4C8")
    W, H = float(P["width"]), float(P["height"])
    h0, Tf, e = float(P["drop"]), float(P["fall"]), float(P["bounce"])
    sq, st = float(P["squash"]), float(P["stretch"])
    per, hold = float(P["pulse"]), int(P["hold"])
    if h0 <= 0 or Tf <= 0:
        raise ValueError("drop and fall must be > 0 (height in units, fall time in seconds)")
    if not 0 <= e < 1:
        raise ValueError("bounce is the coefficient of restitution: 0 <= bounce < 1")
    if not 0 <= sq < 0.8:
        raise ValueError("squash must be between 0 and 0.8")
    if per <= 0 or hold < 0:
        raise ValueError("pulse must be > 0 seconds and hold >= 0 pulses")
    B = _bounces(h0, Tf, e, float(P["contact"]))
    g, v0 = B["g"], B["v0"]
    Ti = Tf
    settle = 0.6
    th = Ti + max(settle, B["rest"] - Ti + 0.05)
    D = th + hold * per
    rng = np.random.default_rng(c.seed + 301)
    grp = c.bone("wild", c.group, 0, 0)

    def y_at(t):
        for t0, t1, y0, vy0 in B["flights"]:
            if t0 <= t <= t1:
                s = t - t0
                return y0 + vy0 * s - 0.5 * g * s * s, vy0 - g * s
        return 0.0, 0.0

    def scale_at(t):
        for t0, t1, vin, vout in B["contacts"]:
            if t0 <= t <= t1:
                q = (t - t0) / (t1 - t0)
                ki, ko = vin / v0, vout / v0
                base = (1 + st * ki) * (1 - q) + (1 + st * ko) * q
                sy = base - (sq * ki + st * (ki + ko) / 2) * math.sin(math.pi * q)
                return 1 / sy, sy
        if t >= B["rest"]:
            return 1.0, 1.0
        sy = 1 + st * abs(y_at(t)[1]) / v0
        return 1 / sy, sy

    # the wild itself: the game's bone under a carrier at the symbol's base, or our own bone to parent the wild art under
    if P["wild"]:
        bx, byw = c.sk.world()[c.group].to_world(0, -H / 2)
        drop = _carrier(c, str(P["wild"]), "drop", (bx, byw))
        amp = c.S
    else:
        drop = c.bone("drop", c.group, 0, -H / 2)
        amp = 1.0
    knots = {0.0, B["rest"]}
    for t0, t1, *_ in B["contacts"]:
        knots.update([t0, t1, (t0 + t1) / 2])
    tw = sorted(set(times_dense(0, B["rest"], 120)) | knots)
    _merge_keys(c, drop, "translate", tw, lambda u: (0.0, amp * y_at(u)[0]), "add")
    _merge_keys(c, drop, "scale", tw, scale_at, "mul")

    # motion-blur streak above the falling wild: its length is the speed
    b_st = c.bone("streak", grp, 0, H * 0.2, rot=180)
    Ls = max(H, 0.35 * h0)
    s_st = c.slot(b_st, f"fx/trail_{col}", W * 1.6, oy=-Ls / 2, height=Ls, make=lambda: tex_trail(col), role="streak",
                  anchor="top", stretch=True)
    # impact: flash, two shock rings on the ground plane, a starburst, sparks
    b_fl = c.bone("flash", grp, 0, -H / 2, sy=0.45)
    s_fl = c.slot(b_fl, "fx/glow", W * 2.2, role="flash")
    rings = []
    for i, (d0, k_) in enumerate(((0.0, 1.0), (0.07, 0.7))):
        bn = c.bone(f"ring{i}", grp, 0, -H / 2, sy=0.3)
        rings.append((bn, c.slot(bn, "fx/ring", W * 2.6, role="ring"), d0, k_))
    b_sb = c.bone("star", grp)
    s_sb = c.slot(b_sb, f"fx/starburst_{col}", W * 1.7, make=lambda: tex_starburst(col), role="starburst")
    sparks = []
    for i in range(int(P["count"])):
        side = -1.0 if i % 2 == 0 else 1.0
        bn = c.bone(f"sp{i}", grp, side * W * float(rng.uniform(0.1, 0.5)), -H / 2 + float(rng.uniform(0, 10)))
        sl = c.slot(bn, "fx/mote", float(rng.uniform(12, 22)), role="spark")
        a = math.radians(float(rng.uniform(18, 72)))
        v = float(rng.uniform(520, 980))
        sparks.append(dict(b=bn, s=sl, vx=side * math.cos(a) * v, vy=math.sin(a) * v, k=float(rng.uniform(2.4, 4.0)),
                           t0=Ti + float(rng.uniform(0, 0.03)), life=float(rng.uniform(0.35, 0.6))))
    # the sticky frame: a soft glow and a crisp line, both 9-slices on one bone
    b_fr = c.bone("frame", grp)
    s_glow = _frame_glow(c, b_fr, W, H, tag="sticky", role="glow")
    s_line, _ = c.slice9(b_fr, f"fx/frame9_{col}", W + 12, H + 12, 48.0, make=lambda: tex_frame9(col), tag="line", role="frame")   # just outside the symbol
    b_fs = []
    nsp = int(P["sparks"])
    for i in range(nsp):
        x_, y_, _ = rr_point(float(rng.uniform(0, 1)), W, H, 14.0)
        bn = c.bone(f"es{i}", grp, x_, y_)
        sl = c.slot(bn, "fx/spark", float(rng.uniform(30, 58)), color=hexa(hot, 1.0), role="sticky_spark")
        life = float(rng.uniform(0.12, min(0.22, per * 0.4)))
        b_fs.append(dict(b=bn, s=sl, ph=float(rng.uniform(0, per - life - 0.01)), life=life, rot=float(rng.uniform(-80, 80))))

    # ---- keys
    ts_fall = times_dense(0, Ti + 0.03, 90)
    c.show([s_st], 0, Ti + 0.03)
    c.bone_keys(b_st, "translate", ts_fall, lambda u: (0.0, y_at(min(u, Ti))[0]))
    c.bone_keys(b_st, "scale", ts_fall, lambda u: (1.0, max(0.02, abs(y_at(min(u, Ti))[1]) / v0)))
    c.color_keys(s_st, ts_fall, lambda u: hexa("FFFFFF", c.a(0.9 * (abs(y_at(min(u, Ti))[1]) / v0) ** 0.6 * (1 - smooth(u, Ti, Ti + 0.03)))))
    te = Ti + 0.75
    c.show([s_fl, s_sb] + [r_[1] for r_ in rings], Ti, te)
    ti = times_dense(Ti, te, 40)
    c.color_keys(s_fl, ti, lambda u: hexa(hot, c.a(0.75 * _flash(u - Ti))))
    c.bone_keys(b_fl, "scale", ti, lambda u: (0.5 + 0.8 * ease_out((u - Ti) / 0.2, 2.5),) * 2)
    for bn, sl, d0, k_ in rings:
        c.bone_keys(bn, "scale", ti, lambda u, d0=d0, k_=k_: (0.1 + 1.05 * k_ * min(1.0, _sedov(u - Ti - d0, 0.6)),) * 2 if u >= Ti + d0 else (0.0, 0.0))
        c.color_keys(sl, ti, lambda u, d0=d0, k_=k_: hexa(col if k_ == 1.0 else "FFFFFF", c.a(
            0.9 * k_ * max(0.0, 1 - _sedov(u - Ti - d0, 0.6)) ** 1.5 * smooth(u, Ti + d0, Ti + d0 + 0.02))))
    c.bone_keys(b_sb, "scale", ti, lambda u: (0.3 + 0.85 * ease_out((u - Ti) / 0.14, 3.0) - 0.15 * smooth(u, Ti + 0.2, te),) * 2)
    c.bone_keys(b_sb, "rotate", ti, lambda u: 30.0 * (u - Ti))
    c.color_keys(s_sb, ti, lambda u: hexa("FFFFFF", c.a(min(1.0, 1.3 * _flash(u - Ti, 9.0)) * (1 - smooth(u, Ti + 0.3, te)))))
    G = 1700.0
    for sp in sparks:
        t0, k_, L = sp["t0"], sp["k"], sp["life"]
        tdd = times_dense(t0, t0 + L, 30)

        def stt(u, sp=sp, t0=t0, k_=k_):
            t = max(0.0, u - t0)
            ee = (1 - math.exp(-k_ * t)) / k_
            vx, vy = sp["vx"] * math.exp(-k_ * t), sp["vy"] * math.exp(-k_ * t) - G * t
            sp_ = math.hypot(vx, vy)
            return sp["vx"] * ee, sp["vy"] * ee - 0.5 * G * t * t, math.degrees(math.atan2(vy, vx)) - 90.0, 1 + 1.6 * min(1.0, sp_ / 900)
        vals = [stt(u) for u in tdd]
        ang = np.degrees(np.unwrap(np.radians([v[2] for v in vals])))
        c.ab.bone(sp["b"], "translate", _uniq([(c.T(u), v[0], v[1]) for u, v in zip(tdd, vals)]), "linear")
        c.ab.bone(sp["b"], "rotate", _uniq([(c.T(u), float(a_)) for u, a_ in zip(tdd, ang)]), "linear")
        c.ab.bone(sp["b"], "scale", _uniq([(c.T(u), 1 / math.sqrt(v[3]), v[3]) for u, v in zip(tdd, vals)]), "linear")
        c.color_keys(sp["s"], tdd, lambda u, t0=t0, L=L: hexa(hot if (u - t0) < 0.4 * L else col, c.a(0.95 * max(0.0, 1 - (u - t0) / L) ** 1.2)))
        c.show([sp["s"]], t0, t0 + L)

    base, amp_b = float(P["glow"]), float(P["breath"])
    pop = _step(float(P["overshoot"]), 3.2)
    breathe = lambda s: base + amp_b * math.sin(math.pi * s / per) ** 2  # noqa: E731   s = time since the hold began

    def frame_a(u):
        if u < th:
            s = u - Ti
            return base + (1.0 - base) * (1 - smooth(u, Ti + 0.12, th)) / (1 + 6 * max(0.0, s - 0.03)) * smooth(s, 0, 0.03)
        return breathe((u - th) % per)
    c.show([s_glow, s_line], Ti, None)
    tf = sorted(set(times_dense(Ti, D, 40)) | {th + j * per for j in range(hold + 1)})
    c.color_keys(s_line, tf, lambda u: hexa(_hexmix(hot, col, (u - Ti) / 0.3), c.a(frame_a(u))))
    c.color_keys(s_glow, tf, lambda u: hexa(col, c.a(0.5 * frame_a(u))))
    tpop = times_dense(Ti, th, 60)
    c.bone_keys(b_fr, "scale", tpop, lambda u: (1 + 0.28 * (1 - pop(u - Ti)) * (1 - smooth(u, th - 0.15, th)),) * 2)

    def spark_keys(starts):
        for sp in b_fs:
            sc, ro, att = [], [], [(0.0, None)]
            for t0 in starts:
                s0, e0 = t0 + sp["ph"], t0 + sp["ph"] + sp["life"]
                att += [(c.T(s0), "fx"), (c.T(e0), None)]
                sc += [(c.T(s0), 0, 0), (c.T(s0 + sp["life"] * 0.4), 1, 1), (c.T(e0), 0, 0)]
                ro += [(c.T(s0), 0), (c.T(e0), sp["rot"])]
            if sc:
                c.ab.bone(sp["b"], "scale", _uniq(sc), "quad_in_out")
                c.ab.bone(sp["b"], "rotate", _uniq(ro), "linear")
            c.ab.slot_attachment(sp["s"], att)
    spark_keys([th + j * per for j in range(hold)])
    c.ab.event(c.T(Ti), "fx_wild_impact")
    for t0, *_ in B["contacts"][1:]:
        c.ab.event(c.T(t0), "fx_wild_bounce")

    # the hold loop: one breath, starting where the clip ends (same frame, same alpha), closing exactly
    hold_anim = ""
    if P["loop"]:
        hold_anim = f"{c.anim}_hold"
        saved = (c.ab, c.t0)
        c.ab, c.t0 = AnimBuilder(c.sk, hold_anim, replace=(c.anim == f"fx_{c.prefix}")), 0.0   # merged clips merge their hold too
        try:
            tl = times_dense(0, per, 40)
            c.show([s_glow, s_line], 0, None)
            c.color_keys(s_line, tl, lambda u: hexa(col, c.a(breathe(u))))
            c.color_keys(s_glow, tl, lambda u: hexa(col, c.a(0.5 * breathe(u))))
            spark_keys([0.0])
        finally:
            c.ab, c.t0 = saved
    hint = dict(parent=b_fr, front_of=s_line, mode="additive", seq_mode="loop", animation=hold_anim or c.anim,
                note="sticky lightning line: ae_template electric_frame params={width: %g, height: %g} -> ae_fx_to_spine with "
                     "these args into the hold loop" % (W, H))
    return c.result(duration=D * c.k, impact_at=c.T(Ti), rest_at=c.T(B["rest"]), hold_from=c.T(th), drop_bone=drop,
                    bounces=len(B["contacts"]), contacts=[c.T(t0) for t0, *_ in B["contacts"]], gravity=round(g * amp, 3),
                    hold_anim=hold_anim, hold_period=per * c.k, ae_hint=hint)


# ------------------------------------------------------------------ expanding_wild
def _slosh(A: float, tilt: float, hz: float, zeta: float):
    """Standing waves on a free surface between two walls, x' in [0, 1]: modes cos(n pi x'), deep-water dispersion
    omega_n = omega_1 sqrt(n), damped. The collapsing centre bulge drives the symmetric modes (2, 4); ``tilt`` adds the
    side-to-side mode 1. eta(x', s) for s >= 0 seconds after the release (0 at s = 0)."""
    w1 = 2 * math.pi * hz
    modes = [(1, tilt * A), (2, A), (4, 0.3 * A)]

    def eta(xp, s):
        if s <= 0:
            return 0.0
        v = 0.0
        for n, a in modes:
            if a == 0:
                continue
            w = w1 * math.sqrt(n)
            wd = w * math.sqrt(1 - zeta * zeta)
            v += a * math.cos(n * math.pi * xp) * math.exp(-zeta * w * s) * math.sin(wd * s)
        return v
    return eta, sum(abs(a) for _, a in modes)


def expanding_wild(c: Ctx, P: dict) -> dict:
    """The wild floods its reel like liquid: a 9-slice fill whose front corners move, a wobbling surface strand, a light
    column rising behind, the frame flashing on when the reel is full."""
    D = float(P["duration"])
    col = _hexn(P["color"], "FFC93C")
    hot = _hexn(P["color2"], "FFF6D0")
    W, H, cell = float(P["width"]), float(P["height"]), float(P["cell"])
    direction = str(P["direction"])
    if direction not in ("down", "up"):
        raise ValueError(f"direction must be down | up, got {direction!r}")
    Tfill, fade = float(P["fill"]), float(P["fade"])
    if Tfill <= 0 or fade < 0 or Tfill + fade + 0.2 > D:
        raise ValueError("need fill > 0, fade >= 0 and fill + fade + 0.2 <= duration")
    A, B_, tilt = float(P["wobble"]), float(P["bulge"]), float(P["tilt"])
    zeta, hz = float(P["damping"]), float(P["slosh_hz"])
    if not 0 < zeta < 1:
        raise ValueError("damping must be between 0 and 1")
    eta_s, amax = _slosh(A, tilt, hz, zeta)
    R = 1.25 * max(B_, amax) + 4                     # the mesh front stays this far behind the wavy surface
    s9 = min(48.0, W / 2)
    if cell - R <= 2 * s9 + 1 or cell > H:
        raise ValueError(f"cell must be between {2 * s9 + R + 1:.0f} and height (it is where the fill starts)")
    sgn = -1.0 if direction == "down" else 1.0      # the front moves this way
    y_o = H / 2 if direction == "down" else -H / 2  # the edge the fill starts from
    y_end = y_o + sgn * H
    fill_a = float(P["fill_alpha"])
    t_full = Tfill
    t_calm = min(t_full + 1.4, D - fade)
    hfun = lambda u: cell + (H - cell) * smooth(u, 0, Tfill)  # noqa: E731   eased height
    vmax = 1.5 * (H - cell) / Tfill                  # smoothstep's peak speed
    speed = lambda u: 6 * (H - cell) / Tfill * (u / Tfill) * (1 - u / Tfill) if 0 < u < Tfill else 0.0  # noqa: E731
    F = lambda u: y_o + sgn * hfun(u)  # noqa: E731   the front
    calm = lambda u: 1 - smooth(u, t_full + 0.9, t_calm)  # noqa: E731

    def eta(xp, u):
        """surface displacement ahead of the front (+ = further in the flow direction)"""
        flow = B_ * speed(u) / vmax * (1 - (2 * xp - 1) ** 2)      # Poiseuille: leads in the middle, pinned at the walls
        return (flow + eta_s(xp, u - t_full)) * calm(u)
    retract = lambda u: R * calm(u)  # noqa: E731
    out = lambda u: 1 - smooth(u, D - fade, D) if fade > 0 else 1.0  # noqa: E731
    rng = np.random.default_rng(c.seed + 311)
    grp = c.bone("expand", c.group, 0, 0)

    # fill (normal) and surface band (normal) first, then the light
    fill_hex = col
    s_fill, corners = c.slice9(grp, "fx/features_liquid", W, H, s9, make=tex_liquid, color=hexa(fill_hex, c.a(fill_a)), tag="fill", blend="normal", role="fill")
    front = ("bl", "br") if direction == "down" else ("tl", "tr")
    rows = 9
    b_surf = c.bone("surf", grp, 0, y_end, rot=90 * sgn)
    Hb = 3.2 * R + 10
    s_band, n_band = c.strand(b_surf, "fx/features_surface", Hb, W * 0.97, rows, x=-Hb / 2, color=hexa(fill_hex, c.a(fill_a)),
                              make=tex_surface, tag="band", role="surface")
    if "surface" not in c.art:
        c.sk.slot(s_band).blend = "normal"               # the band is liquid too: it occludes like the fill
    b_col = c.bone("column", grp)
    s_col = c.slot(b_col, "fx/column", W * 1.6, height=H * 1.08, role="column", stretch=True)
    s_hot, n_hot = c.strand(b_surf, "fx/strand_FFFFFF", 20.0, W * 0.92, rows, x=-6.0, make=lambda: tex_strand("FFFFFF"),
                            tag="hot", role="line")
    b_fr = c.bone("frame", grp)                      # the line sits just OUTSIDE the reel: additive light over the opaque fill
    s_line, _ = c.slice9(b_fr, f"fx/frame9_{col}", W + 16, H + 16, 48.0, make=lambda: tex_frame9(col), tag="line", role="frame")
    b_fl = c.bone("flash", grp, 0, y_end, sy=0.4)
    s_fl = c.slot(b_fl, "fx/glow", W * 2.4, role="flash")
    glints = []
    for i in range(int(P["count"])):
        t0 = float(rng.uniform(0.1, max(0.15, D - fade - 0.5)))
        life = float(rng.uniform(0.35, 0.7))
        filled = hfun(t0)
        yy = y_o + sgn * float(rng.uniform(0.15, 0.9)) * filled
        room = (H / 2 - 14) - yy                      # rising must not carry a glint out of the top of the reel
        bn = c.bone(f"gl{i}", grp, float(rng.uniform(-0.38, 0.38)) * W, yy)
        sl = c.slot(bn, "fx/mote", float(rng.uniform(9, 20)), role="mote")
        glints.append(dict(b=bn, s=sl, t0=t0, life=min(life, D - t0), rise=max(0.0, min(float(rng.uniform(10, 28)), room)),
                           col=str(rng.choice(["FFFFFF", hot]))))

    # ---- keys
    ts = sorted(set(times_dense(0, D, 30)) | set(times_dense(t_full, t_calm, 60)) | {t_full})
    c.show([s_fill, s_band, s_col, s_hot], 0, D if fade > 0 else None)
    for k_ in front:      # the fill mesh's front corners: setup = full reel, keyed back to the moving front
        c.bone_keys(corners[k_], "translate", ts, lambda u: (0.0, (F(u) - sgn * retract(u)) - y_end))
    c.bone_keys(b_surf, "translate", ts, lambda u: (0.0, F(u) - y_end))
    xs = [i / (rows - 1) for i in range(rows)]
    for nodes in (n_band, n_hot):
        for i, nb in enumerate(nodes):
            xp = xs[i] if direction == "down" else 1 - xs[i]       # rows run along +x (down) or -x (up)
            c.bone_keys(nb, "translate", ts, lambda u, xp=xp: (eta(xp, u), 0.0))
    c.color_keys(s_fill, ts, lambda u: hexa(fill_hex, c.a(fill_a * out(u))))
    c.color_keys(s_band, ts, lambda u: hexa(fill_hex, c.a(fill_a * out(u))))
    c.color_keys(s_hot, ts, lambda u: hexa(hot, c.a((0.55 + 0.45 * speed(u) / vmax * 1.5) * (0.6 + 0.4 * calm(u)) * out(u))))
    c.bone_keys(b_col, "translate", ts, lambda u: (0.0, (y_o + F(u)) / 2))
    c.bone_keys(b_col, "scale", ts, lambda u: (1.0 + 0.06 * math.sin(2 * math.pi * 1.2 * u), hfun(u) / H))
    c.color_keys(s_col, ts, lambda u: hexa(hot, c.a((0.1 + 0.14 * math.exp(-max(0.0, u - t_full) / 0.3) * smooth(u, t_full - 0.05, t_full)
                                                      + 0.04 * math.sin(2 * math.pi * 1.2 * u) ** 2) * out(u))))
    c.show([s_line], t_full, D if fade > 0 else None)
    tf = times_dense(t_full, D, 40)
    fr = lambda u: (0.55 + 0.45 / (1 + 7 * max(0.0, u - t_full - 0.03)) * smooth(u, t_full, t_full + 0.03)  # noqa: E731
                    + 0.08 * math.sin(2 * math.pi * 0.9 * (u - t_full)) ** 2) * out(u)
    c.color_keys(s_line, tf, lambda u: hexa(_hexmix(hot, col, (u - t_full) / 0.3), c.a(fr(u))))
    c.bone_keys(b_fr, "scale", times_dense(t_full, t_full + 0.5, 60), lambda u: (1 + 0.05 * math.exp(-(u - t_full) / 0.08) * smooth(u, t_full, t_full + 0.02)
                                                                                 * (1 - smooth(u, t_full + 0.35, t_full + 0.5)),) * 2)
    c.show([s_fl], t_full, min(D, t_full + 0.8))
    tfl = times_dense(t_full, min(D, t_full + 0.8), 40)
    c.color_keys(s_fl, tfl, lambda u: hexa(hot, c.a(min(1.0, _flash(u - t_full, 12.0)) * (1 - smooth(u, t_full + 0.5, t_full + 0.8)))))
    c.bone_keys(b_fl, "scale", tfl, lambda u: (0.5 + 0.7 * ease_out((u - t_full) / 0.25, 2.5),) * 2)
    for gl in glints:
        t0, L = gl["t0"], gl["life"]
        tg = times_dense(t0, t0 + L, 24)
        c.show([gl["s"]], t0, t0 + L)
        c.bone_keys(gl["b"], "translate", tg, lambda u, gl=gl, t0=t0, L=L: (0.0, gl["rise"] * ((u - t0) / L) ** 2))     # buoyant: y ~ t^2
        c.color_keys(gl["s"], tg, lambda u, gl=gl, t0=t0, L=L: hexa(gl["col"], c.a(0.9 * max(0.0, math.sin(math.pi * (u - t0) / L)) ** 1.2 * out(u))))
    c.ab.event(c.T(t_full), "fx_expanding_wild_full")
    return c.result(duration=D * c.k, full_at=c.T(t_full), fill_slot=s_fill, corner_bones=dict(corners), front_corners=list(front),
                    surface_bones=list(n_band), direction=direction)


# ------------------------------------------------------------------ scatter_trigger
def _scatter_plan(P: dict) -> dict:
    sc = P["scatters"] if P["scatters"] is not None else [[-300.0, 150.0, 0.0], [0.0, -150.0, 0.35], [300.0, 150.0, 0.7]]
    if not isinstance(sc, (list, tuple)) or not sc:
        raise ValueError("scatters must be a non-empty list of [x, y, land_time]")
    pts = [_vec(s, 3, "each scatter") for s in sc]
    if any(p[2] < 0 for p in pts):
        raise ValueError("land_time must be >= 0")
    cx, cy = _vec(P["centre"], 2, "centre")
    need = int(P["need"])
    if need < 1:
        raise ValueError("need must be >= 1")
    v = float(P["beam_speed"])
    if v <= 0:
        raise ValueError("beam_speed must be > 0")
    order = sorted(range(len(pts)), key=lambda i: pts[i][2])
    lands = [pts[i][2] for i in order]
    trig = len(pts) >= need
    plan = dict(pts=pts, order=order, centre=(cx, cy), need=need, triggered=trig)
    if not trig:
        plan["D"] = max(lands) + 1.2
        return plan
    t_ready = lands[need - 1]
    locks, fires, arrive = {}, {}, {}
    for k, i in enumerate(order):
        lk = max(t_ready, pts[i][2]) + float(P["lock_delay"]) + k * float(P["stagger"])
        locks[i] = lk
        fires[i] = lk + 0.12
        arrive[i] = fires[i] + math.hypot(cx - pts[i][0], cy - pts[i][1]) / v
    T = max(arrive.values()) + 0.1
    plan.update(locks=locks, fires=fires, arrive=arrive, trigger=T, D=T + 1.1)
    return plan


def scatter_trigger(c: Ctx, P: dict) -> dict:
    """Scatters ring as they land; with enough of them they lock on in turn and each fires a beam to the centre, which
    charges up and bursts: the bonus is triggered."""
    col = _hexn(P["color"], "FFC83C")
    beam_c = _hexn(P["color2"], "6FD8FF")
    size = float(P["size"])
    plan = _scatter_plan(P)
    D, pts, cx, cy = plan["D"], plan["pts"], *plan["centre"]
    trig = plan["triggered"]
    T = plan.get("trigger", D)
    N = len(pts)
    tau = float(P["charge_tau"])
    land_spring = _step(0.22, 3.2)
    grp = c.bone("scatter", c.group, 0, 0)

    def spend(u):
        """the halos and beams spend their light in the burst"""
        if not trig or u < T:
            return 1.0
        return math.exp(-(u - T) / 0.09) * (1 - smooth(u, T + 0.2, T + 0.4))
    end_all = (T + 0.4) if trig else D
    fade_end = (lambda u: 1.0) if trig else (lambda u: 1 - smooth(u, D - 0.4, D))
    land_n = 0
    for k, i in enumerate(plan["order"]):
        x, y, L = pts[i]
        land_n += 1
        g_i = c.bone(f"s{i}", grp, x, y)
        b_glow, b_rune, b_ring, b_fl = c.bone(f"s{i}_glow", g_i), c.bone(f"s{i}_rune", g_i), c.bone(f"s{i}_ring", g_i), c.bone(f"s{i}_fl", g_i)
        s_glow = c.slot(b_glow, "fx/glow", size * 1.7, role="glow")
        s_rune = c.slot(b_rune, f"fx/features_runes_{col}", size * 1.45, make=lambda: tex_halo_runes(col), role="rune")
        s_ring = c.slot(b_ring, "fx/ring", size * 1.9, role="ring")
        s_fl = c.slot(b_fl, "fx/glow", size * 1.1, role="flash")
        lk = plan["locks"][i] if trig else None
        kick = (lambda u, lk=lk: math.exp(-((u - lk) / 0.06) ** 2)) if trig else (lambda u: 0.0)
        c.show([s_glow, s_rune], L, end_all)
        c.show([s_ring, s_fl], L, min(end_all, L + 0.7) if trig else min(D, L + 0.7))
        ts = sorted(set(times_dense(L, end_all, 30)) | ({lk} if trig else set()))
        c.bone_keys(b_rune, "scale", ts, lambda u, L=L, kick=kick: ((0.2 + 0.8 * land_spring(u - L)) * (1 + 0.16 * kick(u)),) * 2)
        c.bone_keys(b_rune, "rotate", ts, lambda u, L=L, lk=lk: -40.0 * (u - L) - (140.0 * ease_out((u - lk) / 0.5, 2.0) if trig and u > lk else 0.0))
        c.color_keys(s_rune, ts, lambda u, L=L, kick=kick: hexa("FFFFFF", c.a(smooth(u, L, L + 0.08) * (0.72 + 0.18 * math.sin(2 * math.pi * 1.3 * (u - L)) ** 2
                                                                                                    + 0.3 * kick(u)) * spend(u) * fade_end(u))))
        c.color_keys(s_glow, ts, lambda u, L=L, kick=kick: hexa(col, c.a(smooth(u, L, L + 0.05) * (0.32 + 0.5 * _flash(u - L, 8.0) + 0.3 * kick(u)) * spend(u) * fade_end(u))))
        c.bone_keys(b_glow, "scale", ts, lambda u, L=L: (0.7 + 0.3 * ease_out((u - L) / 0.3, 2.5),) * 2)
        tr = times_dense(L, L + 0.7, 40)
        c.bone_keys(b_ring, "scale", tr, lambda u, L=L: (0.15 + 0.95 * _sedov(u - L, 0.7),) * 2)
        c.color_keys(s_ring, tr, lambda u, L=L: hexa(col, c.a(0.85 * max(0.0, 1 - _sedov(u - L, 0.7)) ** 1.5 * smooth(u, L, L + 0.02))))
        c.color_keys(s_fl, tr, lambda u, L=L: hexa("FFF6DC", c.a(min(1.0, 1.1 * _flash(u - L, 20.0)))))
        c.bone_keys(b_fl, "scale", tr, lambda u, L=L: (0.5 + 0.7 * ease_out((u - L) / 0.2, 2.5),) * 2)
        c.ab.event(c.T(L), "fx_scatter_land", int=land_n)
        if not trig:
            continue
        # lock on: the reticle drops in big and spinning, snaps on at lk, recoils when it fires
        fi, ai = plan["fires"][i], plan["arrive"][i]
        lock_in = 0.3
        b_ret, b_lr = c.bone(f"s{i}_ret", g_i), c.bone(f"s{i}_lring", g_i)
        s_ret = c.slot(b_ret, f"fx/reticle_{beam_c}", size * 1.25, make=lambda: tex_reticle(beam_c), role="reticle")
        s_lr = c.slot(b_lr, "fx/ring", size * 1.6, role="ring")
        r0 = lk - lock_in
        c.show([s_ret], r0, fi + 0.3)
        c.show([s_lr], lk, lk + 0.45)
        trt = times_dense(r0, fi + 0.3, 40)
        app = lambda u, r0=r0: ease_out((u - r0) / lock_in, 3.0)  # noqa: E731
        leave = lambda u, fi=fi: smooth(u, fi, fi + 0.3)  # noqa: E731
        c.bone_keys(b_ret, "scale", trt, lambda u, app=app, leave=leave, lk=lk: ((2.4 - 1.4 * app(u)) * (1 + 0.12 * math.exp(-((u - lk) / 0.06) ** 2))
                                                                                * (1 + 0.3 * leave(u)),) * 2)
        c.bone_keys(b_ret, "rotate", trt, lambda u, app=app, leave=leave: -150.0 * (1 - app(u)) + 45.0 * leave(u))
        c.color_keys(s_ret, trt, lambda u, r0=r0, leave=leave: hexa("FFFFFF", c.a(smooth(u, r0, r0 + 0.1) * (1 - leave(u)))))
        tlr = times_dense(lk, lk + 0.45, 40)
        c.bone_keys(b_lr, "scale", tlr, lambda u, lk=lk: (0.5 + 0.9 * ease_out((u - lk) / 0.45, 2.4),) * 2)
        c.color_keys(s_lr, tlr, lambda u, lk=lk: hexa(beam_c, c.a(0.85 * (1 - smooth(u, lk, lk + 0.45)))))
        c.ab.event(c.T(lk), "fx_scatter_lock", int=k + 1)
        # the beam: its front travels at one constant speed from the scatter to the centre
        dx, dy = cx - x, cy - y
        d = math.hypot(dx, dy) or 1.0
        ux, uy = dx / d, dy / d
        b_beam = c.bone(f"s{i}_beam", grp, x, y, rot=math.degrees(math.atan2(dy, dx)) - 90)
        s_body = c.slot(b_beam, "fx/column", size * 0.6, oy=d / 2, height=d, role="beam", anchor="bottom", stretch=True)
        s_core = c.slot(b_beam, "fx/strand_FFFFFF", size * 0.22, oy=d / 2, height=d, make=lambda: tex_strand("FFFFFF"), role="core",
                        anchor="bottom", stretch=True)
        b_head = c.bone(f"s{i}_head", grp, x, y)
        s_head = c.slot(b_head, "fx/glow", size * 0.75, role="head")
        v = float(P["beam_speed"])
        reach = lambda u, fi=fi, d=d: min(1.0, max(0.0, v * (u - fi) / d))  # noqa: E731
        tb = sorted(set(times_dense(fi, end_all, 60)) | {ai})
        c.show([s_body, s_core], fi, end_all)
        c.show([s_head], fi, ai + 0.12)
        thin = lambda u, ai=ai: 1.0 if u < ai else 0.35 + 0.65 / (1 + 8 * (u - ai))  # noqa: E731
        c.bone_keys(b_beam, "scale", tb, lambda u, reach=reach, thin=thin, fi=fi: ((0.4 + 0.6 * ease_out((u - fi) / 0.08, 2)) * thin(u), max(0.001, reach(u))))
        c.color_keys(s_body, tb, lambda u, fi=fi, thin=thin: hexa(beam_c, c.a(0.75 * smooth(u, fi, fi + 0.03) * thin(u) * spend(u))))
        c.color_keys(s_core, tb, lambda u, fi=fi, thin=thin: hexa("FFFFFF", c.a(0.95 * smooth(u, fi, fi + 0.03) * thin(u) * spend(u))))
        th_ = times_dense(fi, ai + 0.12, 60)
        c.bone_keys(b_head, "translate", th_, lambda u, reach=reach, d=d, ux=ux, uy=uy: (ux * d * reach(u), uy * d * reach(u)))
        c.color_keys(s_head, th_, lambda u, ai=ai: hexa(beam_c, c.a(0.95 * (1 - smooth(u, ai, ai + 0.12)))))

    centre_res = {}
    if trig:
        arr = sorted(plan["arrive"].values())
        a0 = arr[0]
        Q = lambda u: sum(1 - math.exp(-(u - a) / tau) for a in arr if u > a) / N  # noqa: E731   capacitor charge, 0..1
        Qint = lambda u: sum((u - a) - tau * (1 - math.exp(-(u - a) / tau)) for a in arr if u > a) / N  # noqa: E731   its integral
        g_c = c.bone("centre", grp, cx, cy)
        b_cg, b_cr, b_r1, b_r2, b_ry, b_cf = (c.bone("c_glow", g_c), c.bone("c_rune", g_c), c.bone("c_ring1", g_c),
                                              c.bone("c_ring2", g_c), c.bone("c_rays", g_c), c.bone("c_flash", g_c))
        s_cg = c.slot(b_cg, "fx/glow", size * 2.4, role="centre_glow")
        s_cr = c.slot(b_cr, f"fx/features_runes_{beam_c}", size * 1.8, make=lambda: tex_halo_runes(beam_c), role="centre_rune")
        s_r1 = c.slot(b_r1, "fx/ring", size * 3.6, role="ring")
        s_r2 = c.slot(b_r2, "fx/ring", size * 3.6, role="ring")
        s_ry = c.slot(b_ry, f"fx/rays_{beam_c}", size * 3.4, make=lambda: tex_rays(beam_c), role="rays")
        s_cf = c.slot(b_cf, "fx/glow", size * 1.6, role="flash")
        tc = sorted(set(times_dense(a0 - 0.05, D, 40)) | set(arr) | {T})
        c.show([s_cg, s_cr], a0 - 0.05, D)
        burst = lambda u: _flash(u - T, 7.0)  # noqa: E731
        endf = lambda u: 1 - smooth(u, D - 0.5, D)  # noqa: E731
        c.color_keys(s_cg, tc, lambda u: hexa(beam_c, c.a((0.15 * smooth(u, a0 - 0.05, a0) + 0.65 * Q(u) * spend(u) + 0.9 * burst(u)) * endf(u))))
        c.bone_keys(b_cg, "scale", tc, lambda u: (0.55 + 0.45 * Q(u) + 0.6 * ease_out((u - T) / 0.4, 2.5) * (u > T),) * 2)
        c.color_keys(s_cr, tc, lambda u: hexa("FFFFFF", c.a((0.2 * smooth(u, a0 - 0.05, a0) + 0.8 * Q(u)) * (1 if u < T else math.exp(-(u - T) / 0.25)) * endf(u))))
        c.bone_keys(b_cr, "rotate", tc, lambda u: -50.0 * (u - a0) - 420.0 * Qint(u))          # spins up as it charges
        c.bone_keys(b_cr, "scale", tc, lambda u: (0.55 + 0.45 * Q(u) + 0.5 * ease_out((u - T) / 0.5, 2.2) * (u > T),) * 2)
        tt = times_dense(T, D, 40)
        c.show([s_r1, s_r2, s_ry, s_cf], T, D)
        for bn, sl, d0, k_, cc in ((b_r1, s_r1, 0.0, 1.0, beam_c), (b_r2, s_r2, 0.06, 0.75, "FFFFFF")):
            c.bone_keys(bn, "scale", tt, lambda u, d0=d0, k_=k_: (0.1 + 1.0 * k_ * _sedov(u - T - d0, D - T),) * 2 if u >= T + d0 else (0.0, 0.0))
            c.color_keys(sl, tt, lambda u, d0=d0, k_=k_, cc=cc: hexa(cc, c.a(0.9 * k_ * max(0.0, 1 - _sedov(u - T - d0, D - T)) ** 1.6 * smooth(u, T + d0, T + d0 + 0.02))))
        c.bone_keys(b_ry, "rotate", tt, lambda u: 35.0 * ease_out((u - T) / (D - T), 1.5))
        c.bone_keys(b_ry, "scale", tt, lambda u: (0.4 + 0.6 * ease_out((u - T) / 0.25, 3.0),) * 2)
        c.color_keys(s_ry, tt, lambda u: hexa("FFFFFF", c.a(min(1.0, smooth(u, T, T + 0.04) * (0.25 + 0.75 / (1 + 10 * max(0.0, u - T - 0.04)))) * endf(u))))
        c.color_keys(s_cf, tt, lambda u: hexa("FFFFFF", c.a(min(1.0, 1.2 * _flash(u - T, 14.0)))))
        c.bone_keys(b_cf, "scale", tt, lambda u: (0.6 + 1.0 * ease_out((u - T) / 0.2, 2.5),) * 2)
        c.ab.event(c.T(T), "fx_scatter_bonus")      # fx_scatter_trigger is the recipe's own start event
        centre_res = dict(trigger_at=c.T(T), locks=[c.T(plan["locks"][i]) for i in plan["order"]],
                          fires=[c.T(plan["fires"][i]) for i in plan["order"]], arrivals=[c.T(plan["arrive"][i]) for i in plan["order"]])
    return c.result(duration=D * c.k, triggered=trig, scatters=N, need=plan["need"],
                    lands=[c.T(pts[i][2]) for i in plan["order"]], **centre_res)


# ------------------------------------------------------------------ free_spins_transition
def _infall(tau: float, Tp: float, core: float, swirl: float):
    """Accelerating infall s(t) = a - b e^(t/tau): 1 at t=0, exactly 0 at Tp, speed growing exponentially. Spin with
    conserved angular momentum, omega (s + core)^2 = omega0, integrated exactly:
    theta = omega0 tau [F(w) - F(1)], w = e^(t/tau), F(w) = 1/(A(A - b w)) + ln(w / (A - b w)) / A^2, A = a + core.
    omega0 is solved so the total turn over the pull is ``swirl`` degrees."""
    E = math.exp(Tp / tau)
    b = 1 / (E - 1)
    a = 1 + b
    A = a + core
    Fw = lambda w: 1 / (A * (A - b * w)) + math.log(w / (A - b * w)) / (A * A)  # noqa: E731
    span = tau * (Fw(E) - Fw(1.0))
    w0 = swirl / span                                   # deg/s at full size
    s = lambda t: min(1.0, max(0.0, a - b * math.exp(min(t, Tp) / tau))) if t > 0 else 1.0  # noqa: E731
    th = lambda t: w0 * tau * (Fw(math.exp(min(max(t, 0.0), Tp) / tau)) - Fw(1.0))  # noqa: E731
    return s, th, w0


def free_spins_transition(c: Ctx, P: dict) -> dict:
    """A portal opens behind the reels, the screen is pulled into it (accelerating, swirling faster as it shrinks), the
    portal collapses, a puff bursts in front and the screen springs back out, unwinding to rest."""
    col = _hexn(P["color"], "4A78FF")
    flash_c = _hexn(P["color2"], "B050FF")
    smoke = _hexn(P["smoke"], "EEE6FF")
    size = float(P["size"])
    t_open, pull_at, pull = float(P["open"]), float(P["pull_at"]), float(P["pull"])
    tau, core, swirl = float(P["tau"]), float(P["core"]), float(P["swirl"])
    if pull <= 0 or tau <= 0 or core <= 0 or t_open <= 0 or pull_at < 0:
        raise ValueError("open, pull, tau and core must be > 0 and pull_at >= 0")
    gap = float(P["gap"])
    if gap < 0.02:
        raise ValueError("gap must be >= 0.02 s (the screen is swapped while it is gone)")
    T_in = pull_at + pull
    T_out = T_in + gap
    D = T_out + 1.15
    s_fn, th_fn, w0 = _infall(tau, pull, core, swirl)
    emerge = _step(float(P["overshoot"]), float(P["emerge_hz"]))
    unwind = float(P["unwind"])
    open_spring = _step_at(0.12, t_open)          # the portal is fully open at t_open
    rng = np.random.default_rng(c.seed + 331)
    sk = c.sk

    # the screen: the game's bone under a carrier at the portal centre, or our own bone to parent the screen under
    under: set[str] = set()
    if P["screen"]:
        gx, gy = sk.world()[c.group].x, sk.world()[c.group].y
        pull_b = _carrier(c, str(P["screen"]), "pull", (gx, gy))
        under = set(sk.descendants(pull_b))
        mine = [s.name for s in sk.slots if s.bone in under]
        if mine and not c.behind and not c.front_of:
            c.behind = mine[0]                      # the portal goes behind the screen
    else:
        pull_b = c.bone("screen", c.group)
        mine = []
    grp = c.bone("fs", c.group, 0, 0)

    # ---- run A: the portal (behind the screen); the disc occludes (normal), first in the run
    b_por = c.bone("portal", grp)
    s_disc = c.slot(b_por, f"fx/disc_{col}", size, color=hexa("FFFFFF", c.a(0.92)), make=lambda: tex_disc(col), blend="normal", role="disc")
    b_rg = c.bone("rim", b_por)
    s_rg = c.slot(b_rg, "fx/ring", size * 1.35, role="glow")
    b_sa, b_sb = c.bone("swirl_a", b_por), c.bone("swirl_b", b_por)
    s_sa = c.slot(b_sa, f"fx/swirl3_{col}", size * 1.02, make=lambda: tex_swirl(3, col), role="swirl_a")
    s_sb = c.slot(b_sb, f"fx/swirl5_{col}", size * 0.82, make=lambda: tex_swirl(5, col, seed=5, twist=3.1), role="swirl_b")
    comets = []
    for i in range(2):
        bn = c.bone(f"cm{i}", b_por)
        comets.append((bn, c.slot(bn, "fx/comet", size * (0.95 - 0.12 * i), make=lambda: tex_comet(), role="comet"), i))
    ring_after = c.last_slot
    specks = []
    for i in range(int(P["specks"])):
        piv = c.bone(f"sp{i}", b_por)
        mb = c.bone(f"sp{i}m", piv, 100, 0)
        sl = c.slot(mb, "fx/mote", float(rng.uniform(6, 12)), role="mote")
        specks.append(dict(piv=piv, mb=mb, s=sl, r0=float(rng.uniform(0.3, 0.5)) * size, a0=float(rng.uniform(0, 360)),
                           L=float(rng.uniform(0.45, 0.8)), ph=float(rng.uniform(0, 1)), col=str(rng.choice(["FFFFFF", "BFE8FF", "E8DCFF"]))))
    b_pf = c.bone("pflash", grp)
    s_pf = c.slot(b_pf, "fx/glow", size * 1.6, role="flash")
    run_a_end = c.last_slot

    # ---- run B: the puff, in front of the screen (clouds normal first, then the light)
    if mine:
        c.last_slot = [s.name for s in sk.slots if s.bone in under][-1]
    b_puff = c.bone("puff", grp)
    R_, ps = float(P["radius"]), float(P["puff_size"])
    lobes = []
    for i in range(int(P["count"])):
        a = 2 * math.pi * i / max(1, int(P["count"])) + float(rng.uniform(-0.3, 0.3))
        bn = c.bone(f"lb{i}", b_puff)
        sl = c.slot(bn, "fx/cloud", ps * float(rng.uniform(0.8, 1.2)), blend="normal", role="cloud")
        lobes.append(dict(b=bn, s=sl, a=a, d=R_ * float(rng.uniform(0.55, 1.0)), g=float(rng.uniform(1.0, 1.5)),
                          rot=float(rng.uniform(-40, 40)), dl=float(rng.uniform(0, 0.06)), tint=("FFFFFF" if rng.random() < 0.5 else smoke)))
    b_core = c.bone("pcore", b_puff)
    s_core = c.slot(b_core, "fx/cloud", ps * 1.5, blend="normal", role="cloud")
    smoke_after = c.last_slot
    b_of, b_or = c.bone("oflash", b_puff), c.bone("oring", b_puff)
    s_of = c.slot(b_of, "fx/glow", ps * 3.0, role="puff_flash")
    s_or = c.slot(b_or, "fx/ring", ps * 3.2, role="ring")

    # ---- keys: the screen (carrier)
    tp = sorted(set(times_dense(pull_at, T_in, 90)) | set(times_dense(T_in - 0.12, T_in, 400)))
    te = times_dense(T_out, D, 60)
    ts_screen = ([0.0] if pull_at > 0 else []) + tp + te

    def scale_at(u):
        if u <= pull_at:
            return 1.0
        if u <= T_in:
            return s_fn(u - pull_at)
        if u < T_out:
            return 0.0
        s = u - T_out
        dev = (emerge(s) - 1) * (1 - smooth(u, D - 0.3, D))
        return max(0.0, 1 + dev)

    def rot_at(u):
        if u <= pull_at:
            return 0.0
        if u <= T_in:
            return -th_fn(u - pull_at)                      # clockwise, like the vortex
        s = max(0.0, u - T_out)
        return unwind * math.exp(-s / 0.22) * (1 - smooth(u, D - 0.35, D)) if u >= T_out else unwind
    ts_s = sorted(set(ts_screen) | {T_in, T_out, D})
    _merge_keys(c, pull_b, "scale", ts_s, lambda u: (scale_at(u),) * 2, "mul")
    rot_pts = [u for u in ts_s if u <= T_in] + [T_in + 0.002] + [u for u in ts_s if u > T_in + 0.002]
    _merge_rot(c, pull_b, rot_pts, rot_at)        # the jump to `unwind` happens at scale 0, unseen

    # ---- keys: the portal
    c.show([s_disc, s_rg, s_sa, s_sb] + [cm[1] for cm in comets], 0, T_in + 0.14)
    tpo = sorted(set(times_dense(0, T_in + 0.14, 40)) | set(times_dense(T_in - 0.1, T_in + 0.14, 200)))
    collapse = lambda u: 1 - smooth(u, T_in - 0.02, T_in + 0.12) ** 0.7  # noqa: E731
    c.bone_keys(b_por, "scale", tpo, lambda u: ((0.05 + 0.95 * open_spring(u)) * collapse(u)
                                                 * (1 + 0.08 * smooth(u, pull_at, T_in)),) * 2)
    spin = lambda u: -200.0 * u - 0.35 * th_fn(min(max(0.0, u - pull_at), pull))  # noqa: E731   co-rotates with what falls in
    c.bone_keys(b_sa, "rotate", tpo, spin)
    c.bone_keys(b_sb, "rotate", tpo, lambda u: 2.4 * spin(u))                # inner layer faster (differential rotation)
    for bn, sl, i in comets:
        c.bone_keys(bn, "rotate", tpo, lambda u, i=i: 180.0 * i + 1.7 * spin(u))
        c.color_keys(sl, tpo, lambda u, i=i: hexa("FFFFFF", c.a((0.35 + 0.55 * smooth(u, pull_at, T_in)) * smooth(u, 0.1 + 0.1 * i, 0.35 + 0.1 * i))))
    opa = lambda u: smooth(u, 0, 0.15)  # noqa: E731
    c.color_keys(s_disc, tpo, lambda u: hexa("FFFFFF", c.a(0.92 * opa(u))))
    c.color_keys(s_sa, tpo, lambda u: hexa("FFFFFF", c.a(0.85 * opa(u))))
    c.color_keys(s_sb, tpo, lambda u: hexa("FFFFFF", c.a((0.45 + 0.3 * smooth(u, pull_at, T_in)) * opa(u))))
    c.color_keys(s_rg, tpo, lambda u: hexa(col, c.a((0.55 + 0.3 * smooth(u, pull_at, T_in)) * opa(u))))
    for sp in specks:
        tsd = set(times_dense(0.05, T_in, 30))
        k = 0
        while True:
            k += 1
            wrap = (k - sp["ph"]) * sp["L"]
            if wrap >= T_in:
                break
            if wrap > 0.05:
                tsd.update([wrap - 0.002, wrap])
        tsd = sorted(t for t in tsd if 0.05 <= t <= T_in)
        q = lambda u, sp=sp: (u / sp["L"] + sp["ph"]) % 1.0  # noqa: E731
        kep = lambda qq: ((1 - 0.8 * qq) ** -0.5 - 1) / ((0.2) ** -0.5 - 1)  # noqa: E731   Keplerian: whips round near the centre
        c.show([sp["s"]], 0.05, T_in)
        c.bone_keys(sp["piv"], "rotate", tsd, lambda u, sp=sp, q=q: sp["a0"] - 330.0 * kep(q(u)))
        c.bone_keys(sp["mb"], "translate", tsd, lambda u, sp=sp, q=q: (sp["r0"] * (1 - 0.8 * q(u)) - 100, 0.0))
        c.color_keys(sp["s"], tsd, lambda u, sp=sp, q=q: hexa(sp["col"], c.a(0.9 * max(0.0, math.sin(math.pi * q(u))) ** 0.8 * smooth(u, 0.05, 0.3))))
    tpf = times_dense(T_in - 0.02, T_in + 0.6, 40)
    c.show([s_pf], T_in - 0.02, T_in + 0.6)
    c.color_keys(s_pf, tpf, lambda u: hexa(flash_c, c.a(min(1.0, 1.1 * _flash(u - T_in + 0.02, 12.0)))))
    c.bone_keys(b_pf, "scale", tpf, lambda u: (0.5 + 0.6 * ease_out((u - T_in) / 0.2, 2.5),) * 2)

    # ---- keys: the puff on the other side
    c.show([x["s"] for x in lobes] + [s_core, s_of, s_or], T_out, D)
    tq = times_dense(T_out, D, 30)
    env = lambda u, dl: smooth(u, T_out + dl, T_out + dl + 0.08) * (1 - smooth(u, T_out + dl + 0.4, D))  # noqa: E731
    for lb in lobes:
        dl = lb["dl"]
        e_ = lambda u, dl=dl: ease_out((u - T_out - dl) / 0.6, 2.6) if u >= T_out + dl else 0.0  # noqa: E731
        c.bone_keys(lb["b"], "translate", tq, lambda u, lb=lb, e_=e_: (math.cos(lb["a"]) * lb["d"] * e_(u), math.sin(lb["a"]) * lb["d"] * 0.85 * e_(u)
                                                                        + 30.0 * max(0.0, u - T_out)))
        c.bone_keys(lb["b"], "scale", tq, lambda u, lb=lb, dl=dl: ((0.3 + (lb["g"] - 0.3) * ease_out((u - T_out - dl) / 0.5, 2.2)) if u >= T_out + dl else 0.0,) * 2)
        c.bone_keys(lb["b"], "rotate", tq, lambda u, lb=lb: lb["rot"] * ease_out((u - T_out) / 0.9, 1.6))
        c.color_keys(lb["s"], tq, lambda u, lb=lb, dl=dl: hexa(lb["tint"], c.a(0.96 * env(u, dl))))
    c.bone_keys(b_core, "scale", tq, lambda u: (0.3 + 1.0 * ease_out((u - T_out) / 0.45, 2.2),) * 2)
    c.color_keys(s_core, tq, lambda u: hexa("FFFFFF", c.a(0.96 * env(u, 0.0))))
    c.color_keys(s_of, tq, lambda u: hexa(flash_c, c.a(min(1.0, 0.95 * _flash(u - T_out, 10.0)))))
    c.bone_keys(b_of, "scale", tq, lambda u: (0.5 + 0.8 * ease_out((u - T_out) / 0.25, 2.5),) * 2)
    c.bone_keys(b_or, "scale", tq, lambda u: (0.2 + 1.1 * ease_out((u - T_out) / 0.6, 2.5),) * 2)
    c.color_keys(s_or, tq, lambda u: hexa(smoke, c.a(0.6 * (1 - smooth(u, T_out, T_out + 0.6)) * smooth(u, T_out, T_out + 0.03))))
    c.ab.event(c.T(T_in), "fx_free_spins_in")
    c.ab.event(c.T(T_out), "fx_free_spins_out")
    ring = dict(parent=b_por, front_of=ring_after, mode="additive", seq_mode="loop", until=c.T(T_in + 0.14),
                note="plasma ring: ae_template portal_ring -> ae_fx_to_spine with these args (parent is the portal bone, so the "
                     "ring opens and collapses with it); scale ~ %.2f for a 384px comp" % (size * 1.65 / 384))
    haze = dict(parent=b_puff, front_of=smoke_after, mode="alpha", seq_mode="once", start=c.T(T_out), until=c.T(D),
                note="realistic smoke: ae_template smoke_haze (or smoke_puff) -> ae_fx_to_spine with these args, over the cartoon puff")
    return c.result(duration=D * c.k, pull_bone=pull_b, in_at=c.T(T_in), out_at=c.T(T_out), pull_from=c.T(pull_at),
                    omega0=round(w0 / c.k, 3), portal_run=[s_disc, run_a_end], puff_run=[lobes[0]["s"] if lobes else s_core, s_or],
                    ring_hint=ring, ae_hint=ring, smoke_hint=haze)


# ------------------------------------------------------------------ registry
def _wild_default_duration() -> float:
    B = _bounces(480.0, 0.38, 0.3, 0.06)
    return round(0.38 + max(0.6, B["rest"] - 0.38 + 0.05) + 2 * 0.8, 4)


def _scatter_default_duration() -> float:
    return round(_scatter_plan(dict(scatters=None, centre=[0, 0], need=3, beam_speed=1400.0, lock_delay=0.35, stagger=0.25))["D"], 4)


RECIPES.update({
    "wild_land": dict(
        fn=wild_land, duration=_wild_default_duration(), kind="one-shot", color="FFC93C", count=10,
        summary="A wild drops in with exaggerated real physics: free fall under gravity solved to land at `fall`, bounces with a "
                "coefficient of restitution (each bounce bounce^2 as high, Hertz contact times), stretched along its speed and "
                "squashed on contact (area-preserving, first squash exact), a motion-blur streak, 1/t flash, Sedov rings, sparks; "
                "then a sticky frame glow snaps on (exact spring overshoot) and breathes. Also writes <anim>_hold, a loop that "
                "starts on the clip's last frame and holds the sticky glow. Moves your wild through a carrier (wild=). "
                "Events fx_wild_land, fx_wild_impact, fx_wild_bounce. ae_hint: electric_frame line for the hold.",
        anchor="Centre of the cell the wild lands in (width x height); it falls from `drop` above.",
        options=dict(width=(150.0, "cell width"), height=(150.0, "cell height"),
                     wild=("", "bone of the wild symbol: a carrier is inserted above it at the cell's base and dropped/squashed "
                               "(your keys stay untouched). Empty: the result's drop_bone is a bone to parent the wild under"),
                     drop=(480.0, "fall height (units)"), fall=(0.38, "seconds to land (gravity is solved from it)"),
                     bounce=(0.3, "coefficient of restitution, 0..1 (0 = no bounce)"), squash=(0.3, "squash at the first contact"),
                     stretch=(0.22, "stretch along the speed at impact speed"), contact=(0.06, "first contact time (s)"),
                     color2=("FFF4C8", "hot colour (flash, sparks, frame snap)"), overshoot=(0.25, "frame snap spring overshoot"),
                     pulse=(0.8, "breathing period of the sticky glow (s) = the hold loop's length"),
                     hold=(2, "breaths of the sticky glow inside this clip"), glow=(0.6, "sticky glow resting alpha"),
                     breath=(0.3, "sticky glow breathing depth"), sparks=(4, "electric sparks per breath along the frame"),
                     loop=(True, "also write the <anim>_hold loop animation"))),
    "expanding_wild": dict(
        fn=expanding_wild, duration=2.4, kind="window", color="FFC93C", count=14, normal_blend=True,
        summary="An expanding wild floods its reel like liquid: a 9-slice fill whose front corner bones move (eased height), "
                "the front leading in the middle while it flows (Poiseuille profile), then sloshing in damped standing waves "
                "(modes cos(n pi x/W), deep-water dispersion) on a strand-mesh surface; a light column rises with it, rising glints, "
                "and the frame flashes on when it is full. Events fx_expanding_wild, fx_expanding_wild_full.",
        anchor="Reel centre (width x height); the fill starts from one cell at the top (direction=down) or bottom.",
        options=dict(width=(150.0, "reel width"), height=(450.0, "reel height"), cell=(150.0, "height it starts from (the wild's cell)"),
                     direction=("down", "down (from the top cell) | up (from the bottom cell)"), fill=(0.6, "seconds to fill"),
                     wobble=(9.0, "standing-wave amplitude (units)"), bulge=(16.0, "how far the middle leads while it flows"),
                     tilt=(0.5, "side-to-side slosh, relative to the symmetric modes"), slosh_hz=(2.4, "fundamental slosh frequency (Hz)"),
                     damping=(0.14, "damping ratio of the slosh, 0..1"), fill_alpha=(1.0, "fill opacity (it covers the reel; below 1 the surface band shows where it overlaps)"),
                     color2=("FFF6D0", "hot colour (surface line, column, flash)"), fade=(0.35, "seconds to fade out at the end (0 = stays)"))),
    "scatter_trigger": dict(
        fn=scatter_trigger, duration=_scatter_default_duration(),
        kind="one-shot", color="FFC83C",
        summary="Bonus trigger: each scatter rings as it lands (rune halo on an exact-overshoot spring, Sedov ring, 1/t flash); with "
                "`need` or more they lock on in turn (reticle drops in spinning and snaps) and fire beams to the centre at one constant "
                "speed; the centre charges like a capacitor (1 - e^-t/tau per beam) and bursts (1/t bloom, rays, Sedov rings) when the "
                "last one lands. Events fx_scatter_trigger (start), fx_scatter_land (int = count landed), fx_scatter_lock (int = order), fx_scatter_bonus (the burst).",
        anchor="Origin of the scatter and centre offsets.",
        options=dict(scatters=(None, "[[x, y, land_time], ...] relative to x, y (default: three, landing 0 / 0.35 / 0.7 s)"),
                     centre=([0.0, 0.0], "[x, y] where the beams meet (the bonus)"), need=(3, "scatters needed to trigger"),
                     size=(150.0, "symbol size"), color2=("6FD8FF", "beam, reticle and centre colour"),
                     lock_delay=(0.35, "seconds after the deciding scatter lands before the first lock"),
                     stagger=(0.25, "seconds between locks"), beam_speed=(1400.0, "beam front speed (units/s)"),
                     charge_tau=(0.12, "centre charge time constant (s)"))),
    "free_spins_transition": dict(
        fn=free_spins_transition, duration=2.52, kind="one-shot", color="4A78FF", count=10, normal_blend=True,
        summary="Free-spins transition: a portal opens behind the reels, the screen is pulled in by an accelerating infall "
                "(scale = a - b e^(t/tau), exactly 0 at the swap) swirling with conserved angular momentum (omega ~ 1/(s+core)^2, "
                "exact integral), the portal collapses with a flash, a puff bursts in front and the screen springs back out "
                "(exact overshoot) unwinding to rest. Moves your screen through a carrier (screen=). Events fx_free_spins_transition, "
                "fx_free_spins_in (swap now), fx_free_spins_out. ae_hint portal_ring, smoke_hint smoke_haze.",
        anchor="Portal centre (the screen pivots there).",
        options=dict(screen=("", "bone of the whole screen / reels container (not root): carrier inserted above it at the portal "
                                 "centre; the portal goes behind its slots, the puff in front. Empty: the result's pull_bone is a "
                                 "bone to parent the screen under"),
                     size=(420.0, "portal diameter"), open=(0.45, "portal opening time (s)"), pull_at=(0.35, "seconds when the pull starts"),
                     pull=(0.9, "seconds the pull takes"), tau=(0.28, "infall e-folding time (smaller = later, harder acceleration)"),
                     core=(0.1, "radius-of-gyration floor (keeps the spin finite at scale 0)"),
                     swirl=(720.0, "degrees the screen turns while it is pulled in"), gap=(0.12, "seconds the screen is gone"),
                     overshoot=(0.14, "emerge spring overshoot"), emerge_hz=(2.0, "emerge spring frequency (Hz)"),
                     unwind=(80.0, "degrees the new screen unwinds from"), color2=("B050FF", "flash colour"),
                     smoke=("EEE6FF", "puff tint"), radius=(300.0, "how far the puff lobes travel"), puff_size=(250.0, "puff lobe size"),
                     specks=(24, "specks falling into the portal"))),
})
ROLES.update({
    "wild_land": {"streak": "the motion-blur streak, a vertical strip, head at the TOP (it is turned to trail above the wild)",
                  "flash": "the impact light", "ring": "the shock rings", "starburst": "the impact star", "spark": "one flung spark",
                  "glow": "9-slice soft glow hugging the sticky frame (give slice and px)",
                  "frame": "9-slice sticky frame line (give slice and px)", "sticky_spark": "one electric spark on the frame"},
    "expanding_wild": {"fill": "9-slice liquid fill (normal blend; give slice and px)",
                       "surface": "the surface band strip: fill side on the LEFT, front edge on the RIGHT",
                       "line": "the hot line along the surface, a vertical strip", "column": "the light column, tall (stretched)",
                       "frame": "9-slice frame line (just outside the reel)", "flash": "the flash at the far end", "mote": "one glint"},
    "scatter_trigger": {"rune": "the halo ring round each scatter, square, hollow middle", "glow": "the light behind each scatter",
                        "ring": "the shock rings", "flash": "the landing flash", "reticle": "the lock-on reticle, square",
                        "beam": "the beam body, a vertical strip, BASE at the bottom (stretched to the distance)",
                        "core": "the beam's hot core strip", "head": "the beam front", "centre_glow": "the charging light at the centre",
                        "centre_rune": "the ring spinning up at the centre", "rays": "the burst ray star"},
    "free_spins_transition": {"disc": "the portal's dark disc (normal blend by default)", "glow": "the portal rim light",
                              "swirl_a": "main spiral layer, square", "swirl_b": "inner spiral layer", "comet": "the whip streak",
                              "mote": "one infalling speck", "flash": "the collapse flash", "cloud": "one puff lobe (also the core), normal blend",
                              "puff_flash": "the puff flash", "ring": "the puff ring"},
})
for _n, _d in ROLES.items():
    if _n in RECIPES:
        RECIPES[_n]["roles"] = _d
