---
name: tcms-download-logs
description: Download tikv/tidb/tiflash/pd/scheduling/tso/s3clean logs from Kubernetes pods using scripts/download_logs.py, with required source filtering and per-pod output folders. Use when collecting logs for TCMS testbeds, usually in a TCMS-managed Kubernetes environment, including large-log cases where per-pod logs exceed 3GiB and time-range suffix filtering should be chosen.
---

# TCMS Download Logs

## Quick Start
- Ensure `kubectl` points to the target cluster.
- Usually run this in a TCMS-managed Kubernetes environment (for example, after loading `kubeconfig.yml` from a TCMS testbed).
- Run from the analysis directory so logs are saved there:
```
python3 /DATA/disk1/jaysonhuang/oh-my-agents/tcms-download-logs/scripts/download_logs.py --sources tiflash
```
- Choose exactly one mode:
  - source mode: `--sources <list>`
  - single-file mode: `--single-file <remote-path> --pod <pod-name>`
- Download specific sources:
```
python3 scripts/download_logs.py --sources tikv
python3 scripts/download_logs.py --sources tikv,tidb,tiflash
python3 scripts/download_logs.py --sources pd
python3 scripts/download_logs.py --sources scheduling,tso
```
- Download one source from one pod only:
```
python3 scripts/download_logs.py --sources tikv --pod tc-tikv-0
python3 scripts/download_logs.py --sources pd --pod tc-pd-0
```
- Inspect one source in one pod (size + file list + per-file size, no download):
```
python3 scripts/inspect_logs.py --sources tikv --pod tc-tikv-0
python3 scripts/inspect_logs.py --sources tikv --pod tc-tikv-0 --output ./tikv0.inspect.json
```
- Download selected files from one pod using the file list generated/decided by agent:
```
python3 scripts/download_logs.py --sources tikv --pod tc-tikv-0 --selected-files ./selected-files.txt
```
- Download one file from one pod:
```
python3 scripts/download_logs.py --single-file /var/lib/tikv/log/tikv.log --pod tc-tikv-0
python3 scripts/download_logs.py --single-file /var/lib/tidb/log/tidb.log --pod tc-tidb-0 --container tidb
python3 scripts/download_logs.py --single-file /var/lib/pd/log/pd.log --pod tc-pd-0 --container pd --dest-name pd-current.log
```
- Or specify sources directly from the analysis directory:
```
python3 /DATA/disk1/jaysonhuang/oh-my-agents/tcms-download-logs/scripts/download_logs.py --sources tiflash
python3 /DATA/disk1/jaysonhuang/oh-my-agents/tcms-download-logs/scripts/download_logs.py --sources tikv,tidb,pd
python3 /DATA/disk1/jaysonhuang/oh-my-agents/tcms-download-logs/scripts/download_logs.py --sources pd,scheduling,tso
```

## Outputs
- Logs are saved under `./<pod-name>/...` in the current working directory.
- tikv: `/var/lib/tikv/log`
- tidb: `/var/lib/tidb/log` (uses container `tidb`)
- tiflash: `/data0/logs` (uses container `serverlog`)
- pd: `/var/lib/pd/log` (uses container `pd`)
- scheduling: `/var/lib/pd/scheduling/scheduling.log` (container `scheduling`) -> `./<pod>/scheduling.log`
- tso: `/var/lib/pd/tso/tso.log` (container `tso`) -> `./<pod>/tso.log`
- s3clean: `/tmp/s3clean.log` -> `./<pod>/s3clean.log`

## Notes
- tiflash logs use `kubectl exec ... cat` because filenames can include `:` which breaks `kubectl cp`.
- `--sources` and `--single-file` are mutually exclusive.
- `--single-file` requires `--pod`.
- `--container` and `--dest-name` are used only in `--single-file` mode.
- Multi-file downloads print per-file progress in `[current/total]` format.
- `download_logs.py` is download-only.
- `inspect_logs.py` is inspect-only and writes inspect report JSON:
  - `file_details`: structured list with `path`, `filename`, `size_bytes`
- In `download_logs.py`, `--selected-files`, `--allow-large-download`, and `--threshold-bytes` are only for source mode.
- `--selected-files` requires exactly one source and `--pod`.
- If source-mode logs exceed the threshold, `download_logs.py` blocks full download and exits with code `3` unless `--selected-files` or `--allow-large-download` is provided.
- If source-mode logs exceed the 3GiB threshold, default behavior is:
  - Do not force full download.
  - First confirm the user's expected log time range through dialog.
  - Only use `--allow-large-download` when the user explicitly requests full logs.
- scheduling/tso log paths come from `/etc/pd/pd.toml` (`[log.file].filename`) in each pod.
- Large log sets can take time to copy; re-run safely if interrupted.

## Large Pod Guardrail Workflow
Use this 4-step workflow when one pod has many log files:

1. Check pod log size and record file list:
```
python3 scripts/inspect_logs.py --sources tikv --pod tc-tikv-0
```
This generates `./log-inspect-<source>-<pod>.json` by default (or `--output` path).

2. Compare with threshold:
- If not exceeding threshold: run normal download (step 4).
- If exceeding threshold (>3GiB): do not force full download; you must ask user for desired log time range through agent dialog first.

3. Decide files to download from the inspect report:
- Agent/user determines expected time range.
- Agent selects matching file names from step-1 inspect report (`file_details`).
- Save selected entries (full path or basename) to a text file, one per line.

4. Download with script:
```
python3 scripts/download_logs.py --sources tikv --pod tc-tikv-0 --selected-files ./selected-files.txt
```
If and only if user explicitly wants full logs despite threshold, use:
```
python3 scripts/download_logs.py --sources tikv --pod tc-tikv-0 --allow-large-download
```

## Extend To Other Pods
- Edit `scripts/tcms_logs_common.py`.
- Add a new `LogSource(...)` entry in `build_sources()`:
  - Set `pod_predicate` to match pod names.
  - Use `log_dir` for a log directory, or `single_file` for one file.
  - Set `container` if the pod requires a specific container.
  - Set `use_exec_copy=True` if `kubectl cp` fails or filenames include `:`.
- `AVAILABLE_SOURCES` is derived from `build_sources()`, no separate list update needed.

## Find Log Paths For New Pod Types
When adding a new source, locate the real log output path before coding:

1. Inspect pod startup command.
```
kubectl describe pod <pod-name>
```
Check the `Command`/`Args` section for the startup script path.

2. Open the startup script and find config file path.
```
kubectl exec <pod-name> -c <container> -- cat <startup-script-path>
```
Startup scripts usually pass a config file path (for example via `--config=...`).

3. Open the config file and find log output settings.
```
kubectl exec <pod-name> -c <container> -- cat <config-path>
```
Use the log path from config to decide whether to use:
- `log_dir` for a log directory, or
- `single_file` for an exact log file path.
