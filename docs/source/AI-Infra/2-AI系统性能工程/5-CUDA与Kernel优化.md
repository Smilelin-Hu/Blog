# CUDA 与 Kernel 优化

系统层的收益见顶之后，剩下的常常在单条 Kernel 里：访存是否合并、中间张量是否白搬一趟、Launch 是否碎成几百次。这一篇从编程模型讲到融合与 Triton。

## 1. CUDA 编程模型

```text
Grid
└── Thread Block（共享内存协作 / 块级同步）
    └── Warp（32 线程，硬件调度单位）
        └── Thread（同一 Kernel 的逻辑实例）
```

```cpp
int idx = blockIdx.x * blockDim.x + threadIdx.x;

int row = blockIdx.y * blockDim.y + threadIdx.y;
int col = blockIdx.x * blockDim.x + threadIdx.x;
```

三个工程要点：

- **块内可用 `__syncthreads()` 做同步**，块间没有便宜的全同步——跨块归约要么两阶段 Kernel，要么 grid sync，要么换算法；
- **寄存器与共享内存是硬预算**，用多了块就驻留不进来；
- **线程不是核**：线程是程序状态，执行资源是有限的管线，靠 Warp 切换隐藏延迟。

## 2. 访存优化

Kernel 性能的第一杀手不是算力，是访存：

- **合并访问**：同一 Warp 访问连续地址，128 字节可被少量事务覆盖；跨步访问请求字节不变、搬运字节翻倍；
- **向量化**：能用 `float4` 就不要四次 `float`，减少事务数与指令数；
- **共享内存 tiling**：把复用数据搬到片上，减少对 HBM 的重复访问；注意 bank conflict；
- **寄存器压力**：局部数组被 spill 到 local memory，等于把寄存器问题变成访存问题；
- **读多写少的场景优先复用**：一次加载、多次使用，把算术强度抬上去。

判断依据始终是 Roofline：

$$
AI = \frac{\mathrm{FLOPs}}{\mathrm{Bytes}_{DRAM}},\qquad
P \le \min\left(P_{peak},\ AI \times BW_{memory}\right)
$$

贴着 Memory Roof：减少流量、改善访问模式、提高复用；贴着 Compute Roof：关注 Tensor Core、指令吞吐、流水线与精度。

## 3. 性能分析：六步法与工具分工

### 3.1 六步

1. **定义目标**：是要吞吐、TTFT、还是 P99？
2. **固定实验条件**：硬件、版本、batch、序列长度、随机种子；
3. **先建端到端基线**：没有基线的「优化」不可证伪；
4. **从系统时间线下钻**：先看 CPU/GPU/通信的整体形态，再进 Kernel；
5. **形成可证伪假设**：「访存未合并导致有效带宽只有 40%」，而不是「感觉慢」；
6. **一次只改一个主要变量**。

### 3.2 关键路径而不是简单相加

$$
T_{step} = T_{input} + T_{cpu} + T_{h2d} + T_{kernel} + T_{comm} + T_{sync} + T_{io}
$$

只在没有重叠时成立。真正决定端到端的是依赖图上的关键路径：

$$
T_{step} = \max_{p \in Paths} \sum_{i \in p} T_i
$$

两个反直觉结论：一个 5 ms 的 Memcpy 若完全藏在 20 ms Kernel 后面，优化它不缩短 Step；一个 1 ms 的同步点若卡住所有后续工作，它比 5 ms 的非关键任务更值得动手。

### 3.3 工具各管一段

| 工具 | 主要回答 | 不要误用为 |
|---|---|---|
| 应用日志 / 压测器 | SLO、Goodput、业务吞吐 | Kernel 根因分析 |
| `nvidia-smi` | 温度、功耗、显存、粗粒度活动 | MFU、精确利用率 |
| DCGM | 集群长期遥测、健康与作业统计 | 指令级分析 |
| CUDA Event | 某 Stream 上 GPU 侧耗时 | 端到端 Host 延迟 |
| `torch.utils.benchmark` | 有预热与同步的微基准 | 分布式时间线 |
| NVTX | 给时间线加业务语义 | 自动给答案 |
| Nsight Systems | CPU/GPU/通信的端到端时间线 | 单 Kernel 计数器深挖 |
| Nsight Compute | 单 Kernel 硬件计数器 | 长任务全量追踪 |
| Compute Sanitizer | 越界、竞态、未初始化 | 性能测量 |

`nvidia-smi` 的 GPU-Util 是采样型「引擎是否忙」，它回答不了「SM 是否在等内存」「Tensor Core 用没用」「这些运算是否有效」。

### 3.4 有效带宽与 Occupancy

$$
BW_{effective} = \frac{B_{useful}}{t}
$$

对 FP32 的 `out = x + y * z`，至少读 x/y/z、写 out：

$$
B_{useful} = N \times (3+1) \times 4\ \text{bytes}
$$

基线若先产生临时张量再相加，会多一次写与一次读——这正是融合的收益来源。

Occupancy 是「可驻留 Warp 比例」，不是「算力利用率」。低 Occupancy 可能是瓶颈，但高 Occupancy 不保证更快：指令级并行可能已足够；更多 Block 可能压寄存器导致 spill；更多 Warp 可能是去抢 Cache、共享内存与带宽；尾效应也会让平均 Occupancy 看起来偏低。

## 4. Kernel Fusion

### 4.1 中间张量是一张昂贵的交接单

```text
tmp1 = x * y
tmp2 = tmp1 + bias
out  = relu(tmp2)
```

数学上只是 \(\max(x_iy_i + bias, 0)\)，Eager 下却可能是三个 Kernel：每个 `tmp` 都完整走一次 Store 与后续 Load。融合后每个线程把中间值留在寄存器，只写一次 `out`。

### 4.2 两类收益

**减少 Launch**：

$$
\Delta T_{launch} \approx (K - F)\,t_{launch}
$$

对大 GEMM，Launch 几乎可忽略；对几百个只有几微秒的 Pointwise，它可能成为主瓶颈。

**减少 Global Memory 往返**（FP32 的 `relu(x*y+bias)`）：

| 阶段 | 读 | 写 | 每元素流量 |
|---|---|---|---|
| Multiply | x,y：8 B | tmp1：4 B | 12 B |
| Bias Add | tmp1：4 B | tmp2：4 B | 8 B |
| ReLU | tmp2：4 B | out：4 B | 8 B |
| 未融合合计 |  |  | 28 B |
| 融合 Kernel | x,y：8 B | out：4 B | 12 B |

$$
R_{traffic} = \frac{28}{12} \approx 2.33
$$

注意：这是**理想流量缩减比**，不是必然加速 2.33 倍——Cache 会吸收一部分中间流量，Kernel 还可能被 Launch、寄存器、Occupancy 限制。

### 4.3 综合模型与判断

$$
T \approx N_{launch}t_{launch} + \max\left(\frac{Bytes}{BW_{eff}},\ \frac{FLOPs}{P_{eff}}\right) + T_{sync} + T_{other}
$$

融合只改变三个量：\(N_{launch}\) 变小、\(Bytes\) 变小、\(P_{eff}\) 可能升也可能因寄存器压力下降。所以判断标准不是「能不能合」，而是「合完之后这三项整体是否变好」。

### 4.4 五类融合

| 类型 | 形态 | 收益 |
|---|---|---|
| Vertical（上下游） | Bias→Activation→Dropout、GEMM→Bias→Act | 消除中间 Tensor，适合 Pointwise 链 |
| Horizontal（同类小任务） | 多个参数的 Adam 更新 → 一个 Multi-Tensor Kernel | 主要减少 Launch，并提高小 Tensor 并行度 |
| Epilogue | \(D = \mathrm{Activation}(\alpha AB + \beta C + bias)\) | 直接消费 Accumulator，不落 HBM |
| Reduction | 统计量与归一化、Loss 与归约、Softmax 各阶段 | 省流量，但需要跨线程归约与数值稳定 |
| Algorithmic | FlashAttention：Tiling + Online Softmax | 改变 I/O 复杂度与数据流 |

Epilogue 的实践建议：优先用 cuBLASLt / CUTLASS 提供的 Epilogue 能力，**不要为了「自定义」重写 GEMM Mainloop**。

跨 Block 的 Global Reduction 未必适合硬塞进一个普通 Kernel；Persistent Kernel 与 Megakernel 能减少 Launch 与全局同步，但调度、负载均衡、寄存器/共享内存、死锁与可维护性都会变复杂。

### 4.5 适合与不适合

**适合**：规则的 Pointwise 链、GEMM 后处理、多小张量的同类更新、能在一个 Block 内完成的归约、有清晰复用关系的算子。

**不适合**：需要跨 Block 全同步的归约、动态控制流重的算子、融合后寄存器爆表导致 occupancy 崩塌、以及「编译器的融合已经做得很好」的通用算子。

## 5. Triton：用块级抽象写 Kernel

Triton 暴露的是 tile 级语义（`tl.load` / `tl.store` / `tl.dot` / `tl.arange`），线程映射、向量化与流水由编译器负责。适合的场景很明确：融合类算子、Attention 变体、需要快速试错的自定义 Kernel。

```python
@triton.jit
def add_kernel(x_ptr, y_ptr, out_ptr, n, BLOCK: tl.constexpr):
    pid = tl.program_id(0)
    offs = pid * BLOCK + tl.arange(0, BLOCK)
    mask = offs < n
    x = tl.load(x_ptr + offs, mask=mask)
    y = tl.load(y_ptr + offs, mask=mask)
    tl.store(out_ptr + offs, x + y, mask=mask)
```

工程要点：

- **`autotune` 是主要调参手段**：BLOCK 大小、`num_warps`、`num_stages` 直接决定占用与流水深度；
- **先跑通再调优**：`num_stages` 太大在部分硬件上会撑爆共享内存；
- **对照 cuBLAS 与 torch 实现**：Triton 的优势在融合与定制，不在替代成熟 GEMM；
- **迁移到 NPU 时先降 Block**：UB 容量比共享内存小得多（一期迁移五坑里已有记录）。

## 写在最后

Kernel 层的三板斧是：让访存合并、让中间结果不落 HBM、让 Launch 别碎。下一篇把这些放回分布式语境：并行体系、NCCL 深优、通信优化与 FSDP——单卡再快，同步点也能把收益吃回去。
