# Key Metric Signals for TiDB Incident Triage

## 1) TiFlash proxy RSS 暴涨，先判断是不是 `raftstore-entry_cache`
- 场景：`tiflash-proxy` RSS 快速上升，怀疑内存驻留在 proxy 内部而不是 TiFlash 主进程。
- 第一优先 metrics：
  - `tiflash_proxy_process_resident_memory_bytes`
  - `tiflash_proxy_tikv_server_mem_trace_sum{name="raftstore-entry_cache"}`
- 解读要点：
  - 先用 `tiflash_proxy_process_resident_memory_bytes` 确认 RSS 暴涨主体就是 `tiflash-proxy`。
  - 如果 `raftstore-entry_cache` 和 proxy RSS 在同一时间带一起上升，且量级本身足够大，应优先沿 `raft entry` 驻留路径继续查。
  - 这能直接支撑“proxy 内存上涨与 `entry_cache` 强相关”，但还不能单独区分是 cache 本体涨了，还是已送给 apply 的 entry 迟迟未释放。
- 下一步排查：
  - 对齐 `wait-index`、`ready` 的同窗口变化。
  - 补 `apply.rs:737`、`ReadIndex.cpp:119`、`MPPTask.cpp:647` 等日志。
  - 不要直接把它写成“内存泄漏”；先写成“内存驻留量异常增加”。

## 2) `wait-index` 与 `ready` 同时变坏，优先怀疑 learner 侧消费变慢
- 场景：查询抖动、TiFlash learner read 变慢、proxy 内存同时抬升。
- 第一优先 metrics：
  - `tiflash_raft_wait_index_duration_seconds_sum{type="tmt_raft_wait_index_duration"}`
  - `tiflash_raft_wait_index_duration_seconds_count{type="tmt_raft_wait_index_duration"}`
  - `tiflash_proxy_tikv_raftstore_raft_process_duration_secs_sum{type="ready"}`
  - `tiflash_proxy_tikv_raftstore_raft_process_duration_secs_count{type="ready"}`
- 解读要点：
  - 用同一时间窗口的 `sum` 增量除以 `count` 增量，得到窗口平均耗时；不要直接拿累计值本身比较。
  - 如果 `wait-index` 和 `ready` 在同一异常时间带一起抬升，再叠加 `entry_cache` / proxy RSS 上升，更支持沿 `ready -> apply -> compact` 这一侧继续查。
  - 这能支撑“消费变慢或落后”，但还不能仅凭 metrics 直接写成某个单独 region 的根因。
- 下一步排查：
  - 查 `ReadIndex.cpp:119 wait learner index timeout`。
  - 查 `MPPTask.cpp:647 Region unavailable ... applied_index=...`。
  - 查 `apply.rs:737 [store ...] handle ready ... committed entries`。

## 3) 先确认异常数据盘是谁，不要把系统盘和数据盘混看
- 场景：想讨论磁盘压力，但还没搞清楚 `/data` 到底对应哪个 block device。
- 第一优先 metrics：
  - `node_disk_info`
  - `node_filesystem_size_bytes`
  - `node_filesystem_avail_bytes`
- 解读要点：
  - 先通过 `node_filesystem_*` 确认挂载点到 device 的映射，例如 `/data -> /dev/sdb1`。
  - 再通过 `node_disk_info` 看设备型号、总线、路径，避免把 SATA SSD 和 NVMe 混为一谈。
  - 只有先确认“哪个盘是数据盘”，后面的 `node_disk_*` 压力分析才有意义。
- 下一步排查：
  - 固定住数据盘 device 名称后，再看该 device 的 `io_now`、带宽、时延。
  - 如果存在多块数据盘，不要只盯着 `sda` 或根分区。

## 4) 数据盘 I/O 背压：重要支撑项，不是单独因果证据
- 场景：怀疑 `applied index` 推进慢、learner read 超时、ready/apply 变慢与磁盘背压有关。
- 第一优先 metrics：
  - `node_disk_io_now`
  - `node_disk_read_bytes_total`
  - `node_disk_written_bytes_total`
  - `node_disk_reads_completed_total`
  - `node_disk_writes_completed_total`
  - `node_disk_read_time_seconds_total`
  - `node_disk_write_time_seconds_total`
- 解读要点：
  - `node_disk_io_now` 直接反映当前排队深度，是最直观的背压信号。
  - `read/write_time_seconds_total` 对 `reads/writes_completed_total` 做同窗口增量相除，可估算平均读写时延。
  - 如果同一数据盘在异常窗口里同时出现高 `io_now`、持续毫秒级时延、高带宽，就可以把“磁盘 I/O 背压”写成重要支撑项。
  - 但单凭磁盘高压，不能直接写成“已经证明 `applied index` 推进慢就是磁盘导致的”。
- 下一步排查：
  - 必须与 `wait-index`、`ready`、`entry_cache`、proxy RSS 同时段对齐。
  - 再去日志里确认是否出现 `wait learner index timeout`、`Region unavailable`、大 batch `handle ready`。
  - 如果这些信号共振，才可以把磁盘背压写成“很可能的放大器”。

## 5) 写结构化结论时的推荐句式
- 可以直接写：
  - “`tiflash_proxy_tikv_server_mem_trace_sum{name="raftstore-entry_cache"}` 与 proxy RSS 在同一时间带一起上升，是当前最强的 proxy 内存解释信号。”
  - “`wait-index` 和 `ready` 的同窗口恶化，支撑继续沿 learner 侧消费变慢这条线查。”
  - “数据盘 I/O 背压可以作为 `applied index` 推进变慢的重要支撑项或放大器。”
- 不建议直接写：
  - “已经确认内存泄漏。”
  - “已经确认某个单独 region 就是根因。”
  - “只凭磁盘 util 高，就已经证明 `applied index` 推进慢是磁盘导致的。”

## 6) 典型输出结构
- 命中 metrics：
  - 列出 exact metric name 和实例。
- 当前能支撑的判断：
  - 明确写“支撑项”“高相关”“更值得继续查的主线”。
- 当前还不能确认的点：
  - 明确写缺少哪类日志、代码或 region 级证据。
- 下一步排查动作：
  - 指向 `tidb-log-triage` 里的具体关键词，或继续缩小到单个实例 / region / 磁盘。
