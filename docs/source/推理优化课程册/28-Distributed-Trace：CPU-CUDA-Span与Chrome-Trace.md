# Distributed Trace：PyTorch CPU/CUDA Span 与 Chrome Trace

性能归因依赖 trace：PyTorch profiler 产出 CPU/CUDA span，导出 Chrome Trace JSON 供可视化与复算。本课核验 trace 含真实 CUDA activity、产物非空、top CUDA 算子表来自当次运行（而非缓存/上次产物）。拿旧 trace 的算子表解释新运行的延迟，是归因错误的高发来源。

## 1. 机制要点

- **CUDA activity 必需**：只有 CPU span 的 trace 看不到 kernel 执行与空隙，归因不成立。
- **产物完整性**：trace JSON 非空且 SHA-256 留存，用于复算与版本绑定。
- **当次运行绑定**：top 算子表必须由当次 trace 计算；复用历史表会把旧瓶颈当成新瓶颈。

## 2. 实验闭环

```bash
python lesson/28-profiler-trace/run.py --check-only
python lesson/28-profiler-trace/run.py --output results/lesson-28-fixture.json
python lesson/28-profiler-trace/run.py --real --model /models/target --output results/gpu_result.json
```

- **输入**：模型与 workload、CUDA GPU、profiler 配置。
- **输出**：trace JSON、trace SHA-256、top CUDA operators。
- **验收**：trace 含 CUDA activity；产物非空；算子表来自当次运行。

## 3. 判读纪律

- trace SHA-256 与运行 ID 绑定留存：对不上 hash 的归因结论作废。
- 算子表要附占比与耗时口径（self/total），只报 top 名字不接受。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

profiler 方法论展开见 [PyTorch 性能分析体系](/source/AI-Infra/2-AI系统性能工程/19-PyTorch性能分析体系) 与 [GPU 性能分析方法](/source/AI-Infra/2-AI系统性能工程/12-GPU性能分析方法)；本课聚焦 trace 产物与当次绑定的核验。