"""Look at a video clip the way an animator does: contact sheets, a measuring grid, a motion graph that finds the
beats, zoomed strips and onion-skin spacing charts. macOS, no ffmpeg (frames come from AVFoundation via grab.swift,
compiled once into ~/.cache/cliptools/grab).

Run with Pillow + numpy available, e.g.:
    ~/.local/bin/uv run --with pillow --with numpy python cliptools.py <command> ...

Commands (every command prints a JSON line describing what it wrote):
  info    VIDEO                                    duration, size, fps
  sheet   VIDEO OUT [--n 24] [--start S] [--end E] [--crop x0,y0,x1,y1] [--per 8] [--width 360]
                                                    contact sheets, each frame labelled with its time
  grid    VIDEO OUT.png --t T [--step 25] [--units W]
                                                    one frame with a pixel grid (and, with --units, how pixels map to a
                                                    W-unit-wide skeleton whose origin is the frame centre, y up)
  motion  VIDEO OUT.png [--fps 12] [--start S] [--end E]
                                                    change / brightness curves over time, peaks = beats (hits, flashes,
                                                    cuts, holds) with a thumbnail at each
  strip   VIDEO OUT.png --start S --end E [--n 12] [--crop ...]
                                                    consecutive frames side by side at full detail (timing, spacing)
  onion   VIDEO OUT.png --start S --end E [--n 8] [--crop ...]
                                                    frames layered with rising opacity: the spacing chart (even gaps =
                                                    linear, gaps closing = ease out, opening = ease in, overshoot shows)
--crop takes FRACTIONS of the frame (0..1): x0,y0,x1,y1 from the top-left.
"""
from __future__ import annotations

import argparse
import glob
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
CACHE = Path.home() / ".cache" / "cliptools"


def grab_bin() -> str:
    exe = CACHE / "grab"
    src = HERE / "grab.swift"
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        CACHE.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["swiftc", "-O", str(src), "-o", str(exe)], capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("could not compile grab.swift (needs Xcode command line tools):\n" + r.stderr[-1500:])
    return str(exe)


def info(video: str) -> dict:
    r = subprocess.run([grab_bin(), "info", video], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(r.stderr)
    return json.loads(r.stdout)


def frames(video: str, n: int, start: float | None, end: float | None, max_size: int = 960, uniform: bool = False):
    """[(time, PIL.Image)] for n frames between start and end."""
    meta = info(video)
    s = 0.0 if start is None else max(0.0, start)
    e = meta["duration"] if end is None else min(end, meta["duration"])
    d = Path(tempfile.mkdtemp(prefix="clip_"))
    args = [grab_bin(), "frames", video, str(d), str(n), str(s), str(e), str(max_size)] + (["uniform"] if uniform else [])
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(r.stderr)
    out = []
    for f in sorted(glob.glob(str(d / "f*.jpg"))):
        t = float(Path(f).stem.split("_")[1][:-1])
        out.append((t, Image.open(f).convert("RGB")))
    shutil.rmtree(d, ignore_errors=True)
    return out


def font(px: int):
    for f in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"):
        try:
            return ImageFont.truetype(f, px)
        except OSError:
            continue
    return ImageFont.load_default()


def crop(im: Image.Image, c: str | None) -> Image.Image:
    if not c:
        return im
    x0, y0, x1, y1 = (float(v) for v in c.split(","))
    W, H = im.size
    return im.crop((int(x0 * W), int(y0 * H), int(x1 * W), int(y1 * H)))


def label(im: Image.Image, text: str) -> Image.Image:
    d = ImageDraw.Draw(im)
    f = font(max(11, im.width // 22))
    d.rectangle((0, 0, d.textlength(text, font=f) + 8, f.size + 6), fill=(0, 0, 0))
    d.text((4, 2), text, fill=(255, 220, 60), font=f)
    return im


def cmd_sheet(a):
    fr = frames(a.video, a.n, a.start, a.end)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tiles = []
    for t, im in fr:
        im = crop(im, a.crop)
        h = int(a.width * im.height / im.width)
        tiles.append(label(im.resize((a.width, h), Image.LANCZOS), f"{t:.2f}s"))
    sheets = []
    cols = 4
    for k in range(0, len(tiles), a.per):
        grp = tiles[k:k + a.per]
        rows = (len(grp) + cols - 1) // cols
        w, h = grp[0].size
        sh = Image.new("RGB", (w * cols, h * rows), (20, 20, 24))
        for i, t in enumerate(grp):
            sh.paste(t, ((i % cols) * w, (i // cols) * h))
        p = out / f"sheet_{k // a.per:02d}.jpg"
        sh.save(p, quality=88)
        sheets.append(str(p))
    return {"sheets": sheets, "times": [round(t, 3) for t, _ in fr]}


def cmd_grid(a):
    meta = info(a.video)
    (t, im), = frames(a.video, 1, a.t, a.t + 0.04, max_size=4096, uniform=True)
    W, H = im.size
    d = ImageDraw.Draw(im)
    f = font(max(10, W // 70))
    for x in range(0, W, a.step):
        major = x % (a.step * 4) == 0
        d.line((x, 0, x, H), fill=(255, 40, 40) if major else (120, 20, 20), width=1)
        if major:
            d.text((x + 2, 2), str(x), fill=(255, 255, 255), font=f)
    for y in range(0, H, a.step):
        major = y % (a.step * 4) == 0
        d.line((0, y, W, y), fill=(40, 255, 40) if major else (20, 110, 20), width=1)
        if major:
            d.text((2, y + 2), str(y), fill=(255, 255, 255), font=f)
    im.save(a.out)
    res = {"grid": a.out, "time": t, "frame_px": [W, H], "source_px": [meta["width"], meta["height"]]}
    if a.units:
        k = a.units / W
        res["to_units"] = {"scale": k, "x": f"(px - {W / 2}) * {k:.5f}", "y": f"({H / 2} - py) * {k:.5f}",
                           "screen_units": [round(W * k, 1), round(H * k, 1)]}
    return res


def cmd_motion(a):
    meta = info(a.video)
    s = a.start or 0.0
    e = a.end or meta["duration"]
    n = max(8, int((e - s) * a.fps))
    fr = frames(a.video, n, s, e, max_size=200, uniform=True)
    ts = np.array([t for t, _ in fr])
    arr = [np.asarray(im, np.float32) / 255 for _, im in fr]
    bright = np.array([x.mean() for x in arr])
    change = np.array([0.0] + [np.abs(arr[i] - arr[i - 1]).mean() for i in range(1, len(arr))])

    def peaks(v, k=1.6):
        thr = np.median(v) + k * (np.percentile(v, 90) - np.median(v) + 1e-6)
        idx = [i for i in range(1, len(v) - 1) if v[i] >= thr and v[i] >= v[i - 1] and v[i] >= v[i + 1]]
        keep = []
        for i in sorted(idx, key=lambda i: -v[i]):           # at least 0.25 s apart
            if all(abs(ts[i] - ts[j]) > 0.25 for j in keep):
                keep.append(i)
        return sorted(keep)
    cp, bp = peaks(change), peaks(bright - np.convolve(bright, np.ones(9) / 9, "same"), 2.0)
    cuts = [i for i in cp if change[i] > 0.18]
    holds, run = [], []
    for i, c in enumerate(change):
        if c < np.percentile(change, 15) * 1.2:
            run.append(i)
        else:
            if len(run) >= int(0.5 * a.fps):
                holds.append([round(ts[run[0]], 2), round(ts[run[-1]], 2)])
            run = []
    if len(run) >= int(0.5 * a.fps):
        holds.append([round(ts[run[0]], 2), round(ts[run[-1]], 2)])
    # chart: two curves + thumbnails at the change peaks
    Wc, Hc, th = 1400, 300, 150
    marks = sorted(set(cp) | set(bp))[:14]
    img = Image.new("RGB", (Wc, Hc + th + 30), (18, 18, 22))
    d = ImageDraw.Draw(img)
    f = font(13)
    X = lambda t: 40 + (t - s) / max(e - s, 1e-6) * (Wc - 60)  # noqa: E731

    def curve(v, col):
        v = (v - v.min()) / (np.ptp(v) + 1e-9)
        d.line([(X(t), Hc - 20 - y * (Hc - 50)) for t, y in zip(ts, v)], fill=col, width=2)
    for sec in range(int(s), int(e) + 1):
        d.line((X(sec), 10, X(sec), Hc - 20), fill=(50, 50, 60))
        d.text((X(sec) + 2, Hc - 18), f"{sec}s", fill=(160, 160, 170), font=f)
    curve(change, (255, 170, 40))
    curve(bright, (90, 180, 255))
    d.text((44, 8), "change (orange): motion / hits / cuts    brightness (blue): flashes / fades", fill=(220, 220, 220), font=f)
    for i in marks:
        d.line((X(ts[i]), 10, X(ts[i]), Hc - 20), fill=(255, 80, 80) if i in cuts else (255, 255, 255))
    if marks:
        tw = min(th, (Wc - 20) // len(marks))
        for k, i in enumerate(marks):
            im = fr[i][1].copy()
            im.thumbnail((tw - 4, th))
            img.paste(im, (10 + k * tw, Hc + 4))
            d.text((10 + k * tw, Hc + th + 8), f"{ts[i]:.2f}s", fill=(255, 220, 60), font=f)
    img.save(a.out)
    return {"chart": a.out, "change_peaks": [round(ts[i], 2) for i in cp], "flash_peaks": [round(ts[i], 2) for i in bp],
            "cuts": [round(ts[i], 2) for i in cuts], "holds": holds, "samples": len(ts), "fps": a.fps}


def cmd_strip(a):
    fr = frames(a.video, a.n, a.start, a.end, uniform=True)
    tiles = [label(crop(im, a.crop), f"{t:.3f}s") for t, im in fr]
    h = 300
    tiles = [t.resize((int(t.width * h / t.height), h), Image.LANCZOS) for t in tiles]
    cols = min(6, len(tiles))
    rows = (len(tiles) + cols - 1) // cols
    w = max(t.width for t in tiles)
    sh = Image.new("RGB", (w * cols, h * rows), (20, 20, 24))
    for i, t in enumerate(tiles):
        sh.paste(t, ((i % cols) * w, (i // cols) * h))
    sh.save(a.out)
    return {"strip": a.out, "times": [round(t, 3) for t, _ in fr], "step_s": round((a.end - a.start) / max(a.n - 1, 1), 4)}


def cmd_onion(a):
    fr = frames(a.video, a.n, a.start, a.end, uniform=True)
    ims = [np.asarray(crop(im, a.crop), np.float32) for _, im in fr]
    bg = np.median(np.stack(ims), axis=0)                      # what stays put
    grey = bg.mean(axis=2, keepdims=True) * 0.3
    acc = np.repeat(grey, 3, axis=2)
    n = len(ims)
    for k, im in enumerate(ims):                               # early frames blue, late frames red, later on top
        moved = (np.abs(im - bg).max(axis=2, keepdims=True) > 40).astype(np.float32)
        u = k / max(n - 1, 1)
        tint = np.array([60 + 195 * u, 90, 255 - 195 * u], np.float32)
        ghost = im * 0.55 + tint * 0.45
        acc = acc * (1 - moved * 0.7) + ghost * moved * 0.7
    out = Image.fromarray(np.clip(acc, 0, 255).astype(np.uint8))
    out = label(out, f"{a.start:.2f}-{a.end:.2f}s, {n} frames: blue = early, red = late")
    out.save(a.out)
    return {"onion": a.out, "times": [round(t, 3) for t, _ in fr],
            "read": "even gaps = linear; gaps shrinking toward red = ease out; growing = ease in; red past blue then back = overshoot"}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("info"); s.add_argument("video")
    s = sub.add_parser("sheet"); s.add_argument("video"); s.add_argument("out")
    s.add_argument("--n", type=int, default=24); s.add_argument("--start", type=float); s.add_argument("--end", type=float)
    s.add_argument("--crop"); s.add_argument("--per", type=int, default=8); s.add_argument("--width", type=int, default=360)
    s = sub.add_parser("grid"); s.add_argument("video"); s.add_argument("out"); s.add_argument("--t", type=float, required=True)
    s.add_argument("--step", type=int, default=25); s.add_argument("--units", type=float)
    s = sub.add_parser("motion"); s.add_argument("video"); s.add_argument("out"); s.add_argument("--fps", type=float, default=12)
    s.add_argument("--start", type=float); s.add_argument("--end", type=float)
    for name in ("strip", "onion"):
        s = sub.add_parser(name); s.add_argument("video"); s.add_argument("out")
        s.add_argument("--start", type=float, required=True); s.add_argument("--end", type=float, required=True)
        s.add_argument("--n", type=int, default=12 if name == "strip" else 8); s.add_argument("--crop")
    a = p.parse_args(argv)
    if a.cmd == "info":
        res = info(a.video)
    else:
        res = {"sheet": cmd_sheet, "grid": cmd_grid, "motion": cmd_motion, "strip": cmd_strip, "onion": cmd_onion}[a.cmd](a)
    print(json.dumps(res))


if __name__ == "__main__":
    main()
