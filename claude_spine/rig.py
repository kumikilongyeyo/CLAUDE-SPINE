"""Bones and constraints: chains, IK, physics, transform constraints, strand
rigs (hair/cloth/tails) and the 2.5D turn rig — the ``rig_constraints`` tool's
engine.

Everything here keeps the world-space setup pose unchanged: adding a bone,
re-parenting a slot or inserting a parent never moves art on screen.
"""
from __future__ import annotations

import math

import numpy as np

from .ir import (Bone, ClippingAttachment, BoundingBoxAttachment, IkConstraint, MeshAttachment,
                 PhysicsConstraint, PointAttachment, RegionAttachment, SkeletonData, TransformConstraint, _wrap)
from .mesh import region_pixel_to_local, rig_mesh, to_local, to_world
from .project import Project
from .timeline import AnimBuilder

# ------------------------------------------------------------------ physics presets
# Spine 4.2 physics, as the runtime applies them (PhysicsConstraint.update):
# strength is spring stiffness; the swing frequency is about sqrt(strength/mass)
# rad/s. damping is the velocity KEPT per 1/60 s (velocity *= damping^(60·dt)):
# 1.0 never settles, 0.9 settles in about a second. inertia is how much of the
# parent's motion the bone resists: the main knob for "how wild". limit caps
# the velocity (px/s) the solver accepts, so a reel-stop slam cannot fling a
# lock of hair straight out sideways.
PHYSICS_PRESETS: dict[str, dict] = {
    "hair":    dict(rotate=1, x=0, y=0, inertia=0.3, strength=160, damping=0.88, mass=1.2, limit=1200),
    "cloth":   dict(rotate=1, x=0.15, y=0, inertia=0.25, strength=120, damping=0.88, mass=1.5, limit=1000),
    "tail":    dict(rotate=1, x=0, y=0, inertia=0.55, strength=70, damping=0.85, mass=1.6),
    "ribbon":  dict(rotate=1, x=0.1, y=0.1, inertia=0.4, strength=90, damping=0.86, mass=1.3, limit=1500),
    "jiggle":  dict(rotate=0, x=1, y=1, scaleX=0.5, inertia=0.7, strength=200, damping=0.8, mass=1.0),
    "antenna": dict(rotate=1, x=0, y=0, inertia=0.8, strength=250, damping=0.8, mass=0.8),
    "tassel":  dict(rotate=1, x=0, y=0, inertia=0.45, strength=100, damping=0.88, mass=1.4),
}


def _next_order(sk: SkeletonData) -> int:
    orders = [c.order for c in [*sk.ik, *sk.transform, *sk.physics]] + [p.get("order", 0) for p in sk.path]
    return (max(orders) + 1) if orders else 0


# ------------------------------------------------------------------------- bones
def add_chain(sk: SkeletonData, name: str, points: list[list[float]], parent: str = "root") -> list[str]:
    """Bones along a polyline of world points: n points → n-1 bones, each
    reaching exactly to the next point. Named ``name1..n``."""
    if len(points) < 2:
        raise ValueError("a chain needs at least two points")
    names, par = [], parent
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        nm = sk.unique_name(f"{name}{i + 1}")
        sk.add_bone_world(nm, par, a[0], a[1], ang, L)
        names.append(nm)
        par = nm
    return names


def insert_parent(sk: SkeletonData, new: str, under: str, children: list[str], x: float = 0, y: float = 0) -> Bone:
    """Insert ``new`` (pure translation, at world x,y) between ``under`` and
    ``children`` without moving them."""
    world = sk.world()
    b = sk.add_bone_world(new, under, x, y, world[under].rotation if under else 0)
    b.rotation = 0
    nw = sk.world()[new]
    for c in children:
        cb = sk.bone(c)
        cw = world[c]
        lx, ly = nw.to_local(cw.x, cw.y)
        cb.parent = new
        cb.x, cb.y = round(lx, 3), round(ly, 3)
        cb.rotation = round(_wrap(cw.rotation - nw.rotation), 3) if cb.inherit == "normal" else cb.rotation
    # parents must precede children in the list
    # (list.sort empties the list while sorting, so compute the order first)
    sk.reorder_bones(_depth_order(sk))
    return sk.bone(new)


def _depth_order(sk: SkeletonData) -> list[str]:
    order, stack = [], [b.name for b in sk.bones if b.parent is None]
    kids: dict[str, list[str]] = {}
    for b in sk.bones:
        if b.parent:
            kids.setdefault(b.parent, []).append(b.name)
    while stack:
        n = stack.pop(0)
        order.append(n)
        stack[0:0] = kids.get(n, [])
    return order


def reparent_slot(sk: SkeletonData, slot: str, new_bone: str) -> None:
    """Move a slot to another bone, rewriting its unweighted attachments so the
    art stays where it is. Weighted meshes name their bones explicitly and
    need no change."""
    s = sk.slot(slot)
    world = sk.world()
    old, new = world[s.bone], world[new_bone]
    for skin in sk.skins:
        for an, att in skin.attachments.get(slot, {}).items():
            if isinstance(att, RegionAttachment) or isinstance(att, PointAttachment):
                wx, wy = old.to_world(att.x, att.y)
                lx, ly = new.to_local(wx, wy)
                att.x, att.y = round(lx, 3), round(ly, 3)
                att.rotation = round(_wrap(att.rotation + old.rotation - new.rotation), 3)
            elif isinstance(att, (MeshAttachment, ClippingAttachment, BoundingBoxAttachment)):
                n = len(att.vertices)
                cnt = len(att.uvs) // 2 if isinstance(att, MeshAttachment) else att.vertexCount
                if n == 2 * cnt:
                    lp = np.asarray(att.vertices, float).reshape(-1, 2)
                    att.vertices = [round(float(v), 3) for v in to_local(new, to_world(old, lp)).ravel()]
    s.bone = new_bone


# ---------------------------------------------------------------------------- IK
def add_ik(sk: SkeletonData, bones: list[str], target: str | None = None, target_parent: str | None = None,
           name: str | None = None, bend_positive: bool | None = None, softness: float = 0,
           stretch: bool = False, compress: bool = False, mix: float = 1) -> dict:
    """One- or two-bone IK. Creates the target bone at the chain's tip (world)
    under ``target_parent`` unless an existing ``target`` is named. The bend
    direction defaults to the one the setup pose already has."""
    if not 1 <= len(bones) <= 2:
        raise ValueError("Spine IK takes 1 or 2 bones (parent, child)")
    for b in bones:
        sk.bone(b)
    if len(bones) == 2 and sk.bone(bones[1]).parent != bones[0]:
        raise ValueError(f"{bones[1]!r} must be a direct child of {bones[0]!r}")
    world = sk.world()
    tip = world[bones[-1]]
    if tip.length <= 0:
        raise ValueError(f"bone {bones[-1]!r} has length 0; IK needs a length to reach the target")
    if bend_positive is None:
        bend_positive = True
        if len(bones) == 2:
            p, c = world[bones[0]], world[bones[1]]
            v1 = np.subtract(c.head, p.head)
            v2 = np.subtract(c.tail, c.head)
            cross = v1[0] * v2[1] - v1[1] * v2[0]
            bend_positive = bool(cross >= 0)
    if target_parent is None:
        # under the juice bones when they exist, so drops and squashes carry the target
        target_parent = "juice_core" if sk.has_bone("juice_core") else "root"
    if target is None:
        target = sk.unique_name(f"{bones[-1]}_ik")
        tx, ty = tip.tail
        sk.add_bone_world(target, target_parent, tx, ty, 0, color="FF3F00FF")
    name = name or sk.unique_name(f"ik_{bones[-1]}", "constraint")
    sk.ik.append(IkConstraint(name=name, order=_next_order(sk), bones=list(bones), target=target, mix=mix,
                              softness=softness, bendPositive=bend_positive, stretch=stretch, compress=compress))
    return {"constraint": name, "target": target, "bendPositive": bend_positive}


# ----------------------------------------------------------------------- physics
def add_physics(sk: SkeletonData, bones: list[str], preset: str = "hair", taper: float = 0.15, **overrides) -> list[str]:
    """One physics constraint per bone. Down a chain each bone is a little
    looser (``taper``), so tips trail their roots like real hair does."""
    if preset not in PHYSICS_PRESETS:
        raise ValueError(f"unknown physics preset {preset!r}; one of {sorted(PHYSICS_PRESETS)}")
    names = []
    for i, b in enumerate(bones):
        sk.bone(b)
        p = dict(PHYSICS_PRESETS[preset])
        p.update(overrides)
        loosen = max(0.3, 1 - taper * i)
        p["strength"] = round(p["strength"] * loosen, 2)
        nm = sk.unique_name(f"phys_{b}", "constraint")
        sk.physics.append(PhysicsConstraint(name=nm, order=_next_order(sk), bone=b, **p))
        names.append(nm)
    return names


# --------------------------------------------------------------------- transform
def add_transform(sk: SkeletonData, bones: list[str], target: str, name: str | None = None,
                  mix_rotate: float = 1, mix_x: float = 1, mix_y: float | None = None,
                  mix_scale_x: float = 0, mix_scale_y: float | None = None, mix_shear_y: float = 0,
                  local: bool = False, relative: bool = False, **offsets) -> str:
    for b in [*bones, target]:
        sk.bone(b)
    name = name or sk.unique_name(f"tc_{bones[0]}", "constraint")
    sk.transform.append(TransformConstraint(
        name=name, order=_next_order(sk), bones=list(bones), target=target, mixRotate=mix_rotate, mixX=mix_x,
        mixY=mix_y, mixScaleX=mix_scale_x, mixScaleY=mix_scale_y, mixShearY=mix_shear_y,
        local=local, relative=relative, **offsets))
    return name


# ------------------------------------------------------------------------ strands
def strand_centerline(alpha: np.ndarray, n_bones: int, root_end: str = "auto", threshold: int = 8):
    """Centre line of an elongated part in image pixels, root first: the art's
    principal axis cut into ``n_bones`` slabs, one centroid per slab, so the
    chain follows a curved strand instead of a straight line through it."""
    ys, xs = np.nonzero(alpha > threshold)
    if len(xs) < 10:
        raise ValueError("strand image is (almost) empty")
    P = np.c_[xs, ys].astype(float) + 0.5
    c = P.mean(0)
    u, s, vt = np.linalg.svd(P - c, full_matrices=False)
    axis = vt[0]
    t = (P - c) @ axis
    lo, hi = t.min(), t.max()
    ends = {"a": c + axis * lo, "b": c + axis * hi}
    if root_end == "auto":
        root_end = "top"  # hair, ribbons and capes hang from above by default
    pick = {"top": lambda e: e[1], "bottom": lambda e: -e[1], "left": lambda e: e[0], "right": lambda e: -e[0]}
    if root_end not in pick:
        raise ValueError("root_end is auto|top|bottom|left|right")
    if pick[root_end](ends["b"]) < pick[root_end](ends["a"]):
        axis, t, lo, hi = -axis, -t, -hi, -lo
    edges = np.linspace(lo, hi, n_bones * 2 + 1)
    pts = [None] * (n_bones + 1)
    # joints sit at slab boundaries; use the centroid of a thin band there
    for i in range(n_bones + 1):
        e = edges[2 * i]
        band = np.abs(t - e) <= max((hi - lo) / (n_bones * 6), 1.5)
        if i == 0:
            band = t <= lo + max((hi - lo) * 0.04, 1.5)
        if i == n_bones:
            band = t >= hi - max((hi - lo) * 0.04, 1.5)
        pts[i] = P[band].mean(0) if band.any() else c + axis * e
    return np.array(pts)


def rig_strand(project: Project, slot: str, n_bones: int = 3, parent: str | None = None, root_end: str = "auto",
               physics: str | None = "hair", name: str | None = None, detail: float = 1.0) -> dict:
    """Chain + heat-weighted mesh + physics for hair locks, capes, ribbons,
    tails: one call. The chain follows the strand's own centre line."""
    sk = project.data
    s = sk.slot(slot)
    att = sk.attachment(slot)
    if not isinstance(att, RegionAttachment):
        raise ValueError("rig_strand starts from a region attachment (run it before meshing)")
    im = project.image(project.att_image_name(slot, s.attachment))
    W, H = im.size
    alpha = np.array(im)[:, :, 3]
    cl = strand_centerline(alpha, n_bones, root_end)
    f, _ = region_pixel_to_local(att, W, H)
    world = sk.world()
    pts_w = to_world(world[s.bone], f(cl))
    parent = parent or s.bone
    base = name or f"{slot}_"
    bones = add_chain(sk, base, pts_w.tolist(), parent)
    mesh = rig_mesh(project, slot, bones=bones, detail=detail)
    phys = add_physics(sk, bones, physics) if physics else []
    return {"bones": bones, "mesh": mesh, "physics": phys}


# ----------------------------------------------------------------------- turn rig
def setup_hull_world(project: Project, slot: str) -> np.ndarray:
    """World-space outline of a slot's setup attachment."""
    from .mesh import mesh_world_vertices
    sk = project.data
    att = sk.attachment(slot)
    world = sk.world()
    if isinstance(att, MeshAttachment):
        return mesh_world_vertices(sk, slot, att, world)[: att.hull]
    if isinstance(att, RegionAttachment):
        im = project.image(project.att_image_name(slot, sk.slot(slot).attachment))
        f, _ = region_pixel_to_local(att, *im.size)
        W, H = im.size
        corners = np.array([[0, 0], [W, 0], [W, H], [0, H]], float)
        return to_world(world[sk.slot(slot).bone], f(corners))
    raise ValueError(f"{slot}: unsupported attachment type {att.type}")


def turn_rig(project: Project, head_bone: str, face_slot: str, features: dict[str, float],
             turn_range: float | None = None, pitch: float = 0.6, swap_pairs: list[list[str]] | None = None,
             make_test_animation: bool = True) -> dict:
    """2.5D head turn driven by one control bone.

    face_slot   the face/head base layer. It becomes a mesh whose middle travels
                with the control while its outline stays pinned, which reads as
                a surface turning rather than sliding.
    features    {slot: depth}. Depth 1.0 moves with the face surface; >1 for
                parts that stick out (nose 1.25, eyes 0.9, brows 0.95, mouth
                1.0); negative for parts behind the head (ears -0.35, back
                hair -0.5) so they slide the opposite way.
    turn_range  control travel in px for a full turn (default 25% of face width;
                beyond ~30% features near the edge cross the outline).
    swap_pairs  [[front, back], ...] slots that swap draw order past ~70% turn
                (e.g. an ear passing behind the head) in the test animation.

    Bones: ``turn_base`` (child of head at the head's origin) → ``turn_ctrl``.
    Constraints are local+relative, which add the target's *absolute* local
    offset — so the control must sit at local (0, 0) under a base bone.
    """
    sk = project.data
    sk.bone(head_bone)
    hull = setup_hull_world(project, face_slot)
    fw = float(np.ptp(hull[:, 0]))
    fh = float(np.ptp(hull[:, 1]))
    R = turn_range or 0.25 * fw
    world = sk.world()
    hw = world[head_bone]
    # All turn bones live in a frame aligned with the screen at setup (world
    # rotation 0) that still follows the head. Head bones usually point up
    # (rotation 90), and in the head's own frame "x" would be screen-up: the
    # control would nod instead of turning.
    space = sk.unique_name("turn_space")
    sk.add_bone_world(space, head_bone, hw.x, hw.y, 0)
    base = sk.unique_name("turn_base")
    sk.add_bone_world(base, space, hw.x, hw.y, 0)
    ctrl = sk.unique_name("turn_ctrl")
    sk.add_bone_world(ctrl, base, hw.x, hw.y, 0, color="FFD400FF")
    made = {"control": ctrl, "base": base, "space": space, "range": round(R, 2), "features": {}}

    # face surface: weighted between head and a driven bone with a silhouette field
    face_drv = sk.unique_name("turn_face")
    sk.add_bone_world(face_drv, space, hw.x, hw.y, 0)
    add_transform(sk, [face_drv], ctrl, name=sk.unique_name("turn_face_tc", "constraint"), mix_rotate=0, mix_x=1,
                  mix_y=pitch, mix_scale_x=0, mix_scale_y=0, mix_shear_y=0, local=True, relative=True)
    rig_mesh(project, face_slot, bones=[head_bone], detail=1.2)
    _surface_weights(project, face_slot, head_bone, face_drv)
    made["face"] = {"slot": face_slot, "driven_bone": face_drv}

    for slot, depth in features.items():
        s = sk.slot(slot)
        att = sk.attachment(slot)
        if isinstance(att, MeshAttachment) and len(att.vertices) != 2 * (len(att.uvs) // 2):
            raise ValueError(f"{slot} is a weighted mesh; give the turn rig region or unweighted parts")
        h = setup_hull_world(project, slot)
        cx, cy = h.mean(0)
        b = sk.unique_name(f"turn_{slot}")
        sk.add_bone_world(b, space, cx, cy, 0)
        # a feature off-centre turns less: it is already on the curved side
        off = (cx - hull[:, 0].mean()) / max(fw / 2, 1e-6)
        fall = max(0.25, 1 - off * off)
        mix = round(depth * fall, 3)
        reparent_slot(sk, slot, b)
        tc = add_transform(sk, [b], ctrl, name=sk.unique_name(f"turn_{slot}_tc", "constraint"), mix_rotate=0,
                           mix_x=mix, mix_y=round(mix * pitch, 3), mix_scale_x=0, mix_scale_y=0, mix_shear_y=0,
                           local=True, relative=True)
        made["features"][slot] = {"bone": b, "mix": mix, "constraint": tc}

    if make_test_animation:
        ab = AnimBuilder(sk, "turn_test")
        ab.bone(ctrl, "translate", [(0, 0, 0), (0.6, R, 0), (1.2, 0, 0), (1.8, -R, 0), (2.4, 0, 0),
                                     (2.8, 0, R * 0.5), (3.2, 0, -R * 0.5), (3.6, 0, 0)], ease="sine_in_out")
        for front, back in swap_pairs or []:
            from .timeline import swap_offsets
            ab.draw_order(0.42, swap_offsets(sk, front, back))
            ab.draw_order(0.78, None)
        made["animation"] = "turn_test"
    return made


def _surface_weights(project: Project, slot: str, head: str, driven: str, knee: float = 0.8) -> None:
    """Per-row parabola across the face silhouette (see the rig25d notes in
    the README): w = A(h) * (1 - ((x - c(y)) / h(y))²), A(h) = min(1, h / (knee·R)).
    Outline vertices get w = 0 (pinned); the middle of each row travels most.
    The parabola keeps x + s·w monotonic for control travel s < knee·R/2, so
    the mesh cannot fold over itself inside the turn range."""
    from .mesh import mesh_world_vertices
    from .weights import skin_vertices
    sk = project.data
    att = sk.attachment(slot)
    world = sk.world()
    pts = mesh_world_vertices(sk, slot, att, world)
    hull = pts[: att.hull]
    ys = pts[:, 1]
    # row extents of the outline at each vertex's height
    w = np.zeros(len(pts))
    R = 0.0
    rows = []
    for y in ys:
        xs = _row_intersections(hull, y)
        if len(xs) >= 2:
            rows.append((xs.min(), xs.max()))
        else:
            rows.append((None, None))
        if len(xs) >= 2:
            R = max(R, (xs.max() - xs.min()) / 2)
    for i, (x, (a, b)) in enumerate(zip(pts[:, 0], rows)):
        if a is None:
            continue
        h = (b - a) / 2
        c = (a + b) / 2
        A = min(1.0, h / max(knee * R, 1e-6))
        w[i] = max(0.0, A * (1 - ((x - c) / max(h, 1e-6)) ** 2))
    w[: att.hull] = 0.0
    W = np.c_[1 - w, w]
    att.vertices = skin_vertices(pts, W, [sk.bone_index(head), sk.bone_index(driven)], [world[head], world[driven]])


def _row_intersections(poly: np.ndarray, y: float) -> np.ndarray:
    a, b = poly, np.roll(poly, -1, axis=0)
    cond = (a[:, 1] - y) * (b[:, 1] - y) <= 0
    dy = b[:, 1] - a[:, 1]
    ok = cond & (np.abs(dy) > 1e-9)
    t = (y - a[ok, 1]) / dy[ok]
    return a[ok, 0] + t * (b[ok, 0] - a[ok, 0])
