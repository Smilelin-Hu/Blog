#!/usr/bin/env python3
import argparse
import statistics
import time

import torch
from torch import nn


class TinyModel(nn.Module):
    def __init__(self, width, depth):
        super().__init__()
        layers = []
        for _ in range(depth):
            layers.extend([nn.Linear(width, width), nn.GELU()])
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)


def bench(fn, repeats):
    samples = []
    output = None
    for _ in range(repeats):
        torch.cuda.synchronize()
        t0 = time.perf_counter()
        output = fn()
        torch.cuda.synchronize()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(samples), output


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--requests", type=int, default=512)
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--depth", type=int, default=2)
    p.add_argument("--microbatch", type=int, default=32)
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--repeats", type=int, default=5)
    args = p.parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("需要可用的 NVIDIA CUDA GPU；无 GPU 请运行 Level 0")
    if min(args.requests, args.width, args.depth,
           args.microbatch, args.warmup, args.repeats) < 1:
        raise SystemExit("所有参数必须为正数")

    device = torch.device("cuda")
    prop = torch.cuda.get_device_properties(device)
    print(f"torch={torch.__version__} cuda={torch.version.cuda}")
    print(f"gpu={prop.name} capability={prop.major}.{prop.minor} "
          f"vram_gib={prop.total_memory/2**30:.2f}")

    torch.manual_seed(0)
    torch.set_float32_matmul_precision("high")
    model = TinyModel(args.width, args.depth).eval().to(device)
    inputs = torch.randn(args.requests, args.width, device=device)

    with torch.inference_mode():
        for _ in range(args.warmup):
            model(inputs[:args.microbatch])
        torch.cuda.synchronize()

        def sync_each_request():
            last = None
            for i in range(args.requests):
                last = model(inputs[i:i+1])
                torch.cuda.synchronize()
            return last

        def async_each_request():
            last = None
            for i in range(args.requests):
                last = model(inputs[i:i+1])
            return last

        def microbatched():
            last = None
            for start in range(0, args.requests, args.microbatch):
                last = model(inputs[start:start+args.microbatch])
            return last

        sync_ms, sync_out = bench(sync_each_request, args.repeats)
        async_ms, async_out = bench(async_each_request, args.repeats)
        batch_ms, batch_out = bench(microbatched, args.repeats)

        torch.testing.assert_close(sync_out, async_out, rtol=1e-4, atol=1e-4)
        tail = args.requests % args.microbatch or args.microbatch
        reference_batch = model(inputs[-tail:])
        torch.cuda.synchronize()
        torch.testing.assert_close(batch_out, reference_batch,
                                   rtol=1e-4, atol=1e-4)

    def rps(ms):
        return args.requests / (ms / 1000.0)

    print(f"sync_each_ms={sync_ms:.3f} throughput_rps={rps(sync_ms):.2f}")
    print(f"async_each_ms={async_ms:.3f} throughput_rps={rps(async_ms):.2f}")
    print(f"microbatch_ms={batch_ms:.3f} throughput_rps={rps(batch_ms):.2f}")
    print(f"async_speedup={sync_ms/async_ms:.3f}x")
    print(f"batch_speedup={sync_ms/batch_ms:.3f}x")
    print(f"peak_allocated_mib={torch.cuda.max_memory_allocated()/2**20:.1f}")
    print(f"peak_reserved_mib={torch.cuda.max_memory_reserved()/2**20:.1f}")


if __name__ == "__main__":
    main()
