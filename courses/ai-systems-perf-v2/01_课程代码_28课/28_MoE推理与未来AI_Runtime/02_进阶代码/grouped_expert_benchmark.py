#!/usr/bin/env python3
import argparse
import time
import torch


def arch_name(major, minor):
    if major == 8 and minor in (0, 6, 7):
        return "Ampere"
    if major == 8 and minor == 9:
        return "Ada Lovelace"
    if major == 9:
        return "Hopper"
    if major >= 10:
        return "Blackwell"
    return "Other/Older"


def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def bench(fn, device, warmup, iters):
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
    p.add_argument("--tokens", type=int, default=512)
    p.add_argument("--hidden", type=int, default=128)
    p.add_argument("--experts", type=int, default=8)
    p.add_argument("--iters", type=int, default=10)
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    torch.manual_seed(a.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float16 if device.type == "cuda" else torch.float32
    print("torch=", torch.__version__, "cuda_runtime=", torch.version.cuda)
    print("device=", device, "dtype=", dtype)
    if device.type == "cuda":
        prop = torch.cuda.get_device_properties(0)
        print("gpu=", prop.name, "cc=", f"{prop.major}.{prop.minor}",
              "arch=", arch_name(prop.major, prop.minor),
              "vram_GiB=", round(prop.total_memory / 2**30, 2))

    x = torch.randn(a.tokens, a.hidden, device=device, dtype=dtype)
    weights = torch.randn(a.experts, a.hidden, a.hidden,
                          device=device, dtype=dtype) / a.hidden**0.5
    expert_ids = torch.randint(0, a.experts, (a.tokens,), device=device)

    @torch.inference_mode()
    def token_loop():
        out = torch.empty_like(x)
        for t in range(a.tokens):
            out[t] = x[t] @ weights[expert_ids[t]]
        return out

    @torch.inference_mode()
    def grouped():
        out = torch.empty_like(x)
        for e in range(a.experts):
            idx = torch.where(expert_ids == e)[0]
            if idx.numel():
                out[idx] = x[idx] @ weights[e]
        return out

    ref = token_loop()
    opt = grouped()
    max_err = (ref - opt).abs().max().item()
    loop_ms = bench(token_loop, device, a.warmup, a.iters)
    grouped_ms = bench(grouped, device, a.warmup, a.iters)
    counts = torch.bincount(expert_ids, minlength=a.experts).cpu().tolist()
    print("tokens_per_expert=", counts)
    print(f"max_abs_error={max_err:.6g}")
    print(f"token_loop={loop_ms:.3f} ms")
    print(f"grouped={grouped_ms:.3f} ms")
    print(f"speedup={loop_ms/grouped_ms:.3f}x")
    print("结果仅代表本机形状；真实框架会使用融合 Grouped GEMM kernel。")


if __name__ == "__main__":
    main()
