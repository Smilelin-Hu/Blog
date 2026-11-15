# 分布式 AI 工作负载 API：JobSet、LeaderWorkerSet 与失败语义

一个训练任务已经创建了 Leader，八个 Worker 却因为 GPU 不足停在 Pending；Leader 不断等待成员加入，同时持续占用 CPU、网络端口和队列额度。另一个推理组只坏了一张卡，平台只重建对应 Worker，剩余成员却仍保存旧的通信世界，最终所有请求都卡在集合通信里。两个现场看起来都是“有 Pod 没有跑起来”，但 Pod 数量并不能解释故障。平台没有表达一组进程怎样共同开始、怎样共同成功，以及故障时多大的范围必须一起恢复。

![分布式工作负载 API 与失败语义](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l17_01.png)

单个 Kubernetes Job 能够管理一类 Pod 的并行执行与完成，但大模型训练、分布式推理和 HPC 工作负载经常包含 Leader、Trainer、Evaluator、数据准备器等异构角色。角色之间不仅资源不同，还存在身份、依赖、网络、成功条件、失败传播和清理顺序。把它们硬塞进一个 Pod 会错误绑定调度与故障域；拆成互不相关的 Job 又会丢失整组生命周期。

本文的核心判断是：分布式工作负载 API 的价值，不是少写几份 YAML，而是把“协调一致性单元”变成控制器能够观察和收敛的对象。JobSet 适合多个 Job 模板组成的批处理或训练作业；LeaderWorkerSet 适合把一个 Leader 加若干 Worker 作为可复制的组，尤其适合多机推理。恢复范围由应用状态耦合决定，而不是由最先失败的 Pod 决定。无限重试也不是高可用，它只是把没有终止预算的问题延后。

技术基线锁定在 2026 年 8 月 22 日能够从官方资料核验的接口：Kubernetes Job 当前稳定语义、JobSet v0.12.0 所使用的 jobset.x-k8s.io/v1alpha2、LeaderWorkerSet v0.10 文档对应的 leaderworkerset.x-k8s.io/v1，以及 Kueue v0.19.0 集成文档。快速演进字段必须以目标集群实际安装的 CRD 为准；这里给出的机制判断可以迁移，字段名和 Feature Gate 不能脱离版本单独承诺。

## 1. 先确定需要被一起管理的最小单元

分布式系统首先要回答“哪些进程必须共享命运”。如果四个进程只读取同一份不可变数据，各自生成独立结果，某个进程失败通常只需重跑自己。如果八个 Rank 处于同一个同步集合通信世界，其中一个 Rank 消失会让其余 Rank 阻塞，八个 Rank 就构成更大的协调单元。若 Leader 持有成员列表、Epoch 和全局提交权，Leader 与所有 Worker 可能需要共同恢复。

这个最小单元不是固定等于 Pod、节点或 Job。它由应用协议决定。单 Pod 内多个容器共享调度和网络命名空间，天然形成很强的故障绑定；一个 Indexed Job 的不同索引可以有稳定身份，但仍共享一个 Pod 模板；一个 JobSet 可以包含多个角色和多个 Child Job；一个 LeaderWorkerSet 的一个 Replica 则是一组 Leader 与 Worker。平台先识别协议，再选对象，不能反过来看到某个 CRD 就把应用塞进去。

可以用四个问题识别一致性单元。第一，成员失联后，其余成员能否在不重新初始化的情况下继续产生正确结果。第二，新成员加入时，旧成员是否能安全更新世界大小和路由。第三，多个 Attempt 是否可能同时写同一个 Checkpoint 或模型 Manifest。第四，局部重启是否保留了足够的稳定身份、持久状态和幂等边界。只要其中一项答案是否定的，恢复范围就需要扩大。

平台设计文档应把“调度单元、启动单元、运行单元、恢复单元、发布单元”分别写出。它们可能相同，也可能不同。例如推理服务以一个 LeaderWorker 组作为调度和恢复单元，以多个组作为容量单元，以整个服务 Revision 作为发布单元。同步训练则可能以全部 Rank 作为启动和恢复单元，以 Checkpoint Attempt 作为存储提交单元。

## 2. 单个 Job 为什么不足以表达所有角色

Kubernetes Job 的核心职责是让一个 Pod 模板完成指定数量的成功执行。parallelism 控制最多并行运行多少 Pod，completions 控制需要多少成功完成，Indexed 模式为完成索引提供稳定编号。这个模型很适合参数扫描、数据分片处理和同构 Worker，但一个 Job 只有一个 Pod Template。

假设训练系统包含一个只需 CPU 的 Coordinator、两个每个请求四张 GPU 的 Trainer Job，以及一个使用另一镜像和两张 GPU 的 Evaluator。四类角色的镜像、命令、资源、探针和服务账户不同。若为了使用一个 Job 而把它们放进同一个 Pod，Coordinator 会被迫跟 Trainer 落到同一 GPU 节点，Evaluator 也不能在训练完成后再调度。任何容器级问题还会通过 Pod 重启策略影响其他容器。

如果改成四个独立 Job，资源表达正确了，但系统失去一个共同 Owner 和聚合状态。谁保证 Coordinator 就绪后 Trainer 才创建，谁在 Trainer 完成后启动 Evaluator，Leader 失败时是否删除仍在运行的 Worker，整个工作负载何时算成功，清理共享 PVC 时如何避免孤儿对象，这些都需要额外控制器或工作流层回答。

因此“一个 Job 能创建很多 Pod”与“一个 Job 能表达多角色工作负载”不是同一件事。前者描述同一模板的并行性，后者要求多模板编排、跨角色依赖、聚合成功和分层失败策略。JobSet 在 Job 之上补这层语义，而不是替代 Job 控制器内部已经成熟的重试、索引和终止能力。

## 3. Pod 重启、Job 重试和整组重启是三个层次

容器的 restartPolicy 由 kubelet 在 Pod 边界内执行。OnFailure 允许同一个 Pod 里的容器进程失败后重新启动；Never 让容器退出后由上层 Job 决定是否创建替代 Pod。它不会把一个已经进入 Failed 终态的 Job 重新变成新的 Job，也不会自动协调其他角色。

Job 的 backoffLimit 限制 Pod 失败重试。官方文档说明默认值通常为六；失败 Pod 的重建采用指数退避，延迟从十秒逐步增加并有上限。activeDeadlineSeconds 是跨重试的总运行时限，而且优先于 backoffLimit。达到这些终止条件后 Job 进入失败流程，需要外部控制器或用户决定是否重新创建 Job。

JobSet 的 RestartJob 会重建一个失败的 Child Job，RestartJobSet 会重建整组 Child Job。它们发生在 Job 对象层，而不是容器层。LeaderWorkerSet 的组级策略又发生在 Pod 组层，可以因组内成员重启而重建整个组。相同的“restart”字样对应不同 Owner、不同对象 UID 和不同状态保留范围。

诊断时必须记录是容器 restartCount 增加、Job 新建了替代 Pod、JobSet 重新创建了 Child Job，还是 LWS 重建了一个组。只看 Pod 名称或界面上的“重启次数”会混淆责任。平台事件应同时保留对象层级、Owner UID、Attempt、动作原因和是否计入全局预算。

## 4. Indexed Job 提供身份，但不自动提供协调

Indexed Job 把每个完成单元编号为零到 completions 减一。Pod 能够读取 JOB_COMPLETION_INDEX，状态里记录 completedIndexes 和 failedIndexes。backoffLimitPerIndex 允许分别限制每个索引的失败次数；当前官方文档将这一能力标为自 Kubernetes v1.33 起稳定。它非常适合分片处理，因为索引可以映射到稳定数据分片。

稳定索引并不等于成员发现和 Gang 启动。八个索引可能依次被调度，前四个已经占用 GPU，后四个因资源不足长期 Pending。若应用要求八个 Rank 一起初始化，Indexed Job 本身不会保证原子准入。还需要 Kueue、支持 Gang 的调度路径或应用级容错。

每索引失败也不表示整体能部分成功。官方语义是：当所有索引处理结束后，只要存在失败索引，整个 Job 仍可能被标记 Failed；maxFailedIndexes 可以在失败索引超过阈值时终止剩余 Pod。successPolicy 则允许基于成功索引提前判定成功，但必须与业务结果一致。

将索引直接当作训练 Rank 时，还要考虑重建后的 Epoch。新 Pod 继续拥有相同索引，却不是同一个进程实例。其他 Rank 若只按索引识别而不校验 Attempt 或 Rendezvous 代次，可能接受一个旧世界之外的新成员。稳定逻辑身份需要再结合工作负载 UID、重启代次和应用握手。

## 5. Job 的失败条件先于上层恢复策略

JobSet 只会根据 Child Job 可见的状态与 Reason 执行策略，因此下层 Job 必须准确分类失败。backoffLimit 耗尽通常产生 BackoffLimitExceeded；activeDeadlineSeconds 产生 DeadlineExceeded；PodFailurePolicy 可以把特定退出码或 Pod Condition 转换成 FailJob、Ignore、Count 或 Indexed Job 可用的 FailIndex。

PodFailurePolicy 规则按顺序求值，第一个匹配项生效。官方文档要求使用该策略时 Pod 模板的 restartPolicy 设为 Never。退出码四十二可以代表不可恢复配置错误并直接 FailJob；带 DisruptionTarget Condition 的基础设施扰动可以 Ignore，不计入普通失败预算。没有规则匹配时采用默认处理。

分类质量决定上层动作质量。如果训练脚本把数据校验失败、CUDA OOM、网络超时和节点驱逐都返回同一个退出码，JobSet 无法可靠选择 FailJobSet 或 RestartJobSet。平台需要建立退出码、结构化终止消息、Pod Condition 与业务 Reason 之间的合同，并通过反例测试验证。

不能只依赖日志文本做自动恢复。日志可能被截断、本地化、改变格式或在进程崩溃前未刷出。结构化 Reason 应优先，消息正则只用于补充，并锁定 RE2 语法与长度边界。任何基于消息的规则变化都要进入兼容测试。

## 6. SuccessPolicy 不能把控制面成功当成业务成功

默认情况下，Job 在成功 Pod 数量达到 completions 时完成。Indexed Job 的 successPolicy 允许指定成功索引或成功数量，满足某条规则后进入成功流程并终止剩余 Pod。官方文档同时说明，当成功策略与 backoffLimit、PodFailurePolicy 等终止策略冲突时，已经满足的终止策略优先。

JobSet 也有 SuccessPolicy，但目标是 ReplicatedJob 角色而不是单个 Pod 索引。operator 可以选择 All 或 Any，并以 targetReplicatedJobs 限定目标。例如训练角色完成后即可把整个 JobSet 视为成功，而持续运行的日志上传辅助角色不再阻止终态。

这只证明控制器观察到目标 Job 完成。真实业务可能还要求 Checkpoint 写入完毕、模型 Manifest 原子发布、评测摘要存在、输出 Digest 可读取。若 Trainer 先退出零，Sidecar 稍后才把文件传到对象存储，而 SuccessPolicy 立即终止其余角色，平台会得到一个控制面成功、制品却不完整的运行。

正确做法是把业务提交纳入成功协议。训练进程先写 Attempt 目录，校验后通过条件写发布 Manifest，最后才退出零；或由独立 Committer 角色验证制品并作为 SuccessPolicy 目标。控制面 Condition、产物证据和注册状态三者一致后，平台状态才进入 Succeeded。

## 7. Job 终态并不意味着所有 Pod 已经消失

Kubernetes 当前 Job 文档区分触发终止的 FailureTarget 或 SuccessCriteriaMet 与最终 Failed 或 Complete Condition。较新版本会等待 Job Pod 全部终止后再添加终态 Condition。平台不能假设看到“成功条件已满足”的瞬间，所有旧 Pod 都停止写数据。

清理窗口影响下一次 Attempt。若新 JobSet 马上使用相同输出目录，旧 Pod 仍在 Termination Grace Period 内，就可能形成双写。训练容器要响应 SIGTERM、停止领取新工作、完成或放弃临界写入，并在超时前退出。存储层还要用 Attempt 和 Fence Token 防止越代提交。

Job 默认不会自动删除完成对象和 Pod，以便保留状态和日志。ttlSecondsAfterFinished 可以设置清理时间。JobSet 也提供同名用途的 TTL 字段，但清理的是 JobSet 及其依赖对象，且仍遵守 Owner、Finalizer 和级联删除语义。TTL 不是数据保留策略，日志、制品和审计需要独立生命周期。

验收脚本应分别等待触发 Condition、所有活跃 Pod 归零、最终 Condition、制品提交与资源清理。只执行一次 kubectl wait 而没有说明等待的 Condition，会把多个阶段压成一个不可诊断的“完成”。

## 8. JobSet 把多个 Job 放进同一对象树

JobSet 的 spec.replicatedJobs 包含多个 ReplicatedJob 声明。每个条目有唯一 name、一个 JobTemplate 和 replicas。控制器为每个副本创建 Child Job，Child Job 再按自己的 parallelism 与 completions 创建 Pod。对象树因此包含 JobSet、ReplicatedJob 声明、实际 Job 和 Pod 四个层级。

ReplicatedJob 不是独立 CRD 对象，而是 JobSet Spec 中的一段声明。它的 replicas 表示要基于该模板创建多少个 Job，不等于每个 Job 内部的 Pod 数量。总 Pod 需求需要同时乘以 replicas 与 Job 模板的并行度，并考虑 completions 对峰值并行的限制。

假设 trainer 的 replicas 为二，每个 Child Job 的 parallelism 与 completions 都是四，那么 Trainer 峰值是八个 Pod。再加一个 Leader 和两个 Evaluator，整个 JobSet 的峰值是十一 Pod。若每个 Trainer Pod 请求一张 GPU、Evaluator 各请求一张 GPU，准入需求是十张 GPU，而不是看到“replicas: 2”就记为两张。

平台应从实际 Pod Template 聚合 CPU、内存、GPU、临时存储、DRA Claim、拓扑与优先级，而不是依赖用户额外填写一个总量字段。用户声明与计算结果可以对照；不一致时以控制器可执行的模板为准并拒绝模糊请求。

## 9. OwnerReference 是清理关系，标签是查询关系

JobSet 创建的 Child Job 带有指向 JobSet 的 OwnerReference，Job 创建的 Pod 再指向 Job。Kubernetes 垃圾收集器使用 Owner 关系决定级联删除。标签和选择器便于控制器与观察系统查找对象，但标签不能替代所有权。

这一区别在重启时尤其重要。JobSet 重新创建 Child Job 后，名称可能体现相同角色和索引，UID 却已经变化。观察系统如果只按 name 聚合，会把旧 Attempt 的终止事件与新 Attempt 的运行指标混在一起。正确主键至少包含 Namespace、Kind、UID 和控制器代次。

跨 Namespace OwnerReference 按 Kubernetes 设计不被允许。JobSet、Child Job 和 Pod 必须在相同 Namespace 形成有效所有权。平台若把共享协调器放在另一个 Namespace，不能用 OwnerReference 期待自动清理，需要明确的外部 Owner、Finalizer 或独立生命周期。

删除策略也要显式。前台级联删除让 Owner 保留到需要阻塞删除的依赖项清理完成，后台删除先移除 Owner 再异步清理依赖。故障恢复中若必须确认旧 Worker 全部停止后才能创建新 Attempt，应使用可验证的清理屏障，而不是假定后台回收已经完成。

## 10. 名称稳定与实例稳定不能混为一谈

分布式应用需要稳定名称发现成员，但稳定 DNS 并不保证背后仍是同一个实例。Pod 重建后可以继续使用按角色和索引生成的主机名，IP、UID、进程状态和本地缓存却已经改变。协议必须区分逻辑身份与物理实例。

JobSet 为 Job 与 Pod 传播 JobSet 名称、UID、ReplicatedJob 名称和索引等标签。观察系统使用 JobSet UID 区分同名重建，使用角色与索引聚合逻辑位置，使用 Pod UID 定位具体实例。应用握手再携带 Attempt 或 Epoch，拒绝旧代次成员。

仅靠 Pod 名称实现幂等也不安全。删除后重新创建同名对象会获得新 UID，旧客户端缓存可能仍指向原 IP。DNS TTL、Endpoint 更新和连接重试都会造成短暂交叠。Leader 必须用租约或存储 Fence Token 保护单写，而不能认为“名字唯一”就没有 Split Brain。

平台在日志中同时输出 logical_member_id 与 instance_uid。前者回答“哪个 Rank”，后者回答“哪次实例”。故障统计按逻辑成员看热点，事故追踪按实例看时间线，两种维度都不能丢失。

## 11. JobSet 网络解决发现，不证明服务就绪

JobSet 可以创建并管理 Headless Service，为 Pod 提供基于 JobSet、ReplicatedJob、Job 索引和 Pod 索引的稳定主机名。spec.network 可以控制是否启用 DNS 主机名、Subdomain 以及是否在 Pod 未 Ready 时发布地址。当前 API 参考说明 publishNotReadyAddresses 默认倾向于 True，具体行为仍应由目标 CRD 验证。

提前发布未 Ready 地址适合某些需要所有成员互相发现后才能完成初始化的框架，但它也会让 DNS 可解析早于业务可用。Worker 解析到 Leader 地址并不表示 Leader 已经加载 Checkpoint、监听端口、取得租约或准备接收 Rendezvous。

如果关闭未 Ready 地址发布，Leader 的 Readiness 又依赖 Worker 连接，就可能形成环：Worker 等待 DNS，DNS 等待 Leader Ready，Leader 等待 Worker。启动协议要明确哪个条件可以无依赖成立。常见做法是 DNS 允许发现，应用连接返回明确的 NotReady 或 Epoch，再由业务探针控制真正准入。

网络设计还要覆盖 NetworkPolicy、Service DNS、端口和跨节点 MTU。控制器创建 Headless Service 不意味着 Namespace 网络策略允许通信，也不意味着 RDMA 接口可达。实验必须将名称解析、TCP 握手、应用协议和集合通信分开验证。

## 12. Coordinator 字段提供端点，不替代 Leader 选举

JobSet 的 spec.coordinator 能够指定某个 ReplicatedJob、Job Index 和 Pod Index 作为协调 Pod。控制器把该 Pod 的稳定网络 Endpoint 通过 jobset.sigs.k8s.io/coordinator 标签与注解传播到相关 Job 和 Pod，应用可以通过 Downward API 读取，避免每个镜像都自行拼接名称。

Coordinator 是声明式指定，不是基于健康动态选举。被指定 Pod 失败时，JobSet 根据 FailurePolicy 决定局部或整组恢复；它不会自动把另一个 Worker 晋升为新 Leader。应用若需要 Leader 选举，仍需 Lease、外部一致存储或框架自身协议。

指定端点也不建立写入权。旧 Coordinator 与新 Coordinator 在网络分区、终止延迟或控制器恢复期间可能短暂并存。对 Checkpoint、队列消费和模型发布等副作用，需要 Fence Token、版本条件写或单写服务。连接到正确 DNS 只是第一步。

在平台模板中，Coordinator 字段适合稳定引导地址。应用启动后通过该地址获取成员列表与当前 Epoch；每次请求都校验 Epoch。若模板只把 Endpoint 注入环境变量却没有就绪、超时和防脑裂机制，评审状态应是“发现已配置”，而不是“高可用已完成”。

## 13. DependsOn 表达创建依赖，不是任意工作流

JobSet v1alpha2 的 ReplicatedJob 可以通过 dependsOn 引用前置角色，并选择 Ready 或 Complete 状态。当前 API 参考说明只支持单个依赖项，而且第一个 ReplicatedJob 不能使用 DependsOn；DependsOn 与已弃用的 StartupPolicy 互斥。模板必须按实际 CRD 做 Server-Side Dry Run 验证。

Ready 依赖适合 Leader 先建立服务，再创建 Trainer。Complete 依赖适合数据准备 Job 完成后再启动训练，或训练完成后启动评估。它让控制器避免过早创建 Child Job，从而减少无意义的 Pending 和启动竞态。

依赖满足的是 JobSet 定义的 ReplicatedJob 状态。Ready 通常来自 Child Job 中就绪 Pod 数量达到期望值，不一定包含业务自定义握手。若 Leader 探针只检查进程存活，Trainer 仍可能在模型加载前启动。探针必须与依赖承诺一致。

DependsOn 不是通用 DAG 引擎。只支持单依赖意味着复杂扇入、条件分支、缓存、重试编排和制品传递更适合 Kubeflow Pipelines、Argo Workflows 或专门控制器。JobSet 负责一个紧密工作负载的角色协调，不能承担完整 ML 流水线。

## 14. 依赖图必须在准入前验证

任何依赖都可能形成永久等待。角色 A 等待 B Ready，B 又等待 A Complete，控制器即使没有创建错误对象，工作负载也永远不会前进。Admission Webhook 或平台编译器应在提交前检查引用存在、顺序合法、无环、状态值受版本支持。

还要检查资源死锁。Leader 先启动并占用一张 GPU，Trainer 需要同机架八张 GPU，但剩余节点无法组成八卡形状；如果整组没有 Kueue 原子准入，Leader 会一直持有资源。依赖正确不等于资源可达。

启动超时需要归属明确。等待 Leader Ready 超过十分钟，是 Job 失败、JobSet 失败、释放 Kueue 配额，还是继续排队？没有 Deadline 的 Pending 对象会占用运维注意力，也可能持有已准入资源。平台应分别设置排队期限、启动期限与业务运行期限。

回滚还要处理已经创建的前置角色。如果 Trainer 启动失败，持续运行的 Leader 是否保留等待重试，取决于恢复策略。紧耦合训练通常整组重建；外部无状态协调服务可以继续。默认答案必须由应用合同给出，不能交给值班人员临时猜测。

## 15. StartupPolicy 弃用意味着模板需要迁移

旧 JobSet 模板常见 startupPolicy.startupPolicyOrder 为 InOrder 或 AnyOrder。当前 v1alpha2 API 参考已经把 StartupPolicy 标记为 Deprecated，并建议使用 DependsOn。Deprecated 不表示立刻不可用，但它说明新模板不应继续把该字段作为长期接口。

迁移不能只做字段替换。InOrder 按 replicatedJobs 列表顺序推进，而 DependsOn 把关系写在目标角色上并区分 Ready 与 Complete。平台需要先明确旧顺序依赖的真实业务条件，再生成新依赖。若旧模板只是偶然依赖列表顺序，迁移正好暴露隐含合同。

升级流程先导出集群 CRD Schema，再对所有模板执行 Server-Side Dry Run，检查弃用告警和默认值变化。随后在隔离 Namespace 创建最小 JobSet，观察 Child Job 创建顺序、Condition 和挂起恢复。只升级 Controller 镜像而不验证存量对象，会把兼容问题留到生产重启时。

模板目录记录最低与最高验证版本、字段代次和迁移器版本。旧模板可以在兼容窗口内读取，但新提交统一编译到当前规范。平台页面不向用户暴露两个等价开关，避免同一意图生成互斥字段。

## 16. SuccessPolicy 的 All 与 Any 要从业务成果反推

JobSet 的 SuccessPolicy 可以针对若干 ReplicatedJob 选择 All 或 Any。目标列表为空时，API 语义可能覆盖全部 ReplicatedJob；生产模板应显式列出关键角色，避免新增辅助角色后悄悄改变完成条件。

All 适合所有指定角色都必须完成的情况。例如数据生成的两个 Shard 角色都要发布输出，缺一不可。Any 适合多个等价候选，只要任意一个成功就取得有效成果，例如相同输入的冗余搜索尝试。但 Any 不适合同步训练 Rank，因为一个 Rank 成功退出并不代表全局模型有效。

提前成功会触发其他 Child Job 终止。选择目标前要问：剩余角色被 SIGTERM 时会不会留下半写文件，是否需要上传日志，是否仍承担 Committer 职责。辅助角色若必须完成清理，就不能简单排除；可以把清理转移到 Finalizer、独立控制器或外部存储协议。

平台验收不仅检查 JobSet terminalState，还检查目标角色、被终止角色、制品 Manifest 和清理事件。成功策略改变属于公共合同变更，应更新实验和发布说明，不能只改一行 YAML。

## 17. FailurePolicy 是有序决策表

JobSet FailurePolicy 包含 maxRestarts、可选 restartStrategy 和一组 Rules。每个 Child Job 失败时，控制器按顺序求值，只执行第一个匹配规则。没有规则匹配时，当前官方文档规定默认执行 RestartJobSet，并计入 maxRestarts。

规则可按 targetReplicatedJobs、onJobFailureReasons 和 onJobFailureMessagePatterns 筛选。Reason 列表内部只需某项匹配，消息模式使用 RE2 正则；当同时配置 Reason 与消息要求时，需要两类条件共同满足。空列表通常表示不限制该维度。

顺序错误会遮挡精细策略。若第一条规则对所有 Trainer 失败执行 RestartJobSet，后面针对“配置缺失”执行 FailJobSet 的规则永远不会运行。应先放确定性、窄范围、不可恢复条件，再放基础设施中断和兜底规则。

规则评审需要样例驱动。给每条规则至少一个正例和一个近似反例，确认角色、Reason、消息边界与动作。升级后重放这些事件，避免 Controller 或 Job Reason 变化导致自动恢复策略漂移。

## 18. 五种失败动作对应不同风险

FailJobSet 立即把整组标记失败，适合权限拒绝、无效配置、数据校验失败和明确的软件错误。继续重试只会重复花费，因此快速失败反而提高可用性：用户更早得到可行动 Reason，队列更早释放资源。

RestartJobSet 重建全部 Child Job，并把动作计入 maxRestarts。它适合 Leader 故障、全局通信世界损坏或 Checkpoint 边界明确的同步训练。代价是健康成员也会退出，未提交计算被丢弃，启动和数据预热重新发生。

RestartJob 只重建失败 Child Job。JobSet 官方文档说明采用这类动作时每个 ReplicatedJob 最多支持 1024 个副本。它适合 Evaluator、独立 Shard 或真正具备成员替换协议的 Worker；若应用没有局部恢复能力，节省的重启成本会换成更隐蔽的挂起。

RestartJobSetAndIgnoreMaxRestarts 与 RestartJobAndIgnoreMaxRestarts 不增加对应最大重启计数。它们适合被认定为外部维护或可无限容忍的短暂事件，但“忽略计数”会移除一个重要保险丝。必须另有 Deadline、成本、事件频率和人工停止条件。

## 19. maxRestarts 不是完整的重试预算

maxRestarts 只统计符合特定动作的 JobSet 或 Job 重建次数。忽略上限的动作不计数，容器内部重启、应用自行重连和某些外部重建也可能不进入该字段。一个工作负载因此可以在 maxRestarts 看似很小的情况下消耗很长时间和大量 GPU。

生产预算至少包含四维：最大整组重启次数、最大局部重启次数、最大墙钟时间和最大资源成本。再加入相同 Reason 的速率限制，避免十分钟内连续重启把镜像仓库、存储和控制面一起压垮。

预算达到后要进入明确终态，而不是换一个控制器继续重试。平台保存最后失败角色、Reason、Attempt、最近可用 Checkpoint 和已花费额度。用户重新提交会获得新 runID 或显式 Resume 关系，审计能够区分自动恢复与人工再运行。

重试预算与 SLO 相连。在线推理组也许允许单组快速重建三次，但如果可用容量已经低于最低副本，就要优先扩容或切流；离线训练可以容忍更长恢复，却受截止时间和预算约束。一个固定整数不能覆盖所有工作负载类别。

## 20. Message Pattern 只能作为受控补充

JobSet 支持根据 Job 失败消息的正则模式选择规则，这为尚未提供结构化 Reason 的框架错误提供了桥梁。例如特定 Admission 或应用包装器可能把“不可恢复配置”写入 Job Condition Message，平台据此 FailJobSet。

自由文本很脆弱。组件升级会修改措辞，消息包含动态对象名，国际化或截断会改变匹配。正则过宽还可能把网络瞬断误判成配置错误。模式应锚定稳定前缀或机器生成代码，不匹配用户任意日志。

安全上要限制正则复杂度和来源。官方 API 使用 RE2 语法，避免某些灾难性回溯，但模板仍需限制长度、数量和权限。普通租户不应通过宽泛模式绕过组织规定的重试与成本策略。

最佳演进路径是把已证明稳定的消息分类上移到结构化退出码、PodFailurePolicy 或自定义 Condition。消息规则记录引入原因和移除条件；长期存在却无人维护的正则是事故债务。

## 21. RestartJob 是否安全取决于输出幂等

局部重启不只关心通信，还关心副作用。失败 Worker 若已写出部分 Shard，新 Child Job 使用同一路径重跑，可能重复追加、覆盖完整结果或与迟到旧实例并发。即使其他成员完全独立，输出不幂等也不能安全 RestartJob。

一种可靠方式是按 runID、role、jobIndex 和 attempt 写隔离目录。任务完成后生成包含 Digest、数量和 Schema 的 Manifest，再由原子重命名或条件写发布稳定指针。重启产生新 Attempt，旧 Attempt 不会覆盖新结果。

## 写在最后

工作负载 API 之上，还需要一套面向多用户 ML 生命周期的平台组件。下一篇：[Kubeflow 平台组件、Profiles 与多用户隔离](/source/AI-Infra/4-AI平台工程/18-Kubeflow平台组件-Profiles与多用户隔离)。