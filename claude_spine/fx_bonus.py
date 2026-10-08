"""Bonus-game moments for ``fx_recipe``: ``pick_reveal``, ``hold_respin``, ``jackpot_wheel``, ``meter_fill``.

Same rules as fx_recipes.py (procedural textures, one group bone per recipe, dense linear keys of closed-form functions,
``art=`` roles, hidden in the setup pose, normal-blend layers first in the run) and two new things:

* These recipes are BUILT FROM other recipes. ``_sub`` runs a registered recipe (puff, shine, ice_shatter, electric_frame,
  rune_ring, smoke_glow, explosion, projectile, light_beam) inside this one's run and animation, under this one's group
  bone, on this one's clock, so a pick reveal is a flip + a real ``puff`` + a real ``shine``. Loops are tiled exactly
  (``_repeat``, a loop that closes repeats seamlessly), windows are faded (``_envelope``), and at the end the run is
  re-sorted so every normal-blend layer comes first (one normal batch, then one additive batch).
* Like the reel moments, they MOVE the game's bones (the tile that flips, the wheel that spins, the pointer that ticks)
  through inserted carrier bones (``fx_reels._carrier``), never the artist's own keys.

Exaggerated real physics:

* ``pick_reveal``: the tile is flicked over, theta = 90 deg (t/t_flip)^2 (a flick accelerates), its projected width is
  |cos theta|, which goes through 0 with a kink at edge-on (that is what a rigid rotation does). The face that comes up
  is caught by an underdamped spring started from width 0 at the SAME speed the flip had (pi / t_flip): the damping
  ratio is solved so the width overshoots by exactly ``overshoot`` (closed-form peak time, bisection on zeta). A real
  ``puff`` hides the edge-on moment (and the game's attachment swap, event fx_pick_swap); a good pick gets a ``shine``,
  a bad one a dark smoke puff and a "no" shake, or an ``ice_shatter``.
* ``hold_respin``: the respin counter is ONE ring mesh whose rows sit on bones placed on a circle; the sweep S(t) is
  where the rows are, so the ring depletes like a clock hand with no clipping. Each tick is a step of a damped spring
  (the escapement): the sweep overshoots the new value by exactly ``recoil`` of the step (zeta = -ln(os) /
  sqrt(pi^2 + ln(os)^2)); refills are the same spring, slower, under a rune-ring flash. Locked cells glow (electric_frame +
  smoke_glow, tiled exactly per respin) and breathe with an integer number of breaths per respin, so they loop exactly.
* ``jackpot_wheel``: the wheel is kicked up to speed, then slowed by Coulomb + viscous friction, w' = -a - k w, solved in
  closed form: w(t) = (w0 + a/k) e^(-kt) - a/k, phi(t) = ((w0 + a/k)/k)(1 - e^(-kt)) - (a/k) t. a and w0 are solved so
  the wheel stops (w = 0) at exactly ``duration`` with exactly the winner under the pointer. Every peg that passes the
  pointer is a tick (event fx_wheel_tick, times solved from phi): the peg pushes the flapper to ``recoil`` and lets go,
  it springs back with an exact undershoot e^(-zeta pi / sqrt(1 - zeta^2)); at speed the pegs come faster than it can
  return, so it chatters near full deflection, and the last slow pegs give big single clacks. The segment under the
  pointer lights and its glow decays e^(-t/trail) behind it, so the light trails the pointer. The winner explodes.
* ``meter_fill``: energy drops (``projectile``) fly into the meter; each one raises the level with a critically damped
  rise and kicks the surface into sloshing standing waves: modes cos(n pi x / W), amplitude cos(n pi x0 / W) for a drop
  landing at x0, frequencies from the water-wave dispersion w_n = sqrt(g k_n tanh(k_n h)) (shallow liquid sloshes
  slower), damped e^(-gamma t), superposed over every drop. Bubbles rise at their Stokes speed (v ~ r^2, big ones
  faster), zig-zag, swell as the pressure drops and pop at the moving surface; they are born as a Poisson process whose
  rate grows with the level, plus a burst at each impact. Full = overflow burst (drag-free parabolas stretched along
  their speed, a 1/t flash, a t^0.4 ring) and a ``light_beam``.

Registered into fx_recipes.RECIPES / ROLES at import.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .fx import _rgba
from .fx_elements import tex_bubble
from .fx_recipes import (Ctx, RECIPES, ROLES, _grid, _hexn, _params, _rr_sdf, _uniq, ease_out, hexa, smooth, smooth_arr,
                         times_dense)
from .fx_reels import _carrier, _merge_keys
from .ir import MeshAttachment, Slot, color_hex, parse_color
from .timeline import r


# ------------------------------------------------------------------ textures (fx/bonus_*)
def tex_band(w: int = 256, h: int = 64) -> Image.Image:
    """A glowing band: hot core and soft halo ACROSS v (image rows), constant along u, soft at the two u ends."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    yn = (y - (h - 1) / 2) / ((h - 1) / 2)
    xn = x / (w - 1)
    a = np.exp(-(yn / 0.26) ** 2) + 0.4 * np.exp(-(yn / 0.62) ** 2)
    a *= np.clip((1 - np.abs(yn)) / 0.12, 0, 1) * np.clip(xn / 0.015, 0, 1) * np.clip((1 - xn) / 0.015, 0, 1)
    core = np.clip(np.exp(-(yn / 0.2) ** 2) * 0.6, 0, 1)
    rgb = np.dstack([np.ones_like(a), np.ones_like(a), np.ones_like(a)]) * (0.75 + 0.25 * core[..., None])
    return _rgba(rgb, np.clip(a, 0, 1))


def tex_liquid(w: int = 128, h: int = 256) -> Image.Image:
    """The liquid body, white (tint with the slot): lit from the top, darker at the bottom, rounder at the glass sides
    (cylinder shading) with one highlight stripe. Nearly opaque: it is normal blend and hides the empty meter."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = y / (h - 1)
    lum = (0.62 + 0.38 * (1 - yn) ** 1.4) * (0.62 + 0.38 * np.sqrt(np.clip(1 - xn * xn, 0, 1)))
    lum += 0.35 * np.exp(-((xn + 0.5) / 0.09) ** 2) * (0.4 + 0.6 * (1 - yn))
    a = 0.94 * np.clip((1 - np.abs(xn)) / 0.03, 0, 1)
    return _rgba(np.clip(lum, 0, 1), a)


def tex_wedge(n_seg: int, n: int = 384) -> Image.Image:
    """One wheel segment as a soft pie slice pointing UP from the image centre (the wheel centre), brighter at the rim.
    White; tint with the slot."""
    x, y = _grid(n)
    yu = -y                                                   # image rows grow down; the wedge points up
    rr = np.hypot(x, yu)
    th = np.arctan2(yu, x)
    dth = np.abs(((th - math.pi / 2 + math.pi) % (2 * math.pi)) - math.pi)
    half = math.pi / n_seg
    a = np.clip(((half - dth) * np.maximum(rr, 0.05)) / 0.03, 0, 1)
    a *= smooth_arr(rr, 0.12, 0.26) * np.clip((0.97 - rr) / 0.05, 0, 1)
    a *= 0.35 + 0.65 * rr ** 1.6
    return _rgba(np.ones((n, n)), np.clip(a, 0, 1))


def tex_pointer(color: str = "FFC83A", w: int = 128, h: int = 224) -> Image.Image:
    """The wheel's flapper: a hub at the top (the pivot, 18% down) and a blade tapering to a tip at the bottom. Opaque
    art (normal blend), gold with a dark outline and a red gem in the hub."""
    s = 3
    W_, H_ = w * s, h * s
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    base = tuple(int(v) for v in (int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)))
    dark = tuple(int(v * 0.42) for v in base)
    cx, hub_y, hub_r = W_ / 2, H_ * 0.18, W_ * 0.34
    blade = [(cx - W_ * 0.30, hub_y + hub_r * 0.2), (cx + W_ * 0.30, hub_y + hub_r * 0.2), (cx, H_ * 0.97)]
    d.polygon(blade, fill=dark)
    d.ellipse([cx - hub_r, hub_y - hub_r, cx + hub_r, hub_y + hub_r], fill=dark)
    k = 0.8
    blade_in = [(cx - W_ * 0.30 * k, hub_y + hub_r * 0.25), (cx + W_ * 0.30 * k, hub_y + hub_r * 0.25), (cx, H_ * 0.97 - 7 * s)]
    d.polygon(blade_in, fill=base)
    d.ellipse([cx - hub_r * 0.84, hub_y - hub_r * 0.84, cx + hub_r * 0.84, hub_y + hub_r * 0.84], fill=base)
    d.ellipse([cx - hub_r * 0.42, hub_y - hub_r * 0.42, cx + hub_r * 0.42, hub_y + hub_r * 0.42], fill=(200, 24, 40, 255),
              outline=(90, 0, 10, 255), width=2 * s)
    d.ellipse([cx - hub_r * 0.25, hub_y - hub_r * 0.30, cx - hub_r * 0.05, hub_y - hub_r * 0.10], fill=(255, 200, 200, 255))
    d.line([(cx - W_ * 0.06, hub_y + hub_r), (cx, H_ * 0.9)], fill=tuple(min(255, int(v * 1.25 + 40)) for v in base), width=3 * s)
    return im.resize((w, h), Image.LANCZOS)


def tex_tile(kind: str, color: str, n: int = 256) -> Image.Image:
    """A pick tile face (opaque art, normal blend). kind: back (a gem on a deep panel), good (a star on gold),
    bad (a dull X on slate). Rounded square, lit from the top, bevelled rim."""
    d = _rr_sdf(n, 0.94, 0.94, 0.24)
    x, y = _grid(n)
    base = np.array([int(color[i:i + 2], 16) for i in (0, 2, 4)], float) / 255
    lum = 0.72 + 0.38 * (-y * 0.5 + 0.5) ** 1.2
    rgb = base[None, None, :] * lum[..., None]
    rim = np.exp(-((d + 0.05) / 0.035) ** 2)
    rim_c = {"back": (1.0, 0.82, 0.32), "good": (1.0, 0.97, 0.82), "bad": (0.55, 0.57, 0.62)}[kind]
    rgb = rgb * (1 - rim[..., None]) + np.array(rim_c)[None, None, :] * rim[..., None]
    a = np.clip(-d / 0.02, 0, 1)
    face = _rgba(np.clip(rgb, 0, 1), a)
    s = 3
    em = Image.new("RGBA", (n * s, n * s), (0, 0, 0, 0))
    dr = ImageDraw.Draw(em)
    c = n * s / 2
    if kind == "back":
        for rad, col in ((0.42, (255, 205, 80, 255)), (0.30, (255, 238, 160, 255)), (0.14, (255, 255, 235, 255))):
            R_ = rad * c
            dr.polygon([(c, c - R_), (c + R_ * 0.8, c), (c, c + R_), (c - R_ * 0.8, c)], fill=col)
        for k in range(4):
            ang = k * math.pi / 2 + math.pi / 4
            px, py = c + math.cos(ang) * c * 0.62, c + math.sin(ang) * c * 0.62
            dr.ellipse([px - 0.05 * c, py - 0.05 * c, px + 0.05 * c, py + 0.05 * c], fill=(255, 215, 110, 255))
    elif kind == "good":
        pts = []
        for k in range(10):
            ang = -math.pi / 2 + k * math.pi / 5
            R_ = c * (0.6 if k % 2 == 0 else 0.25)
            pts.append((c + math.cos(ang) * R_, c + 0.04 * c + math.sin(ang) * R_))
        dr.polygon(pts, fill=(255, 255, 240, 255), outline=(200, 110, 10, 255))
        dr.line(pts + pts[:1], fill=(190, 100, 10, 255), width=3 * s, joint="curve")
    else:
        for sgn in (-1, 1):
            dr.line([(c - 0.36 * c, c - sgn * 0.36 * c), (c + 0.36 * c, c + sgn * 0.36 * c)], fill=(150, 40, 50, 255), width=int(0.16 * c))
    face.alpha_composite(em.resize((n, n), Image.LANCZOS))
    return face


# ------------------------------------------------------------------ building blocks
def _run_slot(c: Ctx, bone: str, blend: str = "additive", color: str = "FFFFFFFF") -> str:
    """A slot that continues this recipe's run (the same placement rule as Ctx.slot)."""
    sk = c.sk
    nm = sk.unique_name(bone, "slot")
    s = Slot(name=nm, bone=bone, color=color, blend=blend)
    if c.last_slot is not None:
        sk.add_slot(s, after=c.last_slot)
    elif c.behind:
        sk.add_slot(s, before=c.behind)
    elif c.front_of:
        sk.add_slot(s, after=c.front_of)
    else:
        sk.add_slot(s)
    c.last_slot = nm
    c.slots.append(nm)
    return nm


def _ribbon(c: Ctx, bone: str, tex: str, make, rows: list, blend: str = "additive", role: str | None = None,
            color: str = "FFFFFFFF") -> str:
    """A strip mesh, every vertex weighted 100% to one bone. rows = [((boneA, x, y), (boneB, x, y)), ...]: side A is
    v = 0, side B is v = 1, u runs along the rows. Move the bones and the strip follows (no deform keys)."""
    art = c._art(role)
    if art:
        tex, make, blend = art["tex"], None, art.get("blend", blend)
    tw, th = c.tex(tex, make)
    n = len(rows)
    pts, uvs = [], []
    for i, (a_, _) in enumerate(rows):
        pts.append(a_)
        uvs += [i / (n - 1), 0.0]
    for i in range(n - 1, -1, -1):
        pts.append(rows[i][1])
        uvs += [i / (n - 1), 1.0]
    n2 = 2 * n
    tris: list[int] = []
    for i in range(n - 1):
        Li, Li1, Ri, Ri1 = i, i + 1, n2 - 1 - i, n2 - 2 - i
        tris += [Li, Ri, Ri1, Li, Ri1, Li1]
    verts: list[float] = []
    for b, x, y in pts:
        verts += [1, c.sk.bone_index(b), round(x, 3), round(y, 3), 1]
    edges: list[int] = []
    for i in range(n2):
        edges += [i * 2, ((i + 1) % n2) * 2]
    nm = _run_slot(c, bone, blend, color)
    c.sk.set_attachment(nm, "fx", MeshAttachment(path=tex, uvs=[round(v, 5) for v in uvs], triangles=tris, vertices=verts,
                                                hull=n2, edges=edges, width=tw, height=th))
    return nm


def _sub(c: Ctx, recipe: str, u0: float, x: float = 0.0, y: float = 0.0, scale: float = 1.0, options: dict | None = None,
         color: str = "", count: int = 0, duration: float = 0.0, art: dict | None = None, seed: int = 0,
         parent: str | None = None, gain: float = 1.0):
    """Run a registered recipe INSIDE this one: same project, animation, clock (start u0 of ours, our time scale) and
    run of slots, under our group (or ``parent``), at ``gain`` x our intensity. art maps the member's roles to ours:
    {member_role: our_role}. Returns (member result, member Ctx)."""
    d = RECIPES[recipe]
    P = _params(recipe, color, count, duration, options)
    k = c.k * (P["duration"] / d["duration"] if d["kind"] == "one-shot" else 1.0)
    sub_art = {mr: c.art[our] for mr, our in (art or {}).items() if our in c.art}
    sc = Ctx(c.p, recipe, x, y, scale, c.T(u0), k, c.I * gain, c.seed + seed, c.anim, parent or c.group,
             c.last_slot or c.front_of, "" if c.last_slot else c.behind, f"{c.prefix}_{recipe}", art=sub_art)
    res = d["fn"](sc, P)
    c.slots += sc.slots
    c.bones += sc.bones
    if sc.last_slot:
        c.last_slot = sc.last_slot
    for role, tex in sc.art_used.items():
        c.art_used[f"{recipe}.{role}"] = tex
    for role, pic in sc.kit_used.items():
        c.kit_used[f"{recipe}.{role}"] = pic
    return res, sc


def _shift_curve(cv, dt: float):
    if not isinstance(cv, list):
        return cv
    return [r(v + dt) if i % 2 == 0 else v for i, v in enumerate(cv)]


def _repeat(c: Ctx, bones: list[str], slots: list[str], u0: float, period: float, n: int) -> None:
    """Tile the keys a member loop wrote on [u0, u0 + period] n times. A loop that closes exactly repeats seamlessly;
    the key where two copies meet is kept once (the later copy's, which carries the outgoing curve)."""
    a = c.ab.a
    t0, Pp = c.T(u0), period * c.k

    def rep(keys):
        out = list(keys)
        loop = [k for k in keys if k.time >= t0 - 1e-6]
        for j in range(1, n):
            for k in loop:
                nk = k.model_copy(deep=True)
                nk.time = r(k.time + j * Pp)
                nk.curve = _shift_curve(k.curve, j * Pp)
                if out and abs(out[-1].time - nk.time) < 1e-6:
                    out[-1] = nk
                else:
                    out.append(nk)
        return out
    for b in bones:
        for tl, keys in list(a.bones.get(b, {}).items()):
            a.bones[b][tl] = rep(keys)
    for s in slots:
        for tl, keys in list(a.slots.get(s, {}).items()):
            a.slots[s][tl] = rep(keys)


def _envelope(c: Ctx, slots: list[str], env, ranges: list[tuple[float, float]], rate: float = 30) -> None:
    """Multiply the alpha of slots (their own colour keys, or their setup colour) by env(u), sampling the ranges where
    env changes. Fades a member window in and out without touching its maths."""
    a = c.ab.a
    extra = {c.T(u) for lo, hi in ranges for u in times_dense(lo, hi, rate)}
    for s in slots:
        keys = a.slots.get(s, {}).get("rgba")
        if keys:
            kt = np.array([k.time for k in keys])
            kc = np.array([parse_color(k.color) for k in keys])
        else:
            kt = np.array([0.0])
            kc = np.array([parse_color(c.sk.slot(s).color)])
        times = sorted({round(float(t), 4) for t in kt} | extra)
        pts = []
        for t in times:
            col = [float(np.interp(t, kt, kc[:, i])) for i in range(4)]
            col[3] *= max(0.0, min(1.0, env((t - c.t0) / c.k)))
            pts.append((t, color_hex(*col)))
        c.ab.slot_color(s, _uniq(pts), "linear")


def _tint(c: Ctx, slots: list[str], rgb: str) -> None:
    """Recolour slots' colour keys to rgb, keeping their alpha (a member drew white where this recipe wants dark)."""
    for s in slots:
        keys = c.ab.a.slots.get(s, {}).get("rgba")
        for k in keys or []:
            k.color = rgb.upper()[:6] + k.color[6:8]


def _hide_after(c: Ctx, slots: list[str], u: float) -> None:
    """Switch slots off at u (drop any later attachment keys)."""
    t = c.T(u)
    for s in slots:
        keys = c.ab.a.slots.get(s, {}).get("attachment")
        pts = [(k.time, k.name) for k in keys if k.time < t - 1e-6] if keys else [(0.0, "fx")]
        c.ab.slot_attachment(s, pts + [(t, None)])


def _normal_first(c: Ctx) -> None:
    """Re-sort this recipe's run so every normal-blend slot comes first (stable within each blend): the run then costs
    one normal batch and one additive batch, whatever its members did."""
    sk = c.sk
    if not c.slots:
        return
    idx = sorted(sk.slot_index(s) for s in c.slots)
    objs = [sk.slots[i] for i in idx]
    new = sorted(objs, key=lambda s: s.blend != "normal")
    for i, s in zip(idx, new):
        sk.slots[i] = s
    c.slots = [s.name for s in new]
    c.last_slot = c.slots[-1]


def _dedupe_events(c: Ctx) -> None:
    """Members fire their own event and their result's: drop exact repeats (same name, time, payload)."""
    seen, out = set(), []
    for e in c.ab.a.events:
        key = (e.name, round(e.time, 4), tuple(sorted((k, str(v)) for k, v in (e.model_extra or {}).items())))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    c.ab.a.events[:] = out


def _merge_rot(c: Ctx, bone: str, ts, fn) -> None:
    """Rotate keys on a carrier, ADDED to any rotation an earlier call left on it in this animation."""
    new = [(c.T(u), float(fn(u))) for u in ts]
    old = c.ab.a.bones.get(bone, {}).get("rotate")
    if old:
        val = lambda k: 0.0 if getattr(k, "value", None) is None else float(k.value)  # noqa: E731
        ot, ov = np.array([k.time for k in old]), np.array([val(k) for k in old])
        nt, nv = np.array([p[0] for p in new]), np.array([p[1] for p in new])
        times = sorted(set(np.round(np.concatenate([ot, nt]), 4).tolist()))
        new = [(t, float(np.interp(t, ot, ov)) + (float(np.interp(t, nt, nv)) if nt[0] - 1e-9 <= t <= nt[-1] + 1e-9 else 0.0))
               for t in times]
    c.ab.bone(bone, "rotate", _uniq(new), "linear")


def _step(os: float, hz: float):
    """Unit step response of a damped spring, from 1 to 0 at rest: h = e^(-s t)(cos wd t + s/wd sin wd t). The damping
    ratio is solved from the wanted overshoot os (the first swing past 0 is exactly -os). Returns (h, time of that swing)."""
    os = min(max(os, 1e-4), 0.9)
    lo = math.log(os)
    z = -lo / math.sqrt(math.pi ** 2 + lo * lo)
    w = 2 * math.pi * hz
    sg, wd = z * w, w * math.sqrt(1 - z * z)
    return (lambda t: math.exp(-sg * t) * (math.cos(wd * t) + sg / wd * math.sin(wd * t)) if t > 0 else 1.0), math.pi / wd


def _need(cond: bool, msg: str) -> None:
    if not cond:
        raise ValueError(msg)


# ------------------------------------------------------------------ pick_reveal
def _face_spring(t_flip: float, A: float, hz: float):
    """The face that comes up after edge-on: width s(0) = 0 rising at the flip's own speed v0 = pi / t_flip, caught by a
    spring at rest width 1: s = 1 + e^(-s t)(-cos wd t + C2 sin wd t), C2 = (v0 - s)/wd. Its first peak (closed form:
    tan(wd t) = -v0 wd / (w^2 - s v0)) is 1 + A EXACTLY, by bisection on the damping ratio. Returns (s(t), zeta, t_peak)."""
    v0 = math.pi / t_flip
    w = 2 * math.pi * hz

    def peak(z):
        sg, wd = z * w, w * math.sqrt(1 - z * z)
        c2 = (v0 - sg) / wd
        ph = math.atan2(v0, -(w * w - sg * v0) / wd)
        return 1 + math.exp(-sg * ph / wd) * (-math.cos(ph) + c2 * math.sin(ph)), ph / wd
    lo, hi = 0.02, 0.98
    _need(peak(hi)[0] <= 1 + A, f"overshoot {A:g} is too small for a {t_flip:g} s flip at {hz:g} Hz (the face would fly past "
                                "it however damped); lower bounce or slow the flip")
    _need(peak(lo)[0] >= 1 + A, f"overshoot {A:g} is too big for a {t_flip:g} s flip at {hz:g} Hz; raise bounce or speed the flip")
    for _ in range(70):
        mid = (lo + hi) / 2
        if peak(mid)[0] > 1 + A:
            lo = mid
        else:
            hi = mid
    z = (lo + hi) / 2
    sg, wd = z * w, w * math.sqrt(1 - z * z)
    c2 = (v0 - sg) / wd
    return (lambda t: 1 + math.exp(-sg * t) * (-math.cos(wd * t) + c2 * math.sin(wd * t))), z, peak(z)[1]


def pick_reveal(c: Ctx, P: dict) -> dict:
    """A pick-me tile flips over: flicked, edge-on behind a puff, the face springs up past full width and settles;
    shine for a good pick, a dark smoke puff and a "no" shake (or an ice block that shatters) for a bad one."""
    W, H = float(P["width"]), float(P["height"])
    _need(W > 0 and H > 0, "width and height must be > 0")
    tf, A, hz = float(P["flip"]), float(P["overshoot"]), float(P["bounce"])
    _need(0.05 <= tf <= 1.5, "flip (seconds to edge-on) must be between 0.05 and 1.5")
    _need(A > 0, "overshoot must be > 0 (the face pops past full width)")
    good = bool(P["good"])
    bad = str(P["bad"])
    _need(bad in ("smoke", "ice"), f"bad must be smoke | ice, got {bad!r}")
    swap_slot, swap_to = str(P["swap_slot"] or ""), str(P["swap_to"] or "")
    _need(bool(swap_slot) == bool(swap_to), "swap_slot and swap_to go together (the game slot and the attachment to show)")
    if swap_slot:
        _need(c.sk.has_slot(swap_slot), f"no slot {swap_slot!r} to swap")
        atts = c.sk.skin("default").attachments.get(swap_slot, {})
        _need(swap_to in atts, f"slot {swap_slot!r} has no attachment {swap_to!r} in the default skin")
    col = _hexn(P["color"], "FFC23A")
    back_c = _hexn(P["color2"], "5A3CC8")
    s_face, zeta, tp = _face_spring(tf, A, hz)
    settle = (0.5, 0.8)

    def sx(u):
        if u <= tf:
            return math.cos(math.pi / 2 * (max(0.0, u) / tf) ** 2)
        tau = u - tf
        return 1 + (s_face(tau) - 1) * (1 - smooth(tau, *settle))

    def scl(u):
        x = sx(u)
        return (x, 1 + 0.10 * (1 - x) if x < 1 else 1 + 0.5 * (x - 1))      # the near edge grows as it turns; a pop
    ts = sorted(set(times_dense(0, tf, 120)) | set(times_dense(tf, tf + settle[1], 90)) | {tf, tf + tp})
    t_shake = tf + 0.12
    shake = (not good) and bad == "smoke"
    Ash = W * 0.07
    shk = lambda u: (Ash * math.exp(-(u - t_shake) / 0.16) * math.sin(2 * math.pi * 6.0 * (u - t_shake))  # noqa: E731
                     * (1 - smooth(u - t_shake, 0.42, 0.6)) if u > t_shake else 0.0)
    tsh = times_dense(t_shake, t_shake + 0.6, 90)

    grp = c.bone("pick", c.group, 0, 0)
    face_slots: dict[str, str] = {}
    if P["tile"]:
        car = _carrier(c, str(P["tile"]), "pick")
        _merge_keys(c, car, "scale", ts, scl, "mul")
        if shake:
            _merge_keys(c, car, "translate", tsh, lambda u: (shk(u) * c.S, 0.0), "add")
        flip_bone = car
    else:
        face = c.bone("face", grp)
        flip_bone = face
        kf = "good" if good else "bad"
        fc = col if good else "6E7480"
        face_slots["back"] = c.slot(face, f"fx/bonus_tile_back_{back_c}", W, height=H, make=lambda: tex_tile("back", back_c),
                                    blend="normal", role="back")
        face_slots["front"] = c.slot(face, f"fx/bonus_tile_{kf}_{fc}", W, height=H, make=lambda: tex_tile(kf, fc),
                                     blend="normal", role="front")
        c.bone_keys(face, "scale", ts, scl)
        if shake:
            c.bone_keys(face, "translate", tsh, lambda u: (shk(u), 0.0))
    if swap_slot:
        old = c.ab.a.slots.get(swap_slot, {}).get("attachment")
        pts = [(k.time, k.name) for k in old] if old else []
        c.ab.slot_attachment(swap_slot, _uniq(sorted(pts + [(c.T(tf), swap_to)], key=lambda p: p[0])))

    # the puff that hides the edge-on moment (and the game's swap)
    u_p = max(0.0, tf - 0.14)
    pc, pf = ("FFF1DC", "FFD27A") if (good or bad == "ice") else ("5E5866", "7D7090")
    puff_res, pc_ = _sub(c, "puff", u_p, options=dict(size=W * 0.42, radius=W * 0.36, rise=16.0 if good else 30.0, color2=pf),
                       color=pc, count=int(P["count"]), art={"cloud": "cloud"}, seed=1)
    if not good and bad == "smoke":                                  # dark smoke all through (puff draws half its lobes white)
        _tint(c, [s for s in pc_.slots if c.sk.slot(s).blend == "normal"], pc)
    ends = [tf + settle[1], u_p + 1.15]
    hint = puff_res.get("ae_hint")
    shine_at = ice_at = None
    if good:
        shine_at = tf + 0.5 * tp
        _sub(c, "shine", shine_at, options=dict(size=W * 0.5 * float(P["shine_size"])), color=_hexn(P["color3"], "FFF2B0"),
             count=6, art={"rays": "rays"}, seed=2, gain=0.75)
        ends.append(shine_at + 1.4)
    elif bad == "ice":
        ice_at = tf + 0.12
        _sub(c, "ice_shatter", ice_at, options=dict(size=max(W, H) * 1.12, crack=0.32, shatter=0.58), count=12,
             art={"block": "block"}, seed=3)
        ends.append(ice_at + 1.6)
    else:
        ends.append(t_shake + 0.6)
    D = max(ends)
    if face_slots:
        c.ab.slot_attachment(face_slots["back"], [(0.0, "fx"), (c.T(tf), None)])     # waiting to be picked from the clip's start
        c.show([face_slots["front"]], tf, (ice_at + 0.58) if ice_at is not None else (None if P["keep"] else D))
    c.ab.event(c.T(tf), "fx_pick_swap")
    c.ab.event(c.T(tf + 0.02), "fx_pick_good" if good else "fx_pick_bad")
    _normal_first(c)
    _dedupe_events(c)
    out = dict(duration=D * c.k, swap_at=c.T(tf), peak_at=c.T(tf + tp), zeta=round(zeta, 4), flip_bone=flip_bone,
               good=good, shine_at=None if shine_at is None else c.T(shine_at),
               shatter_at=None if ice_at is None else c.T(ice_at + 0.58))
    if hint:
        out["ae_hint"] = hint
    return c.result(**out)


# ------------------------------------------------------------------ hold_respin
def _respin_schedule(N: int, resets: set[int], lead: float, period: float):
    """[(time, kind, count after)] for the counter: a fill at lead, a tick at the start of every respin, a refill after
    any tick listed in resets (a new symbol landed during that respin). Stops when a tick reaches 0 and is not reset."""
    ev = [(lead, "fill", N)]
    t, count, k = lead + 0.5, N, 0
    while True:
        k += 1
        count -= 1
        ev.append((t, "tick", count))
        if k in resets:
            count = N
            ev.append((t + 0.6 * period, "fill", N))
        elif count <= 0:
            break
        t += period
        _need(k < 200, "respin schedule does not end (too many resets)")
    return ev, k


def hold_respin(c: Ctx, P: dict) -> dict:
    """Hold & respin: the locked cells glow and breathe (electric frame + smoke haze), and a counter ring above them
    depletes one segment per respin like a clock hand, ticking on a spring; a new lock refills it under a rune flash."""
    N = int(P["respins"])
    _need(1 <= N <= 12, "respins must be 1..12")
    period = float(P["period"])
    _need(period >= 0.6, "period (seconds per respin) must be >= 0.6")
    breaths = int(P["breaths"])
    _need(breaths >= 1, "breaths (per respin) must be an integer >= 1 so the glow loops exactly")
    resets = {int(v) for v in (P["resets"] or [])}
    _need(all(v >= 1 for v in resets), "resets are tick numbers, 1-based")
    cells = P["cells"] or [[0.0, 0.0, float(P["width"]), float(P["height"])]]
    for cl in cells:
        _need(len(cl) == 4 and float(cl[2]) > 0 and float(cl[3]) > 0, f"each cell is [dx, dy, w, h] with w, h > 0, got {cl}")
    col = _hexn(P["color"], "FFD24A")
    cell_c = _hexn(P["color2"], "FF8A1E")
    smoke_c = _hexn(P["color3"], "FFB070")
    lead = 0.55
    ev, nticks = _respin_schedule(N, resets, lead, period)
    t_last = ev[-1][0]
    D = period * math.ceil((t_last + 0.8 * period + 0.35) / period)
    t_end = t_last + 0.8 * period
    rng = np.random.default_rng(c.seed + 301)
    grp = c.bone("hold", c.group, 0, 0)
    fade = lambda u: smooth(u, 0, 0.3) * (1 - smooth(u, D - 0.4, D))  # noqa: E731
    br = lambda u: 0.5 - 0.5 * math.cos(2 * math.pi * breaths * u / period)  # noqa: E731   0 at every tick: exact loop

    # ---- locked cells: member loops of one respin, tiled over the window, faded in and out
    n_rep = int(round(D / period))
    cell_groups, cell_slots = [], []
    hints = []
    for i, cl in enumerate(cells):
        dx, dy, w, h = (float(v) for v in cl)
        cb = c.bone(f"cell{i}", grp, dx, dy)
        first = len(c.slots)
        b_lock = c.bone(f"lock{i}", cb)
        s_lock = c.slot(b_lock, "fx/glow", max(w, h) * 1.25, role="lock")
        _, sm = _sub(c, "smoke_glow", 0.0, parent=cb, options=dict(width=w * 0.78, height=h * 0.8, blend="additive", alpha=0.28,
                                                                     color2="7A4010"),
                     color=smoke_c, count=5, duration=period, art={"smoke": "smoke"}, seed=10 + i, gain=0.6)
        _repeat(c, sm.bones, sm.slots, 0.0, period, n_rep)
        res, ef = _sub(c, "electric_frame", 0.0, parent=cb, options=dict(width=w, height=h, sparks=int(P["count"])),
                       color=cell_c, duration=period, art={"spark": "spark"}, seed=20 + i, gain=0.55)
        _repeat(c, ef.bones, ef.slots, 0.0, period, n_rep)
        hints.append(res.get("ae_hint"))
        cell_groups.append(ef.group)
        c.show([s_lock], 0, D)
        tsl = times_dense(0, D, 16)
        c.color_keys(s_lock, tsl, lambda u: hexa(cell_c, c.a(0.08 + 0.16 * br(u))))
        c.bone_keys(b_lock, "scale", tsl, lambda u: (0.92 + 0.1 * br(u),) * 2)
        pop, _ = _step(0.12, 3.0)
        tsc = sorted(set(times_dense(0, D, 16)) | set(times_dense(0, 0.6, 60)))
        c.bone_keys(ef.group, "scale", tsc, lambda u: ((1 + 0.03 * br(u)) * (1 + 0.22 * pop(u) * (1 - smooth(u, 0.35, 0.6))),) * 2)
        cell_slots += c.slots[first:]
    _envelope(c, cell_slots, fade, [(0, 0.3), (D - 0.4, D)])

    # ---- the counter ring: a dim track, segment pips, one band mesh on a circle of bones, a glowing hand
    R = float(P["ring_size"]) / 2
    thick = max(6.0, R * 0.3)
    b_ring = c.bone("ring", grp, float(P["ring_x"]), float(P["ring_y"]))
    s_track = c.slot(b_ring, "fx/ring", 2 * R / 0.78, role="track")
    pips = []
    for j in range(N):
        ang = math.radians(90 - j * 360 / N)
        bp = c.bone(f"pip{j}", b_ring, R * math.cos(ang), R * math.sin(ang))
        pips.append(c.slot(bp, "fx/mote", thick * 1.5, role="pip"))
    rows = 33
    set_ang = [90 - 360 * i / (rows - 1) for i in range(rows)]
    row_b = [c.bone(f"r{i}", b_ring, R * math.cos(math.radians(a_)), R * math.sin(math.radians(a_)), rot=a_)
             for i, a_ in enumerate(set_ang)]
    s_band = _ribbon(c, b_ring, "fx/bonus_band", tex_band, [((b, thick / 2, 0.0), (b, -thick / 2, 0.0)) for b in row_b],
                     role="ring")
    b_head = c.bone("head", b_ring, 0, R)
    s_head = c.slot(b_head, "fx/glow", thick * 4.2, role="head")
    tick_h, tick_tp = _step(float(P["recoil"]), 9.0)
    fill_h, fill_tp = _step(0.08, 3.2)
    steps, prev = [], 0
    for t_e, kind, cnt in ev:
        steps.append((t_e, (cnt - prev) / N, tick_h if kind == "tick" else fill_h, kind))
        prev = cnt
    taper = (0.3, 0.55)

    def S(u):
        v = 0.0
        for t_e, dS, h, kind in steps:
            if u >= t_e:
                tau = u - t_e
                v += dS * (1 - h(tau) * (1 - smooth(tau, *(taper if kind == "tick" else (0.3, 0.45)))))
        return min(1.0, max(0.0, v))
    tsr = set(times_dense(0, D, 5))
    for t_e, _, _, kind in steps:
        tsr.update(times_dense(t_e, min(D, t_e + 0.8), 60))
        tsr.add(round(t_e + (tick_tp if kind == "tick" else fill_tp), 4))
    tsr = sorted(t for t in tsr if 0 <= t <= D)
    hand = lambda u: 90 - 360 * (1 - S(u))  # noqa: E731
    for i, b in enumerate(row_b):
        def ang(u, i=i):
            s_ = S(u)
            return 90 - 360 * (1 - s_) - 360 * s_ * i / (rows - 1)
        a0 = set_ang[i]
        c.bone_keys(b, "translate", tsr, lambda u, ang=ang, a0=a0: (R * (math.cos(math.radians(ang(u))) - math.cos(math.radians(a0))),
                                                                    R * (math.sin(math.radians(ang(u))) - math.sin(math.radians(a0)))))
        c.bone_keys(b, "rotate", tsr, lambda u, ang=ang, a0=a0: ang(u) - a0)
    c.bone_keys(b_head, "translate", tsr, lambda u: (R * math.cos(math.radians(hand(u))), R * (math.sin(math.radians(hand(u))) - 1)))
    ticks = [(t_e, cnt) for t_e, kind, cnt in ev if kind == "tick"]
    fills = [t_e for t_e, kind, _ in ev if kind == "fill"]
    fl = lambda u: sum(smooth(u, t_, t_ + 0.02) / (1 + 25 * max(0.0, u - t_ - 0.02)) for t_, _ in ticks)  # noqa: E731
    alive = lambda u: smooth(S(u), 0.0, 0.02)  # noqa: E731
    c.show([s_track, s_band, s_head] + pips, 0, D)
    tsh = sorted(set(tsr) | {round(t_ + d_, 4) for t_, _ in ticks for d_ in (0.0, 0.02, 0.06, 0.15)})
    c.color_keys(s_band, tsh, lambda u: hexa(col, c.a(fade(u) * (0.9 + 0.1 * br(u)) * alive(u))))
    c.color_keys(s_head, tsh, lambda u: hexa("FFF6D8", c.a(fade(u) * alive(u) * (0.55 + 0.45 * min(1.0, fl(u))))))
    c.bone_keys(b_head, "scale", tsh, lambda u: (0.8 + 0.6 * min(1.0, fl(u)),) * 2)
    c.color_keys(s_track, times_dense(0, D, 10), lambda u: hexa(col, c.a(fade(u) * (0.16 + 0.06 * br(u)))))
    for j, sp in enumerate(pips):
        lit = lambda u, j=j: smooth(S(u) * N - j, 0.2, 0.8)  # noqa: E731   pip j is lit while segment j is left
        c.color_keys(sp, tsr, lambda u, lit=lit: hexa("FFF6D8", c.a(fade(u) * (0.15 + 0.75 * lit(u)))))
    # a spark where each consumed segment was
    for i, (t_, cnt) in enumerate(ticks):
        a_ = math.radians(90 - 360 * (1 - (cnt + 1) / N))
        bs = c.bone(f"tk{i}", b_ring, R * math.cos(a_), R * math.sin(a_))
        ss = c.slot(bs, "fx/spark", thick * 4.0, color=hexa("FFFFFF", 1.0), role="spark")
        life = 0.32
        c.ab.slot_attachment(ss, [(0.0, None), (c.T(t_), "fx"), (c.T(t_ + life), None)])
        c.ab.bone(bs, "scale", _uniq([(c.T(t_), 0, 0), (c.T(t_ + life * 0.3), 1, 1), (c.T(t_ + life), 0, 0)]), "quad_in_out")
        c.ab.bone(bs, "rotate", _uniq([(c.T(t_), 0), (c.T(t_ + life), float(rng.uniform(60, 120)))]), "linear")
        c.ab.event(c.T(t_), "fx_respin_tick", int=int(cnt))
    # refill flash: a rune ring timed so its flash peaks on the refill, and a 1/t glow
    rune_k = 1.0 / 2.7
    rs = 2 * R * 1.3 / 400
    b_fl = c.bone("flash", b_ring)
    s_fl = c.slot(b_fl, "fx/glow", R * 3.6, role="flash")
    c.show([s_fl], 0, D)
    tff = sorted(set(times_dense(0, D, 8)) | {round(t_ + d_, 4) for t_ in fills for d_ in (0, 0.02, 0.05, 0.1, 0.2, 0.4)})
    ffl = lambda u: sum(smooth(u, t_, t_ + 0.02) / (1 + 14 * max(0.0, u - t_ - 0.02)) for t_ in fills)  # noqa: E731
    c.color_keys(s_fl, tff, lambda u: hexa(col, c.a(0.85 * min(1.0, ffl(u)))))
    for k_, t_ in enumerate(fills):
        u_r = max(0.0, t_ - 1.45 * rune_k)
        _sub(c, "rune_ring", u_r, x=float(P["ring_x"]) - 8 * rs, y=float(P["ring_y"]) - 24 * rs, scale=rs, parent=grp,
             options=dict(squash=1.0, spin=60.0, flash=0.8), color=col, duration=1.0, art={"ring": "runes"}, seed=40 + k_)
        if k_:
            c.ab.event(c.T(t_), "fx_respin_reset")
    c.ab.event(c.T(t_end), "fx_respin_end")
    _normal_first(c)
    _dedupe_events(c)
    out = dict(duration=D, loop=period, ticks=[c.T(t_) for t_, _ in ticks], counts=[cnt for _, cnt in ticks],
               fills=[c.T(t_) for t_ in fills], end_at=c.T(t_end), cells=len(cells), ring_bone=b_ring, cell_bones=cell_groups)
    h0 = next((h for h in hints if h), None)
    if h0:
        out["ae_hint"] = h0
    return c.result(**out)


# ------------------------------------------------------------------ jackpot_wheel
def _wheel_motion(Phi: float, dur: float, kick: float, k: float):
    """Kick (w ramps 0 -> w0 over kick s), then Coulomb + viscous friction w' = -a - k w until w = 0 at exactly dur,
    having turned exactly Phi degrees in all. Closed form; returns (phi(t), omega(t), w0, a)."""
    T = dur - kick
    if k > 1e-6:
        E = math.exp(k * T) - 1 - k * T
        G = k * (math.exp(k * T) - 1) / E                # w0 = Phi_friction * G
    else:
        E, G = 0.0, 2.0 / T
    Pf = Phi / (1 + G * kick / 2)
    w0 = Pf * G
    a = Pf * k * k / E if k > 1e-6 else w0 / T
    pk = w0 * kick / 2

    def phi(t):
        if t <= 0:
            return 0.0
        if t < kick:
            return w0 * t * t / (2 * kick)
        tau = min(t, dur) - kick
        if k > 1e-6:
            return pk + (w0 + a / k) / k * (1 - math.exp(-k * tau)) - a / k * tau
        return pk + w0 * tau - a * tau * tau / 2

    def omega(t):
        if t <= 0 or t >= dur:
            return 0.0
        if t < kick:
            return w0 * t / kick
        tau = t - kick
        return (w0 + a / k) * math.exp(-k * tau) - a / k if k > 1e-6 else w0 - a * tau
    return phi, omega, w0, a


def _invert(phi, target: float, t1: float) -> float:
    lo, hi = 0.0, t1
    for _ in range(60):
        mid = (lo + hi) / 2
        if phi(mid) < target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def jackpot_wheel(c: Ctx, P: dict) -> dict:
    """A prize wheel: kicked, slowed by real friction to stop exactly on the winner, the pointer clacking on every peg,
    the segment under the pointer lighting up with a glow that trails behind it, and the winner exploding."""
    N = int(P["segments"])
    _need(2 <= N <= 64, "segments must be 2..64")
    win = int(P["winner"])
    _need(0 <= win < N, f"winner must be a segment index 0..{N - 1}")
    spins = int(P["spins"])
    _need(spins >= 0, "spins must be >= 0")
    dur, kick, k = float(P["duration"]), float(P["kick"]), float(P["viscous"])
    _need(0.0 <= kick < dur - 0.5, "kick (spin-up seconds) must be >= 0 and leave at least 0.5 s of slowing down")
    _need(k >= 0, "viscous (drag rate, 1/s) must be >= 0")
    Rw = float(P["radius"])
    _need(Rw > 0, "radius must be > 0")
    col = _hexn(P["color"], "FFD24A")
    win_c = _hexn(P["color2"], "FF5A2A")
    seg = 360.0 / N
    Phi = spins * 360.0 + ((-win * seg) % 360.0)
    _need(Phi > 0, "the wheel must turn: spins >= 1 or a winner other than 0")
    phi, omega, w0, a_c = _wheel_motion(Phi, dur, kick, k)
    # pegs passing the pointer: phi = (m + 1/2) seg
    cross = []
    m = 0
    while (m + 0.5) * seg <= Phi - 1e-6:
        cross.append(_invert(phi, (m + 0.5) * seg, dur))
        m += 1
    under = [0] + [(-(i + 1)) % N for i in range(len(cross))]       # segment under the pointer after each crossing
    _need(under[-1] == win, "internal: the wheel did not stop on the winner")
    boom = bool(P["boom"])
    D = dur + (1.9 if boom else 1.1)
    grp = c.bone("wheel", c.group, 0, 0)
    rho = lambda u: -phi(u)  # noqa: E731   clockwise
    tw = sorted(set(times_dense(0, dur, 60)) | {dur})
    wheel_bone = ""
    if P["wheel"]:
        wheel_bone = _carrier(c, str(P["wheel"]), "spin")
        _merge_rot(c, wheel_bone, tw, rho)
    b_spin = c.bone("spin", grp)
    c.bone_keys(b_spin, "rotate", tw, rho)

    # pointer: pushed to `recoil` by each peg, released, springs back with an exact undershoot
    Rp = float(P["recoil"])
    ret, t_under = _step(math.exp(-float(P["pointer_damping"]) * math.pi / math.sqrt(1 - float(P["pointer_damping"]) ** 2)),
                         float(P["pointer_hz"]))
    pushes = []
    for i, t_i in enumerate(cross):
        gap = (cross[i + 1] - t_i) if i + 1 < len(cross) else 1.0
        dp = min(0.45 * gap, 0.18 * seg / max(omega(t_i), 1e-3), 0.12)
        pushes.append((t_i, dp))

    def theta(u):
        v = 0.0
        for i, (t_i, dp) in enumerate(pushes):
            if u < t_i:
                break
            nxt = pushes[i + 1][0] if i + 1 < len(pushes) else 1e9
            if u >= nxt:
                continue
            start = theta_at_end[i - 1](t_i) if i else 0.0
            if u < t_i + dp:
                q = (u - t_i) / dp
                v = start + (Rp - start) * q
            else:
                v = Rp * ret(u - t_i - dp)
        return v * (1 - smooth(u, dur + 0.5, dur + 0.9))
    theta_at_end = [(lambda u, i=i: Rp * ret(u - pushes[i][0] - pushes[i][1])) for i in range(len(pushes))]
    tp_ = set(times_dense(0, dur + 1.0, 90))
    for t_i, dp in pushes:
        tp_.update([round(t_i, 4), round(t_i + dp, 4), round(t_i + dp + t_under, 4)])
    tp_ = sorted(t for t in tp_ if 0 <= t <= D)
    plen = Rw * 0.36
    if P["pointer"]:
        ptr = _carrier(c, str(P["pointer"]), "tick")
        _merge_rot(c, ptr, tp_, theta)
        s_ptr = None
    else:
        ptr = c.bone("pointer", grp, 0, Rw + plen * 0.16)
        pc = _hexn(P["color3"], "FFC83A")
        s_ptr = c.slot(ptr, f"fx/bonus_pointer_{pc}", plen * 0.57, oy=-plen * (0.5 - 0.18), height=plen,
                       make=lambda: tex_pointer(pc), blend="normal", role="pointer")
        c.bone_keys(ptr, "rotate", tp_, theta)

    # segment glows on the wheel: lit while under the pointer, decaying e^(-t/trail) after it leaves
    trail = float(P["trail"])
    _need(trail > 0, "trail must be > 0 (seconds)")
    passes: dict[int, list[tuple[float, float]]] = {j: [] for j in range(N)}
    bounds = [0.0] + cross + [1e9]
    for i, j in enumerate(under):
        passes[j].append((bounds[i], bounds[i + 1]))
    wedges = []
    for j in range(N):
        bw = c.bone(f"seg{j}", b_spin, rot=-j * seg)
        sw = c.slot(bw, f"fx/bonus_wedge_{N}", 2 * Rw * 0.98, color=hexa(col, 0.0), make=lambda: tex_wedge(N), role="wedge")
        wedges.append(sw)
    for s_ in wedges:
        c.ab.slot_attachment(s_, [(0.0, "fx"), (c.T(D), None)])
    if s_ptr:
        c.ab.slot_attachment(s_ptr, [(0.0, "fx")])                    # the pointer is part of the wheel: always on
    strobe = lambda u: (0.62 + 0.38 * math.cos(2 * math.pi * 3.0 * (u - dur))) * (1 - smooth(u, D - 0.5, D))  # noqa: E731
    for j, sw in enumerate(wedges):
        ps = passes[j]

        def g(u, ps=ps, j=j):
            v = 0.0
            for t_in, t_out in ps:
                if u < t_in:
                    break
                v = 1.0 if u <= t_out else math.exp(-(u - t_out) / trail)
            if j == win and u >= dur:
                v = strobe(u)
            return v
        tsw = set(times_dense(0, D, 30))
        for t_in, t_out in ps:
            for t_ in (t_in - 0.001, t_in, min(t_out, D), t_out + 0.3 * trail, t_out + trail, t_out + 2 * trail, t_out + 4 * trail):
                if 0 <= t_ <= D:
                    tsw.add(round(t_, 4))
        if j == win:
            tsw.update(times_dense(dur, D, 30))
        tsw = sorted(tsw)
        cj = win_c if j == win else col
        c.color_keys(sw, tsw, lambda u, g=g, cj=cj: hexa(cj if u >= dur else col, c.a(0.62 * g(u))))
    for t_i, j in zip(cross, under[1:]):
        c.ab.event(c.T(t_i), "fx_wheel_tick", int=int(j))
    c.ab.event(c.T(dur), "fx_wheel_stop", int=win)
    hint = None
    if boom:
        bs = float(P["boom_size"])
        res, _ = _sub(c, "explosion", dur, x=0, y=Rw * 0.62, options=dict(size=Rw * 0.62 * bs, embers=8),
                      color=win_c, count=int(P["count"]), art={"fire": "fire", "smoke": "smoke", "flash": "flash"}, seed=5)
        _sub(c, "shine", dur + 0.02, x=0, y=Rw * 0.62, options=dict(size=Rw * 0.42 * bs), color="FFE6A0", count=6,
             art={"rays": "rays"}, seed=6, gain=0.85)
        hint = res.get("ae_hint")
    _normal_first(c)
    _dedupe_events(c)
    out = dict(duration=D, stop_at=c.T(dur), turned=Phi, omega0=round(w0, 3), coulomb=round(a_c, 3), viscous=k,
               ticks=[c.T(t_) for t_ in cross], segments_passed=under[1:], winner=win, wheel_bone=wheel_bone or b_spin,
               pointer_bone=ptr)
    if hint:
        out["ae_hint"] = hint
    return c.result(**out)


# ------------------------------------------------------------------ meter_fill
def meter_fill(c: Ctx, P: dict) -> dict:
    """An energy meter fills: drops fly in on arcs, the level rises with a sloshing surface and rising bubbles, and at
    full it overflows in a burst under a beam of light."""
    W, H = float(P["width"]), float(P["height"])
    _need(W > 0 and H > 0, "width and height must be > 0")
    levels = [float(v) for v in (P["levels"] or [])]
    _need(bool(levels) and all(0 < v <= 1 for v in levels), "levels are fill fractions in (0, 1], one per drop")
    _need(all(b >= a_ for a_, b in zip(levels, levels[1:])), "levels must not go down (a meter only fills)")
    srcs = P["sources"] or [[-260.0, 140.0]]
    for s_ in srcs:
        _need(len(s_) == 2, f"each source is [x, y], got {s_}")
    interval, flight = float(P["interval"]), float(P["flight"])
    _need(interval > 0 and flight > 0.05, "interval must be > 0 and flight > 0.05 s")
    liq_c = _hexn(P["color"], "2FD8FF")
    drop_c = _hexn(P["color2"], "B8FBFF")
    rng = np.random.default_rng(c.seed + 401)
    lead = 0.1
    nd = len(levels)
    launch = [lead + i * interval for i in range(nd)]
    hit = [t_ + flight for t_ in launch]
    dL = [levels[0]] + [b - a_ for a_, b in zip(levels, levels[1:])]
    tau_r, X = 0.09, 6.0
    norm = 1 - math.exp(-X) * (1 + X)

    def rise(tau):
        if tau <= 0:
            return 0.0
        x = tau / tau_r
        return 1.0 if x >= X else (1 - math.exp(-x) * (1 + x)) / norm      # critically damped, exact at x = X
    L = lambda u: sum(d_ * rise(u - h_) for d_, h_ in zip(dL, hit))  # noqa: E731
    full = levels[-1] >= 1 - 1e-9
    t_full = hit[-1] + X * tau_r if full else None
    D = (t_full + 1.7) if full else (hit[-1] + X * tau_r + 0.9)
    gfade = lambda u: 1 - smooth(u, D - 0.5, D - 0.1)  # noqa: E731
    # sloshing: standing waves cos(n pi x/W), dispersion w_n = sqrt(g k tanh(k h)), g from the wanted fundamental
    k1 = math.pi / W
    w1 = 2 * math.pi * float(P["slosh_hz"])
    g = w1 * w1 / (k1 * math.tanh(k1 * H * 0.5))
    gam = float(P["slosh_damping"])
    A0 = float(P["wobble"])
    x0s = [float(rng.uniform(-0.3, 0.3)) * W for _ in range(nd)]
    modes = []
    for i in range(nd):
        h_i = max(H * levels[i], 4.0)
        for n in range(1, 5):
            kn = n * k1
            wn = math.sqrt(g * kn * math.tanh(kn * h_i))
            amp = -A0 * math.cos(n * math.pi * (x0s[i] + W / 2) / W) * n ** -0.7
            modes.append((hit[i], n, wn, amp))

    def eta(x, u):
        v = 0.0
        for t_i, n, wn, amp in modes:
            tau = u - t_i
            if tau > 0:
                v += amp * math.cos(n * math.pi * (x + W / 2) / W) * math.exp(-gam * tau) * math.sin(wn * tau)
        return v * gfade(u)
    surf = lambda x, u: max(0.0, H * L(u) + eta(x, u))  # noqa: E731   height of the surface above the meter floor

    grp = c.bone("meter", c.group, 0, 0)
    base = c.bone("floor", grp, 0, -H / 2)
    M = 11
    xs = [-W / 2 + j * W / (M - 1) for j in range(M)]
    tops = [c.bone(f"top{j}", base, x_, 0) for j, x_ in enumerate(xs)]
    s_body = _ribbon(c, base, "fx/bonus_liquid", tex_liquid, [((tb, 0.0, 0.0), (base, x_, 0.0)) for tb, x_ in zip(tops, xs)],
                     blend="normal", role="liquid")
    bnd = max(3.0, W * 0.06)
    s_men = _ribbon(c, base, "fx/bonus_band", tex_band, [((tb, 0.0, bnd), (tb, 0.0, -bnd)) for tb in tops], role="surface")
    b_sg = c.bone("surfglow", tops[M // 2])
    s_sg = c.slot(b_sg, "fx/glow", W * 2.0, role="glow")
    ts = set(times_dense(0, D, 40))
    for h_ in hit:
        ts.update(times_dense(h_, min(D, h_ + 0.6), 90))
    ts = sorted(t for t in ts if 0 <= t <= D)
    for tb, x_ in zip(tops, xs):
        c.bone_keys(tb, "translate", ts, lambda u, x_=x_: (0.0, surf(x_, u)))
    c.show([s_body, s_men], hit[0], None)                           # the meter stays full after the clip
    c.show([s_sg], hit[0], D)
    c.color_keys(s_body, ts, lambda u: hexa(liq_c, 0.88))
    imp = lambda u: sum(smooth(u, h_, h_ + 0.02) / (1 + 18 * max(0.0, u - h_ - 0.02)) for h_ in hit)  # noqa: E731
    pulse = lambda u: (0.5 + 0.5 * math.sin(2 * math.pi * 1.6 * (u - t_full))) * smooth(u, t_full, t_full + 0.3) if full else 0.0  # noqa: E731
    c.color_keys(s_men, ts, lambda u: hexa(drop_c, c.a(0.45 + 0.25 * gfade(u) + 0.3 * min(1.0, imp(u)))))
    c.color_keys(s_sg, ts, lambda u: hexa(drop_c, c.a(gfade(u) * (0.12 + 0.6 * min(1.0, imp(u)) + 0.25 * pulse(u)))))
    c.bone_keys(b_sg, "scale", ts, lambda u: (1.0 + 0.5 * min(1.0, imp(u)), 0.5 + 0.3 * min(1.0, imp(u))))

    # bubbles: Poisson births (rate grows with the level, a burst at each impact), Stokes rise v ~ r^2, zig-zag,
    # swell as the pressure drops, pop at the moving surface
    pool = max(1, int(P["count"]))
    births = []
    t = hit[0]
    while True:
        lam = 1.5 + 9.0 * L(t)
        t += float(rng.exponential(1 / lam))
        if t > D - 0.3:
            break
        births.append((t, float(rng.uniform(-0.38, 0.38)) * W))
    for h_, x0 in zip(hit, x0s):
        births += [(h_ + float(rng.uniform(0.02, 0.2)), x0 + float(rng.uniform(-0.12, 0.12)) * W) for _ in range(3)]
    births.sort()
    rs = W / 70.0
    slots_b = []
    for i in range(pool):
        bb = c.bone(f"bub{i}", base)
        slots_b.append(dict(b=bb, s=c.slot(bb, "fx/bubble", 12.0 * rs, make=lambda: tex_bubble(), role="bubble"),
                            free=0.0, tr=[], sc=[], co=[], att=[(0.0, None)]))
    made = 0
    for t0, x0 in births:
        free = [sb for sb in slots_b if sb["free"] <= t0]
        if not free:
            continue
        rr = float(rng.uniform(2.2, 6.0)) * rs
        if surf(x0, t0) < 5 * rr:
            continue
        sb = free[0]
        v = float(np.clip(160.0 * (rr / (4.0 * rs)) ** 2, 90.0, 420.0)) * (H / 320.0) ** 0.5     # Stokes: v ~ r^2
        f, ph, zz = float(rng.uniform(2.5, 4.0)), float(rng.uniform(0, 6.28)), rr * 0.8
        y0 = rr + 2
        tau, t_pop = 0.0, None
        while tau < 3.0:
            tt = t0 + tau
            if tt >= D - 0.08:
                break
            if y0 + v * tau + rr >= surf(x0, tt) - 1:
                t_pop = tt
                break
            tau += 1 / 120
        if t_pop is None or t_pop - t0 < 0.08:
            continue
        made += 1
        life = t_pop - t0
        tl = times_dense(t0, t_pop + 0.06, 30)

        def st(u, t0=t0, x0=x0, v=v, f=f, ph=ph, zz=zz, rr=rr, y0=y0, t_pop=t_pop):
            tau_ = min(u, t_pop) - t0
            y = y0 + v * tau_
            depth = max(0.0, surf(x0, u) - y)
            swell = (1 + depth / (H * 1.2)) ** (-1 / 3) * (1.18 + 0.5 * smooth(u, t_pop, t_pop + 0.06))
            return x0 + zz * math.sin(2 * math.pi * f * tau_ + ph), y, swell * rr / (6.0 * rs)
        sb["tr"] += [(c.T(u), *st(u)[:2]) for u in tl]
        sb["sc"] += [(c.T(u), st(u)[2], st(u)[2]) for u in tl]
        sb["co"] += [(c.T(u), hexa("FFFFFF", c.a(0.9 * smooth(u, t0, t0 + 0.05) * (1 - smooth(u, t_pop, t_pop + 0.06))))) for u in tl]
        sb["att"] += [(c.T(t0), "fx"), (c.T(t_pop + 0.06), None)]
        sb["free"] = t_pop + 0.08
        _ = life
    for sb in slots_b:
        c.ab.slot_attachment(sb["s"], sb["att"])
        if sb["tr"]:
            c.ab.bone(sb["b"], "translate", _uniq(sb["tr"]), "linear")
            c.ab.bone(sb["b"], "scale", _uniq(sb["sc"]), "linear")
            c.ab.slot_color(sb["s"], _uniq(sb["co"]), "linear")

    # the drops: projectiles from each source onto the surface where they land
    hints = []
    for i in range(nd):
        sx_, sy_ = (float(v) for v in srcs[i % len(srcs)])
        tx = x0s[i] - sx_
        ty = (-H / 2 + surf(x0s[i], hit[i] - 1e-3)) - sy_
        res, _ = _sub(c, "projectile", launch[i], x=sx_, y=sy_, options=dict(tx=tx, ty=ty, flight=flight, arc=float(P["arc"]),
                                                                             size=float(P["drop_size"]), sparks=4),
                      color=drop_c, art={"tail": "tail", "glow": "drop", "spark": "drop"}, seed=60 + i)
        hints.append(res)
        c.ab.event(c.T(hit[i]), "fx_meter_drop", int=i + 1)
    beam = None
    if full:
        # overflow burst at the brim: droplets on drag-free parabolas stretched along their speed, a 1/t flash, a ring
        b_top = c.bone("brim", grp, 0, H / 2)
        s_fl = c.slot(b_top, "fx/glow", W * 4.0, role="glow")
        b_rg = c.bone("brimring", b_top, sy=0.35)
        s_rg = c.slot(b_rg, "fx/ring", W * 4.2, role="ring")
        tb_ = times_dense(t_full, t_full + 1.0, 40)
        c.show([s_fl, s_rg], t_full, t_full + 1.0)
        fl1 = lambda u: smooth(u, t_full, t_full + 0.02) / (1 + 20 * max(0.0, u - t_full - 0.02))  # noqa: E731
        c.color_keys(s_fl, tb_, lambda u: hexa(drop_c, c.a(min(1.0, 1.1 * fl1(u)))))
        c.bone_keys(b_top, "scale", tb_, lambda u: (0.6 + 0.6 * ease_out((u - t_full) / 0.2, 2.5),) * 2)
        sed = lambda u: (max(0.0, u - t_full) / 0.8) ** 0.4  # noqa: E731
        c.bone_keys(b_rg, "scale", tb_, lambda u: (0.1 + 1.0 * min(1.0, sed(u)),) * 2)
        c.color_keys(s_rg, tb_, lambda u: hexa(drop_c, c.a(0.85 * max(0.0, 1 - sed(u)) ** 1.5 * smooth(u, t_full, t_full + 0.02))))
        G = 1400.0 * (H / 320.0)
        for i in range(int(P["splash"])):
            side = -1.0 if i % 2 == 0 else 1.0
            xb = side * float(rng.uniform(0.05, 0.5)) * W
            bd = c.bone(f"drop{i}", b_top, xb, 0)
            sd = c.slot(bd, "fx/mote", float(rng.uniform(10, 18)) * rs, role="splash")
            vx, vy = side * float(rng.uniform(60, 240)) * rs ** 0.5, float(rng.uniform(260, 520)) * (H / 320.0) ** 0.5
            t0 = t_full + float(rng.uniform(0.0, 0.08))
            life = float(rng.uniform(0.6, 0.95))
            td = times_dense(t0, t0 + life, 40)

            def stp(u, vx=vx, vy=vy, t0=t0):
                tt = max(0.0, u - t0)
                vy_ = vy - G * tt
                sp = math.hypot(vx, vy_)
                return vx * tt, vy * tt - 0.5 * G * tt * tt, math.degrees(math.atan2(vy_, vx)) - 90, 1 + 1.3 * min(1.0, sp / 500)
            vals = [stp(u) for u in td]
            ang = np.degrees(np.unwrap(np.radians([v_[2] for v_ in vals])))
            c.ab.bone(bd, "translate", _uniq([(c.T(u), v_[0], v_[1]) for u, v_ in zip(td, vals)]), "linear")
            c.ab.bone(bd, "rotate", _uniq([(c.T(u), float(a_)) for u, a_ in zip(td, ang)]), "linear")
            c.ab.bone(bd, "scale", _uniq([(c.T(u), 1 / math.sqrt(v_[3]), v_[3]) for u, v_ in zip(td, vals)]), "linear")
            c.color_keys(sd, td, lambda u, t0=t0, life=life: hexa(drop_c, c.a(0.95 * (1 - smooth(u, t0 + 0.5 * life, t0 + life)))))
            c.ab.slot_attachment(sd, [(0.0, None), (c.T(t0), "fx"), (c.T(t0 + life), None)])
        c.ab.event(c.T(t_full), "fx_meter_full")
        if P["beam"]:
            first = len(c.slots)
            u_b = t_full - 0.05
            _sub(c, "light_beam", u_b, x=0, y=H * 0.5, duration=D - u_b,
                 options=dict(style="gold", height=H * 1.2, strands=3, dust=8, sparks=3, column_width=W * 2.2, column_alpha=0.3),
                 color=drop_c, art={"column": "beam"}, seed=90)
            beam_slots = c.slots[first:]
            _envelope(c, beam_slots, lambda u: smooth(u, u_b, u_b + 0.3) * (1 - smooth(u, D - 0.6, D - 0.05)),
                      [(u_b, u_b + 0.3), (D - 0.6, D)])
            _hide_after(c, beam_slots, D)
            beam = c.T(u_b)
    _normal_first(c)
    _dedupe_events(c)
    return c.result(duration=D, hits=[c.T(h_) for h_ in hit], launches=[c.T(t_) for t_ in launch], levels=levels,
                    full_at=None if t_full is None else c.T(t_full), beam_at=beam, bubbles=made, surface_bones=tops,
                    slosh_g=round(g, 1))


# ------------------------------------------------------------------ registry
RECIPES.update({
    "pick_reveal": dict(
        fn=pick_reveal, duration=1.7, kind="one-shot", color="FFC23A", count=8, normal_blend=True,
        summary="Pick-me tile reveal with exaggerated flip physics: flicked over (theta ~ t^2), edge-on behind a real puff "
                "(event fx_pick_swap: swap your art there, or swap_slot/swap_to does it), the face springs up from width 0 at "
                "the flip's own speed and overshoots by EXACTLY overshoot (damping solved), then settles. good=True: a shine; "
                "good=False: a dark smoke puff and a 'no' shake (bad=smoke) or an ice block that shatters (bad=ice). tile= "
                "flips the game's own tile through a carrier. Events fx_pick_reveal, fx_pick_swap, fx_pick_good | fx_pick_bad "
                "(+ the members' fx_puff, fx_shine, fx_ice_crack, fx_ice_shatter).",
        anchor="Tile centre (width x height).",
        options=dict(width=(150.0, "tile width"), height=(150.0, "tile height"), good=(True, "a good pick (shine) or a bad one"),
                     bad=("smoke", "bad pick look: smoke (dark puff + shake) | ice (ice_shatter)"),
                     flip=(0.16, "seconds from the flick to edge-on (the swap moment)"),
                     overshoot=(0.16, "how far past full width the face pops (0.16 = 16%), exact"),
                     bounce=(3.2, "frequency of the face spring (Hz)"),
                     tile=("", "the game's tile bone: a carrier is inserted above it and flipped (your keys untouched); "
                               "empty: a procedural tile is drawn"),
                     swap_slot=("", "game slot whose attachment switches at the swap moment"),
                     swap_to=("", "attachment to show in swap_slot at the swap moment"),
                     color2=("5A3CC8", "tile back colour (procedural tile)"), color3=("FFF2B0", "shine colour"),
                     shine_size=(1.0, "shine size multiplier"),
                     keep=(True, "the revealed face stays on after the clip (False: off at the end)")),
        tiers={"small": {"overshoot": 0.1, "shine_size": 0.8}, "big": {"overshoot": 0.2, "shine_size": 1.25},
               "mega": {"overshoot": 0.24, "shine_size": 1.5}, "epic": {"overshoot": 0.28, "shine_size": 1.8}}),
    "hold_respin": dict(
        fn=hold_respin, duration=4.0, kind="window", color="FFD24A", count=5,
        summary="Hold & respin: locked cells glow and breathe (electric_frame underglow + sparks and an additive smoke_glow "
                "haze, tiled exactly per respin, breaths per respin an integer so it loops exactly) and a respin counter ring "
                "depletes like a clock hand: one band mesh on a circle of bones, so the sweep shrinks with no clipping; each "
                "tick steps on a spring that overshoots by exactly recoil of the step; resets refill it under a rune_ring flash. "
                "Length = the respins (duration is not used). Events fx_hold_respin, fx_respin_tick (int = respins left), "
                "fx_respin_reset, fx_respin_end.",
        anchor="Board centre; cells are [dx, dy, w, h] from it, the counter ring sits at ring_x, ring_y.",
        options=dict(cells=(None, "[[dx, dy, w, h], ...] locked cells (default one cell of width x height at the anchor)"),
                     width=(140.0, "default cell width"), height=(140.0, "default cell height"),
                     respins=(3, "counter size (respins per lock)"), period=(1.2, "seconds per respin"),
                     resets=([], "tick numbers (1-based) after which a new symbol lands and the counter refills"),
                     ring_x=(0.0, "counter ring centre x"), ring_y=(150.0, "counter ring centre y"),
                     ring_size=(110.0, "counter ring diameter"), recoil=(0.3, "tick overshoot, fraction of one segment"),
                     breaths=(1, "glow breaths per respin (integer: exact loop)"),
                     color2=("FF8A1E", "locked cell glow colour"), color3=("FFB070", "cell smoke tint"))),
    "jackpot_wheel": dict(
        fn=jackpot_wheel, duration=5.0, kind="window", color="FFD24A", count=14, normal_blend=True,
        summary="Prize wheel with real friction: kicked to speed, then Coulomb + viscous drag (w' = -a - k w, closed form) "
                "solved so it stops at exactly duration with exactly the winner under the pointer. Every peg pushes the "
                "pointer to recoil and lets go (spring return, exact undershoot; it chatters at speed, clacks at the end), "
                "the segment under the pointer lights with a glow that trails behind, the winner strobes and explodes. "
                "wheel= / pointer= drive the game's bones through carriers. Events fx_jackpot_wheel, fx_wheel_tick "
                "(int = segment now under the pointer), fx_wheel_stop (int = winner), fx_explosion.",
        anchor="Wheel centre (radius); the pointer is at the top.",
        options=dict(segments=(12, "segment count"), winner=(0, "segment it stops on (0 = at the top at rest, clockwise)"),
                     spins=(4, "full turns before the last partial turn"), radius=(200.0, "wheel radius"),
                     kick=(0.35, "seconds of spin-up"), viscous=(0.8, "viscous drag rate k (1/s); 0 = pure Coulomb friction"),
                     wheel=("", "the game's wheel bone: a carrier at its origin is rotated (your keys untouched); empty: the "
                                "result's wheel_bone is a bone to parent wheel art under"),
                     pointer=("", "the game's pointer bone (pivot at its origin); empty: a procedural pointer is drawn"),
                     recoil=(24.0, "pointer deflection per peg (degrees)"), pointer_hz=(7.0, "pointer spring frequency (Hz)"),
                     pointer_damping=(0.22, "pointer spring damping ratio (0..1)"),
                     trail=(0.22, "seconds the segment glow takes to decay to 1/e behind the pointer"),
                     boom=(True, "the winner explodes"), boom_size=(1.0, "explosion size multiplier"),
                     color2=("FF5A2A", "winner colour"), color3=("FFC83A", "procedural pointer colour")),
        tiers={"small": {"spins": 2, "boom_size": 0.8}, "big": {"spins": 5, "boom_size": 1.2},
               "mega": {"spins": 6, "boom_size": 1.45}, "epic": {"spins": 8, "boom_size": 1.75}}),
    "meter_fill": dict(
        fn=meter_fill, duration=4.0, kind="window", color="2FD8FF", count=10, normal_blend=True,
        summary="Energy meter fill: drops fly in on arcs (projectile tails), each raises the liquid (critically damped) and "
                "kicks the surface into sloshing standing waves (modes cos(n pi x/W), water-wave dispersion, damped, "
                "superposed); bubbles rise at their Stokes speed, zig-zag, swell and pop at the moving surface (Poisson births); "
                "at full an overflow burst and a light_beam. The liquid is one mesh whose top rides surface bones. Length = "
                "the drops (duration is not used). Events fx_meter_fill, fx_meter_drop (int = drop number), fx_meter_full.",
        anchor="Meter centre (width x height); sources are drop launch points relative to it.",
        options=dict(width=(70.0, "meter inner width"), height=(320.0, "meter inner height"),
                     levels=([0.25, 0.5, 0.75, 1.0], "fill level after each drop (one drop each; 1 = full -> overflow)"),
                     sources=([[-260.0, 140.0], [250.0, 190.0], [-230.0, -70.0], [240.0, -30.0]], "[[x, y], ...] drop launch points"),
                     interval=(0.45, "seconds between launches"), flight=(0.5, "flight time of a drop"),
                     arc=(90.0, "how high a drop's arc bows"), drop_size=(26.0, "drop head size"),
                     slosh_hz=(3.0, "fundamental slosh frequency (Hz), sets g"), slosh_damping=(3.2, "slosh decay rate (1/s)"),
                     wobble=(7.0, "slosh amplitude per drop (units)"), splash=(12, "overflow droplets"),
                     beam=(True, "light_beam glow when full"), color2=("B8FBFF", "drop / glow colour"))),
})
ROLES.update({
    "pick_reveal": {"back": "tile back face (normal blend), square", "front": "revealed face (normal blend), square",
                    "cloud": "the puff's cloud lobe", "rays": "the shine's ray star", "block": "the ice block (bad=ice)"},
    "hold_respin": {"ring": "the counter band, a horizontal strip (bent round the ring as a mesh; profile across its height)",
                    "head": "glow on the moving end of the counter", "track": "faint full ring behind the counter",
                    "pip": "one segment pip", "lock": "breathing glow inside a locked cell", "flash": "refill flash",
                    "runes": "the refill rune ring", "smoke": "cell smoke blob", "spark": "a spark (cell edges, consumed segment)"},
    "jackpot_wheel": {"wedge": "one segment glow, square, the slice pointing UP from the centre",
                      "pointer": "the pointer (normal blend), pivot 18% from the top, tip DOWN",
                      "fire": "explosion fireball blob", "smoke": "explosion smoke blob", "flash": "explosion flash"},
    "meter_fill": {"liquid": "the liquid body (normal blend), stretched to the level", "surface": "the bright surface line, a horizontal strip",
                   "glow": "glow on the surface and at the brim", "bubble": "one bubble, round", "tail": "a drop's comet tail (head at the TOP)",
                   "drop": "a drop's head", "ring": "the overflow ring", "splash": "one overflow droplet", "beam": "the full-meter beam column"},
})
for _n, _d in ROLES.items():
    if _n in RECIPES:
        RECIPES[_n]["roles"] = _d
