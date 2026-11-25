#!/usr/bin/env python3
import argparse
import math
import random
import statistics


def route(tokens, experts, topk, skew, capacity_factor, penalty, seed):
    rng = random.Random(seed)
    loads = [0] * experts
    expected = tokens * topk / experts
    capacity = math.ceil(capacity_factor * expected)
    dropped = 0

    for _ in range(tokens):
        # 低编号专家更热门，用于模拟真实工作负载倾斜。
        raw = [rng.gauss(0, 1) - skew * e / max(1, experts - 1)
               for e in range(experts)]
        if penalty == 0.0:
            # 模型原始 Top-K：容量满时丢弃，不偷偷改选其他专家。
            selected = sorted(range(experts), key=lambda e: raw[e], reverse=True)[:topk]
            for e in selected:
                if loads[e] < capacity:
                    loads[e] += 1
                else:
                    dropped += 1
            continue

        selected = set()
        for _ in range(topk):
            candidates = []
            for e in range(experts):
                if e in selected or loads[e] >= capacity:
                    continue
                balanced_score = raw[e] - penalty * loads[e] / max(1.0, expected)
                candidates.append((balanced_score, e))
            if not candidates:
                dropped += 1
                continue
            _, e = max(candidates)
            selected.add(e)
            loads[e] += 1
    return loads, dropped, capacity


def summarize(name, loads, dropped, capacity):
    mean = statistics.mean(loads)
    cv = statistics.pstdev(loads) / mean if mean else 0.0
    ratio = max(loads) / mean if mean else 0.0
    efficiency = mean / max(loads) if max(loads) else 0.0
    print(f"\n[{name}]")
    print("loads=", loads)
    print(f"capacity={capacity} dropped_copies={dropped}")
    print(f"max/mean={ratio:.3f} CV={cv:.3f}")
    print(f"balance_efficiency_upper_bound={efficiency:.3f}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tokens", type=int, default=4096)
    p.add_argument("--experts", type=int, default=16)
    p.add_argument("--topk", type=int, default=2)
    p.add_argument("--skew", type=float, default=1.5)
    p.add_argument("--capacity-factor", type=float, default=1.25)
    p.add_argument("--balance-penalty", type=float, default=1.5)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    if a.topk > a.experts:
        p.error("topk 不能大于 experts")

    base = route(a.tokens, a.experts, a.topk, a.skew,
                 a.capacity_factor, penalty=0.0, seed=a.seed)
    balanced = route(a.tokens, a.experts, a.topk, a.skew,
                     a.capacity_factor, penalty=a.balance_penalty, seed=a.seed)
    summarize("model_topk_with_capacity", *base)
    summarize("capacity_aware_simulation", *balanced)
    print("\n注意：第二组修改了路由分数，只用于系统容量学习，")
    print("不能直接替换真实模型 Router，否则可能改变输出质量。")


if __name__ == "__main__":
    main()
