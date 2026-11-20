# Model Loading：权重清单、CPU 装载、H2D 与首轮生成

将冷启动拆成可观测阶段，并保存本地权重文件清单。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/21-model-loading/run.py --check-only
python lesson/21-model-loading/run.py --output results/lesson-21-model-loading-fixture.json
python lesson/21-model-loading/run.py --real --model /models/target --dtype auto \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- local or resolvable model
- CUDA GPU

## 输出

- load phase breakdown
- first generation
- weight manifest hash

## 验收

- phases are not merged
- model runs on CUDA
- manifest is reproducible for local paths

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
