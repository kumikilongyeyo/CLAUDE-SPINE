"""Volume-preserving 2.5D mesh weighting and sparse bounce motion.

The volume pass layers on top of existing skin weights. It reserves a smooth
centre-weight for a new core bone, scales the old influences by the remainder,
then re-normalises to the requested mobile influence cap.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from .ir import MeshAttachment, RegionAttachment
from .mesh import mesh_world_vertices, rig_mesh
from .project import Project
from .timeline import AnimBuilder, r
from .weights import decode_weighted, finalize, skin_vertices


def _weights(sk, slot: str, att: MeshAttachment) -> tuple[list[str], np.ndarray]:
    """Return stable bone names + weight matrix (bone indices can change when the core is inserted)."""
    n = len(att.uvs) // 2
    if len(att.vertices) == 2 * n:
        return [sk.slot(slot).bone], np.ones((n, 1), float)
    inf = decode_weighted(att.vertices, n)
    names: list[str] = []
    for row in inf:
        for bi, *_ in row:
            name = sk.bones[bi].name
            if name not in names:
                names.append(name)
    col = {name: j for j, name in enumerate(names)}
    W = np.zeros((n, len(names)), float)
    for i, row in enumerate(inf):
        for bi, _x, _y, w in row:
            W[i, col[sk.bones[bi].name]] = float(w)
    return names, W


def _dominant_parent(names: list[str], W: np.ndarray, pts: np.ndarray, centre: np.ndarray) -> str:
    i = int(np.argmin(np.sum((pts - centre[None]) ** 2, axis=1)))
    return names[int(np.argmax(W[i]))]


def rig_volume(project: Project, slots: list[str], strength: float = 0.72, falloff: float = 1.6,
               rim_weight: float = 0.0, parent: str = "", detail: float = 1.2,
               max_vertices: int = 280, min_weight: float = 0.03, max_influences: int = 4,
               physics: str = "none", test_animation: bool = True, name: str = "volume") -> dict[str, Any]:
    """Add one shared 2.5D volume core to one or more art slots.

    Existing weighted meshes keep their current deformation; the new core gets
    strongest influence near the visual centre and fades toward rim_weight at
    the outline. rim_weight=0 pins the silhouette, usually the cleanest choice
    for slot symbols and faces.

    Animate the returned core bone's scale/translate for squash, bulge and
    secondary wobble. physics=jiggle optionally adds runtime secondary motion.
    """
    if not slots:
        raise ValueError("give at least one slot")
    if not 0 <= strength <= 0.95:
        raise ValueError("strength must be 0..0.95")
    if falloff <= 0:
        raise ValueError("falloff must be > 0")
    if not 0 <= rim_weight <= strength:
        raise ValueError("rim_weight must be between 0 and strength")

    sk = project.data
    prepared: list[tuple[str, MeshAttachment, np.ndarray, list[str], np.ndarray]] = []
    hulls = []
    for slot in slots:
        sk.slot(slot)
        att = sk.attachment(slot)
        if isinstance(att, RegionAttachment):
            rig_mesh(project, slot, bones=None, detail=detail, max_vertices=max_vertices)
            att = sk.attachment(slot)
        if not isinstance(att, MeshAttachment):
            raise ValueError(f"{slot}: volume rig needs a region or mesh attachment")
        pts = mesh_world_vertices(sk, slot, att, sk.world())
        names, W = _weights(sk, slot, att)
        prepared.append((slot, att, pts, names, W))
        hulls.append(pts[:att.hull])

    H = np.vstack(hulls)
    lo, hi = H.min(0), H.max(0)
    centre = (lo + hi) / 2
    rx, ry = np.maximum((hi - lo) / 2, 1e-6)

    if parent:
        sk.bone(parent)
        par = parent
    else:
        slot, att, pts, names, W = prepared[0]
        par = _dominant_parent(names, W, pts, centre)

    core = sk.unique_name(f"{name}_core")
    sk.add_bone_world(core, par, float(centre[0]), float(centre[1]), 0, color="FF9A3CFF")
    core_i = sk.bone_index(core)
    world = sk.world()

    results = {}
    for slot, att, pts, names, Wold in prepared:
        q = np.sqrt(((pts[:, 0] - centre[0]) / rx) ** 2 + ((pts[:, 1] - centre[1]) / ry) ** 2)
        radial = np.clip(1.0 - q, 0.0, 1.0) ** float(falloff)
        wv = rim_weight + (strength - rim_weight) * radial
        wv[:att.hull] = rim_weight

        Wnew = np.c_[Wold * (1.0 - wv[:, None]), wv]
        fallback = np.argmax(Wold, axis=1)
        Wnew = finalize(Wnew, min_weight=min_weight, max_influences=max_influences, fallback=fallback)
        bone_names = names + [core]
        bone_ids = [sk.bone_index(n) for n in bone_names]
        att.vertices = skin_vertices(
            pts, Wnew, bone_ids, [world[n] for n in bone_names]
        )

        inf_count = (Wnew > 0).sum(1)
        results[slot] = {
            "peak_volume_weight": round(float(Wnew[:, -1].max()), 4),
            "mean_volume_weight": round(float(Wnew[:, -1].mean()), 4),
            "max_influences": int(inf_count.max()),
            "mean_influences": round(float(inf_count.mean()), 3),
            "vertices": len(pts),
        }

    phys = []
    if physics and physics != "none":
        from .rig import add_physics
        phys = add_physics(sk, [core], physics, taper=0.0)

    test = ""
    if test_animation:
        test = f"{name}_test"
        bounce(project, [core], test, duration=0.72, strength=0.18, wobble=0.035, merge=False)

    return {
        "slots": slots,
        "core": core,
        "parent": par,
        "centre": [round(float(v), 2) for v in centre],
        "strength": strength,
        "falloff": falloff,
        "rim_weight": rim_weight,
        "meshes": results,
        "physics": phys,
        "test_animation": test,
    }


def bounce(project: Project, bones: list[str], animation: str, start: float = 0.0, duration: float = 0.55,
           strength: float = 0.18, wobble: float = 0.03, merge: bool = False) -> dict[str, Any]:
    """Sparse squash/bounce for volume cores.

    Five meaningful scale keys: rest -> impact squash -> rebound -> small settle
    -> rest. No evenly spaced bake.
    """
    if duration <= 0:
        raise ValueError("duration must be > 0")
    if not bones:
        raise ValueError("give one or more volume bones")
    sk = project.data
    for b in bones:
        sk.bone(b)

    ab = AnimBuilder(sk, animation, replace=not merge)
    t = lambda f: r(start + duration * f)  # noqa: E731
    s = float(strength)
    w = float(wobble)
    for i, bone in enumerate(bones):
        sign = -1 if i % 2 else 1
        ab.bone(bone, "scale", [
            (t(0.00), 1.0, 1.0, "quad_in"),
            (t(0.22), 1.0 + 0.68 * s, 1.0 - s, "back_out"),
            (t(0.48), 1.0 - 0.28 * s, 1.0 + 0.48 * s, "sine_in_out"),
            (t(0.72), 1.0 + 0.08 * s, 1.0 - 0.10 * s, "sine_out"),
            (t(1.00), 1.0, 1.0),
        ], "linear")
        if w:
            ab.bone(bone, "translatex", [
                (t(0.00), 0.0, "quad_out"),
                (t(0.28), sign * w * 100.0, "sine_in_out"),
                (t(0.58), -sign * w * 55.0, "sine_in_out"),
                (t(1.00), 0.0),
            ], "linear")
            ab.bone(bone, "rotate", [
                (t(0.00), 0.0, "sine_in_out"),
                (t(0.30), sign * w * 55.0, "sine_in_out"),
                (t(0.62), -sign * w * 28.0, "sine_in_out"),
                (t(1.00), 0.0),
            ], "linear")
    return {
        "animation": animation,
        "bones": bones,
        "start": start,
        "duration": duration,
        "scale_keys_per_bone": 5,
        "sparse": True,
    }
