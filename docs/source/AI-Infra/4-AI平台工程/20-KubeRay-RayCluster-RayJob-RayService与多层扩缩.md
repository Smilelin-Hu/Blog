# KubeRay：RayCluster、RayJob、RayService 与多层扩缩

一个团队把 Ray 当成“能在 Kubernetes 里启动的 Python 框架”，于是长期保留一套共享 RayCluster。白天的交互任务与夜间批处理共享 Head，某次驱动提交了数十万个对象引用，GCS 压力升高，所有团队一起受到影响。另一个团队为每次推理发布都直接改 RayCluster 镜像，发现 Ray 并不原生提供集群内滚动升级，只能在旧集群停机与新集群启动之间选择。第三个团队开启了 Ray 工作节点自动扩缩，却没有配置 Kubernetes 节点池扩缩，Ray Autoscaler 不断请求新 Worker Pod，而 Pod 因为物理 GPU 节点不存在持续 Pending。三个场景都不是 Ray 算子写错，而是平台没有把应用生命周期、Ray 集群生命周期与 Kubernetes 容量生命周期分开治理。

![KubeRay 三种资源与产品语义](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l20_01.png)

KubeRay 提供 Kubernetes 原生控制面，把 RayCluster、RayJob 和 RayService 三种稳定资源映射到不同产品语义。RayCluster 适合被复用的开发或常驻计算集群；RayJob 把一次批处理应用与专属集群、提交器和清理策略绑定；RayService 把 Ray 集群与 Ray Serve 应用组合起来，提供应用原地更新和集群级无中断切换。KubeRay 1.6 还引入了 RayCronJob，但它是默认关闭的 Alpha 能力，不能与三个稳定资源放在同一承诺等级。

本文以 2026 年 8 月 27 日核验的官方一手资料为事实基线。KubeRay 稳定版本采用 v1.7.0，Ray 稳定版本采用 2.58.0；KubeRay 的 v1 API 具有稳定兼容承诺，但 History Server 在 v1.7 为 Beta，增量升级为默认启用的 Beta，自动 Sidecar、mTLS 与 NetworkPolicy 等能力仍含 Alpha 边界，具体行为必须按发行标签和目标 CRD 验证。这里会把 Ray 任务、Actor、Serve 副本、Ray 工作 Pod、Kubernetes 节点、队列准入、Head 与 GCS 状态、服务切换和资源清理放到同一条可观察链路中，并明确模拟验证与真实集群验证的边界。

## 1. Ray 与 Kubernetes 是两个调度系统

![两层调度与多层扩缩](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l20_02.png)

Kubernetes 调度器把 Pod 放到节点上，处理容器资源请求、节点标签、污点、亲和性、拓扑与设备分配。Ray 调度器位于 Ray 集群内部，把任务和 Actor 放到 Ray 节点上，依据逻辑 CPU、GPU、自定义资源、放置组与本地性作出决定。一个 Ray 工作 Pod 通常对应一个 Ray 节点，但 Ray 节点内部还可以承载多个 Python 工作进程、任务和 Actor。

平台若只看 Kubernetes，会知道 Pod 申请了几张 GPU，却不知道哪些 Actor 正在排队；若只看 Ray，会知道逻辑资源不足，却不知道新 Pod 为何无法被集群调度。工程分析必须沿着“应用需求—Ray 逻辑资源—工作 Pod—物理节点”逐层定位，不能把任意一层的 Pending 统称为资源不够。

## 2. KubeRay 是两个控制面的适配层

KubeRay Operator 观察 ray.io API 资源，创建 Head Pod、Worker Pod、Service、提交器 Job 及关联对象，并把底层状态汇总到高层资源。它不是 Ray 调度器的替代品，也不是 Kubernetes 调度器的替代品；它负责把声明式 Kubernetes 对象转换成 Ray 集群生命周期，并持续协调期望状态与实际状态。

控制器的价值在于幂等协调。用户提交一个 RayCluster 后，Operator 不只是执行一次脚本，而是持续观察 Pod、配置与状态；对象删除时通过所有权关系回收资源；规格变化时按照对应资源的升级语义处理。平台因此可以用 GitOps、准入策略、RBAC、事件和 Condition 管理 Ray，而不是维护一套无法审计的远程 Shell 脚本。

## 3. 三个稳定 CRD 分别表达三类产品

官方 KubeRay 文档列出三个稳定核心 CRD。RayCluster 管理一个 Ray 集群的创建、删除、扩缩和故障相关生命周期；RayJob 在集群就绪后提交一个 Ray 应用，并可在任务结束后删除关联集群；RayService 组合 RayCluster 与 Ray Serve 应用，面向持续在线服务提供应用更新、集群升级和高可用能力。

选型不能根据 YAML 长短决定。需要长时间复用同一集群、容忍集群重建停机且对启动延迟敏感时，RayCluster 更直接；每次运行需要独立依赖、独立版本、明确终态和自动回收时，RayJob 更合适；入口流量必须持续服务且需要变更 Serve 应用或底层集群时，应使用 RayService。

## 4. RayCluster 适合显式拥有集群生命周期

RayCluster 声明 Head 与一个或多个 Worker Group。Operator 据此生成 Head Service、Head Pod 和 Worker Pods。用户可以通过 Ray Jobs API、Ray Client 或在集群内运行驱动连接 Head，再把多个应用提交到同一个集群。复用减少了镜像拉取、Head 启动和工作节点预热带来的延迟。

复用同时扩大故障域。不同作业共享 GCS、对象存储、Head 网络、Ray Dashboard 和逻辑资源，某个应用的对象爆炸、日志洪峰或命名资源占用会影响其他应用。平台必须定义租户边界、并发上限、资源命名、提交认证、空闲回收和维护窗口，不能把“共享集群”误解为没有治理成本的公共池。

## 5. RayJob 适合一次运行一个合同

RayJob 管理两个关键部分：一个 RayCluster 资源，以及用于执行 ray job submit 的 Kubernetes Job。Operator 先创建 RayCluster，等待集群达到可提交状态，再启动提交器把入口命令交给 Ray Jobs API。高层 RayJob 状态串联了集群准备、作业提交、运行、成功或失败与清理。

这种隔离允许每个作业固定 Ray 版本、镜像、依赖、Worker Group 和队列标签。运行结束后可以按策略保留 Head 用于诊断、先删除 Worker 降低成本、延迟删除整集群，或删除 RayJob 自身。代价是每次运行都承担集群启动时延，平台需要通过镜像预拉取、依赖内置、节点暖池和合理 TTL 平衡成本与诊断窗口。

## 6. RayService 是在线服务控制面

RayService 的规格同时包含 Ray 集群配置和 Serve 应用配置。KubeRay 创建受管 RayCluster，将 Serve 配置提交到集群，并创建稳定的 Head Service 与 Serve Service。客户端访问的是稳定 Kubernetes Service，而不是直接绑定某个短生命周期 Pod 或集群名字。

应用级配置变化可以在活动集群内更新，例如路由、部署参数和副本配置；集群级变化会触发新集群路径，例如 Ray 镜像、工作组或底层运行环境变化。平台要在变更评审时先判断修改属于应用面还是集群面，因为两者的容量、回滚与风险完全不同。

## 7. RayCronJob 必须按 Alpha 能力管理

KubeRay v1.6 引入 RayCronJob，用标准 Cron 表达式周期创建 RayJob，适合定时训练、批处理和周期推理。官方发布说明明确标记该能力为 Alpha，并且默认关闭，需要在 Operator 上显式启用 RayCronJob 特性开关。稳定入门文档仍以三个核心 CRD 为主，开发分支才把 RayCronJob 加入选型列表。

平台可以在受控试验集群评估它，但不应让门户在未开启特性时生成资源，更不能把 Alpha Schema 当成长周期兼容合同。生产周期任务也可以由稳定的工作流调度器或 Kubernetes CronJob 创建 RayJob；选择依据应包括错过调度、并发策略、时区、暂停、历史保留、升级和审计需求。

## 8. Head Pod 不是普通主节点

Head 运行 GCS、Ray Dashboard、作业服务和其他控制组件，并且自身也可参与任务调度。它维护集群成员、对象位置、Actor 与资源等关键元数据。Head CPU 或内存不足可能表现为任务调度延迟、Dashboard 超时、提交失败或整个集群不稳定，而不是单纯少一个计算 Worker。

因此 Head 需要独立容量模型和节点放置策略。交互与大规模批任务的 Head 规格不应完全相同；在线服务还要考虑 Serve 控制器、代理和观测负载。平台应限制普通任务占用 Head 资源，给控制面保留 CPU 与内存，并为 Head 配置合适的优先级、反亲和、持久状态和重启策略。

## 9. Worker Group 表达异构计算池

一个 RayCluster 可以包含多个 Worker Group，每组有独立镜像、资源、最小与最大副本、节点选择、容忍度和启动参数。平台可用不同组表达 CPU 预处理、通用 GPU、特定 GPU 型号或高内存节点，Ray 再通过逻辑资源和调度策略把任务放到合适组。

异构不应只靠组名。容器资源请求必须与 Ray 公布的逻辑资源一致，GPU 型号等能力应通过节点标签、ResourceFlavor 或自定义资源明确绑定。若 Ray 认为节点有某种资源而 Kubernetes 并未保证对应硬件，任务会成功调度到错误 Pod；反过来，Pod 拿到 GPU 但 Ray 资源声明缺失，应用会长时间等待不存在的逻辑资源。

## 10. Head Service 建立稳定发现入口

KubeRay 为 RayCluster 创建名为“集群名-head-svc”的 Service。官方配置文档列出常用端口：Ray Client 通常使用 10001，Dashboard 使用 8265，GCS 使用 6379，Ray Serve 使用 8000，Prometheus 指标使用 8080。集群内客户端可通过 Service DNS 连接 Head，不应依赖 Pod IP。

端口存在不代表应该对公网开放。Dashboard、Ray Client 与 Jobs API 都具有强大控制能力，必须放在受信网络、认证和 TLS 之后。入口 Service 还需要 NetworkPolicy 限制来源；调试时使用受控端口转发比创建公开 LoadBalancer 更安全。任何临时暴露都要有明确到期和审计。

## 11. Ray 资源是逻辑承诺

Ray 的 num_cpus、num_gpus 与自定义资源用于调度，并不等价于操作系统强隔离。任务申请一个逻辑 CPU 主要表示并发配额，真实线程仍可能超额使用；GPU 通常通过可见设备环境变量隔离，但最终还依赖 Kubernetes 设备插件与容器运行时。逻辑资源是调度合同，不是替代 cgroup 的安全边界。

平台应同时校验 Pod 资源与 Ray 资源。CPU、内存和 GPU 请求决定 Kubernetes 能否放置 Pod；Ray 启动参数决定任务能否在 Pod 内被放置。两层数值不一致会造成过度承诺或闲置。容量报告要分别展示物理已分配、Ray 逻辑总量、Ray 逻辑已用与应用排队需求。

## 12. 多层扩缩从应用需求开始

在线 Serve 应用可以依据排队和进行中请求调整部署副本；普通 Ray 任务或 Actor 会产生逻辑资源需求；Ray Autoscaler 观察这些需求并调整 Worker Group 副本；Kubernetes 看到新增 Worker Pod 后，再由节点自动扩缩器决定是否增加物理节点。每层都有自己的控制循环、采样、冷却和失败语义。

把三层合并成一个“自动扩缩开关”会隐藏关键延迟。Serve 副本创建需要 Actor 放置，Worker Pod 创建需要镜像与 Ray 加入集群，节点创建还需要云 API 与驱动初始化。端到端突发响应时间是这些阶段的串联，平台必须为每层设置上限、超时和预热，而不是只调整一个副本数。

## 13. 第一层是 Serve 部署副本或 Ray Actor

Ray Serve 根据部署配置创建 Replica Actor。自动扩缩策略可以根据运行中与排队请求估算副本需求，并受到最小、副本上限、目标并发和冷却等参数约束。普通 Ray 应用也会通过 Actor、任务和放置组表达资源请求，这些请求进入 Ray 调度队列。

这一层回答“应用需要多少执行单元”，不回答“集群应有多少 Pod”。一个 Worker Pod 可能容纳多个 CPU Replica，也可能一张 GPU 只能承载一个大模型 Replica。平台需要把每个 Replica 的 CPU、GPU、内存和对象存储需求写清楚，否则副本数与 Worker 数之间无法建立可靠关系。

## 14. 第二层是 Ray Worker Pod

启用 KubeRay 的 in-tree autoscaling 后，Autoscaler 通常作为 Head Pod 中的边车运行。它收集 Ray 集群的逻辑资源需求，计算各 Worker Group 目标副本，更新 RayCluster 规格中的副本数；KubeRay Operator 再创建或删除 Worker Pod。扩容路径由 Ray 需求驱动，不是直接读取 GPU 利用率。

缩容时 Autoscaler 识别空闲 Ray 节点，更新副本并指定需要删除的 Worker，Operator 回收对应 Pod。Actor、对象引用、放置组和空闲超时会影响节点能否安全缩容。平台不能仅靠 Kubernetes 平均利用率强行删除 Pod，否则可能破坏有状态 Actor 或仍被引用的对象。

## 15. 第三层是 Kubernetes 物理节点

当新增 Worker Pod 找不到满足资源、标签、拓扑或设备要求的节点时，它进入 Pending。节点自动扩缩器读取这些不可调度 Pod，为匹配的节点池增加机器；机器启动、加入集群、安装驱动和设备插件后，Kubernetes 才能真正调度 Pod。KubeRay 不会替平台自动配置云节点池。

GPU 池的 min、max、实例类型、配额、可用区和扩容策略必须与 Worker Group 一致。若 Ray Worker 最大副本为二十，而节点池最多只能提供四张 GPU，Ray 会持续看到未满足需求。平台应把物理容量上限反馈到准入和 Autoscaler 配置，避免控制循环长期追逐不可能目标。

## 16. 三层控制循环需要阻尼

Serve 扩容、Ray Pod 扩容和节点扩容都有观测延迟。如果 Serve 迅速把副本从一扩到十，Ray 立即请求十个 Worker，而节点池需要十分钟才就绪，期间请求队列可能继续上升并触发更多扩容。节点终于到达时，流量已经下降，三层又同时缩容，容易形成振荡。

阻尼来自最小暖容量、上下行冷却、最大变化速率、排队上限、超时与分层 SLO。在线服务可以保留少量热 Worker；GPU 节点池可以保留安全余量；批任务则可以接受更长等待换取接近零的空闲成本。参数必须从实测启动分位数和业务到达分布推导，而不是照抄示例。

## 17. Ray Autoscaler 看的是逻辑需求

官方高级说明强调 Ray Autoscaler 根据任务、Actor 和放置组的逻辑资源请求扩缩，而不是以物理 CPU 或 GPU 利用率为主要输入。一个 Actor 申请 GPU 但暂时空闲，资源仍被占用；一个任务没有声明足够 CPU，即使真实线程把 CPU 打满，Autoscaler 也不会凭利用率推断更多副本。

这意味着应用资源声明是扩缩输入的一部分。开发者少报资源会导致过度并发、内存压力和无法触发扩容；多报资源则造成碎片与成本升高。平台要对常见工作负载提供经过测量的资源模板，并把排队需求、声明资源和真实利用率一起用于诊断，而不是用真实利用率替代逻辑声明。

## 18. GPU 扩缩要同时配置两套边界

官方 GPU 指南示例把 GPU Worker Group 的 minReplicas 设为零、maxReplicas 设为五，并提醒同时开启 RayCluster 的 enableInTreeAutoscaling 以及云侧 GPU 节点池自动扩缩。前者允许 Ray 逻辑层请求 Worker Pod，后者才可能提供物理 GPU 节点。

GPU 启动路径还包括大镜像拉取、驱动与设备插件就绪、模型下载和显存预热。若业务要求短时间吸收突发，完全从零扩容通常不够。可以保留最小热节点、预拉镜像、使用节点本地模型缓存，并把首次加载与后续副本扩展分开测量。

## 19. GPU 可见性存在安全陷阱

官方 KubeRay GPU 文档提醒：某些 NVIDIA 运行环境中，Pod 未声明 nvidia.com/gpu 时，NVIDIA_VISIBLE_DEVICES 默认可能为 all，使 Pod 在 GPU 节点上看到设备。这个行为不是 KubeRay 独有，但会破坏“没有申请就看不到 GPU”的直觉。

平台应通过资源请求、设备插件、运行时配置和准入策略共同约束 GPU 可见性，并执行反向测试：一个不申请 GPU 的 Ray Pod 即使被调度到 GPU 节点，也不应能使用设备。多租户场景还要禁止特权容器和主机设备挂载，不能只依赖 Ray 逻辑 num_gpus。

## 20. RayCluster 的更新不是天然滚动升级

官方选型文档指出 Ray 本身不原生支持集群滚动升级。对普通 RayCluster，修改 Ray 版本或关键集群配置通常需要关闭并创建新集群。KubeRay 1.6 增加 RayCluster 的 upgradeStrategy 字段，Recreate 可以在规格变化时重建全部 Pod，但发布说明也提醒：需要保留集群状态时不推荐这种策略。

因此 RayCluster 适合可以显式维护窗口的场景。平台应在变更前停止新提交、等待或取消现有作业、持久化需要的结果，再重建集群并执行烟雾测试。直接 kubectl apply 镜像并期待无损逐 Pod 更新，会把 Head、Actor 和对象状态置于未定义风险中。

## 21. RayService 区分原地应用更新与新集群更新

当只修改 Serve 应用配置时，RayService 可在当前活动集群上原地协调部署，避免重建整个集群。若修改 rayClusterConfig，Operator 创建待切换集群，等待其 Ray 与 Serve 应用健康，再把稳定 Service 指向新集群，最后回收旧集群。

平台发布单必须标注变更类别。应用内模型版本变更仍可能触发大规模 Replica 替换和模型加载，但不一定需要双集群；Ray 镜像、系统依赖或工作组结构变更属于集群升级，必须为新旧集群并存准备资源和配额。回滚路径也分别对应恢复 Serve 配置或重新切换集群。

## 22. 标准新集群升级需要接近双份容量

RayService 的 NewCluster 策略先把待切换集群扩到可服务容量，再切流，因此升级期间可能需要约为原集群两倍的计算资源。对昂贵 GPU，这个峰值可能被集群配额、云账户配额或可用区容量阻断。Operator 无法凭空创造第二套 GPU。

上线前应做升级容量预检：计算活动集群实际与最小容量、待切换集群启动容量、镜像缓存、模型存储带宽和队列策略；给升级对象独立优先级，并明确超过等待期限后的动作。若容量不足，应在变更前扩大池或选择经过验证的其他策略，不能让服务长期停在 UpgradeInProgress。

## 23. 增量升级仍是 Alpha

官方文档说明 NewClusterWithIncrementalUpgrade 在 KubeRay v1.5.1 以 Alpha 形式加入，利用 Kubernetes Gateway API 逐步把流量从旧集群迁到新集群，同时让新集群扩容、旧集群缩容，从而降低一次性双份加速器需求。KubeRay 1.6 发布说明增加了该策略的回滚能力。

Alpha 意味着接口与行为仍可能变化。使用前要固定 KubeRay、Gateway API 和网关实现版本，验证流量权重、长连接、重试、会话状态、回滚与控制器重启，并保留标准升级退路。它降低容量峰值但增加流量控制复杂性，不能被描述为没有代价的生产默认值。

## 24. Ready 与 UpgradeInProgress 要共同解释

RayService 从 KubeRay v1.3 开始提供 Status.Conditions。Ready 为 True 表示服务具备可用端点；UpgradeInProgress 为 True 表示活动与待切换 RayCluster 同时存在并处于升级过程。观察 generation 与 observedGeneration 可以判断状态是否已经对应最新规格。

只看 Pod Running 不足以判断服务可用。Head 可能启动但 Serve 应用尚未部署，Worker 可能 Running 但 Replica 没有健康，Service 可能存在但端点为空。发布门禁至少要检查 RayService Condition、应用状态、部署状态、Kubernetes Endpoint 以及真实请求探针，且在整个切换窗口连续观测错误率。

## 25. 初始化超时防止资源无限占用

最新官方排障文档提供 ray.io/initializing-timeout 注解。若底层 Pod 因为 ImagePullBackOff、CrashLoopBackOff 等原因长期无法启动，超时后 Operator 把 RayService Ready 置为 False，原因标记 InitializingTimeout，清理关联 RayCluster，并发出 Warning 事件。对象进入终态后需要删除重建才能恢复。

超时值必须覆盖正常镜像拉取、GPU 节点启动和模型加载的高分位数，同时又不能允许坏版本长期占用昂贵资源。平台应区分镜像、节点、容器和 Serve 初始化耗时，基于历史分布设置阈值；触发后保存足够事件、Pod 终止原因和日志，避免清理让根因完全消失。

## 26. RayJob 状态串联两种 Job 概念

RayJob 是 Kubernetes CRD；Ray job 则是通过 Ray Jobs API 运行的应用。KubeRay 还创建一个 Kubernetes Job 作为提交器执行 ray job submit。名称相似但职责不同：高层 CR 管理生命周期，提交器负责把入口交给 Ray 集群，真正的 Ray 任务在 Head 和 Worker 中运行。

排障时先定位失败阶段。RayCluster 没 Ready 属于基础设施准备；提交器 Pod 失败属于认证、网络、入口或运行时环境；Ray job 进入 FAILED 属于应用执行；清理没发生属于删除策略与控制器协调。把所有失败都归到提交器日志，会遗漏底层集群和应用状态。

## 27. 提交模式影响故障面

KubeRay v1.5 引入 SidecarMode，把作业提交逻辑作为 Head Pod 边车编排，减少外部提交客户端网络故障。不同版本还可能支持传统 Kubernetes Job 提交器等路径。选择提交模式要结合版本支持、网络策略、日志位置、重试和安全边界。

边车并不消除入口错误或 Head 故障，也会改变 Head Pod 资源与生命周期。平台应明确提交发生几次、如何生成 submissionId、控制器重启是否会重复提交、入口是否幂等。会产生外部副作用的应用需要自身幂等或事务防护，不能只依赖控制器避免重复。

## 28. preRunningDeadline 限制准备阶段

KubeRay v1.6 为 RayJob 增加 preRunningDeadlineSeconds，用于作业在规定时间内未达到 Running 时自动失败。它针对集群创建、排队、镜像拉取、提交等运行前阶段，与应用已经运行后的执行期限不同。

平台可用它防止永远 Pending 的 GPU 作业持续占用队列名额或 Head 资源，但阈值必须考虑 Kueue 等待是否应计入、Spot 容量可能多慢以及大镜像首次拉取时间。失败原因要与容量、策略和应用区分，用户才知道应该重试、换资源池还是修复镜像。

## 29. 清理策略是成本与诊断的平衡

早期 RayJob 通过 shutdownAfterJobFinishes 和 ttlSecondsAfterFinished 控制结束后删除 RayCluster。KubeRay 1.6 把更灵活的 RayJobDeletionPolicy 提升为 Beta 并默认开启，规则可根据 SUCCEEDED 或 FAILED 分别执行 DeleteWorkers、DeleteCluster、DeleteSelf 或 DeleteNone，并设置独立延迟。

生产默认可在成功后快速删 Worker、短暂保留 Head 和日志，然后删除集群；失败时保留更长诊断窗口，但仍设置上限。保留对象、保留 Head 与保留全部 Worker 的成本差异巨大。清理合同还要确保日志、指标、Ray 历史与应用制品已经外部持久化。

## 30. 删除规则不能与旧字段随意混用

官方 RayJob 快速入门说明，推荐的 rules-based deletionRules 与 shutdownAfterJobFinishes 及全局 ttlSecondsAfterFinished 互斥，应使用每条规则的 condition.ttlSeconds。旧式 onSuccess 和 onFailure 策略已经弃用并要求迁移。复制旧示例与新字段混合，可能导致校验失败或产生与预期不同的清理顺序。

平台应在准入阶段只允许一种策略风格，并为成功、失败、取消和超时分别测试。验收不只是对象最终消失，还要验证 Worker 先删、Head 保留窗口、RayJob 自身回收与外部日志落盘的顺序。删除属于业务生命周期的一部分，不是后台垃圾回收细节。

## 31. GCS 是集群元数据核心

Global Control Service 保存节点、Actor、对象位置、放置组等集群控制信息。默认情况下相关状态位于内存，Head 与 GCS 失败会使集群失去关键状态；Head 重启后原 Worker 可能被视为未知，应用和 Actor 状态无法自动完整恢复。Kubernetes 把 Pod 拉起不等于 Ray 集群语义恢复。

批处理可以通过检查点与重试接受集群重建，在线服务则通常需要更强高可用合同。平台必须先定义恢复点与恢复时间，再决定使用外部状态、嵌入式持久后端、RayService 重建或业务层重试。单纯给 Head 配置 restartPolicy 无法完成状态恢复设计。

## 32. 外部 Redis 提供 GCS 持久化但转移了风险

官方 GCS 故障转移文档长期使用外部 Redis 保存 GCS 状态，使重启后的 GCS 能读取元数据并让集群继续。Redis 连接、认证、容量、持久化和高可用因此成为 Ray 集群依赖；若只部署单实例无持久化 Redis，故障点只是从 Head 移到 Redis。

生产设计要测 Redis 故障、网络分区、密码轮换、数据恢复与版本升级，监控延迟、内存、持久化失败和连接数。不同租户或服务是否共享 Redis 也会影响故障域。平台不能只看到“启用 GCS FT”的配置项就宣称端到端高可用。

## 33. Ray 2.57 新增嵌入式 RocksDB 路径

Ray 2.57 发布说明加入用于 GCS 容错的嵌入式 RocksDB 存储后端，可通过 RAY_gcs_storage 与 RAY_gcs_storage_path 选择，使 GCS 持久化不再必然依赖外部 Redis。这一变化减少外部组件，但把持久卷、磁盘故障和 Head 重调度后的卷挂载纳入恢复路径。

新能力应按明确版本启用并执行破坏性恢复测试。持久目录必须落在具有正确访问模式和保留策略的卷上，不能使用随 Pod 删除的 emptyDir。还要验证磁盘满、数据损坏、卷不可挂载和跨可用区迁移。嵌入式并不意味着无运维，只是故障边界发生变化。

## 34. RayService 高可用需要状态与流量共同恢复

官方 RayService 高可用指南要求 KubeRay 1.3 以上并启用 GCS 故障转移。Head 失败后，Kubernetes 重建 Pod，GCS 恢复控制状态，Serve 端点仍需重新确认；稳定 Service 为流量提供固定入口。只有这几层都成立，服务才可能继续。

高可用验收应在持续请求下删除 Head Pod，记录成功率、尾延迟、Ready Condition、端点数量、Replica 状态和恢复时间。还要测试 Redis 或持久卷故障、Worker 故障与 Operator 重启。一次手工访问成功不能代表连续服务 SLO。

## 35. 对象存储压力与 Head 内存要分开观察

## 写在最后

单个工作负载之外，实验与流水线需要更高层的编排与元数据。下一篇：[Kubeflow Pipelines V2、Katib 与实验工作流](/source/AI-Infra/4-AI平台工程/21-KubeflowPipelinesV2-Katib与实验工作流)。