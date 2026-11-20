#!/usr/bin/env python3
import argparse
import contextlib
import json
import os
import time

import torch
import torch.nn as nn
from torch.profiler import ProfilerActivity, profile, record_function


class MLP(nn.Module):
    def __init__(self, width, depth):
        super().__init__()
        layers = []
        for _ in range(depth):
            layers += [nn.Linear(width, width), nn.GELU()]
        layers += [nn.Linear(width, width)]
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


@contextlib.contextmanager
def phase(name, use_nvtx):
    if use_nvtx:
        torch.cuda.nvtx.range_push(name)
    try:
        with record_function(name):
            yield
    finally:
        if use_nvtx:
            torch.cuda.nvtx.range_pop()


def preprocess(x, mode):
    if mode == "baseline":
        # 故意保留 Python 循环和许多小 Tensor 操作。
        return torch.stack([(row - row.mean()) / (row.std() + 1e-5) for row in x])
    return (x - x.mean(dim=1, keepdim=True)) / (
        x.std(dim=1, keepdim=True) + 1e-5
    )


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["baseline", "optimized"], required=True)
    p.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--depth", type=int, default=4)
    p.add_argument("--steps", type=int, default=8)
    p.add_argument("--with-stack", action="store_true")
    p.add_argument("--memory-snapshot", action="store_true")
    p.add_argument("--out", default="profiler_artifacts")
    return p.parse_args()


def main():
    args = parse_args()
    has_cuda = torch.cuda.is_available()
    device = "cuda" if args.device == "auto" and has_cuda else args.device
    if device == "auto":
        device = "cpu"
    if device == "cuda" and not has_cuda:
        raise SystemExit("请求 CUDA，但 torch.cuda.is_available() 为 False")

    os.makedirs(args.out, exist_ok=True)
    torch.manual_seed(2026)
    use_cuda = device == "cuda"
    if use_cuda:
        p = torch.cuda.get_device_properties(0)
        print({"torch": torch.__version__, "cuda": torch.version.cuda,
               "gpu": p.name, "cc": f"{p.major}.{p.minor}",
               "vram_gib": round(p.total_memory / 1024**3, 2)})
    else:
        print({"torch": torch.__version__, "device": "cpu",
               "threads": torch.get_num_threads()})

    model = MLP(args.width, args.depth).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    host_batch = torch.randn(args.batch, args.width)

    if args.memory_snapshot and use_cuda:
        torch.cuda.memory._record_memory_history(max_entries=100000)

    def train_step():
        optimizer.zero_grad(set_to_none=True)
        with phase("input/preprocess", use_cuda):
            x = preprocess(host_batch, args.mode)
        with phase("input/h2d", use_cuda):
            x = x.to(device, non_blocking=use_cuda)
        with phase("model/forward", use_cuda):
            y = model(x)
            loss = y.float().square().mean()
        with phase("model/backward", use_cuda):
            loss.backward()
        with phase("optimizer/step", use_cuda):
            optimizer.step()
        return loss.detach()

    # 无 Profiler 预热，隔离 CUDA 初始化与优化器状态首次创建。
    for _ in range(3):
        train_step()
    if use_cuda:
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()

    # 先做低扰动端到端计时。
    start = time.perf_counter()
    for _ in range(args.steps):
        train_step()
    if use_cuda:
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    benchmark = {
        "mode": args.mode,
        "device": device,
        "step_ms": elapsed * 1000 / args.steps,
        "samples_per_s": args.batch * args.steps / elapsed,
    }
    if use_cuda:
        benchmark.update({
            "peak_allocated_gib": torch.cuda.max_memory_allocated() / 1024**3,
            "peak_reserved_gib": torch.cuda.max_memory_reserved() / 1024**3,
        })
    print("BENCHMARK", json.dumps(benchmark, ensure_ascii=False))

    activities = [ProfilerActivity.CPU]
    if use_cuda:
        activities.append(ProfilerActivity.CUDA)

    def save_trace(prof):
        path = os.path.join(args.out, f"{args.mode}_step_{prof.step_num}.json")
        prof.export_chrome_trace(path)
        print("TRACE", path)

    schedule = torch.profiler.schedule(wait=1, warmup=1, active=3, repeat=1)
    with profile(
        activities=activities,
        schedule=schedule,
        on_trace_ready=save_trace,
        record_shapes=True,
        profile_memory=True,
        with_stack=args.with_stack,
        with_flops=True,
    ) as prof:
        # wait + warmup + active = 5；多跑一步确保 cycle 结束并导出。
        for _ in range(6):
            train_step()
            prof.step()

    sort_key = "self_cuda_time_total" if use_cuda else "self_cpu_time_total"
    print(prof.key_averages().table(sort_by=sort_key, row_limit=20))

    if args.memory_snapshot and use_cuda:
        path = os.path.join(args.out, f"{args.mode}_memory_snapshot.pickle")
        torch.cuda.memory._dump_snapshot(path)
        print("MEMORY_SNAPSHOT", path)


if __name__ == "__main__":
    main()
