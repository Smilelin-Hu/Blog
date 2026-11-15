# Gang Scheduling 与分布式作业原子准入

两个分布式训练作业同时提交，每个都有四个 Worker，每个 Worker 申请一张 GPU。集群只有六张空闲卡，普通 Pod 级调度按到达顺序交替绑定：作业甲启动三个 Worker，作业乙也启动三个，最后两个 Worker 都无卡可用。六张 GPU 全部被已经启动的进程占住，但两个训练作业都要求四个 Rank 完成 Rendezvous 才能进入第一步计算，于是有效训练吞吐为零。

![Gang Scheduling 与部分占用死锁](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l11_01.png)

如果这些进程一直等待，集群不会自然恢复：未启动的两个 Worker 需要现有六张卡中的至少两张，而已经启动的六个 Worker 又不会退出。超时后，两个控制器可能同时重建 Pod，产生新一轮交错绑定；如果失败退避、服务发现和 Checkpoint 清理没有协调，系统会在空转、超时、删除和重试之间循环。

Gang Scheduling 要解决的不是“让 Pod 尽量同时出现”，而是把一组相互依赖的 Pod 当作一个调度或准入单元：只有当至少 `minMember` 成员能一起获得所需位置与资源时才提交，否则不让部分成员长期占用。对于固定四 Rank 训练，`minMember` 通常等于四；对于真正支持弹性成员的框架，可以定义最小三、最大五，但准入时仍要冻结一个可执行 World Size，并让运行时、Rendezvous 和 Checkpoint 共同支持变化。

先给出本文最重要的边界。第一，配额原子准入、Pod 创建时机、节点绑定原子性和“所有 Pod 已经 Ready”是四个不同强度的保证。Kueue 可以为整个 Workload 预留配额并在准入前保持 Job Suspend，`waitForPodsReady` 还能在部分 Pod 未能及时 Ready 时撤销准入、挂起并重新排队；这是一种带超时恢复的 All-or-Nothing 资源分配语义，不等同于所有 Pod 在同一个调度事务中同时绑定。Scheduler Framework Coscheduling 或原生 PodGroup Gang 更接近绑定侧协同，Volcano 在调度会话中按 Job／PodGroup 提交 Gang。

第二，`minMember` 不是随意降低等待的旋钮。若四 Rank 训练的通信世界固定为四，把最小数改成三只会让三个进程更早进入不可推进状态。只有应用与控制器明确支持三到五个成员、能生成一致 Rendezvous 配置并在成员变化时处理状态，弹性最小值才成立。

第三，首次原子准入并不自动保证运行期一直满足最小成员。一个 Worker 启动失败、节点中断或 Pod 被抢占后，作业可能跌到 `minMember` 以下。平台必须定义恢复等待、整组重启、替换成员、Checkpoint 边界和资源回收；否则系统只在第一分钟“像 Gang”，之后仍会长期空转。

本文从部分启动的代价和形式化问题开始，比较 Kubernetes 原生 Alpha Gang、Scheduler Plugins Coscheduling、Kueue Workload 准入与 PodsReady 超时、Volcano PodGroup 与调度会话。随后讨论 JobSet、TrainJob、RayJob 和自定义 Operator 如何提供成员集合，刚性与弹性世界、失败恢复、组级抢占、优先级与可解释性。实验会精确复现六卡空转，并证明三种实现位置怎样避免或回收部分占用。

## 1. 分布式作业为什么不能被当成独立 Pod 集合

单个无状态 Web 副本通常可以独立服务，先启动一个就产生部分价值。同步数据并行训练、MPI、某些参数服务器拓扑和紧耦合 Ray 任务不同：成员必须发现彼此、建立通信组并按协议共同前进。调度器若只看到互不相关的 Pod，就无法判断部分启动是否有用。

![成员集合与最小可行数](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l11_02.png)

### 1.1 Worker 等待不是普通排队

未绑定的 Pod 在队列中等待不占 GPU；已经绑定但等待其他 Rank 的 Worker 会持有 GPU、CPU、内存、卷、网络端口和节点缓存。它看起来 Running，GPU 进程也存在，却没有完成有效训练 Step。

这种等待比队列等待更昂贵：它既消耗资源，又阻止缺失成员获得资源。平台指标应区分 Queued GPU、Reserved GPU、Bound-but-not-productive GPU 和 Productive GPU，不能只看 Running Pod 数。

### 1.2 Rendezvous 是成员共同确认世界的协议

分布式运行时需要确定成员身份、Rank、地址、World Size 和代次。Rendezvous 可以由固定地址、服务、共享存储或专门后端实现。成员未齐时，已启动进程通常阻塞或重试连接。

Gang 调度只负责让足够成员获得资源或进入运行，不替代 Rendezvous。即使四个 Pod 都绑定，DNS、网络、Secret 或进程启动失败仍可能让组无法形成。Kueue 的 PodsReady 检测或作业控制器恢复负责后续层。

### 1.3 同步训练的最慢成员决定一步完成

同步数据并行中，每个 Rank 计算梯度并参与集合通信。一个成员没有启动或在某步失联，其他成员通常无法完成该集合操作。有效吞吐不是各 GPU 利用率之和，而是整个通信世界完成的 Step。

因此三个已绑定 Rank 对固定四 Rank 作业的有效 GPU 数可以近似视为零，尽管监控可能看到显存占用和周期性重试。容量效率必须按作业进度归因。

### 1.4 部分启动会制造资源死锁

作业甲和乙各需四张卡，集群六张。若甲占三、乙占三，两者都缺一，且没有成员释放，就形成资源等待环。甲等乙释放一张，乙也等甲释放一张，普通调度器没有作业级信息打破环。

这与代码锁死锁相似：多个参与者分别持有部分资源，又等待对方持有的资源。Gang 准入在提交占用前检查最小集合，避免形成环。

### 1.5 重试风暴会让偶发不足变成持续故障

Rendezvous 超时后，控制器删除并重建成员。若两个作业退避相同，它们再次同时出现，调度仍可能交错。API、镜像、网络和日志都承受额外负载，真正空闲窗口很短。

引入随机退避可以降低同步重试，却不提供正确原子性。需要组级拒绝、资源回滚和排队顺序，让一次只有可满足的 Gang 进入。

### 1.6 部分启动还可能写出不完整外部状态

某些 Worker 在等待期间创建临时 Checkpoint 目录、注册服务、占用数据分片或写运行状态。整组失败后若清理不完整，下一代成员读取旧地址或半成品，问题从调度扩展到数据一致性。

作业代次使用 UID 与 Attempt 标识，外部写入按代次隔离；只有整组 Ready 或任务协议到达提交点才发布。Gang 不自动清这些外部状态。

### 1.7 不是所有多 Pod 工作负载都需要 Gang

无状态副本、独立批任务、可逐个扩容的消费者通常允许部分运行。强制 Gang 会让它们等待整组，降低利用率和弹性。判断标准是低于某成员数时是否仍能产生正确、可接受的进展。

“一次创建了很多 Pod”不是充分条件。平台工作负载类型显式声明刚性、弹性或独立，控制器据此选择调度语义。

## 2. 用成员集合与最小可行数定义 Gang

Gang 首先是一个工作负载模型。系统必须知道哪些 Pod 属于同一组、最少多少成员、每个成员请求、是否异构、何时视为就绪以及超时后怎样回滚。

### 2.1 成员集合要有稳定身份

设作业组为 $G=\{p_1,p_2,\ldots,p_m\}$，每个 $p_i$ 是一个 Pod 或 Pod 模板实例。成员归属不能只靠容易冲突的普通标签；需要 PodGroup 引用、Owner、Workload PodSet 或调度系统定义的组标识，并带 UID 区分同名重建。

读法是组 $G$ 由 $m$ 个明确成员组成。删除同名旧组再创建新组，UID 变化，新 Pod 不能误加入旧等待集合。

### 2.2 MinMember 是启动仲裁线

定义 $q$ 为最少必须共同获得资源的成员数，要求 $1\le q\le m$。Gang 可行性可以概念化为：存在至少 $q$ 个成员及其节点映射，使每个成员硬约束都满足，且映射后的节点资源总占用不超容量。

固定四 Rank 作业有 $m$ 等于四、$q$ 等于四。弹性作业可能 $m$ 等于五、$q$ 等于三，但应用必须对三、四、五均有正确运行语义。

### 2.3 MinMember 不等于最终成功数

`minMember=4` 表示达到初始或调度 Gang 门槛，不表示四个成员最终都成功完成，也不表示组内剩余成员永远不再调度。完成语义由 Job、JobSet 或训练控制器定义。

某工作负载有一个 Coordinator 加四个 Worker，最小可行集合可能包含 Coordinator 和至少三个 Worker，不能只写整数而不考虑角色。异构 PodSet 需要角色级最小数或完整资源聚合。

### 2.4 MinResources 提供集合资源下界

Volcano PodGroup 等模型可声明最小资源。它回答组达到可运行门槛至少需要多少 CPU、内存、GPU 等。仅有成员数时，如果成员模板尚未全部出现或资源不同，系统可能低估。

MinResources 必须与实际成员请求一致或保守覆盖。写四成员却只声明两张 GPU 会造成准入后仍无资源；写得过大则不必要等待。控制器最好从 Pod 模板计算，减少人工漂移。

### 2.5 原子准入的形式化目标

设 $x_i\in\{0,1\}$ 表示成员是否被提交占用。强 Gang 初始提交要求：

$$\sum_{i=1}^{m}x_i\ge q$$

并且在决定提交前，所有被选成员的放置都已可行；如果无法达到 $q$，则所有本次暂存的 $x_i$ 回到零。读法是提交成员数至少达到门槛，否则一个也不提交。

这个公式只描述数量。节点拓扑、角色和资源仍在每个成员的放置约束中。异构组用简单贪心顺序可能找不到实际存在的组合，因此算法边界必须说明。

### 2.6 配额原子与绑定原子是两层事务

上层队列可以一次为整个 Workload 预留四张 GPU 配额，并在此之前让 Job 保持 Suspend。它保证没有只给两个 Worker 配额；但 Job 解除 Suspend 后，节点层仍可能只绑定三个，第四个因瞬时拓扑或启动问题等待。

绑定侧 Gang 在同一调度周期或 Permit 协调中暂存具体节点放置，达到门槛才提交，更接近节点资源原子。两层可以组合：先工作负载配额准入，再 PodGroup 绑定。

### 2.7 Ready 原子比 Bound 原子更强也更慢

四个 Pod 都 Bound 不表示容器 Ready。镜像、卷、设备、网络和应用探针仍可能失败。Kueue 的 `waitForPodsReady` 观察已准入 Workload，如果超时未全部 Ready，就取消准入、Suspend 并重新排队。

这种语义可以回收启动失败造成的长期空转，但在超时窗口内可能已有部分 Pod 绑定。`blockAdmission` 还能让同一 ClusterQueue 后续准入等待，减少多个 Workload 各占一部分资源形成死锁，代价是吞吐与队头等待。

### 2.8 原子不是同一纳秒启动

Gang 保证提交条件，不保证容器进程在完全相同时间启动。节点 Kubelet、镜像缓存和运行时准备不同，启动仍有偏差。应用 Rendezvous 必须容忍合理的到达窗口。

验收使用“首个成员 Ready 到达到门槛成员 Ready 的时间差”和超时，而不是要求时间戳完全相等。

## 3. 四种实现位置的核心差异

同样叫 Gang，机制可能位于原生调度器、Out-of-tree 插件、工作负载准入控制器或替代批调度器。比较时先问“在哪个状态点阻止部分占用”。

### 3.1 Kubernetes 原生 Gang 是快速演进的 Alpha 能力

当前 Kubernetes 文档中的 Gang Scheduling 依赖 GenericWorkload 与 PodGroup API，处于 Alpha 并默认关闭。Pod 引用 PodGroup，组使用 Gang 策略与 `minCount`。成员对象未达到最小数时可在 PreEnqueue 等待；调度器尝试为至少最小数找到放置，失败时不绑定该组。

这是重要方向，但生产使用必须绑定确切 Kubernetes 版本、Feature Gate、API 版本和发行版支持。Alpha 字段与算法边界可能变化，不把示例当所有集群现状。

### 3.2 PodGroup 调度周期把组作为一次快照处理

较新的 PodGroup 调度周期会在一致快照中取出组成员，逐个寻找可行放置并暂存，达到策略门槛后进入绑定；失败则整组回队列。它避免用许多独立 Pod 长期占资源等待 Permit。

默认算法对同质、无成员间依赖的组更容易找到放置；异构组与组内亲和可能受处理顺序影响，存在可行解也不保证算法发现。平台对复杂角色组做目标版本实验。

### 3.3 Scheduler Plugins Coscheduling 使用多个扩展点协同

Out-of-tree Coscheduling 通过 PodGroup CRD 与 QueueSort、PreFilter、Permit、Unreserve 等扩展点实现。QueueSort 尽量让同组 Pod 连续尝试；PreFilter 可在成员对象不足时快速失败；Permit 把未达到门槛的 Pod 放入等待；达到 minMember 后批准等待成员；超时则 Reject 并 Unreserve 整组。

这套机制说明为什么只写 Permit 不够：成员若在队列中交错、对象尚未创建或超时后 Reservation 不回滚，仍会低效。插件版本必须与 Kubernetes 版本匹配，并理解一个 Profile 只能有一致 QueueSort 实现。

### 3.4 Kueue 在创建 Pod 之前控制工作负载配额

Kueue 集成 Job 类工作负载时，Webhook 或控制器让未准入 Job 保持 Suspend，提取 PodSet 与资源请求生成 Workload。只有整个 Workload 获得 ClusterQueue 配额、ResourceFlavor 和所需 AdmissionCheck，Job 才解除 Suspend 并创建 Pod。

这个位置非常适合组织配额、公平、借用和大作业排队，避免未获配额的成员先占节点。它通常不替代 kube-scheduler 的具体节点选择。

### 3.5 waitForPodsReady 是超时回收语义

Workload 准入后，若 Pod 没有在配置时间内全部 Scheduled、Running 并满足可选 Readiness，PodsReady 保持 False。超时后 Kueue 撤销准入、Suspend Job 并重新排队，释放配额；恢复期某成员再次 NotReady，还可使用 recoveryTimeout。

因此它解决的是“整组获得配额后仍部分启动”的长期占用，不承诺零时间窗口内绝无部分绑定。需要更强绑定原子性时，结合 PodGroup/Coscheduling/TAS 或批调度器。

### 3.6 Volcano 在调度会话内按 PodGroup 提交

Volcano Scheduler 围绕 Job、Queue 和 PodGroup 运行调度 Session。Gang 插件根据 minMember、minResources、队列分配与任务状态判断能否达到最小运行数；满足时提交组内调度动作，不满足则不提交本次部分分配。

Volcano 还把 Gang 与队列、公平、Binpack、Preempt、Reclaim 等动作组合。插件顺序和 Session 语义影响结果，不能只创建 PodGroup 而仍让 Pod 交给默认 Scheduler。

### 3.7 四种方案可以组合但不能重复争夺所有权

常见组合是 Kueue 先做 Quota Reservation，Job 解除 Suspend 后由支持 Coscheduling 或 Volcano 的 Scheduler 做节点 Gang。必须保证 SchedulerName、PodGroup 注入和控制器集成一致。

两个不同调度器不能同时绑定同一 Pod。两套控制器也不能互相反复 Suspend／Unsuspend。平台画清 Owner：谁生成成员、谁准入配额、谁选择节点、谁观察 Ready、谁在失败时重启或回收。

## 4. Coscheduling 的 Permit 机制怎样避免长期占用

理解 Permit 路径的关键，是把“暂存”“等待”“批准”“拒绝”和“回滚”分开。Pod 在 Filter 和 Score 后已经选出节点，调度器可以在缓存中 Assume 并执行 Reserve，但尚未写最终绑定。Permit 让同组成员在这个边界会合。

### 4.1 QueueSort 让组成员尽量连续被尝试

若甲一、乙一、甲二、乙二交错进入 Permit，两个组都可能分别暂存部分资源。Coscheduling 的 QueueSort 会结合 PodGroup 创建时间、优先级和成员身份，让同组 Pod 尽量背靠背进入调度周期，缩短组凑齐时间。

“尽量”不是无条件保证。更高优先级 Pod、失败重排和其他事件仍会影响顺序。正确性由 Permit 门槛与 Unreserve 保证，QueueSort 主要提高效率。

### 4.2 PreFilter 等待成员对象完整

控制器可能逐个创建 Pod。第一个成员到达时，其他对象还不存在；若立刻进入 Filter 并 Reserve，它会无意义等待。PreFilter 可检查同组已观察成员数是否达到 minMember，不足就快速判定尚未准备。

## 写在最后

Gang 解决的是「整组一起进入」，而组织层面的配额、借用与公平需要专门的队列系统。下一篇：[Kueue 队列、配额、公平共享与抢占](/source/AI-Infra/4-AI平台工程/12-Kueue队列-配额-公平共享与抢占)。