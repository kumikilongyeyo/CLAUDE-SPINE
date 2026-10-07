# Claude Code skills

| Skill | What it does |
|---|---|
| `clip-breakdown` | Watches a clip and breaks the animation down: beat sheet with timings in seconds and frames, easing, layering, measured layout, and which tool each part needs. Ships `cliptools.py` (motion graph that finds the beats, contact sheets, strips, onion-skin spacing charts, measuring grid; macOS, no ffmpeg). |
| `clip-to-spine` | Rebuilds a clip's effects as Spine 4.2 animations: After Effects templates for noise (lightning, fire, auras, smoke), `fx_recipe` for moving light, previews over the clip, caveats report. Ships starter `build.py` / `render.py` / `ae_sheet.py`. |
| `ae-vfx-director` | Plans realistic/premium/stylized/anime AE effects, enforces clean layer structure and impact timing, self-reviews rendered passes, then imports through a mobile-safe AE -> Spine budget. |

Install: `sh skills/install.sh` (copies them to `~/.claude/skills`). They use the `claude-spine` MCP from this repo and,
for the AE parts, an After Effects MCP.
