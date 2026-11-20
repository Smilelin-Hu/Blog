#!/usr/bin/env python3
import argparse
import math


def ring_allreduce_us(size_bytes, ranks, alpha_us, bandwidth_gbs):
    steps = 2 * (ranks - 1)
    traffic = 2 * (ranks - 1) / ranks * size_bytes
    transfer_us = traffic / (bandwidth_gbs * 1e9) * 1e6
    return steps * alpha_us + transfer_us


def tree_allreduce_us(size_bytes, ranks, alpha_us, bandwidth_gbs,
                      tree_bandwidth_factor):
    levels = math.ceil(math.log2(ranks)) if ranks > 1 else 0
    # 教学模型：上下树各 levels 轮；有效带宽由 factor 表示。
    transfer_us = 2 * size_bytes / (
        bandwidth_gbs * tree_bandwidth_factor * 1e9
    ) * 1e6
    return 2 * levels * alpha_us + transfer_us


def parse_sizes(text):
    values = []
    for item in text.split(","):
        value = float(item.strip())
        if value <= 0:
            raise ValueError("消息大小必须为正数")
        values.append(value)
    return values


def main():
    p = argparse.ArgumentParser(description="NCCL All-Reduce 教学成本模型")
    p.add_argument("--ranks", type=int, default=8)
    p.add_argument("--bandwidth-gbs", type=float, default=25.0,
                   help="假设的单向有效链路带宽 GB/s")
    p.add_argument("--alpha-us", type=float, default=4.0,
                   help="每个通信阶段的启动延迟 us")
    p.add_argument("--tree-bandwidth-factor", type=float, default=0.65)
    p.add_argument("--sizes-mib", default="0.001,0.01,0.1,1,16,64,256")
    args = p.parse_args()

    if args.ranks < 2:
        raise ValueError("至少需要 2 个 Rank")
    if args.bandwidth_gbs <= 0 or args.alpha_us < 0:
        raise ValueError("带宽必须为正，延迟不能为负")
    if not 0 < args.tree_bandwidth_factor <= 1:
        raise ValueError("tree-bandwidth-factor 必须位于 (0, 1]")

    sizes = parse_sizes(args.sizes_mib)
    print(f"ranks={args.ranks} bandwidth={args.bandwidth_gbs}GB/s "
          f"alpha={args.alpha_us}us")
    print(f"{'MiB':>10} {'Ring_us':>12} {'Tree_us':>12} {'ModelPick':>12}")
    crossover = None
    for size_mib in sizes:
        size_bytes = size_mib * 1024 ** 2
        ring = ring_allreduce_us(
            size_bytes, args.ranks, args.alpha_us, args.bandwidth_gbs
        )
        tree = tree_allreduce_us(
            size_bytes, args.ranks, args.alpha_us,
            args.bandwidth_gbs, args.tree_bandwidth_factor
        )
        pick = "Ring" if ring < tree else "Tree"
        if pick == "Ring" and crossover is None:
            crossover = size_mib
        print(f"{size_mib:10.3f} {ring:12.3f} {tree:12.3f} {pick:>12}")

    print("\n注意：这是理解 alpha/B 权衡的教学模型，不代表 NCCL 选型器。")
    print("模型中的首次 Ring 优势消息大小:", crossover)


if __name__ == "__main__":
    main()
