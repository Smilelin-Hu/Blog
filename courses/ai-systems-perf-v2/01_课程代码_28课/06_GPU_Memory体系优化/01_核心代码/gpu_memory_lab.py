#!/usr/bin/env python3
import argparse
import gc
import json
import math
import statistics
import time


def transaction_model(stride, offset_bytes=0, element_bytes=4,
                      lanes=32, segment_bytes=32):
    addresses = [offset_bytes + lane * stride * element_bytes
                 for lane in range(lanes)]
    segments = {addr // segment_bytes for addr in addresses}
    requested = lanes * element_bytes
    actual = len(segments) * segment_bytes
    return {
        "stride_elements": stride,
        "offset_bytes": offset_bytes,
        "segments": len(segments),
        "requested_bytes": requested,
        "modeled_actual_bytes": actual,
        "efficiency": round(requested / actual, 4),
    }


def bank_model(stride_words, lanes=32, banks=32):
    bank_hits = [0] * banks
    for lane in range(lanes):
        bank = (lane * stride_words) % banks
        bank_hits[bank] += 1
    nonzero = [x for x in bank_hits if x]
    return {
        "stride_words": stride_words,
        "banks_touched": len(nonzero),
        "max_conflict_degree": max(nonzero),
        "idealized_rounds": max(nonzero),
        "bank_hits": bank_hits,
    }


def capacity_model(params_billion, bytes_per_param,
                   grad_bytes, optimizer_bytes, activation_gib,
                   workspace_gib, fragmentation_ratio):
    n = params_billion * 1e9
    param = n * bytes_per_param
    grad = n * grad_bytes
    optimizer = n * optimizer_bytes
    base = param + grad + optimizer + (activation_gib + workspace_gib) * 2**30
    total = base * (1 + fragmentation_ratio)
    return {
        "parameter_gib": round(param / 2**30, 3),
        "gradient_gib": round(grad / 2**30, 3),
        "optimizer_gib": round(optimizer / 2**30, 3),
        "activation_gib": activation_gib,
        "workspace_gib": workspace_gib,
        "fragmentation_ratio": fragmentation_ratio,
        "estimated_total_gib": round(total / 2**30, 3),
        "warning": "教学估算，不包含框架、通信和所有临时张量",
    }


def cpu_copy_benchmark(size_mib, repeat):
    size = size_mib * 2**20
    src = bytearray(size)
    dst = bytearray(size)
    samples = []
    for _ in range(3):
        dst[:] = src
    for _ in range(repeat):
        start = time.perf_counter()
        dst[:] = src
        samples.append(time.perf_counter() - start)
    median = statistics.median(samples)
    return {
        "size_mib": size_mib,
        "median_ms": round(median * 1000, 4),
        "logical_copy_gbs": round(size / median / 1e9, 3),
        "note": "Python bytearray CPU 回退结果，不代表 GPU 带宽",
    }


def torch_benchmark(elements, matrix_rows, matrix_cols, repeat,
                    fragmentation_demo):
    try:
        import torch
    except ImportError:
        return {"available": False, "reason": "未安装 PyTorch"}

    use_cuda = torch.cuda.is_available()
    device = torch.device("cuda" if use_cuda else "cpu")
    result = {
        "available": True,
        "torch_version": torch.__version__,
        "device": str(device),
    }
    if use_cuda:
        prop = torch.cuda.get_device_properties(0)
        cc = torch.cuda.get_device_capability(0)
        result.update({
            "gpu": prop.name,
            "compute_capability": f"{cc[0]}.{cc[1]}",
            "total_memory_gib": round(prop.total_memory / 2**30, 3),
            "cuda_runtime": torch.version.cuda,
        })

    def sync():
        if use_cuda:
            torch.cuda.synchronize()

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

    # 低算术强度：两读一写，按逻辑字节估算有效带宽。
    x = torch.randn(elements, device=device, dtype=torch.float32)
    y = torch.randn(elements, device=device, dtype=torch.float32)
    add_ms = median_ms(lambda: torch.add(x, y))
    add_bytes = elements * 4 * 3

    # 连续与跨步视图都归约相同数量的元素。
    stride = 8
    base = torch.randn(elements * stride, device=device, dtype=torch.float32)
    contiguous = base[:elements]
    strided = base[::stride]
    contiguous_ms = median_ms(lambda: contiguous.sum())
    strided_ms = median_ms(lambda: strided.sum())

    # 同样的元素数，比较 contiguous 和 transpose view 的逐元素读取。
    matrix = torch.randn((matrix_rows, matrix_cols),
                         device=device, dtype=torch.float32)
    transposed = matrix.t()
    transpose_view_ms = median_ms(lambda: transposed * 1.0001)
    transpose_copy_ms = median_ms(lambda: transposed.contiguous())

    result["device_memory"] = {
        "elementwise_add": {
            "elements": elements,
            "median_ms": round(add_ms, 4),
            "effective_gbs": round(add_bytes / (add_ms / 1000) / 1e9, 3),
        },
        "contiguous_vs_stride_sum": {
            "elements_each": elements,
            "contiguous_ms": round(contiguous_ms, 4),
            "stride": stride,
            "strided_ms": round(strided_ms, 4),
            "slowdown": round(strided_ms / contiguous_ms, 3),
        },
        "transpose": {
            "shape": [matrix_rows, matrix_cols],
            "is_contiguous": transposed.is_contiguous(),
            "elementwise_read_ms": round(transpose_view_ms, 4),
            "materialize_contiguous_ms": round(transpose_copy_ms, 4),
        },
    }

    if use_cuda:
        # 分配 pageable 与预先 pinned 的 Host Tensor；拷贝后同步以测完成时间。
        host_pageable = torch.randn(elements, dtype=torch.float32)
        try:
            host_pinned = torch.randn(elements, dtype=torch.float32,
                                      pin_memory=True)

            pageable_ms = median_ms(
                lambda: host_pageable.to("cuda", non_blocking=False), warmup=3
            )
            pinned_sync_ms = median_ms(
                lambda: host_pinned.to("cuda", non_blocking=False), warmup=3
            )
            pinned_async_ms = median_ms(
                lambda: host_pinned.to("cuda", non_blocking=True), warmup=3
            )
            copy_bytes = elements * 4
            result["host_to_device"] = {
                "bytes": copy_bytes,
                "pageable_blocking_ms": round(pageable_ms, 4),
                "pinned_blocking_ms": round(pinned_sync_ms, 4),
                "pinned_non_blocking_completed_ms": round(pinned_async_ms, 4),
                "pinned_non_blocking_effective_gbs": round(
                    copy_bytes / (pinned_async_ms / 1000) / 1e9, 3
                ),
                "note": "计时包含最终同步，测的是完成时间；单拷贝不等于重叠流水",
            }
        except RuntimeError as exc:
            result["host_to_device"] = {
                "skipped": True,
                "reason": str(exc).splitlines()[0],
            }

        gc.collect()
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
        before = {
            "allocated_mib": round(torch.cuda.memory_allocated() / 2**20, 3),
            "reserved_mib": round(torch.cuda.memory_reserved() / 2**20, 3),
        }
        chunks = [torch.empty(16 * 2**20 // 4, device="cuda")
                  for _ in range(8)]
        live = {
            "allocated_mib": round(torch.cuda.memory_allocated() / 2**20, 3),
            "reserved_mib": round(torch.cuda.memory_reserved() / 2**20, 3),
        }
        del chunks[::2]
        gc.collect()
        after_delete = {
            "allocated_mib": round(torch.cuda.memory_allocated() / 2**20, 3),
            "reserved_mib": round(torch.cuda.memory_reserved() / 2**20, 3),
        }
        torch.cuda.empty_cache()
        after_empty_cache = {
            "allocated_mib": round(torch.cuda.memory_allocated() / 2**20, 3),
            "reserved_mib": round(torch.cuda.memory_reserved() / 2**20, 3),
        }
        result["allocator"] = {
            "before": before,
            "with_live_tensors": live,
            "after_delete_half": after_delete,
            "after_empty_cache": after_empty_cache,
            "peak_allocated_mib": round(
                torch.cuda.max_memory_allocated() / 2**20, 3
            ),
        }
        del chunks
        gc.collect()
        torch.cuda.empty_cache()

        if fragmentation_demo:
            result["allocator"]["memory_summary"] = \
                torch.cuda.memory_summary(abbreviated=True)
    else:
        result["host_to_device"] = {
            "skipped": True,
            "reason": "CPU 回退没有 CUDA Host↔Device 链路",
        }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--size-mib", type=int, default=64)
    parser.add_argument("--repeat", type=int, default=10)
    parser.add_argument("--torch", action="store_true")
    parser.add_argument("--elements", type=int, default=1_000_000)
    parser.add_argument("--matrix-rows", type=int, default=1024)
    parser.add_argument("--matrix-cols", type=int, default=1024)
    parser.add_argument("--fragmentation-demo", action="store_true")
    parser.add_argument("--params-billion", type=float, default=7.0)
    parser.add_argument("--bytes-per-param", type=float, default=2.0)
    parser.add_argument("--grad-bytes", type=float, default=2.0)
    parser.add_argument("--optimizer-bytes", type=float, default=8.0)
    parser.add_argument("--activation-gib", type=float, default=4.0)
    parser.add_argument("--workspace-gib", type=float, default=1.0)
    parser.add_argument("--fragmentation-ratio", type=float, default=0.1)
    args = parser.parse_args()

    output = {
        "global_transactions": [
            transaction_model(stride, offset)
            for stride in (1, 2, 4, 8, 16)
            for offset in (0, 4)
        ],
        "shared_memory_banks": [
            bank_model(stride) for stride in (1, 2, 4, 8, 16, 32, 33)
        ],
        "capacity": capacity_model(
            args.params_billion, args.bytes_per_param,
            args.grad_bytes, args.optimizer_bytes,
            args.activation_gib, args.workspace_gib,
            args.fragmentation_ratio,
        ),
        "cpu_copy": cpu_copy_benchmark(args.size_mib, args.repeat),
    }
    if args.torch:
        output["torch"] = torch_benchmark(
            args.elements, args.matrix_rows, args.matrix_cols,
            args.repeat, args.fragmentation_demo
        )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
