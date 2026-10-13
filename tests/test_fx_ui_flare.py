"""UI flare family (fx_ui_flare): rim_glow_pulse, anamorphic_burst, ray_fan_beam, glyph_strike, banner_energy,
ember_drift, and the flame_wisps AE template."""
import json
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image

from claude_spine import ae_templates, fx_recipes as R, qa, runtime
from claude_spine.ir import new_skeleton
from claude_spine.project import Project
from test_fx_ambient import MOCK

NODE = shutil.which("node")
FAMILY = ["rim_glow_pulse", "anamorphic_burst", "ray_fan_beam", "glyph_strike", "banner_energy", "ember_drift"]


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 844, 708))


def _frames(d, n=4, w=64, h=32):
    d.mkdir()
    for i in range(n):                                  # light on black: a soft horizontal bar
        y, x = np.mgrid[0:h, 0:w]
        a = np.exp(-((y - h / 2) / 5.0) ** 2) * np.exp(-((x - w / 2) / (8.0 + 4 * i)) ** 2)
        Image.fromarray((np.dstack([a, a, a]) * 255).astype(np.uint8), "RGB").save(d / f"f_{i:02d}.png")
    return str(d)


def _run(proj, anim):
    proj.save()
    res = runtime.run(proj, animations=[anim], fps=30, geometry=True)
    assert res.get("ok", True) and not res.get("problems"), res.get("problems") or res.get("error")
    return res["animations"][anim]["frames"]


def test_family_is_registered_without_collisions():
    for n in FAMILY:
        d = R.RECIPES[n]
        assert d["fn"].__module__ == "claude_spine.fx_ui_flare" and d["summary"] and "roles" in d
    assert not set(FAMILY) & set(ae_templates.list_templates())
    assert "flame_wisps" in ae_templates.list_templates() and "flame_wisps" not in R.RECIPES


@pytest.mark.parametrize("name", FAMILY)
def test_every_recipe_validates_and_runs_in_spine_core(proj, name):
    res = R.apply(proj, name, x=20, y=-190)
    assert qa.validate(proj.data)["ok"] and res["slots"]
    fr = _run(proj, res["animation"])
    assert sum(len(f["draws"]) for f in fr) > 0
    assert f"fx_{name}" in {e.name for e in proj.data.animations[res["animation"]].events}


@pytest.mark.parametrize("name", FAMILY)
def test_the_colour_argument_changes_the_drawn_colour(tmp_path, name):
    seen = {}
    for col in ("", "00FF00"):
        p = Project(tmp_path / f"{name}{col}.json", new_skeleton("t", 844, 708))
        res = R.apply(p, name, color=col)
        fr = _run(p, res["animation"])
        seen[col] = {tuple(np.round(d["color"][:3], 2)) for f in fr for d in f["draws"]}
    assert (0.0, 1.0, 0.0) in seen["00FF00"] and (0.0, 1.0, 0.0) not in seen[""]


def test_one_shot_lengths_and_timing_match_the_clip(proj):
    lengths = {}
    for n in FAMILY:
        res = R.apply(proj, n, name=n)
        lengths[n] = proj.data.animations[res["animation"]].duration()
    assert lengths["rim_glow_pulse"] == pytest.approx(29 / 30, abs=1e-3)
    assert lengths["glyph_strike"] == pytest.approx(31 / 30, abs=1e-3)
    assert lengths["banner_energy"] == pytest.approx(1.8, abs=1e-3)
    assert lengths["ray_fan_beam"] == pytest.approx(2.8, abs=1e-3) and lengths["ember_drift"] == pytest.approx(4.0, abs=1e-3)
    an = proj.data.animations["fx_glyph_strike"]
    assert [e.time for e in an.events if e.name == "fx_glyph_strike_hit"] == [pytest.approx(0.2, abs=1e-3)]


def test_one_shots_retime_with_duration(proj):
    res = R.apply(proj, "rim_glow_pulse", duration=29 / 15)
    assert proj.data.animations[res["animation"]].duration() == pytest.approx(29 / 15, abs=1e-3)


def test_loops_close(proj):
    for n in ("ray_fan_beam", "ember_drift"):
        res = R.apply(proj, n)
        an = proj.data.animations[res["animation"]]
        for s, tl in an.slots.items():
            if "rgba" in tl and len(tl["rgba"]) > 2:
                a0, a1 = int(tl["rgba"][0].color[6:8], 16), int(tl["rgba"][-1].color[6:8], 16)
                assert abs(a0 - a1) <= 3, (n, s)
        for b, tl in an.bones.items():
            if "rotate" in tl:
                assert tl["rotate"][0].value == pytest.approx(tl["rotate"][-1].value, abs=0.05), (n, b)


def test_ae_parts_come_as_hints_or_imported_frames(proj, tmp_path):
    res = R.apply(proj, "rim_glow_pulse")
    h = res["ae_hint"]
    assert h["template"] == "ripple_glow" and h["params"]["look"] == "line" and h["params"]["origin"] == "rim"
    assert set(h["params"]) <= set(ae_templates.list_templates()["ripple_glow"]["params"])
    assert res["ripple"] is None
    frames = _frames(tmp_path / "ripple")
    res = R.apply(proj, "rim_glow_pulse", name="r2", color="2A8CFF", options={"ripple_frames": frames, "deep": "0A28A8"})
    sl = proj.data.slot(res["ripple"])
    assert sl.dark == "0A28A8" and sl.blend == "additive" and sl.color.startswith("2A8CFF")
    order = [s.name for s in proj.data.slots]
    assert order.index(res["slots"][0]) < order.index(res["ripple"]) < order.index(res["slots"][-1]), "kept in the run"
    assert "alpha" in proj.data.animations["fx_r2"].slots[res["ripple"]]
    b = R.apply(proj, "anamorphic_burst", options={"wisps_frames": _frames(tmp_path / "wisps")})
    assert b["ae_hint"]["template"] == "flame_wisps" and len(b["ae_hint"]["copies"]) == 3
    assert set(b["ae_hint"]["params"]) <= set(ae_templates.list_templates()["flame_wisps"]["params"])
    assert len(b["wisps"]) == 4 and len({proj.data.slot(s).dark for s in b["wisps"]}) == 2
    assert qa.validate(proj.data)["ok"]
    _run(proj, "fx_anamorphic_burst")


def test_glyph_strike_takes_your_glyph_and_reveals_a_secondary(proj, tmp_path):
    pic = tmp_path / "coin.png"
    Image.new("RGBA", (60, 60), (240, 200, 60, 255)).save(pic)
    res = R.apply(proj, "glyph_strike", art={"glyph": str(pic), "secondary": str(pic)})
    clip, lit = res["secondary"]
    att = proj.data.attachment(clip, "clip")
    assert att.type == "clipping" and att.end == lit
    assert proj.data.slot(lit).blend == "normal" and "fx/art_glyph_strike_glyph" in res["art"].values()
    fr = _run(proj, res["animation"])
    assert any(d["slot"] == lit for f in fr[8:] for d in f["draws"])
    none = R.apply(proj, "glyph_strike", name="g2", options={"secondary": None, "line_up": 0, "line_down": 0})
    assert none["secondary"] is None and len(none["slots"]) < len(res["slots"])


def test_banner_energy_draw_order_puts_late_slashes_over_the_bar(proj):
    res = R.apply(proj, "banner_energy")
    names = [s.name for s in proj.data.slots]
    bar = [n for n in names if "_bar" in n]
    slash = [n for n in names if "_slash" in n]
    assert len(bar) == 2 and len(slash) == 32
    assert names.index(slash[0]) < names.index(bar[0]) < names.index(slash[-1])
    assert res["coins"] == 12


def test_flame_wisps_template(tmp_path):
    meta = ae_templates.list_templates()["flame_wisps"]
    assert (meta["params"]["width"], meta["params"]["height"], meta["params"]["fps"]) == (768, 192, 30)
    assert meta["params"]["color"] == "808080" and meta["params"]["core"] == "FFFFFF", "grey by default: import tintable"
    src = open(ae_templates.build_script("flame_wisps", {"comp": "w1", "color": "FF8000"}, tmp_path)["script"]).read()
    for key in ('"ADBE Fractal Noise"', '"ADBE Turbulent Displace"', "TrackMatteType.ALPHA", '"ADBE Tritone"', '"ADBE Glo2"',
                '"mode":"additive"', '"tintable":true', "Offset Turbulence", "scale.setValue([-100, 100])"):
        assert key in src, key
    assert '"color": "FF8000"' in src


@pytest.mark.skipif(NODE is None, reason="Node not installed")
@pytest.mark.parametrize("opts", [{}, {"width": 512, "height": 128, "speed": 200, "color": "FF8000", "core": "FFF0C0"}])
def test_flame_wisps_runs_against_a_mock_after_effects(tmp_path, opts):
    r = ae_templates.build_script("flame_wisps", dict(opts, comp="wisps"), tmp_path)
    src = open(r["script"]).read().replace("var __r = (function", "AEFX.find = function (g, n) { return g.property(n); };\nvar __r = (function", 1)
    js = tmp_path / "run.js"
    js.write_text(MOCK + src + "\nconsole.log(JSON.stringify({ r: JSON.parse(__r), comps: rec.comps, ex: rec.expressions }));\n")
    p = subprocess.run([NODE, str(js)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    o = json.loads(p.stdout.strip().splitlines()[-1])
    assert o["r"]["comp"] == "wisps" and o["r"]["width"] == opts.get("width", 768) and o["r"]["frames"] == 27
    assert {"wisps_srcR", "wisps_srcL", "wisps_pair", "wisps"} <= set(o["comps"])
    assert any(str(opts.get("speed", 380)) in e for e in o["ex"])
