#!/usr/bin/env python3
"""A dependency-free pipeline lab with optional PyTorch/CUDA compute."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import queue
import random
import shutil
import subprocess
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple


def timed_command(argv: List[str]) -> Dict[str, Any]:
    """Run a read-only inventory command without shell expansion."""
    if shutil.which(argv[0]) is None:
        return {"available": False}
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=5, check=False
        )
        return {
            "available": True,
            "returncode": result.returncode,
            "stdout": result.stdout.strip()[:4000],
            "stderr": result.stderr.strip()[:1000],
        }
    except (subprocess.SubprocessError, OSError) as exc:
        return {"available": True, "error": repr(exc)}


def host_memory_gib() -> Optional[float]:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1024 / 1024, 2)
    except (OSError, ValueError, IndexError):
        pass
    return None


def inventory() -> Dict[str, Any]:
    inv: Dict[str, Any] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "host_memory_gib": host_memory_gib(),
        "container_hint": Path("/.dockerenv").exists()
        or Path("/run/.containerenv").exists(),
    }
    inv["nvidia_smi"] = timed_command([
        "nvidia-smi",
        "--query-gpu=name,uuid,memory.total,driver_version,pci.bus_id",
        "--format=csv,noheader",
    ])
    inv["gpu_topology"] = timed_command(["nvidia-smi", "topo", "-m"])
    return inv


def percentile(values: List[float], q: float) -> float:
    data = sorted(values)
    if not data:
        return 0.0
    pos = (len(data) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(data) - 1)
    frac = pos - lo
    return data[lo] * (1 - frac) + data[hi] * frac


def make_dataset(path: Path, items: int, block_bytes: int) -> None:
    rng = random.Random(20260805)
    with path.open("wb") as f:
        for _ in range(items):
            f.write(rng.randbytes(block_bytes))


def read_and_prepare(
    f, item_id: int, block_bytes: int, io_delay_ms: float
) -> Tuple[bytes, Dict[str, float]]:
    t0 = time.perf_counter()
    f.seek(item_id * block_bytes)
    payload = f.read(block_bytes)
    if io_delay_ms:
        # Explicitly models remote/object-storage latency; it is not a disk claim.
        time.sleep(io_delay_ms / 1000.0)
    t1 = time.perf_counter()
    prepared = hashlib.blake2b(payload, digest_size=32).digest()
    t2 = time.perf_counter()
    return prepared, {
        "read_ms": (t1 - t0) * 1000,
        "preprocess_ms": (t2 - t1) * 1000,
    }


class ComputeEngine:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.torch = None
        self.device = "cpu"
        self.capability = None
        if args.torch:
            try:
                import torch
            except ImportError as exc:
                raise SystemExit("--torch requires PyTorch in this environment") from exc
            self.torch = torch
            if args.device == "cuda":
                if not torch.cuda.is_available():
                    raise SystemExit("--device cuda requested, but CUDA is unavailable")
                self.device = "cuda"
                self.capability = list(torch.cuda.get_device_capability())
            torch.manual_seed(20260805)
            self.base = torch.randn(args.matrix_n, args.matrix_n, dtype=torch.float32)

    def run(self, prepared: bytes) -> Tuple[str, Dict[str, float]]:
        if self.torch is None:
            t0 = time.perf_counter()
            digest = prepared
            for _ in range(self.args.compute_rounds):
                digest = hashlib.sha256(digest).digest()
            t1 = time.perf_counter()
            return digest.hex()[:16], {
                "transfer_ms": 0.0,
                "compute_ms": (t1 - t0) * 1000,
                "postprocess_ms": 0.0,
            }

        torch = self.torch
        scale = 1.0 + prepared[0] / 2550.0
        host = self.base * scale
        if self.args.pin_memory and self.device == "cuda":
            host = host.pin_memory()
        t0 = time.perf_counter()
        x = host.to(
            self.device,
            non_blocking=self.args.pin_memory and self.device == "cuda",
        )
        if self.device == "cuda":
            torch.cuda.synchronize()
        t1 = time.perf_counter()
        y = x @ x
        if self.device == "cuda":
            torch.cuda.synchronize()
        t2 = time.perf_counter()
        checksum = f"{float(y[0, 0].cpu()):.6f}"
        t3 = time.perf_counter()
        return checksum, {
            "transfer_ms": (t1 - t0) * 1000,
            "compute_ms": (t2 - t1) * 1000,
            "postprocess_ms": (t3 - t2) * 1000,
        }

    def metadata(self) -> Dict[str, Any]:
        if self.torch is None:
            return {"backend": "python-cpu"}
        torch = self.torch
        data: Dict[str, Any] = {
            "backend": "pytorch",
            "torch_version": torch.__version__,
            "torch_cuda_version": torch.version.cuda,
            "device": self.device,
        }
        if self.device == "cuda":
            data.update({
                "gpu_name": torch.cuda.get_device_name(),
                "compute_capability": self.capability,
                "memory_gib": round(
                    torch.cuda.get_device_properties(0).total_memory / 2**30, 2
                ),
            })
        return data


def merge_stage(dst: Dict[str, List[float]], src: Dict[str, float]) -> None:
    for key, value in src.items():
        dst[key].append(value)


def summarize(
    name: str,
    total_s: float,
    stages: Dict[str, List[float]],
    checksums: List[str],
) -> Dict[str, Any]:
    return {
        "name": name,
        "total_ms": round(total_s * 1000, 3),
        "items_per_second": round(len(checksums) / total_s, 3),
        "stage_mean_ms": {k: round(mean(v), 4) for k, v in stages.items()},
        "stage_p95_ms": {k: round(percentile(v, 0.95), 4) for k, v in stages.items()},
        "checksum_sample": checksums[:3],
        "checksums": checksums,
    }


def run_serial(
    path: Path, args: argparse.Namespace, engine: ComputeEngine
) -> Dict[str, Any]:
    stages: Dict[str, List[float]] = defaultdict(list)
    checksums: List[str] = []
    start = time.perf_counter()
    with path.open("rb") as f:
        for item_id in range(args.items):
            prepared, stage = read_and_prepare(
                f, item_id, args.block_bytes, args.io_delay_ms
            )
            merge_stage(stages, stage)
            checksum, stage = engine.run(prepared)
            merge_stage(stages, stage)
            checksums.append(checksum)
    return summarize("serial", time.perf_counter() - start, stages, checksums)


def run_prefetch(
    path: Path, args: argparse.Namespace, engine: ComputeEngine
) -> Dict[str, Any]:
    work_queue: queue.Queue[Any] = queue.Queue(maxsize=args.prefetch)
    stages: Dict[str, List[float]] = defaultdict(list)
    checksums: List[str] = []
    sentinel = object()

    def producer() -> None:
        with path.open("rb") as f:
            for item_id in range(args.items):
                prepared, stage = read_and_prepare(
                    f, item_id, args.block_bytes, args.io_delay_ms
                )
                work_queue.put((item_id, prepared, stage))
        work_queue.put(sentinel)

    start = time.perf_counter()
    thread = threading.Thread(target=producer, name="prefetch", daemon=True)
    thread.start()
    while True:
        item = work_queue.get()
        if item is sentinel:
            break
        _, prepared, producer_stage = item
        merge_stage(stages, producer_stage)
        checksum, compute_stage = engine.run(prepared)
        merge_stage(stages, compute_stage)
        checksums.append(checksum)
    thread.join()
    return summarize("prefetch", time.perf_counter() - start, stages, checksums)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--items", type=int, default=40)
    p.add_argument("--block-bytes", type=int, default=256 * 1024)
    p.add_argument("--io-delay-ms", type=float, default=3.0)
    p.add_argument("--compute-rounds", type=int, default=8000)
    p.add_argument("--prefetch", type=int, default=2)
    p.add_argument("--torch", action="store_true")
    p.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    p.add_argument("--matrix-n", type=int, default=512)
    p.add_argument("--pin-memory", action="store_true")
    p.add_argument("--json-out", type=Path, default=Path("stack_report.json"))
    args = p.parse_args()
    if args.items < 2 or args.block_bytes < 1024 or args.prefetch < 1:
        p.error("items >= 2, block-bytes >= 1024, prefetch >= 1 are required")
    return args


def main() -> None:
    args = parse_args()
    engine = ComputeEngine(args)
    with tempfile.TemporaryDirectory(prefix="ai-stack-lab-") as tmp:
        dataset = Path(tmp) / "dataset.bin"
        make_dataset(dataset, args.items, args.block_bytes)
        # Warm up the selected compute path outside the reported interval.
        engine.run(b"warmup".ljust(32, b"0"))
        serial = run_serial(dataset, args, engine)
        prefetch = run_prefetch(dataset, args, engine)

    if serial["checksums"] != prefetch["checksums"]:
        raise RuntimeError("correctness check failed: pipeline changed item results")
    speedup = serial["total_ms"] / prefetch["total_ms"]
    report = {
        "config": vars(args) | {"json_out": str(args.json_out)},
        "inventory": inventory(),
        "compute": engine.metadata(),
        "serial": {k: v for k, v in serial.items() if k != "checksums"},
        "prefetch": {k: v for k, v in prefetch.items() if k != "checksums"},
        "speedup": round(speedup, 3),
        "correctness": "PASS",
        "interpretation": (
            "Prefetch overlaps producer work with consumer work; "
            "speedup depends on the slowest stage and available resources."
        ),
    }
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
