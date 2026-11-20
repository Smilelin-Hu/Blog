#!/usr/bin/env bash
set -euo pipefail
mkdir -p baseline candidate artifacts
python3 capstone_runner.py --elements 200000 --warmup 3 --repeats 20 \
  --target-speedup 1.0 --output candidate/metrics.json
printf '%q ' python3 capstone_runner.py --elements 200000 --warmup 3 --repeats 20 \
  --target-speedup 1.0 --output candidate/metrics.json > artifacts/commands.txt
printf '\n' >> artifacts/commands.txt
