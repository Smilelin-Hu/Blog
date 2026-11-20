# Speculative Decoding：Draft 提议与 Target 验证

执行 Draft/Target 闭环并核对贪心输出与 Target 基线一致。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/01-speculative-decode/run.py --check-only
python lesson/01-speculative-decode/run.py --output results/lesson-01-speculative-decode-fixture.json
python lesson/01-speculative-decode/run.py --real --model /models/target --draft-model /models/draft --draft-tokens 4 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- compatible draft and target models
- CUDA GPU

## 输出

- cycle trace
- acceptance rate
- baseline/candidate token IDs

## 验收

- two distinct model inputs
- candidate equals greedy target baseline
- acceptance is recomputable

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
