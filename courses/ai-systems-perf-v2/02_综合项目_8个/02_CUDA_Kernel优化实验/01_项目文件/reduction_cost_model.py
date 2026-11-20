#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path


def estimate(elements: int, blocks: int, block_size: int) -> dict:
    if min(elements, blocks, block_size) <= 0:
        raise ValueError("elements、blocks、block-size 必须大于 0")
    if block_size % 32 != 0 or block_size > 1024:
        raise ValueError("block-size 必须是 32 的倍数且不超过 1024")

    warps_per_block = block_size // 32
    shared_steps = int(math.log2(block_size))
    return {
        "elements": elements,
        "blocks": blocks,
        "block_size": block_size,
        "baseline_global_atomics": elements,
        "optimized_global_atomics": blocks,
        "atomic_reduction_ratio": elements / blocks,
        "v1_shared_reduction_steps_per_block": shared_steps,
        "v1_barriers_per_block_approx": shared_steps,
        "v2_warp_shuffle_rounds": 5,
        "v2_warp_partial_values_per_block": warps_per_block,
        "minimum_input_bytes": elements * 4,
        "warning": "这是操作数量模型，不是 GPU 性能预测。",
    }


def main():
    parser = argparse.ArgumentParser(description="CUDA Reduction 成本模型")
    parser.add_argument("--elements", type=int, default=4_194_304)
    parser.add_argument("--blocks", type=int, default=256)
    parser.add_argument("--block-size", type=int, default=256)
    parser.add_argument("--output", default="reports/cost_model.json")
    args = parser.parse_args()

    result = estimate(args.elements, args.blocks, args.block_size)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
