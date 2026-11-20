# 平台基础设施即代码：Terraform、Crossplane 与环境一致性

24 用 Argo CD 管集群内对象，30 用 Cluster API 管集群生命周期；本文补它们之下的一层：VPC/子网、GPU 节点池、对象存储桶、IAM 角色、配额与 DNS 这些**云资源**如何声明式创建、持续保持一致。平台的环境一致性事故大多出在这层——staging 与 prod 的节点池机型不同、IAM 策略手工改过、存储桶生命周期规则只在一个环境存在。

## 1. 两层声明式：云资源与集群内对象

| 层 | 对象 | 工具 | 一致性机制 |
|---|---|---|---|
| 云资源 | VPC、节点池、桶、IAM、配额、KMS | Terraform / Crossplane / Pulumi | state 对账或控制器 reconcile |
| 集群内 | Deployment、CRD 实例、策略、队列 | Argo CD / Flux（24） | Git 期望态持续同步 |

分层原则：云资源层输出「集群与周边设施的连接信息」（kubeconfig、桶名、角色 ARN），集群内层消费这些输出。两层都进 Git、都走评审，禁止控制台手工改——手工改是 drift 的头号来源。

## 2. Terraform：state 与 plan/apply 模型

- 核心是 **state 文件**：记录「上次 apply 后的资源快照」，plan 用它与代码、真实云状态三方对比得出 diff。state 必须远程存储（对象存储 + 版本化）并加锁（DynamoDB/原生 lock），并发 apply 不加锁会互相覆盖。
- state 含敏感输出（连接串、密钥引用），按 37 的口径加密与限权；state 丢失等于失去对账基准，只能 import 重建。
- **drift 检测是周期性的**：plan/refresh 或托管平台的 drift detection 定时跑，两次检查之间的手工改动不可见。发现 drift 后两条路：代码收敛（改回期望态）或代码追认（把合理变更写回代码），不允许长期挂账。
- 环境一致性靠「同一 module + 不同变量」：dev/staging/prod 用同一套模块，差异只允许出现在显式变量（机型、副本数、配额），目录结构强制同构；workspace 或目录分环境各有取舍，关键是 state 隔离与晋级路径（dev 验证过的 module 版本原样进 prod）。

## 3. Crossplane：把云资源变成 Kubernetes API

- 模型三件套：Managed Resource（MR，一对一映射云资源）、Composition（把一组 MR 打包成模板）、CompositeResourceDefinition（XRD，定义平台自己的 API，如 `XGpuCluster`）。用户提交一个 claim，控制器展开成整组云资源。
- 与 Terraform 的本质差异：**控制器持续 reconcile**——每隔固定周期把真实状态拉回期望态，drift 自动修复而非只告警；删除保护、依赖顺序由控制器管理，不需要人肉 apply 顺序。
- 与平台天然集成：claim 是 K8s 资源，直接复用 RBAC（28）、GitOps（24）、配额与审计；连接信息写入 connection secret，与 37 的 ESO/CSI 链路打通。30 的自助门户「申请一个训练环境」按钮，背后就是一个 claim。
- 代价：provider 覆盖与成熟度参差（部分云资源字段滞后或行为与 CLI 不一致）、调试要读控制器事件链、团队需要 K8s 控制器心智。

![两层声明式对账：plan/apply 周期检查 vs 控制器持续 reconcile](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y4_l38_01.png)

## 4. 选型判据与混合模式

| 维度 | Terraform | Crossplane |
|---|---|---|
| 执行模型 | CLI/CI 触发 plan-apply | 控制器持续 reconcile |
| drift | 周期检测、人工决策 | 持续检测、自动修复 |
| 状态 | 独立 state 文件（需锁与加密） | etcd 中的资源状态 |
| 生态 | provider 最全、模块市场成熟 | provider 追赶中、Composition 复用 |
| 自助化 | 需额外包一层 API/门户 | claim 即自助 API |

2026 常见混合：**Terraform 做 bootstrap**（一次性创建集群、网络、IAM 骨架，变更频率低、provider 要求全），**Crossplane 做 day-2**（节点池扩缩、桶与配额等高频自助资源，持续 reconcile 价值大）。判据不是「谁更先进」，而是变更频率与自助化需求：低频基础设施用 Terraform 足够，高频租户自助用 Crossplane 收益明显。Pulumi 用通用语言写 IaC，适合已有强代码工程文化的团队，模型与 Terraform 同属 state 派。

## 5. 环境一致性与验收

- 变更纪律：一切变更走 PR + plan diff 评审（diff 里出现 destroy 要双人确认）；prod 的 apply 由 CI 执行而非本机，凭证用短期 OIDC 联邦（37），不落长期 AK。
- 删除保护：关键资源（prod 集群、数据桶）开 prevent_destroy / deletionPolicy 保护；destroy 演练只在隔离环境做。
- 一致性回归：周期性对 dev/staging/prod 跑「结构 diff」（同 module 版本、变量白名单内差异），drift 告警接 26 可观测性通道。
- 验收清单：state 远程 + 锁 + 加密；手工变更 drift 检出并闭环；环境重建演练（从代码完整拉起一套 staging）通过；prod apply 全部来自 CI 且有 plan 评审记录；destroy 保护覆盖关键资源清单。

## 写在最后

主题四至此把平台从资源底座、调度配额、工作负载 API、交付供应链、运营面一直补到秘密与基础设施的声明式治理。下一个主题转向这些平台所依赖的数据与后训练体系：[数据工程与后训练](/source/AI-Infra/5-数据工程与后训练/README)。