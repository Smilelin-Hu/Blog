# RLHF 数据流图与分布式控制面

## 1. 本文要解决的工程问题

Rollout、Reward 与 Trainer 分别维护自己的队列和版本。一次重试后，同一轨迹被重复更新，另一些轨迹已经找不到生成策略，恢复只能从进程层面猜状态。

本文围绕一个可执行判断展开：怎样把 Rollout、Reward、Trainer 和版本账本组织成可恢复的分布式控制面？读完应能给出自己的系统边界、输入输出、版本关系和验收证据，而不是只复述工具名称或公式。

![RLHF 数据流与分布式控制面](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l27_01.png)

## 2. 本文交付物与判定标准

控制消息与大张量分开，Experience 需包含算法所需证据。

本文的核心决定是：用轨迹账本、幂等提交、版本护照和联合检查点连接 Rollout、Reward、Experience 与 Trainer 控制面。

完成学习和实验后，应当交付一份最小可复现记录，至少包含输入快照、配置、代码版本、运行状态、原始输出和结论边界。验收证据是：从任一 update_id 能反查全部轨迹、奖励和策略版本；故障注入后没有重复提交或静默遗漏。

围绕“RLHF 数据流图与分布式控制面”的验收不接受三类替代品：把模拟输出写成真实 GPU 结果；只展示成功样本而隐藏失败与 `SKIPPED`；只给总分，不保存能复算总分的对象级记录。

## 3. 前置知识与实验边界

“RLHF 数据流图与分布式控制面”的机制实验使用 Python 3.10 及以上版本和标准库，重点验证对象、算法或状态转换。真实硬件路径使用 PyTorch；检测不到 CUDA 时必须输出结构化 `SKIPPED`，不得静默改跑 CPU 后仍标成 GPU 实测。

本文控制面模拟验证状态语义，实际框架的网络、存储和调度行为需要目标集群复测。

### 3.1 单进程隐含了哪些保证

在一个 Python 进程中，程序先调用 `generate`，再计算 Reward，然后立刻使用同一份模型参数优化。调用栈天然提供顺序：生成完成前不会训练，训练前 Reward 已经存在，当前 Batch 不会被别的 Worker 重复消费，模型变量只有一份。即使代码没有显式写版本，这些保证也暂时由进程内存和串行控制流提供。

扩展到多个角色以后，每个保证都要被设计出来。Rollout Worker 可能复制了旧权重；Reward Worker 的环境调用时延差异很大；Trainer 在消费队列时模型已经前进；Reference Server 可能仍加载上一版 Adapter；控制器在超时后重发任务，原任务却稍后成功返回。若系统只保留响应文本和一个 Reward，后续无法判断它是否仍适合更新。

### 3.2 为什么“消息到了”不等于“数据可训练”

一条响应到达队列，只证明某个 Worker 产生了字节。它还需要通过完整性、版本、组一致性、奖励状态、Token 对齐和新鲜度门禁。对于 GRPO，一组八条响应只到七条时，组均值和标准差就改变；对于 PPO，缺少 Old Logprob 或 Value 会让目标函数无法还原；对于 Agent 轨迹，环境状态缺失会让 Reward 无法审计。

因此队列中的对象应当是状态化的 Trajectory 或 Experience，而不是裸字符串。对象要携带生成策略版本、Tokenizer、Template、Sampling Config、Prompt 与 Group ID、Token、Mask、Old Logprob、终止原因、Reward 证据以及内容哈希。只有满足算法合同后，它才从“生成结果”转变为“可训练数据”。

### 3.3 为什么吞吐最大化可能损害学习

让 Rollout 不停生成、Trainer 不停消费，表面上能提高 GPU 利用率，却会积累 Policy Lag。假设响应由版本 $v$ 生成，训练器当前版本为 $u$，定义版本滞后：

$$L_v=u-v$$

版本差只是离散代理，更直接的度量是当前策略与行为策略在响应 Token 上的偏移：

$$L_{\mathrm{kl}}=\frac{1}{N}\sum_t D_{\mathrm{KL}}\left(\pi_v(\cdot\mid s_t)\,\|\,\pi_u(\cdot\mid s_t)\right)$$

当积压增大，Experience 越来越离策略，Ratio 方差、Clip Fraction 和样本浪费都会上升。控制面的目标不是让单个组件永远满载，而是在学习质量、吞吐、显存和故障恢复之间找到可解释的工作点。

### 3.4 五类核心角色

典型后训练系统包含 Policy Trainer、Rollout Engine、Reward 或 Verifier、Reference Model，以及可选的 Critic。PPO 需要 Critic 产生 Value；GRPO 与 RLOO 通常用组内统计替代 Critic；RLVR 依赖可执行 Verifier；开放式任务可能使用 Reward Model 或 Judge。角色不同，数据合同随之变化。

控制器不承担大张量计算，却负责创建任务、放置角色、分配 Prompt、聚合 Group、触发权重发布、决定更新和处理故障。Checkpoint Manager、Artifact Store、Metric Collector 和数据目录则形成支撑服务。把这些服务省略在图外，会让恢复与审计看起来无成本。

### 3.5 三条不能混画的流

数据流承载 Prompt、Response、Token、Logprob、Reward、Advantage 与 Batch；版本流承载 Policy、Reference、Reward、Tokenizer、Template、Runtime 与 Environment 的不可变标识；控制流承载启动、心跳、背压、同步、暂停、提交、取消和恢复。三条流可能经过相同进程，但语义不同。

图中 `Policy Bundle` 不是一串临时参数，而是模型或 Adapter 制品、版本、哈希、Tokenizer、Template 和生成兼容信息的集合。`Checkpoint / 账本` 也不仅保存模型，它还保存消费游标、已提交 Experience、采样器状态和控制器状态。

### 3.6 一条 Experience 的生命线

Prompt 先由 Sampler 选择并获得 `prompt_id`、`group_id` 和目标 Policy Version。Rollout 为每个 Group Member 生成响应，记录 Token、Old Logprob、Stop Reason 和运行证据。Reward 阶段解析输出、调用环境或模型，形成分量化结果。Group Aggregator 在成员齐全或明确超时策略后计算优势。Trainer 通过版本与完整性门禁，组装 Batch、反向传播并提交更新。

这条生命线必须允许查询。给定 `experience_id`，系统能定位每个阶段的输入、输出、状态、时间、重试次数和制品版本；给定一个 Checkpoint，又能反查哪些 Experience 被提交。没有双向血缘，分布式系统只能给出“某个任务失败”，无法解释影响范围。

### 3.7 数据面追求大吞吐

数据面包含批量 Prompt、KV Cache、Token 序列、Logprob、Reward Tensor 与梯度。它关注批处理、序列长度、Pinned Memory、序列化、网络带宽和 GPU 利用率。大对象应尽量走共享内存、对象存储或张量通信，避免通过中心控制器复制。

如果每条响应都先回到 Controller 的 Python 堆，再转发给 Reward 和 Trainer，控制器会成为序列化与内存瓶颈。合理设计是 Controller 只传 Object Reference 与元数据，让 Worker 直接读取对象；大规模环境下可用分布式对象存储、流系统或专用 Transfer Engine。

### 3.8 控制面追求确定语义

控制面消息很小，却决定系统是否正确。它包含 Job ID、Role、Lease、Policy Version、Group Deadline、Queue Watermark、Checkpoint Barrier 和 Commit ID。控制消息要幂等、可重试、带时钟与状态机，并能区分期望状态与观察状态。

控制器不能因为一次 RPC 超时就认定 Worker 没执行。它应给任务分配唯一 ID 和租约，Worker 完成后按 ID 提交；重复提交由账本去重。取消也不是删除消息，而是写入期望状态，Worker 在安全点响应。否则“超时重试”会演化成重复生成与重复更新。

### 3.9 证据面让结果可以追溯

证据面保存 Manifest、日志、指标、事件、内容哈希、固定回放与审计记录。它不位于训练热路径的每个字节上，但必须覆盖所有语义转折：哪版 Policy 生成、哪版 Reward 评分、哪次更新消费、哪次故障恢复重放。

证据面应分冷热层。热层保留近期任务状态和调试字段，支持快速下钻；冷层保留不可变 Manifest、聚合统计和需要长期审计的制品。敏感文本可加密、脱敏或按权限访问，但元数据血缘和删除传播必须存在。

## 4. 同步控制为什么最容易理解，却不一定最省资源

### 4.1 同步迭代的状态机

失败重试产生 Attempt，不能改写逻辑任务身份。

同步系统在每一轮冻结 Policy $v$，生成规定数量的响应，等待 Reward 与 Group 完成，随后 Trainer 使用这批 Experience 更新若干步，发布 Policy $v+1$，再开始下一轮。它的好处是数据新鲜度清楚，版本边界整齐，Initial Ratio 容易验证。

状态机可以写成 `ROLLOUT → REWARD → TRAIN → PUBLISH → COMMIT`。只有当前状态完成才能进入下一状态，失败则重试或从最近 Barrier 恢复。对于教学与早期验证，这种方法最适合建立可信基线。

### 4.2 Barrier 带来哪些空闲

Rollout 长尾会让其他 Worker 等待最慢任务；Reward 中的工具和 Judge 时延更不稳定；进入 Train 后，专用 Rollout GPU 可能空闲。若同一批 GPU 在阶段间重分片，权重和优化器状态迁移又会带来昂贵停顿。

设一轮 Rollout、Reward、Train、Publish 时间分别为 $T_r,T_w,T_t,T_p$，完全串行轮次时间为：

$$T_{\mathrm{iter}}=T_r+T_w+T_t+T_p$$

资源利用率受各阶段占比限制。同步并不等于低性能，可以通过阶段内部并行、Prompt 长度分桶、推测终止和重叠部分 I/O 改善；但全局 Barrier 仍使长尾显著。

### 4.3 同步基线怎样做得可信

首先为每轮生成 `iteration_id` 和冻结的 Policy Bundle。其次规定 Group Timeout：超时后是丢整组、补采样还是允许变长组，必须由算法定义。再次，在 Train 前运行完整性与版本门禁，并把本轮可训练 Experience 集合写成不可变清单。

最后，Publish 只有在模型、优化器、数据游标和提交账本共同 Checkpoint 成功后才可见。若只上传权重而提交账本失败，恢复时可能使用新权重重复旧数据。发布应采用临时路径加原子指针切换，读者只看到完整 Bundle。

## 5. 异步控制为什么更快，也更难证明正确

### 5.1 异步流水线的基本想法

Rollout 持续读取最新可用 Policy，Reward 持续消费 Trajectory，Trainer 持续消费 Experience 并周期性发布新权重。阶段重叠以后，理论吞吐接近最慢阶段的速率，而不是各阶段时间之和。设三个稳定阶段服务率为 $\mu_r,\mu_w,\mu_t$，流水线长期吞吐上限约为：

$$\lambda_{\max}\le \min(\mu_r,\mu_w,\mu_t)$$

但这个结论依赖队列稳定。若到达率长期超过某阶段服务率，积压和 Lag 会无界增长。异步系统必须用背压调整 Sampling 或暂停上游，而不能把对象存储当无限缓冲。

### 5.2 Policy Lag 怎样进入训练门禁

最简单的门禁限制版本差 $u-v\le L_{\max}$。它便于实现，但不同更新幅度下相同版本差并不等价。更可靠的方法在 Trainer 侧重算 Current Logprob，观察 Ratio、近似 KL 或 Clip Fraction，并按异常程度拒绝或降权。

拒绝旧 Experience 会浪费昂贵 Rollout，接受过旧 Experience 又伤害 On-policy。系统可动态控制发布频率、队列深度和 Trainer 更新步数，使浪费率与学习稳定在预算内。Lag 指标应按 Token、Prompt 域、响应长度和 Worker 分桶，避免聚合均值掩盖某个慢 Worker。

### 5.3 异步组聚合有什么陷阱

GRPO 组成员若由不同 Policy Version 生成，组内相对 Reward 不再对应同一行为分布。即使版本差只有一，Sampling Temperature 或模板变化也会破坏可比性。控制器应在分配时固定 Group 的 Policy Bundle，并让所有成员携带相同 `group_policy_version`。

成员超时后补采样也必须使用原版本。如果原 Bundle 已被回收，组应失效，而不是用最新策略补一条。组状态包含 Planned、Running、Partial、Complete、Expired 和 Invalid；只有 Complete 且版本一致才进入优势计算。

## 6. 混合控制如何兼顾边界与重叠

### 6.1 微批次流水线

把一轮大 Rollout 拆成多个 Microbatch。第一个 Microbatch 进入 Reward 时，Rollout 可以生成第二个；第一个进入 Train 时，Reward 处理第二个。所有 Microbatch 仍绑定同一 Policy Version，在轮次末统一发布。这样保留版本边界，又重叠阶段。

代价是需要更细的 Group 和 Commit 管理。Trainer 在同一轮更新后，后续 Microbatch 若仍按旧策略生成，会逐渐离策略；可以累积梯度后只做一次更新，也可以允许有限更新并监控 Ratio。选择必须写进 Objective Contract。

### 6.2 有界异步

有界异步允许 Rollout 与 Trainer 同时运行，但限制最大 Policy Lag、最大队列 Token、最大 Group Age 和每版最大更新数。当任一阈值触发，控制器暂停上游、强制发布或清理过期数据。它比完全异步容易运营，是很多实际系统的折中。

有界条件要由测量校准。版本差二不一定安全，版本差五也不一定危险；关键是 Ratio 分布、Clip Fraction、KL 和固定评测。先在同步基线得到正常区间，再逐步扩大窗口，并记录吞吐收益与样本丢弃成本。

### 6.3 Partial Rollout 什么时候有用

长 Agent 轨迹可能运行数分钟，等完整结束才训练会增加时延。Partial Rollout 把轨迹切成片段，Trainer 先消费已完成片段，后续再续生成。它要求保存环境状态、KV 或可重建上下文、片段边界、Bootstrap Value 和终止语义。

对 GRPO 终局 Reward，未完成片段没有最终组优势，不能简单当普通 Experience。可以延迟信用、使用 Process Reward、Value Bootstrap 或仅把片段用于别的目标。Partial 是算法与系统共同设计，不是把列表切片。

## 7. 控制器应当是中央大脑还是分层协调者

控制器管理身份和状态，不应搬运全部训练内容。

### 7.1 单一中央控制器

中央控制器维护所有角色、队列和迭代状态，逻辑集中，便于调试和一致性。小规模实验和单集群训练适合这种结构。它不传大张量，只保存引用与元数据，避免成为数据面瓶颈。

风险是单点故障和状态膨胀。控制器必须把关键状态外置到持久账本，重启后通过事件重建，而不是依赖 Actor 内存。高频心跳和细粒度 Token 事件不应全部写进中央状态。

### 7.2 分层控制器

大规模系统可以由 Global Controller 分配资源池、策略版本和迭代，Local Controller 管理一组 Rollout 或 Trainer Worker。局部故障先在本组恢复，减少全局事件量。分层还可对应机架、可用区或不同网络域。

分层会引入一致性边界。Global 与 Local 对任务所有权必须通过 Lease 明确；Local 失联后，Global 等 Lease 到期再重新分配，避免两个控制器同时执行。Policy Publish 由全局版本服务裁决，本地缓存只读不可改。

### 7.3 去中心化工作窃取

Worker 直接从共享队列拉任务，实现简单伸缩和负载均衡。对于独立 Prompt 或 Reward 任务很有效；对于需要固定 Group、版本亲和或环境会话的任务，必须加队列分区和亲和键。

工作窃取不能破坏数据位置。若 KV、模型或环境状态在特定节点，搬任务比等待更贵。调度器需要把负载与位置一起考虑，而不是只看空闲 GPU。

## 8. 资源池与 Worker Group 怎样表达算法角色

### 8.1 资源池不是设备列表

资源池描述一组具有共同能力、网络和生命周期的资源，例如 Rollout GPU Pool、Trainer GPU Pool、CPU Verifier Pool 和高内存 Judge Pool。它还包含设备类型、显存、互联、节点标签、租户配额和可抢占属性。

Worker Group 是算法角色的并行集合，例如八个 Rollout Actor 或一个四卡 FSDP Trainer。一个 Group 的成员可能需要 Gang Scheduling，因为缺一张卡就无法启动；独立 Verifier Worker 则可以弹性伸缩。

### 8.2 Colocate 与 Disaggregate 的取舍

Colocate 把 Rollout 与 Trainer 放在同一批 GPU，阶段间复用显存和高速互联，减少闲置，但需要模型状态切换、显存整理和重分片。Disaggregate 使用独立资源池，阶段可并行、故障隔离好，却需要权重同步并复制模型。

对至少一张可用 CUDA GPU 的实验，采用最清楚的 Disaggregate：GPU 0 生成，GPU 1 训练。它不是吞吐最优配置，却能显式观察队列和权重版本。生产选择要根据模型大小、阶段占比、网络、同步频率和资源价格建模。

### 8.3 资源放置应考虑什么

Trainer 的张量并行成员需要高带宽互联；Rollout Replicas 更容易跨节点；Reward Model 若较小可与 CPU Parser 混合；执行型 Verifier 需要沙箱和网络隔离。Placement Group 需要表达 Pack、Spread、Strict Pack 和拓扑约束。

只按 GPU 数量调度会让通信密集角色跨慢链路，或让多个高 CPU 环境共享一个核。每个 Role Manifest 应声明 GPU、CPU、内存、共享内存、临时磁盘、端口、网络和安全需求。调度失败也要输出原因，而不是无限 Pending。

## 9. 权重发布为什么是控制面的核心事务

缺失分片或加载失败时不能提前切换路由。

### 9.1 发布对象包含哪些内容

Policy Bundle 至少包含 Base Model 标识、Adapter 或完整权重、Tokenizer、Chat Template、Generation Defaults、精度、并行兼容信息、内容哈希和 Policy Version。若 Rollout Runtime 需要特殊格式，还要包含转换制品与 Runtime Version。

发布不是直接覆盖共享文件。Trainer 先写临时目录，计算哈希并生成 Manifest，验证完整后原子更新 `latest` 指针。Rollout 在安全点读取指针，下载并验证哈希，再切换本地活动版本。切换失败继续使用旧版并上报，不加载半份权重。

### 9.2 全量权重与 LoRA Delta

全量发布通用但带宽和停顿大。LoRA 只同步 Adapter，适合 CUDA 实验和参数高效训练。接收端必须绑定相同 Base Model；Base 哈希不同，即使 Adapter 文件能加载，语义也错误。

Delta 发布可进一步只传变化块，但恢复和版本链复杂。若某个中间 Delta 丢失，后续无法应用。生产系统常周期性发布全量快照，中间发布 Delta，并让 Manifest 指明父版本。保留策略要覆盖活跃 Rollout 与可恢复窗口。

### 9.3 热切换与安全点

生成中的请求不能在一半 Token 时切换权重，否则一条响应来自两个策略。Rollout Worker 在 Batch 边界或请求边界切换，活动请求继续使用旧实例。内存允许时可双缓冲：后台加载新版本，验证后交换指针；显存紧张则需停顿卸载。

版本服务记录 Worker 的 Desired Version 与 Active Version。控制器等待足够 Worker 确认后开始分配新 Group；未更新 Worker 可以继续完成旧 Group，但不领取新版本任务。这样把滚动更新与组一致性结合。

## 10. 队列、背压与容量怎样一起设计

![队列、背压与容量](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l27_02.png)

### 10.1 用 Token 而不是条数看队列

一千条短响应和一千条长响应的计算量完全不同。队列应统计 Prompt Token、预计生成 Token、已生成 Token、有效 Response Token 和对象字节。背压阈值以 Token 与 Age 为主，条数只作辅助。

如果 Reward 服务率低于 Rollout，Trajectory Queue 增长；如果 Trainer 慢，Experience Queue 增长。每个队列分别记录到达率、完成率、在途数、等待时间分位数、最老对象年龄和版本分布。只看总长度无法定位瓶颈。

### 10.2 Little 定律如何估算在途量

稳定系统中，平均在途数 $N$、到达率 $\lambda$ 与平均停留时间 $W$ 近似满足：

$$N=\lambda W$$

若每秒进入二十条轨迹、平均从生成到更新等待三十秒，系统约有六百条在途。将条数换成 Token 可估显存、内存和对象存储压力。该关系要求长期稳定，突发和长尾需看分位数。

### 10.3 背压动作分几级

第一层降低新 Prompt 领取速率；第二层减少每 Prompt 组大小或并发，但改变算法前要谨慎；第三层暂停低优先级域；第四层停止 Rollout，只排空队列；第五层触发熔断并保存检查点。动作应有滞回，避免水位在阈值附近频繁开关。

背压不能通过静默丢数据实现。过期对象写明确状态和原因，统计浪费的生成 Token 与成本。若 Lag 门禁持续丢弃，根因可能是 Trainer 过慢、更新太频繁或队列过深，应调控制参数而非提高丢弃阈值。

## 11. Experience Schema 怎样成为角色之间的共同语言

### 11.1 为什么不能直接传框架内部对象

## 写在最后

控制面之下，Rollout 引擎与权重同步决定实际吞吐。下一篇：[Rollout 引擎、权重同步、重分片与资源放置](/source/AI-Infra/5-数据工程与后训练/28-Rollout引擎-权重同步-重分片与资源放置)。