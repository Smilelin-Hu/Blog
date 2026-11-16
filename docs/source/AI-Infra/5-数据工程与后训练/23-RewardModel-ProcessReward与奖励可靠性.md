# Reward Model、Process Reward 与奖励可靠性

## 1. 本文要解决的工程问题

优化过程会暴露离线评测没有覆盖的漏洞。

Reward Model 在验证集上准确率很高，策略训练后却学会输出更长、格式更讨巧的回答。模型优化了奖励代理，并没有改善目标行为。

本文围绕一个可执行判断展开：怎样训练和审计 Reward Model 与 Process Reward，降低奖励投机和分布外失真？读完应能给出自己的系统边界、输入输出、版本关系和验收证据，而不是只复述工具名称或公式。

![Reward Model 与奖励可靠性](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l23_01.png)

## 2. 本文交付物与判定标准

本文的核心决定是：分开 Outcome Reward、Process Reward、规则奖励和可验证奖励，建立校准、切片、对抗与策略外分布测试。

完成学习和实验后，应当交付一份最小可复现记录，至少包含输入快照、配置、代码版本、运行状态、原始输出和结论边界。验收证据是：奖励模型报告成对准确率、校准、长度偏差、对抗集和策略版本迁移；PRM 还要核对步骤边界与标签。

围绕“Reward Model、Process Reward 与奖励可靠性”的验收不接受三类替代品：把模拟输出写成真实 GPU 结果；只展示成功样本而隐藏失败与 `SKIPPED`；只给总分，不保存能复算总分的对象级记录。

## 3. 前置知识与实验边界

“Reward Model、Process Reward 与奖励可靠性”的机制实验使用 Python 3.10 及以上版本和标准库，重点验证对象、算法或状态转换。真实硬件路径使用 PyTorch；检测不到 CUDA 时必须输出结构化 `SKIPPED`，不得静默改跑 CPU 后仍标成 GPU 实测。

Reward 是可审计的训练信号，不是目标行为的完整定义。

### 3.1 业务背景与失败模式

Reward Model 把 Prompt 与响应映射为标量，用于排序、拒绝采样、离线偏好优化或在线 RL。它通常从人类或 AI 偏好学习，因此继承标签的维度、噪声、位置、长度、策略和时间分布。高 Reward 只表示模型在当前训练与校准范围内预测更受偏好，不证明事实正确、安全或产品成功。策略一旦针对 Reward 优化，训练分布会移动并主动寻找漏洞，这使 Reward 可靠性成为持续对抗问题。

Outcome Reward 评价最终结果，Process Reward 评价中间步骤或状态。结果奖励便宜、适合可验证任务，却无法区分偶然正确与可靠推理；过程奖励能定位首错并提供密集信号，却更难标注、对步骤切分敏感，也可能奖励漂亮但无因果作用的轨迹。生产系统通常把执行器、规则、Reward Model、Process Reward、KL 与硬安全约束组合，而不是把所有价值压进一个浮点数。

### 3.2 输入契约

输入包含 Prompt、候选、工具状态、证据、Template 与策略版本。训练与推理渲染必须一致，截断和隐藏信息会改变分数语义。

### 3.3 标量输出

绝对分数可排序但跨版本、任务和长度未必可比。保存原始 Logit、校准分、分项 Reward、拒判和硬规则状态。

### 3.4 Pairwise 训练

常用目标使 chosen 分数高于 rejected，例如负对数 Sigmoid Margin。标签强度、平局与多维冲突需要显式处理。

### 3.5 Pointwise 训练

回归绝对等级或通过概率，适合阈值和缓存，但标尺漂移与不同标注者尺度更明显。需要校准和分桶。

### 3.6 Reward 发布

权重、Tokenizer、Template、训练偏好发布、损失、校准集、阈值、指标、适用范围和已知漏洞共同构成不可变 Reward 版本。

### 3.7 数据分割

按 Prompt 簇、父事件、策略和时间分割，防同一任务变体跨训练验证。最终盲测与 Reward 选择过程隔离。

### 3.8 候选平衡

控制长度、策略、风格、语言和难度，避免 Reward 用捷径。保留易对稳定基础、难对学习边界和平局校准。

### 3.9 损失与 Margin

Pairwise Loss 可写为负的 log-sigmoid 分差。增加 Margin 或权重可以表达强偏好，但标签强度必须校准，不能直接用 Judge 自信。

### 3.10 正则与容量

过大模型更能拟合标签也更能记忆与学习捷径；过小模型欠拟合专业边界。使用早停、权重衰减、多种子和独立分层评测。

### 3.11 校准

排序准确不说明阈值概率可靠。使用独立金标做温度、等距或其他校准，按任务、语言和风险检查误差。

## 4. Process Reward

### 4.1 步骤切分

按自然推理句、程序语句、工具事件或环境状态切分。切分改变标签粒度和信用分配，必须版本化。

### 4.2 首错标签

定位第一个使轨迹偏离正确性的步骤。后续步骤可能形式正确但建立在错误状态上，不能洗掉首错。

### 4.3 每步正确与进展

正确性判断本步是否有效，进展判断是否朝目标推进。重复正确常识可能正确却无进展，二者分项更可靠。

### 4.4 过程验证器

数学可用符号与数值检查，代码用执行与状态，工具用模拟器，开放推理用模型与专家。不同证据强度单列。

### 4.5 聚合轨迹 Reward

可取最后、最小、总和、折扣和或学习聚合。最小强调任何严重错误，总和可能让大量小正分补偿致命错误；硬门槛与训练目标需匹配。

## 5. Reward 可靠性

![Reward 可靠性评审](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y5_l23_02.png)

奖励模型给出的高分不是正确性的同义词。可靠性评审要同时观察分布内排序、分布外漂移、代理漏洞和策略优化后的反馈变化。

均值准确不能覆盖尾部攻击与稀有任务。

### 5.1 分布内准确

在与训练相似的策略与 Prompt 上比较排序、校准和分桶。它是基础，不代表优化后可靠。

### 5.2 分布外泛化

新策略、长答案、新语言、新工具和对抗风格测试。Reward 用于策略优化时，新策略分布尤其关键。

### 5.3 Goodhart 效应

指标被当目标后会失去测量质量。Best-of-N 与 RL 都增加搜索强度，微小偏差会被放大。扩大 N 必须配独立审核。

### 5.4 Reward Hacking

策略利用长度、关键词、格式、引用、重复、拒答或验证器缺口获得高分。红队样本与策略生成数据持续回流 Reward 评测，但不得无门禁自动训练。

### 5.5 Reward Overoptimization

代理 Reward 继续上升而真实人类或任务质量达到峰值后下降。需要代理—真实曲线、KL 或更新限制、早停与独立 Judge。

## 6. CPU 机制实验：Reward Hacking 曲线

### 随包实验的运行入口与边界

本文可直接运行的入口在实验包的 `lessons/lesson-23/`。正文中的生产架构、建议目录和框架示例用于解释机制与扩展设计，不代表这些生产系统已经随包实现。所有原有代码围栏另存于该目录的 `examples/`，文件以 `.txt` 结尾，便于逐字对照。

```bash
python lessons/lesson-23/run.py
python lessons/lesson-23/run_gpu.py
```

第一条命令读取固定反例并输出机制检查。第二条只运行单进程 CUDA 基础探针，不是本文完整数据平台或训练算法；没有 CUDA 时输出 `skipped`。通过探针不能证明 DDP、模型质量、集群吞吐或端到端恢复。真实系统扩展需要另外实现正文所列模块，并在自己的模型、数据和硬件上验收。

完整入口脚本保存在实验包同名文件中；阅读时从入口追到共享机制函数，再对照 fixture 与结果检查项。

### 6.1 目标

模拟真实质量、长度偏差与 Best-of-N 选择，观察 N 增大时代理 Reward 上升而真实质量可能下降，并用去偏 Reward 对照。

```python
import json
import random
import statistics

def sample(rng):
    quality = rng.gauss(0.0, 1.0)
    length = max(0.0, rng.gauss(1.0, 0.55))
    proxy = quality + 0.55 * length + rng.gauss(0.0, 0.35)
    debiased = quality + rng.gauss(0.0, 0.35)
    return {"quality": quality, "length": length, "proxy": proxy, "debiased": debiased}

def run(n, score_key, trials=4000):
    rng = random.Random(20260822 + n + len(score_key))
    chosen = []
    for _ in range(trials):
        pool = [sample(rng) for _ in range(n)]
        chosen.append(max(pool, key=lambda x: x[score_key]))
    return {
        "n": n,
        "selector": score_key,
        "mean_proxy": statistics.mean(x["proxy"] for x in chosen),
        "mean_true_quality": statistics.mean(x["quality"] for x in chosen),
        "mean_length": statistics.mean(x["length"] for x in chosen),
    }

def main():
    rows = [run(n, key) for key in ["proxy", "debiased"] for n in [1, 2, 4, 8, 16, 32]]
    print(json.dumps({"status": "passed",
                      "claim_boundary": "synthetic reward-hacking mechanism only",
                      "results": rows}, ensure_ascii=False, indent=2))

if __name__ == "__main__": main()
```

### 6.2 解释

原始代理包含长度偏差，N 越大越容易选到靠长度和噪声得高分的候选。去偏代理更接近真实质量，但仍有噪声，极大搜索仍可能过优化。真实系统必须用人工、执行和独立 Reward 绘制搜索强度曲线。

## 7. 通用 CUDA Reward 训练路径

### 7.1 目标

使用一个或多个 Rank 训练小型 Pairwise Reward 网络，聚合准确、Margin 和 Token，输出结构化资源状态。缺 CUDA 或本地 CUDA 时 `skipped`，不伪造生产模型结果。

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
        nn.Linear(64, 128), nn.GELU(), nn.Linear(128, 1)).to(device), device_ids=[local])
    opt = torch.optim.AdamW(model.parameters(), lr=8e-4)
    stats = torch.zeros(3, dtype=torch.float64, device=device)
    try:
        for step in range(160):
            g = torch.Generator(device=device); g.manual_seed(rank * 100000 + step)
            c = torch.randn(16, 64, generator=g, device=device) + 0.12
            r = torch.randn(16, 64, generator=g, device=device) - 0.12
            margin = model(c).squeeze(-1) - model(r).squeeze(-1)
            loss = -torch.nn.functional.logsigmoid(margin).mean()
            opt.zero_grad(set_to_none=True); loss.backward(); opt.step()
            stats += torch.tensor([float(loss.item()), float((margin > 0).sum()), margin.numel()], device=device)
        dist.all_reduce(stats)
        if rank == 0:
            print(json.dumps({"status": "passed", "mean_rank_loss": float(stats[0] / 320),
                              "pair_accuracy": float(stats[1] / stats[2]),
                              "pairs": int(stats[2]),
                              "peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
                              "claim_boundary": "synthetic two-GPU reward control path only"}))
    except torch.cuda.OutOfMemoryError as exc:
        if rank == 0: print(json.dumps({"status": "skipped", "reason": f"CUDA OOM: {exc}"}))
    finally:
        dist.destroy_process_group()

if __name__ == "__main__": main()
```

### 7.2 真实替换

替换为许可明确的小语言模型、冻结偏好发布和独立策略候选，按 Prompt 簇与策略时间分割。比较基础 Reward、长度匹配、分项 Reward 与 Process Reward，报告分布内、策略外、Best-of-N、校准和红队。本地 CUDA 只适合 Canary，目标规模需真实环境。

## 8. 八十个 Reward 控制点

### 8.1 目标先分维度

事实、帮助、安全、风格、成本和工具成功分开。不可补偿风险不用一个总 Reward 掩盖。

### 8.2 输入上下文一致

训练与服务使用相同系统、Template、工具和证据。隐藏字段差异会制造 Reward 分布漂移。

### 8.3 权重身份不可变

模型摘要、Tokenizer、Head、精度和转换共同标识 Reward。别名不是评测证据。

### 8.4 数据发布冻结

Prompt、候选、标签、强度、平局、策略和来源形成不可变输入。修正创建新版本。

### 8.5 按 Prompt 簇分割

同一任务变体不能跨训练验证。按父事件、策略与时间进一步隔离，降低近邻泄漏。

### 8.6 策略分层分割

验证包含训练策略、未见策略和优化后策略。只测同源候选会高估泛化。

### 8.7 时间分割

政策、工具和 Prompt 变化需要未来切片。旧金标不自动代表当前。

### 8.8 Pair 方向 Canary

已知 chosen/rejected 对在数据适配、Shuffle 和 Loss 前后保持方向。一次颠倒会系统训练反 Reward。

### 8.9 平局显式处理

丢弃、零 Margin、弱权重或绝对评分按算法定义。随机方向制造噪声。

### 8.10 拒判不训练

测量未知不能成为任一方向。保留用于 Judge 与数据改进。

### 8.11 同坏先过滤

两个候选都违反硬门槛时不产生正例。Reward 只在可接受域学习细分。

### 8.12 同好用于校准

两个都好可训练小 Margin 或平局，避免 Reward 把合法答案拉开过大。

### 8.13 长度匹配

同任务内控制 Token 或构造反偏对，防 Reward 把详细误作质量。

### 8.14 策略身份盲化

模型名称不进入输入。风格指纹仍需交叉策略 Canary 评估。

### 8.15 引用真实性硬验

虚构引用不能因格式权威得分。存在、相关和蕴含分别检查。

### 8.16 执行器优先

代码、数学、SQL 和工具用确定结果做硬或分项 Reward，语言模型不覆盖可验证事实。

### 8.17 文档证据优先

条件问答按冻结证据与版本判断。Reward 世界知识冲突时不替代当前文档。

### 8.18 安全硬约束

严重危险、秘密和权限越界独立门禁。总分高不能补偿。

### 8.19 多语校准

每种关键语言有金标、阈值和偏差报告。统一分数尺度会误伤低资源语言。

### 8.20 难度分层

易对、边界对、平局和不可判分开。总体准确会被易对支配。

### 8.21 Prompt 长度分层

长上下文和工具历史容易截断与位置漂移。按长度分位测 Reward。

### 8.22 响应长度分层

报告短、中、长准确、校准与分数斜率。单一平均掩盖长度 Reward。

### 8.23 多轮分层

## 写在最后

奖励信号之外，还可以直接用偏好对做离线优化。下一篇：[DPO、IPO、KTO、ORPO、SimPO 与离线偏好系统](/source/AI-Infra/5-数据工程与后训练/24-DPO-IPO-KTO-ORPO-SimPO与离线偏好系统)。