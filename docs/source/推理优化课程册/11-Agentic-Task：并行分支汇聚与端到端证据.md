# Agentic Task：并行分支、汇聚与端到端证据

Agentic 请求不是单链生成而是 DAG：fan-out 并行执行多个工具/子任务分支，fan-in 汇聚分支输出再产出最终回答。本课核验三件事：fan-out 真并发（而非串行伪装）、fan-in 真消费分支输出（而非丢弃）、trace ID 完整可串联。端到端延迟的归因依赖完整 DAG trace。

## 1. 机制要点

- **fan-out 并发**：分支间无依赖时应同批发起；串行执行会把并行收益吃掉且 trace 上可见。
- **fan-in 消费**：汇聚节点输入必须包含各分支输出；丢分支的「汇聚」是假闭环。
- **trace 完整性**：每个节点带 trace/span ID，端到端 hash 可复算；缺 ID 的 trace 无法归因延迟。

## 2. 实验闭环

```bash
python lesson/11-agentic-dag/run.py --check-only
python lesson/11-agentic-dag/run.py --output results/lesson-11-fixture.json
python lesson/11-agentic-dag/run.py --real --endpoint http://agent:8000 --output results/gpu_result.json
```

- **输入**：agent 端点、含并行分支的任务集。
- **输出**：DAG trace、node latency、final response hash。
- **验收**：fan-out 并发执行；fan-in 消费分支输出；trace ID 完整。

## 3. 判读纪律

- 并发要有时间证据：分支 span 重叠区间可见，仅凭「配置了并行」不算。
- 最终回答 hash 与分支输出 lineage 对齐：hash 对不上说明汇聚丢了信息。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

Agent 运行环境与资源调度的平台侧展开见 [Agent 任务运行环境与资源调度](/source/AI-Infra/4-AI平台工程/40-Agent任务运行环境与资源调度)；本课聚焦 DAG 闭环的实验证据口径。