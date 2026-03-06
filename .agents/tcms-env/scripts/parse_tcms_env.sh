#!/usr/bin/env bash
set -euo pipefail

env_file="${1:-.env}"
kubeconfig_file="${2:-kubeconfig.yml}"

if [[ ! -f "$env_file" || ! -f "$kubeconfig_file" ]]; then
  echo "Missing required file(s). Expected: $env_file and $kubeconfig_file"
  echo "Please provide/regenerate them (example): tcctl testbed get -p <plan-execution-id>"
  exit 1
fi

if [[ -z "${KUBECONFIG:-}" ]]; then
  echo "KUBECONFIG is not set. Run: export KUBECONFIG=$kubeconfig_file"
else
  echo "KUBECONFIG is set to: $KUBECONFIG"
fi

testbed="$(sed -nE 's/^TESTBED:[[:space:]]*//p' "$env_file" | head -n1)"

if [[ -z "$testbed" ]]; then
  echo "TESTBED not found in $env_file"
  exit 1
fi

plan_id=""
if [[ "$testbed" =~ -tps-([0-9]+)(-|$) ]]; then
  plan_id="${BASH_REMATCH[1]}"
else
  plan_id="$(printf '%s\n' "$testbed" | grep -oE '[0-9]{6,}' | head -n1 || true)"
fi

mysql_proxy="$(sed -nE 's/^MYSQL_PROXY:[[:space:]]*//p' "$env_file" | head -n1 || true)"

echo "TESTBED: $testbed"
if [[ -n "$plan_id" ]]; then
  echo "TCMS_URL: https://tcms.pingcap.net/dashboard/executions/plan/$plan_id"
else
  echo "TCMS_URL: <unable to derive plan id from TESTBED>"
fi

if [[ -n "$mysql_proxy" ]]; then
  echo "MYSQL_PROXY: $mysql_proxy"
fi

echo "MYCLI_COMMANDS:"

# DSN pattern example: root:@tcp(10.2.12.57:31415)/
# Also supports optional db name: user:pass@tcp(host:port)/db_name
dsns="$(grep -oE '[A-Za-z0-9_]+:[^@" ]*@tcp\([^)]+\)/[^" ]*' "$env_file" | sort -u || true)"
version_sql="select type,version,git_hash from information_schema.cluster_info group by type,version,git_hash order by type;"
version_result=""
version_source=""
last_query_error=""

if [[ -z "$dsns" ]]; then
  echo "- <no DSN found in $env_file>"
  exit 0
fi

while IFS= read -r dsn; do
  [[ -z "$dsn" ]] && continue
  if [[ "$dsn" =~ ^([^:]+):([^@]*)@tcp\(([^:]+):([0-9]+)\)/(.*)$ ]]; then
    user="${BASH_REMATCH[1]}"
    pass="${BASH_REMATCH[2]}"
    host="${BASH_REMATCH[3]}"
    port="${BASH_REMATCH[4]}"
    db="${BASH_REMATCH[5]}"

    cmd="mycli -h $host -P $port -u $user --password '$pass'"
    if [[ -n "$db" ]]; then
      cmd="$cmd $db"
    fi

    echo "- $cmd"

    if [[ -z "$version_result" ]]; then
      if command -v mysql >/dev/null 2>&1; then
        if out="$(MYSQL_PWD="$pass" mysql --connect-timeout=5 -h "$host" -P "$port" -u "$user" -e "$version_sql" 2>&1)"; then
          version_result="$out"
          version_source="mysql://$user@$host:$port"
        else
          last_query_error="$(printf '%s\n' "$out" | head -n1)"
        fi
      elif command -v mycli >/dev/null 2>&1; then
        if out="$(mycli -h "$host" -P "$port" -u "$user" --password "$pass" -e "$version_sql" 2>&1)"; then
          version_result="$out"
          version_source="mycli://$user@$host:$port"
        else
          last_query_error="$(printf '%s\n' "$out" | head -n1)"
        fi
      fi
    fi
  else
    echo "- <unparsed DSN> $dsn"
  fi
done <<< "$dsns"

echo "CLUSTER_COMPONENT_VERSIONS:"
if [[ -n "$version_result" ]]; then
  echo "SOURCE: $version_source"
  printf '%s\n' "$version_result"
else
  echo "<query not successful>"
  if [[ -n "$last_query_error" ]]; then
    echo "QUERY_ERROR: $last_query_error"
  else
    echo "QUERY_ERROR: mysql/mycli client unavailable or no reachable DSN"
  fi
fi
