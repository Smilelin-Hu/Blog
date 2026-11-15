# GPU 性能分析实验

本项目使用真实分析流程定位 GPU 性能瓶颈，并输出可复现的测量结果与优化报告。

它把前面最重要的一条方法论真正跑通：**不要凭 GPU 利用率猜瓶颈，要用可复现基准、系统时间线与 Kernel 指标建立证据链。** 从一个同时包含「小算子启动开销、显存流量与矩阵乘法」的 PyTorch 工作负载出发，依次完成：固化环境与工作负载 → 建立无 Profiler 的墙钟基线 → 用 PyTorch Profiler 找到高开销算子 → 用 Nsight Systems 判断 CPU、CUDA API、Memcpy 与 GPU Kernel 的时间关系 → 用 Nsight Compute 深入一个 Kernel，判断它受计算、带宽、延迟还是资源限制 → 只修改一个变量，验证正确性并复测 → 输出一份别人可以复现、审阅与继续优化的性能报告。

项目不要求特定 GPU。没有 NVIDIA GPU 时可以完整完成 Level 0，并在 CPU 上完成 Level 1 的方法训练；有常见 NVIDIA GPU 时完成 CUDA 路径；Nsight Compute 硬件计数器不可用时，保留 PyTorch Profiler 与 Nsight Systems 证据，不伪造 Kernel 级结论。

## 1. 内容概览与交付物

做完之后应当能够：区分基准测试、系统级 Profiling 与 Kernel 级 Profiling；正确测量异步 CUDA 工作负载，不把 CPU 提交时间当成 GPU 执行时间；根据时间线识别 Launch-bound、Memory-bound、Compute-bound 与同步等待；用算术强度与 Roofline 为优化方向设定上界；用 PyTorch Profiler、NVTX、Nsight Systems 与 Nsight Compute 形成逐层下钻的证据链；避免「同时改很多变量」「只跑一次」「只看平均值」等常见实验错误。

前置知识：能运行 Python 与基础 Bash 命令；理解 Latency、Throughput、P50/P95/P99；理解 GPU Kernel、CUDA Stream、异步执行与显存层级；理解算术强度、Roofline、Occupancy 的基本含义。可选：已安装 PyTorch、CUDA Toolkit、Nsight Systems、Nsight Compute。

建议建立如下目录：

```text
gpu-profiling-project/
├── roofline_planner.py
├── gpu_profiling_lab.py
├── reports/
│   ├── environment.txt
│   ├── roofline.json
│   ├── benchmark.json
│   ├── pytorch_trace.json
│   ├── nsys_baseline.nsys-rep
│   └── ncu_matmul.ncu-rep
└── analysis.md
```

并在 `analysis.md` 中回答四个问题：

1. 当前最主要的瓶颈是什么？
2. 哪些证据支持这个判断？
3. 修改了哪个变量，为什么？
4. 提升是否通过正确性、稳定性与跨尺寸复测？

## 2. 核心直觉：Profiler 是显微镜，不是秒表

性能工程应按由粗到细的顺序推进：

```text
业务指标异常
  ↓
可复现墙钟基准：问题真的存在吗？
  ↓
系统时间线：时间花在 CPU、I/O、通信还是 GPU？
  ↓
框架算子：哪个算子或阶段最贵？
  ↓
Kernel 指标：为什么这个 Kernel 慢？
  ↓
单变量优化 → 正确性检查 → 复测 → 回归门禁
```

Profiler 会增加开销，因此不能用带完整 Profiler 的一次运行替代正常基准。正确做法是：用轻量墙钟基准确认问题与收益；用 Profiler 解释原因；用不带 Profiler 的重复实验确认最终收益。

## 3. 性能模型

### 3.1 端到端延迟

对一组重复测量值排序后，使用中位数与尾延迟：

$$
P_q = \operatorname{percentile}(t_1, t_2, \ldots, t_n, q)
$$

小型实验至少报告 P50 与 P95。平均值容易被初始化、缓存填充、频率变化与偶发系统抖动影响。

### 3.2 加速比

$$
S = \frac{T_{baseline}}{T_{optimized}}
$$

$S > 1$ 表示优化后更快。只有在输入、精度、输出语义与测量策略相同时，这个比值才有意义。

### 3.3 有效带宽

若一次算子最少读写 $B$ 字节，耗时为 $t$：

$$
BW_{effective} = \frac{B}{t}
$$

它是算法层面的有效带宽，不等于 GPU 规格表峰值，也不等于 Nsight Compute 观察到的全部物理事务。

### 3.4 算术强度与 Roofline

$$
AI = \frac{FLOPs}{Bytes}
$$

$$
P_{attainable} \le \min(P_{peak},\; BW_{peak} \times AI)
$$

其中 $AI$ 是每搬运一个字节完成多少次浮点运算。屋脊转折点为

$$
AI_{ridge} = \frac{P_{peak}}{BW_{peak}}
$$

- $AI < AI_{ridge}$：更可能受内存带宽限制。
- $AI > AI_{ridge}$：更可能受计算峰值限制。
- 远低于两条屋脊：还可能受 Launch、依赖链、分支、Occupancy、同步或输入流水线限制。

Roofline 是方向模型，不是瓶颈判决器。最终判断要结合时间线与硬件指标。

## 4. 瓶颈诊断矩阵

| 现象 | 优先查看 | 可能原因 | 首个实验 |
| --- | --- | --- | --- |
| GPU 时间线有大量短 Kernel 与空隙 | Nsight Systems | Python/Launch-bound、同步过多 | 合并小算子或减少循环 |
| GPU 长时间空闲，CPU 线程繁忙 | PyTorch Profiler、OSRT | 数据准备、日志、锁、线程调度 | 关闭日志并隔离数据阶段 |
| 单个 Kernel 很长，DRAM 吞吐高 | Nsight Compute Memory | Memory-bound | 减少中间张量与内存流量 |
| 单个 Kernel 很长，计算管线高 | Nsight Compute SpeedOfLight | Compute-bound | 精度、Tensor Core、算法与 Tiling |
| Occupancy 低但吞吐不低 | Occupancy + Stall | 可能是合理资源交换 | 不要只为提高 Occupancy 改代码 |
| 每轮都出现同步锯齿 | CUDA API、NVTX | `.item()`、隐式同步、阻塞拷贝 | 删除或降低同步频率 |
| 多卡只有一个 Rank 落后 | 各 Rank 时间线 | 负载不均、拓扑、I/O、日志 | 分 Rank 采集并对齐 NVTX |

## 5. 实验前的测量纪律

### 5.1 冻结工作负载

每次比较必须保持一致：输入尺寸、数据类型与随机种子；PyTorch、CUDA、驱动与依赖版本；GPU 型号、GPU 数量与可见设备；Warmup 次数、正式迭代次数与统计方法；精度策略、编译开关与同步位置；正确性容差。

如果同时更换 GPU、PyTorch、精度与算法，只能把结果标为探索性观察，不能把收益归因给某一个优化。

### 5.2 记录环境

```bash
mkdir -p gpu-profiling-project/reports
cd gpu-profiling-project

{
  date -Iseconds
  uname -a
  lscpu | sed -n '1,25p'
  free -h
  command -v nvidia-smi >/dev/null && nvidia-smi -L
  command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,driver_version,memory.total,pci.bus_id,pstate,temperature.gpu,power.limit --format=csv
  command -v nvcc >/dev/null && nvcc --version
  command -v nsys >/dev/null && nsys --version
  command -v ncu >/dev/null && ncu --version
  python --version
} 2>&1 | tee reports/environment.txt
```

不要在报告中只写「RTX 3080」或「H100」。驱动、软件版本、功耗状态、温度与输入形状都可能改变结果。

## 6. Level 0：无 GPU 的 Roofline 与诊断训练

下面的脚本只依赖 Python 标准库。它根据 FLOPs、最小数据搬运量、设备峰值计算能力与内存带宽计算理论上界，并明确给出「模型推断」而不是「实测结论」。保存为 `roofline_planner.py`：

```python
#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

def analyze(flops, bytes_moved, peak_tflops, bandwidth_gbps):
    if min(flops, bytes_moved, peak_tflops, bandwidth_gbps) <= 0:
        raise ValueError("所有参数必须大于 0")

    peak_flops = peak_tflops * 1e12
    bandwidth = bandwidth_gbps * 1e9
    arithmetic_intensity = flops / bytes_moved
    ridge_point = peak_flops / bandwidth
    memory_roof = bandwidth * arithmetic_intensity
    attainable = min(peak_flops, memory_roof)
    lower_bound_seconds = flops / attainable
    bound = "memory-model-bound" if arithmetic_intensity < ridge_point else "compute-model-bound"

    return {
        "flops": flops,
        "bytes_moved": bytes_moved,
        "peak_tflops": peak_tflops,
        "bandwidth_gbps": bandwidth_gbps,
        "arithmetic_intensity_flop_per_byte": arithmetic_intensity,
        "ridge_point_flop_per_byte": ridge_point,
        "roofline_attainable_gflops": attainable / 1e9,
        "roofline_time_lower_bound_ms": lower_bound_seconds * 1e3,
        "model_classification": bound,
        "warning": "这是理论方向模型；真实瓶颈需由基准与 Profiler 验证。",
    }

def main():
    parser = argparse.ArgumentParser(description="通用 Roofline 规划器")
    parser.add_argument("--flops", type=float, default=2e9)
    parser.add_argument("--bytes", dest="bytes_moved", type=float, default=1e9)
    parser.add_argument("--peak-tflops", type=float, default=20.0)
    parser.add_argument("--bandwidth-gbps", type=float, default=500.0)
    parser.add_argument("--output", default="reports/roofline.json")
    args = parser.parse_args()

    result = analyze(
        args.flops,
        args.bytes_moved,
        args.peak_tflops,
        args.bandwidth_gbps,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

if __name__ == "__main__":
    main()
```

运行命令：

```bash
python roofline_planner.py \
  --flops 2000000000 \
  --bytes 1000000000 \
  --peak-tflops 20 \
  --bandwidth-gbps 500

python roofline_planner.py \
  --flops 2000000000000 \
  --bytes 1000000000 \
  --peak-tflops 20 \
  --bandwidth-gbps 500 \
  --output reports/roofline_compute_case.json
```

第一组的算术强度较低，模型会指向内存屋脊；第二组的算术强度较高，模型会指向计算屋脊。这里的峰值参数只是教学输入，不代表任何具体 GPU。正式分析时应填入当前精度、当前设备与当前功耗条件下对应的官方或实测上限。

两组实跑结果（峰值 20 TFLOPS、带宽 500 GB/s，屋脊点 40 FLOP/Byte）：

| 用例 | FLOPs | Bytes | AI | 可达 GFLOPS | 时间下界 | 分类 |
| --- | --- | --- | --- | --- | --- | --- |
| 低强度 | 2e9 | 1e9 | 2.0 | 1000 | 2.000 ms | memory-model-bound |
| 高强度 | 2e12 | 1e9 | 2000.0 | 20000 | 100.000 ms | compute-model-bound |

低强度用例的时间下界由 $Bytes/BW = 1\text{e}9/5\text{e}11 = 2$ ms 决定，与 FLOPs 无关；高强度用例则由 $FLOPs/P_{peak} = 2\text{e}12/2\text{e}13 = 100$ ms 决定。这正是 Roofline 的两条边：先判断落在哪一侧，再决定优化方向是「减少搬运」还是「提高算力利用」。

如果一个实际 Kernel 的性能远低于 Roofline 两条屋脊，先检查 Launch、依赖、分支、Occupancy 与同步，不要直接断言「显存带宽不够」。

## 7. Level 1：通用 PyTorch CPU/CUDA 性能实验

### 7.1 隔离环境

```bash
python -m venv .venv-project1
source .venv-project1/bin/activate
python -m pip install --upgrade pip
python -m pip install "torch>=2.5,<3"
```

如果默认安装包与本机 CUDA 不匹配，使用 PyTorch 官方安装选择器给出的命令。没有 NVIDIA GPU 时可以安装 CPU wheel；不要为了运行本实验替换生产机驱动。

实验自动检测 CPU/CUDA、GPU 型号、Compute Capability、显存与软件版本，并包含三类工作负载：

- `launch`：许多微小算子，对比一次向量化表达。
- `memory`：产生中间张量的逐元素链，对比减少分配的原地版本。
- `matmul`：用于观察高算术强度矩阵乘法。

保存为 `gpu_profiling_lab.py`：

```python
#!/usr/bin/env python3
import argparse
import contextlib
import json
import math
import platform
import statistics
import time
from pathlib import Path

import torch

def percentile(values, q):
    data = sorted(values)
    if not data:
        return float("nan")
    position = (len(data) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return data[lower]
    weight = position - lower
    return data[lower] * (1 - weight) + data[upper] * weight

def synchronize(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)

def architecture_name(capability):
    major, minor = capability
    if (major, minor) == (8, 9):
        return "Ada Lovelace"
    if major == 8:
        return "Ampere"
    if major == 9:
        return "Hopper"
    if major >= 10:
        return "Blackwell-or-newer"
    return f"pre-Ampere-or-other-sm_{major}{minor}"

def environment(device):
    info = {
        "python": platform.python_version(),
        "pytorch": torch.__version__,
        "device": str(device),
        "cuda_available": torch.cuda.is_available(),
        "pytorch_cuda_runtime": torch.version.cuda,
    }
    if device.type == "cuda":
        props = torch.cuda.get_device_properties(device)
        capability = torch.cuda.get_device_capability(device)
        info.update({
            "gpu_name": props.name,
            "compute_capability": f"{capability[0]}.{capability[1]}",
            "architecture_family": architecture_name(capability),
            "vram_gib": round(props.total_memory / 2**30, 2),
            "gpu_count": torch.cuda.device_count(),
        })
    return info

@contextlib.contextmanager
def nvtx_range(name, device):
    enabled = device.type == "cuda"
    if enabled:
        torch.cuda.nvtx.range_push(name)
    try:
        yield
    finally:
        if enabled:
            torch.cuda.nvtx.range_pop()

def timed(fn, device, warmup, iterations):
    with torch.inference_mode():
        for _ in range(warmup):
            output = fn()
        synchronize(device)

        samples_ms = []
        for _ in range(iterations):
            start = time.perf_counter_ns()
            output = fn()
            synchronize(device)
            samples_ms.append((time.perf_counter_ns() - start) / 1e6)

    return output, {
        "p50_ms": statistics.median(samples_ms),
        "p95_ms": percentile(samples_ms, 0.95),
        "min_ms": min(samples_ms),
        "max_ms": max(samples_ms),
        "iterations": iterations,
    }

def check_close(reference, candidate):
    torch.testing.assert_close(reference, candidate, rtol=2e-4, atol=2e-4)
    return True

def build_workloads(args, device):
    generator = torch.Generator(device=device)
    generator.manual_seed(args.seed)
    x = torch.randn(args.elements, device=device, generator=generator)
    a = torch.randn((args.matrix, args.matrix), device=device, generator=generator)
    b = torch.randn((args.matrix, args.matrix), device=device, generator=generator)

    def launch_baseline():
        y = x.clone()
        for _ in range(args.steps):
            y = y + 0.001
        return y

    def launch_optimized():
        return x + args.steps * 0.001

    def memory_baseline():
        return torch.relu(x * 1.1 + 0.3).square()

    def memory_optimized():
        y = x.clone()
        return y.mul_(1.1).add_(0.3).relu_().square_()

    def matmul():
        return a @ b

    return {
        "launch": (launch_baseline, launch_optimized),
        "memory": (memory_baseline, memory_optimized),
        "matmul": (matmul, None),
    }

def profile_once(name, fn, device, output_path):
    activities = [torch.profiler.ProfilerActivity.CPU]
    if device.type == "cuda":
        activities.append(torch.profiler.ProfilerActivity.CUDA)

    with torch.profiler.profile(
        activities=activities,
        record_shapes=True,
        profile_memory=True,
        with_flops=True,
    ) as profiler:
        with torch.profiler.record_function(name):
            with nvtx_range(name, device):
                output = fn()
                synchronize(device)

    profiler.export_chrome_trace(str(output_path))
    sort_key = "self_cuda_time_total" if device.type == "cuda" else "self_cpu_time_total"
    print(profiler.key_averages().table(sort_by=sort_key, row_limit=15))
    return output

def capture_one_matmul(fn, device):
    if device.type != "cuda":
        raise RuntimeError("--capture-kernel 需要 CUDA 设备")
    with torch.inference_mode():
        for _ in range(5):
            output = fn()
        synchronize(device)
        torch.cuda.cudart().cudaProfilerStart()
        with nvtx_range("capture_matmul", device):
            output = fn()
            synchronize(device)
        torch.cuda.cudart().cudaProfilerStop()
    print(float(output.flatten()[0]))

def main():
    parser = argparse.ArgumentParser(description="通用 GPU 性能分析综合实验")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--mode", choices=["all", "launch", "memory", "matmul"], default="all")
    parser.add_argument("--elements", type=int, default=1_000_000)
    parser.add_argument("--matrix", type=int, default=512)
    parser.add_argument("--steps", type=int, default=50)
    parser.add_argument("--warmup", type=int, default=10)
    parser.add_argument("--iters", type=int, default=30)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--capture-kernel", action="store_true")
    parser.add_argument("--output", default="reports/benchmark.json")
    args = parser.parse_args()

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("请求了 CUDA，但 PyTorch 未检测到可用 CUDA GPU")
    device = torch.device(
        "cuda" if (args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available())) else "cpu"
    )
    if min(args.elements, args.matrix, args.steps, args.warmup, args.iters) <= 0:
        raise ValueError("尺寸、步骤与迭代参数必须大于 0")

    workloads = build_workloads(args, device)
    if args.capture_kernel:
        capture_one_matmul(workloads["matmul"][0], device)
        return

    selected = list(workloads) if args.mode == "all" else [args.mode]
    report = {
        "environment": environment(device),
        "config": vars(args),
        "results": {},
    }
    print(json.dumps(report["environment"], indent=2, ensure_ascii=False))

    for name in selected:
        baseline, optimized = workloads[name]
        with nvtx_range(f"{name}_baseline_benchmark", device):
            baseline_output, baseline_stats = timed(
                baseline, device, args.warmup, args.iters
            )
        item = {"baseline": baseline_stats}

        if optimized is not None:
            with nvtx_range(f"{name}_optimized_benchmark", device):
                optimized_output, optimized_stats = timed(
                    optimized, device, args.warmup, args.iters
                )
            item["optimized"] = optimized_stats
            item["correct"] = check_close(baseline_output, optimized_output)
            item["speedup_p50"] = baseline_stats["p50_ms"] / optimized_stats["p50_ms"]

        report["results"][name] = item
        print(name, json.dumps(item, indent=2, ensure_ascii=False))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.profile:
        profile_name = selected[0]
        trace_path = output_path.parent / "pytorch_trace.json"
        profile_once(
            f"{profile_name}_baseline_profile",
            workloads[profile_name][0],
            device,
            trace_path,
        )
        print(f"PyTorch trace: {trace_path}")

if __name__ == "__main__":
    main()
```

### 7.2 运行命令

CPU 或自动设备：

```bash
python gpu_profiling_lab.py --device auto --mode all
python gpu_profiling_lab.py --device cpu --mode launch --profile \
  --output reports/cpu_benchmark.json
```

NVIDIA GPU：

```bash
CUDA_VISIBLE_DEVICES=0 python gpu_profiling_lab.py \
  --device cuda --mode all --output reports/gpu_benchmark.json

CUDA_VISIBLE_DEVICES=0 python gpu_profiling_lab.py \
  --device cuda --mode memory --profile \
  --output reports/gpu_memory_benchmark.json
```

### 7.3 预期现象

- `launch` 优化版通常显著减少算子与 Kernel 启动次数；输入较小时，收益往往比输入较大时更明显。
- `memory` 优化版减少中间张量分配，但原地链仍可能包含多个 Kernel；它不等价于编译器生成的真正融合 Kernel。
- `matmul` 的性能受尺寸、精度、库版本、Tensor Core 可用性与频率状态影响。
- CPU 与 GPU 的绝对延迟不可直接比较，它们主要用于练习同一套测量与诊断方法。
- 第一次运行可能包含 CUDA Context、库初始化与缓存建立开销，因此必须 Warmup。

### 7.4 如何读 PyTorch Profiler

优先查看：`self_cpu_time_total`（Python/框架侧谁占用 CPU）；`self_cuda_time_total`（哪个算子对应的 CUDA Kernel 最耗时）；调用次数（是否存在大量微小算子）；输入形状（慢算子是否只在特定尺寸出现）；内存分配（是否频繁创建与释放中间张量）。

`record_shapes`、`profile_memory`、`with_stack` 都可能增加开销。诊断完成后应关闭它们，再跑纯墙钟基准。

### 7.5 实测参考：纯 CPU 环境

下面是一台无 NVIDIA GPU 机器上的实跑结果（Python 3.7.0、torch 1.13.1+cpu、device=cpu），用于说明「同一套方法在 CPU 上也能跑通，但结论不能外推」。取 elements=2e5、matrix=256、warmup=3、iters=10：

| 工作负载 | Baseline P50 | Optimized P50 | Baseline P95 | 加速比 | 正确性 |
| --- | --- | --- | --- | --- | --- |
| launch | 2.947 ms | 0.065 ms | 3.827 ms | 45.30x | 通过 |
| memory | 0.251 ms | 0.250 ms | 0.282 ms | 1.00x | 通过 |
| matmul | 0.158 ms | 不适用 | 0.191 ms | 不适用 | 不适用 |

`launch` 的跨尺寸复测（steps=50，前两组 warmup=3/iters=10，第三组 warmup=2/iters=5）：

| elements | Baseline P50 | Optimized P50 | 加速比 |
| --- | --- | --- | --- |
| 1e4 | 0.270 ms | 0.0057 ms | 47.45x |
| 1e6 | 33.98 ms | 0.545 ms | 62.33x |
| 1e7 | 220.31 ms | 4.119 ms | 53.49x |

两点与「预期现象」不同，必须写进报告而不是掩盖：

- **`memory` 在 CPU 上几乎没有收益（1.00x）**。原地链省掉的是中间张量分配，但 CPU 上分配成本相对访存很低，且四个算子仍是四次独立遍历。真正的收益要靠编译器融合成单 Kernel（`torch.compile` / Inductor），在 GPU 上才明显。
- **`launch` 的加速比没有随尺寸增大而衰减**，反而在 1e6 达到峰值。原因是 CPU 上 Baseline 的 50 次循环意味着 50 遍完整内存遍历，优化版只有 1 遍，收益主要来自访存量减少而非 Launch 开销。「小输入收益更大」是 GPU 上 Launch 占比主导时的规律，不能跨设备照搬。

Profiler 证据：`--profile --steps 10` 时，`key_averages()` 表中 `aten::add` 的 `# of Calls` 恰为 10、Self CPU 占 50.27%，与「循环里每步一个算子」的判断一致。注意 `profile_once` 只对 `selected[0]` 的 **baseline** 采集；若要对比优化版的算子数，需把传入的函数换成 `workloads[name][1]` 再采一次，两份 trace 分开保存。

## 8. Level 2：NVIDIA Nsight 专项实验

### 8.1 支持边界

| 架构 | 常见 GPU | 本项目可做 | 注意事项 |
| --- | --- | --- | --- |
| Ampere | RTX 3080/3090、A100 | Systems、Compute、TF32/FP16 对照 | 消费卡可能受性能计数器权限限制 |
| Ada Lovelace | RTX 4090、L40/L40S | Systems、Compute、Kernel 对照 | RTX 4090 不是 Blackwell |
| Hopper | H100/H200 | Systems、Compute、可选 FP8 | FP8 结论不能由低代 GPU 等价模拟 |
| Blackwell | RTX 5090、B100/B200/GB200 | Systems、Compute、可选 FP4/新 Tensor Core | 数据中心与消费卡能力并不相同 |

Nsight Systems 主要回答「何时发生、各阶段如何重叠」；Nsight Compute 主要回答「一个 CUDA Kernel 为什么慢」。前者适合先扫全局，后者采集硬件计数器时会重放 Kernel，开销可能很大，不应直接包住完整训练任务。

### 8.2 Nsight Systems：先看全局时间线

```bash
mkdir -p reports

nsys profile \
  --trace=cuda,nvtx,osrt \
  --sample=none \
  --cpuctxsw=none \
  --force-overwrite=true \
  --output=reports/nsys_baseline \
  python gpu_profiling_lab.py --device cuda --mode all --warmup 5 --iters 10

nsys stats reports/nsys_baseline.nsys-rep \
  | tee reports/nsys_baseline_stats.txt
```

打开 `.nsys-rep` 后检查：NVTX 范围是否清楚分隔 baseline 与 optimized；CUDA API 调用与 GPU Kernel 之间是否存在长空隙；是否出现大量短 Kernel；`cudaDeviceSynchronize`、`cudaStreamSynchronize` 是否过多；Host-to-Device/Device-to-Host 拷贝是否与计算重叠；GPU 空闲时 CPU 在执行什么。

如果系统限制 CPU Sampling，不需要直接使用 `sudo`。本命令已关闭 Sampling 与 Context Switch 采集，仍可分析 CUDA/NVTX 时间线。

### 8.3 Nsight Compute：只抓一个矩阵乘 Kernel

脚本的 `--capture-kernel` 会先完成分配与 Warmup，再通过 CUDA Profiler API 只开放一个采集窗口：

```bash
ncu \
  --profile-from-start off \
  --set full \
  --target-processes all \
  --force-overwrite \
  --export reports/ncu_matmul \
  python gpu_profiling_lab.py \
    --device cuda --mode matmul --matrix 1024 --capture-kernel
```

若 `--set full` 太慢，可先使用：

```bash
ncu \
  --profile-from-start off \
  --section SpeedOfLight \
  --section MemoryWorkloadAnalysis \
  --section Occupancy \
  --section LaunchStats \
  --force-overwrite \
  --export reports/ncu_matmul_focused \
  python gpu_profiling_lab.py \
    --device cuda --mode matmul --matrix 1024 --capture-kernel
```

重点回答：SM 与 Memory 吞吐哪一侧更接近上限？DRAM、L2、L1/TEX 哪一级压力最大？活跃 Warp、寄存器、Shared Memory、Block 尺寸如何限制 Occupancy？Warp Stall 的主要类别是什么？当前 Kernel 是否使用预期的矩阵计算路径？

不要把「Occupancy 不是 100%」自动判定为问题。高寄存器或 Shared Memory 使用可能换来更少的访存与更高吞吐，最终仍以实际时间与瓶颈指标为准。

### 8.4 性能计数器权限不足

如果出现 `ERR_NVGPUCTRPERM` 或类似错误：

1. 记录错误与当前驱动、容器、虚拟化环境。
2. 在有权限的机器上让管理员按 NVIDIA 官方安全策略开放计数器。
3. 无法开放时，使用 Nsight Systems、PyTorch Profiler 与墙钟基准完成项目。
4. 不要声称已经验证 DRAM 吞吐、Warp Stall 或 Occupancy 原因。

## 9. 优化前后对照与结论写法

把实际结果填入下表，不要照抄示例数字：

| 工作负载 | Baseline P50 | Optimized P50 | P95 | 加速比 | 正确性 | 主要证据 |
| --- | --- | --- | --- | --- | --- | --- |
| launch | 待测 | 待测 | 待测 | 待测 | 通过/失败 | Kernel 数、GPU 空隙 |
| memory | 待测 | 待测 | 待测 | 待测 | 通过/失败 | 分配、DRAM/L2、Kernel 数 |
| matmul | 待测 | 不适用 | 待测 | 不适用 | 不适用 | SM/Memory Roof、Tensor 路径 |

一份合格结论应当同时包含判断、证据、改动与边界，例如：

> 在 <GPU 型号 + 驱动 + PyTorch 版本> 上，`launch` 工作负载（elements=1e6、steps=50、warmup=10、iters=30）Baseline P50 为 A ms、Optimized P50 为 B ms，加速比 A/B；Nsight Systems 显示 Baseline 每轮出现 50 个短 Kernel 且 Kernel 间存在稳定空隙，Optimized 只有 1 个 Kernel，空隙消失；`assert_close(rtol=2e-4, atol=2e-4)` 通过；elements 降到 1e4 时加速比升到 X，升到 1e7 时降到 Y，说明收益随尺寸从 Launch-bound 转向 Memory-bound。本结论不覆盖 FP16、`torch.compile` 与多卡场景。

不合格结论的典型形态是「优化后快了 3 倍」——没有环境、没有分布、没有证据、没有正确性、没有边界，别人无法复现也无法审阅。

## 10. 完整结果分析流程

### 10.1 第一步：确认基准可信

是否 Warmup？CUDA 测量是否同步？是否报告了多次测量的分布？基线与优化是否使用同一输入？温度、P-State、后台任务是否异常？

### 10.2 第二步：确定最大时间贡献者

先找占总时间最多的阶段。优化占比 1% 的算子，即使把它完全消除，端到端收益也不会超过约 1%（Amdahl 定律的直接推论）。

### 10.3 第三步：提出可证伪假设

坏假设：「GPU 利用率只有 40%，所以显卡没吃满，换个更大的 Batch 就会快。」——没有指明时间花在哪里，也无法被单次实验否证。

好假设：「`launch` 工作负载的 GPU 时间线中，Kernel 之间的空隙占总时长 60% 以上，且每个 Kernel 的执行时间小于 5 µs；因此瓶颈是 Launch 与 Python 循环，而不是算力或带宽。把 50 次逐元素加法合并为一次向量化表达后，Kernel 数应从 50 降到 1，P50 应下降至少 5 倍，且输出在 2e-4 容差内一致。」——它给出了可测量的预测，任何一条不成立都说明假设错误。

### 10.4 第四步：一次只改一个变量

保持输入、精度、迭代与环境不变，只修改循环表达式。若同时启用 `torch.compile`、FP16、CUDA Graph 与更大 Batch，就无法确定收益来源。

### 10.5 第五步：验证收益边界

至少改变两组输入尺寸重新运行：

```bash
python gpu_profiling_lab.py --device auto --mode launch --elements 10000
python gpu_profiling_lab.py --device auto --mode launch --elements 1000000
python gpu_profiling_lab.py --device auto --mode launch --elements 10000000
```

小输入常受 Launch 影响，大输入可能逐渐转为内存带宽限制。优化不一定在所有尺寸都保持同一加速比。

## 11. 常见错误与排查

### 11.1 CUDA 计时没有同步

症状：耗时异常小，只测到 CPU 提交 Kernel 的时间；增大矩阵尺寸后「耗时」几乎不变。

排查：确认计时区间末尾调用 `torch.cuda.synchronize(device)`，或改用 CUDA Event 计时。对照方法是把 `--matrix` 从 512 提到 2048，若墙钟时间没有相应增长，说明测的是提交而非执行。

### 11.2 没有 Warmup

症状：第一次迭代比后续慢一个数量级，P95 与 max 远大于 P50。

排查：首次运行包含 CUDA Context 创建、cuBLAS/cuDNN 句柄初始化、显存分配器建池与 autotune。保持 `--warmup 10` 以上，并单独报告冷启动时间，不要把它混进稳态统计。

### 11.3 同时改多个变量

症状：加速比很漂亮，但无法解释来源，换一台机器就消失。

排查：回到单变量对照，逐项启用 `torch.compile`、精度、CUDA Graph、Batch，每项都单独记录 P50/P95 与正确性。

### 11.4 只看平均值

症状：均值下降但用户侧尾延迟变差。

排查：报告 P50/P95/max 与迭代次数；检查是否有周期性抖动（日志 flush、内存分配器扩张、其他进程抢占）。

### 11.5 把 Profiler 开销当成收益或损失

症状：开启 `--profile` 后基线变慢，于是得出「优化无效」的结论。

排查：Profiler 只用于解释原因，最终收益必须用不带 Profiler 的墙钟基准复测；`record_shapes`、`profile_memory`、`with_stack` 与 Nsight Compute 的 Kernel 重放都会显著改变时间。

### 11.6 正确性检查被跳过

症状：原地链或向量化改写后输出静默偏差，性能数字却「更好」。

排查：每次改写都跑 `check_close`；`memory_optimized` 使用 `x.clone()` 保护输入，若直接对 `x` 原地操作会污染后续基线，导致对照失效。

### 11.7 把 CPU 结果外推到 GPU

症状：在 CPU 上测得 2 倍加速，就宣称 GPU 上也有 2 倍。

排查：CPU 与 GPU 的瓶颈结构不同（CPU 更受向量化与缓存影响，GPU 更受 Launch 与 HBM 带宽影响）。跨设备结论必须在目标设备重测，报告中明确标注设备与精度。

## 写在最后

这个项目的价值不在某个加速比，而在于建立一条可复现的证据链：环境 → 基线 → 时间线 → Kernel 指标 → 单变量改动 → 正确性 → 跨尺寸复测 → 边界声明。后续七个项目都会复用这套流程。

下一篇：[CUDA Kernel 优化项目](/source/AI-Infra/2-AI系统性能工程/30-CUDAKernel优化项目)。
