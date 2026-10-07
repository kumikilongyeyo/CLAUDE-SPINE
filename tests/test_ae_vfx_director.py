"""AE VFX director: planning, self-review and optimized AE -> Spine import."""
from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_vfx_director as D


def _frames(path, count=36, size=320):
    path.mkdir(parents=True, exist_ok=True)
    yy, xx = np.mgrid[0:size, 0:size]
    for i in range(count):
        a = np.zeros((size, size), np.float32)
        if 3 <= i < count - 3:
            t = (i - 3) / max(1, count - 7)
            radius = 18 + 70 * np.sin(np.pi * t)
            mask = (xx - size / 2) ** 2 + (yy - size / 2) ** 2 <= radius ** 2
            a[mask] = 0.85
        rgb = np.dstack([np.ones_like(a), np.full_like(a, 0.45), np.full_like(a, 0.08)])
        rgba = np.dstack([rgb, a])
        Image.fromarray(np.round(rgba * 255).astype(np.uint8), "RGBA").save(path / f"f_{i:05d}.png")
    return path


def test_plan_has_compressed_impact_and_clean_comp_structure():
    p = D.plan("heavy fire punch", event="fire_hit", style="realistic", fps=30, target="mobile_feature")
    assert p["comp_structure"] == [
        "00_CONTROLS", "01_SOURCE", "02_CORE", "03_SECONDARY",
        "04_DISTORTION", "05_LIGHTING", "06_ATMOSPHERE", "07_FINISH",
    ]
    assert p["timing_rules"]["avoid_even_spacing"] is True
    assert p["beats"]["impact_peak"][1] - p["beats"]["impact_peak"][0] < p["beats"]["residual_decay"][1] - p["beats"]["residual_decay"][0]
    assert any(x["role"] == "fire_relight" for x in p["layers"])
    assert p["handoff"]["max_size"] == 256
    assert p["handoff"]["max_frames"] <= 26


def test_styles_change_direction_without_changing_event_semantics():
    stylized = D.plan(event="impact", style="stylized")
    realistic = D.plan(event="impact", style="realistic")
    assert [x["role"] for x in stylized["layers"]] == [x["role"] for x in realistic["layers"]]
    assert stylized["duration"] < realistic["duration"]
    assert stylized["look_rules"]["bloom_amount"] > realistic["look_rules"]["bloom_amount"]
    assert stylized["look_rules"]["texture_amount"] < realistic["look_rules"]["texture_amount"]


def test_review_subtracts_before_adding_when_cluttered():
    out = D.review({
        "readability": 6.5,
        "impact": 8.0,
        "depth": 7.0,
        "lighting_integration": 7.0,
        "motion_flow": 7.5,
        "texture_quality": 8.0,
        "timing": 7.0,
        "clutter": 6.0,
    }, style="premium")
    assert not out["pass"]
    assert out["metrics"]["clarity"] == pytest.approx(4.0)
    assert out["actions"][0].startswith("Remove 20-35%")
    assert "subtraction" in out["anti_soup_rule"].lower()


def test_handoff_budget_scales_by_target():
    symbol = D.handoff_policy("mobile_symbol", "impact", "premium")
    hero = D.handoff_policy("mobile_hero", "impact", "premium")
    desktop = D.handoff_policy("desktop_preview", "impact", "premium")
    assert symbol["max_size"] < hero["max_size"] < desktop["max_size"]
    assert symbol["max_frames"] <= hero["max_frames"] <= desktop["max_frames"]
    assert symbol["reuse_frames_for_copies"] is True


def test_optimized_import_trims_downsizes_and_caps_frames(symbol, tmp_path):
    frames = _frames(tmp_path / "frames")
    res = D.import_optimized(
        symbol, "directed_hit", frames_dir=str(frames), fps=30,
        event="impact", style="premium", target="mobile_symbol",
    )
    assert res["trimmed"] == [3, 32]
    assert res["frames_out"] <= 20
    assert max(res["image_size"]) == 192
    assert res["director"]["optimized"] is True
    assert res["director"]["policy"]["target"] == "mobile_symbol"


def test_explicit_import_budget_overrides_director_defaults(symbol, tmp_path):
    frames = _frames(tmp_path / "frames2", count=24, size=160)
    res = D.import_optimized(
        symbol, "manual_budget", frames_dir=str(frames), fps=24,
        event="impact", target="mobile_symbol", max_size=96, max_frames=7, feather=0.0,
    )
    assert res["frames_out"] <= 7
    assert max(res["image_size"]) == 96


def test_mcp_tools_are_registered_and_callable(symbol, tmp_path):
    from claude_spine.server import mcp

    async def call(name, **args):
        res = await mcp.call_tool(name, args)
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"ae_vfx_plan", "ae_vfx_review", "ae_vfx_to_spine"} <= names

    plan = asyncio.run(call("ae_vfx_plan", brief="electric scatter hit", event="electric_hit", style="anime"))
    assert plan["event"] == "electric_hit" and plan["style"] == "anime"

    frames = _frames(tmp_path / "frames3", count=18, size=128)
    imported = asyncio.run(call(
        "ae_vfx_to_spine", project=str(symbol.path), name="mcp_hit",
        frames_dir=str(frames), fps=24, event="impact", style="premium", target="mobile_symbol",
    ))
    assert imported["director"]["optimized"] is True
    assert "validation_errors" not in imported
