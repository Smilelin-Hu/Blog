# 可按显存缩放的-SFT-到-DPO-到-GRPO-RLVR-流水线

可按显存缩放的 SFT→DPO→GRPO/RLVR 流水线：按资源选算法与并行。

## 1. 机制要点

- 显存预算决定算法族（离线偏好 vs 在线 RL）与并行配置
- 流水线各阶段检查点衔接可恢复

## 2. 实验闭环

```bash
python projects/project-05/run.py
python projects/project-05/run_gpu.py
```

- **输入**：固定 Fixture 场景集（可修改阈值/状态/样本观察验收变化）
- **输出**：结构化报告（状态/原因/检查项）与运行产物
- **验收**：显存预算决定算法族（离线偏好 vs 在线 RL）与并行配置；流水线各阶段检查点衔接可恢复

## 3. 判读纪律

- 默认 Fixture/模拟只验证控制逻辑与合同；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置条件不足时返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 结果冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据（trace/快照/哈希）；负例与失败注入对照必做。

## 4. 与主题笔记的关系

机制与工程展开见 [AI Infra 主题笔记·35-可按显存缩放的SFT到DPO到GRPORLVR流水线](/source/AI-Infra/5-数据工程与后训练/35-可按显存缩放的SFT到DPO到GRPORLVR流水线)；本册保留课程原课次顺序，聚焦实验闭环与判读口径。
