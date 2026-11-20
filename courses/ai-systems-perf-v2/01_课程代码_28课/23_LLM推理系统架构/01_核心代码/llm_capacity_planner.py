#!/usr/bin/env python3
import argparse
from dataclasses import dataclass

GIB = 1024 ** 3


@dataclass
class Plan:
    weight_gib: float
    kv_kib_per_token: float
    fixed_gib: float
    kv_budget_gib: float
    max_kv_tokens: int
    target_tokens: int
    target_kv_gib: float
    total_gib: float
    fits: bool
    max_concurrency_at_avg_context: int


def build_plan(args: argparse.Namespace) -> Plan:
    # 原始权重估算；overhead 用于覆盖量化元数据、未量化层和 Runtime Buffer。
    raw_weight_bytes = args.params_b * 1e9 * args.weight_bits / 8
    weight_bytes = raw_weight_bytes * (1 + args.weight_overhead)

    kv_bytes_per_token = (
        2
        * args.layers
        * args.kv_heads
        * args.head_dim
        * args.kv_bits
        / 8
    )

    usable_bytes = args.gpu_gib * GIB * args.utilization
    fixed_bytes = weight_bytes + args.runtime_gib * GIB
    kv_budget_bytes = max(0.0, usable_bytes - fixed_bytes)
    max_kv_tokens = int(kv_budget_bytes // kv_bytes_per_token)

    avg_context = args.avg_prompt + args.avg_output
    target_tokens = args.concurrency * avg_context
    target_kv_bytes = target_tokens * kv_bytes_per_token
    total_bytes = fixed_bytes + target_kv_bytes
    max_concurrency = max_kv_tokens // avg_context if avg_context > 0 else 0

    return Plan(
        weight_gib=weight_bytes / GIB,
        kv_kib_per_token=kv_bytes_per_token / 1024,
        fixed_gib=fixed_bytes / GIB,
        kv_budget_gib=kv_budget_bytes / GIB,
        max_kv_tokens=max_kv_tokens,
        target_tokens=target_tokens,
        target_kv_gib=target_kv_bytes / GIB,
        total_gib=total_bytes / GIB,
        fits=total_bytes <= usable_bytes,
        max_concurrency_at_avg_context=max_concurrency,
    )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="LLM inference memory capacity planner")
    p.add_argument("--params-b", type=float, default=7.0)
    p.add_argument("--weight-bits", type=float, default=4.0)
    p.add_argument("--weight-overhead", type=float, default=0.15)
    p.add_argument("--layers", type=int, default=32)
    p.add_argument("--kv-heads", type=int, default=8)
    p.add_argument("--head-dim", type=int, default=128)
    p.add_argument("--kv-bits", type=float, default=16.0)
    p.add_argument("--gpu-gib", type=float, default=20.0)
    p.add_argument("--utilization", type=float, default=0.85)
    p.add_argument("--runtime-gib", type=float, default=2.0)
    p.add_argument("--avg-prompt", type=int, default=1024)
    p.add_argument("--avg-output", type=int, default=256)
    p.add_argument("--concurrency", type=int, default=32)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not (0 < args.utilization <= 1):
        raise ValueError("utilization must be in (0, 1]")
    if min(args.layers, args.kv_heads, args.head_dim) <= 0:
        raise ValueError("layers, kv_heads and head_dim must be positive")

    plan = build_plan(args)
    usable = args.gpu_gib * args.utilization
    print("=== LLM Inference Capacity Plan ===")
    print(f"GPU capacity              : {args.gpu_gib:.2f} GiB")
    print(f"Usable budget             : {usable:.2f} GiB")
    print(f"Estimated weights         : {plan.weight_gib:.2f} GiB")
    print(f"Weights + runtime fixed   : {plan.fixed_gib:.2f} GiB")
    print(f"KV cache per token        : {plan.kv_kib_per_token:.2f} KiB")
    print(f"KV budget                 : {plan.kv_budget_gib:.2f} GiB")
    print(f"Maximum resident KV tokens: {plan.max_kv_tokens:,}")
    print(f"Target resident tokens    : {plan.target_tokens:,}")
    print(f"Target KV cache           : {plan.target_kv_gib:.2f} GiB")
    print(f"Estimated total           : {plan.total_gib:.2f} GiB")
    print(f"Target fits budget        : {plan.fits}")
    print(
        "Max concurrency at average context "
        f"({args.avg_prompt + args.avg_output} tokens): "
        f"{plan.max_concurrency_at_avg_context}"
    )
    print("\nNote: this is a capacity estimate, not a performance guarantee.")


if __name__ == "__main__":
    main()
