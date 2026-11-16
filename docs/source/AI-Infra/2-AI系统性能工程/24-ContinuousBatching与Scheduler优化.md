# Continuous Batching 与 Scheduler 优化

本篇深入 Continuous Batching 与 Scheduler 的工作机制，学会在吞吐、延迟与公平性之间进行权衡。

传统 Batch 推理像一辆「坐满才发车、全员到终点才返程」的班车。大模型在线请求却持续到达，Prompt 与输出长度差异很大：短请求早已结束，长请求仍在逐 Token 生成。如果 Batch 必须等最长请求完成，短请求释放出的计算槽位就会一直空着。

Continuous Batching（也称 In-flight Batching 或 Iteration-level Batching）把调度边界从「整个请求」缩小到「一个推理迭代」。每轮 Decode 后，已结束或已取消的请求立即退出，新请求可以在后续迭代进入；Scheduler 同时协调 Prefill、Decode、KV Cache 与 Token Budget。重点不是背诵某个框架参数，而是建立一套可迁移的调度模型。

## 1. 内容概览

- Static、Dynamic 与 Continuous Batching 的区别。
- 请求级调度与迭代级调度的本质差异。
- `max_num_seqs`、`max_num_batched_tokens`、KV Block 与 Deadline 的联合约束。
- Prefill 优先、Decode 优先、Chunked Prefill、公平性与吞吐的取舍。
- 队头阻塞、Padding Waste、排队稳定性与 Goodput 的分析方法。
- 取消、抢占、Backpressure、优先级与多租户隔离机制。
- 用真实长度分布与开环负载调优推理服务。

## 2. 核心直觉：从「整车发车」变成「每站换乘」

设一个静态 Batch 中四个请求分别需要生成 8、16、32、64 个 Token。若 Kernel 使用固定 Batch Width，前 8 步四个槽位都有效；之后请求陆续完成，但 Batch 仍要运行到第 64 步。

有效槽位数 $N_{useful} = 8+16+32+64 = 120$，静态 Batch 分配的槽位 $N_{allocated} = 4 \times 64 = 256$，仅从输出长度 Padding 看：

$$
Efficiency = \frac{120}{256} = 46.875\%
$$

Continuous Batching 在短请求结束后立刻把新请求放入空槽，使活动 Batch 尽量保持充实。它不能减少每个有效 Token 本身的模型计算，却能减少：等待固定 Batch 凑齐的时间；等最长序列完成造成的空槽；短请求被长请求拖住的队头阻塞；请求取消后仍执行的无效 Decode；低负载时的大量 Padding。

## 3. 三种 Batching 不要混淆

### 3.1 Static Batching

请求在执行前形成固定 Batch，直到全部完成才接收下一批。适合离线、长度分桶充分、吞吐优先的场景。优点是实施简单、Shape 稳定、容易使用 CUDA Graph；缺点是在线等待与输出长度 Padding 明显，短请求无法释放槽位。

### 3.2 Dynamic Batching

服务器在一个短等待窗口内收集兼容请求，形成较大的请求级 Batch。它减少小请求 Launch 开销，但 Batch 一旦开始通常仍保持固定。Dynamic Batching 常用于固定输出 Shape 的模型服务；对自回归 LLM，它只解决「开始时如何组批」，没有解决「生成过程中请求何时退出与补位」。

### 3.3 Continuous Batching

每个推理迭代重新形成活动集合：

```text
Iteration 0: A(Prefill), B(Prefill)
Iteration 1: A(Decode), B(Decode), C(Prefill chunk)
Iteration 2: A(Decode), B完成, C(Prefill chunk)
Iteration 3: A(Decode), C(Decode), D(Prefill)
Iteration 4: A完成, C(Decode), D(Decode), E(Prefill)
```

Continuous Batching 是调度策略，不是单个 CUDA Kernel。生产系统还需要 Packed Input、Block Table、KV Cache Manager、变长 Attention 与输出状态管理配合。

## 4. Scheduler 每轮在做什么

一个简化的 Decode Loop：

```python
while server_alive:
    collect_new_requests()
    propagate_cancellation()
    reclaim_finished_kv_blocks()
    token_budget = max_num_batched_tokens

    schedule_decode_requests(token_budget, kv_budget, deadlines)
    schedule_prefill_chunks(remaining_budget, kv_budget, priorities)
    reserve_kv_blocks()

    execute_one_iteration()
    sample_and_stream_tokens()
    update_request_state_and_metrics()
```

调度器必须维护至少三类队列：Waiting（已准入但尚未开始）、Running（已有 KV、正在 Prefill 或 Decode）、Finished/Cancelled（等待回收状态与 KV Block）。有抢占或 Offload 时还会有 Paused/Swapped 队列。

## 5. 调度的四个约束

### 5.1 Sequence Budget

`max_num_seqs` 限制一轮中可处理的最大活动序列数，它控制 Batch Width、调度元数据、CUDA Graph Shape 与部分 Workspace。设置过小会让 GPU 吃不饱；设置过大可能增加 KV 压力、单步延迟、Graph Pool 与 Scheduler 成本。

### 5.2 Token Budget

`max_num_batched_tokens` 限制一轮最多处理多少输入 Token。对 Decode 请求，每个活动序列通常消耗一个 Token；Prefill 可能一次消耗数百或数千 Token。一轮预算近似为

$$
B_{token} = N_{decode} + \sum_j C^{prefill}_j
$$

其中 $C^{prefill}_j$ 是本轮为第 $j$ 个 Prompt 处理的 Chunk 大小。只看 Sequence 数会把「128 个 Decode Token」与「128 个 8K Prompt」误认为同样成本。

### 5.3 KV Budget

每个新 Prefill 与每个 Decode Token 都可能申请新 KV Block，调度前必须确认

$$
KV_{used} + KV_{reserved} + KV_{new} \le KV_{capacity}
$$

否则要等待、拒绝、抢占、驱逐可重算状态或降低并发。先执行后发现 OOM，不是调度策略。

### 5.4 Time 与 SLO Budget

即使 Token 与 KV 容量允许，一轮太大也可能让 Decode ITL 超标。实际目标是

$$
\max Goodput \quad \text{s.t.} \quad P99(TTFT) \le SLO_{TTFT},\ P99(ITL) \le SLO_{ITL}
$$

最大吞吐配置与最大 SLO Goodput 配置可能不同。

## 6. Prefill 与 Decode 的优先级冲突

**Prefill 优先**：先处理等待 Prompt，可降低新请求 TTFT，但大 Prompt 可能占满一轮 Token Budget，让已有会话的 Decode 暂停，形成 ITL 尖峰。适合首 Token 极敏感、输出较短、负载可控的场景。

**Decode 优先**：先为所有 Running Decode 请求保留一个 Token，再把剩余预算给 Prefill。它保护流式体验与 ITL，却可能让新请求长时间等不到 Prefill。适合聊天、语音交互与稳定流式输出。

**Chunked Prefill**：长 Prompt 不再一次占完整轮次，而是按剩余 Token Budget 切片：

$$
C_i = \min(PromptRemaining_i,\ BudgetRemaining)
$$

优点是 Decode 与 Prefill 可以在相邻或同一调度周期共存、长 Prompt 不易垄断 GPU、预算更容易满足、ITL 尖峰通常更可控。代价是 Prefill 被拆成更多迭代从而增加 Launch 与调度开销、小 Chunk 的 GEMM 效率可能下降、新请求 TTFT 可能增加、Partial Prefill 状态更复杂。

因此 Chunk Size 是 TTFT、ITL 与吞吐之间的旋钮，不存在跨硬件通用的最优值。

## 7. 调度策略

| 策略 | 收益 | 风险与前提 |
| --- | --- | --- |
| FIFO | 实现简单、容易解释 | 长 Prompt 或超长输出导致队头阻塞 |
| Shortest Remaining Processing Time | 降低平均延迟 | 长请求饥饿；输出长度通常只是上限，无法准确预知 |
| Deadline-aware | 贴近 SLO 的紧迫度排序 | 需要可靠成本估计，否则频繁插队造成抖动 |
| Priority / Fair Share | 区分在线、离线、付费等级与系统任务 | 必须有 Aging 或租户配额，避免低优先级永久饥饿 |
| Cache-aware | 复用 Prefix/KV 减少 Prefill | 牺牲 FIFO 公平性；需评估等待增长与跨租户安全 |
| Capacity-aware | 保守策略保证不被 KV 中途打断 | 激进策略填满 GPU 但增加重算与尾延迟 |

## 8. 性能模型

### 8.1 静态 Decode Padding Waste

Batch 内输出长度为 $O_i$：

$$
Waste_{static} = 1 - \frac{\sum_i O_i}{B \cdot \max_i O_i}
$$

Continuous Batching 用新请求补位，长期有效率更接近活动槽位率，但仍会受队列不足、KV 不足与 Shape Bucket 约束。

### 8.2 每轮成本

$$
T_{iter} = T_{schedule} + T_{launch} + T_{prefill}(N_p) + T_{decode}(N_d, S) + T_{comm} + T_{sample}
$$

$N_p$ 是本轮 Prefill Token 数，$N_d$ 是 Decode 序列数，$S$ 表示上下文长度分布。调度优化只有在节省的 GPU 空洞或 Padding 大于新增的 Scheduler、Pack 与 Block Table 开销时才有收益。

### 8.3 排队稳定性

$$
\rho = \frac{\lambda}{\mu}
$$

当 $\rho$ 接近 1，排队与 P99 会非线性上升。Continuous Batching 能提高 $\mu$，却不能让超过物理容量的系统稳定，仍需 Admission Control 与 Backpressure。

### 8.4 Little 定律在显存规划中的含义

$$
L = \lambda W
$$

平均在途请求数 $L$ 随到达率与停留时间增长。在途请求越多，KV 占用越高；为了追求吞吐而拉长 $W$，可能反过来压缩可用并发并触发抢占。

## 9. 调度器数据结构与关键路径

### 9.1 请求状态

每个 Request 至少包含：Request ID、租户、优先级、Arrival 与 Deadline；Prompt Token 数、已 Prefill Token 数；已生成 Token 数、最大输出长度、停止状态；KV Block Table 与 Prefix 复用信息；Sampling、LoRA、约束解码与多模态元数据；取消、暂停、重算与流式输出状态。

### 9.2 Scheduler 热路径原则

避免每轮扫描无关的全部历史请求；队列操作保持近似 $O(1)$ 或 $O(\log N)$；避免 Python 对每个 Token 做重型对象创建；调度结果使用紧凑数组传递给 Executor；KV 预留与状态转换必须原子化；Metrics 不应持有全局锁或同步 GPU。

### 9.3 Packed Batch

将变长 Prompt Padding 到最大长度会浪费计算。生产 Runtime 常把有效 Token 紧凑排列，并用位置、序列边界与 Block Table 还原逻辑关系：

```text
Padded : [A A A A][B B _ _][C C C _]
Packed : [A A A A B B C C C]
Meta   : offsets=[0,4,6,9]
```

Packed Input 提高有效 Token 密度，但要求 Attention Kernel 与调度元数据正确处理边界。

## 10. 瓶颈分析方法

调度问题必须用分布而不是平均值判断。至少采集：

- **TTFT 分解**：Queue、Tokenize、Prefill、首 Token 采样与流式发送各占多少。
- **ITL 分布**：P50/P95/P99 与最大值，尖峰是否与新 Prefill、抢占、驱逐或 GC 对齐。
- **槽位有效率**：每轮活动序列数 / `max_num_seqs`，以及有效 Token 数 / Padding 后 Token 数。
- **KV 事件**：Block 使用率、抢占次数、重算 Token 数、驱逐与恢复耗时。
- **公平性**：按租户/优先级分组的等待时间与被抢占次数，检查是否存在饥饿。
- **Scheduler 自身成本**：每轮调度耗时占 $T_{iter}$ 的比例，Python 对象创建与锁竞争。

诊断顺序：先看队列是否增长（容量问题），再看 ITL 尖峰是否与 Prefill 对齐（干扰问题），再看槽位有效率是否偏低（补位不足或 KV 受限），最后才看 Kernel 与通信。若 Scheduler 每轮耗时已经接近 GPU 步长时间，优化方向是数据结构与批量化，而不是继续加大 Batch。

## 11. Level 0：离散事件调度模拟

纯 Python 模拟 Static、Dynamic 与 Continuous 三种策略，无需 GPU 与第三方库。保存为 `batching_scheduler_sim.py`：

```python
#!/usr/bin/env python3
import argparse
import math
import random
import statistics


def percentile(values, q):
    xs = sorted(values)
    pos = (len(xs) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return xs[lo] if lo == hi else xs[lo] * (hi - pos) + xs[hi] * (pos - lo)


def make_requests(count, rate, seed, prompt_mean, out_mean):
    rng = random.Random(seed)
    now, reqs = 0.0, []
    for i in range(count):
        now += rng.expovariate(rate) * 1000.0
        prompt = max(1, int(rng.expovariate(1.0 / prompt_mean)))
        out = max(1, int(rng.expovariate(1.0 / out_mean)))
        reqs.append({"id": i, "arrival": now, "prompt": prompt, "out": out})
    return reqs


def simulate(reqs, mode, max_batch, max_wait_ms, fixed_ms,
             per_token_ms, per_seq_ms, slo_ttft, slo_itl, chunk):
    """per_token_ms: 每 Prefill Token 成本；per_seq_ms: 每 Decode 序列每步成本"""
    waiting = list(reqs)
    running = []          # 每项：[req, remaining_out, last_token_time, itls, ttft]
    latencies, ttfts, itls = [], [], []
    now, wi, useful, allocated, slo_ok = 0.0, 0, 0, 0, 0
    pending_batch = []

    def admit(start_time):
        nonlocal wi
        if mode == "static" and running:
            return start_time        # 静态批未跑完不接收新请求
        t = start_time
        while wi < len(waiting) and len(running) < max_batch:
            r = waiting[wi]
            if r["arrival"] > t:
                break
            wi += 1
            ntok = min(r["prompt"], chunk) if mode == "continuous" else r["prompt"]
            t += fixed_ms + per_token_ms * ntok
            running.append([r, r["out"], t, [], t - r["arrival"]])
            ttfts.append(t - r["arrival"])
            if mode == "continuous":
                break                # 迭代级准入：每轮最多补一个新请求
        return t

    while wi < len(waiting) or running or pending_batch:
        if not running and wi < len(waiting):
            now = max(now, waiting[wi]["arrival"])
        if mode == "dynamic":
            deadline = now + max_wait_ms
            while (wi < len(waiting) and len(running) + len(pending_batch) < max_batch
                   and waiting[wi]["arrival"] <= deadline):
                pending_batch.append(waiting[wi])
                wi += 1
            now = max(now, deadline) if pending_batch else now
            for r in pending_batch:
                cost = fixed_ms + per_token_ms * r["prompt"]
                running.append([r, r["out"], now + cost, [], now + cost - r["arrival"]])
                ttfts.append(now + cost - r["arrival"])
            pending_batch = []
        else:
            now = admit(now)

        if not running:
            continue

        # 一轮迭代：所有活动序列各生成一个 Token
        step = fixed_ms + per_seq_ms * len(running)
        if mode == "continuous":
            step += per_token_ms * min(chunk, 64)   # 同轮夹带 Prefill chunk 的近似成本
        now += step
        allocated += len(running)
        useful += sum(1 for it in running if it[1] > 0)
        finished = []
        for item in running:
            if item[1] <= 0:
                continue             # 静态批中已完成却仍占槽位的请求
            r, remaining, last, hist, ttft = item
            hist.append(now - last)
            item[2] = now
            item[1] = remaining - 1
            if item[1] <= 0:
                finished.append(item)
                latencies.append(now - r["arrival"])
                itls.extend(hist)
                mean_itl = statistics.mean(hist) if hist else 0.0
                if ttft <= slo_ttft and mean_itl <= slo_itl:
                    slo_ok += 1
        if mode == "static":
            if all(it[1] <= 0 for it in running):
                running.clear()      # 整批结束后才释放槽位
            continue
        for item in finished:
            running.remove(item)
        if mode == "continuous":
            now = admit(now)

    elapsed = (now - reqs[0]["arrival"]) / 1000.0
    return {
        "throughput_rps": len(reqs) / elapsed,
        "ttft_p50": percentile(ttfts, 0.5),
        "ttft_p99": percentile(ttfts, 0.99),
        "itl_p50": percentile(itls, 0.5),
        "itl_p99": percentile(itls, 0.99),
        "e2e_p99": percentile(latencies, 0.99),
        "goodput_rps": slo_ok / elapsed,
        "slo_rate": slo_ok / len(reqs),
        "slot_efficiency": useful / allocated if allocated else 0.0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--requests", type=int, default=2000)
    p.add_argument("--arrival-rps", type=float, default=20.0)
    p.add_argument("--max-batch", type=int, default=16)
    p.add_argument("--max-wait-ms", type=float, default=5.0)
    p.add_argument("--fixed-ms", type=float, default=1.0)
    p.add_argument("--per-token-ms", type=float, default=0.02)
    p.add_argument("--per-seq-ms", type=float, default=0.4)
    p.add_argument("--prompt-mean", type=int, default=256)
    p.add_argument("--out-mean", type=int, default=64)
    p.add_argument("--chunk", type=int, default=128)
    p.add_argument("--slo-ttft", type=float, default=500.0)
    p.add_argument("--slo-itl", type=float, default=60.0)
    p.add_argument("--seed", type=int, default=11)
    args = p.parse_args()
    if min(args.requests, args.max_batch, args.chunk) < 1:
        raise SystemExit("requests/max-batch/chunk 必须为正整数")

    reqs = make_requests(args.requests, args.arrival_rps, args.seed,
                         args.prompt_mean, args.out_mean)
    print("mode        rps   ttft_p50  ttft_p99  itl_p50  itl_p99  e2e_p99  goodput  slo_rate  slots")
    for mode in ["static", "dynamic", "continuous"]:
        r = simulate(reqs, mode, args.max_batch, args.max_wait_ms, args.fixed_ms,
                     args.per_token_ms, args.per_seq_ms, args.slo_ttft,
                     args.slo_itl, args.chunk)
        print(f"{mode:10s} {r['throughput_rps']:6.2f} {r['ttft_p50']:9.2f} "
              f"{r['ttft_p99']:9.2f} {r['itl_p50']:8.2f} {r['itl_p99']:8.2f} "
              f"{r['e2e_p99']:8.2f} {r['goodput_rps']:8.2f} "
              f"{r['slo_rate']:9.3f} {r['slot_efficiency']:6.3f}")


if __name__ == "__main__":
    main()
```

运行：

```bash
python3 batching_scheduler_sim.py
python3 batching_scheduler_sim.py --arrival-rps 5 --out-mean 128
python3 batching_scheduler_sim.py --arrival-rps 60 --max-batch 32 --chunk 256
python3 batching_scheduler_sim.py --out-mean 256 --prompt-mean 2048 --chunk 64
```

预期现象：输出长度方差越大，Static 的槽位有效率与 P99 越差；低到达率下 Dynamic 的 `max_wait` 直接抬高 TTFT；Continuous 的槽位有效率接近 1，但 `chunk` 太小会拉长 TTFT、太大则抬高 ITL P99；到达率超过服务能力时三种模式的队列都会增长，说明调度不能替代 Admission。

模拟器只验证调度逻辑与量纲关系，不模拟 Attention 的真实非线性成本、KV 碎片与通信，绝对数值不可外推到具体框架。

## 12. Level 1：GPU 上的连续 Decode 组批实验

在设备侧对比「固定 Batch 等最长序列」与「迭代级补位」的吞吐差异。保存为 `continuous_decode_lab.py`：

```python
#!/usr/bin/env python3
import argparse
import random
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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--requests", type=int, default=64)
    p.add_argument("--max-batch", type=int, default=8)
    p.add_argument("--width", type=int, default=256)
    p.add_argument("--layers", type=int, default=2)
    p.add_argument("--heads", type=int, default=4)
    p.add_argument("--vocab", type=int, default=2048)
    p.add_argument("--prompt", type=int, default=64)
    p.add_argument("--seed", type=int, default=3)
    args = p.parse_args()
    if not torch.cuda.is_available():
        raise SystemExit("需要可用的 NVIDIA CUDA GPU")

    device = torch.device("cuda")
    torch.manual_seed(0)
    rng = random.Random(args.seed)
    model = TinyDecoder(args.vocab, args.width, args.layers, args.heads).eval().to(device)
    outs = [rng.choice([8, 16, 32, 64, 96]) for _ in range(args.requests)]
    print(f"gpu={torch.cuda.get_device_properties(device).name} "
          f"total_output_tokens={sum(outs)}")

    def run_static():
        done_tokens, t0 = 0, time.perf_counter()
        with torch.inference_mode():
            for start in range(0, args.requests, args.max_batch):
                group = outs[start:start + args.max_batch]
                width = max(group)
                ids = torch.randint(0, args.vocab, (len(group), args.prompt), device=device)
                for _ in range(width):          # 整批跑到最长序列
                    logits = model(ids)
                    nxt = logits[:, -1].argmax(-1, keepdim=True)
                    ids = torch.cat([ids, nxt], dim=1)
                done_tokens += sum(group)       # 只有有效 Token 计入
        torch.cuda.synchronize()
        return (time.perf_counter() - t0), done_tokens

    def run_continuous():
        done_tokens, t0 = 0, time.perf_counter()
        pending = list(range(args.requests))
        active = []                             # [req_idx, remaining, ids]
        with torch.inference_mode():
            while pending or active:
                while pending and len(active) < args.max_batch:
                    i = pending.pop(0)
                    ids = torch.randint(0, args.vocab, (1, args.prompt), device=device)
                    active.append([i, outs[i], ids])
                if not active:
                    continue
                width = max(a[2].shape[1] for a in active)
                # 变长序列按当前最大长度对齐，结束后立即退出并补位
                padded = torch.zeros(len(active), width, dtype=torch.long, device=device)
                for k, a in enumerate(active):
                    padded[k, :a[2].shape[1]] = a[2][0]
                logits = model(padded)
                nxt = logits[:, -1].argmax(-1, keepdim=True)
                keep = []
                for k, a in enumerate(active):
                    a[2] = torch.cat([a[2], nxt[k:k + 1]], dim=1)
                    a[1] -= 1
                    if a[1] > 0:
                        keep.append(a)
                    else:
                        done_tokens += outs[a[0]]
                active = keep
        torch.cuda.synchronize()
        return (time.perf_counter() - t0), done_tokens

    for name, fn in [("static", run_static), ("continuous", run_continuous)]:
        elapsed, tokens = fn()
        print(f"{name:10s} wall_s={elapsed:.3f} useful_tokens={tokens} "
              f"useful_tokens_per_s={tokens / elapsed:.1f}")


if __name__ == "__main__":
    main()
```

运行与检查点：

```bash
python continuous_decode_lab.py --requests 64 --max-batch 8
python continuous_decode_lab.py --requests 64 --max-batch 1
python continuous_decode_lab.py --requests 128 --max-batch 16
nsys profile --trace=cuda,nvtx,osrt -o continuous_decode python continuous_decode_lab.py
```

`max_batch=1` 时两种策略应趋同；输出长度方差越大，Continuous 的有效 Tokens/s 优势越明显；在时间线上确认 Static 后段是否出现「大部分槽位已完成却仍在计算」的浪费。该实现仍用 Padding 对齐而非 Packed Input，也未复用 KV，因此测到的是调度收益的下界；真实框架叠加 Paged KV 与变长 Attention 后差距会更大。

## 13. Level 2：真实服务调优与架构边界

在 vLLM 等推理服务上验证上述模型时，方法比参数更重要：

1. **用真实长度分布**：从生产日志采样 Prompt/Output 长度直方图，而不是统一固定长度；长度分布决定 Padding、KV 占用与抢占频率。
2. **开环负载**：按目标到达率独立发压（不依赖响应返回再发下一条），才能观察队列增长与 P99；闭环压测会掩盖过载。
3. **单变量扫描**：依次扫 `max_num_seqs`、`max_num_batched_tokens`、Chunk Size、KV 水位（如 `gpu_memory_utilization`）、是否启用 Prefix Caching，每次记录 TTFT/ITL 分位数、Goodput、抢占与重算次数。
4. **找 Goodput 拐点**：吞吐继续上升但 SLO 达标率开始下降的位置，就是该长度分布下的容量边界。
5. **验证取消与抢占**：主动断连一部分请求，确认 KV Block 被释放、生成停止；人为压低 KV 水位，观察抢占是否带来可接受的重算成本。

| 环境 | 可验证内容 | 边界 |
| --- | --- | --- |
| 纯 CPU | 调度模拟、排队稳定性、公平性与 Goodput 权衡 | 任何设备侧吞吐数值 |
| 单张消费级 GPU | 迭代级补位、Token Budget、Chunked Prefill、KV 水位 | 大模型容量、TP/EP 通信 |
| 双卡 PCIe | 副本路由与负载不均、跨卡 TP 的代价 | NVLink 级 Collective 效率 |
| 数据中心多卡 | TP/PP/EP 下的调度与通信耦合、解耦式服务 | 消费卡无法复现的互联与低精度路径 |

调度策略与四个约束是架构无关的；具体阈值（最大序列数、Chunk Size、KV 水位）必须在目标硬件与真实长度分布上实测。

## 14. 量化补充：分块干扰与 Token 预算的代价

第 6 节的 Chunk Size 旋钮可以算出具体数字。**块长相同，注意力工作量仍随上下文增长**：本块 $c$ 个新 token、已有上下文 $h$，配对数

$$
N_{\mathrm{pair}}=ch+\frac{c(c+1)}{2},
$$

矩形项是新 token 对旧上下文的访问，三角形项是块内因果注意力。$c=512$ 时首块 131328 对全来自块内，8K 输入的末块（$h=7680$）增至 4063488 对，约 31 倍；投影与 FFN 每块基本相同，实测末块主干矩阵运算比首块多约 32%、执行时间中位数从 25.3 ms 增到 35.1 ms（+39%）——**同样大小的块越来越慢，是上下文而非块本身**。反过来缩小块也有代价：256 token 块拆成两个 128，调度机会多一次、矩阵行数减半，但每小块都要读同一份权重——一层 FFN 288 MiB 权重的读取从 288 变 576 MiB。调度器应选能满足输出间隔要求的较大块，让新增启动与读取尽量少（NanoFlow 一类 intra-device 流水同理）。

**Token 预算与执行形状是两件事**。预算决定本轮分给新请求多少工作，实际执行却要把 token 组成矩阵选 kernel 或预捕获的 Graph：预捕获 16/32 行两档时，17-32 行都填到 32 行，从 18 行减到 17 行仍执行 32 行图，减到 16 行才换小图——**少处理一个 token 不一定少做一份计算**；为 17 行另捕获一图省 15 行填充，但捕获要准备时间、重放缓冲长期占内存（21 篇第 13 节的输入复制账）。预算本身的取舍有回放数据：六条请求每隔 80 ms 到达，每轮 token 上限从 512 增到 8192，后到请求排队从约 149 ms 降到不足 0.1 ms，最长输出间隔却从约 32 ms 增到 183 ms。确定预算分两步：先由允许的输出间隔定一轮最多执行多久，再结合上下文长度与预设形状换算可处理的新 token 数——同时间内上下文长的请求能处理的新 token 少，上下文短的可以用更大的块。

## 写在最后

Continuous Batching 的本质是把调度粒度降到迭代级，让槽位与 KV 都能及时回收再利用；而 Scheduler 的真正难点是在 Sequence、Token、KV、SLO 四重预算下同时保住吞吐、尾延迟与公平性。下一篇聚焦其中的空间维度——KV Cache 的性能优化。

下一篇：[KV Cache 性能优化](/source/AI-Infra/2-AI系统性能工程/25-KVCache性能优化)。