# AI Runtime 优化思想

本篇从调度、内存、执行图与设备协同角度理解 AI Runtime，建立系统级优化方法。

高性能 Kernel 并不等于高性能系统。一个算子可以达到很高的 Tensor Core 利用率，但用户请求仍可能在队列里等待；GPU 可以拥有很高的瞬时利用率，但大量工作可能是 Padding、重复计算或最终超时的无效请求。

AI Runtime 是模型与硬件之间的「现场总指挥」：接收工作，管理状态与内存，选择执行计划，把请求组合成 Batch，把任务投递到设备，并在超载时进行限流、降级与回退。下面不局限于某个推理框架，而是建立一套通用于训练 Runtime、推理 Runtime、在线服务与本地多 GPU 系统的优化思想。

## 1. 内容概览

- AI Runtime 的控制面、数据面与执行面。
- Scheduler、Batcher、Memory Manager、Executor、Compiler Cache 的职责。
- Hot Path/Cold Path、异步流水线、Shape Bucket 与内存复用思想。
- 用排队模型解释吞吐、尾延迟、并发与背压的关系。
- 端到端性能预算，而不是只优化 GPU Kernel。
- Admission Control、超时、取消、优先级与降级策略的设计。
- 判断下一步该优化 Scheduler、Batch、内存、Compiler、Kernel、通信还是拓扑。

## 2. 核心直觉：Runtime 优化的是「流」，不是单个点

把 AI 系统想象成机场：请求是乘客；Scheduler 是塔台；Batch 是同一班飞机；GPU 是跑道与飞机；KV Cache/Activation/Workspace 是登机口与行李位；CUDA Stream 是不同作业通道；Graph/Compiled Plan 是预先批准的固定航线；Backpressure 是限制进入候机楼的人数。

只把飞机发动机调快，并不能解决登机口拥堵、跑道冲突与乘客错过转机。Runtime 优化要关注请求从进入到完成的整条路径：

```text
接入 → 排队 → 预处理 → 调度/组批 → H2D → 计算/通信
    → 后处理 → D2H/流式输出 → 计量与回收
```

任何一段变慢，都会通过队列放大成尾延迟。

## 3. AI Runtime 的分层架构

### 3.1 控制面、数据面与执行面

```text
┌──────────────────────── 控制面 ────────────────────────┐
│ 模型版本、配置、路由、配额、扩缩容、健康检查、回滚      │
└────────────────────────────────────────────────────────┘
                           │
┌──────────────────────── 数据面 ────────────────────────┐
│ Gateway → Queue → Admission → Scheduler → Batcher      │
│                   ↕ 状态/KV/缓存 ↕                      │
└────────────────────────────────────────────────────────┘
                           │
┌──────────────────────── 执行面 ────────────────────────┐
│ Executor → Compiler/Plan Cache → Memory Pool            │
│          → CUDA Stream/Graph → Kernel/Library/NCCL      │
└────────────────────────────────────────────────────────┘
                           │
                   GPU / CPU / 网络 / 存储
```

控制面变化频率低，负责「应该运行什么」；数据面高频处理请求，负责「何时运行谁」；执行面贴近设备，负责「如何运行得快」。把三者混在一个同步线程中，会让配置、日志或网络抖动进入计算热路径。

### 3.2 Runtime 的核心组件

| 组件 | 主要职责 | 常见失败模式 |
| --- | --- | --- |
| Admission Controller | 限制并发和显存承诺 | 无界接收导致 OOM 和 P99 爆炸 |
| Scheduler | 选择下一批工作 | 饥饿、队头阻塞、不公平 |
| Batcher | 合并兼容请求 | 等待过久或 Padding 浪费 |
| Executor | 驱动设备执行 | 同步过多、Launch 碎片 |
| Memory Manager | 分配、复用、驱逐 | 碎片、地址不稳定、错误驱逐 |
| Plan/Graph Cache | 复用编译和捕获结果 | Shape 爆炸、缓存污染 |
| State Manager | 管理 KV、会话、随机状态 | 泄漏、状态串扰、恢复错误 |
| Telemetry | 观测阶段、队列和资源 | 只有平均值，无法解释 P99 |

## 4. 第一原则：先定义有效工作

Runtime 最终优化目标应是 Goodput，而不是单一的 GPU Utilization：

$$
Goodput = \frac{\text{满足正确性、SLO 和业务约束的完成工作}}{\text{时间或资源成本}}
$$

以下工作可能提高 Throughput 却不提高 Goodput：大 Batch 导致大量请求超过 P99 SLO；取消的请求仍继续生成几十个 Token；Padding 占用了大部分 FLOPs；低精度提高 Tokens/s 却使质量不达标；过载时不断重试制造重试风暴；GPU 100% 忙于预热或低优先级任务，在线请求却超时。

Runtime 的指标应至少同时包含：吞吐、P50/P95/P99、超时率、拒绝率、取消浪费、有效 Token/s、显存水位与成本。

## 5. 第二原则：拆分 Cold Path 与 Hot Path

**Cold Path** 可以承受较高延迟，负责加载权重与初始化 CUDA Context；编译、Autotune、CUDA Graph Capture；建立 NCCL Communicator；分配大块内存池；构建 Shape/Plan Cache；健康检查与模型切换。

**Hot Path** 每请求或每 Token 执行，应尽可能：不分配大对象；不做文件 I/O、日志格式化或远程 RPC；不触发编译、模型加载与算法搜索；不做非必要 `.item()` 与全局同步；不持有粗粒度锁；使用预分配 Buffer、缓存 Plan 与异步队列。

判断方法很简单：如果某件事能在请求到来前完成，就不应放进每请求路径。

## 6. 第三原则：调度是性能功能，不只是排队

### 6.1 FIFO 不是万能策略

FIFO 简单公平，但长请求可能造成队头阻塞。Runtime 需要根据业务选择：

- FIFO：简单、可预测。
- 优先级：区分在线、批处理与系统任务。
- Deadline-aware：优先处理接近 SLO 的请求。
- Shortest-job-first：降低平均延迟，但需防止长请求饥饿。
- Fair-share：限制租户或用户长期占用。
- Cache-aware：优先命中同一 Prefix、KV 或已编译 Shape。
- Topology-aware：把任务放到数据与通信路径更近的设备。

### 6.2 Admission Control 比事后排队更重要

当到达率长期超过服务率，无论 Scheduler 多聪明，队列都会增长。设到达率 $\lambda$、每个 Worker 服务率 $\mu$、Worker 数 $c$：

$$
\rho = \frac{\lambda}{c\mu}
$$

当 $\rho$ 接近 1，排队延迟会非线性上升；当 $\rho > 1$，系统无法稳定。Admission Control 应在显存、并发、Deadline 或队列长度达到预算时拒绝、降级或转移请求。「尽量不拒绝」常常会变成「所有人都超时」，快速失败对 Goodput 更友好。

### 6.3 取消必须贯穿执行链

用户断开连接后，Gateway、Scheduler、Batcher 与 Executor 都要识别取消。若只在 API 层丢弃响应，GPU 仍继续计算，取消请求会吞噬有效请求资源。

## 7. 第四原则：Batching 是吞吐与等待的交换

### 7.1 批处理收益模型

设固定调度/Launch 开销 $a$、单样本增量计算成本 $b$、Batch 大小 $B$：

$$
T(B) = a + bB + \epsilon(B),\qquad \bar{T}(B) = \frac{a}{B} + b + \frac{\epsilon(B)}{B}
$$

增大 $B$ 能摊薄固定成本，但会增加排队等待、显存、Padding 与长尾干扰。最优 Batch 不是显存能装下的最大值，而是满足 SLO 时 Goodput 最高的值。

### 7.2 Dynamic Batching

Dynamic Batcher 在短时间窗口内收集兼容请求，核心旋钮是 `max_batch_size`（最大批量）、`max_wait`（允许首个请求等待多久）、Shape/Dtype/Model Version 兼容规则、Priority 与 Deadline、最大队列与超时动作。

如果流量低，等待满 Batch 会伤害延迟；如果流量高，Batch 往往自然形成，无需额外延迟。

### 7.3 Shape Bucket 与 Padding

混合长度请求直接组批会产生 Padding：

$$
Padding\ Waste = 1 - \frac{\sum_i L_i}{B \cdot \max_i L_i}
$$

按长度 Bucket 可以降低浪费，也有利于 `torch.compile`、CUDA Graph 与 TensorRT Plan 复用。但 Bucket 太细会减少可合批请求并扩大 Cache。

## 8. 第五原则：异步不是「不要同步」，而是显式依赖

一个高效 Runtime 会让 CPU 预处理、H2D、GPU 计算、通信、D2H 与后处理形成流水线：

```text
时间 →
CPU :  prep N+1 ─ prep N+2 ─ prep N+3
H2D :      copy N+1 ─ copy N+2 ─ copy N+3
GPU : run N ───── run N+1 ───── run N+2
D2H :          out N ───── out N+1
```

实现手段包括 Pinned Memory、`non_blocking=True`、CUDA Stream、Event、异步 NCCL 与独立线程/进程。关键不是删除所有同步，而是把同步缩小到真实数据依赖：Producer 完成后 Consumer 才能读取；Buffer 重用前必须确认前一次使用结束；输出返回前必须确认相应请求的设备工作完成；不相关请求不应被全局 `cudaDeviceSynchronize()` 一起阻塞。

## 9. 第六原则：内存是 Runtime 的一等资源

### 9.1 容量规划

Runtime 显存近似由以下部分构成：

$$
M = M_{weights} + M_{state/cache} + M_{activation} + M_{workspace} + M_{graph} + M_{fragmentation} + M_{reserve}
$$

不能把 `free_memory / request_memory` 直接当最大并发，因为 Workspace、Graph Pool、临时通信 Buffer 与碎片会随执行计划变化。

### 9.2 预分配与对象生命周期

热路径频繁分配会引入锁、碎片与地址不稳定。常用方式：大块预分配后切分；Size-class Pool；Paged/Block 管理；Ring Buffer 或双 Buffer；请求完成或取消时明确归还；Watermark 触发 Admission 或 Eviction。

### 9.3 Eviction 不是免费空间

驱逐 KV、Activation 或编译缓存会带来重算、重新加载或重新编译。合理策略应比较

$$
Eviction\ Cost = Reload + Recompute + Tail\ Risk
$$

不能只看「释放了多少 GB」。

## 10. 第七原则：专门化与安全回退并存

Runtime 可以为高频路径建立编译后的计算图、CUDA Graph、TensorRT/后端 Engine、高频 Batch/Shape 的 Kernel 配置、常用 Prefix 或 KV Cache、特定 GPU 架构的低精度路径。

但专门化必然增加状态空间。每个优化路径都需要：Capability 检测；正确性门槛；Cache Key；生命周期与淘汰；不支持输入的通用回退；版本升级后的重新验证。

一个只有 Fast Path、没有 Fallback 的 Runtime 不是生产系统。

## 11. 第八原则：调优对象是关键路径

端到端请求延迟可以拆为

$$
L = L_{queue} + L_{pre} + L_{batch} + L_{H2D} + L_{dispatch} + L_{compute} + L_{comm} + L_{post} + L_{return}
$$

优化某阶段 $x$ 的收益上限受 Amdahl 定律约束：

$$
S = \frac{1}{(1-p_x) + p_x/s_x}
$$

若 Queue 占 P99 的 60%，把 Kernel 加速 2 倍不会解决主要问题。若 GPU 只有 20% 利用率但 Queue 很长，可能是 CPU 调度、锁、输入搬运或内存 Admission 在阻塞，而不是 GPU 不够快。

## 12. 瓶颈分析方法

### 12.1 分层证据

| 层级 | 关键证据 | 常见工具 |
| --- | --- | --- |
| 请求 | Arrival、Queue、Deadline、Cancel | 服务 Trace、Histogram |
| Scheduler | Batch Size、等待、拒绝、公平性 | Runtime Metrics |
| CPU | Thread、Lock、GIL、预处理、Launch | CPU Profile、Nsight Systems |
| GPU | Kernel、空洞、Memcpy、Stream | Nsight Systems/Compute |
| 内存 | Pool、碎片、Cache、Eviction | PyTorch Snapshot、Runtime Metrics |
| 多卡 | Rank 等待、Collective、拓扑 | NCCL 日志、Nsight、拓扑图 |

### 12.2 Runtime 诊断顺序

```text
SLO/Goodput 不达标
  │
  ├─ Queue 是否增长？
  │    ├─ 是：到达率、服务率、Admission、Batch、Worker
  │    └─ 否
  │
  ├─ CPU 是否喂不满 GPU？
  │    ├─ 是：锁、同步、预处理、Launch、H2D
  │    └─ 否
  │
  ├─ GPU 是否有长空洞或低效 Kernel？
  │    ├─ 空洞：Graph、Batch、Stream、通信重叠
  │    └─ 长热点：Fusion、精度、Kernel、并行策略
  │
  └─ Memory/Network 是否限制并发？
       ├─ Memory：Pool、KV、碎片、驱逐
       └─ Network：拓扑、Payload、重叠、解耦
```

### 12.3 不要只看平均值

Runtime 优化至少保留：Arrival Rate 与完成率；Queue Time P50/P95/P99；Service Time P50/P95/P99；Batch Size 分布；Inflight 与 Queue Depth；超时、拒绝、取消与重试；显存 Pool、碎片与驱逐；按 Model、Shape、Tenant、GPU、Rank 分组的指标。

## 13. Level 0：通用 CPU 调度模拟实验

下面的纯 Python 离散事件模拟器比较「立即执行」与「等待组批」，无需 GPU 或第三方库。它不是具体推理框架实现，但能验证 Batch、Queue 与 SLO 的基本关系。保存为 `runtime_scheduler_sim.py`：

```python
#!/usr/bin/env python3
import argparse
import math
import random
import statistics

def percentile(values, q):
    values = sorted(values)
    pos = (len(values) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    if lo == hi:
        return values[lo]
    return values[lo] * (hi - pos) + values[hi] * (pos - lo)

def make_arrivals(count, rate, seed):
    rng = random.Random(seed)
    now = 0.0
    arrivals = []
    for _ in range(count):
        now += rng.expovariate(rate) * 1000.0
        arrivals.append(now)
    return arrivals

def simulate(arrivals, max_batch, max_wait_ms, fixed_ms, per_item_ms, slo_ms):
    pending = []
    latencies = []
    now = 0.0
    index = 0
    batches = []

    while index < len(arrivals) or pending:
        if not pending and index < len(arrivals):
            now = max(now, arrivals[index])
        # 先接收 Server 忙碌期间已经到达的请求。
        while index < len(arrivals) and arrivals[index] <= now:
            pending.append(arrivals[index])
            index += 1

        # 若尚未满批，最多等到队首请求的 max_wait 截止时间。
        deadline = max(now, pending[0] + max_wait_ms)
        while (index < len(arrivals) and len(pending) < max_batch
               and arrivals[index] <= deadline):
            pending.append(arrivals[index])
            index += 1

        if len(pending) >= max_batch:
            start = max(now, pending[max_batch - 1])
        else:
            start = deadline

        batch = pending[:max_batch]
        del pending[:max_batch]
        service = fixed_ms + per_item_ms * len(batch)
        now = start + service
        batches.append(len(batch))
        latencies.extend(now - arrival for arrival in batch)

    elapsed_s = (now - arrivals[0]) / 1000.0
    return {
        "throughput": len(arrivals) / elapsed_s,
        "p50": percentile(latencies, 0.50),
        "p95": percentile(latencies, 0.95),
        "p99": percentile(latencies, 0.99),
        "goodput": sum(x <= slo_ms for x in latencies) / elapsed_s,
        "slo_rate": sum(x <= slo_ms for x in latencies) / len(latencies),
        "avg_batch": statistics.mean(batches),
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--requests", type=int, default=5000)
    p.add_argument("--arrival-rps", type=float, default=300.0)
    p.add_argument("--max-batch", type=int, default=16)
    p.add_argument("--max-wait-ms", type=float, default=2.0)
    p.add_argument("--fixed-ms", type=float, default=1.0)
    p.add_argument("--per-item-ms", type=float, default=0.15)
    p.add_argument("--slo-ms", type=float, default=20.0)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    if min(args.requests, args.max_batch) < 1:
        raise SystemExit("requests/max-batch 必须为正整数")
    if min(args.arrival_rps, args.fixed_ms, args.per_item_ms, args.slo_ms) <= 0:
        raise SystemExit("速率和时间参数必须为正数")
    if args.max_wait_ms < 0:
        raise SystemExit("max-wait-ms 不能为负数")

    arrivals = make_arrivals(args.requests, args.arrival_rps, args.seed)
    immediate = simulate(arrivals, 1, 0.0, args.fixed_ms,
                         args.per_item_ms, args.slo_ms)
    batched = simulate(arrivals, args.max_batch, args.max_wait_ms,
                       args.fixed_ms, args.per_item_ms, args.slo_ms)

    print("mode throughput_rps p50_ms p95_ms p99_ms goodput_rps slo_rate avg_batch")
    for name, result in [("immediate", immediate), ("batched", batched)]:
        print(f"{name:9s} {result['throughput']:14.2f} "
              f"{result['p50']:7.2f} {result['p95']:7.2f} "
              f"{result['p99']:7.2f} {result['goodput']:11.2f} "
              f"{result['slo_rate']:8.3f} {result['avg_batch']:9.2f}")

if __name__ == "__main__":
    main()
```

运行命令：

```bash
python3 runtime_scheduler_sim.py
python3 runtime_scheduler_sim.py --arrival-rps 50 --max-wait-ms 5
python3 runtime_scheduler_sim.py --arrival-rps 900 --max-batch 32 --slo-ms 20
```

预期现象：中高负载时组批能摊薄固定开销、提高 Throughput；低流量时额外等待可能让 P50/P99 变差，Batch 也未必能装满；高于系统服务能力时队列增长，P99 与 SLO 达标率迅速恶化；最大 Throughput 配置不一定拥有最高 Goodput。

## 14. Level 1：GPU 异步流水线与组批实验

把上面的调度结论落到设备上：对比「同步逐请求」与「Pinned Memory + 独立 Copy Stream + 预分配 Buffer + 组批」两种执行方式。保存为 `runtime_pipeline_lab.py`：

```python
#!/usr/bin/env python3
import argparse
import statistics
import time

import torch
from torch import nn


class TinyNet(nn.Module):
    def __init__(self, width):
        super().__init__()
        self.fc1 = nn.Linear(width, width)
        self.fc2 = nn.Linear(width, width)

    def forward(self, x):
        return self.fc2(torch.nn.functional.gelu(self.fc1(x)))


def sync():
    torch.cuda.synchronize()


def bench(fn, warmup, iters):
    for _ in range(warmup):
        fn()
    sync()
    samples = []
    for _ in range(iters):
        t0 = time.perf_counter()
        fn()
        sync()
        samples.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(samples), statistics.quantiles(samples, n=20)[18]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--width", type=int, default=1024)
    p.add_argument("--batch", type=int, default=8)
    p.add_argument("--requests", type=int, default=64)
    p.add_argument("--warmup", type=int, default=5)
    p.add_argument("--iters", type=int, default=20)
    args = p.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("需要可用的 NVIDIA CUDA GPU")
    device = torch.device("cuda")
    prop = torch.cuda.get_device_properties(device)
    print(f"torch={torch.__version__} gpu={prop.name} "
          f"capability={prop.major}.{prop.minor}")

    torch.manual_seed(0)
    model = TinyNet(args.width).eval().to(device)
    host = torch.randn(args.requests, args.width)
    pinned = host.pin_memory()

    def sync_path():
        # 每请求：Pageable H2D + 单条执行 + 立即取回
        with torch.inference_mode():
            for i in range(args.requests):
                x = host[i:i + 1].to(device)
                y = model(x)
                _ = y.cpu()

    # 预分配 Buffer 与独立 Copy Stream，避免热路径分配与全局同步
    buf = torch.empty(args.batch, args.width, device=device)
    out = torch.empty(args.batch, args.width, device=device)
    copy_stream = torch.cuda.Stream()

    def async_batched_path():
        with torch.inference_mode():
            for start in range(0, args.requests, args.batch):
                n = min(args.batch, args.requests - start)
                copy_stream.wait_stream(torch.cuda.current_stream())
                with torch.cuda.stream(copy_stream):
                    buf[:n].copy_(pinned[start:start + n], non_blocking=True)
                torch.cuda.current_stream().wait_stream(copy_stream)
                out[:n] = model(buf[:n])
                _ = out[:n].to("cpu", non_blocking=False)

    sync_p50, sync_p95 = bench(sync_path, args.warmup, args.iters)
    pipe_p50, pipe_p95 = bench(async_batched_path, args.warmup, args.iters)
    print(f"sync_p50_ms={sync_p50:.3f} sync_p95_ms={sync_p95:.3f}")
    print(f"pipeline_p50_ms={pipe_p50:.3f} pipeline_p95_ms={pipe_p95:.3f}")
    print(f"speedup={sync_p50 / pipe_p50:.3f}x")
    print(f"per_request_sync_us={sync_p50 * 1000 / args.requests:.2f}")
    print(f"per_request_pipeline_us={pipe_p50 * 1000 / args.requests:.2f}")
    print(f"peak_reserved_mib={torch.cuda.max_memory_reserved()/2**20:.1f}")


if __name__ == "__main__":
    main()
```

运行与观测：

```bash
python runtime_pipeline_lab.py --requests 64 --batch 8
python runtime_pipeline_lab.py --requests 64 --batch 1
python runtime_pipeline_lab.py --requests 256 --batch 32
nsys profile --trace=cuda,nvtx,osrt -o runtime_pipeline python runtime_pipeline_lab.py
```

检查点：`batch=1` 时组批收益应消失，只剩 Pinned Memory 与预分配的收益；`requests` 增大后每请求成本应下降，说明固定开销被摊薄；在 Nsight Systems 中确认 Copy Stream 与计算 Stream 是否真正重叠，而不是被 `wait_stream` 串行化；`peak_reserved` 上升通常来自预分配 Buffer，属于预期而非泄漏。

这个实验只覆盖单机执行面。真实服务还需要在数据面加入 Admission、Deadline 与取消传播，否则 GPU 侧再快也会被队列与无效工作抵消。

## 15. Level 2：架构与部署边界

| 场景 | 可验证的 Runtime 思想 | 不可验证的部分 |
| --- | --- | --- |
| 单张消费级 GPU（如 RTX 3080） | Hot/Cold Path 拆分、组批、Pinned Memory、Stream 重叠、Graph 捕获 | NVLink/NVSwitch 拓扑、大规模 Collective |
| 双卡 PCIe 工作站 | 每卡独立 Runtime、Rank 间等待、DDP 重叠 | 数据中心级 NVLS/CollNet 路径 |
| A100/H100 数据中心卡 | 更大 Batch 与 KV 容量、FP8/BF16 专门化路径、MPS/MIG 隔离 | 消费卡上无法复现的互联带宽 |
| 纯 CPU 环境 | 调度模拟、排队模型、Goodput 与 SLO 权衡 | 任何设备执行面结论 |

Runtime 思想本身与架构无关：控制面/数据面/执行面拆分、Admission、Bucket、内存池与回退在任何设备上都成立。与架构强相关的是具体阈值——最大 Batch、KV 容量、Graph 数量、低精度路径与互联拓扑，必须在目标硬件上实测，不能跨设备外推。

生产落地时把八条原则转成检查清单：是否定义了 Goodput 而非只看利用率；Cold Path 是否全部前置；是否有 Admission 与取消传播；Batch 与 `max_wait` 是否按 SLO 调过；同步是否只保留真实依赖；内存是否预分配并有水位线；每条 Fast Path 是否有 Fallback；优化对象是否落在关键路径上。

## 写在最后

Runtime 优化的本质是把「单个算子快」升级为「整条请求流有效」：先定义 Goodput，再拆冷热路径，然后用调度、组批、异步与内存管理把关键路径上的浪费逐段消除。下一篇进入 LLM 推理系统架构，看这些原则在 Prefill/Decode 两阶段负载上如何具体落地。

下一篇：[LLM 推理系统架构](/source/AI-Infra/2-AI系统性能工程/23-LLM推理系统架构)。