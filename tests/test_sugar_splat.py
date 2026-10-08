"""Melted-sugar splat: the simulation, the AE script (run against a small mock of the AE object model in Node), the
gloss pass, the no-AE preview and the two MCP tools."""
import asyncio
import json
import shutil
import subprocess

import numpy as np
import pytest
from scipy import ndimage

from claude_spine import fx_sugar_splat as SS
from claude_spine import samples
from claude_spine.project import Project

from test_ae_bridge import write_tiff

NODE = shutil.which("node")
SMALL = {"size": 600, "duration": 0.6, "globs": 6, "ligament": 3, "splits": [2, 2], "speed": [300, 700],
         "glob_size": [50, 80], "blur": 5, "seed": 3}


def _size(d, k=0):
    return (d["sc"][k][1] * d["sc"][k][2]) ** 0.5


def test_simulation_is_deterministic_and_inside_its_own_lives():
    a, b = SS.simulate(SMALL), SS.simulate(SMALL)
    assert a == b and len(a) > 6
    assert SS.simulate({**SMALL, "seed": 4}) != a
    for d in a:
        assert 0 <= d["t0"] < SMALL["duration"] and d["t1"] > d["t0"]
        for rows in (d["pos"], d["sc"], d["ro"]):
            ts = [r[0] for r in rows]
            assert ts == sorted(ts) and d["t0"] - 1e-6 <= ts[0] and ts[-1] <= d["t1"] + 1e-6
        assert d["g"] in SS.params_of(SMALL)["colors"]


def test_it_gets_smaller_by_breaking_up_not_by_shrinking():
    drops = SS.simulate({**SMALL, "duration": 2.0})
    globs = sorted(_size(d, -1) for d in drops if d["t0"] == 0 and len(d["sc"]) > 3)[-SMALL["globs"]:]
    later = [_size(d) for d in drops if d["t0"] > 0.3]
    assert later and np.mean(later) < 0.5 * np.mean(globs)            # the late pieces are fragments
    # a drop born from a split keeps its size through its flight (until its evaporating tail)
    split = [d for d in drops if 0.1 < d["t0"] < 0.3 and len(d["sc"]) > 4]
    assert split and all(abs(_size(d, 1) - _size(d, len(d["sc"]) // 2)) / _size(d, 1) < 0.25 for d in split)


def test_drops_stretch_along_their_flight_and_keep_their_area():
    d = max(SS.simulate(SMALL), key=lambda d: len(d["pos"]))
    (t0, x0, y0), (t1, x1, y1) = d["pos"][0], d["pos"][1]
    sx, sy = d["sc"][0][1], d["sc"][0][2]
    assert sx > sy                                                    # long axis = flight
    ang = np.degrees(np.arctan2(y1 - y0, x1 - x0))                    # AE: y down, rotation clockwise
    assert abs(((d["ro"][0][1] - ang) + 180) % 360 - 180) < 25


def test_unknown_param_is_a_clear_error():
    with pytest.raises(ValueError, match="unknown sugar_splat param"):
        SS.params_of({"colour": "FF0000"})


def test_metaballs_merge_close_drops_and_keep_far_ones_apart():
    P = {**SMALL, "colors": {"pink": "FF3FA8"}, "accents": []}

    def drop(x):
        return {"g": "pink", "t0": 0, "t1": 1, "pos": [[0, x, 300]], "sc": [[0, 40, 40]], "ro": [[0, 0]]}
    close = SS.frame([drop(280), drop(320)], 0.1, P, half=1)
    far = SS.frame([drop(150), drop(450)], 0.1, P, half=1)
    assert ndimage.label(close[..., 3] > 0.5)[1] == 1
    assert ndimage.label(far[..., 3] > 0.5)[1] == 2


def test_gloss_keeps_the_alpha_lights_the_top_left_and_stays_premultiplied():
    P = {**SMALL, "colors": {"pink": "FF3FA8"}, "accents": []}
    blob = {"g": "pink", "t0": 0, "t1": 1, "pos": [[0, 300, 300]], "sc": [[0, 160, 160]], "ro": [[0, 0]]}
    flat = SS.frame([blob], 0.1, P, half=1)
    out = SS.shade(flat)
    assert np.allclose(out[..., 3], flat[..., 3])
    assert (out[..., :3] <= out[..., 3:4] + 1e-6).all()
    lum = out[..., :3].sum(2)
    ys, xs = np.unravel_index(np.argmax(lum), lum.shape)
    assert xs < 300 and ys < 300                                      # the glint sits up-left of the centre
    assert out[..., :3].max() > 0.95                                   # a wet white highlight


def _js_mock():
    return r"""
var LOG = {comps: [], saved: null, alerts: [], levels: [], layers: 0};
function Prop(name) { this.name = name; this.matchName = name; this.propertyType = 0; this.value = null; }
Prop.prototype.setValue = function (v) { if (v === undefined || (typeof v === "number" && isNaN(v))) throw new Error("bad value " + this.name); this.value = v; };
Prop.prototype.setValuesAtTimes = function (t, v) { if (t.length !== v.length) throw new Error("length"); for (var i = 0; i < v.length; i++) this.setValue(v[i]); };
function Group(name, names) { this.name = name; this.matchName = name; this.propertyType = 1; this.kids = [];
  for (var i = 0; i < (names || []).length; i++) this.kids.push(new Prop(names[i])); this.numProperties = this.kids.length; }
Group.prototype.property = function (k) { if (typeof k === "number") return this.kids[k - 1];
  for (var i = 0; i < this.kids.length; i++) if (this.kids[i].name === k) return this.kids[i];
  var leaf = /^ADBE (Vector Ellipse Size|Vector Fill Color|Position|Scale|Rotate Z)$/.test(k);
  var g = leaf ? new Prop(k) : new Group(k, []);
  this.kids.push(g); this.numProperties = this.kids.length; return g; };
var FX = {"ADBE Turbulent Displace": ["Amount", "Size", "Evolution"], "ADBE Box Blur2": ["Blur Radius", "Iterations"],
  "ADBE Pro Levels2": ["Alpha Input Black", "Alpha Input White"], "ADBE Fill": ["Color"],
  "ADBE Bevel Alpha": ["Edge Thickness", "Light Angle", "Light Intensity"]};
Group.prototype.addProperty = function (m) {
  if (this.name === "ADBE Effect Parade") { if (!FX[m]) throw new Error("no effect " + m); var e = new Group(m, FX[m]);
    if (m === "ADBE Pro Levels2") LOG.levels.push(e); this.kids.push(e); this.numProperties = this.kids.length; return e; }
  var g = new Group(m, []); this.kids.push(g); this.numProperties = this.kids.length; return g; };
function Layer() { this.root = new Group("layer", []); this.inPoint = 0; this.outPoint = 0; }
Layer.prototype.property = function (k) { return this.root.property(k); };
function Comp(name) { this.name = name; this.n = 0; var self = this;
  this.layers = {addShape: function () { self.n++; LOG.layers++; return new Layer(); }, add: function () { self.n++; return new Layer(); }}; }
var PropertyType = {PROPERTY: 0};
function File(p) { this.fsName = p; }
var app = {project: {file: null, dirty: false, items: {addComp: function (n) { LOG.comps.push(n); return new Comp(n); }},
  save: function (f) { LOG.saved = f.fsName; }}, newProject: function () {}, open: function () {},
  beginSuppressDialogs: function () {}, endSuppressDialogs: function () {}};
function alert(s) { LOG.alerts.push(String(s)); }
"""


@pytest.mark.skipif(NODE is None, reason="Node not installed")
def test_ae_script_runs_against_a_mock_ae(tmp_path):
    src = SS.jsx(SMALL, "sugar_t", tmp_path / "sugar_t.aep")
    for i, line in enumerate(src.split("\n")):
        if not line.startswith("var D = "):
            assert line.count('"') % 2 == 0, f"line {i + 1}: a string spans lines"
    js = tmp_path / "run.js"
    js.write_text(_js_mock() + src + "\nconsole.log(JSON.stringify({comps: LOG.comps, saved: LOG.saved, layers: LOG.layers,"
                  "alerts: LOG.alerts, levels: LOG.levels.map(function (e) { return [e.kids[0].value, e.kids[1].value]; })}));",
                  encoding="utf-8")
    p = subprocess.run([NODE, str(js)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert not [c for c in out["comps"] if c.startswith("CLAUDE_ERR")], out["comps"]
    assert {"sugar_t_flat", "sugar_t_bevel"} <= set(out["comps"])
    assert out["layers"] == len(SS.simulate(SMALL))
    assert out["saved"].endswith("sugar_t.aep") and "all done" in out["alerts"][-1]
    assert out["levels"] and all(0 < lo < hi <= 1 for lo, hi in out["levels"])   # Levels takes 0..1 from a script


@pytest.mark.skipif(NODE is None, reason="Node not installed")
def test_ae_script_refuses_an_unsaved_project(tmp_path):
    src = SS.jsx(SMALL, "sugar_t", tmp_path / "sugar_t.aep")
    js = tmp_path / "run.js"
    js.write_text(_js_mock() + "app.project.dirty = true;\n" + src + "\nconsole.log(JSON.stringify(LOG.comps.length + ':' + LOG.saved + ':' + LOG.alerts[0]));",
                  encoding="utf-8")
    p = subprocess.run([NODE, str(js)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith('"0:null:') and "SAVE" in p.stdout


def _ae_frames(tmp_path, n=6):
    """`_flat`-like AE TIFFs: a pink blob growing, premultiplied."""
    d = tmp_path / "frames" / "sugar_t_flat"
    d.mkdir(parents=True)
    y, x = np.mgrid[0:96, 0:96]
    for i in range(n):
        a = (np.hypot(x - 48, y - 48) < 10 + 5 * i).astype(float)
        rgb = np.array([1.0, 0.25, 0.66])[None, None] * a[..., None]
        write_tiff(d / f"f_{i:05d}.tif", np.dstack([rgb, a]))
    (d / "meta.json").write_text(json.dumps({"fps": 30, "width": 96, "height": 96}))
    return d


def test_shade_frames_turns_ae_tiffs_into_glossed_pngs(tmp_path):
    from PIL import Image
    r = SS.shade_frames(_ae_frames(tmp_path), tmp_path / "shaded", px=2.0)
    assert r["frames"] == 6 and r["px"] == 2.0 and r["fps"] == 30
    im = np.asarray(Image.open(tmp_path / "shaded" / "f_00005.png")).astype(float) / 255
    assert im.shape == (96, 96, 4) and im[48, 48, 3] == 1.0 and im[2, 2, 3] == 0
    assert im[..., :3][im[..., 3] > 0.5].max() > 0.95                 # glossed: a white glint on the pink


def _call(tool, args):
    from claude_spine.server import mcp
    out = asyncio.run(mcp.call_tool(tool, args))
    return json.loads((out[0] if isinstance(out, tuple) else out)[0].text)


def test_sugar_splat_ae_tool_writes_the_script_and_a_preview(tmp_path):
    r = _call("sugar_splat_ae", {"out_dir": str(tmp_path), "comp": "goo", "params": SMALL})
    assert r["comps"] == ["goo_flat", "goo_bevel"] and r["save_as"].endswith("goo.aep")
    assert (tmp_path / "goo.jsx").exists() and r["run_with"].startswith("return String($.evalFile(")
    assert r["preview"]["frames"] == round(SMALL["duration"] * 30) and (tmp_path / "preview" / "sugar_splat_preview.gif").exists()
    quiet = _call("sugar_splat_ae", {"out_dir": str(tmp_path), "comp": "goo", "params": SMALL, "preview": False,
                                     "alerts": False})
    assert '"alerts":false' in (tmp_path / "goo.jsx").read_text() and "preview" not in quiet


def test_sugar_splat_to_spine_lands_the_burst_and_mirrors(tmp_path):
    proj = str(samples.make_symbol(tmp_path / "gem").path)
    frames = _ae_frames(tmp_path)
    r = _call("sugar_splat_to_spine", {"project": proj, "animation": "boom", "at": 0.5, "frames_dir": str(frames),
                                       "scale": 2.0, "mirror": True, "max_size": 64})
    assert r["mirrored"] and r["shaded"].endswith("sugar_t_flat_shaded")
    p = Project.open(proj)
    anim = p.data.animations["boom"]
    assert r["slot"] in anim.slots or any(r["slot"] in s for s in anim.attachments.values())
    sc = anim.bones[r["bone"]]["scale"][0]
    assert sc.x == -1 and sc.y == 1
    with pytest.raises(Exception):
        _call("sugar_splat_to_spine", {"project": proj, "animation": "boom", "at": 0.5})
