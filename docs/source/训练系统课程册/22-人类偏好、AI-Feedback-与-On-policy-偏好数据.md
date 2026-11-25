# 人类偏好、AI-Feedback-与-On-policy-偏好数据

偏好数据来自人类或 AI Feedback，on-policy 采样减少分布偏移。

## 1. 机制要点

- 人类偏好贵但准，AI Feedback  scalable 但有偏
- on-policy 偏好对齐当前策略，离线偏好有陈旧度

## 2. 实验闭环

```bash
python lessons/lesson-22/run.py
python lessons/lesson-22/run_gpu.py
```

- **输入**：固定 Fixture 场景集（可修改阈值/状态/样本观察验收变化）
- **输出**：结构化报告（状态/原因/检查项）与运行产物
- **验收**：人类偏好贵但准，AI Feedback  scalable 但有偏；on-policy 偏好对齐当前策略，离线偏好有陈旧度

## 3. 判读纪律

- 默认 Fixture/模拟只验证控制逻辑与合同；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置条件不足时返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 结果冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据（trace/快照/哈希）；负例与失败注入对照必做。

## 4. 与主题笔记的关系

机制与工程展开见 [AI Infra 主题笔记·22-人类偏好-AIFeedback与On-policy偏好数据](/source/AI-Infra/5-数据工程与后训练/22-人类偏好-AIFeedback与On-policy偏好数据)；本册保留课程原课次顺序，聚焦实验闭环与判读口径。
