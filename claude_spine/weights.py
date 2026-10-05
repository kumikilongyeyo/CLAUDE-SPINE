"""Automatic skin weights by bone-heat diffusion (Baran & Popović, "Automatic
Rigging and Animation of 3D Characters", 2007), adapted to 2D meshes.

Why not inverse distance to joints: a vertex halfway along a long upper arm is
about as close to the elbow as to the shoulder, so it gets pulled half onto the
forearm and the whole arm bends like rubber. Heat weights measure distance to
bone *segments* and then diffuse over the mesh surface, so

* a vertex on a bone belongs to that bone (weight 1 at the bone itself),
* weights fall off smoothly across joints instead of by straight-line distance,
* heat does not jump across a gap in the art (two fingers, an arm in front of
  the body), because it can only travel through mesh triangles.

The solve, per bone j:   (L + A·H) w_j = A·H·p_j

L   cotangent Laplacian of the mesh (surface smoothness)
A   lumped vertex areas
H   diagonal "heat" 1/d², d = distance to the nearest bone segment the vertex
    can see in a straight line inside the outline
p_j 1 where bone j is that nearest visible bone

Then weights are clamped to ≥ 0, influences under ``min_weight`` pruned, at most
``max_influences`` kept, and each vertex renormalised to sum to exactly 1.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.sparse import coo_matrix, diags
from scipy.sparse.linalg import factorized

from .geometry import points_in_polygon


@dataclass
class BoneSeg:
    name: str
    head: tuple[float, float]
    tail: tuple[float, float]


def seg_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray):
    ab = b - a
    L2 = float(ab @ ab)
    if L2 < 1e-12:
        return np.linalg.norm(p - a, axis=1), np.repeat(a[None], len(p), 0)
    t = np.clip(((p - a) @ ab) / L2, 0, 1)
    q = a + t[:, None] * ab
    return np.linalg.norm(p - q, axis=1), q


def cotan_laplacian(pts: np.ndarray, tris: np.ndarray):
    n = len(pts)
    I, J, V = [], [], []
    area = np.zeros(n)
    for k in range(3):
        i, j, o = tris[:, k], tris[:, (k + 1) % 3], tris[:, (k + 2) % 3]
        u, v = pts[i] - pts[o], pts[j] - pts[o]
        cross = np.abs(u[:, 0] * v[:, 1] - u[:, 1] * v[:, 0])
        dot = (u * v).sum(1)
        cot = dot / np.maximum(cross, 1e-12)
        # Obtuse angles give negative cotangents; on a Delaunay mesh the two
        # per-edge halves still sum ≥ 0, and clamping keeps the system an
        # M-matrix (no negative weights from the solve itself).
        w = 0.5 * cot
        I += [i, j]
        J += [j, i]
        V += [w, w]
    p0, p1, p2 = pts[tris[:, 0]], pts[tris[:, 1]], pts[tris[:, 2]]
    ta = 0.5 * np.abs((p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1]) - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0]))
    for k in range(3):
        np.add.at(area, tris[:, k], ta / 3)
    W = coo_matrix((np.concatenate(V), (np.concatenate(I), np.concatenate(J))), shape=(n, n)).tocsr()
    W.data = np.maximum(W.data, 0)
    W.eliminate_zeros()
    L = diags(np.asarray(W.sum(1)).ravel()) - W
    return L.tocsc(), np.maximum(area, 1e-9)


def _visible(p: np.ndarray, q: np.ndarray, hull: np.ndarray, samples: int = 6) -> np.ndarray:
    """Whether the straight line p→q stays inside the outline (sampled)."""
    ok = np.ones(len(p), bool)
    for t in np.linspace(0.15, 0.85, samples):
        ok &= points_in_polygon(p + (q - p) * t, hull)
    return ok


def heat_weights(pts: np.ndarray, tris: np.ndarray, hull_count: int, bones: list[BoneSeg],
                 min_weight: float = 0.05, max_influences: int = 4, heat: float = 1.0,
                 smooth: float = 1.0) -> np.ndarray:
    """Return an (n_vertices, n_bones) weight matrix whose rows sum to 1.

    smooth  >1 spreads weights wider across joints, <1 tightens them.
    """
    n, B = len(pts), len(bones)
    if B == 0:
        raise ValueError("need at least one bone")
    if B == 1:
        return np.ones((n, 1))
    hull = pts[:hull_count]
    D = np.zeros((n, B))
    Q = np.zeros((n, B, 2))
    for j, b in enumerate(bones):
        D[:, j], Q[:, j] = seg_distance(pts, np.asarray(b.head, float), np.asarray(b.tail, float))
    vis = np.zeros((n, B), bool)
    for j in range(B):
        vis[:, j] = _visible(pts, Q[:, j], hull) | (D[:, j] < 1e-6)
    Dv = np.where(vis, D, np.inf)
    none = ~np.isfinite(Dv).any(1)
    Dv[none] = D[none]  # nothing visible: fall back to plain nearest
    dmin = Dv.min(1)
    scale = float(np.ptp(pts, axis=0).max()) or 1.0
    dmin_c = np.maximum(dmin, 1e-3 * scale)
    nearest = np.isclose(Dv, dmin[:, None], rtol=1e-6, atol=1e-6 * scale)
    P = nearest / nearest.sum(1, keepdims=True)

    L, A = cotan_laplacian(pts, tris)
    Hdiag = heat / (dmin_c ** 2) / max(smooth, 1e-6) ** 2
    M = (L + diags(A * Hdiag)).tocsc()
    solve = factorized(M)
    rhs = (A * Hdiag)[:, None] * P
    Wt = np.column_stack([solve(rhs[:, j]) for j in range(B)])
    return finalize(Wt, min_weight, max_influences, fallback=np.argmin(Dv, 1))


def finalize(W: np.ndarray, min_weight: float = 0.05, max_influences: int = 4, fallback=None) -> np.ndarray:
    W = np.clip(np.nan_to_num(W, nan=0.0), 0, None)
    s = W.sum(1, keepdims=True)
    W = np.divide(W, s, out=np.zeros_like(W), where=s > 0)
    if max_influences and W.shape[1] > max_influences:
        cut = -np.sort(-W, axis=1)[:, max_influences - 1:max_influences]
        W[W < cut] = 0
        # ties at the cut can still leave too many; keep the first ones
        over = (W > 0).sum(1) > max_influences
        for i in np.nonzero(over)[0]:
            keep = np.argsort(-W[i])[:max_influences]
            row = np.zeros_like(W[i])
            row[keep] = W[i, keep]
            W[i] = row
    W[W < min_weight] = 0
    s = W.sum(1, keepdims=True)
    empty = s[:, 0] <= 0
    if empty.any():
        fb = fallback if fallback is not None else np.zeros(len(W), int)
        W[empty] = 0
        W[np.nonzero(empty)[0], np.asarray(fb)[empty]] = 1
        s = W.sum(1, keepdims=True)
    return W / s


def skin_vertices(world_pts: np.ndarray, W: np.ndarray, bone_indices: list[int], bone_worlds: list,
                  decimals: int = 3) -> list[float]:
    """Encode weighted vertices in Spine's mesh layout:
    per vertex ``[count, (boneIndex, localX, localY, weight) * count]``."""
    out: list[float] = []
    for i, (x, y) in enumerate(world_pts):
        nz = np.nonzero(W[i])[0]
        out.append(len(nz))
        ws = np.round(W[i, nz], 4)
        ws[-1] = round(1.0 - float(ws[:-1].sum()), 4)  # exact sum after rounding
        for j, w in zip(nz, ws):
            lx, ly = bone_worlds[j].to_local(float(x), float(y))
            out += [bone_indices[j], round(lx, decimals), round(ly, decimals), float(w)]
    return out


def decode_weighted(vertices: list[float], n: int):
    """Inverse of :func:`skin_vertices`: list of [(boneIndex, x, y, w), ...]."""
    res, i = [], 0
    for _ in range(n):
        c = int(vertices[i]); i += 1
        inf = []
        for _ in range(c):
            inf.append((int(vertices[i]), vertices[i + 1], vertices[i + 2], vertices[i + 3]))
            i += 4
        res.append(inf)
    if i != len(vertices):
        raise ValueError("weighted vertex data length does not match the vertex count")
    return res
