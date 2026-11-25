# Inference Economics：Token 吞吐、GPU 功耗与成本

在真实生成期间采样 GPU 功耗，并用用户提供的小时成本计算单位 Token 成本。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/29-inference-economics/run.py --check-only
python lesson/29-inference-economics/run.py --output results/lesson-29-inference-economics-fixture.json
python lesson/29-inference-economics/run.py --real --model /models/target --hourly-cost-usd REPLACE_WITH_CURRENT_HOURLY_COST --repeats 4 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- CUDA GPU
- NVML
- model
- hourly GPU cost

## 输出

- token throughput
- energy per output token
- cost per million output tokens

## 验收

- price is supplied, not assumed
- power is sampled during work
- token counts come from generation

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
