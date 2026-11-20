#!/usr/bin/env python3
import argparse
import math

MIB = 1024 ** 2


def simulate(total_mib, bucket_mib, backward_ms, alpha_us,
             bandwidth_gbs, world_size):
    total_bytes = total_mib * MIB
    bucket_bytes = bucket_mib * MIB
    buckets = max(1, math.ceil(total_bytes / bucket_bytes))
    sizes = [bucket_bytes] * buckets
    sizes[-1] = total_bytes - bucket_bytes * (buckets - 1)
    ready_gap_ms = backward_ms / buckets
    ring_factor = 2 * (world_size - 1) / world_size
    comm_end = 0.0
    pure_comm_ms = 0.0

    for i, size in enumerate(sizes):
        ready = (i + 1) * ready_gap_ms
        comm_ms = alpha_us / 1000 + (
            ring_factor * size / (bandwidth_gbs * 1e9) * 1000
        )
        start = max(ready, comm_end)
        comm_end = start + comm_ms
        pure_comm_ms += comm_ms

    sequential_ms = backward_ms + pure_comm_ms
    overlapped_ms = max(backward_ms, comm_end)
    return {
        "buckets": buckets,
        "pure_comm_ms": pure_comm_ms,
        "sequential_ms": sequential_ms,
        "overlapped_ms": overlapped_ms,
        "exposed_tail_ms": max(0.0, comm_end - backward_ms),
        "hidden_ms": sequential_ms - overlapped_ms,
    }


def main():
    p = argparse.ArgumentParser(description="梯度 Bucket 重叠教学模拟器")
    p.add_argument("--total-mib", type=float, default=512)
    p.add_argument("--backward-ms", type=float, default=80)
    p.add_argument("--alpha-us", type=float, default=8)
    p.add_argument("--bandwidth-gbs", type=float, default=20)
    p.add_argument("--world-size", type=int, default=8)
    p.add_argument("--bucket-mib", default="1,4,8,16,25,50,100,256,512")
    args = p.parse_args()

    if args.world_size < 2:
        raise ValueError("world-size 至少为 2")
    if min(args.total_mib, args.backward_ms, args.bandwidth_gbs) <= 0:
        raise ValueError("数据量、计算时间和带宽必须为正")

    print(f"{'Bucket':>8} {'Count':>7} {'Comm':>10} {'Serial':>10} "
          f"{'Overlap':>10} {'Tail':>10} {'Hidden':>10}")
    best = None
    for bucket in [float(x) for x in args.bucket_mib.split(",")]:
        r = simulate(args.total_mib, bucket, args.backward_ms,
                     args.alpha_us, args.bandwidth_gbs, args.world_size)
        if best is None or r["overlapped_ms"] < best[1]:
            best = (bucket, r["overlapped_ms"])
        print(f"{bucket:8.1f} {r['buckets']:7d} {r['pure_comm_ms']:10.3f} "
              f"{r['sequential_ms']:10.3f} {r['overlapped_ms']:10.3f} "
              f"{r['exposed_tail_ms']:10.3f} {r['hidden_ms']:10.3f}")

    print("\n模型最佳 Bucket MiB:", best[0])
    print("注意：真实梯度就绪不均匀，通信也可能与计算争用。")


if __name__ == "__main__":
    main()
