# Capacity Planning：并发 × 输出长度实测矩阵

在一个真实端点上扫描并发和输出预算，找出满足 P95 门槛的容量点。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python lesson/27-capacity-matrix/run.py --check-only
python lesson/27-capacity-matrix/run.py --output results/lesson-27-capacity-matrix-fixture.json
python lesson/27-capacity-matrix/run.py --real --base-url http://127.0.0.1:8000 --model REPLACE_WITH_SERVED_MODEL_ID --concurrencies 1,2,4 --output-lengths 32,128 \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- one GPU-backed endpoint
- served model

## 输出

- capacity matrix
- feasible frontier
- raw records

## 验收

- both axes vary
- each cell has independent requests
- frontier uses measured P95

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。
