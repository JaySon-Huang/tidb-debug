#!/usr/bin/env python3
"""
Inspect Kubernetes pod logs to get total size, file list, and per-file size.

Examples:
  python3 inspect_logs.py --sources tikv --pod tc-tikv-0
  python3 inspect_logs.py --sources pd --pod tc-pd-0 --output ./pd0.inspect.json
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shlex
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


def run_allow_fail(cmd):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def list_log_files_with_sizes(pod_name, log_dir, container=None):
    cmd = ["kubectl", "exec", pod_name]
    if container:
        cmd += ["-c", container]
    quoted = shlex.quote(log_dir)
    cmd += ["--", "sh", "-c", f"find {quoted} -type f -printf '%p\\t%s\\n'"]
    result = run_allow_fail(cmd)
    if result.returncode == 0:
        items = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if "\t" not in line:
                continue
            path, size_str = line.rsplit("\t", 1)
            path = path.strip()
            size_bytes = None
            try:
                size_bytes = int(size_str.strip())
            except ValueError:
                size_bytes = None
            items.append(
                {
                    "path": path,
                    "filename": Path(path).name,
                    "size_bytes": size_bytes,
                }
            )
        return items

    files = list_log_files(pod_name, log_dir, container)
    return [
        {
            "path": path,
            "filename": Path(path).name,
            "size_bytes": get_single_file_size_bytes(pod_name, path, container),
        }
        for path in files
    ]


def list_single_file(pod_name, remote_path, container=None):
    cmd = ["kubectl", "exec", pod_name]
    if container:
        cmd += ["-c", container]
    quoted = shlex.quote(remote_path)
    cmd += ["--", "sh", "-c", f"if [ -f {quoted} ]; then echo {quoted}; fi"]
    output = run(cmd)
    return [line.strip() for line in output.splitlines() if line.strip()]


def get_single_file_size_bytes(pod_name, remote_path, container=None):
    base_cmd = ["kubectl", "exec", pod_name]
    if container:
        base_cmd += ["-c", container]

    stat_cmd = base_cmd + ["--", "stat", "-c", "%s", remote_path]
    result = run_allow_fail(stat_cmd)
    if result.returncode == 0:
        out = result.stdout.strip().splitlines()
        if out:
            try:
                return int(out[-1].strip())
            except ValueError:
                pass

    quoted = shlex.quote(remote_path)
    wc_cmd = base_cmd + ["--", "sh", "-c", f"wc -c < {quoted}"]
    result = run_allow_fail(wc_cmd)
    if result.returncode == 0:
        out = result.stdout.strip().splitlines()
        if out:
            try:
                return int(out[-1].strip().split()[0])
            except ValueError:
                pass
    return None


def default_inspect_output_path(base_dir, source_name, pod_name):
    return base_dir / f"log-inspect-{source_name}-{pod_name}.json"


def write_inspect_report(
    output_path,
    source_name,
    pod_name,
    target_path,
    mode,
    container,
    threshold_bytes,
    total_size_bytes,
    file_details,
):
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": source_name,
        "pod": pod_name,
        "mode": mode,
        "target_path": target_path,
        "container": container,
        "threshold_bytes": threshold_bytes,
        "total_size_bytes": total_size_bytes,
        "exceeds_threshold": (
            total_size_bytes is not None and total_size_bytes > threshold_bytes
        ),
        "file_count": len(file_details),
        "file_details": file_details,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload


def parse_args():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-s",
        "--sources",
        required=True,
        help=(
            "Exactly one source to inspect: "
            "tikv,tidb,tiflash,s3clean,pd,scheduling,tso"
        ),
    )
    parser.add_argument(
        "--pod",
        required=True,
        help="Inspect logs from this exact pod name.",
    )
    parser.add_argument(
        "--output",
        help="Inspect report output path (JSON).",
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
    selected_sources = {name.strip() for name in args.sources.split(",") if name.strip()}
    unknown_sources = sorted(selected_sources.difference(AVAILABLE_SOURCES))
    if unknown_sources:
        print(f"unknown sources: {', '.join(unknown_sources)}", file=sys.stderr)
        return 2
    if len(selected_sources) != 1:
        print("--sources must contain exactly one source", file=sys.stderr)
        return 2
    if args.threshold_bytes <= 0:
        print("--threshold-bytes must be > 0", file=sys.stderr)
        return 2

    try:
        pod_names_all = list_pods()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if args.pod not in pod_names_all:
        print(f"pod not found: {args.pod}", file=sys.stderr)
        return 2

    source_name = next(iter(selected_sources))
    source_map = {source.name: source for source in build_sources()}
    source = source_map[source_name]
    if not source.pod_predicate(args.pod):
        print(f"pod {args.pod} does not match source {source_name}", file=sys.stderr)
        return 2

    if source.log_dir:
        file_details = list_log_files_with_sizes(args.pod, source.log_dir, source.container)
        total_size_bytes = get_log_dir_size_bytes(args.pod, source.log_dir, source.container)
        if total_size_bytes is None:
            known_sizes = [item["size_bytes"] for item in file_details if item["size_bytes"] is not None]
            if len(known_sizes) == len(file_details):
                total_size_bytes = sum(known_sizes)
        mode = "log_dir"
        target_path = source.log_dir
    elif source.single_file:
        files = list_single_file(args.pod, source.single_file, source.container)
        size_bytes = get_single_file_size_bytes(args.pod, source.single_file, source.container)
        file_details = [
            {
                "path": path,
                "filename": Path(path).name,
                "size_bytes": size_bytes,
            }
            for path in files
        ]
        total_size_bytes = size_bytes
        mode = "single_file"
        target_path = source.single_file
    else:
        print(f"source {source_name} has no inspectable target", file=sys.stderr)
        return 2

    base_dir = Path.cwd()
    output_path = Path(args.output) if args.output else default_inspect_output_path(
        base_dir, source.name, args.pod
    )
    payload = write_inspect_report(
        output_path,
        source.name,
        args.pod,
        target_path,
        mode,
        source.container,
        args.threshold_bytes,
        total_size_bytes,
        file_details,
    )

    print(
        f"inspect report written: {output_path} "
        f"(size={format_size_gib(total_size_bytes)}, files={payload['file_count']}, "
        f"exceeds_threshold={payload['exceeds_threshold']})"
    )
    if payload["exceeds_threshold"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
