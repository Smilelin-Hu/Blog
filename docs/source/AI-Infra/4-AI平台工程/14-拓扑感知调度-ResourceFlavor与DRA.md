# 拓扑感知调度、ResourceFlavor 与 DRA

八张空闲 GPU 不等于一个八卡训练作业能够高效运行。它们可能分散在不同机架，可能属于不同型号，也可能只有一部分连接到目标 RDMA 网络。传统整数资源只回答“数量够不够”，AI 平台还必须回答“资源位于哪里、属于哪种产品、设备本身具有什么属性，以及这些条件能否同时满足”。

![拓扑感知调度与资源产品](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l14_01.png)

本文把这组问题拆成三层。Kubernetes 节点约束和 Topology Spread 负责单 Pod 或副本分布；Kueue 的 ResourceFlavor 与 Topology Aware Scheduling 在 Workload 准入时选择资源产品和拓扑域；DRA 把设备类别、属性、Claim、ResourceSlice 与节点可达性纳入联合分配。三层不是同一功能的重复实现，而是作用对象与承诺不同。

先给结论：拓扑标签是事实，不是装饰；ResourceFlavor 是配额产品，不是 GPU 型号别名；TAS 做的是工作负载准入时的拓扑 Assignment；DRA 做的是具体设备 Claim 分配与节点可访问性联立求解。生产系统必须让配额、拓扑和设备三份状态指向同一组真实节点，否则会出现“已准入却无法绑定”或“Claim 已分配却不在目标拓扑域”的断裂。

## 1. 为什么 AI 工作负载需要多层拓扑

分布式训练的通信代价不是线性的。两张 GPU 若通过同一 NVLink 或 NVSwitch 域通信，与跨 PCIe 根、跨 NUMA、跨机、跨机架和跨可用区的延迟带宽完全不同。一个训练 Job 即使在数量上获得全部 GPU，也可能因跨慢链路让 Step 时间显著增加。

在线推理的目标常常相反。多个副本需要跨节点、机架或可用区分散，以承受故障。把训练和推理统一配置成“尽量同机架”会放大服务风险；统一配置成“尽量分散”又会破坏集合通信。拓扑策略必须从工作负载 SLO 推导。

拓扑至少有故障、网络、主机与设备四个尺度。Zone、Block、Rack 通常描述故障和网络域；Hostname 描述节点；NUMA、PCIe、NVLink 和设备 Fabric 描述机内关系。上层标签不能替代机内设备图，DRA 也不会自动替代跨机架的工作负载准入。

平台需要一套稳定层级，例如 Zone 到 Block 到 Rack 到 Node。Kueue 的 Topology 对象把这些层级按从粗到细排列，当前官方文档要求至少一个、最多十六个 Level，每个 Level 使用唯一 Node Label，Hostname 只能处于最低层。Topology 的 Levels 创建后不可变，因此改层级应创建新对象并迁移 ResourceFlavor。

## 2. Kubernetes 原生放置约束

nodeSelector 和 Node Affinity 先缩小候选节点。requiredDuringSchedulingIgnoredDuringExecution 是硬条件，preferredDuringSchedulingIgnoredDuringExecution 是评分偏好。后半段 IgnoredDuringExecution 表示节点标签在 Pod 运行后变化时，调度器不会因此自动驱逐已有 Pod。

Taint 让节点排斥默认工作负载，Toleration 只允许 Pod 进入候选，不保证一定调度。GPU 专用节点常同时使用 Label 表达产品属性、Taint 表达准入边界。只有 Label 没有 Taint，普通 Pod 可能占用昂贵节点；只有 Taint 没有 Label，GPU 工作负载可能进入错误产品池。

Pod Topology Spread 用 maxSkew、topologyKey、whenUnsatisfiable 与 Label Selector 约束副本分布。DoNotSchedule 形成硬边界，ScheduleAnyway 形成软偏好。多个 Spread Constraint 取交集，交集为空时 Pod 保持 Pending。

计算 Skew 时，调度器会跳过不满足输入 Pod nodeSelector 或 Node Affinity 的节点。缺少所有要求 Topology Key 的节点也会被跳过，既不参与计数，也不能承载新 Pod。节点标签漂移因此可能悄悄缩小可用域。

Spread 适合副本平衡，却不等价于一次性为整个训练 Workload 预留同一 Rack。每个 Pod 独立进入调度队列时，前几个绑定可能改变后续候选。需要作业级准入和固定拓扑 Assignment 时，应使用 Kueue TAS、Gang 或相应批调度能力。

## 3. ResourceFlavor 是资源产品合同

Kueue 用 ResourceFlavor 表示一种资源变体，并通过 Node Labels、Node Taints 和 Tolerations 把配额映射到节点。典型 Flavor 可以代表 H100 加 RDMA、A100 以太网、Spot GPU 或特定区域存储，而不是只代表抽象 GPU 数量。

ClusterQueue 的 ResourceGroup 为每种 Covered Resource 配置 Flavor 与 Nominal Quota。Workload 准入后，Status Admission 记录每个 PodSet 被分配的 Flavor 和数量。集成控制器把 Flavor 的 Node Labels 与 Tolerations 注入 Pod 模板，使后续 kube-scheduler 看到一致约束。

如果用户自己的 Node Affinity 与 Flavor Node Label 冲突，配额虽然存在也不能放置。平台应在准入前检测明显冲突，并返回 ResourceFlavorNodeLabelConflict，而不是让 Pod 解除 Suspend 后长期 Pending。

Taint 与 Toleration 同样是合同的一部分。Flavor 声明的 Toleration 允许相应工作负载进入专用节点，但用户仍需经过 Queue 与 Namespace 授权。不能让租户直接添加任意 Toleration 绕过产品边界。

一个 Flavor 只有在 Node Label 真实、资源健康、Quota 口径与物理容量一致时才有意义。标签自动发现、设备插件与节点生命周期控制器共同维护事实；Kueue 不会主动验证标签背后的 GPU 确实存在或网络确实可用。

## 4. Kueue Topology Aware Scheduling

Topology 对象是集群级层级定义，ResourceFlavor 通过 spec.topologyName 引用它。启用 TAS 的 Flavor 至少需要一个 Node Label；一旦设置 TopologyName，官方文档说明整个 ResourceFlavor Spec 不可修改。这种不可变性保护已经生成的 Topology Assignment 不被静默重解释。

Workload 通过 Pod 模板 Annotation 选择拓扑语义。Required 要求整个 PodSet 位于指定层级的同一 Domain；Preferred 从指定层级向更粗层逐级尝试，无法单域容纳时允许跨多个 Domain；Unconstrained 仍要求 TAS 计算整体可容纳性，但不强制共同 Domain，适合利用分散碎片。

Slice Required 把 PodSet 切成固定大小的 Slice，每个 Slice 分别要求位于同一 Domain。它适合数据并行分组、推理副本组或通信层级。当前文档还描述多层 Slice Constraint 能力，最多支持三层并需要对应 Feature Gate。这里必须把稳定能力与 Feature Gate 能力分开。

TAS 先在 Kueue 准入层查看 Flavor 覆盖节点、已用容量和拓扑层级，选择 Domain 并把 Assignment 写入 Workload Status。随后集成控制器根据 Assignment 更新 PodSet，kube-scheduler 执行具体节点绑定。Quota Reserved、Topology Assigned、Pod Bound 和 Application Ready 是四个不同状态。

TAS 与 Cluster Autoscaler 通过 Provisioning AdmissionCheck 协作时，顺序是先保留 Quota，再等待包括 Provisioning 在内的 AdmissionCheck Ready，然后根据新增节点计算 Topology Assignment。若在节点出现前固化 Assignment，可能为不存在的容量做错误承诺。

当最低层为 Node 时，TAS 会用 Node Selector 固定 Pod。节点运行中失败会让替代困难。Kueue 当前文档描述 TASFailedNodeReplacement 热替换能力为 Beta 且默认启用，但替代节点仍必须满足相同 Flavor 与拓扑要求；作业占满整个 Rack 时可能根本没有同域替代。

## 5. DRA 把设备属性纳入调度

Kubernetes DRA 在当前官方文档中已于一比三十五进入 Stable 并默认启用。设备驱动发布 ResourceSlice，集群管理员提供 DeviceClass，工作负载通过 ResourceClaim 或 ResourceClaimTemplate 请求设备，Pod 引用 Claim。Scheduler 选择匹配设备并把 Allocation 写入 Claim，再把 Pod 放到能访问该设备的 Node。

DeviceClass 定义管理员认可的设备类别和选择规则。Claim 可以用 CEL 在类别范围内进一步筛选属性，例如显存、Fabric 或型号。ResourceSlice 描述设备池、设备名称、节点可达性、属性与容量。它是驱动维护的动态事实，不应由普通用户伪造。

调度过程需要联合求解。先选设备再发现目标 Node 不符合 Rack 要求会失败；先锁定 Rack 再发现其中没有满足 Claim 的设备也会失败。正确候选是 Flavor 节点、Topology Domain、Pod 硬约束和 DRA 设备可达节点的交集。

官方文档说明核心分配采用 First Fit，并按 Pool 与 ResourceSlice 名称的字典顺序评估；驱动可以通过命名影响优先顺序。平台不能假设 Scheduler 一定选择性能最高设备，若性能差异是硬需求，应进入 DeviceClass 或 Claim Selector。

DRA 设备由驱动与 Kubelet 在目标节点准备并注入容器。Claim 显示 Allocated 不等于容器已经拿到可用设备。还要观察设备准备、CDI 或运行时集成、Pod 启动和应用探针。

当前官方限制非常关键：kube-scheduler 不支持对 DRA 资源做 Preemption。一个高优先级 Pod 需要已被低优先级 Pod 占用的 DRA 设备时，会继续 Pending，直到设备自然释放或占用 Pod 被人工删除。不能把普通 Pod Priority 抢占承诺直接套到 DRA Claim。

## 6. 三层状态怎样保持一致

第一层是 Queue 与 Flavor。它说明租户有权使用哪种资源以及多少。第二层是 Topology Assignment。它说明一组 Pod 应落在哪个 Domain。第三层是 ResourceClaim Allocation。它说明具体设备和可访问节点。三层都满足后，Pod 才进入普通绑定与 Kubelet 准备。

假设 Queue 为 Job 预留八张 H100 配额，TAS 选择 Rack 一，DRA 却分配 Rack 二的设备。每一层局部都可能显示成功，联合结果却为空。平台在提交前必须用同一节点集合计算，并把不相交错误稳定标记为 TopologyAndDeviceIntersectionEmpty。

另一个断裂是 Flavor 标签过期。Rack 一节点仍标记 H100 和 RDMA，但设备驱动已移除 ResourceSlice 或报告不健康。TAS 依据节点与 Quota 可能准入，DRA 无法分配。节点健康控制器应及时隔离 Flavor，AdmissionCheck 也可阻止继续解除 Suspend。

资源释放同样跨层。Pod 删除后，Kubelet 与驱动清理设备，Claim 按生命周期释放，Kueue 在 Workload 结束或失去准入时归还 Quota，Topology Assignment 不再占用。任何一个 Finalizer 或控制器卡住都会形成泄漏。

## 7. 把拓扑约束写成可计算问题

拓扑感知不能停留在“尽量放近一点”。调度系统需要明确输入、可行集合、目标函数与失败条件。设节点集合为 $N$，工作负载包含 $P$ 个 Pod，每个 Pod 请求资源向量 $r$，节点 $n$ 的剩余资源为 $c_n$。普通调度只需为每个 Pod 找到资源足够的节点；Required Rack 还要求所有被选节点的 Rack Label 取值相同。

对某个 Rack Domain $d$，可用容量不是节点 GPU 数量的简单总和。首先删除不属于 ResourceFlavor 的节点，再删除不满足 Node Affinity、Taint Toleration、Volume Zone 与 DRA 设备可达性的节点，最后按 Pod Shape 计算可容纳 Pod 数。若 Pod 每个请求两张 GPU，三台节点各剩一张时，总量为三却一个 Pod 也放不下。

把 Domain $d$ 对某 PodSet $s$ 的可容纳数量写成 $F(d,s)$。Required 条件是存在一个 Domain，使 $F$ 不小于 Pod 数。Preferred 先在指定层查找满足条件的 Domain，找不到再向更粗层扩大；Unconstrained 只要求所有合格节点合计能容纳，但仍要避免把同一节点资源重复计给多个 Pod。

当一个 Workload 有多个 PodSet，例如 Leader、Worker 和 Evaluator，约束可能不同。Leader 只需一张 GPU，Worker 要求同 Rack，Evaluator 可以跨 Rack。不能为每个 PodSet 独立挑选一套会互相争用的容量，再声称整体可行。Assignment 需要考虑所有 PodSet 的联合占用。

拓扑选择还可能有目标函数。多个 Rack 都能容纳时，可以选择放置后剩余碎片更少的 Domain，也可以选择网络更快、成本更低或健康余量更大的 Domain。目标函数只能在硬约束已经满足的候选中比较。把成本分数放在安全约束之前，会选择便宜但不合法的节点。

工程上常用“可行性”和“质量”两阶段。第一阶段返回 Domain 是否能完整承载，以及排除原因；第二阶段给可行 Domain 评分。日志必须区分这两阶段：零可行 Domain 是约束或容量问题，有多个可行 Domain 但选了某一个才是策略偏好。

拓扑容量随 Pod 绑定、释放、节点健康和设备 Claim 变化。准入时使用的是一个快照，不可能永久保证未来不变。因此 Assignment 之后还需要 Scheduling Gate、Node Selector、控制器重试与失败恢复，把快照决策落实为可收敛状态机。

## 8. 节点标签治理：拓扑事实从哪里来

Topology 对象只声明哪些 Label 组成层级，不会自动证明 Label 正确。云环境的 Zone 与 Region 通常由 Provider 写入，Rack、Block、Fabric、GPU 岛和网络 Rail 可能来自裸金属管理系统、网络控制器或平台自建发现器。每一个 Label 都要有唯一 Owner 和更新协议。

手工给数百节点打 Rack Label 只能用于实验。生产应从 CMDB、交换机、UFM、机柜管理或云实例元数据生成，经过校验后写入 Node。来源系统不可用时采用保守策略：保持最后已知值并标记陈旧，或隔离节点；不能随便猜测一个默认 Rack 让作业继续。

Label Key 要稳定，Value 要在同一层级唯一且能表达父子关系。若两个 Zone 都各有名为 rack-1 的机架，仅用 rack-1 作为 Domain 值会被错误合并。可以让 Value 全局唯一，或在生成时编码父级。Kueue 根据同一 Label 值分组，名称设计直接影响 Domain 边界。

所有引用 Topology Level 的节点都应具备相应 Label。缺失 Label 的节点不会成为该层候选，容量会悄悄减少。新增节点进入 Ready 前执行拓扑完整性门禁；发现漂移时先 Taint 隔离，再修复事实，避免训练的一部分进入未知域。

标签变化对运行 Pod 和待调度 Workload 影响不同。Node Affinity 的 IgnoredDuringExecution 不会自动驱逐已运行 Pod；新的 TAS Assignment 会使用新值；已经固定 Node Selector 的 Pod 可能在替换时无法找到节点。修改 Rack Label 等同于改变调度事实，应经过变更窗口和在途 Workload 评估。

拓扑并非越细越好。每增加一层就增加对象、状态与可行性计算，还增加错误配置机会。只有业务能利用且基础设施能可靠维护的层级才应进入 Topology。比如 GPU 岛若驱动没有稳定发现，宁可作为设备属性由 DRA 表达，也不要用人工 Label 伪装。

平台每日做三类对账。结构对账检查 Topology 声明的 Label 是否在目标节点完整存在；物理对账检查 Label 与网络、机架和 GPU 事实一致；行为对账检查 Assignment 中的 Domain 与最终 Pod Node 一致。三类只做其中一类都会留下盲区。

安全上，普通租户不能修改 Node Label、Topology 或 ResourceFlavor。能改 Rack Label 的人实际上能改变作业放置与故障域，权限等同于集群基础设施管理员。审计要记录旧值、新值、来源、时间和影响节点。

## 9. ResourceFlavor 的完整语义

ResourceFlavor 把同名资源的不同产品形态映射到 Quota。两台节点都暴露 nvidia.com/gpu，设备插件整数资源无法说明一台是 H100、一台是 T4；Flavor 通过 Node Labels 把 ClusterQueue 中的 Quota 指向指定节点群。用户申请的是平台产品，Kueue 决定使用哪个 Flavor。

Flavor 的 Node Labels 在 Workload 准入后被加入底层 Pod 模板的 Node Selector，前提是模板没有冲突字段。它形成硬放置条件，不是评分偏好。若用户已经声明同 Key 不同 Value，正确结果是不能使用该 Flavor，而不是覆盖用户值。

ResourceFlavor 的 Tolerations 用于自动让被分配该 Flavor 的 Pod 容忍相应 Node Taint。另一个字段 Node Taints 用于准入侧筛选：Workload 自身必须容忍这些 Taint，除非 Flavor 同时提供匹配 Toleration。两者名字接近但用途不同，平台模板要明确谁负责添加。

Node Taints 只把 NoSchedule 与 NoExecute 作为准入约束，PreferNoSchedule 在这一语义中被忽略。普通 Kubernetes 调度仍可能处理节点上的 PreferNoSchedule，但不要把它当成 Kueue Flavor 选择的硬门槛。需要强隔离时使用明确硬 Taint 和 Admission 权限。

同一个 Resource Group 可以包含多个 Flavor，例如 on-demand-h100、spot-h100 与 on-demand-a100。Flavor 顺序和借用政策会影响选择。平台不能只展示“GPU 配额十张”，应展示每种 Flavor 的 Nominal、Borrowing、Lending、当前使用和候选节点健康。

资源异构并不意味着每个硬件属性都建一个 Flavor。Flavor 数量过多会让 Quota 组合与运营复杂度爆炸。通常把影响价格、可用性、应用兼容和拓扑的主要维度产品化，细粒度设备属性交给 DRA Selector。比如 H100-80G-RDMA 可以是 Flavor，具体 NVLink 域与设备健康由 Topology 和 DRA 处理。

空 Flavor 适合真正同构或无需区分的资源。如果集群同时存在不同 GPU 却用空 Flavor，Kueue 只做数量准入，Pod 可能落到不兼容节点。是否同构应由持续对账证明，而不是部署初期的假设。

Flavor 与 Topology 绑定后，至少要有一个 Node Label，且 Spec 不可变。要调整 Node Selector、Toleration 或 Topology 引用，创建新 Flavor、在 ClusterQueue 中增加新项、灰度 Workload，再移除旧 Flavor。直接删除仍被 Workload 引用的 Flavor 会破坏解释与恢复。

Quota 事实与节点事实可能不同。ClusterQueue 为 H100 配置十六张 Nominal，不代表当前有十六张健康物理 GPU。Kueue 的 Quota 是组织权利，TAS 会进一步考虑节点容量；若 DRA 或设备健康再减少，Workload 仍可能等待。状态页要分别显示账面 Quota、拓扑可容纳与设备可分配。

## 10. Required、Preferred 与 Unconstrained 的选择

Required 用于违反拓扑就无法正确或无法达到最低性能的场景。典型例子是一个通信组必须位于同 Rack，或数据处理必须位于同 Zone 以访问本地卷。它的优点是性能边界清楚，代价是更容易 Pending 并增加碎片。

设置 Required 前要回答“为什么是这一层”。要求同 Node 最严格，同 Rack 次之，同 Block 或 Zone 更宽。层级越细，单 Domain 容量越小，节点失败替换越困难。若训练能跨 Rack 只是性能稍差，Preferred 可能比 Required 带来更高总体吞吐。

Preferred 从指定层向更粗层寻找。若同 Node 放不下，可以尝试同 Rack；同 Rack 不行再尝试同 Block，最终可能跨 Domain 准入。它不是“随机忽略约束”，而是有序降级。状态应记录最终使用的 Level，让用户知道性能档位。

Preferred 适合软性能目标，但业务必须能接受最粗层结果。若跨 Zone 会产生不可接受费用或数据合规问题，就不能使用 Preferred 把 Zone 边界当软条件。硬合规用 Node Affinity、Storage Topology 或 Required 约束。

Unconstrained 仍通过 TAS 维护容量视图与 Assignment，但不要求共同 Domain。它擅长填充散落空隙，适合独立推理副本、数据分片或通信很少的任务。它可能获得更高准入率，却不能承诺低通信延迟。

三种模式应由平台 Profile 生成，而不是让用户根据名字猜。表单可以询问通信组大小、可否跨 Rack、单故障域最大副本、数据位置和性能降级容忍度，然后选择 Annotation。高级覆盖必须显示预计容量与风险。

评估同一 Workload 时，应在相同节点快照下运行三种模式。Required 可能 Pending，Preferred 可能在 Block 层运行，Unconstrained 可能铺满碎片。比较有效 Step 时间与等待时间，才能判断业务完成时间，而不是只看谁最早 Admitted。

反例是把高可用在线服务所有副本标成 Required 同 Rack。它可能降低服务间通信，却让 Rack 故障一次带走全部副本。另一反例是把强 AllReduce 训练标成 Unconstrained，数量利用提高但 Step 时间恶化。模式没有绝对优劣，只有是否匹配 SLO。

## 11. Slice 拓扑：一个 Workload 里的分组放置

大型 Job 未必要求全部 Pod 位于同一 Rack。一个六十四卡训练可以由八个八卡通信组组成，每组要求同 Rack，组间允许跨 Block。若整体 Required 同 Rack，容量难以满足；若完全 Unconstrained，又破坏组内通信。Slice 提供中间表达。

podset-slice-required-topology 指定每个 Slice 必须位于某个 Topology Level 的同一 Domain，podset-slice-size 给出每 Slice 成员数。Kueue 为每个 Slice 选择 Domain，并在 Topology Assignment 中记录分布。最后一个 Slice 如何处理取决于 Pod 数与 Size 合同，应在目标版本实验验证。

Slice Size 应与应用并行结构一致。例如张量并行八路的成员需要共享高速域，数据并行组可以跨域。只为了更容易准入而随意切片，会让应用通信组与调度组错位。训练启动器、Rank 映射与调度 Assignment 需要共同设计。

多层 Slice 约束可以表达更复杂层级，例如每八个 Pod 同 Rack、每三十二个 Pod 同 Block。当前 Kueue 文档说明该能力需要 TASMultiLayerTopology Feature Gate，约束最多三层，并通过 JSON 编码 Annotation 表达。生产使用前必须锁定 Kueue 版本、Gate 状态与工作负载集成支持。

多层约束从最粗到最细排列，Slice Size 要保持合理嵌套。若外层三十个、内层八个，边界可能无法整齐分组。Admission 应在提交前校验大小关系，避免让控制器在运行时产生难解释结果。

Slice 提高可调度性也改变故障语义。一个 Rack 失败只影响其中一 Slice，应用是否能局部替换或必须全 Job 重启由框架决定。Kueue 能找节点不等于训练框架能动态重建通信组。

在线推理也可使用 Slice。比如每个模型 Shard 组需要四个成员同 Rack，多个完整 Shard 组跨 Rack 分散以提供高可用。此时既有组内聚合，也有组间隔离。平台要把服务拓扑转换为多个 PodSet 或 Slice，而不是单纯用 Replica 数。

验收 Slice 不能只看每个 Pod 的 Node。先从 Workload Status 读取 Topology Assignment，重建每个 Slice 的成员和 Domain，再对照最终 Pod Rank 与应用通信组。任何一层错位都可能在表面 Running 下产生性能问题。

## 12. TAS 从提交到绑定的状态机

用户提交 Suspended Job，Kueue 集成控制器创建或维护 Workload。Workload 进入 LocalQueue 并指向 ClusterQueue。此时没有 Quota Reservation，也没有 Topology Assignment，底层 Pod 通常尚未运行。

Admission 选择 ResourceFlavor 与 Quota。对 TAS Flavor，控制器根据匹配节点、当前占用与 PodSet 请求计算 Topology Assignment。若 Required Domain 只能容纳四个而需要十个，即使 Quota 为一百核，Workload 也保持 Pending。原因必须明确是拓扑不足而非 Quota 不足。

Kueue 官方实验流程显示，TAS Workload 的 Pod 会带 kueue.x-k8s.io/topology Scheduling Gate，在 Assignment 计算完成前保持门控。Kueue 随后注入匹配 Assignment 的 Node Selector 并移除 Gate。这样避免 Pod 过早被普通 Scheduler 绑定到错误 Domain。

Scheduling Gate 不是资源 Reservation 本身。它只是阻止 Pod 进入调度。Topology Assignment 与 Quota 状态才说明 Kueue 决策。值班时看到 Pod SchedulingGated，应追溯 Workload Status，而不是把它当 kube-scheduler 性能问题。

移除 Gate 后，kube-scheduler 仍要检查 CPU、内存、GPU、卷、端口、Affinity 和 DRA Claim。若这些事实与 TAS 快照变化，Pod 可能 Pending。Kueue 的 PodsReady 策略可在超时后释放 Admission 并重排，但具体恢复合同要测试。

Provisioning AdmissionCheck 加入自动扩容时，官方顺序是 Quota Reserved、所有 AdmissionCheck Ready、再结合新增节点生成 Topology Assignment。新节点必须带正确 Flavor 与 Topology Label，否则扩容成功数量增加，TAS 仍然找不到 Domain。

运行中节点失败时，固定 Node 级 Assignment 限制替代范围。TASFailedNodeReplacement 会尝试在同一要求内寻找替代，但若 Workload 占满整个 Domain 就无空位。平台需在性能与故障余量间留出容量，或接受整组重排。

作业完成或撤销时，Pod 删除、Gate 和 Selector 不再相关，Workload 释放 Quota 与 Topology 占用。清理过程必须幂等。Job、Workload 或 Pod 任一 Owner 链断裂都会留下幽灵容量。

## 13. DRA 对象模型与责任边界

DRA 的 Provider 是设备驱动。它发现或管理设备，发布 ResourceSlice 并在目标 Node 准备设备。Cluster Admin 安装驱动、定义 DeviceClass 和授权。Workload Operator 创建 Claim 或 ClaimTemplate 并让 Pod 引用。Scheduler 负责在候选设备与节点之间做分配。

DeviceClass 是集群级抽象，类似存储中的 StorageClass，但它描述设备类别与管理员选择。一个 Class 可以代表受信任的 GPU、网络接口或其他加速器。名称应表达稳定产品能力，不把短期节点名编码进去。

ResourceSlice 由驱动发布设备池的一部分。它可以描述 Node 范围、具体 Device、Attributes 和 Capacity。Slice 更新反映设备变化。普通用户不应有创建或修改权限，否则可伪造设备、影响 Scheduler 或诱导 Pod 访问未授权硬件。

ResourceClaim 是命名的设备请求和 Allocation 状态。独立 Claim 可被明确生命周期管理；ResourceClaimTemplate 适合控制器为每个 Pod 生成 Claim。选择取决于设备是否需要跨 Pod 共享、何时创建以及谁负责删除。

Pod 通过 spec.resourceClaims 引用 Claim 或 Template 生成的 Claim。Scheduler 必须先找到符合 DeviceClass 与 Selector 的设备，再确保 Pod 能落到设备可访问节点。Kubelet 和驱动在节点侧 Prepare，容器才能看到设备。

Allocation 写入 Claim Status 是控制面承诺，但不是应用成功。设备可能在 Prepare 阶段失败、CDI 条目缺失、健康变化或容器配置错误。监控至少区分 Claim Pending、Allocated、Pod Scheduled、Device Prepared、Container Started 和 Application Ready。

资源释放从 Pod 不再使用 Claim 开始，随后驱动 Unprepare 并归还设备。独立 Claim 若仍存在，是否保留 Allocation 取决于生命周期与使用方式；Template 生成 Claim 通常随 Owner 清理。实验要验证目标实现，不能用普通扩展资源经验推断。

DRA 核心 Stable 不代表所有高级字段都 Stable。Admin Access、细粒度 Status 授权、分区设备、Consumable Capacity、Device Taint 等各自有 Feature Stage 和 Gate。这里的核心路径只承诺目标版本已启用的能力，其他作为版本化扩展。

## 14. DeviceClass 与 CEL Selector

DeviceClass 提供管理员级 Selector，Claim 再追加用户请求。有效候选必须同时满足两者。管理员可以用 Class 排除未认证设备，用户再筛选显存或 Fabric；用户不能通过 Claim 放宽 Class 边界。

CEL 表达式针对驱动发布的 Attributes 与 Capacity。字段通常带驱动 Domain，避免不同 Provider 使用同名属性产生冲突。编写表达式前先读取实际 ResourceSlice Schema 与样本，不要凭想象写 memory 或 model 字段。

Selector 是硬条件。请求显存至少八十 GiB 而设备只报告四十 GiB 时，Claim 保持 Pending。若业务只是偏好八十 GiB、四十 GiB 也能运行，核心 Selector 未必能表达排序偏好，应建立两个 DeviceClass 或上层 Profile 的有序回退，并验证目标版本能力。

属性缺失与值不匹配要区分。设备驱动升级后停止发布某 Attribute，所有相关 Claim 可能突然没有候选。发布前对 DeviceClass 表达式做契约测试：每种目标设备至少有一个匹配，每种禁止设备都不匹配。

## 写在最后

拓扑与设备决定了放置的可行域，而容量本身会随时间增减。下一篇：[弹性容量、Spot、节点自动扩缩与中断治理](/source/AI-Infra/4-AI平台工程/15-弹性容量-Spot-节点自动扩缩与中断治理)。