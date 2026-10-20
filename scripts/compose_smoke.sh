#!/usr/bin/env bash
# CI smoke test of the Compose stack: health, a key, a run job, two workers, the result.
set -euo pipefail
docker compose up -d --build --wait postgres api worker
KEY=$(docker compose exec -T api fdeops keys create --name ci --role admin | awk '/^key:/ {print $2}')
curl -fsS http://127.0.0.1:8000/health
JOB=$(curl -fsS -X POST http://127.0.0.1:8000/v1/tenants/ledgerloop/runs \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d '{"agent_config": "agents/ledgerloop-heuristic.yaml", "dataset": "support-core", "split": "dev", "limit": 8}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
for i in $(seq 1 60); do
  STATUS=$(curl -fsS "http://127.0.0.1:8000/v1/tenants/ledgerloop/jobs/$JOB" -H "Authorization: Bearer $KEY" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  echo "job $JOB: $STATUS"
  [ "$STATUS" = "succeeded" ] && break
  [ "$STATUS" = "failed" ] && { docker compose logs worker; exit 1; }
  sleep 2
done
[ "$STATUS" = "succeeded" ]
curl -fsS http://127.0.0.1:8000/v1/tenants/ledgerloop/runs -H "Authorization: Bearer $KEY" | head -c 400
echo
docker compose down -v
