# MoE 推理与未来 AI Runtime

本篇梳理 MoE 推理的专家路由、负载均衡与通信挑战，并展望下一代 AI Runtime 的演进方向。

Dense 模型对每个 Token 都激活同一套参数，模型越大，每个 Token 的计算与显存带宽成本通常越高。Mixture of Experts（MoE）换了一种扩展方式：把 FFN 拆成许多专家，由 Router 为每个 Token 只选择少量专家。这让模型可以拥有很大的总参数容量，同时把单 Token 激活计算控制在较小范围。

但「少算参数」不等于「系统天然更快」。所有专家权重仍要被存放；Token 会被动态发送到不同 GPU；热门专家形成尾部慢 Rank；小批 Decode 还会把 GEMM 切得很碎。因此 MoE 是最能体现 AI Systems Performance Engineering 的模型之一：算法稀疏性只有经过 Router、Dispatch、All-to-All、Grouped GEMM、Combine、负载均衡与 Runtime 调度的协同，才能变成实际速度。

MoE 也是正式内容的收束点：从这里出发，可以连接未来 AI Runtime 的关键方向——动态并行、计算通信融合、分层 KV、推测执行、解耦推理、拓扑感知与 SLO 驱动自治。

## 1. 内容概览

- Total Parameters 与 Activated Parameters 的区别。
- Top-K Router、容量因子、负载不均衡与通信量的推导。
- Route → Dispatch → Expert Compute → Combine 数据流。
- TP、EP、ETP、DP/Attention DP 与 Wide-EP 的区分。
- 用每专家 Token 数、最大/平均负载、All-to-All 带宽与 Grouped GEMM 效率定位瓶颈。
- CPU 上的路由倾斜模拟，以及通用 PyTorch 环境下的逐 Token 与分组专家执行对比。
- 双 RTX 3080、RTX 4090、H100/H200、RTX 5090 与 B200/GB200 的实验边界。
- 未来 Runtime 为什么必须从「执行模型」升级为「持续控制系统」。

前置知识：Transformer FFN、Softmax、Top-K；Tensor/Data/Pipeline/Expert Parallel；NCCL Collective、All-to-All、NVLink/NVSwitch 与 RDMA；Continuous Batching、KV Cache、Speculative Decoding、Disaggregated Inference。

## 2. 核心直觉：MoE 把算力问题变成了数据搬运与排队问题

Dense FFN 对所有 Token 执行同一个函数：

$$
y = \operatorname{FFN}(x)
$$

MoE 有 $E$ 个专家。Router 为 Token $x$ 计算分数，选择 Top-K 专家集合 $\mathcal{T}(x)$：

$$
p(x) = \operatorname{softmax}(W_r x)
$$

$$
y = \sum_{e \in \mathcal{T}(x)} p_e(x)\,\operatorname{Expert}_e(x)
$$

如果 $E=64, K=2$，一个 Token 理论上只执行 2 个专家，而不是 64 个。但 Runtime 必须先回答：这 2 个专家在哪张 GPU？要发送多少 Token？各专家的批量有多大？最慢专家什么时候完成？如何把结果按原 Token 顺序合并？

```text
Hidden States
      |
   Router / Top-K
      |
 Token Permute + Dispatch
      |
  All-to-All / Local Copy
      |
 Grouped Expert GEMM
      |
  All-to-All / Combine
      |
 Unpermute + Weighted Sum
```

MoE 的性能不是平均专家决定的，而经常由最拥挤专家、最慢 Rank 与最差链路决定。

## 3. 系统与架构原理

### 3.1 Router：决定模型质量，也决定系统负载

Router 通常输出每个 Token 到各专家的 logits，再做 Top-K。推理时要保存专家 ID 与权重，Dispatch 按专家重排 Token。

理想状态是专家专业化且负载可控。现实中，自然语言分布、Prompt 类型、批次大小与模型训练都会让某些专家更热门。训练阶段可使用辅助负载均衡损失、bias-based balancing 或其他策略；推理阶段还需要动态放置、冗余专家、路由约束与请求调度。

不能为了「看起来均匀」随意改 Router：修改专家选择可能改变模型输出。运行时的无损优化更常通过移动/复制专家映射、改变请求到 Rank 的分配来实现，而不是替换模型定义的 Top-K。

### 3.2 Capacity Factor、Padding 与 Token Drop

若一次共有 $T$ 个 Token，每个 Token 选择 $K$ 个专家，理想平均负载为

$$
L_{avg} = \frac{TK}{E}
$$

每个专家容量常近似设置为

$$
C = \left\lceil \gamma \frac{TK}{E} \right\rceil
$$

$\gamma$ 是 capacity factor。容量小会发生 token drop 或 reroute，可能影响质量；容量大则需要 Padding，浪费计算与显存。Dropless MoE 和 block-sparse/grouped kernel 尝试在不丢 Token 的同时高效处理变长专家批次。

### 3.3 Expert Parallel（EP）

EP 将完整专家分散到不同 GPU。假设 8 个专家、4 张 GPU，每张 GPU 可放 2 个专家。每个 Rank 先把非本地 Token Dispatch 给目标 Rank，目标计算后再 Combine 回源 Rank。

优点：每张卡只存部分专家，总参数容量可扩展；本地专家权重完整，避免每个专家内部都做 TP。代价：每个 MoE 层通常出现两次全交换语义的数据移动。

### 3.4 TP、EP 与混合 ETP

| 模式 | 权重放置 | Token 通信 | 适用情况 |
| --- | --- | --- | --- |
| TP | 每个专家都切到多卡 | 所有 Rank 参与专家内计算 | 单专家太大或小规模部署 |
| EP | 不同 Rank 放不同完整专家 | Token 在专家 Rank 间交换 | 专家多、单专家能放入一组卡 |
| ETP | 先按 EP 分专家，再对本地专家做 TP | Dispatch + 专家内部 Collective | 单专家仍很大或需混合扩展 |
| DP/Attention DP + EP | Attention 可复制/数据并行，专家跨 DP Rank 分布 | Attention 与 MoE 使用不同映射 | DeepSeek/Qwen 等大 MoE 服务 |

并行度越多不代表越快。EP 扩大后，每 Rank 的专家批量可能变小，All-to-All 占比上升；ETP 又会增加专家内部通信。选择必须结合 Batch、Top-K、专家宽度与拓扑。

### 3.5 Dispatch 与 Combine

Dispatch 通常包含：

1. 计算每个目标专家的 Token 数。
2. Prefix Sum / Offset。
3. Permute，将同一专家的 Token 放到连续区间。
4. 按目标 Rank 做 All-to-All / All-to-All-V。
5. 目标 Rank 为本地专家建立分组描述符。

Combine 反向传回专家输出，按原 Token ID 反排列，并用 Router 权重求和。这里容易出现很多「小但昂贵」的 kernel：计数、排序、Scatter、Gather、同步与跨流事件。高性能 Runtime 会融合 Router、Top-K、Permutation、量化与通信准备。

### 3.6 Grouped GEMM 与小 Batch

同一 Rank 上不同专家的 Token 数不同。如果对每个专家逐个启动 GEMM，Decode 小 Batch 时容易产生大量小矩阵与 Launch 开销。Grouped GEMM 把多个专家 GEMM 一次提交，Block-sparse kernel 则以块为单位调度不规则稀疏计算。

Prefill 与 Decode 的最优路径不同：

- **Prefill**：Token 多，追求吞吐，可使用连续布局与高吞吐 All-to-All。
- **Decode**：每步 Token 少，追求低延迟，需要更轻量的 Dispatch、固定/掩码布局、CUDA Graph 与低延迟通信。

同一套 MoE kernel 很难同时覆盖两种极端形状，这也是解耦推理与阶段专用 Runtime 的价值。


## 4. 关键公式与性能模型

### 4.1 稀疏计算不等于稀疏显存

MoE 的每 Token FLOPs 主要与激活专家数 $K$ 有关，但权重显存近似与总专家数 $E$ 有关：

$$
FLOPs_{token} \propto K \cdot FLOPs_{expert}
$$

$$
Memory_{weights} \propto E \cdot Params_{expert}
$$

因此，一个「总参数很大、激活参数较小」的模型可能计算接近中等 Dense 模型，却仍要求多卡保存权重。不能根据 Activated Parameters 推断单卡可加载。

### 4.2 负载不均衡

设第 $e$ 个专家收到 $n_e$ 个 Token：

$$
R_{imbalance} = \frac{\max_e n_e}{\frac{1}{E}\sum_e n_e}
$$

$R=1$ 表示完全均匀。若一轮必须等待最慢专家，则粗略的计算效率上界为

$$
\eta_{balance} \approx \frac{1}{R_{imbalance}}
$$

例如最大专家是平均值的 2 倍，即使其他 Rank 很空闲，这一层也可能只获得约一半的理想并行效率。

### 4.3 通信量

隐藏维度为 $H$、元素字节数为 $b$。若远程路由比例为 $f_{remote}$，一次 Dispatch payload 近似

$$
B_{dispatch} \approx TKHb \cdot f_{remote}
$$

Combine 还要传回同量级输出：

$$
B_{layer} \approx 2TKHb \cdot f_{remote}
$$

忽略元数据与协议开销时：

$$
T_{comm} \approx T_{dispatch} + T_{combine} \approx 2T_{setup} + \frac{B_{layer}}{BW_{effective}}
$$

小 Decode 消息更受 setup/同步影响；大 Prefill 更受带宽与拓扑影响。

### 4.4 MoE 层延迟

串行近似：

$$
T_{MoE} = T_{route} + T_{permute} + T_{dispatch} + T_{expert} + T_{combine} + T_{unpermute}
$$

若实现通信计算重叠：

$$
T_{MoE} \approx T_{route} + T_{tail} + \max(T_{comm},\, T_{expert})
$$

这里的 `tail` 包括无法隐藏的启动、最后一个 chunk、负载不均衡与同步。仅看到 timeline 有重叠，不代表通信已完全隐藏。

### 4.5 Goodput 与成本

生产系统应比较

$$
Goodput = \frac{\text{满足 TTFT、TPOT、正确性 SLO 的请求}}{\text{时间}}
$$

并同时报告每请求成本、每输出 Token 能耗、显存冗余与网络占用。MoE 可能降低激活计算，却因专家副本、空闲 Rank 与通信增加集群成本。

## 5. DeepSeek 案例中的系统协同

DeepSeek-V3 是总参数 671B、每 Token 激活 37B 参数的 MoE 模型。关键点不是单一技巧，而是组合：细粒度专家、共享专家、无辅助损失负载均衡、FP8、通信计算重叠、DeepEP、MTP 与 MLA。

需要避免两个常见误解：

- 「只激活 37B」不代表只需保存 37B 权重，完整专家仍需分布在系统中。
- 官方特定 H800 集群的训练/推理结果不能直接套到 RTX 3080、4090 或任意以太网集群。

DeepEP 针对 EP 的 Dispatch/Combine 提供高吞吐与低延迟 All-to-All kernel，并支持低精度路径。当前实现及硬件/软件要求仍在快速变化，应以对应版本官方仓库为准；双 RTX 3080 不属于它的标准生产验证平台。

## 6. 瓶颈分析方法

### 6.1 先分清模型瓶颈还是 Runtime 瓶颈

记录 Router 原始分布。如果少数专家天然过热，问题来自模型/数据分布或专家放置；如果路由均匀但耗时不均，检查 GPU 频率、拓扑、后台任务、专家大小与通信。

### 6.2 逐层记录专家负载

至少采集：每层每专家 Token 数；max/mean、CV、空专家比例；dropped/rerouted Token；每 Rank 接收/发送字节；最慢 Rank 与最慢专家；专家副本命中率与迁移次数。

全模型平均负载可能掩盖某一层的热点。

### 6.3 拆解 MoE 时间线

![MoE 推理：算力问题变成数据搬运与排队问题](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l28_01.png)

用 NVTX/Nsight Systems 看通信与计算是否重叠；用 Nsight Compute 检查 Grouped GEMM 的 Tensor Core、带宽、Occupancy 与小矩阵效率；用 NCCL/通信库计数器看链路与拓扑。

### 6.4 区分 Prefill 与 Decode

分别测 Prompt 长度、Batch、并发与输出长度。只测 Prefill 大 Batch 得出的高带宽方案，可能在 Decode 小消息下延迟很差。

### 6.5 做正确性验证

- Router Top-K 与权重保持一致。
- Permute/Unpermute 恢复原 Token 顺序。
- Dispatch/Combine 前后 shape、dtype、Token ID 一致。
- Dropless/Drop/Reroute 策略符合模型定义。
- 专家重新映射或副本不会改变专家语义。
- 低精度通信与专家计算满足误差预算。

## 7. Level 0：CPU Router 负载模拟

保存为 `moe_routing_sim.py`：

```python
#!/usr/bin/env python3
import argparse
import math
import random
import statistics

def route(tokens, experts, topk, skew, capacity_factor, penalty, seed):
    rng = random.Random(seed)
    loads = [0] * experts
    expected = tokens * topk / experts
    capacity = math.ceil(capacity_factor * expected)
    dropped = 0

    for _ in range(tokens):
        # 低编号专家更热门，用于模拟真实工作负载倾斜。
        raw = [rng.gauss(0, 1) - skew * e / max(1, experts - 1)
               for e in range(experts)]
        if penalty == 0.0:
            # 模型原始 Top-K：容量满时丢弃，不偷偷改选其他专家。
            selected = sorted(range(experts), key=lambda e: raw[e], reverse=True)[:topk]
            for e in selected:
                if loads[e] < capacity:
                    loads[e] += 1
                else:
                    dropped += 1
            continue

        selected = set()
        for _ in range(topk):
            candidates = []
            for e in range(experts):
                if e in selected or loads[e] >= capacity:
                    continue
                balanced_score = raw[e] - penalty * loads[e] / max(1.0, expected)
                candidates.append((balanced_score, e))
            if not candidates:
                dropped += 1
                continue
            _, e = max(candidates)
            selected.add(e)
            loads[e] += 1
    return loads, dropped, capacity

def summarize(name, loads, dropped, capacity):
    mean = statistics.mean(loads)
    cv = statistics.pstdev(loads) / mean if mean else 0.0
    ratio = max(loads) / mean if mean else 0.0
    efficiency = mean / max(loads) if max(loads) else 0.0
    print(f"\n[{name}]")
    print("loads=", loads)
    print(f"capacity={capacity} dropped_copies={dropped}")
    print(f"max/mean={ratio:.3f} CV={cv:.3f}")
    print(f"balance_efficiency_upper_bound={efficiency:.3f}")

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tokens", type=int, default=4096)
    p.add_argument("--experts", type=int, default=16)
    p.add_argument("--topk", type=int, default=2)
    p.add_argument("--skew", type=float, default=1.5)
    p.add_argument("--capacity-factor", type=float, default=1.25)
    p.add_argument("--balance-penalty", type=float, default=1.5)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    if a.topk > a.experts:
        p.error("topk 不能大于 experts")

    base = route(a.tokens, a.experts, a.topk, a.skew,
                 a.capacity_factor, penalty=0.0, seed=a.seed)
    balanced = route(a.tokens, a.experts, a.topk, a.skew,
                     a.capacity_factor, penalty=a.balance_penalty, seed=a.seed)
    summarize("model_topk_with_capacity", *base)
    summarize("capacity_aware_simulation", *balanced)
    print("\n注意：第二组修改了路由分数，只用于系统容量学习，")
    print("不能直接替换真实模型 Router，否则可能改变输出质量。")

if __name__ == "__main__":
    main()
```

运行：

```bash
python moe_routing_sim.py
python moe_routing_sim.py --skew 0 --capacity-factor 1.1
python moe_routing_sim.py --skew 2.5 --capacity-factor 2.0
```

预期现象：倾斜增大时，原始 Top-K 更容易让热门专家达到容量并产生 dropped copies；模拟的负载惩罚会降低 max/mean，但它改变了专家选择，只能帮助理解「均衡与模型语义」的权衡，不是可直接部署的无损优化。

三组参数的实测结果（tokens=4096、experts=16、topk=2）：

| 参数 | 组别 | capacity | dropped copies | max/mean | CV | 效率上界 |
| --- | --- | --- | --- | --- | --- | --- |
| 默认（skew=1.5, γ=1.25） | 原始 Top-K | 640 | 1681 | 1.573 | 0.520 | 0.636 |
| 默认 | 负载惩罚模拟 | 640 | 0 | 1.250 | 0.232 | 0.800 |
| `--skew 0 --capacity-factor 1.1` | 原始 Top-K | 564 | 16 | 1.104 | 0.049 | 0.906 |
| `--skew 0 --capacity-factor 1.1` | 负载惩罚模拟 | 564 | 0 | 1.035 | 0.019 | 0.966 |
| `--skew 2.5 --capacity-factor 2.0` | 原始 Top-K | 1024 | 1235 | 2.355 | 0.901 | 0.425 |
| `--skew 2.5 --capacity-factor 2.0` | 负载惩罚模拟 | 1024 | 0 | 1.771 | 0.460 | 0.564 |

三点值得注意：

- **dropped 由倾斜与容量共同决定**。skew 从 1.5 升到 2.5 时倾斜更严重，但 γ 同时从 1.25 提到 2.0，dropped 反而从 1681 降到 1235——扩容确实吃下了更多 Token，代价是 max/mean 从 1.573 恶化到 2.355，效率上界只剩 0.425。这正是「容量换 Padding 与不均衡」的权衡。
- **无倾斜时两组几乎一致**。`--skew 0` 下原始 Top-K 的 CV 已只有 0.049，负载均衡机制没有多少可改进空间，却仍要承担改变专家选择的质量风险。
- **负载惩罚不是万能**。高倾斜下它把 max/mean 从 2.355 压到 1.771，仍远未均匀，因为容量约束与 Top-K 语义限制了可调整范围；生产环境应改用专家重映射与冗余副本，而不是改 Router 分数。

## 8. Level 1：通用 PyTorch 分组专家微基准

这个实验比较「逐 Token 启动专家计算」与「先按专家分组再做批量 GEMM」。它是 Runtime 机制实验，不是完整 MoE 模型。保存为 `grouped_expert_benchmark.py`：

```python
#!/usr/bin/env python3
import argparse
import time
import torch

def arch_name(major, minor):
    if major == 8 and minor in (0, 6, 7):
        return "Ampere"
    if major == 8 and minor == 9:
        return "Ada Lovelace"
    if major == 9:
        return "Hopper"
    if major >= 10:
        return "Blackwell"
    return "Other/Older"

def sync(device):
    if device.type == "cuda":
        torch.cuda.synchronize(device)

def bench(fn, device, warmup, iters):
    for _ in range(warmup):
        fn()
    sync(device)
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    sync(device)
    return (time.perf_counter() - t0) * 1000 / iters

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tokens", type=int, default=512)
    p.add_argument("--hidden", type=int, default=128)
    p.add_argument("--experts", type=int, default=8)
    p.add_argument("--iters", type=int, default=10)
    p.add_argument("--warmup", type=int, default=3)
    p.add_argument("--seed", type=int, default=7)
    a = p.parse_args()
    torch.manual_seed(a.seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dtype = torch.float16 if device.type == "cuda" else torch.float32
    print("torch=", torch.__version__, "cuda_runtime=", torch.version.cuda)
    print("device=", device, "dtype=", dtype)
    if device.type == "cuda":
        prop = torch.cuda.get_device_properties(0)
        print("gpu=", prop.name, "cc=", f"{prop.major}.{prop.minor}",
              "arch=", arch_name(prop.major, prop.minor),
              "vram_GiB=", round(prop.total_memory / 2**30, 2))

    x = torch.randn(a.tokens, a.hidden, device=device, dtype=dtype)
    weights = torch.randn(a.experts, a.hidden, a.hidden,
                          device=device, dtype=dtype) / a.hidden**0.5
    expert_ids = torch.randint(0, a.experts, (a.tokens,), device=device)

    @torch.inference_mode()
    def token_loop():
        out = torch.empty_like(x)
        for t in range(a.tokens):
            out[t] = x[t] @ weights[expert_ids[t]]
        return out

    @torch.inference_mode()
    def grouped():
        out = torch.empty_like(x)
        for e in range(a.experts):
            idx = torch.where(expert_ids == e)[0]
            if idx.numel():
                out[idx] = x[idx] @ weights[e]
        return out

    ref = token_loop()
    opt = grouped()
    max_err = (ref - opt).abs().max().item()
    loop_ms = bench(token_loop, device, a.warmup, a.iters)
    grouped_ms = bench(grouped, device, a.warmup, a.iters)
    counts = torch.bincount(expert_ids, minlength=a.experts).cpu().tolist()
    print("tokens_per_expert=", counts)
    print(f"max_abs_error={max_err:.6g}")
    print(f"token_loop={loop_ms:.3f} ms")
    print(f"grouped={grouped_ms:.3f} ms")
    print(f"speedup={loop_ms/grouped_ms:.3f}x")
    print("结果仅代表本机形状；真实框架会使用融合 Grouped GEMM kernel。")

if __name__ == "__main__":
    main()
```

运行：

```bash
python grouped_expert_benchmark.py
python grouped_expert_benchmark.py --tokens 4096 --hidden 1024 --experts 16
```

CPU 或显存不足时保持默认值，GPU 上逐步增大参数。预期分组执行减少 Python/Kernel Launch，并把许多 GEMV/小 GEMM 合成较大的 GEMM。`max_abs_error` 应接近 0（FP16 下约 $10^{-3}$ 量级），若明显偏大说明分组索引或权重映射有误。真实 Runtime 还应融合 Top-K、Permutation、Grouped GEMM 与 Combine，不能把这个微基准速度当作端到端 MoE 收益。

一台纯 CPU 环境（torch 1.13.1+cpu、float32）的默认参数实测：`tokens_per_expert=[53,60,70,65,71,73,68,52]`，`max_abs_error=1.43e-06`，`token_loop=4.657 ms`，`grouped=2.021 ms`，`speedup=2.304x`。CPU 上收益主要来自减少 Python 循环与算子调度次数；换到 GPU 后小矩阵的 Launch 开销占比更高，分组带来的加速比通常更明显，但必须重测而不是外推。

## 9. Level 2：Expert Parallel 专项

### 9.1 vLLM 标准后端功能路径

先核对安装版本：

```bash
vllm --version
vllm serve --help | grep -E 'expert-parallel|all2all|eplb'
```

当前 vLLM 使用 `--enable-expert-parallel` 与 `--all2all-backend`。以下只展示配置形态，模型是否支持、显存是否足够与 DP/EP 语义应以当前版本文档为准：

```bash
CUDA_VISIBLE_DEVICES=0,1 vllm serve /path/to/supported-moe-model \
  --tensor-parallel-size 1 \
  --data-parallel-size 2 \
  --enable-expert-parallel \
  --all2all-backend allgather_reducescatter
```

双 RTX 3080 20GB 可先选择总权重能在两卡 EP 布局中容纳的小型 MoE checkpoint。注意：Attention/共享参数可能在 DP Rank 复制，不能简单用「模型总字节 ÷ 2」判断显存。

### 9.2 DeepEP 高吞吐与低延迟路径

大规模数据中心部署可按 Prefill/Decode 分别选择高吞吐与低延迟后端：

```bash
# Prefill 倾向
--all2all-backend deepep_high_throughput

# Decode 倾向
--all2all-backend deepep_low_latency
```

DeepEP、NCCL、CUDA、GPU 架构与网络支持会变化，安装前必须阅读对应版本矩阵。H100/H200 属于 Hopper，B100/B200/GB200 属于 Blackwell；双 RTX 3080 的回退是标准 `allgather_reducescatter`/框架可用后端与 Level 1 微基准，不能宣称等价验证 DeepEP。

### 9.3 EPLB 与冗余专家

运行时可根据窗口内负载重新映射专家，或为热门专家创建冗余副本。当前 vLLM 提供 EPLB 配置，但副本会占用显存：

```bash
vllm serve /path/to/supported-moe-model \
  --enable-expert-parallel \
  --enable-eplb \
  --eplb-config '{
    "window_size":1000,
    "step_interval":3000,
    "num_redundant_experts":2,
    "log_balancedness":true,
    "use_async":true
  }'
```

先在离线 Trace 上确定热点稳定性与副本显存成本。过于频繁地搬专家权重，可能让重平衡开销超过收益。判断依据是热点是否在 `window_size` 尺度上稳定：若每几百步热点就换一批专家，重映射带来的搬运与缓存失效会吃掉全部收益。

### 9.4 实验边界与可替代验证

| 平台 | 可验证内容 | 不可宣称的内容 |
| --- | --- | --- |
| 双 RTX 3080 20GB | EP 布局、小型 MoE checkpoint 功能、All-to-All 相对开销、EPLB 配置形态 | DeepEP 生产性能、大规模专家放置收益 |
| RTX 4090 / 5090 | 单卡大 Batch Grouped GEMM、FP16/FP8 路径、CUDA Graph 化 Decode | 跨节点 All-to-All 带宽结论 |
| H100 / H200 | NVLink 域内高吞吐 Dispatch/Combine、FP8、通信计算重叠 | 与官方 H800 集群数字逐项等同 |
| B200 / GB200 | 新架构 kernel 与新互联形态的可行性 | 未发布的软件栈能力 |

缺少多卡时，Level 0 与 Level 1 仍能给出负载倾斜与分组执行的定量直觉，只是不能替代真实 All-to-All 测量。

## 10. 未来 AI Runtime 的演进方向

前面各篇的手段大多仍是「静态配置 + 一次性编译」：并行度在启动时确定，kernel 在预热时选定，KV 容量按峰值预留，批处理策略按经验值固定。真实服务的负载是持续变化的，因此 Runtime 必须从「执行模型」升级为「持续控制系统」——不断观测、决策、执行、再观测。

### 10.1 七个方向

| 方向 | 现状痛点 | 演进形态 | 依赖的前置能力 |
| --- | --- | --- | --- |
| 动态并行 | TP/EP/PP 启动即固定，长短请求混部时无法切换 | 按阶段与负载在线调整并行映射，Attention 与 MoE 用不同布局 | 权重重分片、KV 重排、拓扑感知 |
| 计算通信融合 | Dispatch/Combine 与 GEMM 串行，timeline 有重叠但尾部未隐藏 | chunk 级流水、通信 kernel 与计算 kernel 协同调度 | 细粒度依赖描述、多流与事件管理 |
| 分层 KV | KV 只驻留 HBM，长上下文与多轮对话被迫重算 | HBM → Host → NVMe/远端 KV Store 的多级缓存与预取 | Token 级 Cache Key、驱逐成本模型、传输引擎 |
| 推测执行 | Draft 模型与接受率固定，负载变化时收益反转 | 按接受率与队列压力动态调 $K$、切换 Draft 策略 | 在线接受率统计、KV 回滚、SLO 反馈 |
| 解耦推理 | P/D 比例按平均长度一次性设定 | conditional disaggregation + 独立弹性扩缩容 | KV Data Plane、背压、幂等重试 |
| 拓扑感知 | 调度只看队列长度，不看 NIC-GPU 亲和与链路拥塞 | 路由与专家放置同时考虑 NVLink 域、PCIe Switch、NUMA | 拓扑发现、有效带宽在线测量 |
| SLO 驱动自治 | 以 tokens/s 与利用率为目标，尾延迟失控 | 以 Goodput 为唯一目标函数的闭环控制器 | 分段打点、P99 统计、准入与降级策略 |

### 10.2 闭环控制的四个环节

![MoE Runtime 自适应闭环：Observe → Decide → Act → Verify](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l28_02.png)

四个环节缺一不可。只 Observe 不 Act 是仪表盘；只 Act 不 Verify 是把系统推向不可解释的状态。每次决策都要有明确的回滚条件与生效范围，且不能改变模型语义——这也是 MoE 里「不能随意改 Router」的同一条原则在 Runtime 层的推广。

### 10.3 判断一个优化是否值得进入生产

三条筛选标准，与前面各篇一致：

1. **收益口径是 Goodput，不是单项指标**：吞吐上升但 P99 ITL 恶化，等于没有收益。
2. **代价要算全**：显存冗余、通信占用、重平衡搬运、控制面复杂度、故障面都要计入。
3. **可验证、可回滚**：有分段打点能证明收益来自哪一段，有开关能退回原路径。

MoE 把这三条标准放大到了极致：算法上的稀疏收益，必须穿过路由、通信、排队与调度层层损耗，才能落到用户可感知的延迟上。

## 11. 量化补充：大 EP 的三层 skew

第 4.2 节的负载不均衡可以算出具体倍数。整层按最忙卡计时：卡 $r$ 完成时间至少 $\max(F_r/C_r,W_r/B_r)$，合并要等最长的一条而非平均。同样 512 次分派放八张 H100（有效算力取峰值 50% 即 494.7 TFLOP/s），均分每卡约 2.42 GFLOPs、4.9 μs；八个热点专家集中一卡则该卡 19.3 GFLOPs、39.1 μs，八倍。集中路由把权重读取从 4.5 GiB 减到 288 MiB（41 篇第 6 节的复用账），却可能把最忙卡计算增至八倍——**均衡策略要先定瓶颈在读取还是计算，再决定追求复用还是分散**。

**EP 越大，专家间不均越原样变成卡间不均**。256 专家、1024 token 各选 8（共 8192 次分派、平均每专家 32 行），一个热点专家收 128 行（4 倍）：EP8 每卡 32 专家，热点被同卡其他专家冲淡，热点卡约 1108 行只比平均多 8%；EP32 每卡 8 专家，多 36%；EP256 每卡只剩这一个专家，128 行是平均 32 行的 4 倍。没有热点也一样：均匀随机路由下固定种子模拟 1000 批，EP8 最忙卡平均只多 4%，EP256 多 52%——每卡可相互抵消的专家越少、要等的卡越多。DeepSeek 公开 decode 部署用 EP144（每卡 2 个路由专家）加 32 个冗余专家按负载调副本，正是曲线右端的应对手段。从 EP8 到 EP256 每卡平均行数缩到 1/32，最忙卡却只从 1108 降到 128（约 1/8.7），平均卡四分之三时间在等。

skew 要分三层观察：逻辑专家选择频率定每专家有效行数；放置与副本把行数变成每卡负载；token 来源、目标与网络路径再把每卡负载变成每方向流量。通信下界按发送方、接收方、物理割集三者取最大：

$$
T_X\ge\max\left(\max_i\frac{\sum_jV^X_{ij}}{B^{\mathrm{send}}_i},\max_j\frac{\sum_iV^X_{ij}}{B^{\mathrm{recv}}_j},\max_{\mathcal C}\frac{V^X_{\mathcal C}}{B_{\mathcal C}}\right),
$$

同方向并发流量要相加，不能各除一份完整带宽假定同时完成。算例：1024 token、每份 8 KiB，四来源卡跨服务器发四专家组（每卡 50 GB/s 网卡），dispatch 与 combine 各 64 MiB：均衡时阶段屏障总下界 0.827 ms，热点分布 [5120,1024,1024,1024] 时三段都变 2.5 倍、总下界 2.068 ms——总通信量与总计算量都没变。跨服务器时两次交换占八成（H100 算一份专家约 76 ns，网卡传一份 8 KiB 要约 164 ns）；只把 dispatch 改 FP8 降到 1.649 ms（combine 与计算不变）；两池只剩一条 400 Gbit/s 链路则均衡也要 2.841 ms——加专家卡替代不了跨池带宽；两池同进一台 HGX（NVLink 450 GB/s）两次交换压到 0.093 ms，热点卡 0.391 ms 计算成了最长段，这时减热点计算比再加带宽有效——专家副本与动态放置针对的正是这种情形，展开见主题三 40 篇。

## 写在最后

MoE 说明了一件事：模型结构的稀疏性只是「潜在算力」，把它兑现成速度的是 Runtime。至此正式内容告一段落，接下来进入八个综合项目，把前面所有诊断方法、公式与实验串成可交付的工程产出。

下一篇：[GPU 性能分析实验](/source/AI-Infra/2-AI系统性能工程/29-GPU性能分析实验)。
