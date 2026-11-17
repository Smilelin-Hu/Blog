# PyTorch 性能分析体系

本篇建立 PyTorch 训练性能分析体系，学会用 Profiler 与时间线准确定位 CPU、GPU 与数据瓶颈。

性能优化最危险的状态，不是程序慢，而是「凭感觉知道它为什么慢」。GPU 利用率低不等于 GPU 算子慢，某个算子 CUDA 总时间高也不等于优化它就能缩短 Step，显存 reserved 很大也不等于发生了内存泄漏。可行的路径是：先用低扰动基准确认问题，再逐层增加观测强度，最终把端到端慢映射到 Python、Dispatcher、ATen 算子、CUDA Runtime、GPU Kernel、显存分配、数据管线或分布式通信中的具体环节。

## 1. 内容概览

- Benchmark、Profile、Trace 与 Monitor 的分工。
- 异步 CUDA 工作负载的正确测量。
- Self CPU、CPU Total、Self Device、Device Total 的读法。
- `record_function`、Profiler Schedule 与 Chrome/Perfetto Trace。
- allocated、reserved、active、inactive split 与非 PyTorch 显存。
- 数据加载、Python launch、同步、算子碎片化、通信与显存碎片的识别。

## 2. 核心直觉：Profiler 是显微镜，不是测速表

| 工具层 | 核心问题 | 常见输出 |
| --- | --- | --- |
| Benchmark | 到底快不快、是否回归 | 中位数、尾延迟、tokens/s |
| Profiler | 哪些算子最贵 | 算子聚合表、调用栈、shape |
| Trace | 为什么不能重叠、哪里有空洞 | CPU/GPU 时间线、Flow、Kernel |
| Monitor | 是否随时间、温度、负载变化 | 利用率、功耗、时钟、显存曲线 |

四者不能互相替代。正确顺序是先确定性能问题真实存在，再用足够轻的工具缩小范围。Profile 本身有开销，若打开 shape、stack、memory 与长时间 CUDA Activity，观测到的就不再是原始程序。

## 3. 从端到端时间拆开 PyTorch

一次训练 Step 可粗略写成：

$$
T_{step} = T_{input} + T_{H2D} + T_{forward} + T_{backward} + T_{optim} + T_{comm} + T_{sync} + T_{other} - T_{overlap}
$$

这不是把 Profiler 表中每一列直接相加：GPU Kernel、Memcpy、通信与 CPU 工作可能重叠，同一个父算子也包含子算子时间。吞吐为 $Throughput = Work / T_{step}$。

若只优化占 Step 比例 $p$ 的部分并把该部分加速 $s$ 倍，整体加速上限为

$$
Speedup = \frac{1}{(1-p) + p/s}
$$

某个算子占端到端时间 10% 时，即使无限加速，整体也最多约 $1/0.9=1.11\times$。这就是为什么「Top 1 算子」不一定是最值得优化的对象。

## 4. PyTorch 执行链路

一行 `y = model(x)` 大致跨过：

![ai2-19-L49](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l19_01.png)

分析时要问：Python 是否来不及提交工作；是否产生大量细碎 ATen 算子与 Kernel；算子是否触发隐式同步；GPU Kernel 是计算受限、显存带宽受限还是 launch 受限；H2D、NCCL 与计算是否重叠；某个高层 Module 为什么展开成这些低层算子。

PyTorch Profiler 擅长把 Python/ATen 与设备活动关联起来，Nsight Systems 擅长系统级时间线，Nsight Compute 擅长单 Kernel 微架构指标。不要指望一个工具回答全部问题。

## 5. 读懂 Profiler 表

### 5.1 Self 与 Total

假设 `train_step` 包含 `forward`，`forward` 又调用 `aten::mm`：`CPU total` 是该事件及其子事件在 CPU 侧的总时间；`Self CPU` 是扣除子事件后该事件自身的 CPU 时间；`Device total` 是该事件及子事件关联的设备活动总时间；`Self Device` 是归属于该事件自身、不含子事件的设备活动。父级 `forward` 的 total 很大很正常；寻找叶子热点时更关注 Self，理解模块成本时看 Total。

### 5.2 CPU 时间不等于 GPU 执行时间

CUDA launch 通常异步，CPU 可能只花几十微秒提交一个运行数毫秒的 Kernel。普通 Python 计时若不在边界同步，测到的主要是提交时间：

```python
torch.cuda.synchronize()
start = time.perf_counter()
run()
torch.cuda.synchronize()
elapsed = time.perf_counter() - start
```

微基准优先使用 `torch.utils.benchmark.Timer` 或 CUDA Event，端到端基准必须明确同步边界。

### 5.3 Count 是重要信号

某个算子单次只占 5 微秒，但每 Step 调用 10,000 次，总开销仍可能巨大。高 Count 常提示：Python 循环没有向量化；Pointwise 算子没有 Fusion；输入被切成大量小块；日志、`.item()` 或小 Tensor 创建太频繁。

### 5.4 Shape、Stack 与 Memory 都有代价

`record_shapes=True`、`with_stack=True`、`profile_memory=True` 能提供强证据，但会增加开销，shape 记录还可能延长 Tensor 生命周期。先用轻配置找到可疑窗口，再对 2–5 个 Step 开启重配置。

## 6. 诊断阶梯：从轻到重

| 层级 | 手段 | 关注点 |
| --- | --- | --- |
| A 稳定基准 | 固定模型、shape、dtype、batch、线程数、种子与设备状态 | warmup 后多次结果的中位数与分位数 |
| B 快速入口 | `python -m torch.utils.bottleneck your_script.py` | cProfile + Autograd Profiler 摘要，仅第一轮筛查 |
| C 算子聚合 | `torch.profiler.profile` + `key_averages()` | CPU-bound 按 `self_cpu_time_total`、GPU-bound 按设备 self time、碎片看 Count、特化按 shape 分组 |
| D 时间线 | 导出 Chrome Trace，用 Perfetto UI 查看 | launch 与执行之间的空洞、Memcpy 是否串行、阶段是否清晰、频繁 `cudaDeviceSynchronize`、多 Stream 是否真重叠 |
| E 显存快照 | PyTorch Memory Snapshot | Segment/Block、分配释放历史、OOM 时状态；只看 PyTorch allocator 管理的内存 |
| F 系统与 Kernel | Nsight Systems / Nsight Compute / DCGM | 全局时间线、单 Kernel Roofline 与 Occupancy、长时间温度功耗时钟 |

CUDA 异步会让普通 CPU Profile 产生误导，因此 Level B 只用于筛查；NCCL 或其他 CUDA 库直接分配的显存在 Memory Snapshot 中可能不可见。

## 7. 常见性能形态

**CPU launch-bound**：GPU 时间线上大量短 Kernel、中间有空洞，CPU 线程持续忙于 Python/Dispatcher，GPU 利用率锯齿。候选优化是向量化、算子融合、`torch.compile`、CUDA Graph、减少 Python 控制流。

**数据管线饥饿**：Step 开头长时间没有 GPU 活动，`enumerate(DataLoader)` 或预处理范围很长，CPU/磁盘忙。候选优化是合理 workers、Pinned Memory、批量 H2D、`non_blocking=True`、缓存与异步预取；必须区分 DataLoader 慢与 H2D 慢。

**隐式同步**：热路径调用 `.item()`、把 CUDA Tensor 打印或转为 NumPy、频繁查询需要设备结果的属性、错误的计时同步。现象是 CUDA Runtime 线程出现同步调用、CPU 等待 GPU、流水线被切断。

**算子碎片化**：大量 `aten::add`、`mul`、`copy_`、小 reduction，单个很快但总数极多。候选优化是 Fusion、in-place（先确认 Autograd 正确性）、布局调整、编译器捕获；优化前要确认不是 Profile 本身制造了额外开销。

**显存碎片或泄漏**：`allocated` 持续上涨可能有 Tensor 被 Python 容器、闭包或计算图引用；`reserved` 高但 `allocated` 低可能是缓存池正常行为，也可能有不可复用碎片；`nvidia-smi` 高于 PyTorch 可能包含 CUDA Context、NCCL、第三方库或其他进程。`empty_cache()` 只能释放完全空闲的缓存 Segment，不会释放仍被 Tensor 引用的内存，也通常不是训练循环里的性能优化。

**分布式慢 rank**：平均 rank 没有意义，Collective 会等待最慢 rank。每个 rank 单独保存 trace，用相同 Step ID 对齐，寻找数据、日志、checkpoint 或拓扑差异。

## 8. 关键性能模型

**Profiler 扰动**：设原始耗时 $T$、采集事件/栈/shape 与写 trace 的开销 $O_p$，则 $T_{profile}=T+O_p$。需要优化的是原始 $T$，因此性能结论必须回到无 Profiler 基准复验。

**GPU 空闲比例**：

$$
IdleRatio = 1 - \frac{T_{GPU\ busy}}{T_{step}}
$$

多 Stream 有重叠时不能简单把所有 Kernel duration 相加，应对时间轴区间求并集。

**尾延迟与方差**：$CV=\sigma/\mu$。均值相近但 CV 或 P99 变差，通常意味着动态 shape、GC、数据 I/O、后台进程、温度/时钟或周期性 checkpoint。性能工程不能只报最优单次结果。

## 9. Level 0：纯 Python Trace 摘要诊断

没有 PyTorch、没有 GPU 也能运行。它不模拟 CUDA，只训练「如何把现象转成可验证假设」。保存为 `profile_summary_analyzer.py`：

```python
#!/usr/bin/env python3
import argparse, json, statistics

SAMPLE = [
    {"step_ms": 120, "gpu_busy_ms": 70, "input_ms": 32, "launch_gap_ms": 12, "sync_ms": 3, "memory_mb": 5200},
    {"step_ms": 124, "gpu_busy_ms": 71, "input_ms": 35, "launch_gap_ms": 13, "sync_ms": 3, "memory_mb": 5310},
    {"step_ms": 130, "gpu_busy_ms": 72, "input_ms": 39, "launch_gap_ms": 14, "sync_ms": 4, "memory_mb": 5430},
    {"step_ms": 138, "gpu_busy_ms": 73, "input_ms": 44, "launch_gap_ms": 15, "sync_ms": 5, "memory_mb": 5560},
    {"step_ms": 146, "gpu_busy_ms": 74, "input_ms": 49, "launch_gap_ms": 16, "sync_ms": 6, "memory_mb": 5700},
]

def percentile(values, q):
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac

def slope(values):
    n = len(values)
    x_mean, y_mean = (n - 1) / 2, statistics.mean(values)
    num = sum((i - x_mean) * (y - y_mean) for i, y in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n)) or 1
    return num / den

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", help="JSON 文件，内容为 step 记录数组")
    a = p.parse_args()
    rows = json.load(open(a.input, encoding="utf-8")) if a.input else SAMPLE
    if not rows:
        raise SystemExit("没有记录")

    steps = [r["step_ms"] for r in rows]
    idle = [1 - r["gpu_busy_ms"] / r["step_ms"] for r in rows]
    report = {
        "step_p50_ms": round(percentile(steps, 0.50), 2),
        "step_p95_ms": round(percentile(steps, 0.95), 2),
        "mean_gpu_idle_ratio": round(statistics.mean(idle), 3),
        "input_mean_ms": round(statistics.mean(r["input_ms"] for r in rows), 2),
        "launch_gap_mean_ms": round(statistics.mean(r["launch_gap_ms"] for r in rows), 2),
        "sync_mean_ms": round(statistics.mean(r["sync_ms"] for r in rows), 2),
        "memory_growth_mb_per_step": round(slope([r["memory_mb"] for r in rows]), 2),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    hypotheses = []
    if report["mean_gpu_idle_ratio"] > 0.25:
        hypotheses.append("GPU 空闲较多：先检查输入管线和 CPU launch 空洞")
    if report["input_mean_ms"] > 0.20 * report["step_p50_ms"]:
        hypotheses.append("输入阶段占比高：用 record_function 拆 DataLoader/H2D/预处理")
    if report["launch_gap_mean_ms"] > 0.08 * report["step_p50_ms"]:
        hypotheses.append("launch gap 偏高：检查小算子、Python 循环与同步")
    if report["memory_growth_mb_per_step"] > 5:
        hypotheses.append("显存随 step 上涨：检查 Tensor/计算图引用并抓 Memory Snapshot")
    print("\n优先验证的假设：")
    for i, text in enumerate(hypotheses or ["未触发规则，扩大采样窗口"], 1):
        print(f"{i}. {text}")

if __name__ == "__main__":
    main()
```

```bash
python3 profile_summary_analyzer.py
```

脚本会指出 GPU 空闲、输入占比、launch gap 与显存增长风险。规则只生成假设，不能直接宣判根因，下一步要用 PyTorch Profiler 或 Memory Snapshot 验证。

## 10. Level 1：CPU/GPU 通用 Profiler 实验

保存为 `pytorch_profile_lab.py`，对照「Python 行循环预处理」与「按维度归约 + 广播」两种写法：

```python
#!/usr/bin/env python3
import argparse, contextlib, json, os, time
import torch
import torch.nn as nn
from torch.profiler import ProfilerActivity, profile, record_function

class MLP(nn.Module):
    def __init__(self, width, depth):
        super().__init__()
        layers = []
        for _ in range(depth):
            layers += [nn.Linear(width, width), nn.GELU()]
        layers += [nn.Linear(width, width)]
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x)

@contextlib.contextmanager
def phase(name, use_nvtx):
    if use_nvtx:
        torch.cuda.nvtx.range_push(name)
    try:
        with record_function(name):
            yield
    finally:
        if use_nvtx:
            torch.cuda.nvtx.range_pop()

def preprocess(x, mode):
    if mode == "baseline":
        # 故意保留 Python 循环和许多小 Tensor 操作
        return torch.stack([(row - row.mean()) / (row.std() + 1e-5) for row in x])
    return (x - x.mean(dim=1, keepdim=True)) / (x.std(dim=1, keepdim=True) + 1e-5)

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["baseline", "optimized"], required=True)
    p.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--depth", type=int, default=4)
    p.add_argument("--steps", type=int, default=8)
    p.add_argument("--with-stack", action="store_true")
    p.add_argument("--memory-snapshot", action="store_true")
    p.add_argument("--out", default="profiler_artifacts")
    return p.parse_args()

def main():
    args = parse_args()
    has_cuda = torch.cuda.is_available()
    device = "cuda" if args.device == "auto" and has_cuda else args.device
    if device == "auto":
        device = "cpu"
    if device == "cuda" and not has_cuda:
        raise SystemExit("请求 CUDA，但 torch.cuda.is_available() 为 False")

    os.makedirs(args.out, exist_ok=True)
    torch.manual_seed(2026)
    use_cuda = device == "cuda"
    if use_cuda:
        prop = torch.cuda.get_device_properties(0)
        print({"torch": torch.__version__, "cuda": torch.version.cuda, "gpu": prop.name,
               "cc": f"{prop.major}.{prop.minor}", "vram_gib": round(prop.total_memory / 1024**3, 2)})
    else:
        print({"torch": torch.__version__, "device": "cpu", "threads": torch.get_num_threads()})

    model = MLP(args.width, args.depth).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)
    host_batch = torch.randn(args.batch, args.width)
    if args.memory_snapshot and use_cuda:
        torch.cuda.memory._record_memory_history(max_entries=100000)

    def train_step():
        optimizer.zero_grad(set_to_none=True)
        with phase("input/preprocess", use_cuda):
            x = preprocess(host_batch, args.mode)
        with phase("input/h2d", use_cuda):
            x = x.to(device, non_blocking=use_cuda)
        with phase("model/forward", use_cuda):
            y = model(x)
            loss = y.float().square().mean()
        with phase("model/backward", use_cuda):
            loss.backward()
        with phase("optimizer/step", use_cuda):
            optimizer.step()
        return loss.detach()

    # 无 Profiler 预热，隔离 CUDA 初始化与优化器状态首次创建
    for _ in range(3):
        train_step()
    if use_cuda:
        torch.cuda.synchronize()
        torch.cuda.reset_peak_memory_stats()

    # 先做低扰动端到端计时
    start = time.perf_counter()
    for _ in range(args.steps):
        train_step()
    if use_cuda:
        torch.cuda.synchronize()
    elapsed = time.perf_counter() - start
    benchmark = {"mode": args.mode, "device": device,
                 "step_ms": elapsed * 1000 / args.steps,
                 "samples_per_s": args.batch * args.steps / elapsed}
    if use_cuda:
        benchmark.update({"peak_allocated_gib": torch.cuda.max_memory_allocated() / 1024**3,
                          "peak_reserved_gib": torch.cuda.max_memory_reserved() / 1024**3})
    print("BENCHMARK", json.dumps(benchmark, ensure_ascii=False))

    activities = [ProfilerActivity.CPU] + ([ProfilerActivity.CUDA] if use_cuda else [])

    def save_trace(prof):
        path = os.path.join(args.out, f"{args.mode}_step_{prof.step_num}.json")
        prof.export_chrome_trace(path)
        print("TRACE", path)

    schedule = torch.profiler.schedule(wait=1, warmup=1, active=3, repeat=1)
    with profile(activities=activities, schedule=schedule, on_trace_ready=save_trace,
                 record_shapes=True, profile_memory=True,
                 with_stack=args.with_stack, with_flops=True) as prof:
        # wait + warmup + active = 5；多跑一步确保 cycle 结束并导出
        for _ in range(6):
            train_step()
            prof.step()

    sort_key = "self_cuda_time_total" if use_cuda else "self_cpu_time_total"
    print(prof.key_averages().table(sort_by=sort_key, row_limit=20))
    if args.memory_snapshot and use_cuda:
        path = os.path.join(args.out, f"{args.mode}_memory_snapshot.pickle")
        torch.cuda.memory._dump_snapshot(path)
        print("MEMORY_SNAPSHOT", path)

if __name__ == "__main__":
    main()
```

```bash
# CPU 回退
python pytorch_profile_lab.py --mode baseline --device cpu --width 512
python pytorch_profile_lab.py --mode optimized --device cpu --width 512
# 自动选择 GPU
python pytorch_profile_lab.py --mode baseline --device auto
python pytorch_profile_lab.py --mode optimized --device auto
# 只在缩小窗口后开启 stack 和显存历史
python pytorch_profile_lab.py --mode baseline --device cuda \
  --with-stack --memory-snapshot --steps 10
```

查看输出：把 `profiler_artifacts/*.json` 拖入 Perfetto UI 或兼容 Trace Viewer；把 `*_memory_snapshot.pickle` 拖入 PyTorch Memory Visualizer。快照可能包含调用栈、路径与张量信息，外发前按组织安全规范处理。

预期现象：Baseline 的 `input/preprocess` 更长并出现更多小算子调用；Optimized 用按维度归约与广播替代 Python 行循环，CPU launch 数减少；GPU 上端到端加速幅度取决于预处理占比，模型 GEMM 很重时 Amdahl 定律会限制收益；Profile 运行时间会比无 Profile Benchmark 慢，不能拿两者直接算优化加速比；具体数值只属于该次环境。

## 11. Level 2：GPU 与多卡专项

| 平台 | PyTorch Profiler | Nsight Systems/Compute | 架构专项注意 |
| --- | --- | --- | --- |
| Ampere RTX 3080/3090、A100 | 支持 | 支持 | 3080 双卡通常走 PCIe；A100 视 PCIe/SXM 拓扑 |
| Ada RTX 4090、L40/L40S | 支持 | 支持 | 4090 是 Ada 且无 NVLink |
| Hopper H100/H200 | 支持 | 支持 | 可另测 Transformer Engine/FP8，但不是通用基线 |
| Blackwell RTX 5090、B100/B200/GB200 | 支持 | 需匹配新版本工具链 | 消费卡与 NVLink/NVSwitch 数据中心系统不可等价 |

Profiler 方法本身跨架构通用，Kernel 名称、可用 dtype、性能计数器与工具版本并不通用。脚本已用 NVTX 标出阶段，可用 Nsight Systems 交叉验证：

```bash
nsys profile --help
nsys profile --trace=cuda,nvtx,osrt,cublas \
  --output=pytorch_systems --force-overwrite=true \
  python pytorch_profile_lab.py --mode baseline --device cuda --steps 10
```

交叉检查的内容：NVTX 阶段与 CUDA Kernel 的对应关系是否与 Profiler 表一致；`record_function` 标出的 input 阶段里 GPU 是否真的空闲；是否存在 Profiler 未归因的 Memcpy 或 NCCL 活动；隐式同步在 CUDA API 行上的位置。多卡场景要为每个 rank 单独导出 trace 并按 Step ID 对齐，最终结论仍回到关闭 Profiler 的端到端基准。

## 写在最后

分析体系的价值在于「观测强度递增、结论可回归」：先有稳定基准，再按阶梯加观测，最后把假设落回单变量改动与无 Profiler 复验。下一篇进入 `torch.compile`，看编译器如何自动消除这里发现的小算子与 launch 空洞。

下一篇：[torch.compile 深度解析](/source/AI-Infra/2-AI系统性能工程/20-torchcompile深度解析)。