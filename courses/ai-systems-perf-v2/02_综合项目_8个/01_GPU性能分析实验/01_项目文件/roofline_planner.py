#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def analyze(flops, bytes_moved, peak_tflops, bandwidth_gbps):
    if min(flops, bytes_moved, peak_tflops, bandwidth_gbps) <= 0:
        raise ValueError("所有参数必须大于 0")

    peak_flops = peak_tflops * 1e12
    bandwidth = bandwidth_gbps * 1e9
    arithmetic_intensity = flops / bytes_moved
    ridge_point = peak_flops / bandwidth
    memory_roof = bandwidth * arithmetic_intensity
    attainable = min(peak_flops, memory_roof)
    lower_bound_seconds = flops / attainable
    bound = "memory-model-bound" if arithmetic_intensity < ridge_point else "compute-model-bound"

    return {
        "flops": flops,
        "bytes_moved": bytes_moved,
        "peak_tflops": peak_tflops,
        "bandwidth_gbps": bandwidth_gbps,
        "arithmetic_intensity_flop_per_byte": arithmetic_intensity,
        "ridge_point_flop_per_byte": ridge_point,
        "roofline_attainable_gflops": attainable / 1e9,
        "roofline_time_lower_bound_ms": lower_bound_seconds * 1e3,
        "model_classification": bound,
        "warning": "这是理论方向模型；真实瓶颈需由基准与 Profiler 验证。",
    }


def main():
    parser = argparse.ArgumentParser(description="通用 Roofline 规划器")
    parser.add_argument("--flops", type=float, default=2e9)
    parser.add_argument("--bytes", dest="bytes_moved", type=float, default=1e9)
    parser.add_argument("--peak-tflops", type=float, default=20.0)
    parser.add_argument("--bandwidth-gbps", type=float, default=500.0)
    parser.add_argument("--output", default="reports/roofline.json")
    args = parser.parse_args()

    result = analyze(
        args.flops,
        args.bytes_moved,
        args.peak_tflops,
        args.bandwidth_gbps,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
