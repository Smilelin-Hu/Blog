#!/usr/bin/env bash
set -euo pipefail
command -v nvcc >/dev/null 2>&1 || { echo "未检测到nvcc；请先运行Level 0成本模型。"; exit 2; }
mkdir -p reports build
nvcc -O3 -lineinfo -std=c++17 reduction_benchmark.cu -o build/reduction_benchmark
build/reduction_benchmark | tee reports/baseline.txt
