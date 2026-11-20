# Heterogeneous GPU：逐卡容量与延迟画像

异构集群里不同卡型的算力/显存/带宽不同，同一模型在不同卡上的容量与延迟画像不同。本课用两个真实 device index 跑同一模型/负载，逐卡记录延迟/吞吐/显存快照，并核验记录不跨卡复制——把 A 卡数字抄给 B 卡的「异构画像」是伪造。画像差异是放置与路由决策的输入。

## 1. 机制要点

- **逐卡画像**：容量（可承载并发/序列长度）与延迟画像逐卡实测，不能按标称 FLOPS 推算冒充。
- **同模型同负载**：跨卡对比必须控制变量（同模型、同 workload），否则差异混入负载因素。
- **记录不跨卡复制**：每条记录绑定 device index；复制记录会让画像失去决策价值。

## 2. 实验闭环

```bash
python lesson/24-heterogeneous-gpu/run.py --check-only
python lesson/24-heterogeneous-gpu/run.py --output results/lesson-24-fixture.json
python lesson/24-heterogeneous-gpu/run.py --real --model /models/target --devices 0,1 \
  --output results/gpu_result.json
```

- **输入**：两个真实 device index、同一模型与 workload。
- **输出**：device profiles、latency/throughput comparison、memory snapshots。
- **验收**：两个真实 device index；同模型/负载；记录不跨卡复制。

## 3. 判读纪律

- 画像要附显存快照与计时口径：缺任一项的画像不可用于放置决策。
- 跨卡差异要解释到硬件因素（带宽/算力/显存），解释不了的差异先怀疑测量。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

异构放置与拓扑亲和的机制展开见 [Heterogeneous GPU Placement：异构设备与拓扑亲和性](/source/AI-Infra/3-大模型推理优化工程/25-HeterogeneousGPUPlacement-异构设备与拓扑亲和性)；本课聚焦逐卡画像的真实性核验。