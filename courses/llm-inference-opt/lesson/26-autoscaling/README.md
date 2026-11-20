# LLM Autoscaling：容量校准、需求窗口与状态机

先实测单副本输出容量，再把需求时间序列输入带滞后和冷却的 Autoscaler。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/26-autoscaling/run.py --check-only
python lesson/26-autoscaling/run.py --output results/lesson-26-autoscaling-fixture.json
python lesson/26-autoscaling/run.py --real --base-url http://127.0.0.1:8000 --model REPLACE_WITH_SERVED_MODEL_ID --demand-tps 40,70,150,220,90,35,20 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- one GPU-backed endpoint
- demand trace

## 输出

- measured replica capacity
- scale events
- SLO risk windows

## 验收

- capacity source is measured
- startup delay is explicit
- scale-down uses hysteresis

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
