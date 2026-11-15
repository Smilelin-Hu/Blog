# Kueue 队列、配额、公平共享与抢占

一家公司的 GPU 集群有八张 A100。研究团队与产品团队各自被承诺四张保底额度。上午，研究团队只使用两张，产品团队便临时借走一张，总使用量达到七张；中午，研究团队提交一个需要两张 A100 的高优先级恢复作业。物理上只剩一张空闲卡，产品团队却正在使用五张，超过自己的四张保底。系统应当回收产品团队借用的那一张，使研究团队恢复到自己的保底范围，而不是随机终止任意一个运行作业。

![Kueue 配额与借用回收](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l12_01.png)

到了下午，两个团队都提交大量开发作业。只按提交时间排序，先批量提交的一方可能连续占满刚释放的资源；只按当前使用量排序，又会忽略过去一周持续使用的差异；只给高优先级作业开抢占，会让低优先级训练反复丢失数小时进度。队列系统必须同时表达保底、可借、可借出、历史使用、权重、优先级、抢占范围和失败成本。

Kueue 在 Kubernetes 之上增加工作负载级准入控制。它不替代 kube-scheduler 为 Pod 挑选具体节点，也不把云资源预算变成设备本身；它回答的是：一个完整 Workload 现在是否可以进入执行阶段、应从哪个资源品类扣减多少配额、是否允许借用、哪些额外检查必须完成，以及资源不足时是否可以回收已准入工作负载。

本文先给出四个最重要的结论。

第一，物理容量、Kubernetes ResourceQuota 与 Kueue Quota 不是同一概念。物理容量说明集群实际有什么；ResourceQuota 限制 Namespace 里对象累计请求；Kueue Quota 决定等待型工作负载何时获得组织额度。ClusterQueue 中还有八张 GPU 配额，不能证明节点当前真有八张可放置 GPU；节点空闲八张，也不能证明某租户有权使用。

第二，`nominalQuota` 是保底与分享计算的基准，不是简单的硬上限。加入同一 Cohort 的 ClusterQueue 可以借用其他成员暂时未使用且允许借出的额度。`borrowingLimit` 限制借方最多超出自己的名义额度多少，`lendingLimit` 保护贷方至少保留多少不被借走的空间。借用提高利用率，但借来的额度可能因原所有者回收或公平策略而被抢占。

第三，公平共享至少有两个不同位置。Admission Fair Sharing 在同一个 ClusterQueue 内部，根据来源 LocalQueue 的历史资源使用与权重调整新 Workload 的准入顺序；Preemption-based Fair Sharing 在 Cohort 竞争与抢占中比较 ClusterQueue 或层级 Cohort 的份额。两者都不是“轮流运行一个作业”，也不保证每一分钟完全平均，而是让长期份额向权重目标收敛。

第四，Kueue 抢占的是 Workload 准入，不是直接挑某个 Pod 释放一张 GPU。Victim Workload 被标记 Evicted，集成控制器 Suspend 或停止其 Job，配额释放后 Preemptor 才有机会准入。是否能保存检查点、实际多久释放 GPU、Pod Priority 是否又在节点层触发另一套抢占，仍由工作负载控制器、运行时与 kube-scheduler 共同决定。

本文将用两个租户、A100 与 L4 两种 ResourceFlavor 和一个 Cohort，逐步演算保底、借用、借出限制、公平顺序、名义额度回收与高优先级抢占。实验的模拟路径验证状态和算术；真实路径只读取指定 Kubernetes Context 中的 ClusterQueue、LocalQueue 与 Workload。没有安装 Kueue 的专用环境时，真实路径必须标记 SKIPPED，不能用模拟 PASS 替代版本兼容证据。

## 1. 为什么“集群有多少卡”回答不了“谁现在能运行”

GPU 平台的资源问题至少有四个维度：设备是否真实存在、当前是否空闲、组织是否授权、时间窗口内是否符合预算。把它们压成一个“剩余 GPU”数字，会产生错误准入和错误扩容。

### 1.1 物理容量描述设备事实

节点 Capacity 与 Allocatable 来自设备插件和节点状态。八张 A100 可能位于两台四卡节点，也可能分布在八台单卡节点；某些卡可能 Unhealthy，某些节点因网络或驱动被隔离。物理容量需要同时带型号、节点 Shape、拓扑、健康与可供给状态。

Kueue 在不启用拓扑感知调度时主要管理配额，不保证已预留的 Workload 一定能被 kube-scheduler 放下。即使 ClusterQueue 显示四张 A100 可用，节点亲和、卷拓扑、污点或碎片仍可能让 Pod Pending。

### 1.2 组织配额是资源使用权

企业不会把所有空闲卡完全按先到先得分配。产品团队承担在线 SLO，需要恢复保底；研究团队允许突发借用；外部合作项目只有固定上限；生产事故作业具有更高优先级。配额把预算和治理规则转换为机器可执行对象。

组织配额不是给每支团队永久划出物理节点。Kueue 可以让多个 ClusterQueue 共享 Cohort，空闲额度被借用，需求回来时按策略回收。这样保留承诺，同时减少静态分区的长期闲置。

### 1.3 Kubernetes ResourceQuota 与 Kueue Quota 作用时间不同

ResourceQuota 通常在 API 创建对象时限制 Namespace 内资源请求总量。如果一个团队创建大量 Suspend Job，它们的 Pod 尚未运行，传统配额很难提供跨团队排队、公平历史和借用策略。Kueue 围绕 Workload 建立等待队列，在解除 Suspend 以前决定是否获得额度。

两者可以并存。ResourceQuota 是 Namespace 安全上界，防止对象或运行资源无限增长；Kueue 负责工作负载排队和组织份额。两者数值不一致时，要明确谁先拒绝和如何解释，不能让用户看到两个都叫 QuotaExceeded 却属于不同控制层。

### 1.4 同时使用上限与累计预算也不同

ClusterQueue Quota 主要约束同时保留或使用的资源量。团队四张 GPU 运行十分钟和运行十天，在某个时刻都占四张。若组织还限制每月 GPU 小时，需要 FinOps 预算控制器、AdmissionCheck 或外部策略计算累计使用。

因此“每月一万 GPU 小时”不能直接写成 `nominalQuota: 10000`。名义额度单位仍是资源数量。时间累计预算可以影响队列停止、优先级、借用许可或 AdmissionCheck，但属于另一条账本。

### 1.5 容量、额度与可放置性要分别显示

用户提交八卡训练，门户至少给出 QuotaFeasible、PlacementFeasible 和 Provisionable 三个判断。QuotaFeasible 说明 ClusterQueue 与 Cohort 能否提供对应 Flavor 额度；PlacementFeasible 说明当前节点形状与拓扑能否放下；Provisionable 说明自动供给能否在期限内补齐。

只显示 Pending 会让用户无从行动。额度不足找队列管理员，节点碎片由调度团队处理，云容量售罄由供应团队处理。统一状态可以给出 PrimaryBlocker，但保留其他层的证据。

### 1.6 长驻服务与批作业需要不同预算语义

训练 Job 有明确完成点，释放额度后下一个 Workload 运行；推理 Deployment 可能长期存在，直接放入同一等待模型会永久占用名义额度。Kueue 支持管理某些长驻工作负载，但平台必须先定义它们如何获得、续期、缩容与释放 Reservation。

常见做法是为在线服务保留独立 ClusterQueue 或 Flavor，批作业只能借用可回收部分；也可以给服务声明最低副本保底和弹性副本借用。不能让一次开发训练抢占生产最小副本，也不能让过度保守的服务配额使夜间 GPU 永久空闲。

## 2. Kueue 对象模型：从用户命名空间到集群资源池

Kueue 最小主线由 Job、Workload、LocalQueue、ClusterQueue、ResourceFlavor 和 Cohort 组成。Job 表达业务执行，Workload 是准入单位，LocalQueue 提供命名空间入口，ClusterQueue 定义集群级政策，ResourceFlavor 区分资源品类，Cohort 允许额度共享。

### 2.1 Job 是用户操作对象

用户通常提交 Kubernetes Job、JobSet、Kubeflow TrainJob、RayJob 或其他已集成类型，而不是手写 Workload。对象带队列标签或字段，并保持 Suspend 直到准入。Kueue 集成控制器从 Job Pod 模板提取 PodSets、资源请求、优先级和元数据。

平台应把“选择队列”做成提交 API 的一部分，验证当前 Namespace 存在对应 LocalQueue。省略队列的 Job 是否由 Kueue 管理取决于配置和集成策略，不可依赖团队记忆。

### 2.2 Workload 是整体准入单位

一个 Workload 表示一个作为整体完成任务的应用，可包含一个或多个 PodSet。每个 PodSet 有 Count 与 PodTemplate，配额请求等于各 PodSet 单成员 Request 乘数量再求和。Workload Status 记录 ClusterQueue、PodSetAssignments、Flavor、QuotaReserved、AdmissionChecks、Admitted、Evicted 与完成状态。

Workload 不等于运行 Pod 清单。它是准入合同和状态载体。Job 重新排队时 Workload 可能保留并更新 Condition；Job 完成后 Workload 记录 Finished。排障从 Workload 关联回父 Job，再向下查看 Pod。

### 2.3 LocalQueue 是 Namespace 内的提交入口

LocalQueue 属于 Namespace，并引用一个 ClusterQueue。团队可以在不同 Namespace 里都创建名为 `training` 的 LocalQueue，它们分别指向授权的集群队列。用户只需要知道本 Namespace 可用的产品入口，不需要直接操作集群级政策。

LocalQueue Status 可汇总 Pending、Reserving、Admitted 与 Flavor 使用。Admission Fair Sharing 还可按 LocalQueue 记录历史使用与权重。它既是用户体验边界，也是平台做租户归因的重要维度。

### 2.4 ClusterQueue 是集群级准入政策

ClusterQueue 不属于 Namespace。它定义允许使用它的 Namespace 选择器、队列策略、ResourceGroups、各 Flavor 名义额度、借用与借出限制、Cohort、抢占、公平共享、AdmissionChecks 和停止策略。多个 LocalQueue 可以指向同一 ClusterQueue。

ClusterQueue 不是物理节点队列，而是配额与政策队列。一个 ClusterQueue 可包含 A100、L4 和 CPU 等 Flavor，也可能跨多个节点池。它的 Status 应与实际 Workload Reservation 对账。

### 2.5 NamespaceSelector 是租户安全边界之一

LocalQueue 引用 ClusterQueue 并不自动获得权限。ClusterQueue 的 `namespaceSelector` 决定哪些 Namespace 的 Workload 可进入。平台给租户 Namespace 打受控标签，由 Admission Policy 阻止普通用户修改租户身份标签。

若选择器写成空对象，通常匹配所有 Namespace，适合真正共享的公共队列；多租户生产环境不能无意中用全匹配。拒绝原因应明确为 Namespace 不被该 ClusterQueue 接纳，而不是笼统资源不足。

### 2.6 Cohort 把多个 ClusterQueue 放入共享关系

同一 Cohort 或 CohortTree 里的 ClusterQueue 可以借用彼此未使用的名义额度，并依据限制、优先级与公平策略回收。Cohort 本身还可定义额外共享 Quota；层级 Cohort 把部门、事业部与公司级共享池表达成树。

共享提高利用率，也扩大策略影响面。一个 ClusterQueue 错误设置高借用上限可能占用整个树的闲置资源；回收策略错误则会终止其他组织作业。Cohort 设计需要资源所有者共同确认。

### 2.7 对象所有权要防止双重控制

父 Job 由其 Operator 管理，Kueue 负责 Suspend 与 Workload 准入，kube-scheduler 负责 Pod 绑定。每个字段有单一权威。平台不能另写一个控制器同时修改 Job Suspend，或让两个 ClusterQueue 控制同一 Workload。

集成升级时做字段所有权合同测试：谁创建 Workload、谁更新 Admission、谁解挂 Job、谁在 Evicted 后重新挂起、谁写 Finished。双控制会造成状态震荡和配额泄漏。

## 3. ResourceFlavor：同名 GPU 资源背后的真实品类

Kubernetes 扩展资源常把不同 GPU 都暴露为 `nvidia.com/gpu`。A100、L4、H100 在资源名称上可能相同，价格、显存、性能、网络和可用性却完全不同。ResourceFlavor 通过节点标签、污点容忍和可选拓扑把配额绑定到资源品类。

### 3.1 Flavor 不是新的设备资源名称

`a100-on-demand` 可以是 ResourceFlavor 名称，实际扣减的资源仍是 `nvidia.com/gpu`。ClusterQueue 在该 Flavor 下为 `nvidia.com/gpu` 声明 Quota。Workload 被分配 Flavor 后，Kueue 把相应节点约束合入 PodSet，使 Pod 只落到匹配节点。

如果平台已经用不同扩展资源名区分 GPU 型号，也仍可用 Flavor 表达容量类型或拓扑。但资源命名、Flavor 与 DRA 设备属性不要重复制造三套矛盾分类。

### 3.2 NodeLabels 把 Flavor 落实到节点

ResourceFlavor 的 `nodeLabels` 应使用稳定、受控的标签，例如 GPU 型号、容量类型或节点池。Kueue 在准入时检查 Workload 已有 NodeSelector 与 Required NodeAffinity 是否与 Flavor 相容；冲突 Flavor 不能分配。

自动扩容创建的新节点必须带同样标签。若 ClusterQueue 有 Quota 但节点模板缺标签，Kueue 可准入而 Pod 永远匹配不到供给节点。标签 Schema 与节点池模板属于同一发布资产。

### 3.3 Tolerations 允许 Flavor 自动进入专用节点池

GPU 节点常有 `NoSchedule` 污点，防止普通 Pod 占用。ResourceFlavor 可以带 Tolerations，在分配后合入 Pod，使选择该 Flavor 的 Workload 具备进入对应节点池的许可。

Toleration 只表示允许，不表示必须去该节点。仍需 NodeLabels 或 Affinity 保证目标。将宽泛 Toleration 注入所有 Flavor 会扩大租户可达范围，安全审查应检查键、值、Effect 和来源。

### 3.4 同一资源在 ResourceGroup 中按 Flavor 有序搜索

ClusterQueue 的 ResourceGroup 声明一组 `coveredResources`，下面列出多个 Flavor 及各资源 Quota。Kueue 按 Flavor 顺序和 FlavorFungibility 策略评估是否直接 Fit、是否需要 Borrow 或 Preempt，以及是否继续尝试下一 Flavor。

顺序不是装饰。若先放昂贵 A100 再放便宜 L4，未指定硬型号的作业可能优先消耗 A100；反过来，关键训练可能被分配到不满足性能 SLO 的卡。平台产品要么要求用户选 Profile，要么给出经过验证的默认顺序。

### 3.5 FlavorFungibility 决定借用、抢占与换 Flavor 的取舍

当前文档允许配置当前 Flavor 可借时是否继续寻找下一个 Flavor，当前 Flavor 需抢占时是否继续寻找，以及在多个可行候选间偏好借用还是抢占。其目的不是简单“都可替换”，而是决定成本与中断策略。

例如 A100 On-Demand 需借一张，L4 Spot 可在本队列名义额度内直接 Fit。若作业接受两种性能，选择 L4 可避免借用；若作业有 A100 硬 SLO，就不应把 L4 列为可接受 Flavor。业务约束先于策略偏好。

### 3.6 异构 GPU 不能只靠 Quota 区分

如果 A100 与 L4 都以 `nvidia.com/gpu` 上报，节点标签必须可靠且不可被普通租户伪造。设备插件健康、MIG Profile、显存和驱动代次也可能影响可用性。ResourceFlavor 选择成功不等于设备满足全部运行合同。

平台在节点准入阶段验证标签与真实设备一致，漂移节点从 Flavor 节点池隔离。否则错误标签会让高价 Quota 被普通卡兑现，或让 Pod 启动后才发现能力缺失。

### 3.7 Flavor 配额与物理池需要持续对账

ClusterQueue 可声明十张 A100 名义额度，但集群只有八张，或者自动供给上限只有六张。这不一定非法：组织 Quota 可以依赖弹性供给；但门户必须显示物理与可供给缺口，并有 AdmissionCheck 阻止不可兑现的承诺长期占用资源。

对账维度包括声明 Quota、已 Reservation、已 Admitted、实际 Pod Request、匹配节点 Allocatable、可创建节点上限和供应商容量。只比较名义额度与节点总卡数会忽略借用和多 Flavor。

## 4. 名义额度、借用上限与借出保护

Quota 算术必须按 Resource 与 Flavor 分别计算。CPU 有余不能抵扣 A100 不足，L4 空闲不能自动满足 A100 硬请求。下面用单一 A100 Flavor 先解释，再扩展到多资源。

### 4.1 NominalQuota 是 ClusterQueue 自己的基准份额

设团队甲名义额度为四张 A100，当前使用两张。一个两卡 Workload 可以在名义额度内准入，不需要向 Cohort 借用。一个三卡 Workload 会使使用达到五张，其中一张属于 Borrowed 部分。

名义额度不是当前空闲物理卡，也不意味着四张永久闲置给甲。甲不用时，Cohort 成员可在规则允许范围内借用；甲需求回来时可以回收属于自己的范围。

### 4.2 借用量按超出名义额度计算

对某 Queue、Flavor 和 Resource，令当前使用为 $U$，名义额度为 $N$，新请求为 $R$，则准入后的借用量可写为：

$$B=\max(0,U+R-N)$$

读法是准入后总使用超过名义额度的部分。判断借用上限时比较 $B$ 与 `borrowingLimit`，而不是只比较新请求 $R$。

### 4.3 BorrowingLimit 控制借方最大突发

团队乙名义四张、借用上限两张，最多可在 Cohort 条件允许时使用六张。当前已用五张，再提交两张会使借用量达到三，超过上限，即使别的团队空闲很多也不能准入。

借用上限用于控制单租户突发、潜在回收规模和成本。设置过高会让一个团队填满共享池，设置为零则失去共享利用率。不同 Flavor 可以有不同上限。

### 4.4 LendingLimit 保护贷方可被借走的范围

团队甲名义四张、当前用两张，理论空闲两张。若 `lendingLimit` 为一，Cohort 最多只能借走其中一张，另一个名义空位被保护，以便甲更快启动新 Workload。未设置时可能允许更多额度借出，具体以目标版本 Schema 为准。

## 写在最后

Kueue 管的是「谁有权启动」，节点层面的动作组合与在线离线混部则由批调度器承担。下一篇：[Volcano 调度策略与在线离线混部](/source/AI-Infra/4-AI平台工程/13-Volcano调度策略与在线离线混部)。