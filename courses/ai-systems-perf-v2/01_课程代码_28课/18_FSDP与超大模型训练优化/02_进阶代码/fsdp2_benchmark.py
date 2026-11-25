#!/usr/bin/env python3
import argparse
import contextlib
import os
import time

import torch
import torch.distributed as dist
import torch.nn as nn
from torch.distributed.device_mesh import init_device_mesh
from torch.nn.parallel import DistributedDataParallel as DDP


class Block(nn.Module):
    def __init__(self, hidden, expansion=4):
        super().__init__()
        self.norm = nn.LayerNorm(hidden)
        self.fc1 = nn.Linear(hidden, hidden * expansion, bias=False)
        self.fc2 = nn.Linear(hidden * expansion, hidden, bias=False)

    def forward(self, x):
        h = self.norm(x)
        h = torch.nn.functional.gelu(self.fc1(h), approximate="tanh")
        return x + self.fc2(h)


class TinyTransformer(nn.Module):
    def __init__(self, hidden, layers):
        super().__init__()
        self.blocks = nn.ModuleList([Block(hidden) for _ in range(layers)])
        self.norm = nn.LayerNorm(hidden)

    def forward(self, x):
        for block in self.blocks:
            x = block(x)
        return self.norm(x)


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["ddp", "fsdp2"], required=True)
    p.add_argument("--hidden", type=int, default=1024)
    p.add_argument("--layers", type=int, default=8)
    p.add_argument("--batch", type=int, default=2)
    p.add_argument("--seq", type=int, default=256)
    p.add_argument("--steps", type=int, default=10)
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--accum", type=int, default=1)
    p.add_argument("--lr", type=float, default=1e-3)
    return p.parse_args()


def main():
    args = parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("Level 1 需要 NVIDIA GPU；无 GPU 请运行 Level 0。")

    dist.init_process_group("nccl")
    rank = dist.get_rank()
    world = dist.get_world_size()
    local_rank = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local_rank)
    device = torch.device("cuda", local_rank)
    torch.manual_seed(2026)
    torch.cuda.manual_seed_all(2026)

    if world < 2:
        raise SystemExit("请用 torchrun 启动至少 2 个进程。")

    model = TinyTransformer(args.hidden, args.layers).to(device)
    total_params = sum(p.numel() for p in model.parameters())
    use_bf16 = torch.cuda.is_bf16_supported()
    compute_dtype = torch.bfloat16 if use_bf16 else torch.float16

    if args.mode == "ddp":
        model = DDP(model, device_ids=[local_rank])
    else:
        try:
            from torch.distributed.fsdp import fully_shard, MixedPrecisionPolicy
        except ImportError as exc:
            raise SystemExit("当前 PyTorch 没有 FSDP2，请安装受支持版本。") from exc

        mesh = init_device_mesh("cuda", (world,))
        mp = MixedPrecisionPolicy(
            param_dtype=compute_dtype,
            reduce_dtype=compute_dtype,
        )
        # 关键：Block 先分片，根模型最后分片。
        for block in model.blocks:
            fully_shard(block, mesh=mesh, mp_policy=mp,
                        reshard_after_forward=True)
        fully_shard(model, mesh=mesh, mp_policy=mp)

    # 必须在 FSDP2 处理参数后创建 optimizer。
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr)

    def one_step(measure=False):
        optimizer.zero_grad(set_to_none=True)
        loss_value = 0.0
        for micro in range(args.accum):
            sync = micro == args.accum - 1
            if args.mode == "fsdp2":
                model.set_requires_gradient_sync(sync)
                sync_ctx = contextlib.nullcontext()
            else:
                sync_ctx = contextlib.nullcontext() if sync else model.no_sync()

            x = torch.randn(args.batch, args.seq, args.hidden,
                            device=device, dtype=compute_dtype)
            target = torch.zeros_like(x)
            with sync_ctx:
                out = model(x)
                loss = (out.float() - target.float()).square().mean()
                loss = loss / args.accum
                loss.backward()
            loss_value += loss.detach().float().item()
        optimizer.step()
        return loss_value

    for _ in range(args.warmup):
        one_step()
    dist.barrier()
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()

    start = time.perf_counter()
    last_loss = 0.0
    for _ in range(args.steps):
        last_loss = one_step(measure=True)
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - start

    peak_alloc = torch.cuda.max_memory_allocated() / 1024**3
    peak_reserved = torch.cuda.max_memory_reserved() / 1024**3
    stat = torch.tensor([elapsed, peak_alloc, peak_reserved], device=device)
    dist.all_reduce(stat, op=dist.ReduceOp.MAX)

    if rank == 0:
        global_samples = args.batch * world * args.accum * args.steps
        tokens = global_samples * args.seq
        print({
            "mode": args.mode,
            "world_size": world,
            "params_m": round(total_params / 1e6, 2),
            "dtype": str(compute_dtype),
            "step_ms_max_rank": round(stat[0].item() * 1000 / args.steps, 3),
            "tokens_per_s": round(tokens / stat[0].item(), 1),
            "peak_alloc_gib_max_rank": round(stat[1].item(), 3),
            "peak_reserved_gib_max_rank": round(stat[2].item(), 3),
            "last_loss": round(last_loss, 6),
        })
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
