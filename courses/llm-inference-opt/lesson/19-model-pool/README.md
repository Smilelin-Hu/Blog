# Multi-Model Pool：热门模型突发与冷模型穿插

重放带热门/冷门分布的真实多模型请求，并按模型拆分成功率和尾延迟。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/19-model-pool/run.py --check-only
python lesson/19-model-pool/run.py --output results/lesson-19-model-pool-fixture.json
python lesson/19-model-pool/run.py --real --base-url http://127.0.0.1:8000 --models REPLACE_WITH_HOT_MODEL_ID,REPLACE_WITH_COLD_MODEL_ID --requests 8 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- endpoint serving at least two model IDs
- explicit --models

## 输出

- workload mix
- per-model summaries
- first-hit versus warm records

## 验收

- multiple models are requested
- hot and cold traffic both exist
- results are grouped by model

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
