# Speculator Artifact：版本绑定与双端点 Smoke Benchmark

用制品清单把 candidate 服务绑定到 Target/Drafter 版本，再执行真实双端点配对请求。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/09-speculator-artifact/run.py --check-only
python lesson/09-speculator-artifact/run.py --output results/lesson-09-speculator-artifact-fixture.json
python lesson/09-speculator-artifact/run.py --real --base-url http://127.0.0.1:8000 --base-url http://127.0.0.1:8001 --speculator-manifest data/speculator_manifest.json \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- baseline endpoint
- candidate endpoint
- Speculator manifest JSON

## 输出

- artifact identity
- metrics evidence
- paired smoke result

## 验收

- manifest target matches served model
- candidate is a distinct endpoint
- all pairs complete

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
