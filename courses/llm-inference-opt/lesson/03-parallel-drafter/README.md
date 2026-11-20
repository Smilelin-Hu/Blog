# P-EAGLE：并行候选分支与 Target 批量验证

从同一前缀构造多个候选分支，核对串行与批量 Target 得分并测量验证成本。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/03-parallel-drafter/run.py --check-only
python lesson/03-parallel-drafter/run.py --output results/lesson-03-parallel-drafter-fixture.json
python lesson/03-parallel-drafter/run.py --real --model /models/target --branches 4 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- causal LM
- CUDA GPU

## 输出

- branch trace
- numerical agreement
- latency comparison

## 验收

- more than one branch
- same candidate set
- batched and serial scores agree

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
