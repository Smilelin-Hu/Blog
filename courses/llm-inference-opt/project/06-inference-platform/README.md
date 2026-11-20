# Project 06：Production LLM Inference Platform

把版本注册、Canary、Gateway 选路、配额、故障回退、扩缩容和成本证据连接成一次完整运行。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python project/06-inference-platform/run.py --check-only
python project/06-inference-platform/run.py --output results/project-06-inference-platform-fixture.json
python project/06-inference-platform/run.py --real --platform-config data/project06_platform.json --workload data/project06_workload.jsonl --failure-at 3 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- stable/candidate endpoints
- platform config
- tenant workload

## 输出

- end-to-end trace
- release decision
- failure recovery
- capacity and cost report

## 验收

- invalid lifecycle transitions fail
- candidate is shadow-compared
- failed candidate returns traffic to stable
- all reservations settle
- final state is explicit

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
