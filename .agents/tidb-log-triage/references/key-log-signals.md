# Key Log Signals for TiDB Incident Triage

## Component Index
- Still default to looking up by scenario; the component index is for fast jumping when the component boundary is already clear.
- `tidb-server`: 2, 3, 4, 13
- `tikv`: 1, 7, 12
- `tiflash`: 5, 6, 8, 9, 10, 12, 13
- `tiflash-proxy`: 1, 7, 9, 10, 11
- `pingcap/tidb` unit tests: 14
- Scenarios with the strongest cross-component linkage: 3, 9, 12, 13

## 1) TiKV/TiFlash-Proxy disk is about to fill up
- Scenario: available space on the node is dropping quickly, which may lead to abnormal write or Raft behavior.
- Component: `tikv`, `tiflash-proxy`
- Keyword: `disk usage Normal->AlmostFull`
- Example logs:
```log
[WARN] [run.rs:1521] ["disk usage Normal->AlmostFull, available=2597175296,...,capacity=52521566208"]
[WARN] [run.rs:1521] ["disk usage AlmostFull->AlreadyFull, available=865656832,...,capacity=52521566208"]
```
- Interpretation: a state transition from `Normal` to `AlmostFull/AlreadyFull` means the disk waterline has crossed protection thresholds.
- Next steps: align with node disk monitoring, writes to hot tables/regions, and the sources of snapshot and raft-log growth.

## 2) A key DDL was executed on TiDB Server
- Scenario: investigate who executed a metadata-affecting operation and when.
- Component: `tidb-server`
- Keyword: `CRUCIAL OPERATION`
- Example logs:
```log
[INFO] [session.go:4157] ["CRUCIAL OPERATION"] ... [sql="drop table if exists test.t"] [user=root@%]
[INFO] [session.go:4157] ["CRUCIAL OPERATION"] ... [sql="create table test.t(c1 varchar(100), c2 varchar(100))"] [user=root@%]
[INFO] [session.go:4157] ["CRUCIAL OPERATION"] ... [sql="alter table test.t set tiflash replica 1"] [user=root@%]
```
- Interpretation: this can directly locate the DDL SQL, user, connection ID, and schemaVersion.
- Next steps: align the DDL timestamp with alerts, slow queries, and replica synchronization delay.

## 3) TiDB Server query dispatch failed
- Scenario: SQL execution fails and you suspect scheduling or downstream interaction failure.
- Component: `tidb-server`
- Keyword: `command dispatched failed`
- Example logs: no sample was included in the original checklist. Start with a full search by this keyword, then aggregate by connection ID.
- Interpretation: this usually indicates failure during the request dispatch phase, so you need downstream errors from the same period.
- Next steps: correlate with TiKV/TiFlash connection anomalies, timeouts, and resource bottleneck logs.

## 4) DDL is blocked by a long-running DML transaction
- Scenario: a DDL does not finish for a long time and is suspected to be blocked by an old transaction.
- Component: `tidb-server`
- Keyword: `old running transaction block DDL`
- Example logs:
```log
[INFO] [job_worker.go:831] ["run DDL job"] ... [jobID=594239] ...
[INFO] [session.go:4907] ["old running transaction block DDL"] ... [jobID=594239] ["connection ID"=1690356170]
[INFO] [conn.go:1152] ["read packet timeout, close this connection"] [conn=1690356170] ...
[INFO] [job_worker.go:423] ["finish DDL job"] ... [jobID=594239] ...
```
- Interpretation: `jobID` can connect the DDL lifecycle end to end; once the blocking connection is closed, the DDL may finish immediately.
- Next steps: locate the SQL from the blocking connection, the transaction duration, and whether connection-pool / timeout settings are reasonable.

## 5) Long-running or high-CPU queries on TiFlash
- Scenario: MPP queries are slow, CPU is high, or some operators have abnormal runtime.
- Component: `tiflash`
- Keyword: `MPPTaskStatistics`
- Loki filter expression:
```text
Line contains regex match: \"execution_time_ns\":\d{11,}
```
- Example log (trimmed):
```log
[INFO] [MPPTaskStatistics.cpp:139] ["{\"query_tso\":...,\"executors\":[{\"id\":\"ExchangeSender_55\",\"execution_time_ns\":11169887270},...],\"cpu_ru\":12040,...}"]
```
- Interpretation: an 11-digit `execution_time_ns` is roughly 10s+; together with the executor structure, it can identify the slow operator.
- Next steps: aggregate the same query by `query_tso/local_query_id/task_id` and determine whether the bottleneck is scan, aggregation, or network exchange.

## 6) Filter TopN cases from TiFlash logs
- Scenario: you suspect TopN is causing performance problems and need to narrow samples quickly.
- Component: `tiflash`
- Keywords: `MPPTaskStatistics` + `TopN`
- Loki filter expression:
```text
|= `MPPTaskStatistics` |~ `TopN`
```
- Interpretation: use this to filter task logs containing TopN from MPP execution statistics.
- Next steps: combine with slow logs and execution plans to confirm TopN pushdown, sorting cost, and data distribution.

## 7) TiKV/TiFlash-Proxy spends a long time recovering raft logs after restart
- Scenario: node restart recovery is slow and affects availability and query recovery.
- Component: `tikv`, `tiflash-proxy`
- Keyword: `Recovering raft logs takes`
- Example logs:
```log
[INFO] [run.rs:161] ["engine-store server is started"]
[INFO] [engine.rs:91] ["Recovering raft logs takes 74.360526691s"]
[INFO] [mod.rs:288] ["Storage started."]
```
- Interpretation: the recovery time directly reflects the cost of log replay before the node becomes serviceable again after restart.
- Next steps: evaluate the recovery window together with raft-log volume, disk performance, and abnormal shutdown frequency.

## 8) TiFlash Read Index times out and triggers Remote Read
- Scenario: Learner Read times out and falls back to remote read, which may cause query jitter.
- Component: `tiflash`
- Keyword: `Batch read index`
- Example logs:
```log
[INFO] [LearnerReadWorker.cpp:348] ["[Learner Read] Batch read index,... cost=10000ms,..."]
[INFO] [RemoteRequest.cpp:35] ["Start to build remote request for 1 regions ..."]
```
- Interpretation: `cost=10000ms` is a clear timeout signal; the subsequent remote-read retry usually amplifies latency.
- Next steps: focus on region distribution, target store health, network latency, and read-index load.

## 9) TiFlash learner read times out, `applied index` advances slowly, and proxy `entry_cache` grows
- Scenario: `wait-index` spikes, `raftstore-entry_cache` / proxy RSS rises quickly, or MPP queries report `Region unavailable`.
- Component: `tiflash`, `tiflash-proxy`
- Highest-priority keywords:
  - `handle ready`
  - `wait learner index timeout`
  - `Region unavailable`
  - `MPPTaskStatistics.cpp:139`
- Example logs:
```log
[WARN] [apply.rs:737] ["[store 1186230783] handle ready 128705 committed entries"] [takes=117624]
[WARN] [ReadIndex.cpp:119] ["[region_id=1186346433] wait learner index timeout, prev_index=7744 curr_index=7744 to_wait=8478 state=0 elapsed_s=300.000 timeout_s=300.000"]
[ERROR] [MPPTask.cpp:647] ["task running meets error: ... Region unavailable, region_id=1186346433 wait_index=8478 applied_index=7744 ..."]
[INFO] [MPPTaskStatistics.cpp:139] ["{\"query_tso\":...,\"read_wait_index_start_timestamp\":1773318083765724000,\"read_wait_index_end_timestamp\":1773318090020155000,\"learner_read_time\":\"6284.469ms\",\"num_local_region\":40,...}"]
```
- Interpretation:
  - `"[store ...] handle ready ... committed entries"` from `apply.rs:737` is a store-level apply-poller log, not a slow-apply log for a single region.
  - `wait learner index timeout` from `ReadIndex.cpp:119` is direct evidence that a read is waiting for learner / applied index advancement.
  - `MPPTask.cpp:647` often includes `region_id`, `wait_index`, and `applied_index` directly, which makes it suitable for grouping by region.
  - From `MPPTaskStatistics.cpp:139`, prioritize extracting `read_wait_index_start_timestamp`, `read_wait_index_end_timestamp`, `learner_read_time`, `await_time_ns`, and `num_local_region`.
- Next steps:
  - First aggregate timeouts / `Region unavailable` by `region_id`.
  - Then align them with `raftstore-entry_cache`, proxy RSS, and disk I/O on `tiflash-proxy` over the same period.
  - If disk is suspected, at most write it first as an important supporting factor / amplifier; do not infer root cause from disk pressure alone.

## 10) Region churn / conf change / term changes on the TiFlash learner side
- Scenario: the input side is unstable in the anomalous window, and you suspect peer recreation, conf changes, merge, or term changes are amplifying learner-side pressure.
- Component: `tiflash`, `tiflash-proxy`
- Keywords:
  - `peer created again`
  - `peer created`
  - `conf change successfully`
  - `leave joint state successfully`
  - `execute CommitMerge`
  - `can't flush data, filter CompactLog`
  - `received a message with higher term`
  - `became follower at term`
- Example logs:
```log
[INFO] [region.rs:88] [" 1186230783:1174966361 0, peer created again"] ...
[INFO] [apply.rs:2465] ["conf change successfully"] ... [region_id=1186132431]
[INFO] [apply.rs:2866] ["execute CommitMerge"] ... [region_id=1186346433]
[INFO] [raft.rs:1371] ["received a message with higher term from 1186365537"] ... [region_id=1186346433]
```
- Interpretation:
  - This log set is usually not enough by itself to prove root cause directly.
  - But it is very useful for explaining why the learner-side input was unstable in the same time window.
  - Pick a region with repeated timeouts and build a timeline such as `CommitMerge -> CompactLog -> higher term -> peer created -> timeout`; that is often valuable.
- Next steps:
  - First find the `region_id` with the most timeouts.
  - Then cross-search the keywords above for that `region_id`.
  - Compare against `handle ready` and `ReadIndex.cpp:119` to determine whether it is an isolated issue or a common symptom in the window.

## 11) Keywords to add when ruling out snapshot-dominated behavior
- Scenario: you suspect `wait-index` / apply anomalies are caused by a burst of snapshot apply.
- Component: `tiflash-proxy`
- Keywords:
  - `pre apply snapshot`
  - `post apply snapshot`
  - `replace apply snapshot`
- Interpretation: if these logs are not dense in the critical window, do not casually describe the issue as "snapshot-dominated".
- Next steps: align snapshot log density with the windows of `handle ready`, `wait learner index timeout`, and `Region unavailable`.

## 12) Network connectivity between TiKV and TiFlash is unstable
- Scenario: unstable RPC between nodes causes request failures or increased retries.
- Component: `tikv`, `tiflash`
- Keyword: `connection abort` (you can also search `connection aborted` at the same time)
- Example logs:
```log
[WARN] [raft_client.rs:585] ["connection aborted"] ... [message: "Connection timed out"] ...
[WARN] [raft_client.rs:910] ["connection abort"] ... [store_id=63] ...
```
- Interpretation: `UNAVAILABLE` + `Connection timed out` is a typical signal of network jitter or link congestion.
- Next steps: verify node network quality, cross-AZ / cross-DC links, gRPC connection counts, and queue backlog.

## 13) Use TiDB-X Slow Log to identify slow queries executed on TiFlash
- Scenario: filter slow SQLs from the slow log that truly ran on TiFlash.
- Component: `tidb-server`, `tiflash`
- Keyword: `Storage_from_mpp: true`
- Example logs: filter by slow-log fields rather than by component log keywords.
- Interpretation: when this field is present, prioritize TiFlash / MPP as the bottleneck direction.
- Next steps: analyze together with `MPPTaskStatistics`, execution plans, and resource-group quota.

## 14) Locate failing unit tests in the `pingcap/tidb` repository
- Scenario: CI or local tests fail and you need to locate the failing test case and assertion difference quickly.
- Component: `pingcap/tidb` unit tests
- Keyword: `--- FAIL`
- Example logs:
```log
result.go:49: Error: Not equal: expected: "[4986]\n" actual: "[4998]\n"
--- FAIL: TestColumnTable (1.13s)
```
- Interpretation: `--- FAIL: <TestName>` is the anchor; tracing upward to `Error Trace` can locate the call chain.
- Next steps: combine with recent code changes and related package tests, reproduce, and narrow the impact scope.
