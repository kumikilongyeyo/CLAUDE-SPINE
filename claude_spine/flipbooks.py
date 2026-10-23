"""Ready flipbooks: the After Effects templates rendered ONCE and stored, so they drop onto any asset without AE.

``CATALOG`` lists what is rendered: every non-particle template (the particle ones are ``fx_emitter`` presets
``ae_*``) at its own tuned defaults, plus a few variants. Templates that need the user's art or text to exist
(heat_shimmer, relief_shimmer, surface_sweep, edge_aura, saber) are not here: render those with ``ae_template``.

A flipbook is a folder ``<name>/`` holding ``f_0000.webp ...`` (straight RGBA, lossless where it matters) and
``meta.json`` (template, params, fps, mode alpha | additive, seq_mode once | loop, size, parts for multi-comp
templates such as win_aura in / loop / out). ``fx_flipbook`` (tools_flipbook.py) places one on any skeleton
through the same importer as ``ae_fx_to_spine`` (x, y, scale, parent, behind / front_of, start, tint, copies,
budget), and ``fx_emitter`` takes ``texture="flipbook:<name>"`` so every particle plays it.

Where they live: ``~/.cache/claude-spine/flipbooks`` (``CLAUDE_SPINE_FLIPBOOKS`` overrides). They are too big for
the package (about 100 MB lossless), so each one is a zip on the GitHub release ``RELEASE`` and is downloaded the
first time it is used (1-13 MB each). ``render_all`` rebuilds them (needs After Effects; run it again after
changing a template) and ``pack_release`` writes the zips to upload.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

from . import ae_bridge, ae_templates

RELEASE = "flipbooks-v1"
RELEASE_URL = f"https://github.com/kumikilongyeyo/CLAUDE-SPINE/releases/download/{RELEASE}/{{name}}.zip"

# name -> template, params over its defaults, parts ({part: comp suffix}; "" = the main comp), what it is for
CATALOG: dict[str, dict] = {
    "caustics":       {"template": "caustics", "doc": "Rippling water light (caustic net), loops. Under water, behind reels."},
    "electric_frame": {"template": "electric_frame", "doc": "Crackling electricity round a square frame. Feature cells, locked symbols."},
    "energy_burst":   {"template": "energy_burst", "doc": "Cyan energy-smoke pop round a button or symbol: pops in 2 frames, holds, falls to a haze. Button taps."},
    "fire":           {"template": "fire", "doc": "A soft rising flame, loops. Torches, braziers, a burning symbol."},
    "fire_aura":      {"template": "fire_aura", "doc": "Flames shooting outward from a hole (power-up aura), loops. Behind a symbol or character."},
    "fire_strip":     {"template": "fire_strip", "doc": "A straight strip of flames rising from a base line, loops; bend it along a path with ae_fx_along_path frames_dir=."},
    "flame_wisps":    {"template": "flame_wisps", "doc": "Anamorphic flame wisps, one-shot, tintable. Spin buttons, banners."},
    "fog_roll":       {"template": "fog_roll", "doc": "A bank of fog rolling sideways, loops. Ground fog, mystery screens."},
    "sand_roll":      {"template": "fog_roll", "params": {"kind": "sand"}, "doc": "Sand blowing sideways with hopping grains, loops. Desert themes."},
    "frost_creep":    {"template": "frost_creep", "doc": "Hoarfrost creeping over a round face from its rim and freezing it, one-shot. Freeze features."},
    "glow_pulse":     {"template": "glow_pulse", "doc": "A soft round glow that swells and fades with a hot core. Behind a symbol, on a win."},
    "god_rays":       {"template": "god_rays", "doc": "Volumetric light shafts sweeping slowly, loops. Reveals, temple light."},
    "lens_flare":     {"template": "lens_flare", "doc": "An optical lens flare with a ghost chain that blooms and drifts, one-shot. Big moments."},
    "lightning":      {"template": "lightning", "doc": "A forking bolt with stepped leader, return stroke and restrikes, one-shot. Strikes between two points."},
    "magic_glow":     {"template": "magic_glow", "doc": "A breathing magic aura with wisps flowing out and motes, loops, tintable."},
    "magic_smoke":    {"template": "magic_smoke", "doc": "Glowing magic smoke curling up from a source, loops, tintable."},
    "magic_smoke_dark": {"template": "magic_smoke", "params": {"luminous": False},
                         "doc": "See-through (non-glowing) magic smoke curling up, loops. Over bright art."},
    "orbit_ribbons":  {"template": "orbit_ribbons", "parts": {"back": "_back", "front": "_front"},
                       "doc": "Rings of energy orbiting a subject, as a back half (behind it) and a front half (in front), loops."},
    "portal_ring":    {"template": "portal_ring", "doc": "The churning lace edge of a magic portal, loops. Pair with fx_recipe portal."},
    "prism_glow":     {"template": "prism_glow", "doc": "White star / streak / lens-ring glow that splits into a spectrum in Spine, loops."},
    "ripple_glow":    {"template": "ripple_glow", "doc": "Soft smoky glowing ripples from the centre, every wave different, loops. Charged orbs, multipliers."},
    "ripple_lines":   {"template": "ripple_glow", "params": {"look": "line"}, "doc": "Crisp glowing rings rippling out, loops."},
    "shockwave":      {"template": "shockwave", "doc": "An expanding ring with a soft flash, one-shot. Impacts, landings, reveals."},
    "smoke_haze":     {"template": "smoke_haze", "doc": "A column of rising haze, loops. Over a fire, steam, incense."},
    "smoke_puff":     {"template": "smoke_puff", "doc": "A realistic smoke puff that bursts, rises, rolls and erodes, one-shot. Landings, poofs."},
    "win_aura":       {"template": "win_aura", "parts": {"in": "_in", "loop": "_loop", "out": "_out"},
                       "doc": "A symbol's win aura in three parts: flare in, smoky loop, dissolve out."},
}
ONCE = {"energy_burst", "flame_wisps", "frost_creep", "lens_flare", "lightning", "shockwave", "smoke_puff",
        "glow_pulse"}


def data_dir() -> Path:
    env = os.environ.get("CLAUDE_SPINE_FLIPBOOKS")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cache" / "claude-spine" / "flipbooks"


def listing() -> dict[str, dict]:
    root = data_dir()
    out = {}
    for name, e in CATALOG.items():
        meta = root / name / "meta.json"
        m = json.loads(meta.read_text()) if meta.exists() else {}
        out[name] = {"doc": e["doc"], "template": e["template"], "downloaded": meta.exists(),
                     **{k: m[k] for k in ("mode", "seq_mode", "fps", "seconds", "size", "parts", "tintable") if k in m}}
    return out


def fetch(name: str, timeout: float = 120) -> Path:
    """Download one flipbook's zip from the release into the data folder (once)."""
    import io
    import urllib.request
    import zipfile
    dest = data_dir()
    req = urllib.request.Request(RELEASE_URL.format(name=name), headers={"User-Agent": "claude-spine"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    tmp = Path(tempfile.mkdtemp(prefix="flipbook_dl_", dir=dest.parent if dest.parent.exists() else None))
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():                # only <name>/... inside, no absolute or parent paths
                parts = Path(info.filename).parts
                if not parts or parts[0] != name or ".." in parts or Path(info.filename).is_absolute():
                    raise ValueError(f"unexpected file {info.filename!r} in the {name} flipbook zip")
            z.extractall(tmp)
        dest.mkdir(parents=True, exist_ok=True)
        if (dest / name).exists():
            shutil.rmtree(dest / name)
        shutil.move(str(tmp / name), str(dest / name))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return dest / name


def meta(name: str, download: bool = True) -> dict:
    if name not in CATALOG:
        raise ValueError(f"no flipbook {name!r}; one of {sorted(CATALOG)}")
    p = data_dir() / name / "meta.json"
    if not p.exists() and download and not os.environ.get("CLAUDE_SPINE_FLIPBOOKS"):
        try:
            fetch(name)
        except Exception as e:  # noqa: BLE001 - reported below with what to do
            raise FileNotFoundError(f"flipbook {name!r} is not here ({p}) and the download failed ({e}); check the "
                                    f"network, or run flipbooks.render_all() with After Effects") from e
    if not p.exists():
        raise FileNotFoundError(f"flipbook {name!r} is not rendered here ({p}); run flipbooks.render_all() with "
                                f"After Effects, or set CLAUDE_SPINE_FLIPBOOKS to a folder that has it")
    return json.loads(p.read_text())


def pack_release(out_dir: str, root: str = "") -> list[str]:
    """One zip per flipbook (``<name>/meta.json`` + frames) for the ``RELEASE`` assets."""
    import zipfile
    src = Path(root).expanduser() if root else data_dir()
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    made = []
    for name in CATALOG:
        if not (src / name / "meta.json").exists():
            continue
        z = out / f"{name}.zip"
        with zipfile.ZipFile(z, "w", zipfile.ZIP_STORED) as zf:      # WebP is already compressed
            for f in sorted((src / name).rglob("*")):
                if f.is_file():
                    zf.write(f, f.relative_to(src).as_posix())
        made.append(str(z))
    return made


def frames(name: str, part: str = "") -> list[Path]:
    m = meta(name)
    part = part or m["default_part"]
    if part not in m["parts"]:
        raise ValueError(f"flipbook {name!r} has parts {list(m['parts'])}, not {part!r}")
    return sorted((data_dir() / name / part).glob("f_*.webp"))


def materialize(name: str, part: str = "") -> tuple[Path, dict]:
    """PNG copies of the frames in a temp folder (what the importer reads), with the part's meta."""
    m = meta(name)
    part = part or m["default_part"]
    tmp = Path(tempfile.mkdtemp(prefix=f"flip_{name}_"))
    for i, f in enumerate(frames(name, part)):
        Image.open(f).save(tmp / f"f_{i:04d}.png")
    return tmp, {**m, **m["parts"][part], "part": part}


def _store(frames_in: list[Path], dest: Path, mode: str, max_size: int) -> dict:
    """Premultiplied AE TIFFs -> straight RGBA WebP (lossless), at most ``max_size`` on the long side."""
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("f_*.webp"):
        old.unlink()
    size, source = None, None
    for i, f in enumerate(frames_in):
        pm = ae_bridge.read_premultiplied(f, mode)
        if mode == "additive":                # light on opaque black: brightness becomes the alpha, so the frame
            pm[..., 3] = pm[..., :3].max(axis=2)   # is also a clean texture (no black square) for fx_emitter
        a = pm[..., 3:4]
        rgb = np.divide(pm[..., :3], a, out=np.zeros_like(pm[..., :3]), where=a > 1e-3)
        im = Image.fromarray(np.round(np.clip(np.dstack([rgb, a]), 0, 1) * 255).astype(np.uint8), "RGBA")
        source = source or list(im.size)
        if max(im.size) > max_size:
            k = max_size / max(im.size)
            im = im.resize((round(im.width * k), round(im.height * k)), Image.Resampling.LANCZOS)
        size = im.size
        im.save(dest / f"f_{i:04d}.webp", lossless=True, method=6)
    return {"frames": len(frames_in), "size": list(size or (0, 0)), "source_size": source}


def render_all(work_dir: str, names: list[str] | None = None, max_size: int = 512, out_dir: str = "",
               timeout_seconds: float = 1500, reuse: bool = False) -> dict:
    """Build every catalogue template in one fresh After Effects project, render each comp with aerender and
    store the frames. The artist's open project is left alone (saved + clean: reopened afterwards)."""
    from . import ae_fx_autofit
    work = Path(work_dir).expanduser().resolve()
    work.mkdir(parents=True, exist_ok=True)
    names = names or list(CATALOG)
    scripts = []
    for n in names:
        e = CATALOG[n]
        scripts.append(ae_templates.build_script(e["template"], {**e.get("params", {}), "comp": f"fb_{n}"},
                                                 work / "scripts" / n)["script"])
    master = work / "build_all.jsx"
    aep = work / "flipbooks.aep"
    if reuse and aep.exists():                # store again from the frames already rendered (no After Effects)
        return _finish(work, names, root_dir(out_dir), max_size, aep, reuse)
    master.write_text("".join(f"$.evalFile(new File({json.dumps(s)}));\n" for s in scripts), encoding="utf-8")
    ae_fx_autofit._execute(str(master), aep, work / "ack.txt", None, ae_fx_autofit._resolve_afterfx(), timeout_seconds)
    return _finish(work, names, root_dir(out_dir), max_size, aep, reuse)


def root_dir(out_dir: str = "") -> Path:
    return Path(out_dir).expanduser() if out_dir else data_dir()


def _finish(work: Path, names: list[str], root: Path, max_size: int, aep: Path, reuse: bool) -> dict:
    report = {}
    for n in names:
        e = CATALOG[n]
        tpl = ae_templates.list_templates()[e["template"]]
        mode = "additive" if _mode(e["template"], e.get("params", {})) == "additive" else "alpha"
        parts = {}
        for part, suffix in (e.get("parts") or {"main": ""}).items():
            done = work / "frames" / n / part
            if reuse and any(done.glob("f_*.tif")):
                fps = float((done / "fps.txt").read_text()) if (done / "fps.txt").exists() else float(
                    {**tpl["params"], **e.get("params", {})}["fps"])
                tifs = sorted(done.glob("f_*.tif"))
            else:
                info = ae_bridge.render_comp(str(aep), f"fb_{n}{suffix}", work / "frames" / n / part)
                fps, tifs = info.fps, info.frames
                (work / "frames" / n / part / "fps.txt").write_text(str(fps))
            stored = _store(tifs, root / n / part, mode, max_size)
            parts[part] = {"fps": fps, "seconds": round(len(tifs) / fps, 4), **stored}
        first = next(iter(parts.values()))
        m = {"name": n, "template": e["template"], "params": {**tpl["params"], **e.get("params", {})}, "doc": e["doc"],
             "mode": mode, "seq_mode": "once" if n in ONCE else "loop", "fps": first["fps"],
             "seconds": first["seconds"], "size": first["size"], "source_size": first["source_size"], "parts": parts,
             "default_part": "loop" if "loop" in parts else next(iter(parts)),
             "tintable": _flag(e["template"], "tintable")}
        if n == "win_aura":
            m["parts"]["in"]["seq_mode"], m["parts"]["out"]["seq_mode"] = "once", "once"
            m["parts"]["loop"]["seq_mode"] = "loop"
        (root / n / "meta.json").write_text(json.dumps(m, indent=1) + "\n")
        report[n] = {k: m[k] for k in ("mode", "seq_mode", "fps", "seconds", "size")} | {"parts": list(parts)}
    return report


def _src(template: str) -> str:
    return (ae_templates.HERE / f"{template}.jsx").read_text(encoding="utf-8")


def _mode(template: str, params: dict) -> str:
    src = _src(template)
    if template == "magic_smoke":                       # luminous (default) renders on black, see-through in alpha
        return "alpha" if params.get("luminous") is False else "additive"
    # declared in its JSON line, or in its doc ("on black for an additive layer (mode=\"additive\")")
    return "additive" if ('"mode":"additive"' in src or 'mode=\\"additive\\"' in src) else "alpha"


def _flag(template: str, flag: str) -> bool:
    return f'"{flag}":true' in _src(template)
