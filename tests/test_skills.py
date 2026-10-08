"""The Claude Code skills shipped in skills/: valid frontmatter, scripts that compile, and the starters wired to this
package's real API."""
import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1] / "skills"
SKILLS = sorted(p.parent for p in ROOT.glob("*/SKILL.md"))


def test_both_skills_exist():
    assert {p.name for p in SKILLS} >= {"clip-breakdown", "clip-to-spine"}


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_frontmatter(skill):
    text = (skill / "SKILL.md").read_text()
    m = re.match(r"^---\nname: (.+)\ndescription: (.+?)\n---\n", text, re.S)
    assert m, "SKILL.md must start with name / description frontmatter"
    assert m.group(1) == skill.name
    assert 200 < len(m.group(2)) < 1024, "the description is what triggers the skill: say what and when"


@pytest.mark.parametrize("py", sorted(ROOT.glob("*/*/*.py")), ids=lambda p: f"{p.parent.parent.name}/{p.name}")
def test_scripts_parse(py):
    ast.parse(py.read_text())


def test_cliptools_help_runs_without_a_video():
    r = subprocess.run([sys.executable, str(ROOT / "clip-breakdown/scripts/cliptools.py"), "--help"], capture_output=True, text=True)
    assert r.returncode == 0 and "motion" in r.stdout and "onion" in r.stdout


def test_starters_use_the_real_api():
    from claude_spine import ae_bridge, ae_vfx_director, atlas, fx_recipes, qa, spine_cli  # noqa: F401
    src = (ROOT / "clip-to-spine/templates/build.py").read_text()
    for name in ("D.import_optimized", "B.render_comp", "R.apply", "atlas.pack", "spine_cli.make_project", "qa.validate"):
        assert name in src
    assert hasattr(ae_vfx_director, "import_optimized") and hasattr(ae_bridge, "render_comp") and hasattr(atlas, "pack")


def test_every_template_named_in_the_skill_exists():
    from claude_spine import ae_templates, fx_recipes
    text = (ROOT / "clip-to-spine/SKILL.md").read_text()
    names = set(re.findall(r"\| `([a-z_]+)` ", text))
    assert names, "the known-good table lists templates"
    have = set(ae_templates.list_templates()) | set(fx_recipes.RECIPES)
    assert names <= have, names - have


def test_install_script(tmp_path):
    r = subprocess.run(["sh", str(ROOT / "install.sh")], env={"CLAUDE_SKILLS_DIR": str(tmp_path), "PATH": "/usr/bin:/bin"},
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "clip-breakdown/scripts/cliptools.py").exists() and (tmp_path / "clip-to-spine/templates/build.py").exists()


def test_starter_build_starts_from_a_fresh_spine_project():
    src = (ROOT / "clip-to-spine/templates/build.py").read_text()
    assert src.index(".unlink(missing_ok=True)") < src.index("spine_cli.make_project"), "a stale .spine gains a skeleton per build"
    assert src.index('shutil.rmtree(ROOT / "export"') < src.index("atlas.pack")
