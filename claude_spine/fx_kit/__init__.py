"""Bundled realistic texture kit for ``fx_recipe kit="realistic"``.

The procedural pictures every recipe draws for itself are clean but read as placeholder next to painted game art. The
fix that worked on a real job was to keep every recipe's motion and swap its pictures, through the ``art=`` roles,
for photographic CC0 particles: real smoke, real lightning, lens flares, smoke rings, a painted flash. This package
ships those pictures (32 PNGs, ~1.5 MB, all Kenney CC0: see CREDITS.md and LICENSE-kenney.txt; ``build_kit.py``
rebuilds them) and the table that picks one per ROLE NAME, so ``kit="realistic"`` re-skins any recipe in one argument.

Rules:

* the caller's own ``art=`` always wins; the kit only fills the roles nobody supplied;
* roles that ARE the game's art (symbol, coin, reticle, number plates, confetti, blocks, shards, ...), 9-slice
  frames and mesh-bent strips have no kit picture and stay procedural;
* glows come from ``glow_s`` at 0.7 of the recipe's width and rings from ``ring_s`` / ``ring_floor``: tuned, tighter
  variants, because a photographic glow is fuller than a drawn one and turns into a haze over the subject when big;
* a picture keeps the recipe's WIDTH and its own aspect (``scale`` multiplies the width), as any ``art=`` spec.

Any kit picture can also be named directly in ``art=``: ``art={"glow": "kit:glow_s"}`` or
``{"glow": {"path": "kit:glow_s", "scale": 0.5}}``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

KIT_DIR = Path(__file__).resolve().parent

#: kit name -> one-line description (listed by fx_recipe recipe="" and recipe="kit")
KITS: dict[str, str] = {
    "realistic": "photographic CC0 particles (Kenney Particle Pack + Smoke Particles): real smoke, real lightning, "
                 "lens flares, smoke rings, a painted flash; glows and rings are pre-tightened so they never haze",
}
#: kit names that mean "no kit" (a sequence step can switch an inherited kit off with one of these)
NO_KIT = ("", "none", "procedural")

# role name -> (kit picture, width multiplier). The same role name means the same kind of picture across recipes;
# the exceptions are in RECIPE_ROLES below.
ROLE_PICS: dict[str, tuple[str, float]] = {
    # light
    "glow": ("glow_s", 0.7), "glow_soft": ("glow_s", 0.7), "halo": ("glow_s", 0.7), "aura": ("glow_s", 0.7),
    "centre_glow": ("glow_s", 0.7), "lock": ("glow_s", 0.7), "floor": ("glow_s", 0.7), "pool": ("glow_s", 0.7),
    "sky": ("glow_s", 0.7), "head": ("glow_s", 0.7), "impact_glow": ("glow_s", 0.7), "puff_glow": ("glow_s", 0.7),
    "shine_glow": ("glow_s", 0.7),
    "core": ("flare_01", 1.0), "glow_core": ("flare_01", 1.0), "burst": ("flare_01", 1.0),
    "flare": ("flare_01", 1.0), "shine_flare": ("flare_01", 1.0),
    "flare_star": ("star_06", 1.0), "glint": ("star_06", 1.0), "sparkle": ("star_06", 1.0),
    "shine_spark": ("star_06", 1.0),
    "rays": ("star_08", 1.0), "shine_rays": ("star_08", 1.0),
    "flash": ("star_09", 1.0), "hit": ("star_09", 1.0), "puff_flash": ("star_09", 1.0),
    "starburst": ("star_09", 0.5), "impact_star": ("star_09", 0.5), "pop": ("star_09", 0.5),
    "flash_burst": ("flash_s", 0.8),
    # rings (round, never a square cell)
    "ring": ("ring_s", 1.0), "ring_inner": ("ring_s", 1.0), "impact_ring": ("ring_s", 1.0),
    "shine_ring": ("ring_s", 1.0), "cell_glow": ("ring_s", 1.0), "rune": ("ring_s", 1.0),
    "centre_rune": ("ring_floor", 1.0), "runes": ("ring_floor", 1.0), "puff_ring": ("smoke_10", 1.0),
    # particles
    "spark": ("star_05", 1.0), "mote": ("star_05", 1.0), "ember": ("star_05", 1.0), "flake": ("star_05", 1.0),
    # streaks and trails
    "light_streak": ("trace_01", 1.0), "line": ("trace_01", 1.0),
    "energy_trail": ("trail_r", 1.0), "tail": ("trail_up", 1.0),
    "swirl": ("twirl_02", 1.0), "swirl_a": ("twirl_02", 0.72), "swirl_b": ("twirl_03", 0.66), "comet": ("twirl_01", 1.0),
    # smoke and fire
    "cloud": ("smoke_07", 1.0), "smoke_puff": ("smoke_07", 1.0), "dust": ("smoke_07", 1.0),
    "smoke": ("smoke_08", 1.0), "mist": ("smoke_08", 1.0), "puff": ("smoke_08", 1.0), "fire": ("smoke_08", 1.0),
    "flame": ("muzzle_02", 1.0), "flame_tongue": ("flame_05", 1.0),
    # electricity
    "bolt": ("spark_05", 1.0), "sticky_spark": ("spark_04", 1.0),
    # fx_real's own roles
    "bolt_2": ("bolt_h6", 1.0), "spark_1": ("spark_01", 1.0), "spark_2": ("spark_02", 1.0),
    "spark_3": ("spark_03", 1.0), "spark_4": ("spark_04", 1.0), "flame_1": ("muzzle_02", 1.0),
    "flame_2": ("muzzle_03", 1.0), "flame_3": ("muzzle_04", 1.0), "flame_4": ("muzzle_05", 1.0),
}

_TWINKLE = ("star_06", 1.0)
# recipe -> {role: (picture, scale) | None}: where a role name means something else in that recipe. None = keep the
# procedural picture (a mesh-bent strip, a shaped crack, a full-screen wash, ...).
RECIPE_ROLES: dict[str, dict[str, tuple[str, float] | None]] = {
    "rune_ring": {"ring": ("ring_floor", 1.0)},
    "near_miss": {"ring": ("ring_floor", 1.0)},
    "hold_respin": {"ring": None},                       # the counter band: a strip bent round the ring as a mesh
    "saber": {"glow": None, "core": None},               # beam strips, uniform along their length
    "scatter_trigger": {"core": None},                   # the beam's core strip
    "explosion": {"dust": ("smoke_10", 1.0)},            # the ground dust RING
    "lightning_storm": {"cloud": ("glow_s", 0.7)},       # the light inside the cloud, not a cloud
    "electric_frame": {"spark": ("spark_03", 1.0)},
    "free_spins_transition": {"glow": ("ring_s", 1.0)},  # its rim light is drawn with a ring
    "screen_shake": {"flash": ("glow_s", 1.0)},          # a full-screen wash, not a star
    "reel_stop": {"flash": ("glow_s", 0.7)},
    "prop_charge": {"crack": ("spark_07", 1.0)},         # a horizontal crack of light: real lightning
    "turbo_spin": {"line": ("trace_01v", 1.0)},
    "expanding_wild": {"line": ("trace_01v", 1.0)},
    "weather": {"streak": ("trace_01v", 1.0)},
    "wild_land": {"streak": ("trace_01v", 1.0)},
    "speed_lines": {"streak": ("trace_01", 1.0)},
    "prop_bob": {"body": ("glow_s", 0.7)},
    "prop_blink": {"body": ("glow_s", 0.7)},
    "prop_breathe_heavy": {"body": ("glow_s", 0.7)},
    "bolt_link": {"bolt": ("bolt_h5", 1.0), "bolt_3": ("spark_07", 1.0)},
    # twinkles and head stars are four-point stars, not soft dots
    **{n: {"spark": _TWINKLE} for n in ("twinkles", "light_beam", "cell_glow", "meteor_trace", "projectile", "shine",
                                         "frost", "icicles", "payline", "win_highlight", "multiplier_stack", "win_rollup",
                                         "coin_fountain")},
}


def pictures() -> list[str]:
    """Every kit picture name (the PNGs next to this file)."""
    return sorted(p.stem for p in KIT_DIR.glob("*.png"))


def path(pic: str) -> Path:
    p = KIT_DIR / f"{pic}.png"
    if not p.exists():
        raise ValueError(f"no kit picture {pic!r}; kit pictures: {pictures()}")
    return p


def check(kit: str) -> str:
    """Normalise a kit name ('' / none / procedural = no kit); unknown names are a clear error."""
    k = (kit or "").strip().lower()
    if k in NO_KIT:
        return ""
    if k not in KITS:
        raise ValueError(f"unknown kit {kit!r}; one of {sorted(KITS)} (or '' for the procedural pictures)")
    return k


def pick(recipe: str, role: str, what: str = "") -> tuple[str, float] | None:
    """The kit picture for one role of one recipe, or None when the role keeps its procedural picture."""
    over = RECIPE_ROLES.get(recipe, {})
    if role in over:
        return over[role]
    if "9-slice" in what:                                  # a 9-slice frame needs slice / px art made for it
        return None
    return ROLE_PICS.get(role)


def spec(pic: str, scale: float = 1.0) -> dict[str, Any]:
    """An art= spec for a kit picture (``_kit`` names the shared texture, so recipes share one atlas region)."""
    out: dict[str, Any] = {"path": str(path(pic)), "_kit": pic}
    if scale != 1.0:
        out["scale"] = scale
    return out


def fill(kit: str, recipe: str, roles: dict[str, str], art: dict | None) -> tuple[dict, dict[str, str]]:
    """(art with every role the caller did not supply filled from the kit, {role: kit picture} that were filled)."""
    art = dict(art or {})
    if not check(kit):
        return art, {}
    filled: dict[str, str] = {}
    for role, what in roles.items():
        if role in art:
            continue
        got = pick(recipe, role, what)
        if got:
            art[role] = spec(*got)
            filled[role] = got[0]
    return art, filled


def resolve_path(p: str) -> str:
    """'kit:<picture>' -> the bundled file; anything else unchanged."""
    if isinstance(p, str) and p.startswith("kit:"):
        return str(path(p[4:].strip()))
    return p


def table(roles_by_recipe: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    """The kit listing: kits, pictures, the role table, per-recipe exceptions, and (given the recipes' roles) the
    picture every recipe would get."""
    out: dict[str, Any] = {
        "kits": dict(KITS), "pictures": pictures(), "dir": str(KIT_DIR),
        "roles": {r: {"picture": p, "scale": s} for r, (p, s) in sorted(ROLE_PICS.items())},
        "exceptions": {n: {r: (None if v is None else {"picture": v[0], "scale": v[1]}) for r, v in d.items()}
                       for n, d in sorted(RECIPE_ROLES.items())},
        "rules": ["your own art= always wins; the kit fills only the roles you did not give",
                  "game-art roles (symbol, coin, reticle, plates, confetti, blocks, shards), 9-slice frames and mesh-bent "
                  "strips stay procedural",
                  "a picture keeps the recipe's width and its own aspect; scale multiplies the width",
                  "art={role: 'kit:<picture>'} names any kit picture directly",
                  "credits: Kenney (kenney.nl), CC0 1.0; see fx_kit/CREDITS.md"],
    }
    if roles_by_recipe:
        out["by_recipe"] = {n: {r: p for r, (p, _) in ((r, pick(n, r, w)) for r, w in roles.items() if pick(n, r, w))}
                            for n, roles in sorted(roles_by_recipe.items())}
    return out
