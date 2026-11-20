#!/usr/bin/env python3
import argparse
import time


def tiny_work(x, rounds):
    for i in range(rounds):
        x = (x * 1664525 + 1013904223 + i) & 0xFFFFFFFF
    return x


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--steps", type=int, default=20000)
    p.add_argument("--nodes", type=int, default=32)
    p.add_argument("--work-rounds", type=int, default=2)
    p.add_argument("--launch-us", type=float, default=3.0)
    args = p.parse_args()
    if min(args.steps, args.nodes, args.work_rounds) < 1 or args.launch_us < 0:
        raise SystemExit("参数必须为正数，launch-us 不能为负数")

    # 用算术循环近似每个节点的计算；固定 launch 成本用公式计入，
    # 避免 time.sleep 在微秒区间误差过大。
    x = 1
    t0 = time.perf_counter()
    for _ in range(args.steps):
        for _ in range(args.nodes):
            x = tiny_work(x, args.work_rounds)
    compute_s = time.perf_counter() - t0

    eager_launch_s = args.steps * args.nodes * args.launch_us / 1e6
    graph_launch_s = args.steps * args.launch_us / 1e6
    eager_total = compute_s + eager_launch_s
    graph_total = compute_s + graph_launch_s

    print(f"checksum={x}")
    print(f"compute_s={compute_s:.6f}")
    print(f"eager_model_s={eager_total:.6f}")
    print(f"graph_model_s={graph_total:.6f}")
    print(f"modeled_speedup={eager_total / graph_total:.3f}x")
    print(f"launch_overhead_saved_s={eager_launch_s - graph_launch_s:.6f}")


if __name__ == "__main__":
    main()
