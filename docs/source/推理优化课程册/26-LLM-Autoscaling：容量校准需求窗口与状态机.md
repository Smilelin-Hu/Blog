# LLM Autoscaling：容量校准、需求窗口与状态机

 autoscaling 的决策链是「实测单副本容量 → 需求窗口估计 → 状态机扩缩」。三个环节都可能失真：容量用标称值而非实测、需求窗口忽略启动延迟、缩容不用滞回导致振荡。本课核验容量来源为 measured、启动延迟显式计入、缩容带滞回——三者缺一，扩缩容要么慢半拍要么来回抖。

## 1. 机制要点

- **容量实测**：单副本容量（可承载并发/Token 率）必须实测校准，标称值会把需求换算错。
- **启动延迟显式**：扩容决策到副本就绪之间有启动延迟；需求窗口必须提前覆盖这段时间，否则 SLO 风险窗口出现。
- **缩容滞回**：缩容阈值与窗口宽于扩容（滞回），避免负载抖动引起扩缩振荡。

## 2. 实验闭环

```bash
python lesson/26-autoscaling/run.py --check-only
python lesson/26-autoscaling/run.py --output results/lesson-26-fixture.json
python lesson/26-autoscaling/run.py --real --endpoint http://serving:8000 --output results/gpu_result.json
```

- **输入**：serving 端点、负载曲线（含突发与回落）、启动延迟配置。
- **输出**：measured replica capacity、scale events、SLO risk windows。
- **验收**：容量来源 measured；启动延迟显式；缩容用滞回。

## 3. 判读纪律

- scale events 要附触发时的需求估计与容量快照：无依据的扩缩不算闭环。
- SLO risk windows 要量化（窗口时长×违约程度），只报「有风险」不接受。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

 autoscaling 机制展开见 [LLM Autoscaling：Queue、Token 与 SLA-aware Planner](/source/AI-Infra/3-大模型推理优化工程/27-LLMAutoscaling-Queue-Token与SLA-awarePlanner)；本课聚焦容量校准与滞回状态的实验核验。