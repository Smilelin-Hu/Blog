# CUDA Triton算子开发入门

手写CUDA内核能带来极致的性能，但开发门槛极高——需要管理线程层级、共享内存、内存合并访问、bank conflict……每一个细节都直接影响性能。而Triton则提供了一种**基于Python的DSL（领域特定语言）**，让开发者用接近Python的语法写出高性能的GPU内核。
### 1.1. 为什么需要理解CUDA
在开始写代码之前，我们需要先理解一个根本问题：**GPU是如何执行并行计算的？**
CPU的设计目标是**低延迟**——快速执行单条指令。GPU的设计目标是**高吞吐**——同时执行成千上万个线程。为了实现高吞吐，GPU将更多晶体管用于数据处理而非缓存和控制。
CUDA（Compute Unified Device Architecture）是NVIDIA推出的通用并行计算平台和编程模型。理解CUDA的线程层级结构，是理解一切GPU编程（包括Triton）的基础。
### 1.2. 线程层级：Thread → Block → Grid
CUDA的线程组织方式是一个**三层金字塔**：
**第一层：Thread（线程）**
线程是CUDA中最小的执行单元。每个线程执行相同的内核代码，但处理不同的数据——通过`threadIdx`内置变量来区分。
**第二层：Block（线程块）**
多个线程组成一个Block。Block内的线程可以：
- 通过**共享内存（Shared Memory）** 交换数据
- 通过**屏障同步（**`__syncthreads()`**）** 协调执行
- 通过`blockIdx`和`blockDim`获取自己在网格中的位置
Block可以是1D、2D或3D的。Block的大小在启动内核时指定，通常为128、256或512个线程。
**第三层：Grid（网格）**
多个Block组成一个Grid。Grid也可以是多维的。Grid的大小通过`gridDim`获取。
**线程索引的计算**
在1D场景中，每个线程的全局索引为：
```text
int idx = blockIdx.x * blockDim.x + threadIdx.x;
```
在2D场景中（如图像处理）：
```text
int row = blockIdx.y * blockDim.y + threadIdx.y;
int col = blockIdx.x * blockDim.x + threadIdx.x;
int idx = row * width + col;
```
这种层级设计使得CUDA程序可以**在任意规模的GPU上运行**——Block内的线程数决定了单个SM（流式多处理器）上的并行度，Grid的大小决定了整体并行规模。
### 1.3. Warp：GPU调度的最小单位
**Warp**是CUDA执行模型中一个至关重要的概念。
一个Warp包含**32个线程**，这32个线程在同一个SM上**以SIMT（单指令多线程）方式同时执行相同的指令**。
**关键特性**：
1. **线程以32为一组调度**：Block中的线程按照x、y、z维度的顺序线性化后，每32个一组形成一个Warp。
2. **所有线程执行相同指令**：在一个Warp中，所有线程在每一时刻执行相同的指令——但它们处理的数据不同。
3. **Warp Divergence（线程束分化）**：如果Warp中的线程进入了不同的代码分支（如if-else），这些分支会被**串行执行**——先执行一个分支，再执行另一个。这会严重降低性能。
4. **内存访问按Warp发出**：所有全局内存的加载/存储请求都是按Warp发出的。
**实战意义**：
- Block大小应设置为**32的倍数**，否则最后一个Warp中会有空闲线程
- 尽量避免Warp内的分支分化
- 设计内存访问模式时，要让同一个Warp的32个线程访问**连续的内存地址**——这就是“合并访问（Coalesced Access）”
### 1.4. 内存层级：从全局内存到共享内存
CUDA程序可以访问多种内存空间，从“慢而大”到“快而小”排列如下：
> [内嵌电子表格，分享态无法直接读取内容]
**全局内存（HBM）** 是GPU最主要的显存，容量大但访问延迟高。所有线程都可以读写全局内存。
**共享内存（Shared Memory）** 是片上高速缓存，由同一Block内的所有线程共享。它的访问速度远快于全局内存，是实现高性能算子的关键——将频繁访问的数据从全局内存加载到共享内存，然后反复使用。
**合并访问（Coalesced Access）**
当一个Warp中的32个线程访问全局内存时，如果它们访问的地址是**连续的**，硬件可以将多次访问合并为**一次**内存事务。如果地址是分散的，则需要多次事务，带宽利用率大幅下降。
实战中，合并访问可以使全局内存带宽利用率达到**100%**；而非合并访问可能降至**50%甚至更低**。
### 1.5. 一个简单的CUDA内核示例
以下是一个向量加法的CUDA内核：
```text
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
- `global`：声明这是一个内核函数，在GPU上执行、从CPU调用
- `blockIdx.x`、`blockDim.x`、`threadIdx.x`：计算线程在Grid中的位置
- `<<<blocks, threads_per_block>>>`：内核启动配置，指定Grid和Block的大小
这个简单的示例展示了CUDA编程的核心模式：**将问题分解为大量并行任务，每个线程处理一小部分**。
## 2. 使用Triton开发高性能算子的实践
手写CUDA C++虽然性能极致，但开发效率低、调试困难、维护成本高。**Triton**的出现改变了这一局面。
### 2.1. Triton是什么
Triton是OpenAI开发的开源Python DSL（领域特定语言），专门用于编写GPU上的深度学习内核。
**核心设计理念**：
- **基于Python**：用接近Python的语法编写内核，无需深入CUDA C++的底层细节
- **分块计算（Tiled Computation）**：将数据和计算任务划分为小块（Block），这是实现高性能的关键抽象
- **基于MLIR的编译器**：自动生成优化的PTX代码，即使没有CUDA经验也能写出高效内核
- **与PyTorch无缝集成**：Triton内核可以像PyTorch算子一样调用
**Triton的定位**：它不替代CUDA C++，而是**降低了高性能算子开发的门槛**——让在“Python的便利性”和“CUDA的性能”之间取得平衡。
### 2.2. Triton的核心抽象：程序（Program）与块（Block）
在Triton中，一个内核由**多个程序实例（Program Instance）** 并行执行，每个程序实例处理一个**数据块（Block）**。
这与CUDA的“Grid of Blocks”概念相似，但Triton将复杂性封装了起来：
- 不需要手动管理`blockIdx`、`threadIdx`
- 只需要用`tl.program_id(axis)`获取当前程序的ID
- 只需要指定每个块的大小（`BLOCK_SIZE`）
**一个Triton内核的典型结构**：
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
### 2.3. 实战一：Fused Softmax
Softmax是一个典型的**访存密集型（Memory-Bound）** 操作。在PyTorch中，naive实现需要**读取5MN + 2M个元素，写入3MN + 2M个元素**——大量的中间结果读写导致性能低下。
Triton的Fused Softmax将整个过程**融合为单个内核**，每个程序实例处理输入矩阵的一行或多行：
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
**关键优化点**：
- 整行数据一次加载到SRAM，**避免多次HBM读写**
- 在SRAM中完成max、exp、sum、除法所有操作
- 相比naive PyTorch实现，可达到**4倍加速**
### 2.4. 实战二：矩阵乘法
矩阵乘法是深度学习的基础算子。Triton的矩阵乘法教程展示了如何用**块级算法**实现接近cuBLAS的性能。
**核心算法**：每个Triton程序计算输出矩阵C的一个`[BLOCK_SIZE_M, BLOCK_SIZE_N]`块。内循环中，程序从A和B中加载对应的块到SRAM，累加部分结果。
**多维指针算术**：Triton需要计算每个块在A和B中的内存位置：
```text
# 初始化指针
a_block_ptr = tl.make_block_ptr(
    base=a_ptr, shape=(M, K), strides=(stride_am, stride_ak),
    offsets=(m, k), block_shape=(BLOCK_SIZE_M, BLOCK_SIZE_K),
    order=(1, 0)
)
```
**L2缓存优化**：Triton教程还展示了如何通过**程序重排序**提高L2缓存命中率——将输出块按组（Group）组织，而非简单的行主序，以减少从全局内存加载的次数。在A100上，这种优化可带来**超过10%的性能提升**（从220 TFLOPS到245 TFLOPS）。
### 2.5. 实战三：LayerNorm
LayerNorm是Transformer中的关键算子。Triton的LayerNorm教程展示了如何处理**更复杂的反向传播**。
**前向传播**：计算均值和方差，然后归一化并应用权重和偏置。
**反向传播的挑战**：由于同一批次的所有行共享相同的权重`w`和偏置`b`，它们的梯度需要**累加**。Triton使用**并行归约策略**：每个内核实例将部分梯度累积到独立的缓冲区中。
这个例子展示了Triton处理**复杂数据依赖**的能力——不仅仅是简单的逐元素操作。
### 2.6. Triton与CUDA的对比
> [内嵌电子表格，分享态无法直接读取内容]
## 3. 从Python到CUDA Kernel的性能优化路径
对于AI Infra工程师来说，算子开发通常不是“非此即彼”的选择，而是一条**渐进式的优化路径**。
### 3.1. 五层优化路径
**第一层：PyTorch原生实现**
这是起点。先用PyTorch的高层API实现功能，验证正确性。
**适用场景**：快速原型、对性能不敏感的部分。
**第二层：**`torch.compile`
在后文中我们学过，`torch.compile`可以自动捕获计算图并生成优化代码。这是**零代码改动**的优化手段。
**适用场景**：希望快速获得性能提升，不想手写内核。
**第三层：Triton内核**
当`torch.compile`的优化不够时，用Triton手写融合内核。Triton提供了**接近CUDA的性能，但开发效率高得多**。
**适用场景**：自定义算子、访存密集型操作的融合、需要精细控制内存访问的模式。
**第四层：CUDA C++内核**
当Triton也无法满足需求时（如需要利用特定的硬件特性、极致性能调优），手写CUDA C++。
**适用场景**：对性能有极致要求、需要利用最新硬件特性（如Hopper的TMA）、需要与现有CUDA库集成。
**第五层：汇编级优化（PTX/SASS）**
极少使用。只有在极少数情况下，需要对CUDA编译器生成的PTX或SASS进行手工调优。
### 3.2. 如何选择优化路径
**决策树**：
```text
第1步：PyTorch实现是否满足性能要求？
├── 是 → 停留在第一层
└── 否 → 第2步

第2步：torch.compile是否能达到目标性能？
├── 是 → 停留在第二层
└── 否 → 第3步

第3步：算子是否适合用Triton实现？
├── 是（访存密集、分块计算、融合多个小算子）→ 使用Triton
└── 否（需要特殊硬件指令、极复杂的控制流）→ 使用CUDA C++
```
### 3.3. 从Triton到CUDA的进阶路径
如果已经掌握了Triton，想进一步深入学习CUDA，建议按以下路径：
**第一步：理解CUDA的线程模型**
- 理解Thread、Block、Grid的三层结构
- 理解Warp的32线程调度
- 理解`blockIdx`、`threadIdx`、`blockDim`、`gridDim`的作用
**第二步：理解内存层次**
- 全局内存、共享内存、寄存器、L1/L2缓存
- 合并访问（Coalesced Access）
- 共享内存的bank conflict
**第三步：从简单内核开始**
- 向量加法 → 矩阵乘法 → 归约 → Softmax
- 每一步对比Triton实现和CUDA实现，理解差异
**第四步：性能调优**
- 使用`nvprof`或`Nsight Compute`分析性能瓶颈
- 优化occupancy（每个SM上活跃的Warp数量）
- 减少寄存器压力
### 3.4. 学习资源推荐
**CUDA**：
- NVIDIA官方《CUDA C++ Programming Guide》
- NVIDIA Developer Blog上的性能优化文章
- 《Professional CUDA C Programming》
**Triton**：
- Triton官方教程（矩阵乘法、Fused Softmax、LayerNorm）
- Triton中文文档（[hub.baai.ac.cn](http://hub.baai.ac.cn)）

## 写在最后

下一篇：[高效数据加载与预处理](/source/AI-Infra/1-大模型训练优化/18-高效数据加载与预处理.md)。
