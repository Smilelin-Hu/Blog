# GPU Bin Packing：分配、打洞与大块探针

用受限张量分配模式制造空洞，观察 allocated/reserved 差异和大块探针结果。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/25-fragmentation/run.py --check-only
python lesson/25-fragmentation/run.py --output results/lesson-25-fragmentation-fixture.json
python lesson/25-fragmentation/run.py --real --block-mib 8,16,32,64 --rounds 2 --probe-mib 96 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- CUDA GPU
- PyTorch

## 输出

- allocator snapshots
- fragmentation proxy
- cleanup proof

## 验收

- allocation budget is bounded
- every free is recorded
- final allocated memory returns near baseline

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
