"""Bend an After Effects strip along any path in Spine: the ``ae_fx_along_path`` tool's engine.

AE renders the effect on a straight strip (``fire_strip``: tongues rise from a baseline; ``energy_payline``: a
payline beam along the middle row). Here that strip becomes a mesh that follows a Spine **path**, so the game can
reshape the line at runtime:

* ``<name>_c0..cK``  control bones, one per knot of the path. Move one to drag the line (a slot game moves them to
  the reel positions of the winning line), rotate one to turn the curve there (the bezier handles are offsets in that
  bone's own space, so they turn with it).
* ``<name>_path``    a path attachment whose bezier vertices are weighted to the control bones. ``corners="smooth"``
  runs a Catmull-Rom curve through the knots; ``corners="sharp"`` makes every segment a straight line, so the path
  turns sharply at each knot (paylines).
* ``<name>_b0..bN``  a bone chain driven by a **path constraint** (proportional spacing, chain scale), so it always
  spans the whole path, stretching or shrinking with its length.
* ``<name>_fx``      a mesh on that chain playing the AE frames as a sequence. Strip x runs along the path, strip y
  across it; the strip's ``baseline`` row sits on the path.

``parts`` splits one render into several animations on the same mesh (each its own sequence attachment): e.g. a
payline's ``in`` (draw-on, once), ``loop`` and ``out`` (once), played in a row by the game.

The setup pose already lies along the path you gave, so the editor shows it correctly; the runtime constraint keeps
it there when the control bones move.
"""
from __future__ import annotations

import math
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

import numpy as np
from PIL import Image

from . import ae_bridge
from .ir import MeshAttachment, PathAttachment, Sequence, Slot
from .project import Project
from .rig import _next_order
from .timeline import AnimBuilder, r

SEQ_MODES = ("once", "loop", "pingpong", "hold")


# ------------------------------------------------------------------ geometry
def catmull_rom_bezier(pts: np.ndarray):
    """Knots -> per-knot tangent vectors (already /3, ready to be bezier handle offsets)."""
    n = len(pts)
    tang = np.zeros_like(pts)
    for i in range(n):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, n - 1)]
        tang[i] = (b - a) / (2.0 if 0 < i < n - 1 else 1.0)
    return tang / 3.0


def knot_handles(pts: np.ndarray, corners: str):
    """(in-handle, out-handle) offsets per knot. smooth: one Catmull-Rom tangent, in = -out. sharp: each handle points
    a third of the way to the neighbouring knot, so every segment is a straight line and the path turns at the knot."""
    if corners == "smooth":
        h = catmull_rom_bezier(pts)
        return -h, h
    if corners != "sharp":
        raise ValueError('corners must be "smooth" or "sharp"')
    hin, hout = np.zeros_like(pts), np.zeros_like(pts)
    hout[:-1] = (pts[1:] - pts[:-1]) / 3.0
    hin[1:] = (pts[:-1] - pts[1:]) / 3.0
    hin[0], hout[-1] = -hout[0], -hin[-1]
    return hin, hout


def bezier_polyline(pts: np.ndarray, hin: np.ndarray, hout: np.ndarray | None = None, per: int = 80):
    """Sample the open path (per-1 steps per curve): returns (points, cumulative arc length). With one handle array
    it is the smooth form (in = -out)."""
    if hout is None:
        hin, hout = -hin, hin
    out = []
    for i in range(len(pts) - 1):
        p0, p3 = pts[i], pts[i + 1]
        p1, p2 = p0 + hout[i], p3 + hin[i + 1]
        t = np.linspace(0, 1, per + 1, endpoint=True)[:, None]
        t = t if i == len(pts) - 2 else t[:-1]
        out.append((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3)
    poly = np.vstack(out)
    seg = np.hypot(*np.diff(poly, axis=0).T)
    return poly, np.concatenate([[0.0], np.cumsum(seg)])


def at_length(poly: np.ndarray, cum: np.ndarray, s: np.ndarray):
    """Position and unit tangent at arc lengths ``s``."""
    s = np.clip(s, 0, cum[-1])
    x = np.interp(s, cum, poly[:, 0])
    y = np.interp(s, cum, poly[:, 1])
    ds = max(cum[-1] * 1e-3, 1e-6)
    x2 = np.interp(np.clip(s + ds, 0, cum[-1]), cum, poly[:, 0])
    y2 = np.interp(np.clip(s + ds, 0, cum[-1]), cum, poly[:, 1])
    x1 = np.interp(np.clip(s - ds, 0, cum[-1]), cum, poly[:, 0])
    y1 = np.interp(np.clip(s - ds, 0, cum[-1]), cum, poly[:, 1])
    t = np.stack([x2 - x1, y2 - y1], -1)
    t /= np.maximum(np.hypot(t[:, 0], t[:, 1]), 1e-9)[:, None]
    return np.stack([x, y], -1), t


def _weights(u: float, n: int) -> list[tuple[int, float]]:
    """Linear blend between neighbouring bone midpoints: 1 at a bone's middle, 0.5/0.5 at a joint."""
    u = min(max(u, 0.5), n - 0.5)
    i = int(math.floor(u - 0.5))
    t = u - 0.5 - i
    if i >= n - 1:
        return [(n - 1, 1.0)]
    if t < 1e-6:
        return [(i, 1.0)]
    return [(i, 1 - t), (i + 1, t)]


def window_weights(s: float, length: float, bones: int, window: float, cap: int = 8) -> list[tuple[int, float]]:
    """Tent weights over every chain bone whose middle is within ``window`` (arc length) of ``s``. Spreading a
    vertex over several bones makes linear-blend skinning round a corner instead of folding the strip's inner side:
    the smoothing lives in the weights, so it also holds when the game moves the knots to a new line."""
    seg = length / bones
    if window <= seg:
        return _weights(min(max(s, 0.0), length) / seg, bones)
    mids = (np.arange(bones) + 0.5) * seg
    w = np.clip(1 - np.abs(min(max(s, 0.0), length) - mids) / window, 0, None)
    idx = np.argsort(-w)[:cap]
    idx = idx[w[idx] > 0.01]
    tot = float(w[idx].sum())
    return [(int(i), float(w[i]) / tot) for i in sorted(idx)]


def smooth_tangent(poly: np.ndarray, cum: np.ndarray, s: np.ndarray, window: float) -> np.ndarray:
    """Unit tangent averaged over [s - window, s + window]: offsets taken along its normal round a sharp corner."""
    if window <= 0:
        return at_length(poly, cum, s)[1]
    acc = np.zeros((len(s), 2))
    for k in np.linspace(-1, 1, 9):
        acc += at_length(poly, cum, s + k * window)[1]
    return acc / np.maximum(np.hypot(acc[:, 0], acc[:, 1]), 1e-9)[:, None]


def miter_limits(wp: np.ndarray, cum: np.ndarray, per: int, s: np.ndarray, top: float, bot: float):
    """Per-column (top, bottom) offsets clamped on the INNER side of every corner to the corner's bisector
    (|s - s_corner| x tan(interior / 2)): a thick strip's inner edge would otherwise fold back over itself (flipped
    triangles, mirrored texture). The two arms' inner edges then meet on the bisector, like a mitred line."""
    t_off, b_off = np.full(len(s), float(top)), np.full(len(s), float(bot))
    for i in range(1, len(wp) - 1):
        d1, d2 = wp[i] - wp[i - 1], wp[i + 1] - wp[i]
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        turn = math.atan2(cross, float(np.dot(d1, d2)))
        if abs(turn) < 1e-3:
            continue
        k = math.tan((math.pi - abs(turn)) / 2)
        lim = np.abs(s - cum[min(i * per, len(cum) - 1)]) * k
        if cross > 0:                 # turning left: the inner side is the left (top) row
            t_off = np.minimum(t_off, lim)
        else:
            b_off = np.minimum(b_off, lim)
    return t_off, b_off


def unfold(row: np.ndarray, tan: np.ndarray) -> np.ndarray:
    """A row of offset points must never step backwards along the path: a point that would is pulled onto the one
    before it (a degenerate triangle instead of a flipped one). Safety net after miter_limits for smoothed normals."""
    out = row.copy()
    for j in range(1, len(out)):
        if float(np.dot(out[j] - out[j - 1], tan[j])) < 0:
            out[j] = out[j - 1]
    return out


# ------------------------------------------------------------------ frames
@contextmanager
def _frame_source(*, aep: str, comp: str, frames_dir: str, fps: float, start_frame, end_frame, keep_frames: str):
    """Yield (frame paths, fps, info) from a comp rendered with aerender, or from a folder of frames."""
    tmp = None
    try:
        if aep:
            if not comp:
                raise ValueError("aep needs comp=<composition name>")
            dest = Path(keep_frames).expanduser() if keep_frames else Path(tempfile.mkdtemp(prefix="ae_path_"))
            if not keep_frames:
                tmp = dest
            info = ae_bridge.render_comp(aep, comp, dest, start_frame, end_frame, ae_bridge.DEFAULT_TEMPLATE)
            yield info.frames, info.fps, {"aep": str(Path(aep).expanduser().resolve()), "comp": comp,
                                          "comp_fps": info.fps, "comp_size": [info.width, info.height],
                                          "comp_frames": [info.start, info.end]}
        elif frames_dir:
            exts = ("*.tif", "*.tiff", "*.png")
            frames = sorted(p for e in exts for p in Path(frames_dir).expanduser().glob(e))
            if not frames:
                raise FileNotFoundError(f"no .tif/.png frames in {frames_dir}")
            if fps <= 0:
                raise ValueError("frames_dir needs fps=<the comp's frame rate>")
            yield frames, fps, {"frames_dir": str(Path(frames_dir).expanduser().resolve())}
        else:
            raise ValueError("give aep + comp, or frames_dir + fps")
    finally:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)


def _write_part(project: Project, prefix: str, pms: list[np.ndarray], fps: float, mode: str, seq_mode: str,
                max_size: int, max_frames: int, min_fps: float, trim: bool, fit_duration: float = 0.0,
                feather: float = 0.0) -> dict:
    """Premultiplied frames -> ``images/ae/<prefix>NN.png`` (full size each: a mesh's UVs map the whole picture)."""
    lo, hi = ae_bridge.active_range(pms, mode) if trim else (0, len(pms) - 1)
    keep = list(range(lo, hi + 1))
    h, w = pms[0].shape[:2]
    budget = ae_bridge.frame_budget(len(keep), fps, w, h, max_size=max_size, max_frames=max_frames,
                                    seq_mode=seq_mode, min_fps=min_fps)
    step, (tw, th) = budget["step"], budget["size"]
    keep = keep[::step]
    resize = (tw, th) if (tw, th) != (w, h) else None
    digits = max(2, len(str(len(keep) - 1)))
    img_dir = project.images_dir / "ae"
    img_dir.mkdir(parents=True, exist_ok=True)
    for old in img_dir.glob(f"{Path(prefix).name}[0-9]*.png"):
        old.unlink()
    for n, i in enumerate(keep):
        out = ae_bridge.to_straight(pms[i], mode, resize)
        if feather > 0:                              # soft light reaching the strip's border must not end in a hard edge
            out[..., 3] *= ae_bridge.edge_window(out.shape[1], out.shape[0], feather)
        project.write_image(f"ae/{prefix}{str(n).zfill(digits)}", Image.fromarray(np.round(out * 255).astype(np.uint8), "RGBA"))
    delay = fit_duration / len(keep) if fit_duration else step / fps
    return {"n": len(keep), "digits": digits, "w": w, "h": h, "tw": tw, "th": th, "delay": delay,
            "dur": len(keep) * delay, "step": step, "frames": [lo, hi], "note": budget["note"]}


def _build_rig(sk, name, parent, wp, hin, hout, poly, cum, per, bones, sharp=False):
    """Control bones (one per knot), the path attachment weighted to them, and the chain the constraint drives."""
    ctrl = []
    for i, (x, y) in enumerate(wp):
        d = hout[i] if np.hypot(*hout[i]) > 1e-9 else -hin[i]
        b = sk.add_bone_world(sk.unique_name(f"{name}_c{i}"), parent, float(x), float(y),
                              math.degrees(math.atan2(d[1], d[0])), length=float(np.hypot(*d)), color="FF3F00FF")
        ctrl.append(b.name)
    world = sk.world()
    path_slot = sk.unique_name(f"{name}_path", "slot")
    sk.add_slot(Slot(name=path_slot, bone=parent, attachment="path"), before=sk.slots[0].name if sk.slots else None)
    verts: list[float] = []
    idx = [sk.bone_index(cb) for cb in ctrl]
    for i, cb in enumerate(ctrl):
        bi = idx[i]
        for side, q in ((-1, wp[i] + hin[i]), (0, wp[i]), (1, wp[i] + hout[i])):   # in-handle, knot, out-handle
            nb = i + side
            if sharp and side and 0 <= nb < len(ctrl):
                # sharp: the handle sits a third of the way to the neighbouring knot, weighted 2/3 to this knot's bone
                # and 1/3 to the neighbour's, so every segment stays straight wherever the game moves the knots
                verts += [2, bi, 0.0, 0.0, round(2 / 3, 6), idx[nb], 0.0, 0.0, round(1 / 3, 6)]
                continue
            lx, ly = world[cb].to_local(float(q[0]), float(q[1]))
            verts += [1, bi, round(lx, 3), round(ly, 3), 1.0]
    curve_len = [float(cum[min((i + 1) * per, len(cum) - 1)]) for i in range(len(wp) - 1)]   # cumulative, like Spine
    sk.set_attachment(path_slot, "path", PathAttachment(closed=False, constantSpeed=True, vertexCount=3 * len(wp),
                                                       vertices=verts, lengths=[round(v, 3) for v in curve_len]))

    # ---- the bone chain: head at station i, pointing at station i+1
    pos, _ = at_length(poly, cum, np.linspace(0, float(cum[-1]), bones + 1))
    chain = []
    prev = parent
    for i in range(bones):
        d = pos[i + 1] - pos[i]
        b = sk.add_bone_world(sk.unique_name(f"{name}_b{i}"), prev, float(pos[i][0]), float(pos[i][1]),
                              math.degrees(math.atan2(d[1], d[0])), length=float(np.hypot(*d)), color="FFB000FF")
        chain.append(b.name)
        prev = b.name
    cname = sk.unique_name(f"{name}_follow", "constraint")
    sk.path.append({"name": cname, "order": _next_order(sk),
                    "bones": chain, "target": path_slot, "positionMode": "percent", "spacingMode": "proportional",
                    "rotateMode": "chainScale", "position": 0, "spacing": 1})

    return ctrl, chain, path_slot, cname


# ----------------------------------------------------------------------- tool
def fx_along_path(project: Project, name: str, points: list[list[float]], *, corners: str = "smooth",
                  bones: int = 0, columns: int = 0, across_scale: float = 0.0, baseline: float = 0.8,
                  ends: float = 0.0, feather: float = 0.0, weight_window: float = -1.0, rig: str = "",
                  mode: str = "alpha", seq_mode: str = "loop", parts: list[dict] | None = None, animation: str = "",
                  start: float = 0.0, until: float = 0.0, fit_duration: float = 0.0, max_size: int = 0,
                  max_frames: int = 0, min_fps: float = 0.0, blend: str = "", color: str = "FFFFFFFF",
                  parent: str = "root", front_of: str = "", behind: str = "", demo_bend: float = 0.0,
                  aep: str = "", comp: str = "", frames_dir: str = "", fps: float = 0,
                  start_frame: int | None = None, end_frame: int | None = None, keep_frames: str = "") -> dict:
    """Wrap an AE strip on a bendable path in the skeleton. ``points`` are the path's knots in the parent bone's
    space (at least 2). See the module docstring for what is created.

    ``parts``: ``[{"name": "in", "frames": [0, 17], "mode": "once"}, ...]`` (comp frame numbers, inclusive, counted
    from the first rendered frame). Each part becomes animation ``<animation or name>_<part>`` playing its own
    sequence on the same mesh; ``max_frames`` applies per part. Without parts the whole render is one sequence in
    ``animation`` (default ``ae_<name>``) played with ``seq_mode``. bones / columns = 0 pick defaults: smooth 8 x 3;
    sharp one bone per ~55 units of path x 2 columns (enough to turn a payline corner cleanly).

    ``ends``: strip pixels at each end that lie BEYOND the path's ends (a strip padded so a head glow is not clipped:
    energy_payline reports its pad); they hang off the end knots along the end tangents. ``feather`` (fraction of the
    frame) fades every frame's border so soft light that reaches the strip's edge does not end in a hard line.

    ``weight_window`` (arc length, world units): each mesh vertex is weighted over the chain bones within this window
    (tent weights) and offset along the tangent averaged over it, so a THICK strip rounds a sharp corner instead of
    folding its inner side, also after the game moves the knots. -1 = auto (smooth: 2-bone blend; sharp: 0.9 x the
    strip's half thickness). Keep a thin core sharp with a small window and give a wide aura its own mesh with a big
    one. ``rig``: the name of an earlier ``fx_along_path`` call on the SAME points: its control bones, path and chain
    are reused and only a new mesh slot is added (one set of knots drives both meshes)."""
    if len(points) < 2:
        raise ValueError("points needs at least two [x, y] knots")
    if ends < 0:
        raise ValueError("ends must be >= 0")
    if not 0 <= baseline <= 1:
        raise ValueError("baseline is a fraction of the strip height, 0..1")
    if seq_mode not in SEQ_MODES:
        raise ValueError(f"seq_mode must be one of {SEQ_MODES}")
    for p in parts or []:
        if not p.get("name") or len(p.get("frames", [])) != 2 or p.get("mode", "once") not in SEQ_MODES:
            raise ValueError('each part is {"name": str, "frames": [first, last], "mode": "once|loop|pingpong|hold"}')
    sk = project.data

    # ---- the path, in world space
    pw = sk.world()[parent]
    wp = np.array([pw.to_world(float(x), float(y)) for x, y in points])
    hin, hout = knot_handles(wp, corners)
    per = 80
    poly, cum = bezier_polyline(wp, hin, hout, per)
    length = float(cum[-1])
    if length < 1e-3:
        raise ValueError("the path has no length")
    if not bones:
        bones = 8 if corners == "smooth" else max(8, math.ceil(length / 55))
    if bones < 2:
        raise ValueError("bones must be at least 2")

    # ---- frames -> sprites (one set per part)
    with _frame_source(aep=aep, comp=comp, frames_dir=frames_dir, fps=fps, start_frame=start_frame,
                       end_frame=end_frame, keep_frames=keep_frames) as (frames, fps_v, src):
        pms = [ae_bridge.read_premultiplied(f, mode) for f in frames]
    if any(p.shape[:2] != pms[0].shape[:2] for p in pms):
        raise ValueError("frames differ in size")
    written = []
    if parts:
        for p in parts:
            a, b = int(p["frames"][0]), int(p["frames"][1])
            if not 0 <= a <= b < len(pms):
                raise ValueError(f"part {p['name']!r}: frames {a}..{b} outside the {len(pms)} rendered frames")
            pr = _write_part(project, f"{name}_{p['name']}_", pms[a:b + 1], fps_v, mode, p.get("mode", "once"),
                             max_size, int(p.get("max_frames", max_frames)), min_fps, trim=False, feather=feather)
            written.append((p["name"], p.get("mode", "once"), pr))
    else:
        pr = _write_part(project, f"{name}_", pms, fps_v, mode, seq_mode, max_size, max_frames, min_fps, trim=True,
                         fit_duration=fit_duration, feather=feather)
        written.append(("", seq_mode, pr))
    w, h = written[0][2]["w"], written[0][2]["h"]
    if 2 * ends >= w:
        raise ValueError(f"ends={ends} leaves no strip for the path (strip is {w} px wide)")

    if rig:
        con = next((c for c in sk.path if c["name"] == f"{rig}_follow"), None)
        if con is None:
            raise ValueError(f"no along-path rig {rig!r} (its constraint {rig}_follow is missing)")
        ctrl = [f"{rig}_c{i}" for i in range(len(wp))]
        have = {b.name for b in sk.bones}
        if any(c not in have for c in ctrl) or f"{rig}_c{len(wp)}" in have:
            raise ValueError(f"rig {rig!r} has a different number of knots than points ({len(wp)})")
        chain, path_slot, bones, cname = list(con["bones"]), con["target"], len(con["bones"]), con["name"]
    else:
        ctrl, chain, path_slot, cname = _build_rig(sk, name, parent, wp, hin, hout, poly, cum, per, bones,
                                                   sharp=corners == "sharp")
    columns = columns or (3 if corners == "smooth" else 2)
    # ---- the mesh: three rows (strip top, the baseline ON the path, strip bottom), `columns` per bone, weighted to
    #      the chain. The baseline row pins the strip's centre line to the path, whatever the two halves do.
    cols = bones * columns + (2 if ends else 0)            # + one overhang column at each end
    xs = np.concatenate([[0.0], np.linspace(ends, w - ends, bones * columns + 1), [float(w)]]) if ends \
        else np.linspace(0, w, cols + 1)                   # strip x of every column
    s_all = (xs - ends) * length / (w - 2 * ends)          # arc length (beyond 0..length for the overhang)
    p, t = at_length(poly, cum, s_all)
    p = p + t * (s_all - np.clip(s_all, 0, length))[:, None]   # overhang: straight on along the end tangent
    nrm = np.stack([-t[:, 1], t[:, 0]], -1)                # left of travel = up for a path running left to right
    sc = across_scale or length / (w - 2 * ends)           # world units per strip pixel across the path
    top_off, bot_off = baseline * h * sc, (1 - baseline) * h * sc
    win = weight_window if weight_window >= 0 else (0.0 if corners == "smooth" else 0.9 * max(top_off, bot_off))
    if win > 0:
        t = smooth_tangent(poly, cum, s_all, win)
        nrm = np.stack([-t[:, 1], t[:, 0]], -1)
    world = sk.world()
    t_lim, b_lim = miter_limits(wp, cum, per, s_all, top_off, bot_off)
    tan_path = at_length(poly, cum, s_all)[1]
    top = unfold(p + nrm * t_lim[:, None], tan_path)
    bot = unfold(p - nrm * b_lim[:, None], tan_path)
    order_pts = np.vstack([top, bot[::-1], p])             # hull: along the top, back along the bottom; then the baseline
    order_s = np.concatenate([s_all, s_all[::-1], s_all])
    vertices: list[float] = []
    for q, sv in zip(order_pts, order_s):
        infl = window_weights(float(sv), length, bones, win)
        row: list[float] = [len(infl)]
        for bi_, wgt in infl:
            lx, ly = world[chain[bi_]].to_local(float(q[0]), float(q[1]))
            row += [sk.bone_index(chain[bi_]), round(lx, 3), round(ly, 3), round(wgt, 5)]
        vertices += row
    uvs: list[float] = []
    for j in range(cols + 1):
        uvs += [float(xs[j] / w), 0.0]
    for j in range(cols, -1, -1):
        uvs += [float(xs[j] / w), 1.0]
    for j in range(cols + 1):
        uvs += [float(xs[j] / w), float(baseline)]
    hull = 2 * (cols + 1)
    tris: list[int] = []
    for j in range(cols):
        t0, t1 = j, j + 1                                  # top row
        b0, b1 = 2 * cols + 1 - j, 2 * cols + 1 - (j + 1)  # bottom row (stored backwards)
        m0, m1 = hull + j, hull + j + 1                    # baseline row (interior)
        tris += [t0, t1, m1, t0, m1, m0, m0, m1, b1, m0, b1, b0]
    edges = []
    for i in range(hull):
        edges += [i * 2, ((i + 1) % hull) * 2]
    fx_slot = Slot(name=sk.unique_name(f"{name}_fx", "slot"), bone=parent, color=color,
                   blend=blend or ("additive" if mode == "additive" else "normal"))
    if behind:
        sk.add_slot(fx_slot, before=behind)
    elif front_of:
        sk.add_slot(fx_slot, after=front_of)
    else:
        sk.add_slot(fx_slot)
    att_names = []
    for part, _m, pr in written:
        an = f"fx_{part}" if part else "fx"
        sk.set_attachment(fx_slot.name, an, MeshAttachment(
            path=f"ae/{name}_{part + '_' if part else ''}", uvs=[round(v, 5) for v in uvs], triangles=tris,
            vertices=vertices, hull=hull, edges=edges, width=pr["tw"], height=pr["th"],
            sequence=Sequence(count=pr["n"], start=0, digits=pr["digits"])))
        att_names.append(an)

    # ---- animations
    base = animation or (name if parts else f"ae_{name}")
    anims = {}
    for (part, m, pr), an in zip(written, att_names):
        anim = f"{base}_{part}" if part else base
        ab = AnimBuilder(sk, anim, replace=not animation)    # a given animation name merges (two meshes, one clip)
        t0 = start
        end_t = until or max(t0 + pr["dur"], sk.animations[anim].duration() if anim in sk.animations else 0.0)
        if m == "once":
            end_t = t0 + pr["dur"]
        keys = [(t0, an), (r(end_t), None if m == "once" and not part else an)]
        if t0 > 0:
            keys.insert(0, (0.0, None))
        ab.slot_attachment(fx_slot.name, keys)
        ab.sequence(fx_slot.name, an, [(t0, m, 0, pr["delay"])])
        ab.event(t0, f"ae_{name}" + (f"_{part}" if part else ""))
        if demo_bend and not part or (demo_bend and m == "loop"):
            sway = demo_bend * length * 0.25
            period = max(end_t, 1.0)
            for i, cb in enumerate(ctrl):
                ph = i * 0.9
                ks = [(period * k / 8, 0.0, round(sway * math.sin(2 * math.pi * k / 8 + ph), 2)) for k in range(9)]
                ab.bone(cb, "translate", ks, "sine_in_out")
        anims[part or "main"] = {"animation": anim, "attachment": an, "mode": m, "frames_out": pr["n"],
                                 "delay": round(pr["delay"], 5), "duration": round(end_t - t0, 4),
                                 "image_size": [pr["tw"], pr["th"]], **({"note": pr["note"]} if pr["note"] else {})}

    first = anims[next(iter(anims))]
    return {"name": name, "animation": first["animation"], "animations": anims, "control_bones": ctrl,
            "chain_bones": chain, "path_slot": path_slot, "slot": fx_slot.name, "constraint": cname,
            "corners": corners, "weight_window": round(win, 2), "rig": rig or name, "path_length": round(length, 2), "mesh_vertices": hull, "bones": bones,
            "frames_out": sum(pr["n"] for *_, pr in written), "source_size": [w, h], "across_scale": round(sc, 4),
            "mode": mode, "source": src}
