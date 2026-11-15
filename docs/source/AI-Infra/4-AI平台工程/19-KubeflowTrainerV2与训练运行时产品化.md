# Kubeflow Trainer V2 与训练运行时产品化

同一段 PyTorch 训练代码，研究员在 Notebook 中用两张 GPU 运行成功，提交到四节点集群后却卡在会合；另一个团队把镜像改成 latest 修复依赖，第二天相同任务得到不同结果；第三个团队为了挂载数据，直接覆盖 ServiceAccount 和 SecurityContext，顺手绕过了平台的对象存储权限与容器安全策略。三个问题表面分别属于分布式通信、镜像管理和权限控制，根因却相同：平台只提供了“创建 Pod”的入口，没有把训练环境、框架启动方式、资源结构和组织约束做成稳定产品。

![Kubeflow Trainer V2 与运行时](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l19_01.png)

Kubeflow Trainer V2 试图把这种碎片化接口收敛为 TrainJob 与 Runtime。训练用户表达模型代码、节点数量、每节点资源和少量业务参数；平台管理员维护 ClusterTrainingRuntime 或命名空间级 TrainingRuntime，把框架镜像、JobSet 模板、MLPolicy、调度策略、初始化器与安全默认值封装起来；控制器再把两者组合成可执行对象。产品化的关键并不是少写几行 YAML，而是明确哪些字段属于用户意图、哪些属于平台策略、谁能覆盖什么、版本如何演进、失败如何聚合。

本文以 2026 年 8 月 22 日可核验的官方一手资料为事实基线。生产稳定版本采用 Kubeflow Trainer v2.2.1；v2.3.0 仍处于候选发布阶段，不作为稳定基线。稳定文档中的核心 API 为 trainer.kubeflow.org/v1alpha1，主要对象是 TrainJob、TrainingRuntime 与 ClusterTrainingRuntime。官方最新文档网站可能随开发分支展示更前沿的字段或 API 版本，例如 RuntimePatches 页面出现 v2alpha1 示例，因此真实部署必须以已安装 CRD、固定发行标签和对应发布说明为准，不能只复制网站当前片段。

## 1. 训练平台的产品不是一个提交按钮

提交按钮只解决了请求入口。一次可复现训练还依赖代码版本、基础镜像、Python 包、驱动与框架兼容、数据位置、模型初始化、分布式启动器、网络发现、GPU 数量、拓扑、队列、检查点、制品写回、身份、安全上下文和超时。任何一项留给个人临时拼接，平台都会积累无法重放的特殊作业。

真正的训练产品应把变化分为两类。业务变化由训练用户掌握，例如训练函数、数据集、超参数、节点规模和输出名称；基础设施变化由平台团队治理，例如镜像来源、运行身份、挂载方式、调度器、安全约束、观测端点与回收策略。Runtime 是两类变化之间的版本化接口，而不是一份无限开放的 PodTemplate。

## 2. 从框架专用 CRD 走向统一 TrainJob

Training Operator V1 为不同框架提供 PyTorchJob、TFJob、MPIJob 等专用资源。它们直接表达各框架的副本角色和启动结构，简单直观，但平台必须维护多套 Schema、准入规则、SDK 与门户表单。同样的镜像、队列、安全和制品策略需要在多个 Kind 上重复实现。

Trainer V2 引入统一 TrainJob，并让 Runtime 描述框架和执行模板。用户不再先选择某个框架专用 CRD 再填完整 Pod 结构，而是引用一个经过平台批准的 Runtime。统一不意味着所有框架行为相同；差异转移到 MLPolicy、模板和插件中，公共生命周期则由 TrainJob 统一呈现。

## 3. 统一 API 减少的是产品分叉，不是框架复杂性

PyTorch 的 torchrun、MPI 的 launcher、JAX 的协调过程和 XGBoost 的工作节点仍有不同语义。Trainer 不能用同一个魔法命令消除这些差异，它能做的是把差异封装在管理员维护的 Runtime 里，使使用者面对相似的提交、观察、取消和结果接口。

平台评审因此不能只问“是否支持 PyTorch”。还要问支持哪种启动器、哪些并行策略、怎样计算 world size、主节点如何发现、失败是否整体重试、检查点如何恢复、网络和拓扑需要什么前提。Runtime 名称必须对应这些具体合同，而不是一个宽泛框架标签。

## 4. TrainJob 是一次训练意图的持久记录

TrainJob 保存用户对一次运行的声明，包括引用的 Runtime、训练器配置、节点与资源、初始化和可能的运行时补丁。控制器观察该资源，选择 Runtime，完成默认化与校验，构建底层 JobSet，并将执行状态回写到 TrainJob。用户因此可以围绕一个稳定对象查询生命周期，而不必自行拼接多个 Pod 状态。

持久记录也带来审计价值。平台可以回答谁在何时使用哪个 Runtime 版本、申请多少 GPU、由哪个队列准入、最终生成哪个 JobSet、是否超时、制品写到哪里。若门户只调用后台脚本创建 Pod 却不保存高层对象，这些关系会随着日志轮转而丢失。

## 5. TrainJob 不是底层所有字段的拥有者

一个危险设计是把完整 PodSpec 重新暴露到 TrainJob 表单，让用户任意改镜像、ServiceAccount、hostPath、特权模式和调度器。这样虽然灵活，却让 Runtime 退化为示例模板，平台无法保证安全、可复现和支持边界。

合理的接口只开放有业务意义且能够验证的字段。节点数和 GPU 数可以开放并设置上限；训练命令可以开放，但只能在固定镜像与身份中执行；普通环境变量可以通过受控补丁增加，而安全上下文和凭据挂载应由平台拥有。开放字段越多，兼容测试矩阵越大。

## 6. ClusterTrainingRuntime 是集群级共享蓝图

ClusterTrainingRuntime 属于集群范围，适合平台管理员提供组织统一的训练蓝图。多个命名空间可以引用同一个 Runtime，从而共享镜像、框架启动策略、JobSet 结构和安全默认值。官方 Runtime 指南把它描述为可在整个集群重用的模板。

共享范围意味着变更影响面很大。直接修改同名 ClusterTrainingRuntime 会影响后续所有引用者，因此生产上应采用不可变版本名称或显式版本标签，例如 torch-distributed-2-2-cuda128，而不是长期覆盖一个含义不断变化的 latest 名称。旧版本在迁移窗口内保留，直到所有运行和回放合同完成迁移。

## 7. TrainingRuntime 提供命名空间级定制

TrainingRuntime 是命名空间范围对象，只能被同一命名空间的 TrainJob 引用。它适合团队需要特定框架插件、合规镜像或数据挂载，而这些差异不应扩散到整个集群的场景。命名空间作用域同时给 RBAC 提供更清晰的委派边界。

局部定制不等于团队可以任意绕过平台规则。平台可通过准入策略限制谁能创建 TrainingRuntime、允许哪些镜像和字段，并要求基础安全合同仍然成立。若普通用户拥有任意 Runtime 写权限，他们实际上就拥有了生成任意 PodTemplate 的能力。

## 8. RuntimeRef 建立运行请求与蓝图的显式关联

TrainJob 通过 runtimeRef 引用 Runtime。引用需要能够区分 ClusterTrainingRuntime 与 TrainingRuntime，并指向实际名称。控制器在展开前解析引用；不存在、跨命名空间或类型错误时，应停留在明确的等待或失败状态，不能悄悄换用默认 Runtime。

显式引用支持审计和回放。仅保存“PyTorch”不足以重建环境，因为同一框架可能有多个 CUDA、通信库和启动器组合。保存具体 Runtime 名称、对象 UID 或摘要、镜像摘要与 CRD 版本，才能在事后解释运行差异。

## 9. framework 标签连接 Runtime 与 SDK 能力

官方 Runtime 指南要求每个 Runtime 带 trainer.kubeflow.org/framework 标签，Kubeflow SDK 据此识别 BuiltinTrainer 可用的框架配置。缺少标签时，原生控制器可能仍能看到对象，但 SDK 无法可靠判断如何构造用户体验。

标签不是安全证明。写上 torch 并不能验证镜像确实包含 PyTorch，也不能证明命令符合 torchrun。平台发布 Runtime 时要执行镜像探测、包版本读取、单节点自检和多节点会合测试，再把标签作为已验证事实的索引。

## 10. Runtime 中的模板最终面向 JobSet

官方 Job Template 指南说明 Runtime 的 Template API 定义用于编排 TrainJob 资源的 JobSet 模板。控制器综合 TrainJob、Template、PodGroupPolicy 和 MLPolicy 生成底层 JobSet。JobSet 负责多组 Job 的协调、成功策略和失败传播，是高层训练意图与 Kubernetes Job 之间的执行桥梁。

这条链应被平台观测完整保留：TrainJob 指向 Runtime，TrainJob 拥有或关联 JobSet，JobSet 再拥有 Job 与 Pod。排障时从高层 Condition 向下钻取，而不是只看某个失败 Pod。OwnerReference 和统一标签是成本归属、清理与日志关联的基础。

## 11. ReplicatedJob 表达一类可复制执行单元

JobSet 模板包含 ReplicatedJobs。典型 torch-distributed Runtime 使用名为 node 的 ReplicatedJob，每个副本代表一个训练节点，对应一个 Kubernetes Job 和 Pod 模板。节点数由 Runtime 默认或 TrainJob 训练器参数决定，框架插件再配置每节点进程数和分布式环境。

平台必须区分节点副本与 GPU 进程。四个节点、每节点四张 GPU 通常得到十六个训练进程，但底层可能仍只有四个 Pod；若一个 Pod 启动多个进程，资源限制、日志、健康和故障语义都与每 GPU 一个 Pod 不同。门户不能把“Worker 数”含糊地同时表示二者。

## 12. MLPolicy 把框架语义加入通用模板

MLPolicy 描述训练框架需要的规则，例如节点数量和 PyTorch 每节点进程数。通用 JobSet 只知道如何运行 Jobs，并不知道 torchrun 的 rank、world size 或主节点地址。Trainer 插件根据 MLPolicy 向模板注入框架所需配置。

这种分层避免把所有框架逻辑写死在 TrainJob Schema 中。新增框架可以通过 Runtime 与扩展机制加入，而公共 API 仍围绕训练意图。代价是平台必须对插件版本和模板假设做联合测试，不能把一个 MLPolicy 字段复制到不兼容模板。

## 13. numProcPerNode 的 auto 需要资源合同支持

PyTorch Runtime 常把 numProcPerNode 设置为 auto，使每节点进程数根据可用加速器推导。这个便利只有在资源请求明确且容器可见设备与请求一致时才可靠。若只写 limit 不写 request、使用共享 GPU 或设备注入异常，自动推导可能与预期不同。

平台应在准入时计算并展示预期 world size，并在启动日志中记录实际 WORLD_SIZE、RANK 与 LOCAL_RANK。二者不一致时直接阻断训练，比等到梯度同步超时更容易诊断。对 MIG、时间片共享和异构设备，需要额外定义一个资源单位对应多少训练进程。

## 14. Python SDK 是用户接口，不是事实来源替代品

Kubeflow Python SDK 提供 TrainerClient、CustomTrainer 和 BuiltinTrainer 等接口，使训练函数可以转化为 TrainJob。SDK 能序列化函数、安装附加包、提交任务、等待状态和读取日志，降低用户直接操作 YAML 的门槛。

SDK 生成的仍是集群 API 对象。平台排障必须查看最终 TrainJob 和 CRD，而不是只根据 Notebook 中的 Python 调用猜测。SDK 版本、服务端 Trainer 版本和 CRD 版本需要兼容矩阵；客户端升级不能先于服务端支持的字段。

## 15. CustomTrainer 适合包装自有训练函数

官方 PyTorch 指南允许把训练逻辑封装在函数中交给 CustomTrainer。函数在远端训练节点执行，因此所需导入要放在函数体内，不能依赖 Notebook 进程中已经导入的模块。远端文件系统、环境变量和凭据也与本地会话不同。

产品化时应限制函数序列化边界。闭包捕获的大对象可能导致提交包膨胀，隐式本地路径会在容器中失效，Notebook 中的临时凭据更不应被序列化。推荐把稳定代码构建进固定镜像或版本化制品，只让 SDK 传递小型入口和参数。

## 16. BuiltinTrainer 把常见训练配方进一步产品化

BuiltinTrainer 面向平台预定义的训练方案，例如特定模型族与微调工具。用户填写模型、数据和少量超参数，Runtime 决定镜像、入口、依赖和分布式结构。它比 CustomTrainer 更受约束，也更容易做成本预估和兼容验证。

内置并不代表通用。每个配方都要明确支持的模型、精度、并行方法、数据格式、最大规模和输出合同。平台若把所有 LLM 微调都塞进一个 Runtime，条件分支会迅速失控；按稳定能力集合拆分多个版本更可维护。

## 17. packages_to_install 提高便利性也降低可复现性

SDK 允许为训练节点声明运行时安装包。这适合探索，但生产作业在启动时访问外网或包仓库，会受到版本漂移、供应链、下载时延和网络故障影响。多节点同时安装还会放大镜像冷启动和仓库压力。

生产 Runtime 应把核心依赖构建进摘要固定镜像，并生成 SBOM 与漏洞记录。确需动态安装时，使用内部镜像源、锁定精确版本与哈希、设置缓存和超时，并把最终解析出的包清单写入运行元数据。不能仅保存用户输入的宽松版本范围。

## 18. 镜像是 Runtime 最重要的可执行合同

镜像同时决定操作系统、Python、框架、CUDA 用户态库、通信工具和训练入口。镜像标签可以被重写，摘要才是可复现标识。平台应允许用户选择经过批准的 Runtime 版本，而不是任意输入镜像字符串。

镜像发布要经过分层验证：静态扫描检查来源和漏洞；CPU 启动检查导入；GPU 节点检查设备与框架；单节点多卡检查 collective；多节点检查网络和 NCCL；最后运行小型训练并写出制品。任一层失败都不能只靠修改标签重新发布。

## 19. Runtime 模板必须显式指定运行身份

训练 Pod 访问对象存储、镜像、日志和密钥，需要 ServiceAccount 与外部身份映射。若 Runtime 不指定，Kubernetes 会使用命名空间 default ServiceAccount，权限来源容易模糊。若允许用户覆盖，则可借用高权限身份读取不应访问的数据。

平台应为 Runtime 分配最小权限 ServiceAccount，按团队或数据域绑定云身份，禁用不需要的令牌自动挂载，并把访问审计关联到 TrainJob。数据读取和模型写出可以使用不同凭据或受控代理，避免训练代码同时拥有宽泛读写权。

## 20. SecurityContext 属于平台不可覆盖字段

runAsNonRoot、allowPrivilegeEscalation、capabilities、seccomp 和只读根文件系统构成容器基线。训练框架若确有共享内存、锁页或特定设备需求，应通过受审 Runtime 显式提供，而不是给所有用户开放 privileged。

平台策略要作用在最终生成的 JobSet 和 Pod 上，因为只校验 TrainJob 输入可能漏掉 Runtime 或 Webhook 注入。正向测试确认合法训练可运行，反向测试尝试通过 RuntimePatches、命令或额外挂载绕过，并验证在准入阶段被拒绝。

## 21. RuntimePatches 解决多方修改所有权问题

Trainer v2.2 引入 RuntimePatches 替代早期 PodTemplateOverrides。其核心思想是不同控制器以 manager 名称拥有各自补丁条目，用户、Kueue 和准入 Webhook 可以分别贡献配置，减少对同一平面列表的争用。Admission Webhook 在创建 JobSet 前合并这些补丁。

多所有者不代表冲突自动安全。平台必须限制 manager 命名、可修改路径和补丁操作，检测多个管理者对同一字段的相互覆盖，并记录最终合并结果。若用户能写入平台 manager 或修改 ServiceAccount 路径，所有权模型就失去意义。

## 22. 网站示例与安装 CRD 不一致时以集群为准

官方文档网站可能面向最新开发线，而稳定发行仍使用不同 API 版本。当前 RuntimePatches 页面展示 v2alpha1 示例，稳定 v2.2.1 的其他指南仍使用 v1alpha1。照抄片段可能在服务器返回 no matches for kind，或更危险地命中新 Schema 却产生不同默认值。

部署脚本应先读取 CRD served 与 storage 版本，再使用与发行标签绑定的清单。CI 对目标集群执行 server-side dry-run，并保存生成对象摘要。文档可解释概念，但生产流水线不能通过网页片段动态决定 API。

## 23. 用户补丁应采用允许列表

最安全的开放方式不是列举少数禁止字段，而是列出允许路径，例如训练容器普通环境变量、业务标签、资源规模和特定容忍度。PodSpec 字段众多，未来 Kubernetes 新增字段时，拒绝列表容易默认放行未知能力。

允许列表还应校验值。环境变量名不能覆盖平台注入的 MASTER_ADDR、WORLD_SIZE 和凭据路径；标签不能冒充队列或成本归属；容忍度不能进入受保护节点池；资源不能超团队上限。补丁经过规范化后再参与摘要和审计。

## 24. Dataset Initializer 把数据 I/O 从 GPU 训练阶段分离

Trainer V2 迁移文档强调自定义数据集与模型初始化器，用 CPU 工作负载准备资产，从而减少 GPU 等待 I/O 的成本。初始化阶段可以下载、校验、解压和转换数据，训练容器只消费已经就绪的路径。

分离后必须定义交接合同：数据版本、校验和、目录权限、完成标志、失败重试和清理策略。若初始化器只在共享目录写入部分文件就退出，训练节点可能读到不完整数据。使用原子完成标志或内容寻址目录，避免把“Pod 成功”当成“数据一致”。

## 25. Model Initializer 需要处理大模型分发放大

多节点训练若每个 Pod 独立从远端下载同一模型，会产生 N 倍带宽、对象存储请求和启动抖动。Model Initializer 可以预取到共享存储、节点缓存或分布式缓存，再由训练节点消费。选择取决于模型大小、存储带宽和节点本地容量。

缓存命中必须以模型内容摘要和转换参数为键，不能只用易变名称。量化、分片和 tokenizer 版本都会改变实际字节。缓存污染时应隔离新目录并回退，而不是覆盖正在被运行使用的路径。

## 26. 分布式数据缓存是独立数据面

官方 Data Cache 指南描述使用 Apache Arrow、DataFusion 与 Arrow Flight 构建分布式缓存，对对象存储数据预处理和分区，再向多个 TrainJob 流式提供。它可以减少重复预处理和复制，但也引入缓存节点、元数据、容量与网络故障域。

平台要分别观察缓存填充和训练消费。GPU 利用率下降可能源于缓存未热、分区倾斜、Flight 连接或训练计算，而不是统一归因于存储慢。租户隔离、数据授权和缓存生命周期也不能因为缓存位于集群内就省略。

## 27. Checkpoint 是训练生命周期合同而非普通输出文件

长时训练必须周期保存可恢复状态，包括模型参数、优化器、学习率调度、随机数状态、数据游标和分布式分片信息。只保存模型权重可以用于推理，却未必能无损继续训练。Runtime 应规定检查点格式、原子提交和保留策略。

写检查点时多个 rank 的职责要明确。某些方案只由 rank0 聚合写出，另一些按 rank 保存分片；恢复时 world size 变化是否支持取决于框架。平台不能把所有目录简单复制到对象存储后就宣称可恢复，必须执行真实中断与恢复验收。

## 28. Output Model 需要可注册的制品契约

最终模型不是任意目录。至少应包含权重、配置、tokenizer 或特征处理、代码版本、基础模型引用、训练数据版本、许可证信息和评测摘要。写回成功后生成不可变 URI 与摘要，再由模型注册流程建立版本。

训练成功但制品写回失败不能标记整条交付为成功。TrainJob 状态、业务状态和流水线状态可以区分计算完成与发布完成；用户界面应明确需要重试哪一步。若直接重跑整个训练只为补一次上传，会浪费大量 GPU。

## 29. Kueue 负责准入与配额而不是框架启动

Trainer 可与 Kueue 集成，让 TrainJob 进入 LocalQueue，由 ClusterQueue 依据 ResourceFlavor、配额和策略准入。Kueue 决定何时可以使用资源，Trainer 和 Runtime 决定准入后如何构建并运行分布式训练。两者职责互补。

## 写在最后

训练之外，另一类常见负载是 Python 原生的分布式计算与服务。下一篇：[KubeRay：RayCluster、RayJob、RayService 与多层扩缩](/source/AI-Infra/4-AI平台工程/20-KubeRay-RayCluster-RayJob-RayService与多层扩缩)。