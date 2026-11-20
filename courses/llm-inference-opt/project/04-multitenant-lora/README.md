# Project 04：Multi-Tenant, Multi-Model and Multi-LoRA Serving

以加权公平顺序处理多租户请求，执行 Token 配额、模型/Adapter 选路、驻留淘汰和真实端点调用。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python project/04-multitenant-lora/run.py --check-only
python project/04-multitenant-lora/run.py --output results/project-04-multitenant-lora-fixture.json
python project/04-multitenant-lora/run.py --real --serving-config data/project04_serving.json --tenant-policy data/project04_tenants.json --workload data/project04_workload.jsonl \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- multi-ID vLLM endpoints
- tenant policy JSON
- multi-model/multi-adapter workload

## 输出

- fair schedule
- tenant accounting
- adapter hit/eviction trace
- per-ID metrics

## 验收

- at least two tenants/models/adapters
- every accepted reservation settles
- adapter is explicit on every LoRA request
- fair scheduler is exercised

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
