#!/usr/bin/env python3
import argparse
import json
import os
import statistics
import time

import torch
import torch.distributed as dist


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--bucket-mib", type=float, default=16)
    p.add_argument("--buckets", type=int, default=4)
    p.add_argument("--compute-dim", type=int, default=1024)
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--iters", type=int, default=10)
    return p.parse_args()


def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def main():
    args = parse_args()
    use_cuda = torch.cuda.is_available()
    backend = "nccl" if use_cuda else "gloo"
    dist.init_process_group(backend=backend)
    rank, world = dist.get_rank(), dist.get_world_size()
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    if use_cuda:
        torch.cuda.set_device(local_rank)
        device = torch.device("cuda", local_rank)
    else:
        device = torch.device("cpu")
        torch.set_num_threads(max(1, (os.cpu_count() or 2) // world))

    torch.manual_seed(2026)
    a = torch.randn(args.compute_dim, args.compute_dim, device=device)
    b = torch.randn(args.compute_dim, args.compute_dim, device=device)
    numel = max(1, int(args.bucket_mib * 1024 ** 2 / 4))
    buckets = [torch.empty(numel, device=device) for _ in range(args.buckets)]
    expected = world * (world + 1) / 2

    def step(mode):
        works = []
        for bucket in buckets:
            compute = a @ b
            bucket.fill_(rank + 1)
            bucket.add_(compute[0, 0] * 0.0)  # 计算到通信的数据依赖
            if mode == "sequential":
                dist.all_reduce(bucket)
            else:
                works.append(dist.all_reduce(bucket, async_op=True))
        for work in works:
            work.wait()
        sync(device)
        ok = torch.isclose(
            buckets[-1][0].float(), torch.tensor(float(expected), device=device)
        )
        if not bool(ok.item()):
            raise RuntimeError(f"rank={rank} correctness failed")

    def benchmark(mode):
        for _ in range(args.warmup):
            step(mode)
        sync(device)
        dist.barrier()
        local_ms = []
        for _ in range(args.iters):
            dist.barrier()
            sync(device)
            start = time.perf_counter()
            step(mode)
            local_ms.append((time.perf_counter() - start) * 1000)
        times = torch.tensor(local_ms, dtype=torch.float32, device=device)
        dist.all_reduce(times, op=dist.ReduceOp.MAX)
        values = times.cpu().tolist()
        return {
            "p50_ms_max_rank": statistics.median(values),
            "min_ms_max_rank": min(values),
            "max_ms_max_rank": max(values),
        }

    sequential = benchmark("sequential")
    overlap = benchmark("overlap")
    speedup = sequential["p50_ms_max_rank"] / overlap["p50_ms_max_rank"]
    if rank == 0:
        print(json.dumps({
            "backend": backend, "device": str(device), "world_size": world,
            "bucket_mib": args.bucket_mib, "buckets": args.buckets,
            "compute_dim": args.compute_dim, "sequential": sequential,
            "overlap": overlap, "p50_speedup": speedup,
            "warning": "合成实验仅代表当前环境；重叠可能因争用变慢"
        }, indent=2))
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
