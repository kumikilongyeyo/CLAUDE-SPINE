"""Reference-footage capture and AE remix regression tests (no installed AE needed)."""
from __future__ import annotations

import asyncio
import json

import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_fx_memory as M


def make_footage(tmp_path, n=40, size=112):
    src = tmp_path / "video_frames"
    src.mkdir()
    yy, xx = np.mgrid[:size, :size]
    for i in range(n):
        arr = np.zeros((size, size, 4), np.uint8)
        if 3 <= i < n - 3:
            phase = (i - 3) / (n - 7)
            radius = 4 + 24 * np.sin(np.pi * phase)
            cx = size / 2 + 10 * phase
            area = (xx - cx) ** 2 + (yy - size/2) ** 2 < radius ** 2
            arr[area] = [255, 125, 40, 255]
        Image.fromarray(arr, mode="RGBA").save(src / f"hit_{i:04d}.png")
    return src


def test_capture_creates_persistent_motion_recipe_and_reference(tmp_path):
    src = make_footage(tmp_path)
    out = M.capture(str(src), str(tmp_path/"FX_LIBRARY"), "Flame Hit", fps=24)
    recipe = json.loads((tmp_path / "FX_LIBRARY" / "flame_hit" / "recipe.json").read_text())
    assert out["mask_mode"] == "alpha"
    assert out["event"] == "impact"
    assert (tmp_path / "FX_LIBRARY" / "flame_hit" / "reference.jpg").exists()
    assert recipe["schema"] == M.FORM
    assert len(recipe["keys"]) <= 44
    assert recipe["keys"][0]["t"] == 0.0
    assert recipe["keys"][-1]["t"] == 1.0
    assert recipe["analysis"]["peak_energy"] > 0
    assert recipe["analysis"]["peak_at"] > 0
    assert recipe["source"]["sampled_frames"] == 40


def test_remix_generates_nondestructive_editable_ae_script(tmp_path):
    captured = M.capture(str(make_footage(tmp_path)), str(tmp_path/"FX_LIBRARY"), "Heavy Punch")
    out = M.remix(captured["recipe"], str(tmp_path/"scripts"), strength=2.4,
                  style="anime", color="#2255ff", speed=1.4, canvas=1024,
                  spark_count=21, save_as=str(tmp_path / "hit.aep"))
    js = (tmp_path / "scripts" / "heavy_punch_anime.jsx").read_text()
    assert out["canvas"] == [1024, 1024]
    assert out["spark_count"] == 21
    assert "00_FX_CONTROLS" in js
    assert "Impact Strength" in js and "Global Scale" in js
    assert "02_CORE_reference_energy" in js
    assert "04_DISTORTION_rebuild_ring" in js
    assert "03_SECONDARY_spark_" in js
    assert "KeyframeInterpolationType.BEZIER" in js
    assert "app.project.save(" in js
    assert "__COMP__" not in js and "__PEAK__" not in js
    assert out["layers"] == 25  # 3 visual layers, 21 sparks, one control


def test_mask_mode_no_background_warns_and_invalid_options_rejected(tmp_path):
    src = make_footage(tmp_path)
    with pytest.raises(ValueError, match="mask_mode"):
        M.capture(str(src), str(tmp_path/"lib"), "nope", mask_mode="guess")
    with pytest.raises(ValueError, match="max_frames"):
        M.capture(str(src), str(tmp_path/"lib"), "nope", max_frames=0)
    cap = M.capture(str(src), str(tmp_path/"lib"), "nope", mask_mode="none")
    assert cap["warnings"]
    with pytest.raises(ValueError, match="strength"):
        M.remix(cap["recipe"], str(tmp_path/"s"), strength=7)
    with pytest.raises(ValueError, match="color"):
        M.remix(cap["recipe"], str(tmp_path/"s"), color="not-a-hex")
    with pytest.raises(ValueError, match="canvas"):
        M.remix(cap["recipe"], str(tmp_path/"s"), canvas=10)


def test_capture_subsamples_entire_sequence_and_accepts_large_sources(tmp_path):
    src = make_footage(tmp_path, n=55, size=300)
    result = M.capture(str(src), str(tmp_path/"lib"), "sample", fps=30, max_frames=16)
    recipe = json.loads((tmp_path/"lib"/"sample"/"recipe.json").read_text())
    assert recipe["source"]["sampled_frames"] == 16
    assert recipe["source"]["preview_size"] == [256,256]
    assert recipe["analysis"]["duration"] == pytest.approx(54/30, abs=.01)
    assert (tmp_path/"lib"/"sample"/"reference.jpg").exists()


def test_mcp_tools_are_registered(tmp_path):
    from claude_spine.server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"ae_fx_capture", "ae_fx_remix"} <= names
