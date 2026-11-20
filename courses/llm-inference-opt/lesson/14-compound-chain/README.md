# Compound AI：分类、证据生成与回答链路

让每一阶段的真实输出成为下一阶段输入，并保存可核对的数据血缘。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/14-compound-chain/run.py --check-only
python lesson/14-compound-chain/run.py --output results/lesson-14-compound-chain-fixture.json
python lesson/14-compound-chain/run.py --real --base-url http://127.0.0.1:8000 --model REPLACE_WITH_SERVED_MODEL_ID \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- one OpenAI-compatible endpoint
- served model

## 输出

- ordered stage records
- lineage links
- final output hash

## 验收

- three stages execute in order
- downstream input includes upstream output
- failures stop the chain

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
