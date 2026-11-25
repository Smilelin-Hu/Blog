# DFlare：Drafter 特征融合的层数扩展

扫描融合层数并记录时间、显存与数值尺度，为扩大 Drafter 提供可复验边界。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/06-dflare-scaling/run.py --check-only
python lesson/06-dflare-scaling/run.py --output results/lesson-06-dflare-scaling-fixture.json
python lesson/06-dflare-scaling/run.py --real --model /models/target --layer-counts 1,2,4,8 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- hidden-state capable causal LM
- CUDA GPU

## 输出

- fusion sweep
- latency knee
- norm statistics

## 验收

- same input for every point
- layer count truly changes
- no invented quality score

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
