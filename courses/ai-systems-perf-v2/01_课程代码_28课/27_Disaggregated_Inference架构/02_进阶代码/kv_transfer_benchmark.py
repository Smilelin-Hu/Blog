#!/usr/bin/env python3
import argparse
import time
import torch


def sync_all():
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            torch.cuda.synchronize(i)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mib", type=int, default=256)
    p.add_argument("--iters", type=int, default=30)
    p.add_argument("--warmup", type=int, default=5)
    a = p.parse_args()
    n = a.mib * 1024 * 1024 // 2  # FP16 元素数

    print("torch=", torch.__version__, "cuda=", torch.version.cuda)
    print("gpu_count=", torch.cuda.device_count())
    if torch.cuda.device_count() >= 2:
        src = torch.empty(n, dtype=torch.float16, device="cuda:0").normal_()
        dst = torch.empty_like(src, device="cuda:1")
        print("src=", torch.cuda.get_device_name(0))
        print("dst=", torch.cuda.get_device_name(1))
        print("peer_access=", torch.cuda.can_device_access_peer(0, 1))

        def copy_once():
            with torch.cuda.device(1):
                dst.copy_(src, non_blocking=True)

        route = "GPU0 -> GPU1"
    elif torch.cuda.device_count() == 1:
        src = torch.empty(n, dtype=torch.float16, device="cuda:0").normal_()
        host = torch.empty(n, dtype=torch.float16, pin_memory=True)
        dst = torch.empty_like(src)
        print("gpu=", torch.cuda.get_device_name(0))

        def copy_once():
            host.copy_(src, non_blocking=True)
            dst.copy_(host, non_blocking=True)

        route = "GPU -> pinned CPU -> GPU round trip"
    else:
        src = torch.empty(n, dtype=torch.float16).normal_()
        dst = torch.empty_like(src)

        def copy_once():
            dst.copy_(src)

        route = "CPU memory copy"

    for _ in range(a.warmup):
        copy_once()
    sync_all()
    t0 = time.perf_counter()
    for _ in range(a.iters):
        copy_once()
    sync_all()
    elapsed = time.perf_counter() - t0
    bytes_per_iter = a.mib * 1024 * 1024
    if torch.cuda.device_count() == 1:
        bytes_per_iter *= 2
    gib_s = bytes_per_iter * a.iters / elapsed / 2**30
    print(f"route={route}")
    print(f"payload={a.mib} MiB iterations={a.iters}")
    print(f"mean_latency={elapsed/a.iters*1000:.3f} ms")
    print(f"effective_bandwidth={gib_s:.3f} GiB/s")
    print("该结果只代表当前路径与并发条件，不等于链路标称带宽。")


if __name__ == "__main__":
    main()
