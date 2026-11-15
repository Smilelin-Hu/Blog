# PyTorch 训练性能优化

本项目围绕 PyTorch 训练任务建立性能基线，定位瓶颈并验证数据、算子与运行时优化收益。

它把 Benchmark、PyTorch Profiler、混合精度、数据管线、`torch.compile` 与性能回归方法串成一个完整训练优化闭环：从一个可运行的 MLP 分类训练基线出发，在不改变模型语义与有效 Batch Size 的前提下，逐项验证以下优化。

```text
可复现基线
  → 找到 Data、Forward、Backward、Optimizer 的时间占比
  → zero_grad(set_to_none=True)
  → CUDA 自动混合精度
  → DataLoader pinned memory / workers / persistent workers
  → 可选 torch.compile
  → 正确性、吞吐、显存与回归门禁
```

目标不是证明「某个开关永远更快」，而是建立一套任何 PyTorch 训练任务都能复用的测量方法。CPU 机器可以完成 Level 0；常见 NVIDIA GPU 可以完成 Level 1；Level 2 用于 BF16、TF32、编译器与架构专项验证。

## 1. 内容概览与交付物

做完之后应当能够：用稳定的热身、同步、重复测量获得可信的 Step Time；同时报告吞吐、P50/P95、峰值显存、损失与训练有效性；用 Profiler 区分数据等待、CPU Launch、GPU Kernel、拷贝与同步瓶颈；正确使用 `zero_grad(set_to_none=True)`、AMP、Pinned Memory 与 `torch.compile`；解释为什么 AMP、增加 Worker 或编译并不保证加速；设计性能回归门禁，避免把随机波动写成优化收益；在 CPU、Ampere、Ada、Hopper 与 Blackwell 环境中采用不同能力门控。

前置知识：PyTorch 性能分析与编译器相关内容；理解 Forward、Autograd、Optimizer 与 DataLoader；Python 3.10 或更高版本；PyTorch 2.x，若使用 `torch.compile` 建议采用当前稳定版并记录完整版本；GPU 实验需要与 PyTorch 匹配的 NVIDIA 驱动与 CUDA Runtime。

```text
pytorch-training-project/
├── train_benchmark.py
├── reports/
│   ├── environment.json
│   ├── baseline.json
│   ├── optimized.json
│   ├── profile/
│   └── comparison.md
└── regression_gate.py
```

`comparison.md` 必须记录命令、硬件、软件版本、输入形状、有效 Batch Size、P50/P95、吞吐、峰值显存、损失差异与结论边界。

## 2. 核心直觉：训练 Step 是一条流水线

一次训练迭代可粗略拆成

$$
T_{step} = T_{data} + T_{H2D} + T_{forward} + T_{backward} + T_{optimizer} + T_{sync} + T_{idle}
$$

吞吐为

$$
Throughput = \frac{B_{effective}}{T_{step}}
$$

其中 $B_{effective}$ 是一次参数更新实际消费的样本数。若使用梯度累积：

$$
B_{effective} = B_{micro} \times N_{accum} \times N_{data\ parallel}
$$

优化时必须保持 $B_{effective}$ 与数据形状一致，否则「吞吐提升」可能只是改变了问题。

对于异步 CUDA，CPU 计时若没有同步，测到的常常只是 Kernel Launch 时间。项目代码在每个计时窗口前后调用设备同步，确保 Step Time 包含实际设备工作。

## 3. 性能与正确性指标

| 指标 | 目的 | 最低要求 |
| --- | --- | --- |
| P50 Step Time | 典型性能 | 热身后至少 20 步 |
| P95 Step Time | 尾部抖动 | 同一进程内报告 |
| Samples/s | 训练吞吐 | 有效 Batch Size 不变 |
| Peak Memory | 容量与碎片风险 | CUDA 才报告 |
| Final Loss | 基本正确性 | 同种子下趋势一致 |
| Good Steps | 有效工作量 | 无 NaN、无 OOM、无跳步 |

有效训练吞吐可以写成

$$
Goodput = Throughput \times \frac{N_{valid\ steps}}{N_{all\ steps}}
$$

一旦出现 NaN、OOM 重试或数据异常，峰值吞吐不再等于有效吞吐。这也是脚本要单独统计 `valid_step_ratio` 的原因：一个「跑得快但每十步崩一次」的配置，Goodput 可能低于慢而稳的基线。

## 4. 瓶颈分析决策树

```text
GPU 利用率低？
├─ CPU 线程忙、DataLoader 间隙明显 → 数据/预处理瓶颈
├─ 大量短 Kernel 与 Launch 空洞 → Python/Runtime 开销
├─ H2D 拷贝串行且耗时明显 → Pinned Memory / non_blocking / Batch 太小
├─ GEMM 时间占主导但吞吐低 → Shape、精度、Tensor Core、内存带宽
├─ Optimizer/zero_grad 占比高 → set_to_none、融合优化器、参数规模
└─ 多卡通信占比高 → Bucket、重叠、拓扑、慢 Rank
```

先定位占比最大的阶段，再改变一个变量。一次同时打开 AMP、编译、更多 Worker 与更大 Batch，会让因果关系不可解释。

## 5. Level 0 / Level 1：完整训练 Benchmark

下面的脚本在 CPU 与 CUDA 上使用同一套训练逻辑。它自动检测设备、Compute Capability、BF16 支持、PyTorch/CUDA 版本与显存；CPU 模式不伪装成 GPU 实测。保存为 `train_benchmark.py`：

```python
#!/usr/bin/env python3
import argparse
import json
import math
import os
import platform
import random
import statistics
import time
from contextlib import nullcontext
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

class SyntheticClassification(Dataset):
    def __init__(self, samples: int, features: int, classes: int, seed: int):
        generator = torch.Generator().manual_seed(seed)
        self.x = torch.randn(samples, features, generator=generator)
        teacher = torch.randn(features, classes, generator=generator)
        self.y = (self.x @ teacher).argmax(dim=1)

    def __len__(self):
        return self.x.shape[0]

    def __getitem__(self, index):
        return self.x[index], self.y[index]

class MLP(nn.Module):
    def __init__(self, features: int, hidden: int, classes: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(features, hidden),
            nn.GELU(),
            nn.Linear(hidden, hidden),
            nn.GELU(),
            nn.Linear(hidden, classes),
        )

    def forward(self, x):
        return self.net(x)

def percentile(values, q):
    ordered = sorted(values)
    if not ordered:
        return float("nan")
    position = (len(ordered) - 1) * q
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[low]
    return ordered[low] * (high - position) + ordered[high] * (position - low)

def synchronize(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)

def environment(device):
    info = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "torch": torch.__version__,
        "torch_cuda_runtime": torch.version.cuda,
        "device": str(device),
        "cpu_count": os.cpu_count(),
    }
    if device.type == "cuda":
        props = torch.cuda.get_device_properties(device)
        info.update({
            "gpu": props.name,
            "compute_capability": list(torch.cuda.get_device_capability(device)),
            "total_memory_gib": round(props.total_memory / 2**30, 2),
            "bf16_supported": bool(torch.cuda.is_bf16_supported()),
        })
    return info

def choose_amp(device, enabled):
    if not enabled or device.type != "cuda":
        return False, torch.float32
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    return True, dtype

def main():
    parser = argparse.ArgumentParser(description="PyTorch 训练性能 Benchmark")
    parser.add_argument("--mode", choices=["baseline", "optimized"], default="baseline")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--features", type=int, default=1024)
    parser.add_argument("--hidden", type=int, default=2048)
    parser.add_argument("--classes", type=int, default=100)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--compile", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    if min(args.steps, args.batch_size, args.features, args.hidden, args.classes) <= 0:
        raise ValueError("steps、batch-size、features、hidden、classes 必须大于 0")

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("请求了 CUDA，但当前 PyTorch 无可用 CUDA 设备")
    use_cuda = args.device == "cuda" or (args.device == "auto" and torch.cuda.is_available())
    device = torch.device("cuda" if use_cuda else "cpu")

    optimized = args.mode == "optimized"
    pin_memory = optimized and device.type == "cuda"
    persistent_workers = optimized and args.workers > 0
    samples = max(args.batch_size * (args.steps + args.warmup + 2), args.batch_size * 8)
    dataset = SyntheticClassification(samples, args.features, args.classes, args.seed)
    loader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=pin_memory,
        persistent_workers=persistent_workers,
        drop_last=True,
    )

    model = MLP(args.features, args.hidden, args.classes).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    criterion = nn.CrossEntropyLoss()

    compiled = False
    if args.compile:
        if not hasattr(torch, "compile"):
            raise RuntimeError("当前 PyTorch 不支持 torch.compile")
        model = torch.compile(model)
        compiled = True

    amp_enabled, amp_dtype = choose_amp(device, optimized)
    scaler_enabled = amp_enabled and amp_dtype == torch.float16
    scaler = torch.amp.GradScaler("cuda", enabled=scaler_enabled)

    activities = [torch.profiler.ProfilerActivity.CPU]
    if device.type == "cuda":
        activities.append(torch.profiler.ProfilerActivity.CUDA)
    profile_context = (
        torch.profiler.profile(
            activities=activities,
            schedule=torch.profiler.schedule(wait=1, warmup=1, active=3, repeat=1),
            on_trace_ready=torch.profiler.tensorboard_trace_handler("reports/profile"),
            record_shapes=True,
            profile_memory=True,
        )
        if args.profile
        else nullcontext()
    )

    times_ms = []
    losses = []
    valid_steps = 0
    total_needed = args.warmup + args.steps
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)

    with profile_context as profiler:
        for step, (features, labels) in enumerate(loader):
            if step >= total_needed:
                break
            synchronize(device)
            start = time.perf_counter()

            features = features.to(device, non_blocking=pin_memory)
            labels = labels.to(device, non_blocking=pin_memory)
            optimizer.zero_grad(set_to_none=optimized)

            autocast_context = (
                torch.autocast(device_type="cuda", dtype=amp_dtype)
                if amp_enabled
                else nullcontext()
            )
            with autocast_context:
                logits = model(features)
                loss = criterion(logits, labels)

            if scaler_enabled:
                scaler.scale(loss).backward()
                scaler.step(optimizer)
                scaler.update()
            else:
                loss.backward()
                optimizer.step()

            synchronize(device)
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            loss_value = float(loss.detach().cpu())
            if math.isfinite(loss_value):
                valid_steps += 1
            if step >= args.warmup:
                times_ms.append(elapsed_ms)
                losses.append(loss_value)
            if args.profile:
                profiler.step()

    if len(times_ms) != args.steps:
        raise RuntimeError(f"只测到 {len(times_ms)} 步，预期 {args.steps} 步")

    p50_ms = percentile(times_ms, 0.50)
    result = {
        "mode": args.mode,
        "compiled": compiled,
        "amp_enabled": amp_enabled,
        "amp_dtype": str(amp_dtype),
        "pin_memory": pin_memory,
        "persistent_workers": persistent_workers,
        "batch_size": args.batch_size,
        "workers": args.workers,
        "measured_steps": args.steps,
        "p50_step_ms": round(p50_ms, 4),
        "p95_step_ms": round(percentile(times_ms, 0.95), 4),
        "mean_step_ms": round(statistics.mean(times_ms), 4),
        "samples_per_second_at_p50": round(args.batch_size / (p50_ms / 1000.0), 2),
        "first_loss": round(losses[0], 6),
        "final_loss": round(losses[-1], 6),
        "valid_step_ratio": round(valid_steps / total_needed, 6),
        "peak_memory_mib": (
            round(torch.cuda.max_memory_allocated(device) / 2**20, 2)
            if device.type == "cuda"
            else None
        ),
        "environment": environment(device),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))

    output = args.output or f"reports/{args.mode}.json"
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

if __name__ == "__main__":
    main()
```

读代码时要能指认的几处设计：

- **`mode` 是唯一的优化开关集合**：`optimized` 同时决定 `set_to_none`、AMP、`pin_memory`、`persistent_workers`。做单变量归因时必须逐项拆开跑，而不是只比 baseline 与 optimized 两个端点。
- **计时窗口两端各一次 `synchronize`**：窗口前的同步保证上一步的设备工作已结束，窗口后的同步保证本步工作已计入。
- **`loss.detach().cpu()` 在计时窗口之外**：它本身会触发一次 D2H 同步，若放进窗口会污染 Step Time。
- **`drop_last=True` 与 `samples` 的下界**：保证每个 Batch 形状一致、步数足够，避免尾批触发重编译或形状变化。
- **`valid_step_ratio` 的分母是 `warmup + steps`**：包含热身步，因此它衡量的是整个进程的有效性，而不只是统计窗口。
- **版本兼容**：`torch.amp.GradScaler("cuda", ...)` 是 PyTorch 2.4 之后的写法；在更早的 2.x 上需改用 `torch.cuda.amp.GradScaler(enabled=...)`，`torch.autocast(device_type="cuda", ...)` 在 2.0 之前写作 `torch.cuda.amp.autocast(...)`。报告里必须写清实际使用的版本与写法。

### 5.1 安装与环境隔离

不要在系统 Python 中直接覆盖现有框架：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

PyTorch 的安装命令取决于操作系统、驱动与 CUDA Runtime。从 PyTorch 官方安装选择器复制与当前机器匹配的命令，并把安装结果锁定：

```bash
python -m pip freeze > reports/requirements-lock.txt
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda runtime:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
PY
```

### 5.2 CPU 回退实验

先用小规模确认流程与结果文件：

```bash
mkdir -p reports
python train_benchmark.py --device cpu --mode baseline \
  --features 128 --hidden 256 --batch-size 64 --warmup 2 --steps 10 \
  --output reports/cpu_baseline.json

python train_benchmark.py --device cpu --mode optimized \
  --features 128 --hidden 256 --batch-size 64 --warmup 2 --steps 10 \
  --output reports/cpu_optimized.json
```

CPU 模式主要验证计时、正确性、报告与回归流程。CUDA AMP、Pinned Memory、Tensor Core 与 GPU 峰值显存无法由 CPU 等价验证。

### 5.3 常见 NVIDIA GPU 基线

```bash
python train_benchmark.py --device auto --mode baseline \
  --batch-size 256 --workers 0 --warmup 5 --steps 30 \
  --output reports/baseline.json

python train_benchmark.py --device auto --mode optimized \
  --batch-size 256 --workers 2 --warmup 5 --steps 30 \
  --output reports/optimized.json
```

如果系统是容器、Notebook 或 Windows，`--workers 2` 可能不是最优，甚至可能因为进程启动方式而更慢。必须扫描而不是猜测：

```bash
for workers in 0 1 2 4 8; do
  python train_benchmark.py --device auto --mode optimized \
    --workers "$workers" --output "reports/workers_${workers}.json"
done
```

### 5.4 可选 torch.compile

首次调用包含编译成本，必须扩大热身并单独报告首次运行时间：

```bash
python train_benchmark.py --device auto --mode optimized --compile \
  --batch-size 256 --workers 2 --warmup 10 --steps 30 \
  --output reports/optimized_compile.json
```

若出现 Graph Break、重编译或动态 Shape 问题，可使用：

```bash
TORCH_LOGS="graph_breaks,recompiles" \
python train_benchmark.py --device auto --mode optimized --compile \
  --warmup 10 --steps 10
```

不要为了「让编译成功」而静默吞掉异常并把 Eager 结果写成编译结果。判断编译是否真的生效，看三点：日志里有没有大量 graph break、稳态步是否明显快于 Eager、`compiled` 字段与 trace 中是否出现 Inductor 生成的 kernel。

## 6. Profiler 实验

```bash
python train_benchmark.py --device auto --mode baseline \
  --warmup 2 --steps 8 --profile --output reports/profiled_baseline.json

python train_benchmark.py --device auto --mode optimized \
  --warmup 2 --steps 8 --profile --output reports/profiled_optimized.json

tensorboard --logdir reports/profile
```

Profiler 会引入额外开销，因此它用于解释时间分布，不用于产生最终吞吐数字。长任务应使用 Schedule 只采集少量窗口；`record_shapes`、`profile_memory` 与 Stack Trace 都会增加开销。脚本里的 `schedule(wait=1, warmup=1, active=3, repeat=1)` 表示只采集第 3～5 步，正好避开冷启动。

### 6.1 时间线检查清单

1. DataLoader 是否在 GPU 工作结束前准备好下一批数据。
2. H2D Copy 是否与计算重叠，还是每步都串行阻塞。
3. 是否存在 `.item()`、打印 Tensor、隐式设备到主机拷贝造成的同步。
4. Forward/Backward 中是否有大量短 Kernel。
5. Optimizer 与 `zero_grad` 是否占据异常高比例。
6. 编译模式是否出现多个碎片化的 Compiled Region。
7. 首步、热身步与稳态步是否被混在同一个统计窗口。

## 7. Level 2：架构专项实验

### 7.1 能力检测

```bash
python - <<'PY'
import torch
print("torch", torch.__version__)
print("runtime", torch.version.cuda)
print("cuda", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu", torch.cuda.get_device_name())
    print("capability", torch.cuda.get_device_capability())
    print("bf16", torch.cuda.is_bf16_supported())
PY
```

### 7.2 支持边界

| 架构 | 常见 GPU | 本项目重点 |
| --- | --- | --- |
| Ampere | RTX 3080/3090、A100 | TF32、FP16；A100 与部分 Ampere 支持 BF16 |
| Ada Lovelace | RTX 4090、L40/L40S | FP16/BF16、编译器融合；RTX 4090 不属于 Blackwell |
| Hopper | H100/H200 | BF16/FP8 与 Transformer Engine 可另做专项 |
| Blackwell | RTX 5090、B100/B200/GB200 | BF16、FP8/FP4 专项需匹配工具链和库 |

通用脚本只自动选择 BF16 或 FP16 AMP，不会把普通 PyTorch Autocast 宣称为 Transformer Engine FP8/FP4 实测。FP8/FP4 需要支持的硬件、驱动、CUDA、框架与专用库，无法用低代 GPU 等价模拟。

### 7.3 TF32 对照

Ampere 及以后 NVIDIA GPU 可针对 FP32 矩阵乘设置精度策略：

```python
torch.set_float32_matmul_precision("high")
```

应分别运行默认策略与 `high`，记录误差与吞吐。不要只依据「GPU 属于某架构」就断言一定加速；小矩阵、数据瓶颈或非 GEMM 模型可能看不到明显收益。`high` 允许 TF32（10 位尾数），`medium` 允许 BF16 风格的更低精度路径，两者都会改变数值结果，因此必须同时报告损失差异，而不是只报吞吐。

## 8. 结果分析

### 8.1 优化前后对照模板

| 版本 | AMP | Workers | Compile | P50 ms | P95 ms | Samples/s | Peak MiB | Final Loss |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Baseline | 否 | 0 | 否 | 实测 | 实测 | 实测 | 实测 | 实测 |
| Opt-A | 是 | 0 | 否 | 实测 | 实测 | 实测 | 实测 | 实测 |
| Opt-B | 是 | 最优值 | 否 | 实测 | 实测 | 实测 | 实测 | 实测 |
| Opt-C | 是 | 最优值 | 是 | 实测 | 实测 | 实测 | 实测 | 实测 |

四行是递进关系：Opt-A 只加 AMP，Opt-B 在 A 的基础上加最优 Worker 数，Opt-C 再加编译。每一行与上一行的差值才是该项优化的边际收益；直接拿 Opt-C 与 Baseline 比，只能得到「组合收益」，无法归因。

### 8.2 如何解释结果

- **AMP 变快**：通常意味着 GEMM/卷积占比较高且 Shape 能利用低精度计算单元。
- **AMP 不变或变慢**：模型过小、转换开销占比高、数据管线受限或算子不适配。
- **增加 Worker 变快**：CPU 预处理或数据读取曾让设备等待。
- **增加 Worker 变慢**：进程调度、IPC、内存压力或数据本来就在内存中。
- **`set_to_none=True` 小幅改善**：避免了部分梯度 Tensor 清零写入。
- **Compile 变快**：稳态融合收益超过编译与 Guard 成本。
- **Compile 变慢**：运行太短、Graph Break、重编译、动态 Shape 或模型已被高效库主导。

所有性能数字只对该次硬件、软件、形状、Batch、Worker 与功耗状态成立。本项目的合成数据集完全在内存中，`__getitem__` 只做一次索引，因此 Worker 收益天然偏小——这正好说明「数据管线优化要看真实预处理成本」，不能把合成数据的结论搬到图像解码、tokenize 或远端读取场景。

## 9. 性能回归门禁

保存为 `regression_gate.py`：

```python
#!/usr/bin/env python3
import argparse
import json

def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("candidate")
    parser.add_argument("--max-regression", type=float, default=0.05)
    parser.add_argument("--max-loss-delta", type=float, default=0.20)
    args = parser.parse_args()

    baseline = load(args.baseline)
    candidate = load(args.candidate)
    if baseline["batch_size"] != candidate["batch_size"]:
        raise SystemExit("FAIL: batch_size 不一致，不能直接比较")
    if candidate["valid_step_ratio"] < 1.0:
        raise SystemExit("FAIL: 存在非有限损失或无效 Step")

    ratio = candidate["p50_step_ms"] / baseline["p50_step_ms"]
    loss_delta = abs(candidate["final_loss"] - baseline["final_loss"])
    print(f"p50_ratio={ratio:.4f}, loss_delta={loss_delta:.6f}")
    if ratio > 1.0 + args.max_regression:
        raise SystemExit("FAIL: P50 Step Time 超过回归阈值")
    if loss_delta > args.max_loss_delta:
        raise SystemExit("FAIL: 损失差异超过阈值")
    print("PASS")

if __name__ == "__main__":
    main()
```

运行：

```bash
python regression_gate.py reports/baseline.json reports/optimized.json \
  --max-regression 0.05 --max-loss-delta 0.20
```

门禁的三条判定各有分工：`batch_size` 一致保证比较的是同一个问题；`valid_step_ratio == 1.0` 保证没有 NaN/OOM 换来的虚假加速；`p50_ratio` 与 `loss_delta` 分别守住性能与语义。注意它是**单向门禁**——只拦截回归，不要求必须变快，因此适合放进 CI 作为长期护栏。

真实项目不能只比较单次 P50。建议在相同机器、相同功耗与相同负载下重复 3～5 次，使用中位数，并给短期波动保留容差。`--max-loss-delta 0.20` 只是合成任务上的宽松示例值；真实训练应改为「同种子下损失曲线趋势一致 + 验证集指标不下降」，绝对差阈值在不同任务上不可通用。

## 10. 常见错误与排查

### 10.1 优化版损失与基线完全不能比较

检查随机种子、初始化、数据顺序、有效 Batch Size 与优化器超参数。AMP 会带来合理数值差异，但不应出现 NaN 或完全不同的训练趋势。

### 10.2 CUDA 时间异常小

原因通常是异步执行。确认计时边界含 `torch.cuda.synchronize()`，或使用 CUDA Event。不要在每个算子后同步，那会破坏真实流水线。

### 10.3 `num_workers>0` 卡住

在受限容器、Notebook、Windows 或共享内存不足环境中，先回退到 `--workers 0`。检查 `/dev/shm`、进程启动方式与 Dataset 是否可序列化。

### 10.4 Pinned Memory 没有效果

只有 CPU 到 CUDA 的数据路径才可能受益；数据已在 GPU、Batch 很小或计算时间占主导时收益有限。`non_blocking=True` 也不保证自动产生有效重叠——若紧接着就有依赖该数据的 Kernel，且没有独立 Copy Stream，拷贝仍会串行。

### 10.5 AMP 出现 NaN

脚本在 FP16 时启用 GradScaler；若自定义损失或算子数值范围异常，应定位第一个非有限值。不要为了跑通直接忽略损失。BF16 动态范围与 FP32 相同，通常不需要 GradScaler，这也是脚本优先选 BF16 的原因。

### 10.6 `torch.compile` 首次运行很慢

首次编译与后续稳态必须分开报告。增大热身，检查 Graph Break 与 Recompile；短作业可能不值得编译。

### 10.7 Profiler 结果比正常运行慢很多

Profiler 本身有开销。缩短 Active 窗口，关闭不需要的 `record_shapes`、Memory 与 Stack 采集；最终 Benchmark 不要开 Profiler。

### 10.8 CPU 优化版没有加速

本脚本的核心优化偏向 CUDA，CPU 回退用于方法验证。CPU 性能还受线程数、BLAS、NUMA、内存与算子实现影响，应单独设计实验。

## 11. 常见追问与解答

### 11.1 为什么不能用普通 `time.time()` 直接测 CUDA Kernel

CUDA 默认异步执行，CPU 调用返回时 GPU 可能尚未完成。必须同步计时窗口或使用 CUDA Event。

### 11.2 `zero_grad(set_to_none=True)` 为什么可能更快

它把梯度引用设为 `None`，避免把已有梯度缓冲区逐元素写零，通常减少内存写入；但未产生梯度的参数会被优化器跳过，语义与全零梯度并不完全相同。带 weight decay 或动量的优化器在「梯度为 None」与「梯度为 0」两种情况下行为可能有差别，切换后要核对损失曲线。

### 11.3 为什么更多 DataLoader Worker 不一定更快

Worker 会增加进程调度、IPC、预取与内存开销。若数据生成很轻、已经在内存中或 CPU 核数有限，额外 Worker 可能降低性能。

### 11.4 AMP 的收益取决于什么

取决于四件事：低精度算子（GEMM/卷积）在总时间中的占比；Shape 是否对齐 Tensor Core 的 tile 要求；dtype 转换与 cast 的额外开销；以及是否原本就受数据管线或 Launch 限制。占比高、Shape 合适、开销小、且瓶颈确实在计算时才明显加速；否则可能持平甚至变慢。此外 FP16 需要 GradScaler 维护数值范围，BF16 不需要但尾数更短，两者的损失差异要分别记录。

### 11.5 为什么必须固定有效 Batch Size

吞吐的分子是 $B_{effective}$。若优化版偷偷用了更大的 Batch 或更少的梯度累积步数，Samples/s 上升可能只是「每步做更多工作」，而不是「同样工作做得更快」，同时收敛行为也已改变。回归门禁第一条就检查 `batch_size` 一致，正是为此。

### 11.6 峰值显存为什么要单独报告

`max_memory_allocated` 反映的是分配器视角的峰值，与实际保留显存（`max_memory_reserved`）可能差很多。AMP 通常降低激活显存，但 GradScaler、cast 中间张量与编译缓存可能带来额外占用；只看吞吐会漏掉「更快但更容易 OOM」的配置，而 OOM 重试会直接打掉 Goodput。

## 写在最后

训练优化的难点不在开关本身，而在「保持问题不变的前提下逐项归因」。下一个项目把规模推到 7B 模型，瓶颈会从单卡算子扩展到显存容量、并行策略与集群通信。

下一篇：[7B 模型训练性能 Benchmark](/source/AI-Infra/2-AI系统性能工程/32-7B模型训练性能Benchmark)。
