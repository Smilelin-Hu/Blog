#!/usr/bin/env python3
import argparse
import json
import math
import operator
import platform
import random
import statistics
import time
from pathlib import Path


def silu(value):
    return value / (1.0 + math.exp(-max(-60.0, min(60.0, value))))


def baseline(values, epsilon):
    squares = [value * value for value in values]
    mean_square = sum(squares) / len(squares)
    inverse_rms = 1.0 / math.sqrt(mean_square + epsilon)
    normalized = [value * inverse_rms for value in values]
    return [silu(value) for value in normalized]


def candidate(values, epsilon):
    mean_square = sum(map(operator.mul, values, values)) / len(values)
    inverse_rms = 1.0 / math.sqrt(mean_square + epsilon)
    return [silu(value * inverse_rms) for value in values]


def percentile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return values[low]
    return values[low] * (high - position) + values[high] * (position - low)


def benchmark(function, values, epsilon, warmup, repeats):
    for _ in range(warmup):
        function(values, epsilon)
    samples = []
    output = None
    for _ in range(repeats):
        start = time.perf_counter()
        output = function(values, epsilon)
        samples.append(time.perf_counter() - start)
    return output, samples


def summarize(samples, elements):
    p50 = percentile(samples, 0.50)
    return {
        "p50_ms": p50 * 1000,
        "p95_ms": percentile(samples, 0.95) * 1000,
        "mean_ms": statistics.mean(samples) * 1000,
        "elements_per_second_at_p50": elements / p50,
        "raw_seconds": samples,
    }


def main():
    parser = argparse.ArgumentParser(description="AI 性能工程结课实验")
    parser.add_argument("--elements", type=int, default=200000)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--epsilon", type=float, default=1e-6)
    parser.add_argument("--max-relative-error", type=float, default=1e-12)
    parser.add_argument("--max-regression", type=float, default=0.05)
    parser.add_argument("--target-speedup", type=float, default=1.0)
    parser.add_argument("--hotspot-fraction", type=float, default=0.60)
    parser.add_argument("--output", default="reports/capstone.json")
    args = parser.parse_args()
    if min(args.elements, args.repeats, args.epsilon, args.target_speedup) <= 0:
        raise ValueError("规模、重复、epsilon 和目标加速必须大于 0")
    if args.warmup < 0 or not 0 < args.hotspot_fraction <= 1:
        raise ValueError("warmup 必须非负，hotspot-fraction 必须位于 (0, 1]")

    rng = random.Random(2026)
    values = [rng.uniform(-3.0, 3.0) for _ in range(args.elements)]
    baseline_output, baseline_samples = benchmark(
        baseline, values, args.epsilon, args.warmup, args.repeats
    )
    candidate_output, candidate_samples = benchmark(
        candidate, values, args.epsilon, args.warmup, args.repeats
    )

    max_abs = max(abs(left - right)
                  for left, right in zip(baseline_output, candidate_output))
    denominator = max(max(abs(value) for value in baseline_output), 1e-30)
    max_relative = max_abs / denominator
    baseline_summary = summarize(baseline_samples, args.elements)
    candidate_summary = summarize(candidate_samples, args.elements)
    speedup = baseline_summary["p50_ms"] / candidate_summary["p50_ms"]
    predicted_end_to_end_speedup = 1.0 / (
        (1 - args.hotspot_fraction) + args.hotspot_fraction / speedup
    )
    correctness_pass = max_relative <= args.max_relative_error
    performance_pass = (
        candidate_summary["p50_ms"]
        <= baseline_summary["p50_ms"] * (1 + args.max_regression)
        and speedup >= args.target_speedup
    )

    result = {
        "workload": {
            "elements": args.elements,
            "operation": "RMSNorm + SiLU",
            "seed": 2026,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "baseline": baseline_summary,
        "candidate": candidate_summary,
        "correctness": {
            "max_absolute_error": max_abs,
            "max_relative_error": max_relative,
            "threshold": args.max_relative_error,
            "pass": correctness_pass,
        },
        "speedup_p50": speedup,
        "hotspot_fraction": args.hotspot_fraction,
        "amdahl_predicted_end_to_end_speedup": predicted_end_to_end_speedup,
        "gate": {
            "performance_pass": performance_pass,
            "correctness_pass": correctness_pass,
            "pass": performance_pass and correctness_pass,
        },
        "warning": "这是 CPU 教学负载；结果不能外推到 GPU Kernel 或真实模型。",
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if not result["gate"]["pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
