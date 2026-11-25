# DSpark：按 Draft 置信度决定是否提议

不是每个位置都值得投机：draft 置信度低的位置提议大概率被拒，白白付验证成本。DSpark 用 draft logits 的置信度做门控——置信度高于阈值才提议，否则回退普通自回归步。阈值扫描给出 coverage（提议覆盖率）与 agreement（提议被接受比例）的权衡曲线。

## 1. 机制要点

- **置信度来源**：必须来自 draft logits（如 top-1 概率或熵），不能用外部启发式冒充。
- **agreement 来源**：必须来自 target 验证结果，不能用 draft 自评冒充接受率。
- **阈值语义**：阈值改变的是「是否提议」的决策；coverage 与 agreement 随阈值反向变化，最优点由净收益决定。

## 2. 实验闭环

```bash
python lesson/08-confidence-scheduler/run.py --check-only
python lesson/08-confidence-scheduler/run.py --output results/lesson-08-fixture.json
python lesson/08-confidence-scheduler/run.py --real --model /models/target --draft-model /models/draft \
  --output results/gpu_result.json
```

- **输入**：draft/target 模型、阈值扫描网格、CUDA GPU。
- **输出**：prefix-level labels、threshold sweep、coverage/agreement curve。
- **验收**：置信度来自 Draft logits；agreement 来自 Target；阈值变化真实改变决策。

## 3. 判读纪律

- 两个来源缺一不可：置信度非 draft logits、或 agreement 非 target 验证，实验即无效。
- 阈值扫描要附决策变化证据（同一前缀在不同阈值下提议/不提议），证明门控真实生效。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

置信度门控与调度策略的展开见 [DSpark：置信度调度与负载感知验证](/source/AI-Infra/3-大模型推理优化工程/09-DSpark-置信度调度与负载感知验证)；本课聚焦 coverage/agreement 权衡的实验口径。