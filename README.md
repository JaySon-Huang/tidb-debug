# tidb-debug

`tidb-debug` is a repository for documenting and reusing TiDB/TiKV/TiFlash debugging workflows. The current content mainly consists of reusable skills under `.agents/` and helper scripts for installing them into local agent toolchains.

## Repository Layout

- `.agents/`
  - Skill directories. Each installable skill lives at `.agents/<skill-name>/SKILL.md`.
- `.agents/tcms-env/`
  - A skill for parsing TCMS clusters' `.env` / `kubeconfig.yml` files, extracting DSNs, building TCMS URLs, and checking cluster health.
- `.agents/tcms-download-logs/`
  - A skill and scripts for downloading component logs from TCMS/Kubernetes clusters.
- `.agents/tidb-system-table-sql/`
  - A skill for querying TiDB system tables and cluster metadata with a troubleshooting-focused SQL cookbook.
- `.agents/tidb-log-triage/`
  - A skill for quickly triaging TiDB/TiKV/TiFlash incidents using high-signal log patterns and Loki filters.

## How To Use These Skills

1. Trigger a skill by name in a Codex session (for example: `tcms-download-logs`).
2. Follow the workflow in the corresponding `SKILL.md`.
3. Keep investigation notes and conclusions in your current debugging directory.

## Sync Skills Into Local Tooling

This repository includes helper scripts for symlinking every skill under `.agents/` into the standard global skill directories used by Claude, OpenCode, and Codex.

```bash
./sync-skills.sh
```

This creates links in:

- `~/.claude/skills/`
- `~/.config/opencode/skills/`
- `${CODEX_HOME:-~/.codex}/skills/`

To remove only the symlinks created by this repository:

```bash
./unsync-skills.sh
```

Notes:
- The scripts scan `.agents/*/SKILL.md`.
- Existing non-symlink entries are left untouched.
- Existing symlinks that do not point back into this repository are skipped.
- Restart Codex, Claude, or OpenCode after syncing if the new skills do not appear immediately.

## License

See [LICENSE](./LICENSE).
