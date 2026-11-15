# Continued Pretraining 与 SFT 数据配方工厂

![Continued Pretraining 与 SFT 数据配方工厂](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l33_01.png)

## 1. 项目目标

共享治理和血缘，不共享全部样本编译规则。

这个项目把“选一些领域数据继续训练，再混一些指令数据”变成可比较的数据产品决策。系统接收多个 CPT 域、SFT 能力簇、Token 预算、遗忘约束和评测目标，输出至少三个候选配方、代理训练结果、消融证据、最终 Train-ready Release 和可回放的数据卡。

项目重点是配方工厂，而不是追求某个模型的最高分。CPU 实验用于证明采样、覆盖、确定性和边际价值计算；真实硬件路径以单卡或通用 CUDA GPU 上的小模型、LoRA 或 QLoRA 进行桥接。若 CUDA、显存、模型或数据不可用，必须返回结构化 `skipped`。小模型结果只能支持当前任务与预算下的相对选择，不能外推到更大模型的绝对收益。

## 2. 输入、输出与边界

输入包含基座模型与 Tokenizer 版本、CPT 候选数据域、SFT 样本及能力标签、污染报告、质量与难度分数、目标 Token 预算、最大重复次数、长上下文比例、通用能力锚点、安全锚点和硬件预算。任何未知来源、未知模板或缺少 Loss Mask 证据的数据不能进入候选。

输出包括 Domain Catalog、Capability Catalog、候选 Recipe、确定性 Sample Manifest、代理训练 Run、评测切片、成本账本、配方选择记录、最终 Release 和 Checkpoint 反向血缘。CPT 与 SFT 分别发布，不能用同一个模糊“训练集版本”覆盖不同目标、Schema 和 Mask。

项目不声称代理模型排名必然等于目标模型排名。代理实验用于缩小搜索空间，最终决策还要考虑不确定性、规模迁移、遗忘、安全和真实预算。若候选差异落在噪声内，正确结论是需要更多证据或选择运营更稳健的配方。

## 3. 总体架构

Catalog 层保存每个数据域、能力簇、来源、质量、难度、长度、独特性、许可和污染证据。Recipe Generator 按约束生成 CPT 与 SFT 候选权重。Sampler 根据权重、温度、预算和最大 Epoch 形成确定性清单。Materializer 完成 Tokenizer、截断、Packing、Chat Template 和 Loss Mask。Proxy Trainer 执行小规模训练。Evaluator 运行能力、安全、通用保持与数据效率评测。Selector 根据多目标门槛和置信区间输出选择理由。

候选要共享可比的计算与评测条件。

控制面把每个候选定义为不可变对象：输入 Release、域权重、随机种子、采样单位、重复上限、Tokenizer、模板、Packing、训练配置和评测集合都进入哈希。候选之间共享原始资产，但 Sample Manifest 独立。任何训练实际消费偏离 Manifest 时，Run 状态标记 Non-conformant，结果不得进入正式比较。

## 4. 目录结构

```text
recipe_factory/
  catalogs/domains.yaml
  catalogs/capabilities.yaml
  recipes/cpt/
  recipes/sft/
  schemas/sample.json
  schemas/chat.json
  src/profile.py
  src/generate_candidates.py
  src/materialize.py
  src/train_proxy.py
  src/evaluate.py
  src/select_recipe.py
  configs/hardware/cuda_scalable.yaml
  tests/test_sampling.py
  artifacts/manifests/
  artifacts/reports/
```

CPT 样本记录文档与 Token 范围、域、来源、质量、难度、重复次数和污染状态。SFT 样本记录 Messages、模板、Token 序列、角色边界、Label、Loss Mask、能力标签和生成血缘。Packing 后保存每个 Sequence 由哪些 Sample 片段组成以及文档边界，保证 Loss 与删除影响可追踪。

## 5. 建立数据画像

每个域至少统计名义 Token、有效 Token、独特 Token、文档长度、语言、质量、难度、近重复簇、来源集中度和评测污染。SFT 还统计用户与助手 Token、平均轮数、截断位置、有效 Loss Token、模板错误、能力覆盖和安全标签。只看样本条数会让短样本和长样本失衡。

质量分数不能直接当采样概率。先按域校准并检查高分尾部，再设硬门禁与软权重。来源集中度限制单域内某个站点或 Teacher 支配数据。重复上限按独特身份而非文件行号计算，避免相同内容在多个 Release 中绕过限制。

## 6. 候选配方设计

权重优化不能绕过数据可用性。

至少生成三个候选。候选 A 是稳健基线：CPT 以规模温度采样，保留较高通用域锚点；SFT 按能力宏配额分配。候选 B 强调目标领域，提高高质量和高难度样本权重，同时限制来源集中。候选 C 由代理模型或回归模型建议，用更强边际价值权重，但保留探索下限和安全配额。

候选 Recipe 明确采样单位是文档、Sample 还是 Token；明确有放回与无放回；明确域耗尽后的动作；明确课程阶段、每阶段 Token 和是否重置随机；明确 CPT 到 SFT 之间的 Checkpoint、学习率和评测门禁。权重之和相同不代表实际消费相同，必须物化清单后重新统计。

## 7. 确定性物化与门禁

门禁检查记录实际值、阈值与基线。

Sampler 使用稳定 Sample ID、Recipe 哈希和显式种子生成优先键，按域预算选择后写 Manifest。并发度变化不能改变逻辑成员。Tokenizer 与模板物化后，按有效 Token 重新检查预算；Packing 使用固定桶与排序规则，输出 Sequence Manifest。训练恢复保存 Manifest 游标、Epoch 和随机状态。

发布门禁检查来源权限、Schema、模板、Mask、污染、重复、能力覆盖、Token 预算、长上下文比例和通用锚点。对 CPT 运行基准子串与语义去污染；对 SFT 检查评测题改写、Teacher 泄漏、答案模板和系统 Prompt 冲突。被拒绝样本保留原因，不从统计中消失。

## 8. CPU 机制实验：配方与覆盖

### 随包实验的运行入口与边界

本文可直接运行的入口在实验包的 `projects/project-03/`。正文中的生产架构、建议目录和框架示例用于解释机制与扩展设计，不代表这些生产系统已经随包实现。所有原有代码围栏另存于该目录的 `examples/`，文件以 `.txt` 结尾，便于逐字对照。

```bash
python projects/project-03/run.py
python projects/project-03/run_gpu.py
```

第一条命令读取固定反例并输出机制检查。第二条只运行单进程 CUDA 基础探针，不是本文完整数据平台或训练算法；没有 CUDA 时输出 `skipped`。通过探针不能证明 DDP、模型质量、集群吞吐或端到端恢复。真实系统扩展需要另外实现正文所列模块，并在自己的模型、数据和硬件上验收。

完整入口脚本保存在实验包同名文件中；阅读时从入口追到共享机制函数，再对照 fixture 与结果检查项。

拒绝、长度和读取失败可能让二者偏离。

```python
import hashlib
import json
import random
from collections import Counter

SAMPLES = [
    {"id": f"math-{i}", "domain": "math", "capability": "reason", "tokens": 80 + i * 3, "quality": 0.7 + i / 100}
    for i in range(12)
] + [
    {"id": f"code-{i}", "domain": "code", "capability": "tool", "tokens": 100 + i * 5, "quality": 0.75 + i / 120}
    for i in range(10)
] + [
    {"id": f"general-{i}", "domain": "general", "capability": "chat", "tokens": 60 + i * 2, "quality": 0.65 + i / 150}
    for i in range(15)
]

def priority(sample, recipe_id, seed):
    raw = f"{recipe_id}:{seed}:{sample['id']}".encode()
    return int(hashlib.sha256(raw).hexdigest(), 16)

def materialize(samples, domain_tokens, recipe_id, seed=7):
    selected = []
    for domain, budget in domain_tokens.items():
        pool = [x for x in samples if x["domain"] == domain and x["quality"] >= 0.7]
        pool.sort(key=lambda x: priority(x, recipe_id, seed))
        used = 0
        for item in pool:
            if used + item["tokens"] > budget and selected:
                continue
            selected.append(item)
            used += item["tokens"]
            if used >= budget:
                break
    return selected

recipes = {
    "balanced": {"math": 500, "code": 500, "general": 500},
    "domain_heavy": {"math": 700, "code": 650, "general": 150},
    "anchor_heavy": {"math": 400, "code": 400, "general": 700},
}
report = {}
for name, budget in recipes.items():
    data = materialize(SAMPLES, budget, name)
    report[name] = {
        "tokens": sum(x["tokens"] for x in data),
        "domains": Counter(x["domain"] for x in data),
        "capabilities": Counter(x["capability"] for x in data),
        "manifest": hashlib.sha256("\n".join(sorted(x["id"] for x in data)).encode()).hexdigest(),
    }
assert materialize(SAMPLES, recipes["balanced"], "balanced") == materialize(list(reversed(SAMPLES)), recipes["balanced"], "balanced")
print(json.dumps(report, ensure_ascii=False, indent=2, default=dict))
```

实验验证输入顺序不影响候选成员，并展示名义域预算经过质量门禁后可能无法完全使用。生产 Sampler 应明确域耗尽策略，不能静默把缺口分给到达更快的域。扩展练习加入温度采样、最大重复、长上下文配额和不确定性探索。

## 9. 代理训练与评测设计

代理训练固定模型、初始化、优化器、有效 Token、Batch、序列长度和评测频率，只改变数据配方。每个候选运行多个种子，报告能力宏平均、目标领域、通用保持、安全、困惑度、训练 Loss、有效 Token、峰值显存和墙钟。选择前预先注册主指标和不能下降的红线。

CPT 评测关注目标域建模、通用困惑度、遗忘、长上下文和污染敏感题。SFT 评测关注指令遵循、能力簇、格式、工具、拒答与安全。自动 Judge 只作为一个信号，保留固定规则、人工抽样和可执行 Verifier。评测数据与训练数据沿血缘做去污染。

边际价值通过消融判断：从候选中删除或降低一个域，保持总 Token 不变，用替代域补齐，再比较指标变化。不要把“有该域的模型更好”直接解释为该域有效，因为总 Token、质量与难度可能同时变化。代理回归输出不确定性，差异小于噪声时不强行排序。

## 10. 通用 CUDA 真实路径

推荐选择许可清晰的小模型与小数据 Release，使用 bf16 或 fp16、梯度检查点、LoRA/QLoRA 和短到中等上下文。单卡先直接运行训练逻辑；多卡扩展时再采用 DDP 或 FSDP，实验目标是比较配方，而不是挑战最大参数。运行前探测：

```python
import json
import os

try:
    import torch
    count = torch.cuda.device_count()
    memory = [round(torch.cuda.get_device_properties(i).total_memory / 1024 ** 3, 1) for i in range(count)]
    checks = {"cuda": torch.cuda.is_available(), "gpu_count": count, "memory_gib": memory, "model_path": bool(os.environ.get("MODEL_PATH"))}
except Exception as exc:
    checks = {"cuda": False, "error": type(exc).__name__}

ready = checks.get("cuda") and checks.get("gpu_count", 0) >= 2 and checks.get("model_path")
print(json.dumps({"status": "ready" if ready else "skipped", "reason": None if ready else "dual_gpu_or_model_unavailable", "checks": checks}))
```

真实命令固定 `CUDA_VISIBLE_DEVICES=0`、容器、驱动、PyTorch、Transformers、PEFT、数据 Manifest 与 Seed。先在几十步上验证 Loss Mask、梯度、Checkpoint 和恢复，再完成每个候选的等 Token 训练。若某候选 OOM，只能通过对全部候选一致的 Batch 或序列策略修正，不能单独降低其预算后继续公平比较。

## 11. 选择规则与验收

选择不是把所有指标加权成一个不透明分数。先执行硬门槛：安全、通用保持、污染、模板、恢复和成本不能越界；再在合格候选中比较目标能力、达到门槛时间和总成本；最后用不确定性、运维复杂度与规模迁移风险决胜。权重与门槛在结果出现前版本化。

验收要求三个候选都有不可变 Recipe、Sample 与 Sequence Manifest、训练配置、Checkpoint、评测原始结果和成本账本。相同候选重跑时成员与顺序可重现；从 Checkpoint 能反查实际消费清单；任一数据撤回能定位候选和 Run。最终 Release 附选择理由与未选择候选的证据，而不是只保存冠军。

## 12. 演示、排障与交付

只交一组权重不能复现训练输入。

演示先展示 Catalog 画像，再一键生成三个 Recipe 与清单，比较物化后的实际 Token 和能力覆盖。运行 CPU 代理或真实小模型训练，展示多种子曲线、消融和 Pareto 选择。随后改变一个来源权限或提交 Tombstone，系统重新物化候选并显示受影响 Run，证明配方工厂不是静态表格。

能力下降时先区分数据成员、Tokenization、Mask、训练配置与评测变化。通用遗忘时检查通用锚点的有效 Token、重复与课程位置；目标域无收益时检查独特性、难度、污染和代理规模失配；候选不可复现时核对稳定身份、并发归并、库版本和恢复游标。

最终交付 Catalog、三套以上 Recipe、确定性 Sampler、物化器、机制测试、单卡基线配置、训练日志、Checkpoint、评测切片、消融报告、成本报告、最终数据卡与限制说明。合格结果不是“找到最佳比例”，而是建立一套能在新数据、新模型和新预算下重复做出有证据决策的工厂。

## 13. 生产评审十二问

### 13.1 预算单位是否统一

不同长度和 Mask 会改变实际学习预算。

候选都写“百万样本”没有可比性，必须统一到有效 Token、序列和 Loss Token，并保留文档与能力宏统计。CPT 总 Token 相同而 SFT 有效助手 Token 不同，会改变优化量；物化后重新核算，超差候选不能直接进入代理训练。

### 13.2 候选是否只改变配方

模型、初始化、训练 Token、优化器、序列长度、模板、评测和停止规则固定，只有预注册的数据变量变化。若某候选因 OOM 改了微批或检查点，所有候选使用兼容设置重跑，避免把系统差异归因于数据。

### 13.3 域权重是否等于消费权重

质量门禁、去重、长度、域耗尽和 Packing 会改变实际 Token 比例。报告 Recipe 目标、物化清单和训练实际消费三层分布，并解释偏差。只有配置权重而没有消费证据，不能支持配方结论。

### 13.4 通用锚点是否真的独特

通用域可能与目标域近重复，名义上保留锚点却没有提供互补知识。按去重簇和语义覆盖测独特 Token，限制重复频率，并在评测中检查通用能力保持。锚点质量差也会浪费防遗忘预算。

### 13.5 能力标签是否可靠

标签来自规则、模型或人工时都保存版本与置信。抽样检查多标签、缺失与切片偏差；能力覆盖用任务宏和 Token 微观同时报告。标签漂移后重新投影 Catalog，不在旧数据上覆盖原判断。

### 13.6 代理结果能否迁移

代理结果用于筛选，不能保证排名完整迁移。

用至少一组不同模型规模或训练预算验证候选排序稳定性，并报告秩相关与不确定性。若排序不稳定，选择稳健配方或扩大目标模型 Pilot。不能把最小代理的一次领先写成目标模型必然最优。

### 13.7 多种子是否足够

预先估算希望识别的最小效应和方差，为每候选分配重复。报告均值、区间和单次曲线，不只展示最好种子。差异落在噪声内时，成本、风险和可运营性可以成为合理决胜因素，但要明确证据不足。

### 13.8 课程顺序是否被验证

相同总量在不同阶段顺序可能产生遗忘或迁移差异。至少比较混合、先通用后领域和阶段间锚点三类小实验，Checkpoint 在阶段边界评测。课程顺序属于 Recipe，不得只写在调度脚本中。

### 13.9 SFT Mask 是否进入验收

随机抽样展示角色、Token 与 Mask，统计每能力簇有效 Loss Token。模板升级运行 Golden Diff，防止系统与用户 Token 进入 Loss 或助手尾部被截断。Mask 错误会让再精细的配方权重失去意义。

### 13.10 评测是否被训练污染

从原始文档、合成父任务、改写和语义近邻多层去污染，记录基准版本与命中证据。发现污染后同时修订训练 Release 和评测解释；不能只删除完全相同字符串，然后宣称所有能力提升可信。

### 13.11 成本怎样影响选择

同等质量下，数据获取、物化、训练、评测和人工审核总成本更低的配方更优。若一个候选需要大量低保留生成或长序列填充，成本必须计入。选择报告展示质量—时间—成本 Pareto，不把 GPU 训练成本当全部成本。

### 13.12 最终配方能否重建

在空缓存、不同并行度下从 Release 和 Recipe 重建 Sample 与 Sequence Manifest，逻辑成员、顺序和哈希一致。训练恢复从 Checkpoint 继续消费正确下一个样本。无法重建的“最佳配方”不能成为可发布数据产品。

## 写在最后

配方工厂之后，合成数据与奖励模型也需要同样可复现的生产线。下一篇：[合成数据、偏好数据与 Reward Model 工厂](/source/AI-Infra/5-数据工程与后训练/34-合成数据-偏好数据与RewardModel工厂)。