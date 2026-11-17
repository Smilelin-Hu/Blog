# AI Systems Performance Engineering 综合项目

本项目综合运用性能建模、GPU、分布式、编译器与推理系统知识，交付完整的 AI Systems Performance Engineering 优化方案。

这是整个系列的最终工程验收：选择一个真实训练或推理工作负载，从业务目标出发完成一次可复现的性能工程闭环——定义 SLO 与成本目标、建立可信基线、定位主瓶颈、提出可证伪假设、实施最小改动、验证正确性与收益、设计发布回滚，并交付完整证据包。

![ai2-36-L7](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l36_01.png)

本项目不要求具备相同 GPU。Level 0 使用纯 Python 完成方法和门禁；Level 1 在任意可用 NVIDIA GPU 上选择训练或推理工作负载；Level 2 仅在真实支持环境验证 NVLink/NVSwitch、RDMA、FP8/FP4、Transformer Engine、Disaggregated Inference 等专项能力。

## 1. 内容概览与交付物

做完之后应当能够：把性能问题翻译为业务 SLO、Goodput 和成本；建立环境、数据、模型、精度和工作量受控的基线；用系统、框架、Kernel 和分布式证据定位瓶颈；用 Roofline、排队论、通信模型与 Amdahl 定律建立预测；设计单变量、可重复、带正确性门禁的实验；同时报告 P50/P95/P99、吞吐、显存、错误率、能耗和成本；区分资料事实、模型推导、模拟结果和硬件实测；形成可发布、可回滚、可持续防回归的工程交付。

前置知识：前面全部主题与前七个综合项目；能使用至少一种 Profiler；能阅读训练或推理日志；对目标系统拥有合法的测试权限、模型/数据许可和隔离测试环境。

```text
capstone/
├── README.md
├── experiment.yaml
├── capstone_runner.py
├── baseline/
│   ├── environment.txt
│   ├── metrics.json
│   └── traces/
├── candidate/
│   ├── environment.txt
│   ├── metrics.json
│   └── traces/
├── reports/
│   ├── hypothesis_register.md
│   ├── comparison.md
│   ├── correctness.md
│   ├── cost_model.md
│   └── rollback.md
└── artifacts/
    └── commands.txt
```

交付物的组织方式本身就是结论的一部分：`baseline/` 与 `candidate/` 并列且结构相同，意味着两者用同一套口径采集；`reports/` 里五份文档分别对应假设、对比、正确性、成本与回滚，缺任何一份都说明闭环不完整；`artifacts/commands.txt` 保存可复现的完整命令。

## 2. 项目选题

从以下方向选择一个，不改变统一交付标准：

| 方向 | 示例目标 | 核心指标 |
| --- | --- | --- |
| 单 GPU 训练 | 提升稳态训练吞吐 | Step P95、Samples/s、显存、Loss |
| 多 GPU 训练 | 提升扩展效率 | Tokens/s、MFU、通信占比、慢 Rank |
| CUDA Kernel | 消除热点 | Kernel P50/P95、带宽、正确性 |
| 在线推理 | SLO 下最大 Goodput | TTFT、TPOT、P99、Token/s |
| KV Cache | 提升稳定并发容量 | KV Token、Preemption、P95 |
| P/D 解耦 | 降低干扰/成本 | Transfer、TTFT/TPOT、Goodput |
| MoE 推理 | 优化路由与 All-to-All | Expert Load、通信、Token/s |

七个方向对应前面七个项目，选题时可直接复用对应项目的脚本与报告结构。关键约束是「不改变统一交付标准」：无论选哪个方向，都必须有 Primary Metric、Guardrail、原始样本、正确性门禁与回滚方案。方向只影响指标名称，不影响证据要求。

## 3. 性能工程总模型

### 3.1 端到端延迟

$$
T_{end} = T_{queue} + T_{data} + T_{compute} + T_{memory} + T_{communication} + T_{runtime} + T_{sync}
$$

### 3.2 Goodput

$$
Goodput = Throughput \times SuccessRate \times SLOPassRate
$$

### 3.3 Roofline

$$
Performance \le \min(PeakCompute,\ Bandwidth \times ArithmeticIntensity)
$$

### 3.4 通信

$$
T_{comm} \approx \alpha N_{messages} + \frac{Bytes}{BW_{effective}}
$$

### 3.5 Amdahl

$$
S_{total} = \frac{1}{(1-p) + \frac{p}{S_{optimized}}}
$$

### 3.6 成本

$$
CostPerWork = \frac{InfrastructureCost + EnergyCost + FailureCost}{ValidWork}
$$

这些模型用于产生可验证预测。任何模型都必须与真实 Profile 对照，不能把公式结果直接写成硬件实测。

六个模型覆盖了性能工程的完整判断链：延迟分解回答「时间花在哪」，Roofline 回答「计算还是访存受限」，通信模型回答「多卡开销来自消息数还是字节数」，Amdahl 回答「局部优化能带来多少端到端收益」，Goodput 与成本回答「这个收益是否值得上线」。缺任何一个，结论都可能片面——例如只看 Roofline 会忽略排队，只看 Amdahl 会忽略正确性代价。

## 4. 阶段一：项目章程

项目开始前写清：

```yaml
project: example
owner: team
workload:
  type: training-or-inference
  model_revision: immutable-id
  dataset_revision: immutable-id
  precision: bf16
  input_distribution: fixed-and-versioned
slo:
  primary: "p95_step_ms <= target"
  secondary: "peak_memory_gib <= target"
correctness:
  metric: "loss-delta-or-output-match"
  threshold: 0.0
budget:
  max_gpu_hours: 0
  deadline: YYYY-MM-DD
```

必须有一个 Primary Metric 和至少两个 Guardrail。没有 Guardrail 的「更快」可能来自精度下降、丢请求、减少 Token、改变 Batch 或禁用必要功能。

章程里所有 revision 都写成不可变 ID，`input_distribution` 标注 fixed-and-versioned，这是后续所有对比的前提。`budget` 一栏常被省略，但它决定了实验规模：GPU 小时上限直接约束重复次数与扫描粒度，没有预算约束的性能工程容易陷入无限调参。

## 5. 阶段二：冻结工作负载与环境

### 5.1 环境快照

```bash
mkdir -p baseline candidate reports artifacts
{
  date -Iseconds
  uname -a
  lscpu
  free -h
  python --version
  nvidia-smi -L 2>/dev/null || true
  nvidia-smi topo -m 2>/dev/null || true
  nvidia-smi --query-gpu=name,driver_version,memory.total,pci.bus_id,pstate,power.limit --format=csv 2>/dev/null || true
  nvcc --version 2>/dev/null || true
  nsys --version 2>/dev/null || true
  ncu --version 2>/dev/null || true
  python -m pip freeze 2>/dev/null || true
} 2>&1 | tee baseline/environment.txt
```

还应保存 Git Commit、容器 Digest、模型 Revision、Tokenizer、数据 Hash、完整命令、环境变量、功耗/时钟策略和物理拓扑。

所有 GPU 相关命令都带 `2>/dev/null || true`，保证在没有 GPU 或没有 Profiler 的机器上快照依然完整——缺失项本身就是环境事实，比中断脚本更有价值。`lscpu` 与 `free -h` 不能省：数据加载与 Host 内存压力经常是 GPU 空洞的真实原因。

### 5.2 受控变量

- 相同请求/Token/样本工作量；
- 相同有效 Batch、序列长度和精度；
- 相同随机种子或可比较的数据分布；
- 相同正确性标准；
- 相同是否包含数据、日志、Checkpoint 和网络的计时边界；
- 相同机器、隔离和功耗条件；
- 只改变实验声明的变量。

第五条「计时边界」是最容易被忽略的混淆源。同一个训练脚本，把 Checkpoint 写盘算进 Step 时间与不算进去，可能差出数倍；把数据加载算进去与不算进去，结论可能完全相反。边界必须在章程里写死，并在两组实验中保持一致。

## 6. 阶段三：可信基线

基线至少包含：

1. Smoke Test：能运行并得到正确结果；
2. Warmup：排除初始化、Allocator、编译和连接建立；
3. 稳态：足够多的重复 Step/Request；
4. Tail：P95/P99 与错误率；
5. 容量：峰值显存、Host Memory、KV/Activation；
6. Profile：至少一个代表性窗口；
7. 重复：相同条件下 3～5 次独立运行。

性能数字必须保存原始样本，而不只保存平均值。

七项的顺序有意义：先证明正确，再排除冷启动，再取稳态，再看尾部与容量，最后才采 Profile。跳过 Warmup 直接测稳态会把编译与 Allocator 预热算进基线，让后续任何优化都显得「收益巨大」；只保存平均值则无法判断收益是否超过环境噪声。

「3～5 次独立运行」指的是重新启动进程、重新加载模型的独立运行，而不是同一进程内的重复迭代。前者才能暴露初始化差异、缓存状态与频率漂移。

## 7. 阶段四：瓶颈定位

### 7.1 从外到内

![ai2-36-L199](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l36_02.png)

### 7.2 工具选择

| 问题 | 工具 |
| --- | --- |
| CPU/GPU 时间线、Launch、空洞 | Nsight Systems |
| Kernel、Memory、Roofline | Nsight Compute |
| PyTorch Op、Shape、Memory | PyTorch Profiler |
| NCCL/多 Rank | NCCL 日志、nccl-tests、Trace |
| vLLM 服务 | 官方 Bench、服务日志、Prometheus |
| 正确性 | Unit/Golden/Convergence/Quality Eval |

不要把所有 Profiler 同时打开。采集本身有开销，应使用短窗口并保留无 Profiler 的最终 Benchmark。

「从外到内」的顺序是效率问题也是正确性问题。先看业务层能避免把排队误诊为 Kernel 慢；先看系统时间线能避免在 GPU 空闲时去优化 Kernel。Nsight Systems 与 Nsight Compute 的分工必须清楚：前者看全局时间线与空洞，后者用重放方式看单 Kernel 内部指标，两者的时间数字不可直接互相引用。

## 8. 阶段五：假设登记

保存为 `reports/hypothesis_register.md`：

| ID | 证据 | 假设 | 改动 | 预测 | Guardrail | 结果 |
| --- | --- | --- | --- | --- | --- | --- |
| H1 | GPU 空洞 20% | 数据供给不足 | Worker/Prefetch | P50 -10% | Loss/内存 | 待测 |
| H2 | Kernel Launch 密集 | Fusion 可减少开销 | Compile/Fusion | P50 -8% | 数值误差 | 待测 |
| H3 | NCCL 暴露 | Bucket/Overlap 不佳 | 调整重叠 | Step -12% | 峰值显存 | 待测 |

每个假设必须可证伪，并写出「如果没有收益，下一步检查什么」。

这张表的价值在于把「证据 → 假设 → 预测 → 结果」串成闭环。预测必须是具体数字而非「会变快」，因为只有这样失败时才能判断是假设错了还是实现错了。例如 H1 预测 P50 降 10%，若实测只降 1%，说明数据供给不是主瓶颈，应回到时间线重新定位，而不是继续加大 Prefetch。

Guardrail 列同样不可省略：H3 的通信重叠优化几乎必然抬高峰值显存，若只看 Step 时间就接受改动，可能在更长序列上触发 OOM。

## 9. Level 0：完整性能实验与回归门禁

### 9.1 capstone_runner.py

下面的纯 Python 程序提供一个可运行的参考实验：Baseline 对列表做多次中间分配，Candidate 将缩放和激活融合到一次遍历；两者完成相同的 RMS Normalization + SiLU 工作。程序执行热身、重复计时、正确性、P50/P95、吞吐、Goodput、Amdahl 端到端预测和自动门禁。

保存为 `capstone_runner.py`：

```python
#!/usr/bin/env python3
import argparse
import json
import math
import operator
import platform
import random
import statistics
import time
from pathlib import Path

def silu(value):
    return value / (1.0 + math.exp(-max(-60.0, min(60.0, value))))

def baseline(values, epsilon):
    squares = [value * value for value in values]
    mean_square = sum(squares) / len(squares)
    inverse_rms = 1.0 / math.sqrt(mean_square + epsilon)
    normalized = [value * inverse_rms for value in values]
    return [silu(value) for value in normalized]

def candidate(values, epsilon):
    mean_square = sum(map(operator.mul, values, values)) / len(values)
    inverse_rms = 1.0 / math.sqrt(mean_square + epsilon)
    return [silu(value * inverse_rms) for value in values]

def percentile(values, q):
    values = sorted(values)
    position = (len(values) - 1) * q
    low, high = math.floor(position), math.ceil(position)
    if low == high:
        return values[low]
    return values[low] * (high - position) + values[high] * (position - low)

def benchmark(function, values, epsilon, warmup, repeats):
    for _ in range(warmup):
        function(values, epsilon)
    samples = []
    output = None
    for _ in range(repeats):
        start = time.perf_counter()
        output = function(values, epsilon)
        samples.append(time.perf_counter() - start)
    return output, samples

def summarize(samples, elements):
    p50 = percentile(samples, 0.50)
    return {
        "p50_ms": p50 * 1000,
        "p95_ms": percentile(samples, 0.95) * 1000,
        "mean_ms": statistics.mean(samples) * 1000,
        "elements_per_second_at_p50": elements / p50,
        "raw_seconds": samples,
    }

def main():
    parser = argparse.ArgumentParser(description="AI 性能工程结课实验")
    parser.add_argument("--elements", type=int, default=200000)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--repeats", type=int, default=20)
    parser.add_argument("--epsilon", type=float, default=1e-6)
    parser.add_argument("--max-relative-error", type=float, default=1e-12)
    parser.add_argument("--max-regression", type=float, default=0.05)
    parser.add_argument("--target-speedup", type=float, default=1.0)
    parser.add_argument("--hotspot-fraction", type=float, default=0.60)
    parser.add_argument("--output", default="reports/capstone.json")
    args = parser.parse_args()
    if min(args.elements, args.repeats, args.epsilon, args.target_speedup) <= 0:
        raise ValueError("规模、重复、epsilon 和目标加速必须大于 0")
    if args.warmup < 0 or not 0 < args.hotspot_fraction <= 1:
        raise ValueError("warmup 必须非负，hotspot-fraction 必须位于 (0, 1]")

    rng = random.Random(2026)
    values = [rng.uniform(-3.0, 3.0) for _ in range(args.elements)]
    baseline_output, baseline_samples = benchmark(
        baseline, values, args.epsilon, args.warmup, args.repeats
    )
    candidate_output, candidate_samples = benchmark(
        candidate, values, args.epsilon, args.warmup, args.repeats
    )

    max_abs = max(abs(left - right)
                  for left, right in zip(baseline_output, candidate_output))
    denominator = max(max(abs(value) for value in baseline_output), 1e-30)
    max_relative = max_abs / denominator
    baseline_summary = summarize(baseline_samples, args.elements)
    candidate_summary = summarize(candidate_samples, args.elements)
    speedup = baseline_summary["p50_ms"] / candidate_summary["p50_ms"]
    predicted_end_to_end_speedup = 1.0 / (
        (1 - args.hotspot_fraction) + args.hotspot_fraction / speedup
    )
    correctness_pass = max_relative <= args.max_relative_error
    performance_pass = (
        candidate_summary["p50_ms"]
        <= baseline_summary["p50_ms"] * (1 + args.max_regression)
        and speedup >= args.target_speedup
    )

    result = {
        "workload": {
            "elements": args.elements,
            "operation": "RMSNorm + SiLU",
            "seed": 2026,
        },
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
        },
        "baseline": baseline_summary,
        "candidate": candidate_summary,
        "correctness": {
            "max_absolute_error": max_abs,
            "max_relative_error": max_relative,
            "threshold": args.max_relative_error,
            "pass": correctness_pass,
        },
        "speedup_p50": speedup,
        "hotspot_fraction": args.hotspot_fraction,
        "amdahl_predicted_end_to_end_speedup": predicted_end_to_end_speedup,
        "gate": {
            "performance_pass": performance_pass,
            "correctness_pass": correctness_pass,
            "pass": performance_pass and correctness_pass,
        },
        "warning": "这是 CPU 教学负载；结果不能外推到 GPU Kernel 或真实模型。",
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if not result["gate"]["pass"]:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
```

这个参考实现里有七处值得留意的设计：

1. **`silu` 对指数参数做 ±60 截断**：`math.exp` 在参数过大时抛 `OverflowError`。截断到 60 已远超 SiLU 的饱和区（$x>20$ 时 $\sigma(x)\approx 1$），不影响数值结果，但保证了任意输入下不崩溃。
2. **两个实现的算术顺序完全一致**：Baseline 先算 `value * inverse_rms` 再送进 `silu`，Candidate 在列表推导里做同样的乘法再调 `silu`；平方和都是按同一顺序累加。因此两者理论上逐位相同，`max_absolute_error` 应为 0，这也是 `--max-relative-error 1e-12` 这种严格阈值能通过的原因。
3. **相对误差用全局尺度归一**：分母是 Baseline 输出的最大绝对值，而不是逐元素相对误差。这避免了输出接近 0 的元素把相对误差放大到无意义的量级，是数值对比的常用口径。
4. **`sum(map(operator.mul, values, values))` 不建中间列表**：这是 Candidate 的核心改动——省掉 `squares` 与 `normalized` 两个列表的分配与写入。
5. **`raw_seconds` 完整保存**：门禁判定基于 P50，但原始样本必须落盘，便于事后判断收益是否超过噪声。
6. **`performance_pass` 是双条件**：既要求不超过基线的 $1 + 5\%$（防回归），又要求达到 `target_speedup`（防无效改动）。只写前者会让「没有收益」也判 PASS。
7. **门禁用退出码 2 而非 0**：便于直接接入 CI，失败时中断发布流程。

### 9.2 运行命令

```bash
mkdir -p reports
python capstone_runner.py \
  --elements 200000 --warmup 3 --repeats 20 \
  --target-speedup 1.0 --max-regression 0.05 \
  --output reports/capstone.json
```

如果当前 CPU、Python 版本或频率抖动导致 Candidate 未达到目标，程序会以状态码 2 退出。这不是脚本失败，而是门禁按设计拒绝没有证据的优化。先增加重复、隔离噪声并查看原始样本；不要降低阈值只为获得 PASS。

`--target-speedup 1.0` 是最宽松的门槛（只要不比基线慢即可）。把它调到 1.2 或 1.5 就变成真正的收益门禁，此时 FAIL 的概率显著上升——这恰好演示了门禁阈值与结论强度之间的关系。

### 9.3 Amdahl 预测的量级

`--hotspot-fraction` 默认 0.60，表示被优化的部分占端到端时间的 60%。按 Amdahl 公式推导，局部加速与端到端加速的关系为：

| 局部加速 $S_{optimized}$ | 端到端加速（$p=0.6$） |
| --- | --- |
| 1.2 | ≈1.11 |
| 1.5 | 1.25 |
| 2.0 | ≈1.43 |
| 3.0 | ≈1.67 |
| $\infty$ | 2.50 |

最后一行是上界 $1/(1-p) = 2.5$：即使把热点优化到零耗时，端到端也只能快 2.5 倍。这张表解释了为什么「Kernel 快 3 倍」常常只换来「服务快 1.6 倍」，也说明在投入大量精力优化热点之前，应先确认 $p$ 到底有多大——若热点只占 20%，上界仅 1.25，优化空间从一开始就很有限。

### 9.4 预期现象

Candidate 少创建一个中间列表，通常减少分配和内存流量，但 `sum(map(...))` 的调用开销与 Python 解释器成本可能让它在部分环境中没有优势。这正是性能工程的核心：代码看起来更「优化」不等于实测更快。

在 GPU 上同样的改动通常收益明确（省掉的是真实的显存读写与 Kernel Launch），但在 CPU 解释执行下，省下的分配可能被 `operator.mul` 的逐元素调用开销抵消。这个反差本身就是结论：**融合收益取决于被省掉的开销在总时间中的占比**，而不是取决于代码行数变少。

## 10. Level 1：替换为真实 GPU 工作负载

保留 `capstone_runner.py` 的报告和门禁结构，把 `baseline()`、`candidate()` 替换为目标工作负载，并遵守：

- CUDA 用 Event 或同步边界计时；
- PyTorch 训练同时测 Loss/Gradient/Convergence；
- 推理同时测 TTFT/TPOT/输出一致性；
- 多 GPU 同时测全局吞吐、慢 Rank 和通信；
- Kernel 同时跑 Compute Sanitizer、误差与 Nsight Compute；
- 每个结果保存硬件、版本、Shape、精度和原始样本。

### 10.1 GPU 能力检测

```python
python - <<'PY'
try:
    import torch
except ImportError:
    print("PyTorch 未安装，使用 Level 0")
else:
    print("torch", torch.__version__)
    print("cuda runtime", torch.version.cuda)
    print("cuda available", torch.cuda.is_available())
    if torch.cuda.is_available():
        for index in range(torch.cuda.device_count()):
            print(index, torch.cuda.get_device_name(index),
                  torch.cuda.get_device_capability(index),
                  round(torch.cuda.get_device_properties(index).total_memory / 2**30, 2))
PY
```

能力检测的输出应直接写进环境快照。`get_device_capability` 返回的计算能力决定了哪些专项合法（例如 FP8 需要 Hopper 及以上），`total_memory` 决定容量规划的上界。先检测再选实验，比先跑再报错更节省预算。

替换工作负载时最容易破坏的是计时边界：CPU 版本用 `time.perf_counter()` 直接包住函数调用即可，CUDA 版本必须插入 Event 或显式同步，否则测到的是 Launch 时间而非执行时间。这一处改动若遗漏，后续所有收益数字都不可信。

## 11. Level 2：架构专项

| 架构 | 例子 | 合法专项 |
| --- | --- | --- |
| Ampere | RTX 3080/3090、A100 | TF32、FP16/BF16（按卡）、Ampere Async Copy |
| Ada Lovelace | RTX 4090、L40/L40S | FP16/BF16、PCIe 推理与编译器优化 |
| Hopper | H100/H200 | FP8、Transformer Engine、TMA、NVLink/NVSwitch |
| Blackwell | RTX 5090、B100/B200/GB200 | FP8/FP4、新 Tensor Core/Fabric，依工具链 |

RTX 4090 不是 Blackwell。消费卡与数据中心 GPU 即使属于相近代际，也可能在显存、互联、ECC、虚拟化和低精度能力上不同。

专项实验必须有能力检测与跳过逻辑。例如：没有 NVLink 时测 PCIe 基线并标记 `SKIPPED_NVLINK`，而不是把 Host Staging 写成 NVLink 模拟。

显式跳过标记比默默不跑更重要：报告里出现 `SKIPPED_NVLINK` 说明结论有明确边界，评审者知道哪些部分未被验证；而缺失该项则容易被误读为「已验证无收益」。

## 12. 阶段六：实验矩阵

### 12.1 单变量实验

| Run | 改变量 | 工作量 | 正确性 | P50/P95 | 容量 | 结论 |
| --- | --- | --- | --- | --- | --- | --- |
| B0 | 无 | 固定 | Pass | 待测 | 待测 | 基线 |
| C1 | 变量 A | 相同 | Pass/Fail | 待测 | 待测 | 接受/拒绝 |
| C2 | 变量 B | 相同 | Pass/Fail | 待测 | 待测 | 接受/拒绝 |

### 12.2 交互实验

只有单变量结果明确后，才组合 AMP + Compile、Batch + Scheduler、FSDP + Checkpoint 或 TP + KV 配置。组合收益不能简单相乘，可能存在重复优化和资源冲突。

典型的冲突有三类：AMP 与 Compile 可能重复做同一件事（都减少访存或都用低精度），叠加后收益远低于乘积；FSDP 与 Activation Checkpoint 都改变显存峰值构成，组合后峰值可能不降反升；TP 与 KV 配置共同决定每卡容量，单独调优的最优值组合起来可能触发抢占。因此交互实验必须重新测 Guardrail，不能沿用单变量阶段的结论。

## 13. 阶段七：正确性与稳定性

### 13.1 正确性门禁

训练：

- Loss/Gradient 有限；
- 固定小数据上的趋势一致；
- 精度误差在阈值内；
- 完整收敛或质量代理不退化。

推理：

- 固定 Prompt 的 Greedy 输出或 Logit 差异；
- Token 数、Stop、EOS 与结构化输出一致；
- 量化前后质量集；
- 流式顺序、取消和重试正确。

系统：

- OOM/Timeout/错误率；
- 30～120 分钟 Soak；
- Worker/网络/磁盘故障注入；
- 热降频、功耗、ECC 和内存泄漏。

三类门禁的严格程度递增：数值正确性可以在几分钟内验证，收敛与质量需要小时级，系统稳定性需要 Soak 与故障注入。性能收益越大、改动越靠近底层，就越需要完整跑完三类——一个只通过数值对比的 Kernel 改动，可能在长时间运行后暴露内存泄漏。

### 13.2 统计规则

- 保存原始样本；
- 报告中位数与尾部；
- 独立运行至少 3 次；
- 对收益小于环境噪声的改动不下结论；
- 不删除「难看」的离群点，先解释来源；
- 预先定义门禁，不在看结果后改阈值。

最后一条是整套方法论的底线。看完结果再调阈值，等于把「验证」变成「找理由」，此后所有 PASS 都失去意义。正确做法是在章程阶段写死阈值，若实测 FAIL，要么改实现，要么承认假设不成立并记录失败原因——失败的假设同样是交付物的一部分。

## 14. 阶段八：成本与收益

### 14.1 训练

$$
CostPerBillionTokens = \frac{GPUHourPrice \times GPUCount \times Hours}{Tokens / 10^9}
$$

### 14.2 推理

$$
CostPerMillionOutputTokens = \frac{HourlyFleetCost}{OutputTokensPerHour / 10^6}
$$

必须按有效 Token 计算：失败、重试、SLO Miss 与空闲容量都计入成本。若优化需要更多工程维护、专属硬件或可靠性风险，报告中也应列入。

分母用「有效 Token」而非「生成 Token」是这两个公式的关键。一个把吞吐提高 20% 但让 SLO Miss 率从 1% 升到 15% 的配置，按生成 Token 算成本下降，按有效 Token 算可能反而上升。空闲容量同样计入：为峰值预留但长期闲置的 GPU，其成本要摊到实际产出的 Token 上。

### 14.3 投资回收

$$
Payback = \frac{EngineeringCost}{MonthlyInfrastructureSavings}
$$

没有稳定工作量或收益小于噪声时，不应给出虚假的精确回收期。

这个公式的分子常被低估：工程成本不只是开发工时，还包括后续维护、回归测试、专属硬件依赖与故障处理。若一项优化每月省下少量费用却需要持续维护一套定制 Kernel，回收期可能是负收益。收益小于噪声时更应直接写「无法量化」，而不是给一个精确到小数点后两位的数字。

## 15. 阶段九：发布、回滚与持续回归

### 15.1 发布计划

1. 离线正确性与性能门禁；
2. Shadow Traffic；
3. 1% Canary；
4. 分阶段扩大；
5. 观察一个完整业务周期；
6. 固化默认配置。

「一个完整业务周期」通常指覆盖日内高低峰与周末模式，至少一天到一周。只观察半小时就固化配置，会漏掉只在高峰出现的排队与抢占问题。Shadow Traffic 阶段不返回结果给用户，因此可以安全验证正确性与性能，但无法验证真实取消与重试行为，这部分要靠 Canary。

### 15.2 自动回滚条件

- Primary SLO 连续超阈值；
- 错误/OOM/NaN 上升；
- Goodput 或成本退化；
- 输出质量门禁失败；
- GPU/Host Memory 持续增长；
- 新配置无法在目标架构安全启动。

「连续」二字很重要：单点抖动不应触发回滚，否则会在噪声中反复切换配置。而「内存持续增长」是泄漏信号，即使当前 SLO 正常也应回滚，因为它注定在数小时后恶化。最后一条针对架构兼容性——在 Hopper 上验证的 FP8 配置若被下发到 Ada 节点，必须启动即失败并回滚，而不是运行中崩溃。

### 15.3 回归层级

| 频率 | 测试 |
| --- | --- |
| 每次提交 | 小规模正确性、语法、Smoke |
| 每日 | 固定机器 Microbenchmark |
| 每周 | 端到端、并发扫描、Profiler |
| 发布前 | 质量、Soak、故障注入、成本 |

四层的设计逻辑是「成本与覆盖度匹配」：提交级必须秒级到分钟级完成，否则开发者会绕过；每日 Microbenchmark 固定机器以消除硬件差异，才能识别小幅回归；每周端到端捕捉组合效应；发布前才做昂贵的 Soak 与故障注入。把发布前测试放到每次提交，结果一定是门禁被禁用。

## 16. 结果报告模板

### 16.1 结论

一段话写清：改了什么、Primary Metric 变化多少、Guardrail 是否全部通过、是否建议上线。结论必须能被非技术读者理解，且每个数字都能在后文找到出处。

### 16.2 问题定义与 SLO

业务目标、Primary Metric、至少两个 Guardrail、成本目标与预算约束。直接引用章程，不在此处重新定义。

### 16.3 环境与工作负载

硬件、驱动、框架版本、模型与数据 Revision、精度、输入分布、计时边界。附完整环境快照与命令。

### 16.4 基线

Smoke、Warmup、稳态、尾部、容量、Profile 窗口与 3～5 次独立运行的原始样本统计。

### 16.5 瓶颈证据

按「从外到内」顺序给出定位过程，每一层附工具输出或 Trace 截图，并说明排除了哪些可能。

### 16.6 假设与实验矩阵

假设登记表全文，包含失败假设及其后续检查方向；单变量与交互实验结果分列。

### 16.7 优化实现

最小改动的具体内容、代码或配置差异、为什么这样改、以及改动的适用边界。

### 16.8 正确性与稳定性

数值误差、收敛或质量对比、Soak 结果、故障注入结果、内存与温度趋势。

### 16.9 成本与收益

按有效 Token 计算的单位成本、投资回收期（或说明无法量化的原因）、工程维护代价。

### 16.10 发布与回滚

灰度计划、观测指标、自动回滚条件、回归层级安排。

### 16.11 局限与后续

明确区分资料事实、模型推导、模拟结果与硬件实测；列出未验证项（含 `SKIPPED_*` 标记）与下一步方向。

### 16.12 附录

完整命令、原始 JSON、Trace 文件路径、环境快照。附录的作用是让别人能不看正文就复现实验。

## 17. 常见错误与排查

### 17.1 没有 Guardrail 就宣布更快

精度下降、丢请求、减少 Token、改变 Batch 或禁用功能都能让数字变好看。必须同时报告正确性与工作量口径。

### 17.2 基线包含冷启动

编译、Allocator 预热、连接建立与首次 CUDA Graph 捕获都会污染基线，让后续优化显得收益巨大。必须有独立 Warmup 阶段。

### 17.3 只保存平均值

平均值掩盖尾部与噪声。必须保存原始样本，报告 P50/P95/P99，并做多次独立运行。

### 17.4 把模型推导写成实测

Roofline、Amdahl、Erlang-C、成本公式的输出都是预测。报告中必须标注来源类别，并与真实 Profile 对照。

### 17.5 同时打开所有 Profiler

采集开销会改变被测系统行为。应使用短窗口分别采集，并保留一份无 Profiler 的最终 Benchmark 作为对外数字。

### 17.6 看完结果再改门禁阈值

这让验证失去意义。阈值必须在实验前写死，FAIL 就记录失败并修正假设。

### 17.7 组合收益按乘积估算

AMP + Compile、FSDP + Checkpoint 等组合存在重复优化与资源冲突，必须重新实测并复查 Guardrail。

### 17.8 跨架构外推专项结论

消费卡与数据中心卡在互联、ECC、低精度能力上不同。没有 NVLink 就标 `SKIPPED_NVLINK`，不要把 Host Staging 写成 NVLink 结果。

### 17.9 成本按生成 Token 而非有效 Token

失败、重试、SLO Miss 与空闲容量都必须计入，否则成本下降可能是假象。

### 17.10 交付物缺少回滚方案

没有回滚路径的优化不能上线。发布计划、自动回滚条件与回归层级必须与性能数字一起交付。

## 18. 常见追问与解答

### 18.1 为什么 Primary Metric 只能有一个

多个主指标会让决策失去优先级，出现「A 变好 B 变差」时无法判断是否接受。其余指标应作为 Guardrail 设定阈值，而不是并列目标。

### 18.2 Guardrail 至少两个的理由

一个 Guardrail 通常只覆盖正确性或容量之一。性能优化的代价往往同时出现在数值精度与资源占用两侧，只设一个会漏掉另一侧的退化。

### 18.3 Amdahl 上界怎么用

上界为 $1/(1-p)$。在动手优化前先估 $p$，若上界本身就低于目标收益，说明该热点不值得投入，应换方向或扩大优化范围。

### 18.4 为什么 CPU 参考实验不能外推到 GPU

CPU 上的开销主要是解释器与内存分配，GPU 上主要是显存带宽与 Kernel Launch。同一处「融合」改动在两类设备上的收益占比完全不同。

### 18.5 门禁 FAIL 时应该做什么

先增加重复次数、隔离噪声、检查原始样本与计时边界；确认实现无误后记录假设失败并给出下一步检查方向。不应降低阈值换取 PASS。

### 18.6 有效 Token 与生成 Token 的差别

生成 Token 包含失败请求、重试与超时请求的输出；有效 Token 只计满足 SLO 且成功的部分。成本与 Goodput 都必须用后者。

### 18.7 为什么发布前要观察一个完整业务周期

日内高低峰与周末模式的负载分布差异很大，短窗口观察会漏掉只在高峰出现的排队、抢占与容量问题。

### 18.8 回归测试为什么分四层

成本与覆盖度需要匹配。提交级要快，每日级要固定机器以识别小幅回归，每周级捕捉组合效应，发布前才做昂贵的 Soak 与故障注入。

## 19. 延伸练习

1. 为选定方向写完整章程，明确 Primary Metric 与两个 Guardrail。
2. 采集 3～5 次独立运行的基线，计算噪声区间并据此设定最小可判定收益。
3. 用「从外到内」顺序完成一次瓶颈定位，记录每层排除的可能。
4. 登记三个可证伪假设，各写出预测数字与失败后的检查方向。
5. 把 `capstone_runner.py` 的工作负载替换为真实 GPU 任务，保留门禁结构。
6. 扫描 `--hotspot-fraction`，验证 Amdahl 预测与实测端到端收益的偏差。
7. 做一次交互实验，检验组合收益是否等于单变量收益之积。
8. 按有效 Token 计算单位成本与投资回收期，并列出工程维护代价。
9. 编写发布与回滚方案，定义自动回滚条件与四层回归安排。
10. 按结果报告模板整理完整证据包，交由他人复现。

## 20. 项目验收 Checklist

- 章程包含 Primary Metric、至少两个 Guardrail、预算与不可变 Revision。
- 环境快照完整，含拓扑、功耗策略、版本与完整命令。
- 工作负载、有效 Batch、精度、随机种子与计时边界全部受控。
- 基线包含 Smoke、Warmup、稳态、尾部、容量、Profile 与多次独立运行。
- 原始样本已保存，报告含 P50/P95/P99 而非仅平均值。
- 瓶颈定位按从外到内顺序，每层有工具证据。
- 假设登记表可证伪，含预测数字、Guardrail 与失败后续方向。
- 实验矩阵先单变量后交互，组合收益经过实测。
- 正确性、稳定性与系统三类门禁全部执行。
- 门禁阈值预先定义，未在看结果后修改。
- 成本按有效 Token 计算，含失败、重试、SLO Miss 与空闲容量。
- 明确区分资料事实、模型推导、模拟结果与硬件实测。
- 未验证专项带 `SKIPPED_*` 标记，未跨架构外推。
- 发布计划、自动回滚条件与四层回归安排齐备。
- 证据包可被他人独立复现。

## 写在最后

主题二至此收束：从性能指标与诊断方法出发，走完 GPU 微架构、集群互联、CUDA 与 Kernel、分布式训练与通信、Compiler 与 Runtime、LLM 推理系统，最后落到八个综合项目。贯穿始终的不是某个具体优化技巧，而是一条证据链——受控基线、可证伪假设、单变量实验、正确性门禁、成本核算与回滚路径。

下一个主题转向大模型推理优化工程，把这套方法用到生产级推理平台的吞吐、成本与多租户治理上。

下一篇：[大模型推理优化工程 · 主题三](/source/AI-Infra/3-大模型推理优化工程/README)。