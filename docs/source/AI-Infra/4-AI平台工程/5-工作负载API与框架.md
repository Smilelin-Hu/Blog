# 工作负载 API 与框架：把调度能力封装成产品

用户不该直接拼 Pod 和 Service。平台的价值之一是提供**表达意图的对象**：一次分布式训练、一次超参搜索、一个在线服务。但这些对象各自带着失败语义、身份语义与清理语义，混用会制造最难查的那类问题。

## 1. Job 的语义边界

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l17_01.png" width="78%" alt="分布式工作负载 API" />
  <p>图 1：容器重启、Job 重建、JobSet 重建、LWS 组重建是四种不同的「restart」</p>
</div>

### 1.1 四种「restart」不要混

| 层级 | 动作 | 保留什么 | 改变什么 |
|---|---|---|---|
| 容器 | `restartCount` 增加 | Pod UID | 进程状态、本地缓存 |
| Job | 新建替代 Pod | Job 对象 | Pod 名称/UID |
| JobSet | `RestartJob` / `RestartJobSet` | JobSet | Child Job UID |
| LWS | 组级策略 | 组标识 | 整组成员 Pod |

诊断时必须记录「是容器重启、是 Job 换了 Pod、是 JobSet 重建了 Child Job，还是 LWS 重建了整组」。只看界面上的「重启次数」会混淆责任。

### 1.2 三种终止条件

- `backoffLimit`：Pod 失败重试上限（默认通常 6，指数退避）；
- `activeDeadlineSeconds`：跨重试的总时限，**优先于** backoffLimit；
- `PodFailurePolicy`：按退出码或 Pod Condition 把失败分类为 `FailJob` / `Ignore` / `Count` / `FailIndex`，规则按顺序求值，首个匹配生效（要求 `restartPolicy: Never`）。

分类质量决定上层动作质量。若训练脚本把「数据校验失败、CUDA OOM、网络超时、节点驱逐」都返回同一个退出码，JobSet 就无法可靠选择 `FailJobSet` 还是 `RestartJobSet`。

**平台需要一份合同**：退出码 / 结构化终止消息 / Pod Condition / 业务 Reason 的映射，并用反例测试验证。不要只靠日志文本自动决策——日志会被截断、本地化、改格式，或在崩溃前没刷出。

### 1.3 Indexed Job：给身份，不给协调

Indexed Job 为每个完成单元编号（0..completions-1），Pod 可读 `JOB_COMPLETION_INDEX`，`backoffLimitPerIndex` 可分别限制每个索引的失败次数——适合「索引 → 稳定数据分片」。

但两个常见误解：

1. **稳定索引 ≠ 成员发现与 Gang 启动**：8 个索引可能依次被调度，前 4 个占着 GPU，后 4 个长期 Pending；应用要求 8 Rank 一起初始化时，Indexed Job 本身不保证原子准入，需要 Kueue、Gang 调度或应用级容错；
2. **索引稳定 ≠ 实例稳定**：Pod 重建后仍拥有相同索引，但不是同一个进程。其他 Rank 若只按索引识别、不校验 Attempt 或 Rendezvous 代次，可能接受一个「旧世界之外」的新成员。

### 1.4 successPolicy：控制面成功 ≠ 业务成功

Job 的 `successPolicy`（以及 JobSet 的 SuccessPolicy，可选 All/Any 与目标角色）只证明**控制器观察到目标完成**。真实业务可能还要求：Checkpoint 写完、模型 Manifest 原子发布、评测摘要存在、输出 Digest 可读。

经典事故：Trainer 先退出 0，Sidecar 稍后才把文件传到对象存储，而 SuccessPolicy 立即终止其余角色——平台得到「控制面成功、制品不完整」。

正确做法是把业务提交纳入成功协议：训练进程先写 Attempt 目录 → 校验 → 条件写发布 Manifest → 才退出 0；或由独立 Committer 角色验证制品并作为 SuccessPolicy 目标。

### 1.5 终态不等于 Pod 都消失了

Job 的 `FailureTarget` / `SuccessCriteriaMet` 与最终 `Failed` / `Complete` 是两个阶段。平台不能假设「成功条件已满足」的瞬间所有旧 Pod 已停止写数据。

清理窗口会影响下一次 Attempt：新 JobSet 马上用同一输出目录，旧 Pod 还在 Termination Grace Period 内，就会**双写**。所以训练容器要响应 SIGTERM、停止领取新工作、完成或放弃临界写入；存储层还要用 Attempt 与 Fence Token 防止越代提交。

`ttlSecondsAfterFinished` 只清理对象，**不是数据保留策略**——日志、制品、审计需要独立生命周期。

## 2. JobSet：把多个 Job 放进同一棵树

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l18_01.png" width="78%" alt="JobSet" />
  <p>图 2：JobSet → ReplicatedJob 声明 → Child Job → Pod 四层对象树</p>
</div>

### 2.1 总量必须算，不能猜

`spec.replicatedJobs` 的每个条目有 name、JobTemplate 与 replicas。**replicas 是「创建几个 Job」，不是「几个 Pod」。**

举例：trainer `replicas=2`，每个 Child Job 的 parallelism=4、completions=4 → Trainer 峰值 8 Pod；再加 1 个 Leader 与 2 个 Evaluator → 峰值 11 Pod。若每个 Trainer 与 Evaluator 各要 1 张 GPU，**准入需求是 10 张 GPU**，而不是看到 `replicas: 2` 记成 2 张。

平台应从实际 PodTemplate 聚合 CPU/内存/GPU/临时存储/DRA Claim/拓扑/优先级，并允许与用户声明对照；不一致时以控制器可执行的模板为准。

### 2.2 OwnerReference 与标签不是一回事

- **OwnerReference 决定级联删除**；
- **标签决定查询与聚合**。

重启时尤其重要：JobSet 重建 Child Job 后，名称可能相同、**UID 已变**。观察系统若只按 name 聚合，会把旧 Attempt 的终止事件与新 Attempt 的运行指标混在一起。主键至少包含 Namespace + Kind + UID + 控制器代次。

另外：跨 Namespace 的 OwnerReference 不被允许；共享协调器放在另一个 Namespace 时，不能用 OwnerReference 期待自动清理。删除策略也要显式（前台级联 vs 后台删除），恢复流程需要**可验证的清理屏障**，而不是假定后台回收已完成。

### 2.3 名称稳定 ≠ 实例稳定

Headless Service 提供基于角色与索引的稳定主机名，但 Pod 重建后 IP、UID、进程状态、本地缓存都变了。

- 日志里同时输出 `logical_member_id`（哪个 Rank）与 `instance_uid`（哪次实例）；
- 应用握手携带 Attempt/Epoch，拒绝旧代次成员；
- 单写保护用租约或存储 Fence Token，而不是「名字唯一」的假设。

### 2.4 Service 解决发现，不证明就绪

`publishNotReadyAddresses` 提前暴露未 Ready 的地址，适合「所有成员互相发现后才能完成初始化」的框架，但也会让 DNS 可解析早于业务可用。

反过来，如果关闭未 Ready 发布、而 Leader 的 Readiness 又依赖 Worker 连接，就会形成**环**：Worker 等 DNS → DNS 等 Leader Ready → Leader 等 Worker。

正确做法：DNS 允许发现（可解析），应用连接返回明确的 `NotReady`/`Epoch`，由业务探针控制真正准入。

## 3. LeaderWorkerSet：以组为单位

LWS 面向「一个 Leader + 若干 Worker 组成一个副本」的推理/训练形态（如多卡大模型服务），关键语义是**组级重启**：组内成员出问题可以按策略重建整组，避免「Leader 换了、Worker 还在连旧地址」。

代价同样明确：整组重建会损失组内所有成员的进度与本地缓存，所以要有组级就绪与组级回滚。

## 4. Kubeflow Trainer：训练运行时产品化

Kubeflow 生态里，Trainer V2 把多种训练作业（PyTorchJob、TFJob、MPIJob 等）收敛成统一 API，并提供运行时（Runtime）抽象：镜像、入口命令、依赖安装、分布式环境变量注入都由 Runtime 定义。

平台侧要点：

- **模板即产品**：把「框架 + 版本 + 启动命令 + 环境变量」固化成 Runtime，用户只填模型与数据；
- **模板要版本化**，否则同一声明在不同日期产生不同环境；
- **Trainer 管作业，调度管准入**：Kueue 管 Workload，Trainer 管 Job 生命周期，边界要写清（谁 suspend、谁解挂）。

## 5. KubeRay：三种 CRD 与三层扩缩

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l20_01.png" width="78%" alt="KubeRay" />
  <p>图 3：RayCluster / RayJob / RayService 对应长期集群、一次性作业与在线服务</p>
</div>

### 5.1 三种形态

| CRD | 用途 | 关键取舍 |
|---|---|---|
| RayCluster | 长期共享集群 | 资源常驻，利用率取决于多任务共享 |
| RayJob | 一次运行一个合同 | 隔离好，但每次承担集群启动时延 |
| RayService | 在线服务 | 稳定 Service + Serve 应用，支持滚动升级 |

RayJob 的高层状态串联「集群准备 → 提交 → 运行 → 成功/失败 → 清理」；结束后可以保留 Head 诊断、先删 Worker 省钱、延迟删整集群，或直接删除。平台要用镜像预拉取、依赖内置、节点暖池与合理 TTL 来平衡成本与诊断窗口。

RayService 的关键判断是**变更属于应用面还是集群面**：路由/部署参数/副本配置可在活动集群内更新；Ray 镜像、Worker Group、运行环境变化会触发新集群路径——两者的容量、回滚与风险完全不同。

`RayCronJob` 目前是 Alpha 且默认关闭：可以在受控试验集群评估，**不应把 Alpha Schema 当长期兼容合同**；生产周期任务可用稳定的工作流调度器或 K8s CronJob 创建 RayJob。

### 5.2 Head 不是普通主节点

Head 运行 GCS、Dashboard、作业服务等控制组件，且自身也参与调度。Head 的 CPU/内存不足会表现为：任务调度延迟、Dashboard 超时、提交失败、整集群不稳定——**不是「少一个 Worker」那么简单**。

因此 Head 要独立容量模型与放置策略：限制普通任务占用 Head 资源、给控制面保留 CPU/内存、配置合适的优先级与反亲和。

### 5.3 Worker Group 表达异构，但两层资源必须对齐

不同 Worker Group 可以有独立镜像、资源、min/max 副本、节点选择与容忍度，用来表达 CPU 预处理 / 通用 GPU / 特定型号 / 高内存节点。

两类错配都会出事：

- Ray 认为节点有某资源，但 K8s 没保证对应硬件 → 任务调度到错误 Pod；
- Pod 拿到了 GPU，但 Ray 资源声明缺失 → 应用长期等待不存在的逻辑资源。

记住：**Ray 的逻辑资源是调度合同，不是隔离边界**（`num_gpus=1` 不等于 cgroup 强隔离）。容量报告要分别展示：物理已分配、Ray 逻辑总量、Ray 逻辑已用、应用排队需求。

<div align="center">
  <img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l20_02.png" width="78%" alt="多层扩缩" />
  <p>图 4：Serve 副本 → Ray Worker Pod → 物理节点，三层控制循环各自有延迟</p>
</div>

### 5.4 三层扩缩与阻尼

```text
第 1 层：Serve 部署副本 / Ray Actor（应用需要多少执行单元）
第 2 层：Ray Worker Pod（Autoscaler 看逻辑需求扩 Worker Group）
第 3 层：Kubernetes 节点（Cluster Autoscaler 补物理机）
```

每层都有自己的采样、冷却与失败语义。端到端突发响应时间是三段的**串联**：Serve 扩副本 → Worker Pod 起并加入集群 → 节点创建并驱动就绪。

把三层合成一个「自动扩缩开关」会隐藏关键延迟，并容易振荡：Serve 迅速扩到 10 → Ray 请求 10 个 Worker → 节点 10 分钟才到 → 流量已回落 → 三层同时缩容。

阻尼来自：最小暖容量、上下行冷却、最大变化速率、排队上限、超时与分层 SLO。参数要从**实测启动分位数**与业务到达分布推导，而不是照抄示例。

另外要同时配置两套边界：Ray 的 `maxReplicas` 与云侧 GPU 节点池上限。若 Ray 允许 20 个 Worker 而节点池最多 4 张卡，控制循环会长期追逐不可能的目标——应把物理上限反馈到准入与 Autoscaler 配置。

## 6. Pipelines 与 Katib：流程与搜索

- **Kubeflow Pipelines V2**：管任务之间的 DAG、参数传递、制品寻址、缓存与血缘。它管**流程状态**，不替代底层调度（资源准入仍由队列/调度器负责）；
- **Katib**：超参/神经架构搜索，每个 trial 是一个工作负载。要控制的是**并发 trial 数**与**总预算**，否则搜索会把整个池吃满。

共同原则：**流程系统不能替代资源准入，资源准入也不能替代流程状态。**

## 7. 选型速查

| 需求 | 选择 |
|---|---|
| 单机或简单多进程训练 | Job / Indexed Job |
| 多角色协同（trainer + evaluator + sidecar） | JobSet |
| Leader + Worker 组的推理/训练副本 | LeaderWorkerSet |
| 统一训练运行时与模板 | Kubeflow Trainer |
| 长期 Ray 集群 / 一次性作业 / 在线服务 | RayCluster / RayJob / RayService |
| 多步流水线与血缘 | Pipelines V2 |
| 超参搜索 | Katib（控并发与预算） |

## 写在最后

工作负载 API 的选择，本质是选择**失败语义、身份语义与清理语义**。同一个「重启」在两个对象里可能意味着完全不同的事——这正是平台需要把这些语义写进产品契约的原因。

下一篇进入交付链：模型注册与版本、KServe 的声明式服务、GitOps 与环境晋级、供应链与发布证明。
