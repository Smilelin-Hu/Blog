# Reasoning Token：输出预算、完成率与尾延迟

推理模型（reasoning）的输出长度不可预知：思考链可能远超答案本身。本课用输出预算（max reasoning tokens）扫描观察三件事：预算对完成率的影响、预算对尾延迟（P99）的影响、以及 usage 缺失时不得估算 token 数。预算不是越大越好——截断思考链会降完成率，放任思考链会抬尾延迟。

## 1. 机制要点

- **预算语义**：预算上限截断的是思考链而非答案；截断点落在思考中段时任务完成率下降。
- **尾延迟来源**：长思考链请求占据 decode 槽位，推高同批其他请求的 P99。
- **usage 纪律**：端点未返回 usage 时不得用启发式估算 token 数冒充实测，否则成本与吞吐结论失真。

## 2. 实验闭环

```bash
python lesson/10-reasoning-tokens/run.py --check-only
python lesson/10-reasoning-tokens/run.py --output results/lesson-10-fixture.json
python lesson/10-reasoning-tokens/run.py --real --model /models/reasoning --budgets 1024,4096,16384 \
  --output results/gpu_result.json
```

- **输入**：reasoning 模型、至少三档预算、同一 prompt 集。
- **输出**：budget sweep、latency and token summaries、raw records。
- **验收**：至少三档预算；同 prompts/模型；usage 缺失时不估算。

## 3. 判读纪律

- 完成率与尾延迟要同表报：只报吞吐会掩盖截断带来的质量损失。
- raw records 必须留存：聚合摘要不可复算时结论作废。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

推理预算与 RL 训练侧的 token 预算对照 [强化学习训练](/source/AI-Infra/1-大模型训练优化/23-强化学习训练)；serving 侧尾延迟治理见 [Continuous Batching 与 Scheduler 优化](/source/AI-Infra/2-AI系统性能工程/24-ContinuousBatching与Scheduler优化)。