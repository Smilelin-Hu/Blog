# Triton Kernel 开发

本篇使用 Triton 将算子意图映射为高效 GPU Kernel，掌握开发、调优与正确性验证的完整流程。

CUDA 把 GPU 暴露为 Thread、Warp、Block 与 Shared Memory；Triton 则把最常见的并行数据块提升为语言中的一等对象。开发者不再逐个编写 Thread 的标量逻辑，而是让每个 Program Instance 处理一块数据，再由编译器把块操作 Lower 到目标 GPU。这并不意味着 Triton 会自动把任何 Python 写法变快——仍然需要理解数据布局、访存、Tiling、Mask、Reduction、Register、Shared Memory、Occupancy 与 Roofline。Triton 降低的是「表达高性能数据流」的门槛，而不是取消性能工程。

## 1. 内容概览

- Program Instance、Launch Grid、Block/Tile 与 CUDA Thread Block 的关系与区别。
- `@triton.jit`、`tl.program_id`、`tl.arange`、`tl.load/store` 与 Mask。
- Runtime Argument 与 `tl.constexpr` Meta-parameter。
- 1D/2D Grid 与规则 Pointer Arithmetic。
- `triton.Config` 与 `@triton.autotune` 搜索 Block Size、`num_warps`。
- 有效显存流量、算术强度与吞吐上限的计算。
- Triton、CUDA C++、CUTLASS/cuBLAS 与框架内置算子的选型边界。

## 2. 核心直觉：写的是「一块数据怎么处理」

CUDA Elementwise Kernel 常让一个 Thread 处理一个元素：

```cuda
int i = blockIdx.x * blockDim.x + threadIdx.x;
if (i < n) out[i] = x[i] + y[i];
```

Triton 让一个 Program Instance 处理 `BLOCK_SIZE` 个元素：

```python
pid = tl.program_id(0)
offsets = pid * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
mask = offsets < n_elements
x = tl.load(x_ptr + offsets, mask=mask)
y = tl.load(y_ptr + offsets, mask=mask)
tl.store(out_ptr + offsets, x + y, mask=mask)
```

`offsets`、`x`、`y` 都是 Block Tensor，不是普通 Python List，也不是一个 CUDA Thread 的单值。编译器负责把这些块操作映射到 Warp、Vector Instruction、Register、Shared Memory 或 Tensor Core 数据流。

**Program Instance 不等于一个 CUDA Thread**。以 1D 向量为例：

```text
N = 1000, BLOCK_SIZE = 256
Grid = ceil(1000 / 256) = 4 个 Program Instance

Program 0 → offsets   0...255
Program 1 → offsets 256...511
Program 2 → offsets 512...767
Program 3 → offsets 768...1023，其中 1000...1023 被 Mask
```

一个 Program Instance 在底层通常对应一个 Thread Block（由 `num_warps` 决定线程数），块内的 lane 分工由编译器安排。

## 3. 编译与执行链路

```text
Python Wrapper
   ↓ 传入 Tensor、Shape、Stride、Meta-parameter
Triton Frontend / @triton.jit
   ↓
Triton IR / GPU-specific Lowering
   ↓
LLVM/PTX 或目标后端代码
   ↓
Driver 加载并缓存编译产物
   ↓
异步 Kernel Launch
```

第一次遇到某个新签名或新 Meta-parameter 组合可能发生 JIT Compile，后续命中缓存才是稳定执行。Benchmark 必须把编译与 Auto-tuning 时间从 Steady-State Kernel Time 中分离。

## 4. 五个核心组件

**`@triton.jit`**：把受 Triton 语言约束的 Python 函数编译为 GPU Kernel。Kernel Body 不是普通 Python Runtime，只能使用 Triton 支持的语义、类型与控制流。

**Launch Grid**：决定启动多少 Program Instance，最多三个 Axis，`tl.program_id(axis)` 读取对应 Axis 上的 Program ID。

```python
grid = lambda meta: (triton.cdiv(n_elements, meta["BLOCK_SIZE"]),)
```

**Block Tensor**：`tl.arange(0, BLOCK_SIZE)` 构造一组连续 Offset，通过 `[:, None]` 与 `[None, :]` 构造 2D Pointer Block：

```python
rows = pid_m * BLOCK_M + tl.arange(0, BLOCK_M)
cols = pid_n * BLOCK_N + tl.arange(0, BLOCK_N)
ptrs = base + rows[:, None] * stride_m + cols[None, :] * stride_n
```

**Masked Load/Store**：Shape 不是 Block Size 整倍数时的基础手段。

```python
mask = offsets < n_elements
value = tl.load(ptr + offsets, mask=mask, other=0.0)
tl.store(out + offsets, value, mask=mask)
```

对 Reduction，`other` 必须选择不会破坏运算的单位元：Sum 用 0，Max 常用负无穷。

**Meta-parameter**：`BLOCK_SIZE: tl.constexpr` 在编译期已知，可决定 Block Shape、静态分支与 Unroll；普通参数如 `n_elements` 通常在运行期传入。不同 `BLOCK_SIZE`、`num_warps`、`num_stages` 会形成不同编译变体，带来性能的同时也增加编译与缓存成本。

## 5. 从 1D 到 2D：Pointer Arithmetic

若矩阵 $X$ 的行、列 Stride 为 $s_m, s_n$：

$$
address(X_{i,j}) = base + i \times s_m + j \times s_n
$$

Triton 处理一个二维 Tile：

```python
offs_m = pid_m * BLOCK_M + tl.arange(0, BLOCK_M)
offs_n = pid_n * BLOCK_N + tl.arange(0, BLOCK_N)
ptrs = x_ptr + offs_m[:, None] * stride_m + offs_n[None, :] * stride_n
mask = (offs_m[:, None] < M) & (offs_n[None, :] < N)
tile = tl.load(ptrs, mask=mask, other=0.0)
```

Pointer Block 的 Shape 是 `[BLOCK_M, BLOCK_N]`。Layout、Stride 与 Program Order 共同决定 Global Memory Coalescing 与 L2 Reuse。

## 6. Block Size、Warp 与 Pipeline

| 参数 | 作用 | 代价 |
| --- | --- | --- |
| `BLOCK_SIZE` | 摊薄 Program 管理开销、增加每 Program 工作量、给 Reduction 更大范围 | Register Live Value 增加、Occupancy 下降、无效 Tail Lane 增多 |
| `num_warps` | 一个 Program 由多少 Warp 协同（4 → 128 线程） | 简单 Pointwise 并非 Warp 越多越好；复杂 Tile/Reduction 可能受益于 8 |
| `num_stages` | 循环 Software Pipelining 的 Stage 数，对分块加载/计算循环更重要 | 更多 Stage 增加重叠，也占用更多片上资源 |
| `num_ctas` | 表达 Cluster 中的 CTA 数，官方接口标注 SM90+ | 需要相应硬件与后端支持 |

RTX 3080 不能通过设置 `num_ctas` 模拟 Hopper Thread Block Cluster。

## 7. Auto-tuning：让配置适配真实 Shape 与 GPU

```python
@triton.autotune(
    configs=[
        triton.Config({"BLOCK_SIZE": 256}, num_warps=4),
        triton.Config({"BLOCK_SIZE": 512}, num_warps=4),
        triton.Config({"BLOCK_SIZE": 1024}, num_warps=8),
    ],
    key=["n_elements"],
)
@triton.jit
def kernel(..., n_elements, BLOCK_SIZE: tl.constexpr):
    ...
```

Tuning Key 改变时，Auto-tuner 会试运行多个配置并选择更快者。三个风险必须理解：

1. **调优成本**：新 Shape 太多会反复 Benchmark 与编译。
2. **副作用**：Auto-tuner 会多次执行 Kernel，In-place/Atomic 更新可能被重复应用；应使用 `reset_to_zero`、`restore_value` 或 Hook 保证每个候选配置看到等价状态。
3. **过拟合**：在空闲机器上选出的配置，不一定代表生产多租户环境。

```bash
TRITON_PRINT_AUTOTUNING=1 python your_kernel.py
```

可查看调优完成后的最佳配置与耗时。不要把 Auto-tuning 时间算入线上请求延迟。

## 8. 性能模型

**Program 数与 Tail 效率**：

$$
N_{program} = \left\lceil \frac{N}{B} \right\rceil, \qquad
\eta_{tail} = \frac{N}{N_{program} \times B}
$$

$N$ 很小却使用巨大 Block 时，Tail Lane 大量被 Mask；Block 太小又会增加 Program 数与调度开销。

**融合 Pointwise 的显存模型**：`out = relu(x * y + bias)` 的 FP32 融合 Kernel

$$
Bytes_{useful} = N \times (2\ \text{reads} + 1\ \text{write}) \times 4 = 12N
$$

约 2 个主要 FLOP，算术强度 $AI \approx 2/12 = 0.167$ FLOP/Byte，通常是 Memory Bound。优化重点是连续访问、一次读写、足够并行度与合理 Block，而不是增加复杂算术技巧。有效带宽 $BW_{effective}=12N/T$ 要与相同 GPU、相近数据规模与访问模式下的稳定测量比较，而不是直接当作显存规格表利用率。

## 9. Level 0：用纯 Python 模拟 Grid 与 Mask

Triton 官方后端当前仍以 GPU 为目标，CPU 后端处于开发中。本实验不伪装成真实 Triton 性能实验，只模拟 Program Instance、Block 与 Tail Mask 的语义。保存为 `triton_grid_sim.py`：

```python
#!/usr/bin/env python3
import argparse, json

def cdiv(x, y):
    return (x + y - 1) // y

def simulated_add(x, y, block_size):
    if len(x) != len(y):
        raise ValueError("x and y length mismatch")
    n = len(x)
    grid = cdiv(n, block_size)
    out, records = [None] * n, []
    for pid in range(grid):
        start = pid * block_size
        offsets = [start + lane for lane in range(block_size)]
        mask = [o < n for o in offsets]
        active = []
        for o, ok in zip(offsets, mask):
            if ok:
                out[o] = x[o] + y[o]
                active.append(o)
        records.append({"program_id": pid, "block_start": start,
                        "active_count": sum(mask),
                        "masked_count": block_size - sum(mask),
                        "active_range": [active[0], active[-1]] if active else None})
    return out, records

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=37)
    p.add_argument("--block-size", type=int, default=16)
    a = p.parse_args()
    if a.n <= 0 or a.block_size <= 0:
        raise SystemExit("n and block-size must be positive")
    x = [float(i) for i in range(a.n)]
    y = [float(2 * i + 1) for i in range(a.n)]
    out, records = simulated_add(x, y, a.block_size)
    if out != [u + v for u, v in zip(x, y)]:
        raise AssertionError("simulation result mismatch")
    grid = cdiv(a.n, a.block_size)
    lanes = grid * a.block_size
    print(json.dumps({"config": vars(a), "grid_size": grid,
                      "total_logical_lanes": lanes, "active_lanes": a.n,
                      "masked_lanes": lanes - a.n, "tail_efficiency": a.n / lanes,
                      "programs": records, "correctness": True,
                      "output_head": out[: min(8, len(out))]},
                     ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

```bash
python3 triton_grid_sim.py --n 37 --block-size 16
python3 triton_grid_sim.py --n 1000 --block-size 256
```

预期现象：`n=37, block=16` 时启动 3 个 Program，最后一个只有 5 个 Active Lane、11 个被 Mask；`correctness` 为 `true`；修改 Block Size 会改变 Grid 数与 Tail Efficiency。模拟器帮助理解 Coverage 与边界，但不包含 Warp Mapping、访存事务、编译器向量化、Register、Shared Memory 或真实并行执行，只能作为语义回退实验，不能推导 GPU 性能。

## 10. Level 1：GPU 上的 Triton 融合算子

**支持与安装**：Triton 官方兼容说明以 Linux 为支持平台，NVIDIA 主线支持 Compute Capability 8.0+。RTX 3080/3090（8.6）与 A100（8.0）满足基础要求；RTX 4090/L40/L40S、H100/H200 以及受当前发行版支持的 Blackwell GPU 可运行相应后端；V100（7.0）不属于当前主线声明的 NVIDIA 支持范围，应改用 CUDA C++、框架算子或与旧环境匹配的方案。

```bash
python -c "import torch; print(torch.__version__, torch.version.cuda)"
python -c "import triton; print(triton.__version__)"
python -m pip install triton   # 环境缺少 Triton 时
```

不要在已有 `torch.compile` 环境里盲目升级单独的 Triton，PyTorch 与 Triton 组合可能存在版本约束。基本 Triton JIT 不要求系统安装 `nvcc`，这与 CUDA C++ Extension 不同。

保存为 `triton_fusion_lab.py`：

```python
#!/usr/bin/env python3
import argparse, json, time
import torch, triton
import triton.language as tl

AUTOTUNE_CONFIGS = [
    triton.Config({"BLOCK_SIZE": 256}, num_warps=4),
    triton.Config({"BLOCK_SIZE": 512}, num_warps=4),
    triton.Config({"BLOCK_SIZE": 1024}, num_warps=8),
]

@triton.autotune(configs=AUTOTUNE_CONFIGS, key=["n_elements"])
@triton.jit
def fused_mul_bias_relu_kernel(x_ptr, y_ptr, out_ptr, n_elements, bias,
                               BLOCK_SIZE: tl.constexpr):
    pid = tl.program_id(axis=0)
    offsets = pid * BLOCK_SIZE + tl.arange(0, BLOCK_SIZE)
    mask = offsets < n_elements
    x = tl.load(x_ptr + offsets, mask=mask, other=0.0)
    y = tl.load(y_ptr + offsets, mask=mask, other=0.0)
    value = x * y + bias
    tl.store(out_ptr + offsets, tl.where(value > 0.0, value, 0.0), mask=mask)

def triton_fused(x, y, bias):
    if not x.is_cuda or not y.is_cuda:
        raise ValueError("x and y must be CUDA tensors")
    if x.dtype != torch.float32 or y.dtype != torch.float32:
        raise ValueError("this lab supports float32 only")
    if not x.is_contiguous() or not y.is_contiguous():
        raise ValueError("this lab requires contiguous tensors")
    if x.shape != y.shape or x.device != y.device:
        raise ValueError("shape and device must match")
    out = torch.empty_like(x)
    n = out.numel()
    grid = lambda meta: (triton.cdiv(n, meta["BLOCK_SIZE"]),)
    fused_mul_bias_relu_kernel[grid](x, y, out, n, bias)
    return out

def torch_reference(x, y, bias):
    return torch.relu(x * y + bias)

def benchmark(fn, warmup, repeat):
    for _ in range(warmup):
        del fn()
    torch.cuda.synchronize()
    start, end = torch.cuda.Event(True), torch.cuda.Event(True)
    wall = time.perf_counter()
    start.record()
    for _ in range(repeat):
        del fn()
    end.record(); end.synchronize()
    return {"cuda_event_ms": start.elapsed_time(end) / repeat,
            "host_wall_ms": (time.perf_counter() - wall) * 1e3 / repeat}

def peak_allocation(fn):
    torch.cuda.empty_cache(); torch.cuda.synchronize()
    base = torch.cuda.memory_allocated()
    torch.cuda.reset_peak_memory_stats()
    out = fn()
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
        raise SystemExit("未检测到 CUDA GPU；请先运行 Level 0")
    dev = torch.device("cuda")
    props = torch.cuda.get_device_properties(dev)
    torch.manual_seed(2026); torch.cuda.manual_seed_all(2026)
    x = torch.randn(a.n, device=dev, dtype=torch.float32)
    y = torch.randn_like(x)

    ref = torch_reference(x, y, a.bias)
    cand = triton_fused(x, y, a.bias)
    err = (ref - cand).abs().max().item()
    if not torch.allclose(ref, cand, rtol=1e-5, atol=1e-6):
        raise AssertionError(f"Triton mismatch: {err}")
    del ref, cand
    torch.cuda.synchronize()

    # 正确性调用已触发 JIT/Autotune，正式计时不含首次编译
    tf = lambda: torch_reference(x, y, a.bias)
    kf = lambda: triton_fused(x, y, a.bias)
    ts, ks = benchmark(tf, a.warmup, a.repeat), benchmark(kf, a.warmup, a.repeat)
    tp, kp = peak_allocation(tf), peak_allocation(kf)
    print(json.dumps({
        "environment": {"torch": torch.__version__, "triton": triton.__version__,
                        "torch_cuda": torch.version.cuda,
                        "device": torch.cuda.get_device_name(dev),
                        "compute_capability": [props.major, props.minor]},
        "config": vars(a),
        "correctness": {"allclose": True, "max_abs_error": err},
        "torch_eager": {"timing": ts, "peak_incremental_allocation_mib": tp / 2**20},
        "triton_fused": {"timing": ks, "peak_incremental_allocation_mib": kp / 2**20,
                         "modeled_effective_gbps": a.n * 12 / (ks["cuda_event_ms"] / 1e3) / 1e9},
        "speedup_by_cuda_event": ts["cuda_event_ms"] / ks["cuda_event_ms"],
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

```bash
TRITON_PRINT_AUTOTUNING=1 python triton_fusion_lab.py --n 16777216 --warmup 10 --repeat 50
CUDA_VISIBLE_DEVICES=0 python triton_fusion_lab.py --n 16777216
CUDA_VISIBLE_DEVICES=1 python triton_fusion_lab.py --n 16777216
```

预期现象：输出 Triton、PyTorch、CUDA、GPU、Compute Capability 与显存信息；`correctness.allclose` 为 `true`；第一次新 Shape 运行会出现 JIT/Auto-tuning 延迟；缓存命中后的 Triton Kernel 是一次融合 Launch，而 Eager Reference 可能生成多个 Kernel 与中间 Tensor；Triton 增量峰值显存通常更低；Speedup 随 GPU、Shape、版本、频率与 PyTorch 实现变化，不保证大于 1。

与 CUDA C++ 版本追求同样的数据流（两次读、一次写、中间值留在片上），区别在于：CUDA C++ 显式控制 Thread、Block 与低层 API；Triton 以 Program/Block Tensor 表达数据块，编译器负责更多映射；Triton Auto-tuner 可按 Shape 与 GPU 搜索配置；CUDA C++ 在特殊指令、复杂同步与成熟 Library 集成上仍有更细控制。

## 11. 进阶：Reduction 与 Softmax 的 Triton 思维

$$
y_i = \frac{e^{x_i - \max(x)}}{\sum_j e^{x_j - \max(x)}}
$$

朴素框架实现可能物化 Max、Shift、Exp、Sum、Divide 等中间 Tensor。Triton 的典型策略是让一个 Program 处理一行，把整行装进 Block Tensor，在片上完成两次 Reduction：

```python
@triton.jit
def softmax_kernel(out_ptr, in_ptr, in_row_stride, out_row_stride,
                   n_cols, BLOCK_SIZE: tl.constexpr):
    row = tl.program_id(0)
    cols = tl.arange(0, BLOCK_SIZE)
    mask = cols < n_cols
    x = tl.load(in_ptr + row * in_row_stride + cols, mask=mask, other=-float("inf"))
    x = x - tl.max(x, axis=0)                 # 数值稳定：减去行最大值
    num = tl.exp(x)
    den = tl.sum(num, axis=0)
    tl.store(out_ptr + row * out_row_stride + cols, num / den, mask=mask)
```

要点：`BLOCK_SIZE` 取 $\ge$ `n_cols` 的 2 的幂；`other=-inf` 保证 Mask 位置不影响 Max；一行一个 Program 时 `num_warps` 影响 Reduction 的树形层级；列数极大时需要分块两趟（先求 Max/Sum，再归一化）或 Online Softmax，不能假设整行永远装得下。

## 12. 选型边界与排错

| 场景 | 更合适的选择 |
| --- | --- |
| 标准 GEMM/Conv/Attention 主路径 | cuBLAS/cuBLASLt、CUTLASS、cuDNN、FlashAttention 等成熟库 |
| 规则 Pointwise 链、轻量 Reduction、自定义 Epilogue | Triton |
| 特殊指令、复杂同步、Warp-specialized 流水、极致控制 | CUDA C++ |
| 整图级融合与调度、减少 Python Dispatch | `torch.compile`（其后端本身可能生成 Triton） |
| 快速验证语义、无 GPU 环境 | PyTorch/NumPy Reference 或纯 Python 模拟 |

排错顺序：先用 `TRITON_INTERPRET=1` 在解释器中逐 Program 检查语义与 Mask；再用断言比对 Reference（含 Tail、空 Tensor、极值）；接着用 Compute Sanitizer 查越界与竞态；最后用 Nsight Systems 确认 Launch 数与 Gap、用 Nsight Compute 确认 DRAM 流量、Register 与 Occupancy。架构能力要分别核对：Ampere/Ada/Hopper/Blackwell 在 Cluster、TMA、低精度格式上的支持不同，不能把某一架构的特性写成通用前提。

## 写在最后

Triton 把「块」变成一等公民，让融合与分块的表达成本大幅下降，但性能工程的全部判断——流量、Tail、Occupancy、编译变体与调优副作用——仍然要自己做。下一篇回到系统层：把这些 Kernel 放进大模型分布式训练体系里看整体效率。

下一篇：[大模型分布式训练体系](/source/AI-Infra/2-AI系统性能工程/15-大模型分布式训练体系)。