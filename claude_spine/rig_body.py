"""Biped character rigs and the character clip contract: the ``rig_biped`` / ``clip_set`` / ``secondary`` /
``squash_stretch`` tools' engine.

**rig_biped.** A project from ``import_psd`` (origin "bottom") or :func:`make_sample_biped` whose layers follow
:data:`BIPED_LAYERS` becomes a game-ready biped:

    root → ground (floor, under the feet) → hips → spine1 → spine2 → spine3 → chest → neck → head
                                                          chest → shoulder_l/r → upper_arm → lower_arm → hand
                                            hips → thigh_l/r → shin_l/r
           ground → ik_foot_l/r → foot_l/r          chest → arm_space → ik_hand_l/r

* Bones are placed from the art: each limb layer's own centre line (the slab centroids ``rig.strand_centerline``
  uses) gives the shoulder/hip at its top cap, the elbow/knee in its middle and the wrist/ankle at its bottom cap,
  inset by the limb's half width so the pivots sit in the round ends. Split layers (upper_arm + lower_arm,
  thigh + shin) meet at the midpoint of their two caps.
* Two-bone IK on arms and legs. The bend direction is the art's own (the joint's side of the root→tip line); when
  the art is straight the default is knees forward, elbows back for the facing found from the feet.
* Foot IK is pinned to the floor: the foot targets live under ``ground``, not under the hips, so the body bobs, leans
  and squashes while planted feet do not move by a pixel. The foot bones are children of their targets, so a key
  on ``ik_foot_*`` rolls the foot.
* One weighted mesh across each joint (``rig_mesh``): the torso over hips → spine → chest, each leg over
  hips → thigh → shin → foot, each arm over shoulder → upper → lower → hand. A bend is a smooth deformation of
  one surface, so it cannot open a crack. Split limb layers are each weighted across their own joint so their
  overlapping ends travel together.
* Breathing (``breathe`` loop, also inside ``idle``): one real breath is 4 s, a quick inhale (40 %) and a long
  exhale. The chest scales 2 % (uniform, the neck and shoulders counter-scale exactly so the head and arms keep
  their size), the shoulders rise 1 % of the height 0.12 s after the chest, the head counter-nods 0.25 s later:
  lag by levels.
* Look-at hook (``look_target``, a child of ``look_base`` at local 0,0): the eyes slide toward it at once, the head
  aims at a follower that trails the target by exactly 2 frames at 30 fps (a critically damped spring solved by a
  Spine physics constraint, its omega calibrated on the runtime's own 60 Hz solver: a target moving at constant
  speed is followed 1/15 s behind), and the spine twists 20 % of the head's turn. Internal and small: 4 bones, 1 IK, 1 physics, 6
  transform constraints. Game code moves ``look_target``; nothing else.

**clip_set.** :data:`CHARACTER_CLIPS` is the character contract: the SAME clip names for every rig type, so game
code never changes between characters. Each clip lists what it needs (canonical bone names, mapped with
``bone_map`` for rigs named differently); clips whose bones are missing are skipped and reported. Loops close
exactly, one-shots end exactly on the setup pose, the artist's setup never moves. Exaggerated real physics:

* walk / run: an in-place treadmill. A planted foot moves backward at exactly the ground speed v (heel rocker →
  flat → toe rocker, every rocker pivot travelling at -v), so the game moves the character at v and the feet do not
  slide. Walking is an inverted pendulum (hips highest at the passing pose); running is a spring-mass (the stance
  compresses a spring, the flight is a gravity parabola, velocities matched at take-off and touch-down). The hips
  sit as low as needed so a leg never locks. ``sfx_step`` fires on every footfall with the foot bone in its string
  and the ground speed (px/s) in its float. The strands get a headwind ~ v^2 (aerodynamic drag).
* jump / win: anticipation crouch, a volume-preserving launch stretch, a ballistic parabola, touch-down absorb.
* land: the impact is caught by an exact spring: the body squashes to exactly 0.85, overshoots to exactly 1.05
  (damping ratio solved from the two extremes, zeta = ln3 / sqrt(pi^2 + ln^2 3)) and settles; volume preserved.
* hit: a 2-frame anticipation OPPOSITE to the blow, then the recoil on an exact spring, lagging up the chain
  (hips, spine, chest, head whiplash) with a red flash.
* attack: wind-up opposite to the strike, a fast strike, an exact-spring follow-through, recovery.
* lose / talk / idle / idle_fidget: slump and sigh, syllable nods, breathing, a glance with the look-at hook.

**secondary.** One call finds every strand-like layer (hair, cloth, tails, ears, by name and by elongated shape) and
gives it a chain, a weighted mesh and physics (presets :data:`SECONDARY_PRESETS`: hair, cloth, silk, leather, chain,
feather, tail, ear, pouch), parented to the body bone its root overlaps.

**squash_stretch.** Volume-preserving squash on any bone chain (sx = sy^-1/2: a cylinder keeps its volume) driven by
an exact-overshoot spring, keyed onto a carrier bone inserted at the chain base and aligned with the chain, so the
artist's keys are never touched.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .geometry import points_in_polygon
from .ir import Bone, Key, MeshAttachment, RegionAttachment, SkeletonData, Slot, _wrap, new_skeleton
from .mesh import region_pixel_to_local, rig_mesh, to_world
from .project import Project
from .rig import (PHYSICS_PRESETS, _depth_order, add_ik, add_physics, add_transform, reparent_slot,
                  rig_strand, setup_hull_world, strand_centerline)
from .timeline import AnimBuilder
from .weights import seg_distance

# ======================================================================================== naming convention
BIPED_LAYERS: dict[str, dict] = {
    # part           aliases (case-insensitive; sides as _l/_r, .L/.R, " left", "left_" ...)
    "torso":     dict(aliases=("torso", "body", "trunk", "tunic", "shirt", "chest", "jacket"), sided=False,
                      required=True, rig="one mesh weighted hips → spine1 → spine2 → spine3 → chest"),
    "pelvis":    dict(aliases=("pelvis", "hips", "hip", "waist", "shorts", "pants", "trousers"), sided=False,
                      required=False, rig="region on hips"),
    "neck":      dict(aliases=("neck",), sided=False, required=False, rig="mesh weighted chest → neck → head"),
    "head":      dict(aliases=("head", "face", "skull"), sided=False, required=True,
                      rig="region on head; every layer inside the head's outline (eyes, mouth, ears, hat) follows it"),
    "arm":       dict(aliases=("arm", "sleeve", "whole_arm"), sided=True, required="arm or upper_arm + lower_arm",
                      rig="one mesh weighted shoulder → upper_arm → lower_arm → hand, 2-bone IK"),
    "upper_arm": dict(aliases=("upper_arm", "upperarm", "bicep", "arm_upper"), sided=True, required=False,
                      rig="mesh weighted shoulder → upper_arm → lower_arm"),
    "lower_arm": dict(aliases=("lower_arm", "lowerarm", "forearm", "fore_arm", "arm_lower"), sided=True,
                      required=False, rig="mesh weighted upper_arm → lower_arm → hand"),
    "hand":      dict(aliases=("hand", "fist", "glove", "palm"), sided=True, required=False, rig="region on hand"),
    "leg":       dict(aliases=("leg", "whole_leg"), sided=True, required="leg or thigh + shin",
                      rig="one mesh weighted hips → thigh → shin → foot, 2-bone IK to a floor-pinned target"),
    "thigh":     dict(aliases=("thigh", "upper_leg", "upperleg", "leg_upper"), sided=True, required=False,
                      rig="mesh weighted hips → thigh → shin"),
    "shin":      dict(aliases=("shin", "calf", "lower_leg", "lowerleg", "leg_lower"), sided=True, required=False,
                      rig="mesh weighted thigh → shin → foot"),
    "foot":      dict(aliases=("foot", "boot", "shoe"), sided=True, required=False,
                      rig="mesh on foot, a child of ik_foot (floor-pinned, rolls heel → toe)"),
}
EYE_NAMES = ("eye", "eyes", "pupil", "pupils", "iris")
MOUTH_NAMES = ("mouth", "lips", "lip", "jaw")

# strand-like layers: name → secondary preset (matched on whole name tokens, longest alias first)
STRAND_NAMES: dict[str, tuple[str, ...]] = {
    "hair": ("hair", "lock", "ponytail", "pony_tail", "braid", "pigtail", "fringe", "bangs", "strand", "mane",
             "whisker", "hair_lock"),
    "cloth": ("cape", "cloak", "skirt", "coat_tail", "coattail", "robe", "cloth", "mantle", "tabard", "apron",
              "loincloth", "flap", "kilt"),
    "silk": ("scarf", "ribbon", "sash", "silk", "veil", "banner", "streamer"),
    "leather": ("belt_tail", "belt_end", "strap", "leather", "thong", "lace", "tassel"),
    "chain": ("chain", "necklace", "rope", "cord"),
    "feather": ("feather", "plume", "quill"),
    "tail": ("tail",),
    "ear": ("floppy_ear", "long_ear", "ear_long", "bunny_ear"),
}
PENDULUM_NAMES = ("pouch", "bag", "satchel", "charm", "pendant", "earring", "bell", "lantern", "flask", "medal",
                  "amulet", "keychain", "purse")
STRAND_EXCLUDE = ("sword", "blade", "staff", "spear", "gun", "shield", "weapon", "wand", "axe", "hammer", "shadow",
                  "glow", "fx", "sheath", "bow_weapon", "pole", "stick",
                  # face features are elongated too, but they never swing
                  "brow", "eyebrow", "lid", "eyelid", "lash", "lashes", "mouth", "lip", "lips", "nose", "eye", "eyes",
                  "pupil", "teeth", "beard", "mustache", "moustache", "blush", "cheek")

# Spine 4.2 physics: damping is the velocity KEPT per 1/60 s, so a LOWER damping settles faster. Cloth has more air
# drag for its mass than a lock of hair, so its damping is lower than hair's. Chain is a heavy physical pendulum
# (low stiffness for its mass → long period, little drag → keeps swinging); silk floats (very light, soft);
# leather is heavy and stiff (a short, quickly damped swing); feathers are light and stiff (a fast flutter).
SECONDARY_PRESETS: dict[str, dict] = {
    "hair":    dict(base="hair", n_bones=4, taper=0.15, over={}),
    "cloth":   dict(base="cloth", n_bones=3, taper=0.12, over=dict(damping=0.82, mass=1.8, strength=110)),
    "silk":    dict(base="ribbon", n_bones=5, taper=0.18, over=dict(mass=0.7, strength=55, damping=0.92, inertia=0.5)),
    "leather": dict(base="cloth", n_bones=3, taper=0.1, over=dict(x=0, mass=2.2, strength=150, damping=0.78,
                                                                 inertia=0.2)),
    "chain":   dict(base="tassel", n_bones=5, taper=0.05, over=dict(mass=2.6, strength=45, damping=0.93, inertia=0.55)),
    "feather": dict(base="antenna", n_bones=2, taper=0.2, over=dict(mass=0.5, strength=230, damping=0.8, inertia=0.6)),
    "tail":    dict(base="tail", n_bones=5, taper=0.12, over={}),
    "ear":     dict(base="antenna", n_bones=2, taper=0.2, over=dict(strength=150, damping=0.84)),
    "pouch":   dict(base="tassel", n_bones=1, taper=0.0, over=dict(mass=2.0, strength=70, damping=0.88, inertia=0.5)),
}

# canonical bones rig_biped makes (clip_set and qa_character speak these names; bone_map= renames them)
BIPED_BONES = ("ground", "hips", "spine1", "spine2", "spine3", "chest", "neck", "head",
               "shoulder_l", "upper_arm_l", "lower_arm_l", "hand_l", "shoulder_r", "upper_arm_r", "lower_arm_r", "hand_r",
               "thigh_l", "shin_l", "foot_l", "thigh_r", "shin_r", "foot_r",
               "ik_foot_l", "ik_foot_r", "arm_space", "ik_hand_l", "ik_hand_r",
               "look_base", "look_target", "look_follow", "look_aim_base", "look_aim", "eye_space", "mouth")
SPINE_CHAIN = ("spine1", "spine2", "spine3", "chest")
HELPER_PREFIXES = ("ik_", "look_", "ss_", "fx_", "juice_", "turn_", "arm_space", "eye_space", "ground", "root")


def _norm(name: str) -> str:
    leaf = name.replace("\\", "/").split("/")[-1].strip().lower()
    s = re.sub(r"[\s.\-]+", "_", leaf)
    return re.sub(r"_+", "_", s).strip("_")


def split_side(n: str) -> tuple[str, str | None]:
    """'arm_l' → ('arm', 'l'); 'left_arm' → ('arm', 'l'); 'arm' → ('arm', None)."""
    m = re.match(r"^(.+?)_(l|r|left|right)$", n)
    if m:
        return m.group(1), m.group(2)[0]
    m = re.match(r"^(l|r|left|right)_(.+)$", n)
    if m:
        return m.group(2), m.group(1)[0]
    return n, None


def _tokens_match(base: str, alias: str) -> bool:
    bt, at = base.split("_"), alias.split("_")
    return any(bt[i:i + len(at)] == at for i in range(len(bt) - len(at) + 1))


def _match_part(base: str) -> str | None:
    best, score = None, -1
    for part, spec in BIPED_LAYERS.items():
        for a in spec["aliases"]:
            if base == a:
                sc = 1000 + len(a)
            elif base.endswith("_" + a):
                sc = len(a)
            else:
                continue
            if sc > score:
                best, score = part, sc
    return best


def find_parts(sk: SkeletonData) -> dict[str, str]:
    """Recognise biped layers by name. Returns {"torso": slot, "head": slot, "arm_l": slot, "thigh_r": slot, ...}."""
    found: dict[str, str] = {}
    for s in sk.slots:
        base, side = split_side(_norm(s.name))
        part = _match_part(base)
        if part is None:
            continue
        spec = BIPED_LAYERS[part]
        if spec["sided"]:
            if side is None:
                continue
            key = f"{part}_{side}"
        else:
            key = part
        found.setdefault(key, s.name)
    return found


def missing_parts(found: dict[str, str]) -> list[str]:
    miss = [p for p in ("torso", "head") if p not in found]
    for s in ("l", "r"):
        if f"arm_{s}" not in found and not (f"upper_arm_{s}" in found and f"lower_arm_{s}" in found):
            miss.append(f"arm_{s} (or upper_arm_{s} + lower_arm_{s})")
        if f"leg_{s}" not in found and not (f"thigh_{s}" in found and f"shin_{s}" in found):
            miss.append(f"leg_{s} (or thigh_{s} + shin_{s})")
    return miss


def strand_kind(name: str) -> str | None:
    """Secondary preset a layer name asks for ("hair", "cloth", ... or "pouch"), else None."""
    base, _ = split_side(_norm(name))
    if any(_tokens_match(base, a) for a in PENDULUM_NAMES):
        return "pouch"
    best, n = None, 0
    for kind, aliases in STRAND_NAMES.items():
        for a in aliases:
            if _tokens_match(base, a) and len(a) > n:
                best, n = kind, len(a)
    return best


# ======================================================================================== geometry from the art
def _slot_image(project: Project, slot: str):
    sk = project.data
    s = sk.slot(slot)
    att = sk.attachment(slot)
    if not isinstance(att, RegionAttachment):
        raise ValueError(f"{slot}: rig_biped starts from region attachments (run it on a fresh import_psd)")
    im = project.image(project.att_image_name(slot, s.attachment))
    W, H = im.size
    f, _ = region_pixel_to_local(att, W, H)
    wb = sk.world()[s.bone]
    return np.array(im)[:, :, 3], (lambda px: to_world(wb, f(np.asarray(px, float))))


def _alpha_world(project: Project, slot: str, max_pts: int = 6000) -> np.ndarray:
    alpha, tw = _slot_image(project, slot)
    ys, xs = np.nonzero(alpha > 8)
    if len(xs) < 10:
        raise ValueError(f"{slot}: the layer is (almost) empty")
    P = np.c_[xs, ys].astype(float) + 0.5
    if len(P) > max_pts:
        P = P[np.linspace(0, len(P) - 1, max_pts).astype(int)]
    return tw(P)


def _limb(project: Project, slot: str, n: int = 2) -> dict:
    """Centre line (top first) of a limb layer in world space, its half width and the cap pivots."""
    alpha, tw = _slot_image(project, slot)
    cl = tw(strand_centerline(alpha, n, "top"))
    P = _alpha_world(project, slot, 3000)
    d = np.full(len(P), np.inf)
    for a, b in zip(cl[:-1], cl[1:]):
        d = np.minimum(d, seg_distance(P, a, b)[0])
    hw = float(np.percentile(d, 92))
    top, bot = cl[0], cl[-1]
    u0 = cl[1] - cl[0]
    u1 = cl[-1] - cl[-2]
    l0, l1 = float(np.hypot(*u0)), float(np.hypot(*u1))
    p_top = top + u0 / max(l0, 1e-9) * min(hw, 0.3 * l0)
    p_bot = bot - u1 / max(l1, 1e-9) * min(hw, 0.3 * l1)
    return dict(line=cl, hw=hw, top=p_top, bottom=p_bot, mid=cl[len(cl) // 2] if n >= 2 else (top + bot) / 2)


def _hull(project: Project, slot: str) -> np.ndarray:
    return setup_hull_world(project, slot)


def _alpha_hull(project: Project, slot: str) -> np.ndarray:
    """Tight outline proxy of a layer: the convex hull of its opaque pixels (world)."""
    from scipy.spatial import ConvexHull
    P = _alpha_world(project, slot, 4000)
    h = ConvexHull(P)
    return P[h.vertices]


def setup_bounds(project: Project) -> tuple[float, float, float, float]:
    sk = project.data
    pts = []
    for s in sk.slots:
        if not s.attachment or s.blend != "normal":
            continue
        try:
            pts.append(setup_hull_world(project, s.name))
        except (KeyError, ValueError, FileNotFoundError):
            continue
    if not pts:
        return (-100.0, 0.0, 100.0, 400.0)
    P = np.vstack(pts)
    return float(P[:, 0].min()), float(P[:, 1].min()), float(P[:, 0].max()), float(P[:, 1].max())


def _angle(a, b) -> float:
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))


def _bone(sk: SkeletonData, name: str, parent: str, head, tail=None, angle: float | None = None, **kw) -> str:
    head = np.asarray(head, float)
    if tail is not None:
        tail = np.asarray(tail, float)
        L = float(np.hypot(*(tail - head)))
        ang = _angle(head, tail) if L > 1e-6 else (angle or 0.0)
    else:
        L, ang = 0.0, angle or 0.0
    sk.add_bone_world(name, parent, float(head[0]), float(head[1]), ang, L, **kw)
    return name


def _bend_sign(a, j, c) -> float:
    """Cross product of (j - a) and (c - j): > 0 bends counter-clockwise (Spine bendPositive)."""
    v1, v2 = np.subtract(j, a), np.subtract(c, j)
    return float(v1[0] * v2[1] - v1[1] * v2[0])


def _place_joint(a, j, c, default_sign: float, min_deg: float = 3.0):
    """Keep the art's bend when it is clear, else put the joint 1 % of the chain length off the line in the default
    direction, so the setup bend and the IK bend direction agree and IK reproduces the setup exactly."""
    a, j, c = (np.asarray(p, float) for p in (a, j, c))
    v1, v2 = j - a, c - j
    ang = abs(math.degrees(math.atan2(v1[0] * v2[1] - v1[1] * v2[0], float(v1 @ v2))))
    if ang >= min_deg:
        return j, bool(_bend_sign(a, j, c) >= 0), "art"
    L = float(np.hypot(*(c - a)))
    t = float(np.clip((j - a) @ (c - a) / max(L * L, 1e-9), 0.3, 0.7))
    p = a + (c - a) * t
    n = np.array([-(c - a)[1], (c - a)[0]]) / max(L, 1e-9)       # left normal of a→c
    # a joint on the right of a→c bends counter-clockwise from the thigh to the shin: bendPositive
    for sgn in (1.0, -1.0):
        q = p + sgn * n * 0.01 * L
        if (_bend_sign(a, q, c) >= 0) == (default_sign >= 0):
            return q, bool(default_sign >= 0), "default"
    return p, bool(default_sign >= 0), "default"


def _facing(sk: SkeletonData, bmap: dict | None = None) -> int:
    """+1 faces screen right, -1 left: from the foot bones (heel → toe), else +1."""
    w = sk.world()
    xs = []
    for s in ("l", "r"):
        b = _b(bmap, f"foot_{s}")
        if sk.has_bone(b) and w[b].length > 1e-6:
            xs.append(w[b].tail[0] - w[b].x)
    if xs:
        return 1 if sum(xs) >= 0 else -1
    return 1


def _b(bmap: dict | None, name: str) -> str:
    return (bmap or {}).get(name, name)


# ======================================================================================== rig_biped
def rig_biped(project: Project, facing: str = "auto", meshes: bool = True, look_at: bool = True,
              breathing: bool = True, secondary_motion: bool = True, detail: float = 0.8,
              look_lag_frames: float = 2.0, spine_twist: float = 0.2) -> dict:
    """Skeleton, IK, floor-pinned feet, joint meshes, breathing, look-at and secondary motion from a biped PSD.

    facing          auto | right | left (auto: the side the feet point to)
    meshes          weighted meshes across shoulders, hips, elbows, knees (False keeps regions)
    look_at         the look_target hook (eyes, head lagging look_lag_frames at 30 fps, spine_twist of the turn)
    breathing       add the 4 s ``breathe`` loop
    secondary_motion run :func:`secondary` on the hair / cloth / strap / pouch layers
    """
    sk = project.data
    parts = find_parts(sk)
    miss = missing_parts(parts)
    if miss:
        raise ValueError("rig_biped: missing required layers: " + ", ".join(miss) +
                         f". Found: {parts}. Name layers after BIPED_LAYERS (case-insensitive, sides _l/_r, "
                         "'Arm L', 'arm.l' or 'left_arm' all work); optional: pelvis, neck, hand_l/r, foot_l/r, "
                         "eye*, mouth, hair/cape/strap/pouch layers.")
    if sk.has_bone("hips") or sk.has_bone("ik_foot_l"):
        raise ValueError("rig_biped: this project already has a biped rig (bones hips / ik_foot_l exist)")
    if facing not in ("auto", "right", "left"):
        raise ValueError("facing is auto | right | left")
    if not 0 <= spine_twist <= 1:
        raise ValueError("spine_twist is a fraction of the head turn, 0..1")
    for p_, s_ in parts.items():
        if not isinstance(sk.attachment(s_), RegionAttachment):
            raise ValueError(f"{s_}: rig_biped starts from region attachments (run it on a fresh import_psd)")
    notes: list[str] = []
    split_arm = {s: f"arm_{s}" not in parts for s in "lr"}
    split_leg = {s: f"leg_{s}" not in parts for s in "lr"}

    # ---- measure the art
    tor = _limb(project, parts["torso"], 1)
    head_h = _alpha_hull(project, parts["head"])
    hx0, hy0 = head_h.min(0)
    hx1, hy1 = head_h.max(0)
    legs, arms = {}, {}
    for s in "lr":
        if split_leg[s]:
            th, sh = _limb(project, parts[f"thigh_{s}"], 1), _limb(project, parts[f"shin_{s}"], 1)
            legs[s] = dict(hip=th["top"], knee=(th["bottom"] + sh["top"]) / 2, ankle=sh["bottom"], hw=min(th["hw"], sh["hw"]))
        else:
            lg = _limb(project, parts[f"leg_{s}"], 2)
            legs[s] = dict(hip=lg["top"], knee=lg["mid"], ankle=lg["bottom"], hw=lg["hw"])
        if split_arm[s]:
            ua, la = _limb(project, parts[f"upper_arm_{s}"], 1), _limb(project, parts[f"lower_arm_{s}"], 1)
            arms[s] = dict(shoulder=ua["top"], elbow=(ua["bottom"] + la["top"]) / 2, wrist=la["bottom"],
                           hw=min(ua["hw"], la["hw"]))
        else:
            am = _limb(project, parts[f"arm_{s}"], 2)
            arms[s] = dict(shoulder=am["top"], elbow=am["mid"], wrist=am["bottom"], hw=am["hw"])
    feet = {}
    for s in "lr":
        if f"foot_{s}" in parts:
            feet[s] = _alpha_hull(project, parts[f"foot_{s}"])
    # facing: the feet point the way the character looks
    if facing == "auto":
        dx = [feet[s][:, 0].mean() - legs[s]["ankle"][0] for s in feet]
        f = 1 if (sum(dx) >= 0 if dx else True) else -1
    else:
        f = 1 if facing == "right" else -1
    floor = min(float(feet[s][:, 1].min()) for s in feet) if feet else \
        min(float(legs[s]["ankle"][1] - legs[s]["hw"]) for s in "lr")
    # joints: the art's bend, else knees forward / elbows back
    knee_def = -f        # knee forward on a leg pointing down: clockwise for f = +1 (bendPositive False)
    elbow_def = f
    bends = {}
    for s in "lr":
        k, bp, how = _place_joint(legs[s]["hip"], legs[s]["knee"], legs[s]["ankle"], knee_def)
        legs[s]["knee"], bends[f"leg_{s}"] = k, (bp, how)
        e, bp, how = _place_joint(arms[s]["shoulder"], arms[s]["elbow"], arms[s]["wrist"], elbow_def)
        arms[s]["elbow"], bends[f"arm_{s}"] = e, (bp, how)
    hipc = (legs["l"]["hip"] + legs["r"]["hip"]) / 2
    neck_base = tor["line"][0] + (tor["line"][-1] - tor["line"][0]) * 0.1
    hcx = (hx0 + hx1) / 2
    head_piv = np.array([hcx + 0.3 * (neck_base[0] - hcx), hy0 + 0.15 * (hy1 - hy0)])
    if "neck" in parts:
        nk = _limb(project, parts["neck"], 1)
        head_piv = nk["top"]
    head_top = np.array([hcx, hy1])

    # ---- bones
    _bone(sk, "ground", "root", (hipc[0], floor), color="00E1FFFF")
    spine_v = neck_base - hipc
    _bone(sk, "hips", "ground", hipc, hipc + spine_v * 0.16, color="FFB000FF")
    prev, a = "hips", hipc + spine_v * 0.16
    for i, nm in enumerate(SPINE_CHAIN):
        b = hipc + spine_v * (0.16 + 0.21 * (i + 1))
        _bone(sk, nm, prev, a, b)
        prev, a = nm, b
    _bone(sk, "neck", "chest", neck_base, head_piv)
    _bone(sk, "head", "neck", head_piv, head_top)
    _bone(sk, "arm_space", "chest", sk.world()["chest"].head, angle=0.0)
    for s in "lr":
        A = arms[s]
        sp = hipc + spine_v * float(np.clip((A["shoulder"] - hipc) @ spine_v / (spine_v @ spine_v), 0, 1))
        _bone(sk, f"shoulder_{s}", "chest", sp, A["shoulder"], angle=_angle(A["shoulder"], A["elbow"]))
        _bone(sk, f"upper_arm_{s}", f"shoulder_{s}", A["shoulder"], A["elbow"])
        _bone(sk, f"lower_arm_{s}", f"upper_arm_{s}", A["elbow"], A["wrist"])
        if f"hand_{s}" in parts:
            hh = _alpha_hull(project, parts[f"hand_{s}"])
            tip = hh[np.argmax(np.hypot(*(hh - A["wrist"]).T))]
        else:
            tip = A["wrist"] + (A["wrist"] - A["elbow"]) * 0.35
        _bone(sk, f"hand_{s}", f"lower_arm_{s}", A["wrist"], tip)
        _bone(sk, f"ik_hand_{s}", "arm_space", A["wrist"], angle=0.0, color="FF3F00FF")
        Lg = legs[s]
        _bone(sk, f"thigh_{s}", "hips", Lg["hip"], Lg["knee"])
        _bone(sk, f"shin_{s}", f"thigh_{s}", Lg["knee"], Lg["ankle"])
        _bone(sk, f"ik_foot_{s}", "ground", Lg["ankle"], angle=0.0, color="FF3F00FF")
        if s in feet:
            fh = feet[s]
            sole = fh[fh[:, 1] <= fh[:, 1].min() + 0.25 * np.ptp(fh[:, 1])]
            toe = sole[np.argmax(f * sole[:, 0])]
            ball = Lg["ankle"] + (np.array([toe[0], (toe[1] + Lg["ankle"][1]) / 2]) - Lg["ankle"]) * 0.8
        else:
            ball = Lg["ankle"] + np.array([f * 2.0 * Lg["hw"], -0.5 * Lg["hw"]])
        _bone(sk, f"foot_{s}", f"ik_foot_{s}", Lg["ankle"], ball)

    # ---- slots onto bones (art never moves), then meshes across the joints
    def put(key: str, bone: str):
        if key in parts:
            reparent_slot(sk, parts[key], bone)

    put("torso", "hips")
    put("pelvis", "hips")
    put("neck", "neck")
    put("head", "head")
    for s in "lr":
        put(f"arm_{s}", f"upper_arm_{s}")
        put(f"upper_arm_{s}", f"upper_arm_{s}")
        put(f"lower_arm_{s}", f"lower_arm_{s}")
        put(f"hand_{s}", f"hand_{s}")
        put(f"leg_{s}", f"thigh_{s}")
        put(f"thigh_{s}", f"thigh_{s}")
        put(f"shin_{s}", f"shin_{s}")
        put(f"foot_{s}", f"foot_{s}")
    body_slots = set(parts.values())
    head_poly = _hull(project, parts["head"])
    eyes, mouth, attached = [], None, {}
    for sl in list(sk.slots):
        if sl.name in body_slots or not sl.attachment:
            continue
        if not isinstance(_safe_att(sk, sl.name), RegionAttachment):
            continue
        if secondary_motion and strand_kind(sl.name) is not None:
            continue                                    # secondary() rigs these
        c = _hull(project, sl.name).mean(0)
        base, _ = split_side(_norm(sl.name))
        if points_in_polygon(c[None], head_poly)[0] or any(_tokens_match(base, e) for e in (*EYE_NAMES, *MOUTH_NAMES)):
            if any(_tokens_match(base, e) for e in EYE_NAMES):
                eyes.append(sl.name)
            elif mouth is None and any(_tokens_match(base, m_) for m_ in MOUTH_NAMES):
                mouth = sl.name
            else:
                reparent_slot(sk, sl.name, "head")
                attached[sl.name] = "head"
            continue
        bone = _nearest_body_bone(sk, c)
        reparent_slot(sk, sl.name, bone)
        attached[sl.name] = bone
    if eyes:
        _bone(sk, "eye_space", "head", sk.world()["head"].head, angle=0.0)
        for e in eyes:
            c = _hull(project, e).mean(0)
            bn = sk.unique_name(f"eye_{_norm(e)}")
            _bone(sk, bn, "eye_space", c, angle=0.0)
            reparent_slot(sk, e, bn)
            attached[e] = bn
    if mouth:
        c = _hull(project, mouth).mean(0)
        _bone(sk, "mouth", "head", c, angle=0.0)
        reparent_slot(sk, mouth, "mouth")
        attached[mouth] = "mouth"

    mesh_info = {}
    if meshes:
        def mesh(key, bones, **kw):
            if key in parts:
                r = rig_mesh(project, parts[key], bones=[b for b in bones if sk.has_bone(b)], detail=detail, **kw)
                mesh_info[parts[key]] = {"bones": r["bones"], "vertices": r.get("vertices")}
        mesh("torso", ["hips", *SPINE_CHAIN])
        mesh("neck", ["chest", "neck", "head"])
        for s in "lr":
            mesh(f"arm_{s}", [f"shoulder_{s}", f"upper_arm_{s}", f"lower_arm_{s}", f"hand_{s}"])
            mesh(f"upper_arm_{s}", [f"shoulder_{s}", f"upper_arm_{s}", f"lower_arm_{s}"])
            mesh(f"lower_arm_{s}", [f"upper_arm_{s}", f"lower_arm_{s}", f"hand_{s}"])
            mesh(f"leg_{s}", ["hips", f"thigh_{s}", f"shin_{s}", f"foot_{s}"])
            mesh(f"thigh_{s}", ["hips", f"thigh_{s}", f"shin_{s}"])
            mesh(f"shin_{s}", [f"thigh_{s}", f"shin_{s}", f"foot_{s}"])
            mesh(f"foot_{s}", [f"foot_{s}"], max_vertices=60)

    # ---- IK: legs to floor-pinned targets, arms to targets riding the chest
    ik = {}
    for s in "lr":
        ik[f"leg_{s}"] = add_ik(sk, [f"thigh_{s}", f"shin_{s}"], target=f"ik_foot_{s}", name=f"ik_leg_{s}",
                                bend_positive=bends[f"leg_{s}"][0])
        ik[f"arm_{s}"] = add_ik(sk, [f"upper_arm_{s}", f"lower_arm_{s}"], target=f"ik_hand_{s}", name=f"ik_arm_{s}",
                                bend_positive=bends[f"arm_{s}"][0])
    for k, (bp, how) in bends.items():
        if how == "default":
            notes.append(f"{k}: the art is straight; bend direction set to the default "
                         f"({'knee forward' if k.startswith('leg') else 'elbow back'})")
    look = _look_rig(project, f, look_lag_frames, spine_twist, eyes) if look_at else None
    made_clips = []
    if breathing:
        breathe_clip(project)
        made_clips.append("breathe")
    sec = secondary(project) if secondary_motion else None
    project.data.skeleton.height = project.data.skeleton.height or float(hy1 - floor)
    return {"parts": parts, "facing": "right" if f > 0 else "left", "floor": round(floor, 2),
            "bones": [b.name for b in sk.bones], "ik": {k: v["constraint"] for k, v in ik.items()},
            "bend": {k: ("positive" if bp else "negative", how) for k, (bp, how) in bends.items()},
            "meshes": mesh_info, "attached": attached, "eyes": eyes, "mouth": mouth, "look_at": look,
            "secondary": sec, "clips": made_clips, "notes": notes,
            "counts": {"bones": len(sk.bones), "slots": len(sk.slots), "ik": len(sk.ik),
                       "transform": len(sk.transform), "physics": len(sk.physics)}}


def _body_bones(sk: SkeletonData) -> list[str]:
    return [b.name for b in sk.bones if not b.name.startswith(HELPER_PREFIXES) and b.name != "root"]


def _nearest_body_bone(sk: SkeletonData, p, among: list[str] | None = None) -> str:
    w = sk.world()
    best, bd = "root", np.inf
    for b in among or _body_bones(sk):
        wb = w[b]
        d = float(seg_distance(np.asarray(p, float)[None], np.asarray(wb.head), np.asarray(wb.tail))[0][0])
        if d < bd:
            best, bd = b, d
    return best


# ---------------------------------------------------------------------------------------- look-at hook
def _look_rig(project: Project, f: int, lag_frames: float, spine_twist: float, eyes: list[str]) -> dict:
    """look_base → look_target (the control, local 0,0) → look_follow (physics: trails by lag_frames at 30 fps);
    look_aim_base (under hips, aimed at the setup target) → look_aim (1-bone IK at look_follow). The head copies the
    aim's local rotation (local+relative), the spine bones share spine_twist of it, the eyes copy look_target's offset."""
    sk = project.data
    w = sk.world()
    hw = w["head"]
    E = np.mean([setup_hull_world(project, e).mean(0) for e in eyes], 0) if eyes else \
        np.array(hw.to_world(hw.length * 0.45, 0))
    hsize = max(hw.length, 40.0)
    T = E + np.array([f * 2.5 * hsize, 0.0])
    _bone(sk, "look_base", "ground", T, angle=0.0)
    _bone(sk, "look_target", "look_base", T, angle=0.0, color="FFD400FF")
    _bone(sk, "look_follow", "look_target", T, angle=0.0)
    _bone(sk, "look_aim_base", "hips", E, angle=_angle(E, T))
    _bone(sk, "look_aim", "look_aim_base", E, T)
    # critically damped follower (velocity kept per 1/60 s = exp(-2 omega / 60)), omega calibrated on the runtime's
    # own 60 Hz solver so a target moving at constant speed is followed exactly ``lag`` seconds behind
    lag = max(lag_frames, 0.25) / 30.0
    om = follower_omega(lag)
    sk.physics.append(_physics("phys_look_follow", sk, "look_follow", x=1, y=1, rotate=0, inertia=1,
                               strength=round(om * om, 3), mass=1, damping=round(math.exp(-2 * om / 60), 6),
                               limit=100000))
    add_ik(sk, ["look_aim"], target="look_follow", name="ik_look")
    zero = dict(mix_x=0, mix_y=0, mix_scale_x=0, mix_scale_y=0, mix_shear_y=0, local=True, relative=True)
    spine = [b for b in SPINE_CHAIN if sk.has_bone(b)]
    per = spine_twist / max(len(spine), 1)
    for b in spine:
        add_transform(sk, [b], "look_aim", name=f"tc_look_{b}", mix_rotate=round(per, 4), **zero)
    head_mix = round(max(0.0, 0.8 - spine_twist), 4)
    add_transform(sk, ["head"], "look_aim", name="tc_look_head", mix_rotate=head_mix, **zero)
    eye_bones = [b.name for b in sk.bones if b.parent == "eye_space"]
    eye_mix = 0.035
    if eye_bones:
        add_transform(sk, eye_bones, "look_target", name="tc_look_eyes", mix_rotate=0, mix_x=eye_mix, mix_y=eye_mix,
                      mix_scale_x=0, mix_scale_y=0, mix_shear_y=0, local=True, relative=True)
    return {"control": "look_target", "follower": "look_follow", "aim": "look_aim", "lag_s": round(lag, 4),
            "omega": round(om, 3), "head_mix": head_mix, "spine_twist": spine_twist, "eye_mix": eye_mix if eye_bones else 0,
            "default_target": [round(float(v), 2) for v in T]}


def follower_lag(strength: float, damping: float, mass: float = 1.0, fps: float = 30.0, T: float = 2.0) -> float:
    """Steady lag (s) of a physics-translate follower (inertia 1) behind a parent moving at constant speed, using
    the spine-core 4.2 solver exactly (PhysicsConstraint.update: inertia applied per frame, 60 Hz substeps,
    v += -x k/m dt; x += v dt; v *= damping^(60 dt)), sampled at ``fps`` frames."""
    st, x, v, ux, rem = 1 / 60, 0.0, 0.0, 0.0, 0.0
    d = damping ** (60 * st)
    speed, bx = 100.0, 0.0
    for i in range(int(T * fps)):
        bx = speed * i / fps
        x += ux - bx
        ux = bx
        rem += 1 / fps
        while rem >= st - 1e-12:
            v += -x * strength / mass * st
            x += v * st
            v *= d
            rem -= st
    return -x / speed


def follower_omega(lag: float) -> float:
    """omega (rad/s) of the critically damped follower whose runtime lag is ``lag`` seconds (bisection)."""
    lo, hi = 1.0, 120.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if follower_lag(mid * mid, math.exp(-2 * mid / 60)) > lag:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _physics(name: str, sk: SkeletonData, bone: str, **p):
    from .ir import PhysicsConstraint
    from .rig import _next_order
    return PhysicsConstraint(name=sk.unique_name(name, "constraint"), order=_next_order(sk), bone=bone, **p)


# ======================================================================================== secondary motion
def _aspect(P: np.ndarray) -> tuple[float, np.ndarray, np.ndarray]:
    c = P.mean(0)
    _, s, vt = np.linalg.svd(P - c, full_matrices=False)
    return float(s[0] / max(s[1], 1e-9)), c, vt[0]


def secondary(project: Project, presets: dict[str, str] | None = None, by_shape: bool = True,
              exclude: list[str] | None = None, slots: list[str] | None = None, n_bones: int | None = None,
              detail: float = 0.8, min_aspect: float = 2.6) -> dict:
    """Find every strand-like layer and give it physics.

    By name (STRAND_NAMES → preset; PENDULUM_NAMES → a one-bone pendulum) and, with ``by_shape``, any other
    unrecognised layer whose alpha is elongated (principal axis ratio >= min_aspect, at least 10 % of the character's
    height, not a face feature or a prop in STRAND_EXCLUDE) becomes "cloth". The chain
    starts at the end that overlaps the body and hangs from the body bone nearest that end.

    presets  {slot: preset} overrides (hair, cloth, silk, leather, chain, feather, tail, ear, pouch)
    exclude  slot names to leave alone; slots: only these
    """
    sk = project.data
    presets = dict(presets or {})
    for s_, pr in presets.items():
        sk.slot(s_)
        if pr not in SECONDARY_PRESETS:
            raise ValueError(f"unknown secondary preset {pr!r} for {s_!r}; one of {sorted(SECONDARY_PRESETS)}")
    if n_bones is not None and not 1 <= int(n_bones) <= 12:
        raise ValueError("n_bones is 1..12")
    exclude = set(exclude or [])
    body = set(find_parts(sk).values())
    x0, y0, x1, y1 = setup_bounds(project)
    Hc = max(y1 - y0, 1.0)
    anchors = []
    for s in sk.slots:
        if s.name in body or (s.attachment and isinstance(_safe_att(sk, s.name), MeshAttachment)):
            try:
                anchors.append((s.name, setup_hull_world(project, s.name)))
            except (KeyError, ValueError, FileNotFoundError):
                pass
    made, skipped = {}, {}
    for s in list(sk.slots):
        nm = s.name
        if slots is not None and nm not in slots:
            continue
        if nm in exclude or nm in body or not s.attachment or s.blend != "normal":
            continue
        att = _safe_att(sk, nm)
        if not isinstance(att, RegionAttachment):
            if isinstance(att, MeshAttachment) and nm in presets:
                skipped[nm] = "already a mesh (rigged)"
            continue
        base, _ = split_side(_norm(nm))
        kind = presets.get(nm) or strand_kind(nm)
        try:
            P = _alpha_world(project, nm, 3000)
        except (ValueError, FileNotFoundError):
            continue
        asp, c, axis = _aspect(P)
        t = (P - c) @ axis
        length = float(np.ptp(t))
        if kind is None:
            if not by_shape or any(_tokens_match(base, e) for e in STRAND_EXCLUDE):
                continue
            if asp < min_aspect or length < 0.1 * Hc:
                continue
            kind = "cloth"
        elif kind != "pouch" and asp < 1.5 and nm not in presets:
            skipped[nm] = f"named like {kind} but not elongated (aspect {asp:.2f}); left rigid"
            continue
        spec = SECONDARY_PRESETS[kind]
        ends = [c + axis * t.min(), c + axis * t.max()]
        dist = [_dist_to_parts(e, anchors, exclude=nm) for e in ends]
        if abs(dist[0] - dist[1]) < 1e-6:
            root = ends[int(np.argmax([e[1] for e in ends]))]
        else:
            root = ends[int(np.argmin(dist))]
        tip = ends[1] if root is ends[0] else ends[0]
        parent = _anchor_bone(sk, project, root, anchors)
        if kind == "pouch" or (n_bones or spec["n_bones"]) == 1:
            made[nm] = _pendulum(project, nm, P, parent, spec, kind)
            continue
        if abs(tip[1] - root[1]) >= abs(tip[0] - root[0]):
            root_end = "top" if root[1] > tip[1] else "bottom"
        else:
            root_end = "left" if root[0] < tip[0] else "right"
        nb = int(n_bones or spec["n_bones"])
        if sk.slot(nm).bone != parent:
            reparent_slot(sk, nm, parent)
        res = rig_strand(project, nm, n_bones=nb, parent=parent, root_end=root_end, physics=None,
                         name=f"{_norm(nm)}_", detail=detail)
        phys = add_physics(sk, res["bones"], spec["base"], spec["taper"], **spec["over"])
        made[nm] = {"preset": kind, "bones": res["bones"], "physics": phys, "parent": parent, "root_end": root_end,
                    "aspect": round(asp, 2), "by": "name" if (presets.get(nm) or strand_kind(nm)) else "shape"}
    return {"strands": made, "skipped": skipped, "presets": {k: _preset_values(k) for k in
                                                              sorted({m["preset"] for m in made.values()})}}


def _preset_values(kind: str) -> dict:
    spec = SECONDARY_PRESETS[kind]
    p = dict(PHYSICS_PRESETS[spec["base"]])
    p.update(spec["over"])
    return p


def _safe_att(sk: SkeletonData, slot: str):
    try:
        return sk.attachment(slot)
    except KeyError:
        return None


def _dist_to_parts(p, anchors, exclude: str) -> float:
    best = np.inf
    for nm, poly in anchors:
        if nm == exclude:
            continue
        if points_in_polygon(np.asarray(p, float)[None], poly)[0]:
            return 0.0
        a, b = poly, np.roll(poly, -1, 0)
        for i in range(len(poly)):
            best = min(best, float(seg_distance(np.asarray(p, float)[None], a[i], b[i])[0][0]))
    return best


def _anchor_bone(sk: SkeletonData, project: Project, p, anchors) -> str:
    """The body bone a strand hangs from: the bones of the smallest body part containing its root (nearest
    segment among them), else the nearest body bone."""
    inside = [(nm, poly) for nm, poly in anchors if points_in_polygon(np.asarray(p, float)[None], poly)[0]]
    if inside:
        from .geometry import polygon_area
        nm = min(inside, key=lambda kv: abs(polygon_area(kv[1])))[0]
        att = sk.attachment(nm)
        bones = [sk.slot(nm).bone]
        if isinstance(att, MeshAttachment) and len(att.vertices) != len(att.uvs):
            from .weights import decode_weighted
            idx = {bi for v in decode_weighted(att.vertices, len(att.uvs) // 2) for bi, *_ in v}
            bones = [sk.bones[i].name for i in sorted(idx)]
        bones = [b for b in bones if b != "root"] or bones
        return _nearest_body_bone(sk, p, bones)
    body = _body_bones(sk)
    return _nearest_body_bone(sk, p, body) if body else "root"


def _pendulum(project: Project, slot: str, P: np.ndarray, parent: str, spec: dict, kind: str) -> dict:
    """A rigid hanging prop: one bone from its attach point (top centre) through its centroid, rotate physics."""
    sk = project.data
    c = P.mean(0)
    top = np.array([c[0], P[:, 1].max()])
    bn = sk.unique_name(f"{_norm(slot)}_swing")
    _bone(sk, bn, parent, top, top + (c - top) * 2.0)
    reparent_slot(sk, slot, bn)
    phys = add_physics(sk, [bn], spec["base"], spec["taper"], **spec["over"])
    return {"preset": kind, "bones": [bn], "physics": phys, "parent": parent, "root_end": "top", "by": "name"}


# ======================================================================================== springs and squash
def exact_spring(first: float, second: float, hz: float):
    """Underdamped spring caught at rest with speed v: x(t) = -(v/wd) e^(-zeta w t) sin(wd t). zeta is solved from the
    ratio of the two extremes and v from the first, so the first extreme is exactly -first and the next exactly
    +second (land: 0.15 and 0.05 → scale 0.85 then 1.05). Returns (x(t), info)."""
    if not (first > 0 and 0 < second < first):
        raise ValueError("exact_spring needs first > second > 0 (each swing smaller than the last)")
    if hz <= 0:
        raise ValueError("hz must be > 0")
    lr = math.log(first / second)
    zeta = lr / math.sqrt(math.pi ** 2 + lr * lr)
    w0 = 2 * math.pi * hz
    wd = w0 * math.sqrt(1 - zeta * zeta)
    tp = math.atan2(wd, zeta * w0) / wd
    peak = math.exp(-zeta * w0 * tp) * math.sin(wd * tp) / wd
    v = first / peak

    def x(t):
        return -v * math.exp(-zeta * w0 * t) * math.sin(wd * t) / wd if t > 0 else 0.0
    return x, {"zeta": zeta, "t_first": tp, "t_second": tp + math.pi / wd, "period": 2 * math.pi / wd}


def smoothstep(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def window_end(t: float, a: float, b: float) -> float:
    """1 before a, 0 after b, smooth between: makes a motion end exactly at rest."""
    return 1.0 - smoothstep((t - a) / max(b - a, 1e-9))


def volume_scale(sy: float, volume: str = "3d") -> tuple[float, float]:
    """(across, along) scale for an along-axis scale sy: 3d keeps a cylinder's volume (across = sy^-1/2), area keeps
    a flat shape's area (across = 1/sy)."""
    sy = max(sy, 0.05)
    return (sy ** -0.5 if volume == "3d" else 1.0 / sy), sy


def ensure_carrier(sk: SkeletonData, chain: list[str], name: str | None = None) -> str:
    """A carrier bone between chain[0] and its parent, at chain[0]'s head and aligned with the chain (head of the
    first bone → tail of the last), so its scaleX squashes ALONG the chain and scaleY across it. Made once and reused.
    Weighted vertices are remapped (reorder_bones)."""
    for b in chain:
        sk.bone(b)
    first = sk.bone(chain[0])
    if first.parent is None:
        raise ValueError(f"{chain[0]!r} is the root; squash a chain below it")
    nm = name or f"ss_{chain[0]}"
    if first.parent == nm:
        return nm
    if sk.has_bone(nm):
        raise ValueError(f"bone {nm!r} exists but is not {chain[0]!r}'s parent")
    w = sk.world()
    h = np.asarray(w[chain[0]].head)
    t = np.asarray(w[chain[-1]].tail)
    ang = _angle(h, t) if np.hypot(*(t - h)) > 1e-6 else w[chain[0]].rotation
    sk.add_bone_world(nm, first.parent, float(h[0]), float(h[1]), ang, 0, color="FF7AF5FF")
    nw = sk.world()[nm]
    kids = [first.name]
    for k in kids:
        kb, kw = sk.bone(k), w[k]
        lx, ly = nw.to_local(kw.x, kw.y)
        kb.parent = nm
        kb.x, kb.y = round(lx, 3), round(ly, 3)
        if kb.inherit == "normal":
            kb.rotation = round(_wrap(kw.rotation - nw.rotation), 3)
    sk.reorder_bones(_depth_order(sk))
    return nm


def squash_stretch(project: Project, chain: list[str], clip: str, start: float = 0.0, squash: float = 0.85,
                   overshoot: float = 1.05, hz: float = 2.6, duration: float | None = None, volume: str = "3d",
                   intensity: float = 1.0, event: str | None = None) -> dict:
    """Volume-preserving squash & stretch of a bone chain on an exact spring, keyed into ``clip`` from ``start``.

    The first extreme of the along-chain scale is exactly ``squash`` (< 1 squashes first, > 1 stretches first), the
    next exactly ``overshoot`` on the other side of 1; then it settles and ends exactly at 1 (``duration`` default:
    the time of the second extreme + 2 periods). Keys go on a carrier bone (``ss_<chain[0]>``) aligned with the chain,
    multiplied into any keys an earlier call left there, so the artist's bones and keys are untouched.
    volume: "3d" (across = along^-1/2) or "area" (across = 1/along)."""
    sk = project.data
    if volume not in ("3d", "area"):
        raise ValueError("volume is 3d | area")
    a1, a2 = (squash - 1) * intensity, (overshoot - 1) * intensity
    if a1 == 0 or a1 * a2 >= 0 or abs(a2) >= abs(a1):
        raise ValueError("squash and overshoot must sit on opposite sides of 1 with |overshoot - 1| < |squash - 1| "
                         f"(got squash={squash}, overshoot={overshoot})")
    if 1 + a1 <= 0.1:
        raise ValueError("squash would collapse the chain (scale <= 0.1)")
    if not chain:
        raise ValueError("give a chain of bones")
    x, info = exact_spring(abs(a1), abs(a2), hz)
    sgn = 1.0 if a1 < 0 else -1.0                        # x dips negative first
    D = duration or (info["t_second"] + 2 * info["period"])
    if D <= info["t_second"]:
        raise ValueError(f"duration {D} ends before the overshoot at {info['t_second']:.3f} s")
    w0 = info["t_second"] + 0.25 * (D - info["t_second"])

    def along(u: float) -> float:
        return 1.0 + sgn * x(u) * window_end(u, w0, D)
    carrier = ensure_carrier(sk, list(chain))
    ab = AnimBuilder(sk, clip, replace=False)
    ts = list(np.linspace(0, D, max(8, int(math.ceil(D * 60)) + 1)))
    ts = sorted(set(ts + [info["t_first"], info["t_second"]]))
    pts = [(start + u, *volume_scale(along(u), volume)) for u in ts]
    pts[-1] = (start + D, 1.0, 1.0)
    # along-chain = carrier local x; Spine scale keys are (x, y) = (along, across)
    pts = [(t, a, c) for (t, c, a) in pts]
    _merge_scale(ab, carrier, pts)
    if event:
        ab.event(start, event)
    return {"carrier": carrier, "clip": clip, "start": start, "duration": round(D, 4), "zeta": round(info["zeta"], 5),
            "t_first": round(start + info["t_first"], 4), "t_second": round(start + info["t_second"], 4),
            "extremes": [round(1 + a1, 4), round(1 + a2, 4)], "volume": volume}


def _merge_scale(ab: AnimBuilder, bone: str, pts: list[tuple[float, float, float]]) -> None:
    old = ab.a.bones.get(bone, {}).get("scale")
    if old:
        def val(k, f):
            v = (k.model_extra or {}).get(f)
            return 1.0 if v is None else float(v)
        ot = np.array([k.time for k in old])
        ox, oy = np.array([val(k, "x") for k in old]), np.array([val(k, "y") for k in old])
        nt = np.array([p[0] for p in pts])
        nx, ny = np.array([p[1] for p in pts]), np.array([p[2] for p in pts])
        times = sorted(set(np.round(np.concatenate([ot, nt]), 4).tolist()))
        merged = []
        for t in times:
            a_ = (np.interp(t, ot, ox), np.interp(t, ot, oy))
            inside = nt[0] - 1e-9 <= t <= nt[-1] + 1e-9
            b_ = (np.interp(t, nt, nx), np.interp(t, nt, ny)) if inside else (1.0, 1.0)
            merged.append((t, a_[0] * b_[0], a_[1] * b_[1]))
        pts = merged
    ab.bone(bone, "scale", _uniq(pts), "linear")


def _uniq(pts):
    out, last = [], None
    for p in pts:
        t = round(p[0], 4)
        if last is not None and abs(t - last) < 1e-4:
            out[-1] = (t, *p[1:])
            continue
        out.append((t, *p[1:]))
        last = t
    return out


# ======================================================================================== the character contract
CHARACTER_CLIPS: dict[str, dict] = {
    "idle":        dict(loop=True, length=4.0, events=[], needs=["chest"],
                        summary="one real breath (4 s): chest +2 %, shoulders up 1 %, head counter-nod, weight sway"),
    "idle_fidget": dict(loop=False, length=3.0, events=["sfx_idle_fidget"], needs=["head"],
                        summary="glance back and up with the look-at hook, weight shift, shrug"),
    "walk":        dict(loop=True, length=1.0, events=["sfx_step", "sfx_step"],
                        needs=["hips", "thigh_l", "shin_l", "thigh_r", "shin_r", "ik_foot_l", "ik_foot_r"],
                        summary="in-place treadmill, inverted pendulum, heel → flat → toe, arms counter-swing"),
    "run":         dict(loop=True, length=0.6, events=["sfx_step", "sfx_step"],
                        needs=["hips", "thigh_l", "shin_l", "thigh_r", "shin_r", "ik_foot_l", "ik_foot_r"],
                        summary="spring-mass stance, gravity-parabola flight, lean, pumping bent arms"),
    "jump":        dict(loop=False, length=1.2, events=["sfx_jump", "sfx_step"], needs=["hips"],
                        summary="crouch, launch stretch, ballistic hop, tuck, touch-down absorb"),
    "land":        dict(loop=False, length=0.8, events=["sfx_land"], needs=["hips"],
                        summary="impact on an exact spring: squash 0.85, overshoot 1.05, settle (volume kept)"),
    "hit":         dict(loop=False, length=0.7, events=["sfx_hit"], needs=["chest"],
                        summary="2-frame anticipation against the blow, spring recoil lagging up the chain, red flash"),
    "attack":      dict(loop=False, length=0.9, events=["sfx_attack", "attack_hit"], needs=["ik_hand_r|ik_hand_l"],
                        summary="wind-up opposite the strike, fast strike, spring follow-through, recover"),
    "win":         dict(loop=False, length=1.6, events=["sfx_win", "sfx_step"], needs=["hips"],
                        summary="crouch, hop with both arms up, pump, settle"),
    "lose":        dict(loop=False, length=2.2, events=["sfx_lose"], needs=["chest", "head"],
                        summary="slump and sigh, head down, arms hang, recover"),
    "talk":        dict(loop=True, length=1.6, events=["sfx_talk"], needs=["head"],
                        summary="syllable nods (5 per loop), mouth open/close, one gesturing hand"),
}


class _Body:
    """Setup-pose measurements the clips are built from (canonical names through bone_map)."""

    def __init__(self, project: Project, bmap: dict | None, facing: str):
        self.p = project
        self.sk = project.data
        self.m = bmap or {}
        self.w = self.sk.world()
        x0, y0, x1, y1 = setup_bounds(project)
        self.bounds = (x0, y0, x1, y1)
        self.H = max(y1 - y0, 1.0)
        self.floor = y0
        if facing == "auto":
            self.f = _facing(self.sk, self.m)
        elif facing in ("right", "left"):
            self.f = 1 if facing == "right" else -1
        else:
            raise ValueError("facing is auto | right | left")
        self.Lleg = self._len("thigh_l") + self._len("shin_l") or 0.3 * self.H
        self.Larm = self._len("upper_arm_r") + self._len("lower_arm_r") or self._len("upper_arm_l") + \
            self._len("lower_arm_l") or 0.25 * self.H
        self.feet = {}
        for s in "lr":
            if self.has(f"ik_foot_{s}"):
                self.feet[s] = self._foot(s)

    def n(self, name: str) -> str:
        return self.m.get(name, name)

    def has(self, name: str) -> bool:
        return self.sk.has_bone(self.n(name))

    def _len(self, name: str) -> float:
        return self.w[self.n(name)].length if self.has(name) else 0.0

    def pos(self, name: str) -> np.ndarray:
        return np.array(self.w[self.n(name)].head, float)

    def _foot(self, s: str) -> dict:
        A = self.pos(f"ik_foot_{s}")
        hull = None
        for sl in self.sk.slots:
            if sl.bone == self.n(f"foot_{s}") and sl.attachment:
                try:
                    hull = setup_hull_world(self.p, sl.name)
                    break
                except (KeyError, ValueError, FileNotFoundError):
                    pass
        if hull is None:
            hull = np.array([[A[0] - 0.08 * self.H, self.floor], [A[0] + 0.12 * self.H, self.floor],
                             [A[0] + 0.1 * self.H, A[1]], [A[0] - 0.06 * self.H, A[1]]])
        floor = float(hull[:, 1].min())
        sole = hull[hull[:, 1] <= floor + 1.5]
        f = self.f
        heel = sole[np.argmin(f * sole[:, 0])]
        toe = sole[np.argmax(f * sole[:, 0])]
        return dict(A=A, hull=hull - A, floor=floor, ha=float(A[1] - floor), lh=float(f * (A[0] - heel[0])),
                    lt=float(f * (toe[0] - A[0])))

    def hipj(self, s: str) -> np.ndarray:
        return self.pos(f"thigh_{s}") if self.has(f"thigh_{s}") else self.pos("hips")

    def leg_len(self, s: str) -> float:
        return self._len(f"thigh_{s}") + self._len(f"shin_{s}")


class _Motion:
    """Accumulates closed-form motion per bone and timeline, then writes dense linear keys once.

    rot(bone, fn)    degrees added to the setup rotation
    move(bone, fn)   WORLD (x, y) offset at setup orientation, converted into the parent's frame
    scale(bone, fn)  (sx, sy) multiplied"""

    def __init__(self, B: _Body, D: float, loop: bool, fps: float = 30):
        self.B, self.D, self.loop, self.fps = B, D, loop, fps
        self.r: dict[str, list] = {}
        self.t: dict[str, list] = {}
        self.s: dict[str, list] = {}
        self.marks: set[float] = {0.0, D}

    def rot(self, bone, fn):
        if self.B.has(bone):
            self.r.setdefault(self.B.n(bone), []).append(fn)

    def move(self, bone, fn):
        if self.B.has(bone):
            self.t.setdefault(self.B.n(bone), []).append(fn)

    def scale(self, bone, fn):
        if self.B.has(bone):
            self.s.setdefault(self.B.n(bone), []).append(fn)

    def mark(self, *ts):
        for t in ts:
            if 0 <= t <= self.D:
                self.marks.add(round(float(t), 4))

    def move_at(self, bone, t) -> np.ndarray:
        return sum((np.asarray(fn(t), float) for fn in self.t.get(self.B.n(bone), [])), np.zeros(2))

    def times(self) -> list[float]:
        n = max(2, int(math.ceil(self.D * self.fps)) + 1)
        ts = set(np.round(np.linspace(0, self.D, n), 4).tolist()) | self.marks
        return sorted(ts)

    def write(self, ab: AnimBuilder) -> None:
        ts = self.times()
        sk = self.B.sk
        w = self.B.w
        for bone, fns in self.r.items():
            v = [sum(f(t) for f in fns) for t in ts]
            v[-1] = v[0] if self.loop else 0.0
            ab.bone(bone, "rotate", list(zip(ts, v)), "linear")
        for bone, fns in self.t.items():
            par = sk.bone(bone).parent
            pw = w[par]
            det = pw.a * pw.d - pw.b * pw.c
            pts = []
            for t in ts:
                dx, dy = sum((np.asarray(f(t), float) for f in fns), np.zeros(2))
                pts.append((t, (pw.d * dx - pw.b * dy) / det, (pw.a * dy - pw.c * dx) / det))
            pts[-1] = (ts[-1], *pts[0][1:]) if self.loop else (ts[-1], 0.0, 0.0)
            ab.bone(bone, "translate", pts, "linear")
        for bone, fns in self.s.items():
            pts = []
            for t in ts:
                sx, sy = 1.0, 1.0
                for f in fns:
                    a, b = f(t)
                    sx, sy = sx * a, sy * b
                pts.append((t, sx, sy))
            pts[-1] = (ts[-1], *pts[0][1:]) if self.loop else (ts[-1], 1.0, 1.0)
            ab.bone(bone, "scale", pts, "linear")


def _missing(B: _Body, needs: list[str]) -> list[str]:
    out = []
    for n in needs:
        alts = n.split("|")
        if not any(B.has(a) for a in alts):
            out.append(n)
    return out


def clip_set(project: Project, clips: list[str] | str = "all", intensity: float = 1.0,
             bone_map: dict[str, str] | None = None, facing: str = "auto", durations: dict[str, float] | None = None,
             wind: bool = True, names: dict[str, str] | None = None, blow_from: str = "front",
             attack_hand: str = "auto") -> dict:
    """Generate the character contract (CHARACTER_CLIPS) on any rig that has the bones each clip needs.

    clips      "all" or a list of contract names
    intensity  0.5 subtle … 1 standard … 1.6 cartoon; scales every amplitude
    bone_map   {canonical: actual} for rigs not made by rig_biped (e.g. {"hips": "hip", "ik_hand_r": "arm_r2_ik"})
    durations  {clip: seconds} overrides (loops stay closed, events move with the clip)
    wind       walk/run blow the strands back with a headwind ~ v^2; every other clip keys the wind back to 0
    names      {clip: animation name} to write a clip under another name (rig_biped's ``breathe`` is idle)
    blow_from  hit: "front" or "back"
    attack_hand auto (the near hand: the arm drawn in front) | l | r
    """
    names = names or {}
    want = list(CHARACTER_CLIPS) if clips == "all" else ([clips] if isinstance(clips, str) else list(clips))
    bad = [c for c in want if c not in CHARACTER_CLIPS]
    if bad:
        raise ValueError(f"unknown clips {bad}; the contract is {list(CHARACTER_CLIPS)}")
    if not 0 < intensity <= 3:
        raise ValueError("intensity is in (0, 3]")
    if blow_from not in ("front", "back"):
        raise ValueError("blow_from is front | back")
    if attack_hand not in ("auto", "l", "r"):
        raise ValueError("attack_hand is auto | l | r")
    for k, v in (durations or {}).items():
        if k not in CHARACTER_CLIPS or not 0.1 <= float(v) <= 30:
            raise ValueError(f"durations: {k}={v} (clip must be in the contract, 0.1..30 s)")
    bone_map = dict(bone_map or {})
    for k, v in bone_map.items():
        project.data.bone(v)
    B = _Body(project, bone_map, facing)
    made, skipped = {}, {}
    for c in want:
        spec = CHARACTER_CLIPS[c]
        miss = _missing(B, spec["needs"])
        if miss:
            skipped[c] = miss
            continue
        if c in ("jump", "win", "land") and not B.has("ground"):
            from .rig import insert_parent
            kids = [b.name for b in B.sk.children("root")]
            x0, y0, x1, y1 = B.bounds
            insert_parent(B.sk, "ground", "root", kids, (x0 + x1) / 2, y0)
            B = _Body(project, bone_map, facing)
        D = float((durations or {}).get(c, spec["length"]))
        m = _Motion(B, D, spec["loop"])
        ab = AnimBuilder(B.sk, names.get(c, c))
        info = GEN[c](m, ab, B, D, intensity, blow_from=blow_from, attack_hand=attack_hand) or {}
        _reach_guard(m, B)
        m.write(ab)
        _wind_keys(ab, B, D, info.get("wind", 0.0) if wind else 0.0, spec["loop"])
        made[names.get(c, c)] = {"loop": spec["loop"], "duration": D, **{k: v for k, v in info.items() if k != "wind"},
                                 "events": [(e.name, e.time) for e in ab.a.events]}
    return {"clips": made, "skipped": skipped, "facing": "right" if B.f > 0 else "left",
            "contract": list(CHARACTER_CLIPS)}


# ---------------------------------------------------------------------------------------- shared motion pieces
def breath(t: float, period: float = 4.0) -> float:
    """0 → 1 → 0 over one breath: quick inhale (40 %), long exhale, zero velocity at the turns (C1, loops)."""
    u = (t / period) % 1.0
    if u < 0.4:
        return 0.5 - 0.5 * math.cos(math.pi * u / 0.4)
    return 0.5 + 0.5 * math.cos(math.pi * (u - 0.4) / 0.6)


def _breathe(m: _Motion, B: _Body, I: float, period: float, amp: float = 1.0, env=None):
    env = env or (lambda t: 1.0)
    a = 0.02 * I * amp

    def chest(t):
        k = 1 + a * breath(t, period) * env(t)
        return (k, k)

    def counter(t):
        k = 1 + a * breath(t, period) * env(t)
        return (1 / k, 1 / k)
    m.scale("chest", chest)
    for b in ("neck", "shoulder_l", "shoulder_r"):
        m.scale(b, counter)
    rise = 0.01 * B.H * I * amp
    for s in "lr":
        m.move(f"shoulder_{s}", lambda t: (0.0, rise * breath(t - 0.12, period) * env(t)))
    m.rot("head", lambda t: -B.f * 0.9 * I * amp * breath(t - 0.25, period) * env(t))


def _arc(B: _Body, s: str, alpha_deg: float, shrink: float = 0.0, lift=(0.0, 0.0)) -> np.ndarray:
    """World offset of the hand IK target when the arm swings alpha (degrees, + = forward) about the shoulder,
    with the shoulder→wrist reach shortened by ``shrink`` (bends the elbow) and an extra lift."""
    S = B.pos(f"upper_arm_{s}") if B.has(f"upper_arm_{s}") else B.pos("chest")
    W0 = B.pos(f"ik_hand_{s}")
    v = (W0 - S) * (1 - shrink)
    a = math.radians(B.f * alpha_deg)
    c, sn = math.cos(a), math.sin(a)
    P = S + np.array([c * v[0] - sn * v[1], sn * v[0] + c * v[1]]) + np.asarray(lift, float)
    return P - W0


def _near_side(B: _Body) -> str:
    """The arm drawn in front (later in the draw order) is the near one."""
    idx = {}
    for i, sl in enumerate(B.sk.slots):
        for s in "lr":
            if sl.bone in (B.n(f"upper_arm_{s}"), B.n(f"lower_arm_{s}"), B.n(f"hand_{s}")):
                idx[s] = max(idx.get(s, -1), i)
    if len(idx) == 2:
        return "l" if idx["l"] > idx["r"] else "r"
    return "r" if B.has("ik_hand_r") else "l"


def _lean(m: _Motion, fn, weights=(0.4, 0.3, 0.2, 0.1), lag: float = 0.0):
    """Distribute a lean (degrees, + = counter-clockwise) over the spine, each level lagging ``lag`` s more."""
    for i, (b, k) in enumerate(zip(SPINE_CHAIN, weights)):
        m.rot(b, lambda t, k=k, i=i: k * fn(t - lag * i))


def _flat(*_):
    return 0.0


# ---------------------------------------------------------------------------------------- gait (walk / run)
def _foot_pose(Bf: dict, f: int, u: float, step: float, beta: float, psi: float, phi: float, lift: float,
               bh: float, bt: float):
    """Ankle offset (world, from setup) and foot angle at local cycle phase u (0 = heel strike).
    Stance [0, beta): heel rocker → flat → toe rocker; every rocker pivot rides the treadmill at -v, so nothing that
    touches the floor slides. Swing [beta, 1): C1 Hermite in x (end speeds = the ground speed), lift arc in y."""
    A0, ha, lh, lt = Bf["A"], Bf["ha"], Bf["lh"], Bf["lt"]
    floor = A0[1] - ha

    def g(uu):
        return f * (step * beta - 2 * step * uu)

    def rotp(pivot, ang, off):
        c, s = math.cos(ang), math.sin(ang)
        return np.array([pivot[0] + c * off[0] - s * off[1], pivot[1] + s * off[0] + c * off[1]])

    def stance(uu):
        if uu < bh:
            th = f * math.radians(psi) * (1 - smoothstep(uu / bh))
            heel = (A0[0] - f * lh + g(uu), floor)
            return rotp(heel, th, (f * lh, ha)), th
        if uu < beta - bt:
            return np.array([A0[0] + g(uu), A0[1]]), 0.0
        th = -f * math.radians(phi) * smoothstep((uu - (beta - bt)) / bt)
        toe = (A0[0] + f * lt + g(uu), floor)
        return rotp(toe, th, (-f * lt, ha)), th

    u = u % 1.0
    if u < beta:
        P, th = stance(u)
    else:
        w = (u - beta) / (1 - beta)
        Ps, ths = stance(beta - 1e-9)
        Pe, the = stance(0.0)
        m0 = -2 * step * f * (1 - beta)
        h00, h10 = 2 * w ** 3 - 3 * w ** 2 + 1, w ** 3 - 2 * w ** 2 + w
        h01, h11 = -2 * w ** 3 + 3 * w ** 2, w ** 3 - w ** 2
        x = h00 * Ps[0] + h10 * m0 + h01 * Pe[0] + h11 * m0
        y = Ps[1] + (Pe[1] - Ps[1]) * smoothstep(w) + lift * 16 * w * w * (1 - w) ** 2
        th = ths + (the - ths) * smoothstep(w)
        P = np.array([x, y])
    return P - A0, math.degrees(th)


def _foot_min_y(Bf: dict, off, ang_deg) -> float:
    a = math.radians(ang_deg)
    c, s = math.cos(a), math.sin(a)
    h = Bf["hull"]
    return float((Bf["A"][1] + off[1] + s * h[:, 0] + c * h[:, 1]).min())


def _gait(m: _Motion, ab: AnimBuilder, B: _Body, D: float, I: float, run: bool) -> dict:
    f = B.f
    L = B.Lleg
    step = (0.78 if run else 0.42) * L * min(I, 1.4) ** 0.5
    beta = 0.32 if run else 0.6
    psi, phi = (6.0, 30.0) if run else (14.0, 22.0)
    lift = (0.24 if run else 0.13) * L
    bh, bt = 0.12 * beta, (0.35 if run else 0.3) * beta
    v = 2 * step / D
    phase = {"r": 0.0, "l": 0.5}
    # toe clearance: raise the swing until no part of the foot dips under the floor
    for s, Bf in B.feet.items():
        for _ in range(12):
            worst = min(_foot_min_y(Bf, *_foot_pose(Bf, f, u, step, beta, psi, phi, lift, bh, bt)) - Bf["floor"]
                        for u in np.linspace(beta, 1, 60))
            if worst >= -0.25:
                break
            lift += -worst + 0.5
    for s, Bf in B.feet.items():
        def pose(t, s=s, Bf=Bf):
            return _foot_pose(Bf, f, t / D + phase[s], step, beta, psi, phi, lift, bh, bt)
        m.move(f"ik_foot_{s}", lambda t, pose=pose: pose(t)[0])
        m.rot(f"ik_foot_{s}", lambda t, pose=pose: pose(t)[1])
    # hips: walk = inverted pendulum (high at passing), run = spring-mass stance + ballistic flight
    if run:
        h = 0.018 * B.H * I
        Ts, Tf = beta * D, (0.5 - beta) * D
        g = 8 * h / Tf ** 2
        v0 = 4 * h / Tf
        c = v0 * Ts / math.pi

        def hy(t):
            tt = (t % (D / 2))
            if tt < Ts:
                return -c * math.sin(math.pi * tt / Ts)
            tau = tt - Ts
            return v0 * tau - g * tau * tau / 2
        info = {"flight_apex": round(h, 2), "gravity": round(g, 1), "compression": round(c, 2)}
    else:
        # inverted pendulum: the hip rides an arc of radius k*L over the planted foot (highest at the passing pose,
        # lowest in double support), the dip exaggerated x(1 + I), plus a short absorb after each contact
        kL = 0.955
        tt = np.linspace(0, D, 241)
        arc = np.zeros(len(tt))
        for i, t in enumerate(tt):
            hs = []
            for s, Bf in B.feet.items():
                uu = (t / D + phase[s]) % 1.0
                if uu < beta:
                    off, _ = _foot_pose(Bf, f, uu, step, beta, psi, phi, lift, bh, bt)
                    A = Bf["A"] + off
                    J0 = B.hipj(s)
                    R = kL * B.leg_len(s)
                    dx = J0[0] - A[0]
                    hs.append(A[1] + math.sqrt(max(R * R - dx * dx, 0.0)) - J0[1])
            arc[i] = min(hs) if hs else 0.0
        ker = np.hanning(15)[1:-1]
        ker /= ker.sum()
        sm = np.convolve(np.r_[arc[-8:-1], arc, arc[1:8]], ker, mode="same")[7:-7]
        top = sm.max()
        sm = top + (sm - top) * (1 + I)
        sm[-1] = sm[0]
        absorb = 0.012 * B.H * I

        def hy(t, sm=sm, tt=tt):
            p = (2 * t / D) % 1.0
            return float(np.interp(t, tt, sm)) - absorb * math.exp(-((p - 0.12) / 0.08) ** 2)
        info = {"bob": round(float(top - sm.min() + absorb), 2)}
    # sit low enough that no leg locks: one constant shift keeps the loop and its shape
    ts = np.linspace(0, D, 121)
    shift = 0.0
    for s in B.feet:
        J0 = B.hipj(s)
        R = 0.975 * B.leg_len(s)
        for t in ts:
            off, _ = _foot_pose(B.feet[s], f, t / D + phase[s], step, beta, psi, phi, lift, bh, bt)
            A = B.feet[s]["A"] + off
            dx = J0[0] - A[0]
            if R * R <= dx * dx:
                raise ValueError(f"stride too long for leg {s}: lower intensity")
            ymax = A[1] + math.sqrt(R * R - dx * dx) - J0[1]
            shift = min(shift, ymax - hy(t))
    m.move("hips", lambda t: (0.0, hy(t) + shift))
    lean = (10.0 if run else 3.0) * I
    _lean(m, lambda t: -f * lean + f * (1.2 if run else 0.8) * I * math.sin(4 * math.pi * t / D - 0.6), lag=0.03)
    m.rot("head", lambda t: f * 0.6 * lean - f * 0.5 * I * math.sin(4 * math.pi * t / D - 1.2))
    amp = (38.0 if run else 22.0) * I
    shrink = 0.22 if run else 0.05
    for s, ph in (("r", 0.0), ("l", math.pi)):
        if B.has(f"ik_hand_{s}"):
            def hand(t, s=s, ph=ph):
                al = -amp * math.cos(2 * math.pi * t / D + ph - 0.25)
                return _arc(B, s, al + (12 if run else 0), shrink + (0.05 if run else 0.03) * (al / max(amp, 1e-9) + 1))
            m.move(f"ik_hand_{s}", hand)
    for s, t0 in (("r", 0.0), ("l", D / 2)):
        if s in B.feet:
            ab.event(t0, "sfx_step", string=B.n(f"foot_{s}"), float=round(v, 2))
            m.mark(t0)
    m.mark(*(D * (k / 2 + q) for k in (0, 1) for q in (beta - bt, bh, beta)))
    wind_w = -f * WIND_K * (v / 300.0) ** 2           # aerodynamic drag ~ v^2, blowing back
    return {"ground_speed": round(v, 2), "stride": round(2 * step, 2), "stance": beta, "hips_lowered": round(-shift, 2),
            "swing_lift": round(lift, 2), "wind": wind_w, **info}


def gen_walk(m, ab, B, D, I, **_):
    return _gait(m, ab, B, D, I, run=False)


def gen_run(m, ab, B, D, I, **_):
    return _gait(m, ab, B, D, I, run=True)


# ---------------------------------------------------------------------------------------- idle family
def gen_idle(m, ab, B, D, I, **_):
    period = D
    _breathe(m, B, I, period)
    sway = 0.005 * B.H * I
    m.move("hips", lambda t: (sway * math.sin(2 * math.pi * t / D), 0.0))
    _lean(m, lambda t: -B.f * 0.6 * I * math.sin(2 * math.pi * t / D - 0.5))
    for s in "lr":
        m.move(f"ik_hand_{s}", lambda t, s=s: _arc(B, s, 2.5 * I * math.sin(2 * math.pi * (t - 0.35) / D)))
    return {"breath_period": period, "chest_scale": round(1 + 0.02 * I, 4)}


def gen_fidget(m, ab, B, D, I, **_):
    f = B.f
    _breathe(m, B, I, 4.0, env=lambda t: window_end(t, D - 0.6, D))

    def env(t, a, b, c_, d_):
        return smoothstep((t - a) / (b - a)) * (1 - smoothstep((t - c_) / (d_ - c_)))
    if B.has("look_target"):
        E = B.pos("look_aim_base")
        T0 = B.pos("look_target")
        dist = float(np.hypot(*(T0 - E)))

        def glance(t):
            a = math.radians(30 * I) * env(t, 0.35, 0.8, 1.15, 1.55) - math.radians(18 * I) * env(t, 1.55, 1.9, 2.2, 2.7)
            return (f * dist * (math.cos(a) - 1), dist * math.sin(a))
        m.move("look_target", glance)
    else:
        m.rot("head", lambda t: f * 14 * I * env(t, 0.35, 0.8, 1.15, 1.55) - f * 8 * I * env(t, 1.55, 1.9, 2.2, 2.7))
    m.move("hips", lambda t: (-f * 0.012 * B.H * I * env(t, 0.2, 0.7, 1.6, 2.2), 0.0))
    shrug = 0.025 * B.H * I
    for s in "lr":
        m.move(f"shoulder_{s}", lambda t: (0.0, shrug * env(t, 1.95, 2.15, 2.25, 2.55)))
    ab.event(0.4, "sfx_idle_fidget")
    m.mark(0.35, 0.8, 1.15, 1.55, 1.9, 2.2, 2.7)
    return {}


def gen_talk(m, ab, B, D, I, **_):
    f = B.f
    n = 5
    w = 2 * math.pi / D
    m.rot("head", lambda t: f * I * (2.2 * math.sin(n * w * t) * abs(math.sin(n * w * t / 2 + 0.3)) +
                                    0.8 * math.sin(2 * w * t + 0.4)))
    m.scale("mouth", lambda t: (1.0, 1 + 0.55 * I * max(0.0, math.sin(n * w * t)) ** 0.7))
    _breathe(m, B, I * 0.6, D)
    near = _near_side(B)
    if B.has(f"ik_hand_{near}"):
        m.move(f"ik_hand_{near}", lambda t: _arc(B, near, 28 * I * (0.5 - 0.5 * math.cos(w * t)),
                                                 0.18 * (0.5 - 0.5 * math.cos(w * t))))
    _lean(m, lambda t: -f * 1.2 * I * (0.5 - 0.5 * math.cos(w * t)))
    ab.event(0.0, "sfx_talk")
    return {"syllables": n}


# ---------------------------------------------------------------------------------------- air (jump / land / win)
def _hop(m: _Motion, B: _Body, I: float, t_crouch: float, t_off: float, air: float, apex: float, crouch: float,
         absorb_end: float, D: float, tuck: float = 0.2):
    """Shared hop: crouch [0, t_crouch], push to take-off t_off, gravity parabola for ``air`` s, touch-down absorb on
    an exact spring, rest by D. The ground carrier flies, so feet and body leave the floor together."""
    g = 8 * apex / air ** 2
    v0 = 4 * apex / air
    t_down = t_off + air
    Ldrop = crouch * B.Lleg
    x_abs, info = exact_spring(1.0, 0.25, 3.2)

    def ground_y(t):
        if t_off <= t <= t_down:
            tau = t - t_off
            return v0 * tau - g * tau * tau / 2
        return 0.0
    m.move("ground", lambda t: (0.0, ground_y(t)))

    def hips_y(t):
        if t < t_crouch:
            return -Ldrop * smoothstep(t / t_crouch)
        if t < t_off:
            u = (t - t_crouch) / (t_off - t_crouch)
            return -Ldrop * (1 - u * u)                       # accelerating push (force → speed at take-off)
        if t < t_down:
            return 0.0
        return 0.55 * Ldrop * x_abs(t - t_down) * window_end(t, absorb_end, D)
    m.move("hips", lambda t: (0.0, hips_y(t)))
    # legs tuck in the air (feet come up under the body), then reach for the floor
    for s in "lr":
        def foot(t, s=s):
            if t_off < t < t_down:
                u = (t - t_off) / air
                return (B.f * 0.06 * B.Lleg * math.sin(math.pi * u) * (1 if s == "r" else -0.6),
                        tuck * B.Lleg * math.sin(math.pi * u) ** 1.5)
            return (0.0, 0.0)
        m.move(f"ik_foot_{s}", foot)
        m.rot(f"ik_foot_{s}", lambda t: (-B.f * 18 * math.sin(math.pi * (t - t_off) / air) * I
                                         if t_off < t < t_down else 0.0))
    m.mark(t_crouch, t_off, t_down, t_off + air / 2)
    return t_off, t_down, {"apex": round(apex, 2), "air_time": air, "gravity": round(g, 1),
                           "launch_speed": round(v0, 1)}


def _stretch_fn(B: _Body, t_crouch, t_off, t_down, D, I, sq=0.9, st=1.12):
    xs, _ = exact_spring(0.08 * I, 0.025 * I, 3.0)

    def along(t):
        if t < t_crouch:
            return 1 + (sq - 1) * I * smoothstep(t / t_crouch)
        if t < t_off:
            u = (t - t_crouch) / (t_off - t_crouch)
            return 1 + (sq - 1) * I + ((st - 1) - (sq - 1)) * I * smoothstep(u)
        if t < t_down:
            u = (t - t_off) / (t_down - t_off)
            return 1 + (st - 1) * I * (1 - smoothstep(u / 0.5)) + 0.04 * I * smoothstep((u - 0.6) / 0.4)
        return 1 + (0.04 * I + xs(t - t_down) * 1.0) * window_end(t, t_down + 0.25, D)
    return along


def _squash_on_spine(m: _Motion, B: _Body, along):
    chain = [b for b in SPINE_CHAIN if B.has(b)]
    if not chain:
        return None
    carrier = ensure_carrier(B.sk, [B.n(b) for b in chain])
    B.w = B.sk.world()
    if not B.has(carrier):
        return None

    def sc(t):
        a = along(t)
        return (a, a ** -0.5)
    m.s.setdefault(carrier, []).append(sc)
    return carrier


def gen_jump(m, ab, B, D, I, **_):
    t_c, t_off, air = 0.24 * D, 0.31 * D, 0.42 * D
    apex = 0.3 * B.H * I
    t_off, t_down, info = _hop(m, B, I, t_c, t_off, air, apex, 0.16 * I, t_off + air + 0.12, D)
    car = _squash_on_spine(m, B, _stretch_fn(B, t_c, t_off, t_down, D, I))
    for s in "lr":
        m.move(f"ik_hand_{s}", lambda t, s=s: _arc(B, s, _arm_jump(t, t_c, t_off, t_down, D) * I,
                                                   0.12 * smoothstep((t - t_off) / 0.1) * window_end(t, t_down, D)))
    _lean(m, lambda t: -B.f * 10 * I * (smoothstep(t / t_c) * window_end(t, t_c, t_off + 0.05)))
    ab.event(t_off, "sfx_jump")
    ab.event(t_down, "sfx_step", string="both", float=0.0)
    return {**info, "take_off": round(t_off, 3), "touch_down": round(t_down, 3), "carrier": car}


def _arm_jump(t, t_c, t_off, t_down, D):
    if t < t_c:
        return -40 * smoothstep(t / t_c)
    if t < t_off + 0.08:
        return -40 + 190 * smoothstep((t - t_c) / (t_off + 0.08 - t_c))
    return 150 * window_end(t, t_off + 0.1, t_down + 0.1) + 0.0 * D


def gen_land(m, ab, B, D, I, **_):
    first, second = 0.15 * I, 0.05 * I
    x, info = exact_spring(first, second, 2.6)
    w0 = info["t_second"] + 0.3 * (D - info["t_second"])
    car = _squash_on_spine(m, B, lambda t: 1 + x(t) * window_end(t, w0, D))
    drop = 0.14 * B.Lleg / 0.15
    # hips absorb on the same spring; a soft cap on the rebound keeps the legs from locking (the guard does the rest)
    rise_cap = 0.012 * B.Lleg
    m.move("hips", lambda t: (0.0, _softcap(drop * x(t), rise_cap) * window_end(t, w0, D)))
    for s in "lr":
        m.move(f"ik_hand_{s}", lambda t, s=s: _arc(B, s, 16 * I * x(t - 0.04) / first * window_end(t, w0, D),
                                                   -0.0, (0.0, 0.25 * B.Larm * x(t - 0.05) / first * 0.3 *
                                                          window_end(t, w0, D))))
    m.rot("head", lambda t: B.f * 7 * I * x(t - 0.05) / first * window_end(t, w0, D))
    ab.event(0.0, "sfx_land")
    m.mark(info["t_first"], info["t_second"])
    return {"squash": round(1 - first, 4), "overshoot": round(1 + second, 4), "zeta": round(info["zeta"], 5),
            "t_squash": round(info["t_first"], 4), "t_overshoot": round(info["t_second"], 4), "carrier": car}


def _softcap(v: float, cap: float) -> float:
    return v if v <= 0 else cap * math.tanh(v / cap)


def gen_win(m, ab, B, D, I, **_):
    t_c, t_off, air = 0.16 * D, 0.22 * D, 0.26 * D
    t_off, t_down, info = _hop(m, B, I, t_c, t_off, air, 0.16 * B.H * I, 0.12 * I, t_off + air + 0.12, D, tuck=0.12)
    _squash_on_spine(m, B, _stretch_fn(B, t_c, t_off, t_down, D, I, 0.92, 1.1))

    def up(t):
        return smoothstep((t - t_c * 0.6) / (t_off - t_c * 0.6 + 0.05)) * window_end(t, D - 0.45, D - 0.08)
    near = _near_side(B)
    for s in "lr":
        top_a = 112.0 if s == near else 96.0                # a chibi head is in the way of straight up: pump forward-up
        ph = 0.0 if s == near else 0.7
        m.move(f"ik_hand_{s}", lambda t, s=s, ph=ph, top_a=top_a: _arc(
            B, s, (top_a + 9 * math.sin(2 * math.pi * 3.0 * (t - t_down) + ph) * smoothstep((t - t_down) / 0.1))
            * up(t) * min(I, 1.2), 0.2 * up(t)))
    m.rot("head", lambda t: B.f * 8 * I * up(t))
    _lean(m, lambda t: B.f * 5 * I * up(t))
    ab.event(t_off, "sfx_win")
    ab.event(t_down, "sfx_step", string="both", float=0.0)
    return {**info, "take_off": round(t_off, 3), "touch_down": round(t_down, 3)}


# ---------------------------------------------------------------------------------------- combat
def gen_hit(m, ab, B, D, I, blow_from: str = "front", **_):
    f = B.f
    d = -f if blow_from == "front" else f                 # the blow pushes this way (world x)
    ta = 2 / 30                                           # 2-frame anticipation against the push
    x, info = exact_spring(1.0, 0.3, 2.8)
    w0 = 0.42 * D

    def ant(t):
        return math.sin(math.pi * min(max(t / ta, 0), 1)) if t < ta else 0.0

    def rec(t, lag=0.0):
        return -x(t - ta - lag) * window_end(t, w0, D) if t >= ta + lag else 0.0
    # lean: + = counter-clockwise; a top moving toward +x leans clockwise, so lean = -dir * angle
    ang = 24 * I
    for i, b in enumerate(SPINE_CHAIN):
        m.rot(b, lambda t, i=i: -d * ang * (0.3, 0.3, 0.25, 0.15)[i] * rec(t, i / 30) + d * 3 * I * 0.25 * ant(t))
    m.rot("neck", lambda t: -d * ang * 0.3 * rec(t, 4 / 30))
    m.rot("head", lambda t: -d * ang * 0.55 * rec(t, 5 / 30))
    m.move("hips", lambda t: (d * 0.05 * B.H * I * rec(t) - d * 0.008 * B.H * ant(t), 0.0))
    for s in "lr":
        m.move(f"ik_hand_{s}", lambda t, s=s: (-d * 0.12 * B.Larm * I * rec(t, 2 / 30),
                                               0.18 * B.Larm * I * rec(t, 2 / 30)))
    # red flash on the art, 1/t-ish fade
    for sl in B.sk.slots:
        if sl.blend != "normal" or not sl.attachment:
            continue
        c = sl.color or "FFFFFFFF"
        hot = _tint(c, (1.0, 0.55, 0.5))
        ab.slot_color(sl.name, [(0, c), (ta, c), (ta + 0.02, hot), (ta + 0.2, _tint(c, (1.0, 0.85, 0.85))),
                                (ta + 0.34, c)], "linear")
    ab.event(ta, "sfx_hit")
    m.mark(ta, ta + info["t_first"])
    return {"blow_dir": d, "anticipation_s": round(ta, 4), "impact": round(ta, 4), "zeta": round(info["zeta"], 4)}


def _tint(c: str, k) -> str:
    v = [int(c[i:i + 2], 16) for i in (0, 2, 4)]
    a = c[6:8] if len(c) >= 8 else "FF"
    return "".join(f"{round(x * kk):02X}" for x, kk in zip(v, k)) + a


def gen_attack(m, ab, B, D, I, attack_hand: str = "auto", **_):
    f = B.f
    s = _near_side(B) if attack_hand == "auto" else attack_hand
    if not B.has(f"ik_hand_{s}"):
        s = "l" if s == "r" else "r"
    o = "l" if s == "r" else "r"
    t_w, t_s = 0.33 * D, 0.42 * D                         # wind-up end, strike (impact)
    x, info = exact_spring(1.0, 0.3, 3.0)
    w0 = 0.6 * D
    S = B.pos(f"upper_arm_{s}") if B.has(f"upper_arm_{s}") else B.pos("chest")
    W0 = B.pos(f"ik_hand_{s}")
    reach = 0.96 * B.Larm
    back = S + np.array([-f * 0.7 * B.Larm, -0.32 * B.Larm])          # reach 0.77: a moderate elbow bend
    hit_p = S + np.array([f * reach, 0.06 * B.Larm])

    def k_strike(t):
        """0 at rest → -1 wound up → +1 struck (+ overshoot) → 0."""
        if t < t_w:
            return -smoothstep(t / t_w)
        if t < t_s:
            u = (t - t_w) / (t_s - t_w)
            return -1 + 2 * u ** 2.2                        # accelerating strike
        return (1 - 0.15 * x(t - t_s)) * window_end(t, t_s + 0.06, D - 0.05)

    def hand(t):
        k = k_strike(t)
        P = W0 + (back - W0) * (-k) if k < 0 else W0 + (hit_p - W0) * k
        return P - W0
    m.move(f"ik_hand_{s}", hand)
    if B.has(f"ik_hand_{o}"):
        m.move(f"ik_hand_{o}", lambda t: _arc(B, o, -25 * I * max(0.0, k_strike(t)) + 15 * I * max(0.0, -k_strike(t))))
    m.move("hips", lambda t: (f * 0.045 * B.H * I * k_strike(t), -0.01 * B.H * abs(k_strike(t))))
    _lean(m, lambda t: -f * 12 * I * k_strike(t), lag=1 / 30)
    m.rot("head", lambda t: f * 5 * I * k_strike(t - 2 / 30))
    car = _squash_on_spine(m, B, lambda t: 1 + 0.05 * I * max(0.0, k_strike(t)) - 0.04 * I * max(0.0, -k_strike(t)))
    ab.event(t_s, "sfx_attack")
    ab.event(t_s, "attack_hit")
    m.mark(t_w, t_s)
    return {"hand": s, "wind_up": round(t_w, 3), "impact": round(t_s, 3), "carrier": car}


def gen_lose(m, ab, B, D, I, **_):
    f = B.f

    def slump(t):
        return smoothstep((t - 0.1) / 0.55) * window_end(t, D - 0.65, D - 0.05)
    _lean(m, lambda t: -f * 16 * I * slump(t) - f * 1.5 * I * slump(t) * math.sin(2 * math.pi * (t - 0.7) / 1.2))
    m.rot("head", lambda t: -f * 20 * I * slump(t))
    m.move("hips", lambda t: (0.0, -0.06 * B.Lleg * I * slump(t)))
    for s in "lr":
        m.move(f"ik_hand_{s}", lambda t, s=s: _arc(B, s, 6 * I * slump(t), -0.02 * slump(t)) +
               np.array([0.0, -0.04 * B.Larm * slump(t)]))
        m.move(f"shoulder_{s}", lambda t: (0.0, -0.012 * B.H * I * slump(t)))
    m.scale("chest", lambda t: ((1 - 0.03 * I * slump(t)),) * 2)
    ab.event(0.1, "sfx_lose")
    return {}


def _reach_guard(m: _Motion, B: _Body) -> None:
    """Lower the hips just enough, smoothly, wherever a clip would over-extend a leg (an over-extended IK leg locks
    and its foot leaves the target: the ankle cracks and the foot slides). Gait clips already sit low enough."""
    if not B.has("hips") or not B.feet:
        return
    ts = np.array(m.times())
    need = np.zeros(len(ts))
    for s in B.feet:
        if not (B.has(f"thigh_{s}") and B.has(f"shin_{s}")):
            continue
        R = 0.975 * B.leg_len(s)
        J0, A0 = B.hipj(s), B.feet[s]["A"]
        for i, t in enumerate(ts):
            hp = m.move_at("hips", t)
            A = A0 + m.move_at(f"ik_foot_{s}", t)
            J = J0 + hp
            dx = J[0] - A[0]
            if R * R <= dx * dx:
                need[i] = max(need[i], J[1] - A[1])
                continue
            over = (J[1] - A[1]) - math.sqrt(R * R - dx * dx)
            need[i] = max(need[i], over)
    if need.max() <= 1e-6:
        return
    # widen and smooth the need so the correction has no corners, keep the clip's ends
    k = max(1, int(round(0.12 / max(ts[1] - ts[0], 1e-6))))
    pad = np.pad(need, k, mode="wrap" if m.loop else "edge")
    mx = np.array([pad[i:i + 2 * k + 1].max() for i in range(len(need))])
    ker = np.hanning(2 * k + 3)[1:-1]
    ker /= ker.sum()
    pad = np.pad(mx, k, mode="wrap" if m.loop else "edge")
    sm = np.convolve(pad, ker, mode="same")[k:-k] * 1.04
    if not m.loop:
        sm[-1] = 0.0
        sm[0] = need[0]
    fn_t, fn_v = ts.copy(), -sm
    m.t.setdefault(B.n("hips"), []).append(lambda t: (0.0, float(np.interp(t, fn_t, fn_v))))


def _wind_keys(ab: AnimBuilder, B: _Body, D: float, wind: float, loop: bool) -> None:
    """Headwind on the strands while moving (gusting a little, closed loop); 0 in every other clip so nothing is
    left blowing when the game switches clips."""
    names = [c.name for c in B.sk.physics if not c.name.startswith("phys_look")]
    for nm in names:
        if wind and loop:
            ks = []
            n = 8
            for i in range(n + 1):
                t = D * i / n
                g = 1 + 0.18 * math.sin(2 * math.pi * i / n) + 0.08 * math.sin(4 * math.pi * i / n + 1)
                ks.append(Key(time=round(t, 4), value=round(wind * g, 3)))
            ks[-1] = Key(time=round(D, 4), value=ks[0].model_extra["value"])
        else:
            ks = [Key(time=0.0, value=0.0)]
        ab.a.physics.setdefault(nm, {})["wind"] = ks


WIND_K = 26.0       # wind at 300 px/s of ground speed (a cape trails back about 25 degrees in a run)


def breathe_clip(project: Project, period: float = 4.0, intensity: float = 1.0, name: str = "breathe",
                 bone_map: dict | None = None) -> dict:
    """The breath alone as a loop (layer it on a second track over any clip): chest, shoulders, head counter-nod."""
    B = _Body(project, bone_map, "auto")
    m = _Motion(B, period, True)
    ab = AnimBuilder(B.sk, name)
    _breathe(m, B, intensity, period)
    m.write(ab)
    return {"clip": name, "period": period}


GEN = {"idle": gen_idle, "idle_fidget": gen_fidget, "walk": gen_walk, "run": gen_run, "jump": gen_jump,
       "land": gen_land, "hit": gen_hit, "attack": gen_attack, "win": gen_win, "lose": gen_lose, "talk": gen_talk}


# ======================================================================================== procedural sample
def _mask_part(shapes, ss: int, x0: float, y1: float, size):
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for sh in shapes:
        _draw_shape(d, sh, ss, x0, y1, 255)
    return m


def _px(p, ss, x0, y1):
    return ((p[0] - x0) * ss, (y1 - p[1]) * ss)


def _draw_shape(d: ImageDraw.ImageDraw, sh: tuple, ss: int, x0: float, y1: float, fill, grow: float = 0.0):
    kind = sh[0]
    if kind == "capsule":                                 # ("capsule", [(x, y), ...], width or [w per point])
        pts, wd = sh[1], sh[2]
        ws = wd if isinstance(wd, (list, tuple)) else [wd] * len(pts)
        for (a, wa), (b, wb) in zip(zip(pts, ws), zip(pts[1:], ws[1:])):
            n = max(2, int(math.hypot(b[0] - a[0], b[1] - a[1]) / 2))
            for k in range(n + 1):
                u = k / n
                c = (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
                r = ((wa + (wb - wa) * u) / 2 + grow) * ss
                cx, cy = _px(c, ss, x0, y1)
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
    elif kind == "ellipse":                               # ("ellipse", cx, cy, rx, ry)
        _, cx, cy, rx, ry = sh
        a = _px((cx - rx - grow, cy + ry + grow), ss, x0, y1)
        b = _px((cx + rx + grow, cy - ry - grow), ss, x0, y1)
        d.ellipse([a[0], a[1], b[0], b[1]], fill=fill)
    elif kind == "poly":                                  # ("poly", [(x, y), ...])
        d.polygon([_px(p, ss, x0, y1) for p in sh[1]], fill=fill)
    elif kind == "rrect":                                 # ("rrect", x0, y0, x1, y1, radius)
        _, a0, b0, a1, b1, rad = sh
        p = _px((a0 - grow, b1 + grow), ss, x0, y1)
        q = _px((a1 + grow, b0 - grow), ss, x0, y1)
        d.rounded_rectangle([p[0], p[1], q[0], q[1]], radius=(rad + grow) * ss, fill=fill)
    elif kind == "chord":                                 # ("chord", cx, cy, rx, ry, start, end)
        _, cx, cy, rx, ry, a0, a1 = sh
        p = _px((cx - rx, cy + ry), ss, x0, y1)
        q = _px((cx + rx, cy - ry), ss, x0, y1)
        d.chord([p[0], p[1], q[0], q[1]], a0, a1, fill=fill)
    else:
        raise ValueError(kind)


def _shape_bounds(sh) -> tuple[float, float, float, float]:
    k = sh[0]
    if k == "capsule":
        P = np.array(sh[1], float)
        w = max(sh[2]) if isinstance(sh[2], (list, tuple)) else sh[2]
        return P[:, 0].min() - w, P[:, 1].min() - w, P[:, 0].max() + w, P[:, 1].max() + w
    if k in ("ellipse", "chord"):
        return sh[1] - sh[3], sh[2] - sh[4], sh[1] + sh[3], sh[2] + sh[4]
    if k == "poly":
        P = np.array(sh[1], float)
        return P[:, 0].min(), P[:, 1].min(), P[:, 0].max(), P[:, 1].max()
    return sh[1], sh[2], sh[3], sh[4]


def _part(project: Project, sk: SkeletonData, slot: str, shapes: list, top, bottom, outline=(34, 24, 38),
          ow: float = 2.5, details: list | None = None, shade: float = 1.0, ss: int = 3):
    """Draw one layer from world-space shapes (supersampled, outlined, vertically shaded), crop it to its content
    and place it on the root bone exactly where import_psd would put that PSD layer."""
    bs = np.array([_shape_bounds(s) for s in shapes + [d[0] for d in (details or [])]])
    x0, yb, x1, y1 = bs[:, 0].min() - 6, bs[:, 1].min() - 6, bs[:, 2].max() + 6, bs[:, 3].max() + 6
    W, H = int(math.ceil((x1 - x0) * ss)), int(math.ceil((y1 - yb) * ss))
    mask = _mask_part(shapes, ss, x0, y1, (W, H))
    inner = mask.filter(ImageFilter.MinFilter(int(2 * ow * ss) | 1))
    g = np.linspace(0, 1, H)[:, None, None]
    top_c = np.array(top, float) * shade
    bot_c = np.array(bottom, float) * shade
    grad = (top_c[None, None] * (1 - g) + bot_c[None, None] * g).repeat(W, 1)
    rgb = np.where((np.array(inner)[..., None] > 127), grad, np.array(outline, float)[None, None])
    im = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    for sh, col in details or []:
        dm = Image.new("L", (W, H), 0)
        _draw_shape(ImageDraw.Draw(dm), sh, ss, x0, y1, 255)
        dm = Image.fromarray(np.minimum(np.array(dm), np.array(inner)))
        layer = Image.new("RGBA", (W, H), tuple(int(c * shade) for c in col[:3]) + (255,))
        im.paste(layer, (0, 0), dm)
    im.putalpha(mask)
    im = im.resize((max(1, W // ss), max(1, H // ss)), Image.LANCZOS)
    bb = im.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    im = im.crop(bb)
    cx = x0 + (bb[0] + bb[2]) / 2
    cy = y1 - (bb[1] + bb[3]) / 2
    # ir.RegionAttachment defaults width/height to 32 and saving drops defaults, but the runtime has no default
    # (NaN vertices): never ship a 32 px side
    if 32 in im.size:
        big = Image.new("RGBA", (im.width + (im.width == 32), im.height + (im.height == 32)), (0, 0, 0, 0))
        big.paste(im, (0, 0))
        cx += 0.5 * (im.width == 32)
        cy -= 0.5 * (im.height == 32)
        im = big
    project.write_image(slot, im)
    sk.slots.append(Slot(name=slot, bone="root", attachment=slot))
    sk.set_attachment(slot, slot, RegionAttachment(x=round(cx, 2), y=round(cy, 2), width=im.width, height=im.height))


def make_sample_biped(out_dir: str | Path, name: str = "biped", split_limbs: bool = False,
                      facing: str = "right", straight: bool = False) -> Project:
    """A chibi adventurer seen from the side (3/4), every part its own layer named after BIPED_LAYERS, exactly as
    import_psd would bring in a PSD with origin="bottom" (feet on y=0): torso, head, arm_l/r + hand_l/r,
    leg_l/r + foot_l/r (or upper_arm/lower_arm, thigh/shin with ``split_limbs``), plus secondary layers (cape,
    ponytail, belt_tail, pouch) and head features (eye_r, brow_r, mouth, ear_r, hat). The far side (_l when facing
    right) is darker and drawn behind. ``straight`` draws straight limbs (the bend direction then comes from the
    default: knees forward, elbows back)."""
    if facing not in ("right", "left"):
        raise ValueError("facing is right | left")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    sk = new_skeleton(width=320, height=460)
    p = Project(out / f"{name}.json", sk)
    F = 1 if facing == "right" else -1

    def X(pts):
        return [(F * x, y) for x, y in pts]

    def mirror(sh):
        k = sh[0]
        if k == "capsule":
            return (k, X(sh[1]), sh[2])
        if k == "ellipse":
            return (k, F * sh[1], sh[2], sh[3], sh[4])
        if k == "poly":
            return (k, X(sh[1]))
        if k == "rrect":
            a, b = sorted((F * sh[1], F * sh[3]))
            return (k, a, sh[2], b, sh[4], sh[5])
        if k == "chord":
            if F > 0:
                return sh
            return (k, -sh[1], sh[2], sh[3], sh[4], 180 - sh[6], 180 - sh[5])
        return sh

    def part(slot, shapes, top, bottom, details=None, shade=1.0, **kw):
        _part(p, sk, slot, [mirror(s) for s in shapes], top, bottom,
              details=[(mirror(s), c) for s, c in (details or [])], shade=shade, **kw)

    skin_t, skin_b = (255, 216, 184), (226, 164, 132)
    tunic_t, tunic_b = (92, 178, 104), (36, 104, 62)
    pants_t, pants_b = (86, 104, 176), (42, 52, 112)
    boot_t, boot_b = (150, 96, 56), (88, 52, 28)
    cape_t, cape_b = (214, 52, 66), (118, 18, 38)
    hair_t, hair_b = (132, 72, 36), (82, 40, 18)
    far = 0.72
    knee_dx = 0 if straight else 9
    elbow_dx = 0 if straight else -9

    def leg(side, dx, shade):
        pts = [(4 + dx, 152), ((3 if straight else 6) + dx + knee_dx, 86), (2 + dx, 20)]
        if not split_limbs:
            part(f"leg_{side}", [("capsule", pts, 30)], pants_t, pants_b, shade=shade)
        else:
            part(f"thigh_{side}", [("capsule", pts[:2], 31)], pants_t, pants_b, shade=shade)
            part(f"shin_{side}", [("capsule", pts[1:], 28)], pants_t, pants_b, shade=shade)

    def foot(side, dx, shade):
        part(f"foot_{side}", [("rrect", -18 + dx, 0, 38 + dx, 22, 10), ("ellipse", -2 + dx, 22, 16, 14)],
             boot_t, boot_b, details=[(("rrect", -18 + dx, 0, 38 + dx, 5, 2), (60, 36, 22))], shade=shade)

    def arm(side, dx, shade):
        pts = [(2 + dx, 250), ((3.02 if straight else 0) + dx + elbow_dx, 199), (4 + dx, 150)]
        if not split_limbs:
            part(f"arm_{side}", [("capsule", pts, 25)], tunic_t, tunic_b,
                 details=[(("capsule", [pts[1], pts[2]], 22), skin_b)], shade=shade)
        else:
            part(f"upper_arm_{side}", [("capsule", pts[:2], 26)], tunic_t, tunic_b, shade=shade)
            part(f"lower_arm_{side}", [("capsule", pts[1:], 23)], skin_t, skin_b, shade=shade)

    def hand(side, dx, shade):
        part(f"hand_{side}", [("ellipse", 5 + dx, 137, 15, 16)], skin_t, skin_b, shade=shade)

    # back → front
    part("cape", [("poly", [(-30, 270), (14, 270), (-6, 112), (-80, 96), (-58, 180)])], cape_t, cape_b)
    lock = [(-62, 376), (-82, 340), (-92, 300), (-90, 262), (-80, 232)]
    part("ponytail", [("capsule", lock, [30, 28, 24, 18, 11])], hair_t, hair_b)
    arm("l", -8, far)
    hand("l", -8, far)
    leg("l", -8, far)
    foot("l", -8, far)
    leg("r", 0, 1.0)
    foot("r", 0, 1.0)
    part("pouch", [("rrect", -54, 108, -26, 140, 8)], (170, 112, 62), (112, 66, 34),
         details=[(("rrect", -54, 128, -26, 140, 6), (96, 56, 28))])
    part("torso", [("rrect", -42, 118, 44, 274, 34)], tunic_t, tunic_b,
         details=[(("rrect", -50, 140, 50, 154, 2), (96, 58, 30)), (("rrect", 8, 138, 24, 156, 3), (236, 196, 70))])
    part("belt_tail", [("capsule", [(30, 146), (36, 122), (33, 92)], [9, 9, 8])], (124, 76, 40), (84, 48, 24))
    part("head", [("ellipse", 8, 344, 78, 80), ("ellipse", 84, 330, 11, 10)], skin_t, skin_b)
    part("ear_r", [("ellipse", -10, 326, 13, 18)], skin_t, skin_b, details=[(("ellipse", -10, 326, 6, 10), (214, 140, 118))])
    part("eye_r", [("ellipse", 50, 336, 9, 13)], (40, 28, 46), (24, 16, 30), outline=(24, 16, 30), ow=1.0,
         details=[(("ellipse", 53, 341, 3.5, 4.5), (255, 255, 255))])
    part("brow_r", [("capsule", [(38, 357), (60, 360)], 6)], (90, 50, 26), (70, 36, 18), outline=(60, 30, 14), ow=1.0)
    part("mouth", [("chord", 60, 300, 13, 10, 0, 180)], (176, 52, 70), (140, 30, 50), outline=(90, 20, 36), ow=1.2)
    part("hat", [("chord", 4, 360, 86, 78, 180, 360), ("rrect", -84, 352, 96, 368, 8)], (60, 140, 80), (30, 92, 50),
         details=[(("rrect", -78, 366, 92, 376, 3), (220, 180, 60))])
    arm("r", 0, 1.0)
    hand("r", 0, 1.0)
    p.save()
    return p
