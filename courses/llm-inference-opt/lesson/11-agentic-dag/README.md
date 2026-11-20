# Agentic Task：并行分支、汇聚与端到端证据

让多个真实模型调用形成 fan-out/fan-in DAG，并区分节点延迟与端到端延迟。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/11-agentic-dag/run.py --check-only
python lesson/11-agentic-dag/run.py --output results/lesson-11-agentic-dag-fixture.json
python lesson/11-agentic-dag/run.py --real --base-url http://127.0.0.1:8000 --model REPLACE_WITH_SERVED_MODEL_ID --fanout 3 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- one OpenAI-compatible endpoint
- served model

## 输出

- DAG trace
- node latency
- final response hash

## 验收

- fan-out executes concurrently
- fan-in consumes branch outputs
- trace IDs are complete

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
