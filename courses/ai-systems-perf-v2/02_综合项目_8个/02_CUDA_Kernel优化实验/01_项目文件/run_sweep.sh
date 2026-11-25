#!/usr/bin/env bash
set -euo pipefail
test -x build/reduction_benchmark || bash build_and_run.sh >/dev/null
mkdir -p reports
: > reports/size_sweep.csv
for n in 1048576 4194304 16777216; do
  build/reduction_benchmark --elements "$n" | tee -a reports/size_sweep.csv
done
