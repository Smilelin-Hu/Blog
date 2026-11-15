# 面向 AI 工作负载的 Kubernetes 基础

训练作业一直显示 Pending，团队第一反应是“GPU 不够”；Notebook 打开后频繁重启，用户认为“平台不稳定”；模型服务的 Pod 全部 Running，但请求仍然没有进入任何实例。三个现象都发生在 Kubernetes，却对应完全不同的状态链：调度约束、容器资源和服务就绪。

![面向 AI 工作负载的 Kubernetes 基础](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l04_01.png)

如果只会执行 `kubectl get pods`，这些问题都会被压缩成几个模糊单词。真正的平台工程需要从用户声明一路追到控制器、调度器、kubelet、容器运行时、存储、网络和应用探针，并判断哪一层尚未兑现条件。Pod 不是一台小虚拟机，Running 也不是业务成功。

本文建立 AI 工作负载所需的 Kubernetes 基础模型。它不以命令大全组织内容，而从四种对象语义出发：交互式 Notebook 为什么需要长驻与可恢复环境，训练为什么需要完成和重试语义，Pipeline Task 为什么依赖制品与前后关系，在线服务为什么需要持续副本、就绪与流量。

判断一次 Kubernetes 故障时，可以先问五个问题：对象是否通过 API 准入；Pod 是否被调度到节点；kubelet 是否完成镜像、Sandbox、卷和初始化；应用进程是否存活；应用是否已经能承担产品流量。每个问题都有不同事件、状态和责任人。

最后的实验会用确定性模拟与四节点 kind 两条路径部署 CPU 模拟的 Notebook、训练 Job 和在线服务，加入 Namespace、ResourceQuota、PVC、节点标签、污点、容忍、Init Container 与探针，并故意产生 QuotaExceeded、UntoleratedTaint、UnboundPVC、ImagePullBackOff、OOMKilled 和 ReadinessProbeFailed。

## 1. Pod 是调度和运行的最小共同命运单元

Pod 包含一个或多个紧密协作容器，共享网络命名空间、IP、端口空间和声明的卷。调度器为整个 Pod 选择一个节点，kubelet 在该节点准备并运行全部容器。容器不会被分别调度到不同机器，因此放进同一 Pod 就意味着它们共享位置与生命周期边界。

这使 Pod 适合主进程和必要辅助进程，例如推理服务器与本地代理、训练进程与低频制品上传 sidecar。但它不适合把八个分布式训练 worker 都塞在一个 Pod：它们需要跨节点、独立资源与共同准入，应由更高层工作负载控制器组织多个 Pod。

### 1.1 Pod 不是可以长期修补的虚拟机

Pod 被设计为相对可替换的对象。容器崩溃时 kubelet 可能在同一 Pod 内重启容器；节点故障或控制器替换时，通常创建具有新 UID 和新 IP 的 Pod。应用不应把本地进程或临时文件当作跨 Pod 永久身份。

进入 Pod 手工安装依赖只能改变当前实例，重建后消失，也无法审计与复现。正确做法是把运行环境固化到镜像或版本化模板，把配置放入 ConfigMap 或受管对象，把持久结果写入卷或对象存储。调试修改应回到声明，而不是变成运维传说。

Pod 的 `spec` 大部分字段在创建后不可随意修改。控制器更新 Deployment 模板时会创建新 Pod，而不是把旧 Pod 原地变成另一个镜像。这个替换语义解释了发布为什么需要就绪、滚动策略和终止宽限。

同一 Pod 内的容器可以通过 localhost 通信，也能共享卷，但资源限制仍按容器或 Pod 级语义配置。某个 sidecar 没有请求和限制，可能影响调度估算与 QoS；辅助进程抢占内存，也可能让主训练容器被 OOM。辅助不等于免费。

### 1.2 Job、Deployment、StatefulSet 和 DaemonSet 回答不同问题

Job 表达一次要完成的任务。它创建一个或多个 Pod，按完成数量与失败策略重试，达到目标后进入完成状态。训练、离线评测、数据转换和批量推理通常从 Job 语义开始，因为用户需要“结束并留下结果”。

Deployment 表达持续维持一组可替换、通常无稳定个体身份的副本。模型推理 API、Notebook Gateway 和平台控制服务适合 Deployment。它通过 ReplicaSet 滚动替换 Pod，关注期望副本与可用副本，而不是完成多少次。

StatefulSet 为每个 Pod 提供稳定序号、网络身份和持久卷关联，并按顺序创建或更新。需要稳定成员身份、分片或每实例存储的服务可能使用它，但有状态并不自动等于数据安全。应用仍需复制、备份、一致性与故障恢复知识。

DaemonSet 确保符合条件的每个节点运行一个 Pod。GPU Device Plugin、DCGM Exporter、日志代理、网络或存储节点组件通常使用 DaemonSet，因为职责绑定节点。它不是“多跑几个副本”的 Deployment，调度、升级与故障域都围绕节点集合。

选择控制器要先看产品语义。任务是否应结束，实例身份是否稳定，是否每个节点一份，副本能否互换。用 Deployment 跑训练会让成功退出的容器不断重启；用 Job 跑长期服务，服务失败后的可用副本与滚动发布难以表达。

### 1.3 Service 和 EndpointSlice 只把流量送给 Ready 后端

Pod IP 会随着替换变化，Service 提供稳定虚拟地址和端口，使用标签选择后端。控制平面为匹配且就绪的 Pod 维护 EndpointSlice，数据面把流量转发到这些端点。Service 本身不会让应用健康，也不会加载模型。

如果 Pod Running 但 Readiness Probe 失败，它通常不会成为 Service 的正常就绪端点。用户看到两个副本 Running，却可能没有一个 Ready，Service 请求超时。排查要同时读取 Deployment 可用副本、Pod Conditions、探针事件和 EndpointSlice。

Service selector 必须匹配 Pod 标签。一次模板改名或标签漂移会造成空端点，而容器完全健康。平台状态应把“没有就绪端点”与“没有 Pod”分开；前者可能是探针或 selector，后者可能是控制器或配额。

Headless Service 不提供普通集群虚拟 IP，而让客户端发现具体 Pod 地址，常用于 StatefulSet 或分布式成员发现。它不自动完成训练框架 rendezvous，应用仍需决定成员列表、Leader 和失败行为。

入口层还可能有 Gateway、Ingress、负载均衡与服务网格。请求失败时，应从外到内检查路由对象、Service 端口、EndpointSlice、Pod Ready、容器监听地址与应用日志，而不是直接重启所有 Pod。

### 1.4 Namespace 是管理边界，不是绝对安全边界

Namespace 为同一集群中的对象提供名称范围，便于按项目应用 RBAC、ResourceQuota、LimitRange、NetworkPolicy、成本标签和生命周期。两个 Namespace 可以都有名为 `training` 的 Job，它们通过 Namespace 区分。

平台常把项目空间映射为 Namespace，但项目通常还包含身份组、预算、数据授权、制品位置和支持等级。只创建 Namespace 不等于完成项目产品。Namespace 是承载这些策略的 Kubernetes 边界之一。

Namespace 也不是虚拟集群。租户共享 API Server、调度器、节点内核、网络与许多集群级控制器。RBAC 与策略配置错误、特权容器或节点漏洞可能跨边界。高风险多租户需要独立集群、沙箱运行时或更强隔离，这里只讨论基础软隔离。

默认 Namespace 容易积累无人所有资源。平台应要求对象带项目与责任标签，限制用户在 default 创建，项目关闭时执行保留与清理。Namespace 删除会级联大量命名空间对象，必须先评估 PVC、制品和外部依赖。

## 2. 一个容器真正开始工作前经过哪些阶段

Pod 被 API Server 接受后，调度器选择节点并写入绑定；目标节点 kubelet 观察 Pod，调用容器运行时创建 Sandbox 与网络，准备卷和 Secret，拉取镜像，顺序运行常规 Init Container，再启动应用与 Sidecar，最后根据探针更新状态。

这条链中每一段都可能等待。Pending 不只代表调度；Pod 已绑定但卷未挂载、Sandbox 未创建时也可能尚未运行。观察 `spec.nodeName`、Pod Conditions、containerStatuses 与 Event，才能确定停在哪一段。

### 2.1 调度只负责选择节点

调度器读取尚未绑定的 Pod，过滤不满足资源、标签、污点、卷拓扑和亲和等条件的节点，为可行节点评分，选择一个并写绑定。它不拉镜像、不启动容器，也不验证应用会不会监听端口。

Pod 没有 NodeName 且 Condition PodScheduled=False 时，重点看调度事件。常见原因是 Insufficient CPU/Memory、扩展资源不足、NodeSelector 或 Affinity 不匹配、污点未容忍、PVC 未绑定、拓扑约束无法满足。事件比笼统 Pending 更接近原因。

绑定后调度器的主要任务结束。随后等待镜像或卷，不能继续归因于“调度慢”。平台看板应把提交到绑定、绑定到容器启动、启动到 Ready 分开计时，容量、镜像和应用团队才能各自改进。

直接设置 `nodeName` 会绕过普通调度选择，通常不应作为平台接口。它把节点身份泄漏给用户，绕过部分策略，并在节点不可用时缺少重新选择。应使用标签、资源类和约束表达意图。

### 2.2 Sandbox、网络和镜像都可能阻止启动

kubelet 通过 CRI 请求容器运行时创建 Pod Sandbox，通常包括基础隔离和网络命名空间。CNI 插件配置网络并分配地址。Sandbox 创建失败可能来自运行时、CNI、地址耗尽、节点磁盘或配置，不是用户镜像进程错误。

镜像拉取失败常显示 ErrImagePull，随后进入 ImagePullBackOff。原因包括镜像名或摘要错误、仓库不可达、身份 Secret 缺失、证书、速率限制和节点磁盘不足。BackOff 表示 kubelet 正在延迟重试，不是一个独立根因。

大型模型运行环境镜像会显著增加启动时间。即使镜像可拉取，解压层、写入节点盘与并发拉取也会造成长尾。平台可以建设镜像缓存、预取和分层，但用户状态应显示“已绑定，正在准备镜像”，不要继续显示普通排队。

镜像拉取策略影响可复现与成本。不可变摘要配合 IfNotPresent 通常更可预测；可变 tag 可能因缓存得到不同内容；Always 并不一定每次下载全部层，却需要解析与验证。生产平台应优先不可变镜像版本。

### 2.3 Init Container 把启动前置条件显式化

常规 Init Container 按声明顺序逐个运行并成功结束，之后应用容器才启动。它适合检查数据、生成配置、修复卷权限或等待必要依赖。每个 Init 可以使用不同镜像和权限，并通过共享卷把结果交给应用。

如果 Init Container 失败，Pod 可能显示 Init:CrashLoopBackOff 或特定进度，应用容器根本没有启动。此时查看应用日志不会有结果，应查询对应 Init 容器的当前与上一次日志、退出码和 Event。

Init 不是无限等待脚本的垃圾桶。循环等待外部服务没有超时，会让 Pod 永久停在初始化，控制器只看到未就绪。前置条件如果由其他 Kubernetes 对象表达，优先通过控制器和 Condition 协调；必须等待时设置超时、Reason 和诊断。

原生 Sidecar 在现代 Kubernetes 中作为可重启的 Init Container 特例表达，能够在主容器之前启动并在 Pod 生命周期内持续运行。它与传统常规 Init 的完成语义不同。模板清单要绑定集群版本，不应把所有 `initContainers` 都理解为运行即退出。

### 2.4 卷挂载和 Secret 注入发生在应用启动前

Pod 引用 PVC 时，卷可能需要等待绑定、拓扑选择、Attach 与 Mount。RWO 卷已挂到另一节点、CSI 驱动异常、节点无法访问存储、权限或文件系统错误，都能阻止容器启动。Pod 已有 NodeName 不代表卷已准备。

ConfigMap 与 Secret 可以通过环境变量或卷注入。环境变量在容器启动时确定，源对象更新不会改变已有进程环境；卷投射可以在一段时间后更新文件，但应用是否重载取决于自身。把配置变化等同于应用已生效，是常见误判。

Secret 是 API 对象，不意味着默认就是外部密钥保险箱。需要 RBAC、etcd 加密、最小挂载、短期身份和日志脱敏。工作负载不应把 Secret 值写入命令参数、Event 或环境转储。

挂载成功后，应用仍可能因文件权限、路径、内容格式或数据版本失败。平台应区分 VolumeMountFailed 与应用读取失败，统一运行标识连接 kubelet Event 和容器日志。只有这样存储团队与训练团队不会互相推诿。

## 3. Requests、Limits 与 QoS 影响调度和生存

Kubernetes 的资源请求用于调度与资源保证，限制用于运行时约束。调度器根据 Requests 判断节点能否容纳 Pod，而不是根据实时平均使用；因此请求过大会造成表面空闲却无法调度，请求过小会让节点承诺过多并增加争用与驱逐。

CPU 以可压缩资源处理，超过限制通常被节流；内存不可压缩，达到限制或节点压力可能触发 OOM 与驱逐。GPU 等扩展资源通常按整数请求，并通过设备插件或 DRA 等机制分配，语义与 CPU 时间片不同。

### 3.1 Request 是规划承诺，不是最低性能的万能保证

容器声明 `requests.cpu: 2`，调度器为装箱计算两核需求。运行时若没有 CPU limit 且节点空闲，进程可能使用更多；若竞争出现，CPU shares 与策略影响分配。Request 帮助获得相对资源份额，却不自动提供固定物理核心和低抖动。

内存 Request 参与调度，并影响 QoS 与驱逐选择，但容器可以在 Limit 允许范围内使用更多。节点把多个请求较小、实际峰值很大的 Pod 放在一起，内存压力时会发生回收与驱逐。AI 数据加载和模型加载峰值应进入容量实验，不能只用稳定阶段平均值。

Request 过大也有代价。训练容器声明 64 CPU 实际只用 8，会让其他工作无法进入，降低利用率；在线服务为峰值保留大量内存可能是 SLO 成本，不能简单认定浪费。平台需按工作负载类别给出模板和建议，而不是统一缩小。

Init Container 的资源计算有特殊性：常规 Init 顺序运行，调度所需会考虑有效 Init 需求与应用容器组合，而不是把所有 Init 与应用简单相加。包含原生 Sidecar 时语义更复杂。生产容量判断应使用调度器实际规则和版本测试。

### 3.2 Limit 对 CPU 与内存的后果不同

CPU Limit 通常通过 cgroup 带宽限制。进程在配额周期内使用完额度会被 throttled，但不会因“超过 CPU”直接被杀。延迟敏感推理可能在节点仍有空闲 CPU 时被限制，表现为高尾延迟。观察 throttling 指标而不只看平均 CPU。

内存 Limit 接近硬上限。容器匿名内存、文件缓存等计入相关 cgroup 后超过限制，内核可能 OOM Kill 进程；containerStatuses 显示 terminated reason OOMKilled，控制器或 kubelet 再按策略重启。增加重启次数不会修复稳定超限。

没有内存 Limit 并不等于安全。容器可消耗节点大量内存，触发 NodePressure，影响其他 Pod 并被驱逐。过低 Limit 又会让模型加载稳定失败。平台需要结合模型大小、运行时峰值、缓存和 Sidecar 设定，并用真实负载验证。

现代 Kubernetes 支持 CPU 与内存的原地调整能力，但具体字段、策略与版本要按集群核验。它不适用于 GPU 等所有资源，也不消除应用对资源变化的适配。平台不能因为存在 In-Place Resize 就承诺任何运行中训练都可无损改资源。

### 3.3 Guaranteed、Burstable 与 BestEffort 是驱逐与资源管理信号

传统容器级规则下，Pod 中每个容器都为 CPU 和内存设置相等的 Request 与 Limit，Pod 获得 Guaranteed QoS；至少设置一项但不满足 Guaranteed 的通常是 Burstable；完全没有 CPU/内存 Request 与 Limit 的是 BestEffort。

QoS 会影响节点资源压力下的驱逐和 cgroup 组织，但它不是业务优先级。Pod Priority 与 Preemption 是另一套机制，调度器的抢占不会简单按 QoS 选择。把 Guaranteed 理解为“永不驱逐”或“最高优先级”都是错误的。

AI 训练常希望资源可预测，可能采用 Guaranteed CPU/Memory，并配合 GPU、CPU Manager、Topology Manager 与内存策略。在线推理也可能需要稳定。Notebook 探索更适合有限 Burst，但仍要设置合理上限，避免一个用户拖垮节点。

Sidecar、Init 和注入容器都会影响 QoS。用户主容器配置完美，但自动注入的代理缺少相等 Request/Limit，整个 Pod 可能变为 Burstable。平台模板与 Admission 需要检查完整 Pod，而不是只看业务容器。

### 3.4 GPU 扩展资源不能照搬 CPU 超卖思路

传统 Device Plugin 向 kubelet 注册例如 `nvidia.com/gpu` 的扩展资源，节点在 Capacity/Allocatable 发布整数数量。容器通常在 limits 中请求 GPU，调度器根据已分配数量选择节点，kubelet 在启动时把具体设备注入容器。

扩展资源通常不可超额分配，也不能用小数直接表示“半张 GPU”，除非厂商通过 MIG、时间切片、MPS 或其他资源抽象发布新的资源语义。调度成功只说明数量与约束满足，不保证显存、互联、健康或性能隔离。

DRA 提供 ResourceClaim、DeviceClass 等更丰富的设备请求与选择模型，适合表达设备属性和共享。它与传统扩展资源的生态、驱动与集群版本需要分别核验。平台应提供稳定资源产品，避免用户同时理解所有底层机制。

kind 实验使用节点标签 `accelerator.training.invalid/class=simulated-gpu` 模拟位置选择，不创建真实 GPU 资源，也不证明设备分配或隔离。真实 GPU 的驱动、Device Plugin、CDI、DRA、MIG 与健康将在后续篇目分别实验。

## 4. 调度约束是一门组合语言

节点标签、NodeSelector、Affinity、Taint、Toleration 和 TopologySpreadConstraints 都会影响 Pod 去哪里，但它们表达的关系不同。把所有要求都堆成硬约束，资源明明存在也可能没有可行节点；全部写成偏好，又可能把敏感或昂贵工作放错位置。

有效设计先区分三类意图：必须满足的安全与硬件条件，尽量满足的性能与成本偏好，以及在一组 Pod 之间维持的放置关系。每类使用合适机制，并在平台 API 中用产品语言表达。

### 4.1 Label 与 Selector 建立可查询分类

Label 是键值元数据，Selector 按精确值或集合筛选对象。节点可标记区域、资源池、硬件类别和合规属性，Pod 用 NodeSelector 或 NodeAffinity 选择。工作负载标签又被 Deployment、Service、NetworkPolicy 和成本系统使用。

标签值必须由可信控制面维护。若 kubelet 或租户能给节点设置“合规”或“高安全”标签，受攻击节点可能把自己伪装成目标。官方建议安全隔离标签使用节点无法自行修改的受限前缀并配合 NodeRestriction 等机制。

稳定标签表达长期语义，而不是临时状态。把 `free-gpu=true` 写成节点标签，由外部脚本频繁改动，会与调度缓存、并发分配和实际数量产生竞态。动态容量应由资源或调度插件表达，标签适合类别与属性。

Selector 是 AND 关系时要注意组合。Pod 同时要求 pool=training、accelerator=simulated-gpu、zone=zone-a，节点必须全部满足。没有候选节点时，调度事件通常指出不匹配，但平台还应展示哪些约束来自用户、模板、队列或策略。

### 4.2 Taint 排斥，Toleration 只允许进入

Taint 放在节点上，以 key、可选 value 和 effect 表达排斥。NoSchedule 阻止没有匹配 Toleration 的新 Pod；PreferNoSchedule 是软排斥；NoExecute 还会影响已运行 Pod，并可配合 tolerationSeconds 延迟驱逐。

Toleration 表示 Pod 可以容忍某个 Taint，不表示它一定选择这些节点。训练 Pod 容忍 `dedicated=training:NoSchedule` 后，如果没有 NodeSelector 或 Affinity，它也可能去普通节点；专用池通常同时使用污点排除普通 Pod、使用选择约束吸引目标 Pod。

系统自动添加的节点状态污点影响故障行为，例如 NotReady、Unreachable、MemoryPressure、DiskPressure。Pod 可能拥有默认容忍一段时间，节点短暂失联不会立即重建；长时间后被驱逐。分布式训练对成员失联的处理要结合这些时间和框架超时。

NoExecute 不是关机按钮。驱逐经过 Pod 终止与控制器替换，Stateful 卷可能需要分离，PDB 对某些驱逐生效但不是所有情况。使用污点维护节点前，平台要评估工作负载检查点与恢复成本。

### 4.3 Node Affinity 与 Pod Affinity 表达硬软条件

NodeAffinity 的 requiredDuringSchedulingIgnoredDuringExecution 是硬条件：调度时必须满足；节点标签后来变化时，不会自动把已运行 Pod 迁走。preferredDuringSchedulingIgnoredDuringExecution 是带权重偏好，没有满足仍可调度到其他可行节点。

硬条件适合数据区域、设备类别或法规要求；软条件适合靠近缓存、降低成本或优先某种型号。把性能偏好误写成硬条件，会在首选池满时让工作负载无限 Pending，降低平台弹性。

PodAffinity 和 AntiAffinity 根据其他 Pod 标签与拓扑域决定共置或分散。推理副本可使用反亲和避免全在同一节点，紧密协作服务可倾向同一区域。它们的计算成本和标签选择要控制，避免大集群调度变慢。

Affinity 规则中的 topologyKey 定义关系所在域，例如 hostname 或 zone。若节点缺少该标签，域计算可能与预期不同。平台维护标准拓扑标签并验证覆盖，不让用户依赖云厂商偶发或不可信标签。

### 4.4 Topology Spread 控制分布，不等于训练共置

TopologySpreadConstraints 以目标 Pod 选择器、topologyKey、maxSkew 和 whenUnsatisfiable 控制副本在域之间的偏斜。在线推理可以跨节点或区域分布，提高故障容忍；当某域容量不足，可选择 DoNotSchedule 硬阻止或 ScheduleAnyway 软优化。

Spread 关注计数平衡，不知道 GPU 互联性能。分布式训练可能恰恰需要多个成员处于同一高速网络域，而在线服务希望分散。二者不能共用“跨区分布就是高可用”的单一模板。

约束的 Pod selector 必须匹配正确工作负载。若标签遗漏，调度器计算不到同组 Pod，Spread 形同虚设；若 selector 太宽，不相关服务互相影响。控制器生成稳定运行标签，平台测试实际分布。

多条 TopologySpreadConstraints 共同生效，和 NodeAffinity、Taint、资源、PVC 拓扑继续求交集。设计评审应从所有硬约束求可行集合，并用调度仿真或预生产验证，而不是逐条看起来都合理。

## 5. 四类 AI 工作负载为什么不能使用同一模板

Notebook、训练、Pipeline Task 和在线服务都会创建 Pod，却拥有不同时间、失败和结果语义。一个通用表单暴露镜像、命令与 GPU 数量，无法表达会话空闲、任务完成、依赖缓存、流量就绪和回滚。

平台可以复用底层安全、身份、资源和观测模板，但上层产品需要不同控制器与默认。判断模板是否合适，要看用户何时认为成功、失败后谁重试、数据怎样持久、资源何时释放。

### 5.1 Notebook 是长驻交互会话，不是永不结束的训练

Notebook 用户期望快速打开、持续交互、保存工作区并可在空闲后恢复。进程可能长期无请求，但仍占用内存、GPU 和卷。平台需要会话、空闲检测、暂停、恢复、存储与用户身份，而不仅是一个 Pod。

使用 Deployment 可以在 Pod 故障后维持一个副本，但滚动替换可能同时产生新旧会话；用户工作区必须在持久卷或外部仓库，不能依赖 emptyDir。StatefulSet 也能提供稳定卷关联，但仍需要会话路由与升级策略。

Notebook 的 Readiness 不应只测 Jupyter 进程端口，还可验证工作区挂载、身份代理和必要扩展。Liveness 过于激进会在长计算阻塞时重启，导致交互状态丢失。Startup Probe 保护首次加载时间较长的环境。

GPU Notebook 通常允许探索弹性，却应有最大时长、空闲回收和数据权限。自动回收前通知并保存；用户可申请延长；生产密钥不应长期挂在会话。交互便利与多租户风险需要资源产品明确交换。

## 写在最后

Kubernetes 语义之上，GPU 节点还需要一整套软件栈才能把设备变成可调度资源。下一篇：[GPU 节点软件栈与 NVIDIA GPU Operator](/source/AI-Infra/4-AI平台工程/05-GPU节点软件栈与NVIDIAGPUOperator)。