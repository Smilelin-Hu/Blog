from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from phase5lab.gpu import print_report, run_gpu_probe


if __name__ == "__main__":
    report = run_gpu_probe("project-05", "masked_loss", scale=2)
    print_report(report)
    raise SystemExit(1 if report["status"] == "failed" else 0)
