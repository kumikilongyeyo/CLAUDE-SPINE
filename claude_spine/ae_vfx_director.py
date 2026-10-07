"""AE VFX director and optimized AE -> Spine handoff.

This module adds the art-direction layer missing from raw After Effects automation:
it decomposes a brief into readable VFX layers, enforces impact timing, scores
rendered results, and chooses conservative frame/texture budgets for Spine.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from . import ae_bridge
from .project import Project


STYLES: dict[str, dict[str, Any]] = {
    "stylized": {
        "summary": "Chunky, graphic and fast; silhouette and value separation beat micro-detail.",
        "time": 0.88, "particles": 0.72, "texture": 0.62, "bloom": 0.72,
        "distortion": 0.62, "light_response": 0.62, "overshoot": 1.15,
    },
    "premium": {
        "summary": "Polished slot-game balance: layered and rich, but controlled at mobile size.",
        "time": 1.00, "particles": 0.90, "texture": 0.82, "bloom": 0.58,
        "distortion": 0.72, "light_response": 0.82, "overshoot": 1.00,
    },
    "realistic": {
        "summary": "Physically motivated light, restrained bloom, richer material texture and longer decay.",
        "time": 1.10, "particles": 0.78, "texture": 1.00, "bloom": 0.42,
        "distortion": 0.86, "light_response": 1.00, "overshoot": 0.72,
    },
    "anime": {
        "summary": "Directional impact frames, sharp value groups, speed energy and deliberate smears.",
        "time": 0.84, "particles": 0.72, "texture": 0.60, "bloom": 0.62,
        "distortion": 0.82, "light_response": 0.72, "overshoot": 1.28,
    },
}

EVENTS: dict[str, dict[str, Any]] = {
    "impact": {
        "duration": 0.72,
        "layers": [
            ("02_CORE", "white_hot_core", "glow_pulse", "additive", 1.00),
            ("03_SECONDARY", "debris_sparks", "burst", "additive", 0.78),
            ("04_DISTORTION", "shockwave", "shockwave", "additive", 0.78),
            ("05_LIGHTING", "impact_relight", "lens_flare", "additive", 0.58),
            ("06_ATMOSPHERE", "residual_haze", "smoke_puff", "normal", 0.52),
        ],
    },
    "fire_hit": {
        "duration": 0.92,
        "layers": [
            ("02_CORE", "fire_body", "fire_aura", "normal", 1.00),
            ("02_CORE", "hot_core", "glow_pulse", "additive", 0.88),
            ("03_SECONDARY", "embers_sparks", "burst", "additive", 0.72),
            ("04_DISTORTION", "heat_refraction", "heat_shimmer", "normal", 0.56),
            ("05_LIGHTING", "fire_relight", "lens_flare", "additive", 0.48),
            ("06_ATMOSPHERE", "smoke_decay", "smoke_puff", "normal", 0.62),
        ],
    },
    "electric_hit": {
        "duration": 0.66,
        "layers": [
            ("02_CORE", "main_arc", "lightning", "additive", 1.00),
            ("03_SECONDARY", "branch_arcs", "lightning", "additive", 0.72),
            ("03_SECONDARY", "ion_sparks", "burst", "additive", 0.66),
            ("05_LIGHTING", "flash_relight", "glow_pulse", "additive", 0.58),
            ("07_FINISH", "lens_kick", "lens_flare", "additive", 0.36),
        ],
    },
    "magic_reveal": {
        "duration": 1.35,
        "layers": [
            ("01_SOURCE", "rune_portal", "portal_ring", "additive", 0.82),
            ("02_CORE", "reveal_core", "glow_pulse", "additive", 0.92),
            ("03_SECONDARY", "sparkles", "sparkle", "additive", 0.58),
            ("05_LIGHTING", "subject_relight", "god_rays", "additive", 0.42),
            ("06_ATMOSPHERE", "haze", "smoke_haze", "normal", 0.44),
            ("07_FINISH", "flare", "lens_flare", "additive", 0.30),
        ],
    },
    "win_burst": {
        "duration": 1.10,
        "layers": [
            ("02_CORE", "win_core", "glow_pulse", "additive", 0.88),
            ("03_SECONDARY", "radial_sparks", "burst", "additive", 0.80),
            ("04_DISTORTION", "ring", "shockwave", "additive", 0.56),
            ("03_SECONDARY", "glitter", "sparkle", "additive", 0.52),
            ("07_FINISH", "flare", "lens_flare", "additive", 0.34),
        ],
    },
    "ambient": {
        "duration": 2.40,
        "layers": [
            ("00_BACK", "atmosphere", "fog_roll", "normal", 0.42),
            ("04_DISTORTION", "air_refraction", "heat_shimmer", "normal", 0.28),
            ("05_LIGHTING", "volumetric_light", "god_rays", "additive", 0.26),
        ],
    },
}

HANDOFF_PROFILES: dict[str, dict[str, Any]] = {
    "mobile_symbol": {
        "max_size": 192, "base_frames": 16, "hard_frames": 20, "export_fps": 20,
        "feather": 0.035, "budget_rgba_mb": 2.5,
    },
    "mobile_feature": {
        "max_size": 256, "base_frames": 20, "hard_frames": 26, "export_fps": 24,
        "feather": 0.035, "budget_rgba_mb": 6.5,
    },
    "mobile_hero": {
        "max_size": 384, "base_frames": 24, "hard_frames": 32, "export_fps": 24,
        "feather": 0.030, "budget_rgba_mb": 16.0,
    },
    "desktop_preview": {
        "max_size": 768, "base_frames": 45, "hard_frames": 60, "export_fps": 30,
        "feather": 0.020, "budget_rgba_mb": 120.0,
    },
}

REVIEW_WEIGHTS = {
    "readability": 1.25,
    "impact": 1.15,
    "depth": 1.00,
    "lighting_integration": 1.20,
    "motion_flow": 1.00,
    "texture_quality": 0.85,
    "timing": 1.15,
    "clarity": 1.20,
}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _require(kind: str, table: dict[str, Any], value: str) -> dict[str, Any]:
    if value not in table:
        raise ValueError(f"unknown {kind} {value!r}; choose one of {sorted(table)}")
    return deepcopy(table[value])


def listing() -> dict[str, Any]:
    return {
        "events": sorted(EVENTS),
        "styles": sorted(STYLES),
        "targets": sorted(HANDOFF_PROFILES),
        "rule": "Use AE for real noise/volume; keep simple moving light, shake and repeated cheap accents native Spine.",
    }


def handoff_policy(target: str = "mobile_feature", event: str = "impact", style: str = "realistic",
                   intensity: float = 1.0, duration: float = 0.0) -> dict[str, Any]:
    """Choose a mobile-aware sequence budget before importing AE frames into Spine."""
    profile = _require("handoff target", HANDOFF_PROFILES, target)
    event_cfg = _require("event", EVENTS, event)
    style_cfg = _require("style", STYLES, style)
    intensity = _clamp(intensity, 0.25, 2.0)
    seconds = duration if duration > 0 else event_cfg["duration"] * style_cfg["time"]
    ideal = max(2, round(seconds * profile["export_fps"]))
    max_frames = min(profile["hard_frames"], max(profile["base_frames"], ideal))
    if event == "ambient":
        max_frames = min(profile["hard_frames"], max(12, round(max_frames * 0.78)))
    if intensity < 0.7:
        max_frames = max(8, round(max_frames * 0.82))
    bytes_per_frame = profile["max_size"] * profile["max_size"] * 4
    memory_frames = max(2, int(profile["budget_rgba_mb"] * 1024 * 1024 // bytes_per_frame))
    requested_frames = max_frames
    max_frames = min(max_frames, memory_frames)
    raw_mb = bytes_per_frame * max_frames / (1024 * 1024)
    return {
        "target": target,
        "max_size": profile["max_size"],
        "max_frames": max_frames,
        "feather": profile["feather"],
        "trim": True,
        "preferred_export_fps": profile["export_fps"],
        "raw_rgba_upper_mb": round(raw_mb, 2),
        "budget_rgba_mb": profile["budget_rgba_mb"],
        "budget_limited": max_frames < requested_frames,
        "reuse_frames_for_copies": True,
        "preserve_world_size_when_downscaled": True,
        "notes": [
            "Trim empty head/tail frames before atlas packing.",
            "Subsample only after timing is locked; ae_bridge preserves playback speed.",
            "Reuse one imported sequence with copies= for repeated instances.",
            "Keep simple glows/rings/shake native Spine unless the effect needs real noise or refraction.",
            "If memory is high, reduce texture size before removing the core impact frames.",
        ],
    }


def _beat_frames(fps: float, total_seconds: float, event: str) -> dict[str, list[int]]:
    total = max(4, round(total_seconds * fps))
    if event == "ambient":
        return {
            "build": [0, round(total * 0.22)],
            "hold": [round(total * 0.22), round(total * 0.72)],
            "drift_decay": [round(total * 0.72), total],
        }
    impact = max(2, round(total * 0.24))
    peak = min(total, impact + max(2, round(total * 0.10)))
    fast = min(total, peak + max(3, round(total * 0.24)))
    return {
        "anticipation": [0, impact],
        "impact_peak": [impact, peak],
        "fast_decay": [peak, fast],
        "residual_decay": [fast, total],
    }


def plan(brief: str = "", event: str = "impact", style: str = "realistic", intensity: float = 1.0,
         fps: float = 30.0, duration: float = 0.0, target: str = "mobile_feature") -> dict[str, Any]:
    """Turn a creative brief into a VFX build plan that an AE MCP can execute."""
    if fps <= 0:
        raise ValueError("fps must be positive")
    if not event and not style:
        return listing()
    intensity = _clamp(intensity, 0.25, 2.0)
    event_cfg = _require("event", EVENTS, event)
    style_cfg = _require("style", STYLES, style)
    seconds = duration if duration > 0 else event_cfg["duration"] * style_cfg["time"]

    layers = []
    for group, role, template, blend, weight in event_cfg["layers"]:
        strength = _clamp(weight * intensity, 0.05, 1.6)
        if style == "realistic" and role in {"lens_kick", "flare", "sparkles", "glitter"}:
            strength *= 0.72
        if style == "anime" and role in {"white_hot_core", "win_core", "main_arc"}:
            strength *= 1.18
        layers.append({
            "group": group,
            "role": role,
            "template": template,
            "blend": blend,
            "relative_strength": round(_clamp(strength, 0.05, 1.6), 3),
        })

    return {
        "brief": brief,
        "event": event,
        "style": style,
        "style_summary": style_cfg["summary"],
        "duration": round(seconds, 4),
        "fps": fps,
        "beats": _beat_frames(fps, seconds, event),
        "comp_structure": [
            "00_CONTROLS", "01_SOURCE", "02_CORE", "03_SECONDARY",
            "04_DISTORTION", "05_LIGHTING", "06_ATMOSPHERE", "07_FINISH",
        ],
        "layers": layers,
        "timing_rules": {
            "principle": "anticipation -> compressed impact -> fast decay -> slower residual",
            "avoid_even_spacing": True,
            "impact_keys_clustered": True,
            "ease": "fast attack, controlled overshoot, monotone settle",
            "style_overshoot": style_cfg["overshoot"],
        },
        "look_rules": {
            "texture_amount": style_cfg["texture"],
            "bloom_amount": style_cfg["bloom"],
            "distortion_amount": style_cfg["distortion"],
            "environment_light_response": style_cfg["light_response"],
            "particle_density_scale": style_cfg["particles"],
            "rules": [
                "Light must visibly affect the subject or nearby surface instead of floating over it.",
                "Use a bright core plus softer volume; never solve impact with one giant blurred glow.",
                "Separate back / subject / front / lens depth planes.",
                "Texture belongs inside the effect body; noise should not become screen clutter.",
                "Remove decorative particles before adding more when readability drops.",
            ],
        },
        "handoff": handoff_policy(target, event, style, intensity, seconds),
        "review_targets": {
            "minimum_score": 8.0,
            "required": {
                "readability": 8.0, "impact": 8.0, "lighting_integration": 7.5,
                "timing": 8.0, "clarity": 8.0,
            },
            "judge_frames": ["end_of_anticipation", "impact_peak", "mid_decay", "final_residual"],
        },
    }


def review(metrics: dict[str, float], style: str = "realistic") -> dict[str, Any]:
    """Score a rendered AE effect and return the smallest useful revision list.

    Metrics are 0..10. Use clarity=10 for a clean read. For convenience callers
    may provide clutter instead; clarity is then interpreted as 10-clutter.
    """
    _require("style", STYLES, style)
    values = dict(metrics)
    if "clarity" not in values and "clutter" in values:
        values["clarity"] = 10.0 - float(values["clutter"])
    missing = [k for k in REVIEW_WEIGHTS if k not in values]
    if missing:
        raise ValueError(f"missing review metric(s): {missing}")
    clean: dict[str, float] = {}
    for key in REVIEW_WEIGHTS:
        clean[key] = _clamp(float(values[key]), 0.0, 10.0)
    denom = sum(REVIEW_WEIGHTS.values())
    score = sum(clean[k] * REVIEW_WEIGHTS[k] for k in REVIEW_WEIGHTS) / denom

    actions: list[str] = []
    if clean["clarity"] < 7.5:
        actions.append("Remove 20-35% of decorative particles/lens layers before adding anything.")
    if clean["readability"] < 8.0:
        actions.append("Strengthen the primary silhouette/value group and simplify competing detail.")
    if clean["impact"] < 8.0:
        actions.append("Compress more change into the impact window: brighter core, faster scale/energy change, then decay.")
    if clean["lighting_integration"] < 7.5:
        actions.append("Add or retime subject/environment relighting so the effect illuminates what it hits.")
    if clean["depth"] < 7.0:
        actions.append("Separate back/front atmosphere and vary scale/blur/parallax instead of stacking everything on one plane.")
    if clean["motion_flow"] < 7.5:
        actions.append("Align secondary motion with the force direction; remove particles moving against the event.")
    if clean["timing"] < 8.0:
        actions.append("Replace evenly spaced keys with anticipation, clustered impact keys, fast decay and a slower residual tail.")
    if clean["texture_quality"] < 7.0 and clean["clarity"] >= 7.5:
        actions.append("Add restrained material breakup inside the core/volume, not extra screen-space noise.")
    if not actions and score < 8.5:
        actions.append("Do a polish-only pass: tiny timing, exposure and edge-quality changes; do not add a new FX family.")

    return {
        "style": style,
        "score": round(score, 2),
        "pass": score >= 8.0 and clean["readability"] >= 8.0 and clean["clarity"] >= 8.0
                and clean["impact"] >= 8.0 and clean["timing"] >= 8.0
                and clean["lighting_integration"] >= 7.5,
        "metrics": clean,
        "actions": actions,
        "anti_soup_rule": "When clarity is low, subtraction comes before addition.",
    }


def import_optimized(project: Project, name: str, *, event: str = "impact", style: str = "realistic",
                     target: str = "mobile_feature", intensity: float = 1.0, duration: float = 0.0,
                     max_size: int = 0, max_frames: int = 0, feather: float = -1.0, **kwargs: Any) -> dict[str, Any]:
    """AE -> Spine using director defaults, while preserving explicit caller overrides."""
    policy = handoff_policy(target, event, style, intensity, duration)
    kwargs["max_size"] = max_size or policy["max_size"]
    kwargs["max_frames"] = max_frames or policy["max_frames"]
    kwargs["feather"] = policy["feather"] if feather < 0 else feather
    result = ae_bridge.fx_to_spine(project, name, **kwargs)
    result["director"] = {
        "event": event,
        "style": style,
        "target": target,
        "policy": policy,
        "optimized": True,
    }
    return result
