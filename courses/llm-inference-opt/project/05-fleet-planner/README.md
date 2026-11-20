# Project 05：GPU Fleet Planner and SLA-Aware Autoscaler

以带原始证据哈希的实测容量点做 GPU 选型与装箱，再对需求时间序列运行带启动延迟、滞后和冷却的扩缩容状态机。

这个目录只有一个入口 `run.py`。所需的底层运行库已经合并到入口中，不需要寻找或复制其他源码目录。

## 运行

从压缩包根目录执行：

```bash
python project/05-fleet-planner/run.py --check-only
python project/05-fleet-planner/run.py --output results/project-05-fleet-planner-fixture.json
python project/05-fleet-planner/run.py --real --inventory data/project05_inventory.json --capacity data/project05_capacity.json --demand data/project05_demand.json \
  --output results/gpu_result.json
```

不带 `--real` 时运行确定性 Fixture，只验证控制逻辑。真实前置条件不足时输出 `status=precondition_failed` 并以退出码 2 结束，不会回退到 CPU 冒充实测。

## 输入

- inventory JSON
- capacity evidence JSON
- demand trace JSON

## 输出

- peak placement
- window decisions
- cost timeline
- constraint findings

## 验收

- fixture capacity is rejected
- placement respects memory/inventory/SLO
- startup delay is represented
- current endpoints are probed

只有 `source=measured` 的报告可以用于性能或发布结论。API Key 只从 `OPENAI_API_KEY` 读取。

`data/project05_capacity.example.json` 只是格式模板；真实运行前应保存为 `data/project05_capacity.json` 并填入实测容量。
