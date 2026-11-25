#!/usr/bin/env python3
"""在 CPU 上模拟一维 CUDA Grid-stride 索引，不模拟 GPU 性能。"""

from __future__ import annotations

import argparse
import json


def simulate(n: int, blocks: int, threads: int) -> dict:
    if n <= 0 or blocks <= 0 or threads <= 0:
        raise ValueError("n, blocks, threads must all be positive")
    stride = blocks * threads
    owners = [[] for _ in range(n)]
    work_per_thread = []

    for block_idx in range(blocks):
        for thread_idx in range(threads):
            global_idx = block_idx * threads + thread_idx
            count = 0
            i = global_idx
            while i < n:
                owners[i].append((block_idx, thread_idx))
                count += 1
                i += stride
            work_per_thread.append(count)

    missing = [i for i, x in enumerate(owners) if not x]
    duplicated = [i for i, x in enumerate(owners) if len(x) != 1]
    active_threads = sum(x > 0 for x in work_per_thread)
    total_threads = blocks * threads
    return {
        "n": n,
        "blocks": blocks,
        "threads_per_block": threads,
        "logical_threads": total_threads,
        "grid_stride": stride,
        "active_threads": active_threads,
        "tail_idle_threads": total_threads - active_threads,
        "min_items_per_thread": min(work_per_thread),
        "max_items_per_thread": max(work_per_thread),
        "missing_indices": missing,
        "non_unique_indices": duplicated,
        "correct_exactly_once": not missing and not duplicated,
        "first_assignments": {
            str(i): owners[i] for i in range(min(n, 16))
        },
        "warning": "This validates mapping only; it cannot simulate warp scheduling, memory transactions, or performance.",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=1003)
    p.add_argument("--threads", type=int, default=256)
    p.add_argument("--blocks", type=int, default=4)
    args = p.parse_args()
    print(json.dumps(simulate(args.n, args.blocks, args.threads),
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
