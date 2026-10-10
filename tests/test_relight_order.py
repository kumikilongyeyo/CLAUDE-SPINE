"""relight (light measured from the FX onto the subject), optimize_draw_order (fewer calls, same pixels), grouped
atlas packing, warm recolouring, and the orbit / texture template options."""
import colorsys

import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_bridge, ae_templates, ae_tint, atlas, draw_order, relight, server
from claude_spine.ir import Bone, RegionAttachment, Slot, new_skeleton
from claude_spine.project import Project
from conftest import needs_node


def pulse_frames(d, n=8, colour=(0.6, 0.3, 1.0)):
    """Light on black that swells to frame 4 and fades: the flash a subject should catch."""
    d.mkdir(parents=True, exist_ok=True)
    y, x = np.mgrid[0:48, 0:48]
    for i in range(n):
        k = 1 - abs(i - 4) / 4
        v = np.clip(1 - np.hypot(x - 24, y - 24) / (8 + 14 * k), 0, 1) * (0.15 + 0.85 * k)
        Image.fromarray(np.round(np.dstack([v * colour[0], v * colour[1], v * colour[2]]) * 255).astype(np.uint8)).save(d / f"f_{i}.png")
    return d


def subject_project(tmp_path, name="s"):
    d = tmp_path / name
    (d / "images").mkdir(parents=True)
    Image.new("RGBA", (40, 40), (220, 170, 40, 255)).save(d / "images" / "coin.png")
    sk = new_skeleton(width=300, height=300)
    sk.bones.append(Bone(name="c", parent="root"))
    sk.slots.append(Slot(name="face", bone="c", attachment="coin"))
    sk.set_attachment("face", "coin", RegionAttachment(width=80, height=80))
    p = Project(d / f"{name}.json", sk)
    p.save()
    return p


@needs_node
def test_relight_follows_the_light_of_the_fx(tmp_path):
    p = subject_project(tmp_path)
    res = ae_bridge.fx_to_spine(p, "flash", frames_dir=str(pulse_frames(tmp_path / "fr")), fps=8, mode="additive",
                                tintable=True, animation="show")
    r = relight.relight(p, "show", ["ae_flash"], ["face"], strength=0.8, fps=8)
    assert r["twins"] == ["face relight"]
    tw = p.data.slot("face relight")
    assert tw.blend == "additive" and tw.bone == "c"
    keys = p.data.animations["show"].slots["face relight"]["rgba"]
    alpha = {round(k.time, 3): int(k.color[6:8], 16) / 255 for k in keys}
    ts = sorted(alpha)
    peak_t = max(ts, key=lambda t: alpha[t])
    assert abs(peak_t - 0.5) <= 0.13                                  # frame 4 of 8 at 8 fps
    assert alpha[peak_t] == pytest.approx(0.8, abs=0.02)               # the peak maps to strength (norm = peak)
    assert alpha[ts[0]] < 0.3 * alpha[peak_t]                         # dim before the flash
    col = ae_tint.hex_rgb(keys[ts.index(peak_t)].color[:6])
    assert col[2] > col[1] and col[0] > col[1]                         # violet light, measured from the frames
    assert r["hits"] and r["hits"][0] < peak_t + 1e-6                  # the sharpest rise comes before the peak


@needs_node
def test_relight_norm_carries_between_animations_and_bad_input_is_clear(tmp_path):
    p = subject_project(tmp_path)
    ae_bridge.fx_to_spine(p, "flash", frames_dir=str(pulse_frames(tmp_path / "fr")), fps=8, mode="additive",
                          animation="show")
    r1 = relight.relight(p, "show", ["ae_fl*"], ["face"], strength=0.5, fps=8)
    r2 = relight.relight(p, "show", ["ae_flash"], ["face"], strength=0.5, norm=r1["norm"] * 4, fps=8)
    assert r2["peak"]["alpha"] == pytest.approx(0.125, abs=0.02)      # a 4x norm: a quarter of the light
    with pytest.raises(ValueError, match="no slot matches"):
        relight.relight(p, "show", ["nope*"], ["face"])


def two_lights_project(tmp_path, overlap: bool):
    """face (normal) between two additive lights; with overlap=False the second light sits far from the face."""
    p = subject_project(tmp_path, "o" if overlap else "n")
    sk = p.data
    Image.new("RGBA", (40, 40), (255, 255, 255, 255)).save(p.images_dir / "glow.png")
    sk.bones.append(Bone(name="far", parent="root", x=0 if overlap else 400))
    sk.slots.insert(0, Slot(name="back_glow", bone="c", attachment="glow", blend="additive"))
    sk.slots.append(Slot(name="side_glow", bone="far", attachment="glow", blend="additive"))
    for s in ("back_glow", "side_glow"):
        sk.set_attachment(s, "glow", RegionAttachment(width=60, height=60))
    from claude_spine.timeline import AnimBuilder
    AnimBuilder(sk, "idle", replace=True).bone("c", "rotate", [(0, 0), (1, 10)])
    p.save()
    return p


@needs_node
def test_draw_order_groups_light_that_does_not_overlap_and_keeps_the_pixels(tmp_path):
    p = two_lights_project(tmp_path, overlap=False)
    r = draw_order.optimize(p, fps=4, group_pages=False)
    assert r["calls_before"]["max"] == 3 and r["calls_after"]["max"] == 2
    assert r["applied"] and r["pixel_max_diff"] <= 2
    names = [s.name for s in p.data.slots]
    assert abs(names.index("back_glow") - names.index("side_glow")) == 1   # the two lights now share a batch


@needs_node
def test_draw_order_never_moves_light_across_art_it_covers(tmp_path):
    p = two_lights_project(tmp_path, overlap=True)
    before = [s.name for s in p.data.slots]
    r = draw_order.optimize(p, fps=4, group_pages=False)
    assert not r["applied"] and [s.name for s in p.data.slots] == before


def test_page_sort_puts_each_pages_lights_together():
    bb = (0, 0, 1, 1)
    blend = {"n": "normal", "a": "additive", "b": "additive", "c": "additive", "d": "additive", "x": "additive"}
    frames = [[("n", "normal", 0, bb), ("a", "additive", 0, bb), ("b", "additive", 1, bb), ("c", "additive", 0, bb),
               ("d", "additive", 1, bb)],
              [("a", "additive", 0, bb), ("d", "additive", 1, bb)]]
    order = ["n", "a", "b", "c", "d", "x"]                          # x is never drawn: it rides with the first page
    new = draw_order.page_sorted(order, blend, set(), frames)
    assert new == ["n", "a", "c", "x", "b", "d"]
    assert draw_order.calls(order, frames) == [5, 2] and draw_order.calls(new, frames) == [3, 2]
    # a normal or pinned slot ends a run: nothing crosses it
    assert draw_order.page_sorted(["b", "a", "n", "d", "c"], blend, set(), frames) == ["b", "a", "n", "d", "c"]
    assert draw_order.page_sorted(["a", "b", "c", "d"], blend, {"c"}, frames) == ["a", "b", "c", "d"]
    # a sequence drawing from several pages counts where it mostly draws
    seq = [[("s", "additive", 1, bb), ("a", "additive", 0, bb)]] * 3 + [[("s", "additive", 0, bb)]]
    assert draw_order.page_sorted(["a", "s", "c"], {"a": "additive", "s": "additive", "c": "additive"}, set(),
                                  seq + [[("c", "additive", 0, bb)]]) == ["a", "c", "s"]


def test_draw_order_leaves_draw_order_keys_alone(tmp_path):
    p = subject_project(tmp_path)
    from claude_spine.ir import DrawOrderKey
    from claude_spine.timeline import AnimBuilder
    AnimBuilder(p.data, "a", replace=True).bone("c", "rotate", [(0, 0), (1, 5)])
    p.data.animations["a"].drawOrder = [DrawOrderKey(time=0.5, offsets=[])]
    assert draw_order.optimize(p, group_pages=False)["reason"].startswith("an animation keys the draw order")


def test_grouped_packing_keeps_a_sequence_on_one_page(tmp_path):
    p = subject_project(tmp_path)
    sk = p.data
    for seq in ("a", "b"):
        for i in range(12):
            Image.new("RGBA", (90, 90), (255, 255, 255, 255)).save(p.images_dir / f"{seq}_{i:02d}.png")
        sk.slots.append(Slot(name=seq, bone="c"))
        from claude_spine.ir import Sequence
        sk.set_attachment(seq, "fx", RegionAttachment(path=f"{seq}_", width=90, height=90,
                                                      sequence=Sequence(count=12, start=0, digits=2)))
    plain = atlas.pack(p, tmp_path / "plain", max_size=420)
    grouped = atlas.pack(p, tmp_path / "grouped", max_size=420, group=True)

    def pages_of(res, seq):
        info = atlas.parse_atlas(res["atlas"])
        return {r["page"] for n, r in info["regions"].items() if n.startswith(seq + "_")}
    assert max(len(pages_of(grouped, s)) for s in "ab") == 1               # each sequence on ONE page
    assert max(len(pages_of(plain, s)) for s in "ab") >= 1
    assert sum(len(pages_of(grouped, s)) for s in "ab") <= sum(len(pages_of(plain, s)) for s in "ab")


def test_warm_tints_turn_their_dark_end_toward_red():
    light, dark = np.array([0.99, 0.98, 1.0], np.float32), np.array([0.24, 0.0, 0.93], np.float32)   # violet aura
    l_gold, d_gold = ae_tint.recolour(light, dark, "FFB020")
    h, l, s = colorsys.rgb_to_hls(*d_gold)
    want = colorsys.rgb_to_hls(*ae_tint.hex_rgb("FFB020"))[0]
    assert h < want - 0.02 and l >= 0.5 and s > 0.95                       # amber, bright: not olive brown
    _, d_green = ae_tint.recolour(light, dark, "30FF8A")                     # cool hues are untouched
    assert abs(colorsys.rgb_to_hls(*d_green)[0] - colorsys.rgb_to_hls(*ae_tint.hex_rgb("30FF8A"))[0]) < 0.02


def test_orbit_ribbons_and_smoke_texture_templates(tmp_path):
    t = ae_templates.list_templates()
    assert "orbit_ribbons" in t
    src = open(ae_templates.build_script("orbit_ribbons", {}, tmp_path)["script"]).read()
    assert '"back":"' in src and '"front":"' in src and "ADBE Polar Coordinates" in src and "ADBE Tritone" in src
    assert "Time Remapping" in src                                         # out-of-step rings still loop
    sm = ae_templates.build_script("magic_smoke", {"texture": "kit:smoke_07"}, tmp_path)
    from pathlib import Path
    assert Path(sm["params"]["texture"]).parts[-2:] == ("fx_kit", "smoke_07.png")      # any OS's separators
    with pytest.raises(ValueError, match="no kit picture"):
        ae_templates.build_script("magic_smoke", {"texture": "kit:nope"}, tmp_path)


def test_tools_are_registered():
    assert callable(server.relight_from_fx) and callable(server.optimize_draw_order)
