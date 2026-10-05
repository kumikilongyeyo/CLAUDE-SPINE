"""Chain rigs: ``rig_serpent`` (fish, eels, snakes, dragon bodies, tentacles) and ``rig_flier`` (birds, bats), plus the
shared machinery the add-on rigs (rig_addons.py) build on: layer lookup by name, chains along a part's own centre
line, exact closed-form keys, and ``merge_clips`` (sub-rig clips merge BY NAME into the host's clips).

Both rigs take a project from import_psd (or the procedural samples below) and recognise parts BY LAYER NAME
(``SERPENT_LAYERS`` / ``FLIER_LAYERS``; case-insensitive, the last ``group/`` part of a flattened PSD name counts).

Exaggerated real physics, as modelled:

* ``rig_serpent`` swims with a travelling wave y(s, t) = A(s) sin(2 pi (s / lambda - f t)) along the body, running
  head -> tail, with an envelope A(s) = A_tail (h + (1 - h) (s / L)^2) that grows toward the tail (carangiform
  fish h ~ 0.15, eels and snakes h ~ 0.5). Speed sets the beat the way fish do it: the body wave travels at
  c = f lambda and the fish swims at U = slip * c (slip ~ 0.7), so f = U / (slip lambda); the tail amplitude follows
  the Strouhal number fish cruise at, St = 2 A_tail f / U ~ 0.3, so A_tail = St slip lambda / 2 (times
  ``exaggerate``). Each bone takes the slope of the wave over its own length (an inextensible chain), the head end
  recoils sideways with y(0, t), and thrust, which peaks twice per tail beat, surges the body at 2 f. ``turn`` is a
  fish C-start: the body curls into a C toward the new heading, the stage-2 tail stroke kicks it back, and the bend
  decays on an exact damped spring. Tentacles swap the head for a base and add reach IK on the tip.
* ``rig_flier`` flaps with a warped sine per joint: the downstroke takes ``downstroke`` (58%) of the beat, every
  joint lags the one before it by ``lag`` degrees of phase (shoulder leads, tip trails), the hand flexes on the
  upstroke and the primaries fan shut, as real wings do to cut drag. Lift accelerates the body up on every
  downstroke, so the body bobs once per beat (lowest at the top of the stroke), while the HEAD stays fixed in the
  rig's frame: a transform constraint pins it to an anchor that does not bob (bird head stabilisation). Folding
  foreshortens the wing (it swings back in depth). Feathers and tail are strands with physics (follow-through).

Clip contract: loops close exactly (same keys at both ends, every period divides the clip), one-shots end exactly on
the setup pose, except ``land``, which ends exactly on the first frame of ``perch`` (the clip it hands over to). Keys
are dense LINEAR samples of closed-form functions of time. Events: ``sfx_swim`` (each tail beat), ``sfx_turn``,
``sfx_reach``, ``sfx_flap`` (each downstroke), ``sfx_takeoff``, ``sfx_land``.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .ir import Key, PhysicsConstraint, RegionAttachment, SkeletonData, Slot, _wrap, new_skeleton
from .mesh import region_pixel_to_local, rig_mesh, to_world
from .project import Project
from .rig import _next_order, add_chain, add_ik, add_transform, reparent_slot, setup_hull_world, strand_centerline
from .timeline import AnimBuilder

# ------------------------------------------------------------------ naming conventions
SERPENT_LAYERS = {
    "body": "REQUIRED. The whole long body (or tentacle) as ONE layer, straight or gently curved.",
    "head": "optional. Rigid head piece over the front of the body; rides the first chain bone.",
    "eye* / jaw / mouth / head_*": "optional. Ride the head (the first chain bone).",
    "fin*": "optional. Every layer whose name starts with 'fin' (fin_dorsal, fin_pectoral_l, ...): a 2-bone strand "
            "with physics on the nearest body bone, rooted at the end nearest the body.",
    "tail_fin / fluke": "optional. Tail fin: a 2-bone strand with physics on the last bone.",
}
FLIER_LAYERS = {
    "body": "REQUIRED. The torso; it bobs on every downstroke.",
    "head": "optional. Stabilised: stays still in the rig's frame while the body bobs.",
    "beak / eye* / head_*": "optional. Ride the head.",
    "wing_l, wing_r": "at least one. Wing art along the arm; the shoulder is the end nearest the body. A 3-bone chain.",
    "wing_l_feather<N>, wing_r_feather<N>": "optional. Primary feathers, fanning off the hand bone; 2-bone strands "
                                            "with physics. (feather_l<N> / feather_r<N> also accepted.)",
    "tail": "optional. Tail fan; a strand with physics.",
}
RIDERS = ("eye", "jaw", "mouth", "head_", "beak", "nose", "pupil")

# ------------------------------------------------------------------ physics presets for the parts (Spine 4.2 fields)
PHYSICS = {
    "fin":     dict(rotate=1, inertia=0.5, strength=110, damping=0.86, mass=1.2, limit=1500),
    "feather": dict(rotate=1, inertia=0.35, strength=230, damping=0.82, mass=0.9, limit=2000),
    "tail":    dict(rotate=1, inertia=0.55, strength=70, damping=0.85, mass=1.6, limit=1500),
    "ear":     dict(rotate=1, inertia=0.45, strength=150, damping=0.84, mass=1.0, limit=1500),
    "fur":     dict(rotate=0.4, x=1, y=1, inertia=0.6, strength=110, damping=0.84, mass=1.0, limit=900),
    "horn":    dict(rotate=0, shearX=1, inertia=0.5, strength=320, damping=0.78, mass=1.0, limit=1200),
}

LOOP_CLIPS = {"idle", "idle_float", "walk", "run", "swim", "fly", "flap", "glide", "perch", "hover", "win_loop",
              "anticipation", "excited", "breathe", "float", "sit", "tail_happy", "tail_alert", "tail_angry",
              "sneak", "trot", "gallop"}


# ------------------------------------------------------------------ layer lookup
def base_name(slot: str) -> str:
    """'Fox/Ear_L' -> 'ear_l': the last part of a flattened PSD name, lower case."""
    return slot.split("/")[-1].strip().lower()


def find_slot(sk: SkeletonData, *names: str) -> str | None:
    for n in names:
        for s in sk.slots:
            if base_name(s.name) == n.lower():
                return s.name
    return None


def find_prefixed(sk: SkeletonData, *prefixes: str, exclude: tuple[str, ...] = ()) -> list[str]:
    """Slots whose base name starts with one of the prefixes, in natural (number-aware) order."""
    out = []
    for s in sk.slots:
        b = base_name(s.name)
        if any(b.startswith(p.lower()) for p in prefixes) and not any(b.startswith(e) for e in exclude):
            out.append(s.name)

    def key(n):
        return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", base_name(n))]
    return sorted(out, key=key)


def find_numbered(sk: SkeletonData, *prefixes: str) -> list[str]:
    """Slots named <prefix><N> or <prefix>_<N>, sorted by N."""
    found = []
    for s in sk.slots:
        b = base_name(s.name)
        for p in prefixes:
            m = re.fullmatch(re.escape(p.lower()) + r"_?(\d+)", b)
            if m:
                found.append((int(m.group(1)), s.name))
                break
    return [n for _, n in sorted(found)]


def find_bone(sk: SkeletonData, *names: str) -> str | None:
    for n in names:
        for b in sk.bones:
            if b.name.lower() == n.lower() or base_name(b.name) == n.lower():
                return b.name
    return None


def missing_error(what: str, missing: list[str], convention: dict, sk: SkeletonData) -> ValueError:
    have = [s.name for s in sk.slots]
    lines = "; ".join(f"{k}: {v}" for k, v in convention.items())
    return ValueError(f"{what}: missing required layer(s) {missing}. Naming convention (case-insensitive): {lines}. "
                      f"Slots in the project: {have}")


# ------------------------------------------------------------------ geometry helpers
def slot_bounds(project: Project, slot: str) -> tuple[float, float, float, float]:
    h = setup_hull_world(project, slot)
    return float(h[:, 0].min()), float(h[:, 1].min()), float(h[:, 0].max()), float(h[:, 1].max())


def slot_center(project: Project, slot: str) -> tuple[float, float]:
    x0, y0, x1, y1 = slot_bounds(project, slot)
    return (x0 + x1) / 2, (y0 + y1) / 2


def _dist_to(p, near) -> float:
    p = np.asarray(p, float)
    near = np.asarray(near, float).reshape(-1, 2)
    if len(near) == 1:
        return float(np.hypot(*(p - near[0])))
    best = math.inf
    for a, b in zip(near[:-1], near[1:]):
        ab = b - a
        t = float(np.clip(np.dot(p - a, ab) / max(np.dot(ab, ab), 1e-9), 0, 1))
        best = min(best, float(np.hypot(*(p - (a + t * ab)))))
    return best


def centerline_world(project: Project, slot: str, n_bones: int, root_near=None, root_end: str | None = None) -> np.ndarray:
    """World joint points (n_bones + 1) along a region layer's own centre line, root first: the end nearest
    ``root_near`` (a point or a polyline), or ``root_end`` (top|bottom|left|right)."""
    sk = project.data
    s = sk.slot(slot)
    att = sk.attachment(slot)
    if not isinstance(att, RegionAttachment):
        raise ValueError(f"{slot!r} is already a {att.type}; this rig starts from the region layer (run it before meshing)")
    im = project.image(project.att_image_name(slot, s.attachment))
    alpha = np.array(im)[:, :, 3]
    f, _ = region_pixel_to_local(att, *im.size)
    wb = sk.world()[s.bone]
    if root_end is not None:
        return to_world(wb, f(strand_centerline(alpha, n_bones, root_end)))
    cands = [to_world(wb, f(strand_centerline(alpha, n_bones, e))) for e in ("top", "bottom", "left", "right")]
    return min(cands, key=lambda c: _dist_to(c[0], root_near) if root_near is not None else 0)


def chain_on_slot(project: Project, slot: str, n_bones: int, parent: str, name: str, root_near=None,
                  root_end: str | None = None, mesh: bool = True, detail: float = 1.0) -> tuple[list[str], np.ndarray]:
    """Bones along a part's own centre line (root first), then a heat-weighted mesh on them. The root is the end
    nearest ``root_near`` (a point or a polyline) unless ``root_end`` (top|bottom|left|right) is given.
    Returns (bones, world joint points)."""
    sk = project.data
    pts = centerline_world(project, slot, n_bones, root_near, root_end)
    bones = add_chain(sk, name, pts.tolist(), parent)
    if mesh:
        rig_mesh(project, slot, bones=bones, detail=detail)
    return bones, pts


def add_phys(sk: SkeletonData, bones: list[str], preset: str, taper: float = 0.15, **over) -> list[str]:
    """One physics constraint per bone from PHYSICS (or rig.PHYSICS_PRESETS); each bone down a chain is looser."""
    from .rig import PHYSICS_PRESETS
    base = PHYSICS.get(preset) or PHYSICS_PRESETS.get(preset)
    if base is None:
        raise ValueError(f"unknown physics preset {preset!r}; one of {sorted({*PHYSICS, *PHYSICS_PRESETS})}")
    out = []
    for i, b in enumerate(bones):
        p = dict(base)
        p.update(over)
        p["strength"] = round(p["strength"] * max(0.3, 1 - taper * i), 2)
        nm = sk.unique_name(f"phys_{b}", "constraint")
        sk.physics.append(PhysicsConstraint(name=nm, order=_next_order(sk), bone=b, **p))
        out.append(nm)
    return out


def frame_bone(sk: SkeletonData, name: str, parent: str, x: float, y: float, rot: float = 0.0, color: str | None = None) -> str:
    nm = sk.unique_name(name)
    kw = {"color": color} if color else {}
    sk.add_bone_world(nm, parent, x, y, rot, **kw)
    return nm


# ------------------------------------------------------------------ exact closed forms
def smooth(t, a, b) -> float:
    u = min(max((t - a) / max(b - a, 1e-9), 0.0), 1.0)
    return u * u * (3 - 2 * u)


def ease_out(u, p=3.0) -> float:
    u = min(max(u, 0.0), 1.0)
    return 1 - (1 - u) ** p


def spring_step(t: float, hz: float, zeta: float) -> float:
    """Unit step response of an underdamped spring: 0 -> 1, first peak exactly 1 + exp(-pi z / sqrt(1 - z^2))."""
    if t <= 0:
        return 0.0
    w0 = 2 * math.pi * hz
    wd = w0 * math.sqrt(1 - zeta * zeta)
    return 1 - math.exp(-zeta * w0 * t) * (math.cos(wd * t) + zeta / math.sqrt(1 - zeta * zeta) * math.sin(wd * t))


def spring_overshoot(zeta: float) -> float:
    return math.exp(-math.pi * zeta / math.sqrt(1 - zeta * zeta))


def spring_kick(t: float, hz: float, zeta: float) -> float:
    """Impulse response, normalised so its first peak is exactly 1: e^(-z w t) sin(wd t) / peak."""
    if t <= 0:
        return 0.0
    w0 = 2 * math.pi * hz
    wd = w0 * math.sqrt(1 - zeta * zeta)
    tp = math.atan2(wd, zeta * w0) / wd
    peak = math.exp(-zeta * w0 * tp) * math.sin(wd * tp)
    return math.exp(-zeta * w0 * t) * math.sin(wd * t) / peak


def fit_period(D: float, period: float) -> tuple[int, float]:
    """Whole cycles that fit a clip of length D: (n, D / n) with D / n as close to ``period`` as possible."""
    n = max(1, int(round(D / max(period, 1e-6))))
    return n, D / n


def times(D: float, rate: float = 30.0, extra: list[float] | None = None) -> list[float]:
    n = max(2, int(math.ceil(D * rate)) + 1)
    ts = set(np.round(np.linspace(0.0, D, n), 6).tolist())
    for e in extra or []:
        if 0 <= e <= D:
            ts.add(round(e, 6))
    return sorted(ts)


def _uniq(pts: list) -> list:
    out: list = []
    for p in pts:
        if out and abs(out[-1][0] - p[0]) < 1e-4:
            out[-1] = p
        else:
            out.append(p)
    return out


REST = {"rotate": (0.0,), "translate": (0.0, 0.0), "scale": (1.0, 1.0), "shear": (0.0, 0.0)}


def key_val(k: Key, fld: str, rest: float) -> float:
    v = getattr(k, fld, None)
    return rest if v is None else float(v)


def put(ab: AnimBuilder, bone: str, tl: str, ts: list[float], fn: Callable, loop: bool = False) -> None:
    """Dense linear keys of fn(t) on a bone timeline. loop=True makes the last key an exact copy of the first.
    If the clip already keys this bone/timeline (two add-ons on one bone), the motions add (scale multiplies)."""
    pts = []
    for t in ts:
        v = fn(t)
        v = v if isinstance(v, tuple) else (v,)
        pts.append((t, *[float(x) for x in v]))
    if loop:
        pts[-1] = (pts[-1][0], *pts[0][1:])
    old = ab.a.bones.get(bone, {}).get(tl)
    if old:
        rest = REST[tl]
        flds = ("value",) if tl == "rotate" else ("x", "y")
        ot = np.array([k.time for k in old])
        ov = [np.array([key_val(k, f, rest[i]) for k in old]) for i, f in enumerate(flds)]
        allt = sorted(set(np.round(np.r_[ot, [p[0] for p in pts]], 4).tolist()))
        nt = np.array([p[0] for p in pts])
        nv = [np.array([p[1 + i] for p in pts]) for i in range(len(flds))]
        merged = []
        for t in allt:
            a = [float(np.interp(t, ot, v)) for v in ov]
            b = [float(np.interp(t, nt, v)) for v in nv]
            merged.append((t, *[(x * y if tl == "scale" else x + y) for x, y in zip(a, b)]))
        pts = merged
    ab.bone(bone, tl, _uniq(pts), "linear")


def event(ab: AnimBuilder, t: float, name: str, **fields) -> None:
    if not any(abs(e.time - round(t, 4)) < 1e-4 and e.name == name and all(getattr(e, k, None) == v for k, v in fields.items())
               for e in ab.a.events):
        ab.event(t, name, **fields)


# ------------------------------------------------------------------ clip merging (sub-rig clips -> host clips)
@dataclass
class ClipSpec:
    """One clip a rig contributes. kind "loop" | "oneshot". build(ab, D, env) writes keys over [0, D]; env(t) is 1
    for a loop merged into a loop (or a new clip) and a fade-in/out window when loop content lands in a host one-shot
    (so the one-shot still ends on setup). create=False: only merged when the host already has a clip of that name."""
    name: str
    kind: str
    length: float
    build: Callable
    create: bool = True


def host_is_loop(name: str) -> bool:
    n = name.lower()
    return n in LOOP_CLIPS or n.endswith("_loop") or n.startswith("idle")


def merge_clips(sk: SkeletonData, specs: list[ClipSpec]) -> dict:
    """Merge clips by name: an existing host clip keeps its length (loops refit their period to divide it exactly,
    one-shots are retimed to it); a missing clip is created at the rig's own length when ``create``."""
    report = {}
    for sp in specs:
        host = sk.animations.get(sp.name)
        Dh = host.duration() if host is not None else 0.0
        if host is None or Dh <= 0:
            if not sp.create:
                continue
            D, mode = sp.length, ("loop" if sp.kind == "loop" else "oneshot")
            created = host is None
        else:
            D = Dh
            created = False
            if sp.kind == "oneshot":
                mode = "oneshot"
            else:
                mode = "loop" if host_is_loop(sp.name) else "window"
        D = round(D, 4)
        if mode == "window":
            env = lambda t, D=D: smooth(t, 0, min(0.25, D / 4)) * (1 - smooth(t, D - min(0.3, D / 4), D))  # noqa: E731
        else:
            env = lambda t: 1.0  # noqa: E731
        ab = AnimBuilder(sk, sp.name, replace=False)
        info = sp.build(ab, D, env) or {}
        report[sp.name] = {"length": D, "mode": mode, "created": created, **info}
    return report


# ------------------------------------------------------------------ constraint-free forward kinematics (QA and tests)
def _interp(keys: list[Key], t: float, flds, rest):
    ts = np.array([k.time for k in keys])
    return [float(np.interp(t, ts, [key_val(k, f, rest[i]) for k in keys])) for i, f in enumerate(flds)]


def sample(sk: SkeletonData, anim: str, bone: str, tl: str, t: float):
    """Keyed value of one bone timeline at t (linear between keys, held outside), rest if not keyed."""
    ks = sk.animations[anim].bones.get(bone, {}).get(tl)
    rest = REST[tl]
    if not ks:
        return rest
    return tuple(_interp(ks, t, ("value",) if tl == "rotate" else ("x", "y"), rest))


def pose_world(sk: SkeletonData, anim: str, t: float):
    """World transforms of every bone at time t from the bone keys alone (no constraints, no physics)."""
    bones = []
    a = sk.animations[anim]
    for b in sk.bones:
        nb = b.model_copy()
        tls = a.bones.get(b.name, {})
        if "rotate" in tls:
            nb.rotation = b.rotation + sample(sk, anim, b.name, "rotate", t)[0]
        if "translate" in tls:
            x, y = sample(sk, anim, b.name, "translate", t)
            nb.x, nb.y = b.x + x, b.y + y
        if "scale" in tls:
            sx, sy = sample(sk, anim, b.name, "scale", t)
            nb.scaleX, nb.scaleY = b.scaleX * sx, b.scaleY * sy
        if "shear" in tls:
            hx, hy = sample(sk, anim, b.name, "shear", t)
            nb.shearX, nb.shearY = b.shearX + hx, b.shearY + hy
        bones.append(nb)
    return SkeletonData(bones=bones).world()


# ================================================================== rig_serpent
@dataclass
class Serpent:
    frame: str                       # aligned with the body at the head end (or tentacle base); never keyed
    drive: str                       # child of frame: recoil, surge, heading
    bones: list[str]                 # the body chain, head (base) -> tail (tip)
    s: list[float]                   # arc position of each joint (len(bones) + 1)
    L: float
    lengths: list[float]
    fins: dict = field(default_factory=dict)
    reach: dict | None = None


def build_serpent(project: Project, slot: str, n_bones: int, parent: str, name: str, root_near=None,
                  root_end: str | None = None, detail: float = 1.0) -> Serpent:
    """The body chain on one layer: frame -> drive -> name1..n, root at the head end (tentacle: the base)."""
    sk = project.data
    if n_bones < 3:
        raise ValueError("n_bones must be >= 3 (a travelling wave needs a few joints)")
    pts = centerline_world(project, slot, n_bones, root_near, root_end)
    d0 = pts[1] - pts[0]
    ang = math.degrees(math.atan2(d0[1], d0[0]))
    frame = frame_bone(sk, name, parent, pts[0][0], pts[0][1], ang, color="00E1FFFF")
    drive = frame_bone(sk, f"{name}_drive", frame, pts[0][0], pts[0][1], ang, color="FFD400FF")
    bones = add_chain(sk, f"{name}_b", pts.tolist(), drive)
    rig_mesh(project, slot, bones=bones, detail=detail)
    lengths = [float(np.hypot(*(pts[i + 1] - pts[i]))) for i in range(n_bones)]
    s = [0.0] + list(np.cumsum(lengths))
    return Serpent(frame, drive, bones, s, float(s[-1]), lengths)


def _wave_angles(sp: Serpent, y_fn, t: float) -> list[float]:
    """Absolute angle (deg) of each bone from the slope of the lateral wave over the bone's own length."""
    ys = [y_fn(s, t) for s in sp.s]
    return [math.degrees(math.atan2(ys[i + 1] - ys[i], sp.lengths[i])) for i in range(len(sp.bones))]


def key_wave(ab: AnimBuilder, sp: Serpent, ts, y_fn, loop: bool, heading=None, surge=None, recoil: float = 1.0) -> None:
    """Keys for a lateral wave y_fn(s, t): each bone rotates by its slope minus its parent's; the drive recoils
    sideways with the head end's own displacement, plus an optional surge (along the body) and heading (deg)."""
    cache = {t: _wave_angles(sp, y_fn, t) for t in ts}
    for i, b in enumerate(sp.bones):
        put(ab, b, "rotate", ts, lambda t, i=i: cache[t][i] - (cache[t][i - 1] if i else 0.0), loop)
    put(ab, sp.drive, "translate", ts, lambda t: ((surge(t) if surge else 0.0), recoil * y_fn(0.0, t)), loop)
    if heading is not None:
        put(ab, sp.drive, "rotate", ts, heading, loop)


def swim_params(L: float, speed: float, wavelength: float, slip: float = 0.7, strouhal: float = 0.3,
                exaggerate: float = 1.5, amp: float | None = None) -> dict:
    """speed (body lengths/s) -> beat frequency and tail amplitude, the way fish do it (see module docstring)."""
    if speed <= 0:
        raise ValueError("speed must be > 0 (body lengths per second)")
    if wavelength <= 0:
        raise ValueError("wavelength must be > 0 (in body lengths)")
    f = speed / (slip * wavelength)
    a_tail = (amp if amp is not None else strouhal * slip * wavelength / 2 * exaggerate) * L
    return {"f": f, "lambda": wavelength * L, "a_tail": a_tail, "slip": slip, "strouhal": strouhal}


def serpent_clips(sp: Serpent, *, speed: float = 1.0, wavelength: float = 1.0, head_amp: float = 0.15, amp=None,
                  exaggerate: float = 1.5, cycles: int = 2, turn_angle: float = 40.0, side: float = 1.0,
                  names: dict | None = None, which=("swim", "idle_float", "turn"), sfx: bool = True) -> list[ClipSpec]:
    """ClipSpecs for swim (exact loop), idle_float (loop) and turn (C-start one-shot); ``names`` renames clips."""
    names = names or {}
    P = swim_params(sp.L, speed, wavelength, exaggerate=exaggerate, amp=amp)
    lam, A_t = P["lambda"], P["a_tail"]
    if not 0 <= head_amp <= 1:
        raise ValueError("head_amp is the head's share of the tail amplitude, 0..1")
    envA = lambda s: A_t * (head_amp + (1 - head_amp) * (s / sp.L) ** 2)  # noqa: E731
    specs = []

    def swim(ab, D, env):
        n, Pd = fit_period(D, 1 / P["f"])
        f = 1 / Pd
        y = lambda s, t: env(t) * envA(s) * math.sin(2 * math.pi * (s / lam - f * t))  # noqa: E731
        surge = lambda t: env(t) * -0.012 * sp.L * math.cos(4 * math.pi * f * t)  # noqa: E731
        ts = times(D, max(30, 14 * f))
        key_wave(ab, sp, ts, y, True, surge=surge)
        if sfx:
            for k in range(n):
                event(ab, k * Pd, "sfx_swim")
        return {"cycles": n, "frequency": round(f, 4), "wavelength": round(lam, 2), "tail_amplitude": round(A_t, 2)}
    if "swim" in which:
        specs.append(ClipSpec(names.get("swim", "swim"), "loop", round(cycles / P["f"], 4), swim))

    def idle(ab, D, env):
        n, Pd = fit_period(D, 1 / (0.4 * P["f"]))       # a slow hover wave at 40% of the swim beat
        f = 1 / Pd
        y = lambda s, t: env(t) * 0.3 * envA(s) * math.sin(2 * math.pi * (s / (1.4 * lam) - f * t))  # noqa: E731
        heave = lambda t: env(t) * 0.035 * sp.L * math.sin(2 * math.pi * t / D)  # noqa: E731   neutral buoyancy: a slow heave
        ts = times(D, 30)
        cache = {t: _wave_angles(sp, y, t) for t in ts}
        for i, b in enumerate(sp.bones):
            put(ab, b, "rotate", ts, lambda t, i=i: cache[t][i] - (cache[t][i - 1] if i else 0.0), True)
        put(ab, sp.drive, "translate", ts, lambda t: (0.0, heave(t) + y(0.0, t)), True)
        put(ab, sp.drive, "rotate", ts, lambda t: env(t) * 2.0 * math.sin(2 * math.pi * t / D + 0.7), True)
        return {"cycles": n, "frequency": round(f, 4)}
    if "idle_float" in which:
        specs.append(ClipSpec(names.get("idle_float", "idle_float"), "loop", round(2 / (0.4 * P["f"]), 4), idle))

    def turn(ab, D, env):
        t1, t2 = 0.18 * D, 0.4 * D
        bend = side * 150.0                              # total C bend (deg) at the end of stage 1
        hz, z = 2.6 / D, 0.32

        def theta(t):
            if t <= t1:
                v = bend * smooth(t, 0, t1)
            elif t <= t2:
                v = bend * (1 - 1.45 * smooth(t, t1, t2))
            else:
                tau = t - t2
                w0 = 2 * math.pi * hz
                v = -0.45 * bend * math.exp(-z * w0 * tau) * math.cos(w0 * math.sqrt(1 - z * z) * tau)
            return v * (1 - smooth(t, 0.82 * D, D))
        head = lambda t: side * turn_angle * smooth(t, 0, 1.3 * t1) * (1 - smooth(t, 0.45 * D, D))  # noqa: E731
        ts = times(D, 60, [t1, t2])
        for i, b in enumerate(sp.bones):
            w = sp.lengths[i] / sp.L if i else 0.0
            put(ab, b, "rotate", ts, lambda t, w=w: theta(t) * w)
        put(ab, sp.drive, "rotate", ts, head)
        if sfx:
            event(ab, t1, "sfx_turn")
        return {"stage1_end": round(t1, 4), "stage2_end": round(t2, 4), "bend": bend}
    if "turn" in which:
        specs.append(ClipSpec(names.get("turn", "turn"), "oneshot", 1.0, turn))
    return specs


def _reach_clip(sp: Serpent, sk: SkeletonData, reach, hook: float = 0.035) -> ClipSpec:
    """Reach: the whole tentacle winds up the other way, then strikes along a constant-curvature arc toward the goal
    (an arc that turns 2 alpha puts its tip at angle alpha from the base) on an exact underdamped spring, so it
    overshoots and settles; the 2-bone IK on the tip follows the chain's own tip, closes the remaining gap to the goal
    and hooks the tip into the curl (the grab). Everything returns to rest, IK mix to 0."""
    ik, target = sp.reach["constraint"], sp.reach["target"]
    w0 = sk.world()
    fw = w0[sp.frame]
    rest = np.array(fw.to_local(*w0[target].head))
    goal = np.array(reach, float) if reach is not None else None    # in the frame's space (x = along the tentacle)
    if goal is not None and (goal.shape != (2,) or not np.all(np.isfinite(goal))):
        raise ValueError("reach is [x, y] in the tentacle's frame (x along the tentacle, from its base)")
    al = math.atan2(goal[1], goal[0]) if goal is not None else math.radians(35.0)
    curl = 2 * math.degrees(al)
    kap = math.radians(curl) / sp.L
    # joint turns of the exact arc: bone i's chord points at kappa (s_i + l_i / 2)
    turns = [math.degrees(kap * (sp.lengths[i - 1] + sp.lengths[i]) / 2 if i else kap * sp.lengths[0] / 2)
             for i in range(len(sp.bones))]

    def tip(k: float) -> np.ndarray:
        """Where the chain's tip is with the arc applied k times (FK, frame space)."""
        tb = {b: t_ * k for b, t_ in zip(sp.bones, turns)}
        cp = SkeletonData(bones=[x.model_copy(update={"rotation": x.rotation + tb.get(x.name, 0.0)}) for x in sk.bones]).world()
        return np.array(cp[sp.frame].to_local(*cp[sp.bones[-1]].tail))
    full = tip(1.0)
    if goal is None:
        goal = full
    gap = goal - full
    side = 1.0 if curl >= 0 else -1.0

    def build(ab, D, env):
        a_end, s_end, h_end = 0.22 * D, 0.42 * D, 0.72 * D
        k = lambda t: (-0.14 * smooth(t, 0, a_end) * (1 - smooth(t, a_end, s_end))       # noqa: E731  wind up the other way
                       + spring_step(t - a_end, 2.4 / D, 0.42) * (1 - smooth(t, h_end, D)))
        g = lambda t: smooth(t, a_end, s_end) * (1 - smooth(t, h_end, D))  # noqa: E731     the grab: IK mix and gap closing
        ts = times(D, 60, [a_end, s_end, h_end])
        kk = {t: k(t) for t in ts}
        tips = {t: tip(kk[t]) for t in ts}

        tang = full - tip(0.95)
        tang = tang / max(float(np.hypot(*tang)), 1e-9)
        inward = side * np.array([-tang[1], tang[0]])                # toward the curl's centre: the tip hooks in
        put(ab, target, "translate", ts, lambda t: tuple(tips[t] + g(t) * (gap + hook * sp.L * inward) - rest))
        for i, b in enumerate(sp.bones):
            put(ab, b, "rotate", ts, lambda t, i=i: turns[i] * kk[t])
        ab.ik(ik, [(t, g(t), curl >= 0) for t in ts], ease="linear")
        event(ab, a_end, "sfx_reach")
        return {"goal": [round(float(v), 2) for v in goal], "ik": ik, "curl": round(curl, 2),
                "overshoot": round(spring_overshoot(0.42), 4), "turns": [round(x, 4) for x in turns]}
    return ClipSpec("reach", "oneshot", 1.6, build)


def rig_serpent(project: Project, slot: str = "", n_bones: int = 8, mode: str = "swim", root_end: str = "auto",
                parent: str = "", name: str = "serpent", speed: float = 1.0, wavelength: float = 0.0,
                head_amp: float = -1.0, amp: float = 0.0, exaggerate: float = 1.5, cycles: int = 2,
                turn_angle: float = 40.0, side: float = 1.0, reach: list[float] | None = None,
                fin_physics: str = "fin", detail: float = 1.0, clips: list[str] | None = None) -> dict:
    """Fish / eel / snake / dragon body / tentacle: one long chain with a travelling wave (see module docstring).

    mode "swim" (head leads; clips swim, idle_float, turn) or "tentacle" (base at the root, adds reach IK on the tip
    and a ``reach`` clip). speed in body lengths/s, wavelength in body lengths (default 1.0 swim, 1.3 tentacle),
    head_amp = head share of the tail amplitude (default 0.15 swim, 0.05 tentacle; 0.5 reads as an eel),
    amp = tail amplitude as a fraction of the length (default: from the Strouhal number x exaggerate)."""
    sk = project.data
    if mode not in ("swim", "tentacle"):
        raise ValueError("mode is swim | tentacle")
    if root_end not in ("auto", "top", "bottom", "left", "right"):
        raise ValueError("root_end is auto | top | bottom | left | right")
    body = sk.slot(slot).name if slot else find_slot(sk, "body", "tentacle")
    if not body:
        raise missing_error("rig_serpent", ["body"], SERPENT_LAYERS, sk)
    parent = parent or "root"
    sk.bone(parent)
    head = find_slot(sk, "head")
    near = None
    if root_end == "auto":
        if head and mode == "swim":
            near = slot_center(project, head)
        else:
            x0, y0, x1, y1 = slot_bounds(project, body)
            near = ((x0 + x1) / 2, y0) if mode == "tentacle" else (x1, (y0 + y1) / 2)
    sp = build_serpent(project, body, n_bones, parent, name, root_near=near,
                       root_end=None if root_end == "auto" else root_end, detail=detail)
    made = {"slot": body, "frame": sp.frame, "drive": sp.drive, "bones": sp.bones, "length": round(sp.L, 2)}
    riders = [head] if head else []
    riders += [s.name for s in sk.slots if base_name(s.name).startswith(RIDERS) and s.name not in riders]
    for r_ in riders:
        reparent_slot(sk, r_, sp.bones[0])
    made["riders"] = riders
    poly = [sk.world()[b].head for b in sp.bones] + [sk.world()[sp.bones[-1]].tail]
    fins = find_prefixed(sk, "fin") + [x for x in (find_slot(sk, "tail_fin", "fluke"),) if x]
    phys = []
    for fs in fins:
        if fs in (body, head):
            continue
        c = slot_center(project, fs)
        if base_name(fs) in ("tail_fin", "fluke"):
            par = sp.bones[-1]
        else:
            par = min(sp.bones, key=lambda b: _dist_to(c, [sk.world()[b].head, sk.world()[b].tail]))
        fb, _ = chain_on_slot(project, fs, 2, par, f"{name}_{base_name(fs)}", root_near=poly)
        phys += add_phys(sk, fb, fin_physics) if fin_physics != "none" else []
        sp.fins[fs] = fb
    made["fins"] = sp.fins
    made["physics"] = phys
    wl = wavelength or (1.0 if mode == "swim" else 1.3)
    ha = head_amp if head_amp >= 0 else (0.15 if mode == "swim" else 0.05)
    if mode == "tentacle" and not amp:
        amp = 0.08                                       # a thin tapered tip kinks at fish amplitudes
    specs = serpent_clips(sp, speed=speed, wavelength=wl, head_amp=ha, amp=amp or None, exaggerate=exaggerate,
                          cycles=cycles, turn_angle=turn_angle, side=side)
    if mode == "tentacle":
        ik = add_ik(sk, [sp.bones[-2], sp.bones[-1]], target_parent=sp.frame, mix=0.0)
        sp.reach = ik
        made["reach_ik"] = ik
        specs.append(_reach_clip(sp, sk, reach))
    if clips is not None:
        bad = [c for c in clips if c not in {s.name for s in specs}]
        if bad:
            raise ValueError(f"unknown clip(s) {bad}; this rig makes {[s.name for s in specs]}")
        specs = [s for s in specs if s.name in clips]
    made["clips"] = merge_clips(sk, specs)
    made["swim"] = {k: round(v, 4) for k, v in swim_params(sp.L, speed, wl, exaggerate=exaggerate, amp=amp or None).items()}
    made["mode"] = mode
    return made


# ================================================================== rig_flier
FOLD = (-62.0, -12.0, -8.0)        # shoulder, elbow, hand (deg, right wing; the left one mirrors): wings down the sides
FOLD_SX = 0.62                     # a folded wing swings back in depth: foreshortened along the arm


@dataclass
class Wing:
    slot: str
    bones: list[str]
    sign: float                      # +1 wing reaches to +x (right), -1 to -x (mirrored rotations)
    feathers: list[tuple[str, float]]   # (feather root bone, angle to the hand: the fan closes by rotating this much)


@dataclass
class Flier:
    frame: str
    body: str
    head: str | None
    anchor: str | None
    wings: list[Wing]
    tail: list[str]
    span: float
    body_h: float


def build_wing(project: Project, slot: str, parent: str, body_c, name: str, feathers: list[str], n_bones: int = 3,
               feather_physics: str = "feather") -> tuple[Wing, list[str]]:
    sk = project.data
    bones, pts = chain_on_slot(project, slot, n_bones, parent, name, root_near=body_c)
    sign = 1.0 if pts[-1][0] >= pts[0][0] else -1.0
    hand = bones[-1]
    w = sk.world()
    seg = [w[hand].head, w[hand].tail]
    out, phys = [], []
    for i, fs in enumerate(feathers):
        fb, fp = chain_on_slot(project, fs, 2, hand, f"{name}_f{i + 1}_", root_near=seg)
        w = sk.world()
        d = _wrap(w[hand].rotation - w[fb[0]].rotation)
        out.append((fb[0], d))
        phys += add_phys(sk, fb[:1], feather_physics) if feather_physics != "none" else []
    return Wing(slot, bones, sign, out), phys


def warp(u: float, d: float) -> float:
    """One wing beat on u in [0, 1): +1 at the top (u = 0), -1 at the bottom (u = d), C1 at both turns. The
    downstroke takes the fraction d of the beat."""
    u = u % 1.0
    return math.cos(math.pi * u / d) if u < d else -math.cos(math.pi * (u - d) / (1 - d))


def upstroke(u: float, d: float) -> float:
    u = u % 1.0
    return math.sin(math.pi * (u - d) / (1 - d)) if u >= d else 0.0


def key_wings(ab: AnimBuilder, fl: Flier, ts, pose, loop: bool) -> None:
    """pose(t) -> (rotations per joint for a RIGHT wing, shoulder scaleX, fan close 0..1 (negative spreads))."""
    cache = {t: pose(t) for t in ts}
    for w in fl.wings:
        for j, b in enumerate(w.bones):
            put(ab, b, "rotate", ts, lambda t, j=j, w=w: w.sign * cache[t][0][min(j, len(cache[t][0]) - 1)], loop)
        put(ab, w.bones[0], "scale", ts, lambda t: (cache[t][1], 1.0), loop)
        for fb, d in w.feathers:
            put(ab, fb, "rotate", ts, lambda t, d=d: 0.85 * cache[t][2] * d, loop)


def key_body(ab: AnimBuilder, fl: Flier, ts, y_fn, loop: bool, squash=None) -> None:
    put(ab, fl.body, "translate", ts, lambda t: (0.0, y_fn(t)), loop)
    if squash is not None:
        put(ab, fl.body, "scale", ts, lambda t: (1 / math.sqrt(max(squash(t), 0.3)), squash(t)), loop)


def flier_clips(fl: Flier, *, flap_hz: float = 2.4, cycles: int = 2, amp=(40.0, 15.0, 20.0), lag: float = 30.0,
                downstroke: float = 0.58, bob: float | None = None, which=("flap", "glide", "perch", "takeoff", "land"),
                names: dict | None = None, sfx: bool = True, fold=FOLD, fold_sx: float = FOLD_SX) -> list[ClipSpec]:
    names = names or {}
    if flap_hz <= 0:
        raise ValueError("flap_hz must be > 0")
    if not 0.2 <= downstroke <= 0.8:
        raise ValueError("downstroke is the fraction of the beat spent on the downstroke, 0.2..0.8 (birds ~0.55-0.6)")
    if len(amp) < 1:
        raise ValueError("amp needs at least the shoulder amplitude")
    amp = tuple(float(a) for a in amp) + (0.0,) * max(0, 3 - len(amp))
    B = bob if bob is not None else 0.11 * fl.body_h
    d = downstroke
    nj = max(len(w.bones) for w in fl.wings) if fl.wings else 3
    specs = []

    def flap_pose(t, f, A=1.0, bias=(0.0, 0.0, 0.0)):
        rots = []
        for j in range(nj):
            u = f * t - j * lag / 360.0
            v = A * amp[min(j, 2)] * warp(u, d) + bias[min(j, 2)]
            if j >= 1:                                   # the elbow and hand flex on the upstroke (cuts drag)
                v -= A * (10.0 if j == 1 else 25.0) * upstroke(u, d)
            rots.append(v)
        close = 0.35 * A * upstroke(f * t - (nj - 1) * lag / 360.0, d)     # primaries fan shut on the upstroke
        return rots, 1.0, close

    def flap(ab, D, env):
        n, Pd = fit_period(D, 1 / flap_hz)
        f = 1 / Pd
        ts = times(D, max(30, 16 * f))
        key_wings(ab, fl, ts, lambda t: (lambda r_: ([env(t) * v for v in r_[0]], 1.0, env(t) * r_[2]))(flap_pose(t, f)), True)
        key_body(ab, fl, ts, lambda t: -env(t) * B * warp(f * t, d), True)
        if sfx:
            for k in range(n):
                event(ab, k * Pd, "sfx_flap")
        return {"beats": n, "frequency": round(f, 4), "downstroke": d, "lag": lag, "bob": round(B, 2)}
    if "flap" in which:
        specs.append(ClipSpec(names.get("flap", "flap"), "loop", round(cycles / flap_hz, 4), flap))

    def glide(ab, D, env):
        ts = times(D, 30)
        sway = lambda t: math.sin(2 * math.pi * t / D)  # noqa: E731
        key_wings(ab, fl, ts, lambda t: ([env(t) * (6 + 3 * sway(t)), env(t) * -3.0, env(t) * (4 + 2 * sway(t + D / 4))], 1.0,
                                         env(t) * -0.15), True)
        key_body(ab, fl, ts, lambda t: env(t) * 0.35 * B * math.sin(2 * math.pi * t / D + 1.1), True)
        return {"sway_period": round(D, 4)}
    if "glide" in which:
        specs.append(ClipSpec(names.get("glide", "glide"), "loop", 2.4, glide))

    def perch_pose(t, D):
        br = 0.06 * math.sin(2 * math.pi * t / D)        # a slow breath in the folded wings
        return [v * (1 + br) for v in fold[:nj]] + [fold[-1]] * max(0, nj - len(fold)), fold_sx, 1.0

    def perch(ab, D, env):
        n, Pd = fit_period(D, 0.8)
        ts = times(D, 30)
        key_wings(ab, fl, ts, lambda t: perch_pose(t, D), True)
        key_body(ab, fl, ts, lambda t: 0.45 * B * math.sin(2 * math.pi * t / Pd), True,
                 squash=lambda t: 1 + 0.025 * math.sin(2 * math.pi * t / Pd))
        if fl.anchor:                                     # the head stays still, with a glance now and then
            put(ab, fl.anchor, "rotate", ts, lambda t: 6.0 * smooth(t, 0.3 * D, 0.38 * D) * (1 - smooth(t, 0.62 * D, 0.7 * D)), True)
        return {"bobs": n, "fold": list(fold[:nj])}
    if "perch" in which:
        specs.append(ClipSpec(names.get("perch", "perch"), "loop", 1.6, perch))

    def takeoff(ab, D, env):
        tc, tl_ = 0.22 * D, 0.32 * D                      # crouch ends, launch (wings at the top of stroke 1)
        f = flap_hz * 1.15
        end = lambda t: 1 - smooth(t, D - 0.28 * D, D)  # noqa: E731
        c = lambda t: 1 - smooth(t, 0.1 * D, tl_)  # noqa: E731     the fold opens through the crouch and launch
        a = lambda t: smooth(t, 0.12 * D, tl_) * (1.3 - 0.3 * smooth(t, tl_, D)) * end(t)  # noqa: E731

        def pose(t):
            fr, _, fc = flap_pose(t - tl_, f, 1.0)
            rots = [c(t) * fold[min(j, 2)] + a(t) * fr[j] for j in range(nj)]
            return rots, 1 - (1 - fold_sx) * c(t), max(c(t), a(t) * fc)
        crouch = lambda t: smooth(t, 0, tc) * (1 - smooth(t, tc, tl_))  # noqa: E731
        y = lambda t: (-0.9 * B * crouch(t) + 1.6 * B * ease_out((t - tc) / (0.3 * D)) * end(t) * (t > tc)  # noqa: E731
                       - B * a(t) * warp(f * (t - tl_), d) * (t > tl_))
        ts = times(D, 60, [tc, tl_])
        key_wings(ab, fl, ts, pose, False)
        key_body(ab, fl, ts, y, False, squash=lambda t: 1 - 0.12 * crouch(t) + 0.06 * smooth(t, tc, tl_) * (1 - smooth(t, tl_, 0.5 * D)))
        if sfx:
            event(ab, tc, "sfx_takeoff")
            k = 0
            while tl_ + k / f < D - 0.2:
                event(ab, tl_ + k / f, "sfx_flap")
                k += 1
        return {"launch": round(tc, 4), "first_downstroke": round(tl_, 4)}
    if "takeoff" in which:
        specs.append(ClipSpec(names.get("takeoff", "takeoff"), "oneshot", 1.4, takeoff))

    def land(ab, D, env):
        td = 0.5 * D                                       # touchdown
        f = flap_hz * 1.8                                  # quick braking strokes with the wings flared forward

        def pose(t):
            br = smooth(t, 0, 0.12 * D) * (1 - smooth(t, 0.36 * D, td))
            fr, _, _ = flap_pose(t, f, 0.45, bias=(18.0, 6.0, 8.0))
            c = smooth(t, td, 0.86 * D)
            rots = [(1 - c) * br * fr[j] + c * fold[min(j, 2)] for j in range(nj)]
            return rots, 1 - (1 - fold_sx) * c, max(c, 0.0) - 0.25 * br
        y = lambda t: -0.8 * B * spring_kick(t - td, 2.6, 0.35) * (1 - smooth(t, 0.8 * D, D))  # noqa: E731   legs absorb it
        sq = lambda t: 1 - 0.1 * spring_kick(t - td, 2.6, 0.35) * (1 - smooth(t, 0.8 * D, D))  # noqa: E731
        ts = times(D, 60, [td])
        key_wings(ab, fl, ts, pose, False)
        key_body(ab, fl, ts, y, False, squash=sq)
        if fl.anchor:
            put(ab, fl.anchor, "rotate", ts, lambda t: 0.0)
        if sfx:
            event(ab, td, "sfx_land")
        return {"touchdown": round(td, 4), "ends_on": names.get("perch", "perch")}
    if "land" in which:
        specs.append(ClipSpec(names.get("land", "land"), "oneshot", 1.3, land))
    return specs


def build_flier(project: Project, body: str, parent: str, name: str, wings: dict[str, tuple[str, list[str]]],
                head: str | None, riders: list[str], tail: str | None, n_wing_bones: int = 3,
                feather_physics: str = "feather", stabilize: bool = True) -> tuple[Flier, dict]:
    sk = project.data
    bx, by = slot_center(project, body)
    x0, y0, x1, y1 = slot_bounds(project, body)
    frame = frame_bone(sk, name, parent, bx, by, 0.0, color="00E1FFFF")
    bbone = frame_bone(sk, f"{name}_body", frame, bx, by, 0.0)
    reparent_slot(sk, body, bbone)
    made: dict = {"frame": frame, "body_bone": bbone, "physics": []}
    hb = anchor = None
    if head:
        hx0, hy0, hx1, hy1 = slot_bounds(project, head)
        px, py = (hx0 + hx1) / 2, hy0 + 0.25 * (hy1 - hy0)          # the neck pivot, low in the head
        hb = frame_bone(sk, f"{name}_head", bbone, px, py, 0.0)
        for r_ in [head, *riders]:
            reparent_slot(sk, r_, hb)
        if stabilize:
            anchor = frame_bone(sk, f"{name}_head_anchor", frame, px, py, 0.0, color="FF3F00FF")
            made["head_constraint"] = add_transform(sk, [hb], anchor, name=sk.unique_name(f"{name}_head_still", "constraint"),
                                                    mix_rotate=1, mix_x=1, mix_y=1, mix_scale_x=0, mix_scale_y=0, mix_shear_y=0)
    ws = []
    span = 0.0
    for side, (wslot, feathers) in wings.items():
        w, ph = build_wing(project, wslot, bbone, (bx, by), f"{name}_{side}", feathers, n_wing_bones, feather_physics)
        ws.append(w)
        made["physics"] += ph
        ww = sk.world()
        span = max(span, abs(ww[w.bones[-1]].tail[0] - bx))
    tb = []
    if tail:
        tb, _ = chain_on_slot(project, tail, 2, bbone, f"{name}_tail", root_near=(bx, by))
        made["physics"] += add_phys(sk, tb, "tail")
    fl = Flier(frame, bbone, hb, anchor, ws, tb, 2 * span, y1 - y0)
    made.update(head_bone=hb, head_anchor=anchor, wings={w.slot: {"bones": w.bones, "feathers": [f for f, _ in w.feathers],
                                                                  "side": "right" if w.sign > 0 else "left"} for w in ws},
                tail=tb, span=round(fl.span, 2))
    return fl, made


def flier_layers(sk: SkeletonData) -> tuple[dict, str | None, list[str], str | None, list[str]]:
    wings = {}
    for side in ("l", "r"):
        ws = find_slot(sk, f"wing_{side}")
        if ws:
            wings[side] = (ws, find_numbered(sk, f"wing_{side}_feather", f"feather_{side}"))
    head = find_slot(sk, "head")
    riders = [s.name for s in sk.slots if base_name(s.name).startswith(RIDERS) and s.name != head]
    tail = find_slot(sk, "tail")
    missing = [] if wings else ["wing_l or wing_r"]
    return wings, head, riders, tail, missing


def rig_flier(project: Project, parent: str = "", name: str = "flier", flap_hz: float = 2.4, cycles: int = 2,
              amp: list[float] | None = None, lag: float = 30.0, downstroke: float = 0.58, bob: float = -1.0,
              stabilize_head: bool = True, feather_physics: str = "feather", clips: list[str] | None = None) -> dict:
    """Bird / flier: 3-bone wings with a feather fan, flap (lead -> lag phase, 58% downstroke, upstroke flex), glide,
    perch (folded, body bobs, head still), takeoff (crouch, launch, power strokes; ends on setup) and land (flare,
    braking strokes, touchdown on an exact spring; ends on perch's first frame). The head is stabilised in the
    rig's frame by a transform constraint to a non-bobbing anchor (stabilize_head)."""
    sk = project.data
    body = find_slot(sk, "body")
    wings, head, riders, tail, missing = flier_layers(sk)
    if not body:
        missing = ["body"] + missing
    if missing:
        raise missing_error("rig_flier", missing, FLIER_LAYERS, sk)
    parent = parent or "root"
    sk.bone(parent)
    fl, made = build_flier(project, body, parent, name, wings, head, riders, tail, feather_physics=feather_physics,
                           stabilize=stabilize_head)
    specs = flier_clips(fl, flap_hz=flap_hz, cycles=cycles, amp=tuple(amp) if amp else (40.0, 15.0, 20.0), lag=lag,
                        downstroke=downstroke, bob=None if bob < 0 else bob)
    if clips is not None:
        bad = [c for c in clips if c not in {s.name for s in specs}]
        if bad:
            raise ValueError(f"unknown clip(s) {bad}; this rig makes {[s.name for s in specs]}")
        specs = [s for s in specs if s.name in clips]
    made["clips"] = merge_clips(sk, specs)
    made["riders"] = riders
    return made


# ================================================================== procedural samples
class Sheet:
    """Draw parts on one canvas (like PSD layers) and place each, cropped to its content, at its world position.
    World (0, 0) sits at pixel (ox, oy); +y is up."""

    def __init__(self, project: Project, W: int, H: int, ox: float, oy: float):
        self.p, self.sk, self.W, self.H, self.ox, self.oy = project, project.data, W, H, ox, oy

    def px(self, x, y):
        return self.ox + x, self.oy - y

    def pts(self, pts):
        return [self.px(x, y) for x, y in pts]

    def add(self, slot: str, im: Image.Image, bone: str = "root") -> str:
        bb = im.getchannel("A").getbbox()
        if bb is None:
            raise ValueError(f"part {slot!r} drew nothing")
        bb = (max(bb[0] - 2, 0), max(bb[1] - 2, 0), min(bb[2] + 2, im.width), min(bb[3] + 2, im.height))
        crop = im.crop(bb)
        cx, cy = (bb[0] + bb[2]) / 2 - self.ox, self.oy - (bb[1] + bb[3]) / 2
        self.p.write_image(slot, crop)
        wb = self.sk.world()[bone]
        lx, ly = wb.to_local(cx, cy)
        self.sk.slots.append(Slot(name=slot, bone=bone, attachment=slot))
        self.sk.set_attachment(slot, slot, RegionAttachment(x=round(lx, 2), y=round(ly, 2), width=crop.width,
                                                            height=crop.height, rotation=round(-wb.rotation, 3)))
        return slot

    def paint(self, shape: Callable, top, bottom, outline=(34, 22, 40), ow: float = 3.0, spots=None, blur: float = 0.8):
        """shape(draw, inset) fills 255 shrunk by inset. Vertical gradient top -> bottom over the part's own box."""
        W, H = self.W, self.H
        mask = Image.new("L", (W, H), 0)
        shape(ImageDraw.Draw(mask), 0.0)
        bb = mask.getbbox() or (0, 0, W, H)
        inner = Image.new("L", (W, H), 0)
        shape(ImageDraw.Draw(inner), ow)
        g = np.clip((np.arange(H) - bb[1]) / max(bb[3] - bb[1], 1), 0, 1)[:, None, None]
        grad = (np.array(top, float)[None, None] * (1 - g) + np.array(bottom, float)[None, None] * g).repeat(W, 1)
        base = Image.new("RGBA", (W, H), tuple(outline) + (255,))
        base.paste(Image.fromarray(grad.astype(np.uint8)), (0, 0), inner)
        if spots:
            sp = Image.new("L", (W, H), 0)
            spots(ImageDraw.Draw(sp))
            sp = Image.composite(sp, Image.new("L", (W, H), 0), inner)
            col = Image.new("RGBA", (W, H), tuple(spots.color) + (255,)) if hasattr(spots, "color") else Image.new("RGBA", (W, H), (255, 250, 240, 255))
            base.paste(col, (0, 0), sp)
        base.putalpha(mask.filter(ImageFilter.GaussianBlur(blur)))
        return base


def spline(pts, hw, n: int = 24):
    """Catmull-Rom through the control points (and linear half-widths), for smooth tapered parts."""
    P = np.asarray(pts, float)
    P = np.vstack([2 * P[0] - P[1], P, 2 * P[-1] - P[-2]])
    out = []
    segs = len(pts) - 1
    for k in range(n):
        u = k / (n - 1) * segs
        i = min(int(u), segs - 1)
        t = u - i
        p0, p1, p2, p3 = P[i], P[i + 1], P[i + 2], P[i + 3]
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    w = np.interp(np.linspace(0, segs, n), np.arange(len(hw)), hw)
    return [tuple(map(float, q)) for q in out], [float(x) for x in w]


def strip_poly(sh: Sheet, pts, hw) -> list[tuple[float, float]]:
    """Outline of a tapered strip along world points with half-widths hw (pixel coords)."""
    P = np.asarray(pts, float)
    n = len(P)
    left, right = [], []
    for i in range(n):
        a, b = P[max(i - 1, 0)], P[min(i + 1, n - 1)]
        t = (b - a) / max(np.hypot(*(b - a)), 1e-9)
        nrm = np.array([-t[1], t[0]])
        left.append(sh.px(*(P[i] + nrm * hw[i])))
        right.append(sh.px(*(P[i] - nrm * hw[i])))
    return left + right[::-1]


def strip_shape(sh: Sheet, pts, hw, caps: bool = True):
    def shape(d, o):
        d.polygon(strip_poly(sh, pts, [max(w - o, 0.6) for w in hw]), fill=255)
        if caps:
            for p, w in ((pts[0], hw[0]), (pts[-1], hw[-1])):
                r_ = max(w - o, 0.6)
                x, y = sh.px(*p)
                d.ellipse([x - r_, y - r_, x + r_, y + r_], fill=255)
    return shape


def ellipse_poly(sh: Sheet, cx, cy, rx, ry, ang_deg=0.0, n=48):
    a = math.radians(ang_deg)
    out = []
    for k in range(n):
        t = 2 * math.pi * k / n
        x, y = rx * math.cos(t), ry * math.sin(t)
        out.append(sh.px(cx + x * math.cos(a) - y * math.sin(a), cy + x * math.sin(a) + y * math.cos(a)))
    return out


def feather_shape(sh: Sheet, root, ang_deg, length, width):
    """A primary feather: rounded root, widest at 40%, pointed rounded tip, along ang_deg from root."""
    a = math.radians(ang_deg)
    ux, uy = math.cos(a), math.sin(a)
    pts = [(root[0] + ux * length * s, root[1] + uy * length * s) for s in np.linspace(0, 1, 12)]
    hw = [width * (0.35 + 0.65 * math.sin(math.pi * min(s * 1.25, 1.0)) ** 0.7) * (1 - 0.6 * s ** 3) for s in np.linspace(0, 1, 12)]
    return strip_shape(sh, pts, hw)


def make_sample_serpent(out_dir: str | Path, kind: str = "fish", name: str = "") -> Project:
    """kind "fish": a koi (body, head, eye, fin_dorsal, fin_pectoral, tail_fin), head to the right.
    kind "tentacle": one tapered tentacle with suckers, base at the bottom."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    if kind not in ("fish", "tentacle"):
        raise ValueError("kind is fish | tentacle")
    if kind == "tentacle":
        sk = new_skeleton(width=300, height=640)
        p = Project(out / f"{name or 'tentacle'}.json", sk)
        sh = Sheet(p, 300, 640, 150, 620)
        ys = np.linspace(0, 590, 30)
        pts = [(28 * math.sin(y / 170), y) for y in ys]
        hw = [44 * (1 - y / 640) ** 1.1 + 5 for y in ys]
        suck = lambda d: [d.ellipse([sh.px(x + w * 0.45, y)[0] - 0.22 * w, sh.px(x, y)[1] - 0.22 * w,  # noqa: E731
                                     sh.px(x + w * 0.45, y)[0] + 0.22 * w, sh.px(x, y)[1] + 0.22 * w], fill=255)
                          for (x, y), w in list(zip(pts, hw))[1:-3:2]]
        sh.add("body", sh.paint(strip_shape(sh, pts, hw), (190, 90, 210), (110, 40, 150), spots=suck))
        p.save()
        return p
    sk = new_skeleton(width=900, height=360)
    p = Project(out / f"{name or 'koi'}.json", sk)
    sh = Sheet(p, 900, 360, 450, 180)
    xs = np.linspace(330, -300, 40)
    s_ = (330 - xs) / 630
    pts = [(x, 6 * math.sin(3 * s)) for x, s in zip(xs, s_)]
    hw = [max(22.0, 52 * math.sin(math.pi * min(0.18 + s * 0.95, 1.0)) ** 0.8 * (1 - 0.5 * s ** 1.6)) for s in s_]

    class Spots:
        color = (255, 248, 236)

        def __call__(self, d):
            for cx, cy, r_ in ((210, 20, 26), (90, -8, 30), (-40, 14, 22), (-150, -4, 16), (150, -24, 14)):
                d.ellipse([sh.px(cx - r_, 0)[0], sh.px(0, cy + r_)[1], sh.px(cx + r_, 0)[0], sh.px(0, cy - r_)[1]], fill=255)
    orange, deep = (255, 128, 40), (210, 70, 20)
    sh.add("tail_fin", sh.paint(lambda d, o: d.polygon(sh.pts([(-286 - o, 5), (-440 + o, 54 - o), (-402 + o, 4), (-440 + o, -48 + o)]), fill=255),
                                (255, 170, 90), (220, 90, 40)))
    sh.add("fin_dorsal", sh.paint(lambda d, o: d.polygon(sh.pts([(120 - o, 44), (40, 105 - o * 1.5), (-60 + o, 40)]), fill=255),
                                  (255, 160, 80), (230, 100, 40)))
    sh.add("body", sh.paint(strip_shape(sh, pts, hw), orange, deep, spots=Spots()))
    sh.add("fin_pectoral", sh.paint(lambda d, o: d.polygon(sh.pts([(225 - o, -28), (150, -100 + o * 1.5), (178 + o, -30)]), fill=255),
                                    (255, 175, 95), (225, 105, 45)))
    head_pts = [(x, y) for x, y in pts[:5]]
    sh.add("head", sh.paint(strip_shape(sh, head_pts, [w * 0.97 for w in hw[:5]]), (255, 150, 60), (225, 85, 25)))
    eye = Image.new("RGBA", (900, 360), (0, 0, 0, 0))
    de = ImageDraw.Draw(eye)
    ex, ey = sh.px(292, 16)
    de.ellipse([ex - 10, ey - 10, ex + 10, ey + 10], fill=(30, 20, 30, 255))
    de.ellipse([ex - 6, ey - 7, ex - 1, ey - 2], fill=(255, 255, 255, 255))
    sh.add("eye", eye)
    p.save()
    return p


def make_sample_flier(out_dir: str | Path, name: str = "bird", feathers: int = 4) -> Project:
    """A front-view bird: tail, wings (wing_l/_r with wing_<side>_feather1..N primaries), body, head, beak, eyes."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sk = new_skeleton(width=860, height=560)
    p = Project(out / f"{name}.json", sk)
    sh = Sheet(p, 860, 560, 430, 300)
    blue, deep = (90, 150, 235), (40, 80, 170)
    sh.add("tail", sh.paint(lambda d, o: d.polygon(sh.pts([(-22 + o, -70), (22 - o, -70), (62 - o, -190 + o), (0, -175 + o), (-62 + o, -190 + o)]), fill=255),
                            (70, 120, 210), (30, 60, 140)))
    for side, sg in (("l", -1), ("r", 1)):
        arm = [(sg * 40, 40), (sg * 130, 78), (sg * 225, 96), (sg * 300, 92)]
        hand = (np.array(arm[2]), np.array(arm[3]))
        for i in range(feathers):
            k = i / max(feathers - 1, 1)
            root = hand[0] + (hand[1] - hand[0]) * (0.15 + 0.85 * k) + np.array([0, -14])
            ang = (-58 + 50 * k) if sg > 0 else (180 + 58 - 50 * k)
            sh.add(f"wing_{side}_feather{i + 1}", sh.paint(feather_shape(sh, root, ang, 120 + 40 * k, 15), (120, 175, 245), (55, 95, 190), ow=2.5))
        hw = [36, 30, 24, 12]
        sh.add(f"wing_{side}", sh.paint(strip_shape(sh, arm, hw), (130, 185, 250), (60, 110, 200)))
    sh.add("body", sh.paint(lambda d, o: d.polygon(ellipse_poly(sh, 0, 0, 78 - o, 98 - o), fill=255), blue, deep,
                            spots=type("S", (), {"color": (245, 235, 215), "__call__": lambda self, d: d.polygon(ellipse_poly(sh, 0, -14, 48, 70), fill=255)})()))
    sh.add("head", sh.paint(lambda d, o: d.polygon(ellipse_poly(sh, 0, 122, 56 - o, 52 - o), fill=255), (110, 165, 245), (60, 110, 205)))
    sh.add("beak", sh.paint(lambda d, o: d.polygon(sh.pts([(-14 + o, 112), (14 - o, 112), (0, 88 + o)]), fill=255), (255, 200, 60), (230, 140, 20), ow=2))
    for side, sg in (("l", -1), ("r", 1)):
        eye = Image.new("RGBA", (860, 560), (0, 0, 0, 0))
        de = ImageDraw.Draw(eye)
        ex, ey = sh.px(sg * 22, 132)
        de.ellipse([ex - 10, ey - 12, ex + 10, ey + 12], fill=(25, 20, 35, 255))
        de.ellipse([ex - 6, ey - 8, ex - 1, ey - 3], fill=(255, 255, 255, 255))
        sh.add(f"eye_{side}", eye)
    p.save()
    return p
