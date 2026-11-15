# CUDA Graph 与 Runtime 优化

本篇通过 CUDA Graph 与 Runtime 优化减少 CPU 提交与 Kernel Launch 开销，提升重复工作负载效率。

Kernel 层面的优化主要回答「GPU 做一件事有多快」：访存是否合并、Kernel 是否融合、Tensor Core 是否吃满。但真实 AI 工作负载还有另一类瓶颈：GPU 很快，CPU 却来不及把工作提交给它。一次训练 Step 或一次 LLM Decode Step 可能包含数十到数百个短 Kernel，每个 Kernel 的计算只需几微秒，Python、Dispatcher、CUDA Runtime 与驱动却要反复完成参数准备、依赖检查与 Launch，GPU 时间线中便会出现一串「短 Kernel + 空洞」。

CUDA Graph 的核心价值是：把一段重复的 GPU 工作及其依赖捕获成图，实例化一次，之后用一次 Graph Launch 重放整段工作。它主要降低 Runtime 与 Launch 开销，不会让单个 Kernel 的数学计算自动变快。

## 1. 内容概览

- CUDA Runtime、Stream、Event、Graph Node、Graph Executable 的关系。
- 显式建图与 Stream Capture 两种方式。
- Capture、Instantiate、Replay、Update 的生命周期。
- 静态地址、静态 Shape、禁止 CPU 同步与私有内存池等约束。
- CPU Submit Time、GPU Execution Time、端到端延迟与盈亏平衡点的测量。
- PyTorch `torch.cuda.CUDAGraph` 与原生 CUDA C++ 的对照实验。
- 何时该用 Graph、`torch.compile`、Kernel Fusion、Batching 或 Stream 并发。

## 2. 核心直觉：把逐张工单变成一张固定流程单

普通 Eager 执行像工厂每完成一道工序，都回办公室领取下一张工单：

```text
CPU: Launch A ─ Launch B ─ Launch C ─ Launch D
         │          │          │          │
GPU:    Kernel A   Kernel B   Kernel C   Kernel D
```

CUDA Graph 则先记录完整工艺流程，后续只提交一次：

```text
首次：Capture(A→B→C→D) → Instantiate
后续：Graph Launch ─────→ GPU 执行 A→B→C→D
```

它省下的是重复提交与调度成本。若 A、B、C、D 本身都是很长的大 GEMM，CPU 早已提前把任务排入队列，Graph 收益可能很小；若它们是大量极短 Kernel，Graph 更容易显著降低空洞。

判断口诀：**Kernel 短而多、CPU 提交跟不上，才考虑 Graph；Kernel 长而少，先做算子与融合优化。**

## 3. 从 CUDA Runtime 看性能瓶颈

### 3.1 Kernel Launch 是异步的，但不是免费的

典型 CUDA Kernel Launch 对 Host 异步：CPU 提交后可以继续运行，GPU 稍后执行。然而每次提交仍经过应用、框架、Runtime、Driver 到设备队列。单次成本不一定大，但 $K$ 个小 Kernel 会累计为

$$
T_{host} = T_{python} + T_{framework} + \sum_{i=1}^{K} T_{launch,i} + T_{sync}
$$

单 Step 的 GPU 路径近似为

$$
T_{gpu} = \sum_{i=1}^{K} T_{kernel,i} + T_{memory} + T_{dependency}
$$

端到端时间不是简单相加，而由 CPU 与 GPU 时间线的关键路径决定：

$$
T_{step} \approx \max(T_{host\ submit},\ T_{gpu}) + T_{unhidden\ sync}
$$

当 $T_{host\ submit} > T_{gpu}$ 时，GPU 会等待 CPU，系统处于 Launch-bound。

### 3.2 隐式同步是 Runtime 优化的大敌

下列操作可能让 CPU 等待 GPU：`tensor.item()`、将 CUDA Tensor 打印成具体值；立即把结果复制回 Pageable Host Memory；`torch.cuda.synchronize()`、`cudaDeviceSynchronize()`；某些内存分配、错误检查或跨 Stream 依赖；读取尚未完成的 CUDA Event。

同步并非一律错误，错误的是把同步放在高频热路径中，或者不知道它存在。

### 3.3 Runtime 优化不只有 CUDA Graph

从低风险到高约束，常见顺序是：

1. 删除不必要同步与 Python 标量往返。
2. 使用 `inference_mode`、批处理与预分配。
3. 用 Kernel Fusion 减少 Launch 数与中间显存流量。
4. 用异步 H2D、Pinned Memory、Stream 实现搬运与计算重叠。
5. 用 `torch.compile` 自动捕获与融合。
6. 对稳定热路径使用 CUDA Graph。
7. 必要时用 Persistent Kernel 或自定义 Runtime。

Graph 与 Fusion 解决的不是同一个问题：Fusion 把多个算子变为更少的 Kernel；Graph 让仍然存在的多个 Kernel 以更低 Host 开销被重放。二者可以叠加。

## 4. CUDA Graph 的对象模型

### 4.1 Graph、Node、Edge

CUDA Graph 是有向无环图：Node 是 Kernel、Memcpy、Memset、Event、Host Function、子图等工作单元；Edge 是节点间依赖；`cudaGraph_t` 是图的定义；`cudaGraphExec_t` 是完成验证与优化后的可执行实例。

一个常见生命周期是：

```text
Warmup
  ↓
Capture / Explicit Construction
  ↓
cudaGraph_t
  ↓ Instantiate
cudaGraphExec_t
  ↓ Launch / Replay many times
Destroy
```

Instantiate 可能进行拓扑验证、资源准备与调度优化，所以不能把它混入稳态延迟。

### 4.2 显式建图与 Stream Capture

显式 API 手工创建 Node 与 Edge，控制精确但代码量大。Stream Capture 更常见：

```cpp
cudaStreamBeginCapture(stream, cudaStreamCaptureModeGlobal);
kernel_a<<<grid, block, 0, stream>>>(...);
kernel_b<<<grid, block, 0, stream>>>(...);
library_call(..., stream);
cudaStreamEndCapture(stream, &graph);
```

Capture 期间，提交到相关 Stream 的工作被记录到图里。PyTorch `torch.cuda.graph(...)` 与 `make_graphed_callables(...)` 在此基础上提供了更安全的封装。

### 4.3 Replay 为什么更便宜

普通模式每次都重走 $K$ 次提交路径，Graph 模式主要提交一个可执行图：

$$
T_{normal} = K \cdot T_{launch} + T_{gpu}
$$

$$
T_{graph} = T_{graph\ launch} + T_{gpu} + T_{input\ update}
$$

理论节省量近似为

$$
\Delta T \approx K \cdot T_{launch} - T_{graph\ launch} - T_{input\ update}
$$

这只是直觉模型。Driver 可能批量提交，Kernel 可并发，输入 Copy 也可能成为关键路径，最终必须 Profile。

## 5. 最重要的约束

### 5.1 固定虚拟地址

Graph Replay 默认读写与 Capture 时相同的虚拟地址。PyTorch 典型做法是保留长期存活的 `static_input` 与 `static_output`：

```python
static_input.copy_(new_input)
graph.replay()
result = static_output
```

不能每次把一个新 Tensor 对象直接「传给 Graph」，新的业务输入必须先复制到静态输入 Buffer。

### 5.2 静态 Shape 与布局

捕获后的 Kernel 参数、内存布局与拓扑高度稳定，不同 Batch、序列长度或 dtype 通常需要不同 Graph。生产实践常用有限 Bucket：

```text
batch: 1 / 2 / 4 / 8
sequence: 128 / 256 / 512 / 1024
每个高频组合预热并缓存一个 Graph
```

Bucket 太多会增加捕获成本、私有内存池与缓存管理压力。

### 5.3 Capture 期间不能做 CPU-GPU 同步

`.item()` 等操作要求 CPU 读取 GPU 结果，会破坏 Capture。CPU 工作本身也不会在 Replay 时重新执行，因此 Tokenizer、日志、文件 I/O 与 Python 动态分支应放在 Graph 外。

### 5.4 Warmup 必须先完成

第一次调用可能触发 CUDA Context 初始化、cuBLAS/cuDNN 算法选择与 Handle 创建、JIT/编译、PyTorch Caching Allocator 扩容、Lazy Module 或通信器初始化。这些动作在 Capture 中可能失败或被错误记录。PyTorch 手工捕获前应在 Side Stream 做足够 Warmup，再等待其完成。

### 5.5 Graph 私有内存池

为保证地址稳定，PyTorch Caching Allocator 会为 Graph 管理私有内存池。Graph 对象与捕获时创建的 Tensor 仍存活时，池可能一直保留。多个 Graph 默认各自拥有池，显存可能明显增加；仅在生命周期不重叠且语义安全时共享池。

### 5.6 随机数与状态更新

PyTorch 支持部分 CUDA RNG 操作，但生成器必须遵循 Graph-safe 状态管理。自定义 RNG、CPU 随机逻辑、动态 Optimizer/GradScaler 状态需要单独验证。Dropout「能运行」不等于随机序列与训练语义必然正确。

## 6. Graph Update 与动态工作负载

原生 CUDA 支持更新已实例化图。若拓扑相同，只是 Kernel 参数、某些内存地址或 Memcpy 参数变化，可以使用整图更新 `cudaGraphExecUpdate()` 或单 Node Update，避免重新 Instantiate。

但它不是「任意动态图」能力：图拓扑或 Node 类型大改通常要重新实例化；内存上下文、Memcpy 类型与 Kernel 能力有更新限制；框架封装不一定暴露所有原生 Update API；维护复杂度可能高于管理有限 Graph Bucket。

更新适合拓扑稳定、参数变化有限的低层 Runtime。高层 PyTorch/LLM 服务通常先用 Bucket；只有 Profile 证明捕获/缓存成本仍是瓶颈，才考虑原生 Update。

## 7. 关键性能模型

**盈亏平衡次数**：设捕获与实例化成本 $T_c$、普通稳态时间 $T_e$、Graph Replay 稳态时间 $T_g$，则

$$
N^* = \frac{T_c}{T_e - T_g},\quad T_g < T_e
$$

如果每个 Shape Bucket 都需独立捕获，$T_c$ 应按实际 Graph 数累计。

**Graph 能优化的比例**：若原时间中只有比例 $p$ 属于可捕获、Launch-bound 的热路径，该部分通过 Graph 加速 $s$ 倍：

$$
S_{total} = \frac{1}{(1-p) + p/s}
$$

Tokenizer、DataLoader、网络队列、长 GEMM 与未捕获通信所占比例越大，端到端收益越小。

**多 Stage Pipeline**：一个服务请求可拆为

$$
T = T_{queue} + T_{H2D} + T_{compute} + T_{D2H} + T_{sync}
$$

Graph 只降低其中可捕获部分。若 H2D 与 D2H 主导，应优先使用 Pinned Memory、批处理与 Stream Pipeline；若 Queue 主导，应优化 Scheduler；若长 GEMM 主导，应优化算子与精度。

## 8. 瓶颈分析方法

### 8.1 先判断是否 Launch-bound

用 Nsight Systems 观察：GPU Kernel 是否很短且密集；Kernel 之间是否有可见空洞；CPU CUDA API 调用是否占满一个核心；GPU 是否经常等待下一次提交；`.item()`、Memcpy 或 Synchronize 是否切断流水线。

若 GPU 上是连续的大 GEMM，Graph 通常不是第一优先级。

### 8.2 四组数字必须分开

1. Capture + Instantiate 时间。
2. CPU Submit Time。
3. GPU Event 测得的设备执行时间。
4. 包含输入 Copy 与必要同步的端到端时间。

Graph 能大幅降低 CPU Submit Time，却不一定按同样比例降低 GPU Event 时间，这是正常现象。

### 8.3 Nsight Systems 命令

```bash
nsys profile --trace=cuda,nvtx,osrt --cuda-graph-trace=graph \
  -o cuda_graph_summary python cuda_graph_lab.py

nsys profile --trace=cuda,nvtx,osrt --cuda-graph-trace=node \
  -o cuda_graph_nodes python cuda_graph_lab.py
```

`graph` 粒度扰动更小；`node` 粒度能看内部节点但采集开销更大。最终性能仍用无 Profile 基准确认。

## 9. Level 0：CPU Runtime 开销模拟实验

该实验不伪装成 GPU Graph，而是帮助没有 NVIDIA GPU 的环境理解「批量提交如何摊薄固定开销」。保存为 `runtime_overhead_model.py`：

```python
#!/usr/bin/env python3
import argparse
import time

def tiny_work(x, rounds):
    for i in range(rounds):
        x = (x * 1664525 + 1013904223 + i) & 0xFFFFFFFF
    return x

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--steps", type=int, default=20000)
    p.add_argument("--nodes", type=int, default=32)
    p.add_argument("--work-rounds", type=int, default=2)
    p.add_argument("--launch-us", type=float, default=3.0)
    args = p.parse_args()
    if min(args.steps, args.nodes, args.work_rounds) < 1 or args.launch_us < 0:
        raise SystemExit("参数必须为正数，launch-us 不能为负数")

    # 用算术循环近似每个节点的计算；固定 launch 成本用公式计入，
    # 避免 time.sleep 在微秒区间误差过大。
    x = 1
    t0 = time.perf_counter()
    for _ in range(args.steps):
        for _ in range(args.nodes):
            x = tiny_work(x, args.work_rounds)
    compute_s = time.perf_counter() - t0

    eager_launch_s = args.steps * args.nodes * args.launch_us / 1e6
    graph_launch_s = args.steps * args.launch_us / 1e6
    eager_total = compute_s + eager_launch_s
    graph_total = compute_s + graph_launch_s

    print(f"checksum={x}")
    print(f"compute_s={compute_s:.6f}")
    print(f"eager_model_s={eager_total:.6f}")
    print(f"graph_model_s={graph_total:.6f}")
    print(f"modeled_speedup={eager_total / graph_total:.3f}x")
    print(f"launch_overhead_saved_s={eager_launch_s - graph_launch_s:.6f}")

if __name__ == "__main__":
    main()
```

运行：

```bash
python3 runtime_overhead_model.py
python3 runtime_overhead_model.py --nodes 4 --work-rounds 100 --launch-us 3
python3 runtime_overhead_model.py --nodes 64 --work-rounds 1 --launch-us 3
```

预期现象：节点越多、单节点计算越短，Launch 开销占比越高，批量提交模型的收益越大；当每个节点计算很重时，Launch 开销被淹没，Speedup 接近 1。这个实验只验证性能模型，不等价模拟 CUDA Stream、Driver 或 GPU 并发。

## 10. Level 1：PyTorch CUDA Graph 完整实验

保存为 `cuda_graph_lab.py`。脚本会自动输出 GPU、Compute Capability、CUDA/PyTorch 版本，并分别测量 Eager、Graph Replay 与「输入 Copy + Replay」。

```python
#!/usr/bin/env python3
import argparse
import statistics
import time

import torch
from torch import nn

class LaunchBoundModel(nn.Module):
    def __init__(self, depth):
        super().__init__()
        self.depth = depth

    def forward(self, x):
        # 有意保留多个短 pointwise 算子，突出 Runtime 开销
        for _ in range(self.depth):
            x = torch.tanh(x) * 0.75 + torch.sigmoid(x) * 0.25
        return x

def sync():
    torch.cuda.synchronize()

def gpu_time_ms(fn, iterations):
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    for _ in range(iterations):
        fn()
    end.record()
    end.synchronize()
    return start.elapsed_time(end) / iterations

def cpu_submit_us(fn, iterations):
    sync()
    samples = []
    for _ in range(5):
        t0 = time.perf_counter()
        for _ in range(iterations):
            fn()
        submit_us = (time.perf_counter() - t0) * 1e6 / iterations
        sync()
        samples.append(submit_us)
    return statistics.median(samples)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--width", type=int, default=4096)
    p.add_argument("--depth", type=int, default=16)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--iterations", type=int, default=100)
    args = p.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("需要可用的 NVIDIA CUDA GPU；无 GPU 请运行 Level 0")
    if min(args.batch, args.width, args.depth, args.warmup, args.iterations) < 1:
        raise SystemExit("所有整数参数必须为正数")

    device = torch.device("cuda")
    prop = torch.cuda.get_device_properties(device)
    print(f"torch={torch.__version__} cuda={torch.version.cuda}")
    print(f"gpu={prop.name} capability={prop.major}.{prop.minor} "
          f"vram_gib={prop.total_memory / 2**30:.2f}")

    torch.manual_seed(0)
    model = LaunchBoundModel(args.depth).eval().to(device)
    static_input = torch.randn(args.batch, args.width, device=device)

    # 必须在 Side Stream 预热，完成 Lazy 初始化和内存池准备。
    warmup_stream = torch.cuda.Stream()
    warmup_stream.wait_stream(torch.cuda.current_stream())
    with torch.cuda.stream(warmup_stream), torch.inference_mode():
        for _ in range(args.warmup):
            model(static_input)
    torch.cuda.current_stream().wait_stream(warmup_stream)
    sync()

    graph = torch.cuda.CUDAGraph()
    capture_begin = time.perf_counter()
    with torch.inference_mode(), torch.cuda.graph(graph):
        static_output = model(static_input)
    sync()
    capture_ms = (time.perf_counter() - capture_begin) * 1000.0

    # 新输入必须 copy 到捕获时的静态地址。
    real_input = torch.randn_like(static_input)
    with torch.inference_mode():
        reference = model(real_input)
        static_input.copy_(real_input)
        graph.replay()
    sync()
    torch.testing.assert_close(static_output, reference, rtol=2e-4, atol=2e-4)

    with torch.inference_mode():
        eager = lambda: model(real_input)
        replay_only = graph.replay

        def copy_and_replay():
            static_input.copy_(real_input)
            graph.replay()

        # 再预热计时路径
        for _ in range(5):
            eager()
            replay_only()
            copy_and_replay()
        sync()

        eager_gpu = gpu_time_ms(eager, args.iterations)
        graph_gpu = gpu_time_ms(replay_only, args.iterations)
        graph_copy_gpu = gpu_time_ms(copy_and_replay, args.iterations)
        eager_submit = cpu_submit_us(eager, args.iterations)
        graph_submit = cpu_submit_us(replay_only, args.iterations)
        graph_copy_submit = cpu_submit_us(copy_and_replay, args.iterations)

    print(f"capture_and_instantiate_ms={capture_ms:.3f}")
    print(f"eager_gpu_ms={eager_gpu:.4f}")
    print(f"graph_replay_gpu_ms={graph_gpu:.4f}")
    print(f"graph_copy_replay_gpu_ms={graph_copy_gpu:.4f}")
    print(f"eager_cpu_submit_us={eager_submit:.3f}")
    print(f"graph_replay_cpu_submit_us={graph_submit:.3f}")
    print(f"graph_copy_replay_cpu_submit_us={graph_copy_submit:.3f}")
    print(f"replay_speedup={eager_gpu / graph_gpu:.3f}x")
    print(f"copy_replay_speedup={eager_gpu / graph_copy_gpu:.3f}x")
    print(f"peak_allocated_mib={torch.cuda.max_memory_allocated()/2**20:.1f}")
    print(f"peak_reserved_mib={torch.cuda.max_memory_reserved()/2**20:.1f}")

if __name__ == "__main__":
    main()
```

### 10.1 安装与运行

```bash
python3 -m venv .venv-cudagraph
source .venv-cudagraph/bin/activate
python -m pip install --upgrade pip
# 按 PyTorch 官方安装页选择与驱动兼容的稳定 CUDA 构建

nvidia-smi
python cuda_graph_lab.py
python cuda_graph_lab.py --batch 8 --width 1024 --depth 32 --iterations 200
python cuda_graph_lab.py --batch 128 --width 8192 --depth 8 --iterations 50

CUDA_VISIBLE_DEVICES=0 python cuda_graph_lab.py
CUDA_VISIBLE_DEVICES=1 python cuda_graph_lab.py
```

### 10.2 预期现象

- `graph_replay_cpu_submit_us` 通常显著低于 Eager，尤其在 `depth` 较大时。
- `graph_replay_gpu_ms` 可能改善，也可能接近 Eager，取决于 Eager 时间线是否真的被 Host 提交限制。
- `copy_and_replay` 比 Replay-only 更接近真实服务，收益会被输入 Copy 部分抵消。
- 增大每个算子的计算量后，Graph Speedup 往往下降，因为 GPU 计算成为主导。
- Graph 私有内存池可能使 `reserved` 增加，这不自动等于内存泄漏。

### 10.3 结果分析模板

| 指标 | Eager | Replay-only | Copy + Replay |
| --- | --- | --- | --- |
| CPU Submit，µs | 实测 | 实测 | 实测 |
| GPU 平均时间，ms | 实测 | 实测 | 实测 |
| Capture/Instantiate，ms | 0 | 一次性 | 一次性 |
| Peak allocated，MiB | 实测 | 实测 | 实测 |
| Peak reserved，MiB | 实测 | 实测 | 实测 |
| 输出正确性 | 基准 | 对齐 | 对齐 |

性能数字只代表本次环境，不可外推为某种 GPU 的固定结论。

## 11. Level 2：原生 CUDA C++ Graph 实验

该实验直接调用 CUDA Runtime，用多个极短 Kernel 观察 Launch 压力，同时对比 Stream Capture 与显式建图。保存为 `cuda_graph_native.cu`：

```cpp
#include <cstdio>
#include <cstdlib>
#include <chrono>
#include <cuda_runtime.h>

#define CHECK(x) do { cudaError_t e = (x); if (e != cudaSuccess) { \
  fprintf(stderr, "%s:%d %s\n", __FILE__, __LINE__, cudaGetErrorString(e)); \
  exit(1); } } while (0)

// 极短 Kernel：每线程只做几次乘加，突出 Launch 开销
__global__ void tiny_step(float* data, int n, float a, float b) {
  int i = blockIdx.x * blockDim.x + threadIdx.x;
  if (i < n) {
    float v = data[i];
    v = v * a + b;
    data[i] = v * a + b;
  }
}

static void run_eager(float* d, int n, int nodes, int blocks, int threads,
                      cudaStream_t s) {
  for (int k = 0; k < nodes; ++k) {
    tiny_step<<<blocks, threads, 0, s>>>(d, n, 1.0001f, 0.0001f);
  }
}

int main(int argc, char** argv) {
  int n = (argc > 1) ? atoi(argv[1]) : 1 << 16;
  int nodes = (argc > 2) ? atoi(argv[2]) : 64;
  int iters = (argc > 3) ? atoi(argv[3]) : 200;
  int threads = 256;
  int blocks = (n + threads - 1) / threads;

  float* d = nullptr;
  CHECK(cudaMalloc(&d, n * sizeof(float)));
  CHECK(cudaMemset(d, 0, n * sizeof(float)));

  cudaStream_t s;
  CHECK(cudaStreamCreate(&s));

  // Warmup：完成 Context、模块加载与首次算法选择
  for (int i = 0; i < 5; ++i) run_eager(d, n, nodes, blocks, threads, s);
  CHECK(cudaStreamSynchronize(s));

  cudaEvent_t e0, e1;
  CHECK(cudaEventCreate(&e0));
  CHECK(cudaEventCreate(&e1));

  // Eager：GPU 时间与 CPU 提交时间分别测
  CHECK(cudaEventRecord(e0, s));
  for (int i = 0; i < iters; ++i) run_eager(d, n, nodes, blocks, threads, s);
  CHECK(cudaEventRecord(e1, s));
  CHECK(cudaEventSynchronize(e1));
  float eager_gpu_ms = 0.f;
  CHECK(cudaEventElapsedTime(&eager_gpu_ms, e0, e1));
  eager_gpu_ms /= iters;

  CHECK(cudaStreamSynchronize(s));
  auto t0 = std::chrono::high_resolution_clock::now();
  for (int i = 0; i < iters; ++i) run_eager(d, n, nodes, blocks, threads, s);
  auto t1 = std::chrono::high_resolution_clock::now();
  CHECK(cudaStreamSynchronize(s));
  double eager_submit_us =
      std::chrono::duration<double, std::micro>(t1 - t0).count() / iters;

  // Stream Capture：记录 nodes 个 Kernel 及其依赖
  CHECK(cudaStreamSynchronize(s));
  cudaGraph_t graph;
  auto c0 = std::chrono::high_resolution_clock::now();
  CHECK(cudaStreamBeginCapture(s, cudaStreamCaptureModeGlobal));
  run_eager(d, n, nodes, blocks, threads, s);
  CHECK(cudaStreamEndCapture(s, &graph));
  cudaGraphExec_t exec;
  CHECK(cudaGraphInstantiate(&exec, graph, nullptr, nullptr, 0));
  auto c1 = std::chrono::high_resolution_clock::now();
  double capture_ms = std::chrono::duration<double, std::milli>(c1 - c0).count();

  for (int i = 0; i < 5; ++i) CHECK(cudaGraphLaunch(exec, s));
  CHECK(cudaStreamSynchronize(s));

  CHECK(cudaEventRecord(e0, s));
  for (int i = 0; i < iters; ++i) CHECK(cudaGraphLaunch(exec, s));
  CHECK(cudaEventRecord(e1, s));
  CHECK(cudaEventSynchronize(e1));
  float graph_gpu_ms = 0.f;
  CHECK(cudaEventElapsedTime(&graph_gpu_ms, e0, e1));
  graph_gpu_ms /= iters;

  CHECK(cudaStreamSynchronize(s));
  t0 = std::chrono::high_resolution_clock::now();
  for (int i = 0; i < iters; ++i) CHECK(cudaGraphLaunch(exec, s));
  t1 = std::chrono::high_resolution_clock::now();
  CHECK(cudaStreamSynchronize(s));
  double graph_submit_us =
      std::chrono::duration<double, std::micro>(t1 - t0).count() / iters;

  size_t num_nodes = 0;
  CHECK(cudaGraphGetNodes(graph, nullptr, &num_nodes));
  printf("nodes=%d graph_nodes=%zu\n", nodes, num_nodes);
  printf("capture_instantiate_ms=%.3f\n", capture_ms);
  printf("eager_gpu_ms=%.4f graph_gpu_ms=%.4f gpu_speedup=%.3fx\n",
         eager_gpu_ms, graph_gpu_ms, eager_gpu_ms / graph_gpu_ms);
  printf("eager_submit_us=%.3f graph_submit_us=%.3f submit_speedup=%.3fx\n",
         eager_submit_us, graph_submit_us, eager_submit_us / graph_submit_us);
  printf("break_even_calls=%.1f\n",
         capture_ms * 1000.0 / (eager_submit_us - graph_submit_us));

  CHECK(cudaGraphExecDestroy(exec));
  CHECK(cudaGraphDestroy(graph));
  CHECK(cudaEventDestroy(e0));
  CHECK(cudaEventDestroy(e1));
  CHECK(cudaStreamDestroy(s));
  CHECK(cudaFree(d));
  return 0;
}
```

编译与运行：

```bash
nvcc -O3 -arch=native cuda_graph_native.cu -o cuda_graph_native
./cuda_graph_native 65536 64 200
./cuda_graph_native 65536 8 200
./cuda_graph_native 1048576 64 100
```

预期现象与检查点：

- `submit_speedup` 通常远大于 `gpu_speedup`，因为 Graph 主要省的是 Host 提交路径。
- `nodes` 越多、`n` 越小，Launch 开销占比越高，收益越明显；`n` 很大时 GPU 计算主导，两者趋近。
- `capture_instantiate_ms` 是一次性成本，用 `break_even_calls` 判断是否值得。
- 用 `nsys profile --cuda-graph-trace=node ./cuda_graph_native` 可确认图内节点数与依赖是否符合预期。

`-arch=native` 需要较新的 CUDA Toolkit；旧版本改为显式 Compute Capability（如 `-arch=sm_86`）。Graph API 不依赖特定架构，但节点级 Trace 与部分更新能力随驱动与 Toolkit 版本变化。

## 12. 决策：Graph 与其他手段如何选

| 现象 | 首选手段 | 理由 |
| --- | --- | --- |
| 大量短 Pointwise Kernel、显存流量高 | Kernel Fusion / `torch.compile` | 同时减少 Launch 与中间 Tensor 往返 |
| Kernel 已融合但仍密集、CPU 提交占满一核 | CUDA Graph | 剩余成本主要在 Runtime 提交路径 |
| 输入 Shape 频繁变化 | Shape Bucket + 有限 Graph | 避免无界捕获与内存池膨胀 |
| Batch 很小、GPU 利用率低 | Batching / Continuous Batching | 先提高并行度，再谈提交开销 |
| H2D/D2H 与计算串行 | Pinned Memory + 多 Stream | 搬运与计算重叠，Graph 无法解决 |
| 通信暴露时间长 | 计算通信重叠、Bucket 调优 | Graph 不会自动消除 All-Reduce |
| 拓扑稳定但参数常变 | Graph Update 或 Bucket | 先评估维护成本，Profile 后再决定 |

三者可以叠加：先用 Fusion 减少 Kernel 数量与显存流量，再用 Graph 固化剩余提交序列，最后用 Stream 与 Batching 处理搬运与并行度。每一步都要回到无 Profile 的端到端基准确认收益，并把 Capture 成本、私有内存池与 Shape Bucket 数量一起纳入总账。

## 写在最后

CUDA Graph 优化的不是计算本身，而是「把计算交给 GPU」这条路径。它的收益上限由可捕获热路径的占比决定，它的落地难度由静态地址、静态 Shape 与内存池约束决定。下一篇把视角从单点技术抬到系统层面，梳理 AI Runtime 优化的通用思想。

下一篇：[AI Runtime 优化思想](/source/AI-Infra/2-AI系统性能工程/22-AIRuntime优化思想)。