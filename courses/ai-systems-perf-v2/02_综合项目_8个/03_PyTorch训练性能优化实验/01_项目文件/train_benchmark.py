#!/usr/bin/env python3
import argparse
import json
import math
import os
import platform
import random
import statistics
import time
from contextlib import nullcontext
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset


class SyntheticClassification(Dataset):
    def __init__(self, samples: int, features: int, classes: int, seed: int):
        generator = torch.Generator().manual_seed(seed)
        self.x = torch.randn(samples, features, generator=generator)
        teacher = torch.randn(features, classes, generator=generator)
        self.y = (self.x @ teacher).argmax(dim=1)

    def __len__(self):
        return self.x.shape[0]

    def __getitem__(self, index):
        return self.x[index], self.y[index]


class MLP(nn.Module):
    def __init__(self, features: int, hidden: int, classes: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(features, hidden),
            nn.GELU(),
            nn.Linear(hidden, hidden),
            nn.GELU(),
            nn.Linear(hidden, classes),
        )

    def forward(self, x):
        return self.net(x)


def percentile(values, q):
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)


def synchronize(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def environment(device):
    info = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "device": str(device),
        "cpu_count": os.cpu_count(),
    }
    if device.type == "cuda":
        props = torch.cuda.get_device_properties(device)
        info.update({
            "gpu": props.name,
            "compute_capability": list(torch.cuda.get_device_capability(device)),
            "total_memory_gib": round(props.total_memory / 2**30, 2),
            "bf16_supported": bool(torch.cuda.is_bf16_supported()),
        })
    return info


def choose_amp(device, enabled):
    if not enabled or device.type != "cuda":
        return False, torch.float32
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    return True, dtype


def main():
    parser = argparse.ArgumentParser(description="PyTorch 训练性能 Benchmark")
    parser.add_argument("--mode", choices=["baseline", "optimized"], default="baseline")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--features", type=int, default=1024)
    parser.add_argument("--hidden", type=int, default=2048)
    parser.add_argument("--classes", type=int, default=100)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    if min(args.steps, args.batch_size, args.features, args.hidden, args.classes) <= 0:
        raise ValueError("steps、batch-size、features、hidden、classes 必须大于 0")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("请求了 CUDA，但当前 PyTorch 无可用 CUDA 设备")
    use_cuda = args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available())
    device = torch.device("cuda" if use_cuda else "cpu")

    optimized = args.mode == "optimized"
    pin_memory = optimized and device.type == "cuda"
    persistent_workers = optimized and args.workers > 0
    samples = max(args.batch_size * (args.steps + args.warmup + 2), args.batch_size * 8)
    dataset = SyntheticClassification(samples, args.features, args.classes, args.seed)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=pin_memory,
        persistent_workers=persistent_workers,
        drop_last=True,
    )

    model = MLP(args.features, args.hidden, args.classes).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()

    compiled = False
    if args.compile:
        if not hasattr(torch, "compile"):
            raise RuntimeError("当前 PyTorch 不支持 torch.compile")
        model = torch.compile(model)
        compiled = True

    amp_enabled, amp_dtype = choose_amp(device, optimized)
    scaler_enabled = amp_enabled and amp_dtype == torch.float16
    scaler = torch.amp.GradScaler("cuda", enabled=scaler_enabled)

    activities = [torch.profiler.ProfilerActivity.CPU]
    if device.type == "cuda":
        activities.append(torch.profiler.ProfilerActivity.CUDA)
    profile_context = (
        torch.profiler.profile(
            activities=activities,
            schedule=torch.profiler.schedule(wait=1, warmup=1, active=3, repeat=1),
            on_trace_ready=torch.profiler.tensorboard_trace_handler("reports/profile"),
            record_shapes=True,
            profile_memory=True,
        )
        if args.profile
        else nullcontext()
    )

    times_ms = []
    losses = []
    valid_steps = 0
    total_needed = args.warmup + args.steps
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)

    with profile_context as profiler:
        for step, (features, labels) in enumerate(loader):
            if step >= total_needed:
                break
            synchronize(device)
            start = time.perf_counter()

            features = features.to(device, non_blocking=pin_memory)
            labels = labels.to(device, non_blocking=pin_memory)
            optimizer.zero_grad(set_to_none=optimized)

            autocast_context = (
                torch.autocast(device_type="cuda", dtype=amp_dtype)
                if amp_enabled
                else nullcontext()
            )
            with autocast_context:
                logits = model(features)
                loss = criterion(logits, labels)

            if scaler_enabled:
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                loss.backward()
                optimizer.step()

            synchronize(device)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            loss_value = float(loss.detach().cpu())
            if math.isfinite(loss_value):
                valid_steps += 1
            if step >= args.warmup:
                times_ms.append(elapsed_ms)
                losses.append(loss_value)
            if args.profile:
                profiler.step()

    if len(times_ms) != args.steps:
        raise RuntimeError(f"只测到 {len(times_ms)} 步，预期 {args.steps} 步")

    p50_ms = percentile(times_ms, 0.50)
    result = {
        "mode": args.mode,
        "compiled": compiled,
        "amp_enabled": amp_enabled,
        "amp_dtype": str(amp_dtype),
        "pin_memory": pin_memory,
        "persistent_workers": persistent_workers,
        "batch_size": args.batch_size,
        "workers": args.workers,
        "measured_steps": args.steps,
        "p50_step_ms": round(p50_ms, 4),
        "p95_step_ms": round(percentile(times_ms, 0.95), 4),
        "mean_step_ms": round(statistics.mean(times_ms), 4),
        "samples_per_second_at_p50": round(args.batch_size / (p50_ms / 1000.0), 2),
        "first_loss": round(losses[0], 6),
        "final_loss": round(losses[-1], 6),
        "valid_step_ratio": round(valid_steps / total_needed, 6),
        "peak_memory_mib": (
            round(torch.cuda.max_memory_allocated(device) / 2**20, 2)
            if device.type == "cuda"
            else None
        ),
        "environment": environment(device),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))

    output = args.output or f"reports/{args.mode}.json"
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
