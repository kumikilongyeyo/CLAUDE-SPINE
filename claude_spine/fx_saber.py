"""Saber for ``fx_recipe``: a native port of Video Copilot's Saber look (energy beams, lightsabers, lasers, neon,
electric and fire outlines, haze), in Spine AND in After Effects.

The After Effects half is the template ``ae_templates/saber.jsx`` (built-in effects only, so it renders with aerender
anywhere, no plug-in). This module is the Spine half: the same beam drawn natively, so it works without AE, plus an
``ae_hint`` that renders the AE version with the SAME preset, colours and geometry for ``ae_fx_to_spine``. Both read
the one preset table that lives in saber.jsx (``PRESETS``), so they never drift apart.

Physics of the look:

* Glow falloff. A glowing tube's light falls off as 1/distance. The beam is a hot core plus ``glow_layers`` soft bands
  at doubling widths (one per octave of distance); band k's peak is ``(r0 / r_k) ** bias``, so with bias 1 each octave
  carries the same light and the sum falls off as 1/r (Saber's "realistic glow falloff"); bias < 1 spreads it into a
  haze, > 1 tightens it to a laser.
* Distortion. Travelling waves along the beam (several wavelengths, each moving an INTEGER number of cycles per loop)
  push the rows sideways, like Saber's turbulent core: the beam writhes and the loop closes exactly.
* Flicker. A product of two sines with integer cycles per loop (an arc that sputters, never a random pop).
* Draw on / off (Saber's start / end offset): rows past the head collapse onto it, the head running at an eased speed.

Every band is a strip mesh on ONE shared set of row bones (no deform keys): move a row bone and every band follows.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import numpy as np
from PIL import Image

from .fx import _rgba
from .fx_recipes import Ctx, RECIPES, ROLES, _hexn, _uniq, hexa, rr_point, smooth, times_dense

_JSX = Path(__file__).resolve().parent / "ae_templates" / "saber.jsx"


def presets() -> dict[str, dict]:
    """The preset table, read from the AE template (the single source of truth)."""
    m = re.search(r"/\*PRESETS\*/(\{.*?\})/\*END\*/", _JSX.read_text(), re.S)
    if not m:
        raise RuntimeError("saber.jsx has no /*PRESETS*/{...}/*END*/ table")
    return json.loads(m.group(1))


STYLE = ("color", "core_color", "core_size", "intensity", "spread", "bias", "distortion", "noise_size", "noise_speed",
         "flicker", "haze")


# ------------------------------------------------------------------ textures
CAP = 0.125                                          # the u fraction at each end of a strip that fades out (the caps)


def _ufade(w: int, h: int) -> np.ndarray:
    u = (np.arange(w) + 0.5)[None, :] / w * np.ones((h, 1))
    f = np.clip(np.minimum(u, 1 - u) / CAP, 0, 1)
    return f * f * (3 - 2 * f)


def tex_band(w: int = 64, h: int = 128) -> Image.Image:
    """A soft band: gaussian ACROSS (v = y), uniform ALONG (u = x) except the end caps, which fade to 0 (a glow ends
    softly, never with a square cut). Every edge is exactly 0, so bands never show a seam."""
    y = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    a = np.exp(-(y / 0.42) ** 2) * np.clip((1 - np.abs(y)) / 0.15, 0, 1) * _ufade(w, h)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def tex_core(w: int = 64, h: int = 64) -> Image.Image:
    """The hot core: a flat-topped profile (a solid tube seen from the side), soft only at its rim; caps as tex_band."""
    y = np.linspace(-1, 1, h)[:, None] * np.ones((1, w))
    a = np.clip((1 - np.abs(y) ** 4) * 1.15, 0, 1) * np.clip((1 - np.abs(y)) / 0.2, 0, 1) * _ufade(w, h)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def _strip(c: Ctx, bone: str, tex: str, make, rows: list, us: list, role: str, color: str) -> str:
    """fx_bonus._ribbon with explicit u per row (so the texture's end caps land on the extension rows only)."""
    from .fx_bonus import _run_slot
    from .ir import MeshAttachment
    art = c._art(role)
    blend = "additive"
    if art:
        tex, make, blend = art["tex"], None, art.get("blend", blend)
    tw, th = c.tex(tex, make)
    n = len(rows)
    pts, uvs = [], []
    for i, (a_, _) in enumerate(rows):
        pts.append(a_)
        uvs += [us[i], 0.0]
    for i in range(n - 1, -1, -1):
        pts.append(rows[i][1])
        uvs += [us[i], 1.0]
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


# ------------------------------------------------------------------ geometry
def _path(P: dict) -> tuple[list[tuple[float, float]], bool]:
    """The core path in design units (group space, y up) and whether it is closed."""
    kind = P["core"]
    if kind == "line":
        a, b = P["start"] or [-260.0, 0.0], P["end"] or [260.0, 0.0]
        return [tuple(map(float, a)), tuple(map(float, b))], False
    if kind == "points":
        pts = P["points"]
        if not pts or len(pts) < 2:
            raise ValueError("core=points needs points=[[x, y], ...] (2 or more)")
        pts, closed = [tuple(map(float, p)) for p in pts], bool(P["closed"])
        for _ in range(3 if len(pts) > 2 else 0):        # Chaikin corner cutting: round joins, like Saber's
            q = []
            m = len(pts)
            for i in range(m if closed else m - 1):
                (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % m]
                q += [(0.75 * x0 + 0.25 * x1, 0.75 * y0 + 0.25 * y1), (0.25 * x0 + 0.75 * x1, 0.25 * y0 + 0.75 * y1)]
            pts = q if closed else [pts[0]] + q + [pts[-1]]
        return pts, closed
    if kind == "circle":
        R = float(P["radius"] or 160.0)
        n = 96
        return [(R * math.cos(2 * math.pi * i / n), R * math.sin(2 * math.pi * i / n)) for i in range(n)], True
    if kind == "rect":
        w, h, cr = (list(P["rect"]) + [0.0])[:3] if P["rect"] else [420.0, 240.0, 30.0]
        n = 128
        return [rr_point(i / n, float(w), float(h), float(cr))[:2] for i in range(n)], True
    raise ValueError(f"core must be line | points | circle | rect (text is After Effects only: ae_template saber core=text), got {kind!r}")


def _resample(pts: list, closed: bool, step: float, max_rows: int) -> tuple[np.ndarray, np.ndarray, float]:
    """Rows evenly spaced by arc length: positions (n, 2), tangent angles (n,) in degrees (unwrapped), total length."""
    p = np.array(pts + ([pts[0]] if closed else []), float)
    seg = np.hypot(*np.diff(p, axis=0).T)
    if seg.sum() <= 1e-6:
        raise ValueError("the saber path has no length")
    s = np.concatenate([[0], np.cumsum(seg)])
    L = float(s[-1])
    n = int(min(max_rows, max(8, math.ceil(L / step) + 1)))
    q = np.linspace(0, L, n)
    xy = np.c_[np.interp(q, s, p[:, 0]), np.interp(q, s, p[:, 1])]
    if closed:                                       # periodic central differences: both ends get the SAME tangent
        ring = xy[:-1]
        d = np.roll(ring, -1, axis=0) - np.roll(ring, 1, axis=0)
        a_ = np.unwrap(np.arctan2(d[:, 1], d[:, 0]))
        turn = 2 * math.pi * round((a_[-1] - a_[0]) / (2 * math.pi)) if len(a_) > 1 else 0.0
        a_ = np.append(a_, a_[0] + (turn if abs(turn) > 0 else 2 * math.pi * np.sign(a_[-1] - a_[0] or 1)))
        ang = np.degrees(a_)
    else:
        d = np.gradient(xy, axis=0)
        ang = np.degrees(np.unwrap(np.arctan2(d[:, 1], d[:, 0])))
    return xy, ang, L


def _band(rows: list, ang: np.ndarray, ds: float, half: float, closed: bool) -> tuple[list, list]:
    """Ribbon rows for one band of half-width `half`. Its edges use normals smoothed over the band's own width and the
    inner edge is clamped to 0.65 x the local radius of curvature, so a wide glow never folds over itself in a tight
    curve (both edges, so the peak stays on the path); open ends get a tapered cap (a round glow tip, not a square cut)."""
    n = len(rows)
    th = np.radians(ang)
    win = max(1, int(round(half / max(ds, 1e-6))))
    if closed:
        base = th[:-1]
        k = np.ones(2 * win + 1) / (2 * win + 1)
        sm = np.convolve(np.concatenate([base[-win:] - (th[-1] - th[0]), base, base[:win] + (th[-1] - th[0])]), k, "valid")
        ths = np.append(sm, sm[0] + (th[-1] - th[0]))
    else:
        pad = np.concatenate([np.full(win, th[0]), th, np.full(win, th[-1])])
        ths = np.convolve(pad, np.ones(2 * win + 1) / (2 * win + 1), "valid")
    kap = np.gradient(ths) / max(ds, 1e-6)
    out = []
    for i in range(n):
        dlt = ths[i] - th[i]
        lim = 0.65 / abs(kap[i]) if abs(kap[i]) > 1e-9 else half
        hp = hm = min(half, lim)          # symmetric: a two-vertex strip peaks halfway between its edges, so an
                                            # asymmetric clamp would push the glow's brightest line off the path
        out.append(((rows[i], hm * math.sin(dlt), -hm * math.cos(dlt)), (rows[i], -hp * math.sin(dlt), hp * math.cos(dlt))))
    if closed:                                       # a ring has no ends: stay inside the texture's uniform middle
        us = list(np.linspace(CAP, 1 - CAP, n))
        return out, us
    cap = 0.7 * half                                 # open ends: full-width extensions that fade out along the beam
    (a0, b0), (a1, b1) = out[0], out[-1]
    out.insert(0, ((rows[0], a0[1] - cap, a0[2]), (rows[0], b0[1] - cap, b0[2])))
    out.append(((rows[-1], a1[1] + cap, a1[2]), (rows[-1], b1[1] + cap, b1[2])))
    us = [0.0] + list(np.linspace(CAP, 1 - CAP, n)) + [1.0]
    return out, us


# ------------------------------------------------------------------ the recipe
def saber(c: Ctx, P: dict) -> dict:
    T = float(P["duration"])
    pre = presets()
    if P["preset"] not in pre:
        raise ValueError(f"preset must be one of {sorted(pre)}, got {P['preset']!r}")
    S = dict(pre[P["preset"]])
    for k in STYLE:                                     # explicit options (and color=) win over the preset
        if P.get(k) is not None and k != "color":
            S[k] = P[k]
    if P["color"]:
        S["color"] = P["color"]
    if P["draw"] not in ("none", "on", "off", "on_off"):
        raise ValueError("draw must be none | on | off | on_off")
    col, hot = _hexn(S["color"], "0A64FF"), _hexn(S["core_color"], "F4FAFF")
    core, I, spread, bias = float(S["core_size"]), float(S["intensity"]), float(S["spread"]), float(S["bias"])
    if core <= 0 or spread <= 0 or bias <= 0 or I < 0:
        raise ValueError("core_size, spread and bias must be > 0, intensity >= 0")
    dist, nsize, nspeed = float(S["distortion"]), float(S["noise_size"]), max(1, int(round(S["noise_speed"])))
    flick, N = float(S["flicker"]), max(1, int(P["glow_layers"]))
    pts, closed = _path(P)
    xy, ang, L = _resample(pts, closed, float(P["row_step"]), int(P["max_rows"]))
    n = len(xy)
    ds = L / max(n - 1, 1)
    grp = c.bone("saber", c.group, 0, 0)
    rows = [c.bone(f"r{i}", grp, float(xy[i, 0]), float(xy[i, 1]), rot=float(ang[i])) for i in range(n)]

    # bands back to front: widest glow first, the core last. Band k: half-width r_k, peak (r0/r_k)^bias.
    r0 = 1.6 * core * spread
    bands = []
    for k in range(N - 1, -1, -1):
        rk = r0 * 2 ** k
        peak = min(1.0, I * (r0 / rk) ** bias)
        half = 2.2 * rk                                  # the texture's gaussian sigma ~ 0.42 of the half-width
        br, bu = _band(rows, ang, ds, half, closed)
        sl = _strip(c, grp, "fx/saber_band", tex_band, br, bu, role="glow", color=hexa(col, 1.0))
        bands.append((sl, peak, col))
    half_c = max(1.0, core * 0.75)
    cr, cu = _band(rows, ang, ds, half_c, closed)
    s_core = _strip(c, grp, "fx/saber_core", tex_core, cr, cu, role="core", color=hexa(hot, 1.0))
    bands.append((s_core, min(1.0, 1.0 * max(I, 0.4)), hot))
    c.show([b[0] for b in bands], 0, T if P["draw"] in ("off", "on_off") else None)

    # flicker: integer cycles per loop, so the loop closes exactly
    def fl(u, a=7, b=13, p1=0.3, p2=1.1):
        return 1 - flick * (0.5 + 0.5 * math.sin(2 * math.pi * a * u / T + p1)) * (0.5 + 0.5 * math.sin(2 * math.pi * b * u / T + p2))
    tf = times_dense(0, T, 30)
    for j, (sl, peak, cc) in enumerate(bands):
        is_core = j == len(bands) - 1
        c.color_keys(sl, tf, lambda u, peak=peak, cc=cc, is_core=is_core: hexa(cc, c.a(peak * (fl(u, 5, 11, 0.7, 2.3) if is_core else fl(u)))))

    # distortion + draw-on, on the row bones (translate relative to each row's setup point, in the group's frame)
    s_row = np.linspace(0, L, n)
    rng = np.random.default_rng(c.seed + 501)
    waves = []
    if dist > 0:
        for j in range(3):                               # wavelengths noise_size x (1, 1/2, 1/4), amplitude halving
            lam = nsize * 2.4 / 2 ** j
            if closed:                                   # a whole number of waves round a closed path: no seam
                lam = L / max(1, round(L / lam))
            waves.append((dist * 0.6 / 1.6 ** j, 2 * math.pi / lam, nspeed * (j + 1), float(rng.uniform(0, 2 * math.pi))))
    dr = P["draw"]
    tau = min(float(P["draw_time"]), T / 2 if dr == "on_off" else T)

    def head(u):                                         # (start, end) of the visible part, as arc length
        a, b = 0.0, L
        if dr in ("on", "on_off"):
            b = L * smooth(u, 0.0, tau)
        if dr in ("off", "on_off"):
            a = L * smooth(u, T - tau, T)
        return a, b
    nx, ny = -np.sin(np.radians(ang)), np.cos(np.radians(ang))
    animate = bool(waves) or dr != "none"
    if animate:
        ts = sorted(set(times_dense(0, T, 30 if waves else 20)) | ({tau, T - tau} if dr != "none" else set()))
        ts = [t for t in ts if 0 <= t <= T]
        for i, b in enumerate(rows):
            def pos(u, i=i):
                off = sum(A * math.sin(k_ * s_row[i] - 2 * math.pi * m * u / T + ph) for A, k_, m, ph in waves)
                x, y = xy[i, 0] + nx[i] * off, xy[i, 1] + ny[i] * off
                if dr != "none":
                    a, e = head(u)
                    sc = min(max(s_row[i], a), e) if e > a else a   # collapse onto the visible part's end
                    if sc != s_row[i]:
                        x, y = float(np.interp(sc, s_row, xy[:, 0])), float(np.interp(sc, s_row, xy[:, 1]))
                return (x - xy[i, 0], y - xy[i, 1])
            c.bone_keys(b, "translate", ts, pos)
            if dr != "none":                             # rows past the head shrink to nothing: no fans, a tapered tip
                def scl(u, i=i):
                    a, e = head(u)
                    fe = min(1.0, max(0.0, (e - s_row[i]) / ds)) if e < L - 1e-9 else 1.0   # head still drawing on
                    fa = min(1.0, max(0.0, (s_row[i] - a) / ds)) if a > 1e-9 else 1.0       # tail drawing off
                    f = min(fe, fa)
                    return (max(f, 0.0), max(f, 0.0))
                c.bone_keys(b, "scale", ts, scl)
    if dr in ("on", "on_off"):
        c.ab.event(c.T(tau), "fx_saber_on")
    if dr in ("off", "on_off"):
        c.ab.event(c.T(T), "fx_saber_off")

    # the AE version of the same beam: comp pixels = design units x px, the comp centred on the group bone
    px = float(P["px"])
    margin = 2.2 * r0 * 2 ** (N - 1) * 0.5 + core * 4
    lo, hi = np.min(np.array(pts), axis=0), np.max(np.array(pts), axis=0)
    span = np.maximum(np.abs(lo), np.abs(hi))
    Wc = int(2 * math.ceil((span[0] + margin) * px)) or 64     # centred on the group: twice the reach, in comp px
    Hc = int(2 * math.ceil((span[1] + margin) * px)) or 64
    Wc, Hc = min(Wc, 2048), min(Hc, 2048)
    to_comp = lambda p: [round(Wc / 2 + p[0] * px, 2), round(Hc / 2 - p[1] * px, 2)]  # noqa: E731
    prm = dict(width=Wc, height=Hc, duration=T, preset=P["preset"], glow_layers=N, draw=dr, draw_time=tau, seed=c.seed,
               **{k: (S[k] * px if k in ("core_size", "noise_size", "distortion") else S[k]) for k in STYLE if k != "color"},
               color=col)
    if P["core"] == "line":
        prm.update(core="line", start=to_comp(pts[0]), end=to_comp(pts[-1]))
    elif P["core"] == "points":
        prm.update(core="points", points=[to_comp(p) for p in pts], closed=closed)
    elif P["core"] == "circle":
        prm.update(core="circle", radius=round(float(P["radius"] or 160.0) * px, 2))
    else:
        w, h, cr = (list(P["rect"]) + [0.0])[:3] if P["rect"] else [420.0, 240.0, 30.0]
        prm.update(core="rect", rect=[w * px, h * px, cr * px])
    hint = dict(template="saber", params=prm, parent=c.group, front_of=c.slots[-1], x=0.0, y=0.0, scale=round(1 / px, 6),
                mode="additive", seq_mode="loop" if dr == "none" else "once", until=c.T(T), start=c.T(0.0),
                note="the same beam rendered by After Effects (built-in effects only): ae_template saber with params -> "
                     "render -> ae_fx_to_spine with these args; lower this recipe's intensity (or remove it) once the AE layer is in")
    return c.result(duration=T, rows=n, length=round(L, 2), bands=len(bands), preset=P["preset"], ae_hint=hint,
                    row_bones=rows[:1] + rows[-1:])


# ------------------------------------------------------------------ registry
RECIPES.update({
    "saber": dict(
        fn=saber, duration=2.0, kind="loop", color="",
        summary="A port of Video Copilot's Saber: energy beams, lightsabers, lasers, neon, electric / fire outlines, haze. A hot "
                "core along a line, polyline, circle or rounded rect, with soft glow bands at doubling widths whose peaks fall "
                "as (r0/r)^bias (bias 1 = a real glowing tube's 1/r falloff), travelling-wave distortion and flicker on integer "
                "cycles (exact loop), and draw on / off (Saber's start / end offset). `preset` = one of the Saber-style presets "
                "(default, red, green, purple, gold, neon, laser, electric, fire, energy, plasma, haze); style options win over "
                "it. ae_hint renders the same beam in After Effects with the saber template (text cores too). Events fx_saber, "
                "fx_saber_on, fx_saber_off.",
        anchor="Beam centre; the path's points are relative to it (design units, y up).",
        options=dict(preset=("default", "Saber-style preset (see summary)"),
                     core=("line", "line | points | circle | rect (text: After Effects only)"),
                     start=(None, "line start [x, y] (default [-260, 0])"), end=(None, "line end [x, y] (default [260, 0])"),
                     points=(None, "core=points: [[x, y], ...]"), closed=(False, "core=points: close the path"),
                     radius=(None, "core=circle radius (default 160)"), rect=(None, "core=rect [w, h, corner] (default [420, 240, 30])"),
                     core_color=(None, "core colour (preset)"), core_size=(None, "core thickness (preset)"),
                     intensity=(None, "glow strength (preset); the shared intensity= still scales alpha"),
                     spread=(None, "glow width multiplier (preset)"), bias=(None, "falloff exponent: 1 = 1/r, < 1 haze, > 1 laser (preset)"),
                     distortion=(None, "sideways writhe amplitude (preset; 0 = straight)"), noise_size=(None, "writhe wavelength (preset)"),
                     noise_speed=(None, "writhe cycles per loop, integer (preset)"), flicker=(None, "0..1 sputter depth (preset)"),
                     haze=(None, "AE only: churn of the outer glow (preset)"), glow_layers=(4, "glow bands (AE uses its own, default 6)"),
                     draw=("none", "none | on | off | on_off"), draw_time=(0.6, "seconds to draw on / off"),
                     row_step=(14.0, "row spacing along the path"), max_rows=(64, "row cap (bones)"),
                     px=(1.0, "AE comp pixels per design unit (for the ae_hint)"))),
})
ROLES.update({"saber": {"glow": "one glow band: a horizontal strip, soft top and bottom, uniform left to right",
                        "core": "the core strip, same layout, hotter and harder-edged"}})
RECIPES["saber"]["roles"] = ROLES["saber"]
