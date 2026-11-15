# Volcano 调度策略与在线离线混部

一个八卡 GPU 集群同时运行在线推理和离线训练。在线服务平时只用两张卡，早高峰需要四张；离线训练趁夜间借到六张，其中两张超过离线队列应得份额。九点流量上升时，如果调度器只按 Pod Priority 逐个抢占，可能杀掉分布式训练的一个 Worker，剩余五张卡继续被无效占用；如果只按 Binpack 追求装满节点，又可能把在线副本与批任务集中到同一机架，单点故障扩大；如果只做 Gang 而没有跨队列回收，在线队列仍拿不回被借走的两张卡。

![Volcano 调度策略与混部](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l13_01.png)

Volcano 的价值不在“比默认调度器多几个插件”，而在于把批作业、PodGroup、Queue 和可组合调度策略放进一个 Session。每个 Session 从缓存获取当前集群与作业快照，按配置顺序执行 Action；Action 负责某一阶段的主流程，Plugin 向 Session 注册排序、过滤、评分、Gang、公平、抢占与回收等函数。最终结果由 Action 顺序、Tier、Plugin 组合、对象字段和当前资源共同决定。

本文先给出五个边界。

第一，Action 与 Plugin 不是同一层。`allocate`、`preempt`、`reclaim` 是动作阶段；`gang`、`predicates`、`drf`、`capacity`、`nodeorder`、`binpack` 等插件提供被动作调用的函数。只启用 Plugin 却没有对应 Action，不一定产生期待行为；Action 顺序错误也会改变结果。

第二，`preempt` 与 `reclaim` 作用域不同。官方 Action 文档将 Preempt 定位为同一 Queue 内 Job 之间或同一 Job Task 之间的优先级抢占；Reclaim 处理不同 Queue 之间的资源回收。在线队列从离线队列拿回借用资源，应建模为 Reclaim，不是笼统跨队列 Preempt。

第三，`guarantee`、`deserved` 和 `capability` 分别表达保留、应得与硬上限。Queue 超过 Deserved 时可借用闲置，但其他 Queue 有需求时超额部分可被回收；Capability 限制最多使用；Guarantee 是只供该 Queue 使用的保留。启用 Capacity Plugin 时显式配置 Deserved；Proportion Plugin 按 Weight 计算 Deserved。当前官方指南明确指出 Capacity 与 Proportion 冲突，不能同时启用。

第四，Binpack 只是一种节点评分偏好。它在可行节点中倾向更满的节点，减少碎片并利于缩容，却不能替代 Predicates 硬过滤、Gang 整体提交、Queue 公平与故障域策略。GPU 权重调高可以更积极装箱，也会集中热量、网络和故障风险。

第五，在线离线混部不是“在线高 Priority、离线低 Priority”就结束。还需要在线 Guarantee 与 Deserved、离线 Reclaimable、批作业 Checkpoint、Victim 终止时间、在线模型预热、Pod 层 QoS、CPU 与内存隔离、网络和缓存监控。Queue Reclaim 只解决资源权利与调度，不自动保证服务 Ready。

实验在同一组节点和作业上切换 Binpack 与 Spread、DRF 顺序、Capacity 与 Proportion、同队列 Preempt 和跨队列 Reclaim。实验还验证在线回收加模型预热是否在九十秒 SLO 内完成，并注入十二种冲突与失败。模拟结果不等于真实 Volcano 兼容性；Live 路径没有专用 Context 时保持 SKIPPED。

## 1. Volcano 在 AI 平台中的位置

Volcano 是面向高性能与批处理工作负载的云原生系统，包含 Scheduler、Controller、Admission、CRD 与命令工具。它可以调度 VolcanoJob、PodGroup 以及由其他框架生成并指定 `schedulerName: volcano` 的 Pod，也在扩展对原生工作负载和异构设备的统一调度。

### 1.1 Batch Scheduler 关注作业而不只是 Pod

默认 kube-scheduler 的核心单位是 Pod。Volcano 通过 Job 与 PodGroup 知道多个 Task 属于同一作业、最少多少成员需要共同运行、归属哪个 Queue、采用什么 Priority 和故障策略。这样调度决定可以围绕完成一项工作，而非让尽可能多独立 Pod 变成 Bound。

作业级视角适合分布式训练、MPI、Spark 与大规模批处理，但不会自动理解训练算法。`minAvailable`、Task 角色、Checkpoint 和失败 Policy 仍要由平台与用户正确声明。

### 1.2 Scheduler 负责 Session 与节点决策

Volcano Scheduler 监视并缓存 Job、PodGroup、Queue、Node 与 Pod 状态，周期性打开 Session，执行配置 Action 并调用 Plugin 函数，产生分配、驱逐与绑定操作。Session 关闭后，下一轮基于更新后的 API 和缓存继续。

这是调度控制面，不负责容器运行、设备驱动或模型服务路由。Pod Bound 后仍由 Kubelet 与运行时执行。

### 1.3 Controller 负责对象生命周期

Volcano Controller 处理 vcjob 等对象，创建或管理 Pod、Service、ConfigMap 与状态。Job Policy 可以在 PodEvicted、PodFailed 或 TaskCompleted 等事件后 RestartJob、RestartTask、AbortJob 或 CompleteJob，具体事件与动作以目标版本为准。

Scheduler 决定在哪里和何时调度，Controller 决定作业对象怎样生成成员和响应生命周期事件。二者版本和 CRD 必须兼容。

### 1.4 Admission 负责默认与校验

Admission 组件可验证 Queue、Job、PodGroup 与调度字段，补充默认配置或拒绝无效对象。它是多租户安全边界，防止普通用户选择未授权 Queue、Priority 或 Scheduler 配置。

Webhook 不可用时的 Fail 策略需要测试。绕过 Admission 的 Pod 可能不受 Gang 与 Queue 合同保护。

### 1.5 CRD 与原生 Pod 是两类入口

vcjob 提供 Task、插件、Policy、Queue、Priority 与 minAvailable 等完整批作业语义；其他 Operator 可直接创建 Pod 并关联 Volcano PodGroup，或让 Pod 指定 Volcano Scheduler。不同入口能否提供完整 Job 信息不同。

平台产品应选少量黄金路径。所有工作负载都直接使用 vcjob 会重复上层 Operator 能力；所有工作负载只生成裸 Pod 又会丢失作业 Policy 和状态。

### 1.6 与 Kueue 是分层关系而非简单替代

Kueue 擅长在 Pod 创建前管理 Workload Quota、LocalQueue／ClusterQueue、Cohort、AdmissionCheck 与多集群派发；Volcano 擅长 Scheduler Session 中的 Gang、节点放置、Queue 公平、Preempt 和 Reclaim。可以只选一种覆盖部分需求，也可以让 Kueue 做上层准入、Volcano 做节点调度。

组合时只有一个最终组织 Quota 权威。若 Kueue 与 Volcano Queue 都独立做相似借用和回收，用户会受到两套策略。明确 Kueue 决定“谁可启动”，Volcano 决定“已获准入的作业如何放置”，或在采用 Volcano Queue 时关闭重叠控制。

### 1.7 不是所有集群都需要 Volcano

独立 Pod、简单 Deployment 和少量 Job 可以使用 kube-scheduler 及 Kueue。引入 Volcano 意味着维护 Scheduler、Controller、Admission、CRD、配置、升级兼容和专门监控。只有 Gang、批 Queue、DRF、Capacity、复杂拓扑或统一批调度的收益超过复杂度时采用。

平台记录选型依据与未选能力，避免工具成为默认答案。

## 2. 核心对象：Job、Task、PodGroup 与 Queue

Volcano 的调度语义来自对象关系。Job 描述整体工作，Task 描述一组同模板角色，PodGroup 承载 Gang 与队列状态，Queue 定义多租户资源边界。

### 2.1 vcjob 是作业合同

`batch.volcano.sh` 下的 Job 包含 Queue、SchedulerName、PriorityClass、minAvailable、maxRetry、Policies、Plugins 与 Tasks。每个 Task 有 Replicas 和 PodTemplate。一个训练可有 Master Task 一个副本与 Worker Task 四个副本。

Job 对象让 Controller 能整组 Restart 或 Complete，并为 Scheduler 提供作业级排序。字段随版本变化，生产使用目标 CRD Schema。

### 2.2 Task 不是运行 Pod 本身

Task 是模板与角色集合，Controller 据此创建多个 Pod。Task 名称可用于服务发现、Task Topology 与故障 Policy。Replicas 乘单 Pod Request 形成角色资源总量。

异构 Task 使 Gang 计算更复杂：一个 Master CPU、四个 Worker GPU，minAvailable 的数量必须与可运行角色组合一致，不能随便选四个 Pod 而缺 Master。

### 2.3 Command 与容器入口仍由用户定义

Volcano 负责调度和生命周期，不修复错误 Command、镜像、Secret 或数据路径。Job Plugin 如 env、svc、ssh 可注入分布式环境和服务发现，但应用仍需正确 Rendezvous。

调度成功而训练无 Progress 时，排障转到容器与运行时，不继续调 Binpack 参数。

### 2.4 PodGroup 是调度组状态载体

PodGroup 记录 minMember／minResources、Queue、Priority 与 Phase。vcjob 通常自动生成关联 PodGroup，其他 Operator 也可创建。Scheduler 用它判断 Pending、Inqueue、Running 等状态和 Gang 门槛。

Pod 必须使用一致 Scheduler 和组引用。只创建 PodGroup 但 Pod 仍走 default-scheduler，不会获得 Volcano Gang。

### 2.5 Queue 是集群级资源分配对象

Volcano Queue 可配置 Weight、Guarantee、Deserved、Capability、Priority、Reclaimable 和 Parent 等字段。Status 报告 Allocated、State 等信息。多个 Job 引用 Queue，Scheduler Plugin 据此排序与分配。

Queue 不是 Namespace；平台用 Admission 把 Namespace、项目与允许 Queue 映射。普通用户不应自由创建集群 Queue。

### 2.6 Queue 状态控制新作业

Queue 可 Open 或 Closed 等状态，具体枚举按版本。关闭 Queue 时新 Job 不能正常进入，存量影响需要用目标版本实验验证。维护操作前列出所有 PodGroup 与 Allocated。

删除 Queue 不是停止的替代。孤儿 Job 和状态关联会更难恢复。

## 3. 调度 Session：为什么配置顺序会改变结果

Volcano 不是对每个 Pod 运行一条固定函数链，而是周期性打开 Session。Plugin 在 Session 打开时注册多类函数，Action 在 Session 内遍历 Queue、Job、Task 与 Node，通过 Statement 暂存 Allocate、Evict 或 Pipeline 操作，达到提交条件后 Commit，否则 Discard。

### 3.1 Cache 提供调度快照

Scheduler Watch API 并维护 Node、Pod、Job、Queue 和 PodGroup 缓存。Session 从缓存建立快照，避免每次计算直接远程读取。快照可能与 API 有短暂延迟，因此最终操作仍要处理冲突和对象变化。

Scheduler 重启后从 API 重建缓存，不能依赖丢失的内存 Reservation。升级测试包含 Session 中断与 Leader 切换。

### 3.2 OpenSession 注册 Plugin 函数

配置中的 Tier 与 Plugin 在 Session 打开时注册 QueueOrder、JobOrder、TaskOrder、Predicate、NodeOrder、JobReady、JobPipelined、Preemptable、Reclaimable、Overused 等函数。一个 Plugin 可注册多个函数，一个 Action 也会调用多个 Plugin 提供的同类函数。

因此“启用 DRF”不只是多一个排序步骤，它可能影响 Job 或资源比较；“启用 Gang”会影响 Ready、Pipelined 与提交判断。

### 3.3 Action 定义 Session 中的主循环

`enqueue` 决定哪些 Job／PodGroup 从 Pending 进入 Inqueue；`allocate` 为可调度 Task 选择 Node 并尝试提交；`preempt` 处理同 Queue 高优先级需求；`reclaim` 从其他可回收 Queue 拿回超额；`backfill` 处理特定剩余任务。动作按配置字符串顺序执行。

官方文档明确指出 Volcano 不会自动检查 Action 顺序是否合理。平台必须用行为测试校验，而不是只验证 ConfigMap YAML 合法。

### 3.4 Statement 提供暂存与提交

Allocate 过程中，Scheduler 可能为 Job 的多个 Task 暂存节点。Gang 门槛满足后 Commit，绑定动作生效；不满足则 Discard 或回滚本 Session 操作。这避免四 Worker 只提交三个。

Statement 不是跨 API Server 的数据库事务。绑定与驱逐仍可能有时间偏斜，Controller 和下一 Session 需从实际状态收敛。

### 3.5 Tier 解决同类函数组合顺序

多个 Plugin 可能都注册 JobOrder 或 Preemptable 函数。Tier 定义优先层次，使 Priority、Gang 和 Conformance 等强政策先于 DRF、Predicates、Capacity 与 NodeOrder 等算法。具体合并逻辑因函数类型不同。

随意交换 Tier 会改变 Priority 与公平的主次。保存配置 Hash 并回放相同作业集。

### 3.6 CloseSession 完成周期

Action 执行后关闭 Session，释放临时状态并输出指标。下一周期观察绑定、驱逐和新提交结果。Session 周期过短会增加计算，过长会提高调度延迟；大集群需性能调优。

任何 Plugin 都应避免长时间阻塞 Session。外部网络调用不适合放在关键 NodeOrder 热路径。

## 4. Action 管线的五个关键阶段

Action 名称相似，但各自处理不同状态和作用域。在线离线混部尤其依赖 Allocate、Preempt 与 Reclaim 的清晰边界。

### 4.1 Enqueue 提前判断最小需求

官方最新 Action 文档说明，Enqueue 在最小资源需求可满足时让 PodGroup 从 Pending 进入 Inqueue，vc-controller 随后才创建相关 Pod。这可以减少资源不足时大量不可调度 Pod，提高高负载场景控制面效率。

它比单纯 Scheduler 排队更早，是作业创建栅栏。需要确认目标版本 Controller 与 PodGroup 行为。

### 4.2 Enqueue 可能与 Preempt／Reclaim 冲突

官方文档特别提醒：若同时配置 Enqueue 与 Preempt／Reclaim，Enqueue 判断作业不能入队时，可能没有 Pending Pod 生成，后续 Preempt 或 Reclaim 缺少触发对象。结果是本应通过回收运行的高优先级作业被提前挡住。

这不是说永远不能组合，而是必须按版本、入口与场景验证。实验将该组合标 Known Risk，安全示例管线移除 Enqueue 以便演示回收。

### 4.3 Allocate 执行过滤、评分与 Gang 提交

Allocate 使用 Predicates 过滤不满足资源、亲和、污点、卷或端口的 Node，再通过 NodeOrder、Binpack 等评分选择。每个 Task 的候选放入 Statement，只有 Gang Ready 才 Commit。

Allocate 是必需 Action。缺失时即使 Plugin 齐全也不会完成正常分配。

### 4.4 Preempt 解决同 Queue 优先级

Preempt 在同一 Queue 的 Job 之间或同一 Job Task 之间选择低优先级 Victim，帮助高优先级 Task 获得资源。Priority Plugin 提供排序，Gang 和 DRF 可参与 Preemptable 判断。

同 Queue 边界保护部门隔离。跨部门资源所有权回收由 Reclaim 处理。

### 4.5 Reclaim 处理跨 Queue 借用回收

当某 Queue 需求增加且自己未 Overused，其他 Queue 使用超过 Deserved 并且 Reclaimable 时，Reclaim 可选择 Victim 释放资源。Capacity 或 Proportion 提供 Queue Deserved、Overused 与 Reclaimable 函数。

在线 Queue 从离线 Queue 拿回两张借用 GPU 就是典型 Reclaim。离线 `reclaimable: false` 会阻止这种回收，即使在线 Priority 高。

### 4.6 Backfill 的官方语义需按版本理解

当前 Action 文档将 Backfill 描述为处理未声明 Resource Request 的 BestEffort Pod，在节点剩余位置中调度。它与 HPC 领域基于预计运行时间的传统回填不是完全同一含义。

平台不要看到 Backfill 名称就承诺 Slurm 式时间窗口回填。使用目标版本文档和实验说明其实际任务集合。

### 4.7 Action 顺序本身是生产代码

`allocate, preempt, reclaim, backfill` 与 `reclaim, allocate...` 在同一 Session 中观察的 Usage 和候选不同。配置变更必须代码评审、影子回放和 Canary，不能把字符串当普通参数。

错误顺序可能导致无谓驱逐、机会丢失或公平偏移。

## 5. Plugin 怎样共同决定结果

Plugin 并非独立依次运行的黑盒列表。它们向 Session 注册不同函数，Action 在需要排序、过滤、评分、Ready 或 Victim 判断时调用。理解函数类型比背 Plugin 名称更重要。

### 5.1 Priority 建立 Queue、Job 与 Task 先后

Priority Plugin 比较 Job PriorityClass，Task 还结合自身 Priority、创建时间和 ID 等。Queue 也有 Priority 影响分配与回收。三层 Priority 需要平台治理，避免低 Queue 中的极高 Job 绕过组织边界。

Priority 决定先处理与可抢占，不创造资源。

### 5.2 Gang 保证最小成员提交

Gang Plugin 围绕 minAvailable 和 Ready 状态判断 Job 能否整体提交，并参与 Preempt／Reclaim 后能否满足最小运行。若只能暂存三个而 minAvailable 四，Statement 回滚。

这与前一篇 Gang Scheduling 一致，但这里重点是它如何嵌入 Session 并与 Queue 和 Victim 选择组合。

### 5.3 Conformance 保护系统任务

官方简介指出 Conformance 赋予 `kube-system` 任务更高保护，使其不被 Preempt。生产还需 Pod Priority、RBAC 与专用节点保护系统组件，不能只依赖一个 Plugin。

验证自定义系统 Namespace 是否同样需要策略，避免误以为名称自动受保护。

### 5.4 Predicates 执行硬可行性

## 写在最后

策略组合之外，放置结果还取决于资源品类与拓扑怎样被表达。下一篇：[拓扑感知调度、ResourceFlavor 与 DRA](/source/AI-Infra/4-AI平台工程/14-拓扑感知调度-ResourceFlavor与DRA)。