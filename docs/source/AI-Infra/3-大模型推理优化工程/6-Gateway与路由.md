# 入口与路由：Gateway、副本选择与 KV 局部性

入口决定了「谁能进来、算多少账」，路由决定了「去哪里排队」。这两层做错，后面的引擎优化基本白费。

## 1. 三层职责必须分开

```text
/v1/chat/completions  model="reasoning-pro"
        │
        ├─ Gateway / API Routing：映射到哪个逻辑服务
        ├─ Model Routing：alias → 版本（v3 90% / v4 10%，Canary、fallback）
        └─ Replica Routing：落到哪个实例（A/B/C）
```

三层的输入、状态与失败语义完全不同。全塞进一个 Router，后续既难演化也难定位「延迟来自策略还是实现」。

## 2. OpenAI 兼容协议的价值

兼容不是为了模仿某个产品，而是建立**稳定的调用契约**：`model`、`messages/input`、采样参数、`tools`、structured output、`stream`、`usage`、`error`。

底层可以随时替换：vLLM、SGLang、TensorRT-LLM、Ray Serve、KServe、自研 Runtime——客户端不需要同时学多套协议。

代价是：一旦对外承诺了字段语义，就不能在实现里悄悄改（例如 `usage` 的统计口径、错误的 HTTP 状态映射）。

## 3. Request Identity：一份 ID 贯穿全链路

```text
request_id / trace_id / tenant_id / user_id(optional)
model_alias / model_revision / adapter_id(optional)
slo_tier / budget
```

后面所有日志、指标、usage 都用同一套 ID。否则用户投诉「慢 / 错 / 贵」时，你无法在 Gateway、Router、Replica 之间拼出完整证据。

**没有身份，就没有归因。**

## 4. 计量、配额与准入

三件事要分开：

| 机制 | 作用点 | 典型做法 |
|---|---|---|
| 计量（metering） | 事后 | 按输入/输出 token、按 adapter、按租户落账 |
| 配额（quota） | 事前 | token/分钟、请求/分钟、并发上限 |
| 准入（admission） | 入队前 | 队列水位、SLO 档位、优先级、拒绝或排队 |

要点：配额要按**token**而不仅是请求数（一个 20K 输入的请求与一个 300 token 的请求不是一个量级）；拒绝要有明确错误码与 `Retry-After`，否则客户端重试会放大成重试风暴。

## 5. 副本路由：从轮询到预计完成时间

### 5.1 轮询为什么失效

```text
Req1: 100 in / 100 out     Req2: 20K in / 4K out     Req3: 300 in / 80 out
RR →  A: short+short   B: 巨长任务   C: short
```

B 会被长期积压，而后续请求仍机械轮转。**LLM 请求的成本方差太大，均分等于制造热点。**

### 5.2 Power-of-Two Choices

每次随机挑两个副本，选更轻的那个。好处是状态读取少、算法简单、显著降低随机热点；缺点是「更轻」取决于你怎么定义负载。

### 5.3 队列长度也不够

```text
A：队列 2 个，每个预计输出 10K token
B：队列 5 个，每个预计输出 100 token
```

按请求数看 A 更空，按剩余工作量看 A 更忙。所以要用：

$$
Work_i = \sum_{r \in i} Cost(r),\qquad
Cost(r) = \alpha I_r + \beta \hat{O}_r
$$

输出长度未知时，可用 `max_tokens`、历史同类请求、模型/域预测器或在线剩余长度估计。

### 5.4 预计完成时间（ECT）

```text
ECT_i = Now + QueueWork_i + ServiceTime(request, i)
i* = argmin_i ECT_i
```

在异构 GPU 上，\(ServiceTime\) 必须与 GPU 型号、模型并行度、当前 batch 状态相关——同一请求在不同卡上不是一个常数。

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l18_01.png" width="78%" alt="KV locality routing" />
  <p>图 1：前缀、会话、Adapter 与模型的局部性都会影响「该去哪台」</p>
</div>

## 6. 四类局部性

| 类型 | 场景 | 收益 |
|---|---|---|
| Prefix locality | 长 system prompt / 长文档 | 省 Prefill |
| Session locality | 多轮对话 | 复用会话状态 |
| Adapter locality | LoRA 已加载在某副本 | 免动态加载 |
| Model locality | 冷门模型只驻留某些副本 | 免冷启动 |

### 6.1 局部性与负载的冲突

```text
Replica A：prefix 命中省 300ms，但队列预计 500ms
Replica B：无 prefix，队列 20ms，Prefill 200ms
```

A 不是最优。所以不能只看命中率，要算总成本：

$$
Score_i = QueueCost_i + MissCost_i + LoadCost_i,\qquad
MissCost_i = \mathrm{PrefillTime}(\text{UncachedTokens}_i)
$$

$$
i^\ast = \arg\min_i Score_i
$$

**局部性只是一项成本，不应凌驾于所有负载信息之上。** 命中率本身不是收益，省下的计算时间才是。

### 6.2 不要做「永久粘滞」

「同一 Session 永远固定一个 Replica」实现简单，但有四个问题：副本宕机无法迁移；长会话把实例绑死；热门租户造成热点；缓存早已被驱逐，Router 却还以为有局部性。

更合理的是 soft affinity：

```text
命中优先，但负载差距超过阈值时允许迁移
```

### 6.3 Locality 元数据的规模问题

Router 侧可能要维护 `replica_id / model_ids / adapter_ids / prefix_fingerprints / session_handles / last_update / capacity`。但 prefix 数量可能巨大，不能把全部 cache key 同步到所有 Router。

常见压缩手段：Bloom filter、prefix summary、事件流推送、热 key 抽样、层次化 Router（先选集群再选副本）。

## 7. 路由的兜底

1. **Headroom**：任何路由策略都要留出余量，否则「最优打分」会把某个副本压到饱和；
2. **Overflow**：目标副本超阈值时允许溢出到次优副本（宁愿丢缓存，也不排长队）；
3. **熔断**：错误率或 P99 超阈值时摘除副本，而不是继续往里送；
4. **可解释**：每次路由决策要能输出「候选、打分、最终选择」，否则线上无法复盘。

## 写在最后

入口与路由的核心是三件事：身份、计量、成本化的选择。**不要用请求数当负载，也不要用命中率当收益。**

下一篇继续在「复用」这条线上走：Multi-LoRA 的 Adapter 缓存与热切换、多模型的冷热分层与稀疏流量，以及模型生命周期与权重分发、冷启动。
