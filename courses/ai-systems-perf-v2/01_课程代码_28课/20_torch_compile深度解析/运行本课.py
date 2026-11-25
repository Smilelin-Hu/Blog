#!/usr/bin/env python3
"""Customer-facing entry point for this lesson."""
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "01_核心代码" / 'compile_roi_planner.py'
OUTPUT = HERE / "03_运行结果"
OUTPUT.mkdir(exist_ok=True)
print(f"正在运行：{SCRIPT.name}")
print(f"结果目录：{OUTPUT}")
raise SystemExit(subprocess.call([sys.executable, str(SCRIPT), *sys.argv[1:]], cwd=OUTPUT))
