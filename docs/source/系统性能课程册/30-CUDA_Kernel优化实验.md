# CUDA_Kernel优化实验

CUDA Kernel 优化实验：从 naive 到融合/共享/向量化迭代。

## 1. 机制要点

- 每轮只改一处并复测，roofline 定位
- 正确性先于性能

## 2. 实验闭环

```bash
python 运行本课.py
```

- **输入**：固定 Fixture 场景集（可修改阈值/状态/样本观察验收变化）
- **输出**：结构化报告（状态/原因/检查项）与运行产物
- **验收**：每轮只改一处并复测，roofline 定位；正确性先于性能

项目产物见 01_项目文件/reports；结论需带证据与口径。

## 3. 判读纪律

- 默认 Fixture/模拟只验证控制逻辑与合同；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置条件不足时返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 结果冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据（trace/快照/哈希）；负例与失败注入对照必做。

## 4. 与主题笔记的关系

机制与工程展开见 [AI Infra 主题笔记·30-CUDAKernel优化项目](/source/AI-Infra/2-AI系统性能工程/30-CUDAKernel优化项目)；本册保留课程原课次顺序，聚焦实验闭环与判读口径。
