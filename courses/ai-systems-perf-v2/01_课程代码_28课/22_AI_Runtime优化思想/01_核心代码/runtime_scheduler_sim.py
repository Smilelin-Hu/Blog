#!/usr/bin/env python3
import argparse
import math
import random
import statistics


def percentile(values, q):
    values = sorted(values)
    pos = (len(values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)


def make_arrivals(count, rate, seed):
    rng = random.Random(seed)
    now = 0.0
    arrivals = []
    for _ in range(count):
        now += rng.expovariate(rate) * 1000.0
        arrivals.append(now)
    return arrivals


def simulate(arrivals, max_batch, max_wait_ms, fixed_ms, per_item_ms, slo_ms):
    pending = []
    latencies = []
    now = 0.0
    index = 0
    batches = []

    while index < len(arrivals) or pending:
        if not pending and index < len(arrivals):
            now = max(now, arrivals[index])
        # 先接收 Server 忙碌期间已经到达的请求。
        while index < len(arrivals) and arrivals[index] <= now:
            pending.append(arrivals[index])
            index += 1

        # 若尚未满批，最多等到队首请求的 max_wait 截止时间。
        deadline = max(now, pending[0] + max_wait_ms)
        while (index < len(arrivals) and len(pending) < max_batch
               and arrivals[index] <= deadline):
            pending.append(arrivals[index])
            index += 1

        if len(pending) >= max_batch:
            start = max(now, pending[max_batch - 1])
        else:
            start = deadline

        batch = pending[:max_batch]
        del pending[:max_batch]
        service = fixed_ms + per_item_ms * len(batch)
        now = start + service
        batches.append(len(batch))
        latencies.extend(now - arrival for arrival in batch)

    elapsed_s = (now - arrivals[0]) / 1000.0
    return {
        "throughput": len(arrivals) / elapsed_s,
        "p50": percentile(latencies, 0.50),
        "p95": percentile(latencies, 0.95),
        "p99": percentile(latencies, 0.99),
        "goodput": sum(x <= slo_ms for x in latencies) / elapsed_s,
        "slo_rate": sum(x <= slo_ms for x in latencies) / len(latencies),
        "avg_batch": statistics.mean(batches),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--requests", type=int, default=5000)
    p.add_argument("--arrival-rps", type=float, default=300.0)
    p.add_argument("--max-batch", type=int, default=16)
    p.add_argument("--max-wait-ms", type=float, default=2.0)
    p.add_argument("--fixed-ms", type=float, default=1.0)
    p.add_argument("--per-item-ms", type=float, default=0.15)
    p.add_argument("--slo-ms", type=float, default=20.0)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    if min(args.requests, args.max_batch) < 1:
        raise SystemExit("requests/max-batch 必须为正整数")
    if min(args.arrival_rps, args.fixed_ms, args.per_item_ms, args.slo_ms) <= 0:
        raise SystemExit("速率和时间参数必须为正数")
    if args.max_wait_ms < 0:
        raise SystemExit("max-wait-ms 不能为负数")

    arrivals = make_arrivals(args.requests, args.arrival_rps, args.seed)
    immediate = simulate(arrivals, 1, 0.0, args.fixed_ms,
                         args.per_item_ms, args.slo_ms)
    batched = simulate(arrivals, args.max_batch, args.max_wait_ms,
                       args.fixed_ms, args.per_item_ms, args.slo_ms)

    print("mode throughput_rps p50_ms p95_ms p99_ms goodput_rps slo_rate avg_batch")
    for name, result in [("immediate", immediate), ("batched", batched)]:
        print(f"{name:9s} {result['throughput']:14.2f} "
              f"{result['p50']:7.2f} {result['p95']:7.2f} "
              f"{result['p99']:7.2f} {result['goodput']:11.2f} "
              f"{result['slo_rate']:8.3f} {result['avg_batch']:9.2f}")


if __name__ == "__main__":
    main()
