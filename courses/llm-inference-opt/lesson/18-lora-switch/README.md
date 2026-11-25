# LoRA Adapter：多模型 ID 交替请求与切换延迟

要求端点实际暴露至少两个模型或 LoRA ID，并按冷热序列发送请求。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/18-lora-switch/run.py --check-only
python lesson/18-lora-switch/run.py --output results/lesson-18-lora-switch-fixture.json
python lesson/18-lora-switch/run.py --real --base-url http://127.0.0.1:8000 --models REPLACE_WITH_BASE_ID,REPLACE_WITH_LORA_ID --cycles 3 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- LoRA-enabled endpoint
- at least two served IDs

## 输出

- transition trace
- per-model summaries
- metrics snapshots

## 验收

- two model IDs are explicitly supplied
- both IDs receive requests
- default command cannot silently test one model

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
