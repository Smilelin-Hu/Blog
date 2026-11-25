#!/usr/bin/env python3
import argparse
import contextlib
import json
import os
import time

import torch
import torch.distributed as dist
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.parallel import DistributedDataParallel as DDP


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--hidden", type=int, default=1024)
    p.add_argument("--layers", type=int, default=4)
    p.add_argument("--local-batch", type=int, default=32)
    p.add_argument("--grad-accum", type=int, default=1)
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--bucket-mb", type=float, default=25.0)
    return p.parse_args()


def make_model(hidden, layers):
    modules = []
    for _ in range(layers):
        modules += [nn.Linear(hidden, hidden), nn.GELU()]
    modules.append(nn.Linear(hidden, hidden))
    return nn.Sequential(*modules)


def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def main():
    args = parse_args()
    use_cuda = torch.cuda.is_available()
    backend = "nccl" if use_cuda else "gloo"
    dist.init_process_group(backend=backend)

    rank = dist.get_rank()
    world = dist.get_world_size()
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))

    if use_cuda:
        torch.cuda.set_device(local_rank)
        device = torch.device("cuda", local_rank)
    else:
        device = torch.device("cpu")
        # 多进程 CPU 实验避免每个进程都占满全部 CPU 线程。
        torch.set_num_threads(max(1, (os.cpu_count() or 2) // world))

    # 构造模型前使用相同种子，使各 rank 初始参数一致。
    torch.manual_seed(2026)
    model = make_model(args.hidden, args.layers).to(device)
    ddp = DDP(
        model,
        device_ids=[local_rank] if use_cuda else None,
        bucket_cap_mb=args.bucket_mb,
        gradient_as_bucket_view=True,
    )
    optimizer = torch.optim.SGD(ddp.parameters(), lr=1e-3)
    params = sum(p.numel() for p in ddp.parameters())

    # 数据种子按 rank 区分，模拟不同数据分片。
    generator = torch.Generator(device=device)
    generator.manual_seed(1000 + rank)

    def train_step():
        optimizer.zero_grad(set_to_none=True)
        loss_value = 0.0
        for micro in range(args.grad_accum):
            # 非最后微步不做梯度同步；forward 也必须位于 no_sync 内。
            ctx = (
                ddp.no_sync()
                if micro < args.grad_accum - 1
                else contextlib.nullcontext()
            )
            with ctx:
                x = torch.randn(
                    args.local_batch, args.hidden,
                    device=device, generator=generator
                )
                target = torch.randn(
                    args.local_batch, args.hidden,
                    device=device, generator=generator
                )
                loss = F.mse_loss(ddp(x), target) / args.grad_accum
                loss.backward()
                loss_value += float(loss.detach())
        optimizer.step()
        return loss_value

    for _ in range(args.warmup):
        train_step()
    sync(device)
    dist.barrier()

    if use_cuda:
        torch.cuda.reset_peak_memory_stats(device)

    start = time.perf_counter()
    last_loss = None
    for _ in range(args.steps):
        last_loss = train_step()
    sync(device)
    dist.barrier()
    elapsed = time.perf_counter() - start

    # 同步训练应使用最慢 rank 的耗时计算端到端吞吐。
    elapsed_tensor = torch.tensor(elapsed, dtype=torch.float64, device=device)
    dist.all_reduce(elapsed_tensor, op=dist.ReduceOp.MAX)
    max_elapsed = float(elapsed_tensor.item())

    local_samples = args.steps * args.local_batch * args.grad_accum
    global_samples = local_samples * world
    peak_gib = (
        torch.cuda.max_memory_allocated(device) / (1024 ** 3)
        if use_cuda else None
    )

    if rank == 0:
        print(json.dumps({
            "world_size": world,
            "backend": backend,
            "device": str(device),
            "torch_version": torch.__version__,
            "parameters": params,
            "local_batch_per_microstep": args.local_batch,
            "grad_accum": args.grad_accum,
            "global_batch_per_optimizer_step": (
                args.local_batch * args.grad_accum * world
            ),
            "max_elapsed_s": max_elapsed,
            "step_ms": max_elapsed * 1000 / args.steps,
            "global_samples_per_s": global_samples / max_elapsed,
            "peak_allocated_gib_rank0": peak_gib,
            "last_loss_rank0": last_loss,
        }, indent=2))

    dist.destroy_process_group()


if __name__ == "__main__":
    main()
