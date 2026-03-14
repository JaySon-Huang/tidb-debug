#!/bin/bash
# Remove tidb-debug symlinks from Claude/OpenCode/Codex global skill directories.
#
# Usage: ./unsync-skills.sh
#
# Removes directory symlinks for skills stored under:
#   ./.agents/<name>/
#
# Target directories:
#   - ~/.claude/skills/<name>/
#   - ~/.config/opencode/skills/<name>/
#   - ${CODEX_HOME:-~/.codex}/skills/<name>/

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_DIR="${SCRIPT_DIR}/.agents"

# Target directories
CLAUDE_SKILLS_DIR="${HOME}/.claude/skills"
OPENCODE_SKILLS_DIR="${HOME}/.config/opencode/skills"
CODEX_HOME="${CODEX_HOME:-${HOME}/.codex}"
CODEX_SKILLS_DIR="${CODEX_HOME}/skills"

# Returns 0 if $1 is a symlink whose resolved target is inside $SKILLS_DIR.
is_our_link() {
    local link="$1"
    [ -L "$link" ] || return 1

    local target
    target="$(readlink "$link")"

    # Resolve relative symlinks relative to the link's parent directory.
    if [[ "$target" != /* ]]; then
        target="$(cd "$(dirname "$link")" && cd "$target" && pwd 2>/dev/null)" || return 1
    fi

    [[ "$target" == "${SKILLS_DIR}"/* || "$target" == "${SKILLS_DIR}" ]]
}

if [ ! -d "$SKILLS_DIR" ]; then
    echo "Skills directory not found: ${SKILLS_DIR}"
    exit 1
fi

echo "Removing skills symlinks from global directories"
echo ""

removed_count=0
skipped_count=0
found_skills=0

for skill_path in "${SKILLS_DIR}"/*/; do
    [ -d "$skill_path" ] || continue

    if [ ! -f "${skill_path}/SKILL.md" ]; then
        continue
    fi

    found_skills=1
    skill_name="$(basename "${skill_path%/}")"

    claude_link="${CLAUDE_SKILLS_DIR}/${skill_name}"
    if [ -L "$claude_link" ]; then
        if is_our_link "$claude_link"; then
            echo "  REMOVE: ~/.claude/skills/${skill_name}"
            rm "$claude_link"
            ((removed_count+=1))
        else
            echo "  SKIP (foreign link): ~/.claude/skills/${skill_name}"
            ((skipped_count+=1))
        fi
    fi

    codex_link="${CODEX_SKILLS_DIR}/${skill_name}"
    if [ -L "$codex_link" ]; then
        if is_our_link "$codex_link"; then
            echo "  REMOVE: ${CODEX_SKILLS_DIR/#$HOME/~}/${skill_name}"
            rm "$codex_link"
            ((removed_count+=1))
        else
            echo "  SKIP (foreign link): ${CODEX_SKILLS_DIR/#$HOME/~}/${skill_name}"
            ((skipped_count+=1))
        fi
    fi

    opencode_link="${OPENCODE_SKILLS_DIR}/${skill_name}"
    if [ -L "${opencode_link}.md" ]; then
        if is_our_link "${opencode_link}.md"; then
            echo "  REMOVE: ~/.config/opencode/skills/${skill_name}.md (legacy)"
            rm -f "${opencode_link}.md"
            ((removed_count+=1))
        else
            echo "  SKIP (foreign link): ~/.config/opencode/skills/${skill_name}.md"
            ((skipped_count+=1))
        fi
    fi
    if [ -L "$opencode_link" ]; then
        if is_our_link "$opencode_link"; then
            echo "  REMOVE: ~/.config/opencode/skills/${skill_name}"
            rm "$opencode_link"
            ((removed_count+=1))
        else
            echo "  SKIP (foreign link): ~/.config/opencode/skills/${skill_name}"
            ((skipped_count+=1))
        fi
    fi
done

if [ "$found_skills" -eq 0 ]; then
    echo "No skill directories with SKILL.md were found under .agents/."
    exit 0
fi

echo ""
if [ "$removed_count" -eq 0 ]; then
    echo "No symlinks found to remove."
else
    echo "Done! Removed ${removed_count} symlink(s)."
fi
if [ "$skipped_count" -gt 0 ]; then
    echo "Skipped ${skipped_count} foreign symlink(s)."
fi
echo ""
