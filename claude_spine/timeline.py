"""Keyframe building with named easings.

Spine 4.x stores a curve on the key that *starts* a segment, as absolute bezier
control points: for each animated value ``cx1, cy1, cx2, cy2`` where cx are
times in seconds and cy are values (not 0..1 fractions as in CSS). This module
takes CSS-style normalised easings and converts them, so presets can say
``"back_out"`` and get the same feel at any duration and amplitude.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from .ir import Animation, DrawOrderKey, DrawOrderOffset, EventKey, Key, SkeletonData, EventData

# CSS cubic-bezier(x1, y1, x2, y2). None = linear (Spine's default, no curve).
EASE: dict[str, tuple[float, float, float, float] | None | str] = {
    "linear": None,
    "stepped": "stepped",
    "ease": (0.25, 0.1, 0.25, 1.0),
    "in": (0.42, 0, 1, 1),
    "out": (0, 0, 0.58, 1),
    "in_out": (0.42, 0, 0.58, 1),
    "sine_in": (0.12, 0, 0.39, 0),
    "sine_out": (0.61, 1, 0.88, 1),
    "sine_in_out": (0.37, 0, 0.63, 1),
    "quad_in": (0.11, 0, 0.5, 0),
    "quad_out": (0.5, 1, 0.89, 1),
    "quad_in_out": (0.45, 0, 0.55, 1),
    "cubic_in": (0.32, 0, 0.67, 0),
    "cubic_out": (0.33, 1, 0.68, 1),
    "cubic_in_out": (0.65, 0, 0.35, 1),
    "expo_in": (0.7, 0, 0.84, 0),
    "expo_out": (0.16, 1, 0.3, 1),
    "expo_in_out": (0.87, 0, 0.13, 1),
    "back_in": (0.36, 0, 0.66, -0.56),
    "back_out": (0.34, 1.56, 0.64, 1),
    "back_in_out": (0.68, -0.6, 0.32, 1.6),
    "snap": (0.2, 1.4, 0.4, 1),          # fast with a crisp overshoot (UI pops)
    "anticipate": (0.6, -0.28, 0.73, 0.04),
}


def curve_for(ease, t0: float, t1: float, v0: Sequence[float], v1: Sequence[float]):
    """Absolute Spine curve for one segment; None means linear."""
    if ease is None:
        return None
    if isinstance(ease, str):
        if ease not in EASE:
            raise ValueError(f"unknown easing {ease!r}; one of {sorted(EASE)}")
        ease = EASE[ease]
        if ease is None or ease == "stepped":
            return ease
    x1, y1, x2, y2 = ease
    dt = t1 - t0
    out: list[float] = []
    for a, b in zip(v0, v1):
        out += [r(t0 + x1 * dt), r(a + y1 * (b - a)), r(t0 + x2 * dt), r(a + y2 * (b - a))]
    return out


def r(v: float, nd: int = 4) -> float:
    v = round(float(v), nd)
    return 0.0 if v == 0 else v


# timeline name -> value field names, for bone/slot/constraint timelines
FIELDS = {
    "rotate": ("value",), "translatex": ("value",), "translatey": ("value",),
    "scalex": ("value",), "scaley": ("value",), "shearx": ("value",), "sheary": ("value",),
    "translate": ("x", "y"), "scale": ("x", "y"), "shear": ("x", "y"),
    "alpha": ("value",),
}
DEFAULT = {"rotate": (0,), "translate": (0, 0), "translatex": (0,), "translatey": (0,),
           "scale": (1, 1), "scalex": (1,), "scaley": (1,), "shear": (0, 0), "alpha": (1,)}


def keys(points: Iterable, timeline: str, ease="sine_in_out") -> list[Key]:
    """Build keys from ``(time, value)`` / ``(time, x, y)`` / ``(time, values..., ease)``.

    The easing on a point shapes the segment that *leaves* it; the last
    point's easing is ignored. A per-point easing overrides the default.
    """
    flds = FIELDS[timeline]
    pts = []
    for p in points:
        p = list(p)
        e = ease
        if len(p) == len(flds) + 2:
            e = p.pop()
        if len(p) != len(flds) + 1:
            raise ValueError(f"{timeline} keys need time + {len(flds)} value(s), got {p}")
        pts.append((float(p[0]), [float(v) for v in p[1:]], e))
    pts.sort(key=lambda t: t[0])
    out: list[Key] = []
    for i, (t, vals, e) in enumerate(pts):
        k = {"time": r(t)}
        for f, v in zip(flds, vals):
            k[f] = r(v, 3)
        if i + 1 < len(pts):
            c = curve_for(e, t, pts[i + 1][0], vals, pts[i + 1][1])
            if c is not None:
                k["curve"] = c
        out.append(Key(**k))
    return out


def color_keys(points: Iterable, ease="sine_in_out", timeline: str = "rgba") -> list[Key]:
    """points: (time, "RRGGBBAA") or (time, (r, g, b, a)) [, ease]."""
    from .ir import color_hex, parse_color
    pts = []
    for p in points:
        p = list(p)
        e = p.pop() if len(p) == 3 else ease
        c = p[1] if isinstance(p[1], str) else color_hex(*p[1])
        pts.append((float(p[0]), c, e))
    pts.sort(key=lambda t: t[0])
    out = []
    n = 4 if timeline == "rgba" else (3 if timeline == "rgb" else 1)
    for i, (t, c, e) in enumerate(pts):
        if timeline == "alpha":
            k = {"time": r(t), "value": r(parse_color(c)[3], 4)}
        else:
            k = {"time": r(t), "color": c[: 2 * n]}
        if i + 1 < len(pts):
            a = parse_color(c)[:n] if timeline != "alpha" else parse_color(c)[3:]
            b = parse_color(pts[i + 1][1])[:n] if timeline != "alpha" else parse_color(pts[i + 1][1])[3:]
            cv = curve_for(e, t, pts[i + 1][0], a, b)
            if cv is not None:
                k["curve"] = cv
        out.append(Key(**k))
    return out


class AnimBuilder:
    """Fluent helper that writes into ``sk.animations[name]``."""

    def __init__(self, sk: SkeletonData, name: str, replace: bool = True):
        self.sk = sk
        if replace or name not in sk.animations:
            sk.animations[name] = Animation()
        self.a = sk.animations[name]
        self.name = name

    def bone(self, bone: str, timeline: str, points, ease="sine_in_out") -> "AnimBuilder":
        self.sk.bone(bone)
        self.a.bones.setdefault(bone, {})[timeline] = keys(points, timeline, ease)
        return self

    def slot_color(self, slot: str, points, ease="sine_in_out", timeline: str = "rgba") -> "AnimBuilder":
        self.sk.slot(slot)
        self.a.slots.setdefault(slot, {})[timeline] = color_keys(points, ease, timeline)
        return self

    def slot_attachment(self, slot: str, points) -> "AnimBuilder":
        self.sk.slot(slot)
        self.a.slots.setdefault(slot, {})["attachment"] = [
            Key(time=r(t), name=n) for t, n in sorted(points, key=lambda p: p[0])]
        return self

    def sequence(self, slot: str, attachment: str, points, skin: str = "default") -> "AnimBuilder":
        """points: (time, mode, index, delay) with mode hold|once|loop|pingpong|..."""
        ks = []
        for t, mode, index, delay in points:
            k = {"time": r(t), "mode": mode}
            if index:
                k["index"] = index
            if delay:
                k["delay"] = r(delay, 5)
            ks.append(Key(**k))
        node = self.a.attachments.setdefault(skin, {}).setdefault(slot, {}).setdefault(attachment, {})
        node["sequence"] = ks
        return self

    def ik(self, name: str, points, ease="sine_in_out") -> "AnimBuilder":
        """points: (time, mix[, bendPositive])."""
        ks = []
        pts = sorted(points, key=lambda p: p[0])
        for i, p in enumerate(pts):
            k = {"time": r(p[0]), "mix": r(p[1], 4)}
            if len(p) > 2:
                k["bendPositive"] = bool(p[2])
            if i + 1 < len(pts):
                c = curve_for(ease, p[0], pts[i + 1][0], [p[1], 0], [pts[i + 1][1], 0])
                if c is not None:
                    k["curve"] = c
            ks.append(Key(**k))
        self.a.ik[name] = ks
        return self

    def transform_mix(self, name: str, points, ease="sine_in_out") -> "AnimBuilder":
        """points: (time, mix) applied to every mix channel."""
        ks = []
        pts = sorted(points, key=lambda p: p[0])
        chans = ("mixRotate", "mixX", "mixY", "mixScaleX", "mixScaleY", "mixShearY")
        for i, (t, m) in enumerate(pts):
            k = {"time": r(t), **{c: r(m, 4) for c in chans}}
            if i + 1 < len(pts):
                c = curve_for(ease, t, pts[i + 1][0], [m] * 6, [pts[i + 1][1]] * 6)
                if c is not None:
                    k["curve"] = c
            ks.append(Key(**k))
        self.a.transform[name] = ks
        return self

    def draw_order(self, time: float, offsets: dict[str, int] | None) -> "AnimBuilder":
        """offsets = {slot: shift} relative to setup order; None restores setup."""
        k = DrawOrderKey(time=r(time), offsets=None if offsets is None else
                         [DrawOrderOffset(slot=s, offset=o) for s, o in
                          sorted(offsets.items(), key=lambda kv: self.sk.slot_index(kv[0]))])
        self.a.drawOrder = [d for d in self.a.drawOrder if abs(d.time - k.time) > 1e-6] + [k]
        self.a.drawOrder.sort(key=lambda d: d.time)
        return self

    def event(self, time: float, name: str, **fields) -> "AnimBuilder":
        if name not in self.sk.events:
            self.sk.events[name] = EventData()
        self.a.events.append(EventKey(time=r(time), name=name, **fields))
        self.a.events.sort(key=lambda e: e.time)
        return self

    def physics_reset(self, time: float, constraint: str = "") -> "AnimBuilder":
        node = self.a.physics.setdefault(constraint, {})
        node.setdefault("reset", []).append(Key(time=r(time)))
        return self


def swap_offsets(sk: SkeletonData, front: str, back: str) -> dict[str, int]:
    """Draw-order offsets that put ``back`` in front of ``front`` (a swap)."""
    i, j = sk.slot_index(front), sk.slot_index(back)
    if i == j:
        return {}
    return {front: j - i, back: i - j}
