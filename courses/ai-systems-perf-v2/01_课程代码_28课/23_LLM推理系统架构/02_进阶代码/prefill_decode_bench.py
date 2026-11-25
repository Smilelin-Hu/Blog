#!/usr/bin/env python3
import argparse
import platform
import statistics
import sys
import time

import torch
import torch.nn as nn
import torch.nn.functional as F


class ToyAttention(nn.Module):
    def __init__(self, hidden: int, heads: int) -> None:
        super().__init__()
        if hidden % heads != 0:
            raise ValueError("hidden must be divisible by heads")
        self.hidden = hidden
        self.heads = heads
        self.head_dim = hidden // heads
        self.q_proj = nn.Linear(hidden, hidden, bias=False)
        self.k_proj = nn.Linear(hidden, hidden, bias=False)
        self.v_proj = nn.Linear(hidden, hidden, bias=False)
        self.o_proj = nn.Linear(hidden, hidden, bias=False)

    def split_heads(self, x: torch.Tensor) -> torch.Tensor:
        batch, seq, _ = x.shape
        return x.view(batch, seq, self.heads, self.head_dim).transpose(1, 2)

    def merge_heads(self, x: torch.Tensor) -> torch.Tensor:
        batch, heads, seq, dim = x.shape
        return x.transpose(1, 2).contiguous().view(batch, seq, heads * dim)

    def prefill(self, x: torch.Tensor):
        q = self.split_heads(self.q_proj(x))
        k = self.split_heads(self.k_proj(x))
        v = self.split_heads(self.v_proj(x))
        y = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        return self.o_proj(self.merge_heads(y)), (k, v)

    def decode(self, x: torch.Tensor, cache):
        old_k, old_v = cache
        q = self.split_heads(self.q_proj(x))
        new_k = self.split_heads(self.k_proj(x))
        new_v = self.split_heads(self.v_proj(x))
        # 教学用朴素追加。生产 Runtime 通常写入预分配的 Paged KV Block。
        k = torch.cat((old_k, new_k), dim=2)
        v = torch.cat((old_v, new_v), dim=2)
        # 当前查询位于序列末尾，可访问缓存中的全部历史位置。
        y = F.scaled_dot_product_attention(q, k, v, is_causal=False)
        return self.o_proj(self.merge_heads(y)), (k, v)


def percentile(values, q: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return ordered[index]


def parse_args():
    p = argparse.ArgumentParser(description="Toy LLM prefill/decode benchmark")
    p.add_argument("--batch", type=int, default=2)
    p.add_argument("--seq", type=int, default=512)
    p.add_argument("--hidden", type=int, default=512)
    p.add_argument("--heads", type=int, default=8)
    p.add_argument("--decode-steps", type=int, default=64)
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--dtype", choices=["fp16", "bf16", "fp32"], default="fp16")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    if not torch.cuda.is_available():
        print("CUDA GPU not found. Run the Level 0 planner on this machine.")
        sys.exit(0)

    device = torch.device("cuda")
    dtype_map = {
        "fp16": torch.float16,
        "bf16": torch.bfloat16,
        "fp32": torch.float32,
    }
    dtype = dtype_map[args.dtype]
    if dtype == torch.bfloat16 and not torch.cuda.is_bf16_supported():
        raise RuntimeError("This GPU/PyTorch stack does not report BF16 support")

    prop = torch.cuda.get_device_properties(0)
    print("=== Environment ===")
    print(f"Python              : {platform.python_version()}")
    print(f"PyTorch             : {torch.__version__}")
    print(f"CUDA runtime        : {torch.version.cuda}")
    print(f"GPU                 : {prop.name}")
    print(f"Compute capability  : {prop.major}.{prop.minor}")
    print(f"VRAM                : {prop.total_memory / 1024**3:.2f} GiB")
    print(f"dtype               : {dtype}")

    torch.manual_seed(0)
    model = ToyAttention(args.hidden, args.heads).to(device=device, dtype=dtype).eval()
    prompt = torch.randn(
        args.batch, args.seq, args.hidden, device=device, dtype=dtype
    )

    with torch.inference_mode():
        for _ in range(args.warmup):
            _, warm_cache = model.prefill(prompt)
            token = torch.randn(
                args.batch, 1, args.hidden, device=device, dtype=dtype
            )
            _, _ = model.decode(token, warm_cache)
        torch.cuda.synchronize()

        torch.cuda.reset_peak_memory_stats()
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        output, cache = model.prefill(prompt)
        end.record()
        torch.cuda.synchronize()
        prefill_ms = start.elapsed_time(end)

        step_events = [
            (torch.cuda.Event(enable_timing=True), torch.cuda.Event(enable_timing=True))
            for _ in range(args.decode_steps)
        ]
        token = output[:, -1:, :]
        host_start = time.perf_counter()
        for step_start, step_end in step_events:
            step_start.record()
            token, cache = model.decode(token, cache)
            step_end.record()
        torch.cuda.synchronize()
        host_ms = (time.perf_counter() - host_start) * 1000
        itl_ms = [start_event.elapsed_time(end_event) for start_event, end_event in step_events]

    generated_tokens = args.batch * args.decode_steps
    peak_gib = torch.cuda.max_memory_allocated() / 1024**3
    print("\n=== Results ===")
    print(f"Prompt shape        : batch={args.batch}, seq={args.seq}, hidden={args.hidden}")
    print(f"Prefill latency     : {prefill_ms:.3f} ms")
    print(f"Prompt throughput   : {args.batch * args.seq / (prefill_ms / 1000):,.1f} token/s")
    print(f"Decode host time    : {host_ms:.3f} ms")
    print(f"Mean TPOT           : {statistics.mean(itl_ms):.3f} ms/step")
    print(f"P50 ITL             : {percentile(itl_ms, 0.50):.3f} ms")
    print(f"P95 ITL             : {percentile(itl_ms, 0.95):.3f} ms")
    print(f"Generation throughput: {generated_tokens / (host_ms / 1000):,.1f} token/s")
    print(f"Final KV length     : {cache[0].shape[2]}")
    print(f"Peak allocated      : {peak_gib:.3f} GiB")
    print("\nThis toy block is for architecture study, not model-quality evaluation.")


if __name__ == "__main__":
    main()
