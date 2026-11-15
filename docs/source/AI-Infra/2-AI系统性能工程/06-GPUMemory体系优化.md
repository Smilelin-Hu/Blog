# GPU Memory 体系优化

本篇梳理 GPU 显存层次与数据搬运路径，把容量、带宽和访问延迟的优化方法讲清楚。

GPU 有很高的峰值计算能力，但算术单元只有拿到数据才能工作。很多 AI Kernel 的真正瓶颈不是「算得不够快」，而是数据从错误的位置、以错误的布局、在错误的时间到达计算单元。

## 1. 内容概览

- Register、Local Memory、Shared Memory、L1、L2、GDDR/HBM、Host Memory 的作用域与性能关系。
- 有效带宽、内存访问效率、数据复用率三个可直接用于诊断的指标。
- 连续/跨步访问、对齐、AoS 与 SoA、向量化对事务的影响。
- Shared Memory 的 Bank Conflict 与 padding。
- Pinned Memory、`non_blocking`、Stream 与双缓冲。
- PyTorch 缓存分配器：allocated / reserved / nvidia-smi 三种口径。

## 2. 本篇要点

1. 解释各层内存的作用域和性能关系。
2. 用有效带宽、算术强度和事务效率判断 Memory Bottleneck。
3. 解释连续访问、跨步访问、对齐、AoS/SoA 布局对内存事务的影响。
4. 识别 Shared Memory Bank Conflict，并用 padding 消除冲突。
5. 解释寄存器压力、spill、Occupancy 与数据复用之间的权衡。
6. 正确使用 Pinned Memory、`non_blocking=True`、Stream 与双缓冲。
7. 理解 `memory_allocated`、`memory_reserved`、缓存分配器、碎片与 OOM 的区别。

## 3. 核心直觉：优化 Memory 不是「少用显存」这么简单

GPU Memory 优化至少包含四个彼此不同的问题：

1. **容量**：模型、激活、优化器状态和临时 Workspace 能否放下？
2. **带宽**：单位时间能搬运多少有效数据？
3. **延迟**：一次依赖性访问要等待多久，能否被其他 Warp 隐藏？
4. **流量**：算法到底需要从目标层级搬多少字节？

一段代码显存占用更少，不代表它更快；一段代码达到很高 DRAM 带宽，也不代表它最优——如果它重复读取本可复用的数据，那么「带宽跑满」可能只是高效地搬运了大量无效流量。

## 4. GPU Memory 层级

```text
每个线程
  Register
     │  寄存器不足时可能 spill
     ▼
  Local Memory（逻辑上线程私有，物理上位于设备内存）

每个 SM / Thread Block 协作
  Shared Memory ↔ L1 Cache
             │
             ▼
全 GPU 共享
  L2 Cache
     │
     ▼
设备显存
  GDDR / HBM
     │
     ▼
系统链路
  PCIe / NVLink-C2C 等
     │
     ▼
Host DRAM（pageable / pinned）
     │
     ▼
SSD / 网络存储
```

「越靠上越快」是有用直觉，但不能机械理解：Register 延迟低但容量小，用多了会降低驻留 Warp 数或造成 spill；Shared Memory 可编程、适合 Block 内复用，但消耗有限的 SM 资源且可能 Bank Conflict；L1/L2 由硬件管理，命中率取决于工作集、访问模式与竞争；HBM/GDDR 容量与带宽大但延迟高；Host Memory 容量更大但更远，跨链路搬运通常远慢于设备内访问。

### 4.1 Register 与 Local Memory

寄存器是线程最直接使用的存储，循环累加器、索引、地址和中间值通常放在寄存器中。

「Local Memory」这个名字容易误导：它的作用域对单线程是 local，但物理存储通常在片外设备内存，并经过缓存层级。以下情况可能让编译器使用 Local Memory：每线程寄存器需求过大发生 spill；线程私有数组无法静态索引到寄存器；大型线程局部对象；某些动态索引或编译器决策。

因此减少寄存器并不总是优化。如果从 96 个寄存器强行压到 64 个，Occupancy 可能提高，但 spill 带来的设备内存访问可能让 Kernel 更慢。

### 4.2 Shared Memory 与 L1

Shared Memory 位于 SM 上，由 Block 中的线程显式管理。典型用途：把全局内存 Tile 搬入片上后重复使用；把非连续访问重排为连续事务；在线程之间交换部分结果；构建归约、扫描、矩阵乘法和卷积 Tile；构建多级异步流水。

Shared Memory 与 L1 的容量组织随架构变化，写通用代码时应查询设备属性，而不是假设固定 KB 数值。

### 4.3 L2 与设备显存

L2 对所有 SM 可见，是跨 Block 数据复用、原子操作与 DRAM 流量之间的重要缓冲层。L2 容量是具体产品属性，不能只按架构名推断。

设备显存可能是 GDDR，也可能是 HBM：RTX 3080/3090、4090、5090 等消费级卡通常用 GDDR；A100、H100/H200、B100/B200 等数据中心产品通常用 HBM。HBM 的高总线并行度适合大带宽负载，但「HBM 一定比所有 GDDR 更快」不是严谨结论，必须比较具体产品、数据类型、功耗状态与可达带宽。

### 4.4 Host Memory：pageable、pinned 与 unified

普通 pageable 内存可能被操作系统换出或移动。Pinned Memory 被锁定在物理内存，便于 DMA，在离散 GPU 的 Host↔Device 大块传输中通常能获得更好吞吐，也是可靠异步传输的重要条件。

但 Pinned Memory 是稀缺系统资源：分配和锁页本身有成本；过量 pin 会影响整个系统；把普通 Tensor 临时 `.pin_memory()` 再立即拷贝可能比直接 `.to()` 更慢；更适合在 DataLoader 或复用缓冲池中预先准备。

Unified Memory 提供统一地址与按需迁移，适合简化编程或让超出显存的数据仍能运行，但页面故障和迁移会带来不可预测延迟。对稳定低延迟与高吞吐负载，它通常是容量安全网，而不是自动性能优化。

## 5. 性能模型

### 5.1 有效带宽

若一次操作从内存读 $R$ 字节、写 $W$ 字节、耗时 $t$ 秒：

$$
BW_{effective} = \frac{R + W}{t}
$$

以 FP32 向量加法 $C = A + B$ 为例，忽略缓存与额外事务：$R = 2N \times 4$、$W = N \times 4$，于是 $BW_{effective} = 12N/t$。它衡量完成有效工作所处理的逻辑字节，不等于硬件计数器看到的真实 DRAM 字节。

### 5.2 请求带宽、实际带宽与效率

设线程实际需要 $Q_{requested}$ 字节，但由于对齐、跨步、事务粒度等原因，内存系统实际搬运 $Q_{actual}$ 字节：

$$
\eta_{memory} = \frac{Q_{requested}}{Q_{actual}}
$$

例如一个 Warp 读取 32 个连续 FP32，共请求 128 字节，在 CC 6.0+ 的常见合并模型中通常由 4 个 32 字节事务覆盖。若每个 lane 间隔 32 字节，可能触及 32 个不同的 32 字节段：仍只使用 128 字节，却可能搬运 1024 字节，简化效率 12.5%。

真实结果还会受缓存复用、地址对齐、写策略与硬件代际影响，因此事务模型用于解释原因，硬件计数器用于给出最终证据。

### 5.3 数据复用与算术强度

设同一批数据从 DRAM 读一次后，在 Shared Memory 或 Register 中使用 $K$ 次，则 DRAM 字节数不随 $K$ 成比例增加，算术强度上升：

$$
AI = \frac{\mathrm{FLOPs}}{\mathrm{Bytes}_{target\ memory\ level}}
$$

必须明确「相对哪个层级」计算 AI：一个 Kernel 对 HBM 有高复用，仍可能受 Shared Memory 带宽或 Register 依赖限制。

### 5.4 容量模型

训练显存不只包含参数：

$$
M_{total} \approx M_{param} + M_{grad} + M_{optimizer} + M_{activation} + M_{workspace} + M_{fragmentation}
$$

推理还要加入 KV Cache：

$$
M_{inference} \approx M_{weights} + M_{KV} + M_{workspace} + M_{runtime}
$$

这解释了为什么「模型权重只有 14 GB」不代表 20 GB 显存一定能训练或承载目标并发。

### 5.5 拷贝与计算重叠

若 Host→Device 拷贝耗时 $T_{copy}$、GPU 计算耗时 $T_{compute}$：串行流水单步约 $T_{copy} + T_{compute}$；双缓冲理想稳态约 $\max(T_{copy}, T_{compute})$。

能否重叠取决于：pinned host buffer；非阻塞拷贝；不同 CUDA Stream 与正确事件依赖；设备是否支持对应方向的并发 copy/compute；缓冲区不能在拷贝完成前被覆盖；数据准备是否及时。

`non_blocking=True` 只是不在调用点主动同步，不等于自动产生端到端重叠。

## 6. 全局内存访问优化

### 6.1 连续、对齐和合并

最常见的好模式是：Warp 中相邻 lane 访问相邻元素。

```cuda
int i = blockIdx.x * blockDim.x + threadIdx.x;
y[i] = x[i];
```

跨步模式可能浪费事务：

```cuda
int i = (blockIdx.x * blockDim.x + threadIdx.x) * stride;
y[i] = x[i];
```

但「Tensor 不是 contiguous」不等于一定慢：转置视图可能被后续高性能算子直接支持，某些维度跨步也可能与实际线程映射匹配。正确做法是看生成 Kernel 的地址模式和实际事务，而不是看到 `is_contiguous=False` 就无条件复制。

### 6.2 AoS 与 SoA

假设每个对象有 `x、y、z、type` 四个字段。

```text
Array of Structures:  [x0 y0 z0 t0][x1 y1 z1 t1][x2 y2 z2 t2]...
Structure of Arrays:  x0 x1 x2 ... | y0 y1 y2 ... | z0 z1 z2 ... | t0 t1 t2 ...
```

若 Kernel 只读 `x`，SoA 更容易让相邻 lane 读取相邻有效数据；AoS 会把未使用字段一起带入缓存线和事务。若每次总要读取完整对象，AoS 也可能合理。布局必须服务于访问模式。

### 6.3 向量化访问

`float4`、128-bit load/store 或编译器生成的向量指令可以减少指令数量，但前提是：地址满足对齐要求；尾部元素正确处理；向量宽度不会增加无效字节；寄存器压力没有抵消收益。向量化改善的可能是指令吞吐，而不一定提升 DRAM 峰值。

## 7. Shared Memory 优化

### 7.1 Tile：用一次 DRAM 读取换多次片上复用

矩阵乘法中，一个输入 Tile 会被多个线程重复使用。朴素实现从全局内存反复加载；Tile 实现则：合并读取 A、B Tile 到 Shared Memory → 块内同步 → 多次复用 Tile 计算 → 加载下一个 Tile。

Tile 过小，复用不足；Tile 过大，Shared Memory 与 Register 压力会降低 Occupancy。最佳值需按架构、dtype、形状与 Kernel 流水扫参。

### 7.2 Bank Conflict

现代 NVIDIA GPU 的 Shared Memory 通常组织为 32 个 Bank，相邻 32-bit word 映射到相邻 Bank。一个 Warp 同时访问不同 Bank 时可并行；多个 lane 访问同一 Bank 的不同地址时会被拆成多次请求。多个 lane 读取完全相同地址可以广播，不按普通冲突处理。

二维 Tile 转置的经典问题：

```cuda
__shared__ float tile[32][32];
```

按列访问时，相邻线程地址相差 32 个 `float`，Bank 索引取模后可能都落到同一 Bank。增加一列 padding：

```cuda
__shared__ float tile[32][33];
```

步长从 32 变为 33，Bank 映射错开，通常可消除这种 32-way 冲突。Padding 会增加 Shared Memory 占用；Tile 很多或流水级很多时，要重新检查 Occupancy。

### 7.3 同步成本

Shared Memory 是显式协作空间，数据依赖必须正确同步：只在单 Warp 内交换时某些场景可用 `__syncwarp()`；跨 Warp 读写通常需要 `__syncthreads()` 或更精确的同步原语；所有需要到达 Block Barrier 的线程都必须遵守控制流要求；少一次必要同步会错误，多一次不必要同步会阻塞并行。

## 8. 缓存、预取与异步搬运

### 8.1 L1/L2：先测工作集，再谈命中

缓存受以下因素影响：工作集相对缓存容量；时间与空间局部性；多个 Block 或 Kernel 的竞争；数据是否只使用一次；访问是否跨越大量缓存线；L2 persistence 等高级策略是否适用。

若数据只流式读取一次，追求高 L2 命中率没有意义；此时更重要的是合并、并发与减少总字节数。

### 8.2 Ampere：异步 global→shared

Ampere（RTX 3080/3090、A100）引入可直接把数据从 Global Memory 异步搬到 Shared Memory 的能力。相比「load 到寄存器再 store 到 Shared」，它减少中间寄存器使用，并帮助构建 copy/compute 流水。Ada（4090、L40/L40S）沿用相关异步拷贝能力，但产品资源、缓存与最佳流水深度需要单独测量。

### 8.3 Hopper：TMA

Hopper（H100/H200）的 TMA 能描述多维张量搬运，减少参与地址计算和数据移动的线程开销，并支持 Warp-specialized producer/consumer 流水。TMA 是硬件能力；在 RTX 3090 或 4090 上用普通 `memcpy` 模拟流水，只能验证算法结构，不能声称验证了 TMA 性能。

### 8.4 Blackwell：分数据中心与消费级

B100/B200/GB200 与 RTX 5090 都属于 Blackwell，但 Compute Capability、Shared Memory 资源和部分专用目标不同。B200 专项 TMA/Cluster Kernel 不能假设在 RTX 5090 上原样可用，必须编译不同目标并提供通用 CUDA 回退。

## 9. PyTorch 内存管理

### 9.1 allocated、reserved 与 nvidia-smi

PyTorch CUDA caching allocator 会保留已释放的显存块，以降低频繁调用底层分配器的成本。

- `torch.cuda.memory_allocated()`：当前存活 Tensor 占用的显存。
- `torch.cuda.memory_reserved()`：分配器从 CUDA 保留的显存池。
- `nvidia-smi`：进程视角的设备占用，还可能包含 CUDA Context、库 Workspace 与非 PyTorch 分配。

因此常见关系是：

$$
\text{allocated} \le \text{reserved} \le \text{process memory seen by nvidia-smi}
$$

三者口径不同，不应要求完全相等。

### 9.2 `empty_cache()` 的真实作用

`torch.cuda.empty_cache()` 只把缓存分配器中空闲的块归还给驱动，不会释放仍被引用的 Tensor，也不能修复真正的显存泄漏。频繁调用会带来额外开销，正确做法是先用 `memory_summary()` 与快照定位增长点。

### 9.3 碎片与 OOM

OOM 的常见形态是「总量够、连续块不够」。定位方法：记录按阶段的 allocated/reserved 峰值；用 `torch.cuda.memory_snapshot()` 观察块大小分布；检查是否有张量生命周期过长、动态 shape 反复分配、或者请求长度差异极大导致 KV Cache 频繁扩容。

## 10. 实验：三个指标怎么测

```python
import torch

def bandwidth(numel=1 << 24, dtype=torch.float32, iters=50):
    a = torch.randn(numel, device="cuda", dtype=dtype)
    b = torch.randn(numel, device="cuda", dtype=dtype)
    c = torch.empty_like(a)
    for _ in range(5):
        torch.add(a, b, out=c)
    torch.cuda.synchronize()
    s = torch.cuda.Event(True); e = torch.cuda.Event(True)
    s.record()
    for _ in range(iters):
        torch.add(a, b, out=c)
    e.record(); torch.cuda.synchronize()
    ms = s.elapsed_time(e) / iters
    bytes_moved = numel * a.element_size() * 3  # 2读1写
    return ms, bytes_moved / (ms / 1000) / 1e9


def strided_penalty(n=32, stride=32, iters=200):
    base = torch.randn(n * stride * iters, device="cuda")
    out = torch.empty(n * iters, device="cuda")
    for _ in range(5):
        out.copy_(base[::stride][: n * iters])
    torch.cuda.synchronize()
    s = torch.cuda.Event(True); e = torch.cuda.Event(True)
    s.record()
    for i in range(iters):
        out[i * n:(i + 1) * n].copy_(base[i * n * stride:(i + 1) * n * stride:stride])
    e.record(); torch.cuda.synchronize()
    return s.elapsed_time(e) / iters


if __name__ == "__main__":
    ms, gbs = bandwidth()
    print(f"vector add: {ms:.3f} ms, effective {gbs:.1f} GB/s")
    print(f"strided copy: {strided_penalty():.4f} ms/elem-group")
    free, total = torch.cuda.mem_get_info()
    print(f"allocated={torch.cuda.memory_allocated()/2**20:.1f} MiB "
          f"reserved={torch.cuda.memory_reserved()/2**20:.1f} MiB "
          f"free={free/2**30:.2f} GiB total={total/2**30:.2f} GiB")
```

把有效带宽与本机规格（如 H100 SXM 3.35 TB/s、A100 1.55 TB/s）对比，能立刻判断这个 Kernel 是带宽受限还是还有余量；再把 stride 参数从 1 调到 32，就能看到事务效率下降的直接效果。

## 写在最后

Memory 体系优化的本质是四个问题分开看：容量够不够、带宽够不够、延迟能不能隐藏、流量有没有浪费。下一篇进入 Tensor Core 与低精度计算，讨论「算得更便宜」这条路。

下一篇：[Tensor Core 与低精度计算优化](/source/AI-Infra/2-AI系统性能工程/07-TensorCore与低精度计算优化)。
