# MTP Serving：原生多 Token 预测头的部署核验

对同一 Target 的 MTP-disabled 与 MTP-enabled 服务做成对请求和证据采集。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/04-mtp-serving/run.py --check-only
python lesson/04-mtp-serving/run.py --output results/lesson-04-mtp-serving-fixture.json
python lesson/04-mtp-serving/run.py --real --base-url http://127.0.0.1:8000 --base-url http://127.0.0.1:8001 --model REPLACE_WITH_SERVED_MODEL_ID --require-metric-fragment mtp \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- two separately configured endpoints
- same served Target model

## 输出

- paired latency delta
- per-endpoint metrics hashes
- request records

## 验收

- endpoints are distinct
- model identity matches
- both sides receive every prompt

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
