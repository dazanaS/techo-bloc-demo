#!/usr/bin/env bash
# Execute SQL against the Dazana-classic-ws serverless warehouse.
# Usage: ./run_sql.sh "SELECT 1"   OR    ./run_sql.sh -f file.sql
set -euo pipefail

PROFILE="Dazana-classic-ws-pat"
WAREHOUSE_ID="a82088b3bfe8752c"

if [[ "${1:-}" == "-f" ]]; then
  STATEMENT="$(cat "$2")"
else
  STATEMENT="$1"
fi

REQ=$(python3 -c "
import json, sys
print(json.dumps({
  'statement': sys.argv[1],
  'warehouse_id': sys.argv[2],
  'wait_timeout': '50s',
  'on_wait_timeout': 'CONTINUE',
  'disposition': 'INLINE',
  'format': 'JSON_ARRAY'
}))
" "$STATEMENT" "$WAREHOUSE_ID")

RESP=$(databricks api post /api/2.0/sql/statements --profile=$PROFILE --json="$REQ")
SID=$(echo "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['statement_id'])")

# Poll until terminal
while true; do
  STATE=$(databricks api get /api/2.0/sql/statements/$SID --profile=$PROFILE | python3 -c "import json,sys; print(json.load(sys.stdin)['status']['state'])")
  if [[ "$STATE" == "SUCCEEDED" || "$STATE" == "FAILED" || "$STATE" == "CANCELED" || "$STATE" == "CLOSED" ]]; then
    break
  fi
  sleep 2
done

databricks api get /api/2.0/sql/statements/$SID --profile=$PROFILE
