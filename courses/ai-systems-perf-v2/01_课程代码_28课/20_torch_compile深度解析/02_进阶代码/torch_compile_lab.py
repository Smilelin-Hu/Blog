#!/usr/bin/env python3
import argparse
import copy
import statistics
import time

import torch
from torch import nn


class Block(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.norm = nn.LayerNorm(width)
        self.fc1 = nn.Linear(width, width * 2)
        self.fc2 = nn.Linear(width * 2, width)

    def forward(self, x):
        residual = x
        x = self.norm(x)
        x = self.fc2(torch.nn.functional.gelu(self.fc1(x)))
        # 保留多个可融合的 pointwise 运算，便于观察编译收益
        x = torch.sigmoid(x) * x + 0.1 * torch.tanh(x)
        return residual + x


class Model(nn.Module):
    def __init__(self, width, depth):
        super().__init__()
        self.blocks = nn.ModuleList([Block(width) for _ in range(depth)])

    def forward(self, x):
        for block in self.blocks:
            x = block(x)
        return x


def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def timed(model, x, warmup, steps, device):
    with torch.inference_mode():
        for _ in range(warmup):
            model(x)
        sync(device)
        samples = []
        for _ in range(steps):
            t0 = time.perf_counter()
            model(x)
            sync(device)
            samples.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(samples), statistics.quantiles(samples, n=20)[18]


def parse_dynamic(value):
    return {"auto": None, "true": True, "false": False}[value]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--depth", type=int, default=4)
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--steps", type=int, default=30)
    p.add_argument("--compile-mode", default="default",
                   choices=["default", "reduce-overhead", "max-autotune"])
    p.add_argument("--dynamic", default="auto", choices=["auto", "true", "false"])
    p.add_argument("--fullgraph", action="store_true")
    p.add_argument("--vary-shapes", action="store_true")
    args = p.parse_args()

    if not hasattr(torch, "compile"):
        raise SystemExit("当前 PyTorch 不提供 torch.compile，请升级到受支持的稳定版本")
    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("请求了 CUDA，但当前 PyTorch/驱动不可用")
    device = torch.device(
        "cuda" if args.device == "cuda" or
        (args.device == "auto" and torch.cuda.is_available()) else "cpu"
    )

    torch.manual_seed(0)
    torch.set_float32_matmul_precision("high")
    eager = Model(args.width, args.depth).eval().to(device)
    compiled = copy.deepcopy(eager)

    print(f"torch={torch.__version__} device={device}")
    if device.type == "cuda":
        prop = torch.cuda.get_device_properties(device)
        print(f"gpu={prop.name} capability={prop.major}.{prop.minor} "
              f"vram_gib={prop.total_memory / 2**30:.2f} cuda={torch.version.cuda}")
        torch.cuda.reset_peak_memory_stats(device)

    x = torch.randn(args.batch, args.width, device=device)
    dynamic = parse_dynamic(args.dynamic)
    compiled.compile(mode=args.compile_mode,
                     fullgraph=args.fullgraph,
                     dynamic=dynamic)

    with torch.inference_mode():
        expected = eager(x)
        sync(device)
        t0 = time.perf_counter()
        actual = compiled(x)
        sync(device)
        first_compiled_ms = (time.perf_counter() - t0) * 1000.0
    torch.testing.assert_close(actual, expected, rtol=2e-3, atol=2e-3)

    eager_p50, eager_p95 = timed(eager, x, args.warmup, args.steps, device)
    comp_p50, comp_p95 = timed(compiled, x, args.warmup, args.steps, device)
    print(f"first_compiled_call_ms={first_compiled_ms:.3f}")
    print(f"eager_p50_ms={eager_p50:.3f} eager_p95_ms={eager_p95:.3f}")
    print(f"compiled_p50_ms={comp_p50:.3f} compiled_p95_ms={comp_p95:.3f}")
    print(f"steady_speedup={eager_p50 / comp_p50:.3f}x")

    if args.vary_shapes:
        print("vary_shapes_begin")
        with torch.inference_mode():
            for batch in [8, 16, 24, 32, 48, 64, 16, 32]:
                value = torch.randn(batch, args.width, device=device)
                t0 = time.perf_counter()
                compiled(value)
                sync(device)
                print(f"batch={batch:2d} call_ms={(time.perf_counter()-t0)*1000:.3f}")
        print("vary_shapes_end")

    if device.type == "cuda":
        print(f"peak_allocated_mib={torch.cuda.max_memory_allocated(device)/2**20:.1f}")
        print(f"peak_reserved_mib={torch.cuda.max_memory_reserved(device)/2**20:.1f}")


if __name__ == "__main__":
    main()
