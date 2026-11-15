# Kubeflow 平台组件、Profiles 与多用户隔离

一名算法工程师登录平台后，在页面里只能看到自己的 Notebook；他却在 Notebook 容器中使用错误的 ServiceAccount 列出了另一个团队的 Secret。另一名用户无法打开相邻团队的页面，于是平台宣布“租户隔离已经完成”；实际原因只是路由返回了 403，底层 Pod 网络仍可直接连通。还有一个团队删除 Profile 清理测试账号，控制器随即删除了同名 Namespace，连 PVC 和运行记录也一起进入级联删除。三个现场都出现了“Profile”，但它们分别暴露了身份、授权、网络与生命周期边界没有被当成一份完整合同。

![Kubeflow 组件与多用户隔离](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y4_l18_01.png)

Kubeflow 的多用户能力不是一个开关。Profile 把用户、Contributor 与 Namespace 关联起来，Profile Controller 和访问管理组件生成部分 RBAC 与 Istio AuthorizationPolicy；Central Dashboard 利用活动 Profile 呈现相应页面；Notebook、Pipelines 等组件再按各自的 API 和身份传播方式执行访问判断。ResourceQuota、LimitRange、NetworkPolicy、Pod 安全、对象存储凭据和 Kueue 队列并不会因为 Profile 存在就自动满足企业策略，它们必须由平台额外编排并持续验证。

本文的核心判断是：Profile 是租户工作空间的声明式入口，不是完整安全边界。可靠的 AI 平台至少同时验证五条链。第一条是外部身份到可信入口；第二条是用户身份到 Namespace 内 RBAC；第三条是入口工作负载身份、用户请求头与 Istio 授权；第四条是 Pod 身份、网络、存储和密钥隔离；第五条是配额、队列、删除与审计。任一链断裂，页面上的租户选择器都不能替代实际隔离。

技术事实以 2026 年 8 月 22 日能够从官方一手资料核验的版本为基线。稳定发行选择 Kubeflow Community Distribution 26.03.1；Profile 与 Notebook 均使用 kubeflow.org/v1 API；Kueue 沿用本系列锁定的 v0.19.0。Kubeflow 各子项目独立发布，发行版还会组合 Istio、认证代理、证书、数据库和对象存储，因此任何安装清单都必须固定发行标签、组件矩阵、CRD 摘要与升级说明，不能把 master 分支示例直接当成生产合同。

## 1. Kubeflow 首先是一组子项目，不是一个不可拆分的二进制

Kubeflow 官方把平台描述为面向 Kubernetes 的 AI 平台工具基础。Notebooks 负责交互开发环境，Trainer 负责分布式训练，Katib 负责超参数与 AutoML 实验，Pipelines 负责工作流，Hub 与模型相关能力负责元数据和制品，Central Dashboard 则把多个 Web 界面汇聚到一个入口。各项目有自己的控制器、API、数据面、发行节奏和故障域。

这意味着“安装了 Kubeflow”不是足够精确的状态。一个集群可能只安装 Pipelines；另一个安装 Dashboard、Profiles、Notebooks 和 Katib；第三个使用完整 Community Distribution，并接入企业身份提供者与外部对象存储。三者的用户体验、隔离边界、升级责任和资源开销都不同。平台资产清单应列出实际启用的子项目，而不是只写一个 Kubeflow 版本。

组件化也意味着故障不会自动共享同一个恢复策略。Central Dashboard 不可用时，已有 Notebook Pod 仍可能运行；Profile Controller 暂时不可用时，已存在的 RBAC 继续由 Kubernetes 授权器执行；Pipelines 数据库故障会影响新的运行编排，却不应被误判成所有训练 Pod 都失去权限。每个组件都要有独立 SLO 和降级模式。

## 2. Community Distribution 是一份经过组合验证的参考发行，不是所有企业环境的唯一形态

官方安装页在当前基线下区分 Kubeflow 子项目、Kubeflow Community Distribution 与厂商打包发行版。Community Distribution 把官方组件和常用公共依赖组合起来，提供 Kustomize 清单、集成测试和已验证版本集合。26.03.1 采用日历式版本号，官方建议希望获得稳定保守体验的用户选择最新稳定分支，而不是直接追随 master。

参考发行的价值在于减少未经验证的版本排列。Dashboard、Profiles、Notebooks、Pipelines、Istio、Cert Manager、认证代理和存储组件之间存在接口依赖。单独看每个项目都能启动，不代表组合后登录、授权、回调、Webhook 和数据迁移正确。发行版的端到端测试为某个组合提供了起点，但企业仍需在自己的 Kubernetes、CNI、CSI、身份和策略环境中重新验收。

参考发行也不是商业支持承诺。官方仓库明确说明社区支持是尽力而为，并建议需要长期支持的组织选择合适的发行方或建立内部维护能力。因此把“上游稳定标签、企业内验证标签、运行环境版本”分开记录；升级决策以本地证据为准，不以组件页面上出现了新版本为准。

## 3. 独立安装子项目适合已经拥有平台控制面的团队

一个企业若已有统一门户、OIDC、命名空间供应、队列、模型注册与 GitOps，重新引入完整 Dashboard 和认证栈可能造成重复控制面。此时可以只部署 Trainer、Katib、Pipelines 或 Notebooks 控制器，再由现有平台 API 生成这些 CR。官方安装文档允许子项目独立使用，这也是 Kubeflow 可组合性的实际意义。

独立安装降低了不需要组件的资源和升级负担，却把集成责任交给平台团队。Profile 不再天然成为所有组件的共同工作空间接口，身份传播、Namespace 选择、RBAC、路由和审计需要自行实现。Pipelines 的独立模式与 Community Distribution 多用户模式也不同，不能把单用户端点放进企业入口后就宣称获得多用户隔离。

选择最小组件组合时，应从用户旅程反推。若只需声明式训练，Trainer 加 Kueue 可能足够；若需要交互 Notebook，至少还需镜像、PVC、身份、入口和闲置治理；若需要流水线，则还要数据库、对象存储、API 身份和运行 Namespace。工具数量减少不等于能力责任消失，只是责任转移到已有平台。

## 4. 厂商发行版与上游参考发行必须分别建立兼容矩阵

厂商发行版可能替换入口、认证、存储、Service Mesh、镜像仓库或部分控制器，也可能延长某个 Kubeflow 版本的支持周期。页面仍叫 Profile 或 Notebook，不代表 CRD Schema、默认策略和升级路径完全相同。运维手册必须引用实际发行方的版本与补丁说明，同时保留上游 API 语义作为概念依据。

兼容矩阵至少记录 Kubernetes、Kubeflow 发行、Dashboard、Notebook、Pipelines、Trainer、KServe、Istio、Cert Manager、CNI、CSI 和数据库版本。对每个组合保存 Server-Side Dry Run、核心正例、权限反例、网络反例与回滚结果。只记录 Helm Chart 或 Kustomize 目录版本，无法证明其引用镜像和 CRD 已经对应。

托管平台还要确认责任边界。云厂商可能负责控制器升级，却不负责用户镜像中的漏洞；负责身份入口，却不保证自定义 NetworkPolicy 正确；负责数据库备份，却不保证流水线制品桶的租户前缀。责任表要落到组件和数据对象，而不是写成模糊的“平台由供应商维护”。

## 5. 组件地图要按控制职责划分，而不是按菜单排列

Dashboard 菜单把 Notebooks、Katib、KServe 和 Pipelines 放在相邻位置，容易让人误以为它们属于一个进程。工程地图应按职责划分。入口层包含认证代理、Gateway、Central Dashboard 和各 Web App；工作空间层包含 Profile Controller、访问管理、Namespace、RBAC 和授权策略；工作负载层包含 Notebook、Trainer、Katib、Pipelines、KServe 等控制器；数据层包含 PVC、对象存储、数据库与元数据服务。

同一个用户动作会跨越多个层。创建 Notebook 时，浏览器先通过外部身份认证，经 Gateway 进入 Dashboard，再进入 Jupyter Web App；Web App 根据用户身份和活动 Profile 发起 Notebook CR 创建；Kubernetes RBAC 决定 API 写入；Notebook Controller 创建 StatefulSet、Service 与 Pod；调度器、CSI 和设备插件完成实际资源交付。任何一层失败都可能在页面表现为“Notebook 启动失败”。

排障地图应为每层保留原生状态。入口看 HTTP 状态、认证会话和 Gateway 日志；授权看 SubjectAccessReview、RoleBinding 和 AuthorizationPolicy；控制器看 CR Condition 与 Event；资源交付看 Pod、PVC、GPU 和调度事件；业务看 Jupyter 进程和用户请求。把所有错误压成一个前端 Toast 会丢失责任边界。

## 6. 平台组件、用户工作负载与共享数据面是三类不同故障域

系统 Namespace 中的 Dashboard、Profile Controller 和 Pipelines API 属于平台组件。Profile Namespace 中的 Notebook、训练 Job 和推理服务属于用户工作负载。数据库、对象存储、镜像仓库和身份提供者可能是集群内共享服务，也可能在集群外。三者的扩缩、备份、权限和变更节奏不同。

平台组件应使用专用 ServiceAccount 和最小权限，不能借用用户 Namespace 的 default-editor。用户工作负载需要 Namespace 内权限时，也不应获得系统 Namespace 写权限。共享数据面必须通过租户凭据、路径、数据库租户字段或独立实例隔离，不能因为调用方来自不同 Namespace 就假定数据自动分开。

故障演练也分层。停止 Dashboard 验证入口降级，不应删除用户 Pod；停止 Profile Controller 验证已有策略是否继续执行，并记录新 Profile 供应受阻；撤销某个租户对象存储凭据只影响该租户。一次演练若同时改变三层，就无法确定是哪项保护真正生效。

## 7. Central Dashboard 是统一入口，不是身份提供者

官方 Dashboard 仓库明确说明认证取决于 Kubeflow 平台的安装方式，不由 Dashboard 本身直接处理。Community Distribution 通常通过外部身份提供者、OAuth2 Proxy 与 Istio Gateway 建立登录链，Dashboard 消费已经认证的请求。将 Dashboard 页面暴露到网络，并不会自动产生可信用户身份。

Dashboard 的主要职责是提供经过认证的 Web 入口、活动 Profile 选择和组件页面导航。它可以把第三方应用加入菜单，也可在链接中使用活动 Namespace。但菜单可见性不是资源授权；用户知道另一个页面 URL 时，后端仍必须独立验证身份与 Namespace 权限。

平台评审要分开问三个问题：谁完成认证，谁把身份可靠传给后端，谁在目标资源上做授权。若三个答案都写成“Dashboard”，设计就缺少可审计边界。浏览器、入口代理、Gateway、Web App 和 Kubernetes API 各自需要明确的信任关系。

## 8. 从登录到 Notebook 的请求链必须逐跳说明身份

一次典型访问从浏览器携带登录会话进入 Gateway。认证代理验证会话，把规范化用户标识交给受信任入口；Istio 根据请求来源工作负载身份和用户属性执行 AuthorizationPolicy；Dashboard 展示用户可访问的 Profile；Jupyter Web App 再代表用户读取或创建目标 Namespace 中的 Notebook 资源。

这里存在两种身份。人类身份回答“谁点击了按钮”，通常表现为邮件或 OIDC Subject；工作负载身份回答“哪个服务转发了请求”，在 Istio 中通常由 mTLS 证书映射为 ServiceAccount Principal。安全策略必须同时约束二者，否则任意 Pod 只要伪造用户请求头就可能冒充用户。

当 Web App 调用 Kubernetes API 时，还要看它是用自身 ServiceAccount 进行 SubjectAccessReview 后代理，还是把用户认证映射给 API Server。不同发行版实现可能不同。验收不能只看浏览器 403，还要执行 kubectl auth can-i、检查后端日志中的决策主体，并确认直接调用内部 Service 不会绕开入口授权。

## 9. 活动 Profile 是页面上下文，不是不可伪造的安全标签

Central Dashboard 顶部的 Profile 选择器决定多数组件页面显示哪个 Namespace。它改善用户体验，也让 Web App 能够生成带 Namespace 的 API 请求。然而选择器只是客户端和服务端之间的上下文，攻击者可以修改 URL、请求体或直接调用 API，因此后端必须重新验证用户是否属于目标 Profile。

一个常见错误是前端只向用户展示允许的 Namespace，然后后端相信传入的 namespace 参数。正常操作看起来完全隔离，修改请求即可越权。正确实现是在每次读取、创建、更新和删除时，根据认证用户、目标 Namespace 和动作执行授权，不能把上一次选择结果当作长期授权缓存。

缓存仍可用于性能，但必须以身份、Namespace、动作、策略版本和短过期时间为键。Contributor 被移除后，缓存需要迅速失效；Profile 删除或重建后，旧缓存不能因名称相同而继承。审计记录应保存用户、活动 Profile、实际目标 Namespace 和最终授权来源。

## 10. 第三方 Web App 接入 Dashboard 时必须继承相同授权合同

Dashboard 允许通过配置加入第三方菜单，也支持在路径中使用活动 Namespace。官方文档说明，位于 Profile Namespace 中的应用可以依赖现有 AuthorizationPolicy 限制 Profile Contributor 访问。这个便利只成立于应用流量确实经过受信任 Gateway、策略选择了正确工作负载且后端没有额外绕行端点。

接入评审应检查 VirtualService 路径是否包含不可混淆的 Namespace，AuthorizationPolicy 是否限制受信任 Principal 和用户标识，Service 是否仅在集群内部暴露，以及应用 API 是否再次检查目标 Namespace。只增加一个菜单链接不能自动获得 Kubeflow 安全模型。

第三方应用若使用自己的数据库，还要实现数据租户键。Istio 只决定请求是否到达服务，不会自动为 SQL 查询追加 tenant_id。应用在读取全局表、导出数据或执行后台任务时都要保留租户上下文。跨租户管理员功能使用独立角色和审计，不与普通 Contributor 路径混用。

## 11. Profile CRD 把工作空间意图交给控制器收敛

官方 Profile 定义位于 kubeflow.org/v1。Profile 名称同时成为 Namespace 名称，spec.owner 声明单一 Owner，plugins 允许扩展 Profile 功能，resourceQuotaSpec 可以选择性生成 ResourceQuota。Profile Controller 观察对象并创建或维护 Namespace 及其配套资源。

Profile 的价值是把多步人工操作变成声明式合同。管理员不必分别创建 Namespace、Owner RoleBinding、默认 ServiceAccount 绑定和 Istio 策略，再担心遗漏其中一步。控制器持续比较期望与实际，资源被误删时可以重建，Profile 状态则成为工作空间供应进度的聚合入口。

声明式不代表字段能够承载所有企业策略。LimitRange、细粒度 NetworkPolicy、Kueue LocalQueue、Pod 安全标签、对象存储凭据、成本标签和闲置回收通常需要插件、外部控制器或平台编排。平台可以让一个更高层 Workspace API 生成 Profile 和这些资源，但要保留 Profile 原生状态以便排障。

## 12. 一个 Profile 只有一个 Owner，但 Owner 不是普通编辑者

官方 Profiles 文档说明每个 Profile 由单一用户拥有。Owner 获得名为 namespaceAdmin 的 RoleBinding，引用 ClusterRole/kubeflow-admin。Owner 还可以通过 Dashboard 管理 Contributor。权限上，Owner 不仅能使用工作空间，还能改变谁可以进入工作空间，因此它承担局部授权管理员责任。

企业团队往往不希望个人离职导致空间无人管理，也不希望普通用户自行扩大访问范围。可采用平台托管身份作为 Owner，再把团队成员赋予 edit 或 view；也可以让团队负责人做 Owner，但通过审批、审计和定期复核约束 Contributor 变更。选择取决于组织授权模型，而不是技术默认值。

Owner 身份必须是身份提供者传入的规范值。邮件大小写、别名、租户后缀和 Subject 迁移都可能造成匹配失败。平台应选用稳定 Subject 或建立明确映射，不在多个组件里分别猜测字符串。身份变更需要可审计的 Profile 迁移流程。

## 13. Contributor 的 edit 与 view 必须同时落到 RBAC 和入口授权

Profile 可以拥有多个 Contributor。当前官方文档描述 edit 拥有读写能力，view 拥有读取能力；Dashboard 中的管理界面只支持添加 edit Contributor，view 通常需管理员以手工或平台 API 方式创建相应资源。产品界面必须如实反映这一差异，不能显示一个无法兑现的只读邀请按钮。

Contributor 并不是 Profile Spec 中的简单长期数组后就结束。官方说明 Contributor 由 Kubeflow Access Management API 管理，并体现为 Namespace 中的 RoleBinding 与 AuthorizationPolicy。RoleBinding 决定 Kubernetes API 动作，AuthorizationPolicy 决定经过 Istio 的 Web 访问；缺少任一项都会造成半通状态。

半通状态的表现很有迷惑性。只有 RoleBinding 时，用户可能通过 kubectl 访问资源，却打不开 Web 页面；只有 AuthorizationPolicy 时，页面路由可能通过，后端 API 操作仍被 Kubernetes 拒绝。健康检查必须逐一验证两类对象和实际动作，而不是只看 Contributor 出现在页面字段中。

## 14. Profile 供应完成要以一组资源合同验收

当前官方文档列出的 Profile 资源包括同名 Namespace、Owner 与 Contributor 的 RoleBinding、default-editor 与 default-viewer ServiceAccount 绑定，以及 Owner 和 Contributor 对应的 Istio AuthorizationPolicy。平台可在此基础上增加 ResourceQuota、LimitRange、NetworkPolicy、LocalQueue、Pod 安全标签和成本标签。

供应状态不能在 Namespace 创建后立即标记 Ready。合理的 Ready 条件至少要求 RBAC、入口授权、默认工作负载身份、配额与基础网络策略存在，必要的 Secret 已经通过外部控制器就绪，且策略通过一次服务器端校验。对象存在但引用的 ClusterRole、ServiceAccount 或 Gateway Principal 不存在，也不应通过验收。

控制器需要幂等。重复事件不应生成第二套 RoleBinding；Contributor 删除应只撤销对应授权，不影响其他成员；暂时 API 失败应保留重试状态而不是宣布成功。生产状态记录 observedGeneration 和 Condition Reason，方便区分“期望已更新”和“控制器已落实”。

## 15. Profile 名称与已有 Namespace 碰撞不是可忽略告警

官方 Profile 示例警告，如果同名 Namespace 已经存在，可能出现非预期行为。原因是现有 Namespace 可能包含不受 Profile 控制的资源、标签、RoleBinding 和数据，控制器再写入一组假定全新的策略，会把两个不同生命周期拼接在一起。

平台 Admission 应在 Profile 创建前检查名称保留、Namespace 是否存在、是否带有受管标签以及是否已绑定其他项目。若要接管已有 Namespace，需要单独的导入流程：盘点资源、验证 Owner、补齐策略、建立备份，并在状态中记录 adopted 而不是 created。

名称还要防止与系统 Namespace、公共服务、历史已删除空间和外部存储前缀冲突。一个 Profile 删除后立即复用同名名称，会让旧对象存储、审计和缓存与新租户混淆。企业平台通常给工作空间分配不可变内部 ID，Namespace 名称只是可读投影。

## 16. 自动 Profile 注册便利，却会改变授权治理

官方 Dashboard 通过 CD_REGISTRATION_FLOW 控制首次登录时是否允许用户自动创建 Profile，默认关闭。开启后，没有 Profile Owner 身份的新用户会被引导创建自己的 Profile，并成为 Owner。这适合教学或开放实验环境，但在企业中等于允许用户获得局部授权管理能力。

自动注册还会制造无限 Namespace、PVC、Secret 和控制器对象的风险。即使 ResourceQuota 限制单个 Namespace，用户仍可能通过多个身份或重复空间扩大总量。企业入口应先完成身份组、项目、成本中心、数据等级和审批判断，再调用工作空间供应流程。

若确实开放自助创建，应设置每主体空间数量、命名规则、默认配额、过期时间和 Owner 复核；将 Profile 创建事件写入审计与成本系统。关闭自动注册时，页面需要给出申请路径，而不是只显示无权限错误。

## 17. 团队、项目与 Profile 的映射需要先于 YAML 确定

一个 Profile 可以对应个人沙箱、团队空间、项目环境或数据安全域。不同映射会改变 Owner、Contributor、配额和生命周期。个人沙箱适合短期探索，默认小配额并自动过期；团队空间需要稳定 Owner 和共享 PVC；生产项目可能禁止交互 Notebook，只允许流水线和服务发布。

不要把组织结构直接复制成 Namespace 层级。Kubernetes Namespace 没有嵌套关系，部门、项目、环境和地区若全部编码到名称中，会造成授权和配额难以变更。平台应使用标签与外部目录保存多维归属，Profile 名称保持稳定、唯一和可审计。

同一用户可以属于多个 Profile，活动 Profile 决定当前页面上下文。权限汇总不应把多个空间合并成全局角色。用户在 team-alpha 是 edit，在 team-beta 是 view，两份 RoleBinding 分别生效；任何全局缓存都必须保留 Namespace 维度。

## 18. 删除 Profile 会删除同名 Namespace，必须视为高风险操作

官方 Profiles 文档明确警告，删除 Profile 也会删除对应 Namespace，Namespace 中的资源随之进入删除流程。Notebook、Job、Secret、ConfigMap 和部分 PVC 会被级联处理，外部对象存储与数据库记录却未必一起删除，最终可能同时出现数据丢失与外部残留。

生产平台不应把删除按钮当作普通元数据操作。流程至少包括停止新提交、盘点运行工作负载、导出需要保留的流水线和元数据、确认 PVC 回收策略、冻结对象存储前缀、撤销入口、获得 Owner 批准，再删除 Profile。删除后还要检查 Finalizer、Namespace Terminating 原因和外部制品清理。

更安全的产品状态是 Active、Suspended、Retiring 与 Deleted。Suspended 先停止准入并保留数据；Retiring 执行保留期与迁移；只有证据齐全后才删除。紧急安全事件可以先撤销身份和网络访问，不必立刻销毁数据。

## 19. Kubernetes RBAC 解决 API 动作，不解决 Pod 网络与业务数据

RBAC 回答某个 User、Group 或 ServiceAccount 能否对 API 资源执行 get、list、create、update、delete 等动作。Profile 通过 RoleBinding 把 kubeflow-admin、kubeflow-edit 或 kubeflow-view 这类 ClusterRole 限制在目标 Namespace 生效。它不会阻止 Pod 之间直接建立 TCP 连接，也不会自动过滤对象存储中的数据。

这一区分解释了为何 kubectl auth can-i 通过不能证明完整租户隔离。它只验证授权器对一个 API 动作的判断。网络需要 NetworkPolicy 或 Service Mesh，存储需要凭据和路径策略，镜像与节点需要供应链和运行时控制，业务 API 还需自己的 tenant 检查。

RBAC 规则也要审计聚合。Kubeflow 的 ClusterRole 可能通过聚合标签或版本升级增加资源权限；企业自定义 ClusterRole 若允许创建 RoleBinding、读取 Secret 或使用 Pod exec，实际能力远大于菜单名称。升级回归应比较有效规则，而不是只比较对象名称。

## 20. RoleBinding 引用 ClusterRole 时，权限仍由 RoleBinding 的 Namespace 限定

Kubernetes 官方 RBAC 文档说明，RoleBinding 可以引用同 Namespace 的 Role，也可以引用 ClusterRole；后者仍只在 RoleBinding 所在 Namespace 授予对 Namespaced 资源的权限。Profile 正是复用全局定义的 kubeflow-edit 和 kubeflow-view，再在每个 Profile Namespace 创建绑定。

如果误用 ClusterRoleBinding，权限范围可能扩大到所有 Namespace。一个为了修复页面 403 而创建的全局绑定，会绕开 Profile 模型，使 Contributor 读取其他团队资源。所有自动化都应禁止普通工作空间流程创建 ClusterRoleBinding，并对现存全局绑定进行持续扫描。

Cluster-scoped 资源还需要特别处理。Node、PersistentVolume、StorageClass、ClusterQueue 和 CRD 不受 Namespace RoleBinding 天然隔离。用户若确需读取其中一部分，平台应提供经过筛选的 API 或精确 ClusterRole，而不是授予通用集群读取权限。

## 21. User 主体字符串区分大小写，身份规范化必须只有一个权威位置

官方 Profile Contributor 示例强调原始邮件主体区分大小写，而生成对象名称会把特殊字符替换并转小写。对象名规范化与 RBAC Subject 不是同一件事。把 Alice@example.invalid 写进 RoleBinding，却由入口传入 alice@example.invalid，会得到名称看似正确、实际主体不匹配的授权失败。

平台应在身份接入层选定规范 Subject，并在 Profile、审计和组件配置中一致使用。显示名、邮件、OIDC sub 和企业员工 ID 可以分别保存，但授权主键只能有一个。不要让每个 Web App 自行 lowercase，因为这会产生无法追踪的隐式映射。

身份提供者迁移时，先建立旧 Subject 到新 Subject 的映射，批量创建新绑定，验证后再撤销旧绑定。对同一邮箱在不同 Identity Provider 租户中的冲突要保留 Issuer 维度。只用邮件作为全局身份，在并购或多域环境中风险很高。

## 22. default-editor 和 default-viewer 是工作负载身份，不等于人类 Contributor

## 写在最后

工作空间与身份边界清楚之后，训练本身需要一个产品化的运行时接口。下一篇：[Kubeflow Trainer V2 与训练运行时产品化](/source/AI-Infra/4-AI平台工程/19-KubeflowTrainerV2与训练运行时产品化)。