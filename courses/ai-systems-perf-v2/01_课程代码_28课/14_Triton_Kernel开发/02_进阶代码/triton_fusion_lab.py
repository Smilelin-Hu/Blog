#!/usr/bin/env python3
import argparse
import json
import time

import torch
import triton
import triton.language as tl


AUTOTUNE_CONFIGS = [
    triton.Config({"BLOCK_SIZE": 256}, num_warps=4),
    triton.Config({"BLOCK_SIZE": 512}, num_warps=4),
    triton.Config({"BLOCK_SIZE": 1024}, num_warps=8),
]


@triton.autotune(configs=AUTOTUNE_CONFIGS, key=["n_elements"])
@triton.jit
def fused_mul_bias_relu_kernel(
    x_ptr,
    y_ptr,
    out_ptr,
    n_elements,
    bias,
    BLOCK_SIZE: tl.constexpr,
):
    pid = tl.program_id(axis=0)
    offsets = pid * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
    mask = offsets < n_elements
    x = tl.load(x_ptr + offsets, mask=mask, other=0.0)
    y = tl.load(y_ptr + offsets, mask=mask, other=0.0)
    value = x * y + bias
    output = tl.where(value > 0.0, value, 0.0)
    tl.store(out_ptr + offsets, output, mask=mask)


def triton_fused(x, y, bias):
    if not x.is_cuda or not y.is_cuda:
        raise ValueError("x and y must be CUDA tensors")
    if x.dtype != torch.float32 or y.dtype != torch.float32:
        raise ValueError("this lab supports float32 only")
    if not x.is_contiguous() or not y.is_contiguous():
        raise ValueError("this lab requires contiguous tensors")
    if x.shape != y.shape or x.device != y.device:
        raise ValueError("shape and device must match")

    out = torch.empty_like(x)
    n_elements = out.numel()
    grid = lambda meta: (triton.cdiv(n_elements, meta["BLOCK_SIZE"]),)
    fused_mul_bias_relu_kernel[grid](x, y, out, n_elements, bias)
    return out


def torch_reference(x, y, bias):
    return torch.relu(x * y + bias)


def benchmark(fn, warmup, repeat):
    for _ in range(warmup):
        out = fn()
        del out
    torch.cuda.synchronize()

    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    wall_start = time.perf_counter()
    start.record()
    for _ in range(repeat):
        out = fn()
        del out
    end.record()
    end.synchronize()
    return {
        "cuda_event_ms": start.elapsed_time(end) / repeat,
        "host_wall_ms": (time.perf_counter() - wall_start) * 1e3 / repeat,
    }


def peak_allocation(fn):
    torch.cuda.empty_cache()
    torch.cuda.synchronize()
    base = torch.cuda.memory_allocated()
    torch.cuda.reset_peak_memory_stats()
    out = fn()
    torch.cuda.synchronize()
    peak_delta = torch.cuda.max_memory_allocated() - base
    del out
    return peak_delta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=16_777_216)
    parser.add_argument("--bias", type=float, default=-0.25)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--repeat", type=int, default=50)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("未检测到 CUDA GPU；请先运行 Level 0")
    if args.n <= 0 or args.warmup < 0 or args.repeat <= 0:
        raise SystemExit("invalid arguments")

    device = torch.device("cuda")
    props = torch.cuda.get_device_properties(device)
    torch.manual_seed(2026)
    torch.cuda.manual_seed_all(2026)
    x = torch.randn(args.n, device=device, dtype=torch.float32)
    y = torch.randn_like(x)

    reference = torch_reference(x, y, args.bias)
    candidate = triton_fused(x, y, args.bias)
    max_abs_error = (reference - candidate).abs().max().item()
    if not torch.allclose(reference, candidate, rtol=1e-5, atol=1e-6):
        raise AssertionError(f"Triton mismatch: {max_abs_error}")
    del reference, candidate
    torch.cuda.synchronize()

    torch_fn = lambda: torch_reference(x, y, args.bias)
    triton_fn = lambda: triton_fused(x, y, args.bias)

    # 上面的正确性调用已经触发 JIT/Autotune；正式计时不含首次编译。
    torch_stats = benchmark(torch_fn, args.warmup, args.repeat)
    triton_stats = benchmark(triton_fn, args.warmup, args.repeat)
    torch_peak = peak_allocation(torch_fn)
    triton_peak = peak_allocation(triton_fn)

    useful_bytes = args.n * 12
    triton_seconds = triton_stats["cuda_event_ms"] / 1e3
    report = {
        "environment": {
            "torch": torch.__version__,
            "triton": triton.__version__,
            "torch_cuda": torch.version.cuda,
            "device": torch.cuda.get_device_name(device),
            "compute_capability": [props.major, props.minor],
            "total_memory_gib": props.total_memory / 2**30,
        },
        "config": vars(args),
        "correctness": {"allclose": True, "max_abs_error": max_abs_error},
        "torch_eager": {
            "timing": torch_stats,
            "peak_incremental_allocation_mib": torch_peak / 2**20,
        },
        "triton_fused": {
            "timing": triton_stats,
            "peak_incremental_allocation_mib": triton_peak / 2**20,
            "modeled_effective_gbps": useful_bytes / triton_seconds / 1e9,
        },
        "speedup_by_cuda_event": (
            torch_stats["cuda_event_ms"] / triton_stats["cuda_event_ms"]
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
