"""Face rig recipe: 2.5D turn, eyes that look and blink, 3-bone brows, visemes + jaw, cheeks, hair physics and the
expression clips (idle, happy, sad, angry, surprised, talk), plus two tools that work on any rig: ``look_at`` (a lagged
eyes -> head -> spine chain) and ``lipsync`` (text or phonemes -> viseme + jaw keys).

**Parts are recognised by layer name** (``FACE_LAYERS``), case-insensitive, with ``_L``/``_R`` sides (``eye_l``,
``eye_left``, ``left_eye`` and ``eyeL`` all work). ``psd.import_psd`` flattens groups to ``group/layer`` slot names, so the
PSD convention is::

    face/                       (any top group name, or none)
      head                      the face base (also: face, skin, base)          REQUIRED
      eye_L/ white iris pupil highlight lid_upper lid_lower                    (eye_R the same)
      brow_L  brow_R  nose  jaw (chin art)  cheek_L  cheek_R  ear_L  ear_R
      mouth/ A E I O U M F L  [rest smile frown]                               (or one plain "mouth" layer)
    hair/ back  bangs (fringe)  strand_L strand_R ... (any other hair_* / lock_* / strand_* layer)

Only the head is required; every missing part is skipped and reported. A single ``eye_L`` layer (no white/iris split)
still turns and blinks by squashing. Recognised slots are renamed to canonical names (``eye_L_white``, ``brow_L``,
``mouth``...) so game code and clips can address them whatever the PSD's group path was; attachments keep their image
paths. The mouth layers merge into ONE ``mouth`` slot with one attachment per shape (``A``...``L``, ``rest``, ``smile``,
``frown``). Eye parts are re-stacked white, iris, pupil, highlight, lid_lower, lid_upper.

**Rig** (all under one ``face_rig`` bone at the chin, screen-aligned, child of ``parent``; keyed only by the clips,
never the artist's own bones):

* Turn: ``rig.turn_rig`` is the base layer: the face mesh's middle travels with ``turn_ctrl`` while its outline stays
  pinned, features parallax by depth (nose 1.25, mouth 1, brows 0.95, eyes 0.9, bangs 0.85, ears -0.35, back hair -0.5).
* Eyes: ``face_look`` (local 0 under ``face_look_base``) is the look target. Each eye's ``eye_L_aim`` copies it times
  a gain (relative/local transform constraint). The **ellipse clamp** is a one-bone IK with ``compress`` and no
  ``stretch``: the IK bone (length rx) points at the aim and shrinks when the aim is closer than rx, never stretches,
  so its tip is the aim inside the circle and on the circle outside it. The IK bone's parent ``eye_L_space`` is scaled
  (1, ry/rx), and IK solves in the parent's local space, so the circle is the socket ELLIPSE (rx, ry) on screen. The
  eyeball ``eye_L_ball`` (iris; pupil on ``eye_L_pupil`` for dilation keys) copies the tip's world position (absolute
  transform constraint, translate only), so the iris is never squashed; the highlight copies 55% of it (a specular
  glint stays with the light). The game may move ``face_look`` anywhere: the iris cannot leave the white.
* Lids: each lid is a mesh weighted between the socket and a lid bone, per column: the lash travels exactly to the
  meeting line ``m(x) = top(x) - 0.7 (top(x) - bottom(x))`` of the white's own silhouette (the upper lid covers 70%,
  the lower lid 30%), the corners stay put, the top of the upper lid (bottom of the lower lid) is pinned. The bone
  length stores the full travel, so a key of ``-length * closure`` closes the eye whatever the art.
* Brows: three sibling bones (inner/mid/outer) along the brow's centre line on a rig_mesh mesh with hat weights
  along the brow's chord (a piecewise-linear bend through three control points: a big inner raise cannot crease it).
* Mouth & jaw: ``face_jaw`` (local 0 under ``face_jaw_base`` at the upper-lip line) opens by SCALE: the lower face is
  weighted to it, so scaleY stretches the lower face from the lip line down and scaleX = scaleY^-1/2 squashes it
  (volume kept in 3D: x and depth shrink together). ``face_jaw_turn`` (child, same turn constraint as the face surface)
  keeps the turn exact on jaw-weighted vertices. The ``mouth`` slot rides ``face_mouth`` (at the lip line), which copies
  the jaw's squash and half its stretch, so the lower lip drops with the chin. Visemes are attachments.
* Cheeks: ``cheek_L``/``cheek_R`` bones weighted into the face mesh (Gaussian, kept off the jaw), turned with the
  surface, stretched by the jaw (transform constraint: opening the mouth pulls the cheeks long) and lifted by
  ``face_smile`` (local 0 under ``face_smile_base``), which also pushes the lower lids up: smiling squints.
* Hair: strands get ``rig.rig_strand`` (chain, mesh, ``hair`` physics), bangs a separate stiffer swing bone with
  physics, so the fringe sways while the side locks swing.

Scales are stored in bone lengths (visible in the editor as bone size), so later tools need no side file: ``face_rig``
= face height, ``turn_base`` = turn range, ``face_look_base`` = full-gaze travel, ``face_smile_base`` = cheek lift
for smile 1, each lid bone = its full blink travel.

**Clips** (clip contract: loops identical at both ends, one-shots end exactly on the setup pose, the setup never moves):

* ``idle`` (loop): breath (a sin^2 cycle that divides the loop), micro-saccades and blinks on a seeded Poisson timer.
  Saccades are instant (two keys 1 ms apart), the head follows 100 ms later through ``look_at`` (dead time + a damped
  spring), and the eyes counter-roll as the head catches up (vestibulo-ocular reflex: eye = gaze - head). The response
  is solved periodically (the steps of four previous loops are superposed), so the loop closes exactly. Blinks: 80 ms
  down (quadratic, accelerating), 160 ms up (decelerating), lower lid 30%. Fires ``sfx_blink`` per blink.
* ``happy`` ``sad`` ``angry`` ``surprised`` (one-shots): every channel follows an exact underdamped spring step
  ``1 - e^-zwt (cos wd t + z/sqrt(1-z^2) sin wd t)`` (overshoot ``e^(-pi z / sqrt(1-z^2))``, 20% at z = 0.45) times a
  smootherstep release that reaches exactly 0. Brows run on the same envelope shifted one frame earlier (they lead every
  expression, release included), the inner-brow raise is exaggerated (sad: 4.6% of face height vs 1.2% mid).
  Surprised anticipates: a 2-frame volume-preserving squash, then a stretch on a looser spring that overshoots.
  Angry adds a damped 7 Hz head shake. Each fires ``sfx_<clip>`` at the attack.
* ``talk`` (one-shot): ``lipsync`` visemes (stepped, one frame ahead of the sound) and an eased jaw, brow raises and
  small nods on stressed words (alpha-function pulses, brows a frame ahead of the head), blinks. Fires ``sfx_talk``,
  ``talk_word`` (string = the word) at every word and ``talk_end``.
"""
from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .ir import Bone, MeshAttachment, RegionAttachment, SkeletonData, Slot, new_skeleton
from .mesh import mesh_world_vertices, region_pixel_to_local, rig_mesh, to_world
from .project import Project
from .rig import add_ik, add_physics, add_transform, insert_parent, reparent_slot, rig_strand, setup_hull_world, \
    strand_centerline, turn_rig
from .timeline import AnimBuilder, r
from .weights import decode_weighted, finalize, skin_vertices

# ------------------------------------------------------------------------------------------------ naming convention
VISEMES = ("A", "E", "I", "O", "U", "M", "F", "L")
MOUTH_EXTRAS = ("rest", "smile", "frown", "open", "closed")
EYE_PARTS = ("white", "iris", "pupil", "highlight", "lid_lower", "lid_upper")   # also the draw order, back to front
SIDES = ("L", "R")

# role -> what it is, how it is named (lowercase aliases matched against the last one or two path segments; {s} is
# the side letter) and whether it is required. Missing optional roles are skipped.
FACE_LAYERS: dict[str, dict] = {
    "face": {"what": "face base / head skin; becomes the turning surface mesh", "required": True,
             "aliases": ["head", "face", "skin", "base", "face_base", "head_base", "face/head", "face/skin",
                         "face/base"]},
    "eye_{S}_white": {"what": "eye white (sclera); the socket ellipse comes from it",
                      "aliases": ["eye_{s}/white", "eye_{s}_white", "eye_{s}/sclera", "eye_{s}/eyewhite",
                                  "white_{s}", "sclera_{s}"]},
    "eye_{S}_iris": {"what": "iris; rides the clamped eyeball", "aliases": ["eye_{s}/iris", "eye_{s}_iris", "iris_{s}"]},
    "eye_{S}_pupil": {"what": "pupil; scale keys dilate it", "aliases": ["eye_{s}/pupil", "eye_{s}_pupil", "pupil_{s}"]},
    "eye_{S}_highlight": {"what": "catch light; follows the eyeball at 55%",
                          "aliases": ["eye_{s}/highlight", "eye_{s}_highlight", "eye_{s}/glint", "eye_{s}/shine",
                                      "eye_{s}/catchlight", "highlight_{s}"]},
    "eye_{S}_lid_upper": {"what": "upper lid (skin-coloured, lash on its lower edge); covers 70% in a blink",
                          "aliases": ["eye_{s}/lid_upper", "eye_{s}_lid_upper", "eye_{s}/upper_lid", "eye_{s}/lid",
                                      "eye_{s}/eyelid", "eye_{s}/lid_top", "lid_upper_{s}", "upper_lid_{s}"]},
    "eye_{S}_lid_lower": {"what": "lower lid (skin-coloured, edge on top); covers 30% in a blink",
                          "aliases": ["eye_{s}/lid_lower", "eye_{s}_lid_lower", "eye_{s}/lower_lid",
                                      "eye_{s}/lid_bottom", "lid_lower_{s}", "lower_lid_{s}"]},
    "eye_{S}": {"what": "a whole eye in one layer (no look rig); blinks by squashing", "aliases": ["eye_{s}"]},
    "brow_{S}": {"what": "eyebrow; 3 bones on a mesh", "aliases": ["brow_{s}", "eyebrow_{s}", "brows_{s}"]},
    "nose": {"what": "nose (turn depth 1.25)", "aliases": ["nose"]},
    "mouth": {"what": "mouth shapes: a mouth/ group of A E I O U M F L (+ rest, smile, frown) or one plain layer",
              "aliases": ["mouth", "lips"]},
    "jaw": {"what": "chin art; rides the jaw", "aliases": ["jaw", "chin"]},
    "cheek_{S}": {"what": "cheek / blush art on the cheek bone", "aliases": ["cheek_{s}", "blush_{s}"]},
    "ear_{S}": {"what": "ear (turn depth -0.35)", "aliases": ["ear_{s}"]},
    "hair_back": {"what": "hair behind the head (turn depth -0.5)",
                  "aliases": ["hair_back", "back_hair", "hair/back", "hairback", "hair_behind", "hair/behind"]},
    "bangs": {"what": "fringe; its own swing bone with stiff physics",
              "aliases": ["bangs", "bang", "fringe", "hair/bangs", "hair/fringe", "hair_front", "front_hair",
                          "hair/front", "hair_bangs", "hair_fringe"]},
    "strand": {"what": "hair strand / lock: any other hair/*, hair_*, lock_*, strand_* layer; chain + mesh + physics",
               "aliases": []},
}

DEPTH = {"eye": 0.9, "brow": 0.95, "nose": 1.25, "mouth": 1.0, "ear": -0.35, "hair_back": -0.5, "bangs": 0.85,
         "strand_front": 0.7, "strand_back": -0.3}
LOOK_GAIN = 1.15          # aim offset at full gaze, in socket radii (a little past the rim, so the clamp engages)
JAW_OPEN = 0.32           # lower-face stretch at jaw open 1 (scaleY 1.32)
BLINK_DOWN, BLINK_UP = 0.08, 0.16
UPPER_SHARE = 0.7         # the upper lid covers 70% of the opening, the lower lid 30%
CLIPS = ("idle", "happy", "sad", "angry", "surprised", "talk")
TALK_TEXT = "Hello! Spin to win, big wins today."


def _norm_seg(seg: str) -> str:
    s = re.sub(r"[\s\-.]+", "_", seg.strip().lower()).strip("_")
    m = re.match(r"^(left|l|right|r)_(.+)$", s)
    if m and m.group(2) in ("eye", "brow", "eyebrow", "cheek", "ear", "blush", "strand", "lock", "iris", "pupil"):
        s = f"{m.group(2)}_{m.group(1)[0]}"
    s = re.sub(r"_(left|right)$", lambda mm: "_" + mm.group(1)[0], s)
    m = re.match(r"^(eye|brow|eyebrow|cheek|ear|blush)(l|r)$", s)
    if m:
        s = f"{m.group(1)}_{m.group(2)}"
    return s


def _alias_table() -> dict[str, str]:
    out: dict[str, str] = {}
    for role, spec in FACE_LAYERS.items():
        for al in spec["aliases"]:
            if "{s}" in al or "{S}" in role:
                for S in SIDES:
                    out[al.replace("{s}", S.lower())] = role.replace("{S}", S)
            else:
                out[al] = role
    return out


_ALIASES = _alias_table()


def _role_of(slot_name: str) -> tuple[str | None, str | None]:
    """(role, extra) for one slot name; extra is the mouth shape name or the strand's clean name."""
    segs = [_norm_seg(s) for s in slot_name.split("/") if s.strip()]
    if not segs:
        return None, None
    last = segs[-1]
    if len(segs) >= 2 and segs[-2] in ("mouth", "mouths", "visemes", "lips"):
        return "mouth_shape", last
    m = re.match(r"^mouth_(.+)$", last)
    if m and (m.group(1).upper() in VISEMES or m.group(1) in MOUTH_EXTRAS):
        return "mouth_shape", m.group(1)
    cands = []
    if len(segs) >= 2:
        cands += ["/".join(segs[-2:]), "_".join(segs[-2:])]
    cands.append(last)
    for c in cands:
        if c in _ALIASES:
            return _ALIASES[c], None
    if re.match(r"^(strand|lock|hair)", last) or (len(segs) >= 2 and segs[-2] == "hair"):
        return "strand", last
    return None, None


def find_face_parts(sk: SkeletonData) -> dict:
    """Recognise face parts by slot name. Returns {"roles": {role: slot}, "mouth": {shape: slot}, "strands": [...],
    "missing": [...optional roles not found], "unrecognised": [...]}. Raises ValueError when the head is missing or
    two slots claim the same part."""
    roles: dict[str, str] = {}
    mouth: dict[str, str] = {}
    strands: list[tuple[str, str]] = []
    unknown = []
    for s in sk.slots:
        role, extra = _role_of(s.name)
        if role is None:
            unknown.append(s.name)
        elif role == "mouth_shape":
            shape = extra.upper() if extra.upper() in VISEMES else extra
            if shape in mouth:
                raise ValueError(f"two slots are mouth shape {shape!r}: {mouth[shape]!r} and {s.name!r}")
            mouth[shape] = s.name
        elif role == "strand":
            strands.append((s.name, extra))
        elif role in roles:
            raise ValueError(f"two slots are the {role!r}: {roles[role]!r} and {s.name!r}; rename one")
        else:
            roles[role] = s.name
    if "face" not in roles:
        raise ValueError("no face base layer found: name it head (or face / skin / base), e.g. face/head. "
                         f"Convention: {face_convention()}. Slots seen: {[s.name for s in sk.slots][:30]}")
    for S in SIDES:
        if f"eye_{S}_white" not in roles and any(f"eye_{S}_{p}" in roles for p in ("iris", "pupil", "lid_upper")):
            raise ValueError(f"eye_{S} has parts but no white (eye_{S}/white): the socket ellipse comes from it")
        if f"eye_{S}_white" in roles and f"eye_{S}" in roles:
            raise ValueError(f"both a whole-eye layer {roles['eye_' + S]!r} and eye_{S}/white exist; keep one")
    if "mouth" in roles and mouth:
        raise ValueError(f"both a plain mouth layer {roles['mouth']!r} and a mouth/ group exist; keep one")
    expected = ["nose", "jaw", "hair_back", "bangs", "mouth"] + [f"{p}_{S}" for S in SIDES for p in ("brow", "cheek", "ear")]
    expected += [f"eye_{S}_{p}" for S in SIDES for p in EYE_PARTS]
    missing = [k for k in expected if k not in roles and not (k == "mouth" and mouth)
               and not (k.startswith("eye_") and k[:5] in roles)]
    if mouth:
        missing += [f"mouth/{v}" for v in VISEMES if v not in mouth]
    return {"roles": roles, "mouth": mouth, "strands": strands, "missing": missing, "unrecognised": unknown}


def face_convention() -> str:
    return ("face/head (required), face/eye_L/{white,iris,pupil,highlight,lid_upper,lid_lower}, face/brow_L, "
            "face/nose, face/mouth/{A,E,I,O,U,M,F,L,rest,smile,frown}, face/jaw, face/cheek_L, face/ear_L, "
            "hair/back, hair/bangs, hair/strand_L (and _R); case-insensitive, any group prefix")


# ------------------------------------------------------------------------------------------------ slot surgery
def rename_slot(sk: SkeletonData, old: str, new: str) -> None:
    """Rename a slot everywhere it is referenced (skins, animations, draw order keys, clipping ends)."""
    if old == new:
        return
    if sk.has_slot(new):
        raise ValueError(f"slot {new!r} already exists")
    sk.slot(old).name = new
    for skin in sk.skins:
        if old in skin.attachments:
            skin.attachments[new] = skin.attachments.pop(old)
        for atts in skin.attachments.values():
            for a in atts.values():
                if getattr(a, "type", "") == "clipping" and a.end == old:
                    a.end = new
    for a in sk.animations.values():
        if old in a.slots:
            a.slots[new] = a.slots.pop(old)
        for node in a.attachments.values():
            if old in node:
                node[new] = node.pop(old)
        for d in a.drawOrder:
            for o in d.offsets or []:
                if o.slot == old:
                    o.slot = new


def _merge_mouth(project: Project, shapes: dict[str, str], bone: str) -> dict:
    """Mouth layers -> one ``mouth`` slot with one attachment per shape (path = the layer's image)."""
    sk = project.data
    for sl in shapes.values():
        for a in sk.animations.values():
            if sl in a.slots or any(sl in n for n in a.attachments.values()):
                raise ValueError(f"mouth layer {sl!r} is already animated; rig the face before animating it")
    world = sk.world()
    first = min(shapes.values(), key=sk.slot_index)
    name = sk.unique_name("mouth", "slot")
    sk.add_slot(Slot(name=name, bone=bone), before=first)
    rest = "rest" if "rest" in shapes else ("M" if "M" in shapes else ("closed" if "closed" in shapes else None))
    for shape, sl in shapes.items():
        s = sk.slot(sl)
        att = sk.attachment(sl)
        if not isinstance(att, RegionAttachment):
            raise ValueError(f"mouth layer {sl!r} must be a region (unmeshed) attachment")
        img = project.att_image_name(sl, s.attachment)
        wx, wy = world[s.bone].to_world(att.x, att.y)
        lx, ly = world[bone].to_local(wx, wy)
        new = att.model_copy()
        new.x, new.y, new.path = round(lx, 3), round(ly, 3), img
        sk.set_attachment(name, shape, new)
    for sl in shapes.values():
        sk.slots.remove(sk.slot(sl))
        for skin in sk.skins:
            skin.attachments.pop(sl, None)
    sk.slot(name).attachment = rest or next(iter(shapes))
    return {"slot": name, "shapes": sorted(shapes), "rest": sk.slot(name).attachment}


def _restack(sk: SkeletonData, names: list[str]) -> None:
    """Make ``names`` contiguous, in this order, where the lowest of them was."""
    names = [n for n in names if sk.has_slot(n)]
    if len(names) < 2:
        return
    at = min(sk.slot_index(n) for n in names)
    objs = [sk.slot(n) for n in names]
    for o in objs:
        sk.slots.remove(o)
    sk.slots[at:at] = objs


# ------------------------------------------------------------------------------------------------ geometry helpers
def _alpha_profile(project: Project, slot: str, thr: int = 24):
    """World x of each art column with the world y of its top and bottom opaque pixel (y up: top > bottom)."""
    sk = project.data
    s = sk.slot(slot)
    att = sk.attachment(slot)
    if not isinstance(att, RegionAttachment):
        raise ValueError(f"{slot}: needs a region attachment")
    im = project.image(project.att_image_name(slot, s.attachment))
    W, H = im.size
    a = np.asarray(im)[:, :, 3] > thr
    cols = np.nonzero(a.any(0))[0]
    if len(cols) < 2:
        raise ValueError(f"{slot}: image is (almost) empty")
    top = a[:, cols].argmax(0)
    bot = H - 1 - a[::-1, cols].argmax(0)
    f, _ = region_pixel_to_local(att, W, H)
    wb = sk.world()[s.bone]
    pt = to_world(wb, f(np.c_[cols + 0.5, top.astype(float)]))
    pb = to_world(wb, f(np.c_[cols + 0.5, bot + 1.0]))
    o = np.argsort(pt[:, 0])
    return pt[o, 0], pt[o, 1], pb[o, 1]


def _bbox(project: Project, slot: str) -> tuple[float, float, float, float]:
    h = setup_hull_world(project, slot)
    return float(h[:, 0].min()), float(h[:, 1].min()), float(h[:, 0].max()), float(h[:, 1].max())


def _centre(project: Project, slot: str) -> tuple[float, float]:
    x0, y0, x1, y1 = _bbox(project, slot)
    return (x0 + x1) / 2, (y0 + y1) / 2


def _smoothstep(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


def _smootherstep(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * u * (u * (6 * u - 15) + 10)


# ------------------------------------------------------------------------------------------------ the rig
def rig_face(project: Project, parent: str | None = None, features: dict[str, float] | None = None,
             turn_range: float | None = None, pitch: float = 0.6, clips=CLIPS, talk_text: str = TALK_TEXT,
             seed: int = 7, intensity: float = 1.0, idle_duration: float = 4.0, hair_physics: str = "hair",
             strand_bones: int = 3, spine: str | None = None, fps: float = 30) -> dict:
    """Rig a face from named layers (see FACE_LAYERS) and build its clips.

    parent        bone the face hangs from (the character's head bone); default juice_core or root.
    features      {canonical slot: turn depth} overrides (eye_L_white, brow_L, nose, mouth, ear_L, bangs...).
    turn_range    turn control travel in px (default 25% of the face width).
    clips         which of idle, happy, sad, angry, surprised, talk to build ([] for none).
    spine         an extra body bone for look_at's last level (it lags the head by 2 frames).
    """
    sk = project.data
    if sk.has_bone("face_rig"):
        raise ValueError("this project already has a face rig (bone face_rig)")
    bad = [c for c in (clips or []) if c not in CLIPS]
    if bad:
        raise ValueError(f"unknown clip(s) {bad}; one of {list(CLIPS)}")
    if not 0 <= pitch <= 2:
        raise ValueError("pitch is 0..2 (vertical turn travel relative to horizontal)")
    if intensity <= 0:
        raise ValueError("intensity must be > 0")
    if parent is None:
        parent = "juice_core" if sk.has_bone("juice_core") else "root"
    sk.bone(parent)
    if spine:
        sk.bone(spine)
    found = find_face_parts(sk)
    roles = dict(found["roles"])
    canon = set(roles) | {"mouth"} | {(c if c.startswith("hair") else f"hair_{c}")[:-1] + c[-1].upper()
                                      if re.search(r"_[lr]$", c) else (c if c.startswith("hair") else f"hair_{c}")
                                      for _, c in found["strands"]}
    for k in features or {}:
        if k not in canon and k not in {s.name for s in sk.slots}:
            raise ValueError(f"features: no part {k!r}; canonical names here: {sorted(canon)}")

    # ---- canonical names
    renamed = {}
    for role, sl in list(roles.items()):
        if role == "mouth":
            continue
        new = role if not sk.has_slot(role) or role == sl else sk.unique_name(role, "slot")
        rename_slot(sk, sl, new)
        renamed[sl] = new
        roles[role] = new
    strands = []
    for sl, clean in found["strands"]:
        base = clean if clean.startswith("hair") else f"hair_{clean}"
        base = re.sub(r"_([lr])$", lambda m: "_" + m.group(1).upper(), base)
        new = base if base == sl or not sk.has_slot(base) else sk.unique_name(base, "slot")
        rename_slot(sk, sl, new)
        renamed[sl] = new
        strands.append(new)

    face = roles["face"]
    fx0, fy0, fx1, fy1 = _bbox(project, face)
    fw, fh = fx1 - fx0, fy1 - fy0
    fcx = (fx0 + fx1) / 2
    world = sk.world()
    rig = "face_rig"
    sk.add_bone_world(rig, parent, fcx, fy0, 0, length=round(fh, 2), color="FF66CCFF")
    made: dict = {"bones": [], "constraints": [], "renamed": renamed, "missing": found["missing"],
                  "unrecognised": found["unrecognised"], "skipped": []}

    mouth_info = None
    if found["mouth"]:
        mouth_info = _merge_mouth(project, {k: renamed.get(v, v) for k, v in found["mouth"].items()}, "root")
        roles["mouth"] = mouth_info["slot"]
    elif "mouth" in roles:
        new = "mouth" if not sk.has_slot("mouth") or roles["mouth"] == "mouth" else sk.unique_name("mouth", "slot")
        rename_slot(sk, roles["mouth"], new)
        roles["mouth"] = new
    for S in SIDES:
        _restack(sk, [roles.get(f"eye_{S}_{p}") for p in EYE_PARTS if roles.get(f"eye_{S}_{p}")])

    # ---- turn rig: the base layer
    face_order = sk.slot_index(face)
    feats: dict[str, float] = {}
    for S in SIDES:
        if f"eye_{S}_white" in roles:
            feats[roles[f"eye_{S}_white"]] = DEPTH["eye"]
        elif f"eye_{S}" in roles:
            feats[roles[f"eye_{S}"]] = DEPTH["eye"]
        if f"brow_{S}" in roles:
            feats[roles[f"brow_{S}"]] = DEPTH["brow"]
        if f"ear_{S}" in roles:
            feats[roles[f"ear_{S}"]] = DEPTH["ear"]
    for k in ("nose", "mouth", "hair_back", "bangs"):
        if k in roles:
            feats[roles[k]] = DEPTH[k]
    for st in strands:
        feats[st] = DEPTH["strand_front"] if sk.slot_index(st) > face_order else DEPTH["strand_back"]
    for k, v in (features or {}).items():
        k = renamed.get(k, k)
        if not sk.has_slot(k):
            raise ValueError(f"features: no slot {k!r} (canonical names: {sorted(feats)})")
        feats[k] = float(v)
    turn = turn_rig(project, rig, face, feats, turn_range, pitch, make_test_animation=False)
    ctrl, tspace, tbase = turn["control"], turn["space"], turn["base"]
    sk.bone(tbase).length = turn["range"]
    tbone = {sl: v["bone"] for sl, v in turn["features"].items()}
    face_tc = next(t for t in sk.transform if t.bones == [turn["face"]["driven_bone"]])
    tmx, tmy = face_tc.mixX, (face_tc.mixY if face_tc.mixY is not None else face_tc.mixX)
    made["turn"] = {"control": ctrl, "range": turn["range"], "features": {k: v["mix"] for k, v in turn["features"].items()}}
    world = sk.world()

    def bone(name, par, x, y, rot=0.0, length=0.0, color=None):
        kw = {"color": color} if color else {}
        sk.add_bone_world(name, par, x, y, rot, length, **kw)
        made["bones"].append(name)
        return name

    def tc(bones, target, name, **kw):
        n = add_transform(sk, bones, target, name=name, **{"mix_rotate": 0, "mix_x": 0, "mix_y": 0, **kw})
        made["constraints"].append(n)
        return n

    # ---- drivers: look, smile, jaw
    eye_c = [_centre(project, roles[f"eye_{S}_white"]) for S in SIDES if f"eye_{S}_white" in roles]
    eye_c += [_centre(project, roles[f"eye_{S}"]) for S in SIDES if f"eye_{S}" in roles]
    ex, ey = (np.mean([c[0] for c in eye_c]), np.mean([c[1] for c in eye_c])) if eye_c else (fcx, fy0 + 0.6 * fh)
    R_look = round(0.25 * fw, 2)
    bone("face_look_base", tspace, ex, ey, 0, R_look, "00C8FFFF")
    bone("face_look", "face_look_base", ex, ey, 0, 0, "00C8FFFF")
    if "mouth" in roles:
        mx0, my0, mx1, my1 = _bbox(project, roles["mouth"])
        lip_y = (my0 + my1) / 2 + 0.25 * (my1 - my0)
        mcx = (mx0 + mx1) / 2
    else:
        lip_y, mcx = fy0 + 0.28 * fh, fcx
    smile_px = round(0.045 * fh, 2)
    bone("face_smile_base", tspace, mcx, lip_y, 0, smile_px, "FFB000FF")
    bone("face_smile", "face_smile_base", mcx, lip_y, 0, 0, "FFB000FF")
    bone("face_jaw_base", tspace, mcx, lip_y, 0, round(lip_y - fy0, 2), "FF5050FF")   # screen-aligned: scaleY is vertical
    bone("face_jaw", "face_jaw_base", mcx, lip_y, 0, 0, "FF5050FF")
    bone("face_jaw_turn", "face_jaw", mcx, lip_y, 0, 0)
    tc(["face_jaw_turn"], ctrl, "face_jaw_turn_tc", mix_x=tmx, mix_y=tmy, local=True, relative=True)

    # ---- eyes
    eyes = {}
    for S in SIDES:
        if f"eye_{S}_white" in roles:
            eyes[S] = _build_eye(project, S, {p: roles.get(f"eye_{S}_{p}") for p in EYE_PARTS},
                                 tbone[roles[f"eye_{S}_white"]], R_look, made)
        elif f"eye_{S}" in roles:
            eyes[S] = {"simple": True, "socket": tbone[roles[f"eye_{S}"]]}
            made["skipped"].append(f"eye_{S}: one layer, no look rig (blinks by squash)")
    made["eyes"] = eyes

    # ---- brows
    brows = {}
    for S in SIDES:
        sl = roles.get(f"brow_{S}")
        if not sl:
            continue
        B = sk.slot(sl).bone
        att = sk.attachment(sl)
        im = project.image(project.att_image_name(sl, sk.slot(sl).attachment))
        bcx = _centre(project, sl)[0]
        inner_end = "right" if bcx < fcx else "left"
        cl = strand_centerline(np.asarray(im)[:, :, 3], 3, inner_end)
        f, _ = region_pixel_to_local(att, *im.size)
        pts = to_world(sk.world()[sk.slot(sl).bone], f(cl))
        names = []
        for part, a, b in zip(("inner", "mid", "outer"), pts[:-1], pts[1:]):
            nm = f"brow_{S}_{part}"
            bone(nm, B, a[0], a[1], math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])), math.hypot(*(b - a)), "8B5A2BFF")
            names.append(nm)
        # hat weights along the brow's chord (inner 1 -> 0 at the middle, mid peaks there, outer 0 -> 1): the
        # three bones are control points of a piecewise-linear bend, so a big inner raise cannot crease the brow
        rig_mesh(project, sl, bones=None, detail=0.9, max_vertices=60)
        batt = sk.attachment(sl)
        bw = sk.world()
        bp = mesh_world_vertices(sk, sl, batt, bw)
        ch = pts[-1] - pts[0]
        u = np.clip(((bp - pts[0]) @ ch) / float(ch @ ch), 0, 1)
        Wb = np.c_[np.clip(1 - 2 * u, 0, 1), 1 - np.abs(2 * u - 1), np.clip(2 * u - 1, 0, 1)]
        batt.vertices = skin_vertices(bp, Wb, [sk.bone_index(n) for n in names], [bw[n] for n in names])
        brows[S] = {"slot": sl, "bones": names, "in_sign": 1.0 if inner_end == "right" else -1.0}
    made["brows"] = brows

    # ---- mouth rides the jaw
    if "mouth" in roles:
        ms = roles["mouth"]
        bone("face_mouth", sk.slot(ms).bone, mcx, lip_y, 0, 0)
        reparent_slot(sk, ms, "face_mouth")
        tc(["face_mouth"], "face_jaw", "face_mouth_tc", mix_scale_x=1, mix_scale_y=0.5, local=True, relative=True)
        made["mouth"] = {"slot": ms, "shapes": sorted(sk.skin().attachments.get(ms, {})),
                         "rest": sk.slot(ms).attachment}
    if "jaw" in roles:
        jx, jy = _centre(project, roles["jaw"])
        bone("face_chin", "face_jaw", jx, jy)
        reparent_slot(sk, roles["jaw"], "face_chin")
        tc(["face_chin"], ctrl, "face_chin_tc", mix_x=round(0.7 * tmx, 3), mix_y=round(0.7 * tmy, 3),
           local=True, relative=True)

    # ---- cheeks
    w_now = sk.world()
    att = sk.attachment(face)
    fpts = mesh_world_vertices(sk, face, att, w_now)
    inf = decode_weighted(att.vertices, len(att.uvs) // 2)
    i_rig, i_t = sk.bone_index(rig), sk.bone_index(turn["face"]["driven_bone"])
    wt = np.array([sum(w for bi, *_, w in v if bi == i_t) for v in inf])
    band = 0.05 * fh
    jw = _smoothstep((lip_y + band - fpts[:, 1]) / (2 * band))
    cheeks = {}
    for S in SIDES:
        if f"cheek_{S}" in roles:
            cx, cy = _centre(project, roles[f"cheek_{S}"])
        else:
            src = eyes.get(S, {}).get("centre")
            sgn = -1 if S == "L" else 1
            cx = src[0] if src else fcx + sgn * 0.25 * fw
            cy = (src[1] - 0.55 * (src[1] - lip_y)) if src else fy0 + 0.42 * fh
        g = 0.75 * np.exp(-((fpts[:, 0] - cx) ** 2 + (fpts[:, 1] - cy) ** 2) / (2 * (0.11 * fw) ** 2)) * (1 - jw)
        m = float((g * wt).sum() / max(g.sum(), 1e-9))
        nm = f"cheek_{S}"
        bone(nm, tspace, cx, cy, 0, 0, "FF8FA0FF")
        tc([nm], ctrl, f"cheek_{S}_turn_tc", mix_x=round(m * tmx, 3), mix_y=round(m * tmy, 3), local=True,
           relative=True)
        tc([nm], "face_smile", f"cheek_{S}_smile_tc", mix_y=1, local=True, relative=True)
        tc([nm], "face_jaw", f"cheek_{S}_jaw_tc", mix_scale_x=1, mix_scale_y=0.4, local=True, relative=True)
        if f"cheek_{S}" in roles:
            reparent_slot(sk, roles[f"cheek_{S}"], nm)
        cheeks[S] = {"bone": nm, "weights": g, "turn_mix": round(m, 3)}
    made["cheeks"] = {S: {"bone": v["bone"], "turn_mix": v["turn_mix"]} for S, v in cheeks.items()}

    # ---- face surface: head / turn / jaw / jaw_turn / cheeks
    order = [rig, turn["face"]["driven_bone"], "face_jaw", "face_jaw_turn"] + [cheeks[S]["bone"] for S in cheeks]
    Wm = np.zeros((len(fpts), len(order)))
    csum = sum((cheeks[S]["weights"] for S in cheeks), np.zeros(len(fpts)))
    keep = 1 - jw - csum
    Wm[:, 0] = keep * (1 - wt)
    Wm[:, 1] = keep * wt
    Wm[:, 2] = jw * (1 - wt)
    Wm[:, 3] = jw * wt
    for k, S in enumerate(cheeks):
        Wm[:, 4 + k] = cheeks[S]["weights"]
    Wm = finalize(Wm, min_weight=0.02, max_influences=4)
    w_now = sk.world()
    att.vertices = skin_vertices(fpts, Wm, [sk.bone_index(b) for b in order], [w_now[b] for b in order])
    made["face"] = {"slot": face, "vertices": len(fpts), "jaw_vertices": int((jw > 0.5).sum())}

    # ---- hair
    hair = {"strands": {}, "bangs": None}
    for st in strands:
        try:
            res = rig_strand(project, st, n_bones=strand_bones, parent=tbone[st], physics=hair_physics, detail=0.6)
            hair["strands"][st] = res["bones"]
        except ValueError as e:
            made["skipped"].append(f"{st}: {e}")
    if "bangs" in roles:
        hair["bangs"] = _build_bangs(project, roles["bangs"], tbone[roles["bangs"]], made)
    made["hair"] = hair

    made["slots"] = {k: v for k, v in roles.items()}
    made["clips"] = {}
    for c in clips or []:
        made["clips"][c] = add_face_clip(project, c, seed=seed, intensity=intensity, text=talk_text,
                                         duration=idle_duration if c == "idle" else None, spine=spine, fps=fps)
    made["look_levels"] = face_look_levels(sk, spine)
    made["counts"] = {"bones": len(sk.bones), "slots": len(sk.slots), "transform": len(sk.transform),
                      "ik": len(sk.ik), "physics": len(sk.physics)}
    return made


def _build_eye(project: Project, S: str, parts: dict, socket: str, R_look: float, made: dict) -> dict:
    sk = project.data
    white = parts["white"]
    wx0, wy0, wx1, wy1 = _bbox(project, white)
    W_, H_ = wx1 - wx0, wy1 - wy0
    iris = parts.get("iris") or parts.get("pupil")
    iw, ih = (_bbox(project, iris)[2] - _bbox(project, iris)[0], _bbox(project, iris)[3] - _bbox(project, iris)[1]) \
        if iris else (0.4 * W_, 0.4 * W_)
    rx = round(max((W_ - iw) / 2, 0.12 * W_) * 0.92, 3)
    ry = round(max((H_ - ih) / 2, 0.12 * H_) * 0.92, 3)
    w = sk.world()
    sx, sy = w[socket].x, w[socket].y
    p = f"eye_{S}"

    def bone(name, par, x, y, rot=0.0, length=0.0, color="66CCFFFF"):
        sk.add_bone_world(name, par, x, y, rot, length, color=color)
        made["bones"].append(name)
        return name

    bone(f"{p}_space", socket, sx, sy)
    sk.bone(f"{p}_space").scaleY = round(ry / rx, 5)
    bone(f"{p}_ik", f"{p}_space", sx, sy, 0, rx)
    sk.add_bone(Bone(name=f"{p}_tip", parent=f"{p}_ik", x=rx, color="66CCFFFF"))
    made["bones"].append(f"{p}_tip")
    bone(f"{p}_aim", socket, sx, sy, color="00C8FFFF")
    bone(f"{p}_ball", socket, sx, sy)
    bone(f"{p}_glint", socket, sx, sy)
    gx, gy = LOOK_GAIN * rx / R_look, LOOK_GAIN * ry / R_look
    made["constraints"].append(add_transform(sk, [f"{p}_aim"], "face_look", name=f"{p}_aim_tc", mix_rotate=0,
                                             mix_x=round(gx, 5), mix_y=round(gy, 5), local=True, relative=True))
    ik = add_ik(sk, [f"{p}_ik"], target=f"{p}_aim", name=f"{p}_clamp", bend_positive=True, compress=True)
    made["constraints"].append(ik["constraint"])
    made["constraints"].append(add_transform(sk, [f"{p}_ball"], f"{p}_tip", name=f"{p}_ball_tc", mix_rotate=0,
                                             mix_x=1, mix_y=1))
    made["constraints"].append(add_transform(sk, [f"{p}_glint"], f"{p}_tip", name=f"{p}_glint_tc", mix_rotate=0,
                                             mix_x=0.55, mix_y=0.55))
    if parts.get("iris"):
        reparent_slot(sk, parts["iris"], f"{p}_ball")
    if parts.get("pupil"):
        cx, cy = _centre(project, parts["pupil"])
        bone(f"{p}_pupil", f"{p}_ball", cx, cy)
        reparent_slot(sk, parts["pupil"], f"{p}_pupil")
    if parts.get("highlight"):
        reparent_slot(sk, parts["highlight"], f"{p}_glint")
    xs, top, bot = _alpha_profile(project, white)
    opening = top - bot
    meet = top - UPPER_SHARE * opening
    over = 0.04 * float(opening.max())
    out = {"socket": socket, "space": f"{p}_space", "ellipse": [rx, ry], "centre": [sx, sy], "simple": False,
           "opening": round(float(opening.max()), 3)}
    for which in ("lid_upper", "lid_lower"):
        sl = parts.get(which)
        if not sl:
            made["skipped"].append(f"{p}: no {which}, no blink on that side")
            continue
        reparent_slot(sk, sl, socket)
        lx, lt, lb = _alpha_profile(project, sl)
        rig_mesh(project, sl, bones=None, detail=0.8, max_vertices=60)
        att = sk.attachment(sl)
        w = sk.world()
        pts = mesh_world_vertices(sk, sl, att, w)
        if which == "lid_upper":
            trav_cols = np.interp(xs, lx, lb, left=np.nan, right=np.nan) - meet + over
        else:
            trav_cols = meet + over - np.interp(xs, lx, lt, left=np.nan, right=np.nan)
        trav_cols = np.clip(np.nan_to_num(trav_cols, nan=0.0), 0, None)
        D = float(trav_cols.max())
        if D <= 1e-6:
            made["skipped"].append(f"{p}: {which} does not overlap the white, no blink")
            continue
        frac = np.interp(pts[:, 0], xs, trav_cols / D, left=0.0, right=0.0)
        vt = np.interp(pts[:, 0], lx, lt)
        vb = np.interp(pts[:, 0], lx, lb)
        span = np.maximum(vt - vb, 1e-6)
        u = (vt - pts[:, 1]) / span if which == "lid_upper" else (pts[:, 1] - vb) / span
        wv = frac * np.clip(u / 0.7, 0, 1)
        k = int(np.argmax(trav_cols))
        ex_ = float(xs[k])
        ey_ = float(np.interp(ex_, lx, lb if which == "lid_upper" else lt))
        nm = f"{p}_{which}"
        bone(nm, socket, ex_, ey_, -90 if which == "lid_upper" else 90, round(D, 3), "FFD0A0FF")
        Wm = np.c_[1 - wv, wv]
        w = sk.world()
        att.vertices = skin_vertices(pts, Wm, [sk.bone_index(socket), sk.bone_index(nm)], [w[socket], w[nm]])
        out[which] = {"bone": nm, "travel": round(D, 3), "slot": sl}
        if which == "lid_lower":
            made["constraints"].append(add_transform(sk, [nm], "face_smile", name=f"{nm}_push_tc", mix_rotate=0,
                                                     mix_x=0, mix_y=0.55, local=True, relative=True))
    return out


def _build_bangs(project: Project, slot: str, tb: str, made: dict) -> dict:
    """A separate swing bone hanging from the fringe's top-centre, weighted by height (the root rows stay on the
    head, the tips swing), with physics a little stiffer than the strands so the fringe sways rather than flaps."""
    sk = project.data
    x0, y0, x1, y1 = _bbox(project, slot)
    cx = (x0 + x1) / 2
    nm = "bangs_swing"
    sk.add_bone_world(nm, tb, cx, y1, -90, round(y1 - y0, 2), color="C08040FF")
    made["bones"].append(nm)
    rig_mesh(project, slot, bones=None, detail=0.8, max_vertices=80)
    att = sk.attachment(slot)
    w = sk.world()
    pts = mesh_world_vertices(sk, slot, att, w)
    u = np.clip((y1 - pts[:, 1]) / max(y1 - y0, 1e-6), 0, 1) ** 1.5
    att.vertices = skin_vertices(pts, np.c_[1 - u, u], [sk.bone_index(tb), sk.bone_index(nm)], [w[tb], w[nm]])
    phys = add_physics(sk, [nm], "hair", strength=220, inertia=0.35, damping=0.86, x=0.15)
    made["constraints"] += phys
    return {"bone": nm, "physics": phys}


# ------------------------------------------------------------------------------------------------ rig lookup
def face_info(sk: SkeletonData) -> dict:
    """Everything the clip builders need, read back from the rig's bone names and lengths."""
    if not sk.has_bone("face_rig"):
        raise ValueError("no face rig in this project (run rig_face first)")
    U = sk.bone("face_rig").length / 100.0
    ctrl = next((b.name for b in sk.bones if b.name.startswith("turn_ctrl") and sk.has_bone(b.parent or "")
                 and (b.parent or "").startswith("turn_base") and "face_rig" in _ancestors(sk, b.name)), None)
    info = {"rig": "face_rig", "U": U, "turn": ctrl, "turn_range": sk.bone(sk.bone(ctrl).parent).length if ctrl else 0,
            "look": "face_look" if sk.has_bone("face_look") else None,
            "R_look": sk.bone("face_look_base").length if sk.has_bone("face_look_base") else 0,
            "smile": "face_smile" if sk.has_bone("face_smile") else None, "jaw": "face_jaw" if sk.has_bone("face_jaw") else None,
            "eyes": {}, "brows": {}, "mouth": None, "shapes": {}, "rest": None}
    for S in SIDES:
        p = f"eye_{S}"
        if sk.has_bone(f"{p}_space"):
            e = {"simple": False, "socket": sk.bone(f"{p}_space").parent}
            for which in ("lid_upper", "lid_lower"):
                if sk.has_bone(f"{p}_{which}"):
                    e[which] = {"bone": f"{p}_{which}", "travel": sk.bone(f"{p}_{which}").length}
            if sk.has_bone(f"{p}_pupil"):
                e["pupil"] = f"{p}_pupil"
            info["eyes"][S] = e
        elif sk.has_bone(f"turn_eye_{S}"):
            info["eyes"][S] = {"simple": True, "socket": f"turn_eye_{S}"}
        bs = [f"brow_{S}_{k}" for k in ("inner", "mid", "outer")]
        if all(sk.has_bone(b) for b in bs):
            w = sk.world()
            info["brows"][S] = {"bones": bs, "in_sign": 1.0 if w[bs[0]].x > w[bs[2]].x else -1.0}
    if sk.has_slot("mouth"):
        info["mouth"] = "mouth"
        atts = sk.skin().attachments.get("mouth", {})
        info["shapes"] = {_shape_key(n): n for n in atts}
        info["rest"] = sk.slot("mouth").attachment
    return info


def _ancestors(sk: SkeletonData, name: str) -> list[str]:
    out = []
    b = sk.bone(name)
    while b.parent:
        out.append(b.parent)
        b = sk.bone(b.parent)
    return out


def _shape_key(att_name: str) -> str:
    last = att_name.split("/")[-1].strip()
    return last.upper() if last.upper() in VISEMES else last.lower()


# ------------------------------------------------------------------------------------------------ motion maths
def spring_step(tau, hz: float, zeta: float):
    """Unit step response of a damped spring (0 for tau <= 0). zeta < 1 overshoots by e^(-pi z / sqrt(1 - z^2))."""
    tau = np.asarray(tau, float)
    out = np.zeros_like(tau)
    m = tau > 0
    if hz is None or hz <= 0:
        return (tau >= 0).astype(float)
    w = 2 * math.pi * hz
    t = tau[m]
    if zeta >= 1:
        out[m] = 1 - (1 + w * t) * np.exp(-w * t)
    else:
        wd = w * math.sqrt(1 - zeta * zeta)
        out[m] = 1 - np.exp(-zeta * w * t) * (np.cos(wd * t) + zeta / math.sqrt(1 - zeta * zeta) * np.sin(wd * t))
    return out


def overshoot(zeta: float) -> float:
    return math.exp(-math.pi * zeta / math.sqrt(1 - zeta * zeta)) if zeta < 1 else 0.0


def blink_curve(t, t0: float, down: float = BLINK_DOWN, up: float = BLINK_UP):
    """Lid closure 0..1: quadratic in (accelerating) for ``down`` s, quadratic out (decelerating) for ``up`` s."""
    t = np.asarray(t, float)
    c = np.zeros_like(t)
    a = (t >= t0) & (t < t0 + down)
    c[a] = ((t[a] - t0) / down) ** 2
    b = (t >= t0 + down) & (t < t0 + down + up)
    c[b] = (1 - (t[b] - t0 - down) / up) ** 2
    return c


def poisson_times(rng: np.random.Generator, rate: float, t0: float, t1: float, min_gap: float) -> list[float]:
    """Event times of a Poisson process (exponential gaps, mean 1/rate) in [t0, t1), thinned to ``min_gap``."""
    out: list[float] = []
    t = t0 + rng.exponential(1 / rate)
    while t < t1:
        if not out or t - out[-1] >= min_gap:
            out.append(round(t, 3))
        t += rng.exponential(1 / rate)
    return out


def _dp_keep(ts: np.ndarray, V: np.ndarray, tol: float, rest=None) -> np.ndarray:
    """Douglas-Peucker on a sampled channel; also always keeps the corners where it leaves or returns to rest, so a
    simplified channel never starts moving early."""
    n = len(ts)
    keep = np.zeros(n, bool)
    keep[0] = keep[-1] = True
    if rest is not None:
        at = np.abs(V - np.asarray(rest, float)).max(1) <= 1e-9
        edge = at[:-1] != at[1:]
        keep[:-1] |= edge & at[:-1]
        keep[1:] |= edge & at[1:]
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        u = (ts[i + 1:j] - ts[i]) / max(ts[j] - ts[i], 1e-12)
        lin = V[i] + (V[j] - V[i]) * u[:, None]
        err = np.abs(V[i + 1:j] - lin).max(1)
        k = int(np.argmax(err))
        if err[k] > tol:
            keep[i + 1 + k] = True
            stack += [(i, i + 1 + k), (i + 1 + k, j)]
    return keep


class _Acc:
    """Closed-form channels summed per (bone, timeline) and written as dense LINEAR keys (simplified with a
    Douglas-Peucker pass that keeps every corner and jump)."""
    REST = {"translate": (0.0, 0.0), "rotate": (0.0,), "scale": (1.0, 1.0)}

    def __init__(self, sk: SkeletonData, T: float, fps: float = 30):
        self.sk, self.T = sk, T
        self.ts = set(np.round(np.linspace(0, T, int(round(T * fps)) + 1), 4).tolist())
        self.fns: dict[tuple[str, str], list] = {}

    def at(self, *ts) -> None:
        for t in ts:
            if 0 <= t <= self.T:
                self.ts.add(round(float(t), 4))

    def add(self, bone: str, tl: str, fn) -> None:
        self.sk.bone(bone)
        self.fns.setdefault((bone, tl), []).append(fn)

    def values(self, bone: str, tl: str, ts: np.ndarray) -> np.ndarray:
        rest = np.array(self.REST[tl], float)
        V = np.tile(rest, (len(ts), 1))
        for fn in self.fns.get((bone, tl), []):
            v = np.asarray(fn(ts), float).reshape(len(ts), -1)
            V = V * v if tl == "scale" else V + v
        return V

    def write(self, ab: AnimBuilder) -> dict:
        ts = np.array(sorted(self.ts))
        out = {}
        for (bone, tl) in self.fns:
            V = self.values(bone, tl, ts)
            rest = np.array(self.REST[tl])
            if np.abs(V - rest).max() < 1e-4:
                continue
            amp = float(np.abs(V - rest).max())
            keep = _dp_keep(ts, V, min(0.0006 if tl == "scale" else 0.02, 0.02 * amp), rest)
            pts = [(float(t), *map(float, v)) for t, v, k in zip(ts, V, keep) if k]
            ab.bone(bone, tl, pts, "linear")
            out[f"{bone}/{tl}"] = len(pts)
        return out


# ------------------------------------------------------------------------------------------------ look_at
def face_look_levels(sk: SkeletonData, spine: str | None = None) -> list[dict]:
    """Default eyes -> head (-> spine) levels for a face rig."""
    info = face_info(sk)
    lv = []
    if info["look"]:
        lv.append({"bone": "face_look", "channel": "translate", "range": [info["R_look"], info["R_look"]], "weight": 1.0,
                   "lag": 0.0, "role": "eyes", "limit": 1.3})
    if info["turn"]:
        R = info["turn_range"]
        lv.append({"bone": info["turn"], "channel": "translate", "range": [R, 0.6 * R], "weight": 0.4, "lag": 0.1,
                   "hz": 2.0, "zeta": 0.75, "limit": 1.0})
    if spine:
        lv.append({"bone": spine, "channel": "rotate", "range": [-5.0, 2.0], "weight": 0.15, "lag": 0.1 + 2 / 30,
                   "hz": 1.4, "zeta": 0.85, "limit": 8.0})
    return lv


def _check_levels(sk: SkeletonData, levels: list[dict]) -> list[dict]:
    if not levels:
        raise ValueError("look_at needs at least one level")
    out = []
    for i, L in enumerate(levels):
        L = dict(L)
        if "bone" not in L or not sk.has_bone(L["bone"]):
            raise ValueError(f"level {i}: no bone {L.get('bone')!r}")
        ch = L.setdefault("channel", "rotate" if L.get("role") != "eyes" else "translate")
        if ch not in ("translate", "rotate"):
            raise ValueError(f"level {i}: channel is translate|rotate, not {ch!r}")
        rng_ = L.setdefault("range", [10.0, 10.0] if ch == "translate" else [10.0, 0.0])
        if not (isinstance(rng_, (list, tuple)) and len(rng_) == 2):
            raise ValueError(f"level {i}: range is [x, y] (px for translate, degrees per unit gaze for rotate)")
        if L.setdefault("weight", 1.0) < 0 or L.setdefault("lag", 0.0) < 0:
            raise ValueError(f"level {i}: weight and lag must be >= 0")
        L.setdefault("hz", None if L["lag"] == 0 and L.get("role") == "eyes" else 2.0)
        L.setdefault("zeta", 0.8)
        L.setdefault("limit", None)
        out.append(L)
    return out


def gaze_steps(fixations, T: float, loop: bool):
    """Fixations [(t, gx, gy)] -> (step times, step deltas (n, 2), base value). A loop wraps: the gaze before the
    first fixation is the last one, so the steps of one period sum to zero."""
    fx = sorted((float(f[0]), float(f[1]), float(f[2])) for f in fixations)
    if not fx:
        return np.zeros(0), np.zeros((0, 2)), np.zeros(2)
    if any(t < 0 or t > T + 1e-9 for t, *_ in fx):
        raise ValueError("gaze times must lie inside the clip")
    v = np.array([[g[1], g[2]] for g in fx])
    t = np.array([g[0] for g in fx])
    base = v[-1].copy() if loop else np.zeros(2)
    prev = np.vstack([base[None], v[:-1]])
    return t, v - prev, base


def level_outputs(levels: list[dict], t: np.ndarray, st: np.ndarray, sd: np.ndarray, base: np.ndarray, T: float,
                  loop: bool, counter: bool = True) -> list[np.ndarray]:
    """Normalised output (n, 2) of every level: a non-eye level is weight x the gaze passed through its dead time
    (lag) and a damped spring (hz, zeta); the eye level takes the rest (gaze minus the other levels: the eyes jump
    first, then counter-roll as the head arrives). A loop superposes the steps of four previous periods."""
    if loop:
        st = np.concatenate([st - k * T for k in range(4, -1, -1)])
        sd = np.tile(sd, (5, 1))
    outs = []
    for L in levels:
        if L.get("role") == "eyes":
            outs.append(None)
            continue
        S = spring_step(t[:, None] - st[None, :] - L["lag"], L["hz"], L["zeta"])
        outs.append(L["weight"] * (base[None] + S @ sd))
    gaze = base[None] + (t[:, None] >= st[None, :]).astype(float) @ sd
    for i, L in enumerate(levels):
        if outs[i] is None:
            o = gaze.copy()
            if counter:
                for j, M in enumerate(levels):
                    if outs[j] is not None and j != i:
                        o = o - outs[j]
            outs[i] = L["weight"] * o if not counter else o
    return outs


def _map_level(L: dict, o: np.ndarray) -> np.ndarray:
    rx, ry = L["range"]
    if L["channel"] == "translate":
        o = o.copy()
        if L.get("limit"):
            n = np.hypot(o[:, 0], o[:, 1])
            k = np.where(n > L["limit"], L["limit"] / np.maximum(n, 1e-12), 1.0)
            o *= k[:, None]
        return np.c_[o[:, 0] * rx, o[:, 1] * ry]
    v = o[:, 0] * rx + o[:, 1] * ry
    if L.get("limit"):
        v = np.clip(v, -L["limit"], L["limit"])
    return v[:, None]


def _carrier(sk: SkeletonData, bone: str) -> str:
    """Rotation carrier above a body bone (pure translation at the bone's origin), made once: look_at rotates the
    carrier, so the artist's own keys on the bone still play."""
    b = sk.bone(bone)
    if b.parent is None:
        raise ValueError("the root bone cannot follow a look target")
    if b.parent.startswith(f"look_{bone}"):
        return b.parent
    w = sk.world()[bone]
    nm = sk.unique_name(f"look_{bone}")
    insert_parent(sk, nm, b.parent, [bone], w.x, w.y)
    return nm


def sample_timeline(keys, fields: tuple[str, ...], t: np.ndarray, rest: tuple[float, ...]) -> np.ndarray:
    """Evaluate Spine keys (linear, stepped or absolute bezier curves) at times t -> (n, len(fields))."""
    t = np.asarray(t, float)
    if not keys:
        return np.tile(np.array(rest, float), (len(t), 1))
    kt = np.array([k.time for k in keys])
    kv = np.array([[float(getattr(k, f, None) if getattr(k, f, None) is not None else rest[i])
                    for i, f in enumerate(fields)] for k in keys])
    out = np.zeros((len(t), len(fields)))
    for n, tt in enumerate(t):
        i = int(np.searchsorted(kt, tt, side="right")) - 1
        if i < 0:
            out[n] = kv[0]
            continue
        if i >= len(keys) - 1:
            out[n] = kv[-1]
            continue
        c = keys[i].curve
        t0, t1 = kt[i], kt[i + 1]
        if c == "stepped":
            out[n] = kv[i]
        elif isinstance(c, list):
            for j in range(len(fields)):
                cx1, cy1, cx2, cy2 = c[4 * j: 4 * j + 4]
                lo, hi = 0.0, 1.0
                for _ in range(40):
                    s = (lo + hi) / 2
                    x = (1 - s) ** 3 * t0 + 3 * (1 - s) ** 2 * s * cx1 + 3 * (1 - s) * s * s * cx2 + s ** 3 * t1
                    lo, hi = (s, hi) if x < tt else (lo, s)
                s = (lo + hi) / 2
                out[n, j] = (1 - s) ** 3 * kv[i, j] + 3 * (1 - s) ** 2 * s * cy1 + 3 * (1 - s) * s * s * cy2 + s ** 3 * kv[i + 1, j]
        else:
            u = (tt - t0) / max(t1 - t0, 1e-12)
            out[n] = kv[i] + (kv[i + 1] - kv[i]) * u
    return out


def look_at(project: Project, animation: str, levels: list[dict] | None = None, gaze: list | None = None,
            target: str | None = None, target_range: float | None = None, duration: float | None = None,
            loop: bool | None = None, fps: float = 30, counter: bool = True, spine: str | None = None,
            carrier: bool = True) -> dict:
    """Bake a lagged look chain (eyes -> head -> spine, or any bones) into ``animation``.

    gaze      fixations [[t, gx, gy], ...] in normalised gaze units (-1..1; +x = viewer's right, +y = up). Saccades
              are instant. Or:
    target    a bone whose translate keys in ``animation`` ARE the gaze (divided by ``target_range``, default the
              length of the target's parent: face_look_base on a face rig).
    levels    [{bone, channel: translate|rotate, range: [x, y], weight, lag (s), hz, zeta, limit, role: "eyes"}];
              default: face_look_levels (eyes 1.0 instant; turn_ctrl 0.4 after 100 ms; ``spine`` 0.15 two frames later).
              The eye level gets gaze minus every other level (counter-roll) unless counter=False. Rotate levels on
              body bones go through an inserted carrier bone (carrier=False keys the bone itself).
    """
    sk = project.data
    if levels is None:
        levels = face_look_levels(sk, spine)
    levels = _check_levels(sk, levels)
    an = sk.animations.get(animation)
    if loop is None:
        loop = False
    if gaze is None and target is None:
        raise ValueError("give gaze=[[t, gx, gy], ...] or target=<bone with translate keys in the animation>")
    if gaze is not None:
        if not gaze:
            raise ValueError("gaze is empty")
        T = duration or (an.duration() if an and an.duration() > 0 else max(float(g[0]) for g in gaze) + 1.0)
        st, sd, base = gaze_steps(gaze, T, loop)
    else:
        sk.bone(target)
        ks = (an.bones.get(target, {}).get("translate") if an else None) or []
        if not ks:
            raise ValueError(f"target {target!r} has no translate keys in {animation!r}")
        R = target_range or (sk.bone(sk.bone(target).parent).length if sk.bone(target).parent else 0) or 100.0
        T = duration or an.duration()
        fine = np.linspace(0, T, int(round(T * 240)) + 1)
        g = sample_timeline(ks, ("x", "y"), fine, (0.0, 0.0)) / R
        base = g[-1] if loop else g[0]
        st = fine
        sd = np.diff(np.vstack([base[None], g]), axis=0)
    if T <= 0:
        raise ValueError("duration must be > 0")
    grid = set(np.round(np.linspace(0, T, int(round(T * fps)) + 1), 4).tolist())
    if gaze is not None:
        for tk in st:
            for d in (-0.001, 0.0):
                if 0 <= tk + d <= T:
                    grid.add(round(float(tk + d), 4))
        for L in levels:
            for tk in st:
                if 0 <= tk + L["lag"] <= T:
                    grid.add(round(float(tk + L["lag"]), 4))
    ts = np.array(sorted(grid))
    outs = level_outputs(levels, ts, st, sd, base, T, loop, counter)
    ab = AnimBuilder(sk, animation, replace=False)
    res = {"animation": animation, "duration": round(T, 4), "levels": []}
    for L, o in zip(levels, outs):
        V = _map_level(L, o)
        if loop:
            V[-1] = V[0]
        b = L["bone"]
        if L["channel"] == "rotate" and carrier and not b.startswith(("face_", "turn_", "look_", "eye_", "brow_")):
            b = _carrier(sk, b)
        keep = _dp_keep(ts, V, min(0.01, 0.02 * float(np.abs(V).max())), np.zeros(V.shape[1]))
        pts = [(float(t), *map(float, v)) for t, v, k in zip(ts, V, keep) if k]
        ab.bone(b, L["channel"], pts, "linear")
        res["levels"].append({"bone": b, "channel": L["channel"], "keys": len(pts), "lag": L["lag"],
                              "weight": L["weight"], "max": round(float(np.abs(V).max()), 3)})
    return res


# ------------------------------------------------------------------------------------------------ lipsync
ARPABET = {"AA": "A", "AE": "A", "AH": "A", "AO": "O", "AW": "O", "AY": "A", "B": "M", "CH": "E", "D": "L",
           "DH": "L", "EH": "E", "ER": "U", "EY": "E", "F": "F", "G": "E", "HH": "E", "IH": "I", "IY": "I",
           "JH": "E", "K": "E", "L": "L", "M": "M", "N": "L", "NG": "E", "OW": "O", "OY": "O", "P": "M", "R": "U",
           "S": "E", "SH": "E", "T": "L", "TH": "L", "UH": "U", "UW": "U", "V": "F", "W": "U", "Y": "I", "Z": "E",
           "ZH": "E"}
ARPA_VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"}
PAUSES = {"rest", "sil", "sp", "_", ".", ",", "pau", "-"}
JAW_OF = {"A": 1.0, "E": 0.5, "I": 0.35, "O": 0.8, "U": 0.4, "M": 0.0, "F": 0.15, "L": 0.55, "rest": 0.0}
FALLBACK = {"A": ["O", "E"], "E": ["I", "A"], "I": ["E", "A"], "O": ["U", "A"], "U": ["O", "M"], "M": ["rest", "closed"],
            "F": ["M", "E"], "L": ["E", "A"], "rest": ["M", "closed"]}
# a tiny English grapheme -> viseme table: digraphs first, then letters (vowel flag drives timing)
G2P_DIGRAPHS = [("tch", "E", 0), ("sch", "E", 0), ("ch", "E", 0), ("sh", "E", 0), ("th", "L", 0), ("ph", "F", 0),
                ("wh", "U", 0), ("ck", "E", 0), ("ng", "E", 0), ("qu", "U", 0), ("ee", "I", 1), ("ea", "I", 1),
                ("ie", "I", 1), ("oo", "U", 1), ("ou", "O", 1), ("ow", "O", 1), ("oa", "O", 1), ("aw", "O", 1),
                ("au", "O", 1), ("oi", "O", 1), ("oy", "O", 1), ("ai", "A", 1), ("ay", "A", 1), ("ey", "E", 1),
                ("ei", "E", 1)]
G2P_LETTERS = {"a": ("A", 1), "e": ("E", 1), "i": ("I", 1), "o": ("O", 1), "u": ("U", 1), "y": ("I", 1),
               "b": ("M", 0), "m": ("M", 0), "p": ("M", 0), "f": ("F", 0), "v": ("F", 0), "l": ("L", 0),
               "t": ("L", 0), "d": ("L", 0), "n": ("L", 0), "w": ("U", 0), "q": ("U", 0), "r": ("E", 0),
               "c": ("E", 0), "g": ("E", 0), "h": ("E", 0), "j": ("E", 0), "k": ("E", 0), "s": ("E", 0),
               "x": ("E", 0), "z": ("E", 0)}
PUNCT_PAUSE = {",": 0.22, ";": 0.3, ":": 0.3, ".": 0.4, "!": 0.4, "?": 0.4}


def g2p(word: str) -> list[tuple[str, bool]]:
    """Graphemes -> [(viseme, is_vowel)], repeated visemes merged, a silent final e dropped."""
    w = re.sub(r"[^a-z]", "", word.lower())
    if len(w) >= 3 and w.endswith("e") and w[-2] not in "aeiouy" and not w.endswith("le"):
        w = w[:-1]
    out: list[tuple[str, bool]] = []
    i = 0
    while i < len(w):
        for dg, v, vow in G2P_DIGRAPHS:
            if w.startswith(dg, i):
                out.append((v, bool(vow)))
                i += len(dg)
                break
        else:
            v, vow = G2P_LETTERS.get(w[i], ("E", 0))
            out.append((v, bool(vow)))
            i += 1
    merged: list[tuple[str, bool]] = []
    for v, vow in out:
        if merged and merged[-1][0] == v:
            merged[-1] = (v, merged[-1][1] or vow)
        else:
            merged.append((v, vow))
    return merged


def speech_schedule(text: str | None = None, phonemes: list | None = None, wpm: float = 150,
                    durations: dict | None = None) -> list[dict]:
    """[{t, dur, viseme, word}] from text (word length = 60/wpm s, vowels 1.6x a consonant, punctuation pauses) or
    from phonemes (ARPAbet like HH AH0 L OW1, viseme letters, or rest/sil; items may be [phoneme, seconds])."""
    if (text is None) == (phonemes is None):
        raise ValueError("give exactly one of text= or phonemes=")
    if wpm <= 0:
        raise ValueError("wpm must be > 0")
    sched: list[dict] = []
    t = 0.0
    if text is not None:
        toks = re.findall(r"[A-Za-z']+|[,;:.!?]", text)
        if not any(re.match(r"[A-Za-z]", k) for k in toks):
            raise ValueError("text has no words")
        wd = 60.0 / wpm
        for tok in toks:
            if tok in PUNCT_PAUSE:
                sched.append({"t": t, "dur": PUNCT_PAUSE[tok], "viseme": "rest", "word": None})
                t += PUNCT_PAUSE[tok]
                continue
            ph = g2p(tok) or [("E", True)]
            wts = np.array([1.6 if v else 1.0 for _, v in ph])
            ds = wd * wts / wts.sum()
            ds = np.maximum(ds, 0.05)
            for k, ((v, _), d) in enumerate(zip(ph, ds)):
                sched.append({"t": t, "dur": float(d), "viseme": v, "word": tok if k == 0 else None})
                t += float(d)
    else:
        if not phonemes:
            raise ValueError("phonemes is empty")
        for item in phonemes:
            name, d = (item[0], float(item[1])) if isinstance(item, (list, tuple)) else (item, None)
            raw = str(name).strip()
            key = re.sub(r"\d", "", raw).upper()
            if raw.lower() in PAUSES:
                v, vow = "rest", False
            elif key in ARPABET:
                v, vow = ARPABET[key], key in ARPA_VOWELS
            elif key in VISEMES:
                v, vow = key, key in "AEIOU"
            else:
                raise ValueError(f"unknown phoneme {raw!r}: use ARPAbet (HH, AH0, L, OW1...), a viseme (A E I O U M F L) "
                                 "or rest/sil")
            if d is None:
                d = (durations or {}).get(v, 0.2 if v == "rest" else (0.12 if vow else 0.08))
            if d <= 0:
                raise ValueError(f"phoneme {raw!r} needs a positive duration")
            sched.append({"t": t, "dur": d, "viseme": v, "word": None})
            t += d
    return sched


def _viseme_atts(sk: SkeletonData, slot: str) -> dict[str, str]:
    return {_shape_key(n): n for n in sk.skin().attachments.get(slot, {})}


def _pick(shapes: dict[str, str], v: str) -> str | None:
    if v in shapes:
        return shapes[v]
    for alt in FALLBACK.get(v, []):
        if alt in shapes:
            return shapes[alt]
    return None


def lipsync(project: Project, text: str | None = None, phonemes: list | None = None, animation: str = "talk",
            start: float = 0.0, wpm: float = 150, mouth_slot: str | None = None, jaw_bone: str | None = None,
            lead: float = 1 / 30, events: bool = True, replace: bool = False, durations: dict | None = None,
            jaw_amount: float = 1.0) -> dict:
    """Visemes (stepped attachment keys, ``lead`` s ahead of the sound, as animators do) and an eased jaw into
    ``animation``. The mouth slot's attachments are matched by name (A E I O U M F L, rest; case-insensitive, any
    path prefix); a missing viseme falls back to its nearest shape. The jaw opens by scale (scaleY up, scaleX =
    scaleY^-1/2), keyed mid-phoneme with sine in-out. Ends on the rest shape with the jaw closed.
    Events: sfx_talk at the start, talk_word (string = the word) at every word, talk_end at the end."""
    sk = project.data
    if start < 0:
        raise ValueError("start must be >= 0")
    mouth_slot = mouth_slot or ("mouth" if sk.has_slot("mouth") else None)
    if mouth_slot is None:
        cand = [s.name for s in sk.slots if sum(_shape_key(n) in VISEMES for n in sk.skin().attachments.get(s.name, {})) >= 2]
        mouth_slot = cand[0] if cand else None
    if mouth_slot is not None:
        sk.slot(mouth_slot)
    if jaw_bone is None and sk.has_bone("face_jaw"):
        jaw_bone = "face_jaw"
    if jaw_bone is not None:
        sk.bone(jaw_bone)
    if mouth_slot is None and jaw_bone is None:
        raise ValueError("no mouth slot with viseme attachments and no jaw bone: nothing to lipsync")
    sched = speech_schedule(text, phonemes, wpm, durations)
    shapes = _viseme_atts(sk, mouth_slot) if mouth_slot else {}
    rest_att = (sk.slot(mouth_slot).attachment if mouth_slot else None)
    end = start + sched[-1]["t"] + sched[-1]["dur"]
    ab = AnimBuilder(sk, animation, replace=replace)
    if shapes:
        keys, last = [(start, rest_att)], rest_att
        for ph in sched:
            att = rest_att if ph["viseme"] == "rest" else (_pick(shapes, ph["viseme"]) or rest_att)
            tk = max(start, start + ph["t"] - lead)
            if att != last:
                keys = [k for k in keys if abs(k[0] - tk) > 1e-6] + [(tk, att)]
                last = att
        if last != rest_att:
            keys.append((max(end - lead, keys[-1][0] + 1e-3), rest_att))
        ab.slot_attachment(mouth_slot, [(round(t, 4), a) for t, a in keys])
    if jaw_bone:
        pts = [(start, 1.0, 1.0)]
        for ph in sched:
            o = JAW_OF.get(ph["viseme"], 0.3) * jaw_amount
            sy = 1 + JAW_OPEN * o
            tk = start + ph["t"] + 0.4 * ph["dur"]
            if tk > pts[-1][0] + 1e-3:
                pts.append((tk, sy ** -0.5, sy))
        pts.append((max(end, pts[-1][0] + 0.05), 1.0, 1.0))
        ab.bone(jaw_bone, "scale", pts, "sine_in_out")
    if events:
        ab.event(start, "sfx_talk", string=(text or " ".join(map(str, phonemes)))[:60])
        for ph in sched:
            if ph["word"]:
                ab.event(start + ph["t"], "talk_word", string=ph["word"])
        ab.event(end, "talk_end")
    return {"animation": animation, "start": start, "end": round(end, 4), "phonemes": len(sched),
            "visemes": [p["viseme"] for p in sched], "words": sum(1 for p in sched if p["word"]),
            "mouth_slot": mouth_slot, "jaw_bone": jaw_bone, "schedule": sched}


# ------------------------------------------------------------------------------------------------ expression clips
# brows: {part: (inward, up)} in % of face height; lids: (upper, lower) closure; smile/jaw 0..1; pupil scale;
# gaze/head in normalised gaze / turn units; tilt degrees; squash = stretch amplitude (sy - 1) at full envelope
EXPRESSIONS: dict[str, dict] = {
    "happy": dict(duration=1.8, anticipation=0, hz=2.4, zeta=0.45,
                  brows={"inner": (0.0, 2.2), "mid": (0.0, 2.6), "outer": (0.0, 1.6)}, lids=(0.12, 0.3), smile=1.0,
                  jaw=0.18, pupil=1.12, gaze=(0.0, 0.12), head=(0.0, 0.25), tilt=6.0, squash=0.035, squash_zeta=0.3,
                  mouth=["smile", "E", "A"]),
    "sad": dict(duration=2.0, anticipation=0, hz=1.6, zeta=0.7,
                brows={"inner": (0.8, 4.6), "mid": (0.2, 1.6), "outer": (0.0, -1.4)}, lids=(0.38, 0.0), smile=-0.35,
                jaw=0.0, pupil=1.08, gaze=(-0.2, -0.55), head=(-0.1, -0.5), tilt=-5.0, squash=-0.03, squash_zeta=0.8,
                mouth=["frown", "U", "M"]),
    "angry": dict(duration=1.8, anticipation=0, hz=3.0, zeta=0.5,
                  brows={"inner": (1.6, -3.6), "mid": (0.4, -1.4), "outer": (0.0, 1.2)}, lids=(0.28, 0.32), smile=0.35,
                  jaw=0.08, pupil=0.8, gaze=(0.0, -0.12), head=(0.0, -0.35), tilt=0.0, squash=-0.02, squash_zeta=0.6,
                  shake=(2.5, 7.0, 4.0), mouth=["E", "I", "M"]),
    "surprised": dict(duration=1.8, anticipation=2, hz=2.6, zeta=0.45,
                      brows={"inner": (0.0, 5.2), "mid": (0.0, 5.8), "outer": (0.0, 4.4)}, lids=(-0.12, -0.12),
                      eye_pop=0.1, smile=-0.2, jaw=0.8, pupil=0.68, gaze=(0.0, 0.1), head=(0.0, 0.3), tilt=0.0,
                      squash=0.08, squash_zeta=0.32, anti_squash=0.1, mouth=["O", "A"]),
}


def add_face_clip(project: Project, clip: str, duration: float | None = None, intensity: float = 1.0, seed: int = 7,
                  text: str | None = None, phonemes: list | None = None, wpm: float = 150, name: str | None = None,
                  spine: str | None = None, fps: float = 30) -> dict:
    """(Re)build one face clip: idle | happy | sad | angry | surprised | talk (see the module docstring)."""
    sk = project.data
    if clip not in CLIPS:
        raise ValueError(f"unknown face clip {clip!r}; one of {list(CLIPS)}")
    if intensity <= 0:
        raise ValueError("intensity must be > 0")
    if duration is not None and duration <= 0.5:
        raise ValueError("duration must be > 0.5 s")
    info = face_info(sk)
    nm = name or clip
    if clip == "idle":
        return _idle(project, info, nm, duration or 4.0, intensity, seed, spine, fps)
    if clip == "talk":
        return _talk(project, info, nm, text if (text or phonemes is None) else None, phonemes, wpm, intensity, seed,
                     fps, text_default=TALK_TEXT)
    return _expression(project, info, nm, clip, EXPRESSIONS[clip], duration, intensity, spine, fps)


def _blink_into(acc: _Acc, info: dict, t0s: list[float], closure_base=None) -> None:
    """Lids: closure = base + (1 - base) * blink, upper lid -travel x closure, lower +travel x closure."""
    for t0 in t0s:
        acc.at(t0, t0 + BLINK_DOWN / 2, t0 + BLINK_DOWN, t0 + BLINK_DOWN + BLINK_UP / 3,
               t0 + BLINK_DOWN + 2 * BLINK_UP / 3, t0 + BLINK_DOWN + BLINK_UP)

    def blink(t):
        return np.clip(sum((blink_curve(t, t0) for t0 in t0s), np.zeros_like(np.asarray(t, float))), 0, 1)

    for S, e in info["eyes"].items():
        if e["simple"]:
            acc.add(e["socket"], "scale", lambda t: np.c_[np.ones(len(t)), 1 - 0.9 * blink(t)])
            continue
        for which, sign in (("lid_upper", -1.0), ("lid_lower", 1.0)):
            if which not in e:
                continue
            D = e[which]["travel"]
            base = (closure_base or {}).get(which)

            def fn(t, D=D, sign=sign, base=base):
                b = blink(t)
                c0 = base(t) if base is not None else 0.0
                c = c0 + (1 - np.clip(c0, None, 1)) * b if base is not None else b
                return np.c_[np.zeros(len(t)), sign * D * c]
            acc.add(e[which]["bone"], "translate", fn)


def _look_into(acc: _Acc, sk, levels: list[dict], st, sd, base, T: float, loop: bool, ramp=None) -> None:
    for i, L in enumerate(levels):
        def fn(t, i=i, L=L):
            outs = level_outputs(levels, np.asarray(t, float), st, sd, base, T, loop)
            V = _map_level(L, outs[i])
            if ramp is not None:
                V = V * ramp(t)[:, None]
            return V
        b = L["bone"]
        if L["channel"] == "rotate" and not b.startswith(("face_", "turn_", "look_", "eye_", "brow_")):
            b = _carrier(sk, b)
        acc.add(b, L["channel"], fn)
    for tk in st:
        for d in (-0.001, 0.0):
            acc.at(tk + d)
        for L in levels:
            acc.at(tk + L["lag"])


def _idle(project: Project, info: dict, name: str, T: float, I: float, seed: int, spine, fps) -> dict:
    sk = project.data
    rng = np.random.default_rng(seed)
    ab = AnimBuilder(sk, name)
    acc = _Acc(sk, T, fps)
    U, fh = info["U"], info["U"] * 100
    n = max(1, int(round(T / 3.8)))
    breath = lambda t: 0.5 - 0.5 * np.cos(2 * np.pi * n * np.asarray(t) / T)  # noqa: E731
    acc.add("face_rig", "scale", lambda t: np.c_[(1 + 0.008 * I * breath(t)) ** -0.5, 1 + 0.008 * I * breath(t)])
    acc.add("face_rig", "translate", lambda t: np.c_[np.zeros(len(t)), 0.0035 * I * fh * breath(t)])
    for S, b in info["brows"].items():
        for bn in b["bones"]:
            acc.add(bn, "translate", lambda t: np.c_[np.zeros(len(t)), 0.25 * U * I * breath(t)])
    # micro-saccades: a seeded Poisson timer, small fixations with an occasional glance
    sac = poisson_times(rng, 1.6, 0.2, T - 0.15, 0.28)
    fix = []
    for t in sac:
        if rng.random() < 0.25:
            g = (rng.uniform(-0.45, 0.45), rng.uniform(-0.15, 0.15))
        else:
            g = tuple(np.clip(rng.normal(0, 0.1, 2), -0.25, 0.25))
        fix.append((t, g[0] * I, g[1] * I))
    if info["look"] or info["turn"]:
        levels = face_look_levels(sk, spine)
        for L in levels:
            if L.get("role") != "eyes":
                L["weight"] *= 0.75
        if fix:
            st, sd, base = gaze_steps(fix, T, True)
            _look_into(acc, sk, levels, st, sd, base, T, True)
    blinks = poisson_times(rng, 0.32, 0.15, T - BLINK_DOWN - BLINK_UP - 0.05, 1.0) or [round(0.55 * T, 3)]
    _blink_into(acc, info, blinks)
    for t0 in blinks:
        ab.event(t0, "sfx_blink")
    keys = acc.write(ab)
    _close_loop(sk.animations[name], T)
    return {"animation": name, "duration": T, "loop": True, "blinks": blinks, "saccades": [f[0] for f in fix],
            "timelines": len(keys), "events": ["sfx_blink"]}


def _close_loop(a, T: float) -> None:
    """Exact loop: every timeline's key at T equals its key at 0 (closed-form periodic channels already do, to the
    rounding of the key values; this removes the rounding)."""
    for tls in a.bones.values():
        for ks in tls.values():
            if len(ks) >= 2 and abs(ks[0].time) < 1e-9 and abs(ks[-1].time - T) < 1e-6:
                for f in ("x", "y", "value"):
                    if hasattr(ks[0], f) or hasattr(ks[-1], f):
                        setattr(ks[-1], f, getattr(ks[0], f, None) if getattr(ks[0], f, None) is not None else 0.0)


def _env(t, ta, tr, rel, hz, zeta):
    return spring_step(np.asarray(t, float) - ta, hz, zeta) * (1 - _smootherstep((np.asarray(t, float) - tr) / rel))


def _expression(project: Project, info: dict, name: str, clip: str, X: dict, duration, I: float, spine, fps) -> dict:
    sk = project.data
    f = 1.0 / fps
    D = duration or X["duration"]
    anti = X.get("anticipation", 0) * f
    t0 = 2 * f                       # the first motion (brows run a frame ahead of it)
    ta = t0 + anti                   # the attack (after any anticipation)
    rel = min(0.45, 0.3 * D)
    tr = D - rel - 0.05              # the release starts; everything reaches rest at D - 0.05
    if tr <= ta + 0.25:
        raise ValueError(f"{clip}: duration {D} s is too short (needs > {ta + 0.25 + rel + 0.05:.2f} s)")
    hz, z = X["hz"], X["zeta"]
    U, fh = info["U"], info["U"] * 100
    e = lambda t: _env(t, ta, tr, rel, hz, z)  # noqa: E731
    eb = lambda t: _env(np.asarray(t) + f, ta, tr, rel, hz, z)  # noqa: E731  brows lead by one frame
    ramp = lambda t: 1 - _smootherstep((np.asarray(t, float) - tr) / rel)  # noqa: E731
    ab = AnimBuilder(sk, name)
    acc = _Acc(sk, D, fps)
    acc.at(t0 - f, t0, ta - f, ta, tr - f, tr, tr + rel - f, tr + rel, D)
    # brows (with an anticipation dip that also leads by a frame)
    adip = lambda t: _smootherstep((np.asarray(t, float) + f - t0) / max(anti, 1e-9)) * (1 - spring_step(np.asarray(t, float) + f - ta, 4.0, 1.0)) * ramp(np.asarray(t, float) + f) if anti else 0 * np.asarray(t, float)  # noqa: E731
    for S, b in info["brows"].items():
        for part, bn in zip(("inner", "mid", "outer"), b["bones"]):
            din, dup = X["brows"][part]
            acc.add(bn, "translate", lambda t, din=din, dup=dup, s=b["in_sign"]:
                    np.c_[s * din * U * I * eb(t), dup * U * I * eb(t) - 0.6 * U * I * adip(t)])
    # lids (squint / droop / wide) and eye pop
    lu, ll = X["lids"]
    _blink_into(acc, info, [], closure_base={"lid_upper": lambda t: lu * I * e(t), "lid_lower": lambda t: ll * I * e(t)})
    if X.get("eye_pop"):
        for S, ev in info["eyes"].items():
            acc.add(ev["socket"], "scale", lambda t: np.c_[1 + X["eye_pop"] * I * e(t), 1 + X["eye_pop"] * I * e(t)])
    for S, ev in info["eyes"].items():
        if ev.get("pupil"):
            acc.add(ev["pupil"], "scale", lambda t: np.c_[1 + (X["pupil"] - 1) * e(t), 1 + (X["pupil"] - 1) * e(t)])
    if info["smile"]:
        acc.add("face_smile", "translate", lambda t: np.c_[np.zeros(len(t)), X["smile"] * I * sk.bone("face_smile_base").length * e(t)])
    if info["jaw"] and X["jaw"]:
        def jaw(t):
            sy = 1 + JAW_OPEN * X["jaw"] * I * e(t)
            return np.c_[sy ** -0.5, sy]
        acc.add("face_jaw", "scale", jaw)
    # the whole face: tilt, squash & stretch (volume kept: sx = sy^-1/2), anticipation, shake
    sq = lambda t: _env(t, ta, tr, rel, hz, X.get("squash_zeta", z))  # noqa: E731
    asq = X.get("anti_squash", 0.0)

    def face_scale(t):
        t = np.asarray(t, float)
        if anti:   # squash for `anti` s, then a fast loose spring from the squash into the stretch (overshoot)
            fast = spring_step(t - ta, X.get("squash_hz", 5.0), X.get("squash_zeta", z))
            sy = np.where(t < ta, 1 - asq * I * _smoothstep((t - t0) / anti),
                          1 + (-asq * I + (asq + X["squash"]) * I * fast) * ramp(t))
        else:
            sy = 1 + X["squash"] * I * sq(t)
        return np.c_[sy ** -0.5, sy]
    acc.add("face_rig", "scale", face_scale)
    if anti:
        acc.at(t0 + f, t0 + 2 * f)

    def face_rot(t):
        t = np.asarray(t, float)
        v = X["tilt"] * I * e(t)
        if X.get("shake"):
            A, F, k = X["shake"]
            tau = t - ta
            v = v + np.where(tau > 0, A * I * np.exp(-k * tau) * np.sin(2 * np.pi * F * tau), 0.0) * ramp(t)
        return v[:, None]
    acc.add("face_rig", "rotate", face_rot)
    if info["turn"]:
        R = info["turn_range"]
        acc.add(info["turn"], "translate", lambda t: np.c_[X["head"][0] * R * I * e(t), X["head"][1] * 0.6 * R * I * e(t)])
    # gaze through look_at: eyes jump at the attack, the head follows, everything back for the release
    if info["look"] or info["turn"]:
        levels = face_look_levels(sk, spine)
        st, sd, base = gaze_steps([(ta, X["gaze"][0] * I, X["gaze"][1] * I), (tr, 0.0, 0.0)], D, False)
        _look_into(acc, sk, levels, st, sd, base, D, False, ramp=ramp)
    # the mouth shape switches when the envelope passes 0.3 (stepped, as visemes are)
    if info["mouth"]:
        shape = next((info["shapes"][m] for m in X["mouth"] if m in info["shapes"]), None)
        if shape:
            ts = np.linspace(0, D, int(round(D * 240)) + 1)
            on = e(ts) > 0.3
            if not on.any():
                on[len(on) // 2] = True
            t_on = float(ts[np.argmax(on)])
            t_off = float(ts[len(on) - 1 - np.argmax(on[::-1])])
            ab.slot_attachment("mouth", [(0, info["rest"]), (round(t_on, 4), shape), (round(t_off, 4), info["rest"])])
    ab.event(ta, f"sfx_{clip}")
    keys = acc.write(ab)
    return {"animation": name, "duration": D, "attack": round(ta, 4), "release": round(tr, 4), "timelines": len(keys),
            "overshoot": round(overshoot(z), 4), "events": [f"sfx_{clip}"]}


def _talk(project: Project, info: dict, name: str, text, phonemes, wpm, I, seed, fps, text_default) -> dict:
    sk = project.data
    if text is None and phonemes is None:
        text = text_default
    f = 1.0 / fps
    start = 0.15
    sched = speech_schedule(text, phonemes, wpm)
    end = start + sched[-1]["t"] + sched[-1]["dur"]
    D = round(end + 0.35, 4)
    ab = AnimBuilder(sk, name)
    acc = _Acc(sk, D, fps)
    U = info["U"]
    words = [start + p["t"] for p in sched if p["word"] and len(g2p(p["word"])) >= 2]
    stressed = [w for k, w in enumerate(words) if k % 2 == 0 or k == len(words) - 1]
    tau_p = 0.12
    tail0 = end
    ramp = lambda t: 1 - _smootherstep((np.asarray(t, float) - tail0) / 0.3)  # noqa: E731

    def pulse(t, lead=0.0):
        t = np.asarray(t, float) + lead
        out = np.zeros_like(t)
        for w in stressed:
            tau = np.clip(t - w, 0, None)
            out += (tau / tau_p) * np.exp(1 - tau / tau_p)
        return out * ramp(np.asarray(t, float) - lead)
    for S, b in info["brows"].items():
        for part, bn in zip(("inner", "mid", "outer"), b["bones"]):
            k = {"inner": 1.4, "mid": 1.1, "outer": 0.8}[part]
            acc.add(bn, "translate", lambda t, k=k: np.c_[np.zeros(len(t)), 1.2 * k * U * I * pulse(t, f)])
    if info["turn"]:
        R = info["turn_range"]
        acc.add(info["turn"], "translate", lambda t: np.c_[np.zeros(len(t)), -0.08 * R * I * pulse(t)])
    acc.add("face_rig", "rotate", lambda t: (1.2 * I * np.sin(2 * np.pi * np.asarray(t) / D) *
                                             _smootherstep(np.asarray(t) / 0.3) * ramp(t))[:, None])
    for w in stressed:
        acc.at(w - f, w, w + tau_p)
    rng = np.random.default_rng(seed + 101)
    blinks = poisson_times(rng, 0.3, 0.4, D - 0.4, 1.2) or [round(0.5 * D, 3)]
    _blink_into(acc, info, blinks)
    for t0 in blinks:
        ab.event(t0, "sfx_blink")
    acc.write(ab)
    res = lipsync(project, text=text, phonemes=phonemes, animation=name, start=start, wpm=wpm, jaw_amount=I,
                  replace=False)
    res.pop("schedule", None)
    res.update({"duration": D, "blinks": blinks, "stressed_words": len(stressed)})
    return res


# ------------------------------------------------------------------------------------------------ procedural sample
def _canvas(W, H, s):
    im = Image.new("RGBA", (W * s, H * s), (0, 0, 0, 0))
    return im, ImageDraw.Draw(im)


def make_sample_face(out_dir: str | Path, name: str = "face") -> Project:
    """A 520x640 mascot head drawn as separate layers named exactly as import_psd names a PSD that follows the
    convention (face/head, face/eye_L/white..., face/mouth/A..., hair/bangs...), all on root like an import with
    origin=bottom: shoulders, back hair, ears, face, cheeks, chin, nose, ten mouth shapes, two six-part eyes, brows,
    two side strands and bangs."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    W, H, s = 520, 640, 3
    sk = new_skeleton(width=W, height=H)
    p = Project(out / f"{name}.json", sk)
    skin, skin_line = (255, 216, 186), (196, 128, 106)
    hair, hair_dark = (112, 62, 44), (62, 32, 22)
    layers: list[tuple[str, Image.Image]] = []

    def S(v):
        return v * s

    def poly(cx, cy, a, b_top, b_bot, chin=0.0, n=120):
        pts = []
        for k in range(n):
            th = 2 * math.pi * k / n
            sn = math.sin(th)
            b = b_bot if sn > 0 else b_top
            x = a * math.cos(th) * (1 - chin * max(0.0, sn) ** 2)
            pts.append((S(cx + x), S(cy + b * sn)))
        return pts

    def add(nm, im, blur=0.6):
        # premultiplied box downsample + premultiplied blur: no ringing, no dark or light fringes at the edges
        a = np.asarray(im, np.float32) / 255
        a[..., :3] *= a[..., 3:4]
        a = a.reshape(H, s, W, s, 4).mean((1, 3))
        if blur:
            from scipy.ndimage import gaussian_filter
            a = np.stack([gaussian_filter(a[..., c], blur) for c in range(4)], -1)
        al = a[..., 3:4]
        rgb = np.divide(a[..., :3], al, out=np.zeros_like(a[..., :3]), where=al > 1e-4)
        layers.append((nm, Image.fromarray(np.round(np.clip(np.concatenate([rgb, al], -1), 0, 1) * 255).astype(np.uint8), "RGBA")))

    # back hair
    im, d = _canvas(W, H, s)
    d.ellipse([S(92), S(66), S(428), S(450)], fill=hair_dark)
    d.ellipse([S(100), S(74), S(420), S(442)], fill=hair)
    add("hair/back", im)
    # shoulders + neck
    im, d = _canvas(W, H, s)
    d.rounded_rectangle([S(96), S(546), S(424), S(700)], radius=S(70), fill=(40, 60, 130))
    d.rounded_rectangle([S(102), S(552), S(418), S(700)], radius=S(64), fill=(70, 110, 200))
    d.rectangle([S(228), S(452), S(292), S(566)], fill=skin_line)
    d.rectangle([S(232), S(452), S(288), S(562)], fill=(236, 188, 160))
    add("body", im)
    for side, ex in (("L", 116), ("R", 404)):
        im, d = _canvas(W, H, s)
        d.ellipse([S(ex - 24), S(286), S(ex + 24), S(356)], fill=skin_line)
        d.ellipse([S(ex - 20), S(290), S(ex + 20), S(352)], fill=skin)
        d.arc([S(ex - 11), S(302), S(ex + 11), S(340)], 60 if side == "L" else -120, 300 if side == "L" else 120,
              fill=skin_line, width=S(3))
        add(f"face/ear_{side}", im)
    im, d = _canvas(W, H, s)
    d.polygon(poly(260, 300, 146, 182, 192, 0.3), fill=skin_line)
    d.polygon(poly(260, 300, 141, 177, 187, 0.3), fill=skin)
    add("face/head", im)
    for side, cx in (("L", 180), ("R", 340)):
        im, d = _canvas(W, H, s)
        d.ellipse([S(cx - 30), S(368), S(cx + 30), S(398)], fill=(255, 128, 140, 120))
        add(f"face/cheek_{side}", im, blur=4)
    im, d = _canvas(W, H, s)
    d.chord([S(244), S(452), S(276), S(464)], 0, 180, fill=(246, 198, 170))
    add("face/jaw", im, blur=1.5)
    im, d = _canvas(W, H, s)
    d.ellipse([S(249), S(340), S(271), S(358)], fill=(236, 168, 144))
    d.ellipse([S(252), S(342), S(266), S(352)], fill=(246, 190, 166))
    add("face/nose", im)
    # mouth shapes around (260, 412)
    lip, inside, teeth, tongue = (176, 72, 84), (96, 26, 44), (252, 250, 245), (226, 96, 110)
    mx, my = 260, 412
    shapes = {}

    def mouth_canvas():
        return _canvas(W, H, s)
    im, d = mouth_canvas()
    d.line([S(mx - 27), S(my), S(mx), S(my + 2), S(mx + 27), S(my)], fill=lip, width=S(4), joint="curve")
    shapes["M"] = im
    im, d = mouth_canvas()
    d.ellipse([S(mx - 27), S(my - 14), S(mx + 27), S(my + 26)], fill=lip)
    d.ellipse([S(mx - 23), S(my - 10), S(mx + 23), S(my + 22)], fill=inside)
    d.chord([S(mx - 20), S(my - 10), S(mx + 20), S(my + 2)], 180, 360, fill=teeth)
    d.ellipse([S(mx - 14), S(my + 8), S(mx + 14), S(my + 22)], fill=tongue)
    shapes["A"] = im
    im, d = mouth_canvas()
    d.rounded_rectangle([S(mx - 31), S(my - 9), S(mx + 31), S(my + 13)], radius=S(11), fill=lip)
    d.rounded_rectangle([S(mx - 27), S(my - 6), S(mx + 27), S(my + 10)], radius=S(8), fill=inside)
    d.rectangle([S(mx - 22), S(my - 6), S(mx + 22), S(my - 1)], fill=teeth)
    d.rectangle([S(mx - 18), S(my + 6), S(mx + 18), S(my + 10)], fill=teeth)
    shapes["E"] = im
    im, d = mouth_canvas()
    d.rounded_rectangle([S(mx - 29), S(my - 6), S(mx + 29), S(my + 8)], radius=S(7), fill=lip)
    d.rounded_rectangle([S(mx - 25), S(my - 3), S(mx + 25), S(my + 5)], radius=S(4), fill=teeth)
    d.line([S(mx - 25), S(my + 1), S(mx + 25), S(my + 1)], fill=(200, 190, 190), width=S(1))
    shapes["I"] = im
    im, d = mouth_canvas()
    d.ellipse([S(mx - 17), S(my - 14), S(mx + 17), S(my + 22)], fill=lip)
    d.ellipse([S(mx - 11), S(my - 8), S(mx + 11), S(my + 16)], fill=inside)
    shapes["O"] = im
    im, d = mouth_canvas()
    d.ellipse([S(mx - 11), S(my - 8), S(mx + 11), S(my + 12)], fill=lip)
    d.ellipse([S(mx - 5), S(my - 3), S(mx + 5), S(my + 7)], fill=inside)
    shapes["U"] = im
    im, d = mouth_canvas()
    d.rounded_rectangle([S(mx - 24), S(my - 6), S(mx + 24), S(my + 10)], radius=S(7), fill=lip)
    d.rectangle([S(mx - 18), S(my - 5), S(mx + 18), S(my + 2)], fill=teeth)
    d.line([S(mx - 22), S(my + 5), S(mx + 22), S(my + 5)], fill=(150, 55, 70), width=S(2))
    shapes["F"] = im
    im, d = mouth_canvas()
    d.ellipse([S(mx - 23), S(my - 12), S(mx + 23), S(my + 20)], fill=lip)
    d.ellipse([S(mx - 19), S(my - 8), S(mx + 19), S(my + 16)], fill=inside)
    d.chord([S(mx - 16), S(my - 9), S(mx + 16), S(my + 1)], 180, 360, fill=teeth)
    d.ellipse([S(mx - 8), S(my - 4), S(mx + 8), S(my + 8)], fill=tongue)
    shapes["L"] = im
    im, d = mouth_canvas()
    d.chord([S(mx - 34), S(my - 22), S(mx + 34), S(my + 18)], 15, 165, fill=lip)
    d.chord([S(mx - 30), S(my - 18), S(mx + 30), S(my + 14)], 20, 160, fill=inside)
    d.chord([S(mx - 26), S(my - 4), S(mx + 26), S(my + 6)], 180, 360, fill=teeth)
    shapes["smile"] = im
    im, d = mouth_canvas()
    d.arc([S(mx - 22), S(my - 2), S(mx + 22), S(my + 26)], 200, 340, fill=lip, width=S(4))
    shapes["frown"] = im
    for k in ("A", "E", "I", "O", "U", "M", "F", "L", "smile", "frown"):
        add(f"face/mouth/{k}", shapes[k], blur=0.5)
    # eyes
    for side, cx in (("L", 195), ("R", 325)):
        cy, a, b = 300, 34, 23

        def white_pts(scale=1.0, n=90):
            pts = []
            for k in range(n):
                th = 2 * math.pi * k / n
                pts.append((cx + a * scale * math.cos(th), cy + b * scale * math.sin(th) * (1 - 0.18 * math.cos(th) ** 2)))
            return pts

        def top_y(x, off=0.0):
            u = max(-1.0, min(1.0, (x - cx) / a))
            th = math.acos(u)
            return cy - b * math.sin(th) * (1 - 0.18 * math.cos(th) ** 2) + off

        def bot_y(x, off=0.0):
            return 2 * cy - top_y(x) + off
        im, d = _canvas(W, H, s)
        d.polygon([(S(x), S(y)) for x, y in white_pts()], fill=(120, 96, 100))
        d.polygon([(S(x), S(y)) for x, y in white_pts(0.94)], fill=(252, 252, 255))
        add(f"face/eye_{side}/white", im)
        im, d = _canvas(W, H, s)
        d.ellipse([S(cx - 16), S(cy - 16), S(cx + 16), S(cy + 16)], fill=(18, 44, 86))
        d.ellipse([S(cx - 14), S(cy - 14), S(cx + 14), S(cy + 14)], fill=(46, 122, 190))
        d.ellipse([S(cx - 10), S(cy - 4), S(cx + 10), S(cy + 13)], fill=(78, 160, 220))
        add(f"face/eye_{side}/iris", im)
        im, d = _canvas(W, H, s)
        d.ellipse([S(cx - 7), S(cy - 7), S(cx + 7), S(cy + 7)], fill=(12, 10, 20))
        add(f"face/eye_{side}/pupil", im)
        im, d = _canvas(W, H, s)
        d.ellipse([S(cx + 2), S(cy - 12), S(cx + 11), S(cy - 3)], fill=(255, 255, 255))
        add(f"face/eye_{side}/highlight", im)
        xs = np.linspace(cx - a - 3, cx + a + 3, 60)
        lash = [(x, min(top_y(x, 4.0), cy + 3)) for x in xs]
        im, d = _canvas(W, H, s)
        d.polygon([(S(cx - a - 4), S(cy + 3)), (S(cx - a - 4), S(cy - b - 18)), (S(cx + a + 4), S(cy - b - 18)),
                   (S(cx + a + 4), S(cy + 3))] + [(S(x), S(y)) for x, y in lash[::-1]], fill=skin)
        outer = 1 if side == "R" else -1
        for k in range(len(lash) - 1):
            x, y = lash[k]
            wgt = 3.5 + 2.5 * max(0.0, outer * (x - cx) / a)
            d.line([S(x), S(y), S(lash[k + 1][0]), S(lash[k + 1][1])], fill=(40, 24, 30), width=int(round(S(wgt))))
        add(f"face/eye_{side}/lid_upper", im)
        low = [(x, max(bot_y(x, -2.0), cy - 2)) for x in xs]
        im, d = _canvas(W, H, s)
        d.polygon([(S(x), S(y)) for x, y in low] + [(S(cx + a + 4), S(cy + b + 10)), (S(cx - a - 4), S(cy + b + 10))],
                  fill=skin)
        d.line([c for x, y in low for c in (S(x), S(y))], fill=(214, 156, 136), width=S(2))
        add(f"face/eye_{side}/lid_lower", im)
    for side, (xi, xo) in (("L", (233, 157)), ("R", (287, 363))):
        im, d = _canvas(W, H, s)
        n = 24
        top, bot = [], []
        for k in range(n + 1):
            u = k / n
            x = xi + (xo - xi) * u
            yc = 252 - 14 * math.sin(math.pi * (0.3 + 0.7 * u)) - 4 * u
            th = 7.0 * (1 - u) + 3.0
            top.append((S(x), S(yc - th / 2)))
            bot.append((S(x), S(yc + th / 2)))
        d.polygon(top + bot[::-1], fill=(84, 46, 34))
        add(f"face/brow_{side}", im)
    for side, x0 in (("L", 126), ("R", 394)):
        im, d = _canvas(W, H, s)
        sg = 1 if side == "L" else -1
        for t in range(0, 270, 4):
            y = 205 + t
            x = x0 + sg * (-8 + 10 * math.sin(t / 45.0))
            rr = 19 * (1 - t / 330)
            d.ellipse([S(x - rr), S(y - rr * 0.7), S(x + rr), S(y + rr * 0.7)], fill=hair)
        add(f"hair/strand_{side}", im)
    im, d = _canvas(W, H, s)
    arc = [(260 + 152 * math.cos(th), 258 + 168 * math.sin(th)) for th in np.linspace(math.pi, 2 * math.pi, 40)]
    jag = [(408, 226), (372, 170), (338, 198), (300, 162), (262, 194), (224, 162), (186, 198), (150, 170), (112, 226)]
    d.polygon([(S(x), S(y)) for x, y in arc + jag], fill=hair_dark)
    arc2 = [(260 + 146 * math.cos(th), 262 + 162 * math.sin(th)) for th in np.linspace(math.pi, 2 * math.pi, 40)]
    jag2 = [(x - (4 if x > 260 else -4), y - 5) for x, y in jag]
    d.polygon([(S(x), S(y)) for x, y in arc2 + jag2], fill=hair)
    add("hair/bangs", im)

    for nm, im in layers:
        bb = im.getchannel("A").getbbox()
        if bb is None:
            continue
        crop = im.crop(bb)
        p.write_image(nm, crop)
        cx = bb[0] + crop.width / 2 - W / 2
        cy = H - (bb[1] + crop.height / 2)
        sk.slots.append(Slot(name=nm, bone="root", attachment=nm))
        sk.set_attachment(nm, nm, RegionAttachment(x=round(cx, 2), y=round(cy, 2), width=crop.width, height=crop.height))
    p.save()
    return p
