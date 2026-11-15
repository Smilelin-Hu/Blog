# Inference Economics：Cost per Token、SLO 与全局优化

## 1. 课程定位

“如何把 GPU 时间、缓存复用、服务等级和失败成本统一到可决策的单位经济模型？”贯穿本文。先把 Inference Economics、Cost per Token 及其状态边界讲清楚，再讨论计算、实现和上线证据。在 Inference Economics：Cost per Token、SLO 与全局优化中，算法选择只是决策的一部分；负载分布、模型修订、调度、显存、并发和服务等级都会改变结论。每项收益都需要对应可观察的事件与适用范围。

个人电脑即可完成本文的双路径验证：CPU 模拟负责检验 Inference Economics 到 Cost per Token 的方向，CUDA 实验负责测量真实执行代价。模拟、实测和外部资料不会混用。围绕 Inference Economics 得出的结果只对记录的模型、软件、设备和负载负责，同时给出失败原因与回滚入口。

## 2. 学习目标

1. 准确解释 Inference Economics、Cost per Token 和有效 Token 之间的状态与资源关系。
2. 使用“unit_economics = (GPU+CPU+network+storage+ops+expected_failure)/valid_outputs”建立可计算的收益边界并解释全部变量。
3. 围绕每有效 Token 成本、每成功任务成本、SLO Goodput 和全栈单位成本设计可复现实验。
4. 识别使用全部生成 Token 稀释成本、删除冗余获得虚假节省和 GPU 报表改善但总成本上升等典型失败模式。
5. 对“如何把 GPU 时间、缓存复用、服务等级和失败成本统一到可决策的单位经济模型？”给出包含适用条件、证据、风险和回滚的工程答案。

## 3. 前置知识与环境

阅读 Inference Economics：Cost per Token、SLO 与全局优化需要理解自回归生成、Tokenizer、Prefill、Decode、KV Cache、批处理和分位延迟的基本含义。涉及 Inference Economics 时，所有缩写都会在正文首次出现处定义；没有某个特定框架经验不妨碍理解机制。实验需要 Python 3.11 或兼容版本。围绕 Inference Economics 的机制模拟只依赖 CPU；真实路径需要任意可用的 CUDA GPU、与驱动兼容的 PyTorch，以及自行准备的本地小模型或兼容制品。

验证 Inference Economics 前必须记录 GPU 名称、数量、可用显存、驱动、CUDA、PyTorch、推理框架、模型摘要、精度、批量、序列长度和完整命令。脚本根据可用显存缩放模型、批量、上下文和样本数，并把 Inference Economics 状态写入报告；可选 CUDA 入口不下载未经确认的大模型。

## 4. 工程问题

Inference Economics：Cost per Token、SLO 与全局优化没有脱离环境的统一加速数字。评审记录应包含模型修订、长度分布、到达过程、并发、采样、缓存、每有效 Token 成本定义、服务等级和硬件；随后才能比较“选择有效成本分母”和“计入空闲和冗余”。缺少这些信息时，局部速度无法换算成系统收益。

需要纳入同一证据链的对象包括：Inference Economics、Cost per Token、有效 Token、SLO Goodput、空闲与冗余、共享成本分摊、失败成本、全局优化。它们并不处在同一个组件中，却会一起改变预期失败损失和全栈单位成本。正文按 Inference Economics 的生命周期、状态归属、测量位置和失败条件展开，再将同一方法应用到其他对象。

## 5. 知识串讲

### 核心直觉与基础关系

### 核心直觉：真正的目标是在 SLO 约束下最小化“有效服务成本”

最低 Cost/Token 如果伴随不可接受的 P99、拒绝率或冷启动，就不是可用的最优解。成本必须与 SLO、可靠性和容量余量一起看。

GPU 每小时成本：

$$C_g=\text{price per GPU-hour}$$

一段时间使用 $N$ 张 GPU、运行 $H$ 小时：

$$C_{infra}=N\cdot H\cdot C_g$$

如果输出 $T_{out}$ tokens：

$$CostPer1MOutput=\frac{C_{infra}}{T_{out}}\times10^6$$

但这只是第一层，因为输入 token、不同模型、缓存、失败请求都消耗资源。

### 有效 Token 与无效 Token

GPU 计算的 token 不一定都带来用户价值：

- Speculative rejected tokens；
- 用户取消后继续生成；
- failed/retried request；
- warming synthetic request；
- 重复 Prefill；
- timeout 后无用户消费的结果。

可以定义：

$$Efficiency_{useful}=\frac{UsefulTokens}{ComputedTokens}$$

这是“GPU 很忙”和“钱花得有效”的区别。

### Idle Cost

Fleet 按峰值部署，低峰大量空闲：

$$C_{idle}=GPUHours_{idle}\cdot C_g$$

Autoscaling 可以降低 idle cost，但可能增加：

- cold start；
- SLO miss；
- model load traffic。

所以缩得越狠不一定越省。

### Cold Start 的经济成本

Cold Start 不只是 latency：

- 下载带宽；
- 用户等待/流失；
- SLO penalty；
- burst queue；
- warmup GPU 时间。

可以近似：

$$C_{cold}=C_{compute}+C_{bandwidth}+C_{SLO}$$

Warm Pool 的 idle cost 与它比较，才能决定是否保留预热容量。

### Speculation 的经济账

Speculative Decoding 可能：

- 提高单用户速度；
- 增加 Drafter 计算；
- 增加 Verify tokens；
- 减少 Target 串行轮数。

所以收益：

$$ROI_{spec}=\frac{BaselineGPUTime-OptimizedGPUTime}{ExtraSpeculatorCost}$$

更直接地看：

$CostPerAcceptedToken$

而不是只看 `speedup x`。

### Multi-Model 的经济账

Dedicated：

- SLO 好；
- idle cost 高。

Multiplexed：

- GPU utilization 高；
- cold miss/load cost 高。

最优点取决于模型请求率 $\lambda_m$：

如果：

$$IdleCost_m < \lambda_m\cdot ColdMissCost_m$$

常驻可能更省；反之适合 multiplex/cold。

### 不同 SLO Tier 的价格

低延迟往往需要更多 Headroom：

```text
Standard: P99 TTFT < 3s
Premium : P99 TTFT < 1s
```

Premium 为了更低 queue：

- 需要更多 Ready Replica；
- 更大 Warm Pool；
- 更少 packing；
- 更高成本。

因此产品价格应体现：

$$Cost(SLO_{premium})>Cost(SLO_{standard})$$

SLO 是经济参数，不只是技术指标。

### Pareto Frontier

两个方案：

```text
A: P99=0.8s, cost=$4/1M tokens
B: P99=1.0s, cost=$2/1M tokens
C: P99=2.5s, cost=$1/1M tokens
```

如果业务 SLO 是 1.2s，A 虽更快，但 B 可能更经济。

把所有配置画：

```text
X = Cost
Y = P99 Latency
```

只保留不存在“又更便宜又更快”的点，就是 Pareto frontier。

### SLO-Constrained Optimization

正式目标：

$$\min_x Cost(x)$$

subject to：

$$P99_{TTFT}(x)\le S_{TTFT}$$

$$P99_{TPOT}(x)\le S_{TPOT}$$

$$ErrorRate(x)\le S_{error}$$

$$Quality(x)\ge Q_{min}$$

$x$ 可以包含：

- GPU type/count；
- replica count；
- warm pool；
- placement；
- speculator；
- model tier；
- multiplex policy；
- autoscaling target。

### 成本分摊

共享 Fleet 中，不能简单按请求数把 GPU 成本均分给租户。

可以使用：

$$Charge_u\propto\sum_r(InputTokens\cdot w_{in}+OutputTokens\cdot w_{out}+ExtraWork)$$

ExtraWork 包括：

- reasoning candidates；
- multimodal encoder；
- tool/sub-agent；
- model/adapter cold load（是否向用户计费取决于产品策略）。

内部 FinOps 可以更精细，外部价格不一定完全暴露真实成本结构。

### 六个项目如何形成完整能力

```text
Speculator Benchmark
             ↓
Workload Platform
             ↓
Gateway + Smart Router
             ↓
Multi-Model / Multi-LoRA
             ↓
GPU Fleet Planner
             ↓
Production Inference Platform
```

最终应具备的不是记住若干结论，而是：

能从一个真实推理业务的流量与 SLO 出发，选择算法和 Serving 架构，计算资源，部署多模型，监控系统，并证明优化真的降低了单位成本。

### 实验目标

扫描 draft depth，比较 AR Drafter 与 Parallel Drafter 在不同 acceptance 衰减下的单位有效 Token 成本。

### 环境

- Python 3.9+
- 仅使用 Python 标准库
- CPU 即可运行

### 运行

```bash
python run.py
```

可以修改 `base`、`decay`、Draft/Verify 成本，模拟不同 Speculator 与 GPU。

### 注意

本实验用于验证机制与成本模型。真实框架实验必须另外记录模型 revision、runtime 版本、GPU、并发和 workload。

对应主题：EAGLE-3 / P-EAGLE

### 实验目标

用 position-wise conditional acceptance 模拟 EAGLE-3 候选质量，寻找 accepted length 与 Draft/Verify 成本共同决定的最优 depth。

### 环境

- Python 3.9+
- 仅使用 Python 标准库
- CPU 即可运行

### 运行

## 写在最后

理论篇到此收束，接下来六个综合项目把前面的口径落成可运行的平台。下一篇：[新一代 Speculator Benchmark](/source/AI-Infra/3-大模型推理优化工程/31-新一代SpeculatorBenchmark)。