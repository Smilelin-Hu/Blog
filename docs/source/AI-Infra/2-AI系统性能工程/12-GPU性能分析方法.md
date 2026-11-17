# GPU 性能分析方法

本篇建立从基准测量到 Nsight 分析的标准流程，把「感觉慢」转化为可验证的瓶颈假设。

性能优化最危险的状态，不是不会写 CUDA，而是拿到一个「GPU 利用率 95%」就开始改 Kernel。这个数字可能只表示采样窗口内 GPU 经常有任务在运行，并不等于 Tensor Core 接近峰值、不等于显存带宽已打满，更不等于业务 Goodput 达标。

## 1. 内容概览

- 带版本、输入、预热、重复次数与噪声统计的性能基线。
- Host Wall Time、CUDA Event Time 与 Profiler Timeline 的区别。
- Nsight Systems 的时间线下钻与 Nsight Compute 的 Kernel 计数器。
- 为什么 GPU Util、Occupancy、单个 Counter 都不能独立证明性能良好。
- NVTX 业务语义标注与 Amdahl 上限估算。
- 异步计时、冷启动、Profiler Replay、频率波动造成的伪结论。

工具链的层次关系：

![ai2-12-L18](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l12_01.png)

## 2. 核心直觉：Profiler 是显微镜，不是判决书

Profiler 提供证据，但证据必须放在正确的问题里解释。

假设一个训练 Step 需要 100 ms：数据输入 20 ms、CPU 调度与 Kernel Launch 15 ms、GPU Kernel 50 ms、AllReduce 与同步 15 ms。如果只盯着最慢的 10 ms Kernel 并把它优化 2 倍，Step 也只是从 100 ms 降到 95 ms。反过来，如果许多小 Kernel 之间存在 15 ms CPU Gap，Kernel Fusion、CUDA Graph 或减少 Python Dispatch 可能比手写单个 Kernel 更有效。

因此分析顺序必须是：业务是否真的慢 → 慢在哪个阶段 → 哪些阶段位于 Critical Path → 热点 Kernel 为什么慢 → 修改后端到端指标是否改善。

## 3. 性能分析的六步方法

### 3.1 定义目标

训练系统常见目标：Step Time、Samples/s、Tokens/s；MFU、Goodput；每次有效训练更新的成本；Checkpoint 或故障导致的吞吐损失。

推理系统常见目标：TTFT、TPOT、ITL、E2E Latency；Request/s、Output Tokens/s；满足 P99 SLO 的 Goodput；单位 Token 成本。

不要用「GPU Util 越高越好」代替业务目标——一个死循环 Kernel 可以制造很高的 GPU Util，却没有任何 Goodput。

### 3.2 固定实验条件

| 类别 | 需要记录的内容 |
| --- | --- |
| 软件 | OS、Driver、CUDA、cuDNN/NCCL、框架与依赖版本 |
| 硬件 | GPU 型号、数量、Compute Capability、显存、互联与 CPU/NUMA |
| 工作负载 | 模型、精度、Batch、Shape、序列长度、输入分布 |
| 运行状态 | 功耗/温度、时钟、后台任务、MIG、容器与 CPU Affinity |
| 测量协议 | 预热次数、正式重复次数、同步点、统计方法 |

性能对比必须保证正确性与输入等价。若「优化版」少算了一部分、改变精度或偷偷减小 Batch，速度提升没有意义。

### 3.3 先建立端到端基线

至少输出 Median、P95/P99、最小值与最大值、变异系数 CV、正确性误差、吞吐或业务 Goodput。若重复时间为 $t_1,\dots,t_n$，均值 $\mu$、标准差 $\sigma$：

$$
CV = \frac{\sigma}{\mu}
$$

CV 很高说明实验不稳定，此时先控制环境、增加单次工作量或延长测量时间，不要急着宣称 3% 的提升。

### 3.4 从系统时间线下钻

先用 Nsight Systems 看：CPU 是否及时提交工作；CUDA API 是否被同步调用阻塞；Kernel 之间是否有空洞；H2D/D2H 是否与计算重叠；多 Stream 是否真正并行；NCCL 是否位于 Critical Path；哪些 NVTX 阶段占时最多；哪些 Kernel 值得进一步分析。再用 Nsight Compute 分析少数代表性 Kernel，不要一开始就对整个训练任务采集 `--set full`。

### 3.5 形成可证伪假设

好的假设包含证据、机制与预测，例如「Kernel A 的 DRAM 吞吐已达稳定带宽的 92%，而 L2 命中很低；把 AoS 改为 SoA 后事务数应下降约 4 倍，Step Time 预计下降 6%」。坏的假设只有工具提示，例如「Occupancy 低，所以提高 Occupancy」。Occupancy 低可能由寄存器、Shared Memory、Block 数、尾部波次或算法本身导致；更高 Occupancy 还可能降低每线程资源并拖慢 Kernel。

### 3.6 一次只改一个主要变量

同时改 Batch、精度、DataLoader、Kernel 与编译选项，速度即使提升也无法归因。工程上可以最终组合多项优化，但验证阶段应保留可解释的增量对照。

## 4. 端到端时间模型

完全串行的简化系统中：

$$
T_{step} = T_{input} + T_{cpu} + T_{h2d} + T_{kernel} + T_{comm} + T_{sync} + T_{io}
$$

实际系统通常存在重叠，不能机械相加。真正决定端到端时间的是依赖图上的 Critical Path：

$$
T_{step} = \max_{p \in Paths} \sum_{i \in p} T_i
$$

这解释了两个常见现象：某个 Memcpy 占用 5 ms 但完全隐藏在 20 ms Kernel 后面，单独优化它不一定缩短 Step；某个 1 ms 同步点让后续所有工作等待，它可能比 5 ms 的非关键任务更值得优化。

**Amdahl 定律**：可优化部分占原总时间比例 $p$、局部加速倍数 $s$，则

$$
Speedup_{total} = \frac{1}{(1-p) + \frac{p}{s}}
$$

热点只占 10% 时，即使把它变成零成本，整体也最多 $1/(1-0.1)=1.11\times$。先算上限，再决定是否投入开发时间。

## 5. Kernel 性能模型

**有效带宽**：Kernel 读写总数据量 $B_{useful}$、执行时间 $t$，则 $BW_{effective}=B_{useful}/t$。对 `out = x + y * z` 的 FP32 元素操作，至少读 `x/y/z` 并写 `out`：

$$
B_{useful} = N \times (3+1) \times 4\ \text{bytes}
$$

基线若先产生临时张量再执行加法，会多一次写临时结果与一次读临时结果。Fusion 的收益往往来自减少 Kernel Launch 与 Global Memory Round Trip，而不是增加 FLOPs。有效带宽应与同一机器、相近访问模式下测得的稳定带宽比较，而不是直接除以规格表理想峰值。

**Arithmetic Intensity 与 Roofline**：

$$
AI = \frac{FLOPs}{Bytes_{DRAM}}, \qquad P \le \min(P_{peak},\ AI \times BW_{memory})
$$

测量点贴近 Memory Roof 时，继续减少算术指令帮助有限，应减少数据流量、改善访问模式或提高复用；贴近 Compute Roof 时，应关注 Tensor Core、指令吞吐、流水线与数值精度。

**Occupancy 与延迟隐藏**：

$$
Occupancy = \frac{\text{Active Warps per SM}}{\text{Maximum Warps per SM}}
$$

它是「可驻留 Warp 数比例」，不是「算力利用率」，价值在于帮助隐藏 Memory/Execution Latency。较低 Occupancy 可能是瓶颈，但较高 Occupancy 不保证更快：Kernel 可能有足够的 Instruction-Level Parallelism；增加 Block 可能导致寄存器压缩与 Spill；更多 Warp 可能争抢 Cache、Shared Memory 或带宽；Tail Effect 可能使平均 Occupancy 看似低。

## 6. 工具分工：每把尺子测不同问题

| 工具 | 主要回答 | 不应被误用为 |
| --- | --- | --- |
| 应用日志/压测器 | SLO、Goodput、业务吞吐 | Kernel 根因分析 |
| `nvidia-smi` | 温度、功耗、显存、粗粒度活动 | MFU、精确 Kernel 利用率 |
| DCGM | 集群长期遥测、健康与作业统计 | 单条指令级分析 |
| CUDA Event | 某 Stream 上 GPU 工作耗时 | 端到端 Host Latency |
| `torch.utils.benchmark` | 有预热、重复与同步的微基准 | 完整分布式时间线 |
| NVTX | 给时间线添加业务语义 | 自动给出优化答案 |
| Nsight Systems | CPU/GPU/通信的端到端时间线 | 所有 Kernel 计数器深挖 |
| Nsight Compute | 单个 Kernel 的硬件计数器与分析 | 长任务全量追踪 |
| Compute Sanitizer | 越界、竞态、未初始化与同步错误 | 性能测量工具 |

采样型 GPU Utilization 通常反映一个时间窗口内 Graphics/Compute Engine 是否忙，它不能告诉：SM 是否主要在等待 Memory、Tensor Core 是否被使用、有多少运算对业务有效、Kernel 是否在做冗余工作、P99 是否满足 SLO。因此它适合发现「GPU 长时间完全空闲」「显存异常增长」「温度导致降频」，不适合单独证明优化成功。

## 7. Nsight Systems：先找时间去哪了

重点观察五类行：**GPU Row**（是否有大段空白，Kernel/Memcpy/NCCL 是否重叠）、**CUDA API Row**（`cudaDeviceSynchronize`、`cudaStreamSynchronize`、Allocation 是否频繁阻塞）、**CPU Thread Row**（Python、DataLoader、锁、文件 I/O 与调度是否拖慢提交）、**NVTX Row**（Forward/Backward/Optimizer/Input/Checkpoint 阶段占比）、**CUDA HW/Memory**（依版本与硬件显示更细的吞吐信息）。

常用诊断树：

![GPU Idle Gap：先分「有空洞」与「持续忙」](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l12_02.png)

NVTX 用于把业务阶段映射到 CUDA 时间线：

```python
import torch.cuda.nvtx as nvtx

nvtx.range_push("forward")
out = model(x)
nvtx.range_pop()
```

## 8. Nsight Compute：解释单个 Kernel 为什么慢

推荐从较小的 Section Set 开始，逐步关注：**Speed Of Light**（SM 与 Memory 吞吐相对上限）、**Roofline**（算术强度与 Compute/Memory Roof）、**Memory Workload Analysis**（DRAM/L2/L1/Shared 流量、合并与命中）、**Scheduler / Warp State**（Eligible Warp、Issue、主要 Stall 原因）、**Occupancy**（寄存器、Shared Memory、Block/SM 限制）、**Source / SASS**（高代价指令与源码对应关系）。

```bash
ncu --set basic --kernel-name regex:gemm --launch-count 3 ./app
nsys profile -t cuda,nvtx,osrt -o step_timeline ./train.sh
```

不要把某一个 Stall 百分比直接当根因。Stall 指标需要结合 Scheduler 状态、并发 Warp、吞吐与源码解释；某类 Stall 高，有时只是另一个瓶颈的结果。Profiler 的 Replay 机制会多次重放 Kernel 以采集不同计数器组，因此采集态的墙钟时间不能当作业务延迟。

## 9. 正确计时：异步系统最容易骗人

错误示例——只包住异步提交：

```python
start = time.perf_counter()
out = torch.mm(a, b)          # 异步提交
elapsed = time.perf_counter() - start
```

这里主要测到 Python 调用与 Kernel Launch，而不是 GPU 完成时间。

**Host Wall Time**（含 Dispatch、GPU 执行与同步开销，适合端到端调用延迟）：

```python
torch.cuda.synchronize()
start = time.perf_counter()
out = torch.mm(a, b)
torch.cuda.synchronize()
elapsed = time.perf_counter() - start
```

**CUDA Event Time**（在 Stream 时间线上记录，适合测 GPU 工作区间）：

```python
start = torch.cuda.Event(enable_timing=True)
end = torch.cuda.Event(enable_timing=True)
start.record()
out = torch.mm(a, b)
end.record()
end.synchronize()
elapsed_ms = start.elapsed_time(end)
```

两种时间回答的问题不同，不能混为一谈。**预热不可省略**：首次运行可能包含 CUDA Context 创建、Module/Kernel Loading、JIT 编译、cuBLAS/cuDNN Heuristic 与 Workspace 建立、Memory Pool 扩容、Page Fault 与 Cache 冷启动。Cold Start 与 Steady State 都可能是业务指标，但必须分别测量和命名。

## 10. 可运行的分析实验

### 10.1 Level 0：无 GPU 的基线—优化对照

展示五件事：正确性、预热、重复测量、阶段分解与 Amdahl 上限。基线逐元素计算多项式之和，优化版使用等价闭式公式。保存为 `profile_cpu_lab.py`：

```python
#!/usr/bin/env python3
import argparse, json, math, platform, statistics, time

def percentile(values, q):
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return ordered[lo]
    return ordered[lo] * (hi - pos) + ordered[hi] * (pos - lo)

def summarize(samples_s):
    mean = statistics.fmean(samples_s)
    stdev = statistics.pstdev(samples_s)
    return {
        "median_ms": statistics.median(samples_s) * 1e3,
        "p95_ms": percentile(samples_s, 0.95) * 1e3,
        "min_ms": min(samples_s) * 1e3,
        "max_ms": max(samples_s) * 1e3,
        "cv_percent": 100.0 * stdev / mean if mean else 0.0,
    }

def baseline_once(n):
    t0 = time.perf_counter()
    values = list(range(n))
    t1 = time.perf_counter()
    total = 0
    for x in values:
        total += x * x + 3 * x + 7
    t2 = time.perf_counter()
    result = int(total)          # 模拟结果封装，而不是用 sleep 制造瓶颈
    t3 = time.perf_counter()
    return result, {"input_ms": (t1 - t0) * 1e3,
                    "compute_ms": (t2 - t1) * 1e3,
                    "finalize_ms": (t3 - t2) * 1e3}

def optimized_once(n):
    t0 = time.perf_counter()
    sum_x = n * (n - 1) // 2                 # sum(x)
    sum_x2 = n * (n - 1) * (2 * n - 1) // 6  # sum(x^2)
    result = sum_x2 + 3 * sum_x + 7 * n
    return result, {"closed_form_ms": (time.perf_counter() - t0) * 1e3}

def run_many(fn, n, repeat):
    samples, phase_totals, result = [], {}, None
    for _ in range(repeat):
        t0 = time.perf_counter()
        result, phases = fn(n)
        samples.append(time.perf_counter() - t0)
        for k, v in phases.items():
            phase_totals[k] = phase_totals.get(k, 0.0) + v
    return result, summarize(samples), {k: v / repeat for k, v in phase_totals.items()}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=300_000)
    p.add_argument("--warmup", type=int, default=2)
    p.add_argument("--repeat", type=int, default=9)
    a = p.parse_args()
    if a.n <= 0 or a.repeat < 3 or a.warmup < 0:
        raise SystemExit("要求 n > 0、repeat >= 3、warmup >= 0")

    expected, _ = optimized_once(a.n)
    actual, _ = baseline_once(a.n)
    if actual != expected:
        raise AssertionError(f"结果不一致：baseline={actual}, optimized={expected}")
    for _ in range(a.warmup):
        baseline_once(a.n); optimized_once(a.n)

    br, bs, bp = run_many(baseline_once, a.n, a.repeat)
    orr, os_, op = run_many(optimized_once, a.n, a.repeat)
    assert br == orr
    share = bp["compute_ms"] / sum(bp.values())
    report = {
        "environment": {"python": platform.python_version(), "platform": platform.platform()},
        "config": vars(a), "correctness": True,
        "baseline": {"stats": bs, "phase_mean_ms": bp},
        "optimized": {"stats": os_, "phase_mean_ms": op},
        "analysis": {
            "baseline_compute_share": share,
            "amdahl_speedup_if_compute_10x": 1.0 / ((1.0 - share) + share / 10.0),
            "measured_algorithmic_speedup": bs["median_ms"] / os_["median_ms"],
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

```bash
python3 profile_cpu_lab.py --n 300000 --warmup 2 --repeat 9
mkdir -p reports
python3 profile_cpu_lab.py --n 300000 --warmup 3 --repeat 15 \
  | tee reports/cpu_profile_baseline.json
```

预期现象：`correctness` 为 `true`；基线 `compute_ms` 通常占主导；闭式公式的 Median 显著更低；不同 CPU、Python 版本与系统负载会得到不同数值；CV 较高时应增加 `n` 或重复次数并检查后台任务。

这个实验故意展示「算法变化」而不是微优化：Profiler 先证明逐元素循环是热点，数学推导再消除整个循环。真实 GPU 优化同理——有时应改善 Kernel，有时应融合 Kernel，有时应改变算法或数据布局。`amdahl_speedup_if_compute_10x` 是在其他阶段不变假设下的上限；实际闭式公式也消除了输入列表构造，所以测得速度可能超过这个局部假设。这恰好提醒：Amdahl 的 $p$ 必须与真实修改边界一致。

### 10.2 Level 1：GPU 上的等价表达式对照

比较 `torch.mm` 与手写逐元素组合、Fusion 前后的有效带宽，以及 `torch.compile` 前后的 Kernel 数量：

```python
import torch, time

def bench(fn, warmup=10, iters=50):
    for _ in range(warmup):
        fn()
    torch.cuda.synchronize()
    s, e = torch.cuda.Event(True), torch.cuda.Event(True)
    s.record()
    for _ in range(iters):
        fn()
    e.record(); torch.cuda.synchronize()
    return s.elapsed_time(e) / iters

n = 1 << 24
x, y, z = (torch.randn(n, device="cuda") for _ in range(3))
naive = lambda: x + y * z
fused = torch.compile(lambda a, b, c: a + b * c)
ms_naive, ms_fused = bench(naive), bench(lambda: fused(x, y, z))
bytes_useful = n * 4 * 4
for name, ms in (("naive", ms_naive), ("fused", ms_fused)):
    print(name, round(ms, 3), "ms", round(bytes_useful / (ms / 1e3) / 1e9, 1), "GB/s")
```

记录时要同时保存：GPU 型号与 Driver、时钟与温度状态、输入 Shape 与 dtype、预热与重复次数、Median/P95/CV、正确性误差。只报一个「快了多少倍」而没有这些条件的结论，无法复现也无法回归。

## 写在最后

性能分析的价值不在于工具用了多少，而在于每个结论都能被复现与证伪：先定目标与基线，再看时间线找 Critical Path，最后才对少数热点下钻计数器。下一篇进入 Kernel Fusion 与高性能算子开发，把「减少 Round Trip」落到具体实现。

下一篇：[Kernel Fusion 与高性能算子开发](/source/AI-Infra/2-AI系统性能工程/13-KernelFusion与高性能算子开发)。