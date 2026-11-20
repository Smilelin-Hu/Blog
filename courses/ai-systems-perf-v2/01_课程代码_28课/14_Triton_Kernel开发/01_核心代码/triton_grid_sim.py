#!/usr/bin/env python3
import argparse
import json
import math


def cdiv(x, y):
    return (x + y - 1) // y


def simulated_add(x, y, block_size):
    if len(x) != len(y):
        raise ValueError("x and y length mismatch")
    n = len(x)
    grid = cdiv(n, block_size)
    out = [None] * n
    records = []

    for pid in range(grid):
        block_start = pid * block_size
        offsets = [block_start + lane for lane in range(block_size)]
        mask = [offset < n for offset in offsets]
        active_offsets = []
        for offset, active in zip(offsets, mask):
            if active:
                out[offset] = x[offset] + y[offset]
                active_offsets.append(offset)
        records.append({
            "program_id": pid,
            "block_start": block_start,
            "active_count": sum(mask),
            "masked_count": block_size - sum(mask),
            "active_range": (
                [active_offsets[0], active_offsets[-1]]
                if active_offsets else None
            ),
        })
    return out, records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=37)
    parser.add_argument("--block-size", type=int, default=16)
    args = parser.parse_args()
    if args.n <= 0 or args.block_size <= 0:
        raise SystemExit("n and block-size must be positive")

    x = [float(i) for i in range(args.n)]
    y = [float(2 * i + 1) for i in range(args.n)]
    out, records = simulated_add(x, y, args.block_size)
    reference = [a + b for a, b in zip(x, y)]
    if out != reference:
        raise AssertionError("simulation result mismatch")

    grid = cdiv(args.n, args.block_size)
    total_lanes = grid * args.block_size
    report = {
        "config": vars(args),
        "grid_size": grid,
        "total_logical_lanes": total_lanes,
        "active_lanes": args.n,
        "masked_lanes": total_lanes - args.n,
        "tail_efficiency": args.n / total_lanes,
        "programs": records,
        "correctness": True,
        "output_head": out[: min(8, len(out))],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
