from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
targets = sorted((ROOT / "lessons").glob("lesson-*/run.py")) + sorted((ROOT / "projects").glob("project-*/run.py"))
targets += [ROOT / "projects/project-05/train_toy_policy.py", ROOT / "projects/project-06/durable_commit.py"]
summary = {"passed": [], "failed": []}
for target in targets:
    proc = subprocess.run([sys.executable, str(target)], cwd=ROOT, text=True, capture_output=True, timeout=60)
    key = str(target.relative_to(ROOT))
    summary["passed" if proc.returncode == 0 else "failed"].append(key)
    if proc.returncode != 0:
        print(proc.stdout); print(proc.stderr, file=sys.stderr)
print(json.dumps(summary, ensure_ascii=False, indent=2))
raise SystemExit(1 if summary["failed"] else 0)
