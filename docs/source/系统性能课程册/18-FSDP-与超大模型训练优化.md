# FSDP-与超大模型训练优化

FSDP 分片参数/梯度/优化器状态降显存，按需 AllGather。

![FSDP-与超大模型训练优化](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l18_02.png)

## 1. 机制要点

- 分片降常驻显存，峰值仍含临时完整组
- reshard/预取权衡显存与通信

## 2. 实验闭环

```bash
python 运行本课.py
```

- **输入**：固定 Fixture 场景集（可修改阈值/状态/样本观察验收变化）
- **输出**：结构化报告（状态/原因/检查项）与运行产物
- **验收**：分片降常驻显存，峰值仍含临时完整组；reshard/预取权衡显存与通信

核心代码优先 CPU/通用回退路径；涉及 PyTorch/GPU/CUDA/NVLink/K8s 的能力需具备对应软硬件环境运行，结果见 03_运行结果。

## 3. 判读纪律

- 默认 Fixture/模拟只验证控制逻辑与合同；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置条件不足时返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 结果冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据（trace/快照/哈希）；负例与失败注入对照必做。

## 4. 与主题笔记的关系

机制与工程展开见 [AI Infra 主题笔记·18-FSDP与超大模型训练优化](/source/AI-Infra/2-AI系统性能工程/18-FSDP与超大模型训练优化)；本册保留课程原课次顺序，聚焦实验闭环与判读口径。
