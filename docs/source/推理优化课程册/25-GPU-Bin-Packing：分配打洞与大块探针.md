# GPU Bin Packing：分配、打洞与大块探针

KV/显存分配器在长期运行后产生碎片：总空闲够但连续大块不够，大请求分配失败。本课用有界分配预算做分配/释放序列，记录碎片代理指标与清理证明，核验每次 free 都被记录、终态 allocated 回到基线附近——free 漏记会让碎片指标虚高或虚低，清理证明缺失则「碎片治理」无法验收。

## 1. 机制要点

- **碎片代理**：用「最大可分配连续块 / 总空闲」等代理指标刻画碎片；代理口径要声明。
- **free 全记录**：每次释放留痕（块 ID/大小/时点），漏记的 free 会让快照与真实状态脱节。
- **清理证明**：实验终态 allocated 回到基线附近，证明分配/释放闭环无泄漏；不回基线说明有漏 free 或泄漏。

## 2. 实验闭环

```bash
python lesson/25-fragmentation/run.py --check-only
python lesson/25-fragmentation/run.py --output results/lesson-25-fixture.json
python lesson/25-fragmentation/run.py --real --budget-gb 24 --output results/gpu_result.json
```

- **输入**：有界分配预算、分配/释放序列（含大块探针）。
- **输出**：allocator snapshots、fragmentation proxy、cleanup proof。
- **验收**：分配预算有界；每次 free 被记录；终态 allocated 接近基线。

## 3. 判读纪律

- 碎片结论要附快照序列：单点碎片值无法区分稳态碎片与瞬时打洞。
- 大块探针失败要归因到碎片而非总量：总空闲够而大块失败才是碎片问题。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

Bin packing 与放置算法的机制展开见 [GPU Bin Packing：并行组、碎片与放置算法](/source/AI-Infra/3-大模型推理优化工程/26-GPUBinPacking-并行组-碎片与放置算法)；本课聚焦分配器闭环与清理证明的实验口径。