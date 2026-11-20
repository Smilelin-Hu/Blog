# EAGLE-3：多层 Target 特征抽取与融合路径

验证选层、张量形状、融合投影和额外显存，而不把随机投影当作已训练 Drafter。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/02-eagle-feature-path/run.py --check-only
python lesson/02-eagle-feature-path/run.py --output results/lesson-02-eagle-feature-path-fixture.json
python lesson/02-eagle-feature-path/run.py --real --model /models/target --layers=-1,-4,-8 --projection-width 512 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- hidden-state capable causal LM
- CUDA GPU

## 输出

- layer map
- projection timing
- memory evidence

## 验收

- layer indices resolve
- batch/sequence dimensions agree
- report labels projection as untrained

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
