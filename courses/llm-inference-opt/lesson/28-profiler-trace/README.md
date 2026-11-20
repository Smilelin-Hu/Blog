# Distributed Trace：PyTorch CPU/CUDA Span 与 Chrome Trace

为真实模型 Forward 导出可打开的 Chrome Trace，并保存 Top CUDA Op。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/28-profiler-trace/run.py --check-only
python lesson/28-profiler-trace/run.py --output results/lesson-28-profiler-trace-fixture.json
python lesson/28-profiler-trace/run.py --real --model /models/target --trace results/lesson-28-trace.json \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- local or resolvable model
- CUDA GPU
- PyTorch profiler

## 输出

- trace JSON
- trace SHA-256
- top CUDA operators

## 验收

- trace contains CUDA activity
- artifact is non-empty
- operator table comes from current run

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
