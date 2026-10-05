"""Creature rigs: ``rig_creature(project, kind=...)`` rigs a non-humanoid creature from its layers and builds its clip set,
by COMPOSING the existing rigs (rig_gait's gait / rig_quadruped, rig_chain's serpents and wings, rig_addons' clip merge,
fx_recipes) instead of re-implementing them.

    slime     one mesh on a core + 6-8 outline bones with soft physics: idle (jiggle), hop, hit, win
    golem     rigid rock parts with gaps, each lagging its parent on a critically damped filter, glowing seams:
              idle (grind), stomp (screen-shake event), hit
    ghost     a strand-chain body with physics, no legs, bob + sway from two incommensurate periods closed exactly
              over the loop, alpha breathing, trailing wisps: idle, swoop, fade_out, fade_in
    tentacle  N rig_serpent tentacle chains off a core with reach IK on the tips, suckers that swap with stretch:
              idle (each tentacle its own phase), reach (grab), slam
    dragon    rig_quadruped body + serpent neck and tail + bat wings + a generated fire flipbook from the mouth:
              idle, walk (gait), fly (flap), breath, roar
    insect    6 legs on the insect tripod gait, antenna strands, a generated wing-blur flipbook: idle, walk, fly
    plant     branches as strands, root IK feet, leaves as physics fans, diffusion-limited growth: idle (sway), grow,
              attack
    mimic     a treasure chest with a spring hinge lid, a tongue strand, teeth: idle (breathing crack), open (reveal),
              bite, land and win (the juice_apply contract)

Every part is found BY LAYER NAME (``CREATURE_LAYERS[kind]``; case-insensitive, the last ``group/`` part of a
flattened PSD name counts, ``_l``/``_r`` sides). Missing optional parts are skipped (reported), a missing required
part is a clear ValueError that lists the convention. ``make_sample_creature(out_dir, kind)`` draws a procedural
sample named exactly as import_psd would name a PSD that follows the convention.

Exaggerated real physics, as modelled:

* slime: squash conserves VOLUME (a 3D blob seen from the side: scaleX = scaleY^-1/2, so scaleY 0.7 -> scaleX 1.195;
  ``law="area"`` gives the flat 2D rule scaleX = 1/scaleY). The hop is anticipation squash, push-off stretch, a
  ballistic parabola (apex exactly ``hop_height``) with the stretch following the speed |v| (round at the apex), a
  short compression on impact, then the splat recovers on an exact underdamped spring (peak exactly
  1 + (1 - splat) exp(-pi z / sqrt(1 - z^2))). The outline wobbles in Rayleigh's drop modes: mode n rings at
  f_n ~ sqrt(n (n - 1) (n + 2)), so mode 3 rings 1.936 x faster than mode 2, each a damped spring on every outline
  bone (radial), over Spine physics on the same bones.
* golem: heavy parts lag their parent through a critically (or over-) damped second-order filter, x'' + 2 z w0 x' +
  w0^2 x = w0^2 u with z >= 1 (no overshoot ever: the step response is monotonic), w0 = 1 / lag; a level deeper
  (fists on arms) is filtered again, so lag grows by levels. The stomp rises slowly (heavy: slow attack), drops on a
  gravity parabola, compresses and recovers critically damped; the seams flash with a 1/t decay.
* ghost: bob and sway run at two incommensurate periods (default 1.7 s and 2.9 s); the loop length is the shortest
  D with D = n1 P1' = n2 P2' and every period within 5% of its target, so the drift never repeats inside the loop
  yet the loop closes exactly. The body leans into its motion (drag), the sheet trails with a travelling wave, the
  alpha breathes with the bob; swoop is a dive along a smooth path with the tail streaming opposite the velocity.
* tentacle: each tentacle is a rig_serpent tentacle chain with its own phase; reach is rig_serpent's
  constant-curvature strike on an exact spring with IK closing the grab; the slam whips (the bend travels base ->
  tip) and recoils on an exact spring kick.
* dragon: rig_quadruped's gait and clips, the neck and tail as serpent chains (travelling waves), the wings flap with
  rig_flier's warped-sine stroke (downstroke 58%, lag down the joints) while the legs tuck. The fire jet grows like a
  starting turbulent jet (front ~ sqrt(t)), spreads at a constant half-angle, cools along its length and curls up on
  buoyancy; the flipbook's noise is periodic so it loops exactly.
* insect: rig_gait's alternating tripod; the wing beat is far above the frame rate, so the wings become a generated
  motion-blur flipbook (the wing swept over its stroke arc).
* plant: idle sway is a wind-loaded cantilever (rotation grows up the trunk, branches lag by levels, leaves flutter);
  grow is diffusion-limited like frost dendrites: ds/dt = k / s, so s = sqrt(2 k t): tips race then slow, and a
  branch of length L takes L^2 / (2 k) (one shared k); leaves pop on an exact spring.
* mimic: the lid hinge is a spring (open overshoots exactly), a closing lid falls under gravity and bounces off the
  rim with restitution e (each bounce e^2 as high), the tongue is a strand with physics.

Clip contract (rig_chain.merge_clips merges by name): loops close exactly, one-shots end exactly on the setup pose,
except ``fade_out`` (ends invisible, bones on setup: ``fade_in`` starts there) and ``grow`` (starts tiny, ends on
setup). Dense LINEAR keys of closed-form functions of time. Events: ``sfx_<clip>`` at the clip's moment (hop: ``sfx_hop``
at launch and ``sfx_land``), ``sfx_step`` (string = foot) on footfalls, ``screen_shake`` (float = amplitude in px,
int = duration in ms) on stomps, slams and roars, the FX events (``fx_shine``, ``fx_fire``) and the rigs' own
(``sfx_reach``, ``sfx_flap``).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .ir import RegionAttachment, Sequence, SkeletonData, Slot, color_hex, new_skeleton, parse_color
from .mesh import region_pixel_to_local, rig_mesh, to_local
from .project import Project
from .rig import add_ik, reparent_slot
from .rig_chain import (ClipSpec, Sheet, _dist_to, add_phys, base_name, chain_on_slot, ellipse_poly, event,
                        find_prefixed, find_slot, frame_bone, merge_clips, put, slot_bounds, smooth, spring_kick,
                        spring_overshoot, spring_step, strip_shape, times)
from .timeline import AnimBuilder

KINDS = ("slime", "golem", "ghost", "tentacle", "dragon", "insect", "plant", "mimic")

# ------------------------------------------------------------------ naming conventions (case-insensitive)
CREATURE_LAYERS: dict[str, dict[str, str]] = {
    "slime": {
        "body": "REQUIRED (aliases slime, blob). The whole blob as ONE layer; becomes one mesh on a core + outline bones.",
        "eye_l, eye_r (or eye)": "optional; each gets a bone for blinks and squints.",
        "mouth, shine, highlight, face*": "optional; ride the core.",
        "shadow": "optional ground shadow; stays on the ground, shrinks and fades with the hop height.",
    },
    "golem": {
        "torso": "REQUIRED (aliases body, chest). The main boulder; its bottom centre is the body pivot.",
        "head": "optional; lags the torso (one level).",
        "arm_l, arm_r": "optional (aliases shoulder_*, upper_arm_*); hang from the end nearest the torso, lag one level.",
        "fist_l, fist_r": "optional (aliases hand_*, forearm_*); hang from the arm, lag two levels.",
        "leg_l, leg_r, foot_l, foot_r": "optional pillars under the torso (the stomp lifts leg_r).",
        "rock*, boulder*, stone*": "optional floating pieces; bob and lag the torso.",
        "crack*, seam*, rune*, vein*, magma*": "optional; each gets an additive glow slot generated from its art.",
        "eye*": "optional; ride the head and glow like the seams.",
    },
    "ghost": {
        "body": "REQUIRED (aliases ghost, sheet, spirit). One tall layer: the head at the top, the tail trailing below.",
        "eye*, mouth, face*, cheek*, brow*": "optional; ride the head (the first chain bone).",
        "arm_l, arm_r": "optional 2-bone strands with physics.",
        "wisp*, trail*, tendril*": "optional trailing strands with physics, rooted at the end nearest the body.",
        "aura, glow": "optional; ride the float bone and breathe with the body.",
    },
    "tentacle": {
        "core": "REQUIRED (aliases body, head, mantle). The central mass.",
        "tentacle<N>": "REQUIRED, at least one (tentacle1, tentacle_2 ...): each a rig_serpent tentacle chain, rooted "
                       "at the end nearest the core.",
        "eye*, mouth, beak, brow*": "optional; ride the core.",
        "sucker, sucker_stretched": "optional TEMPLATE art: cloned onto every tentacle as attachments that swap to "
                                    "the stretched one while the tentacle stretches (the template layers are hidden; "
                                    "a missing stretched art is generated).",
    },
    "dragon": {
        "body, head, {front|hind}_{upper|lower|mid|foot}_{L|R}": "REQUIRED: the rig_quadruped convention "
                                                                "(rig_gait.QUADRUPED_LAYERS); ears, eyes, horns, snout "
                                                                "and the other quadruped parts work as there.",
        "neck": "optional long neck: a serpent chain from the shoulders that carries the head.",
        "tail": "optional long tail: a serpent chain from the hips with physics on its last bones.",
        "wing_l, wing_r": "optional bat wings (far, near): 3-bone chains on the shoulders.",
        "jaw": "optional lower jaw: hinged at its back end, opens in roar and breath.",
    },
    "insect": {
        "thorax": "REQUIRED (alias body). The gait body bone sits at its centre.",
        "leg_{L|R}{1|2|3}_{upper|lower}": "REQUIRED, 12 layers. 1 = front, 3 = hind; L = far side (behind), R = near. "
                                          "upper = femur (hip -> knee), lower = tibia (knee -> foot).",
        "head": "optional; eye*, mandible*, mouth ride it.",
        "abdomen": "optional; a 2-bone strand with physics behind the thorax (stinger rides it).",
        "antenna_l, antenna_r (or antenna)": "optional 3-bone strands with antenna physics.",
        "wing_l, wing_r (or wing)": "optional; folded in the setup, a generated motion-blur flipbook in fly.",
    },
    "plant": {
        "trunk": "REQUIRED (aliases stem, body). Vertical, rooted at the bottom; a 3-bone chain.",
        "branch*": "optional strands rooted on the trunk (3 bones, stiff physics on the tip).",
        "root*": "optional root legs: 2-bone chains with IK feet planted on the ground.",
        "leaf*, leaves*, foliage*, canopy*": "optional; one bone + physics each, on the nearest branch: a fan.",
        "eye*, mouth, face*, brow*": "optional; ride the top of the trunk.",
        "flower*, fruit*": "optional; ride the nearest branch bone.",
    },
    "mimic": {
        "base": "REQUIRED (aliases chest, box). The box; its bottom centre is the body pivot.",
        "lid": "REQUIRED. Hinged at its bottom back corner (the back is away from the lock, else -x).",
        "inside, mouth": "optional dark interior; rides the base, covered by the closed lid.",
        "teeth_upper, teeth_lower (teeth*, tooth*)": "optional; upper ride the lid, lower the base (by position).",
        "tongue": "optional strand with physics.",
        "eye*": "optional; in the dark interior (ride the base), glint in the crack.",
        "gold*, coin*, treasure*": "optional; ride the base (revealed when the lid opens).",
        "lock, latch, trim*, strap*": "optional; ride the part they sit on.",
    },
}

CREATURE_CLIPS = {
    "slime": ("idle", "hop", "hit", "win"),
    "golem": ("idle", "stomp", "hit"),
    "ghost": ("idle", "swoop", "fade_out", "fade_in"),
    "tentacle": ("idle", "reach", "slam"),
    "dragon": ("idle", "walk", "fly", "breath", "roar"),
    "insect": ("idle", "walk", "fly"),
    "plant": ("idle", "grow", "attack"),
    "mimic": ("idle", "open", "bite", "land", "win"),
}
LOOPS = {"idle", "walk", "fly"}

# options per kind: {name: (default, what)}
OPTIONS: dict[str, dict[str, tuple[Any, str]]] = {
    "slime": dict(n_outline=(8, "outline bones around the blob (6-8 reads best; 3..12)"),
                  squash=(0.7, "anticipation scaleY (0.3..0.95)"), stretch=(1.25, "push-off / flight stretch scaleY"),
                  splat=(0.6, "landing splat scaleY before the spring recovers"),
                  hop_height=(0.9, "hop apex in body heights"), flight=(0.5, "time in the air (s)"),
                  law=("volume", "volume: scaleX = scaleY^-1/2 (a 3D blob) | area: scaleX = 1/scaleY"),
                  hz=(2.6, "mode-2 wobble / landing spring frequency (Hz)"), zeta=(0.28, "landing spring damping ratio"),
                  idle=(2.4, "idle loop length (s)")),
    "golem": dict(lag=(0.12, "lag time constant per level (s): 1/w0"),
                  zeta=(1.0, "lag damping ratio, >= 1 (1 critical, > 1 over-damped: never overshoots)"),
                  shake=(14.0, "screen_shake amplitude (px) on the stomp"), glow_color=("FF7A1C", "seam glow colour"),
                  idle=(4.0, "idle loop length (s)")),
    "ghost": dict(bob=(1.7, "bob period target (s)"), sway=(2.9, "sway period target (s)"),
                  tolerance=(0.05, "how far each period may move to close the loop (fraction)"),
                  max_loop=(12.0, "longest idle loop allowed (s)"), n_bones=(5, "bones down the body"),
                  breathe=(0.22, "alpha breathing depth (0..0.6)")),
    "tentacle": dict(n_bones=(6, "bones per tentacle"), reach=(None, "[x, y] reach goal in the reaching tentacle's frame"),
                     reach_tentacle=(-1, "index of the tentacle that reaches (-1: the one whose tip is frontmost)"),
                     shake=(10.0, "screen_shake amplitude (px) on the slam"), idle=(3.0, "idle loop length (s)")),
    "dragon": dict(leg_type=("digitigrade", "rig_quadruped leg type"), flap_hz=(1.6, "fly wing beats per second"),
                   fire_frames=(8, "fire flipbook frames"), fire_length=(1.6, "fire jet length in body lengths"),
                   shake=(12.0, "screen_shake amplitude (px) on the roar"), neck_bones=(4, "neck serpent bones"),
                   tail_bones=(6, "tail serpent bones")),
    "insect": dict(gait=("tripod", "tripod | wave (rig_gait hexapod gaits)"), speed=(0.0, "walk speed (0 = the gait's)"),
                   blur_frames=(6, "wing-blur flipbook frames"), stroke=(70.0, "wing stroke arc (deg)"),
                   lift=(0.9, "fly hover height in leg lengths")),
    "plant": dict(grow=(2.6, "grow clip length (s)"), sway=(4.0, "idle loop length (s)"),
                  wind=(1.0, "sway strength"), shake=(8.0, "screen_shake amplitude (px) on the attack")),
    "mimic": dict(crack=(7.0, "idle breathing crack (deg)"), open_angle=(105.0, "open angle (deg)"),
                  zeta=(0.32, "hinge spring damping ratio (open overshoot)"), restitution=(0.3, "lid bounce restitution"),
                  juice=(True, "add land and win through the juice_apply contract")),
}


def _opts(kind: str, options: dict | None) -> dict:
    d = OPTIONS[kind]
    P = {k: v[0] for k, v in d.items()}
    bad = [k for k in (options or {}) if k not in P]
    if bad:
        raise ValueError(f"unknown option(s) {bad} for creature {kind!r}; valid: {sorted(P)}")
    P.update(options or {})
    return P


def list_kinds() -> dict:
    return {k: {"layers": CREATURE_LAYERS[k], "clips": list(CREATURE_CLIPS[k]),
                "options": {o: {"default": v[0], "what": v[1]} for o, v in OPTIONS[k].items()}} for k in KINDS}


def _missing(kind: str, missing: list[str], sk: SkeletonData) -> ValueError:
    conv = "; ".join(f"{k}: {v}" for k, v in CREATURE_LAYERS[kind].items())
    return ValueError(f"rig_creature {kind}: missing required layer(s) {missing}. Naming convention (case-insensitive, "
                      f"last group/ part counts): {conv}. Slots in the project: {[s.name for s in sk.slots]}")


def _find(sk: SkeletonData, *names: str) -> str | None:
    return find_slot(sk, *names)


def _side(slot: str) -> str:
    b = base_name(slot)
    for suf, s in (("_l", "l"), ("_left", "l"), ("_r", "r"), ("_right", "r")):
        if b.endswith(suf):
            return s
    return ""


# ------------------------------------------------------------------ art geometry
def alpha_fn(project: Project, slot: str):
    """Vectorised alpha (0..1) of a region slot's art at world points (0 outside the image)."""
    sk = project.data
    s = sk.slot(slot)
    att = sk.attachment(slot)
    if not isinstance(att, RegionAttachment):
        raise ValueError(f"{slot!r} is a {att.type}; this rig reads the region layer (run it before meshing)")
    im = project.image(project.att_image_name(slot, s.attachment))
    A = np.asarray(im)[:, :, 3].astype(float) / 255
    _, inv = region_pixel_to_local(att, *im.size)
    wb = sk.world()[s.bone]

    def f(pts):
        P = np.atleast_2d(np.asarray(pts, float))
        px = inv(to_local(wb, P))
        i, j = np.floor(px[:, 0]).astype(int), np.floor(px[:, 1]).astype(int)
        ok = (i >= 0) & (i < im.width) & (j >= 0) & (j < im.height)
        out = np.zeros(len(P))
        out[ok] = A[j[ok], i[ok]]
        return out
    return f


def art_points(project: Project, slot: str, step: int = 2, thr: float = 0.3) -> np.ndarray:
    """World positions of the opaque pixels of a region slot (subsampled)."""
    from .mesh import to_world
    sk = project.data
    s = sk.slot(slot)
    att = sk.attachment(slot)
    im = project.image(project.att_image_name(slot, s.attachment))
    A = np.asarray(im)[::step, ::step, 3].astype(float) / 255
    ys, xs = np.nonzero(A > thr)
    if not len(xs):
        raise ValueError(f"layer {slot!r} is empty")
    f, _ = region_pixel_to_local(att, *im.size)
    return to_world(sk.world()[s.bone], f(np.c_[xs * step + 0.5, ys * step + 0.5]))


def art_bounds(project: Project, slot: str) -> tuple[float, float, float, float]:
    P = art_points(project, slot)
    return float(P[:, 0].min()), float(P[:, 1].min()), float(P[:, 0].max()), float(P[:, 1].max())


def art_center(project: Project, slot: str) -> tuple[float, float]:
    x0, y0, x1, y1 = art_bounds(project, slot)
    return (x0 + x1) / 2, (y0 + y1) / 2


def art_axis(project: Project, slot: str) -> tuple[np.ndarray, np.ndarray]:
    """The two ends of a part's principal axis (world), from its opaque pixels."""
    P = art_points(project, slot)
    c = P.mean(0)
    _, _, vt = np.linalg.svd(P - c, full_matrices=False)
    t = (P - c) @ vt[0]
    return c + vt[0] * t.min(), c + vt[0] * t.max()


def ray_radius(project: Project, slot: str, c, ang_deg: float, rmax: float) -> float:
    """Distance from c to the art's edge along a ray (the last opaque sample)."""
    f = alpha_fn(project, slot)
    u = np.array([math.cos(math.radians(ang_deg)), math.sin(math.radians(ang_deg))])
    r = np.linspace(0, rmax, max(16, int(rmax)))
    a = f(np.asarray(c, float)[None] + r[:, None] * u[None])
    idx = np.nonzero(a > 0.5)[0]
    return float(r[idx[-1]]) if len(idx) else 0.0


def nearest_part(project: Project, point, slots: list[str]) -> str:
    """The slot whose art covers ``point`` most (alpha), else the one whose centre is nearest."""
    best, ba = None, 0.0
    for s in slots:
        a = float(alpha_fn(project, s)(np.asarray(point, float)[None])[0])
        if a > ba:
            best, ba = s, a
    if best is not None and ba > 0.3:
        return best
    return min(slots, key=lambda s: math.dist(art_center(project, s), point))


def reparent_bone(sk: SkeletonData, bone: str, parent: str) -> None:
    """Move a bone under another parent without moving it (world kept), keeping parents before children."""
    from .rig import _depth_order
    w = sk.world()
    b, p = sk.bone(bone), w[parent]
    cw = w[bone]
    lx, ly = p.to_local(cw.x, cw.y)
    b.parent = parent
    b.x, b.y = round(lx, 3), round(ly, 3)
    b.rotation = round((cw.rotation - p.rotation + 180) % 360 - 180, 3)
    sk.reorder_bones(_depth_order(sk))


# ------------------------------------------------------------------ closed-form motion helpers
def ring(t: float, hz: float, zeta: float) -> float:
    """Free vibration from an initial displacement of 1: e^(-z w t) cos(wd t) (0 before t = 0)."""
    if t < 0:
        return 0.0
    w0 = 2 * math.pi * hz
    return math.exp(-zeta * w0 * t) * math.cos(w0 * math.sqrt(max(1 - zeta * zeta, 1e-9)) * t)


def spring_peak_time(hz: float, zeta: float) -> float:
    """Time of the first peak of the underdamped step response: pi / wd."""
    return 0.5 / (hz * math.sqrt(1 - zeta * zeta))


def bump(t: float, t0: float, w: float) -> float:
    """sin(pi u) on [t0, t0 + w], 0 elsewhere."""
    u = (t - t0) / w
    return math.sin(math.pi * u) if 0 <= u <= 1 else 0.0


def end_env(t: float, D: float, frac: float = 0.15) -> float:
    return 1 - smooth(t, D * (1 - frac), D)


def squash_x(sy: float, law: str = "volume") -> float:
    """scaleX that keeps the volume (3D blob: sx = sy^-1/2) or the area (2D: sx = 1/sy) for a scaleY."""
    sy = max(sy, 1e-3)
    return sy ** -0.5 if law == "volume" else 1.0 / sy


def lowpass(u: np.ndarray, dt: float, w0: float, zeta: float) -> np.ndarray:
    """Exact zero-order-hold discretisation of x'' + 2 z w0 x' + w0^2 x = w0^2 u (from rest), sampled like u."""
    from scipy.linalg import expm
    A = np.array([[0.0, 1.0], [-w0 * w0, -2 * zeta * w0]])
    B = np.array([0.0, w0 * w0])
    Phi = expm(A * dt)
    G = np.linalg.solve(A, (Phi - np.eye(2)) @ B)
    s = np.zeros(2)
    out = np.empty_like(u)
    for k, uk in enumerate(u):
        out[k] = s[0]
        s = Phi @ s + G * uk
    return out


def lagged(fn, D: float, w0: float, zeta: float, loop: bool, levels: int = 1, dt: float = 1 / 1200):
    """A function of t: the driver fn(t) passed ``levels`` times through the critically damped filter. Loops are run
    from three periods before 0 so the result is the periodic steady state (it then closes exactly)."""
    pre = 3 * D if loop else 0.0
    tt = np.arange(-pre, D + dt, dt)
    u = np.array([fn(t % D if loop else max(t, 0.0)) for t in tt])
    if not loop:
        u[tt < 0] = fn(0.0)
    y = u
    for _ in range(levels):
        y = lowpass(y - y[0], dt, w0, zeta) + y[0]
    return lambda t: float(np.interp(t, tt, y))


def color_track(ab: AnimBuilder, slot: str, ts, fn, loop: bool = False) -> None:
    """rgba keys of fn(t) -> (r, g, b, a) in 0..1, linear."""
    pts = [(t, color_hex(*fn(t))) for t in ts]
    if loop:
        pts[-1] = (pts[-1][0], pts[0][1])
    ab.slot_color(slot, pts, "linear")


def shown(ab: AnimBuilder, slot: str, pts) -> None:
    ab.slot_attachment(slot, pts)


def _setup_rgba(sk: SkeletonData, slot: str):
    return parse_color(sk.slot(slot).color)


def _write_tex(project: Project, name: str, make) -> tuple[int, int]:
    try:
        im = project.image(name)
    except FileNotFoundError:
        im = make()
        project.write_image(name, im)
    return im.size


def _add_fx_slot(sk: SkeletonData, name: str, bone: str, att_name: str, att: RegionAttachment, blend: str = "additive",
                 after: str | None = None, color: str = "FFFFFFFF") -> str:
    """A slot hidden in the setup pose (clips switch it on); additive slots go to the top of the draw order."""
    nm = sk.unique_name(name, "slot")
    sl = Slot(name=nm, bone=bone, color=color, blend=blend)
    if after:
        sk.add_slot(sl, after=after)
    else:
        sk.add_slot(sl)
    sk.set_attachment(nm, att_name, att)
    return nm


def _last_normal(sk: SkeletonData) -> str:
    return [s.name for s in sk.slots if s.blend == "normal"][-1]


def glow_image(im: Image.Image, color: str, radius: float = 6.0) -> tuple[Image.Image, int]:
    """An additive glow from a part's own alpha: a blurred halo around a white-hot copy of the shape. Returns the image
    and the padding added on each side."""
    from .fx_recipes import _blur, _colorize, _palette
    a = np.asarray(im)[:, :, 3].astype(np.float32) / 255
    pad = int(math.ceil(3 * radius))
    A = np.pad(a, pad)
    g = np.clip(0.75 * A + 1.4 * _blur(A, radius) + 0.5 * _blur(A, radius * 2.2), 0, 1)
    hot, mid, edge = _palette(color.lstrip("#")[:6])
    return _colorize(g, hot, mid, edge), pad


def ensure_tex(project: Project, name: str) -> tuple[int, int]:
    from .fx_recipes import WHITE_TEX
    return _write_tex(project, name, WHITE_TEX[name])


# ------------------------------------------------------------------ the shared clip runner
def _specs_filter(kind: str, specs: list[ClipSpec], clips) -> list[ClipSpec]:
    if clips is None:
        return specs
    names = [clips] if isinstance(clips, str) else list(clips)
    bad = [c for c in names if c not in CREATURE_CLIPS[kind]]
    if bad:
        raise ValueError(f"unknown clip(s) {bad} for {kind}; one of {list(CREATURE_CLIPS[kind])}")
    return [s for s in specs if s.name in names]


def _counts(sk: SkeletonData) -> dict:
    return {"bones": len(sk.bones), "slots": len(sk.slots), "ik": len(sk.ik), "transform": len(sk.transform),
            "physics": len(sk.physics)}


# ================================================================== 1. slime
RAYLEIGH_3_2 = math.sqrt(3 * 2 * 5 / (2 * 1 * 4))       # f3 / f2 for a drop: sqrt(n (n-1) (n+2)) ratio = 1.936


def _rig_slime(project: Project, P: dict, seed: int, X: float, clips) -> dict:
    sk = project.data
    body = _find(sk, "body", "slime", "blob")
    if not body:
        raise _missing("slime", ["body"], sk)
    N = int(P["n_outline"])
    if not 3 <= N <= 12:
        raise ValueError("n_outline must be 3..12 (6-8 reads best)")
    law = str(P["law"])
    if law not in ("volume", "area"):
        raise ValueError("law is volume | area")
    sq, st, splat = float(P["squash"]), float(P["stretch"]), float(P["splat"])
    if not 0.3 <= sq <= 0.95 or not 1.0 <= st <= 2.0 or not 0.3 <= splat <= 0.95:
        raise ValueError("squash and splat must be 0.3..0.95, stretch 1.0..2.0")
    hz, z = float(P["hz"]), float(P["zeta"])
    if hz <= 0 or not 0.05 <= z < 1:
        raise ValueError("hz must be > 0 and zeta 0.05..0.99 (underdamped: the splat overshoots)")
    flight = float(P["flight"])
    if flight <= 0.1:
        raise ValueError("flight (time in the air) must be > 0.1 s")
    x0, y0, x1, y1 = art_bounds(project, body)
    W_, H_ = x1 - x0, y1 - y0
    c = np.array(((x0 + x1) / 2, y0 + 0.45 * H_))
    frame = frame_bone(sk, "slime", "root", c[0], y0, 0.0, color="00E1FFFF")
    hop = frame_bone(sk, "slime_hop", frame, c[0], y0, 0.0, color="FFD400FF")
    core = frame_bone(sk, "slime_core", hop, c[0], c[1], 0.0)
    rmax = 1.2 * max(W_, H_)
    outline, R, ang = [], [], []
    for k in range(N):
        a = 90.0 + 360.0 * k / N
        r = ray_radius(project, body, c, a, rmax)
        if r <= 1:
            raise ValueError(f"slime body has no art at {a:.0f} deg from its centre")
        u = np.array([math.cos(math.radians(a)), math.sin(math.radians(a))])
        nm = sk.unique_name(f"slime_o{k + 1}")
        h = c + 0.42 * r * u
        sk.add_bone_world(nm, core, float(h[0]), float(h[1]), a, 0.53 * r)
        outline.append(nm)
        R.append(r)
        ang.append(math.radians(a))
    reparent_slot(sk, body, core)
    eyes = []
    riders = []
    shadow = _find(sk, "shadow")
    for s in list(sk.slots):
        b = base_name(s.name)
        if s.name in (body, shadow) or not s.attachment:
            continue
        if b.startswith("eye") or b.startswith("pupil"):
            ex, ey = art_center(project, s.name)
            eb = frame_bone(sk, f"slime_{b}", core, ex, ey, 0.0)
            reparent_slot(sk, s.name, eb)
            eyes.append(eb)
        elif b.startswith(("shine", "highlight", "gloss")):            # near the rim: rides the nearest outline bone
            hx, hy = art_center(project, s.name)
            a = math.degrees(math.atan2(hy - c[1], hx - c[0]))
            k = int(round((a - 90.0) / (360.0 / N))) % N
            reparent_slot(sk, s.name, outline[k])
            riders.append(s.name)
        elif b.startswith(("mouth", "face", "cheek", "blush", "brow")):
            reparent_slot(sk, s.name, core)
            riders.append(s.name)
    sh_bone = None
    if shadow:
        sx_, sy_ = art_center(project, shadow)
        sh_bone = frame_bone(sk, "slime_shadow", frame, sx_, sy_, 0.0)
        reparent_slot(sk, shadow, sh_bone)
    mesh = rig_mesh(project, body, bones=[core, *outline], detail=1.0)
    phys = add_phys(sk, outline, "jiggle", taper=0.0, inertia=0.35, strength=260, damping=0.82, mix=0.7)
    Rm = float(np.mean(R))
    hop_h = float(P["hop_height"]) * H_ * X

    def outline_keys(ab, ts, radial, loop):
        """radial(k, t) -> fraction of R_k: each outline bone moves along its own spoke."""
        for k, b in enumerate(outline):
            ca, sa = math.cos(ang[k]), math.sin(ang[k])
            put(ab, b, "translate", ts, lambda t, k=k, ca=ca, sa=sa: (R[k] * radial(k, t) * ca, R[k] * radial(k, t) * sa), loop)

    def body_keys(ab, ts, sy_fn, y_fn, loop, rot_fn=None):
        put(ab, hop, "scale", ts, lambda t: (squash_x(sy_fn(t), law), sy_fn(t)), loop)
        put(ab, hop, "translate", ts, lambda t: (0.0, y_fn(t)), loop)
        if rot_fn is not None:
            put(ab, hop, "rotate", ts, rot_fn, loop)
        if sh_bone:
            put(ab, sh_bone, "scale", ts, lambda t: ((1 - 0.5 * y_fn(t) / max(hop_h, 1e-6)),) * 2, loop)
            color_track(ab, shadow, ts, lambda t: (1, 1, 1, max(0.0, 1 - 0.6 * y_fn(t) / max(hop_h, 1e-6))), loop)

    def eye_keys(ab, ts, fn, loop):
        for e in eyes:
            put(ab, e, "scale", ts, lambda t: (1.0, fn(t)), loop)

    def hop_curve(t, ta, Tf, H, sq_, st_, splat_):
        """(y, sy) of one hop starting at 0: anticipation squash, push-off stretch, parabola (stretch ~ |v|), impact
        compression, spring recovery."""
        tl, tc = ta + Tf, 0.05
        if t < 0.8 * ta:
            return 0.0, 1 + (sq_ - 1) * smooth(t, 0, 0.8 * ta)
        if t < ta:
            return 0.0, sq_ + (st_ - sq_) * smooth(t, 0.8 * ta, ta)
        if t < tl:
            q = (t - ta) / Tf
            return 4 * H * q * (1 - q), 1 + (st_ - 1) * abs(1 - 2 * q)
        if t < tl + tc:
            return 0.0, st_ + (splat_ - st_) * (t - tl) / tc
        return 0.0, splat_ + (1 - splat_) * spring_step(t - tl - tc, hz, z)

    specs = []
    Didle = float(P["idle"])

    def idle(ab, D, env):
        ts = times(D, 40)
        n2 = max(1, round(D * 1.25))
        sy = lambda t: 1 + 0.035 * X * math.sin(2 * math.pi * t / D)  # noqa: E731   a slow breath
        body_keys(ab, ts, sy, lambda t: 0.0, True)
        outline_keys(ab, ts, lambda k, t: X * (0.03 * math.sin(2 * math.pi * n2 * t / D) * math.cos(2 * ang[k])
                                               + 0.014 * math.cos(3 * ang[k] - 2 * math.pi * t / D)), True)
        rng = np.random.default_rng(seed)
        tb = float(rng.uniform(0.35, 0.75)) * D
        eye_keys(ab, times(D, 40, [tb + 0.07]), lambda t: 1 - 0.9 * bump(t, tb, 0.14), True)
        if eyes:
            event(ab, tb, "sfx_idle", string="blink")
        return {"breath_period": round(D, 4), "jiggle_cycles": n2, "blink": round(tb, 4)}
    specs.append(ClipSpec("idle", "loop", Didle, idle))

    ta = 0.3

    def hopclip(ab, D, env):
        Tf = flight
        tl = ta + Tf
        tp = tl + 0.05 + spring_peak_time(hz, z)
        ts = times(D, 60, [0.8 * ta, ta, ta + Tf / 2, tl, tl + 0.05, tp])
        e = lambda t: end_env(t, D, 0.12)  # noqa: E731
        yy = lambda t: hop_curve(t, ta, Tf, hop_h, sq, st, splat)[0] * e(t)  # noqa: E731
        sy = lambda t: 1 + (hop_curve(t, ta, Tf, hop_h, sq, st, splat)[1] - 1) * e(t)  # noqa: E731
        body_keys(ab, ts, sy, yy, False)
        outline_keys(ab, ts, lambda k, t: X * e(t) * (0.08 * ring(t - tl, hz, z) * math.cos(2 * ang[k])
                                                      + 0.03 * ring(t - tl, hz * RAYLEIGH_3_2, z) * math.sin(3 * ang[k])
                                                      - 0.03 * bump(t, 0, ta) * math.cos(2 * ang[k])), False)
        put(ab, core, "translate", ts, lambda t: (0.0, -0.08 * Rm * X * spring_kick(t - tl, 0.8 * hz, 0.35) * e(t)))
        eye_keys(ab, ts, lambda t: 1 - 0.55 * bump(t, 0.05, ta) - 0.6 * bump(t, tl, 0.2) + 0.12 * bump(t, ta, Tf), False)
        event(ab, ta, "sfx_hop")
        event(ab, tl, "sfx_land")
        g = 8 * hop_h / Tf ** 2
        return {"launch": ta, "land": round(tl, 4), "apex": round(hop_h, 2), "gravity": round(g, 2),
                "splat_peak": round(1 + (1 - splat) * spring_overshoot(z), 4), "splat_peak_time": round(tp, 4),
                "squash": sq, "squash_x": round(squash_x(sq, law), 4), "law": law}
    specs.append(ClipSpec("hop", "oneshot", round(ta + flight + 0.65, 4), hopclip))

    def hit(ab, D, env):
        ts = times(D, 60)
        e = lambda t: end_env(t, D, 0.15)  # noqa: E731
        k_ = lambda t: spring_kick(t, 3.0, 0.3) * e(t)  # noqa: E731
        put(ab, core, "translate", ts, lambda t: (-0.16 * Rm * X * k_(t), 0.0))
        body_keys(ab, ts, lambda t: 1 + 0.12 * X * k_(t), lambda t: 0.0, False)
        outline_keys(ab, ts, lambda k, t: X * e(t) * (-0.1 * ring(t, 1.1 * hz, z) * math.cos(2 * ang[k])
                                                      - 0.2 * math.exp(-(((ang[k] + math.pi) % (2 * math.pi) - math.pi) / 0.7) ** 2)
                                                      * spring_kick(t, hz, 0.4)), False)
        eye_keys(ab, ts, lambda t: 1 - 0.85 * bump(t, 0.0, 0.4), False)
        f = lambda t: math.exp(-t / 0.1) * smooth(t, 0, 0.02) * e(t)  # noqa: E731
        r0, g0, b0, a0 = _setup_rgba(sk, body)
        color_track(ab, body, ts, lambda t: (r0, g0 * (1 - 0.3 * f(t)), b0 * (1 - 0.3 * f(t)), a0))
        event(ab, 0.0, "sfx_hit")
        return {"kick_hz": 3.0}
    specs.append(ClipSpec("hit", "oneshot", 0.9, hit))

    def win(ab, D, env):
        h1 = dict(ta=0.16, Tf=0.34, H=0.45 * hop_h, sq_=1 - 0.6 * (1 - sq), st_=1 + 0.8 * (st - 1), splat_=1 - 0.6 * (1 - splat))
        t2 = 0.75
        ts = times(D, 60, [h1["ta"], t2 + h1["ta"]])

        def one(t):
            return hop_curve(t, h1["ta"], h1["Tf"], h1["H"], h1["sq_"], h1["st_"], h1["splat_"])

        def yy(t):
            a = one(t)[0] if t < t2 else 0.0
            b = one(t - t2)[0] if t >= t2 else 0.0
            return (a + b) * end_env(t, D, 0.12)

        def sy(t):
            a = (one(t)[1] - 1) * (1 - smooth(t, t2 - 0.08, t2))
            b = (one(t - t2)[1] - 1) if t >= t2 else 0.0
            return 1 + (a + b) * end_env(t, D, 0.12)
        tilt = lambda t: 9 * X * (bump(t, h1["ta"], h1["Tf"]) - bump(t, t2 + h1["ta"], h1["Tf"]))  # noqa: E731
        body_keys(ab, ts, sy, yy, False, rot_fn=tilt)
        tl1, tl2 = h1["ta"] + h1["Tf"], t2 + h1["ta"] + h1["Tf"]
        outline_keys(ab, ts, lambda k, t: X * end_env(t, D, 0.12) * 0.06 * (ring(t - tl1, hz, z) + ring(t - tl2, hz, z))
                     * math.cos(2 * ang[k]), False)
        eye_keys(ab, ts, lambda t: 1 - 0.55 * smooth(t, 0.05, 0.2) * (1 - smooth(t, D - 0.3, D - 0.05)), False)
        event(ab, h1["ta"], "sfx_win")
        return {"hops": 2, "launches": [h1["ta"], round(t2 + h1["ta"], 4)]}
    specs.append(ClipSpec("win", "oneshot", 1.7, win))

    made = {"bones": {"frame": frame, "hop": hop, "core": core, "outline": outline, "eyes": eyes, "shadow": sh_bone},
            "slot": body, "riders": riders, "mesh_vertices": mesh.get("vertices"), "physics": phys,
            "radii": [round(r, 2) for r in R], "law": law}
    made["clips"] = merge_clips(sk, _specs_filter("slime", specs, clips))
    return made


# ================================================================== 2. golem
def _rig_golem(project: Project, P: dict, seed: int, X: float, clips) -> dict:
    sk = project.data
    torso = _find(sk, "torso", "body", "chest")
    if not torso:
        raise _missing("golem", ["torso"], sk)
    lag, z = float(P["lag"]), float(P["zeta"])
    if lag <= 0:
        raise ValueError("lag (time constant per level) must be > 0 s")
    if z < 1:
        raise ValueError("zeta must be >= 1: a golem is heavy (critically or over-damped, it never overshoots)")
    w0 = 1.0 / lag
    tx0, ty0, tx1, ty1 = art_bounds(project, torso)
    Ht = ty1 - ty0
    tc = np.array(((tx0 + tx1) / 2, (ty0 + ty1) / 2))
    parts = [s.name for s in sk.slots if s.attachment]
    legs = {sd: _find(sk, f"leg_{sd}") for sd in "lr"}
    feet = {sd: _find(sk, f"foot_{sd}") for sd in "lr"}
    gy = min(art_bounds(project, s)[1] for s in parts)
    frame = frame_bone(sk, "golem", "root", tc[0], gy, 0.0, color="00E1FFFF")
    body = frame_bone(sk, "golem_body", frame, tc[0], ty0, 0.0, color="FFD400FF")
    reparent_slot(sk, torso, body)
    lagged_parts: list[tuple[str, str, int]] = []         # (bone, parent driver bone, level)
    made_parts = {}
    head = _find(sk, "head")
    hb = None
    if head:
        hx0, hy0, hx1, hy1 = art_bounds(project, head)
        hb = frame_bone(sk, "golem_head", body, (hx0 + hx1) / 2, hy0, 0.0)
        reparent_slot(sk, head, hb)
        lagged_parts.append((hb, body, 1))
        made_parts["head"] = hb
    arms = {}
    for sd in "lr":
        arm = _find(sk, f"arm_{sd}", f"shoulder_{sd}", f"upper_arm_{sd}")
        fist = _find(sk, f"fist_{sd}", f"hand_{sd}", f"forearm_{sd}")
        par, lvl = body, 1
        if arm:
            a0, a1 = art_axis(project, arm)
            top = a0 if math.dist(a0, tc) <= math.dist(a1, tc) else a1
            bot = a1 if top is a0 else a0
            ab_ = frame_bone(sk, f"golem_arm_{sd}", body, float(top[0]), float(top[1]), 0.0)
            sk.bone(ab_).length = round(float(np.hypot(*(bot - top))), 3)
            reparent_slot(sk, arm, ab_)
            lagged_parts.append((ab_, body, 1))
            arms[sd] = ab_
            made_parts[f"arm_{sd}"] = ab_
            par, lvl = ab_, 2
        if fist:
            f0, f1 = art_axis(project, fist)
            ref = np.array(sk.world()[par].tail) if par != body else tc
            top = f0 if math.dist(f0, ref) <= math.dist(f1, ref) else f1
            fb = frame_bone(sk, f"golem_fist_{sd}", par, float(top[0]), float(top[1]), 0.0)
            reparent_slot(sk, fist, fb)
            lagged_parts.append((fb, par, lvl))
            made_parts[f"fist_{sd}"] = fb
    leg_bones = {}
    for sd in "lr":
        if legs[sd]:
            lx0, ly0, lx1, ly1 = art_bounds(project, legs[sd])
            lb = frame_bone(sk, f"golem_leg_{sd}", frame, (lx0 + lx1) / 2, ly1, 0.0)
            reparent_slot(sk, legs[sd], lb)
            leg_bones[sd] = lb
            if feet[sd]:
                reparent_slot(sk, feet[sd], lb)
    rocks = []
    for i, rs in enumerate(find_prefixed(sk, "rock", "boulder", "stone")):
        rx, ry = art_center(project, rs)
        rb = frame_bone(sk, f"golem_rock{i + 1}", body, rx, ry, 0.0)
        reparent_slot(sk, rs, rb)
        rocks.append(rb)
        lagged_parts.append((rb, body, 1))
    eyes = [s for s in find_prefixed(sk, "eye") if s]
    for e in eyes:
        reparent_slot(sk, e, hb or body)
    # glowing seams: one additive slot per crack (and eye), generated from the art, riding the same part
    seams = find_prefixed(sk, "crack", "seam", "rune", "vein", "magma")
    host_parts = [s for s in (torso, head, *[x for x in (_find(sk, f"arm_{q}", f"shoulder_{q}") for q in "lr") if x],
                              *[x for x in (_find(sk, f"fist_{q}", f"hand_{q}") for q in "lr") if x]) if s]
    for s in seams:
        cx_, cy_ = art_center(project, s)
        host = nearest_part(project, (cx_, cy_), host_parts) if host_parts else torso
        reparent_slot(sk, s, sk.slot(host).bone)
    glows = []
    gcol = str(P["glow_color"]).lstrip("#")
    for s in seams + eyes:
        att = sk.attachment(s)
        im = project.image(project.att_image_name(s, sk.slot(s).attachment))
        gi, pad = glow_image(im, gcol, 5.0)
        tex = f"creature/golem_glow_{base_name(s)}"
        project.write_image(tex, gi)
        kx, ky = att.width / im.width, att.height / im.height
        ga = RegionAttachment(path=tex, x=att.x, y=att.y, rotation=att.rotation, width=round(gi.width * kx, 2),
                              height=round(gi.height * ky, 2))
        glows.append(_add_fx_slot(sk, f"{base_name(s)}_glow", sk.slot(s).bone, "glow", ga))
    # dust for the stomp: normal-blend cloud puffs right after the art (same batch), hidden in setup
    stomp_leg = leg_bones.get("r") or leg_bones.get("l")
    foot_pt = np.array((sk.world()[stomp_leg].x, gy)) if stomp_leg else np.array((tc[0], gy))
    ensure_tex(project, "fx/cloud")
    dust = []
    after = _last_normal(sk)
    for i in range(5):
        db = frame_bone(sk, f"golem_dust{i + 1}", frame, float(foot_pt[0]), float(foot_pt[1]) + 0.06 * Ht, 0.0)
        sl = _add_fx_slot(sk, f"golem_dust{i + 1}", db, "dust",
                          RegionAttachment(path="fx/cloud", width=round(0.55 * Ht, 2), height=round(0.55 * Ht, 2)),
                          blend="normal", after=after, color="B8AC9EFF")
        after = sl
        dust.append((db, sl))
    for g in glows:
        sk.slot(g).attachment = None
    gw_rng = np.random.default_rng(seed + 3)
    grind = {b: (int(gw_rng.choice([7, 9, 11, 13])), float(gw_rng.uniform(0, 2 * math.pi))) for b, _, _ in lagged_parts}

    def key_lag(ab, D, ts, drv, loop, extra_rot=None, extra_tr=None):
        """drv: {'x','y','rot'} -> functions of t for the body. Each lagged part's local keys make its absolute motion
        the filtered copy of its parent's (levels deep)."""
        for ch in ("x", "y", "rot"):
            drv.setdefault(ch, lambda t: 0.0)
        put(ab, body, "translate", ts, lambda t: (drv["x"](t), drv["y"](t)), loop)
        put(ab, body, "rotate", ts, drv["rot"], loop)
        cache = {}
        for b, par, lvl in lagged_parts:
            for ch in ("x", "y", "rot"):
                lo, hi = (cache.setdefault((ch, lvl - 1), lagged(drv[ch], D, w0, z, loop, lvl - 1)) if lvl > 1 else drv[ch],
                          cache.setdefault((ch, lvl), lagged(drv[ch], D, w0, z, loop, lvl)))
                cache[(b, ch)] = (lo, hi)
            ex = (extra_rot or {}).get(b, lambda t: 0.0)
            et = (extra_tr or {}).get(b, lambda t: (0.0, 0.0))
            fin = (lambda t: 1.0) if loop else (lambda t: end_env(t, D, 0.12))     # a one-shot ends exactly on setup
            put(ab, b, "rotate", ts, lambda t, b=b, ex=ex: (cache[(b, "rot")][1](t) - cache[(b, "rot")][0](t)) * fin(t) + ex(t), loop)
            put(ab, b, "translate", ts, lambda t, b=b, et=et: ((cache[(b, "x")][1](t) - cache[(b, "x")][0](t)) * fin(t) + et(t)[0],
                                                               (cache[(b, "y")][1](t) - cache[(b, "y")][0](t)) * fin(t) + et(t)[1]), loop)

    def glow_keys(ab, ts, fn, loop=False):
        for g in glows:
            shown(ab, g, [(0.0, "glow")])
            color_track(ab, g, ts, lambda t: (1, 1, 1, min(1.0, max(0.0, fn(t)))), loop)

    specs = []

    def idle(ab, D, env):
        ts = times(D, 30)
        drv = {"y": lambda t: -0.012 * Ht * X * (1 - math.cos(4 * math.pi * t / D)) / 2,
               "rot": lambda t: 1.0 * X * math.sin(2 * math.pi * t / D)}
        extra = {b: (lambda t, k=k, ph=ph: 0.5 * X * math.sin(2 * math.pi * k * t / D + ph)) for b, (k, ph) in grind.items()}
        bob = {rb: (lambda t, ph=2 * math.pi * (0.37 * i + 0.1): (0.0, 0.035 * Ht * X * math.sin(2 * math.pi * t / D + ph)))
               for i, rb in enumerate(rocks)}
        key_lag(ab, D, ts, drv, True, extra, bob)
        glow_keys(ab, ts, lambda t: 0.5 + 0.4 * (1 - math.cos(4 * math.pi * t / D)) / 2, True)
        for k in (0.25, 0.75):
            event(ab, k * D, "sfx_idle", string="grind")
        return {"breaths": 2, "lag_w0": round(w0, 4), "zeta": z, "grind_cycles": sorted({k for k, _ in grind.values()})}
    specs.append(ClipSpec("idle", "loop", float(P["idle"]), idle))

    t_up, t_s = 0.62, 0.8

    def stomp(ab, D, env):
        Hup, comp, lam = 0.11 * Ht * X, 0.05 * Ht * X, 7.0
        ts = times(D, 60, [t_up, t_s])
        e = lambda t: end_env(t, D, 0.12)  # noqa: E731

        def y(t):
            if t < t_up:
                return Hup * smooth(t, 0.04, t_up)
            if t < t_s:
                q = (t - t_up) / (t_s - t_up)
                return Hup - (Hup + comp) * q * q                    # a free fall from rest: a parabola
            tau = t - t_s
            return -comp * (1 + lam * tau) * math.exp(-lam * tau) * e(t)   # critically damped recovery: no bounce
        lean = lambda t: 4.0 * X * smooth(t, 0.04, t_up) * (1 - smooth(t, t_up, t_s + 0.25)) * e(t)  # noqa: E731
        swing = {}
        for sd, b in arms.items():
            out = 1.0 if sk.world()[b].x < tc[0] else -1.0         # +1: the arm hangs on the left
            swing[b] = (lambda t, out=out: -out * X * (20 * smooth(t, 0.04, t_up) - 26 * smooth(t, t_up, t_s)
                                                        + 6 * smooth(t, t_s, t_s + 0.5)) * e(t))
        key_lag(ab, D, ts, {"y": y, "rot": lean}, False, swing)
        if stomp_leg:
            Lup = 0.22 * Ht * X

            def ly(t):
                if t < t_up:
                    return Lup * smooth(t, 0.04, t_up)
                if t < t_s:
                    q = (t - t_up) / (t_s - t_up)
                    return Lup * (1 - q * q)
                return 0.0
            put(ab, stomp_leg, "translate", ts, lambda t: (0.0, ly(t)))
            put(ab, stomp_leg, "rotate", ts, lambda t: -4.0 * X * smooth(t, 0.04, t_up) * (1 - smooth(t, t_up, t_s)))
        base = 0.5
        glow_keys(ab, ts, lambda t: base - 0.25 * smooth(t, 0, t_up) * (1 - smooth(t, t_up, t_s))
                  + (1.0 - base) * (t >= t_s) / (1 + 10 * max(0.0, t - t_s)) * e(t))
        rng = np.random.default_rng(seed + 11)
        td = times(D, 40, [t_s])
        for i, (db, sl) in enumerate(dust):
            a = math.pi * (i + 0.5) / len(dust)
            v0, kd = 1.6 * Ht * X * float(rng.uniform(0.8, 1.2)), 4.0
            dirx, diry = math.cos(a), 0.35 * math.sin(a)
            dd = lambda t, dirx=dirx, diry=diry, v0=v0: (v0 * dirx * (1 - math.exp(-kd * max(0.0, t - t_s))) / kd,  # noqa: E731
                                                         v0 * diry * (1 - math.exp(-kd * max(0.0, t - t_s))) / kd)
            put(ab, db, "translate", td, lambda t, dd=dd: dd(t) if t < D - 1e-6 else (0.0, 0.0))
            put(ab, db, "scale", td, lambda t: ((0.35 + 1.0 * (1 - math.exp(-3.0 * max(0.0, t - t_s)))) if t < D - 1e-6 else 1.0,) * 2)
            color_track(ab, sl, td, lambda t: (0.72, 0.67, 0.62, 0.9 * (t >= t_s) * math.exp(-1.6 * max(0.0, t - t_s)) * e(t)))
            shown(ab, sl, [(0.0, None), (t_s, "dust"), (D - 0.02, None)])
        event(ab, t_s, "sfx_stomp")
        event(ab, t_s, "screen_shake", float=float(P["shake"]) * X, int=350)
        return {"impact": t_s, "rise": round(Hup, 2), "compression": round(comp, 2), "screen_shake": float(P["shake"]) * X}
    specs.append(ClipSpec("stomp", "oneshot", 1.8, stomp))

    def hit(ab, D, env):
        ts = times(D, 60)
        th = 0.08
        imp = lambda t: (t / th) * math.exp(1 - t / th) * end_env(t, D, 0.12) if t > 0 else 0.0  # noqa: E731   critically damped impulse
        key_lag(ab, D, ts, {"rot": lambda t: -9.0 * X * imp(t), "x": lambda t: -0.08 * Ht * X * imp(t)}, False)
        glow_keys(ab, ts, lambda t: 0.5 + 0.5 * math.exp(-t / 0.08) * math.cos(2 * math.pi * 9 * t) ** 2 * end_env(t, D, 0.12))
        event(ab, 0.0, "sfx_hit")
        return {"impulse_peak_time": th}
    specs.append(ClipSpec("hit", "oneshot", 1.1, hit))

    made = {"bones": {"frame": frame, "body": body, **made_parts, "legs": leg_bones, "rocks": rocks},
            "lagged": [{"bone": b, "parent": p, "level": lvl} for b, p, lvl in lagged_parts], "glows": glows,
            "dust": [s for _, s in dust], "lag": {"w0": round(w0, 4), "zeta": z, "time_constant": lag}}
    made["clips"] = merge_clips(sk, _specs_filter("golem", specs, clips))
    return made


# ================================================================== 3. ghost
def close_periods(P1: float, P2: float, tol: float = 0.05, max_D: float = 12.0) -> tuple[int, int, float]:
    """The shortest loop D = n1 P1' = n2 P2' with both periods within tol of their targets and n1 != n2 (coprime):
    two incommensurate drifts that still close exactly."""
    if P1 <= 0 or P2 <= 0:
        raise ValueError("periods must be > 0")
    best = None
    for n2 in range(1, 40):
        n1 = max(1, round(n2 * P2 / P1))
        if n1 == n2 or math.gcd(n1, n2) != 1:
            continue
        D = (n1 * P1 + n2 * P2) / 2
        e = max(abs(D / n1 / P1 - 1), abs(D / n2 / P2 - 1))
        if e <= tol:
            best = (n1, n2, D)
            break
        if D > max_D:
            break
    if best is None or best[2] > max_D:
        raise ValueError(f"no loop up to {max_D} s closes bob {P1} s and sway {P2} s within {tol:.0%}; raise max_loop or tolerance")
    return best


def _rig_ghost(project: Project, P: dict, seed: int, X: float, clips) -> dict:
    sk = project.data
    body = _find(sk, "body", "ghost", "sheet", "spirit")
    if not body:
        raise _missing("ghost", ["body"], sk)
    nb = int(P["n_bones"])
    if not 3 <= nb <= 10:
        raise ValueError("n_bones must be 3..10")
    br = float(P["breathe"])
    if not 0 <= br <= 0.6:
        raise ValueError("breathe (alpha depth) must be 0..0.6")
    n1, n2, Dl = close_periods(float(P["bob"]), float(P["sway"]), float(P["tolerance"]), float(P["max_loop"]))
    x0, y0, x1, y1 = art_bounds(project, body)
    Wb, Hb = x1 - x0, y1 - y0
    frame = frame_bone(sk, "ghost", "root", (x0 + x1) / 2, (y0 + y1) / 2, 0.0, color="00E1FFFF")
    flt = frame_bone(sk, "ghost_float", frame, (x0 + x1) / 2, y1 - 0.25 * Hb, 0.0, color="FFD400FF")
    reparent_slot(sk, body, flt)
    chain, pts = chain_on_slot(project, body, nb, flt, "ghost_", root_end="top")
    phys = add_phys(sk, chain[1:], "cloth", taper=0.12)
    riders = []
    for s in sk.slots:
        b = base_name(s.name)
        if s.name != body and b.startswith(("eye", "mouth", "face", "cheek", "brow", "blush", "pupil")):
            reparent_slot(sk, s.name, chain[0])
            riders.append(s.name)
    poly = pts.tolist()
    strands = {}
    for s in [x for x in (_find(sk, "arm_l"), _find(sk, "arm_r")) if x] + find_prefixed(sk, "wisp", "trail", "tendril"):
        c = art_center(project, s)
        w = sk.world()
        par = min(chain, key=lambda b: _dist_to(c, [w[b].head, w[b].tail]))
        n = 2 if base_name(s).startswith("arm") else 3
        sb, _ = chain_on_slot(project, s, n, par, f"ghost_{base_name(s)}_", root_near=poly, detail=0.7)
        phys += add_phys(sk, sb, "hair", strength=90, damping=0.9)
        strands[s] = sb
    aura = _find(sk, "aura", "glow")
    if aura:
        reparent_slot(sk, aura, flt)
    ghost_slots = [body, *strands, *([aura] if aura else [])]
    face_slots = riders
    n = len(chain)

    def alpha_keys(ab, ts, fn, loop, slots_=None):
        for s in (slots_ or ghost_slots + face_slots):
            r0, g0, b0, a0 = _setup_rgba(sk, s)
            color_track(ab, s, ts, lambda t, r0=r0, g0=g0, b0=b0, a0=a0: (r0, g0, b0, a0 * fn(t)), loop)

    def chain_keys(ab, ts, psi, loop):
        """psi(i, t): absolute bend of chain bone i (deg); keys are the increments down the chain."""
        for i, b in enumerate(chain):
            put(ab, b, "rotate", ts, lambda t, i=i: psi(i, t) - (psi(i - 1, t) if i else 0.0), loop)

    specs = []

    def idle(ab, D, env):
        k1, k2 = n1, n2
        if abs(D - Dl) > 1e-6:                              # merged into a host clip of another length: refit
            k1, k2 = max(1, round(D / float(P["bob"]))), max(1, round(D / float(P["sway"])))
        w1, w2 = 2 * math.pi * k1 / D, 2 * math.pi * k2 / D
        ts = times(D, 30)
        put(ab, flt, "translate", ts, lambda t: (0.05 * Hb * X * math.sin(w2 * t), 0.06 * Hb * X * math.sin(w1 * t)), True)
        put(ab, flt, "rotate", ts, lambda t: -4.0 * X * math.cos(w2 * t), True)          # leans into the sway (drag)
        chain_keys(ab, ts, lambda i, t: X * (i / max(n - 1, 1)) * (9.0 * math.cos(w2 * t - 0.75 * i)
                                                                    + 4.0 * math.sin(w1 * t - 0.9 * i)), True)
        alpha_keys(ab, ts, lambda t: 1 - br * (1 - math.cos(w1 * t)) / 2, True, ghost_slots)
        return {"loop": round(D, 4), "bob": {"cycles": k1, "period": round(D / k1, 4)},
                "sway": {"cycles": k2, "period": round(D / k2, 4)}, "ratio": f"{k1}:{k2}"}
    specs.append(ClipSpec("idle", "loop", round(Dl, 4), idle))

    def swoop(ab, D, env):
        knots = [(0.0, 0.0, 0.0), (0.28 * D, -0.2 * Wb, 0.14 * Hb), (0.56 * D, 0.65 * Wb, -0.24 * Hb),
                 (0.8 * D, 0.22 * Wb, 0.1 * Hb), (D, 0.0, 0.0)]
        kt = np.array([k[0] for k in knots])
        kp = np.array([[k[1] * X, k[2] * X] for k in knots])
        kv = np.zeros_like(kp)
        for i in range(1, len(knots) - 1):
            kv[i] = (kp[i + 1] - kp[i - 1]) / (kt[i + 1] - kt[i - 1])

        def path(t):
            i = int(np.clip(np.searchsorted(kt, t) - 1, 0, len(kt) - 2))
            h = kt[i + 1] - kt[i]
            s = (t - kt[i]) / h
            h00, h10, h01, h11 = 2 * s ** 3 - 3 * s ** 2 + 1, s ** 3 - 2 * s ** 2 + s, -2 * s ** 3 + 3 * s ** 2, s ** 3 - s ** 2
            d00, d10, d01, d11 = 6 * s ** 2 - 6 * s, 3 * s ** 2 - 4 * s + 1, -6 * s ** 2 + 6 * s, 3 * s ** 2 - 2 * s
            p = h00 * kp[i] + h10 * h * kv[i] + h01 * kp[i + 1] + h11 * h * kv[i + 1]
            v = (d00 * kp[i] + d10 * h * kv[i] + d01 * kp[i + 1] + d11 * h * kv[i + 1]) / h
            return p, v
        tt = np.linspace(0, D, 600)
        sp = [float(np.hypot(*path(t)[1])) for t in tt]
        vmax = max(sp) or 1.0
        tfast = float(tt[int(np.argmax(sp))])
        ts = times(D, 60, [tfast])
        put(ab, flt, "translate", ts, lambda t: tuple(path(t)[0]))
        put(ab, flt, "rotate", ts, lambda t: -16.0 * path(t)[1][0] / vmax)
        lagv = lambda t: path(max(0.0, t - 0.05))[1]  # noqa: E731
        chain_keys(ab, ts, lambda i, t: (i / max(n - 1, 1)) * 28.0 * lagv(t - 0.03 * i)[0] / vmax * end_env(t, D, 0.1), False)
        st = lambda t: 0.12 * float(np.hypot(*path(t)[1])) / vmax  # noqa: E731
        put(ab, flt, "scale", ts, lambda t: (1 / math.sqrt(1 + st(t)), 1 + st(t)))
        event(ab, tfast, "sfx_swoop")
        return {"fastest": round(tfast, 4), "max_speed": round(vmax, 2)}
    specs.append(ClipSpec("swoop", "oneshot", 1.8, swoop))

    def fade_out(ab, D, env):
        tau = 0.3 * D
        ts = times(D, 40)
        a = lambda t: (math.exp(-t / tau) - math.exp(-D / tau)) / (1 - math.exp(-D / tau))  # noqa: E731
        e = lambda t: end_env(t, D, 0.12)  # noqa: E731
        u = lambda t: smooth(t, 0, 0.88 * D) * e(t)  # noqa: E731
        put(ab, flt, "translate", ts, lambda t: (0.0, 0.3 * Hb * X * u(t)))
        put(ab, flt, "scale", ts, lambda t: (1 - 0.35 * u(t), 1 + 0.45 * u(t)))
        chain_keys(ab, ts, lambda i, t: (i / max(n - 1, 1)) * 14.0 * X * math.sin(9 * t - i) * u(t), False)
        alpha_keys(ab, ts, a, False)
        event(ab, 0.0, "sfx_fade_out")
        return {"ends": "invisible (alpha 0), bones on setup", "tau": round(tau, 4)}
    specs.append(ClipSpec("fade_out", "oneshot", 1.0, fade_out))

    def fade_in(ab, D, env):
        tau = 0.28 * D
        ts = times(D, 60)
        a = lambda t: (1 - math.exp(-t / tau)) / (1 - math.exp(-D / tau))  # noqa: E731
        g = lambda t: 1 - spring_step(t, 1.6, 0.38) * (1 - smooth(t, 0.85 * D, D)) - smooth(t, 0.85 * D, D)  # noqa: E731
        put(ab, flt, "scale", ts, lambda t: (1 - 0.4 * g(t), 1 + 0.4 * g(t)))
        put(ab, flt, "translate", ts, lambda t: (0.0, 0.25 * Hb * X * g(t)))
        alpha_keys(ab, ts, a, False)
        event(ab, 0.0, "sfx_fade_in")
        return {"starts": "invisible (alpha 0)", "overshoot": round(spring_overshoot(0.38), 4)}
    specs.append(ClipSpec("fade_in", "oneshot", 1.0, fade_in))

    made = {"bones": {"frame": frame, "float": flt, "chain": chain, "strands": strands}, "riders": riders,
            "physics": phys, "periods": {"bob": float(P["bob"]), "sway": float(P["sway"]), "cycles": [n1, n2],
                                         "loop": round(Dl, 4)}}
    made["clips"] = merge_clips(sk, _specs_filter("ghost", specs, clips))
    return made


# ================================================================== 4. tentacle beast
def _rig_tentacle(project: Project, P: dict, seed: int, X: float, clips) -> dict:
    from .rig_chain import _reach_clip, build_serpent, key_wave
    sk = project.data
    core = _find(sk, "core", "body", "head", "mantle")
    tents = [s for s in find_prefixed(sk, "tentacle")]
    missing = ([] if core else ["core"]) + ([] if tents else ["tentacle<N>"])
    if missing:
        raise _missing("tentacle", missing, sk)
    nb = int(P["n_bones"])
    if not 3 <= nb <= 12:
        raise ValueError("n_bones must be 3..12")
    cx0, cy0, cx1, cy1 = art_bounds(project, core)
    cc = ((cx0 + cx1) / 2, (cy0 + cy1) / 2)
    Hc = cy1 - cy0
    frame = frame_bone(sk, "beast", "root", cc[0], cc[1], 0.0, color="00E1FFFF")
    cb = frame_bone(sk, "beast_core", frame, cc[0], cc[1], 0.0, color="FFD400FF")
    reparent_slot(sk, core, cb)
    riders = []
    for s in sk.slots:
        if s.name != core and base_name(s.name).startswith(("eye", "mouth", "beak", "brow", "pupil", "lid")):
            reparent_slot(sk, s.name, cb)
            riders.append(s.name)
    sucker = _find(sk, "sucker")
    sucker2 = _find(sk, "sucker_stretched")
    widths = {t: alpha_fn(project, t) for t in tents}
    sps = []
    for i, tsl in enumerate(tents):
        sp = build_serpent(project, tsl, nb, cb, f"tent{i + 1}", root_near=cc, detail=0.8)
        sp.reach = add_ik(sk, [sp.bones[-2], sp.bones[-1]], target_parent=sp.frame, mix=0.0)
        sps.append(sp)
    made_suckers = {}
    if sucker:
        im = project.image(project.att_image_name(sucker, sk.slot(sucker).attachment))
        satt = sk.attachment(sucker)
        kx = satt.width / im.width
        if sucker2:
            tex2 = project.att_image_name(sucker2, sk.slot(sucker2).attachment)
            im2 = project.image(tex2)
        else:
            im2 = im.resize((max(2, int(im.width * 1.5)), max(2, int(im.height * 0.7))), Image.LANCZOS)
            tex2 = f"creature/{base_name(sucker)}_stretched"
            project.write_image(tex2, im2)
        tex1 = project.att_image_name(sucker, sk.slot(sucker).attachment)
        for i, (tsl, sp) in enumerate(zip(tents, sps)):
            w = sk.world()
            after = tsl
            for j in [j for j in (1, 3) if j < nb - 1]:
                bw = w[sp.bones[j]]
                mid = np.array(bw.to_world(bw.length / 2, 0))
                nrm = np.array(bw.to_world(bw.length / 2, -1)) - mid
                nrm = nrm / max(float(np.hypot(*nrm)), 1e-9)
                hw = 0.0
                for r_ in np.linspace(0, 80, 81):
                    if widths[tsl]((mid + nrm * r_)[None])[0] > 0.5:
                        hw = float(r_)
                size = max(6.0, 0.75 * hw)
                sc = size / (im.width * kx)
                nm = _add_fx_slot(sk, f"tent{i + 1}_sucker{j}", sp.bones[j], "sucker",
                                  RegionAttachment(path=tex1, x=round(bw.length / 2, 2), y=round(-0.45 * hw, 2),
                                                   width=round(im.width * kx * sc, 2), height=round(im.height * kx * sc, 2)),
                                  blend="normal", after=after)
                sk.set_attachment(nm, "sucker_stretched", RegionAttachment(
                    path=tex2, x=round(bw.length / 2, 2), y=round(-0.4 * hw, 2), width=round(im2.width * kx * sc, 2),
                    height=round(im2.height * kx * sc, 2)))
                sk.slot(nm).attachment = "sucker"
                made_suckers.setdefault(tsl, []).append(nm)
                after = nm
        sk.slot(sucker).attachment = None                    # the template layers are hidden (cloned above)
        if sucker2:
            sk.slot(sucker2).attachment = None
    w = sk.world()
    tips = [np.array(w[sp.bones[-1]].tail) for sp in sps]
    bases = [np.array(w[sp.bones[0]].head) for sp in sps]
    lift = [1.0 if (tp - bs)[0] > 0.05 * sp.L or ((tp - bs)[0] > -0.05 * sp.L and bs[0] >= cc[0]) else -1.0
            for tp, bs, sp in zip(tips, bases, sps)]
    m = int(P["reach_tentacle"])
    if m < 0:
        m = int(np.argmax([tp[0] for tp in tips]))
    if m >= len(sps):
        raise ValueError(f"reach_tentacle {m} is out of range (0..{len(sps) - 1})")
    reach_spec = _reach_clip(sps[m], sk, P["reach"])
    phases = [2 * math.pi * ((0.618 * i + 0.1) % 1.0) for i in range(len(sps))]
    specs = []

    def idle(ab, D, env):
        ts = times(D, 30)
        for i, sp in enumerate(sps):
            c_ = 1 + (i % 2)
            lam = 1.3 * sp.L
            A = lambda s, sp=sp: 0.07 * sp.L * X * (0.1 + 0.9 * (s / sp.L) ** 2)  # noqa: E731
            y = lambda s, t, A=A, lam=lam, c_=c_, ph=phases[i]: A(s) * math.sin(2 * math.pi * (s / lam - c_ * t / D) + ph)  # noqa: E731
            key_wave(ab, sp, ts, y, True, heading=lambda t, ph=phases[i]: 5.0 * X * math.sin(2 * math.pi * t / D + ph), recoil=0.0)
        put(ab, cb, "translate", ts, lambda t: (0.0, 0.03 * Hc * X * math.sin(2 * math.pi * t / D)), True)
        put(ab, cb, "scale", ts, lambda t: (squash_x(1 + 0.025 * X * math.sin(2 * math.pi * t / D + 0.6)),
                                            1 + 0.025 * X * math.sin(2 * math.pi * t / D + 0.6)), True)
        return {"phases": [round(p, 4) for p in phases], "cycles": [1 + (i % 2) for i in range(len(sps))]}
    specs.append(ClipSpec("idle", "loop", float(P["idle"]), idle))

    def reach(ab, D, env):
        info = reach_spec.build(ab, D, env)
        a_end, s_end, h_end = 0.22 * D, 0.42 * D, 0.72 * D
        g = lambda t: smooth(t, a_end, s_end) * (1 - smooth(t, h_end, D))  # noqa: E731
        ts = times(D, 60, [a_end, s_end, h_end])
        sp = sps[m]
        put(ab, sp.bones[0], "scale", ts, lambda t: (1 + 0.14 * X * g(t), 1 - 0.05 * X * g(t)))
        on = [t for t in np.linspace(0, D, 801) if g(t) > 0.43]
        if on and made_suckers.get(tents[m]):
            for s in made_suckers[tents[m]]:
                shown(ab, s, [(0.0, "sucker"), (round(float(on[0]), 4), "sucker_stretched"), (round(float(on[-1]), 4), "sucker")])
        d = tips[m] - np.array(cc)
        d = d / max(float(np.hypot(*d)), 1e-9)
        put(ab, cb, "translate", ts, lambda t: tuple(0.05 * sp.L * X * g(t) * d))
        for i, o in enumerate(sps):
            if i == m:
                continue
            for j, b in enumerate(o.bones):
                put(ab, b, "rotate", ts, lambda t, i=i, j=j: -lift[i] * 4.0 * X * (j + 1) / nb * bump(t, 0.05 * D, 0.75 * D))
        event(ab, s_end, "sfx_grab")
        info.update(tentacle=tents[m], stretch=round(1 + 0.14 * X, 4),
                    sucker_swap=[round(float(on[0]), 4), round(float(on[-1]), 4)] if on else None)
        return info
    specs.append(ClipSpec("reach", "oneshot", 1.6, reach))

    def slam(ab, D, env):
        t_up, t_s = 0.45 * D, 0.62 * D
        up, dn = 38.0 * X, 16.0 * X
        dl = 0.028

        def th(t):
            if t < t_up:
                return up * smooth(t, 0.04 * D, t_up)
            if t < t_s:
                q = (t - t_up) / (t_s - t_up)
                return up - (up + dn) * q * q                 # accelerating down like a falling whip
            return -dn * ring(t - t_s, 2.4, 0.3)
        ts = times(D, 60, [t_up, t_s])
        e = lambda t: end_env(t, D, 0.15)  # noqa: E731
        for i, sp in enumerate(sps):
            sg = lift[i]
            put(ab, sp.drive, "rotate", ts, lambda t, sg=sg: sg * th(t) * e(t))
            for j, b in enumerate(sp.bones):
                put(ab, b, "rotate", ts, lambda t, j=j, sg=sg: sg * 0.6 * (th(t - (j + 1) * dl) - th(t - j * dl)) * e(t))
        dy = lambda t: (0.05 * Hc * smooth(t, 0.04 * D, t_up) * (1 - smooth(t, t_up, t_s))  # noqa: E731
                        - 0.07 * Hc * spring_kick(t - t_s, 2.5, 0.4)) * X * e(t)
        put(ab, cb, "translate", ts, lambda t: (0.0, dy(t)))
        sq = lambda t: 1 - 0.12 * X * spring_kick(t - t_s, 2.5, 0.4) * e(t)  # noqa: E731
        put(ab, cb, "scale", ts, lambda t: (squash_x(sq(t)), sq(t)))
        event(ab, t_s, "sfx_slam")
        event(ab, t_s, "screen_shake", float=float(P["shake"]) * X, int=300)
        return {"impact": round(t_s, 4), "lift_signs": lift, "whip_delay": dl}
    specs.append(ClipSpec("slam", "oneshot", 1.5, slam))

    made = {"bones": {"frame": frame, "core": cb}, "riders": riders,
            "tentacles": {t: {"bones": sp.bones, "frame": sp.frame, "drive": sp.drive, "reach_ik": sp.reach["constraint"],
                              "length": round(sp.L, 2)} for t, sp in zip(tents, sps)},
            "suckers": made_suckers, "reach_tentacle": tents[m]}
    made["clips"] = merge_clips(sk, _specs_filter("tentacle", specs, clips))
    return made


# ================================================================== 6. insect
def wing_blur_frames(im: Image.Image, root_px, elevation: float, frames: int, arc: float, raise_sign: float,
                     lighten: float = 0.35) -> tuple[list[Image.Image], int]:
    """Motion-blur flipbook of a beating wing: frame k smears the wing over its share of the stroke (rotations about the
    root pixel, raised by ``elevation`` and swept over ``arc`` degrees) over a faint ghost of the whole arc. The canvas
    is square, centred on the root. Returns (frames, canvas size)."""
    L = int(math.ceil(max(math.dist(root_px, c) for c in ((0, 0), (im.width, 0), (0, im.height), (im.width, im.height)))))
    S = 2 * L + 8
    base = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    base.paste(im, (int(round(S / 2 - root_px[0])), int(round(S / 2 - root_px[1]))))

    def rot(a):
        return np.asarray(base.rotate(a, resample=Image.BICUBIC, center=(S / 2, S / 2)), np.float32) / 255
    sub = 9
    ghost = np.mean([rot(raise_sign * a) for a in np.linspace(elevation - arc / 2, elevation + arc / 2, 15)], 0)
    out = []
    tri = lambda u: 1 - 4 * abs((u % 1.0) - 0.5)  # noqa: E731   a triangle wave: every frame sweeps the same arc
    for k in range(frames):
        a0 = elevation + arc / 2 * tri(k / frames)
        a1 = elevation + arc / 2 * tri((k + 1.5) / frames)
        acc = np.mean([rot(raise_sign * a) for a in np.linspace(a0, a1, sub)], 0)
        rgba = np.zeros_like(acc)
        alpha = np.clip(1.5 * acc[..., 3] + 0.6 * ghost[..., 3], 0, 0.9)
        wsum = acc[..., 3] + 0.4 * ghost[..., 3] + 1e-6
        rgb = (acc[..., :3] * acc[..., 3:4] + 0.4 * ghost[..., :3] * ghost[..., 3:4]) / wsum[..., None]
        rgba[..., :3] = rgb + (1 - rgb) * lighten
        rgba[..., 3] = alpha
        out.append(Image.fromarray(np.clip(rgba * 255, 0, 255).astype(np.uint8), "RGBA"))
    return out, S


def _rig_insect(project: Project, P: dict, seed: int, X: float, clips) -> dict:
    from .rig_gait import gait as gait_fn
    sk = project.data
    thorax = _find(sk, "thorax", "body")
    legs = {}
    missing = [] if thorax else ["thorax"]
    for S_ in "LR":
        for k in (1, 2, 3):
            up = _find(sk, f"leg_{S_}{k}_upper")
            lo = _find(sk, f"leg_{S_}{k}_lower")
            if not up:
                missing.append(f"leg_{S_}{k}_upper")
            if not lo:
                missing.append(f"leg_{S_}{k}_lower")
            legs[f"{S_}{k}"] = (up, lo, _find(sk, f"leg_{S_}{k}_foot"))
    if missing:
        raise _missing("insect", missing, sk)
    g_name = str(P["gait"])
    if g_name not in ("tripod", "wave"):
        raise ValueError("gait is tripod | wave")
    K = int(P["blur_frames"])
    if not 2 <= K <= 24:
        raise ValueError("blur_frames must be 2..24")
    tc = np.array(art_center(project, thorax))
    head = _find(sk, "head")
    facing = 1.0
    if head:
        facing = 1.0 if art_center(project, head)[0] >= tc[0] else -1.0
    gy = min(art_bounds(project, lg[1])[1] for lg in legs.values())
    frame = frame_bone(sk, "insect", "root", float(tc[0]), gy, 0.0, color="00E1FFFF")
    bodyb = frame_bone(sk, "insect_body", frame, float(tc[0]), float(tc[1]), 0.0, color="FFD400FF")
    reparent_slot(sk, thorax, bodyb)
    hb = None
    if head:
        h0, h1 = art_axis(project, head)
        piv = h0 if math.dist(h0, tc) <= math.dist(h1, tc) else h1
        far = h1 if piv is h0 else h0
        hb = frame_bone(sk, "insect_head", bodyb, float(piv[0]), float(piv[1]),
                        math.degrees(math.atan2(*(far - piv)[::-1])))
        sk.bone(hb).length = round(float(np.hypot(*(far - piv))), 3)
        reparent_slot(sk, head, hb)
    riders = []
    for s in sk.slots:
        if s.name != head and base_name(s.name).startswith(("eye", "mandible", "mouth", "jaw", "proboscis")):
            reparent_slot(sk, s.name, hb or bodyb)
            riders.append(s.name)
    abd = _find(sk, "abdomen")
    abd_bones, phys = [], []
    if abd:
        abd_bones, _ = chain_on_slot(project, abd, 2, bodyb, "abdomen_", root_near=tuple(tc), detail=0.8)
        phys += add_phys(sk, abd_bones, "tail", strength=120)
        st = _find(sk, "stinger")
        if st:
            reparent_slot(sk, st, abd_bones[-1])
    leg_info, gait_legs = {}, []
    for nm, (up, lo, ft) in legs.items():
        u0, u1 = art_axis(project, up)
        hip = u0 if math.dist(u0, tc) <= math.dist(u1, tc) else u1
        kn_a = u1 if hip is u0 else u0
        l0, l1 = art_axis(project, lo)
        kn_b = l0 if math.dist(l0, kn_a) <= math.dist(l1, kn_a) else l1
        foot = l1 if kn_b is l0 else l0
        knee = (kn_a + kn_b) / 2
        bu, bl = f"leg_{nm}_upper", f"leg_{nm}_lower"
        sk.add_bone_world(bu, bodyb, float(hip[0]), float(hip[1]), math.degrees(math.atan2(*(knee - hip)[::-1])),
                          float(np.hypot(*(knee - hip))))
        sk.add_bone_world(bl, bu, float(knee[0]), float(knee[1]), math.degrees(math.atan2(*(foot - knee)[::-1])),
                          float(np.hypot(*(foot - knee))))
        tgt = f"ik_{nm}"
        sk.add_bone_world(tgt, frame, float(foot[0]), float(foot[1]), 0.0, color="FF3F00FF")
        add_ik(sk, [bu, bl], target=tgt, name=f"ikc_{nm}")
        reparent_slot(sk, up, bu)
        reparent_slot(sk, lo, bl)
        if ft:
            reparent_slot(sk, ft, bl)
        leg_info[nm] = {"bones": [bu, bl], "target": tgt}
        gait_legs.append({"target": tgt, "side": nm[0], "end": {"1": "front", "2": "middle", "3": "hind"}[nm[1]],
                          "name": nm, "roll": 0.0})
    w = sk.world()
    L_leg = float(np.mean([w[v["bones"][0]].y - w[v["target"]].y for v in leg_info.values()]))
    antennae = {}
    hc = art_center(project, head) if head else tuple(tc)
    for s in [x for x in (_find(sk, "antenna_l"), _find(sk, "antenna_r"), _find(sk, "antenna")) if x]:
        ab_, _ = chain_on_slot(project, s, 3, hb or bodyb, f"antenna{('_' + _side(s)) if _side(s) else ''}_",
                               root_near=hc, detail=0.6)
        phys += add_phys(sk, ab_, "antenna")
        antennae[s] = ab_
    wings = {}
    for s in [x for x in (_find(sk, "wing_l"), _find(sk, "wing_r"), _find(sk, "wing")) if x]:
        w0_, w1_ = art_axis(project, s)
        root = w0_ if math.dist(w0_, tc) <= math.dist(w1_, tc) else w1_
        tip = w1_ if root is w0_ else w0_
        att = sk.attachment(s)
        im = project.image(project.att_image_name(s, sk.slot(s).attachment))
        _, inv = region_pixel_to_local(att, *im.size)
        sb = sk.world()[sk.slot(s).bone]
        rp = inv(to_local(sb, np.array([root])))[0]
        raise_sign = 1.0 if (tip - root)[0] >= 0 else -1.0
        wb = frame_bone(sk, f"insect_wing{('_' + _side(s)) if _side(s) else ''}", bodyb, float(root[0]), float(root[1]),
                        math.degrees(math.atan2(*(tip - root)[::-1])))
        sk.bone(wb).length = round(float(np.hypot(*(tip - root))), 3)
        frames, Sz = wing_blur_frames(im, rp, 55.0, K, float(P["stroke"]), raise_sign)
        reparent_slot(sk, s, wb)
        base_tex = f"creature/{base_name(s)}_blur_"
        for i, f_ in enumerate(frames):
            project.write_image(f"{base_tex}{i:02d}", f_)
        kx = att.width / im.width
        rw = sk.world()[wb].rotation
        sk.set_attachment(s, "blur", RegionAttachment(path=base_tex, width=round(Sz * kx, 2), height=round(Sz * kx, 2),
                                                      rotation=round(-rw, 3), sequence=Sequence(count=K, start=0, digits=2)))
        wings[s] = wb
    specs = []

    def idle(ab, D, env):
        ts = times(D, 30)
        put(ab, bodyb, "translate", ts, lambda t: (0.0, 0.012 * L_leg * X * math.sin(4 * math.pi * t / D)), True)
        if hb:
            put(ab, hb, "rotate", ts, lambda t: 4.0 * X * math.sin(2 * math.pi * t / D + 0.8), True)
        for j, b in enumerate(abd_bones):
            put(ab, b, "rotate", ts, lambda t, j=j: 2.5 * X * math.sin(4 * math.pi * t / D - 0.6 * j), True)
        rng = np.random.default_rng(seed + 5)
        tk = []
        for i, (s, bs) in enumerate(antennae.items()):
            ph = float(rng.uniform(0, 2 * math.pi))
            tw = float(rng.uniform(0.15, 0.55)) * D
            tk.append(tw)
            put(ab, bs[0], "rotate", times(D, 30, [tw + 0.07]),
                lambda t, ph=ph, tw=tw: X * (7.0 * math.sin(2 * math.pi * t / D + ph)
                                             + 14.0 * spring_kick(t - tw, 3.5, 0.3) * (1 - smooth(t, D - 0.25, D))), True)
        for tw in tk[:1]:
            event(ab, tw, "sfx_idle", string="twitch")
        return {"twitches": [round(x, 4) for x in tk]}
    specs.append(ClipSpec("idle", "loop", 2.4, idle))

    def fly(ab, D, env):
        h = float(P["lift"]) * L_leg * X
        nb_ = max(1, round(D / 0.2))
        ts = times(D, 60)
        bob = lambda t: h + 0.05 * L_leg * X * math.sin(2 * math.pi * 2 * t / D)  # noqa: E731
        put(ab, bodyb, "translate", ts, lambda t: (0.0, bob(t)), True)
        put(ab, bodyb, "rotate", ts, lambda t: facing * (8.0 + 1.5 * math.sin(2 * math.pi * 2 * t / D + 1.0)) * X, True)
        w = sk.world()
        for nm, v in leg_info.items():
            hip = np.array(w[v["bones"][0]].head)
            ft = np.array(w[v["target"]].head)
            tuck = 0.38 * (hip - ft)
            ph = {"1": 0.0, "2": 0.9, "3": 1.8}[nm[1]]
            put(ab, v["target"], "translate", ts, lambda t, tuck=tuck, ph=ph: (
                float(tuck[0]) + 0.06 * L_leg * math.sin(2 * math.pi * t / D + ph), float(tuck[1]) + bob(t)), True)
        for s, bs in antennae.items():
            put(ab, bs[0], "rotate", ts, lambda t: -facing * (16.0 + 3.0 * math.sin(2 * math.pi * 4 * t / D)) * X, True)
        for s in wings:
            shown(ab, s, [(0.0, "blur")])
            ab.sequence(s, "blur", [(0.0, "loop", 0, round(D / nb_ / K, 5))])
        event(ab, 0.0, "sfx_fly")
        return {"hover": round(h, 2), "blur_loops": nb_, "frame_delay": round(D / nb_ / K, 5)}
    specs.append(ClipSpec("fly", "loop", 0.8, fly))

    sel = _specs_filter("insect", specs + [ClipSpec("walk", "loop", 1.0, lambda ab, D, env: {})], clips)
    walk_on = any(s.name == "walk" for s in sel)
    made = {"bones": {"frame": frame, "body": bodyb, "head": hb, "abdomen": abd_bones, "wings": wings},
            "legs": leg_info, "antennae": antennae, "riders": riders, "physics": phys, "facing": facing}
    made["clips"] = merge_clips(sk, [s for s in sel if s.name != "walk"])
    if walk_on:
        res = gait_fn(project, gait_legs, bodyb, g_name, name="walk", speed=float(P["speed"]) or None, cycles=2,
                      facing=int(facing))
        D = res["duration"]
        ab = AnimBuilder(sk, "walk", replace=False)
        ts = times(D, 30)
        cyc = res["cycles"]
        for s, bs in antennae.items():
            put(ab, bs[0], "rotate", ts, lambda t: 6.0 * X * math.sin(2 * math.pi * cyc * t / D), True)
        if hb:
            put(ab, hb, "rotate", ts, lambda t: 2.5 * X * math.sin(4 * math.pi * cyc * t / D + 0.5), True)
        made["clips"]["walk"] = {"length": D, "mode": "loop", "gait": res["gait"], "period": res["period"],
                                 "steps": len(res["steps"]), "stride": res["stride"]}
    return made


# ================================================================== 7. plant / tree monster
def _rig_plant(project: Project, P: dict, seed: int, X: float, clips) -> dict:
    sk = project.data
    trunk = _find(sk, "trunk", "stem", "body")
    if not trunk:
        raise _missing("plant", ["trunk"], sk)
    Dg = float(P["grow"])
    if Dg < 0.8:
        raise ValueError("grow (clip length) must be >= 0.8 s")
    wind = float(P["wind"]) * X
    tx0, ty0, tx1, ty1 = art_bounds(project, trunk)
    Ht = ty1 - ty0
    frame = frame_bone(sk, "plant", "root", (tx0 + tx1) / 2, ty0, 0.0, color="00E1FFFF")
    tb, tpts = chain_on_slot(project, trunk, 3, frame, "trunk", root_end="bottom", detail=0.9)
    tlen = [sk.bone(b).length for b in tb]
    tarc = [0.0] + list(np.cumsum(tlen))
    poly = tpts.tolist()

    def arc_on(points, lens, p):
        """Arc position of the point of a polyline nearest p."""
        best, bs = 1e18, 0.0
        acc = 0.0
        p = np.asarray(p, float)
        for (a, b), L in zip(zip(points[:-1], points[1:]), lens):
            a, b = np.asarray(a, float), np.asarray(b, float)
            ab_ = b - a
            u = float(np.clip(np.dot(p - a, ab_) / max(np.dot(ab_, ab_), 1e-9), 0, 1))
            d = float(np.hypot(*(p - (a + u * ab_))))
            if d < best:
                best, bs = d, acc + u * L
            acc += L
        return bs
    branches = {}
    phys = []
    for i, bsl in enumerate(find_prefixed(sk, "branch")):
        c = art_center(project, bsl)
        w = sk.world()
        par = min(tb, key=lambda b: _dist_to(c, [w[b].head, w[b].tail]))
        bb, bp = chain_on_slot(project, bsl, 3, par, f"{base_name(bsl)}_", root_near=poly, detail=0.8)
        phys += add_phys(sk, bb[-1:], "antenna", strength=180, inertia=0.5)
        branches[bsl] = {"bones": bb, "parent": par, "attach": arc_on(tpts, tlen, bp[0]), "points": bp.tolist(),
                         "lengths": [sk.bone(b).length for b in bb]}
    roots = {}
    for rs in find_prefixed(sk, "root"):
        rb, rp = chain_on_slot(project, rs, 2, tb[0], f"{base_name(rs)}_",
                               root_near=(float(tpts[0][0]), float(tpts[0][1]) + 0.08 * Ht), detail=0.8)
        ik = add_ik(sk, rb, target_parent=frame)
        roots[rs] = {"bones": rb, "ik": ik, "lengths": [sk.bone(b).length for b in rb]}
    leaves = {}
    w = sk.world()
    hosts = {b: (w[b].head, w[b].tail) for v in branches.values() for b in v["bones"]} or {tb[-1]: (w[tb[-1]].head, w[tb[-1]].tail)}
    for i, ls in enumerate(find_prefixed(sk, "leaf", "leaves", "foliage", "canopy")):
        c = art_center(project, ls)
        par = min(hosts, key=lambda b: _dist_to(c, list(hosts[b])))
        a0, a1 = art_axis(project, ls)
        seg = list(hosts[par])
        rt = a0 if _dist_to(a0, seg) <= _dist_to(a1, seg) else a1
        tip = a1 if rt is a0 else a0
        lb = frame_bone(sk, f"plant_{base_name(ls)}", par, float(rt[0]), float(rt[1]), math.degrees(math.atan2(*(tip - rt)[::-1])))
        sk.bone(lb).length = round(float(np.hypot(*(tip - rt))), 3)
        reparent_slot(sk, ls, lb)
        phys += add_phys(sk, [lb], "antenna", strength=round(120 + 50 * ((i * 0.618) % 1.0), 1), inertia=0.6, damping=0.86)
        leaves[ls] = {"bone": lb, "parent": par}
    riders = []
    for s in sk.slots:
        b = base_name(s.name)
        if b.startswith(("eye", "mouth", "face", "brow", "pupil", "nose")):
            reparent_slot(sk, s.name, tb[-1])
            riders.append(s.name)
        elif b.startswith(("flower", "fruit", "bud", "berry")):
            c = art_center(project, s.name)
            reparent_slot(sk, s.name, min(hosts, key=lambda b_: _dist_to(c, list(hosts[b_]))))
            riders.append(s.name)
    nT = len(tb)
    rng = np.random.default_rng(seed + 9)
    leaf_ph = {ls: (int(rng.choice([2, 3])), float(rng.uniform(0, 2 * math.pi))) for ls in leaves}
    w = sk.world()
    side_of = {b: (1.0 if w[v["bones"][-1]].tail[0] >= w[v["bones"][0]].head[0] else -1.0) for b, v in branches.items()}
    specs = []

    def idle(ab, D, env):
        ts = times(D, 30)
        wv = lambda t, lag: math.sin(2 * math.pi * t / D - lag) + 0.25 * math.sin(2 * math.pi * 3 * t / D - 1.7 * lag)  # noqa: E731
        amp = (1.4, 1.0, 0.8)
        for i, b in enumerate(tb):
            put(ab, b, "rotate", ts, lambda t, i=i: -wind * amp[min(i, 2)] * wv(t, 0.35 * i), True)
        for k, (bsl, v) in enumerate(branches.items()):
            for j, b in enumerate(v["bones"]):
                put(ab, b, "rotate", ts, lambda t, j=j, k=k: -wind * 2.2 * wv(t, 0.35 * (nT + j) + 0.2 * k), True)
        for ls, v in leaves.items():
            n_, ph = leaf_ph[ls]
            put(ab, v["bone"], "rotate", ts, lambda t, n_=n_, ph=ph: 5.0 * wind * math.sin(2 * math.pi * n_ * t / D + ph), True)
        event(ab, 0.25 * D, "sfx_idle", string="rustle")
        return {"gust_period": round(D, 4)}
    specs.append(ClipSpec("idle", "loop", float(P["sway"]), idle))

    EPS = 0.01

    def grow_plan(D):
        LT = tarc[-1]
        f1 = {"trunk": LT ** 2 / 2}
        for bsl, v in branches.items():
            f1[bsl] = f1["trunk"] * (v["attach"] / LT) ** 2 + sum(v["lengths"]) ** 2 / 2
        for rs, v in roots.items():
            f1[rs] = sum(v["lengths"]) ** 2 / 2
        k = max(f1.values()) / (0.68 * D)
        T_T = LT ** 2 / (2 * k)
        plan = {"k": k, "trunk": (0.0, T_T, LT)}
        for bsl, v in branches.items():
            Lb = sum(v["lengths"])
            plan[bsl] = (T_T * (v["attach"] / LT) ** 2, Lb ** 2 / (2 * k), Lb)
        for rs, v in roots.items():
            Lr = sum(v["lengths"])
            plan[rs] = (0.0, Lr ** 2 / (2 * k), Lr)
        return plan

    def front(t, t0, T, L):
        return L * math.sqrt(min(max((t - t0) / T, 0.0), 1.0)) if T > 0 else L

    def fracs(t, t0, T, lens):
        s = front(t, t0, T, sum(lens))
        out, acc = [], 0.0
        for L in lens:
            out.append(min(max((s - acc) / L, EPS), 1.0))
            acc += L
        return out

    def grow(ab, D, env):
        pl = grow_plan(D)
        ts = times(D, 60)
        Gt = {t: fracs(t, *pl["trunk"][:2], tlen) for t in ts}

        def G_of(bone, t):
            return fracs(t, *pl["trunk"][:2], tlen)[tb.index(bone)] if bone in tb else 1.0
        for i, b in enumerate(tb):
            put(ab, b, "scale", ts, lambda t, i=i: ((fracs(t, *pl["trunk"][:2], tlen)[i]
                                                     / (fracs(t, *pl["trunk"][:2], tlen)[i - 1] if i else 1.0)),) * 2)
        for bsl, v in branches.items():
            t0, T, _ = pl[bsl]
            for j, b in enumerate(v["bones"]):
                put(ab, b, "scale", ts, lambda t, j=j, v=v, t0=t0, T=T: (
                    (fracs(t, t0, T, v["lengths"])[j] / (fracs(t, t0, T, v["lengths"])[j - 1] if j else G_of(v["parent"], t))),) * 2)
        for rs, v in roots.items():
            t0, T, _ = pl[rs]
            for j, b in enumerate(v["bones"]):
                put(ab, b, "scale", ts, lambda t, j=j, v=v, t0=t0, T=T: (
                    (fracs(t, t0, T, v["lengths"])[j] / (fracs(t, t0, T, v["lengths"])[j - 1] if j else G_of(tb[0], t))),) * 2)
            ab.ik(v["ik"]["constraint"], [(0.0, 0.0), (round(t0 + T, 4), 0.0), (round(min(D, t0 + T + 0.25), 4), 1.0)], ease="linear")
        _ = Gt
        pops = []
        for i, (ls, v) in enumerate(leaves.items()):
            host = next((bsl for bsl, bv in branches.items() if v["parent"] in bv["bones"]), None)
            t0, T, _ = pl[host] if host else pl["trunk"]
            tp = t0 + T + 0.03 * i
            pops.append(tp)

            def ls_(t, tp=tp):
                s = EPS + (1 - EPS) * spring_step(t - tp, 2.4, 0.4) if t > tp else EPS
                return 1 + (s - 1) * (1 - smooth(t, 0.9 * D, D))
            put(ab, v["bone"], "scale", times(D, 60, [tp + spring_peak_time(2.4, 0.4)]), lambda t, f=ls_: (f(t),) * 2)
        event(ab, 0.0, "sfx_grow", string="sprout")
        if pops:
            event(ab, min(pops), "sfx_grow", string="bloom")
        return {"k": round(pl["k"], 3), "trunk_time": round(pl["trunk"][1], 4),
                "branches": {b: {"start": round(pl[b][0], 4), "time": round(pl[b][1], 4), "length": round(pl[b][2], 2)}
                             for b in branches},
                "leaf_pops": [round(p, 4) for p in pops], "law": "s = sqrt(2 k t)"}
    specs.append(ClipSpec("grow", "oneshot", Dg, grow))

    def attack(ab, D, env):
        t_up, t_s = 0.42 * D, 0.58 * D
        sb = max(branches, key=lambda b: sk.world()[branches[b]["bones"][-1]].tail[0]) if branches else None
        fwd = side_of.get(sb, 1.0) if sb else 1.0

        def th(t, back, fore):
            if t < t_up:
                return back * smooth(t, 0.04 * D, t_up)
            if t < t_s:
                q = (t - t_up) / (t_s - t_up)
                return back - (back + fore) * q * q
            return -fore * ring(t - t_s, 2.0, 0.3)
        ts = times(D, 60, [t_up, t_s])
        e = lambda t: end_env(t, D, 0.15)  # noqa: E731
        dl = 0.035
        for i, b in enumerate(tb):
            put(ab, b, "rotate", ts, lambda t, i=i: fwd * (0.5, 0.3, 0.2)[min(i, 2)] * th(t - i * dl, 9.0 * X, 13.0 * X) * e(t))
        for bsl, v in branches.items():
            k_ = 1.0 if bsl == sb else 0.25
            for j, b in enumerate(v["bones"]):
                put(ab, b, "rotate", ts, lambda t, j=j, k_=k_: fwd * k_ * (0.45, 0.35, 0.3)[min(j, 2)]
                    * th(t - (nT + j) * dl, 30.0 * X, 55.0 * X) * e(t))
        for ls, v in leaves.items():
            put(ab, v["bone"], "rotate", ts, lambda t: 12.0 * X * spring_kick(t - t_s - 0.05, 4.0, 0.25) * e(t))
        event(ab, t_s, "sfx_attack")
        event(ab, t_s, "screen_shake", float=float(P["shake"]) * X, int=250)
        return {"impact": round(t_s, 4), "striking_branch": sb, "whip_delay": dl}
    specs.append(ClipSpec("attack", "oneshot", 1.4, attack))

    made = {"bones": {"frame": frame, "trunk": tb}, "branches": {b: v["bones"] for b, v in branches.items()},
            "roots": {r: {"bones": v["bones"], "ik": v["ik"]["constraint"]} for r, v in roots.items()},
            "leaves": {ls: v["bone"] for ls, v in leaves.items()}, "riders": riders, "physics": phys}
    made["clips"] = merge_clips(sk, _specs_filter("plant", specs, clips))
    return made


# ================================================================== 8. mimic
def lid_bounce(t: float, t_hit: float, theta_c: float, T_fall: float, e: float, n: int = 4) -> float:
    """Lid angle as it falls from theta_c (starting at t_hit - T_fall) under constant angular gravity to 0 at t_hit,
    then bounces off the rim with restitution e: bounce k rises e^(2k) theta_c and lasts 2 e^k T_fall."""
    if t < t_hit - T_fall:
        return theta_c
    if t < t_hit:
        q = (t - (t_hit - T_fall)) / T_fall
        return theta_c * (1 - q * q)
    tau = t - t_hit
    for k in range(1, n + 1):
        Tk = 2 * e ** k * T_fall
        if tau < Tk:
            u = tau / Tk
            return theta_c * e ** (2 * k) * 4 * u * (1 - u)
        tau -= Tk
    return 0.0


def _rig_mimic(project: Project, P: dict, seed: int, X: float, clips) -> dict:
    sk = project.data
    base = _find(sk, "base", "chest", "box")
    lid = _find(sk, "lid")
    missing = ([] if base else ["base"]) + ([] if lid else ["lid"])
    if missing:
        raise _missing("mimic", missing, sk)
    z = float(P["zeta"])
    if not 0.05 <= z < 1:
        raise ValueError("zeta must be 0.05..0.99 (the hinge spring overshoots)")
    e_ = float(P["restitution"])
    if not 0 <= e_ < 1:
        raise ValueError("restitution must be 0..0.99")
    bx0, by0, bx1, by1 = art_bounds(project, base)
    lx0, ly0, lx1, ly1 = art_bounds(project, lid)
    Wb, Hb = bx1 - bx0, (max(by1, ly1) - by0)
    lock = _find(sk, "lock", "latch")
    facing = 1.0
    if lock and art_center(project, lock)[0] < (bx0 + bx1) / 2:
        facing = -1.0
    frame = frame_bone(sk, "mimic", "root", (bx0 + bx1) / 2, by0, 0.0, color="00E1FFFF")
    bodyb = frame_bone(sk, "mimic_body", frame, (bx0 + bx1) / 2, by0, 0.0, color="FFD400FF")
    reparent_slot(sk, base, bodyb)
    hinge = (lx0 if facing > 0 else lx1, ly0)
    lidb = frame_bone(sk, "mimic_lid", bodyb, hinge[0], hinge[1], 0.0 if facing > 0 else 180.0, color="FF3F00FF")
    sk.bone(lidb).length = round(lx1 - lx0, 3)
    reparent_slot(sk, lid, lidb)
    eyes, teeth = [], []
    for s in list(sk.slots):
        b = base_name(s.name)
        if s.name in (base, lid) or not s.attachment:
            continue
        c = art_center(project, s.name)
        if b.startswith(("inside", "mouth", "gold", "coin", "treasure", "gem")):
            reparent_slot(sk, s.name, bodyb)
        elif b.startswith(("teeth", "tooth")):
            up = "upper" in b or "top" in b or ("lower" not in b and "bottom" not in b and c[1] >= hinge[1])
            reparent_slot(sk, s.name, lidb if up else bodyb)
            teeth.append(s.name)
        elif b.startswith(("eye", "pupil")):
            eb = frame_bone(sk, f"mimic_{b}", bodyb, c[0], c[1], 0.0)          # in the dark, revealed by the lid
            reparent_slot(sk, s.name, eb)
            eyes.append(eb)
        elif b.startswith(("lock", "latch")):
            reparent_slot(sk, s.name, lidb)
        elif b.startswith(("trim", "strap", "band", "rivet")):
            host = nearest_part(project, c, [base, lid])
            reparent_slot(sk, s.name, lidb if host == lid else bodyb)
    tongue = _find(sk, "tongue")
    tb, phys = [], []
    if tongue:
        tb, _ = chain_on_slot(project, tongue, 3, bodyb, "tongue_", root_near=(hinge[0] + facing * 0.25 * Wb, by1), detail=0.8)
        phys += add_phys(sk, tb, "tassel")
    specs = []
    crack = float(P["crack"]) * X
    Th = float(P["open_angle"])
    if not 10 <= Th <= 170:
        raise ValueError("open_angle must be 10..170 deg")

    def lid_keys(ab, ts, fn, loop=False):
        put(ab, lidb, "rotate", ts, lambda t: facing * fn(t), loop)

    def tongue_keys(ab, ts, fn, loop=False):
        for j, b in enumerate(tb):
            put(ab, b, "rotate", ts, lambda t, j=j: -facing * fn(t) * (0.5 + 0.25 * j), loop)

    def idle(ab, D, env):
        ts = times(D, 40)
        cr = lambda t: crack * math.sin(2 * math.pi * t / D) ** 2  # noqa: E731   two breaths per loop
        lid_keys(ab, ts, cr, True)
        sy = lambda t: 1 + 0.012 * X * math.sin(2 * math.pi * t / D) ** 2  # noqa: E731
        put(ab, bodyb, "scale", ts, lambda t: (squash_x(sy(t)), sy(t)), True)
        for eb in eyes:
            put(ab, eb, "scale", ts, lambda t: (1 + 0.2 * (bump(t, 0.17 * D, 0.16 * D) + bump(t, 0.67 * D, 0.16 * D)),) * 2, True)
        tongue_keys(ab, ts, lambda t: 4.0 * X * math.sin(2 * math.pi * t / D) ** 2, True)
        for k in (0.25, 0.75):
            event(ab, k * D, "sfx_idle", string="creak")
        return {"crack": round(crack, 3), "breaths": 2}
    specs.append(ClipSpec("idle", "loop", 3.2, idle))

    def open_(ab, D, env):
        t_o, t_c, T_fall = 0.32, 0.62 * D, 0.2
        t_hit = t_c + T_fall
        tp = t_o + spring_peak_time(2.0, z)
        th_c = Th * spring_step(t_c - t_o, 2.0, z)

        def th(t):
            if t < t_o:
                return 2.5 * X * math.sin(2 * math.pi * 16 * t) * bump(t, 0.0, t_o)       # the rattle
            if t < t_c:
                return Th * spring_step(t - t_o, 2.0, z)
            return lid_bounce(t, t_hit, th_c, T_fall, e_)
        ts = times(D, 60, [t_o, tp, t_c, t_hit])
        lid_keys(ab, ts, lambda t: th(t) * end_env(t, D, 0.06))
        tongue_keys(ab, ts, lambda t: 35.0 * X * smooth(t, t_o + 0.1, t_o + 0.45) * (1 - smooth(t, t_c - 0.15, t_hit)))
        for eb in eyes:
            put(ab, eb, "scale", ts, lambda t: (1 + 0.35 * bump(t, t_o, 0.5),) * 2)
        sq = lambda t: 1 - 0.08 * X * spring_kick(t - t_hit, 3.0, 0.4) * end_env(t, D)  # noqa: E731
        put(ab, bodyb, "scale", ts, lambda t: (squash_x(sq(t)), sq(t)))
        from . import fx_recipes
        cav = ((bx0 + bx1) / 2 + facing * 0.1 * Wb, by1 + 0.12 * Hb)
        lx, ly = sk.world()[bodyb].to_local(*cav)
        fx = fx_recipes.apply(project, "shine", x=lx, y=ly, scale=round(0.4 * Wb / 160, 3), start=t_o + 0.06, into="open",
                              parent=bodyb, front_of=sk.slots[-1].name, count=5, name="mimic_shine",
                              color="FFD86A", intensity=0.75)
        event(ab, t_o, "sfx_open")
        event(ab, t_hit, "sfx_close")
        return {"fling": t_o, "overshoot_angle": round(Th * (1 + spring_overshoot(z)), 3), "peak_time": round(tp, 4),
                "close_hit": round(t_hit, 4), "close_from": round(th_c, 3),
                "bounce_heights": [round(e_ ** (2 * k), 4) for k in (1, 2)], "fx": fx["recipe"], "fx_slots": len(fx["slots"])}
    specs.append(ClipSpec("open", "oneshot", 2.2, open_))

    def bite(ab, D, env):
        t_open, t_b = 0.12, 0.38
        Tb = 58.0 * X

        def th(t):
            if t < t_open:
                return Tb * (1 - (1 - t / t_open) ** 3)
            return lid_bounce(t, t_b, Tb, t_b - t_open, e_)
        ts = times(D, 60, [t_open, t_b])
        lid_keys(ab, ts, lambda t: th(t) * end_env(t, D, 0.1))
        lam = 9.0
        lunge = lambda t: smooth(t, 0.02, t_b) if t < t_b else (1 + lam * (t - t_b)) * math.exp(-lam * (t - t_b))  # noqa: E731
        put(ab, bodyb, "translate", ts, lambda t: (facing * 0.22 * Wb * X * lunge(t) * end_env(t, D, 0.1),
                                                   0.14 * Hb * X * bump(t, 0.02, t_b + 0.06) * end_env(t, D, 0.1)))
        put(ab, bodyb, "rotate", ts, lambda t: -facing * 8.0 * X * bump(t, 0.02, t_b + 0.1) * end_env(t, D, 0.1))
        tongue_keys(ab, ts, lambda t: (25.0 * bump(t, 0.0, t_b) - 18.0 * spring_kick(t - t_b, 3.0, 0.3)) * X * end_env(t, D, 0.1))
        event(ab, t_b, "sfx_bite")
        return {"snap_shut": t_b, "open": round(Tb, 2)}
    specs.append(ClipSpec("bite", "oneshot", 1.0, bite))

    juice_on = bool(P["juice"])
    if juice_on:
        def land(ab, D, env):
            ti = 0.27 * D
            ts = times(D, 60, [ti])
            lid_keys(ab, ts, lambda t: 14.0 * X * spring_kick(t - ti, 5.0, 0.35) * end_env(t, D, 0.1))
            tongue_keys(ab, ts, lambda t: 5.0 * X * spring_kick(t - ti, 4.0, 0.3) * end_env(t, D, 0.1))
            return {"impact": round(ti, 4)}

        def win(ab, D, env):
            ts = times(D, 60)
            lid_keys(ab, ts, lambda t: 32.0 * X * (bump(t, 0.22 * D, 0.22 * D) + bump(t, 0.5 * D, 0.22 * D)))
            tongue_keys(ab, ts, lambda t: 20.0 * X * math.sin(2 * math.pi * 3 * t / D) * bump(t, 0.2 * D, 0.65 * D))
            return {"chomps": 2}
        specs += [ClipSpec("land", "oneshot", 0.45, land), ClipSpec("win", "oneshot", 1.2, win)]
    sel = _specs_filter("mimic", specs, clips)
    made = {"bones": {"frame": frame, "body": bodyb, "lid": lidb, "tongue": tb, "eyes": eyes}, "teeth": teeth,
            "hinge": [round(v, 2) for v in hinge], "facing": facing, "physics": phys}
    made["clips"] = merge_clips(sk, sel)
    jc = [s.name for s in sel if s.name in ("land", "win")]
    if juice_on and jc:
        from . import juice
        made["juice"] = juice.apply(project, jc, merge=True)
    return made


# ================================================================== 5. dragon
def fire_frames(w: int = 384, h: int = 144, frames: int = 8, seed: int = 1, hot=(255, 250, 225), mid=(255, 140, 28),
                cool=(190, 38, 8)) -> list[Image.Image]:
    """A fire jet streaming to +x from a nozzle at the left edge (image y down), as an exactly looping flipbook:
    constant spreading half-angle (turbulent jet), cooling along its length, the centre line curling up on buoyancy,
    tongues from periodic noise advected downstream (each octave moves a whole number of tile widths per loop, small
    licks faster: the turbulence cascade), soft at the tip and along the edges."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float64)
    u = x / w
    yc = 0.55 * h - 0.22 * h * u ** 2
    hw = h * (0.07 + 0.42 * u)
    r = np.abs(y - yc) / hw
    octs = [(int(m), float(rng.uniform(0, 2 * math.pi)), float(rng.uniform(-3, 3)), a, c)
            for m, a, c in ((3, 0.5, 1), (5, 0.3, 2), (9, 0.2, 3), (14, 0.12, 4))]
    out = []
    for k in range(frames):
        s = k / frames
        n = np.zeros_like(u)
        for m, ph, fy, a, c in octs:
            n += a * np.sin(2 * math.pi * (m * u - c * s) + fy * (y - yc) / h * 2 * math.pi + ph)
        n = n / 1.12
        body = np.clip(1 - r ** 2 * (1 + 0.55 * n), 0, 1)
        I = 1.7 * body * (1 - u) ** 0.4 * (0.8 + 0.4 * n) * (1 - smooth_arr(u, 0.7, 1.0))
        I += 0.55 * np.exp(-((u / 0.09) ** 2) - (r / 0.6) ** 2)              # the white-hot nozzle
        I = np.clip(I * smooth_arr(u, 0.0, 0.03) * (1 - smooth_arr(np.abs(y - h / 2) / (h / 2), 0.86, 1.0)), 0, 1)
        from .fx_recipes import _colorize
        out.append(_colorize(I.astype(np.float32), hot, mid, cool))
    return out


def smooth_arr(x, a, b):
    u = np.clip((np.asarray(x, float) - a) / max(b - a, 1e-9), 0, 1)
    return u * u * (3 - 2 * u)


def _rig_dragon(project: Project, P: dict, seed: int, X: float, clips) -> dict:
    from .rig_chain import Flier, _wave_angles, build_serpent, build_wing, flier_clips, key_wave, key_wings, warp
    from .rig_face import rename_slot
    from .rig_gait import LEG_TYPES, find_quadruped_parts, rig_quadruped
    sk = project.data
    if str(P["leg_type"]) not in LEG_TYPES:
        raise ValueError(f"leg_type must be one of {sorted(LEG_TYPES)}")
    fh = float(P["flap_hz"])
    if fh <= 0:
        raise ValueError("flap_hz must be > 0")
    F = int(P["fire_frames"])
    if not 2 <= F <= 32:
        raise ValueError("fire_frames must be 2..32")
    want = list(CREATURE_CLIPS["dragon"]) if clips is None else ([clips] if isinstance(clips, str) else list(clips))
    bad = [c for c in want if c not in CREATURE_CLIPS["dragon"]]
    if bad:
        raise ValueError(f"unknown clip(s) {bad} for dragon; one of {list(CREATURE_CLIPS['dragon'])}")
    try:
        find_quadruped_parts(sk)
    except ValueError as err:
        raise _missing("dragon", [str(err).split("missing: ")[-1].split(". Convention")[0]], sk) from None
    neck, tail, jaw = _find(sk, "neck"), _find(sk, "tail"), _find(sk, "jaw")
    wings_sl = {sd: _find(sk, f"wing_{sd}") for sd in "lr"}
    hidden = {}
    for i, s in enumerate([x for x in (neck, tail, *wings_sl.values()) if x]):
        tmp = f"__dragon_part{i}"
        rename_slot(sk, s, tmp)
        hidden[tmp] = s
    try:
        q = rig_quadruped(project, leg_type=str(P["leg_type"]), clips=[c for c in ("idle", "walk") if c in want],
                          seed=seed, exaggerate=X)
    finally:
        for tmp, s in hidden.items():
            rename_slot(sk, tmp, s)
    quad = project._quad  # noqa: SLF001
    facing = float(q["facing"])
    w = sk.world()
    body_c = np.array((w["q_body"].x, w["q_body"].y))
    body_len = float(abs(w["shoulders"].tail[0] - w["hips"].tail[0]))
    made: dict = {"quadruped": {k: q[k] for k in ("legs", "strands", "attached", "skipped", "facing", "leg_type")}}
    phys = []
    neck_sp = tail_sp = None
    head_ctrl = "head"
    if neck:
        neck_sp = build_serpent(project, neck, int(P["neck_bones"]), "shoulders", "neck", root_near=w["shoulders"].tail, detail=0.8)
        w = sk.world()
        tip = np.array(w[neck_sp.bones[-1]].tail)
        snout = np.array(w["head"].tail)
        head_ctrl = frame_bone(sk, "dragon_head", neck_sp.bones[-1], float(tip[0]), float(tip[1]),
                               math.degrees(math.atan2(*(snout - tip)[::-1])))
        sk.bone(head_ctrl).length = round(float(np.hypot(*(snout - tip))), 3)
        reparent_bone(sk, "head", head_ctrl)
        made["neck"] = {"bones": neck_sp.bones, "frame": neck_sp.frame, "drive": neck_sp.drive}
    if tail:
        tail_sp = build_serpent(project, tail, int(P["tail_bones"]), "hips", "tail", root_near=w["hips"].tail, detail=0.8)
        phys += add_phys(sk, tail_sp.bones[-3:], "tail", taper=0.1)
        made["tail"] = {"bones": tail_sp.bones, "frame": tail_sp.frame, "drive": tail_sp.drive}
    jb = None
    if jaw:
        a0, a1 = art_axis(project, jaw)
        hinge = a0 if facing * a0[0] <= facing * a1[0] else a1
        jb = frame_bone(sk, "dragon_jaw", "head", float(hinge[0]), float(hinge[1]), 0.0 if facing > 0 else 180.0)
        reparent_slot(sk, jaw, jb)
    wings = []
    for sd, ws in wings_sl.items():
        if not ws:
            continue
        wg, _ = build_wing(project, ws, "shoulders", tuple(body_c), f"wing_{sd}", [], 3, "none")
        phys += add_phys(sk, wg.bones[-1:], "feather", strength=150)
        wings.append(wg)
    made["wings"] = {wg.slot: wg.bones for wg in wings}
    # the breath: a generated fire flipbook on a bone at the mouth (additive, top of the draw order, hidden in setup)
    w = sk.world()
    hw_ = w["head"]
    mouth = np.array(hw_.tail)
    hx0, hy0, hx1, hy1 = art_bounds(project, _find(sk, "head"))
    mouth = mouth + np.array((0.0, -0.18 * (hy1 - hy0)))
    breath = frame_bone(sk, "dragon_breath", "head", float(mouth[0]), float(mouth[1]),
                        (-4.0 if facing > 0 else 184.0), color="FF3F00FF")
    imgs = fire_frames(384, 168, F, seed)
    base_tex = "creature/dragon_fire_"
    for i, im in enumerate(imgs):
        project.write_image(f"{base_tex}{i:02d}", im)
    FW = float(P["fire_length"]) * max(body_len, 1.0)
    FH = FW * 168 / 384
    fire = _add_fx_slot(sk, "dragon_fire", breath, "fire",
                        RegionAttachment(path=base_tex, x=round(FW / 2, 2), y=round(0.05 * FH, 2), width=round(FW, 2),
                                         height=round(FH, 2), sequence=Sequence(count=F, start=0, digits=2)))
    ensure_tex(project, "fx/glow")
    glow = _add_fx_slot(sk, "dragon_mouth_glow", breath, "glow",
                        RegionAttachment(path="fx/glow", width=round(0.9 * (hy1 - hy0), 2), height=round(0.9 * (hy1 - hy0), 2)),
                        color="FFB040FF")
    ae_bone = frame_bone(sk, "dragon_breath_ae", breath, float(mouth[0]), float(mouth[1]), sk.world()[breath].rotation + 90.0)
    fl = Flier(frame="", body="q_body", head=None, anchor=None, wings=wings, tail=[], span=0.0, body_h=0.25 * body_len)
    FOLD = (15.0, -40.0, -45.0)
    FOLD_SX = 0.75
    nj = 3
    legs = quad.legs
    L = quad.L

    def fold_pose(t, D, k=1.0):
        br = 0.05 * math.sin(2 * math.pi * t / D)
        return [k * v * (1 + br) for v in FOLD], 1 - k * (1 - FOLD_SX), 0.0

    def neck_wave(ab, ts, D, amp, cycles, loop, heading=None, head_keep=0.7):
        if not neck_sp:
            return
        lam = 1.6 * neck_sp.L
        y = lambda s, t: amp * neck_sp.L * (s / neck_sp.L) * math.sin(2 * math.pi * (s / lam - cycles * t / D))  # noqa: E731
        key_wave(ab, neck_sp, ts, y, loop, heading=heading, recoil=0.0)
        hd = heading or (lambda t: 0.0)
        put(ab, head_ctrl, "rotate", ts, lambda t: -head_keep * (_wave_angles(neck_sp, y, t)[-1] + hd(t)), loop)

    def tail_wave(ab, ts, D, amp, cycles, loop, heading=None):
        if not tail_sp:
            return
        lam = 1.1 * tail_sp.L
        A = lambda s: amp * tail_sp.L * (0.1 + 0.9 * (s / tail_sp.L) ** 2)  # noqa: E731
        key_wave(ab, tail_sp, ts, lambda s, t: A(s) * math.sin(2 * math.pi * (s / lam - cycles * t / D)), loop,
                 heading=heading, recoil=0.0)

    specs = []

    def idle(ab, D, env):
        ts = times(D, 30)
        neck_wave(ab, ts, D, 0.05 * X, 1, True, heading=lambda t: 3.0 * X * facing * math.sin(2 * math.pi * t / D))
        tail_wave(ab, ts, D, 0.06 * X, 1, True)
        if wings:
            key_wings(ab, fl, ts, lambda t: fold_pose(t, D), True)
        return {"wings": "folded, breathing"}
    specs.append(ClipSpec("idle", "loop", 4.0, idle, create=False))

    def walk(ab, D, env):
        ts = times(D, 40)
        neck_wave(ab, ts, D, 0.04 * X, 1, True, heading=lambda t: 2.0 * X * facing * math.sin(4 * math.pi * t / D))
        tail_wave(ab, ts, D, 0.08 * X, 1, True)
        if wings:
            key_wings(ab, fl, ts, lambda t: fold_pose(t, D), True)
        return {}
    specs.append(ClipSpec("walk", "loop", 1.0, walk, create=False))

    if wings:
        fspec = flier_clips(fl, flap_hz=fh, cycles=2, amp=(46.0, 18.0, 24.0), which=("flap",), names={"flap": "fly"},
                            fold=FOLD, fold_sx=1.0)[0]

        def fly(ab, D, env):
            info = fspec.build(ab, D, env)
            n, Pd = max(1, round(D * fh)), D / max(1, round(D * fh))
            ts = times(D, 40)
            bob = lambda t: -fl.body_h * 0.11 * warp(t / Pd, 0.58)  # noqa: E731
            w_ = sk.world()
            lift = 0.45 * L
            for leg, lg in legs.items():
                hip = np.array(w_[lg["upper"]].head)
                ft = np.array(w_[lg["target"]].head)
                tuck = 0.5 * (hip - ft) + np.array((-facing * 0.25 * L, 0.0))
                put(ab, lg["target"], "translate", ts, lambda t, tuck=tuck: (float(tuck[0]), float(tuck[1]) + lift + bob(t)), True)
            put(ab, "q_body", "translate", ts, lambda t: (0.0, lift), True)          # airborne: off the ground
            put(ab, "q_body", "rotate", ts, lambda t: facing * 4.0 * X, True)
            neck_wave(ab, ts, D, 0.03 * X, n, True, heading=lambda t: -facing * 22.0 * X, head_keep=0.8)
            tail_wave(ab, ts, D, 0.07 * X, n, True, heading=lambda t: facing * 8.0 * X)
            return {**info, "legs": "tucked"}
        specs.append(ClipSpec("fly", "loop", fspec.length, fly))

    t_in, t0, t1 = 0.7, 0.78, 1.85

    def breath_clip(ab, D, env):
        ts = times(D, 60, [t_in, t0, t1])
        e = lambda t: end_env(t, D, 0.12)  # noqa: E731
        up = lambda t: smooth(t, 0.05, t_in) * (1 - smooth(t, t_in, t0 + 0.08))  # noqa: E731
        thrust = lambda t: smooth(t, t_in, t0 + 0.1) * (1 - smooth(t, t1, t1 + 0.4))  # noqa: E731
        trem = lambda t: 1.4 * math.sin(2 * math.pi * 11 * t) * thrust(t)  # noqa: E731
        hd = lambda t: facing * X * (12.0 * up(t) - 7.0 * thrust(t) + trem(t)) * e(t)  # noqa: E731
        if neck_sp:
            neck_wave(ab, ts, D, 0.0, 1, False, heading=hd, head_keep=0.0)
        put(ab, head_ctrl, "rotate", ts, lambda t: facing * X * (10.0 * up(t) - 1.0 * thrust(t)) * e(t))
        put(ab, "q_body", "rotate", ts, lambda t: facing * X * (3.0 * up(t) - 1.5 * thrust(t)) * e(t))
        if jb:
            put(ab, jb, "rotate", ts, lambda t: -facing * 26.0 * X * smooth(t, t_in - 0.15, t0) * (1 - smooth(t, t1, t1 + 0.35)) * e(t))
        grow_t = 0.35
        sc = lambda t: (min(1.0, math.sqrt(max(0.0, t - t0) / grow_t)) if t < t1 else 1 + 0.25 * (t - t1) / 0.35) if t >= t0 else 0.05  # noqa: E731
        fl_ = lambda t: 1 + 0.06 * math.sin(2 * math.pi * 11 * t)  # noqa: E731
        put(ab, breath, "scale", ts, lambda t: (sc(t), sc(t) * fl_(t)) if t < D - 1e-6 else (1.0, 1.0))
        put(ab, breath, "translate", ts, lambda t: (0.5 * FW * max(0.0, t - t1) / 0.35 if t1 <= t < D - 1e-6 else 0.0, 0.0))
        shown(ab, fire, [(0.0, None), (t0, "fire"), (round(t1 + 0.35, 4), None)])
        ab.sequence(fire, "fire", [(t0, "loop", 0, round(1 / 24, 5))])
        color_track(ab, fire, ts, lambda t: (1, 1, 1, max(0.0, 1 - max(0.0, t - t1) / 0.35)))
        shown(ab, glow, [(0.0, None), (0.2, "glow"), (round(t1 + 0.3, 4), None)])
        color_track(ab, glow, ts, lambda t: (1, 0.69, 0.25, min(1.0, 0.45 * smooth(t, 0.2, t_in) + 0.5 * thrust(t) * fl_(t)) * (1 - smooth(t, t1, t1 + 0.3))))
        event(ab, 0.05, "sfx_breath", string="inhale")
        event(ab, t0, "sfx_breath", string="fire")
        event(ab, t0, "fx_fire")
        return {"fire": [t0, t1], "grow": grow_t, "jet_length": round(FW, 2), "frames": F,
                "ae_hint": {"template": "fire", "parent": ae_bone, "front_of": _last_normal(sk), "mode": "additive",
                            "seq_mode": "loop", "animation": "breath", "start": t0, "until": t1, "x": 0.0,
                            "y": round(0.5 * 576 * FW / 576, 2), "scale": round(FW / 576, 4),
                            "note": "volumetric fire: ae_template fire (width 384, height 576, rise 420) -> save -> "
                                    "ae_fx_to_spine with these args; the bone turns the rising column along the jet. "
                                    "Hide dragon_fire then (it is the Spine fallback)."}}
    specs.append(ClipSpec("breath", "oneshot", 2.4, breath_clip))

    def roar(ab, D, env):
        ta, tp_ = 0.35, 0.7
        ts = times(D, 60, [ta, tp_])
        e = lambda t: end_env(t, D, 0.15)  # noqa: E731
        dip = lambda t: smooth(t, 0.02, ta) * (1 - smooth(t, ta, tp_))  # noqa: E731
        rear = lambda t: smooth(t, ta, tp_) * (1 - smooth(t, 1.45, D))  # noqa: E731
        trem = lambda t: 3.0 * math.exp(-2.5 * max(0.0, t - tp_)) * math.sin(2 * math.pi * 14 * (t - tp_)) * (t > tp_)  # noqa: E731
        hd = lambda t: facing * X * (-10.0 * dip(t) + 24.0 * rear(t)) * e(t)  # noqa: E731
        if neck_sp:
            neck_wave(ab, ts, D, 0.0, 1, False, heading=hd, head_keep=0.0)
        put(ab, head_ctrl, "rotate", ts, lambda t: facing * X * (-6.0 * dip(t) + 8.0 * rear(t) + trem(t)) * e(t))
        put(ab, "q_body", "rotate", ts, lambda t: facing * X * (-1.5 * dip(t) + 5.0 * rear(t)) * e(t))
        put(ab, "q_body", "translate", ts, lambda t: (0.0, -0.03 * L * X * dip(t) * e(t)))
        if jb:
            put(ab, jb, "rotate", ts, lambda t: -facing * 34.0 * X * (spring_step(t - 0.62, 2.5, 0.35) * (1 - smooth(t, 1.45, 1.75))) * e(t))
        if wings:
            key_wings(ab, fl, ts, lambda t: ([X * (30.0 * rear(t) - 6.0 * dip(t)) * e(t)] + [X * 12.0 * rear(t) * e(t)] * 2, 1.0, 0.0), False)
        if tail_sp:
            tail_wave(ab, ts, D, 0.0, 1, False, heading=lambda t: facing * X * 20.0 * rear(t) * math.sin(2 * math.pi * 3 * t) * e(t))
        event(ab, tp_, "sfx_roar")
        event(ab, tp_, "screen_shake", float=float(P["shake"]) * X, int=600)
        return {"peak": tp_, "tremor_hz": 14}
    specs.append(ClipSpec("roar", "oneshot", 2.0, roar))

    made["clips"] = merge_clips(sk, [s for s in specs if s.name in want])
    made["clips"].update({c: dict(q["clips"][c], merged=True) for c in ("idle", "walk") if c in q["clips"]})
    made.update(bones={"head": head_ctrl, "jaw": jb, "breath": breath, "ae": ae_bone}, fire=fire, glow=glow,
                physics=phys, facing=facing)
    return made


# ================================================================== the entry point
RIGS = {"slime": _rig_slime, "golem": _rig_golem, "ghost": _rig_ghost, "tentacle": _rig_tentacle, "dragon": _rig_dragon,
        "insect": _rig_insect, "plant": _rig_plant, "mimic": _rig_mimic}
MARKER = {"slime": "slime", "golem": "golem", "ghost": "ghost", "tentacle": "beast", "dragon": "q_body", "insect": "insect",
          "plant": "plant", "mimic": "mimic"}


def rig_creature(project: Project, kind: str = "", clips: list[str] | str | None = None, seed: int = 7,
                 exaggerate: float = 1.0, options: dict | None = None) -> dict:
    """Rig a creature of ``kind`` from its layers (CREATURE_LAYERS[kind]) and build its clips (CREATURE_CLIPS[kind]).
    kind "" lists the kinds with their layer conventions, clips and options. Does not save."""
    if not kind:
        return {"kinds": list_kinds()}
    if kind not in KINDS:
        raise ValueError(f"unknown creature kind {kind!r}; one of {list(KINDS)}")
    if exaggerate <= 0:
        raise ValueError("exaggerate must be > 0")
    sk = project.data
    if sk.has_bone(MARKER[kind]):
        raise ValueError(f"this project is already rigged as a {kind} (bone {MARKER[kind]!r} exists)")
    P = _opts(kind, options)
    made = RIGS[kind](project, P, int(seed), float(exaggerate), clips)
    from . import qa
    b = qa.budget(sk, "mobile_character")
    made.update(kind=kind, counts=_counts(sk), animations=sorted(sk.animations),
                budget={"profile": "mobile_character", "ok": b["ok"], "over_budget": b["over_budget"], "metrics": b["metrics"]})
    return made


# ================================================================== procedural samples
def _canvas(sh: Sheet) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGBA", (sh.W, sh.H), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def _ell(sh: Sheet, cx, cy, rx, ry, ang=0.0):
    return lambda d, o: d.polygon(ellipse_poly(sh, cx, cy, max(rx - o, 1), max(ry - o, 1), ang), fill=255)


def _poly(sh: Sheet, pts, centre=None):
    P = np.asarray(pts, float)
    c = P.mean(0) if centre is None else np.asarray(centre, float)

    def shape(d, o):
        Q = []
        for p in P:
            v = p - c
            n = float(np.hypot(*v)) or 1.0
            Q.append(sh.px(*(p - v / n * o)))
        d.polygon(Q, fill=255)
    return shape


def _rock(cx, cy, rx, ry, seed, n=11):
    rng = np.random.default_rng(seed)
    a0 = float(rng.uniform(0, 2 * math.pi))
    return [(cx + rx * float(rng.uniform(0.86, 1.05)) * math.cos(a0 + 2 * math.pi * k / n),
             cy + ry * float(rng.uniform(0.86, 1.05)) * math.sin(a0 + 2 * math.pi * k / n)) for k in range(n)]


def _spots(color, fn):
    class S:
        pass
    s = S()
    s.color = color
    s.__class__.__call__ = lambda self, d: fn(d)
    return s


def _eye(sh: Sheet, x, y, rx, ry, iris=(25, 20, 35), white=None, glint=True):
    im, d = _canvas(sh)
    px, py = sh.px(x, y)
    if white:
        d.ellipse([px - rx - 3, py - ry - 3, px + rx + 3, py + ry + 3], fill=white + (255,))
    d.ellipse([px - rx, py - ry, px + rx, py + ry], fill=tuple(iris) + (255,))
    if glint:
        d.ellipse([px - rx * 0.55, py - ry * 0.6, px - rx * 0.05, py - ry * 0.1], fill=(255, 255, 255, 255))
    return im


def _sample_slime(p: Project) -> None:
    sh = Sheet(p, 360, 300, 180, 280)
    im, d = _canvas(sh)
    x, y = sh.px(0, 4)
    d.ellipse([x - 112, y - 13, x + 112, y + 13], fill=(10, 30, 20, 110))
    sh.add("shadow", im.filter(ImageFilter.GaussianBlur(3)))

    def dome(d_, o):
        pts = []
        for k in range(72):
            a = 2 * math.pi * k / 72
            ry = (112 if math.sin(a) > 0 else 84) - o
            pts.append(sh.px((106 - o) * math.cos(a) * (1 + 0.04 * math.sin(a)), 88 + ry * math.sin(a)))
        d_.polygon(pts, fill=255)
    bubbles = _spots((190, 250, 200), lambda d_: [d_.ellipse([sh.px(bx - r, 0)[0], sh.px(0, by + r)[1], sh.px(bx + r, 0)[0],
                                                              sh.px(0, by - r)[1]], fill=255)
                                                  for bx, by, r in ((-60, 60, 9), (55, 40, 7), (70, 120, 6), (-20, 30, 5))])
    sh.add("body", sh.paint(dome, (150, 240, 170), (40, 160, 90), outline=(20, 80, 45), spots=bubbles))
    im, d = _canvas(sh)
    x, y = sh.px(-48, 150)
    d.ellipse([x - 24, y - 11, x + 24, y + 11], fill=(255, 255, 255, 190))
    sh.add("shine", im.filter(ImageFilter.GaussianBlur(1.2)))
    for side, ex in (("l", -36), ("r", 36)):
        sh.add(f"eye_{side}", _eye(sh, ex, 104, 11, 16))
    im, d = _canvas(sh)
    d.arc([sh.px(-16, 0)[0], sh.px(0, 84)[1], sh.px(16, 0)[0], sh.px(0, 64)[1]], 20, 160, fill=(20, 70, 40, 255), width=4)
    sh.add("mouth", im)


def _sample_golem(p: Project) -> None:
    sh = Sheet(p, 440, 420, 220, 400)
    stone, deep, ol = (165, 160, 152), (92, 88, 86), (42, 38, 36)
    pock = lambda pts: _spots((120, 115, 110), lambda d_: [d_.ellipse([sh.px(x - r, 0)[0], sh.px(0, y + r)[1], sh.px(x + r, 0)[0],  # noqa: E731
                                                                       sh.px(0, y - r)[1]], fill=255) for x, y, r in pts])
    for side, sg in (("l", -1), ("r", 1)):
        sh.add(f"leg_{side}", sh.paint(_poly(sh, _rock(sg * 44, 50, 30, 50, 3 + (sg > 0))), stone, deep, outline=ol))
    for side, sg in (("l", -1), ("r", 1)):
        sh.add(f"arm_{side}", sh.paint(_poly(sh, _rock(sg * 128, 190, 30, 44, 11 + (sg > 0), 9)), stone, deep, outline=ol))
        sh.add(f"fist_{side}", sh.paint(_poly(sh, _rock(sg * 136, 118, 34, 30, 21 + (sg > 0), 9)), stone, deep, outline=ol,
                                        spots=pock([(sg * 130, 120, 5)])))
    sh.add("torso", sh.paint(_poly(sh, _rock(0, 182, 92, 76, 5, 13)), stone, deep, outline=ol,
                             spots=pock([(-50, 200, 7), (40, 150, 6), (60, 220, 5), (-30, 130, 4)])))
    sh.add("head", sh.paint(_poly(sh, _rock(0, 296, 50, 38, 9, 10)), stone, deep, outline=ol))
    sh.add("rock1", sh.paint(_poly(sh, _rock(-92, 336, 17, 14, 31, 8)), stone, deep, outline=ol))
    sh.add("rock2", sh.paint(_poly(sh, _rock(98, 322, 13, 11, 37, 8)), stone, deep, outline=ol))
    for nm, pts, wd in (("crack1", [(-42, 228), (-14, 196), (-34, 168), (2, 140), (-6, 120)], 5),
                        ("crack2", [(46, 214), (62, 182), (40, 158), (56, 132)], 4),
                        ("crack3", [(-14, 312), (2, 300), (-4, 288)], 3)):
        im, d = _canvas(sh)
        d.line(sh.pts(pts), fill=(255, 196, 90, 255), width=wd, joint="curve")
        d.line(sh.pts(pts), fill=(255, 245, 210, 255), width=max(1, wd - 3), joint="curve")
        sh.add(nm, im)
    for side, ex in (("l", -18), ("r", 18)):
        im, d = _canvas(sh)
        x, y = sh.px(ex, 300)
        d.polygon([(x - 9, y - 2), (x + 9, y - 4), (x + 7, y + 3), (x - 8, y + 3)], fill=(255, 190, 70, 255))
        sh.add(f"eye_{side}", im)


def _sample_ghost(p: Project) -> None:
    sh = Sheet(p, 380, 470, 200, 440)
    pts, hw = [(0, 330), (2, 255), (-8, 180), (-32, 110), (-70, 52)], [86, 78, 58, 32, 6]
    from .rig_chain import spline
    sp_, sw = spline(pts, hw, 30)
    top, bot, ol = (245, 250, 255), (150, 192, 238), (70, 95, 150)
    for nm, wp, ww in (("wisp1", [(-60, 62), (-108, 44), (-150, 58)], [8, 5, 2]), ("wisp2", [(-38, 98), (-84, 104), (-120, 128)], [7, 4, 1.5])):
        a, b = spline(wp, ww, 14)
        sh.add(nm, sh.paint(strip_shape(sh, a, b), top, bot, outline=ol, ow=2))
    sh.add("body", sh.paint(strip_shape(sh, sp_, sw), top, bot, outline=ol))
    sh.sk.slot("body").color = "FFFFFFEE"
    for nm in ("wisp1", "wisp2"):
        sh.sk.slot(nm).color = "FFFFFFB4"
    for nm, wp in (("arm_l", [(-72, 250), (-104, 228), (-122, 206)]), ("arm_r", [(72, 252), (104, 236), (124, 218)])):
        a, b = spline(wp, [16, 12, 8], 12)
        sh.add(nm, sh.paint(strip_shape(sh, a, b), top, bot, outline=ol, ow=2.5))
    for side, ex in (("l", -28), ("r", 28)):
        sh.add(f"eye_{side}", _eye(sh, ex, 338, 11, 17, iris=(30, 30, 60)))
    im, d = _canvas(sh)
    x, y = sh.px(0, 300)
    d.ellipse([x - 13, y - 15, x + 13, y + 15], fill=(40, 40, 80, 255))
    sh.add("mouth", im)


def _sample_tentacle(p: Project) -> None:
    sh = Sheet(p, 640, 560, 320, 540)
    from .rig_chain import spline
    col_t, col_b, ol = (200, 110, 225), (110, 40, 150), (55, 20, 70)
    roots = [(-74, 238), (-38, 222), (0, 216), (38, 222), (74, 238)]
    angs = [-152, -116, -90, -64, -28]

    def tent(i):
        a = math.radians(angs[i])
        u, n = np.array((math.cos(a), math.sin(a))), np.array((-math.sin(a), math.cos(a)))
        curl = 1.0 if angs[i] < -90 else -1.0
        cps = [np.array(roots[i]) + u * 236 * s + n * curl * 46 * s ** 2.2 for s in np.linspace(0, 1, 6)]
        return spline([tuple(c) for c in cps], [26, 22, 17, 12, 8, 4], 30)
    order = [0, 4, None, 1, 3, 2]
    for i in order:
        if i is None:
            sh.add("core", sh.paint(_ell(sh, 0, 330, 98, 112), (215, 130, 235), (120, 45, 160), outline=ol,
                                    spots=_spots((235, 175, 245), lambda d_: [d_.ellipse([sh.px(x - r, 0)[0], sh.px(0, y + r)[1],
                                                                                          sh.px(x + r, 0)[0], sh.px(0, y - r)[1]], fill=255)
                                                                              for x, y, r in ((-40, 400, 10), (30, 410, 7), (55, 370, 6))])))
            continue
        a, b = tent(i)
        dark = i in (0, 4)
        sh.add(f"tentacle{i + 1}", sh.paint(strip_shape(sh, a, b), tuple(int(v * (0.8 if dark else 1)) for v in col_t),
                                            tuple(int(v * (0.8 if dark else 1)) for v in col_b), outline=ol))
    for side, ex in (("l", -38), ("r", 38)):
        im, d = _canvas(sh)
        x, y = sh.px(ex, 318)
        d.ellipse([x - 20, y - 17, x + 20, y + 17], fill=(255, 235, 120, 255), outline=(60, 30, 20, 255), width=3)
        d.ellipse([x - 4, y - 13, x + 4, y + 13], fill=(30, 20, 30, 255))
        sh.add(f"eye_{side}", im)
    im, d = _canvas(sh)
    x, y = sh.px(0, 262)
    d.polygon([(x - 14, y - 6), (x + 14, y - 6), (x, y + 14)], fill=(70, 30, 40, 255))
    sh.add("beak", im)
    im, d = _canvas(sh)
    x, y = sh.px(250, 480)
    d.ellipse([x - 10, y - 10, x + 10, y + 10], fill=(255, 205, 235, 255), outline=(150, 70, 140, 255), width=3)
    d.ellipse([x - 3, y - 3, x + 3, y + 3], fill=(180, 90, 160, 255))
    sh.add("sucker", im)


def _sample_dragon(p: Project) -> None:
    from .rig_chain import spline
    sh = Sheet(p, 1040, 640, 540, 610)
    g_t, g_b, ol = (120, 190, 130), (52, 112, 72), (28, 52, 36)
    m_t, m_b = (200, 100, 86), (120, 50, 50)

    def dim(c, k=0.7):
        return tuple(int(v * k) for v in c)

    def capsule(pts, radii):
        a, b = spline(pts, radii, max(8, 6 * len(pts)))
        return strip_shape(sh, a, b)

    def wing(shift, dark):
        sx, sy = shift
        arm = [(40 + sx, 214 + sy), (-24 + sx, 326 + sy), (-112 + sx, 404 + sy)]
        mem = [(40 + sx, 214 + sy), (-24 + sx, 330 + sy), (-112 + sx, 406 + sy), (-236 + sx, 338 + sy), (-196 + sx, 304 + sy),
               (-214 + sx, 262 + sy), (-160 + sx, 238 + sy), (-100 + sx, 222 + sy)]
        k = 0.72 if dark else 1.0
        return sh.paint(_poly(sh, mem), dim(m_t, k), dim(m_b, k), outline=ol,
                        spots=_spots(dim((235, 205, 160), k), lambda d_: d_.line(sh.pts(arm), fill=255, width=9, joint="curve")))
    sh.add("wing_l", wing((26, 16), True))
    legs = {"hind": ([(-110, 168), (-86, 112), (-122, 60), (-112, 18)], [34, 19, 12, 10], (-98, 10)),
            "front": ([(100, 165), (78, 118), (96, 58), (100, 18)], [26, 16, 12, 10], (114, 10))}

    def leg_layers(side):
        far = side == "L"
        t, b = (dim(g_t), dim(g_b)) if far else (g_t, g_b)
        off = np.array((14.0, 5.0)) if far else np.zeros(2)
        for end in ("hind", "front"):
            J, R, paw = legs[end]
            J = [tuple(np.add(j, off)) for j in J]
            for seg, i0 in (("upper", 0), ("lower", 1), ("mid", 2)):
                sh.add(f"{end}_{seg}_{side}", sh.paint(capsule([J[i0], J[i0 + 1]], [R[i0], R[i0 + 1]]), t, b, outline=ol, ow=2.5))
            px_, py_ = np.add(paw, off)
            sh.add(f"{end}_foot_{side}", sh.paint(_ell(sh, px_, py_, 24, 10), t, b, outline=ol, ow=2.5))
    leg_layers("L")
    sh.add("tail", sh.paint(capsule([(-140, 186), (-220, 160), (-300, 148), (-372, 166), (-424, 204)], [28, 20, 13, 8, 4]), g_t, g_b,
                            outline=ol))
    belly = _spots((222, 212, 150), lambda d_: d_.polygon(ellipse_poly(sh, 10, 140, 120, 26), fill=255))
    body = [(0, 176, 150, 56), (86, 172, 62, 60), (-104, 178, 58, 52)]
    sh.add("body", sh.paint(lambda d_, o: [d_.polygon(ellipse_poly(sh, cx, cy, rx - o, ry - o), fill=255) for cx, cy, rx, ry in body],
                            g_t, g_b, outline=ol, spots=belly))
    sh.add("neck", sh.paint(capsule([(104, 196), (148, 242), (186, 292), (214, 336)], [36, 29, 24, 21]), g_t, g_b, outline=ol))
    sh.add("jaw", sh.paint(capsule([(242, 326), (304, 318)], [11, 7]), dim(g_t, 0.85), dim(g_b, 0.85), outline=ol, ow=2.5))
    for nm, a, b_ in (("horn_1", (226, 376), (194, 418)), ("horn_2", (210, 370), (172, 398))):
        sh.add(nm, sh.paint(capsule([a, b_], [8, 2]), (245, 236, 205), (190, 175, 140), outline=ol, ow=2))
    sh.add("head", sh.paint(lambda d_, o: [d_.polygon(ellipse_poly(sh, 240, 352, 46 - o, 32 - o), fill=255),
                                           strip_shape(sh, *spline([(262, 346), (318, 338)], [20, 14], 10))(d_, o)],
                            g_t, g_b, outline=ol))
    im, d = _canvas(sh)
    x, y = sh.px(258, 362)
    d.ellipse([x - 9, y - 7, x + 9, y + 7], fill=(255, 220, 80, 255), outline=(40, 30, 20, 255), width=2)
    d.ellipse([x - 2, y - 6, x + 2, y + 6], fill=(30, 20, 20, 255))
    sh.add("eye_R", im)
    leg_layers("R")
    sh.add("wing_r", wing((0, 0), False))


def _sample_insect(p: Project) -> None:
    sh = Sheet(p, 420, 300, 200, 284)
    b_t, b_b, ol = (180, 80, 58), (92, 34, 28), (36, 18, 16)
    leg_t, leg_b = (90, 62, 52), (50, 34, 30)
    from .rig_chain import spline
    J = {1: [(18, 60), (50, 110), (80, 6)], 2: [(0, 58), (10, 108), (22, 6)], 3: [(-18, 60), (-56, 108), (-90, 6)]}

    def wing(dark):
        sx, sy = (8, 6) if dark else (0, 0)
        im = sh.paint(_ell(sh, -44 + sx, 102 + sy, 62, 14, 6), (225, 238, 255), (170, 195, 235), outline=(70, 90, 130), ow=2)
        a = np.asarray(im).copy()
        a[..., 3] = (a[..., 3] * (0.62 if dark else 0.78)).astype(np.uint8)
        return Image.fromarray(a, "RGBA")

    def legs(side):
        far = side == "L"
        off = np.array((7.0, 4.0)) if far else np.zeros(2)
        t, b = (tuple(int(v * 0.7) for v in leg_t), tuple(int(v * 0.7) for v in leg_b)) if far else (leg_t, leg_b)
        for k, pts in J.items():
            pts = [tuple(np.add(q, off)) for q in pts]
            for seg, (a, c), r in (("upper", (pts[0], pts[1]), [6, 5]), ("lower", (pts[1], pts[2]), [5, 2.5])):
                xs, ws = spline([a, c], r, 8)
                sh.add(f"leg_{side}{k}_{seg}", sh.paint(strip_shape(sh, xs, ws), t, b, outline=ol, ow=1.5))
    sh.add("wing_l", wing(True))
    legs("L")
    sh.add("abdomen", sh.paint(_ell(sh, -64, 76, 48, 30, 4), b_t, b_b, outline=ol,
                               spots=_spots((205, 120, 90), lambda d_: [d_.line(sh.pts([(xx, 50), (xx + 4, 104)]), fill=255, width=3)
                                                                        for xx in (-90, -70, -50)])))
    sh.add("thorax", sh.paint(_ell(sh, 0, 72, 31, 21), b_t, b_b, outline=ol))
    legs("R")
    for nm, pts in (("antenna_l", [(78, 98), (104, 132), (134, 150)]), ("antenna_r", [(72, 98), (94, 138), (118, 162)])):
        xs, ws = spline(pts, [3.5, 2.5, 1.5], 14)
        sh.add(nm, sh.paint(strip_shape(sh, xs, ws), (70, 40, 35), (40, 24, 20), outline=ol, ow=1))
    sh.add("head", sh.paint(_ell(sh, 62, 82, 22, 19), b_t, b_b, outline=ol))
    sh.add("eye", _eye(sh, 72, 88, 7, 8, iris=(20, 15, 15)))
    im, d = _canvas(sh)
    d.polygon(sh.pts([(76, 70), (94, 64), (82, 75)]), fill=(40, 22, 20, 255))
    sh.add("mandible", im)
    sh.add("wing_r", wing(False))


def _sample_plant(p: Project) -> None:
    from .rig_chain import spline
    sh = Sheet(p, 560, 540, 280, 520)
    bark_t, bark_b, ol = (140, 102, 66), (82, 56, 36), (40, 26, 18)
    leaf_t, leaf_b, lol = (130, 210, 96), (52, 134, 56), (26, 66, 30)

    def strip(pts, hw, n=18):
        a, b = spline(pts, hw, n)
        return strip_shape(sh, a, b)
    for nm, pts, hw in (("root_l", [(-24, 22), (-76, 10), (-128, 2)], [18, 11, 5]), ("root_r", [(24, 22), (78, 9), (130, 2)], [18, 11, 5])):
        sh.add(nm, sh.paint(strip(pts, hw), bark_t, bark_b, outline=ol))
    for nm, pts, hw in (("branch1", [(-16, 150), (-82, 196), (-136, 252)], [17, 11, 6]),
                        ("branch2", [(16, 140), (86, 186), (146, 236)], [17, 11, 6]),
                        ("branch3", [(-12, 214), (-56, 276), (-76, 330)], [14, 9, 5]),
                        ("branch4", [(12, 220), (66, 282), (90, 336)], [14, 9, 5])):
        sh.add(nm, sh.paint(strip(pts, hw), bark_t, bark_b, outline=ol))
    knots = _spots((110, 78, 50), lambda d_: [d_.ellipse([sh.px(x - r, 0)[0], sh.px(0, y + r)[1], sh.px(x + r, 0)[0],
                                                          sh.px(0, y - r)[1]], fill=255) for x, y, r in ((-14, 40, 5), (12, 196, 4))])
    sh.add("trunk", sh.paint(strip([(0, 0), (0, 80), (-6, 160), (0, 246)], [48, 37, 31, 26]), bark_t, bark_b, outline=ol, spots=knots))
    for i, (cx, cy, ang) in enumerate(((-152, 262, 30), (-118, 284, -20), (160, 246, -30), (128, 266, 20),
                                       (-84, 348, 40), (-58, 356, -10), (100, 352, -40), (72, 360, 10)), 1):
        sh.add(f"leaf{i}", sh.paint(_ell(sh, cx, cy, 36, 22, ang), leaf_t, leaf_b, outline=lol, ow=2.5))
    for side, ex in (("l", -13), ("r", 14)):
        im, d = _canvas(sh)
        x, y = sh.px(ex, 138)
        d.ellipse([x - 10, y - 8, x + 10, y + 8], fill=(40, 26, 16, 255))
        d.ellipse([x - 4, y - 4, x + 4, y + 4], fill=(255, 220, 90, 255))
        sh.add(f"eye_{side}", im)
    im, d = _canvas(sh)
    d.polygon(sh.pts([(-14, 108), (-6, 100), (0, 108), (6, 100), (14, 108), (8, 94), (-8, 94)]), fill=(40, 22, 14, 255))
    sh.add("mouth", im)


def _sample_mimic(p: Project) -> None:
    from .rig_chain import spline
    sh = Sheet(p, 420, 330, 200, 310)
    wood_t, wood_b, ol = (176, 112, 62), (108, 64, 34), (48, 28, 16)
    gold = (236, 190, 70)
    sh.add("inside", sh.paint(_poly(sh, [(-102, 100), (106, 100), (106, 156), (-102, 156)]), (70, 14, 24), (40, 6, 14), outline=(30, 4, 10), ow=1))
    sh.add("gold", sh.paint(lambda d_, o: [d_.ellipse([sh.px(x - 14 + o, 0)[0], sh.px(0, y + 7 - o)[1], sh.px(x + 14 - o, 0)[0],
                                                        sh.px(0, y - 7 + o)[1]], fill=255)
                                           for x, y in ((-50, 108), (-24, 112), (4, 110), (30, 114), (52, 108), (-36, 120), (16, 122))],
                            (255, 228, 120), (200, 150, 40), outline=(120, 80, 20), ow=2))
    for side, ex in (("l", -12), ("r", 30)):
        im, d = _canvas(sh)
        x, y = sh.px(ex, 136)
        d.ellipse([x - 9, y - 7, x + 9, y + 7], fill=(255, 236, 90, 255))
        d.ellipse([x - 2, y - 6, x + 2, y + 6], fill=(40, 10, 10, 255))
        sh.add(f"eye_{side}", im)
    im, d = _canvas(sh)
    for k in range(9):
        x0 = -94 + k * 22
        d.polygon(sh.pts([(x0, 106), (x0 + 16, 106), (x0 + 8, 124)]), fill=(250, 245, 230, 255), outline=(90, 80, 70, 255))
    sh.add("teeth_lower", im)
    bands = _spots((84, 60, 40), lambda d_: [d_.rectangle([sh.px(x, 0)[0], sh.px(0, 110)[1], sh.px(x + 12, 0)[0], sh.px(0, 0)[1]], fill=255)
                                             for x in (-80, 64)])
    sh.add("base", sh.paint(_poly(sh, [(-112, 4), (112, 4), (112, 110), (-112, 110)]), wood_t, wood_b, outline=ol, spots=bands))
    a, b = spline([(-40, 116), (40, 120), (108, 112), (126, 86), (120, 62)], [15, 14, 12, 10, 7], 24)
    sh.add("tongue", sh.paint(strip_shape(sh, a, b), (240, 110, 140), (180, 50, 80), outline=(90, 20, 40), ow=2.5))
    im, d = _canvas(sh)
    for k in range(9):
        x0 = -94 + k * 22
        d.polygon(sh.pts([(x0, 114), (x0 + 16, 114), (x0 + 8, 96)]), fill=(250, 245, 230, 255), outline=(90, 80, 70, 255))
    sh.add("teeth_upper", im)
    top = [(112, 114), (-112, 114)] + [(-112 + 224 * k / 16, 150 + 30 * math.sin(math.pi * k / 16)) for k in range(17)]
    bands2 = _spots((84, 60, 40), lambda d_: [d_.rectangle([sh.px(x, 0)[0], sh.px(0, 186)[1], sh.px(x + 12, 0)[0], sh.px(0, 112)[1]], fill=255)
                                              for x in (-80, 64)])
    sh.add("lid", sh.paint(_poly(sh, top, centre=(0, 140)), (190, 124, 70), wood_b, outline=ol, spots=bands2))
    sh.add("lock", sh.paint(_poly(sh, [(104, 118), (122, 118), (122, 146), (104, 146)]), gold, (170, 120, 30), outline=(90, 60, 10), ow=2))


SAMPLES = {"slime": (_sample_slime, 360, 300), "golem": (_sample_golem, 440, 420), "ghost": (_sample_ghost, 380, 470),
           "tentacle": (_sample_tentacle, 640, 560), "dragon": (_sample_dragon, 1040, 640), "insect": (_sample_insect, 420, 300),
           "plant": (_sample_plant, 560, 540), "mimic": (_sample_mimic, 420, 330)}


def make_sample_creature(out_dir: str | Path, kind: str, name: str = "") -> Project:
    """A procedural creature of ``kind`` drawn from simple shapes, one PNG per layer, named exactly as import_psd would
    name a PSD that follows CREATURE_LAYERS[kind]. Saved; not rigged."""
    if kind not in SAMPLES:
        raise ValueError(f"unknown creature kind {kind!r}; one of {list(KINDS)}")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    fn, W, H = SAMPLES[kind]
    p = Project(out / f"{name or kind}.json", new_skeleton(width=W, height=H))
    fn(p)
    p.save()
    return p
