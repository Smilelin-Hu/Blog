# RLVR、环境、拒绝采样与-Agentic-数据飞轮

RLVR 用可验证奖励 + 环境交互，拒绝采样与 Agentic 飞轮扩数据。

## 1. 机制要点

- 可验证奖励（数学/代码）免奖励模型 hacking
- 拒绝采样筛正确轨迹，Agentic 飞轮闭环扩池

## 2. 实验闭环

```bash
python lessons/lesson-26/run.py
python lessons/lesson-26/run_gpu.py
```

- **输入**：固定 Fixture 场景集（可修改阈值/状态/样本观察验收变化）
- **输出**：结构化报告（状态/原因/检查项）与运行产物
- **验收**：可验证奖励（数学/代码）免奖励模型 hacking；拒绝采样筛正确轨迹，Agentic 飞轮闭环扩池

## 3. 判读纪律

- 默认 Fixture/模拟只验证控制逻辑与合同；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置条件不足时返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 结果冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据（trace/快照/哈希）；负例与失败注入对照必做。

## 4. 与主题笔记的关系

机制与工程展开见 [AI Infra 主题笔记·26-RLVR-环境-拒绝采样与Agentic数据飞轮](/source/AI-Infra/5-数据工程与后训练/26-RLVR-环境-拒绝采样与Agentic数据飞轮)；本册保留课程原课次顺序，聚焦实验闭环与判读口径。
