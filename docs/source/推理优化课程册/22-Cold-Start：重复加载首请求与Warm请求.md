# Cold Start：重复加载、首请求与 Warm 请求

冷启动代价只有「真的冷」才量得到：循环之间必须销毁模型对象，否则第二轮起就是 warm 请求，冷启动数字被稀释。本课用至少两个冷循环（循环间销毁模型）对比 cold/warm 摘要与输出 hash，核验 warm 请求真实复用已加载模型——冷热不分的「冷启动优化收益」是自欺。

## 1. 机制要点

- **冷循环定义**：模型对象销毁 → 重新加载 → 首请求；不销毁对象的重复请求不是冷启动。
- **warm 复用证据**：warm 请求延迟应显著低于 cold 首请求，且输出 hash 一致（复用不改语义）。
- **多循环必要性**：单冷循环受首次缓存/页缓存影响大，至少两循环才能区分稳态冷启动与偶发因素。

## 2. 实验闭环

```bash
python lesson/22-cold-start/run.py --check-only
python lesson/22-cold-start/run.py --output results/lesson-22-fixture.json
python lesson/22-cold-start/run.py --real --model /models/target --cycles 2 --output results/gpu_result.json
```

- **输入**：模型路径、冷循环次数（≥2）、CUDA GPU。
- **输出**：cycle records、cold/warm summaries、output hashes。
- **验收**：至少两个冷循环；循环间模型对象销毁；warm 请求复用已加载模型。

## 3. 判读纪律

- 销毁证据要留痕（对象生命周期日志/显存回落快照），口头「销毁了」不算。
- cold/warm 摘要分开报，输出 hash 对齐证明语义不变。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

冷启动优化的机制展开见 [Cold Start Optimization：缓存、Warm Pool 与 GPU Memory Service](/source/AI-Infra/3-大模型推理优化工程/23-ColdStartOptimization-缓存-WarmPool与GPUMemoryService)；加载阶段计量见本册 [21-Model-Loading](21-Model-Loading：权重清单CPU装载H2D与首轮生成)。