"""<PROJECT> VFX: After Effects for what needs real noise, Spine for the rest.  (clip-to-spine skill starter)

    ~/.local/bin/uvx --from git+https://github.com/kumikilongyeyo/CLAUDE-SPINE@<SHA> python build.py

1. renders every comp in COMPS from ae/<PROJECT>.aep once into ae/frames/<comp>/ (aerender, headless, reads the SAVED
   .aep; delete a folder to re-render that comp after editing it in AE)
2. builds <PROJECT>.json: one function per animation, AE comps come in as frame sequences with their timing kept,
   Spine recipes (fx_recipe) mixed into the same animation with into=
3. validates, packs export/ (json + atlas + png) and spine_project/<PROJECT>.spine (real Spine import, repairs printed)
Layout: measured on a gridded clean frame of the clip (cliptools grid --units), origin at the screen centre, y up.
"""
import shutil
import sys
from pathlib import Path

from claude_spine import ae_bridge as B, ae_vfx_director as D, atlas, fx_recipes as R, qa, spine_cli
from claude_spine.ir import Bone, new_skeleton
from claude_spine.project import Project

ROOT = Path(__file__).resolve().parent
NAME = "<PROJECT>"
AEP = ROOT / "ae" / f"{NAME}.aep"
FRAMES = ROOT / "ae" / "frames"
FPS = 24                                    # the comps' fps (the ae_template default)
SCREEN = (720, 1089)                        # skeleton units = the clip frame scaled to 720 wide

# ---- layout (measured, never guessed)
COLS = [-252.0, -128.0, 5.0, 136.0, 264.0]  # e.g. reel centres
ROWS = [136.0, 51.0, -40.0, -125.0, -210.0]

# ---- AE comps: name -> (mode, max_size). mode "additive" = light on black (lightning, glows),
#      "alpha" = the comp's own transparency (fire, auras, smoke). 256 px is plenty for a looping aura.
COMPS = {
    # "xx_bolt_v1": ("additive", 320),
    # "xx_aura_fire_v1": ("alpha", 256),
}


def render_all():
    for comp in COMPS:
        out = FRAMES / comp
        if out.exists() and any(out.glob("*.tif")):
            continue
        out.mkdir(parents=True, exist_ok=True)
        B.render_comp(AEP, comp, out)
        print("rendered", comp)


def bone(p, name, parent="root", x=0.0, y=0.0, rot=0.0, sx=1.0, sy=1.0):
    """An aiming bone: rotate / stretch it to point a flame or a bolt; sequences parented to it follow."""
    nm = p.data.unique_name(name)
    p.data.bones.append(Bone(name=nm, parent=parent, x=x, y=y, rotation=rot, scaleX=sx, scaleY=sy, length=10))
    return nm


def seq(p, comp, name, anim, *, parent="root", x=0.0, y=0.0, scale=1.0, start=0.0, loop=False, until=0.0,
        blend="", color="FFFFFFFF", hit_ae=None, hit_at=None, event="impact", style="premium",
        target="mobile_feature"):
    """One AE comp as an optimized frame sequence in animation `anim`.

    blend="" follows the comp mode; pass blend="normal" for flames over bright/same-coloured backgrounds.
    The director trims/caps the sequence for target memory. COMPS may still request a larger texture; when it does,
    the frame allowance falls automatically unless both size and frame count are explicitly overridden."""
    mode, max_size = COMPS[comp]
    kw = dict(hit_ae=hit_ae, hit_at=hit_at) if hit_ae is not None else dict(start=start)
    return D.import_optimized(
        p, name, frames_dir=str(FRAMES / comp), fps=FPS, mode=mode, blend=blend, animation=anim,
        parent=parent, x=x, y=y, scale=scale, seq_mode="loop" if loop else "once", until=until,
        max_size=max_size, color=color, event=event, style=style, target=target, **kw)


# ---- one function per animation (name = the game event it plays on) ----------------------------------------------
def example_hit(p):
    A = "example_hit"
    R.apply(p, "hit_burst", x=COLS[2], y=ROWS[0], into=A, color="FFB347", name="hit")
    R.apply(p, "shine", x=COLS[2], y=ROWS[0], into=A, start=0.05, name="shine", options={"size": 110.0})
    # seq(p, "xx_bolt_v1", "bolt", A, x=COLS[2], y=ROWS[0] + 176, scale=0.55, start=0.1)


ANIMATIONS = [example_hit]


def main():
    render_all()
    p = Project(ROOT / f"{NAME}.json", new_skeleton(NAME, *SCREEN))
    if p.images_dir.exists():
        shutil.rmtree(p.images_dir)
    for f in ANIMATIONS:
        f(p)
    v = qa.validate(p.data)
    if not v["ok"]:
        raise SystemExit(v["errors"])
    p.save()
    shutil.rmtree(ROOT / "export", ignore_errors=True)
    atlas.pack(p, ROOT / "export", NAME)
    (ROOT / "spine_project").mkdir(exist_ok=True)
    # importing into an existing .spine ADDS another skeleton (NAME2, NAME3, ...) instead of replacing it, and the
    # export then writes one json per skeleton: start from a fresh .spine on every build
    (ROOT / "spine_project" / f"{NAME}.spine").unlink(missing_ok=True)
    r = spine_cli.make_project(str(p.path), str(ROOT / "spine_project" / f"{NAME}.spine"))
    spine_cli.export_project(str(ROOT / "spine_project" / f"{NAME}.spine"), str(ROOT / "export"), "json")
    print(list(p.data.animations), len(p.data.bones), "bones", len(p.data.slots), "slots; spine import repairs:", r["repairs"])
    print("atlas pages:", sorted(x.name for x in (ROOT / "export").glob("*.png")))


if __name__ == "__main__":
    sys.exit(main())
