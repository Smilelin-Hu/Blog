#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports
python3 disagg_capacity_planner.py --output reports/capacity.json
for rate in 1 2 4 8; do
  python3 disagg_capacity_planner.py --arrival-rate "$rate" --decode-workers 16 \
    --output "reports/rate_${rate}.json"
done
for link in 25 100 400; do
  python3 disagg_capacity_planner.py --link-gbps "$link" --decode-workers 16 \
    --output "reports/link_${link}.json"
done
