# Heterogeneous GPU：逐卡容量与延迟画像

在每张指定 GPU 上独立加载同一模型，保留设备身份、显存和请求级测量。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/24-heterogeneous-gpu/run.py --check-only
python lesson/24-heterogeneous-gpu/run.py --output results/lesson-24-heterogeneous-gpu-fixture.json
python lesson/24-heterogeneous-gpu/run.py --real --model /models/target --devices 0,1 --repeats 3 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- at least two CUDA devices
- one model fitting every selected device

## 输出

- device profiles
- latency/throughput comparison
- memory snapshots

## 验收

- two actual device indices
- same model/workload
- records are not copied across devices

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
