"""A Unity-style (Shuriken) particle emitter, simulated here and BAKED into Spine keys: ``fx_emitter``.

Spine has no particles, so the emitter runs the simulation in Python and writes the result as ordinary keys: a fixed
POOL of slots (one bone each) that particles reuse in turn. A slot is shown at a particle's birth and hidden at its
death (attachment keys), so a slot can be handed to the next particle without a visible jump, and each life is keyed
densely (``key_rate``) then thinned to straight-line keys within ``tolerance``. The pool never grows past
``max_particles``; a particle that would need one more slot is dropped and counted (``dropped``), so the budget is a
hard cap, not a hope.

Modules (names follow Unity's Particle System; every one is optional):

* main: ``duration`` (the emission window, or the loop period), ``loop``, ``lifetime``, ``speed``, ``size``,
  ``rotation``, ``color``, ``alpha``, ``gravity`` (units/s^2, pulls down), ``max_particles``, ``seed``.
* ``emission``: ``rate`` (particles/s, or a curve over the duration) and ``bursts`` [{time, count, cycles, interval,
  probability}].
* ``shape``: type point | circle | ring | cone | rect | edge | path, with ``radius``, ``thickness`` (0 = rim only,
  1 = filled), ``arc``, ``angle`` (direction, 90 = up), ``spread`` (cone width in degrees), ``width``/``height``,
  ``length``, ``points`` (path), ``direction`` outward | angle | normal, ``edge_only`` (rect).
* ``velocity``: extra ``x``/``y`` (units/s), ``orbital`` (deg/s round the emitter), ``radial`` (units/s away from it),
  ``speed_multiplier`` (curve over the life); ``drag`` (1/s, linear); ``inherit`` (share of a moving emitter's or
  a parent particle's velocity).
* ``noise``: ``strength`` (units/s), ``frequency`` (1/units), ``scroll`` (Hz): a divergence-free swirl field.
* over lifetime: ``size_over_lifetime``, ``alpha_over_lifetime``, ``color_over_lifetime`` (gradient), ``spin`` (deg/s).
* ``renderer``: ``blend`` additive | normal | multiply | screen, ``align`` none | velocity, ``stretch`` (seconds of
  travel added to the length when aligned: a streak), ``flip`` (random mirror).
* ``texture``: a built-in picture (``fx/spark``, ``fx/mote``, ``fx/glow``, ``fx/smoke``, ``fx/cloud``, ``fx/ring``,
  ``fx/wisp``), ``kit:<picture>`` (bundled CC0), a PNG path, ``file.psd#Layer``, or a FLIPBOOK
  {"frames": folder | [png, ...], "fps": 24 | "cycles": 1, "random_start": true} played as a Spine sequence
  (AE flipbooks drop straight in).
* ``sub_emitters``: [{"on": "death" | "birth", "emitter": {...} | "<preset>", "probability": 1}]: a child burst at
  every parent particle's death or birth, at that spot.
* ``move``: [[t, x, y], ...] the emitter's own path (world-space simulation: a trail stays behind).

Values: a number, [lo, hi] (random per particle), or for over-lifetime curves [[t, v], ...] with t in 0..1 of the
life (linear between points), or {"min": curve, "max": curve} (random between two curves). Colours: "RRGGBB",
["RRGGBB", ...] (random pick) or a gradient [[t, "RRGGBB"], ...].

A LOOP closes exactly: the spawn schedule is periodic, a particle alive across the loop point keeps the SAME slot on
both sides of it (its tail is drawn at the start of the loop), the noise scrolls a whole number of cycles per loop,
and a lifetime longer than the loop is clamped (warned). A one-shot runs ``duration`` of emission and lasts until the
last particle dies.

Presets (``emitter_presets/*.json``, plus your own saved with ``save_preset``) are the stored building blocks; start
from the closest one and override only what differs.
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
from pathlib import Path

import numpy as np
from PIL import Image

from .fx_recipes import WHITE_TEX, Ctx, _uniq
from .ir import Sequence
from .project import Project
from .timeline import r

WHITE_TEX.setdefault("fx/chip", lambda: Image.new("RGBA", (32, 48), (255, 255, 255, 255)))   # confetti, debris
PRESET_DIR = Path(__file__).resolve().parent / "emitter_presets"
BLENDS = ("additive", "normal", "multiply", "screen")
SHAPES = ("point", "circle", "ring", "cone", "rect", "edge", "path")
BASE = 64.0                                   # region size in units; particle size is a scale of it
TOL = {"position": 0.6, "rotation": 1.5, "scale": 0.015, "color": 0.02}

DEFAULTS: dict = {
    "duration": 1.0, "loop": False, "lifetime": [0.6, 1.0], "speed": [180.0, 360.0], "size": [14.0, 26.0],
    "rotation": [0.0, 360.0], "color": "FFFFFF", "alpha": 1.0, "gravity": 0.0, "max_particles": 40, "seed": 7,
    "emission": {"rate": 0.0, "bursts": [{"time": 0.0, "count": 24}]},
    "shape": {"type": "point", "radius": 0.0, "thickness": 1.0, "arc": 360.0, "angle": 90.0, "spread": 360.0,
              "width": 100.0, "height": 100.0, "length": 100.0, "points": [], "direction": "outward",
              "edge_only": False},
    "velocity": {"x": 0.0, "y": 0.0, "orbital": 0.0, "radial": 0.0, "speed_multiplier": 1.0},
    "drag": 0.0, "inherit": 0.0,
    "noise": {"strength": 0.0, "frequency": 0.01, "scroll": 0.5},
    "size_over_lifetime": 1.0, "alpha_over_lifetime": [[0.0, 0.0], [0.08, 1.0], [0.7, 1.0], [1.0, 0.0]],
    "color_over_lifetime": None, "spin": 0.0,
    "renderer": {"blend": "additive", "align": "none", "stretch": 0.0, "flip": False},
    "texture": "fx/spark",
    "sub_emitters": [],
    "move": [],
    "key_rate": 30.0, "tolerance": {},
}


# ------------------------------------------------------------------ presets
def _user_dir() -> Path:
    return Path(os.environ.get("CLAUDE_SPINE_PRESETS", Path.home() / ".claude-spine" / "emitter_presets")).expanduser()


def presets() -> dict[str, dict]:
    """Every preset: the built-in ones, then the user's own (which win on a name clash)."""
    out = {}
    for folder, origin in ((PRESET_DIR, "built-in"), (_user_dir(), "user")):
        if folder.is_dir():
            for f in sorted(folder.glob("*.json")):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                except ValueError as e:
                    raise ValueError(f"emitter preset {f} is not valid JSON: {e}") from e
                out[f.stem] = {**data, "_origin": origin, "_file": str(f)}
    return out


def _merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def resolve(preset: str = "", emitter: dict | None = None) -> dict:
    """DEFAULTS <- preset <- overrides; unknown keys are refused (a typo would silently do nothing)."""
    spec = copy.deepcopy(DEFAULTS)
    if preset:
        found = presets()
        if preset not in found:
            raise ValueError(f"no emitter preset {preset!r}; one of {sorted(found)}")
        spec = _merge(spec, {k: v for k, v in found[preset].items() if not k.startswith("_") and k != "doc"})
    spec = _merge(spec, emitter or {})
    _check(spec)
    return spec


def _check(spec: dict, where: str = "emitter") -> None:
    unknown = set(spec) - set(DEFAULTS) - {"doc"}
    if unknown:
        raise ValueError(f"{where}: unknown module(s) {sorted(unknown)}; modules are {sorted(DEFAULTS)}")
    for mod in ("emission", "shape", "velocity", "noise", "renderer"):
        extra = set(spec[mod]) - set(DEFAULTS[mod])
        if extra:
            raise ValueError(f"{where}.{mod}: unknown setting(s) {sorted(extra)}; it takes {sorted(DEFAULTS[mod])}")
    if spec["shape"]["type"] not in SHAPES:
        raise ValueError(f"{where}.shape.type must be one of {SHAPES}")
    if spec["renderer"]["blend"] not in BLENDS:
        raise ValueError(f"{where}.renderer.blend must be one of {BLENDS}")
    if spec["renderer"]["align"] not in ("none", "velocity"):
        raise ValueError(f"{where}.renderer.align must be none | velocity")
    if float(spec["duration"]) <= 0:
        raise ValueError(f"{where}.duration must be > 0")
    if not 1 <= int(spec["max_particles"]) <= 400:
        raise ValueError(f"{where}.max_particles must be 1..400 (every particle is a bone, a slot and keys)")
    if spec["shape"]["type"] == "path" and len(spec["shape"]["points"]) < 2:
        raise ValueError(f"{where}.shape: a path needs at least 2 points [[x, y], ...]")
    for sub in spec["sub_emitters"]:
        if sub.get("on", "death") not in ("death", "birth"):
            raise ValueError(f"{where}.sub_emitters: on must be death | birth")


def save_preset(name: str, spec: dict, doc: str = "") -> str:
    if not re.fullmatch(r"[a-z0-9_]{2,48}", name):
        raise ValueError("preset name: 2-48 lowercase letters, digits or _")
    folder = _user_dir()
    folder.mkdir(parents=True, exist_ok=True)
    keep = {k: v for k, v in spec.items() if k in DEFAULTS and v != DEFAULTS[k]}
    if doc:
        keep = {"doc": doc, **keep}
    path = folder / f"{name}.json"
    path.write_text(json.dumps(keep, indent=1) + "\n", encoding="utf-8")
    return str(path)


# ------------------------------------------------------------------ values
def _start(v, rng) -> float:
    """A start value: number, or [lo, hi] uniform per particle."""
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, (list, tuple)) and len(v) == 2 and all(isinstance(x, (int, float)) for x in v):
        return float(rng.uniform(v[0], v[1]))
    raise ValueError(f"start value must be a number or [lo, hi], got {v!r}")


def _curve(v, q: float, k: float = 0.0) -> float:
    """An over-lifetime value at life fraction q: number, [[t, v], ...], or {"min": c, "max": c} blended by k."""
    if v is None:
        return 1.0
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):
        return _curve(v["min"], q) * (1 - k) + _curve(v["max"], q) * k
    pts = sorted((float(t), float(y)) for t, y in v)
    if q <= pts[0][0]:
        return pts[0][1]
    for (t0, y0), (t1, y1) in zip(pts, pts[1:]):
        if q <= t1:
            return y0 + (y1 - y0) * ((q - t0) / max(t1 - t0, 1e-9))
    return pts[-1][1]


def _rgbf(h: str) -> tuple[float, float, float]:
    h = h.lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", h):
        raise ValueError(f"colour must be RRGGBB, got {h!r}")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _gradient(g, q: float) -> tuple[float, float, float]:
    pts = sorted((float(t), _rgbf(c)) for t, c in g)
    if q <= pts[0][0]:
        return pts[0][1]
    for (t0, c0), (t1, c1) in zip(pts, pts[1:]):
        if q <= t1:
            u = (q - t0) / max(t1 - t0, 1e-9)
            return tuple(a + (b - a) * u for a, b in zip(c0, c1))
    return pts[-1][1]


def _start_color(v, rng) -> tuple[float, float, float]:
    if isinstance(v, str):
        return _rgbf(v)
    if isinstance(v, list) and v and isinstance(v[0], str):
        return _rgbf(str(rng.choice(v)))
    if isinstance(v, list) and v and isinstance(v[0], (list, tuple)):
        return _gradient(v, float(rng.uniform()))
    raise ValueError(f"color must be RRGGBB, a list of them or a gradient, got {v!r}")


# ------------------------------------------------------------------ simulation
class _Noise:
    """Curl of psi = sum_k a_k sin(f_k x + p_k + w_k t) sin(f_k y + q_k): swirls, no sources or sinks."""

    def __init__(self, n: dict, rng, period: float | None):
        self.s = float(n["strength"])
        f = float(n["frequency"])
        self.oct = []
        for k in range(3):
            fk = f * (1.9 ** k)
            w = 2 * math.pi * float(n["scroll"]) * (1.6 ** k)
            if period:                       # a whole number of cycles per loop: the field closes with the loop
                w = 2 * math.pi * round(w * period / (2 * math.pi)) / period
            self.oct.append((0.55 ** k, fk, float(rng.uniform(0, 6.3)), float(rng.uniform(0, 6.3)), w))

    def __call__(self, x: float, y: float, t: float) -> tuple[float, float]:
        if not self.s:
            return 0.0, 0.0
        vx = vy = 0.0
        for a, f, p, q, w in self.oct:
            sx, cx = math.sin(f * x + p + w * t), math.cos(f * x + p + w * t)
            sy, cy = math.sin(f * y + q), math.cos(f * y + q)
            vx += a * sx * cy          # d psi / dy
            vy -= a * cx * sy          # -d psi / dx
        return self.s * vx, self.s * vy


def _emitter_pos(move: list, t: float) -> tuple[float, float, float, float]:
    """(x, y, vx, vy) of the emitter at time t from its [[t, x, y], ...] path."""
    if not move:
        return 0.0, 0.0, 0.0, 0.0
    pts = sorted((float(a), float(b), float(c)) for a, b, c in move)
    if t <= pts[0][0]:
        return pts[0][1], pts[0][2], 0.0, 0.0
    for (t0, x0, y0), (t1, x1, y1) in zip(pts, pts[1:]):
        if t <= t1:
            u, dt = (t - t0) / max(t1 - t0, 1e-9), max(t1 - t0, 1e-9)
            return x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, (x1 - x0) / dt, (y1 - y0) / dt
    return pts[-1][1], pts[-1][2], 0.0, 0.0


def _shape_point(sh: dict, rng) -> tuple[float, float, float]:
    """(x, y, direction in degrees) of one birth on the emitter's shape."""
    kind, ang, spread = sh["type"], float(sh["angle"]), float(sh["spread"])
    cone = ang + float(rng.uniform(-spread / 2, spread / 2))
    if kind == "point":
        return 0.0, 0.0, cone
    if kind in ("circle", "ring"):
        R = float(sh["radius"])
        th = 0.0 if kind == "ring" else float(sh["thickness"])
        a = math.radians(float(rng.uniform(0, float(sh["arc"]))) + (ang - float(sh["arc"]) / 2 if sh["arc"] < 360 else 0))
        rad = R * math.sqrt(float(rng.uniform((1 - th) ** 2, 1.0)))
        d = math.degrees(a) if sh["direction"] == "outward" else cone
        return rad * math.cos(a), rad * math.sin(a), d
    if kind == "cone":
        R = float(sh["radius"])
        off = float(rng.uniform(-R, R))
        p = math.radians(ang + 90)
        return off * math.cos(p), off * math.sin(p), ang + spread / 2 * (off / R if R else float(rng.uniform(-1, 1)))
    if kind == "rect":
        w, h = float(sh["width"]), float(sh["height"])
        if sh["edge_only"]:
            per = 2 * (w + h)
            s = float(rng.uniform(0, per))
            if s < w:
                x, y, d = -w / 2 + s, h / 2, 90.0
            elif s < w + h:
                x, y, d = w / 2, h / 2 - (s - w), 0.0
            elif s < 2 * w + h:
                x, y, d = w / 2 - (s - w - h), -h / 2, 270.0
            else:
                x, y, d = -w / 2, -h / 2 + (s - 2 * w - h), 180.0
            return x, y, (d + float(rng.uniform(-spread / 2, spread / 2))) if sh["direction"] != "angle" else cone
        return float(rng.uniform(-w / 2, w / 2)), float(rng.uniform(-h / 2, h / 2)), cone
    if kind == "edge":
        L = float(sh["length"])
        s = float(rng.uniform(-L / 2, L / 2))
        p = math.radians(ang - 90)
        return s * math.cos(p), s * math.sin(p), cone
    # path: uniform by arc length, direction = the segment's normal (left of travel) unless direction=angle
    pts = [(float(a), float(b)) for a, b in sh["points"]]
    segs = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    s = float(rng.uniform(0, sum(segs)))
    for (a, b), L in zip(zip(pts, pts[1:]), segs):
        if s <= L or L == segs[-1]:
            u = s / max(L, 1e-9)
            x, y = a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
            n = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) + 90
            jit = float(rng.uniform(-spread / 2, spread / 2))
            return x, y, (n + jit) if sh["direction"] != "angle" else cone
        s -= L
    return pts[-1][0], pts[-1][1], cone


def _spawn_times(spec: dict, rng, loop: bool) -> list[float]:
    D = float(spec["duration"])
    em = spec["emission"]
    times: list[float] = []
    rate = em["rate"]
    if isinstance(rate, (int, float)) and rate > 0 or isinstance(rate, list):
        # inverse CDF of the rate curve over the duration; a loop gets a whole number of births per period
        xs = np.linspace(0, 1, 201)
        rs = np.array([max(0.0, _curve(rate, float(x))) for x in xs])
        cdf = np.concatenate([[0], np.cumsum((rs[1:] + rs[:-1]) / 2 * np.diff(xs))]) * D
        n = int(round(cdf[-1])) if loop else int(math.floor(cdf[-1] + float(rng.uniform())))
        for i in range(n):
            u = (i + 0.5 + float(rng.uniform(-0.35, 0.35))) / max(n, 1) * cdf[-1]
            times.append(float(np.interp(u, cdf, xs)) * D)
    for b in em.get("bursts", []):
        cycles = int(b.get("cycles", 1))
        for c in range(cycles):
            t = float(b.get("time", 0.0)) + c * float(b.get("interval", 0.0))
            if t >= D and loop:
                continue
            if float(rng.uniform()) > float(b.get("probability", 1.0)):
                continue
            n = int(round(_start(b.get("count", 10), rng)))
            times += [t] * n
    return sorted(t % D if loop else t for t in times)


class _P:
    __slots__ = ("birth", "life", "t", "x", "y", "rot", "sx", "sy", "rgba", "depth", "tex", "frame0", "pool")


def _simulate(spec: dict, rng, loop: bool, period: float | None, births: list[tuple] | None = None,
              depth: int = 0) -> list[_P]:
    """Simulate every particle of one emitter. ``births`` = [(time, x, y, vx, vy)] for a sub-emitter (at a parent's
    death or birth), else the emitter's own schedule on its shape. Returns sampled particles (and their children)."""
    D = float(spec["duration"])
    noise = _Noise(spec["noise"], rng, period)
    sh, vel, ren = spec["shape"], spec["velocity"], spec["renderer"]
    drag, grav, inherit = float(spec["drag"]), float(spec["gravity"]), float(spec["inherit"])
    rate_k = float(spec["key_rate"])
    out: list[_P] = []
    if births is None:
        births = [(t, *_emitter_pos(spec["move"], t)) for t in _spawn_times(spec, rng, loop)]
        sub_each = None
    else:
        sub_each = True
    sub_events: list[tuple[dict, tuple]] = []
    for (t0, ex, ey, evx, evy) in births:
        reps = 1 if sub_each is None else int(round(_start(spec["emission"]["bursts"][0].get("count", 6), rng)
                                                    if spec["emission"].get("bursts") else 6))
        for _ in range(reps):
            life = max(0.02, _start(spec["lifetime"], rng))
            if period and life > period * 0.98:
                life = period * 0.98
            sx_, sy_, d = _shape_point(sh, rng)
            sp = _start(spec["speed"], rng)
            a = math.radians(d)
            vx, vy = sp * math.cos(a) + inherit * evx, sp * math.sin(a) + inherit * evy
            x, y = ex + sx_, ey + sy_
            size0, rot0 = _start(spec["size"], rng), _start(spec["rotation"], rng)
            spin = _start(spec["spin"], rng)
            col0 = _start_color(spec["color"], rng)
            alpha0 = _start(spec["alpha"], rng)
            kcur = float(rng.uniform())
            flip = -1.0 if ren["flip"] and rng.uniform() < .5 else 1.0
            ox, oy = ex, ey                                   # the orbit / radial centre: where it was born from
            n_sim = max(8, int(math.ceil(life * 120)))
            dt = life / n_sim
            ts, xs, ys, vxs, vys = [0.0], [x], [y], [vx], [vy]
            for i in range(n_sim):
                q = i / n_sim
                vy -= grav * dt
                if drag:
                    f = math.exp(-drag * dt)
                    vx, vy = vx * f, vy * f
                m = _curve(vel["speed_multiplier"], q, kcur)
                nx, ny = noise(x, y, t0 + i * dt)
                stepx = (vx * m + float(vel["x"]) + nx) * dt
                stepy = (vy * m + float(vel["y"]) + ny) * dt
                rx, ry = x - ox, y - oy
                rr = math.hypot(rx, ry)
                if float(vel["radial"]) and rr > 1e-6:
                    stepx += rx / rr * float(vel["radial"]) * dt
                    stepy += ry / rr * float(vel["radial"]) * dt
                if float(vel["orbital"]):
                    w = math.radians(float(vel["orbital"])) * dt
                    rx2, ry2 = rx * math.cos(w) - ry * math.sin(w), rx * math.sin(w) + ry * math.cos(w)
                    stepx += rx2 - rx
                    stepy += ry2 - ry
                x, y = x + stepx, y + stepy
                ts.append((i + 1) * dt)
                xs.append(x); ys.append(y); vxs.append(stepx / dt); vys.append(stepy / dt)
            # keys: dense samples of the life, then the exact birth and death
            nk = max(2, int(math.ceil(life * rate_k)) + 1)
            kt = np.linspace(0, life, nk)
            P = _P()
            P.birth, P.life, P.t, P.depth = t0, life, kt, depth
            P.x = np.interp(kt, ts, xs)
            P.y = np.interp(kt, ts, ys)
            vxk, vyk = np.interp(kt, ts, vxs), np.interp(kt, ts, vys)
            qk = kt / life
            size = np.array([size0 * max(0.0, _curve(spec["size_over_lifetime"], float(q), kcur)) for q in qk])
            if ren["align"] == "velocity":
                P.rot = np.degrees(np.arctan2(vyk, vxk)) - 90.0
                spd = np.hypot(vxk, vyk)
                length = size + float(ren["stretch"]) * spd
                P.sx, P.sy = size / BASE * flip, length / BASE
            else:
                P.rot = rot0 + spin * kt
                P.sx, P.sy = size / BASE * flip, size / BASE
            # keep the rotation continuous (atan2 wraps): Spine interpolates the short way only between close keys
            P.rot = np.degrees(np.unwrap(np.radians(P.rot)))
            alpha = np.array([alpha0 * max(0.0, min(1.0, _curve(spec["alpha_over_lifetime"], float(q), kcur)))
                              for q in qk])
            if spec["color_over_lifetime"]:
                tint = np.array([_gradient(spec["color_over_lifetime"], float(q)) for q in qk])
            else:
                tint = np.ones((nk, 3))
            P.rgba = np.column_stack([tint * np.array(col0), alpha])
            P.tex = None
            P.frame0 = int(rng.integers(0, 1 << 30))
            out.append(P)
            for sub in spec["sub_emitters"]:
                if float(rng.uniform()) > float(sub.get("probability", 1.0)):
                    continue
                at = life if sub.get("on", "death") == "death" else 0.0
                ii = -1 if at else 0
                tb = (t0 + at) % period if period else t0 + at     # a death past the loop point wraps to its start
                sub_events.append((sub, (tb, float(P.x[ii]), float(P.y[ii]), float(vxk[ii]), float(vyk[ii]))))
    if depth < 2:
        by_sub: dict[int, tuple[dict, list]] = {}
        for sub, ev in sub_events:
            by_sub.setdefault(id(sub), (sub, []))[1].append(ev)
        for k, (sub, evs) in by_sub.items():
            child = sub["emitter"]
            cspec = resolve(child) if isinstance(child, str) else resolve("", child)
            cspec["duration"] = spec["duration"]
            out += _simulate(cspec, rng, loop, period, births=evs, depth=depth + 1)
    for P in out:
        if P.tex is None:                    # each emitter (parent, every sub-emitter) gets its own pool
            P.tex = ((depth, id(spec)), spec)
    return out


# ------------------------------------------------------------------ pooling
def _segments(P: _P, D: float | None) -> list[tuple[float, float, float]]:
    """(start, end, age at start) pieces of a life on the animation clock; a loop wraps a life across the seam."""
    a, b = P.birth, P.birth + P.life
    if D is None or b <= D:
        return [(a, b, 0.0)]
    return [(a, D, 0.0), (0.0, b - D, D - a)]


def _pool(parts: list[_P], cap: int, D: float | None, gap: float) -> tuple[list[list[tuple[_P, list]]], int]:
    """Greedy interval assignment: a slot takes the next particle once its last one is gone (``gap`` later).
    In a loop a particle crossing the seam is placed first, so its two pieces share one slot."""
    slots: list[list[tuple[float, float]]] = []
    owners: list[list[tuple[_P, list]]] = []
    dropped = 0
    order = sorted(parts, key=lambda p: (0 if D is not None and p.birth + p.life > D else 1, p.birth))
    for P in order:
        segs = _segments(P, D)
        placed = False
        for i, busy in enumerate(slots):
            if all(s1 + gap <= a or b + gap <= s0 for a, b, _ in segs for s0, s1 in busy):
                busy += [(a, b) for a, b, _ in segs]
                owners[i].append((P, segs))
                placed = True
                break
        if not placed:
            if len(slots) >= cap:
                dropped += 1
                continue
            slots.append([(a, b) for a, b, _ in segs])
            owners.append([(P, segs)])
    return owners, dropped


# ------------------------------------------------------------------ key reduction
def _reduce(t: np.ndarray, v: np.ndarray, tol: float) -> list[int]:
    """Indices of keys to keep so straight lines between them stay within tol of every sample (RDP, all channels)."""
    keep = {0, len(t) - 1}
    stack = [(0, len(t) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        u = (t[lo + 1:hi] - t[lo]) / max(t[hi] - t[lo], 1e-12)
        pred = v[lo] + (v[hi] - v[lo]) * u[:, None]
        err = np.abs(v[lo + 1:hi] - pred).max(axis=1)
        j = int(np.argmax(err))
        if err[j] > tol:
            mid = lo + 1 + j
            keep.add(mid)
            stack += [(lo, mid), (mid, hi)]
    return sorted(keep)


def _hex8(rgba) -> str:
    return "".join(f"{max(0, min(255, round(float(c) * 255))):02X}" for c in rgba)


# ------------------------------------------------------------------ textures
def _flipbook(c: Ctx, spec, name: str) -> tuple[str, int, tuple[int, int], dict]:
    """Write a flipbook's frames as one Spine sequence; returns (path prefix, count, frame size, options)."""
    frames = spec["frames"]
    if isinstance(frames, str):
        folder = Path(frames).expanduser()
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() in (".png", ".tif", ".tiff"))
    else:
        files = [Path(f).expanduser() for f in frames]
    if not files:
        raise ValueError(f"texture.frames: no PNG/TIFF frames in {frames!r}")
    from . import ae_bridge
    digits = max(2, len(str(len(files) - 1)))
    prefix = f"fx/emit_{name}_"
    size = (0, 0)
    for i, f in enumerate(files):
        if f.suffix.lower() in (".tif", ".tiff"):
            pm = ae_bridge.read_premultiplied(f, "alpha")
            a = pm[..., 3:4]
            rgb = np.divide(pm[..., :3], a, out=np.zeros_like(pm[..., :3]), where=a > 1e-3)
            im = Image.fromarray(np.round(np.clip(np.dstack([rgb, a]), 0, 1) * 255).astype(np.uint8), "RGBA")
        else:
            im = Image.open(f).convert("RGBA")
        size = im.size
        c.p.write_image(f"{prefix}{i:0{digits}d}", im)
    return prefix, len(files), size, {"digits": digits}


def bake(p: Project, preset: str = "", emitter: dict | None = None, x: float = 0.0, y: float = 0.0,
         scale: float = 1.0, start: float = 0.0, intensity: float = 1.0, into: str = "", parent: str = "root",
         front_of: str = "", behind: str = "", name: str = "") -> dict:
    """Simulate the emitter and bake it into ``p``: one group bone at (x, y) in ``parent``, a pooled slot per
    concurrent particle, keys into the animation ``into`` (or a new ``fx_<name>``)."""
    spec = resolve(preset, emitter)
    loop = bool(spec["loop"])
    D = float(spec["duration"])
    rng = np.random.default_rng(int(spec["seed"]))
    parts = _simulate(spec, rng, loop, D if loop else None)
    if not parts:
        raise ValueError("the emitter spawned no particles (emission.rate and bursts are both empty)")
    warnings = []
    lt = spec["lifetime"]
    if loop and (max(lt) if isinstance(lt, list) else float(lt)) > D * 0.98:
        warnings.append("lifetime longer than the loop: clamped to the loop length")
    nm = name or preset or "emitter"
    c = Ctx(p, "emitter", x, y, scale, start, 1.0, intensity, int(spec["seed"]), into, parent, front_of, behind, nm)
    tol = {**TOL, **spec["tolerance"]}
    gap = 1.0 / 240
    groups: dict[int, list[_P]] = {}
    for P in parts:
        groups.setdefault(P.tex[0], []).append(P)
    slots_out, keys_out, dropped_out, emitted = [], 0, 0, len(parts)
    spans: list[tuple[float, float]] = []
    end = 0.0
    for gi, (gk, members) in enumerate(sorted(groups.items(), key=lambda kv: kv[0][0])):
        gspec = members[0].tex[1]
        cap = int(gspec["max_particles"])
        owners, dropped = _pool(members, cap, D if loop else None, gap)
        dropped_out += dropped
        tex = gspec["texture"]
        blend = gspec["renderer"]["blend"]
        flip = None
        if isinstance(tex, dict) and "frames" in tex:
            flip = _flipbook(c, tex, f"{nm}{gi}")
        art_role = None
        if not flip and isinstance(tex, str) and not tex.startswith("fx/"):
            art_role = f"particle{gi}"
            c.art[art_role] = tex
        elif not flip and isinstance(tex, dict):
            art_role = f"particle{gi}"
            c.art[art_role] = tex
        grp = c.bone(f"pool{gi}", c.group)
        for si, own in enumerate(owners):
            b = c.bone(f"g{gi}p{si}", grp)
            if flip:
                prefix, count, fsize, _ = flip
                sl = c.slot(b, prefix + "0" * flip[3]["digits"], BASE, blend=blend)
                _set_sequence(c, sl, prefix, count, fsize, flip[3]["digits"])
            else:
                sl = c.slot(b, tex if tex.startswith("fx/") else "fx/spark", BASE, blend=blend, role=art_role) \
                    if isinstance(tex, str) else c.slot(b, "fx/spark", BASE, blend=blend, role=art_role)
            vis: list = []
            tr, ro, scl, col, seq = [], [], [], [], []
            for P, segs in own:
                for (a, bnd, age0) in segs:
                    sel = (P.t >= age0 - 1e-9) & (P.t <= age0 + (bnd - a) + 1e-9)
                    tt = P.t[sel] - age0 + a
                    if len(tt) < 2 or tt[0] > a + 1e-6 or tt[-1] < bnd - 1e-6:
                        # the cut fell between samples: add exact ends by interpolation
                        grid = np.unique(np.concatenate([[age0, age0 + bnd - a], P.t[sel]]))
                        tt = grid - age0 + a
                        cols = lambda arr: np.interp(grid, P.t, arr)  # noqa: E731
                    else:
                        cols = lambda arr, s=sel: arr[s]  # noqa: E731
                    xs, ys = cols(P.x), cols(P.y)
                    rs, sxs, sys_ = cols(P.rot), cols(P.sx), cols(P.sy)
                    rgba = np.column_stack([cols(P.rgba[:, k]) for k in range(4)])
                    rgba[:, 3] = np.clip(rgba[:, 3] * intensity, 0, 1)
                    keep = sorted(set(_reduce(tt, np.column_stack([xs, ys]), tol["position"]))
                                  | set(_reduce(tt, rs[:, None], tol["rotation"]))
                                  | set(_reduce(tt, np.column_stack([sxs, sys_]), tol["scale"]))
                                  | set(_reduce(tt, rgba, tol["color"])))
                    for i in keep:
                        T = c.T(float(tt[i]))
                        tr.append((T, round(float(xs[i]), 2), round(float(ys[i]), 2)))
                        ro.append((T, round(float(rs[i]), 2)))
                        scl.append((T, round(float(sxs[i]), 4), round(float(sys_[i]), 4)))
                        col.append((T, _hex8(rgba[i])))
                    vis.append((c.T(a), "fx"))
                    if not (loop and bnd >= D - 1e-9):   # a life crossing the loop point carries on at t = 0
                        vis.append((c.T(bnd), None))
                    if flip:
                        fps = tex.get("fps", 0)
                        delay = (1.0 / fps) if fps else (P.life / max(1, flip[1] * float(tex.get("cycles", 1))))
                        idx = (P.frame0 % flip[1]) if tex.get("random_start", False) else 0
                        idx = (idx + int(age0 / delay)) % flip[1]
                        seq.append((c.T(a), tex.get("mode", "loop"), idx, delay))
                    end = max(end, bnd)
            vis = _visibility(vis, c.T(0.0), loop)
            c.ab.slot_attachment(sl, vis)
            c.ab.bone(b, "translate", _uniq(sorted(tr)), "linear")
            c.ab.bone(b, "rotate", _uniq(sorted(ro)), "linear")
            c.ab.bone(b, "scale", _uniq(sorted(scl)), "linear")
            c.ab.slot_color(sl, _uniq(sorted(col)), "linear")
            if flip:
                c.ab.sequence(sl, "fx", _uniq(sorted(seq)))
            keys_out += len(tr) * 4 + len(vis)
            slots_out.append(sl)
        spans += [(a, b2) for own in owners for P, segs in own for a, b2, _ in segs]
    # how many are alive at once, every pool together (after the caps)
    peak_alive, alive = 0, 0
    for _, dlt in sorted([(a, 1) for a, _ in spans] + [(b2, -1) for _, b2 in spans]):
        alive += dlt
        peak_alive = max(peak_alive, alive)
    length = D if loop else end
    if dropped_out:
        warnings.append(f"{dropped_out} of {emitted} particles dropped: more than max_particles alive at once "
                        f"(raise max_particles, lower the rate/count, or shorten the lifetime)")
    res = c.result(duration=round(length, 4), loop=loop, emitted=emitted, dropped=dropped_out,
                   peak_alive=peak_alive, pool_slots=len(slots_out), keys=keys_out, warnings=warnings,
                   preset=preset or None,
                   budget={"bones": len(c.bones), "slots": len(slots_out), "keys": keys_out,
                           "note": "each pooled slot is a bone + slot + its keys; cost follows peak_alive, not emitted"})
    return res


def _visibility(vis: list, t_zero: float, loop: bool) -> list:
    """Attachment keys from (time, name) pairs: hidden before the first birth, and no hide+show on the same tick."""
    pts: dict[float, str | None] = {}
    for t, n in sorted(vis, key=lambda p: (p[0], p[1] is not None)):
        pts[t] = n
    out = sorted(pts.items())
    if not out or out[0][0] > t_zero:
        out.insert(0, (t_zero, None))
    if t_zero > 0 and out[0][0] > 0:
        out.insert(0, (0.0, None))
    return out


def _set_sequence(c: Ctx, slot: str, prefix: str, count: int, fsize: tuple[int, int], digits: int) -> None:
    """Turn the slot's region into a sequence of the flipbook frames (path prefix + index)."""
    att = c.sk.attachment(slot, "fx")
    att.path = prefix
    att.height = round(BASE * fsize[1] / max(fsize[0], 1), 2)
    att.sequence = Sequence(count=count, start=0, digits=digits)
