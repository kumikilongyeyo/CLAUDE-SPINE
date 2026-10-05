"""Silhouette meshes: alpha → outline → simplified hull → constrained triangulation.

Pipeline, and why each step is there:

1. **Mask.** Alpha above a threshold, holes filled, islands bridged into one
   shape (a Spine mesh has exactly one hull).
2. **Pad.** The mask grows by ``pad`` pixels (Euclidean). The outline is traced
   on the grown mask, so it sits ``pad`` away from the art.
3. **Trace.** Moore-neighbour tracing gives the exact pixel outline.
4. **Simplify.** Douglas-Peucker with tolerance below ``pad``. DP keeps every
   traced point within tolerance of the result, and every traced point is at
   least ``pad`` from the art, so the simplified hull still encloses every
   opaque pixel. That is checked afterwards rather than assumed.
5. **Refine.** Hull edges are split so none is longer than the local spacing.
   Near joints the spacing shrinks: a hull edge that spans an elbow cannot
   bend, however good the weights are.
6. **Interior.** Poisson-disk points, denser near joints, kept clear of the
   hull so no sliver triangles form against it.
7. **Triangulate.** A *conforming* Delaunay: any hull edge whose diametral
   circle holds another vertex is split (or the interior vertex dropped) until
   every hull edge is a Gabriel edge, which Delaunay is guaranteed to contain.
   Triangles outside the hull are discarded. A plain clipped Delaunay misses
   hull edges on concave shapes, and Spine's importer then "fixes" the mesh by
   throwing triangles away.

The result always satisfies ``len(triangles) == 2n - hull - 2``, which is what
a valid triangulation of a simple polygon with interior points must have.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage
from scipy.spatial import Delaunay, cKDTree

# Moore neighbourhood, clockwise on screen (image y grows downward).
_DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


@dataclass
class MeshGeom:
    """Points are in image pixels (x right, y down). The first ``hull`` points
    are the outline in order; triangles index into ``points``."""
    points: np.ndarray
    hull: int
    triangles: np.ndarray
    width: int
    height: int
    stats: dict = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.points)


# --------------------------------------------------------------------------- mask
def art_mask(alpha: np.ndarray, threshold: int = 8, min_island: int = 16) -> np.ndarray:
    m = alpha > threshold
    lab, n = ndimage.label(m, structure=np.ones((3, 3)))
    if n > 1:
        sizes = ndimage.sum(m, lab, range(1, n + 1))
        keep = np.zeros(n + 1, bool)
        keep[1:] = sizes >= min_island
        if not keep.any():
            keep[1 + int(np.argmax(sizes))] = True
        m = keep[lab]
    return ndimage.binary_fill_holes(m)


def single_shape(mask: np.ndarray, max_bridge: int = 64) -> np.ndarray:
    """Join islands into one 8-connected shape by closing with a growing disk.
    Falls back to the islands' convex hull when they are too far apart."""
    lab, n = ndimage.label(mask, structure=np.ones((3, 3)))
    if n <= 1:
        return mask
    r = 2
    while r <= max_bridge:
        big = np.pad(mask, r + 1)
        grown = ndimage.distance_transform_edt(~big) <= r
        closed = (ndimage.distance_transform_edt(grown) > r)[r + 1:-r - 1, r + 1:-r - 1] | mask
        closed = ndimage.binary_fill_holes(closed)
        if ndimage.label(closed, structure=np.ones((3, 3)))[1] == 1:
            return closed
        r *= 2
    ys, xs = np.nonzero(mask)
    pts = np.c_[xs, ys].astype(float)
    hull = _convex_hull(pts)
    return polygon_mask(hull, mask.shape) | mask


def _disk(r: int) -> np.ndarray:
    y, x = np.ogrid[-r:r + 1, -r:r + 1]
    return x * x + y * y <= r * r


def pad_mask(mask: np.ndarray, pad: float) -> np.ndarray:
    """Grow by ``pad`` px; the canvas grows too so nothing clips at the border."""
    p = int(np.ceil(pad)) + 2
    big = np.pad(mask, p)
    if pad > 0:
        dist = ndimage.distance_transform_edt(~big)
        big = dist <= pad
    return big, p


# -------------------------------------------------------------------------- trace
def trace_outline(mask: np.ndarray) -> np.ndarray:
    """Moore-neighbour trace of the outer boundary of the (single) shape.
    Returns pixel coordinates (x, y), clockwise on screen, not closed."""
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        raise ValueError("empty mask")
    i0 = np.lexsort((xs, ys))[0]
    start = (int(xs[i0]), int(ys[i0]))
    H, W = mask.shape

    def fg(x, y):
        return 0 <= x < W and 0 <= y < H and mask[y, x]

    out = [start]
    cur, back = start, 4  # we "arrived" from the west, which is background
    second = None
    for _ in range(4 * mask.size + 8):
        found = None
        for i in range(1, 9):
            k = (back + i) % 8
            nx, ny = cur[0] + _DIRS[k][0], cur[1] + _DIRS[k][1]
            if fg(nx, ny):
                found = (k, (nx, ny))
                break
        if found is None:  # isolated pixel
            return np.array(out, float)
        k, nxt = found
        if cur == start and second is not None and nxt == second:
            break
        if second is None:
            second = nxt
        # the last background cell looked at, re-expressed from the new pixel
        lb = (k - 1) % 8 if k != (back + 1) % 8 else back
        bx, by = cur[0] + _DIRS[lb][0] - nxt[0], cur[1] + _DIRS[lb][1] - nxt[1]
        back = _DIRS.index((bx, by))
        cur = nxt
        out.append(cur)
    if len(out) > 1 and out[-1] == start:
        out.pop()
    return np.array(out, float)


# ----------------------------------------------------------------------- simplify
def douglas_peucker_closed(pts: np.ndarray, eps: float) -> np.ndarray:
    n = len(pts)
    if n <= 4:
        return pts.copy()
    # split the ring at its two mutually farthest points
    d = np.linalg.norm(pts - pts[0], axis=1)
    a = int(np.argmax(d))
    d2 = np.linalg.norm(pts - pts[a], axis=1)
    b = int(np.argmax(d2))
    a, b = sorted((a, b))
    keep = np.zeros(n, bool)
    keep[[a, b]] = True
    _dp(pts, a, b, eps, keep)
    ring = np.r_[np.arange(b, n), np.arange(0, a + 1)]
    sub = np.zeros(len(ring), bool)
    _dp_idx(pts, ring, eps, sub)
    keep[ring[sub]] = True
    return pts[keep]


def _dp(pts, i, j, eps, keep):
    stack = [(i, j)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        seg = pts[i + 1:j]
        dist = _point_seg_dist(seg, pts[i], pts[j])
        k = int(np.argmax(dist))
        if dist[k] > eps:
            m = i + 1 + k
            keep[m] = True
            stack += [(i, m), (m, j)]


def _dp_idx(pts, ring, eps, keep):
    keep[0] = keep[-1] = True
    stack = [(0, len(ring) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        seg = pts[ring[i + 1:j]]
        dist = _point_seg_dist(seg, pts[ring[i]], pts[ring[j]])
        k = int(np.argmax(dist))
        if dist[k] > eps:
            m = i + 1 + k
            keep[m] = True
            stack += [(i, m), (m, j)]


def _point_seg_dist(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    L2 = float(ab @ ab)
    if L2 == 0:
        return np.linalg.norm(p - a, axis=-1)
    t = np.clip(((p - a) @ ab) / L2, 0, 1)
    return np.linalg.norm(p - (a + t[..., None] * ab), axis=-1)


def dist_to_polyline(p: np.ndarray, poly: np.ndarray, closed: bool = True) -> np.ndarray:
    """Distance from each point in ``p`` (k,2) to the polygon outline."""
    a = poly
    b = np.roll(poly, -1, axis=0) if closed else poly[1:]
    if not closed:
        a = poly[:-1]
    ab = b - a
    L2 = np.maximum((ab * ab).sum(1), 1e-12)
    ap = p[:, None, :] - a[None]
    t = np.clip((ap * ab[None]).sum(2) / L2[None], 0, 1)
    proj = a[None] + t[..., None] * ab[None]
    return np.linalg.norm(p[:, None, :] - proj, axis=2).min(1)


# ------------------------------------------------------------------------ polygon
def polygon_area(poly: np.ndarray) -> float:
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def points_in_polygon(p: np.ndarray, poly: np.ndarray) -> np.ndarray:
    x, y = p[:, 0][:, None], p[:, 1][:, None]
    x1, y1 = poly[:, 0][None], poly[:, 1][None]
    x2, y2 = np.roll(poly[:, 0], -1)[None], np.roll(poly[:, 1], -1)[None]
    cond = (y1 > y) != (y2 > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        xin = (x2 - x1) * (y - y1) / (y2 - y1) + x1
    return (cond & (x < xin)).sum(1) % 2 == 1


def polygon_mask(poly: np.ndarray, shape) -> np.ndarray:
    """Rasterise a polygon (pixel coords) to a bool mask. PIL does this in C;
    a numpy point-in-polygon over every pixel was O(W·H·n) and ran out of
    memory on a 2K layer."""
    from PIL import Image, ImageDraw
    H, W = shape
    im = Image.new("1", (W, H), 0)
    ImageDraw.Draw(im).polygon([(float(x) - 0.5, float(y) - 0.5) for x, y in poly], fill=1, outline=1)
    return np.array(im, bool)


def _boundary_pixels(mask: np.ndarray) -> np.ndarray:
    """Centres of opaque pixels on the shape's edge. If these are inside the
    hull, so is every opaque pixel (the shape is one hole-filled piece)."""
    inner = ndimage.binary_erosion(mask, structure=np.ones((3, 3)), border_value=0)
    ys, xs = np.nonzero(mask & ~inner)
    return np.c_[xs + 0.5, ys + 0.5]


def uncovered(px: np.ndarray, poly: np.ndarray, tol: float = 0.55) -> int:
    """Count pixel centres outside the polygon by more than ``tol`` px. Exact
    (a rasterised polygon mask disagrees with itself along edges). 0.55 = half
    a pixel plus the ≤0.034 px collinear dent: a pixel centre on the image
    edge row sits exactly 0.5 px from a hull edge that runs along the edge."""
    if len(px) == 0:
        return 0
    out = ~points_in_polygon(px, poly)
    if not out.any():
        return 0
    far = dist_to_polyline(px[out], poly) > tol
    return int(far.sum())


def snap_to_border(poly: np.ndarray, W: int, H: int) -> np.ndarray:
    """Outline points on the image's edge pixels move onto the edge itself, so
    full-bleed art is covered to the last half pixel and UVs stay in 0..1."""
    p = poly.copy()
    # Only the edge row/column itself (traced centres sit at k + 0.5). A wider
    # band would pull both sides of a thin strip onto one line: overlapping
    # collinear edges that look "simple" and triangulate into flat triangles.
    p[:, 0] = np.where(p[:, 0] <= 0.5 + 1e-6, 0.0, np.where(p[:, 0] >= W - 0.5 - 1e-6, float(W), p[:, 0]))
    p[:, 1] = np.where(p[:, 1] <= 0.5 + 1e-6, 0.0, np.where(p[:, 1] >= H - 0.5 - 1e-6, float(H), p[:, 1]))
    # snapping can merge neighbours; drop exact repeats
    keep = np.r_[True, np.any(np.abs(np.diff(p, axis=0)) > 1e-9, axis=1)]
    p = p[keep]
    if len(p) > 1 and np.allclose(p[0], p[-1]):
        p = p[:-1]
    return p


def is_simple(poly: np.ndarray) -> bool:
    """True when no two non-adjacent edges intersect (vectorised O(n²))."""
    n = len(poly)
    if n < 3:
        return False
    a = poly
    b = np.roll(poly, -1, axis=0)

    def orient(p, q, r):
        return np.sign((q[..., 0] - p[..., 0]) * (r[..., 1] - p[..., 1]) -
                       (q[..., 1] - p[..., 1]) * (r[..., 0] - p[..., 0]))

    A, B = a[:, None], b[:, None]
    C, D = a[None], b[None]
    o1, o2 = orient(A, B, C), orient(A, B, D)
    o3, o4 = orient(C, D, A), orient(C, D, B)
    hit = (o1 * o2 < 0) & (o3 * o4 < 0)

    def on_seg(p, q, r):  # r on segment p-q, given collinear
        return ((np.minimum(p[..., 0], q[..., 0]) - 1e-9 <= r[..., 0]) & (r[..., 0] <= np.maximum(p[..., 0], q[..., 0]) + 1e-9) &
                (np.minimum(p[..., 1], q[..., 1]) - 1e-9 <= r[..., 1]) & (r[..., 1] <= np.maximum(p[..., 1], q[..., 1]) + 1e-9))

    # touching / collinear overlap also counts (an edge lying on another edge)
    hit |= (o1 == 0) & on_seg(A, B, C)
    hit |= (o2 == 0) & on_seg(A, B, D)
    hit |= (o3 == 0) & on_seg(C, D, A)
    hit |= (o4 == 0) & on_seg(C, D, B)
    idx = np.arange(n)
    adj = (np.abs(idx[:, None] - idx[None]) <= 1) | (np.abs(idx[:, None] - idx[None]) == n - 1)
    hit &= ~adj
    # duplicate vertices are also a failure
    if len(np.unique(np.round(poly, 6), axis=0)) != n:
        return False
    return not hit.any()


def _convex_hull(pts: np.ndarray) -> np.ndarray:
    pts = np.unique(pts, axis=0)
    pts = pts[np.lexsort((pts[:, 1], pts[:, 0]))]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(tuple(p))
    for p in pts[::-1]:
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(tuple(p))
    return np.array(lower[:-1] + upper[:-1], float)


# ---------------------------------------------------------------------- spacing
def spacing_field(base: float, joints: np.ndarray, joint_radius: float, joint_factor: float):
    """Local target spacing: ``base`` far from joints, ``base*joint_factor`` on
    them, smoothly blended over ``joint_radius``."""
    if joints is None or len(joints) == 0:
        return lambda p: np.full(len(p), base)
    tree = cKDTree(joints)

    def f(p):
        d, _ = tree.query(p)
        t = np.clip(d / max(joint_radius, 1e-6), 0, 1)
        t = t * t * (3 - 2 * t)
        return base * (joint_factor + (1 - joint_factor) * t)

    return f


def refine_ring(poly: np.ndarray, spacing) -> np.ndarray:
    """Split every edge longer than the local spacing into equal pieces."""
    out = []
    n = len(poly)
    for i in range(n):
        a, b = poly[i], poly[(i + 1) % n]
        L = float(np.linalg.norm(b - a))
        s = float(min(spacing(a[None])[0], spacing(b[None])[0], spacing(((a + b) / 2)[None])[0]))
        k = max(1, int(np.ceil(L / max(s, 1e-6) - 1e-9)))
        for j in range(k):
            out.append(a + (b - a) * (j / k))
    return np.array(out)


def poisson_interior(poly: np.ndarray, spacing, base: float, seed: int = 0) -> np.ndarray:
    """Greedy Poisson-disk sampling inside ``poly`` with a variable radius.
    Candidates come from a fine jittered grid; finer cells near joints win."""
    lo, hi = poly.min(0), poly.max(0)
    step = max(base * 0.25, 0.75)
    xs = np.arange(lo[0] + step / 2, hi[0], step)
    ys = np.arange(lo[1] + step / 2, hi[1], step)
    if len(xs) == 0 or len(ys) == 0:
        return np.zeros((0, 2))
    gx, gy = np.meshgrid(xs, ys)
    cand = np.c_[gx.ravel(), gy.ravel()]
    rng = np.random.default_rng(seed)
    cand = cand + rng.uniform(-step * 0.3, step * 0.3, cand.shape)
    cand = cand[points_in_polygon(cand, poly)]
    if len(cand) == 0:
        return cand
    r = spacing(cand)
    edge_d = dist_to_polyline(cand, poly)
    cand, r = cand[edge_d > 0.7 * r], r[edge_d > 0.7 * r]
    if len(cand) == 0:
        return cand
    order = np.lexsort((rng.random(len(cand)), r))  # small radius first
    tree_pts: list[np.ndarray] = []
    radii: list[float] = []
    grid: dict[tuple[int, int], list[int]] = {}
    cell = float(r.min())
    rmax = float(r.max())
    reach = int(np.ceil(rmax / cell))
    for i in order:
        p, ri = cand[i], r[i]
        cx, cy = int(p[0] // cell), int(p[1] // cell)
        ok = True
        for gx_ in range(cx - reach, cx + reach + 1):
            for gy_ in range(cy - reach, cy + reach + 1):
                for j in grid.get((gx_, gy_), ()):
                    if np.hypot(*(tree_pts[j] - p)) < 0.5 * (ri + radii[j]) * 0.92:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            grid.setdefault((cx, cy), []).append(len(tree_pts))
            tree_pts.append(p)
            radii.append(ri)
    return np.array(tree_pts) if tree_pts else np.zeros((0, 2))


# -------------------------------------------------------------------- triangulate
def conforming_delaunay(ring: np.ndarray, interior: np.ndarray, max_rounds: int = 16, max_fix: int = 12):
    """Triangulate a simple polygon (``ring``) plus interior points so every ring
    edge is a mesh edge. Returns (ring, interior, triangles) — the ring may gain
    vertices and the interior may lose ones that encroached on it.

    The Gabriel pass makes every hull edge a Delaunay edge in theory; pixel-grid
    coordinates are full of exact cocircular ties where theory and qhull
    disagree. So the result is *checked*: any hull edge still missing is split
    and the triangulation redone, until none is missing."""
    ring = ring.copy()
    interior = interior.copy() if len(interior) else np.zeros((0, 2))
    ring, interior = _gabriel(ring, interior, max_rounds)
    T = None
    for _ in range(max_fix):
        pts = np.vstack([ring, interior]) if len(interior) else ring
        T = _delaunay_inside(pts, ring)
        missing = _missing_hull_edges(T, len(ring))
        if not missing:
            break
        n = len(ring)
        split = set(missing)
        new = []
        for i in range(n):
            new.append(ring[i])
            if i in split:
                new.append((ring[i] + ring[(i + 1) % n]) / 2)
        # interior points near a split edge are what blocked it
        if len(interior):
            a, b = ring[list(split)], ring[[(i + 1) % n for i in split]]
            mid, rad = (a + b) / 2, np.linalg.norm(b - a, axis=1) / 2
            d = np.linalg.norm(interior[:, None, :] - mid[None], axis=2)
            interior = interior[~(d < rad[None] * 1.5).any(1)]
        ring, interior = _gabriel(np.array(new), interior, max_rounds)
    pts = np.vstack([ring, interior]) if len(interior) else ring
    T = _flip_flat_triangles(pts, T)
    if _missing_hull_edges(T, len(ring)) or len(T) != 2 * len(pts) - len(ring) - 2:
        T, kept = cdt(ring, interior)
        if len(interior):
            interior = interior[kept]
        pts = np.vstack([ring, interior]) if len(interior) else ring
    # orient every triangle the same way (counter-clockwise on screen math)
    p0, p1, p2 = pts[T[:, 0]], pts[T[:, 1]], pts[T[:, 2]]
    cr = (p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1]) - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0])
    T[cr < 0] = T[cr < 0][:, [0, 2, 1]]
    return ring, interior, T


def _gabriel(ring: np.ndarray, interior: np.ndarray, max_rounds: int, min_len: float = 1.0):
    cap = max(4 * len(ring), 64)
    for _ in range(max_rounds):
        if len(ring) > cap:  # an outline running close to itself; leave it to the CDT fallback
            break
        changed = False
        # dent first, so the checks below see final coordinates
        ring = _dent_collinear(ring)
        # interior points inside a hull edge's diametral circle are dropped
        if len(interior):
            a, b = ring, np.roll(ring, -1, axis=0)
            mid, rad = (a + b) / 2, np.linalg.norm(b - a, axis=1) / 2
            d = np.linalg.norm(interior[:, None, :] - mid[None], axis=2)
            bad = (d < rad[None] * 1.0001).any(1)
            if bad.any():
                interior = interior[~bad]
                changed = True
        # ring vertices inside another hull edge's diametral circle split it
        a, b = ring, np.roll(ring, -1, axis=0)
        mid, rad = (a + b) / 2, np.linalg.norm(b - a, axis=1) / 2
        d = np.linalg.norm(ring[:, None, :] - mid[None], axis=2)
        n = len(ring)
        idx = np.arange(n)
        d[idx, idx] = np.inf
        d[(idx + 1) % n, idx] = np.inf
        # strict: counting ties splits symmetric pixel grids forever; ties that
        # matter are caught by the missing-edge check in conforming_delaunay
        enc = (d < rad[None] * 0.9999).any(0) & (rad * 2 > min_len)
        if enc.any():
            new = []
            for i in range(n):
                new.append(ring[i])
                if enc[i]:
                    new.append((ring[i] + ring[(i + 1) % n]) / 2)
            ring = np.array(new)
            changed = True
        if not changed:
            break
    return _dent_collinear(ring), interior


def _delaunay_inside(pts: np.ndarray, ring: np.ndarray) -> np.ndarray:
    tri = Delaunay(pts, qhull_options="QJ Pp" if len(pts) < 4 else "Qbb Qc Qz")
    T = tri.simplices
    return T[points_in_polygon(pts[T].mean(1), ring)]


def _missing_hull_edges(T: np.ndarray, hull: int) -> list[int]:
    edges = set()
    for t in T:
        for k in range(3):
            a, b = int(t[k]), int(t[(k + 1) % 3])
            edges.add((min(a, b), max(a, b)))
    return [i for i in range(hull) if (min(i, (i + 1) % hull), max(i, (i + 1) % hull)) not in edges]


# ------------------------------------------------------------------- exact CDT
def _orient(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _ear_clip(poly: np.ndarray) -> list[list[int]]:
    """Triangulate a simple polygon (any orientation) by ear clipping."""
    n = len(poly)
    idx = list(range(n))
    sgn = 1.0 if polygon_area(poly) > 0 else -1.0
    tris = []
    guard = 0
    while len(idx) > 3 and guard < 10 * n * n:
        guard += 1
        m = len(idx)
        cut = False
        best = None
        for k in range(m):
            i0, i1, i2 = idx[(k - 1) % m], idx[k], idx[(k + 1) % m]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if sgn * _orient(a, b, c) <= 1e-12:
                continue  # reflex or flat
            others = [j for j in idx if j not in (i0, i1, i2)]
            if others:
                P = poly[others]
                d1 = sgn * ((b[0] - a[0]) * (P[:, 1] - a[1]) - (b[1] - a[1]) * (P[:, 0] - a[0]))
                d2 = sgn * ((c[0] - b[0]) * (P[:, 1] - b[1]) - (c[1] - b[1]) * (P[:, 0] - b[0]))
                d3 = sgn * ((a[0] - c[0]) * (P[:, 1] - c[1]) - (a[1] - c[1]) * (P[:, 0] - c[0]))
                if ((d1 >= 0) & (d2 >= 0) & (d3 >= 0)).any():
                    continue
            # prefer the fattest ear: better triangles before the Delaunay flips
            q = abs(_orient(a, b, c)) / (np.sum((b - a) ** 2) + np.sum((c - b) ** 2) + np.sum((a - c) ** 2))
            if best is None or q > best[0]:
                best = (q, k, (i0, i1, i2))
        if best is not None:
            tris.append(list(best[2]))
            del idx[best[1]]
            cut = True
        if not cut:
            # only flat ears left (collinear run): clip one anyway
            tris.append([idx[-1], idx[0], idx[1]])
            del idx[0]
    tris.append(idx[:3])
    return tris


def _in_circle(a, b, c, d) -> bool:
    """d strictly inside the circumcircle of triangle abc (any orientation)."""
    m = np.array([[a[0] - d[0], a[1] - d[1], (a[0] - d[0]) ** 2 + (a[1] - d[1]) ** 2],
                  [b[0] - d[0], b[1] - d[1], (b[0] - d[0]) ** 2 + (b[1] - d[1]) ** 2],
                  [c[0] - d[0], c[1] - d[1], (c[0] - d[0]) ** 2 + (c[1] - d[1]) ** 2]])
    det = np.linalg.det(m)
    return det * np.sign(_orient(a, b, c)) > 1e-9


def cdt(ring: np.ndarray, interior: np.ndarray):
    """Constrained Delaunay triangulation: ear-clip the outline, Lawson-flip to
    Delaunay (hull edges are never flipped), then insert interior points one
    at a time with flips. Valid by construction for any simple polygon — the
    fallback when qhull's unconstrained result cannot be made to conform.
    Returns (triangles, kept) where ``kept`` masks the interior points used
    (a point lying exactly on the outline is dropped)."""
    pts = np.vstack([ring, interior]) if len(interior) else ring.copy()
    h = len(ring)
    hull_edges = {(min(i, (i + 1) % h), max(i, (i + 1) % h)) for i in range(h)}
    tris: dict[int, list[int]] = {}
    edge_map: dict[tuple[int, int], set[int]] = {}
    nid = [0]

    def key(a, b):
        return (a, b) if a < b else (b, a)

    def add(t):
        k = nid[0]
        nid[0] += 1
        tris[k] = t
        for i in range(3):
            edge_map.setdefault(key(t[i], t[(i + 1) % 3]), set()).add(k)
        return k

    def remove(k):
        t = tris.pop(k)
        for i in range(3):
            edge_map[key(t[i], t[(i + 1) % 3])].discard(k)

    def legalize(stack):
        guard = 0
        while stack and guard < 50000:
            guard += 1
            u, v = stack.pop()
            e = key(u, v)
            if e in hull_edges:
                continue
            ts = list(edge_map.get(e, ()))
            if len(ts) != 2:
                continue
            t1, t2 = tris[ts[0]], tris[ts[1]]
            w1 = next(x for x in t1 if x not in e)
            w2 = next(x for x in t2 if x not in e)
            a, b = pts[e[0]], pts[e[1]]
            if not _in_circle(a, b, pts[w1], pts[w2]):
                continue
            # flip only if the quad is convex (both new triangles proper)
            if _orient(pts[w1], pts[w2], a) * _orient(pts[w1], pts[w2], b) >= 0:
                continue
            remove(ts[0])
            remove(ts[1])
            add([w1, w2, e[0]])
            add([w2, w1, e[1]])
            stack += [(w1, e[0]), (e[0], w2), (w2, e[1]), (e[1], w1)]

    for t in _ear_clip(ring):
        add(t)
    legalize([(i, j) for i, j in edge_map.keys()])

    for p in range(h, len(pts)):
        P = pts[p]
        ks = list(tris.keys())
        T = np.array([tris[k] for k in ks])
        A, B, C = pts[T[:, 0]], pts[T[:, 1]], pts[T[:, 2]]
        area = (B[:, 0] - A[:, 0]) * (C[:, 1] - A[:, 1]) - (B[:, 1] - A[:, 1]) * (C[:, 0] - A[:, 0])
        l1 = ((B[:, 0] - P[0]) * (C[:, 1] - P[1]) - (B[:, 1] - P[1]) * (C[:, 0] - P[0])) / area
        l2 = ((C[:, 0] - P[0]) * (A[:, 1] - P[1]) - (C[:, 1] - P[1]) * (A[:, 0] - P[0])) / area
        l3 = 1 - l1 - l2
        mn = np.minimum(np.minimum(l1, l2), l3)
        j = int(np.argmax(mn))
        if mn[j] < -1e-9:
            continue  # outside the outline (should not happen); skip the point
        a, b, c = tris[ks[j]]
        lam = (l1[j], l2[j], l3[j])
        if min(lam) < 1e-7:
            # on an edge: split the triangle(s) sharing it
            opp = [a, b, c][int(np.argmin(lam))]
            e = [x for x in (a, b, c) if x != opp]
            ek = key(*e)
            if ek in hull_edges:
                continue  # on the outline: drop the point
            for k in list(edge_map.get(ek, ())):
                t = tris[k]
                w = next(x for x in t if x not in ek)
                remove(k)
                add([e[0], w, p])
                add([w, e[1], p])
            stack = [(x, y) for k2 in list(edge_map.get(key(e[0], p), ())) + list(edge_map.get(key(e[1], p), ()))
                     for t2 in [tris[k2]] for x, y in ((t2[0], t2[1]), (t2[1], t2[2]), (t2[2], t2[0])) if p not in (x, y)]
            legalize(stack)
            continue
        remove(ks[j])
        add([a, b, p])
        add([b, c, p])
        add([c, a, p])
        legalize([(a, b), (b, c), (c, a)])

    T = np.array(list(tris.values()), dtype=np.int64)
    used = np.zeros(len(pts), bool)
    used[T.ravel()] = True
    kept = used[h:]
    if not kept.all():
        remap = np.cumsum(used) - 1
        T = remap[T]
    return T, kept


def _dent_collinear(ring: np.ndarray, eps: float = 0.02) -> np.ndarray:
    """Move every hull vertex that lies on a straight run (edge refinement and
    midpoint splits make many) a hair inward. Three collinear points on the
    point set's convex hull make qhull emit zero-area triangles; a long run of
    them defeats any flip repair. After the dent, the would-be sliver lies
    outside the outline and is discarded with the other outside triangles.
    0.02 px stays above the 1e-3 rounding of saved vertices and far below
    the outline padding, so no art is exposed."""
    n = len(ring)
    if n < 4:
        return ring
    a, b, c = np.roll(ring, 1, axis=0), ring, np.roll(ring, -1, axis=0)
    cross = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    span = np.linalg.norm(c - a, axis=1)
    flat = np.abs(cross) < 1e-6 * np.maximum(span, 1e-9) ** 2 + 1e-9
    # only straight runs: b between a and c, not the tip of a needle
    flat &= ((b - a) * (c - b)).sum(1) > 0
    if not flat.any():
        return ring
    d = (c - a) / np.maximum(span, 1e-12)[:, None]
    nrm = np.c_[-d[:, 1], d[:, 0]]
    out = ring.copy()
    sign = 1.0 if polygon_area(ring) > 0 else -1.0
    for i in np.nonzero(flat)[0]:
        k = eps * (1 + 0.37 * (i % 3))  # vary so dented runs are not collinear either
        cand = ring[i] + sign * nrm[i] * k
        if not points_in_polygon(cand[None], ring)[0]:
            cand = ring[i] - sign * nrm[i] * k
        if not _moves_cleanly(out, i, cand):
            continue
        out[i] = cand
    return out


def _seg_hits(p, q, A, B) -> np.ndarray:
    """Whether segment p-q touches each segment A[k]-B[k] (vectorised)."""
    def orient(a, b, c):
        return np.sign((b[..., 0] - a[..., 0]) * (c[..., 1] - a[..., 1]) - (b[..., 1] - a[..., 1]) * (c[..., 0] - a[..., 0]))
    P, Q = np.broadcast_to(p, A.shape), np.broadcast_to(q, A.shape)
    o1, o2, o3, o4 = orient(P, Q, A), orient(P, Q, B), orient(A, B, P), orient(A, B, Q)
    return ((o1 * o2 < 0) & (o3 * o4 < 0)) | ((o1 == 0) & (o2 == 0) & (o3 == 0) & (o4 == 0))


def _moves_cleanly(ring: np.ndarray, i: int, new: np.ndarray) -> bool:
    """Moving vertex i to ``new`` keeps the ring simple: its two edges must not
    touch any non-adjacent edge. O(n), unlike a full is_simple."""
    n = len(ring)
    a, b = ring, np.roll(ring, -1, axis=0)
    prev, nxt = ring[(i - 1) % n], ring[(i + 1) % n]
    for (p, q, skip) in ((prev, new, {(i - 2) % n, (i - 1) % n, i}), (new, nxt, {(i - 1) % n, i, (i + 1) % n})):
        keep = np.array([k not in skip for k in range(n)])
        if _seg_hits(p, q, a[keep], b[keep]).any():
            return False
    return True


def _flip_flat_triangles(pts: np.ndarray, T: np.ndarray) -> np.ndarray:
    """Refined hull edges put vertices exactly on straight lines, and qhull
    can return a zero-area triangle (a, b, c) through three of them. Dropping it
    would leave b as a T-junction; instead flip it with its neighbour across
    the long edge a-c: (a, b, c) + (a, c, d) → (a, b, d) + (b, c, d)."""
    T = [list(map(int, t)) for t in T]
    scale = float(np.ptp(pts, axis=0).max()) or 1.0
    for _ in range(len(T)):
        flat = None
        for k, t in enumerate(T):
            a, b, c = pts[t[0]], pts[t[1]], pts[t[2]]
            if abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < 1e-9 * scale * scale:
                flat = k
                break
        if flat is None:
            break
        t = T[flat]
        # the middle vertex is the one opposite the longest edge
        L = [np.linalg.norm(pts[t[(i + 1) % 3]] - pts[t[(i + 2) % 3]]) for i in range(3)]
        m = int(np.argmax(L))
        b, a, c = t[m], t[(m + 1) % 3], t[(m + 2) % 3]
        nb = next((j for j, u in enumerate(T) if j != flat and a in u and c in u), None)
        if nb is None:
            del T[flat]  # flat sliver on the outside: nothing to keep
            continue
        d = next(v for v in T[nb] if v not in (a, c))
        for j in sorted((flat, nb), reverse=True):
            del T[j]
        T += [[a, b, d], [b, c, d]]
    return np.array(T, dtype=np.int64).reshape(-1, 3)


def triangulation_ok(points: np.ndarray, hull: int, tris: np.ndarray) -> tuple[bool, str]:
    n = len(points)
    want = 2 * n - hull - 2
    if len(tris) != want:
        return False, f"{len(tris)} triangles, a valid mesh of {n} vertices / {hull} hull has {want}"
    p0, p1, p2 = points[tris[:, 0]], points[tris[:, 1]], points[tris[:, 2]]
    area = 0.5 * np.abs((p1[:, 0] - p0[:, 0]) * (p2[:, 1] - p0[:, 1]) - (p1[:, 1] - p0[:, 1]) * (p2[:, 0] - p0[:, 0]))
    if (area < 1e-6).any():
        return False, f"{int((area < 1e-6).sum())} degenerate triangles"
    poly_a = abs(polygon_area(points[:hull]))
    if abs(area.sum() - poly_a) > 1e-3 * poly_a + 1e-6:
        return False, f"triangles cover {area.sum():.1f} px² but the hull is {poly_a:.1f} px² (overlap or gap)"
    # every hull edge must be a triangle edge
    edges = set()
    for t in tris:
        for i in range(3):
            a, b = int(t[i]), int(t[(i + 1) % 3])
            edges.add((min(a, b), max(a, b)))
    for i in range(hull):
        a, b = i, (i + 1) % hull
        if (min(a, b), max(a, b)) not in edges:
            return False, f"hull edge {a}-{b} is not in the triangulation"
    return True, "ok"


# ---------------------------------------------------------------------- top level
def build_mesh_geom(alpha: np.ndarray, joints=None, detail: float = 1.0, pad: float = 2.0,
                    threshold: int = 8, max_vertices: int = 400, joint_factor: float = 0.45,
                    seed: int = 0) -> MeshGeom:
    """Build a clean mesh for an image's alpha channel.

    joints        image-space (x, y) points where the mesh must bend: vertex
                  density rises around them and hull vertices are forced nearby.
    detail        1.0 = balanced. 2.0 roughly doubles vertex density per axis.
    max_vertices  hard cap; spacing is widened until the mesh fits.
    """
    H, W = alpha.shape
    mask = art_mask(alpha, threshold)
    if not mask.any():
        raise ValueError("image has no opaque pixels above the alpha threshold")
    mask = single_shape(mask)
    big, off = pad_mask(mask, pad)
    # The pad must not leave the image: UVs outside 0..1 are clamped by the
    # Spine editor on import, which silently shifts the texture on the mesh.
    inside_img = np.pad(big[off:off + H, off:off + W], 1)
    raw = trace_outline(inside_img) - 1 + 0.5  # pixel centres, image coords
    joints_a = np.asarray(joints, float).reshape(-1, 2) if joints is not None and len(joints) else np.zeros((0, 2))

    area = float(mask.sum())
    diag = float(np.hypot(*(np.ptp(np.argwhere(mask), axis=0) + 1)))
    eps = max(0.6, min(pad * 0.8, pad - 0.25))
    edge_px = _boundary_pixels(mask)
    hull0, best = None, None
    for _ in range(9):
        cand = snap_to_border(douglas_peucker_closed(raw, eps), W, H)
        # simplicity is checked AFTER the border snap: snapping can fold a
        # thin sliver along the edge into a zero-width spike
        if len(cand) >= 3 and is_simple(cand):
            if polygon_area(cand) < 0:
                cand = cand[::-1]
            leak = uncovered(edge_px, cand)
            if best is None or leak < best[0]:
                best = (leak, cand)
            if leak == 0:
                hull0 = cand
                break
        eps *= 0.6
    if hull0 is None:
        if best is None:
            raise ValueError("could not simplify the outline into a simple polygon")
        hull0 = best[1]

    base = max(np.sqrt(area / 60.0) / detail, diag / 40.0, 3.0)
    joint_radius = max(base * 2.5, diag * 0.12)
    for attempt in range(10):
        spacing = spacing_field(base, joints_a, joint_radius, joint_factor)
        ring = refine_ring(hull0, lambda p: spacing(p) * 1.15)
        interior = poisson_interior(ring, spacing, base * joint_factor, seed=seed)
        ring, interior, tris = conforming_delaunay(ring, interior)
        n = len(ring) + len(interior)
        if n <= max_vertices:
            break
        base *= np.sqrt(n / max_vertices) * 1.05
    pts = np.vstack([ring, interior]) if len(interior) else ring
    ok, why = triangulation_ok(pts, len(ring), tris)
    if not ok:
        raise ValueError(f"triangulation failed validation: {why}")
    leaked = uncovered(edge_px, ring)
    return MeshGeom(points=pts, hull=len(ring), triangles=tris, width=W, height=H,
                    stats={"vertices": len(pts), "hull": len(ring), "triangles": len(tris),
                           "spacing": round(float(base), 2), "uncovered_px": leaked,
                           "coverage_ratio": round(area / max(abs(polygon_area(ring)), 1), 3)})
