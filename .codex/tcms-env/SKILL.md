---
name: tcms-env
description: Validate and parse tcctl testbed artifacts in a working directory. Use when `.env` and `kubeconfig.yml` should be checked, when `KUBECONFIG` needs to be set, when cluster pod health should be checked for abnormal states (for example `CrashLoopBackOff`), when TESTBED name and TiDB/MySQL DSN values must be extracted, when DSNs must be converted to `mycli`/`mysql` commands, when a TCMS execution URL should be generated from the testbed plan id, or when component versions should be queried from `information_schema.cluster_info`.
---

# TCMS Env

## Workflow

1. Verify required files in current working directory.
2. Ensure `KUBECONFIG` is usable for the target cluster.
3. Check pods in current namespace and identify abnormal pod states.
4. Parse `.env` for TESTBED, DSNs, and proxy hints.
5. Convert DSN strings to `mycli`/`mysql` commands.
6. Build TCMS URL from TESTBED plan id.
7. Query component versions from `information_schema.cluster_info` when a parsed DSN is reachable.

## Step 1: Validate Required Inputs

Run:

```bash
ls -la .env kubeconfig.yml
```

If either file is missing, ask the user to provide/regenerate them with:

```bash
tcctl testbed get -p <plan-execution-id>
```

Do not continue parsing until `.env` exists.

## Step 2: Ensure Kube Context

If `KUBECONFIG` is empty, set it:

```bash
export KUBECONFIG=kubeconfig.yml
```

Then verify access as needed (for example `kubectl get pods`).

## Step 3: Check Pod Health

After loading `KUBECONFIG`, inspect pod status:

```bash
kubectl get pods
```

Filter likely abnormal states (for example `CrashLoopBackOff`):

```bash
kubectl get pods --no-headers | awk '$4 ~ /(CrashLoopBackOff|Error|ImagePullBackOff|ErrImagePull|CreateContainerConfigError|CreateContainerError|RunContainerError|ContainerStatusUnknown|OOMKilled|Pending)/'
```

If the filtered command returns no rows, no obvious abnormal pod status is currently visible.

If `kubectl get pods` fails due to RBAC or connectivity, report the exact error and continue with `.env` parsing.

## Step 4: Parse `.env`

Extract TESTBED name:

```bash
sed -nE 's/^TESTBED:[[:space:]]*//p' .env | head -n1
```

Extract TiDB/MySQL DSNs (inside `TI_PARAM_RES_*` JSON payloads):

```bash
rg -o '[A-Za-z0-9_]+:[^@" ]*@tcp\([^)]+\)/[^" ]*' .env | sort -u
```

Optional proxy hint:

```bash
sed -nE 's/^MYSQL_PROXY:[[:space:]]*//p' .env | head -n1
```

## Step 5: Convert DSN to `mycli`/`mysql`

Use this mapping for each DSN:

- Input DSN: `<user>:<pass>@tcp(<host>:<port>)/<db>`
- Output command: `mycli -h <host> -P <port> -u <user> --password '<pass>' [<db>]`
- Optional fallback command: `mysql -h <host> -P <port> -u <user> -p'<pass>' [-D <db>]`

If `<db>` is empty, omit it from the end of the command.

## Step 6: Build TCMS URL from TESTBED

Plan execution id is embedded in TESTBED name, usually in `-tps-<plan-execution-id>-`.

Example:

- TESTBED: `endless-htap-consistency-tps-8079852-1-377`
- Plan execution id: `8079852`
- URL: `https://tcms.pingcap.net/dashboard/executions/plan/8079852`

Fallback rule: if `-tps-<plan-execution-id>-` is not found, use the first 6+ digit number from TESTBED as plan execution id.

## Step 7: Component Version Query

If a TiDB/MySQL endpoint is reachable, run:

```sql
select type,version,git_hash from information_schema.cluster_info group by type,version,git_hash;
```

With `mycli`:

```bash
mycli -h <host> -P <port> -u <user> --password '<pass>' -e "select type,version,git_hash from information_schema.cluster_info group by type,version,git_hash;"
```

With `mysql`:

```bash
mysql -h <host> -P <port> -u <user> -p'<pass>' -e "select type,version,git_hash from information_schema.cluster_info group by type,version,git_hash;"
```

Use any parsed DSN that has permission to query `information_schema.cluster_info`.

When using `bash scripts/parse_tcms_env.sh`, the script automatically attempts this query with parsed DSNs. If query succeeds, it prints a `CLUSTER_COMPONENT_VERSIONS` section with `type/version/git_hash`.

## Script

Use bundled parser for deterministic output:

```bash
bash scripts/parse_tcms_env.sh
```

Optional custom paths:

```bash
bash scripts/parse_tcms_env.sh /path/to/.env /path/to/kubeconfig.yml
```

The script output includes:

- `TESTBED`
- `TCMS_URL`
- `MYSQL_PROXY` (if present)
- `MYCLI_COMMANDS`
- `CLUSTER_COMPONENT_VERSIONS` (when query succeeds)
