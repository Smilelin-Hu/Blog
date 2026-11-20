#!/usr/bin/env python3
import argparse
import json
import os
import time

import torch
from torch.utils.cpp_extension import load_inline


CPP_SOURCE = r"""
torch::Tensor baseline_cuda(torch::Tensor x, torch::Tensor y, double bias);
torch::Tensor fused_cuda(torch::Tensor x, torch::Tensor y, double bias);
"""


CUDA_SOURCE = r"""
#include <torch/extension.h>
#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAException.h>
#include <cuda.h>
#include <cuda_runtime.h>

__global__ void multiply_kernel(
    const float* x, const float* y, float* out, int64_t n) {
    int64_t i = static_cast<int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (i < n) out[i] = x[i] * y[i];
}

__global__ void bias_kernel(
    const float* x, float bias, float* out, int64_t n) {
    int64_t i = static_cast<int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (i < n) out[i] = x[i] + bias;
}

__global__ void relu_kernel(const float* x, float* out, int64_t n) {
    int64_t i = static_cast<int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (i < n) out[i] = x[i] > 0.0f ? x[i] : 0.0f;
}

__global__ void fused_kernel(
    const float* x, const float* y, float bias, float* out, int64_t n) {
    int64_t i = static_cast<int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (i < n) {
        float value = x[i] * y[i] + bias;
        out[i] = value > 0.0f ? value : 0.0f;
    }
}

void check_inputs(const torch::Tensor& x, const torch::Tensor& y) {
    TORCH_CHECK(x.is_cuda() && y.is_cuda(), "x and y must be CUDA tensors");
    TORCH_CHECK(x.scalar_type() == torch::kFloat32, "x must be float32");
    TORCH_CHECK(y.scalar_type() == torch::kFloat32, "y must be float32");
    TORCH_CHECK(x.is_contiguous() && y.is_contiguous(), "tensors must be contiguous");
    TORCH_CHECK(x.sizes() == y.sizes(), "x and y must have the same shape");
    TORCH_CHECK(x.get_device() == y.get_device(), "x and y must be on one GPU");
}

torch::Tensor baseline_cuda(torch::Tensor x, torch::Tensor y, double bias) {
    check_inputs(x, y);
    auto tmp1 = torch::empty_like(x);
    auto tmp2 = torch::empty_like(x);
    auto out = torch::empty_like(x);
    const int threads = 256;
    const int64_t n = x.numel();
    const int blocks = static_cast<int>((n + threads - 1) / threads);
    cudaStream_t stream = at::cuda::getCurrentCUDAStream();

    multiply_kernel<<<blocks, threads, 0, stream>>>(
        x.data_ptr<float>(), y.data_ptr<float>(), tmp1.data_ptr<float>(), n);
    bias_kernel<<<blocks, threads, 0, stream>>>(
        tmp1.data_ptr<float>(), static_cast<float>(bias), tmp2.data_ptr<float>(), n);
    relu_kernel<<<blocks, threads, 0, stream>>>(
        tmp2.data_ptr<float>(), out.data_ptr<float>(), n);
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    return out;
}

torch::Tensor fused_cuda(torch::Tensor x, torch::Tensor y, double bias) {
    check_inputs(x, y);
    auto out = torch::empty_like(x);
    const int threads = 256;
    const int64_t n = x.numel();
    const int blocks = static_cast<int>((n + threads - 1) / threads);
    cudaStream_t stream = at::cuda::getCurrentCUDAStream();

    fused_kernel<<<blocks, threads, 0, stream>>>(
        x.data_ptr<float>(), y.data_ptr<float>(), static_cast<float>(bias),
        out.data_ptr<float>(), n);
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    return out;
}
"""


def load_extension(verbose):
    return load_inline(
        name="fusion_lab_ext_v1",
        cpp_sources=CPP_SOURCE,
        cuda_sources=CUDA_SOURCE,
        functions=["baseline_cuda", "fused_cuda"],
        extra_cflags=["-O3"],
        extra_cuda_cflags=["-O3", "--use_fast_math"],
        with_cuda=True,
        verbose=verbose,
    )


def benchmark(fn, x, y, bias, warmup, repeat):
    for _ in range(warmup):
        out = fn(x, y, bias)
        del out
    torch.cuda.synchronize()

    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    wall_start = time.perf_counter()
    start.record()
    for _ in range(repeat):
        out = fn(x, y, bias)
        del out
    end.record()
    end.synchronize()
    return {
        "cuda_event_ms": start.elapsed_time(end) / repeat,
        "host_wall_ms": (time.perf_counter() - wall_start) * 1e3 / repeat,
    }


def peak_allocation(fn, x, y, bias):
    torch.cuda.empty_cache()
    torch.cuda.synchronize()
    base = torch.cuda.memory_allocated()
    torch.cuda.reset_peak_memory_stats()
    out = fn(x, y, bias)
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
    parser.add_argument("--verbose-build", action="store_true")
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("未检测到 CUDA GPU；请运行 Level 0")
    if args.n <= 0 or args.warmup < 0 or args.repeat <= 0:
        raise SystemExit("参数无效")

    ext = load_extension(args.verbose_build)
    device = torch.device("cuda")
    props = torch.cuda.get_device_properties(device)
    torch.manual_seed(2026)
    torch.cuda.manual_seed_all(2026)
    x = torch.randn(args.n, device=device, dtype=torch.float32)
    y = torch.randn_like(x)

    reference = torch.relu(x * y + args.bias)
    base_out = ext.baseline_cuda(x, y, args.bias)
    fused_out = ext.fused_cuda(x, y, args.bias)
    base_error = (reference - base_out).abs().max().item()
    fused_error = (reference - fused_out).abs().max().item()
    if not torch.allclose(reference, base_out, rtol=1e-5, atol=1e-6):
        raise AssertionError(f"baseline mismatch: {base_error}")
    if not torch.allclose(reference, fused_out, rtol=1e-5, atol=1e-6):
        raise AssertionError(f"fused mismatch: {fused_error}")
    del reference, base_out, fused_out
    torch.cuda.synchronize()

    baseline_stats = benchmark(
        ext.baseline_cuda, x, y, args.bias, args.warmup, args.repeat
    )
    fused_stats = benchmark(
        ext.fused_cuda, x, y, args.bias, args.warmup, args.repeat
    )
    baseline_peak = peak_allocation(ext.baseline_cuda, x, y, args.bias)
    fused_peak = peak_allocation(ext.fused_cuda, x, y, args.bias)

    bytes_unfused = args.n * 28
    bytes_fused = args.n * 12
    report = {
        "environment": {
            "torch": torch.__version__,
            "torch_cuda": torch.version.cuda,
            "device": torch.cuda.get_device_name(device),
            "compute_capability": [props.major, props.minor],
            "total_memory_gib": props.total_memory / 2**30,
        },
        "config": vars(args),
        "correctness": {
            "baseline_max_abs_error": base_error,
            "fused_max_abs_error": fused_error,
        },
        "model": {
            "unfused_useful_bytes": bytes_unfused,
            "fused_useful_bytes": bytes_fused,
            "theoretical_traffic_reduction": bytes_unfused / bytes_fused,
        },
        "baseline": {
            "timing": baseline_stats,
            "peak_incremental_allocation_mib": baseline_peak / 2**20,
        },
        "fused": {
            "timing": fused_stats,
            "peak_incremental_allocation_mib": fused_peak / 2**20,
        },
        "speedup_by_cuda_event": (
            baseline_stats["cuda_event_ms"] / fused_stats["cuda_event_ms"]
        ),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
