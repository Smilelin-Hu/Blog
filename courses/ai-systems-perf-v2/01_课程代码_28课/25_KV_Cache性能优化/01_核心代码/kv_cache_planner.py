#!/usr/bin/env python3
import argparse
import math
import random

GIB = 1024 ** 3


def kv_bytes_per_token(layers, kv_heads, head_dim, kv_bits):
    return 2 * layers * kv_heads * head_dim * kv_bits / 8


def parse_args():
    p = argparse.ArgumentParser(description="KV cache capacity and paging planner")
    p.add_argument("--layers", type=int, default=32)
    p.add_argument("--kv-heads", type=int, default=8)
    p.add_argument("--head-dim", type=int, default=128)
    p.add_argument("--kv-bits", type=float, default=16)
    p.add_argument("--kv-budget-gib", type=float, default=12)
    p.add_argument("--requests", type=int, default=32)
    p.add_argument("--min-seq", type=int, default=128)
    p.add_argument("--max-seq", type=int, default=4096)
    p.add_argument("--block-size", type=int, default=16)
    p.add_argument("--shared-prefix", type=int, default=512)
    p.add_argument("--prefix-users", type=int, default=16)
    p.add_argument("--seed", type=int, default=7)
    return p.parse_args()


def main():
    args = parse_args()
    if min(args.layers, args.kv_heads, args.head_dim, args.block_size) <= 0:
        raise ValueError("model dimensions and block size must be positive")
    if args.min_seq <= 0 or args.min_seq > args.max_seq:
        raise ValueError("require 0 < min_seq <= max_seq")

    rng = random.Random(args.seed)
    lengths = [rng.randint(args.min_seq, args.max_seq) for _ in range(args.requests)]
    per_token = kv_bytes_per_token(
        args.layers, args.kv_heads, args.head_dim, args.kv_bits
    )
    useful_tokens = sum(lengths)

    contiguous_tokens = args.requests * args.max_seq
    paged_tokens = sum(
        math.ceil(length / args.block_size) * args.block_size for length in lengths
    )
    blocks = paged_tokens // args.block_size

    reusable_prefix = (args.shared_prefix // args.block_size) * args.block_size
    prefix_users = min(args.requests, max(0, args.prefix_users))
    saved_prefix_tokens = max(0, prefix_users - 1) * reusable_prefix

    budget_bytes = args.kv_budget_gib * GIB
    max_tokens = int(budget_bytes // per_token)

    print("=== KV Cache Plan ===")
    print(f"KV per token                  : {per_token / 1024:.2f} KiB")
    print(f"KV token capacity             : {max_tokens:,}")
    print(f"Requests / sequence range     : {args.requests} / {args.min_seq}-{args.max_seq}")
    print(f"Useful resident tokens        : {useful_tokens:,}")
    print(f"Contiguous reserved tokens    : {contiguous_tokens:,}")
    print(f"Paged allocated tokens        : {paged_tokens:,}")
    print(f"Paged blocks                  : {blocks:,} x {args.block_size} tokens")
    print(f"Contiguous efficiency         : {useful_tokens / contiguous_tokens * 100:.2f}%")
    print(f"Paged efficiency              : {useful_tokens / paged_tokens * 100:.2f}%")
    print(f"Contiguous KV                 : {contiguous_tokens * per_token / GIB:.2f} GiB")
    print(f"Paged KV                      : {paged_tokens * per_token / GIB:.2f} GiB")
    print(f"Fits paged workload           : {paged_tokens <= max_tokens}")
    print(f"Block-aligned reusable prefix : {reusable_prefix:,} tokens/request")
    print(f"Prefix tokens saved           : {saved_prefix_tokens:,}")
    print(f"Prefix KV bytes avoided       : {saved_prefix_tokens * per_token / GIB:.2f} GiB")
    print("\nThis is a capacity model, not an attention-latency benchmark.")


if __name__ == "__main__":
    main()
