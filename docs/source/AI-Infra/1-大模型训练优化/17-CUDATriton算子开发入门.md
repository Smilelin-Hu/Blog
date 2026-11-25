# CUDA Triton 算子开发入门

手写 CUDA 内核能带来极致的性能，但开发门槛极高——需要管理线程层级、共享内存、内存合并访问、bank conflict……每一个细节都直接影响性能。而 Triton 提供了一种**基于 Python 的 DSL（领域特定语言）**，用接近 Python 的语法写出高性能的 GPU 内核。

## 1. CUDA 编程基础：Grid、Block、Warp、Shared Memory

### 1.1 为什么需要理解 CUDA

在写代码之前，先理解一个根本问题：**GPU 是如何执行并行计算的？**

CPU 的设计目标是**低延迟**——快速执行单条指令；GPU 的设计目标是**高吞吐**——同时执行成千上万个线程。为了实现高吞吐，GPU 把更多晶体管用于数据处理而非缓存和控制。

CUDA（Compute Unified Device Architecture）是 NVIDIA 推出的通用并行计算平台和编程模型。理解 CUDA 的线程层级结构，是理解一切 GPU 编程（包括 Triton）的基础。

### 1.2 线程层级：Thread → Block → Grid

CUDA 的线程组织方式是一个**三层金字塔**。

**第一层：Thread（线程）**。线程是最小的执行单元。每个线程执行相同的内核代码，但处理不同的数据——通过 `threadIdx` 内置变量区分。

**第二层：Block（线程块）**。多个线程组成一个 Block，块内线程可以：

- 通过**共享内存（Shared Memory）** 交换数据。
- 通过**屏障同步（`__syncthreads()`）** 协调执行。
- 通过 `blockIdx` 和 `blockDim` 获取自己在网格中的位置。

Block 可以是 1D、2D 或 3D 的，大小在启动内核时指定，通常为 128、256 或 512 个线程。

**第三层：Grid（网格）**。多个 Block 组成一个 Grid，也可以是多维的，大小通过 `gridDim` 获取。

**线程索引的计算**：1D 场景下，每个线程的全局索引为

```cuda
int idx = blockIdx.x * blockDim.x + threadIdx.x;
```

2D 场景下（如图像处理）：

```cuda
int row = blockIdx.y * blockDim.y + threadIdx.y;
int col = blockIdx.x * blockDim.x + threadIdx.x;
int idx = row * width + col;
```

这种层级设计使得 CUDA 程序可以**在任意规模的 GPU 上运行**——Block 内的线程数决定单个 SM 上的并行度，Grid 的大小决定整体并行规模。

### 1.3 Warp：GPU 调度的最小单位

**Warp** 是 CUDA 执行模型中一个至关重要的概念：一个 Warp 包含 **32 个线程**，这 32 个线程在同一个 SM 上**以 SIMT（单指令多线程）方式同时执行相同的指令**。

**关键特性**：

1. **线程以 32 为一组调度**：Block 中的线程按 x、y、z 维度线性化后，每 32 个一组形成一个 Warp。
2. **所有线程执行相同指令**：同一 Warp 内所有线程在每个时刻执行相同指令，只是处理的数据不同。
3. **Warp Divergence（线程束分化）**：如果 Warp 中的线程进入不同分支（如 if-else），这些分支会被**串行执行**，严重降低性能。
4. **内存访问按 Warp 发出**：所有全局内存的加载/存储请求都是按 Warp 发出的。

**实战意义**：

- Block 大小应设为 **32 的倍数**，否则最后一个 Warp 中会有空闲线程。
- 尽量避免 Warp 内的分支分化。
- 设计内存访问模式时，让同一 Warp 的 32 个线程访问**连续的内存地址**——这就是「合并访问（Coalesced Access）」。

### 1.4 内存层级：从全局内存到共享内存

CUDA 程序可以访问多种内存空间，按「慢而大」到「快而小」排列：

| 内存类型 | 位置 | 延迟 | 可见范围 |
|---|---|---|---|
| 全局内存（HBM） | 片外 | 高（数百 cycle） | 所有线程 |
| L2 缓存 | 片上 | 中 | 所有 SM |
| 共享内存（Shared Memory） | 片上 SRAM | 低（约 20–30 cycle） | 同一 Block |
| 寄存器 | 片上 | 最低 | 单线程 |

**全局内存（HBM）** 是 GPU 最主要的显存，容量大但访问延迟高，所有线程都可读写。**共享内存（Shared Memory）** 是片上高速缓存，由同一 Block 内的所有线程共享，访问速度远快于全局内存，是实现高性能算子的关键——把频繁访问的数据从全局内存加载到共享内存，然后反复使用。

**合并访问（Coalesced Access）**：当一个 Warp 中的 32 个线程访问全局内存时，如果地址是**连续的**，硬件可以把多次访问合并为**一次**内存事务；如果地址分散，则需要多次事务，带宽利用率大幅下降。实战中合并访问可以使全局内存带宽利用率达到 **100%**，而非合并访问可能降至 **50% 甚至更低**。

### 1.5 一个简单的 CUDA 内核示例

```cuda
// 内核函数：将两个向量相加
__global__ void vector_add(float *a, float *b, float *c, int n) {
    // 计算当前线程的全局索引
    int idx = blockIdx.x * blockDim.x + threadIdx.x;

    // 边界检查
    if (idx < n) {
        c[idx] = a[idx] + b[idx];
    }
}

// Host端调用
int main() {
    int n = 1000000;
    int threads_per_block = 256;
    int blocks = (n + threads_per_block - 1) / threads_per_block;

    vector_add<<<blocks, threads_per_block>>>(d_a, d_b, d_c, n);
}
```

**关键要素**：

- `__global__`：声明这是一个内核函数，在 GPU 上执行、从 CPU 调用。
- `blockIdx.x`、`blockDim.x`、`threadIdx.x`：计算线程在 Grid 中的位置。
- `<<<blocks, threads_per_block>>>`：内核启动配置，指定 Grid 和 Block 的大小。

这个简单的示例展示了 CUDA 编程的核心模式：**把问题分解为大量并行任务，每个线程处理一小部分**。

## 2. 使用 Triton 开发高性能算子的实践

手写 CUDA C++ 虽然性能极致，但开发效率低、调试困难、维护成本高。**Triton** 的出现改变了这一局面。

### 2.1 Triton 是什么

Triton 是 OpenAI 开发的开源 Python DSL，专门用于编写 GPU 上的深度学习内核。核心设计理念：

- **基于 Python**：用接近 Python 的语法编写内核，无需深入 CUDA C++ 的底层细节。
- **分块计算（Tiled Computation）**：把数据和计算任务划分为小块（Block），这是实现高性能的关键抽象。
- **基于 MLIR 的编译器**：自动生成优化的 PTX 代码，即使没有 CUDA 经验也能写出高效内核。
- **与 PyTorch 无缝集成**：Triton 内核可以像 PyTorch 算子一样调用。

Triton 的定位是**降低高性能算子开发的门槛**，在「Python 的便利性」和「CUDA 的性能」之间取得平衡，而不是替代 CUDA C++。

### 2.2 核心抽象：程序（Program）与块（Block）

在 Triton 中，一个内核由**多个程序实例（Program Instance）** 并行执行，每个程序实例处理一个**数据块（Block）**。这与 CUDA 的「Grid of Blocks」概念相似，但 Triton 封装了复杂性：

- 不需要手动管理 `blockIdx`、`threadIdx`。
- 只需用 `tl.program_id(axis)` 获取当前程序的 ID。
- 只需指定每个块的大小（`BLOCK_SIZE`）。

```python
import triton
import triton.language as tl

@triton.jit
def my_kernel(
    output_ptr, input_ptr,
    n_elements,
    BLOCK_SIZE: tl.constexpr,
):
    # 获取当前程序的ID
    pid = tl.program_id(0)

    # 计算当前程序负责的数据范围
    block_start = pid * BLOCK_SIZE
    offsets = block_start + tl.arange(0, BLOCK_SIZE)

    # 加载数据（带掩码防止越界）
    mask = offsets < n_elements
    x = tl.load(input_ptr + offsets, mask=mask)

    # ... 计算 ...

    # 写回结果
    tl.store(output_ptr + offsets, y, mask=mask)
```

### 2.3 实战一：Fused Softmax

Softmax 是一个典型的**访存密集型（Memory-Bound）** 操作。在 PyTorch 中，naive 实现需要**读取 $5MN + 2M$ 个元素、写入 $3MN + 2M$ 个元素**——大量中间结果读写导致性能低下。Triton 的 Fused Softmax 把整个过程**融合为单个内核**，每个程序实例处理输入矩阵的一行或多行：

```python
@triton.jit
def softmax_kernel(
    output_ptr, input_ptr,
    input_row_stride, output_row_stride,
    n_rows, n_cols,
    BLOCK_SIZE: tl.constexpr,
):
    # 当前程序处理的起始行
    row_start = tl.program_id(0)
    row_step = tl.num_programs(0)

    for row_idx in tl.range(row_start, n_rows, row_step):
        # 计算当前行的指针
        row_start_ptr = input_ptr + row_idx * input_row_stride

        # 加载整行数据到SRAM
        offsets = tl.arange(0, BLOCK_SIZE)
        mask = offsets < n_cols
        row = tl.load(row_start_ptr + offsets, mask=mask, other=-float('inf'))

        # 数值稳定：减去最大值
        row_max = tl.max(row, axis=0)
        row = row - row_max

        # 计算exp和sum
        numerator = tl.exp(row)
        denominator = tl.sum(numerator, axis=0)

        # 写回结果
        output_row_ptr = output_ptr + row_idx * output_row_stride
        tl.store(output_row_ptr + offsets, numerator / denominator, mask=mask)
```

**关键优化点**：整行数据一次加载到 SRAM，避免多次 HBM 读写；在 SRAM 中完成 max、exp、sum、除法所有操作。相比 naive PyTorch 实现可达到 **4 倍加速**。

### 2.4 实战二：矩阵乘法

矩阵乘法是深度学习的基础算子。Triton 的矩阵乘法教程展示了如何用**块级算法**实现接近 cuBLAS 的性能。

**核心算法**：每个 Triton 程序计算输出矩阵 C 的一个 `[BLOCK_SIZE_M, BLOCK_SIZE_N]` 块；内循环中从 A 和 B 加载对应的块到 SRAM，累加部分结果。

**多维指针算术**：Triton 需要计算每个块在 A 和 B 中的内存位置。

```python
# 初始化指针
a_block_ptr = tl.make_block_ptr(
    base=a_ptr, shape=(M, K), strides=(stride_am, stride_ak),
    offsets=(m, k), block_shape=(BLOCK_SIZE_M, BLOCK_SIZE_K),
    order=(1, 0)
)
```

**L2 缓存优化**：Triton 教程还展示了如何通过**程序重排序**提高 L2 缓存命中率——把输出块按组（Group）组织，而非简单的行主序，以减少从全局内存加载的次数。在 A100 上这种优化可带来**超过 10% 的性能提升**（从 220 TFLOPS 到 245 TFLOPS）。

### 2.5 实战三：LayerNorm

LayerNorm 是 Transformer 中的关键算子，Triton 教程展示了如何处理**更复杂的反向传播**。

**前向传播**：计算均值和方差，然后归一化并应用权重和偏置。

**反向传播的挑战**：同一批次的所有行共享相同的权重 $w$ 和偏置 $b$，它们的梯度需要**累加**。Triton 使用**并行归约策略**：每个内核实例把部分梯度累积到独立的缓冲区中。这个例子展示了 Triton 处理**复杂数据依赖**的能力，而不仅是简单的逐元素操作。

### 2.6 Triton 与 CUDA 的对比

| 维度 | CUDA C++ | Triton |
|---|---|---|
| 抽象层级 | 线程级（thread） | 块级（block/program） |
| 开发效率 | 低 | 高 |
| 性能上限 | 最高（可手调 PTX/SASS） | 接近 CUDA，少数场景略低 |
| 内存管理 | 手动（共享内存、bank conflict） | 编译器自动 |
| 调试 | Nsight 系列 | 依赖编译产物与 profiler |
| 适用场景 | 极致优化、特殊硬件指令 | 访存密集融合、自定义算子 |

## 3. 从 Python 到 CUDA Kernel 的性能优化路径

对 AI Infra 工程师来说，算子开发通常不是「非此即彼」的选择，而是一条**渐进式的优化路径**。

### 3.1 五层优化路径

1. **PyTorch 原生实现**：起点，先用高层 API 实现功能、验证正确性。适用快速原型与对性能不敏感的部分。
2. **`torch.compile`**：自动捕获计算图并生成优化代码，**零代码改动**。
3. **Triton 内核**：当 `torch.compile` 优化不够时，用 Triton 手写融合内核，接近 CUDA 的性能但开发效率高得多。适用自定义算子、访存密集型融合、需要精细控制内存访问的模式。
4. **CUDA C++ 内核**：需要利用特定硬件特性（如 Hopper 的 TMA）、追求极致性能调优、或需与现有 CUDA 库集成时使用。
5. **汇编级优化（PTX/SASS）**：极少使用，只在需要对编译器产物做手工调优时。

### 3.2 如何选择优化路径

![算子开发分层决策：PyTorch→compile→Triton→CUDA](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y1_l17_01.png)

### 3.3 从 Triton 到 CUDA 的进阶路径

已经掌握 Triton 之后想进一步深入 CUDA，建议按以下顺序：

1. **理解线程模型**：Thread/Block/Grid 三层结构、Warp 的 32 线程调度、`blockIdx`/`threadIdx`/`blockDim`/`gridDim` 的作用。
2. **理解内存层次**：全局内存、共享内存、寄存器、L1/L2 缓存；合并访问；共享内存的 bank conflict。
3. **从简单内核开始**：向量加法 → 矩阵乘法 → 归约 → Softmax，每一步对比 Triton 实现与 CUDA 实现，理解差异。
4. **性能调优**：用 `nvprof` 或 Nsight Compute 分析瓶颈；优化 occupancy（每个 SM 上活跃的 Warp 数量）；减少寄存器压力。

### 3.4 学习资源

**CUDA**：

- NVIDIA 官方《CUDA C++ Programming Guide》。
- NVIDIA Developer Blog 上的性能优化文章。
- 《Professional CUDA C Programming》。

**Triton**：

- Triton 官方教程（矩阵乘法、Fused Softmax、LayerNorm）。
- Triton 中文文档（hub.baai.ac.cn）。

## 写在最后

下一篇：[高效数据加载与预处理](/source/AI-Infra/1-大模型训练优化/18-高效数据加载与预处理)。
