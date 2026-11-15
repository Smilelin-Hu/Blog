# Kernel Fusion 与高性能算子开发

本篇从中间张量与内存流量出发理解 Kernel Fusion，并掌握高性能自定义算子的设计与验证方法。

很多 AI Kernel 的算术并不复杂：乘法、加法、激活、缩放、Dropout、Mask、Residual。问题在于，如果每一步都成为独立 Kernel，中间结果就要反复写入 Global Memory 再读回来，同时 CPU 还要不断提交 Kernel Launch。Fusion 的核心并不是「把代码写进同一个函数」，而是让 Producer 产生的数据尽量停留在 Register 或 Shared Memory 中直接交给 Consumer，不落到显存中的中间 Tensor。

## 1. 内容概览

- Launch Fusion、Memory-Traffic Fusion、Epilogue Fusion 与 Algorithmic Fusion 的区别。
- Elementwise 算子链融合前后的理论 Global Memory Traffic 计算。
- 含 Launch、Memory、Compute 与同步开销的性能模型。
- Vertical / Horizontal Fusion 的适用判断。
- Register Pressure、Occupancy 下降、Spill 与并行度损失。
- PyTorch CUDA Extension 的三 Kernel 与单融合 Kernel 对照，以及验收流程。

## 2. 核心直觉：中间 Tensor 是一张昂贵的交接单

```python
tmp1 = x * y
tmp2 = tmp1 + bias
out = relu(tmp2)
```

数学上它只是 $out_i=\max(x_i y_i+bias,\ 0)$，但 Eager 执行中可能形成三个独立 Kernel：

```text
Kernel 1: 读 x、y → 写 tmp1
Kernel 2: 读 tmp1 → 写 tmp2
Kernel 3: 读 tmp2 → 写 out
```

`tmp1` 与 `tmp2` 不是最终结果，却完整走了两次 Store 与两次后续 Load。融合后：

```text
Fused Kernel: 读 x、y → 在 Register 中乘、加、ReLU → 写 out
```

每个线程加载自己的 $x_i$、$y_i$，中间值停留在 Register，最终只写一次 $out_i$。这就是最典型的 Producer-Consumer Fusion。

## 3. Fusion 的两大收益

### 3.1 减少 Kernel Launch

设一次 Launch 的有效开销为 $t_{launch}$，原来 $K$ 个 Kernel、融合后 $F$ 个：

$$
\Delta T_{launch} \approx (K-F)\,t_{launch}
$$

真实 Launch Cost 受 CPU、Driver、Python/Framework、CUDA Graph、Profiler 与系统负载影响，不能把某个固定微秒数写成通用常量。对大 GEMM，Launch Cost 几乎可忽略；对数百个只有几微秒的小 Pointwise Kernel，它可能成为主瓶颈。

### 3.2 减少 Global Memory Round Trip

以 FP32 的 `relu(x * y + bias)` 为例，不考虑 Cache，按有用字节估算：

| 阶段 | 读取 | 写入 | 每元素流量 |
| --- | --- | --- | --- |
| Multiply | `x,y`：8 B | `tmp1`：4 B | 12 B |
| Bias Add | `tmp1`：4 B | `tmp2`：4 B | 8 B |
| ReLU | `tmp2`：4 B | `out`：4 B | 8 B |
| 未融合合计 | | | 28 B |
| 融合 Kernel | `x,y`：8 B | `out`：4 B | 12 B |

理想流量缩减比 $R_{traffic}=28/12\approx2.33$。这不是「必然加速 2.33 倍」：Cache 可能吸收部分中间流量，Kernel 还可能受 Launch、Compute、Register、Occupancy 与其他系统开销影响。

## 4. 综合性能模型

$$
T \approx N_{launch}\,t_{launch} + \max\left(\frac{Bytes}{BW_{effective}},\ \frac{FLOPs}{P_{effective}}\right) + T_{sync} + T_{other}
$$

Fusion 主要改变三个量：$N_{launch}$ 减少、$Bytes$ 减少、$P_{effective}$ 可能上升也可能因 Register Pressure、Occupancy 或指令依赖而下降。因此正确判断不是「能不能合」，而是「合了之后这三项的净变化是否为正，且正确性与可维护性代价是否可接受」。

## 5. Fusion 的主要类型

**Vertical Fusion（上下游融合）**：把 Producer 与 Consumer 合并，如 `Bias → Activation → Dropout`、`Residual Add → LayerNorm 前处理`、`Dequantize → GEMM 输入转换`、`GEMM → Bias → Activation Epilogue`。收益来自消除中间 Tensor，最适合一对一或规则广播的 Pointwise 链。

**Horizontal Fusion（同类小任务融合）**：很多小 Tensor 分别执行相同更新时，打包为一个 Multi-Tensor Kernel：

```text
参数 1 的 Adam 更新 ┐
参数 2 的 Adam 更新 ├─→ 一个 Multi-Tensor Apply Kernel
参数 3 的 Adam 更新 ┘
```

重点减少 Launch 数，也能改善小 Tensor 的并行度，Fused Optimizer 常采用这种思路。

**Epilogue Fusion**：矩阵乘得到 Accumulator 后不立即写回 Global Memory，而在 Epilogue 中完成

$$
D = \mathrm{Activation}(\alpha AB + \beta C + bias)
$$

Bias、Scale、Activation、Residual 或 Quantization 可直接消费 Accumulator。cuBLASLt、CUTLASS 等库提供多种 Epilogue 能力；优先复用成熟库，不要为了「自定义」而重写 GEMM Mainloop。

**Reduction Fusion**：如统计量计算与归一化、Loss 与 Reduction、Softmax 的若干阶段融合。它比 Pointwise Fusion 难，因为需要 Warp/Block Reduction、跨线程同步、数值稳定算法，可能还要多阶段全局归约。无法在单个 Block 内完成的 Global Reduction，未必适合强行塞进一个普通 Kernel。

**Algorithmic Fusion**：FlashAttention 不只是把几个表达式写到同一 Kernel，而是通过 Tiling 与 Online Softmax 避免物化完整 Attention Matrix，改变了 I/O 复杂度与数据流，属于比 Pointwise Fusion 更深的算法级融合。

**Persistent Kernel 与 Megakernel**：前者让 Thread Block 长时间驻留、循环从 Work Queue 取任务；后者把更多执行阶段放进一个大型 Kernel。它们可以减少 Host Launch 与全局同步，但调度、负载均衡、Register/Shared Memory、死锁与可维护性都更复杂。

## 6. 什么样的算子适合融合

**适合**：连续的 Elementwise 操作；中间 Tensor 只被下游消费一次；相同或易广播的 Shape；每步 Arithmetic Intensity 很低；Kernel 很短、Launch Overhead 明显；GEMM/Conv 后的 Bias、Activation、Scale 等 Epilogue；多个结构相同的小 Tensor 更新。

**谨慎**：中间结果会被多个 Consumer 复用；上下游拥有完全不同的最优 Grid/Tile；某阶段是大 Reduction 或需要全局同步；融合后每线程寄存器激增；分支路径复杂、Warp Divergence 加重；融合会破坏原本可并行的独立 Kernel；为了消除存储而大量重复计算；不同精度与 Reduction Order 造成数值变化；动态 Shape 让编译缓存持续失效。

## 7. 为什么「融合得越多」不一定越快

**Register Pressure**：多个阶段的 Live Value 同时存在，编译器需要更多 Register。超过物理限制时 Active Block/Warp 数下降、Occupancy 降低、发生 Local Memory Spill，而 Spill 又引入新的显存流量——原来省掉的中间 Tensor 流量可能被 Spill 抵消。

**最优并行策略冲突**：Pointwise Kernel 希望大量独立 Thread，Reduction 需要协同，GEMM 需要 Tile 与 Tensor Core Pipeline。强行融合会让至少一个阶段使用不合适的映射。

**失去并发**：两个互不依赖的小 Kernel 原本可在不同 Stream 并发，合成一个资源占用很高的 Kernel 不一定更快。

**Code Size 与编译成本**：大量 Shape、Dtype、Layout 与 Feature 组合会产生变体爆炸

$$
Variants = Shapes \times Dtypes \times Layouts \times Architectures \times Features
$$

JIT 编译、Binary Size、Cache、测试矩阵与回归维护都会变贵。

## 8. 高性能算子开发流程

1. **写清算子契约**：输入/输出 Shape、Dtype、Device、Layout；Contiguous、Stride、Alignment 要求；Broadcast 规则；In-place、Alias 与 Mutation 语义；Forward、Backward 与 Higher-order Gradient；确定性、随机数与数值容差；支持的架构与回退路径。
2. **建立可信 Reference**：优先由现有 PyTorch/NumPy 操作组合而成，追求易读与正确而不是快。测试随机值、零、极值、NaN/Inf、奇数长度、非对齐 Tail 与空 Tensor。
3. **建立性能模型**：先数清 FLOPs、最少输入/输出 Byte、未融合中间 Byte、Kernel 数，判断预期是 Launch、Memory 还是 Compute Bound。
4. **写最小正确 Kernel**：先实现单 Dtype、Contiguous、规则 Shape，确保边界检查与正确性，再逐步加入 Vectorized Load、Mixed Precision、不同 Layout、Backward 与 Auto-tuning。
5. **Profile 而不是猜**：Nsight Systems 看 Kernel 数、Launch Gap、NVTX Range；Nsight Compute 看 DRAM Byte、Memory Throughput、Register、Occupancy、Stall、Source/SASS；无 Profiler Benchmark 看最终端到端速度与 Tail。
6. **集成 Framework**：教学实验可用 `torch.utils.cpp_extension.load_inline` 快速 JIT；生产自定义算子还要正确注册 Operator Schema、Fake/Meta Kernel、Autograd 与编译器可见性，不能只暴露一个随意的 PyBind 函数。
7. **建立回归矩阵**：多 Shape/Batch/Sequence Length；FP32、FP16、BF16 或目标低精度；Ampere、Ada、Hopper、Blackwell 的实际支持范围；Cold Compile 与 Warm Execution；单 Kernel Microbenchmark 与端到端模型。

## 9. Level 0：CPU 单遍融合实验

不需要 GPU。基线对 Python List 做三次遍历并构造两个中间列表，融合版只做一次遍历直接写最终输出。保存为 `fusion_cpu_lab.py`：

```python
#!/usr/bin/env python3
import argparse, gc, json, math, platform, statistics, time, tracemalloc

def baseline(x, y, bias):
    tmp1 = [a * b for a, b in zip(x, y)]
    tmp2 = [v + bias for v in tmp1]
    return [v if v > 0.0 else 0.0 for v in tmp2]

def fused(x, y, bias):
    return [(value if value > 0.0 else 0.0)
            for a, b in zip(x, y) for value in (a * b + bias,)]

def percentile(values, q):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] if lo == hi else ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)

def benchmark(fn, x, y, bias, warmup, repeat):
    for _ in range(warmup):
        fn(x, y, bias)
    gc.collect()
    samples, checksum = [], None
    for _ in range(repeat):
        t0 = time.perf_counter()
        out = fn(x, y, bias)
        samples.append(time.perf_counter() - t0)
        checksum = sum(out[:: max(1, len(out) // 1000)])
    mean = statistics.fmean(samples)
    return {"median_ms": statistics.median(samples) * 1e3,
            "p95_ms": percentile(samples, 0.95) * 1e3,
            "cv_percent": statistics.pstdev(samples) / mean * 100.0,
            "checksum_sample": checksum}

def measure_peak(fn, x, y, bias):
    gc.collect()
    tracemalloc.start()
    out = fn(x, y, bias)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return {"peak_mib": peak / 2**20, "output_length": len(out)}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=300_000)
    p.add_argument("--bias", type=float, default=-0.25)
    p.add_argument("--warmup", type=int, default=2)
    p.add_argument("--repeat", type=int, default=7)
    a = p.parse_args()
    if a.n <= 0 or a.warmup < 0 or a.repeat < 3:
        raise SystemExit("要求 n > 0、warmup >= 0、repeat >= 3")
    x = [((i % 1009) - 504) / 503.0 for i in range(a.n)]
    y = [((i % 997) - 498) / 499.0 for i in range(a.n)]

    ref, opt = baseline(x, y, a.bias), fused(x, y, a.bias)
    err = max(abs(u - v) for u, v in zip(ref, opt))
    if err != 0.0:
        raise AssertionError(f"结果不一致：max_abs_error={err}")
    del ref, opt

    bs = benchmark(baseline, x, y, a.bias, a.warmup, a.repeat)
    fs = benchmark(fused, x, y, a.bias, a.warmup, a.repeat)
    bm, fm = measure_peak(baseline, x, y, a.bias), measure_peak(fused, x, y, a.bias)
    print(json.dumps({
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "config": vars(a),
        "correctness": {"exact": True, "max_abs_error": err},
        "baseline": {"timing": bs, "memory": bm},
        "fused": {"timing": fs, "memory": fm},
        "speedup": bs["median_ms"] / fs["median_ms"],
        "peak_memory_reduction": bm["peak_mib"] / fm["peak_mib"],
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

```bash
python3 fusion_cpu_lab.py --n 300000 --warmup 2 --repeat 7
```

预期现象：`correctness.exact` 为 `true`；融合版通常更快、`peak_mib` 明显更低；具体速度随 Python 版本、CPU、GC 与后台负载变化；`tracemalloc` 只用于比较 Python Allocation，不代表 CUDA 显存。

基线需要同时持有 `tmp1`、`tmp2` 与 `out`，融合版主要只持有 `out`。这与 GPU Fusion 的数据流直觉一致，但 CPU Python 实验不是 GPU Kernel 的等价模拟：它不包含 Warp、Register、CUDA Launch、Coalescing 或显存带宽。

## 10. Level 1：三个 CUDA Kernel 融合为一个

环境检查（PyTorch Wheel 自带的 CUDA Runtime 与系统 `nvcc` 是两个概念，JIT 编译 Extension 时系统 Toolkit、编译器与 PyTorch 构建版本必须兼容）：

```bash
python -m pip install --upgrade pip ninja
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
nvcc --version
c++ --version
```

保存为 `fusion_cuda_extension.py`：

```python
#!/usr/bin/env python3
import argparse, json, time
import torch
from torch.utils.cpp_extension import load_inline

CPP_SOURCE = r"""
torch::Tensor baseline_cuda(torch::Tensor x, torch::Tensor y, double bias);
torch::Tensor fused_cuda(torch::Tensor x, torch::Tensor y, double bias);
"""

CUDA_SOURCE = r"""
#include <torch/extension.h>
#include <ATen/cuda/CUDAContext.h>
#include <c10/cuda/CUDAException.h>
#include <cuda_runtime.h>

__global__ void multiply_kernel(const float* x, const float* y, float* out, int64_t n) {
    int64_t i = static_cast<int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (i < n) out[i] = x[i] * y[i];
}
__global__ void bias_kernel(const float* x, float bias, float* out, int64_t n) {
    int64_t i = static_cast<int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (i < n) out[i] = x[i] + bias;
}
__global__ void relu_kernel(const float* x, float* out, int64_t n) {
    int64_t i = static_cast<int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (i < n) out[i] = x[i] > 0.0f ? x[i] : 0.0f;
}
__global__ void fused_kernel(const float* x, const float* y, float bias, float* out, int64_t n) {
    int64_t i = static_cast<int64_t>(blockIdx.x) * blockDim.x + threadIdx.x;
    if (i < n) {
        float value = x[i] * y[i] + bias;
        out[i] = value > 0.0f ? value : 0.0f;
    }
}

void check_inputs(const torch::Tensor& x, const torch::Tensor& y) {
    TORCH_CHECK(x.is_cuda() && y.is_cuda(), "x and y must be CUDA tensors");
    TORCH_CHECK(x.scalar_type() == torch::kFloat32, "x must be float32");
    TORCH_CHECK(y.scalar_type() == torch::kFloat32, "y must be float32");
    TORCH_CHECK(x.is_contiguous() && y.is_contiguous(), "tensors must be contiguous");
    TORCH_CHECK(x.sizes() == y.sizes(), "x and y must have the same shape");
    TORCH_CHECK(x.get_device() == y.get_device(), "x and y must be on one GPU");
}

torch::Tensor baseline_cuda(torch::Tensor x, torch::Tensor y, double bias) {
    check_inputs(x, y);
    auto tmp1 = torch::empty_like(x);
    auto tmp2 = torch::empty_like(x);
    auto out = torch::empty_like(x);
    const int threads = 256;
    const int64_t n = x.numel();
    const int blocks = static_cast<int>((n + threads - 1) / threads);
    cudaStream_t stream = at::cuda::getCurrentCUDAStream();
    multiply_kernel<<<blocks, threads, 0, stream>>>(
        x.data_ptr<float>(), y.data_ptr<float>(), tmp1.data_ptr<float>(), n);
    bias_kernel<<<blocks, threads, 0, stream>>>(
        tmp1.data_ptr<float>(), static_cast<float>(bias), tmp2.data_ptr<float>(), n);
    relu_kernel<<<blocks, threads, 0, stream>>>(
        tmp2.data_ptr<float>(), out.data_ptr<float>(), n);
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    return out;
}

torch::Tensor fused_cuda(torch::Tensor x, torch::Tensor y, double bias) {
    check_inputs(x, y);
    auto out = torch::empty_like(x);
    const int threads = 256;
    const int64_t n = x.numel();
    const int blocks = static_cast<int>((n + threads - 1) / threads);
    cudaStream_t stream = at::cuda::getCurrentCUDAStream();
    fused_kernel<<<blocks, threads, 0, stream>>>(
        x.data_ptr<float>(), y.data_ptr<float>(), static_cast<float>(bias),
        out.data_ptr<float>(), n);
    C10_CUDA_KERNEL_LAUNCH_CHECK();
    return out;
}
"""

def benchmark(fn, x, y, bias, warmup, repeat):
    for _ in range(warmup):
        del fn(x, y, bias)
    torch.cuda.synchronize()
    start, end = torch.cuda.Event(True), torch.cuda.Event(True)
    wall = time.perf_counter()
    start.record()
    for _ in range(repeat):
        del fn(x, y, bias)
    end.record(); end.synchronize()
    return {"cuda_event_ms": start.elapsed_time(end) / repeat,
            "host_wall_ms": (time.perf_counter() - wall) * 1e3 / repeat}

def peak_allocation(fn, x, y, bias):
    torch.cuda.empty_cache(); torch.cuda.synchronize()
    base = torch.cuda.memory_allocated()
    torch.cuda.reset_peak_memory_stats()
    out = fn(x, y, bias)
    torch.cuda.synchronize()
    delta = torch.cuda.max_memory_allocated() - base
    del out
    return delta

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=16_777_216)
    p.add_argument("--bias", type=float, default=-0.25)
    p.add_argument("--warmup", type=int, default=10)
    p.add_argument("--repeat", type=int, default=50)
    a = p.parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("未检测到 CUDA GPU；请运行 Level 0")
    ext = load_inline(name="fusion_lab_ext_v1", cpp_sources=CPP_SOURCE,
                      cuda_sources=CUDA_SOURCE,
                      functions=["baseline_cuda", "fused_cuda"],
                      extra_cflags=["-O3"],
                      extra_cuda_cflags=["-O3", "--use_fast_math"],
                      with_cuda=True, verbose=False)
    dev = torch.device("cuda")
    props = torch.cuda.get_device_properties(dev)
    torch.manual_seed(2026); torch.cuda.manual_seed_all(2026)
    x = torch.randn(a.n, device=dev, dtype=torch.float32)
    y = torch.randn_like(x)

    ref = torch.relu(x * y + a.bias)
    bo, fo = ext.baseline_cuda(x, y, a.bias), ext.fused_cuda(x, y, a.bias)
    be = (ref - bo).abs().max().item()
    fe = (ref - fo).abs().max().item()
    assert torch.allclose(ref, bo, rtol=1e-5, atol=1e-6), f"baseline mismatch: {be}"
    assert torch.allclose(ref, fo, rtol=1e-5, atol=1e-6), f"fused mismatch: {fe}"
    del ref, bo, fo
    torch.cuda.synchronize()

    bs = benchmark(ext.baseline_cuda, x, y, a.bias, a.warmup, a.repeat)
    fs = benchmark(ext.fused_cuda, x, y, a.bias, a.warmup, a.repeat)
    bp = peak_allocation(ext.baseline_cuda, x, y, a.bias)
    fp = peak_allocation(ext.fused_cuda, x, y, a.bias)
    print(json.dumps({
        "environment": {"torch": torch.__version__, "torch_cuda": torch.version.cuda,
                        "device": torch.cuda.get_device_name(dev),
                        "compute_capability": [props.major, props.minor]},
        "config": vars(a),
        "correctness": {"baseline_max_abs_error": be, "fused_max_abs_error": fe},
        "model": {"unfused_useful_bytes": a.n * 28, "fused_useful_bytes": a.n * 12,
                  "theoretical_traffic_reduction": 28 / 12},
        "baseline": {"timing": bs, "peak_incremental_allocation_mib": bp / 2**20},
        "fused": {"timing": fs, "peak_incremental_allocation_mib": fp / 2**20},
        "speedup_by_cuda_event": bs["cuda_event_ms"] / fs["cuda_event_ms"],
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

```bash
export MAX_JOBS=4
python fusion_cuda_extension.py --n 16777216 --warmup 10 --repeat 50
```

第一次运行需要 JIT 编译，不能把编译时间混入 Steady-State Kernel Benchmark；PyTorch 会缓存 Extension，修改源码后名称不变时要留意缓存是否被正确重建。多卡机器上可分别指定设备各跑一次基线：

```bash
CUDA_VISIBLE_DEVICES=0 python fusion_cuda_extension.py --n 16777216
CUDA_VISIBLE_DEVICES=1 python fusion_cuda_extension.py --n 16777216
```

这不是双 GPU Kernel，每次进程只在一张卡上建立基线，适合比较两张卡的温度、频率与环境稳定性。

预期现象：自动输出 GPU 型号、Compute Capability、显存与 PyTorch/CUDA 版本；Baseline 与 Fused 都通过正确性检查；Baseline 在时间线中有 Multiply、Bias、ReLU 三个 Kernel，Fused 只有一个；Fused 的增量峰值显存更低（两个中间 Tensor 各占 `n × 4` 字节）；大数组下通常看到 Fused 的有效带宽与耗时更好；实测 Speedup 不会严格等于理论流量缩减比 2.33。

## 写在最后

Fusion 的收益要用流量与 Launch 数算出来，再用 Profiler 验证，而不是凭「合在一起应该更快」的直觉；同时必须盯住 Register Pressure 与并行策略冲突这两个反作用力。下一篇换一种写法：用 Triton 在更高层次表达同样的融合与分块。

下一篇：[Triton Kernel 开发](/source/AI-Infra/2-AI系统性能工程/14-TritonKernel开发)。