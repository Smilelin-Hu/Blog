# Diffusion Draft Tree：树预算、叶路径与批量验证

扩散式草稿把候选组织成树：从根出发按扩散步展开分支，叶路径即候选序列，target 一次批量验证所有叶。树预算（节点数上限）决定验证成本；树结构必须无环、叶路径可重建、所有叶都参与验证，否则接受率数字不可信。

![树状草稿：一次验证覆盖多条候选路径](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y3_l08_03.png)

## 1. 机制要点

- **树预算**：节点总数上限约束验证 batch 大小；预算内如何分配宽度/深度决定覆盖形状。
- **叶路径可重建**：每条叶到根的路径必须能由 trace 重建，接受判定才有依据。
- **全叶验证**：漏验任何叶都会让 acceptance 虚高（未验叶被默认接受或默认拒绝都失真）。

## 2. 实验闭环

```bash
python lesson/07-diffusion-tree/run.py --check-only
python lesson/07-diffusion-tree/run.py --output results/lesson-07-fixture.json
python lesson/07-diffusion-tree/run.py --real --model /models/target --output results/gpu_result.json
```

- **输入**：target 模型、树预算与扩散步配置、CUDA GPU。
- **输出**：tree topology、leaf acceptance、verification latency。
- **验收**：树无环；每条叶路径可重建；所有叶都被验证。

## 3. 判读纪律

- 拓扑验收先于性能验收：有环或漏验的树，其 acceptance 与延迟数字一律作废。
- 报 acceptance 要附叶路径重建证据（trace ID 链），单数字不接受。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

树验证与扩散草稿的机制展开见 [DDTree：Diffusion Draft Tree 与树验证](/source/AI-Infra/3-大模型推理优化工程/08-DDTree-DiffusionDraftTree与树验证)；本课聚焦树拓扑与全叶验证的实验验收。