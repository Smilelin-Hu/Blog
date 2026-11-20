#!/usr/bin/env bash
set -euo pipefail
device="${1:-auto}"
python3 -c 'import torch; print("torch", torch.__version__)' >/dev/null || { echo "请先安装PyTorch。"; exit 2; }
mkdir -p reports
common=(--device "$device" --steps 20 --warmup 3 --batch-size 64 --features 256 --hidden 512 --classes 16 --workers 0)
python3 train_benchmark.py "${common[@]}" --mode baseline --output reports/baseline.json
python3 train_benchmark.py "${common[@]}" --mode optimized --output reports/optimized.json
python3 regression_gate.py reports/baseline.json reports/optimized.json --max-regression 0.10 --max-loss-delta 0.20
