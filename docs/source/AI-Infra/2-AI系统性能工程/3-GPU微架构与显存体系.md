# GPU 微架构、显存体系与低精度

系统层的「慢」最终要落到硬件语言：Warp 怎么调度、访存怎么合并、Occupancy 被什么卡住、Tensor Core 在什么条件下才快。这一篇把这些条件讲清楚。

## 1. 第一性原理：延迟隐藏

一个 Warp 访问 HBM 要等很久。GPU 的办法不是把这次访问变得像寄存器一样快，而是**在当前 Warp 等待时，立刻发射另一个就绪的 Warp**：

```text
Warp A 发起访存 ───────── 等待数据 ── 继续计算
Warp B         计算 ── 访存等待 ─────── 继续
Warp C                计算 ── 计算 ── 访存
时间 ───────────────────────────────────────▶
```

延迟隐藏成立要三个条件：

1. 有足够多的就绪 Warp；
2. 指令之间没有过长依赖链；
3. 数据布局没有制造严重的额外内存事务。

所以问题不是「线程越多越好吗」，而是「有没有足够就绪的工作去填满执行管线」。

## 2. 从软件层级到硬件层级

### 2.1 CUDA 的四层结构

```text
Grid
└── Thread Block
    └── Warp（NVIDIA 固定 32 线程）
        └── Thread
```

- **Grid**：一次 launch 的全部线程块；
- **Thread Block**：能在共享内存协作、能做块级同步的一组线程；
- **Warp**：硬件调度与发射的基本单位；
- **Thread**：执行同一 Kernel 的逻辑线程。

线程块被分配到 SM 上，块内线程、寄存器与共享内存都驻留在同一 SM——普通 CUDA 模型不会把一个块拆到多个 SM。

### 2.2 物理层级

```text
GPU
├── GPC / 更高层处理分区
│   ├── SM
│   │   ├── Warp Scheduler / Dispatch
│   │   ├── 标量与浮点管线
│   │   ├── Tensor Core
│   │   ├── Load/Store 与特殊函数单元
│   │   ├── Register File
│   │   └── Shared Memory / L1
│   └── SM ...
├── 共享 L2
├── Memory Controller
└── GDDR / HBM
```

不要把 Thread 机械对应成「一个 CUDA Core」：线程是程序状态，Core 是执行资源，大量线程的指令在时间上复用有限管线。

### 2.3 SM 内真正竞争的资源

同一 SM 可驻留多个线程块，它们共同竞争：最大驻留线程/Warp 数、最大驻留块数、Register File、Shared Memory、Warp Scheduler 与执行管线、Load/Store 与缓存带宽。任一项到上限，新块就进不来——**只看 `threads_per_block` 无法判断 Occupancy**。

## 3. SIMT 与分支发散

SIMT 下，一个 Warp 的线程执行同一 Kernel，但各有寄存器状态、索引与控制流。所有线程走同一分支时效率最高；若同 Warp 内按奇偶走不同路径，硬件必须分别执行有效掩码对应的路径再汇合——理想情况下有效线程工作比例可能只有一半。

一个简化的分支效率：

$$
\eta_{branch} = \frac{\text{有效线程指令数}}{\text{发射槽覆盖的线程指令数}}
$$

更要紧的是：**发散不一定来自 `if`**。以下都会造成 Warp 内工作量不均：

- 变长序列让不同 token 的循环次数不同；
- MoE 中各专家收到的 token 数差异过大；
- 稀疏计算每行非零元素数量不同；
- 线程内循环次数由数据决定；
- 尾块只有少量线程处理有效元素。

优化时要问的不是「有没有 `if`」，而是「同一 Warp 的活跃掩码与工作量是否一致」。

## 4. 内存层级与合并访问

| 层级 | 作用域 | 特征 |
|---|---|---|
| Register | 单线程 | 最靠近管线；过多会降低驻留度或 spill |
| Shared Memory / L1 | 单 SM / 单块协作 | 软件可控复用、低延迟、容量有限 |
| L2 | 整个 GPU | SM 共享，产品间容量差异大 |
| GDDR / HBM | 整个 GPU | 容量与带宽大，延迟高 |
| Host Memory | CPU 侧 | 经 PCIe / NVLink-C2C 访问或搬运 |

### 4.1 一个 Warp 的访问会被合并成若干事务

每个线程读 4 字节时：连续 32 个线程读连续地址，128 字节可用少量连续事务覆盖；步长变大，地址散落到更多内存段——**请求字节不变，搬运字节成倍增加**。

以 32 个连续 FP32（128 字节）为例，在 CC 6.0+ 的常见合并模型中通常由 4 个 32 字节事务覆盖；若每个 lane 间隔 32 字节，可能触及 32 个不同段，仍只用 128 字节却搬运 1024 字节，简化效率 12.5%：

$$
\eta_{memory} = \frac{Q_{requested}}{Q_{actual}}
$$

### 4.2 有效带宽与算术强度

$$
BW_{effective} = \frac{R + W}{t}
$$

FP32 向量加 \(C = A + B\) 时 \(R = 2N\times4\)、\(W = N\times4\)，故 \(BW_{effective} = 12N/t\)。它衡量「逻辑字节」，不等于硬件计数器里的真实 DRAM 字节。

算术强度必须指明相对哪一层：

$$
AI = \frac{\mathrm{FLOPs}}{\mathrm{Bytes}_{target\ level}}
$$

对 HBM 复用很高的 Kernel，仍可能被 Shared Memory 带宽或寄存器依赖卡住。

## 5. Occupancy：能驻留多少 Warp

忽略分配粒度，可驻留块数的简化上界：

$$
B_{active} = \min\left(B_{SM},\ \left\lfloor\frac{T_{SM}}{T_b}\right\rfloor,\ \left\lfloor\frac{R_{SM}}{R_t T_b}\right\rfloor,\ \left\lfloor\frac{S_{SM}}{S_b}\right\rfloor\right)
$$

每块 Warp 数 \(W_b = \lceil T_b/32 \rceil\)，于是：

$$
\mathrm{Occupancy} = \frac{\min(B_{active}W_b,\ W_{SM})}{W_{SM}}
$$

真实硬件还有分配粒度与块级上限，手算只用来定位「是寄存器还是共享内存卡住了」，最终以 CUDA Occupancy API、编译器输出与 Nsight Compute 为准。

**Occupancy 不是越高越好**：高 Occupancy 只是提供更多候选 Warp，不保证它们就绪、不保证指令混合能填满目标管线、不保证访存合并、不保证 Tensor Core 与带宽被用满，更不保证算法在做有效工作。

## 6. Host 内存：pageable、pinned 与 unified

普通 pageable 内存可能被换出或移动。Pinned（锁页）内存在物理地址上固定，DMA 可以直接读，是**可靠异步传输的前提**，大块 H2D 通常更快。

但 pinned 是稀缺资源：

- 分配与锁页本身有成本；
- 过量 pin 影响整机；
- 临时 `.pin_memory()` 再立刻拷贝可能比直接 `.to()` 更慢；
- 应该在 DataLoader 或复用缓冲池中预先准备。

Unified Memory 提供统一地址与按需迁移，能简化编程、也能让超出显存的数据跑起来，但页面故障与迁移带来不可预测延迟——它是**容量安全网，不是自动优化**。

## 7. 容量模型与双缓冲

训练：

$$
M_{total} \approx M_{param} + M_{grad} + M_{optimizer} + M_{activation} + M_{workspace} + M_{fragmentation}
$$

推理：

$$
M_{inference} \approx M_{weights} + M_{KV} + M_{workspace} + M_{runtime}
$$

这解释了为什么「权重只有 14 GB」不代表 20 GB 卡一定能训练或承载目标并发。

拷贝与计算：串行近似 \(T_{copy} + T_{compute}\)，双缓冲理想稳态 \(\max(T_{copy}, T_{compute})\)。能否真的重叠取决于 pinned buffer、非阻塞拷贝、不同 Stream 与正确事件依赖、设备是否支持该方向的并发 copy/compute、缓冲区是否被提前覆盖、数据准备是否及时。

## 8. Tensor Core：矩阵块流水线

### 8.1 它的工作方式

标量 FMA 是 \(d = a\times b + c\)；Tensor Core 面向矩阵块执行 MMA：

$$
D = A\times B + C
$$

它不是「一条指令完成任意大小矩阵」。大 GEMM 会被切成层级 Tile：

```text
完整 GEMM
└── Thread Block / Cluster Tile
    └── Warp / Warpgroup Tile
        └── Tensor Core MMA Tile
```

高吞吐来自一组共同条件：Tile 形状与硬件 MMA 形状匹配；数据按要求布局、对齐并及时搬到片上；有足够工作填满 SM；多级流水能隐藏访存延迟；累加器与缩放不成为新瓶颈；输出精度满足模型要求。

### 8.2 它不负责所有算子

容易受益：GEMM/BMM/Linear、卷积的部分实现、Attention 的 QK 与 PV、MoE 的 grouped GEMM、结构化稀疏矩阵乘。

不一定受益：Softmax、LayerNorm/RMSNorm、Sampling/Top-k/Tokenizer、很小的逐元素 Kernel、不规则 Gather/Scatter、CPU 调度与 IO。

Amdahl 提醒：若 GEMM 只占 Step 的 50%，即使 GEMM 加速 4 倍，整体上限也只有

$$
S = \frac{1}{(1-0.5) + 0.5/4} = 1.6
$$

### 8.3 输入、累加、输出可以是不同精度

```text
低精度 A × 低精度 B → 较高精度 Accumulator → 指定输出 dtype
```

FP16/BF16 输入配 FP32 累加器既提高乘法吞吐，又降低长点积累加误差。**不要只看 Tensor 的存储 dtype**——库选择的 MMA 指令与 accumulation mode 才决定计算路径。

## 9. 数值格式：动态范围与精度是两条轴

| 格式 | 构成 | 直觉 | 常见用途 |
|---|---|---|---|
| FP32 | 1 + 8 + 23 | 范围与精度都够 | 主权重、敏感归约 |
| TF32 | 1 + 8 + 10（仅计算） | FP32 范围、接近 FP16 尾数 | Ampere+ 的 FP32 GEMM 加速 |
| BF16 | 1 + 8 + 7 | 范围近 FP32、精度较粗 | 现代训练主力 |
| FP16 | 1 + 5 + 10 | 精度较高、范围小 | 训练/推理通用 |
| FP8 E4M3 | 1 + 4 + 3 | 精度较好、范围小 | 前向与激活 |
| FP8 E5M2 | 1 + 5 + 2 | 范围大、精度低 | 梯度 |
| NVFP4 | 4-bit 值 + 分层 scale | 极低存储与高吞吐 | Blackwell 路线 |
| INT8/INT4 | 整数 + scale/zero point | 规则、便于量化 | 推理量化 |

$$
x = (-1)^s \times (1.m) \times 2^{e - bias}
$$

exponent 决定动态范围，fraction 决定分辨率。所以「BF16 精度低于 FP16」只描述了尾数；BF16 保留 8 位指数，训练中往往更稳，因为**溢出比舍入更致命**。

### 9.1 FP8 需要缩放，而不是 `.to(float8)`

$$
x_{fp8} = \mathrm{cast}_{fp8}(x \cdot s),\qquad \hat{x} = \mathrm{cast}_{high}(x_{fp8}) / s
$$

要决定的事：用历史 Amax 还是当前 Amax；每 Tensor、每通道还是每 Block 一个 scale；scale 多久更新；分布式下 Amax 是否跨 Rank 归约；前向与反向是否用不同格式（E4M3 / E5M2）。Transformer Engine 的职责是管理「配方 + Amax + scale + 量化缓存 + 高性能 Kernel」，不是把所有层一律降到最低精度。

### 9.2 NVFP4 不是普通 INT4

它有浮点值与分层 scale，表示集合、scale 结构、硬件 MMA 路径、校准与精度行为都与对称 INT4 不同。**文件里写「4-bit」不能证明能走 NVFP4 Tensor Core**；没有 Blackwell 与对应软件栈时，可以模拟量化误差，但不能声称验证了 NVFP4 吞吐。

## 10. 混合精度训练的工程要点

- **Autocast 是按算子选择 dtype**，不是全局替换：GEMM 走低精度、归约留在 FP32；
- **GradScaler** 只对 FP16 必要（防下溢），BF16 通常不需要；
- **master weights 用 FP32**，更新也在 FP32 做，否则小更新会被舍入吃掉；
- **loss scaling 与 Amax 都是状态**，要能保存/恢复，否则断点续训会数值突变；
- **精度下降要能测出来**：同一评测集、同一解码参数、可接受的容差。

## 写在最后

单卡硬件边界基本清楚了：延迟靠 Warp 隐藏、带宽靠合并访问换取、算力靠 Tensor Core 但有形状与精度前提。下一篇把视野扩到机箱与集群——NVLink/NVSwitch、RDMA 网络，以及 Linux、容器与 K8s 如何影响 GPU 的实际可用性能。
