# DSpark：按 Draft 置信度决定是否提议

在一组真实前缀上计算 Draft 置信度和 Target 一致性，再扫描调度阈值。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/08-confidence-scheduler/run.py --check-only
python lesson/08-confidence-scheduler/run.py --output results/lesson-08-confidence-scheduler-fixture.json
python lesson/08-confidence-scheduler/run.py --real --model /models/target --draft-model /models/draft --thresholds 0.2,0.4,0.6,0.8 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- compatible draft and target models
- CUDA GPU

## 输出

- prefix-level labels
- threshold sweep
- coverage/agreement curve

## 验收

- confidence comes from Draft logits
- agreement comes from Target
- threshold changes decisions

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
