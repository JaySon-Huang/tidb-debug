# Key Log Signals for TiDB Incident Triage

## 1) TiKV/TiFlash-Proxy 磁盘即将写满
- 场景：节点可用空间快速下降，可能导致写入或 Raft 行为异常。
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
- 关键词：`command dispatched failed`
- 示例日志：原始清单未附样例，建议按该关键词先全量筛选后再按连接 ID 聚合。
- 解读要点：通常是请求分发阶段失败信号，需看同时间段下游报错。
- 下一步排查：关联 TiKV/TiFlash 连接异常、超时和资源瓶颈日志。

## 4) DDL 被长事务 DML 阻塞
- 场景：DDL 长时间不结束，疑似被旧事务阻塞。
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
- 关键词：`MPPTaskStatistics` + `TopN`
- Loki 过滤表达式：
```text
|= `MPPTaskStatistics` |~ `TopN`
```
- 解读要点：用于从 MPP 执行统计中筛选包含 TopN 的任务日志。
- 下一步排查：配合慢日志和执行计划确认 TopN 下推、排序代价与数据分布。

## 7) TiKV/TiFlash-Proxy 重启后恢复 raft-log 耗时
- 场景：节点重启恢复慢，影响可用性与查询恢复。
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
- 关键词：`Batch read index`
- 示例日志：
```log
[INFO] [LearnerReadWorker.cpp:348] ["[Learner Read] Batch read index,... cost=10000ms,..."]
[INFO] [RemoteRequest.cpp:35] ["Start to build remote request for 1 regions ..."]
```
- 解读要点：`cost=10000ms` 是明显超时信号；随后 remote read 重试通常会放大时延。
- 下一步排查：关注 region 分布、目标 store 健康度、网络时延与 read-index 负载。

## 9) TiKV 与 TiFlash 网络连接不稳定
- 场景：节点间 RPC 不稳定导致请求失败或重试增多。
- 关键词：`connection abort`（也可同时检索 `connection aborted`）
- 示例日志：
```log
[WARN] [raft_client.rs:585] ["connection aborted"] ... [message: "Connection timed out"] ...
[WARN] [raft_client.rs:910] ["connection abort"] ... [store_id=63] ...
```
- 解读要点：`UNAVAILABLE` + `Connection timed out` 是典型网络抖动或链路拥塞信号。
- 下一步排查：核对节点网络质量、跨机房链路、gRPC 连接数与队列积压。

## 10) TiDB-X Slow Log 识别在 TiFlash 执行的慢查询
- 场景：从 slow log 中筛选“真正跑在 TiFlash”的慢 SQL。
- 关键词：`Storage_from_mpp: true`
- 示例日志：按 slow log 字段过滤，不依赖组件日志关键字。
- 解读要点：该字段命中时，可优先沿 TiFlash/MPP 方向分析瓶颈。
- 下一步排查：与 `MPPTaskStatistics`、执行计划、资源组配额联合分析。

## 11) pingcap/tidb 仓库定位失败单测
- 场景：CI 或本地测试失败，需要快速定位失败用例和断言差异。
- 关键词：`--- FAIL`
- 示例日志：
```log
result.go:49: Error: Not equal: expected: "[4986]\n" actual: "[4998]\n"
--- FAIL: TestColumnTable (1.13s)
```
- 解读要点：`--- FAIL: <TestName>` 是锚点，向上回溯 `Error Trace` 可定位调用链。
- 下一步排查：结合最近代码变更和相关包测试，复现并缩小影响范围。
