"""Turn region attachments into clean, weighted Spine meshes (and re-weight
existing meshes) — the ``rig_mesh`` tool's engine."""
from __future__ import annotations

import math

import numpy as np

from .geometry import build_mesh_geom, dist_to_polyline, points_in_polygon
from .ir import MeshAttachment, RegionAttachment, SkeletonData, WorldBone
from .project import Project
from .weights import BoneSeg, decode_weighted, heat_weights, skin_vertices


# ------------------------------------------------------------------ coordinates
def region_pixel_to_local(att: RegionAttachment, W: int, H: int):
    """Map image pixels (x right, y down) to the slot bone's local space for a
    region attachment, matching RegionAttachment.updateRegion."""
    r = math.radians(att.rotation)
    c, s = math.cos(r), math.sin(r)

    def f(px: np.ndarray) -> np.ndarray:
        u, v = px[:, 0] / W, px[:, 1] / H
        lx0 = (u - 0.5) * att.width * att.scaleX
        ly0 = (0.5 - v) * att.height * att.scaleY
        return np.c_[att.x + c * lx0 - s * ly0, att.y + s * lx0 + c * ly0]

    def inv(lp: np.ndarray) -> np.ndarray:
        dx, dy = lp[:, 0] - att.x, lp[:, 1] - att.y
        lx0, ly0 = c * dx + s * dy, -s * dx + c * dy
        u = lx0 / (att.width * att.scaleX) + 0.5
        v = 0.5 - ly0 / (att.height * att.scaleY)
        return np.c_[u * W, v * H]

    return f, inv


def to_world(wb: WorldBone, lp: np.ndarray) -> np.ndarray:
    return np.c_[wb.a * lp[:, 0] + wb.b * lp[:, 1] + wb.x, wb.c * lp[:, 0] + wb.d * lp[:, 1] + wb.y]


def to_local(wb: WorldBone, wp: np.ndarray) -> np.ndarray:
    det = wb.a * wb.d - wb.b * wb.c
    dx, dy = wp[:, 0] - wb.x, wp[:, 1] - wb.y
    return np.c_[(wb.d * dx - wb.b * dy) / det, (wb.a * dy - wb.c * dx) / det]


def bone_segment(sk: SkeletonData, world: dict[str, WorldBone], name: str, among: set[str]) -> BoneSeg:
    """A bone's segment for weighting: head→tail; a zero-length bone with one
    selected child uses the child's head as its tail."""
    wb = world[name]
    if wb.length > 1e-6:
        return BoneSeg(name, wb.head, wb.tail)
    kids = [c.name for c in sk.children(name) if c.name in among]
    if len(kids) == 1:
        return BoneSeg(name, wb.head, world[kids[0]].head)
    return BoneSeg(name, wb.head, wb.head)


def mesh_world_vertices(sk: SkeletonData, slot: str, att: MeshAttachment, world=None) -> np.ndarray:
    world = world or sk.world()
    n = len(att.uvs) // 2
    if len(att.vertices) == 2 * n:
        lp = np.asarray(att.vertices, float).reshape(-1, 2)
        return to_world(world[sk.slot(slot).bone], lp)
    out = np.zeros((n, 2))
    for i, inf in enumerate(decode_weighted(att.vertices, n)):
        for bi, x, y, w in inf:
            out[i] += w * np.array(world[sk.bones[bi].name].to_world(x, y))
    return out


def auto_bones(sk: SkeletonData, slot: str, hull_world: np.ndarray, world) -> list[str]:
    """Bones that plausibly deform this part: the slot's bone, its parent, and
    the slot bone's descendants whose segment touches the part's outline
    (within 8% of its size)."""
    sb = sk.slot(slot).bone
    cands = [sb] + sk.descendants(sb)
    parent = sk.bone(sb).parent
    if parent and parent != "root":
        cands.append(parent)
    size = float(np.ptp(hull_world, axis=0).max())
    margin = 0.08 * size
    keep = []
    among = set(cands)
    for b in cands:
        seg = bone_segment(sk, world, b, among)
        pts = np.linspace(np.asarray(seg.head), np.asarray(seg.tail), 9)
        inside = points_in_polygon(pts, hull_world)
        near = dist_to_polyline(pts, hull_world) <= margin
        if (inside | near).any():
            keep.append(b)
    if sb not in keep:
        keep.insert(0, sb)
    return keep


# ------------------------------------------------------------------------ build
def rig_mesh(project: Project, slot: str, attachment: str | None = None, bones: list[str] | str | None = "auto",
             detail: float = 1.0, max_vertices: int = 300, pad: float = 2.0, alpha_threshold: int = 8,
             min_weight: float = 0.05, max_influences: int = 4, smooth: float = 1.0,
             extra_joints: list[list[float]] | None = None, skin: str = "default") -> dict:
    """Replace a region (or re-mesh an existing mesh) with a contour mesh and,
    when more than one bone applies, heat-diffused weights.

    bones  "auto" (default) picks bones whose segments touch the part; a list
           names them explicitly; None or [] makes an unweighted mesh.
    """
    sk = project.data
    s = sk.slot(slot)
    att_name = attachment or s.attachment
    if att_name is None:
        raise ValueError(f"slot {slot!r} has no setup attachment; pass attachment=")
    att = sk.attachment(slot, att_name, skin)
    world = sk.world()
    sbw = world[s.bone]

    img_name = project.att_image_name(slot, att_name)
    im = project.image(img_name)
    W, H = im.size
    if isinstance(att, RegionAttachment):
        f, inv = region_pixel_to_local(att, W, H)
    elif isinstance(att, MeshAttachment):
        # re-mesh in the space the existing mesh occupies: fit an affine
        # uv→world map from its own vertices
        wv = mesh_world_vertices(sk, slot, att, world)
        uv = np.asarray(att.uvs, float).reshape(-1, 2) * [W, H]
        Aff, *_ = np.linalg.lstsq(np.c_[uv, np.ones(len(uv))], to_local(sbw, wv), rcond=None)
        f = lambda px: np.c_[px, np.ones(len(px))] @ Aff  # noqa: E731
        Ainv = np.linalg.inv(np.r_[Aff.T, [[0, 0, 1]]])
        inv = lambda lp: (np.c_[lp, np.ones(len(lp))] @ Ainv.T)[:, :2]  # noqa: E731
    else:
        raise ValueError(f"{slot}/{att_name} is a {att.type}; only region and mesh attachments can be meshed")

    alpha = np.array(im)[:, :, 3]

    # joints = bone heads/tails that fall on the art, in image pixels
    if bones == "auto":
        # outline first, cheaply, to choose bones
        g0 = build_mesh_geom(alpha, None, detail=0.5, pad=pad, threshold=alpha_threshold, max_vertices=120)
        hull_w = to_world(sbw, f(g0.points[:g0.hull]))
        bone_list = auto_bones(sk, slot, hull_w, world)
    elif not bones:
        bone_list = []
    else:
        bone_list = list(bones)
        for b in bone_list:
            sk.bone(b)
    among = set(bone_list)
    segs = [bone_segment(sk, world, b, among) for b in bone_list]
    joint_w = []
    for sg in segs:
        joint_w += [sg.head, sg.tail]
    joints_px = np.zeros((0, 2))
    if len(segs) > 1 and joint_w:
        jp = inv(to_local(sbw, np.asarray(joint_w, float)))
        okj = (jp[:, 0] > -0.1 * W) & (jp[:, 0] < 1.1 * W) & (jp[:, 1] > -0.1 * H) & (jp[:, 1] < 1.1 * H)
        joints_px = jp[okj]
        # the head of the first (parent-most) bone is not a bend point
    if extra_joints:
        joints_px = np.vstack([joints_px, np.asarray(extra_joints, float)])

    g = build_mesh_geom(alpha, joints_px if len(joints_px) else None, detail=detail, pad=pad,
                        threshold=alpha_threshold, max_vertices=max_vertices)
    local = f(g.points)
    world_pts = to_world(sbw, local)
    uvs = np.clip(np.c_[g.points[:, 0] / W, g.points[:, 1] / H], 0, 1)
    tris = g.triangles

    if len(segs) > 1:
        Wt = heat_weights(world_pts, tris, g.hull, segs, min_weight=min_weight,
                          max_influences=max_influences, smooth=smooth)
        verts = skin_vertices(world_pts, Wt, [sk.bone_index(b) for b in bone_list],
                              [world[b] for b in bone_list])
        weighted = True
    else:
        if segs and segs[0].name != s.bone:
            # a single named bone: weight everything to it (weight 1)
            Wt = np.ones((len(world_pts), 1))
            verts = skin_vertices(world_pts, Wt, [sk.bone_index(segs[0].name)], [world[segs[0].name]])
            weighted = True
        else:
            Wt = None
            verts = [round(float(v), 3) for v in local.ravel()]
            weighted = False

    hull_edges = []
    for i in range(g.hull):
        hull_edges += [i * 2, ((i + 1) % g.hull) * 2]
    mesh = MeshAttachment(
        path=getattr(att, "path", None) if getattr(att, "path", None) not in (None, att_name) else None,
        uvs=[round(float(v), 5) for v in uvs.ravel()],
        triangles=[int(i) for i in tris.ravel()],
        vertices=verts, hull=g.hull, edges=hull_edges,
        width=W, height=H, color=att.color, sequence=getattr(att, "sequence", None))
    sk.set_attachment(slot, att_name, mesh, skin)
    dropped = _drop_deforms(sk, skin, slot, att_name)

    infl = None
    if Wt is not None:
        infl = {b: int((Wt[:, j] > 0).sum()) for j, b in enumerate(bone_list)}
    return {"slot": slot, "attachment": att_name, "weighted": weighted, "bones": bone_list,
            "vertices_per_bone": infl, **g.stats, "dropped_deform_timelines": dropped}


def _drop_deforms(sk: SkeletonData, skin: str, slot: str, att: str) -> list[str]:
    """A new mesh invalidates deform keys made for the old vertex list."""
    out = []
    for an, a in sk.animations.items():
        node = a.attachments.get(skin, {}).get(slot, {})
        if att in node and "deform" in node[att]:
            del node[att]["deform"]
            if not node[att]:
                del node[att]
            out.append(an)
    return out


def lbs_pose(sk: SkeletonData, slot: str, att: MeshAttachment, posed_world: dict[str, WorldBone]) -> np.ndarray:
    """Linear-blend-skinned vertex positions for a pose (used by QA and tests)."""
    n = len(att.uvs) // 2
    if len(att.vertices) == 2 * n:
        return to_world(posed_world[sk.slot(slot).bone], np.asarray(att.vertices, float).reshape(-1, 2))
    out = np.zeros((n, 2))
    for i, inf in enumerate(decode_weighted(att.vertices, n)):
        for bi, x, y, w in inf:
            out[i] += w * np.array(posed_world[sk.bones[bi].name].to_world(x, y))
    return out
