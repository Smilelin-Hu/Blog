# 合成数据、偏好数据与 Reward Model 工厂

![合成数据、偏好数据与 Reward Model 工厂](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l34_01.png)

## 1. 项目目标

基于真实消费关系定位，不仅按运行日期估计。

项目构建从任务种子、Teacher 生成、验证与修订，到偏好标注、Judge、Reward Model、红队和策略回流的完整数据工厂。目标不是制造尽可能多的“高分答案”，而是生产来源可追踪、偏好语义明确、评分可校准、漏洞可回放、版本可撤销的监督信号。

CPU 机制实验模拟成对偏好、Judge 偏差、Reward 校准和选择偏差。真实路径可以在至少一张可用 CUDA GPU 上用小模型完成 LoRA Teacher 生成、Reward Model 微调和切片评估。缺少模型、CUDA 或许可清晰数据时输出 `skipped`。自动 Judge 与小规模人工标注只能支持受限实验，不能声称替代真实用户偏好或完成全场景安全认证。

## 2. 输入与数据对象

输入包括任务种子 Release、能力与风险标签、Teacher 与采样版本、生成预算、Verifier、修订策略、标注规范、Judge 版本、偏好聚合规则、Reward 架构、训练配方和评测集。所有 Prompt 模板、系统消息、停止条件和工具环境都属于版本合同。

核心对象为 Task、Candidate Response、Verification、Critique、Revision、Preference Annotation、Preference Aggregate、Reward Score、Red-team Case 和 Policy Feedback。Candidate 绑定 Task、Policy、Runtime、采样参数和 Token 级证据；Annotation 绑定标注者类型、盲化信息、位置随机、理由和置信度；Aggregate 保存原始票据与聚合方法，不能覆盖个人判断。

偏好标签要区分“整体更好”“满足硬约束”“更安全”“风格更合适”“事实更准确”和“不可比较”。把所有信号压成 Chosen/Rejected 会失去冲突结构。Reward 可以针对不同目标使用多头、规则门禁或向量信号；最终标量组合版本化并接受独立红队。

## 3. 总体架构

Task Composer 从真实需求、失败样本与能力网格生成任务。Candidate Generator 按多策略、多温度产生候选。Verifier 执行规则、单元测试、沙箱、检索证据和格式检查。Critique/Revision 阶段生成可追踪修订。Annotation Router 把难例送给人类、AI Judge 或混合流程。Aggregator 处理一致率、平局和不确定性。Reward Trainer 训练与校准模型。Adversarial Evaluator 搜索 Reward 漏洞。Release Gate 发布偏好与 Reward 版本。

每一步都保留来源与版本，不把 Teacher 输出当真值。

数据面与评分面必须隔离。Judge 看不到候选来自哪个策略、训练轮次或预期答案位置；A/B 顺序随机且记录。Reward 服务不在原地更新，同一请求可以保存多个版本评分。策略训练消费的 Reward 版本进入 Experience 与 Checkpoint 清单，使漏洞发现后能计算污染范围。

## 4. 目录与 Schema

```text
feedback_factory/
  catalogs/tasks.yaml
  prompts/generator/
  prompts/judge/
  schemas/task.json
  schemas/candidate.json
  schemas/preference.json
  schemas/reward_score.json
  src/generate.py
  src/verify.py
  src/annotate.py
  src/aggregate.py
  src/train_reward.py
  src/evaluate_reward.py
  src/release.py
  tests/position_bias/
  tests/reward_hacking/
  artifacts/cards/
```

偏好记录至少包含 `comparison_id`、任务版本、候选 A/B 身份、展示顺序、标注者或 Judge 版本、判定、目标维度、理由、置信、时间和质检状态。Reward 分数包含模型版本、输入模板、截断、标量与各头分数、校准版本和异常标记。合成样本保存父任务、Teacher、采样、Verifier、Critique 和 Revision 谱系。

## 5. 任务与候选生成

任务来源分为真实脱敏请求、能力模板、失败回流、对抗变体和课程扩展。模板生成必须防止槽位组合产生无意义任务；真实回流必须满足隐私和许可。任务去重使用文本、语义和结构视图，并与评测集做去污染。

每个 Task 生成多个候选时，策略、温度、Top-p 和随机种子形成实验设计。不能只让强 Teacher 生成 Chosen、弱模型生成 Rejected，否则 Reward 学到风格与模型身份。加入同策略不同采样、强弱交叉、人工修订和硬负例，使偏好差异覆盖事实、推理、安全、格式与细微质量。

生成失败、超时、拒答和工具故障分别记录。环境失败不能自动成为 Rejected；空输出也不能只因长度短就赋极低分，除非任务合同要求回答。候选进入标注前先过 Schema、PII 与安全隔离。

## 6. 验证、批评与修订

各证据有边界，不能把多个弱检查相加视为绝对正确。

可执行任务使用单元测试、编译器、数学解析或环境回报；知识任务保存检索证据与引用检查；格式任务用确定性解析器。Verifier 输出证据、错误类别和版本，而不仅是通过分数。对于可能被策略利用的测试，维护隐藏集、变形测试和对抗样本。

Critique 指出具体缺陷，Revision 绑定父候选与修改证据。若修订由同一个 Teacher 自评，需警惕自洽偏差；可用独立 Verifier 或不同 Judge 交叉。修订后重新执行全部硬约束，不能因文本看起来更好就继承父样本通过状态。

## 7. 偏好标注与质量控制

标注指南提供维度定义、不可比较、平局、拒答、安全冲突和工具证据示例。展示顺序随机，候选长度和模型身份尽量盲化。部分重复金标测稳定性，部分 A/B 翻转测位置偏差，部分同答案对测虚假偏好。低一致样本进入复审而不是强行多数票。

AI Feedback 需要记录 Judge Prompt、模型、采样、上下文截断和解析器。Judge 与 Teacher 尽量避免同源，并在人工锚点上按任务、语言、长度、安全和难度校准。总体一致率高仍可能在关键切片失败，尤其是长推理、少数语言与高风险拒答。

主动选择优先标注 Reward 不确定、模型分歧、边界样本和高业务价值任务，但要保留随机样本估计真实分布。只标注难例会改变训练先验；数据集中保存选择概率或批次策略，评测集保持独立代表性。

## 8. CPU 机制实验：位置偏差与校准

### 随包实验的运行入口与边界

本文可直接运行的入口在实验包的 `projects/project-04/`。正文中的生产架构、建议目录和框架示例用于解释机制与扩展设计，不代表这些生产系统已经随包实现。所有原有代码围栏另存于该目录的 `examples/`，文件以 `.txt` 结尾，便于逐字对照。

```bash
python projects/project-04/run.py
python projects/project-04/run_gpu.py
```

第一条命令读取固定反例并输出机制检查。第二条只运行单进程 CUDA 基础探针，不是本文完整数据平台或训练算法；没有 CUDA 时输出 `skipped`。通过探针不能证明 DDP、模型质量、集群吞吐或端到端恢复。真实系统扩展需要另外实现正文所列模块，并在自己的模型、数据和硬件上验收。

完整入口脚本保存在实验包同名文件中；阅读时从入口追到共享机制函数，再对照 fixture 与结果检查项。

映射回身份后不一致说明需要调查位置偏差。

```python
import json
import math
import random

rng = random.Random(13)
examples = []
for index in range(400):
    true_gap = rng.gauss(0, 1)
    a_first = rng.random() < 0.5
    position_bias = 0.35 if a_first else -0.35
    judge_logit = true_gap + position_bias + rng.gauss(0, 0.45)
    prediction = 1 if judge_logit > 0 else 0
    truth = 1 if true_gap > 0 else 0
    examples.append({"a_first": a_first, "prediction": prediction, "truth": truth, "confidence": 1 / (1 + math.exp(-abs(judge_logit)))})

def accuracy(rows):
    return sum(x["prediction"] == x["truth"] for x in rows) / len(rows)

def expected_calibration_error(rows, bins=5):
    error = 0.0
    for bucket in range(bins):
        low, high = bucket / bins, (bucket + 1) / bins
        part = [x for x in rows if low <= x["confidence"] < high or (bucket == bins - 1 and x["confidence"] == 1)]
        if not part:
            continue
        confidence = sum(x["confidence"] for x in part) / len(part)
        correct = sum(x["prediction"] == x["truth"] for x in part) / len(part)
        error += len(part) / len(rows) * abs(confidence - correct)
    return error

report = {
    "overall_accuracy": accuracy(examples),
    "a_first_accuracy": accuracy([x for x in examples if x["a_first"]]),
    "b_first_accuracy": accuracy([x for x in examples if not x["a_first"]]),
    "position_preference_gap": sum(x["prediction"] for x in examples if x["a_first"]) / sum(x["a_first"] for x in examples)
    - sum(x["prediction"] for x in examples if not x["a_first"]) / sum(not x["a_first"] for x in examples),
    "ece": expected_calibration_error(examples),
}
print(json.dumps(report, indent=2))
```

实验展示总体准确率不能揭示位置偏差，校准也要单独测。扩展实验可加入长度偏差、任务切片、三标注者聚合和主动选择，比较原始分布与选择后分布。生产结论需要人工锚点，不应把模拟真值当真实偏好。

## 9. Reward Model 训练

分数尺度变化会影响下游策略优化。

数据切分以 Task 族、来源和时间为单位，避免同一任务改写跨训练与验证。Pairwise 目标、Listwise 目标或多头分类要与数据语义一致。长度、格式和模型风格是常见捷径，训练前做对照统计，评测加入内容相同但长度、顺序和措辞变化的反事实对。

训练保存 Reference 模板、Tokenizer、截断、最大长度、Loss、采样权重和随机状态。若偏好数据来自主动选择，评估真实分布时不能沿用选择分布。多目标 Reward 先分别校准，再由策略层显式组合；安全硬门槛不要被高帮助性分数抵消。

Reward 输出需要校准。对 Pairwise 看准确率、AUC、平局与置信；对标量看可靠性曲线和分位。分布外评测覆盖新策略、新任务、长响应、少数语言、拒答、工具轨迹和对抗样本。高平均准确率不足以发布。

## 10. 真实硬件路径

至少一张可用 CUDA GPU 可使用小型 Encoder 或 Decoder Reward Model，采用 fp16、梯度检查点和 LoRA。生成与训练分阶段运行以减少显存竞争。依赖探测：

```python
import json
import os

try:
    import torch
    gpus = torch.cuda.device_count()
    memory = [round(torch.cuda.get_device_properties(i).total_memory / 1024 ** 3, 1) for i in range(gpus)]
    checks = {"cuda": torch.cuda.is_available(), "gpus": gpus, "memory_gib": memory, "teacher": bool(os.environ.get("TEACHER_MODEL")), "reward": bool(os.environ.get("REWARD_BASE_MODEL"))}
except Exception as exc:
    checks = {"cuda": False, "error": type(exc).__name__}
ready = checks.get("cuda") and checks.get("gpus", 0) >= 1 and checks.get("teacher") and checks.get("reward")
print(json.dumps({"status": "ready" if ready else "skipped", "reason": None if ready else "gpu_or_model_unavailable", "checks": checks}))
```

真实实验固定任务 Release，生成至少两个策略来源的候选，随机翻转位置并建立少量人工锚点。训练前跑未训练基座与简单长度规则基线；训练后按来源、长度、难度和安全切片比较。再让策略或搜索器最大化 Reward，人工审查 Top 尾部是否出现 Hacking。所有结果绑定模型许可、硬件、软件和样本范围。

## 11. 红队与反馈闭环

保留失败样本用于防回归，避免只调低奖励上限。

Reward 红队包括长度填充、关键词注入、格式伪装、引用捏造、测试过拟合、拒答模板、Unicode 和工具结果伪造。搜索不只看最高 Reward，还看 Reward 与独立 Verifier、人类和终局结果的分歧。发现漏洞后冻结版本、保存攻击样本、追踪已训练 Checkpoint、修复并重放，而不是覆盖原分数。

策略回流采用 Candidate 状态机：新 Policy 先在固定任务与隐藏红队上生成，结果进入与历史相同的版本合同；只有通过门槛才扩大采样。在线新数据按 Policy 版本分桶，避免把旧离线偏好与新 On-policy 偏好无标记混合。主动学习预算按风险、不确定性和覆盖分配。

## 12. 指标与验收

指标包括候选生成成功与独特率、Verifier 通过与错误分布、修订提升率、标注一致率、平局率、位置偏差、长度偏差、Judge 对人工准确率、校准误差、Reward 域内与 OOD 准确率、高分尾部错误、红队攻击成功、偏好来源覆盖和每个合格 Pair 成本。

验收要求任一 Preference 能追到 Task、两个候选、生成合同、原始标注与聚合；任一 Reward 分数能按版本重算；训练 Checkpoint 能反查偏好 Release；位置翻转测试与同答案测试通过阈值；OOD 和安全切片满足红线；发现漏洞后能在规定时间内阻断新消费并导出影响。

总体准确率无法排除特定切片失效。

## 13. 演示、排障与交付

演示从十个任务种子生成多候选，执行 Verifier、Critique 和 Revision，随机盲化形成偏好，训练小 Reward 并展示校准与切片。然后运行一个奖励攻击，让高分错误暴露，冻结版本、重算影响并发布修复版本。这个负向演示比单纯展示准确率更能证明工厂可运营。

一致率下降时按标注者、Judge、任务、长度与展示顺序切片；Reward 训练 Loss 下降而 OOD 变差时检查来源捷径、切分泄漏和主动选择偏差；Top Reward 质量差时检查 Verifier 漏洞与标量组合；修订退化时核对父子版本和是否继承了过期通过状态。

最终交付任务与偏好 Schema、生成与 Judge Prompt 版本、Verifier、标注指南、聚合器、CPU 实验、真实训练配置、Reward Checkpoint、校准与 OOD 报告、红队语料、事故 Runbook、成本账本和数据卡。成功标准是监督信号可以被解释、质疑、重算和撤回，而不是仅有一个不断增长的 Pair 数量。

## 14. 生产评审十二问

### 14.1 Teacher 是否支配风格

比较不同 Teacher、同 Teacher 不同采样、人工修订和真实响应的措辞与长度。若 Chosen 几乎总来自同一模型，Reward 可能识别模型指纹。通过交叉生成、盲化和风格反事实降低捷径，并在新策略上做 OOD 评测。

### 14.2 Judge 是否知道答案位置

随机翻转 A/B 并保存展示顺序，测同一 Pair 翻转一致性和第一位置偏好。Prompt 解析不能把 Chosen 放入固定字段名。位置偏差超过阈值时，校准、双向判断或更换 Judge，不能用总体准确率掩盖。

### 14.3 平局是否被强行拆开

质量接近或维度冲突的候选允许平局与不可比较。强行二选一会给 Reward 注入随机噪声，并把标注者偏好风格放大。聚合器保存不确定性，训练可降权、使用软标签或排除，但保留原始票据。

### 14.4 Verifier 是否可被利用

奖励器应在进入策略优化前完成独立验收。

对通过样本运行变形测试、隐藏测试和人工 Top 尾部审计。若策略能通过关键词、格式空洞或测试泄漏获得高分，冻结版本并追踪历史消费。修复后发布新 Verifier，原评分不覆盖，便于计算污染范围。

### 14.5 Reward 是否依赖长度

画分数与长度、格式、拒答模板和模型来源的关系，构造内容相同但冗余、截断或重排的反事实对。相关不一定代表错误，但必须由任务语义解释。策略搜索后长度暴涨是重要 Hacking 信号。

### 14.6 人工锚点是否代表真实分布

锚点覆盖语言、任务、难度、安全、长响应和新策略，而不只包含容易标注的短 Pair。主动选择数据与随机代表性样本分开，前者发现边界，后者估计真实误差。两者不能混成一个总体准确率。

### 14.7 Reward 升级能否回放

给定旧 Preference Release，新 Reward 可批量重算并输出新分数资产；原分数、模型和校准保留。比较新旧分数翻转、尺度、切片和 Top 尾部，训练清单明确使用哪一版。升级不能直接替换在线列值。

### 14.8 主动学习是否形成反馈偏差

高不确定样本被更多标注后，训练分布与线上分布不同。保存选择概率、批次策略和未选择池统计，评测仍用独立代表集。必要时做重要性权重或分层采样，但监控方差，不能默认主动样本就是自然频率。

### 14.9 安全是否被标量抵消

帮助性、事实和安全若简单相加，高帮助分可能抵消严重越权。高风险约束使用硬门禁或分层决策，报告各头与最终动作。组合权重版本化并经过红队，不能由在线团队临时调高总分阈值。

### 14.10 策略迭代后 Reward 是否过期

新 Policy 会访问旧训练分布之外的响应。每轮 Canary 测 Reward 与人工、Verifier 和独立 Judge 分歧，Top Reward 尾部重点抽样。漂移超过阈值时收紧训练、补充 On-policy 偏好或升级 Reward，而非继续依赖域内验证分数。

### 14.11 删除请求怎样传播

从 Task 或候选的来源身份定位 Preference、Reward 训练 Release、Checkpoint 和策略 Run。未来消费立即阻断，模型层影响进入治理。合成与修订样本不能因为文本变化就切断父来源，所有代际关系必须保留。

### 14.12 工厂吞吐是否有价值

每小时生成 Pair 很高但独特性、标注一致、Verifier 通过或 OOD 质量低，不是有效吞吐。核心成本分母应是通过版本、偏差、安全和可追溯门禁的合格偏好信号，并最终关联策略质量门槛，而不是原始生成数量。

## 写在最后

数据与奖励生产线就绪后，训练流水线本身也要能按显存缩放。下一篇：[可按显存缩放的 SFT 到 DPO 到 GRPO/RLVR 流水线](/source/AI-Infra/5-数据工程与后训练/35-可按显存缩放的SFT到DPO到GRPORLVR流水线)。