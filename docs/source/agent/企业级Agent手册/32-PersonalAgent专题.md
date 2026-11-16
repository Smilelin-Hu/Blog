# Personal Agent 专题：产品观察、AaaS 架构与 SuperAgent

2026 年 9 月，Personal Agent 产品几乎同时发布：Meta Muse 于 9 月 8 日、Manus 2.0 与 Cue 于 9 月 28 日、OpenAI dots 于 9 月 29 日，Grok Bot 则早在 8 月 11 日上线并于 9 月 28 日推出 Team Bots。本专题按源顺序整理三篇：产品技术与商业观察盘点十款产品的设计路线、技术挑战与商业判断；AgentScope 的 Agent as a Service 架构回答个人助手与企业智能体如何共用同一套服务底座；DeepSeek SuperAgent 解析与协同空间 Flock 实践展示「一个 Agent 同时做很多事」的工程收敛。贯穿的核心判断是：**Personal Agent 的新不在模型更会聊天，而在运行时变了——执行环境、身份、触发、审批与记忆被整合成围绕同一用户的长期产品；而长期运行的可靠性，最终要靠经典分布式工程的确定性外壳来兜底**。

## 1. 这轮新在哪里：四种形态与四个组成部分

新变化主要发生在产品组织方式上：部分厂商开始围绕一个具体用户，把长期运行环境（一台真正的电脑）、个人身份、触发条件、审批和记忆管理整合到同一个产品中。四种形态的分野在于主要组织单位：普通聊天助手以当前对话为中心，任务多由对话启动、后续是否继续仍由用户决定；Manus 1.0 更接近云端任务执行器，给一个明确目标就在独立环境调用浏览器、文件和代码工具交付结果，后续补充的 Sandbox、Cloud Computer、Project、Schedules 增加了隔离环境、常驻机器、项目知识和定时执行，但主线仍是完成一项任务；OpenClaw 是可自托管的个人 Agent 运行时，长期记忆、默认约 30 分钟一次的 heartbeat、落盘的 cron 与 Webhook 调度都有，运行环境、配置和安全责任也更多由用户自己承担；这一代 Personal Agent 则把这些能力做成面向普通用户的完整产品，配任务列表、审批页、记忆管理、计划安排和执行记录。从实现机制拆解大致四个部分：**运行内核**（底层模型加围绕它的 Harness，负责规划、记忆、调度和工具调用）；**独立执行环境**（一台属于自己的电脑，如独立 Linux 桌面，像人一样操作浏览器、管理多 Tab，实测页面过多导致卡顿时还要主动清理无用 Tab 再继续）；**工具与服务生态**（国外邮件、日历、财务软件接口较开放，国内能力集中在超级 App 和政务平台，汇聚了信息流、支付、借贷、政务服务但接口开放程度有限）；**数字身份**（从「操作软件」走向「代替个人办事」需要能被现实社会识别授权的账号、支付工具和通信号码——网络电话只能通话，真实手机号和支付账户意味着能注册服务、验证身份甚至完成交易）。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-01.jpg" width="90%" alt="Manus 2.0 发布的 Personal Agent：Cue" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-02.jpg" width="90%" alt="Personal Agent 的四个组成部分：运行内核、独立执行环境、工具与服务生态、数字身份" />

## 2. 路线一：给 Agent 独立邮箱、电话和支付（Cue 与 Fo）

Cue 在这条路线上走得较远：Manus 2.0 随附的独立应用，为每位 Agent 配邮箱、电话、钱包和电脑，可收发邮件消息、在用户控制的权限下支付、在用户离开后继续工作。官方示例里多个 Agent 在群聊中调查纽约发布会场地、筛选候选并制作演示稿；线下扫商家二维码还能创建对应 Agent 用于预订、代点餐或排队；连接器展示 Trip.com、Oura、Gmail、MyFitnessPal 等，早期访问免费需邀请码。但具体反馈几乎都指向落地摩擦而非任务成功率：电话并不完全免费，有用户装上后发现已是 9.9 美元/月，先免费一个月之后起价约 20 美元；电话能力被形容为「后挂上去的」，部分热门国家收不到短信，号码国家跟当前代理 IP 绑定，想换区要先换 VPN；沙箱重启容器会换「住宅」IP，有人连试三次得到巴基斯坦、埃及、越南，几乎看不到主要西方国家；产品形态上基本是把原先 Manus Agent 面板里的能力拆成独立 App。Fo 来自 Wajo（8 月 25 日发布、9 月 28 日对公众开放），创始人 Shivani Poddar 有 CMU、Meta、Google DeepMind 与 Google Labs 背景，但 Fo 并非 Google 产品。定位是「把事做完」的行动 Agent：自有电话、邮箱、语音和一次性支付卡（商家和 Fo 都看不到用户真卡），免费 Fo Mini 有每日任务上限、邀请制无限 OG、按需报价的 Pro。最有代表性的设计是**人机之间的正式交接**：自动化遇到瓶颈时任务转给训练过的人类执行助理，处理机器无法完成的现实环节再把结果带回流程——Fo 可以雇佣人类作为外包辅助完成任务（主要指电话），并在过程中学习人类。官网称内部 104 项真实杂务完成率约 71%、信任率 94%。使用案例：预约医生对方不接，Fo 循环重拨留言第三次打通；延误包裹从邮箱找运单号、联系商家、抄送用户改 FedEx 隔夜；Costco 拦截时比价确认最便宜、建购物车付款再交还用户。槽点：保险报价一问一答、iMessage 收敏感信息缺保险库确认。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-03.png" width="90%" alt="Cue 的扫码创建商家 Agent、跨设备工作空间与多 Agent 协作示意（1/3）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-04.png" width="90%" alt="Cue 的扫码创建商家 Agent、跨设备工作空间与多 Agent 协作示意（2/3）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-05.png" width="90%" alt="Cue 的扫码创建商家 Agent、跨设备工作空间与多 Agent 协作示意（3/3）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-06.jpg" width="90%" alt="Fo 通过电话功能和商家沟通并且预订座位。并且可以寻求真人协助完成工作(上图 3)。（1/3）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-07.jpg" width="90%" alt="Fo 通过电话功能和商家沟通并且预订座位。并且可以寻求真人协助完成工作(上图 3)。（2/3）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-08.jpg" width="90%" alt="Fo 通过电话功能和商家沟通并且预订座位。并且可以寻求真人协助完成工作(上图 3)。（3/3）" />

## 3. 路线二：接入现有应用生态（dots、Muse、Spark、Today.ai）

dots 于 DevDay（9 月 29 日）发布，GPT-6 Astra 驱动，插件生态覆盖 4000+ 应用，首发一个主 dot、specialist dots 企业试点。上下文三分：当前任务上下文、ChatGPT 记忆、dot 自己的持久上下文（非逐字副本）；用户隔离的 Linux-Chrome 云工作区；密码走安全登录流程进浏览器、不进模型上下文；独立 Auto-review 检查外部动作授权；工程场景持续整理反馈、做测试过的修复 PR 并附视频。笔者电话指挥时有很「人」的感觉，案例是发票 PDF 批准后发出。反馈分化明显：上手快、个性可调、iOS 消息式界面受好评；但主动性几乎只是定时任务、缺常识，Codex 连接不稳空转烧 token，语音比 GPT Live 差，不能改自己的 AGENTS.md，Windows 本机 computer use 不可用。Muse（9 月 8 日）为每用户提供持续云端计算机，入口覆盖 iOS、Android、muse.ai、WhatsApp，关 App 继续工作，主对话可并行打断并开 side chats，有命名形象和 artifacts；支付走 Stripe Link，总额由人确认、Agent 不见真实支付信息，另有一次性虚拟卡；未来扩展 AI 眼镜、Muse for Mac、独立邮箱；小企业连接 Asana、Canva、Notion、QuickBooks、Shopify、Slack、Stripe（勿与模型家族 Muse Spark 混淆）。技术重点是 **Secure VM**：每用户独立 Linux VM，Agent 跑在 systemd-nspawn 容器内，即使拿到容器管理员权限也不能控制宿主机；凭证审批安全服务放在容器外，authd 管理凭证、模型只接触替代令牌；Sentinel 在网络请求时检查连接器操作，获批后才在网络边界使用真实凭证；eBPF 做流量控制与数据污染追踪；浏览器是独立 broker 进程；子 Agent 经 accessibility tree 读界面，减少任意 JS 执行。案例：NYT 记者两周使用后称「最有用的 AI 应用」，打电话报会员号答安全问题、导入消费记录标出两个重复订阅并取消、要回 44.99 美元退款。反面同样刺眼：默认对话用于训练、记忆无关闭开关，拒绝 Messages 权限仍被同步 18.7 万条 iMessage，Amazon 屏蔽代购，内测暴露 iCloud 照片，深推理出错；毛绒形象亲和力、回消息点赞等设计让它在一项排名中列第二。Gemini Spark（5 月 19 日 I/O）在 Gemini 内配 Antigravity harness，借 Google 账户授权、Google Cloud 专用 VM，时间、Gmail 条件、主题事件三类调度，最多 50 个活动计划、15 并发；6 月接 Mac、Keep、Tasks 与自定义 MCP，7 月接 Chrome 登录态与已存密码（160 多国），9 月接 Photos；背后是 DeepMind AI Control Roadmap 的异步监控（百万量级任务）；限 18 岁以上，官方自称实验早期，提示注入、误操作、泄露风险仍在。Today.ai 是国内最先发布的，记忆管理进 UI（人物、项目、偏好可查看编辑删除），早间简报晚间收尾，对外动作需确认，主动链接推送；争议在于要大量权限、登录后扫描本地磁盘，个性化代价是大量用户数据遭海外批评，且所谓云电脑其实只是沙箱。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-09.jpg" width="90%" alt="dots 的任务协作界面与动作审核架构（1/2）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-10.png" width="90%" alt="dots 的任务协作界面与动作审核架构（2/2）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-11.jpg" width="90%" alt="Muse Secure VM 官方架构图（隔离运行容器、凭证存储、Sentinel 及外部服务）与购物审批界面（购买前审阅金额）（1/4）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-12.png" width="90%" alt="Muse Secure VM 官方架构图（隔离运行容器、凭证存储、Sentinel 及外部服务）与购物审批界面（购买前审阅金额）（2/4）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-13.jpg" width="90%" alt="Muse Secure VM 官方架构图（隔离运行容器、凭证存储、Sentinel 及外部服务）与购物审批界面（购买前审阅金额）（3/4）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-14.png" width="90%" alt="Muse Secure VM 官方架构图（隔离运行容器、凭证存储、Sentinel 及外部服务）与购物审批界面（购买前审阅金额）（4/4）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-15.jpg" width="90%" alt="Muse 的毛绒形象" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-16.jpg" width="90%" alt="Gemini Spark 的任务执行过程与桌面/移动端任务界面（1/2）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-17.png" width="90%" alt="Gemini Spark 的任务执行过程与桌面/移动端任务界面（2/2）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-18.jpg" width="90%" alt="Today.ai 使用界面 from 归藏" />

## 4. 路线三：多 Agent 协作与自托管（Grok Bot、Manus、OpenClaw）

Grok Bot Group 让一组 Bot 共享一台云电脑，跨应用传递上下文、群聊分工，覆盖五平台；Bot 名单显示谁做什么、哪里需要人判断；skill 管「如何做」、routine 管「何时做」，每 Bot 最多 50 个；Teach a task 录制最长 10 分钟的可见操作生成 skill 草稿。官方案例：工程两层分工，外层按 iOS、桌面、Android、基础设施分 Bot，内层调度 Cursor 云端 Agent，读任务记录、截图、PR 证据，异常追问或中断；采购案排查 125 家供应商、找出 43 个连续 90 天未使用的付费席位，订单从 14629 降到 6143 美元；9 月 28 日的 Team Bots 共享文件、工具、技能和团队知识，保留私有对话。要注意**多个 Bot 不等于多个安全区域**：同一用户的 Bot 共用文件、浏览器 session 和应用登录，Bot 之间没有安全隔离，删除一个 Bot 也未必清理共享电脑中的文件与会话。体验亮点：无预设引导，对话确定身份人设；权限按用户级共享，授权一次 Slack、GitHub、Gmail 所有 Bot 可用；灵活创建加群组；Skills 和提示词动态生成无需人工配置；模型完成任务的一次准确率和速度都不错。笔者体验中 Grok Bot 完整度最高、确实能 24 小时工作（整理热点推文非常好，电脑配置高、价格也高），dots 的优势在与 CodeX 集成且 Pro 用户不限量。Manus 展示了通用任务 Agent 的演进：2025 年 3 月首发「给目标、云端执行、交付结果」；7 月公开上下文工程方法，Wide Research 把多对象工作分发给并行子 Agent（每个都是通用 Manus 实例）；2026 年 1 月任务 Sandbox 为每项任务提供隔离云 VM，空闲休眠、返回唤醒；4 月 Cloud Computer 是专用常驻机器，可跑 bot、脚本、服务和周期采集；5 月 Project 自更新从任务中提取可复用决定、格式和流程，经用户批准写回项目知识——不等同模型在线训练，也不表示无边界记录整个账户。OpenClaw 前身是 2025 年 11 月的 WhatsApp Relay「Clawd」，2026 年 1 月底更名（即年初爆火随后很快销声匿迹的龙虾）：长期运行的 Gateway 维持消息渠道连接，Web UI、CLI、客户端经 WebSocket 长连接接入，同一会话任务串行执行并限制全局并发；记忆分布在 USER.md、MEMORY.md 和按日期记录的笔记，SQLite 提供检索索引，后台 dreaming 流程把历史材料合并到更紧凑的长期层并保留审阅记录；heartbeat 周期唤醒、cron 保存计划、Webhook 接收外部事件。**开源可审计不等于默认安全**：当时文档明确沙箱默认关闭，Gateway 仍在主机上运行；命令审批必须绑定获批命令、目录和可执行文件，避免审批内容在执行时变化；9 月 21 日官方审计复盘指出权限要随请求传递、授权要指向最后实际访问的资源、用户撤销授权后已运行的任务也必须受到影响。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-19.jpg" width="90%" alt="Grok Bot 官方采购案例——核对续约报价与已有支出，整理约 125 家供应商" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-20.jpg" width="90%" alt="Grok Bot 官方工程案例（按专长分工的 Bot 名单）与客服案例（从仅调查、人审到有限自动执行的阶段图）（1/2）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-21.jpg" width="90%" alt="Grok Bot 官方工程案例（按专长分工的 Bot 名单）与客服案例（从仅调查、人审到有限自动执行的阶段图）（2/2）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-22.png" width="90%" alt="Grok Bot 新建 Bot 时的对话引导界面" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-23.png" width="90%" alt="Grok Bot 的多 Bot 协作界面" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-24.png" width="90%" alt="Manus 官方机制图（将文件系统作为外置上下文）与 Cloud Computer 发布图（专用常驻云机）（1/2）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-25.jpg" width="90%" alt="Manus 官方机制图（将文件系统作为外置上下文）与 Cloud Computer 发布图（专用常驻云机）（2/2）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-26.jpg" width="90%" alt="OpenClaw 2.0 官方 UI（Claw Patrol 会话入口）与命令审批 UI（展示嵌套命令并请求执行批准）（1/2）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-27.png" width="90%" alt="OpenClaw 2.0 官方 UI（Claw Patrol 会话入口）与命令审批 UI（展示嵌套命令并请求执行批准）（2/2）" />

## 5. 全天候 Agent 的技术挑战

Always-on 的定义是交代任务后即使结束对话，它仍记住任务、等待变化、在合适时候继续推进——「盯住这笔采购，供应商延期就找替代方案，换供应商前让我确认」，关键不是一次执行了两天，而是**跨越两天、多次执行和等待，始终接着处理同一项委托**。本质是运行时的变化：把需要长期保存的状态放到会话之外（任务账本、记忆、权限、凭证、触发条件、已对外发出的动作），邮箱电话钱包是给常驻进程一个可被外界找到的身份。由此三点要求：记忆能巩固压缩遗忘、身份跨模型跨主机延续、已发出的信和付出的钱可审计不能被悄悄撤回。**持久状态不等于 RAG**：记忆分情节（发生过什么）、语义（知道什么）、程序（会做什么）加工作记忆，源自 Tulving、Baddeley 与 Soar/ACT-R 的认知科学划分；LLM 记忆演化三阶段是先存轨迹、再反思轨迹、最后抽象成可复用经验，全天候需要的正是最后一步。**执行状态本身就是记忆**：FlowState 把带类型的状态节点、节点关系、对原始工具输出的引用分开存，循环运行只增量更新、推理时按需回看，同一模型上 MemoryArena 成功率和 τ3-Bench 通过率分别提升约 4.6 和 14 个百分点、token 消耗降约 40%，与 Manus Cascade 按需加载思路相近。**身份要跨运行时延续**：架构论文把连续性写成 Pt=(It,Mt,Bt)（身份、记忆、可执行的「身体」），与可替换的执行绑定分开，迁移流程为暂停、检查点、校验、绑定、再水合、恢复；配套 PAI-Bench 区分「能回忆出身份事实」和「行为上真按身份行事」，两者经常对不上。**触发器是控制环不是定时器**：事件先写入触发状态、满足条件才唤醒云电脑执行一次，更像分布式系统的订阅和事务；对外付款发信是已提交无法收回的副作用，必须和内部计划分开记账。长任务需要可恢复的任务状态机（哪些在计划、已执行、等待批准、可安全重试、需回滚或转交），邮件已发出、日历已创建时从头重跑会重复操作；dots 把停止拆成暂停主任务、停止子任务、取消未来计划三种，准确说明后台同时存在当前流程、并行分支和未来触发器；LangGraph Persistence/Interrupts 提供检查点与「暂停等批准、原位恢复」范式，Pare 区分用户界面操作与 Agent API 操作的不同操作面，π-Bench 关注长周期主动助理面对隐藏意图的表现。何时打扰用户：低风险汇总通知、高风险执行前暂停、不确定先调查、需判断给少量清晰选项；体验指标可记录用户为盯进度、纠错、重新提供上下文而回到任务的次数。权限方面，借用户登录态会让外部系统把动作记录成用户本人操作，需明确邮件由谁发起、支付由哪个 Agent 提交、用户在哪个节点批准；授权覆盖整个任务周期：凭证有期限、撤销影响运行中任务、角色变更或删除后文件会话授权有明确处置。记忆方面，错误偏好一旦进入长期层会在后续任务反复出现，用户需知道一条记忆从哪来、影响哪些任务、怎样更正删除；MemGPT（2023 年 10 月）把记忆读写设计为工具调用，Letta MemFS 用 Git 存可跨会话共享的记忆并 dreaming 合并，Mem0 提供外接记忆层，Zep/Graphiti 整理成带时间关系的知识图谱；Sleep-time Compute 说明空闲时预处理可复用上下文可把查询阶段计算降到约五分之一（不能外推为所有产品成本降 80%），LongMemEval 提醒分开评估写入是否正确、需要时能否找到、读出能否支持当前任务。越权与注入方面，任务开始时的一次确认无法覆盖后续目标变化、资源替换和新数据；MCP 是无状态的互操作协议，不替开发者决定谁能访问、授权多久、文件是否已变、返回数据是否受污染；Muse、dots、Spark 都没有宣称彻底解决提示注入，分层措施降低风险但不提供绝对免疫。失败处理与完成证明方面，要尽早识别失败、保留现场、说明未完成部分，选择重试、回滚、等待、询问或转人工；**验证完成不能只听 Agent 自述**，订单是否生成、邮件是否送达、PR 是否通过测试才是可靠的外部状态；GAIA、OSWorld、τ-bench、τ²-bench、LongMemEval 各覆盖部分能力，单项高分不能证明完整产品可靠。Wajo 构建模拟世界（可控商家网站、邮箱、电话、合成人物，含仿冒网站和暗黑模式）测试行动型 Agent，评分优先读外部系统状态和执行记录，模型评委只处理确定性检查无法裁决的部分且不能推翻硬性结果；其报告的 Fo 自主完成率约 71%、信任率约 94% 不含人类兜底，论文含 104 个完成任务、60 个信任任务、每配置跑 3 次，OpenClaw 在共同任务上完成率约 42%——但这是开发方预印本而非独立横评或同行评审，不能包装成市场份额或真实客户成功率，官网图中 Muse 与 Instinct 的位置也只是作者主观判断。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-28.jpg" width="90%" alt="全天候 Agent 的六个技术要点：持久状态、分层记忆、任务账本、事件触发、身份延续与重要动作授权" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-29.jpg" width="90%" alt="Pare 提出的事件驱动环境与用户/agent 不对称接口，及 π-Bench 长周期主动助理评测框架" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-30.jpg" width="90%" alt="Pare 提出的事件驱动环境与用户/agent 不对称接口，及 π-Bench 长周期主动助理评测框架" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-31.png" width="90%" alt="MemGPT 分层记忆与更新已保存信息的机制" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-32.jpg" width="90%" alt="LongMemEval 索引/检索/读取统一设计框架，及 Sleep-time Compute 把部分推理计算移到查询之前" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-33.jpg" width="90%" alt="LongMemEval 索引/检索/读取统一设计框架，及 Sleep-time Compute 把部分推理计算移到查询之前" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-34.jpg" width="90%" alt="Wajo 为行动型 Agent 构建的模拟世界概念图，及按任务类型比较自主完成率的厂商自测图（1/2）" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-35.png" width="90%" alt="Wajo 为行动型 Agent 构建的模拟世界概念图，及按任务类型比较自主完成率的厂商自测图（2/2）" />

## 6. 为什么集中在 2026 年，以及商业判断

笔者的判断：**Personal Agent 不是突然出现的新需求，而是一个反复被技术能力、执行成本和信任问题打断的旧目标，现在几条过去各自不够成熟的路线能组合成可用整体**。早期 Siri 依赖预设流程，大模型带来通用理解后 AutoGPT 尝试直接全自动，很快暴露长任务跑偏、错误累积、频繁接管；实际落地反而靠 Copilot、固定工作流、Coding Agent 和 Harness 先缩小任务边界。这段绕路积累了执行基础，但「完成一次任务」不等于「长期替你做事」：「整理供应商报价」是一次交付，「持续跟进到下周三、收到新报价就更新、作出采购承诺时再问我」才是持续委托。通用理解、工具执行、持续状态管理开始拼在一起，推理成本下降让持续服务有机会打正 ROI，产品从「你问一次我做一次」转向「你交代一个目标我持续跟进」——最终能否成立，要看省下的操心是否多于检查和纠错的负担。商业化上笔者判断**C 端走免费路线、B 端走数字员工**：C 端定位是「替你办事的人」而非付费订阅工具，先免费换规模和持续依赖，变现发生在决策和交易环节——佣金（交易闭环在 Agent 内完成，向商家收 CPS 分成，离交易越近、越懂偏好、转化越高）和广告（传统广告卖曝光，Agent 时代卖「被采纳的推荐」，按有效推荐转化计费，完整上下文让精准度显著高于搜索信息流）；前提是信任，一旦被感知为「偏向出价高的商家」依赖就会崩塌，商业化内容清晰标注、排序以用户利益为先、付费只影响「谁有资格进入候选」不影响「谁被选中」。B 端形态是数字员工：每个岗位每位员工拥有绑定角色、权限和知识的专属 Agent，在企业系统内实际执行数据查询、流程审批、报表生成、跨系统协同、异常处理；按数字员工订阅（像招聘一样按岗位按数量开通）、按任务量或成果计费、平台与生态（统一底座、技能市场、模型算力）三种变现；壁垒在对企业数据、业务流程、权限体系的深度理解和安全合规可审计的运行保障。泛化来看，B 端的运营、产品、研发人力对应一个个员工，Personal Agent 也可以按业务单元而非人和职能划分来支撑工作。对中国的判断是**生态内嵌加信任变现**：C 端很难出现「打通所有场景的胶水」——用户行为高度集中在少数超级 App，广告、搜索、会员、付费推广都建立在用户亲自停留浏览点击的前提上，Agent 通过 GUI 代替筛选决策会整体绕过付费触点、直接冲击平台收入模型，这是平台反感甚至封禁 GUI Agent 的根本原因（如招聘网站限制 GUI Agent 筛简历）；价值更应落在帮用户解决日常问题上，差异化来自独占数据和能力（小红书的内容不对外开放，它自己的 Agent 在旅游攻略等私域信息上就有难以替代的来源），每个生态都会长出自己的 Personal Agent。信任是 C 端变现关键：用户对豆包、千问类结果几乎直接采信，Agent 成为「外脑」后推荐转化率和交易达成率会远高于传统信息流搜索，但信任是脆弱资产，一旦察觉推荐为佣金服务会塌得很快（魏则西事件是前车之鉴），越是靠信任变现越要克制变现。B 端机会在从「单点嵌入」走向数字员工：获取企业完整上下文、通过账本等持久化机制承接任务、在执行中积累进化，企业人力供给因 Agent 获得指数级扩展。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-36.jpg" width="90%" alt="ReAct 的推理-行动-观察循环——现代 Agent 的学术起点" />

## 7. AgentScope AaaS：两种部署模式与服务职责

Personal Agent 需要用户离开电脑后继续整理资料、回来时由本地 Harness 接续同一项工作；企业智能体需要在远端组织调查、按数据和权限把工具调用交给云沙箱或企业内网执行端，并在工具等待、人工确认、节点切换后继续处理。共同要求是**身份、任务状态与长期积累独立于单个客户端、Harness 实例和执行环境**。Agent as a Service 是围绕任务交付的服务形态：调用方能提交工作、读进度、补要求、处理确认、稍后取结果；Managed Agent 进一步明确运行责任——平台承载约定范围内的 Harness、执行调度与状态管理，应用团队提供业务工具、授权与验收标准，平台可部署在企业自己的基础设施上。一个 Agent 至少涉及几个不同生命周期：Agent 定义长期复用、用户会话跨多个任务、推理实例只运行一段时间、沙箱按文件和进程需要保留或回收，拆开这些生命周期是平台的重要设计工作。构建入口四种可组合：高代码框架自主构建 Harness（AgentScope 提供模型、消息、工具、状态的代码抽象，定制深但要自行对接存储运行恢复）；复用产品化 Harness（成熟 Coding Agent 已组织好规划、文件操作、命令执行、上下文管理和权限交互，CLI 直接使用或 SDK 嵌入）；平台托管（配置模型、指令、工具、Skill、执行环境，API 提交任务消费事件）；云产品预置能力（界面装配资源并进入版本发布治理流程）。部署模式则是另一个维度，看 **Agent Loop 实际在哪里运行**：Agent IN Sandbox 把运行组件放进沙箱，接近本地工作区开发，直接使用环境里的文件依赖工具，依赖既有 CLI 和复杂工具链时容易起步，代价是升级、环境恢复、进程管理要一起考虑；Sandbox as Tool 让 Harness 运行在服务端，组织上下文、调模型、判断下一步，需要操作文件或执行代码时再调远程 Sandbox，为状态与执行环境建立独立边界、模型访问凭据留在沙箱外，代价是网络交互和远程故障处理。SDK 在沙箱外发起调用但启动的完整 Harness 在沙箱内，仍属前者。平台视角的差异：任务承载单元（完整环境 vs 推理与执行分别管理）、长期状态（从环境提取外置 vs 围绕独立任务记录）、资源调度（生命周期紧密 vs 按负载分别调度）、权限设计（划分运行组件与生成代码 vs 远程工具边界集中检查）、故障处理（进程与环境状态 vs 工具是否执行及结果交接）。基于 AgentScope 的服务链路六项职责：定义与资源管理、请求与事件接入（鉴权、受理、进度查询、事件订阅、补充输入、人工确认）、任务调度与执行控制（会话顺序、并发、预算、执行权与恢复调度）、Agent 运行（Harness 构建上下文调模型组织工具调用）、工具执行（沙箱、MCP、业务系统，记录稳定执行标识）、状态与工作区存储（会话日志、检查点、待办、工具记录、产物）。落地时每次执行经 RuntimeContext 传入授权的用户与会话身份，Session Log 接持久存储；模型产生工具调用后先查权限、记录执行意图，再由执行层调用，确认结果写回后继续下一步。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-37.png" width="90%" alt="Agent IN Sandbox 与 Sandbox as Tool 部署模式对比" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-38.png" width="90%" alt="AgentScope Agent as a Service 总体架构" />

## 8. 挂起恢复协议与四个服务化层次

任务状态与推理实例分开管理有四个要点：为会话和任务建稳定标识，执行节点退出后调度层先取得新执行权再读已提交状态恢复，不依赖原进程内上下文；推理资源与工具资源分别管理，等待阶段释放推理资源，回收沙箱前另行确认活动进程、未完成工具与工作区保存；授权落实到不同能力入口，模型访问、受控业务工具、任意代码执行各用所需身份凭据与网络策略（工单查询走获准业务工具，测试沙箱只获得跑测试的访问范围）；Agent 行为与执行环境版本分别管理，记录模型、指令、工具定义、Harness 配置和环境版本，明确变更对新任务与进行中任务的生效范围。长工具任务的挂起恢复六步：受理（身份资源授权检查，持久保存输入与标识，网络重试沿用同一请求标识）→ 启动推理（取得执行权、加载会话状态与工作区）→ 派发工具（查权限、保存调用参数和稳定执行标识）→ 保存等待（检查点加待等待工具集合，确认持久化后挂起并释放推理资源）→ 接收结果并恢复（核对等待条件、取得执行权、合并匹配结果）→ 提交交付（终态、回复、产物引用，浏览器断开不改变执行状态）。异步派发用持久投递记录或事务 Outbox，接收端按稳定标识去重；挂起与结果到达相遇时重新检查就绪条件，避免工具已完成而任务仍沉睡。两类状态重点处理：继续执行所需的状态（聊天历史无法区分工具尚未派发、正在运行、已返回但未进入下一次模型输入）和外部动作的确认状态（网络超时后创建工单可能已生效，保留为 unknown、按稳定执行标识查询原操作，幂等键贯穿调用与重试）。四个可组合的服务化层次：**远端托管 Harness**（客户端断开后任务仍由服务调度）；**本地与远端执行交接**（轮次边界或可恢复检查点交接，先确认原执行者退出或被撤销执行权，另一端再取得执行权加载状态）；**Context 与 Memory 云端状态服务**（Context 是当前任务的会话历史、压缩摘要、计划和参考材料，Memory 是跨会话的事实偏好经验，配稳定归属、版本和访问接口）；**Brain 与 Hands 分离**（统一工具协议把获准调用路由到本地设备、云沙箱或企业内网执行端，已派发工具仍按原执行标识查询结算，迁移活动执行另行完成停止确认、状态保存与恢复）。个人场景接通：多渠道身份映射到统一服务入口，手机上说「继续整理上周的调研并生成对比报告」，远端 Harness 读原任务进度，公开数据交云端 Hands、用户电脑文件路由到在线本地 Hands，回电脑后经检查点和执行权交接接回；后台工作经持久化调度器接入同一链路。企业场景接通：告警、文档上传、需求更新、工单超时等事件经适配器去重、业务关联、确定执行身份与数据范围后建任务，保存业务对象、输入版本与标识对应；故障调查由远端 Brain 读授权日志形成假设、按数据位置路由内网或沙箱 Hands 复现测试，补丁与证据交研发审阅、发布走既有审批；文档核验写回时再核对版本，避免旧结果覆盖新事实；确定的步骤、审批和交易边界交给工作流或业务代码，Agent 处理资料理解、调查分析与按反馈调整行动。承载用阿里云 AgentCore：自研 Harness 封装容器镜像走高代码 Agent 入口（准备镜像、配置运行与访问、连接持久状态与执行资源、接通调用与观测），也可用托管 Harness 入口围绕 QwenPaw 或 Qoder 配置；未来方向是把应用托管延伸为持续的 Agent 服务管理，让自建与托管 Harness 通过兼容的身份、任务和事件协议接入，围绕完整生命周期提供版本发布、任务调度、人工介入、恢复运行和结果交付。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-39.png" width="90%" alt="Personal Agent 与企业智能体共用服务架构" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-40.png" width="90%" alt="企业事件驱动任务的执行与恢复链路" />

## 9. SuperAgent：双层架构与事件驱动

DSH 团队观察到一个人通常只能同时跟进 3 到 5 个活跃会话，总结很准确：**单任务的上限取决于模型，多任务的上限取决于人的注意力**。SuperAgent 要做的事压成一句话：让人感觉始终只有一个 Agent，而它能同时做很多事。四个要求对应人的四个瓶颈：连续（群里说用方案 A、代码评论里改成方案 B，它能接上）、高效（不等上一件做完就接下一件）、主动（自己看环境，值得做就推进、没必要就闭嘴）、持久（一直在线、出问题自己恢复、合上电脑不停）。此前行业各自拆了一部分：Cursor Background Agents 把任务放云端跑拆「要人盯着」，但发起调度还是人；LangChain Ambient Agents 事件驱动拆「要人发起」，人只在收件箱处理请求；Muse、dots、Grok Bot 拆「要人在线」，但偏个人、团队责任不是重点。双层架构解开**连续性与吞吐量的矛盾**：所有事放一个 Session 上下文最连续，但单个 ReAct Loop 只能串行、排队且互相打断；每件事开新 Session 可并发，但彼此不知道对方在干嘛、还各自跟你说话。解法是拆开：**Router 负责连续性**——所有对人的沟通和任务间协调都经过它，是系统的全局序点和记忆，不执行具体工作（DSH 甚至可以不给它 Bash），较轻的模型往往就够；**Worker 负责并发**——每任务一个隔离 Session，配最强模型，推理和工具调用关在自己的 Session 里，有结论汇报 Router 统一对外回复。与 Agent Team 的 Team Lead 的区别：Team Lead 深入任务内部做拆解，Router 只管任务之间的关系；Worker 内部再用 Subagent 或 Team 对 Router 透明——双层架构讲的是职责划分，不是某个特定组件。事件驱动拆「要人发起」：真实环境事件流高噪音低触发率，每条都问模型又慢又贵，所以简单情况走 Fast Path（就是规则，如重点监听某些群或某些用户的发言），少数复杂情况走 Slow Path（就是模型）；DSH 实验负载里约 300 条消息只有约 20 条是工作请求（合成数据）。最巧妙的是路由：同一 PR 或群话题下的一串事件叫一条 **Thread**，Worker 接任务后订阅它，之后事件由程序直接送到手上不再经过 Router（订阅直通）；Worker 与 Thread 多对多，两个 Worker 订阅同一 PR 就能看到彼此动作，回答了「Worker 之间不沟通会不会打架」。消融实验：去掉直通后任务完成时间几乎没变，但 Router 多做约 30% 的决定、读缓存 Token 多约 37%——**它省的是 Router 的负载，不是任务的时间**。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-41.svg" width="90%" alt="DSH-SuperAgent-首图-IM版-动画.svg" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-42.png" width="90%" alt="superagent 02" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-43.png" width="90%" alt="superagent 03" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-44.jpg" width="90%" alt="Picture 4" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-45.jpeg" width="90%" alt="dsh-arch.jpeg" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-46.png" width="90%" alt="superagent 06" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-47.png" width="90%" alt="superagent 07" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-48.png" width="90%" alt="superagent 08" />

## 10. 上下文组织、全双工与计算环境分离

上下文窗口当 Cache 管，两个来自编译优化的词：**Inline** 把近期很可能用到的信息直接放进窗口省一次工具调用，**Spill** 把超预算或低频内容留在窗口外只留摘要或引用；放什么由局部性决定（IM 消息的前后相邻消息、代码评论所在讨论的相邻评论）。规则一致地用到 Trigger、Thread、Worker Session 上就构成引用图：每个对象内联下一跳对象的 ID，模型从当前事件顺引用逐跳展开，即**链式召回**——Router 不用把所有历史放进窗口也能找回旧任务；原文坦白边界：主要解决近期任务，跨月之后长程记忆仍是瓶颈。全双工与 Codex 插话有关系但不一样：**插话解决「消息能不能进来」，全双工还要解决「消息要等多久才被处理」**。steer 能把消息注入运行中的一轮、下一个推理步被看到，但模型循环是推理、调工具、等结果、再推理——正在等同步工具时，说「先停」也可能要等 20 分钟测试跑完。全双工把耗时命令和子任务改成异步 start/stop：调用立刻返回「已启动」、循环继续走，工具后台跑、结果作为新事件投递回来，模型也可主动 stop；推理步一直很短，新消息在当前步结束后就能处理（模型本身仍一步一步跑，并没有同时做两件事）；原型里前台命令超过 5 秒自动转后台。计算、状态与环境分离有两层：Agent Loop 放云端无状态容器、Session 存数据库，容器重启替换不影响进度；本机未提交修改、私有凭据、内网依赖在云上重建成本高也容易漏，就让环境留在原地、只装一个不保存会话状态的轻量 daemon 执行命令返回结果，设备重新上线后云端继续——即 BYOM（Bring Your Own Machine），**与其重建环境，不如把离不开本机环境交互的操作下发到本地执行**；代价是依赖设备在线，离线时那一步停下但进度不丢。Cursor、Codex 云端任务走另一条路在云上重建环境：不依赖你的电脑、可并行、隔离好，代价是复刻成本，两种做法没有绝对好坏。还有个容易忽略的问题：**Agent 的故障常常不是进程挂了，而是进程活得好好的、模型在原地打转**，存活探测发现不了，所以 DSH 在系统外放独立 Watchdog 会话，定时判断每个 Worker 有没有实质进展、方向有没有跑偏。实验数字要完整读：SuperAgent P50 12.4 分钟、P95 15.7、读缓存 2323 万 Token（3.8 倍）；单会话提示词要求优先委派 P50 13.8、P95 29.0、1082 万（1.8 倍）；中性提示词 P50 20.4、P95 29.5、605 万（基准）。只改一句提示词，一半任务完成时间只比 SuperAgent 慢 11%、Token 还不到一半——**架构买到的是稳定**：模型总有一次会判断「这活很小我自己干」，这一次就把最慢任务拖到 29 分钟，这种随机性靠提示词消不掉，代价是 Token 翻倍多；且这是合成负载（编码用只耗时间的工具代替），测的是调度能力，不能直接推出真实团队快这么多。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-49.png" width="90%" alt="superagent 09" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-50.png" width="90%" alt="superagent 10" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-51.png" width="90%" alt="superagent 11" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-52.jpg" width="90%" alt="Picture 11" />

## 11. 原型源码的五个设计判断与边界

DSH 开源了约 1.6 万行的原型，核心概念对应朴素问题：Trigger 与 Thread（世界上发生了什么、哪些属于同一回事）、**Ticket**（一份获准开工的工作，系统里最稳定的东西——会话可以断、执行者可以换，Ticket 不变）、Policy（团队规矩，会改所以有版本）、**Mandate**（这份 Ticket「凭什么可以做」的凭证：谁要求的、范围多大、依据哪版规则）。Ticket 与 Mandate 分开的价值：修复已合并、Ticket 结束，一周后有人在那个 PR 下说「这里还有个问题」，可沿用当时的 Mandate 恢复工作，但先对照最新规则检查它是否仍有效——**一件工作能不能继续，和它现在是什么状态，是两个问题**。一条消息变成工作五步，整条链路只有一步调用模型：进门登记（不管有没有用先落库、重复只算一次，Append Only 思路，重启不重放、事后可查消息去向）→ 查 owner（人的后续消息落在某 Ticket 跟进的 Thread 上就直接交对应 Worker，Router 不介入）→ 门禁（代码判断发消息的人有没有资格）→ 才用模型 → 开单（Ticket、Mandate、订阅、确认回复一次性生成，不出现「单开了但没人知道」的中间状态）。五个设计判断：**模型提议、程序裁决**——确定性核心是 Ticket 状态唯一写入者，Router「接单」本质只是提交申请，核心校验权限、规则、参数和当前状态，不合格就拒绝；模型错了、被注入了，最坏也只是提交了一个被拒绝的申请；Router 不许干活不只写在提示词里，长时间等待类操作在代码层面就被拒绝。**先记账再动手**——要做的外部动作也当成数据，和状态改动记在同一笔账里，提交后由后台逐条执行（Outbox 模式），启动 Worker、投递消息、发 IM 全走这条路；模型的工作不可能完全重放，重启后 Worker 收到提示先看代码目录和 PR 实际状态再决定要不要重做。**外部文本永远只是数据**——优先级明确、外部文本在最底层；Router 转交任务备注最多 30 个词、不许添加实现计划和验收标准，Worker 必须自己读原始消息，防「传话失真」。**主动能力要能灰度**——新规则默认试运行，模型照常判断但只记下「如果放开我会接这个单」不真开工，团队看记录觉得准再放开执行；判断必须对每条规则逐一给结论，接单引用消息原文作证据。**人的优先级最高**——状态按「在等谁」算、等人的排最前；并发名额留一个给人，Worker 全忙时人的消息仍能唤醒已有工作；区分「送到了」和「读到了」，消息进入 Worker 会话不算数、真正进入模型历史才算，Ticket 结束时还没读到的人类消息退回重新评估——人在最后一刻说「先别合，方案有变」也要被正确处理。原型的边界也明显：状态在单机数据库，一个部署只对应一个仓库一套账号；Worker 以运维者系统身份运行，文档明说命令包装不是安全边界；文章提到的 Watchdog 和投机执行在原型代码、文档、提示词里都没搜到；完成主要靠外部事实（PR 合并了），对研发自然、换到业务工作就不够。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-53.png" width="90%" alt="superagent 13" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-54.png" width="90%" alt="superagent 14" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-55.png" width="90%" alt="superagent 15" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-56.png" width="90%" alt="superagent 16" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-57.png" width="90%" alt="superagent 17" />

## 12. 笔者思考：数字员工四问与中心化的取舍

判断一个东西算不算数字员工看四个问题：需要每次重新讲背景吗（真同事不用，所以不能有「新建会话」概念）；走开之后它还在做吗（等得了别人、接得上）；没人催的时候会动吗（上游完成、CI 挂了、到时间了要被叫醒）；做错了能查清楚是谁为什么吗（企业里没有责任和审计的员工没法用）。「连续、高效、主动、持久」换个说法就是一个好同事的基本素质。**Router 不是必须的**：它打包了三份工作——对人的前台交互、判断路由、全局记忆，并不必须放在同一个常驻会话里。笔者的做法：前台就是 Channel 本身（人和 Agent 看同一条时间线），谁该被叫醒由程序按任务状态计算，需要判断的部分交给 Coordinator（Channel 里的普通成员，职责写明「不亲自执行具体业务操作，而是拆解、指派、跟踪与汇总」），记忆放在 Quest 和文件里。得到的是协调者不用常驻、上下文不无限膨胀、有事叫醒做完就走、权限边界更清楚；失去的是常驻 Router 的连续感和「积压事件下一轮一起处理」的批处理红利。中心化 Router 的设计原点值得注意：人类组织分层是因为**人的带宽很窄**，一个管理者同时跟不了几件事；Agent 读得快、不累、不用开会同步，DSH 压测有个反直觉结果——事件从每分钟 1 条涨到 40 条，单个决定的平均推理时间反而从 6.4 秒降到 1.6 秒，因为思考时积压的事件下一轮合并处理。**不要把人类组织的形态直接搬到 Agent 身上**：层级、周会、逐级汇报是为适应人的带宽发明的，很多多 Agent 系统照公司组织架构设计角色可能恰恰学错了地方。但瓶颈还在只是换了地方（压测 Worker 用假模型、速率只到每分钟 40 条，不能外推）：上下文容量（DSH 靠直通加链式召回、承认跨月瓶颈；笔者按 Channel 切分、协调者不常驻）、判断质量（只有消息明确指向某 Ticket 才归到它；@ 只算沟通、正式建单才算委派）、成本（接受 3.8 倍读缓存；笔者有事才调模型但还没做合并唤醒）、爆炸半径（外部文本只算数据、权限代码强制；笔者按 Channel 隔离、跨 Channel 需双方授权）。DSH 说切得越细吞吐越高但连续性越低，「在全局记忆问题被解决之前这一权衡始终存在」；企业里笔者更愿意先要边界。**中心只该关心结果、不该关心怎么做**：一旦关心「怎么做」就要读细节做规划，马上退化成很重的 Team Lead。笔者的任务只定义目标、验收标准、责任人和依赖，没有「实现计划」这一项，执行者自己决定怎么做，协调者拆完就结束这一轮、子任务全部结束时平台叫醒它；DSH 更极端，Router 连验收标准都不许写、Worker 回到原始需求自己判断。差别在于研发有 PR、CI 这些客观事实，业务工作没有客观完成信号，**验收标准就是任务的接口**。「只看结果」的前提碰到业界著名争论：Anthropic 的 Research 系统（2025 年 6 月）主 Agent 拆任务、子 Agent 并行搜索；Cognition 同期发《Don't Build Multi-Agents》，举 Flappy Bird 例子——一个子 Agent 做了超级玛丽风格背景、另一个做了对不上的鸟，因为每个行动都带隐含决策彼此却看不到。两边都有道理：调研可以切开，一个游戏的美术风格切不开。答案不是该不该用多 Agent，而是**切分的边界在哪里：只有能被独立验收的工作才能分出去**。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-58.png" width="90%" alt="superagent 18" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-59.png" width="90%" alt="superagent 19" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-60.png" width="90%" alt="superagent 20" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-61.jpg" width="90%" alt="Picture 20" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-62.png" width="90%" alt="superagent 22" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-63.jpg" width="90%" alt="Picture 22" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-64.jpg" width="90%" alt="Picture 23" />

## 13. Flock 实践与两个趋势

DSH 回答「一个 Agent 怎样同时做很多事」，协同空间 Flock 回答「**一群人和一群 Agent 怎样对一件事负责到底**」。最重要的是控制面与执行面分离：控制面是业务事实（谁负责、做到哪了、结果是哪一版），执行面只管把这一轮跑完（模型调用、工具执行、断点恢复）；执行可以失败、重来、换人，责任和进度在控制面不会丢——与 DSH「Ticket 不跟随会话」同一想法，只是做成了人也能直接看到和操作的产品。产品形态是一张 Channel 组成的网：每个 Channel 对应一个项目或业务场景，里面有人、协调者、各种 Agent 甚至用户电脑上的本地 Qoder，共享一条时间线，上下文和权限默认不出这个空间。跨边界协作不是把对方拉进来，而是在对方 Channel 建一个任务、由对方在自己的空间执行；同一条交互线往返超过上限（默认 6 轮）会被拒绝并建议合并空间——要聊这么多轮，很可能是边界划错了。本地 Qoder 是 Channel 里的一个成员，与平台 Agent 用同一套任务和验收，只是主动来领任务、在用户电脑上执行。**Sessionless** 不是说底层没有会话，而是会话不再代表身份和任务、只是一次执行的耗材：聊天要连续所以对话会话续接；任务执行每轮尽量开新的（继承旧会话会让上下文跨轮累积），只有子任务收口回父任务、人工断点重启才续接；验收每次新建（验收者不该带执行者的上下文，也没有执行权）。用户没有「新建会话」按钮，系统把几个事实算成一个键、键相同就接着聊；「谁能看见」是容易忽略的隐私边界——Channel 换了成员，新对话自动切到新会话，新来的人读不到之前的上下文；9 月加的血缘表让节点（会话或任务）和每条边（谁触发的）一次查询看全。**Quest** 建表注释三个字：责任状——可分配、可追踪、可验收的工作，有目标、验收标准和唯一责任人，类似 DSH 的 Ticket，本质是把聊天和会话变成结构化可显式化的任务列表。最关键的是「待验收」状态：**Agent 跑成功不等于任务完成**，只代表提交了一版结果，要由人或指定验收 Agent 认可才算完，不满意打回再执行、上一版留着——企业里「做完了」必须有人认。任务链的 DAG 不是规划出来的而是做事时自然长出来的，机制只有三条：执行某任务时新建任务默认是当前任务的子任务；建任务写明依赖谁、上游完成才唤醒下游；子任务全部结束平台唤醒父任务并带上已验收结果汇总。「失败订单复核」就是执行者中途自己拆出来的，协调者一开始并不知道；说不清新任务属于谁平台会拒绝创建，否则游离任务让父任务永远等不到收口。Quest 链还是上下文召回的副产品：任务链本身就是引用图，边是工作关系、比事件关系更稳定——答案分散在第二版批注、上游失败明细、业务人员一句答复三处时，Agent 不需要记住两周前的事，沿工作关系走过去就行。主动推进的实现很朴素：任务状态存在账本里，状态一变就算出该叫醒谁，有事才调用模型，一次执行的产出变成下一次的触发。踩过最大的坑是**互相唤醒**：「组织一次报数」任务理想 3 次执行，实际跑了 10 多次、同一任务产生 8 个执行实例、还有 Agent @ 了自己；根因不是模型笨，而是平台把「被点名」和「任务落到头上」放进同一条链路，被 @ 的 Agent 拿到「完成后必须提交交付物」的指令就认真开始拆任务发通知。修法是把语义分开：**@ 是沟通，Quest 才是委派**——被 @ 只回应不领执行权，要干活先建任务；加上抄送不唤醒、Agent 间连续唤醒默认最多 3 次、人一介入清零。平台的硬约束比提示词可靠。跨会话记忆经历过转折：早期每次唤醒把成员名单、今天的消息、最近动态全拼进去，上下文越来越胖还总有废话；瘦身后全删、从推到拉（与 Inline/Spill 同一结论，是被线上问题逼到的）；长消息不直接截断而是保留头尾、中间折叠标明取回方式——每次唤醒都是全新的，检索是了解过去的唯一通路，截断会让它把残缺内容当成全部。再往前是 MDC（Meta-Dance-Context）思路：**不要让 Agent 记住，让 Agent 能找到**——记忆放在可自己翻阅的文件接口后面，每次唤醒编译出干净窗口、需要什么再读，结果可审计、可引用、换模型也带得走。最后是两个趋势判断：**Agent 的架构在趋同**——不是巧合或互相借鉴，而是约束条件把解空间压窄了（模型能做完单任务、瓶颈变成人的注意力，所以要统一对外入口；任务越来越长越来越多，所以要隔离执行单元；任务要比会话活得久，所以要可持久化可追踪的任务对象），问题一旦定义清楚答案就会收敛，就像数据库最终都走向预写日志、操作系统最终都走向进程和调度器。**Agent 正在回到传统工程**——从「一次对话」变成「长期运行的进程」就必须面对分布式老问题：进程会崩、机器会离线、消息会重复、副作用不能执行两次，于是越来越多看到预写日志、Outbox、租约、可回放事件记录这些经典手段。模型是系统里唯一不确定的部件，工程的职责是用确定性的外壳把它包住；可靠性不再只取决于模型能不能做对，还取决于做错或中断时系统能不能恢复——**模型是 CPU，Harness 是操作系统和数据库**。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-65.png" width="90%" alt="superagent 25" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-66.png" width="90%" alt="superagent 26" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-67.png" width="90%" alt="superagent 27" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-68.png" width="90%" alt="superagent 28" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-69.png" width="90%" alt="superagent 29" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-70.png" width="90%" alt="superagent 30" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-71.png" width="90%" alt="superagent 31" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-72.png" width="90%" alt="superagent 32" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-73.png" width="90%" alt="superagent 33" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-74.png" width="90%" alt="superagent 34" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-32-75.png" width="90%" alt="superagent 35" />

## 写在最后

Personal Agent 把「常驻进程加数字身份」做成了产品，AaaS 把身份、状态与执行协议做成了服务底座，SuperAgent 与 Flock 则殊途同归地走向确定性工程外壳。下一篇整理 [FDE工程实践专题](/source/agent/企业级Agent手册/33-FDE工程实践专题)，看 AI Coding 全生命周期的企业级 FDE 工程实践如何把 Agent 能力落到交付现场。