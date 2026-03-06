# tidb-debug

`tidb-debug` is a repository for documenting and reusing TiDB/TiKV/TiFlash debugging workflows. The current content mainly consists of reusable Codex skills and helper scripts.

## Repository Layout

- `.agents/tcms-download-logs/`
  - A skill and scripts for downloading component logs from TCMS/Kubernetes clusters.
- `.agents/tcms-env/`
  - A skill for parsing `.env` / `kubeconfig.yml`, extracting DSNs, building TCMS URLs, and checking cluster health.

## How To Use These Skills

1. Trigger a skill by name in a Codex session (for example: `tcms-download-logs`).
2. Follow the workflow in the corresponding `SKILL.md`.
3. Keep investigation notes and conclusions in your current debugging directory.

## Skill Installation Guide (Codex)

The following commands use the built-in `skill-installer`:

```bash
CODEX_HOME="${CODEX_HOME:-$HOME/.codex}"
SKILL_INSTALLER="$CODEX_HOME/skills/.system/skill-installer/scripts"
```

1. List installable curated skills:

```bash
python3 "$SKILL_INSTALLER/list-skills.py"
```

2. Install from any GitHub repository path (example):

```bash
python3 "$SKILL_INSTALLER/install-skill-from-github.py" \
  --url https://github.com/<owner>/<repo>/tree/<ref>/<path-to-skill>
```

Notes:
- The default install destination is `$CODEX_HOME/skills/<skill-name>` (usually `~/.codex/skills/<skill-name>` if `CODEX_HOME` is not set).
- Restart Codex after installation to load new skills.

## License

See [LICENSE](./LICENSE).
