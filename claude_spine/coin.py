"""An extruded spinning coin: the ``rig_coin`` and ``coin_spin`` tools' engine.

A flat ``scaleX = cos`` card flip reads as a sticker. A real coin is a disc with a THICKNESS: while it turns, its
near face slides one way, its far face the other, and the reeded side wall shows between them. Here:

* two face bones under the coin bone carry the near face (``<name>_f``: x = +T/2 sin(theta), scaleX = cos(theta))
  and the far face (``<name>_eb``: x = -T/2 sin(theta), scaleX = cos(theta));
* the side wall is ONE weighted cylinder mesh bound to those two bones: its front ring of vertices follows the near
  face bone, its back ring the far face bone, joined by a quad strip, so the silhouette is exact and nothing is keyed
  per vertex. The rings are inset 0.8 px so the hidden half never fringes past the face disc;
* only the face that points at the camera has an attachment, swapped EXACTLY at the cos = 0 crossings (both faces
  are zero wide there, so the swap cannot pop). The back face shows the same picture (or its own art) with
  scaleX = -1 and x mirrored, which un-mirrors it while its bone's scale is negative;
* slot colours shade the faces by how much they face the camera and brighten the wall when it is edge-on.

Spin angles come from relative speed profiles normalised to EXACTLY the asked number of turns, so a spin always
stops face-on. Traps kept from the job this was ported from: weighted vertices index bones by POSITION (every bone is
added before the mesh is built, and ``add_bone`` remaps later inserts), scale timelines MULTIPLY the setup scale, the
face swap must be keyed at the exact crossing time, the rim UVs stay in 0..1.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion, binary_fill_holes, label

from .ir import (Animation, Bone, EventData, EventKey, Key, MeshAttachment, RegionAttachment, Slot, color_hex,
                 parse_color)
from .mesh import region_pixel_to_local, to_local, to_world
from .project import Project
from .sphere import _put
from .timeline import EASE, color_keys, keys as make_keys, r

DEPTHS = {"thin": 0.065, "medium": 0.13, "thick": 0.26}      # thickness / diameter; medium (0.13) is the approved coin
GOLD = (226, 130, 7)
RIM_N = 48              # segments round the rim mesh
HZ = 60.0               # key density
INSET_PX = 0.8          # rim inset so the hidden half never fringes past the face disc
MODES = ("loop", "flip", "spin_up", "slow_down", "land")
SETTLE = 0.7            # landing squash length after a "land"


# ------------------------------------------------------------------ measuring the art
def fit_disc(img: Image.Image, seed: int = 0) -> tuple[float, float, float]:
    """(cx, cy, radius) of the coin disc in the art, in image pixels (y down).

    The outline of the NEAR-OPAQUE area (alpha > 0.9: a drop shadow or glow is usually softer than that) is fitted
    with a RANSAC circle, so anything poking out on one side (which drags the bounding box and the alpha centroid)
    does not move the disc: the longest circular arc wins, and when two arcs tie (an opaque shadow the size of the
    coin) the upper one, since shadows fall down. Falls back to alpha > 0.5 for art that is never that opaque.
    """
    a = np.asarray(img.convert("RGBA"))[..., 3].astype(float) / 255.0
    best = None
    for thr, inward in ((0.9, 0.4), (0.5, 0.0)):
        fit = _fit_outline(a > thr, seed)
        if fit is None:
            continue
        cx, cy, rr, support = fit
        # edge pixels' centres sit half a pixel inside the mask, and the 90 % contour ~0.4 px inside the 50 % one
        cand = (cx, cy, rr + 0.5 + inward)
        if support >= 0.5:
            return tuple(float(v) for v in cand)
        best = best or cand
    if best is None:
        raise ValueError("could not find a round coin in the art's alpha")
    return tuple(float(v) for v in best)


def _fit_outline(m: np.ndarray, seed: int):
    """RANSAC circle on the outer outline of the largest blob of mask m: (cx, cy, r, support) where support is the
    fraction of the circle's circumference the outline covers, or None."""
    m = binary_fill_holes(m)
    lab, n = label(m)
    if n == 0:
        return None
    if n > 1:
        sizes = np.bincount(lab.ravel())
        sizes[0] = 0
        m = lab == int(sizes.argmax())
    edge = m & ~binary_erosion(m)
    ys, xs = np.nonzero(edge)
    pts = np.c_[xs + 0.5, ys + 0.5]
    if len(pts) < 12:
        return None
    rng = np.random.default_rng(seed)
    cands = []
    lim = max(m.shape) * 0.75
    for _ in range(500):
        c = _circle3(pts[rng.choice(len(pts), 3, replace=False)])
        if c is None or not 4 < c[2] < lim:
            continue
        cands.append((int((np.abs(np.hypot(pts[:, 0] - c[0], pts[:, 1] - c[1]) - c[2]) < 1.5).sum()), c))
    if not cands:
        return None
    top = max(nin for nin, _ in cands)
    cx, cy, rr = min((c for nin, c in cands if nin >= 0.9 * top), key=lambda c: c[1])     # ties: the upper arc
    for tol in (1.5, 1.0):                                  # refine on the inliers (algebraic least squares)
        d = np.abs(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - rr)
        q = pts[d < tol]
        if len(q) < 6:
            return None
        A = np.c_[2 * q, np.ones(len(q))]
        sol, *_ = np.linalg.lstsq(A, (q ** 2).sum(1), rcond=None)
        cx, cy = sol[0], sol[1]
        rr = math.sqrt(max(sol[2] + cx * cx + cy * cy, 1e-9))
    nin = int((np.abs(np.hypot(pts[:, 0] - cx, pts[:, 1] - cy) - rr) < 1.0).sum())
    # an 8-connected outline has ~1.1 pixels per unit of arc length (diagonals count less)
    return cx, cy, rr, nin / (2 * math.pi * rr * 1.1)


def _circle3(p):
    (x1, y1), (x2, y2), (x3, y3) = p
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-9:
        return None
    s1, s2, s3 = x1 * x1 + y1 * y1, x2 * x2 + y2 * y2, x3 * x3 + y3 * y3
    ux = (s1 * (y2 - y3) + s2 * (y3 - y1) + s3 * (y1 - y2)) / d
    uy = (s1 * (x3 - x2) + s2 * (x1 - x3) + s3 * (x2 - x1)) / d
    return ux, uy, math.hypot(x1 - ux, y1 - uy)


def rim_colour_from(img: Image.Image, cx: float, cy: float, R: float) -> tuple[int, int, int]:
    """The metal colour of the face art's outer ring (median of the 80-95 % band), brought to the rim's brightness;
    gold when the ring is too dark or too grey-black to say."""
    a = np.asarray(img.convert("RGBA")).astype(float)
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    rr = np.hypot(xx + 0.5 - cx, yy + 0.5 - cy) / R
    m = (rr > 0.80) & (rr < 0.95) & (a[..., 3] > 230)
    if m.sum() < 20:
        return GOLD
    c = np.median(a[..., :3][m], axis=0)
    if c.max() < 24:
        return GOLD
    c = c * (226.0 / c.max())
    return tuple(int(round(v)) for v in c)


def make_rim(base=GOLD, ridges: int = 26, w: int = 32, per: int = 28) -> Image.Image:
    """Reeded rim texture, unrolled: x = across the thickness, y = once round the coin (seamless). `base` is the
    metal's body colour; the groove and highlight are derived from it (gold gives the approved coin's palette)."""
    b = np.asarray(base, float) / 255.0
    body = b * 255
    groove = 255 * 0.73 * b ** 1.78
    hi = 255 * (1 - 0.77 * (1 - b) ** 1.69)
    h = ridges * per
    phi = np.arange(h) / h * 2 * math.pi
    u = ((np.arange(h) / per) % 1.0)[:, None]
    col = np.where(u < 0.16, groove + (body - groove) * (np.clip(u / 0.16, 0, 1) ** 0.6),
          np.where(u < 0.5, body + (hi - body) * (np.clip((u - 0.16) / 0.34, 0, 1) ** 1.5),
          np.where(u < 0.64, hi, hi + (groove - hi) * (np.clip((u - 0.64) / 0.36, 0, 1) ** 0.8))))
    light = np.cos(phi - math.radians(-130)) * 0.5 + 0.5                 # lit from the upper left
    col = col * (0.50 + 0.55 * light)[:, None]
    x = (np.arange(w) + 0.5) / w * 2 - 1
    xs = 1 - 0.20 * np.abs(x) ** 3                                     # soft bevel where it meets each face
    img = col[:, None, :] * xs[None, :, None]
    out = np.dstack([np.clip(img / 255, 0, 1), np.ones((h, w))])
    return Image.fromarray((out * 255).round().astype(np.uint8), "RGBA")


def rim_mesh(sk, front_bone: str, back_bone: str, R: float, T: float, path: str, inset: float = INSET_PX,
             n: int = RIM_N) -> MeshAttachment:
    """The side wall: two rings of vertices (front ring -> the near face bone, back ring -> the far face bone, each
    weight 1) joined by a quad strip. Bone indices are positions in the bone list: build it after every bone exists.
    width / height carry the wall's real size (thickness T, circumference 2 pi R); coin_spin reads T back from it."""
    Rm = R - inset
    fi, bi = sk.bone_index(front_bone), sk.bone_index(back_bone)
    verts, uvs = [], []
    for k in range(n + 1):                       # front ring, uv column 0, top -> bottom
        phi = 2 * math.pi * k / n
        verts += [1, fi, round(Rm * math.cos(phi), 3), round(Rm * math.sin(phi), 3), 1.0]
        uvs += [0.0, round(k / n, 5)]
    for j in range(n + 1):                       # back ring reversed, uv column 1, bottom -> top
        k = n - j
        phi = 2 * math.pi * k / n
        verts += [1, bi, round(Rm * math.cos(phi), 3), round(Rm * math.sin(phi), 3), 1.0]
        uvs += [1.0, round(k / n, 5)]
    tris = []
    for k in range(n):
        f0, f1, b0, b1 = k, k + 1, 2 * n + 1 - k, 2 * n - k
        tris += [f0, f1, b1, f0, b1, b0]
    hull = 2 * (n + 1)
    edges = []
    for i in range(hull):
        edges += [i * 2, ((i + 1) % hull) * 2]
    return MeshAttachment(name="edge", path=path, uvs=uvs, triangles=tris, vertices=verts, hull=hull, edges=edges,
                          width=round(T, 3), height=round(2 * math.pi * R, 3))


def thickness_for(depth, R: float) -> float:
    """depth: thin | medium | thick (0.065 / 0.13 / 0.26 of the diameter), a fraction of the diameter (< 1) or
    units (>= 1)."""
    if isinstance(depth, str):
        key = depth.strip().lower()
        if key in DEPTHS:
            return DEPTHS[key] * 2 * R
        try:
            depth = float(key)
        except ValueError:
            raise ValueError(f"depth {depth!r}: one of {sorted(DEPTHS)} or a number") from None
    depth = float(depth)
    if depth <= 0:
        raise ValueError("depth must be > 0")
    return depth * 2 * R if depth < 1 else depth


# ------------------------------------------------------------------ shading
def face_shade(f: float) -> float:
    """Brightness of a face given how much it faces the camera (f = +-cos)."""
    return 0.62 + 0.38 * (max(f, 0.0) ** 0.8) if f >= 0 else 0.62 - 0.17 * min(-f, 1.0)


def warm(b: float, a: float = 1.0) -> str:
    """A shade that warms as it darkens (gold in shadow), pure white when fully lit so the setup pose matches."""
    k = min(1.0, max(0.0, (1 - b) / 0.38))
    return color_hex(min(b, 1.0), min(b * (1 - 0.035 * k), 1.0), min(b * (1 - 0.09 * k), 1.0), a)


def edge_shade(sn: float) -> float:
    return 0.62 + 0.38 * abs(sn)


# ------------------------------------------------------------------ rig_coin
def _mirror(att: RegionAttachment, axis: str, name: str) -> RegionAttachment:
    """The same picture mirrored about the face bone's spin axis, so a negative bone scale shows it the right way."""
    d = att.model_dump()
    d["name"] = name
    d["rotation"] = r(-att.rotation, 3)
    if axis == "y":
        d["x"], d["scaleX"] = r(-att.x, 3), -att.scaleX
    else:
        d["y"], d["scaleY"] = r(-att.y, 3), -att.scaleY
    return RegionAttachment(**d)


def _face_att(P, W: int, H: int, disc_px, path: str) -> tuple[RegionAttachment, float]:
    """A region attachment for art whose pixel (x right, y down) -> coin-local map is P, placed so the disc centre
    is the bone origin. Returns it and the units-per-pixel scale."""
    C = P([W / 2, H / 2])
    X = P([W / 2 + 1, H / 2]) - C
    Yd = P([W / 2, H / 2 + 1]) - C
    D = P(disc_px)
    sx, sy = float(np.hypot(*X)), float(np.hypot(*Yd))
    rot = math.degrees(math.atan2(X[1], X[0]))
    mirrored = X[0] * -Yd[1] - X[1] * -Yd[0] < 0
    att = RegionAttachment(name="face", path=path, x=r(C[0] - D[0], 3), y=r(C[1] - D[1], 3),
                           rotation=r(rot, 3) if abs(rot) > 1e-6 else 0.0, scaleY=-1 if mirrored else 1,
                           width=r(W * sx, 3), height=r(H * sy, 3))
    return att, (sx + sy) / 2


def _art_source(project: Project, src: str, what: str):
    """(image, path in the project, slot or None, pixel -> world map) for a slot name or a PNG file."""
    sk = project.data
    if sk.has_slot(src):
        slot = sk.slot(src)
        if not slot.attachment:
            raise ValueError(f"{what} slot {src!r} shows nothing in the setup pose")
        att = sk.attachment(src, slot.attachment)
        if not isinstance(att, RegionAttachment) or att.sequence is not None:
            raise ValueError(f"{what} slot {src!r} must show a plain region attachment (a picture), not {att.type}")
        img = project.image(project.att_image_name(src, slot.attachment))
        W, H = img.size
        f, _ = region_pixel_to_local(att, W, H)
        wb = sk.world()[slot.bone]
        def to_w(px):
            return to_world(wb, f(np.atleast_2d(np.asarray(px, float))))[0]
        return img, att.path or slot.attachment, src, to_w
    p = Path(src).expanduser()
    if not p.exists():
        raise ValueError(f"{what}: {src!r} is neither a slot nor an image file")
    return Image.open(p).convert("RGBA"), None, None, None


def rig_coin(project: Project, face: str = "", image: str = "", name: str = "coin", depth="medium",
             radius: float = 0, ridges: int = 26, rim_color: str = "", parent: str = "root", x: float = 0,
             y: float = 0, back: str = "") -> dict:
    """Turn a flat coin face into an extruded disc: bones <name>, <name>_f, <name>_eb; slots <name>_edge,
    <name>_back, <name>_front (that draw order); a weighted reeded rim mesh; the setup pose face-on."""
    sk = project.data
    if bool(face) == bool(image):
        raise ValueError("give exactly one of face (a slot showing the coin face) or image (a PNG of it)")
    for b in (name, f"{name}_f", f"{name}_eb"):
        if sk.has_bone(b):
            raise ValueError(f"bone {b!r} already exists: pick another name")
    for s in (f"{name}_edge", f"{name}_back", f"{name}_front"):
        if sk.has_slot(s):
            raise ValueError(f"slot {s!r} already exists: pick another name")
    sk.bone(parent)
    img, path, face_slot, to_w = _art_source(project, face or image, "face")
    if face_slot is None:
        path = f"{name}_face"
        project.write_image(path, img)
    W, H = img.size
    cx, cy, r_px = fit_disc(img)
    if radius and radius > 0:
        r_px = float(radius)

    # the coin bone sits on the disc centre (world rotation 0); x, y shift it in the parent's space
    world = sk.world()
    pw = world[parent]
    if to_w is not None:
        wx, wy = to_w([cx, cy])
        lx, ly = pw.to_local(float(wx), float(wy))
    else:
        lx, ly = 0.0, 0.0
    sk.add_bone(Bone(name=name, parent=parent, x=r(lx + x, 3), y=r(ly + y, 3),
                     rotation=r(-pw.rotation, 3) if abs(pw.rotation) > 1e-9 else 0.0))
    sk.add_bone(Bone(name=f"{name}_f", parent=name))
    sk.add_bone(Bone(name=f"{name}_eb", parent=name))
    world = sk.world()
    cw = world[name]
    if to_w is not None:
        P = lambda px: to_local(cw, np.atleast_2d(to_w(px)))[0]                  # noqa: E731
    else:
        P = lambda px: np.array([float(px[0]) - cx, cy - float(px[1])])          # noqa: E731  1 px = 1 unit
    front, upp = _face_att(P, W, H, (cx, cy), path)
    R = r_px * upp
    T = thickness_for(depth, R)

    # the back face: the same picture un-mirrored, or its own art scaled so its disc matches
    back_slot = None
    if back:
        bimg, bpath, back_slot, _ = _art_source(project, back, "back")
        if back_slot is None:
            bpath = f"{name}_back"
            project.write_image(bpath, bimg)
        bcx, bcy, br = fit_disc(bimg)
        k = R / br
        bW, bH = bimg.size
        back_att, _ = _face_att(lambda px: np.array([(float(px[0]) - bcx) * k, (bcy - float(px[1])) * k]),
                                bW, bH, (bcx, bcy), bpath)
    else:
        back_att = front
        bimg, bcx, bcy, br = img, cx, cy, r_px

    if rim_color:
        base = tuple(int(round(v * 255)) for v in parse_color(rim_color)[:3])
    else:
        base = rim_colour_from(img, cx, cy, r_px)
    rim_path = f"{name}_rim"
    project.write_image(rim_path, make_rim(base, ridges))

    # slots: edge, back, front; where the face art was in the draw order (it is hidden), else on top
    anchor = face_slot
    edge_s = Slot(name=f"{name}_edge", bone=name, attachment="edge", color=warm(edge_shade(0.0)))
    back_s = Slot(name=f"{name}_back", bone=f"{name}_eb", attachment=None, color=warm(face_shade(-1.0)))
    front_s = Slot(name=f"{name}_front", bone=f"{name}_f", attachment="face")
    if anchor:
        sk.add_slot(edge_s, after=anchor)
    else:
        sk.add_slot(edge_s)
    sk.add_slot(back_s, after=edge_s.name)
    sk.add_slot(front_s, after=back_s.name)
    hidden = []
    for s in (face_slot, back_slot):
        if s and sk.slot(s).attachment:
            sk.slot(s).attachment = None
            hidden.append(s)
    sk.set_attachment(front_s.name, "face", front)
    sk.set_attachment(back_s.name, "face", _mirror(back_att, "y", "face"))
    sk.set_attachment(back_s.name, "face_x", _mirror(back_att, "x", "face_x"))
    # every bone exists now: the weighted mesh's bone indices are final
    mesh = rim_mesh(sk, f"{name}_f", f"{name}_eb", R, T, rim_path, INSET_PX * upp)
    sk.set_attachment(edge_s.name, "edge", mesh)
    return {"coin": name, "bones": [name, f"{name}_f", f"{name}_eb"],
            "slots": [edge_s.name, back_s.name, front_s.name], "hidden": hidden,
            "radius": round(R, 3), "thickness": round(T, 3), "depth": depth,
            "thickness_ratio": round(T / (2 * R), 4),
            "centre_px": [round(cx, 2), round(cy, 2)], "art_size": [W, H],
            "centre_offset": [round(cx - W / 2, 2), round(H / 2 - cy, 2)],
            "units_per_px": round(upp, 5), "rim_color": "%02X%02X%02X" % base,
            "vertices": len(mesh.uvs) // 2, "images": [f"images/{path}.png", f"images/{rim_path}.png"]}


# ------------------------------------------------------------------ angles
def spin_profile(t0: float, t1: float, delta: float, speed, theta0: float = 0.0, n: int = 4000):
    """theta(t) over [t0, t1] from a relative speed profile speed(u), normalised so it turns EXACTLY `delta`
    degrees (whole turns -> the coin stops face-on); theta0 before, theta0 + delta after."""
    u = np.linspace(0, 1, n)
    s = np.array([max(0.0, float(speed(v))) for v in u])
    cum = np.concatenate([[0.0], np.cumsum((s[1:] + s[:-1]) / 2)])
    if cum[-1] <= 0:
        raise ValueError("the speed profile never moves")
    cum = cum / cum[-1] * delta

    def theta(t):
        if t <= t0:
            return theta0
        if t >= t1:
            return theta0 + delta
        return theta0 + float(np.interp((t - t0) / (t1 - t0), u, cum))
    return theta


def _bezier(x1, y1, x2, y2):
    """CSS cubic-bezier(x1, y1, x2, y2) as a function of u in 0..1 (exact at both ends)."""
    def bx(s):
        return 3 * x1 * s * (1 - s) ** 2 + 3 * x2 * s * s * (1 - s) + s ** 3

    def by(s):
        return 3 * y1 * s * (1 - s) ** 2 + 3 * y2 * s * s * (1 - s) + s ** 3

    def f(u):
        if u <= 0:
            return 0.0
        if u >= 1:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(40):
            mid = (lo + hi) / 2
            if bx(mid) < u:
                lo = mid
            else:
                hi = mid
        return by((lo + hi) / 2)
    return f


def _in_out_cubic(u):
    return 4 * u ** 3 if u < 0.5 else 1 - (-2 * u + 2) ** 3 / 2


PROFILES = {
    # relative SPEED over u in 0..1 (normalised to the exact angle afterwards)
    "loop": lambda u: 1.0,
    "spin_up": lambda u: u ** 1.6 if u < 0.82 else 0.82 ** 1.6 * max(0.0, 1 - (u - 0.82) / 0.18) ** 1.4,
    "slow_down": lambda u: (1 - u) ** 1.7 + 0.02,
}


def spin_theta(mode: str, t0: float, t1: float, delta: float, theta0: float = 0.0, ease: str = "auto"):
    """theta(t) in degrees for a coin_spin window: exactly theta0 at t0 and theta0 + delta at t1."""
    if mode not in MODES:
        raise ValueError(f"mode {mode!r}: one of {list(MODES)}")
    D = t1 - t0
    if ease not in ("", "auto"):
        if ease not in EASE or EASE[ease] == "stepped":
            raise ValueError(f"ease {ease!r}: 'auto' or one of {sorted(k for k in EASE if k != 'stepped')}")
        e = EASE[ease]
        g = (lambda u: u) if e is None else _bezier(*e)
    elif mode == "loop":
        g = lambda u: u                                               # noqa: E731
    elif mode == "flip":
        g = _in_out_cubic
    elif mode == "land":
        g = lambda u: 1 - (1 - u) ** 2                                 # noqa: E731  tumbling in, slowing to the floor
    else:
        return spin_profile(t0, t1, delta, PROFILES[mode], theta0)

    def theta(t):
        if t <= t0:
            return theta0
        if t >= t1:
            return theta0 + delta
        return theta0 + delta * g((t - t0) / D)
    return theta


def crossings(theta, t0: float, t1: float) -> tuple[list[float], list[float]]:
    """Exact times in (t0, t1) where cos(theta) = 0 (edge-on: the face swap) and sin(theta) = 0 (face-on)."""
    fine = np.linspace(t0, t1, max(64, int((t1 - t0) * 2000)) + 1)
    th = np.radians([theta(t) for t in fine])
    out_cos, out_sin = [], []
    for fn, out in ((math.cos, out_cos), (math.sin, out_sin)):
        v = np.array([fn(a) for a in th])
        idx = np.nonzero(np.sign(v[:-1]) * np.sign(v[1:]) < 0)[0]
        for i in idx:
            lo, hi = fine[i], fine[i + 1]
            for _ in range(48):
                mid = (lo + hi) / 2
                if fn(math.radians(theta(lo))) * fn(math.radians(theta(mid))) <= 0:
                    hi = mid
                else:
                    lo = mid
            out.append((lo + hi) / 2)
    return out_cos, out_sin


def _sample_times(t0: float, t1: float, exact: list[float]) -> list[float]:
    """A 60 Hz grid over [t0, t1] plus the exact crossing times (a grid sample that would round onto a crossing's
    key time is dropped, never the crossing)."""
    n = max(1, int(math.ceil((t1 - t0) * HZ - 1e-9)))
    keyed = {r(t0 + (t1 - t0) * i / n): t0 + (t1 - t0) * i / n for i in range(n + 1)}
    for e in exact:
        re_ = r(e)
        for k in [k for k in keyed if abs(k - re_) < 2.5e-4]:
            del keyed[k]
        keyed[re_] = e
    return [keyed[k] for k in sorted(keyed)]


# ------------------------------------------------------------------ coin_spin
def coin_parts(sk, coin: str) -> dict:
    need_b = [coin, f"{coin}_f", f"{coin}_eb"]
    need_s = [f"{coin}_edge", f"{coin}_back", f"{coin}_front"]
    for b in need_b:
        if not sk.has_bone(b):
            raise ValueError(f"no bone {b!r}: run rig_coin first (name={coin!r})")
    for s in need_s:
        if not sk.has_slot(s):
            raise ValueError(f"no slot {s!r}: run rig_coin first (name={coin!r})")
    mesh = sk.attachment(f"{coin}_edge", "edge")
    if not isinstance(mesh, MeshAttachment):
        raise ValueError(f"{coin}_edge has no rim mesh 'edge'")
    return {"T": float(mesh.width), "R": float(mesh.height) / (2 * math.pi)}


def _side_at(anim: Animation | None, coin: str, t: float) -> bool:
    """True when the BACK face shows at time t of the existing animation (its last face-bone scale key < 0)."""
    if anim is None:
        return False
    node = anim.bones.get(f"{coin}_f", {})
    best = None
    for tl in ("scalex", "scaley"):
        for k in node.get(tl, []):
            if k.time <= t + 1e-6 and (best is None or k.time >= best[0]):
                best = (k.time, float(getattr(k, "value", 1)))
    return best is not None and best[1] < 0


def coin_spin(project: Project, coin: str = "coin", animation: str = "spin", mode: str = "loop", turns: float = 1,
              duration: float = 2.0, start: float = 0.0, axis: str = "y", bob: float = 0.0, tilt: float = 0.0,
              ease: str = "auto", stop: str = "face", replace: bool = False) -> dict:
    """Key the coin's spin into `animation` over [start, start + duration] (land adds a 0.7 s settle after)."""
    sk = project.data
    dims = coin_parts(sk, coin)
    R, T = dims["R"], dims["T"]
    if mode not in MODES:
        raise ValueError(f"mode {mode!r}: one of {list(MODES)}")
    if axis not in ("y", "x"):
        raise ValueError("axis: 'y' (turn round the vertical axis) or 'x' (flip over the horizontal axis)")
    if stop not in ("face", "back", "any"):
        raise ValueError("stop: face | back | any")
    if duration <= 0:
        raise ValueError("duration must be > 0")
    turns = float(turns)
    if turns < 0:
        raise ValueError("turns must be >= 0")
    whole = abs(turns - round(turns)) < 1e-9
    if mode == "loop":
        if not whole or round(turns) < 1:
            raise ValueError("a loop needs whole turns >= 1 so its last frame is its first")
        if stop == "back":
            raise ValueError("a loop ends where it started: stop='back' cannot loop")
    elif stop in ("face", "back") and not whole:
        raise ValueError(f"turns={turns} with stop={stop!r}: use whole turns (stop picks the side), or stop='any'")

    if replace or animation not in sk.animations:
        sk.animations[animation] = Animation()
    anim = sk.animations[animation]
    t0, t1 = float(start), float(start) + float(duration)
    back0 = _side_at(anim, coin, t0)
    theta0 = 180.0 if back0 else 0.0
    delta = 360.0 * turns
    if stop != "any":
        delta += 180.0 * ((stop == "back") != back0)
    if delta <= 0:
        raise ValueError("nothing to turn: turns=0 and the coin already shows that side")
    theta = spin_theta(mode, t0, t1, delta, theta0, ease)
    cos_t, sin_t = crossings(theta, t0, t1)
    tend = t1 + (SETTLE if mode == "land" else 0.0)
    ts = _sample_times(t0, tend, cos_t + sin_t)

    bone_c = sk.bone(coin)
    sy0 = abs(bone_c.scaleY) or 1.0
    Rp = R * sy0                                                     # the radius in the parent's units
    D = t1 - t0
    fall = bob if (mode == "land" and bob > 0) else 4.0 * Rp

    def lift(t):
        u = min(1.0, max(0.0, (t - t0) / D))
        if mode == "loop":
            return bob * math.sin(2 * math.pi * u)
        if mode == "flip":
            return bob * 4 * u * (1 - u)
        if mode in ("spin_up", "slow_down"):
            return bob * math.sin(math.pi * u)
        if t <= t1:                                                  # land: free fall onto the floor
            return fall * (1 - u * u)
        v = t - t1
        return 0.11 * Rp * math.sin(math.pi * (v - 0.10) / 0.30) if 0.10 < v < 0.40 else 0.0

    def lean(t):
        u = min(1.0, max(0.0, (t - t0) / D))
        if mode == "loop":
            return tilt * math.sin(2 * math.pi * u)
        if mode == "land":
            return -tilt * (1 - u)
        return tilt * math.sin(2 * math.pi * u) * (1 - u)

    def squash(t):
        if mode != "land" or t <= t1:
            return 1.0, 1.0
        v = t - t1
        env = math.exp(-7.0 * v) * min(1.0, max(0.0, (SETTLE - v) / 0.15))
        c = math.cos(16.0 * v)
        return 1 + 0.10 * env * c, 1 - 0.18 * env * c

    tx = "translatex" if axis == "y" else "translatey"
    sc = "scalex" if axis == "y" else "scaley"
    other_tx = "translatey" if axis == "y" else "translatex"
    other_sc = "scaley" if axis == "y" else "scalex"
    back_att = "face" if axis == "y" else "face_x"
    ftx, btx, csx, fc, bc, ec = [], [], [], [], [], []
    tr, ro, scl = [], [], []
    moves = mode == "land" or bob != 0
    for t in ts:
        th = math.radians(theta(min(t, t1)))
        cs, sn = math.cos(th), math.sin(th)
        cs = 0.0 if abs(cs) < 1e-6 else cs
        sn = 0.0 if abs(sn) < 1e-6 else sn
        ftx.append((t, T / 2 * sn))
        btx.append((t, -T / 2 * sn))
        csx.append((t, cs))
        fc.append((t, warm(face_shade(cs))))
        bc.append((t, warm(face_shade(-cs))))
        ec.append((t, warm(edge_shade(sn))))
        sx, sy = squash(t)
        tr.append((t, 0.0, lift(t) - (1 - sy) * Rp))
        ro.append((t, lean(t)))
        scl.append((t, sx, sy))

    def put_bone(bone, tl, pts, kind):
        _put(anim.bones.setdefault(bone, {}), tl, make_keys(pts, kind, "linear"), t0, tend)

    def put_slot(slot, tl, ks):
        _put(anim.slots.setdefault(slot, {}), tl, ks, t0, tend)

    for b, pts in ((f"{coin}_f", ftx), (f"{coin}_eb", btx)):
        put_bone(b, tx, pts, tx)
        put_bone(b, sc, csx, sc)
        node = anim.bones.get(b, {})
        for tl, rest in ((other_tx, 0.0), (other_sc, 1.0)):          # an earlier spin on the other axis rests here
            if tl in node:
                put_bone(b, tl, [(t0, rest), (tend, rest)], tl)
    if moves:
        put_bone(coin, "translate", tr, "translate")
    if tilt:
        put_bone(coin, "rotate", ro, "rotate")
    if mode == "land":
        put_bone(coin, "scale", scl, "scale")
    put_slot(f"{coin}_front", "rgba", color_keys(fc, "linear"))
    put_slot(f"{coin}_back", "rgba", color_keys(bc, "linear"))
    put_slot(f"{coin}_edge", "rgba", color_keys(ec, "linear"))

    # only the face pointing at the camera is drawn; both are zero wide at each swap
    facing = math.cos(math.radians(theta0)) >= 0
    fk = [Key(time=r(t0), name="face" if facing else None)]
    bk = [Key(time=r(t0), name=None if facing else back_att)]
    for t in sorted(cos_t):
        facing = not facing
        fk.append(Key(time=r(t), name="face" if facing else None))
        bk.append(Key(time=r(t), name=None if facing else back_att))
    put_slot(f"{coin}_front", "attachment", fk)
    put_slot(f"{coin}_back", "attachment", bk)
    put_slot(f"{coin}_edge", "attachment", [Key(time=r(t0), name="edge")])

    events = {"loop": [], "flip": [(t0, "sfx_flip")] + ([(t1, "sfx_land")] if bob else []),
              "spin_up": [(t0, "sfx_spin"), (t1, "sfx_stop")], "slow_down": [(t0, "sfx_spin"), (t1, "sfx_stop")],
              "land": [(t1, "sfx_land")]}[mode]
    for t, ev in events:
        if ev not in sk.events:
            sk.events[ev] = EventData()
        anim.events = [e for e in anim.events if not (e.name == ev and abs(e.time - r(t)) < 1e-6)]
        anim.events.append(EventKey(time=r(t), name=ev))
    anim.events.sort(key=lambda e: e.time)
    end_angle = theta0 + delta
    return {"animation": animation, "coin": coin, "mode": mode, "axis": axis, "start": round(t0, 4),
            "end": round(t1, 4), "settle_end": round(tend, 4), "turns": turns, "start_angle": theta0,
            "end_angle": round(end_angle, 6),
            "ends_on": "front" if abs(math.cos(math.radians(end_angle)) - 1) < 1e-9 else (
                "back" if abs(math.cos(math.radians(end_angle)) + 1) < 1e-9 else "edge/angle"),
            "face_swaps": [round(float(t), 4) for t in sorted(cos_t)],
            "face_on": [round(float(t), 4) for t in sorted(sin_t)],
            "events": [[round(float(t), 4), ev] for t, ev in events], "keys_per_timeline": len(ts),
            "radius": round(R, 3), "thickness": round(T, 3), "duration": round(anim.duration(), 4)}
