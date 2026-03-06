"""Shared utilities and source definitions for TCMS log scripts."""

from dataclasses import dataclass
import json
import subprocess
from typing import Callable, Optional


TIKV_LOG_DIR = "/var/lib/tikv/log"
TIDB_LOG_DIR = "/var/lib/tidb/log"
TIFLASH_LOG_DIR = "/data0/logs"
PD_LOG_DIR = "/var/lib/pd/log"
SCHEDULING_LOG = "/var/lib/pd/scheduling/scheduling.log"
TSO_LOG = "/var/lib/pd/tso/tso.log"
S3CLEAN_LOG = "/tmp/s3clean.log"
LARGE_POD_LOG_THRESHOLD_BYTES = 3 * 1024 * 1024 * 1024


@dataclass
class LogSource:
    name: str
    pod_predicate: Callable[[str], bool]
    log_dir: Optional[str] = None
    single_file: Optional[str] = None
    container: Optional[str] = None
    dest_name: Optional[str] = None
    # Some logs need exec-based copy because kubectl cp can't handle ':' in filenames.
    use_exec_copy: bool = False


# To add new pod types, append a LogSource here.
def build_sources():
    return [
        LogSource(
            name="tikv",
            pod_predicate=lambda name: "tikv" in name and "tikv-worker" not in name,
            log_dir=TIKV_LOG_DIR,
        ),
        LogSource(
            name="tidb",
            pod_predicate=lambda name: "-tidb-" in name,
            log_dir=TIDB_LOG_DIR,
            container="tidb",
        ),
        LogSource(
            name="tiflash",
            pod_predicate=lambda name: "tiflash" in name and "tiflash-minio" not in name,
            log_dir=TIFLASH_LOG_DIR,
            container="serverlog",
            use_exec_copy=True,
        ),
        LogSource(
            name="pd",
            pod_predicate=lambda name: "-pd-" in name,
            log_dir=PD_LOG_DIR,
            container="pd",
        ),
        LogSource(
            name="scheduling",
            pod_predicate=lambda name: "scheduling" in name,
            container="scheduling",
            single_file=SCHEDULING_LOG,
            dest_name="scheduling.log",
        ),
        LogSource(
            name="tso",
            pod_predicate=lambda name: "tso" in name,
            container="tso",
            single_file=TSO_LOG,
            dest_name="tso.log",
        ),
        LogSource(
            name="s3clean",
            pod_predicate=lambda name: "s3clean" in name,
            single_file=S3CLEAN_LOG,
        ),
    ]


AVAILABLE_SOURCES = tuple(source.name for source in build_sources())


def run(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\\n{result.stderr.strip()}")
    return result.stdout


def format_size_gib(size_bytes):
    if size_bytes is None:
        return "unknown"
    return f"{size_bytes / (1024 ** 3):.2f} GiB"


def list_pods():
    pods_json = run(["kubectl", "get", "pods", "-o", "json"])
    data = json.loads(pods_json)
    return [item.get("metadata", {}).get("name", "") for item in data.get("items", [])]


def list_log_files(pod_name, log_dir, container=None):
    cmd = ["kubectl", "exec", pod_name]
    if container:
        cmd += ["-c", container]
    cmd += ["--", "find", log_dir, "-type", "f", "-print"]
    output = run(cmd)
    return [line.strip() for line in output.splitlines() if line.strip()]


def get_log_dir_size_bytes(pod_name, log_dir, container=None):
    base_cmd = ["kubectl", "exec", pod_name]
    if container:
        base_cmd += ["-c", container]

    attempts = [
        (["du", "-sb", log_dir], 1),
        (["du", "-sk", log_dir], 1024),
    ]
    for cmd_suffix, scale in attempts:
        try:
            output = run(base_cmd + ["--"] + cmd_suffix).strip()
        except RuntimeError:
            continue
        if not output:
            continue
        size_str = output.split()[0]
        try:
            return int(size_str) * scale
        except ValueError:
            continue
    return None
