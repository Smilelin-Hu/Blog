# PPO、GRPO、RLOO、DAPO 与长推理训练

## 1. 本文要解决的工程问题

长推理 RL 的平均奖励上升，但完成长度、无奖励组、截断率和 KL 同时变化。只看奖励曲线，无法判断策略学会推理还是学会迎合验证器。

本文围绕一个可执行判断展开：怎样在 PPO、GRPO、RLOO 与 DAPO 中保持目标、采样、奖励和更新语义一致？读完应能给出自己的系统边界、输入输出、版本关系和验收证据，而不是只复述工具名称或公式。

![长推理强化学习目标与数据流](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l25_01.png)

## 2. 本文交付物与判定标准

本文的核心决定是：统一 Prompt Group、Rollout、Old Policy、Reference、Reward、Advantage 与 Update Batch 的版本和计量语义，再比较 PPO、GRPO、RLOO 与 DAPO。

完成学习和实验后，应当交付一份最小可复现记录，至少包含输入快照、配置、代码版本、运行状态、原始输出和结论边界。验收证据是：训练记录包含奖励分解、组内方差、有效 Token、截断、KL、熵和策略版本，并能重放一组 Experience。

围绕“PPO、GRPO、RLOO、DAPO 与长推理训练”的验收不接受三类替代品：把模拟输出写成真实 GPU 结果；只展示成功样本而隐藏失败与 `SKIPPED`；只给总分，不保存能复算总分的对象级记录。

## 3. 前置知识与实验边界

“PPO、GRPO、RLOO、DAPO 与长推理训练”的机制实验使用 Python 3.10 及以上版本和标准库，重点验证对象、算法或状态转换。真实硬件路径使用 PyTorch；检测不到 CUDA 时必须输出结构化 `SKIPPED`，不得静默改跑 CPU 后仍标成 GPU 实测。

算法仿真验证目标和采样语义，目标模型上的稳定性仍需真实 GPU、多种子和任务评测。

### 3.1 业务背景与失败模式

### 1.1 从一个可验证数学题开始

给定题目“某个数加七等于十九，这个数是多少”，策略模型生成八条不同推理。有些答案是十二，有些计算错，有些最终答案对但过程含无效文字，还有一条利用 Verifier 解析漏洞把多个数字都输出。系统最终得到每条响应的 Reward。

如果直接对高 Reward 响应做 SFT，数据分布由筛选决定，无法显式惩罚低 Reward 动作，也没有控制策略更新幅度。如果直接把 Reward 乘语言模型 Loss，正负号、基线、长度和 Old Policy 概率都没有处理，梯度方差极大。

策略梯度要回答：哪些已生成 Token 应提高概率，哪些应降低；提高多少；相对于生成它们的旧策略改变是否过大；同 Prompt 难度不同怎样归一；长短响应怎样公平；采样和训练不是同一引擎时概率是否可信。

### 1.2 为什么长推理比单步分类困难

奖励通常只在序列结束后获得，而动作是每一个 Token。将同一个结果 Reward 广播到所有 Token 是一种 Credit Assignment 近似：无法区分关键推理与无关铺垫。过程 Verifier 可以提供密集信号，但构建和防黑客更难。

序列概率是 Token 条件概率乘积，长度增加后数值趋近零，概率比更容易极端。工程实现使用 Logprob 差，再按 Token 或序列定义重要性比率。选择不同，优化几何和稳定性不同。

长响应还放大计算与内存。需要保存 Input、Response、Old Logprob、Reference Logprob、Reward、Advantage 和 Mask；若 PPO 使用 Critic 还要 Value 与 Return。一次 Rollout 可能被多个 Mini-batch 重复训练，数据年龄和 Policy Version 必须追踪。

### 1.3 本文的证据边界

数学部分推导目标与估计器；机制实验用小张量验证优势、Clip、KL、Mask 与长度聚合；真实硬件实验在本地 0.5B 到 1.5B 模型上跑短步可验证数学 GRPO 或等价教学路径，验证 CUDA、显存、Rollout 与更新数据流。

至少一张可用 CUDA GPU 不能证明大型集群吞吐，也不能用几十步宣称获得复杂推理能力。没有本地模型、CUDA 或依赖时输出 `skipped`。所有性能与 Reward 数字由运行产生，不预填。

### 3.2 学习目标与能力清单

### 2.1 策略梯度到底在优化什么

策略 $\pi_\theta(a_t\mid s_t)$ 在状态 $s_t$ 选择动作 $a_t$。语言模型里状态是 Prompt 与已生成前缀，动作是下一个 Token。目标是最大化期望累计回报：

$$J(\theta)=\mathbb{E}_{\tau\sim\pi_\theta}[R(\tau)]$$

REINFORCE 梯度为：

$$\nabla_\theta J(\theta)=\mathbb{E}\left[\sum_t \nabla_\theta\log\pi_\theta(a_t\mid s_t)\,G_t\right]$$

当 $G_t\gt 0$ 时，提高已采取动作概率；为负则降低。语言模型不会对所有可能响应求和，而从策略采样轨迹估计期望，因此样本方差和策略匹配成为核心。

### 2.2 为什么要减 Baseline

从 Return 减去只依赖状态、不依赖当前动作的 Baseline，不改变期望梯度，却可降低方差。优势函数：

$$A_t=Q(s_t,a_t)-V(s_t)$$

表达该动作相对当前状态平均表现好多少。PPO 用 Critic 估计 $V$；GRPO 用同 Prompt 组内响应 Reward 的均值与标准差；RLOO 用除当前响应外其他样本均值。三者主要差别之一就是 Baseline 从哪里来。

绝对 Reward 1 分在简单题可能低于平均，在困难题可能是最佳。按 Prompt 相对比较能消除部分题目难度尺度。但如果组内全部 Reward 相同，优势为零，没有更新信号。

### 2.3 为什么 Reward 不能直接跨任务比较

数学 Verifier 输出 0 或 1，代码任务可能按测试通过比例，开放回答 Judge 给 1 到 10，安全任务有惩罚。直接混合会让尺度大任务主导。Reward Recipe 需要分量、归一、权重和版本。

归一化可在任务、Prompt 组、Batch 或运行窗口执行。组归一适合 GRPO，却在低方差组放大噪声；全局归一受任务分布变化；固定标定便于复现但需要维护。不存在无条件最佳方案。

训练记录原始分量、组合 Reward 与用于优势的标准化值。只保存最终 Advantage 无法排查 Verifier 或归一变化。

### 2.4 Monte Carlo Return 与 Token Credit

结果监督把序列最终 Reward 作为每个 Response Token 的 Return。所有 Token 共享一个优势，区别只来自各 Token Logprob 与 Clip。实现简单、适合可验证最终答案，但无法指出哪步导致成功。

过程监督为中间 Step 提供 Reward 或 Value，能改善 Credit Assignment，却依赖可靠步骤切分与 Verifier。错误过程评分会把模型推向表面格式。长推理中常把结果监督作为基础，再用长度、格式或过程信号谨慎补充。

Prompt Token 通常 Mask，不参与策略 Loss；Response 有效 Token 参与。工具轨迹还要决定 Observation 与环境 Token 是否是策略动作。只有模型生成的 Action Token 应进入 Policy Gradient。

### 3.3 实验准备与责任边界

### 3.1 Actor Model

Actor 是正在优化的策略。它生成 Rollout，也在训练端计算 Current Logprob。同步系统中生成后立即更新；异步系统中 Rollout 可能由旧 Policy Version 产生，Experience 必须携带 Old Logprob 和版本。

Actor 既承担生成又承担反向，显存与并行需求不同。生成重 KV Cache 和吞吐，训练重激活、梯度与优化器。实际系统常用两套 Runtime 共享权重，这会引入训推不一致与同步成本。

### 3.2 Reference Model

Reference 通常是 SFT 初始策略的冻结副本，用于 KL 约束，防止 Actor 为追逐 Reward 过度偏离可读、通用和安全行为。每个 Response Token 计算 Reference Logprob。

Reference 不需要梯度，但仍占权重与前向计算。可以与 Actor 共置、量化、参数共享或离线缓存 Logprob；任何优化都要保证概率语义。Reference Version 固定在 Run Recipe，不能中途静默更换。

### 3.3 Critic Model

Critic 估计每个状态的 Value，为 PPO 提供优势和 Return。它可以与 Actor 共享骨干加 Value Head，也可以独立模型。共享省权重但梯度相互影响，独立更灵活但资源昂贵。

长文本 Critic 需要为每个 Token 输出 Value，激活和训练成本显著。Value 误差会增加优势噪声；还要处理 Bootstrap、终止、Padding 与 GAE。GRPO 去掉 Critic 正是大模型 RL 系统简化的重要动机。

### 3.4 Reward Model 或 Verifier

Reward Model 把 Prompt 与 Response 映射成偏好分数；Verifier 可执行检查答案、代码或环境状态。PPO 算法只需要数值 Reward，但工程可信度依赖信号来源。

模型 Reward 适合开放质量，可能被长度、风格和分布外响应欺骗；规则 Verifier 可重复，可能有解析漏洞。组合时保存每个分量、状态、超时和版本。基础设施错误不应默认记为答案错误。

### 3.5 四类模型怎样形成数据流

Actor 生成 Response 与 Old Logprob；Reward 组件计算序列或步骤 Reward；Reference 计算参考 Logprob；Critic 计算 Value；Experience Builder 结合 Mask、KL、Reward 与 GAE 产生 Advantage 和 Return；Trainer 分 Mini-batch 多 Epoch 更新 Actor 与 Critic。

每个阶段都必须使用同一 Token 序列与 Response Boundary。生成引擎若用不同 Tokenizer 或 Template，训练端重算 Old Logprob 就会错位。Experience 不是一段文本，而是一组按 Token 对齐的张量和版本关系。

## 4. PPO 的目标函数

### 4.1 重要性比率从哪里来

Rollout 由旧策略 $\pi_{old}$ 生成，更新时使用当前策略 $\pi_\theta$。对已采 Token 的重要性比率：

$$r_t(\theta)=\frac{\pi_\theta(a_t\mid s_t)}{\pi_{old}(a_t\mid s_t)} =\exp(\log\pi_\theta-\log\pi_{old})$$

若策略尚未更新，Ratio 接近 1。训练多 Epoch 后，正优势 Token 概率提高，Ratio 可能大于 1；负优势 Token 概率降低，Ratio 小于 1。极端 Ratio 意味着同一 Experience 在新策略下已不再近似 On-policy。

### 4.2 为什么要 Clip

PPO Clipped Objective：

$$L^{CLIP}=\mathbb{E}_t\left[\min\left(r_t A_t, \operatorname{clip}(r_t,1-\epsilon,1+\epsilon)A_t\right)\right]$$

对正优势，Ratio 超过 $1+\epsilon$ 后收益被截住，避免继续大幅提高；对负优势，Ratio 低于 $1-\epsilon$ 后不再奖励更大下降。Min 与优势符号共同决定非对称分支，不能把公式简化成“把 Ratio 裁剪后乘优势”而忽略原项。

Clip 不是硬性保证参数或 KL 在信任域内。不同 Token、参数共享和多次更新仍可能整体漂移。因此监控 Approx KL、Clip Fraction 和 Ratio 分布。

### 4.3 为什么正负优势的 Clip 行为不同

设 $A\gt 0$，希望提高动作概率。Ratio 从 1 上升时目标增加，到上界停止；Ratio 下降仍产生损失。设 $A\lt 0$，希望降低动作概率。Ratio 下降到下界后停止继续获益，Ratio 上升会加重损失。

面试中只背上下界容易答错。最可靠是代入正负数画分段函数。机制实验会对 Ratio 网格输出 Unclipped、Clipped 与最终 Min。

### 4.4 Value Loss 与 Entropy

PPO 通常同时优化 Value 回归，并可给策略增加 Entropy Bonus 鼓励探索。语言模型词表大，Token Entropy 尺度与传统连续动作不同；过高系数会损害确定推理，过低又可能快速坍缩。

Value 也可 Clip，防止 Critic 更新过大。总损失含 Policy、Value、Entropy 与可能 KL 项，各分量分别记录。只看总 Loss 无法判断策略是否因 Critic 主导。

## 5. GAE：怎样从 Value 得到优势

### 5.1 Temporal Difference Residual

一步 TD 误差：

$$\delta_t=r_t+\gamma V(s_{t+1})-V(s_t)$$

GAE 将未来 TD 误差按 $(\gamma\lambda)^l$ 加权：

$$A_t^{GAE}=\sum_{l=0}^{T-t-1}(\gamma\lambda)^l\delta_{t+l}$$

$\lambda$ 在低方差偏差与高方差 Monte Carlo 之间折中。语言模型结果 Reward 常在末尾，前面 Token 优势通过递推传播。

### 5.2 终止与截断怎样影响 Bootstrap

真正终止时下一状态 Value 通常为零；因最大长度截断不等于环境终止，是否 Bootstrap 取决于是否有可信下一状态。把过长截断当失败 Reward 或终止，会引入长度偏差。

Padding 位置不递推，Prompt 与 Response Boundary 明确。工具环境中的中间 Observation 可能继续 Episode，不能因一个生成 Chunk 结束就清零。

### 5.3 为什么 Critic 容易成为瓶颈

Critic 要与不断变化的 Actor 分布共同学习，Reward 稀疏、长序列 Value 目标噪声大。若 Value Explained Variance 低，优势近似高方差；若过拟合，可能压缩真实差异。

系统还要存 Value、Return 并训练额外参数。对每 Prompt 本来就生成多条响应的场景，可以利用组内比较代替状态 Value，这引出 GRPO。

## 6. GRPO：为什么可以去掉 Critic

### 6.1 组内相对优势

对同一个 Prompt 生成 $G$ 条响应，得到 Reward $R_1,\ldots,R_G$。GRPO 常用组均值与标准差标准化：

$$\hat A_i=\frac{R_i-\operatorname{mean}(R_1,\ldots,R_G)} {\operatorname{std}(R_1,\ldots,R_G)+\varepsilon}$$

同一响应的所有有效 Token 通常共享 $\hat A_i$。相对组平均更好的响应优势为正，更差为负。题目难度造成的 Reward 基线被组内消除，不需要训练 Token 级 Value Model。

去掉 Critic 减少一套权重、优化器、前向与训练，但并非“免费”。为了得到可靠组统计，每个 Prompt 必须生成多条响应，Rollout 成本增加；同组样本相关，组大小影响方差与有效 Batch。

### 6.2 为什么一定要同 Prompt 分组

若把不同 Prompt 的响应放在同一组，简单题高 Reward、难题低 Reward，优势主要学习题目难度而非同题策略差异。组键必须是逻辑 Prompt 或 Task Instance，而不是相同 Batch 位置。

Agent 环境还需固定初始状态、工具版本和随机条件。文本 Prompt 相同但环境不同，Reward 不可直接比较。Group ID 包含任务与环境实例。

分布式采样后同组响应可能散在 Worker，Experience Builder 需要正确 Gather。漏一条或重复一条会改变整组优势，必须有组完整性门禁。

### 6.3 组标准差为零会发生什么

若所有响应 Reward 相同，分子全零，优势全零；加 $\varepsilon$ 只防除零，不创造信号。全对与全错组都无法通过相对优势更新。

这不是数值 Bug，而是采样与任务难度问题。全错可能题太难、策略太弱或 Verifier 失败；全对可能题太易。Dynamic Sampling 会丢弃零方差组并补充有信息 Prompt，但必须记录生成成本与分布变化。

如果 Reward 是连续但微小噪声，标准差很小会放大不可靠差异。设置最低方差、使用不标准化中心化或稳健尺度，需通过消融选择。

### 6.4 组大小怎样影响估计

组越大，均值与方差更稳定、探索更多，但每 Prompt 生成成本线性上升，同一 Batch 覆盖 Prompt 数下降。小组覆盖题目多，却容易被单个异常 Reward 支配。

二元 Reward 下，组中既有成功又有失败才有信号。成功概率很低时，即使组八条也常全错；提高组大小、调整采样温度、使用难度课程或先 SFT 都可改善。

组大小还是系统参数，影响 Rollout 并发、KV Cache、Reward 吞吐、Experience Shard 与训练 Global Batch。报告不能只写 `G=8` 而不写 Prompt Batch 和总 Response。

### 6.5 GRPO 的 Policy Objective

## 写在最后

可验证奖励把 RL 从偏好代理推向环境与任务本身。下一篇：[RLVR、环境、拒绝采样与 Agentic 数据飞轮](/source/AI-Infra/5-数据工程与后训练/26-RLVR-环境-拒绝采样与Agentic数据飞轮)。