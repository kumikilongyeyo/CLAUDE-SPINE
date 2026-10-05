"""Screen-level atmosphere for ``fx_recipe``: weather, god_rays, water_surface, heat_shimmer, fog_roll, lightning_storm.

Same rules as fx_recipes.py (procedural textures, one group bone per recipe, dense linear keys of closed-form functions
of time, loops that close exactly, ``art=`` roles, ``ae_hint`` for the After Effects half). These are SCREEN layers:
``x, y`` is the centre of the area they fill (``width`` x ``height``, default about the 720-unit canvas), except
``god_rays`` (x, y = the light source) and ``heat_shimmer`` (x, y = the top of the fire).

Exaggerated real physics:

* ``weather`` (rain | snow | embers | petals): every particle moves at its kind's TERMINAL velocity (rain 1300 u/s, snow
  80, petals 70); embers RISE at 75 after being spat out at 3.4x that and slowed by drag, v = vt + (v0 - vt) e^(-t/tau).
  Sideways a particle obeys linear (Stokes) drag toward the wind, dv/dt = (w(t) - v) / tau, the wind being a mean plus a
  slow gust sine. Solved exactly, the drift follows the gust attenuated by 1/sqrt(1 + (w tau)^2) and late by
  atan(w tau) / w: a raindrop (tau 0.85 s) smooths and lags the gust, a snowflake (tau 0.1 s) rides every one. The gust is
  a wave travelling with the wind (it reaches the upwind side of the screen first). Depth layers sit at distance
  1..``depth``: apparent speed, drift and size go as 1/distance (parallax), far layers are paler (aerial perspective) and
  more numerous (more volume far away). Rain streaks are the drop's path during a short exposure, turned along the
  velocity; petals swing like a falling leaf (sway, with the tilt in phase with the swing) and flip (scaleX through 0 =
  edge-on); embers flicker (~7 Hz), cool yellow -> orange -> red and shrink. Every particle lives D/m seconds (m an
  integer) and respawns somewhere new at alpha 0 (keys at every respawn), so the loop closes exactly.
* ``god_rays``: light through gaps scattered by haze. Each column narrows to the source and widens with distance
  (divergent light), its brightness falls off along the ray (extinction, e^(-s/l)); an occluder (clouds, leaves) drifting
  across the source dims the rays IN SEQUENCE (a travelling pattern, not independent flicker); the whole fan sweeps slowly;
  dust motes glint only while they cross a beam. The volumetric version is the AE template ``god_rays`` (ae_hint).
* ``water_surface``: every symbol that lands sends capillary rings out, radius ~ sqrt(t) (as water_splash), whose
  brightness falls as 1/sqrt(r) (the ring's energy spreads along a longer circumference) and fades as they damp out, plus a
  1/t glint at the impact. ``fx_water_land`` fires on every landing. The caustic light under the surface is the existing AE
  template ``caustics`` behind the reels (ae_hint).
* ``heat_shimmer``: Spine cannot refract, so the real thing is After Effects (template ``heat_shimmer``: a rising
  refractive-index field used as a displacement map, or rendered as a schlieren image, brightness ~ the index gradient).
  The recipe places the anchor bone at the top of the fire and adds a faint stand-in: wide soft strands bent by a wave
  that rises with the plume (phase speed = ``rise``) and grows with height (the plume turns turbulent as it mixes).
* ``fog_roll`` (fog | sand): a bank flowing sideways. Puffs advect with a wind that grows with height (shear: the top of
  the bank runs faster) and roll forward as they go (the shear's vorticity), the bank is densest at the ground and thins
  upward, a far layer moves slower (parallax). Sand adds grains in SALTATION: hopping along the ground on parabolas,
  streaked along their velocity. The volumetric bank is the AE template ``fog_roll`` (horizontal convection, loopified).
* ``lightning_storm``: strikes arrive as a Poisson process with dead time (interval = ``min_gap`` + Exp, mean 1/``rate``,
  seeded), at random x across the top, each at a random distance. Each strike is a few return strokes; its cloud glow and
  the sky glow flash with an instant attack and a 1/t decay, the channel cools e^(-t/50 ms); brightness ~ 1/distance
  (exaggerated from 1/d^2). ``fx_thunder`` fires distance / ``sound_speed`` later (sound exaggerated to ~6x its real speed
  so the rumble follows in game time), carrying the distance (float), a volume (1/d) and the stereo balance (x). The bolt
  is the AE ``lightning`` template (ae_hint, one entry per strike with x and start); a Spine fallback bolt (a jagged
  procedural strand) makes it work without AE.

Registered into fx_recipes.RECIPES / ROLES at import (the lead adds the import to fx_recipes.py).
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .fx import _rgba
from .fx_recipes import (Ctx, RECIPES, ROLES, _blur, _grid, _hexn, _mix, _rgb, _uniq, ease_out, hexa, smooth, smooth_arr,
                         times_dense)


# ------------------------------------------------------------------ textures (white; tinted by the slot)
def tex_rain(w: int = 16, h: int = 160) -> Image.Image:
    """A rain streak: the drop's path during the exposure. Bright head at the BOTTOM (the leading end), long fading tail."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    v = y / (h - 1)
    a = np.exp(-(xn / 0.38) ** 2) * (0.25 + 0.75 * v ** 1.6) * smooth_arr(v, 0.0, 0.3) * smooth_arr(1 - v, 0.0, 0.05)
    a *= np.clip((1 - np.abs(xn)) / 0.15, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def tex_petal(n: int = 96) -> Image.Image:
    """A cherry petal: an egg shape, wide near its notched tip (top), narrowing to the base; lighter toward the tip, a
    faint crease down the middle. Supersampled for a clean edge. Near white: the slot tints it."""
    S = 3
    N = n * S
    x, y = _grid(N)
    up = -y
    half = 0.62 * np.sqrt(np.clip(1 - (up * 0.96) ** 2, 0, 1)) * (0.62 + 0.38 * (up + 1) / 2)
    inside = (np.abs(x) <= half).astype(np.float32)
    notch = ((x / 0.17) ** 2 + ((up - 0.97) / 0.2) ** 2) < 1
    inside[notch] = 0
    shade = 0.8 + 0.2 * np.clip((up + 1) / 2, 0, 1)
    shade *= 1 - 0.09 * np.exp(-(x / 0.04) ** 2) * (up > -0.7)
    a = np.asarray(Image.fromarray((inside * 255).astype(np.uint8), "L").resize((n, n), Image.LANCZOS), np.float32) / 255
    s = np.asarray(Image.fromarray((np.clip(shade, 0, 1) * 255).astype(np.uint8), "L").resize((n, n), Image.LANCZOS),
                   np.float32) / 255
    rgb = np.dstack([s, s * 0.97, s * 0.98])
    return _rgba(rgb, np.clip(a, 0, 1))


def tex_godray(w: int = 128, h: int = 512) -> Image.Image:
    """One light shaft, SOURCE at the BOTTOM edge: narrow there and widening with distance (divergent light), fading
    along its length (extinction by the haze), faint lengthwise streaks."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    s = 1 - y / (h - 1)                                   # distance from the source, 0..1
    width = 0.14 + 0.42 * s
    a = np.exp(-(xn / width) ** 2) * np.exp(-s / 0.55) * smooth_arr(s, 0.0, 0.04) * (1 - smooth_arr(s, 0.8, 1.0))
    a *= 0.86 + 0.14 * np.cos(xn / np.maximum(width, 1e-3) * 4.0 + 0.6) ** 2
    a *= np.clip((1 - np.abs(xn)) / 0.12, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a * 1.1, 0, 1))


def tex_haze(w: int = 32, h: int = 256) -> Image.Image:
    """One faint wavering filament for the shimmer stand-in (bent as a strand mesh): soft core, tapered ends. A schlieren
    view of hot air is thin bright filaments, not a band."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    v = y / (h - 1)
    a = (np.exp(-(xn / 0.18) ** 2) + 0.3 * np.exp(-(xn / 0.5) ** 2)) * smooth_arr(v, 0.0, 0.35) * smooth_arr(1 - v, 0.0, 0.2)
    a *= np.clip((1 - np.abs(xn)) / 0.15, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def tex_grit(w: int = 64, h: int = 12) -> Image.Image:
    """A sand grain smeared along its motion: a short horizontal streak, solid core."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = (y - (h - 1) / 2) / ((h - 1) / 2)
    a = np.exp(-(yn / 0.45) ** 2) * np.exp(-(xn / 0.62) ** 4)
    a *= np.clip((1 - np.abs(xn)) / 0.1, 0, 1) * np.clip((1 - np.abs(yn)) / 0.2, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a * 1.2, 0, 1))


def _bolt_path(rng, p0, p1, rough: float, depth: int) -> list[tuple[float, float]]:
    """Midpoint displacement: each segment's middle is pushed sideways by ~rough x its length (a fractal channel)."""
    pts = [p0, p1]
    for _ in range(depth):
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy) or 1.0
            off = float(rng.normal(0, rough * L))
            out += [((a[0] + b[0]) / 2 - dy / L * off, (a[1] + b[1]) / 2 + dx / L * off), b]
        pts = out
    return pts


def tex_bolt(seed: int = 0, w: int = 128, h: int = 512) -> Image.Image:
    """A forked lightning channel from the cloud (TOP centre) down: jagged main channel, thinner side branches that die
    out, a hot core and an air-glow halo."""
    S = 2
    W, H = w * S, h * S
    rng = np.random.default_rng(1000 + seed)
    img = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(img)
    end = (W / 2 + float(rng.uniform(-0.28, 0.28)) * W, H * 0.97)
    main = _bolt_path(rng, (W / 2, H * 0.01), end, 0.16, 6)
    d.line(main, fill=255, width=int(4.5 * S), joint="curve")
    for _ in range(int(rng.integers(3, 6))):
        i = int(rng.integers(len(main) // 8, len(main) * 3 // 4))
        x0, y0 = main[i]
        ang = math.pi / 2 + float(rng.choice([-1, 1])) * float(rng.uniform(0.35, 0.85))
        ln = H * float(rng.uniform(0.12, 0.32))
        b_end = (min(W * 0.96, max(W * 0.04, x0 + math.cos(ang) * ln * 0.6)), min(H * 0.98, y0 + math.sin(ang) * ln))
        br = _bolt_path(rng, (x0, y0), b_end, 0.18, 4)
        for k, (a, b) in enumerate(zip(br, br[1:])):              # branches taper as they die out
            d.line([a, b], fill=int(255 * (1 - 0.6 * k / len(br))), width=max(1, int(2.6 * S * (1 - 0.5 * k / len(br)))))
    base = np.asarray(img, np.float32) / 255
    a = np.clip(_blur(base, 0.8 * S) * 1.3 + _blur(base, 5 * S) * 0.75 + _blur(base, 14 * S) * 0.35, 0, 1)
    a = np.asarray(Image.fromarray((a * 255).astype(np.uint8), "L").resize((w, h), Image.LANCZOS), np.float32) / 255
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    a *= np.clip(np.minimum(xx, w - 1 - xx) / 6, 0, 1) * np.clip((h - 1 - yy) / 6, 0, 1)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


TEX = {"fx/ambient_rain": tex_rain, "fx/ambient_petal": tex_petal, "fx/ambient_godray": tex_godray,
       "fx/ambient_haze": tex_haze, "fx/ambient_grit": tex_grit}


def _tex(name: str):
    return TEX[name]


# ------------------------------------------------------------------ shared helpers
def _check_pos(P: dict, *names: str) -> None:
    for n in names:
        if float(P[n]) <= 0:
            raise ValueError(f"{n} must be > 0")


def _cycles(P: dict, name: str) -> int:
    v = P[name]
    if int(v) != v or int(v) < 1:
        raise ValueError(f"{name} must be a whole number >= 1 (the loop closes only on whole cycles)")
    return int(v)


def _life_times(D: float, m: int, ph: float, rate: float, fade: float) -> list[float]:
    """Key times for a particle living D/m seconds with phase ph: dense samples plus, at every respawn w, the pair
    (w - 2 ms, w) so the jump happens at alpha 0, and the ends of the fade-in / fade-out."""
    T = D / m
    ts = set(times_dense(0, D, rate))
    for n in range(0, m + 2):
        w = (n - ph) * T
        for t in (w, w + fade * T, w + T - fade * T):
            if 0 <= t <= D:
                ts.add(t)
        if 0 < w < D:
            ts.add(w - 0.002)
    return sorted(ts)


def _life(u: float, D: float, m: int, ph: float) -> tuple[int, float, float]:
    """(life index mod m, q in [0, 1), spawn time) at time u. The epsilon puts a respawn instant in the NEW life."""
    T = D / m
    z = u / T + ph
    k = math.floor(z + 1e-7)
    q = min(max(z - k, 0.0), 1.0 - 1e-9)
    return k % m, q, (k - ph) * T


# ------------------------------------------------------------------ weather
KINDS: dict[str, dict] = {
    # vt: terminal speed (u/s); dirn: -1 falls, +1 rises; tau: drag time constant (s); v0: launch speed / vt;
    # life: nominal life (s); size: near-layer size range (rain: streak length); fade: fraction of the life fading in/out
    "rain": dict(vt=1300.0, dirn=-1, tau=0.85, v0=1.0, wind=150.0, gust=110.0, life=0.42, count=110, color="C4DAFF",
                 size=(56.0, 92.0), alpha=0.62, fade=0.1, rate=8, sway=(0.0, 0.0), sway_hz=(0.0, 0.0), spin=0.0,
                 blend="additive", palette=None),
    "snow": dict(vt=80.0, dirn=-1, tau=0.1, v0=1.0, wind=35.0, gust=45.0, life=4.0, count=70, color="FFFFFF",
                 size=(9.0, 24.0), alpha=0.9, fade=0.15, rate=8, sway=(5.0, 16.0), sway_hz=(0.3, 0.8), spin=60.0,
                 blend="additive", palette=None),
    "embers": dict(vt=75.0, dirn=1, tau=0.55, v0=3.4, wind=25.0, gust=40.0, life=2.2, count=40, color="FF9A30",
                   size=(18.0, 38.0), alpha=1.0, fade=0.05, rate=16, sway=(10.0, 28.0), sway_hz=(0.4, 1.1), spin=0.0,
                   blend="additive", palette=None),
    "petals": dict(vt=70.0, dirn=-1, tau=0.35, v0=1.0, wind=70.0, gust=70.0, life=4.5, count=30, color="",
                   size=(26.0, 44.0), alpha=1.0, fade=0.12, rate=14, sway=(18.0, 40.0), sway_hz=(0.35, 0.7), spin=90.0,
                   blend="normal", palette=["FFC2D6", "FFB0C8", "FFD9E6", "FFF0F4"]),
}


def _gust(G: float, tau: float, omega: float) -> tuple[float, float]:
    """Steady response of v' = (w - v)/tau to w = G sin(omega t): amplitude G/sqrt(1 + (omega tau)^2), phase lag atan(omega tau)."""
    return G / math.sqrt(1 + (omega * tau) ** 2), math.atan(omega * tau)


def weather(c: Ctx, P: dict) -> dict:
    """Rain, snow, embers or petals across the screen in parallax depth layers; loops exactly every `duration`."""
    kind = str(P["kind"])
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {sorted(KINDS)}, got {kind!r}")
    K = KINDS[kind]
    D = float(P["duration"])
    _check_pos(P, "width", "height", "size")
    Wd, Hd = float(P["width"]), float(P["height"])
    nl = int(P["layers"])
    if nl < 1:
        raise ValueError("layers must be >= 1")
    depth = float(P["depth"])
    if depth < 1:
        raise ValueError("depth must be >= 1 (the far layer's distance relative to the near one)")
    ng = _cycles(P, "gust_cycles")
    W0 = float(K["wind"] if P["wind"] is None else P["wind"])
    G = float(K["gust"] if P["gust"] is None else P["gust"])
    n = int(P["count"] or K["count"])
    blend = str(P["blend"] or K["blend"])
    if blend not in ("additive", "normal"):
        raise ValueError("blend must be additive | normal")
    alpha_k = float(K["alpha"] if P["alpha"] is None else P["alpha"])
    palette = [_hexn(x, "FFFFFF") for x in ([P["color"]] if P["color"] else (P["palette"] or K["palette"] or [K["color"]]))]
    tau, vt, dirn, v0m, fade = K["tau"], K["vt"], K["dirn"], K["v0"], K["fade"]
    omega = 2 * math.pi * ng / D
    gA, lag = _gust(G, tau, omega)
    rng = np.random.default_rng(c.seed + 301)
    grp = c.bone("weather", c.group, 0, 0)
    dists = [1.0 + (depth - 1.0) * (i / max(1, nl - 1)) for i in range(nl)][::-1]    # far first (drawn behind)
    wts = np.array([d ** 1.5 for d in dists])
    counts = np.floor(n * wts / wts.sum()).astype(int)
    counts[np.argmax(wts)] += n - counts.sum()
    tex, role, rate = {"rain": ("fx/ambient_rain", "streak", 8), "snow": ("fx/mote", "flake", 8),
                       "embers": ("fx/mote", "ember", 16), "petals": ("fx/ambient_petal", "petal", 14)}[kind]
    layers, parts = [], []
    for li, (dist, cnt) in enumerate(zip(dists, counts)):
        f = 1.0 / dist                                            # parallax: apparent speed and size ~ 1/distance
        lb = c.bone(f"layer{li}", grp)
        layers.append(dict(bone=lb, distance=round(dist, 3), factor=round(f, 4), count=int(cnt)))
        for i in range(int(cnt)):
            bn = c.bone(f"l{li}p{i}", lb)
            sz = float(rng.uniform(*K["size"])) * float(P["size"]) * f
            col = str(rng.choice(palette))
            if kind == "rain":
                sl = c.slot(bn, tex, sz * 0.14, height=sz, make=_tex(tex), blend=blend, role=role)
            else:
                sl = c.slot(bn, tex, sz, make=_tex(tex) if tex in TEX else None, blend=blend, role=role)
            j = float(rng.uniform(0.85, 1.15))
            life = K["life"] * float(rng.uniform(0.8, 1.25)) / (f ** 0.5 if kind == "rain" else 1.0)
            m = max(1, int(round(D / life)))
            vte = vt * j
            T = D / m
            travel = vte * T + (v0m - 1) * vte * tau * (1 - math.exp(-T / tau))
            spawn = []
            for _ in range(m):
                x0 = float(rng.uniform(-Wd / 2, Wd / 2)) - f * W0 * T / 2
                if kind == "embers":
                    y0 = -Hd / 2 + float(rng.uniform(0.0, 0.35)) * Hd
                else:
                    y0 = float(rng.uniform(-Hd / 2, Hd / 2)) + f * travel / 2
                spawn.append(dict(x=x0, y=y0, ph=float(rng.uniform(0, 2 * math.pi)), ph2=float(rng.uniform(0, 2 * math.pi)),
                                  sw=float(rng.uniform(*K["sway"])), swf=2 * math.pi * float(rng.uniform(*K["sway_hz"]) if K["sway_hz"][1] else 0.0),
                                  flip=2 * math.pi * float(rng.uniform(0.5, 1.3)), spin=float(rng.uniform(-1, 1)) * K["spin"],
                                  tilt=float(rng.uniform(25, 45))))
            parts.append(dict(b=bn, s=sl, f=f, m=m, ph=float(rng.uniform(0.02, 0.98)), vte=vte, col=col, spawn=spawn,
                              la=0.45 + 0.55 * f))
    c.show([p["s"] for p in parts], 0, None)
    trav = -1.0 if W0 < 0 else 1.0

    def state(u: float, p: dict):
        li, q, usp = _life(u, D, p["m"], p["ph"])
        sp = p["spawn"][li]
        T = D / p["m"]
        s = q * T
        f, vte = p["f"], p["vte"]
        gph = -2 * math.pi * sp["x"] / (2 * Wd) * trav if W0 else 0.0     # the gust reaches the upwind side first
        th = lambda t: omega * t + gph - lag  # noqa: E731
        x = sp["x"] + f * (W0 * s + gA / omega * (math.cos(th(usp)) - math.cos(th(u))))
        vx = f * (W0 + gA * math.sin(th(u)))
        y = sp["y"] + dirn * f * (vte * s + (v0m - 1) * vte * tau * (1 - math.exp(-s / tau)))
        vy = dirn * f * vte * (1 + (v0m - 1) * math.exp(-s / tau))
        if sp["swf"]:
            x += sp["sw"] * f * math.sin(sp["swf"] * s + sp["ph"])
            vx += sp["sw"] * f * sp["swf"] * math.cos(sp["swf"] * s + sp["ph"])
        env = smooth(q, 0, fade) * (1 - smooth(q, 1 - fade, 1))
        rot, sc, col = 0.0, (1.0, 1.0), p["col"]
        a = alpha_k * p["la"] * env
        if kind == "rain":
            rot = math.degrees(math.atan2(-vy, -vx)) - 90.0          # the streak's tail points back along the velocity
        elif kind == "snow":
            rot = sp["spin"] * s
        elif kind == "petals":
            rot = sp["tilt"] * math.cos(sp["swf"] * s + sp["ph"]) + sp["spin"] * s     # tilts with its swing
            fx_ = math.cos(sp["flip"] * s + sp["ph2"])
            sc = (math.copysign(max(0.1, abs(fx_)), fx_), 1.0)           # flips over: edge-on as scaleX crosses 0
        else:                                                           # embers: flicker, cool, shrink
            fl = 0.72 + 0.28 * math.sin(2 * math.pi * 7.0 * s + sp["ph"]) * math.sin(2 * math.pi * 2.3 * s + sp["ph2"])
            a = alpha_k * p["la"] * smooth(q, 0, fade) * (1 - q) ** 0.8 * fl
            hot, mid, red = (255, 240, 176), _rgb(_hexn(col, "FF9A30")), (176, 32, 8)
            rgb = _mix(hot, mid, min(1.0, q / 0.35)) if q < 0.35 else _mix(mid, red, min(1.0, (q - 0.35) / 0.55))
            col = "%02X%02X%02X" % tuple(int(v) for v in rgb)
            k_ = 1.0 - 0.5 * q
            sc = (k_, k_)
        return x, y, rot, sc, hexa(col, c.a(min(1.0, a)))

    for p in parts:
        ts = _life_times(D, p["m"], p["ph"], rate, fade)
        vals = [state(u, p) for u in ts]
        c.ab.bone(p["b"], "translate", _uniq([(c.T(u), v[0], v[1]) for u, v in zip(ts, vals)]), "linear")
        if kind != "embers":
            c.ab.bone(p["b"], "rotate", _uniq([(c.T(u), v[2]) for u, v in zip(ts, vals)]), "linear")
        if kind in ("petals", "embers"):
            c.ab.bone(p["b"], "scale", _uniq([(c.T(u), *v[3]) for u, v in zip(ts, vals)]), "linear")
        c.ab.slot_color(p["s"], _uniq([(c.T(u), v[4]) for u, v in zip(ts, vals)]), "linear")
    return c.result(duration=D * c.k, loop=D, kind=kind, particles=len(parts), layers=layers, terminal_velocity=vt,
                    tau=tau, wind=W0, gust=G, gust_gain=round(gA / G, 4) if G else 1.0, gust_lag=round(lag / omega, 4))


# ------------------------------------------------------------------ god_rays
def god_rays(c: Ctx, P: dict) -> dict:
    """A fan of light shafts from a source, sweeping slowly, dimmed in sequence by a drifting occluder; dust glints in them."""
    D = float(P["duration"])
    col = _hexn(P["color"], "FFE6A8")
    nr = int(P["rays"])
    if nr < 1:
        raise ValueError("rays must be >= 1")
    _check_pos(P, "length", "width")
    L, Wr = float(P["length"]), float(P["width"])
    ang, spread, sweep, flick = float(P["angle"]), float(P["spread"]), float(P["sweep"]), float(P["flicker"])
    if not 0 <= flick <= 1:
        raise ValueError("flicker must be in 0..1")
    rng = np.random.default_rng(c.seed + 311)
    grp = c.bone("rays", c.group, 0, 0)
    fan = c.bone("fan", grp)
    glow = None
    if P["source_glow"]:
        bg = c.bone("source", grp)
        glow = (bg, c.slot(bg, "fx/glow", L * 0.42, role="glow"))
    rays = []
    for i in range(nr):
        fr = i / (nr - 1) if nr > 1 else 0.5
        a_i = ang + spread * (fr - 0.5) + float(rng.uniform(-0.18, 0.18)) * spread / max(1, nr)
        rb = c.bone(f"ray{i}", fan, rot=a_i - 90.0)                      # the shaft runs along the bone's +y
        beam = c.bone(f"beam{i}", rb)
        w_i = Wr * float(rng.uniform(0.55, 1.45))
        l_i = L * float(rng.uniform(0.78, 1.08))
        sl = c.slot(beam, "fx/ambient_godray", w_i, oy=l_i / 2, height=l_i, make=tex_godray, role="ray", stretch=True)
        rays.append(dict(b=rb, beam=beam, s=sl, w=w_i, l=l_i, fr=fr, a=float(rng.uniform(0.32, 0.6)),
                         br=int(rng.integers(1, 4)), brph=float(rng.uniform(0, 6.28))))
    motes = []
    for i in range(int(P["count"])):
        r_ = rays[int(rng.integers(0, nr))]
        bn = c.bone(f"dust{i}", r_["b"], 0, r_["l"] * float(rng.uniform(0.12, 0.8)))
        sl = c.slot(bn, "fx/mote", float(rng.uniform(6, 14)), role="mote")
        motes.append(dict(b=bn, s=sl, ray=r_, cyc=int(rng.choice([1, 1, 2])), ph=float(rng.uniform(0, 6.28)),
                          dy=float(rng.uniform(8, 30)), tw=int(rng.integers(3, 9)), twph=float(rng.uniform(0, 6.28))))
    c.show([x for x in c.slots], 0, None)
    ph1, ph2 = float(rng.uniform(0, 6.28)), float(rng.uniform(0, 6.28))

    def occ(fr: float, u: float) -> float:
        """The occluder drifting across the source: a pattern travelling across the fan, once (and twice) per loop."""
        return 0.6 * (0.5 + 0.5 * math.sin(2 * math.pi * (1.3 * fr - u / D) + ph1)) + \
            0.4 * (0.5 + 0.5 * math.sin(2 * math.pi * (2.7 * fr - 2 * u / D) + ph2))
    light = lambda r_, u: 1.0 - flick * occ(r_["fr"], u)  # noqa: E731
    ts = times_dense(0, D, 12)
    c.bone_keys(fan, "rotate", ts, lambda u: sweep * math.sin(2 * math.pi * u / D))
    for r_ in rays:
        c.color_keys(r_["s"], ts, lambda u, r_=r_: hexa(col, c.a(r_["a"] * light(r_, u))))
        c.bone_keys(r_["beam"], "scale", ts, lambda u, r_=r_: (1.0 + 0.1 * math.sin(2 * math.pi * r_["br"] * u / D + r_["brph"]), 1.0))
    if glow:
        c.color_keys(glow[1], ts, lambda u: hexa(col, c.a(0.55 * sum(light(r_, u) for r_ in rays) / nr)))
        c.bone_keys(glow[0], "scale", ts, lambda u: (1.0 + 0.06 * math.sin(2 * math.pi * u / D + ph1),) * 2)
    for m in motes:
        hw = m["ray"]["w"] * 0.38

        def mx(u, m=m, hw=hw):
            return hw * 2.2 * math.sin(2 * math.pi * m["cyc"] * u / D + m["ph"])
        c.bone_keys(m["b"], "translate", ts, lambda u, m=m, mx=mx: (mx(u), m["dy"] * math.sin(2 * math.pi * u / D + m["ph"] * 2)))
        c.color_keys(m["s"], ts, lambda u, m=m, mx=mx, hw=hw: hexa("FFFFFF", c.a(min(1.0, 0.95 * light(m["ray"], u) * math.exp(-(mx(u) / hw) ** 2)
                                                                                   * (0.6 + 0.4 * math.sin(2 * math.pi * m["tw"] * u / D + m["twph"]))))))
    # where the AE comp goes: its source point (fractions, y down) lands on this group's origin
    cw = int(P["comp_size"])
    sx, sy = 0.5 - 0.42 * math.cos(math.radians(ang)), 0.5 + 0.42 * math.sin(math.radians(ang))
    scale = L / (0.84 * cw)
    hint = dict(template="god_rays", params=dict(width=cw, height=cw, duration=D, source=[round(sx, 3), round(sy, 3)], sweep=sweep,
                                                  color=col, flicker=round(flick * 0.7, 3)),
                parent=c.group, front_of=c.slots[-1], mode="additive", seq_mode="loop", until=c.T(D),
                x=round((0.5 - sx) * cw * scale, 2), y=round((sy - 0.5) * cw * scale, 2), scale=round(scale, 4),
                note="volumetric rays: ae_template god_rays with these params -> save -> ae_fx_to_spine with the other args "
                     "(its sweep has the same phase as the Spine fan, so the two line up)")
    return c.result(duration=D * c.k, loop=D, rays=nr, dust=len(motes), fan_bone=fan, ae_hint=hint)


# ------------------------------------------------------------------ water_surface
def _default_lands() -> list[list[float]]:
    """Five reels of three symbols landing reel by reel, rings at each symbol's base."""
    return [[(i - 2) * 150.0, (j - 1) * 150.0 - 55.0, 0.25 + 0.3 * i] for i in range(5) for j in range(3)]


def water_surface(c: Ctx, P: dict) -> dict:
    """Capillary rings on the water surface wherever a symbol lands; caustics behind the reels come from AE (ae_hint)."""
    D = float(P["duration"])
    col = _hexn(P["color"], "BFEFFF")
    lands = P["lands"] if P["lands"] is not None else _default_lands()
    try:
        lands = [[float(v) for v in ld] for ld in lands]
    except (TypeError, ValueError):
        raise ValueError("lands must be [[x, y, t], ...]") from None
    if not lands or any(len(ld) != 3 for ld in lands):
        raise ValueError("lands must be a non-empty list of [x, y, t]")
    _check_pos(P, "size", "life", "squash")
    size, life, sq = float(P["size"]), float(P["life"]), float(P["squash"])
    nring = int(P["rings"])
    if nring < 1:
        raise ValueError("rings must be >= 1")
    late = [ld for ld in lands if not 0 <= ld[2] < D]
    if late:
        raise ValueError(f"lands {late} are outside the window 0..{D} s (raise duration)")
    grp = c.bone("water", c.group, 0, 0)
    made = []
    for li, (lx, ly, lt) in enumerate(lands):
        base = c.bone(f"land{li}", grp, lx, ly, sy=sq)                  # the surface is seen at an angle: rings are ellipses
        bg = c.bone(f"glint{li}", base)
        s_g = c.slot(bg, "fx/glow", size * 0.7, role="glint") if P["glint"] else None
        rings = []
        for k in range(nring):
            rb = c.bone(f"ring{li}_{k}", base)
            rings.append((rb, c.slot(rb, "fx/ring", size, role="ring"), 0.13 * k, 0.72 ** k))
        made.append(dict(t=lt, g=(bg, s_g), rings=rings))
    r0 = 0.12

    def radius(s: float) -> float:                     # capillary ring: r ~ sqrt(t)
        return r0 + (1.0 - r0) * math.sqrt(max(0.0, s) / life)
    for li, ld in enumerate(made):
        t0 = ld["t"]
        for rb, rs, d0, k_ in ld["rings"]:
            a0, e0 = t0 + d0, min(D, t0 + d0 + life)
            if a0 >= D:
                c.ab.slot_attachment(rs, [(0.0, None)])
                continue
            tr = times_dense(a0, e0, 30)
            c.bone_keys(rb, "scale", tr, lambda u, a0=a0: (radius(u - a0),) * 2)
            c.color_keys(rs, tr, lambda u, a0=a0, k_=k_: hexa(col, c.a(min(1.0, 1.1 * k_ * math.sqrt(0.25 / max(radius(u - a0), 0.25)))
                                                                         * (1 - smooth(u - a0, 0, life)) ** 1.2 * smooth(u - a0, 0, 0.03))))
            c.ab.slot_attachment(rs, [(0.0, None), (c.T(a0), "fx"), (c.T(e0), None)] if c.T(a0) > 0 else [(0.0, "fx"), (c.T(e0), None)])
        bg, s_g = ld["g"]
        if s_g:
            e0 = min(D, t0 + 0.5)
            tg = times_dense(t0, e0, 40)
            c.color_keys(s_g, tg, lambda u, t0=t0: hexa("FFFFFF", c.a(0.8 * smooth(u - t0, 0, 0.02) / (1 + 30 * max(0.0, u - t0))
                                                                     * (1 - smooth(u - t0, 0.3, 0.5)))))
            c.bone_keys(bg, "scale", tg, lambda u, t0=t0: (0.5 + 0.7 * ease_out((u - t0) / 0.3, 2.5),) * 2)
            c.ab.slot_attachment(s_g, [(0.0, None), (c.T(t0), "fx"), (c.T(e0), None)] if c.T(t0) > 0 else [(0.0, "fx"), (c.T(e0), None)])
        c.ab.event(c.T(t0), "fx_water_land", int=li)
    hint = dict(template="caustics", params=dict(width=int(P["caustics_width"]), height=int(P["caustics_height"]), duration=2.0),
                parent=c.group, behind=c.slots[0], mode="additive", seq_mode="loop", until=c.T(D), x=0, y=0, scale=1.0,
                note="caustic light under the surface: ae_template caustics with these params -> save -> ae_fx_to_spine with "
                     "behind=<your first reel/background slot> (the rings stay in front of the reels)")
    return c.result(duration=D * c.k, lands=len(lands), land_times=[c.T(ld["t"]) for ld in made], ae_hint=hint)


# ------------------------------------------------------------------ heat_shimmer
def heat_shimmer(c: Ctx, P: dict) -> dict:
    """The anchor for the AE heat shimmer above a fire, plus a faint rising-wave stand-in so it reads without AE."""
    D = float(P["duration"])
    col = _hexn(P["color"], "FFE8C8")
    _check_pos(P, "width", "height", "rise")
    Wd, Hd, rise, wob = float(P["width"]), float(P["height"]), float(P["rise"]), float(P["wobble"])
    ns = int(P["strands"])
    if ns < 1:
        raise ValueError("strands must be >= 1")
    rng = np.random.default_rng(c.seed + 321)
    strip = c.bone("strip", c.group, 0, Hd / 2)                       # x, y = the top of the fire; the strip rises from it
    cyc = max(1, int(round(rise * D / float(P["wavelength"]))))
    lam = rise * D / cyc                                              # phase speed = rise exactly, whole cycles per loop
    rows = max(8, int(round(Hd / 24)) + 1)
    strands = []
    for i in range(ns):
        xo = (i - (ns - 1) / 2) * Wd / max(ns, 1) * 0.8 + float(rng.uniform(-0.06, 0.06)) * Wd
        sl, nodes = c.strand(strip, "fx/ambient_haze", Wd * float(rng.uniform(0.1, 0.16)), Hd * float(rng.uniform(0.8, 1.0)), rows, x=xo, make=tex_haze,
                             tag=f"h{i}", role="haze")
        strands.append(dict(s=sl, nodes=nodes, ph=float(rng.uniform(0, 6.28)), a=float(rng.uniform(0.7, 1.0)),
                            fl=int(rng.integers(2, 6)), flph=float(rng.uniform(0, 6.28))))
    c.show(c.slots, 0, None)
    ts = times_dense(0, D, 16)
    amp = lambda yy: wob * (0.35 + 0.65 * yy / Hd)  # noqa: E731   the plume turns turbulent as it rises
    for sd in strands:
        for i, nb in enumerate(sd["nodes"]):
            yy = c.sk.bone(nb).y + Hd / 2                           # height above the fire top
            c.bone_keys(nb, "translate", ts, lambda u, yy=yy, sd=sd: (amp(yy) * math.sin(2 * math.pi * (yy - rise * u) / lam + sd["ph"]), 0.0))
        c.color_keys(sd["s"], ts, lambda u, sd=sd: hexa(col, c.a(float(P["alpha"]) * sd["a"] * (0.8 + 0.2 * math.sin(2 * math.pi * sd["fl"] * u / D + sd["flph"])))))
    hint = dict(template="heat_shimmer", params=dict(width=256, height=384, duration=D, rise=round(rise * 384 / Hd, 2), output="shimmer"),
                parent=strip, x=0, y=0, scale=round(Hd / 384, 4), front_of=c.slots[-1], mode="additive", seq_mode="loop",
                until=c.T(D),
                note="Spine cannot refract. output=shimmer bakes the schlieren look (additive) for ae_fx_to_spine with these args; "
                     "output=map renders the looping displacement map for an engine distortion shader placed on this bone; "
                     "output=preview shows the refraction over an image in AE. Turn the Spine stand-in down (intensity) when "
                     "the AE layer is in.")
    return c.result(duration=D * c.k, loop=D, anchor_bone=strip, wavelength=round(lam, 3), ae_hint=hint)


# ------------------------------------------------------------------ fog_roll
FOG = {"fog": dict(color="D6DEE8", speed=60.0, alpha=0.34, count=22, grit=0, size=(0.7, 1.2), life=4.0),
       "sand": dict(color="D2A868", speed=220.0, alpha=0.45, count=18, grit=36, size=(0.6, 1.0), life=2.5)}


def fog_roll(c: Ctx, P: dict) -> dict:
    """A fog bank or sandstorm rolling sideways across the screen in parallax layers; sand grains hop in saltation."""
    kind = str(P["kind"])
    if kind not in FOG:
        raise ValueError(f"kind must be fog | sand, got {kind!r}")
    F = FOG[kind]
    D = float(P["duration"])
    _check_pos(P, "width", "height")
    Wd, Hd = float(P["width"]), float(P["height"])
    col = _hexn(P["color"], F["color"])
    v = float(F["speed"] if P["speed"] is None else P["speed"])
    if v == 0:
        raise ValueError("speed must not be 0 (the bank has to flow; negative = leftward)")
    sgn = 1.0 if v > 0 else -1.0
    alpha_k = float(F["alpha"] if P["alpha"] is None else P["alpha"])
    n = int(P["count"] or F["count"])
    ng = int(F["grit"] if P["grit"] is None else P["grit"])
    nl = int(P["layers"])
    if nl < 1:
        raise ValueError("layers must be >= 1")
    shear = float(P["shear"])
    rng = np.random.default_rng(c.seed + 331)
    grp = c.bone("bank", c.group, 0, 0)
    puffs, grit = [], []
    for li in range(nl):
        dist = 1.0 + 0.8 * (nl - 1 - li) / max(1, nl - 1)                # far layer first (behind), slower and paler
        f = 1.0 / dist
        lb = c.bone(f"layer{li}", grp)
        for i in range(max(1, int(round(n / nl)))):
            bn = c.bone(f"l{li}f{i}", lb)
            sz = Hd * float(rng.uniform(*F["size"])) * (0.75 + 0.25 * f)
            sl = c.slot(bn, "fx/smoke", sz, blend="normal", role="puff")
            h = float(rng.beta(1.3, 2.4))                                 # 0 = ground: densest low down
            speed = abs(v) * f * (1 - shear / 2 + shear * h)               # shear: the top of the bank runs faster
            m = max(1, int(round(D / (F["life"] * float(rng.uniform(0.8, 1.25))))))
            T = D / m
            spawn = [dict(x=float(rng.uniform(-Wd / 2, Wd / 2)) - sgn * speed * T / 2, y=-Hd / 2 + h * Hd * 0.8 + float(rng.uniform(-0.04, 0.04)) * Hd)
                     for _ in range(m)]
            puffs.append(dict(b=bn, s=sl, m=m, ph=float(rng.uniform(0.02, 0.98)), speed=speed, spawn=spawn,
                              bob=float(rng.uniform(4, 14)), bc=int(rng.integers(1, 3)), bph=float(rng.uniform(0, 6.28)),
                              br=int(rng.integers(1, 3)), a=alpha_k * (0.55 + 0.45 * f) * (1.0 - 0.45 * h), h=h,
                              tint=_mix(_rgb(col), (255, 255, 255), float(rng.uniform(0.0, 0.25)) * f)))
    dudy = abs(v) * shear / (0.8 * Hd)                                    # shear rate of the near layer (1/s)
    spin = -sgn * math.degrees(0.5 * dudy) * 6.0                          # a parcel turns at half the vorticity (x6)
    for i in range(ng):
        bn = c.bone(f"g{i}", grp)
        sl = c.slot(bn, "fx/ambient_grit", float(rng.uniform(14, 26)), make=tex_grit, blend="normal", role="grain")
        hops = int(rng.integers(3, 7))
        span = Wd + 40
        speed = abs(v) * float(rng.uniform(1.6, 2.6))
        m = max(1, int(round(speed * D / span)))
        grit.append(dict(b=bn, s=sl, y0=-Hd / 2 + float(rng.uniform(0.0, 0.35)) * Hd, span=span, m=m, ph=float(rng.uniform(0, 1)),
                         hops=hops, hh=float(rng.uniform(10, 34)), a=float(rng.uniform(0.5, 0.85))))
    c.show(c.slots, 0, None)

    def lap(u, pf):
        z = u * pf["m"] / D + pf["ph"]
        return max(0.0, z - math.floor(z + 1e-7))

    def lap_times(pf, rate):
        ts = set(times_dense(0, D, rate))
        for k in range(0, pf["m"] + 2):
            w = (k - pf["ph"]) * D / pf["m"]
            if 0 < w < D:
                ts.update([w - 0.002, w])
        return sorted(t for t in ts if 0 <= t <= D)
    for pf in puffs:
        ts = _life_times(D, pf["m"], pf["ph"], 8, 0.25)

        def st(u, pf=pf):
            li, q, _ = _life(u, D, pf["m"], pf["ph"])
            sp = pf["spawn"][li]
            s_ = q * D / pf["m"]
            x = sp["x"] + sgn * pf["speed"] * s_
            y = sp["y"] + pf["bob"] * math.sin(2 * math.pi * pf["bc"] * u / D + pf["bph"])   # billows travel along the top
            return x, y, spin * s_, smooth(q, 0, 0.25) * (1 - smooth(q, 0.75, 1.0))
        vals = [st(u) for u in ts]
        c.ab.bone(pf["b"], "translate", _uniq([(c.T(u), vv[0], vv[1]) for u, vv in zip(ts, vals)]), "linear")
        c.ab.bone(pf["b"], "rotate", _uniq([(c.T(u), vv[2]) for u, vv in zip(ts, vals)]), "linear")
        c.bone_keys(pf["b"], "scale", ts, lambda u, pf=pf: (1.0 + 0.08 * math.sin(2 * math.pi * pf["br"] * u / D + pf["bph"]),) * 2)
        tint = "%02X%02X%02X" % tuple(int(x) for x in pf["tint"])
        c.ab.slot_color(pf["s"], _uniq([(c.T(u), hexa(tint, c.a(pf["a"] * vv[3]))) for u, vv in zip(ts, vals)]), "linear")
    for gr in grit:
        ts = lap_times(gr, 18)
        hop = D / (gr["m"] * gr["hops"])                                  # key every landing exactly: z * hops is whole
        ts = sorted(set(ts) | {(j - gr["ph"] * gr["hops"]) * hop for j in range(0, (gr["m"] + 1) * gr["hops"] + 2)
                               if 0 < (j - gr["ph"] * gr["hops"]) * hop < D})

        def gst(u, gr=gr):
            p = lap(u, gr)
            x = sgn * (-gr["span"] / 2 + p * gr["span"])
            hs = (p * gr["hops"]) % 1.0                                   # saltation: a parabola per hop
            y = gr["y0"] + 4 * gr["hh"] * hs * (1 - hs)
            vx = gr["span"] * gr["m"] / D * sgn
            vy = 4 * gr["hh"] * (1 - 2 * hs) * gr["hops"] * gr["m"] / D
            return x, y, math.degrees(math.atan2(vy, vx)) + (180.0 if sgn < 0 else 0.0), smooth(p, 0, 0.08) * (1 - smooth(p, 0.92, 1.0))
        vals = [gst(u) for u in ts]
        c.ab.bone(gr["b"], "translate", _uniq([(c.T(u), vv[0], vv[1]) for u, vv in zip(ts, vals)]), "linear")
        c.ab.bone(gr["b"], "rotate", _uniq([(c.T(u), vv[2]) for u, vv in zip(ts, vals)]), "linear")
        c.ab.slot_color(gr["s"], _uniq([(c.T(u), hexa(col, c.a(gr["a"] * vv[3]))) for u, vv in zip(ts, vals)]), "linear")
    cw = 1024
    hint = dict(template="fog_roll", params=dict(kind=kind, width=cw, height=int(round(cw * Hd / Wd)), duration=D,
                                                  speed=round(v * cw / Wd, 2)),
                parent=c.group, front_of=c.slots[-1], mode="alpha", seq_mode="loop", until=c.T(D), x=0, y=0,
                scale=round(Wd / cw, 4),
                note="volumetric bank: ae_template fog_roll with these params -> save -> ae_fx_to_spine with the other args; "
                     "lower this recipe's intensity (or count) once the AE layer is in")
    return c.result(duration=D * c.k, loop=D, kind=kind, puffs=len(puffs), grains=len(grit), ae_hint=hint)


# ------------------------------------------------------------------ lightning_storm
def schedule(rng, D: float, rate: float, min_gap: float, lead: float, tail: float) -> list[float]:
    """Strike times: a Poisson process with dead time, interval = min_gap + Exp(mean 1/rate - min_gap), so the mean
    interval is exactly 1/rate and no two strikes come closer than min_gap. Times in [lead, D - tail)."""
    out, t = [], lead + float(rng.exponential(1.0 / rate - min_gap))
    while t < D - tail:
        out.append(t)
        t += min_gap + float(rng.exponential(1.0 / rate - min_gap))
    return out


def lightning_storm(c: Ctx, P: dict) -> dict:
    """Random strikes across the top of the screen: flashes, sky glow, thunder events delayed by distance; AE bolts via ae_hint."""
    D = float(P["duration"])
    col = _hexn(P["color"], "B8CCFF")
    sky_c = _hexn(P["color2"], "8094FF")
    _check_pos(P, "rate", "width", "height", "sound_speed", "length")
    rate, gap = float(P["rate"]), float(P["min_gap"])
    if gap < 0 or gap >= 1.0 / rate:
        raise ValueError(f"min_gap must be in [0, 1/rate) = [0, {1.0 / rate:.3f}) so the mean interval can be 1/rate")
    d_lo, d_hi = (float(v) for v in P["distance"])
    if not 0 < d_lo <= d_hi:
        raise ValueError("distance must be [near, far] km with 0 < near <= far")
    Wd, Hd, cs, Lb = float(P["width"]), float(P["height"]), float(P["sound_speed"]), float(P["length"])
    nv = int(P["variants"])
    if nv < 1:
        raise ValueError("variants must be >= 1")
    rng = np.random.default_rng(c.seed + 341)
    top = Hd / 2
    fixed = P["strikes"]
    if fixed is not None:                                           # an exact schedule: [[x, t(, km)], ...]
        if not isinstance(fixed, list) or not fixed or any(len(f) not in (2, 3) for f in fixed):
            raise ValueError("strikes must be [[x, t], ...] or [[x, t, km], ...]")
        if any(not 0 <= float(f[1]) < D for f in fixed):
            raise ValueError(f"every strike time must be inside the window [0, {D})")
        fixed = sorted(([float(v) for v in f] for f in fixed), key=lambda f: f[1])
        times = [f[1] for f in fixed]
    else:
        times = schedule(rng, D, rate, gap, 0.15, 0.7)
        if not times:
            times = [min(D * 0.3, max(0.0, D - 0.75))]              # always at least one strike in the window
    strikes = []
    for i, t in enumerate(times):
        dmax = min(d_hi, (D - 0.02 - t) * cs)                       # its thunder must land inside the window
        if fixed is not None:
            d = max(0.05, min(fixed[i][2] if len(fixed[i]) == 3 else d_lo, max(dmax, 0.05)))
            x = fixed[i][0]
        else:
            if dmax < d_lo:
                continue
            d = float(rng.uniform(d_lo, dmax))
            x = float(rng.uniform(-0.45, 0.45)) * Wd
        b = min(1.0, d_lo / d)                                      # brightness ~ 1/distance (exaggerated from 1/d^2)
        strokes = [t]
        for _ in range(int(rng.integers(0, int(P["restrikes"]) + 1))):
            strokes.append(strokes[-1] + float(rng.uniform(0.06, 0.14)))
        strikes.append(dict(t=t, d=d, b=b, x=x, strokes=strokes, v=len(strikes) % nv))
    grp = c.bone("storm", c.group, 0, 0)
    b_sky = c.bone("sky", grp, 0, top, sy=0.55)
    s_sky = c.slot(b_sky, "fx/glow", Wd * 1.9, role="sky")
    for k, s in enumerate(strikes):
        s["gb"] = c.bone(f"cloud{k}", grp, s["x"], top - Hd * 0.05, sy=0.6)
        s["gs"] = c.slot(s["gb"], "fx/glow", Wd * 0.8 * (0.6 + 0.4 * s["b"]), role="cloud")
    if P["bolt"]:
        for k, s in enumerate(strikes):
            sc = 0.55 + 0.45 * math.sqrt(s["b"])                    # far bolts look smaller
            s["bb"] = c.bone(f"bolt{k}", grp, s["x"], top - Hd * 0.04, sx=float(rng.choice([-1.0, 1.0])) * sc, sy=sc)
            s["bs"] = c.slot(s["bb"], f"fx/ambient_bolt{s['v']}", Lb * 0.25, oy=-Lb / 2, height=Lb,
                             make=lambda v=s["v"]: tex_bolt(c.seed + v), role="bolt", stretch=True)
    amps = [1.0, 0.7, 0.55, 0.45, 0.4]

    def flash(u: float, s: dict) -> float:
        """Sum of return-stroke flashes: ~12 ms attack, 1/t decay (tau 40 ms), gone by 0.6 s."""
        v_ = 0.0
        for j, ts_ in enumerate(s["strokes"]):
            q = u - ts_
            if q > 0:
                v_ += amps[min(j, 4)] * smooth(q, 0, 0.012) / (1 + q / 0.04) * (1 - smooth(q, 0.35, 0.6))
        return v_

    def channel(u: float, s: dict) -> float:
        """The bolt itself: a faint stepped leader 50 ms before, then each stroke snaps on and cools e^(-t/50 ms)."""
        v_ = 0.25 * smooth(u, s["t"] - 0.05, s["t"] - 0.002) * (1 - smooth(u, s["t"] - 0.002, s["t"] + 0.01))
        for j, ts_ in enumerate(s["strokes"]):
            q = u - ts_
            if q > 0:
                v_ += amps[min(j, 4)] * smooth(q, 0, 0.008) * math.exp(-q / 0.05)
        return min(1.0, v_)
    win = sorted({t for s in strikes for t in times_dense(max(0.0, s["t"] - 0.06), min(D, s["strokes"][-1] + 0.62), 50)} | {0.0, D})
    c.show([s_sky], 0, D)
    c.color_keys(s_sky, win, lambda u: hexa(sky_c, c.a(min(1.0, 0.8 * sum((0.35 + 0.65 * s["b"]) * flash(u, s) for s in strikes)))))
    for s in strikes:
        on, off = max(0.0, s["t"] - 0.06), min(D, s["strokes"][-1] + 0.62)
        tw = times_dense(on, off, 50)
        c.ab.slot_attachment(s["gs"], [(0.0, None), (c.T(on), "fx"), (c.T(off), None)] if c.T(on) > 0 else [(0.0, "fx"), (c.T(off), None)])
        c.color_keys(s["gs"], tw, lambda u, s=s: hexa(col, c.a(min(1.0, 1.2 * (0.4 + 0.6 * s["b"]) * flash(u, s)))))
        if "bs" in s:
            c.ab.slot_attachment(s["bs"], [(0.0, None), (c.T(on), "fx"), (c.T(off), None)] if c.T(on) > 0 else [(0.0, "fx"), (c.T(off), None)])
            c.color_keys(s["bs"], tw, lambda u, s=s: hexa(col, c.a(min(1.0, (0.5 + 0.5 * s["b"]) * channel(u, s)))))
        c.ab.event(c.T(s["t"]), "fx_lightning_strike", int=strikes.index(s))
        c.ab.event(c.T(s["t"] + s["d"] / cs), "fx_thunder", float=round(s["d"], 3), volume=round(s["b"], 3),
                   balance=round(max(-1.0, min(1.0, s["x"] / (Wd / 2))), 3))
    lead_ae = 0.08                                                   # the AE template's stepped-leader time
    var_params = [dict(width=256, height=512, duration=0.7, start=[0.5, 0.02], end=[round(0.5 + float(rng.uniform(-0.15, 0.15)), 3), 0.97],
                       seed=c.seed + v, restrikes=int(P["restrikes"]), lead=lead_ae, color=col) for v in range(nv)]
    front = c.slots[-1]
    hint = dict(template="lightning", parent=c.group, front_of=front, mode="additive", seq_mode="once", variants=var_params,
                strikes=[dict(x=round(s["x"], 2), y=round(top - Hd * 0.04 - Lb * 0.5 * (0.55 + 0.45 * math.sqrt(s["b"])), 2),
                              start=round(c.T(s["t"]) - lead_ae, 4), hit_ae=lead_ae, hit_at=c.T(s["t"]), variant=s["v"],
                              scale=round(Lb / 512 * (0.55 + 0.45 * math.sqrt(s["b"])), 4), distance=round(s["d"], 3))
                         for s in strikes],
                note="AE bolts: render each entry of variants with ae_template lightning (params as given), then ae_fx_to_spine "
                     "once per strike with that strike's x, y, scale and hit_ae/hit_at (the return stroke lands on the strike "
                     "time). Set options bolt=false to drop the Spine fallback bolts; the flashes and thunder stay.")
    return c.result(duration=D * c.k, strikes=[c.T(s["t"]) for s in strikes],
                    thunder=[c.T(s["t"] + s["d"] / cs) for s in strikes], distances=[round(s["d"], 3) for s in strikes],
                    xs=[round(s["x"], 2) for s in strikes], ae_hint=hint)


# ------------------------------------------------------------------ registry
RECIPES.update({
    "weather": dict(
        fn=weather, duration=4.0, kind="loop", color="", count=0, normal_blend=True,
        summary="Screen weather with exaggerated real physics, option kind = rain | snow | embers | petals: particles at their "
                "kind's terminal velocity, Stokes drag toward a wind with a slow travelling gust (heavy drops lag and smooth "
                "it, flakes ride it), parallax depth layers (speed and size ~ 1/distance, far ones paler), rain streaks turned "
                "along the velocity, petals that swing, tilt and flip, embers that rise, flicker, cool and shrink. Looping lives "
                "respawn at alpha 0, so the loop closes exactly. count=0 uses the kind's default.",
        anchor="Centre of the area it fills (width x height).",
        options=dict(kind=("rain", "rain | snow | embers | petals"), width=(760.0, "area width"), height=(760.0, "area height"),
                     layers=(3, "depth layers (far ones drawn first)"), depth=(2.6, "distance of the far layer relative to the near one"),
                     wind=(None, "mean wind in units/s (+ = rightward); default per kind"),
                     gust=(None, "gust amplitude in units/s; default per kind"), gust_cycles=(1, "gusts per loop (whole number)"),
                     size=(1.0, "particle size multiplier"), alpha=(None, "opacity (default per kind)"),
                     palette=(None, "colours drawn at random (default per kind; color= forces one)"),
                     blend=("", "additive | normal (default: normal for petals, additive for the rest)"))),
    "god_rays": dict(
        fn=god_rays, duration=8.0, kind="loop", color="FFE6A8", count=16,
        summary="God rays: a fan of light shafts from a source (narrow there, widening and fading with distance), sweeping "
                "slowly, dimmed IN SEQUENCE by an occluder drifting across the source; dust motes glint only inside the beams. "
                "ae_hint: the volumetric AE template god_rays (rays through a mask, same sweep phase). count = dust motes.",
        anchor="The light source; the fan points along angle.",
        options=dict(rays=(7, "light shafts"), angle=(-60.0, "fan direction in degrees (0 = right, -90 = straight down)"),
                     spread=(48.0, "fan opening in degrees"), length=(900.0, "shaft length"), width=(110.0, "shaft width (at the far end)"),
                     sweep=(5.0, "slow sweep amplitude in degrees (one cycle per loop)"),
                     flicker=(0.45, "how much the drifting occluder dims the rays (0..1)"),
                     source_glow=(True, "soft glow at the source"), comp_size=(768, "AE comp size the ae_hint is computed for"))),
    "water_surface": dict(
        fn=water_surface, duration=2.6, kind="window", color="BFEFFF",
        summary="Water surface under the reels: every symbol that lands (option lands [[x, y, t], ...], default a 5x3 grid "
                "landing reel by reel) sends capillary rings out, r ~ sqrt(t), dimming as 1/sqrt(r) and damping out, with a "
                "1/t glint at the impact. Event fx_water_land (int = landing index) on every landing. ae_hint: the AE "
                "caustics template behind the reels.",
        anchor="Origin of the land offsets (the reel area centre).",
        options=dict(lands=(None, "[[x, y, t], ...] landing points and times (seconds) relative to x, y"),
                     size=(130.0, "ring diameter when fully spread"), life=(1.1, "seconds a ring lives"),
                     rings=(2, "rings per landing"), squash=(0.4, "ring squash (1 = seen from above)"),
                     glint=(True, "flash at the impact"), caustics_width=(800, "caustics comp width (ae_hint)"),
                     caustics_height=(480, "caustics comp height (ae_hint)"))),
    "heat_shimmer": dict(
        fn=heat_shimmer, duration=2.0, kind="loop", color="FFE8C8",
        summary="Heat shimmer above a fire. The refraction is After Effects (template heat_shimmer: displacement map, or its "
                "schlieren image baked additive); this recipe places the anchor bone at the fire's top (result anchor_bone, "
                "ae_hint) and adds a faint stand-in: soft strands bent by a wave rising with the plume (phase speed = rise), "
                "growing with height. Loops exactly.",
        anchor="The top of the fire; the strip rises height above it.",
        options=dict(width=(140.0, "strip width"), height=(260.0, "strip height"), rise=(160.0, "plume rise speed (units/s)"),
                     wobble=(7.0, "sideways wobble at the top (units)"), wavelength=(110.0, "wave length (rounded so the loop closes)"),
                     strands=(5, "stand-in filaments"), alpha=(0.2, "stand-in opacity"))),
    "fog_roll": dict(
        fn=fog_roll, duration=6.0, kind="loop", color="", count=0, normal_blend=True,
        summary="Fog bank or sandstorm (option kind fog | sand) rolling sideways: puffs advect with a wind that grows with "
                "height (shear) and roll forward as they go, densest at the ground, a far layer slower and paler (parallax); "
                "sand adds grains hopping in saltation (parabolic hops, streaked along their velocity). Normal blend. Loops "
                "exactly. ae_hint: the volumetric AE template fog_roll. count=0 uses the kind's default.",
        anchor="Centre of the bank (width x height); the ground is height/2 below.",
        options=dict(kind=("fog", "fog | sand"), width=(820.0, "bank width"), height=(300.0, "bank height"),
                     speed=(None, "flow speed in units/s (negative = leftward); default per kind"),
                     shear=(0.6, "how much faster the top runs than the bottom (0 = plug flow)"),
                     layers=(2, "depth layers"), alpha=(None, "puff opacity (default per kind)"),
                     grit=(None, "sand grains (default 36 for sand, 0 for fog)"))),
    "lightning_storm": dict(
        fn=lightning_storm, duration=8.0, kind="window", color="B8CCFF",
        summary="Lightning storm: strikes scheduled as a seeded Poisson process (rate per second, dead time min_gap) at random "
                "x across the top, each at a random distance: cloud glow + sky glow flash with a 1/t decay per return stroke, "
                "brightness ~ 1/distance, a Spine fallback bolt (jagged procedural channel), and fx_thunder fired distance / "
                "sound_speed later (float = km, volume, balance = pan). Events fx_lightning_strike, fx_thunder. ae_hint: the AE "
                "lightning template, one entry per strike (x, start, hit_ae/hit_at).",
        anchor="Centre of the screen (width x height); strikes come from the top edge.",
        options=dict(rate=(0.45, "mean strikes per second"), min_gap=(0.35, "dead time between strikes (s)"),
                     width=(760.0, "screen width"), height=(720.0, "screen height"), length=(520.0, "bolt length"),
                     distance=([1.0, 6.0], "strike distance range (km)"),
                     sound_speed=(2.0, "km/s (real 0.343; exaggerated so thunder follows in game time)"),
                     restrikes=(2, "max extra return strokes per strike"), color2=("8094FF", "sky glow colour"),
                     bolt=(True, "Spine fallback bolts (False when the AE bolts are in)"), variants=(3, "distinct bolt shapes"),
                     strikes=(None, "exact schedule instead of the Poisson draw: [[x, t], ...] or [[x, t, km], ...] (x from the centre, t in the window)"))),
})
RECIPES["lightning_storm"]["tiers"] = {"small": {"rate": 0.3}, "big": {"rate": 0.7, "restrikes": 3},
                                       "mega": {"rate": 1.0, "restrikes": 3}, "epic": {"rate": 1.4, "restrikes": 4, "min_gap": 0.25}}
ROLES.update({
    "weather": {"streak": "one rain streak, tall, head (leading end) at the BOTTOM", "flake": "one snowflake, centred",
                "ember": "one ember, centred", "petal": "one petal, tip at the TOP (normal blend)"},
    "god_rays": {"ray": "one light shaft, SOURCE at the BOTTOM edge, tall (stretched to the shaft length)", "glow": "the source glow",
                 "mote": "one dust mote"},
    "water_surface": {"ring": "the ripple ring, round, centred", "glint": "the impact glint"},
    "heat_shimmer": {"haze": "the faint stand-in strip, tall, centred (bent as a mesh)"},
    "fog_roll": {"puff": "one fog / dust puff, soft, centred (normal blend)", "grain": "one sand grain streak, horizontal (normal blend)"},
    "lightning_storm": {"sky": "the sky glow, round (squashed wide)", "cloud": "the glow inside the cloud at a strike",
                        "bolt": "one bolt, cloud at the TOP, tall (stretched to length)"},
})
for _n, _d in ROLES.items():
    if _n in RECIPES:
        RECIPES[_n]["roles"] = _d
