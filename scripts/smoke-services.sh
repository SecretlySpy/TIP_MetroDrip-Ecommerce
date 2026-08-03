#!/usr/bin/env bash
# Smoke: build and start strangler sidecars, assert /healthz/ready == 200.
# Usage (repo root): bash scripts/smoke-services.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> Building services image (single target avoids parallel tag race)"
docker compose --profile services build notifications

echo "==> Starting db, redis, sidecars, internal caddy"
docker compose --profile services up -d db redis notifications fulfillment inventory caddy-internal

echo "==> Waiting for healthchecks"
for i in $(seq 1 40); do
  n=$(docker inspect -f '{{.State.Health.Status}}' metrodrip-notifications 2>/dev/null || echo starting)
  f=$(docker inspect -f '{{.State.Health.Status}}' metrodrip-fulfillment 2>/dev/null || echo starting)
  v=$(docker inspect -f '{{.State.Health.Status}}' metrodrip-inventory 2>/dev/null || echo starting)
  echo "  attempt $i: notifications=$n fulfillment=$f inventory=$v"
  if [[ "$n" == healthy && "$f" == healthy && "$v" == healthy ]]; then
    break
  fi
  sleep 3
done

fail=0
for url in \
  http://127.0.0.1:8002/healthz/ready \
  http://127.0.0.1:8003/healthz/ready \
  http://127.0.0.1:8001/healthz/ready \
  http://127.0.0.1:9080/internal/notifications/healthz/ready \
  http://127.0.0.1:9080/internal/fulfillment/healthz/ready \
  http://127.0.0.1:9080/internal/inventory/healthz/ready
do
  code=$(curl -s -o /tmp/smoke_body -w "%{http_code}" "$url" || echo 000)
  body=$(cat /tmp/smoke_body 2>/dev/null || true)
  echo "  $url → $code $body"
  if [[ "$code" != "200" ]]; then
    fail=1
  fi
done

# Correlation-ID round-trip: book a shipment through fulfillment with a fixed cid.
CID="smoke-cid-$(date +%s)"
book=$(curl -s -o /tmp/smoke_book -w "%{http_code}" \
  -H "Content-Type: application/json" \
  -H "X-Correlation-ID: $CID" \
  -d "{\"order_no\":\"MD-SMOKE-1\",\"courier\":\"jnt\",\"correlation_id\":\"$CID\"}" \
  http://127.0.0.1:8003/v1/shipments/book)
echo "  book shipment → $book $(cat /tmp/smoke_book)"
[[ "$book" == "200" ]] || fail=1

# Prove cid appears in fulfillment logs
if docker logs metrodrip-fulfillment 2>&1 | grep -q "$CID"; then
  echo "  correlation id $CID found in fulfillment logs: OK"
else
  echo "  correlation id $CID NOT found in fulfillment logs: FAIL"
  fail=1
fi

if [[ "$fail" -ne 0 ]]; then
  echo "SMOKE FAILED"
  exit 1
fi
echo "SMOKE PASSED — all /healthz/ready endpoints 200; correlation id traced"
