# OpenAI-Compatible API：直连与 Gateway 成对开销

以相同模型、Prompt 和采样参数交替调用直连与 Gateway，估算 API 层附加延迟。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/15-gateway-overhead/run.py --check-only
python lesson/15-gateway-overhead/run.py --output results/lesson-15-gateway-overhead-fixture.json
python lesson/15-gateway-overhead/run.py --real --base-url http://127.0.0.1:8000 --base-url http://127.0.0.1:8080 --model REPLACE_WITH_SERVED_MODEL_ID \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- direct backend URL
- gateway URL
- same served model

## 输出

- paired deltas
- order-balanced records
- failure comparison

## 验收

- request order alternates
- payloads match
- both endpoints serve same model ID

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
