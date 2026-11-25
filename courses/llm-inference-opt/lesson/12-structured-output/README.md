# Grammar：受约束 JSON 输出与逐请求校验

向真实端点提交 JSON Schema 约束，并独立解析和校验每条响应。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/12-structured-output/run.py --check-only
python lesson/12-structured-output/run.py --output results/lesson-12-structured-output-fixture.json
python lesson/12-structured-output/run.py --real --base-url http://127.0.0.1:8000 --model REPLACE_WITH_SERVED_MODEL_ID \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- JSON-schema capable endpoint
- served model

## 输出

- request records
- schema pass rate
- parse failures

## 验收

- schema is sent to backend
- every response is parsed
- invalid output fails acceptance

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
