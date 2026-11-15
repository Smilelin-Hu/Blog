# 可按显存缩放的 SFT 到 DPO 到 GRPO/RLVR 流水线

![可按显存缩放的后训练流水线](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l35_01.png)

## 1. 项目目标与硬件边界

时分执行也有切换峰值，不能仅取静态参数大小。

本项目在至少一张可用 CUDA GPU 上建立一条真实可运行的小规模后训练流水线：先对许可清晰的小模型执行 SFT，再从同一策略产生或消费偏好数据执行 DPO，最后在可验证任务上执行小规模 GRPO 或 RLVR。重点是数据、概率、Checkpoint、显存、恢复和评测合同完整，而不是宣称单卡实验复现了前沿大模型能力。

实验规模要服从显存。建议选择约 0.5B 到 3B 参数模型，SFT 和 DPO 使用 LoRA 或 QLoRA，序列长度从 512 或 1024 起步；GRPO 并发生成数量、Group 大小和最大响应严格受控。任何 OOM 后的降配必须记录并对比较组一致应用。缺少可用 CUDA GPU、模型或数据时返回结构化 `skipped`，不能用 CPU 模拟吞吐冒充 CUDA 实测。

## 2. 端到端产物

每阶段输入与输出都不可变。SFT 输入是 Chat Schema、模板、Token、Label 与 Loss Mask Manifest，输出 Adapter、合并候选、训练状态和评测。DPO 输入是 Policy/Reference、Chosen/Rejected、Token 对齐与长度统计，输出新的 Adapter 和偏好评测。GRPO 输入是任务、环境、Verifier、Policy Bundle、采样合同和 Group，输出 Experience、更新 Checkpoint 与完整成功评测。

最终必须能从 GRPO Checkpoint 反查 SFT Release、DPO Preference Release、所有模型基座、Tokenizer、代码提交、容器、GPU、驱动、随机种子和实际消费清单。阶段间不靠“output/final”目录传递，而通过版本 Manifest 解析。

## 3. 架构与资源放置

SFT 和 DPO 先采用单卡 LoRA/QLoRA 基线；需要扩展时再使用 DDP 或 FSDP，LoRA 参数同步，数据按确定性 Distributed Sampler 分片。GRPO 在小规模下可以采用时分复用：阶段一在单卡加载推理 Policy，生成 Group 并保存行为 Logprob；阶段二释放推理引擎，再在同一设备加载 Trainer 执行更新。该方案吞吐不高，却避免同时驻留 Policy、Reference 和 Trainer 导致 OOM，适合验证算法合同。

若模型足够小，也可一张卡 Rollout、一张卡 Trainer 做有界异步，但可选的多卡拓扑没有高速互联时权重同步和跨卡传输成本明显。项目先完成严格同步正确性基线，再选择是否增加流水重叠。所有权重发布使用完整 Bundle 与哈希，生成请求不中途切版。

CPU 负责数据预处理、环境、Verifier、清单和指标聚合；NVMe 保存 Tokenizer 缓存、分片、Checkpoint 和生成中间结果。预留至少两份 Checkpoint 和一个临时上传空间。不要把系统盘剩余空间耗尽后再谈恢复。

## 4. 建议目录

```text
cuda_scalable_posttrain/
  manifests/
  data/sft/
  data/preferences/
  data/rlvr_tasks/
  configs/model.yaml
  configs/sft.yaml
  configs/dpo.yaml
  configs/grpo.yaml
  src/prepare_sft.py
  src/train_sft.py
  src/build_preferences.py
  src/train_dpo.py
  src/rollout.py
  src/train_grpo.py
  src/evaluate.py
  src/checkpoint.py
  tests/test_masks.py
  tests/test_logprobs.py
  artifacts/metrics/
```

每个配置显式写模型与 Tokenizer 路径、精度、量化、LoRA、序列长度、Batch、梯度累积、学习率、Warmup、Checkpoint 间隔、Seed、评测 Manifest 和恢复策略。环境变量只保存凭证与机器路径，影响训练语义的参数不能藏在 Shell 历史中。

## 5. SFT 阶段

梯度正常不保证目标角色正确，先做逐 Token 核对。

SFT 数据先验证 Messages 角色、系统消息、工具 Schema 和多轮顺序，再由目标 Tokenizer 与 Chat Template 物化。Label 与 Loss Mask 逐 Token 保存或可确定重算：用户、系统、工具 Observation、Padding 和被截断无效尾部不参与助手策略损失。抽样打印 Token、角色边界和 Mask 是发布门禁。

Packing 只拼接合同允许的 Sample，保存边界和 Position 策略。有效 Token 而非总 Token 用于 Loss 归一和吞吐。训练先执行一个 Batch 过拟合：Loss 应快速下降，Mask 打乱或 Label 错位测试应失败。随后运行短烟测，验证一个或多个 Rank 数据不重复、梯度同步、Checkpoint 和恢复。

正式小实验固定有效 Token 预算，记录每步有效 Token、Loss、学习率、梯度范数、吞吐、显存和数据等待。评测覆盖目标能力、格式、安全和通用锚点。SFT Adapter 只有在恢复测试与评测门槛通过后进入 DPO。

## 6. DPO 阶段

共享 Prompt 与模板，保留两者 Logprob 证据。

DPO Pair 绑定同一 Prompt 版本，Chosen 与 Rejected 来自明确策略和标注。模板分别物化后核对共享 Prompt Token 边界；长度截断不能让偏好差异消失。训练前统计响应长度、模型来源、任务、位置和偏好强度，防止长度或策略身份成为捷径。

Policy 从 SFT Checkpoint 初始化，Reference 固定为同一 SFT 版本或配置声明版本。若使用参考模型预计算 Logprob，缓存键包含模型、Tokenizer、模板、序列和精度；随机抽样在线重算。DPO 记录 Chosen/Rejected 对数概率差、隐式 Reward 差、准确率、KL 代理、长度切片和峰值显存。

比较 SFT 与 DPO 时使用同一评测和解码合同。DPO 提升偏好指标却降低通用能力或安全时不能发布。Reference、Beta 和长度分布改变都需单独实验，不把多个变化归因到算法名称。

## 7. GRPO 与 RLVR 阶段

组内无差异时缺少相对信号，不能伪造非零优势。

选择可执行验证的小任务，例如受限数学表达式、结构化转换、单元测试代码或沙箱工具任务。Verifier 返回通过、错误类别、证据和版本。隐藏测试与变形测试防止策略记忆表面规则。环境故障与策略失败分开，前者作废或重试。

每个 Task 生成固定 Group，成员使用同一 Policy、Runtime、采样合同和 Reward 版本。保存 Prompt、Response Token、行为 Logprob、有效 Mask、终止原因、Reward、Group 统计和成本。组内优势计算明确方差为零时的处理。过长、自然 EOS 和时间截断使用不同 Mask 与 Bootstrap 语义。

训练前在 CPU 上重算一个微型 Group 的优势与 Loss，再在 GPU 上比对。初始 Ratio 应接近一；出现大偏差先检查 Token、模板、Logprob 和精度，不能通过调大 Clip 掩盖。每轮更新后保存 Policy Bundle，下一轮 Rollout 只在 Bundle 完整就绪后开始。

## 8. CPU 机制实验：GRPO 优势与裁剪

### 随包实验的运行入口与边界

本文可直接运行的入口在实验包的 `projects/project-05/`。正文中的生产架构、建议目录和框架示例用于解释机制与扩展设计，不代表这些生产系统已经随包实现。所有原有代码围栏另存于该目录的 `examples/`，文件以 `.txt` 结尾，便于逐字对照。

```bash
python projects/project-05/run.py
python projects/project-05/run_gpu.py
```

第一条命令读取固定反例并输出机制检查。第二条只运行单进程 CUDA 基础探针，不是本文完整数据平台或训练算法；没有 CUDA 时输出 `skipped`。通过探针不能证明 DDP、模型质量、集群吞吐或端到端恢复。真实系统扩展需要另外实现正文所列模块，并在自己的模型、数据和硬件上验收。

完整入口脚本保存在实验包同名文件中；阅读时从入口追到共享机制函数，再对照 fixture 与结果检查项。

```python
import json
import math
from statistics import mean, pstdev

groups = {
    "task-a": [1.0, 0.0, 0.5, 1.0],
    "task-b": [0.0, 0.0, 0.0, 0.0],
}
old_logprob = [-1.20, -0.75, -2.10, -1.45]
new_logprob = [-1.15, -0.90, -1.95, -1.80]

def normalize(values, eps=1e-6):
    scale = pstdev(values)
    if scale < eps:
        return [0.0 for _ in values]
    center = mean(values)
    return [(x - center) / (scale + eps) for x in values]

def clipped_objective(old_lp, new_lp, advantages, clip=0.2):
    rows = []
    for before, after, advantage in zip(old_lp, new_lp, advantages):
        ratio = math.exp(after - before)
        clipped = min(max(ratio, 1 - clip), 1 + clip)
        objective = min(ratio * advantage, clipped * advantage)
        rows.append({"ratio": ratio, "advantage": advantage, "objective": objective, "clipped": ratio != clipped})
    return rows

advantages = normalize(groups["task-a"])
report = {
    "task_a_advantages": advantages,
    "task_b_advantages": normalize(groups["task-b"]),
    "tokens": clipped_objective(old_logprob, new_logprob, advantages),
}
assert abs(sum(advantages)) < 1e-5
assert report["task_b_advantages"] == [0.0] * 4
print(json.dumps(report, indent=2))
```

这个实验验证组内标准化、零方差 Group 与裁剪方向。生产 Loss 在 Token 维度展开并使用有效 Mask，还要处理长度归一、KL、Entropy 和多轮动作边界。CPU 结果是公式 Golden Test，不是训练质量实测。

## 9. 硬件与依赖探测

```python
import json
import os

checks = {"model_path": bool(os.environ.get("MODEL_PATH")), "dataset_manifest": bool(os.environ.get("DATASET_MANIFEST"))}
try:
    import torch
    checks["cuda"] = torch.cuda.is_available()
    checks["gpu_count"] = torch.cuda.device_count()
    checks["devices"] = [
        {"name": torch.cuda.get_device_name(i), "memory_gib": round(torch.cuda.get_device_properties(i).total_memory / 1024 ** 3, 1)}
        for i in range(torch.cuda.device_count())
    ]
except Exception as exc:
    checks.update({"cuda": False, "error": type(exc).__name__})
ready = checks.get("cuda") and checks.get("gpu_count", 0) >= 2 and checks["model_path"] and checks["dataset_manifest"]
print(json.dumps({"status": "ready" if ready else "skipped", "reason": None if ready else "dual_rtx_path_unavailable", "checks": checks}))
```

Ready 后记录 `nvidia-smi` 拓扑、驱动、CUDA、PyTorch、NCCL、GPU 名称与显存。多张卡若不是同型号或同显存，配置按较小卡设计。先执行 NCCL 小测试与双 Rank 张量 AllReduce，再开始训练。PCIe 拓扑、CPU NUMA 和磁盘位置写入实验卡。

## 10. 推荐运行顺序

低层未通过时先定位，不把复杂系统错误堆在一起。

第一步运行数据门禁和 CPU Golden Test。第二步单卡一个 Batch 过拟合。第三步完成单卡二十步烟测，检查 Rank、显存和 Checkpoint。第四步故意在梯度累积、保存和恢复后各中断一次，核对数据游标与优化器步。第五步完成 SFT 等 Token 训练与评测。第六步物化 Preference 并执行 DPO。第七步构建 RLVR 任务与 Verifier，先只生成不更新，审计 Group。第八步执行一到数轮严格同步 GRPO。

若引入有界异步，作为独立实验分支：限制最大 Policy Lag 为一，记录行为版本、Ratio 高低尾和新鲜有效吞吐，与严格同步在相同生成 Token 和训练 Token 下比较。本地 CUDA 资源很紧时，时分复用往往比常驻异步更诚实；架构复杂度也进入结论。

## 11. 指标体系

数据指标包括 Schema 失败、模板失败、有效 Loss Token、截断、Packing 利用率、Pair 长度差、Group 完成与环境作废。训练指标包括 Loss、学习率、梯度范数、Token 吞吐、数据等待、峰值显存、通信时间和 Checkpoint 时间。DPO 增加偏好准确率、隐式 Reward 差和 KL 代理；GRPO 增加 Reward、成功率、优势方差、Ratio、Clip Fraction、KL、Entropy、响应长度和陈旧度。

产品结果用固定解码合同下的任务成功、能力宏平均、安全红线和格式正确衡量。性能结果同时报告 Warmup、稳态和完整作业时间。成本包含生成、训练、Verifier、失败和恢复。不得用训练 Reward 替代独立评测，也不得用单次最好结果替代多种子分布。

## 12. Checkpoint 与恢复

缺少某项会改变下一步输入或更新。

Checkpoint 包含模型或 Adapter、优化器、调度器、GradScaler、随机状态、数据游标、已提交 Batch、Policy 版本、Rollout 清单和配置哈希。保存先写临时目录、计算分片哈希、生成 Manifest，再原子注册 Ready。恢复只从 Ready 版本读取。

SFT 和 DPO 恢复后下一个 Sample ID 应与不中断对照一致。GRPO 恢复要识别已生成未训练、已训练未发布和已发布未开始下一轮三种边界；同一 Experience 不能重复更新。故障测试比较恢复前后优化器步、数据清单、权重哈希和评测，而不只是程序能继续输出 Loss。

## 13. 验收阈值

小规模冒烟只证明实现路径，不能承诺模型能力收益。

结构门禁要求全部数据、模型和 Checkpoint 都有 Manifest 与血缘。正确性门禁要求 Mask Golden Test、Logprob 重算、初始 Ratio、双 Rank 数据分片、Group 版本一致和恢复最多一次通过。硬件门禁要求真实设备与软件信息完整，OOM 和跳过如实记录。

质量门禁预先设定：SFT 相对基座提升目标能力且通用与安全不越红线；DPO 相对 SFT 提升偏好切片且没有明显长度捷径；GRPO 在独立隐藏 Verifier 上提高完整成功，Reward 与长度、Entropy 和 KL 保持合理。具体数值由所选任务 Pilot 建立，不能在看到结果后移动阈值。

## 14. 故障排查

改变序列或 Group 后不再是完全相同的算法条件。

SFT Loss 不降先检查 Mask、Label 平移、模板、学习率和有效 Token；多进程曲线不一致检查 Sampler、梯度同步和每 Rank Batch。DPO 偏好准确率迅速一百但评测不升，重点检查数据泄漏、模型来源和长度捷径。GRPO Ratio 初始不接近一，检查生成端与训练端 Tokenizer、模板、Logprob、量化和 Mask。

OOM 按权重、优化器、激活、KV 与临时通信缓冲分解，依次调整序列、微批、检查点、LoRA 和阶段时分复用，并记录影响。NCCL 挂起先收集 Rank 日志、拓扑和超时位置，不盲目重启覆盖现场。恢复后 Loss 跳变检查优化器、调度器、随机状态和重复 Batch。

## 15. 演示与最终交付

演示从一条 SFT 样本展示模板与 Mask，完成短 SFT 并恢复；展示一个 DPO Pair 的 Token 与概率，完成 DPO；展示一个 RLVR Group、Verifier 证据、优势和一次策略更新。最后对比基座、SFT、DPO 与 GRPO Candidate 的固定评测、显存、吞吐和成本，并明确小规模证明边界。

最终交付全部数据与模型 Manifest、四类配置、CPU Golden Test、CUDA 环境探测、运行命令、训练日志、Checkpoint、恢复证据、评测原始结果、成本报告、已知限制和 `skipped` 示例。真正的完成标准是另一台满足条件的 CUDA 机器可以按 Manifest 重跑，并得到统计上可解释、路径上可追责的结果。

## 16. CUDA 发布前十二问

### 16.1 实际设备是否参与训练

保存每 Rank 启动日志、设备、数据 Sample ID、梯度同步和显存曲线。看到多个设备都有显存不等于正确 DDP；可能一个 Rank 只加载模型却不推进。全局有效 Batch 与梯度累积按 Rank 数重新计算并写入实验卡。

### 16.2 数据分片是否重复

收集一个 Epoch 或固定窗口内每 Rank 的 Sample ID，验证并集、交集和 Padding 规则。Distributed Sampler 在恢复与最后不整 Batch 时尤其容易重复。重复若属于显式补齐，要从有效样本与吞吐统计中剔除。

### 16.3 Mask 是否跨 Packing 边界泄漏

构造两个带特殊标记的样本拼入同一 Sequence，检查 Label、Mask、Position 和注意力边界符合配置。若使用连续注意力，也要证明语义允许。删除传播能从 Sequence 回到两个父 Sample。

### 16.4 Reference 是否保持冻结

DPO 与 RL 阶段计算 Reference Logprob 时参数、Adapter 和 Dropout 状态固定。训练前后对固定 Batch 重算哈希与概率，差异超过数值容差立即失败。缓存键包含所有行为合同，不能因文件名相同复用旧概率。

### 16.5 生成与训练 Token 是否一致

从 Rollout 抽样保存原始文本、Token、Mask 和 Logprob，Trainer 使用相同 Tokenizer 与模板重建并逐 Token 比对。无法对齐的 Experience 进入隔离。不能删除“看似无关”的特殊 Token 后仍沿用原行为概率。

### 16.6 显存峰值是否完整

分别记录模型加载、前向、反向、优化器、Checkpoint、评测和 Rollout KV 峰值，并在每阶段重置峰值统计。`nvidia-smi` 低频采样可能漏掉瞬时 OOM 前峰值。报告保留显存、已分配与碎片化信息。

### 16.7 吞吐口径是否诚实

SFT 用有效 Loss Token，生成用输出 Token，完整作业包含加载、Warmup、保存和 Drain。梯度累积、Padding 和被 Mask Token 不得混进有效吞吐。多卡加速比使用相同配置的单卡基线，而不是不同 Batch 与长度。

### 16.8 Checkpoint 恢复是否连续

在固定步中断，恢复后比较下一个 Sample、学习率、优化器步、随机状态、Loss Scale 和权重。允许浮点统计差异时预先设容差。只看最终 Loss 大致接近不能发现重复消费或调度器跳步。

### 16.9 OOM 调整是否公平

OOM 后记录失败配置与阶段，再选择减微批、序列、Group、KV 或量化。候选比较使用同一有效 Token 与语义配置；若只有一个算法被迫改变，结论明确为资源受限实现差异，不冒充纯算法比较。

### 16.10 GRPO Reward 是否独立验证

训练 Reward 来自版本化 Verifier，最终评测使用隐藏测试或独立实现。策略可访问的信息不能包含隐藏答案。Top Reward 尾部人工或规则审计，发现利用立即冻结 Checkpoint 谱系，不继续用更强 KL 掩盖漏洞。

### 16.11 本地 CUDA 结果怎样外推

报告明确模型参数、序列、Group、PCIe 拓扑和时分复用。大集群会引入网络、权重广播、调度、队列和更大在途状态，本地 CUDA 结论只证明功能与局部性能。生产容量需重新测，不能线性乘 GPU 数。

### 16.12 另一台机器能否复现

在干净环境至少重跑烟测与一个短阶段，解析同一 Manifest、容器和 Seed。结果比较数据清单、结构指标和统计容差，不要求不同 GPU 位级一致。缺少模型许可或私有数据时提供替代 Fixture，但必须标明不是原实测复现。

## 17. 把三种目标真正作用到同一个小策略

这个实验使用只有两个动作的分类策略。SFT 的交叉熵、带冻结参考项的 DPO 和组内优势驱动的裁剪更新都会实际修改策略参数。先观察 SFT 后动作概率，再核对 DPO 的参考差是否固定，最后检查零方差组与行为概率。它没有语言上下文、价值网络或分布式并行，不能用结果推断 LLM 的能力提升。

```bash
python projects/project-05/train_toy_policy.py
```

下面代码直接取自实验包同名文件。运行报告保存在该项目的 `results/` 中；失败记录不改写为成功。

```python
"""Run SFT -> reference-aware DPO -> grouped clipped policy-gradient updates.
A two-action categorical policy, NOT a language model or a GPU benchmark.
"""
from __future__ import annotations
import json, math, random
from pathlib import Path

def probs(logits):
    high=max(logits); values=[math.exp(x-high) for x in logits]; total=sum(values)
    return [x/total for x in values]

def main():
    logits=[0.0,0.0]; lr=0.1; stages=[]
    # Chosen action is 1. Cross entropy gradient for softmax classification.
    for _ in range(12):
        p=probs(logits)
        logits=[x-lr*(p[i]-(i==1)) for i,x in enumerate(logits)]
    ref=probs(logits); stages.append({'stage':'sft','chosen_probability':ref[1]})
    beta=0.5
    for _ in range(12):
        p=probs(logits)
        margin=math.log(p[1]/p[0])-math.log(ref[1]/ref[0])
        grad=-beta/(1+math.exp(beta*margin))
        logits[1]-=lr*grad; logits[0]+=lr*grad
    stages.append({'stage':'dpo','chosen_probability':probs(logits)[1], 'reference':ref})
    rng=random.Random(7); rows=[]
    for step in range(12):
        old=probs(logits)
        actions=rng.choices([0,1],weights=old,k=16)
        rewards=[float(a==1) for a in actions]
        mean=sum(rewards)/len(rewards); std=math.sqrt(sum((r-mean)**2 for r in rewards)/len(rewards))
        advantage=[0.0 if std==0 else (r-mean)/std for r in rewards]
        # Two inner updates expose the distinction between old and current probabilities.
        for _ in range(2):
            p=probs(logits); gradient=[0.0,0.0]
            for action,a in zip(actions,advantage):
                ratio=p[action]/old[action]
                clipped=(a>0 and ratio>1.2) or (a<0 and ratio<0.8)
                if not clipped:
                    for k in range(2):gradient[k]+=-a*ratio*((k==action)-p[k])/len(actions)
            logits=[x-lr*g for x,g in zip(logits,gradient)]
        rows.append({'step':step,'zero_variance':std==0,'reward_mean':mean})
    stages.append({'stage':'grouped_policy_gradient','chosen_probability':probs(logits)[1]})
    checks={'sft_updates_policy':stages[0]['chosen_probability']>0.5,
            'dpo_improves_fixed_pair':stages[1]['chosen_probability']>stages[0]['chosen_probability'],
            'finite_normalized':all(math.isfinite(x) for x in probs(logits)) and abs(sum(probs(logits))-1)<1e-12}
    report={'status':'passed' if all(checks.values()) else 'failed','checks':checks,'stages':stages,'rollout':rows,
            'boundary':'Two-action, one-step CPU policy; beta_KL=0; not full GRPO/DAPO, not LLM capability or GPU performance.'}
    out=Path(__file__).with_name('results');out.mkdir(exist_ok=True);(out/'toy_training.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return 0 if all(checks.values()) else 1
if __name__=='__main__':raise SystemExit(main())
```

## 写在最后

同步流水线跑通后，最后一个项目把它扩展为可恢复的异步 Agentic RL 平台。下一篇：[可恢复的异步 Agentic RL 后训练平台](/source/AI-Infra/5-数据工程与后训练/36-可恢复的异步AgenticRL后训练平台)。