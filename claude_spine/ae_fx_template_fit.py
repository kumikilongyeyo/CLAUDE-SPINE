"""Rebuild a captured reference FROM A STORED AE TEMPLATE (the house rule: never from zero).

``ae_fx_memory.remix(template=...)`` lands here. The template (shockwave, burst, magic_glow ...) is built exactly as
``ae_template`` would build it, with the captured duration, colour and canvas, then nested in an outer comp that
carries the whole fit as keys on ONE layer: position (centre + offset), scale (spread), opacity + Exposure (energy)
and start time (timing). That is the same tuning ``ae_fx_match`` already computes for the shape rebuild, so every
template can be matched to a reference without touching its own technique, and the template comp stays editable.

``rank`` orders the candidate templates for a recipe from its measured behaviour (hit / build / loop, ring growth,
white-hot share, saturation, warmth, rise). It is only a short list: ``ae_fx_auto_fit`` auditions the top ones on a
real render and keeps the best score.
"""
from __future__ import annotations

import colorsys
import json
import math
import re
from pathlib import Path

import numpy as np

from . import ae_templates

# template -> what it looks like, measured the same way capture measures footage.
#   kinds: hit | build | loop it suits;  grow: does the energy's radius expand after the peak (ring / burst);
#   hot: white-hot core share;  sat: saturated colour;  warm: fire / gold;  rise: drifts up;  mode: how it renders
CANDIDATES: dict[str, dict] = {
    "shockwave":    {"kinds": {"hit"}, "grow": True, "hot": True, "mode": "alpha"},
    "glow_pulse":   {"kinds": {"hit", "loop", "build"}, "grow": False, "mode": "alpha"},
    "burst":        {"kinds": {"hit"}, "grow": True, "points": True, "mode": "alpha"},
    "sparkle":      {"kinds": {"loop", "hit"}, "grow": False, "points": True, "hot": True, "mode": "alpha"},
    "metal_sparks": {"kinds": {"hit"}, "grow": True, "points": True, "hot": True, "warm": True, "mode": "additive"},
    "smoke_puff":   {"kinds": {"hit"}, "grow": True, "sat": False, "hot": False, "rise": True, "mode": "alpha"},
    "splash":       {"kinds": {"hit"}, "grow": True, "points": True, "cool": True, "mode": "alpha"},
    "magic_glow":   {"kinds": {"loop", "build"}, "grow": False, "sat": True, "mode": "additive"},
    "prism_glow":   {"kinds": {"loop", "build"}, "grow": False, "sat": False, "hot": True, "mode": "additive"},
    "ripple_glow":  {"kinds": {"loop", "hit"}, "grow": True, "sat": True, "mode": "additive"},
    "energy_burst": {"kinds": {"hit"}, "grow": True, "sat": True, "mode": "additive"},
    "fire_aura":    {"kinds": {"loop"}, "grow": False, "warm": True, "rise": True, "mode": "alpha"},
    "portal_ring":  {"kinds": {"loop"}, "grow": False, "sat": True, "cool": True, "mode": "additive"},
    "lens_flare":   {"kinds": {"hit"}, "grow": False, "hot": True, "mode": "additive"},
}
COUNT_PARAMS = ("n", "count", "motes", "droplets")


def shape_traits(signal: np.ndarray) -> dict:
    """Structure of one frame's light (``signal`` = luminance x mask, H x W): ``rays`` = how much the light varies
    AROUND the centre (streaks, star points, tongues: coefficient of variation along rings, weighted by each ring's
    light) and ``hollow`` = how dark the centre is against the brightest ring (1 = a ring / burst with a hole)."""
    h, w = signal.shape
    mass = float(signal.sum())
    if mass < 1e-6:
        return {"rays": 0.0, "hollow": 0.0}
    yy, xx = np.indices((h, w), dtype=np.float32)
    cx, cy = float((xx * signal).sum() / mass), float((yy * signal).sum() / mass)
    reach = .5 * min(h, w)
    radii = np.linspace(.04, 1.0, 24) * reach
    ang = np.linspace(0, 2 * np.pi, 180, endpoint=False)
    px = np.clip(np.round(cx + np.cos(ang)[None, :] * radii[:, None]).astype(int), 0, w - 1)
    py = np.clip(np.round(cy + np.sin(ang)[None, :] * radii[:, None]).astype(int), 0, h - 1)
    rings = signal[py, px]                              # 24 rings x 180 angles
    m = rings.mean(axis=1)
    cv = rings.std(axis=1) / np.maximum(m, 1e-6)
    rays = float(np.average(cv, weights=m + 1e-9))
    hollow = 1.0 - float(m[:3].mean() / max(float(m.max()), 1e-6))
    return {"rays": round(min(rays, 3.0), 4), "hollow": round(max(0.0, hollow), 4)}


def traits(obj: dict) -> dict:
    """The behaviour ``rank`` compares, from a capture recipe."""
    keys = obj["keys"]
    peak = max(range(len(keys)), key=lambda i: keys[i]["energy"])
    after = [k for k in keys[peak:] if k["energy"] > .2] or [keys[peak]]
    growth = max(k["radius"] for k in after) / max(keys[peak]["radius"], 1e-4)
    r, g, b = obj["analysis"]["color"]
    hue, sat, _ = colorsys.rgb_to_hsv(r, g, b)
    rise = keys[peak]["y"] - min(k["y"] for k in after)         # +: the light climbs after the peak
    hot = max(k.get("heat", 0) for k in keys) / max(obj["analysis"]["coverage_peak"], 1e-4)
    shape = obj["analysis"].get("shape", {})
    return {"kind": obj["analysis"]["kind"], "growth": round(growth, 3), "sat": round(sat, 3),
            "rays": shape.get("rays", 0.0), "hollow": shape.get("hollow", 0.0),
            "hue": round(hue * 360, 1), "warm": sat > .3 and (hue * 360 < 60 or hue * 360 > 330),
            "cool": sat > .3 and 160 < hue * 360 < 260, "rise": round(rise, 3), "hot": round(min(hot, 1), 3)}


def _measured() -> dict:
    try:
        return json.loads(TRAITS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def rank(obj: dict, top: int = 0) -> list[dict]:
    """Candidate templates, best first. Each template's MEASURED traits (``measure_templates``: its own render
    captured like footage) are compared with the reference's: hit / build / loop, growth after the peak, rays,
    hollow centre, rise and white-hot share. Colour is left out (every candidate is recoloured to the reference).
    A template that was never measured falls back to its hand-written flags in ``CANDIDATES``."""
    t = traits(obj)
    measured = _measured()
    out = []
    for name, c in CANDIDATES.items():
        m = measured.get(name)
        if m:
            parts = {"kind": 0.0 if m["kind"] == t["kind"] else (1.0 if "loop" in (m["kind"], t["kind"]) else .6),
                     "growth": abs(math.log(max(t["growth"], .05) / max(m["growth"], .05))) * 3,
                     "rays": min(abs(t["rays"] - m["rays"]), 1.5) * 1.6,
                     "hollow": abs(t["hollow"] - m["hollow"]) * 1.4,
                     "rise": min(abs(t["rise"] - m["rise"]), .5) * 2,
                     "hot": abs(min(t["hot"], 1) - min(m["hot"], 1)) * .6}
            score = round(10 - sum(parts.values()) * 2, 2)
            why = [k for k, v in sorted(parts.items(), key=lambda kv: kv[1])[:3]]
            out.append({"template": name, "score": score, "why": ["closest " + ", ".join(why)],
                        "distance": {k: round(v, 3) for k, v in parts.items()}, "mode": c["mode"]})
            continue
        score, why = 0.0, []
        if t["kind"] in c["kinds"]:
            score += 3; why.append(t["kind"])
        grows = t["growth"] > 1.35
        if c.get("grow") == grows:
            score += 2; why.append("expands" if grows else "holds its size")
        for k, test in (("sat", t["sat"] > .35), ("hot", t["hot"] > .25), ("warm", t["warm"]), ("cool", t["cool"]),
                        ("rise", t["rise"] > .06)):
            if k in c:
                if c[k] == test:
                    score += 1; why.append(("" if test else "not ") + k)
                else:
                    score -= .5
        out.append({"template": name, "score": score, "why": why, "mode": c["mode"]})
    out.sort(key=lambda e: -e["score"])
    return out[:top] if top else out


# which colour of the reference each template's colour parameter takes: base = the captured colour, light / hot =
# toward white, deep = darker. Templates not listed use color=base, core_color=hot, color2=light.
COLOR_ROLES = {
    "fire_aura": {"hot": "hot", "mid": "base", "cool": "deep"},
    "portal_ring": {"color": "light", "glow_color": "base", "deep": "deep"},
    "magic_glow": {"color": "base", "core": "hot"},
    "ripple_glow": {"color": "base", "core": "light"},
    "energy_burst": {"color": "base", "light": "light"},
    "metal_sparks": {"hot": "hot", "cool": "base", "droplet_hot": "light", "droplet_cool": "deep"},
    "smoke_puff": {"light": "light", "mid": "base", "shadow": "deep"},
    "lens_flare": {"tint": "base"},
}
_DEFAULT_ROLES = {"color": "base", "core_color": "hot", "color2": "light"}


def _hex(rgb: list[float]) -> str:
    return "".join(f"{max(0, min(255, round(v * 255))):02X}" for v in rgb)


def _lighten(rgb: list[float], k: float) -> list[float]:
    return [v + (1 - v) * k for v in rgb]


def template_params(template: str, w: int, h: int, fps: int, duration: float, rgb: list[float],
                    strength: float = 1.0, extra: dict | None = None) -> dict:
    """The template's own parameters for this reference: its duration, canvas, colour and particle count."""
    defaults = ae_templates.list_templates()[template]["params"]
    p = {}
    for key, value in (("duration", round(duration, 4)), ("fps", fps), ("size", min(w, h)),
                       ("width", w), ("height", h)):
        if key in defaults:
            p[key] = value
    # measured on the pink burst: hot at 82 % white turned fire_aura's whole body white; real hot cores keep the hue
    palette = {"base": rgb, "light": _lighten(rgb, .35), "hot": _lighten(rgb, .5), "deep": [v * .5 for v in rgb]}
    for key, role in COLOR_ROLES.get(template, _DEFAULT_ROLES).items():
        if isinstance(defaults.get(key), str) and re.fullmatch(r"[0-9A-Fa-f]{6}", defaults[key]):
            p[key] = _hex(palette[role])
    for key in COUNT_PARAMS:
        if key in defaults and isinstance(defaults[key], (int, float)):
            p[key] = max(1, round(defaults[key] * strength))
    p.update(extra or {})
    return p


_WRAP = r"""
(function () {
  var srcName = (String(__r).match(/"comp":"([^"]*)"/) || [])[1], src = null;
  for (var i = 1; i <= app.project.numItems; i++) {
    var it = app.project.item(i);
    if (it instanceof CompItem && it.name === srcName) { src = it; break; }
  }
  if (!src) throw new Error("template comp not found: " + __r);
  var comp = app.project.items.addComp(__COMP__, __W__, __H__, 1, __DURATION__, __FPS__);
  comp.bgColor = [0, 0, 0];
  var ctrl = comp.layers.addNull();
  ctrl.name = "00_FX_CONTROLS"; ctrl.guideLayer = true;
  function slider(name, value) {
    var e = ctrl.property("ADBE Effect Parade").addProperty("ADBE Slider Control");
    e.name = name; e.property(1).setValue(value); return e;
  }
  slider("Impact Strength", 100); slider("Global Scale", 100);
  var L = comp.layers.add(src);
  L.name = "01_TEMPLATE_" + __TEMPLATE__;
  L.startTime = __START__;
  var tr = L.property("ADBE Transform Group"), t = __TIMES__;
  tr.property("ADBE Position").setValuesAtTimes(t, __POS__);
  tr.property("ADBE Scale").setValuesAtTimes(t, __SCALE__);
  tr.property("ADBE Opacity").setValuesAtTimes(t, __OPACITY__);
  tr.property("ADBE Opacity").expression =
    'Math.min(100, value * thisComp.layer("00_FX_CONTROLS").effect("Impact Strength")("Slider") / 100)';
  tr.property("ADBE Scale").expression =
    'value * thisComp.layer("00_FX_CONTROLS").effect("Global Scale")("Slider") / 100';
  var ex = L.property("ADBE Effect Parade").addProperty("ADBE Exposure2");
  var stops = null;
  for (var j = 1; j <= ex.numProperties; j++) if (ex.property(j).name === "Exposure") stops = ex.property(j);
  if (stops) stops.setValuesAtTimes(t, __EXPOSURE__);
  __SAVE__
  return '{"comp":"' + comp.name + '","template":"' + __TEMPLATE__ + '","source_comp":"' + src.name + '"}';
})();
"""


def build(obj: dict, template: str, name: str, out_dir: Path, w: int, h: int, fps: int, duration: float,
          rgb: list[float], fit: dict, strength: float = 1.0, params: dict | None = None,
          save_as: str = "") -> dict:
    """Write the template + fit-wrapper script. ``fit`` is the remix tuning (gains, offsets, timeline)."""
    if template not in ae_templates.list_templates():
        raise ValueError(f"unknown template {template!r}; candidates: {sorted(CANDIDATES)}")
    tp = template_params(template, w, h, fps, duration, rgb, strength, params)
    built = ae_templates.build_script(template, {**tp, "comp": name + "_src"}, out_dir / (name + "_parts"))
    keys = obj["keys"]
    # the template's own motion carries the effect (a puff rises by itself), so the layer sits still on the
    # reference's peak centre and only the measured residuals (offset, per-key dx/dy) move it
    peak = max(keys, key=lambda k: k["energy"])
    cx, cy = min(max(float(peak["x"]), 0), 1), min(max(float(peak["y"]), 0), 1)
    times, pos, scale, opacity, exposure = [], [], [], [], []
    last = -1.0
    for k, local in zip(keys, fit["timeline"]):
        tk = max(round(min(max(float(k["t"]), 0), 1) * duration, 5), last + 1e-4)
        last = tk
        g = fit["energy_gain"] * local["energy"] * strength
        times.append(tk)
        pos.append([round((cx + fit["offset_x"] + local["dx"]) * w, 3), round((cy + fit["offset_y"] + local["dy"]) * h, 3)])
        s = round(100 * fit["radius_gain"] * local["radius"], 3)
        scale.append([s, s])
        opacity.append(round(min(100.0, 100 * g), 3))
        exposure.append(round(min(3.0, math.log2(max(g, 1.0))), 4))
    js = json.dumps
    save = f"app.project.save(new File({js(str(Path(save_as).expanduser().resolve()))}));" if save_as else ""
    wrap = _WRAP
    for key, value in {"__COMP__": js(name), "__W__": str(w), "__H__": str(h),
                       "__DURATION__": js(round(duration + .03, 5)), "__FPS__": str(fps),
                       "__TEMPLATE__": js(template), "__START__": js(round(fit["time_shift"] * duration, 5)),
                       "__TIMES__": js(times), "__POS__": js(pos), "__SCALE__": js(scale),
                       "__OPACITY__": js(opacity), "__EXPOSURE__": js(exposure), "__SAVE__": save}.items():
        wrap = wrap.replace(key, value)
    src = Path(built["script"]).read_text(encoding="utf-8")
    # the template script ends with `if (__err) throw __err; __r;` -> append the wrapper as the new last expression
    src = re.sub(r"__r;\s*$", "", src) + wrap
    outfile = out_dir / (name + ".jsx")
    outfile.write_text(src, encoding="utf-8")
    return {"jsx": str(outfile), "comp": name, "template": template, "template_params": tp,
            "mode": CANDIDATES.get(template, {}).get("mode", "alpha"), "source_comp": name + "_src"}


TRAITS_FILE = Path(__file__).resolve().parent / "ae_templates" / "_traits.json"


def measure_templates(work_dir: str, names: list[str] | None = None, size: int = 256, afterfx_bin: str = "",
                      timeout_seconds: float = 900) -> dict:
    """Render every candidate template once (defaults, ``size`` px) and capture it exactly like footage, so
    ``rank`` compares measured templates with measured references. Writes ``ae_templates/_traits.json``.
    Needs After Effects; run it again after adding or changing a candidate template."""
    from . import ae_bridge, ae_fx_autofit, ae_fx_memory
    from PIL import Image
    work = Path(work_dir).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    names = names or sorted(CANDIDATES)
    scripts = []
    for name in names:
        defaults = ae_templates.list_templates()[name]["params"]
        p = {"comp": f"measure_{name}"}
        if "size" in defaults:
            p["size"] = size
        scripts.append(ae_templates.build_script(name, p, work / "scripts")["script"])
    master = work / "measure_all.jsx"
    master.write_text("".join(f"$.evalFile(new File({json.dumps(s)}));\n" for s in scripts), encoding="utf-8")
    aep = work / "measure_templates.aep"
    ae_fx_autofit._execute(str(master), aep, work / "measure_ack.txt", None,
                           ae_fx_autofit._resolve_afterfx(afterfx_bin), timeout_seconds)
    out = json.loads(TRAITS_FILE.read_text()) if TRAITS_FILE.exists() else {}
    for name in names:
        info = ae_bridge.render_comp(str(aep), f"measure_{name}", work / "frames" / name)
        pngs = work / "png" / name
        pngs.mkdir(parents=True, exist_ok=True)
        for i, fr in enumerate(info.frames):
            pm = ae_bridge.read_premultiplied(fr, "alpha")
            a = pm[..., 3:4]
            rgb = np.divide(pm[..., :3], a, out=np.zeros_like(pm[..., :3]), where=a > 1e-3)
            Image.fromarray(np.round(np.clip(np.dstack([rgb, a]), 0, 1) * 255).astype(np.uint8), "RGBA") \
                .save(pngs / f"f_{i:05d}.png")
        mode = "black" if CANDIDATES[name]["mode"] == "additive" else "alpha"
        cap = ae_fx_memory.capture(str(pngs), str(work / "lib"), name, fps=info.fps, mask_mode=mode,
                                   archive_source=False)
        t = traits(json.loads(Path(cap["recipe"]).read_text()))
        out[name] = {k: t[k] for k in ("kind", "growth", "sat", "hue", "rise", "hot", "rays", "hollow")}
    TRAITS_FILE.write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return out
