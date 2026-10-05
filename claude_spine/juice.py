"""Slot-symbol juice presets and the symbol animation contract — the
``juice_apply`` tool's engine.

**The contract.** Every symbol ships the same clip names, so game code never
special-cases a symbol:

    idle          seamless loop, subtle (breathing)
    land          one-shot when the reel stops: drop, squash, overshoot, settle
    win           one-shot payout: anticipation squash, pop, wobble, return
    win_loop      seamless loop while the win is shown
    anticipation  seamless tease loop (scatter/bonus near-miss)
    dim           one-shot that darkens the symbol and holds (non-winning)

Optional: ``scatter_trigger``, ``wild_expand``, ``flip``, ``flip_depth``,
``multiplier_fly``, ``win_big``/``win_mega``/``win_epic``.

**Never fights the artist.** Presets animate two inserted bones only —
``juice_ground`` (pivot at the symbol's base, for squash and drops) and
``juice_core`` (pivot at its centre, for pulses and spins) — which parent the
root's former children without moving them. The artist's own bone keys stay
untouched and still play; juice is layered on top.

Every one-shot ends exactly at the setup pose so clips mix cleanly, and every
clip fires events for the game (``sfx_land``, ``sfx_win``, ...).
"""
from __future__ import annotations

import math

import numpy as np

from .ir import MeshAttachment, RegionAttachment, SkeletonData
from .project import Project
from .rig import insert_parent
from .timeline import AnimBuilder, r

CONTRACT = ["idle", "land", "win", "win_loop", "anticipation", "dim"]
EXTRAS = ["scatter_trigger", "wild_expand", "flip", "flip_depth", "multiplier_fly", "win_big", "win_mega", "win_epic"]


def setup_bounds(project: Project) -> tuple[float, float, float, float]:
    """Axis-aligned bounds of the setup pose in world space (regions + meshes)."""
    from .rig import setup_hull_world
    sk = project.data
    pts = []
    for s in sk.slots:
        if not s.attachment or s.name.startswith("fx_") or s.blend == "additive":
            continue
        try:
            att = sk.attachment(s.name)
        except KeyError:
            continue
        if isinstance(att, (RegionAttachment, MeshAttachment)):
            try:
                pts.append(setup_hull_world(project, s.name))
            except (FileNotFoundError, ValueError):
                if isinstance(att, RegionAttachment):
                    w = sk.world()[s.bone]
                    hw, hh = att.width / 2, att.height / 2
                    pts.append(np.array([w.to_world(att.x + dx, att.y + dy) for dx in (-hw, hw) for dy in (-hh, hh)]))
    if not pts:
        w, h = sk.skeleton.width or 200, sk.skeleton.height or 200
        return (-w / 2, -h / 2, w / 2, h / 2)
    P = np.vstack(pts)
    return (float(P[:, 0].min()), float(P[:, 1].min()), float(P[:, 0].max()), float(P[:, 1].max()))


def ensure_juice_bones(project: Project) -> dict:
    sk = project.data
    if sk.has_bone("juice_ground") and sk.has_bone("juice_core"):
        b = setup_bounds(project)
        return {"ground": "juice_ground", "core": "juice_core", "bounds": b, "created": False}
    b = setup_bounds(project)
    x0, y0, x1, y1 = b
    kids = [c.name for c in sk.children("root")]
    insert_parent(sk, "juice_ground", "root", kids, (x0 + x1) / 2, y0)
    insert_parent(sk, "juice_core", "juice_ground", [c.name for c in sk.children("juice_ground")],
                  (x0 + x1) / 2, (y0 + y1) / 2)
    for n, col in (("juice_ground", "00E1FFFF"), ("juice_core", "00FFA8FF")):
        sk.bone(n).color = col
    return {"ground": "juice_ground", "core": "juice_core", "bounds": b, "created": True}


def _art_slots(sk: SkeletonData) -> list[str]:
    return [s.name for s in sk.slots if s.attachment and s.blend == "normal"]


# --------------------------------------------------------------------- presets
def idle(ab: AnimBuilder, H: float, I: float, d: float, **_):
    a = 0.015 * I
    ab.bone("juice_core", "scale", [(0, 1, 1), (d / 2, 1 - a * 0.5, 1 + a), (d, 1, 1)], "sine_in_out")
    ab.bone("juice_ground", "translatey", [(0, 0), (d / 2, H * 0.006 * I), (d, 0)], "sine_in_out")


def land(ab: AnimBuilder, H: float, I: float, d: float, **_):
    t = lambda f: r(d * f)  # noqa: E731
    ab.bone("juice_ground", "translatey", [(0, H * 0.32 * I, "quad_in"), (t(0.27), 0)], "linear")
    ab.bone("juice_ground", "scale", [
        (0, 0.94, 1.08, "quad_in"),                    # stretched while falling
        (t(0.27), 1 + 0.16 * I, 1 - 0.18 * I, "quad_out"),  # impact squash
        (t(0.5), 1 - 0.05 * I, 1 + 0.07 * I, "sine_in_out"),  # rebound
        (t(0.72), 1 + 0.015 * I, 1 - 0.02 * I, "sine_in_out"),
        (d, 1, 1)], "linear")
    ab.event(t(0.27), "sfx_land")


def win(ab: AnimBuilder, H: float, I: float, d: float, **_):
    t = lambda f: r(d * f)  # noqa: E731
    p = 0.2 * I
    ab.bone("juice_ground", "scale", [(0, 1, 1, "quad_out"), (t(0.08), 1 + 0.06 * I, 1 - 0.08 * I, "back_out"),
                                      (t(0.22), 1, 1)], "linear")
    ab.bone("juice_core", "scale", [(0, 1, 1), (t(0.08), 1, 1, "back_out"), (t(0.24), 1 + p, 1 + p, "sine_in_out"),
                                    (t(0.55), 1 + p * 0.8, 1 + p * 0.8, "cubic_in_out"), (d, 1, 1)], "linear")
    w = 4 * I
    ab.bone("juice_core", "rotate", [(0, 0), (t(0.24), 0, "sine_in_out"), (t(0.34), w, "sine_in_out"),
                                     (t(0.46), -w * 0.7, "sine_in_out"), (t(0.58), w * 0.35, "sine_in_out"),
                                     (t(0.72), 0)], "linear")
    ab.event(t(0.2), "sfx_win")


def win_loop(ab: AnimBuilder, H: float, I: float, d: float, **_):
    p = 0.07 * I
    ab.bone("juice_core", "scale", [(0, 1, 1), (d * 0.5, 1 + p, 1 + p), (d, 1, 1)], "sine_in_out")
    ab.bone("juice_core", "rotate", [(0, 0), (d * 0.25, 1.5 * I), (d * 0.75, -1.5 * I), (d, 0)], "sine_in_out")


def anticipation(ab: AnimBuilder, H: float, I: float, d: float, **_):
    """Tense, buzzing loop: scale held up a little, fast shake whose amplitude
    breathes so it never looks mechanical, seamless at the loop point."""
    n = max(4, int(round(d * 14)))  # ~14 shakes per second
    amp = H * 0.012 * I
    pts = []
    for i in range(n + 1):
        t = d * i / n
        env = 0.6 + 0.4 * math.sin(2 * math.pi * t / d) ** 2
        x = 0 if i in (0, n) else amp * env * (1 if i % 2 else -1)
        pts.append((r(t), r(x, 3)))
    ab.bone("juice_core", "translatex", pts, "sine_in_out")
    s = 1 + 0.05 * I
    ab.bone("juice_core", "scale", [(0, s, s), (d / 2, s + 0.03 * I, s + 0.03 * I), (d, s, s)], "sine_in_out")


def dim(ab: AnimBuilder, H: float, I: float, d: float, darkness: float = 0.45, **_):
    v = max(0.0, min(1.0, 1 - (1 - darkness) * I))
    for s in _art_slots(ab.sk):
        c = ab.sk.slot(s).color
        ab.slot_color(s, [(0, c), (d, _scale_rgb(c, v))], "quad_out")


def _scale_rgb(c: str, v: float) -> str:
    vals = [int(c[i:i + 2], 16) for i in (0, 2, 4)]
    return "".join(f"{round(x * v):02X}" for x in vals) + (c[6:8] if len(c) >= 8 else "FF")


def scatter_trigger(ab: AnimBuilder, H: float, I: float, d: float, **_):
    t = lambda f: r(d * f)  # noqa: E731
    p = 0.35 * I
    ab.bone("juice_ground", "scale", [(0, 1, 1, "quad_out"), (t(0.1), 1 + 0.1 * I, 1 - 0.12 * I, "back_out"),
                                      (t(0.25), 1, 1)], "linear")
    ab.bone("juice_core", "scale", [(0, 1, 1), (t(0.1), 1, 1, "back_out"), (t(0.3), 1 + p, 1 + p),
                                    (t(0.75), 1 + p, 1 + p, "cubic_in_out"), (d, 1, 1)], "linear")
    ab.bone("juice_core", "rotate", [(0, 0), (t(0.3), 0, "sine_in_out"), (t(0.4), 8 * I, "sine_in_out"),
                                     (t(0.5), -8 * I, "sine_in_out"), (t(0.6), 5 * I, "sine_in_out"),
                                     (t(0.7), -3 * I, "sine_in_out"), (t(0.8), 0)], "linear")
    ab.event(t(0.1), "sfx_scatter")


def wild_expand(ab: AnimBuilder, H: float, I: float, d: float, rows: int = 3, **_):
    """Grow to cover ``rows`` reel cells (vertical), hold, return. The game
    usually swaps to a tall art; this is the motion to hand off from."""
    t = lambda f: r(d * f)  # noqa: E731
    ab.bone("juice_core", "scale", [(0, 1, 1, "anticipate"), (t(0.35), 1.08, rows, "sine_in_out"),
                                    (t(0.8), 1.08, rows, "cubic_in_out"), (d, 1, 1)], "linear")
    ab.event(t(0.35), "sfx_wild_expand")


def flip(ab: AnimBuilder, H: float, I: float, d: float, back: str | None = None, full: bool = True, **_):
    """Card flip without depth: scaleX through 0 with a squash at the
    midpoint. ``back`` names a slot holding the reverse face; it shows while
    scaleX is negative (attachment keys) and the draw order swaps so it is on
    top. ``full`` turns 360° (ends on the front), otherwise 180°."""
    sk = ab.sk
    mids = [0.25, 0.75] if full else [0.5]
    pts = [(0, 1, 1, "sine_in")]
    for i, m in enumerate(mids):
        pts.append((r(d * m), 0.0, 1 + 0.06 * I, "sine_out"))
        sign = -1 if i % 2 == 0 else 1
        nxt = d * (0.5 if full and i == 0 else 1.0)
        pts.append((r(nxt), sign, 1, "sine_in"))
    ab.bone("juice_core", "scale", pts, "linear")
    if back:
        sk.slot(back)
        front_att = sk.slot(back).attachment
        keys = [(0, None), (r(d * mids[0]), front_att or back)]
        if full:
            keys.append((r(d * mids[1]), None))
        ab.slot_attachment(back, keys)
    ab.event(r(d * mids[0]), "sfx_flip")


def flip_depth(ab: AnimBuilder, H: float, I: float, d: float, back: str | None = None, **_):
    """Flip that reads as 3D: when a turn rig exists (``turn_ctrl``), the face
    turns away as scaleX closes, the control jumps to the other side at the
    midpoint, and turns back in as scaleX opens on the reverse."""
    sk = ab.sk
    flip(ab, H, I, d, back=back, full=False)
    if sk.has_bone("turn_ctrl"):
        rng = H * 0.12 * I
        ab.bone("turn_ctrl", "translatex", [(0, 0, "sine_in"), (r(d * 0.5 - 1e-3), rng, "stepped"),
                                            (r(d * 0.5), -rng, "sine_out"), (d, 0)], "linear")


def multiplier_fly(ab: AnimBuilder, H: float, I: float, d: float, to: tuple[float, float] = (0, 300), **_):
    """Fly to a world target on an arc, scaling up then shrinking into it."""
    tx, ty = to
    t = lambda f: r(d * f)  # noqa: E731
    ab.bone("juice_core", "scale", [(0, 1, 1, "back_out"), (t(0.2), 1.3, 1.3, "sine_in_out"), (t(0.85), 1.0, 1.0, "quad_in"),
                                    (d, 0.6, 0.6)], "linear")
    ab.bone("juice_ground", "translatex", [(0, 0, "sine_in_out"), (t(0.15), 0, "cubic_in_out"), (d, tx)], "linear")
    lift = abs(tx) * 0.25 + H * 0.3
    ab.bone("juice_ground", "translatey", [(0, 0, "quad_out"), (t(0.15), H * 0.08, "quad_out"),
                                           (t(0.55), (ty + lift) * 0.6, "quad_in"), (d, ty)], "linear")
    ab.event(d, "multiplier_land")


def win_tier(tier: str):
    mult = {"win_big": 1.0, "win_mega": 1.35, "win_epic": 1.7}[tier]

    def f(ab: AnimBuilder, H: float, I: float, d: float, **kw):
        win(ab, H, I * mult, d, **kw)
        ab.event(0, "rollup_start")
        ab.event(r(d * 0.95), "rollup_end")
    return f


PRESETS = {"idle": idle, "land": land, "win": win, "win_loop": win_loop, "anticipation": anticipation, "dim": dim,
           "scatter_trigger": scatter_trigger, "wild_expand": wild_expand, "flip": flip, "flip_depth": flip_depth,
           "multiplier_fly": multiplier_fly, "win_big": win_tier("win_big"), "win_mega": win_tier("win_mega"),
           "win_epic": win_tier("win_epic")}

DURATION = {"idle": 2.0, "land": 0.45, "win": 1.2, "win_loop": 1.0, "anticipation": 0.8, "dim": 0.25,
            "scatter_trigger": 1.6, "wild_expand": 1.2, "flip": 0.8, "flip_depth": 0.8, "multiplier_fly": 0.9,
            "win_big": 1.6, "win_mega": 2.0, "win_epic": 2.6}

# FX layered on by default (when fx=True) — ties juice to the FX library
AUTO_FX = {
    "win": [("glow_pulse", dict(loop=False, intensity=0.8))],
    "scatter_trigger": [("shockwave", {}), ("sparkle", {})],
    "anticipation": [("glow_pulse", dict(loop=True, intensity=0.6))],
    "win_big": [("coin_burst", dict(intensity=0.8))],
    "win_mega": [("coin_burst", dict(intensity=1.1)), ("shockwave", {})],
    "win_epic": [("coin_burst", dict(intensity=1.5)), ("explosion", dict(intensity=0.8))],
}


def apply(project: Project, clips: list[str] | str = "contract", intensity: float = 1.0,
          durations: dict[str, float] | None = None, fx: bool = False, shine_slot: str | None = None,
          merge: bool = False, **options) -> dict:
    """Add juice clips. ``clips="contract"`` adds the six contract clips.

    intensity  0.5 subtle … 1 standard … 1.6 loud. Scales every amplitude.
    fx         also layer matching FX (glow on win, coins on big wins …).
    shine_slot clipped shine sweep across this part inside ``win``.
    merge      add into an existing animation of the same name instead of
               replacing it (juice only keys juice bones, so the artist's keys
               survive).
    options    per-preset extras: back=<slot> (flip), rows=3 (wild_expand),
               to=[x, y] (multiplier_fly), darkness=0.45 (dim).
    """
    from . import fx as fx_mod
    names = CONTRACT if clips == "contract" else ([clips] if isinstance(clips, str) else list(clips))
    bad = [c for c in names if c not in PRESETS]
    if bad:
        raise ValueError(f"unknown clips {bad}; contract {CONTRACT}, extras {EXTRAS}")
    jb = ensure_juice_bones(project)
    x0, y0, x1, y1 = jb["bounds"]
    H = max(y1 - y0, 1.0)
    made = {}
    for c in names:
        d = (durations or {}).get(c, DURATION[c])
        ab = AnimBuilder(project.data, c, replace=not merge)
        if merge:
            for b in ("juice_ground", "juice_core"):
                ab.a.bones.pop(b, None)
        PRESETS[c](ab, H, intensity, d, **options)
        info = {"duration": d, "loop": c in ("idle", "win_loop", "anticipation")}
        if fx and c in AUTO_FX:
            info["fx"] = []
            for preset, kw in AUTO_FX[c]:
                kw = dict(kw)
                k_int = kw.pop("intensity", 1.0) * intensity
                res = fx_mod.generate(project, preset, x=(x0 + x1) / 2, y=(y0 + y1) / 2, size=max(x1 - x0, H),
                                      intensity=k_int, duration=d if preset == "glow_pulse" else None,
                                      parent="juice_core", into=c, name=f"{c}_{preset}",
                                      behind=_art_slots(project.data)[0] if preset == "glow_pulse" and _art_slots(project.data) else None,
                                      **kw)
                info["fx"].append(res["preset"])
        if shine_slot and c in ("win", "win_big", "win_mega", "win_epic", "scatter_trigger"):
            fx_mod.shine_sweep(project, shine_slot, duration=min(0.6, d * 0.5), start=d * 0.22, into=c,
                               name=f"{c}_shine")
            info["shine"] = shine_slot
        made[c] = info
    return {"clips": made, "bones": ["juice_ground", "juice_core"], "bounds": [round(v, 2) for v in jb["bounds"]]}
