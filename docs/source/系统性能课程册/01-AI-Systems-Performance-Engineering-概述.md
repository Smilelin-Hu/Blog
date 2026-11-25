# AI-Systems-Performance-Engineering-概述

性能工程的目标是把「GPU 很忙」变成「系统真的更快」：区分利用率与有效产出。

## 1. 机制要点

- GPU-Util 高不等于 MFU 高，需看有效 FLOPs 与带宽利用
- 先测量再定位，一次只改一处并复测

## 2. 实验闭环

```bash
python 运行本课.py
```

- **输入**：固定 Fixture 场景集（可修改阈值/状态/样本观察验收变化）
- **输出**：结构化报告（状态/原因/检查项）与运行产物
- **验收**：GPU-Util 高不等于 MFU 高，需看有效 FLOPs 与带宽利用；先测量再定位，一次只改一处并复测

核心代码优先 CPU/通用回退路径；涉及 PyTorch/GPU/CUDA/NVLink/K8s 的能力需具备对应软硬件环境运行，结果见 03_运行结果。

## 3. 判读纪律

- 默认 Fixture/模拟只验证控制逻辑与合同；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置条件不足时返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 结果冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据（trace/快照/哈希）；负例与失败注入对照必做。

## 4. 与主题笔记的关系

机制与工程展开见 [AI Infra 主题笔记·01-AI-Systems-Performance-Engineering概述](/source/AI-Infra/2-AI系统性能工程/01-AI-Systems-Performance-Engineering概述)；本册保留课程原课次顺序，聚焦实验闭环与判读口径。
