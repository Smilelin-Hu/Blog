# Slurm GPU 集群与 Kubernetes 的边界和协同

企业建设 AI 基础设施时，经常同时拥有传统 HPC 集群与云原生 Kubernetes 集群。问题不应简化成“谁取代谁”。Slurm 擅长为 Linux 计算集群分配一段时间内的节点资源、启动并监控并行 Job，以及在排队需求之间仲裁；Kubernetes 擅长以声明式 API 管理容器化应用及其持续生命周期，并通过控制器、服务发现、策略与扩展生态承载在线服务和平台能力。两者可以处理部分相同的批作业，却有不同控制模型与运维边界。

![Slurm 与 Kubernetes 双栈边界](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l16_01.png)

本文以 Slurm 26.05 官方文档为版本基线。目标不是把 Slurm 术语机械翻译成 Kubernetes 对象，而是判断同一工作负载应进入哪个后端，并让身份、项目、制品、运行 ID、状态、成本与审计在平台层统一。双栈平台最危险的设计是把一份任务同时提交到两个后端，或者为了“统一”而抹掉 QOS、Association、Namespace 与 Workload 准入的真实语义。

## 1. Slurm 解决的问题

Slurm 官方将系统的三个主要职责概括为资源分配、工作启动与监控、资源竞争仲裁。用户提交 Job，请求节点、CPU、内存、GPU、时间和约束；Job 获得 Allocation 后，可在其中启动一个或多个 Step。这个模型非常适合 MPI、科学计算、仿真和大规模同步训练：资源通常在一个有界时间窗口内整体分配，任务完成后释放。

Slurm 不是一个只执行 Shell 脚本的队列。它具有节点状态、Partition、Reservation、GRES、TRES、Association、QOS、优先级、回填、抢占、拓扑与 Accounting 等完整调度体系。把它称为“简单批处理器”会忽略成熟 HPC 站点积累的公平性、资源限制和高性能网络知识。

同样，Slurm 也不自动提供 Kubernetes 式应用控制面。在线推理通常需要 Service、Ingress 或 Gateway、滚动升级、探针、Secret、配置、自动扩缩与 Operator 协调。可以在 Slurm 上运行长期服务，也可以在 Kubernetes 运行 MPI 与批作业，但技术可行不代表产品模型最自然。平台需要根据工作负载生命周期和组织能力做选择。

## 2. 核心守护进程与信任边界

slurmctld 是集中式管理器，负责资源与 Job 状态，可以配置备用管理器接管。每个计算节点运行 slurmd，接收工作、启动任务并返回状态。可选的 slurmdbd 把一个或多个 Slurm 集群的 Accounting 信息写入数据库，并支撑 Association、QOS 与资源限制。可选的 slurmrestd 通过 REST API 让外部平台访问 Slurm。

控制面高可用不等于所有组件共用一个身份。slurmctld、slurmd、slurmdbd、slurmrestd 与门户代理应具有清晰网络和凭证边界。官方示例常见 auth/munge，slurmrestd 也支持 JWT 等认证路径；生产选择必须按目标版本和站点安全设计验证。门户不能把管理员凭证转发给普通用户，也不能仅依赖前端隐藏字段实施 Account 与 QOS 授权。

slurmrestd 是无状态服务，请求会同步到 slurmctld 或 slurmdbd。官方文档建议在客户端与 slurmrestd 之间使用缓存代理，避免重复查询增加控制器负载与锁竞争。双栈门户若每秒全量轮询数万 Job，会把用户体验问题转化为 Slurm 控制面事故。应使用条件查询、缓存、增量事件或受控刷新频率。

## 3. Job、Allocation 与 Step

Job 是用户提交的资源与工作请求。获得资源后形成 Allocation，Step 是在这份 Allocation 中启动的一组任务。一个训练 Job 可以先启动环境探针 Step，再启动主要 MPI Step，最后启动评估或归档 Step；各 Step 共享 Job 已获得的资源上限。这个复用固定 Allocation 的能力与 Kubernetes 每个 Pod 独立调度的默认心智不同。

Partition 把节点组成逻辑集合，并可定义时间、规模、访问与共享政策。节点可以出现在重叠 Partition，因此 Partition 更接近带政策的资源队列，不应简单映射成 Kubernetes Namespace。Namespace 主要是 API 对象与策略边界；Kueue 的 ClusterQueue、ResourceFlavor 和 LocalQueue 更接近部分排队与配额语义，但仍不是一一对应。

Reservation 为指定时间、用户或用途保留资源，适合预约实验、维护和教学窗口。Kubernetes 世界可通过保留节点、队列额度、ProvisioningRequest 或外部预约系统组合实现，却没有一个通用对象天然等价。统一门户应保留“预约容量”业务概念，再分别编译到后端能力。

## 4. GPU GRES 的正确模型

GRES 是 Generic RESources。Slurm 默认不启用任何 GRES，管理员必须在 slurm.conf 声明 GresTypes 和节点 Gres，并通常在计算节点的 gres.conf 描述设备、数量、文件和亲和。若 Slurm 发现节点设备少于配置，官方文档说明节点会进入 DRAIN。这是重要安全行为：配置声称八卡而实际只有七卡时，系统不应继续把节点作为健康八卡节点使用。

用户通过 --gres、--gpus、--gpus-per-node、--gpus-per-socket 或 --gpus-per-task 请求 GPU。官方文档指出 GPU 专用选项依赖 select/cons_tres；typed 与 untyped GRES 在同一 Job 及其 Step 中要保持一致。平台适配器必须把门户里的 GPU 型号和数量稳定编译到这些字段，不能在 Job 申请非类型 GPU 后让 Step 改成特定型号。

gres.conf 可使用 AutoDetect。对于 NVIDIA，AutoDetect=nvml 能够发现 GPU 并支持更完整信息；较新的 AutoDetect=nvidia 不要求 NVML，但官方文档明确它不检测 MIG 或 NVLink。平台不能因为节点枚举到 GPU 就声称 MIG 与互联拓扑已验证。`slurmd -C` 与 `slurmd -G` 可以辅助生成和检查配置，但真实节点仍需运行计算、绑定和通信探针。

Slurm 为 Job Step 设置 CUDA_VISIBLE_DEVICES，并可结合 cgroup 约束设备文件。环境变量只是可见性提示，不是强隔离本身；生产需要 task/cgroup 等正确配置。Prolog 与 Epilog 运行在 Job cgroup 之外时，看见的设备编号还可能与 Job 内部不同，诊断脚本不能用一个环境的编号直接推断另一个环境。

## 5. MIG、MPS 与 Sharding 边界

Slurm 支持把预先配置的 MIG 实例当作 GPU GRES 调度，并进行 cgroup 隔离与任务绑定。官方文档同时指出 Slurm 不负责动态创建 MIG 布局，AutoDetect 的完整性检查也不适用于 MIG。节点在加入对应 Partition 之前，应由外部配置管理完成 MIG 几何，并由 Profile 验证实际布局与 slurm.conf 声明一致。

MPS 和 Sharding 用于共享 GPU，但语义不同于硬隔离切片。Sharding 允许多个 Job 共享 GPU，却不为 GPU 上进程提供隔离，官方建议更适合相似工作流。统一门户不能把 Slurm shard、MPS、MIG 与 Kubernetes time-slicing 都展示成相同的“小 GPU”。产品必须说明显存、故障、性能和安全边界。

GPU 利用率与显存 Accounting 也有实现范围。配置 AccountingStorageTRES=gres/gpu 后，可启用相关 GPU TRES；官方文档指出 NVML 不提供 MIG 设备利用率指标，因此 Slurm 不会为 MIG 提供相同 gpumem 与 gpuutil Accounting。报表缺少指标不能被解释成零使用。

## 6. TRES、Association 与 QOS

TRES 是 Trackable RESources，由 Type 与 Name 组成，可用于追踪用量或执行限制。默认跟踪 Billing、CPU、Energy、Memory、Node 等资源，GPU 通常通过 AccountingStorageTRES 显式加入。若只加入具体 gres/gpu:a100 而不加入通用 gres/gpu，非类型 GPU 请求可能不会按预期进入同一 Accounting 口径，因此官方文档建议同时配置通用类型。

Association 把 Cluster、Account、User 和可用 Partition 等关系连接起来。QOS 在 Slurm 数据库中定义，用户通过 --qos 请求，并且必须被允许使用。QOS 影响优先级、抢占和资源限制。它不是一个只用于显示的服务等级标签。门户在提交前可以预检，却必须让 Slurm 继续执行最终授权和限制。

资源限制具有层级与优先顺序，Partition QOS、Job QOS、User Association、Account 层级、Root 与 Partition 共同作用，部分时间和节点限制还有特殊上界语义。适配器不能用“取所有限制最小值”这种简单算法冒充 Slurm。正确做法是提交前提供估算，提交后读取真实 Pending Reason，并把可行动原因翻译给用户。

累计资源时间能够表达团队预算，例如 GPU 数量乘运行分钟。它不同于同时使用上限。一个 Team 可能同时最多用三十二卡，但每月或滚动周期还有累计额度。双栈平台要把 Slurm Accounting 与 Kubernetes 请求时间归一成共同单位，同时保留源系统原始记录用于审计。

## 7. 优先级、公平共享与抢占

Slurm 默认使用 multifactor 优先级插件。官方文档列出的因素包括 Age、Association、Fair-share、Job size、Nice、Partition、QOS、Site 与 TRES 等。最终次序还受可抢占、Reservation 和 Partition PriorityTier 等条件影响，所以最高数值优先级不一定总是第一个被评估的 Job。

Fair-share 把承诺份额与历史消费联系起来，目标不是让每个瞬间完全相等，而是让长期使用回到组织政策。历史衰减、Account 层级、权重与 TRES 计费都会影响结果。门户应展示主要因子与预计等待，不能自行重算后承诺精确启动时间。

Slurm 抢占可以由 Partition 层级或 QOS 关系控制，PreemptMode 决定取消、重新排队、暂停等机制。官方文档里的 GANG 还表示同一 Partition 内 Job 的时间切片，与 Kubernetes 语境中“多个 Pod 原子准入”的 Gang Scheduling 不是同一个含义。平台 UI 必须避免同词误导。

GPU 训练若采用 CANCEL 或 REQUEUE，需要应用 Checkpoint 与恢复。SUSPEND 可能保留已分配 GRES，暂停 Job 不会自动让 GPU 给其他 Job，具体行为要结合配置验证。抢占政策不能只检查调度器动作，还要验证业务状态、一致性和 Accounting。

## 8. 网络拓扑

没有 Topology 插件时，Slurm 把节点视为一维数组并进行 Best Fit。topology/tree 可描述层级网络，调度器寻找能满足请求的最低层 Switch，再在叶子 Switch 下进行 Best Fit，以减少网络竞争。拓扑数据来自站点配置，不是 Slurm 自动发现所有网络事实。

用户可用 --switches 请求最多叶子 Switch 数量以及愿意等待该形状的时间。如果单叶子 Switch 暂时不足，用户可选择等待获得更好通信布局，或者超过窗口后接受更宽分布。这个合同适合大规模 AllReduce，但必须以真实性能验证选择等待是否值得。

Slurm 26.05 官方发布说明加入 ring 与 torus3d 拓扑插件。这里不把新插件存在直接等同于目标集群可用；站点需核对硬件、配置和版本。Kubernetes 也发展拓扑感知调度、DRA 与 Workload API，两者表达不同，双栈门户应统一业务意图“同机架、最大跨域数、最长等待”，再分别编译。

## 9. Federation 与多集群

Slurm Federation 支持多个集群点对点调度。Federated Job 获得在 Federation 内唯一的 Job ID，提交到本地 Origin Cluster 后复制到其他 Sibling Cluster，各集群按本地政策尝试调度，并与 Origin 协调。它不是把所有集群合并成一个共享 slurmctld。

官方文档明确 Federation 不面向高吞吐环境，并针对每天超过五万 Job 给出减少 Sibling 或限制提交集群的建议。统一门户不能把 Federation 当成无限扩展的消息总线。大量短任务需要评估 Job Array、本地调度、数据位置和提交削峰。

Federation 解决 Job 放置协同，不自动搬运镜像、数据、Checkpoint、用户目录和许可。多个集群必须共享或协调身份与 Accounting，目标集群也要满足软件和网络 Profile。全球唯一 Job ID 有助追踪，却不证明数据准备与业务恢复完成。

## 10. Kubernetes 与 Slurm 的能力边界

Slurm 的核心抽象是 Job 在有限时间内获得计算资源并运行 Step；Kubernetes 的核心抽象是控制器持续把声明对象收敛到期望状态。前者对紧耦合批作业、HPC 拓扑和成熟 Accounting 非常自然，后者对在线服务、声明式生命周期、Operator 与云原生交付非常自然。

Kubernetes Job、JobSet、Kueue、Gang Scheduling 与 Topology 能力持续增强，因此不能用旧版本印象断言 Kubernetes 不能运行 HPC。当前 Kubernetes Workload API 与原生 Gang Scheduling 仍有目标版本和 Feature Gate 边界，生产采用需核对稳定性。反过来，也不能因 Slurm 以 Job 为中心就断言它不能运行容器或服务。

选择依据包括工作负载生命周期、MPI 与 Fabric、容器与应用控制、隔离、队列政策、Accounting、团队技能和既有硬件。平台可让紧耦合训练进入 Slurm，让在线推理进入 Kubernetes，让普通容器批任务根据数据位置与队列选择。任何默认路由都允许被政策审计，而不是由用户随意绕开成本与安全边界。

## 11. 双栈平台的统一层

统一门户维护平台 Principal 与 Project，再分别映射到 Slurm User、Account、QOS 和 Kubernetes Namespace、ServiceAccount、Queue。映射本身要审计并有生命周期。删除门户用户不能直接删除历史 Accounting 身份；人员离开后停止新授权，保留历史归属。

统一提交对象包含 runID、Project、工作负载类、资源形状、拓扑、时间、优先级、制品 Digest、Checkpoint 与成本边界。路由器选择一个后端并取得运行租约。相同 runID 若已由 Slurm 拥有，就不能再次创建 Kubernetes Job，反之亦然。失败重试沿同一后端幂等恢复。

制品层使用不可变镜像或环境、版本化数据和 Checkpoint。Slurm 可通过容器插件、Apptainer 或站点环境执行，Kubernetes 通过容器 Runtime 执行；门户保存同一逻辑制品 Digest 和后端物化方式。不要假设两个 Runtime 对挂载、用户 ID、网络和 GPU 库完全等价。

状态汇聚把 Slurm Pending、Running、Completing、Completed 等状态与 Kubernetes Job 和高级 Workload 状态映射到稳定平台阶段，同时保留原始 Reason。统一阶段服务用户体验，原始状态服务诊断。映射必须显式处理未知新状态，不能把未知当成失败或成功。

成本汇聚使用统一 runID 与 Project，把 Slurm 的 TRES 用量和 Kubernetes 的 GPU Request 时间、实际计量与云账单关联。两套数据采样和结束语义不同，因此报表显示来源与完整性。没有 Slurm GPU Accounting 或 Kubernetes 成本数据时标记缺失，不用零填充。

## 12. 从登录节点到计算节点的提交链

典型 Slurm 环境把交互入口、控制面与计算面分开。用户在登录节点准备脚本、查看队列并调用 sbatch、salloc 或 srun，请求由 slurmctld 处理，计算任务最终由目标节点的 slurmd 与 slurmstepd 执行。登录节点不是大规模训练节点，不能因为它能访问共享文件系统就直接在上面运行 GPU 程序。平台门户应通过受控 API 或代理提交，而不是让 Web 服务 SSH 到登录节点拼接 Shell。

sbatch 提交批脚本并立即返回 Job ID，脚本在获得 Allocation 后执行。salloc 主要取得交互式 Allocation，用户再在其中运行 Step。srun 既可以请求资源启动 Job，也可以在已有 Allocation 中创建 Step。三者共享许多资源参数，却有不同生命周期。平台若只封装一条命令，需要明确是否支持交互、Step 与信号转发，不能把所有场景都伪装成批脚本。

Job 提交成功只说明控制器接受对象，不说明它立即运行。squeue 里的 Pending Reason 可能来自资源、优先级、Association、QOS、Reservation、Dependency 或站点政策。门户保存 Job ID 后，应异步观察状态，不让 HTTP 连接一直等待 Job 完成。取消使用稳定 ID 并检查所有权，不能让用户通过任意数字取消别人的 Job。

节点被分配后，Slurm 生成 Job 凭证并在计算节点启动任务。Prolog、容器环境、文件系统挂载、GPU 绑定与 MPI 启动都会影响最终可运行性。slurmctld 显示 Running 不等于训练框架已完成初始化。双栈平台统一状态时应增加业务启动阶段，读取应用心跳或结构化日志。

任务完成后，slurmstepd 收集退出状态与 Accounting，Epilog 执行站点清理，节点随后返回可分配状态。Epilog 失败、残留进程、设备错误或文件系统异常可能让节点 DRAIN。平台不能只看 Job Completed 就假设节点健康，也不能在 Epilog 尚未结束时把下一份敏感工作放上去。

提交链每一跳都需要身份连续性。门户 Principal 映射到 Slurm User 与 Account，请求中的 QOS、Partition 和 Reservation 受到服务端校验，Job 环境中的用户身份与文件权限一致。平台服务账号代替所有用户提交会破坏 Accounting 与文件归属，除非使用经过设计的代理身份和 Impersonation 机制，并保留真实用户审计。

## 13. slurmctld 高可用与状态恢复

slurmctld 维护 Job、Node、Partition 与调度状态，是 Slurm 控制面的核心。官方架构允许备用控制器在主控制器故障时接管。高可用设计首先保证 StateSaveLocation 可靠、主备配置一致、身份与网络可达，再考虑进程自动重启。仅运行两个 Pod 或两台虚拟机并不自动构成正确主备。

控制器切换期间，提交、查询与调度可能短暂受阻，但计算节点上的运行任务不应因为门户超时就被重复提交。双栈适配器为每个 runID 保存后端和 Job ID，HTTP 超时后先查询已有 Job，再决定是否重试。若请求结果不确定，重复 sbatch 会产生两个训练并同时写同一 Checkpoint。

StateSaveLocation 包含控制器恢复所需状态，应有正确权限、低延迟和故障域设计。把它放在不稳定网络存储会让主备同时失去状态；只放本地盘又需要可靠主备同步。具体部署依站点架构选择，验收必须实际停止主控制器并观察备用接管、Job 状态和新提交。

配置重载与版本升级不是普通 Web 服务滚动更新。控制器、计算节点守护进程、插件和数据库兼容性要按 Slurm 官方升级指南核对。先保存配置与 Accounting，验证主备，再分批升级计算节点。版本混合是否允许以及允许多久由目标版本文档决定，不从一次偶然成功推断永久兼容。

控制器性能受 Job 数量、节点规模、调度周期、插件、Accounting 和外部查询影响。门户的高频全量轮询、复杂 JobSubmit 插件和大量短 Job 都会增加负载。性能治理应从 Job Array、提交聚合、slurmrestd 缓存和合理刷新入手，不先简单扩大 slurmctld 主机规格。

故障演练至少覆盖主控制器进程退出、主机网络隔离、StateSave 不可用、备用配置漂移和门户请求超时。每次检查运行 Job 是否继续、Pending 是否保持、重复提交是否发生、Accounting 是否连续。没有主备环境时，该项明确 SKIPPED。

## 14. slurmd、slurmstepd 与节点完整性

slurmd 代表计算节点参与 Slurm 集群，报告硬件、状态并启动工作。每个 Job Step 由 slurmstepd 负责进程、I/O、信号、cgroup 和 Accounting 等本地执行。节点注册信息必须与 slurm.conf 声明匹配，尤其是 CPU、内存与 GRES；不一致时应隔离，而不是通过修改状态强制继续。

节点状态比空闲与忙碌丰富。IDLE 表示可分配，ALLOCATED 表示资源被使用，MIXED 表示部分资源占用，DOWN、DRAIN、FAIL 等表示不同不可用边界。DRAIN 可能由管理员设置，也可能由配置或健康问题触发。平台 UI 要同时显示基础状态和 Reason，不能把所有不可用节点归为“离线”。

ResumeProgram 与 SuspendProgram 等弹性节点能力可以把 Slurm 与云资源供应连接，但它们属于站点实现合同。脚本要幂等、有限重试、验证实例身份并安全清理。slurmctld 认为节点可恢复，不代表云一定有容量。与前一篇弹性容量相同，节点启动后还需要驱动、网络、存储和 GPU Profile 门禁。

节点健康检查需要区分 Slurm 注册与业务能力。slurmd 可正常，GPU 却出现 Xid；CPU 与内存正确，RDMA 链路却断开；共享文件系统可挂载，Checkpoint 写入却超时。站点可以用 HealthCheckProgram、Prolog 或外部监控连接这些信号，但不得让慢探针阻塞整个调度循环。

slurmstepd 的退出状态与应用语义也不同。进程退出零可能只是包装脚本完成，模型产物仍未校验；非零可能由 Preemption、Node Fail、Out Of Memory 或应用错误造成。门户保留 Slurm State、ExitCode、DerivedExitCode 和应用验证，不把所有非零统一成“代码失败”。

节点回到 IDLE 前的清理包括残留进程、临时目录、设备状态、容器挂载和敏感凭证。多租户 GPU 集群尤其需要设备复位与数据清理政策。清理失败时 DRAIN 并保留证据，不能因为队列很长就 RESUME 未经确认的节点。

## 15. Partition 设计不是按组织画资源盒子

Partition 是节点集合与调度政策的组合，可定义默认 Partition、时间限制、节点数量、访问组、优先级层级和共享方式。节点能够属于多个 Partition，这给站点表达不同入口带来灵活性，也容易产生重叠政策。设计前先定义产品，再决定是否共享物理节点。

按 GPU 型号划分 Partition 直观，但型号可以同时由 GRES Type 或 Feature 表达。若每个型号、Team、优先级和环境都创建一个 Partition，组合数量快速膨胀。更稳健的做法是用 Partition 表达主要生命周期与硬边界，用 Association、QOS、GRES 与 Constraint 表达其他维度。

在线服务与大训练若共用节点，Partition 重叠和 Preemption 需要极谨慎。一个节点出现在高优先级和低优先级 Partition，不等于高优先级天然可安全拿回。PreemptType、PreemptMode、GraceTime、Checkpoint 与共享方式共同决定。任何抢占前都要验证低优先级应用能恢复。

Partition MaxTime 保护资源不被无限占用，也帮助 Backfill 估算未来空档。用户故意写过长时间会降低可回填机会，写过短则 Job 被时间上限终止。平台可用历史运行时建议，但最终请求与限制必须可见。训练模板应该在 TimeLimit 前收到信号并保存。

节点维护不应临时删除所有 Partition 关系。DRAIN 节点、创建 Reservation 或设置维护窗口能保留拓扑与配置证据。维护结束后先运行节点 Profile 和合成 Job，再恢复状态。批量 RESUME 前检查驱动、固件与文件系统版本。

Partition 验收提交允许用户、禁止用户、超时、节点数超限、重叠节点与默认路由等场景，观察服务端真实 Reason。门户预检若与 Slurm 结果不同，以 Slurm 为准并记录适配器缺口。

## 16. Reservation、Dependency 与时间语义

Advanced Reservation 为一组资源和时间窗口建立明确可用权，常用于维护、培训、关键实验或项目承诺。Reservation 本身可能包含节点、TRES、用户、Account 等范围。统一门户应把预约审批、成本和过期串起来，避免预留节点无人使用。

Job 引用 Reservation 后仍需满足自身资源、Partition、Association 与 QOS 条件。Reservation 不是绕过所有政策的超级权限。预约容量与 Job 形状不匹配时，Job 仍可能 Pending。平台在预约创建时验证预期模板，并在开始前再次预检节点健康。

Job Dependency 表达 after、afterok、afternotok 等运行关系，适合 Slurm 内部批处理链。它不等价于完整 ML Pipeline，因为数据制品、缓存、条件分支、重试、参数和跨后端状态可能需要更高层编排。平台可把简单同集群依赖编译成 Slurm Dependency，复杂流程由 Pipeline 控制器协调。

时间语义需要统一时区和时钟。Reservation 开始、Job 提交、Accounting 与跨集群事件应使用明确时间基准。控制器与数据库时钟漂移会让审计顺序混乱。所有节点与控制面配置时间同步，门户展示用户时区但保存标准时间。

预约前允许可抢占 Job 填充能提高利用率。填充 Job 必须在窗口前有足够 Grace 与 Checkpoint，调度器也要知道 Reservation 边界。若任务声明时间不可信，可能占用预约开始时的节点。站点应使用 TimeLimit 与 Preemption 合同，而不是依靠值班手工取消。

Reservation 故障演练包括节点在开始前 DOWN、预约用户映射错误、形状不足、Job 超时和填充 Job 未退出。验收终点是预约工作在窗口内获得完整健康容量，不是 Reservation 对象创建成功。

## 17. GRES 配置的逐层校验

slurm.conf 里的 Gres 告诉 slurmctld 节点应有多少资源，gres.conf 描述计算节点设备与属性，AutoDetect 从硬件发现信息。三层必须一致。控制器声明八张 A100、节点只发现七张时 DRAIN 是正确结果；强行把节点改回 IDLE 会让调度器分配不存在的设备。

Type 命名要稳定。AutoDetect 报告的设备名会把空格替换为下划线，Type 可以使用匹配子串。站点应选择不会让两个型号意外重叠的标准名称，并通过 `slurmd -C`、`slurmd -G` 与实际 GPU 清单校验。门户只允许批准的 Type，不直接暴露任意字符串。

File 顺序影响 CUDA_VISIBLE_DEVICES 映射，官方文档要求设备文件按数字递增。容器、cgroup、CUDA 与 NVML 可能看到不同逻辑编号，诊断时同时记录 PCI Bus ID、UUID、宿主设备文件和容器内逻辑编号。只用“GPU 0”无法跨层定位硬件。

GPU 与 CPU 亲和通过 Cores 关联，但 Slurm 调度内部按 Socket 处理 GRES 亲和。官方文档说明 Cores 配置需与 Socket 边界一致，并给出使用 L3 Cache 或 NUMA Node 作为 Socket 的参数路径。站点不能把任意 Core 列表写入 GRES 后假定调度器会按 Core 精确放置。

Links 可帮助描述设备互联，而 AutoDetect 能力取决于后端。即使配置有 NVLink 信息，训练性能仍受进程绑定、NCCL 选择、PCIe、NUMA 与网络影响。节点 Profile 通过小规模集合通信校验，不把静态 Links 字段当作性能保证。

GRES 可表示 License、带宽或其他站点资源，并支持 no_consume 等语义。平台扩展自定义 GRES 前明确它是否可消耗、如何发现、失败如何处理和是否进入 TRES Accounting。用 GRES 标签替代真正设备隔离会产生错误安全感。

## 18. GPU 请求、绑定与 Step 继承

`--gpus` 表达每个 Job 总 GPU 数，`--gpus-per-node` 表达每节点数量，`--gpus-per-task` 把设备与任务数连接，`--gres` 可请求通用或带 Type 的资源。适配器选择参数时需保留用户形状。总共十六卡与两节点每节点八卡不是同一个请求，前者可能落到更多节点。

`--cpus-per-gpu` 与 `--mem-per-gpu` 帮助按 GPU 成比例声明主机资源。训练数据加载、NCCL 线程、Checkpoint 与编译需要 CPU 和内存。如果只请求 GPU，默认 CPU 或内存可能不足；如果过度请求，又降低装箱与 Fair-share。模板由真实 Profile 校准。

`--gpu-bind` 控制任务和 GPU 亲和，仍要结合 CPU 绑定与应用启动。每个 Task 一 GPU 的训练通常用 tres-per-task 或 gpus-per-task 表达，但 MPI Launcher、Slurm MPI 插件和框架环境必须一致。错误配置可能让多个 Rank 看见同一 GPU 或跨 NUMA 访问。

Job Allocation 获得 GPU 后，Step 默认与显式请求规则需要仔细理解。不同 Step 可以在 Allocation 内部使用子集，但不能超出 Job 获得的资源。并行 Step 要使用互斥与正确资源声明，否则互相等待。平台若支持多 Step 模板，应验证每一步总和和并发，而不是只验证 Job 上限。

Job 被 SUSPEND 时，官方 GRES 文档说明已分配 Generic Resources 不会因此变成可用。因而用 SUSPEND 抢占 GPU Job 可能无法释放 GPU 给高优先级任务，除非站点采用适合的时间切片设计。抢占模式选择要以资源释放实测为准。

绑定验收在计算节点内部运行设备枚举、UUID 映射、CPU NUMA、显存小分配和双 Task 隔离。用两个并发 Job 尝试访问对方设备，确认 cgroup 约束有效。只有 CUDA_VISIBLE_DEVICES 不同而设备文件仍可打开时，隔离验收失败。

## 19. MIG 生命周期与配置漂移

MIG 把支持的 GPU 划成硬件隔离实例，几何由 GPU 配置决定。Slurm 可以调度已经存在的 MIG 设备，却不负责根据队列动态重分。平台需在节点无 Job 时变更几何，重启或更新必要服务，重新发现 GRES，再将节点恢复到对应 Profile。

一个物理 GPU 上的 MIG 实例共享故障域。多个租户获得不同实例并不意味着物理卡故障互不影响。平台产品说明显存与计算隔离、故障域、监控缺口和重配置窗口。安全等级还取决于设备驱动、cgroup、容器与主机隔离。

MIG Type 应包含足以区分 Profile 的信息。用户请求一个任意 `gpu:1` 可能匹配整卡或 MIG，产生严重歧义。站点可使用具体 Type、独立 Partition 或 JobSubmit 政策阻止泛型请求落入混合资源。Kubernetes 侧也需用资源名、DRA 属性或 Node Profile 表达相同产品边界。

官方 GRES 文档指出 NVML 不提供 MIG 利用率指标，因此 gpumem 与 gpuutil Accounting 存在缺口。站点可结合 DCGM 等外部监控，但要标明数据来源与采样语义。跨后端报表不能拿 Kubernetes 完整指标和 Slurm 缺失字段直接比较。

MIG 重配置必须确认物理 GPU 上没有运行 Job 和残留进程。仅看 Slurm IDLE 不够，Prolog、监控或非 Slurm 进程可能占用设备。变更前 Drain 节点，完成后检查 GPU 清单、GRES、cgroup、容器和计算，再 RESUME。

漂移检测比较期望几何、实际 MIG 实例、设备 UUID、Slurm GRES 和 Accounting Type。任一不一致就隔离。自动修复有次数上限，连续失败需要人工检查驱动、固件或 GPU 状态，避免反复切换损伤运行稳定性。

## 写在最后

后端选定之后，需要一套能表达多角色分布式作业的工作负载 API。下一篇：[分布式 AI 工作负载 API：JobSet、LeaderWorkerSet 与失败语义](/source/AI-Infra/4-AI平台工程/17-分布式AI工作负载API-JobSet-LeaderWorkerSet与失败语义)。