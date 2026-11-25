# DFlare：Drafter 特征融合的层数扩展

DFlare 研究 drafter 特征融合的层数扩展：融合更多 target 层能否持续提高接受率，还是存在 latency knee（延迟拐点）。层数增加带来特征信息增益，也带来融合层计算与显存开销；本课用 fusion sweep 把「层数—接受率—延迟」三条曲线放在一起找拐点。

## 1. 机制要点

- **层数扩展**：从单层到多层融合，draft 输入信息量递增；增益边际递减而成本线性递增。
- **latency knee**：draft 侧延迟随层数增长的拐点是部署上限——超过拐点后接受率增益换不回延迟代价。
- **norm 统计**：各层 hidden 的 norm 分布差异决定融合前是否需要归一化对齐，否则大 norm 层会主导融合输出。

## 2. 实验闭环

```bash
python lesson/06-dflare-scaling/run.py --check-only
python lesson/06-dflare-scaling/run.py --output results/lesson-06-fixture.json
python lesson/06-dflare-scaling/run.py --real --model /models/target --output results/gpu_result.json
```

- **输入**：target 模型、融合层数扫描配置、CUDA GPU。
- **输出**：fusion sweep、latency knee、norm statistics。
- **验收**：每个扫描点同一输入；层数真实变化（配置可追溯）；不发明质量分数（无自造评分）。

## 3. 判读纪律

- 拐点要在曲线上可见：只报「层数越多越好」或单点最优都不接受。
- norm 统计是融合设计的前置证据：跳过它直接调层数，等于在不对齐的特征上做加法。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

特征融合路径的基线见本册 [02-EAGLE-3](/source/推理优化课程册/02-EAGLE-3：多层Target特征抽取与融合)；层数扩展的成本模型对照 [AI 系统性能工程](/source/AI-Infra/2-AI系统性能工程/README) 的数量级估算方法。