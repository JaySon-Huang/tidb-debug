---
name: tidb-log-triage
description: Triage TiDB/TiKV/TiFlash incidents by locating high-signal logs quickly. Use when users ask for key log patterns, Loki filters, or first-pass diagnosis clues for DDL, storage pressure, MPP slow queries, read-index timeout, network instability, and test failures.
---

# TiDB Log Triage

## Workflow
1. 先确认故障现象和组件范围（`tidb-server` / `tikv` / `tiflash` / `tiflash-proxy` / `pingcap/tidb` UT）。
2. 打开 `references/key-log-signals.md`，默认按“场景”找到对应关键词；如果组件边界更清楚，就先看顶部的 `Component Index`。
3. 先用关键词粗筛，再结合时间窗口与上下游组件日志做交叉验证。
4. 输出结构化结论：`命中日志`、`可能含义`、`下一步排查动作`。

## Quick Navigation
- DDL 变更与阻塞：`CRUCIAL OPERATION`、`old running transaction block DDL`
- 磁盘与重启恢复：`disk usage Normal->AlmostFull`、`Recovering raft logs takes`
- TiFlash 执行性能：`MPPTaskStatistics`（长耗时/TopN）、`Storage_from_mpp: true`
- TiFlash learner read / apply 异常：`handle ready`、`wait learner index timeout`、`Region unavailable`、`MPPTaskStatistics.cpp:139`
- TiFlash region 侧扰动：`peer created again`、`peer created`、`conf change successfully`
- Read Index 与远程读：`Batch read index`
- 网络不稳定：`connection abort`
- 查询失败与测试失败：`command dispatched failed`、`--- FAIL`

## Component Entry
- `tidb-server`：`CRUCIAL OPERATION`、`old running transaction block DDL`、`command dispatched failed`、`Storage_from_mpp: true`
- `tikv`：`disk usage Normal->AlmostFull`、`Recovering raft logs takes`、`connection abort`
- `tiflash`：`MPPTaskStatistics`、`Batch read index`、`wait learner index timeout`、`Region unavailable`、`Storage_from_mpp: true`
- `tiflash-proxy`：`disk usage Normal->AlmostFull`、`Recovering raft logs takes`，以及需要和 TiFlash 对齐的 learner / region 侧日志
- `pingcap/tidb` UT：`--- FAIL`
- 组件只是入口，不是主组织维度；跨组件问题仍优先回到 `references/key-log-signals.md` 按场景串联证据。

## Safety Notes
- 日志信号用于快速定位，不等同于根因结论。
- 结论前需要至少一个“关联证据”（同时段上游/下游日志、SQL 变更日志或资源指标）。
- 如果日志不完整，优先补齐时间窗口、请求来源、目标组件后再下判断。
