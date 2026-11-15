# LLM Autoscaling：Queue、Token 与 SLA-aware Planner

## 1. 课程定位

本文把 LLM Autoscaling：Queue、Token 与 SLA-aware Planner 放回真实请求链路中讨论，中心问题为“什么信号能让扩缩容既及时响应突发流量，又避免冷启动振荡？”。LLM Autoscaling 和 Queue Signal 提供分析入口，计算模型负责说明方向，实验和发布门禁负责限定结论。评审时需要同时查看模型版本、负载、调度、显存、并发与服务等级，避免把 LLM Autoscaling 的局部理想收益直接当成端到端结果。

本文先用 CPU 模拟控制 LLM Autoscaling 和 Queue Signal，再用真实 CUDA 路径检查这些关系进入实现后增加了哪些成本。每份结果都要标明数据来源、运行环境和适用边界。这样得到的是可复查的工程判断，而非依赖某个框架版本的参数口诀。

## 2. 学习目标

1. 准确解释 LLM Autoscaling、Queue Signal 和 Token Work 之间的状态与资源关系。
2. 使用“desired = ceil((queued_work + forecast_work)/(service_rate*target_window)) - ready - pending”建立可计算的收益边界并解释全部变量。
3. 围绕队列 Token、预计等待时间、扩容次数和空闲成本设计可复现实验。
4. 识别按 GPU 利用率反应过晚、忽略待启动副本重复扩容和短突发触发昂贵冷启动等典型失败模式。
5. 对“什么信号能让扩缩容既及时响应突发流量，又避免冷启动振荡？”给出包含适用条件、证据、风险和回滚的工程答案。

## 3. 前置知识与环境

阅读 LLM Autoscaling：Queue、Token 与 SLA-aware Planner 需要理解自回归生成、Tokenizer、Prefill、Decode、KV Cache、批处理和分位延迟的基本含义。涉及 LLM Autoscaling 时，所有缩写都会在正文首次出现处定义；没有某个特定框架经验不妨碍理解机制。实验需要 Python 3.11 或兼容版本。围绕 LLM Autoscaling 的机制模拟只依赖 CPU；真实路径需要任意可用的 CUDA GPU、与驱动兼容的 PyTorch，以及自行准备的本地小模型或兼容制品。

验证 LLM Autoscaling 前必须记录 GPU 名称、数量、可用显存、驱动、CUDA、PyTorch、推理框架、模型摘要、精度、批量、序列长度和完整命令。脚本根据可用显存缩放模型、批量、上下文和样本数，并把 LLM Autoscaling 状态写入报告；可选 CUDA 入口不下载未经确认的大模型。

## 4. 工程问题

关于 LLM Autoscaling：Queue、Token 与 SLA-aware Planner 的性能问题，要从测量条件开始。模型与修订、输入输出分布、请求到达、并发、采样、缓存、队列 Token 统计方式、服务等级和硬件均需保持可追溯。“选择扩缩信号”和“估计 Token 服务率”只有在同一证据口径下才可比较。

决策所需的八个观察对象为：LLM Autoscaling、Queue Signal、Token Work、SLA-aware Planner、Pending Capacity、冷启动延迟、迟滞、Scale-to-Zero。它们横跨算法、运行时和平台，共同作用于过载拒绝率与空闲成本。以 LLM Autoscaling 为例，每个对象都要标出拥有者、状态、计量点和失败边界，局部变化才能与端到端结果对上。

## 5. 知识串讲

### 核心直觉与基础关系

### 核心直觉：Scale-out 决策发生在现在，新增容量却在未来到达

LLM Replica 可能有几十秒级甚至更长的启动关键路径，因此 Autoscaler 必须同时估计当前 backlog、未来到达和 pending capacity。

```text
Traffic
  ↓
Metrics
  ↓
Planner
  ↓
Target Replicas
  ↓
Control Plane
  ↓
Ready Replicas
  └────→ Metrics
```

问题：这个环不是即时的。

如果：

$$T_{startup}=60s$$

Planner 看到过载后才扩容，未来 60 秒仍没有新容量。

### Replica Capacity 不是固定 QPS

同一 Replica：

```text
短输入短输出 → 20 req/s
长 reasoning → 2 req/s
```

所以容量更适合写成 workload-conditioned：

$$\mu=f(ISL,OSL,Concurrency,CacheHit,Speculation,Hardware)$$

需要通过 profile 得到服务曲线。

### Queue Work

不只看 Waiting Request Count，而估计：

$$W_q=\sum_{r\in queue}EstimatedWork(r)$$

例如：

$$EstimatedWork=\alpha InputTokens+\beta ExpectedOutputTokens$$

Reasoning/Agent 可以再加入 workload weight。

目标让：

$$\frac{W_q}{Capacity_{ready}}<Target$$

### SLA-aware Scaling

如果目标 TTFT P99 < 1s，Planner 可以使用：

$$QueueDelay+ServiceTime\le SLO$$

反推需要的 Replica 数：

$$N\ge \frac{PredictedWork}{CapacityPerReplica\cdot Window}$$

并加 Headroom：

$$N_{target}=\lceil N(1+h)\rceil$$

### Pending Capacity

假设目标 10 个 Replica：

```text
Ready 6
Loading 3
Pending 1
```

不能把 10 都当作当前 capacity。

但也不能忽略 Loading，否则 Planner 每轮都继续创建，最终 overshoot。

需要分别建模：

$$C_{effective}=C_{ready}+\gamma C_{loading}$$

其中 $0\le\gamma<1$ 反映预计多久 Ready。

更完整做法按 ETA 进入预测。

### Reactive vs Predictive

### Reactive

看到 queue/latency 上升再扩。

适合随机小波动。

### Predictive

根据：

- 历史周期；
- 已知活动；
- arrival trend；
- workload mix；

提前扩容。

对于 cold start 很长的模型，predictive 更重要。

### Hysteresis 与 Cooldown

如果阈值：

```text
load>70% scale out
load<70% scale in
```

会在边界抖动。

使用：

```text
>75% 持续3个窗口 → out
<40% 持续10个窗口 → in
```

这叫 hysteresis。

Scale-in 通常更保守，因为：

- Drain 需要时间；
- 误缩容会触发新的 Cold Start；
- 长请求仍在运行。

### SLO 与 Cost 双目标

最大化 Ready Replica 可以轻松降低 queue，但成本高。

目标：

$$\min N_{GPU}\cdot C_{gpu}$$

subject to：

$$P99(TTFT),P99(TPOT)\le SLO$$

这与后续 Inference Economics 一篇直接连接。

### 放置算法实验（第三部分）

在 Placement/Bin Packing 模拟器上加入时间序列流量：

```text
00-10min: low
10-20min: burst
20-40min: stable high
40-60min: low
```

比较：

- CPU-like fixed threshold；
- queue-count；
- token-work；
- predictive + cold-start ETA。

指标：

- SLO misses；
- replica hours；
- scaling actions；
- overshoot；
- cold miss。

### LLM Autoscaling

LLM Autoscaling 在 LLM Autoscaling：Queue、Token 与 SLA-aware Planner 中的生命周期需要落到组件接口：输入从哪里来，状态由谁持有，输出交给谁，失败如何传播。它与 Queue Signal 之间的身份和版本若未绑定，请求时间线就可能混入旧配置。

Queue Token 更接近待处理计算量对 LLM Autoscaling 的影响会分散到计算、显存、内存带宽、主机处理和同步等待。某一阶段变短时，被遮蔽的成本可能随即暴露。为确认 LLM Autoscaling 的变化来自哪里，本文对齐请求时间线与资源采样，而非只看整段运行的 GPU 平均值。

LLM Autoscaling 的边际价值会随输入长度、输出长度、并发、流量突发、采样和任务域变化。验证预测容量到达时分别运行低载、接近饱和与过载区间，并使用代表性分布。单一长度、批量或短窗口只能说明该测试点。

正确性门禁覆盖 LLM Autoscaling 影响到的 Token、采样、结构、结束状态与错误。若检测到缩容删除仍有会话的副本，当前性能结果不进入候选评审，并立即切回已验证配置。失败样本与版本信息要一并保存。

为 LLM Autoscaling 建立证据链时，统一保存请求 ID、模型及策略修订、关键时间点、资源快照和错误。振荡次数的定义随报告存档，包括单位、窗口和分母。这样才能按同一条件重放“什么信号能让扩缩容既及时响应突发流量，又避免冷启动振荡？”。

### Queue Signal

对 Queue Signal 做边界检查，要覆盖输入、输出、状态归属和销毁时点。LLM Autoscaling：Queue、Token 与 SLA-aware Planner 的等待、计算及复制都能沿这些节点定位。Queue Signal 传给 Token Work 的数据还应附带模型或策略版本，使测量结果可以对应到唯一配置。

Queue Signal 的资源账要拆成计算、显存、内存带宽、主机开销和同步等待。扩容动作经过冷启动后才形成可路由容量通常只先改变其中几项，其他资源随后可能进入关键路径。Queue Signal 的请求时间线和资源曲线可以呈现这种转移，平均 GPU 利用率只作为辅助信号。

工作负载一变，Queue Signal 对系统的贡献也会变化。设置上下阈值与迟滞应覆盖长短输入、不同输出、并发、突发、采样与任务域，并保留低载、稳定高载和过载记录。容量判断不能从一次固定批量的短运行外推。

对 Queue Signal 的优化只有在输出合同不变时才有效。Token 序列、采样分布、结构合法性、结束原因和错误传播均需对账。尺度变化导致路由器状态过期会触发停止与回退，系统恢复到已有证据支持的配置。

Queue Signal 相关事件要能关联到稳定请求身份、模型与策略版本、开始结束时间、阶段耗时、资源采样和失败原因。冷启动请求 P99 必须附带口径。缺少这些信息时，关于“什么信号能让扩缩容既及时响应突发流量，又避免冷启动振荡？”的判断无法在上线后复核。

### Token Work

在 LLM Autoscaling：Queue、Token 与 SLA-aware Planner 中，Token Work 的边界由输入、输出、状态和拥有者共同确定。把生命周期写清楚，才能定位请求在哪个阶段等待、计算或复制。Token Work 连接 SLA-aware Planner 时还要传播身份和版本，避免把另一套配置的结果归到当前实验。

测量 Token Work 时分别记录算力、显存、带宽、CPU 开销与同步。发生“Planner 需要把待启动容量计入预测”后，缩短的阶段可能让另一项资源成为瓶颈。分析因此对齐 Token Work 的阶段事件和资源轨迹，不让单个平均利用率代替因果证据。

评估 Token Work 需要把负载分布写入实验：输入输出长度、并发、到达突发、采样方式和业务域都可能移动收益边界。控制 Scale-to-Zero 至少比较低载、临近容量与过载，结论只覆盖实际运行过的区间。

Token Work 进入候选路径后，输出校验继续检查 Token、采样、结构、结束原因和错误传递。Scale-to-Zero 违反交互 SLO 一旦出现，质量结果优先于速度数字；发布停止，流量回到已验证修订，相关请求留作重放。

观察 Token Work 需要稳定请求身份、模型与策略修订、起止时间、阶段耗时、资源快照和失败原因。过载拒绝率同时注明单位、窗口和分母。这些字段使“什么信号能让扩缩容既及时响应突发流量，又避免冷启动振荡？”可以在发布后按原条件回放。

### SLA-aware Planner

解释 SLA-aware Planner 时，先列出它接收什么、产生什么、由谁维护以及状态何时结束。LLM Autoscaling：Queue、Token 与 SLA-aware Planner 的请求可能在这些交界处增加等待、计算或复制。与 Pending Capacity 交互的字段必须携带版本身份，便于回放时找到同一配置。

围绕 SLA-aware Planner 建立资源模型，需要把计算量、显存占用、内存流量、主机工作和等待时间单独记账。迟滞和冷却避免扩缩振荡会移动关键路径，却很少让所有资源同比例变化。请求事件负责说明顺序，资源曲线负责解释瓶颈转移。

保留 Headroom 是否合适，取决于 SLA-aware Planner 所面对的长度分布、并发、到达过程、采样和任务域。实验在低载、接近饱和、过载三段保留同口径证据。固定长度与固定批量的结果用于解释机制，不承担完整容量结论。

SLA-aware Planner 带来的速度变化仍需满足模型输出合同，包括 Token 序列、采样分布、结构合法性、结束原因和错误传播。出现按 GPU 利用率反应过晚时，质量门禁应停止性能发布；回退目标是已验证配置，并保留问题请求用于复现。

SLA-aware Planner 的观测记录包含请求身份、模型版本、策略版本、阶段时间、资源状态与失败原因。空闲成本没有单位、统计窗口和分母时不参与决策。完整记录用于复查“什么信号能让扩缩容既及时响应突发流量，又避免冷启动振荡？”在具体负载下是否成立。

### Pending Capacity

Pending Capacity 在 LLM Autoscaling：Queue、Token 与 SLA-aware Planner 中的生命周期需要落到组件接口：输入从哪里来，状态由谁持有，输出交给谁，失败如何传播。它与冷启动延迟之间的身份和版本若未绑定，请求时间线就可能混入旧配置。

## 写在最后

扩缩容解决的是分钟级的容量跟随，而采购与配额需要提前数周决定 Fleet 规模。下一篇：[Capacity Planning：流量预测、Headroom 与 GPU Fleet](/source/AI-Infra/3-大模型推理优化工程/28-CapacityPlanning-流量预测-Headroom与GPUFleet)。