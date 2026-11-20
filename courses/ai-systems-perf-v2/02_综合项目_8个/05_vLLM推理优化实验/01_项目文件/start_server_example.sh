#!/usr/bin/env bash
set -euo pipefail
: "${MODEL_PATH:?请先设置MODEL_PATH为已获授权且可访问的模型路径或模型ID}"
command -v vllm >/dev/null 2>&1 || { echo "未检测到vllm命令。"; exit 2; }
mkdir -p reports logs
printf 'vllm serve %q --host 0.0.0.0 --port 8000\n' "$MODEL_PATH" > reports/server_command.txt
vllm serve "$MODEL_PATH" --host 0.0.0.0 --port 8000 2>&1 | tee logs/server.log
