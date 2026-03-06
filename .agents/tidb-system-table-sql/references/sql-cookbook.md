# TiDB System Table SQL Cookbook

## Table of Contents
- [Placeholder Conventions](#placeholder-conventions)
- [Region Peers Distribution](#region-peers-distribution)
- [Store Filtering](#store-filtering)
- [Table and Index ID Lookup](#table-and-index-id-lookup)
- [DDL Jobs](#ddl-jobs)
- [TiFlash Replica](#tiflash-replica)
- [Storage Usage](#storage-usage)
- [Task Progress](#task-progress)

## Placeholder Conventions
- `<database_name>`: target database/schema name.
- `<table_name>`: target table name.
- `<partition_name_pattern>`: partition pattern used with `LIKE`.
- `<table_id>`: table or partition ID.
- `<job_id>`: DDL job ID.
- `<task_id>`: DXF task ID.

## Region Peers Distribution

### Get the regions info list of a given table
```sql
SHOW TABLE `<database_name>`.`<table_name>` REGIONS;
```

### Peers distribution on TiFlash stores of given table / partition
```sql
-- non-partitioned table
select TABLE_ID, p.STORE_ID, ADDRESS, count(p.REGION_ID)
from
  information_schema.tikv_region_status r,
  information_schema.tikv_region_peers p,
  information_schema.tikv_store_status s
where
  r.db_name = '<database_name>' and r.table_name = '<table_name>'
  and r.region_id = p.region_id and p.store_id = s.store_id
  and json_extract(s.label, "$[0].value") = "tiflash"
group by TABLE_ID, p.STORE_ID, ADDRESS;
```

```sql
-- Partitioned table
select TABLE_ID, r.PARTITION_NAME, p.STORE_ID, ADDRESS, count(p.REGION_ID)
from
  information_schema.tikv_region_status r,
  information_schema.tikv_region_peers p,
  information_schema.tikv_store_status s
where
  r.db_name = '<database_name>' and r.table_name = '<table_name>' and r.PARTITION_NAME like '<partition_name_pattern>'
  and r.region_id = p.region_id and p.store_id = s.store_id
  and json_extract(s.label, "$[0].value") = "tiflash"
group by TABLE_ID, r.PARTITION_NAME, p.STORE_ID, ADDRESS
order by TABLE_ID, r.PARTITION_NAME, p.STORE_ID;
```

### Peers distribution on TiKV and TiFlash stores of given table / partition
```sql
-- Non-partitioned table
select TABLE_ID, p.STORE_ID, ADDRESS, count(p.REGION_ID),
  CASE WHEN JSON_CONTAINS(s.LABEL, JSON_OBJECT('key', 'engine', 'value', 'tiflash'))
       THEN 'tiflash' ELSE 'tikv'END AS store_type, s.LABEL
from
  information_schema.tikv_region_status r,
  information_schema.tikv_region_peers p,
  information_schema.tikv_store_status s
where r.db_name = '<database_name>' and r.table_name = '<table_name>'
  and r.region_id = p.region_id and p.store_id = s.store_id
group by TABLE_ID, p.STORE_ID, s.LABEL, ADDRESS;
-- example output
+----------+----------+-----------------+--------------------+------------+---------------------------------------------------+
| TABLE_ID | STORE_ID | ADDRESS         | count(p.REGION_ID) | store_type | LABEL                                             |
+----------+----------+-----------------+--------------------+------------+---------------------------------------------------+
| 241      | 1        | 10.2.12.79:7580 | 1026               | tikv       | [{"key": "host", "value": "tidb-host-machine-1"}] |
| 241      | 122      | 10.2.12.81:9580 | 584                | tiflash    | [{"key": "engine", "value": "tiflash"}]           |
+----------+----------+-----------------+--------------------+------------+---------------------------------------------------+
```

```sql
-- Partitioned table
select TABLE_ID, r.PARTITION_NAME, p.STORE_ID, ADDRESS, count(p.REGION_ID),
  CASE WHEN JSON_CONTAINS(s.LABEL, JSON_OBJECT('key', 'engine', 'value', 'tiflash'))
       THEN 'tiflash' ELSE 'tikv'END AS store_type, s.LABEL
from
  information_schema.tikv_region_status r,
  information_schema.tikv_region_peers p,
  information_schema.tikv_store_status s
where r.db_name = '<database_name>' and r.table_name = '<table_name>'
  and r.region_id = p.region_id and p.store_id = s.store_id
group by TABLE_ID, r.PARTITION_NAME, p.STORE_ID, s.LABEL, ADDRESS
order by TABLE_ID, r.PARTITION_NAME;
```

### Region peers and leader distribution on TiKV and TiFlash stores of given table / partition
```sql
select TABLE_ID, p.STORE_ID, p.IS_LEADER, ADDRESS, count(p.REGION_ID),
  CASE WHEN JSON_CONTAINS(s.LABEL, JSON_OBJECT('key', 'engine', 'value', 'tiflash'))
       THEN 'tiflash' ELSE 'tikv'END AS store_type, s.LABEL
from
  information_schema.tikv_region_status r,
  information_schema.tikv_region_peers p,
  information_schema.tikv_store_status s
where r.db_name = '<database_name>' and r.table_name = '<table_name>'
  and r.region_id = p.region_id and p.store_id = s.store_id
group by TABLE_ID, p.STORE_ID, p.IS_LEADER, s.LABEL, ADDRESS;
-- example output
+----------+----------+-----------+-----------------+--------------------+------------+---------------------------------------------------+
| TABLE_ID | STORE_ID | IS_LEADER | ADDRESS         | count(p.REGION_ID) | store_type | LABEL                                             |
+----------+----------+-----------+-----------------+--------------------+------------+---------------------------------------------------+
| 241      | 1        | 1         | 10.2.12.79:7580 | 1026               | tikv       | [{"key": "host", "value": "tidb-host-machine-1"}] |
| 241      | 122      | 0         | 10.2.12.81:9580 | 584                | tiflash    | [{"key": "engine", "value": "tiflash"}]           |
+----------+----------+-----------+-----------------+--------------------+------------+---------------------------------------------------+
```

```sql
-- Partitioned table
select TABLE_ID, r.PARTITION_NAME, p.STORE_ID, p.IS_LEADER, ADDRESS, count(p.REGION_ID),
  CASE WHEN JSON_CONTAINS(s.LABEL, JSON_OBJECT('key', 'engine', 'value', 'tiflash'))
       THEN 'tiflash' ELSE 'tikv'END AS store_type, s.LABEL
from
  information_schema.tikv_region_status r,
  information_schema.tikv_region_peers p,
  information_schema.tikv_store_status s
where r.db_name = '<database_name>' and r.table_name = '<table_name>'
  and r.region_id = p.region_id and p.store_id = s.store_id
group by TABLE_ID, r.PARTITION_NAME, p.STORE_ID, p.IS_LEADER, s.LABEL, ADDRESS
order by TABLE_ID, r.PARTITION_NAME, p.IS_LEADER;
-- example output
+----------+----------+-----------+-----------------+--------------------+------------+---------------------------------------------------+
| TABLE_ID | STORE_ID | IS_LEADER | ADDRESS         | count(p.REGION_ID) | store_type | LABEL                                             |
+----------+----------+-----------+-----------------+--------------------+------------+---------------------------------------------------+
| 241      | 1        | 1         | 10.2.12.79:7580 | 1026               | tikv       | [{"key": "host", "value": "tidb-host-machine-1"}] |
| 241      | 122      | 0         | 10.2.12.81:9580 | 584                | tiflash    | [{"key": "engine", "value": "tiflash"}]           |
+----------+----------+-----------+-----------------+--------------------+------------+---------------------------------------------------+
```

## Store Filtering

```sql
-- Under classic tidb arch
-- Only return tiflash nodes
SELECT * FROM information_schema.tikv_store_status
WHERE JSON_CONTAINS(LABEL, JSON_OBJECT('key', 'engine', 'value', 'tiflash'));

-- Under next-gen or tiflash compute and storage disagg arch
-- Only return tiflash-write nodes
SELECT * FROM information_schema.tikv_store_status
WHERE JSON_CONTAINS(LABEL, JSON_OBJECT('key', 'engine', 'value', 'tiflash'));
-- Only return tiflash-compute nodes
SELECT * FROM information_schema.tikv_store_status WHERE JSON_CONTAINS(LABEL, JSON_OBJECT('key', 'engine', 'value', 'tiflash_compute') );
```

## Table and Index ID Lookup

### Check the table_id by table_name and vice versa
```sql
-- check the table_id by table_name
select table_schema,table_name,tidb_table_id from information_schema.`tables`
where table_schema = '<database_name>' and table_name = '<table_name>'
union
select table_schema,table_name,tidb_partition_id from information_schema.`partitions`
where table_schema = '<database_name>' and table_name = '<table_name>'

-- check the table_name/partition_name by table_id
select table_schema,table_name,'' as partition_name,tidb_table_id from information_schema.`tables`
where tidb_table_id = <table_id>
union
select table_schema,table_name,partition_name,tidb_partition_id from information_schema.`partitions`
where tidb_partition_id = <table_id>
```

### Check the table_id, index_id by table_name
```sql
select
    t.table_schema, t.table_name, t.table_id, i.key_name, i.index_id, i.column_name
from (
    select table_schema,table_name,tidb_table_id as table_id from information_schema.`tables`
    where table_schema = '<database_name>' and table_name = '<table_name>'
    union
    select table_schema,table_name,tidb_partition_id as table_id from information_schema.`partitions`
    where table_schema = '<database_name>' and table_name = '<table_name>'
) t join (
    select table_schema, table_name, index_id, key_name, column_name  from information_schema.tidb_indexes
    where table_schema = '<database_name>' and table_name = '<table_name>'
) i on t.table_id is not NULL and t.table_schema = i.table_schema and t.table_name = i.table_name;
```

## DDL Jobs

### Check recent DDL jobs executed/paused in TiDB
```sql
-- View the 10 jobs in the current DDL job queue, including running and pending jobs (if any), and the last 10 jobs in the executed DDL job queue (if any).
ADMIN SHOW DDL JOBS;
-- To limit the number of rows shown, specify a number and a where condition
ADMIN SHOW DDL JOBS [NUM] [WHERE where_condition];
-- Cancel DDL job(s)
ADMIN CANCEL DDL JOBS <job_id> [, <job_id>] ...;
```

## TiFlash Replica

### Check TiFlash replica and progress
```sql
select * from information_schema.tiflash_replica
```

### TiFlash replica manipulate
```sql
-- Retain the SQL statement that lists which tables
-- in the current cluster have TIFlash replicas configured.
select CONCAT('ALTER TABLE `', TABLE_SCHEMA, '`.`', TABLE_NAME, '` SET TIFLASH REPLICA ', REPLICA_COUNT)
from information_schema.tiflash_replica;

-- Generate SQL to remove all TIFLASH replicas of the tables.
select CONCAT('ALTER TABLE `', TABLE_SCHEMA, '`.`', TABLE_NAME, '` SET TIFLASH REPLICA ', 0)
from information_schema.tiflash_replica;
```

## Storage Usage

### Top N tables that occupy the most TiFlash disk storage space
```sql
-- This sql can return the table_schema, table_name and partition_name
-- stable_disk_mb is the mainly disk storage usage
select
    t.tiflash_instance,
    t.table_id,
    round(t.total_stable_size / 1024 / 1024, 0) as stable_mb,
    round(t.total_stable_size_on_disk / 1024 / 1024, 0) as stable_disk_mb,
    coalesce(p.table_schema, pr.table_schema) as table_schema,
    coalesce(p.table_name, pr.table_name) as table_name,
    pr.partition_name
from
    information_schema.tiflash_tables t
    left join information_schema.tables p on t.table_id = p.tidb_table_id
    left join information_schema.partitions pr on t.table_id = pr.tidb_partition_id
order by
    stable_disk_mb desc
limit
    100;
```

or without the table_name, only return the table_id

```sql
select
    tiflash_instance,
    table_id,
    round(total_stable_size / 1024 / 1024, 0) as stable_mb,
    round(total_stable_size_on_disk / 1024 / 1024, 0) as stable_disk_mb,
    round(avg_stable_rows, 0) as avg_stable_rows,
    round(avg_stable_size / 1024 / 1024, 0) as avg_stable_mb,
    round(total_stable_size_on_disk / 1024.0 / 1024 / segment_count, 0) as avg_stable_disk_mb,
    segment_count,
    round(delta_index_size / 1024, 0) as delta_idx_kb,
    round(delta_cache_size / 1024, 0) as delta_cache_kb,
    total_delta_rows as delta_rows,
    round(total_delta_size / 1024 / 1024, 0) as delta_mb,
    delta_count
from
    information_schema.tiflash_tables
order by
    stable_disk_mb desc
limit
    100
```

### TiKV disk storage space estimation
Reference: https://docs.pingcap.com/tidb/stable/manage-cluster-faq/#how-do-i-estimate-the-size-of-a-table-in-tidb

```sql
SELECT
  db_name,
  table_name,
  ROUND(SUM(total_size / cnt), 2) Approximate_Size,
  ROUND(
    SUM(
      total_size / cnt / (
        SELECT
          ROUND(AVG(value), 2)
        FROM
          METRICS_SCHEMA.store_size_amplification
        WHERE
          value > 0
      )
    ),
    2
  ) Disk_Size
FROM
  (
    SELECT
      db_name,
      table_name,
      region_id,
      SUM(Approximate_Size) total_size,
      COUNT(*) cnt
    FROM
      information_schema.TIKV_REGION_STATUS
    WHERE
      db_name = '<database_name>'
      AND table_name IN ('<table_name>')
    GROUP BY
      db_name,
      table_name,
      region_id
  ) tabinfo
GROUP BY
  db_name,
  table_name;
```

When using the above statement, replace placeholders as needed:
- `<database_name>`: the database name.
- `<table_name>`: target table name.

## Task Progress

### TiDB DXF job status
```sql
SELECT keyspace,id,task_key,type,state,create_time,end_time,step,error FROM mysql.tidb_global_task;

SELECT id,task_key,step,state,create_time,end_time,error FROM mysql.tidb_background_subtask;

SELECT id,step,state,count(*) as cnt FROM mysql.tidb_background_subtask WHERE id=<task_id> GROUP BY id,step,state;
```

### TiCI import progress
```sql
SELECT job_id,status,count(*) AS cnt FROM tici.tici_import_jobs_task GROUP BY job_id,status;
```
