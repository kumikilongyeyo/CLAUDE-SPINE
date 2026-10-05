"""Payout moments for ``fx_recipe``: ``coin_fountain`` and ``cascade_pop``, the FX that pay a win out.

Same rules as fx_recipes.py (procedural textures, one group bone per recipe, closed-form keys, ``art=`` roles, normal
blend first in the run). ``cascade_pop`` also MOVES the game's own symbol bones, the fx_reels way: a pure-translation
carrier bone is inserted above each dropping symbol (``fx_reels._carrier``) and keyed with ``_merge_keys``, so the
artist's keys, constraints and weights are never touched.

Exaggerated real physics:

* ``coin_fountain``: every coin is a real projectile with linear air drag, closed form in physics time s:
  x = vx/k (1 - e^-ks), y = (vy + g/k)/k (1 - e^-ks) - g s/k (shower coins tend to the terminal speed g/k). The launch
  speed is solved so the apex is exactly the coin's chosen height, the horizontal speed so the first landing is exactly
  its chosen spot (under linear drag the two axes are independent). HANG TIME is exaggerated by a time warp around the
  apex (where vy = 0): real time t = s + hang * integral of e^-((s - s_apex)/w)^2 ds, so the clock runs 1/(1 + hang) as
  fast at the top and normally again well before the landing (the warp has no effect on where the coin goes, only on
  when). Landings are restitution bounces: each hop leaves at e times the speed it came in with, so the hop heights fall
  by e^2 every time, and each impact takes a Coulomb friction impulse off the sideways speed (|dvx| <= mu (1+e) |vy|).
  Then the coin slaps flat, slides to a stop at constant deceleration mu g and rattles down like Euler's disk: the
  rocking angle dies as (1 - t/T)^(1/3) while its frequency RISES as (1 - t/T)^(-1/6), and it is exactly still at T.
  While airborne it tumbles: the coin flipbook (fx.py's ``fx/coin_`` frames, a flip about its own axis) plays on a
  bone that turns in-plane with a spin that decays to zero exactly when the coin lands flat (whole turns, so it rests
  level). Launch times are a Poisson process (sorted uniform times given the count). Coins on a deeper part of the
  counter land higher up the screen, are a touch smaller and are drawn behind; soft contact shadows tighten as a coin
  comes down.
* ``cascade_pop``: the winning symbols swell, crack (Voronoi crack lines) and shatter into Voronoi shards, one image per
  shard (the ``ice_shatter`` method, cut from the symbol's own picture), that fly out from the centre with air drag and
  fall under gravity, spinning down as drag eats their spin; a dust ``puff`` and a ``hit_burst`` on every cell. The
  symbols above fall freely (y = -g t^2 / 2) into the gap and land with exact restitution hops (the first hop is e^2 of
  the drop height, the next e^4...) while an underdamped spring squashes them onto the symbol below (area-preserving,
  pivoting on their base), ending exactly at rest.

Registered into fx_recipes.RECIPES / ROLES at import (fx_recipes imports this module at its end).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from . import fx_recipes as _fr
from .fx import _rgba, ensure_coin
from .fx_recipes import (Ctx, RECIPES, ROLES, _blur, _colorize, _hexn, _mix, _rgb, _uniq, ease_out, hexa, smooth,
                         times_dense)
from .fx_reels import _carrier, _merge_keys, _spring
from .ir import Sequence

COIN_FRAMES = 8           # fx.py's coin flipbook: 8 frames = half a turn about the coin's own axis


# ------------------------------------------------------------------ textures
def tex_shadow(w: int = 128, h: int = 40) -> Image.Image:
    """A soft contact shadow: a dark ellipse, densest in the middle (white; tint it black in the slot)."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = (y - (h - 1) / 2) / ((h - 1) / 2)
    d = np.hypot(xn, yn)
    a = np.exp(-(d / 0.55) ** 2) * np.clip((1 - d) / 0.15, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def tex_symbol(color: str = "E8364F", n: int = 256) -> Image.Image:
    """A procedural slot symbol to shatter when no art is given: a faceted gem on a gold-rimmed tile. Drawn at 2x."""
    S = 2
    N = n * S
    im = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    c = N / 2
    base = _rgb(color)
    dark = tuple(int(v) for v in _mix(base, (20, 0, 20), 0.55))
    lite = tuple(int(v) for v in _mix(base, (255, 255, 255), 0.45))
    m = int(N * 0.04)
    d.rounded_rectangle([m, m, N - m, N - m], int(N * 0.16), fill=(70, 30, 60, 255), outline=(255, 205, 80, 255), width=int(N * 0.035))
    R = N * 0.34
    pts = [(c + R * math.cos(math.radians(a)), c - R * math.sin(math.radians(a))) for a in range(90, 450, 45)]
    d.polygon(pts, fill=base + (255,), outline=dark + (255,))
    inner = [(c + 0.55 * (px - c), c + 0.55 * (py - c)) for px, py in pts]
    d.polygon(inner, fill=lite + (255,))
    for (px, py), (qx, qy) in zip(pts, inner):           # the facet lines
        d.line([(px, py), (qx, qy)], fill=dark + (255,), width=int(N * 0.008))
    d.polygon(pts, outline=dark + (255,), width=int(N * 0.014))
    hx, hy = c - R * 0.32, c - R * 0.4
    d.ellipse([hx - R * 0.14, hy - R * 0.09, hx + R * 0.14, hy + R * 0.09], fill=(255, 255, 255, 230))
    return im.resize((n, n), Image.LANCZOS)


def voronoi_shards(img: Image.Image, count: int = 9, seed: int = 5):
    """Cut a picture into Voronoi shards, the ice_shatter way (fx_elements.ice_block), but for any RGBA image.
    Returns (crack-lines image, [(shard image, cx, cy) in pixels from the picture centre, y up])."""
    rng = np.random.default_rng(seed)
    arr = np.asarray(img.convert("RGBA")).copy()
    h, w = arr.shape[:2]
    alpha = arr[..., 3].astype(np.float32) / 255
    inside = alpha > 0.04
    y, x = np.mgrid[0:h, 0:w].astype(float)
    ys_in, xs_in = np.nonzero(inside)
    if len(xs_in) < 30:
        raise ValueError("the symbol picture is empty (no opaque pixels to shatter)")
    x0, x1, y0, y1 = xs_in.min(), xs_in.max(), ys_in.min(), ys_in.max()
    pts = np.column_stack([rng.uniform(x0, x1, count), rng.uniform(y0, y1, count)])
    pts[0] = ((x0 + x1) / 2, (y0 + y1) / 2)
    dist = np.stack([np.hypot(x - px, y - py) for px, py in pts])
    lab = np.argmin(dist, 0)
    srt = np.sort(dist, 0)
    edge_px = 0.012 * max(w, h)
    crack = np.clip(1 - (srt[1] - srt[0]) / edge_px, 0, 1) * alpha if count > 1 else np.zeros((h, w))
    crack_img = _colorize(np.clip(crack + _blur(crack, 1.6) * 0.6, 0, 1), (255, 255, 255), (255, 246, 220), (255, 214, 140))
    pieces = []
    for k in range(count):
        m = (lab == k) & inside
        if m.sum() < 30:
            continue
        ys, xs = np.nonzero(m)
        a0, a1, b0, b1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        piece = arr[a0:a1, b0:b1].copy()
        mm = m[a0:a1, b0:b1]
        piece[..., 3] = (piece[..., 3] * mm).astype(np.uint8)
        e = _blur(mm.astype(np.float32), 1.0)                      # a bright cut edge on every shard
        cut = np.clip((1 - np.abs(e - 0.5) * 2) * mm, 0, 1)
        piece[..., :3] = np.clip(piece[..., :3] + cut[..., None] * 70, 0, 255).astype(np.uint8)
        pieces.append((Image.fromarray(piece, "RGBA"), float((b0 + b1) / 2 - w / 2), float(h / 2 - (a0 + a1) / 2)))
    return crack_img, pieces


# ------------------------------------------------------------------ physics helpers (closed form)
def drag_y(s: float, vy: float, g: float, k: float) -> float:
    """Height after time s for a projectile with linear drag k (vy up, gravity g)."""
    if k < 1e-6:
        return vy * s - 0.5 * g * s * s
    return (vy + g / k) / k * (1 - math.exp(-k * s)) - g * s / k


def drag_vy(s: float, vy: float, g: float, k: float) -> float:
    if k < 1e-6:
        return vy - g * s
    return (vy + g / k) * math.exp(-k * s) - g / k


def drag_x(s: float, vx: float, k: float) -> float:
    if k < 1e-6:
        return vx * s
    return vx / k * (1 - math.exp(-k * s))


def apex_time(vy: float, g: float, k: float) -> float:
    """Where vy = 0: s = ln(1 + k vy / g) / k."""
    if vy <= 0:
        return 0.0
    return vy / g if k < 1e-6 else math.log(1 + k * vy / g) / k


def launch_speed(height: float, g: float, k: float) -> float:
    """The upward speed whose drag-slowed apex is exactly ``height`` (bisection: the apex grows with vy)."""
    lo, hi = 0.0, math.sqrt(2 * g * height) * 2 + 10
    while drag_y(apex_time(hi, g, k), hi, g, k) < height:
        hi *= 2
    for _ in range(80):
        mid = (lo + hi) / 2
        if drag_y(apex_time(mid, g, k), mid, g, k) < height:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def hit_time(y0: float, vy: float, floor: float, g: float, k: float) -> float:
    """First s > apex with y0 + y(s) = floor (the coin is coming down)."""
    sa = apex_time(vy, g, k)
    if y0 + drag_y(sa, vy, g, k) <= floor:
        raise ValueError("the coin never rises above the floor; put the floor below the spout (floor < 0)")
    lo, hi = sa, sa + 0.5
    while y0 + drag_y(hi, vy, g, k) > floor:
        hi += 0.5
    for _ in range(80):
        mid = (lo + hi) / 2
        if y0 + drag_y(mid, vy, g, k) > floor:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def hang_warp(sa: float, w: float, hang: float):
    """Real time as a function of physics time: t(s) = s + hang * int_0^s e^-((u - sa)/w)^2 du. dt/ds = 1 + hang at
    the apex, so the coin hangs there; far from it the clock runs at 1 (the warp only changes WHEN, not where)."""
    if hang <= 0 or w <= 0:
        return lambda s: s
    c = hang * w * math.sqrt(math.pi) / 2
    e0 = math.erf(sa / w)
    return lambda s: s + c * (math.erf((s - sa) / w) + e0)


def euler_wobble(T: float, hz: float, amp: float) -> list[tuple[float, float]]:
    """Euler's-disk rattle as (time, angle) at every quarter cycle: angle = amp (1-q)^(1/3) sin(phi) with
    phi = 2 pi hz T (6/5) (1 - (1-q)^(5/6)), q = t/T, i.e. the frequency rises as (1-q)^(-1/6) while it dies; exactly 0 at T."""
    if T <= 0 or amp == 0:
        return [(0.0, 0.0)]
    w0 = 2 * math.pi * hz
    pmax = w0 * T * 1.2
    out = []
    j = 0
    while j * math.pi / 2 < pmax:
        ph = j * math.pi / 2
        q = 1 - (1 - ph / pmax) ** 1.2
        out.append((T * q, amp * (1 - q) ** (1 / 3) * math.sin(ph)))
        j += 1
    out.append((T, 0.0))
    return [(t, round(a, 4) if abs(a) > 1e-9 else 0.0) for t, a in out]


# ------------------------------------------------------------------ coin_fountain
def _coin_path(mode: str, rng, P: dict, g: float, k: float, e: float, mu: float, H: float, W: float, floor: float,
               depth: float, hang: float, settle: float) -> dict:
    """One coin, from launch (local time 0) to rest. Returns its samples and phase times."""
    dz = float(rng.uniform(-depth / 2, depth / 2)) if depth > 0 else 0.0
    yf = floor + dz
    if mode == "fountain":
        x0, y0 = float(rng.uniform(-6, 6)), 0.0
        apex = H * float(rng.uniform(0.55, 1.0))
        vy = launch_speed(apex, g, k)
        sa = apex_time(vy, g, k)
        sh = hit_time(y0, vy, yf, g, k)
        target = W / 2 * float(rng.uniform(-1, 1))
        vx = target * (k / (1 - math.exp(-k * sh)) if k >= 1e-6 else 1 / sh)
        warp = hang_warp(sa, 0.32 * sa, hang)
    else:                                                  # shower: in from above, no apex, heading for terminal speed
        x0, y0 = W / 2 * float(rng.uniform(-1, 1)), H * float(rng.uniform(1.0, 1.25))
        vy, vx = -float(rng.uniform(0, 260)), float(rng.uniform(-70, 70))
        sa = 0.0
        sh = hit_time(y0, vy, yf, g, k) if y0 + 0 > yf else 0.0
        warp = lambda s: s  # noqa: E731
    ss = sorted(set(np.linspace(0, sh, max(3, int(math.ceil(sh * 70)) + 1)).tolist()) | ({sa} if 0 < sa < sh else set()))
    T, X, Y = [], [], []
    for s in ss:
        T.append(warp(s))
        X.append(x0 + drag_x(s, vx, k))
        Y.append(y0 + drag_y(s, vy, g, k))
    Y[-1] = yf
    t_hit, x_hit = T[-1], X[-1]
    t_apex = warp(sa) if mode == "fountain" else None
    vxh = vx * math.exp(-k * sh) if k >= 1e-6 else vx
    vyh = abs(drag_vy(sh, vy, g, k))
    # restitution hops: out at e x the speed in; a Coulomb friction impulse off the sideways speed at every impact
    hops, t, x, vin, vxc = [], t_hit, x_hit, vyh, vxh
    for _ in range(int(P["bounces"])):
        vxc = math.copysign(max(0.0, abs(vxc) - mu * (1 + e) * vin), vxc)
        vout = e * vin
        if vout * vout / (2 * g) < 1.5:
            break
        dur = 2 * vout / g
        n = max(3, int(math.ceil(dur * 70)) + 1)
        for q in np.linspace(0, dur, n)[1:]:
            T.append(t + q)
            X.append(x + vxc * q)
            Y.append(yf + vout * q - 0.5 * g * q * q)
        Y[-1] = yf
        hops.append(dict(t=t, v=vout, h=vout * vout / (2 * g)))
        t, x, vin = t + dur, x + vxc * dur, vout
    vxc = math.copysign(max(0.0, abs(vxc) - mu * (1 + e) * vin), vxc) if hops else vxc
    # the slap flat, then the slide: constant deceleration mu g (at least fast enough to stop in 0.5 s)
    t_flat = t
    v = abs(vxc)
    a = max(mu * g, v / 0.5, 1e-6)
    t_sl = v / a
    if t_sl > 0:
        for q in np.linspace(0, t_sl, max(3, int(math.ceil(t_sl * 40)) + 1))[1:]:
            T.append(t_flat + q)
            X.append(x + math.copysign(v * q - 0.5 * a * q * q, vxc))
            Y.append(yf)
    x_rest = x + math.copysign(v * t_sl - 0.5 * a * t_sl * t_sl, vxc) if t_sl > 0 else x
    return dict(T=T, X=X, Y=Y, yf=yf, dz=dz, t_hit=t_hit, x_hit=x_hit, t_apex=t_apex, hops=hops, t_flat=t_flat,
                t_slide=t_sl, x_rest=x_rest, length=t_flat + max(t_sl, settle), vy0=vy, vx0=vx, slide_a=a)


def coin_fountain(c: Ctx, P: dict) -> dict:
    """Coins gush up and out of a spout (or rain from above), hang at the top, tumble, bounce on the counter, slide,
    rattle flat and lie there; contact shadows, a glint on the first landings, a glow at the spout."""
    D = float(P["duration"])
    mode = str(P["mode"])
    if mode not in ("fountain", "shower"):
        raise ValueError(f"mode must be fountain | shower, got {mode!r}")
    n = int(P["count"])
    if n < 1:
        raise ValueError("count must be >= 1")
    if n > 80:
        raise ValueError(f"count={n}: heavy coin counts belong to the game's particle emitter (start it on the "
                         "fx_coin_fountain event, with the numbers in the result's engine_hint); keep Spine coins <= 80")
    e, mu, k = float(P["restitution"]), float(P["friction"]), float(P["drag"])
    if not 0 <= e < 1:
        raise ValueError("restitution must be in [0, 1): each hop leaves at restitution x the speed it came in with")
    if mu < 0 or k < 0 or float(P["hang"]) < 0:
        raise ValueError("friction, drag and hang must be >= 0")
    g, H, W = float(P["gravity"]), float(P["height"]), float(P["width"])
    floor, depth, size = float(P["floor"]), float(P["depth"]), float(P["size"])
    if g <= 0 or H <= 0 or size <= 0:
        raise ValueError("gravity, height and size must be > 0")
    if mode == "fountain" and floor >= 0:
        raise ValueError("floor is the counter top relative to the spout: it must be below it (floor < 0)")
    settle, fade = float(P["settle"]), float(P["fade"])
    col = _hexn(P["color"], "FFE58A")
    rng = np.random.default_rng(c.seed + 307)
    coins = [_coin_path(mode, rng, P, g, k, e, mu, H, W, floor, depth, float(P["hang"]), settle) for _ in range(n)]
    Lmax = max(cn["length"] for cn in coins)
    spread = min(float(P["spread"]), D - fade - Lmax)
    if spread < 0:
        raise ValueError(f"duration {D:g}s is too short: the slowest coin needs {Lmax + fade:.2f}s to land, settle and "
                         f"fade; raise duration or lower height")
    t0s = np.sort(rng.uniform(0, spread, n)) if n > 1 else np.array([0.0])      # Poisson launches, given the count
    for cn, t0 in zip(coins, t0s):
        cn["t0"] = float(t0)
        cn["size"] = size * float(rng.uniform(0.85, 1.12)) * (1 - 0.3 * cn["dz"] / depth if depth > 0 else 1.0)
        cn["fps"] = float(rng.uniform(18, 30))
        cn["frame"] = int(rng.integers(0, COIN_FRAMES))
        w_turns = float(rng.uniform(1.6, 3.2)) * (1 if rng.random() < 0.5 else -1)           # turns per second, in-plane
        cn["turns"] = (max(1, round(abs(w_turns) * cn["t_flat"] / 2)) * (1 if w_turns > 0 else -1)) if cn["t_flat"] > 0 else 0
        cn["wob"] = float(rng.uniform(6, 11)) * (1 if rng.random() < 0.5 else -1)
    grp = c.bone("coins", c.group, 0, 0)

    # normal-blend layers first (shadows, then the coins back to front), then the additive ones
    shadows = []
    if P["shadows"]:
        for i, cn in enumerate(coins):
            bn = c.bone(f"sh{i}", grp)
            sl = c.slot(bn, "fx/payouts_shadow", cn["size"] * 1.15, color="000000FF", blend="normal",
                        make=lambda: tex_shadow(), role="shadow")
            shadows.append((bn, sl, cn))
    order = sorted(range(n), key=lambda i: -coins[i]["dz"])
    ensure_coin(c.p, COIN_FRAMES)
    for i in order:
        cn = coins[i]
        bn = c.bone(f"c{i}", grp)
        sl = c.slot(bn, "fx/coin_00", cn["size"], blend="normal", role="coin")
        att = c.sk.skin("default").attachments[sl]["fx"]
        cn["seq"] = "coin" not in c.art_used
        if cn["seq"]:
            att.path = "fx/coin_"
            att.sequence = Sequence(count=COIN_FRAMES, start=0, digits=2)
        cn["b"], cn["s"] = bn, sl
    # the gush: a glow and a ring at the spout (fountain only)
    s_glow = s_ring = None
    if mode == "fountain":
        b_glow, b_ring = c.bone("glow", grp), c.bone("ring", grp)
        s_glow = c.slot(b_glow, "fx/glow", size * 4.0, role="glow")
        s_ring = c.slot(b_ring, "fx/ring", size * 3.2, role="ring")
    # glints at the first landings, thinned to `landings` evenly through time
    by_hit = sorted(range(n), key=lambda i: coins[i]["t0"] + coins[i]["t_hit"])
    m = min(int(P["landings"]), n)
    pick = sorted({by_hit[int(round(j))] for j in np.linspace(0, n - 1, m)}) if m > 0 else []
    glints = []
    for i in pick:
        cn = coins[i]
        bn = c.bone(f"gl{i}", grp, cn["x_hit"], cn["yf"] + cn["size"] * 0.15)
        glints.append((bn, c.slot(bn, "fx/spark", cn["size"] * 1.5, color=hexa(col, 1.0), role="spark"), cn))

    # keys
    for cn in coins:
        t0, bn, sl = cn["t0"], cn["b"], cn["s"]
        Tm = [t0 + t for t in cn["T"]]
        c.ab.bone(bn, "translate", _uniq([(c.T(t), x, y) for t, x, y in zip(Tm, cn["X"], cn["Y"])]), "linear")
        tf = t0 + cn["t_flat"]
        Theta = 360.0 * cn["turns"]
        rot = []
        for t in Tm:
            if t <= tf + 1e-9:
                q = (t - t0) / max(cn["t_flat"], 1e-9)
                rot.append((c.T(t), Theta * (2 * q - q * q)))         # spin decays to 0 exactly as it lands flat
        rot += [(c.T(tf + t), Theta + a) for t, a in euler_wobble(settle, float(P["rattle"]), cn["wob"])]
        c.ab.bone(bn, "rotate", _uniq(rot), "linear")
        flat = float(P["flat"])
        if cn["seq"]:
            pop = [(c.T(t0), 0.55, 0.55), (c.T(t0 + 0.07), 1.0, 1.0)] if mode == "fountain" else [(c.T(t0), 1.0, 1.0)]
        else:                                     # one picture: the flip about its own axis is a scaleX turn, |cos|
            rate = math.pi * cn["fps"] / COIN_FRAMES
            pf = (lambda t: 0.55 + 0.45 * min(1.0, (t - t0) / 0.07)) if mode == "fountain" else (lambda t: 1.0)
            pop = [(c.T(t), pf(t) * max(0.08, abs(math.cos(rate * (t - t0) + cn["frame"] * math.pi / COIN_FRAMES))), pf(t))
                   for t in times_dense(t0, tf, 90)][:-1]
        c.ab.bone(bn, "scale", _uniq(pop + [(c.T(tf), 1.0, 1.0), (c.T(tf + 0.04), 1.12, flat * 0.8),
                                           (c.T(tf + 0.12), 1.0, flat)]), "linear")
        if cn["seq"]:
            c.ab.sequence(sl, "fx", [(c.T(t0), "loop", cn["frame"], 1.0 / cn["fps"]), (c.T(tf), "hold", 0, 0)])
        c.show([sl], t0, D)
        c.color_keys(sl, [t0, D - fade, D], lambda u: hexa("FFFFFF", c.a(1 - smooth(u, D - fade, D))))
    for bn, sl, cn in shadows:
        t0, yf = cn["t0"], cn["yf"]
        pts_t, pts_s, pts_c = [], [], []
        for t, x, y in zip(cn["T"], cn["X"], cn["Y"]):
            hgt = max(0.0, y - yf)
            pts_t.append((c.T(t0 + t), x, yf))
            sc = 0.45 + 0.55 * math.exp(-hgt / 260)
            pts_s.append((c.T(t0 + t), sc, sc))
            pts_c.append((c.T(t0 + t), hexa("000000", c.a(0.5 * math.exp(-hgt / 220)))))
        if pts_c[-1][0] < c.T(D - fade):
            pts_c.append((c.T(D - fade), pts_c[-1][1]))
        pts_c.append((c.T(D), "00000000"))
        c.ab.bone(bn, "translate", _uniq(pts_t), "linear")
        c.ab.bone(bn, "scale", _uniq(pts_s), "linear")
        c.ab.slot_color(sl, _uniq(pts_c), "linear")
        c.show([sl], t0, D)
    if s_glow:
        gush = spread + 0.12
        ts = times_dense(0, gush + 0.3, 30)
        c.show([s_glow, s_ring], 0, gush + 0.3)
        c.color_keys(s_glow, ts, lambda u: hexa(col, c.a(0.75 * smooth(u, 0, 0.04) * (1 - smooth(u, gush, gush + 0.3))
                                                       * (0.8 + 0.2 * math.cos(2 * math.pi * 9 * u)))))
        c.bone_keys(c.sk.slot(s_glow).bone, "scale", ts, lambda u: (0.6 + 0.5 * ease_out(u / 0.2, 2.5), 0.45 + 0.4 * ease_out(u / 0.2, 2.5)))
        tr = times_dense(0, 0.5, 40)
        sedov = lambda u: (max(0.0, u) / 0.5) ** 0.4  # noqa: E731
        c.bone_keys(c.sk.slot(s_ring).bone, "scale", tr, lambda u: (0.15 + 1.1 * sedov(u), 0.5 * (0.15 + 1.1 * sedov(u))))
        c.color_keys(s_ring, tr, lambda u: hexa(col, c.a(0.8 * (1 - sedov(u)) ** 1.5 * smooth(u, 0, 0.02))))
    land_times = []
    for bn, sl, cn in glints:
        th = cn["t0"] + cn["t_hit"]
        land_times.append(c.T(th))
        c.ab.event(c.T(th), "fx_coin_land")
        c.ab.slot_attachment(sl, [(0.0, None), (c.T(th), "fx"), (c.T(th + 0.3), None)])
        c.ab.bone(bn, "scale", _uniq([(c.T(th), 0, 0), (c.T(th + 0.07), 1, 1), (c.T(th + 0.3), 0, 0)]), "linear")
        c.ab.bone(bn, "rotate", _uniq([(c.T(th), 0), (c.T(th + 0.3), 60)]), "linear")
    hint = dict(note="heavy counts (100+ coins) belong to the game's particle emitter: start it on fx_coin_fountain "
                     "with these numbers; keep the Spine coins for the hero coins in front",
                mode=mode, gravity=round(g * c.S, 2), drag=k, restitution=e, friction=mu, rate=round(n / max(spread, 0.05), 2),
                height=round(H * c.S, 2), floor=round(floor * c.S, 2), width=round(W * c.S, 2))
    return c.result(duration=D, coins=n, shadows=len(shadows), spread=round(spread, 4), landings=sorted(land_times),
                    rest=[round(cn["t0"] + cn["length"], 4) for cn in coins], engine_hint=hint)


# ------------------------------------------------------------------ cascade_pop
def _normal_first(sk, names: list[str]) -> list[str]:
    """Reorder one contiguous run of new slots so every normal-blend slot comes first (stable within each class):
    one normal batch, then one additive batch."""
    idx = sorted(sk.slot_index(nm) for nm in names)
    if idx and idx[-1] - idx[0] + 1 != len(idx):
        return [sk.slots[i].name for i in idx]               # not contiguous (should not happen): leave it alone
    block = [sk.slots[i] for i in idx]
    new = [s for s in block if s.blend == "normal"] + [s for s in block if s.blend != "normal"]
    sk.slots[idx[0]:idx[-1] + 1] = new if idx else []
    return [s.name for s in new]


def _cells(P: dict) -> list[tuple[float, float, float, float]]:
    cells = P["cells"]
    if cells is None:
        cells = [[0, 0, P["width"], P["height"]]]
    if not isinstance(cells, (list, tuple)) or not cells:
        raise ValueError("cells must be a non-empty list of [dx, dy, w, h]")
    out = []
    for cl in cells:
        if not isinstance(cl, (list, tuple)) or len(cl) != 4:
            raise ValueError(f"each cell is [dx, dy, w, h], got {cl!r}")
        dx, dy, w, h = (float(v) for v in cl)
        if w <= 0 or h <= 0:
            raise ValueError(f"cell {cl!r}: width and height must be > 0")
        out.append((dx, dy, w, h))
    return out


def _drops(P: dict, cells) -> list[tuple[str, float, float]]:
    out = []
    for d in P["drop"] or []:
        if not isinstance(d, (list, tuple)) or len(d) not in (2, 3):
            raise ValueError(f"each drop entry is [bone, distance] or [bone, distance, height], got {d!r}")
        bone, dist = str(d[0]), float(d[1])
        if dist <= 0:
            raise ValueError(f"drop {d!r}: the distance to fall must be > 0")
        out.append((bone, dist, float(d[2]) if len(d) == 3 else cells[0][3]))
    return out


def cascade_pop(c: Ctx, P: dict) -> dict:
    """Winning symbols swell, crack and shatter into shards that fly out and fall; a dust puff and a hit burst on each
    cell; the symbols above drop into the gap and land with an exact damped bounce (through carrier bones)."""
    D = 1.3
    cells = _cells(P)
    drops = _drops(P, cells)
    col = _hexn(P["color"], "FFD45A")
    sym_c = _hexn(P["color2"], "E8364F")
    g, kd, burst = float(P["gravity"]), float(P["drag"]), float(P["burst"])
    e, sq = float(P["restitution"]), float(P["squash"])
    if not 0 <= e < 1:
        raise ValueError("restitution must be in [0, 1)")
    if g <= 0 or kd < 0:
        raise ValueError("gravity must be > 0 and drag >= 0")
    n_sh = int(P["count"])
    if not 1 <= n_sh <= 40:
        raise ValueError("count (shards per symbol) must be 1..40")
    pop, stag = float(P["pop"]), float(P["stagger"])
    if pop < 0 or stag < 0:
        raise ValueError("pop and stagger must be >= 0")
    for bone, _, _ in drops:                          # fail before building anything
        if not c.sk.has_bone(bone):
            raise ValueError(f"no bone {bone!r} to drop")
    rng = np.random.default_rng(c.seed + 331)
    grp = c.bone("pop", c.group, 0, 0)
    gb = c.sk.bone(c.group)
    S = c.S
    art = c._art("symbol")
    made: list[str] = []
    breaks, lives = [], []
    cut: dict[str, tuple] = {}
    for ci, (dx, dy, w, h) in enumerate(cells):
        tb = pop + ci * stag
        breaks.append(tb)
        b_cell = c.bone(f"cell{ci}", grp, dx, dy)
        b_sym = c.bone(f"sym{ci}", b_cell)
        aspect = art["size"][0] / art["size"][1] if art else 1.0
        width = float(P["inset"]) * min(w, h * aspect)
        s_sym = c.slot(b_sym, "fx/payouts_symbol_" + sym_c, width, blend="normal", make=lambda: tex_symbol(sym_c), role="symbol")
        made.append(s_sym)
        att = c.sk.skin("default").attachments[s_sym]["fx"]
        width, hsym = float(att.width), float(att.height)
        src = art["tex"] if art else "fx/payouts_symbol_" + sym_c
        tag = f"{src.replace('/', '_')}_{n_sh}_{c.seed}"
        if tag not in cut:                        # cut the picture once (at <= 384 px), shared by every cell
            im = c.p.image(src)
            if max(im.size) > 384:
                f = 384 / max(im.size)
                im = im.resize((max(8, round(im.size[0] * f)), max(8, round(im.size[1] * f))), Image.LANCZOS)
            crack_img, pieces = voronoi_shards(im, n_sh, c.seed + 5)
            c.p.write_image(f"fx/payouts_crack_{tag}", crack_img)
            for i, (pim, _, _) in enumerate(pieces):
                c.p.write_image(f"fx/payouts_shard_{tag}_{i}", pim)
            cut[tag] = (im.size, pieces)
        isz, pieces = cut[tag]
        kpx = width / isz[0]
        # the dust puff behind the shards (puff, normal blend; its flash/ring go to the additive batch below)
        if P["puff"]:
            pr = _fr.apply(c.p, "puff", x=gb.x + dx * S, y=gb.y + dy * S, scale=S,
                           start=c.T(tb), duration=RECIPES["puff"]["duration"] * c.k, color=_hexn(P["dust"], "D8C4A6"),
                           intensity=c.I * float(P["dust_alpha"]), seed=c.seed + 17 * ci, into=c.anim,
                           parent=gb.parent or "root", front_of=c.last_slot, count=int(P["lobes"]), name=f"{c.prefix}_puff",
                           options=dict(size=0.4 * min(w, h), radius=0.5 * min(w, h), rise=26.0, blend="normal"))
            made += pr["slots"]
            c.last_slot = pr["slots"][-1]
            lives.append(tb + RECIPES["puff"]["duration"])
        # shards: one slot per Voronoi piece (normal blend), on their own bones at their place in the picture
        b_sh = c.bone(f"shards{ci}", b_cell)
        shards = []
        for i, (pim, cx, cy) in enumerate(pieces):
            bn = c.bone(f"s{ci}_{i}", b_sh, cx * kpx, cy * kpx)
            sl = c.slot(bn, f"fx/payouts_shard_{tag}_{i}", pim.size[0] * kpx, blend="normal")
            made.append(sl)
            r_ = math.hypot(cx, cy) * kpx / max(width / 2, 1e-6)
            ang = math.atan2(cy, cx) if r_ > 0.02 else float(rng.uniform(0, 2 * math.pi))
            ang += float(rng.uniform(-0.35, 0.35))
            sp = burst * (0.55 + 0.75 * min(1.0, r_)) * float(rng.uniform(0.8, 1.2)) * (min(w, h) / 150)
            shards.append(dict(b=bn, s=sl, vx=math.cos(ang) * sp, vy=math.sin(ang) * sp + burst * float(rng.uniform(0.25, 0.6)) * (min(w, h) / 150),
                               w=float(rng.uniform(-720, 720)), life=float(rng.uniform(0.5, 0.7))))
        # crack lines over the symbol before it breaks (additive), the hit burst on top
        b_crk = c.bone(f"crack{ci}", b_sym)
        s_crk = c.slot(b_crk, f"fx/payouts_crack_{tag}", width, height=hsym, role="crack")
        made.append(s_crk)
        if P["hit"]:
            hr = _fr.apply(c.p, "hit_burst", x=gb.x + dx * S, y=gb.y + dy * S, scale=S, start=c.T(tb),
                           duration=RECIPES["hit_burst"]["duration"] * c.k, color=col, intensity=c.I * float(P["flash"]), seed=c.seed + 23 * ci,
                           into=c.anim, parent=gb.parent or "root", front_of=c.last_slot, count=int(P["sparks"]),
                           name=f"{c.prefix}_hit", options=dict(size=0.8 * min(w, h)))
            made += hr["slots"]
            c.last_slot = hr["slots"][-1]
            lives.append(tb + RECIPES["hit_burst"]["duration"])

        # keys: swell + win wiggle, crack, break
        ts = times_dense(0, tb, 60) if tb > 0 else [0.0]
        c.show([s_sym], 0, tb)
        if tb > 0:
            c.bone_keys(b_sym, "scale", ts, lambda u, tb=tb: (1 + 0.12 * math.sin(math.pi * min(1.0, u / tb)) ** 0.7,) * 2)
            c.bone_keys(b_sym, "rotate", ts, lambda u, tb=tb: 4.0 * math.sin(2 * math.pi * 14 * u) * smooth(u, 0, 0.6 * tb) * (1 - smooth(u, 0.85 * tb, tb)))
            t_cr = 0.45 * tb
            c.show([s_crk], t_cr, tb)
            tcs = times_dense(t_cr, tb, 60)
            c.color_keys(s_crk, tcs, lambda u, t_cr=t_cr, tb=tb: hexa("FFFFFF", c.a(smooth(u, t_cr, tb) * (0.8 + 0.2 * math.sin(u * 70)))))
        else:
            c.ab.slot_attachment(s_crk, [(0.0, None)])
        for s_ in shards:
            L = s_["life"]
            tt = times_dense(tb, tb + L, 60)
            q = lambda u, tb=tb: max(0.0, u - tb)  # noqa: E731
            c.show([s_["s"]], tb, tb + L)
            c.bone_keys(s_["b"], "translate", tt, lambda u, s_=s_, q=q: (drag_x(q(u), s_["vx"], kd), drag_y(q(u), s_["vy"], g, kd)))
            c.bone_keys(s_["b"], "rotate", tt, lambda u, s_=s_, q=q: drag_x(q(u), s_["w"], kd))      # spin dies with drag too
            c.bone_keys(s_["b"], "scale", tt, lambda u, q=q, L=L: (1 - 0.35 * q(u) / L,) * 2)
            c.color_keys(s_["s"], tt, lambda u, tb=tb, L=L: hexa("FFFFFF", c.a(1 - smooth(u, tb + 0.55 * L, tb + L))))
            lives.append(tb + L)
        c.ab.event(c.T(tb), "fx_cascade_shatter")

    # the symbols above fall into the gap: free fall, exact restitution hops, a squash spring on every impact
    t_drop0 = (breaks[-1] if breaks else 0.0) + float(P["delay"])
    lands, carriers = [], []
    spring = _spring(1.0, float(P["bounce_hz"]), 0.4)
    for di, (bone, dist, hgt) in enumerate(drops):
        ts0 = t_drop0 + di * float(P["drop_stagger"])
        w = c.sk.world()
        car = _carrier(c, bone, "drop", (w[bone].x, w[bone].y - hgt * S / 2))
        carriers.append(car)
        d = dist * S
        gg = g * S
        tf = math.sqrt(2 * d / gg)
        vin = gg * tf
        impacts = [(tf, vin)]                     # (time from drop start, speed in)
        hops = []
        t, v = tf, vin
        for _ in range(3):
            vo = e * v
            if vo * vo / (2 * gg) < 0.6:
                break
            hops.append((t, vo))
            t += 2 * vo / gg
            impacts.append((t, vo))
            v = vo
        t_end = t + 0.32

        def ypos(u, ts0=ts0, d=d, tf=tf, gg=gg, hops=hops):
            s = u - ts0
            if s <= 0:
                return 0.0
            if s <= tf:
                return -0.5 * gg * s * s
            for (th, vo) in hops:
                if th <= s <= th + 2 * vo / gg:
                    q = s - th
                    return -d + vo * q - 0.5 * gg * q * q
            return -d

        def sy(u, ts0=ts0, impacts=impacts, vin=vin, t_end=t_end):
            s = u - ts0
            v_ = 1.0
            for ti, vi in impacts:
                if s > ti:
                    v_ += sq * (vi / vin) * spring(s - ti)
            return 1 + (v_ - 1) * (1 - smooth(s, t_end - 0.12, t_end))
        crit = sorted({ts0 + ti for ti, _ in impacts} | {ts0 + th + vo / gg for th, vo in hops})
        tt = sorted(set(times_dense(ts0, ts0 + t_end, 120)) | set(crit))
        _merge_keys(c, car, "translate", tt, lambda u, ypos=ypos: (0.0, ypos(u)), "add")
        _merge_keys(c, car, "scale", tt, lambda u, sy=sy: (1 / max(0.3, sy(u)), max(0.3, sy(u))), "mul")
        lands.append(c.T(ts0 + tf))
        c.ab.event(c.T(ts0 + tf), "fx_cascade_land")
        lives.append(ts0 + t_end)

    names = _normal_first(c.sk, made)
    end = max([D] + lives)
    return c.result(duration=round(end * c.k, 4), slots=names, cells=len(cells), shards=n_sh, breaks=[c.T(t) for t in breaks],
                    lands=lands, carriers=carriers, end=c.T(end))


# ------------------------------------------------------------------ registry
RECIPES.update({
    "coin_fountain": dict(
        fn=coin_fountain, duration=3.8, kind="window", color="FFE58A", count=22, normal_blend=True,
        summary="Coins with exaggerated real physics: drag-slowed parabolas (apex and landing spot solved exactly), extra HANG "
                "TIME at the apex (a time warp around vy=0), tumbling (fx coin flipbook + decaying spin), restitution bounces "
                "on the counter (hop heights x e^2), a friction slide and an Euler's-disk rattle to rest; contact shadows, glints "
                "on the first landings. Modes fountain (up and out of a spout) | shower (from above). Events fx_coin_fountain "
                "and fx_coin_land (thinned to `landings`). Heavy counts belong to the engine emitter (result engine_hint).",
        anchor="The spout (fountain) or the middle of the drop zone (shower); the counter top is `floor` below it.",
        options=dict(mode=("fountain", "fountain | shower"), height=(330.0, "apex of the highest coin above the spout (shower: "
                                                                            "where the coins enter)"),
                     width=(560.0, "how wide the coins land (fountain) or fall (shower)"),
                     floor=(-60.0, "the counter top, relative to the anchor (negative = below)"),
                     depth=(50.0, "depth of the counter: coins land up to depth/2 above or below floor, farther ones smaller"),
                     size=(44.0, "coin diameter"), gravity=(2000.0, "gravity (units/s^2)"),
                     drag=(1.2, "linear air drag k (1/s): velocity decays e^-kt, terminal speed gravity/k"),
                     hang=(1.0, "extra hang time at the apex: the clock runs 1/(1+hang) as fast at vy=0 (0 = real)"),
                     restitution=(0.38, "bounce: each hop leaves at this x the speed it came in with (0..1)"),
                     friction=(0.12, "Coulomb friction mu: impact impulse and the slide's deceleration mu*gravity"),
                     bounces=(3, "max hops before it slaps flat"), flat=(0.38, "how flat a lying coin looks (scaleY)"),
                     settle=(0.45, "seconds of the Euler's-disk rattle once flat"), rattle=(5.0, "rattle frequency at the start (Hz)"),
                     spread=(0.7, "seconds over which coins launch (clipped so every coin rests before the fade)"),
                     fade=(0.35, "seconds to fade the resting coins at the end"), landings=(8, "max fx_coin_land events/glints"),
                     shadows=(True, "contact shadows on the counter (normal blend)")),
        tiers={"small": dict(count=10, height=240.0, duration=3.2, spread=0.4, width=420.0),
               "big": dict(count=32, height=400.0, duration=4.2, spread=0.8, width=620.0),
               "mega": dict(count=44, height=470.0, duration=4.6, spread=1.0, width=660.0),
               "epic": dict(count=60, height=540.0, duration=5.2, spread=1.3, width=700.0)}),
    "cascade_pop": dict(
        fn=cascade_pop, duration=1.3, kind="one-shot", color="FFD45A", count=7, normal_blend=True,
        summary="Cascade win: each winning symbol swells, cracks and shatters into Voronoi shards cut from its own picture (art= "
                "symbol) that fly out with drag and fall under gravity, a dust puff and a hit burst per cell; the symbols above "
                "(drop=[[bone, distance], ...]) fall into the gap through carrier bones and land with exact restitution hops "
                "(e^2 of the drop) and a squash spring. Events fx_cascade_pop, fx_cascade_shatter (per cell), fx_cascade_land "
                "(per dropping symbol).",
        anchor="Origin of the cell offsets (each entry of cells is [dx, dy, w, h] from it).",
        options=dict(cells=(None, "[[dx, dy, w, h], ...] the cells to pop (default: one width x height cell at the anchor)"),
                     width=(150.0, "cell width (default cell)"), height=(150.0, "cell height (default cell)"),
                     drop=([], "[[bone, distance] or [bone, distance, height], ...] game bones (at the symbol centre) that fall "
                               "`distance` into the gap; a carrier is inserted above each, pivoting on the symbol base"),
                     pop=(0.14, "seconds of swell + crack before the first cell breaks"),
                     stagger=(0.05, "seconds between cells breaking (in list order)"),
                     delay=(0.12, "seconds after the last break before the symbols above fall"),
                     drop_stagger=(0.035, "seconds between dropping symbols (in list order)"),
                     gravity=(2600.0, "gravity for the shards and the falling symbols"), drag=(2.2, "air drag on the shards (1/s)"),
                     burst=(360.0, "shard launch speed for a 150 cell"), restitution=(0.3, "landing hop: e (first hop = e^2 x drop)"),
                     squash=(0.16, "squash on landing (0.16 = 16% shorter, area preserving)"), bounce_hz=(6.5, "squash spring Hz"),
                     inset=(0.9, "symbol size inside the cell"), color2=("E8364F", "procedural gem colour (no art)"),
                     dust=("D8C4A6", "dust puff colour"), dust_alpha=(0.6, "dust puff opacity (its intensity)"),
                     flash=(0.4, "hit burst intensity (additive over light symbols saturates fast)"), puff=(True, "dust puff per cell (puff recipe)"),
                     hit=(True, "hit burst per cell (hit_burst recipe)"), lobes=(3, "puff cloud lobes per cell"),
                     sparks=(4, "hit_burst sparks per cell"))),
})
ROLES.update({
    "coin_fountain": {"coin": "one coin, face on, centred (replaces the flipbook; the flip is then a scaleX turn)",
                      "shadow": "the contact shadow (normal blend), wide ellipse", "spark": "the landing glint",
                      "glow": "the glow at the spout", "ring": "the ring at the spout"},
    "cascade_pop": {"symbol": "the symbol picture that shatters (normal blend; its shards are cut from it)",
                    "crack": "the crack lines over the symbol (generated from the shards if not given)"},
})
for _n, _d in ROLES.items():
    if _n in RECIPES:
        RECIPES[_n]["roles"] = _d
