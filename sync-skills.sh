#!/bin/bash
# Sync tidb-debug skills to Claude/OpenCode/Codex global skill directories.
#
# Usage: ./sync-skills.sh
#
# Creates directory symlinks from skills stored under:
#   ./.agents/<name>/
#
# Target directories:
#   - ~/.claude/skills/<name>/ -> ./.agents/<name>/
#   - ~/.config/opencode/skills/<name>/ -> ./.agents/<name>/
#   - ${CODEX_HOME:-~/.codex}/skills/<name>/ -> ./.agents/<name>/

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

mkdir -p "$CLAUDE_SKILLS_DIR"
mkdir -p "$OPENCODE_SKILLS_DIR"
mkdir -p "$CODEX_SKILLS_DIR"

echo "Syncing skills from: ${SKILLS_DIR}"
echo ""

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
            echo "  UPDATE: ~/.claude/skills/${skill_name}"
            rm "$claude_link"
        else
            echo "  SKIP (foreign link): ~/.claude/skills/${skill_name}"
            continue
        fi
    elif [ -e "$claude_link" ]; then
        echo "  SKIP (not a symlink): ~/.claude/skills/${skill_name}"
        continue
    else
        echo "  CREATE: ~/.claude/skills/${skill_name}"
    fi
    ln -sf "${skill_path%/}" "$claude_link"

    codex_link="${CODEX_SKILLS_DIR}/${skill_name}"
    if [ -L "$codex_link" ]; then
        if is_our_link "$codex_link"; then
            echo "  UPDATE: ${CODEX_SKILLS_DIR/#$HOME/~}/${skill_name}"
            rm "$codex_link"
        else
            echo "  SKIP (foreign link): ${CODEX_SKILLS_DIR/#$HOME/~}/${skill_name}"
            continue
        fi
    elif [ -e "$codex_link" ]; then
        echo "  SKIP (not a symlink): ${CODEX_SKILLS_DIR/#$HOME/~}/${skill_name}"
        continue
    else
        echo "  CREATE: ${CODEX_SKILLS_DIR/#$HOME/~}/${skill_name}"
    fi
    ln -sf "${skill_path%/}" "$codex_link"

    opencode_link="${OPENCODE_SKILLS_DIR}/${skill_name}"
    if [ -L "${opencode_link}.md" ]; then
        if is_our_link "${opencode_link}.md"; then
            rm -f "${opencode_link}.md"
        fi
    fi
    if [ -L "$opencode_link" ]; then
        if is_our_link "$opencode_link"; then
            rm "$opencode_link"
        else
            echo "  SKIP (foreign link): ~/.config/opencode/skills/${skill_name}"
            continue
        fi
    elif [ -e "$opencode_link" ]; then
        echo "  SKIP (not a symlink): ~/.config/opencode/skills/${skill_name}"
        continue
    fi
    ln -sf "${skill_path%/}" "$opencode_link"
    echo "         ~/.config/opencode/skills/${skill_name}/"
done

if [ "$found_skills" -eq 0 ]; then
    echo "No skill directories with SKILL.md were found under .agents/."
    exit 0
fi

echo ""
echo "Done! Skills are now available globally."
echo ""
echo "Claude skills:   ~/.claude/skills/"
echo "OpenCode skills: ~/.config/opencode/skills/"
echo "Codex skills:    ${CODEX_SKILLS_DIR/#$HOME/~}/"
