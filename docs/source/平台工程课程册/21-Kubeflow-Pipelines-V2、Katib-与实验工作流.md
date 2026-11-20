# Kubeflow-Pipelines-V2、Katib-与实验工作流

Kubeflow Pipelines V2/Katib 把实验工作流与调参产品化。

## 1. 机制要点

- Pipelines 声明式 DAG 实验，Katib 自动调参
- 实验血缘与制品版本保证可复现

## 2. 实验闭环

```bash
python3 lessons/lesson-21/run.py
```

- **输入**：固定 Fixture 场景集（可修改阈值/状态/样本观察验收变化）
- **输出**：结构化报告（状态/原因/检查项）与运行产物
- **验收**：Pipelines 声明式 DAG 实验，Katib 自动调参；实验血缘与制品版本保证可复现

## 3. 判读纪律

- 默认 Fixture/模拟只验证控制逻辑与合同；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置条件不足时返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 结果冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据（trace/快照/哈希）；负例与失败注入对照必做。

## 4. 与主题笔记的关系

机制与工程展开见 [AI Infra 主题笔记·21-KubeflowPipelinesV2-Katib与实验工作流](/source/AI-Infra/4-AI平台工程/21-KubeflowPipelinesV2-Katib与实验工作流)；本册保留课程原课次顺序，聚焦实验闭环与判读口径。
