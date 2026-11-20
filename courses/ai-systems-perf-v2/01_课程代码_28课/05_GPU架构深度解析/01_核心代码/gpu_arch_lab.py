#!/usr/bin/env python3
import argparse
import json
import math
import random
import statistics
import time


ARCH = {
    "80": {"name": "Ampere CC 8.0 / A100", "threads": 2048,
           "warps": 64, "blocks": 32, "registers": 65536,
           "shared_kb": 164},
    "86": {"name": "Ampere CC 8.6 / RTX 3080/3090", "threads": 1536,
           "warps": 48, "blocks": 16, "registers": 65536,
           "shared_kb": 100},
    "89": {"name": "Ada CC 8.9 / RTX 4090, L40/L40S", "threads": 1536,
           "warps": 48, "blocks": 24, "registers": 65536,
           "shared_kb": 100},
    "90": {"name": "Hopper CC 9.0 / H100/H200", "threads": 2048,
           "warps": 64, "blocks": 32, "registers": 65536,
           "shared_kb": 228},
    "100": {"name": "Blackwell CC 10.0 / B200", "threads": 2048,
            "warps": 64, "blocks": 32, "registers": 65536,
            "shared_kb": 228},
    "120": {"name": "Blackwell CC 12.0 / RTX 5090", "threads": 1536,
            "warps": 48, "blocks": 32, "registers": 65536,
            "shared_kb": 128},
}


def architecture_from_cc(major, minor):
    code = major * 10 + minor
    if code == 80:
        return "Ampere CC 8.0"
    if 80 < code < 89:
        return "Ampere CC 8.x"
    if code == 89:
        return "Ada Lovelace CC 8.9"
    if 90 <= code < 100:
        return "Hopper CC 9.x"
    if 100 <= code < 120:
        return "Blackwell Data Center CC 10.x/11.x"
    if 120 <= code < 130:
        return "Blackwell CC 12.x"
    return f"未在本实验表中建模的 CC {major}.{minor}"


def occupancy(profile, threads_per_block, regs_per_thread, shared_kb):
    warps_per_block = math.ceil(threads_per_block / 32)
    by_threads = profile["threads"] // threads_per_block
    by_warps = profile["warps"] // warps_per_block
    regs_per_block = regs_per_thread * threads_per_block
    by_regs = profile["registers"] // regs_per_block if regs_per_block else 10**9
    shared_bytes = shared_kb * 1024
    by_shared = ((profile["shared_kb"] * 1024) // shared_bytes
                 if shared_bytes else 10**9)
    limits = {
        "hardware_blocks": profile["blocks"],
        "threads": by_threads,
        "warps": by_warps,
        "registers": by_regs,
        "shared_memory": by_shared,
    }
    active_blocks = max(0, min(limits.values()))
    active_warps = min(profile["warps"], active_blocks * warps_per_block)
    limiting = [k for k, v in limits.items() if v == active_blocks]
    return {
        "threads_per_block": threads_per_block,
        "regs_per_thread": regs_per_thread,
        "shared_kb_per_block": shared_kb,
        "active_blocks_per_sm": active_blocks,
        "active_warps_per_sm": active_warps,
        "occupancy": round(active_warps / profile["warps"], 4),
        "limiting_resources": limiting,
    }


def divergence_model(prob_true, warps=20000, seed=7):
    rng = random.Random(seed)
    useful = 0
    issued_slots = 0
    divergent = 0
    for _ in range(warps):
        true_lanes = sum(rng.random() < prob_true for _ in range(32))
        false_lanes = 32 - true_lanes
        useful += 32
        if true_lanes == 0 or false_lanes == 0:
            issued_slots += 32
        else:
            divergent += 1
            # 简化模型：两条等成本路径分别发射一次，每次覆盖 32 个槽位。
            issued_slots += 64
    return {
        "p_true": prob_true,
        "divergent_warp_ratio": round(divergent / warps, 4),
        "simplified_branch_efficiency": round(useful / issued_slots, 4),
    }


def coalescing_model(stride, element_bytes=4, segment_bytes=32):
    addresses = [lane * stride * element_bytes for lane in range(32)]
    segments = {addr // segment_bytes for addr in addresses}
    requested = 32 * element_bytes
    transferred = len(segments) * segment_bytes
    return {
        "stride": stride,
        "segments": len(segments),
        "requested_bytes": requested,
        "modeled_transferred_bytes": transferred,
        "modeled_efficiency": round(requested / transferred, 4),
    }


def roofline_model(peak_tflops, bandwidth_gbs):
    rows = []
    for ai in [0.25, 0.5, 1, 2, 4, 8, 16, 32, 64, 128]:
        bandwidth_roof = bandwidth_gbs * ai / 1000.0
        rows.append({
            "arithmetic_intensity_flop_per_byte": ai,
            "roof_tflops": round(min(peak_tflops, bandwidth_roof), 4),
            "bound": "memory" if bandwidth_roof < peak_tflops else "compute",
        })
    return {
        "peak_tflops": peak_tflops,
        "bandwidth_gbs": bandwidth_gbs,
        "ridge_point_flop_per_byte": round(peak_tflops * 1000 / bandwidth_gbs, 4),
        "rows": rows,
    }


def bench_torch(device_name, elements, matrix_n, repeat):
    try:
        import torch
    except ImportError:
        return {"available": False, "reason": "未安装 PyTorch"}

    if device_name == "auto":
        device_name = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device_name)
    info = {
        "available": True,
        "torch_version": torch.__version__,
        "device": str(device),
    }
    if device.type == "cuda":
        idx = device.index if device.index is not None else torch.cuda.current_device()
        prop = torch.cuda.get_device_properties(idx)
        major, minor = torch.cuda.get_device_capability(idx)
        info.update({
            "gpu_name": prop.name,
            "compute_capability": f"{major}.{minor}",
            "architecture": architecture_from_cc(major, minor),
            "memory_gib": round(prop.total_memory / 2**30, 2),
            "cuda_runtime": torch.version.cuda,
        })

    def sync():
        if device.type == "cuda":
            torch.cuda.synchronize(device)

    def median_ms(fn, warmup=5):
        for _ in range(warmup):
            fn()
        sync()
        samples = []
        for _ in range(repeat):
            start = time.perf_counter()
            fn()
            sync()
            samples.append((time.perf_counter() - start) * 1000)
        return statistics.median(samples)

    # 每个用例先分配，再计时，避免把 allocator 时间算进 Kernel。
    x = torch.randn(elements, device=device, dtype=torch.float32)
    y = torch.randn(elements, device=device, dtype=torch.float32)
    add_ms = median_ms(lambda: torch.add(x, y))
    add_gbs = (elements * 4 * 3) / (add_ms / 1000) / 1e9

    # 两个视图都归约 elements 个元素；跨步视图来自更大的底层张量。
    stride = 8
    base = torch.randn(elements * stride, device=device, dtype=torch.float32)
    contiguous = base[:elements]
    strided = base[::stride]
    contiguous_ms = median_ms(lambda: contiguous.sum())
    strided_ms = median_ms(lambda: strided.sum())

    a = torch.randn((matrix_n, matrix_n), device=device, dtype=torch.float32)
    b = torch.randn((matrix_n, matrix_n), device=device, dtype=torch.float32)
    matmul_ms = median_ms(lambda: torch.mm(a, b), warmup=3)
    matmul_tflops = (2 * matrix_n**3) / (matmul_ms / 1000) / 1e12

    info["measurements"] = {
        "elementwise_add": {
            "elements": elements,
            "median_ms": round(add_ms, 4),
            "estimated_gbs": round(add_gbs, 2),
        },
        "sum_layout": {
            "elements_each": elements,
            "contiguous_ms": round(contiguous_ms, 4),
            "stride": stride,
            "strided_ms": round(strided_ms, 4),
            "slowdown": round(strided_ms / contiguous_ms, 2),
        },
        "fp32_matmul": {
            "n": matrix_n,
            "median_ms": round(matmul_ms, 4),
            "estimated_tflops": round(matmul_tflops, 3),
        },
    }
    return info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cc", choices=ARCH, default="86")
    parser.add_argument("--threads", type=int, default=256)
    parser.add_argument("--regs", type=int, default=64)
    parser.add_argument("--shared-kb", type=int, default=32)
    parser.add_argument("--peak-tflops", type=float, default=30.0)
    parser.add_argument("--bandwidth-gbs", type=float, default=700.0)
    parser.add_argument("--torch", action="store_true")
    parser.add_argument("--device", default="auto")
    parser.add_argument("--elements", type=int, default=1_000_000)
    parser.add_argument("--matrix-n", type=int, default=1024)
    parser.add_argument("--repeat", type=int, default=10)
    args = parser.parse_args()

    profile = ARCH[args.cc]
    result = {
        "architecture_profile": profile,
        "occupancy": occupancy(
            profile, args.threads, args.regs, args.shared_kb
        ),
        "occupancy_sweep": [
            occupancy(profile, t, args.regs, args.shared_kb)
            for t in (64, 128, 256, 512, 1024)
            if t <= 1024
        ],
        "divergence": [divergence_model(p) for p in (0.0, 0.1, 0.5, 0.9, 1.0)],
        "coalescing": [coalescing_model(s) for s in (1, 2, 4, 8, 16)],
        "roofline": roofline_model(args.peak_tflops, args.bandwidth_gbs),
    }
    if args.torch:
        result["torch_benchmark"] = bench_torch(
            args.device, args.elements, args.matrix_n, args.repeat
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
