#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


GIB = 1024 ** 3


def gib(value):
    return round(value / GIB, 3)


def main():
    parser = argparse.ArgumentParser(description="7B 训练容量与 MFU 规划器")
    parser.add_argument("--params", type=float, default=7e9)
    parser.add_argument("--gpus", type=int, default=2)
    parser.add_argument("--gpu-memory-gib", type=float, default=20.0)
    parser.add_argument("--safe-utilization", type=float, default=0.85)
    parser.add_argument("--micro-batch", type=int, default=1)
    parser.add_argument("--sequence-length", type=int, default=2048)
    parser.add_argument("--grad-accum", type=int, default=16)
    parser.add_argument("--data-parallel", type=int, default=2)
    parser.add_argument("--step-seconds", type=float, default=1.0)
    parser.add_argument("--peak-tflops-per-gpu", type=float)
    parser.add_argument("--output", default="reports/capacity.json")
    args = parser.parse_args()

    positive = [args.params, args.gpus, args.gpu_memory_gib, args.micro_batch,
                args.sequence_length, args.grad_accum, args.data_parallel,
                args.step_seconds]
    if any(value <= 0 for value in positive):
        raise ValueError("所有规模、时间与峰值参数必须大于 0")
    if not 0 < args.safe_utilization <= 1:
        raise ValueError("safe-utilization 必须位于 (0, 1]")
    if args.peak_tflops_per_gpu is not None and args.peak_tflops_per_gpu <= 0:
        raise ValueError("peak-tflops-per-gpu 必须大于 0")

    param_bytes = args.params * 2
    grad_bytes = args.params * 2
    master_bytes = args.params * 4
    adam_bytes = args.params * 8
    total_state = param_bytes + grad_bytes + master_bytes + adam_bytes
    ddp_per_gpu = total_state
    ideal_fsdp_per_gpu = total_state / args.data_parallel
    safe_capacity = args.gpu_memory_gib * GIB * args.safe_utilization

    tokens_per_step = (args.micro_batch * args.sequence_length *
                       args.grad_accum * args.data_parallel)
    flops_per_step = 6 * args.params * tokens_per_step
    achieved_tflops = flops_per_step / args.step_seconds / 1e12
    cluster_peak_tflops = (
        args.gpus * args.peak_tflops_per_gpu
        if args.peak_tflops_per_gpu is not None else None
    )
    mfu = (
        achieved_tflops / cluster_peak_tflops
        if cluster_peak_tflops is not None else None
    )

    result = {
        "parameters": args.params,
        "training_state_gib": {
            "parameters_bf16": gib(param_bytes),
            "gradients_bf16": gib(grad_bytes),
            "master_weights_fp32": gib(master_bytes),
            "adam_moments_fp32": gib(adam_bytes),
            "total_before_activations": gib(total_state),
        },
        "per_gpu_estimate_gib": {
            "ddp": gib(ddp_per_gpu),
            "ideal_full_shard": gib(ideal_fsdp_per_gpu),
            "safe_capacity": round(args.gpu_memory_gib * args.safe_utilization, 3),
        },
        "fits_before_activations": {
            "ddp": ddp_per_gpu <= safe_capacity,
            "ideal_full_shard": ideal_fsdp_per_gpu <= safe_capacity,
        },
        "workload": {
            "tokens_per_step": tokens_per_step,
            "tokens_per_second": tokens_per_step / args.step_seconds,
            "approx_flops_per_step": flops_per_step,
            "achieved_tflops": achieved_tflops,
            "cluster_peak_tflops": cluster_peak_tflops,
            "mfu": mfu,
        },
        "warning": (
            "静态状态估算不含激活、通信缓冲、临时张量、CUDA Context、"
            "碎片和峰值 All-Gather；MFU 依赖正确的同精度 Dense 峰值。"
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
