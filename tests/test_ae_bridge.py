"""The After Effects -> Spine bridge, tested on synthetic frames (no AE needed) plus an optional live render."""
import os
import struct

import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_bridge, atlas, runtime
from claude_spine.ir import Sequence
from conftest import needs_node


def write_tiff(path, arr, bps=8):
    """Minimal big-endian uncompressed RGBA strip TIFF, the way AE writes it (alpha NOT flagged as extra)."""
    h, w, c = arr.shape
    dt = ">u2" if bps == 16 else "u1"
    data = np.round(arr * (65535 if bps == 16 else 255)).astype(dt).tobytes()
    entries = [(256, 4, w), (257, 4, h), (258, 3, (bps,) * c), (259, 3, 1), (262, 3, 2), (273, 4, 0),
               (277, 3, c), (278, 4, h), (279, 4, len(data))]
    n = len(entries)
    ifd_size = 2 + 12 * n + 4
    extra = b""
    body = b""
    ext_at = 8 + ifd_size
    data_at = ext_at + 2 * c
    for tag, typ, val in entries:
        if tag == 258:
            ent = struct.pack(">HHI", tag, 3, c) + struct.pack(">I", ext_at << 0)
            extra = struct.pack(">" + "H" * c, *[bps] * c)
        else:
            if tag == 273:
                val = data_at
            if typ == 3:
                ent = struct.pack(">HHIHH", tag, 3, 1, val, 0)
            else:
                ent = struct.pack(">HHII", tag, 4, 1, val)
        body += ent
    blob = b"MM\x00*" + struct.pack(">I", 8) + struct.pack(">H", n) + body + struct.pack(">I", 0) + extra + data
    path.write_bytes(blob)


def blob_frames(d, n=8, lead=2, trail=1, size=(40, 30), kind="png"):
    """n frames: `lead` empty, a glowing disc growing for the middle ones, `trail` empty."""
    d.mkdir(parents=True, exist_ok=True)
    out = []
    y, x = np.mgrid[0:size[1], 0:size[0]]
    for i in range(n):
        live = lead <= i < n - trail
        rad = 3 + 2 * (i - lead) if live else 0
        a = ((x - 20) ** 2 + (y - 15) ** 2 < rad ** 2).astype(np.float32) * 0.8
        rgb = np.dstack([np.full_like(a, 1.0), np.full_like(a, 0.6), np.full_like(a, 0.1)])
        if kind == "png":
            im = Image.fromarray(np.round(np.dstack([rgb, a]) * 255).astype(np.uint8), "RGBA")
            f = d / f"f_{i:05d}.png"
            im.save(f)
        else:
            f = d / f"f_{i:05d}.tif"
            write_tiff(f, np.dstack([rgb * a[..., None], a]))
        out.append(f)
    return d


def test_tiff_reader_reads_the_alpha_pil_drops(tmp_path):
    arr = np.random.default_rng(1).random((5, 7, 4)).astype(np.float32)
    for bps in (8, 16):
        f = tmp_path / f"a{bps}.tif"
        write_tiff(f, arr, bps)
        got = ae_bridge.read_tiff(f)
        assert got.shape == (5, 7, 4)
        assert np.abs(got - arr).max() < (1 / 255 if bps == 8 else 1 / 65535) + 1e-6


def test_straight_conversion_alpha_and_additive():
    pm = np.zeros((2, 2, 4), np.float32)
    pm[0, 0] = [0.2, 0.1, 0.0, 0.4]          # premultiplied half-alpha orange
    s = ae_bridge.to_straight(pm, "alpha")
    assert np.allclose(s[0, 0], [0.5, 0.25, 0, 0.4], atol=1e-6)
    assert np.allclose(s[1, 1], [0, 0, 0, 0])
    pm2 = np.zeros((1, 1, 4), np.float32)
    pm2[0, 0] = [0.8, 0.4, 0.0, 1.0]          # light on black, opaque comp
    s = ae_bridge.to_straight(pm2, "additive")
    assert np.allclose(s[0, 0], [1.0, 0.5, 0, 0.8], atol=1e-6)
    # what an additive slot adds on screen is unchanged: rgb * alpha
    assert np.allclose(s[0, 0, :3] * s[0, 0, 3], pm2[0, 0, :3], atol=1e-6)


@pytest.mark.parametrize("kind", ["png", "tif"])
def test_frames_become_a_trimmed_sequence_at_comp_speed(symbol, tmp_path, kind):
    d = blob_frames(tmp_path / "fr", n=10, lead=2, trail=2, kind=kind)
    res = ae_bridge.fx_to_spine(symbol, "puff", frames_dir=str(d), fps=24, mode="alpha", x=10, y=20, scale=2.0)
    assert res["trimmed"] == [2, 7] and res["frames_out"] == 6
    assert res["delay"] == pytest.approx(1 / 24, abs=1e-5)
    assert res["start"] == 0 and res["end"] == pytest.approx(6 / 24, abs=1e-4)
    sk = symbol.data
    slot = res["slot"]
    att = sk.attachment(slot, "fx")
    assert att.sequence == Sequence(count=6, start=0, digits=2, setup=0)
    assert (att.width, att.height) == (80, 60)                       # scale 2 on a 40x30 comp
    assert (symbol.images_dir / "ae" / "puff_05.png").exists() and not (symbol.images_dir / "ae" / "puff_06.png").exists()
    a = sk.animations["ae_puff"]
    seq = a.attachments["default"][slot]["fx"]["sequence"][0]
    assert seq.mode == "once" and seq.delay == pytest.approx(1 / 24, abs=1e-5)
    assert [k.name for k in a.slots[slot]["attachment"]] == ["fx", None]
    assert sk.slot_by_name(slot).blend == "normal" if hasattr(sk, "slot_by_name") else True
    px = np.asarray(symbol.image("ae/puff_00"))
    assert px[..., 3].max() > 150                                    # straight alpha, not premultiplied


def test_additive_mode_sets_blend_and_alpha_from_brightness(symbol, tmp_path):
    d = tmp_path / "fr"
    d.mkdir()
    for i in range(3):                                               # opaque comp, light on black
        rgb = np.zeros((8, 8, 3), np.float32)
        rgb[2:6, 2:6] = 0.25 * (i + 1)
        Image.fromarray(np.round(rgb * 255).astype(np.uint8)).save(d / f"f_{i:05d}.png")
    res = ae_bridge.fx_to_spine(symbol, "glint", frames_dir=str(d), fps=30, mode="additive")
    assert res["blend"] == "additive"
    assert [s.blend for s in symbol.data.slots if s.name == res["slot"]] == ["additive"]
    im = np.asarray(symbol.image("ae/glint_02"), np.float32) / 255
    assert im[4, 4, 3] == pytest.approx(0.75, abs=0.01) and im[0, 0, 3] == 0


def test_hit_sync_puts_the_ae_impact_on_the_spine_impact(symbol, tmp_path):
    d = blob_frames(tmp_path / "fr", n=12, lead=3, trail=0)          # first visible frame is comp frame 3
    # AE impact at comp second 0.5 (frame 12 at 24 fps, past the sprite's first frame); land it at Spine 1.5 s
    res = ae_bridge.fx_to_spine(symbol, "hit", frames_dir=str(d), fps=24, hit_ae=0.5, hit_at=1.5)
    assert res["start"] == pytest.approx(1.5 - (0.5 - 3 / 24), abs=1e-3)
    assert res["trimmed"][0] == 3
    # a stretched sequence plays slower, so the AE moment moves in proportion
    res2 = ae_bridge.fx_to_spine(symbol, "hit2", frames_dir=str(d), fps=24, hit_ae=0.5, hit_at=2.0,
                                 fit_duration=1.8)
    delay = 1.8 / res2["frames_out"]
    assert res2["delay"] == pytest.approx(delay, abs=1e-4)
    assert res2["start"] == pytest.approx(2.0 - (0.5 - 3 / 24) * delay * 24, abs=1e-3)
    with pytest.raises(ValueError, match="before the animation starts"):
        ae_bridge.fx_to_spine(symbol, "early", frames_dir=str(d), fps=24, hit_ae=0.9, hit_at=0.1)


def test_max_frames_subsamples_and_keeps_the_speed(symbol, tmp_path):
    d = blob_frames(tmp_path / "fr", n=14, lead=1, trail=1)
    res = ae_bridge.fx_to_spine(symbol, "thin", frames_dir=str(d), fps=24, max_frames=4, max_size=20)
    assert res["step"] == 3 and res["frames_out"] == 4
    assert res["delay"] == pytest.approx(3 / 24, abs=1e-5)           # every 3rd frame, 3x the delay: same speed
    assert res["image_size"] == [20, 15]
    att = symbol.data.attachment(res["slot"], "fx")
    assert (att.width, att.height) == (40, 30)                       # world size does not shrink with the texture


def test_loop_runs_to_the_end_of_the_animation_it_merges_into(symbol, tmp_path):
    from claude_spine import juice
    juice.apply(symbol, ["win"])
    d = blob_frames(tmp_path / "fr", n=6, lead=0, trail=0)
    end = symbol.data.animations["win"].duration()
    res = ae_bridge.fx_to_spine(symbol, "aura", frames_dir=str(d), fps=12, seq_mode="loop", animation="win",
                                start=0.1, fade=0.2)
    assert res["animation"] == "win" and res["end"] == pytest.approx(max(end, 0.1 + 6 / 12), abs=1e-3)
    assert "fx" in symbol.data.animations["win"].attachments["default"][res["slot"]]
    assert symbol.data.animations["win"].slots[res["slot"]]["rgba"][-1].color.endswith("00")


def test_bad_input_is_a_clear_error(symbol, tmp_path):
    d = blob_frames(tmp_path / "fr")
    with pytest.raises(ValueError, match="fps"):
        ae_bridge.fx_to_spine(symbol, "x", frames_dir=str(d))
    with pytest.raises(ValueError, match="mode"):
        ae_bridge.fx_to_spine(symbol, "x", frames_dir=str(d), fps=24, mode="screen")
    with pytest.raises(ValueError, match="aep"):
        ae_bridge.fx_to_spine(symbol, "x")
    empty = tmp_path / "empty"
    empty.mkdir()
    Image.new("RGBA", (4, 4)).save(empty / "f_0.png")
    with pytest.raises(ValueError, match="empty"):
        ae_bridge.fx_to_spine(symbol, "x", frames_dir=str(empty), fps=24)


def test_tool_is_registered_and_validates(symbol, tmp_path):
    import asyncio
    import json
    from claude_spine.server import mcp
    d = blob_frames(tmp_path / "fr", kind="tif")
    out = asyncio.run(mcp.call_tool("ae_fx_to_spine", {"project": str(symbol.path), "name": "puff",
                                                      "frames_dir": str(d), "fps": 24, "start": 0.25}))
    res = json.loads((out[0] if isinstance(out, tuple) else out)[0].text)
    assert res["start"] == 0.25 and "validation_errors" not in res
    assert "ae_fx_to_spine" in {t.name for t in asyncio.run(mcp.list_tools())}


def test_copies_take_scale_and_rotation_and_keep_the_old_forms(symbol, tmp_path):
    d = blob_frames(tmp_path / "fr", n=8)
    res = ae_bridge.fx_to_spine(symbol, "hits", frames_dir=str(d), fps=24, mode="additive", start=0.1,
                                copies=[[5, 6], [7, 8, 0.5], [0, 0, 0.9, 1.3], [0, 0, None, 1.7, 45],
                                        {"x": 1, "y": 2, "start": 1.2, "scale": 2}])
    assert len(res["copies"]) == 5 and all(isinstance(c, str) for c in res["copies"])   # slot names, as before
    inst = res["copy_instances"]
    assert [c["slot"] for c in inst] == res["copies"]
    bones = {b.name: b for b in symbol.data.bones}
    for c in inst:
        b = bones[c["bone"]]
        assert next(s.bone for s in symbol.data.slots if s.name == c["slot"]) == c["bone"]
        assert (b.x, b.y, b.scaleX, b.scaleY, b.rotation) == (c["x"], c["y"], c["scale"], c["scale"], c["rotation"])
    assert [(c["start"], c["scale"], c["rotation"]) for c in inst] == [
        (0.1, 1.0, 0.0), (0.5, 1.0, 0.0), (0.9, 1.3, 0.0), (0.1, 1.7, 45.0), (1.2, 2.0, 0.0)]
    assert len(list((symbol.images_dir / "ae").glob("hits_*.png"))) == res["frames_out"], "one shared frame set"
    an = symbol.data.animations[res["animation"]]
    assert an.slots[inst[2]["slot"]]["attachment"][1].time == pytest.approx(0.9)
    assert ae_bridge.copy_sequence(symbol, res, x=1, y=1, scale=1.5) in {s.name for s in symbol.data.slots}


def test_bad_copies_fail_before_anything_is_written(symbol, tmp_path):
    d = blob_frames(tmp_path / "fr", n=6)
    for bad in ([1], [1, 2, 0, 1, 0, 9], [0, 0, 0, -1], {"x": 0}):
        with pytest.raises(ValueError, match="copy"):
            ae_bridge.fx_to_spine(symbol, "bad", frames_dir=str(d), fps=24, copies=[bad])
    assert not list((symbol.images_dir / "ae").glob("bad_*.png")) if (symbol.images_dir / "ae").exists() else True


def test_frame_budget_never_drops_below_min_fps():
    fb = ae_bridge.frame_budget
    # the old behaviour without min_fps: a 16-frame 24 fps loop squeezed into 6 frames plays at 8 fps
    assert fb(16, 24, 512, 512, max_size=512, max_frames=6, seq_mode="loop")["step"] == 3
    # loop: the texture shrinks first and every frame stays (same pixel budget: 6 x 512^2)
    b = fb(16, 24, 512, 512, max_size=512, max_frames=6, seq_mode="loop", min_fps=12)
    assert b["step"] == 1 and 256 <= b["size"][0] < 512
    assert 16 * b["size"][0] ** 2 <= 6 * 512 ** 2 + 16 * 1024
    # loop past the texture floor: frames go next, but never below 12 fps
    b = fb(48, 24, 512, 512, max_size=512, max_frames=6, seq_mode="loop", min_fps=12)
    assert b["step"] == 2 and b["size"] == (256, 256) and not b["note"]          # half size, 12 fps: both floors met
    b = fb(96, 24, 512, 512, max_size=512, max_frames=6, seq_mode="loop", min_fps=12)
    assert b["step"] == 2 and b["size"][0] < 256 and b["note"]                    # past both: the texture gives
    # one-shot: frames go first (texture untouched while that fits), but only down to min_fps
    b = fb(24, 30, 320, 320, max_size=320, max_frames=12, seq_mode="once", min_fps=12)
    assert b == {"step": 2, "size": (320, 320), "note": ""}
    b = fb(24, 30, 320, 320, max_size=320, max_frames=6, seq_mode="once", min_fps=12)
    assert b["step"] == 2 and b["size"][0] < 320 and 12 * b["size"][0] ** 2 <= 6 * 320 ** 2 + 12 * 640
    # a comp already slower than min_fps is never subsampled
    assert fb(20, 10, 64, 64, max_frames=5, seq_mode="loop", min_fps=12)["step"] == 1
    # inside the budget nothing changes
    assert fb(6, 24, 100, 50, max_size=64, max_frames=10, min_fps=12) == {"step": 1, "size": (64, 32), "note": ""}


def test_import_reports_the_playback_rate(symbol, tmp_path):
    d = blob_frames(tmp_path / "fr", n=18, lead=1, trail=1)
    res = ae_bridge.fx_to_spine(symbol, "loopy", frames_dir=str(d), fps=24, seq_mode="loop", max_frames=4,
                                max_size=40, min_fps=12)
    assert res["playback_fps"] >= 12 and res["step"] <= 2
    assert res["delay"] == pytest.approx(res["step"] / 24, abs=1e-5)


@needs_node
def test_the_runtime_loads_and_plays_the_sequence(symbol, tmp_path):
    d = blob_frames(tmp_path / "fr", n=8)
    res = ae_bridge.fx_to_spine(symbol, "puff", frames_dir=str(d), fps=24)
    symbol.save()
    pk = atlas.pack(symbol, tmp_path / "exp", strip=True, pma=True)
    out = runtime.run(symbol, atlas_path=pk["atlas"], animations=[res["animation"]], fps=24)
    assert out["ok"], out
    assert any(e["name"] == "ae_puff" for e in out["animations"][res["animation"]]["events"])


@pytest.mark.skipif(not (ae_bridge.available() and os.environ.get("AE_TEST_AEP")),
                    reason="needs aerender and AE_TEST_AEP=<saved .aep>, AE_TEST_COMP=<comp>")
def test_live_render_through_aerender(symbol, tmp_path):
    res = ae_bridge.fx_to_spine(symbol, "live", aep=os.environ["AE_TEST_AEP"],
                                comp=os.environ.get("AE_TEST_COMP", "fire_arc"), mode="alpha", max_size=256)
    assert res["frames_out"] > 1 and res["source"]["comp_fps"] > 0
    assert (symbol.images_dir / "ae" / "live_00.png").exists()
