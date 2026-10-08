"""Reference-footage FX memory for the existing AE/Spine VFX director.

Analyzes an isolated PNG sequence or a video (ffmpeg optional), stores a compact
editable motion recipe and generates a native, layered After Effects JSX rebuild.
It does not claim to recover hidden source effects from flattened pixels.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import ae_look

FORM = "claude-spine.fx-reference.v1"
EXTENSIONS = {".png", ".tif", ".tiff", ".jpg", ".jpeg"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}


def _slug(name: str) -> str:
    value = re.sub(r"[^a-z0-9_-]+", "_", name.lower().strip()).strip("_")
    if not value:
        raise ValueError("FX name must contain letters or digits")
    return value[:72]


def _clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, float(x)))


def _frames(source: Path, fps: float, limit: int, folder: Path):
    if source.is_dir():
        paths = sorted(p for p in source.iterdir() if p.suffix.lower() in EXTENSIONS)
        if len(paths) < 3:
            raise ValueError("Need at least 3 PNG/TIFF/JPEG frames")
        if fps <= 0:
            raise ValueError("Image sequences need fps > 0")
        if len(paths) > limit:
            ix = np.linspace(0, len(paths) - 1, limit).round().astype(int)
            selected = [paths[int(i)] for i in ix]
            times = [int(i) / fps for i in ix]
        else:
            selected, times = paths, [i / fps for i in range(len(paths))]
        return selected, times, fps
    if not source.is_file() or source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError("source must be a video or a directory of image frames")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("Install ffmpeg to analyze video, or supply an extracted PNG sequence")
    seconds = 0.0
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        p = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
            capture_output=True, text=True, timeout=15, check=False)
        try:
            seconds = max(0.0, float(p.stdout.strip()))
        except ValueError:
            pass
    # Cover the whole clip, rather than truncating after the first N frames.
    chosen_fps = min(fps if fps > 0 else 24.0, limit / seconds) if seconds else min(fps or 12.0, 30.0)
    chosen_fps = max(0.25, chosen_fps)
    subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(source),
         "-vf", f"fps={chosen_fps:.7f},scale=256:256:force_original_aspect_ratio=decrease",
         "-frames:v", str(limit), "-pix_fmt", "rgba", str(folder / "f_%06d.png")],
        check=True, timeout=180)
    paths = sorted(folder.glob("f_*.png"))
    if len(paths) < 3:
        raise ValueError("No usable frames extracted from the video")
    return paths, [i / chosen_fps for i in range(len(paths))], chosen_fps


def _array(path: Path, max_edge: int = 256) -> np.ndarray:
    with Image.open(path) as src:
        im = src.convert("RGBA")
        if max(im.size) > max_edge:
            k = max_edge / max(im.size)
            im = im.resize((round(im.width * k), round(im.height * k)), Image.Resampling.BILINEAR)
        return np.asarray(im, dtype=np.float32) / 255.0


def _mask(arr: np.ndarray, method: str, background: np.ndarray | None) -> np.ndarray:
    rgb = arr[..., :3]
    if method == "alpha":
        return arr[..., 3]
    if method == "black":
        return np.clip((rgb.max(axis=2) - 0.035) / 0.22, 0, 1)
    if method == "green":
        g = rgb[..., 1]
        return np.clip((np.maximum(rgb[..., 0], rgb[..., 2]) - g * 0.45 + 0.03) / 0.4, 0, 1)
    if method == "background":
        if background is None:
            raise ValueError("background image required for mask_mode=background")
        if background.shape != arr.shape:
            raise ValueError("Background image size must match analyzed footage")
        return np.clip(np.abs(rgb - background[..., :3]).max(axis=2) / 0.25, 0, 1)
    # none: cannot isolate effects; uses frame luminance as an imperfect proxy.
    return np.ones(arr.shape[:2], dtype=np.float32)


def _mode(first: np.ndarray, mode: str, background: np.ndarray | None) -> str:
    if mode not in ("auto", "alpha", "black", "green", "background", "none"):
        raise ValueError("mask_mode must be auto|alpha|black|green|background|none")
    if mode != "auto":
        return mode
    if first[..., 3].min() < 0.98:
        return "alpha"
    if background is not None:
        return "background"
    rgb = first[..., :3]
    corners = np.concatenate([rgb[:12, :12].reshape(-1, 3),
                              rgb[-12:, -12:].reshape(-1, 3)])
    return "black" if float(corners.max(axis=1).mean()) < 0.12 else "none"


def _measurement(a: np.ndarray, mode: str, background: np.ndarray | None) -> dict:
    rgb = a[..., :3]
    mask = _mask(a, mode, background)
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)
    signal = lum * mask
    h, w = signal.shape
    yy, xx = np.indices((h, w), dtype=np.float32)
    mass = float(signal.sum())
    if mass < 1e-4:
        return {"energy": 0., "heat": 0., "coverage": 0., "x": 0.5, "y": 0.5,
                "radius": 0.02, "color": [1., 1., 1.]}
    x = float((xx * signal).sum() / mass) / max(1, w - 1)
    y = float((yy * signal).sum() / mass) / max(1, h - 1)
    r = float(np.sqrt((((xx / w - x) ** 2 + (yy / h - y) ** 2) * signal).sum() / mass))
    chroma = (rgb * signal[..., None]).sum(axis=(0, 1)) / max(mass, 1e-4)
    chroma /= max(float(chroma.max()), 0.01)
    return {"energy": round(mass / (w * h), 6),
            "heat": round(float(((lum > 0.85) * (mask > 0.25)).mean()), 6),
            "coverage": round(float((mask > 0.25).mean()), 6),
            "x": round(_clamp(x), 5), "y": round(_clamp(y), 5),
            "radius": round(_clamp(r, 0.02, 0.8), 5),
            "color": [round(float(v), 4) for v in chroma]}


def _compact(samples: list[dict], must: set[int], tolerance: float = 0.038) -> list[int]:
    """Multichannel adaptive reduction; preserves beat extrema and authored timing."""
    n = len(samples)
    channels = ("energy", "radius", "x", "y", "heat")
    values = np.asarray([[s[k] for k in channels] for s in samples], float)
    scale = np.ptp(values, axis=0)
    scale = np.maximum(scale, [0.01, 0.05, 0.05, 0.05, 0.01])
    values = values / scale
    anchors = sorted({0, n - 1} | {i for i in must if 0 <= i < n})
    chosen = set(anchors)

    def segment(lo: int, hi: int):
        if hi - lo < 2:
            return
        left, right = samples[lo]["time"], samples[hi]["time"]
        delta = max(right - left, 1e-6)
        residual = []
        for j in range(lo + 1, hi):
            t = (samples[j]["time"] - left) / delta
            predicted = values[lo] * (1 - t) + values[hi] * t
            residual.append(float(np.max(np.abs(values[j] - predicted))))
        worst = int(np.argmax(residual))
        if residual[worst] > tolerance:
            mid = lo + 1 + worst
            chosen.add(mid)
            segment(lo, mid)
            segment(mid, hi)

    for i, j in zip(anchors, anchors[1:]):
        segment(i, j)
    # Keep the recipe bounded; beat anchors always survive.
    if len(chosen) > 44:
        remaining = sorted(chosen - set(anchors))
        stride = max(1, math.ceil(len(remaining) / max(1, 44 - len(anchors))))
        chosen = set(anchors) | set(remaining[::stride])
    return sorted(chosen)


def capture(source: str, library_dir: str, name: str, fps: float = 24.0,
            mask_mode: str = "auto", background: str = "", max_frames: int = 96) -> dict:
    """Capture the VFX motion signature into a versioned, reusable JSON recipe.

    PNG/TIFF/JPEG sequence directories need fps. Videos need ffmpeg. For composite
    footage use background=clean_plate.png or supply an already isolated render.
    """
    src = Path(source).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(str(src))
    if max_frames < 8 or max_frames > 240:
        raise ValueError("max_frames must be 8..240")
    if not library_dir:
        raise ValueError("library_dir is required for persistent recipes")
    slug = _slug(name)
    target = Path(library_dir).expanduser().resolve() / slug
    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ae_fx_capture_") as tmp:
        paths, times, effective_fps = _frames(src, fps, max_frames, Path(tmp))
        first = _array(paths[0])
        bg = _array(Path(background).expanduser().resolve()) if background else None
        method = _mode(first, mask_mode, bg)
        frames = []
        size = [int(first.shape[1]), int(first.shape[0])]
        for path, seconds in zip(paths, times):
            arr = _array(path)
            if arr.shape != first.shape:
                raise ValueError("Frames must share dimensions; export a fixed-size sequence")
            frames.append({"time": round(seconds, 5), **_measurement(arr, method, bg)})
        raw_energies = [f["energy"] for f in frames]
        if max(raw_energies) < 0.00001:
            raise ValueError("No FX signal found; check mask_mode / input footage")
        peak = max(raw_energies)
        norm = [e / peak for e in raw_energies]
        beats = ae_look.find_beats(norm, [f["heat"] for f in frames])
        key_positions = set(beats["beats"].values()) | {beats["peak"],
                         int(np.argmax([f["radius"] for f in frames])),
                         int(np.argmax([f["heat"] for f in frames]))}
        compacted = _compact(frames, key_positions)
        duration = max(1 / effective_fps, times[-1])
        main = frames[beats["peak"]]
        light = np.array([f["color"] for f in frames])
        weights = np.asarray(raw_energies) + 1e-6
        avg = (light * weights[:, None]).sum(axis=0) / sum(weights)
        avg = avg / max(avg.max(), 1e-6)
        speed = math.dist((frames[beats["lo"]]["x"], frames[beats["lo"]]["y"]),
                          (frames[beats["hi"]]["x"], frames[beats["hi"]]["y"]))
        family = {"hit": "impact", "build": "magic_reveal", "loop": "ambient"}[beats["kind"]]
        signature = hashlib.sha256(json.dumps(frames, sort_keys=True).encode()).hexdigest()[:16]
        warnings = []
        if method == "none":
            warnings.append("Background not isolated; energy/color/motion may include scene content. Supply alpha or a clean background plate.")
        if method == "black":
            warnings.append("Black-key analysis may discard dark smoke and shadows.")
        preset = {
            "schema": FORM, "name": name, "id": slug, "signature": signature,
            "source": {"path": str(src), "type": "video" if src.is_file() else "sequence",
                       "mask_mode": method, "sampled_frames": len(frames),
                       "sample_fps": round(effective_fps, 5), "preview_size": size},
            "analysis": {"kind": beats["kind"], "suggested_event": family,
                         "duration": round(duration, 5),
                         "beats": {k: round(times[v], 5) for k, v in beats["beats"].items()},
                         "peak_at": round(times[beats["peak"]], 5),
                         "direction": [round(frames[beats["hi"]]["x"] - frames[beats["lo"]]["x"], 4),
                                       round(frames[beats["hi"]]["y"] - frames[beats["lo"]]["y"], 4)],
                         "travel": round(speed, 4),
                         "coverage_peak": main["coverage"],
                         "color": [round(float(v), 4) for v in avg],
                         "peak_energy": round(peak, 6)},
            "keys": [{"t": round(frames[i]["time"] / duration, 6),
                      "energy": round(norm[i], 5), "radius": frames[i]["radius"],
                      "x": frames[i]["x"], "y": frames[i]["y"], "heat": frames[i]["heat"]}
                     for i in compacted],
            "warnings": warnings,
            "limitations": "Reverse engineered timing, color, size and motion; source particle emitters, depth and effect-stack parameters cannot be recovered reliably from flattened footage.",
        }
        dest = target / "recipe.json"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=target,
                                         prefix=".capture-", suffix=".json", delete=False) as handle:
            json.dump(preset, handle, indent=2)
            staged = Path(handle.name)
        staged.replace(dest)
        # Keep a small visual reference even if the original footage later moves.
        im = Image.new("RGB", (size[0] * 4, size[1]), (20, 20, 24))
        chosen = list(beats["beats"].values())[:4]
        for pos, i in enumerate(chosen):
            with Image.open(paths[i]) as fr:
                im.paste(fr.convert("RGB").resize(tuple(size), Image.Resampling.BILINEAR),
                         (pos * size[0], 0))
        sheet = target / "reference.jpg"
        im.save(sheet, quality=88)
    return {"recipe": str(dest), "reference": str(sheet), "event": family,
            "beats": preset["analysis"]["beats"], "keys": len(preset["keys"]),
            "mask_mode": method, "warnings": warnings,
            "next": "ae_fx_remix recipe=<recipe path> out_dir=<output folder> strength=1.8 style=anime"}


def _hex_color(color: str, fallback: list[float]) -> list[float]:
    if not color:
        return fallback
    raw = color.lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", raw):
        raise ValueError("color must be a 6-digit hex code like #FF6633")
    return [int(raw[i:i+2], 16) / 255.0 for i in (0, 2, 4)]


def _js(value) -> str:
    return json.dumps(value, ensure_ascii=True)


def remix(recipe: str, out_dir: str, strength: float = 1.0, style: str = "premium",
          color: str = "", speed: float = 1.0, spark_count: int = -1,
          comp_name: str = "", save_as: str = "", canvas: int = 1024) -> dict:
    """Write editable JSX. Run via AE MCP ae_run_script or File > Scripts > Run Script File.

    A .jsx builds a reusable multi-layer composition; it is NOT a .ffx preset.
    """
    if style not in ("stylized", "premium", "realistic", "anime"):
        raise ValueError("style must be stylized|premium|realistic|anime")
    if not 0.25 <= strength <= 3.0 or not 0.25 <= speed <= 4.0:
        raise ValueError("strength must be 0.25..3; speed must be 0.25..4")
    obj = json.loads(Path(recipe).expanduser().read_text(encoding="utf-8"))
    if obj.get("schema") != FORM:
        raise ValueError("Not an AE reference recipe of the current schema")
    if not obj.get("keys") or not obj.get("analysis"):
        raise ValueError("Malformed FX reference recipe")
    if not out_dir:
        raise ValueError("out_dir is required")
    if canvas < 128 or canvas > 4096:
        raise ValueError("canvas must be 128..4096")
    path = Path(out_dir).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    name = _slug(comp_name or (obj["id"] + "_" + style))
    duration = max(0.1, float(obj["analysis"]["duration"]) / speed)
    sample_fps = float(obj["source"]["sample_fps"])
    fps = min(60, max(12, round(sample_fps)))
    w, h = obj["source"]["preview_size"]
    factor = canvas / max(w, h)
    w, h = max(32, round(w * factor)), max(32, round(h * factor))
    col = _hex_color(color, obj["analysis"]["color"])
    keys = obj["keys"]
    time_keys = [round(_clamp(float(k["t"])) * duration, 5) for k in keys]
    e = [_clamp(float(k["energy"])) for k in keys]
    x = [round(_clamp(k["x"]) * w, 3) for k in keys]
    y = [round(_clamp(k["y"]) * h, 3) for k in keys]
    radius = [round(_clamp(k["radius"], .02, .8) * min(w, h) * (1 + (strength - 1) * .23), 3) for k in keys]
    peak_at = float(obj["analysis"]["peak_at"]) / speed
    high = 1.0 if style in ("anime", "stylized") else 0.8
    particles = (14 if style == "anime" else 10 if style == "premium" else 7 if style == "stylized" else 5)
    particles = round(particles * strength) if spark_count < 0 else spark_count
    particles = max(0, min(80, particles))
    radius_max = max(radius)
    # Native AE shapes + sparse Bezier keys. Controls remain live after generation.
    script = r"""(function(){
    app.beginUndoGroup("Rebuild reference FX");
    try {
        if (!app.project) app.newProject();
        var comp = app.project.items.addComp(__COMP__, __W__, __H__, 1, __DURATION__, __FPS__);
        comp.bgColor = [0.02, 0.02, 0.025];
        var ctrl = comp.layers.addNull();
        ctrl.name = "00_FX_CONTROLS"; ctrl.guideLayer = true;
        function slider(name, value) {
            var e = ctrl.property("ADBE Effect Parade").addProperty("ADBE Slider Control");
            e.name = name; e.property(1).setValue(value); return e;
        }
        slider("Impact Strength", 100); slider("Global Scale", 100);
        var force = 'thisComp.layer("00_FX_CONTROLS").effect("Impact Strength")("Slider")/100';
        var zoom = 'thisComp.layer("00_FX_CONTROLS").effect("Global Scale")("Slider")/100';
        function keys(p, t, values) {
            for (var i = 0; i < t.length; ++i) p.setValueAtTime(t[i], values[i]);
            for (var i = 1; i <= p.numKeys; ++i)
                p.setInterpolationTypeAtKey(i, KeyframeInterpolationType.BEZIER, KeyframeInterpolationType.BEZIER);
        }
        function disk(name, rgb, outline) {
            var layer = comp.layers.addShape(); layer.name = name;
            var g = layer.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group");
            var v = g.property("ADBE Vectors Group");
            var circle = v.addProperty("ADBE Vector Shape - Ellipse");
            circle.property("ADBE Vector Ellipse Size").setValue([100,100]);
            if (outline) {
                var stroke = v.addProperty("ADBE Vector Graphic - Stroke");
                stroke.property("ADBE Vector Stroke Color").setValue(rgb);
                stroke.property("ADBE Vector Stroke Width").setValue(outline);
            } else {
                var fill = v.addProperty("ADBE Vector Graphic - Fill");
                fill.property("ADBE Vector Fill Color").setValue(rgb);
            }
            return layer;
        }
        function track(layer, t, opacity, pos, scale) {
            var tr = layer.property("ADBE Transform Group");
            keys(tr.property("ADBE Opacity"), t, opacity);
            keys(tr.property("ADBE Position"), t, pos);
            keys(tr.property("ADBE Scale"), t, scale);
            tr.property("ADBE Opacity").expression = 'Math.min(100, value * (' + force + '))';
            tr.property("ADBE Scale").expression = 'value * (' + zoom + ')';
            return layer;
        }
        var t = __TIMES__, energy = __ENERGY__, xx = __X__, yy = __Y__, rr = __RADII__;
        var positions = [], coreScale = [], haloScale = [], ringScale = [];
        var coreOpacity = [], haloOpacity = [], ringOpacity = [];
        for(var i = 0; i < t.length; i++) {
            positions.push([xx[i], yy[i]]);
            var diameter = Math.max(2, rr[i]*2);
            coreScale.push([diameter*.55,diameter*.55]);
            haloScale.push([diameter*1.55,diameter*1.55]);
            ringScale.push([diameter*1.24,diameter*1.24]);
            coreOpacity.push(Math.min(100, energy[i]*__CORE_GAIN__*100));
            haloOpacity.push(Math.min(80, Math.sqrt(energy[i])*25));
            ringOpacity.push(Math.min(75, energy[i]*65));
        }
        // The base ellipse is 100 px wide, so scale == desired diameter.
        track(disk("02_CORE_reference_energy", [1,1,1], 0),
              t, coreOpacity, positions, coreScale);
        track(disk("05_LIGHTING_soft_halo", __RGB__, 0),
              t, haloOpacity, positions, haloScale);
        track(disk("04_DISTORTION_rebuild_ring", __RGB__, 3),
              t, ringOpacity, positions, ringScale);
        var hit = __PEAK__, count = __COUNT__, burst = __BURST__;
        var cx = xx[0], cy = yy[0], top = 0;
        for(var i=0;i<energy.length;i++) if(energy[i]>=top) { top=energy[i];cx=xx[i];cy=yy[i]; }
        function seedRandom(i) { var n=Math.sin(i*127.1 + __SEED__*311.7)*43758.5453; return n-Math.floor(n); }
        for(var i=0;i<count;i++) {
            var angle = 2*Math.PI*(i+seedRandom(i)*.27)/Math.max(1,count);
            var dist = burst*(.65+seedRandom(i+93)*.8);
            var dx=Math.cos(angle)*dist, dy=Math.sin(angle)*dist;
            var spark=disk("03_SECONDARY_spark_"+("00"+i).slice(-3), __RGB__, 0);
            var start=Math.max(0,hit-Math.min(.07,__DURATION__*.07));
            var end=Math.min(__DURATION__,hit + Math.max(.12,__DURATION__*.38));
            if(end<=start) end=start+.05;
            var st=[start, Math.min(end,start+.035), end];
            track(spark,st,[0, __SPARK_POWER__,0],
                  [[cx,cy],[cx+dx*.23,cy+dy*.23],[cx+dx,cy+dy]],
                  [[2,2],[5,5],[1,1]]);
        }
        comp.openInViewer();
        __SAVE__
    } finally { app.endUndoGroup(); }
})();"""
    # Nothing is evaluated from user text in the AE host; all literals are JSON serialized.
    tokens = {
        "__COMP__": _js(name), "__W__": str(w), "__H__": str(h),
        "__DURATION__": _js(round(duration + .03, 5)), "__FPS__": str(fps),
        "__TIMES__": _js(time_keys), "__ENERGY__": _js(e),
        "__X__": _js(x), "__Y__": _js(y), "__RADII__": _js(radius),
        "__RGB__": _js(col), "__CORE_GAIN__": _js(high * strength),
        "__COUNT__": str(particles), "__PEAK__": _js(round(peak_at, 5)),
        "__BURST__": _js(round(radius_max * (1.45 + strength * .33), 3)),
        "__SPARK_POWER__": _js(round(min(100, 45 * strength), 2)),
        "__SEED__": str(int(obj["signature"][:6], 16)),
        "__SAVE__": ("app.project.save(new File(" + _js(str(Path(save_as).expanduser().resolve())) + "));")
                    if save_as else "",
    }
    for key, value in tokens.items():
        script = script.replace(key, value)
    outfile = path / (name + ".jsx")
    outfile.write_text(script, encoding="utf-8")
    return {"jsx": str(outfile), "comp": name, "duration": round(duration, 4),
            "fps": fps, "canvas": [w, h], "layers": 3 + particles + 1, "spark_count": particles,
            "control_sliders": ["Impact Strength", "Global Scale"],
            "source_recipe": str(Path(recipe).expanduser().resolve()),
            "save_as": str(Path(save_as).expanduser().resolve()) if save_as else None,
            "run_with": "AE MCP ae_run_script or After Effects > File > Scripts > Run Script File",
            "usage": "Reusable multi-layer composition; save the AE project (.aep). For .ffx, select a single layer's properties and use Animation > Save Animation Preset.",
            "limits": "Reconstruction is a procedural approximation. Photographic smoke, 3D depth, simulated fluids and occlusion require authored passes."}
