"""A round symbol turned in real 3D: the ``sphere_spin`` tool's engine.

A flat ``scaleX = cos`` card flip squeezes a ball to a sliver; a ball never does that. Here the artist's own art
is wrapped onto a sphere and re-projected while it turns around the vertical axis:

* the visible (front) hemisphere is unwrapped to longitude/latitude (orthographic projection);
* the back is filled by repeating the art's own pattern along longitude (its period is found by autocorrelation
  and snapped to divide 360), blended into the real front wherever the front is well sampled, so stripes run on
  round the back with no mirror "V" seams;
* the light stays put: the art's radial shading (rim darkening) is divided out before the turn and put back after,
  holes in the art (under a cap) are filled from the nearest paint, and the art's white specular glints are
  composited back at their fixed screen spots;
* each frame averages a few sub-angles (motion blur), and frame 0 is the artist's own pixels.

In the skeleton the frames become a sequence attachment keyed frame by frame (``hold``), the original slots hide
during the turn, bones riding the surface (a cap) orbit it with the correct tilt and foreshortening and pass BEHIND
the ball through draw-order keys, and bones that stick out sideways (a wick) flatten and flip as they turn.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, gaussian_filter, map_coordinates

from .ir import Animation, DrawOrderKey, DrawOrderOffset, Key, MeshAttachment, RegionAttachment, Sequence, Slot
from .mesh import mesh_world_vertices, region_pixel_to_local, to_world
from .project import Project
from .timeline import keys as make_keys, r

SPIN_EVENT = "sfx_spin"


# ------------------------------------------------------------------ the art in world space
def setup_art(project: Project, slots: list[str], px_per_unit: float = 1.0):
    """Composite the setup pose of `slots` (draw order) into one RGBA image in world space.
    Returns (image, (x0, y1)): the world coords of the image's top-left pixel corner (y up)."""
    sk = project.data
    world = sk.world()
    items = []
    for name in [s.name for s in sk.slots if s.name in set(slots)]:
        s = sk.slot(name)
        if not s.attachment:
            continue
        att = sk.attachment(name)
        im = project.image(project.att_image_name(name, s.attachment)).convert("RGBA")
        W, H = im.size
        if isinstance(att, RegionAttachment):
            f, _ = region_pixel_to_local(att, W, H)
            src = np.array([[0, 0], [W, 0], [0, H]], float)
            dst = to_world(world[s.bone], f(src))
        elif isinstance(att, MeshAttachment):
            wv = mesh_world_vertices(sk, name, att, world)
            uv = np.asarray(att.uvs, float).reshape(-1, 2) * [W, H]
            A, *_ = np.linalg.lstsq(np.c_[uv, np.ones(len(uv))], wv, rcond=None)
            src = np.array([[0, 0], [W, 0], [0, H]], float)
            dst = np.c_[src, np.ones(3)] @ A
        else:
            continue
        items.append((im, src, dst))
    if not items:
        raise ValueError(f"none of {slots} shows a region or mesh in the setup pose")
    pts = np.vstack([d for _, s, d in items for d in [_corners(s, d)]])
    x0, y0 = pts.min(0)
    x1, y1 = pts.max(0)
    Wc, Hc = int(math.ceil((x1 - x0) * px_per_unit)) + 2, int(math.ceil((y1 - y0) * px_per_unit)) + 2
    canvas = Image.new("RGBA", (Wc, Hc))
    for im, src, dst in items:
        cpx = np.c_[(dst[:, 0] - x0) * px_per_unit, (y1 - dst[:, 1]) * px_per_unit]
        # affine canvas -> image (PIL wants the inverse map)
        M = np.linalg.solve(np.c_[cpx, np.ones(3)], src)
        layer = im.transform((Wc, Hc), Image.AFFINE, tuple(M.T.ravel()), resample=Image.BILINEAR)
        canvas.alpha_composite(layer)
    return canvas, (float(x0), float(y1))


def _corners(src, dst):
    A = np.linalg.solve(np.c_[src, np.ones(3)], dst)
    W, H = src[1, 0], src[2, 1]
    return np.c_[np.array([[0, 0], [W, 0], [0, H], [W, H]], float), np.ones(4)] @ A


def fit_sphere(img: Image.Image, origin) -> tuple[float, float, float, float, float]:
    """(cx, cy) in image px, R in px, and the centre in world space, from the art's opaque area."""
    a = np.asarray(img)[..., 3] > 127
    ys, xs = np.nonzero(a)
    cx, cy = float(xs.mean()), float(ys.mean())
    R = math.sqrt(a.sum() / math.pi)
    return cx, cy, R, origin[0] + cx, origin[1] - cy


# ------------------------------------------------------------------ rendering the turn
def _unwrap(rgb, cx, cy, R, W=1440, H=512):
    lon = (np.arange(W) + 0.5) / W * 180 - 90
    lat = 90 - (np.arange(H) + 0.5) / H * 180
    LON, LAT = np.meshgrid(np.radians(lon), np.radians(lat))
    x = cx + R * np.cos(LAT) * np.sin(LON)
    y = cy - R * np.sin(LAT)
    return np.stack([map_coordinates(rgb[..., c], [y, x], order=1, mode="nearest") for c in range(3)], -1)


def _wrap_around(front, blend=14.0):
    """Full 360 texture: the pattern's own longitude period, snapped to divide 360, tiled round the back."""
    W, H = front.shape[1], front.shape[0]
    dpp = 180 / W
    f = front[int(H * 0.25):int(H * 0.75)].mean(-1)
    best, bestP = -1e9, 120.0
    for P in np.arange(60, 150, 1.0):
        k = int(round(P / dpp))
        lo, hi = int(20 / dpp), int((160 - P) / dpp)
        if hi <= lo + 10:
            continue
        a, b = f[:, :W - k][:, lo:hi], f[:, k:][:, lo:hi]
        if a.std() < 1e-6 or b.std() < 1e-6:
            continue
        c = np.corrcoef(a.ravel(), b.ravel())[0, 1]
        if c > best:
            best, bestP = c, P
    P = 360 / max(3, round(360 / bestP))
    Wf = int(round(360 / dpp))
    lon = (np.arange(Wf) + 0.5) * dpp - 180
    base = ((lon + P / 2) % P) - P / 2
    alt = np.where(base > 0, base - P, base + P)
    w = np.clip((np.abs(base) - (P / 2 - blend)) / blend, 0, 1) * 0.5
    w = np.where(np.abs(alt) < 88, w, 0)
    rows = np.repeat(np.arange(H)[:, None], Wf, 1)

    def sample(deg):
        x = np.repeat(((deg + 90) / dpp - 0.5)[None, :], H, 0)
        return np.stack([map_coordinates(front[..., c], [rows, x], order=1, mode="nearest") for c in range(3)], -1)
    tiled = sample(base) * (1 - w)[None, :, None] + sample(alt) * w[None, :, None]
    wf = np.clip((86 - np.abs(lon)) / 14, 0, 1)
    return sample(np.clip(lon, -89.9, 89.9)) * wf[None, :, None] + tiled * (1 - wf)[None, :, None], P


def _profile(lum, alpha, cx, cy, R, bins=48):
    yy, xx = np.mgrid[0:lum.shape[0], 0:lum.shape[1]]
    rr = np.hypot(xx - cx, yy - cy) / R
    prof = np.ones(bins)
    for i in range(bins):
        m = (rr >= i / bins) & (rr < (i + 1) / bins) & (alpha > 0.9)
        if m.sum() > 20:
            prof[i] = np.median(lum[m])
    prof = gaussian_filter(prof, 1.5)
    k = int(bins * 0.55)
    prof[:k] = prof[k]                      # only the rim darkening is shading; the middle is paint
    return prof / max(np.median(prof[: bins * 2 // 3]), 1e-3)


def render_turn(art: Image.Image, cx: float, cy: float, R: float, frames: int = 24, size: int = 640,
                pad: float = 6.0, blur_sub: int = 3) -> tuple[list[Image.Image], float, dict]:
    """`frames` images of one full turn (frame k = k * 360 / frames degrees, surface moving to the right).
    Returns (images, size of the square in art pixels, info)."""
    a = np.asarray(art.convert("RGBA")).astype(float) / 255
    rgb, al = a[..., :3], a[..., 3]
    lum = rgb @ [0.3, 0.59, 0.11]
    prof = _profile(lum, al, cx, cy, R)
    rc = (np.arange(len(prof)) + 0.5) / len(prof)
    yy, xx = np.mgrid[0:a.shape[0], 0:a.shape[1]]
    shade_src = np.interp(np.clip(np.hypot(xx - cx, yy - cy) / R, 0, 0.999), rc, prof)
    albedo = np.clip(rgb / shade_src[..., None], 0, 1.4)
    holes = al < 0.6
    if holes.any() and (~holes).any():
        _, (iy, ix) = distance_transform_edt(holes, return_indices=True)
        albedo = albedo[iy, ix]
    tex, period = _wrap_around(_unwrap(albedo, cx, cy, R))
    sat = rgb.max(-1) - rgb.min(-1)
    glint = gaussian_filter(np.clip((lum - 0.9) / 0.08, 0, 1) * np.clip((0.12 - sat) / 0.08, 0, 1) * (al > 0.5), 1.2)

    ext = R + pad
    g = (np.arange(size) + 0.5) / size * 2 * ext - ext
    X, Y = np.meshgrid(g, g)
    rho = np.hypot(X, Y) / R
    inside = rho < 1
    Z = np.sqrt(np.clip(1 - rho ** 2, 0, 1)) * R
    lat = np.arcsin(np.clip(-Y / R, -1, 1))
    lon0 = np.arctan2(X, Z)
    edge = np.clip((R - np.hypot(X, Y)) / (2 * ext / size) + 0.5, 0, 1)
    shade_dst = np.interp(np.clip(rho, 0, 0.999), rc, prof)
    sx, sy = cx + X, cy + Y
    glint_d = map_coordinates(glint, [sy, sx], order=1, mode="constant")
    orig = np.stack([map_coordinates(rgb[..., c], [sy, sx], order=1, mode="nearest") for c in range(3)], -1)
    Ht, Wt = tex.shape[:2]
    out_imgs = []
    for k in range(frames):
        acc = np.zeros((size, size, 3))
        for s in range(blur_sub):
            th = 2 * math.pi * (k + (s - (blur_sub - 1) / 2) / blur_sub) / frames
            lon = (lon0 - th + math.pi) % (2 * math.pi) - math.pi
            u = (lon + math.pi) / (2 * math.pi) * Wt - 0.5
            v = (math.pi / 2 - lat) / math.pi * Ht - 0.5
            acc += np.stack([map_coordinates(tex[..., c], [v, u], order=1, mode="wrap") for c in range(3)], -1)
        col = orig if k == 0 else np.clip(acc / blur_sub * shade_dst[..., None], 0, 1)
        col = col * (1 - glint_d[..., None]) + orig * glint_d[..., None]
        out = np.dstack([col, edge * inside])
        out_imgs.append(Image.fromarray((out * 255).round().astype(np.uint8), "RGBA"))
    return out_imgs, 2 * ext, {"period_deg": round(float(period), 2), "radius_px": round(R, 2)}


# ------------------------------------------------------------------ keys, merged into an animation
def _smootherstep(u):
    return u * u * u * (u * (6 * u - 15) + 10)


def _drop_window(ks: list[Key], t0: float, t1: float) -> list[Key]:
    """Existing keys outside [t0, t1]; the key leading into the window loses its curve (its old partner is gone)."""
    out = [k for k in ks if k.time < t0 - 1e-6 or k.time > t1 + 1e-6]
    for i, k in enumerate(out):
        if k.time < t0 and (i + 1 == len(out) or out[i + 1].time > t1):
            if getattr(k, "curve", None) not in (None, "stepped"):
                k.curve = None
    return out


def _put(store: dict, key: str, new: list[Key], t0: float, t1: float) -> None:
    store[key] = sorted(_drop_window(store.get(key, []), t0, t1) + new, key=lambda k: k.time)


def sphere_spin(project: Project, slots: list[str], animation: str, start: float = 0.0, duration: float = 1.0,
                turns: int = 1, riders: list[str] | None = None, flip: list[str] | None = None, glow: float = 0.0,
                frames: int = 24, size: int = 640, name: str = "spin", host: str = "", fps: float = 30.0,
                frames_from: str = "") -> dict:
    """Turn the ball made of `slots` around its vertical axis inside `animation` (created if missing).

    riders: bones on the surface that orbit with it, as one group led by the first (a cap; their slots pass
    behind the ball). flip: bones that
    stick out sideways and turn with it (a wick: flattened by cos, mirrored past 90). glow > 0 adds an additive
    twin that swells to that alpha mid-turn. host: the bone the ball sprite rides (default the first slot's bone).
    Re-running reuses the frames and slots already made for `name`. frames_from: the name of a spin already made on
    a ball with the same art (a copy made with clone_art): its frames are reused, scaled to this ball, nothing is
    rendered and the atlas holds one set."""
    sk = project.data
    if turns < 1:
        raise ValueError("turns must be a whole number >= 1 (the ball has to end where it started)")
    for s in slots:
        sk.slot(s)
    riders, flip = list(riders or []), list(flip or [])
    for b in riders + flip:
        sk.bone(b)
    body, twin = f"{name} body", f"{name} glow"
    host = host or sk.slot(slots[0]).bone
    world = sk.world()
    path = f"spin/{name}_"
    made = sk.has_slot(body)
    if made:
        att = sk.attachment(body, "fx")
        frames = att.sequence.count
        cxw, cyw = world[sk.slot(body).bone].to_world(att.x, att.y)
        R = float(att.width) / 2 - 6.0                      # the sprite is the ball + a 6 px margin
        info = {"reused": True}
    else:
        art, origin = setup_art(project, slots)
        cx, cy, R, cxw, cyw = fit_sphere(art, origin)
        if frames_from:
            src = f"{frames_from} body"
            if not sk.has_slot(src):
                raise ValueError(f"frames_from={frames_from!r}: no spin named that (no slot {src!r})")
            satt = sk.attachment(src, "fx")
            path, frames, digits = satt.path, satt.sequence.count, satt.sequence.digits
            span = float(satt.width) * R / (float(satt.width) / 2 - 6.0)
            info = {"reused": True, "frames_from": frames_from}
        else:
            imgs, span, info = render_turn(art, cx, cy, R, frames, size)
            digits = max(2, len(str(frames - 1)))
            for k, im in enumerate(imgs):
                project.write_image(f"{path}{str(k).zfill(digits)}", im)
        lx, ly = world[host].to_local(cxw, cyw)

        def seq_att():
            return RegionAttachment(path=path, x=round(lx, 2), y=round(ly, 2), width=round(span, 2),
                                    height=round(span, 2), sequence=Sequence(count=frames, start=0, digits=digits))
        last = max(sk.slot_index(s) for s in slots)
        sk.add_slot(Slot(name=body, bone=host), after=sk.slots[last].name)
        sk.set_attachment(body, "fx", seq_att())
        sk.add_slot(Slot(name=twin, bone=host, blend="additive"), after=body)
        sk.set_attachment(twin, "fx", seq_att())
        world = sk.world()
    anim = sk.animations.setdefault(animation, Animation())
    t0, t1 = start, start + duration
    # attachments: ball shown, original slots hidden, for the window
    for s in slots:
        setup = sk.slot(s).attachment
        _put(anim.slots.setdefault(s, {}), "attachment", [Key(time=r(t0), name=None), Key(time=r(t1), name=setup)],
             t0, t1)
    shown = [body] + ([twin] if glow > 0 else [])
    for s in shown:
        pre = [] if t0 <= 1e-6 else [Key(time=0.0, name=None)]
        _put(anim.slots.setdefault(s, {}), "attachment", pre + [Key(time=r(t0), name="fx"), Key(time=r(t1), name=None)],
             t0, t1)
    if glow > 0:
        from .timeline import color_keys
        _put(anim.slots.setdefault(twin, {}), "rgba", color_keys(
            [(t0, "FFFFFF00"), ((t0 + t1) / 2, f"FFFFFF{round(glow * 255):02X}", "sine_in"), (t1, "FFFFFF00")]),
            t0, t1)
    n = max(2, int(round(duration * fps)))
    seq = []
    rider_keys = {b: {"translate": [], "rotate": [], "scale": []} for b in riders}
    flip_keys = {b: [] for b in flip}
    behind_spans, state = [], {}
    geo = {}
    for b in riders:
        hx, hy = world[b].x - cxw, world[b].y - cyw
        rr2 = R * R - hx * hx - hy * hy
        z = math.sqrt(rr2) if rr2 > 0 else 0.0
        L = math.sqrt(hx * hx + hy * hy + z * z) or 1.0
        nx, ny, nz = hx / L, hy / L, z / L
        geo[b] = (hx, z, nx, ny, nz, math.atan2(ny, nx), math.hypot(nx, ny) or 1e-6)
    for i in range(n + 1):
        t = t0 + duration * i / n
        th = 2 * math.pi * turns * _smootherstep(i / n)
        cs, sn = math.cos(th), math.sin(th)
        seq.append(Key(time=r(t, 5), mode="hold", index=int(round(th / (2 * math.pi) * frames)) % frames))
        for b in riders:
            hx, z, nx, ny, nz, a0, L0 = geo[b]
            nxr = nx * cs + nz * sn
            rk = rider_keys[b]
            rk["translate"].append((t, hx * cs + z * sn - hx, 0, "linear"))
            rk["rotate"].append((t, math.degrees(math.atan2(ny, nxr) - a0), "linear"))
            rk["scale"].append((t, math.hypot(nxr, ny) / L0, 1, "linear"))
            behind = -hx * sn + z * cs < 0
            if state.get(b) != behind:
                behind_spans.append((t, b, behind))
                state[b] = behind
        for b in flip:
            fl = max(abs(cs), 0.04) * (1 if cs >= 0 else -1)
            rot = math.radians(world[b].rotation)
            flip_keys[b].append((t, 1, fl, "linear") if abs(math.sin(rot)) > abs(math.cos(rot)) else (t, fl, 1, "linear"))
    for s in shown:
        node = anim.attachments.setdefault("default", {}).setdefault(s, {}).setdefault("fx", {})
        node["sequence"] = sorted(_drop_window(node.get("sequence", []), t0, t1) + seq, key=lambda k: k.time)
    for b, rk in rider_keys.items():
        node = anim.bones.setdefault(b, {})
        _put(node, "translate", make_keys(rk["translate"] + [(t1, 0, 0)], "translate"), t0, t1)
        _put(node, "rotate", make_keys(rk["rotate"] + [(t1, 0)], "rotate"), t0, t1)
        _put(node, "scale", make_keys(rk["scale"] + [(t1, 1, 1)], "scale"), t0, t1)
    for b, fk in flip_keys.items():
        _put(anim.bones.setdefault(b, {}), "scale", make_keys(fk + [(t1, 1, 1)], "scale"), t0, t1)
    # draw order: while a rider is behind, the ball draws after the rider's slots
    rider_slots = []
    for b in riders:
        sub = set(sk.descendants(b)) | {b}
        rider_slots += [s.name for s in sk.slots if s.bone in sub]
    anim.drawOrder = [d for d in anim.drawOrder if d.time < t0 - 1e-6 or d.time > t1 + 1e-6]
    behind_now = False
    lead = riders[0] if riders else None                    # riders move as one group (a cap and its wick)
    for t, b, beh in behind_spans:
        if b != lead or beh == behind_now:
            continue
        behind_now = beh
        if behind_now and rider_slots:
            order = [s.name for s in sk.slots]
            moved = [s for s in shown]
            rest = [s for s in order if s not in moved]
            i = max(rest.index(s) for s in rider_slots) + 1
            new = rest[:i] + moved + rest[i:]
            offs = [DrawOrderOffset(slot=s, offset=new.index(s) - order.index(s)) for s in moved]
            anim.drawOrder.append(DrawOrderKey(time=r(t, 5), offsets=sorted(offs, key=lambda o: sk.slot_index(o.slot))))
        else:
            anim.drawOrder.append(DrawOrderKey(time=r(t, 5), offsets=None))
    if behind_now:
        anim.drawOrder.append(DrawOrderKey(time=r(t1, 5), offsets=None))
    anim.drawOrder.sort(key=lambda d: d.time)
    from .ir import EventData, EventKey
    if SPIN_EVENT not in sk.events:
        sk.events[SPIN_EVENT] = EventData()
    anim.events = sorted(anim.events + [EventKey(time=r(t0), name=SPIN_EVENT)], key=lambda e: e.time)
    return {"animation": animation, "body_slot": body, "glow_slot": twin if glow > 0 else None, "frames": frames,
            "start": t0, "end": t1, "turns": turns, "riders": riders, "flip": flip,
            "behind": [[round(t, 3), b, beh] for t, b, beh in behind_spans], "images": f"images/{path}*", **info}
