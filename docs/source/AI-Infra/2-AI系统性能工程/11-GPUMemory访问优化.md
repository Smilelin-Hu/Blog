# GPU Memory 访问优化

本篇聚焦合并访存、Shared Memory、Bank Conflict 与缓存行为，系统提升 GPU Memory 访问效率。

现代 GPU 的计算能力增长很快，但很多 Kernel 并不是「算不动」，而是「数据送不到」。即使 Global Memory 带宽很高，Warp 中 32 个线程的地址分散、未对齐或跨步过大，也会把一个逻辑 Load 拆成许多 Memory Transaction；Shared Memory 虽然在片上，Bank Conflict 仍可能让访问串行化。

## 1. 内容概览

- 从 Warp 地址集合推导 Transaction 数与传输效率。
- 连续、Misalignment、Stride、Scatter/Gather 的不同代价。
- AoS / SoA / AoSoA 的布局选择。
- `float2/float4` 等 Vectorized Access 的对齐与尾部处理。
- Shared Memory Bank Mapping、Broadcast 与 N-way Conflict。
- Padding 消除矩阵转置的 Bank Conflict。
- `cp.async`、Hopper TMA 与后续演进。

## 2. 核心直觉：硬件处理的是地址集合

许多人把 Coalescing 理解成「相邻线程读相邻地址就快」。这个直觉接近正确，但需要精确两点：

1. 硬件并不知道 C++ 的「行」或 Tensor 的「维度」，只看到一个 Warp 发出的地址集合；
2. 地址集合会被归并为若干对齐的 Memory Segment/Transaction，而不是任何情况下都只有一次物理读取。

对 Compute Capability 6.0+，以 32 个线程各读一个相邻 `float` 为例：请求 128 字节，理想对齐下官方简化模型是 **4 个 32-byte Transaction**，而不是「一个不可再分的 128-byte 操作」。若首地址错开 4 字节，可能覆盖 5 个 Segment；若每个线程跨 32 个 `float`，则可能触及大量不同 Segment。

## 3. Global Memory Transaction 模型

设第 $l$ 个 Lane 的地址为 $a_l$、Segment 大小为 $S$ 字节，则它属于

$$
\mathrm{segment}_l = \left\lfloor \frac{a_l}{S} \right\rfloor
$$

简化 Transaction 数 $N_{txn}$ 为 32 个 Lane 覆盖的不同 Segment 数，请求效率为

$$
\eta_{request} = \frac{\mathrm{Bytes}_{requested}}{N_{txn} \times S}
$$

这个模型非常适合建立直觉，但真实硬件还受 Cache Line、Sector、合并规则、访问宽度、Cache Hit、ECC、Store Policy 与架构影响，最终以 Profiler Counter 为准。

### 3.1 连续访问

```cuda
float value = x[warp_base + lane];
```

32 个 Lane 访问相邻 4-byte Word，请求 128 字节；首地址合理对齐时通常只覆盖必要的 4 个 Segment，请求效率接近 100%。

### 3.2 Misalignment

```cuda
float value = x[warp_base + lane + 1];
```

只偏移一个 `float`，地址范围可能从 4 个 Segment 扩为 5 个，简化效率 $128/(5\times32)=80\%$。Cache 可能让相邻 Warp 复用多取回的数据，所以实测下降不一定正好 20%。

### 3.3 Stride

```cuda
float value = x[(warp_base + lane) * stride];
```

`stride=32` 时相邻 Lane 相隔 128 字节，很可能每个 Lane 触及不同 Segment；虽然每个线程只要 4 字节，硬件可能搬运远多于 128 字节，造成严重 Overfetch。

### 3.4 Permutation 与部分 Warp

如果 Warp 仍只访问相同的少量 Segment，即使 Lane 顺序被打乱，Transaction 数也可能不增加——Coalescing 关注地址覆盖集合，不要求 Lane 0 访问最低地址。

边界 Warp 中只有少量 Lane Active 时，硬件仍按 Segment 搬运，Bandwidth Utilization 下降；Tail 很短时影响有限，但大量不规则小任务会放大该问题。

## 4. Alignment

`cudaMalloc` 返回的基地址满足较高对齐，但以下操作会破坏对齐：对指针加非对齐 Offset；Struct 字段布局与 Padding 不当；从 Byte Buffer 中切出任意地址；Tensor View/Storage Offset；把 `float*` 强制转换为 `float4*` 但地址不是 16 字节对齐。

| 类型 | Payload | 常见自然对齐要求 |
| --- | --- | --- |
| `float` | 4 B | 4 B |
| `float2` | 8 B | 8 B |
| `float4` | 16 B | 16 B |

Vectorized Load 的主要价值常是减少 Load/Store Instruction 数、提高每线程搬运宽度；它不会自动修复跨 Warp 的随机地址，也不保证 DRAM Transaction 更少。

## 5. 数据布局：AoS、SoA 与 AoSoA

**AoS**：

```cuda
struct TokenState {
    float score;
    int token_id;
    float probability;
};
TokenState states[N];
```

若 Kernel 只读取 `score`，相邻线程地址间隔为 `sizeof(TokenState)`，会取回不需要的字段。

**SoA**：

```cuda
float scores[N];
int token_ids[N];
float probabilities[N];
```

只读 `scores` 时 Warp 访问连续，通常更适合合并读取。但 SoA 不是永远更好：若每个线程总是一起读取一个对象的全部字段，紧凑且对齐良好的 AoS/AoSoA 可能更合适。布局选择要依据「Warp 在同一条指令中读哪些字段」。

**AoSoA** 把数据分成 Warp/Tile 大小的块，块内采用 SoA：

```text
Block 0: scores[32], ids[32], probs[32]
Block 1: scores[32], ids[32], probs[32]
```

它常用于兼顾局部性、Vectorization 与对象分块，代价是实现更复杂。

## 6. Shared Memory：片上重排缓冲区

三个核心用途：

1. 把 Global Memory 的分散访问转换为合并访问。
2. 在 Block 内复用数据，减少重复 Global Load。
3. 在片上进行 Transpose、Reduction、Stencil Halo 等数据重排。

典型流程：

![ai2-11-L128](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l11_01.png)

## 7. Shared Memory Bank Conflict

现代 CUDA GPU 的 Shared Memory 通常可抽象为 32 个 Bank。对常见 32-bit Word：

$$
\mathrm{bank} = \left(\frac{\mathrm{address}}{4}\right) \bmod 32
$$

**无冲突**：`shared[lane]` 时 Lane 0–31 映射到 Bank 0–31，可并行服务。

**32-way 冲突**：`shared[lane * 32]` 时所有 Lane 的 Bank Index 都是 0、但地址不同，访问需拆成多个 Conflict-free Request。多个 Lane 读取**完全相同地址**时由 Broadcast 处理，不算普通冲突。

### 7.1 矩阵转置的经典解法

```cuda
__shared__ float tile[32][32];
// 按列访问时相邻线程地址相差 32 个 float，Bank 索引可能全落到同一 Bank

__shared__ float tile[32][33];  // 加一列 padding，步长 33 与 32 互质
```

Padding 把冲突错开，通常可消除 32-way 冲突；代价是多占 Shared Memory，Tile 很大或流水级很多时要重新检查 Occupancy。

## 8. Warp Shuffle 与片上通信

同 Warp 内交换数据不必经 Shared Memory，可以用 `__shfl_sync` 等 intrinsic 完成寄存器级交换，避免一次片上往返与额外的 Barrier：

```cuda
unsigned mask = __activemask();
float from_lane0 = __shfl_sync(mask, value, 0);
float sum_pair = value + __shfl_xor_sync(mask, value, 1);
```

注意必须传入正确的 Active Mask，并保证参与线程集合一致；错误依赖「Warp 自然同步」的代码在 Volta 之后可能出问题。

## 9. 异步搬运：`cp.async` 与 TMA

**Ampere `cp.async`**：把 Global → Shared 的拷贝变成异步指令，减少经过寄存器的中间拷贝，并让搬运与计算形成多级流水（典型双缓冲或多级 pipeline）：

```cuda
// 伪代码示意：发起异步拷贝到共享内存，再提交/等待分组
cp.async.cg.shared.global [dst_smem], [src_gmem], 16;
cp.async.commit_group;
cp.async.wait_group 0;
```

**Hopper TMA**：以「张量描述符」表达 1D–5D 搬运，由专用单元执行，进一步减少地址计算与线程占用，并支持 Warp-specialized 的 producer/consumer 流水。

**Blackwell**：在 TMA 与集群能力上继续演进，但数据中心与消费级 SKU 的目标不同；专项 Kernel 需分别编译并提供回退路径。

## 10. 分析与验证方法

1. **先保证正确**：与参考实现逐元素比对，固定输入规模与种子。
2. **再测带宽**：用 CUDA Event 包裹，重复多轮并 Warmup，计算 `(读+写字节)/时间` 与理论带宽比较。
3. **看事务效率**：Nsight Compute 里关注 Global Load/Store Efficiency、Sector 数、L2 Hit Rate、Shared Memory Bank Conflict 计数。
4. **做单变量对照**：只改 stride、padding、向量宽度、Tile 尺寸中的一项，记录前后数据。
5. **判断瓶颈归属**：若 DRAM 吞吐接近上限而计算管线偏低，继续减少字节；若两者都低，问题可能在依赖、发散或 Launch 开销。

一个最小对照实验的骨架：

```python
import torch

def bandwidth_of(stride, n=1 << 24, iters=50):
    src = torch.randn(n * stride, device="cuda")
    dst = torch.empty(n, device="cuda")
    for _ in range(5):
        dst.copy_(src[::stride][:n])
    torch.cuda.synchronize()
    s, e = torch.cuda.Event(True), torch.cuda.Event(True)
    s.record()
    for _ in range(iters):
        dst.copy_(src[::stride][:n])
    e.record()
    torch.cuda.synchronize()
    ms = s.elapsed_time(e) / iters
    useful = n * 4 * 2
    return ms, useful / (ms / 1000) / 1e9

for stride in (1, 4, 32):
    print(stride, bandwidth_of(stride))
```

stride 从 1 到 32，`useful GB/s`（按请求字节算）会明显下降，而 DRAM 实际搬运量并不会同比减少——这就是 Overfetch 的直接体现。把「按请求字节算的带宽」与「按实际事务算的带宽」分开记录，才能看清真实代价。

## 写在最后

Memory 访问优化的核心是把「数组语义」翻译成「地址集合 + 事务」：先看地址怎么落，再看片上怎么摆，最后才谈指令与流水。下一篇进入性能分析工具：有了模型，还需要证据。

下一篇：[GPU 性能分析方法](/source/AI-Infra/2-AI系统性能工程/12-GPU性能分析方法)。
