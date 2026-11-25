# Cold Start：重复加载、首请求与 Warm 请求

通过显式卸载和重新加载，分离冷启动、首轮生成与热路径。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/22-cold-start/run.py --check-only
python lesson/22-cold-start/run.py --output results/lesson-22-cold-start-fixture.json
python lesson/22-cold-start/run.py --real --model /models/target --cycles 2 --warm-requests 2 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- local or resolvable model
- CUDA GPU

## 输出

- cycle records
- cold/warm summaries
- output hashes

## 验收

- at least two cold cycles
- model object is destroyed between cycles
- warm requests reuse the loaded model

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
