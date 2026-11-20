#!/usr/bin/env python3
import argparse
import json
import statistics
import time
from contextlib import contextmanager

import torch


@contextmanager
def nvtx_range(name):
    torch.cuda.nvtx.range_push(name)
    try:
        yield
    finally:
        torch.cuda.nvtx.range_pop()


def baseline(x, y, z):
    tmp = y * z
    return x + tmp


def optimized(x, y, z):
    return torch.addcmul(x, y, z)


def event_benchmark(name, fn, x, y, z, warmup, repeat):
    with nvtx_range(f"{name}_warmup"):
        for _ in range(warmup):
            out = fn(x, y, z)
    torch.cuda.synchronize()

    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    wall_start = time.perf_counter()
    start.record()
    with nvtx_range(f"{name}_measure"):
        for _ in range(repeat):
            out = fn(x, y, z)
    end.record()
    end.synchronize()
    wall_ms = (time.perf_counter() - wall_start) * 1e3 / repeat
    event_ms = start.elapsed_time(end) / repeat
    return out, {"cuda_event_ms": event_ms, "host_wall_ms": wall_ms}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=4_194_304)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--repeat", type=int, default=50)
    parser.add_argument(
        "--mode", choices=("baseline", "optimized", "both"), default="both"
    )
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("未检测到 CUDA GPU；请先完成 Level 0")
    if args.n <= 0 or args.warmup < 0 or args.repeat <= 0:
        raise SystemExit("参数必须为正数，warmup 可为 0")

    device = torch.device("cuda")
    props = torch.cuda.get_device_properties(device)
    torch.manual_seed(2026)
    torch.cuda.manual_seed_all(2026)

    x = torch.randn(args.n, device=device, dtype=torch.float32)
    y = torch.randn_like(x)
    z = torch.randn_like(x)

    # 正确性验证放在正式测量区间外。
    ref = baseline(x, y, z)
    candidate = optimized(x, y, z)
    max_abs_error = (ref - candidate).abs().max().item()
    if not torch.allclose(ref, candidate, rtol=1e-5, atol=1e-6):
        raise AssertionError(f"结果不一致，max_abs_error={max_abs_error}")
    del ref, candidate
    torch.cuda.synchronize()

    results = {}
    if args.mode in ("baseline", "both"):
        out, results["baseline"] = event_benchmark(
            "baseline", baseline, x, y, z, args.warmup, args.repeat
        )
        del out
    if args.mode in ("optimized", "both"):
        out, results["optimized"] = event_benchmark(
            "optimized", optimized, x, y, z, args.warmup, args.repeat
        )
        del out

    if args.mode == "both":
        results["speedup_by_cuda_event"] = (
            results["baseline"]["cuda_event_ms"]
            / results["optimized"]["cuda_event_ms"]
        )

    report = {
        "environment": {
            "torch": torch.__version__,
            "cuda_runtime_reported_by_torch": torch.version.cuda,
            "device": torch.cuda.get_device_name(device),
            "compute_capability": [props.major, props.minor],
            "total_memory_gib": props.total_memory / 2**30,
        },
        "config": vars(args),
        "correctness": {"allclose": True, "max_abs_error": max_abs_error},
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
