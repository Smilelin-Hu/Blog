#!/usr/bin/env python3
import argparse
import statistics
import time

import torch
from torch import nn


class LaunchBoundModel(nn.Module):
    def __init__(self, depth):
        super().__init__()
        self.depth = depth

    def forward(self, x):
        # 有意保留多个短 pointwise 算子，突出 Runtime 开销
        for _ in range(self.depth):
            x = torch.tanh(x) * 0.75 + torch.sigmoid(x) * 0.25
        return x


def sync():
    torch.cuda.synchronize()


def gpu_time_ms(fn, iterations):
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    for _ in range(iterations):
        fn()
    end.record()
    end.synchronize()
    return start.elapsed_time(end) / iterations


def cpu_submit_us(fn, iterations):
    sync()
    samples = []
    for _ in range(5):
        t0 = time.perf_counter()
        for _ in range(iterations):
            fn()
        submit_us = (time.perf_counter() - t0) * 1e6 / iterations
        sync()
        samples.append(submit_us)
    return statistics.median(samples)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--width", type=int, default=4096)
    p.add_argument("--depth", type=int, default=16)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--iterations", type=int, default=100)
    args = p.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("需要可用的 NVIDIA CUDA GPU；无 GPU 请运行 Level 0")
    if min(args.batch, args.width, args.depth, args.warmup, args.iterations) < 1:
        raise SystemExit("所有整数参数必须为正数")

    device = torch.device("cuda")
    prop = torch.cuda.get_device_properties(device)
    print(f"torch={torch.__version__} cuda={torch.version.cuda}")
    print(f"gpu={prop.name} capability={prop.major}.{prop.minor} "
          f"vram_gib={prop.total_memory / 2**30:.2f}")

    torch.manual_seed(0)
    model = LaunchBoundModel(args.depth).eval().to(device)
    static_input = torch.randn(args.batch, args.width, device=device)

    # 必须在 Side Stream 预热，完成 Lazy 初始化和内存池准备。
    warmup_stream = torch.cuda.Stream()
    warmup_stream.wait_stream(torch.cuda.current_stream())
    with torch.cuda.stream(warmup_stream), torch.inference_mode():
        for _ in range(args.warmup):
            model(static_input)
    torch.cuda.current_stream().wait_stream(warmup_stream)
    sync()

    graph = torch.cuda.CUDAGraph()
    capture_begin = time.perf_counter()
    with torch.inference_mode(), torch.cuda.graph(graph):
        static_output = model(static_input)
    sync()
    capture_ms = (time.perf_counter() - capture_begin) * 1000.0

    # 新输入必须 copy 到捕获时的静态地址。
    real_input = torch.randn_like(static_input)
    with torch.inference_mode():
        reference = model(real_input)
        static_input.copy_(real_input)
        graph.replay()
    sync()
    torch.testing.assert_close(static_output, reference, rtol=2e-4, atol=2e-4)

    with torch.inference_mode():
        eager = lambda: model(real_input)
        replay_only = graph.replay

        def copy_and_replay():
            static_input.copy_(real_input)
            graph.replay()

        # 再预热计时路径
        for _ in range(5):
            eager()
            replay_only()
            copy_and_replay()
        sync()

        eager_gpu = gpu_time_ms(eager, args.iterations)
        graph_gpu = gpu_time_ms(replay_only, args.iterations)
        graph_copy_gpu = gpu_time_ms(copy_and_replay, args.iterations)
        eager_submit = cpu_submit_us(eager, args.iterations)
        graph_submit = cpu_submit_us(replay_only, args.iterations)
        graph_copy_submit = cpu_submit_us(copy_and_replay, args.iterations)

    print(f"capture_and_instantiate_ms={capture_ms:.3f}")
    print(f"eager_gpu_ms={eager_gpu:.4f}")
    print(f"graph_replay_gpu_ms={graph_gpu:.4f}")
    print(f"graph_copy_replay_gpu_ms={graph_copy_gpu:.4f}")
    print(f"eager_cpu_submit_us={eager_submit:.3f}")
    print(f"graph_replay_cpu_submit_us={graph_submit:.3f}")
    print(f"graph_copy_replay_cpu_submit_us={graph_copy_submit:.3f}")
    print(f"replay_speedup={eager_gpu / graph_gpu:.3f}x")
    print(f"copy_replay_speedup={eager_gpu / graph_copy_gpu:.3f}x")
    print(f"peak_allocated_mib={torch.cuda.max_memory_allocated()/2**20:.1f}")
    print(f"peak_reserved_mib={torch.cuda.max_memory_reserved()/2**20:.1f}")


if __name__ == "__main__":
    main()
