import colorsys

import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_bridge, ae_tint, render, runtime, server
from conftest import needs_node


def ramp_frames(d, colours, n=6, size=(48, 32)):
    """n PNG frames of a disc whose colour runs through `colours` from rim to centre (straight RGBA)."""
    d.mkdir(parents=True, exist_ok=True)
    y, x = np.mgrid[0:size[1], 0:size[0]]
    r = np.hypot(x - size[0] / 2, y - size[1] / 2) / (size[1] / 2)
    stops = np.array(colours, np.float32)
    for i in range(n):
        t = np.clip(1 - r, 0, 1) ** 0.7                         # 0 at the rim, 1 in the centre
        pos = t * (len(stops) - 1)
        k = np.clip(pos.astype(int), 0, len(stops) - 2)
        f = (pos - k)[..., None]
        rgb = stops[k] * (1 - f) + stops[k + 1] * f
        a = (r < 1).astype(np.float32) * (0.5 + 0.08 * i)
        Image.fromarray(np.round(np.dstack([rgb, a]) * 255).astype(np.uint8), "RGBA").save(d / f"f_{i:05d}.png")
    return d


def hue_gap(c, tint):
    """Circular distance between the hue of colour c and of the hex tint (hue 0.9999 is red, like 0)."""
    d = abs(colorsys.rgb_to_hls(*c)[0] - colorsys.rgb_to_hls(*ae_tint.hex_rgb(tint))[0]) % 1.0
    return min(d, 1 - d)


BLUE_WHITE = [(0.05, 0.1, 0.9), (0.95, 0.98, 1.0)]                    # electric: one line in RGB
FIRE = [(0.5, 0.02, 0.0), (1.0, 0.45, 0.0), (1.0, 0.9, 0.2), (1.0, 1.0, 1.0)]   # a curve: two colours can't


def test_two_tone_render_is_stored_grey_and_coloured_by_the_slot(symbol, tmp_path):
    d = ramp_frames(tmp_path / "fr", BLUE_WHITE)
    res = ae_bridge.fx_to_spine(symbol, "zap", frames_dir=str(d), fps=24, mode="alpha", tintable=True)
    t = res["tint"]
    assert t["grade"] == "good" and t["error_mean"] < 3
    light, dark = ae_tint.hex_rgb(t["light"]), ae_tint.hex_rgb(t["dark"])
    assert light.min() > 0.85 and dark[2] > 0.7 and dark[0] < 0.2       # white core, blue rim
    px = np.asarray(symbol.image("ae/zap_02"), np.int16)
    vis = px[..., 3] > 0
    assert np.abs(px[..., 0] - px[..., 1])[vis].max() <= 1 and np.abs(px[..., 1] - px[..., 2])[vis].max() <= 1
    slot = next(s for s in symbol.data.slots if s.name == res["slot"])
    assert slot.color[:6] == t["light"] and slot.dark == t["dark"]
    # the slot colours rebuild the render: g * light + (1 - g) * dark ~ the original straight colour
    src = np.asarray(Image.open(d / "f_00002.png"), np.float32) / 255
    g = px[..., 0] / 255
    rebuilt = g[..., None] * light + (1 - g[..., None]) * dark
    assert np.abs(rebuilt - src[..., :3])[vis].max() < 0.06


def test_fire_is_graded_poor(symbol, tmp_path):
    d = ramp_frames(tmp_path / "fr", FIRE)
    res = ae_bridge.fx_to_spine(symbol, "fire", frames_dir=str(d), fps=24, mode="alpha", tintable=True)
    assert res["tint"]["grade"] == "poor" and "After Effects" in res["tint"]["note"]


def test_tint_turns_the_hue_and_keeps_a_white_core():
    light, dark = np.array([0.93, 1.0, 1.0], np.float32), np.array([0.0, 0.0, 0.73], np.float32)
    l2, d2 = ae_tint.recolour(light, dark, "FF3030")
    assert hue_gap(d2, "FF3030") < 0.01                                           # red edge
    assert l2.min() > 0.9                                                         # still white-hot
    l3, d3 = ae_tint.recolour(light, dark, "FFFFFF/7A2CFF")
    assert ae_tint.rgb_hex(l3) == "FFFFFF" and ae_tint.rgb_hex(d3) == "7A2CFF"
    grey_l, grey_d = np.array([1, 1, 1], np.float32), np.array([0.3, 0.3, 0.3], np.float32)
    l4, d4 = ae_tint.recolour(grey_l, grey_d, "2E7BFF")                           # colourless: tint colours the glow
    assert ae_tint.rgb_hex(l4) == "FFFFFF" and ae_tint.rgb_hex(d4) == "2E7BFF"
    # white lightning fits white -> near-black navy; its tint must colour the glow, not just the invisible navy
    l5, d5 = ae_tint.recolour(np.array([0.98, 0.98, 1.0], np.float32), np.array([0, 0, 0.184], np.float32), "FF3BD0")
    assert ae_tint.rgb_hex(d5) == "FF3BD0" and l5.min() > 0.95


def test_copies_share_the_frames_in_their_own_colours(symbol, tmp_path):
    d = ramp_frames(tmp_path / "fr", BLUE_WHITE)
    n_before = len(list((symbol.images_dir).rglob("*.png")))
    res = ae_bridge.fx_to_spine(symbol, "zap", frames_dir=str(d), fps=24, tintable=True, tint="30FF60",
                                copies=[{"x": 50, "y": 0, "tint": "FF3030"}, [100, 0],
                                        {"x": 150, "y": 0, "tint": "FFFFFF/7A2CFF"}])
    assert len(list((symbol.images_dir).rglob("*.png"))) - n_before == res["frames_out"]   # one frame set
    slots = {s.name: s for s in symbol.data.slots}
    main = slots[res["slot"]]
    assert hue_gap(ae_tint.hex_rgb(main.dark), "30FF60") < 0.02                  # green
    red, plain, purple = res["copy_instances"]
    assert hue_gap(ae_tint.hex_rgb(slots[red["slot"]].dark), "FF3030") < 0.02
    assert (slots[plain["slot"]].color, slots[plain["slot"]].dark) == (main.color, main.dark)   # untinted copy
    assert (slots[purple["slot"]].color[:6], slots[purple["slot"]].dark) == ("FFFFFF", "7A2CFF")
    assert red["light"] == slots[red["slot"]].color[:6] and red["dark"] == slots[red["slot"]].dark


def test_tint_errors_are_clear_and_early(symbol, tmp_path):
    d = ramp_frames(tmp_path / "fr", BLUE_WHITE)
    with pytest.raises(ValueError, match="tintable"):
        ae_bridge.fx_to_spine(symbol, "a", frames_dir=str(d), fps=24, tint="FF0000")
    with pytest.raises(ValueError, match="tintable"):
        ae_bridge.fx_to_spine(symbol, "b", frames_dir=str(d), fps=24, copies=[{"x": 0, "y": 0, "tint": "FF0000"}])
    with pytest.raises(ValueError, match="bad colour"):
        ae_bridge.fx_to_spine(symbol, "c", frames_dir=str(d), fps=24, tintable=True,
                              copies=[{"x": 0, "y": 0, "tint": "red"}])
    assert not (symbol.images_dir / "ae").exists() or not list((symbol.images_dir / "ae").glob("[abc]_*.png"))


def test_renderer_draws_two_colour_tint_like_spine_webgl():
    page = np.zeros((2, 2, 4), np.float32)
    page[...] = [0.3, 0.3, 0.3, 0.6]                  # premultiplied grey 0.5 at alpha 0.6

    class Pages:
        arr = {"p": page}
    draw = {"page": "p", "v": [-1, -1, 1, -1, 1, 1, -1, 1], "uv": [0, 1, 1, 1, 1, 0, 0, 0],
            "tri": [0, 1, 2, 2, 3, 0], "color": [1.0, 0.8, 0.6, 1.0], "dark": [0.0, 0.0, 1.0], "blend": "normal"}
    im = np.asarray(render.render_frame([draw], Pages, (-1, -1, 1, 1), (8, 8)), np.float32) / 255
    want = 0.5 * np.array([1.0, 0.8, 0.6]) + 0.5 * np.array([0.0, 0.0, 1.0])   # straight: g*light + (1-g)*dark
    assert np.allclose(im[4, 4, :3], want, atol=0.02) and im[4, 4, 3] == pytest.approx(0.6, abs=0.01)


def test_tool_takes_tint_options(symbol, tmp_path):
    d = ramp_frames(tmp_path / "fr", BLUE_WHITE)
    res = server.ae_vfx_to_spine(str(symbol.path), "zap", frames_dir=str(d), fps=24, tintable=True,
                                 copies=[{"x": 10, "y": 0, "tint": "FF3030"}])
    assert res["tint"]["grade"] == "good" and "validation_errors" not in res


@needs_node
def test_the_runtime_draws_the_dark_colour(symbol, tmp_path):
    d = ramp_frames(tmp_path / "fr", BLUE_WHITE)
    res = ae_bridge.fx_to_spine(symbol, "zap", frames_dir=str(d), fps=24, tintable=True)
    symbol.save()
    dump = runtime.run(symbol, animations=[res["animation"]], fps=24, geometry=True)
    draws = [dr for f in dump["animations"][res["animation"]]["frames"] for dr in f["draws"]
             if dr["slot"] == res["slot"]]
    assert draws and np.allclose(draws[0]["dark"], ae_tint.hex_rgb(res["tint"]["dark"]), atol=0.01)


def test_preview_bounds_skip_an_empty_setup_pose():
    dump = {"setup": {"bounds": [None, None, None, None]}, "animations": {"a": {"bounds": [-10, -5, 10, 5]}}}
    x0, y0, x1, y1 = render.union_bounds(dump, ["a"], pad=0)
    assert (x0, y0, x1, y1) == (-10, -5, 10, 5)


def test_white_additive_light_ramps_on_brightness(symbol, tmp_path):
    """White lightning: near-white everywhere, only brightness varies. Untinted it must look like the render; a tint
    must colour the dim glow and leave the core white."""
    d = tmp_path / "fr"
    d.mkdir()
    y, x = np.mgrid[0:32, 0:48]
    for i in range(4):
        v = np.clip(1.2 - np.abs(x - 24) / 10, 0, 1) * (0.7 + 0.1 * i)       # light on black, white
        Image.fromarray(np.round(np.dstack([v, v, v * 0.98 + 0.02 * (v > 0)]) * 255).astype(np.uint8)).save(d / f"f_{i}.png")
    res = ae_bridge.fx_to_spine(symbol, "bolt", frames_dir=str(d), fps=24, mode="additive", tintable=True,
                                copies=[{"x": 0, "y": 0, "tint": "2E7BFF"}])
    t = res["tint"]
    assert t["ramp"] == "brightness" and t["grade"] == "good" and t["light"] == t["dark"]
    px = np.asarray(symbol.image("ae/bolt_03"), np.float32) / 255
    assert np.allclose(px[..., 0], px[..., 3], atol=1 / 255)                    # grey = brightness
    slots = {s.name: s for s in symbol.data.slots}
    blue = slots[res["copy_instances"][0]["slot"]]
    assert blue.dark == "2E7BFF" and ae_tint.hex_rgb(blue.color[:6]).min() > 0.95
    # what a pixel shows (premultiplied, spine-webgl two-colour tint): dim glow mostly blue, bright core white
    L, D = ae_tint.hex_rgb(blue.color[:6]), ae_tint.hex_rgb(blue.dark)
    show = lambda a: (a - a * a) * D + a * a * L
    dim, core = show(0.2), show(1.0)
    assert dim[2] > 1.5 * dim[0] and np.allclose(core, L, atol=1e-6)
