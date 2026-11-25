# P-EAGLE：并行候选分支与 Target 批量验证

单链 draft 的接受率随步数衰减，P-EAGLE 用并行候选分支换覆盖：同时外推多条分支，target 一次前向批量验证所有分支位置（掩码隔离分支间注意力），逐分支接受最长正确前缀。分支数提高「至少一条分支走得远」的概率，代价是验证位置数线性增长。

![P-EAGLE：并行候选分支，Target 一次批量验证](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y13_l03_01.png)

## 1. 机制要点

- **分支并行**：各分支独立自回归外推，互不依赖，可同批发射；分支间差异来自采样或初始化扰动。
- **批量验证**：target 前向把「分支数 × 链长」个位置拼成一个 batch，用掩码保证分支间不串注意力；一次读权重服务全部候选。
- **预算约束**：验证位置数 = 分支数 × 链长，超过预算后边际收益递减；分支数不是越多越好。

## 2. 实验闭环

```bash
python lesson/03-parallel-drafter/run.py --check-only
python lesson/03-parallel-drafter/run.py --output results/lesson-03-fixture.json
python lesson/03-parallel-drafter/run.py --real --model /models/target --branches 3 --draft-tokens 4 \
  --output results/gpu_result.json
```

- **输入**：target 模型、分支数与链长配置、CUDA GPU。
- **输出**：逐分支 acceptance、批量验证耗时、端到端 token/s、cycle trace。
- **验收**：分支间掩码隔离可证（串分支的对照实验接受率异常）；输出与贪心基线一致；验证耗时随位置数线性可复算。

## 3. 判读纪律

- 报收益必须同时报验证位置数与分支数：脱离预算谈加速没有意义。
- 掩码隔离要有反证实验：故意串分支应看到接受率/输出异常，证明隔离真实生效。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

并行 drafter 与长上下文训练的机制展开见 [P-EAGLE：并行 Drafter 与长上下文训练](/source/AI-Infra/3-大模型推理优化工程/04-P-EAGLE-并行Drafter与长上下文训练)；本课聚焦分支预算与批量验证的实验口径。