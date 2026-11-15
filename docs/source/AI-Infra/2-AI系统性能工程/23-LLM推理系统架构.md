# LLM 推理系统架构

本篇拆解现代 LLM 推理系统的端到端架构，理解 Prefill、Decode、Batching、缓存与调度如何协同工作。

大模型推理不是调用一次 `model.generate()` 那么简单。在线服务需要同时处理长短不同、到达时间不同、优先级不同的请求；还要在有限显存中保存模型权重与每个会话的 KV Cache，并在每个解码迭代重新决定哪些请求一起执行。因此核心问题不是「单次矩阵乘法有多快」，而是「在途请求集合如何在时间与空间两个维度上被有效管理」。

## 1. 内容概览

- 一次 LLM 在线请求从接入到流式返回的完整链路。
- Gateway、Tokenizer、Admission Controller、Scheduler、KV Manager、Model Executor、Detokenizer 的职责。
- Prefill 与 Decode 的计算形态、性能指标与瓶颈差异。
- 权重、KV Cache、Workspace、CUDA Graph Pool 与碎片的显存模型。
- TTFT、TPOT、ITL、Tokens/s、Goodput 与排队模型。
- 离线推理、在线推理、单体服务、分布式服务与解耦式服务的取舍。
- 单卡、双卡与多节点环境下的数据并行、张量并行与请求路由策略。

## 2. 核心直觉：推理系统是一台「有状态的 Token 工厂」

普通图像分类请求通常输入固定 Shape，执行一次前向计算后结束。LLM 请求不同：Prompt 先经过一次 Prefill，生成第一个 Token 所需状态；系统保存所有层的 Key/Value；每生成一个新 Token 都要再次调度并执行一次 Decode；请求长度与结束时间事先并不完全确定；多个请求会在不同迭代加入或离开运行集合。

所以 LLM 服务不是「请求级 Batch」一次算完，而更像一个操作系统：

- 请求是进程。
- 每个 Decode Step 是一个时间片。
- KV Cache 是进程常驻内存。
- Scheduler 决定本轮运行谁。
- Token Budget 类似 CPU 时间与内存配额。
- Prefix Cache 类似可共享的只读页。
- 超时、取消与抢占决定无效工作能否及时停止。

优化对象由单个请求变成了整个在途请求集合。

## 3. 端到端推理架构

### 3.1 一次请求的完整路径

```text
客户端
  │ HTTP/gRPC，流式或非流式
  ▼
Gateway / API Server
  │ 鉴权、配额、路由、限流、参数校验
  ▼
Tokenizer / Input Processor
  │ 文本→Token IDs，Chat Template，多模态预处理
  ▼
Admission Controller + Request Queue
  │ 并发、Token、显存、Deadline 预算
  ▼
Scheduler / Batcher ───────────────┐
  │ 选择 Prefill/Decode 请求        │ 取消、优先级、抢占
  ▼                                │
KV Cache Manager ◄─────────────────┘
  │ 分配、映射、共享、驱逐 KV Block
  ▼
Model Executor
  │ 权重、Attention、MLP、Collective、采样 Kernel
  ▼
Sampler → Detokenizer → Stream Writer
  │ Token IDs→文本增量，停止条件，输出过滤
  ▼
客户端

旁路：Metrics / Trace / Logs / Billing / Health Check
```

该链路中，API Server 负责协议，Scheduler 负责时间，KV Manager 负责空间，Model Executor 负责计算。把所有职责都塞进一个同步 Python 循环，会让网络、日志、内存分配与 GPU 执行互相阻塞。

### 3.2 控制面与数据面

控制面负责低频决策：模型版本、量化格式与副本数量；路由、扩缩容、灰度与回滚；TP/PP/EP 拓扑与设备放置；SLO、租户配额与优先级规则。

数据面负责每请求、每迭代的高频工作：Tokenize、入队、组批；KV Block 分配与回收；Prefill/Decode 执行；Sampling、Detokenize 与流式发送。

高频数据面不应等待控制面 RPC，也不应在热路径加载模型、编译 Kernel 或初始化通信组。

### 3.3 Model Executor 内部

| 模块 | 职责 | 主要性能风险 |
| --- | --- | --- |
| Weight Loader | 加载、分片、量化权重 | 冷启动、峰值内存、格式转换 |
| Execution Plan | 选择图、Kernel 和 Shape Bucket | 重编译、图缓存膨胀 |
| Attention Backend | Prefill/Decode Attention | 长上下文、KV 读带宽 |
| KV Cache Manager | 分配和映射 KV Block | 碎片、驱逐、泄漏 |
| Distributed Executor | TP/PP/EP Collective | PCIe/NVLink/网络同步 |
| Sampler | Top-k、Top-p、温度、约束解码 | 小 Kernel、CPU 往返 |
| Output Processor | 停止条件、Detokenize、流式输出 | Python/GIL、网络背压 |

高性能框架的名称与实现会变化，但这些职责不会消失。

## 4. Prefill 与 Decode：同一个模型，两种工作负载

### 4.1 Prefill 阶段

Prefill 一次处理 Prompt 中的多个 Token，计算所有层的表示并建立 KV Cache。长 Prompt 可形成较大的矩阵乘法，通常有较高并行度；在常见密集 Transformer 上，较长 Prefill 往往更接近计算受限。

关键指标包括排队时间、Prompt Tokens/s、Prefill 时间、TTFT、每请求占用的 KV 容量。

「Prefill 一定计算受限」不是定律。小 Batch、短 Prompt、低效 Kernel、CPU Tokenize 或频繁 Launch 都可能改变瓶颈。

### 4.2 Decode 阶段

Decode 每次通常只为每个活动序列生成一个 Token。每层都要读取权重与历史 KV，单步矩阵更「瘦」，算术强度通常低于 Prefill，因此常见瓶颈是：权重与 KV Cache 的 HBM 带宽；小 Kernel 与 Launch 开销；Scheduler 的每步开销；TP All-Reduce；长上下文 Attention 的 KV 读取；流式输出与同步。

关键指标包括 TPOT、ITL、Generation Tokens/s 与每 Token 能耗。

### 4.3 为什么二者会互相干扰

长 Prefill 能占用大量计算时间；Decode 则需要频繁、低延迟地获得 GPU 时间片。如果把两者不加约束地放在同一队列，大 Prompt 可能让正在流式输出的请求出现 ITL 尖峰。

常见控制手段：限制每轮 Prefill Token Budget；Chunked Prefill 把长 Prompt 分段；Prefill/Decode 分别设优先级；在资源足够时将两个阶段放到不同 Worker；以 Deadline 或最大 ITL 约束调度。

## 5. 推理延迟模型

### 5.1 TTFT

$$
T_{TTFT} = T_{gateway} + T_{tokenize} + T_{queue} + T_{schedule} + T_{prefill} + T_{sample} + T_{stream}
$$

只优化 $T_{prefill}$ 不一定改善 TTFT。过载时 $T_{queue}$ 往往远大于 GPU 执行时间。

### 5.2 TPOT、ITL 与端到端延迟

若生成 $N_{out}$ 个 Token：

$$
T_{E2E} \approx T_{TTFT} + \sum_{i=2}^{N_{out}} ITL_i \approx T_{TTFT} + (N_{out}-1)\cdot TPOT
$$

平均 TPOT 会掩盖停顿，因此在线聊天应同时报告 ITL 的 P50/P95/P99。

### 5.3 吞吐与 Goodput

$$
Throughput_{token} = \frac{N_{prompt} + N_{generated}}{T}
$$

Prompt Token 与 Generation Token 的成本不同，不宜只给一个总 Tokens/s。建议分开记录 Prompt Tokens/s、Generation Tokens/s、Requests/s，以及满足 TTFT 与 TPOT SLO 的 Requests/s（即 Goodput）。设请求 $i$ 是否满足正确性与 SLO 为 $I_i$：

$$
Goodput = \frac{\sum_i I_i}{T}
$$

把超时、取消后仍生成的 Token 计入吞吐，会虚高系统表现。

## 6. 显存模型与 KV Cache

### 6.1 总显存预算

$$
M_{total} = M_{weights} + M_{KV} + M_{activation} + M_{workspace} + M_{graph} + M_{comm} + M_{fragment} + M_{reserve}
$$

权重通常较稳定；KV Cache 随在途 Token 数增长，是在线并发的主要动态容量；Workspace、CUDA Graph Pool、NCCL Buffer 与碎片决定「纸面可用显存」为何不能全部分给 KV。

### 6.2 权重容量

只考虑原始权重时：

$$
M_{weights} \approx N_{param} \cdot \frac{b_w}{8}
$$

7B 模型的 FP16 原始权重约 14 GB（十进制），4-bit 原始权重约 3.5 GB。实际加载量还包含 Scale、Zero Point、未量化层、Tensor 元数据与 Runtime Buffer，不能只按位宽做最终部署承诺。

### 6.3 KV Cache 每 Token 容量

对常见 Decoder-only Transformer，单个 Token 的 KV 近似为

$$
M_{KV/token} = 2 \cdot L \cdot H_{kv} \cdot D_{head} \cdot \frac{b_{kv}}{8}
$$

其中 2 表示 Key 与 Value，$L$ 是层数，$H_{kv}$ 是 KV Head 数，$D_{head}$ 是每个 Head 的维度，$b_{kv}$ 是 KV 元素位数。全部在途请求的 KV 近似为

$$
M_{KV} = M_{KV/token} \cdot \sum_i S_i
$$

$S_i$ 是请求当前已缓存 Token 数。GQA/MQA 通过减少 $H_{kv}$ 降低容量与带宽；它们不是运行时开关，而是模型结构的一部分。

### 6.4 连续内存与 Paged KV

为每个请求按最大长度预留连续 KV，简单但会产生内部碎片。Paged KV 将缓存拆成固定大小 Block，按请求实际增长分配，便于回收、共享 Prefix 与实现抢占。

Paged KV 并不意味着零开销：Block Table 需要管理；Block 大会增加内部碎片；Block 小会增加元数据与寻址开销；Prefix 只有完全匹配且语义安全时才能复用；驱逐后可能需要重算或从主存/存储重新载入。

## 7. Scheduler：同时管理时间和空间

每轮 Scheduler 至少要回答四个问题：哪些新请求可以进入；本轮 Prefill 多少 Token；哪些 Decode 请求继续运行；KV 不足时拒绝、等待、抢占还是驱逐谁。

### 7.1 双重预算

只限制 Batch Size 不够，因为 32 个短请求与 32 个长请求的成本差异巨大。实用 Scheduler 通常同时限制最大活动序列数、每迭代最大 Token 数、可用 KV Block、最大 Prompt/Context 长度，以及 Deadline、优先级与租户份额。

### 7.2 排队稳定性

到达率 $\lambda$、有效服务率 $\mu$：

$$
\rho = \frac{\lambda}{\mu}
$$

当 $\rho$ 长时间接近 1，尾延迟会迅速上升；当 $\rho > 1$，队列必然增长。扩 Batch 可能提高 $\mu$，但如果同时让 TPOT 超过 SLO，Goodput 仍会下降。

### 7.3 背压与取消

无界队列不是容量。过载策略应明确：拒绝并返回可重试状态；降低最大输出长度或切换小模型；路由到空闲副本；对批处理请求延后执行；用户断连后立即传播取消并释放 KV Block。

取消只停在 HTTP 层会产生「幽灵请求」：客户端已离开，GPU 仍在生成。

## 8. 并行与部署形态

### 8.1 单 GPU

最简单、延迟最可控。若模型与目标 KV 容量能放入单卡，应先建立单卡基线。单卡没有 TP Collective，也更容易判断 Kernel、KV 与 Scheduler 的真实瓶颈。

### 8.2 数据并行副本

每张 GPU 保存完整模型，Router 按请求分发。优点是没有请求内跨卡通信、故障隔离简单、吞吐易水平扩展；缺点是每卡重复保存权重、单请求显存上限不变、Prefix/KV 在副本间迁移困难。

双 RTX 3080 20GB 环境中，若模型能放入单卡，两个独立副本通常比跨 PCIe 的 TP 更适合作为吞吐基线。

### 8.3 张量并行

把单层权重切分到多卡，每层需要 All-Reduce/All-Gather。它降低单卡权重与 KV 压力、缩短单请求计算时间，但引入请求内同步：

$$
T_{step}^{TP} \approx \frac{T_{compute}}{N_{tp}} + T_{collective}(N_{tp},\ payload,\ link)
$$

NVLink/NVSwitch 上 TP 通常划算；PCIe 上小 Batch Decode 的 Collective 可能吃掉大部分收益。TP 度数越高，每卡 GEMM 越瘦，Kernel 效率与 Launch 占比也会变化。

### 8.4 流水并行与专家并行

PP 把层切到不同设备，适合权重放不下且可接受跨 Stage 气泡的场景；在线 Decode 的 PP 需要足够多的在途请求才能填满流水，否则单请求延迟反而变差。EP 把 MoE 专家分布到多卡，每步引入 All-to-All，收益依赖专家负载均衡与互联带宽。

### 8.5 解耦式服务

把 Prefill 与 Decode 放到不同 Worker/设备池，各自按自身瓶颈配置 Batch、并行度与硬件，中间传输 KV。它消除相互干扰、便于独立扩缩容，代价是 KV 传输带宽与延迟、更复杂的路由与状态一致性。是否值得，取决于 KV 传输时间能否被两阶段各自的效率提升覆盖。

### 8.6 离线与在线

| 维度 | 离线批处理 | 在线服务 |
| --- | --- | --- |
| 首要目标 | 总完成时间、成本 | TTFT/ITL SLO 下的 Goodput |
| 到达模式 | 一次性已知集合 | 持续随机到达 |
| Batch 策略 | 长度分桶 + 大 Static Batch | Continuous Batching + Token Budget |
| 可接受手段 | 长排队、重试、抢占重算 | 快速失败、取消传播、限流 |
| 显存倾向 | 尽量填满 KV | 留水位应对突发与长输出 |

## 9. 瓶颈分析方法

诊断顺序应从请求侧向设备侧推进：

1. **SLO 分解**：TTFT 超标先看 Queue 与 Prefill；ITL 超标先看 Decode 步长、抢占与通信。
2. **队列证据**：Arrival Rate、Queue Depth、Inflight、拒绝率、取消率、Batch Size 分布。
3. **容量证据**：KV 使用率、Block 碎片、驱逐/重算次数、Workspace 与 Graph Pool 占用。
4. **设备证据**：Nsight Systems 看 Decode 步内 Kernel 空洞、Memcpy、NCCL；Nsight Compute 看 Attention 与 GEMM 的带宽/算力利用。
5. **单变量回归**：每次只改一个旋钮（`max_num_seqs`、Token Budget、Chunk Size、KV 水位、TP 度数），用相同长度分布与开环负载复测。

一个常见误判：GPU 利用率很高但 Goodput 很低。此时应先查 Padding、取消后仍生成的 Token、超时请求与低优先级任务，而不是继续优化 Kernel。

## 10. Level 0：容量规划实验

无需 GPU，用显存模型估算可支撑的并发与上下文长度。保存为 `llm_capacity_planner.py`：

```python
#!/usr/bin/env python3
import argparse

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--params-b", type=float, default=7.0, help="参数量，单位十亿")
    p.add_argument("--weight-bits", type=float, default=16.0)
    p.add_argument("--layers", type=int, default=32)
    p.add_argument("--kv-heads", type=int, default=32)
    p.add_argument("--head-dim", type=int, default=128)
    p.add_argument("--kv-bits", type=float, default=16.0)
    p.add_argument("--vram-gib", type=float, default=24.0)
    p.add_argument("--overhead-gib", type=float, default=3.0,
                   help="Workspace/Graph/通信/碎片/预留")
    p.add_argument("--context", type=int, default=2048)
    p.add_argument("--block-size", type=int, default=16)
    args = p.parse_args()
    if min(args.params_b, args.layers, args.kv_heads, args.head_dim,
           args.vram_gib, args.context, args.block_size) <= 0:
        raise SystemExit("参数必须为正数")

    gib = 2 ** 30
    weights = args.params_b * 1e9 * args.weight_bits / 8 / gib
    kv_per_token = 2 * args.layers * args.kv_heads * args.head_dim * args.kv_bits / 8
    kv_budget = max(args.vram_gib - weights - args.overhead_gib, 0.0)
    token_capacity = kv_budget * gib / kv_per_token

    blocks_per_req = -(-args.context // args.block_size)
    kv_per_req = blocks_per_req * args.block_size * kv_per_token / gib
    max_concurrency = int(kv_budget // kv_per_req) if kv_per_req > 0 else 0

    print(f"weights_gib={weights:.2f}")
    print(f"kv_budget_gib={kv_budget:.2f}")
    print(f"kv_bytes_per_token={kv_per_token:.0f}")
    print(f"kv_token_capacity={token_capacity:.0f}")
    print(f"kv_gib_per_request={kv_per_req:.3f} (context={args.context}, block={args.block_size})")
    print(f"max_concurrency={max_concurrency}")
    print(f"block_internal_waste={1 - args.context / (blocks_per_req * args.block_size):.3f}")
    for ctx in [512, 1024, 2048, 4096, 8192]:
        blocks = -(-ctx // args.block_size)
        per = blocks * args.block_size * kv_per_token / gib
        print(f"context={ctx:5d} kv_gib={per:7.3f} concurrency={int(kv_budget // per) if per else 0:4d}")

if __name__ == "__main__":
    main()
```

运行：

```bash
python3 llm_capacity_planner.py
python3 llm_capacity_planner.py --params-b 7 --weight-bits 4 --kv-bits 8 --vram-gib 24
python3 llm_capacity_planner.py --kv-heads 8 --context 4096 --block-size 16
```

预期现象：权重量化主要释放静态容量，KV 量化与 GQA 主要释放动态容量；上下文翻倍时并发近似减半；Block 越大内部碎片越高。纸面并发只是上界，真实值还要扣掉 Workspace、Graph Pool 与突发长输出，必须用实测水位校正。

## 11. Level 1：Prefill/Decode 形态实验

不下载任何模型权重，用小型 Transformer 观察两阶段的计算形态与延迟构成。保存为 `prefill_decode_lab.py`：

```python
#!/usr/bin/env python3
import argparse
import statistics
import time

import torch
from torch import nn


class TinyDecoder(nn.Module):
    def __init__(self, vocab, width, layers, heads):
        super().__init__()
        self.embed = nn.Embedding(vocab, width)
        layer = nn.TransformerEncoderLayer(
            d_model=width, nhead=heads, dim_feedforward=width * 4,
            batch_first=True, norm_first=True)
        self.blocks = nn.TransformerEncoder(layer, num_layers=layers)
        self.head = nn.Linear(width, vocab)

    def forward(self, ids):
        return self.head(self.blocks(self.embed(ids)))


def sync():
    if torch.cuda.is_available():
        torch.cuda.synchronize()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prompt", type=int, default=512)
    p.add_argument("--decode-steps", type=int, default=64)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--width", type=int, default=512)
    p.add_argument("--layers", type=int, default=4)
    p.add_argument("--heads", type=int, default=8)
    p.add_argument("--vocab", type=int, default=4096)
    p.add_argument("--repeat", type=int, default=5)
    args = p.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    torch.manual_seed(0)
    model = TinyDecoder(args.vocab, args.width, args.layers, args.heads).eval().to(device)
    if device.type == "cuda":
        prop = torch.cuda.get_device_properties(device)
        print(f"gpu={prop.name} capability={prop.major}.{prop.minor}")
    print(f"device={device} torch={torch.__version__}")

    prompt = torch.randint(0, args.vocab, (args.batch, args.prompt), device=device)
    ttfts, tpots, prefill_ms, decode_ms = [], [], [], []

    with torch.inference_mode():
        for _ in range(args.repeat):
            sync()
            t0 = time.perf_counter()
            logits = model(prompt)                 # Prefill：一次处理全部 Prompt Token
            next_id = logits[:, -1].argmax(-1, keepdim=True)
            sync()
            ttft = (time.perf_counter() - t0) * 1000.0

            t1 = time.perf_counter()
            ids = prompt
            for _ in range(args.decode_steps):     # Decode：每步只新增一个 Token
                logits = model(ids)
                next_id = logits[:, -1].argmax(-1, keepdim=True)
                ids = torch.cat([ids, next_id], dim=1)
            sync()
            decode = (time.perf_counter() - t1) * 1000.0

            ttfts.append(ttft)
            prefill_ms.append(ttft)
            decode_ms.append(decode)
            tpots.append(decode / args.decode_steps)

    print(f"prefill_tokens={args.prompt * args.batch}")
    print(f"ttft_p50_ms={statistics.median(ttfts):.3f}")
    print(f"decode_total_p50_ms={statistics.median(decode_ms):.3f}")
    print(f"tpot_p50_ms={statistics.median(tpots):.3f}")
    print(f"prompt_tokens_per_s={args.prompt * args.batch / (statistics.median(prefill_ms) / 1000):.1f}")
    print(f"generation_tokens_per_s={args.batch * args.decode_steps / (statistics.median(decode_ms) / 1000):.1f}")
    if device.type == "cuda":
        print(f"peak_reserved_mib={torch.cuda.max_memory_reserved()/2**20:.1f}")


if __name__ == "__main__":
    main()
```

运行：

```bash
python prefill_decode_lab.py --prompt 128 --decode-steps 64
python prefill_decode_lab.py --prompt 1024 --decode-steps 64
python prefill_decode_lab.py --prompt 512 --batch 16 --decode-steps 32
nsys profile --trace=cuda,nvtx,osrt -o prefill_decode python prefill_decode_lab.py
```

这个实现刻意不做 KV Cache 复用，每步重算整个序列，因此它测到的是「无缓存 Decode」的上界成本。检查点：Prompt 变长时 Prefill 时间近似随 Token 数增长，而单步 Decode 成本随已生成长度增长得更快（$O(S^2)$ Attention 重算）；`batch` 增大时 Generation Tokens/s 上升但 TPOT 也上升，正是吞吐与延迟的交换；把这段循环换成带 `past_key_values` 的实现，即可对比 KV Cache 带来的数量级差异。真实服务还需要 Paged KV、变长 Attention 与迭代级调度，这些在后续篇目展开。

## 12. Level 2：多卡与架构边界

| 环境 | 推荐形态 | 需要实测的边界 |
| --- | --- | --- |
| 单张 RTX 3080/4090 | 单卡基线 + 量化 + Paged KV | KV 水位、Graph Bucket、最大上下文 |
| 双卡 PCIe（如 2×3080 20GB） | 两个独立副本 + Router | 跨 PCIe TP 的 Collective 是否得不偿失 |
| 双卡 NVLink | TP=2 或副本，按模型大小选择 | All-Reduce 暴露时间、小 Batch Decode 效率 |
| A100/H100 多卡 | TP + 可选 PP/EP、解耦式服务 | NVLink/NVSwitch 带宽、FP8 路径、KV 传输 |
| 纯 CPU | 容量规划与调度模拟 | 任何设备侧吞吐结论都不可外推 |

架构相关的量（HBM 带宽、互联带宽、低精度支持、显存容量）决定阈值；架构无关的部分（链路职责划分、双重预算、Goodput 定义、取消传播）在任何环境都成立。部署决策应先算容量与通信成本，再实测单请求延迟与开环 Goodput，最后才决定副本数、TP 度数与是否解耦。

## 写在最后

LLM 推理系统的难点在于它同时是一个调度系统与一个内存系统：Prefill 与 Decode 争夺时间片，KV Cache 争夺空间，Scheduler 必须在两者之间做出可解释的取舍。下一篇深入 Continuous Batching 与 Scheduler，看迭代级调度如何把空槽与队头阻塞降到最低。

下一篇：[Continuous Batching 与 Scheduler 优化](/source/AI-Infra/2-AI系统性能工程/24-ContinuousBatching与Scheduler优化)。