#!/usr/bin/env python3
"""Customer-facing entry point for this project."""
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
WORK = HERE / "01_项目文件"
COMMAND = ['{python}', 'disagg_capacity_planner.py', '--decode-workers', '16', '--output', 'reports/capacity.json']
COMMAND = [sys.executable if part == "{python}" else part for part in COMMAND]
if COMMAND[0] == "bash" and shutil.which("bash") is None:
    print("本项目需要 Bash。Windows 用户请使用 WSL 或 Git Bash 运行。")
    raise SystemExit(2)
print("正在运行：", " ".join(COMMAND))
raise SystemExit(subprocess.call(COMMAND + sys.argv[1:], cwd=WORK))
