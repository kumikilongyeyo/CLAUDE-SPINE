"""speed_lines (Spine), the fire_aura AE template (a composite of the fire template), and sequences that follow a
rotated parent bone."""
import json
import math
import shutil
import subprocess

import numpy as np
import pytest

from claude_spine import ae_bridge as B, ae_templates, fx_recipes as R, qa
from claude_spine.ir import Bone, new_skeleton
from claude_spine.project import Project
from test_fx_ambient import MOCK

NODE = shutil.which("node")


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 1200))


def test_speed_lines_redraw_on_stepped_keys(proj):
    res = R.apply(proj, "speed_lines", count=8, options={"rate": 10.0})
    assert res["lines"] == 8 and res["redraws"] == 27 and qa.validate(proj.data)["ok"]
    an = proj.data.animations["fx_speed_lines"]
    for b, tl in an.bones.items():
        for k in tl["translate"][:-1]:
            assert k.curve == "stepped"
    times = [k.time for k in next(iter(an.bones.values()))["translate"]]
    assert np.allclose(np.diff(times), 0.1, atol=1e-3)
    assert all(s.blend == "additive" for s in proj.data.slots)


def test_speed_lines_rush_in_and_brighten_at_the_hit(proj):
    R.apply(proj, "speed_lines", count=40, options={"hit": 1.3, "rate": 20.0})
    an = proj.data.animations["fx_speed_lines"]
    assert "fx_speed_lines_hit" in {e.name for e in an.events}

    def stat(t0, t1):
        rr, aa = [], []
        for b, tl in an.bones.items():
            rr += [math.hypot(k.x or 0, k.y or 0) for k in tl["translate"] if t0 <= k.time <= t1]
        for s, tl in an.slots.items():
            aa += [int(k.color[6:8], 16) for k in tl["rgba"] if t0 <= k.time <= t1]
        return np.mean(rr), np.mean(aa)
    r_hit, a_hit = stat(1.25, 1.35)
    r_far, a_far = stat(0.0, 0.6)
    assert r_hit < r_far * 0.8 and a_hit > a_far * 1.3


def test_fire_aura_inlines_the_fire_template(tmp_path):
    meta = ae_templates.list_templates()["fire_aura"]
    assert meta["uses"] == ["fire"] and meta["params"]["size"] == 512
    src = open(ae_templates.build_script("fire_aura", {"comp": "a1"}, tmp_path)["script"]).read()
    assert "AEFX.T_fire = function (P)" in src and "AEFX.D_fire = " in src
    assert src.index("AEFX.T_fire") < src.index("var __r = (function")
    plain = open(ae_templates.build_script("fire", {}, tmp_path)["script"]).read()
    assert "AEFX.T_" not in plain, "templates without `uses` are unchanged"


@pytest.mark.skipif(NODE is None, reason="Node not installed")
@pytest.mark.parametrize("opts", [{}, {"hot": "F0FFFF", "mid": "3AA8FF", "cool": "1030B0", "size": 256}])
def test_fire_aura_runs_against_a_mock_after_effects(tmp_path, opts):
    r = ae_templates.build_script("fire_aura", dict(opts, comp="aura"), tmp_path)
    src = open(r["script"]).read().replace("var __r = (function", "AEFX.find = function (g, n) { return g.property(n); };\nvar __r = (function", 1)
    js = tmp_path / "run.js"
    js.write_text(MOCK + src + "\nconsole.log(JSON.stringify({ r: JSON.parse(__r), comps: rec.comps }));\n")
    p = subprocess.run([NODE, str(js)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    o = json.loads(p.stdout.strip().splitlines()[-1])
    S = opts.get("size", 512)
    assert o["r"]["comp"] == "aura" and o["r"]["width"] == S and o["r"]["mode"] == "alpha" and o["r"]["seq_mode"] == "loop"
    assert {"aura_strip", "aura_mirror", "aura_square", "aura"} <= set(o["comps"])


def test_a_sequence_follows_a_rotated_parent(proj, tmp_path):
    from PIL import Image
    d = tmp_path / "frames"
    d.mkdir()
    for i in range(3):
        Image.new("RGBA", (40, 20), (255, 255, 255, 255)).save(d / f"f_{i}.png")
    proj.data.bones.append(Bone(name="aim", parent="root", x=100, y=50, rotation=90, scaleX=2, scaleY=1))
    res = B.fx_to_spine(proj, "flame", frames_dir=str(d), fps=24, parent="aim", x=10, y=0)
    bn = next(b for b in proj.data.bones if b.name == res["bone"])
    assert (bn.parent, bn.x, bn.y, bn.rotation) == ("aim", 10, 0, 0)
    w = proj.data.world()[bn.name]
    assert w.to_world(0, 0) == pytest.approx((100, 70), abs=1e-6), "x=10 along a parent turned 90 deg and scaled 2"
    with pytest.raises(ValueError, match="no bone"):
        B.fx_to_spine(proj, "flame2", frames_dir=str(d), fps=24, parent="nope")
