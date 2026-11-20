#!/usr/bin/env python3
import argparse
import json
import math
import platform
import statistics
import time


def percentile(values, q):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)


def summarize(samples_s):
    mean = statistics.fmean(samples_s)
    stdev = statistics.pstdev(samples_s)
    return {
        "median_ms": statistics.median(samples_s) * 1e3,
        "p95_ms": percentile(samples_s, 0.95) * 1e3,
        "min_ms": min(samples_s) * 1e3,
        "max_ms": max(samples_s) * 1e3,
        "cv_percent": 100.0 * stdev / mean if mean else 0.0,
    }


def baseline_once(n):
    t0 = time.perf_counter()
    values = list(range(n))
    t1 = time.perf_counter()

    total = 0
    for x in values:
        total += x * x + 3 * x + 7
    t2 = time.perf_counter()

    # 模拟真实流水线中的结果封装，而不是用 sleep 制造瓶颈。
    result = int(total)
    t3 = time.perf_counter()
    phases = {
        "input_ms": (t1 - t0) * 1e3,
        "compute_ms": (t2 - t1) * 1e3,
        "finalize_ms": (t3 - t2) * 1e3,
    }
    return result, phases


def optimized_once(n):
    t0 = time.perf_counter()
    # sum(x) = n(n-1)/2
    # sum(x^2) = n(n-1)(2n-1)/6
    sum_x = n * (n - 1) // 2
    sum_x2 = n * (n - 1) * (2 * n - 1) // 6
    result = sum_x2 + 3 * sum_x + 7 * n
    t1 = time.perf_counter()
    return result, {"closed_form_ms": (t1 - t0) * 1e3}


def run_many(fn, n, repeat):
    samples = []
    phase_totals = {}
    result = None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result, phases = fn(n)
        samples.append(time.perf_counter() - t0)
        for key, value in phases.items():
            phase_totals[key] = phase_totals.get(key, 0.0) + value
    phase_mean = {key: value / repeat for key, value in phase_totals.items()}
    return result, summarize(samples), phase_mean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=300_000)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--repeat", type=int, default=9)
    args = parser.parse_args()
    if args.n <= 0 or args.repeat < 3 or args.warmup < 0:
        raise SystemExit("要求 n > 0、repeat >= 3、warmup >= 0")

    expected, _ = optimized_once(args.n)
    actual, _ = baseline_once(args.n)
    if actual != expected:
        raise AssertionError(f"结果不一致：baseline={actual}, optimized={expected}")

    for _ in range(args.warmup):
        baseline_once(args.n)
        optimized_once(args.n)

    base_result, base_stats, base_phases = run_many(
        baseline_once, args.n, args.repeat
    )
    opt_result, opt_stats, opt_phases = run_many(
        optimized_once, args.n, args.repeat
    )
    assert base_result == opt_result

    base_total = sum(base_phases.values())
    compute_share = base_phases["compute_ms"] / base_total
    amdahl_if_compute_10x = 1.0 / ((1.0 - compute_share) + compute_share / 10.0)
    measured_speedup = base_stats["median_ms"] / opt_stats["median_ms"]

    report = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "config": vars(args),
        "correctness": True,
        "baseline": {"stats": base_stats, "phase_mean_ms": base_phases},
        "optimized": {"stats": opt_stats, "phase_mean_ms": opt_phases},
        "analysis": {
            "baseline_compute_share": compute_share,
            "amdahl_speedup_if_compute_10x": amdahl_if_compute_10x,
            "measured_algorithmic_speedup": measured_speedup,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
