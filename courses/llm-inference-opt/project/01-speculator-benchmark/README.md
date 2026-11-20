# Project 01：Next-Generation Speculator Benchmark

用同一工作负载成对比较禁用与启用 Speculator 的独立端点，并校验输出等价和部署归因。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python project/01-speculator-benchmark/run.py --check-only
python project/01-speculator-benchmark/run.py --output results/project-01-speculator-benchmark-fixture.json
python project/01-speculator-benchmark/run.py --real --base-url http://127.0.0.1:8000 --base-url http://127.0.0.1:8001 --speculator-manifest data/speculator_manifest.json --deployment-evidence data/speculator_deployment_evidence.json \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- baseline endpoint
- candidate endpoint
- workload JSONL
- artifact manifest
- deployment evidence

## 输出

- pair table
- correctness gate
- latency delta
- evidence manifest

## 验收

- every request reaches both endpoints
- target/sampling/workload identities match
- candidate output equals baseline
- deployment evidence binds candidate to artifact

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。

运行真实项目之前，请复制并填写 `data/speculator_manifest.example.json` 与 `data/speculator_deployment_evidence.example.json`，不要保留 `REPLACE_WITH_*`。
