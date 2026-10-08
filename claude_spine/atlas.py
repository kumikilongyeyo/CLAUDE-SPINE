"""Texture atlas packing in the Spine 4.x atlas format.

MaxRects (best short side fit) without rotation, optional whitespace strip,
optional premultiplied alpha. Only the images the skeleton actually references
are packed, so leftovers in ``images/`` never bloat the page.

Format notes that bite:
* ``offsets: left, bottom, origW, origH`` — the y offset is measured from the
  *bottom* of the original image (runtime MeshAttachment.updateRegion computes
  the top gap as ``origH - offsetY - height``).
* Region names must match attachment paths exactly, sequence frames included
  (``shine/f1_00``). Spine's own packer with ``useIndexes`` renames sequence
  frames to ``shine/f1`` + index and the runtime then fails with "Region not
  found"; this packer never does that.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .project import Project


@dataclass
class Placed:
    name: str
    page: int
    x: int
    y: int
    w: int
    h: int
    left: int
    top: int
    orig_w: int
    orig_h: int


class _MaxRects:
    def __init__(self, w: int, h: int):
        self.w, self.h = w, h
        self.free = [(0, 0, w, h)]

    def insert(self, w: int, h: int):
        best, bs, bl = None, 1 << 30, 1 << 30
        for fx, fy, fw, fh in self.free:
            if w <= fw and h <= fh:
                ss, ls = min(fw - w, fh - h), max(fw - w, fh - h)
                if ss < bs or (ss == bs and ls < bl):
                    best, bs, bl = (fx, fy), ss, ls
        if best is None:
            return None
        self._split(best[0], best[1], w, h)
        return best

    def _split(self, x, y, w, h):
        out = []
        for fx, fy, fw, fh in self.free:
            if x >= fx + fw or x + w <= fx or y >= fy + fh or y + h <= fy:
                out.append((fx, fy, fw, fh))
                continue
            if x > fx:
                out.append((fx, fy, x - fx, fh))
            if x + w < fx + fw:
                out.append((x + w, fy, fx + fw - x - w, fh))
            if y > fy:
                out.append((fx, fy, fw, y - fy))
            if y + h < fy + fh:
                out.append((fx, y + h, fw, fy + fh - y - h))
        # prune rectangles contained in others
        pruned = []
        for i, a in enumerate(out):
            if not any(i != j and a[0] >= b[0] and a[1] >= b[1] and a[0] + a[2] <= b[0] + b[2]
                       and a[1] + a[3] <= b[1] + b[3] and (a != b or j < i) for j, b in enumerate(out)):
                pruned.append(a)
        self.free = pruned


def mesh_uv_extent(project: Project) -> dict[str, tuple[float, float, float, float] | None]:
    """For every image a mesh draws: the UV box its vertices reach, (u0, v0, u1, v1) in 0..1 of the ORIGINAL image
    (v down). Whitespace stripping must never crop inside it: a mesh vertex in the stripped border would map outside
    the packed region and sample the neighbouring image on the page (a 9-slice's soft corner, a contour hull padded
    past the art). Linked meshes get None (their UVs live on the parent): never strip those."""
    out: dict[str, tuple[float, float, float, float] | None] = {}

    def add(name, box):
        if name in out and (out[name] is None or box is None):
            out[name] = None
        elif name in out:
            o = out[name]
            out[name] = (min(o[0], box[0]), min(o[1], box[1]), max(o[2], box[2]), max(o[3], box[3]))
        else:
            out[name] = box
    for skin in project.data.skins:
        for an, att in ((an, att) for atts in skin.attachments.values() for an, att in atts.items()):
            if att.type not in ("mesh", "linkedmesh"):
                continue
            path = getattr(att, "path", None) or an
            seq = getattr(att, "sequence", None)
            frames = [path] if seq is None else [f"{path}{str(seq.start + i).zfill(seq.digits)}" for i in range(seq.count)]
            uv = getattr(att, "uvs", None) if att.type == "mesh" else None
            box = (min(uv[0::2]), min(uv[1::2]), max(uv[0::2]), max(uv[1::2])) if uv else None
            for fr in frames:
                add(fr, box)
    return out


def referenced_images(project: Project) -> list[str]:
    names: list[str] = []
    seen = set()
    for skin in project.data.skins:
        for slot, atts in skin.attachments.items():
            for an, att in atts.items():
                if att.type not in ("region", "mesh"):
                    continue
                path = getattr(att, "path", None) or an
                seq = getattr(att, "sequence", None)
                frames = [path] if seq is None else [
                    f"{path}{str(seq.start + i).zfill(seq.digits)}" for i in range(seq.count)]
                for fr in frames:
                    if fr not in seen:
                        seen.add(fr)
                        names.append(fr)
    for skin in project.data.skins:
        for slot, atts in skin.attachments.items():
            for an, att in atts.items():
                if att.type == "linkedmesh":
                    path = att.path or an
                    if path not in seen:
                        seen.add(path)
                        names.append(path)
    return names


def pack(project: Project, out_dir: str | Path | None = None, name: str | None = None,
         max_size: int = 2048, padding: int = 2, strip: bool = True, pma: bool = True,
         scale: float = 1.0, group: bool = False) -> dict:
    """Pack every referenced image into ``<name>.atlas`` + page PNGs.

    group=True keeps each frame sequence (images that differ only by a trailing number) on as few pages as possible:
    a whole sequence goes onto the first page it fits on, else a page of its own. Mixed packing scatters a sequence
    over every page, and the runtime then switches texture (a new draw call) from frame to frame."""
    out = Path(out_dir) if out_dir else project.root
    out.mkdir(parents=True, exist_ok=True)
    name = name or project.name
    items = []
    missing = []
    meshes = mesh_uv_extent(project) if strip else {}
    for n in referenced_images(project):
        try:
            im = project.image(n)
        except FileNotFoundError:
            missing.append(n)
            continue
        if scale != 1.0:
            im = im.resize((max(1, round(im.width * scale)), max(1, round(im.height * scale))), Image.LANCZOS)
        ow, oh = im.size
        left = top = 0
        if strip:
            bbox = im.getchannel("A").point(lambda a: 255 if a > 0 else 0).getbbox()
            if bbox is None:
                bbox = (0, 0, 1, 1)
            if n in meshes:                       # never crop inside what a mesh samples (+1 px for bilinear)
                ub = meshes[n]
                if ub is None:
                    bbox = (0, 0, ow, oh)
                else:
                    bbox = (max(0, min(bbox[0], math.floor(ub[0] * ow) - 1)), max(0, min(bbox[1], math.floor(ub[1] * oh) - 1)),
                            min(ow, max(bbox[2], math.ceil(ub[2] * ow) + 1)), min(oh, max(bbox[3], math.ceil(ub[3] * oh) + 1)))
            left, top = bbox[0], bbox[1]
            im = im.crop(bbox)
        items.append((n, im, left, top, ow, oh))
    if missing:
        raise FileNotFoundError(f"missing images for: {', '.join(missing)}")
    if not items:
        raise ValueError("the skeleton references no images")
    too_big = [n for n, im, *_ in items if im.width + 2 * padding > max_size or im.height + 2 * padding > max_size]
    if too_big:
        raise ValueError(f"images larger than a {max_size}px page: {too_big}")

    items.sort(key=lambda t: (-max(t[1].size), -t[1].width * t[1].height))
    pages: list[_MaxRects] = []
    placed: list[Placed] = []

    def put(item, pi=None):
        n, im, left, top, ow, oh = item
        w, h = im.width + padding, im.height + padding
        pos = None
        for k in ([pi] if pi is not None else range(len(pages))):
            pos = pages[k].insert(w, h)
            if pos:
                pi = k
                break
        if pos is None:
            pages.append(_MaxRects(max_size - padding, max_size - padding))
            pi = len(pages) - 1
            pos = pages[pi].insert(w, h)
        placed.append(Placed(n, pi, pos[0] + padding, pos[1] + padding, im.width, im.height, left, top, ow, oh))

    if group:
        import copy
        import re
        groups: dict[str, list] = {}
        for it in items:
            groups.setdefault(re.sub(r"_?\d+$", "", it[0]), []).append(it)
        for g in sorted(groups.values(), key=lambda g: -sum(i[1].width * i[1].height for i in g)):
            for k in range(len(pages)):                 # the first page that takes the WHOLE sequence
                trial = copy.deepcopy(pages[k])
                if all(trial.insert(i[1].width + padding, i[1].height + padding) for i in g):
                    for i in g:
                        put(i, k)
                    break
            else:                                       # none: start a fresh page for it (spilling if it must)
                start = len(pages)
                pages.append(_MaxRects(max_size - padding, max_size - padding))
                for i in g:
                    for k in range(start, len(pages)):
                        if copy.deepcopy(pages[k]).insert(i[1].width + padding, i[1].height + padding):
                            put(i, k)
                            break
                    else:
                        pages.append(_MaxRects(max_size - padding, max_size - padding))
                        put(i, len(pages) - 1)
    else:
        for it in items:
            put(it)

    lookup = {it[0]: it[1] for it in items}
    lines: list[str] = []
    page_files = []
    for pi in range(len(pages)):
        regs = [p for p in placed if p.page == pi]
        pw = _pot(max(p.x + p.w for p in regs) + padding)
        ph = _pot(max(p.y + p.h for p in regs) + padding)
        canvas = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
        for p in regs:
            canvas.paste(lookup[p.name], (p.x, p.y))
        if pma:
            a = np.asarray(canvas, np.float32)
            a[..., :3] *= a[..., 3:4] / 255.0
            canvas = Image.fromarray(np.clip(np.round(a), 0, 255).astype(np.uint8), "RGBA")
        fname = f"{name}.png" if len(pages) == 1 else f"{name}_{pi + 1}.png"
        canvas.save(out / fname, optimize=True)
        page_files.append(str(out / fname))
        if lines:
            lines.append("")
        lines += [fname, f"size: {pw},{ph}", "filter: Linear,Linear"]
        if pma:
            lines.append("pma: true")
        for p in regs:
            lines += [p.name, f"bounds: {p.x},{p.y},{p.w},{p.h}"]
            if (p.w, p.h) != (p.orig_w, p.orig_h):
                bottom = p.orig_h - p.top - p.h
                lines.append(f"offsets: {p.left},{bottom},{p.orig_w},{p.orig_h}")
    atlas = out / f"{name}.atlas"
    atlas.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"atlas": str(atlas), "pages": page_files, "regions": len(placed),
            "page_sizes": [Image.open(p).size for p in page_files], "pma": pma, "scale": scale}


def _pot(v: int) -> int:
    """Round page sides up to a multiple of 4 (not power of two: WebGL2 and
    every current runtime handle NPOT, and POT padding wastes memory)."""
    return (v + 3) // 4 * 4


def parse_atlas(path: str | Path) -> dict:
    """Minimal reader: {region: {page, bounds, offsets, rotate}} + page sizes."""
    regions, pages, page = {}, {}, None
    cur = None
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            page, cur = None, None
            continue
        if ":" in line and (cur is not None or page is not None):
            k, v = [s.strip() for s in line.split(":", 1)]
            target = regions[cur] if cur is not None else pages[page]
            target[k] = v
            continue
        if page is None:
            page = line
            pages[page] = {}
        else:
            cur = line
            regions[cur] = {"page": page}
    return {"pages": pages, "regions": regions}
