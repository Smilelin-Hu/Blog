#!/usr/bin/env python3
import argparse
import contextlib
import json
import math
import platform
import statistics
import time
from pathlib import Path

import torch


def percentile(values, q):
    data = sorted(values)
    if not data:
        return float("nan")
    position = (len(data) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return data[lower]
    weight = position - lower
    return data[lower] * (1 - weight) + data[upper] * weight


def synchronize(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def architecture_name(capability):
    major, minor = capability
    if (major, minor) == (8, 9):
        return "Ada Lovelace"
    if major == 8:
        return "Ampere"
    if major == 9:
        return "Hopper"
    if major >= 10:
        return "Blackwell-or-newer"
    return f"pre-Ampere-or-other-sm_{major}{minor}"


def environment(device):
    info = {
        "python": platform.python_version(),
        "pytorch": torch.__version__,
        "device": str(device),
        "cuda_available": torch.cuda.is_available(),
        "pytorch_cuda_runtime": torch.version.cuda,
    }
    if device.type == "cuda":
        props = torch.cuda.get_device_properties(device)
        capability = torch.cuda.get_device_capability(device)
        info.update({
            "gpu_name": props.name,
            "compute_capability": f"{capability[0]}.{capability[1]}",
            "architecture_family": architecture_name(capability),
            "vram_gib": round(props.total_memory / 2**30, 2),
            "gpu_count": torch.cuda.device_count(),
        })
    return info


@contextlib.contextmanager
def nvtx_range(name, device):
    enabled = device.type == "cuda"
    if enabled:
        torch.cuda.nvtx.range_push(name)
    try:
        yield
    finally:
        if enabled:
            torch.cuda.nvtx.range_pop()


def timed(fn, device, warmup, iterations):
    with torch.inference_mode():
        for _ in range(warmup):
            output = fn()
        synchronize(device)

        samples_ms = []
        for _ in range(iterations):
            start = time.perf_counter_ns()
            output = fn()
            synchronize(device)
            samples_ms.append((time.perf_counter_ns() - start) / 1e6)

    return output, {
        "p50_ms": statistics.median(samples_ms),
        "p95_ms": percentile(samples_ms, 0.95),
        "min_ms": min(samples_ms),
        "max_ms": max(samples_ms),
        "iterations": iterations,
    }


def check_close(reference, candidate):
    torch.testing.assert_close(reference, candidate, rtol=2e-4, atol=2e-4)
    return True


def build_workloads(args, device):
    generator = torch.Generator(device=device)
    generator.manual_seed(args.seed)
    x = torch.randn(args.elements, device=device, generator=generator)
    a = torch.randn((args.matrix, args.matrix), device=device, generator=generator)
    b = torch.randn((args.matrix, args.matrix), device=device, generator=generator)

    def launch_baseline():
        y = x.clone()
        for _ in range(args.steps):
            y = y + 0.001
        return y

    def launch_optimized():
        return x + args.steps * 0.001

    def memory_baseline():
        return torch.relu(x * 1.1 + 0.3).square()

    def memory_optimized():
        y = x.clone()
        return y.mul_(1.1).add_(0.3).relu_().square_()

    def matmul():
        return a @ b

    return {
        "launch": (launch_baseline, launch_optimized),
        "memory": (memory_baseline, memory_optimized),
        "matmul": (matmul, None),
    }


def profile_once(name, fn, device, output_path):
    activities = [torch.profiler.ProfilerActivity.CPU]
    if device.type == "cuda":
        activities.append(torch.profiler.ProfilerActivity.CUDA)

    with torch.profiler.profile(
        activities=activities,
        record_shapes=True,
        profile_memory=True,
        with_flops=True,
    ) as profiler:
        with torch.profiler.record_function(name):
            with nvtx_range(name, device):
                output = fn()
                synchronize(device)

    profiler.export_chrome_trace(str(output_path))
    sort_key = "self_cuda_time_total" if device.type == "cuda" else "self_cpu_time_total"
    print(profiler.key_averages().table(sort_by=sort_key, row_limit=15))
    return output


def capture_one_matmul(fn, device):
    if device.type != "cuda":
        raise RuntimeError("--capture-kernel 需要 CUDA 设备")
    with torch.inference_mode():
        for _ in range(5):
            output = fn()
        synchronize(device)
        torch.cuda.cudart().cudaProfilerStart()
        with nvtx_range("capture_matmul", device):
            output = fn()
            synchronize(device)
        torch.cuda.cudart().cudaProfilerStop()
    print(float(output.flatten()[0]))


def main():
    parser = argparse.ArgumentParser(description="通用 GPU 性能分析综合实验")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--mode", choices=["all", "launch", "memory", "matmul"], default="all")
    parser.add_argument("--elements", type=int, default=1_000_000)
    parser.add_argument("--matrix", type=int, default=512)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--iters", type=int, default=30)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--capture-kernel", action="store_true")
    parser.add_argument("--output", default="reports/benchmark.json")
    args = parser.parse_args()

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("请求了 CUDA，但 PyTorch 未检测到可用 CUDA GPU")
    device = torch.device(
        "cuda" if (args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available())) else "cpu"
    )
    if min(args.elements, args.matrix, args.steps, args.warmup, args.iters) <= 0:
        raise ValueError("尺寸、步骤与迭代参数必须大于 0")

    workloads = build_workloads(args, device)
    if args.capture_kernel:
        capture_one_matmul(workloads["matmul"][0], device)
        return

    selected = list(workloads) if args.mode == "all" else [args.mode]
    report = {
        "environment": environment(device),
        "config": vars(args),
        "results": {},
    }
    print(json.dumps(report["environment"], indent=2, ensure_ascii=False))

    for name in selected:
        baseline, optimized = workloads[name]
        with nvtx_range(f"{name}_baseline_benchmark", device):
            baseline_output, baseline_stats = timed(
                baseline, device, args.warmup, args.iters
            )
        item = {"baseline": baseline_stats}

        if optimized is not None:
            with nvtx_range(f"{name}_optimized_benchmark", device):
                optimized_output, optimized_stats = timed(
                    optimized, device, args.warmup, args.iters
                )
            item["optimized"] = optimized_stats
            item["correct"] = check_close(baseline_output, optimized_output)
            item["speedup_p50"] = baseline_stats["p50_ms"] / optimized_stats["p50_ms"]

        report["results"][name] = item
        print(name, json.dumps(item, indent=2, ensure_ascii=False))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.profile:
        profile_name = selected[0]
        trace_path = output_path.parent / "pytorch_trace.json"
        profile_once(
            f"{profile_name}_baseline_profile",
            workloads[profile_name][0],
            device,
            trace_path,
        )
        print(f"PyTorch trace: {trace_path}")


if __name__ == "__main__":
    main()
