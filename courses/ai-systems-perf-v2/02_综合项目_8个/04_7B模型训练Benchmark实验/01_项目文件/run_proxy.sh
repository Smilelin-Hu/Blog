#!/usr/bin/env bash
set -euo pipefail
device="${1:-auto}"
python3 -c 'import torch; print("torch", torch.__version__)' >/dev/null || { echo "请先安装PyTorch。"; exit 2; }
mkdir -p reports
python3 capacity_planner.py --params 7e9 --gpus 2 --gpu-memory-gib 20 --output reports/capacity.json
python3 gpt_proxy_benchmark.py --device "$device" --preset proxy --steps 5 --warmup 1 --output reports/proxy.json
