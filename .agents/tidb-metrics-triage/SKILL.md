---
name: tidb-metrics-triage
description: Triage TiDB/TiKV/TiFlash incidents by locating high-signal Prometheus metrics quickly. Use when users ask which metrics to inspect first, how to read TiFlash proxy RSS or `raftstore-entry_cache` growth, how to judge `wait-index` and `ready` degradation, or whether data-disk I/O backpressure can support an `applied index` slowdown hypothesis.
---

# TiDB Metrics Triage

## Workflow
1. First confirm the failing component and instance mapping so you do not mix metrics from `tidb-server`, `tiflash`, `tiflash-proxy`, and `node-exporter`.
2. Open `references/key-metric-signals.md` and choose the smallest high-signal metric set for the current scenario.
3. Check peaks and co-movement within the same time window first, then decide whether logs or code-level evidence need to be added.
4. Output a structured conclusion: `matched metrics`, `what they support`, `what evidence is still missing`, and `next investigation steps`.

## Quick Navigation
- TiFlash proxy RSS surge: `tiflash_proxy_process_resident_memory_bytes`, `tiflash_proxy_tikv_server_mem_trace_sum{name="raftstore-entry_cache"}`
- `wait-index` / `ready` degradation: `tiflash_raft_wait_index_duration_seconds_sum/count`, `tiflash_proxy_tikv_raftstore_raft_process_duration_secs_sum/count{type="ready"}`
- Data-disk mapping: `node_disk_info`, `node_filesystem_size_bytes`, `node_filesystem_avail_bytes`
- Data-disk I/O backpressure: `node_disk_io_now`, `node_disk_*_bytes_total`, `node_disk_*_completed_total`, `node_disk_*_time_seconds_total`

## Safety Notes
- Metrics are for quickly narrowing the direction; they are not equivalent to a root-cause conclusion.
- For `sum/count` metrics, prefer increments or rates within the same window rather than comparing the raw cumulative values.
- Disk pressure can at most support an "amplifier" or "important supporting factor" interpretation; by itself it cannot prove causality for slow `applied index` advancement.
- If you need to write a stronger conclusion from metrics, cross-check against the key logs in `tidb-log-triage`.
