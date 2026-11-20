#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import platform
import random
import statistics
import time
from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass
class RequestTrace:
    request_id: int
    arrival_s: float
    input_tokens: int
    token_times_s: list[float]
    success: bool

    @property
    def output_tokens(self) -> int:
        return len(self.token_times_s)

    @property
    def first_token_s(self) -> float:
        return self.token_times_s[0]

    @property
    def finish_s(self) -> float:
        return self.token_times_s[-1]

    @property
    def e2e_ms(self) -> float:
        return (self.finish_s - self.arrival_s) * 1000.0

    @property
    def ttft_ms(self) -> float:
        return (self.first_token_s - self.arrival_s) * 1000.0

    @property
    def tpot_ms(self) -> float:
        if self.output_tokens <= 1:
            return 0.0
        return (
            (self.finish_s - self.first_token_s)
            * 1000.0
            / (self.output_tokens - 1)
        )

    @property
    def itl_ms(self) -> list[float]:
        return [
            (right - left) * 1000.0
            for left, right in zip(self.token_times_s, self.token_times_s[1:])
        ]

    @property
    def per_user_output_tps(self) -> float:
        if self.output_tokens <= 1 or self.finish_s <= self.first_token_s:
            return float("nan")
        return (self.output_tokens - 1) / (self.finish_s - self.first_token_s)


def percentile(values: Iterable[float], q: float) -> float:
    ordered = sorted(v for v in values if math.isfinite(v))
    if not ordered:
        return float("nan")
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def summarize(values: Iterable[float]) -> dict[str, float]:
    cleaned = [v for v in values if math.isfinite(v)]
    if not cleaned:
        return {"mean": float("nan"), "p50": float("nan"),
                "p95": float("nan"), "p99": float("nan")}
    return {
        "mean": statistics.fmean(cleaned),
        "p50": percentile(cleaned, 0.50),
        "p95": percentile(cleaned, 0.95),
        "p99": percentile(cleaned, 0.99),
    }


def jittered_length(mean: int, jitter: float, rng: random.Random) -> int:
    low = max(1, round(mean * (1.0 - jitter)))
    high = max(low, round(mean * (1.0 + jitter)))
    return rng.randint(low, high)


def simulate_traces(args: argparse.Namespace) -> list[RequestTrace]:
    """A small queueing simulator, not a real model performance predictor."""
    rng = random.Random(args.seed)
    worker_available = [0.0 for _ in range(args.workers)]
    arrival_s = 0.0
    traces: list[RequestTrace] = []

    for request_id in range(args.requests):
        if request_id > 0:
            arrival_s += rng.expovariate(args.arrival_rps)

        input_tokens = jittered_length(
            args.prompt_tokens, args.length_jitter, rng
        )
        output_tokens = jittered_length(
            args.output_tokens, args.length_jitter, rng
        )

        worker = min(range(args.workers), key=worker_available.__getitem__)
        service_start_s = max(arrival_s, worker_available[worker])

        prefill_s = (
            args.base_prefill_ms / 1000.0
            + input_tokens / args.prefill_tokens_per_s
        )
        first_token_s = service_start_s + prefill_s

        # 为了观察 ITL 尾部，给每个 Token 间隔加入少量抖动。
        token_times = [first_token_s]
        for _ in range(1, output_tokens):
            jitter = max(0.1, rng.gauss(1.0, args.itl_jitter))
            token_times.append(
                token_times[-1] + args.decode_tpot_ms / 1000.0 * jitter
            )

        worker_available[worker] = token_times[-1]
        success = rng.random() >= args.failure_rate
        traces.append(
            RequestTrace(
                request_id=request_id,
                arrival_s=arrival_s,
                input_tokens=input_tokens,
                token_times_s=token_times,
                success=success,
            )
        )
    return traces


def analyze_traces(
    traces: list[RequestTrace], ttft_slo_ms: float, tpot_slo_ms: float
) -> dict:
    if not traces:
        raise ValueError("trace list is empty")

    window_start = min(t.arrival_s for t in traces)
    window_end = max(t.finish_s for t in traces)
    duration_s = window_end - window_start
    successful = [t for t in traces if t.success]
    good = [
        t for t in successful
        if t.ttft_ms <= ttft_slo_ms and t.tpot_ms <= tpot_slo_ms
    ]

    total_input = sum(t.input_tokens for t in successful)
    total_output = sum(t.output_tokens for t in successful)
    all_itls = [gap for t in successful for gap in t.itl_ms]

    metrics = {
        "attempted_requests": len(traces),
        "successful_requests": len(successful),
        "slo_compliant_requests": len(good),
        "duration_s": duration_s,
        "success_rate": len(successful) / len(traces),
        "request_throughput_rps": len(successful) / duration_s,
        "output_token_throughput_tps": total_output / duration_s,
        "input_token_throughput_tps": total_input / duration_s,
        "total_token_throughput_tps": (total_input + total_output) / duration_s,
        "goodput_rps": len(good) / duration_s,
        "goodput_ratio_of_attempted": len(good) / len(traces),
        "e2e_latency_ms": summarize(t.e2e_ms for t in successful),
        "ttft_ms": summarize(t.ttft_ms for t in successful),
        "tpot_ms_per_request": summarize(t.tpot_ms for t in successful),
        "itl_ms_per_token_gap": summarize(all_itls),
        "per_user_output_tps": summarize(
            t.per_user_output_tps for t in successful
        ),
    }
    return metrics


def print_distribution(name: str, stats: dict[str, float], unit: str) -> None:
    print(
        f"{name:24s} mean={stats['mean']:9.3f} {unit}  "
        f"p50={stats['p50']:9.3f}  p95={stats['p95']:9.3f}  "
        f"p99={stats['p99']:9.3f}"
    )


def print_trace_report(metrics: dict) -> None:
    print("\n=== Inference trace metrics ===")
    print(f"attempted requests       : {metrics['attempted_requests']}")
    print(f"successful requests      : {metrics['successful_requests']}")
    print(f"SLO-compliant requests   : {metrics['slo_compliant_requests']}")
    print(f"measurement duration     : {metrics['duration_s']:.3f} s")
    print(f"success rate             : {100*metrics['success_rate']:.2f}%")
    print(f"request throughput       : {metrics['request_throughput_rps']:.3f} req/s")
    print(f"input token throughput   : {metrics['input_token_throughput_tps']:.3f} tok/s")
    print(f"output token throughput  : {metrics['output_token_throughput_tps']:.3f} tok/s")
    print(f"total token throughput   : {metrics['total_token_throughput_tps']:.3f} tok/s")
    print(f"SLO goodput              : {metrics['goodput_rps']:.3f} req/s")
    print(f"goodput/attempted ratio  : {100*metrics['goodput_ratio_of_attempted']:.2f}%")
    print_distribution("E2E latency", metrics["e2e_latency_ms"], "ms")
    print_distribution("TTFT", metrics["ttft_ms"], "ms")
    print_distribution("TPOT per request", metrics["tpot_ms_per_request"], "ms")
    print_distribution("ITL per token gap", metrics["itl_ms_per_token_gap"], "ms")
    print_distribution("per-user output TPS", metrics["per_user_output_tps"], "tok/s")


def calculate_training_efficiency(args: argparse.Namespace) -> dict | None:
    if args.training_tokens_per_s <= 0 or args.peak_tflops <= 0:
        return None
    if args.exact_model_flops_per_token > 0:
        model_flops_per_token = args.exact_model_flops_per_token
        formula = "user supplied exact/analytical model FLOPs per token"
    else:
        model_flops_per_token = 6.0 * args.model_params_b * 1e9
        formula = "6P dense-Transformer approximation"

    useful_model_flops_per_s = (
        model_flops_per_token * args.training_tokens_per_s
    )
    cluster_peak_flops_per_s = (
        args.devices * args.peak_tflops * 1e12
    )
    mfu = useful_model_flops_per_s / cluster_peak_flops_per_s
    # 这是分析估算，不是硬件计数器实测 HFU。
    estimated_hfu = mfu * args.recompute_flops_factor
    return {
        "formula": formula,
        "model_flops_per_token": model_flops_per_token,
        "useful_model_tflops_per_s": useful_model_flops_per_s / 1e12,
        "cluster_peak_tflops": cluster_peak_flops_per_s / 1e12,
        "mfu": mfu,
        "estimated_hfu": estimated_hfu,
        "recompute_flops_factor": args.recompute_flops_factor,
    }


def print_training_efficiency(result: dict | None) -> None:
    print("\n=== Training MFU / HFU estimate ===")
    if result is None:
        print("Skipped. Set --training-tokens-per-s and --peak-tflops.")
        return
    print(f"model FLOPs formula       : {result['formula']}")
    print(f"model FLOPs/token         : {result['model_flops_per_token']:.4e}")
    print(f"useful model throughput   : {result['useful_model_tflops_per_s']:.3f} TFLOP/s")
    print(f"cluster theoretical peak  : {result['cluster_peak_tflops']:.3f} TFLOP/s")
    print(f"MFU                       : {100*result['mfu']:.2f}%")
    print(f"estimated HFU             : {100*result['estimated_hfu']:.2f}%")
    print(
        "HFU is analytical here. Real HFU needs profiler/counter data or a "
        "carefully validated executed-FLOPs model."
    )
    if result["mfu"] > 1.0 or result["estimated_hfu"] > 1.0:
        print("WARNING: utilization >100%; check peak precision, sparsity, FLOPs formula, and device count.")


def roofline(
    flops: float, bytes_moved: float, peak_tflops: float, bandwidth_gbps: float
) -> dict:
    if min(flops, bytes_moved, peak_tflops, bandwidth_gbps) <= 0:
        raise ValueError("all Roofline inputs must be positive")
    peak_flops_s = peak_tflops * 1e12
    bandwidth_bytes_s = bandwidth_gbps * 1e9
    arithmetic_intensity = flops / bytes_moved
    bandwidth_roof_flops_s = bandwidth_bytes_s * arithmetic_intensity
    attainable_flops_s = min(peak_flops_s, bandwidth_roof_flops_s)
    ridge_point = peak_flops_s / bandwidth_bytes_s
    return {
        "arithmetic_intensity_flops_per_byte": arithmetic_intensity,
        "ridge_point_flops_per_byte": ridge_point,
        "bandwidth_roof_tflops": bandwidth_roof_flops_s / 1e12,
        "attainable_tflops": attainable_flops_s / 1e12,
        "predicted_lower_bound_ms": flops / attainable_flops_s * 1000.0,
        "bound": "memory-bandwidth" if bandwidth_roof_flops_s < peak_flops_s else "compute",
    }


def print_roofline(result: dict | None, title: str = "Roofline estimate") -> None:
    print(f"\n=== {title} ===")
    if result is None:
        print("Skipped. Set peak, bandwidth, kernel FLOPs, and kernel bytes.")
        return
    print(f"arithmetic intensity      : {result['arithmetic_intensity_flops_per_byte']:.3f} FLOPs/Byte")
    print(f"ridge point               : {result['ridge_point_flops_per_byte']:.3f} FLOPs/Byte")
    print(f"bandwidth roof            : {result['bandwidth_roof_tflops']:.3f} TFLOP/s")
    print(f"attainable roof           : {result['attainable_tflops']:.3f} TFLOP/s")
    print(f"ideal time lower bound    : {result['predicted_lower_bound_ms']:.6f} ms")
    print(f"predicted primary bound   : {result['bound']}")


def optional_torch_matmul(args: argparse.Namespace) -> dict | None:
    if not args.torch_matmul:
        return None
    try:
        import torch
    except ImportError as exc:
        raise RuntimeError(
            "PyTorch is required only for --torch-matmul. Install torch or omit the flag."
        ) from exc

    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)
    if device.type == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")

    dtype_map = {
        "float32": torch.float32,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
    }
    dtype = dtype_map[args.dtype]
    if device.type == "cpu" and dtype == torch.float16:
        print("WARNING: CPU float16 matmul may be unsupported or slower than float32.")

    if device.type == "cuda":
        index = torch.cuda.current_device()
        props = torch.cuda.get_device_properties(index)
        cc = torch.cuda.get_device_capability(index)
        device_description = {
            "name": props.name,
            "compute_capability": f"{cc[0]}.{cc[1]}",
            "vram_gib": props.total_memory / 2**30,
            "torch_cuda": torch.version.cuda,
        }
    else:
        device_description = {"name": platform.processor() or "CPU"}

    n = args.matmul_n
    generator = torch.Generator(device=device).manual_seed(args.seed)
    a = torch.randn((n, n), device=device, dtype=dtype, generator=generator)
    b = torch.randn((n, n), device=device, dtype=dtype, generator=generator)

    def sync() -> None:
        if device.type == "cuda":
            torch.cuda.synchronize()

    for _ in range(args.matmul_warmup):
        _ = a @ b
    sync()
    start = time.perf_counter()
    for _ in range(args.matmul_iters):
        c = a @ b
    sync()
    elapsed_s = (time.perf_counter() - start) / args.matmul_iters
    # 防止某些编译/静态分析环境认为结果完全未使用。
    checksum = float(c[0, 0].float().cpu())

    flops = 2.0 * n**3
    element_size = a.element_size()
    # A、B 各读一次，C 写一次：这是理想最低流量，不是硬件计数器实测流量。
    minimum_bytes = 3.0 * n**2 * element_size
    achieved_tflops = flops / elapsed_s / 1e12
    result = {
        "device": str(device),
        "device_description": device_description,
        "dtype": args.dtype,
        "n": n,
        "mean_ms": elapsed_s * 1000.0,
        "achieved_tflops": achieved_tflops,
        "minimum_arithmetic_intensity": flops / minimum_bytes,
        "checksum": checksum,
    }
    if args.peak_tflops > 0:
        result["achieved_vs_peak"] = achieved_tflops / args.peak_tflops
    if args.memory_bandwidth_gbps > 0 and args.peak_tflops > 0:
        result["idealized_roofline"] = roofline(
            flops, minimum_bytes, args.peak_tflops, args.memory_bandwidth_gbps
        )
    return result


def print_matmul(result: dict | None) -> None:
    print("\n=== Optional PyTorch matmul ===")
    if result is None:
        print("Skipped. Add --torch-matmul to run it.")
        return
    print(f"device                     : {result['device']} {result['device_description']}")
    print(f"dtype / shape              : {result['dtype']} / {result['n']}x{result['n']}")
    print(f"mean latency               : {result['mean_ms']:.4f} ms")
    print(f"achieved throughput        : {result['achieved_tflops']:.4f} TFLOP/s")
    print(f"minimum arithmetic intensity: {result['minimum_arithmetic_intensity']:.3f} FLOPs/Byte")
    if "achieved_vs_peak" in result:
        print(f"achieved / supplied peak   : {100*result['achieved_vs_peak']:.2f}%")
    print(f"checksum                   : {result['checksum']:.6f}")
    if "idealized_roofline" in result:
        print_roofline(result["idealized_roofline"], "Idealized matmul Roofline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI performance metric laboratory"
    )
    # Level 0: inference trace simulation
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--arrival-rps", type=float, default=4.0)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--prompt-tokens", type=int, default=512)
    parser.add_argument("--output-tokens", type=int, default=128)
    parser.add_argument("--length-jitter", type=float, default=0.20)
    parser.add_argument("--base-prefill-ms", type=float, default=8.0)
    parser.add_argument("--prefill-tokens-per-s", type=float, default=5000.0)
    parser.add_argument("--decode-tpot-ms", type=float, default=25.0)
    parser.add_argument("--itl-jitter", type=float, default=0.08)
    parser.add_argument("--failure-rate", type=float, default=0.01)
    parser.add_argument("--ttft-slo-ms", type=float, default=500.0)
    parser.add_argument("--tpot-slo-ms", type=float, default=50.0)
    parser.add_argument("--seed", type=int, default=2026)

    # Level 1: training MFU/HFU estimate
    parser.add_argument("--model-params-b", type=float, default=7.0)
    parser.add_argument("--training-tokens-per-s", type=float, default=0.0)
    parser.add_argument("--devices", type=int, default=1)
    parser.add_argument(
        "--peak-tflops", type=float, default=0.0,
        help="Per-device non-sparse peak for the measured precision"
    )
    parser.add_argument(
        "--exact-model-flops-per-token", type=float, default=0.0
    )
    parser.add_argument(
        "--recompute-flops-factor", type=float, default=1.0,
        help="Executed FLOPs / useful model FLOPs; analytical estimate"
    )

    # Level 1/2: Roofline and optional real matmul
    parser.add_argument("--kernel-flops", type=float, default=0.0)
    parser.add_argument("--kernel-bytes", type=float, default=0.0)
    parser.add_argument("--memory-bandwidth-gbps", type=float, default=0.0)
    parser.add_argument("--torch-matmul", action="store_true")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument(
        "--dtype", choices=["float32", "float16", "bfloat16"], default="float32"
    )
    parser.add_argument("--matmul-n", type=int, default=2048)
    parser.add_argument("--matmul-warmup", type=int, default=5)
    parser.add_argument("--matmul-iters", type=int, default=20)
    parser.add_argument("--json-out", type=str, default="")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    positive = {
        "requests": args.requests,
        "arrival_rps": args.arrival_rps,
        "workers": args.workers,
        "prompt_tokens": args.prompt_tokens,
        "output_tokens": args.output_tokens,
        "prefill_tokens_per_s": args.prefill_tokens_per_s,
        "devices": args.devices,
        "matmul_n": args.matmul_n,
        "matmul_iters": args.matmul_iters,
    }
    invalid = [name for name, value in positive.items() if value <= 0]
    if invalid:
        raise ValueError(f"these arguments must be positive: {invalid}")
    if not 0.0 <= args.failure_rate < 1.0:
        raise ValueError("--failure-rate must be in [0, 1)")
    if not 0.0 <= args.length_jitter < 1.0:
        raise ValueError("--length-jitter must be in [0, 1)")
    if args.recompute_flops_factor < 1.0:
        raise ValueError("--recompute-flops-factor should be >= 1.0")


def main() -> None:
    args = parse_args()
    validate_args(args)

    traces = simulate_traces(args)
    trace_metrics = analyze_traces(
        traces, args.ttft_slo_ms, args.tpot_slo_ms
    )
    print_trace_report(trace_metrics)

    training = calculate_training_efficiency(args)
    print_training_efficiency(training)

    kernel_roofline = None
    if (
        args.kernel_flops > 0
        and args.kernel_bytes > 0
        and args.peak_tflops > 0
        and args.memory_bandwidth_gbps > 0
    ):
        kernel_roofline = roofline(
            args.kernel_flops,
            args.kernel_bytes,
            args.peak_tflops,
            args.memory_bandwidth_gbps,
        )
    print_roofline(kernel_roofline)

    matmul = optional_torch_matmul(args)
    print_matmul(matmul)

    if args.json_out:
        report = {
            "arguments": vars(args),
            "trace_metrics": trace_metrics,
            "training_efficiency": training,
            "kernel_roofline": kernel_roofline,
            "matmul": matmul,
            "traces": [asdict(t) for t in traces],
        }
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print(f"\nJSON report written to: {args.json_out}")


if __name__ == "__main__":
    main()
