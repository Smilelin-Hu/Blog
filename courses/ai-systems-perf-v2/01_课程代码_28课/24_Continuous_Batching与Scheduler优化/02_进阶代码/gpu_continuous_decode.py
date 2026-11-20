#!/usr/bin/env python3
import argparse
import platform
import random
import statistics
import sys

import torch
import torch.nn as nn


class TinyDecoder(nn.Module):
    def __init__(self, hidden):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(hidden, hidden * 4, bias=False),
            nn.GELU(),
            nn.Linear(hidden * 4, hidden, bias=False),
            nn.LayerNorm(hidden),
        )

    def forward(self, x):
        return self.net(x)


def time_cuda(fn):
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    result = fn()
    end.record()
    torch.cuda.synchronize()
    return result, start.elapsed_time(end)


def baseline(model, initial, lengths):
    outputs = []
    calls = 0
    for state, steps in zip(initial, lengths):
        x = state.unsqueeze(0)
        for _ in range(steps):
            x = model(x)
            calls += 1
        outputs.append(x.squeeze(0))
    return torch.stack(outputs), calls


def continuous(model, initial, lengths):
    states = [x.clone() for x in initial]
    remaining = list(lengths)
    calls = 0
    while any(x > 0 for x in remaining):
        active = [i for i, value in enumerate(remaining) if value > 0]
        batch = torch.stack([states[i] for i in active])
        batch_out = model(batch)
        calls += 1
        for row, request_id in enumerate(active):
            states[request_id] = batch_out[row]
            remaining[request_id] -= 1
    return torch.stack(states), calls


def parse_args():
    p = argparse.ArgumentParser(description="GPU continuous decode compaction")
    p.add_argument("--requests", type=int, default=32)
    p.add_argument("--hidden", type=int, default=512)
    p.add_argument("--min-steps", type=int, default=8)
    p.add_argument("--max-steps", type=int, default=64)
    p.add_argument("--dtype", choices=["fp16", "bf16", "fp32"], default="fp16")
    p.add_argument("--seed", type=int, default=7)
    return p.parse_args()


def main():
    args = parse_args()
    if not torch.cuda.is_available():
        print("CUDA GPU not found. Run the Level 0 simulator on this machine.")
        sys.exit(0)

    dtype = {
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
        "fp32": torch.float32,
    }[args.dtype]
    if dtype == torch.bfloat16 and not torch.cuda.is_bf16_supported():
        raise RuntimeError("BF16 is not supported by this GPU/PyTorch stack")

    rng = random.Random(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device("cuda")
    prop = torch.cuda.get_device_properties(0)
    lengths = [rng.randint(args.min_steps, args.max_steps) for _ in range(args.requests)]
    initial = torch.randn(args.requests, args.hidden, device=device, dtype=dtype)
    model = TinyDecoder(args.hidden).to(device=device, dtype=dtype).eval()

    print("=== Environment ===")
    print(f"Python             : {platform.python_version()}")
    print(f"PyTorch            : {torch.__version__}")
    print(f"CUDA runtime       : {torch.version.cuda}")
    print(f"GPU                : {prop.name}")
    print(f"Compute capability : {prop.major}.{prop.minor}")
    print(f"VRAM               : {prop.total_memory / 1024**3:.2f} GiB")
    print(f"dtype              : {dtype}")
    print(f"output steps       : min={min(lengths)}, mean={statistics.mean(lengths):.1f}, max={max(lengths)}")

    with torch.inference_mode():
        # 两条路径各预热一次，不计入结果。
        baseline(model, initial[:2], [2, 3])
        continuous(model, initial[:2], [2, 3])
        torch.cuda.synchronize()

        torch.cuda.reset_peak_memory_stats()
        (baseline_out, baseline_calls), baseline_ms = time_cuda(
            lambda: baseline(model, initial, lengths)
        )
        baseline_peak = torch.cuda.max_memory_allocated()

        torch.cuda.reset_peak_memory_stats()
        (continuous_out, continuous_calls), continuous_ms = time_cuda(
            lambda: continuous(model, initial, lengths)
        )
        continuous_peak = torch.cuda.max_memory_allocated()

    max_error = (baseline_out.float() - continuous_out.float()).abs().max().item()
    total_tokens = sum(lengths)
    print("\n=== Results ===")
    print(f"Useful decode tokens       : {total_tokens}")
    print(f"Baseline model calls       : {baseline_calls}")
    print(f"Continuous model calls     : {continuous_calls}")
    print(f"Baseline latency           : {baseline_ms:.3f} ms")
    print(f"Continuous latency         : {continuous_ms:.3f} ms")
    print(f"Baseline throughput        : {total_tokens / (baseline_ms / 1000):,.1f} token/s")
    print(f"Continuous throughput      : {total_tokens / (continuous_ms / 1000):,.1f} token/s")
    print(f"Speedup                    : {baseline_ms / continuous_ms:.2f}x")
    print(f"Max absolute output error  : {max_error:.6f}")
    print(f"Peak allocated baseline    : {baseline_peak / 1024**3:.3f} GiB")
    print(f"Peak allocated continuous  : {continuous_peak / 1024**3:.3f} GiB")
    print("\nThis is a launch/compaction microbenchmark, not a full LLM server.")


if __name__ == "__main__":
    main()
