"""Melted-sugar splat: a physical liquid burst simulated here, made gooey in After Effects, glossed here, played in Spine.

From a candy-bomb symbol whose splat had to read as hot melted sugar, not pieces shrinking in place:

1. ``simulate`` throws the liquid out on air drag and gravity. A fat centre glob per colour swells and drains; big
   globs fly out at uneven speeds (some far, some heavy near the middle), each dragging a *ligament* of beads that
   leave the centre slower and slower behind it; every glob TEARS into drops (spread, a teardrop tail behind each),
   which tear again into droplets that fall and evaporate. Everything is stretched along its velocity with its area
   kept (thinner as it stretches). It gets smaller by breaking up, never by shrinking in place.
2. ``jsx`` writes an After Effects script: one shape layer per drop keyed every frame, one precomp per candy colour,
   each finished as metaballs (Turbulent Displace -> Fast Box Blur -> Levels on alpha), so drops that are close melt
   into one body with gooey necks that stretch and pinch off. Two comps: ``<comp>_flat`` (colour only, for the gloss
   pass) and ``<comp>_bevel`` (an all-AE look with Bevel Alpha). The script refuses to run over an unsaved project,
   builds its own, saves it to ``save_as``, reopens the artist's project and leaves ``CLAUDE_ERR sugar: ...`` comps
   for problems (``ae_check`` reads them).
3. ``shade`` is the wet-sugar gloss AE's CC Glass / Glow could not give without washing the colour out: a dome
   height field grown from the alpha (thick syrup mid-blob, thin at the edge), a sharp specular and a soft sheen from
   the top left, a translucent bright core and a darker saturated rim.
4. ``preview`` renders the same metaball maths here (no AE), so the motion can be tuned before each AE run.

AE scripting traps this recipe already handles: Levels values are 0..1 from a script (0..255 wipes the alpha), no
line breaks inside script strings, AE's TIFF alpha is unflagged (``ae_bridge.read_tiff``), aerender needs absolute
output paths.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from scipy import ndimage

DEFAULTS: dict[str, Any] = {
    "size": 1800,            # comp px (square), splat centre in the middle
    "fps": 30,
    "duration": 1.4,
    "colors": {"pink": "FF3FA8", "yellow": "FFC21A", "cyan": "2FD3FF", "violet": "A469FF", "cream": "FFF1DA"},
    "accents": ["cream"],    # colours used only for 2 globs (highlights of the mix), never for the centre
    "globs": 20,
    "speed": [700, 2000],    # px/s at launch
    "glob_size": [110, 190], # px diameter
    "ligament": 7,           # beads per glob
    "splits": [2, 4],        # drops per glob (inclusive range)
    "gravity": 1.0,          # scales every stage's gravity
    "drag": 1.0,             # scales every stage's air drag
    "centre": True,          # fat centre globs that swell and drain
    "blur": 11,              # Fast Box Blur radius (x3 iterations): how far drops reach to merge
    "levels": [118, 150],    # alpha threshold (0..255 scale; written to AE as 0..1)
    "turbulence": 7,         # Turbulent Displace amount (organic wobble of the edges)
    "seed": 5,
}

LIGHT = np.array([-0.5, -0.62, 0.6]) / np.linalg.norm([-0.5, -0.62, 0.6])     # up-left, in front (image y down)
HALF = (LIGHT + np.array([0, 0, 1.0])) / np.linalg.norm(LIGHT + np.array([0, 0, 1.0]))


def params_of(params: dict | None) -> dict[str, Any]:
    p = json.loads(json.dumps(DEFAULTS))
    for k, v in (params or {}).items():
        if k not in p:
            raise ValueError(f"unknown sugar_splat param {k!r}; one of {sorted(p)}")
        p[k] = v
    if not p["colors"]:
        raise ValueError("colors needs at least one colour")
    return p


# ------------------------------------------------------------------ 1. simulation
def simulate(params: dict | None = None) -> list[dict]:
    """Drops as {g: colour, t0, t1, pos: [[t, x, y]], sc: [[t, sx%, sy%]], ro: [[t, deg]]} in AE comp space
    (px, y down, rotation clockwise; scale in % of a 100 px circle)."""
    P = params_of(params)
    rng = np.random.default_rng(int(P["seed"]))
    S, F = float(P["size"]), 1.0 / float(P["fps"])
    G, K = float(P["gravity"]), float(P["drag"])
    drops: list[dict] = []

    def fly(t0, p0, v0, size, life, drag, g, grp, fade_at=None, grow=0.05):
        drag, g = drag * K, g * G
        ts = list(np.arange(0, life, F)) + [life]
        pos, sc, ro = [], [], []
        prev = None
        for tau in ts:
            e = math.exp(-drag * tau)
            x = p0[0] + v0[0] * (1 - e) / drag
            y = p0[1] + v0[1] * (1 - e) / drag - 0.5 * g * tau * tau
            vx, vy = v0[0] * e, v0[1] * e - g * tau
            ang = math.degrees(math.atan2(vy, vx))
            if prev is not None:
                ang = prev + ((ang - prev + 180) % 360 - 180)
            prev = ang
            st = 1 + min(1.6, math.hypot(vx, vy) / 900.0)            # stretch along the flight, area kept
            k = size * min(1.0, 0.5 + 0.5 * tau / grow) if grow else size
            if fade_at is not None and tau > fade_at:
                k *= max(0.0, 1 - (tau - fade_at) / (life - fade_at))
            pos.append([round(t0 + tau, 4), round(S / 2 + x, 2), round(S / 2 - y, 2)])
            sc.append([round(t0 + tau, 4), round(k * st, 2), round(k / math.sqrt(st), 2)])
            ro.append([round(t0 + tau, 4), round(-ang, 2)])
        drops.append({"g": grp, "t0": round(t0, 4), "t1": round(t0 + life, 4), "pos": pos, "sc": sc, "ro": ro})
        e = math.exp(-drag * life)
        return ((p0[0] + v0[0] * (1 - e) / drag, p0[1] + v0[1] * (1 - e) / drag - 0.5 * g * life * life),
                (v0[0] * e, v0[1] * e - g * life))

    def turn(v, deg, f):
        a = math.radians(deg)
        return (f * (v[0] * math.cos(a) - v[1] * math.sin(a)), f * (v[0] * math.sin(a) + v[1] * math.cos(a)))

    names = list(P["colors"])
    accents = [c for c in P["accents"] if c in names]
    main = [c for c in names if c not in accents] or names
    if P["centre"]:
        for i, g in enumerate(main):
            a = 2 * math.pi * i / len(main) + rng.uniform(-0.3, 0.3)
            drops.append({"g": g, "t0": 0.0, "t1": 0.2,
                          "pos": [[0, S / 2 + 20 * math.cos(a), S / 2 - 20 * math.sin(a)],
                                  [0.2, S / 2 + 100 * math.cos(a), S / 2 - 100 * math.sin(a)]],
                          "sc": [[0, 140, 140], [0.06, 250, 240], [0.2, 50, 50]], "ro": [[0, 0]]})
    n = int(P["globs"])
    n_acc = min(2 * len(accents), max(0, n - 1))
    cols = (main * n)[:n - n_acc] + [accents[i % len(accents)] for i in range(n_acc)]
    rng.shuffle(cols)
    v_lo, v_hi = P["speed"]
    s_lo, s_hi = P["glob_size"]
    for i in range(n):
        a = 2 * math.pi * (i + rng.uniform(-0.45, 0.45)) / n
        v = rng.uniform(v_lo, v_hi)
        g = cols[i]
        s0 = rng.uniform(s_lo, s_hi) * (1.25 if v < v_lo + 0.15 * (v_hi - v_lo) else 1.0)   # slow ones are heavy
        life1 = rng.uniform(0.16, 0.28)
        v0 = (v * math.cos(a), v * math.sin(a))
        p1, v1 = fly(0.0, (math.cos(a) * 40, math.sin(a) * 40), v0, s0, life1, 1.8, 500, g)
        for k in range(int(P["ligament"])):              # the syrup strand behind the glob
            f = 0.12 + 0.72 * k / max(1, int(P["ligament"]) - 1)
            life = rng.uniform(0.35, 0.6)
            fly(0.005 * k, (math.cos(a) * 30, math.sin(a) * 30), turn(v0, rng.uniform(-3, 3), f),
                s0 * (0.3 + 0.24 * k / max(1, int(P["ligament"]) - 1)) * rng.uniform(0.9, 1.1), life, 1.8, 1300, g,
                fade_at=0.6 * life, grow=0.03)
        for _ in range(int(rng.integers(P["splits"][0], P["splits"][1] + 1))):
            vv = turn(v1, rng.uniform(-28, 28), rng.uniform(0.65, 1.0))
            s1 = s0 * rng.uniform(0.45, 0.6)
            life2 = rng.uniform(0.22, 0.38)
            p2, v2 = fly(life1, p1, vv, s1, life2, 2.0, 1400, g, grow=0.0)
            fly(life1, p1, turn(vv, 0, 0.85), s1 * 0.55, life2, 2.0, 1400, g, grow=0.0)        # teardrop tail
            for _m in range(2):
                life3 = rng.uniform(0.5, 0.8)
                fly(life1 + life2, p2, turn(v2, rng.uniform(-35, 35), rng.uniform(0.5, 0.9)),
                    s1 * rng.uniform(0.4, 0.55), life3, 1.4, 1900, g, fade_at=0.55 * life3, grow=0.0)
    end = float(P["duration"])
    return [d for d in drops if d["t0"] < end]


# ------------------------------------------------------------------ 2. After Effects script
JSX = r"""// melted-sugar splat (claude_spine.fx_sugar_splat)
var D = __DATA__;
var OUT = new File(__AEP__);
var COMPNAME = __COMP__;
var VARIANTS = ["_flat", "_bevel"];   // _flat: colour only (glossed by fx_sugar_splat.shade), _bevel: an all-AE look
var err = "";
function rgb(h) { return [parseInt(h.substr(0, 2), 16) / 255, parseInt(h.substr(2, 2), 16) / 255, parseInt(h.substr(4, 2), 16) / 255]; }
function findp(group, name) {
  for (var i = 1; i <= group.numProperties; i++) {
    var p = group.property(i);
    if (p.name === name || p.matchName === name) return p;
    if (p.propertyType !== PropertyType.PROPERTY) { var r = findp(p, name); if (r) return r; }
  }
  return null;
}
function setp(fx, name, v) {
  try { var p = findp(fx, name); if (p) p.setValue(v); else err += " [no " + name + "]"; }
  catch (e) { err += " [" + name + ": " + String(e) + "]"; }
}
function keyed(prop, rows, dims) {
  var t = [], v = [];
  for (var i = 0; i < rows.length; i++) { t.push(rows[i][0]); v.push(dims === 1 ? rows[i][1] : [rows[i][1], rows[i][2]]); }
  if (t.length === 1) prop.setValue(v[0]); else prop.setValuesAtTimes(t, v);
}
function finish(main, pc, gname, col, variant) {
  try {
    var G = main.layers.add(pc);
    G.name = "sugar_" + gname;
    var td = G.property("ADBE Effect Parade").addProperty("ADBE Turbulent Displace");
    setp(td, "Amount", D.turbulence); setp(td, "Size", 34);
    try { findp(td, "Evolution").setValuesAtTimes([0, D.dur], [0, 160]); } catch (e) {}
    var bl = G.property("ADBE Effect Parade").addProperty("ADBE Box Blur2");
    setp(bl, "Blur Radius", D.blur); setp(bl, "Iterations", 3);
    var lv = G.property("ADBE Effect Parade").addProperty("ADBE Pro Levels2");
    setp(lv, "Alpha Input Black", D.levels[0] / 255); setp(lv, "Alpha Input White", D.levels[1] / 255);
    var fl = G.property("ADBE Effect Parade").addProperty("ADBE Fill"); setp(fl, "Color", col);
    if (variant === "_bevel") {
      var bv = G.property("ADBE Effect Parade").addProperty("ADBE Bevel Alpha");
      setp(bv, "Edge Thickness", 11); setp(bv, "Light Angle", -50); setp(bv, "Light Intensity", 0.75);
    }
  } catch (e) { err += " [" + variant + " " + gname + ": " + String(e) + " @" + e.line + "]"; }
}
var ORIG = app.project ? app.project.file : null, DIRTY = app.project ? app.project.dirty : false;
if (DIRTY) {
  if (D.alerts) alert("Sugar splat: please SAVE your open project first, then run this script again. It builds its own project and reopens yours afterwards.");
} else {
  try {
    app.beginSuppressDialogs();
    app.newProject();
    app.project.bitsPerChannel = 8;
    var S = D.size, mains = [];
    for (var vi = 0; vi < VARIANTS.length; vi++) {
      var m = app.project.items.addComp(COMPNAME + VARIANTS[vi], S, S, 1, D.dur, D.fps);
      m.bgColor = [0, 0, 0]; mains.push(m);
    }
    for (var gi = 0; gi < D.order.length; gi++) {
      var gname = D.order[gi], col = rgb(D.colors[gname]);
      var pc = app.project.items.addComp("grp_" + gname, S, S, 1, D.dur, D.fps);
      for (var di = 0; di < D.drops.length; di++) {
        var d = D.drops[di];
        if (d.g !== gname) continue;
        var L = pc.layers.addShape();
        var c = L.property("ADBE Root Vectors Group").addProperty("ADBE Vector Group").property("ADBE Vectors Group");
        c.addProperty("ADBE Vector Shape - Ellipse").property("ADBE Vector Ellipse Size").setValue([100, 100]);
        c.addProperty("ADBE Vector Graphic - Fill").property("ADBE Vector Fill Color").setValue(col);
        var tr = L.property("ADBE Transform Group");
        keyed(tr.property("ADBE Position"), d.pos, 2);
        keyed(tr.property("ADBE Scale"), d.sc, 2);
        keyed(tr.property("ADBE Rotate Z"), d.ro, 1);
        L.inPoint = d.t0; L.outPoint = Math.min(D.dur, d.t1 + 1 / D.fps);
      }
      for (var vj = 0; vj < mains.length; vj++) finish(mains[vj], pc, gname, col, VARIANTS[vj]);
    }
    for (var vk = 0; vk < mains.length; vk++) { mains[vk].workAreaStart = 0; mains[vk].workAreaDuration = D.dur; }
  } catch (e) { err += " " + String(e) + " @" + e.line; }
  if (err) { try { app.project.items.addComp(("CLAUDE_ERR sugar: " + err).substr(0, 250), 4, 4, 1, 1, 1); } catch (x) {} }
  app.project.save(OUT);
  app.endSuppressDialogs(false);
  if (ORIG) app.open(ORIG); else app.newProject();
  if (D.alerts) alert("Sugar splat saved: " + OUT.fsName + (err ? " -- warnings: " + err : " -- all done."));
}
"""


def jsx(params: dict | None, comp: str, save_as: str | Path, alerts: bool = True) -> str:
    """The AE script. alerts=False for an After Effects MCP run (no modal dialogs)."""
    P = params_of(params)
    drops = simulate(P)
    accents = [c for c in P["accents"] if c in P["colors"]]
    order = accents + [c for c in P["colors"] if c not in accents]          # accents underneath
    data = {"size": int(P["size"]), "fps": float(P["fps"]), "dur": float(P["duration"]), "colors": P["colors"],
            "order": order, "drops": drops, "blur": float(P["blur"]), "levels": [float(v) for v in P["levels"]],
            "turbulence": float(P["turbulence"]), "alerts": bool(alerts)}
    return (JSX.replace("__DATA__", json.dumps(data, separators=(",", ":")))
            .replace("__AEP__", json.dumps(str(Path(save_as).expanduser().resolve())))
            .replace("__COMP__", json.dumps(comp)))


# ------------------------------------------------------------------ 3. gloss
def shade(rgba: np.ndarray, scale: float = 1.0) -> np.ndarray:
    """Straight-colour float RGBA (alpha 0..1, flat candy colours) -> premultiplied, glossed melted sugar.
    scale: px per comp px (0.5 for a half-size preview)."""
    A = rgba[..., 3]
    C = rgba[..., :3]
    d = ndimage.distance_transform_edt(A > 0.5)
    R = 26.0 * scale
    h = ndimage.gaussian_filter(np.sqrt(np.clip(d / R, 0, 1)), 1.6 * scale)
    gy, gx = np.gradient(h * R * 0.9)
    n = np.dstack([-gx, -gy, np.ones_like(h)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    ndl = np.clip(n @ LIGHT, 0, 1)
    ndh = np.clip(n @ HALF, 0, 1)
    diffuse = 0.58 + 0.42 * ndl
    spec = ndh ** 90 * 1.15 + ndh ** 14 * 0.16                  # wet glint + soft sheen
    core = 0.22 * h                                             # light through the thick middle
    rim = 0.72 + 0.28 * np.sqrt(np.clip(h, 0, 1))               # thin edges darker, more saturated
    col = np.clip(C * (diffuse * rim)[..., None] + C * core[..., None] + spec[..., None], 0, 1)
    return np.dstack([col * A[..., None], A])


# ------------------------------------------------------------------ 4. preview (same metaball maths, no AE)
def _ellipse(acc, cx, cy, rx, ry, rot_deg):
    H, W = acc.shape
    r = max(rx, ry) + 2
    x0, x1 = int(max(0, cx - r)), int(min(W, cx + r + 1))
    y0, y1 = int(max(0, cy - r)), int(min(H, cy + r + 1))
    if x0 >= x1 or y0 >= y1 or rx < 0.3 or ry < 0.3:
        return
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(float)
    t = math.radians(rot_deg)
    dx, dy = xx - cx, yy - cy
    u = dx * math.cos(t) + dy * math.sin(t)
    v = -dx * math.sin(t) + dy * math.cos(t)
    q = np.sqrt((u / rx) ** 2 + (v / ry) ** 2)
    acc[y0:y1, x0:x1] = np.maximum(acc[y0:y1, x0:x1], np.clip((1 - q) * min(rx, ry) + 0.5, 0, 1))


def _at(rows, t, dims):
    ts = [r[0] for r in rows]
    if len(rows) == 1 or t <= ts[0]:
        return list(rows[0][1:dims + 1])
    if t >= ts[-1]:
        return list(rows[-1][1:dims + 1])
    i = int(np.searchsorted(ts, t)) - 1
    a, b = rows[i], rows[i + 1]
    f = (t - a[0]) / (b[0] - a[0])
    return [a[k] + (b[k] - a[k]) * f for k in range(1, dims + 1)]


def frame(drops: list[dict], t: float, params: dict | None = None, half: int = 2) -> np.ndarray:
    """Straight-colour RGBA of the splat at t, as the AE `_flat` comp makes it (box blur x3 ~ a Gaussian)."""
    P = params_of(params)
    S = int(P["size"]) // half
    layers: dict[str, np.ndarray] = {}
    for d in drops:
        if not (d["t0"] <= t < d["t1"] + 1 / float(P["fps"])):
            continue
        x, y = _at(d["pos"], t, 2)
        sx, sy = _at(d["sc"], t, 2)
        _ellipse(layers.setdefault(d["g"], np.zeros((S, S))), x / half, y / half, sx / 2 / half, sy / 2 / half,
                 _at(d["ro"], t, 1)[0])
    out = np.zeros((S, S, 4))
    b = float(P["blur"])
    sigma = math.sqrt(3 * ((2 * b + 1) ** 2 - 1) / 12) / half
    lo, hi = (v / 255 for v in P["levels"])
    accents = [c for c in P["accents"] if c in P["colors"]]
    for g in accents + [c for c in P["colors"] if c not in accents]:
        if g not in layers:
            continue
        a = np.clip((ndimage.gaussian_filter(layers[g], sigma) - lo) / (hi - lo), 0, 1)
        c = np.array([int(P["colors"][g][i:i + 2], 16) / 255 for i in (0, 2, 4)])
        out[..., :3] = out[..., :3] * (1 - a[..., None]) + c * a[..., None]
        out[..., 3] = out[..., 3] * (1 - a) + a
    return out


def over(prem: np.ndarray, bg=(30, 24, 44)) -> Image.Image:
    bgc = np.array(bg) / 255.0
    return Image.fromarray((np.clip(prem[..., :3] + bgc * (1 - prem[..., 3:4]), 0, 1) * 255).astype(np.uint8))


def preview(params: dict | None, out_dir: str | Path, half: int = 2) -> dict:
    """Contact sheet + GIF of the simulated, glossed splat (no After Effects)."""
    P = params_of(params)
    drops = simulate(P)
    out = Path(out_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    frames = [over(shade(frame(drops, float(t), P, half), 1.0 / half))
              for t in np.arange(0, float(P["duration"]), 1 / float(P["fps"]))]
    idx = np.linspace(1, len(frames) - 1, 10).astype(int)
    w = min(360, frames[0].width)
    sheet = Image.new("RGB", (w * 5, w * 2))
    for i, k in enumerate(idx):
        sheet.paste(frames[k].resize((w, w)), ((i % 5) * w, (i // 5) * w))
    sheet.save(out / "sugar_splat_preview.png")
    frames[0].save(out / "sugar_splat_preview.gif", save_all=True, append_images=frames[1:],
                   duration=int(round(1000 / float(P["fps"]))), loop=0)
    return {"sheet": str(out / "sugar_splat_preview.png"), "gif": str(out / "sugar_splat_preview.gif"),
            "drops": len(drops), "frames": len(frames)}


# ------------------------------------------------------------------ AE frames -> glossed PNG frames
def shade_frames(src_dir: str | Path, dst_dir: str | Path, px: float | None = None) -> dict:
    """AE's `_flat` TIFF render (premultiplied) -> glossed straight-alpha PNGs (+ meta.json with fps / px)."""
    from .ae_bridge import read_tiff
    src, dst = Path(src_dir).expanduser(), Path(dst_dir).expanduser()
    tifs = sorted(src.glob("*.tif")) + sorted(src.glob("*.tiff"))
    if not tifs:
        raise FileNotFoundError(f"no TIFF frames in {src}")
    dst.mkdir(parents=True, exist_ok=True)
    for f in dst.glob("*.png"):
        f.unlink()
    for f in tifs:
        a = read_tiff(f)
        if a.shape[2] < 4:
            raise ValueError(f"{f}: no alpha channel (render with the 'TIFF Sequence with Alpha' template)")
        al = a[..., 3:4]
        straight = np.dstack([np.where(al > 1e-4, a[..., :3] / np.maximum(al, 1e-4), 0), a[..., 3]])
        sh = shade(straight)
        rgb = np.where(sh[..., 3:4] > 1e-4, sh[..., :3] / np.maximum(sh[..., 3:4], 1e-4), 0)
        Image.fromarray((np.dstack([np.clip(rgb, 0, 1), sh[..., 3]]) * 255).astype(np.uint8), "RGBA").save(
            dst / (f.stem + ".png"))
    meta = {}
    if (src / "meta.json").exists():
        meta = json.loads((src / "meta.json").read_text())
    if px is not None:
        meta["px"] = px
    (dst / "meta.json").write_text(json.dumps(meta))
    return {"frames": len(tifs), "dir": str(dst), **meta}
