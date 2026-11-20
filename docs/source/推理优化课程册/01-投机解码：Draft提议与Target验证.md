# 投机解码：Draft 提议与 Target 验证

投机解码把「串行逐 token 生成」改成「便宜模型提议、目标模型一次验证」：draft 先给出 k 个候选 token，target 用一次前向并行算出这 k 个位置的分布，接受最长正确前缀并补一个修正 token。收益来自一次读权重服务多个候选位置，代价是 draft 开销与被拒绝候选的浪费。

![串行 Decode 四次前向 vs 推测解码一次验证](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l26_02.png)

## 1. 机制要点

- **接受规则**：贪心场景下候选 token 与 target 贪心输出逐位比对，接受最长一致前缀；采样场景用拒绝采样保证分布不变。
- **正确性底线**：投机解码不改变 target 的输出分布，任何「加速但输出变了」的实现都是错的。
- **收益模型**：净加速 ≈ 接受期望长度 / (1 + draft 相对成本)；接受率低或 draft 太重时收益为负。

## 2. 实验闭环

```bash
python lesson/01-speculative-decode/run.py --check-only
python lesson/01-speculative-decode/run.py --output results/lesson-01-speculative-decode-fixture.json
python lesson/01-speculative-decode/run.py --real --model /models/target --draft-model /models/draft --draft-tokens 4 \
  --output results/gpu_result.json
```

- **输入**：兼容的 draft 与 target 模型、CUDA GPU。
- **输出**：cycle trace、acceptance rate、baseline/candidate token IDs。
- **验收**：两个不同模型输入；candidate 与贪心 target 基线逐 token 一致；acceptance 可由 trace 复算。

## 3. 判读纪律

- 一致性验收优先于速度验收：先证「输出不变」，再谈「快了多少」。
- acceptance 必须附 trace 可复算，单跑一个数字不接受。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2，不以 CPU 结果冒充。

## 4. 与主题笔记的关系

机制与性能模型的展开见 [Speculative Decoding 与推理加速](/source/AI-Infra/2-AI系统性能工程/26-SpeculativeDecoding与推理加速)；本课聚焦 Draft/Target 闭环的实验验收口径。