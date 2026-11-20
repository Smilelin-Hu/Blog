# LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo

## 1. 课程定位

理解 LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo，需要先回答“不同控制面如何表达服务、发现工作器、执行编排并恢复期望状态？”。本文沿着概念边界、性能关系、实现证据和发布条件四条线展开，其中 Serving Control Plane 与期望状态是最先核对的状态。工作负载、模型修订、运行时、资源余量和服务承诺共同决定控制面把声明的服务转化为可路由工作器是否值得采用，后续每个结论都会注明这些条件。

实验采用两条证据路径。CPU 机制模拟隔离 Serving Control Plane 与期望状态的因果关系；真实 CUDA 路径记录实现、框架和硬件开销。报告分别标记两类结果，协调延迟的模拟值不充当 GPU 基准，单台设备的绝对速度也不外推。最终结论必须能够复现、诊断并回滚。

## 2. 学习目标

1. 准确解释 Serving Control Plane、期望状态和工作器发现之间的状态与资源关系。
2. 使用“observed_state --reconcile→ desired_state；convergence = detection + action + readiness”建立可计算的收益边界并解释全部变量。
3. 围绕协调延迟、工作器发现时间、状态收敛时间和数据面降级成功率设计可复现实验。
4. 识别控制器反复创建重复副本、心跳抖动导致摘挂振荡和工作器注册成功但模型未就绪等典型失败模式。
5. 对“不同控制面如何表达服务、发现工作器、执行编排并恢复期望状态？”给出包含适用条件、证据、风险和回滚的工程答案。

## 3. 前置知识与环境

阅读 LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo 需要理解自回归生成、Tokenizer、Prefill、Decode、KV Cache、批处理和分位延迟的基本含义。涉及 Serving Control Plane 时，所有缩写都会在正文首次出现处定义；没有某个特定框架经验不妨碍理解机制。实验需要 Python 3.11 或兼容版本。围绕 Serving Control Plane 的机制模拟只依赖 CPU；真实路径需要任意可用的 CUDA GPU、与驱动兼容的 PyTorch，以及自行准备的本地小模型或兼容制品。

验证 Serving Control Plane 前必须记录 GPU 名称、数量、可用显存、驱动、CUDA、PyTorch、推理框架、模型摘要、精度、批量、序列长度和完整命令。脚本根据可用显存缩放模型、批量、上下文和样本数，并把 Serving Control Plane 状态写入报告；可选 CUDA 入口不下载未经确认的大模型。

## 4. 工程问题

决定是否采用 LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo 前，先冻结模型版本、长度分布、流量到达、并发、采样、缓存状态、协调延迟、服务等级和硬件配置。评审“选择控制面抽象”和“定义服务与工作器身份”时，由这些记录解释收益分子、成本分母及共享资源竞争。

本文跟踪八个概念：Serving Control Plane、期望状态、工作器发现、Ray Serve、KServe LLMInferenceService、NVIDIA Dynamo、健康与就绪、协调与租约。虽然它们分属不同系统层级，控制面可用性和数据面降级成功率会同时受到这些状态影响。后文从 Serving Control Plane 开始，逐项说明谁维护状态、在哪里计量、什么情况下失效，以及结果怎样传到请求端。

## 5. 知识串讲

### 核心直觉与基础关系

### 核心直觉：Control Plane 持续把“期望状态”拉回“实际状态”

生产平台不能依赖一次性的启动脚本。节点会失败、模型会升级、流量会变化，因此控制面必须持续观察并 Reconcile。

用户声明目标：

```yaml
model: reasoning-pro
replicas: auto
gpu: H100
min: 2
max: 16
```

这叫 Desired State。

当前实际可能：

```text
READY=2
LOADING=1
FAILED=1
```

这叫 Observed State。

Controller 不断执行：

$$Action = Reconcile(Desired,Observed)$$

直到实际状态逐渐接近目标。

这比写一个“一次性部署脚本”可靠，因为故障和资源变化持续发生。

### Control Loop

一个通用循环：

![Autoscaling 闭环：Observe → Decide → Act → Wait/Measure](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y3_l24_01.png)

例如 Autoscaling：

![ai3-24-L84](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y3_l24_02.png)

核心难点是：**Action 有延迟**。大模型 Cold Start 很慢，控制器不能假设扩容命令发出后容量立刻出现。

### Ray Serve 的抽象价值

Ray Serve 更接近应用级分布式 Serving：

- Deployment；
- Replica；
- DeploymentHandle / routing；
- autoscaling；
- model multiplexing；
- LLM-specific serving abstractions。

它的优势是 Python 应用与分布式 Serving 组合自然，适合把 LLM 与其他 Python service/DAG 组合。

这里关注的是：

它怎样把“模型服务”变成可扩缩的 Deployment/Replica，而不是记 API。

### KServe 的抽象价值

KServe 更接近 Kubernetes-native Model Serving Control Plane。

对象通常通过 CRD 描述，Controller 负责生成/管理：

- Workload；
- Service/Gateway；
- Routing resources；
- Model-specific serving resources；
- Autoscaling/rollout。

LLMInferenceService 类抽象把生成式模型需要的 routing、模型资源和工作负载描述引入 Kubernetes 控制面。

价值是：

让模型 Serving 生命周期进入 Kubernetes 声明式管理、RBAC、Operator、Gateway 等平台体系。

### NVIDIA Dynamo 的抽象价值

Dynamo 更强调分布式 LLM inference runtime/control components，例如：

- Frontend；
- Router；
- Worker；
- Planner；
- disaggregated components；
- LLM-specific metrics。

LLM 的扩缩容不能只看 CPU/内存，而要理解 TTFT、ITL、KV、active tokens、throughput profile 等推理特有信号。

### 不要把“框架对比”变成谁最好

更有价值的比较维度：

框架会持续变化，这些问题更稳定。

### 最小 Control Plane 数据模型

综合项目可以使用：

```text
Model
Deployment
Replica
Node/GPU
Route
ScalingPolicy
PlacementPolicy
Artifact
```

Replica 状态：

![ai3-24-L165](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y3_l24_03.png)

Controller 只做状态决策，不直接承担用户 token 流量。

### Controller 的幂等性

如果 Controller crash/restart，它会重复看到：

```text
Desired: 4 replicas
Observed: 3 ready + 1 pending
```

`reconcile()` 不能每次都再创建一个。

Action 必须通过：

- deterministic name；
- resource id；
- generation；
- optimistic concurrency；

保持幂等。

### 控制面故障不应立刻杀死 Data Plane

如果 Controller 暂时不可用，已有 Ready Replica 最好继续服务。

所以：

Control Plane failure 应主要影响“改变状态的能力”，而不是让所有已有请求立刻失败。

这是典型的故障隔离原则。

### 实验

实验实现一个纯 Python reconciliation loop：

输入 desired deployments 和 observed replicas，输出：

- CREATE；
- DRAIN；
- REPLACE；
- NOOP。

再注入：

- Replica failure；
- desired version upgrade；
- scale target 变化；
- node unavailable。

验证幂等。

### Serving Control Plane

对 Serving Control Plane 做边界检查，要覆盖输入、输出、状态归属和销毁时点。LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo 的等待、计算及复制都能沿这些节点定位。Serving Control Plane 传给期望状态的数据还应附带模型或策略版本，使测量结果可以对应到唯一配置。

Serving Control Plane 的资源账要拆成计算、显存、内存带宽、主机开销和同步等待。工作器注册和心跳维护当前容量视图通常只先改变其中几项，其他资源随后可能进入关键路径。Serving Control Plane 的请求时间线和资源曲线可以呈现这种转移，平均 GPU 利用率只作为辅助信号。

工作负载一变，Serving Control Plane 对系统的贡献也会变化。设置发现和心跳应覆盖长短输入、不同输出、并发、突发、采样与任务域，并保留低载、稳定高载和过载记录。容量判断不能从一次固定批量的短运行外推。

对 Serving Control Plane 的优化只有在输出合同不变时才有效。Token 序列、采样分布、结构合法性、结束原因和错误传播均需对账。控制面故障阻塞在途请求会触发停止与回退，系统恢复到已有证据支持的配置。

Serving Control Plane 相关事件要能关联到稳定请求身份、模型与策略版本、开始结束时间、阶段耗时、资源采样和失败原因。就绪验证时间必须附带口径。缺少这些信息时，关于“不同控制面如何表达服务、发现工作器、执行编排并恢复期望状态？”的判断无法在上线后复核。

### 期望状态

在 LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo 中，期望状态的边界由输入、输出、状态和拥有者共同确定。把生命周期写清楚，才能定位请求在哪个阶段等待、计算或复制。期望状态连接工作器发现时还要传播身份和版本，避免把另一套配置的结果归到当前实验。

测量期望状态时分别记录算力、显存、带宽、CPU 开销与同步。发生“不同控制面以 Actor、Kubernetes CRD 或分布式组件表达编排”后，缩短的阶段可能让另一项资源成为瓶颈。分析因此对齐期望状态的阶段事件和资源轨迹，不让单个平均利用率代替因果证据。

评估期望状态需要把负载分布写入实验：输入输出长度、并发、到达突发、采样方式和业务域都可能移动收益边界。设计期望状态协调至少比较低载、临近容量与过载，结论只覆盖实际运行过的区间。

期望状态进入候选路径后，输出校验继续检查 Token、采样、结构、结束原因和错误传递。声明配置与运行配置漂移一旦出现，质量结果优先于速度数字；发布停止，流量回到已验证修订，相关请求留作重放。

观察期望状态需要稳定请求身份、模型与策略修订、起止时间、阶段耗时、资源快照和失败原因。漂移数量同时注明单位、窗口和分母。这些字段使“不同控制面如何表达服务、发现工作器、执行编排并恢复期望状态？”可以在发布后按原条件回放。

### 工作器发现

解释工作器发现时，先列出它接收什么、产生什么、由谁维护以及状态何时结束。LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo 的请求可能在这些交界处增加等待、计算或复制。与 Ray Serve 交互的字段必须携带版本身份，便于回放时找到同一配置。

围绕工作器发现建立资源模型，需要把计算量、显存占用、内存流量、主机工作和等待时间单独记账。健康只描述进程而就绪需要真实能力会移动关键路径，却很少让所有资源同比例变化。请求事件负责说明顺序，资源曲线负责解释瓶颈转移。

区分健康与就绪是否合适，取决于工作器发现所面对的长度分布、并发、到达过程、采样和任务域。实验在低载、接近饱和、过载三段保留同口径证据。固定长度与固定批量的结果用于解释机制，不承担完整容量结论。

工作器发现带来的速度变化仍需满足模型输出合同，包括 Token 序列、采样分布、结构合法性、结束原因和错误传播。出现框架抽象遮蔽实际资源约束时，质量门禁应停止性能发布；回退目标是已验证配置，并保留问题请求用于复现。

工作器发现的观测记录包含请求身份、模型版本、策略版本、阶段时间、资源状态与失败原因。控制面可用性没有单位、统计窗口和分母时不参与决策。完整记录用于复查“不同控制面如何表达服务、发现工作器、执行编排并恢复期望状态？”在具体负载下是否成立。

### Ray Serve

Ray Serve 在 LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo 中的生命周期需要落到组件接口：输入从哪里来，状态由谁持有，输出交给谁，失败如何传播。它与 KServe LLMInferenceService 之间的身份和版本若未绑定，请求时间线就可能混入旧配置。

租约和协调处理故障与重复拥有者对 Ray Serve 的影响会分散到计算、显存、内存带宽、主机处理和同步等待。某一阶段变短时，被遮蔽的成本可能随即暴露。为确认 Ray Serve 的变化来自哪里，本文对齐请求时间线与资源采样，而非只看整段运行的 GPU 平均值。

Ray Serve 的边际价值会随输入长度、输出长度、并发、流量突发、采样和任务域变化。验证决定失联后的数据面行为时分别运行低载、接近饱和与过载区间，并使用代表性分布。单一长度、批量或短窗口只能说明该测试点。

正确性门禁覆盖 Ray Serve 影响到的 Token、采样、结构、结束状态与错误。若检测到控制器反复创建重复副本，当前性能结果不进入候选评审，并立即切回已验证配置。失败样本与版本信息要一并保存。

为 Ray Serve 建立证据链时，统一保存请求 ID、模型及策略修订、关键时间点、资源快照和错误。数据面降级成功率的定义随报告存档，包括单位、窗口和分母。这样才能按同一条件重放“不同控制面如何表达服务、发现工作器、执行编排并恢复期望状态？”。

### KServe LLMInferenceService

对 KServe LLMInferenceService 做边界检查，要覆盖输入、输出、状态归属和销毁时点。LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo 的等待、计算及复制都能沿这些节点定位。KServe LLMInferenceService 传给 NVIDIA Dynamo 的数据还应附带模型或策略版本，使测量结果可以对应到唯一配置。

KServe LLMInferenceService 的资源账要拆成计算、显存、内存带宽、主机开销和同步等待。数据面在控制面短暂不可用时需要降级通常只先改变其中几项，其他资源随后可能进入关键路径。KServe LLMInferenceService 的请求时间线和资源曲线可以呈现这种转移，平均 GPU 利用率只作为辅助信号。

工作负载一变，KServe LLMInferenceService 对系统的贡献也会变化。选择控制面抽象应覆盖长短输入、不同输出、并发、突发、采样与任务域，并保留低载、稳定高载和过载记录。容量判断不能从一次固定批量的短运行外推。

对 KServe LLMInferenceService 的优化只有在输出合同不变时才有效。Token 序列、采样分布、结构合法性、结束原因和错误传播均需对账。心跳抖动导致摘挂振荡会触发停止与回退，系统恢复到已有证据支持的配置。

KServe LLMInferenceService 相关事件要能关联到稳定请求身份、模型与策略版本、开始结束时间、阶段耗时、资源采样和失败原因。协调延迟必须附带口径。缺少这些信息时，关于“不同控制面如何表达服务、发现工作器、执行编排并恢复期望状态？”的判断无法在上线后复核。

### NVIDIA Dynamo

在 LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo 中，NVIDIA Dynamo 的边界由输入、输出、状态和拥有者共同确定。把生命周期写清楚，才能定位请求在哪个阶段等待、计算或复制。NVIDIA Dynamo 连接健康与就绪时还要传播身份和版本，避免把另一套配置的结果归到当前实验。

## 写在最后

控制面决定「谁在什么设备上运行」，而设备本身的差异会反过来约束放置决策。下一篇：[Heterogeneous GPU Placement：异构设备与拓扑亲和性](/source/AI-Infra/3-大模型推理优化工程/25-HeterogeneousGPUPlacement-异构设备与拓扑亲和性)。