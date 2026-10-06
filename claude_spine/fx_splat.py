"""Liquid splat from the artist's own splash layers, plus a violent shake / implode: the ``liquid_splat`` and
``shake`` tools' engine.

The splat follows a reference candy-slot burst frame by frame:

1. (optional) the symbol IMPLODES to a point while a white star flares (a symbol about to burst pinches in);
2. a zoom-blurred rainbow smear of the whole splash punches out for 4 frames (speed reads as radial blur);
3. a RING of liquid: every splash piece starts near the centre and flies out past its painted spot (pieces with
   little paint fly furthest), stretched along its flight, then slapped wide, leaving the middle hollow;
4. the ring thins into ribbons that shrink away together (no hanging, no fading one by one) while drips tear off
   it, are thrown out and rain down on gravity, shrinking;
5. a white starburst of thin rays and a lens streak, then a late thin glint.

Pieces get a bone at their own centre pointing away from the blast (bone x = radial), so stretch and squash act
along the flight. Lens flare ghosting, bloom and shockwave rings come from After Effects: the result's ``ae_hint``
says which templates to run and how to land them on the burst. ``prefix`` + ``offset`` clone the whole kit to
another spot (one splat per bomb in a column) sharing the same images.
"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

from .ir import Animation, Bone, EventData, EventKey, RegionAttachment, Slot
from .project import Project
from .rig import reparent_slot
from .sphere import _put, setup_art
from .timeline import color_keys, keys as make_keys, r

F = 1 / 30


# ------------------------------------------------------------------ textures
def _rgba(rgb, a) -> Image.Image:
    rgb = np.clip(rgb, 0, 1)
    if rgb.ndim == 2:
        rgb = np.dstack([rgb] * 3)
    return Image.fromarray((np.dstack([rgb, np.clip(a, 0, 1)[..., None]]) * 255).astype(np.uint8), "RGBA")


def tex_ray(w=512, h=32):
    y, x = np.mgrid[0:h, 0:w].astype(float)
    u = x / (w - 1)
    v = (y - (h - 1) / 2) / ((h - 1) / 2)
    along = np.clip(u / 0.06, 0, 1) * (1 - u) ** 1.6
    return _rgba(np.ones((h, w)), along * np.exp(-(v / 0.32) ** 2) + 0.5 * along * np.exp(-(v / 0.08) ** 2))


def tex_lens(w=1024, h=32):
    y, x = np.mgrid[0:h, 0:w].astype(float)
    u = np.abs(x - (w - 1) / 2) / ((w - 1) / 2)
    v = (y - (h - 1) / 2) / ((h - 1) / 2)
    along = np.exp(-u * 2.4) * (1 - u ** 3)
    return _rgba(np.ones((h, w)), along * (np.exp(-(v / 0.35) ** 2) * 0.7 + np.exp(-(v / 0.1) ** 2)))


def tex_drop(w=48, h=72):
    """White teardrop (tail up), tinted per slot."""
    y, x = np.mgrid[0:h, 0:w].astype(float)
    cx, cy, rad = (w - 1) / 2, h * 0.66, w * 0.42
    d = np.hypot(x - cx, y - cy) / rad
    tail = (y < cy) & (np.abs(x - cx) < rad * np.clip((y - h * 0.05) / (cy - h * 0.05), 0, 1) ** 1.6)
    a = np.clip((1 - d) * 6, 0, 1) + tail * 1.0
    shade = 0.75 + 0.25 * np.clip(1 - np.hypot(x - cx + rad * 0.3, y - cy + rad * 0.3) / rad, 0, 1)
    return _rgba(shade, np.clip(a, 0, 1))


def zoom_blur(im: Image.Image, cx: float, cy: float, steps: int = 12, reach: float = 0.35) -> Image.Image:
    """Radial (zoom) motion blur about (cx, cy), half size; the smear dies out before the layer's edge."""
    a = np.asarray(im.convert("RGBA")).astype(float) / 255
    a[a[..., 3] < 0.05] = 0
    pm = a.copy()
    pm[..., :3] *= pm[..., 3:4]
    H, W = a.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W].astype(float)
    acc = np.zeros_like(pm)
    for i in range(steps):
        k = 1 - reach * i / (steps - 1)
        sx, sy = cx + (xx - cx) * k, cy + (yy - cy) * k
        acc += np.stack([map_coordinates(pm[..., c], [sy, sx], order=1, mode="constant") for c in range(4)], -1)
    acc /= steps
    al = np.clip(acc[..., 3] * 1.35, 0, 1)
    e = np.minimum.reduce([xx, yy, W - 1 - xx, H - 1 - yy]) / (0.16 * max(W, H))
    al *= np.clip(e, 0, 1) ** 1.5
    al[al < 0.02] = 0
    rgb = np.where(acc[..., 3:4] > 1e-4, acc[..., :3] / np.maximum(acc[..., 3:4], 1e-4), 0)
    out = Image.fromarray((np.dstack([np.clip(rgb, 0, 1), al]) * 255).round().astype(np.uint8), "RGBA")
    return out.resize((max(1, W // 2), max(1, H // 2)), Image.LANCZOS)


# ------------------------------------------------------------------ the kit (bones + slots), built once
def _att_name(sk, slot: str) -> str:
    """A slot's own attachment name (its setup one, or its only one when hidden in the setup pose)."""
    s = sk.slot(slot)
    if s.attachment:
        return s.attachment
    names = list(sk.skin().attachments.get(slot, {}))
    if not names:
        raise ValueError(f"slot {slot!r} has no attachment")
    return names[0]


def _kit_names(name: str, prefix: str) -> dict:
    return {"blast": f"{prefix}{name}", "blur": f"{prefix}{name} blur", "lens": f"{prefix}{name} lens",
            "star": f"{prefix}{name} star", "drip": f"{prefix}{name} drip", "ray": f"{prefix}{name} ray"}


def build_kit(project: Project, slots: list[str], name: str = "splat", center=None, composite: str = "",
              drip_slots: list[str] | None = None, drips: int = 16, rays: int = 18, parent: str = "root",
              seed: int = 7) -> dict:
    """Bones and slots of the main kit (the artist's own slots move onto per-piece bones)."""
    sk = project.data
    rng = np.random.default_rng(seed)
    N = _kit_names(name, "")
    if sk.has_bone(N["blast"]):
        raise ValueError(f"a splat kit named {name!r} already exists")
    for s in slots + ([composite] if composite else []) + list(drip_slots or []):
        sk.slot(s)
    art, (ox, oy) = setup_art(project, slots + ([composite] if composite else []))
    a = np.asarray(art)[..., 3].astype(float)
    if center is None:
        ys, xs = np.mgrid[0:a.shape[0], 0:a.shape[1]]
        center = (ox + (a * xs).sum() / a.sum(), oy - (a * ys).sum() / a.sum())
    cx, cy = float(center[0]), float(center[1])
    sk.add_bone_world(N["blast"], parent, cx, cy, color="FF6FB8FF")
    areas = {}
    for s in slots:
        im, (sx, sy) = setup_art(project, [s])
        al = np.asarray(im)[..., 3].astype(float)
        yy, xx = np.mgrid[0:al.shape[0], 0:al.shape[1]]
        px, py = sx + (al * xx).sum() / al.sum(), sy - (al * yy).sum() / al.sum()
        areas[s] = float((al > 127).sum())
        bn = f"{name} {s}"
        sk.add_bone_world(bn, N["blast"], px, py, math.degrees(math.atan2(py - cy, px - cx)))
        reparent_slot(sk, s, bn)
    # the smeared burst
    comp_img = art if not composite else setup_art(project, [composite])[0]
    comp_origin = (ox, oy) if not composite else setup_art(project, [composite])[1]
    blur = zoom_blur(comp_img, cx - comp_origin[0], comp_origin[1] - cy)
    project.write_image(f"fx/{name}_blur", blur)
    W, H = comp_img.size
    bx, by = comp_origin[0] + W / 2 - cx, comp_origin[1] - H / 2 - cy
    sk.add_bone_world(N["blur"], N["blast"], cx, cy)
    sk.add_slot(Slot(name=N["blur"], bone=N["blur"]))
    sk.set_attachment(N["blur"], "fx", RegionAttachment(path=f"fx/{name}_blur", x=round(bx, 2), y=round(by, 2),
                                                        width=W, height=H))
    if composite:
        sk.slot(composite).attachment = None
    # drips: the artist's droplets, or a tinted teardrop in the splash's own colours
    rgb = np.asarray(art.convert("RGB")).reshape(-1, 3)[np.asarray(art)[..., 3].ravel() > 200]
    palette = rgb[rng.integers(0, len(rgb), 64)] if len(rgb) else np.full((64, 3), 255)
    if not drip_slots:
        project.write_image("fx/drop", tex_drop())
    for j in range(drips):
        bn = f"{N['drip']}{j + 1}"
        sk.add_bone_world(bn, N["blast"], cx, cy)
        if drip_slots:
            src = drip_slots[j % len(drip_slots)]
            ra = sk.attachment(src)
            k = float(rng.uniform(0.9, 1.5))
            sk.add_slot(Slot(name=bn, bone=bn))
            sk.set_attachment(bn, "fx", RegionAttachment(path=project.att_image_name(src, sk.slot(src).attachment),
                                                         width=round(ra.width * k, 2), height=round(ra.height * k, 2)))
        else:
            c = palette[j % len(palette)]
            sk.add_slot(Slot(name=bn, bone=bn, color=f"{c[0]:02X}{c[1]:02X}{c[2]:02X}FF"))
            s = float(rng.uniform(26, 46))
            sk.set_attachment(bn, "fx", RegionAttachment(path="fx/drop", width=round(s, 2), height=round(s * 1.5, 2)))
    project.write_image("fx/ray", tex_ray())
    project.write_image("fx/lens", tex_lens())
    from .fx import ensure_texture
    ensure_texture(project, "fx/spark")
    base = float(rng.uniform(0, 360))
    for j in range(rays):
        ang = base + j * 360 / rays + float(rng.uniform(-9, 9))
        L = float(rng.uniform(900, 1500)) * max(W, H) / 1200
        bn = f"{N['ray']}{j + 1}"
        sk.add_bone_world(bn, N["blast"], cx, cy, ang)
        sk.add_slot(Slot(name=bn, bone=bn, blend="additive", color="FFF6E0FF"))
        sk.set_attachment(bn, "fx", RegionAttachment(path="fx/ray", x=round(L / 2, 2), width=round(L, 2),
                                                     height=round(float(rng.uniform(8, 20)), 2)))
    for key, path, w, h, col in (("lens", "fx/lens", 2.2 * max(W, H), 40, "FFEAD2FF"),
                                 ("star", "fx/spark", 0.25 * max(W, H), 0.25 * max(W, H), "FFFFFFFF")):
        sk.add_bone_world(N[key], N["blast"], cx, cy)
        sk.add_slot(Slot(name=N[key], bone=N[key], blend="additive", color=col))
        sk.set_attachment(N[key], "fx", RegionAttachment(path=path, width=round(w, 2), height=round(h, 2)))
    # kit slots draw above everything they burst out of, in a fixed order
    kit_slots = [N["blur"]] + slots + [f"{N['drip']}{j + 1}" for j in range(drips)] + \
        [f"{N['ray']}{j + 1}" for j in range(rays)] + [N["lens"], N["star"]]
    rest = [s for s in sk.slots if s.name not in set(kit_slots)]
    by = {s.name: s for s in sk.slots}
    sk.slots = rest + [by[n] for n in kit_slots]
    for n in kit_slots:
        by[n].attachment = None
    big = max(areas.values())
    return {"name": name, "prefix": "", "center": [cx, cy], "pieces": slots,
            "far": [s for s, v in areas.items() if v < 0.15 * big], "drips": drips, "rays": rays}


def clone_kit(project: Project, name: str, pieces: list[str], prefix: str, offset) -> None:
    """Copy the main kit's bones and slots to `offset`, renamed with `prefix` (images shared)."""
    sk = project.data
    N0, N1 = _kit_names(name, ""), _kit_names(name, prefix)
    if sk.has_bone(N1["blast"]):
        return
    b0 = sk.bone(N0["blast"])
    sk.add_bone(Bone(name=N1["blast"], parent=b0.parent, x=b0.x + offset[0], y=b0.y + offset[1],
                     rotation=b0.rotation, color=b0.color))
    sub = [b for b in sk.descendants(N0["blast"]) if b != N0["blast"]]
    ren = {}
    for b in sub:
        bone = sk.bone(b)
        nb = prefix + b
        ren[b] = nb
        sk.add_bone(Bone(name=nb, parent=ren.get(bone.parent, N1["blast"]), x=bone.x, y=bone.y,
                         rotation=bone.rotation))
    for s in [s for s in sk.slots if s.bone in ren]:
        ns = prefix + s.name
        an = _att_name(sk, s.name)
        att = sk.attachment(s.name, an).model_copy()
        if s.name in pieces:
            att.path = att.path or an
        sk.add_slot(Slot(name=ns, bone=ren[s.bone], blend=s.blend, color=s.color))
        sk.set_attachment(ns, "fx", att)


def _kit(project: Project, name: str, prefix: str, pieces: list[str]) -> dict:
    sk = project.data
    N = _kit_names(name, prefix)
    world = sk.world()
    cw = world[N["blast"]]
    ps = []
    for s in pieces:
        sl = prefix + s if prefix else s
        b = world[sk.slot(sl).bone]
        an = _att_name(sk, sl)
        att = sk.attachment(sl, an)
        ps.append({"slot": sl, "bone": sk.slot(sl).bone, "att": an,
                   "off": (b.x - cw.x, b.y - cw.y), "area": att.width * att.height})
    big = max(p["area"] for p in ps)
    for p in ps:
        p["far"] = p["area"] < 0.15 * big
    drips = [b for b in [f"{N['drip']}{j}" for j in range(1, 999)] if sk.has_bone(b)]
    rays = [b for b in [f"{N['ray']}{j}" for j in range(1, 999)] if sk.has_bone(b)]
    blur = sk.attachment(N["blur"], "fx")
    return {**N, "pieces": ps, "drips": drips, "rays": rays, "size": max(blur.width, blur.height)}


# ------------------------------------------------------------------ keys
class _Keys:
    """Collects keys for one animation window and merges them in (keys outside the window survive)."""

    def __init__(self, sk, animation: str, t0: float, t1: float):
        self.sk, self.t0, self.t1 = sk, t0, t1
        self.anim = sk.animations.setdefault(animation, Animation())
        self.b: dict = {}
        self.c: dict = {}
        self.a: dict = {}

    def k(self, bone, tl, pts, ease="sine_in_out"):
        self.b.setdefault((bone, tl), []).extend([(*p, ease) if isinstance(p[-1], (int, float)) else p for p in pts])

    def col(self, slot, pts):
        self.c.setdefault(slot, []).extend(pts)

    def show(self, slot, name, t_on, t_off):
        self.a.setdefault(slot, []).extend([(t_on, name), (t_off, None)])

    def flush(self):
        for (bone, tl), pts in self.b.items():
            _put(self.anim.bones.setdefault(bone, {}), tl, make_keys(pts, tl), self.t0, self.t1)
        for slot, pts in self.c.items():
            _put(self.anim.slots.setdefault(slot, {}), "rgba", color_keys(pts), self.t0, self.t1)
        from .ir import Key
        for slot, pts in self.a.items():
            first = min(pts, key=lambda q: q[0])
            pre = [Key(time=0.0, name=None)] if first[0] > 1e-6 and first[1] is not None else []
            _put(self.anim.slots.setdefault(slot, {}), "attachment",
                 pre + [Key(time=r(t), name=n) for t, n in sorted(pts, key=lambda q: q[0])], self.t0, self.t1)


def _fade(a: float, rgb: str = "FFFFFF") -> str:
    return f"{rgb}{round(max(0, min(1, a)) * 255):02X}"


def _event(sk, anim: Animation, t: float, name: str) -> None:
    if name not in sk.events:
        sk.events[name] = EventData()
    anim.events = sorted(anim.events + [EventKey(time=r(t), name=name)], key=lambda e: e.time)


def liquid_splat(project: Project, slots: list[str], animation: str, at: float, name: str = "splat",
                 center=None, composite: str = "", drip_slots: list[str] | None = None, drips: int = 16,
                 rays: int = 18, scale: float = 1.0, seed: int = 1, implode_bone: str = "",
                 implode_from: float = 1.0, implode_hide: list[str] | None = None, prefix: str = "",
                 offset=(0.0, 0.0), lens: bool = True) -> dict:
    """Key the splat into `animation`, bursting at `at`. Builds the kit on first use (see module doc)."""
    sk = project.data
    info = {}
    if not sk.has_bone(_kit_names(name, "")["blast"]):
        info = build_kit(project, slots, name, center, composite, drip_slots, drips, rays)
    if prefix:
        clone_kit(project, name, slots, prefix, offset)
    kit = _kit(project, name, prefix, slots)
    rng = np.random.default_rng(seed)
    tb = at
    K = _Keys(sk, animation, tb - 0.16, tb + 1.25)
    s = scale
    if implode_bone:
        sk.bone(implode_bone)
        K.k(implode_bone, "scale", [(tb - 0.12, implode_from, implode_from, "cubic_in"), (tb, 0.03, 0.03, "linear")])
        for sl in implode_hide or []:
            K.a.setdefault(sl, []).append((tb, None))
        st = kit["star"]
        K.show(st, "fx", tb - 0.14, tb + 0.1)
        K.k(st, "scale", [(tb - 0.14, 0, 0, "cubic_in"), (tb - 0.01, 2.0 * s, 2.0 * s, "expo_out"), (tb + 0.1, 0, 0)])
        K.k(st, "rotate", [(tb - 0.14, 0, "linear"), (tb + 0.1, 70)])
    bl = kit["blur"]
    K.show(bl, "fx", tb, tb + 0.14)
    K.k(bl, "scale", [(tb, 0.3 * s, 0.3 * s, "expo_out"), (tb + 0.12, 0.95 * s, 0.95 * s)])
    K.k(bl, "rotate", [(tb, -14, "expo_out"), (tb + 0.13, 4)])
    K.col(bl, [(tb, _fade(1)), (tb + 0.06, _fade(1), "quad_in"), (tb + 0.14, _fade(0))])
    for j, sp in enumerate(kit["pieces"]):
        t0 = tb + 0.02 + 0.012 * (j % 4)
        ox, oy = sp["off"]
        reach = 1.9 if sp["far"] else 1.5
        life = 0.78 + float(rng.uniform(0, 0.1)) + (0.08 if sp["far"] else 0)
        K.show(sp["slot"], sp["att"], t0, t0 + life)
        mx, my = ox * (reach - 1), oy * (reach - 1)
        K.k(sp["bone"], "translate", [(t0, -ox * 0.72, -oy * 0.72, "expo_out"),
                                      (t0 + life * 0.62, mx, my - 12 * s, "quad_in"),
                                      (t0 + life, mx * 1.15, my * 1.15 - 75 * s, "linear")])
        K.k(sp["bone"], "scale", [(t0, 0.5 * s, 0.55 * s, "expo_out"), (t0 + 0.1, 1.18 * s, 1.0 * s, "sine_in_out"),
                                  (t0 + life * 0.35, 1.28 * s, 0.9 * s, "sine_in_out"),
                                  (t0 + life * 0.7, 0.8 * s, 0.45 * s, "sine_in"),
                                  (t0 + life, 0.1 * s, 0.05 * s, "linear")])
        curl = float(rng.uniform(10, 24)) * (1 if j % 2 else -1)
        K.k(sp["bone"], "rotate", [(t0, -curl * 0.3, "sine_out"), (t0 + life, curl, "linear")])
    reach_px = kit["size"] * 0.42 * s
    for bn in kit["drips"]:
        tl = tb + 0.2 + float(rng.uniform(0, 0.3))
        ang = float(rng.uniform(0, 2 * math.pi))
        r0 = float(rng.uniform(0.55, 0.95)) * reach_px
        spd = float(rng.uniform(0.6, 1.3)) * reach_px
        vx, vy = math.cos(ang) * spd, math.sin(ang) * spd + 0.4 * reach_px
        life = float(rng.uniform(0.45, 0.7))
        g = 3.9 * reach_px
        tr, sc, ro = [], [], []
        steps = max(4, int(life / (2 * F)))
        for k in range(steps + 1):
            tau = life * k / steps
            q = 1 - (k / steps) ** 1.6
            tr.append((tl + tau, math.cos(ang) * r0 + vx * tau, math.sin(ang) * r0 + vy * tau - 0.5 * g * tau * tau,
                       "linear"))
            sc.append((tl + tau, q * s, q * s, "linear"))
            ro.append((tl + tau, math.degrees(math.atan2(vy - g * tau, vx)) + 90, "linear"))
        K.show(bn, "fx", tl, tl + life)
        K.b[(bn, "translate")] = tr
        K.b[(bn, "scale")] = sc
        K.b[(bn, "rotate")] = ro
    for j, bn in enumerate(kit["rays"]):
        t0 = tb + 0.01 * (j % 3)
        L = float(rng.uniform(0.75, 1.25)) * s
        K.show(bn, "fx", t0, t0 + 0.45)
        K.k(bn, "scale", [(t0, 0.05, 1.8, "expo_out"), (t0 + 0.14, L, 1.0, "quad_out"), (t0 + 0.42, L * 1.2, 0.05, "linear")])
        K.col(bn, [(t0, _fade(1)), (t0 + 0.16, _fade(0.9), "quad_in"), (t0 + 0.42, _fade(0))])
    if lens:
        bn = kit["lens"]
        K.a.setdefault(bn, []).extend([(tb, "fx"), (tb + 0.4, None), (tb + 0.42, "fx"), (tb + 0.66, None)])
        K.k(bn, "scale", [(tb, 0.15 * s, 1.4, "expo_out"), (tb + 0.16, s, 1.0, "quad_out"),
                          (tb + 0.4, 1.2 * s, 0.15, "stepped"), (tb + 0.42, 0.2 * s, 0.6, "expo_out"),
                          (tb + 0.52, 0.9 * s, 0.45, "quad_in"), (tb + 0.66, 1.1 * s, 0.05, "linear")])
        K.col(bn, [(tb, _fade(0.85)), (tb + 0.16, _fade(0.7), "quad_in"), (tb + 0.4, _fade(0), "stepped"),
                   (tb + 0.42, _fade(0.75), "quad_in"), (tb + 0.66, _fade(0))])
    K.flush()
    _event(sk, K.anim, tb, "sfx_explode")
    cw = sk.world()[kit["blast"]]
    return {"animation": animation, "at": tb, "kit": kit["blast"], "pieces": len(kit["pieces"]),
            "drips": len(kit["drips"]), "rays": len(kit["rays"]), "built": bool(info), "center": [cw.x, cw.y],
            "ae_hint": {
                "lens_flare": "ae_template name=lens_flare (ghost chain) -> ae_fx_to_spine mode=additive "
                              f"parent={kit['blast']} anchor=[from_x, from_y] feather=0.22 hit_ae=2/fps hit_at={tb}",
                "shockwave": f"ae_template name=shockwave -> ae_fx_to_spine mode=additive parent={kit['blast']} "
                             f"start={tb + 0.02}",
                "bloom": f"ae_template name=glow_pulse -> ae_fx_to_spine mode=additive parent={kit['blast']} "
                         f"start={round(tb - F, 4)} fit_duration=0.5"}}


def shake(project: Project, animation: str, bone: str, start: float, end: float, amplitude: float = 20.0,
          rotation: float = 10.0, every: int = 2, grow: bool = True, seed: int = 3) -> dict:
    """A violent shake on `bone`: translate + rotate jumps every `every` frames (at 30 fps), growing toward `end`
    when grow (fear building up), back to rest at `end`. Merges into the animation's existing keys."""
    sk = project.data
    sk.bone(bone)
    rng = np.random.default_rng(seed)
    tr, ro = [(start, 0, 0, "linear")], [(start, 0, "linear")]
    t, n = start, 0
    while t + every * F < end - 1e-6:
        t += every * F
        n += 1
        k = ((t - start) / (end - start)) ** 1.3 if grow else 1.0
        ang = rng.uniform(0, 2 * math.pi)
        tr.append((t, math.cos(ang) * amplitude * k, math.sin(ang) * amplitude * k, "linear"))
        ro.append((t, float(rng.choice([-1, 1])) * rotation * k * rng.uniform(0.6, 1), "linear"))
    tr.append((end, 0, 0, "linear"))
    ro.append((end, 0, "linear"))
    anim = sk.animations.setdefault(animation, Animation())
    node = anim.bones.setdefault(bone, {})
    _put(node, "translate", make_keys(tr, "translate"), start, end)
    _put(node, "rotate", make_keys(ro, "rotate"), start, end)
    _event(sk, anim, start, "sfx_rumble")
    return {"animation": animation, "bone": bone, "start": start, "end": end, "jumps": n}
