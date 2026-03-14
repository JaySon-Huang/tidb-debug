---
name: tidb-log-triage
description: Triage TiDB/TiKV/TiFlash incidents by locating high-signal logs quickly. Use when users ask for key log patterns, Loki filters, or first-pass diagnosis clues for DDL, storage pressure, MPP slow queries, read-index timeout, network instability, and test failures.
---

# TiDB Log Triage

## Workflow
1. First confirm the failure symptom and component scope (`tidb-server` / `tikv` / `tiflash` / `tiflash-proxy` / `pingcap/tidb` unit tests).
2. Open `references/key-log-signals.md`. By default, find the relevant keywords by scenario; if the component boundary is clearer, start from the `Component Index` at the top.
3. Use keyword-based rough filtering first, then cross-check with the time window and upstream/downstream component logs.
4. Output a structured conclusion: `matched logs`, `possible meaning`, and `next investigation steps`.

## Quick Navigation
- DDL changes and blocking: `CRUCIAL OPERATION`, `old running transaction block DDL`
- Disk pressure and restart recovery: `disk usage Normal->AlmostFull`, `Recovering raft logs takes`
- TiFlash execution performance: `MPPTaskStatistics` (long runtime / TopN), `Storage_from_mpp: true`
- TiFlash learner read / apply anomalies: `handle ready`, `wait learner index timeout`, `Region unavailable`, `MPPTaskStatistics.cpp:139`
- TiFlash region-side disturbances: `peer created again`, `peer created`, `conf change successfully`
- Read Index and remote read: `Batch read index`
- Network instability: `connection abort`
- Query failures and test failures: `command dispatched failed`, `--- FAIL`

## Component Entry
- `tidb-server`: `CRUCIAL OPERATION`, `old running transaction block DDL`, `command dispatched failed`, `Storage_from_mpp: true`
- `tikv`: `disk usage Normal->AlmostFull`, `Recovering raft logs takes`, `connection abort`
- `tiflash`: `MPPTaskStatistics`, `Batch read index`, `wait learner index timeout`, `Region unavailable`, `Storage_from_mpp: true`
- `tiflash-proxy`: `disk usage Normal->AlmostFull`, `Recovering raft logs takes`, plus learner / region-side logs that must be aligned with TiFlash
- `pingcap/tidb` unit tests: `--- FAIL`
- Components are only an entry point, not the main organizing dimension; for cross-component issues, return to `references/key-log-signals.md` and connect the evidence by scenario.

## Safety Notes
- Log signals are for quick localization; they are not equivalent to a root-cause conclusion.
- Before drawing a conclusion, require at least one piece of corroborating evidence from the same period, such as upstream/downstream logs, SQL change logs, or resource metrics.
- If the logs are incomplete, fill in the time window, request source, and target component before making a judgment.
