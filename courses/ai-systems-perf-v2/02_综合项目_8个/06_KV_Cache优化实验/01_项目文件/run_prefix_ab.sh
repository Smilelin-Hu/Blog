#!/usr/bin/env bash
set -euo pipefail
: "${SERVED_MODEL:?请先设置SERVED_MODEL为服务返回的实际模型名称}"
base_url="${BASE_URL:-http://127.0.0.1:8000}"
label="${CACHE_MODE:-current}"
mkdir -p reports
python3 prefix_cache_benchmark.py --base-url "$base_url" --model "$SERVED_MODEL" \
  --requests 20 --output "reports/prefix_${label}.json"
