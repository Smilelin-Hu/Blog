# Multi-Model Pool：热门模型突发与冷模型穿插

模型池同时驻留多个模型：热门模型承受突发流量，冷模型偶发请求触发装载/换出。本课用「热突发 + 冷穿插」混合负载观察池行为：逐模型表现、首 hit 与 warm 请求的差异、以及冷模型请求是否把热模型挤出去（换出抖动）。结果必须按模型分组，聚合数字会掩盖冷启动对热模型的伤害。

## 1. 机制要点

- **热冷混合**：热模型突发考验批处理与显存驻留；冷模型穿插考验装载/换出策略。
- **首 hit vs warm**：冷模型首请求含装载成本，warm 请求不含；两者混报会低估冷启动代价。
- **换出抖动**：池容量不足时冷请求触发换出热模型，热模型后续请求再付装载成本——抖动是池容量的红线信号。

## 2. 实验闭环

```bash
python lesson/19-model-pool/run.py --check-only
python lesson/19-model-pool/run.py --output results/lesson-19-fixture.json
python lesson/19-model-pool/run.py --real --endpoint http://pool:8000 --hot-model m-hot --cold-models m-c1,m-c2 \
  --output results/gpu_result.json
```

- **输入**：模型池端点、热模型与冷模型集、混合负载序列。
- **输出**：workload mix、per-model summaries、first-hit versus warm records。
- **验收**：多模型被请求；热冷流量都存在；结果按模型分组。

## 3. 判读纪律

- 首 hit 与 warm 分开报：冷启动代价只出现在首 hit，混报即失真。
- 换出抖动要有证据：热模型在冷请求后出现装载延迟尖峰才算抖动成立。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

模型池与驻留策略的机制展开见主题三 [Multi-Model Serving：热冷模型与稀疏流量](/source/AI-Infra/3-大模型推理优化工程/20-Multi-ModelServing-热冷模型与稀疏流量)；本课聚焦热冷混合与首 hit 口径。