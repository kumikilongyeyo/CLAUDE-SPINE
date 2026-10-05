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
