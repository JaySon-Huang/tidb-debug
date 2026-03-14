# Key Metric Signals for TiDB Incident Triage

## 1) If TiFlash proxy RSS surges, first determine whether `raftstore-entry_cache` is involved
- Scenario: `tiflash-proxy` RSS rises quickly, and you suspect the memory is resident inside the proxy rather than the TiFlash main process.
- Highest-priority metrics:
  - `tiflash_proxy_process_resident_memory_bytes`
  - `tiflash_proxy_tikv_server_mem_trace_sum{name="raftstore-entry_cache"}`
- Interpretation:
  - First use `tiflash_proxy_process_resident_memory_bytes` to confirm that the process with the RSS surge is indeed `tiflash-proxy`.
  - If `raftstore-entry_cache` and proxy RSS rise together in the same time window, and the magnitude is large enough, prioritize investigating the `raft entry` residency path.
  - This directly supports the statement that proxy memory growth is strongly correlated with `entry_cache`, but metrics alone still cannot distinguish whether the cache itself is growing or entries already handed to apply are not being released promptly.
- Next steps:
  - Align same-window changes in `wait-index` and `ready`.
  - Add logs such as `apply.rs:737`, `ReadIndex.cpp:119`, and `MPPTask.cpp:647`.
  - Do not write this up directly as a "memory leak"; start with "abnormal increase in memory residency".

## 2) If `wait-index` and `ready` deteriorate together, first suspect slower consumption on the learner side
- Scenario: query jitter appears, TiFlash learner reads slow down, and proxy memory rises at the same time.
- Highest-priority metrics:
  - `tiflash_raft_wait_index_duration_seconds_sum{type="tmt_raft_wait_index_duration"}`
  - `tiflash_raft_wait_index_duration_seconds_count{type="tmt_raft_wait_index_duration"}`
  - `tiflash_proxy_tikv_raftstore_raft_process_duration_secs_sum{type="ready"}`
  - `tiflash_proxy_tikv_raftstore_raft_process_duration_secs_count{type="ready"}`
- Interpretation:
  - Divide the same-window delta of `sum` by the delta of `count` to get window-average latency; do not compare the raw cumulative values directly.
  - If `wait-index` and `ready` rise together in the same anomalous window, and `entry_cache` / proxy RSS also increases, that more strongly supports continuing along the `ready -> apply -> compact` line of investigation.
  - This supports "consumption is slower or lagging", but metrics alone still cannot justify writing that a single region is the root cause.
- Next steps:
  - Check `ReadIndex.cpp:119 wait learner index timeout`.
  - Check `MPPTask.cpp:647 Region unavailable ... applied_index=...`.
  - Check `apply.rs:737 [store ...] handle ready ... committed entries`.

## 3) Identify the anomalous data disk first; do not mix system-disk and data-disk signals
- Scenario: you want to discuss disk pressure, but you have not yet confirmed which block device `/data` actually maps to.
- Highest-priority metrics:
  - `node_disk_info`
  - `node_filesystem_size_bytes`
  - `node_filesystem_avail_bytes`
- Interpretation:
  - First use `node_filesystem_*` to confirm the mount-point-to-device mapping, for example `/data -> /dev/sdb1`.
  - Then use `node_disk_info` to inspect device model, bus, and path so that SATA SSD and NVMe are not conflated.
  - Only after confirming which disk is the data disk does later `node_disk_*` pressure analysis become meaningful.
- Next steps:
  - After fixing the data-disk device name, inspect `io_now`, throughput, and latency for that device.
  - If multiple data disks exist, do not focus only on `sda` or the root partition.

## 4) Data-disk I/O backpressure: important supporting evidence, not standalone causal proof
- Scenario: you suspect slow `applied index` advancement, learner read timeouts, or slower ready/apply processing may be related to disk backpressure.
- Highest-priority metrics:
  - `node_disk_io_now`
  - `node_disk_read_bytes_total`
  - `node_disk_written_bytes_total`
  - `node_disk_reads_completed_total`
  - `node_disk_writes_completed_total`
  - `node_disk_read_time_seconds_total`
  - `node_disk_write_time_seconds_total`
- Interpretation:
  - `node_disk_io_now` directly reflects current queue depth and is the most intuitive backpressure signal.
  - Divide the same-window delta of `read/write_time_seconds_total` by the delta of `reads/writes_completed_total` to estimate average read/write latency.
  - If the same data disk shows high `io_now`, sustained millisecond-level latency, and high throughput in the anomalous window, you can write disk I/O backpressure as an important supporting factor.
  - But disk pressure alone still cannot prove that slow `applied index` advancement is caused by disk.
- Next steps:
  - Align it with `wait-index`, `ready`, `entry_cache`, and proxy RSS over the same period.
  - Then confirm in logs whether `wait learner index timeout`, `Region unavailable`, or large-batch `handle ready` appears.
  - Only when these signals move together should disk backpressure be described as a likely amplifier.

## 5) Recommended wording for structured conclusions
- You can write directly:
  - "`tiflash_proxy_tikv_server_mem_trace_sum{name=\"raftstore-entry_cache\"}` and proxy RSS rise together in the same time window; this is currently the strongest signal explaining proxy memory growth."
  - "`wait-index` and `ready` deteriorate in the same window, which supports continuing along the learner-side slow-consumption line of investigation."
  - "Data-disk I/O backpressure can be written as an important supporting factor or amplifier for slow `applied index` advancement."
- Avoid writing directly:
  - "Memory leak has been confirmed."
  - "A single region has been confirmed as the root cause."
  - "High disk util alone already proves that slow `applied index` advancement is caused by disk."

## 6) Typical output structure
- Matched metrics:
  - List the exact metric names and instances.
- What the current evidence supports:
  - Explicitly label supporting factors, strong correlation, or the main line that is most worth continuing to investigate.
- What is still unconfirmed:
  - Explicitly state what logs, code evidence, or region-level evidence are still missing.
- Next investigation steps:
  - Point to concrete keywords in `tidb-log-triage`, or continue narrowing to a single instance, region, or disk.
