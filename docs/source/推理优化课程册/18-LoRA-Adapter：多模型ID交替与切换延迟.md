# LoRA Adapter：多模型 ID 交替请求与切换延迟

多 LoRA serving 用同一 base 权重挂多个 adapter，按请求的 model ID 切换。切换不是零成本：adapter 权重装载/换入、批内混排策略都影响延迟。本课用两个显式 model ID 交替请求，量切换延迟与逐模型表现，并核验「默认命令不能静默只测一个模型」——单模型跑出来的「多 LoRA 结论」无效。

## 1. 机制要点

- **切换成本**：adapter 换入涉及权重搬运与可能的批重组；交替频率越高切换开销占比越大。
- **逐模型口径**：不同 adapter 的输出长度/难度不同，聚合延迟会掩盖单模型退化，必须逐模型分组。
- **显式双 ID**：实验必须显式供给两个 model ID 且都收到请求，防止配置遗漏导致静默单模型。

## 2. 实验闭环

```bash
python lesson/18-lora-switch/run.py --check-only
python lesson/18-lora-switch/run.py --output results/lesson-18-fixture.json
python lesson/18-lora-switch/run.py --real --endpoint http://lora:8000 --model-ids adapter-a,adapter-b \
  --output results/gpu_result.json
```

- **输入**：多 LoRA 端点、两个显式 model ID、交替请求序列。
- **输出**：transition trace、per-model summaries、metrics snapshots。
- **验收**：两个 model ID 显式供给；两 ID 都收到请求；默认命令不能静默单模型。

## 3. 判读纪律

- 切换延迟从 transition trace 取（切换点前后延迟差），不用聚合均值冒充。
- 逐模型 summary 与 metrics snapshot 对齐：快照时点不明则延迟归因无效。
- 只有 `source=measured` 的报告可用于性能或发布结论；前置不足时 `precondition_failed` 退出码 2。

## 4. 与主题笔记的关系

多 LoRA 与模型池的机制展开见[Multi-LoRA Serving：Adapter 缓存与热切换](/source/AI-Infra/3-大模型推理优化工程/19-Multi-LoRAServing-Adapter缓存与热切换)；本课聚焦切换延迟与双 ID 核验。