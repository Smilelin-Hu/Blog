# 弹性容量、Spot、节点自动扩缩与中断治理

GPU 节点自动扩缩不是“Pod Pending 就买机器，Pod 结束就删机器”这么简单。AI 工作负载请求大、启动慢、拓扑强、设备准备链长，还可能使用 Spot 或可抢占容量。扩得太慢，训练错过窗口；缩得太快，完整 GPU 拓扑被打碎；中断处理只剩数分钟时，Checkpoint、Drain 和替代节点往往无法全部完成。

![弹性容量与中断治理](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l15_01.png)

本文的核心结论是：弹性容量是一条从逻辑配额、物理 Provisioning、节点完整 Profile、工作负载准入、运行中断到容量回收的状态链。Node Autoscaler 只依据 Pod 资源请求与调度约束规划节点，不直接依据容器真实使用量；Consolidation 也主要依据 Request 而非真实使用。Request、DaemonSet Overhead 和 Topology Shape 因此都是成本与正确性输入。

Spot 不是便宜的 On-demand，而是带不确定终止权的产品。平台必须把中断通知、替代容量、Checkpoint、Drain、Job 恢复和数据一致性组合成可验证合同。云厂商没有保证通知一定足够应用完成，模拟成功也不能替代真实事件演练。

## 1. Node Autoscaling 解决什么问题

Kubernetes 官方将 Node Autoscaling 分为 Provisioning 与 Consolidation。Provisioning 在现有节点无法承载 Pending Pod 时创建云资源并让 Node 加入集群；Consolidation 移除低效节点，必要时用更合适节点替换，以降低成本。

Autoscaler 的目标是让符合条件的 Pod 可调度，并不保证所有请求一定成功。NodePool 或 Node Group 限制、Pod 约束冲突、云 Provider 无容量、Quota、拓扑和设备准备都可能让扩容失败。平台必须把失败变成稳定状态，而不是无限创建实例。

Cluster Autoscaler 从预配置 Node Group 选择并调整规模；Karpenter 根据 NodePool 约束直接自动选择实例并管理更完整 Node 生命周期。两者都需要与具体 Cloud Provider 集成，功能和支持范围随 Provider 不同。选型应基于目标云与运维合同。

Provisioning 依据 Pod Resource Request，不读取应用启动后的真实 GPU、CPU 或内存使用。Request 过小会让 Autoscaler 认为较小节点可行，Pod 运行后产生争用或 OOM；Request 过大则阻止合并并增加成本。VPA 可以帮助校准普通工作负载，但 AI GPU 作业仍需结合框架 Profile。

新节点可分配资源必须扣除 Kubelet Reserved、System Reserved 和 DaemonSet。GPU 节点通常有网络、监控、存储、设备与安全 DaemonSet。忽略 Overhead 会让计算认为一个 Node 可放四 Pod，实际只能放三个，扩容后仍 Pending。

## 2. 从 Pending Pod 到 Node Ready

普通路径从 kube-scheduler 把 Pod 标为 Unschedulable 开始。Autoscaler 读取 Pod Request、Node Selector、Affinity、Taint Toleration、Topology Spread 和卷约束，与可创建 Node 模板比较。至少一种 Node 配置可行，且未超过 Pool 上限，才向 Provider 请求容量。

实例创建成功只是第一段。Node 还要启动操作系统、Kubelet 与 CNI，安装或加载 GPU Driver、Runtime、Device Plugin 或 DRA Driver、RDMA、存储与监控，最后通过 Node Profile 门禁。Node Ready 不能自动代表 nvidia.com/gpu 或 ResourceSlice 已经可用。

AI 平台把扩容时间拆成 Unschedulable 检测、计划、Provider 排队、实例启动、Node 注册、设备发现、网络 Ready、缓存预热和 Pod 绑定。总时间决定是否满足训练或在线扩容 Deadline。只报告云实例启动耗时会遗漏最慢阶段。

Provider 可能返回容量不足。Autoscaler 应尝试 NodePool 允许的其他实例、Zone 或 Capacity Type，但不能跨越工作负载硬约束。H100 Job 不能因为 A100 便宜或有货就自动降级，除非产品合同明确允许。

NodePool Limits 是成本和风险硬边界。到达 GPU、CPU 或 Node 上限时继续 Pending 并告警，不能无界采购。临时突破需要审批、有效期与成本归属。

## 3. Kueue ProvisioningRequest 与容量保证

Kueue 没有 Provisioning AdmissionCheck 时，Quota 充足可让 Workload Admitted，但物理节点未必存在。ProvisioningRequest 把逻辑 Quota 与 Cluster Autoscaler 的物理 Capacity Guarantee 连接起来。

流程先完成 Quota Reservation，防止其他 Workload 抢走同一配额；Kueue Controller 根据 PodSet 和 ProvisioningRequestConfig 创建 ProvisioningRequest，并让它 Owner 指向 Workload。Cluster Autoscaler 处理请求，创建或预留容量，并更新 Condition。

官方文档列出 Provisioned、Failed、BookingExpired 和 CapacityRevoked 等状态。Provisioned 为真表示容量准备；Failed 说明无法交付；BookingExpired 表示预留过期；CapacityRevoked 表示容量被撤销，运行 Workload 可能被驱逐。平台要把每种状态映射到 Queue、Quota 和用户动作。

只有 Quota Reserved 且全部 AdmissionCheck Ready，Workload 才 Admitted。Check Retry 会释放 Reservation 并重新排队；Rejected 会停用 Workload。Provisioning 成功后若 Job 迟迟不创建 Pod，Booking 可能过期，容量被回收。

Topology Aware Scheduling 加入后，Provisioning 要交付完整 Domain，而不是实例总数。八台节点分布在两个 Rack 可能无法满足 Required 同 Rack。前一篇的 Node Profile、Flavor、Topology 与 DRA 准备在此成为 AdmissionCheck 条件。

## 4. Spot 容量的真实合同

Spot 或可抢占实例价格低，因为 Provider 保留回收权。不同云的通知、事件渠道与最长期限不同，这里不把一个 Provider 的时长当成行业统一标准。以 AWS 与 Karpenter 官方路径为例，Spot 回收通常有两分钟通知，Karpenter 可监听事件、Taint、启动替代节点并 Drain。

两分钟不是应用可自由使用的完整时间。事件传递、Controller 反应、替代实例排队、Pod 驱逐、Checkpoint 与对象存储写入都消耗预算。Checkpoint 九十秒、Drain 三十秒已经没有安全余量，替代节点也未必在回收前 Ready。

Spot 工作负载必须能被中断。训练在收到终止信号后停止领取新 Batch，写一致 Checkpoint 并退出；数据任务保证分片幂等；推理先从 Gateway 摘流。未经恢复演练的应用不能因为“有保存代码”就标记可中断。

实例类型与 Zone 多样性提高获得 Spot 容量的概率。Karpenter 当前 AWS 文档描述以 Price Capacity Optimized 策略选 Spot，并在 Spot-to-Spot 单节点替换时要求足够实例类型灵活性，避免不断追逐最低价而提高中断风险。具体阈值属于实现版本合同。

On-demand 与 Spot 可作为不同 ResourceFlavor 或 Capacity Type。用户选择允许回退时，平台在准入前显示最终类型、成本和中断等级。运行中的 Gang 不应混入未经验证的不同产品。

## 5. Consolidation 不是无风险省钱

Consolidation 依据 Pod Request 判断节点可删除或由更便宜节点替换。空节点删除风险最低；低利用节点合并会驱逐运行 Pod。Karpenter 当前提供 WhenEmpty、Balanced 与 WhenEmptyOrUnderutilized 等策略，具体可用值以目标版本为准。

PodDisruptionBudget 会阻止某些自愿驱逐，但多个 Pod 与多个 PDB 的交集可能让 Node 长期不可合并。do-not-disrupt 可以保护 Pod 免受部分自愿操作，却不能阻止 Spot Interruption、Node Repair 等强制事件。它不是永不终止保证。

NodePool Disruption Budget 限制 Drift、Consolidation 和 Empty 等自愿动作速率。预算通常不阻止所有强制终止，不能拿它承诺 Spot 不会同时回收。值班页面要区分自愿和非自愿 Disruption。

GPU 集群还要保护 Topology Capacity。删除每个 Rack 一台低利用节点，可能让所有 Rack 都无法承载八节点训练；集中删除一个完整空 Rack 反而保留其他 Domain。Autoscaler 原生成本决策若不了解未来 Job Shape，平台需要外部门禁或保守 NodePool 边界。

Consolidation 必须计算替代节点启动、Drain、镜像与设备准备，不在旧节点删除后才发现替代无 GPU。对于大模型在线服务，迁移的模型 Warmup 可能比实例价格节省更重要。

## 6. 用资源请求而不是瞬时利用率理解扩容

节点扩缩容器看到的世界与监控系统看到的世界不同。监控系统记录某个容器在过去一分钟使用了多少 CPU、内存和 GPU，调度器与节点扩容器则主要依据 Pod 声明的资源请求、调度约束以及节点模板判断未来能否放置。这个差异不是实现细节，而是可预测调度的基础。如果用瞬时利用率决定一个尚未运行的 Pod 需要什么节点，系统就没有稳定输入；如果把资源请求写成随意的数字，扩容结果也一定偏离真实需要。

可以把一个节点的有效容量写成节点可分配资源减去常驻开销。常驻开销包括系统保留、Kubelet 保留、CNI、设备插件、日志、监控、存储、网络与安全代理。对 GPU 节点，不能只计算 GPU 卡数。一个八卡节点可能因为主机内存、共享内存、CPU、临时盘或可用 Pod 数量不足而无法承载第二个训练 Pod。扩容仿真应同时计算多维向量，而不是用 GPU 数量做唯一判断。

资源请求过小会造成三类后果。第一类是扩容器选择了规格不足的节点，节点加入后 Pod 仍然 Pending，形成“扩了却不能调度”的假扩容。第二类是多个 Pod 被装入同一节点，运行后在 CPU、内存、网络或本地盘上争用，表现为训练吞吐抖动、数据加载停顿或容器被驱逐。第三类是 Consolidation 错误地认为 Pod 可以迁移到更小节点，驱逐后才发现运行特征无法满足。资源请求过大则会让可行实例集合变窄、碎片增加、空闲节点无法回收，并把成本归因放大。

平台应把请求校准视为容量产品的一部分。CPU 与内存可以参考历史分位数，但不能机械采用平均值；训练启动、Checkpoint、编译和数据预处理常有短时峰值。GPU 通常以整数设备或 DRA 声明，主机资源仍需按实际 Profile 校准。在线推理还要考虑模型加载期与稳定服务期的不同资源曲线。若系统允许 Init Container 预取权重，Init Container 与主容器请求的调度语义也要纳入评审，不能只观察服务稳定后的曲线。

请求校准需要版本化证据。每个工作负载模板记录模型版本、镜像、并行策略、Batch、上下文长度、节点 Profile、测量窗口、峰值、建议请求和安全余量。平台变更 GPU 驱动、通信库、缓存策略或 Sidecar 后，应重新采样。否则旧数据会悄悄进入新节点池，扩容器虽然按声明正确工作，结果却不再符合业务目标。

判断扩容是否正确，至少要同时回答四个问题：Pending Pod 是否由容量不足造成；新节点模板是否满足全部硬约束；节点加入后设备与网络是否达到完整 Profile；Pod 运行后的实际资源曲线是否证明请求合理。只回答“创建了实例”不能完成验收。

## 7. Bin Packing、碎片与形状匹配

AI 容量调度不是把总卡数相加。两台各剩四卡的八卡节点，不能承载一个要求单机八卡的 Pod；两个 Rack 各剩四台节点，也不能承载一个要求同 Rack 八节点的 Gang。容量是否可用取决于资源形状、拓扑域、设备型号、互联能力和时间窗口。平台看板若只展示集群空闲 GPU 总数，会让用户误以为容量充足。

最基本的装箱判断需要对每个候选节点模板计算 Pod 请求向量能否放入，并检查 Node Selector、Affinity、Taint、Topology Spread、Volume Zone 与 RuntimeClass。对于 Gang，还要在同一个决策中放置全部 PodSet；逐 Pod 得到的局部可行不等于整体可行。Topology Aware Scheduling 要求的域计数也必须一次满足，否则先占用几个节点会使剩余成员永远无法进入。

碎片有空间碎片和时间碎片。空间碎片是资源分散在不兼容节点与拓扑域；时间碎片是容量在错误时间释放，例如低优先级作业还有十分钟结束，高优先级作业却需要马上获得完整 Gang。单纯提高平均利用率可能同时恶化两者。平台要针对常见 Job Shape 保留可组合的空闲结构，并用排队预测决定是等待自然释放、抢占、扩容还是改用另一容量产品。

GPU 型号不是唯一形状。同型号节点可能具有不同网卡速率、RDMA 配置、NUMA 布局、本地盘、驱动版本和故障域。Node Profile 应把这些能力编码为稳定标签、Flavor 或设备属性，并由准入层阻止应用直接依赖未经治理的云厂商原始标签。否则云侧实例系列调整、驱动升级或节点镜像切换会造成隐性漂移。

一个常见错误是允许 Autoscaler 自由选择大量实例类型，却没有验证每个类型的 DaemonSet 开销和启动链。候选集合看似增加了容量概率，实际上某些较小实例在系统组件启动后已无足够 CPU 或 Pod 槽位。正确做法是在节点模板层维护可分配资源快照，并通过真实启动测试校正。新实例类型进入生产前，先在隔离池验证节点注册、设备发现、网络、存储、镜像与训练通信。

另一个错误是把在线推理与离线训练放入同一可任意合并的池。推理副本可能只用一张卡，训练 Pod 需要整机八卡。若推理副本均匀散布到所有节点，集群有大量空闲卡却没有完整节点。平台可用分池、拓扑约束、整机保留、可迁移窗口或定时整理减少碎片，但每种方式都要计算迁移成本和可用性风险。

## 8. Cluster Autoscaler 与 Karpenter 的架构边界

Cluster Autoscaler 与 Karpenter 都能为不可调度 Pod 提供节点，但控制模型不同。Cluster Autoscaler 通常在云侧预定义的 Node Group 之间选择，增加或减少 Group 的目标规模。Node Group 的实例类型、镜像、网络与启动配置预先绑定，运维边界清晰，适合需要固定节点产品与成熟变更流程的环境。其代价是候选形状受 Group 集合限制，新增规格常需要基础设施变更。

Karpenter 以 NodePool 和 NodeClass 类资源表达约束，在允许范围内为 Pending Pod 选择具体容量，并直接管理节点生命周期。它可以扩大实例类型、Zone 与 Capacity Type 的选择空间，也把 Drift、Consolidation、Expiration 和中断处理带入同一控制面。灵活性越高，越需要明确约束、预算与版本合同。把实例集合写得无限宽不是成熟配置，因为镜像、设备、网络和许可并不一定在所有候选上等价。

选型不应只比较谁扩容更快。需要比较目标 Provider 支持、控制面升级方式、节点镜像治理、预留与 Spot 能力、拓扑表达、DRA 集成、可观测性、故障恢复、变更审计以及团队掌握程度。一个多云平台可能在不同集群使用不同实现，但应对用户暴露统一的容量状态和 SLO，而不是泄漏所有控制器差异。

同一集群同时运行多个节点扩容器时，要避免争抢同一 Pending Pod 或管理同一节点池。若确有分区需求，应通过互斥标签、NodePool 边界和明确所有权隔离。节点上的终止 Finalizer、云实例生命周期和控制器状态也要唯一负责。双重管理的典型故障是一个控制器准备替换节点，另一个把它视为空闲并删除，导致重复采购或非预期驱逐。

扩容器不是队列系统的替代品。没有 Kueue 之类的准入控制时，大量 Pod 可同时进入 Pending，扩容器会尝试为所有 Pod 寻找节点，即使业务配额、预算或公平性并不允许它们同时运行。队列先决定哪些 Workload 值得获得逻辑配额，节点扩容器再为已选择的需求交付物理容量。两层必须通过状态和 AdmissionCheck 连接。

扩容器也不是容量承诺系统。云 Provider 可能缺货、Quota 可能耗尽、账号策略可能拒绝创建、网络地址可能不足。平台对用户承诺的应是带范围的 SLO，例如在指定区域和允许的实例集合中，某类请求有多大概率在多久内 Ready。对于必须准时开始的训练，应使用预留、容量块、长期节点或其他可保证产品，而不是把尽力而为的自动扩容包装成硬保证。

## 9. 新节点启动链与 Node Profile 门禁

云 API 返回实例标识后，节点还没有可用于训练。操作系统启动、Container Runtime、Kubelet 注册、CNI 地址分配、DNS、时间同步、证书、GPU 驱动、Device Plugin 或 DRA Driver、RDMA、存储插件、监控代理和安全策略都要成功。任何环节异常都可能出现 Node Ready 但 GPU 不可分配，或者 GPU 可见但通信与存储不满足 Profile。

平台应定义 Node Profile 状态机。第一阶段是实例已创建；第二阶段是 Node 对象已注册；第三阶段是基础网络与存储 Ready；第四阶段是设备资源发布；第五阶段是拓扑、驱动和健康标签完成；第六阶段是通过合成探针；最后才移除启动 Taint 并允许业务调度。启动 Taint 能阻止 Pod 过早绑定，避免业务容器在驱动或 RDMA 未准备时失败。

合成探针不能只运行设备枚举。对训练节点，至少验证驱动与用户态兼容、GPU 基础计算、节点内互联、必要的 RDMA 设备、DNS、对象存储和 Checkpoint 路径。对推理节点，还要验证模型存储访问、共享内存、镜像层和健康上报。探针要有超时与失败隔离，不能无限占用新节点。

节点镜像应不可变并有版本标签。Bootstrap 脚本从互联网临时下载安装驱动，会造成启动时间不可控、供应链风险和版本漂移。必要组件尽量固化到镜像，运行时只做短小、幂等且可观测的配置。镜像升级先建新池验证，再通过 Drift 或受控替换迁移，不能直接在所有运行节点原地修改。

Node Ready 时间应按阶段输出分位数。只看平均值会隐藏尾部：多数节点五分钟可用，少数节点二十五分钟卡在设备插件，训练 Gang 仍要等待最慢节点。应报告从 Unschedulable 到 Provisioning 开始、实例创建、Node 注册、设备 Ready、Profile 通过和 Pod Running 的 P50、P95 与 P99，并按 Region、Zone、实例类型、镜像版本和 Capacity Type 切分。

启动失败节点必须有隔离和回收策略。若节点注册后长时间没有设备，控制器将其标记异常、阻止业务、保留诊断证据并在预算允许时替换。无限重试 DaemonSet 可能让故障节点长期计费。直接删除又会丢失日志。平台可先采集事件、启动日志、设备诊断和云侧状态，再执行有上限的修复或替换。

## 10. ProvisioningRequest 状态机的工程含义

Quota Reservation 回答“调度政策是否愿意把额度留给这个 Workload”，ProvisioningRequest 回答“物理容量是否已经或可以被保证”。两者分开能避免一个常见竞态：Workload 认为自己已获准，Pod 大量创建，但节点扩容失败；与此同时配额被其他 Workload 消费，导致状态反复。

当 Workload 取得 Quota Reservation 后，Kueue 根据 PodSet 需求与 ProvisioningRequest 配置创建请求。外部供应控制器读取需求并尝试准备容量。只有相关 AdmissionCheck 全部 Ready，Workload 才进入 Admitted。平台 UI 要展示当前卡在哪一层：等待队列配额、等待供应请求、供应失败、预留到期、容量撤销，还是其他准入检查未完成。

Provisioned 表示供应控制器认为容量已经准备，但它不等同于应用完成。平台仍要观察 Workload 创建 Pod、Pod 绑定、节点 Profile、容器启动和业务健康。若 Provisioned 后业务对象迟迟未使用容量，BookingExpired 可以结束预留，防止资源永久闲置。到期时间需要覆盖控制器传播和 Pod 启动尾部，又不能长到让昂贵 GPU 空转。

Failed 需要可行动原因。简单写“供应失败”无法支持用户或值班处理。原因至少区分 NodePool 上限、云账号 Quota、实例类型无货、Zone 无货、约束无解、网络地址耗尽、权限拒绝、节点启动失败与控制器内部错误。暂时性失败可退避重试，确定性约束冲突应尽快拒绝，避免无效排队。

CapacityRevoked 意味着此前准备的容量不再可靠。平台不能只把 Condition 写入对象后等待用户发现。对尚未启动的 Workload，应释放或重新申请；对运行中的 Workload，要根据产品合同触发驱逐、暂停、Checkpoint 或故障恢复，并对已占用 Quota 做一致处理。撤销事件需要进入审计和 SLO，因为它代表供应承诺失效。

AdmissionCheck 的 Retry 与 Rejected 语义要进入自动化测试。Retry 通常会释放 Reservation 并让 Workload 重新排队，若外部系统持续返回 Retry，可能形成排队抖动。Rejected 会使 Workload 停用，需要清楚原因和重新激活流程。控制器升级时要测试 Condition 字段、Reason 和状态迁移，避免自动化依赖非稳定文本。

对于多 PodSet 作业，供应请求必须反映每组角色和拓扑。训练 Worker、Parameter Server、数据服务可能需要不同 Flavor。不能只保证 GPU Worker 而忽略控制角色的 CPU、存储和网络，否则 Workload 已获得昂贵 GPU，关键 CPU Pod 却 Pending。验收要从完整 Job 模板生成需求，而不是手工构造简化请求。

## 11. Spot 与按需容量的产品分层

平台不应只给用户一个“是否使用 Spot”的复选框。容量产品至少描述价格模型、可获得性、终止风险、通知渠道、替代策略、回退规则、适用工作负载、最长等待和责任边界。用户选择的不是一种实例标签，而是一组运行时合同。

适合 Spot 的训练通常具备周期 Checkpoint、确定性恢复、幂等数据读取、可重放采样、外部持久化和对中断成本的量化。若一个作业每六小时保存一次，启动需要四十分钟，被中断后重算代价可能超过价格节省。平台应把预期节省减去中断频率乘以恢复成本，得到风险调整后的成本，而不是只展示每卡小时单价。

在线推理使用 Spot 需要更多保护。Gateway 应先摘除将终止的副本，保留足够按需基线，替代副本需在模型加载和 Warmup 后才计入 Ready。若模型权重巨大、冷启动长，短通知无法完成替换。平台可以让无状态、低优先级或可降级流量使用 Spot，但不能把最低副本数也全部放在可回收容量上。

数据处理适合 Spot 的前提是分片幂等和输出提交原子化。一个 Worker 被回收后，未完成分片可以重新领取，已提交结果不会重复。若任务直接向共享文件追加，重试可能造成重复与损坏。队列或元数据服务要区分领取、租约、完成与提交，使中断成为正常控制流。

按需回退不是天然安全。Spot 不足时切换按需会改变成本；预算系统必须提前授权，不能在夜间无限采购。相反，禁止回退会扩大排队时间。平台应让 Team 在模板中声明最大按需占比、每次运行成本上限和最长等待，并由准入层执行。临时突破需要审批记录和过期时间。

混合容量 Gang 也要明确语义。一个八节点训练若七台 Spot、一台按需，其中任何 Spot 回收都可能重启整组，按需节点并没有提高成功率，反而在重启等待中继续计费。对 Gang，常见策略是整组选择同一风险等级、保留整组替代、或者使用框架真正支持的弹性成员变更。不能把异构拼接误当成容灾。

## 12. 中断时间预算与 Checkpoint 合同

中断治理必须用时间线推导。设通知到实例终止的可用窗口为总预算，减去事件传输、控制器处理、Taint 传播、应用接收信号、停止新工作、Checkpoint、上传确认、Pod 退出和安全余量，剩余时间必须非负。替代节点是否能在窗口内 Ready 是另一条并行路径，不能默认它一定快于旧节点终止。

事件传输本身会失败。云事件可能延迟，队列权限可能错误，控制器可能重启，节点网络可能已受损。应用不能把提前通知当作唯一正确性机制。Checkpoint 周期、作业重试和持久化协议要保证即使没有提前通知，损失仍在可接受恢复点目标内。通知优化的是损失和恢复时间，不是数据正确性的唯一屏障。

Checkpoint 合同包含触发、冻结、写入、提交和恢复。触发后各 Rank 停止推进到不一致状态；写入临时对象；所有必要分片成功后原子发布元数据；恢复端只读取已提交版本。只看到对象存储里出现几个文件不能判定成功。必须验证全局步数、模型、优化器、随机数状态、数据游标以及并行切分元数据的一致性。

Checkpoint 带宽要按最坏规模核算。模型与优化器状态可能远大于单次通知窗口，直接从所有 GPU 同时写对象存储会打满网络或触发限流。平台可使用本地到远端分层、异步快照、增量或分布式 Checkpoint，但每种优化都要验证恢复。写得快却无法读取，或者读取后丢失数据游标，都不是有效方案。

应用退出与 Kubernetes 驱逐期限要协调。terminationGracePeriodSeconds 过短会在 Checkpoint 完成前发送强制终止；过长又可能超过 Provider 窗口。PreStop Hook、信号处理和训练框架回调的顺序要通过故障注入观察，不能依赖文档想象。若 Drain 并发驱逐多个 Pod，存储峰值会更高，还需控制节点和集群级并发。

恢复时间目标包括发现失败、重新排队、获得配额、Provisioning、节点 Ready、镜像与权重准备、恢复 Checkpoint 和重新达到稳定吞吐。只测 Checkpoint 写入耗时会严重低估 RTO。平台应分别记录无替代容量、已有热备、按需回退和原地重试路径，给用户真实期望。

中断演练至少有三类。第一类向应用发送与终止等价的信号，验证 Checkpoint 协议；第二类驱逐 Pod 或删除节点，验证 Kubernetes 与队列恢复；第三类在隔离 NodePool 使用 Provider 官方事件或测试机制，验证云事件到控制器全链路。前两类通过不能替代第三类，真实路径缺失时必须标记 SKIPPED。

## 13. Karpenter Disruption 控制面

Karpenter 管理的节点通常通过终止 Finalizer 参与删除。控制器先 Taint 节点阻止新 Pod 调度，再驱逐可迁移 Pod，必要时创建替代容量，最后删除底层实例并移除 Finalizer。这个流程让节点删除成为受控状态机，但不能保证每种外部强制终止都有充分时间完成。

自愿 Disruption 包括 Empty、Consolidation 和 Drift 等原因。Empty 处理没有业务 Pod 的节点；Consolidation 尝试删除或替换以降低成本；Drift 处理 NodePool 或 NodeClass 期望与现有节点不一致。Expiration 与 Node Repair 具有不同强制边界。实际可用 Reason、策略值和预算计算会随目标版本变化，平台必须把文档版本与控制器版本绑定。

NodePool Disruption Budget 控制自愿操作速率。百分比预算在小池中存在取整效应，固定数值在大池中可能过于保守。多个预算可按时间段限制，例如业务高峰冻结 Consolidation、维护窗口允许 Drift。预算设计要结合副本、PDB、Topology 和替代启动时长，不能只写一个全局百分比。

PodDisruptionBudget 针对自愿驱逐保护应用可用副本，但它只对匹配 Pod 集合生效。选择器错误、期望副本与实际副本不一致、多个 PDB 交叠都会造成意外。一个节点上只要有 Pod 受阻，整节点可能无法完成自愿删除。值班工具应列出阻塞节点的具体 Pod 与 PDB，而不是只显示“无法合并”。

do-not-disrupt 注解适合显式保护不能安全迁移的 Pod，但它不是永久节点租约。官方边界中，Spot Interruption、Expiration、Node Repair 和手工删除等强制路径可能不受其保护。平台如果把它包装成“不会中断”，就是错误承诺。使用它的 Workload 还应有最长运行、审批和恢复方案，避免整个节点池永远无法升级。

Drift 替换要先验证新配置可交付。NodeClass 更新镜像、子网、安全组或启动脚本后，若新节点无法 Ready，旧节点不应批量退出。发布流程先创建 Canary 节点，运行 Profile 探针，再逐批迁移。预算只是并发限制，不能替代新版本健康门禁。

Node Repair 针对硬件或节点健康异常，通常需要比成本合并更快。对 GPU Xid、网络链路和磁盘故障，平台应关联设备健康、Node Condition 和作业错误。修复策略可能重启组件、隔离设备、排空节点或替换实例。每个动作都要防止故障风暴时同时移除过多容量。

## 14. Consolidation 与拓扑保护

Consolidation 算法在当前 Pod 集合上证明可迁移，并不自动知道下一小时会到来什么大 Job。若平台长期运行固定形状训练，可以从历史队列得到未来需求分布，为某些拓扑域保留最小完整块。保留会降低即时利用率，但减少大作业等待和反复扩容，属于可量化的容量保险。

保护拓扑不能依赖节点名字。应按 Zone、Rack、网络 Fabric、Block 或平台定义 Domain 计算。对于必须同域的八节点 Job，保护目标是至少一个域拥有八个兼容节点或可保证扩到八个。若每个域各留七个，总空闲节点很多，仍然不可用。看板要显示“最大可调度形状”，而不仅是空闲数量。

Consolidation 替换可能改变实例类型。对普通无状态 Pod，只要资源足够可能无感；对 GPU 训练，GPU 型号、显存、NVLink 拓扑、网卡和驱动都会影响正确性与性能。NodePool 约束应只包含经过 Profile 验证且产品合同允许互换的规格。价格更低不是等价证明。

替换过程还会产生暂时双份容量。先建新节点再删旧节点可提高安全性，但会短期超过预算或云 Quota；先删后建则暴露容量不可得风险。平台应为替换预留 Burst Headroom，并在 Quota 不足时阻止自愿合并。不能为了省每小时费用制造长时间服务降级。

镜像与模型缓存会改变经济性。删除一个低利用节点可以节省计算费用，但替代节点要重新拉取数百 GB 镜像与权重，占用出口、对象存储和时间。成本模型应加入迁移流量、缓存重建和冷启动期间的冗余副本。频繁合并造成的抖动可能比保留节点更贵。

一个稳健门禁会模拟删除候选节点后的全局可调度性。它检查当前 Pod 迁移、PDB、do-not-disrupt、Topology Spread、卷 Zone、DRA 设备和未来保留形状；还检查替代候选的 Provider 容量和 Node Profile。无法证明安全时返回阻止原因，不以强制驱逐掩盖模型缺口。

## 15. 扩缩容风暴、退避与幂等

当数百个 Pod 同时 Pending，多个控制器可能在短时间产生大量供应请求。若每次调度事件都触发新计算、每个失败立即重试，就会形成扩容风暴，撞击云 API 限流、账号 Quota、地址池和控制面。系统需要去重、批处理、指数退避、抖动和每池并发上限。

供应操作必须幂等。控制器重启或网络超时后，无法确定创建请求是否成功时，应以稳定请求标识查询，不得直接再次创建。节点、云实例、ProvisioningRequest 和 Workload 之间要有可追踪 Owner 或标签。孤儿实例既浪费成本也可能绕过平台安全配置。

扩容退避应区分失败类别。Provider 暂时无货适合在允许实例与 Zone 间切换并退避；权限拒绝、无效规格和硬约束冲突重试不会自愈，应快速失败并告警；账号 Quota 耗尽需要容量团队处理；节点启动探针失败可尝试有限替换，同时保留镜像版本和故障证据。

缩容也会形成风暴。批量作业结束后大量节点变空，若同时删除，会冲击日志回收、存储卸载、云 API 和后续突然到来的作业。Disruption Budget、删除并发和最小存活时间可以平滑回收。节点刚 Ready 便被合并通常说明扩容与合并策略互相振荡。

振荡的典型根因包括请求估计变化、队列准入反复、候选实例短缺、Consolidation 观察窗过短和工作负载周期性突发。平台应记录每个节点从创建到删除的寿命与原因。大量寿命仅几十分钟的昂贵 GPU 节点是重要信号，应追溯谁触发、为何未使用、为何又删除。

控制面恢复测试需要主动重启 Autoscaler、Kueue Controller 和事件处理器，验证状态可从持久对象重建。不能依赖进程内缓存保存唯一映射。重启后不得重复采购、丢失预留、错误释放 Quota 或漏掉中断事件。

## 16. 云侧限制是调度输入

## 写在最后

弹性容量之外，许多组织还保留着成熟的 HPC 调度体系，需要明确两者的边界。下一篇：[Slurm GPU 集群与 Kubernetes 的边界和协同](/source/AI-Infra/4-AI平台工程/16-SlurmGPU集群与Kubernetes的边界和协同)。