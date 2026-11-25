#!/usr/bin/env python3
import argparse
import json
import statistics


SAMPLE = [
    {"step_ms": 120, "gpu_busy_ms": 70, "input_ms": 32,
     "launch_gap_ms": 12, "sync_ms": 3, "memory_mb": 5200},
    {"step_ms": 124, "gpu_busy_ms": 71, "input_ms": 35,
     "launch_gap_ms": 13, "sync_ms": 3, "memory_mb": 5310},
    {"step_ms": 130, "gpu_busy_ms": 72, "input_ms": 39,
     "launch_gap_ms": 14, "sync_ms": 4, "memory_mb": 5430},
    {"step_ms": 138, "gpu_busy_ms": 73, "input_ms": 44,
     "launch_gap_ms": 15, "sync_ms": 5, "memory_mb": 5560},
    {"step_ms": 146, "gpu_busy_ms": 74, "input_ms": 49,
     "launch_gap_ms": 16, "sync_ms": 6, "memory_mb": 5700},
]


def percentile(values, q):
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


def slope(values):
    n = len(values)
    x_mean = (n - 1) / 2
    y_mean = statistics.mean(values)
    num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n)) or 1
    return num / den


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", help="JSON 文件，内容为 step 记录数组")
    args = p.parse_args()
    rows = json.load(open(args.input, encoding="utf-8")) if args.input else SAMPLE
    if not rows:
        raise SystemExit("没有记录")

    steps = [r["step_ms"] for r in rows]
    idle = [1 - r["gpu_busy_ms"] / r["step_ms"] for r in rows]
    mem = [r["memory_mb"] for r in rows]
    report = {
        "step_p50_ms": round(percentile(steps, 0.50), 2),
        "step_p95_ms": round(percentile(steps, 0.95), 2),
        "mean_gpu_idle_ratio": round(statistics.mean(idle), 3),
        "input_mean_ms": round(statistics.mean(r["input_ms"] for r in rows), 2),
        "launch_gap_mean_ms": round(statistics.mean(r["launch_gap_ms"] for r in rows), 2),
        "sync_mean_ms": round(statistics.mean(r["sync_ms"] for r in rows), 2),
        "memory_growth_mb_per_step": round(slope(mem), 2),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    hypotheses = []
    if report["mean_gpu_idle_ratio"] > 0.25:
        hypotheses.append("GPU 空闲较多：先检查输入管线和 CPU launch 空洞")
    if report["input_mean_ms"] > 0.20 * report["step_p50_ms"]:
        hypotheses.append("输入阶段占比高：用 record_function 拆 DataLoader/H2D/预处理")
    if report["launch_gap_mean_ms"] > 0.08 * report["step_p50_ms"]:
        hypotheses.append("launch gap 偏高：检查小算子、Python 循环与同步")
    if report["memory_growth_mb_per_step"] > 5:
        hypotheses.append("显存随 step 上涨：检查 Tensor/计算图引用并抓 Memory Snapshot")
    print("\n优先验证的假设：")
    for i, text in enumerate(hypotheses or ["未触发规则，扩大采样窗口"], 1):
        print(f"{i}. {text}")


if __name__ == "__main__":
    main()
