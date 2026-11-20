#!/usr/bin/env python3
import argparse
import gc
import json
import math
import platform
import statistics
import time
import tracemalloc


def baseline(x, y, bias):
    tmp1 = [a * b for a, b in zip(x, y)]
    tmp2 = [v + bias for v in tmp1]
    out = [v if v > 0.0 else 0.0 for v in tmp2]
    return out


def fused(x, y, bias):
    return [
        (value if value > 0.0 else 0.0)
        for a, b in zip(x, y)
        for value in (a * b + bias,)
    ]


def percentile(values, q):
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lo = math.floor(position)
    hi = math.ceil(position)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - position) + ordered[hi] * (position - lo)


def benchmark(fn, x, y, bias, warmup, repeat):
    for _ in range(warmup):
        fn(x, y, bias)
    gc.collect()

    samples = []
    checksum = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        out = fn(x, y, bias)
        samples.append(time.perf_counter() - t0)
        checksum = sum(out[:: max(1, len(out) // 1000)])
    mean = statistics.fmean(samples)
    return {
        "median_ms": statistics.median(samples) * 1e3,
        "p95_ms": percentile(samples, 0.95) * 1e3,
        "cv_percent": statistics.pstdev(samples) / mean * 100.0,
        "checksum_sample": checksum,
    }


def measure_peak(fn, x, y, bias):
    gc.collect()
    tracemalloc.start()
    out = fn(x, y, bias)
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"peak_mib": peak / 2**20, "output_length": len(out)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=300_000)
    parser.add_argument("--bias", type=float, default=-0.25)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--repeat", type=int, default=7)
    args = parser.parse_args()
    if args.n <= 0 or args.warmup < 0 or args.repeat < 3:
        raise SystemExit("要求 n > 0、warmup >= 0、repeat >= 3")

    x = [((i % 1009) - 504) / 503.0 for i in range(args.n)]
    y = [((i % 997) - 498) / 499.0 for i in range(args.n)]

    ref = baseline(x, y, args.bias)
    opt = fused(x, y, args.bias)
    max_abs_error = max(abs(a - b) for a, b in zip(ref, opt))
    if max_abs_error != 0.0:
        raise AssertionError(f"结果不一致：max_abs_error={max_abs_error}")
    del ref, opt

    base_stats = benchmark(
        baseline, x, y, args.bias, args.warmup, args.repeat
    )
    fused_stats = benchmark(
        fused, x, y, args.bias, args.warmup, args.repeat
    )
    base_mem = measure_peak(baseline, x, y, args.bias)
    fused_mem = measure_peak(fused, x, y, args.bias)

    report = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "config": vars(args),
        "correctness": {"exact": True, "max_abs_error": max_abs_error},
        "baseline": {"timing": base_stats, "memory": base_mem},
        "fused": {"timing": fused_stats, "memory": fused_mem},
        "speedup": base_stats["median_ms"] / fused_stats["median_ms"],
        "peak_memory_reduction": base_mem["peak_mib"] / fused_mem["peak_mib"],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
