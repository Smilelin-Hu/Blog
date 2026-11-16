# Capacity Planning：流量预测、Headroom 与 GPU Fleet

## 1. 课程定位

理解 Capacity Planning：流量预测、Headroom 与 GPU Fleet，需要先回答“如何从工作负载分布、性能曲线和 SLO 推导长期容量与安全余量？”。本文沿着概念边界、性能关系、实现证据和发布条件四条线展开，其中 Capacity Planning 与流量预测是最先核对的状态。工作负载、模型修订、运行时、资源余量和服务承诺共同决定容量由工作负载分布和单副本性能曲线共同推导是否值得采用，后续每个结论都会注明这些条件。

实验采用两条证据路径。CPU 机制模拟隔离 Capacity Planning 与流量预测的因果关系；真实 CUDA 路径记录实现、框架和硬件开销。报告分别标记两类结果，预测误差的模拟值不充当 GPU 基准，单台设备的绝对速度也不外推。最终结论必须能够复现、诊断并回滚。

## 2. 学习目标

1. 准确解释 Capacity Planning、流量预测和性能曲线之间的状态与资源关系。
2. 使用“required_capacity = demand_quantile/service_capacity * (1 + headroom) + failure_reserve”建立可计算的收益边界并解释全部变量。
3. 围绕预测误差、峰均比、稳定单副本容量和单位有效容量成本设计可复现实验。
4. 识别用峰值吞吐直接除平均 QPS、忽略输入输出长度变化和 Headroom 被临时任务长期占用等典型失败模式。
5. 对“如何从工作负载分布、性能曲线和 SLO 推导长期容量与安全余量？”给出包含适用条件、证据、风险和回滚的工程答案。

## 3. 前置知识与环境

阅读 Capacity Planning：流量预测、Headroom 与 GPU Fleet 需要理解自回归生成、Tokenizer、Prefill、Decode、KV Cache、批处理和分位延迟的基本含义。涉及 Capacity Planning 时，所有缩写都会在正文首次出现处定义；没有某个特定框架经验不妨碍理解机制。实验需要 Python 3.11 或兼容版本。围绕 Capacity Planning 的机制模拟只依赖 CPU；真实路径需要任意可用的 CUDA GPU、与驱动兼容的 PyTorch，以及自行准备的本地小模型或兼容制品。

验证 Capacity Planning 前必须记录 GPU 名称、数量、可用显存、驱动、CUDA、PyTorch、推理框架、模型摘要、精度、批量、序列长度和完整命令。脚本根据可用显存缩放模型、批量、上下文和样本数，并把 Capacity Planning 状态写入报告；可选 CUDA 入口不下载未经确认的大模型。

## 4. 工程问题

决定是否采用 Capacity Planning：流量预测、Headroom 与 GPU Fleet 前，先冻结模型版本、长度分布、流量到达、并发、采样、缓存状态、预测误差、服务等级和硬件配置。评审“选择预测粒度”和“建立基准曲线”时，由这些记录解释收益分子、成本分母及共享资源竞争。

本文跟踪八个概念：Capacity Planning、流量预测、性能曲线、Headroom、故障容量、GPU Fleet、季节性、采购提前期。虽然它们分属不同系统层级，GPU 利用区间和单位有效容量成本会同时受到这些状态影响。后文从 Capacity Planning 开始，逐项说明谁维护状态、在哪里计量、什么情况下失效，以及结果怎样传到请求端。

## 5. 知识串讲

### 核心直觉与基础关系

### 核心直觉：容量规划是在不确定 Workload 下购买“满足 SLO 的余量”

平均 QPS 只是一个维度。真正的 GPU 需求取决于输入/输出长度、模型 mix、Reasoning 比例、故障储备和发布期间的双版本容量。

至少预测：

```text
request rate over time
input length distribution
output length distribution
model mix
tenant mix
reasoning tier
multimodal ratio
region
```

不能只预测总 request QPS。

比如 QPS 不变，但 Reasoning 占比从 10%涨到 50%，GPU 需求可能大幅上升。

### 第二步：Service Profile

对模型 $m$、硬件 $g$、工作负载 bucket $w$，得到：

$Capacity(m,g,w,SLO)$

例如：

```text
short-chat
long-chat
reasoning
structured
multimodal
```

分别 profile。

只用一个平均 workload 会掩盖 P99 最危险场景。

### 第三步：把需求转换成 Replica

时间窗口 $t$ 的总 work：

$$W_t=\sum_w \lambda_{t,w}\cdot Work_w$$

单 Replica 能力：

$C_{m,g}$

基础需求：

$$N_{base}=\left\lceil\frac{W_t}{C_{m,g}}\right\rceil$$

再加 Headroom：

$$N_{plan}=\lceil N_{base}(1+h)\rceil$$

### Headroom 从哪里来

Headroom 不是随手写 20%。

来源：

- Forecast error；
- Traffic burst；
- Replica failure；
- Node maintenance；
- Model upgrade overlap；
- Cold Start delay；
- workload mix drift。

可以拆成：

$$h=h_{forecast}+h_{failure}+h_{deployment}+h_{burst}$$

实际不一定简单相加，但这个分解有助于说明为什么保留容量。

### N+1 / Zone Failure Reserve

如果服务不能因单节点故障失去 SLO：

```text
正常需要 8 replicas
任意1 replica故障仍要满足
→ 至少需要9或更高
```

跨 Zone 服务还要考虑：

一个 Zone 整体不可用时，剩余 Zone 是否能承载关键流量？

这会显著增加 reserve cost。

### Committed 与 Burst Capacity

### Committed/Baseline

长期常驻，价格稳定，承担平均负载。

### Burst

用于峰值：

- 临时 GPU；
- 云按需；
- 低优先级任务让路；
- fallback model。

理想结构：

```text
Baseline Capacity
       +
Elastic Burst Capacity
```

而不是永远按历史最大峰值部署全部 GPU。

### Scenario Planning

至少做：

### Scenario A：平均日

正常模型 mix。

### B：业务活动峰值

QPS ×3。

### C：Reasoning 占比翻倍

token work 增长。

### D：一个 Region/GPU Pool 故障

剩余容量验证。

### E：模型升级双版本同时运行

Canary/rolling 导致短期资源翻倍。

最终选择能覆盖风险容忍度的 Fleet。

### 容量不是越多越安全

过度 Headroom：

$$IdleGPUHours\uparrow$$

Cost/token 上升。

因此 Capacity Planning 的目标仍然是：

$$\min TotalCost$$

subject to：

$$P(SLO\ violation)\le \epsilon$$

### Fleet Planner 实验前置数据

Fleet Planner 实验会使用：

- forecast workload；
- per-GPU capacity profile；
- GPU hourly cost；
- SLO penalty；
- failure scenarios。

枚举不同 Fleet 组合，找到成本与 SLO 的 Pareto frontier。

### Capacity Planning

对 Capacity Planning 做边界检查，要覆盖输入、输出、状态归属和销毁时点。Capacity Planning：流量预测、Headroom 与 GPU Fleet 的等待、计算及复制都能沿这些节点定位。Capacity Planning 传给流量预测的数据还应附带模型或策略版本，使测量结果可以对应到唯一配置。

Capacity Planning 的资源账要拆成计算、显存、内存带宽、主机开销和同步等待。平均流量无法覆盖突发和长尾通常只先改变其中几项，其他资源随后可能进入关键路径。Capacity Planning 的请求时间线和资源曲线可以呈现这种转移，平均 GPU 利用率只作为辅助信号。

工作负载一变，Capacity Planning 对系统的贡献也会变化。确定 Headroom 应覆盖长短输入、不同输出、并发、突发、采样与任务域，并保留低载、稳定高载和过载记录。容量判断不能从一次固定批量的短运行外推。

对 Capacity Planning 的优化只有在输出合同不变时才有效。Token 序列、采样分布、结构合法性、结束原因和错误传播均需对账。所有冗余位于同一故障域会触发停止与回退，系统恢复到已有证据支持的配置。

Capacity Planning 相关事件要能关联到稳定请求身份、模型与策略版本、开始结束时间、阶段耗时、资源采样和失败原因。故障后容量必须附带口径。缺少这些信息时，关于“如何从工作负载分布、性能曲线和 SLO 推导长期容量与安全余量？”的判断无法在上线后复核。

### 流量预测

在 Capacity Planning：流量预测、Headroom 与 GPU Fleet 中，流量预测的边界由输入、输出、状态和拥有者共同确定。把生命周期写清楚，才能定位请求在哪个阶段等待、计算或复制。流量预测连接性能曲线时还要传播身份和版本，避免把另一套配置的结果归到当前实验。

测量流量预测时分别记录算力、显存、带宽、CPU 开销与同步。发生“Headroom 吸收预测误差、故障和发布开销”后，缩短的阶段可能让另一项资源成为瓶颈。分析因此对齐流量预测的阶段事件和资源轨迹，不让单个平均利用率代替因果证据。

评估流量预测需要把负载分布写入实验：输入输出长度、并发、到达突发、采样方式和业务域都可能移动收益边界。建模故障与维护至少比较低载、临近容量与过载，结论只覆盖实际运行过的区间。

流量预测进入候选路径后，输出校验继续检查 Token、采样、结构、结束原因和错误传递。预测模型没有不确定性区间一旦出现，质量结果优先于速度数字；发布停止，流量回到已验证修订，相关请求留作重放。

观察流量预测需要稳定请求身份、模型与策略修订、起止时间、阶段耗时、资源快照和失败原因。SLO 缺口同时注明单位、窗口和分母。这些字段使“如何从工作负载分布、性能曲线和 SLO 推导长期容量与安全余量？”可以在发布后按原条件回放。

### 性能曲线

解释性能曲线时，先列出它接收什么、产生什么、由谁维护以及状态何时结束。Capacity Planning：流量预测、Headroom 与 GPU Fleet 的请求可能在这些交界处增加等待、计算或复制。与 Headroom 交互的字段必须携带版本身份，便于回放时找到同一配置。

围绕性能曲线建立资源模型，需要把计算量、显存占用、内存流量、主机工作和等待时间单独记账。故障域决定可同时损失的容量会移动关键路径，却很少让所有资源同比例变化。请求事件负责说明顺序，资源曲线负责解释瓶颈转移。

规划异构 Fleet 是否合适，取决于性能曲线所面对的长度分布、并发、到达过程、采样和任务域。实验在低载、接近饱和、过载三段保留同口径证据。固定长度与固定批量的结果用于解释机制，不承担完整容量结论。

性能曲线带来的速度变化仍需满足模型输出合同，包括 Token 序列、采样分布、结构合法性、结束原因和错误传播。出现采购容量到达晚于业务增长时，质量门禁应停止性能发布；回退目标是已验证配置，并保留问题请求用于复现。

性能曲线的观测记录包含请求身份、模型版本、策略版本、阶段时间、资源状态与失败原因。GPU 利用区间没有单位、统计窗口和分母时不参与决策。完整记录用于复查“如何从工作负载分布、性能曲线和 SLO 推导长期容量与安全余量？”在具体负载下是否成立。

### Headroom

Headroom 在 Capacity Planning：流量预测、Headroom 与 GPU Fleet 中的生命周期需要落到组件接口：输入从哪里来，状态由谁持有，输出交给谁，失败如何传播。它与故障容量之间的身份和版本若未绑定，请求时间线就可能混入旧配置。

季节性和增长改变长期需求对 Headroom 的影响会分散到计算、显存、内存带宽、主机处理和同步等待。某一阶段变短时，被遮蔽的成本可能随即暴露。为确认 Headroom 的变化来自哪里，本文对齐请求时间线与资源采样，而非只看整段运行的 GPU 平均值。

Headroom 的边际价值会随输入长度、输出长度、并发、流量突发、采样和任务域变化。验证设置复盘与重预测时分别运行低载、接近饱和与过载区间，并使用代表性分布。单一长度、批量或短窗口只能说明该测试点。

正确性门禁覆盖 Headroom 影响到的 Token、采样、结构、结束状态与错误。若检测到用峰值吞吐直接除平均 QPS，当前性能结果不进入候选评审，并立即切回已验证配置。失败样本与版本信息要一并保存。

为 Headroom 建立证据链时，统一保存请求 ID、模型及策略修订、关键时间点、资源快照和错误。单位有效容量成本的定义随报告存档，包括单位、窗口和分母。这样才能按同一条件重放“如何从工作负载分布、性能曲线和 SLO 推导长期容量与安全余量？”。

### 故障容量

对故障容量做边界检查，要覆盖输入、输出、状态归属和销毁时点。Capacity Planning：流量预测、Headroom 与 GPU Fleet 的等待、计算及复制都能沿这些节点定位。故障容量传给 GPU Fleet 的数据还应附带模型或策略版本，使测量结果可以对应到唯一配置。

## 6. 量化补充：到达、准入与有效吞吐

容量规划落到在线服务，先算系统内平均请求数：Little 定律 $\bar n=\lambda\bar T$，每秒 4 条、平均停留 0.5 s 则系统内 2 条，停留增到 2 s 就是 8 条——排队、计算中、仅留状态的都算。处理速度跟不上到达率时新请求累积，**准入控制**在接收前查可用 KV 与剩余时限：短请求 0.196 s 首输出＋6.76 s 生成已用 6.95 s，再排 0.1 s 就超时，提前识别可拒绝、转交或换更快配置；取消则停止后续迭代并在加速器操作完成后释放空间。KV 压缩、大 batch 与推测解码的收益会相互影响，要组合后重算。

吞吐要分完成与有效两种：$R_{\mathrm{good}}=\sum_i Q_iD_i/T_{\mathrm{obs}}$，分子只计正确且按期的请求。实测（Qwen3-8B 检索、八题、3 s 期限、每窗口 16 请求）：336 次回答 294 次正确、只有 155 次同时按时——139 次正确回答因太晚仍不合格。到达率 1/s 时两种在线策略有效吞吐均约 0.90 req/s；4/s 时逐个接纳完成 1.22 但有效只 0.31，连续批处理完成 2.33、有效 1.02；推到 16/s 完成只增到 2.38、有效反降约 41% 到 0.60——**4/s 比 16/s 按时返回更多正确答案**。配置选择要先找有效吞吐开始下降的到达率再限准入；计时从请求原定到达时刻起，引擎外排队也要计入。

配置比较先把实测换算成处理速度：请求 $L$ 新输入、$G$ 输出占加速器 $t_{\mathrm{GPU}}=L/r_P+(G-1)/r_D$（批内共享执行每请求都算一次调用、占用只计一次）。无同条件测量时用规格乘效率：RTX PRO 6000 实测 decode 带宽效率随 batch 从 33%（batch 1）升到 65%（batch 64），prefill 算力效率稳定 58%-62%（8K 输入前 6K 已缓存时 52%-58%）。decode 效率上升不是读取变快：关闭 CUDA Graph 逐个提交 kernel，读取从 15.44 增到 34.46 GB 一轮只从 26.26 增到 29.63 ms，几乎固定的开销被更多字节分摊——batch 1 多出的约 17.6 ms 是实现开销而非模型漏项，用 Graph 与更好调度可去（主机侧开销的判据见主题二 40 篇第 5 节，PD 配比代入见主题二 27 篇第 13 节）。

## 写在最后

容量规划给出的是「应该有多少余量」，而余量是否真的在故障时可用，取决于可观测性与隔离手段。下一篇：[Observability 与 Reliability：Trace、Canary、Drain 与隔离](/source/AI-Infra/3-大模型推理优化工程/29-Observability与Reliability-Trace-Canary-Drain与隔离)。