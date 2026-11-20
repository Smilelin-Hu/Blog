# Replica Set：基于 Inflight 与 EWMA 的负载路由

在多个真实端点之间维护运行状态，记录每次选路并反馈成功、失败和延迟。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/16-load-router/run.py --check-only
python lesson/16-load-router/run.py --output results/lesson-16-load-router-fixture.json
python lesson/16-load-router/run.py --real --base-url http://127.0.0.1:8000 --base-url http://127.0.0.1:8001 --model REPLACE_WITH_SERVED_MODEL_ID --concurrency 2 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- at least two endpoints
- common served model

## 输出

- decision trace
- endpoint state
- request results

## 验收

- selection is executed before every request
- inflight is settled
- failed replicas become ineligible

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
