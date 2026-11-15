# AI Systems Performance Engineering 概述

本篇从端到端视角建立 AI 系统性能工程的基本方法，把「设备很忙」转化为可测量的有效产出。

## 1. 内容概览

AI Systems Performance Engineering，中文可译为「AI 系统性能工程」。它研究的不是某个孤立算子能跑多快，而是：**怎样让模型、算法、编译器、Runtime、GPU、CPU、内存、网络、存储和调度系统协同工作，以更低成本稳定完成更多有效任务。**

这里不会把「GPU 利用率 100%」当作终点。GPU 可以一直忙碌，却可能在重复计算、等待同步、执行低效 Kernel，甚至反复重跑已经失败的任务。真正要优化的是业务得到的有效结果，例如：

- 训练在目标时间内完成了多少有效样本或 Token。
- 推理在延迟 SLO 内成功返回了多少请求。
- 每块 GPU、每美元、每焦耳电能产出了多少有效 Token。
- 系统扩展到更多 GPU 后，新增硬件是否转化成了接近等比例的有效吞吐。
- 优化是否保持数值正确、模型质量、稳定性和可复现性。

整套方法可以概括为 **profile-first、goodput-driven**：先测量，再定位；先证明瓶颈，再改动；最后用相同工作负载验证收益，而不是凭感觉「调几个参数」。

## 2. 本篇要点

1. 用一句话解释 AI 系统性能工程与普通模型开发、CUDA Kernel 优化、运维监控的区别。
2. 画出 AI 工作负载从数据到 GPU、再到网络和服务端的端到端路径。
3. 区分「设备忙碌」「原始吞吐」和「有效工作吞吐 Goodput」。
4. 用分层时间模型拆解训练或推理延迟，而不是看到 GPU 利用率低就直接加 Batch Size。
5. 建立可复现的优化闭环：基线、假设、剖析、改动、正确性验证、回归保护。
6. 识别「看起来更快、实际不可比」的常见 Benchmark 陷阱。

## 3. 阅读前提

只需具备：能读基础 Python；知道训练包含前向、损失、反向和参数更新；知道 CPU、GPU、显存和主存不是同一种资源；会在终端运行 Python。

不要求提前掌握 CUDA、NCCL、Triton 或分布式训练，后续篇目会逐层展开。

## 4. 核心直觉：性能问题通常不在「最显眼」的地方

想象一家高度自动化的餐厅：GPU 是后厨里速度极快的厨师；HBM/显存是他伸手可取的操作台；CPU 和主存是备菜区；PCIe、NVLink 和网络是传菜通道；数据加载器是采购与洗切流程；Runtime 和调度器决定下一道菜什么时候进厨房；模型算法是菜谱；用户请求或训练样本是订单。

购买更快的厨师，并不保证餐厅每小时能完成更多订单。如果备菜慢、传菜通道拥堵、菜单切换频繁、多个厨师互相等待，后厨即使「看起来很忙」，顾客仍然要排队。

AI 系统也是如此：端到端性能取决于整条链路中最限制有效产出的环节。单个 Kernel 快 20%，如果它只占总时间的 5%，端到端最多也只改善一点点；反过来，一个看似不起眼的数据等待如果占到每步时间的一半，消除它可能比重写核心算子更有价值。

由此得到两条贯穿始终的直觉：

1. **局部峰值不等于端到端结果。**
2. **优化的本质不是让所有部件都更忙，而是减少完成有效工作所需的时间、资源和失败重做。**

## 5. 这个角色在做什么

AI Systems Performance Engineer 位于算法、框架、编译器和基础设施的交叉点。典型工作包括：

- 建立训练、推理和算子的性能基线。
- 使用 PyTorch Profiler、Nsight Systems、Nsight Compute 等工具定位瓶颈。
- 分析 GPU Kernel、显存访问、Runtime 调度和 CPU 数据管线。
- 优化 DP、FSDP、TP、PP、CP、EP 等并行策略及其通信。
- 设计 Continuous Batching、KV Cache、推测解码和解耦式推理系统。
- 建立性能回归测试、硬件分层基线和可复现实验规范。
- 在速度、显存、模型精度、可靠性、能耗和成本之间做工程权衡。

| 角色 | 首要问题 | 性能工程师的补充视角 |
| --- | --- | --- |
| 算法/研究工程师 | 模型是否更准、能力是否更强 | 相同质量下能否更快、更省、更稳定地训练和服务 |
| CUDA/算子工程师 | 单个 Kernel 是否高效 | 这个 Kernel 是否真是端到端瓶颈，收益是否被其他层抵消 |
| 平台/SRE 工程师 | 服务是否稳定、资源是否可调度 | 调度、拓扑和资源隔离是否伤害有效吞吐与尾延迟 |
| 推理工程师 | 请求能否低延迟返回 | TTFT、TPOT、吞吐、KV Cache、批处理和 SLO 如何联合优化 |
| 训练工程师 | 模型能否正确收敛 | MFU、通信气泡、数据等待、Checkpoint 和故障恢复损失多大 |

成熟的性能工程师不会只问「哪里慢」，还会问：

- 慢是相对于什么基线？
- 工作负载是否一致？
- 结果是否保持正确？
- 优化改善的是平均值还是 P95/P99？
- 是否只是把开销移动到了另一个阶段？
- 在另一张卡、另一版本和另一输入分布上是否仍然成立？

## 6. 现代 AI 系统的端到端路径

一个典型训练或推理系统可以抽象为：数据读取 → 解码与分词 → 组批 → Host→Device 拷贝 → 前向/反向计算 → 集合通信 → 优化器更新 → 检查点/输出。任何一层都可能成为瓶颈，而且瓶颈会随工作负载变化：

- 短 Prompt、低 Batch 推理往往更容易受调度和 Kernel Launch 开销影响。
- 长上下文 Prefill 更接近大矩阵计算和显存带宽问题。
- Decode 每步处理的 Token 少，常受权重读取、KV Cache 和批处理效率限制。
- 单卡训练可能是计算或显存瓶颈，多卡后通信和负载不均会迅速显现。
- 小模型在高端 GPU 上反而容易「喂不饱」，Python 和 CPU 开销占比会更高。

因此性能分析必须先固定场景：训练还是推理、模型多大、输入长度如何分布、Batch 策略是什么、硬件和版本是什么、目标是吞吐还是尾延迟。

## 7. 机械同理心：让算法理解硬件

「机械同理心」（Mechanical Sympathy）指软件设计者理解硬件真正擅长和不擅长什么，并据此组织算法和数据。

以 Attention 为例，朴素实现会产生大型中间矩阵并在显存中多次读写。FlashAttention 的关键价值不是改变 Attention 的数学定义，而是改变计算顺序和分块方式，让更多中间结果停留在更快的片上存储中，从而减少 HBM 搬运。

相同思想贯穿整个 AI Infra：

- 把连续线程要访问的数据放在连续地址中，形成合并访存。
- 使用适合 Tensor Core 的数据类型和矩阵形状。
- 把通信与反向计算重叠。
- 将多个小 Kernel 融合，减少 Launch 和中间张量读写。
- 根据 Prefill 和 Decode 的资源特征选择不同硬件或独立资源池。
- 通过 Paged KV Cache 减少碎片并提高可调度请求数。

机械同理心不是「为某一张 GPU 写死代码」，而是检测能力、选择合适路径，并明确不同路径的精度和性能边界。

## 8. 关键性能模型

### 8.1 端到端时间分解

先把一次训练 Step 或一次请求的时间写成：

$$
T_{e2e} = T_{input} + T_{transfer} + T_{compute} + T_{communication} + T_{runtime} + T_{idle} + T_{recovery}
$$

- $T_{input}$：读取、解码、分词、数据增强和组批。
- $T_{transfer}$：CPU 与 GPU、GPU 与 GPU 之间的数据搬运。
- $T_{compute}$：真正的前向、反向、采样或算子计算。
- $T_{communication}$：AllReduce、AllGather、ReduceScatter、All-to-All 等。
- $T_{runtime}$：Python、Dispatcher、Kernel Launch、内存分配和同步。
- $T_{idle}$：气泡、负载不均、锁和队列等待。
- $T_{recovery}$：失败重启、Checkpoint 回滚和重算摊销到有效工作中的成本。

这个加法模型适用于没有重叠的直觉分析。如果输入、传输、计算和通信能够流水化，稳态时间更接近关键路径的最大值：

$$
T_{steady} \approx \max(T_{input}, T_{transfer}, T_{compute}, T_{communication}) + T_{unhidden}
$$

优化预取、异步拷贝和通信重叠，实质上就是在把「相加的等待」变成「被其他工作隐藏的等待」。

### 8.2 Latency 与 Throughput

$$
\mathrm{Latency}_{avg} = \frac{\sum_{i=1}^{N} T_i}{N}, \qquad
\mathrm{Throughput} = \frac{\text{Useful Work}}{\text{Wall Clock Time}}
$$

训练中的 Useful Work 可以是样本或 Token；推理中可以是成功请求、输入 Token、输出 Token。不要把单位省略，因为 `requests/s`、`tokens/s` 和 `sequences/s` 不是同一个指标。

### 8.3 Goodput：真正完成的有效工作

两个互补定义：

$$
\mathrm{Goodput}_{abs} = \frac{\text{Correct and SLO compliant work}}{\text{Total wall time}}, \qquad
\mathrm{Goodput}_{ratio} = \frac{\text{Measured useful throughput}}{\text{Reference useful throughput}}
$$

对训练，只有真正推进了有效训练进度、且最终没有因失败而丢失的 Step 才算有效工作；对在线推理，超过延迟 SLO、失败或被取消的请求，即使消耗了 GPU，也未必算业务 Goodput。

教学实验中常用「计算阶段时间 / 总时间」构造 Goodput Ratio：$G_{lab} = T_{useful\ compute} / T_{wall}$。它不是生产系统的通用定义，但能直观看到输入等待如何侵蚀有效计算占比。

### 8.4 Speedup 与 Amdahl 定律

$$
\mathrm{Speedup} = \frac{T_{before}}{T_{after}}, \qquad
S_{total} = \frac{1}{(1-p) + \dfrac{p}{s}}
$$

若某部分占原总时间比例 $p$、被加速 $s$ 倍，则端到端加速上限如上式。举例：某 Kernel 占总时间 10%，即使把它加速到无限快，端到端也只有 $1/(1-0.1) = 1.11\times$。这解释了为什么「优化最酷的 Kernel」不一定比「消除最大的等待」更有价值。

### 8.5 扩展效率

$$
\mathrm{Scaling\ Efficiency} = \frac{X_N}{N \cdot X_1}
$$

如果单卡 1000 tokens/s、8 卡只有 5600 tokens/s，则扩展效率为 70%；剩余 30% 消耗在通信、同步、负载不均和额外 Runtime 上。

### 8.6 成本与能效

$$
\mathrm{Cost\ per\ 1M\ tokens} = \frac{\text{Total cost}}{\text{Completed tokens}} \times 10^6, \qquad
\mathrm{Tokens\ per\ Joule} = \frac{\text{Completed tokens}}{\text{Average power} \times \text{Time}}
$$

工程目标通常是多目标的：低延迟可能要求保留空闲容量，从而降低设备利用率；最大吞吐可能增加排队时间；低精度可能提高速度，却需要验证模型质量。不存在脱离约束的「绝对最优」。

## 9. 瓶颈分类与分析方法

### 9.1 六类常见瓶颈

| 类型 | 常见信号 | 首先验证什么 |
| --- | --- | --- |
| 计算瓶颈 | 大型 GEMM/Attention 占据关键路径 | 数据类型、Tensor Core、算子形状、实际 FLOPs/s |
| 显存瓶颈 | OOM、频繁分配、显存碎片、换入换出 | 峰值显存、张量生命周期、激活/KV Cache/优化器占用 |
| 带宽/访存瓶颈 | GPU 很忙但计算单元吞吐不高 | 算术强度、HBM 流量、合并访存、数据复用 |
| Runtime/Launch 瓶颈 | 大量很短的 Kernel，GPU 时间线有空洞 | Python 开销、Launch 数、同步、Fusion、CUDA Graph |
| 输入/系统瓶颈 | GPU 周期性空闲，CPU 或存储先满 | DataLoader、解码、页锁定内存、NUMA、I/O、预取 |
| 通信/调度瓶颈 | 多卡扩展效率下降、长尾 Rank 拖慢 | Collective 时间、拓扑、Bucket、负载均衡、网络热点 |

### 9.2 标准优化闭环

把每次优化写成可审计的实验：**固定工作负载 → 采集基线 → 提出瓶颈假设 → 用 profiler 取证 → 单变量改动 → 验证正确性 → 复测同负载 → 记录回归门禁**。任何一步缺失，结论都不能算成立。

### 9.3 一份合格的 Benchmark 至少记录什么

- GPU/CPU 型号、GPU Compute Capability 和显存。
- 驱动、CUDA Runtime、PyTorch、Python 和关键依赖版本。
- 模型、精度、Batch Size、序列长度、输入分布。
- Warmup 次数、正式迭代次数、同步方式。
- 平均值、中位数、P95/P99、吞吐和峰值显存。
- 是否启用编译、AMP、TF32、CUDA Graph、FlashAttention。
- 正确性容差和模型质量指标。
- 功耗、温度、时钟或共享机器干扰（需要严谨比较时）。
- 原始日志、命令、代码版本和随机种子。

## 10. 完整可运行实验：数据等待怎样吞噬 Goodput

### 10.1 实验目的

构造一个小型 MLP 训练任务，并人为加入可控的「数据准备延迟」：

- **Baseline**：每一步先同步等待数据准备，再执行训练。
- **Prefetch**：后台线程提前准备下一批数据，使数据等待与当前计算重叠。
- 两条路径使用相同模型、相同 Batch、相同数据顺序和相同步数。
- 输出 Step Latency、Samples/s、教学用 Goodput Ratio 和最终 Loss。

这个实验不是为了证明「线程预取永远有效」，而是让端到端优化的核心变得可见：**只要两个阶段能并行，关键路径就有机会从相加变成取最大值。**

### 10.2 硬件适配层级

- **Level 0：CPU 回退**。任意安装了 PyTorch 的电脑都能运行。
- **Level 1：通用 NVIDIA GPU**。自动识别设备、显存和 Compute Capability，适用于常见 Ampere、Ada、Hopper、Blackwell 及其他 CUDA GPU。
- **Level 2：Nsight Systems 可选**。仅在装有 Nsight Systems 的 NVIDIA 环境采集时间线。

### 10.3 实验代码

```python
import time
import threading
import queue

import torch
import torch.nn as nn

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
BATCH, DIM, HIDDEN, STEPS = 256, 512, 1024, 200
DATA_DELAY = 0.004  # 每批数据准备耗时（秒），人为放大

torch.manual_seed(0)
model = nn.Sequential(
    nn.Linear(DIM, HIDDEN), nn.GELU(),
    nn.Linear(HIDDEN, HIDDEN), nn.GELU(),
    nn.Linear(HIDDEN, 1),
).to(DEVICE)
opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
crit = nn.MSELoss()


def make_batch(step):
    if DATA_DELAY:
        time.sleep(DATA_DELAY)  # 模拟取数/解码/组批
    x = torch.randn(BATCH, DIM)
    y = x.sum(dim=1, keepdim=True) * 0.1
    return x.to(DEVICE), y.to(DEVICE)


def run(mode):
    if mode == "prefetch":
        q = queue.Queue(maxsize=2)

        def producer():
            for s in range(STEPS):
                q.put(make_batch(s))

        th = threading.Thread(target=producer, daemon=True)
        th.start()

    t0 = time.perf_counter()
    compute_time = 0.0
    for step in range(STEPS):
        tc = time.perf_counter()
        if mode == "baseline":
            x, y = make_batch(step)
        else:
            x, y = q.get()
        compute_time += time.perf_counter() - tc

        opt.zero_grad(set_to_none=True)
        loss = crit(model(x), y)
        loss.backward()
        opt.step()

    wall = time.perf_counter() - t0
    return wall, compute_time, loss.item()


for mode in ("baseline", "prefetch"):
    wall, compute_time, last_loss = run(mode)
    print(
        f"{mode:9s} wall={wall:.3f}s  step={wall/STEPS*1000:.2f}ms  "
        f"{STEPS*BATCH/wall:8.1f} samples/s  "
        f"goodput_ratio={compute_time/wall:.3f}  loss={last_loss:.4f}"
    )
```

### 10.4 怎么读结果

- **Baseline** 的 `wall` 里包含每次 `DATA_DELAY` 的串行等待，`goodput_ratio` 明显偏低。
- **Prefetch** 把取数放到后台线程，稳态下 `wall` 接近计算时间，`goodput_ratio` 上升。
- 若 `DATA_DELAY` 很大而计算很短，预取收益会被「生产速度仍跟不上」封顶——这正是端到端分析的意义：**先看关键路径，再谈优化**。

### 10.5 环境与运行

推荐新建隔离环境：

```bash
conda create -n aiperf python=3.10 -y
conda activate aiperf
pip install torch
python ai_perf_intro_lab.py
```

Windows PowerShell 激活命令为 `conda activate aiperf`。如果需要特定 CUDA 构建，不要盲目复制网络上的 `cuXXX` 安装地址，请使用 PyTorch 官方安装选择器，按驱动、操作系统和当前稳定版本选择命令。

## 写在最后

本篇建立的是「怎么问问题」的框架：先固定场景，再定位瓶颈，最后用同一工作负载证明收益。下一篇把「性能」拆成可量化、可对比的指标体系。

下一篇：[AI 系统性能指标体系](/source/AI-Infra/2-AI系统性能工程/02-AI系统性能指标体系)。
