# Diffusion Draft Tree：树预算、叶路径与批量验证

把候选树保存为父子关系，展开叶路径并用同一 Target 批量验证。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/07-diffusion-tree/run.py --check-only
python lesson/07-diffusion-tree/run.py --output results/lesson-07-diffusion-tree-fixture.json
python lesson/07-diffusion-tree/run.py --real --model /models/target --tree-depth 3 --branching 2 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- causal LM
- CUDA GPU

## 输出

- tree topology
- leaf acceptance
- verification latency

## 验收

- tree has no cycles
- every leaf path is reconstructable
- all leaves are verified

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
