# Agent 调优与数据飞轮：把运行经验变成可验证的改进

模型调优改变的是模型本身的能力，Agent 调优改变的是一个已经上线的 Agent 怎样使用模型、工具与业务规则，把任务反复做好。上线之后仍要持续回答两组问题：**任务有没有做好，以及把它做好花了多少代价**。一条回答正确的轨迹可能反复查了相同资料，一次 Token 明显减少的执行也可能省掉了必要验证，调优要同时看业务结果、执行过程、时间和成本。本文整理数据飞轮的完整闭环——接入、观测、评估、实验、经验库与数据集沉淀。核心判断：**飞轮的关键不在于某一个环节多强，而在于环节之间首尾相接**——评估的产出是实验的输入，实验的结论又指回下一轮评估，经验库则让每一圈都比上一圈起点更高。

## 1. 上线以后：会做、做完和稳定交付是不同层次

传统应用主要通过代码规定行为，在输入、状态和外部依赖相同的前提下确定性逻辑通常可预测可复现，研发围绕明确的功能契约编写测试。Agent 把其中一部分决策交给了模型：开发者给出目标、工具和约束，模型在运行时理解意图、规划步骤、选择工具，再根据中间结果调整行动，同一个任务可能因上下文、工具反馈或生成结果不同而走出不同路径。以退款为例，接口可以根据订单状态和规则判断是否允许退款，Agent 还要从对话中确认用户指的是哪笔订单、识别适用规则、选择操作并核实退款是否完成——**对话顺利结束、接口没有报错，都不足以说明这件事办对了**。相比传统逻辑，Agent 新增的要求落在四处：执行路径要检查模型为什么选这条路以及中间反馈怎样影响后续行动，正确性要同时验证目标达成、业务约束和交付结果，故障定位要进一步区分理解、上下文、工具使用和恢复策略的问题，变更验证还要观察重复执行是否稳定以及质量成本延迟怎样变化。

公开 Benchmark 提醒会做、做完和稳定交付是不同层次：τ-bench 原论文中 GPT-4o 原生工具调用在零售任务上 pass¹ 为 61.2% 而 pass⁸ 低于 25%（pass⁸ 指同一任务八次执行全部成功，区别于「八次中至少成功一次」的 pass@8），说明一次做对之后还要检查重复执行的可靠性；OSWorld 2.0 长流程任务中某模型严格完成率仅 20.6% 而部分得分 54.8%，说明完成许多中间步骤并不等于交付了完整结果。这些是各自测试条件下的结果，不代表当前最高分，**也不能直接换算为企业业务成功率**，企业需要在自己的业务上建立评估。**评估负责把「好不好」落实为可检查的标准和结果，调优负责根据这些结果改变系统，二者需要通过真实任务连起来**——否则团队要么只有分数没有修改方向，要么不断改 Prompt 却说不清哪些修改有效。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-01.png" width="90%" alt="AgentLoop 数据飞轮实践（一）配图 1" />

## 2. 数据飞轮：两条反馈路径与模块边界

一次排障往往能修好眼前的问题，却未必能帮助下一次排障：工程师记得原因，相关 Trace 散在日志里，修复记录又在另一个系统，几周后同类问题换一种表述再次出现仍要从头查起。数据飞轮要解决的就是这种断裂——把一次执行留下的事实整理成可复用样本，用评估找出问题，用实验检验修改，再把有效变更带回运行环境，过程中留下的轨迹、样本、评分规则、失败模式和版本记录可被下一轮继续使用。这里有两条需要同时推进的反馈路径：一条改进数据和判断方法（如客服 Agent 在「有哪些功能」和「如何配置评估」两类问题上需要覆盖的内容不同，最初把两道题的规则写在同一个评估器里，实验后才发现标准不合适，于是给 Dataset 增加题目级 Rubric 逐题填写再重新实验），另一条改进 Agent 的行为（评估确认缺少配置步骤后补充 Skill，发现工具用错后修改工具描述，发现超时后反复提交则检查重试和结果核实逻辑，这些修改先成为候选经同条件实验和回归再决定是否采用）。因此**数据在调优中承担两种作用：帮助判断应该改哪里，也帮助拒绝没有效果或带来退化的修改**；样本数量增加、经验入库、候选生成都还只是过程产物，有效变更进入运行以后新任务的结果才提供下一轮反馈。

**Pipeline 是这套架构中的数据生产层**：原始 Trace 以调用和事件为单位，评估可能要检查完整任务，实验可能只需要任务输入和预期行为，成本分析又要保留调用量与耗时，Pipeline 按这些目标组织数据、提取字段、筛选和去重，把一套加工规则变成可以按范围或周期执行的工作，不同用途可配置不同管线。各模块围绕同一任务连接但不必排成一条只能向前走的流水线：Trace 与 Trajectory 用于按应用问题工具或耗时搜索任务、展开步骤、选入数据集，Pipeline 把每天的运行记录变成质检人员和评估器能直接使用的样本，Dataset 与人工复核积累可重复使用的业务验收题，Evaluator 与持续评估发现哪些场景需要改进，Experiment 让当前方案与候选执行同一批题比较逐题结果成本耗时，Trace2Optimizers 从问题改进 Skill 工具与运行机制或把历史方法送入经验召回。评估结果可以写回 Dataset 供人工复核，复核既可能修正样本也可能修正评估器，优化候选需要回到实验，已采用的 Skill、Harness 或经验又会改变后续轨迹。**模块边界要清楚：轨迹组织不能凭空补出业务事实，Pipeline 不能替代人工确认，评估不能代替候选执行，保存了一个版本也不等于运行中的 Agent 已经使用它**。第一次建设调优流程时先选一个团队确实想解决的问题（如产品客服能答概念却经常漏掉操作步骤），一轮可以这样完成：找到真实问题 → 把问题持续收集起来（少量直接加入数据集，日常质检则建 Pipeline 持续写入候选集）→ 把业务要求写成题库（产品或客服人员确认参考答案，在每道题的 rubric 中写明应包含的步骤，选入黄金集）→ 先知道哪里没做好（创建评估器对已知题试评确认能指出遗漏再用于更多真实任务）→ 修改后让两个版本都做题（用同一份黄金集分别运行旧版和新版，看操作题是否改善、正常题是否保持、成本耗时能否接受）→ 采用有效方案继续接收反馈。这一轮留下的不只是一个改过的 Prompt，还包括一份可复用题库、一套评分要求、改动前后的结果以及持续收集问题的管线，下次换模型或升级产品时可直接继续使用。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-02.png" width="90%" alt="18.3 围绕同一任务连接各个模块 图1" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-03.png" width="90%" alt="AgentLoop 数据飞轮实践（一）配图 2" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-04.png" width="90%" alt="AgentLoop 数据飞轮实践（一）配图 3" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-05.png" width="90%" alt="AgentLoop 数据飞轮实践（五）配图 10" />

## 3. 接入与观测：先看清一次请求怎样执行

1688 的组织经营大脑「宙斯」在接入前的痛点有代表性：偏差根因难以对应到具体修改动作（行为受 Prompt、Skill、工具参数、读取策略多重因素影响，优化依赖经验试错），优化效果缺少量化依据（少量用例通过只能说明局部改善，无法证明同类问题已解决或是否引入新偏差），缺少稳定的回归机制（失败请求、边界场景和判定标准分散在日志与沟通记录中，同类缺陷在不同版本反复出现）。调研对比 AgentLoop、DeepEval 与内部评测平台后选择 AgentLoop，理由是它可通过 ARMS 探针无侵入采集执行链路，且观测、评估和样本回归一体化。AgentLoop 的数据接入构建在 **OTel（OpenTelemetry）标准协议**之上以探针形式工作，把各个调模型、调工具的地方以 Trace ID 串联并完整保留上下文依赖，形成 Trace 拓扑图再组装出完整的思考和执行轨迹；选标准协议做底座本质上是在保证今天接进来的数据未来任何基于 OTel 的生态都能消费，接入不锁定、数据可互通。针对不同形态的 Agent 提供四种接入方式：通用 Agent 一键对接（已做专业化埋点无需开发）、Agent 框架 SDK 集成（埋点跟着框架走，框架知道模型与工具调用发生在哪）、自定义高代码注解埋点（把埋点位置控制权交还开发者，AI-coding 方式加几行埋点成本很低）、eBPF 无侵入（内核级监控，适合存量系统、无法改动的闭源组件）——**四种方式不是互斥的选择题，而是按 Agent 形态和改造意愿选择成本最低的一条路**。接入时两个必填概念：Service Name 在同一 AgentSpace 下区分不同应用与来源（数据的归属标识，后续观测评估按它圈定范围），License Key 用于数据鉴权（数据的通行证）。

观测用 Session、Trace 和 Span 组织调用日志：Session 对应一段多轮会话，Trace 对应其中一轮请求，Span 记录该轮中的模型调用、工具调用等具体操作，沿调用链可检查各步骤的输入输出参数结果和耗时。这里的「白箱」指可检查的执行记录，**能看到多少细节取决于框架暴露和实际采集的数据，接入验收需要确认关键步骤是否齐全，不能只以控制台出现一条 Trace 为准**。一条合格 Trace 的判定口径有三：步骤齐全（模型调用、每次工具调用均有 Span 且输入输出可读）、嵌套正确（子代理和异步任务不丢父 Span，无孤儿 Span 或断链）、染色正确（业务相关数据在传播过程中不丢且正确挂在对应 Span）。基于 Claude Code / Claude Agent SDK 的 Agent 可用探针或 webhook 两条路接入，演示采用更原生的 webhook 配合 LoongSuite Pilot——它是一个**旁路进程**，不在 Agent 的执行路径上，采集的开销和故障都不会影响 Agent 本身，数据发不出去时 Agent 照常工作；安装后 hooks 已配置在 settings.json 里，需拷贝到自己 Agent 的安装目录并重启才生效（忘了拷贝或重启数据就不会上报）。常见踩坑有五：环境未隔离（生产预发共用应用标识或 workspace 导致结果不可比较，应配独立标识并按环境筛选）、插桩范围过宽（低价值基础设施 Span 淹没业务链路，应仅开启 Agent 所需插桩并显式关闭数据库访问等非必要组件）、用户标识未随链路上报（Span Attribute 仅作用于当前 Span，异步新建 Span 不自动继承，需在入口写入 OTel Baggage 并在异步切换前完成上下文捕获）、多套链路上下文互相覆盖（共用同一上下文导致子任务挂错父 Span 或断链，应为不同链路设独立上下文键与父链路恢复逻辑）、TraceId 不统一（两套体系各自生成 TraceId 无法跨系统检索，应在入口及关键节点日志同时打印两个 TraceId 建立映射）。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-06.png" width="90%" alt="一、背景与痛点：接入前的“盲人摸象” 图2" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-07.png" width="90%" alt="2.2 观测：先看清一次请求怎样执行 图3" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-08.png" width="90%" alt="步骤一：开通 workspace 并通过启动参数挂载探针 图6" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-09.png" width="90%" alt="步骤二：验证 Trace 完整性 图7" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-10.png" width="90%" alt="3.3 踩坑清单 图12" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-11.png" width="90%" alt="3.3 踩坑清单 图13" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-12.png" width="90%" alt="AgentLoop 数据飞轮实践（二）配图 1" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-13.png" width="90%" alt="AgentLoop 数据飞轮实践（二）配图 2" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-14.png" width="90%" alt="AgentLoop 数据飞轮实践（二）配图 3" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-15.png" width="90%" alt="AgentLoop 数据飞轮实践（二）配图 4" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-16.png" width="90%" alt="AgentLoop 数据飞轮实践（二）配图 5" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-17.png" width="90%" alt="AgentLoop 数据飞轮实践（二）配图 6" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-18.png" width="90%" alt="AgentLoop 数据飞轮实践（二）配图 7" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-19.png" width="90%" alt="AgentLoop 数据飞轮实践（二）配图 8" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-20.png" width="90%" alt="AgentLoop 数据飞轮实践（二）配图 9" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-21.png" width="90%" alt="AgentLoop 数据飞轮实践（二）配图 10" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-22.png" width="90%" alt="AgentLoop 数据飞轮实践（二）配图 11" />

## 4. 评估：从黄金指标到 Rubric

**工具调用成功只能说明某个执行步骤正常结束，不代表任务真正完成**，评估还要判断用户要求是否满足、关键结论是否有证据、最终结果是否完整交付。评估体系分两层：**评估器（Evaluator）**定义评估指标是什么，包含类型、输出定义和评判标准（Rubric），是「怎么评」的定义，与具体数据无关可以复用；**评估任务（Evaluation Task）**指定用哪些评估器对哪些数据做评估，是「评什么数据、何时评」的执行配置——评估器是考卷和评分标准，评估任务是组织一场考试，同一套考卷可以考不同的学生，同一批学生也可以考多套卷子。评估器按类型分三种：Code 评估用代码规则打分，确定便宜但只能覆盖能用规则表达的指标（格式、长度、字段完整性、数值阈值）；LLM 评估用一段 Prompt 直接调大模型打分，适合靠语义理解就能判断、无需外部查证的维度（相关性、语气、是否答非所问）；Agent-as-a-Judge 让专门的评估 Agent 像人一样阅读输入输出和运行轨迹按 Rubric 判断，可挂载知识库、业务 Skill 或 MCP 先查证事实再评分，适合需要业务知识或多步核验的维度（回答是否符合最新政策、结论是否有数据支撑），代价是消耗更大。

评估的第一步不是写代码而是回答「这个场景下什么算好」，答案就是黄金指标（Golden Metrics）。以客服 Agent 为例关注两类：**回答质量**（最终答案对不对好不好）和**执行过程**（工具调用是否合理、路径是否绕远）——只看结果会漏掉「蒙对的」，只看过程会漏掉「做对了但答非所问的」。制定黄金指标可以让 AI 基于业务场景帮忙拆解成 **Rubric**：把抽象的「好」拆成一条条可判定的评分细则，每个指标在什么情况下打什么分数、占多少权重，最终汇总成一个加权分数，**有了 Rubric 评估才从「凭感觉」变成「可复现」**；对业务足够熟悉也可人工制定，AI 只是提效手段，特别关注的指标（如是否泄露用户隐私）还可提出来作为顶层评估器单独评估，不淹没在总分里。Rubric 的载体就是评估器的 Prompt，评分规则和 input、output、执行轨迹三个参考变量都写在里面；评估器输入三变量恰好对应评估一次运行所需的三类信息（input 用户问了什么、output Agent 答了什么、轨迹 Agent 怎么一步步得出答案），有了它们既能评结果也能评过程。输出定义是一组结构化字段：score 单项得分、raw-weighted score 加权分（0~1）、final score 归一化总分、decision 与 scenario type 结论判定与场景分类（方便下游按结论过滤）、summary 与 explanation 结论摘要与解释（**分数必须可解释，否则低分时不知道该改什么**）、rubric version 版本号（**留版本号才能区分「分数变化是 Agent 变了还是标准变了」**）。创建时按场景做减法，用不到的通用项删掉，评估器是长期复用的资产，初始配置越干净后面维护越省心。

评估任务有四个配置点。评什么数据：平台里 Trace 数据关注微服务调用过程（基础设施视角），轨迹（Trajectory）数据关注 Agent 思考和调用工具的过程（智能体行为视角），评估回答质量和执行过程显然要用轨迹数据。怎么跑：持续评估基于新数据来一条评一条适合线上质量盯盘，历史评估对某段时间数据做一次完整评估适合复盘和专项分析。评多少：评估要调用专门的评估 Agent 每条数据走一遍完整流程消耗较大，并非所有场景都需全量，只关心 badcase 时可做采样大幅降低成本（先把最大样本数设小把流程验证掉，需要全量盯盘时再放开）。字段怎么对：把数据字段映射到评估器变量（trace.input→input、trace.output→output、轨迹数据→trace.agent），映射对了评估器才能拿到正确输入。评估结果里分数之外更有价值的是解释、summary、decision 与证据——**评估器不只是打分还要说明「为什么是这个分」，这让低分条目变得可处理**，看到的不是一个孤零零的 0.4 分而是「哪一步做错了、依据是什么」，调优方向直接写在结果里；单次评估存在浮动，可多次评估看均值更客观。更重要的是闭环：在线评估抓出来的 badcase 沉淀进数据集成为后续实验回测的弹药，评估分数低的地方就是下一轮针对性调优的方向。**评估的本质是把专家对「好」的定义变成机器可执行、结果可解释的资产**，这份资产一旦建立后面的实验回测、经验注入才有共同的度量衡。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-23.png" width="90%" alt="2.3 评估：调用成功之后，还要判断任务是否完成 图4" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-24.png" width="90%" alt="步骤三：配置评估 图8" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-25.png" width="90%" alt="步骤三：配置评估 图9" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-26.png" width="90%" alt="步骤三：配置评估 图10" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-27.png" width="90%" alt="步骤三：配置评估 图11" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-28.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 1" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-29.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 2" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-30.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 3" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-31.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 4" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-32.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 5" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-33.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 6" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-34.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 7" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-35.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 8" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-36.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 9" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-37.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 10" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-38.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 11" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-39.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 12" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-40.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 13" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-41.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 14" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-42.png" width="90%" alt="AgentLoop 数据飞轮实践（四）配图 11" />

## 5. 实验：证明一次优化真的有效

改 Prompt、换模型、调参数，任何改动都可能「感觉变好了」，但感觉不算数——回归测试里别的题目可能悄悄变差，答案是用数据集里的题目反复回测用分数说话。实验计划指定数据集、勾选评估器、配置变量映射（一边是实验内置变量 input/output/轨迹，另一边是 dataset 原始内容如 expected output，可加变量映射把它喂给评估器做对照），还可加自定义变量标记实验上下文如版本号、实验记录 ID——**版本号尤其重要，大盘上要对比不同版本的分数差异，没有版本标记就无从对比**。实验要访问的 Agent 往往部署在公司内网只有内网才能访问，云端平台够不着、把数据搬出去测又不现实，为此提供**离线实验平台**直接部署在客户内网就近访问本地 Agent：云端负责存储实验记录、展示大盘，内网平台负责执行（既能出网访问云端又能在内网直接调用本地 Agent），**数据不出内网能力不打折扣**；配置时绑定 AgentSpace 与 region，AK 需具备 AgentLoop FullAccess 读写权限，建议申请专门 AK 保存本地用于离线实验（权限专用、用途单一、出状况好排查）。连接本地 Agent 需要一段自定义调用代码，默认代码假设 API 无状态（发请求拿响应），但大部分 Agent 是有状态的——如基于 Claude Agent SDK 的客服 Agent 需先创建 Session 拿到 Session ID 再向它发消息，默认代码不满足就改成「建 Session → 发消息 → 取响应」的逻辑，保存后发起单题测试验证连通性。**定时调度把回测变成日常**（生产环境通常配每天回归），Launch History 里可看每次触发记录且本地平台与云端控制台数据同步。

每个实验计划自动创建一个实验大盘，提供整体分数、变化趋势、明细，可按题目下钻查看单题分数变化，为消除单次浮动可按时间窗口计算均值。分数分析有一套方法论：**分数变低要及时关注**（可能是 Agent 真的退化了），**先排查 Rubric 定义**（同一版本多次评估分数不稳频繁波动，多半不是 Agent 变了而是 Rubric 定义模糊，标准不清楚分数自然飘，这时要优化评估器的 Rubric），**再看版本差异**（确认评估器没问题后，同一版本内分数稳定、不同版本之间有差异才是版本带来的真实差异）——这套排查顺序避免了最常见的误判：**把「尺子不准」当成「东西变差」**。流程跑通后还有一个关键实践是题目级 Rubric：从线上抓 badcase 时用户问题非常发散没法定具体 Rubric，所以在线评估用通用标准；但实验不一样，badcase 抓出来后知道了具体的用户问题，不同题目的评估标准其实并不相同，用同一套 Rubric 评两道题优化时就会失去方向。正确做法是把 Rubric 定义到题目级别，四步改造：整理每道题的 Rubric（含细项、单项判定、概念边界、扣分项）→ 数据集 schema 加一列 rubric（text 类型）把每题的评分规则原子能力计算公式分别写进对应题目 → 给评估器新增 rubric 变量让它按传入的 Rubric 评估并输出合法 JSON（含 rubric_id、score、reason、item_scores）→ 实验配置里的 Rubric 选项改为从 dataset 读取。改造之后每道题按自己的标准被评估，**哪道题低分就补哪道题对应的能力点**，实验分数才真正有指导意义。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-43.png" width="90%" alt="4.1 实际怎么用：线上巡检、实验验证与发布回归 图14" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-44.png" width="90%" alt="4.1 实际怎么用：线上巡检、实验验证与发布回归 图15" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-45.png" width="90%" alt="4.1 实际怎么用：线上巡检、实验验证与发布回归 图16" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-46.png" width="90%" alt="AgentLoop 数据飞轮实践（四）配图 1" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-47.png" width="90%" alt="AgentLoop 数据飞轮实践（四）配图 2" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-48.png" width="90%" alt="AgentLoop 数据飞轮实践（四）配图 3" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-49.png" width="90%" alt="AgentLoop 数据飞轮实践（四）配图 4" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-50.png" width="90%" alt="AgentLoop 数据飞轮实践（四）配图 5" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-51.png" width="90%" alt="AgentLoop 数据飞轮实践（四）配图 6" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-52.png" width="90%" alt="AgentLoop 数据飞轮实践（四）配图 7" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-53.png" width="90%" alt="AgentLoop 数据飞轮实践（四）配图 8" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-54.png" width="90%" alt="AgentLoop 数据飞轮实践（四）配图 9" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-55.png" width="90%" alt="AgentLoop 数据飞轮实践（四）配图 10" />

## 6. 经验库：自动挖掘与消融验证

经验库是飞轮里最自动化的一块，核心机制是**算法自动从 Agent 的运行轨迹中挖掘成功模式和失败模式沉淀成经验资产**，以**上下文注入**的方式进入运行过程让 Agent 越跑越好。它建立在一个朴素观察上：同一个坑第一次踩了可以原谅，第一百次还踩就是浪费；成功的模式告诉 Agent 该怎么做，失败的模式告诉 Agent 别怎么做。挖掘的是通用 Agent 领域的常见优化手段（工具调用执行情况、延时、执行准确率、执行路径），这些维度不依赖具体业务任何 Agent 都在反复遇到，因此适合自动化。前提是数据接入已完成，创建经验库时选择应用、命名、设置挖掘起始时间（设早一点可挖掘更多轨迹）；挖出的每条经验可看到内容、适用场景以及来自哪条 Trace，**全程可追溯——经验不是黑箱里蹦出来的结论，每一条都能回查出处**，这在调优排障时非常重要。要让 Agent 用上经验需装一个经验召回 Skill（alibabacloud-agentloop-experience），创建 API Key 作访问凭证、把经验库信息写进 env 配置，Skill 生效还有三个权限条件缺一不可：加入 Agent 白名单、打开 Shell 权限（召回需调用 shell 命令）、新建会话时 allow shell。召回是有判断的：与经验相关的问题会召回对应经验，**没有类似经验时不会召回——这个「宁缺毋滥」的设计防止无关甚至错误的经验误导 Agent**。

看到步骤减少先别急着上线：通用优化手段之外真实业务总有自定义需求，经验的注入方式（召回多少、放在哪、怎么呈现）会直接影响效果甚至可能帮倒忙，为严格保证经验注入之后是正向作用，真正部署前要做召回测试找到最佳策略。以无经验作为基线做一轮消融实验，要调的参数包括：召回阈值（1 最相似 0 最不相似，太高漏召回太低召回噪声，最终选 0.6 一个「相对相似」的水位）、注入条数（只返回 top1，**经验注入不是越多越好，多了会稀释注意力挤占上下文**）、经验在上下文的位置（实测顺序是用户真实问题 → 业务经验使用规则 → 最后 top1 经验，位置影响模型对经验的采纳程度）、经验瘦身（只保留标题摘要、使用条件和关键结论并限制字符数，原始经验往往带着具体场景的冗余细节，瘦身后信噪比更高）、防护护栏（说明经验只是**历史参考**，经验来自过去不一定适用于当前，护栏给模型留了「不照办」的余地）。**每一个参数都是一次「注入经验 vs 不注入/换种注入」的对照，这正是消融实验的含义：逐个因素拆开验证，而不是笼统地说「加了经验会更好」**。经消融选定策略后相比基线耗时降低 30%~40%、成本降低 20%~47%、Token 与工具调用大幅下降；消融的价值有两层——帮助找到最佳策略组合，并证明经验注入在真实业务下有真实效果（不是理论可行而是数字可查）。**演示里的数字属于演示场景，每个使用者都应在自己的真实业务场景里做一遍召回率测试找到属于自己的最佳策略**。两种调优模式不是二选一而是互补：人类专家驱动模式建立标准、兜住业务底线（把专家头脑里「这个回答不行」的隐性判断固化成可复用可回测的显性 Rubric，这份标准本身就是团队资产），全自动化经验库模式在标准之上持续自动增益。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-56.png" width="90%" alt="AgentLoop 数据飞轮实践（一）配图 4" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-57.png" width="90%" alt="AgentLoop 数据飞轮实践（五）配图 1" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-58.png" width="90%" alt="AgentLoop 数据飞轮实践（五）配图 2" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-59.png" width="90%" alt="AgentLoop 数据飞轮实践（五）配图 3" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-60.png" width="90%" alt="AgentLoop 数据飞轮实践（五）配图 4" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-61.png" width="90%" alt="AgentLoop 数据飞轮实践（五）配图 5" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-62.png" width="90%" alt="AgentLoop 数据飞轮实践（五）配图 6" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-63.png" width="90%" alt="AgentLoop 数据飞轮实践（五）配图 7" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-64.png" width="90%" alt="AgentLoop 数据飞轮实践（五）配图 8" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-65.png" width="90%" alt="AgentLoop 数据飞轮实践（五）配图 9" />

## 7. 数据集沉淀：从 Badcase 到质量资产

数据集不是临时保存的一批样本，而是按使用目的持续沉淀的数据资产，主要四类：**测试集**用于问题复现和优化验证（来自线上低分样本和 Bad Case，也含低频场景、异常分支和人工设计题目，验证「能不能做对」），**回归集**用于防止历史问题再次出现（已确认修复的 Bad Case 及 Prompt/Skill/Tool/知识库变更可能影响的关键样本，上线前重复执行作为发布拦截和质量门禁），**基准集**由长期稳定、经人工审核且具代表性的黄金样本组成（用于模型切换、大版本变更和核心能力升级时的全量回归、版本对比和质量基线判断），**后训练集**面向模型能力的进一步训练（由高质量执行轨迹、专家标注样本、黄金答案及线上覆盖不足但具代表性的人工题目组成，可用于 SFT、RL、行为对齐和经验迁移，样本不一定都有唯一标准答案，也可含参考答案、偏好关系、过程标注或奖励信号）。一条线上 Bad Case 通常先进测试集完成复现和方案验证，修复确认后进入回归集防止同类问题再现，经长期验证的代表性样本进一步沉淀为基准集，其中适合提升通用能力的高质量样本可加工为后训练数据；**实验过程中临时冻结的样本集合只是一次实验的数据切片，可从上述数据集中选取，不再单独作为一种长期数据集**。

两个典型 Case 表面现象不同但反映同一类质量风险。Case A：用户要求重新读取在线文档并按最新内容回答，Agent 只凭对话上下文给出变化说明却没真正发起本轮读取，执行记录里只有用户请求和最终回答缺少新的读取记录，回答看起来可信但依据可能仍是旧上下文或模型推断——当文档已更新时 Agent 可能把旧信息包装成最新结论，改进方向是遇到「重新读取、刷新、最新」等要求必须触发本轮读取并将答案与本次读取结果或文档版本关联，读取失败时明确说明未能获取最新内容。Case B：主 Agent 委派子 Agent 只读查询 6 个工作项，子 Agent 确实执行了全部 6 次查询且都成功返回详情，但最终摘要前后矛盾（既说已开始查询又说没收到工作项 ID），主 Agent 直接采信得出「6 项都没查到真实数据」的结论，任务完成度仅 0.25 分——底层查询已成功用户却收到「没有数据」的错误结论，改进方向是主 Agent 在子任务结束后以结构化返回结果为准逐项核对查询数量和必填字段、比对子 Agent 摘要与实际执行轨迹是否一致、发现冲突时优先采用可核验的真实返回。两者共同说明：**Agent 是否完成任务不能只看最终回答或任务状态，还要核验本轮是否执行了必要动作、远程工具结果是否被正确读取、关键结论是否完整交付**；若监控只看任务是否「已完成」、工具是否「调用成功」，就发现不了「结果已返回但主流程未真正使用」这类问题。宙斯接入后的实际效果（特定业务场景、固定数据集和评估口径下的一段运行）：单次问题定位从约 55 分钟缩短至 15 分钟（效率提升约 73%），一轮完整回归从约 1.5 人天缩短至 3 小时（耗时下降约 75%），评估覆盖从每轮人工抽查约 200 条扩大到日均自动 2000+ 条记录和 5 个维度（约 10 倍）；从任务完成度不高于 0.6 的记录筛出 72 条候选，人工复核确认 31 个有效问题其中 26 个已修复并通过回归（修复通过率约 84%），固定回归集上任务完成度均分由 0.62 提升至 0.82、证据支持度由 0.66 提升至 0.85、历史问题复发率由 16% 降至 5%；工作流由收到反馈后临时排查的「救火」模式转向「线上巡检—人工复核—沉淀回归集—优化验证—上线准出」的「防火」模式，问题在上线前被发现的比例由约 30% 提升至 75%。**这些数字不能直接作为其他团队接入后的预期收益**，但 Bad Case 不再停留在一次性修复而是转化为可重复执行的质量资产，持续降低版本发布风险。

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-66.png" width="90%" alt="2.4 回归验证：让失败样本成为下一次测试的输入 图5" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-67.png" width="90%" alt="Case A｜Agent 读取在线文档，但未获取最新内容 图17" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-68.png" width="90%" alt="Case B｜子 Agent 已完成执行，但结果没有正确回传主 Agent 图18" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-69.png" width="90%" alt="4.3 Case 怎么留下来：测试集、回归集与基准集 图19" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-70.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 15" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-71.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 16" />

<img src="https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/handbook-19-72.png" width="90%" alt="AgentLoop 数据飞轮实践（三）配图 17" />

## 写在最后

飞轮的每个环节都在回答一个问题：接入回答「发生了什么」，观测回答「细节是什么」，评估回答「做得好不好」，实验回答「改动有没有用」，经验库回答「怎么自动变得更好」，五个问题首尾相接，**Agent 的每一次运行都同时是服务的输出和下一轮优化的输入**。而这一切的起点是把分散的运行记录组织成可阅读、可分析的轨迹。下一篇整理 [Agent 轨迹数据](/source/agent/企业级Agent手册/20-Agent轨迹数据)。