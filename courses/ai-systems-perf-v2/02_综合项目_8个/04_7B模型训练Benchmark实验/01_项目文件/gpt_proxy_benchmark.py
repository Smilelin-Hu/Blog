#!/usr/bin/env python3
import argparse
import json
import math
import os
import platform
import statistics
import time
from contextlib import nullcontext
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F


class RMSNorm(nn.Module):
    def __init__(self, dim, eps=1e-6):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(dim))
        self.eps = eps

    def forward(self, x):
        norm = x.float().pow(2).mean(-1, keepdim=True)
        return (x * torch.rsqrt(norm + self.eps).to(x.dtype)) * self.weight


class Block(nn.Module):
    def __init__(self, hidden, heads, intermediate):
        super().__init__()
        if hidden % heads:
            raise ValueError("hidden 必须能被 heads 整除")
        self.hidden = hidden
        self.heads = heads
        self.head_dim = hidden // heads
        self.attn_norm = RMSNorm(hidden)
        self.qkv = nn.Linear(hidden, 3 * hidden, bias=False)
        self.proj = nn.Linear(hidden, hidden, bias=False)
        self.ffn_norm = RMSNorm(hidden)
        self.gate = nn.Linear(hidden, intermediate, bias=False)
        self.up = nn.Linear(hidden, intermediate, bias=False)
        self.down = nn.Linear(intermediate, hidden, bias=False)

    def forward(self, x):
        batch, seq, _ = x.shape
        h = self.attn_norm(x)
        q, k, v = self.qkv(h).chunk(3, dim=-1)
        def shape(tensor):
            return tensor.view(batch, seq, self.heads, self.head_dim).transpose(1, 2)
        q, k, v = shape(q), shape(k), shape(v)
        attention = F.scaled_dot_product_attention(q, k, v, is_causal=True)
        attention = attention.transpose(1, 2).contiguous().view(batch, seq, self.hidden)
        x = x + self.proj(attention)
        h = self.ffn_norm(x)
        return x + self.down(F.silu(self.gate(h)) * self.up(h))


class GPT(nn.Module):
    def __init__(self, vocab, layers, hidden, heads, intermediate):
        super().__init__()
        self.embed = nn.Embedding(vocab, hidden)
        self.blocks = nn.ModuleList([
            Block(hidden, heads, intermediate) for _ in range(layers)
        ])
        self.norm = RMSNorm(hidden)
        self.lm_head = nn.Linear(hidden, vocab, bias=False)
        self.lm_head.weight = self.embed.weight

    def forward(self, tokens, targets):
        x = self.embed(tokens)
        for block in self.blocks:
            x = block(x)
        logits = self.lm_head(self.norm(x))
        return F.cross_entropy(logits.view(-1, logits.shape[-1]), targets.view(-1))


def percentile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return values[low]
    return values[low] * (high - position) + values[high] * (position - low)


def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)


def main():
    parser = argparse.ArgumentParser(description="GPT 训练代理 Benchmark")
    parser.add_argument("--preset", choices=["proxy", "7b"], default="proxy")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--sequence-length", type=int, default=128)
    parser.add_argument("--steps", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=1)
    parser.add_argument("--amp", action="store_true")
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--output", default="reports/proxy.json")
    args = parser.parse_args()

    if args.preset == "7b":
        config = dict(vocab=32000, layers=32, hidden=4096, heads=32, intermediate=11008)
    else:
        config = dict(vocab=2048, layers=4, hidden=256, heads=8, intermediate=768)

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("请求了 CUDA，但当前不可用")
    use_cuda = args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available())
    device = torch.device("cuda" if use_cuda else "cpu")
    torch.manual_seed(2026)

    model = GPT(**config).to(device)
    parameter_count = sum(parameter.numel() for parameter in model.parameters())
    optimizer = torch.optim.AdamW(model.parameters(), lr=3e-4)
    if args.compile:
        model = torch.compile(model)

    amp_enabled = args.amp and device.type == "cuda"
    amp_dtype = torch.bfloat16 if amp_enabled and torch.cuda.is_bf16_supported() else torch.float16
    scaler = torch.amp.GradScaler("cuda", enabled=amp_enabled and amp_dtype == torch.float16)
    times = []
    losses = []
    total_steps = args.warmup + args.steps
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)

    for step in range(total_steps):
        sync(device)
        start = time.perf_counter()
        optimizer.zero_grad(set_to_none=True)
        accumulated_loss = 0.0
        for _ in range(args.grad_accum):
            tokens = torch.randint(
                0, config["vocab"],
                (args.batch_size, args.sequence_length + 1),
                device=device,
            )
            inputs, targets = tokens[:, :-1], tokens[:, 1:]
            context = (
                torch.autocast("cuda", dtype=amp_dtype)
                if amp_enabled else nullcontext()
            )
            with context:
                loss = model(inputs, targets) / args.grad_accum
            if scaler.is_enabled():
                scaler.scale(loss).backward()
            else:
                loss.backward()
            accumulated_loss += float(loss.detach().cpu())
        if scaler.is_enabled():
            scaler.step(optimizer)
            scaler.update()
        else:
            optimizer.step()
        sync(device)
        elapsed = time.perf_counter() - start
        if step >= args.warmup:
            times.append(elapsed)
            losses.append(accumulated_loss)

    tokens_per_step = args.batch_size * args.sequence_length * args.grad_accum
    p50 = percentile(times, 0.50)
    approx_flops = 6 * parameter_count * tokens_per_step
    result = {
        "preset": args.preset,
        "config": config,
        "parameters": parameter_count,
        "device": str(device),
        "torch": torch.__version__,
        "cuda_runtime": torch.version.cuda,
        "batch_size": args.batch_size,
        "sequence_length": args.sequence_length,
        "grad_accum": args.grad_accum,
        "tokens_per_step": tokens_per_step,
        "p50_step_seconds": p50,
        "p95_step_seconds": percentile(times, 0.95),
        "tokens_per_second": tokens_per_step / p50,
        "approx_achieved_tflops": approx_flops / p50 / 1e12,
        "final_loss": losses[-1],
        "amp": amp_enabled,
        "compile": args.compile,
        "peak_memory_mib": (
            torch.cuda.max_memory_allocated(device) / 2**20
            if device.type == "cuda" else None
        ),
        "host": platform.platform(),
        "world_size": int(os.environ.get("WORLD_SIZE", "1")),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
