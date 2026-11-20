#!/usr/bin/env python3
import argparse
import json
import math
import random
import statistics
from pathlib import Path


def percentile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return values[low]
    return values[low] * (high - position) + values[high] * (position - low)


def capacity(args):
    bytes_per_token = 2 * args.layers * args.kv_heads * args.head_dim * args.dtype_bytes
    usable_bytes = args.kv_memory_gib * (1024 ** 3) * args.safe_utilization
    token_capacity = math.floor(usable_bytes / bytes_per_token)
    request_capacity = math.floor(token_capacity / args.tokens_per_request)
    return {
        "bytes_per_token": bytes_per_token,
        "kib_per_token": bytes_per_token / 1024,
        "usable_kv_gib": args.kv_memory_gib * args.safe_utilization,
        "theoretical_token_capacity": token_capacity,
        "theoretical_request_capacity": request_capacity,
        "warning": "不含 Block 元数据、工作区、图捕获、Allocator 和运行峰值。",
    }


def fragmentation(args):
    rng = random.Random(args.seed)
    lengths = [rng.randint(args.min_tokens, args.max_tokens) for _ in range(args.requests)]
    contiguous_reserved = args.requests * args.max_tokens
    paged_reserved = sum(math.ceil(length / args.block_size) * args.block_size
                         for length in lengths)
    used = sum(lengths)
    return {
        "requests": args.requests,
        "block_size": args.block_size,
        "used_tokens": used,
        "contiguous_reserved_tokens": contiguous_reserved,
        "paged_reserved_tokens": paged_reserved,
        "contiguous_utilization": used / contiguous_reserved,
        "paged_utilization": used / paged_reserved,
        "paged_internal_fragmentation_tokens": paged_reserved - used,
        "length_p50": percentile(lengths, 0.50),
        "length_p95": percentile(lengths, 0.95),
        "mean_length": statistics.mean(lengths),
        "warning": "模拟器不包含真实请求生命周期、Prefix 共享、抢占或 Kernel 成本。",
    }


def main():
    parser = argparse.ArgumentParser(description="KV Cache 容量与分页实验")
    parser.add_argument("--mode", choices=["capacity", "fragmentation"], required=True)
    parser.add_argument("--layers", type=int, default=32)
    parser.add_argument("--kv-heads", type=int, default=8)
    parser.add_argument("--head-dim", type=int, default=128)
    parser.add_argument("--dtype-bytes", type=float, default=2)
    parser.add_argument("--kv-memory-gib", type=float, default=8)
    parser.add_argument("--safe-utilization", type=float, default=0.90)
    parser.add_argument("--tokens-per-request", type=int, default=4096)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--min-tokens", type=int, default=32)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--block-size", type=int, default=16)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", default="reports/kv_cache.json")
    args = parser.parse_args()
    numeric = [args.layers, args.kv_heads, args.head_dim, args.dtype_bytes,
               args.kv_memory_gib, args.tokens_per_request, args.requests,
               args.min_tokens, args.max_tokens, args.block_size]
    if any(value <= 0 for value in numeric):
        raise ValueError("容量与负载参数必须大于 0")
    if args.min_tokens > args.max_tokens:
        raise ValueError("min-tokens 不能大于 max-tokens")
    if not 0 < args.safe_utilization <= 1:
        raise ValueError("safe-utilization 必须位于 (0, 1]")

    result = capacity(args) if args.mode == "capacity" else fragmentation(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
