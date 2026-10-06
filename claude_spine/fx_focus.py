"""Focus / speed lines for ``fx_recipe``: the anime "focus lines" that converge on an impact (a punch clash, a
jackpot hit, a character's entrance).

Hand-drawn focus lines are redrawn every few frames, each time in new places with new lengths, which is what makes
them flicker with energy; smoothly sliding lines read as a tunnel instead. So every line is re-placed on STEPPED keys
`rate` times a second (new angle on the ring, new radius, length and width, sometimes hidden), costing no tweening.
`hit` makes the ring rush inward and brighten around that moment (the impact).
"""
from __future__ import annotations

import math

import numpy as np

from .fx_recipes import RECIPES, ROLES, Ctx, _hexn, hexa


def speed_lines(c: Ctx, P: dict) -> dict:
    D, N = float(P["duration"]), int(P["count"])
    col = _hexn(P["color"], "FFFFFF")
    r_in, r_out = (float(v) for v in P["radius"])
    hit = P["hit"]
    rate = float(P["rate"])
    rng = np.random.default_rng(c.seed + 31)
    from .fx_pinata import PICS                      # the shared light streak
    ticks = [round(k / rate, 4) for k in range(int(math.floor(D * rate)) + 1)]
    for i in range(N):
        b = c.bone(f"l{i}")
        s = c.slot(b, "fx/pinata_light_streak", float(P["length"]), height=float(P["width"]), make=PICS["light_streak"],
                   role="streak", stretch=True)
        c.show([s], 0, D)
        pos, rot, scl, colk = [], [], [], []
        for t in ticks:
            rush = math.exp(-((t - float(hit)) / 0.12) ** 2) if hit is not None else 0.0
            a = float(rng.uniform(0, 2 * math.pi))
            rr = float(rng.uniform(r_in, r_out)) * (1 - 0.35 * rush)
            on = rng.random() < float(P["density"])
            peak = 0.55 + 0.45 * rush
            T = c.T(t)
            pos.append((T, rr * math.cos(a), rr * math.sin(a), "stepped"))
            rot.append((T, math.degrees(a), "stepped"))             # the streak lies along the radius
            scl.append((T, float(rng.uniform(0.6, 1.6)), float(rng.uniform(0.6, 1.4)), "stepped"))
            colk.append((T, hexa(col, c.a(float(rng.uniform(0.35, 1.0)) * peak if on else 0.0)), "stepped"))
        c.ab.bone(b, "translate", pos)
        c.ab.bone(b, "rotate", rot)
        c.ab.bone(b, "scale", scl)
        c.ab.slot_color(s, colk)
    if hit is not None:
        c.ab.event(c.T(float(hit)), "fx_speed_lines_hit")
    return c.result(duration=D, lines=N, redraws=len(ticks))


RECIPES.update({
    "speed_lines": dict(
        fn=speed_lines, duration=2.6, kind="window", count=26, color="FFFFFF",
        summary="Anime focus lines converging on a point: thin streaks on a ring, each redrawn `rate` times a second on "
                "STEPPED keys (new angle, radius, length, sometimes hidden), the hand-drawn flicker; `hit` = seconds of the "
                "impact, when the ring rushes inward and brightens (event fx_speed_lines_hit).",
        anchor="The point the lines converge on (the impact).",
        options=dict(radius=([330.0, 560.0], "[inner, outer] ring the lines sit on"), length=(260.0, "streak length"),
                     width=(14.0, "streak thickness"), rate=(12.0, "redraws per second (12 = every 2 frames at 24 fps)"),
                     density=(0.7, "share of lines visible at each redraw"), hit=(None, "seconds of the impact (None: no rush)"))),
})
ROLES["speed_lines"] = {"streak": "one light streak, horizontal, brightest in the middle (it is stretched to length x width)"}
RECIPES["speed_lines"]["roles"] = ROLES["speed_lines"]
