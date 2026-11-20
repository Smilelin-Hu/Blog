#!/usr/bin/env python3
import argparse
import platform
import sys

import torch


def parse_args():
    p = argparse.ArgumentParser(description="Naive cat vs preallocated KV append")
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--heads", type=int, default=8)
    p.add_argument("--steps", type=int, default=512)
    p.add_argument("--head-dim", type=int, default=64)
    p.add_argument("--dtype", choices=["fp16", "bf16", "fp32"], default="fp16")
    return p.parse_args()


def timed(fn):
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    result = fn()
    end.record()
    torch.cuda.synchronize()
    return result, start.elapsed_time(end)


def naive_cat(new_k, new_v):
    shape = (*new_k.shape[:2], 0, new_k.shape[-1])
    k = torch.empty(shape, device=new_k.device, dtype=new_k.dtype)
    v = torch.empty(shape, device=new_v.device, dtype=new_v.dtype)
    for step in range(new_k.shape[2]):
        k = torch.cat((k, new_k[:, :, step : step + 1, :]), dim=2)
        v = torch.cat((v, new_v[:, :, step : step + 1, :]), dim=2)
    return k, v


def preallocated(new_k, new_v):
    k = torch.empty_like(new_k)
    v = torch.empty_like(new_v)
    for step in range(new_k.shape[2]):
        k[:, :, step : step + 1, :].copy_(new_k[:, :, step : step + 1, :])
        v[:, :, step : step + 1, :].copy_(new_v[:, :, step : step + 1, :])
    return k, v


def run_case(name, fn, new_k, new_v):
    torch.cuda.empty_cache()
    base = torch.cuda.memory_allocated()
    torch.cuda.reset_peak_memory_stats()
    (k, v), elapsed_ms = timed(lambda: fn(new_k, new_v))
    peak_delta = torch.cuda.max_memory_allocated() - base
    checksum = (k.float().sum() + v.float().sum()).item()
    del k, v
    return elapsed_ms, peak_delta, checksum


def main():
    args = parse_args()
    if not torch.cuda.is_available():
        print("CUDA GPU not found. Run the Level 0 planner on this machine.")
        sys.exit(0)

    dtype = {
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
        "fp32": torch.float32,
    }[args.dtype]
    if dtype == torch.bfloat16 and not torch.cuda.is_bf16_supported():
        raise RuntimeError("BF16 is not supported by this GPU/PyTorch stack")

    device = torch.device("cuda")
    prop = torch.cuda.get_device_properties(0)
    torch.manual_seed(7)
    shape = (args.batch, args.heads, args.steps, args.head_dim)
    new_k = torch.randn(shape, device=device, dtype=dtype)
    new_v = torch.randn(shape, device=device, dtype=dtype)

    print("=== Environment ===")
    print(f"Python             : {platform.python_version()}")
    print(f"PyTorch            : {torch.__version__}")
    print(f"CUDA runtime       : {torch.version.cuda}")
    print(f"GPU                : {prop.name}")
    print(f"Compute capability : {prop.major}.{prop.minor}")
    print(f"VRAM               : {prop.total_memory / 1024**3:.2f} GiB")
    print(f"KV shape           : {shape}")
    print(f"dtype              : {dtype}")

    # 小规模预热，不计入正式结果。
    warm_k = new_k[:, :, :8, :]
    warm_v = new_v[:, :, :8, :]
    naive_cat(warm_k, warm_v)
    preallocated(warm_k, warm_v)
    torch.cuda.synchronize()

    naive_ms, naive_peak, naive_sum = run_case("naive", naive_cat, new_k, new_v)
    pre_ms, pre_peak, pre_sum = run_case("preallocated", preallocated, new_k, new_v)
    checksum_error = abs(naive_sum - pre_sum)

    print("\n=== Results ===")
    print(f"Naive torch.cat latency     : {naive_ms:.3f} ms")
    print(f"Preallocated latency        : {pre_ms:.3f} ms")
    print(f"Speedup                     : {naive_ms / pre_ms:.2f}x")
    print(f"Naive peak allocation delta : {naive_peak / 1024**2:.2f} MiB")
    print(f"Prealloc peak alloc delta   : {pre_peak / 1024**2:.2f} MiB")
    print(f"Checksum absolute error     : {checksum_error:.6f}")
    print("\nThis isolates KV append behavior; it is not a PagedAttention benchmark.")


if __name__ == "__main__":
    main()
