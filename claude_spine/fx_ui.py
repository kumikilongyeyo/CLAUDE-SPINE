"""UI and symbol polish for ``fx_recipe``: ``button_press``, ``idle_shimmer``, ``focus_glow``, ``padlock``, ``popup``.

Same rules as fx_recipes.py (procedural textures, one group bone per recipe, closed-form dense linear keys, ``art=``
roles, additive light, normal blend only for solid art and drawn first in the run). Like fx_reels.py they MOVE the
game's own bones (a button squashes, a panel pops) only through inserted pure-translation carrier bones
(``fx_reels._carrier`` / ``_merge_keys``), so the artist's keys, constraints and weights stay untouched and several
presses on one button multiply into the same carrier. New here: they COMPOSE existing recipes as sub-recipes
(``shine`` micro-bursts, a ``puff`` with ``lobes=False``) merged into the same animation and the same draw-order run;
the sub-recipe's pictures are swapped with prefixed roles (``art={"shine_rays": ...}``).

Exaggerated real physics:

* Exact-overshoot springs. Every "spring back" is the step response of an underdamped oscillator,
  x(t) = 1 - e^(-z w t) (cos wd t + z / sqrt(1 - z^2) sin wd t), with the damping ratio SOLVED from the overshoot you
  ask for, z = -ln(os) / sqrt(pi^2 + ln(os)^2), so the first peak is exactly 1 + os at t = pi / wd. The ringing tail is
  windowed after the first peak so the clip ends exactly at rest.
* ``button_press``: the press is a quarter period of simple harmonic motion (the finger meets a spring: fast in,
  decelerating to the bottom), squash is volume preserving (sx^2 * sy = 1: the button bulges in x and in depth), the
  release is the exact-overshoot spring, and a ripple ring leaves the outline at release: its front spreads like
  sqrt(t) (a damped surface wave) and its brightness falls as 1 / perimeter (the ring's energy is shared along a
  longer and longer front). A ``shine`` micro-burst peaks with the overshoot.
* ``idle_shimmer``: a specular highlight on a glossy dome. The light turns at a constant rate, so the reflected band
  sits at R sin(phi): fast over the middle, lingering at the rims; it is foreshortened (thinner) toward the rims and
  fades with cos(phi) so it never pops at the outline. When the band crosses the hotspot the highlight aligns with the
  eye (a Blinn-Phong lobe) and a ``shine`` glint fires. Seamless loop with a rest gap.
* ``focus_glow``: the "breathing LED" curve, (e^sin - 1/e) / (e - 1/e): an exponential of a sine, which the eye reads as an
  even breath because brightness is perceived logarithmically. Enter = 1/t flash and a critically damped settle (no
  overshoot: no pop); exit = exponential decay normalised to reach exactly zero.
* ``padlock``: unlocking releases a spring: the shackle lifts (exact-overshoot step) and swings open about its long leg
  (exact-overshoot rotation spring); the recoil kicks the body into a damped jiggle e^(-t/tau) sin(2 pi f t). Then it pops
  off with a ``shine`` and a Sedov ring (r ~ t^0.4), or breaks: cracks along Voronoi lines, then shards fly on gravity
  parabolas and spin. Locking: the shackle swings shut under constant angular acceleration, drops in free fall and
  bounces with a coefficient of restitution (each bounce e^2 the height of the last), and clicks.
* ``popup``: the panel scales 0 -> 1 on the exact-overshoot spring with a volume-preserving jelly wobble on top
  (sx^2 * sy = s^3); a ``puff`` flash + ring at the start and a ``shine`` at the overshoot peak. Exit: anticipation (grows
  first, a quarter sine), then collapses with constant acceleration (s ~ 1 - t^2, zero speed at the turn) to exactly 0.

Registered into fx_recipes.RECIPES / ROLES at import.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from . import fx_recipes as FR
from .fx_recipes import (Ctx, RECIPES, ROLES, _blur, _colorize, _hexn, _mix, _rgb, ease_out, hexa, smooth, smooth_arr,
                         times_dense)
from .fx import _rgba
from .fx_reels import _carrier, _merge_keys
from .ir import ClippingAttachment, Key, RegionAttachment, Slot


# ------------------------------------------------------------------ maths
def _zeta(overshoot: float) -> float:
    """Damping ratio whose step response overshoots by exactly ``overshoot`` (a fraction, 0..1)."""
    if not 0 < overshoot < 1:
        raise ValueError(f"overshoot must be between 0 and 1 (a fraction past rest), got {overshoot}")
    L = math.log(overshoot)
    return -L / math.sqrt(math.pi ** 2 + L * L)


def _step(overshoot: float, hz: float):
    """Underdamped step response 0 -> 1 with its first peak exactly 1 + overshoot. Returns (f(t), t_peak)."""
    if hz <= 0:
        raise ValueError("spring frequency (Hz) must be > 0")
    z = _zeta(overshoot)
    w0 = 2 * math.pi * hz
    wd = w0 * math.sqrt(1 - z * z)
    q = z / math.sqrt(1 - z * z)

    def f(t: float) -> float:
        if t <= 0:
            return 0.0
        return 1 - math.exp(-z * w0 * t) * (math.cos(wd * t) + q * math.sin(wd * t))
    return f, math.pi / wd


def _settled(f, tp: float, end: float):
    """f windowed to exactly 1 by ``end``; untouched up to 1.5 peaks so the first overshoot stays exact."""
    a = min(1.5 * tp, 0.6 * end)
    return lambda t: 1 + (f(t) - 1) * (1 - smooth(t, a, end)) if t > 0 else 0.0


def breath(x: float) -> float:
    """Breathing-LED curve over one period (x in cycles): 0 at x = 0, 1 at x = 0.5, exactly periodic."""
    e = math.e
    return (math.exp(math.sin(2 * math.pi * x - math.pi / 2)) - 1 / e) / (e - 1 / e)


def _pos(P: dict, *names: str) -> list[float]:
    out = []
    for n in names:
        v = float(P[n])
        if v <= 0:
            raise ValueError(f"{n} must be > 0, got {v}")
        out.append(v)
    return out


def _choice(P: dict, name: str, allowed: tuple[str, ...]) -> str:
    v = str(P[name])
    if v not in allowed:
        raise ValueError(f"{name} must be {' | '.join(allowed)}, got {v!r}")
    return v


def _pair(v, name: str) -> tuple[float, float]:
    try:
        a, b = (float(q) for q in v)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be [x, y], got {v!r}") from None
    return a, b


def rr_polygon(w: float, h: float, rad: float, per_corner: int = 6) -> list[tuple[float, float]]:
    """Counter-clockwise rounded-rectangle outline (y up), ``per_corner`` points per corner arc."""
    rad = max(0.0, min(rad, w / 2, h / 2))
    pts = []
    for cx, cy, a0 in ((w / 2 - rad, h / 2 - rad, 0), (-w / 2 + rad, h / 2 - rad, 90),
                       (-w / 2 + rad, -h / 2 + rad, 180), (w / 2 - rad, -h / 2 + rad, 270)):
        for i in range(per_corner):
            a = math.radians(a0 + 90 * i / (per_corner - 1))
            pts.append((cx + rad * math.cos(a), cy + rad * math.sin(a)))
    return pts


# ------------------------------------------------------------------ composition helpers
def _sub(c: Ctx, recipe: str, u0: float, dur: float, x: float = 0.0, y: float = 0.0, options: dict | None = None,
         color: str = "", count: int = 0, tag: str | None = None, parent: str | None = None, gain: float = 1.0,
         behind_slot: str = "") -> dict:
    """Apply another recipe INSIDE this one: same animation, next in the draw-order run, retimed with this one.
    Art for it comes from this recipe's roles prefixed with ``<tag>_`` (``shine_rays`` -> shine's ``rays``)."""
    tag = tag or recipe
    pfx = f"{tag}_"
    art = {k[len(pfx):]: v for k, v in c.art.items() if k.startswith(pfx)}
    if behind_slot:                            # elsewhere in the draw order (e.g. behind the panel): the run continues as before
        order = dict(front_of="", behind=behind_slot)
    else:
        order = dict(front_of=c.last_slot, behind="") if c.last_slot else dict(front_of=c.front_of, behind=c.behind)
    res = FR.apply(c.p, recipe, x=x, y=y, scale=1.0, start=c.T(u0), duration=dur * c.k, color=color, intensity=c.I * gain,
                   seed=c.seed + 3 + len(c.slots), into=c.anim, parent=parent or c.group, count=count,
                   name=f"{c.prefix}_{tag}", options=options, art=art or None, **order)
    c.slots += res["slots"]
    if res["slots"] and not behind_slot:
        c.last_slot = res["slots"][-1]
    c.sub_bones = getattr(c, "sub_bones", 0) + res["bones"]
    for k, v in res.get("art", {}).items():
        c.art_used[pfx + k] = v
    for k, v in res.get("kit", {}).get("roles", {}).items():
        c.kit_used[pfx + k] = v
    seen, keep = set(), []
    for e in c.ab.a.events:                    # a sub-recipe can fire its own event twice on one tick
        key = (round(e.time, 4), e.name)
        if key not in seen:
            seen.add(key)
            keep.append(e)
    c.ab.a.events[:] = keep
    return res


def _raw_slot(c: Ctx, bone: str, blend: str = "additive") -> str:
    """A slot in this recipe's run with no attachment yet (for a clipping polygon)."""
    nm = c.sk.unique_name(bone, "slot")
    s = Slot(name=nm, bone=bone, blend=blend)
    if c.last_slot is not None:
        c.sk.add_slot(s, after=c.last_slot)
    elif c.behind:
        c.sk.add_slot(s, before=c.behind)
    elif c.front_of:
        c.sk.add_slot(s, after=c.front_of)
    else:
        c.sk.add_slot(s)
    c.last_slot = nm
    c.slots.append(nm)
    return nm


def _drive(c: Ctx, P_bone: str, tag: str, pivot_local: tuple[float, float], own: str) -> tuple[str, bool]:
    """The bone to scale: a carrier above the game's bone at the pivot, or our own bone there. Returns (bone, carrier?)."""
    if P_bone:
        at = c.sk.world()[c.group].to_world(*pivot_local)
        return _carrier(c, str(P_bone), tag, at), True
    return c.bone(own, c.group, *pivot_local), False


def _finish(c: Ctx, **extra) -> dict:
    res = c.result(**extra)
    res["bones"] = len(c.bones) + getattr(c, "sub_bones", 0)
    return res


# ------------------------------------------------------------------ textures
def tex_sheen(w: int = 256, h: int = 64) -> Image.Image:
    """A glossy sheen band, long along x: soft wide body, hot thin core, and a thinner second streak beside it (the
    double highlight of a lacquered surface). White; tint with the slot."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = (y - (h - 1) / 2) / ((h - 1) / 2)
    a = 0.55 * np.exp(-(yn / 0.30) ** 2) + 0.85 * np.exp(-(yn / 0.08) ** 2) + 0.5 * np.exp(-((yn - 0.62) / 0.06) ** 2)
    a *= smooth_arr(1 - np.abs(xn), 0.0, 0.3) * np.clip((1 - np.abs(yn)) / 0.12, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def tex_ui_frame(kind: str, corner: int, margin: int) -> tuple[Image.Image, int]:
    """Source for a 9-slice UI frame at 1 texture px = 1 design unit: an outline with ``corner`` radius sitting ``margin``
    px in from the border. kind line = thin hot line with a soft halo; glow = soft light outside (and a little inside) the
    outline; fill = the solid inside. Everything reaches exactly 0 at the border (no box edge when stretched), and the
    edge cross-section is constant along the middle. Returns (white image, slice px)."""
    cr, mg = int(corner), int(margin)
    n = 2 * (mg + cr) + 8
    y, x = np.mgrid[0:n, 0:n].astype(float)
    cc = (n - 1) / 2
    half = n / 2 - mg
    qx, qy = np.abs(x - cc) - (half - cr), np.abs(y - cc) - (half - cr)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - cr      # px, < 0 inside
    if kind == "line":
        a = np.exp(-(d / 1.7) ** 2) + 0.42 * np.exp(-(d / max(2.0, 0.42 * mg)) ** 2)
    elif kind == "glow":
        a = np.where(d > 0, 0.9 * np.exp(-(d / (0.36 * mg)) ** 2), 0.7 * np.exp(-(-d / 10.0) ** 2))
    elif kind == "fill":
        a = np.clip(0.5 - d, 0, 1) * (0.8 + 0.2 * np.exp(-(-d / 8.0) ** 2))
    else:
        raise ValueError(kind)
    edge = np.minimum(np.minimum(x, n - 1 - x), np.minimum(y, n - 1 - y))
    a *= np.clip(edge / 4.0, 0, 1)
    return _rgba(np.ones((n, n)), np.clip(a, 0, 1)), mg + cr + 2


UI_MARGIN = {"line": 14, "fill": 14, "glow": 44}


def _ui9(c: Ctx, parent: str, kind: str, W: float, H: float, corner: float, tag: str, role: str, share=None):
    """A 9-slice of ``tex_ui_frame`` whose outline lands exactly on W x H. Returns (slot, corner bones)."""
    cr = int(round(max(2.0, min(corner, W / 2 - 1, H / 2 - 1))))
    mg = UI_MARGIN[kind]
    name = f"fx/ui_{kind}9_c{cr}"
    sl = mg + cr + 2
    return c.slice9(parent, name, W + 2 * mg, H + 2 * mg, float(sl), make=lambda: tex_ui_frame(kind, cr, mg)[0],
                    tag=tag, share=share, role=role)


# padlock geometry, in units of the body width B (origin of the shackle shape: body top centre)
LOCK = dict(Hb=0.83, Rc=0.29, t=0.13, hv=0.16, li=0.14, pad=0.03, lift=0.2, key_y=0.06)


def tex_lock_body(color: str = "F2B632", w: int = 256) -> Image.Image:
    """The padlock body: a rounded block of polished metal (lit from the top-left, bevelled rim, embossed groove),
    with a keyhole. Opaque, coloured (normal blend)."""
    h = int(round(w * LOCK["Hb"]))
    y, x = np.mgrid[0:h, 0:w].astype(float)
    cx, cy = (w - 1) / 2, (h - 1) / 2
    hx, hy, rr = w / 2 - 3, h / 2 - 3, 0.2 * w
    qx, qy = np.abs(x - cx) - (hx - rr), np.abs(y - cy) - (hy - rr)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - rr     # px, < 0 inside
    alpha = np.clip(0.5 - d, 0, 1)
    xn, yn = (x - cx) / hx, (y - cy) / hy                                                           # yn: -1 top
    lum = 1.1 - 0.36 * (yn + 1) / 2
    rim = np.exp(-((-d - 5) / 3.2) ** 2) * (d < 0)
    lum += 0.42 * rim * np.clip(-0.85 * yn - 0.35 * xn, -1, 1)
    lum -= 0.16 * np.exp(-((yn + 0.5) / 0.03) ** 2) * (np.abs(xn) < 0.93)
    lum += 0.12 * np.exp(-((yn + 0.44) / 0.025) ** 2) * (np.abs(xn) < 0.93)
    lum += 0.24 * np.exp(-((xn * 0.6 + yn * 0.8 + 0.62) / 0.13) ** 2) * (d < -4)
    lum *= 1 - 0.5 * np.exp(-((d + 1) / 2.4) ** 2)
    # keyhole: a round hole and a tapering slot under it
    ky = cy - LOCK["key_y"] * w * 1.0
    kr = 0.105 * w
    hole = np.hypot(x - cx, y - ky) < kr
    sy0, sy1 = ky, ky + 0.36 * w
    half = 0.035 * w + (y - sy0) / (sy1 - sy0) * 0.03 * w
    slot = (y >= sy0) & (y <= sy1) & (np.abs(x - cx) <= half)
    m = (hole | slot).astype(np.float32)
    ms = _blur(m, 1.0)
    edge = np.clip(_blur(m, 3.0) - ms, 0, 1)                         # just outside the hole
    lum = lum * (1 - ms) + ms * (0.1 + 0.1 * np.clip((y - ky) / (0.4 * w), 0, 1))
    lum += 0.9 * edge * (y > ky) - 0.5 * edge * (y <= ky)
    base = np.array(_rgb(color), float) / 255
    rgb = base[None, None, :] * np.clip(lum, 0, 1.25)[..., None]
    rgb += np.clip(lum - 1.0, 0, 1)[..., None] * 0.9                  # hot highlights go white
    return _rgba(np.clip(rgb, 0, 1), alpha)


def tex_shackle(color: str = "C9D2DC", B: int = 200) -> Image.Image:
    """The padlock shackle: an upside-down U of polished steel bar (shaded as a tube lit from the top-left, with a hard
    specular), legs long enough to sit inside the body. Opaque (normal blend)."""
    g = {k: v * B for k, v in LOCK.items()}
    W = int(round(2 * g["Rc"] + g["t"] + 2 * g["pad"]))
    top = g["hv"] + g["Rc"] + g["t"] / 2 + g["pad"]
    H = int(round(top + g["li"] + g["pad"]))
    y, x = np.mgrid[0:H, 0:W].astype(float)
    X = x + 0.5 - W / 2
    Y = top - (y + 0.5)
    ht = g["t"] / 2
    ry = Y - g["hv"]
    rad = np.hypot(X, ry)
    arc = ry > 0
    s = np.where(arc, (rad - g["Rc"]) / ht, (np.abs(X) - g["Rc"]) / ht)
    nx = np.where(arc, X / np.maximum(rad, 1e-6), np.sign(X))
    ny = np.where(arc, ry / np.maximum(rad, 1e-6), 0.0)
    sc = np.clip(s, -1, 1)
    nz = np.sqrt(1 - sc * sc)
    n = np.stack([sc * nx, sc * ny, nz], -1)
    L = np.array([-0.45, 0.6, 0.66]); L /= np.linalg.norm(L)
    Hh = L + np.array([0, 0, 1.0]); Hh /= np.linalg.norm(Hh)
    lam = np.clip(n @ L, 0, 1)
    spec = np.clip(n @ Hh, 0, 1) ** 40
    lum = (0.3 + 0.75 * lam) * (1 - 0.35 * smooth_arr(np.abs(s), 0.7, 1.0))
    alpha = np.clip((1 - np.abs(s)) * ht / 1.2, 0, 1) * np.clip((Y + g["li"]) / 1.5, 0, 1)
    base = np.array(_rgb(color), float) / 255
    rgb = np.clip(base[None, None, :] * lum[..., None] + 0.85 * spec[..., None], 0, 1)
    return _rgba(rgb, alpha)


def voronoi_pieces(im: Image.Image, n: int, seed: int, color: str = "FFE7A0"):
    """Cut a picture into ``n`` Voronoi shards. Returns (crack-lines image, [(piece image, cx, cy) in px from the centre,
    y up]). The crack image glows along every shard border inside the picture."""
    arr = np.asarray(im.convert("RGBA")).copy()
    h, w = arr.shape[:2]
    alpha = arr[..., 3].astype(np.float32) / 255
    rng = np.random.default_rng(seed)
    pts = np.c_[rng.uniform(0.08 * w, 0.92 * w, n), rng.uniform(0.08 * h, 0.92 * h, n)]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    dist = np.stack([np.hypot(x - px, y - py) for px, py in pts])
    lab = np.argmin(dist, 0)
    srt = np.sort(dist, 0)
    crack = np.clip(1 - (srt[1] - srt[0]) / 2.2, 0, 1) * (alpha > 0.5)
    crack_img = _colorize(np.clip(crack + _blur(crack, 2.5) * 0.7, 0, 1), (255, 255, 255), (255, 244, 210), _rgb(color))
    pieces = []
    for k in range(n):
        m = (lab == k) & (alpha > 0.02)
        if m.sum() < 30:
            continue
        ys, xs = np.nonzero(m)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        piece = arr[y0:y1, x0:x1].copy()
        piece[..., 3] = (piece[..., 3] * m[y0:y1, x0:x1]).astype(np.uint8)
        pieces.append((Image.fromarray(piece, "RGBA"), float((x0 + x1) / 2 - w / 2), float(h / 2 - (y0 + y1) / 2)))
    return crack_img, pieces


# ------------------------------------------------------------------ button_press
def button_press(c: Ctx, P: dict) -> dict:
    """A button squashes down under the finger (volume preserving), holds, springs back with an exact overshoot; a
    ripple ring leaves its outline and a shine micro-burst peaks with the overshoot."""
    W, H = _pos(P, "width", "height")
    depth = float(P["depth"])
    if not 0 < depth < 0.6:
        raise ValueError(f"depth must be between 0 and 0.6 (0.14 = 14% shorter at the bottom), got {depth}")
    press, = _pos(P, "press")
    hold = float(P["hold"])
    if hold < 0:
        raise ValueError("hold must be >= 0 seconds")
    pivot = _choice(P, "pivot", ("bottom", "center"))
    col = _hexn(P["color"], "FFE9A0")
    f, tp = _step(float(P["overshoot"]), float(P["bounce"]))
    u_up = press + hold
    ripple, R = bool(P["ripple"]), float(P["ripple_size"])
    L = 0.55
    shine_dur = 0.5
    D = max(u_up + 0.62, u_up + L + 0.02, u_up + tp - 0.02 + shine_dur + 0.02)
    rel = _settled(f, tp, D - 0.05 - u_up)

    py = -H / 2 if pivot == "bottom" else 0.0
    drv, is_carrier = _drive(c, P["button"], "press", (0.0, py), "button")

    def sy(u):
        if u <= press:
            return 1 - depth * math.sin(0.5 * math.pi * u / press)       # quarter period: fast in, decelerating
        if u <= u_up:
            return 1 - depth
        return 1 - depth * (1 - rel(u - u_up))                          # exact-overshoot spring back to rest
    ts = sorted(set(times_dense(0, press, 160)) | set(times_dense(press, D, 90)) | {u_up + tp})
    _merge_keys(c, drv, "scale", ts, lambda u: (sy(u) ** -0.5, sy(u)), "mul")   # sx^2 * sy = 1

    grp = c.bone("press", c.group, 0, 0)
    out = {}
    if ripple:
        s_ring, corners = _ui9(c, grp, "line", W, H, float(P["corner"]), "ring", "ring")
        P0 = 2 * (W + H)
        rad = lambda u: R * math.sqrt(max(0.0, u - u_up) / L)  # noqa: E731   front ~ sqrt(t)
        tr = times_dense(u_up, u_up + L, 60)
        sgn = {"tl": (-1, 1), "tr": (1, 1), "bl": (-1, -1), "br": (1, -1)}
        for k_, b in corners.items():
            sx_, sy_ = sgn[k_]
            c.bone_keys(b, "translate", tr, lambda u, sx_=sx_, sy_=sy_: (sx_ * rad(u), sy_ * rad(u)))
        c.color_keys(s_ring, tr, lambda u: hexa(col, c.a(0.9 * P0 / (P0 + 2 * math.pi * rad(u))
                                                                  * smooth(u, u_up, u_up + 0.025) * (1 - smooth(u, u_up + 0.45 * L, u_up + L)))))
        c.show([s_ring], u_up, u_up + L)
        out["ripple_slot"] = s_ring
    if P["shine"]:
        fx_, fy_ = _pair(P["shine_at"], "shine_at") if P["shine_at"] is not None else (0.34, 0.22)
        _sub(c, "shine", u_up + tp - 0.02, shine_dur, x=fx_ * W, y=fy_ * H, color=_hexn(P["color2"], "FFF2B0"),
             count=int(P["count"]), options=dict(size=0.55 * min(W, H)))
    c.ab.event(c.T(0.0), "fx_button_down")
    c.ab.event(c.T(u_up), "fx_button_up")
    return _finish(c, duration=D * c.k, button_bone=drv, carrier=is_carrier, up_at=c.T(u_up), peak_at=c.T(u_up + tp),
                   **out)


# ------------------------------------------------------------------ idle_shimmer
def idle_shimmer(c: Ctx, P: dict) -> dict:
    """A glossy sheen sweeps across the symbol (clipped to its outline), then a glint pops where it crosses the
    hotspot; rest; loop."""
    D = float(P["period"]) if P["period"] else float(P["duration"])
    W, H = _pos(P, "width", "height")
    sweep, = _pos(P, "sweep")
    lead = float(P["lead"])
    band = float(P["band"])
    angle = float(P["angle"])
    strength = float(P["strength"])
    col = _hexn(P["color"], "FFFFFF")
    glint, gdur = bool(P["glint"]), 0.7
    if not 0 < band < 1:
        raise ValueError("band must be between 0 and 1 (band thickness as a fraction of the symbol's diagonal)")
    if lead < 0 or lead + sweep > D - 0.02:
        raise ValueError(f"period {D:g}s is too short for lead {lead:g}s + sweep {sweep:g}s (leave a rest gap)")
    hx, hy = _pair(P["hotspot"], "hotspot")
    sk = c.sk
    grp = c.bone("shimmer", c.group, 0, 0)
    sname = "fx/ui_sheen"

    if P["slot"]:
        from .fx import shine_sweep
        from .mesh import to_local
        from .rig import setup_hull_world
        slot = str(P["slot"])
        if not sk.has_slot(slot):
            raise ValueError(f"no slot {slot!r} to clip the shimmer to")
        if sk.slot(slot).attachment is None:
            raise ValueError(f"slot {slot!r} has no setup attachment to take the outline from")
        res = shine_sweep(c.p, slot, duration=sweep * c.k, start=c.T(lead), angle=angle, into=c.anim,
                          name=f"{c.prefix}_sweep", width=band)
        clip, s_band, b_band = res["clip_slot"], res["streak_slot"], res["bone"]
        c.ab.a.events[:] = [e for e in c.ab.a.events if not (e.name == "fx_shine" and abs(e.time - c.T(lead)) < 1e-6)]
        old = sk.attachment(s_band, "fx")
        c.tex(sname, tex_sheen)
        sk.set_attachment(s_band, "fx", RegionAttachment(path=sname, width=old.width, height=old.height))
        world = sk.world()
        tb = sk.slot(slot).bone
        wr = world[tb].rotation
        bb = sk.bone(b_band)
        bb.rotation = round((90 - angle) - wr, 3)                         # band leans `angle` from vertical
        dloc = math.radians(-angle - wr)
        dvec = (math.cos(dloc), math.sin(dloc))
        hull_w = setup_hull_world(c.p, slot)
        hl = to_local(world[tb], hull_w) - np.array([bb.x, bb.y])
        ext = float(np.max(np.abs(hl @ np.array(dvec))))
        thick = old.height
        lo, hi = hull_w.min(0), hull_w.max(0)
        hot_w = ((lo[0] + hi[0]) / 2 + hx * (hi[0] - lo[0]), (lo[1] + hi[1]) / 2 + hy * (hi[1] - lo[1]))
        hot_l = to_local(world[tb], np.array([hot_w])) - np.array([bb.x, bb.y])
        s_hot = float(hot_l[0] @ np.array(dvec))
        gx, gy = world[c.group].to_local(*hot_w)
        gsize = 0.24 * min(hi[0] - lo[0], hi[1] - lo[1]) / max(c.S, 1e-6)
        c.slots += [clip, s_band]
        if c.last_slot is None and not c.front_of and not c.behind:
            c.last_slot = s_band
        mode = "slot"
    else:
        rad = float(P["corner"])
        poly = rr_polygon(W, H, rad)
        b_clip = c.bone("clip", grp)
        clip = _raw_slot(c, b_clip)
        span = math.hypot(W, H)
        thick = span * band
        b_band = c.bone("band", grp, 0, 0, rot=90 - angle)
        s_band = c.slot(b_band, sname, span * 1.25, height=thick, make=tex_sheen, role="sheen")
        sk.set_attachment(clip, "fx", ClippingAttachment(end=s_band, vertexCount=len(poly),
                                                         vertices=[round(v, 2) for p in poly for v in p]))
        dvec = (math.cos(math.radians(-angle)), math.sin(math.radians(-angle)))
        ext = max(abs(px * dvec[0] + py * dvec[1]) for px, py in poly)
        gx, gy = hx * W, hy * H
        s_hot = gx * dvec[0] + gy * dvec[1]
        gsize = 0.24 * min(W, H)
        mode = "box"

    Lr = ext + 0.35 * thick                                                # the core has left the outline at +-Lr
    phi = lambda u: -math.pi / 2 + math.pi * min(1.0, max(0.0, (u - lead) / sweep))  # noqa: E731
    pos = lambda u: Lr * math.sin(phi(u))  # noqa: E731   R sin(phi): left -> right, fast mid, lingering at the rims
    phi_g = math.asin(max(-1.0, min(1.0, s_hot / Lr)))
    u_g = lead + sweep * (phi_g + math.pi / 2) / math.pi
    if glint and u_g - 0.03 + gdur > D - 0.005:
        raise ValueError(f"period {D:g}s is too short: the glint at {u_g:.2f}s needs {gdur:g}s to fade before the loop wraps")
    lobe = lambda u: math.exp(-((u - u_g) / 0.05) ** 2)  # noqa: E731   Blinn-Phong: brightest when it meets the hotspot
    ts = sorted(set(times_dense(lead, lead + sweep, 70)) | {u_g, 0.0, D})       # keys at 0 and D: the loop is exactly D long
    c.bone_keys(b_band, "translate", ts, lambda u: (pos(u) * dvec[0], pos(u) * dvec[1]))
    c.bone_keys(b_band, "scale", ts, lambda u: (1.0, 0.55 + 0.45 * math.cos(phi(u))))       # foreshortened at the rims
    c.color_keys(s_band, ts, lambda u: hexa(col, c.a(strength * max(0.0, math.cos(phi(u))) ** 0.6 * (1 + 0.5 * lobe(u)))))
    c.show([clip, s_band] if mode == "box" else [s_band], lead, lead + sweep)   # shine_sweep keys its own clip
    if glint:
        _sub(c, "shine", u_g - 0.03, gdur, x=gx, y=gy, color=_hexn(P["color2"], "FFF2B0"), count=int(P["count"]),
             options=dict(size=gsize * float(P["glint_size"])))
        c.ab.event(c.T(u_g), "fx_shimmer_glint")
    return _finish(c, duration=D, loop=D, mode=mode, clip_slot=clip, band_slot=s_band, glint_at=c.T(u_g) if glint else None,
                   sweep=(c.T(lead), c.T(lead + sweep)))


# ------------------------------------------------------------------ focus_glow
def focus_glow(c: Ctx, P: dict) -> dict:
    """Hover / focus frame: a 9-slice glowing line, a soft outer glow and a faint inner wash that breathe (exact
    loop); phase=enter flashes in and settles (no pop), phase=exit fades out and drifts outward."""
    phase = _choice(P, "phase", ("enter", "loop", "exit"))
    W, H = _pos(P, "width", "height")
    T = float(P["duration"])
    depth = float(P["depth"])
    if not 0 < depth <= 1:
        raise ValueError("depth must be in (0, 1]: how much of the line's brightness the breath takes away")
    col = _hexn(P["color"], "5AD8FF")
    flash_c = _hexn(P["color2"], "FFFFFF")
    ga, fa = float(P["glow"]), float(P["fill"])
    grp = c.bone("focus", c.group, 0, 0)
    cr = float(P["corner"])
    s_glow, glow_corners = _ui9(c, grp, "glow", W, H, cr, "glow", "glow")
    b_glow = c.sk.slot(s_glow).bone
    s_fill, _ = _ui9(c, grp, "fill", W, H, cr, "fill", "fill")
    s_frame, corners = _ui9(c, grp, "line", W, H, cr, "fill", "frame", share=c._last_s9)   # one corner set: line + wash
    slots = [s_glow, s_fill, s_frame]

    def level(b):
        """(line alpha, glow alpha, wash alpha, glow scale) at breath b in [0, 1]."""
        return (1 - depth) + depth * b, ga * (0.45 + 0.55 * b), fa * (0.4 + 0.6 * b), 1 + 0.025 * b

    def keys(ts, b_of, flash, on, scl):
        def lv(u):
            return level(b_of(u))
        c.color_keys(s_frame, ts, lambda u: hexa("%02X%02X%02X" % tuple(int(v) for v in _mix(_rgb(col), _rgb(flash_c), 0.55 + 0.45 * flash(u))),
                                                  c.a(on(u) * min(1.0, lv(u)[0] + (1 - lv(u)[0]) * flash(u)))))
        c.color_keys(s_glow, ts, lambda u: hexa("%02X%02X%02X" % tuple(int(v) for v in _mix(_rgb(col), _rgb(flash_c), flash(u))),
                                                 c.a(on(u) * min(1.0, lv(u)[1] + (0.8 - lv(u)[1]) * flash(u)))))
        c.color_keys(s_fill, ts, lambda u: hexa(col, c.a(on(u) * (lv(u)[2] + 0.3 * flash(u)))))
        c.bone_keys(b_glow, "scale", ts, lambda u: (lv(u)[3],) * 2)
        c.bone_keys(grp, "scale", ts, lambda u: (scl(u),) * 2)

    zero = lambda u: 0.0  # noqa: E731
    one = lambda u: 1.0  # noqa: E731
    if phase == "loop":
        D = T
        ts = times_dense(0, D, 40)
        keys(ts, lambda u: breath(u / D), zero, one, one)
        c.show(slots, 0, None)
        out = dict(loop=D)
    elif phase == "enter":
        D, = _pos(P, "enter")
        k_, at = 20.0 / D, 0.03
        tail = 1 / (1 + k_ * (D - at))
        fl = lambda u: smooth(u, 0, at) if u < at else max(0.0, (1 / (1 + k_ * (u - at)) - tail) / (1 - tail))  # noqa: E731   attack, 1/t, 0 at D
        w = 9.0 / D
        crit = lambda u: (1 + w * u) * math.exp(-w * u)  # noqa: E731   critically damped: no overshoot
        settle = lambda u: (crit(u) - crit(D)) / (1 - crit(D))  # noqa: E731
        ts = sorted(set(times_dense(0, D, 90)) | {at})
        keys(ts, zero, fl, lambda u: smooth(u, 0, at), lambda u: 1 + float(P["expand"]) * 1.6 * settle(u))
        c.show(slots, 0, None)
        c.ab.event(c.T(0.0), "fx_focus_in")
        out = dict(hands_off_to="loop")
    else:
        D, = _pos(P, "exit")
        tau = D / 3
        dec = lambda u: (math.exp(-u / tau) - math.exp(-D / tau)) / (1 - math.exp(-D / tau))  # noqa: E731
        ts = times_dense(0, D, 90)
        keys(ts, zero, zero, dec, lambda u: 1 + float(P["expand"]) * ease_out(u / D, 2.0))
        c.show(slots, 0, D)
        c.ab.event(c.T(0.0), "fx_focus_out")
        out = {}
    return _finish(c, duration=D * c.k, phase=phase, corner_bones=list(corners.values()),
                   glow_corner_bones=list(glow_corners.values()), **out)


# ------------------------------------------------------------------ padlock
def padlock(c: Ctx, P: dict) -> dict:
    """A procedural padlock. unlock: the key glows, the shackle springs open, the lock jiggles, pops off with a shine.
    break: same release, then it cracks and shatters. lock: the open shackle swings shut, drops, bounces, clicks."""
    mode = _choice(P, "mode", ("lock", "unlock", "break"))
    B, = _pos(P, "size")
    col = _hexn(P["color"], "F2B632")
    steel = _hexn(P["color2"], "C9D2DC")
    glow_c = _hexn(P["glow_color"], "FFE7A0")
    opening = float(P["open"])
    jig = float(P["jiggle"])
    f_sw, tp_sw = _step(float(P["overshoot"]), float(P["bounce"]))
    f_lf, tp_lf = _step(0.22, 7.0)
    g = {k: v * B for k, v in LOCK.items()}
    Hb, Rc, lift = g["Hb"], g["Rc"], g["lift"]
    rng = np.random.default_rng(c.seed + 307)
    sk = c.sk

    grp = c.bone("lock", c.group, 0, 0)
    b_jig = c.bone("jig", grp, 0, -Hb / 2)                                # the jiggle pivots on the bottom
    b_body = c.bone("body", b_jig, 0, Hb / 2)
    b_shk = c.bone("shackle", b_jig, -Rc, Hb)                             # pivot: the long (left) leg at the body top
    top = g["hv"] + Rc + g["t"] / 2
    b_shk_img = c.bone("shackle_img", b_shk, Rc, (top - g["li"]) / 2)
    shk_w = 2 * Rc + g["t"] + 2 * g["pad"]
    s_shk = c.slot(b_shk_img, f"fx/ui_shackle_{steel}", shk_w, make=lambda: tex_shackle(steel), blend="normal", role="shackle")
    s_body = c.slot(b_body, f"fx/ui_lockbody_{col}", B, make=lambda: tex_lock_body(col), blend="normal", role="body")
    solid = [s_shk, s_body]

    # timeline
    if mode == "lock":
        T1, T2, e = 0.28, 0.1, 0.35
        gacc = 2 * lift / T2 ** 2
        v0 = gacc * T2
        t_click = T1 + T2
        bounces, t_ = [], t_click
        for n in (1, 2):
            vn = v0 * e ** n
            bounces.append((t_, vn))
            t_ += 2 * vn / gacc
        t_rest = t_
        D = t_click + 0.62

        def lift_at(u):
            if u <= T1:
                return lift
            if u <= t_click:
                return lift - 0.5 * gacc * (u - T1) ** 2                 # free fall from the open height
            for tb, vn in bounces:
                q = u - tb
                if 0 <= q <= 2 * vn / gacc:
                    return vn * q - 0.5 * gacc * q * q                    # restitution: each hop e^2 the height of the last
            return 0.0
        swing_at = lambda u: opening * max(0.0, 1 - (u / T1) ** 2)  # noqa: E731   constant angular acceleration shut
        t_ev, ev = t_click, "fx_lock"
        q0 = t_click
    else:
        t_rel = 0.3
        sw = _settled(f_sw, tp_sw, 0.58)
        lf = _settled(f_lf, tp_lf, 0.4)
        lift_at = lambda u: lift * lf(u - t_rel)  # noqa: E731
        swing_at = lambda u: opening * sw(u - t_rel - 0.05)  # noqa: E731
        t_ev, ev = t_rel, "fx_unlock"
        q0 = t_rel
        if mode == "unlock":
            t_end = t_rel + 0.62
            D = t_end + 0.83
        else:
            t_crack, t_end = t_rel + 0.22, t_rel + 0.5
            D = t_end + 1.0

    # body jiggle (damped spring kicked by the release / the click) and a recoil squash
    amp = jig if mode != "lock" else 0.45 * jig

    def jiggle(u):
        q = u - q0
        if q <= 0:
            return 0.0
        v = amp * math.exp(-q / 0.12) * math.sin(2 * math.pi * 7.0 * q) * (1 - smooth(q, 0.3, 0.45))
        if mode == "break" and t_crack <= u < t_end:                      # strain: a fine tremble before it gives
            v += 1.6 * math.sin(2 * math.pi * 26 * (u - t_crack)) * smooth(u, t_crack, t_crack + 0.05)
        return v
    recoil = lambda u: 0.07 * ((u - q0) / 0.035) * math.exp(1 - (u - q0) / 0.035) * (1 - smooth(u - q0, 0.2, 0.3)) if u > q0 else 0.0  # noqa: E731

    ts = sorted(set(times_dense(0, D, 60)) | set(times_dense(q0, min(D, q0 + 0.5), 140)) | {q0, q0 + tp_sw + 0.05})
    if mode == "lock":
        ts = sorted(set(ts) | {T1, t_click, t_rest} | {tb for tb, _ in bounces} | {tb + vn / gacc for tb, vn in bounces})
    shk_until = D if mode != "break" else t_end
    tsk = [u for u in ts if u <= shk_until] + ([] if mode != "break" else [t_end])
    c.bone_keys(b_shk, "translate", sorted(set(tsk)), lambda u: (0.0, lift_at(u)))
    c.bone_keys(b_shk, "rotate", sorted(set(tsk)), lambda u: swing_at(u))
    tj = [u for u in ts if u <= (t_end if mode != "lock" else D)]
    c.bone_keys(b_jig, "rotate", tj, jiggle)
    pop_scale = (lambda u: 1 + 0.32 * ease_out((u - t_end) / 0.25, 2.2) if u > t_end else 1.0) if mode == "unlock" else (lambda u: 1.0)
    tsc = ts if mode == "unlock" else tj
    c.bone_keys(b_jig, "scale", tsc, lambda u: (pop_scale(u) * (1 - recoil(u)) ** -0.5, pop_scale(u) * (1 - recoil(u))))

    out = {}
    shards = []
    if mode == "break":
        att = sk.attachment(s_body, "fx")
        im = c.p.image(att.path)
        k = att.width / im.size[0]
        crack_img, pieces = voronoi_pieces(im, int(P["count"]), c.seed + 11, glow_c)
        tag = f"{att.path.replace('/', '_')}_{c.seed}_{int(P['count'])}"
        c.p.write_image(f"fx/ui_lockcrack_{tag}", crack_img)
        scale_g = B / 120.0
        for i, (pim, cx, cy) in enumerate(pieces):
            c.p.write_image(f"fx/ui_lockshard_{tag}_{i}", pim)
            bn = c.bone(f"shard{i}", b_jig, cx * k, Hb / 2 + cy * k)
            sl = c.slot(bn, f"fx/ui_lockshard_{tag}_{i}", pim.size[0] * k, blend="normal")
            a = math.atan2(cy, cx) if (cx or cy) else float(rng.uniform(0, 2 * math.pi))
            sp = float(rng.uniform(140, 260)) * scale_g
            shards.append(dict(b=bn, s=sl, vx=math.cos(a) * sp, vy=math.sin(a) * sp + float(rng.uniform(120, 260)) * scale_g,
                               rot=float(rng.uniform(-480, 480))))
        solid += [s_["s"] for s_ in shards]
        out["gravity"] = 1700.0 * scale_g
    # light (additive), after every solid layer
    b_key = c.bone("key", b_jig, 0, Hb / 2 + LOCK["key_y"] * B)
    s_key = c.slot(b_key, "fx/glow", 0.75 * B, role="glow")
    b_hole = c.bone("hole", b_jig, Rc, Hb)
    s_hole = c.slot(b_hole, "fx/glow", 0.7 * B, role="flash")
    b_ring = c.bone("ring", b_jig, *((0, Hb / 2) if mode != "lock" else (Rc, Hb)))
    s_ring = c.slot(b_ring, "fx/ring", 1.5 * B if mode != "lock" else 0.7 * B, role="ring")
    light = [s_key, s_hole, s_ring]
    if mode == "break":
        b_crk = c.bone("crack", b_body)
        s_crk = c.slot(b_crk, f"fx/ui_lockcrack_{tag}", B, role="crack")
        light.append(s_crk)

    tl = times_dense(0, D, 60)
    if mode == "lock":
        c.show(solid, 0, None)
        c.color_keys(s_key, ts, lambda u: hexa(glow_c, c.a(0.85 * math.exp(-((u - t_click - 0.04) / 0.12) ** 2))))
        c.color_keys(s_hole, ts, lambda u: hexa("FFFFFF", c.a(smooth(u, t_click - 0.005, t_click) / (1 + 25 * max(0.0, u - t_click)) * (1 - smooth(u, t_click + 0.3, D)))))
        c.show(light[:2], 0, D)
    else:
        turn = lambda u: smooth(u, 0.0, t_rel)  # noqa: E731   the key turning: the keyhole lights up
        c.color_keys(s_key, ts, lambda u: hexa(glow_c, c.a(0.9 * turn(u) / (1 + 10 * max(0.0, u - t_rel)) * (1 - smooth(u, t_end - 0.1, t_end + 0.1)))))
        c.color_keys(s_hole, ts, lambda u: hexa("FFFFFF", c.a(smooth(u, t_rel - 0.005, t_rel) / (1 + 30 * max(0.0, u - t_rel)) * (1 - smooth(u, t_rel + 0.3, t_end)))))
        if mode == "unlock":
            fade = lambda u: 1 - smooth(u, t_end, t_end + 0.22)  # noqa: E731
            for s in solid:
                c.color_keys(s, tl + [t_end], lambda u: hexa("FFFFFF", fade(u)))
            c.show(solid, 0, t_end + 0.24)
        else:
            c.show([s_shk], 0, D)
            c.show([s_body], 0, t_end)
            c.show([s_["s"] for s_ in shards], t_end, D)
            c.color_keys(s_shk, tl, lambda u: hexa("FFFFFF", 1 - smooth(u, D - 0.35, D)))
            c.color_keys(s_crk, ts, lambda u: hexa("FFFFFF", c.a(smooth(u, t_crack, t_crack + 0.08) * (0.7 + 0.3 * math.sin(60 * u)))))
        c.show(light[:2], 0, D)
        if mode == "break":
            c.show([s_crk], t_crack, t_end)
    # the ring: a Sedov blast front, r ~ t^0.4, thinning as it spreads
    t_ring = t_click if mode == "lock" else t_end
    sed = lambda u: (max(0.0, u - t_ring) / 0.5) ** 0.4  # noqa: E731
    tr = times_dense(t_ring, min(D, t_ring + 0.55), 50)
    c.bone_keys(b_ring, "scale", tr, lambda u: (0.25 + 1.0 * min(1.0, sed(u)),) * 2)
    c.color_keys(s_ring, tr, lambda u: hexa(glow_c, c.a(0.85 * max(0.0, 1 - sed(u)) ** 1.5 * smooth(u, t_ring, t_ring + 0.02))))
    c.ab.slot_attachment(s_ring, [(0.0, None), (c.T(t_ring), "fx"), (c.T(min(D, t_ring + 0.55)), None)] if c.T(t_ring) > 0
                         else [(0.0, "fx"), (c.T(min(D, t_ring + 0.55)), None)])

    if mode == "break":
        gv = out["gravity"]
        tb = times_dense(t_end, D, 40)
        for s_ in shards:
            c.bone_keys(s_["b"], "translate", tb, lambda u, s_=s_: (s_["vx"] * (u - t_end), s_["vy"] * (u - t_end) - 0.5 * gv * (u - t_end) ** 2))
            c.bone_keys(s_["b"], "rotate", tb, lambda u, s_=s_: s_["rot"] * (u - t_end))
            c.color_keys(s_["s"], tb, lambda u: hexa("FFFFFF", 1 - smooth(u, D - 0.35, D)))
        # the shackle flies off from where it is when the body gives way: up and away, spinning, on a parabola
        y0, a0 = lift_at(t_end), swing_at(t_end)
        vx, vy, w_ = 140.0 * B / 120, 420.0 * B / 120, 320.0
        tsh = times_dense(t_end, D, 40)
        c.bone_keys(b_shk, "translate", sorted(set(tsk) | set(tsh)),
                    lambda u: (vx * max(0.0, u - t_end), lift_at(u) if u <= t_end else y0 + vy * (u - t_end) - 0.5 * gv * (u - t_end) ** 2))
        c.bone_keys(b_shk, "rotate", sorted(set(tsk) | set(tsh)), lambda u: swing_at(u) if u <= t_end else a0 + w_ * (u - t_end))
        c.ab.event(c.T(t_crack), "fx_lock_crack")
        c.ab.event(c.T(t_end), "fx_lock_break")
        _sub(c, "shine", t_end - 0.02, 0.6, x=0, y=0, color=glow_c, count=int(P["twinkles"]), options=dict(size=0.6 * B), gain=0.8)
        out.update(shards=len(shards), break_at=c.T(t_end))
    elif mode == "unlock":
        _sub(c, "shine", t_end + 0.03, 0.8, x=0, y=0.15 * B, color=glow_c, count=int(P["twinkles"]), options=dict(size=0.7 * B),
             gain=0.75)
        c.ab.event(c.T(t_end), "fx_lock_pop")
        out.update(pop_at=c.T(t_end))
    else:
        _sub(c, "shine", t_click - 0.02, 0.55, x=Rc, y=Hb / 2, color=glow_c, count=int(P["twinkles"]), options=dict(size=0.45 * B))
        out.update(click_at=c.T(t_click), bounces=[c.T(tb) for tb, _ in bounces], restitution=0.35)
    c.ab.event(c.T(t_ev), ev)
    return _finish(c, duration=D * c.k, mode=mode, release_at=c.T(q0) if mode != "lock" else None, shackle_bone=b_shk,
                   body_bone=b_jig, **out)


# ------------------------------------------------------------------ popup
def popup(c: Ctx, P: dict) -> dict:
    """Toast / popup: the panel springs in from nothing with an exact overshoot and a jelly wobble, a puff flash +
    ring at the start, a shine at the peak. phase=out: anticipation, then it collapses to nothing."""
    phase = _choice(P, "phase", ("in", "out"))
    W, H = _pos(P, "width", "height")
    pivot = _choice(P, "pivot", ("center", "bottom"))
    col = _hexn(P["color"], "FFF1DC")
    py = -H / 2 if pivot == "bottom" else 0.0
    drv, is_carrier = _drive(c, P["panel"], "pop", (0.0, py), "panel")
    out = {}
    if phase == "in":
        f, tp = _step(float(P["overshoot"]), float(P["bounce"]))
        D = 0.9
        s = _settled(f, tp, D - 0.05)
        wob = float(P["wobble"])
        fj = 1.6 * float(P["bounce"])
        jel = lambda u: 1 + wob * math.exp(-u / 0.16) * math.sin(2 * math.pi * fj * u) * (1 - smooth(u, 0.45, D - 0.05))  # noqa: E731
        ts = sorted(set(times_dense(0, D, 90)) | {tp})
        _merge_keys(c, drv, "scale", ts, lambda u: (s(u) * jel(u) ** -0.5, s(u) * jel(u)), "mul")   # sx^2 sy = s^3
        tl = c.ab.a.bones[drv]["scale"]
        if tl[0].time > 0:                              # before its first key Spine shows the setup pose: hold it at 0
            tl.insert(0, Key(time=0.0, x=0.0, y=0.0))
        if P["puff"]:
            res = _sub(c, "puff", 0.0, 0.8, color=col, options=dict(lobes=False, size=0.24 * max(W, H),
                                                                    color2=_hexn(P["color2"], "FFF2B0")),
                       gain=0.7, behind_slot=str(P["under"]))
            out["ae_hint"] = dict(res["ae_hint"], note="optional realistic smoke behind the panel: " + res["ae_hint"]["note"])
        if P["shine"]:
            fx_, fy_ = _pair(P["shine_at"], "shine_at")
            _sub(c, "shine", tp - 0.03, 0.6, x=fx_ * W, y=fy_ * H, color=_hexn(P["color2"], "FFF2B0"), count=int(P["count"]),
                 options=dict(size=0.36 * min(W, H)))
        c.ab.event(c.T(0.0), "fx_popup_in")
        out.update(peak_at=c.T(tp), peak=1 + float(P["overshoot"]))
    else:
        ant, = _pos(P, "anticipation")
        X, = _pos(P, "exit")
        ta = min(0.1, 0.35 * X)
        D = X + (0.46 if P["puff"] else 0.0)

        def s(u):
            if u <= ta:
                return 1 + ant * math.sin(0.5 * math.pi * u / ta)          # grows first (a quarter sine: zero speed at the top)
            if u <= X:
                return (1 + ant) * (1 - ((u - ta) / (X - ta)) ** 2)       # then collapses with constant acceleration
            return 0.0
        ts = sorted(set(times_dense(0, X, 120)) | {ta, X})
        _merge_keys(c, drv, "scale", ts, lambda u: (s(u), s(u)), "mul")
        if P["puff"]:
            _sub(c, "puff", X - 0.04, 0.5, color=col, options=dict(lobes=False, size=0.14 * max(W, H),
                                                                   color2=_hexn(P["color2"], "FFF2B0")), gain=0.7)
        c.ab.event(c.T(0.0), "fx_popup_out")
        out.update(gone_at=c.T(X))
    return _finish(c, duration=D * c.k, phase=phase, panel_bone=drv, carrier=is_carrier, **out)


# ------------------------------------------------------------------ registry
_SHINE_ROLES = {"shine_glow": "the shine's core bloom", "shine_rays": "the shine's ray star", "shine_flare": "the shine's streak",
                "shine_ring": "the shine's halo rings", "shine_spark": "one shine twinkle"}
RECIPES.update({
    "button_press": dict(
        fn=button_press, duration=0.75, kind="one-shot", color="FFE9A0", count=3,
        summary="Button press with exaggerated spring physics: a fast volume-preserving squash (quarter-period SHM, sx^2*sy = 1), "
                "a hold, then an exact-overshoot spring back (damping solved from the overshoot); a 9-slice ripple ring leaves the "
                "outline at release (front ~ sqrt(t), brightness ~ 1/perimeter) and a shine micro-burst peaks with the overshoot. "
                "Moves your button through an inserted carrier bone (button=). Events fx_button_down, fx_button_up.",
        anchor="Button centre (width x height).",
        options=dict(width=(220.0, "button width"), height=(90.0, "button height"),
                     button=("", "bone of the button: a carrier is inserted above it at the pivot and squashed (your keys stay "
                                 "untouched). Empty: the result's button_bone is a bone to parent the button art under"),
                     pivot=("bottom", "bottom (squashes onto its base) | center"),
                     depth=(0.14, "squash at the bottom of the press (0.14 = 14% shorter)"),
                     press=(0.07, "seconds to the bottom of the press"), hold=(0.06, "seconds held down"),
                     overshoot=(0.45, "release overshoot past rest, as a fraction of the press depth (0..1, exact)"),
                     bounce=(6.0, "release spring frequency (Hz)"), ripple=(True, "ripple ring from the outline at release"),
                     corner=(26.0, "corner radius of the button outline (the ripple ring follows it)"),
                     ripple_size=(38.0, "how far the ripple ring travels out (units)"),
                     shine=(True, "shine micro-burst at the overshoot peak"),
                     shine_at=(None, "[fx, fy] shine position as fractions of width/height from the centre (default [0.34, 0.22])"),
                     color2=("FFF2B0", "shine colour"))),
    "idle_shimmer": dict(
        fn=idle_shimmer, duration=2.4, kind="loop", color="FFFFFF", count=2,
        summary="Symbol idle shimmer: a glossy sheen band sweeps across the symbol clipped to its outline (a rounded box, or "
                "slot= the part's own outline), moving as R sin(phi) like a highlight over a dome (fast mid, lingering at the "
                "rims, foreshortened, fading at the edges); where it crosses the hotspot a shine glint pops. Rest gap, exact loop. "
                "Event fx_shimmer_glint.",
        anchor="Symbol centre (width x height); ignored for the band when slot= is given (the glint still uses it).",
        options=dict(period=(None, "loop length in seconds (default: duration)"), width=(200.0, "box width (no slot=)"),
                     height=(200.0, "box height (no slot=)"), corner=(36.0, "box corner radius (no slot=)"),
                     slot=("", "clip to this slot's own outline (fx.shine_sweep: mesh hull or region rectangle)"),
                     angle=(25.0, "band lean from vertical (deg, + = /)"), band=(0.3, "band thickness, fraction of the diagonal"),
                     sweep=(0.6, "seconds the band takes to cross"), lead=(0.25, "seconds of rest before the sweep"),
                     strength=(0.75, "band brightness"), glint=(True, "shine glint where the band crosses the hotspot"),
                     hotspot=([-0.2, 0.22], "[fx, fy] glint point as fractions of the box from its centre"),
                     glint_size=(1.0, "glint size multiplier"), color2=("FFF2B0", "glint colour"))),
    "focus_glow": dict(
        fn=focus_glow, duration=2.0, kind="loop", color="5AD8FF",
        summary="Hover / focus glow: cell_glow-style 9-slice line + soft outer glow + faint inner wash, breathing on the "
                "breathing-LED curve (e^sin, exact loop). phase=enter: 1/t flash and a critically damped settle (no pop) that hands "
                "off exactly to the loop; phase=exit: exponential fade to exactly zero, drifting outward. Resizable through the "
                "corner bones. Events fx_focus_in (enter), fx_focus_out (exit).",
        anchor="Frame centre (width x height).",
        options=dict(phase=("loop", "enter | loop | exit"), width=(240.0, "frame width"), height=(96.0, "frame height"),
                     corner=(22.0, "corner radius of the outline"),
                     depth=(0.45, "how much of the line's brightness the breath takes away"), glow=(0.6, "outer glow strength"),
                     fill=(0.12, "inner wash strength (additive)"), enter=(0.35, "enter length (s)"), exit=(0.3, "exit length (s)"),
                     expand=(0.04, "scale the frame settles from (enter, x1.6) / drifts to (exit)"),
                     color2=("FFFFFF", "enter flash colour"))),
    "padlock": dict(
        fn=padlock, duration=1.75, kind="one-shot", color="F2B632", count=9, normal_blend=True,
        summary="Procedural padlock (shackle + body textures, normal blend). mode=unlock: the keyhole lights, the shackle lifts and "
                "swings open on exact-overshoot springs, the body jiggles (damped spring), then pops off with a shine and a Sedov "
                "ring. mode=break: same release, cracks along Voronoi lines, then shatters (shards on gravity parabolas, the "
                "shackle flies off spinning). mode=lock: the open shackle swings shut, drops in free fall, bounces with "
                "restitution and clicks. Events fx_unlock, fx_lock_pop, fx_lock_crack, fx_lock_break, fx_lock.",
        anchor="Lock body centre; the shackle rises above it.",
        options=dict(mode=("unlock", "lock | unlock | break"), size=(120.0, "body width"), color2=("C9D2DC", "shackle (steel) colour"),
                     glow_color=("FFE7A0", "keyhole glow / flash / ring colour"), open=(38.0, "how far the shackle swings open (deg)"),
                     overshoot=(0.3, "swing overshoot past open (fraction, exact)"), bounce=(3.5, "swing spring frequency (Hz)"),
                     jiggle=(8.0, "body jiggle amplitude (deg)"), twinkles=(4, "shine twinkles"))),
    "popup": dict(
        fn=popup, duration=0.9, kind="one-shot", color="FFF1DC", count=4,
        summary="Toast / popup entrance: the panel scales 0 -> 1 on an exact-overshoot spring with a volume-preserving jelly "
                "wobble, a puff (lobes=False: flash + ring) at the start and a shine at the overshoot peak; phase=out: anticipation "
                "(grows first), then collapses with constant acceleration to exactly 0 and a small puff. Moves your panel through "
                "an inserted carrier bone (panel=). Events fx_popup_in, fx_popup_out.",
        anchor="Panel centre (width x height).",
        options=dict(phase=("in", "in | out"), width=(360.0, "panel width"), height=(200.0, "panel height"),
                     panel=("", "bone of the panel: a carrier is inserted above it at the pivot (your keys stay untouched). "
                                "Empty: the result's panel_bone is a bone to parent the panel art under"),
                     pivot=("center", "center | bottom (a toast rising from its base)"),
                     overshoot=(0.14, "entrance overshoot (0.14 = peaks at exactly 114%)"), bounce=(3.2, "spring frequency (Hz)"),
                     wobble=(0.05, "jelly wobble on top of the spring (volume preserving)"),
                     puff=(True, "puff flash + ring"), shine=(True, "shine at the overshoot peak (phase in)"),
                     under=("", "slot to draw the puff behind (e.g. the panel), so its ring passes behind the panel"),
                     shine_at=([0.42, 0.36], "[fx, fy] shine position as fractions of width/height from the centre"),
                     anticipation=(0.06, "exit: how much it grows before collapsing"), exit=(0.3, "exit: seconds to vanish"),
                     color2=("FFF2B0", "shine / flash colour")),
        tiers={"small": dict(overshoot=0.08, wobble=0.03, shine=False), "big": dict(overshoot=0.18, wobble=0.07),
               "mega": dict(overshoot=0.22, wobble=0.08), "epic": dict(overshoot=0.26, wobble=0.1)}),
})
ROLES.update({
    "button_press": {"ring": "9-slice ripple ring art (give slice and px; generated: 1 px = 1 unit)", **_SHINE_ROLES},
    "idle_shimmer": {"sheen": "the sheen band, a horizontal strip (long along x), centred", **_SHINE_ROLES},
    "focus_glow": {"frame": "9-slice frame line art (give slice and px)", "fill": "9-slice inner wash art",
                   "glow": "9-slice outer glow art"},
    "padlock": {"body": "the lock body (normal blend), centred; break mode cuts its shards from this picture",
                "shackle": "the shackle: an upside-down U whose legs reach down into the body, centred on its own box",
                "glow": "the keyhole glow", "flash": "the flash where the shackle leaves / enters its hole",
                "ring": "the burst ring", "crack": "the crack lines (break mode)", **_SHINE_ROLES},
    "popup": {"puff_glow": "the puff flash", "puff_ring": "the puff ring", **_SHINE_ROLES},
})
for _n, _d in ROLES.items():
    if _n in RECIPES:
        RECIPES[_n]["roles"] = _d
