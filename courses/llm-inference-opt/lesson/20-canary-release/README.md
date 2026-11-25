# Model Registry：稳定版、Canary 门禁与回滚

按稳定哈希分流到两个真实修订，依据请求证据决定推进或回滚。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/20-canary-release/run.py --check-only
python lesson/20-canary-release/run.py --output results/lesson-20-canary-release-fixture.json
python lesson/20-canary-release/run.py --real --base-url http://127.0.0.1:8000 --base-url http://127.0.0.1:8001 --model REPLACE_WITH_SERVED_MODEL_ID --canary-percent 25 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- stable endpoint
- candidate endpoint
- common model ID

## 输出

- state transitions
- gate calculation
- post-decision probes

## 验收

- canary receives nonzero traffic
- gate is computed from records
- failed gate routes probes back to stable

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
