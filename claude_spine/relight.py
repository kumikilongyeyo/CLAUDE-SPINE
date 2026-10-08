"""Light from the effect onto the subject, measured instead of hand-keyed.

The realism rule the AE VFX director ranks first: the effect must light what it is near. Doing it by hand means
guessing a face-glow envelope that matches a flash, a breathing aura and a spectrum burst at once. ``relight``
measures it instead. It plays the animation in the official spine-core runtime and, for every frame, takes every
draw of the source slots. A draw contributes its displayed area (from the real vertices, so bone scale, sequence
frame and clipping are all in it) times its opacity times the mean light of the exact texture region shown (the
region name the runtime reports, so a sequence's current frame), in the colour it is drawn in (two-colour tint
included). The sum is the light reaching the subject, frame by frame. Additive twins of the subject slots (the
subject's own pictures, following its attachment keys, e.g. a coin's face swap) are keyed to that light's
brightness and colour: violet while an aura breathes, white on a spectrum flash, back to violet.

``norm`` maps an energy to ``strength``. Pass one animation's returned ``norm`` to the next (idle -> reveal) so the
same aura lights the subject equally in both and only the flash goes beyond (it clips at full).
"""
from __future__ import annotations

import fnmatch
import math

import numpy as np

from . import runtime
from .art_tools import art_twin
from .project import Project
from .timeline import AnimBuilder

LUM = np.array([0.2126, 0.7152, 0.0722])


def match_slots(project: Project, patterns: list[str]) -> list[str]:
    """Slot names matching any of the patterns (exact names or fnmatch globs such as 'ae_flash*')."""
    names = [s.name for s in project.data.slots]
    out = [n for n in names if any(n == p or fnmatch.fnmatchcase(n, p) for p in patterns)]
    if not out:
        raise ValueError(f"no slot matches {patterns}")
    return out


class _Stats:
    """Mean light of a texture region: A = mean alpha, G = mean premultiplied grey, M = mean premultiplied rgb."""

    def __init__(self, project: Project):
        self.p, self.cache = project, {}

    def get(self, region: str | None):
        if region not in self.cache:
            try:
                im = np.asarray(self.p.image(region).convert("RGBA"), np.float32) / 255
            except Exception:  # noqa: BLE001  (a generated texture missing on disk: treat as a soft white disc)
                self.cache[region] = (0.5, 0.5, np.array([0.5, 0.5, 0.5]))
                return self.cache[region]
            a = im[..., 3]
            pm = im[..., :3] * a[..., None]
            self.cache[region] = (float(a.mean()), float((pm @ LUM).mean()), pm.reshape(-1, 3).mean(0))
        return self.cache[region]


def _area(v: list[float], tri: list[int]) -> float:
    if not tri:
        return 0.0
    p = np.asarray(v, float).reshape(-1, 2)
    t = np.asarray(tri, int).reshape(-1, 3)
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    return float(np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (c[:, 0] - a[:, 0]) * (b[:, 1] - a[:, 1])).sum() / 2)


def light_curve(project: Project, animation: str, sources: list[str], fps: float = 30) -> dict:
    """Per-frame light of the source slots: times, energy (luminance x world area), and its colour."""
    src = set(match_slots(project, sources))
    dump = runtime.run(project, animations=[animation], fps=fps, geometry=True)
    if not dump.get("ok", True) and dump.get("error"):
        raise RuntimeError(dump["error"])
    frames = dump["animations"][animation]["frames"]
    stats = _Stats(project)
    times, energy, colour = [], [], []
    for i, f in enumerate(frames):
        rgb = np.zeros(3)
        for d in f["draws"]:
            if d["slot"] not in src:
                continue
            A, G, M = stats.get(d.get("region"))
            col = np.asarray(d["color"][:3], float)
            alpha = float(d["color"][3])
            if d.get("dark") is not None:          # two-colour tint: rgb = g * light + (1 - g) * dark
                emitted = G * col + (A - G) * np.asarray(d["dark"], float)
            else:
                emitted = M * col
            rgb += emitted * alpha * _area(d["v"], d["tri"])
        times.append(f.get("t", i / fps))
        energy.append(float(rgb @ LUM))
        colour.append(rgb)
    return {"times": times, "energy": energy, "colour": colour, "slots": sorted(src)}


def _hex(c) -> str:
    return "".join(f"{int(round(float(np.clip(x, 0, 1)) * 255)):02X}" for x in c)


def _simplify(keys: list[tuple[float, np.ndarray]], tol: float = 2 / 255) -> list[tuple[float, np.ndarray]]:
    """Drop keys that linear interpolation between their neighbours reproduces within tol (every channel)."""
    if len(keys) <= 2:
        return keys
    out = [keys[0]]
    for i in range(1, len(keys) - 1):
        t0, v0 = out[-1]
        t1, v1 = keys[i]
        t2, v2 = keys[i + 1]
        u = (t1 - t0) / max(t2 - t0, 1e-9)
        if np.abs(v0 + (v2 - v0) * u - v1).max() > tol:
            out.append(keys[i])
    out.append(keys[-1])
    return out


def relight(project: Project, animation: str, sources: list[str], subjects: list[str], strength: float = 0.6,
            floor: float = 0.0, gamma: float = 1.0, norm: float = 0.0, fps: float = 30, name: str = "relight",
            saturation: float = 1.0) -> dict:
    """Key additive twins of `subjects` to the measured light of `sources` (see the module docstring).

    alpha(t) = clamp(floor + strength * (E(t) / norm) ** gamma); colour(t) = the sources' light colour at t (its
    brightest channel at 1, pulled toward white by 1 - saturation). Returns twins, norm, peak and hits (times of
    the sharpest rises: flashes and impacts, for timing shakes or sounds to the light)."""
    sk = project.data
    if animation not in sk.animations:
        raise ValueError(f"no animation {animation!r}")
    for s in subjects:
        sk.slot(s)
    if strength <= 0:
        raise ValueError("strength must be positive")
    cv = light_curve(project, animation, sources, fps)
    E = np.asarray(cv["energy"])
    if E.max() <= 0:
        raise ValueError(f"the sources {cv['slots']} give no light in {animation!r} (hidden, or fully transparent?)")
    n = norm if norm > 0 else float(E.max())
    alpha = np.clip(floor + strength * np.clip(E / n, 0, None) ** gamma, 0, 1)
    keys = []
    for t, a, c in zip(cv["times"], alpha, cv["colour"]):
        m = float(np.max(c))
        col = c / m if m > 1e-12 else np.ones(3)
        col = 1 - saturation * (1 - col)                       # saturation < 1 pulls toward white
        keys.append((float(t), np.r_[col, a]))
    keys = _simplify(keys)
    tw = art_twin(project, subjects, name=name)["twins"]
    a = sk.animations[animation]
    ab = AnimBuilder(sk, animation, replace=False)
    for s, twin in zip(subjects, tw):
        src_keys = a.slots.get(s, {}).get("attachment", [])
        pts = [(k.time, getattr(k, "name", None)) for k in src_keys]
        if not pts or pts[0][0] > 0:
            pts.insert(0, (0.0, sk.slot(s).attachment))
        ab.slot_attachment(twin, pts)
        ab.slot_color(twin, [(t, _hex(v[:3]) + f"{int(round(v[3] * 255)):02X}") for t, v in keys], "linear")
    dE = np.diff(E) * fps
    hits = []
    if len(dE) > 2 and dE.max() > 0:
        thr = 0.5 * dE.max()
        for i in range(1, len(dE) - 1):
            if dE[i] >= thr and dE[i] >= dE[i - 1] and dE[i] >= dE[i + 1]:
                hits.append(round(cv["times"][i + 1], 4))
    peak_i = int(E.argmax())
    return {"animation": animation, "twins": tw, "sources": cv["slots"], "norm": round(n, 4),
            "peak": {"time": round(cv["times"][peak_i], 4), "alpha": round(float(alpha[peak_i]), 3)},
            "hits": hits, "keys": len(keys), "mean_alpha": round(float(alpha.mean()), 3)}
