# Kubernetes-调度器与-AI-资源碎片

K8s 调度器与 AI 资源碎片：大块 gang 需求与碎片矛盾。

## 1. 机制要点

- 默认调度器不感知 gang/拓扑，AI 作业易碎片化
- 碎片治理需装箱与预留策略

## 2. 实验闭环

```bash
python3 lessons/lesson-10/run.py
```

- **输入**：固定 Fixture 场景集（可修改阈值/状态/样本观察验收变化）
- **输出**：结构化报告（状态/原因/检查项）与运行产物
- **验收**：默认调度器不感知 gang/拓扑，AI 作业易碎片化；碎片治理需装箱与预留策略

## 3. 判读纪律

- 默认 Fixture/模拟只验证控制逻辑与合同；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置条件不足时返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 结果冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据（trace/快照/哈希）；负例与失败注入对照必做。

## 4. 与主题笔记的关系

机制与工程展开见 [AI Infra 主题笔记·10-Kubernetes调度器与AI资源碎片](/source/AI-Infra/4-AI平台工程/10-Kubernetes调度器与AI资源碎片)；本册保留课程原课次顺序，聚焦实验闭环与判读口径。
