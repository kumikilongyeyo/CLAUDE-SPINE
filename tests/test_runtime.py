"""The official spine-core runtime must load everything we write."""
import json

import numpy as np
from PIL import Image

from claude_spine import atlas, fx, juice, render, rig, runtime
from claude_spine.mesh import rig_mesh
from claude_spine.timeline import AnimBuilder
from conftest import needs_node


@needs_node
def test_full_character_loads_and_plays(character, tmp_path):
    p = character
    sk = p.data
    rig_mesh(p, "arm_l", bones=["arm_l1", "arm_l2"])
    rig_mesh(p, "body", bones=["hip", "chest"])
    rig.add_ik(sk, ["arm_l1", "arm_l2"])
    rig.rig_strand(p, "lock_l", n_bones=3)
    rig.rig_strand(p, "cape", n_bones=3, physics="cloth")
    rig.turn_rig(p, "head", "face", {"nose": 1.25, "eye_l": 0.9, "eye_r": 0.9, "ear_r": -0.35})
    juice.apply(p, fx=True, shine_slot="body")
    fx.generate(p, "explosion")
    fx.generate(p, "coin_burst")
    p.save()
    res = runtime.run(p, fps=15)
    assert res["ok"], res.get("error") or res["problems"][:3]
    assert set(res["animations"]) == set(sk.animations)
    assert any(e["name"] == "sfx_win" for e in res["animations"]["win"]["events"])


@needs_node
def test_ik_reaches_its_target_in_the_runtime(arm):
    rig_mesh(arm, "arm")
    r = rig.add_ik(arm.data, ["upper", "fore"])
    AnimBuilder(arm.data, "reach").bone(r["target"], "translate", [(0, 0, 0), (1, -60, 90)])
    dump = runtime.run(arm, animations=["reach"], fps=2, geometry=True)
    assert dump["ok"]
    last = dump["animations"]["reach"]["frames"][-1]
    v = np.asarray(last["draws"][0]["v"]).reshape(-1, 2)
    # the arm bent: its far end rose ~90 px and came ~60 px closer
    assert v[:, 1].max() > 60


@needs_node
def test_preview_renders_pixels(symbol, tmp_path):
    juice.apply(symbol, ["win"])
    fx.generate(symbol, "shine_sweep", slot="gem", into="win")
    dump = runtime.run(symbol, animations=["win"], fps=10, geometry=True)
    out = render.render_animation(dump, "win", tmp_path, size=128)
    im = Image.open(out["sheet"]).convert("RGBA")
    assert np.asarray(im)[..., :3].std() > 10


@needs_node
def test_packed_atlas_with_offsets_loads(symbol, tmp_path):
    rig_mesh(symbol, "gem")
    res = atlas.pack(symbol, tmp_path / "exp", strip=True, pma=True)
    text = open(res["atlas"]).read()
    assert "pma: true" in text and "bounds:" in text
    out = runtime.run(symbol, atlas_path=res["atlas"], fps=5)
    assert out["ok"], out
