"""FX recipes: every recipe builds, validates, renders in the runtime, and honours the shared arguments."""
import asyncio
import json
from pathlib import Path

import pytest

from claude_spine import fx_recipes as R, qa, runtime
from claude_spine.ir import RegionAttachment, new_skeleton
from claude_spine.project import Project
from conftest import needs_node

ALL = list(R.RECIPES)


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


def _dur(p, anim):
    a = p.data.animations[anim]
    ts = [0.0]
    for tl in a.bones.values():
        for keys in tl.values():
            ts += [k.time for k in keys]
    for tl in a.slots.values():
        for keys in tl.values():
            ts += [k.time for k in keys]
    return max(ts)


@pytest.mark.parametrize("name", ALL)
def test_each_recipe_builds_and_validates(proj, name):
    res = R.apply(proj, name)
    assert res["animation"] == f"fx_{name}" and res["slots"] and res["event"] == f"fx_{name}"
    assert all(s.blend == "additive" or (name == "portal" and "disc" in s.name) or (name == "cell_glow" and s.blend == "normal")
               or (name in ("puff", "smoke_glow") and s.blend == "normal")
               for s in proj.data.slots)
    assert all(s.attachment is None for s in proj.data.slots), "FX slots must be hidden in the setup pose"
    v = qa.validate(proj.data)
    assert v["ok"], v["errors"]


@needs_node
@pytest.mark.parametrize("name", ALL + ["magic_reveal"])
def test_each_recipe_plays_in_the_spine_core_runtime(proj, name):
    res = R.apply(proj, name)
    proj.save()
    dump = runtime.run(proj, animations=[res["animation"]], fps=10, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    assert dump["animations"][res["animation"]]["frames"]


def test_unknown_recipe_or_option_is_a_clear_error(proj):
    with pytest.raises(ValueError, match="unknown recipe"):
        R.apply(proj, "nope")
    with pytest.raises(ValueError, match="unknown option"):
        R.apply(proj, "rune_ring", options={"colour": "red"})
    with pytest.raises(ValueError, match="scale"):
        R.apply(proj, "rune_ring", scale=0)


def test_x_y_scale_land_on_the_group_bone(proj):
    res = R.apply(proj, "bloom_aura", x=120, y=-40, scale=1.5)
    g = proj.data.bone(res["group_bone"])
    assert (g.x, g.y, g.scaleX, g.scaleY) == (120, -40, 1.5, 1.5)
    assert g.parent == "root"


def test_parent_and_draw_order(proj):
    from claude_spine.ir import Bone, Slot
    proj.data.bones.append(Bone(name="hand", parent="root", x=50))
    proj.data.add_slot(Slot(name="art", bone="hand"))
    proj.data.add_slot(Slot(name="top", bone="hand"))
    res = R.apply(proj, "twinkles", parent="hand", front_of="art")
    assert proj.data.bone(res["group_bone"]).parent == "hand"
    names = [s.name for s in proj.data.slots]
    assert names.index("art") + 1 == names.index(res["slots"][0]) and names.index("top") > names.index(res["slots"][-1])
    res2 = R.apply(proj, "twinkles", behind="art", name="back")
    names = [s.name for s in proj.data.slots]
    assert names.index(res2["slots"][-1]) + 1 == names.index("art")


def test_color_bakes_its_own_texture(proj):
    a = R.apply(proj, "rune_ring")
    b = R.apply(proj, "rune_ring", color="5AE0FF", name="cyan")
    pa = proj.data.skin("default").attachments[a["slots"][1]]["fx"].path
    pb = proj.data.skin("default").attachments[b["slots"][1]]["fx"].path
    assert pa == "fx/rune_ring_FFCD3C" and pb == "fx/rune_ring_5AE0FF"
    import numpy as np

    def tint(path):
        im = np.asarray(proj.image(path), float)
        w = im[..., 3:4]
        return (im[..., :3] * w).sum((0, 1)) / w.sum()
    ta, tb = tint(pa), tint(pb)
    assert ta[0] > ta[2] + 50 and tb[2] > tb[0] + 20, (ta, tb)    # gold stays warm, cyan goes cool


def test_start_shifts_and_into_merges_into_an_existing_animation(proj):
    from claude_spine.timeline import AnimBuilder
    AnimBuilder(proj.data, "win").bone("root", "rotate", [(0, 0), (1.2, 10)])
    res = R.apply(proj, "burst_flare", into="win", start=0.5)
    a = proj.data.animations["win"]
    assert res["animation"] == "win" and "root" in a.bones and a.bones["root"]["rotate"][-1].time == 1.2
    flare_bones = [b for b in proj.data.bones if b.name.startswith("fx_burst_flare")]
    first = min(k.time for b in flare_bones if b.name in a.bones for tl in a.bones[b.name].values() for k in tl)
    assert first >= 0.5
    assert any(e.name == "fx_burst_flare" and e.time == 0.5 for e in a.events)


def test_one_shot_duration_is_a_time_scale_and_window_duration_is_a_length(proj):
    a = R.apply(proj, "rune_ring")
    b = R.apply(proj, "rune_ring", duration=5.4, name="slow")
    assert _dur(proj, b["animation"]) == pytest.approx(2 * _dur(proj, a["animation"]), rel=0.02)
    c = R.apply(proj, "fireflies", duration=4.0)
    assert _dur(proj, c["animation"]) == pytest.approx(4.0, abs=0.01)


def test_count_and_seed(proj, tmp_path):
    assert len(R.apply(proj, "fireflies", count=12)["slots"]) == 12
    assert R.apply(proj, "rim_wisps", count=8)["tufts"] == 8
    q1 = Project(tmp_path / "a.json", new_skeleton("a", 720, 720))
    q2 = Project(tmp_path / "b.json", new_skeleton("b", 720, 720))
    q3 = Project(tmp_path / "c.json", new_skeleton("c", 720, 720))
    for q, sd in ((q1, 7), (q2, 7), (q3, 9)):
        R.apply(q, "fireflies", seed=sd)
    dump = lambda q: json.dumps(q.data.model_dump(mode="json", exclude_none=True), sort_keys=True)  # noqa: E731
    assert dump(q1) == dump(q2) and dump(q1) != dump(q3)


def test_intensity_scales_alpha(proj):
    a = R.apply(proj, "bloom_aura", name="a")
    b = R.apply(proj, "bloom_aura", name="b", intensity=0.5)
    def peak(anim, slot):
        ks = proj.data.animations[anim].slots[slot]["rgba"]
        return max(int(k.color[6:8], 16) for k in ks)
    assert peak(b["animation"], b["slots"][0]) < peak(a["animation"], a["slots"][0])


def test_fireflies_respawn_hides_inside_alpha_zero(proj):
    res = R.apply(proj, "fireflies", count=6)
    a = proj.data.animations[res["animation"]]
    for s in res["slots"]:
        keys = a.slots[s]["rgba"]
        # every key pair closer than 5 ms is a respawn: both sides must be invisible
        for k0, k1 in zip(keys, keys[1:]):
            if k1.time - k0.time < 0.005:
                assert int(k0.color[6:8], 16) <= 6 and int(k1.color[6:8], 16) <= 6


def test_magic_reveal_bundle(proj):
    res = R.apply(proj, "magic_reveal", scale=0.8, x=10)
    assert res["parts"] == [n for n, *_ in R.REVEAL] and res["animation"] == "magic_reveal"
    assert _dur(proj, "magic_reveal") <= R.REVEAL_LENGTH + 1e-6
    ev = {e.name: e.time for e in proj.data.animations["magic_reveal"].events}
    assert ev["fx_rune_ring"] == 2.0 and ev["fx_burst_flare"] == 3.55 and ev["fx_reveal_end"] == R.REVEAL_LENGTH
    b = qa.budget(proj.data, "desktop")
    assert b["metrics"]["draw_calls"] == 1 and b["metrics"]["clipping"] == 0 and b["metrics"]["weighted_vertices"] == 0
    names = [s.name for s in proj.data.slots]
    assert len(names) == len(set(names))
    assert {s.blend for s in proj.data.slots} == {"additive"}


def test_magic_reveal_skip_and_overrides(proj):
    res = R.apply(proj, "magic_reveal", options={"skip": ["fireflies", "twinkles"],
                                                 "overrides": {"rune_ring": {"color": "5AE0FF"}}})
    assert "fireflies" not in res["parts"] and "twinkles" not in res["parts"]
    assert proj.image_path("fx/rune_ring_5AE0FF")
    with pytest.raises(ValueError, match="unknown recipe"):
        R.apply(proj, "magic_reveal", options={"skip": ["nope"]})


def test_the_mcp_tool_lists_returns_the_guide_and_applies(tmp_path):
    from claude_spine.server import mcp

    def call(**args):
        res = asyncio.run(mcp.call_tool("fx_recipe", args))
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)
    listing = call()
    assert set(R.RECIPES) | {"magic_reveal"} <= set(listing["recipes"])
    assert "Fork" in call(recipe="guide")["guide"]
    p = Project(tmp_path / "t.json", new_skeleton("t", 720, 720))
    p.save()
    out = call(project=str(p.path), recipe="rune_ring", x=5, y=5)
    assert out["animation"] == "fx_rune_ring" and "validation_errors" not in out
    assert "fx_rune_ring" in Project.open(p.path).data.animations


def test_docs_guide_mirrors_the_tool_guide():
    from claude_spine.fx_recipes_guide import GUIDE
    doc = Path(__file__).resolve().parents[1] / "docs" / "FX_RECIPES.md"
    assert doc.read_text() == GUIDE


# ---------------------------------------------------------------- beams, portal, electric frame
@pytest.mark.parametrize("style", ["gold", "ribbon", "blue"])
def test_light_beam_styles_and_loop_closure(proj, style):
    res = R.apply(proj, "light_beam", options={"style": style})
    assert res["loop"] == 4.0 and res["strands"] >= 2
    a = proj.data.animations[res["animation"]]
    # every strand row translates, and the loop closes: first and last key of a row match
    rows = [b for b in a.bones if "_n" in b and a.bones[b].get("translate")]
    assert rows
    for b in rows[:20]:
        ks = a.bones[b]["translate"]
        assert ks[0].time == 0 and ks[-1].time == pytest.approx(4.0)
        assert ks[0].x == pytest.approx(ks[-1].x, abs=0.01)
    # ribbons are weighted meshes (no deform keys, which blow the mobile budget)
    assert not any("deform" in tls for sk in a.attachments.values() for sl in sk.values() for tls in sl.values())
    meshes = [att for att in proj.data.skin("default").attachments.values() for att in att.values() if att.type == "mesh"]
    assert meshes and all(m.hull == len(m.uvs) // 2 for m in meshes)
    assert qa.validate(proj.data)["ok"]


def test_light_beam_unknown_style_and_style_defaults(proj):
    with pytest.raises(ValueError, match="unknown style"):
        R.apply(proj, "light_beam", options={"style": "green"})
    g = R.apply(proj, "light_beam", name="g", options={"style": "gold"})
    b = R.apply(proj, "light_beam", name="b", options={"style": "blue"})
    assert b["dust"] > g["dust"] and R.apply(proj, "light_beam", name="x", count=5)["dust"] == 5
    assert R.apply(proj, "light_beam", name="r", options={"style": "ribbon"})["sparks"] > 0


def test_portal_leaves_a_slot_for_the_ae_ring(proj):
    res = R.apply(proj, "portal")
    hint = res["ring_hint"]
    assert hint["parent"] == res["group_bone"] and hint["front_of"] == res["ring_after"] and hint["mode"] == "additive"
    names = [s.name for s in proj.data.slots]
    after = names.index(res["ring_after"])
    assert names[after + 1].endswith("flash") or "flash" in names[after + 1], "flashes must draw above the ring"
    disc = next(s for s in proj.data.slots if "disc" in s.name)
    assert disc.blend == "normal"          # the disc hides the scene; everything else is light


def test_electric_frame_hint_and_sparks(proj):
    res = R.apply(proj, "electric_frame", options={"width": 300.0, "height": 200.0, "sparks": 6})
    assert res["ring_hint"]["front_of"] == res["ring_after"] and len(res["slots"]) == 1 + 6
    under = next(b for b in proj.data.bones if b.name.endswith("under"))
    assert under.scaleX == pytest.approx(1.0) and under.scaleY == pytest.approx(200 / 300)


def test_the_portal_and_frame_ae_templates_exist_and_build():
    from claude_spine import ae_templates
    t = ae_templates.list_templates()
    assert {"portal_ring", "electric_frame"} <= set(t)
    for n in ("portal_ring", "electric_frame"):
        r = ae_templates.build_script(n, {"comp": f"x_{n}"})
        src = open(r["script"]).read()
        assert "Turbulent Displace" in src and "Cycle Evolution" in src, "must loop seamlessly"


# ---------------------------------------------------------------- crosshair, hit burst, cell glow, lock-on
def test_crosshair_events_and_timing(proj):
    res = R.apply(proj, "crosshair", start=0.5, options={"lock": 0.4, "hit": 1.0})
    ev = {e.name: e.time for e in proj.data.animations[res["animation"]].events}
    assert ev["fx_crosshair_lock"] == pytest.approx(0.9) and ev["fx_crosshair_hit"] == pytest.approx(1.5)
    assert res["lock_at"] == pytest.approx(0.9) and res["hit_at"] == pytest.approx(1.5)


def test_hit_burst_fires_fx_hit_and_sparks(proj):
    res = R.apply(proj, "hit_burst", count=6, start=1.0)
    assert res["sparks"] == 6
    assert any(e.name == "fx_hit" and e.time == 1.0 for e in proj.data.animations[res["animation"]].events)


def test_cell_glow_is_a_resizable_9_slice_on_corner_bones(proj):
    res = R.apply(proj, "cell_glow", options={"width": 200.0, "height": 120.0})
    assert len(res["corner_bones"]) == 4                      # fill and frame ride the same four corner bones
    meshes = [a for sl in proj.data.skin("default").attachments.values() for a in sl.values() if a.type == "mesh"]
    assert len(meshes) == 2
    for m in meshes:
        assert m.hull == 12 and len(m.uvs) == 32 and len(m.triangles) == 54
        assert all(v == 1 for v in m.vertices[0::5])          # every vertex has exactly one influence
        xs = sorted({round(m.vertices[i + 2], 1) for i in range(0, len(m.vertices), 5)})
        assert max(xs) <= 48.0 and min(xs) >= -48.0           # local to its corner bone: never spans the cell
    corners = {proj.data.bone(b).name.rsplit("_", 1)[-1]: proj.data.bone(b) for b in res["corner_bones"]}
    assert (corners["tl"].x, corners["tl"].y, corners["br"].x, corners["br"].y) == (-100, 60, 100, -60)
    assert qa.validate(proj.data)["ok"]


def test_cell_glow_cells_stagger_and_pop(proj):
    res = R.apply(proj, "cell_glow", options={"cells": [[0, 0, 100, 100], [0, -110, 100, 200]], "stagger": 0.2, "pop": 1.5})
    assert res["cells"] == 2 and res["pops"] == [pytest.approx(1.5), pytest.approx(1.7)]
    ev = [e.time for e in proj.data.animations[res["animation"]].events if e.name == "fx_cell_pop"]
    assert ev == [pytest.approx(1.5), pytest.approx(1.7)]
    disc = next(s for s in proj.data.slots if s.blend == "normal")
    assert disc.blend == "normal"                              # the fill darkens what is behind the cell
    nopop = R.apply(proj, "cell_glow", name="calm", options={"pop": 0})
    assert nopop["pops"] == [None]
    assert not any(e.name == "fx_cell_pop" for e in proj.data.animations[nopop["animation"]].events)


def test_lock_on_places_every_target(proj):
    res = R.apply(proj, "lock_on", scale=0.5, x=10, y=20, options={"targets": [[0, 0], [100, -40]], "stagger": 0.3,
                                                                  "crosshair": {"hit": 0.7}})
    assert res["targets"] == 2 and "fx_hit" in res["events"] or "fx_hit_burst" in res["events"]
    groups = [b for b in proj.data.bones if b.name in ("fx_crosshair", "fx_crosshair2", "fx_hit_burst", "fx_hit_burst2")]
    pos = sorted((round(b.x, 1), round(b.y, 1)) for b in groups)
    assert pos == [(10.0, 20.0), (10.0, 20.0), (60.0, 0.0), (60.0, 0.0)]
    a = proj.data.animations["lock_on"]
    hits = sorted(e.time for e in a.events if e.name == "fx_hit")
    assert hits == [pytest.approx(0.7), pytest.approx(1.0)]
    assert qa.validate(proj.data)["ok"]


# ---------------------------------------------------------------- custom art
def _png(path, size=(160, 80), color=(255, 0, 0, 255)):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse([4, 4, size[0] - 5, size[1] - 5], fill=color)
    im.save(path)
    return str(path)


def test_art_replaces_the_generated_picture_and_keeps_the_motion(proj, tmp_path):
    base = R.apply(proj, "crosshair", name="gen")
    res = R.apply(proj, "crosshair", name="mine", art={"reticle": _png(tmp_path / "r.png")})
    assert res["art"] == {"reticle": "fx/art_crosshair_reticle"}
    att = proj.data.skin("default").attachments[res["slots"][2]]["fx"]
    assert att.path == "fx/art_crosshair_reticle" and att.width == 170 and att.height == 85    # recipe width, art aspect
    assert proj.image("fx/art_crosshair_reticle").size == (160, 80)
    a, b = proj.data.animations[base["animation"]], proj.data.animations[res["animation"]]
    ka = {bn: [(k.time) for k in tl["rotate"]] for bn, tl in a.bones.items() if "rotate" in tl}
    kb = {bn: [(k.time) for k in tl["rotate"]] for bn, tl in b.bones.items() if "rotate" in tl}
    assert sorted(ka.values()) == sorted(kb.values()), "the motion must not change"
    assert qa.validate(proj.data)["ok"]


def test_art_options_blend_scale_and_unknown_role(proj, tmp_path):
    f = _png(tmp_path / "r.png")
    res = R.apply(proj, "crosshair", art={"reticle": {"path": f, "blend": "normal", "scale": 0.5}})
    slot = next(s for s in proj.data.slots if s.name == res["slots"][2])
    att = proj.data.skin("default").attachments[slot.name]["fx"]
    assert slot.blend == "normal" and att.width == 85
    with pytest.raises(ValueError, match="unknown art role"):
        R.apply(proj, "crosshair", art={"retical": f})
    with pytest.raises(ValueError, match="not found"):
        R.apply(proj, "crosshair", name="x", art={"reticle": str(tmp_path / "missing.png")})


def test_art_from_a_psd_layer(proj, tmp_path):
    from PIL import Image
    from psd_tools import PSDImage
    from psd_tools.api.layers import Group, PixelLayer
    psd = PSDImage.new("RGBA", (400, 300))
    psd.append(PixelLayer.frompil(Image.new("RGBA", (120, 60), (0, 255, 0, 255)), psd, name="Reticle", top=50, left=60))
    g = Group.new(name="fx", parent=psd)
    psd.append(g)
    g.append(PixelLayer.frompil(Image.new("RGBA", (30, 30), (255, 0, 0, 255)), psd, name="Burst", top=0, left=0))
    f = tmp_path / "a.psd"
    psd.save(f)
    res = R.apply(proj, "crosshair", art={"reticle": f"{f}#reticle"})
    assert proj.image(res["art"]["reticle"]).size == (120, 60)          # cut at the layer's own bounding box
    res2 = R.apply(proj, "hit_burst", art={"starburst": f"{f}#fx/burst"})
    assert proj.image(res2["art"]["starburst"]).size == (30, 30)
    with pytest.raises(ValueError, match="not found"):
        R.apply(proj, "crosshair", name="z", art={"reticle": f"{f}#nope"})


def test_art_anchors_for_wisps_beams_and_stretched_columns(proj, tmp_path):
    f = _png(tmp_path / "t.png", size=(100, 400))
    w = R.apply(proj, "rim_wisps", count=3, art={"wisp": f})
    att = proj.data.skin("default").attachments[w["slots"][1]]["fx"]
    assert att.x == pytest.approx(att.width / 2, abs=0.01)                         # base on the bone, art extends outward
    b = R.apply(proj, "bloom_aura", art={"beam": f})
    att = proj.data.skin("default").attachments[b["slots"][1]]["fx"]
    assert att.y == pytest.approx(att.height / 2, abs=0.01)                        # base at the bottom
    lb = R.apply(proj, "light_beam", art={"column": f, "strand": f})
    col = proj.data.skin("default").attachments[lb["slots"][0]]["fx"]
    assert col.height == pytest.approx(640 * 1.02)                       # a column spans the beam whatever the art's aspect
    assert qa.validate(proj.data)["ok"]


def test_art_for_a_9_slice_frame_and_for_bundles(proj, tmp_path):
    f = _png(tmp_path / "frame.png", size=(96, 96))
    res = R.apply(proj, "cell_glow", options={"width": 100.0, "height": 100.0},
                  art={"frame": {"path": f, "slice": 30, "px": 0.5}})
    mesh = next(a for sl in proj.data.skin("default").attachments.values() for a in sl.values()
                if a.type == "mesh" and a.path == "fx/art_cell_glow_frame")
    assert mesh.uvs[2] == pytest.approx(30 / 96)                         # slice in art pixels -> UV
    xs = sorted({round(mesh.vertices[i + 2], 1) for i in range(0, len(mesh.vertices), 5)})
    assert max(xs) == pytest.approx(15.0)                                # ... and 15 units (px = 0.5) from its corner
    lk = R.apply(proj, "lock_on", options={"targets": [[0, 0]]}, art={"crosshair": {"reticle": f}, "hit_burst": {"starburst": f}})
    assert lk["animation"] == "lock_on"
    with pytest.raises(ValueError, match="keyed by member"):
        R.apply(proj, "lock_on", art={"reticle": f})
    with pytest.raises(ValueError, match="keyed by member"):
        R.apply(proj, "magic_reveal", art={"ring": f})
    assert qa.validate(proj.data)["ok"]


def test_listing_shows_the_art_roles(proj):
    ls = R.list_recipes()
    assert {"reticle", "glow", "ring", "flash"} <= set(ls["crosshair"]["art_roles"])
    assert {"frame", "fill"} <= set(ls["cell_glow"]["art_roles"])
    assert all(ls[n]["art_roles"] for n in R.RECIPES)


def test_art_for_rings_and_glows_too(proj, tmp_path):
    f = _png(tmp_path / "g.png", size=(128, 128))
    res = R.apply(proj, "crosshair", art={"ring": f, "glow": f, "flash": f})
    assert set(res["art"]) == {"ring", "glow", "flash"}
    paths = {proj.data.skin("default").attachments[s]["fx"].path for s in res["slots"]}
    assert {"fx/art_crosshair_ring", "fx/art_crosshair_glow", "fx/art_crosshair_flash", "fx/reticle_FFB02E"} <= paths


# ---------------------------------------------------------------- puff, smoke glow, cell fill
def test_puff_blend_count_and_event(proj):
    res = R.apply(proj, "puff", count=5, start=1.0, options={"blend": "additive"})
    assert res["blobs"] == 5 and all(s.blend == "additive" for s in proj.data.slots)
    assert any(e.name == "fx_puff" and e.time == 1.0 for e in proj.data.animations[res["animation"]].events)
    n = R.apply(proj, "puff", name="cartoon")
    cloud = [s for s in proj.data.slots if s.name.startswith("fx_cartoon_b")]
    assert cloud and all(s.blend == "normal" for s in cloud)           # the cartoon puff is opaque by default


def test_smoke_glow_loops_and_fills_the_box(proj):
    res = R.apply(proj, "smoke_glow", options={"width": 200.0, "height": 300.0}, count=10)
    assert res["loop"] == 4.0 and res["blobs"] == 10
    a = proj.data.animations[res["animation"]]
    for sl in res["slots"][1:]:
        keys = a.slots[sl]["rgba"]
        assert keys[0].time == 0 and keys[-1].time == pytest.approx(4.0)
        assert keys[0].color == keys[-1].color                         # the loop closes exactly
    xt = []
    for sl in res["slots"][1:]:
        ks = a.bones[sl]["translate"]
        xt.append(sum(k.x for k in ks) / len(ks))
    assert max(xt) - min(xt) > 120, "blobs are spread across the width, not bunched on one side"


def test_cell_glow_fill_options(proj):
    res = R.apply(proj, "cell_glow", options={"fill_color": "C98A7A", "fill_alpha": 0.3})
    fill = next(s for s in proj.data.slots if s.blend == "normal")
    ks = proj.data.animations[res["animation"]].slots[fill.name]["rgba"]
    assert all(k.color[:6] == "C98A7A" for k in ks) and max(int(k.color[6:8], 16) for k in ks) <= int(0.3 * 255) + 1
