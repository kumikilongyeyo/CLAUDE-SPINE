"""Clean-key optimization and layered 2.5D volume weighting."""
from __future__ import annotations

import asyncio
import json
import math

import numpy as np
import pytest

from claude_spine import animation_opt, qa, rig, volume25d
from claude_spine.mesh import mesh_world_vertices
from claude_spine.timeline import AnimBuilder
from claude_spine.weights import decode_weighted


def test_optimizer_reduces_dense_sampled_motion(symbol):
    ab = AnimBuilder(symbol.data, "dense")
    pts = []
    for i in range(61):
        t = i / 60
        y = 35 * math.sin(math.pi * t)
        pts.append((t, y))
    ab.bone("root", "translatey", pts, "linear")
    ab.event(0.5, "impact")

    out = animation_opt.optimize(symbol, "dense", mode="editable")
    ks = symbol.data.animations["dense"].bones["root"]["translatey"]
    assert out["removed"] > 35
    assert len(ks) < 20
    assert ks[0].time == 0 and ks[-1].time == 1
    assert any(k.curve is not None for k in ks[:-1])
    assert symbol.data.animations["dense"].events[0].name == "impact"
    assert qa.validate(symbol.data)["ok"]


def test_optimizer_preserves_authored_curves_by_default(symbol):
    ab = AnimBuilder(symbol.data, "authored")
    ab.bone("root", "scale", [
        (0, 1, 1, "quad_in"),
        (0.2, 1.2, 0.8, "back_out"),
        (0.45, 0.95, 1.05, "sine_in_out"),
        (0.8, 1, 1),
    ], "linear")
    before = [k.model_copy(deep=True) for k in symbol.data.animations["authored"].bones["root"]["scale"]]
    out = animation_opt.optimize(symbol, "authored")
    after = symbol.data.animations["authored"].bones["root"]["scale"]
    assert out["skipped_curved"] == ["root/scale"]
    assert [k.model_dump() for k in after] == [k.model_dump() for k in before]


def test_volume_rig_keeps_setup_pose_and_pins_outline(symbol):
    before = {}
    for slot in ("plate", "gem"):
        from claude_spine.rig import setup_hull_world
        h = setup_hull_world(symbol, slot)
        before[slot] = (h.min(0), h.max(0))

    out = volume25d.rig_volume(symbol, ["plate", "gem"], strength=0.72, test_animation=True)
    core = out["core"]
    assert symbol.data.has_bone(core)
    assert out["test_animation"] == "volume_test"

    for slot in ("plate", "gem"):
        att = symbol.data.attachment(slot)
        now = mesh_world_vertices(symbol.data, slot, att, symbol.data.world())
        lo0, hi0 = before[slot]
        assert np.max(np.abs(now[:att.hull].min(0) - lo0)) < 2.0
        assert np.max(np.abs(now[:att.hull].max(0) - hi0)) < 2.0
        inf = decode_weighted(att.vertices, len(att.uvs) // 2)
        ci = symbol.data.bone_index(core)
        hull_core = [sum(w for bi, _x, _y, w in row if bi == ci) for row in inf[:att.hull]]
        inner_core = [sum(w for bi, _x, _y, w in row if bi == ci) for row in inf[att.hull:]]
        assert max(hull_core) == 0
        assert max(inner_core) > 0.25
        assert max(len(row) for row in inf) <= 4

    scale = symbol.data.animations["volume_test"].bones[core]["scale"]
    assert len(scale) == 5
    assert qa.validate(symbol.data)["ok"]


def test_volume_layers_on_top_of_turn_weights(character):
    tr = rig.turn_rig(character, "head", "face", {"nose": 1.25})
    face = character.data.attachment("face")
    n = len(face.uvs) // 2
    before = decode_weighted(face.vertices, n)
    driven = character.data.bone_index(tr["face"]["driven_bone"])
    before_peak = max(sum(w for bi, _x, _y, w in row if bi == driven) for row in before)

    out = volume25d.rig_volume(character, ["face"], strength=0.55, name="face_volume", test_animation=False)
    assert out["parent"] == tr["face"]["driven_bone"]
    face = character.data.attachment("face")
    after = decode_weighted(face.vertices, n)
    driven = character.data.bone_index(tr["face"]["driven_bone"])
    core = character.data.bone_index(out["core"])
    after_turn = max(sum(w for bi, _x, _y, w in row if bi == driven) for row in after)
    after_core = max(sum(w for bi, _x, _y, w in row if bi == core) for row in after)
    assert before_peak > 0.6 and after_turn > 0.15 and after_core > 0.2
    assert max(len(row) for row in after) <= 4
    assert qa.validate(character.data)["ok"]


def test_volume_bounce_is_sparse_and_editable(symbol):
    out = volume25d.rig_volume(symbol, ["gem"], test_animation=False)
    res = volume25d.bounce(symbol, [out["core"]], "squish", duration=0.6, strength=0.2)
    a = symbol.data.animations["squish"]
    assert res["sparse"] and len(a.bones[out["core"]]["scale"]) == 5
    assert len(a.bones[out["core"]]["translatex"]) == 4
    assert any(k.curve is not None for k in a.bones[out["core"]]["scale"][:-1])
    assert qa.validate(symbol.data)["ok"]


def test_new_mcp_tools_are_registered_and_callable(tmp_path):
    from claude_spine.server import mcp
    from claude_spine import samples

    async def call(name, **args):
        res = await mcp.call_tool(name, args)
        content = res[0] if isinstance(res, tuple) else res
        return json.loads(content[0].text)

    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert {"rig_volume_2p5d", "volume_bounce", "optimize_animation"} <= names

    p = samples.make_symbol(tmp_path / "mcp")
    v = asyncio.run(call("rig_volume_2p5d", project=str(p.path), slots=["gem"], test_animation=False))
    assert v["core"]
    b = asyncio.run(call("volume_bounce", project=str(p.path), bones=[v["core"]], animation="vb"))
    assert b["sparse"] is True

    p = p.open(p.path)
    ab = AnimBuilder(p.data, "dense")
    ab.bone("root", "translatex", [(i / 30, 20 * math.sin(math.pi * i / 30)) for i in range(31)], "linear")
    p.save()
    o = asyncio.run(call("optimize_animation", project=str(p.path), animation="dense", mode="editable"))
    assert o["removed"] > 0
