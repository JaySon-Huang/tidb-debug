---
name: tidb-metrics-triage
description: Triage TiDB/TiKV/TiFlash incidents by locating high-signal Prometheus metrics quickly. Use when users ask which metrics to inspect first, how to read TiFlash proxy RSS or `raftstore-entry_cache` growth, how to judge `wait-index` and `ready` degradation, or whether data-disk I/O backpressure can support an `applied index` slowdown hypothesis.
---

# TiDB Metrics Triage

## Workflow
1. 先确认故障组件和实例映射，避免把 `tidb-server`、`tiflash`、`tiflash-proxy`、`node-exporter` 的指标混在一起看。
2. 打开 `references/key-metric-signals.md`，按“场景”挑最少的一组关键 metrics。
3. 先看同一时间窗口里的峰值和共振，再看是否需要补日志或代码。
4. 输出结构化结论：`命中 metrics`、`可以支撑什么判断`、`还缺什么证据`、`下一步排查动作`。

## Quick Navigation
- TiFlash proxy 内存暴涨：`tiflash_proxy_process_resident_memory_bytes`、`tiflash_proxy_tikv_server_mem_trace_sum{name="raftstore-entry_cache"}`
- `wait-index` / `ready` 恶化：`tiflash_raft_wait_index_duration_seconds_sum/count`、`tiflash_proxy_tikv_raftstore_raft_process_duration_secs_sum/count{type="ready"}`
- 数据盘映射：`node_disk_info`、`node_filesystem_size_bytes`、`node_filesystem_avail_bytes`
- 数据盘 I/O 背压：`node_disk_io_now`、`node_disk_*_bytes_total`、`node_disk_*_completed_total`、`node_disk_*_time_seconds_total`

## Safety Notes
- metrics 用于快速收敛方向，不等同于根因结论。
- 对 `sum/count` 型指标，优先看同一窗口的增量或速率，不要直接比较累计值本身。
- 磁盘高压最多只能先支撑“放大器”或“重要支撑项”，不能单凭它直接确认 `applied index` 推进慢的因果。
- 如果需要把 metrics 判断写成更强结论，补 `tidb-log-triage` 里的关键日志做交叉验证。
