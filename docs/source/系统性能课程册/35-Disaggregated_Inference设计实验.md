# Disaggregated_Inference设计实验

Disaggregated Inference 设计实验：PD 分离容量与 KV 传输建模。

![Disaggregated_Inference设计实验](https://raw.gitcode.com/weixin_42917352/image-host/raw/main/images/aiinfra_y2_l35_02.png)

## 1. 机制要点

- 分离容量按两阶段独立算
- KV 传输带宽是可行性约束

## 2. 实验闭环

```bash
python 运行本课.py
```

- **输入**：固定 Fixture 场景集（可修改阈值/状态/样本观察验收变化）
- **输出**：结构化报告（状态/原因/检查项）与运行产物
- **验收**：分离容量按两阶段独立算；KV 传输带宽是可行性约束

项目产物见 01_项目文件/reports；结论需带证据与口径。

## 3. 判读纪律

- 默认 Fixture/模拟只验证控制逻辑与合同；真实路径（`--real`/GPU）才产生可用于性能或发布结论的测量。
- 前置条件不足时返回 SKIPPED/precondition_failed 并说明原因，不以模拟或 CPU 结果冒充实测。
- 报告区分 PASS/FAIL/SKIPPED 并附原因与证据（trace/快照/哈希）；负例与失败注入对照必做。

## 4. 与主题笔记的关系

机制与工程展开见 [AI Infra 主题笔记·35-DisaggregatedInference系统设计](/source/AI-Infra/2-AI系统性能工程/35-DisaggregatedInference系统设计)；本册保留课程原课次顺序，聚焦实验闭环与判读口径。
