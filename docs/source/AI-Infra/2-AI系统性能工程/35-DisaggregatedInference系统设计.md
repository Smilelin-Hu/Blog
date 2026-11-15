# Disaggregated Inference 系统设计

本项目设计一套 Prefill 与 Decode 分离的推理系统，完成资源规划、通信分析与高可用方案。

最终产物不是一张概念图，而是一份带容量模型、KV 传输预算、路由规则、故障语义、SLO、观测指标、回退路径和验证计划的系统设计。

```text
请求入口
  → Prefill Router → Prefill Worker Pool
  → KV Transfer / KV Metadata Commit
  → Decode Router → Decode Worker Pool
  → Streaming Response
```

Prefill 通常是计算密集的大矩阵阶段，Decode 通常是内存带宽敏感的小步迭代。解耦允许两类资源独立扩缩和调度，但引入 KV 传输、跨池排队、一致性、故障恢复和更多网络跳数。只有收益超过这些成本时，解耦才成立。

Level 0 使用纯 Python 容量规划器，任何机器可运行。Level 1 使用单机或 PCIe 多 GPU 验证调度和传输成本。Level 2 才验证 GPUDirect RDMA、NIXL、NVLink/NVSwitch 或跨节点高速网络。

## 1. 内容概览与交付物

做完之后应当能够：从 Prefill、KV Transfer、Decode 三阶段建立延迟和吞吐模型；使用 Erlang-C 估计排队等待和稳定性边界；计算 KV 传输字节、链路占用和最小 Decode 容量；设计 Request ID、KV Handle、幂等、超时和重试语义；设计 P/D 独立扩缩、拓扑感知路由和过载保护；区分模拟、单机验证与真实 RDMA/NVLink 实测；用端到端 Goodput 决定是否采用解耦，而不是只比较阶段峰值。

前置知识：LLM 推理系统、解耦推理与 MoE 相关内容，以及 vLLM 推理优化、KV Cache 优化两个项目；排队论基础、HTTP/gRPC、KV Cache、GPU 拓扑与分布式系统；可选 vLLM、NVIDIA Dynamo/NIXL 或等价的受支持框架。

```text
disaggregated-inference-design/
├── disagg_capacity_planner.py
├── architecture.md
├── api_contract.md
├── failure_matrix.md
├── deployment/
│   ├── prefill.yaml
│   ├── decode.yaml
│   └── router.yaml
└── reports/
    ├── capacity.json
    ├── transfer_sweep.json
    └── validation_report.md
```

与其他项目不同，这里的交付物以设计文档为主、脚本为辅。`architecture.md` 要画出控制面与数据面的分离，`api_contract.md` 要写清幂等与条件提交语义，`failure_matrix.md` 要覆盖每一类故障的可见症状与处理动作。三份文档缺一份，设计就无法评审。

## 2. 核心直觉：把两种不同形态的工作独立排队

Monolithic Worker 同时处理 Prefill 与 Decode。长 Prefill 可能干扰正在生成的请求；Decode 又可能让大 GEMM 难以形成高效 Batch。解耦后：

$$
T_{TTFT} = T_{queue,p} + T_{prefill} + T_{transfer} + T_{queue,d} + T_{first\ decode}
$$

$$
T_{E2E} = T_{TTFT} + (N_{out} - 1) \times TPOT
$$

对比单体服务的 TTFT 构成，解耦多出了 $T_{transfer}$ 与 $T_{queue,d}$ 两项。这意味着解耦在 TTFT 上天然处于劣势，收益必须来自别处：Prefill 不再被 Decode 打断、Decode 不再被长 Prefill 阻塞、两类资源可以按各自瓶颈独立扩缩、甚至可以使用异构硬件（Prefill 用算力强的卡，Decode 用显存带宽大或容量大的卡）。

收益来自阶段隔离、独立 Batch、异构硬件与独立扩缩；成本来自 KV 传输、额外排队、网络、元数据和故障处理。

解耦必要条件不是「Prefill 和 Decode 不同」，而是：

$$
Gain_{isolation} + Gain_{scaling} > Cost_{transfer} + Cost_{queue} + Cost_{operation}
$$

这个不等式是本项目所有决策的总纲。后面每一个设计选择——KV 路径、副本数、路由策略、回退方式——都是在压低右侧或抬高左侧。

## 3. KV 传输模型

Prefill 产生的 KV 字节：

$$
Bytes_{KV} = S_{input} \times 2 \times L \times H_{kv} \times D_{head} \times B_{dtype}
$$

链路有效带宽为 $BW_{effective}$，固定开销为 $T_{fixed}$：

$$
T_{transfer} = T_{fixed} + \frac{Bytes_{KV}}{BW_{effective}}
$$

协议 Header、序列化、注册内存、NUMA、PCIe Switch、网络拥塞和小消息效率都会让有效带宽低于标称带宽。

链路长期字节速率：

$$
BW_{required} = ArrivalRate \times Bytes_{KV}
$$

仅看单请求传输时间不足以判断系统是否稳定，还必须检查总吞吐和突发流量。

两个公式回答的是不同问题：$T_{transfer}$ 决定单请求 TTFT 里多了多少毫秒，$BW_{required}$ 决定这条链路会不会成为系统级瓶颈。一条链路完全可能「单请求传输只要 8 ms」却「在目标到达率下占用率 90%」，后者才是失稳的前兆。

注意 $Bytes_{KV}$ 只与输入长度有关，与输出长度无关。因此长输入短输出的负载对传输压力最大，短输入长输出的负载几乎不产生传输压力——这直接决定了解耦在哪类业务上划算。

## 4. 排队稳定性

Prefill 平均服务时间 $S_p$、副本数 $c_p$、到达率 $\lambda$：

$$
\rho_p = \frac{\lambda S_p}{c_p}
$$

Decode 同理。若 $\rho \ge 1$，稳态队列没有有限均值。生产系统不应长期运行在 100% 理论利用率，应为流量突发、尾部请求和故障副本保留余量。

链路也要做同样的检查：

$$
\rho_{link} = \frac{ArrivalRate \times Bytes_{KV}}{BW_{effective}}
$$

三个利用率必须同时小于 1，系统才存在稳态。实践中更严格的门槛是三者都不超过 0.7～0.8，因为 Erlang-C 的等待时间在 $\rho \to 1$ 时呈 $1/(1-\rho)$ 发散：利用率从 0.8 升到 0.9，平均排队时间会翻倍以上。

## 5. Level 0：完整容量规划器

### 5.1 disagg_capacity_planner.py

下面的脚本计算 KV 传输、阶段利用率、Erlang-C 平均排队、TTFT/E2E 近似和链路占用。它用于方案筛选，不替代离散事件模拟与真实集群压测。

保存为 `disagg_capacity_planner.py`：

```python
#!/usr/bin/env python3
import argparse
import json
import math
from pathlib import Path

def erlang_c_wait(arrival_rate, service_seconds, servers):
    offered = arrival_rate * service_seconds
    rho = offered / servers
    if rho >= 1:
        return math.inf, rho
    series = sum(offered ** n / math.factorial(n) for n in range(servers))
    tail = offered ** servers / math.factorial(servers) / (1 - rho)
    probability_wait = tail / (series + tail)
    wait_seconds = probability_wait * service_seconds / (servers * (1 - rho))
    return wait_seconds, rho

def main():
    parser = argparse.ArgumentParser(description="P/D 解耦容量规划器")
    parser.add_argument("--arrival-rate", type=float, default=4.0)
    parser.add_argument("--prefill-workers", type=int, default=2)
    parser.add_argument("--decode-workers", type=int, default=4)
    parser.add_argument("--prefill-ms", type=float, default=200.0)
    parser.add_argument("--decode-ms-per-token", type=float, default=20.0)
    parser.add_argument("--output-tokens", type=int, default=128)
    parser.add_argument("--input-tokens", type=int, default=2048)
    parser.add_argument("--layers", type=int, default=32)
    parser.add_argument("--kv-heads", type=int, default=8)
    parser.add_argument("--head-dim", type=int, default=128)
    parser.add_argument("--dtype-bytes", type=float, default=2.0)
    parser.add_argument("--link-gbps", type=float, default=100.0)
    parser.add_argument("--link-efficiency", type=float, default=0.70)
    parser.add_argument("--fixed-transfer-ms", type=float, default=0.2)
    parser.add_argument("--output", default="reports/capacity.json")
    args = parser.parse_args()

    positive = [args.arrival_rate, args.prefill_workers, args.decode_workers,
                args.prefill_ms, args.decode_ms_per_token, args.output_tokens,
                args.input_tokens, args.layers, args.kv_heads, args.head_dim,
                args.dtype_bytes, args.link_gbps]
    if any(value <= 0 for value in positive):
        raise ValueError("容量参数必须大于 0")
    if not 0 < args.link_efficiency <= 1:
        raise ValueError("link-efficiency 必须位于 (0, 1]")

    kv_bytes_per_token = 2 * args.layers * args.kv_heads * args.head_dim * args.dtype_bytes
    kv_bytes = args.input_tokens * kv_bytes_per_token
    effective_bytes_per_second = args.link_gbps * 1e9 / 8 * args.link_efficiency
    transfer_seconds = args.fixed_transfer_ms / 1000 + kv_bytes / effective_bytes_per_second
    required_link_bytes_per_second = args.arrival_rate * kv_bytes
    link_utilization = required_link_bytes_per_second / effective_bytes_per_second

    prefill_service = args.prefill_ms / 1000
    decode_service = args.decode_ms_per_token / 1000 * args.output_tokens
    prefill_wait, prefill_rho = erlang_c_wait(
        args.arrival_rate, prefill_service, args.prefill_workers
    )
    decode_wait, decode_rho = erlang_c_wait(
        args.arrival_rate, decode_service, args.decode_workers
    )
    stable = all(value < 1 for value in (prefill_rho, decode_rho, link_utilization))

    if stable:
        ttft = (prefill_wait + prefill_service + transfer_seconds +
                decode_wait + args.decode_ms_per_token / 1000)
        e2e = ttft + (args.output_tokens - 1) * args.decode_ms_per_token / 1000
    else:
        ttft = None
        e2e = None

    result = {
        "stable": stable,
        "kv": {
            "bytes_per_token": kv_bytes_per_token,
            "mib_per_request": kv_bytes / 2**20,
            "required_link_gbps": required_link_bytes_per_second * 8 / 1e9,
            "effective_link_gbps": args.link_gbps * args.link_efficiency,
            "link_utilization": link_utilization,
            "transfer_ms": transfer_seconds * 1000,
        },
        "prefill": {
            "workers": args.prefill_workers,
            "utilization": prefill_rho,
            "mean_queue_ms": None if math.isinf(prefill_wait) else prefill_wait * 1000,
        },
        "decode": {
            "workers": args.decode_workers,
            "utilization": decode_rho,
            "mean_queue_ms": None if math.isinf(decode_wait) else decode_wait * 1000,
        },
        "latency_estimate": {
            "ttft_ms": None if ttft is None else ttft * 1000,
            "e2e_ms": None if e2e is None else e2e * 1000,
        },
        "warning": (
            "Erlang-C 假设泊松到达、指数服务时间与同质 Worker；"
            "未包含 Batch、抢占、长尾、KV 元数据和故障。"
        ),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

if __name__ == "__main__":
    main()
```

几处设计要点：

- **`erlang_c_wait` 在 $\rho \ge 1$ 时返回 `math.inf`**：不是返回一个很大的数，而是明确的无穷。下游据此把延迟写成 `null`，避免「不稳定系统却报出有限平均延迟」这种自相矛盾的结论。
- **`stable` 同时检查三项**：Prefill、Decode、链路。任一越界即判定不稳定，这与第 4 节的三利用率门槛一致。
- **`decode_service` 是「每 Token 时间 × 输出 Token」**：把整条请求在 Decode 池的占用时间建模为一个服务时长。这是简化——真实 Decode 是逐 Token 推进且可被 Continuous Batching 共享，因此该模型会高估 Decode 副本需求，属于保守估计。
- **`link_gbps` 用 1e9 而非 2^30**：网络带宽按十进制 Gbps 计，显存按二进制 GiB 计，两者混用是容量估算里的常见错误。脚本里 `mib_per_request` 用 `2**20`、`required_link_gbps` 用 `1e9`，正是刻意区分。
- **`--link-efficiency` 独立参数**：把「标称带宽」与「有效带宽」分开，便于做保守/乐观两档方案对比。
- **`warning` 写进结果**：Erlang-C 的三条假设（泊松到达、指数服务时间、同质 Worker）在真实推理服务里都不严格成立，结果文件必须自带这个声明。

### 5.2 运行命令

```bash
mkdir -p reports
python disagg_capacity_planner.py \
  --arrival-rate 4 --prefill-workers 2 --decode-workers 16 \
  --prefill-ms 200 --decode-ms-per-token 20 --output-tokens 128 \
  --input-tokens 2048 --link-gbps 100 --link-efficiency 0.70 \
  --output reports/capacity.json
```

注意命令里把 Decode 副本数从默认的 4 改成了 16。这不是随意取值：默认参数下 Decode 服务时间为 $20\ \text{ms} \times 128 = 2.56\ \text{s}$，到达率 4 时 offered load 为 $4 \times 2.56 = 10.24$，4 个副本的利用率 $\rho_d = 2.56 \ge 1$，系统直接不稳定。必须先按服务时间比推算副本数，再跑规划器。

扫描到达率、P/D 副本数和链路：

```bash
for rate in 1 2 4 8 16; do
  python disagg_capacity_planner.py --arrival-rate "$rate" \
    --prefill-workers 2 --decode-workers 16 \
    --output "reports/rate_${rate}.json"
done

for link in 16 32 64 100 200 400; do
  python disagg_capacity_planner.py --link-gbps "$link" \
    --output "reports/link_${link}.json"
done
```

### 5.3 默认参数下的推导结果

按公式手工推导（输入 2048 Token、32 层、8 KV Head、Head Dim 128、BF16、100 Gbps 链路、效率 0.70、P=2、D=16、到达率 4 req/s）：

| 量 | 推导值 | 说明 |
| --- | --- | --- |
| 每 Token KV 字节 | 131072 B（128 KiB） | $2 \times 32 \times 8 \times 128 \times 2$ |
| 单请求 KV | 256 MiB | $2048 \times 128$ KiB |
| 有效链路带宽 | 70 Gbps = 8.75 GB/s | $100 \times 0.70$ |
| 单请求传输时间 | ≈30.9 ms | $0.2 + 256\ \text{MiB} / 8.75\ \text{GB/s}$ |
| 链路需求速率 | ≈8.59 Gbps | $4 \times 256$ MiB/s |
| 链路利用率 | ≈0.123 | 需求 / 有效带宽 |
| Prefill 利用率 | 0.40 | $4 \times 0.2 / 2$ |
| Prefill 平均排队 | ≈38 ms | Erlang-C，$a=0.8$、$c=2$ |
| Decode 利用率 | 0.64 | $4 \times 2.56 / 16$ |
| Decode 平均排队 | ≈30 ms | Erlang-C，$a=10.24$、$c=16$ |
| TTFT 估计 | ≈319 ms | 五项相加 |
| E2E 估计 | ≈2.86 s | TTFT + $127 \times 20$ ms |

表中数字为公式推导，不是实测。其中最有决策价值的一条是：单请求 KV 达 256 MiB，在 70 Gbps 有效带宽下传输就要 30.9 ms，占 TTFT 的近 10%。若链路换成 PCIe 或百兆级网络，这一项会迅速膨胀到数百毫秒，解耦的 TTFT 劣势将难以接受。

另一个关键比例来自服务时间：单 Prefill Worker 支撑 $1/0.2 = 5$ req/s，单 Decode Worker 支撑 $1/2.56 \approx 0.39$ req/s，因此平衡的 P:D 副本比约为 **1:12.8**。这解释了为什么长输出业务的解耦集群里 Decode 池远大于 Prefill 池，也说明「P:D = 1:1」通常是错误起点。

### 5.4 到达率与链路扫描

固定 P=2、D=16、链路 100 Gbps，按公式推导各到达率下的利用率：

| 到达率 (req/s) | $\rho_p$ | $\rho_d$ | $\rho_{link}$ | 稳态 | 首个越界环节 |
| --- | --- | --- | --- | --- | --- |
| 1 | 0.10 | 0.16 | 0.031 | 是 | — |
| 2 | 0.20 | 0.32 | 0.061 | 是 | — |
| 4 | 0.40 | 0.64 | 0.123 | 是 | — |
| 8 | 0.80 | 1.28 | 0.245 | 否 | Decode |
| 16 | 1.60 | 2.56 | 0.491 | 否 | Prefill 与 Decode |

三条稳定性边界分别是：Decode 约 6.25 req/s（$16/2.56$）、Prefill 约 10 req/s（$2/0.2$）、链路约 32.6 req/s（$8.75\ \text{GB/s} \div 256\ \text{MiB}$）。**Decode 最先失稳**，因此扩容顺序应先 Decode 后 Prefill，最后才是链路。

固定到达率 4 req/s，扫描链路带宽：

| 标称带宽 (Gbps) | 有效带宽 (Gbps) | 传输时间 (ms) | 链路利用率 |
| --- | --- | --- | --- |
| 16 | 11.2 | ≈191.9 | 0.767 |
| 32 | 22.4 | ≈96.1 | 0.383 |
| 64 | 44.8 | ≈48.1 | 0.192 |
| 100 | 70.0 | ≈30.9 | 0.123 |
| 200 | 140.0 | ≈15.5 | 0.061 |
| 400 | 280.0 | ≈7.9 | 0.031 |

16 Gbps 一行值得单独警惕：单请求传输 192 ms 看似「还能接受」，但链路利用率已达 0.767，任何突发都会让传输排队急剧放大。这正是第 3 节强调「两个公式回答不同问题」的实例。

### 5.5 预期现象

Decode 服务时间是「每 Token 时间 × 输出 Token」，因此长输出可能需要明显更多 Decode 副本。若任何阶段或链路利用率达到 1，规划器把稳态延迟输出为 `null`，避免在不稳定队列上制造有限平均延迟。

还应观察到：输出 Token 数翻倍时，Decode 副本需求近似翻倍，而 KV 传输字节完全不变；输入 Token 数翻倍时，KV 传输字节与 Prefill 时间都上升，Decode 副本需求不变。两类长度对系统资源的压力方向完全不同，这是解耦架构能做针对性优化的根本原因。

## 6. 系统架构设计

### 6.1 控制面与数据面

```text
Control Plane
├─ Worker Registry / Health / Capability
├─ Model Revision / KV Layout Version
├─ Autoscaler / Placement / Topology
└─ Config Rollout / Drain / Rollback

Data Plane
Client → Gateway → Prefill Router → P Worker
                                  ├─ KV Data → Transfer Fabric → D Worker
                                  └─ KV Commit → Metadata Service/Router
Client ← Streaming Gateway ← Decode Router ← D Worker
```

KV 数据路径与元数据路径应分开设计。大块 KV 不应绕经普通控制面数据库；控制面只保存 Handle、位置、版本、长度、校验和、租约和状态。

这条原则的量级依据很直接：单请求 KV 是 256 MiB 级，而元数据是几百字节级，两者相差六个数量级。把 KV 塞进控制面存储会瞬间打爆数据库带宽与延迟，并让控制面成为数据面的单点。

### 6.2 Request/KV 状态机

```text
RECEIVED
  → PREFILL_ASSIGNED
  → PREFILL_RUNNING
  → KV_TRANSFERRING
  → KV_COMMITTED
  → DECODE_ASSIGNED
  → STREAMING
  → COMPLETED

任意阶段 → CANCELLED / TIMED_OUT / FAILED
```

Decode Worker 只有在 KV 完整写入、校验通过并提交元数据后才能读取。先暴露 Handle、后完成传输会产生部分 KV 可见性问题。

`KV_COMMITTED` 是整个状态机的关键屏障：它之前 KV 对 Decode 完全不可见，它之后 KV 必须完整可用。所有重试、取消、故障恢复逻辑都围绕这个屏障设计——屏障前的失败可以安全重做，屏障后的失败需要副本或重算。

## 7. API 契约

### 7.1 Prefill 请求

```json
{
  "request_id": "uuid",
  "model_revision": "immutable-hash",
  "input_token_ids": [1, 2, 3],
  "kv_layout_version": "v1",
  "deadline_unix_ms": 0,
  "preferred_decode_pool": "pool-a"
}
```

字段设计的三个要点：`model_revision` 用不可变哈希而非「latest」标签，避免滚动发布期间 P 与 D 使用不同权重；`kv_layout_version` 显式声明 KV 张量排布，因为不同 Attention 实现的 KV 布局不兼容；`deadline_unix_ms` 用绝对时间而非相对超时，跨多跳传递时不会因各节点处理耗时而累积漂移。

传 `input_token_ids` 而不是原始文本，是为了把 Tokenizer 固定在 Gateway 一侧，保证 P/D 看到完全相同的 Token 序列。

### 7.2 KV Commit

```json
{
  "request_id": "uuid",
  "kv_handle": "opaque-handle",
  "model_revision": "immutable-hash",
  "token_count": 2048,
  "dtype": "bf16",
  "bytes": 268435456,
  "checksum": "...",
  "locations": ["worker-d-17"],
  "lease_expiry_unix_ms": 0,
  "status": "COMMITTED"
}
```

`bytes` 字段的 268435456 恰好是 256 MiB，与第 5.3 节推导的单请求 KV 一致——契约里的示例值应当能被容量模型复算，这是文档自洽性的一个检查点。

`checksum` 用于检测传输损坏，`lease_expiry_unix_ms` 用于防止 KV 泄漏：Decode 侧崩溃或请求取消后，租约到期即可回收显存，不依赖对端主动通知。`locations` 是数组，为多副本留出空间。

`request_id` 必须幂等。重试 Prefill 时，新 Attempt 不能让旧 KV Commit 覆盖新状态；可使用 `(request_id, attempt_id, generation)` 做条件提交。

具体语义是：元数据服务只接受 `generation` 单调递增的提交，旧 Attempt 的迟到 Commit 会被拒绝并触发其 KV 清理。缺少这个机制时，一次超时重试可能让 Decode 读到上一次 Attempt 的 KV，产生难以复现的错误输出。

## 8. 路由策略

### 8.1 Prefill Router

评分可综合：

$$
Score_p = w_1 Q_p + w_2 EstimatedPrefill + w_3 MemoryPressure + w_4 TransferDistance
$$

四项分别对应：队列长度、预估 Prefill 计算量（与输入 Token 数相关）、显存压力、以及到候选 Decode 池的传输距离。前三项决定「多久能算完」，第四项决定「算完多久能送到」。只按队列长度路由会忽略长请求与短请求的成本差异，也会把 KV 送到很远的 Decode 池。

权重需要按负载标定：长输入短输出场景应提高 $w_4$，短输入长输出场景 $w_4$ 几乎无关紧要。

### 8.2 Decode Router

优先级顺序：

1. 已持有目标 KV 的 Decode Worker；
2. 同 NVLink/NVSwitch 域或同节点；
3. 同机架 RDMA；
4. 需要跨域传输但仍满足 Deadline；
5. 拒绝、降级或回退 Monolithic。

路由不能只看队列长度。一个短队列但 KV 很远的 Worker，端到端可能更慢。

这个优先级本质上是按「KV 搬运成本」排序：第 1 级零搬运，第 2 级走高速域内互联，第 3 级走机架内网络，第 4 级跨域，第 5 级放弃解耦。每一级都应带上 Deadline 校验——若剩余时间预算已不足以覆盖传输，即使拓扑最优也应直接降级，而不是让请求注定超时。

## 9. 扩缩容

Prefill 与 Decode 独立扩缩：

- Prefill：队列 Token、Prefill GPU 时间、TTFT Budget；
- Decode：Active Sequences、Output Token/s、TPOT、KV 占用；
- Transfer：排队字节、有效带宽、P95 传输时间；
- 全局：Goodput、错误率、Deadline Miss、成本/Token。

扩容 Decode Worker 后并不会自动获得现有 KV。需要 Drain、复制、迁移或让新 Worker 只接新请求。

这是解耦架构区别于无状态服务扩缩容的核心难点。无状态服务加一个副本立刻分担流量；Decode 副本加进来时，在途请求的 KV 仍在老副本上，新副本只能接新请求。因此扩容的生效速度取决于请求生命周期：长输出请求可能持续数十秒，期间新副本利用率偏低。缩容更麻烦，必须先 Drain（停止接新请求、等在途请求生成完毕）再下线，否则会中断正在流式输出的连接。

三类指标里 Transfer 最容易被漏掉。P/D 都健康但链路饱和时，症状是 TTFT 整体抬升而两侧队列都不长，只看 Worker 指标会误判为「模型变慢」。

## 10. 故障矩阵

| 故障 | 可见症状 | 正确处理 |
| --- | --- | --- |
| Prefill Worker 崩溃 | 无 Commit | 同 Attempt 超时，幂等重试 |
| 传输中断 | KV 不完整 | 不提交 Handle，清理临时 Buffer |
| Commit 后 D Worker 崩溃 | 流中断 | 有副本则重路由；否则重做 Prefill |
| Router 重启 | 状态丢失风险 | 状态外置或从 Worker/租约恢复 |
| Client 取消 | 无人消费 KV | 传播取消并释放 KV |
| Model Revision 不同 | 错误输出/崩溃 | 强校验并拒绝路由 |
| 网络分区 | 超时、积压 | 熔断、Deadline、回退/拒绝 |
| 慢 Worker | P99 恶化 | Deadline-aware 路由与 Drain |

「自动重试所有失败」可能放大负载。重试必须受 Deadline、Budget、Attempt 和幂等约束。

矩阵里最危险的一行是「Model Revision 不同」：它的症状不是报错而是**错误输出**，可能被当成模型质量问题排查很久。因此版本校验必须发生在路由阶段而非推理阶段，且不匹配时直接拒绝，不做任何「尽力而为」的兼容。

「Client 取消」一行关系到成本：解耦架构下 KV 已经跨池搬运，若取消不传播，P 侧与 D 侧都会保留无人消费的 256 MiB 显存，高取消率场景下会迅速耗尽 KV 池。取消传播延迟因此被列为观测指标。

## 11. Level 1：单机与常见 GPU 验证

没有高速互联时仍可验证：

1. 在 CPU 内存中生成等大小 KV Buffer；
2. 测量本机内存拷贝和 PCIe GPU↔Host/GPU↔GPU；
3. 用独立队列模拟 P/D Worker；
4. 注入延迟、失败、取消和重复 Commit；
5. 用 vLLM 推理优化项目的流式压测比较 Monolithic 与模拟 Disaggregated 路由。

环境记录：

```bash
mkdir -p reports
{
  date -Iseconds
  nvidia-smi -L
  nvidia-smi topo -m
  nvidia-smi nvlink -s 2>/dev/null || true
  ip -br link
  rdma link 2>/dev/null || true
} 2>&1 | tee reports/environment.txt
```

双 RTX 3080 通常以 PCIe 为跨 GPU 路径。这个实验能验证慢链路回退和路由策略，不能等价模拟 NVLink、NVSwitch 或 GPUDirect RDMA。

Level 1 的价值在于验证**协议与状态机**，而不是带宽数字。故障注入（延迟、失败、取消、重复 Commit）在 CPU 模拟里就能完整覆盖，且比真实集群更容易构造极端场景。带宽相关结论则必须留到 Level 2，报告中要明确区分这两类证据。

`2>/dev/null || true` 的写法保证在没有 NVLink 或 RDMA 工具的机器上环境记录不会中断——缺失本身就是需要记录的事实。

## 12. Level 2：真实框架与高速互联

可选择当前受支持的 vLLM Disaggregated Serving、NVIDIA Dynamo/NIXL 或等价实现。由于 CLI、Connector 和部署拓扑持续变化，必须：

1. 锁定框架 Release/Commit；
2. 保存官方示例原始配置；
3. 运行框架自带 Smoke Test；
4. 确认 KV Layout、Model Revision、Dtype 与 Connector 一致；
5. 保存完整启动命令和日志；
6. 用相同模型/负载对比 Monolithic。

第 4 步是解耦特有的坑：单体服务里 KV 布局是引擎内部细节，解耦后它变成跨进程契约。P 侧与 D 侧若使用不同 Attention 后端或不同 dtype，KV 字节流可能「传输成功、校验通过」但语义错误，因此必须显式核对而不依赖默认值。

### 12.1 硬件边界

| 路径 | 可验证内容 | 不可外推 |
| --- | --- | --- |
| 单机 CPU Copy | 协议、状态机 | GPUDirect 带宽 |
| 双消费 GPU PCIe | GPU P2P/Host Staging | NVSwitch 全互联 |
| RTX 3090 特定 NVLink | 单机 NVLink 对照 | 数据中心 NVSwitch/RDMA |
| H100/H200 NVLink/NVSwitch | Hopper 数据中心路径 | Blackwell NVLink 5 |
| B100/B200/GB200 | Blackwell Fabric | 消费级 RTX 5090 等价能力 |

RTX 4090 是 Ada Lovelace，不是 Blackwell；RTX 5090 属于 Blackwell，但消费卡不等于 GB200 NVL 系统。

「不可外推」列比「可验证内容」列更重要。解耦架构的收益高度依赖互联带宽，而消费级与数据中心级互联差一到两个数量级，把 PCIe 上「解耦不划算」的结论推广到 NVSwitch 集群（或反之）都是错误的。

## 13. 验证计划

### 13.1 功能验证

- Token 与 Monolithic 基线一致；
- Model Revision/Dtype/Layout 不一致被拒绝；
- Client Cancel 能释放 P/D/KV；
- 重复请求不会重复 Commit；
- 部分传输永不对 Decode 可见；
- Worker Drain 不丢正在生成的请求。

第一条是正确性底线：解耦只改变计算的组织方式，不应改变输出。在贪心解码下应逐 Token 比对；若存在数值差异，需要定位到 KV 传输精度或 Layout 转换，而不是接受「大致相同」。

后五条都是故障语义验证，必须用注入手段主动构造，不能等线上偶发。

### 13.2 性能验证

| 负载 | Monolithic | Disaggregated | 关注指标 |
| --- | --- | --- | --- |
| 短输入长输出 | 基线 | P/D | TPOT、D 利用率 |
| 长输入短输出 | 基线 | P/D | TTFT、Transfer |
| 混合长度 | 基线 | P/D | 隔离、Goodput |
| 突发 | 基线 | P/D | 队列、P99、拒绝 |
| Worker 故障 | 基线 | P/D | 恢复时间、重复工作 |

五种负载各自检验一个假设：短输入长输出检验 Decode 隔离收益（传输成本几乎为零，是最有利场景）；长输入短输出检验传输成本是否吃掉收益（最不利场景）；混合长度检验隔离是否真的减少了相互干扰；突发检验排队与过载保护；Worker 故障检验恢复语义。只在最有利场景上得出「解耦更好」的结论没有意义。

### 13.3 观测指标

- `prefill_queue_tokens`、`prefill_duration`；
- `kv_transfer_bytes`、`kv_transfer_duration`、`kv_transfer_failures`；
- `decode_active_sequences`、`decode_tpot`；
- `kv_bytes_in_use`、`kv_lease_expired`；
- `request_attempts`、`deadline_miss`、`cancel_propagation_ms`；
- TTFT/TPOT/E2E P50/P95/P99、Goodput 与成本/Token。

每个 Trace 应以 Request ID 串联 Gateway、P Router、P Worker、Transfer、D Router 与 D Worker。

指标设计里有三个解耦专属项：`kv_lease_expired` 反映 KV 泄漏回收是否正常工作；`request_attempts` 反映重试是否在放大负载；`cancel_propagation_ms` 反映取消是否及时释放跨池资源。这三项在单体服务里都不存在，却是解耦系统最常见的故障来源。

## 14. 结果分析

### 14.1 设计决策表

| 决策 | 候选 | 选择证据 |
| --- | --- | --- |
| P:D 比例 | 1:1、1:2、1:4 | 阶段利用率与 SLO |
| KV 路径 | Local、P2P、RDMA、Host | P95 传输与容量 |
| KV 副本 | 1、2 | 可用性与额外带宽 |
| 路由 | 最短队列、拓扑、Deadline | Goodput 与 P99 |
| 回退 | 重做 Prefill、Monolithic、拒绝 | Deadline 与成本 |

每一行的「选择证据」都必须是实测或可复算的模型输出，不能是偏好。P:D 比例一行尤其如此：第 5.3 节推导的 1:12.8 说明候选集本身可能需要扩展到 1:8、1:16，候选列表应由服务时间比推算后再确定。

KV 副本一行是可用性与带宽的直接交换：双副本让 D Worker 崩溃后可重路由，代价是传输字节翻倍、链路利用率翻倍。在链路利用率已达 0.7 的系统里，开启双副本会直接把系统推入不稳定区。

### 14.2 采用门槛

只有同时满足以下条件才建议上线：

- 相同模型质量和输出语义；
- Goodput 或成本/Token 有稳定收益；
- TTFT/TPOT P95/P99 满足目标；
- KV Transfer 不成为新瓶颈；
- 单 Worker/单链路故障可恢复；
- 运维复杂度、容量余量和回滚路径可接受。

六条是「与」关系而非「或」。实践中最常见的失败模式是前四条都满足、第五条靠重试勉强通过、第六条被忽略——上线后一次滚动发布就暴露出 P/D 版本不一致或 Drain 丢请求的问题。解耦把单体服务的内部复杂度外化成了分布式复杂度，运维门槛必须计入决策。

## 15. 常见错误与排查

### 15.1 只比较 Prefill 和 Decode Kernel

系统收益必须包含两次排队、KV 传输、路由、网络和错误重试。阶段峰值提升不等于端到端 Goodput 提升。

### 15.2 KV 字节估算使用 Query Head

应使用 KV Head。GQA/MQA 模型的 Query Head 更大，会严重高估传输。以 32 Query Head、8 KV Head 的 GQA 模型为例，用错会让传输预算虚高 4 倍，进而错误地否掉解耦方案。

### 15.3 Decode Worker 先看到未完成 KV

Handle 暴露必须晚于传输完成与校验通过。若元数据先提交，Decode 可能读到部分写入的 KV，表现为输出乱码或崩溃，且难以稳定复现。排查方式是检查 Commit 时序与校验和是否真正生效。

### 15.4 重试不带 Attempt 与 Generation

超时重试后旧 Commit 迟到，会覆盖新状态。必须用 `(request_id, attempt_id, generation)` 做条件提交，并在拒绝旧 Commit 时清理其 KV。

### 15.5 取消不传播

Client 断开后 P/D 两侧仍保留 KV，显存被无人消费的请求占满。应把取消沿 Request ID 传播到所有持有资源的节点，并用租约兜底。

### 15.6 扩缩容当成无状态服务

新 Decode 副本不会自动获得在途请求的 KV，缩容不 Drain 会中断流式输出。扩缩容策略必须与请求生命周期和 KV 归属绑定。

### 15.7 把 PCIe 结论外推到 NVLink/RDMA

互联带宽差一到两个数量级，解耦的收益符号都可能反转。报告中必须写明实测路径，并标注不可外推的范围。

### 15.8 用平均延迟判断稳定性

$\rho \ge 1$ 时平均排队时间发散，任何有限平均值都可能是采样窗口太短的假象。应先检查三个利用率，再看延迟分布，并保留 `null` 语义。

## 16. 常见追问与解答

### 16.1 解耦为什么可能让 TTFT 变差

TTFT 里新增了 KV 传输与 Decode 侧排队两项。若传输成本高或 Decode 池排队严重，即使 Prefill 更快，首 Token 也可能更晚。

### 16.2 什么负载最适合解耦

短输入长输出：KV 传输量小，Decode 占用时间长，隔离与独立扩缩收益最大。长输入短输出则相反，传输成本占比高，收益最不确定。

### 16.3 P:D 副本比怎么定

由两类服务时间之比推算。单 Prefill Worker 支撑 $1/S_p$ req/s，单 Decode Worker 支撑 $1/S_d$ req/s，平衡比例约为 $S_d : S_p$，再按目标利用率与突发余量调整。

### 16.4 为什么 KV 数据不能走控制面

KV 是数百 MiB 级，元数据是数百字节级，相差六个数量级。混走会让控制面存储成为带宽瓶颈与单点，正确做法是数据面直传、控制面只存 Handle 与状态。

### 16.5 KV Commit 为什么需要校验和与租约

校验和检测传输损坏，防止 Decode 读到错误 KV；租约保证对端崩溃或取消后显存能被回收，避免依赖不可靠的主动通知。

### 16.6 Erlang-C 在这里的适用边界

它假设泊松到达、指数服务时间、同质 Worker，且不含 Batch、抢占、长尾与故障。真实推理服务的服务时间高度依赖长度分布，因此结果只用于方案筛选与量级判断，不能当作 SLO 承诺。

### 16.7 双副本 KV 的代价是什么

传输字节与链路利用率翻倍，同时元数据与一致性管理更复杂。在链路已接近饱和时，双副本可能把系统推入不稳定区，应优先改善链路或降低输入长度。

### 16.8 解耦上线前最容易被忽略的一条门槛

运维复杂度与回滚路径。P/D 版本一致性、Drain 语义、故障恢复与容量余量都需要长期维护，缺少回退到 Monolithic 的能力时，一次发布事故就可能造成大面积不可用。

## 17. 延伸练习

1. 用规划器扫描输出 Token 数 32/128/512/2048，推算各自的 P:D 平衡比例。
2. 固定总副本数，扫描 P:D 分配，找到 Goodput 最高的组合。
3. 把链路效率从 0.70 降到 0.30，观察传输时间与稳定性边界的变化。
4. 在 CPU 上实现 KV 传输状态机，注入部分写入与重复 Commit，验证屏障语义。
5. 实现取消传播与租约回收，测量 `cancel_propagation_ms` 与显存释放延迟。
6. 用流式压测客户端对比 Monolithic 与模拟解耦路由在五种负载下的表现。
7. 给 Router 增加 Deadline-aware 拒绝逻辑，比较拒绝率与 P99。
8. 若具备真实高速互联，复测传输带宽并把结果与 PCIe 基线并列，标注不可外推范围。

## 18. 项目验收 Checklist

- 已建立 Prefill、Transfer、Decode 三阶段延迟与吞吐模型。
- 已同时检查 Prefill、Decode、链路三个利用率并给出稳定性边界。
- KV 字节使用实际 KV Head 数，且与 API 契约示例值可互相复算。
- 已推算 P:D 平衡比例，而非默认 1:1。
- 控制面与数据面分离，KV 不经过控制面存储。
- 状态机包含 `KV_COMMITTED` 屏障，部分传输永不对 Decode 可见。
- 幂等、Attempt/Generation 条件提交、超时与重试语义已写明。
- 故障矩阵覆盖崩溃、传输中断、取消、版本不一致、分区与慢 Worker。
- 扩缩容包含 Drain 与新副本 KV 归属处理。
- 观测指标包含传输、租约、重试与取消传播，并以 Request ID 串联 Trace。
- CPU 模拟与 PCIe 实测未被写成 NVLink/RDMA 结论。
- 采用门槛六条全部给出证据，包含运维与回滚路径。

## 写在最后

解耦推理的设计难点不在「把 Prefill 和 Decode 分开」这个想法，而在分开之后必须补齐的一整套分布式语义：KV 什么时候可见、重试如何幂等、取消如何传播、副本如何扩缩、故障如何回退。容量模型给出量级，状态机与故障矩阵给出正确性，两者都通过才谈得上收益。最后一个项目把前面所有方法收拢成一次完整的端到端性能工程交付。

下一篇：[AI Systems Performance Engineering 综合项目](/source/AI-Infra/2-AI系统性能工程/36-AISystemsPerformanceEngineering综合项目)。