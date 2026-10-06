"""Prop bundles: whole prop moments from the prop recipes, chained on their own EVENTS (not fixed offsets), so retiming
one member keeps the chain in sync.

* ``bonus_chest_reveal``  prop_peek -> prop_shake -> prop_open (+ coin_fountain at the pop) -> prop_upgrade
* ``collect_into_prop``   prop_absorb -> counter_plate (starts at the first arrival) -> prop_overflow
* ``pinata_style_break``  prop_dangle (all along) + prop_hit x3 (alternating sides) -> prop_shatter -> pinata_hit
* ``magic_vessel``        prop_idle + liquid_slosh + liquid_bubble + smoke_wisp, one seamless loop (4 idle cycles)

Bundle options that a member recipe also takes (prop, lid, pivot, plate, liquid, ...) are passed to every member that
accepts them; ``steps={recipe: {option: value}}`` overrides one member; ``skip=[recipe, ...]`` leaves members out.
"""
from __future__ import annotations

from .fx_recipes import BUNDLES, BUNDLE_INFO, RECIPES, apply
from .project import Project
from .timeline import AnimBuilder

SHARED = ("prop", "lid", "pivot", "plate", "liquid", "size", "at")


def _events(project: Project, anim: str, name: str) -> list[float]:
    an = project.data.animations.get(anim)
    return sorted(e.time for e in (an.events if an else []) if e.name == name)


class _Run:
    def __init__(self, project, anim, kw, options, art):
        self.p, self.anim, self.kw, self.parts = project, anim, kw, []
        self.shared = {k: v for k, v in options.items() if k in SHARED}
        self.over = dict(options.get("steps") or {})
        self.skip = set(options.get("skip") or [])
        self.art = art or {}
        bad = set(self.over) - set(RECIPES)
        if bad:
            raise ValueError(f"steps name unknown recipe(s) {sorted(bad)}")

    def step(self, recipe: str, start: float, name: str = "", **opts) -> dict | None:
        if recipe in self.skip:
            return None
        accepted = RECIPES[recipe]["options"]
        o = {k: v for k, v in self.shared.items() if k in accepted}
        o.update(opts)
        o.update(self.over.get(recipe, {}))
        call = {k: v for k, v in self.kw.items() if k in ("x", "y", "scale", "intensity", "seed", "parent", "front_of", "behind")}
        for k in ("duration", "color", "count"):
            if k in o and k not in accepted:
                call[k] = o.pop(k)
        res = apply(self.p, recipe, start=max(0.0, start), into=self.anim, name=name or "", options=o,
                    art=self.art.get(recipe), **call)
        self.parts.append(res)
        return res

    def ev(self, name: str, default: float) -> list[float]:
        ts = _events(self.p, self.anim, name)
        return ts or [default]

    def summary(self, bundle: str, end_event: float | None = None) -> dict:
        an = self.p.data.animations[self.anim]
        end = end_event if end_event is not None else max([0.0] + [k.time for tl in an.bones.values() for ks in tl.values() for k in ks]
                                                         + [k.time for tl in an.slots.values() for ks in tl.values() for k in ks])
        AnimBuilder(self.p.data, self.anim, replace=False).event(round(end, 4), f"fx_{bundle}_end")
        AnimBuilder(self.p.data, self.anim, replace=False).event(round(self.kw.get("start", 0.0), 4), f"fx_{bundle}")
        return {"recipe": bundle, "animation": self.anim, "parts": [p["recipe"] for p in self.parts],
                "slots": [s for p in self.parts for s in p.get("slots", [])], "bones": sum(p.get("bones", 0) for p in self.parts),
                "event": f"fx_{bundle}", "end": round(end, 4)}


def _begin(project, bundle, kw, options, art):
    bad = set(options) - set(SHARED) - {"steps", "skip"}
    if bad:
        raise ValueError(f"unknown option(s) {sorted(bad)} for {bundle!r}; valid: {sorted(SHARED + ('steps', 'skip'))}")
    anim = kw.get("into") or kw.get("name") or bundle
    if not kw.get("into"):
        AnimBuilder(project.data, anim, replace=True)
    return _Run(project, anim, kw, options, art)


def bonus_chest_reveal(project: Project, *, options, art, **kw) -> dict:
    r = _begin(project, "bonus_chest_reveal", kw, options, art)
    t = kw.get("start", 0.0)
    r.step("prop_peek", t)
    t = r.ev("prop_peek_shut", t + 1.6)[-1] + 0.25
    r.step("prop_shake", t)
    t = r.ev("prop_shake_release", t + 1.4)[-1]
    r.step("prop_open", t)
    pop = r.ev("prop_open", t + 0.35)[-1]
    r.step("coin_fountain", pop)                    # its own default length (the coins must land and settle)
    settled = r.ev("prop_open_settled", pop + 1.0)[-1]
    r.step("prop_upgrade", settled + 0.6)
    return r.summary("bonus_chest_reveal")


def collect_into_prop(project: Project, *, options, art, **kw) -> dict:
    r = _begin(project, "collect_into_prop", kw, options, art)
    t = kw.get("start", 0.0)
    r.step("prop_absorb", t)
    hits = r.ev("prop_absorb_hit", t + 0.6)
    r.step("counter_plate", hits[0], steps=max(3, len(hits)))
    done = r.ev("counter_done", hits[-1] + 0.4)[-1]
    r.step("prop_overflow", max(hits[-1], done) + 0.15)
    return r.summary("collect_into_prop")


def pinata_style_break(project: Project, *, options, art, **kw) -> dict:
    r = _begin(project, "pinata_style_break", kw, options, art)
    t = kw.get("start", 0.0)
    hits = [t + 0.45, t + 1.15, t + 1.85]
    for i, h in enumerate(hits):                       # alternate sides, each harder than the last
        r.step("prop_hit", h, name=f"hit{i}", direction=0.0 if i % 2 == 0 else 180.0, squash=0.18 + 0.05 * i)
    crack = hits[-1] + 0.6
    r.step("prop_shatter", crack)
    burst = r.ev("prop_shatter", crack + 0.7)[-1]
    r.step("pinata_hit", burst)
    end = burst + RECIPES["pinata_hit"]["duration"]   # swing until the fireballs have landed
    r.step("prop_dangle", t, duration=end - t, steady=True)   # swinging all along (keys added last: under the hits)
    return r.summary("pinata_style_break", end)


def magic_vessel(project: Project, *, options, art, **kw) -> dict:
    r = _begin(project, "magic_vessel", kw, options, art)
    t = kw.get("start", 0.0)
    cyc = RECIPES["prop_idle"]["duration"]
    L = round(cyc * 4, 4)                              # 4 idle cycles: long enough for bubbles and smoke to read
    r.step("prop_idle", t, cycles=4)
    if r.shared.get("liquid"):
        r.step("liquid_slosh", t, cycles=4)
    else:
        r.skip.add("liquid_slosh")
    r.step("liquid_bubble", t, duration=L)
    r.step("smoke_wisp", t, duration=L)
    return r.summary("magic_vessel", t + L)


BUNDLES.update({"bonus_chest_reveal": bonus_chest_reveal, "collect_into_prop": collect_into_prop,
                "pinata_style_break": pinata_style_break, "magic_vessel": magic_vessel})
_OPTS = {"prop": {"default": "", "what": "the prop's root bone (passed to every member that takes it)"},
         "lid": {"default": "", "what": "lid bone (peek / open)"}, "pivot": {"default": None, "what": "hinge / pivot (members that take it)"},
         "plate": {"default": "", "what": "counter plate bone"}, "liquid": {"default": "", "what": "liquid bone (magic_vessel)"},
         "size": {"default": None, "what": "prop size for members that take it"}, "at": {"default": None, "what": "mouth / spout / impact point"},
         "steps": {"default": {}, "what": "{recipe: {option: value}} overrides for one member"},
         "skip": {"default": [], "what": "member recipes to leave out"}}
BUNDLE_INFO.update({
    "bonus_chest_reveal": {"summary": "prop_peek -> prop_shake -> prop_open (+ coin_fountain at the pop) -> prop_upgrade, chained on each "
                                      "member's events. Events: every member's, fx_bonus_chest_reveal_end.",
                           "kind": "bundle", "anchor": "Prop centre", "default_duration": 0.0, "options": _OPTS},
    "collect_into_prop": {"summary": "prop_absorb -> counter_plate (from the first arrival, one tick per item) -> prop_overflow.",
                          "kind": "bundle", "anchor": "Prop centre", "default_duration": 0.0, "options": _OPTS},
    "pinata_style_break": {"summary": "prop_dangle all along + three prop_hit (alternating sides, harder each time) -> prop_shatter -> "
                                      "pinata_hit at the burst.",
                           "kind": "bundle", "anchor": "Prop centre", "default_duration": 0.0, "options": _OPTS},
    "magic_vessel": {"summary": "prop_idle + liquid_slosh (with options liquid=) + liquid_bubble + smoke_wisp as one seamless loop of four "
                                "idle cycles (3.02 s).",
                     "kind": "bundle", "anchor": "Vessel centre", "default_duration": 0.0, "options": _OPTS},
})
