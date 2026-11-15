# Observability 与 Reliability：Trace、Canary、Drain 与隔离

## 1. 课程定位

本文回答的问题是“如何用统一证据定位推理故障，并在发布和故障期间保护在途请求？”。分析从 Distributed Trace 与 Canary 的关系开始，随后落到计算模型、实现路径和发布验收。Observability 与 Reliability：Trace、Canary、Drain 与隔离会同时受到工作负载、模型修订、运行时调度、显存容量、并发状态与服务等级约束。正文会把相关机制还原成 Distributed Trace 等可观察实体，再据此划定收益条件与额外成本。

证据分为机制模拟和真实 CUDA 测量。前者用可控变量观察 Distributed Trace 怎样影响 Canary，后者把框架、Kernel、内存和硬件成本计入结果。两条路径使用不同来源标签，并保留 Distributed Trace 相关环境与限制；参数组合可以随版本改变，证据链仍要支持复现、定位和回退。

## 2. 学习目标

1. 准确解释 Distributed Trace、Canary 和 Graceful Drain 之间的状态与资源关系。
2. 使用“MTTR = detect + isolate + restore + verify + ramp；retry_amplification = attempts/original”建立可计算的收益边界并解释全部变量。
3. 围绕 Trace 完整率、Canary 错误率、排空完成时间和恢复目标时间设计可复现实验。
4. 识别 Trace 缺失模型或策略版本、Canary 样本不代表高风险请求和排空超时直接杀死在途请求等典型失败模式。
5. 对“如何用统一证据定位推理故障，并在发布和故障期间保护在途请求？”给出包含适用条件、证据、风险和回滚的工程答案。

## 3. 前置知识与环境

阅读 Observability 与 Reliability：Trace、Canary、Drain 与隔离需要理解自回归生成、Tokenizer、Prefill、Decode、KV Cache、批处理和分位延迟的基本含义。涉及 Distributed Trace 时，所有缩写都会在正文首次出现处定义；没有某个特定框架经验不妨碍理解机制。实验需要 Python 3.11 或兼容版本。围绕 Distributed Trace 的机制模拟只依赖 CPU；真实路径需要任意可用的 CUDA GPU、与驱动兼容的 PyTorch，以及自行准备的本地小模型或兼容制品。

验证 Distributed Trace 前必须记录 GPU 名称、数量、可用显存、驱动、CUDA、PyTorch、推理框架、模型摘要、精度、批量、序列长度和完整命令。脚本根据可用显存缩放模型、批量、上下文和样本数，并把 Distributed Trace 状态写入报告；可选 CUDA 入口不下载未经确认的大模型。

## 4. 工程问题

评估 Observability 与 Reliability：Trace、Canary、Drain 与隔离时，先不要回答“打开以后能快多少”。需要固定模型与修订、输入输出长度分布、到达过程、并发、采样、缓存状态、Trace 完整率口径、服务等级和硬件环境，再评审“定义 Trace 字段”和“设置 Canary 阶段门禁”。这些条件共同决定收益、成本和资源竞争。

分析范围由八个可观察概念组成：Distributed Trace、Canary、Graceful Drain、Failure Isolation、健康探针、重试预算、错误分类、恢复时间线。算法层的变化会经运行时和平台层传到检测时间与恢复目标时间。每个概念都像 Distributed Trace 一样绑定具体状态、责任边界、观测字段和故障表现。

## 5. 知识串讲

### 核心直觉与基础关系

### 核心直觉：先用 Trace 找到请求卡在哪一层，再用 Metrics 判断是不是系统性问题

LLM 平台跨 Gateway、Router、Replica、Model/Adapter、Streaming 和 Control Plane。单看 GPU 利用率无法解释请求级尾延迟。

### Metrics

回答：

“系统整体现在怎么样？”

例如：

- request rate；
- P50/P95/P99；
- error rate；
- queue work；
- active tokens；
- replica states；
- model load time；
- cache/adaptor hit；
- GPU cost。

### Logs

回答：

“某个组件发生了什么事件？”

例如：

```text
request abc routed to replica-7
adapter finance-v2 cache miss
model revision r42 load failed
```

### Traces

回答：

“这一个请求跨多个服务时，时间到底花在哪？”

三者不能互相替代。

### LLM Request Trace

一个 trace 可以：

```text
Trace abc  total 4.8s
├─ gateway.auth              2ms
├─ model_route               1ms
├─ replica_route             3ms
├─ adapter_load              0ms (hit)
├─ queue                     430ms
├─ inference.ttft            610ms
├─ inference.stream          3.6s
└─ usage_commit              5ms
```

如果是 Agent：

```text
root request
├─ planner
├─ search
├─ sub-llm-1
├─ sub-llm-2
└─ final
```

这样才有“用户级 critical path”。

### Span Attributes

建议：

```text
model_alias
model_revision
runtime
replica_id
gpu_type
adapter_id
speculator
slo_tier
input_token_bucket
output_token_bucket
structured_output
multimodal_type
```

注意不要把：

- 完整 prompt；
- 用户隐私；
- 超高基数的任意字符串；

直接当 metric labels。

### High Cardinality

如果把 `request_id` 放进 Prometheus label：

每个请求产生一个新 time series，监控系统很快爆炸。

原则：

- Metrics：低/中基数维度；
- Trace/Logs：request_id 等高基数；
- 用户/租户维度按规模谨慎聚合。

### Golden Signals 的 LLM 版本

可以把经典四大信号扩展：

### Traffic

requests、input/output tokens、model mix。

### Latency

Gateway、queue、TTFT、TPOT、E2E、model load。

### Errors

HTTP、Runtime、OOM、timeout、cancel、tool failure。

### Saturation

queue work、active tokens、KV/VRAM、replica occupancy、pending replicas。

### Canary Rollout

新模型/Runtime/Speculator 不应直接全量。

```text
V1 95%
V2 5%
```

比较：

- error；
- P99；
- output quality；
- acceptance/speculation；
- cost/token；
- memory；
- cold start。

Canary 的流量必须足够代表真实 workload，不能只用内部健康请求。

### Graceful Drain

LLM 流式请求可能很长。

直接终止 Replica：

```text
SIGKILL
→ 用户生成到一半断开
```

Drain：

1. 标记 `DRAINING`；
2. Router 不再发送新请求；
3. 已有请求继续；
4. 到 grace deadline 后处理剩余；
5. 停止实例。

$$T_{drain}=\min(T_{all-active-finish},GracePeriod)$$

### Failure Isolation

### Replica failure

只影响该实例，请求按幂等/重试规则处理。

### Model-specific failure

某一 revision 错误，回滚 alias，不影响其他模型。

### Tenant/Adapter failure

坏 Adapter 不应导致 Base Model 全局下线。

### Control Plane failure

已有 Data Plane 尽量继续运行。

这就是 failure domain 设计。

### Circuit Breaker

某个 backend 连续失败：

```text
fail rate > threshold
→ OPEN
→ 暂停新流量
→ fallback / fail-fast
→ half-open probe
→ recover
```

比无限重试更安全。

### SLO 与 Error Budget

例如：

$$Availability=99.9\%$$

允许错误预算：

$$ErrorBudget=0.1\%$$

如果本月已经快耗尽预算，可以：

- 暂缓高风险发布；
- 降低新 Speculator/模型流量；
- 增加容量；
- 修复热点错误。

SLO 不只是报警阈值，而是发布速度与可靠性的决策工具。

### 综合项目故障注入

至少模拟：

- replica crash；
- model load failure；
- adapter corrupted；
- router stale state；
- slow backend；
- canary regression；
- control loop restart。

检查：

- 是否只影响局部；
- 是否可回滚；
- trace 是否能定位；
- usage 是否重复；
- drain 是否中断流式请求。

### Distributed Trace

在 Observability 与 Reliability：Trace、Canary、Drain 与隔离中，Distributed Trace 的边界由输入、输出、状态和拥有者共同确定。把生命周期写清楚，才能定位请求在哪个阶段等待、计算或复制。Distributed Trace 连接 Canary 时还要传播身份和版本，避免把另一套配置的结果归到当前实验。

测量 Distributed Trace 时分别记录算力、显存、带宽、CPU 开销与同步。发生“Canary 在少量流量中验证新修订”后，缩短的阶段可能让另一项资源成为瓶颈。分析因此对齐 Distributed Trace 的阶段事件和资源轨迹，不让单个平均利用率代替因果证据。

评估 Distributed Trace 需要把负载分布写入实验：输入输出长度、并发、到达突发、采样方式和业务域都可能移动收益边界。设计排空协议至少比较低载、临近容量与过载，结论只覆盖实际运行过的区间。

Distributed Trace 进入候选路径后，输出校验继续检查 Token、采样、结构、结束原因和错误传递。共享线程池导致故障跨租户传播一旦出现，质量结果优先于速度数字；发布停止，流量回到已验证修订，相关请求留作重放。

观察 Distributed Trace 需要稳定请求身份、模型与策略修订、起止时间、阶段耗时、资源快照和失败原因。重试放大系数同时注明单位、窗口和分母。这些字段使“如何用统一证据定位推理故障，并在发布和故障期间保护在途请求？”可以在发布后按原条件回放。

### Canary

解释 Canary 时，先列出它接收什么、产生什么、由谁维护以及状态何时结束。Observability 与 Reliability：Trace、Canary、Drain 与隔离的请求可能在这些交界处增加等待、计算或复制。与 Graceful Drain 交互的字段必须携带版本身份，便于回放时找到同一配置。

围绕 Canary 建立资源模型，需要把计算量、显存占用、内存流量、主机工作和等待时间单独记账。Graceful Drain 停止新请求并保护在途工作会移动关键路径，却很少让所有资源同比例变化。请求事件负责说明顺序，资源曲线负责解释瓶颈转移。

划分隔离单元是否合适，取决于 Canary 所面对的长度分布、并发、到达过程、采样和任务域。实验在低载、接近饱和、过载三段保留同口径证据。固定长度与固定批量的结果用于解释机制，不承担完整容量结论。

Canary 带来的速度变化仍需满足模型输出合同，包括 Token 序列、采样分布、结构合法性、结束原因和错误传播。出现无限重试形成级联时，质量门禁应停止性能发布；回退目标是已验证配置，并保留问题请求用于复现。

Canary 的观测记录包含请求身份、模型版本、策略版本、阶段时间、资源状态与失败原因。故障影响范围没有单位、统计窗口和分母时不参与决策。完整记录用于复查“如何用统一证据定位推理故障，并在发布和故障期间保护在途请求？”在具体负载下是否成立。

## 写在最后

可靠性手段最终都要换算成成本与收益，才能决定发布节奏和容量余量。下一篇：[Inference Economics：Cost per Token、SLO 与全局优化](/source/AI-Infra/3-大模型推理优化工程/30-InferenceEconomics-CostperToken-SLO与全局优化)。