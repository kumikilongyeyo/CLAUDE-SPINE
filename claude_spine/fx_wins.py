"""Win presentation for ``fx_recipe``: ``payline``, ``win_highlight``, ``multiplier_stack``, ``win_rollup``.

What a slot shows after the reels stop on a win: the line is traced, the winning symbols light up, the multipliers fly
into the total, and the win counter rolls up. Same rules as fx_recipes.py (procedural textures, one group bone per
recipe, dense linear keys of closed-form functions of time, ``art=`` roles, every recipe fires ``fx_<recipe>``), and the
carrier-bone trick of fx_reels.py for popping the GAME's counter / total / symbol bones without touching their keys.

Exaggerated real physics:

* ``payline``: a comet head runs along the polyline at CONSTANT SPEED BY ARC LENGTH (not per segment, so a short hop
  and a long diagonal take the time their length says), after an eased start (the velocity ramps linearly from 0 over
  ``ease`` s: s = v t^2 / 2 t_e, then s = v (t - t_e/2)). The tail is the head's own past: every row of the tail strand
  sits where the head was ``lag`` seconds ago, so the tail is longer where the head is fast and folds round the corners.
  The head stretches along its velocity (volume preserving). Sparks are shed at every symbol with air drag and gravity,
  integrated exactly (x = v/k (1 - e^-kt), y with terminal velocity g/k); a 1/t flash and a Sedov (r ~ t^0.4) ring pop on
  each symbol. A glow line is left behind like a phosphor trace: each segment decays e^(-3t/linger) from the moment the
  head leaves it, so the line fades from its start first.
* ``win_highlight``: per symbol, a 9-slice frame and a soft 9-slice glow snap on at the hit time with a 1/t bloom burst
  (``shine`` optics: instant attack, 1/t tail, ray star, Sedov halo); the cell pops on an underdamped spring whose first
  overshoot is EXACTLY ``pop``; a specular sheen band sweeps across it (a travelling highlight, pre-masked to the
  rounded cell in a generated flipbook, so it never pokes outside and costs no clipping).
* ``multiplier_stack``: each badge flies on a BALLISTIC arc (a quadratic Bezier in linear time is exactly a parabola
  under constant acceleration) with a comet tail, shrinks and is absorbed; the total pops on a spring with exact
  overshoot, and overlapping pops SUPERPOSE (a linear spring is exactly the sum of its kicks), each kick a bit harder as
  the stack builds; a Sedov ring and 1/t flash per hit, a shine burst on the last one.
* ``win_rollup``: coins fall INTO the counter (a reverse projectile: from rest, constant acceleration toward it,
  r = r0 (1 - q^2), with a slight spiral that also starts at rest, so speed only grows), launched as a Poisson process
  (n arrivals in a window are uniform order statistics). The counter pops on every digit tick (a quick spring kick per
  tick, superposed) and with a big exact-overshoot pop at the end, its glow intensifies as the count climbs and with
  the win tier, a floor glow lights the ground under it, and a shine burst lands on ``fx_rollup_end``.

Events: ``fx_payline_hit`` (int = symbol index, string = "line<k>"), ``fx_payline_end`` (int = line index),
``fx_win_highlight_hit`` (int = cell index), ``fx_multiplier_launch`` / ``fx_multiplier_hit`` (int = source index),
``fx_multiplier_total``, ``fx_rollup_tick`` (int = tick index), ``fx_rollup_end``.

Registered into fx_recipes.RECIPES / ROLES at import (each registry entry also carries ``tiers``).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .fx import _rgba
from .fx_recipes import (Ctx, RECIPES, ROLES, _colorize, _frame_glow, _grid, _hexn, _mix, _palette, _rgb, _trail_keys,
                         _uniq, ease_out, hexa, smooth, smooth_arr, tex_flare, tex_frame9, tex_rays, tex_trail, times_dense)
from .fx_reels import _carrier, _merge_keys, _spring
from .ir import Sequence


# ------------------------------------------------------------------ textures
def tex_line(color: str = "FFD25A", w: int = 256, h: int = 64) -> Image.Image:
    """The glow line left behind a payline: hot thin core, soft halo, both ends fading over the outer 12% (two segments
    overlapping by that much at a symbol sum to a constant brightness: smoothstep(u) + smoothstep(1-u) = 1)."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = x / (w - 1)
    yn = (y - (h - 1) / 2) / ((h - 1) / 2)
    a = np.exp(-(yn / 0.13) ** 2) + 0.42 * np.exp(-(yn / 0.45) ** 2)
    a *= smooth_arr(xn, 0.0, _CAPF) * smooth_arr(1 - xn, 0.0, _CAPF)
    a *= np.clip((1 - np.abs(yn)) / 0.12, 0, 1)
    return _colorize(np.clip(a, 0, 1), *_palette(color))


_CAPF = 0.12          # fraction of the line texture that fades at each end


def tex_coin(color: str = "FFC83A", n: int = 128) -> Image.Image:
    """A gold coin, face on: bevelled rim, inner ring, embossed star, lit from the top-left, a specular glint. Opaque
    (normal blend); its x scale is keyed through zero to spin it."""
    S = 4
    N = n * S
    star = Image.new("L", (N, N), 0)
    d = ImageDraw.Draw(star)
    c = N / 2
    pts = []
    for k in range(10):
        a = -math.pi / 2 + k * math.pi / 5
        rad = N * (0.27 if k % 2 == 0 else 0.115)
        pts.append((c + math.cos(a) * rad, c + math.sin(a) * rad))
    d.polygon(pts, fill=255)
    star = np.asarray(star.resize((n, n), Image.LANCZOS), np.float32) / 255
    x, y = _grid(n)
    r = np.hypot(x, y)
    gold = np.array(_rgb(color), float)
    dark = np.array(_mix(tuple(gold), (110, 45, 0), 0.6))
    light = np.array(_mix(tuple(gold), (255, 255, 235), 0.6))
    lit = np.clip(0.5 + 0.55 * (-0.55 * x - 0.8 * y), 0, 1)[..., None]
    face = dark * (1 - lit) + light * lit
    rim = dark * lit + light * (1 - lit)                          # bevel: the rim is lit the other way
    rgb = np.where((r > 0.8)[..., None], rim, face * 0.85 + gold * 0.15)
    ring = np.exp(-((r - 0.66) / 0.025) ** 2)[..., None]
    rgb = rgb * (1 - 0.45 * ring)
    st = star[..., None]
    emb = np.clip(0.5 + 0.9 * (-0.55 * x - 0.8 * y), 0, 1)[..., None]
    rgb = rgb * (1 - st) + (dark * (1 - emb) + light * emb) * st
    spec = np.exp(-(((x + 0.38) / 0.16) ** 2 + ((y + 0.42) / 0.10) ** 2))[..., None]
    rgb = np.clip(rgb + 255 * 0.85 * spec, 0, 255)
    a = np.clip((0.97 - r) / 0.03, 0, 1)
    return _rgba(rgb / 255.0, a)


def sheen_frames(w: int, h: int, frames: int = 14, band: float = 0.2, corner: float = 0.14) -> list[Image.Image]:
    """A specular band sweeping diagonally (bottom-left to top-right) across a rounded cell, one image per position,
    pre-masked to the cell (no clipping needed). The first and last frames are empty: the band is outside, so a
    sequence that plays "once" and holds its last frame shows nothing between sweeps."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    px, py = x - (w - 1) / 2, (h - 1) / 2 - y
    m = min(w, h)
    hx, hy, cr = w / 2 * 0.9, h / 2 * 0.9, corner * m
    qx, qy = np.abs(px) - (hx - cr), np.abs(py) - (hy - cr)
    d = np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - cr
    mask = np.clip(-d / (0.05 * m), 0, 1)
    s = (px / (w / 2) + py / (h / 2)) / 2
    out = []
    for k, cpos in enumerate(np.linspace(-1 - 2.4 * band, 1 + 2.4 * band, frames)):
        a = 0.7 * np.exp(-((s - cpos) / band) ** 2) + 0.55 * np.exp(-((s - cpos + 0.9 * band) / (0.2 * band)) ** 2)
        a = np.clip(a * mask, 0, 1)
        a[a < 0.02] = 0
        if k in (0, frames - 1):
            a[:] = 0
        out.append(_rgba(np.ones((h, w)), a))
    return out


# ------------------------------------------------------------------ helpers
class _Poly:
    """A polyline walked by arc length: at(s) -> point, pose(s) -> (x, y, tangent deg). The tangent is the chord over a
    small window around s, so it turns smoothly through a vertex instead of snapping."""

    def __init__(self, pts):
        self.p = np.asarray(pts, float)
        dd = np.diff(self.p, axis=0)
        self.seg = np.hypot(dd[:, 0], dd[:, 1])
        if np.any(self.seg < 1e-6):
            raise ValueError("payline points: two consecutive points coincide")
        self.cum = np.concatenate([[0.0], np.cumsum(self.seg)])
        self.L = float(self.cum[-1])
        self.soft = 0.2 * float(self.seg.min())

    def at(self, s: float) -> tuple[float, float]:
        s = min(max(s, 0.0), self.L)
        k = min(int(np.searchsorted(self.cum, s, side="right")) - 1, len(self.seg) - 1)
        f = (s - self.cum[k]) / self.seg[k]
        q = self.p[k] + f * (self.p[k + 1] - self.p[k])
        return float(q[0]), float(q[1])

    def pose(self, s: float) -> tuple[float, float, float]:
        x, y = self.at(s)
        a, b = self.at(s - self.soft), self.at(s + self.soft)
        dx, dy = b[0] - a[0], b[1] - a[1]
        if math.hypot(dx, dy) < 1e-9:
            dx, dy = self.p[-1] - self.p[-2]
        return x, y, math.degrees(math.atan2(dy, dx))


def _ramp(v: float, te: float):
    """Arc length vs time with an eased start (velocity ramps 0 -> v over te, continuous), and its inverse."""
    if te <= 0:
        return (lambda t: v * max(0.0, t)), (lambda s: s / v)

    def s_of(t):
        if t <= 0:
            return 0.0
        return v * t * t / (2 * te) if t < te else v * (t - te / 2)

    def t_of(s):
        return math.sqrt(2 * te * s / v) if s < v * te / 2 else s / v + te / 2
    return s_of, t_of


def _points(val, what: str, min_n: int = 1) -> list[tuple[float, float]]:
    try:
        pts = [(float(p[0]), float(p[1])) for p in val]
    except (TypeError, ValueError, IndexError):
        raise ValueError(f"{what} must be a list of [x, y] pairs, got {val!r}") from None
    if len(pts) < min_n:
        raise ValueError(f"{what} needs at least {min_n} point(s)")
    return pts


def _up(hz: float, zeta: float):
    """Unit spring kick: peaks at exactly +1 (first overshoot), then rings down to 0."""
    x = _spring(1.0, hz, zeta)
    return lambda q: -x(q)


def _vis(c: Ctx, slot: str, on: float, off: float) -> None:
    c.show([slot], on, off)


def _seq(c: Ctx, bone: str, base: str, imgs: list[Image.Image], w: float, h: float) -> str:
    """A region slot playing a generated flipbook base00, base01, ... (written once per size)."""
    for i, im in enumerate(imgs):
        nm = f"{base}{i:02d}"
        try:
            c.p.image(nm)
        except FileNotFoundError:
            c.p.write_image(nm, im)
    sl = c.slot(bone, f"{base}00", w, height=h)
    att = c.sk.skin("default").attachments[sl]["fx"]
    att.path = base
    att.sequence = Sequence(count=len(imgs), start=0, digits=2)
    return sl


def _sedov(q: float, life: float) -> float:
    return min(1.0, (max(0.0, q) / life) ** 0.4)


def _bloom(q: float, fade0: float, fade1: float) -> float:
    """shine optics: 40 ms attack, then 1/t with a floor, out between fade0 and fade1 (seconds after the hit)."""
    if q < 0:
        return 0.0
    return smooth(q, 0, 0.04) * (0.18 + 0.82 / (1 + 14 * max(0.0, q - 0.04))) * (1 - smooth(q, fade0, fade1))


def _check_spring(P: dict) -> tuple[float, float]:
    z = float(P["damping"])
    if not 0 < z < 1:
        raise ValueError("damping must be between 0 and 1 (an underdamped spring is what overshoots)")
    hz = float(P["bounce"])
    if hz <= 0:
        raise ValueError("bounce (spring Hz) must be > 0")
    return hz, z


# ------------------------------------------------------------------ payline
def payline(c: Ctx, P: dict) -> dict:
    """A comet traces each winning line, left to right, at constant speed by arc length; sparks and a flash at every
    symbol it passes, a glow line left behind that fades. Several lines are staggered."""
    v, te, lag = float(P["speed"]), float(P["ease"]), float(P["tail"])
    linger, stagger = float(P["linger"]), float(P["stagger"])
    if v <= 0:
        raise ValueError("speed must be > 0 (units per second along the line)")
    if te < 0 or lag < 0 or linger <= 0 or stagger < 0:
        raise ValueError("ease, tail and stagger must be >= 0 and linger > 0")
    raw = P["lines"] if P["lines"] else [P["points"]]
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("lines must be a list of point lists")
    paths = [_Poly(_points(ln, "payline points", 2)) for ln in raw]
    cols = [_hexn(x, "FFD25A") for x in (P["colors"] or [P["color"] or "FFD25A"])]
    size, th, nsp = float(P["size"]), float(P["thickness"]), int(P["sparks"])
    rows = 20
    rng = np.random.default_rng(c.seed + 301)
    s_of, t_of = _ramp(v, te)
    grp = c.bone("payline", c.group)
    lines_out, hits = [], []
    D = 0.0
    for li, path in enumerate(paths):
        col = cols[li % len(cols)]
        hot = "%02X%02X%02X" % tuple(int(x) for x in _mix(_rgb(col), (255, 255, 255), 0.55))
        t0 = li * stagger
        T = t_of(path.L)
        hit_t = [t0 + t_of(float(s)) for s in path.cum]
        lg = c.bone(f"l{li}", grp)
        head_s = lambda u, t0=t0, path=path: min(path.L, s_of(u - t0))  # noqa: E731

        # the glow line left behind: one segment per hop, drawn by the head, fading from where it was drawn first
        tln = f"fx/wins_line_{col}"
        for j in range(len(path.seg)):
            L = float(path.seg[j])
            cap = _CAPF * L / (2 - 2 * _CAPF)                     # the faded ends overlap exactly at the symbols
            (x0, y0), (x1, y1) = path.p[j], path.p[j + 1]
            ux, uy = (x1 - x0) / L, (y1 - y0) / L
            bn = c.bone(f"l{li}_g{j}", lg, x0 - ux * cap, y0 - uy * cap, rot=math.degrees(math.atan2(uy, ux)))
            sl = c.slot(bn, tln, L + 2 * cap, ox=(L + 2 * cap) / 2, height=th * 1.5, make=lambda col=col: tex_line(col),
                        role="line", anchor="left", stretch=True)
            ta, tb = hit_t[j], hit_t[j + 1]
            off = tb + linger
            _vis(c, sl, ta, off)
            ts = sorted(set(times_dense(ta, tb, 60)) | set(times_dense(tb, off, 30)))
            c.bone_keys(bn, "scale", ts, lambda u, j=j, L=L, cap=cap, hs=head_s, path=path: (
                min(1.0, max(0.0, (hs(u) - float(path.cum[j]) + cap) / (L + 2 * cap))), 1.0))

            def la(u, ta=ta, tb=tb):
                if u <= tb:
                    return 0.8 * smooth(u, ta, ta + 0.03)
                q = (u - tb) / linger
                return 0.8 * math.exp(-3 * q) * (1 - smooth(q, 0.55, 1.0))
            c.color_keys(sl, ts, lambda u, la=la: hexa("FFFFFF", c.a(la(u))))

        # the tail: rows of a strand mesh where the head was lag * (row fraction) seconds ago
        s_tail, nodes = c.strand(lg, f"fx/trail_{col}", th * 2.4, 100.0, rows, make=lambda col=col: tex_trail(col),
                                 tag=f"l{li}_tail", role="tail")

        def pos_at(u, lagf, t0=t0, path=path):
            return path.pose(s_of(u - t0 - lagf * lag))
        ts_t = times_dense(t0, t0 + T + lag, 60)
        _trail_keys(c, nodes, rows, 100.0, ts_t, pos_at)
        _vis(c, s_tail, t0, t0 + T + lag)
        c.color_keys(s_tail, ts_t, lambda u, t0=t0, T=T: hexa("FFFFFF", c.a(0.95 * smooth(u, t0, t0 + 0.06)
                                                                             * (1 - smooth(u, t0 + T, t0 + T + max(lag, 0.05))))))

        # the head: glow stretched along its velocity (area kept), a spinning star
        b_head = c.bone(f"l{li}_head", lg)
        b_hg = c.bone(f"l{li}_hg", b_head)
        s_hg = c.slot(b_hg, "fx/glow", size * 2.2, role="glow")
        s_hs = c.slot(b_head, "fx/spark", size * 1.3, role="spark")
        hend = t0 + T + 0.15
        ts_h = sorted(set(times_dense(t0, hend, 60)) | set(hit_t))
        c.bone_keys(b_head, "translate", ts_h, lambda u, path=path, hs=head_s: path.at(hs(u)))
        angs = np.degrees(np.unwrap(np.radians([path.pose(head_s(u))[2] for u in ts_h])))
        c.ab.bone(b_hg, "rotate", _uniq([(c.T(u), float(a)) for u, a in zip(ts_h, angs)]), "linear")
        vr = lambda u, t0=t0: (min(1.0, max(0.0, u - t0) / te) if te > 0 else 1.0) if u - t0 <= T else 0.0  # noqa: E731
        c.bone_keys(b_hg, "scale", ts_h, lambda u, vr=vr: (1 + 0.6 * vr(u), 1 / (1 + 0.6 * vr(u))))
        c.bone_keys(b_head, "rotate", ts_h, lambda u, t0=t0: 540.0 * (u - t0))
        _vis(c, s_hg, t0, hend)
        _vis(c, s_hs, t0, hend)
        hal = lambda u, t0=t0, T=T: smooth(u, t0, t0 + 0.04) * (1 - smooth(u, t0 + T, t0 + T + 0.15))  # noqa: E731
        c.color_keys(s_hg, ts_h, lambda u, hal=hal, col=col: hexa(col, c.a(0.9 * hal(u))))
        c.color_keys(s_hs, ts_h, lambda u, hal=hal: hexa("FFFFFF", c.a(hal(u))))

        # every symbol it passes: a 1/t flash, a Sedov ring, sparks with drag + gravity
        for i, ti in enumerate(hit_t):
            xi, yi = (float(q) for q in path.p[i])
            ang = path.pose(float(path.cum[i]))[2]
            b_f = c.bone(f"l{li}_h{i}", lg, xi, yi)
            s_f = c.slot(b_f, "fx/glow", size * 2.8, role="hit")
            b_r = c.bone(f"l{li}_r{i}", lg, xi, yi)
            s_r = c.slot(b_r, "fx/ring", size * 2.4, role="ring")
            tf = times_dense(ti, ti + 0.6, 40)
            _vis(c, s_f, ti, ti + 0.6)
            _vis(c, s_r, ti, ti + 0.6)
            c.color_keys(s_f, tf, lambda u, ti=ti, col=col: hexa(col, c.a(0.55 * _bloom(u - ti, 0.3, 0.6))))
            c.bone_keys(b_f, "scale", tf, lambda u, ti=ti: (0.6 + 0.6 * ease_out((u - ti) / 0.2, 2.5),) * 2)
            c.bone_keys(b_r, "scale", tf, lambda u, ti=ti: (0.15 + 0.95 * _sedov(u - ti, 0.55),) * 2)
            c.color_keys(s_r, tf, lambda u, ti=ti: hexa(hot, c.a(0.85 * (1 - _sedov(u - ti, 0.55)) ** 1.5 * smooth(u - ti, 0, 0.02))))
            for k in range(nsp):
                bn = c.bone(f"l{li}_s{i}_{k}", lg, xi, yi)
                sl = c.slot(bn, "fx/mote", float(rng.uniform(8, 16)), role="mote")
                side = 1 if rng.random() < 0.5 else -1
                a = math.radians(ang + side * 90 + float(rng.uniform(-55, 55)))
                v0, kd, g, life = float(rng.uniform(140, 300)), float(rng.uniform(4, 7)), 520.0, float(rng.uniform(0.35, 0.6))
                vx, vy = math.cos(a) * v0, math.sin(a) * v0
                tsp = times_dense(ti, ti + life, 30)

                def sp_pos(u, ti=ti, vx=vx, vy=vy, kd=kd, g=g):
                    q = max(0.0, u - ti)
                    e = (1 - math.exp(-kd * q)) / kd
                    return vx * e, (vy + g / kd) * e - g * q / kd
                c.bone_keys(bn, "translate", tsp, sp_pos)
                c.color_keys(sl, tsp, lambda u, ti=ti, life=life: hexa(hot, c.a(0.95 * max(0.0, 1 - (u - ti) / life) ** 1.3)))
                _vis(c, sl, ti, ti + life)
            c.ab.event(c.T(ti), "fx_payline_hit", int=i, string=f"line{li}")
            hits.append([xi, yi, round(ti, 4)])
        c.ab.event(c.T(t0 + T), "fx_payline_end", int=li)
        lines_out.append(dict(start=c.T(t0), end=c.T(t0 + T), length=round(path.L, 2), hits=[c.T(t) for t in hit_t]))
        D = max(D, t0 + T + max(lag, linger, 0.6))
    return c.result(duration=round(D, 4), lines=lines_out, hits=hits, hit_times=[c.T(h[2]) for h in hits])


# ------------------------------------------------------------------ win_highlight
def _cells(P: dict) -> list[tuple[float, float, float, float, float]]:
    W, H, hit, st = float(P["width"]), float(P["height"]), float(P["hit"]), float(P["stagger"])
    raw = P["cells"] or [[0.0, 0.0]]
    out = []
    for i, cl in enumerate(raw):
        try:
            v = [float(x) for x in cl]
        except (TypeError, ValueError):
            raise ValueError(f"cells must be [dx, dy], [dx, dy, w, h] or [dx, dy, w, h, time]; got {cl!r}") from None
        if len(v) == 2:
            v += [W, H]
        if len(v) == 4:
            v.append(hit + i * st)
        if len(v) != 5 or v[2] <= 0 or v[3] <= 0:
            raise ValueError(f"cells must be [dx, dy], [dx, dy, w, h] or [dx, dy, w, h, time] with w, h > 0; got {cl!r}")
        out.append(tuple(v))
    return out


def win_highlight(c: Ctx, P: dict) -> dict:
    """Per-symbol win highlight: 9-slice frame + soft glow snap on with a shine burst at the hit time, the cell pops on
    an exact-overshoot spring, a sheen band sweeps across it until the window ends."""
    D = float(P["duration"])
    col = _hexn(P["color"], "FFD25A")
    bc = _hexn(P["color2"], "FFF2B0")
    cells = _cells(P)
    hz, z = _check_spring(P)
    up = _up(hz, z)
    pop, burst = float(P["pop"]), float(P["burst"])
    per, sweep = float(P["sheen_period"]), float(P["sheen_time"])
    if per <= 0 or sweep <= 0:
        raise ValueError("sheen_period and sheen_time must be > 0")
    syms = list(P["symbols"] or [])
    if len(syms) > len(cells):
        raise ValueError(f"symbols has {len(syms)} bones for {len(cells)} cells")
    F = 14
    rng = np.random.default_rng(c.seed + 311)
    grp = c.bone("win", c.group)
    out, carriers = [], []
    fade = lambda u: 1 - smooth(u, D - 0.3, D)  # noqa: E731
    for ci, (dx, dy, w, h, th_) in enumerate(cells):
        if not 0 <= th_ < D - 0.3:
            raise ValueError(f"cell {ci} lights at {th_} s: must be in [0, duration - 0.3) (duration {D})")
        g = c.bone(f"cell{ci}", grp, dx, dy)
        s_under = _frame_glow(c, g, w, h, tag=f"c{ci}_under", role="under")
        s_frame, corners = c.slice9(g, f"fx/frame9_{col}", w, h, 48.0, make=lambda: tex_frame9(col), tag=f"c{ci}_frame", role="frame")
        k = 128 / max(w, h)
        tw, tht = max(16, int(round(w * k))), max(16, int(round(h * k)))
        s_sh = _seq(c, g, f"fx/wins_sheen_{tw}x{tht}_", sheen_frames(tw, tht, F), w, h)
        m = max(w, h) * burst
        b_rays, b_core, b_halo = c.bone(f"c{ci}_rays", g), c.bone(f"c{ci}_core", g), c.bone(f"c{ci}_halo", g)
        s_rays = c.slot(b_rays, f"fx/rays_{bc}", m * 2.0, make=lambda: tex_rays(bc), role="rays")
        s_core = c.slot(b_core, "fx/glow", m * 1.4, role="glow")
        s_halo = c.slot(b_halo, "fx/ring", m * 1.7, role="ring")
        tws = []
        for q in range(4):
            sx, sy = (-1 if q in (0, 3) else 1), (1 if q < 2 else -1)
            bn = c.bone(f"c{ci}_tw{q}", g, sx * w * 0.45, sy * h * 0.45)
            sl = c.slot(bn, "fx/spark", float(rng.uniform(0.28, 0.42)) * min(w, h), color=hexa("FFFFFF", 1.0), role="spark")
            tws.append((bn, sl, th_ + float(rng.uniform(0.03, 0.2)), float(rng.uniform(-90, 90))))
        b_end = min(D, th_ + 1.1)
        for s in (s_under, s_frame, s_sh):
            _vis(c, s, th_, D)
        for s in (s_rays, s_core, s_halo):
            _vis(c, s, th_, b_end)
        ts = sorted(set(times_dense(th_, D, 30)) | set(times_dense(th_, min(D, th_ + 0.8), 90)))
        popf = lambda u, th_=th_: pop * up(u - th_) * fade(u) if u > th_ else 0.0  # noqa: E731
        c.bone_keys(g, "scale", ts, lambda u, popf=popf: (1 + popf(u),) * 2)
        if ci < len(syms) and syms[ci]:
            car = _carrier(c, str(syms[ci]), "pop")
            _merge_keys(c, car, "scale", ts, lambda u, popf=popf: (1 + popf(u),) * 2, "mul")
            carriers.append(car)
        breath = lambda u, th_=th_: 0.82 + 0.18 * math.sin(2 * math.pi * 1.1 * (u - th_) - math.pi / 2)  # noqa: E731
        snap = lambda u, th_=th_: smooth(u - th_, 0, 0.04)  # noqa: E731
        c.color_keys(s_under, ts, lambda u, th_=th_, breath=breath, snap=snap: hexa(col, c.a(
            snap(u) * fade(u) * min(1.0, 0.26 * breath(u) + 0.34 / (1 + 10 * max(0.0, u - th_))))))

        def frame_c(u, th_=th_, breath=breath, snap=snap):
            rgb = _mix(_mix(_rgb(col), (255, 255, 255), 0.5), _rgb(col), smooth(u - th_, 0.0, 0.3))
            return hexa("%02X%02X%02X" % tuple(int(x) for x in rgb), c.a(snap(u) * fade(u) * (0.7 + 0.2 * breath(u))))
        c.color_keys(s_frame, ts, frame_c)
        c.color_keys(s_sh, ts, lambda u, snap=snap: hexa("FFFBEA", c.a(0.6 * snap(u) * fade(u))))
        sweeps = []
        t = th_ + 0.12
        while t + sweep <= D - 0.15:
            sweeps.append(t)
            t += per
        c.ab.sequence(s_sh, "fx", [(c.T(t_), "once", 0, sweep / F * c.k) for t_ in sweeps] or [(c.T(th_), "hold", 0, 0)])
        tb = times_dense(th_, b_end, 40)
        bl = lambda u, th_=th_: _bloom(u - th_, 0.55, 1.1)  # noqa: E731
        c.color_keys(s_core, tb, lambda u, bl=bl: hexa(bc, c.a(0.5 * bl(u))))
        c.bone_keys(b_core, "scale", tb, lambda u, bl=bl: (0.6 + 0.5 * bl(u),) * 2)
        c.color_keys(s_rays, tb, lambda u, bl=bl: hexa("FFFFFF", c.a(0.8 * bl(u))))
        c.bone_keys(b_rays, "scale", tb, lambda u, th_=th_: (0.45 + 0.55 * ease_out((u - th_) / 0.22, 3.0),) * 2)
        c.bone_keys(b_rays, "rotate", tb, lambda u, th_=th_: 40.0 * ease_out((u - th_) / 1.1, 1.5))
        c.bone_keys(b_halo, "scale", tb, lambda u, th_=th_: (0.3 + 0.95 * _sedov(u - th_, 0.7),) * 2)
        c.color_keys(s_halo, tb, lambda u, th_=th_: hexa(bc, c.a(0.8 * (1 - _sedov(u - th_, 0.7)) ** 1.5 * smooth(u - th_, 0, 0.02))))
        for bn, sl, t0, rot in tws:
            t1 = min(D, t0 + 0.42)
            _vis(c, sl, t0, t1)
            c.ab.bone(bn, "scale", _uniq([(c.T(t0), 0, 0), (c.T(t0 + 0.15), 1, 1), (c.T(t1), 0, 0)]), "quad_in_out")
            c.ab.bone(bn, "rotate", _uniq([(c.T(t0), 0), (c.T(t1), rot)]), "linear")
        c.ab.event(c.T(th_), "fx_win_highlight_hit", int=ci)
        out.append(dict(hit=c.T(th_), corners=corners, sweeps=[c.T(t_) for t_ in sweeps]))
    return c.result(duration=D, cells=len(cells), hits=[o["hit"] for o in out], sweeps=[o["sweeps"] for o in out],
                    corner_bones=[b for o in out for b in o["corners"].values()], symbol_carriers=carriers)


# ------------------------------------------------------------------ multiplier_stack
def multiplier_stack(c: Ctx, P: dict) -> dict:
    """Each multiplier badge flies on a ballistic arc with a comet tail into the total; the total pops on a spring (exact
    overshoot, kicks superpose), a Sedov ring and flash per hit, a shine burst on the last."""
    srcs = _points(P["sources"], "sources")
    tx, ty = _points([P["target"]], "target")[0]
    T, stagger, arc, lag = float(P["flight"]), float(P["stagger"]), float(P["arc"]), float(P["tail"])
    if T <= 0 or stagger < 0 or lag < 0:
        raise ValueError("flight must be > 0, stagger and tail >= 0")
    hz, z = _check_spring(P)
    up = _up(hz, z)
    pop, growth, size = float(P["pop"]), float(P["growth"]), float(P["size"])
    col = _hexn(P["color"], "FFD25A")
    hot = _hexn(P["color2"], "FFF2B0")
    N = len(srcs)
    rows = 20
    rng = np.random.default_rng(c.seed + 321)
    grp = c.bone("mult", c.group)
    arrive = [i * stagger + T for i in range(N)]
    tl = arrive[-1]
    D = tl + 1.2
    fade = lambda u: 1 - smooth(u, D - 0.35, D)  # noqa: E731

    # the total: its aura (behind the flights), then per-hit flash + ring, the final shine
    b_t = c.bone("tgt", grp, tx, ty)
    b_aura = c.bone("aura", b_t)
    s_aura = c.slot(b_aura, "fx/glow", size * 5.0, role="aura")
    hit_fx = []
    for i in range(N):
        bf, br = c.bone(f"hf{i}", b_t), c.bone(f"hr{i}", b_t, sy=0.85)
        hit_fx.append((bf, c.slot(bf, "fx/glow", size * 3.6, role="flash"), br, c.slot(br, "fx/ring", size * 4.0, role="ring")))
    b_ray, b_fl = c.bone("rays", b_t), c.bone("flare", b_t)
    s_ray = c.slot(b_ray, f"fx/rays_{hot}", size * 6.0, make=lambda: tex_rays(hot), role="rays")
    s_fl = c.slot(b_fl, f"fx/flare_{hot}", size * 7.0, make=lambda: tex_flare(hot), role="flare")
    ts_all = times_dense(0, D, 30)
    _vis(c, s_aura, arrive[0] - 0.05 if arrive[0] > 0.05 else 0, D)
    level = lambda u: sum(smooth(u, a, a + 0.12) for a in arrive) / N  # noqa: E731
    flash = lambda u: sum(_bloom(u - a, 0.25, 0.6) for a in arrive)  # noqa: E731
    c.color_keys(s_aura, ts_all, lambda u: hexa(col, c.a(fade(u) * min(1.0, 0.2 * smooth(u, arrive[0] - 0.1, arrive[0])
                                                                       + 0.45 * level(u) + 0.25 * flash(u)))))
    c.bone_keys(b_aura, "scale", ts_all, lambda u: (0.7 + 0.35 * level(u),) * 2)
    for i, (bf, sf, br, sr) in enumerate(hit_fx):
        a = arrive[i]
        th = times_dense(a, a + 0.6, 40)
        _vis(c, sf, a, a + 0.6)
        _vis(c, sr, a, a + 0.6)
        c.color_keys(sf, th, lambda u, a=a: hexa(hot, c.a(_bloom(u - a, 0.25, 0.6))))
        c.bone_keys(bf, "scale", th, lambda u, a=a: (0.5 + 0.6 * ease_out((u - a) / 0.2, 2.5),) * 2)
        k_ = 1 + growth * i
        c.bone_keys(br, "scale", th, lambda u, a=a, k_=k_: (0.12 + 0.9 * min(1.5, k_) * _sedov(u - a, 0.55),) * 2)
        c.color_keys(sr, th, lambda u, a=a: hexa(col, c.a(0.9 * (1 - _sedov(u - a, 0.55)) ** 1.5 * smooth(u - a, 0, 0.02))))
    tb = times_dense(tl, D, 40)
    _vis(c, s_ray, tl, D)
    _vis(c, s_fl, tl, D)
    bl = lambda u: _bloom(u - tl, 0.6, 1.15)  # noqa: E731
    c.color_keys(s_ray, tb, lambda u: hexa("FFFFFF", c.a(bl(u))))
    c.bone_keys(b_ray, "scale", tb, lambda u: (0.45 + 0.55 * ease_out((u - tl) / 0.25, 3.0),) * 2)
    c.bone_keys(b_ray, "rotate", tb, lambda u: 35.0 * ease_out((u - tl) / 1.2, 1.5))
    c.color_keys(s_fl, tb, lambda u: hexa("FFFFFF", c.a(min(1.0, 1.1 * bl(u)))))
    c.bone_keys(b_fl, "scale", tb, lambda u: (0.25 + 0.95 * ease_out((u - tl) / 0.3, 3.0), 0.5 + 0.5 * bl(u)))

    # the total's pop: superposed exact-overshoot spring kicks, one per arrival, harder as the stack builds
    amps = [pop * (1 + growth * i) for i in range(N)]

    def scl(u):
        x = sum(A * up(u - a) for A, a in zip(amps, arrive) if u > a)
        return (1 + x * (1 - smooth(u, D - 0.2, D)),) * 2
    ts_p = sorted(set(times_dense(0, D, 40)) | {r_ for a in arrive for r_ in times_dense(a, min(D, a + 0.7), 120)})
    if P["total"]:
        tot = _carrier(c, str(P["total"]), "pop")
        _merge_keys(c, tot, "scale", ts_p, scl, "mul")
    else:
        tot = c.bone("total", grp, tx, ty)
        c.bone_keys(tot, "scale", ts_p, scl)

    # the flights: badge bone on a parabola (the game parents its badge under it), comet tail, head glow, sparks
    badges = []
    for i, (sx, sy) in enumerate(srcs):
        t0 = i * stagger
        mx, my = (sx + tx) / 2, (sy + ty) / 2
        ln = math.hypot(tx - sx, ty - sy) or 1.0
        nx, ny = -(ty - sy) / ln, (tx - sx) / ln
        if ny < 0:
            nx, ny = -nx, -ny                                    # the arc bows upward
        p0, p1, p2 = (sx, sy), (mx + nx * arc, my + ny * arc), (tx, ty)

        def bez(q, p0=p0, p1=p1, p2=p2):
            q = min(max(q, 0.0), 1.0)
            x = (1 - q) ** 2 * p0[0] + 2 * (1 - q) * q * p1[0] + q * q * p2[0]
            y = (1 - q) ** 2 * p0[1] + 2 * (1 - q) * q * p1[1] + q * q * p2[1]
            dx = 2 * (1 - q) * (p1[0] - p0[0]) + 2 * q * (p2[0] - p1[0])
            dy = 2 * (1 - q) * (p1[1] - p0[1]) + 2 * q * (p2[1] - p1[1])
            return x, y, math.degrees(math.atan2(dy, dx))
        s_tail, nodes = c.strand(grp, f"fx/trail_{col}", size * 0.75 * 2.4, 100.0, rows, make=lambda: tex_trail(col),
                                 tag=f"t{i}", role="tail")
        ts_t = times_dense(t0, t0 + T + lag * T, 60)
        _trail_keys(c, nodes, rows, 100.0, ts_t, lambda u, lagf, t0=t0, bez=bez: bez((u - t0 - lagf * lag * T) / T))
        _vis(c, s_tail, t0, t0 + T + lag * T)
        c.color_keys(s_tail, ts_t, lambda u, t0=t0: hexa("FFFFFF", c.a(0.95 * smooth(u, t0, t0 + 0.05) * (1 - smooth(u, t0 + T, t0 + T + max(0.05, lag * T))))))
        bb = c.bone(f"badge{i}", grp, sx, sy)
        b_hg = c.bone(f"b{i}_glow", bb)
        s_hg = c.slot(b_hg, "fx/glow", size * 2.4, role="glow")
        s_hs = c.slot(bb, "fx/spark", size * 1.4, role="spark")
        ts_b = times_dense(t0, t0 + T, 60)
        c.bone_keys(bb, "translate", ts_b + [t0 + T + 0.08], lambda u, bez=bez, t0=t0: (bez((u - t0) / T)[0] - sx, bez((u - t0) / T)[1] - sy) if u <= t0 + T else (tx - sx, ty - sy))

        def bsc(u, t0=t0):
            q = (u - t0) / T
            if q > 1:
                return (0.0, 0.0)                                 # absorbed into the total
            s = 1 + 0.2 * math.sin(math.pi * q / 0.35) if q < 0.35 else 1 - 0.4 * ((q - 0.35) / 0.65) ** 2
            return (s, s)
        c.bone_keys(bb, "scale", ts_b + [t0 + T + 0.08], bsc)
        c.bone_keys(b_hg, "rotate", ts_b, lambda u, t0=t0: 360.0 * (u - t0))
        _vis(c, s_hg, t0, t0 + T)
        _vis(c, s_hs, t0, t0 + T)
        c.color_keys(s_hg, ts_b, lambda u, t0=t0: hexa(col, c.a(0.85 * smooth(u, t0, t0 + 0.05))))
        c.color_keys(s_hs, ts_b, lambda u, t0=t0: hexa("FFFFFF", c.a(smooth(u, t0, t0 + 0.05))))
        for k in range(int(P["sparks"])):
            ts0 = t0 + T * (k + 0.5) / max(1, int(P["sparks"]))
            life = float(rng.uniform(0.3, 0.5))
            x0, y0, _ = bez((ts0 - t0) / T)
            bn = c.bone(f"b{i}_s{k}", grp, x0, y0)
            sl = c.slot(bn, "fx/mote", float(rng.uniform(7, 14)), role="mote")
            dx_, dy_ = float(rng.uniform(-18, 18)), float(rng.uniform(-30, 0))
            tsp = times_dense(ts0, ts0 + life, 24)
            c.bone_keys(bn, "translate", tsp, lambda u, ts0=ts0, life=life, dx_=dx_, dy_=dy_: (dx_ * ease_out((u - ts0) / life, 2),
                                                                                             dy_ * ((u - ts0) / life) ** 2))
            c.color_keys(sl, tsp, lambda u, ts0=ts0, life=life: hexa(hot, c.a(0.9 * max(0.0, 1 - (u - ts0) / life) ** 1.3)))
            _vis(c, sl, ts0, ts0 + life)
        c.ab.event(c.T(t0), "fx_multiplier_launch", int=i)
        c.ab.event(c.T(arrive[i]), "fx_multiplier_hit", int=i)
        badges.append(bb)
    c.ab.event(c.T(tl), "fx_multiplier_total")
    return c.result(duration=round(D * c.k, 4), hits=[c.T(a) for a in arrive], total_at=c.T(tl), total_bone=tot,
                    badge_bones=badges, target=[tx, ty])


# ------------------------------------------------------------------ win_rollup
def win_rollup(c: Ctx, P: dict) -> dict:
    """The win counter rolls up: coins fall into it, it pops on every digit tick, its glow and the floor glow under it
    intensify as the count climbs (and with the tier), a big pop + shine burst when the count lands."""
    D = float(P["duration"])
    settle = float(P["settle"])
    te = D - settle
    rate = float(P["rate"])
    if rate <= 0:
        raise ValueError("rate (digit ticks per second) must be > 0")
    if settle < 0.3 or te < 0.4:
        raise ValueError(f"settle must be >= 0.3 s and leave >= 0.4 s of counting inside duration {D}")
    hz, z = _check_spring(P)
    up_end = _up(hz, z)
    up_tick = _up(2.0 * hz, min(0.6, z + 0.15))
    W, H = float(P["width"]), float(P["height"])
    glow = float(P["glow"])
    n = int(P["coins"] if P["coins"] is not None else P["count"])
    if n < 0:
        raise ValueError("coins must be >= 0")
    col = _hexn(P["color"], "FFC83A")
    coin_c = _hexn(P["color2"], "FFC83A")
    hot = "%02X%02X%02X" % tuple(int(x) for x in _mix(_rgb(col), (255, 255, 255), 0.6))
    tick_pop, end_pop, spread, csize = float(P["tick_pop"]), float(P["end_pop"]), float(P["spread"]), float(P["coin_size"])
    rng = np.random.default_rng(c.seed + 331)
    grp = c.bone("rollup", c.group)
    ticks = [k / rate for k in range(int(math.ceil(te * rate - 1e-9)))]
    env = lambda u: smooth(u, 0, 0.2) * (1 - smooth(u, D - 0.35, D))  # noqa: E731
    prog = lambda u: min(1.0, max(0.0, u / te)) ** 0.7  # noqa: E731

    def tk(u):
        """recent tick flicker: each tick a 1/e-in-50-ms spike"""
        k = int(min(len(ticks) - 1, math.floor(u * rate))) if u >= 0 else -1
        return sum(math.exp(-(u - ticks[j]) / 0.05) for j in range(max(0, k - 5), k + 1)) if k >= 0 and u < te + 0.3 else 0.0
    bl = lambda u: _bloom(u - te, 0.45, settle - 0.05)  # noqa: E731

    # coins first (normal blend: solid gold), so the additive layers that follow share one batch
    coins = []
    if n:
        win_ = max(0.05, te - 0.75)
        launches = np.sort(rng.uniform(0, win_, n))           # Poisson process: n arrivals = sorted uniforms
        for i, t0 in enumerate(launches):
            T = float(min(rng.uniform(0.45, 0.7), te - t0))
            a = float(rng.uniform(0, 2 * math.pi))
            rad = spread * float(rng.uniform(0.75, 1.15))
            p0 = (math.cos(a) * rad, math.sin(a) * rad * 0.62 + H * 0.15)
            sw = float(rng.uniform(0.3, 0.7)) * (1 if rng.random() < 0.5 else -1)
            bn = c.bone(f"coin{i}", grp)
            sl = c.slot(bn, f"fx/wins_coin_{coin_c}", csize * float(rng.uniform(0.8, 1.2)), make=lambda: tex_coin(coin_c),
                        blend="normal", role="coin")
            coins.append(dict(b=bn, s=sl, t0=float(t0), T=T, p0=p0, sw=sw, f=float(rng.uniform(1.6, 3.0)), ph=float(rng.uniform(0, 6.28))))
    # floor glow under it, the counter glow (9-slice), a streak, a breathing ray star; the end burst
    b_floor = c.bone("floor", grp, 0, -H * 0.62, sy=0.26)
    s_floor = c.slot(b_floor, "fx/glow", W * 2.1, role="floor")
    b_pool = c.bone("pool", grp, 0, -H * 0.56, sy=0.14)
    s_pool = c.slot(b_pool, "fx/glow", W * 1.25, role="pool")
    b_rays = c.bone("rays", grp)
    s_rays = c.slot(b_rays, f"fx/rays_{hot}", max(W, H) * 2.0, make=lambda: tex_rays(hot), role="rays")
    s_under = _frame_glow(c, grp, W, H, tag="under", role="glow")
    b_under = c.sk.slot(s_under).bone
    b_fl = c.bone("streak", grp)
    s_fl = c.slot(b_fl, f"fx/flare_{col}", W * 2.3, make=lambda: tex_flare(col), role="flare")
    b_core, b_h1, b_h2 = c.bone("core", grp), c.bone("halo", grp, sy=0.6), c.bone("halo2", grp, sy=0.6)
    s_core = c.slot(b_core, "fx/glow", max(W, H) * 1.5, role="burst")
    s_h1 = c.slot(b_h1, "fx/ring", W * 1.6, role="ring")
    s_h2 = c.slot(b_h2, "fx/ring", W * 1.9, role="ring")
    tws = []
    for k in range(6):
        bn = c.bone(f"tw{k}", grp, float(rng.uniform(-0.55, 0.55)) * W, float(rng.uniform(-0.7, 0.9)) * H)
        sl = c.slot(bn, "fx/spark", float(rng.uniform(0.25, 0.45)) * H, color=hexa("FFFFFF", 1.0), role="spark")
        tws.append((bn, sl, te + float(rng.uniform(0.02, 0.35)), float(rng.uniform(-90, 90))))

    ts = sorted(set(times_dense(0, D, 30)) | {r_ for t in ticks for r_ in (t, t + 0.02)} | set(times_dense(te, min(D, te + 0.5), 90)))
    for s in (s_floor, s_pool, s_rays, s_under, s_fl):
        _vis(c, s, 0, D)
    G = lambda u: env(u) * glow * (0.3 + 0.7 * prog(u) + 0.16 * tk(u) + 0.3 * bl(u))  # noqa: E731
    c.color_keys(s_under, ts, lambda u: hexa(col, c.a(min(1.0, 0.75 * G(u)))))
    c.bone_keys(b_under, "scale", ts, lambda u: (1 + 0.04 * prog(u) + 0.05 * bl(u),) * 2)
    c.color_keys(s_fl, ts, lambda u: hexa("FFFFFF", c.a(min(1.0, 0.5 * G(u)))))
    c.bone_keys(b_fl, "scale", ts, lambda u: (0.75 + 0.25 * prog(u) + 0.3 * bl(u), 0.8 + 0.2 * prog(u)))
    c.color_keys(s_floor, ts, lambda u: hexa(col, c.a(min(1.0, env(u) * glow * (0.22 + 0.4 * prog(u) + 0.3 * bl(u))))))
    c.color_keys(s_pool, ts, lambda u: hexa(hot, c.a(min(1.0, env(u) * glow * (0.18 + 0.35 * prog(u) + 0.3 * bl(u))))))
    c.bone_keys(b_floor, "scale", ts, lambda u: (0.85 + 0.2 * prog(u),) * 2)
    c.color_keys(s_rays, ts, lambda u: hexa("FFFFFF", c.a(min(1.0, env(u) * glow * ((0.12 + 0.3 * prog(u)) * (0.8 + 0.2 * math.sin(2 * math.pi * u / 0.9)) + 0.6 * bl(u))))))
    c.bone_keys(b_rays, "rotate", ts, lambda u: 22.0 * u)
    c.bone_keys(b_rays, "scale", ts, lambda u: (0.75 + 0.25 * prog(u) + 0.3 * ease_out((u - te) / 0.3, 3),) * 2)
    tb = times_dense(te, D, 40)
    for s in (s_core, s_h1, s_h2):
        _vis(c, s, te, D)
    c.color_keys(s_core, tb, lambda u: hexa(col, c.a(min(1.0, 0.42 * bl(u) * max(0.6, glow)))))
    c.bone_keys(b_core, "scale", tb, lambda u: (0.6 + 0.6 * ease_out((u - te) / 0.2, 2.5),) * 2)
    for bn, sl, d0, k_ in ((b_h1, s_h1, 0.0, 1.0), (b_h2, s_h2, 0.07, 0.75)):
        c.bone_keys(bn, "scale", tb, lambda u, d0=d0, k_=k_: (0.25 + k_ * 1.0 * _sedov(u - te - d0, settle * 0.8),) * 2 if u >= te + d0 else (0.0, 0.0))
        c.color_keys(sl, tb, lambda u, d0=d0, k_=k_: hexa(col if k_ == 1 else hot, c.a(0.9 * k_ * (1 - _sedov(u - te - d0, settle * 0.8)) ** 1.5
                                                                                          * smooth(u - te - d0, 0, 0.02))))
    for bn, sl, t0, rot in tws:
        t1 = min(D, t0 + 0.42)
        _vis(c, sl, t0, t1)
        c.ab.bone(bn, "scale", _uniq([(c.T(t0), 0, 0), (c.T(t0 + 0.15), 1, 1), (c.T(t1), 0, 0)]), "quad_in_out")
        c.ab.bone(bn, "rotate", _uniq([(c.T(t0), 0), (c.T(t1), rot)]), "linear")
    for cn in coins:
        t0, T, (x0, y0), sw = cn["t0"], cn["T"], cn["p0"], cn["sw"]
        tc = times_dense(t0, t0 + T, 50)

        def cpos(u, t0=t0, T=T, x0=x0, y0=y0, sw=sw):
            q = min(1.0, max(0.0, (u - t0) / T))
            ph = sw * q * q                                     # the spiral also starts at rest
            r_ = 1 - q * q                                      # constant acceleration toward the counter, from rest
            return (r_ * (x0 * math.cos(ph) - y0 * math.sin(ph)), r_ * (x0 * math.sin(ph) + y0 * math.cos(ph)))
        c.bone_keys(cn["b"], "translate", tc, cpos)
        c.bone_keys(cn["b"], "scale", tc, lambda u, cn=cn, t0=t0, T=T: (
            math.cos(2 * math.pi * cn["f"] * (u - t0) + cn["ph"]) * (1 - 0.5 * ((u - t0) / T) ** 2), 1 - 0.5 * ((u - t0) / T) ** 2))
        c.color_keys(cn["s"], tc, lambda u, t0=t0, T=T: hexa("FFFFFF", c.a(smooth((u - t0) / T, 0, 0.1) * (1 - smooth((u - t0) / T, 0.86, 1.0)))))
        _vis(c, cn["s"], t0, t0 + T)

    # the counter's pop: a quick kick per digit tick, the big exact-overshoot pop when the count lands (superposed)
    def scl(u):
        x = sum(tick_pop * up_tick(u - t) for t in ticks if 0 < u - t < 0.5)
        if u > te:
            x += end_pop * up_end(u - te)
        return (1 + x * (1 - smooth(u, D - 0.15, D)),) * 2
    ts_p = sorted(set(times_dense(0, D, 90)) | set(ticks) | set(times_dense(te, min(D, te + 0.4), 240)))
    if P["counter"]:
        cnt = _carrier(c, str(P["counter"]), "pop")
        _merge_keys(c, cnt, "scale", ts_p, scl, "mul")
    else:
        cnt = c.bone("counter", grp)
        c.bone_keys(cnt, "scale", ts_p, scl)
    for k, t in enumerate(ticks):
        c.ab.event(c.T(t), "fx_rollup_tick", int=k)
    c.ab.event(c.T(te), "fx_rollup_end")
    return c.result(duration=D, ticks=len(ticks), tick_times=[c.T(t) for t in ticks], end_at=c.T(te), counter_bone=cnt,
                    coins=len(coins), arrivals=sorted(c.T(cn["t0"] + cn["T"]) for cn in coins))


# ------------------------------------------------------------------ registry
_V_LINE = [[-320.0, 160.0], [-160.0, 0.0], [0.0, -160.0], [160.0, 0.0], [320.0, 160.0]]
RECIPES.update({
    "payline": dict(
        fn=payline, duration=1.6, kind="window", color="FFD25A",
        summary="A comet traces each winning line left to right at constant speed by arc length (eased start), its tail the "
                "head's own past (rows lag in time, rotated to the tangent); a 1/t flash, a Sedov ring and sparks with drag + "
                "gravity at every symbol; a glow line left behind that fades like a phosphor trace. Several lines are staggered. "
                "Length follows the line (speed), not duration. Events fx_payline, fx_payline_hit (int = symbol index, "
                "string = line<k>) at every symbol, fx_payline_end (int = line index). The result's hits = [[x, y, t], ...] "
                "feed win_highlight cells.",
        anchor="Origin of the line points (the reel grid centre).",
        options=dict(points=(_V_LINE, "the line: [[x, y], ...] symbol centres, left to right"),
                     lines=(None, "several lines: [[[x, y], ...], ...] (overrides points)"),
                     speed=(1100.0, "head speed along the line, units/s"), ease=(0.14, "seconds to reach full speed"),
                     stagger=(0.45, "seconds between lines"), tail=(0.14, "tail length as a time lag (s)"),
                     linger=(0.9, "seconds the glow line takes to fade after the head passes"),
                     thickness=(26.0, "line / tail thickness"), size=(56.0, "head size"), sparks=(6, "sparks shed per symbol"),
                     colors=(None, "[hex, ...] colour per line (cycled); default color"))),
    "win_highlight": dict(
        fn=win_highlight, duration=2.4, kind="window", color="FFD25A",
        summary="Per-symbol win highlight: a 9-slice frame and soft glow snap on with a shine burst (1/t bloom, ray star, Sedov "
                "halo, corner twinkles) at the hit time, the cell pops on a spring with exact overshoot, a specular sheen band "
                "sweeps across it (generated flipbook pre-masked to the cell: no clipping). symbols= pops your symbol bones "
                "through carriers. Events fx_win_highlight, fx_win_highlight_hit (int = cell index).",
        anchor="Grid origin; each cell is [dx, dy, w, h, time] from it.",
        options=dict(width=(150.0, "cell width"), height=(150.0, "cell height"), hit=(0.0, "seconds when the (first) cell lights"),
                     cells=(None, "[[dx, dy(, w, h(, time))], ...]: several cells; time defaults to hit + i * stagger"),
                     stagger=(0.0, "seconds between cells when they carry no time"), color2=("FFF2B0", "burst colour"),
                     pop=(0.12, "cell pop: first spring overshoot (0.12 = 12% bigger)"), bounce=(6.0, "pop spring Hz"),
                     damping=(0.4, "pop damping ratio, 0..1"), burst=(1.0, "burst size multiplier"),
                     sheen_period=(1.1, "seconds between sheen sweeps"), sheen_time=(0.45, "seconds one sweep takes"),
                     symbols=(None, "[bone, ...] your symbol bones, one per cell: a carrier above each pops with the cell"))),
    "multiplier_stack": dict(
        fn=multiplier_stack, duration=1.8, kind="window", color="FFD25A", count=0,
        summary="Multiplier badges fly into the total one after another on ballistic arcs (exact parabolas) with comet tails, "
                "shrink and are absorbed; the total pops on a spring with exact overshoot (kicks superpose, each harder as the "
                "stack builds), a Sedov ring and 1/t flash per hit, a shine burst on the last. badge_bones (result) carry the "
                "game's badge art; total= pops your total bone through a carrier. Events fx_multiplier_launch / fx_multiplier_hit "
                "(int = source index), fx_multiplier_total.",
        anchor="Origin of sources and target.",
        options=dict(sources=([[-260.0, -120.0], [0.0, -170.0], [260.0, -120.0]], "[[x, y], ...] where each badge starts"),
                     target=([0.0, 170.0], "[x, y] of the total"), stagger=(0.22, "seconds between launches"),
                     flight=(0.55, "flight time (s)"), arc=(90.0, "how high each arc bows"), tail=(0.4, "tail as a fraction of the flight time"),
                     size=(46.0, "head size"), sparks=(5, "sparks shed per flight"), color2=("FFF2B0", "flash / shine colour"),
                     pop=(0.22, "total pop overshoot on the first hit"), growth=(0.3, "each later hit kicks this much harder (x per hit)"),
                     bounce=(5.0, "pop spring Hz"), damping=(0.35, "pop damping ratio, 0..1"),
                     total=("", "your total bone: a carrier above it pops (empty: the result's total_bone is ours)"))),
    "win_rollup": dict(
        fn=win_rollup, duration=3.2, kind="window", color="FFC83A", count=14, normal_blend=True,
        summary="Win counter roll-up: coins fall INTO the counter (reverse projectile: from rest, constant acceleration, a spiral; "
                "Poisson launches), the counter pops on every digit tick and with a big exact-overshoot pop when the count lands, "
                "its glow, streak, ray star and the floor glow under it intensify as the count climbs and with the tier, a shine "
                "burst at the end. counter= pops your counter bone through a carrier (else parent your text under counter_bone). "
                "Events fx_win_rollup, fx_rollup_tick (int = tick index, every 1/rate s), fx_rollup_end. Has tiers.",
        anchor="Counter centre (width x height).",
        options=dict(width=(360.0, "counter width"), height=(110.0, "counter height"), rate=(12.0, "digit ticks per second"),
                     settle=(0.9, "seconds after the count lands (end pop + burst)"), glow=(0.7, "glow level (tiers raise it)"),
                     coins=(None, "coins flying in (default count)"), coin_size=(34.0, "coin size"),
                     spread=(300.0, "how far out the coins start"), color2=("FFC83A", "coin colour"),
                     tick_pop=(0.035, "pop per digit tick"), end_pop=(0.25, "pop when the count lands (exact overshoot)"),
                     bounce=(6.0, "end-pop spring Hz (ticks ring at 2x)"), damping=(0.35, "damping ratio, 0..1"),
                     counter=("", "your counter bone: a carrier above it pops (empty: the result's counter_bone is ours)"))),
})
RECIPES["payline"]["tiers"] = {
    "small": dict(sparks=3, size=46.0, thickness=20.0), "big": dict(sparks=8, size=64.0, thickness=30.0),
    "mega": dict(sparks=10, size=72.0, thickness=34.0, linger=1.1), "epic": dict(sparks=12, size=80.0, thickness=38.0, linger=1.3)}
RECIPES["win_highlight"]["tiers"] = {
    "small": dict(burst=0.8, pop=0.08), "big": dict(burst=1.15, pop=0.14),
    "mega": dict(burst=1.3, pop=0.16, sheen_period=0.9), "epic": dict(burst=1.5, pop=0.18, sheen_period=0.8)}
RECIPES["multiplier_stack"]["tiers"] = {
    "small": dict(pop=0.16, growth=0.2), "big": dict(pop=0.26, size=50.0),
    "mega": dict(pop=0.3, size=54.0, sparks=7), "epic": dict(pop=0.34, size=58.0, sparks=9, growth=0.4)}
RECIPES["win_rollup"]["tiers"] = {
    "small": dict(glow=0.45, coins=6, end_pop=0.15, tick_pop=0.025, rate=10.0, spread=240.0),
    "big": dict(glow=0.9, coins=22, end_pop=0.3, tick_pop=0.04, rate=14.0, spread=330.0),
    "mega": dict(glow=1.1, coins=32, end_pop=0.36, tick_pop=0.045, rate=16.0, spread=360.0),
    "epic": dict(glow=1.3, coins=44, end_pop=0.42, tick_pop=0.05, rate=18.0, spread=400.0)}
ROLES.update({
    "payline": {"line": "the glow line left behind: horizontal strip, ends soft (stretched along each hop)",
                "tail": "the comet tail strip, head at the TOP (bent along the line)", "glow": "light around the head",
                "spark": "the head star", "hit": "the flash on each symbol", "ring": "the ring on each symbol", "mote": "one spark"},
    "win_highlight": {"frame": "9-slice frame art (give slice and px)", "under": "9-slice soft glow around the frame (give slice and px)",
                      "rays": "the burst ray star, centred", "glow": "the burst core", "ring": "the burst halo",
                      "spark": "one corner twinkle"},
    "multiplier_stack": {"tail": "the comet tail strip, head at the TOP", "glow": "light around each badge", "spark": "the head star",
                         "mote": "one shed spark", "aura": "the glow behind the total", "flash": "the flash per hit",
                         "ring": "the ring per hit", "rays": "the final ray star", "flare": "the final streak"},
    "win_rollup": {"coin": "one coin, face on, centred (normal blend; spun by its x scale)", "floor": "the glow on the floor",
                   "pool": "the hot spot on the floor", "glow": "9-slice glow hugging the counter (give slice and px)",
                   "flare": "the streak behind the digits", "rays": "the ray star behind the counter", "burst": "the end burst core",
                   "ring": "the end halo rings", "spark": "one end twinkle"},
})
for _n, _d in ROLES.items():
    if _n in RECIPES:
        RECIPES[_n]["roles"] = _d
