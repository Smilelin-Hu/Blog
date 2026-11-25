# Block Draft：候选块宽度、深度与验证成本

构造明确的候选块几何并测量 Target 批量验证，而不是把普通解码延迟改名为 Block Diffusion。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/05-block-draft/run.py --check-only
python lesson/05-block-draft/run.py --output results/lesson-05-block-draft-fixture.json
python lesson/05-block-draft/run.py --real --model /models/target --widths 2,4,8 --depths 2,4 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- causal LM
- CUDA GPU

## 输出

- block geometry
- verification latency
- peak memory

## 验收

- all candidates share the same prefix
- geometry varies
- each sweep point is measured

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
