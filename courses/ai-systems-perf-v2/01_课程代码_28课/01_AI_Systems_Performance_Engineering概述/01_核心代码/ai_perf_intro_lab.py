#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import platform
import queue
import statistics
import threading
import time
from dataclasses import dataclass

import torch
from torch import nn


def percentile(values: list[float], q: float) -> float:
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = round((len(ordered) - 1) * q)
    return ordered[index]


def architecture_name(cc: tuple[int, int]) -> str:
    major, minor = cc
    if (major, minor) == (8, 9):
        return "Ada Lovelace"
    if major == 8:
        return "Ampere-family"
    if major == 9:
        return "Hopper"
    if major in (10, 12):
        return "Blackwell-family"
    if major == 7:
        return "Volta/Turing-family"
    return f"Unknown/newer architecture (SM {major}.{minor})"


def choose_device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("--device cuda was requested, but CUDA is unavailable")
    return torch.device(requested)


def synchronize(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def nvtx_push(name: str, device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.nvtx.range_push(name)


def nvtx_pop(device: torch.device) -> None:
    if device.type == "cuda":
        torch.cuda.nvtx.range_pop()


def print_environment(device: torch.device) -> None:
    print("=== Environment ===")
    print(f"Python platform : {platform.platform()}")
    print(f"PyTorch         : {torch.__version__}")
    print(f"Selected device : {device}")
    if device.type == "cuda":
        index = device.index if device.index is not None else torch.cuda.current_device()
        props = torch.cuda.get_device_properties(index)
        cc = torch.cuda.get_device_capability(index)
        print(f"GPU             : {props.name}")
        print(f"Compute cap.    : {cc[0]}.{cc[1]} ({architecture_name(cc)})")
        print(f"VRAM            : {props.total_memory / 2**30:.2f} GiB")
        print(f"CUDA runtime    : {torch.version.cuda}")
    else:
        print("GPU metadata    : unavailable; running the Level 0 CPU path")


class TinyMLP(nn.Module):
    def __init__(self, dim: int, hidden: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(dim, hidden),
            nn.GELU(),
            nn.Linear(hidden, dim),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def make_batches(
    steps: int, batch_size: int, dim: int, seed: int
) -> list[tuple[torch.Tensor, torch.Tensor]]:
    generator = torch.Generator(device="cpu").manual_seed(seed)
    batches = []
    for _ in range(steps):
        x = torch.randn(batch_size, dim, generator=generator)
        # 目标函数保持简单但非恒等，确保训练路径完整。
        y = 0.5 * x + 0.1
        batches.append((x, y))
    return batches


@dataclass
class Result:
    name: str
    wall_seconds: float
    compute_seconds: float
    step_ms: list[float]
    samples: int
    final_loss: float

    @property
    def throughput(self) -> float:
        return self.samples / self.wall_seconds

    @property
    def goodput_ratio(self) -> float:
        return self.compute_seconds / self.wall_seconds


def train_one_step(
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    x_cpu: torch.Tensor,
    y_cpu: torch.Tensor,
    device: torch.device,
) -> float:
    x = x_cpu.to(device, non_blocking=False)
    y = y_cpu.to(device, non_blocking=False)
    optimizer.zero_grad(set_to_none=True)
    pred = model(x)
    loss = nn.functional.mse_loss(pred, y)
    loss.backward()
    optimizer.step()
    return float(loss.detach().cpu())


def run_baseline(
    initial_state: dict,
    model_factory,
    batches,
    device: torch.device,
    warmup: int,
    stall_ms: float,
) -> Result:
    model = model_factory().to(device)
    model.load_state_dict(initial_state)
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-3)
    measured_steps: list[float] = []
    measured_wall = 0.0
    measured_compute = 0.0
    final_loss = float("nan")

    for step, (x, y) in enumerate(batches):
        step_start = time.perf_counter()
        time.sleep(stall_ms / 1000.0)  # 模拟同步读取、解码或远端 I/O
        synchronize(device)
        compute_start = time.perf_counter()
        nvtx_push("baseline_compute", device)
        final_loss = train_one_step(model, optimizer, x, y, device)
        nvtx_pop(device)
        synchronize(device)
        compute_end = time.perf_counter()
        step_end = compute_end

        if step >= warmup:
            step_time = step_end - step_start
            measured_steps.append(step_time * 1000.0)
            measured_wall += step_time
            measured_compute += compute_end - compute_start

    samples = (len(batches) - warmup) * batches[0][0].shape[0]
    return Result(
        "baseline_sync_input",
        measured_wall,
        measured_compute,
        measured_steps,
        samples,
        final_loss,
    )


def run_prefetch(
    initial_state: dict,
    model_factory,
    batches,
    device: torch.device,
    warmup: int,
    stall_ms: float,
    prefetch_depth: int,
) -> Result:
    model = model_factory().to(device)
    model.load_state_dict(initial_state)
    optimizer = torch.optim.SGD(model.parameters(), lr=1e-3)
    work_queue: queue.Queue = queue.Queue(maxsize=prefetch_depth)
    sentinel = object()

    def producer() -> None:
        for item in batches:
            time.sleep(stall_ms / 1000.0)
            work_queue.put(item)
        work_queue.put(sentinel)

    producer_thread = threading.Thread(target=producer, daemon=True)
    producer_thread.start()

    measured_steps: list[float] = []
    measured_wall = 0.0
    measured_compute = 0.0
    final_loss = float("nan")
    step = 0

    while True:
        step_start = time.perf_counter()
        item = work_queue.get()  # 等待只发生在预取没有跟上时
        if item is sentinel:
            break
        x, y = item
        synchronize(device)
        compute_start = time.perf_counter()
        nvtx_push("prefetch_compute", device)
        final_loss = train_one_step(model, optimizer, x, y, device)
        nvtx_pop(device)
        synchronize(device)
        compute_end = time.perf_counter()
        step_end = compute_end

        if step >= warmup:
            step_time = step_end - step_start
            measured_steps.append(step_time * 1000.0)
            measured_wall += step_time
            measured_compute += compute_end - compute_start
        step += 1

    producer_thread.join()
    samples = (len(batches) - warmup) * batches[0][0].shape[0]
    return Result(
        "optimized_prefetch",
        measured_wall,
        measured_compute,
        measured_steps,
        samples,
        final_loss,
    )


def print_result(result: Result) -> None:
    print(f"\n=== {result.name} ===")
    print(f"measured wall time : {result.wall_seconds:.4f} s")
    print(f"mean step latency  : {statistics.mean(result.step_ms):.3f} ms")
    print(f"p50 step latency   : {statistics.median(result.step_ms):.3f} ms")
    print(f"p95 step latency   : {percentile(result.step_ms, 0.95):.3f} ms")
    print(f"throughput         : {result.throughput:.2f} samples/s")
    print(f"lab goodput ratio  : {100.0 * result.goodput_ratio:.2f}%")
    print(f"final loss         : {result.final_loss:.6f}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--steps", type=int, default=60)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--dim", type=int, default=512)
    parser.add_argument("--hidden", type=int, default=1024)
    parser.add_argument("--stall-ms", type=float, default=5.0)
    parser.add_argument("--prefetch-depth", type=int, default=4)
    parser.add_argument("--seed", type=int, default=2026)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.steps <= args.warmup:
        raise ValueError("--steps must be larger than --warmup")
    if args.prefetch_depth < 1:
        raise ValueError("--prefetch-depth must be at least 1")

    torch.manual_seed(args.seed)
    device = choose_device(args.device)
    print_environment(device)

    def model_factory() -> TinyMLP:
        return TinyMLP(args.dim, args.hidden)

    reference_model = model_factory()
    initial_state = copy.deepcopy(reference_model.state_dict())
    batches = make_batches(
        args.steps, args.batch_size, args.dim, args.seed + 1
    )

    baseline = run_baseline(
        initial_state,
        model_factory,
        batches,
        device,
        args.warmup,
        args.stall_ms,
    )
    optimized = run_prefetch(
        initial_state,
        model_factory,
        batches,
        device,
        args.warmup,
        args.stall_ms,
        args.prefetch_depth,
    )

    print_result(baseline)
    print_result(optimized)
    speedup = baseline.wall_seconds / optimized.wall_seconds
    throughput_gain = optimized.throughput / baseline.throughput
    loss_delta = abs(optimized.final_loss - baseline.final_loss)
    print("\n=== Comparison ===")
    print(f"wall-time speedup  : {speedup:.3f}x")
    print(f"throughput gain    : {throughput_gain:.3f}x")
    print(f"final-loss delta   : {loss_delta:.8f}")
    print("Interpret the result, do not chase a predetermined speedup number.")


if __name__ == "__main__":
    main()
