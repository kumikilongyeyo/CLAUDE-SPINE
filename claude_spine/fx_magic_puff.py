"""Magic smoke puff: a physical smoke puff born at the centre of a banner, glowing, swirling while its glow dies,
then dissolving (from the teal smoke banner job, 2026-10-10).

1. ``simulate``: a 2D smoke simulation over the whole banner (both sides independent, no mirror). Stable fluids on
   a staggered grid: semi-Lagrangian RK2 advection, an exact pressure projection (DCT Poisson, closed box), drag, a
   little viscosity (smooth flow), vorticity confinement + curl-noise stirring (the swirl). Gas appears in a slab at
   the centre (a partial VOLUME source: a jet pushed from a line alone necks into a thin stem and sucks a streak in
   along the centre line) and is pushed out both ways with a rounded speed profile (a flat one makes a boxy plug
   front). Soft drag barriers hold it in a band (the gold lines of the reference) that ends before the banner's
   ends, where the front spills up and down into curling vortex pairs; they let go later and the smoke billows
   free, lifting a little. The source FILLS its zone to a target density (adding per step laid the smoke down in
   slabs one step's travel apart). Smoke is born hot and cools with its age: the glow that dies as it swirls.
   The nebula detail is advected with the flow (texture coordinates ride it), so it moves with the smoke; glitter
   particles ride the same flow. Writes 16-bit greyscale passes op / heat / lum per frame + sim.json.
2. ``jsx``: the After Effects look in its OWN project (refuses to run over unsaved changes, reopens the artist's
   project afterwards): colour ramp from the palette over a drive of density + detail, the hot glow added and keyed
   out (Levels (Individual Controls): Easy Levels cannot be keyframed in AE 2026), cooling, bloom, the density as
   a softened luma matte that erodes thin-first, then a fade. Comps: <comp>_full (render it) and <comp>_master.
3. ``preview``: the same look approximated in numpy, without AE (contact sheet + GIF), to tune before AE.
4. ``to_spine``: the rendered frames as ONE full-width sequence (resampled to an even playback rate, thinned out
   toward the banner's ends) + native lights over it: the pop (a gathering point, then a flash + streak), gold lines drawn outward with glints, flares
   igniting, a ray fan blooming from the bottom flare, an ambient glow, and glitter on the simulated paths.
"""
from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.fft import dctn, idctn

DEFAULTS: dict[str, Any] = {
    "width": 2172, "height": 724,          # the banner (comp px)
    "res": 0.5,                            # simulation cells (and passes) per comp px
    "pad_x": 164.0, "pad_y": 88.0,         # simulated margin round the banner (walls are out there)
    "cx": None, "cy": 367.0,               # the puff's origin (comp px); cx None = the centre
    "fps": 24, "sub": 4, "t_end": 3.75,
    "t_burst": 0.12,
    # jet: outward push with a rounded profile across the band
    "U0": 3400.0, "kick": 0.3, "rise": 0.05, "hold": 0.5, "decay": 0.45, "stop": 1.5,
    "slab": 150.0, "prof_pow": 2.5, "noise": 0.15, "push": 1.0, "expand": 0.35,
    "src_w": 26.0,                         # half-width of the source slab (comp px)
    # smoke
    "dens_fill": 0.75, "inject_w": 80.0, "dens_slab": 1.0,
    "linger": 1.6, "linger_t": [0.3, 2.0], "linger_x": 150.0,
    # flow character (smooth, large swirls)
    "drag": 0.2, "visc": 0.08, "vort": 0.2,
    "stir": 0.6, "stir_scale": 32, "stir_rise": 0.12, "stir_hold": 1.2, "stir_decay": 1.0,
    # the band: soft barriers along the gold lines, ending before the banner ends, released late
    "wall_drag": 24.0, "wall_in": 120.0, "wall_out": 260.0, "wall_end": 900.0, "wall_fade": 220.0,
    "wall_wander": 1.0, "wall_release": 2.2, "wall_release_dur": 0.8,
    "buoy": 40.0, "t_buoy": 2.4,
    "cool": 0.55,                          # heat = exp(-age / cool)
    "detail_scroll": 25.0,
    "edge_fade": [860.0, 1060.0],          # smoke thins out toward the banner's ends (distance from cx, comp px): the
                                           # passes, then the frames again at the Spine import ([] = no fade)
    "glitter": 30,                         # per side
    "seed": 7,
    # the look (After Effects, and the numpy preview)
    "shadow": "01221C", "mid": "037858", "light": "46EBAA",           # dark teal edges -> teal band -> mint filaments
    "hot_mid": "28DC8C", "hot_light": "AAFFC8", "heat_mix": 30, "heat_off": [0.95, 1.7],
    "cool_to": [1.6, 2.6, 0.80],           # Output White 1 -> 0.8 over these seconds (the glow leaves the smoke)
    "erode": [2.25, 3.65, 0.80],           # the matte's Input Black 0 -> 0.8: thin smoke goes first
    "fade": [3.3, 3.75],
    "bloom": [82, 10, 0.18],               # Glow threshold %, radius, intensity
    "matte_white": 0.85, "matte_gamma": 0.8, "drive_op": 40, "drive_lum": 60, "matte_blur": 2.0, "colour_blur": 0.8,
    # the Spine lights (comp px, the banner's own coordinates; y down)
    "lines": [200.0, 535.0],               # gold lines (empty = none); flares sit on them at cx
    "ray_color": "6EFFC4", "glitter_colors": ["FFD773", "D2FFF0"],     # (the gold of lines and flares is in their pictures)
    "ray_angles": [-72, -60, -51, -38, -23, -11, 0, 11, 24, 38, 53, 62, 71],
}


def params_of(given: dict | None) -> dict:
    p = dict(DEFAULTS)
    for k, v in (given or {}).items():
        if k not in DEFAULTS:
            raise ValueError(f"unknown magic_puff param {k!r}; one of {sorted(DEFAULTS)}")
        p[k] = v
    if p["cx"] is None:
        p["cx"] = p["width"] / 2.0
    return p


def tileable_nebula(n=512, seed=3):
    """Tileable nebula detail: smooth octaves + ridged filaments + sparkly grain (0..1)."""
    rng = np.random.default_rng(seed)

    def octave(cells, amp):
        g = np.tile(rng.random((cells, cells)), (3, 3))
        return amp * ndi.zoom(g, n / cells, order=3)[n:2 * n, n:2 * n]
    base = sum(octave(c, a) for c, a in ((4, 1.0), (8, 0.55), (16, 0.3), (32, 0.16), (64, 0.08)))
    base = (base - base.min()) / (base.max() - base.min())
    ridge = sum(octave(c, a) for c, a in ((6, 1.0), (12, 0.5), (24, 0.25)))
    ridge = (ridge - ridge.min()) / (ridge.max() - ridge.min())
    ridge = (1 - np.abs(ridge * 2 - 1)) ** 6
    grain = ndi.gaussian_filter(rng.random((n, n)), 0.6, mode="wrap")
    grain = np.clip((grain - 0.62) * 6, 0, 1) * (0.4 + 0.6 * base)
    tex = 0.55 * base + 0.35 * ridge + 0.25 * grain
    return np.clip((tex - tex.min()) / (tex.max() - tex.min()), 0, 1)


def _sstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


class Sim:
    def __init__(self, p):
        self.p = p
        self.h = 1.0 / p["res"]                                    # comp px per cell
        self.x0 = p["cx"] - p["width"] / 2 - p["pad_x"]            # comp x of the domain's left edge
        self.y0 = -p["pad_y"]
        self.nx = int(round((p["width"] + 2 * p["pad_x"]) / self.h))
        self.ny = int(round((p["height"] + 2 * p["pad_y"]) / self.h))
        nx, ny, h = self.nx, self.ny, self.h
        self.u = np.zeros((ny, nx + 1))
        self.v = np.zeros((ny + 1, nx))
        self.d = np.zeros((ny, nx))
        self.age = np.zeros((ny, nx))
        jj, ii = np.mgrid[0:ny, 0:nx]
        self.cxs, self.cys = ii + 0.5, jj + 0.5                      # cell centres (cells)
        self.X = (self.cxs * h + self.x0) - p["cx"]                  # comp px from the origin
        self.Yc = self.cys * h + self.y0                             # comp y
        self.tu = (self.cxs * h + self.x0) * 0.5
        self.tv = self.Yc * 0.5
        kx, ky = np.arange(nx), np.arange(ny)
        lam = (2 * np.cos(np.pi * kx / nx) - 2)[None, :] + (2 * np.cos(np.pi * ky / ny) - 2)[:, None]
        lam[0, 0] = 1.0
        self.lam = lam
        self.rng = np.random.default_rng(p["seed"])
        self.ph = self.rng.random((2, 6)) * 2 * np.pi              # independent turbulence left / right
        self.t = 0.0
        self.src = None
        # soft barriers: a band round cy whose inner edge wanders, ending (fading) toward the banner ends
        rw = np.random.default_rng(p["seed"] + 5)
        xs = (np.arange(nx) + 0.5) * h + self.x0 - p["cx"]
        wander = p["wall_wander"] * sum(a * np.sin(xs * k + rw.random() * 6.28) for k, a in ((0.006, 26.0), (0.013, 14.0), (0.031, 6.0)))
        dy = np.abs(self.Yc - p["cy"]) - wander[None, :]
        across = _sstep(p["wall_in"], p["wall_out"], dy)
        along = 1 - _sstep(p["wall_end"] - p["wall_fade"], p["wall_end"], np.abs(xs))[None, :]
        self.wall = p["wall_drag"] * across * along
        self._stir = None

    def burst(self, t):
        p = self.p
        s = t - p["t_burst"]
        if s < 0 or t > p["stop"]:
            return 0.0
        up = min(1.0, s / p["rise"])
        return up * up * (3 - 2 * up) * math.exp(-max(0.0, s - p["rise"] - p["hold"]) / p["decay"])

    def vel_at(self, x, y):
        u = ndi.map_coordinates(self.u, [y - 0.5, x], order=1, mode="nearest")
        v = ndi.map_coordinates(self.v, [y, x - 0.5], order=1, mode="nearest")
        return u, v

    def backtrace(self, x, y, dt):
        u, v = self.vel_at(x, y)
        xm, ym = x - 0.5 * dt * u / self.h, y - 0.5 * dt * v / self.h
        u, v = self.vel_at(xm, ym)
        return x - dt * u / self.h, y - dt * v / self.h

    def advect(self, dt):
        nx, ny = self.nx, self.ny
        jj, ii = np.mgrid[0:ny, 0:nx + 1]
        xb, yb = self.backtrace(ii.astype(float), jj + 0.5, dt)
        u_new = ndi.map_coordinates(self.u, [yb - 0.5, xb], order=3, mode="nearest")
        jj, ii = np.mgrid[0:ny + 1, 0:nx]
        xb, yb = self.backtrace(ii + 0.5, jj.astype(float), dt)
        v_new = ndi.map_coordinates(self.v, [yb, xb - 0.5], order=3, mode="nearest")
        xb, yb = self.backtrace(self.cxs, self.cys, dt)
        c = [yb - 0.5, xb - 0.5]
        self.d = np.clip(ndi.map_coordinates(self.d, c, order=3, mode="constant", cval=0.0), 0, None)
        self.age = ndi.map_coordinates(self.age, c, order=1, mode="nearest")
        self.tu = ndi.map_coordinates(self.tu, c, order=1, mode="nearest")
        self.tv = ndi.map_coordinates(self.tv, c, order=1, mode="nearest")
        self.u, self.v = u_new, v_new

    def stir_field(self, t):
        """Smooth stream function (two drifting octaves of lattice noise): divergence-free stirring."""
        if self._stir is None:
            r = np.random.default_rng(self.p["seed"] + 77)
            c0 = max(4, int(self.p["stir_scale"] * self.p["res"] / 0.5))
            self._stir = []
            for cells, amp in ((c0, 1.0), (max(3, c0 // 2), 0.4)):
                g0 = r.standard_normal((self.ny // cells + 3, self.nx // cells + 3))
                g1 = r.standard_normal(g0.shape)
                self._stir.append((cells, amp, g0, g1))
        out = np.zeros((self.ny, self.nx))
        w = 0.5 - 0.5 * math.cos(math.pi * min(1.0, t / 2.5))
        for cells, amp, g0, g1 in self._stir:
            g = g0 * (1 - w) + g1 * w
            up = ndi.zoom(g, (self.ny / (g.shape[0] - 3), self.nx / (g.shape[1] - 3)), order=3)
            out += amp * up[:self.ny, :self.nx]
        return out * self.h * 40.0

    def forces(self, dt):
        p, h = self.p, self.h
        nx, ny = self.nx, self.ny
        b = self.burst(self.t)
        yc = self.Yc[:, 0]
        X = self.X
        if b > 0:
            tt = self.t
            kick = 1.0 + p["kick"] * math.exp(-max(0.0, tt - p["t_burst"]) / 0.08)
            prof = 1.0 / (1.0 + np.abs((yc - p["cy"]) / p["slab"]) ** p["prof_pow"])
            speeds = []
            for side in (0, 1):                                      # each side its own standing-wave turbulence
                ph = self.ph[side]
                wob = (np.sin(yc * 0.031 + ph[0]) * np.sin(tt * 9.0 + ph[3]) * 0.5
                       + np.sin(yc * 0.073 + ph[1]) * np.sin(tt * 13.0 + ph[4]) * 0.3
                       + np.sin(yc * 0.011 + ph[2]) * np.sin(tt * 5.0 + ph[5]) * 0.2)
                speeds.append(p["U0"] * b * kick * (1 + p["noise"] * wob) * prof)
            sw = p["src_w"]
            # faces (comp px from the origin): push outward on each side of the slab
            xf = (np.arange(nx + 1)) * h + self.x0 - p["cx"]
            right = (xf > 0) & (xf <= sw)
            left = (xf < 0) & (xf >= -sw)
            for mask, sgn, spd in ((right, 1, speeds[1]), (left, -1, speeds[0])):
                idx = np.nonzero(mask)[0]
                for i in idx:
                    frac = 1 - abs(xf[i]) / sw * 0.3
                    if sgn > 0:
                        self.u[:, i] = np.maximum(self.u[:, i], p["push"] * spd * frac)
                    else:
                        self.u[:, i] = np.minimum(self.u[:, i], -p["push"] * spd * frac)
            if p["expand"] > 0:
                src = np.zeros((ny, nx))
                cols = np.abs(X[0]) <= sw
                spd = 0.5 * (speeds[0] + speeds[1])
                src[:, cols] = (p["expand"] * spd / sw)[:, None]            # each side gets expand x its own flux
                self.src = src
            # smoke: FILL the zone round the source to a target density (adding per step laid it down in slabs)
            dprof = 1.0 / (1.0 + ((yc - p["cy"]) / (p["slab"] * p["dens_slab"])) ** 12) * min(1.0, b * 1.5)
            zone = np.abs(X[0]) <= p["inject_w"]
            target = p["dens_fill"] * dprof[:, None] * np.ones((1, zone.sum()))
            cur = self.d[:, zone]
            fresh = target > cur
            self.d[:, zone] = np.maximum(cur, target)
            self.age[:, zone] = np.where(fresh, 0.0, self.age[:, zone])
            xs_ = self.X[0, zone] + p["cx"]
            self.tu[:, zone] = np.where(fresh, (xs_ * 0.5 - self.t * p["detail_scroll"])[None, :], self.tu[:, zone])
            self.tv[:, zone] = np.where(fresh, (yc * 0.5)[:, None], self.tv[:, zone])
        else:
            self.src = None
        # the origin keeps glowing: a gentle supply of hot smoke while the band lives
        t0_, t1_ = p["linger_t"]
        if p["linger"] > 0 and t0_ < self.t < t1_:
            env = min(1.0, (self.t - t0_) / 0.25) * min(1.0, (t1_ - self.t) / 0.5)
            xprof = np.exp(-(X[0] / p["linger_x"]) ** 2)
            yprof = 1.0 / (1.0 + ((yc - p["cy"]) / (p["slab"] * 1.15)) ** 8)
            add = p["linger"] * env * dt * yprof[:, None] * xprof[None, :]
            self.age = np.where(add > 1e-5, self.age * (self.d / (self.d + add * 2 + 1e-6)), self.age)
            self.d += add
        # curl-noise stirring where there is smoke
        if p["stir"] > 0 and self.t > p["t_burst"]:
            env = min(1.0, (self.t - p["t_burst"]) / p["stir_rise"]) * math.exp(-max(0.0, self.t - p["stir_hold"]) / p["stir_decay"])
            psi = self.stir_field(self.t)
            fx = np.gradient(psi, axis=0) / h
            fy = -np.gradient(psi, axis=1) / h
            dw = np.clip(self.d * 2.0, 0, 1)
            self.u[:, 1:-1] += dt * env * p["stir"] * 0.5 * ((fx * dw)[:, :-1] + (fx * dw)[:, 1:])
            self.v[1:-1, :] += dt * env * p["stir"] * 0.5 * ((fy * dw)[:-1, :] + (fy * dw)[1:, :])
        # drag + barriers (released late)
        self.u *= math.exp(-p["drag"] * dt)
        self.v *= math.exp(-p["drag"] * dt)
        if p["wall_drag"] > 0:
            rel = min(1.0, max(0.0, (self.t - p["wall_release"]) / p["wall_release_dur"]))
            wc = self.wall * (1 - rel * rel * (3 - 2 * rel))
            self.u[:, 1:-1] *= np.exp(-0.5 * (wc[:, :-1] + wc[:, 1:]) * dt)
            self.v[1:-1, :] *= np.exp(-0.5 * (wc[:-1, :] + wc[1:, :]) * dt)
        # viscosity: smooth flow, larger swirls
        if p["visc"] > 0:
            k = min(1.0, p["visc"] * dt * 60)
            self.u = self.u * (1 - k) + ndi.uniform_filter(self.u, 3, mode="nearest") * k
            self.v = self.v * (1 - k) + ndi.uniform_filter(self.v, 3, mode="nearest") * k
        # vorticity confinement
        uc = 0.5 * (self.u[:, :-1] + self.u[:, 1:])
        vc = 0.5 * (self.v[:-1, :] + self.v[1:, :])
        w_ = (np.gradient(vc, axis=1) - np.gradient(uc, axis=0)) / h
        aw = np.abs(w_)
        gx, gy = np.gradient(aw, axis=1), np.gradient(aw, axis=0)
        mag = np.sqrt(gx * gx + gy * gy) + 1e-6
        fxv = p["vort"] * h * (gy / mag * w_)
        fyv = p["vort"] * h * (-gx / mag * w_)
        self.u[:, 1:-1] += dt * 0.5 * (fxv[:, :-1] + fxv[:, 1:]) * 40.0
        self.v[1:-1, :] += dt * 0.5 * (fyv[:-1, :] + fyv[1:, :]) * 40.0
        # late lift
        if self.t > p["t_buoy"]:
            kb = min(1.0, (self.t - p["t_buoy"]) / 0.8)
            dc = np.clip(self.d, 0, 2)
            self.v[1:-1, :] -= dt * p["buoy"] * kb * 0.5 * (dc[:-1, :] + dc[1:, :])
        self.u[:, 0] = 0
        self.u[:, -1] = 0
        self.v[0, :] = 0
        self.v[-1, :] = 0

    def project(self):
        h = self.h
        div = (self.u[:, 1:] - self.u[:, :-1] + self.v[1:, :] - self.v[:-1, :]) / h
        if self.src is not None:
            div = div - self.src
        pr = dctn(div * h * h, type=2, norm="ortho") / self.lam
        pr[0, 0] = 0
        pr = idctn(pr, type=2, norm="ortho")
        self.u[:, 1:-1] -= (pr[:, 1:] - pr[:, :-1]) / h
        self.v[1:-1, :] -= (pr[1:, :] - pr[:-1, :]) / h

    def step(self, dt):
        self.forces(dt)
        self.project()
        self.advect(dt)
        self.age += dt
        self.t += dt


def edge_fade(a, xs, x0, x1):
    t = np.clip((np.abs(xs) - x0) / (x1 - x0), 0, 1)
    return a * (1 - t * t * (3 - 2 * t))[None, :]


def simulate(out_dir, params=None, progress: Callable | None = None) -> dict:
    p = params_of(params)
    out = Path(out_dir)
    for sub in ("op", "heat", "lum"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    sim = Sim(p)
    tex = tileable_nebula()
    T = tex.shape[0]
    fps, sub = p["fps"], p["sub"]
    dt = 1.0 / (fps * sub)
    n_frames = int(round(p["t_end"] * fps)) + 1
    # the visible banner inside the domain (cells)
    vx0 = int(round(p["pad_x"] / sim.h))
    vx1 = vx0 + int(round(p["width"] / sim.h))
    vy0 = int(round(p["pad_y"] / sim.h))
    vy1 = vy0 + int(round(p["height"] / sim.h))
    xs_vis = (np.arange(vx0, vx1) + 0.5) * sim.h + sim.x0 - p["cx"]
    rng = np.random.default_rng(p["seed"] + 101)
    glit = []
    for side in (1, -1):
        for _ in range(p["glitter"]):
            glit.append({"side": side, "t0": p["t_burst"] + 0.02 + rng.random() * 0.42,
                         "x": p["cx"] + side * (6.0 + rng.random() * 20), "y": p["cy"] + (rng.random() * 2 - 1) * p["slab"] * 0.8,
                         "jx": side * abs(rng.normal()) * 60, "jy": rng.normal() * 40, "life": 1.4 + rng.random() * 2.0,
                         "size": 0.5 + rng.random() ** 2 * 1.1, "hue": int(rng.random() < 0.45),
                         "tw": 6 + rng.random() * 8, "ph": rng.random(), "path": []})
    t_start = time.time()
    for f in range(n_frames):
        t_f = f / fps
        while sim.t < t_f - 1e-9:
            sim.step(dt)
            for g in glit:
                if sim.t < g["t0"]:
                    continue
                if "cx" not in g:
                    g["cx"], g["cy"] = (g["x"] - sim.x0) / sim.h, (g["y"] - sim.y0) / sim.h
                u, v = sim.vel_at(np.array([g["cx"]]), np.array([g["cy"]]))
                g["cx"] += dt * (u[0] * 1.08 + g["jx"]) / sim.h
                g["cy"] += dt * (v[0] * 1.08 + g["jy"]) / sim.h
                g["jx"] *= math.exp(-2.5 * dt)
                g["jy"] *= math.exp(-2.5 * dt)
        for g in glit:
            if "cx" in g:
                g["path"].append([round(t_f, 4), round(g["cx"] * sim.h + sim.x0, 1), round(g["cy"] * sim.h + sim.y0, 1)])
        d = sim.d[vy0:vy1, vx0:vx1]
        age = sim.age[vy0:vy1, vx0:vx1]
        det = ndi.map_coordinates(tex, [np.mod(sim.tv[vy0:vy1, vx0:vx1], T), np.mod(sim.tu[vy0:vy1, vx0:vx1], T)], order=1, mode="wrap")
        dens = 1 - np.exp(-1.6 * d)
        op = np.clip(dens * (0.55 + 0.75 * det), 0, 1)
        heat = np.clip(np.exp(-age / p["cool"]) * dens, 0, 1)
        op = edge_fade(op, xs_vis, *p["edge_fade"])
        heat = edge_fade(heat, xs_vis, *p["edge_fade"])
        for name, arr in (("op", op), ("heat", heat), ("lum", det)):
            Image.fromarray((np.clip(arr, 0, 1) * 65535 + 0.5).astype(np.uint16)).save(out / name / f"{name}_{f:04d}.png")
        if progress and f % 12 == 0:
            progress(f"frame {f}/{n_frames - 1} t={t_f:.2f}s max density {sim.d.max():.2f} max |u| {np.abs(sim.u).max():.0f} "
                     f"elapsed {time.time() - t_start:.0f}s")
    meta = {"params": p, "frames": n_frames, "fps": fps, "pass_size": [vx1 - vx0, vy1 - vy0], "res": p["res"],
            "glitter": [{k: g[k] for k in ("side", "t0", "life", "size", "hue", "tw", "ph", "path")} for g in glit]}
    (out / "sim.json").write_text(json.dumps(meta))
    return meta


# ------------------------------------------------------------------ 2. the After Effects look
JSX = r"""// magic smoke puff look (claude_spine.fx_magic_puff)
var D = __DATA__;
var OUT = new File(__AEP__);
var C = __COMP__;
var err = "";
var STATUS = "";                         // the script's value: what $.evalFile returns to an MCP run
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
function keyp(fx, name, t, v) {
  try { var p = findp(fx, name); if (p) p.setValuesAtTimes(t, v); else err += " [no " + name + "]"; }
  catch (e) { err += " [keys " + name + ": " + String(e) + "]"; }
}
function effect(layer, match) { return layer.property("ADBE Effect Parade").addProperty(match); }
function seq(name) {
  var io = new ImportOptions(new File(D.simdir + "/" + name + "/" + name + "_0000.png"));
  io.sequence = true;
  var f = app.project.importFile(io);
  f.mainSource.conformFrameRate = D.fps;
  f.name = "sim_" + name;
  return f;
}
function tritone(layer, hi, mid, lo) {
  var t = effect(layer, "ADBE Tritone");
  setp(t, "Highlights", rgb(hi)); setp(t, "Midtones", rgb(mid)); setp(t, "Shadows", lo ? rgb(lo) : [0, 0, 0]);
}
var ORIG = app.project ? app.project.file : null, DIRTY = app.project ? app.project.dirty : false;
if (DIRTY) {
  STATUS = "magic_puff NOT built: the open project has unsaved changes; save it, then run this script again";
  if (D.alerts) alert("Magic puff: please SAVE your open project first, then run this script again. It builds its own project and reopens yours afterwards.");
} else {
  try {
    app.beginSuppressDialogs();
    app.newProject();
    app.project.bitsPerChannel = 16;
    var W = D.w, H = D.h, FPS = D.fps, DUR = D.frames / D.fps;
    var op = seq("op"), heat = seq("heat"), lum = seq("lum");
    // what the colour ramp reads: density + the nebula detail riding the flow
    var drive = app.project.items.addComp(C + "_drive", W, H, 1, DUR, FPS);
    drive.layers.addSolid([0, 0, 0], "black", W, H, 1);
    var lo = drive.layers.add(op); lo.opacity.setValue(D.drive_op);
    var ll = drive.layers.add(lum); ll.opacity.setValue(D.drive_lum); ll.blendingMode = BlendingMode.ADD;
    // colour: the palette, the hot glow keyed out (the glow dies as it swirls), cooling, bloom
    var colour = app.project.items.addComp(C + "_colour", W, H, 1, DUR, FPS);
    var dl = colour.layers.add(drive); dl.name = "smoke colour";
    tritone(dl, D.light, D.mid, D.shadow);
    var cool = effect(dl, "ADBE Pro Levels2");                  // Easy Levels cannot be keyframed (AE 2026)
    keyp(cool, "ADBE Pro Levels2-0008", [D.cool_to[0], D.cool_to[1]], [1, D.cool_to[2]]);
    var hl = colour.layers.add(heat); hl.name = "hot magic glow"; hl.blendingMode = BlendingMode.ADD;
    tritone(hl, D.hot_light, D.hot_mid, null);
    hl.opacity.setValuesAtTimes([0, D.heat_off[0], D.heat_off[1]], [D.heat_mix, D.heat_mix, 0]);
    var bl = colour.layers.addSolid([1, 1, 1], "bloom", W, H, 1); bl.adjustmentLayer = true;
    var gl = effect(bl, "ADBE Glo2");
    setp(gl, "Glow Threshold", D.bloom[0]); setp(gl, "Glow Radius", D.bloom[1]); setp(gl, "Glow Intensity", D.bloom[2]);
    // the render comp: the colour cut by the density (softened), eroding thin-first, then fading
    var full = app.project.items.addComp(C + "_full", W, H, 1, DUR, FPS);
    var cl = full.layers.add(colour); cl.name = "colour";
    setp(effect(cl, "ADBE Gaussian Blur 2"), "Blurriness", D.colour_blur);
    var ml = full.layers.add(op); ml.name = "density (matte)";
    setp(effect(ml, "ADBE Gaussian Blur 2"), "Blurriness", D.matte_blur);
    var er = effect(ml, "ADBE Pro Levels2");
    setp(er, "ADBE Pro Levels2-0006", D.matte_gamma);
    keyp(er, "ADBE Pro Levels2-0004", [D.erode[0], D.erode[1]], [0, D.erode[2]]);
    keyp(er, "ADBE Pro Levels2-0005", [D.erode[0], D.erode[1]], [D.matte_white, Math.min(1, D.erode[2] + 0.18)]);
    ml.moveBefore(cl);
    cl.setTrackMatte(ml, TrackMatteType.LUMA);
    ml.enabled = false;
    cl.opacity.setValuesAtTimes([D.fade[0], D.fade[1]], [100, 0]);
    full.workAreaStart = 0; full.workAreaDuration = DUR;
    var master = app.project.items.addComp(C + "_master", W, H, 1, DUR, FPS);
    master.layers.addSolid([10 / 255, 12 / 255, 18 / 255], "background", W, H, 1);
    master.layers.add(full).name = "magic puff";
  } catch (e) { err += " " + String(e) + " @" + e.line; }
  if (err) { try { app.project.items.addComp(("CLAUDE_ERR magic_puff: " + err).substr(0, 250), 4, 4, 1, 1, 1); } catch (x) {} }
  app.project.save(OUT);
  app.endSuppressDialogs(false);
  if (ORIG) app.open(ORIG); else app.newProject();
  STATUS = "magic_puff saved " + OUT.fsName + (err ? " -- warnings:" + err : " -- all done");
  if (D.alerts) alert("Magic puff saved: " + OUT.fsName + (err ? " -- warnings: " + err : " -- all done."));
}
STATUS;
"""

_LOOK_KEYS = ("shadow", "mid", "light", "hot_mid", "hot_light", "heat_mix", "heat_off", "cool_to", "erode", "fade",
              "bloom", "matte_white", "matte_gamma", "drive_op", "drive_lum", "matte_blur", "colour_blur")


def jsx(params: dict | None, comp: str, save_as: str | Path, sim_dir: str | Path, alerts: bool = True) -> str:
    """The AE script for the look. ``sim_dir`` holds the passes ``simulate`` wrote (op/, heat/, lum/, sim.json)."""
    P = params_of(params)
    meta = json.loads((Path(sim_dir) / "sim.json").read_text())
    w, h = meta["pass_size"]
    data = {"simdir": str(Path(sim_dir).expanduser().resolve()).replace("\\", "/"), "w": int(w), "h": int(h),
            "fps": float(meta["fps"]), "frames": int(meta["frames"]), "alerts": bool(alerts),
            **{k: P[k] for k in _LOOK_KEYS}}
    return (JSX.replace("__DATA__", json.dumps(data, separators=(",", ":")))
            .replace("__AEP__", json.dumps(str(Path(save_as).expanduser().resolve()).replace("\\", "/")))
            .replace("__COMP__", json.dumps(comp)))


# ------------------------------------------------------------------ 3. the look without AE (preview)
def _hex(c: str) -> np.ndarray:
    return np.array([int(c[i:i + 2], 16) for i in (0, 2, 4)], float) / 255


def _tritone(x: np.ndarray, hi: str, mid: str, lo: str | None) -> np.ndarray:
    lo_c = _hex(lo) if lo else np.zeros(3)
    x = np.clip(x, 0, 1)[..., None]
    a = lo_c + (_hex(mid) - lo_c) * np.clip(x / 0.5, 0, 1)
    return np.where(x < 0.5, a, _hex(mid) + (_hex(hi) - _hex(mid)) * np.clip((x - 0.5) / 0.5, 0, 1))


def _ramp(t: float, t0: float, t1: float, a: float, b: float) -> float:
    u = min(1.0, max(0.0, (t - t0) / max(1e-6, t1 - t0)))
    u = u * u * (3 - 2 * u)
    return a + (b - a) * u


def look_frame(P: dict, op: np.ndarray, heat: np.ndarray, lum: np.ndarray, t: float) -> np.ndarray:
    """Premultiplied RGBA of one frame, approximating the AE look."""
    drive = op * P["drive_op"] / 100 + lum * P["drive_lum"] / 100
    col = _tritone(drive, P["light"], P["mid"], P["shadow"]) * _ramp(t, P["cool_to"][0], P["cool_to"][1], 1, P["cool_to"][2])
    hot = _ramp(t, P["heat_off"][0], P["heat_off"][1], P["heat_mix"] / 100, 0)
    col = col + _tritone(heat, P["hot_light"], P["hot_mid"], None) * hot
    lumc = col.max(axis=2)
    glow = ndi.gaussian_filter(np.clip(lumc - P["bloom"][0] / 100, 0, None), P["bloom"][1] / 2) * P["bloom"][2] * 4
    col = np.clip(col + glow[..., None] * _hex(P["light"]), 0, 1)
    m = ndi.gaussian_filter(op, max(0.01, P["matte_blur"] / 2))
    ib = _ramp(t, P["erode"][0], P["erode"][1], 0, P["erode"][2])
    iw = _ramp(t, P["erode"][0], P["erode"][1], P["matte_white"], min(1, P["erode"][2] + 0.18))
    m = np.clip((m - ib) / max(1e-3, iw - ib), 0, 1) ** (1 / P["matte_gamma"])
    a = m * _ramp(t, P["fade"][0], P["fade"][1], 1, 0)
    return np.dstack([col * a[..., None], a])


def preview(params: dict | None, sim_dir: str | Path, out_dir: str | Path, width: int = 724) -> dict:
    """A contact sheet (8 moments) + a GIF of the look made here without AE, over the dark background."""
    P = params_of(params)
    sim_dir, out = Path(sim_dir), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((sim_dir / "sim.json").read_text())
    n, fps = meta["frames"], meta["fps"]
    bg = np.array([10, 12, 18]) / 255.0

    def frame(i):
        rd = lambda k: np.asarray(Image.open(sim_dir / k / f"{k}_{i:04d}.png")).astype(np.float64) / 65535
        pm = look_frame(P, rd("op"), rd("heat"), rd("lum"), i / fps)
        im = Image.fromarray((np.clip(pm[..., :3] + bg * (1 - pm[..., 3:4]), 0, 1) * 255 + 0.5).astype(np.uint8))
        return im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    picks = [min(n - 1, int(round(t * fps))) for t in np.linspace(0.12, (n - 1) / fps * 0.97, 8)]
    tiles = [frame(i) for i in picks]
    th = tiles[0].height
    sheet = Image.new("RGB", (width * 2 + 4, (th + 4) * 4), (60, 60, 60))
    for k, im in enumerate(tiles):
        sheet.paste(im, ((k % 2) * (width + 4), (k // 2) * (th + 4)))
    sheet.save(out / "magic_puff_preview.png")
    gif = [frame(i) for i in range(0, n, 2)]
    gif[0].save(out / "magic_puff_preview.gif", save_all=True, append_images=gif[1:], duration=round(2000 / fps), loop=0)
    return {"sheet": str(out / "magic_puff_preview.png"), "gif": str(out / "magic_puff_preview.gif"), "frames": len(gif),
            "moments": [round(i / fps, 3) for i in picks]}


# ------------------------------------------------------------------ 4. Spine: the frames + native lights + glitter
def _light(rgb_light: np.ndarray) -> Image.Image:
    """Additive light (premultiplied RGB on black) as RGBA: alpha = max(rgb)."""
    a = rgb_light.max(axis=2)
    c = np.where(a[..., None] > 1e-6, rgb_light / np.maximum(a[..., None], 1e-6), 0)
    return Image.fromarray((np.dstack([np.clip(c, 0, 1), np.clip(a, 0, 1)]) * 255 + 0.5).astype(np.uint8), "RGBA")


def tex_flare_halo(n: int = 256) -> Image.Image:
    yy, xx = np.mgrid[0:n, 0:n] + 0.5
    r = np.hypot(xx - n / 2, yy - n / 2) / (n / 2)
    gold = np.array([1.0, 0.86, 0.40])
    light = np.exp(-(r / 0.10) ** 2)[..., None] * np.array([1, 1, 0.95]) + \
        (np.exp(-(r / 0.32) ** 2) * 0.75 + np.exp(-(r / 0.70) ** 2) * 0.28 * np.clip(1 - r, 0, 1))[..., None] * gold
    return _light(np.clip(light, 0, 1))


def tex_flare_star(n: int = 256) -> Image.Image:
    yy, xx = np.mgrid[0:n, 0:n] + 0.5
    r = np.hypot(xx - n / 2, yy - n / 2) / (n / 2)
    ang = np.arctan2(yy - n / 2, xx - n / 2)
    spike = np.zeros_like(r)
    for k in range(4):
        da = np.abs(np.angle(np.exp(1j * (ang - k * math.pi / 2))))
        across = r * np.sin(np.minimum(da, math.pi / 2)) * (n / 2)
        spike = np.maximum(spike, np.exp(-(across / (1.6 + 2.2 * (1 - r))) ** 2) * np.clip(1 - r, 0, 1) ** 1.6 * (da < math.pi / 2))
    return _light(np.clip(spike + np.exp(-(r / 0.06) ** 2), 0, 1)[..., None] * np.array([1.0, 0.95, 0.75]))


def tex_line(w: int = 1024, h: int = 48) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w] + 0.5
    dy = yy - h / 2
    along = np.clip(1 - np.abs(xx - w / 2) / (w / 2), 0, 1) ** 1.3
    line = ((np.exp(-(dy / 2.2) ** 2) + 0.35 * np.exp(-(dy / 9.0) ** 2)) * along)[..., None] * np.array([1.0, 0.9, 0.5])
    line += (np.exp(-(dy / 1.2) ** 2) * along ** 3)[..., None] * np.array([0.0, 0.08, 0.35])
    return _light(np.clip(line, 0, 1))


def tex_glint(w: int = 256, h: int = 32) -> Image.Image:
    yy, xx = np.mgrid[0:h, 0:w] + 0.5
    g = np.exp(-((xx - w / 2) / 52.0) ** 2) * (np.exp(-((yy - h / 2) / 1.8) ** 2) + 0.3 * np.exp(-((yy - h / 2) / 6.0) ** 2))
    g += 0.9 * np.exp(-((xx - w / 2) / 9.0) ** 2 - ((yy - h / 2) / 3.0) ** 2)
    return _light(np.clip(g, 0, 1)[..., None] * np.array([1.0, 0.97, 0.8]))


def tex_speck(n: int = 64) -> Image.Image:
    yy, xx = np.mgrid[0:n, 0:n] + 0.5
    r = np.hypot(xx - n / 2, yy - n / 2)
    dot = np.exp(-(r / 3.0) ** 2) + 0.30 * np.exp(-(r / 8.0) ** 2)
    cross = (np.exp(-((yy - n / 2) / 0.8) ** 2) + np.exp(-((xx - n / 2) / 0.8) ** 2)) * np.clip(1 - r / (n / 2), 0, 1) ** 3 * 0.14
    return _light(np.clip(dot + cross, 0, 1)[..., None] * np.ones(3))


def tex_soft_glow(n: int = 128) -> Image.Image:
    yy, xx = np.mgrid[0:n, 0:n] + 0.5
    r = np.hypot(xx - n / 2, yy - n / 2) / (n / 2)
    g = np.clip(np.exp(-(r / 0.42) ** 2) * np.clip(1 - r, 0, 1) ** 0.5, 0, 1)
    return Image.fromarray((np.dstack([np.ones_like(g)] * 3 + [g]) * 255 + 0.5).astype(np.uint8), "RGBA")


def tex_ray_fan(angles: list, w: int = 512, h: int = 192, seed: int = 4) -> Image.Image:
    """Soft rays fanning UP from the bottom-centre of the image (white: the slot colour tints it). Soft light: half
    the displayed size is plenty (two full-size fans pushed the banner onto a third atlas page)."""
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:h, 0:w] + 0.5
    dx, dy = xx - w / 2, h - yy
    rr = np.hypot(dx, dy) / h
    th = np.degrees(np.arctan2(dx, dy))
    fan = np.zeros((h, w))
    for a in angles:
        wd = 2.2 + 2.6 * rng.random()
        fan = np.maximum(fan, (0.55 + 0.45 * rng.random()) * np.exp(-((th - a) / wd) ** 2))
    radial = np.clip(rr / 0.08, 0, 1) * np.clip(1 - rr / 1.45, 0, 1) ** 1.3
    core = np.exp(-(rr / 0.10) ** 2) * 0.6
    v = np.clip(fan * radial + core, 0, 1)
    return Image.fromarray((np.dstack([np.ones_like(v)] * 3 + [v]) * 255 + 0.5).astype(np.uint8), "RGBA")


TEXTURES: dict[str, Callable[[], Image.Image]] = {
    "fx/mp_flare_halo": tex_flare_halo, "fx/mp_flare_star": tex_flare_star, "fx/mp_line": tex_line,
    "fx/mp_glint": tex_glint, "fx/mp_speck": tex_speck, "fx/mp_soft_glow": tex_soft_glow,
}


def resample(frames: list[Path], src_fps: float, fps: float) -> list[Path]:
    """The rendered frames on an even `fps` grid (nearest frame): smooth playback with fewer frames than 24."""
    n = len(frames)
    dur = (n - 1) / src_fps
    out, k = [], 0
    while k / fps <= dur + 1e-9:
        out.append(frames[min(n - 1, int(round(k / fps * src_fps)))])
        k += 1
    return out


def _fade_ends(project, slot: str, W: float, cx: float, fade) -> None:
    """Thin the imported smoke frames out toward the banner's ends over the passes' own ``edge_fade`` distances.
    The AE matte's levels reshape the passes' fade, so without this the ends stop short instead of reaching zero
    smoothly. The sprites are straight alpha and span the whole comp, so this is alpha x a horizontal ramp."""
    att = project.data.attachment(slot, "fx")
    seq = att.sequence
    for i in range(seq.count):
        name = f"{att.path}{seq.start + i:0{seq.digits}d}"
        im = np.asarray(project.image(name)).astype(np.float32)
        iw = im.shape[1]
        xs = ((np.arange(iw) + 0.5) / iw) * W - cx
        im[..., 3] = edge_fade(im[..., 3], xs, *fade)
        project.write_image(name, Image.fromarray((np.clip(im, 0, 255) + 0.5).astype(np.uint8), "RGBA"))


def to_spine(project, animation: str, frames: list[Path], src_fps: float, sim_meta: dict, *, params: dict | None = None,
             name: str = "magic_puff", x: float = 0.0, y: float = 0.0, scale: float = 1.0, start: float = 0.0,
             parent: str = "root", fps: float = 20.0, max_size: int = 652, lights: bool = True, rays: bool = True,
             glitter: bool = True, front_of: str = "", behind: str = "") -> dict:
    """Land the puff in ``animation``: the AE frames of ``<comp>_full`` as one sequence (normal blend) + lights + glitter.

    x, y: the banner's centre in ``parent``'s space; scale: game units per banner comp px; start: the Spine time of the
    simulation's t = 0 (the pop is t_burst later). fps: the playback rate after resampling (20 keeps the flow smooth
    with ~80 frames); max_size: the frames' longest side in px (652 = 30% of a 2172 banner; two 2048 atlas pages)."""
    from . import ae_bridge
    from .fx_recipes import Ctx

    known = {k: v for k, v in (sim_meta.get("params") or {}).items() if k in DEFAULTS}   # a sim.json of another version
    P = params_of({**known, **(params or {})})
    W, H = P["width"], P["height"]
    seq_frames = resample(list(frames), src_fps, fps)
    fw = ae_bridge.read_premultiplied(seq_frames[0], "alpha").shape[1]      # the comp's width (res x banner, rounded)
    smoke = ae_bridge.import_sequence(project, name, seq_frames, fps, mode="alpha", animation=animation,
                                      hit_ae=0.0, hit_at=start, x=x, y=y, scale=scale * W / fw, max_size=max_size,
                                      parent=parent, front_of=front_of, behind=behind)
    if P["edge_fade"]:
        _fade_ends(project, smoke["slot"], W, P["cx"], P["edge_fade"])
    out: dict[str, Any] = {"smoke": smoke, "animation": animation}
    if not (lights or glitter):
        return out
    c = Ctx(project, "magic_puff", x, y, scale, start, 1.0, 1.0, P["seed"], animation, parent, smoke["slot"], "", name)
    for tname, make in TEXTURES.items():
        c.tex(tname, make)
    U = lambda px: px                                                       # inside the group: banner comp px (scaled by the group)
    ox, oy = U(P["cx"] - W / 2), U(H / 2 - P["cy"])
    fr = lambda a, b, n: list(np.linspace(a, b, n))
    if lights:
        # the ambient glow behind the band
        gb = c.bone("glow", None, ox, oy)
        g = c.slot(gb, "fx/mp_soft_glow", 2176, color=P["ray_color"] + "00", height=560, make=tex_soft_glow)
        c.show([g], 0, 2.2)                     # every light is attached only while it can be seen (no hidden draws)
        c.color_keys(g, [0, 0.14, 0.5, 0.9, 1.4, 2.2], lambda u: P["ray_color"] + "%02x" % int(255 * float(np.interp(u, [0, 0.14, 0.5, 0.9, 1.4, 2.2], [0, 0.05, 0.32, 0.38, 0.24, 0]))))
        c.bone_keys(gb, "scale", [0, 0.3, 0.9, 2.2], lambda u: (float(np.interp(u, [0, 0.3, 0.9, 2.2], [0.15, 0.55, 1.0, 1.08])),
                                                                float(np.interp(u, [0, 0.3, 0.9, 2.2], [0.6, 0.9, 1.0, 1.1]))))
        lines = list(P["lines"] or [])
        if rays and len(lines) >= 2:
            # the ray fan rises from the bottom flare to the top line: two copies shimmer out of step
            base_y = U(H / 2 - max(lines))
            fan_h = abs(max(lines) - min(lines)) * 1.05
            env = lambda u: float(np.interp(u, [0, 0.38, 0.85, 1.3, 2.1], [0, 0, 0.62, 0.42, 0]))
            for k, (rot, ph) in enumerate(((0.0, 0.0), (1.6, 0.5))):
                rb = c.bone(f"rays{k}", None, ox, base_y, rot=rot)
                rs = c.slot(rb, f"fx/mp_rays{k}", fan_h * 2.66, color=P["ray_color"] + "00", oy=fan_h / 2, height=fan_h,
                            make=lambda k=k: tex_ray_fan(P["ray_angles"], seed=4 + k))
                c.show([rs], 0.38, 2.1)
                ts = fr(0, 2.2, 45)
                c.color_keys(rs, ts, lambda u, ph=ph: P["ray_color"] + "%02x" % int(255 * env(u) * (0.62 + 0.38 * math.sin(2 * math.pi * (u / 0.9 + ph)))))
                c.bone_keys(rb, "scale", fr(0.38, 1.2, 9), lambda u: (1.0, float(np.interp(u, [0.38, 0.9, 1.2], [0.55, 1.0, 1.0]))))
        for li, ly in enumerate(sorted(lines)):
            t_on = 0.30 if li == 0 else 0.26                                # the bottom line draws first
            lb = c.bone(f"line{li}", None, ox, U(H / 2 - ly))
            ls = c.slot(lb, "fx/mp_line", 1270, color="ffffff00", height=53)
            c.show([ls], t_on, 2.0)
            c.bone_keys(lb, "scale", [0, t_on, t_on + 0.08, t_on + 0.2, t_on + 0.45],
                        lambda u, t_on=t_on: (float(np.interp(u, [0, t_on, t_on + 0.08, t_on + 0.2, t_on + 0.45], [0.01, 0.01, 0.6, 0.93, 1.0])), 1.0))
            c.color_keys(ls, [0, t_on, t_on + 0.12, 0.9, 1.3, 2.0],
                         lambda u, t_on=t_on: "ffffff%02x" % int(255 * float(np.interp(u, [0, t_on, t_on + 0.12, 0.9, 1.3, 2.0], [0, 0, 0.95, 0.85, 0.6, 0]))))
            for side in (-1, 1):
                gbn = c.bone(f"glint{li}{'LR'[side > 0]}", lb, 0, 0)
                gs = c.slot(gbn, "fx/mp_glint", 256, color="ffe9b000", height=32)
                c.show([gs], t_on, t_on + 1.0)
                c.bone_keys(gbn, "translate", fr(t_on, t_on + 1.0, 12), lambda u, t_on=t_on, side=side: (side * 640 * (1 - (1 - min(1.0, max(0.0, (u - t_on) / 1.0))) ** 3), 0.0))
                c.bone_keys(gbn, "scale", [t_on, t_on + 0.2, t_on + 1.0], lambda u, t_on=t_on: (float(np.interp(u, [t_on, t_on + 0.2, t_on + 1.0], [0.5, 1.8, 0.8])), 1.0))
                c.color_keys(gs, [0, t_on, t_on + 0.06, t_on + 0.6, t_on + 1.0],
                             lambda u, t_on=t_on: "ffe9b0%02x" % int(255 * float(np.interp(u, [0, t_on, t_on + 0.06, t_on + 0.6, t_on + 1.0], [0, 0, 1, 0.75, 0]))))
            # the flare on this line ignites (bottom first), pulses once more, dies with the glow
            fb = c.bone(f"flare{li}", None, ox, U(H / 2 - ly))
            fh = c.slot(fb, "fx/mp_flare_halo", 307, color="ffffff00", height=243)
            sb = c.bone(f"star{li}", fb)
            fs = c.slot(sb, "fx/mp_flare_star", 358, color="ffffff00", height=192)
            t0 = 0.32 if li == 0 else 0.24
            c.show([fh], t0, 2.1)
            c.show([fs], t0, 1.8)
            c.color_keys(fh, [0, t0, t0 + 0.08, t0 + 0.5, 1.25, 1.4, 2.1],
                         lambda u, t0=t0: "ffffff%02x" % int(255 * float(np.interp(u, [0, t0, t0 + 0.08, t0 + 0.5, 1.25, 1.4, 2.1], [0, 0, 1, 0.7, 0.8, 0.62, 0]))))
            c.color_keys(fs, [0, t0, t0 + 0.06, t0 + 0.6, 1.2, 1.27, 1.8],
                         lambda u, t0=t0: "ffffff%02x" % int(255 * float(np.interp(u, [0, t0, t0 + 0.06, t0 + 0.6, 1.2, 1.27, 1.8], [0, 0, 0.95, 0.2, 0, 0.7, 0]))))
            c.bone_keys(fb, "scale", [0, t0, t0 + 0.08, t0 + 0.25, 1.25, 2.1],
                        lambda u, t0=t0: (lambda s: (s, s))(float(np.interp(u, [0, t0, t0 + 0.08, t0 + 0.25, 1.25, 2.1], [0.3, 0.3, 1.15, 0.95, 1.05, 0.8]))))
            c.bone_keys(sb, "rotate", [t0, 1.8], lambda u, t0=t0, li=li: (1 if li else -1) * 14 * (u - t0) / (1.8 - t0))
        # the pop: a point of light gathers, then flashes with an anamorphic streak as the smoke bursts
        pb = c.bone("pop", None, ox, oy)
        pf = c.slot(pb, "fx/mp_flare_halo", 256, color="ffffff00", height=256)
        ps = c.slot(pb, "fx/mp_glint", 1408, color="ffffff00", height=51)
        c.show([pf], 0, 0.55)
        c.show([ps], 0, 0.5)
        c.color_keys(pf, [0, 0.1, 0.14, 0.24, 0.55], lambda u: "ffffff%02x" % int(255 * float(np.interp(u, [0, 0.1, 0.14, 0.24, 0.55], [0, 0.55, 1, 0.85, 0]))))
        c.color_keys(ps, [0, 0.12, 0.15, 0.5], lambda u: "ffffff%02x" % int(255 * float(np.interp(u, [0, 0.12, 0.15, 0.5], [0, 0.2, 1, 0]))))
        c.bone_keys(pb, "scale", [0, 0.11, 0.16, 0.55], lambda u: (float(np.interp(u, [0, 0.11, 0.16, 0.55], [0.15, 0.35, 1.9, 2.6])),
                                                                   float(np.interp(u, [0, 0.11, 0.16, 0.55], [0.15, 0.35, 1.6, 1.9]))))
    n_glit = 0
    if glitter:
        cols = P["glitter_colors"]
        for gi, g in enumerate(sim_meta.get("glitter", [])):
            if not g["path"]:
                continue
            x0, y0 = g["path"][0][1], g["path"][0][2]
            bb = c.bone(f"glit{gi:02d}", None, U(x0 - W / 2), U(H / 2 - y0))
            colr = cols[g["hue"] % len(cols)]
            size = (0.95 if gi % 3 == 0 else 0.6) * g["size"] * 64
            gs = c.slot(bb, "fx/mp_speck", size, color=colr + "00", height=size)
            path = g["path"][::2] + ([g["path"][-1]] if len(g["path"]) % 2 == 0 else [])
            pts = {round(p_[0], 4): (p_[1] - x0, -(p_[2] - y0)) for p_ in path}
            c.bone_keys(bb, "translate", sorted(pts), lambda u, pts=pts: pts[round(u, 4)])
            t0, life = g["t0"], g["life"]
            c.show([gs], t0, t0 + life)
            ts = [0.0, max(0.0, t0 - 0.01)] + list(np.arange(t0, t0 + life, 1 / 12)) + [t0 + life]

            def a_(u, t0=t0, life=life, g=g):
                if u < t0:
                    return 0.0
                s_ = (u - t0) / life
                env_ = min(1.0, (u - t0) / 0.06) * (1 - max(0.0, (s_ - 0.6) / 0.4))
                return max(0.0, env_ * (0.7 + 0.3 * math.sin(2 * math.pi * (g["tw"] * u + g["ph"]))))
            c.color_keys(gs, ts, lambda u, colr=colr, a_=a_: colr + "%02x" % int(255 * min(1.0, a_(u))))
            n_glit += 1
    out.update(c.result(glitter=n_glit, lights=bool(lights), rays=bool(rays and lights)))
    return out
