#!/usr/bin/env python3
"""
Copy logs from Kubernetes pods into per-pod folders.

Examples:
  python3 download_logs.py --sources tiflash
  python3 download_logs.py --sources tikv
  python3 download_logs.py --sources tikv,tidb,tiflash
  python3 download_logs.py --sources pd
  python3 download_logs.py --sources tikv,pd
  python3 download_logs.py --sources scheduling,tso
  python3 download_logs.py --sources tikv --pod tc-tikv-0
  python3 download_logs.py --sources tikv --pod tc-tikv-0 --selected-files ./selected-files.txt
  python3 download_logs.py --single-file /var/lib/tikv/log/tikv.log --pod tc-tikv-0
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import sys

from tcms_logs_common import (
    AVAILABLE_SOURCES,
    LARGE_POD_LOG_THRESHOLD_BYTES,
    build_sources,
    format_size_gib,
    get_log_dir_size_bytes,
    list_log_files,
    list_pods,
    run,
)


def load_selected_files(selected_files_path):
    lines = []
    for raw in Path(selected_files_path).read_text(encoding="utf-8").splitlines():
        item = raw.strip()
        if not item or item.startswith("#"):
            continue
        lines.append(item)
    return lines


def resolve_selected_files(selected_entries, available_files, log_dir):
    available_set = set(available_files)
    resolved = []
    missing = []
    for entry in selected_entries:
        candidate_paths = [
            entry,
            f"{log_dir.rstrip('/')}/{entry}",
        ]
        matched = None
        for candidate in candidate_paths:
            if candidate in available_set:
                matched = candidate
                break
        if matched is None:
            missing.append(entry)
        else:
            resolved.append(matched)
    if missing:
        sample = ", ".join(missing[:5])
        raise RuntimeError(
            f"selected files not found in pod log dir ({len(missing)} missing), sample: {sample}"
        )
    # Keep stable order while removing duplicates.
    deduped = list(dict.fromkeys(resolved))
    return deduped


def copy_file_from_pod_exec(pod_name, remote_path, local_path, container=None):
    # kubectl cp treats ':' as a separator and fails on filenames containing it.
    # Stream the file via exec/cat instead for those cases (e.g. tiflash log names).
    cmd = ["kubectl", "exec", pod_name]
    if container:
        cmd += ["-c", container]
    cmd += ["--", "cat", remote_path]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    assert proc.stderr is not None
    with open(local_path, "wb") as handle:
        shutil.copyfileobj(proc.stdout, handle)
    proc.stdout.close()
    stderr = proc.stderr.read()
    returncode = proc.wait()
    if returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\\n{stderr.decode().strip()}"
        )


def copy_file_from_pod(pod_name, remote_path, local_path, container=None, use_exec=False):
    # Force exec-based copy when requested or when filenames include ':'.
    if use_exec or ":" in remote_path:
        copy_file_from_pod_exec(pod_name, remote_path, local_path, container=container)
        return
    cmd = ["kubectl", "cp"]
    if container:
        cmd += ["-c", container]
    cmd += [f"{pod_name}:{remote_path}", str(local_path)]
    run(cmd)


def copy_log_dir_from_pod(
    pod_name,
    log_dir,
    dest_dir,
    container=None,
    use_exec=False,
    files=None,
):
    files = list(files) if files is not None else list_log_files(pod_name, log_dir, container)
    if not files:
        print(f"no log files found in {log_dir} for {pod_name}")
        return 0
    total = len(files)
    for idx, file_path in enumerate(files, start=1):
        rel_path = Path(file_path).relative_to(log_dir)
        target_dir = dest_dir / rel_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / rel_path.name
        print(
            f"[{idx}/{total}] copying {file_path} -> {target_file}",
            flush=True,
        )
        copy_file_from_pod(
            pod_name, file_path, target_file, container=container, use_exec=use_exec
        )
    return total


def copy_single_file_from_pod(
    pod_name, remote_path, dest_dir, container=None, dest_name=None, use_exec=False
):
    dest_name = dest_name or Path(remote_path).name
    dest_path = dest_dir / dest_name
    copy_file_from_pod(
        pod_name, remote_path, dest_path, container=container, use_exec=use_exec
    )
    return dest_path


def process_source(
    source,
    pod_names_all,
    base_dir,
    target_pod=None,
    threshold_bytes=LARGE_POD_LOG_THRESHOLD_BYTES,
    selected_files_entries=None,
    allow_large_download=False,
):
    pods = [name for name in pod_names_all if source.pod_predicate(name)]
    if target_pod:
        pods = [name for name in pods if name == target_pod]
    if not pods:
        if target_pod:
            print(f"no {source.name} pods found matching {target_pod}")
        else:
            print(f"no {source.name} pods found")
        return False

    blocked_by_threshold = False
    for pod_name in pods:
        dest_dir = base_dir / pod_name
        dest_dir.mkdir(parents=True, exist_ok=True)
        if source.log_dir:
            files_to_copy = None
            if selected_files_entries is not None:
                available_files = list_log_files(pod_name, source.log_dir, source.container)
                files_to_copy = resolve_selected_files(
                    selected_files_entries,
                    available_files,
                    source.log_dir,
                )
                print(f"selected {len(files_to_copy)} file(s) from --selected-files")
            else:
                log_dir_size = get_log_dir_size_bytes(pod_name, source.log_dir, source.container)
                if (
                    log_dir_size is not None
                    and log_dir_size > threshold_bytes
                    and not allow_large_download
                ):
                    print(
                        f"large log set detected for {pod_name} "
                        f"({format_size_gib(log_dir_size)}) in {source.log_dir}; "
                        "download is blocked by threshold guardrail"
                    )
                    print(
                        "next: run inspect_logs.py to get file list, confirm desired "
                        "time range with user, and rerun with --selected-files <path>; "
                        "or use --allow-large-download to force full download"
                    )
                    blocked_by_threshold = True
                    continue
                files_to_copy = list_log_files(pod_name, source.log_dir, source.container)

            count = copy_log_dir_from_pod(
                pod_name,
                source.log_dir,
                dest_dir,
                container=source.container,
                use_exec=source.use_exec_copy,
                files=files_to_copy,
            )
            if count:
                print(f"copied {count} log file(s) from {pod_name} -> {dest_dir}")
        if source.single_file:
            dest_path = copy_single_file_from_pod(
                pod_name,
                source.single_file,
                dest_dir,
                container=source.container,
                dest_name=source.dest_name,
                use_exec=source.use_exec_copy,
            )
            print(f"copied {source.single_file} from {pod_name} -> {dest_path}")
    return blocked_by_threshold


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-s",
        "--sources",
        help=(
            "Comma-separated list of sources to download: "
            "tikv,tidb,tiflash,s3clean,pd,scheduling,tso"
        ),
    )
    parser.add_argument(
        "--pod",
        help="Only download logs from this exact pod name.",
    )
    parser.add_argument(
        "--single-file",
        help=(
            "Copy one remote file path from --pod into ./<pod>/; "
            "when set, --sources must be omitted"
        ),
    )
    parser.add_argument(
        "--container",
        help="Container name used with --single-file mode.",
    )
    parser.add_argument(
        "--dest-name",
        help="Optional local file name in --single-file mode.",
    )
    parser.add_argument(
        "--selected-files",
        help=(
            "Path to a text file containing selected remote files to download "
            "(one entry per line, supports full path or basename). "
            "Requires exactly one source and --pod."
        ),
    )
    parser.add_argument(
        "--allow-large-download",
        action="store_true",
        help="Allow full download even when size exceeds threshold.",
    )
    parser.add_argument(
        "--threshold-bytes",
        type=int,
        default=LARGE_POD_LOG_THRESHOLD_BYTES,
        help="Large log threshold in bytes (default: 3221225472).",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if bool(args.sources) == bool(args.single_file):
        print(
            "exactly one of --sources or --single-file must be specified",
            file=sys.stderr,
        )
        return 2
    if args.single_file is None and (args.container or args.dest_name):
        print("--container/--dest-name require --single-file", file=sys.stderr)
        return 2
    if args.single_file and not args.pod:
        print("--single-file requires --pod", file=sys.stderr)
        return 2
    if args.single_file and (args.selected_files or args.allow_large_download):
        print(
            "--selected-files/--allow-large-download are only for --sources mode",
            file=sys.stderr,
        )
        return 2
    if args.threshold_bytes <= 0:
        print("--threshold-bytes must be > 0", file=sys.stderr)
        return 2

    try:
        pod_names_all = list_pods()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.pod and args.pod not in pod_names_all:
        print(f"pod not found: {args.pod}", file=sys.stderr)
        return 2

    base_dir = Path.cwd()
    if args.single_file:
        try:
            dest_dir = base_dir / args.pod
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest_path = copy_single_file_from_pod(
                args.pod,
                args.single_file,
                dest_dir,
                container=args.container,
                dest_name=args.dest_name,
            )
            print(f"copied {args.single_file} from {args.pod} -> {dest_path}")
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    selected_sources = {name.strip() for name in args.sources.split(",") if name.strip()}
    unknown_sources = sorted(selected_sources.difference(AVAILABLE_SOURCES))
    if unknown_sources:
        print(f"unknown sources: {', '.join(unknown_sources)}", file=sys.stderr)
        return 2
    if not selected_sources:
        print("no sources selected", file=sys.stderr)
        return 2
    if args.selected_files and (not args.pod or len(selected_sources) != 1):
        print("--selected-files requires exactly one source and --pod", file=sys.stderr)
        return 2

    sources = build_sources()

    selected_files_entries = None
    if args.selected_files:
        try:
            selected_files_entries = load_selected_files(args.selected_files)
        except OSError as exc:
            print(f"failed to read --selected-files: {exc}", file=sys.stderr)
            return 2
        if not selected_files_entries:
            print("--selected-files contains no entries", file=sys.stderr)
            return 2

    blocked_by_threshold = False
    try:
        for source in sources:
            if source.name in selected_sources:
                blocked = process_source(
                    source,
                    pod_names_all,
                    base_dir,
                    target_pod=args.pod,
                    threshold_bytes=args.threshold_bytes,
                    selected_files_entries=selected_files_entries,
                    allow_large_download=args.allow_large_download,
                )
                blocked_by_threshold = blocked_by_threshold or blocked
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if blocked_by_threshold:
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
