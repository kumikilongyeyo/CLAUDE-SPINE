"""PSD → project: one slot per visible art layer, positioned exactly as on the
canvas, PNGs cropped to their content.

* Layer order becomes draw order (bottom layer drawn first).
* Groups flatten to ``group/layer`` names by default, or become bones
  (``groups_as_bones=True``) pivoting at the group's bottom-centre.
* Blend modes map: Linear Dodge/Add → additive, Screen → screen,
  Multiply → multiply.
* Layer names may carry tags: ``eye_l [mesh]`` (mark for meshing) or
  ``glow [additive]``. Tags are stripped from slot names and reported.

psd-tools trap: ``composite()`` renders a *hidden* smart object as empty, so
hidden layers are read with ``topil()`` when ``include_hidden`` is set.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
from PIL import Image

from .ir import RegionAttachment, Slot, new_skeleton
from .project import Project

BLEND = {"linear_dodge": "additive", "add": "additive", "screen": "screen", "multiply": "multiply",
         "color_dodge": "additive", "lighten": "screen"}
TAG = re.compile(r"\s*\[([a-z0-9_:=.\- ]+)\]\s*", re.I)


def _clean(name: str) -> tuple[str, list[str]]:
    tags = [t.strip().lower() for t in TAG.findall(name)]
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)   # invisible control chars (a stray DEL) break file names
    base = TAG.sub(" ", name).strip()
    base = re.sub(r"[\\:*?\"<>|]+", "_", base) or "layer"
    return base, tags


def _blend_name(layer) -> str | None:
    try:
        bm = str(layer.blend_mode).split(".")[-1].lower()
    except Exception:  # noqa: BLE001
        return None
    for k, v in BLEND.items():
        if k in bm:
            return v
    return None


def inspect(psd_path: str) -> dict:
    from psd_tools import PSDImage
    psd = PSDImage.open(psd_path)
    rows = []

    def walk(group, prefix, depth):
        for layer in group:
            nm, tags = _clean(layer.name)
            row = {"name": prefix + nm, "kind": layer.kind, "visible": layer.is_visible(), "bbox": list(layer.bbox),
                   "blend": _blend_name(layer), "tags": tags, "depth": depth}
            rows.append(row)
            if layer.is_group():
                walk(layer, prefix + nm + "/", depth + 1)

    walk(psd, "", 0)
    return {"width": psd.width, "height": psd.height, "layers": rows,
            "art_layers": sum(1 for r in rows if r["kind"] != "group" and r["visible"])}


def import_psd(psd_path: str, out_dir: str, name: str | None = None, origin: str = "center",
               groups_as_bones: bool = False, include_hidden: bool = False, scale: float = 1.0,
               alpha_threshold: int = 8) -> dict:
    """origin: "center" (slot symbols) or "bottom" (characters stand on y=0). Pixels at or below
    alpha_threshold are cleared before cropping, so a layer with faint stray alpha over the whole canvas
    (a soft brush, a feathered selection) crops to its real art instead of the full canvas."""
    from psd_tools import PSDImage
    psd = PSDImage.open(psd_path)
    W, H = psd.width, psd.height
    name = name or Path(psd_path).stem
    out = Path(out_dir)
    sk = new_skeleton(width=W * scale, height=H * scale)
    proj = Project(out / f"{name}.json", sk)
    ox = W / 2
    oy = H / 2 if origin == "center" else H
    if origin not in ("center", "bottom"):
        raise ValueError("origin is center|bottom")
    report = {"slots": [], "skipped": [], "tags": {}, "bones": []}

    def to_world(px, py):
        return (px - ox) * scale, (oy - py) * scale

    def walk(group, prefix, bone):
        for layer in group:
            nm, tags = _clean(layer.name)
            if layer.is_group():
                if not layer.is_visible() and not include_hidden:
                    report["skipped"].append(prefix + nm + " (hidden group)")
                    continue
                b = bone
                if groups_as_bones and layer.bbox != (0, 0, 0, 0):
                    l, t, r, btm = layer.bbox
                    bx, by = to_world((l + r) / 2, btm)
                    b = sk.unique_name(nm.replace("/", "_"))
                    sk.add_bone_world(b, bone, bx, by, 0)
                    report["bones"].append(b)
                walk(layer, prefix + nm + "/", b)
                continue
            if not layer.is_visible() and not include_hidden:
                report["skipped"].append(prefix + nm + " (hidden)")
                continue
            if layer.bbox == (0, 0, 0, 0):
                report["skipped"].append(prefix + nm + " (empty)")
                continue
            im = None
            try:
                im = layer.composite() if layer.is_visible() else layer.topil()
            except Exception:  # noqa: BLE001
                im = None
            if im is None:
                try:
                    im = layer.topil()
                except Exception:  # noqa: BLE001
                    im = None
            if im is None:
                report["skipped"].append(prefix + nm + " (could not render)")
                continue
            im = im.convert("RGBA")
            if alpha_threshold > 0:
                a = np.asarray(im).copy()
                a[a[..., 3] <= alpha_threshold] = 0
                im = Image.fromarray(a, "RGBA")
            l, t = layer.bbox[0], layer.bbox[1]
            bbox = im.getchannel("A").getbbox()
            if bbox is None:
                report["skipped"].append(prefix + nm + " (fully transparent)")
                continue
            im = im.crop(bbox)
            l, t = l + bbox[0], t + bbox[1]
            if scale != 1.0:
                im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
            slot_name = sk.unique_name(prefix + nm, "slot")
            proj.write_image(slot_name, im)
            cx, cy = to_world(l + im.width / scale / 2, t + im.height / scale / 2)
            wb = sk.world()[bone]
            lx, ly = wb.to_local(cx, cy)
            blend = _blend_name(layer) or ("additive" if "additive" in tags else "normal")
            alpha = layer.opacity / 255 if hasattr(layer, "opacity") else 1.0
            color = "FFFFFF" + f"{round(alpha * 255):02X}"
            sk.slots.append(Slot(name=slot_name, bone=bone, attachment=slot_name, blend=blend, color=color))
            sk.set_attachment(slot_name, slot_name, RegionAttachment(x=round(lx, 2), y=round(ly, 2),
                                                                     width=im.width, height=im.height))
            report["slots"].append(slot_name)
            if tags:
                report["tags"][slot_name] = tags

    walk(psd, "", "root")
    proj.save()
    return {"project": str(proj.path), "images": str(proj.images_dir), "canvas": [W, H], **report}
