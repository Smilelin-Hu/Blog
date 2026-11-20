# Serving Control Plane：Desired/Actual Diff 与 Probe

读取版本化 Desired State，发现真实端点并生成可执行的差异和健康证据。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/23-control-plane/run.py --check-only
python lesson/23-control-plane/run.py --output results/lesson-23-control-plane-fixture.json
python lesson/23-control-plane/run.py --real --desired data/desired_state.json \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- desired-state JSON
- listed endpoints

## 输出

- reconciliation actions
- actual state
- probe records

## 验收

- desired revision is explicit
- every endpoint is discovered
- diff is empty only when evidence matches

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。

真实运行前，请复制 `data/desired_state.example.json` 为 `data/desired_state.json`，并填写当前部署状态。
