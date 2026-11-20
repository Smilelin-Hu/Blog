#!/usr/bin/env python3
"""Portable DeepSeek co-design lab. No model download is required."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import shutil
import statistics
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


def topk_indices(values: Sequence[float], k: int) -> List[int]:
    return sorted(range(len(values)), key=values.__getitem__, reverse=True)[:k]


def make_scores(tokens: int, experts: int, seed: int) -> List[List[float]]:
    """Create intentionally skewed affinity scores for a repeatable lab."""
    rng = random.Random(seed)
    hot = max(1, experts // 8)
    scores: List[List[float]] = []
    for token in range(tokens):
        row = [rng.gauss(0.0, 1.0) for _ in range(experts)]
        # A data-dependent popularity skew creates realistic straggler pressure.
        for expert in range(hot):
            row[expert] += 0.9 + 0.2 * math.sin(token / 17.0 + expert)
        scores.append(row)
    return scores


def route(
    scores: Sequence[Sequence[float]], k: int, bias: Sequence[float]
) -> Tuple[List[List[int]], List[int], float]:
    experts = len(bias)
    assignments: List[List[int]] = []
    counts = [0] * experts
    quality_sum = 0.0
    for row in scores:
        chosen = topk_indices([v + b for v, b in zip(row, bias)], k)
        assignments.append(chosen)
        for expert in chosen:
            counts[expert] += 1
            quality_sum += row[expert]
    return assignments, counts, quality_sum / (len(scores) * k)


def load_stats(counts: Sequence[int]) -> Dict[str, float]:
    avg = statistics.mean(counts)
    stdev = statistics.pstdev(counts)
    return {
        "min": min(counts),
        "max": max(counts),
        "mean": round(avg, 4),
        "max_over_mean": round(max(counts) / avg, 4),
        "coefficient_of_variation": round(stdev / avg, 4),
    }


def balance_routing(
    scores: Sequence[Sequence[float]],
    experts: int,
    k: int,
    steps: int,
    learning_rate: float,
) -> Tuple[List[float], List[int], float]:
    """Pedagogical feedback bias; not DeepSeek's production implementation."""
    bias = [0.0] * experts
    target = len(scores) * k / experts
    for _ in range(steps):
        _, counts, _ = route(scores, k, bias)
        for expert, count in enumerate(counts):
            relative_error = (target - count) / target
            bias[expert] += learning_rate * relative_error
    _, counts, quality = route(scores, k, bias)
    return bias, counts, quality


def quantize_int8_blockwise(
    values: Sequence[float], block_size: int
) -> Tuple[List[float], int, Dict[str, float]]:
    restored: List[float] = []
    scale_bytes = 0
    for start in range(0, len(values), block_size):
        block = values[start : start + block_size]
        absmax = max(abs(x) for x in block) or 1.0
        scale = absmax / 127.0
        q = [max(-127, min(127, round(x / scale))) for x in block]
        restored.extend(x * scale for x in q)
        scale_bytes += 4  # one FP32 scale per block in this toy format
    errors = [a - b for a, b in zip(values, restored)]
    mse = statistics.mean(e * e for e in errors)
    signal = statistics.mean(x * x for x in values)
    return restored, len(values) + scale_bytes, {
        "mse": mse,
        "relative_rmse": math.sqrt(mse / signal) if signal else 0.0,
        "max_abs_error": max(abs(e) for e in errors),
    }


def communication_model(
    tokens: int, experts: int, topk: int, hidden: int, ranks: int
) -> Dict[str, Any]:
    assignments = tokens * topk
    fp16_payload = assignments * hidden * 2
    fp8_payload = assignments * hidden
    dense_hypothetical = tokens * experts * hidden * 2
    return {
        "tokens": tokens,
        "experts": experts,
        "topk": topk,
        "ranks": ranks,
        "fp16_dispatch_mib": round(fp16_payload / 2**20, 3),
        "fp8_dispatch_mib_before_metadata": round(fp8_payload / 2**20, 3),
        "payload_reduction_fp16_to_fp8": round(fp16_payload / fp8_payload, 3),
        "dense_all_experts_hypothetical_mib": round(dense_hypothetical / 2**20, 3),
        "note": "Real traffic also contains metadata, padding, forwarding and combine.",
    }


def kv_cache_model(
    layers: int,
    kv_heads: int,
    head_dim: int,
    latent_rank: int,
    rope_dim: int,
    dtype_bytes: int,
    sequence_length: int,
    batch_size: int,
) -> Dict[str, Any]:
    mha_per_token = layers * 2 * kv_heads * head_dim * dtype_bytes
    mla_per_token = layers * (latent_rank + rope_dim) * dtype_bytes
    return {
        "mha_bytes_per_token": mha_per_token,
        "mla_bytes_per_token": mla_per_token,
        "compression_ratio_analytical": round(mha_per_token / mla_per_token, 3),
        "mha_total_gib": round(
            mha_per_token * sequence_length * batch_size / 2**30, 3
        ),
        "mla_total_gib": round(
            mla_per_token * sequence_length * batch_size / 2**30, 3
        ),
        "boundary": "This is a capacity model, not an MLA kernel benchmark.",
    }


def overlap_model(microbatches: int, compute_ms: float, comm_ms: float) -> Dict[str, float]:
    serial = microbatches * (compute_ms + comm_ms)
    ideal = compute_ms + comm_ms + (microbatches - 1) * max(compute_ms, comm_ms)
    hidden = max(0.0, serial - ideal)
    return {
        "serial_ms": round(serial, 3),
        "ideal_overlap_ms": round(ideal, 3),
        "ideal_speedup": round(serial / ideal, 3),
        "hidden_ms": round(hidden, 3),
        "unhidden_per_steady_microbatch_ms": round(max(compute_ms, comm_ms), 3),
    }


def command_output(argv: List[str]) -> Dict[str, Any]:
    if shutil.which(argv[0]) is None:
        return {"available": False}
    try:
        result = subprocess.run(
            argv, capture_output=True, text=True, timeout=5, check=False
        )
        return {
            "available": True,
            "returncode": result.returncode,
            "stdout": result.stdout.strip()[:3000],
            "stderr": result.stderr.strip()[:800],
        }
    except (OSError, subprocess.SubprocessError) as exc:
        return {"available": True, "error": repr(exc)}


def synchronize(torch: Any, device: str) -> None:
    if device == "cuda":
        torch.cuda.synchronize()


def torch_moe_benchmark(args: argparse.Namespace) -> Dict[str, Any]:
    try:
        import torch
        import torch.nn.functional as F
    except ImportError as exc:
        raise SystemExit("--torch requires PyTorch") from exc

    if args.device == "cuda" and not torch.cuda.is_available():
        raise SystemExit("CUDA requested but torch.cuda.is_available() is False")
    device = args.device
    torch.manual_seed(args.seed)
    x = torch.randn(args.torch_tokens, args.torch_dim, device=device)
    w1 = torch.randn(
        args.torch_experts,
        args.torch_dim,
        args.torch_hidden,
        device=device,
    ) / math.sqrt(args.torch_dim)
    w2 = torch.randn(
        args.torch_experts,
        args.torch_hidden,
        args.torch_dim,
        device=device,
    ) / math.sqrt(args.torch_hidden)
    router = torch.randn(args.torch_dim, args.torch_experts, device=device)
    logits = x @ router
    top_values, top_indices = torch.topk(logits, args.torch_topk, dim=-1)
    gates = torch.softmax(top_values, dim=-1)

    def dense_all_experts() -> Any:
        outputs = []
        for expert in range(args.torch_experts):
            outputs.append(F.silu(x @ w1[expert]) @ w2[expert])
        stacked = torch.stack(outputs, dim=1)
        selected = torch.gather(
            stacked,
            1,
            top_indices.unsqueeze(-1).expand(-1, -1, args.torch_dim),
        )
        return (selected * gates.unsqueeze(-1)).sum(dim=1)

    def routed_topk() -> Any:
        out = torch.zeros_like(x)
        for expert in range(args.torch_experts):
            token_pos, slot = torch.where(top_indices == expert)
            if token_pos.numel() == 0:
                continue
            expert_out = F.silu(x[token_pos] @ w1[expert]) @ w2[expert]
            out.index_add_(0, token_pos, expert_out * gates[token_pos, slot, None])
        return out

    def measure(fn: Any) -> Tuple[Any, float]:
        for _ in range(args.warmup):
            result = fn()
        synchronize(torch, device)
        samples = []
        for _ in range(args.repeat):
            start = time.perf_counter()
            result = fn()
            synchronize(torch, device)
            samples.append((time.perf_counter() - start) * 1000)
        return result, statistics.median(samples)

    with torch.inference_mode():
        dense_out, dense_ms = measure(dense_all_experts)
        routed_out, routed_ms = measure(routed_topk)
    max_diff = float((dense_out - routed_out).abs().max().cpu())
    result: Dict[str, Any] = {
        "torch_version": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "device": device,
        "shape": {
            "tokens": args.torch_tokens,
            "dim": args.torch_dim,
            "hidden": args.torch_hidden,
            "experts": args.torch_experts,
            "topk": args.torch_topk,
        },
        "dense_all_experts_median_ms": round(dense_ms, 4),
        "routed_topk_median_ms": round(routed_ms, 4),
        "measured_speedup": round(dense_ms / routed_ms, 4),
        "expert_compute_ratio_idealized": round(
            args.torch_experts / args.torch_topk, 4
        ),
        "max_abs_difference": max_diff,
        "correctness": "PASS" if max_diff < 2e-4 else "CHECK",
        "warning": (
            "Sparse Python loops launch many small operations; fewer FLOPs need not "
            "mean lower latency. Production MoE uses grouped/fused kernels."
        ),
    }
    if device == "cuda":
        prop = torch.cuda.get_device_properties(0)
        result.update({
            "gpu_name": torch.cuda.get_device_name(0),
            "compute_capability": list(torch.cuda.get_device_capability(0)),
            "memory_gib": round(prop.total_memory / 2**30, 2),
        })
    return result


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--tokens", type=int, default=2048)
    p.add_argument("--experts", type=int, default=64)
    p.add_argument("--topk", type=int, default=8)
    p.add_argument("--ranks", type=int, default=8)
    p.add_argument("--hidden", type=int, default=7168)
    p.add_argument("--balance-steps", type=int, default=30)
    p.add_argument("--balance-lr", type=float, default=0.02)
    p.add_argument("--seed", type=int, default=20260805)
    p.add_argument("--block-size", type=int, default=128)
    p.add_argument("--microbatches", type=int, default=32)
    p.add_argument("--compute-ms", type=float, default=8.0)
    p.add_argument("--comm-ms", type=float, default=5.0)
    p.add_argument("--torch", action="store_true")
    p.add_argument("--device", choices=["cpu", "cuda"], default="cpu")
    p.add_argument("--torch-tokens", type=int, default=512)
    p.add_argument("--torch-dim", type=int, default=128)
    p.add_argument("--torch-hidden", type=int, default=256)
    p.add_argument("--torch-experts", type=int, default=8)
    p.add_argument("--torch-topk", type=int, default=2)
    p.add_argument("--warmup", type=int, default=2)
    p.add_argument("--repeat", type=int, default=5)
    p.add_argument("--json-out", type=Path, default=Path("deepseek_codesign_report.json"))
    args = p.parse_args()
    if not (1 <= args.topk <= args.experts):
        p.error("require 1 <= topk <= experts")
    if not (1 <= args.torch_topk <= args.torch_experts):
        p.error("require 1 <= torch-topk <= torch-experts")
    return args


def main() -> None:
    args = parse_args()
    scores = make_scores(args.tokens, args.experts, args.seed)
    _, base_counts, base_quality = route(scores, args.topk, [0.0] * args.experts)
    bias, balanced_counts, balanced_quality = balance_routing(
        scores,
        args.experts,
        args.topk,
        args.balance_steps,
        args.balance_lr,
    )

    rng = random.Random(args.seed + 1)
    activations = [rng.gauss(0, 1) for _ in range(8192)]
    _, quantized_bytes, error = quantize_int8_blockwise(
        activations, args.block_size
    )
    fp16_bytes = len(activations) * 2

    report: Dict[str, Any] = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "nvidia_smi": command_output([
                "nvidia-smi",
                "--query-gpu=name,memory.total,driver_version,pci.bus_id",
                "--format=csv,noheader",
            ]),
        },
        "routing": {
            "baseline": load_stats(base_counts),
            "balanced": load_stats(balanced_counts),
            "baseline_mean_selected_raw_score": round(base_quality, 6),
            "balanced_mean_selected_raw_score": round(balanced_quality, 6),
            "mean_abs_bias": round(statistics.mean(abs(x) for x in bias), 6),
            "interpretation": (
                "Feedback bias lowers straggler pressure but may alter semantic routing. "
                "This is a teaching analogue, not DeepSeek source code."
            ),
        },
        "communication": communication_model(
            args.tokens, args.experts, args.topk, args.hidden, args.ranks
        ),
        "blockwise_low_precision": {
            "elements": len(activations),
            "block_size": args.block_size,
            "fp16_payload_bytes": fp16_bytes,
            "toy_int8_plus_scale_bytes": quantized_bytes,
            "storage_ratio": round(fp16_bytes / quantized_bytes, 4),
            **{key: round(value, 8) for key, value in error.items()},
            "boundary": "INT8 simulation illustrates scaling; it is not FP8 E4M3.",
        },
        "kv_cache": kv_cache_model(
            layers=61,
            kv_heads=128,
            head_dim=128,
            latent_rank=512,
            rope_dim=64,
            dtype_bytes=2,
            sequence_length=32768,
            batch_size=8,
        ),
        "pipeline": overlap_model(
            args.microbatches, args.compute_ms, args.comm_ms
        ),
    }
    if args.torch:
        report["torch_moe_benchmark"] = torch_moe_benchmark(args)
    args.json_out.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
