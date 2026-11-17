# GPU 架构深度解析

本篇深入 GPU 微架构与执行模型，把 SM、Warp、调度与并行效率之间的关系讲清楚。

写出能在 GPU 上运行的程序并不难，难的是解释它为什么快、为什么慢，以及换一张卡后为什么结论可能完全改变。这里建立的心智模型，是后续 CUDA、GPU Memory、Tensor Core、Kernel Fusion、Triton 与分布式优化共同依赖的基础：**GPU 不是「很多个更快的 CPU 核」，而是一台依靠大规模并行、快速线程切换和分层存储隐藏延迟的吞吐机器。**

## 1. 内容概览

- CUDA 执行层级（Grid/Block/Warp/Thread）与物理层级（GPC/SM）的映射。
- SIMT、分支发散、合并访存与延迟隐藏。
- Occupancy 的资源约束模型，以及它为什么不是越高越好。
- Roofline 上界与端到端时间的近似拆解。
- Ampere / Ada / Hopper / Blackwell 的能力边界。

## 2. 本篇要点

1. 解释 Grid、Block、Warp、Thread 与 GPC、SM 的映射关系。
2. 解释 SIMT、分支发散、合并访存、延迟隐藏和指令级并行。
3. 计算寄存器、共享内存、线程数共同限制下的理论 Occupancy。
4. 区分 Occupancy、SM 利用率、Tensor Core 利用率和实际性能。
5. 用 Roofline 判断算子更可能受计算还是显存带宽限制。
6. 正确识别 Ampere、Ada Lovelace、Hopper 与 Blackwell 的能力边界。

## 3. 核心直觉：GPU 是吞吐机器，不是低延迟机器

CPU 的典型目标是让少量复杂线程尽快完成，因此投入大量晶体管做分支预测、乱序执行和大缓存；GPU 的典型目标是让海量相似工作在单位时间内完成，因此把更多资源投入算术单元、线程上下文和高带宽数据通路。

一个 GPU 操作访问 HBM 时，单个 Warp 仍可能等待很久。GPU 的办法不是把这次访问变得像寄存器一样快，而是让当前 Warp 等待时，Warp Scheduler 立刻发射另一个已就绪的 Warp：

![延迟隐藏：Warp A 等访存时调度器发射就绪的 B/C](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l05_01.png)

这叫延迟隐藏，它成立需要三个条件：有足够多的就绪 Warp；指令之间没有过长的依赖链；数据布局没有制造严重的额外内存事务。

所以 GPU 优化的核心问题不是「线程越多越好吗」，而是「此刻有没有可发射的 Warp，它发出的指令能不能打满目标管线」。

## 4. 从软件层级到硬件层级

### 4.1 CUDA 执行层级

```text
Grid
└── Thread Block
    └── Warp（当前 NVIDIA CUDA 架构固定为 32 个线程）
        └── Thread
```

- **Grid**：一次 Kernel launch 产生的全部线程块。
- **Thread Block**：能在共享内存中协作、能用块级同步原语同步的一组线程。
- **Warp**：硬件调度和发射的基本线程组，含 32 个线程。
- **Thread**：执行同一 Kernel 程序的逻辑线程实例。

线程块被分配到 SM（Streaming Multiprocessor）上；一个块开始执行后，其线程、寄存器和共享内存资源都驻留在同一个 SM，普通 CUDA 编程模型不会把一个线程块拆到多个 SM 上执行。

### 4.2 物理层级

```text
GPU
├── GPC / 更高层处理分区
│   ├── SM
│   │   ├── Warp Scheduler / Dispatch
│   │   ├── 标量与浮点计算管线
│   │   ├── Tensor Core
│   │   ├── Load/Store 与特殊函数单元
│   │   ├── Register File
│   │   └── Shared Memory / L1
│   └── SM ...
├── 共享 L2 Cache
├── Memory Controller
└── GDDR 或 HBM
```

不要把 CUDA Thread 机械对应为「CUDA Core」：线程是程序状态，Core 是执行资源；大量线程的指令会在时间上复用有限的执行管线。

### 4.3 SM 内真正竞争的资源

同一个 SM 上可以同时驻留多个线程块，但会共同竞争：最大驻留线程数与 Warp 数、最大驻留线程块数、Register File、Shared Memory、Warp Scheduler 与执行管线、Load/Store 单元和缓存带宽。

任何一项达到上限，新的线程块都无法驻留。正因如此，只看 `threads_per_block` 无法判断 Occupancy。

## 5. SIMT、Warp 与分支发散

### 5.1 SIMT 不是简单 SIMD

NVIDIA 使用 SIMT（Single Instruction, Multiple Threads）组织线程：一个 Warp 中的线程执行同一 Kernel，但每个线程拥有自己的寄存器状态、线程索引和控制流状态。

当 Warp 中所有线程走同一分支时效率高：

```cuda
if (blockIdx.x < split) {
    // 整个 block 通常走相同路径
}
```

如果同一 Warp 内线程按奇偶走不同分支：

```cuda
if ((threadIdx.x & 1) == 0) {
    path_a();
} else {
    path_b();
}
```

硬件必须分别执行有效线程掩码对应的路径，再汇合控制流；若两条路径代价相近，理想情况下的有效线程工作比例可能接近一半。可定义简化的分支效率：

$$
\eta_{branch} = \frac{\text{有效线程指令数}}{\text{发射槽覆盖的线程指令数}}
$$

这不是分析工具的严格定义，但能说明：同一 Warp 内路径越碎，执行槽位浪费通常越多。

### 5.2 发散不一定来自 `if`

以下现象也会制造控制流或工作量不均衡：不同 Token 经过长度差异很大的序列；MoE 中不同专家收到的 Token 数差异过大；稀疏计算中每行非零元素数量不同；线程内循环次数由数据决定；尾块只有少量线程处理有效元素。

优化时要问的不是「有没有 `if`」，而是「同一 Warp 中的活跃掩码和工作量是否一致」。

## 6. 内存层级与合并访问

| 层级 | 典型作用域 | 特征 |
| --- | --- | --- |
| Register | 单线程 | 最靠近执行管线，容量有限，过多会降低驻留度或发生 spill |
| Shared Memory / L1 | 单 SM / 单 Block 协作 | 软件可控复用、低延迟，但容量有限 |
| L2 Cache | 整个 GPU | SM 间共享，产品容量差异很大 |
| GDDR / HBM | 整个 GPU | 容量与带宽大，但访问延迟高 |
| Host Memory | CPU 侧 | 通常经 PCIe/NVLink-C2C 等链路访问或搬运 |

最重要的一条是：一个 Warp 的全局内存访问会被合并为若干内存事务。假设每个线程读取 4 字节元素：

- 连续 32 个线程读连续地址时，请求的 128 字节能由少量连续事务覆盖。
- 步长增大时，地址散落到更多内存段。
- 总请求字节不变，实际搬运字节却可能成倍增加。

简化的传输效率：

$$
\eta_{mem} = \frac{\text{线程实际请求字节}}{\text{内存事务搬运字节}}
$$

步长为 1 不保证所有场景都完美（还要看地址对齐、元素宽度、缓存命中与具体指令），但它是最可靠的第一直觉。

## 7. Occupancy：资源约束下能驻留多少 Warp

### 7.1 理论模型

设 SM 的资源上限为：最大驻留线程数 $T_{SM}$、最大驻留块数 $B_{SM}$、32 位寄存器总数 $R_{SM}$、共享内存总量 $S_{SM}$、最大驻留 Warp 数 $W_{SM}$。Kernel 每块使用 $T_b$ 个线程、每线程 $R_t$ 个寄存器、每块 $S_b$ 字节共享内存。

忽略分配粒度时，可驻留块数的简化上界为：

$$
B_{active} = \min\left(B_{SM}, \left\lfloor\frac{T_{SM}}{T_b}\right\rfloor, \left\lfloor\frac{R_{SM}}{R_t T_b}\right\rfloor, \left\lfloor\frac{S_{SM}}{S_b}\right\rfloor\right)
$$

其中 $S_b=0$ 时不构成限制。每块 Warp 数 $W_b = \lceil T_b/32 \rceil$，理论 Occupancy 为：

$$
\mathrm{Occupancy} = \frac{\min(B_{active} W_b, W_{SM})}{W_{SM}}
$$

实际硬件还有寄存器和共享内存分配粒度、块级上限、编译器资源分配等细节，因此手算模型用于定位限制因素，最终应以 CUDA Occupancy API、编译器输出与 Nsight Compute 为准。

### 7.2 为什么 Occupancy 不是越高越好

高 Occupancy 能提供更多候选 Warp，有助隐藏延迟，但不能保证：每个 Warp 都已就绪；指令混合能填满目标执行管线；数据访问是合并的；Tensor Core 或内存带宽被充分利用；算法做的是有效工作。

一个寄存器复用充分、指令级并行高的计算 Kernel，可能在 50% Occupancy 时已接近峰值；反过来，一个 100% Occupancy 的随机访存 Kernel 仍可能很慢。优化目标不是最大化 Occupancy，而是消除阻止性能继续提升的真实瓶颈。

## 8. 性能模型：计算、带宽、延迟和依赖

### 8.1 Roofline 上界

设算子完成 $F$ 次浮点运算、从目标内存层级搬运 $Q$ 字节，则算术强度 $AI = F/Q$（FLOP/Byte）。设设备峰值计算吞吐 $P_{peak}$、目标内存层级带宽 $BW$，则

$$
P \le \min(P_{peak},\ BW \times AI), \qquad AI_{ridge} = \frac{P_{peak}}{BW}
$$

$AI < AI_{ridge}$ 时更可能受带宽限制；$AI > AI_{ridge}$ 时更可能受计算吞吐限制；若实测远低于两条上界，还应检查访存事务、指令依赖、发散、Launch、同步或负载不均衡。

### 8.2 端到端时间不是单一 Roofline

$$
T \gtrsim T_{launch} + \max(T_{compute}, T_{memory}) + T_{dependency} + T_{imbalance} + T_{sync}
$$

这不是严格可加的物理公式（计算与访存可能重叠，各项也会相互作用），它的价值是提醒：峰值 FLOPS 和显存带宽只能解释上界，不能解释所有低效。

## 9. 四代架构：不要只背产品名

Compute Capability（CC）是 CUDA 暴露的硬件能力版本。市场架构名、具体芯片、产品型号和 CC 不是同一个概念；优化代码必须同时检查产品与 CC，不能因为「年份新」就直接启用特性。

| 架构 | 常见产品示例 | 典型 CC | 关注点 |
| --- | --- | --- | --- |
| Ampere | RTX 3080/3090、A100 | 8.6 / 8.0 | 第三代 Tensor Core、TF32/BF16、异步全局到共享内存拷贝 |
| Ada Lovelace | RTX 4090、L40/L40S | 8.9 | 第四代 Tensor Core、产品相关的大 L2、FP8 硬件能力与软件栈边界 |
| Hopper | H100/H200 | 9.0 | TMA、Thread Block Cluster、分布式共享内存、FP8 训练 |
| Blackwell 数据中心 | B100/B200/GB200 | 10.x | 第五代 Tensor Core、FP4/FP6、增强 TMA 与集群能力 |
| Blackwell GeForce | RTX 5090 | 12.0 | 消费级路径，资源与可移植目标不同于 B200 |

关键纠错：

- RTX 4090 是 **Ada Lovelace**，不是 Blackwell。
- RTX 5090 与 B200 都属于 Blackwell，但 CC 12.0 与 CC 10.x 不是同一执行目标。
- A100 与 RTX 3090 都是 Ampere，但前者 CC 8.0、后者 CC 8.6，每 SM 最大 Warp 数、共享内存与块驻留上限并不相同。
- 「硬件指令格式存在」不等于任意框架、驱动和算子都能直接获得对应加速。

### 9.1 资源差异为何会改变最佳参数

| CC 示例 | 最大 Warp/SM | 最大线程/SM | Shared Memory/SM | 说明 |
| --- | --- | --- | --- | --- |
| 8.0 A100 | 64 | 2048 | 164 KB | 数据中心 Ampere |
| 8.6 RTX 3080/3090 | 48 | 1536 | 100 KB | 消费级 Ampere |
| 8.9 Ada | 48 | 1536 | 100 KB | 产品具体缓存容量另查规格 |
| 9.0 Hopper | 64 | 2048 | 228 KB | 支持 TMA 与 Cluster |
| 10.0 B200 | 64 | 2048 | 228 KB | 数据中心 Blackwell |
| 12.0 RTX 5090 | 48 | 1536 | 128 KB | 单块可用共享内存上限低于 SM 总量 |

这些是编程模型资源上限，不等于性能排名。时钟、SM 数量、显存类型、缓存、功耗限制和具体指令吞吐都依产品而异。

同一个每块使用 64 KB 共享内存的 Kernel，在 100 KB/SM 的设备上通常最多驻留 1 块，在 164 KB 或 228 KB/SM 的设备上可能驻留更多块。于是最佳 Tile 大小、流水级数和每线程寄存器预算都会改变。

### 9.2 Ampere：现代通用基线

- Tensor Core 支持 TF32，让许多 FP32 矩阵乘法在允许时走 Tensor Core。
- 支持 BF16/FP16 等训练格式。
- CUDA 异步拷贝可直接把数据从全局内存搬到共享内存，减少中间寄存器占用并支持搬运与计算重叠。
- A100（CC 8.0）与 RTX 30 系列（CC 8.6）的资源上限不同。

对 RTX 3080/3090，实验优先使用 FP32、TF32、FP16/BF16 能力检测与通用 CUDA 路径，不假设具备数据中心互联或 FP8 训练栈。

### 9.3 Ada Lovelace：4090 不是 Blackwell

Ada 的第四代 Tensor Core 和更大的产品级 L2 可改善许多图形与 AI 工作负载。CC 8.9 的 Tensor Core 指令能力包括 FP8，但能否从 PyTorch 或特定推理引擎稳定使用，取决于 GPU 产品、驱动、CUDA、框架、算子实现和数据缩放策略。

因此对 RTX 4090，正确方式是先检测数据类型与算子是否受支持，再测速度与误差；不能只看到「FP8」字样就假设它等价于 H100 上的 Transformer Engine 训练。

### 9.4 Hopper：数据搬运也成为可编排管线

TMA（Tensor Memory Accelerator）可以描述 1D 到 5D 张量搬运，在全局内存、共享内存及集群相关存储之间执行异步传输，减少参与搬运的线程与寄存器开销，并支持更明确的 Warp 专门化：部分 Warp 管搬运、部分 Warp 管计算。

Thread Block Cluster 允许一组线程块进行硬件级协作，并通过 Distributed Shared Memory 访问集群内其他块的共享内存。它不是「所有 GPU 都能模拟的普通共享内存技巧」；没有 H100/H200 时只能学习调度与流水模型，不能声称完成等价硬件验证。

### 9.5 Blackwell：数据中心与消费级要分开看

Blackwell 引入第五代 Tensor Core，并在相关产品上扩展 FP4/FP6 等低精度能力。但 B200/GB200 常用的 CC 10.x 路径与 RTX 5090 的 CC 12.0 路径有实质差别：每 SM 最大驻留 Warp 数不同；Shared Memory 总量与单块上限不同；某些架构专用 PTX、Tensor Memory 和集群能力不能跨目标复用；软件栈对新数据类型与 Kernel 的支持需逐项确认。

移植 Blackwell 专项代码时，应把 `sm_100`、`sm_100a`、`sm_120` 等目标当成不同能力集合管理，提供运行时检测与回退 Kernel。

## 10. 瓶颈分析方法

### 10.1 先确认工作是否正确

与可信实现比较输出；固定随机种子和输入形状；明确精度容差与数据类型；确认没有把异步 GPU 时间误当成完成时间。错误的结果没有优化价值。

### 10.2 判断瓶颈类别

| 现象 | 可能瓶颈 | 优先检查 |
| --- | --- | --- |
| DRAM 吞吐接近平台可达上限、计算管线偏低 | 显存带宽 | 算术强度、合并访存、数据复用 |
| Tensor Core 活跃度低、普通浮点管线高 | 未走 Tensor Core | 形状、dtype、布局、框架开关 |
| 两者都低、Warp 经常无可发射指令 | 延迟或依赖 | Occupancy、长依赖链、随机访存 |
| Occupancy 受寄存器限制 | 每线程状态过多 | 编译器寄存器报告、spill、本地内存 |
| Occupancy 受共享内存限制 | Tile 或流水级过大 | 每块共享内存、双缓冲级数 |
| 分支效率低 | Warp 发散 | 活跃掩码、数据分组、尾部处理 |
| Kernel 很短且调用极多 | Launch/调度 | Fusion、CUDA Graph、批量化 |
| 单卡快、多卡慢 | 通信或负载失衡 | 拓扑、NCCL、重叠、分片均衡 |

### 10.3 建立可证伪假设

不要说「GPU 没跑满」，要说：

- 「每块 96 KB 共享内存使 CC 8.6 上只能驻留一个块，导致内存延迟难以隐藏。」
- 「Warp 以 stride=16 读取 4 字节元素，请求字节与事务字节比例很低。」
- 「矩阵维度与 dtype 没触发目标 Tensor Core 路径。」

然后一次只改变一个变量，并记录正确性、延迟、吞吐和关键硬件计数器。

### 10.4 选择工具

- `nvidia-smi`：产品、驱动、功耗、显存和粗粒度利用率。
- PyTorch Profiler：框架算子、CPU/GPU 时间和形状。
- Nsight Systems：端到端时间线、Kernel 间空洞、CPU/GPU 与通信重叠。
- Nsight Compute：单 Kernel 的 Warp、Occupancy、内存事务和管线计数器。
- `nvcc --ptxas-options=-v`：寄存器、共享内存、spill 等编译资源报告。

`nvidia-smi` 的 GPU Utilization 只表示采样窗口内是否有 Kernel 活动，不能替代 Kernel 级诊断。

## 11. 完整可运行实验：资源、发散、访存与 Roofline

实验分三级：

- **Level 0**：仅依赖 Python 标准库，任何机器都能运行资源上限、Warp 发散、合并访存和 Roofline 模型。
- **Level 1**：可选 PyTorch，自动选择 CPU/CUDA，测量逐元素加法、连续/跨步归约和矩阵乘法。
- **Level 2**：按 CC 检测架构能力，再决定是否进入 TMA、Cluster、FP8/FP4 专项实验。

```python
"""GPU microarchitecture models: occupancy, divergence, coalescing, roofline."""

CC_PRESETS = {
    "ampere_a100":   dict(warps=64, threads=2048, regs=65536, smem_kb=164),
    "ampere_geforce": dict(warps=48, threads=1536, regs=65536, smem_kb=100),
    "ada":           dict(warps=48, threads=1536, regs=65536, smem_kb=100),
    "hopper":        dict(warps=64, threads=2048, regs=65536, smem_kb=228),
    "blackwell_dc":  dict(warps=64, threads=2048, regs=65536, smem_kb=228),
    "blackwell_gf":  dict(warps=48, threads=1536, regs=65536, smem_kb=128),
}


def occupancy(preset, block_threads, regs_per_thread, smem_bytes_per_block, max_blocks=32):
    p = CC_PRESETS[preset]
    by_threads = p["threads"] // block_threads
    by_regs = p["regs"] // (regs_per_thread * block_threads)
    by_smem = p["smem_kb"] * 1024 // smem_bytes_per_block if smem_bytes_per_block else 10**9
    blocks = max(0, min(max_blocks, by_threads, by_regs, by_smem))
    warps_per_block = -(-block_threads // 32)
    return {
        "resident_blocks": blocks,
        "resident_warps": blocks * warps_per_block,
        "occupancy": round(min(blocks * warps_per_block, p["warps"]) / p["warps"], 3),
        "limit": min(
            (by_threads, "threads"), (by_regs, "registers"),
            (by_smem, "shared_memory"), (max_blocks, "max_blocks"),
        )[1],
    }


def branch_efficiency(active_lanes):
    # active_lanes: 每个分支路径的活跃线程数，例如 [16, 16] 表示同一 Warp 内两路各 16
    issued = 32 * len(active_lanes)       # 每次都要覆盖整个 Warp 发射槽
    useful = sum(active_lanes)
    return round(useful / issued, 3)


def coalescing_efficiency(stride_elems, elem_bytes=4, lanes=32, line_bytes=128):
    request = lanes * elem_bytes
    span = (lanes - 1) * stride_elems * elem_bytes + elem_bytes
    transactions = -(-span // line_bytes)
    return {"requested_bytes": request, "moved_bytes": transactions * line_bytes,
            "efficiency": round(request / (transactions * line_bytes), 3)}


def roofline(flops, bytes_moved, peak_flops, peak_bw):
    ai = flops / bytes_moved
    bound = min(peak_flops, peak_bw * ai)
    return {"arithmetic_intensity": round(ai, 2), "achievable_flops": round(bound, 3),
            "bottleneck": "compute" if peak_flops <= peak_bw * ai else "memory"}


if __name__ == "__main__":
    print("occupancy a100 256t/64reg/0smem:", occupancy("ampere_a100", 256, 64, 0))
    print("occupancy geforce 256t/128reg/0smem:", occupancy("ampere_geforce", 256, 128, 0))
    print("occupancy geforce 256t/64reg/96KB:", occupancy("ampere_geforce", 256, 64, 96 * 1024))
    print("branch eff [32]:", branch_efficiency([32]), " [16,16]:", branch_efficiency([16, 16]))
    print("coalesce stride=1:", coalescing_efficiency(1), " stride=16:", coalescing_efficiency(16))
    print("roofline gemm:", roofline(2 * 4096**3, 3 * 4096**2 * 2, 312e12, 1.55e12))
    print("roofline add :", roofline(2 * 10**8, 3 * 10**8 * 4, 312e12, 1.55e12))
```

Level 1 用 PyTorch 做实测（把 `peak_flops`、`peak_bw` 换成本机规格）：

```python
import time
import torch

x = torch.randn(4096, 4096, device="cuda", dtype=torch.bfloat16)
for _ in range(5):
    y = x @ x
torch.cuda.synchronize()
t0 = time.perf_counter()
for _ in range(20):
    y = x @ x
torch.cuda.synchronize()
ms = (time.perf_counter() - t0) / 20 * 1000
tflops = 2 * 4096**3 / (ms / 1000) / 1e12
print(f"{ms:.3f} ms  {tflops:.1f} TFLOPS")
```

先算 Roofline 上界，再看实测离开上界多远，比直接盯着「TFLOPS 数字」更有诊断价值。

## 写在最后

这一篇给的是「读硬件」的能力：从 block 大小、寄存器、共享内存、访存步长和 dtype，推断它受哪类资源限制。下一篇专门讲显存体系——容量、带宽、缓存与数据搬运，那是 GPU 上最常被低估的瓶颈来源。

下一篇：[GPU Memory 体系优化](/source/AI-Infra/2-AI系统性能工程/06-GPUMemory体系优化)。
