# 项目五：GPU Fleet Planner and SLA-Aware Autoscaler

Fleet 规划两段：先用带原始证据哈希的实测容量点做 GPU 选型与装箱（fixture 容量直接拒收），再对需求时间序列跑带启动延迟、滞后与冷却的扩缩容状态机。项目级验收：fixture 容量被拒、放置满足显存/库存/SLO 约束、启动延迟被表征、当前端点被探针——用假设容量做的装箱方案在真实集群上必然落空。

## 1. 项目闭环

```bash
python project/05-fleet-planner/run.py --check-only
python project/05-fleet-planner/run.py --output results/project-05-fixture.json
python project/05-fleet-planner/run.py --real --capacity-points capacity.jsonl --demand demand.jsonl \
  --output results/gpu_result.json
```

- **输入**：实测容量点（含证据哈希）、需求时间序列、库存与 SLO 约束。
- **输出**：选型/装箱方案、扩缩容事件序列、SLO 风险窗口、探针记录。
- **验收**：fixture 容量被拒；放置满足显存/库存/SLO；启动延迟被表征；当前端点被探针。

## 2. 判读纪律

- 容量点证据哈希与原始记录绑定：无哈希的容量点按 fixture 拒收。
- 扩缩容事件附触发需求与冷却状态：无依据事件不算闭环。
- 只有 `source=measured` 的报告可用于性能或发布结论。

## 3. 关联

课次基础见本册 [24-Heterogeneous-GPU](24-Heterogeneous-GPU：逐卡容量与延迟画像)、[26-LLM-Autoscaling](26-LLM-Autoscaling：容量校准需求窗口与状态机)、[27-Capacity-Planning](27-Capacity-Planning：并发×输出长度实测矩阵)；主题展开见 [GPU Fleet Planner 与 Autoscaler](/source/AI-Infra/3-大模型推理优化工程/35-GPUFleetPlanner与Autoscaler)。