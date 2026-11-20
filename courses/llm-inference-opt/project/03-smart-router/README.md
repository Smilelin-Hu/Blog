# Project 03：Production AI Gateway and Smart Router

执行租户配额预留、负载选路、Prefix 亲和、请求发送、失败反馈和一次故障转移。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python project/03-smart-router/run.py --check-only
python project/03-smart-router/run.py --output results/project-03-smart-router-fixture.json
python project/03-smart-router/run.py --real --router-config data/project03_router.json --workload data/project03_workload.jsonl --quota data/project03_quotas.json \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- at least two endpoints
- tenant workload
- quota JSON

## 输出

- route trace
- failover trace
- endpoint state
- quota settlements

## 验收

- every accepted request has a decision
- failed primary excludes that endpoint on retry
- prefix affinity is stateful
- reservations settle

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
