# CUDA 编程模型

本篇建立 CUDA 编程模型的完整认识：线程组织、内存空间、Stream、Event 与异步执行。

PyTorch、Triton、cuBLAS 和 vLLM 最终都要把工作提交给 GPU。理解 CUDA 编程模型，不是为了把所有算子重写成 CUDA C++，而是为了看懂 Kernel 为什么这样划分线程、为什么一次 Launch 没有立刻完成、为什么 `cudaDeviceSynchronize()` 会让程序突然变慢，以及为什么同一段源码在不同 GPU 上会选择不同指令。

## 1. 内容概览

- Host/Device/Kernel/CUDA Runtime 的关系与程序生命周期。
- Grid、Block、Thread、Warp 的组织方式，以及 `__global__` / `__device__` 等执行空间。
- Memory Space 的六种类型与两个常见误区。
- 同步粒度：Block Barrier、Event、Stream 的关系。
- Stream 与异步执行的真实条件。
- Source → PTX → Cubin → SASS 的编译模型与 Compute Capability 目标。

## 2. 核心直觉：CPU 发任务，GPU 批量执行

```text
Host / CPU
  ├─ 分配 Host/Device Memory
  ├─ 准备数据
  ├─ 把工作加入 CUDA Stream
  ├─ 发起 Kernel Launch / Memory Copy
  └─ 在需要结果时同步

Device / GPU
  ├─ SM 接收 Thread Block
  ├─ Warp Scheduler 发射 Warp 指令
  ├─ 线程访问寄存器、Shared Memory、Global Memory
  └─ 完成后由 Event/同步点向 Host 暴露状态
```

CPU 不是逐个遥控 GPU Thread。Host 发出一个 Kernel Launch，描述「运行哪个函数、启动多少 Block、每个 Block 多少 Thread、使用哪个 Stream」，GPU Runtime 与硬件负责把 Block 调度到 SM 上。

因此 CUDA 优化有两条主线：**并行分解**（有没有足够独立的工作填满 GPU）与**数据与依赖**（线程需要的数据在哪里、哪些操作必须等待）。

## 3. CUDA 程序的生命周期

```cuda
// 1. Host 分配并初始化数据
cudaMalloc(&device_ptr, bytes);

// 2. Host -> Device
cudaMemcpy(device_ptr, host_ptr, bytes, cudaMemcpyHostToDevice);

// 3. 启动 Kernel
kernel<<<grid_dim, block_dim>>>(device_ptr, n);

// 4. 检查 Launch，并等待需要的结果
cudaGetLastError();
cudaDeviceSynchronize();

// 5. Device -> Host，验证并释放
cudaMemcpy(host_ptr, device_ptr, bytes, cudaMemcpyDeviceToHost);
cudaFree(device_ptr);
```

Kernel 启动语法不是普通 C++ 函数调用：它配置并提交 GPU Kernel；默认情况下 Host 继续执行，异步错误可能到后续同步 API 才暴露。

## 4. 函数执行空间

| 限定符 | 调用方 | 执行位置 | 常见用途 |
| --- | --- | --- | --- |
| `__global__` | Host；部分场景可由 Device | Device | Kernel 入口，返回 `void` |
| `__device__` | Device | Device | GPU 辅助函数 |
| `__host__` | Host | Host | 普通 CPU 函数 |
| `__host__ __device__` | Host/Device | 分别编译 | 简单通用数学函数 |

`__host__ __device__` 会生成两个版本，但不能因此调用任意 Host-only 标准库或操作系统 API；要检查 Host 与 Device 两条编译路径。

## 5. 线程层级

```text
Kernel Launch
└─ Grid
   ├─ Block 0
   │  ├─ Thread 0
   │  ├─ Thread 1
   │  └─ ...
   ├─ Block 1
   └─ ...
```

CUDA 提供内置坐标：`threadIdx.{x,y,z}`（Block 内位置）、`blockIdx.{x,y,z}`（Grid 内位置）、`blockDim.{x,y,z}`（Block 形状）、`gridDim.{x,y,z}`（Grid 形状）。

一维全局索引：

$$
i = \mathrm{blockIdx.x} \times \mathrm{blockDim.x} + \mathrm{threadIdx.x}
$$

二维矩阵索引：

$$
\mathrm{row} = \mathrm{blockIdx.y} \times \mathrm{blockDim.y} + \mathrm{threadIdx.y}, \qquad
\mathrm{col} = \mathrm{blockIdx.x} \times \mathrm{blockDim.x} + \mathrm{threadIdx.x}
$$

### 5.1 Ceiling Division 与边界检查

若元素数为 $N$、每 Block 有 $T$ 个线程：

$$
B = \left\lceil \frac{N}{T} \right\rceil = \frac{N + T - 1}{T}
$$

最后一个 Block 可能越界，Kernel 必须做边界检查：

```cuda
if (i < n) {
    out[i] = x[i] + y[i];
}
```

### 5.2 Grid-Stride Loop

```cuda
for (size_t i = blockIdx.x * blockDim.x + threadIdx.x;
     i < n;
     i += static_cast<size_t>(blockDim.x) * gridDim.x) {
    out[i] = x[i] + y[i];
}
```

优点：Grid 大小不必与问题规模一一对应；同一 Thread 可处理多个元素；便于控制 Block 数、测试长期驻留工作；对超大数组使用 `size_t` 可避免 32-bit Index Overflow。

### 5.3 Block 是调度和协作单位

同一 Block 的线程：在同一 SM 上执行；可以用 Shared Memory 交换数据；可以通过 `__syncthreads()` 做 Block 范围 Barrier；共享有限的 Register File、Shared Memory 与 Resident Thread 配额。

普通 CUDA 模型不能假设不同 Block 同时驻留，也不能在一个普通 Kernel 中用 `__syncthreads()` 实现 Grid-wide Barrier。跨 Block 全局同步通常需要拆成多个 Kernel、Cooperative Launch 或其他专用机制。

## 6. Warp 与 SIMT

当前 NVIDIA GPU 的 Warp 通常由 32 个线程组成。Scheduler 以 Warp 为基本发射单位，但每个 Thread 保留自己的 Register State 和逻辑执行路径。

### 6.1 分支发散

```cuda
if (threadIdx.x % 2 == 0) {
    path_a();
} else {
    path_b();
}
```

同一 Warp 中线程走不同分支时，硬件需要执行不同路径并屏蔽不参与的 Lane。简化效率模型：

$$
\eta_{branch} \approx \frac{\text{active lane cycles}}{32 \times \text{issued warp cycles}}
$$

但「代码里有 if」不等于一定很慢：编译器可能使用 Predication；分支可能在 Warp 间一致；分支体很短；Kernel 可能由内存或其他瓶颈主导。必须用 Profiler 验证，不要只看源码猜。

### 6.2 独立线程调度的边界

Volta 及以后支持更细粒度的 Independent Thread Scheduling，但这不意味着 Warp 内线程可以忽略同步。Warp-level intrinsic 应使用带 Active Mask 的 `_sync` 版本，并保证参与线程集合正确：

```cuda
unsigned mask = __activemask();
int value_from_lane0 = __shfl_sync(mask, value, 0);
```

依赖「同一 Warp 自然同时执行」而没有正确 primitive 的旧代码，可能产生竞态。

## 7. Memory Space

| 空间 | 典型范围 | 生命周期 | 直觉 |
| --- | --- | --- | --- |
| Register | 单 Thread | Thread | 最快、容量有限 |
| Local Memory | 单 Thread 语义 | Thread | 名为 Local，物理上常落到 Device Memory |
| Shared Memory | 单 Block | Block | 程序员管理的片上共享区 |
| Global Memory | Grid/Host 可管理 | Allocation | 大容量显存，延迟较高 |
| Constant Memory | Grid，只读 | Module/Context | 小型广播常量 |
| Texture/Read-only Path | Grid，只读语义 | Allocation | 特定缓存与寻址行为 |

两个重要误区：

1. C++ 局部变量不保证一定在 Register；Register Pressure 过高可能 Spill 到 Local Memory。
2. `cudaMallocManaged` 不等于「数据永远同时在 CPU 与 GPU」；Unified Memory 仍有迁移、一致性、Page Fault 和 Prefetch 成本。

## 8. 同步与内存可见性

### 8.1 Block 内 Barrier

`__syncthreads()` 的语义是 Block 内参与线程等待，并建立对应的 Shared/Global Memory 可见性边界；它必须被 Block 内所有活动线程以一致方式到达。

```cuda
if (threadIdx.x < 16) {
    __syncthreads(); // 其他线程不进入，可能死锁或产生未定义行为
}
```

### 8.2 Barrier 不等于 Atomic

Barrier 只协调到达与可见性，不能把多个线程的 Read-Modify-Write 自动变成原子操作；计数器需要 `atomicAdd` 或正确的层级归约。

### 8.3 Host 同步粒度

| API | 等待范围 |
| --- | --- |
| `cudaDeviceSynchronize()` | 当前 Device 的先前工作 |
| `cudaStreamSynchronize(s)` | 指定 Stream 的先前工作 |
| `cudaEventSynchronize(e)` | 指定 Event 完成 |
| `cudaStreamWaitEvent(s,e)` | Device-side 依赖，不阻塞 Host Thread |
| `cudaStreamQuery(s)` | 非阻塞查询 Stream 状态 |

同步越粗越容易正确，也越容易破坏并发；性能工程的目标是使用满足依赖的最小同步范围。

## 9. Stream 与异步执行

Stream 是有序工作队列：同一 Stream 中操作按提交顺序执行，不同 Stream 的独立工作**可能**并发。

```text
Stream 0: H2D A → Kernel A → D2H A
Stream 1: H2D B → Kernel B → D2H B
```

实际能否重叠取决于：GPU 是否有相应 Copy Engine；Host Buffer 是否 Page-locked；Kernel 是否占满全部 SM 与 Memory Bandwidth；两项工作是否有真实依赖；默认 Stream 和其他隐式同步；Device Allocation、Page-locked Allocation 等同步行为；消息是否大到足以摊薄 Launch 开销。

**默认 Stream**：Legacy Default Stream 可能与其他 Blocking Stream 发生隐式同步。可创建 `cudaStreamNonBlocking` Stream，或在明确理解语义后使用 Per-thread Default Stream；不要混用后再凭「看起来应该并发」推断结果。

## 10. Event 与计时

CUDA Event 在 Device 时间线上记录位置，适合测量 GPU 工作：

```cuda
cudaEventRecord(start);
kernel<<<grid, block>>>(...);
cudaEventRecord(stop);
cudaEventSynchronize(stop);
cudaEventElapsedTime(&ms, start, stop);
```

Host `std::chrono` 只包住异步 Kernel Launch 时，测到的主要是提交开销。要测端到端，必须在结束前同步；要测单个 Kernel，优先使用正确 Stream 上的 Event。计时前应 Warmup，避免把 Context 初始化、JIT、Cache Cold Start 与 Frequency Ramp 混入稳态。

## 11. 错误处理

CUDA 错误分两类：**同步 API 错误**（如 `cudaMalloc` 立即失败）与**异步执行错误**（如 Illegal Memory Access，常在同步或后续 API 才报告）。必须同时检查：

```cuda
kernel<<<grid, block>>>(...);
CUDA_CHECK(cudaGetLastError());      // Launch 配置等立即错误
CUDA_CHECK(cudaDeviceSynchronize()); // 执行期错误
```

Benchmark 中每轮都 `cudaDeviceSynchronize()` 会扭曲性能；调试时可严格同步，性能测量时用 Event/Stream 边界并在合理位置检查。`CUDA_LAUNCH_BLOCKING=1` 适合定位异步报错位置，不适合当作生产性能配置。

## 12. 编译模型：Source、PTX、Cubin 与 SASS

```text
CUDA C++ Source
   ├─ Host Compiler → Host Object
   └─ NVCC Device Frontend
        ├─ PTX：虚拟 ISA，可由 Driver JIT
        └─ Cubin：目标架构机器码容器
             └─ SASS：GPU 实际执行指令
```

| 架构/产品示例 | 常见目标 |
| --- | --- |
| Ampere A100 | `sm_80` |
| Ampere RTX 3080/3090 | `sm_86` |
| Ada RTX 4090、L40/L40S | `sm_89` |
| Hopper H100/H200 | `sm_90` |
| Blackwell B100/B200/GB200 | `sm_100`，依 Toolkit/SDK 具体目标 |
| Blackwell RTX 5090 | `sm_120` |

单目标编译（双 RTX 3080）：

```bash
nvcc -O3 -std=c++17 -lineinfo -arch=sm_86 cuda_model_lab.cu -o cuda_model_lab
```

通用 Fat Binary：

```bash
nvcc -O3 -std=c++17 -lineinfo \
  -gencode arch=compute_80,code=sm_80 \
  -gencode arch=compute_86,code=sm_86 \
  -gencode arch=compute_89,code=sm_89 \
  -gencode arch=compute_90,code=sm_90 \
  -gencode arch=compute_90,code=compute_90 \
  cuda_model_lab.cu -o cuda_model_lab
```

最后一项保留 PTX，允许 Driver 在受支持的更新 GPU 上 JIT。需要注意：新架构 Cubin 不能反向在旧 GPU 上运行；PTX Forward Compatibility 仍受 PTX ISA、Driver JIT 与 Feature 限制；`sm_100/sm_120` 需要支持 Blackwell 的 Toolkit；仅保留 PTX 会产生首次 JIT 开销，生产应按部署矩阵生成合适 Fatbin。

## 写在最后

CUDA 编程模型给的是「提交与依赖」的框架：谁发任务、谁等待、谁看见什么内存。下一篇专门讲 Memory Access 优化——同一个 Kernel 换个访问模式，性能可以差数倍。

下一篇：[GPU Memory 访问优化](/source/AI-Infra/2-AI系统性能工程/11-GPUMemory访问优化)。
