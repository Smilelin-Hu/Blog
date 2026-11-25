#!/usr/bin/env python3
"""通用 GPU 互联实验：Level 0 模型 + Level 1 可选 PyTorch 实测。"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass


@dataclass
class Link:
    name: str
    bandwidth_gbs: float
    latency_us: float


def transfer_ms(size_mib: float, link: Link, steps: int = 1,
                volume_factor: float = 1.0) -> float:
    """十进制 GB/s + 二进制 MiB；返回教学模型时间，不代表硬件实测。"""
    size_bytes = size_mib * 1024**2 * volume_factor
    return steps * link.latency_us / 1000.0 + size_bytes / (link.bandwidth_gbs * 1e9) * 1000.0


def ring_allreduce_ms(size_mib: float, ranks: int, link: Link) -> float:
    if ranks < 2:
        return 0.0
    steps = 2 * (ranks - 1)
    volume = 2 * (ranks - 1) / ranks
    # 延迟按步数计算，Payload 总量按 volume 计算。
    return steps * link.latency_us / 1000.0 + transfer_ms(
        size_mib, link, steps=0, volume_factor=volume
    )


def recursive_doubling_ms(size_mib: float, ranks: int, link: Link) -> float:
    """小消息教学近似；非 2 次幂 Rank 与 NCCL 实现会有不同路径。"""
    if ranks < 2:
        return 0.0
    steps = math.ceil(math.log2(ranks))
    return transfer_ms(size_mib, link, steps=steps, volume_factor=steps)


def hierarchical_ms(size_mib: float, gpus_per_node: int, nodes: int,
                    intra: Link, inter: Link) -> float:
    if nodes < 2:
        return ring_allreduce_ms(size_mib, gpus_per_node, intra)
    local_steps = math.ceil(math.log2(max(gpus_per_node, 1)))
    local_reduce = transfer_ms(size_mib, intra, local_steps, local_steps)
    inter_reduce = ring_allreduce_ms(size_mib, nodes, inter)
    local_broadcast = transfer_ms(size_mib, intra, local_steps, local_steps)
    return local_reduce + inter_reduce + local_broadcast


def run_level0(args: argparse.Namespace) -> dict:
    intra = Link("intra", args.intra_gbs, args.intra_latency_us)
    inter = Link("inter", args.inter_gbs, args.inter_latency_us)
    rows = []
    for size in args.sizes_mib:
        ring = ring_allreduce_ms(size, args.ranks, intra)
        tree = recursive_doubling_ms(size, args.ranks, intra)
        hier = hierarchical_ms(size, args.gpus_per_node, args.nodes, intra, inter)
        for algorithm, comm_ms in (
            ("ring", ring),
            ("recursive_doubling_teaching_model", tree),
            ("hierarchical_teaching_model", hier),
        ):
            efficiency = args.compute_ms / (args.compute_ms + comm_ms)
            rows.append({
                "size_mib": size,
                "algorithm": algorithm,
                "comm_ms": round(comm_ms, 4),
                "compute_ms": args.compute_ms,
                "efficiency_without_overlap": round(efficiency, 4),
            })
    return {
        "warning": "All bandwidth/latency inputs are user assumptions, not measured hardware specs.",
        "intra_link": asdict(intra),
        "inter_link": asdict(inter),
        "ranks": args.ranks,
        "gpus_per_node": args.gpus_per_node,
        "nodes": args.nodes,
        "results": rows,
    }


def command_output(argv: list[str]) -> str:
    if not shutil.which(argv[0]):
        return f"{argv[0]} not found"
    result = subprocess.run(argv, capture_output=True, text=True, timeout=15,
                            check=False)
    text = (result.stdout or result.stderr).strip()
    return text if text else f"exit_code={result.returncode}"


def sync_pair(torch, a: int, b: int) -> None:
    torch.cuda.synchronize(a)
    torch.cuda.synchronize(b)


def benchmark_cross_device_copy(torch, src_device: int, dst_device: int,
                                size_mib: int, warmup: int, repeat: int) -> dict:
    elements = size_mib * 1024**2 // 4
    with torch.cuda.device(src_device):
        src = torch.arange(elements, dtype=torch.float32, device=src_device)
    with torch.cuda.device(dst_device):
        dst = torch.empty(elements, dtype=torch.float32, device=dst_device)

    for _ in range(warmup):
        dst.copy_(src, non_blocking=True)
    sync_pair(torch, src_device, dst_device)

    start = time.perf_counter()
    for _ in range(repeat):
        dst.copy_(src, non_blocking=True)
    sync_pair(torch, src_device, dst_device)
    elapsed_s = (time.perf_counter() - start) / repeat

    # 抽样检查，避免把完整 Tensor 拷回 CPU 干扰计时。
    sample_idx = torch.tensor([0, elements // 2, elements - 1], device=dst_device)
    got = dst[sample_idx].cpu()
    expected = torch.tensor([0, elements // 2, elements - 1], dtype=torch.float32)
    correct = bool(torch.equal(got, expected))
    gib_per_s = (size_mib / 1024.0) / elapsed_s
    return {
        "size_mib": size_mib,
        "latency_ms": round(elapsed_s * 1000, 4),
        "effective_gib_s": round(gib_per_s, 3),
        "sample_correct": correct,
        "label": "cross-device copy; path must be interpreted with topology/P2P data",
    }


def benchmark_host_staged(torch, src_device: int, dst_device: int,
                          size_mib: int, warmup: int, repeat: int) -> dict:
    elements = size_mib * 1024**2 // 4
    with torch.cuda.device(src_device):
        src = torch.ones(elements, dtype=torch.float32, device=src_device)
    host = torch.empty(elements, dtype=torch.float32, pin_memory=True)
    with torch.cuda.device(dst_device):
        dst = torch.empty(elements, dtype=torch.float32, device=dst_device)

    def one_copy() -> None:
        host.copy_(src, non_blocking=True)
        torch.cuda.synchronize(src_device)
        dst.copy_(host, non_blocking=True)
        torch.cuda.synchronize(dst_device)

    for _ in range(warmup):
        one_copy()
    start = time.perf_counter()
    for _ in range(repeat):
        one_copy()
    elapsed_s = (time.perf_counter() - start) / repeat
    correct = float(dst[0].item()) == 1.0 and float(dst[-1].item()) == 1.0
    gib_per_s = (size_mib / 1024.0) / elapsed_s
    return {
        "size_mib": size_mib,
        "latency_ms": round(elapsed_s * 1000, 4),
        "effective_payload_gib_s": round(gib_per_s, 3),
        "sample_correct": correct,
        "label": "explicit GPU->pinned-host->GPU baseline; two transfer legs",
    }


def run_level1(args: argparse.Namespace) -> dict:
    try:
        import torch
    except ImportError:
        return {"skipped": "PyTorch not installed; Level 0 remains fully usable."}

    result = {
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": torch.cuda.is_available(),
        "topology": command_output(["nvidia-smi", "topo", "-m"]),
        "nvlink_status": command_output(["nvidia-smi", "nvlink", "--status"]),
    }
    if not torch.cuda.is_available():
        result["skipped"] = "CUDA unavailable."
        return result

    count = torch.cuda.device_count()
    result["gpus"] = [
        {
            "index": i,
            "name": torch.cuda.get_device_name(i),
            "compute_capability": list(torch.cuda.get_device_capability(i)),
            "memory_gib": round(torch.cuda.get_device_properties(i).total_memory / 1024**3, 2),
        }
        for i in range(count)
    ]
    result["peer_access_matrix"] = [
        [True if i == j else bool(torch.cuda.can_device_access_peer(i, j))
         for j in range(count)]
        for i in range(count)
    ]
    if count < 2:
        result["skipped"] = "Need at least two visible CUDA GPUs for copy benchmark."
        return result

    result["copy_0_to_1"] = []
    result["host_staged_0_to_1"] = []
    for size in args.gpu_sizes_mib:
        try:
            result["copy_0_to_1"].append(
                benchmark_cross_device_copy(torch, 0, 1, size, args.warmup, args.repeat)
            )
            result["host_staged_0_to_1"].append(
                benchmark_host_staged(torch, 0, 1, size, args.warmup, args.repeat)
            )
        except RuntimeError as exc:
            result.setdefault("errors", []).append({"size_mib": size, "error": str(exc)})
            break
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", choices=("0", "1", "all"), default="all")
    parser.add_argument("--sizes-mib", type=float, nargs="+", default=[0.004, 1, 64, 1024])
    parser.add_argument("--ranks", type=int, default=8)
    parser.add_argument("--gpus-per-node", type=int, default=4)
    parser.add_argument("--nodes", type=int, default=2)
    parser.add_argument("--intra-gbs", type=float, default=25.0)
    parser.add_argument("--intra-latency-us", type=float, default=8.0)
    parser.add_argument("--inter-gbs", type=float, default=12.5)
    parser.add_argument("--inter-latency-us", type=float, default=20.0)
    parser.add_argument("--compute-ms", type=float, default=50.0)
    parser.add_argument("--gpu-sizes-mib", type=int, nargs="+", default=[4, 64, 256])
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--repeat", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = {}
    if args.level in ("0", "all"):
        output["level0"] = run_level0(args)
    if args.level in ("1", "all"):
        output["level1"] = run_level1(args)
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
