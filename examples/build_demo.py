"""Build the README demo from the procedural sample character, using the
same functions the MCP tools call. Writes to ./out/demo and refreshes the
GIFs in docs/.

    python examples/build_demo.py
"""
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from claude_spine import fx, juice, qa, render, rig, runtime, samples  # noqa: E402
from claude_spine.mesh import rig_mesh  # noqa: E402
from claude_spine.timeline import AnimBuilder  # noqa: E402

root = Path(__file__).resolve().parents[1]
out = root / "out" / "demo"
shutil.rmtree(out, ignore_errors=True)

p = samples.make_character(out / "hero")
sk = p.data
rig_mesh(p, "arm_l", bones=["arm_l1", "arm_l2"])
rig_mesh(p, "arm_r", bones=["arm_r1", "arm_r2"])
rig_mesh(p, "body", bones=["hip", "chest"])
rig.add_ik(sk, ["arm_l1", "arm_l2"])
rig.add_ik(sk, ["arm_r1", "arm_r2"])
for lock in ("lock_l", "lock_r"):
    rig.rig_strand(p, lock, n_bones=4, physics="hair")
rig.rig_strand(p, "cape", n_bones=3, physics="cloth")
rig.turn_rig(p, "head", "face", {"eye_l": 0.9, "eye_r": 0.9, "brow_l": 0.95, "brow_r": 0.95, "nose": 1.25,
                                 "mouth": 1.0, "fringe": 0.8, "ear_l": -0.35, "ear_r": -0.35, "hair_back": -0.5})
juice.apply(p, fx=True, shine_slot="body")
juice.apply(p, ["flip", "win_epic"], fx=True)
AnimBuilder(sk, "wave") \
    .bone("arm_r2_ik", "translate", [(0, 0, 0), (0.3, 40, 150), (0.6, 10, 140), (0.9, 40, 150), (1.2, 0, 0)]) \
    .bone("head", "rotate", [(0, 0), (0.3, 8), (0.9, -8), (1.2, 0)]) \
    .bone("hip", "translate", [(0, 0, 0), (0.3, 0, 20, "quad_in"), (0.6, 0, 0), (0.9, 0, 20, "quad_in"), (1.2, 0, 0)])
fx.generate(p, "explosion", y=250)
fx.generate(p, "ripple", size=300)
p.save()

print("validate:", qa.validate(sk)["ok"])
print("budget:", qa.budget(sk, "mobile_character")["metrics"])
anims = ["wave", "turn_test", "land", "win", "flip", "win_epic", "explosion", "ripple"]
dump = runtime.run(p, animations=anims, fps=20, geometry=True)
assert dump["ok"], dump.get("error") or dump["problems"][:3]
for a in anims:
    render.render_animation(dump, a, out / "previews", size=240, sheet=False)
render.render_setup(dump, out / "previews" / "mesh.png", size=420, wire=True)

docs = root / "docs"
docs.mkdir(exist_ok=True)
for a in ["wave", "turn_test", "land", "win_epic", "flip", "ripple"]:
    shutil.copy(out / "previews" / f"{a}.gif", docs / f"{a}.gif")
shutil.copy(out / "previews" / "mesh.png", docs / "mesh.png")
print("previews in", out / "previews")
