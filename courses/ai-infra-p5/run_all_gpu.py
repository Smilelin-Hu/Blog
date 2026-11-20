from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--check-only", action="store_true")
args = parser.parse_args()
if importlib.util.find_spec("torch") is None:
    print(json.dumps({"status": "skipped", "reason": "PyTorch unavailable"}, ensure_ascii=False))
    raise SystemExit(0)
import torch
if not torch.cuda.is_available():
    print(json.dumps({"status": "skipped", "reason": "CUDA device unavailable"}, ensure_ascii=False))
    raise SystemExit(0)
if args.check_only:
    print(json.dumps({"status": "passed", "device_count": torch.cuda.device_count(), "devices": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]}, ensure_ascii=False, indent=2))
    raise SystemExit(0)
ROOT = Path(__file__).resolve().parent
targets = sorted((ROOT / "lessons").glob("lesson-*/run_gpu.py"))
summary = {"passed": [], "skipped": [], "failed": []}
for target in targets:
    proc = subprocess.run([sys.executable, str(target)], cwd=ROOT, text=True, capture_output=True)
    key = str(target.parent.relative_to(ROOT))
    bucket = "failed" if proc.returncode else ("skipped" if '"status": "skipped"' in proc.stdout else "passed")
    summary[bucket].append(key)
print(json.dumps(summary, ensure_ascii=False, indent=2))
raise SystemExit(1 if summary["failed"] else 0)
