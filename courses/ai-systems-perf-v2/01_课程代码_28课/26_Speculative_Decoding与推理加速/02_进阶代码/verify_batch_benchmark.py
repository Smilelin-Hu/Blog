#!/usr/bin/env python3
import argparse
import time
import torch
from torch import nn


def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def bench(fn, device, warmup=10, iters=50):
    for _ in range(warmup):
        fn()
    sync(device)
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    sync(device)
    return (time.perf_counter() - t0) * 1000 / iters


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--hidden", type=int, default=2048)
    p.add_argument("--draft-k", type=int, default=4)
    p.add_argument("--acceptance", type=float, default=0.75)
    p.add_argument("--iters", type=int, default=50)
    a = p.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float16 if device.type == "cuda" else torch.float32
    print("device=", device, "torch=", torch.__version__)
    if device.type == "cuda":
        prop = torch.cuda.get_device_properties(0)
        print("gpu=", prop.name, "cc=", f"{prop.major}.{prop.minor}",
              "vram_GiB=", round(prop.total_memory / 2**30, 2))

    target = nn.Sequential(
        nn.Linear(a.hidden, 4 * a.hidden, bias=False), nn.GELU(),
        nn.Linear(4 * a.hidden, a.hidden, bias=False)
    ).to(device=device, dtype=dtype).eval()
    draft = nn.Sequential(
        nn.Linear(a.hidden, a.hidden // 2, bias=False), nn.ReLU(),
        nn.Linear(a.hidden // 2, a.hidden, bias=False)
    ).to(device=device, dtype=dtype).eval()

    x = torch.randn(a.batch, a.hidden, device=device, dtype=dtype)
    xk = torch.randn(a.batch * a.draft_k, a.hidden,
                     device=device, dtype=dtype)

    @torch.inference_mode()
    def target_sequential():
        y = x
        for _ in range(a.draft_k):
            y = target(y)
        return y

    @torch.inference_mode()
    def target_verify_batch():
        return target(xk)

    @torch.inference_mode()
    def draft_sequential():
        y = x
        for _ in range(a.draft_k):
            y = draft(y)
        return y

    seq_ms = bench(target_sequential, device, iters=a.iters)
    verify_ms = bench(target_verify_batch, device, iters=a.iters)
    draft_ms = bench(draft_sequential, device, iters=a.iters)
    alpha = a.acceptance
    expected = ((1 - alpha ** (a.draft_k + 1)) / (1 - alpha)
                if alpha < 1 else a.draft_k + 1)
    one_target_ms = seq_ms / a.draft_k
    estimated = expected * one_target_ms / (draft_ms + verify_ms)

    print(f"K sequential target calls: {seq_ms:.3f} ms")
    print(f"one batched target verify: {verify_ms:.3f} ms")
    print(f"K draft calls: {draft_ms:.3f} ms")
    print(f"expected committed/round: {expected:.3f}")
    print(f"model-only estimated speedup: {estimated:.3f}x")
    print("注意：未计入 attention、KV、采样、调度和回滚开销。")


if __name__ == "__main__":
    main()
