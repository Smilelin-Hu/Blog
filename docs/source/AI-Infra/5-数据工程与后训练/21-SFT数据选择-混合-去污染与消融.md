# SFT 数据选择、混合、去污染与消融

## 1. 本文要解决的工程问题

SFT 配方加入一批高分样本后总分上升，但样本更长、任务更容易，实际 Token 预算和评测分布都变了。

本文围绕一个可执行判断展开：怎样用选择、混合、去污染和消融证明一份 SFT 配方的边际价值？读完应能给出自己的系统边界、输入输出、版本关系和验收证据，而不是只复述工具名称或公式。

![SFT 数据选择与消融](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l21_01.png)

## 2. 本文交付物与判定标准

本文的核心决定是：用固定 Token 预算、能力切片和逐步消融评估选择与混合策略，先证明边际价值再扩大数据量。

完成学习和实验后，应当交付一份最小可复现记录，至少包含输入快照、配置、代码版本、运行状态、原始输出和结论边界。验收证据是：基线与候选共享起始模型、优化配置和评测集，报告每个数据桶的加入、移除与交互影响。

围绕“SFT 数据选择、混合、去污染与消融”的验收不接受三类替代品：把模拟输出写成真实 GPU 结果；只展示成功样本而隐藏失败与 `SKIPPED`；只给总分，不保存能复算总分的对象级记录。

## 3. 前置知识与实验边界

“SFT 数据选择、混合、去污染与消融”的机制实验使用 Python 3.10 及以上版本和标准库，重点验证对象、算法或状态转换。真实硬件路径使用 PyTorch；检测不到 CUDA 时必须输出结构化 `SKIPPED`，不得静默改跑 CPU 后仍标成 GPU 实测。

消融解释当前模型和预算下的边际变化，不自动外推到更大模型或更长训练。

### 3.1 业务背景与失败模式

SFT 用有限监督 Token 塑造行为，样本的边际价值、冲突和顺序比原始规模更敏感。开放数据、人工数据、合成数据、领域数据与安全数据使用不同 Schema、质量标准和权利边界；直接拼接会让长响应、模板、重复任务或大来源支配梯度。模型可能在总 Loss 下降的同时变得啰嗦、过度拒答、遗忘通用任务或记住评测答案。

选择系统回答“哪些样本值得进入候选集”，混合系统回答“各类样本以多少监督 Token 出现”，去污染系统保护评测独立性，消融系统回答“收益究竟来自哪一类数据与哪种处理”。四者必须共用不可变发布、实际 Token 账本和冻结评测。否则高分只能说明一个不可复现组合看起来有效，不能指导下一轮。

### 3.2 正确性

事实、推理、代码、工具和安全决策满足指定验证器。正确是基础硬门槛，但开放任务的正确边界可能需要人工和多证据。

### 3.3 相关性

样本是否覆盖目标产品任务与真实失败。与主题相关却学生已完全掌握的样本，边际价值可能很低。

### 3.4 可学习性

样本难度处于学生可吸收范围，监督明确，Template 和 Loss Mask 正确。不可解或过难样本可能只增加噪声。

### 3.5 独特性

相对已选集合是否提供新意图、事实、策略、语言、风险边界或长度。表面措辞差异不等于独特训练信号。

### 3.6 风险

包括许可、隐私、安全、偏见、污染、记忆和错误标签。严重风险不可由高任务价值补偿。

### 3.7 成本

不仅是存储，还包括 Token 训练、长序列效率、验证、人工、评测和模型分支维护。选择目标是单位成本的联合收益。

### 3.8 硬过滤

删除权利不清、秘密、无法解析、明显错误、超限、污染和 Schema 不兼容样本。硬过滤有版本和拒绝原因，不把风险转化为连续质量分。

### 3.9 质量排序

在合规候选中用规则、执行、Judge、人工和学生信号排序。分数只在同一量表范围内可比较，跨任务需校准。

### 3.10 覆盖约束

总体质量上升不能掩盖关键能力样本归零。

为能力、语言、难度、安全边界、工具和长度设置最低覆盖与来源上限，避免 Top-K 收缩到易题和高频模板。

### 3.11 核心集选择

通过聚类、设施位置、梯度或表示选择较小代表集。复杂方法必须与分层随机和简单去重基线比较，并保存选择版本。

### 3.12 主动选择

根据目标学生的不确定、错误、损失或梯度挑选样本。信号依学生版本，不是数据永久属性；需防止只选择噪声难例。

## 4. 混合不是文件比例

### 4.1 样本比例

实现简单，却受响应长度影响。相同条数的短分类与长轨迹贡献完全不同监督 Token。

### 4.2 Token 比例

更接近梯度预算，应在 Template、截断、Packing 和 Loss Mask 后计算非 Padding 监督 Token。计划与训练实际都要记录。

### 4.3 来源与能力双层采样

先选能力桶，再选来源与样本，可以同时控制产品覆盖和单来源集中。层次权重必须转换为最终概率并验证。

### 4.4 静态与课程混合

静态混合全程固定，课程随 Token 水位改变难度、领域或安全比例。课程收益需与相同总 Token 的静态基线比较。

### 4.5 重采样与损失加权

重采样改变样本曝光，损失加权改变单次梯度贡献。两者并不等价，尤其在优化器、自适应批量和重复记忆下。实验只改变一种因素。

## 5. 去污染

### 5.1 污染单元

可能是完整题目、答案、推理路径、代码、测试、关键数字、文档段落或同源模板。根据评测任务定义，不用一个字符串规则包打天下。

### 5.2 精确与规范化匹配

哈希适合完全副本，规范化处理空白、标点、大小写和格式。它便宜可解释，却抓不到释义和结构改写。

### 5.3 模糊匹配

使用 n-gram、MinHash、编辑距离或代码结构发现局部和近似重合。阈值需要金标校准，短文本尤其易误报。

### 5.4 语义与来源匹配

嵌入或模型判断可以发现释义，来源谱系能发现由评测题生成的改写。语义高相似不是自动污染，需结合答案与任务判断。

### 5.5 污染处置

隔离命中样本、同父后代或整个簇，重算覆盖与混合。若评测已被用于生成或选择，应降级为开发集并建立新盲测。

## 6. 消融设计

### 6.1 Leave-one-source-out

从完整配方逐个移除来源，观察目标、护栏与成本变化。它回答来源的条件边际价值，但来源之间可能有交互。

### 6.2 Add-one-source

从稳定基线逐个加入来源，适合小规模筛选。加入顺序会影响结论，应固定基线或使用多种顺序。

### 6.3 剂量曲线

对某类数据使用零、低、中、高监督 Token，观察收益饱和和回退。比例必须结合固定总 Token 或明确增量预算。

### 6.4 处理消融

比较去重、质量选择、污染过滤、长度控制和课程，避免所有改动一起上线后无法归因。

### 6.5 多种子与置信区间

小模型 SFT 方差显著。每个关键候选用多个种子，报告逐项分数与不确定性；差异小于方差时结论为无法区分。

## 7. CPU 机制实验：带覆盖约束的选择与消融

### 随包实验的运行入口与边界

本文可直接运行的入口在实验包的 `lessons/lesson-21/`。正文中的生产架构、建议目录和框架示例用于解释机制与扩展设计，不代表这些生产系统已经随包实现。所有原有代码围栏另存于该目录的 `examples/`，文件以 `.txt` 结尾，便于逐字对照。

```bash
python lessons/lesson-21/run.py
python lessons/lesson-21/run_gpu.py
```

第一条命令读取固定反例并输出机制检查。第二条只运行单进程 CUDA 基础探针，不是本文完整数据平台或训练算法；没有 CUDA 时输出 `skipped`。通过探针不能证明 DDP、模型质量、集群吞吐或端到端恢复。真实系统扩展需要另外实现正文所列模块，并在自己的模型、数据和硬件上验收。

完整入口脚本保存在实验包同名文件中；阅读时从入口追到共享机制函数，再对照 fixture 与结果检查项。

### 7.1 实验目标

全局 Top-K 可能把低资源任务全部挤出。

模拟三个能力桶、质量、长度、重复簇与学生增益。比较全量、Top-K、覆盖约束和去重选择，输出监督 Token、覆盖、重复与代理收益。结果只解释选择机制。

```python
import json
import random
from collections import Counter

def make_data(seed: int = 20260822):
    rng = random.Random(seed)
    rows = []
    for index in range(300):
        bucket = ["reason", "code", "safety"][index % 3]
        cluster = f"{bucket}-{index % (12 if bucket != 'safety' else 7)}"
        length = rng.randint(40, 420)
        quality = min(1.0, max(0.0, rng.gauss(0.72, 0.16)))
        gain = quality * {"reason": 1.0, "code": 1.2, "safety": 0.9}[bucket]
        rows.append({"id": index, "bucket": bucket, "cluster": cluster,
                     "length": length, "quality": quality, "gain": gain})
    return rows

def summarize(name, chosen):
    buckets = Counter(x["bucket"] for x in chosen)
    clusters = Counter(x["cluster"] for x in chosen)
    token = sum(x["length"] for x in chosen)
    repeated = sum(max(0, count - 1) for count in clusters.values())
    value = sum(x["gain"] / (1 + 0.18 * (clusters[x["cluster"]] - 1)) for x in chosen)
    return {"name": name, "samples": len(chosen), "tokens": token,
            "bucket_counts": dict(buckets), "unique_clusters": len(clusters),
            "repeated_members": repeated, "proxy_value": round(value, 4)}

def main():
    rows = make_data()
    budget = 90
    top = sorted(rows, key=lambda x: x["quality"], reverse=True)[:budget]
    dedup = []
    seen = set()
    for row in sorted(rows, key=lambda x: x["quality"], reverse=True):
        if row["cluster"] not in seen:
            dedup.append(row)
            seen.add(row["cluster"])
    constrained = list(dedup)
    target = {"reason": 30, "code": 30, "safety": 30}
    for bucket, count in target.items():
        pool = [x for x in rows if x["bucket"] == bucket and x not in constrained]
        pool.sort(key=lambda x: x["quality"], reverse=True)
        need = count - sum(x["bucket"] == bucket for x in constrained)
        constrained.extend(pool[:max(0, need)])
    constrained = constrained[:budget]
    report = {
        "status": "passed",
        "claim_boundary": "synthetic selection mechanism only",
        "strategies": [summarize("all", rows), summarize("top_k", top),
                       summarize("coverage_dedup", constrained)],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
```

### 7.2 解释

Top-K 往往质量均值高但重复簇和桶偏置严重；覆盖去重牺牲少量单样本分数，换取更多独立簇与安全桶。代理收益函数只是教学构造，真实选择必须通过学生训练消融验证。

## 8. 至少一张可用 CUDA GPU 消融路径

### 8.1 目标

用 DDP 对相同小模型运行两个合成数据配方，固定初始化、优化步和验证随机集，输出实际监督 Token、Loss 与资源。缺本地 CUDA 或 CUDA 时结构化 `skipped`。

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

def batch(kind, step, rank, device, vocab=768, length=128):
    g = torch.Generator(device=device); g.manual_seed(step + rank * 100000 + (0 if kind == "balanced" else 999))
    low = 0 if kind == "balanced" or step % 4 else vocab // 2
    return torch.randint(low, vocab, (2, length + 1), generator=g, device=device)

def main():
    if not torch.cuda.is_available(): skip("CUDA unavailable")
    if torch.cuda.device_count() < 1: skip(f"requires at least one CUDA device, found {torch.cuda.device_count()}")
    if int(os.environ.get("WORLD_SIZE", "1")) < 1: skip("launch with torchrun --nproc_per_node=1")
    dist.init_process_group("nccl")
    rank = dist.get_rank(); local = int(os.environ["LOCAL_RANK"])
    torch.cuda.set_device(local); device = torch.device("cuda", local)
    results = []
    try:
        for recipe in ["top_k", "balanced"]:
            torch.manual_seed(42)
            model = nn.Sequential(nn.Embedding(768, 192), nn.LayerNorm(192), nn.Linear(192, 768)).to(device)
            model = nn.parallel.DistributedDataParallel(model, device_ids=[local])
            opt = torch.optim.AdamW(model.parameters(), lr=3e-4)
            consumed = torch.zeros(1, dtype=torch.long, device=device)
            for step in range(60):
                x = batch(recipe, step, rank, device)
                logits = model(x[:, :-1])
                loss = nn.functional.cross_entropy(logits.reshape(-1, 768), x[:, 1:].reshape(-1))
                opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
                consumed += x[:, 1:].numel()
            dist.all_reduce(consumed)
            metric = torch.tensor([float(loss.item())], device=device); dist.all_reduce(metric); metric /= 2
            if rank == 0: results.append({"recipe": recipe, "final_loss": float(metric), "tokens": int(consumed)})
        if rank == 0:
            print(json.dumps({"status": "passed", "results": results,
                              "peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
                              "claim_boundary": "synthetic two-GPU ablation control path only"}))
    except torch.cuda.OutOfMemoryError as exc:
        if rank == 0: print(json.dumps({"status": "skipped", "reason": f"CUDA OOM: {exc}"}))
    finally:
        dist.destroy_process_group()

if __name__ == "__main__": main()
```

### 8.2 真实替换

使用同一父模型、初始化、Tokenizer、Template、优化器、总监督 Token 和冻结评测，分别读取真实 SFT 发布。每个配方多种子，报告目标、通用、安全、风格、记忆和成本。单卡小模型用于筛选与控制面验证，生产结论需要目标尺度重跑。

## 9. 选择器谱系

### 9.1 输入快照

保存候选发布、质量信号、学生版本、表示模型和评测排除集。选择器不能读取最终盲测结果。

### 9.2 决策日志

每个样本记录通过、拒绝、簇、配额和最终权重原因。连续分数之外，硬门槛状态单列。

### 9.3 配方身份

配方由数据发布、选择版本、桶权重、采样器、Template 和 Tokenizer 共同定义。只记录文件路径无法复现。

### 9.4 实际账本

训练端按发布、桶、来源和样本簇回传监督 Token。断点恢复后守恒，计划—实际偏差超过阈值失败。

## 10. 常见错误

### 10.1 只选最高分

集中到易题、长答案和 Judge 偏好。加入覆盖、上限、去重和真实锚点。

### 10.2 只看样本数

长响应支配 Token。按最终 Loss 监督 Token 计量。

### 10.3 去污染只查问题

答案、轨迹、代码和父来源仍可泄漏。检查最终渲染和谱系。

### 10.4 消融同时改多个变量

无法归因。使用正交或分阶段设计，固定总 Token 与训练配置。

### 10.5 单次小领先

训练与评测方差可能更大。多种子与置信区间，证据不足就不排序。

## 11. 八十个选择与混合控制点

### 11.1 先定义学生

同一数据对不同模型、Tokenizer 和能力阶段价值不同。选择运行绑定父模型摘要和学生基线，不把质量分当永久属性。

### 11.2 先定义目标

样本映射到产品任务、用户分布和护栏。无法映射的高分样本进入探索池，不自动占用主训练预算。

### 11.3 先定义监督单元

明确按对话、Turn、响应、工具事件或 Token 选择。单位不同会改变去重、配额和 Loss Mask，必须写入 Schema。

### 11.4 合规先于打分

许可、隐私、秘密和严重安全是硬门禁。不可接受样本不因质量高而获得更高权重，连续总分不能补偿红线。

### 11.5 Schema 先于内容选择

角色、字段、Template 和工具版本不兼容时先迁移或隔离。把格式错误留给训练器跳过会改变实际配方。

### 11.6 最终渲染后计数

选择阶段读取 Tokenizer 和 Chat Template，计算截断、特殊 Token 和监督 Token。原始字符与 JSON 条数都不是训练剂量。

### 11.7 质量信号分项保存

正确、相关、完整、风格、安全和证据分开，避免一个分数失去解释。不同任务使用不同适用字段。

## 写在最后

指令数据之外，还需要成对偏好信号来对齐行为。下一篇：[人类偏好、AI Feedback 与 On-policy 偏好数据](/source/AI-Infra/5-数据工程与后训练/22-人类偏好-AIFeedback与On-policy偏好数据)。