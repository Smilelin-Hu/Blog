# Multi-Tenant、Multi-Model 与 Multi-LoRA Serving

## 1. 工程目标

![项目全景](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l34_01.png)

*项目全景：从输入、关键组件到验收证据形成一条可回放路径。*

实现模型和 Adapter 生命周期、缓存、热切换、预热与回滚。各组件组成一条可运行、可测量、可演示且可恢复的工程路径。结果绑定输入、配置、环境与版本，报告中不预填宣传数字。

## 2. 知识范围

项目整合以下前序能力：《Multi-LoRA Serving：Adapter 缓存与热切换》《Multi-Model Serving：热冷模型与稀疏流量》《Model Registry 与 Inference Deployment 生命周期》《Weight Distribution：大模型权重分发与启动关键路径》《Cold Start Optimization：缓存、Warm Pool 与 GPU Memory Service》。实现时允许复用已有模块，但必须重新验证跨模块接口、身份、截止时间、错误传播和观测字段。

## 3. 系统边界与架构

### 组件 1：Model Registry

在这套架构中，Model Registry 维护清晰的能力边界。输入携带任务及版本，输出由 Adapter Registry 直接消费；运行记录包含配置、时间、指标和错误。租户与模型身份不放入不可见的全局状态。

### 组件 2：Adapter Registry

Adapter Registry 负责处理已绑定任务和版本的输入，将可验证状态交给模型与 Adapter 缓存。组件对外提供配置摘要、开始结束事件、指标及失败原因，身份信息始终经过接口传播。

### 组件 3：模型与 Adapter 缓存

模型与 Adapter 缓存与热冷分层之间使用结构化合同。任务 ID、模型或策略版本随输入传入，输出附带配置摘要、时间、指标和错误，使隔离、回放和追踪拥有同一身份链。

### 组件 4：热冷分层

热冷分层接收带版本和任务身份的输入，并向预热控制器输出结构化状态。接口记录配置摘要、起止时间、核心指标与失败原因。客户身份和模型修订通过显式字段传递，便于故障回放和租户隔离。

### 组件 5：预热控制器

在这套架构中，预热控制器维护清晰的能力边界。输入携带任务及版本，输出由 Canary 与回滚直接消费；运行记录包含配置、时间、指标和错误。租户与模型身份不放入不可见的全局状态。

### 组件 6：Canary 与回滚

Canary 与回滚负责处理已绑定任务和版本的输入，将可验证状态交给 Model Registry。组件对外提供配置摘要、开始结束事件、指标及失败原因，身份信息始终经过接口传播。

## 4. 目录映射

可执行文件为 `project/04-multitenant-lora/run.py`。所需的 HTTP、CUDA、统计、报告或状态机原语已经合并到这一入口。下方代码展示入口中内嵌的可读核心实现；下载包不再单独提供内部源码库目录。默认运行 Fixture，加 `--real` 才进入实测路径。

**内嵌核心实现 → project/04-multitenant-lora/run.py**

```python
"""Project 04 — multi-tenant, multi-model, multi-LoRA serving workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path

from phase3lab.shared.http_client import completion, discover_models, metrics_evidence
from phase3lab.shared.routing import EndpointState, SmartRouter
from phase3lab.shared.runner import LabSpec, PreconditionError, run_cli
from phase3lab.shared.tenancy import AdapterCache, TokenLedger
from phase3lab.shared.workload import WorkItem, load_jsonl

SPEC = LabSpec(
    lab_id="project-04-multitenant-lora",
    title="Project 04：Multi-Tenant, Multi-Model and Multi-LoRA Serving",
    goal="以加权公平顺序处理多租户请求，执行 Token 配额、模型/Adapter 选路、驻留淘汰和真实端点调用。",
    real_evidence=("tenant scheduler order", "served model/adapter discovery", "quota settlement", "adapter residency events"),
    required_inputs=("multi-ID vLLM endpoints", "tenant policy JSON", "multi-model/multi-adapter workload"),
    outputs=("fair schedule", "tenant accounting", "adapter hit/eviction trace", "per-ID metrics"),
    acceptance=("at least two tenants/models/adapters", "every accepted reservation settles", "adapter is explicit on every LoRA request", "fair scheduler is exercised"),
)

def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--serving-config", default="data/project04_serving.json")
    parser.add_argument("--tenant-policy", default="data/project04_tenants.json")
    parser.add_argument("--workload", default="data/project04_workload.jsonl")
    parser.add_argument("--quantum", type=int, default=64)

def read_json(path: str):
    target = Path(path)
    if not target.is_file():
        raise PreconditionError(f"file does not exist: {target}")
    return json.loads(target.read_text(encoding="utf-8")), hashlib.sha256(target.read_bytes()).hexdigest()

def deficit_round_robin(items: list[WorkItem], weights: dict[str, int], quantum: int) -> list[WorkItem]:
    if quantum < 1:
        raise ValueError("--quantum must be positive")
    queues = {tenant: deque(item for item in items if item.tenant == tenant) for tenant in sorted(weights)}
    unknown = sorted({item.tenant for item in items} - set(queues))
    if unknown:
        raise ValueError(f"workload has tenants without policy: {', '.join(unknown)}")
    deficits = {tenant: 0 for tenant in queues}
    result = []
    while any(queues.values()):
        progress = False
        for tenant, queue in queues.items():
            if not queue:
                continue
            deficits[tenant] += quantum * weights[tenant]
            while queue and queue[0].max_new_tokens <= deficits[tenant]:
                item = queue.popleft()
                deficits[tenant] -= item.max_new_tokens
                result.append(item)
                progress = True
        if not progress and any(queues.values()):
            continue
    return result

def jain_index(values: list[float]) -> float:
    if not values or sum(value * value for value in values) == 0:
        return 0.0
    return round(sum(values) ** 2 / (len(values) * sum(value * value for value in values)), 6)

def fixture(args: argparse.Namespace) -> dict:
    items = [
        WorkItem("a1", "chat", "p", 64, tenant="a", model="chat", adapter="sales"),
        WorkItem("a2", "chat", "p", 64, tenant="a", model="chat", adapter="finance"),
        WorkItem("b1", "reasoning", "p", 64, tenant="b", model="reasoning"),
    ]
    order = deficit_round_robin(items, {"a": 1, "b": 2}, args.quantum)
    cache = AdapterCache(1, ["sales"])
    events = [cache.touch("sales").__dict__, cache.touch("finance").__dict__]
    return {"schedule": [item.request_id for item in order], "adapter_events": events, "eviction_observed": events[-1]["evicted"] == "sales"}

def real(args: argparse.Namespace) -> dict:
    config, config_sha = read_json(args.serving_config)
    policies, policy_sha = read_json(args.tenant_policy)
    rows = config.get("endpoints", [])
    if len(rows) < 1:
        raise ValueError("serving config needs endpoints")
    limits = {}
    weights = {}
    for tenant, value in policies.items():
        if not isinstance(value, dict) or int(value.get("token_limit", 0)) < 1 or int(value.get("weight", 0)) < 1:
            raise ValueError(f"invalid tenant policy: {tenant}")
        limits[tenant] = int(value["token_limit"])
        weights[tenant] = int(value["weight"])
    endpoints = []
    caches = {}
    capabilities = {}
    actual_models = {}
    for row in rows:
        required = {"name", "url", "base_models", "adapter_ids", "adapter_cache_capacity"}
        missing = sorted(required - row.keys())
        if missing:
            raise ValueError(f"serving endpoint is missing: {', '.join(missing)}")
        actual = discover_models(row["url"])
        actual_models[row["name"]] = actual
        expected_ids = set(row["base_models"]) | set(row["adapter_ids"])
        missing_ids = expected_ids - set(actual)
        if missing_ids:
            raise PreconditionError(f"{row['name']} does not serve configured IDs: {', '.join(sorted(missing_ids))}")
        initial = list(row.get("initial_adapters", []))
        cache = AdapterCache(int(row["adapter_cache_capacity"]), initial)
        endpoint = EndpointState(row["name"], row["url"].rstrip("/"), set(row["base_models"]), capacity=int(row.get("capacity", 1)), adapters=set(initial))
        endpoints.append(endpoint)
        caches[endpoint.name] = cache
        capabilities[endpoint.name] = set(row["adapter_ids"])
    workload = load_jsonl(args.workload)
    tenants = {item.tenant for item in workload}
    models = {item.model for item in workload}
    adapters = {item.adapter for item in workload if item.adapter}
    if len(tenants) < 2 or len(models) < 2 or len(adapters) < 2:
        raise ValueError("workload must contain at least two tenants, two base models, and two adapters")
    schedule = deficit_round_robin(workload, weights, args.quantum)
    ledger = TokenLedger(limits)
    router = SmartRouter(endpoints, affinity_weight=0.25)
    records = []
    adapter_events = []
    tenant_tokens = defaultdict(int)
    for item in schedule:
        reserved = item.max_new_tokens
        if not ledger.reserve(item.tenant, item.request_id, reserved):
            records.append({"request_id": item.request_id, "tenant": item.tenant, "status": "quota_rejected", "ok": False})
            continue
        eligible = {endpoint.name for endpoint in endpoints if not item.adapter or item.adapter in capabilities[endpoint.name]}
        excluded = {endpoint.name for endpoint in endpoints if endpoint.name not in eligible}
        try:
            endpoint = router.choose(request_id=item.request_id, model=item.model, prefix_key=item.prefix_key, adapter=item.adapter, excluded=excluded)
        except RuntimeError:
            ledger.settle(item.tenant, item.request_id, reserved, 0)
            records.append({"request_id": item.request_id, "tenant": item.tenant, "status": "no_capacity", "ok": False})
            continue
        cache_event = caches[endpoint.name].touch(item.adapter)
        endpoint.adapters = set(caches[endpoint.name].entries)
        adapter_events.append({"request_id": item.request_id, "endpoint": endpoint.name, **cache_event.__dict__, "residency_source": "scheduler_state"})
        served_id = item.adapter or item.model
        record = completion(endpoint.url, served_id, item.prompt, item.max_new_tokens, request_id=item.request_id)
        router.complete(endpoint, latency_ms=record.latency_ms, ok=record.ok)
        actual = min(record.output_tokens or 0, reserved) if record.ok else 0
        ledger.settle(item.tenant, item.request_id, reserved, actual)
        tenant_tokens[item.tenant] += actual
        records.append({
            "request_id": item.request_id,
            "tenant": item.tenant,
            "base_model": item.model,
            "served_id": served_id,
            "adapter": item.adapter,
            "endpoint": endpoint.name,
            "status": "served" if record.ok else "failed",
            "ok": record.ok,
            "record": record.json(),
        })
    if any(ledger.reserved.values()):
        raise RuntimeError("quota reservations remain unsettled")
    normalized = [tenant_tokens[tenant] / weights[tenant] for tenant in sorted(weights)]
    evidence_urls = args.evidence_url or [endpoint.url for endpoint in endpoints]
    return {
        "config_sha256": config_sha,
        "policy_sha256": policy_sha,
        "workload_sha256": hashlib.sha256(Path(args.workload).read_bytes()).hexdigest(),
        "actual_models": actual_models,
        "schedule": [item.request_id for item in schedule],
        "records": records,
        "router_decisions": router.decisions,
        "adapter_events": adapter_events,
        "final_adapter_residency": {name: list(cache.entries) for name, cache in caches.items()},
        "quota_events": ledger.events,
        "tenant_output_tokens": dict(tenant_tokens),
        "weighted_jain_index": jain_index(normalized),
        "metrics": [metrics_evidence(url) for url in evidence_urls],
        "acceptance": {"tenants": len(tenants), "models": len(models), "adapters": len(adapters), "all_reservations_settled": not any(ledger.reserved.values())},
    }

def main() -> None:
    run_cli(SPEC, add_arguments, real, fixture)

if __name__ == "__main__":
    main()
```

## 5. 配置与输入合同

每次运行读取显式配置并生成不可歧义的运行身份。输入必须说明随机种子、工作负载、模型或代理模型、并发、截止时间、硬件模式和输出目录。配置校验拒绝负容量、非法概率、不存在的文件和互相冲突的开关。敏感凭证只从运行环境读取，不写入配置、报告或日志。

## 6. 机制模拟

模拟路径在 CPU 上连接 Model Registry、Adapter Registry、模型与 Adapter 缓存、热冷分层、预热控制器、Canary 与回滚，用离散事件或确定性状态机验证控制逻辑。模拟重点是因果方向、状态转换、容量边界和反例，不声称复刻真实 GPU 速度。输出记录 `fixture` 来源、工作负载、事件时间线、指标、故障和限制。

```bash
python project/04-multitenant-lora/run.py
```

模拟验收至少运行基线、候选和过载三组场景。关闭候选后应回到基线；提高负载到容量以上时必须出现排队、拒绝或服务等级失守；非法状态转换和无效输入必须被拒绝。固定随机种子后，结构化报告应可重复生成。

## 7. 真实本地路径

真实工作流直接执行“以加权公平顺序处理多租户请求，执行 Token 配额、模型/Adapter 选路、驻留淘汰和真实端点调用。”。运行输入为 `multi-ID vLLM endpoints`、`tenant policy JSON`、`multi-model/multi-adapter workload`；报告必须保留 `tenant scheduler order`、`served model/adapter discovery`、`quota settlement`、`adapter residency events`。只有 `source=measured` 可以支撑性能或发布结论，`source=fixture` 只验证控制逻辑。

```bash
python project/04-multitenant-lora/run.py --check-only

python project/04-multitenant-lora/run.py --real --serving-config data/project04_serving.json --tenant-policy data/project04_tenants.json --workload data/project04_workload.jsonl
```

缺少 `multi-ID vLLM endpoints`、`tenant policy JSON`、`multi-model/multi-adapter workload` 中任一真实前提时，脚本写入 `status=precondition_failed` 并以退出码 2 结束。真实路径没有 CPU fallback；性能报告只接受本次运行的 `source=measured` 记录。

## 8. 工作负载与指标

### 指标 1：correctness

项目为 correctness 记录计算口径、单位、分母、采集位置和窗口。报告中的聚合值能够从《Multi-Tenant、Multi-Model 与 Multi-LoRA Serving》事件重算，并与正确性、SLO 及故障恢复一同验收。

### 指标 2：latency

评审 latency 时使用《Multi-Tenant、Multi-Model 与 Multi-LoRA Serving》当前运行的原始数据。定义、单位、采集点、时间范围和分母全部随报告提供；任何以错误率、服务等级或恢复退化换来的改善都被门禁拦截。

### 指标 3：throughput

《Multi-Tenant、Multi-Model 与 Multi-LoRA Serving》把 throughput 作为一项可重算指标，而非单独结论。报告保存原始事件、口径、单位、分母与时间窗口，并同步检查输出正确性、服务等级和故障恢复。

### 指标 4：reliability

reliability 随《Multi-Tenant、Multi-Model 与 Multi-LoRA Serving》的原始事件保存，并注明定义、单位、采集点、时间窗口和分母。验收器可以重新计算聚合值；候选若以正确性、服务等级或恢复能力为代价，即使 reliability 改善也不通过。

### 指标 5：cost_efficiency

项目为 cost_efficiency 记录计算口径、单位、分母、采集位置和窗口。报告中的聚合值能够从《Multi-Tenant、Multi-Model 与 Multi-LoRA Serving》事件重算，并与正确性、SLO 及故障恢复一同验收。

## 9. 故障注入与诊断

### 故障 1：基座与 Adapter 不兼容

“基座与 Adapter 不兼容”由故障注入器稳定复现。系统需要给出告警、影响隔离、可解释降级和回滚事件；诊断依据任务 ID、制品摘要、配置、工作负载与组件时间线。进程恢复后仍要检查队列、缓存和在途任务。

### 故障 2：高基数 Adapter 缓存抖动

在《Multi-Tenant、Multi-Model 与 Multi-LoRA Serving》中注入“高基数 Adapter 缓存抖动”后，观察故障发现、隔离、降级、回退与恢复导流。证据链从任务身份和制品版本开始，经过配置、负载与组件事件，最后确认资源和在途工作回到稳定状态。

### 故障 3：并发模型加载拥塞

本场景复现“并发模型加载拥塞”。验收器检查发现时间、隔离范围、降级结果、回滚目标与恢复节奏，并用任务、制品、配置和负载定位根因。只有缓存、队列、资源及在途任务稳定后才算恢复完成。

### 故障 4：回滚修订不再常驻

主动制造“回滚修订不再常驻”，记录检测、隔离、降级、回滚和渐进恢复。排查时核对《Multi-Tenant、Multi-Model 与 Multi-LoRA Serving》任务身份、制品摘要、配置及负载，再沿组件事件定位故障。重新导流前确认在途任务、缓存、队列与资源稳定。

## 10. 验收阈值

- 每次推理可追溯模型和 Adapter 摘要。
- 冷请求与暖请求分别计量。
- 缓存驱逐具有迟滞。
- 错误修订可在不重启入口的情况下回滚。
- 指标可复现。
- 故障注入产生预期告警或降级。

## 11. 演示方法

先运行 `--check-only`，再执行 Fixture、真实路径、失败注入与报告验收。演示时明确区分 `source=fixture`、`source=measured` 和 `status=precondition_failed`；前提失败不能写成性能通过。

```bash
python project/04-multitenant-lora/run.py
python project/04-multitenant-lora/run.py --check-only
```

## 12. 交付物

- 源代码。
- 配置。
- 实验报告。
- 架构说明。
- 验收结果。

## 13. 项目小结

《Multi-Tenant、Multi-Model 与 Multi-LoRA Serving》将前序机制连接为具有接口、状态、证据和恢复边界的系统。验收时需要解释架构选择、收益验证、无效结果识别和故障恢复，并提交对应运行记录。

## 写在最后

多路复用决定了单节点承载密度，Fleet 级别的成本与 SLO 权衡还需要一个规划器与扩缩容器。下一篇：[GPU Fleet Planner 与 Autoscaler](/source/AI-Infra/3-大模型推理优化工程/35-GPUFleetPlanner与Autoscaler)。