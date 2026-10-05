"""Slot-game FX built from Spine primitives — the ``fx_generate`` tool's engine.

Every texture is generated procedurally, white or neutral, and tinted per slot,
so one small texture serves every colour (the atlas stays tiny). FX slots have
no setup attachment: the FX animation switches them on and off, so they never
show up in the setup pose or in animations that do not use them.

Each preset builds its own group bone (``fx_<name>``) so it can be moved or
scaled as one piece, and writes into its own animation or merges into an
existing one (``into=`` "win", say) so the FX plays inside the symbol's clip.

Heavy particle counts belong in the engine's emitter. Every preset fires a
Spine event at its start (``fx_<preset>``) that the game can use to trigger
one, so a 200-coin fountain does not have to be 200 bones.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image

from .ir import ClippingAttachment, MeshAttachment, RegionAttachment, Sequence, SkeletonData, Slot
from .project import Project
from .timeline import AnimBuilder, r

# ----------------------------------------------------------------- textures
def _rgba(rgb: np.ndarray, a: np.ndarray) -> Image.Image:
    a = np.clip(a, 0, 1)
    out = np.dstack([np.clip(rgb, 0, 1), a]) if rgb.ndim == 3 else np.dstack([np.repeat(np.clip(rgb, 0, 1)[..., None], 3, 2), a])
    return Image.fromarray(np.round(out * 255).astype(np.uint8), "RGBA")


def _grid(n: int):
    y, x = np.mgrid[0:n, 0:n].astype(float)
    c = (n - 1) / 2
    return (x - c) / c, (y - c) / c


def tex_glow(n: int = 128) -> Image.Image:
    x, y = _grid(n)
    d = np.hypot(x, y)
    a = np.exp(-(d / 0.42) ** 2) * (d < 1)
    a *= np.clip((1 - d) / 0.08, 0, 1)
    return _rgba(np.ones((n, n)), a)


def tex_ring(n: int = 192, radius: float = 0.78, width: float = 0.09) -> Image.Image:
    x, y = _grid(n)
    d = np.hypot(x, y)
    a = np.exp(-((d - radius) / width) ** 2)
    a *= np.clip((1 - d) / 0.06, 0, 1)
    return _rgba(np.ones((n, n)), a)


def tex_spark(n: int = 96) -> Image.Image:
    """Four-point star with a hot core."""
    x, y = _grid(n)
    d = np.hypot(x, y)
    rays = np.exp(-np.abs(x) / 0.05) * np.exp(-np.abs(y) / 0.55) + np.exp(-np.abs(y) / 0.05) * np.exp(-np.abs(x) / 0.55)
    core = np.exp(-(d / 0.18) ** 2)
    a = np.clip(rays * 0.9 + core, 0, 1) * np.clip((1 - d) / 0.1, 0, 1)
    return _rgba(np.ones((n, n)), a)


def tex_streak(w: int = 256, h: int = 64) -> Image.Image:
    """Soft vertical band for shine sweeps (rotated by its bone)."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    xn = (x - (w - 1) / 2) / ((w - 1) / 2)
    yn = (y - (h - 1) / 2) / ((h - 1) / 2)
    a = np.exp(-(yn / 0.38) ** 2) * (1 - xn ** 4) ** 2
    a += 0.6 * np.exp(-(yn / 0.08) ** 2) * (1 - xn ** 2)
    return _rgba(np.ones((h, w)), np.clip(a, 0, 1))


def tex_smoke(n: int = 128, seed: int = 3) -> Image.Image:
    rng = np.random.default_rng(seed)
    x, y = _grid(n)
    d = np.hypot(x, y)
    noise = np.zeros((n, n))
    for k, amp in ((4, 0.5), (8, 0.3), (16, 0.2)):
        g = rng.random((k + 1, k + 1))
        noise += amp * np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((n, n), Image.BICUBIC), float) / 255
    a = np.clip(1 - d / 0.95, 0, 1) ** 1.3 * (0.55 + 0.45 * noise)
    a = np.clip((a - 0.12) * 1.5, 0, 1)
    shade = 0.75 + 0.25 * noise
    return _rgba(shade, a)


def tex_coin_frames(n: int = 96, frames: int = 8) -> list[Image.Image]:
    """A gold coin spinning about its vertical axis: width follows |cos|, the
    face darkens edge-on, the rim stays bright."""
    out = []
    y, x = np.mgrid[0:n, 0:n].astype(float)
    c = (n - 1) / 2
    for f in range(frames):
        ang = math.pi * f / frames
        sx = max(abs(math.cos(ang)), 0.12)
        xn = (x - c) / (c * sx)
        yn = (y - c) / c
        d = np.hypot(xn, yn)
        a = np.clip((1 - d) * c * sx * 0.9, 0, 1)
        rim = np.clip(1 - np.abs(d - 0.86) / 0.1, 0, 1)
        face = 0.62 + 0.38 * (0.5 - 0.5 * yn) * abs(math.cos(ang))
        shine = np.exp(-((xn + yn * 0.6 - 0.35 * math.cos(ang)) / 0.22) ** 2) * 0.6
        base = np.stack([1.0 * face, 0.78 * face, 0.22 * face], -1)
        base += rim[..., None] * np.array([0.25, 0.2, 0.05])
        base += shine[..., None] * np.array([1, 0.95, 0.7])
        # edge-on: a thin bright band
        out.append(_rgba(np.clip(base, 0, 1), a))
    return out


TEXTURES = {
    "fx/glow": tex_glow, "fx/ring": tex_ring, "fx/shock": lambda: tex_ring(256, 0.86, 0.035),
    "fx/spark": tex_spark, "fx/streak": tex_streak, "fx/smoke": tex_smoke,
    "fx/ripple": lambda: tex_ring(256, 0.9, 0.04),
}


def ensure_texture(project: Project, name: str) -> tuple[int, int]:
    try:
        im = project.image(name)
    except FileNotFoundError:
        im = TEXTURES[name]()
        project.write_image(name, im)
    return im.size


def ensure_coin(project: Project, frames: int = 8) -> tuple[int, int]:
    try:
        im = project.image("fx/coin_00")
    except FileNotFoundError:
        ims = tex_coin_frames(96, frames)
        for i, im in enumerate(ims):
            project.write_image(f"fx/coin_{i:02d}", im)
        im = ims[0]
    return im.size


# ------------------------------------------------------------------ helpers
class _FX:
    def __init__(self, project: Project, preset: str, name: str | None, parent: str, x: float, y: float,
                 into: str | None, front_of: str | None, behind: str | None, start: float):
        self.p = project
        self.sk: SkeletonData = project.data
        self.name = name or preset
        self.preset = preset
        self.group = self.sk.unique_name(f"fx_{self.name}")
        self.sk.add_bone_world(self.group, parent, x, y, 0, color="FF9E00FF")
        self.anim_name = into or self.name
        self.ab = AnimBuilder(self.sk, self.anim_name, replace=into is None)
        self.slots: list[str] = []
        self.front_of, self.behind = front_of, behind
        self.t0 = start
        self._last_slot: str | None = None

    def bone(self, suffix: str, x: float = 0, y: float = 0, rot: float = 0, parent: str | None = None) -> str:
        nm = self.sk.unique_name(f"{self.group}_{suffix}")
        par = parent or self.group
        pw = self.sk.world()[par]
        wx, wy = pw.to_world(x, y)
        self.sk.add_bone_world(nm, par, wx, wy, pw.rotation + rot)
        return nm

    def slot(self, bone: str, tex: str, size: float, color: str = "FFFFFFFF", blend: str = "additive",
             aspect: float | None = None, sequence: Sequence | None = None) -> str:
        nm = self.sk.unique_name(f"{bone}", "slot")
        s = Slot(name=nm, bone=bone, color=color, blend=blend)
        if self._last_slot is not None:
            self.sk.add_slot(s, after=self._last_slot)
        elif self.behind:
            self.sk.add_slot(s, before=self.behind)
        elif self.front_of:
            self.sk.add_slot(s, after=self.front_of)
        else:
            self.sk.add_slot(s)
        self._last_slot = nm
        if sequence is not None:
            tw, th = ensure_coin(self.p, sequence.count)
        else:
            tw, th = ensure_texture(self.p, tex)
        k = size / max(tw, th)
        h = th * k if aspect is None else size * aspect
        att = RegionAttachment(path=tex if tex != nm else None, width=round(tw * k, 2), height=round(h, 2),
                               sequence=sequence)
        if sequence is not None:
            att.path = "fx/coin_"
        self.sk.set_attachment(nm, "fx", att)
        self.slots.append(nm)
        return nm

    def show(self, slot: str, t_on: float, t_off: float | None) -> None:
        pts = [(r(self.t0 + t_on), "fx")]
        if t_off is not None:
            pts.append((r(self.t0 + t_off), None))
        if self.t0 + t_on > 0:
            pts.insert(0, (0.0, None))
        self.ab.slot_attachment(slot, pts)

    def k(self, bone: str, tl: str, pts, ease="sine_in_out"):
        shifted = [(r(p[0] + self.t0), *p[1:]) for p in pts]
        self.ab.bone(bone, tl, shifted, ease)

    def color(self, slot: str, pts, ease="sine_in_out"):
        shifted = [(r(p[0] + self.t0), *p[1:]) for p in pts]
        self.ab.slot_color(slot, shifted, ease)

    def done(self, **extra) -> dict:
        self.ab.event(self.t0, f"fx_{self.preset}")
        return {"preset": self.preset, "group_bone": self.group, "slots": self.slots,
                "animation": self.anim_name, "event": f"fx_{self.preset}", **extra}


def _hex(c: str | None, default: str) -> str:
    c = (c or default).lstrip("#").upper()
    return c + "FF" if len(c) == 6 else c


def _fade(color: str, a: float) -> str:
    return color[:6] + f"{max(0, min(255, round(a * 255))):02X}"


# ------------------------------------------------------------------- presets
def explosion(fx: _FX, size: float, intensity: float, duration: float, color: str, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    d, I = duration, intensity
    # flash
    b = fx.bone("flash")
    s = fx.slot(b, "fx/glow", size * 0.8, color)
    fx.show(s, 0, d * 0.5)
    fx.k(b, "scale", [(0, 0.3, 0.3, "expo_out"), (d * 0.18, 1.6 * I, 1.6 * I, "quad_in"), (d * 0.5, 2.0 * I, 2.0 * I)])
    fx.color(s, [(0, _fade("FFFFFF", 1), "quad_out"), (d * 0.1, _fade(color, 1), "quad_in"), (d * 0.5, _fade(color, 0))])
    # shockwave
    b = fx.bone("shock")
    s = fx.slot(b, "fx/shock", size * 0.5, color)
    fx.show(s, d * 0.04, d * 0.7)
    fx.k(b, "scale", [(d * 0.04, 0.2, 0.2, "expo_out"), (d * 0.7, 3.2 * I, 3.2 * I)])
    fx.color(s, [(d * 0.04, _fade(color, 1), "quad_in"), (d * 0.7, _fade(color, 0))])
    # smoke (normal blend, behind the sparks)
    for i in range(4):
        ang = rng.uniform(0, 2 * math.pi)
        b = fx.bone(f"smoke{i}", rot=rng.uniform(0, 360))
        s = fx.slot(b, "fx/smoke", size * 0.45, "4A3B35FF", blend="normal")
        fx.show(s, d * 0.08, d)
        R = size * 0.35 * I
        fx.k(b, "translate", [(d * 0.08, 0, 0, "expo_out"), (d, math.cos(ang) * R, math.sin(ang) * R + size * 0.15)])
        fx.k(b, "scale", [(d * 0.08, 0.4, 0.4, "cubic_out"), (d, 1.5 * I, 1.5 * I)])
        fx.color(s, [(d * 0.08, "4A3B3500", "quad_out"), (d * 0.25, "4A3B35B0", "quad_in"), (d, "4A3B3500")])
    # sparks: fly out, fall a little, stretch along their path, burn out
    n = int(8 + 6 * I)
    for i in range(n):
        ang = 2 * math.pi * i / n + rng.uniform(-0.25, 0.25)
        R = size * rng.uniform(0.7, 1.25) * I
        b = fx.bone(f"spark{i}", rot=math.degrees(ang))
        s = fx.slot(b, "fx/spark", size * rng.uniform(0.12, 0.2), color)
        t1 = d * rng.uniform(0.55, 0.85)
        fx.show(s, 0, t1)
        # translate keys are in the PARENT's frame; the bone's own rotation
        # only orients the stretched spark along its path
        fx.k(b, "translate", [(0, 0, 0, "expo_out"), (t1, math.cos(ang) * R, math.sin(ang) * R)])
        fx.k(b, "scale", [(0, 0.6, 0.6, "quad_out"), (d * 0.12, 2.2, 0.7, "quad_in"), (t1, 0.3, 0.3)])
        fx.color(s, [(0, _fade("FFFFFF", 1), "quad_in"), (t1, _fade(color, 0))])
    return fx.done(sparks=n)


def shockwave(fx: _FX, size: float, intensity: float, duration: float, color: str, seed: int) -> dict:
    d, I = duration, intensity
    for i, (delay, w) in enumerate([(0, 1.0), (0.12, 0.7)]):
        b = fx.bone(f"ring{i}")
        s = fx.slot(b, "fx/shock" if i == 0 else "fx/ring", size * 0.5, color)
        fx.show(s, d * delay, d)
        fx.k(b, "scale", [(d * delay, 0.15, 0.15, "expo_out"), (d, 3.0 * I * w, 3.0 * I * w)])
        fx.color(s, [(d * delay, _fade(color, 1), "quad_in"), (d, _fade(color, 0))])
    return fx.done()


def coin_burst(fx: _FX, size: float, intensity: float, duration: float, color: str, seed: int,
               count: int | None = None, shower: bool = False) -> dict:
    """Coins arc up and out (or rain down when ``shower``), spinning through a
    flipbook sequence, then fade. Translate x is linear in time and y is two
    eased segments (rise quad_out, fall quad_in), which is a true parabola."""
    rng = np.random.default_rng(seed)
    d, I = duration, intensity
    n = count or int(6 + 6 * I)
    frames = 8
    for i in range(n):
        b = fx.bone(f"coin{i}")
        cs = size * rng.uniform(0.16, 0.24)
        s = fx.slot(b, "fx/coin_", cs, "FFFFFFFF", blend="normal",
                    sequence=Sequence(count=frames, start=0, digits=2))
        t_start = rng.uniform(0, d * (0.35 if shower else 0.15))
        t_end = d
        fx.show(s, t_start, t_end)
        if shower:
            x0 = rng.uniform(-size, size) * I
            y0 = size * rng.uniform(0.9, 1.3)
            fx.k(b, "translate", [(t_start, x0, y0, "quad_in"), (t_end, x0 + rng.uniform(-30, 30), -size * 1.1)])
        else:
            vx = rng.uniform(-1, 1) * size * 1.1 * I
            apex = size * rng.uniform(0.6, 1.1) * I
            ta = t_start + (t_end - t_start) * rng.uniform(0.32, 0.42)
            fx.ab.bone(b, "translatex", [(r(fx.t0 + t_start), 0), (r(fx.t0 + t_end), vx)], "linear")
            fx.ab.bone(b, "translatey", [(r(fx.t0 + t_start), 0, "quad_out"), (r(fx.t0 + ta), apex, "quad_in"),
                                         (r(fx.t0 + t_end), -size * 0.9)], "linear")
        fx.k(b, "rotate", [(t_start, 0), (t_end, rng.uniform(-120, 120))], "linear")
        fx.color(s, [(t_start, "FFFFFFFF"), (t_end - d * 0.2, "FFFFFFFF", "quad_in"), (t_end, "FFFFFF00")])
        fps = rng.uniform(14, 22)
        fx.ab.sequence(s, "fx", [(r(fx.t0 + t_start), "loop", int(rng.integers(0, frames)), 1 / fps)])
    return fx.done(coins=n)


def ripple(fx: _FX, size: float, intensity: float, duration: float, color: str, seed: int,
           rings: int = 3, perspective: float = 0.42) -> dict:
    """Concentric rings on a water plane, staggered so the loop is seamless:
    ring i runs the same cycle shifted by i/rings. Each ring's alpha is 0 at
    the wrap point, so the jump back to small is invisible."""
    d = duration
    for i in range(rings):
        b = fx.bone(f"ring{i}")
        s = fx.slot(b, "fx/ripple", size, color)
        fx.show(s, 0, None)
        phase = i / rings
        s_keys = _cyclic(lambda u: (0.12 + intensity * u, (0.12 + intensity * u) * perspective), phase, d, 8)
        a_keys = _cyclic(lambda u: (max(0.0, math.sin(math.pi * u)) ** 1.5 * 0.85,), phase, d, 8)
        fx.ab.bone(b, "scale", [(t + fx.t0, v[0], v[1]) for t, v in s_keys], "linear")
        fx.ab.slot_color(s, [(t + fx.t0, _fade(color, v[0])) for t, v in a_keys], "linear")
    return fx.done(loop=True)


def _cyclic(fn, phase: float, d: float, samples: int):
    """Keys over [0, d] for a sawtooth cycle u = (t/d + phase) mod 1, with a
    near-instant jump at the wrap. Values at t=0 and t=d match."""
    keys = []
    for j in range(samples + 1):
        t = j / samples * d
        u = (t / d + phase) % 1
        keys.append((t, fn(u)))
    if 0 < phase < 1:
        tw = (1 - phase) * d
        keys += [(tw - 1e-3, fn(1 - 1e-3 / d)), (tw, fn(0.0))]
    keys.sort(key=lambda k: k[0])
    out = []
    for t, v in keys:
        if out and abs(out[-1][0] - t) < 5e-4:
            continue
        out.append((r(t), v))
    return out


def glow_pulse(fx: _FX, size: float, intensity: float, duration: float, color: str, seed: int, loop: bool = True) -> dict:
    d = duration
    b = fx.bone("glow")
    s = fx.slot(b, "fx/glow", size * 1.3, color)
    fx.show(s, 0, None if loop else d)
    fx.k(b, "scale", [(0, 0.9, 0.9), (d / 2, 0.9 + 0.25 * intensity, 0.9 + 0.25 * intensity), (d, 0.9, 0.9)])
    fx.color(s, [(0, _fade(color, 0.35)), (d / 2, _fade(color, min(1, 0.55 + 0.3 * intensity))), (d, _fade(color, 0.35))])
    return fx.done(loop=loop)


def sparkle(fx: _FX, size: float, intensity: float, duration: float, color: str, seed: int, count: int = 5) -> dict:
    """Twinkles scattered over the area: pop in, rotate a little, pop out."""
    rng = np.random.default_rng(seed)
    d = duration
    for i in range(count):
        ang, rad = rng.uniform(0, 2 * math.pi), size * 0.5 * math.sqrt(rng.uniform(0.05, 1))
        b = fx.bone(f"tw{i}", math.cos(ang) * rad, math.sin(ang) * rad)
        s = fx.slot(b, "fx/spark", size * rng.uniform(0.12, 0.22) * intensity, color)
        t0 = rng.uniform(0, d * 0.6)
        t1 = t0 + d * rng.uniform(0.25, 0.4)
        fx.show(s, t0, min(t1, d))
        tm = (t0 + t1) / 2
        fx.k(b, "scale", [(t0, 0, 0, "back_out"), (tm, 1, 1, "quad_in"), (min(t1, d), 0, 0)])
        fx.k(b, "rotate", [(t0, 0), (min(t1, d), rng.uniform(40, 90))], "linear")
    return fx.done()


def shine_sweep(project: Project, slot: str, duration: float = 0.6, start: float = 0.0, angle: float = 25,
                color: str = "FFFFFFFF", into: str | None = None, name: str | None = None, width: float = 0.35,
                strength: float = 0.85) -> dict:
    """A light band sweeps across one part, clipped to the part's own outline.

    Clipping polygon = the part's hull in its slot bone's space (meshes give
    their real outline; regions their rectangle). The streak slot is drawn
    right after the part with additive blend, and the clip ends on it, so
    nothing else gets clipped (clipping is costly: keep it to one slot)."""
    from .rig import setup_hull_world
    from .mesh import to_local
    sk = project.data
    target = sk.slot(slot)
    hull_w = setup_hull_world(project, slot)
    world = sk.world()
    bw = world[target.bone]
    hull_l = to_local(bw, hull_w)
    if len(hull_l) > 32:  # clipping cost grows with vertex count; simplify
        from .geometry import douglas_peucker_closed
        tol = 0.5
        while len(hull_l) > 32:
            hull_l = douglas_peucker_closed(hull_l, tol)
            tol *= 1.5
    nm = name or f"shine_{slot}"
    clip_slot = sk.unique_name(f"{nm}_clip", "slot")
    sk.add_slot(Slot(name=clip_slot, bone=target.bone), after=slot)
    lo, hi = hull_w.min(0), hull_w.max(0)
    cx, cy = (lo + hi) / 2
    span = float(np.hypot(*(hi - lo)))
    grp = sk.unique_name(f"fx_{nm}")
    sk.add_bone_world(grp, target.bone, cx, cy, 90 + angle)
    streak_slot = sk.unique_name(f"{nm}", "slot")
    sk.add_slot(Slot(name=streak_slot, bone=grp, blend="additive", color=_hex(color, "FFFFFFFF")), after=clip_slot)
    sk.set_attachment(clip_slot, "clip", ClippingAttachment(end=streak_slot, vertexCount=len(hull_l),
                                                            vertices=[round(float(v), 2) for v in hull_l.ravel()]))
    tw, th = ensure_texture(project, "fx/streak")
    sk.set_attachment(streak_slot, "fx", RegionAttachment(path="fx/streak", width=round(span * 1.2, 2),
                                                          height=round(span * width, 2)))
    ab = AnimBuilder(sk, into or nm, replace=into is None)
    t0, t1 = start, start + duration
    pre = [(0.0, None)] if t0 > 0 else []
    ab.slot_attachment(clip_slot, pre + [(r(t0), "clip"), (r(t1), None)])
    ab.slot_attachment(streak_slot, pre + [(r(t0), "fx"), (r(t1), None)])
    # the band lies along the bone's x (world direction 90 + angle); it must travel ACROSS itself, along world
    # direction `angle`. Translate keys live in the PARENT's space, so map the world offsets through its inverse.
    ux, uy = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    ox, oy = bw.to_local(cx, cy)
    ax_, ay_ = bw.to_local(cx - ux * span * 0.75, cy - uy * span * 0.75)
    bx_, by_ = bw.to_local(cx + ux * span * 0.75, cy + uy * span * 0.75)
    ab.bone(grp, "translate", [(r(t0), ax_ - ox, ay_ - oy, "sine_in_out"), (r(t1), bx_ - ox, by_ - oy)])
    c = _hex(color, "FFFFFFFF")
    ab.slot_color(streak_slot, [(r(t0), _fade(c, 0)), (r(t0 + duration * 0.3), _fade(c, strength)),
                                (r(t0 + duration * 0.7), _fade(c, strength)), (r(t1), _fade(c, 0))])
    ab.event(t0, "fx_shine")
    return {"preset": "shine_sweep", "clip_slot": clip_slot, "streak_slot": streak_slot, "bone": grp,
            "clip_vertices": len(hull_l), "animation": into or nm}


PRESETS = {"explosion": explosion, "shockwave": shockwave, "coin_burst": coin_burst,
           "coin_shower": lambda fx, *a, **k: coin_burst(fx, *a, shower=True, **k),
           "ripple": ripple, "glow_pulse": glow_pulse, "sparkle": sparkle}

DEFAULT_DURATION = {"explosion": 0.9, "shockwave": 0.6, "coin_burst": 1.4, "coin_shower": 1.6, "ripple": 2.0,
                    "glow_pulse": 1.0, "sparkle": 1.2}
DEFAULT_COLOR = {"explosion": "FFB040", "shockwave": "FFE6A0", "coin_burst": "FFFFFF", "coin_shower": "FFFFFF",
                 "ripple": "BFE9FF", "glow_pulse": "FFD86B", "sparkle": "FFF6C8"}


def generate(project: Project, preset: str, x: float = 0, y: float = 0, size: float | None = None,
             intensity: float = 1.0, duration: float | None = None, color: str | None = None,
             parent: str = "root", into: str | None = None, start: float = 0.0, name: str | None = None,
             front_of: str | None = None, behind: str | None = None, seed: int = 7, **extra) -> dict:
    """Add an FX preset. ``size`` defaults to 60% of the skeleton's size."""
    if preset == "shine_sweep":
        if "slot" not in extra:
            raise ValueError("shine_sweep needs slot=<part to sweep>")
        return shine_sweep(project, extra.pop("slot"), duration or 0.6, start, color=_hex(color, "FFFFFFFF"),
                           into=into, name=name, **extra)
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r}; one of {sorted([*PRESETS, 'shine_sweep'])}")
    sk = project.data
    if size is None:
        size = 0.6 * max(sk.skeleton.width, sk.skeleton.height, 200)
    fx = _FX(project, preset, name, parent, x, y, into, front_of, behind, start)
    res = PRESETS[preset](fx, size, intensity, duration or DEFAULT_DURATION[preset],
                          _hex(color, DEFAULT_COLOR[preset]), seed, **extra)
    return res
