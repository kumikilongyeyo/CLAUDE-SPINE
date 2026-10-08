"""Frame-by-frame reference-vs-AE visual feedback for the FX memory system.

The initial JSX is executed by the AE MCP (or AE GUI). This module then compares
actual rendered frames with the captured source at matched *times*, assesses
spatial/color/energy differences, and writes the NEXT tuned editable JSX.
It deliberately never reports an improvement until the next real render is evaluated.
"""
from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from . import ae_bridge, ae_fx_memory as memory


def _clip(value: float, lo: float, hi: float) -> float:
    return float(max(lo, min(hi, value)))


def _materialize(source: str, fps: float, limit: int, tmp: Path):
    if not source:
        raise ValueError("Missing reference source (or rendered candidate frames)")
    tmp.mkdir(parents=True, exist_ok=True)
    return memory._frames(Path(source).expanduser().resolve(), fps, limit, tmp)


def _standard_frame(path: Path, w: int, h: int, mode: str,
                    background: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    # A true AE TIFF with premultiplied alpha cannot be decoded correctly by Pillow.
    if path.suffix.lower() in (".tif", ".tiff"):
        pm = ae_bridge.read_premultiplied(path, "alpha")
        alpha = pm[..., 3]
        rgb = np.divide(pm[..., :3], alpha[..., None],
                        out=np.zeros_like(pm[..., :3]), where=alpha[..., None] > 0.001)
        data = np.dstack([rgb, alpha])
    else:
        data = memory._array(path, 256)
    if (data.shape[1], data.shape[0]) != (w, h):
        im = Image.fromarray(np.round(np.clip(data, 0, 1) * 255).astype(np.uint8), "RGBA")
        data = np.asarray(im.resize((w, h), Image.Resampling.BILINEAR), np.float32) / 255
    mask = memory._mask(data, mode, background)
    rgb = data[..., :3] * mask[..., None]
    rgba = np.dstack([rgb, mask])
    return rgba, data


def _feature(pm: np.ndarray) -> dict[str, float]:
    a = pm[..., 3]
    lum = pm[..., :3] @ np.array([.2126, .7152, .0722], np.float32)
    mass = float(lum.sum())
    h, w = lum.shape
    if mass < 1e-5:
        return {"energy": 0., "radius": .02, "x": .5, "y": .5,
                "coverage": 0., "detail": 0., "heat": 0.}
    yy, xx = np.indices((h, w), np.float32)
    x = float((xx * lum).sum() / mass) / max(w - 1, 1)
    y = float((yy * lum).sum() / mass) / max(h - 1, 1)
    radius = math.sqrt(float((((xx / w - x)**2 + (yy / h - y)**2) * lum).sum()) / mass)
    # Local contrast as a simple texture/detail proxy (not an actual material decomposition).
    dx = float(np.abs(np.diff(lum, axis=1)).sum())
    dy = float(np.abs(np.diff(lum, axis=0)).sum())
    edge = (dx + dy) / max(mass, 1e-4)
    return {"energy": mass / (w*h), "radius": radius, "x": x, "y": y,
            "coverage": float((a > .1).mean()), "detail": edge,
            "heat": float((lum > .75).mean())}


def _nearest_indices(times: list[float], targets: list[float]) -> list[int]:
    arr = np.asarray(times, float)
    return [int(np.argmin(np.abs(arr - t))) for t in targets]


def _mae(a: np.ndarray, b: np.ndarray) -> dict:
    # Metrics independent of frame canvas size, with extra emphasis on where FX is visible.
    visibility = np.maximum(a[..., 3], b[..., 3])
    union = np.clip(visibility * 3, .08, 1.)
    color = np.abs(a[..., :3] - b[..., :3]).mean(axis=2)
    alpha = np.abs(a[..., 3] - b[..., 3])
    return {
        "visual_error": float((color * union).sum() / max(union.sum(), 1e-8)),
        "alpha_error": float((alpha * union).sum() / max(union.sum(), 1e-8)),
        "mean_rgb_mae": float(color.mean()),
    }


def _safe_ratio(t: float, c: float, low: float, high: float) -> float:
    if t < 1e-6 or c < 1e-6:
        return 1.
    return _clip(t/c, low, high)


def _weighted_ratio(t: list[float], c: list[float], weights: list[float],
                    low: float, high: float) -> float:
    valid = [(a, b, weight) for a, b, weight in zip(t, c, weights)
             if a > 0.0001 and b > 0.0001 and weight > 0.0001]
    if not valid:
        return 1.
    d = [math.log(_safe_ratio(a, b, low, high)) for a, b, weight in valid]
    ww = [weight for a, b, weight in valid]
    return _clip(math.exp(float(np.average(d, weights=ww))), low, high)


def _frame_preview(target: list[np.ndarray], candidate: list[np.ndarray],
                   times: list[float], dest: Path, max_panels: int = 4) -> None:
    ids = sorted(set(int(i) for i in np.linspace(0, len(target)-1, min(max_panels, len(target)))))
    scale = min(1., 240 / max(target[0].shape[:2]))
    ww = round(target[0].shape[1] * scale)
    hh = round(target[0].shape[0] * scale)
    pad, head = 8, 28
    sheet = Image.new("RGB", (len(ids) * (ww + pad) + pad, 3 * (hh + pad) + head), (27, 28, 34))
    dr = ImageDraw.Draw(sheet)
    for col, i in enumerate(ids):
        x = pad + col * (ww + pad)
        dr.text((x, 6), f"{times[i]:.3f}s", fill=(223,223,223))
        for row, rgba in enumerate((target[i], candidate[i], np.abs(target[i] - candidate[i]))):
            rgb = np.clip(rgba[..., :3] + (1-rgba[..., 3:4]) * .09, 0, 1) if row < 2 else np.clip(rgba[..., :3]*2, 0, 1)
            tile = Image.fromarray(np.round(rgb * 255).astype(np.uint8), "RGB").resize((ww, hh), Image.Resampling.BILINEAR)
            sheet.paste(tile, (x, head + row*(hh+pad)))
    sheet.save(dest)


def compare(recipe: str, out_dir: str, candidate_frames: str = "", candidate_fps: float = 0.,
            aep: str = "", comp: str = "", reference: str = "", background: str = "",
            candidate_mode: str = "alpha", max_frames: int = 40,
            iteration: int = 1, style: str = "premium",
            strength: float = 1.0, color: str = "", speed: float = 1.0,
            canvas: int = 1024, tuning: dict | None = None) -> dict:
    """Real render feedback -> quantitative error + automatically revised editable JSX.

    candidate_frames + candidate_fps = sequence rendered by AE (or aep + comp
    rendered by aerender). The *reference* is the original stored in recipe.
    A source override is supported when the original moved.
    Iteration records stay under out_dir; new rendering is needed to verify progress.
    """
    if bool(candidate_frames) == bool(aep):
        raise ValueError("Give exactly one of candidate_frames or aep")
    if aep and not comp:
        raise ValueError("aep needs comp=<name>")
    if not out_dir:
        raise ValueError("out_dir is required")
    if candidate_frames and candidate_fps <= 0:
        raise ValueError("candidate_frames needs candidate_fps > 0")
    if candidate_mode not in ("alpha", "black", "none"):
        raise ValueError("candidate_mode must be alpha|black|none")
    if not 8 <= max_frames <= 120:
        raise ValueError("max_frames must be 8..120")
    if iteration < 1 or iteration > 500:
        raise ValueError("iteration must be 1..500")
    recipe_obj = json.loads(Path(recipe).expanduser().read_text(encoding="utf-8"))
    if recipe_obj.get("schema") != memory.FORM:
        raise ValueError("Expected an FX reference recipe")
    source = reference or recipe_obj["source"]["path"]
    if not Path(source).expanduser().is_file() and not Path(source).expanduser().is_dir():
        raise FileNotFoundError("Original reference footage unavailable; pass reference=<new path>")
    dest = Path(out_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ae_fx_visual_match_") as scratch:
        tmp = Path(scratch)
        ref_frames, ref_times, ref_fps = _materialize(
            source, recipe_obj["source"]["sample_fps"], max_frames, tmp/"ref")
        if aep:
            info = ae_bridge.render_comp(aep, comp, tmp/"aerender")
            candidate_paths, candidate_times, effective_fps = (
                info.frames, [(info.start + i) / info.fps for i in range(len(info.frames))], info.fps)
        else:
            candidate_paths, candidate_times, effective_fps = _materialize(
                candidate_frames, candidate_fps, max_frames * 3, tmp/"candidate")
        if len(candidate_paths) < 3:
            raise ValueError("Candidate render needs at least 3 frames")
        w, h = recipe_obj["source"]["preview_size"]
        if max(w, h) > 192:
            factor = 192 / max(w, h)
            w, h = max(8, round(w*factor)), max(8, round(h*factor))
        bg = None
        if background:
            plate = memory._array(Path(background).expanduser().resolve(), 256)
            if (plate.shape[1], plate.shape[0]) != (w, h):
                im = Image.fromarray((plate * 255).astype(np.uint8))
                plate = np.asarray(im.resize((w, h), Image.Resampling.BILINEAR), np.float32)/255
            bg = plate
        ref_mask_mode = recipe_obj["source"]["mask_mode"]
        if ref_mask_mode == "background" and bg is None:
            raise ValueError("Reference needs background=<clean_plate.png> for isolation")
        pairs = _nearest_indices(candidate_times, ref_times)
        ref_pm = [_standard_frame(p, w, h, ref_mask_mode, bg)[0] for p in ref_frames]
        cand_cache = {}
        for idx in set(pairs):
            cand_cache[idx] = _standard_frame(candidate_paths[idx], w, h, candidate_mode, None)[0]
        can_pm = [cand_cache[i] for i in pairs]

    reference_features = [_feature(f) for f in ref_pm]
    render_features = [_feature(f) for f in can_pm]
    weights = [max(f["energy"], 0.00001) for f in reference_features]
    weights = np.asarray(weights)
    weights /= weights.sum()

    measures = [_mae(a, b) for a, b in zip(ref_pm, can_pm)]
    metric_names = ("visual_error", "alpha_error", "mean_rgb_mae")
    aggregate = {n: round(float(np.average([m[n] for m in measures], weights=weights)), 6)
                 for n in metric_names}
    abs_center = float(np.average([
        math.dist((t["x"], t["y"]), (r["x"], r["y"]))
        for t, r in zip(reference_features, render_features)], weights=weights))
    energy_l1 = float(np.average([abs(t["energy"] - r["energy"]) for t, r in
                                  zip(reference_features, render_features)], weights=weights))
    radius_l1 = float(np.average([abs(t["radius"] - r["radius"]) for t, r in
                                  zip(reference_features, render_features)], weights=weights))

    t_energy = [f["energy"] for f in reference_features]
    c_energy = [f["energy"] for f in render_features]
    ref_peak_time = ref_times[int(np.argmax(t_energy))]
    cand_peak_time = ref_times[int(np.argmax(c_energy))]
    ref_mass_center = float(np.average(ref_times, weights=np.maximum(t_energy, 1e-8)))
    cand_mass_center = float(np.average(ref_times, weights=np.maximum(c_energy, 1e-8)))
    duration = max(recipe_obj["analysis"]["duration"], 1e-5)
    # Corrective parameters are bounded and partially damped to prevent oscillation.
    energy_ratio = _weighted_ratio(t_energy, c_energy, weights, .4, 2.5)
    radius_ratio = _weighted_ratio([f["radius"] for f in reference_features],
                                    [f["radius"] for f in render_features], weights, .6, 1.9)
    shifts = [float(np.average([t[k]-r[k] for t, r in zip(reference_features, render_features)], weights=weights))
              for k in ("x", "y")]
    vis_target = float(np.average([f["coverage"] for f in reference_features], weights=weights))
    vis_candidate = float(np.average([f["coverage"] for f in render_features], weights=weights))
    cover_ratio = _safe_ratio(vis_target, vis_candidate, .6, 2.)
    tex_target = float(np.average([f["detail"] for f in reference_features], weights=weights))
    tex_candidate = float(np.average([f["detail"] for f in render_features], weights=weights))
    texture_delta = _clip((tex_target - tex_candidate) * 18., -25, 30)
    timing_correction = (ref_mass_center - cand_mass_center) / duration
    timing_correction = _clip(timing_correction, -.3, .3)
    settings = {key: float((tuning or {}).get(key, default)) for key, default in {
        "energy_gain": 1.0, "radius_gain": 1.0,
        "halo_gain": 1.0, "ring_gain": 1.0,
        "offset_x": 0., "offset_y": 0., "time_shift": 0.,
        "roughness": 0.,
    }.items()}
    damp = .7
    settings.update({
        "energy_gain": _clip(settings["energy_gain"] * energy_ratio**damp, .2, 4),
        "radius_gain": _clip(settings["radius_gain"] * radius_ratio**damp, .35, 3),
        "halo_gain": _clip(settings["halo_gain"] * cover_ratio**.3, .2, 3),
        "ring_gain": _clip(settings["ring_gain"] * radius_ratio**.25, .3, 3),
        "offset_x": _clip(settings["offset_x"] + shifts[0]*damp, -.45, .45),
        "offset_y": _clip(settings["offset_y"] + shifts[1]*damp, -.45, .45),
        "time_shift": _clip(settings["time_shift"] + timing_correction*damp, -.4, .4),
        "roughness": _clip(settings["roughness"] + texture_delta*.5, 0, 65),
    })
    settings = {k: round(v, 5) for k,v in settings.items()}

    # Score is comparable within repeated renders of THIS reference. This is a
    # bounded diagnostic score, not proof of an exact/pixel-identical recreation.
    total_error = (aggregate["visual_error"] * .35 + aggregate["alpha_error"] * .25
                   + abs_center * .15 + min(energy_l1 * 2, 1.) * .12
                   + min(radius_l1, 1.) * .13)
    score = round(_clip((1 - total_error)*100, 0, 100), 2)
    comparison = dest / f"comparison_{iteration:03d}.jpg"
    _frame_preview(ref_pm, can_pm, ref_times, comparison)
    factors = {"energy_ratio": round(energy_ratio, 4), "spread_ratio": round(radius_ratio, 4),
               "coverage_ratio": round(cover_ratio, 4),
               "horizontal_shift": round(shifts[0], 4), "vertical_shift": round(shifts[1], 4),
               "timing_shift_seconds": round(ref_mass_center-cand_mass_center, 4),
               "reference_peak_seconds": round(ref_peak_time, 4),
               "render_peak_seconds": round(cand_peak_time, 4),
               "reference_detail": round(tex_target, 4),
               "render_detail": round(tex_candidate, 4)}

    matched = memory.remix(recipe, str(dest), strength=strength, style=style, color=color,
                           speed=speed, canvas=canvas, fit=settings,
                           comp_name=f'{recipe_obj["id"]}_match_{iteration+1:03d}')
    report = {
        "version": 1, "iteration": iteration, "reference": str(Path(source).resolve()),
        "candidate": aep or str(Path(candidate_frames).resolve()),
        "candidate_comp": comp or None,
        "frames_compared": len(ref_pm), "matched_times": [round(x, 4) for x in ref_times],
        "score": score, "score_note": "Diagnostic frame match score; comparison against newly rendered output is needed to verify improvement.",
        "errors": {**aggregate, "center": round(abs_center, 6),
                   "energy": round(energy_l1, 6), "spread": round(radius_l1, 6)},
        "corrections": factors, "tuning": settings,
        "next_jsx": matched["jsx"], "next_comp": matched["comp"],
        "comparison": str(comparison),
        "next": "Run next_jsx inside AE, render next_comp to new frames or .aep; call ae_fx_match again with iteration incremented and tuning from this result.",
    }
    report_path = dest / f"match_{iteration:03d}.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["report"] = str(report_path)
    return report
