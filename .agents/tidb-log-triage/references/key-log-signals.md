# Key Log Signals for TiDB Incident Triage

## Component Index
- 默认仍按“场景”查找；组件索引用于在组件边界明确时快速跳转。
- `tidb-server`：2、3、4、13
- `tikv`：1、7、12
- `tiflash`：5、6、8、9、10、12、13
- `tiflash-proxy`：1、7、9、10、11
- `pingcap/tidb` UT：14
- 跨组件关联最强的场景：3、9、12、13

## 1) TiKV/TiFlash-Proxy 磁盘即将写满
- 场景：节点可用空间快速下降，可能导致写入或 Raft 行为异常。
- 组件：`tikv`、`tiflash-proxy`
- 关键词：`disk usage Normal->AlmostFull`
- 示例日志：
```log
[WARN] [run.rs:1521] ["disk usage Normal->AlmostFull, available=2597175296,...,capacity=52521566208"]
[WARN] [run.rs:1521] ["disk usage AlmostFull->AlreadyFull, available=865656832,...,capacity=52521566208"]
```
- 解读要点：状态从 `Normal` 到 `AlmostFull/AlreadyFull` 表示磁盘水位已触发保护阈值。
- 下一步排查：对齐节点磁盘监控、热点表/region 写入、快照与 raft 日志增长来源。

## 2) TiDB Server 执行过关键 DDL
- 场景：排查“谁在什么时间执行了影响元数据的操作”。
- 组件：`tidb-server`
- 关键词：`CRUCIAL OPERATION`
- 示例日志：
```log
[INFO] [session.go:4157] ["CRUCIAL OPERATION"] ... [sql="drop table if exists test.t"] [user=root@%]
[INFO] [session.go:4157] ["CRUCIAL OPERATION"] ... [sql="create table test.t(c1 varchar(100), c2 varchar(100))"] [user=root@%]
[INFO] [session.go:4157] ["CRUCIAL OPERATION"] ... [sql="alter table test.t set tiflash replica 1"] [user=root@%]
```
- 解读要点：可直接定位 DDL SQL、用户、连接 ID、schemaVersion。
- 下一步排查：把 DDL 时间点与告警/慢查询/副本同步延迟做对齐。

## 3) TiDB Server 查询分发失败
- 场景：SQL 执行报错，怀疑调度或下游交互失败。
- 组件：`tidb-server`
- 关键词：`command dispatched failed`
- 示例日志：原始清单未附样例，建议按该关键词先全量筛选后再按连接 ID 聚合。
- 解读要点：通常是请求分发阶段失败信号，需看同时间段下游报错。
- 下一步排查：关联 TiKV/TiFlash 连接异常、超时和资源瓶颈日志。

## 4) DDL 被长事务 DML 阻塞
- 场景：DDL 长时间不结束，疑似被旧事务阻塞。
- 组件：`tidb-server`
- 关键词：`old running transaction block DDL`
- 示例日志：
```log
[INFO] [job_worker.go:831] ["run DDL job"] ... [jobID=594239] ...
[INFO] [session.go:4907] ["old running transaction block DDL"] ... [jobID=594239] ["connection ID"=1690356170]
[INFO] [conn.go:1152] ["read packet timeout, close this connection"] [conn=1690356170] ...
[INFO] [job_worker.go:423] ["finish DDL job"] ... [jobID=594239] ...
```
- 解读要点：`jobID` 可串联 DDL 生命周期；阻塞连接被关闭后 DDL 可能立即完成。
- 下一步排查：定位阻塞连接来源 SQL、事务持续时长、连接池/超时设置是否合理。

## 5) TiFlash 上长耗时或高 CPU 查询
- 场景：MPP 查询慢、高 CPU、局部算子耗时异常。
- 组件：`tiflash`
- 关键词：`MPPTaskStatistics`
- Loki 过滤表达式：
```text
Line contains regex match: \"execution_time_ns\":\d{11,}
```
- 示例日志（精简）：
```log
[INFO] [MPPTaskStatistics.cpp:139] ["{\"query_tso\":...,\"executors\":[{\"id\":\"ExchangeSender_55\",\"execution_time_ns\":11169887270},...],\"cpu_ru\":12040,...}"]
```
- 解读要点：`execution_time_ns` 达到 11 位数约等于 10s+；结合 executor 结构可定位慢算子。
- 下一步排查：按 `query_tso/local_query_id/task_id` 聚合同一查询，判断是扫描、聚合还是网络交换瓶颈。

## 6) TiFlash 日志中过滤 TopN 场景
- 场景：怀疑 TopN 导致性能问题，需快速收敛样本。
- 组件：`tiflash`
- 关键词：`MPPTaskStatistics` + `TopN`
- Loki 过滤表达式：
```text
|= `MPPTaskStatistics` |~ `TopN`
```
- 解读要点：用于从 MPP 执行统计中筛选包含 TopN 的任务日志。
- 下一步排查：配合慢日志和执行计划确认 TopN 下推、排序代价与数据分布。

## 7) TiKV/TiFlash-Proxy 重启后恢复 raft-log 耗时
- 场景：节点重启恢复慢，影响可用性与查询恢复。
- 组件：`tikv`、`tiflash-proxy`
- 关键词：`Recovering raft logs takes`
- 示例日志：
```log
[INFO] [run.rs:161] ["engine-store server is started"]
[INFO] [engine.rs:91] ["Recovering raft logs takes 74.360526691s"]
[INFO] [mod.rs:288] ["Storage started."]
```
- 解读要点：恢复耗时直接反映重启后进入可服务状态前的日志回放成本。
- 下一步排查：结合 raft-log 体量、磁盘性能、异常关机频次评估恢复窗口。

## 8) TiFlash Read Index 超时并触发 Remote Read
- 场景：Learner Read 超时导致回退远程读取，可能引发查询抖动。
- 组件：`tiflash`
- 关键词：`Batch read index`
- 示例日志：
```log
[INFO] [LearnerReadWorker.cpp:348] ["[Learner Read] Batch read index,... cost=10000ms,..."]
[INFO] [RemoteRequest.cpp:35] ["Start to build remote request for 1 regions ..."]
```
- 解读要点：`cost=10000ms` 是明显超时信号；随后 remote read 重试通常会放大时延。
- 下一步排查：关注 region 分布、目标 store 健康度、网络时延与 read-index 负载。

## 9) TiFlash learner read 超时、applied index 推进慢、proxy `entry_cache` 增长
- 场景：`wait-index` 飙高、`raftstore-entry_cache`/proxy RSS 快速上升，或 MPP 查询报 `Region unavailable`。
- 组件：`tiflash`、`tiflash-proxy`
- 第一优先关键词：
  - `handle ready`
  - `wait learner index timeout`
  - `Region unavailable`
  - `MPPTaskStatistics.cpp:139`
- 示例日志：
```log
[WARN] [apply.rs:737] ["[store 1186230783] handle ready 128705 committed entries"] [takes=117624]
[WARN] [ReadIndex.cpp:119] ["[region_id=1186346433] wait learner index timeout, prev_index=7744 curr_index=7744 to_wait=8478 state=0 elapsed_s=300.000 timeout_s=300.000"]
[ERROR] [MPPTask.cpp:647] ["task running meets error: ... Region unavailable, region_id=1186346433 wait_index=8478 applied_index=7744 ..."]
[INFO] [MPPTaskStatistics.cpp:139] ["{\"query_tso\":...,\"read_wait_index_start_timestamp\":1773318083765724000,\"read_wait_index_end_timestamp\":1773318090020155000,\"learner_read_time\":\"6284.469ms\",\"num_local_region\":40,...}"]
```
- 解读要点：
  - `apply.rs:737` 的 `"[store ...] handle ready ... committed entries"` 是 store 级 apply poller 日志，不是单个 region 的 apply 慢日志。
  - `ReadIndex.cpp:119` 的 `wait learner index timeout` 是“读在等 learner/applied index 推进”的直接证据。
  - `MPPTask.cpp:647` 常直接带出 `region_id`、`wait_index`、`applied_index`，适合按 region 聚合。
  - `MPPTaskStatistics.cpp:139` 里优先提取：`read_wait_index_start_timestamp`、`read_wait_index_end_timestamp`、`learner_read_time`、`await_time_ns`、`num_local_region`。
- 下一步排查：
  - 先按 `region_id` 聚合 timeout / `Region unavailable`。
  - 再对齐同时间段 `tiflash-proxy` 的 `raftstore-entry_cache`、proxy RSS 和磁盘 I/O。
  - 如果怀疑磁盘是原因，最多只能先写成“重要支撑项/放大器”，不要单凭磁盘高压就下根因结论。

## 10) TiFlash learner 侧 region churn / conf change / term 变化
- 场景：异常窗口里输入侧不平静，怀疑 peer 重建、conf change、merge 或 term 变化放大了 learner 侧压力。
- 组件：`tiflash`、`tiflash-proxy`
- 关键词：
  - `peer created again`
  - `peer created`
  - `conf change successfully`
  - `leave joint state successfully`
  - `execute CommitMerge`
  - `can't flush data, filter CompactLog`
  - `received a message with higher term`
  - `became follower at term`
- 示例日志：
```log
[INFO] [region.rs:88] [" 1186230783:1174966361 0, peer created again"] ...
[INFO] [apply.rs:2465] ["conf change successfully"] ... [region_id=1186132431]
[INFO] [apply.rs:2866] ["execute CommitMerge"] ... [region_id=1186346433]
[INFO] [raft.rs:1371] ["received a message with higher term from 1186365537"] ... [region_id=1186346433]
```
- 解读要点：
  - 这组日志本身通常不足以直接证明 root cause。
  - 但它们非常适合解释“为什么同一时间窗口里 learner 输入侧不平静”。
  - 选一个反复 timeout 的 region，把 `CommitMerge -> CompactLog -> higher term -> peer created -> timeout` 串成时间线，通常很有价值。
- 下一步排查：
  - 先找 timeout 最多的 `region_id`。
  - 再按这个 `region_id` 交叉搜上述关键词。
  - 对照 `handle ready` 和 `ReadIndex.cpp:119`，判断它是孤立问题还是窗口内的共性症状。

## 11) 排除 snapshot 主导时要补查的关键词
- 场景：怀疑 `wait-index` / apply 异常是 snapshot apply 洪峰造成的。
- 组件：`tiflash-proxy`
- 关键词：
  - `pre apply snapshot`
  - `post apply snapshot`
  - `replace apply snapshot`
- 解读要点：如果关键窗口里这些日志并不密集，就不要轻易把问题写成“snapshot 主导”。
- 下一步排查：把 snapshot 日志密度与 `handle ready`、`wait learner index timeout`、`Region unavailable` 的窗口做对齐。

## 12) TiKV 与 TiFlash 网络连接不稳定
- 场景：节点间 RPC 不稳定导致请求失败或重试增多。
- 组件：`tikv`、`tiflash`
- 关键词：`connection abort`（也可同时检索 `connection aborted`）
- 示例日志：
```log
[WARN] [raft_client.rs:585] ["connection aborted"] ... [message: "Connection timed out"] ...
[WARN] [raft_client.rs:910] ["connection abort"] ... [store_id=63] ...
```
- 解读要点：`UNAVAILABLE` + `Connection timed out` 是典型网络抖动或链路拥塞信号。
- 下一步排查：核对节点网络质量、跨机房链路、gRPC 连接数与队列积压。

## 13) TiDB-X Slow Log 识别在 TiFlash 执行的慢查询
- 场景：从 slow log 中筛选“真正跑在 TiFlash”的慢 SQL。
- 组件：`tidb-server`、`tiflash`
- 关键词：`Storage_from_mpp: true`
- 示例日志：按 slow log 字段过滤，不依赖组件日志关键字。
- 解读要点：该字段命中时，可优先沿 TiFlash/MPP 方向分析瓶颈。
- 下一步排查：与 `MPPTaskStatistics`、执行计划、资源组配额联合分析。

## 14) pingcap/tidb 仓库定位失败单测
- 场景：CI 或本地测试失败，需要快速定位失败用例和断言差异。
- 组件：`pingcap/tidb` UT
- 关键词：`--- FAIL`
- 示例日志：
```log
result.go:49: Error: Not equal: expected: "[4986]\n" actual: "[4998]\n"
--- FAIL: TestColumnTable (1.13s)
```
- 解读要点：`--- FAIL: <TestName>` 是锚点，向上回溯 `Error Trace` 可定位调用链。
- 下一步排查：结合最近代码变更和相关包测试，复现并缩小影响范围。
