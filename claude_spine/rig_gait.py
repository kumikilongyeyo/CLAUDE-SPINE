"""Gaits and the quadruped rig: footfall tables turned into planted-foot IK paths, and a one-call rig + clip set for
four-legged animals.

GAIT (``gait()``, generic: any rig that has IK targets for its feet and one body bone)
-------------------------------------------------------------------------------------
A gait is a footfall table: each leg's PHASE (when in the cycle its foot touches down, 0..1) and the DUTY FACTOR
(the fraction of the cycle a foot spends on the ground). ``GAITS`` holds the classic ones: walk (4-beat lateral
sequence LH LF RH RF), trot (diagonal pairs), pace (lateral pairs), canter (3-beat), gallop (rotary: LH RH RF LF, with
an extended and a gathered flight), bound (hind pair, fore pair), the insect alternating tripod (L1 R2 L3 / R1 L2 R3)
and metachronal wave for six legs, and biped walk / run.

Modelled, then exaggerated:

* Speed sets stride AND frequency together, Froude style. Animals of any size move alike at equal Froude number
  Fr = v^2 / (g L), and in practice stride frequency grows like the square root of relative speed:
  ``f = c_gait * sqrt(v / L)`` (v in units/s, L = hip height in units, so v / L is leg lengths per second), and the
  stride is whatever the speed leaves: ``S = v / f = sqrt(v L) / c_gait``. Double the speed and both the stride and
  the cadence grow by sqrt(2). The period is rounded to 1 ms so the clip is an exact number of milliseconds.
* Stance: the foot is planted. The cycle is IN PLACE (the game scrolls the world at ``speed``), so a planted foot
  moves backwards at exactly ``speed`` in one straight linear segment keyed only at touch-down and lift-off: the
  runtime's linear interpolation is then exact and the foot cannot slide by a pixel against the ground.
* Swing: the foot covers the stride in the GROUND frame with a minimum-jerk profile (10s^3 - 15s^4 + 6s^5: zero
  velocity and acceleration at both ends), so its velocity matches the stance velocity at lift-off and touch-down
  (no pop), lifted on a clearance arc 16 (q(1-q))^2, q = s^0.8 (peak = ``clearance`` slightly early, soft landing),
  with a toe roll (the paw curls back in swing; 0 in stance so the planted foot never rotates).
* Body: every planted leg pushes with a half-sine ground reaction force sin(pi u) (u = stance progress). Walks vault
  over the stance leg (inverted pendulum: body HIGHEST when the load peaks); trots, gallops, bounds and runs bounce
  on it (spring-mass: body LOWEST when the load peaks). The setup pose is taken as the tallest stance, so the bob
  only lowers the body (0 .. -2 ``bob``, from the normalised summed load) and a planted leg is never stretched past
  its setup length by it; pitch = ``pitch`` degrees from hind load minus fore load (nose up while the hinds push).
  Exaggerated amplitudes.
* Reach: the hip-to-foot distance is checked over the whole cycle. If the stride would over-stretch a leg (the IK
  would let the foot slide), the stance is first moved under the hip (where a leg is shortest), then the hips are
  carried lower (up to 6% of the leg length: locomotion runs lower
  than standing), then the frequency is raised (shorter, quicker steps: what a real animal does) and the bob and
  pitch are eased. The result reports ``sink`` / ``frequency_raised``.

Every touch-down fires ``sfx_step`` with the leg's name in the event's string field. Loops are exact (first key ==
last key on every timeline). ``plan_gait`` returns the maths (``GaitPlan``: foot paths, loads, bob, pitch, contacts)
for other rigs to couple their own parts to the footfalls (the quadruped's head bob and tail swing do).

QUADRUPED (``rig_quadruped()``)
-------------------------------
Recognises parts by layer name (``QUADRUPED_LAYERS``) in a project from import_psd or ``make_sample_quadruped``.
The animal faces +x (right) or -x (detected from the head); _R parts are the near side (in front of the body),
_L the far side. Builds:

* a spine: ``q_body`` (gait bob / pitch pivot at the torso centre) with ``spine_back -> hips`` and
  ``spine_front -> shoulders``; the body art becomes a mesh weighted to the four;
* legs: thigh/upper arm, shin/forearm and (digitigrade, unguligrade) the metapodial, read from the art's own axes
  (capsule caps give the joint centres). ``leg_type``: plantigrade (2-bone IK to the ankle, flat foot), digitigrade
  (2-bone IK to a hock/carpus target hanging off the foot target + a 1-bone IK on the metapodial, toe roll 40 deg),
  unguligrade (same, long cannon, a ``pastern`` bone for the hoof, fetlock roll 55 deg). A missing metapodial layer
  is not an error: the extra bone is made by splitting the lower leg and its art becomes a mesh bent by both bones.
  Foot targets live under root, so feet stay planted whatever the body does; each foot bone copies its target's
  rotation (transform constraint), so a planted foot never rotates;
* neck (2 bones) and head, eye bones (blinks), and strands with Spine 4.2 physics: ears, tail (4 bones, loose
  and wild: the tail is the emotional readout), mane, fur tufts, wattles.

Clips (``QUADRUPED_CLIPS``): idle (breath, ear flicks, tail swishes and blinks on a seeded Poisson timer, exact loop),
alert (ears forward, head up, tail up on an exact underdamped spring step, frozen, then released), walk / trot /
gallop / bound (via ``gait``; the neck counter-rotates the body pitch with a lag and nods to each fore footfall, the
head stabilises its gaze, the tail swings once per stride), pounce (crouch, butt wiggle, heels-off launch, fore paws
strike, pin, step back), sleep (sphinx pose, slow deep breath, eyes shut, exact loop) and shake (a wet-dog shake:
a damped 4.5 Hz sine travelling head to tail along neck, spine and tail). Loops close exactly; one-shots end exactly
on the setup pose; the artist's setup never moves. Events: ``sfx_step`` (string = foot) on every footfall,
``sfx_idle`` (string = ear_flick / tail_swish / blink), ``sfx_alert``, ``sfx_pounce``, ``sfx_sleep`` (each breath),
``sfx_shake``.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .ir import RegionAttachment, SkeletonData, Slot, new_skeleton
from .mesh import region_pixel_to_local, rig_mesh, to_world
from .project import Project
from .rig import add_chain, add_ik, add_physics, add_transform, reparent_slot, rig_strand
from .timeline import AnimBuilder

# ======================================================================= gait tables
QUAD_ROLES = ("LF", "RF", "LH", "RH")
HEX_ROLES = ("L1", "L2", "L3", "R1", "R2", "R3")
BIPED_ROLES = ("L", "R")
KIND_ROLES = {"quadruped": QUAD_ROLES, "hexapod": HEX_ROLES, "biped": BIPED_ROLES}
FRONT_ROLES = {"LF", "RF", "L1", "R1"}
HIND_ROLES = {"LH", "RH", "L3", "R3"}

# phases: touch-down time of each foot as a fraction of the cycle. duty: fraction of the cycle on the ground.
# mech: "vault" (inverted pendulum, body highest at mid-stance) or "bounce" (spring-mass, lowest at mid-stance).
# c: frequency coefficient in f = c sqrt(v / L). speed: default speed in leg lengths per second.
# clearance / bob: fractions of the leg length L; pitch: degrees. roll: toe-roll scale.
GAITS: dict[str, dict] = {
    "walk":   dict(kind="quadruped", phases=dict(LH=0.0, LF=0.25, RH=0.5, RF=0.75), duty=0.65, mech="vault",
                   c=1.5, speed=1.0, clearance=0.12, bob=0.022, pitch=1.5,
                   what="4-beat lateral sequence walk (LH LF RH RF), three feet down most of the time"),
    "trot":   dict(kind="quadruped", phases=dict(LF=0.0, RH=0.0, RF=0.5, LH=0.5), duty=0.42, mech="bounce",
                   c=1.6, speed=2.2, clearance=0.2, bob=0.035, pitch=1.5,
                   what="2-beat diagonal pairs with two short flights"),
    "pace":   dict(kind="quadruped", phases=dict(LF=0.0, LH=0.0, RF=0.5, RH=0.5), duty=0.45, mech="bounce",
                   c=1.6, speed=2.0, clearance=0.16, bob=0.03, pitch=1.0,
                   what="2-beat lateral pairs (camels, giraffes, tired dogs)"),
    "canter": dict(kind="quadruped", phases=dict(RH=0.0, LH=0.3, RF=0.3, LF=0.55), duty=0.38, mech="bounce",
                   c=1.4, speed=3.0, clearance=0.24, bob=0.05, pitch=5.0,
                   what="3-beat: RH, then LH + RF together, then the leading LF, one flight"),
    "gallop": dict(kind="quadruped", phases=dict(LH=0.0, RH=0.1, RF=0.45, LF=0.55), duty=0.28, mech="bounce",
                   c=1.4, speed=4.5, clearance=0.28, bob=0.05, pitch=7.0,
                   what="rotary gallop LH RH RF LF with extended and gathered flights"),
    "bound":  dict(kind="quadruped", phases=dict(LH=0.0, RH=0.0, LF=0.45, RF=0.45), duty=0.32, mech="bounce",
                   c=1.35, speed=3.5, clearance=0.3, bob=0.07, pitch=9.0,
                   what="hind pair, then fore pair: the rabbit / weasel bound"),
    "tripod": dict(kind="hexapod", phases=dict(L1=0.0, R2=0.0, L3=0.0, R1=0.5, L2=0.5, R3=0.5), duty=0.55,
                   mech="vault", c=2.5, speed=1.5, clearance=0.2, bob=0.015, pitch=0.5,
                   what="insect alternating tripod: L1 R2 L3 then R1 L2 R3"),
    "wave":   dict(kind="hexapod", phases=dict(L3=0.0, L2=1 / 6, L1=2 / 6, R3=0.5, R2=0.5 + 1 / 6, R1=0.5 + 2 / 6),
                   duty=0.75, mech="vault", c=2.0, speed=0.8, clearance=0.18, bob=0.01, pitch=0.3,
                   what="slow metachronal wave, back to front on each side"),
    "biped_walk": dict(kind="biped", phases=dict(L=0.0, R=0.5), duty=0.62, mech="vault",
                       c=0.9, speed=1.2, clearance=0.1, bob=0.025, pitch=0.0,
                       what="biped walk with double support"),
    "biped_run":  dict(kind="biped", phases=dict(L=0.0, R=0.5), duty=0.36, mech="bounce",
                       c=1.1, speed=3.0, clearance=0.3, bob=0.04, pitch=0.0,
                       what="biped run with a flight phase"),
}
GAIT_ALIASES = {("walk", 2): "biped_walk", ("run", 2): "biped_run", ("walk", 6): "tripod", ("run", 6): "tripod",
                ("run", 4): "gallop"}


def resolve_gait(name: str, n_legs: int) -> str:
    key = (str(name).lower(), n_legs)
    g = GAIT_ALIASES.get(key, str(name).lower())
    if g not in GAITS:
        raise ValueError(f"unknown gait {name!r}; one of {sorted(GAITS)} (walk/run also resolve for 2 or 6 legs)")
    need = len(KIND_ROLES[GAITS[g]["kind"]])
    if need != n_legs:
        raise ValueError(f"gait {g!r} is for {need} legs ({GAITS[g]['kind']}), got {n_legs}")
    return g


def list_gaits() -> dict:
    return {n: {"legs": len(KIND_ROLES[g["kind"]]), "kind": g["kind"], "duty": g["duty"], "mech": g["mech"],
                "phases": g["phases"], "default_speed_leg_lengths_per_s": g["speed"], "what": g["what"]}
            for n, g in GAITS.items()}


# ===================================================================== shape functions
def minjerk(s):
    s = np.clip(s, 0, 1)
    return s ** 3 * (10 - 15 * s + 6 * s * s)


def lift_arc(s):
    q = np.clip(s, 0, 1) ** 0.8
    return 16 * (q * (1 - q)) ** 2


_RA, _RB = 1.5, 2.0
_RPEAK = (_RA / (_RA + _RB)) ** _RA * (_RB / (_RA + _RB)) ** _RB


def roll_arc(s):
    s = np.clip(s, 0, 1)
    return s ** _RA * (1 - s) ** _RB / _RPEAK


def smoothstep(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def spring_step(t, zeta: float, hz: float):
    """Unit step response of an underdamped spring (0 before t=0). Overshoot = exp(-pi z / sqrt(1-z^2))."""
    t = np.asarray(t, float)
    w = 2 * math.pi * hz
    wd = w * math.sqrt(1 - zeta * zeta)
    tt = np.maximum(t, 0)
    y = 1 - np.exp(-zeta * w * tt) * (np.cos(wd * tt) + zeta / math.sqrt(1 - zeta * zeta) * np.sin(wd * tt))
    return np.where(t > 0, y, 0.0)


def spring_overshoot(zeta: float) -> float:
    return math.exp(-math.pi * zeta / math.sqrt(1 - zeta * zeta))


def spring_kick(t, zeta: float, hz: float, length: float):
    """Impulse response e^(-z w t) sin(wd t), scaled to peak 1, tapered to exactly 0 at ``length``."""
    t = np.asarray(t, float)
    w = 2 * math.pi * hz
    wd = w * math.sqrt(1 - zeta * zeta)
    tp = math.atan2(math.sqrt(1 - zeta * zeta), zeta) / wd
    peak = math.exp(-zeta * w * tp) * math.sin(wd * tp)
    tt = np.clip(t, 0, length)
    y = np.exp(-zeta * w * tt) * np.sin(wd * tt) / peak * (1 - (tt / length) ** 6)
    return np.where((t > 0) & (t < length), y, 0.0)


# ========================================================================= legs
_SIDE_TOK = {"l": "L", "left": "L", "r": "R", "right": "R", "near": "R", "far": "L"}
_END_TOK = {"front": "F", "fore": "F", "f": "F", "arm": "F", "hind": "H", "rear": "H", "back": "H", "h": "H",
            "mid": "M", "middle": "M", "m": "M", "1": "F", "2": "M", "3": "H"}


def infer_leg(name: str) -> tuple[str | None, str | None]:
    """(side, end) from a bone name: 'ik_front_R' -> ('R', 'F'), 'LH' -> ('L', 'H'), 'ik_L2' -> ('L', 'M')."""
    toks = [t for t in re.split(r"[^a-z0-9]+", name.lower()) if t]
    side = end = None
    for t in toks:
        if t in _SIDE_TOK:
            side = side or _SIDE_TOK[t]
        elif t in _END_TOK and t not in ("1", "2", "3"):
            end = end or _END_TOK[t]
        elif re.fullmatch(r"[lr][fhm123]", t):
            side, end = side or t[0].upper(), end or _END_TOK[t[1]]
        elif re.fullmatch(r"[fhm][lr]", t):
            side, end = side or t[1].upper(), end or _END_TOK[t[0]]
    return side, end


def _role(kind: str, side: str | None, end: str | None, label: str) -> str:
    if side not in ("L", "R"):
        raise ValueError(f"leg {label!r}: side unknown; pass side='L'|'R' (or name it _L/_R)")
    if kind == "biped":
        return side
    if end is None:
        mid = "|'middle'" if kind == "hexapod" else ""
        raise ValueError(f"leg {label!r}: end unknown; pass end='front'|'hind'{mid}")
    if kind == "quadruped":
        if end == "M":
            raise ValueError(f"leg {label!r}: a quadruped has no middle legs")
        return side + end
    return side + {"F": "1", "M": "2", "H": "3"}[end]


@dataclass
class LegPlan:
    target: str
    role: str
    name: str
    hip: str
    hip0: np.ndarray          # setup world position of the hip joint
    target0: np.ndarray       # setup world position of the foot target
    offset: np.ndarray        # setup world vector target -> the point the 2-bone IK actually reaches (hock)
    reach: float
    reach_min: float
    roll: float
    inv: np.ndarray           # world delta -> target parent's local delta
    bias: float | None = None  # forward shift of the stance range from the setup foot; None = automatic
    center: float = 0.0        # the bias that centres the stance under the hip


def _leg_from_spec(sk: SkeletonData, world, spec, kind: str) -> LegPlan:
    if isinstance(spec, str):
        spec = {"target": spec}
    spec = dict(spec)
    tgt = spec.get("target")
    if not tgt or not sk.has_bone(tgt):
        raise ValueError(f"leg target bone {tgt!r} not found")
    side, end = infer_leg(tgt)
    if spec.get("side"):
        side = _SIDE_TOK.get(str(spec["side"]).lower(), str(spec["side"]).upper())
    if spec.get("end") is not None:
        e = str(spec["end"]).lower()
        if e not in _END_TOK:
            raise ValueError(f"leg {tgt!r}: end must be front|middle|hind (or 1|2|3), got {spec['end']!r}")
        end = _END_TOK[e]
    role = spec.get("role") or _role(kind, side, end, tgt)
    # the IK chain that serves this target (directly, or through a child such as a hock target)
    family = {tgt, *sk.descendants(tgt)}
    chains = [c for c in sk.ik if c.target in family]
    two = [c for c in chains if len(c.bones) == 2]
    ch = two[0] if two else (chains[0] if chains else None)
    hip = spec.get("hip") or (ch.bones[0] if ch else None)
    if hip is None:
        raise ValueError(f"leg target {tgt!r} drives no IK constraint; pass hip= and reach=")
    lens = [sk.bone(b).length for b in ch.bones] if ch else [0.0]
    reach = float(spec.get("reach") or sum(lens))
    reach_min = abs(lens[0] - lens[1]) if len(lens) == 2 else 0.0
    if reach <= 0:
        raise ValueError(f"leg {tgt!r}: reach must be > 0")
    t0 = np.array(world[tgt].head)
    end_pt = np.array(world[ch.target].head) if ch else t0
    off = np.asarray(spec.get("offset", end_pt - t0), float)
    par = world[sk.bone(tgt).parent]
    lin = np.array([[par.a, par.b], [par.c, par.d]])
    name = spec.get("name") or re.sub(r"^ik_", "", tgt)
    return LegPlan(target=tgt, role=role, name=name, hip=hip, hip0=np.array(world[hip].head), target0=t0,
                   offset=off, reach=reach, reach_min=reach_min, roll=float(spec.get("roll", 25.0)),
                   inv=np.linalg.inv(lin), bias=None if spec.get("bias") is None else float(spec["bias"]))


# ===================================================================== the plan
class GaitPlan:
    """Closed-form gait maths. All outputs are WORLD offsets from the setup pose, functions of time t (s)."""

    def __init__(self, gait: str, legs: list[LegPlan], body: str, pivot, frequency: float, speed: float, L: float,
                 duty: float, clearance: float, bob: float, pitch: float, facing: int, body_inv: np.ndarray,
                 sink: float = 0.0):
        g = GAITS[gait]
        self.gait, self.kind, self.mech = gait, g["kind"], g["mech"]
        self.legs, self.body, self.pivot = legs, body, np.asarray(pivot, float)
        self.T = round(1.0 / frequency, 3)
        self.frequency = 1.0 / self.T
        self.speed, self.L, self.duty = float(speed), float(L), float(duty)
        self.stride = self.speed * self.T
        self.clearance, self.bob_amp, self.pitch_amp = float(clearance), float(bob), float(pitch)
        self.facing = int(facing)
        self.body_inv = body_inv
        self.sink = float(sink)
        self.phase = np.array([g["phases"][lg.role] for lg in legs], float)
        u = np.linspace(0, self.T, 2400, endpoint=False)
        tot, fh = self._total(u), self._hind_minus_front(u)
        self._n_tot = ((tot.max() + tot.min()) / 2, (tot.max() - tot.min()) / 2)
        self._n_fh = ((fh.max() + fh.min()) / 2, (fh.max() - fh.min()) / 2)
        fr = self._group(u, FRONT_ROLES)
        self._n_fr = ((fr.max() + fr.min()) / 2, (fr.max() - fr.min()) / 2)

    # ---- per leg
    def phi(self, i: int, t):
        return np.mod(np.asarray(t, float) / self.T - self.phase[i], 1.0)

    def contact(self, i: int, t):
        return self.phi(i, t) < self.duty

    def load(self, i: int, t):
        p = self.phi(i, t)
        return np.where(p < self.duty, np.sin(math.pi * np.clip(p / self.duty, 0, 1)), 0.0)

    def foot(self, i: int, t):
        """(dx, dy, rotation) world offsets of leg i's target from its setup."""
        b, S, lg = self.duty, self.stride, self.legs[i]
        p = self.phi(i, t)
        # keys sit at times rounded to 0.1 ms: a touch-down / lift-off key that rounds a hair into the swing is
        # still evaluated on the stance line, so the stance segment between them is exactly that line
        eps = 1.5e-4 / self.T
        p = np.where(p > 1 - eps, p - 1, p)
        st = p < b + eps
        x_td, x_lo = b * S / 2 + lg.bias, -b * S / 2 + lg.bias
        s = (p - b) / (1 - b)
        x = np.where(st, x_td - S * p, x_lo + S * minjerk(s) - S * (1 - b) * s)
        y = np.where(st, 0.0, self.clearance * lift_arc(s))
        rot = np.where(st, 0.0, -self.facing * lg.roll * roll_arc(s))
        return self.facing * x, y, rot

    # ---- body
    def _total(self, t):
        return sum(self.load(i, t) for i in range(len(self.legs)))

    def _group(self, t, roles):
        idx = [i for i, lg in enumerate(self.legs) if lg.role in roles]
        return sum((self.load(i, t) for i in idx), np.zeros_like(np.asarray(t, float)))

    def _hind_minus_front(self, t):
        return self._group(t, HIND_ROLES) - self._group(t, FRONT_ROLES)

    @staticmethod
    def _norm(v, n):
        return (v - n[0]) / n[1] if n[1] > 1e-9 else np.zeros_like(v)

    def body_offset(self, t):
        """(dy, pitch_degrees) of the body bone; pitch is a world rotation (nose up while the hinds push).
        The setup pose is the tallest stance (legs near full length), so the bob only ever LOWERS the body, by up to
        2 * bob: a bounce sinks under the load peak (spring-mass), a vault sinks between the peaks (pendulum)."""
        t = np.asarray(t, float)
        n01 = (self._norm(self._total(t), self._n_tot) + 1) / 2 if self._n_tot[1] > 1e-9 else np.zeros_like(t)
        dy = -2 * self.bob_amp * (n01 if self.mech == "bounce" else 1 - n01) - self.sink
        pitch = self.facing * self.pitch_amp * self._norm(self._hind_minus_front(t), self._n_fh)
        return dy, pitch

    def front_load(self, t):
        """Summed fore-leg load normalised to -1..1 (1 = fore feet hardest on the ground)."""
        return self._norm(self._group(t, FRONT_ROLES), self._n_fr)

    def hip_world(self, i: int, t):
        dy, pitch = self.body_offset(t)
        a = np.radians(pitch)
        v = self.legs[i].hip0 - self.pivot
        x = self.pivot[0] + np.cos(a) * v[0] - np.sin(a) * v[1]
        y = self.pivot[1] + np.sin(a) * v[0] + np.cos(a) * v[1] + dy
        return x, y

    def reach_ratio(self, n: int = 240) -> tuple[float, float]:
        t = np.linspace(0, self.T, n, endpoint=False)
        hi, lo = 0.0, 9.0
        for i, lg in enumerate(self.legs):
            dx, dy, rot = self.foot(i, t)
            a = np.radians(rot)
            ex = lg.target0[0] + dx + np.cos(a) * lg.offset[0] - np.sin(a) * lg.offset[1]
            ey = lg.target0[1] + dy + np.sin(a) * lg.offset[0] + np.cos(a) * lg.offset[1]
            hx, hy = self.hip_world(i, t)
            d = np.hypot(ex - hx, ey - hy)
            hi = max(hi, float(d.max() / lg.reach))
            lo = min(lo, float((d.min() - lg.reach_min) / lg.reach))
        return hi, lo

    def touchdowns(self, duration: float) -> list[tuple[float, int]]:
        out = []
        for i in range(len(self.legs)):
            k = math.floor(-self.phase[i]) - 1
            while True:
                t = (self.phase[i] + k) * self.T
                if t >= duration - 1e-6:
                    break
                if t >= -1e-9:
                    out.append((max(t, 0.0), i))
                k += 1
        return sorted(out)

    def foot_times(self, i: int, duration: float, fps: float = 60) -> np.ndarray:
        """Key times for leg i: touch-down and lift-off (stance is ONE linear segment), dense samples in swing."""
        b, T = self.duty, self.T
        sw = (1 - b) * T
        n = max(10, math.ceil(sw * fps))
        ts = [0.0, duration]
        k = math.floor(-self.phase[i]) - 1
        while (self.phase[i] + k) * T < duration + T:
            td = (self.phase[i] + k) * T
            lo = td + b * T
            ts += [td, lo] + list(lo + sw * np.arange(1, n) / n)
            k += 1
        ts = np.array(ts)
        ts = ts[(ts >= -1e-9) & (ts <= duration + 1e-9)]
        return np.unique(np.round(np.clip(ts, 0, duration), 4))

    def summary(self) -> dict:
        return {"gait": self.gait, "kind": self.kind, "mech": self.mech, "period": self.T,
                "frequency_hz": round(self.frequency, 4), "speed": round(self.speed, 3),
                "stride": round(self.stride, 3),
                "step_length": round(self.duty * self.stride, 3), "duty": self.duty, "leg_length": round(self.L, 3),
                "relative_speed": round(self.speed / self.L, 4),
                "clearance": round(self.clearance, 3), "bob": round(self.bob_amp, 3), "pitch": round(self.pitch_amp, 3),
                "facing": self.facing, "legs": {lg.name: {"role": lg.role, "phase": float(self.phase[i]),
                                                           "target": lg.target}
                                                for i, lg in enumerate(self.legs)}}


def _sk(project) -> SkeletonData:
    return project.data if isinstance(project, Project) else project


def plan_gait(project, legs: list, body: str, gait: str = "walk", speed: float | None = None,
              frequency: float | None = None, duty: float | None = None, clearance: float | None = None,
              bob: float | None = None, pitch: float | None = None, exaggerate: float = 1.0, facing: int = 0,
              leg_length: float | None = None, roll: float | None = None,
              fit_reach: bool = True) -> tuple[GaitPlan, dict]:
    """Pure maths: build a GaitPlan (no keys written). Returns (plan, notes)."""
    sk = _sk(project)
    if not legs:
        raise ValueError("legs is empty: pass the foot IK target bones (with side/end, or named like ik_front_R)")
    if not sk.has_bone(body):
        raise ValueError(f"body bone {body!r} not found")
    if exaggerate <= 0:
        raise ValueError("exaggerate must be > 0")
    g = resolve_gait(gait, len(legs))
    G = GAITS[g]
    world = sk.world()
    lp = [_leg_from_spec(sk, world, s, G["kind"]) for s in legs]
    roles = [x.role for x in lp]
    if sorted(roles) != sorted(KIND_ROLES[G["kind"]]):
        raise ValueError(f"gait {g!r} needs one leg per role {list(KIND_ROLES[G['kind']])}, got {roles}")
    if roll is not None:
        for x in lp:
            x.roll = float(roll)
    for x in lp:
        x.roll *= exaggerate
    if not facing:
        fr = [x.target0[0] for x in lp if x.role in FRONT_ROLES]
        hd = [x.target0[0] for x in lp if x.role in HIND_ROLES]
        facing = 1 if not fr or not hd or np.mean(fr) >= np.mean(hd) else -1
    facing = 1 if facing > 0 else -1
    auto = [x for x in lp if x.bias is None]
    for x in lp:
        x.center = facing * float(x.hip0[0] - (x.target0[0] + x.offset[0]))
        if x.bias is None:
            x.bias = 0.0
    L = float(leg_length or np.mean([x.hip0[1] - x.target0[1] for x in lp]))
    if L <= 0:
        raise ValueError("leg length (hip height above the feet) must be > 0; pass leg_length=")
    v = G["speed"] * L if speed is None else float(speed)
    if v <= 0:
        raise ValueError("speed must be > 0 (units per second; the cycle is in place, the world scrolls)")
    d = G["duty"] if duty is None else float(duty)
    if not 0.05 <= d <= 0.95:
        raise ValueError("duty must be within 0.05..0.95")
    f0 = G["c"] * math.sqrt(v / L) if frequency is None else float(frequency)
    if f0 <= 0:
        raise ValueError("frequency must be > 0")
    h = (G["clearance"] * L if clearance is None else float(clearance)) * exaggerate
    A = (G["bob"] * L if bob is None else float(bob)) * exaggerate
    P = (G["pitch"] if pitch is None else float(pitch)) * exaggerate
    bw = world[body]
    par = world[sk.bone(body).parent] if sk.bone(body).parent else None
    binv = np.linalg.inv(np.array([[par.a, par.b], [par.c, par.d]])) if par else np.eye(2)
    notes: dict = {}
    f = f0
    plan = None
    sink, frac, h0 = 0.0, 0.0, h
    for it in range(100):
        for x in auto:
            x.bias = frac * x.center
        plan = GaitPlan(g, lp, body, bw.head, f, v, L, d, h, A, P, facing, binv, sink)
        hi, lo = plan.reach_ratio()
        if not fit_reach or (hi <= 0.985 and lo >= 0.0):
            break
        if hi > 0.985:
            if auto and frac < 1 - 1e-9:
                frac += 0.25              # first plant the feet nearer under the hips (the leg is shortest there)
            elif sink < 0.06 * L - 1e-9:
                sink += 0.005 * L         # first carry the hips a little lower (locomotion is lower than standing)
            elif frequency is None:
                f *= 1.04                 # then take shorter, quicker steps
                if f > 1.6 * f0:
                    A *= 0.85
                    P *= 0.85
            else:
                break
        else:                             # folded past the knee's limit: lift the swinging foot less
            if h < 0.3 * h0:
                break
            h *= 0.9
    hi, lo = plan.reach_ratio()
    if h < h0 - 1e-9:
        notes["clearance_lowered"] = {"from": round(h0, 3), "to": round(h, 3),
                                      "why": "a lifted foot came closer to the hip than the folded leg allows"}
    if lo < 0:
        notes.setdefault("warning", "a foot comes closer to its hip than the folded leg allows; the IK cannot follow")
    if sink:
        notes["sink"] = round(sink, 3)
    if auto and frac:
        notes["stance_centred"] = frac
    if plan.frequency > f0 * 1.01 and frequency is None:
        notes["frequency_raised"] = {"from": round(f0, 4), "to": round(plan.frequency, 4),
                                     "why": "the stride over-stretched a leg (its foot would slide): "
                                            "shorter, quicker steps"}
    if hi > 0.985:
        notes["warning"] = (f"a leg reaches {hi:.0%} of its length: the IK may let a planted foot slide; "
                            "lower the speed or the bob/pitch")
    notes["reach_max"] = round(hi, 4)
    return plan, notes


def apply_gait(project, plan: GaitPlan, name: str, cycles: int = 1, start: float = 0.0, events: bool = True,
               fps: float = 60) -> dict:
    """Write a GaitPlan as keys into animation ``name`` (kept: every other timeline already there)."""
    sk = _sk(project)
    if cycles < 1:
        raise ValueError("cycles must be >= 1")
    D = round(cycles * plan.T, 4)
    ab = AnimBuilder(sk, name, replace=False)
    for i, lg in enumerate(plan.legs):
        ts = plan.foot_times(i, D, fps)
        dx, dy, rot = plan.foot(i, ts)
        loc = lg.inv @ np.vstack([dx, dy])
        tr = [(start + t, x, y) for t, x, y in zip(ts, loc[0], loc[1])]
        tr[-1] = (tr[-1][0], tr[0][1], tr[0][2])
        ab.bone(lg.target, "translate", tr, "linear")
        if lg.roll:
            rk = [(start + t, a) for t, a in zip(ts, rot)]
            rk[-1] = (rk[-1][0], rk[0][1])
            ab.bone(lg.target, "rotate", rk, "linear")
    tb = np.unique(np.round(np.r_[np.linspace(0, D, max(49, math.ceil(D * fps)) + 1)], 4))
    dy, pitch = plan.body_offset(tb)
    loc = plan.body_inv @ np.vstack([np.zeros_like(dy), dy])
    tr = [(start + t, x, y) for t, x, y in zip(tb, loc[0], loc[1])]
    tr[-1] = (tr[-1][0], tr[0][1], tr[0][2])
    ab.bone(plan.body, "translate", tr, "linear")
    if plan.pitch_amp:
        rk = [(start + t, a) for t, a in zip(tb, pitch)]
        rk[-1] = (rk[-1][0], rk[0][1])
        ab.bone(plan.body, "rotate", rk, "linear")
    steps = []
    if events:
        for t, i in plan.touchdowns(D):
            ab.event(start + t, "sfx_step", string=plan.legs[i].name)
            steps.append([round(start + t, 4), plan.legs[i].name])
    return {"animation": name, "duration": D, "cycles": cycles, "steps": steps}


def gait(project, legs: list, body: str, gait: str = "walk", name: str | None = None, speed: float | None = None,
         cycles: int = 1, start: float = 0.0, frequency: float | None = None, duty: float | None = None,
         clearance: float | None = None, bob: float | None = None, pitch: float | None = None,
         exaggerate: float = 1.0, facing: int = 0, leg_length: float | None = None, roll: float | None = None,
         events: bool = True, return_plan: bool = False) -> dict:
    """Plan a gait and key it: the foot IK targets (planted stance, swing arc, toe roll), the body bone (bob, pitch)
    and an ``sfx_step`` event per footfall. ``legs``: IK target bone names (side/end read from the name, e.g.
    ik_front_R, ik_LH, ik_L2) or dicts {target, side, end, name, roll, hip, reach, offset, bias}."""
    plan, notes = plan_gait(project, legs, body, gait, speed, frequency, duty, clearance, bob, pitch, exaggerate,
                            facing, leg_length, roll)
    res = apply_gait(project, plan, name or plan.gait, cycles, start, events)
    res.update(plan.summary())
    res.update(notes)
    if return_plan:
        res["plan"] = plan
    return res


# ================================================================ part geometry from art
def part_axis(project: Project, slot: str, threshold: int = 8):
    """The two cap centres of an elongated part (world) and their radii, from the art's alpha: the principal axis,
    then at each end the point where the half-width profile h(d) meets the distance d from the tip (a circular cap
    of radius r has h(r) = r). Returns (p0, p1, r0, r1) with p0 the end nearer the image top."""
    sk = project.data
    s = sk.slot(slot)
    att = sk.attachment(slot)
    if not isinstance(att, RegionAttachment):
        raise ValueError(f"{slot}: expected a region attachment (rig before meshing)")
    im = project.image(project.att_image_name(slot, s.attachment))
    W, H = im.size
    a = np.array(im)[:, :, 3]
    ys, xs = np.nonzero(a > threshold)
    if len(xs) < 6:
        raise ValueError(f"{slot}: the art is (almost) empty")
    P = np.c_[xs, ys].astype(float) + 0.5
    c = P.mean(0)
    _, _, vt = np.linalg.svd(P - c, full_matrices=False)
    ax = vt[0]
    if ax[1] < 0 or (abs(ax[1]) < 1e-9 and ax[0] < 0):
        ax = -ax                                   # +t runs toward the image bottom
    nrm = np.array([-ax[1], ax[0]])
    t = (P - c) @ ax
    q = np.abs((P - c) @ nrm)
    lo, hi = t.min(), t.max()
    nb = int(math.ceil(hi - lo)) + 1
    prof = np.zeros(nb)
    np.maximum.at(prof, np.clip((t - lo).astype(int), 0, nb - 1), q)

    def cap(profile):
        for d in range(len(profile) // 2):
            if profile[d] >= d:
                continue
            return float(d), float(max(profile[d], d))
        return len(profile) / 2.0, float(profile.max())

    d0, r0 = cap(prof)
    d1, r1 = cap(prof[::-1])
    p0 = c + ax * (lo + d0)
    p1 = c + ax * (hi - d1)
    f, _ = region_pixel_to_local(att, W, H)
    wb = sk.world()[s.bone]
    pw = to_world(wb, f(np.array([p0, p1, p0 + nrm])))
    k = float(np.hypot(*(pw[2] - pw[0])))
    return pw[0], pw[1], r0 * k, r1 * k


def _seg_dist(p, a, b) -> float:
    p, a, b = (np.asarray(v, float) for v in (p, a, b))
    ab = b - a
    L2 = float(ab @ ab)
    u = 0.0 if L2 < 1e-12 else float(np.clip((p - a) @ ab / L2, 0, 1))
    return float(np.hypot(*(p - (a + u * ab))))


# ====================================================================== quadruped
QUADRUPED_LAYERS: dict[str, str] = {
    # required
    "body": "REQUIRED. The torso. Becomes a mesh weighted to spine_back, hips, spine_front, shoulders.",
    "head": "REQUIRED. The head; every face part rides its bone.",
    "{front|hind}_{upper|lower|foot}_{L|R}": (
        "REQUIRED, 12 layers. One elongated part per leg segment, overlapping at the joints (round ends help: the "
        "joint is read at the centre of each end cap). upper = thigh / upper arm, lower = shin / forearm, "
        "foot = paw / hoof. Aliases: fore for front; rear, back for hind; thigh, humerus for upper; shin, forearm "
        "for lower; paw, hoof for foot. Optional leg_ prefix (leg_front_upper_R)."),
    # optional
    "{front|hind}_mid_{L|R}": ("optional metapodial (metatarsus / metacarpus / cannon; aliases metatarsus, "
                               "metacarpus, cannon). Digitigrade and unguligrade legs get the bone anyway (split from "
                               "the lower leg); plantigrade legs carry it rigidly with the foot."),
    "neck": "optional. Two bones from the shoulders to the head.",
    "tail": "optional strand: 4 bones, loose exaggerated physics, keyed swing in every clip (the emotional readout).",
    "ear_{L|R} (or ear)": "optional strands, 2 bones each, hair physics; forward in alert, flicks in idle.",
    "eye_{L|R} (or eye)": "optional; each gets a bone for blinks (idle) and closed eyes (sleep).",
    "mane*": "optional strands on the neck / head, 3 bones, hair physics.",
    "tuft*": "optional fur tufts anywhere, 2 bones, stiff hair physics.",
    "wattle*": "optional strands under the head, 2 bones, tassel physics.",
    "snout, muzzle, nose, mouth, jaw, brow*, cheek*, whisker*, horn*, antler*, beak, tongue, face":
        "optional head parts, ride the head bone.",
    "anything else": "rides the nearest spine / neck / head bone (reported as 'attached').",
}
QUADRUPED_CLIPS = ("idle", "alert", "walk", "trot", "gallop", "bound", "pounce", "sleep", "shake")
LEG_TYPES = {
    # split: where a missing metapodial is cut from the lower leg (fraction knee->ankle); roll: swing toe roll, deg
    "plantigrade": dict(segments=2, split=None, roll=25.0, foot="foot"),
    "digitigrade": dict(segments=3, split=0.6, roll=40.0, foot="foot"),
    "unguligrade": dict(segments=3, split=0.5, roll=55.0, foot="pastern"),
}
_LEG_RE = re.compile(r"^(?:leg_)?(front|fore|hind|rear|back)_(upper|thigh|humerus|lower|shin|forearm|mid|metatarsus|"
                     r"metacarpus|cannon|foot|paw|hoof)_(l|r)$")
_SEG = {"upper": "upper", "thigh": "upper", "humerus": "upper", "lower": "lower", "shin": "lower",
        "forearm": "lower", "mid": "mid", "metatarsus": "mid", "metacarpus": "mid", "cannon": "mid",
        "foot": "foot", "paw": "foot", "hoof": "foot"}
_HEAD_PARTS = re.compile(r"^(snout|muzzle|nose|mouth|jaw|brow.*|cheek.*|whisker.*|horn.*|antler.*|beak|tongue|face)"
                         r"(_[lr])?$")


def _base(slot: str) -> str:
    return slot.split("/")[-1].strip().lower()


def find_quadruped_parts(sk: SkeletonData) -> dict:
    """Map QUADRUPED_LAYERS roles to slot names. Raises ValueError listing every missing required layer."""
    found: dict = {"legs": {}, "ears": [], "eyes": [], "mane": [], "tufts": [], "wattles": [], "head_parts": [],
                   "other": []}
    for s in sk.slots:
        if not s.attachment:
            continue
        b = _base(s.name)
        m = _LEG_RE.match(b)
        if m:
            end = "front" if m.group(1) in ("front", "fore") else "hind"
            found["legs"].setdefault(f"{end}_{m.group(3).upper()}", {})[_SEG[m.group(2)]] = s.name
        elif b in ("body", "torso"):
            found["body"] = s.name
        elif b == "head":
            found["head"] = s.name
        elif b == "neck":
            found["neck"] = s.name
        elif b == "tail":
            found["tail"] = s.name
        elif re.fullmatch(r"ear(_[lr])?", b):
            found["ears"].append(s.name)
        elif re.fullmatch(r"eye(_[lr])?", b):
            found["eyes"].append(s.name)
        elif b.startswith("mane"):
            found["mane"].append(s.name)
        elif b.startswith("tuft"):
            found["tufts"].append(s.name)
        elif b.startswith("wattle"):
            found["wattles"].append(s.name)
        elif _HEAD_PARTS.match(b):
            found["head_parts"].append(s.name)
        else:
            found["other"].append(s.name)
    missing = [n for n in ("body", "head") if n not in found]
    for end in ("front", "hind"):
        for side in ("L", "R"):
            for seg in ("upper", "lower", "foot"):
                if seg not in found["legs"].get(f"{end}_{side}", {}):
                    missing.append(f"{end}_{seg}_{side}")
    if missing:
        raise ValueError(f"quadruped layers missing: {missing}. Convention (case-insensitive, _L/_R sides): "
                         f"{sorted(QUADRUPED_LAYERS)}. Optional parts are skipped when absent.")
    return found


def _leg_chain(sk: SkeletonData, leg: str, parent: str, hip, knee, hock, ankle, toe, knee_forward: bool,
               facing: int, foot_tag: str = "foot") -> dict:
    """Bones + IK for one leg. 2 segments (hock None): 2-bone IK to the ankle target. 3 segments: 2-bone IK to a
    hock target that hangs off the ankle target, plus a 1-bone IK aiming the metapodial at the ankle target. The
    foot bone copies the ankle target's rotation, so a planted foot never turns."""
    def seg(nm, par, a, b):
        a, b = np.asarray(a, float), np.asarray(b, float)
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        sk.add_bone_world(nm, par, float(a[0]), float(a[1]), ang, float(np.hypot(*(b - a))))
        return nm

    up = seg(f"{leg}_upper", parent, hip, knee)
    end2 = hock if hock is not None else ankle
    lo = seg(f"{leg}_lower", up, knee, end2)
    last, mid = lo, None
    if hock is not None:
        mid = seg(f"{leg}_mid", lo, hock, ankle)
        last = mid
    foot = seg(f"{leg}_{foot_tag}", last, ankle, toe)
    tgt = f"ik_{leg}"
    sk.add_bone_world(tgt, "root", float(ankle[0]), float(ankle[1]), 0, color="FF3F00FF")
    v1 = np.subtract(knee, hip)
    v2 = np.subtract(end2, knee)
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    if abs(cross) > 0.03 * np.hypot(*v1) * np.hypot(*v2):
        bend = bool(cross >= 0)
    else:
        bend = (facing > 0) != knee_forward
    out = {"bones": [b for b in (up, lo, mid, foot) if b], "target": tgt, "foot_bone": foot, "upper": up,
           "lower": lo, "mid": mid, "bend_positive": bend}
    if hock is not None:
        ht = f"ik_{leg}_{'hock' if leg.startswith('hind') else 'carpus'}"
        sk.add_bone_world(ht, tgt, float(hock[0]), float(hock[1]), 0, color="FF7F00FF")
        add_ik(sk, [up, lo], target=ht, name=f"ikc_{leg}", bend_positive=bend)
        add_ik(sk, [mid], target=tgt, name=f"ikc_{leg}_mid")
        out["hock_target"] = ht
    else:
        add_ik(sk, [up, lo], target=tgt, name=f"ikc_{leg}", bend_positive=bend)
    w = sk.world()
    add_transform(sk, [foot], tgt, name=f"tc_{leg}_foot", mix_rotate=1, mix_x=0, mix_y=0, mix_scale_x=0,
                  mix_scale_y=0, mix_shear_y=0, rotation=round(w[foot].rotation - w[tgt].rotation, 3))
    return out


@dataclass
class _Quad:
    """What the clip builders need to know about a rigged quadruped."""
    facing: int
    L: float
    legs: dict
    neck: list
    head: str
    tail: list
    ears: list = field(default_factory=list)       # (root bone, forward sign)
    eyes: list = field(default_factory=list)
    neck_raise: float = 1.0
    tail_raise: float = 1.0
    leg_type: str = "digitigrade"
    spine: tuple = ("spine_back", "hips", "spine_front", "shoulders")


def _raise_sign(sk, bone: str) -> float:
    """Sign of the local rotation that LIFTS a bone's tip (d tip_y / d theta = dir_x)."""
    w = sk.world()[bone]
    return 1.0 if w.a >= 0 else -1.0


def _forward_sign(sk, bone: str, facing: int) -> float:
    """Sign of the rotation that swings a bone's tip toward the facing direction (d tip_x / d theta = -dir_y)."""
    w = sk.world()[bone]
    s = -w.c * facing
    return 1.0 if s >= 0 else -1.0


def _alpha_at(project: Project, slot: str, pt) -> float:
    """Alpha (0..1) of a region slot's art at a world point (0 outside the image)."""
    sk = project.data
    s = sk.slot(slot)
    att = sk.attachment(slot)
    if not isinstance(att, RegionAttachment):
        return 0.0
    im = project.image(project.att_image_name(slot, s.attachment))
    _, inv = region_pixel_to_local(att, *im.size)
    lx, ly = sk.world()[s.bone].to_local(float(pt[0]), float(pt[1]))
    px = inv(np.array([[lx, ly]]))[0]
    i, j = int(px[0]), int(px[1])
    if 0 <= i < im.width and 0 <= j < im.height:
        return im.getpixel((i, j))[3] / 255
    return 0.0


def _strand_root_end(project: Project, slot: str, anchors: list, cover: list) -> str:
    """'top'|'bottom'|'left'|'right' for rig_strand: the root is the end that sits ON the art it grows from
    (``cover`` slots: an ear's base overlaps the head), else the end nearest the ``anchors`` segments."""
    p0, p1, _, _ = part_axis(project, slot)
    c0 = max([_alpha_at(project, s, p0) for s in cover] or [0])
    c1 = max([_alpha_at(project, s, p1) for s in cover] or [0])
    if abs(c0 - c1) > 0.25:
        root, tip = (p0, p1) if c0 > c1 else (p1, p0)
    else:
        d0 = min(_seg_dist(p0, a, b) for a, b in anchors)
        d1 = min(_seg_dist(p1, a, b) for a, b in anchors)
        root, tip = (p0, p1) if d0 <= d1 else (p1, p0)
    dx, dy = tip[0] - root[0], tip[1] - root[1]
    if abs(dy) >= abs(dx):
        return "top" if dy < 0 else "bottom"
    return "left" if dx > 0 else "right"


def _nearest_bone(point, segs: dict) -> str:
    return min(segs, key=lambda b: _seg_dist(point, *segs[b]))


def _slot_center(project: Project, slot: str):
    from .rig import setup_hull_world
    return setup_hull_world(project, slot).mean(0)


def rig_quadruped(project: Project, leg_type: str = "digitigrade", clips="all", speeds: dict | None = None,
                  seed: int = 7, exaggerate: float = 1.0, physics: bool = True) -> dict:
    """Rig a four-legged animal from its layers (QUADRUPED_LAYERS) and build its clips (QUADRUPED_CLIPS)."""
    if leg_type not in LEG_TYPES:
        raise ValueError(f"leg_type must be one of {sorted(LEG_TYPES)}")
    if exaggerate <= 0:
        raise ValueError("exaggerate must be > 0")
    clip_list = list(QUADRUPED_CLIPS) if clips in ("all", None) else list(clips)
    bad = [c for c in clip_list if c not in QUADRUPED_CLIPS and GAITS.get(c, {}).get("kind") != "quadruped"]
    if bad:
        raise ValueError(f"unknown clip(s) {bad}; one of {list(QUADRUPED_CLIPS)} or a quadruped gait "
                         f"{[g for g, v in GAITS.items() if v['kind'] == 'quadruped']}")
    for k, v in (speeds or {}).items():
        if v is not None and float(v) <= 0:
            raise ValueError(f"speed for {k!r} must be > 0")
    sk = project.data
    if sk.has_bone("q_body"):
        raise ValueError("this project is already rigged as a quadruped (bone q_body exists)")
    parts = find_quadruped_parts(sk)
    LT = LEG_TYPES[leg_type]
    body_c = _slot_center(project, parts["body"])
    head_c = _slot_center(project, parts["head"])
    facing = 1 if head_c[0] >= body_c[0] else -1

    # ---- leg geometry from the art
    geo = {}
    for leg, segs in sorted(parts["legs"].items()):
        A0, A1, _, _ = part_axis(project, segs["upper"])
        B0, B1, _, _ = part_axis(project, segs["lower"])
        hip = A0 if A0[1] >= A1[1] else A1
        a_bot = A1 if A0[1] >= A1[1] else A0
        b_top, b_bot = (B0, B1) if B0[1] >= B1[1] else (B1, B0)
        knee = (a_bot + b_top) / 2
        hock = None
        if "mid" in segs:
            C0, C1, _, _ = part_axis(project, segs["mid"])
            c_top, c_bot = (C0, C1) if C0[1] >= C1[1] else (C1, C0)
            j = (b_bot + c_top) / 2
            if LT["segments"] == 3:
                hock, ankle = j, c_bot
            else:
                ankle = j
        else:
            ankle = b_bot
            if LT["segments"] == 3:
                hock = knee + LT["split"] * (ankle - knee)
        F0, F1, _, _ = part_axis(project, segs["foot"])
        toe = F0 if facing * F0[0] >= facing * F1[0] else F1
        if np.hypot(*(toe - ankle)) < 2:
            toe = ankle + np.array([facing * 10.0, 0])
        geo[leg] = dict(hip=hip, knee=knee, hock=hock, ankle=ankle, toe=toe,
                        split=("mid" not in segs and hock is not None))
    for leg, g in geo.items():
        if g["hip"][1] <= g["ankle"][1]:
            raise ValueError(f"leg {leg}: the hip is not above the foot; check the leg layers")

    # ---- spine
    S_pt = np.mean([geo[f"front_{s}"]["hip"] for s in "LR"], axis=0)
    H_pt = np.mean([geo[f"hind_{s}"]["hip"] for s in "LR"], axis=0)
    C = (S_pt + H_pt) / 2
    sk.add_bone_world("q_body", "root", float(C[0]), float(C[1]), 0, color="00E1FFFF")

    def bone_to(nm, par, a, b):
        a, b = np.asarray(a, float), np.asarray(b, float)
        sk.add_bone_world(nm, par, float(a[0]), float(a[1]), math.degrees(math.atan2(*(b - a)[::-1])),
                          float(np.hypot(*(b - a))))

    Mf, Mb = (C + S_pt) / 2, (C + H_pt) / 2
    bone_to("spine_front", "q_body", C, Mf)
    bone_to("shoulders", "spine_front", Mf, S_pt)
    bone_to("spine_back", "q_body", C, Mb)
    bone_to("hips", "spine_back", Mb, H_pt)

    # ---- legs
    legs = {}
    for leg, g in sorted(geo.items()):
        par = "shoulders" if leg.startswith("front") else "hips"
        legs[leg] = _leg_chain(sk, leg, par, g["hip"], g["knee"], g["hock"], g["ankle"], g["toe"],
                               knee_forward=leg.startswith("hind"), facing=facing, foot_tag=LT["foot"])
        legs[leg]["ankle"] = g["ankle"]
        legs[leg]["toe"] = g["toe"]
        legs[leg]["roll"] = LT["roll"]
    report = {"facing": facing, "leg_type": leg_type, "legs": {}, "strands": {}, "attached": {}, "skipped": []}
    for leg, segs in parts["legs"].items():
        lg = legs[leg]
        reparent_slot(sk, segs["upper"], lg["upper"])
        if geo[leg]["split"]:
            reparent_slot(sk, segs["lower"], lg["lower"])
            rig_mesh(project, segs["lower"], bones=[lg["lower"], lg["mid"]], detail=0.8)
        else:
            reparent_slot(sk, segs["lower"], lg["lower"])
        if "mid" in segs:
            reparent_slot(sk, segs["mid"], lg["mid"] or lg["foot_bone"])
        reparent_slot(sk, segs["foot"], lg["foot_bone"])
        report["legs"][leg] = {k: lg[k] for k in ("bones", "target", "bend_positive")} | (
            {"hock_target": lg["hock_target"]} if "hock_target" in lg else {}) | (
            {"split_metapodial": True} if geo[leg]["split"] else {})

    # ---- neck and head
    if "neck" in parts:
        N0, N1, _, _ = part_axis(project, parts["neck"])
        nb, nt = (N0, N1) if np.hypot(*(N0 - S_pt)) <= np.hypot(*(N1 - S_pt)) else (N1, N0)
        neck = add_chain(sk, "neck", [nb.tolist(), ((nb + nt) / 2).tolist(), nt.tolist()], "shoulders")
        pivot = nt
        reparent_slot(sk, parts["neck"], neck[0])
    else:
        neck = []
        d = S_pt - head_c
        pivot = head_c + 0.35 * d
    hull = _hull(project, [parts["head"], *[s for s in parts["head_parts"]]])
    tip_i = int(np.argmax(facing * hull[:, 0]))
    tip = hull[tip_i]
    hpar = neck[-1] if neck else "shoulders"
    bone_to("head", hpar, pivot, tip)
    reparent_slot(sk, parts["head"], "head")
    for s in parts["head_parts"]:
        reparent_slot(sk, s, "head")
    eyes = []
    for s in parts["eyes"]:
        c = _slot_center(project, s)
        nm = sk.unique_name(f"eye_{_base(s)[-1]}" if _base(s) != "eye" else "eye")
        sk.add_bone_world(nm, "head", float(c[0]), float(c[1]), 0)
        reparent_slot(sk, s, nm)
        eyes.append(nm)

    reparent_slot(sk, parts["body"], "q_body")

    # ---- strands
    w = sk.world()
    core = {b: (w[b].head, w[b].tail) for b in ("spine_back", "hips", "spine_front", "shoulders", *neck, "head")}
    PH = {"tail": ("tail", dict(inertia=0.75, damping=0.9, strength=60, mass=1.6)),
          "ear": ("hair", dict(inertia=0.5, strength=140, damping=0.86)),
          "mane": ("hair", {}), "tuft": ("hair", dict(strength=220, damping=0.84)), "wattle": ("tassel", {})}

    def strand(slot, kind, n, parent=None):
        c = _slot_center(project, slot)
        par = parent or _nearest_bone(c, core)
        anchors = [core[par]] if par in core else list(core.values())
        cover = [parts["head"]] if par == "head" else [s for s in (parts["body"], parts.get("neck")) if s]
        root_end = _strand_root_end(project, slot, anchors, cover)
        reparent_slot(sk, slot, par)
        res = rig_strand(project, slot, n_bones=n, parent=par, root_end=root_end,
                         physics=None, name=f"{_base(slot)}_", detail=0.8)
        phys = []
        if physics:
            pre, ov = PH[kind]
            phys = add_physics(sk, res["bones"], pre, **ov)
        report["strands"][slot] = {"bones": res["bones"], "physics": phys, "parent": par}
        return res["bones"]

    tail = strand(parts["tail"], "tail", 4, "hips") if "tail" in parts else []
    ears = []
    for s in parts["ears"]:
        bones = strand(s, "ear", 2, "head")
        ears.append((bones[0], _forward_sign(sk, bones[0], facing)))
    for s in parts["mane"]:
        strand(s, "mane", 3)
    for s in parts["tufts"]:
        strand(s, "tuft", 2)
    for s in parts["wattles"]:
        strand(s, "wattle", 2, "head")
    for s in parts["other"]:
        b = _nearest_bone(_slot_center(project, s), core)
        reparent_slot(sk, s, b)
        report["attached"][s] = b
    # ---- meshes last (strand roots are read from the body / neck art while they are still regions)
    rig_mesh(project, parts["body"], bones=["spine_back", "hips", "spine_front", "shoulders"], detail=0.9)
    if neck:
        rig_mesh(project, parts["neck"], bones=neck, detail=0.8)
    for opt in ("neck", "tail"):
        if opt not in parts:
            report["skipped"].append(opt)
    for opt, key in (("ears", "ears"), ("eyes", "eyes")):
        if not parts[key]:
            report["skipped"].append(opt)

    q = _Quad(facing=facing, L=float(np.mean([g["hip"][1] - g["ankle"][1] for g in geo.values()])), legs=legs,
              neck=neck, head="head", tail=tail, ears=ears, eyes=eyes, leg_type=leg_type,
              neck_raise=_raise_sign(sk, neck[0]) if neck else 1.0,
              tail_raise=_raise_sign(sk, tail[0]) if tail else 1.0)
    report["clips"] = {}
    for clip in clip_list:
        report["clips"][clip] = build_clip(project, q, clip, seed=seed, exaggerate=exaggerate,
                                           speed=(speeds or {}).get(clip))
    report["counts"] = {"bones": len(sk.bones), "slots": len(sk.slots), "ik": len(sk.ik),
                        "transform": len(sk.transform), "physics": len(sk.physics)}
    report["gait_legs"] = quad_gait_legs(q)
    project._quad = q  # noqa: SLF001  (handy for callers in the same process)
    return report


def _hull(project, slots):
    from .rig import setup_hull_world
    return np.vstack([setup_hull_world(project, s) for s in slots])


def quad_gait_legs(q: _Quad) -> list[dict]:
    return [{"target": lg["target"], "side": leg[-1], "end": leg.split("_")[0], "name": leg, "roll": lg["roll"]}
            for leg, lg in sorted(q.legs.items())]


def quad_from_project(project: Project) -> _Quad:
    """Rebuild the clip-builder description of an already rigged quadruped (from its bone names)."""
    sk = project.data
    if not sk.has_bone("q_body"):
        raise ValueError("not a rigged quadruped (no q_body bone): run rig_quadruped first")
    w = sk.world()
    legs = {}
    leg_type = "plantigrade"
    for end in ("front", "hind"):
        for side in "LR":
            leg = f"{end}_{side}"
            foot = f"{leg}_pastern" if sk.has_bone(f"{leg}_pastern") else f"{leg}_foot"
            mid = f"{leg}_mid" if sk.has_bone(f"{leg}_mid") else None
            if mid:
                leg_type = "unguligrade" if foot.endswith("pastern") else "digitigrade"
            legs[leg] = {"target": f"ik_{leg}", "foot_bone": foot, "upper": f"{leg}_upper", "lower": f"{leg}_lower",
                         "mid": mid, "ankle": np.array(w[f"ik_{leg}"].head), "toe": np.array(w[foot].tail),
                         "roll": LEG_TYPES[leg_type]["roll"]}
    for lg in legs.values():
        lg["roll"] = LEG_TYPES[leg_type]["roll"]
    facing = 1 if w["head"].x >= w["q_body"].x else -1
    neck = [b for b in ("neck1", "neck2") if sk.has_bone(b)]
    tail = [b.name for b in sk.bones if re.fullmatch(r"tail_\d+", b.name)]
    ears = [(b.name, _forward_sign(sk, b.name, facing)) for b in sk.bones if re.fullmatch(r"ear(_[lr])?_1", b.name)]
    eyes = [b.name for b in sk.bones if re.fullmatch(r"eye(_[lr])?\d*", b.name)]
    L = float(np.mean([w[lg["upper"]].y - lg["ankle"][1] for lg in legs.values()]))
    return _Quad(facing=facing, L=L, legs=legs, neck=neck, head="head", tail=tail, ears=ears, eyes=eyes,
                 leg_type=leg_type, neck_raise=_raise_sign(sk, neck[0]) if neck else 1.0,
                 tail_raise=_raise_sign(sk, tail[0]) if tail else 1.0)


# ====================================================================== clip builders
def _ts(D: float, fps: float = 60, extra=()) -> np.ndarray:
    t = np.r_[np.linspace(0, D, max(2, math.ceil(D * fps)) + 1), np.asarray(list(extra), float)]
    return np.unique(np.round(np.clip(t, 0, D), 4))


def _key(ab: AnimBuilder, bone: str, tl: str, ts, *vals, loop: bool = False, rest: tuple | None = None):
    vals = [np.broadcast_to(np.asarray(v, float), ts.shape) for v in vals]
    pts = [(float(t), *[float(v[i]) for v in vals]) for i, t in enumerate(ts)]
    if loop:
        pts[-1] = (pts[-1][0], *pts[0][1:])
    if rest is not None:
        pts[-1] = (pts[-1][0], *rest)
    ab.bone(bone, tl, pts, "linear")


def _poisson(rng, rate: float, t0: float, t1: float, gap: float) -> list[float]:
    """Event times of a Poisson process (exponential gaps, at least ``gap`` apart) inside [t0, t1]."""
    out, t = [], t0 + rng.exponential(1 / rate) * 0.5
    while t < t1:
        out.append(round(float(t), 3))
        t += gap + rng.exponential(1 / rate)
    return out


def build_clip(project: Project, q: _Quad, clip: str, seed: int = 7, exaggerate: float = 1.0,
               speed: float | None = None) -> dict:
    sk = project.data
    if clip in GAITS:
        return _clip_gait(sk, q, clip, speed, exaggerate)
    fn = {"idle": _clip_idle, "alert": _clip_alert, "pounce": _clip_pounce, "sleep": _clip_sleep,
          "shake": _clip_shake}.get(clip)
    if fn is None:
        raise ValueError(f"unknown clip {clip!r}")
    return fn(sk, q, seed=seed, X=exaggerate)


def _clip_gait(sk, q: _Quad, g: str, speed, X: float, cycles: int = 1, name: str | None = None) -> dict:
    name = name or g
    res = gait(sk, quad_gait_legs(q), "q_body", g, name=name, speed=speed, exaggerate=X, facing=q.facing,
               cycles=cycles, return_plan=True)
    plan: GaitPlan = res.pop("plan")
    D = res["duration"]
    ab = AnimBuilder(sk, name, replace=False)
    ts = _ts(D)
    T = plan.T
    lag = 0.12 * T
    _, pitch_l = plan.body_offset(ts - lag)
    nod = plan.front_load(ts - lag)
    _, pitch_l2 = plan.body_offset(ts - 2 * lag)
    nod2 = plan.front_load(ts - 2 * lag)
    NOD = {"walk": 3.0, "trot": 4.0, "pace": 3.0, "canter": 5.0, "gallop": 5.0, "bound": 6.0}.get(g, 4.0) * X
    TAIL = {"walk": 9.0, "trot": 11.0, "pace": 8.0, "canter": 8.0, "gallop": 6.0, "bound": 8.0}.get(g, 8.0) * X
    TAIL_UP = {"gallop": 10.0, "bound": 8.0, "canter": 6.0}.get(g, 0.0) * X
    n_tot = np.zeros_like(ts)
    if q.neck:
        a1 = -0.6 * pitch_l - q.neck_raise * NOD * nod
        a2 = -0.3 * pitch_l2 - q.neck_raise * 0.6 * NOD * nod2
        _key(ab, q.neck[0], "rotate", ts, a1, loop=True)
        if len(q.neck) > 1:
            _key(ab, q.neck[1], "rotate", ts, a2, loop=True)
            n_tot = a1 + a2
        else:
            n_tot = a1
    _, pitch_now = plan.body_offset(ts)
    _key(ab, q.head, "rotate", ts, -0.7 * (pitch_now + n_tot), loop=True)
    # spine flexion: the back extends while the load passes from the hinds to the fores (the extended flight) and
    # rounds as it passes back (the gathered flight): minus the rate of change of the hind-minus-fore pitch signal
    FLEX = {"canter": 3.0, "gallop": 6.0, "bound": 5.0}.get(g, 0.0) * X
    if FLEX and plan.pitch_amp:
        dlt = 0.02 * T
        u = np.linspace(0, T, 600, endpoint=False)
        e_of = lambda tt: plan.body_offset(tt - dlt)[1] - plan.body_offset(tt + dlt)[1]  # noqa: E731
        ext = e_of(ts) / max(np.abs(e_of(u)).max(), 1e-9) * q.facing
        _key(ab, "spine_front", "rotate", ts, q.facing * FLEX * ext, loop=True)
        _key(ab, "spine_back", "rotate", ts, -q.facing * FLEX * ext, loop=True)
    if q.tail:
        ph = 2 * math.pi * ts / T
        _key(ab, q.tail[0], "rotate", ts, q.tail_raise * TAIL_UP + TAIL * np.sin(ph) - 0.5 * pitch_now, loop=True)
        for k, b in enumerate(q.tail[1:3], 1):
            _key(ab, b, "rotate", ts, 0.6 * TAIL * np.sin(ph - 0.9 * k), loop=True)
    for bone, fwd in q.ears:
        _key(ab, bone, "rotate", ts, -fwd * 5.0 * X * plan.front_load(ts - 2 * lag), loop=True)
    res["kind"] = "loop"
    res["events"] = ["sfx_step"]
    return res


def _clip_idle(sk, q: _Quad, seed: int, X: float, D: float = 4.0) -> dict:
    rng = np.random.default_rng(seed)
    ab = AnimBuilder(sk, "idle")
    fired = []
    extra = []
    flicks = {b: _poisson(rng, 0.45, 0.3, D - 0.7, 0.8) for b, _ in q.ears}
    swishes = _poisson(rng, 0.3, 0.2, D - 1.3, 1.2) if q.tail else []
    blinks = _poisson(rng, 0.35, 0.3, D - 0.4, 1.0) if q.eyes else []
    for ts_ in [*flicks.values(), swishes, blinks]:
        extra += list(ts_)
    ts = _ts(D, 60, extra)
    br = np.sin(2 * math.pi * ts / (D / 2))          # two breaths per loop
    _key(ab, "q_body", "translate", ts, 0, 0.006 * q.L * X * br, loop=True)
    _key(ab, "spine_front", "rotate", ts, q.facing * 0.9 * X * br, loop=True)
    _key(ab, "spine_back", "rotate", ts, -q.facing * 0.4 * X * br, loop=True)
    if q.neck:
        _key(ab, q.neck[0], "rotate", ts, q.neck_raise * 2.5 * X * np.sin(2 * math.pi * ts / D), loop=True)
    _key(ab, q.head, "rotate", ts, 2.0 * X * np.sin(2 * math.pi * ts / D * 2 + 0.7), loop=True)
    for bone, fwd in q.ears:
        a = np.zeros_like(ts)
        for t0 in flicks[bone]:
            a += fwd * 22.0 * X * spring_kick(ts - t0, 0.3, 6.0, 0.55)
            ab.event(t0, "sfx_idle", string="ear_flick")
            fired.append(("ear_flick", t0))
        _key(ab, bone, "rotate", ts, a, loop=True)
    if q.tail:
        base = 4.0 * X * np.sin(2 * math.pi * ts / D * 2)
        sw = np.zeros_like(ts)
        for t0 in swishes:
            sw += 18.0 * X * spring_kick(ts - t0, 0.15, 2.5, 1.2)
            ab.event(t0, "sfx_idle", string="tail_swish")
            fired.append(("tail_swish", t0))
        _key(ab, q.tail[0], "rotate", ts, base + sw, loop=True)
        if len(q.tail) > 1:     # the next bone follows 80 ms later (lag by levels; physics adds the rest)
            sw2 = sum((12.0 * X * spring_kick(ts - t0 - 0.08, 0.15, 2.5, 1.1) for t0 in swishes), np.zeros_like(ts))
            _key(ab, q.tail[1], "rotate", ts, 0.6 * base + sw2, loop=True)
    for e in q.eyes:
        sy = np.ones_like(ts)
        for t0 in blinks:
            u = (ts - t0) / 0.16
            sy -= 0.9 * np.where((u > 0) & (u < 1), np.sin(math.pi * np.clip(u, 0, 1)) ** 2, 0.0)
        _key(ab, e, "scale", ts, 1, sy, loop=True)
    for t0 in blinks:
        ab.event(t0, "sfx_idle", string="blink")
        fired.append(("blink", t0))
    return {"animation": "idle", "duration": D, "kind": "loop", "moments": sorted(fired, key=lambda x: x[1]),
            "events": ["sfx_idle"]}


ALERT_ZETA, ALERT_HZ = 0.45, 3.0


def _clip_alert(sk, q: _Quad, seed: int, X: float, D: float = 2.2) -> dict:
    t0, t_rel = 0.1, 1.55
    wd = 2 * math.pi * ALERT_HZ * math.sqrt(1 - ALERT_ZETA ** 2)
    t_peak = t0 + math.pi / wd
    ab = AnimBuilder(sk, "alert")
    ts = _ts(D, 60, [t_peak, t_rel])
    a = spring_step(ts - t0, ALERT_ZETA, ALERT_HZ) * (1 - smoothstep((ts - t_rel) / (D - t_rel)))
    a[-1] = 0.0
    z = (0,)
    # weight onto the fore legs (they are already near full length, so the body leans rather than rises)
    _key(ab, "q_body", "translate", ts, q.facing * 0.03 * q.L * X * a, -0.01 * q.L * X * a, rest=(0, 0))
    _key(ab, "spine_front", "rotate", ts, q.facing * 3.0 * X * a, rest=z)
    if q.neck:
        _key(ab, q.neck[0], "rotate", ts, q.neck_raise * 12.0 * X * a, rest=z)
        if len(q.neck) > 1:
            _key(ab, q.neck[1], "rotate", ts, q.neck_raise * 6.0 * X * a, rest=z)
    _key(ab, q.head, "rotate", ts, -q.neck_raise * 8.0 * X * a, rest=z)
    for bone, fwd in q.ears:
        _key(ab, bone, "rotate", ts, fwd * 30.0 * X * a, rest=z)
    if q.tail:
        _key(ab, q.tail[0], "rotate", ts, q.tail_raise * 25.0 * X * a, rest=z)
        for b in q.tail[1:]:
            _key(ab, b, "rotate", ts, q.tail_raise * 6.0 * X * a, rest=z)
    ab.event(t0, "sfx_alert")
    return {"animation": "alert", "duration": D, "kind": "one-shot", "snap": t0, "release": t_rel,
            "overshoot": round(spring_overshoot(ALERT_ZETA), 4), "ear_target_deg": 30.0 * X, "events": ["sfx_alert"]}


def _pivot_about(toe, ankle, rot_deg):
    """Translate offset that keeps ``toe`` fixed while a target at ``ankle`` rotates by rot_deg (heels-off)."""
    a = np.radians(rot_deg)
    v = np.asarray(ankle, float) - np.asarray(toe, float)
    nx = toe[0] + np.cos(a) * v[0] - np.sin(a) * v[1]
    ny = toe[1] + np.sin(a) * v[0] + np.cos(a) * v[1]
    return nx - ankle[0], ny - ankle[1]


def _clip_pounce(sk, q: _Quad, seed: int, X: float, D: float = 2.1) -> dict:
    L, f = q.L, q.facing
    t_cr, t_wig, t_go, t_land, t_hold, t_back = 0.35, 0.95, 1.0, 1.22, 1.55, 1.9
    ab = AnimBuilder(sk, "pounce")
    ts = _ts(D, 60, [t_cr, t_wig, t_go, t_land, t_hold, t_back])
    crouch = smoothstep(ts / t_cr) * (1 - smoothstep((ts - t_wig) / (t_go - t_wig)))
    fly = np.clip((ts - t_go) / (t_land - t_go), 0, 1)
    flying = (ts > t_go) & (ts < t_land)
    lunge = (np.where(ts <= t_go, 0, np.where(ts < t_land, minjerk(fly), 1.0))
             * (1 - smoothstep((ts - t_hold) / (D - t_hold))))
    arc = np.where(flying, 4 * fly * (1 - fly), 0.0)
    land = np.where(ts >= t_land, spring_kick(ts - t_land, 0.35, 3.0, 0.5), 0.0)
    wig = np.where((ts > t_cr) & (ts < t_wig), np.sin(2 * math.pi * 3.5 * (ts - t_cr)) *
                   np.sin(math.pi * np.clip((ts - t_cr) / (t_wig - t_cr), 0, 1)), 0.0)
    pin = smoothstep((ts - t_land) / 0.12) * (1 - smoothstep((ts - t_hold) / (t_back - t_hold)))
    bx = f * L * X * (-0.08 * crouch + 0.23 * lunge)
    by = L * X * (-0.2 * crouch + 0.05 * arc - 0.06 * land - 0.08 * pin)     # chest down on the pinned prey
    _key(ab, "q_body", "translate", ts, bx, by, rest=(0, 0))
    _key(ab, "q_body", "rotate", ts, f * X * (-4.0 * crouch + 4.0 * arc - 3.0 * land), rest=(0,))
    _key(ab, "spine_back", "rotate", ts, f * 5.0 * X * wig, rest=(0,))
    if q.neck:
        _key(ab, q.neck[0], "rotate", ts, q.neck_raise * X * (-10.0 * crouch + 8.0 * arc - 6.0 * land - 14.0 * pin),
             rest=(0,))
    _key(ab, q.head, "rotate", ts, -q.neck_raise * X * (-6.0 * crouch + 2.0 * arc - 6.0 * pin), rest=(0,))
    if q.tail:
        lash = np.where(ts > t_land, np.sin(2 * math.pi * 2.2 * (ts - t_land))
                        * (1 - smoothstep((ts - t_land) / (D - t_land))), 0)
        _key(ab, q.tail[0], "rotate", ts, X * (q.tail_raise * (-10.0 * crouch + 15.0 * arc) + 14.0 * wig + 16.0 * lash),
             rest=(0,))
    # fore paws strike forward and pin, then step home
    reach = 0.5 * L * X
    for side in "LR":
        leg = f"front_{side}"
        lg = q.legs[leg]
        st = 0.03 if side == "L" else 0.0
        s1 = np.clip((ts - t_go + 0.05 - st) / (t_land - t_go + 0.05), 0, 1)     # paws leave just before the push
        s2 = np.clip((ts - t_hold - st) / (t_back - t_hold), 0, 1)
        x = reach * (minjerk(s1) - minjerk(s2))
        y = 0.25 * L * X * lift_arc(s1) + 0.1 * L * X * lift_arc(s2)
        rot = -f * 30.0 * X * (roll_arc(s1) + roll_arc(s2))
        _key(ab, lg["target"], "translate", ts, f * x, y, rest=(0, 0))
        _key(ab, lg["target"], "rotate", ts, rot, rest=(0,))
        ab.event(round(t_land + st, 4), "sfx_step", string=leg)
        ab.event(round(t_back + st, 4), "sfx_step", string=leg)
    # hind feet push: heels off (pivot about the toes) during the launch
    for side in "LR":
        leg = f"hind_{side}"
        lg = q.legs[leg]
        push = np.sin(math.pi * np.clip((ts - t_wig) / (t_land + 0.1 - t_wig), 0, 1)) ** 2
        rot = -f * 28.0 * X * push
        dx, dy = _pivot_about(lg["toe"], lg["ankle"], rot)
        _key(ab, lg["target"], "translate", ts, dx, dy, rest=(0, 0))
        _key(ab, lg["target"], "rotate", ts, rot, rest=(0,))
    ab.event(t_go, "sfx_pounce")
    return {"animation": "pounce", "duration": D, "kind": "one-shot", "launch": t_go, "land": t_land,
            "events": ["sfx_pounce", "sfx_step"]}


def _clip_sleep(sk, q: _Quad, seed: int, X: float, D: float = 7.0) -> dict:
    L, f = q.L, q.facing
    ab = AnimBuilder(sk, "sleep")
    ts = _ts(D, 30)
    br = np.sin(2 * math.pi * ts / (D / 2))
    _key(ab, "q_body", "translate", ts, -f * 0.05 * L, -0.58 * L + 0.012 * L * X * br, loop=True)
    _key(ab, "q_body", "rotate", ts, f * 1.5 + 0 * ts, loop=True)
    _key(ab, "spine_front", "rotate", ts, f * 1.2 * X * br, loop=True)
    for side in "LR":
        _key(ab, q.legs[f"front_{side}"]["target"], "translate", ts, f * 0.32 * L, 0, loop=True)
        _key(ab, q.legs[f"hind_{side}"]["target"], "translate", ts, f * 0.12 * L, 0, loop=True)
    # neck down, head tipped back up so the chin rests level on the paws, ears hang (counter the head's turn)
    n1, n2, hd = -q.neck_raise * 30.0, -q.neck_raise * 10.0, q.neck_raise * 24.0
    if q.neck:
        _key(ab, q.neck[0], "rotate", ts, n1 + 1.5 * br, loop=True)
        if len(q.neck) > 1:
            _key(ab, q.neck[1], "rotate", ts, n2 + 0 * ts, loop=True)
    head_turn = (n1 + (n2 if len(q.neck) > 1 else 0)) if q.neck else 0.0
    _key(ab, q.head, "rotate", ts, hd + 0.8 * br, loop=True)
    for b, fwd in q.ears:
        _key(ab, b, "rotate", ts, -(head_turn + hd) - fwd * 6.0 + 0 * ts, loop=True)
    for k, b in enumerate(q.tail):     # lowered, then curled forward round the haunch
        _key(ab, b, "rotate", ts, -q.tail_raise * (34.0, 26.0, 26.0, 22.0)[min(k, 3)] + 0.8 * br * (k == 0),
              loop=True)
    for e in q.eyes:
        _key(ab, e, "scale", ts, 1, 0.12 + 0 * ts, loop=True)
    for k in range(2):
        ab.event(round(k * D / 2, 4), "sfx_sleep", string="breath")
    return {"animation": "sleep", "duration": D, "kind": "loop", "events": ["sfx_sleep"]}


SHAKE_HZ = 4.5   # wet-dog shake: a medium dog shakes at ~4-5 Hz (Dickerson et al. 2012, f ~ M^-0.22)


def _clip_shake(sk, q: _Quad, seed: int, X: float, D: float = 1.9) -> dict:
    t0, t1 = 0.25, 1.6
    ab = AnimBuilder(sk, "shake")
    ts = _ts(D, 60)
    pre = np.sin(math.pi * np.clip(ts / (t0 + 0.15), 0, 1)) ** 2

    def env(t):
        u = np.clip((np.asarray(t, float) - t0) / (t1 - t0), 0, 1)
        e = (1 - np.exp(-u * (t1 - t0) / 0.06)) * np.exp(-np.maximum(0, u * (t1 - t0) - 0.45) / 0.3) * (1 - u ** 8)
        return np.where((t > t0) & (t < t1), e, 0.0)

    w = 2 * math.pi * SHAKE_HZ
    delay = 0.035                                   # the wave runs head -> tail, one bone every 35 ms
    chain = [(q.head, 22.0), *[(b, 9.0) for b in reversed(q.neck)], ("shoulders", 5.0), ("spine_front", 5.0),
             ("spine_back", 5.0), ("hips", 6.0), *[(b, 28.0) for b in q.tail]]
    order = {}
    for k, (b, amp) in enumerate(chain):
        tk = ts - k * delay
        val = amp * X * env(tk) * np.sin(w * (tk - t0))
        if b == q.head:
            val = val - q.neck_raise * 6.0 * pre
        if q.neck and b == q.neck[0]:
            val = val - q.neck_raise * 5.0 * pre
        _key(ab, b, "rotate", ts, val, rest=(0,))
        order[b] = k * delay
    # the head twists about the spine: seen side-on it foreshortens twice per cycle
    _key(ab, q.head, "scale", ts, 1 - 0.3 * X * env(ts) * np.sin(w * (ts - t0)) ** 2, 1, rest=(1, 1))
    # legs braced: the body sits a little lower while it shakes, and bounces at twice the shake rate
    sit = np.maximum(pre, np.minimum(1, 3 * env(ts)))
    _key(ab, "q_body", "translate", ts, 0, q.L * X * (-0.05 * sit + 0.02 * env(ts - 3 * delay) *
                                                       np.sin(2 * w * (ts - t0))), rest=(0, 0))
    for bone, fwd in q.ears:      # flung out by the twist (physics adds the flap)
        _key(ab, bone, "rotate", ts, 45.0 * X * env(ts - delay) * np.sin(w * (ts - delay - t0) + 0.6), rest=(0,))
    ab.event(t0, "sfx_shake")
    return {"animation": "shake", "duration": D, "kind": "one-shot", "frequency_hz": SHAKE_HZ, "wave_delay": delay,
            "start": t0, "end": t1, "events": ["sfx_shake"]}


# ====================================================================== procedural art
SS = 3


def _part(shape, bbox, top, bottom, outline=(58, 36, 24), ow=2.5, pad=4):
    """Render one part: ``shape(draw, T)`` paints a mask using T(x, y) world -> supersampled pixels.
    Returns (image, world centre). Gradient top -> bottom, dark outline, soft edge."""
    x0, y0, x1, y1 = bbox
    x0, y0, x1, y1 = math.floor(x0) - pad, math.floor(y0) - pad, math.ceil(x1) + pad, math.ceil(y1) + pad
    W, H = x1 - x0, y1 - y0
    big = (W * SS, H * SS)

    def T(x, y):
        return ((x - x0) * SS, (y1 - y) * SS)

    mask = Image.new("L", big, 0)
    shape(ImageDraw.Draw(mask), T)
    if ow > 0:
        from scipy.ndimage import distance_transform_edt
        inner = Image.fromarray(((distance_transform_edt(np.asarray(mask) > 127) > ow * SS) * 255).astype(np.uint8))
    else:
        inner = mask
    g = np.linspace(0, 1, big[1])[:, None, None]
    grad = (np.array(top, float)[None, None] * (1 - g) + np.array(bottom, float)[None, None] * g)
    grad = Image.fromarray(np.repeat(grad, big[0], 1).astype(np.uint8))
    im = Image.new("RGBA", big, tuple(outline) + (255,))
    im.paste(grad, (0, 0), inner)
    im.putalpha(mask)
    im = im.resize((W, H), Image.LANCZOS)
    return im, ((x0 + x1) / 2, (y0 + y1) / 2)


def _capsule(pts, radii):
    """Shape fn: a tapered tube through world points with per-point radii (round caps)."""
    def shape(d, T):
        for (a, ra), (b, rb) in zip(zip(pts, radii), zip(pts[1:], radii[1:])):
            L = math.hypot(b[0] - a[0], b[1] - a[1])
            n = max(2, int(L * 1.5))
            for i in range(n + 1):
                u = i / n
                x, y = a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u
                rr = (ra + (rb - ra) * u) * SS
                px, py = T(x, y)
                d.ellipse([px - rr, py - rr, px + rr, py + rr], fill=255)
    return shape


def _bbox_of(pts, radii):
    P = np.asarray(pts, float)
    R = max(radii)
    return (P[:, 0].min() - R, P[:, 1].min() - R, P[:, 0].max() + R, P[:, 1].max() + R)


def _ellipses(items):
    def shape(d, T):
        for (cx, cy, rx, ry) in items:
            ax, ay = T(cx - rx, cy + ry)
            bx, by = T(cx + rx, cy - ry)
            d.ellipse([ax, ay, bx, by], fill=255)
    return shape


def _ell_bbox(items):
    return (min(c[0] - c[2] for c in items), min(c[1] - c[3] for c in items),
            max(c[0] + c[2] for c in items), max(c[1] + c[3] for c in items))


def _add_part(p: Project, name: str, im: Image.Image, center) -> None:
    p.write_image(name, im)
    sk = p.data
    sk.slots.append(Slot(name=name, bone="root", attachment=name))
    sk.set_attachment(name, name, RegionAttachment(x=round(center[0], 2), y=round(center[1], 2),
                                                   width=im.width, height=im.height))


def _dim(c, k=0.68):
    return tuple(int(v * k) for v in c)


def make_sample_quadruped(out_dir: str | Path, name: str = "dog", with_mid: bool = True) -> Project:
    """A readable dog-like side view (faces right, stands on y = 0) drawn from simple shapes, one PNG per layer,
    named exactly as import_psd would name a PSD that follows QUADRUPED_LAYERS. ``with_mid=False`` leaves out the
    metapodial layers (tests the split)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sk = new_skeleton(width=560, height=340)
    p = Project(out / f"{name}.json", sk)
    coat_t, coat_b = (226, 170, 100), (176, 116, 60)
    ear_t, ear_b = (130, 80, 44), (92, 54, 30)
    legs = {
        # end: (joints [hip, knee, hock, ankle], radii, paw centre)
        "hind": ([(-100, 150), (-76, 100), (-112, 54), (-102, 16)], [30, 17, 11, 9], (-90, 10)),
        "front": ([(98, 150), (74, 108), (92, 54), (96, 16)], [22, 14, 11, 9], (108, 10)),
    }
    far_shift = np.array([14.0, 5.0])

    def leg_layers(side):
        far = side == "L"
        t, b = (_dim(coat_t), _dim(coat_b)) if far else (coat_t, coat_b)
        for end in ("hind", "front"):
            J, R, paw = legs[end]
            J = [tuple(np.add(j, far_shift)) if far else j for j in J]
            paw = tuple(np.add(paw, far_shift)) if far else paw
            if with_mid:
                segs = [("upper", [J[0], J[1]], [R[0], R[1]]), ("lower", [J[1], J[2]], [R[1] * 0.95, R[2]]),
                        ("mid", [J[2], J[3]], [R[2], R[3]])]
            else:   # one lower-leg layer from the knee to the paw (the rig splits it)
                segs = [("upper", [J[0], J[1]], [R[0], R[1]]), ("lower", [J[1], J[2], J[3]], [R[1] * 0.95, R[2], R[3]])]
            for seg, pts, rad in segs:
                im, c = _part(_capsule(pts, rad), _bbox_of(pts, rad), t, b)
                _add_part(p, f"{end}_{seg}_{side}", im, c)
            pe = [(paw[0], paw[1], 18, 10)]
            im, c = _part(_ellipses(pe), _ell_bbox(pe), t, b)
            _add_part(p, f"{end}_foot_{side}", im, c)

    leg_layers("L")
    # far ear, tail, belly tuft behind the body
    ear_far = [(181, 284), (171, 242)]
    im, c = _part(_capsule(ear_far, [13, 11]), _bbox_of(ear_far, [13, 11]), _dim(ear_t), _dim(ear_b))
    _add_part(p, "ear_L", im, c)
    tail = [(-138, 180), (-170, 200), (-196, 232), (-206, 266)]
    im, c = _part(_capsule(tail, [11, 9, 7, 5]), _bbox_of(tail, [11, 9, 7, 5]), coat_t, coat_b)
    _add_part(p, "tail", im, c)
    tb = [(4, 108), (8, 86)]
    im, c = _part(_capsule(tb, [8, 3]), _bbox_of(tb, [8, 3]), (240, 214, 170), (214, 180, 130), ow=1.5)
    _add_part(p, "tuft_belly", im, c)
    body = [(5, 152, 138, 48), (84, 146, 58, 56), (-104, 160, 50, 44)]
    im, c = _part(_ellipses(body), _ell_bbox(body), coat_t, coat_b)
    _add_part(p, "body", im, c)
    neck = [(108, 172), (160, 232)]
    im, c = _part(_capsule(neck, [30, 24]), _bbox_of(neck, [30, 24]), coat_t, coat_b)
    _add_part(p, "neck", im, c)
    im, c = _part(_capsule([(110, 205), (140, 178)], [7, 7]), _bbox_of([(110, 205), (140, 178)], [7, 7]),
                  (220, 50, 60), (150, 20, 40), ow=1.5)
    _add_part(p, "collar", im, c)
    tc = [(140, 130), (132, 100)]
    im, c = _part(_capsule(tc, [9, 3]), _bbox_of(tc, [9, 3]), (240, 214, 170), (214, 180, 130), ow=1.5)
    _add_part(p, "tuft_chest", im, c)
    leg_layers("R")
    head = [(182, 252, 40, 34)]
    im, c = _part(_ellipses(head), _ell_bbox(head), coat_t, coat_b)
    _add_part(p, "head", im, c)
    snout = [(200, 238), (240, 236)]
    im, c = _part(_capsule(snout, [17, 13]), _bbox_of(snout, [17, 13]), (236, 196, 140), (196, 150, 96))
    _add_part(p, "snout", im, c)
    nose = [(252, 241, 8, 7)]
    im, c = _part(_ellipses(nose), _ell_bbox(nose), (50, 36, 34), (20, 14, 14), ow=0)
    _add_part(p, "nose", im, c)
    eye = Image.new("RGBA", (16, 18), (0, 0, 0, 0))
    de = ImageDraw.Draw(eye)
    de.ellipse([1, 1, 14, 16], fill=(34, 22, 18, 255))
    de.ellipse([4, 4, 8, 8], fill=(255, 255, 255, 255))
    _add_part(p, "eye_R", eye, (196, 262))
    ear_near = [(168, 282), (150, 230)]
    im, c = _part(_capsule(ear_near, [15, 12]), _bbox_of(ear_near, [15, 12]), ear_t, ear_b)
    _add_part(p, "ear_R", im, c)
    p.save()
    return p


def _test_leg(p: Project, n: str, J, radii, cols, foot, ow=2.5) -> None:
    """Art + two bones + IK + a foot bone that copies the target's rotation, for the gait test rigs."""
    sk = p.data
    for seg, a, b, ra, rb in (("upper", J[0], J[1], *radii[:2]), ("lower", J[1], J[2], *radii[1:])):
        im, c = _part(_capsule([a, b], [ra, rb]), _bbox_of([a, b], [ra, rb]), *cols, ow=ow)
        _add_part(p, f"{n}_{seg}", im, c)
    for seg, par, a, b in (("upper", "body", J[0], J[1]), ("lower", f"{n}_upper", J[1], J[2])):
        sk.add_bone_world(f"{n}_{seg}", par, float(a[0]), float(a[1]),
                          math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])), math.hypot(b[0] - a[0], b[1] - a[1]))
        reparent_slot(sk, f"{n}_{seg}", f"{n}_{seg}")
    sk.add_bone_world(f"ik_{n}", "root", float(J[2][0]), float(J[2][1]), 0, color="FF3F00FF")
    add_ik(sk, [f"{n}_upper", f"{n}_lower"], target=f"ik_{n}", name=f"ikc_{n}")
    fx, fy, frx, fry = foot
    im, c = _part(_ellipses([foot]), _ell_bbox([foot]), *cols, ow=min(ow, 1.5))
    _add_part(p, f"{n}_foot", im, c)
    sk.add_bone_world(f"{n}_foot", f"{n}_lower", float(J[2][0]), float(J[2][1]), 0, frx)
    reparent_slot(sk, f"{n}_foot", f"{n}_foot")
    add_transform(sk, [f"{n}_foot"], f"ik_{n}", name=f"tc_{n}_foot", mix_rotate=1, mix_x=0, mix_y=0,
                  mix_scale_x=0, mix_scale_y=0, mix_shear_y=0)


def make_gait_test_rig(out_dir: str | Path, kind: str = "hexapod", name: str | None = None) -> Project:
    """A small rigged test animal for the generic gait: ``hexapod`` (an insect side view: body, 6 two-bone legs
    with IK targets ik_L1..ik_R3) or ``biped`` (a torso on two legs, ik_L / ik_R). Body bone: ``body``.
    Far-side (L) legs are darker and drawn behind the body."""
    if kind not in ("hexapod", "biped"):
        raise ValueError("kind is hexapod|biped")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sk = new_skeleton(width=400, height=260)
    p = Project(out / f"{name or kind}.json", sk)
    if kind == "hexapod":
        sk.add_bone_world("body", "root", 0, 62, 0)
        for side in "LR":
            sh = np.array((8.0, 5.0)) if side == "L" else np.zeros(2)
            cols = ((60, 60, 60), (30, 30, 30)) if side == "L" else ((90, 80, 70), (40, 34, 30))
            for k, (hx, kx, fx) in enumerate([(36, 78, 118), (0, 18, 44), (-36, -78, -116)], 1):
                J = [tuple(np.add(j, sh)) for j in [(hx, 60), (kx, 112), (fx, 8)]]
                _test_leg(p, f"{side}{k}", J, (6, 5, 3), cols, (J[2][0], J[2][1] - 4, 5, 4), ow=1.5)
            if side == "L":
                b = [(0, 64, 58, 20), (70, 70, 18, 16), (-56, 64, 34, 20)]
                im, c = _part(_ellipses(b), _ell_bbox(b), (90, 170, 110), (40, 100, 60))
                _add_part(p, "body", im, c)
                reparent_slot(sk, "body", "body")
    else:
        sk.add_bone_world("body", "root", 0, 104, 0)
        for side in "LR":
            sh = np.array((6.0, 3.0)) if side == "L" else np.zeros(2)
            J = [tuple(np.add(j, sh)) for j in [(0, 104), (13, 60), (0, 14)]]
            cols = ((70, 70, 90), (40, 40, 60)) if side == "L" else ((110, 110, 140), (60, 60, 90))
            _test_leg(p, side, J, (15, 11, 8), cols, (J[2][0] + 10, J[2][1] - 6, 18, 8))
            if side == "L":
                tor = [(0, 112), (4, 190)]
                im, c = _part(_capsule(tor, [30, 34]), _bbox_of(tor, [30, 34]), (90, 120, 200), (50, 70, 140))
                _add_part(p, "torso", im, c)
                sk.add_bone_world("torso", "body", 0, 112, 90, 78)
                reparent_slot(sk, "torso", "torso")
    p.save()
    return p
