#!/usr/bin/env bash
set -euo pipefail
mkdir -p reports
python3 gpu_profiling_lab.py --device auto --mode all --output reports/benchmark.json
if command -v nsys >/dev/null 2>&1; then
  nsys profile -o reports/nsys_baseline --force-overwrite true \
    python3 gpu_profiling_lab.py --device cuda --mode all --warmup 3 --iters 8
else
  echo "未检测到nsys，已完成通用基准并跳过Nsight Systems。"
fi
