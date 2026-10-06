#!/bin/sh
# Install (or update) this repo's Claude Code skills into ~/.claude/skills.
#   sh skills/install.sh            from a clone
# Each skill is copied whole (SKILL.md + scripts / templates); an existing copy of the same skill is replaced.
set -e
here=$(cd "$(dirname "$0")" && pwd)
dest="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
mkdir -p "$dest"
for d in "$here"/*/; do
  name=$(basename "$d")
  [ -f "$d/SKILL.md" ] || continue
  rm -rf "$dest/$name"
  cp -R "$d" "$dest/$name"
  echo "installed $name -> $dest/$name"
done
