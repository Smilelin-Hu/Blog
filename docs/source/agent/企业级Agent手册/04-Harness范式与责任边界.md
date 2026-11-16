# Harness 范式与责任边界：四类构建入口怎么选

构建 Agent 的主要工作，是为模型建立与任务结构、风险等级相匹配的 Harness，但这不意味着从零实现模型之外的全部系统。本文提炼四种主流构建起点的责任划分——**它们的差异不是模型能力或成熟度高低，而是 Harness 通用行为由谁实现、Runtime 与 Sandbox 由谁提供、企业还要补齐哪些控制与验收责任**。四类入口不互斥：同一企业可以用高代码框架建深度定制的核心 Agent，用 SDK 把产品化 Harness 嵌入现有应用，再由统一 Agent Platform 纳管运营。

## 1. Harness 的定义与五层责任

Harness：**模型之外、围绕 Agent Loop 组织上下文、能力、状态、环境与控制机制，把模型判断转化为可执行、可恢复、可验证任务过程的代码、配置和执行逻辑**。三个「不是」：不是更长的 System Prompt（还含状态机、工具注册、权限检查、错误恢复、完成验证等确定性逻辑）；不是某种 Framework 的同义词（框架/CLI/托管服务都是实现载体）；不是 Runtime 或 Sandbox（三者协同但责任不同）。

| 层次 | 核心问题 | 主要责任 |
|---|---|---|
| Model | 能理解和推理到什么程度 | 语义理解、规划判断、生成与工具选择 |
| Harness 编排 | Agent 如何工作 | Loop、Context、State、Plan、Tool、Skill、Subagent、Permission、Verification |
| Runtime | 如何持续运行 | 进程承载、调度、并发、等待与故障恢复 |
| Sandbox / Environment | 在哪行动、影响多大 | 文件、进程、网络、Secret、资源隔离 |
| Agent Platform | 如何规模化交付治理 | 多租户、发布、网关、配额、观测、评估、运营 |

逻辑边界不必对应五个独立产品（一个 SDK 可同时含 Harness 与本地 Runtime），但架构设计中必须保留，否则无法判断故障归属、数据位置、迁移成本与最终责任。模型调用没有可靠跨轮状态、窗口装不下长任务全部事实、工具调用只表达意图不等于获得授权、模型声称完成不能证明测试通过订单提交——**Harness 的本质是把概率性判断嵌入确定性系统边界**。

开发者视角的八个构建对象：Agent Contract（为谁工作、允许禁止什么、成功标准）、Execution（Loop/状态机/预算/Verifier）、Context & State、Capability（Tool/MCP/Skill/Subagent）、Environment、Control（身份/审批/短时凭证）、Interaction（事件/Streaming/恢复游标）、Quality（Trace/Outcome/评估基线）。最小 Agent 可只实现一部分，进生产后每项都必须有明确责任人。**构建不从选框架开始，而从固定任务契约开始**：同一个「修复高危漏洞」目标，可以只出分析报告、可以在隔离环境改代码跑测试、也可以创建合并请求——除非契约明确授予发布权限并规定审批条件，都不应把「修复完成」解释为「已发布生产」。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-04-01.svg" width="90%" alt="第 03 章1.svg" />

## 2. 入口一：高代码框架自主构建（AgentScope / LangChain 类）

框架提供模型、消息、工具、状态、编排的代码级抽象，核心价值是**任务语义控制**：每轮 Context 怎么组成、哪些错误可重试、计划何时生成、何时审批、什么证据算完成，全部由企业决定。代价是框架只给构建材料，不自动补齐多租户隔离、状态恢复、Sandbox、安全策略、评估基线与业务验收。

以 AgentScope Java 为例，最小 Harness 先定三件事：用什么模型、在哪个 Workspace 工作、调用属于哪个用户和 Session（`HarnessAgent.builder().model(...).workspace(...)` + `RuntimeContext.userId/sessionId`）。之后**从任务成功标准反推能力，而非一次性打开所有开关**：漏洞修复需要读代码/生成补丁/跑测试/安全扫描 → 计划未确认不能改代码就加 Plan Mode 与 Permission → 分析评审可并行就加 Subagent → 跨调用任务就加外置状态与可恢复 Workspace（Compaction、ToolResultEviction、Docker/E2B Sandbox 按需叠加）。

真正的构建工作在能力之间的契约：指令层级与 Token 预算、Session/Task 边界与写入规则、谁批准计划、能力版本与输出契约、文件网络 Secret 隔离范围、ALLOW/DENY/ASK 策略、完成证据与回归标准。原则：**稳定确定性步骤沉淀为 Tool/脚本/策略，需要理解权衡的留在 Agent Loop，影响外部世界的动作统一过权限与 Sandbox**——这样 Harness 才有可测试边界，而不是 Prompt 驱动的隐式行为。走向分布式服务时，在线实例不能依赖进程内消息历史恢复：Session/Task/Plan/Artifact 映射到共享状态接口、同任务设执行租约、Worker 失效从安全点恢复、按租户建 Sandbox、短时身份访问企业工具。适合任务逻辑独特、数据环境不能托管、需要改 Loop/Context 策略的场景，要求团队具备分布式、安全与评估能力。

## 3. 入口二：复用产品化 Harness（CLI / SDK / 工作区助手）

Coding Agent 已形成可复用工作模式：检查工作区 → 制定计划 → 调工具 → 维护 Session → 请求权限 → 生成 Artifact → 接受运行中干预，同样适用于围绕文件、工具与可验证环境的企业任务（数据分析、日志定位、报告生成）。三种形态区别不在模型能力，而在 **Harness 由谁发起、状态由谁保存、事件由谁消费**：CLI 适合开发者直接操作工作区；SDK 把同一 Harness 嵌入既有应用（SDK 是应用侧接口负责提交目标/消费事件/处理权限请求，配套 CLI Runtime 负责规划执行，SDK 包通常自带兼容 Runtime）；工作区助手（OpenClaw/QwenPaw/Hermes 类）强调跨 Channel 连续使用与个人化状态，以 Agent Workspace 为持续边界承载配置/Memory/Skill/历史。

SDK 嵌入的关键工程点（以漏洞修复服务为例）：`tools` 限定可用工具集合、`allowedTools` 只预授权读取检索类，写操作经 `canUseTool` 回调交宿主应用审批（拒绝/取消/超时必须终止操作，审批界面展示真实操作与输入）；「不要发布」不能只写在 Prompt 里——cwd 指向受控 Workspace、不注入生产发布凭据、用身份与网络策略阻断发布通路；`result` 只是运行结果，业务 Outcome 要依据变更文件、测试、安全扫描与业务状态另行验收。扩展优先用现成扩展点（MCP/Skill/Plugin/Subagent/Hooks/Memory/外部 Session Store），不在外围 Prompt 里模拟相同机制；现成行为与成功标准不匹配时才考虑转框架路径。

两个易踩的坑：**外部 Session Store 只镜像 Transcript，不等于企业任务存储**（不含认证状态、文件 Checkpoint、保留策略，Task State/Artifact/Sandbox Snapshot/凭证/Outcome 仍要分别管理），且须保证租户键隔离、追加顺序、幂等写入与并发控制；Worker 失效后先确认原行动与工作区状态再决定 Resume/Retry/转人工，**不能因为 Session 可读就重放最后一次工具调用**。工作区助手同理：功能可用 ≠ 生产责任已满足（如 QwenPaw 官方明确后台 Subagent 不可恢复、Sandbox 未启用约束时不自动隔离、Hub 共享部署不构成强多租户边界），企业接入仍要外围补身份、租户、Task、审批与 Outcome 控制。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-04-02.svg" width="90%" alt="第 03 章2.svg" />

## 4. 入口三：基于模型的托管 Agent（Managed Agents）

以 Qoder Cloud Agents / Claude Managed Agent 为代表，把通用 Harness 与运行基础进一步服务化：平台承担基础 Loop、Session 推进、工具运行与 Serverless 隔离环境，企业集成重点从「组织一次次执行」转向「定义目标、处理干预、验收成果」。四个核心对象：**Agent**（可复用定义：模型/System Prompt/工具/行为配置）、**Environment**（容器运行环境：依赖/资源/凭证）、**Session**（一次任务实例，绑定 Agent+Environment）、**Event**（输入与实时执行事件流）。构建五步：备身份 → 建 Environment → 定义 Agent → 绑定创建 Session → 接通事件通道再发消息。

事件集成的三条纪律：先确认 SSE 订阅建立再提交任务（新连接只收建连后的事件）；处理成功后保存事件 ID，断线用 Last-Event-ID 续接并按 ID 去重，遗漏走 List Events 分页补；提交超时先核对服务端状态再决定重试，避免重复执行。`session.status_idle` 只表示回合结束，**任务是否成功要按交付成果与验收标准判断**。企业仍负责：仓库与业务工具接入、身份权限映射、业务 Task 状态、审批验收流程，并保存业务 task_id 与云端 session_id 的映射使过程与结果可互溯。托管 Sandbox 提供执行隔离，但业务上是否允许一次读取/修改/发布仍由企业 Policy 决定——**托管越多，越要把工具、数据、权限和成功标准定义清楚，否则只是把不明确的行为转移到了云端**。适合长时异步、后端 API 集成、批量与计划任务。

## 5. 入口四：云产品预置能力快速构建

以阿里云 AgentCore 为代表，把模型、指令、知识、Memory、Tool、Skill、Credential、运行环境通过产品界面或 API 组合为 Agent。价值不只是少写初始化代码，而是 **Agent 从创建起就进入统一的资源、身份、版本和质量体系**。与 Managed Agents 的区别主要在控制面：后者侧重把已定义的 Agent 作为服务持续执行，云产品还承担创建、资源装配、版本管理与发布配置，二者可由同一产品提供，不能按自建/半托管/全托管排成成熟度阶梯。

构建仍从任务契约反推资源组合，而不是把所有可用模型知识工具都加进 Agent；六类对象（Agent 定义与版本 / Model+Knowledge+Memory / Tool+MCP+Skill / Credential+Identity / Runtime+Sandbox+Channel / Event+Trace+Evaluation）各配企业责任：数据范围与保留周期、能力契约与风险分级、最小权限与短时凭证、网络边界与超时恢复、评估集与准入阈值。这些对象分属不同架构层（Loop/Context 属 Agentic Core，Runtime/Sandbox 属执行基础，身份观测评估属控制面），**在一个产品界面完成配置不等于所有能力属于同一层**。平台侧「已发布」只说明定义可被调用，不等于业务任务完成；会修改外部系统的 Agent，审批、幂等、超时、补偿与人工接管条件必须落实为确定性机制。

## 6. Agent Platform：统一对象而非抹平实现

多团队多 Agent 之后，每个项目分别建模型接入/工具目录/凭证/Session/Sandbox/观测评估，会重复投入并形成孤岛。Agent Platform 面向多团队、多 Agent、多执行形态，以统一对象支持创建、接入、交付、运行、治理、协作、观测、优化：Agent 目录与版本、异构接入（框架 Workload / SDK Worker / 托管端点）、共享能力资源、Team 协作与任务组织、资源调度、身份策略治理、观测评估优化。**Harness 决定单个 Agent 如何工作，Platform 决定一组 Agent 如何被交付治理；平台汇聚执行证据，业务应用或授权 Verifier 做最终业务判断**。

统一的是公共对象（Definition/Task/Session/Event/Identity/State/Checkpoint/Artifact/Trace/Outcome）与身份、租户、版本、质量语义，不要求外部 Agent 改用同一种 Harness。多源纳管三个底线：版本与归属可追溯（不能只记名字不知模型/配置/环境版本）；Event/Artifact/Trace 关联 Task+Identity+Tenant（支撑跨系统审计与成本归因）；**远程 Agent 不能只返回自然语言结论，必须提供可验收的 Artifact、事件或环境事实**。调度上，长任务在推理/工具/审批/事件间反复等待，不应让等待任务长期占用完整计算资源——可恢复状态与执行实例解耦，按优先级、配额、数据位置、模型容量与预算排队。统一不等于单体：Registry/Runtime/Sandbox/Gateway 可由不同服务实现，关键是共享一致语义、提供可重复的交付路径。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-04-03.svg" width="90%" alt="第 03 章3.svg" />

## 写在最后

四类入口回答「从哪里起步、责任怎么分」，接下来三篇按任务、信息、行动三类工程契约展开构建内部原理，先看任务如何编排与长程推进：[任务编排与长程推进](/source/agent/企业级Agent手册/05-任务编排与长程推进)。