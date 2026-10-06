"""Animator-friendly keyframe reduction for Spine animations.

Dense procedural sampling is useful while generating motion, but unpleasant to
edit by hand. This module reduces linear sampled timelines to meaningful keys,
then optionally rebuilds smooth monotone Bezier curves.

Existing authored/stepped curves are left alone unless force_curved=True.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np

from .project import Project
from .timeline import FIELDS, r


MODE_SCALE = {"fidelity": 0.55, "balanced": 1.0, "editable": 2.25}

BASE_TOL = {
    "rotate": (0.35,),
    "translate": (0.65, 0.65),
    "translatex": (0.65,),
    "translatey": (0.65,),
    "scale": (0.0045, 0.0045),
    "scalex": (0.0045,),
    "scaley": (0.0045,),
    "shear": (0.35, 0.35),
    "shearx": (0.35,),
    "sheary": (0.35,),
    "alpha": (0.008,),
}


def _vals(keys, timeline: str) -> np.ndarray:
    fields = FIELDS[timeline]
    return np.asarray([[float(getattr(k, f)) for f in fields] for k in keys], float)


def _times(keys) -> np.ndarray:
    return np.asarray([float(k.time) for k in keys], float)


def _mandatory(times: np.ndarray, vals: np.ndarray) -> set[int]:
    """Keep endpoints, extrema, direction changes and hold boundaries."""
    n = len(times)
    keep = {0, n - 1}
    if n < 3:
        return keep
    eps = 1e-9
    for i in range(1, n - 1):
        for j in range(vals.shape[1]):
            a = vals[i, j] - vals[i - 1, j]
            b = vals[i + 1, j] - vals[i, j]
            if abs(a) <= eps or abs(b) <= eps or a * b < 0:
                keep.add(i)
                break
    return keep


def _rdp_segment(times: np.ndarray, vals: np.ndarray, lo: int, hi: int,
                 tol: np.ndarray, keep: set[int]) -> None:
    if hi <= lo + 1:
        return
    dt = times[hi] - times[lo]
    if dt <= 1e-12:
        keep.update(range(lo, hi + 1))
        return
    u = ((times[lo + 1:hi] - times[lo]) / dt)[:, None]
    pred = vals[lo] + u * (vals[hi] - vals[lo])
    err = np.max(np.abs(vals[lo + 1:hi] - pred) / np.maximum(tol, 1e-12), axis=1)
    if not len(err):
        return
    krel = int(np.argmax(err))
    if float(err[krel]) > 1.0:
        k = lo + 1 + krel
        keep.add(k)
        _rdp_segment(times, vals, lo, k, tol, keep)
        _rdp_segment(times, vals, k, hi, tol, keep)


def _reduce_indices(times: np.ndarray, vals: np.ndarray, tol: np.ndarray) -> list[int]:
    keep = _mandatory(times, vals)
    anchors = sorted(keep)
    for lo, hi in zip(anchors, anchors[1:]):
        _rdp_segment(times, vals, lo, hi, tol, keep)
    return sorted(keep)


def _monotone_tangents(times: np.ndarray, y: np.ndarray, ease_ends: bool = True) -> np.ndarray:
    """PCHIP-like tangents: smooth, with no new overshoot in monotone runs."""
    n = len(times)
    if n <= 1:
        return np.zeros(n)
    h = np.diff(times)
    d = np.divide(np.diff(y), h, out=np.zeros(n - 1), where=h > 1e-12)
    m = np.zeros(n)
    if n == 2:
        if not ease_ends:
            m[:] = d[0]
        return m
    if not ease_ends:
        m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        a, b = d[i - 1], d[i]
        if a == 0 or b == 0 or a * b <= 0:
            m[i] = 0.0
        else:
            m[i] = 2.0 * a * b / (a + b)
    for i, di in enumerate(d):
        if abs(di) < 1e-12:
            m[i] = m[i + 1] = 0.0
            continue
        a, b = m[i] / di, m[i + 1] / di
        mag = a * a + b * b
        if mag > 9.0:
            q = 3.0 / math.sqrt(mag)
            m[i], m[i + 1] = q * a * di, q * b * di
    return m


def _recurve(keys, timeline: str, ease_ends: bool = True) -> int:
    if len(keys) < 2:
        return 0
    times = _times(keys)
    vals = _vals(keys, timeline)
    tangents = np.column_stack([
        _monotone_tangents(times, vals[:, j], ease_ends) for j in range(vals.shape[1])
    ])
    curves = 0
    for i in range(len(keys) - 1):
        dt = times[i + 1] - times[i]
        if dt <= 1e-12:
            keys[i].curve = None
            continue
        cv: list[float] = []
        for j in range(vals.shape[1]):
            cv += [
                r(times[i] + dt / 3),
                r(vals[i, j] + tangents[i, j] * dt / 3, 4),
                r(times[i] + 2 * dt / 3),
                r(vals[i + 1, j] - tangents[i + 1, j] * dt / 3, 4),
            ]
        keys[i].curve = cv
        curves += 1
    keys[-1].curve = None
    return curves


def optimize(project: Project, animation: str, mode: str = "editable", tolerance: float = 1.0,
             recurve: bool = True, force_curved: bool = False, ease_ends: bool = True) -> dict[str, Any]:
    """Reduce dense numeric bone timelines while preserving extrema.

    mode: fidelity | balanced | editable.
    tolerance multiplies per-channel defaults, so position/rotation/scale are
    judged in sensible native units instead of one universal threshold.
    """
    if mode not in MODE_SCALE:
        raise ValueError(f"mode is one of {sorted(MODE_SCALE)}")
    if tolerance <= 0:
        raise ValueError("tolerance must be > 0")
    sk = project.data
    if animation not in sk.animations:
        raise ValueError(f"animation {animation!r} not found")
    a = sk.animations[animation]

    before = after = curves = 0
    changed: dict[str, dict[str, dict[str, int]]] = {}
    skipped: list[str] = []
    fac = MODE_SCALE[mode] * float(tolerance)

    for bone, tls in a.bones.items():
        for timeline, ks in list(tls.items()):
            if timeline not in FIELDS or timeline not in BASE_TOL or len(ks) < 3:
                continue
            before += len(ks)
            if not force_curved and any(k.curve is not None for k in ks[:-1]):
                skipped.append(f"{bone}/{timeline}")
                after += len(ks)
                continue
            times, vals = _times(ks), _vals(ks, timeline)
            tol = np.asarray(BASE_TOL[timeline], float) * fac
            idx = _reduce_indices(times, vals, tol)
            new = [ks[i].model_copy(deep=True) for i in idx]
            for k in new:
                k.curve = None
            if recurve:
                curves += _recurve(new, timeline, ease_ends=ease_ends)
            tls[timeline] = new
            after += len(new)
            if len(new) != len(ks):
                changed.setdefault(bone, {})[timeline] = {"before": len(ks), "after": len(new)}

    return {
        "animation": animation,
        "mode": mode,
        "before_keys": before,
        "after_keys": after,
        "removed": before - after,
        "reduction": round((before - after) / before, 4) if before else 0.0,
        "curved_segments": curves,
        "changed": changed,
        "skipped_curved": skipped,
        "note": "Events, attachments, draw order and existing authored curves are untouched by default.",
    }
