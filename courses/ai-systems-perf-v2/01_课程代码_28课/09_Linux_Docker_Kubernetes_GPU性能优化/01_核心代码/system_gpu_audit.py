#!/usr/bin/env python3
"""只读系统审计：不修改 sysctl、CPU Governor、GPU Clock 或容器配置。"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import time
from pathlib import Path


def read_text(path: str, default: str = "unavailable") -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").strip()
    except (OSError, PermissionError):
        return default


def run(argv: list[str], timeout: int = 10) -> dict:
    if not shutil.which(argv[0]):
        return {"available": False, "command": argv, "output": "command not found"}
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                           check=False)
        output = (p.stdout or p.stderr).strip()
        return {"available": True, "command": argv, "returncode": p.returncode,
                "output": output}
    except subprocess.TimeoutExpired:
        return {"available": True, "command": argv, "timeout": True}


def parse_cpu_max(text: str) -> dict:
    parts = text.split()
    if len(parts) != 2:
        return {"raw": text, "quota_cpus": None}
    quota, period = parts
    if quota == "max":
        return {"raw": text, "quota_cpus": "unlimited"}
    try:
        return {"raw": text, "quota_cpus": round(int(quota) / int(period), 3)}
    except (ValueError, ZeroDivisionError):
        return {"raw": text, "quota_cpus": None}


def parse_key_values(text: str) -> dict:
    result = {}
    for line in text.splitlines():
        fields = line.split()
        if len(fields) == 2:
            key, value = fields
            try:
                result[key] = int(value)
            except ValueError:
                result[key] = value
    return result


def cgroup_v2_path() -> Path:
    # /proc/self/cgroup 常见格式：0::/user.slice/...
    for line in read_text("/proc/self/cgroup", "").splitlines():
        fields = line.split(":", 2)
        if len(fields) == 3 and fields[0] == "0":
            return Path("/sys/fs/cgroup") / fields[2].lstrip("/")
    return Path("/sys/fs/cgroup")


def cpu_jitter(samples: int, work: int) -> dict:
    """微型 CPU 调度抖动探针，不是通用 CPU Benchmark。"""
    times_ms = []
    checksum = 0
    for _ in range(samples):
        start = time.perf_counter_ns()
        local = 0
        for i in range(work):
            local = (local + i * i) % 1_000_000_007
        checksum ^= local
        times_ms.append((time.perf_counter_ns() - start) / 1e6)
    ordered = sorted(times_ms)
    p95_index = min(len(ordered) - 1, int(0.95 * len(ordered)))
    return {
        "samples": samples,
        "work_per_sample": work,
        "median_ms": round(statistics.median(times_ms), 4),
        "p95_ms": round(ordered[p95_index], 4),
        "max_ms": round(max(times_ms), 4),
        "jitter_max_over_median": round(max(times_ms) / statistics.median(times_ms), 3),
        "checksum": checksum,
    }


def linux_audit(args: argparse.Namespace) -> dict:
    cg = cgroup_v2_path()
    cpu_max = read_text(str(cg / "cpu.max"))
    return {
        "platform": platform.platform(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "pid": os.getpid(),
        "logical_cpus_visible": os.cpu_count(),
        "affinity_cpus": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else [],
        "loadavg": os.getloadavg() if hasattr(os, "getloadavg") else None,
        "cgroup_v2_path": str(cg),
        "cpu_max": parse_cpu_max(cpu_max),
        "cpu_stat": parse_key_values(read_text(str(cg / "cpu.stat"), "")),
        "memory_current": read_text(str(cg / "memory.current")),
        "memory_max": read_text(str(cg / "memory.max")),
        "memory_events": parse_key_values(read_text(str(cg / "memory.events"), "")),
        "cpuset_effective": read_text(str(cg / "cpuset.cpus.effective")),
        "memory_nodes_effective": read_text(str(cg / "cpuset.mems.effective")),
        "transparent_hugepage": read_text(
            "/sys/kernel/mm/transparent_hugepage/enabled"
        ),
        "swappiness": read_text("/proc/sys/vm/swappiness"),
        "memory_psi": read_text("/proc/pressure/memory"),
        "io_psi": read_text("/proc/pressure/io"),
        "shm": run(["df", "-h", "/dev/shm"]),
        "numa": run(["numactl", "-H"]),
        "cpu_jitter_probe": cpu_jitter(args.samples, args.work),
    }


def nvidia_audit() -> dict:
    result = {
        "nvidia_smi": run(["nvidia-smi"]),
        "gpu_query": run([
            "nvidia-smi",
            "--query-gpu=index,name,compute_cap,pci.bus_id,memory.total,"
            "persistence_mode,pstate,temperature.gpu,power.draw",
            "--format=csv",
        ]),
        "topology": run(["nvidia-smi", "topo", "-m"]),
    }
    try:
        import torch
        result["pytorch"] = {
            "version": torch.__version__,
            "compiled_cuda": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "visible_devices": torch.cuda.device_count(),
            "cudnn_version": torch.backends.cudnn.version(),
        }
        if torch.cuda.is_available():
            result["pytorch"]["devices"] = [
                {
                    "index": i,
                    "name": torch.cuda.get_device_name(i),
                    "compute_capability": list(torch.cuda.get_device_capability(i)),
                }
                for i in range(torch.cuda.device_count())
            ]
    except ImportError:
        result["pytorch"] = {"available": False, "reason": "PyTorch not installed"}
    return result


def recommendations(audit: dict) -> list[str]:
    notes = []
    cpu_stat = audit["linux"]["cpu_stat"]
    if cpu_stat.get("nr_throttled", 0) > 0:
        notes.append("cgroup has observed CPU throttling; compare delta during workload.")
    mem_events = audit["linux"]["memory_events"]
    if mem_events.get("oom", 0) > 0 or mem_events.get("oom_kill", 0) > 0:
        notes.append("cgroup has OOM events; inspect host RAM and container/Pod limits.")
    if audit["linux"]["memory_current"] == "unavailable":
        notes.append("cgroup v2 metrics unavailable; system may use v1 or restrict access.")
    if not audit["nvidia"]["nvidia_smi"].get("available", False):
        notes.append("nvidia-smi unavailable; Level 0 is still valid.")
    notes.append("Compare counters before/after the target workload; cumulative values alone are not rates.")
    notes.append("This audit is read-only and intentionally changes no system setting.")
    return notes


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--samples", type=int, default=30)
    p.add_argument("--work", type=int, default=100_000)
    p.add_argument("--output", default="-")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    audit = {"linux": linux_audit(args), "nvidia": nvidia_audit()}
    audit["recommendations"] = recommendations(audit)
    text = json.dumps(audit, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(text)
    else:
        Path(args.output).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
