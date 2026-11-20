# GPU-资源抽象：Device-Plugin、CDI、DRA-与设备健康

GPU 资源抽象 DevicePlugin/CDI/DRA 决定设备分配与健康语义。

## 1. 机制要点

- DevicePlugin 整卡分配，CDI/DRA 支持细粒度/结构化设备
- 设备健康与故障语义影响调度可靠性

## 2. 实验闭环

```bash
python3 lessons/lesson-06/run.py
```

- **输入**：固定 Fixture 场景集（可修改阈值/状态/样本观察验收变化）
- **输出**：结构化报告（状态/原因/检查项）与运行产物
- **验收**：DevicePlugin 整卡分配，CDI/DRA 支持细粒度/结构化设备；设备健康与故障语义影响调度可靠性

## 3. 判读纪律

- 默认 Fixture/模拟只验证控制逻辑与合同；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置条件不足时返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 结果冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据（trace/快照/哈希）；负例与失败注入对照必做。

## 4. 与主题笔记的关系

机制与工程展开见 [AI Infra 主题笔记·06-GPU资源抽象-DevicePlugin-CDI-DRA与设备健康](/source/AI-Infra/4-AI平台工程/06-GPU资源抽象-DevicePlugin-CDI-DRA与设备健康)；本册保留课程原课次顺序，聚焦实验闭环与判读口径。
