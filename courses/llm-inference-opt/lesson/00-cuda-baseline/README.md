# CUDA Baseline：矩阵计算、显存与同步计时

建立后续实验可复用的设备、计时与显存证据基线。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/00-cuda-baseline/run.py --check-only
python lesson/00-cuda-baseline/run.py --output results/lesson-00-cuda-baseline-fixture.json
python lesson/00-cuda-baseline/run.py --real --sizes 512,1024,2048 --repeats 5 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- CUDA GPU
- PyTorch

## 输出

- shape sweep
- latency summary
- memory snapshot

## 验收

- all shapes execute on CUDA
- samples are synchronized
- no CPU fallback

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
