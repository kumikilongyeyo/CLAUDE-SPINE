"""Magic smoke puff: the simulation (small and fast here), the AE look script (run against a mock of the AE object
model in Node), the no-AE preview, the Spine import (smoke sequence + lights + glitter) and the two MCP tools."""
import asyncio
import json
import shutil
import subprocess

import numpy as np
import pytest

from claude_spine import fx_magic_puff as MP
from claude_spine import runtime, samples
from claude_spine.project import Project

from test_ae_bridge import write_tiff

NODE = shutil.which("node")
TINY = {"res": 0.06, "t_end": 0.8, "fps": 12, "sub": 2, "glitter": 3, "linger_t": [0.3, 0.7], "stop": 0.6}


@pytest.fixture(scope="module")
def sim(tmp_path_factory):
    d = tmp_path_factory.mktemp("puff") / "sim"
    meta = MP.simulate(d, TINY)
    return d, meta


def _pass(d, kind, i):
    from PIL import Image
    return np.asarray(Image.open(d / kind / f"{kind}_{i:04d}.png")).astype(float) / 65535


def test_unknown_param_is_a_clear_error():
    with pytest.raises(ValueError, match="unknown magic_puff param"):
        MP.params_of({"colour": "FF0000"})
    assert MP.params_of({})["cx"] == MP.DEFAULTS["width"] / 2


def test_simulation_bursts_out_both_ways_without_a_mirror(sim):
    d, meta = sim
    assert meta["frames"] == round(TINY["t_end"] * TINY["fps"]) + 1
    w, h = meta["pass_size"]
    assert (w, h) == (round(2172 * TINY["res"]), round(724 * TINY["res"]))
    assert _pass(d, "op", 0).max() == 0                              # from nothing
    last = _pass(d, "op", meta["frames"] - 1)
    left, right = last[:, : w // 2], last[:, w - w // 2:]
    assert left.sum() > 1 and right.sum() > 1                        # it went out both ways
    assert np.abs(left - right[:, ::-1]).mean() > 1e-3               # each side its own turbulence: not a mirror
    # heat = freshness: the smoke cools as it ages (no source by the end)
    assert _pass(d, "heat", meta["frames"] - 1).sum() < _pass(d, "op", meta["frames"] - 1).sum()


def test_simulation_is_deterministic(tmp_path, sim):
    d, meta = sim
    again = MP.simulate(tmp_path / "again", TINY)
    assert again["glitter"] == meta["glitter"]
    assert np.array_equal(_pass(d, "op", 6), _pass(tmp_path / "again", "op", 6))


def test_glitter_rides_the_flow_on_both_sides(sim):
    _, meta = sim
    gl = [g for g in meta["glitter"] if g["path"]]
    assert {g["side"] for g in gl} == {-1, 1} and len(gl) == 2 * TINY["glitter"]
    for g in gl:
        ts = [p[0] for p in g["path"]]
        assert ts == sorted(ts) and ts[0] >= g["t0"] - 1 / TINY["fps"]
    cx = MP.params_of(TINY)["cx"]
    for g in gl:                                                      # flung outward on its own side
        assert (g["path"][-1][1] - cx) * g["side"] > 0


def _js_mock():
    return r"""
var LOG = {comps: [], saved: null, alerts: [], keys: {}, imports: [], mattes: 0};
function Prop(name) { this.name = name; this.matchName = name; this.propertyType = 0; this.value = null; }
Prop.prototype.setValue = function (v) { if (v === undefined || (typeof v === "number" && isNaN(v))) throw new Error("bad value " + this.name); this.value = v; };
Prop.prototype.setValuesAtTimes = function (t, v) { if (t.length !== v.length) throw new Error("length " + this.name);
  for (var i = 0; i < v.length; i++) this.setValue(v[i]); LOG.keys[this.name] = v; };
function Group(name, names) { this.name = name; this.matchName = name; this.propertyType = 1; this.kids = [];
  for (var i = 0; i < (names || []).length; i++) this.kids.push(new Prop(names[i])); this.numProperties = this.kids.length; }
Group.prototype.property = function (k) { if (typeof k === "number") return this.kids[k - 1];
  for (var i = 0; i < this.kids.length; i++) if (this.kids[i].name === k) return this.kids[i];
  var g = new Group(k, []); this.kids.push(g); this.numProperties = this.kids.length; return g; };
var FX = {"ADBE Tritone": ["Highlights", "Midtones", "Shadows"],
  "ADBE Pro Levels2": ["ADBE Pro Levels2-0004", "ADBE Pro Levels2-0005", "ADBE Pro Levels2-0006", "ADBE Pro Levels2-0008"],
  "ADBE Glo2": ["Glow Threshold", "Glow Radius", "Glow Intensity"], "ADBE Gaussian Blur 2": ["Blurriness"]};
Group.prototype.addProperty = function (m) {
  if (!FX[m]) throw new Error("no effect " + m); var e = new Group(m, FX[m]); this.kids.push(e); this.numProperties = this.kids.length; return e; };
function Layer(src) { this.src = src; this.name = ""; this.fx = new Group("ADBE Effect Parade", []); this.opacity = new Prop("Opacity");
  this.enabled = true; this.adjustmentLayer = false; this.blendingMode = 0; }
Layer.prototype.property = function (k) { if (k === "ADBE Effect Parade") return this.fx; throw new Error("no " + k); };
Layer.prototype.setTrackMatte = function (m, t) { if (!m || t === undefined) throw new Error("matte"); LOG.mattes++; };
Layer.prototype.moveBefore = function () {};
function Comp(name) { this.name = name; var self = this;
  this.layers = {addSolid: function () { return new Layer(null); }, add: function (src) { if (!src) throw new Error("add nothing"); return new Layer(src); }}; }
var PropertyType = {PROPERTY: 0};
var BlendingMode = {ADD: 2}, TrackMatteType = {LUMA: 3};
function File(p) { this.fsName = p; }
function ImportOptions(f) { this.file = f; this.sequence = false; }
var app = {project: {file: null, dirty: false, bitsPerChannel: 8,
  items: {addComp: function (n) { LOG.comps.push(n); return new Comp(n); }},
  importFile: function (io) { if (!io.sequence) throw new Error("not a sequence"); LOG.imports.push(io.file.fsName); return {mainSource: {}, name: ""}; },
  save: function (f) { LOG.saved = f.fsName; }}, newProject: function () {}, open: function () {},
  beginSuppressDialogs: function () {}, endSuppressDialogs: function () {}};
function alert(s) { LOG.alerts.push(String(s)); }
"""


@pytest.mark.skipif(NODE is None, reason="Node not installed")
def test_ae_script_runs_against_a_mock_ae(tmp_path, sim):
    d, meta = sim
    src = MP.jsx(meta["params"], "puff_t", tmp_path / "puff_t.aep", d)
    for i, line in enumerate(src.split("\n")):
        if not line.startswith("var D = "):
            assert line.count('"') % 2 == 0, f"line {i + 1}: a string spans lines"
        assert "var long" not in line                                 # ExtendScript is ES3
    js = tmp_path / "run.js"
    js.write_text(_js_mock() + src + "\nLOG.status = STATUS; console.log(JSON.stringify(LOG));", encoding="utf-8")
    p = subprocess.run([NODE, str(js)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert not [c for c in out["comps"] if c.startswith("CLAUDE_ERR")], out["comps"]
    assert {"puff_t_drive", "puff_t_colour", "puff_t_full", "puff_t_master"} <= set(out["comps"])
    assert len(out["imports"]) == 3 and all(f.endswith("_0000.png") for f in out["imports"])
    assert out["saved"].endswith("puff_t.aep") and "all done" in out["alerts"][-1] and out["mattes"] == 1
    assert src.rstrip().endswith("STATUS;") and out["status"].endswith("all done")   # what an MCP run gets back
    k = out["keys"]
    lo, hi = k["ADBE Pro Levels2-0004"], k["ADBE Pro Levels2-0005"]   # the erosion never crosses black over white
    assert all(b - a > 0.1 for a, b in zip(lo, hi)) and k["ADBE Pro Levels2-0008"][-1] < 1


@pytest.mark.skipif(NODE is None, reason="Node not installed")
def test_ae_script_refuses_an_unsaved_project(tmp_path, sim):
    d, meta = sim
    src = MP.jsx(meta["params"], "puff_t", tmp_path / "puff_t.aep", d)
    js = tmp_path / "run.js"
    js.write_text(_js_mock() + "app.project.dirty = true;\n" + src + "\nconsole.log(JSON.stringify(LOG.comps.length + ':' + LOG.saved + ':' + LOG.alerts[0] + ':' + STATUS));",
                  encoding="utf-8")
    p = subprocess.run([NODE, str(js)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert p.stdout.startswith('"0:null:') and "SAVE" in p.stdout and "NOT built" in p.stdout


def test_preview_is_the_look_without_ae(tmp_path, sim):
    d, meta = sim
    r = MP.preview(meta["params"], d, tmp_path / "pv", width=200)
    assert (tmp_path / "pv" / "magic_puff_preview.png").exists() and (tmp_path / "pv" / "magic_puff_preview.gif").exists()
    assert r["frames"] == (meta["frames"] + 1) // 2 and len(r["moments"]) == 8
    pm = MP.look_frame(meta["params"], np.full((4, 4), 0.6), np.zeros((4, 4)), np.full((4, 4), 0.5), 0.5)
    assert pm.shape == (4, 4, 4) and np.all(pm[..., :3] <= pm[..., 3:4] + 1e-9)     # premultiplied
    late = MP.look_frame(meta["params"], np.full((4, 4), 0.6), np.zeros((4, 4)), np.full((4, 4), 0.5), 3.74)
    assert late[..., 3].max() < 0.1                                   # dissolved by the end


def _ae_frames(tmp_path, meta, n=10, full=False):
    """`_full`-like AE TIFFs: a teal band growing from the centre (full: across the whole comp), premultiplied."""
    d = tmp_path / "frames" / ("full" if full else "puff_t_full")
    d.mkdir(parents=True)
    w, h = meta["pass_size"]
    y, x = np.mgrid[0:h, 0:w]
    for i in range(n):
        a = (((np.abs(x - w / 2) < 4 + i * w / (2.2 * n)) | full) & (np.abs(y - h / 2) < h / 5)).astype(float)
        write_tiff(d / f"f_{i:05d}.tif", np.dstack([np.array([0.01, 0.6, 0.45])[None, None] * a[..., None], a]))
    (d / "meta.json").write_text(json.dumps({"fps": 12, "width": w, "height": h}))
    return d


def _call(tool, args):
    from claude_spine.server import mcp
    out = asyncio.run(mcp.call_tool(tool, args))
    return json.loads((out[0] if isinstance(out, tuple) else out)[0].text)


def test_to_spine_lands_the_smoke_the_lights_and_the_glitter(tmp_path, sim):
    d, meta = sim
    proj = str(samples.make_symbol(tmp_path / "banner").path)
    frames = _ae_frames(tmp_path, meta)
    r = _call("magic_puff_to_spine", {"project": proj, "frames_dir": str(frames), "sim_dir": str(d), "fps": 12,
                                      "max_size": 96, "scale": 0.5})
    p = Project.open(proj)
    anim = p.data.animations["magic_puff"]
    smoke = r["smoke"]
    assert smoke["slot"] in anim.attachments.get("default", {}) or smoke["slot"] in str(anim.attachments)
    assert smoke["playback_fps"] == 12 and smoke["image_size"][0] <= 96
    order = [s.name for s in p.data.slots]
    lights = [s for s in r["slots"]]
    assert lights and all(order.index(s) > order.index(smoke["slot"]) for s in lights)   # the lights draw over the smoke
    assert r["glitter"] == 2 * TINY["glitter"] and r["rays"] and r["lights"]
    # banner size in units = width x scale: the smoke attachment spans the banner
    att = p.data.skins[0].attachments[smoke["slot"]]["fx"]
    assert abs(att.width - 2172 * 0.5) < 2
    if runtime.available():
        res = runtime.load_check(p)
        assert res["ok"], res
        # the lights DRAW (slots that are never attached pass every structural check and show nothing)
        dump = runtime.run(p, animations=["magic_puff"], fps=10, geometry=True)
        drawn = {f["t"]: {d["slot"] for d in f["draws"] if d["color"][3] > 0.02}
                 for f in dump["animations"]["magic_puff"]["frames"]}
        at = lambda t: drawn[min(drawn, key=lambda k: abs(k - t))]  # noqa: E731
        for part in ("line", "glint", "flare", "star", "rays", "glow"):
            assert any(part in s for s in at(0.6)), (part, sorted(at(0.6)))
        assert any("pop" in s for s in at(0.2)) and any("glit" in s for ss in drawn.values() for s in ss)
        assert not any(k in s for s in at(max(drawn)) for k in ("line", "flare", "rays"))   # gone by the end


def _first_sprite_alpha(proj, slot):
    p = Project.open(proj)
    att = p.data.attachment(slot, "fx")
    a = np.asarray(p.image(f"{att.path}{att.sequence.start:0{att.sequence.digits}d}"))[..., 3].max(0) / 255
    return a, np.abs((np.arange(len(a)) + 0.5) / len(a) * 2172 - 1086)


def test_to_spine_thins_the_smoke_out_toward_the_ends(tmp_path, sim):
    d, meta = sim
    frames = str(_ae_frames(tmp_path, meta, full=True))
    proj = str(samples.make_symbol(tmp_path / "ends").path)
    r = _call("magic_puff_to_spine", {"project": proj, "frames_dir": frames, "sim_dir": str(d), "lights": False,
                                      "glitter": False, "max_size": 128})
    a, dist = _first_sprite_alpha(proj, r["smoke"]["slot"])
    assert a[dist < 800].min() > 0.95 and a[dist > 1070].max() < 0.03          # gone before the banner's ends
    assert 0.25 < a[np.argmin(np.abs(dist - 960))] < 0.75                      # smoothly (smoothstep 860 -> 1060)
    raw = str(samples.make_symbol(tmp_path / "raw").path)                        # [] keeps the frames as rendered
    r = _call("magic_puff_to_spine", {"project": raw, "frames_dir": frames, "sim_dir": str(d), "lights": False,
                                      "glitter": False, "max_size": 128, "params": {"edge_fade": []}})
    assert _first_sprite_alpha(raw, r["smoke"]["slot"])[0].min() > 0.95


def test_spine_side_params_override_the_simulation(tmp_path, sim):
    d, meta = sim
    proj = str(samples.make_symbol(tmp_path / "over").path)
    r = _call("magic_puff_to_spine", {"project": proj, "frames_dir": str(_ae_frames(tmp_path, meta)), "sim_dir": str(d),
                                      "max_size": 64, "params": {"lines": [362.0], "ray_color": "FF40A0"}})
    names = r["slots"]
    assert sum("line" in s for s in names) == 1 and not any("rays" in s for s in names)   # one line: no fan
    p = Project.open(proj)
    glow = next(s for s in p.data.slots if s.name.endswith("_glow"))
    assert glow.color.upper().startswith("FF40A0")
    with pytest.raises(Exception, match="unknown magic_puff param"):
        _call("magic_puff_to_spine", {"project": proj, "frames_dir": str(tmp_path / "frames" / "puff_t_full"),
                                      "sim_dir": str(d), "params": {"gold": "FFFFFF"}})


def test_to_spine_without_lights_is_just_the_smoke(tmp_path, sim):
    d, meta = sim
    proj = str(samples.make_symbol(tmp_path / "plain").path)
    r = _call("magic_puff_to_spine", {"project": proj, "frames_dir": str(_ae_frames(tmp_path, meta)), "sim_dir": str(d),
                                      "lights": False, "glitter": False, "max_size": 64})
    assert set(r) >= {"smoke", "animation"} and "slots" not in r
    with pytest.raises(Exception):
        _call("magic_puff_to_spine", {"project": proj})


def test_magic_puff_ae_tool_simulates_and_writes_the_script(tmp_path):
    r = _call("magic_puff_ae", {"out_dir": str(tmp_path), "comp": "puff", "params": TINY})
    assert r["comps"] == ["puff_full", "puff_master"] and r["save_as"].endswith("puff.aep")
    assert (tmp_path / "puff.jsx").exists() and r["run_with"].startswith("return String($.evalFile(")
    assert r["frames"] == round(TINY["t_end"] * TINY["fps"]) + 1 and (tmp_path / "sim" / "sim.json").exists()
    assert (tmp_path / "preview" / "magic_puff_preview.gif").exists()
    quiet = _call("magic_puff_ae", {"out_dir": str(tmp_path / "q"), "comp": "puff", "params": TINY, "preview": False,
                                    "alerts": False})
    assert '"alerts":false' in (tmp_path / "q" / "puff.jsx").read_text() and "preview" not in quiet
