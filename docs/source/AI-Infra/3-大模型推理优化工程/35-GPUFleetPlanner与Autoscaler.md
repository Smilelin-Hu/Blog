# GPU Fleet Planner 与 Autoscaler

## 1. 工程目标

![项目全景](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l35_01.png)

*项目全景：从输入、关键组件到验收证据形成一条可回放路径。*

实现异构 GPU 放置、碎片评估、容量预测与 SLA-aware 扩缩容。交付物需要连通运行、测量、演示和故障恢复。每项结果都能追溯到输入、配置、环境及版本，并由实际执行产生。

## 2. 知识范围

项目整合以下前序能力：《LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo》《Heterogeneous GPU Placement：异构设备与拓扑亲和性》《GPU Bin Packing：并行组、碎片与放置算法》《LLM Autoscaling：Queue、Token 与 SLA-aware Planner》《Capacity Planning：流量预测、Headroom 与 GPU Fleet》。实现时允许复用已有模块，但必须重新验证跨模块接口、身份、截止时间、错误传播和观测字段。

## 3. 系统边界与架构

### 组件 1：GPU 能力画像

GPU 能力画像负责处理已绑定任务和版本的输入，将可验证状态交给模型资源画像。组件对外提供配置摘要、开始结束事件、指标及失败原因，身份信息始终经过接口传播。

### 组件 2：模型资源画像

模型资源画像与拓扑约束求解之间使用结构化合同。任务 ID、模型或策略版本随输入传入，输出附带配置摘要、时间、指标和错误，使隔离、回放和追踪拥有同一身份链。

### 组件 3：拓扑约束求解

拓扑约束求解接收带版本和任务身份的输入，并向装箱与碎片评估输出结构化状态。接口记录配置摘要、起止时间、核心指标与失败原因。客户身份和模型修订通过显式字段传递，便于故障回放和租户隔离。

### 组件 4：装箱与碎片评估

在这套架构中，装箱与碎片评估维护清晰的能力边界。输入携带任务及版本，输出由容量预测器直接消费；运行记录包含配置、时间、指标和错误。租户与模型身份不放入不可见的全局状态。

### 组件 5：容量预测器

容量预测器负责处理已绑定任务和版本的输入，将可验证状态交给 SLA-aware Autoscaler。组件对外提供配置摘要、开始结束事件、指标及失败原因，身份信息始终经过接口传播。

### 组件 6：SLA-aware Autoscaler

SLA-aware Autoscaler 与 GPU 能力画像之间使用结构化合同。任务 ID、模型或策略版本随输入传入，输出附带配置摘要、时间、指标和错误，使隔离、回放和追踪拥有同一身份链。

## 4. 目录映射

可执行文件为 `project/05-fleet-planner/run.py`。所需的 HTTP、CUDA、统计、报告或状态机原语已经合并到这一入口。下方代码展示入口中内嵌的可读核心实现；下载包不再单独提供内部源码库目录。默认运行 Fixture，加 `--real` 才进入实测路径。

**内嵌核心实现 → project/05-fleet-planner/run.py**

```python
"""Project 05 — measured-capacity GPU Fleet Planner and Autoscaler."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from phase3lab.shared.http_client import completion, discover_models, metrics_evidence
from phase3lab.shared.planner import Autoscaler, CapacityPoint, DeploymentNeed, GpuSku, plan_deployment
from phase3lab.shared.runner import LabSpec, PreconditionError, run_cli

SPEC = LabSpec(
    lab_id="project-05-fleet-planner",
    title="Project 05：GPU Fleet Planner and SLA-Aware Autoscaler",
    goal="以带原始证据哈希的实测容量点做 GPU 选型与装箱，再对需求时间序列运行带启动延迟、滞后和冷却的扩缩容状态机。",
    real_evidence=("measured capacity records", "current endpoint probes", "inventory constraints", "autoscaler event log"),
    required_inputs=("inventory JSON", "capacity evidence JSON", "demand trace JSON"),
    outputs=("peak placement", "window decisions", "cost timeline", "constraint findings"),
    acceptance=("fixture capacity is rejected", "placement respects memory/inventory/SLO", "startup delay is represented", "current endpoints are probed"),
)

def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--inventory", default="data/project05_inventory.json")
    parser.add_argument("--capacity", default="data/project05_capacity.example.json")
    parser.add_argument("--demand", default="data/project05_demand.json")
    parser.add_argument("--startup-windows", type=int, default=2)

def read_json(path: str, label: str) -> tuple[dict, str]:
    target = Path(path)
    if not target.is_file():
        raise PreconditionError(f"{label} does not exist: {target}")
    raw = target.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()

def parse_inputs(inventory_value: dict, capacity_value: dict, demand_value: dict):
    skus = [GpuSku(name=str(row["name"]), memory_gib=float(row["memory_gib"]), hourly_cost=float(row["hourly_cost"]), inventory=int(row["inventory"])) for row in inventory_value.get("skus", [])]
    if not skus or any(sku.memory_gib <= 0 or sku.hourly_cost <= 0 or sku.inventory < 1 for sku in skus):
        raise ValueError("inventory contains invalid GPU SKUs")
    measurements = []
    endpoints = {}
    for row in capacity_value.get("measurements", []):
        required = {"sku", "model", "concurrency", "sustainable_tokens_per_second", "p95_ms", "peak_memory_gib", "source", "evidence_sha256", "endpoint"}
        missing = sorted(required - row.keys())
        if missing:
            raise ValueError(f"capacity point is missing: {', '.join(missing)}")
        if row["source"] != "measured":
            raise ValueError("capacity points must have source=measured; fixtures cannot drive a production plan")
        evidence_sha = str(row["evidence_sha256"])
        if not re.fullmatch(r"[0-9a-f]{64}", evidence_sha) or set(evidence_sha) == {"0"}:
            raise ValueError("capacity evidence_sha256 must be a non-placeholder SHA-256")
        point = CapacityPoint(
            sku=str(row["sku"]), model=str(row["model"]), concurrency=int(row["concurrency"]),
            sustainable_tokens_per_second=float(row["sustainable_tokens_per_second"]), p95_ms=float(row["p95_ms"]),
            peak_memory_gib=float(row["peak_memory_gib"]), source="measured",
        )
        if point.concurrency < 1 or point.sustainable_tokens_per_second <= 0 or point.p95_ms <= 0 or point.peak_memory_gib <= 0:
            raise ValueError("measured capacity values must be positive")
        measurements.append(point)
        endpoints[str(row["sku"])] = str(row["endpoint"])
    if not measurements:
        raise ValueError("capacity evidence contains no measurements")
    known_skus = {sku.name for sku in skus}
    unknown_skus = sorted({point.sku for point in measurements} - known_skus)
    if unknown_skus:
        raise ValueError(f"capacity evidence references unknown SKUs: {', '.join(unknown_skus)}")
    windows = [float(value) for value in demand_value.get("windows_tokens_per_second", [])]
    if len(windows) < 3 or any(value < 0 for value in windows):
        raise ValueError("demand trace needs at least three non-negative windows")
    need = DeploymentNeed(
        model=str(demand_value["model"]), demand_tokens_per_second=max(windows), memory_gib=float(demand_value["memory_gib"]),
        target_utilization=float(demand_value.get("target_utilization", 0.7)), max_p95_ms=float(demand_value["max_p95_ms"]),
        minimum_replicas=int(demand_value.get("minimum_replicas", 1)),
    )
    return skus, measurements, endpoints, windows, need

def fixture(args: argparse.Namespace) -> dict:
    skus = [GpuSku("g48", 48, 2.0, 6), GpuSku("g80", 80, 3.8, 4)]
    points = [CapacityPoint("g48", "chat", 4, 220, 900, 36, "measured"), CapacityPoint("g80", "chat", 8, 430, 750, 52, "measured")]
    need = DeploymentNeed("chat", 600, 32, 0.7, 1200, 1)
    placement = plan_deployment(need, skus, points)
    scaler = Autoscaler(minimum=1, maximum=next(sku.inventory for sku in skus if sku.name == placement.sku))
    selected = next(point for point in points if point.sku == placement.sku)
    events = [scaler.tick(index, demand_tps=demand, replica_capacity_tps=selected.sustainable_tokens_per_second, target_utilization=need.target_utilization, startup_windows=args.startup_windows) for index, demand in enumerate([80, 300, 600, 250, 80, 40])]
    return {"placement": placement.json(), "events": events, "capacity_source": "fixture_for_algorithm_test_only"}

def real(args: argparse.Namespace) -> dict:
    inventory_value, inventory_sha = read_json(args.inventory, "inventory")
    capacity_value, capacity_sha = read_json(args.capacity, "capacity evidence")
    demand_value, demand_sha = read_json(args.demand, "demand trace")
    skus, measurements, endpoints, windows, need = parse_inputs(inventory_value, capacity_value, demand_value)
    placement = plan_deployment(need, skus, measurements)
    selected_point = max((point for point in measurements if point.sku == placement.sku and point.model == need.model and point.p95_ms <= need.max_p95_ms), key=lambda point: point.sustainable_tokens_per_second)
    endpoint_probes = []
    for sku, endpoint in sorted(endpoints.items()):
        models = discover_models(endpoint)
        if need.model not in models:
            raise PreconditionError(f"capacity endpoint for {sku} no longer serves {need.model}")
        probe = completion(endpoint, need.model, args.prompt, min(args.max_new_tokens, 16), request_id=f"fleet-probe-{sku}")
        if not probe.ok:
            raise RuntimeError(f"current endpoint probe failed for {sku}")
        endpoint_probes.append({"sku": sku, "endpoint": endpoint, "models": models, "probe": probe.json(), "metrics": metrics_evidence(endpoint)})
    selected_sku = next(sku for sku in skus if sku.name == placement.sku)
    scaler = Autoscaler(minimum=need.minimum_replicas, maximum=selected_sku.inventory)
    events = [
        scaler.tick(index, demand_tps=demand, replica_capacity_tps=selected_point.sustainable_tokens_per_second, target_utilization=need.target_utilization, startup_windows=args.startup_windows)
        for index, demand in enumerate(windows)
    ]
    timeline = []
    for event in events:
        provisioned = event["ready"] + event["pending"]
        timeline.append({**event, "hourly_cost_usd": round(provisioned * selected_sku.hourly_cost, 4), "available_tps": round(event["ready"] * selected_point.sustainable_tokens_per_second * need.target_utilization, 4), "slo_capacity_pass": event["demand_tps"] <= event["ready"] * selected_point.sustainable_tokens_per_second * need.target_utilization})
    return {
        "input_hashes": {"inventory": inventory_sha, "capacity": capacity_sha, "demand": demand_sha},
        "placement": placement.json(),
        "selected_capacity_point": selected_point.__dict__,
        "endpoint_probes": endpoint_probes,
        "timeline": timeline,
        "acceptance": {
            "all_capacity_points_measured": all(point.source == "measured" for point in measurements),
            "inventory_respected": placement.replicas <= selected_sku.inventory,
            "memory_respected": need.memory_gib <= selected_sku.memory_gib,
            "scale_actions": sum(event["action"] != "hold" for event in events),
            "slo_risk_windows": [item["window"] for item in timeline if not item["slo_capacity_pass"]],
        },
    }

def main() -> None:
    run_cli(SPEC, add_arguments, real, fixture)

if __name__ == "__main__":
    main()
```

## 5. 配置与输入合同

每次运行读取显式配置并生成不可歧义的运行身份。输入必须说明随机种子、工作负载、模型或代理模型、并发、截止时间、硬件模式和输出目录。配置校验拒绝负容量、非法概率、不存在的文件和互相冲突的开关。敏感凭证只从运行环境读取，不写入配置、报告或日志。

## 6. 机制模拟

模拟路径在 CPU 上连接 GPU 能力画像、模型资源画像、拓扑约束求解、装箱与碎片评估、容量预测器、SLA-aware Autoscaler，用离散事件或确定性状态机验证控制逻辑。模拟重点是因果方向、状态转换、容量边界和反例，不声称复刻真实 GPU 速度。输出记录 `fixture` 来源、工作负载、事件时间线、指标、故障和限制。

```bash
python project/05-fleet-planner/run.py
```

模拟验收至少运行基线、候选和过载三组场景。关闭候选后应回到基线；提高负载到容量以上时必须出现排队、拒绝或服务等级失守；非法状态转换和无效输入必须被拒绝。固定随机种子后，结构化报告应可重复生成。

## 7. 真实本地路径

真实工作流直接执行“以带原始证据哈希的实测容量点做 GPU 选型与装箱，再对需求时间序列运行带启动延迟、滞后和冷却的扩缩容状态机。”。运行输入为 `inventory JSON`、`capacity evidence JSON`、`demand trace JSON`；报告必须保留 `measured capacity records`、`current endpoint probes`、`inventory constraints`、`autoscaler event log`。只有 `source=measured` 可以支撑性能或发布结论，`source=fixture` 只验证控制逻辑。

```bash
python project/05-fleet-planner/run.py --check-only

python project/05-fleet-planner/run.py --real --inventory data/project05_inventory.json --capacity data/project05_capacity.json --demand data/project05_demand.json
```

缺少 `inventory JSON`、`capacity evidence JSON`、`demand trace JSON` 中任一真实前提时，脚本写入 `status=precondition_failed` 并以退出码 2 结束。真实路径没有 CPU fallback；性能报告只接受本次运行的 `source=measured` 记录。

## 8. 工作负载与指标

### 指标 1：correctness

评审 correctness 时使用《GPU Fleet Planner 与 Autoscaler》当前运行的原始数据。定义、单位、采集点、时间范围和分母全部随报告提供；任何以错误率、服务等级或恢复退化换来的改善都被门禁拦截。

### 指标 2：latency

《GPU Fleet Planner 与 Autoscaler》把 latency 作为一项可重算指标，而非单独结论。报告保存原始事件、口径、单位、分母与时间窗口，并同步检查输出正确性、服务等级和故障恢复。

### 指标 3：throughput

throughput 随《GPU Fleet Planner 与 Autoscaler》的原始事件保存，并注明定义、单位、采集点、时间窗口和分母。验收器可以重新计算聚合值；候选若以正确性、服务等级或恢复能力为代价，即使 throughput 改善也不通过。

### 指标 4：reliability

项目为 reliability 记录计算口径、单位、分母、采集位置和窗口。报告中的聚合值能够从《GPU Fleet Planner 与 Autoscaler》事件重算，并与正确性、SLO 及故障恢复一同验收。

### 指标 5：cost_efficiency

评审 cost_efficiency 时使用《GPU Fleet Planner 与 Autoscaler》当前运行的原始数据。定义、单位、采集点、时间范围和分母全部随报告提供；任何以错误率、服务等级或恢复退化换来的改善都被门禁拦截。

## 9. 故障注入与诊断

### 故障 1：显存足够但拓扑不可行

在《GPU Fleet Planner 与 Autoscaler》中注入“显存足够但拓扑不可行”后，观察故障发现、隔离、降级、回退与恢复导流。证据链从任务身份和制品版本开始，经过配置、负载与组件事件，最后确认资源和在途工作回到稳定状态。

### 故障 2：慢设备进入同一并行组

本场景复现“慢设备进入同一并行组”。验收器检查发现时间、隔离范围、降级结果、回滚目标与恢复节奏，并用任务、制品、配置和负载定位根因。只有缓存、队列、资源及在途任务稳定后才算恢复完成。

### 故障 3：待启动容量被重复计算

主动制造“待启动容量被重复计算”，记录检测、隔离、降级、回滚和渐进恢复。排查时核对《GPU Fleet Planner 与 Autoscaler》任务身份、制品摘要、配置及负载，再沿组件事件定位故障。重新导流前确认在途任务、缓存、队列与资源稳定。

### 故障 4：缩容终止仍有在途请求的工作器

“缩容终止仍有在途请求的工作器”由故障注入器稳定复现。系统需要给出告警、影响隔离、可解释降级和回滚事件；诊断依据任务 ID、制品摘要、配置、工作负载与组件时间线。进程恢复后仍要检查队列、缓存和在途任务。

## 10. 验收阈值

- 所有放置满足显存和能力硬约束。
- 碎片、迁移与故障余量进入评分。
- 扩容考虑冷启动和待就绪容量。
- 真实硬件不足时仍可完整运行规划模拟。
- 指标可复现。
- 故障注入产生预期告警或降级。

## 11. 演示方法

先运行 `--check-only`，再执行 Fixture、真实路径、失败注入与报告验收。演示时明确区分 `source=fixture`、`source=measured` 和 `status=precondition_failed`；前提失败不能写成性能通过。

```bash
python project/05-fleet-planner/run.py
python project/05-fleet-planner/run.py --check-only
```

## 12. 交付物

- 源代码。
- 配置。
- 实验报告。
- 架构说明。
- 验收结果。

## 13. 项目小结

完成《GPU Fleet Planner 与 Autoscaler》后，应能从接口和状态追到指标与恢复动作。最终演示说明当前架构为何成立、收益如何复验、哪些结果无效，以及故障后怎样回到稳定路径。

## 写在最后

最后一个项目把前面所有组件接成一次完整的发布与恢复运行。下一篇：[生产级 LLM Inference Platform](/source/AI-Infra/3-大模型推理优化工程/36-生产级LLMInferencePlatform)。