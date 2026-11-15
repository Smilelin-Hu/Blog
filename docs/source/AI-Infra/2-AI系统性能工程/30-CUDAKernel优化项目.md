# CUDA Kernel 优化项目

本项目通过 CUDA Kernel 基线、剖析、改写与回归验证，完成一次端到端算子优化。

从一个「结果正确但性能很差」的 CUDA Reduction Kernel 出发，用 Profile-Driven 方法完成两轮优化：

```text
Baseline：每个元素执行一次全局 atomicAdd
    ↓ 消除大部分全局原子争用
V1：线程局部累加 + Shared Memory Block Reduction + 每 Block 一次 atomicAdd
    ↓ 减少 Shared Memory 访问与同步
V2：线程局部累加 + Warp Shuffle + 每 Block 一次 atomicAdd
```

最终交付的不只是「更快的代码」，而是一套完整证据：相同输入、相同正确性标准、稳定计时、不同规模扫描、Nsight Systems 时间线、Nsight Compute Kernel 指标，以及清楚的结论边界。

项目适配常见 NVIDIA GPU。Level 0 不需要 CUDA；Level 1 使用标准 CUDA C++，适合 Ampere RTX 3080/3090、A100，Ada RTX 4090/L40/L40S，Hopper H100/H200，以及工具链支持的 Blackwell RTX 5090、B100/B200/GB200。Level 2 的架构专项实验必须先检测能力，不允许把低代 GPU 的模拟结果写成 FP8、FP4、TMA 或 Cluster 的硬件实测。

## 1. 内容概览与交付物

做完之后应当能够：从算法工作量、内存流量与同步次数解释 Kernel 为什么慢；正确使用 Grid-Stride Loop、Shared Memory、`__syncthreads()` 与 Warp Shuffle；区分全局原子争用、Shared Memory Bank Conflict、Occupancy 与指令依赖；使用 CUDA Event 测量设备执行时间；用 Nsight Systems 找到 Kernel 边界，用 Nsight Compute 验证优化原因；在改变实现后同时验证正确性、P50/P95、跨尺寸稳定性与架构可移植性；避免用峰值带宽、Occupancy 或一次运行结果替代真实证据。

前置知识：GPU 微架构与 Kernel 优化相关内容；理解 Thread、Warp、Block、Grid 与 Grid-Stride Loop；理解 Global Memory、Shared Memory、原子操作与同步；Ubuntu 或其他支持 CUDA Toolkit 的系统；可选 NVIDIA GPU，没有 GPU 时先完成 Level 0。

```text
cuda-kernel-project/
├── reduction_cost_model.py
├── reduction_benchmark.cu
├── reports/
│   ├── environment.txt
│   ├── baseline.csv
│   ├── size_sweep.csv
│   ├── reduction_nsys.nsys-rep
│   └── reduction_ncu.ncu-rep
└── analysis.md
```

`analysis.md` 至少回答：

1. Baseline 最主要的瓶颈是什么？
2. V1 消除了什么成本，又引入了什么成本？
3. V2 为什么可能继续变快，也可能没有明显收益？
4. 哪些结论来自实测，哪些只是模型推断？
5. 结论适用于哪些输入规模、Block Size 与 GPU？

## 2. 核心直觉：先减少昂贵协作，再优化局部细节

Reduction 的数学表达很简单：

$$
y = \sum_{i=0}^{N-1} x_i
$$

但 GPU 实现的关键不是加法本身，而是「数百万个线程如何合并局部结果」。最朴素的实现让每个元素都竞争同一个全局地址：

$$
N_{atomic}^{baseline} = N
$$

如果每个 Block 先在本地归约，只让 Block Leader 更新全局结果：

$$
N_{atomic}^{optimized} = N_{blocks}
$$

原子操作数量的理论缩减比约为

$$
R_{atomic} = \frac{N}{N_{blocks}}
$$

这不等于最终加速比。优化版还要付出线程局部累加、Shared Memory、同步与归约指令的成本；Baseline 的原子实现也可能被缓存、硬件原子单元与输入规模影响。真实收益必须测量。

## 3. 性能模型

### 3.1 最小数据搬运量

若输入为 FP32，至少要读取

$$
Bytes_{read} = 4N
$$

输出只有一个 FP32，但原子读改写会产生额外流量与序列化，不能只按 4 字节输出估算物理事务。有效输入带宽可写成

$$
BW_{effective} = \frac{4N}{t}
$$

它用于比较同一算法的不同实现，不代表硬件实际 DRAM 总流量。

### 3.2 算术强度

Reduction 每读取一个 FP32 大约做一次加法：

$$
AI \approx \frac{N}{4N} = 0.25\ \text{FLOP/Byte}
$$

它通常属于低算术强度工作负载，但 Baseline 可能先受全局原子争用限制，而不是先触达 DRAM 带宽屋脊。

### 3.3 Amdahl 定律

若 Reduction 只占端到端程序的比例为 $p$，即使 Kernel 加速 $S_k$ 倍，端到端加速上界仍是

$$
S_{total} = \frac{1}{(1-p) + \frac{p}{S_k}}
$$

因此项目必须同时报告 Kernel 加速与它在真实应用中的时间占比。

## 4. 瓶颈分析顺序

| 层次 | 问题 | 证据 |
| --- | --- | --- |
| 正确性 | 三个 Kernel 是否得到一致结果 | CPU Reference、误差 |
| 墙钟 | 优化是否稳定变快 | CUDA Event、P50/P95 |
| 系统级 | 是否存在启动、同步或空闲问题 | Nsight Systems |
| Kernel 级 | 时间消耗在原子、内存、同步还是执行依赖 | Nsight Compute |
| 资源级 | Block、寄存器、Shared Memory 是否限制并发 | LaunchStats、Occupancy |
| 端到端 | Reduction 是否值得继续优化 | Amdahl 占比 |

顺序不能颠倒。先确认结果对，再确认时间稳，再解释时间花在哪里；跳过前两步直接看 Nsight Compute 指标，很容易把噪声当成结论。

## 5. Level 0：CPU 成本模型

下面的脚本不模拟 GPU 的真实并发，只计算三种实现的操作数量，用于在上 GPU 前提出可证伪假设。保存为 `reduction_cost_model.py`：

```python
#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path

def estimate(elements: int, blocks: int, block_size: int) -> dict:
    if min(elements, blocks, block_size) <= 0:
        raise ValueError("elements、blocks、block-size 必须大于 0")
    if block_size % 32 != 0 or block_size > 1024:
        raise ValueError("block-size 必须是 32 的倍数且不超过 1024")

    warps_per_block = block_size // 32
    shared_steps = int(math.log2(block_size))
    return {
        "elements": elements,
        "blocks": blocks,
        "block_size": block_size,
        "baseline_global_atomics": elements,
        "optimized_global_atomics": blocks,
        "atomic_reduction_ratio": elements / blocks,
        "v1_shared_reduction_steps_per_block": shared_steps,
        "v1_barriers_per_block_approx": shared_steps,
        "v2_warp_shuffle_rounds": 5,
        "v2_warp_partial_values_per_block": warps_per_block,
        "minimum_input_bytes": elements * 4,
        "warning": "这是操作数量模型，不是 GPU 性能预测。",
    }

def main():
    parser = argparse.ArgumentParser(description="CUDA Reduction 成本模型")
    parser.add_argument("--elements", type=int, default=4_194_304)
    parser.add_argument("--blocks", type=int, default=256)
    parser.add_argument("--block-size", type=int, default=256)
    parser.add_argument("--output", default="reports/cost_model.json")
    args = parser.parse_args()

    result = estimate(args.elements, args.blocks, args.block_size)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

if __name__ == "__main__":
    main()
```

运行命令：

```bash
mkdir -p reports
python reduction_cost_model.py
python reduction_cost_model.py --elements 16777216 --blocks 512 --block-size 256
```

默认配置中，全局原子操作从约 419 万次降到 256 次，数量模型会给出很大的缩减比。但这只是提出了「原子争用可能是主要瓶颈」的假设，它没有计算内存层级、原子吞吐、Warp 调度、频率或编译器生成代码。

两组实跑输出：

| 配置 | baseline atomics | optimized atomics | 缩减比 | V1 归约步数/Barrier | V2 Shuffle 轮数 | V2 warp partial | 最小输入字节 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 默认（4194304 / 256 / 256） | 4194304 | 256 | 16384 | 8 | 5 | 8 | 16777216 |
| 16777216 / 512 / 256 | 16777216 | 512 | 32768 | 8 | 5 | 8 | 67108864 |

模型能直接给出的可证伪假设是：V1 与 V2 的全局原子次数相同（都等于 blocks），因此**两者的差异不可能来自全局原子争用**，只能来自 Shared Memory 访问、Barrier 次数与指令依赖。若实测 V2 明显快于 V1，就应在 Nsight Compute 里看到 Barrier / Shared Memory 相关指标下降，而不是 DRAM 流量下降。

## 6. Level 1：通用 CUDA C++ Reduction

### 6.1 环境检测

```bash
mkdir -p reports
{
  date -Iseconds
  uname -a
  nvidia-smi -L
  nvidia-smi --query-gpu=name,driver_version,memory.total,pci.bus_id,pstate,temperature.gpu,power.limit --format=csv
  nvcc --version
  nsys --version 2>/dev/null || true
  ncu --version 2>/dev/null || true
} 2>&1 | tee reports/environment.txt
```

### 6.2 完整代码

保存为 `reduction_benchmark.cu`：

```cuda
#include <cuda_runtime.h>

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <numeric>
#include <stdexcept>
#include <string>
#include <vector>

#define CUDA_CHECK(call)                                                     \
  do {                                                                       \
    cudaError_t error__ = (call);                                            \
    if (error__ != cudaSuccess) {                                            \
      std::cerr << "CUDA error: " << cudaGetErrorString(error__)            \
                << " at " << __FILE__ << ":" << __LINE__ << std::endl;     \
      std::exit(EXIT_FAILURE);                                               \
    }                                                                        \
  } while (0)

__global__ void reduce_atomic_baseline(const float* x, float* output, int n) {
  int index = blockIdx.x * blockDim.x + threadIdx.x;
  int stride = blockDim.x * gridDim.x;
  for (int i = index; i < n; i += stride) {
    atomicAdd(output, x[i]);
  }
}

__global__ void reduce_shared_v1(const float* x, float* output, int n) {
  extern __shared__ float shared[];
  int tid = threadIdx.x;
  int index = blockIdx.x * blockDim.x + tid;
  int stride = blockDim.x * gridDim.x;

  float local = 0.0f;
  for (int i = index; i < n; i += stride) {
    local += x[i];
  }
  shared[tid] = local;
  __syncthreads();

  for (int offset = blockDim.x / 2; offset > 0; offset >>= 1) {
    if (tid < offset) {
      shared[tid] += shared[tid + offset];
    }
    __syncthreads();
  }

  if (tid == 0) {
    atomicAdd(output, shared[0]);
  }
}

__inline__ __device__ float warp_sum(float value) {
  for (int offset = 16; offset > 0; offset >>= 1) {
    value += __shfl_down_sync(0xffffffffu, value, offset);
  }
  return value;
}

__global__ void reduce_warp_v2(const float* x, float* output, int n) {
  __shared__ float warp_sums[32];
  int tid = threadIdx.x;
  int lane = tid & 31;
  int warp_id = tid >> 5;
  int warp_count = (blockDim.x + 31) / 32;
  int index = blockIdx.x * blockDim.x + tid;
  int stride = blockDim.x * gridDim.x;

  float local = 0.0f;
  for (int i = index; i < n; i += stride) {
    local += x[i];
  }
  local = warp_sum(local);

  if (lane == 0) {
    warp_sums[warp_id] = local;
  }
  __syncthreads();

  if (warp_id == 0) {
    float block_value = lane < warp_count ? warp_sums[lane] : 0.0f;
    block_value = warp_sum(block_value);
    if (lane == 0) {
      atomicAdd(output, block_value);
    }
  }
}

struct Stats {
  float p50_ms;
  float p95_ms;
  float min_ms;
  float max_ms;
  float result;
};

float percentile(std::vector<float> values, double q) {
  std::sort(values.begin(), values.end());
  double position = (values.size() - 1) * q;
  size_t lower = static_cast<size_t>(std::floor(position));
  size_t upper = static_cast<size_t>(std::ceil(position));
  if (lower == upper) return values[lower];
  double weight = position - lower;
  return static_cast<float>(values[lower] * (1.0 - weight) + values[upper] * weight);
}

template <typename Launcher>
Stats benchmark(Launcher launch, float* d_output, int warmup, int iterations) {
  for (int i = 0; i < warmup; ++i) {
    CUDA_CHECK(cudaMemset(d_output, 0, sizeof(float)));
    launch();
  }
  CUDA_CHECK(cudaGetLastError());
  CUDA_CHECK(cudaDeviceSynchronize());

  cudaEvent_t start, stop;
  CUDA_CHECK(cudaEventCreate(&start));
  CUDA_CHECK(cudaEventCreate(&stop));
  std::vector<float> samples;
  samples.reserve(iterations);

  for (int i = 0; i < iterations; ++i) {
    CUDA_CHECK(cudaMemset(d_output, 0, sizeof(float)));
    CUDA_CHECK(cudaEventRecord(start));
    launch();
    CUDA_CHECK(cudaEventRecord(stop));
    CUDA_CHECK(cudaEventSynchronize(stop));
    CUDA_CHECK(cudaGetLastError());
    float elapsed = 0.0f;
    CUDA_CHECK(cudaEventElapsedTime(&elapsed, start, stop));
    samples.push_back(elapsed);
  }

  float result = 0.0f;
  CUDA_CHECK(cudaMemcpy(&result, d_output, sizeof(float), cudaMemcpyDeviceToHost));
  CUDA_CHECK(cudaEventDestroy(start));
  CUDA_CHECK(cudaEventDestroy(stop));

  std::vector<float> sorted = samples;
  std::sort(sorted.begin(), sorted.end());
  return {percentile(samples, 0.50), percentile(samples, 0.95),
          sorted.front(), sorted.back(), result};
}

void print_stats(const std::string& name, const Stats& stats, size_t elements,
                 float expected) {
  double effective_gbps = (elements * sizeof(float)) / (stats.p50_ms * 1e6);
  double relative_error = std::abs(stats.result - expected) / std::max(1.0f, expected);
  std::cout << std::left << std::setw(18) << name
            << " p50=" << std::setw(9) << stats.p50_ms
            << " p95=" << std::setw(9) << stats.p95_ms
            << " min=" << std::setw(9) << stats.min_ms
            << " max=" << std::setw(9) << stats.max_ms
            << " effective_GB/s=" << std::setw(9) << effective_gbps
            << " result=" << stats.result
            << " rel_error=" << relative_error << '\n';
  if (relative_error > 1e-4) {
    throw std::runtime_error(name + " correctness check failed");
  }
}

int main(int argc, char** argv) {
  size_t elements = 1u << 22;
  int block_size = 256;
  int blocks = 256;
  int warmup = 10;
  int iterations = 50;

  for (int i = 1; i < argc; ++i) {
    std::string arg = argv[i];
    if (arg == "--elements" && i + 1 < argc) elements = std::stoull(argv[++i]);
    else if (arg == "--block" && i + 1 < argc) block_size = std::stoi(argv[++i]);
    else if (arg == "--blocks" && i + 1 < argc) blocks = std::stoi(argv[++i]);
    else if (arg == "--warmup" && i + 1 < argc) warmup = std::stoi(argv[++i]);
    else if (arg == "--iters" && i + 1 < argc) iterations = std::stoi(argv[++i]);
    else {
      std::cerr << "Usage: " << argv[0]
                << " [--elements N] [--block N] [--blocks N]"
                << " [--warmup N] [--iters N]\n";
      return EXIT_FAILURE;
    }
  }

  if (elements == 0 || blocks <= 0 || warmup <= 0 || iterations <= 0 ||
      block_size < 32 || block_size > 1024 || block_size % 32 != 0 ||
      (block_size & (block_size - 1)) != 0) {
    std::cerr << "Invalid arguments: block must be a power of two, a multiple of 32, and <= 1024.\n";
    return EXIT_FAILURE;
  }

  int device = 0;
  cudaDeviceProp props{};
  CUDA_CHECK(cudaGetDevice(&device));
  CUDA_CHECK(cudaGetDeviceProperties(&props, device));
  std::cout << "GPU=" << props.name
            << " compute_capability=" << props.major << "." << props.minor
            << " global_memory_GiB=" << props.totalGlobalMem / double(1ull << 30)
            << " SMs=" << props.multiProcessorCount << '\n';
  std::cout << "elements=" << elements << " blocks=" << blocks
            << " block_size=" << block_size << " warmup=" << warmup
            << " iterations=" << iterations << '\n';

  if (elements > static_cast<size_t>(std::numeric_limits<int>::max())) {
    std::cerr << "This teaching implementation requires elements <= INT_MAX.\n";
    return EXIT_FAILURE;
  }

  std::vector<float> host(elements, 1.0f);
  float expected = static_cast<float>(elements);
  float* d_input = nullptr;
  float* d_output = nullptr;
  CUDA_CHECK(cudaMalloc(&d_input, elements * sizeof(float)));
  CUDA_CHECK(cudaMalloc(&d_output, sizeof(float)));
  CUDA_CHECK(cudaMemcpy(d_input, host.data(), elements * sizeof(float), cudaMemcpyHostToDevice));

  auto baseline = benchmark(
      [&] { reduce_atomic_baseline<<<blocks, block_size>>>(d_input, d_output, static_cast<int>(elements)); },
      d_output, warmup, iterations);
  auto shared = benchmark(
      [&] { reduce_shared_v1<<<blocks, block_size, block_size * sizeof(float)>>>(
                d_input, d_output, static_cast<int>(elements)); },
      d_output, warmup, iterations);
  auto warp = benchmark(
      [&] { reduce_warp_v2<<<blocks, block_size>>>(d_input, d_output, static_cast<int>(elements)); },
      d_output, warmup, iterations);

  print_stats("atomic_baseline", baseline, elements, expected);
  print_stats("shared_v1", shared, elements, expected);
  print_stats("warp_v2", warp, elements, expected);
  std::cout << "speedup_shared=" << baseline.p50_ms / shared.p50_ms
            << " speedup_warp=" << baseline.p50_ms / warp.p50_ms
            << " warp_vs_shared=" << shared.p50_ms / warp.p50_ms << '\n';

  CUDA_CHECK(cudaFree(d_input));
  CUDA_CHECK(cudaFree(d_output));
  return EXIT_SUCCESS;
}
```

代码里有几处刻意的设计，读的时候要能指认出来：

- **计时用 CUDA Event 而不是 `std::chrono`**：`cudaEventRecord(start)` → `launch()` → `cudaEventRecord(stop)` → `cudaEventSynchronize(stop)`，测到的是设备侧执行时间。
- **`cudaMemset` 放在 Event 之外**：清零输出属于准备工作，不应计入 Kernel 时间；但它仍在同一 Stream 上串行执行，因此不会与上一次 Kernel 重叠。
- **V1 用动态 Shared Memory**（`extern __shared__`），启动时第三个参数传 `block_size * sizeof(float)`；V2 用静态 `__shared__ float warp_sums[32]`，只需 128 字节。
- **`warp_sum` 使用全掩码 `0xffffffffu`**：要求 Warp 内 32 条 lane 全部活跃，因此 `block_size` 必须是 32 的倍数（参数校验已强制），否则掩码与实际活跃 lane 不一致会导致未定义行为。
- **V2 的第二次 `warp_sum` 只在 `warp_id == 0` 内执行**：该 Warp 的 32 条 lane 全部进入分支，掩码依然成立；`lane < warp_count` 之外的 lane 补 0，不影响结果。

### 6.3 编译命令

通用编译：

```bash
nvcc -O3 -lineinfo -std=c++17 reduction_benchmark.cu -o reduction_benchmark
```

指定常见架构时，选择当前机器对应的一项，不要把多项全部硬编码为唯一方案：

```bash
# RTX 3080/3090
nvcc -O3 -lineinfo -std=c++17 -arch=sm_86 reduction_benchmark.cu -o reduction_benchmark

# RTX 4090 / L40 / L40S
nvcc -O3 -lineinfo -std=c++17 -arch=sm_89 reduction_benchmark.cu -o reduction_benchmark

# H100/H200
nvcc -O3 -lineinfo -std=c++17 -arch=sm_90 reduction_benchmark.cu -o reduction_benchmark
```

`-lineinfo` 用于让 Nsight Compute 把指标映射回源码行，做 Kernel 级分析时建议保留。Blackwell 的具体 `sm_` 目标必须以当前 GPU 的 Compute Capability 与已安装 CUDA Toolkit 支持为准。工具链过旧时应升级隔离环境或使用 PTX 兼容路径，不能把编译失败解释为硬件不支持 Reduction。

### 6.4 运行命令

```bash
./reduction_benchmark
./reduction_benchmark --elements 1048576 --block 256 --blocks 128
./reduction_benchmark --elements 4194304 --block 256 --blocks 256
./reduction_benchmark --elements 16777216 --block 256 --blocks 512
```

扫描 Block Size：

```bash
for block in 64 128 256 512 1024; do
  ./reduction_benchmark --elements 4194304 --block "$block" --blocks 256
done | tee reports/block_sweep.txt
```

扫描 Block 数：

```bash
for blocks in 32 64 128 256 512 1024; do
  ./reduction_benchmark --elements 4194304 --block 256 --blocks "$blocks"
done | tee reports/grid_sweep.txt
```

### 6.5 预期现象

- Baseline 会执行约 $N$ 次全局原子操作，通常明显慢于 V1/V2。
- V1/V2 每个 Block 只执行一次全局原子操作。
- V2 减少 Shared Memory 归约步骤与 Block 级同步，常有进一步收益，但收益不保证。
- Block 太小可能无法提供足够并行度，太大可能增加资源压力或降低调度灵活性。
- 输入很小时，三种 Kernel 的差距会缩小，启动开销占比上升。
- 性能数字只能作为本机实测，不得复制为所有 GPU 的结论。

Grid 扫描还有一条容易忽略的规律：`blocks` 增大会同时带来两个相反效果——并行度提高（更多 SM 参与读输入），但全局原子次数也线性增加（$N_{atomic}=N_{blocks}$）。因此存在一个最优 `blocks`，通常落在「SM 数 × 每 SM 可驻留 Block 数」附近，而不是越大越好。扫描结果应能观察到先降后升的 U 形曲线。

## 7. 正确性分析

### 7.1 为什么输入使用全 1

全 1 输入让 Reference 等于 $N$，便于快速检查。但浮点加法不满足严格结合律，不同归约顺序可能产生不同舍入误差。正式项目还需要加入随机输入，并用 CPU Double Accumulation 作为 Reference。

### 7.2 全 1 输入的精度陷阱

FP32 只有 24 位有效位，能精确表示的整数上限是 $2^{24} = 16777216$。Baseline 每次原子加的都是 `1.0f`，当全局累加值达到 $2^{24}$ 后，再加 1 会因舍入而不再变化——求和停滞。此时：

- $N$ 略大于 $2^{24}$：相对误差仍小于 `1e-4` 容差，检查「通过」，但结果已经失真。
- $N$ 达到 $2^{25}$ 量级：相对误差约 0.5，`print_stats` 抛出 `correctness check failed`。

V1/V2 反而不受影响：线程局部先累加 $N/(N_{blocks} \cdot block\_size)$ 个 1，Block 内归约后参与全局原子的加数已是较大的整数（如 65536），次数只有 `blocks` 次，在远超 $2^{24}$ 的规模下仍保持精确。

这条陷阱的意义在于：**正确性检查失败不一定是优化写错了，也可能是参考值与精度策略不匹配**。因此报告中必须写清输入分布、Reference 的计算精度与容差来源，而不是把容差一路放宽到「总能通过」。

### 7.3 随机输入扩展

将

```cuda
std::vector<float> host(elements, 1.0f);
float expected = static_cast<float>(elements);
```

替换为固定种子的随机数据，并在 CPU 用 Double 计算：

```cuda
#include <random>

std::mt19937 rng(2026);
std::uniform_real_distribution<float> distribution(-1.0f, 1.0f);
std::vector<float> host(elements);
for (float& value : host) value = distribution(rng);
double reference = std::accumulate(host.begin(), host.end(), 0.0);
float expected = static_cast<float>(reference);
```

`std::accumulate(..., 0.0)` 的初值是 `double`，因此整个累加在双精度下进行，这是关键；若写成 `0.0f` 就退化为单精度，Reference 本身失去意义。随机输入下正负项相互抵消，`expected` 可能接近 0，此时 `std::max(1.0f, expected)` 的归一化方式会把相对误差压小，应改用绝对误差与相对误差双阈值，并在报告里记录容差依据。

## 8. Nsight Systems：确认 Kernel 边界

```bash
nsys profile \
  --trace=cuda,nvtx,osrt \
  --sample=none \
  --cpuctxsw=none \
  --force-overwrite=true \
  --output=reports/reduction_nsys \
  ./reduction_benchmark --elements 4194304 --block 256 --blocks 256 --warmup 2 --iters 5

nsys stats reports/reduction_nsys.nsys-rep \
  | tee reports/reduction_nsys_stats.txt
```

检查：三个 Kernel 名称与调用次数是否符合预期；`cudaMemset` 是否被错误计入 Kernel 计时；是否出现频繁同步或异常长的 CUDA API；Kernel 很短时 Launch 开销是否开始主导；Profile 运行与纯 Benchmark 运行的时间差异。

调用次数可以直接核对：`warmup=2, iters=5` 时每个 Kernel 应出现 7 次，`cudaMemset` 也是 7 次。若数量对不上，说明采集窗口或参数与预期不一致，此时的指标不能用于结论。

## 9. Nsight Compute：验证优化原因

先用 Kernel 名称过滤，避免对所有 Warmup 与全部 Kernel 采集完整指标：

```bash
ncu \
  --kernel-name regex:reduce_atomic_baseline \
  --launch-count 1 \
  --section SpeedOfLight \
  --section MemoryWorkloadAnalysis \
  --section LaunchStats \
  --section Occupancy \
  --force-overwrite \
  --export reports/ncu_atomic \
  ./reduction_benchmark --warmup 1 --iters 1

ncu \
  --kernel-name regex:reduce_warp_v2 \
  --launch-count 1 \
  --section SpeedOfLight \
  --section MemoryWorkloadAnalysis \
  --section LaunchStats \
  --section Occupancy \
  --force-overwrite \
  --export reports/ncu_warp \
  ./reduction_benchmark --warmup 1 --iters 1
```

重点对比：

| 指标方向 | Baseline 假设 | V2 假设 |
| --- | --- | --- |
| 全局原子相关 Stall | 高 | 显著减少 |
| Kernel Duration | 长 | 下降 |
| DRAM Read | 读取相同输入 | 大体相近 |
| Shared Memory | 很少 | 仅 Warp Partial |
| Barrier | 很少 | 一个 Block 级 Barrier |
| Occupancy | 不一定低 | 不一定更高 |

不要先写结论再挑指标。若报告显示原子不是主要瓶颈，应回到工作负载规模、编译代码、Kernel 过滤与 GPU 原子实现重新分析。现代 GPU 的全局原子在 L2 侧有专用单元，同一地址的争用会被合并与流水化，因此「$N$ 次原子」不一定线性地转化为 $N$ 倍时间——这正是数量模型不能当性能预测的原因。

## 10. Level 2：架构专项可选实验

### 10.1 能力检测

```bash
nvidia-smi --query-gpu=name,compute_cap --format=csv
nvcc --list-gpu-arch
./reduction_benchmark --elements 4194304
```

### 10.2 Ampere：RTX 3080/3090、A100

- 使用 `sm_86` 或 `sm_80` 分别构建，不能混为同一设备。
- 比较 V1 与 V2，观察 Warp Shuffle 减少同步后的收益。
- 双 RTX 3080 不需要参与本单 Kernel 实验，使用 `CUDA_VISIBLE_DEVICES=0` 固定单卡。
- 消费卡没有 A100 的 HBM、NVLink/NVSwitch 与数据中心特性。

### 10.3 Ada Lovelace：RTX 4090、L40/L40S

- 使用 `sm_89`。
- 保持相同输入与编译参数才能和 Ampere 做架构对照。
- RTX 4090 属于 Ada，不属于 Blackwell。

### 10.4 Hopper：H100/H200

- 基础 Reduction 仍使用同一通用代码。
- 可选研究 Cooperative Groups、异步事务与 Cluster，但必须单独实现并验证。
- FP8 与 Transformer Engine 不会自动让 FP32 Reduction 变快。

### 10.5 Blackwell：RTX 5090、B100/B200/GB200

- 使用当前 Toolkit 支持的准确 Compute Capability。
- 可选研究 Thread Block Cluster、Distributed Shared Memory 或更新的异步流水。
- FP4、TMA、Cluster 是不同优化维度，不能把通用 Warp Shuffle 结果包装成这些特性的验证。
- RTX 5090 与 B200/GB200 的显存、互联与数据中心能力不同。

## 11. 优化前后对照与结论写法

填写本机真实结果：

| 实现 | P50 | P95 | 有效输入带宽 | 全局原子次数 | 正确性 | 主要瓶颈 |
| --- | --- | --- | --- | --- | --- | --- |
| atomic baseline | 待测 | 待测 | 待测 | 约 $N$ | 通过/失败 | 待分析 |
| shared V1 | 待测 | 待测 | 待测 | 约 Blocks | 通过/失败 | 待分析 |
| warp V2 | 待测 | 待测 | 待测 | 约 Blocks | 通过/失败 | 待分析 |

一份合格结论应同时包含以下六项，缺一项就不算完成：

1. **环境与配置**：GPU 型号、Compute Capability、驱动、CUDA Toolkit、编译参数、`elements/blocks/block_size/warmup/iters`。
2. **分布而非单点**：三个实现各自的 P50/P95/min/max，以及 `speedup_shared`、`speedup_warp`、`warp_vs_shared`。
3. **正确性证据**：输入分布、Reference 精度、容差与实测 `rel_error`。
4. **机理解释**：用 Nsight Systems 的 Kernel 边界与 Nsight Compute 的 Stall/内存/Barrier 指标说明「为什么快」，而不是只说「原子少了」。
5. **边界扫描**：至少两组 `elements`、一组 Block Size 扫描、一组 Grid 扫描，指出加速比在哪些区间成立、在哪里消失。
6. **不可外推声明**：明确哪些结论只适用于本机本规模，哪些是模型推断（如 Level 0 的原子缩减比），哪些架构特性根本没有验证。

反面例子是「Warp Shuffle 比 Shared Memory 快 1.8 倍，所以 V2 是最优实现」——没有环境、没有分布、没有正确性、没有指标支撑，也没有说明在什么规模下成立。事实上输入很小时三者差距会被 Launch 开销抹平，`blocks` 很大时全局原子又会重新成为瓶颈，V2 并非在所有配置下都最优。

## 写在最后

Reduction 是最小的「协作成本」样本：算法工作量没变，只是把百万次全局协作换成数百次，性能就发生数量级变化。下一个项目把同样的方法用到完整训练流程上，瓶颈从单个 Kernel 扩展到数据流水线、通信与显存。

下一篇：[PyTorch 训练性能优化](/source/AI-Infra/2-AI系统性能工程/31-PyTorch训练性能优化)。
