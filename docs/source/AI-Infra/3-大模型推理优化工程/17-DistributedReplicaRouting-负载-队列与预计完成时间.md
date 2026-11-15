# Distributed Replica Routing：负载、队列与预计完成时间

## 1. 课程定位

本文回答的问题是“路由器应根据什么实时信号选择副本，才能同时保护 TTFT 与吞吐？”。分析从 Replica Set 与 Power-of-Two Choices 的关系开始，随后落到计算模型、实现路径和发布验收。Distributed Replica Routing：负载、队列与预计完成时间会同时受到工作负载、模型修订、运行时调度、显存容量、并发状态与服务等级约束。正文会把相关机制还原成 Replica Set 等可观察实体，再据此划定收益条件与额外成本。

证据分为机制模拟和真实 CUDA 测量。前者用可控变量观察 Replica Set 怎样影响 Power-of-Two Choices，后者把框架、Kernel、内存和硬件成本计入结果。两条路径使用不同来源标签，并保留 Replica Set 相关环境与限制；参数组合可以随版本改变，证据链仍要支持复现、定位和回退。

## 2. 学习目标

1. 准确解释 Replica Set、Power-of-Two Choices 和 Least-Work 之间的状态与资源关系。
2. 使用“score_i = estimated_queue_work_i / service_rate_i + request_work/service_rate_i + staleness_penalty”建立可计算的收益边界并解释全部变量。
3. 围绕路由决策延迟、负载年龄、预计与实际完成误差和 Goodput 设计可复现实验。
4. 识别最少请求数误判长请求副本、负载上报过慢形成热点和所有路由器同时选择新空闲副本等典型失败模式。
5. 对“路由器应根据什么实时信号选择副本，才能同时保护 TTFT 与吞吐？”给出包含适用条件、证据、风险和回滚的工程答案。

## 3. 前置知识与环境

阅读 Distributed Replica Routing：负载、队列与预计完成时间需要理解自回归生成、Tokenizer、Prefill、Decode、KV Cache、批处理和分位延迟的基本含义。涉及 Replica Set 时，所有缩写都会在正文首次出现处定义；没有某个特定框架经验不妨碍理解机制。实验需要 Python 3.11 或兼容版本。围绕 Replica Set 的机制模拟只依赖 CPU；真实路径需要任意可用的 CUDA GPU、与驱动兼容的 PyTorch，以及自行准备的本地小模型或兼容制品。

验证 Replica Set 前必须记录 GPU 名称、数量、可用显存、驱动、CUDA、PyTorch、推理框架、模型摘要、精度、批量、序列长度和完整命令。脚本根据可用显存缩放模型、批量、上下文和样本数，并把 Replica Set 状态写入报告；可选 CUDA 入口不下载未经确认的大模型。

## 4. 工程问题

评估 Distributed Replica Routing：负载、队列与预计完成时间时，先不要回答“打开以后能快多少”。需要固定模型与修订、输入输出长度分布、到达过程、并发、采样、缓存状态、路由决策延迟口径、服务等级和硬件环境，再评审“选择路由评分”和“定义负载上报字段”。这些条件共同决定收益、成本和资源竞争。

分析范围由八个可观察概念组成：Replica Set、Power-of-Two Choices、Least-Work、预计完成时间、负载新鲜度、排队 Token、服务时间估计、路由迟滞。算法层的变化会经运行时和平台层传到重路由率与 Goodput。每个概念都像 Replica Set 一样绑定具体状态、责任边界、观测字段和故障表现。

## 5. 知识串讲

### 核心直觉与基础关系

### 核心直觉：LLM Replica 的“忙”不是连接数，而是剩余工作量

两个连接数相同的 Replica，可能分别承载短回答与超长 Reasoning 请求，因此完成时间完全不同。跨 Replica 路由要尽量估计 work，而不是机械轮询。

Round Robin 假设请求成本相近：

```text
Req1 → A
Req2 → B
Req3 → C
Req4 → A
```

但 LLM 请求可能是：

```text
Req1: 100 in / 100 out
Req2: 20K in / 4K out
Req3: 300 in / 80 out
```

结果可能：

```text
A: short + short
B: huge long task
C: short
```

后续仍机械分配，会让 B 长时间积压。

### Power-of-Two Choices

P2C 每次随机选两个 Replica，比较负载后选更轻的一个：

```text
候选 A load=8
候选 C load=3
→ 选 C
```

相比每次扫描全体 Replica，它：

- 状态读取少；
- 算法简单；
- 能显著降低随机分配的热点概率；
- 适合 Replica 数量很大时做近似负载均衡。

但关键仍是：**load 怎么定义？**

### Least Queue 为什么也不够

A：队列 2 个，每个输出预计 10K token。

B：队列 5 个，每个预计 100 token。

只看 request count：

```text
A更空
```

实际剩余工作量可能 A 更大。

因此定义：

$$Work_i=\sum_{r\in i}Cost(r)$$

最简单 token proxy：

$$Cost(r)=\alpha I_r+\beta \hat O_r$$

$I_r$ 是 input tokens，$\hat O_r$ 是预计 output tokens。

输出长度未知，可以用：

- 用户 max_tokens；
- 历史同类请求；
- model/domain predictor；
- 在线剩余长度估计。

### Predicted Completion Time

更进一步，Router 不只比较队列，而预测：

$$ECT_i=Now+QueueWork_i+ServiceTime(request,i)$$

选择：

$$i^*=\arg\min_i ECT_i$$

如果 GPU 异构：

$ServiceTime(request,i)$

必须与 GPU 类型、模型并行度和当前 batch 状态相关。

### State Freshness

Router 需要 Replica load：

- queue depth；
- active tokens；
- recent throughput；
- memory pressure；
- model/adapter residency。

但状态更新太频繁会产生控制流量和锁竞争；太慢又会用过期信息。

设更新周期 $\Delta t$：

$$Error_{state}\uparrow \text{ as } \Delta t\uparrow$$

$$Overhead_{control}\uparrow \text{ as } \Delta t\downarrow$$

要找到系统可接受点。

### Push vs Pull

### Push

Replica 定期上报状态。

优点：Router 查询快。

缺点：很多 Replica 时更新流量大。

### Pull

Router 需要时查询。

优点：少无效更新。

缺点：请求热路径可能增加 RPC latency。

常见折中：Push coarse state + local prediction。

### Router 自己也要避免成为单点瓶颈

如果 Router 每请求：

1. 读取集中数据库；
2. 查询 1000 个 Replica；
3. 排序；
4. 再做远程事务；

那么模型再快也没意义。

路由热路径应尽量：

- 内存态；
- 近似；
- O(1)/O(logN)；
- 无强一致全局锁；
- 支持水平扩展。

### Replica Set

在 Distributed Replica Routing：负载、队列与预计完成时间中，Replica Set 的边界由输入、输出、状态和拥有者共同确定。把生命周期写清楚，才能定位请求在哪个阶段等待、计算或复制。Replica Set 连接 Power-of-Two Choices 时还要传播身份和版本，避免把另一套配置的结果归到当前实验。

测量 Replica Set 时分别记录算力、显存、带宽、CPU 开销与同步。发生“Least-Work 用剩余工作而非请求数衡量负载”后，缩短的阶段可能让另一项资源成为瓶颈。分析因此对齐 Replica Set 的阶段事件和资源轨迹，不让单个平均利用率代替因果证据。

评估 Replica Set 需要把负载分布写入实验：输入输出长度、并发、到达突发、采样方式和业务域都可能移动收益边界。设置状态过期惩罚至少比较低载、临近容量与过载，结论只覆盖实际运行过的区间。

Replica Set 进入候选路径后，输出校验继续检查 Token、采样、结构、结束原因和错误传递。模型速度差异未进入估计一旦出现，质量结果优先于速度数字；发布停止，流量回到已验证修订，相关请求留作重放。

观察 Replica Set 需要稳定请求身份、模型与策略修订、起止时间、阶段耗时、资源快照和失败原因。TTFT P99 同时注明单位、窗口和分母。这些字段使“路由器应根据什么实时信号选择副本，才能同时保护 TTFT 与吞吐？”可以在发布后按原条件回放。

### Power-of-Two Choices

解释 Power-of-Two Choices 时，先列出它接收什么、产生什么、由谁维护以及状态何时结束。Distributed Replica Routing：负载、队列与预计完成时间的请求可能在这些交界处增加等待、计算或复制。与 Least-Work 交互的字段必须携带版本身份，便于回放时找到同一配置。

围绕 Power-of-Two Choices 建立资源模型，需要把计算量、显存占用、内存流量、主机工作和等待时间单独记账。预计完成时间结合排队与服务速度会移动关键路径，却很少让所有资源同比例变化。请求事件负责说明顺序，资源曲线负责解释瓶颈转移。

估计 Prefill 与 Decode 工作是否合适，取决于 Power-of-Two Choices 所面对的长度分布、并发、到达过程、采样和任务域。实验在低载、接近饱和、过载三段保留同口径证据。固定长度与固定批量的结果用于解释机制，不承担完整容量结论。

Power-of-Two Choices 带来的速度变化仍需满足模型输出合同，包括 Token 序列、采样分布、结构合法性、结束原因和错误传播。出现排空副本继续接收新请求时，质量门禁应停止性能发布；回退目标是已验证配置，并保留问题请求用于复现。

Power-of-Two Choices 的观测记录包含请求身份、模型版本、策略版本、阶段时间、资源状态与失败原因。副本负载离散度没有单位、统计窗口和分母时不参与决策。完整记录用于复查“路由器应根据什么实时信号选择副本，才能同时保护 TTFT 与吞吐？”在具体负载下是否成立。

### Least-Work

Least-Work 在 Distributed Replica Routing：负载、队列与预计完成时间中的生命周期需要落到组件接口：输入从哪里来，状态由谁持有，输出交给谁，失败如何传播。它与预计完成时间之间的身份和版本若未绑定，请求时间线就可能混入旧配置。

遥测延迟会让路由器使用过期状态对 Least-Work 的影响会分散到计算、显存、内存带宽、主机处理和同步等待。某一阶段变短时，被遮蔽的成本可能随即暴露。为确认 Least-Work 的变化来自哪里，本文对齐请求时间线与资源采样，而非只看整段运行的 GPU 平均值。

Least-Work 的边际价值会随输入长度、输出长度、并发、流量突发、采样和任务域变化。验证引入随机化和迟滞时分别运行低载、接近饱和与过载区间，并使用代表性分布。单一长度、批量或短窗口只能说明该测试点。

正确性门禁覆盖 Least-Work 影响到的 Token、采样、结构、结束状态与错误。若检测到客户端重试扭曲负载，当前性能结果不进入候选评审，并立即切回已验证配置。失败样本与版本信息要一并保存。

## 写在最后

路由评分只是入口，真正决定命中率的是请求与副本之间的状态局部性。下一篇：[Prefix、Session 与 KV-Locality Routing](/source/AI-Infra/3-大模型推理优化工程/18-Prefix-Session与KV-LocalityRouting)。