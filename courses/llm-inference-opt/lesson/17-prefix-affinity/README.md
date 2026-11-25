# Prefix Cache：前缀亲和选路与缓存指标

重复发送相同长前缀，验证路由亲和，并保存后端 Prefix Cache 指标前后快照。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/17-prefix-affinity/run.py --check-only
python lesson/17-prefix-affinity/run.py --output results/lesson-17-prefix-affinity-fixture.json
python lesson/17-prefix-affinity/run.py --real --base-url http://127.0.0.1:8000 --base-url http://127.0.0.1:8001 --model REPLACE_WITH_SERVED_MODEL_ID --prefix-repeats 4 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- at least two vLLM endpoints
- common served model

## 输出

- affinity trace
- cache metric delta inputs
- latencies by repetition

## 验收

- same key remains on one healthy replica
- metrics include cache evidence
- requests really reach selected endpoints

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
