"""Magic button family (fx_magic_button) and its AE templates (energy_burst, edge_aura)."""
import json
import math
import shutil
import subprocess

import numpy as np
import pytest
from PIL import Image, ImageDraw

from claude_spine import ae_templates, fx_recipes as R, qa, runtime
from claude_spine import fx_magic_button as M
from claude_spine.ir import new_skeleton
from claude_spine.project import Project
from conftest import needs_node
from test_fx_ambient import MOCK

NODE = shutil.which("node")
# the shared mock lacks Layer.moveBefore (win_aura-style mattes use it): add it, checking its argument
MOCK_MB = MOCK + 'Node.prototype.moveBefore = function (l) { if (!(l instanceof Node)) throw new Error("moveBefore"); };\n'
FAMILY = ["magic_circle", "disc_flash", "rim_pulse", "silhouette_halo", "icon_spin", "bar_flood", "mote_loop"]


@pytest.fixture
def proj(tmp_path):
    return Project(tmp_path / "t.json", new_skeleton("t", 720, 720))


def _sil_png(path, n=200):
    im = Image.new("RGBA", (n, n), (0, 0, 0, 0))
    ImageDraw.Draw(im).rounded_rectangle([50, 60, 150, 140], 12, fill=(255, 255, 255, 255))
    im.save(path)
    return str(path)


def test_names_are_new_and_registered():
    assert set(FAMILY) <= set(R.RECIPES)
    assert {"energy_burst", "edge_aura"} <= set(ae_templates.list_templates())
    for n in FAMILY:
        assert R.RECIPES[n]["roles"] and R.RECIPES[n]["summary"]


@needs_node
@pytest.mark.parametrize("name", FAMILY)
def test_each_recipe_validates_and_plays(proj, name):
    res = R.apply(proj, name)
    assert qa.validate(proj.data)["ok"]
    assert all(s.attachment is None for s in proj.data.slots)
    proj.save()
    dump = runtime.run(proj, animations=[res["animation"]], fps=15, geometry=True)
    assert dump.get("ok", True) and not dump.get("problems")
    drawn = [d for f in dump["animations"][res["animation"]]["frames"] for d in f["draws"]]
    assert drawn, f"{name} draws nothing"


def _drawn_colours(proj, anim):
    proj.save()
    dump = runtime.run(proj, animations=[anim], fps=15, geometry=True)
    return [tuple(round(c, 3) for c in d["color"][:3]) for f in dump["animations"][anim]["frames"] for d in f["draws"]]


@needs_node
@pytest.mark.parametrize("name,col", [("magic_circle", "FF3366"), ("disc_flash", "3366FF"), ("rim_pulse", "FFAA00"),
                                      ("silhouette_halo", "AA00FF"), ("icon_spin", "00FF88"), ("bar_flood", "FF8800"),
                                      ("mote_loop", "FF0000")])
def test_the_colour_param_changes_the_drawn_colour(proj, name, col):
    res = R.apply(proj, name, color=col)
    want = tuple(round(int(col[i:i + 2], 16) / 255, 3) for i in (0, 2, 4))
    assert want in _drawn_colours(proj, res["animation"])


def test_silhouette_art_is_derived_into_rim_and_halo(proj, tmp_path):
    f = _sil_png(tmp_path / "sil.png")
    r1 = R.apply(proj, "rim_pulse", art={"silhouette": f}, options={"size": 400.0, "disc": False})
    assert r1["art"] == {"silhouette": "derived"} and len(r1["slots"]) == 1
    tex = proj.data.attachment(r1["slots"][0], next(iter(proj.data.skin("default").attachments[r1["slots"][0]]))).path
    assert tex.startswith("fx/mbtn_rim_") and tex != "fx/mbtn_rim_medallion"
    a = np.asarray(proj.image(tex), np.float32)[..., 3]
    assert a[100, 100] == 0, "nothing inside the subject"
    row = a[100, 150:200]                                     # outward from the right edge (x = 150)
    peak = int(np.argmax(row))
    assert 2 <= peak <= 12 and row[peak] > 200, "the rim peaks just outside the edge"
    R.apply(proj, "silhouette_halo", art={"silhouette": f}, options={"size": 400.0})
    assert qa.validate(proj.data)["ok"]
    with pytest.raises(ValueError, match="unknown art role"):
        R.apply(proj, "rim_pulse", art={"outline": f})


def test_magic_circle_snaps_open_and_arcs_spread(proj):
    res = R.apply(proj, "magic_circle")
    an = proj.data.animations[res["animation"]]
    ring = res["group_bone"].replace("fx_magic_circle", "fx_magic_circle_ring")
    sc = an.bones[ring]["scale"]
    assert sc[0].x == pytest.approx(0.62) and sc[2].x == pytest.approx(1.0) and sc[2].time == pytest.approx(0.04)
    arcs = [b for b in proj.data.bones if "_arc" in b.name]
    assert sorted(b.rotation for b in arcs) == [0.0, 180.0]
    for b in arcs:                                            # keys are offsets from the setup angle
        k = an.bones[b.name]["rotate"]
        assert k[0].value == pytest.approx(40.0) and k[-1].value == pytest.approx(40.0 - 160.0)


def test_disc_flash_curves(proj):
    r = R.apply(proj, "disc_flash")
    assert r["curve"] == "press" and proj.data.slots[-1].blend == "normal"
    att = proj.data.animations[r["animation"]].slots[r["slots"][0]]["attachment"]
    assert att[-1].name is None and att[-1].time == pytest.approx(43 / 30, abs=1e-3)
    r2 = R.apply(proj, "disc_flash", options={"curve": "ready"}, name="rdy")
    att2 = proj.data.animations[r2["animation"]].slots[r2["slots"][0]]["attachment"]
    assert att2[-1].name is not None, "ready holds"
    with pytest.raises(ValueError, match="press' or 'ready"):
        R.apply(proj, "disc_flash", options={"curve": "nope"}, name="bad")


def test_icon_spin_is_one_turn_clockwise(proj):
    r = R.apply(proj, "icon_spin", options={"speed": 720.0, "smears": 3})
    assert r["loop"] == pytest.approx(0.5) and len(r["slots"]) == 4
    an = proj.data.animations[r["animation"]]
    spin = [b for b in an.bones if b.endswith("_spin")][0]
    keys = an.bones[spin]["rotate"]
    assert keys[-1].value == pytest.approx(-360.0) and keys[-1].time == pytest.approx(0.5)
    sm = sorted(b.rotation for b in proj.data.bones if "_smear" in b.name)
    assert sm == pytest.approx([6.5, 13.0, 19.5]), "copies trail behind a clockwise turn"


def test_bar_flood_fill_follows_the_stops(proj):
    stops = [[0.0, "0000FF"], [1.0, "0000FF"]]
    r = R.apply(proj, "bar_flood", options={"stops": stops})
    fill = [s for s in r["slots"] if proj.data.slot(s).blend == "normal"][0]
    path = proj.data.attachment(fill, next(iter(proj.data.skin("default").attachments[fill]))).path
    px = np.asarray(proj.image(path))[2, 140]
    assert px[0] < 10 and px[1] < 10 and px[2] > 245, "row 2 is the stop colour"


def test_mote_loop_is_exact(proj):
    r = R.apply(proj, "mote_loop", count=5)
    an = proj.data.animations[r["animation"]]
    L = r["loop"]
    for s in r["slots"]:
        ks = an.slots[s]["rgba"]
        assert ks[0].time == 0 and ks[-1].time == pytest.approx(L)
        assert abs(int(ks[0].color[6:8], 16) - int(ks[-1].color[6:8], 16)) <= 2


# ---------------------------------------------------------------- AE templates
@pytest.mark.parametrize("name", ["energy_burst", "edge_aura"])
def test_templates_header_and_key_effects(tmp_path, name):
    meta = ae_templates.list_templates()[name]
    assert "additive" in meta["doc"] and {"color", "light", "art", "art_scale", "seed"} <= set(meta["params"])
    src = open(ae_templates.build_script(name, {"color": "FF00FF"}, tmp_path)["script"]).read()
    for k in ('"ADBE Fractal Noise"', '"CC Radial Fast Blur"', '"ADBE Turbulent Displace"', '"ADBE Tritone"',
              "TrackMatteType.ALPHA", '"ADBE Box Blur2"', "medallion", '"FF00FF"'):
        assert k in src, k
    if name == "edge_aura":
        assert "AEFX.loopify(src" in src and '"seq_mode":"loop"' in src
    else:
        assert '"hit_ae":' in src and "[0.47, H * 1.05]" in src


@pytest.mark.skipif(NODE is None, reason="Node not installed")
@pytest.mark.parametrize("name,opts", [("energy_burst", {}), ("energy_burst", {"size": 384, "plateau": 0.2}),
                                       ("edge_aura", {}), ("edge_aura", {"duration": 2.0, "reach": 120})])
def test_templates_run_against_a_mock_after_effects(tmp_path, name, opts):
    r = ae_templates.build_script(name, dict(opts, comp="t1"), tmp_path)
    src = open(r["script"]).read()
    js = tmp_path / "chk.js"
    js.write_text(src)
    assert subprocess.run([NODE, "--check", str(js)], capture_output=True).returncode == 0
    src = src.replace("var __r = (function", "AEFX.find = function (g, n) { return g.property(n); };\nvar __r = (function", 1)
    D = r["params"]["duration"]
    js.write_text(MOCK_MB + src + f"""
const out = [];
for (const e of rec.expressions) {{
  const f = new Function("time", "value", "return (" + e + ");");
  out.push([0, {D / 2}, {D}].map((t) => f(t, [10, 20])));
}}
console.log(JSON.stringify({{ r: JSON.parse(__r), ex: out, comps: rec.comps }}));
""")
    p = subprocess.run([NODE, str(js)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr[-2000:]
    o = json.loads(p.stdout.strip().splitlines()[-1])
    assert o["r"]["comp"] == "t1" and o["r"]["mode"] == "additive"
    assert o["r"]["frames"] == round(D * r["params"]["fps"]) and o["r"]["width"] == r["params"]["size"]
    assert {"t1_sil", "t1_src"} <= set(o["comps"])
    for vals in o["ex"]:
        flat = [x for v in vals for x in (v if isinstance(v, list) else [v])]
        assert all(isinstance(x, (int, float)) and math.isfinite(x) for x in flat)
    if name == "edge_aura":
        assert o["r"]["seq_mode"] == "loop"
    else:
        assert o["r"]["hit_ae"] == pytest.approx(2 / r["params"]["fps"])
