#!/usr/bin/env python3
"""教学模拟器：计算简化 Segment 和 Shared Bank 映射，不模拟真实 Cache/性能。"""

from __future__ import annotations

import argparse
import json
from collections import Counter


def global_transactions(warp_size: int, word_bytes: int, segment_bytes: int,
                        stride_words: int, offset_bytes: int) -> dict:
    addresses = [offset_bytes + lane * stride_words * word_bytes
                 for lane in range(warp_size)]
    segments = [address // segment_bytes for address in addresses]
    unique_segments = sorted(set(segments))
    requested = warp_size * word_bytes
    transferred = len(unique_segments) * segment_bytes
    return {
        "stride_words": stride_words,
        "offset_bytes": offset_bytes,
        "addresses_first_8": addresses[:8],
        "unique_segments": len(unique_segments),
        "requested_bytes": requested,
        "modeled_transferred_bytes": transferred,
        "modeled_efficiency": round(requested / transferred, 4),
    }


def shared_banks(warp_size: int, banks: int, word_stride: int,
                 same_address: bool = False) -> dict:
    words = [0 if same_address else lane * word_stride
             for lane in range(warp_size)]
    bank_ids = [word % banks for word in words]
    counts = Counter(bank_ids)
    if same_address:
        conflict_degree = 1
        behavior = "broadcast"
    else:
        conflict_degree = max(counts.values())
        behavior = "conflict-free" if conflict_degree == 1 else f"{conflict_degree}-way conflict"
    return {
        "word_stride": word_stride,
        "bank_ids": bank_ids,
        "bank_histogram": dict(sorted(counts.items())),
        "modeled_conflict_degree": conflict_degree,
        "behavior": behavior,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--warp-size", type=int, default=32)
    p.add_argument("--word-bytes", type=int, default=4)
    p.add_argument("--segment-bytes", type=int, default=32)
    args = p.parse_args()

    global_cases = [
        global_transactions(args.warp_size, args.word_bytes,
                            args.segment_bytes, stride, offset)
        for stride, offset in [(1, 0), (1, 4), (2, 0), (8, 0), (32, 0)]
    ]
    bank_cases = [
        shared_banks(args.warp_size, 32, stride)
        for stride in (1, 2, 16, 32, 33)
    ]
    bank_cases.append(shared_banks(args.warp_size, 32, 0, same_address=True))

    print(json.dumps({
        "global_cases": global_cases,
        "shared_bank_cases": bank_cases,
        "warning": (
            "Simplified model only. Real transactions depend on architecture, "
            "access width, active mask, cache, ECC and instruction semantics."
        ),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
