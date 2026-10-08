"""Reference-footage capture and AE remix regression tests (no installed AE needed)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_fx_memory as M
from claude_spine import ae_fx_visual_match as V


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


def test_saved_fx_are_searchable_for_later_reuse(tmp_path):
    src = make_footage(tmp_path)
    M.capture(str(src), str(tmp_path/"fx"), "Impact Fire", fps=24)
    assert M.library(str(tmp_path/"fx"), "ambient")["count"] == 0
    item = M.library(str(tmp_path/"fx"), "impact")["presets"][0]
    assert item["name"] == "Impact Fire"
    assert item["event"] == "impact"
    assert item["recipe"].endswith("recipe.json")


def test_mcp_tools_are_registered(tmp_path):
    from claude_spine.server import mcp
    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"ae_fx_capture", "ae_fx_library", "ae_fx_remix", "ae_fx_match"} <= names


def _alter_candidate(reference_dir, out_dir, scale=.65, dx=-9, dark=.65):
    out_dir.mkdir()
    for path in sorted(reference_dir.glob("*.png")):
        rgba = np.asarray(Image.open(path).convert("RGBA"), dtype=np.uint8)
        h, w = rgba.shape[:2]
        result = np.zeros_like(rgba)
        xs = np.arange(w)
        ys = np.arange(h)
        xx, yy = np.meshgrid(xs, ys)
        # Map destination to source around the center; compact and shift left.
        ux = np.round((xx - w/2 - dx)/scale + w/2).astype(int)
        uy = np.round((yy - h/2)/scale + h/2).astype(int)
        valid = (ux >= 0) & (ux < w) & (uy >= 0) & (uy < h)
        result[valid] = rgba[uy[valid], ux[valid]]
        result[..., :3] = np.round(result[..., :3].astype(np.float32)*dark).astype(np.uint8)
        Image.fromarray(result).save(out_dir/path.name)
    return out_dir


def test_frame_compare_is_exact_for_identical_source_and_writes_report(tmp_path):
    src = make_footage(tmp_path)
    cap = M.capture(str(src), str(tmp_path/"fx"), "known punch")
    report = V.compare(cap["recipe"], str(tmp_path/"review"),
                       candidate_frames=str(src), candidate_fps=24, max_frames=20)
    assert report["score"] > 99.9
    assert report["frames_compared"] == 20
    assert report["errors"]["visual_error"] < 0.001
    assert (tmp_path/"review"/"comparison_001.jpg").is_file()
    assert (tmp_path/"review"/"match_001.json").is_file()
    jsx = (tmp_path/"review"/"known_punch_match_002.jsx").read_text()
    assert "Turbulent Displace" in jsx
    assert "00_FX_CONTROLS" in jsx
    assert all(k in report["tuning"] for k in
               ("energy_gain","radius_gain","offset_x","time_shift","roughness"))


def test_frame_compare_detects_differences_and_creates_corrected_next_build(tmp_path):
    src = make_footage(tmp_path)
    candidate = _alter_candidate(src, tmp_path/"bad", scale=.62, dx=-11, dark=.47)
    cap = M.capture(str(src), str(tmp_path/"fx"), "fist impact")
    out = V.compare(cap["recipe"], str(tmp_path/"review"),
                    candidate_frames=str(candidate), candidate_fps=24, max_frames=35,
                    style="anime", strength=1.5, canvas=1024)
    assert out["score"] < 99
    assert out["errors"]["visual_error"] > .01
    assert out["errors"]["silhouette_iou"] < .9
    assert out["worst_frames"]
    assert out["next_aep"] is None
    assert out["tuning"]["radius_gain"] > 1.0
    assert out["tuning"]["offset_x"] > 0
    assert out["tuning"]["energy_gain"] > 1.0
    assert Path(out["next_jsx"]).is_file()
    js = Path(out["next_jsx"]).read_text()
    assert "__RING_GAIN__" not in js
    assert "Math.sqrt(energy[i])*25*" in js
    again = V.compare(cap["recipe"], str(tmp_path/"review"), candidate_frames=str(candidate),
                      candidate_fps=24, iteration=2, tuning=out["tuning"], max_frames=35)
    assert again["tuning"]["radius_gain"] > out["tuning"]["radius_gain"]
    assert Path(again["comparison"]).is_file()


def test_compare_rejects_missing_render_and_composite_without_plate(tmp_path):
    ref = make_footage(tmp_path)
    cap = M.capture(str(ref), str(tmp_path/"fx"), "punch")
    with pytest.raises(ValueError, match="exactly one"):
        V.compare(cap["recipe"], str(tmp_path/"review"))
    with pytest.raises(ValueError, match="candidate_fps"):
        V.compare(cap["recipe"], str(tmp_path/"review"), candidate_frames=str(ref))
    with pytest.raises(ValueError, match="comp"):
        V.compare(cap["recipe"], str(tmp_path/"review"), aep="fake.aep")
    with pytest.raises(ValueError, match="candidate_mode"):
        V.compare(cap["recipe"], str(tmp_path/"review"), candidate_frames=str(ref),
                  candidate_fps=24, candidate_mode="arbitrary")
    with pytest.raises(ValueError, match="unknown fit"):
        M.remix(cap["recipe"], str(tmp_path/"review"), fit={"bad_key": 10})


def test_speed_changed_render_matches_rescaled_reference_times(tmp_path):
    reference = make_footage(tmp_path)
    capture = M.capture(str(reference), str(tmp_path/"fx"), "fast")
    # Same source frames at 48fps are a precisely 2x faster edit of a 24fps reference.
    out = V.compare(capture["recipe"], str(tmp_path/"review"), candidate_frames=str(reference),
                    candidate_fps=48, speed=2, max_frames=40)
    assert out["score"] > 99.9
    assert out["matched_times"][-1] == pytest.approx(39/48, abs=.0001)


def test_ae_work_area_can_start_late_and_generates_named_next_project(tmp_path, monkeypatch):
    reference = make_footage(tmp_path)
    cap = M.capture(str(reference), str(tmp_path/"fx"), "nonzero")
    class StubRenderInfo:
        fps = 24
        start = 300
        frames = sorted(reference.glob("*.png"))
    monkeypatch.setattr(V.ae_bridge, "render_comp", lambda *a, **k: StubRenderInfo)
    out = V.compare(cap["recipe"], str(tmp_path/"review"),
                    aep=str(tmp_path/"simulated.aep"), comp="nonzero_premium", max_frames=40)
    assert out["score"] > 99.9
    assert out["next_aep"].endswith("nonzero_match_002.aep")
    jsx = Path(out["next_jsx"]).read_text()
    assert "app.project.save(new File(" in jsx
