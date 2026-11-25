#!/usr/bin/env bash
set -euo pipefail
: "${SERVED_MODEL:?请先设置SERVED_MODEL为服务返回的实际模型名称}"
base_url="${BASE_URL:-http://127.0.0.1:8000}"
mkdir -p reports
for concurrency in 1 4 8 16; do
  python3 openai_stream_benchmark.py --base-url "$base_url" --model "$SERVED_MODEL" \
    --requests 32 --concurrency "$concurrency" --max-tokens 64 \
    --output "reports/c${concurrency}.json"
done
