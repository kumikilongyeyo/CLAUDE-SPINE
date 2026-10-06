"""FX recipes: every recipe builds, validates, renders in the runtime, and honours the shared arguments."""
import asyncio
import json
import math
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
               or ((name in ("puff", "smoke_glow", "frost", "ice_shatter", "explosion") or R.RECIPES[name].get("normal_blend")) and s.blend == "normal")
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
    assert doc.read_text(encoding="utf-8") == GUIDE


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
    # the underglow is a 9-slice on four corner bones whose outline lands on width x height at any aspect
    tl = next(b for b in proj.data.bones if b.name.endswith("under_tl"))
    br = next(b for b in proj.data.bones if b.name.endswith("under_br"))
    inset = 0.26 * 256
    assert (tl.x, tl.y) == (pytest.approx(-150 - inset), pytest.approx(100 + inset))
    assert (br.x, br.y) == (pytest.approx(150 + inset), pytest.approx(-100 - inset))


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


# ---------------------------------------------------------------- meteor, projectile, realistic puff, new AE templates
def test_rr_point_walks_the_perimeter_continuously():
    pts = [R.rr_point(i / 400, 200, 100, 20) for i in range(401)]
    for (x0, y0, a0), (x1, y1, a1) in zip(pts, pts[1:]):
        assert math.hypot(x1 - x0, y1 - y0) < 3.0                      # no jumps (perimeter ~566 / 400 steps)
        assert a1 <= a0 + 1e-6                                          # clockwise: the angle only ever decreases
    assert pts[0][:2] == pytest.approx(pts[-1][:2], abs=1e-6) and pts[-1][2] == pytest.approx(pts[0][2] - 360)
    assert R.rr_point(0.5, 200, 100, 20)[:2] == pytest.approx((80, -50))   # half way = far end of the bottom edge


def test_meteor_trace_tail_follows_the_frame_and_loops(proj):
    res = R.apply(proj, "meteor_trace", options={"width": 200.0, "height": 120.0, "corner": 16.0})
    a = proj.data.animations[res["animation"]]
    head = next(b for b in a.bones if b.endswith("_head"))
    ks = a.bones[head]["translate"]
    assert (ks[0].x, ks[0].y) == pytest.approx((ks[-1].x, ks[-1].y), abs=0.01)     # closes the loop
    for k in ks:                                                         # the head stays on the outline
        on_x = abs(abs(k.x) - 100) < 0.6 and abs(k.y) <= 60.1
        on_y = abs(abs(k.y) - 60) < 0.6 and abs(k.x) <= 100.1
        in_corner = abs(k.x) > 84 - 1e-6 and abs(k.y) > 44 - 1e-6
        assert on_x or on_y or in_corner
    rows = [b for b in a.bones if "_tail_n" in b]
    for b in rows:                                                       # unwrapped: no row ever spins round
        r = [k.value for k in a.bones[b]["rotate"]]
        assert max(abs(r1 - r0) for r0, r1 in zip(r, r[1:])) < 60
    assert qa.validate(proj.data)["ok"]


def test_projectile_reaches_its_target_and_fires_events(proj):
    res = R.apply(proj, "projectile", start=0.2, options={"tx": -300.0, "ty": 50.0, "flight": 0.5})
    a = proj.data.animations[res["animation"]]
    head = next(b for b in a.bones if b.endswith("_head"))
    last = [k for k in a.bones[head]["translate"] if k.time <= 0.7 + 1e-6][-1]
    assert (last.x, last.y) == pytest.approx((-300, 50), abs=0.5)
    ev = {e.name: e.time for e in a.events}
    assert ev["fx_projectile_launch"] == pytest.approx(0.2) and ev["fx_projectile_hit"] == pytest.approx(0.7)
    rows = [b for b in a.bones if "_tail_n" in b]
    for b in rows:                                                       # shooting left crosses +-180: still no spins
        r = [k.value for k in a.bones[b]["rotate"]]
        assert max(abs(r1 - r0) for r0, r1 in zip(r, r[1:])) < 60


def test_realistic_puff_leaves_room_for_the_ae_smoke(proj):
    res = R.apply(proj, "puff", options={"lobes": False})
    assert res["blobs"] == 0 and not any("fx/cloud" == proj.data.skin("default").attachments[s]["fx"].path for s in res["slots"])
    h = res["ae_hint"]
    assert h["parent"] == res["group_bone"] and h["front_of"] in res["slots"] and h["mode"] == "alpha"


def test_frame_glows_are_9_slices(proj):
    for n in ("electric_frame", "meteor_trace"):
        res = R.apply(proj, n, name=n + "_x", options={"width": 900.0, "height": 110.0})
        meshes = [proj.data.skin("default").attachments[s]["fx"] for s in res["slots"]
                  if proj.data.skin("default").attachments[s]["fx"].path == "fx/rrglow"]
        assert meshes and all(m.type == "mesh" and m.hull == 12 for m in meshes)


def test_new_ae_templates_build():
    from claude_spine import ae_templates
    t = ae_templates.list_templates()
    assert {"smoke_puff", "smoke_haze"} <= set(t)
    assert t["fire"]["params"]["edge_fade"] == 0                         # off by default: old fire renders are unchanged
    src = open(ae_templates.build_script("smoke_haze", {})["script"]).read()
    assert "AEFX.loopify" in src and '"black"' in src
    src = open(ae_templates.build_script("fire", {"edge_fade": 0.2})["script"]).read()
    assert "ADBE Mask Feather" in src


# ---------------------------------------------------------------- ice and water
def test_frost_is_a_growing_flipbook(proj):
    import numpy as np
    res = R.apply(proj, "frost", options={"width": 160.0, "height": 120.0, "frames": 10, "grow": 1.0})
    att = next(proj.data.skin("default").attachments[s]["fx"] for s in res["slots"]
               if getattr(proj.data.skin("default").attachments[s]["fx"], "sequence", None))
    assert att.sequence.count == 10 and att.path.startswith("fx/frost_edges_")
    cover = [np.asarray(proj.image(f"{att.path}{i:02d}"))[..., 3].sum() for i in range(10)]
    assert cover[0] < cover[4] < cover[-1] and cover[-1] > 3 * cover[0]                  # it grows (the glowing front moves, so not strictly monotonic)
    a = proj.data.animations[res["animation"]]
    seq = a.attachments["default"][res["slots"][1]]["fx"]["sequence"][0]
    assert seq.mode == "once" and seq.delay == pytest.approx(0.1, abs=1e-4)
    assert any(e.name == "fx_frost_done" and e.time == pytest.approx(1.0) for e in a.events)
    flake = R.apply(proj, "frost", name="flake", options={"mode": "center", "frames": 6})
    assert flake["frames"] == 6


def test_icicles_hang_from_the_top_and_drip(proj):
    res = R.apply(proj, "icicles", count=5, options={"width": 200.0, "height": 100.0})
    assert res["icicles"] == 5
    grp = proj.data.bone("fx_icicles_icicles")                              # the recipe's inner group, on the top edge
    assert grp.y == pytest.approx(50)                                     # the top edge of the box
    icis = [s for s in res["slots"] if proj.data.skin("default").attachments[s]["fx"].path.startswith("fx/icicle")]
    assert len(icis) == 5
    for s in icis:
        att = proj.data.skin("default").attachments[s]["fx"]
        assert att.y == pytest.approx(-att.height / 2, abs=0.02)        # hangs down from its bone
    a = proj.data.animations[res["animation"]]
    drops = [s for s in res["slots"] if proj.data.skin("default").attachments[s]["fx"].path == "fx/drop"]
    assert drops and all("translate" in a.bones[proj.data.slot(s).bone] for s in drops)
    dry = R.apply(proj, "icicles", name="dry", options={"drips": False})
    b = proj.data.animations[dry["animation"]]
    assert not any(proj.data.slot(s).bone in b.bones and "translate" in b.bones[proj.data.slot(s).bone]
                   for s in dry["slots"] if proj.data.skin("default").attachments[s]["fx"].path == "fx/drop")


def test_ice_shatter_cracks_then_breaks(proj):
    res = R.apply(proj, "ice_shatter", start=0.2, count=10)
    assert res["shards"] >= 6 and res["shatter_at"] == pytest.approx(0.95)
    a = proj.data.animations[res["animation"]]
    ev = {e.name: e.time for e in a.events}
    assert ev["fx_ice_crack"] == pytest.approx(0.65) and ev["fx_ice_shatter"] == pytest.approx(0.95)
    shard = next(s for s in res["slots"] if proj.data.skin("default").attachments[s]["fx"].path.startswith("fx/iceshard_"))
    keys = a.slots[shard]["attachment"]
    assert keys[0].name is None and keys[1].time == pytest.approx(0.95)    # shards only exist once it breaks


def test_bubbles_loop_and_splash_drops_never_spin(proj):
    res = R.apply(proj, "bubbles", count=6)
    a = proj.data.animations[res["animation"]]
    for s in res["slots"]:
        ks = a.slots[s]["rgba"]
        assert ks[0].color == ks[-1].color and ks[-1].time == pytest.approx(4.0)
    sp = R.apply(proj, "water_splash", count=8)
    b = proj.data.animations[sp["animation"]]
    drops = [proj.data.slot(s).bone for s in sp["slots"] if proj.data.skin("default").attachments[s]["fx"].path == "fx/drop"
             and "translate" in b.bones.get(proj.data.slot(s).bone, {})]        # spray + crown + the pinched-off drop (the jet only scales)
    assert len(drops) >= 8
    for bn in drops:                                                     # thrown up, then pulled back down by gravity
        ys = [k.y for k in b.bones[bn]["translate"]]
        assert max(ys) > 5 and ys[-1] < max(ys) - 20
        sc = b.bones[bn]["scale"]                                        # stretched along its speed, never squashed flat
        assert all(0.5 < k.x <= 1.0 and 1.0 <= k.y < 1.8 for k in sc)
    assert qa.validate(proj.data)["ok"]


def test_caustics_template():
    from claude_spine import ae_templates
    assert "caustics" in ae_templates.list_templates()
    src = open(ae_templates.build_script("caustics", {})["script"]).read()
    assert "ADBE Cell Pattern-0003" in src and "Cycle Evolution" in src and "Easy Levels2" in src


# ---------------------------------------------------------------- exaggerated-physics redo
def test_explosion_sedov_shockwave_and_cooling_fireball(proj):
    res = R.apply(proj, "explosion", start=0.1, count=6, options={"embers": 2})
    a = proj.data.animations[res["animation"]]
    ev = {e.name: e.time for e in a.events}
    assert ev["fx_explosion"] == pytest.approx(0.1) and ev["fx_explosion_shock"] == pytest.approx(0.12)
    shock = next(b for b in a.bones if b.endswith("_shock"))
    ks = [(k.time - 0.1, k.x) for k in a.bones[shock]["scale"] if k.time > 0.1]
    # radius ~ t^0.4: growth slows, the ratio of early to late growth is far above linear
    early = ks[2][1] - ks[0][1]
    late = ks[-1][1] - ks[-3][1]
    assert early > 4 * late
    fire = next(s for s in res["slots"] if proj.data.skin("default").attachments[s]["fx"].path == "fx/smoke" and proj.data.slot(s).blend == "additive")
    cols = [k.color for k in a.slots[fire]["rgba"]]
    assert cols[1][:2] == "FF" and int(cols[-1][6:8], 16) == 0                 # starts hot and bright, ends gone
    hint = res["ae_hint"]
    assert hint["parent"] == res["group_bone"] and "smoke_puff" in hint["note"]
    assert qa.validate(proj.data)["ok"]


def test_explosion_debris_has_drag(proj):
    res = R.apply(proj, "explosion", count=4, options={"embers": 0})
    a = proj.data.animations[res["animation"]]
    for s in res["slots"]:
        if proj.data.skin("default").attachments[s]["fx"].path != "fx/mote":
            continue
        ks = a.bones[proj.data.slot(s).bone]["translate"]
        dx = [abs(k1.x - k0.x) for k0, k1 in zip(ks, ks[1:])]
        assert dx[0] > dx[-1] * 1.5                                              # horizontal speed decays (air drag)


def test_shine_burst_and_pulse(proj):
    burst = R.apply(proj, "shine", name="b")
    assert burst["loop"] is None and any(e.name == "fx_shine" for e in proj.data.animations[burst["animation"]].events)
    core = next(s for s in burst["slots"] if proj.data.skin("default").attachments[s]["fx"].path == "fx/glow")
    al = [int(k.color[6:8], 16) for k in proj.data.animations[burst["animation"]].slots[core]["rgba"]]
    assert max(al) == al[2] or max(al) == al[1]                                  # instant bloom ...
    assert al[-1] == 0 and al[len(al) // 2] > 0.15 * max(al)                     # ... long tail, then gone
    pulse = R.apply(proj, "shine", name="p", options={"pulse": 3.0})
    assert pulse["loop"] == 3.0
    a = proj.data.animations[pulse["animation"]]
    rays = next(b for b in a.bones if b.endswith("_rays1"))
    rk = a.bones[rays]["rotate"]
    assert rk[-1].value - rk[0].value == pytest.approx(360.0, abs=0.01)         # one turn per loop: closes


def test_portal_differential_rotation_and_keplerian_specks(proj):
    res = R.apply(proj, "portal", options={"specks": 4, "comets": 0})
    a = proj.data.animations[res["animation"]]
    outer = a.bones[next(b for b in a.bones if b.endswith("swirl_a"))]["rotate"]
    inner = a.bones[next(b for b in a.bones if b.endswith("swirl_b"))]["rotate"]
    assert (inner[-1].value - inner[0].value) == pytest.approx(3 * (outer[-1].value - outer[0].value))   # inner spins 3x faster, same way
    piv = next(b for b in a.bones if b.endswith("_sp0"))
    rk = [k for k in a.bones[piv]["rotate"]]
    # within one life the angular speed increases toward the end (infall), ignoring respawn jumps
    speeds = [abs((k1.value - k0.value) / (k1.time - k0.time)) for k0, k1 in zip(rk, rk[1:]) if k1.time - k0.time > 0.01]
    speeds = [s_ for s_ in speeds if s_ < 2000]                          # drop the respawn jumps
    assert len(speeds) > 5 and max(speeds) > 1.8 * min(speeds)           # whips round faster as it falls in


def test_splash_jet_crown_and_landing_ripples(proj):
    res = R.apply(proj, "water_splash", count=6, options={"crown": 4, "landings": 5})
    assert res["landings"] >= 1
    a = proj.data.animations[res["animation"]]
    jet = next(b for b in a.bones if b.endswith("_jet"))
    sy = [k.y for k in a.bones[jet]["scale"]]
    assert max(sy) > 3.0 and sy[-1] < 0.1                                        # shoots up, collapses
    land = [s for s in res["slots"] if "_land" in s]
    assert land and all(a.slots[s]["attachment"][1].time > 0.2 for s in land)    # ripples start when drops come down
    rings = [b for b in a.bones if "_ring0" in b]
    sc = [k.x for k in a.bones[rings[0]]["scale"]]
    assert sc[3] - sc[1] > sc[-1] - sc[-3]                                       # sqrt(t): fast first, then slow


def test_frost_stops_at_contact_and_glows_at_the_front():
    import numpy as np
    from claude_spine.fx_elements import frost_frames
    fr = frost_frames(120, 120, 8, seed=2)
    cov = [np.asarray(f)[..., 3].astype(float).sum() for f in fr]
    assert cov[0] < cov[3] < cov[-1]                                     # grows (the glowing front moves, so not strictly monotonic)
    # the growth front is the brightest thing in a mid frame (white core > tinted film)
    mid = np.asarray(fr[3]).astype(float)
    assert mid[..., :3].max() > 180


def test_loopify_and_physics_templates():
    from claude_spine import ae_templates
    lib = open(ae_templates.HERE / "_lib.jsx").read()
    assert "AEFX.loopify" in lib and "startTime = -D" in lib
    fire = open(ae_templates.build_script("fire", {})["script"]).read()
    assert "AEFX.loopify" in fire and "Offset Turbulence" in fire and "wiggle(11" in fire and "alpha_cut" in fire
    haze = open(ae_templates.build_script("smoke_haze", {})["script"]).read()
    assert "ADBE Twirl" in haze and "AEFX.loopify" in haze and "em.inverted = true" in haze
    puff = open(ae_templates.build_script("smoke_puff", {})["script"]).read()
    assert "_shade" in puff and "P.burst" in puff
    bolt = open(ae_templates.build_script("lightning", {"restrikes": 3})["script"]).read()
    assert "restrikes" in bolt and "duplicate()" in bolt and '"restrikes": 3' in bolt
