"""Global FX art-direction profiles for the recipe system.

This module deliberately keeps *motion semantics* and *look tuning* separate.

Recipes still decide what an explosion, shine, beam or impact physically does.
A style profile only retunes shared presentation knobs (scale, particle count,
one-shot timing, intensity and a small set of recipe options), supplies a
semantic depth manifest, and can add a short reactive-light pass to real art.

That makes the same recipe portable from chunky stylised -> premium semi-real ->
restrained realistic without duplicating every recipe.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from .art_tools import art_twin
from .project import Project
from .timeline import AnimBuilder, r


STYLE_PROFILES: dict[str, dict[str, Any]] = {
    "stylized": {
        "summary": "Chunky, graphic, readable FX: fewer/bigger beats, stronger colour and faster impacts.",
        "shared": {"scale": 1.06, "count": 0.78, "intensity": 1.10, "time": 0.88},
        "option_multipliers": {
            "sparks": 0.78, "embers": 0.72, "specks": 0.78, "dust": 0.78,
            "wave": 1.30, "thickness": 1.18, "core_width": 1.16, "strand_width": 1.15,
            "column_alpha": 1.16, "alpha": 1.12, "spread": 1.06,
        },
        "lighting": {"strength": 0.68, "attack": 0.035, "hold": 0.045, "decay": 0.22, "color": "FFF0C8"},
        "depth": {"back": 0.35, "subject": 0.0, "front": -0.22, "lens": -0.05},
    },
    "premium": {
        "summary": "Balanced slot/cinematic look: physics stays readable, layering is rich but controlled.",
        "shared": {"scale": 1.00, "count": 0.95, "intensity": 0.98, "time": 1.00},
        "option_multipliers": {
            "sparks": 0.92, "embers": 0.95, "specks": 0.92, "dust": 0.95,
            "wave": 0.95, "thickness": 0.96, "core_width": 0.95, "strand_width": 0.95,
            "column_alpha": 0.90, "alpha": 0.92, "spread": 1.00,
        },
        "lighting": {"strength": 0.52, "attack": 0.026, "hold": 0.035, "decay": 0.31, "color": "FFF3D8"},
        "depth": {"back": 0.55, "subject": 0.0, "front": -0.34, "lens": -0.10},
    },
    "realistic": {
        "summary": "Restrained physical look: tighter light, softer volume, less graphic motion and longer decay.",
        "shared": {"scale": 0.98, "count": 0.82, "intensity": 0.82, "time": 1.10},
        "option_multipliers": {
            "sparks": 0.78, "embers": 1.10, "specks": 0.86, "dust": 1.08,
            "wave": 0.70, "thickness": 0.78, "core_width": 0.82, "strand_width": 0.80,
            "column_alpha": 0.68, "alpha": 0.76, "spread": 0.94,
        },
        "lighting": {"strength": 0.38, "attack": 0.018, "hold": 0.024, "decay": 0.42, "color": "FFF7E8"},
        "depth": {"back": 0.75, "subject": 0.0, "front": -0.46, "lens": -0.16},
    },
}

_NUMERIC_GROUPS = ("shared", "option_multipliers", "lighting", "depth")


def _lerp(a: float, b: float, t: float) -> float:
    return float(a) * (1.0 - t) + float(b) * t


def _interpolate(a: dict[str, Any], b: dict[str, Any], t: float, name: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "name": name,
        "summary": f"Interpolated stylized -> realistic profile ({t:.2f})",
    }
    for group in _NUMERIC_GROUPS:
        ga, gb = a.get(group, {}), b.get(group, {})
        keys = set(ga) | set(gb)
        vals: dict[str, Any] = {}
        for k in keys:
            va, vb = ga.get(k), gb.get(k)
            if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
                vals[k] = _lerp(va, vb, t)
            else:
                vals[k] = deepcopy(vb if t >= 0.5 else va)
        out[group] = vals
    # colour is semantic, not numeric. Keep warm readable light at the stylised end,
    # near-white at the realistic end.
    out["lighting"]["color"] = b["lighting"]["color"] if t >= 0.66 else a["lighting"]["color"]
    return out


def _deep_merge(base: dict[str, Any], custom: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(base)
    for k, v in custom.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = deepcopy(v)
    return out


def resolve(style: str = "", realism: float = -1.0, custom: dict | None = None) -> dict[str, Any] | None:
    """Resolve a named profile, a stylized->realistic mix, and optional custom overrides.

    style="" and realism<0 means "no style layer" for complete backwards compatibility.
    realism is 0..1 and is only used when style is omitted.
    """
    if style:
        key = style.lower().strip()
        if key not in STYLE_PROFILES:
            raise ValueError(f"unknown FX style {style!r}; one of {sorted(STYLE_PROFILES)}")
        out = deepcopy(STYLE_PROFILES[key])
        out["name"] = key
    elif realism >= 0:
        if not 0 <= realism <= 1:
            raise ValueError("realism must be 0..1")
        out = _interpolate(STYLE_PROFILES["stylized"], STYLE_PROFILES["realistic"], float(realism),
                           f"realism_{realism:.2f}")
        out["realism"] = float(realism)
    elif custom:
        out = deepcopy(STYLE_PROFILES["premium"])
        out["name"] = "custom"
    else:
        return None
    if custom:
        out = _deep_merge(out, custom)
        out["name"] = str(custom.get("name", out.get("name", "custom")))
    return out


def listing() -> dict[str, Any]:
    return {
        "profiles": {k: deepcopy(v) for k, v in STYLE_PROFILES.items()},
        "realism": "0..1 interpolates stylized -> realistic when style is omitted",
        "custom": "style_profile deep-merges over the selected profile (or premium when no base is selected)",
        "capture_metrics": {
            "realism": "0..1",
            "glow_spread": "0 tight core .. 1 broad bloom",
            "particle_density": "0 sparse .. 1 dense",
            "motion_exaggeration": "0 restrained .. 1 graphic",
            "decay": "0 snappy .. 1 long tail",
            "saturation": "0 restrained .. 1 vivid",
        },
    }


def capture(metrics: dict[str, float]) -> dict[str, Any]:
    """Turn normalised visual measurements from clip-breakdown into a reusable profile.

    This intentionally consumes *measurements*, not pixels/video itself. The clip-breakdown
    skill already owns video inspection; its output can be fed here without coupling this
    low-level Spine package to a video stack.
    """
    allowed = {"realism", "glow_spread", "particle_density", "motion_exaggeration", "decay", "saturation"}
    bad = set(metrics) - allowed
    if bad:
        raise ValueError(f"unknown style metric(s) {sorted(bad)}; valid: {sorted(allowed)}")
    vals = {k: float(v) for k, v in metrics.items()}
    if any(not 0 <= v <= 1 for v in vals.values()):
        raise ValueError("style metrics are normalised 0..1")
    rr = vals.get("realism", 0.5)
    p = resolve(realism=rr) or deepcopy(STYLE_PROFILES["premium"])
    glow = vals.get("glow_spread", 0.5)
    dens = vals.get("particle_density", 0.5)
    motion = vals.get("motion_exaggeration", 0.5)
    decay = vals.get("decay", 0.5)
    sat = vals.get("saturation", 0.5)
    p["name"] = "captured"
    p["summary"] = "Profile captured from normalised reference measurements"
    p["shared"]["count"] *= 0.65 + 0.70 * dens
    p["shared"]["intensity"] *= 0.78 + 0.44 * sat
    p["shared"]["time"] *= 0.82 + 0.36 * decay
    p["option_multipliers"]["wave"] *= 0.60 + 0.80 * motion
    p["option_multipliers"]["spread"] *= 0.82 + 0.36 * motion
    p["option_multipliers"]["column_alpha"] *= 0.65 + 0.70 * glow
    p["lighting"]["strength"] *= 0.75 + 0.50 * glow
    p["source_metrics"] = vals
    return {"profile": p, "realism_estimate": rr}


def tune(meta: dict[str, Any], *, style: str = "", realism: float = -1.0, custom: dict | None = None,
         scale: float, count: int, duration: float, intensity: float,
         options: dict | None = None) -> tuple[float, int, float, float, dict | None, dict[str, Any] | None]:
    """Apply one profile to shared recipe arguments. Explicit recipe options always win."""
    p = resolve(style, realism, custom)
    if p is None:
        return scale, count, duration, intensity, options, None

    sh = p["shared"]
    scale *= float(sh.get("scale", 1.0))
    intensity *= float(sh.get("intensity", 1.0))

    base_count = count or int(meta.get("count", 0) or 0)
    if base_count:
        count = max(1, int(round(base_count * float(sh.get("count", 1.0)))))

    if meta.get("kind") == "one-shot":
        base_duration = duration or float(meta["duration"])
        duration = base_duration * float(sh.get("time", 1.0))

    opts = dict(options or {})
    defaults = {k: v[0] for k, v in meta.get("options", {}).items()}
    for key, mult in p.get("option_multipliers", {}).items():
        if key in opts or key not in defaults:
            continue
        val = defaults[key]
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        tuned = float(val) * float(mult)
        opts[key] = int(round(tuned)) if isinstance(val, int) else tuned

    public = {
        "name": p.get("name", style or "custom"),
        "summary": p.get("summary", ""),
        "shared": deepcopy(p.get("shared", {})),
        "lighting": deepcopy(p.get("lighting", {})),
        "depth": deepcopy(p.get("depth", {})),
    }
    if "realism" in p:
        public["realism"] = p["realism"]
    if "source_metrics" in p:
        public["source_metrics"] = deepcopy(p["source_metrics"])
    return scale, count, duration, intensity, opts or None, public


_DEPTH = {
    "lens": ("flare", "flash", "rays", "lens", "chromatic"),
    "back": ("smoke", "haze", "fog", "disc", "under", "column", "floor", "fill", "aura", "cloud"),
    "front": ("spark", "mote", "debris", "coin", "comet", "confetti", "shard", "drip", "ember", "twinkle"),
}


def depth_class(role: str | None = None, token: str = "", blend: str = "additive") -> str:
    text = f"{role or ''} {token}".lower()
    for depth, words in _DEPTH.items():
        if any(w in text for w in words):
            return depth
    if blend == "normal" and any(w in text for w in ("smoke", "fog", "disc", "fill", "cloud")):
        return "back"
    return "subject"


def relight(project: Project, animation: str, slots: list[str], *, start: float, color: str = "",
            strength: float = 0.0, duration: float = 0.0, profile: dict | None = None,
            name: str = "reactive") -> dict[str, Any]:
    """Add a short additive light response that uses the subject's own art.

    This is intentionally a safe, cheap *surface response* rather than pretending a
    flat sprite has a normal map. A later engine/AE pass can replace it with a true
    directional rim, while this version already makes impacts feel integrated.
    """
    if not slots:
        return {}
    sk = project.data
    for s in slots:
        sk.slot(s)

    prof = profile or deepcopy(STYLE_PROFILES["premium"])
    light = prof.get("lighting", {})
    col = (color or light.get("color") or "FFF3D8").lstrip("#").upper()[:6]
    gain = float(strength) if strength > 0 else float(light.get("strength", 0.5))
    gain = max(0.0, min(1.0, gain))
    attack = float(light.get("attack", 0.025))
    hold = float(light.get("hold", 0.035))
    decay = float(light.get("decay", 0.3))
    base_len = max(0.001, attack + hold + decay)
    if duration > 0:
        k = duration / base_len
        attack, hold, decay = attack * k, hold * k, decay * k
    end = start + attack + hold + decay
    peak = start + attack
    fall = peak + hold

    tag = f"{name} light"
    made = art_twin(project, slots, tag, "additive")["twins"]
    ab = AnimBuilder(sk, animation, replace=False)
    skin = sk.skin()
    alpha = lambda a: f"{col}{max(0, min(255, round(a * 255))):02X}"  # noqa: E731

    for src, tw in zip(slots, made):
        names = list(skin.attachments.get(tw, {}))
        if not names:
            continue
        att = sk.slot(src).attachment or names[0]
        if start > 0:
            ab.slot_attachment(tw, [(0.0, None), (r(start), att), (r(end), None)])
        else:
            ab.slot_attachment(tw, [(0.0, att), (r(end), None)])
        ab.slot_color(tw, [
            (r(start), alpha(0.0)),
            (r(peak), alpha(gain)),
            (r(fall), alpha(gain * 0.92)),
            (r(end), alpha(0.0)),
        ], "quad_out")

    return {
        "slots": made,
        "source_slots": list(slots),
        "color": col,
        "strength": gain,
        "start": r(start),
        "end": r(end),
        "kind": "additive_surface_response",
    }


def qa_premium(project: Project, animation: str = "", subject_slots: list[str] | None = None) -> dict[str, Any]:
    """Heuristic art-direction QA for FX. This is a lint pass, not a beauty oracle."""
    sk = project.data
    if animation and animation not in sk.animations:
        raise ValueError(f"animation {animation!r} not found")
    anims = [animation] if animation else list(sk.animations)
    fx_slots = [s for s in sk.slots if s.name.startswith("fx_") or " light" in s.name]
    relit = [s.name for s in sk.slots if " light" in s.name]
    additive = sum(1 for s in fx_slots if s.blend == "additive")
    normal = sum(1 for s in fx_slots if s.blend == "normal")

    depth_counts = {k: 0 for k in ("back", "subject", "front", "lens")}
    for s in fx_slots:
        d = depth_class(token=s.name, blend=s.blend)
        depth_counts[d] += 1

    events = []
    for a in anims:
        events += [e.name for e in sk.animations[a].events]
    event_variety = len(set(events))

    lighting = 92 if relit else (55 if subject_slots else 38)
    used_depths = sum(1 for v in depth_counts.values() if v)
    depth = min(100, 40 + used_depths * 15)
    hierarchy = min(100, 48 + min(event_variety, 6) * 8)
    material = min(100, 52 + (18 if additive and normal else 5) + min(20, len(fx_slots) // 3))
    density_penalty = max(0, len(fx_slots) - 45) * 2
    readability = max(25, 100 - density_penalty - max(0, additive - 32))
    score = round((lighting * 0.28 + depth * 0.20 + hierarchy * 0.20 + material * 0.14 + readability * 0.18))

    warnings: list[str] = []
    fixes: list[str] = []
    if subject_slots and not relit:
        warnings.append("no reactive lighting is keyed onto the subject art")
        fixes.append("pass relight_slots=[...] to the hero impact recipe")
    if additive > 24 and normal == 0:
        warnings.append("the FX stack is almost entirely additive; bright backgrounds can turn it into white soup")
        fixes.append("move smoke/dust/solid material to normal blend or lower intensity")
    if len(fx_slots) > 45:
        warnings.append(f"{len(fx_slots)} FX slots is visually and technically dense for a mobile hero moment")
        fixes.append("reduce secondary particle counts before reducing the hero flash/shock shape")
    if depth_counts["lens"] > 6:
        warnings.append("many lens-class layers compete with the actual effect")
        fixes.append("keep one hero flare/flash and let material layers carry the rest")
    if used_depths < 2 and len(fx_slots) >= 4:
        warnings.append("the effect reads mostly on one depth plane")
        fixes.append("separate ambient volume behind the subject from a few front particles")

    return {
        "score": max(0, min(100, score)),
        "animation": animation or "all",
        "fx_slots": len(fx_slots),
        "components": {
            "lighting_integration": lighting,
            "depth_separation": depth,
            "impact_hierarchy": hierarchy,
            "material_richness": material,
            "readability": readability,
        },
        "depth_counts": depth_counts,
        "blend_counts": {"additive": additive, "normal": normal},
        "reactive_light_slots": relit,
        "warnings": warnings,
        "fix": fixes,
        "note": "Heuristic art-direction QA; judge final look in preview/video, not from this score alone.",
    }
