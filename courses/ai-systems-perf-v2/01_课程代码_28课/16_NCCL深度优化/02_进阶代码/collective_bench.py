#!/usr/bin/env python3
import argparse
import json
import math
import os
import statistics
import time

import torch
import torch.distributed as dist


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--op", choices=["all_reduce", "all_gather", "reduce_scatter"],
                   default="all_reduce")
    p.add_argument("--sizes-mib", default="0.001,0.01,0.1,1,16,64")
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--iters", type=int, default=20)
    p.add_argument("--dtype", choices=["float32", "float16"], default="float32")
    return p.parse_args()


def percentile(values, q):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1))
    return ordered[index]


def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def run_collective(op, rank, world, numel, dtype, device):
    value = float(rank + 1)
    if op == "all_reduce":
        tensor = torch.full((numel,), value, dtype=dtype, device=device)
        dist.all_reduce(tensor)
        expected = world * (world + 1) / 2
        ok = torch.isclose(tensor[0].float(), torch.tensor(expected, device=device))
        return bool(ok.item())

    if op == "all_gather":
        source = torch.full((numel,), value, dtype=dtype, device=device)
        output = torch.empty(world * numel, dtype=dtype, device=device)
        dist.all_gather_into_tensor(output, source)
        checks = [
            torch.isclose(output[i * numel].float(),
                          torch.tensor(float(i + 1), device=device))
            for i in range(world)
        ]
        return all(bool(x.item()) for x in checks)

    source = torch.full((world * numel,), value, dtype=dtype, device=device)
    output = torch.empty(numel, dtype=dtype, device=device)
    dist.reduce_scatter_tensor(output, source)
    expected = world * (world + 1) / 2
    ok = torch.isclose(output[0].float(), torch.tensor(expected, device=device))
    return bool(ok.item())


def allocate_buffers(op, rank, world, numel, dtype, device):
    value = float(rank + 1)
    if op == "all_reduce":
        source = torch.full((numel,), value, dtype=dtype, device=device)
        return source, None
    if op == "all_gather":
        source = torch.full((numel,), value, dtype=dtype, device=device)
        output = torch.empty(world * numel, dtype=dtype, device=device)
        return source, output
    source = torch.full((world * numel,), value, dtype=dtype, device=device)
    output = torch.empty(numel, dtype=dtype, device=device)
    return source, output


def call_collective(op, source, output):
    if op == "all_reduce":
        dist.all_reduce(source)
    elif op == "all_gather":
        dist.all_gather_into_tensor(output, source)
    else:
        dist.reduce_scatter_tensor(output, source)


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

    dtype = torch.float16 if args.dtype == "float16" else torch.float32
    if device.type == "cpu" and dtype == torch.float16:
        raise ValueError("CPU 回退请使用 float32")
    if backend == "gloo" and args.op == "reduce_scatter":
        raise ValueError("部分 Gloo 版本不支持 reduce_scatter_tensor；请用 GPU/NCCL")

    results = []
    element_size = torch.empty((), dtype=dtype).element_size()
    for size_mib in [float(x) for x in args.sizes_mib.split(",")]:
        numel = max(1, int(size_mib * 1024 ** 2 / element_size))

        # 先单独验证正确性，不把验证开销计入性能。
        if not run_collective(args.op, rank, world, numel, dtype, device):
            raise RuntimeError(f"rank {rank}: {args.op} correctness failed")
        sync(device)
        dist.barrier()

        source, output = allocate_buffers(
            args.op, rank, world, numel, dtype, device
        )
        for _ in range(args.warmup):
            if args.op == "all_reduce":
                source.fill_(rank + 1)
            call_collective(args.op, source, output)
        sync(device)
        dist.barrier()

        local_times_ms = []
        for _ in range(args.iters):
            if args.op == "all_reduce":
                source.fill_(rank + 1)
            sync(device)
            start = time.perf_counter()
            call_collective(args.op, source, output)
            sync(device)
            local_times_ms.append((time.perf_counter() - start) * 1000)

        # 同步作业应使用每次迭代最慢 Rank 的时间。
        times = torch.tensor(local_times_ms, dtype=torch.float32, device=device)
        dist.all_reduce(times, op=dist.ReduceOp.MAX)
        max_rank_times = times.cpu().tolist()

        payload_bytes = numel * element_size
        p50_ms = statistics.median(max_rank_times)
        p95_ms = percentile(max_rank_times, 0.95)
        algbw_gbs = payload_bytes / (p50_ms / 1000) / 1e9
        factor = (2 * (world - 1) / world
                  if args.op == "all_reduce" else (world - 1) / world)
        results.append({
            "size_mib_per_rank": payload_bytes / 1024 ** 2,
            "p50_ms_max_rank": p50_ms,
            "p95_ms_max_rank": p95_ms,
            "algbw_GBps": algbw_gbs,
            "nccl_tests_like_busbw_GBps": algbw_gbs * factor,
        })

    if rank == 0:
        nccl_version = None
        if use_cuda and hasattr(torch.cuda, "nccl"):
            try:
                nccl_version = torch.cuda.nccl.version()
            except Exception:
                pass
        print(json.dumps({
            "backend": backend,
            "world_size": world,
            "device": str(device),
            "torch_version": torch.__version__,
            "nccl_version": nccl_version,
            "op": args.op,
            "dtype": args.dtype,
            "results": results,
        }, indent=2))

    dist.destroy_process_group()


if __name__ == "__main__":
    main()
