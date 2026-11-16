# 人类偏好、AI Feedback 与 On-policy 偏好数据

## 1. 本文要解决的工程问题

偏好数据只有 chosen 和 rejected 两列，标注者、候选策略、展示顺序、分歧和采样原因全部缺失。训练后无法判断模型是在学偏好还是学位置与长度。

本文围绕一个可执行判断展开：怎样组织人类偏好、AI Feedback 与 On-policy 数据并保存判断证据？读完应能给出自己的系统边界、输入输出、版本关系和验收证据，而不是只复述工具名称或公式。

![偏好数据生产与证据保留](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l22_01.png)

## 2. 本文交付物与判定标准

偏好对必须共享条件，不能比较不同 Prompt 的回答。

本文的核心决定是：保存候选生成策略、标注协议、判断主体、位置随机化、分歧、置信度和 On-policy 新鲜度。

完成学习和实验后，应当交付一份最小可复现记录，至少包含输入快照、配置、代码版本、运行状态、原始输出和结论边界。验收证据是：偏好集能按标注者、来源、位置、长度和策略版本做一致性与偏差分析。

围绕“人类偏好、AI Feedback 与 On-policy 偏好数据”的验收不接受三类替代品：把模拟输出写成真实 GPU 结果；只展示成功样本而隐藏失败与 `SKIPPED`；只给总分，不保存能复算总分的对象级记录。

## 3. 前置知识与实验边界

“人类偏好、AI Feedback 与 On-policy 偏好数据”的机制实验使用 Python 3.10 及以上版本和标准库，重点验证对象、算法或状态转换。真实硬件路径使用 PyTorch；检测不到 CUDA 时必须输出结构化 `SKIPPED`，不得静默改跑 CPU 后仍标成 GPU 实测。

偏好标签表达指定协议下的相对选择，不等于事实真值或普遍价值判断。

### 3.1 业务背景与失败模式

偏好数据表达在给定上下文和评价标准下，响应 A 相对响应 B 更符合目标。它可能来自人类选择、AI Judge、规则、执行器、用户行为或这些信号的组合。一个偏好标签不能脱离提示、候选、展示顺序、标注指南、标注者或 Judge 版本来理解；同一对响应在帮助性、安全、简洁、事实和风格维度上可能得到不同结论。

离线偏好来自固定策略或历史模型生成，便于复用但可能与当前策略分布错位。On-policy 偏好由当前或接近当前策略实时生成，更贴近模型正在犯的错误，却增加生成成本、版本同步、去重、标注延迟和分布漂移。工程目标不是收集最多“chosen/rejected”，而是建立可校准、可追溯、能覆盖真实决策边界且与训练策略版本匹配的比较数据产品。

### 3.2 Prompt

Prompt 包含系统约束、用户请求、工具状态、对话历史和风险标签。偏好对必须共享相同决策上下文，否则比较混入输入差异。

### 3.3 Candidate

候选保存生成策略、权重摘要、解码参数、随机种子、完成原因和工具轨迹。只有文本不同不足以解释偏好来源。

### 3.4 Comparison

Comparison 引用两个或多个候选，记录展示顺序、评价维度、标签、强度、平局、拒判和理由。不要把平局强制变成随机胜负。

### 3.5 Annotation

人类标注包含标注者匿名身份、资质、时间、指南版本、耗时与置信；AI Feedback 包含 Judge 模型、提示、顺序、解析和校准。二者都不是无误真值。

### 3.6 Preference Release

发布冻结 Prompt、候选、比较、聚合、Schema、来源、污染、质量、权利和采样权重。训练只能消费不可变发布。

### 3.7 标注指南

把帮助、正确、相关、安全、简洁、证据和风格拆成可观察标准，提供边界例和不可判定条件。指南升级产生新版本，旧新标签不能无标记混合。

### 3.8 标注者选择

通用表达可由训练良好的普通标注者处理，医学、法律、安全和代码执行需要专家或工具证据。身份最小化保存，同时保留资质与一致性统计。

### 3.9 盲化与随机顺序

隐藏模型名称、供应商与训练方法，随机 A/B 顺序，必要时双向展示。位置偏差应被测量，不能只假设随机化完全消除。

### 3.10 平局与拒判

强行拆开平局会制造标签噪声。

两个候选同样好、同样坏或证据不足时允许平局与拒判。强制二选一制造虚假梯度。训练算法若不接受平局，可在发布转换时明确丢弃或转为弱标签。

### 3.11 多标与仲裁

高风险或难例使用多人独立标注，分歧进入仲裁。保留原始标签，不用最终多数票覆盖不确定性。分歧率可揭示指南与任务问题。

## 4. AI Feedback

### 4.1 Constitutional 原则

用明确原则让模型批判和修订，再对候选比较。原则版本和冲突处理必须记录；原则不是自然法，需要产品、安全与治理共同定义。

### 4.2 Pointwise 与 Pairwise

绝对评分便于缓存与多候选排序，但标尺漂移；成对比较更容易判断相对优劣，却受顺序与配对分布影响。两者可组合校准。

### 4.3 Judge 偏差

常见偏差包括位置、长度、自偏好、风格、引用、语言和权威语气。使用 AB/BA、金标、跨家族 Judge、执行证据与人工审计。

### 4.4 AI Feedback 的边界

更强模型也需要位置与长度偏差审计。

它扩展规模和一致性，不能替代真实用户价值、专家事实和严重安全判断。多个相关 Judge 一致也可能共同错误。

## 5. On-policy 偏好

旧候选分布不一定覆盖新策略的失败模式。

### 5.1 为什么需要 On-policy

策略更新后输出分布变化，旧偏好可能只覆盖早期显著错误。当前策略生成的候选更接近决策边界，提供可学习比较。

### 5.2 近策略与严格当前策略

严格 On-policy 要求生成策略与训练当前权重一致，系统同步昂贵；近策略允许一定版本滞后，需记录 Policy Lag 并设置上限。不能把数周旧模型输出称为当前策略。

### 5.3 Prompt 采样

来自真实受治理流量、能力图、红队、环境任务和历史失败。按风险、难度和覆盖采样，线上原文不自动进入训练。

### 5.4 候选生成

同一 Prompt 从当前策略采多个响应，控制温度与长度。候选太相似无法形成信号，差异太大又可能成为容易负例。目标是有意义边界。

### 5.5 标注延迟

生成、Judge 与人工需要时间，标签完成时策略已变化。发布绑定生成策略水位和标注时间，训练器控制可接受滞后。

## 6. 偏好质量

### 6.1 可判定性

上下文充分、评价维度明确，候选差异能够比较。不可判定数据不应被随机标签填满。

### 6.2 标签一致性

通过重复对、顺序交换、金标和多标估计。高一致不一定正确，标注者可能共享指南偏差。

### 6.3 难度

偏好差距过大是易对，过小是难对。训练需要课程与边界，难对同时更容易噪声。保存强度和分歧。

### 6.4 长度控制

对照需要长度切片，不能把冗长偏好当作质量偏好。

若 chosen 总更长，模型可能学习长度而非质量。匹配长度、加入短优长劣对、使用分项指南并审计相关性。

### 6.5 去重与来源上限

同一 Prompt、候选、模板或父事实重复会放大偏好。按 Prompt 簇、响应簇和生成策略设置曝光上限。

## 7. CPU 机制实验：位置偏差与聚合

### 随包实验的运行入口与边界

本文可直接运行的入口在实验包的 `lessons/lesson-22/`。正文中的生产架构、建议目录和框架示例用于解释机制与扩展设计，不代表这些生产系统已经随包实现。所有原有代码围栏另存于该目录的 `examples/`，文件以 `.txt` 结尾，便于逐字对照。

```bash
python lessons/lesson-22/run.py
python lessons/lesson-22/run_gpu.py
```

第一条命令读取固定反例并输出机制检查。第二条只运行单进程 CUDA 基础探针，不是本文完整数据平台或训练算法；没有 CUDA 时输出 `skipped`。通过探针不能证明 DDP、模型质量、集群吞吐或端到端恢复。真实系统扩展需要另外实现正文所列模块，并在自己的模型、数据和硬件上验收。

完整入口脚本保存在实验包同名文件中；阅读时从入口追到共享机制函数，再对照 fixture 与结果检查项。

![位置偏差与双向聚合](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l22_02.png)

位置偏差会让“先出现”悄悄替代“更好”。机制实验因此同时交换 A/B 顺序、保留冲突样本，并把聚合规则写入版本化记录。

真实偏好应在映射回候选身份后保持一致。

### 7.1 目标

模拟真实质量、标注噪声和位置偏差，比较单向标注与 AB/BA 双向聚合，输出准确、平局和冲突。它只说明偏差控制机制。

```python
import json
import random

def judge(a_quality, b_quality, a_first, rng):
    gap = a_quality - b_quality
    position = 0.16 if a_first else -0.16
    noisy = gap + position + rng.gauss(0, 0.18)
    if abs(noisy) < 0.08:
        return "tie"
    return "a" if noisy > 0 else "b"

def main():
    rng = random.Random(20260822)
    single_correct = 0
    double_correct = 0
    conflicts = 0
    usable = 0
    rows = []
    for index in range(500):
        qa, qb = rng.random(), rng.random()
        truth = "a" if qa > qb else "b"
        first = judge(qa, qb, True, rng)
        swapped_raw = judge(qb, qa, True, rng)
        swapped = "b" if swapped_raw == "a" else "a" if swapped_raw == "b" else "tie"
        single_correct += first == truth
        if first == swapped and first != "tie":
            aggregate = first
        else:
            aggregate = "reject"
            conflicts += 1
        if aggregate != "reject":
            usable += 1
            double_correct += aggregate == truth
        if index < 5:
            rows.append({"qa": qa, "qb": qb, "truth": truth,
                         "ab": first, "ba_normalized": swapped, "aggregate": aggregate})
    print(json.dumps({
        "status": "passed",
        "claim_boundary": "synthetic position-bias aggregation only",
        "single_accuracy": single_correct / 500,
        "double_coverage": usable / 500,
        "double_accuracy_on_accepted": double_correct / max(1, usable),
        "conflicts_or_ties": conflicts,
        "examples": rows,
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

### 7.2 解释

双向一致聚合通常提高已接受标签准确率，但降低覆盖并增加一倍 Judge 成本。真实系统要在精确、召回、风险和成本间选择，冲突进入人工或更强验证，不能默认多数。

## 8. 通用 CUDA 近策略数据路径

### 8.1 目标与边界

一个或多个 Rank 使用同一策略快照生成合成候选摘要，并运行小型成对分类器训练，校验生成策略 ID、Token 守恒和本地 CUDA 聚合。没有至少一张 CUDA GPU 输出 `skipped`。该实验不证明真实偏好质量。

```python
import json
import os

try:
    import torch
    import torch.distributed as dist
    from torch import nn
except Exception as exc:
    print(json.dumps({"status": "skipped", "reason": f"torch unavailable: {exc}"}))
    raise SystemExit(0)

def skip(reason):
    print(json.dumps({"status": "skipped", "reason": reason}))
    raise SystemExit(0)

def main():
    if not torch.cuda.is_available(): skip("CUDA unavailable")
    if torch.cuda.device_count() < 1: skip(f"requires at least one CUDA device, found {torch.cuda.device_count()}")
    if int(os.environ.get("WORLD_SIZE", "1")) < 1: skip("launch with torchrun --nproc_per_node=1")
    dist.init_process_group("nccl")
    rank = dist.get_rank(); local = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local); device = torch.device("cuda", local)
    torch.manual_seed(20260822)
    model = nn.parallel.DistributedDataParallel(nn.Sequential(
        nn.Linear(32, 64), nn.GELU(), nn.Linear(64, 1)).to(device), device_ids=[local])
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3)
    counter = torch.zeros(2, dtype=torch.long, device=device)
    policy_version = "policy-canary-step-0000"
    try:
        for step in range(120):
            g = torch.Generator(device=device); g.manual_seed(rank * 100000 + step)
            chosen = torch.randn(8, 32, generator=g, device=device) + 0.18
            rejected = torch.randn(8, 32, generator=g, device=device) - 0.18
            margin = model(chosen).squeeze(-1) - model(rejected).squeeze(-1)
            loss = -torch.nn.functional.logsigmoid(margin).mean()
            opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
            counter += torch.tensor([chosen.shape[0], chosen.numel() + rejected.numel()], device=device)
        dist.all_reduce(counter)
        if rank == 0:
            print(json.dumps({"status": "passed", "policy_version": policy_version,
                              "pairs": int(counter[0]), "feature_values": int(counter[1]),
                              "peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
                              "claim_boundary": "synthetic two-GPU pairwise control path only"}))
    except torch.cuda.OutOfMemoryError as exc:
        if rank == 0: print(json.dumps({"status": "skipped", "reason": f"CUDA OOM: {exc}"}))
    finally:
        dist.destroy_process_group()

if __name__ == "__main__": main()
```

### 8.2 真实替换

替换为许可明确的小策略模型、冻结 Prompt 发布、同一策略多采样和真实 Judge 或人工标签。记录 Policy 摘要、生成水位、标注延迟、实际 Token、平局和拒判。本地 CUDA 资源只适合小模型或参数高效 Canary，生产结论必须目标尺度验证。

## 9. 八十个偏好数据控制点

### 9.1 Prompt 先过治理

线上、文档与红队 Prompt 都要确认来源、同意、隐私、许可和风险。用户请求不能因为去掉姓名就自动训练。

### 9.2 Prompt 绑定时间

事实、工具和策略随版本变化，记录内容时间与采集时间。过期 Prompt 可用于历史测试，但不冒充当前分布。

### 9.3 Prompt 按能力分层

随机按单条比较切分容易泄漏相同问题。

帮助、事实、推理、工具、安全、风格和无答案分别覆盖。只随机抽热门请求会忽略低频高风险边界。

### 9.4 Prompt 去重

精确、语义、模板和父事件共同控制。重复 Prompt 会放大某类偏好并虚增标注一致性。

### 9.5 候选共享上下文

成对响应必须看到相同系统、历史、工具和证据。上下文不同会把输入质量混入响应偏好。

### 9.6 候选身份完整

策略权重、服务版本、解码、Seed、完成原因和工具版本可追踪。模型名称不是不可变身份。

### 9.7 解码差异显式

## 写在最后

偏好数据要变成训练信号，先需要一个可靠的奖励模型。下一篇：[Reward Model、Process Reward 与奖励可靠性](/source/AI-Infra/5-数据工程与后训练/23-RewardModel-ProcessReward与奖励可靠性)。