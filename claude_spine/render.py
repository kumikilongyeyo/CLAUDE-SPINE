"""Software renderer for posed geometry from the spine-core runtime.

Draws textured triangles with PIL affine transforms (C speed), composites them
in premultiplied space with the slot's blend mode, and writes PNG frames, a
contact sheet or a GIF. It is a preview, not the game renderer: no MSAA. It
does two-colour tint (a slot's dark colour) the way spine-webgl does. It is
exact about *where* things are, which is what review needs.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


class _Pages:
    def __init__(self, files: dict[str, str], pma: bool):
        self.img: dict[str, Image.Image] = {}
        for name, f in files.items():
            im = Image.open(f).convert("RGBA")
            if not pma:  # work premultiplied
                a = np.asarray(im, np.float32)
                a[..., :3] *= a[..., 3:4] / 255
                im = Image.fromarray(np.round(a).astype(np.uint8), "RGBA")
            self.img[name] = im
        self.arr = {k: np.asarray(v, np.float32) / 255 for k, v in self.img.items()}


def _rasterize(scr: np.ndarray, uv: np.ndarray, tri: np.ndarray, page: np.ndarray, W: int, H: int):
    """Texture-map one attachment's triangles. Returns (y0, x0, rgba patch) in
    premultiplied float, or None when off-screen.

    PIL draws a triangle-id map (C speed); numpy then maps every covered pixel
    through its triangle's screen→uv affine and samples the page bilinearly.
    """
    x0, y0 = np.floor(scr.min(0)).astype(int) - 1
    x1, y1 = np.ceil(scr.max(0)).astype(int) + 1
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    if x1 <= x0 or y1 <= y0:
        return None
    pw, ph = x1 - x0, y1 - y0
    ids = Image.new("I", (pw, ph), 0)
    dr = ImageDraw.Draw(ids)
    loc = scr - [x0, y0]
    for k, t in enumerate(tri):
        dr.polygon([tuple(loc[i]) for i in t], fill=k + 1, outline=k + 1)
    idm = np.asarray(ids, np.int64) - 1
    ys, xs = np.nonzero(idm >= 0)
    if len(xs) == 0:
        return None
    # per-triangle affine: [x, y, 1] @ C -> (u, v)
    M = np.concatenate([loc[tri], np.ones((len(tri), 3, 1))], axis=2)
    det = np.linalg.det(M)
    ok = np.abs(det) > 1e-9
    C = np.zeros((len(tri), 3, 2))
    C[ok] = np.linalg.solve(M[ok], uv[tri][ok])
    k = idm[ys, xs]
    keep = ok[k]
    ys, xs, k = ys[keep], xs[keep], k[keep]
    px = np.c_[xs + 0.5, ys + 0.5, np.ones(len(xs))]
    u = (px[:, None, :] @ C[k])[:, 0, :]
    # outline pixels sit partly outside their triangle and extrapolate: keep every sample inside the triangle's own
    # UV box, or a minified texture reads past the atlas padding into the neighbouring image (a faint edge line)
    tuv = uv[tri]
    u = np.clip(u, tuv.min(1)[k], tuv.max(1)[k])
    PH, PW = page.shape[:2]
    fx = np.clip(u[:, 0] - 0.5, 0, PW - 1)
    fy = np.clip(u[:, 1] - 0.5, 0, PH - 1)
    ix, iy = np.floor(fx).astype(int), np.floor(fy).astype(int)
    ix1, iy1 = np.minimum(ix + 1, PW - 1), np.minimum(iy + 1, PH - 1)
    ax, ay = (fx - ix)[:, None], (fy - iy)[:, None]
    col = (page[iy, ix] * (1 - ax) * (1 - ay) + page[iy, ix1] * ax * (1 - ay)
           + page[iy1, ix] * (1 - ax) * ay + page[iy1, ix1] * ax * ay)
    patch = np.zeros((ph, pw, 4), np.float32)
    patch[ys, xs] = col
    return y0, x0, patch


def render_frame(draws: list[dict], pages: _Pages, view: tuple[float, float, float, float],
                 size: tuple[int, int], background=(0, 0, 0, 0), wire: bool = False) -> Image.Image:
    """view = (minX, minY, maxX, maxY) in skeleton units (y up)."""
    W, H = size
    x0, y0, x1, y1 = view
    s = min(W / max(x1 - x0, 1e-6), H / max(y1 - y0, 1e-6))
    ox = (W - (x1 - x0) * s) / 2
    oy = (H - (y1 - y0) * s) / 2
    acc = np.zeros((H, W, 4), np.float32)
    bg = np.array(background, np.float32) / 255
    if bg[3] > 0:
        acc[:] = np.r_[bg[:3] * bg[3], bg[3]]
    lines = []
    for d in draws:
        page = pages.arr.get(d["page"])
        if page is None:
            continue
        PH, PW = page.shape[:2]
        v = np.asarray(d["v"], float).reshape(-1, 2)
        scr = np.c_[(v[:, 0] - x0) * s + ox, H - ((v[:, 1] - y0) * s + oy)]
        uv = np.asarray(d["uv"], float).reshape(-1, 2) * [PW, PH]
        tri = np.asarray(d["tri"], int).reshape(-1, 3)
        res = _rasterize(scr, uv, tri, page, W, H)
        if wire:
            lines += [[tuple(scr[i]) for i in t] for t in tri]
        if res is None:
            continue
        py, px, layer = res
        col = np.array(d["color"], np.float32)
        if d.get("dark") is not None:
            # two-colour tint (spine-webgl, premultiplied): rgb = (a - t) * dark + t * light, both times slot alpha
            dk = np.array(d["dark"], np.float32)
            ta = layer[..., 3:4]
            layer[..., :3] = ((ta - layer[..., :3]) * dk + layer[..., :3] * col[:3]) * col[3]
            layer[..., 3:4] = ta * col[3]
        else:
            layer *= np.r_[col[:3] * col[3], col[3]]
        dst = acc[py:py + layer.shape[0], px:px + layer.shape[1]]
        blend = d.get("blend", "normal")
        la = layer[..., 3:4]
        if blend == "additive":
            # PMA additive: src ONE, dst ONE_MINUS_SRC_ALPHA with src alpha 0
            dst[..., :3] += layer[..., :3]
        elif blend == "multiply":
            dst[..., :3] = layer[..., :3] * dst[..., :3] + dst[..., :3] * (1 - la)
        elif blend == "screen":
            dst[..., :3] = dst[..., :3] + layer[..., :3] - dst[..., :3] * layer[..., :3]
            dst[..., 3:4] = la + dst[..., 3:4] * (1 - la)
        else:
            dst[:] = layer + dst * (1 - la)
    acc = np.clip(acc, 0, 1)
    a = acc[..., 3:4]
    rgb = np.divide(acc[..., :3], a, out=np.zeros_like(acc[..., :3]), where=a > 1e-6)
    out = Image.fromarray(np.round(np.concatenate([rgb, a], 2) * 255).astype(np.uint8), "RGBA")
    if wire and lines:
        dr = ImageDraw.Draw(out)
        for L in lines:
            dr.polygon(L, outline=(0, 255, 255, 140))
    return out


def union_bounds(dump: dict, anims: list[str] | None = None, pad: float = 0.06):
    bs = [dump["setup"]["bounds"]]
    for n, a in dump["animations"].items():
        if anims is None or n in anims:
            bs.append(a["bounds"])
    # nothing drawn (an FX-only skeleton's setup pose) dumps Infinity bounds, which JSON turns into null
    bs = [b for b in bs if b is not None and all(v is not None and np.isfinite(v) for v in b)]
    if not bs:
        return (-100, -100, 100, 100)
    b = np.array(bs)
    x0, y0, x1, y1 = b[:, 0].min(), b[:, 1].min(), b[:, 2].max(), b[:, 3].max()
    px, py = (x1 - x0) * pad, (y1 - y0) * pad
    return (x0 - px, y0 - py, x1 + px, y1 + py)


def render_animation(dump: dict, anim: str, out_dir: str | Path, size: int = 360, gif: bool = True,
                     sheet: bool = True, background=(40, 40, 46, 255), wire: bool = False) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pages = _Pages(dump["_page_files"], dump.get("_pma", False))
    view = union_bounds(dump, [anim])
    vw, vh = view[2] - view[0], view[3] - view[1]
    W = size if vw >= vh else max(16, int(size * vw / vh))
    H = size if vh >= vw else max(16, int(size * vh / vw))
    frames = [render_frame(f["draws"], pages, view, (W, H), background, wire) for f in dump["animations"][anim]["frames"]]
    res: dict = {"frames": len(frames)}
    safe = anim.replace("/", "_").replace(" ", "_")
    if gif and frames:
        dur = dump["animations"][anim]["duration"]
        step_ms = max(20, int(round(1000 * dur / max(len(frames) - 1, 1) / 10)) * 10)  # GIF stores centiseconds
        p = out / f"{safe}.gif"
        rgb = [f.convert("RGB") for f in frames]
        rgb[0].save(p, save_all=True, append_images=rgb[1:], duration=step_ms, loop=0, disposal=2)
        res["gif"] = str(p)
    if sheet and frames:
        k = min(len(frames), 8)
        idx = np.linspace(0, len(frames) - 1, k).round().astype(int)
        cs = Image.new("RGBA", (W * k, H), background)
        for i, j in enumerate(idx):
            cs.alpha_composite(frames[j], (i * W, 0))
        p = out / f"{safe}_sheet.png"
        cs.save(p)
        res["sheet"] = str(p)
    return res


def render_setup(dump: dict, out_png: str | Path, size: int = 480, background=(40, 40, 46, 255), wire: bool = False) -> str:
    pages = _Pages(dump["_page_files"], dump.get("_pma", False))
    view = union_bounds(dump, [])
    img = render_frame(dump["setup"]["draws"], pages, view, (size, size), background, wire)
    img.save(out_png)
    return str(out_png)
