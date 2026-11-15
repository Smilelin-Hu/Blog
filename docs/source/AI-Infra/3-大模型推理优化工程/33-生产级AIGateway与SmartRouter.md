# 生产级 AI Gateway 与 Smart Router

## 1. 工程目标

![项目全景](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l33_01.png)

*项目全景：从输入、关键组件到验收证据形成一条可回放路径。*

实现多租户网关、Token 配额、负载与 KV locality 联合路由。实现要覆盖正常运行、指标采集、现场演示和故障恢复。报告只收录与输入、配置、环境及版本绑定的实测或模拟结果。

## 2. 知识范围

项目整合以下前序能力：《OpenAI-Compatible AI Gateway：计量、配额与租户治理》《Distributed Replica Routing：负载、队列与预计完成时间》《Prefix、Session 与 KV-Locality Routing》。实现时允许复用已有模块，但必须重新验证跨模块接口、身份、截止时间、错误传播和观测字段。

## 3. 系统边界与架构

### 组件 1：兼容 API 入口

兼容 API 入口接收带版本和任务身份的输入，并向租户身份与配额输出结构化状态。接口记录配置摘要、起止时间、核心指标与失败原因。客户身份和模型修订通过显式字段传递，便于故障回放和租户隔离。

### 组件 2：租户身份与配额

在这套架构中，租户身份与配额维护清晰的能力边界。输入携带任务及版本，输出由 Token 预留结算直接消费；运行记录包含配置、时间、指标和错误。租户与模型身份不放入不可见的全局状态。

### 组件 3：Token 预留结算

Token 预留结算负责处理已绑定任务和版本的输入，将可验证状态交给负载感知路由。组件对外提供配置摘要、开始结束事件、指标及失败原因，身份信息始终经过接口传播。

### 组件 4：负载感知路由

负载感知路由与 KV Locality 路由之间使用结构化合同。任务 ID、模型或策略版本随输入传入，输出附带配置摘要、时间、指标和错误，使隔离、回放和追踪拥有同一身份链。

### 组件 5：KV Locality 路由

KV Locality 路由接收带版本和任务身份的输入，并向流式代理与取消输出结构化状态。接口记录配置摘要、起止时间、核心指标与失败原因。客户身份和模型修订通过显式字段传递，便于故障回放和租户隔离。

### 组件 6：流式代理与取消

在这套架构中，流式代理与取消维护清晰的能力边界。输入携带任务及版本，输出由兼容 API 入口直接消费；运行记录包含配置、时间、指标和错误。租户与模型身份不放入不可见的全局状态。

## 4. 目录映射

可执行文件为 `project/03-smart-router/run.py`。所需的 HTTP、CUDA、统计、报告或状态机原语已经合并到这一入口。下方代码展示入口中内嵌的可读核心实现；下载包不再单独提供内部源码库目录。默认运行 Fixture，加 `--real` 才进入实测路径。

**内嵌核心实现 → project/03-smart-router/run.py**

```python
"""Project 03 — stateful Smart Router with quota, affinity, and failover."""

from __future__ import annotations

import argparse
import hashlib
import json
import threading
from pathlib import Path

from phase3lab.shared.http_client import completion, discover_models, metrics_evidence
from phase3lab.shared.routing import EndpointState, SmartRouter
from phase3lab.shared.runner import LabSpec, PreconditionError, run_cli
from phase3lab.shared.tenancy import TokenLedger
from phase3lab.shared.workload import WorkItem, load_jsonl, replay

SPEC = LabSpec(
    lab_id="project-03-smart-router",
    title="Project 03：Production AI Gateway and Smart Router",
    goal="执行租户配额预留、负载选路、Prefix 亲和、请求发送、失败反馈和一次故障转移。",
    real_evidence=("validated router config", "decision log", "primary/retry request records", "quota ledger"),
    required_inputs=("at least two endpoints", "tenant workload", "quota JSON"),
    outputs=("route trace", "failover trace", "endpoint state", "quota settlements"),
    acceptance=("every accepted request has a decision", "failed primary excludes that endpoint on retry", "prefix affinity is stateful", "reservations settle"),
)

def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--router-config", default="data/project03_router.json")
    parser.add_argument("--workload", default="data/project03_workload.jsonl")
    parser.add_argument("--quota", default="data/project03_quotas.json")
    parser.add_argument("--time-scale", type=float, default=1.0)
    parser.add_argument("--fail-endpoint", default="", help="mark one configured endpoint unhealthy before replay")

def read_json(path: str):
    target = Path(path)
    if not target.is_file():
        raise PreconditionError(f"configuration file does not exist: {target}")
    return json.loads(target.read_text(encoding="utf-8")), hashlib.sha256(target.read_bytes()).hexdigest()

def load_endpoints(path: str) -> tuple[list[EndpointState], str]:
    value, digest = read_json(path)
    rows = value.get("endpoints") if isinstance(value, dict) else None
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("router config needs at least two endpoints")
    endpoints = []
    for row in rows:
        required = {"name", "url", "models", "capacity"}
        missing = sorted(required - row.keys())
        if missing:
            raise ValueError(f"router endpoint is missing: {', '.join(missing)}")
        endpoints.append(EndpointState(
            name=str(row["name"]),
            url=str(row["url"]).rstrip("/"),
            models=set(str(value) for value in row["models"]),
            capacity=int(row["capacity"]),
            adapters=set(str(value) for value in row.get("adapters", [])),
        ))
    if len({item.name for item in endpoints}) != len(endpoints) or len({item.url for item in endpoints}) != len(endpoints):
        raise ValueError("endpoint names and URLs must be unique")
    return endpoints, digest

def fixture(args: argparse.Namespace) -> dict:
    endpoints = [EndpointState("r0", "http://r0", {"chat"}, capacity=2), EndpointState("r1", "http://r1", {"chat"}, capacity=2)]
    router = SmartRouter(endpoints, affinity_weight=0.7)
    first = router.choose(request_id="a-1", model="chat", prefix_key="account-a")
    router.complete(first, latency_ms=120, ok=False)
    first.healthy = False
    retry = router.choose(request_id="a-1-retry", model="chat", prefix_key="account-a", excluded={first.name})
    router.complete(retry, latency_ms=90, ok=True)
    ledger = TokenLedger({"team-a": 100})
    accepted = ledger.reserve("team-a", "a-1", 40)
    ledger.settle("team-a", "a-1", 40, 25)
    return {"primary": first.name, "retry": retry.name, "different_endpoint": first.name != retry.name, "quota_accepted": accepted, "decisions": router.decisions, "ledger": ledger.events}

def real(args: argparse.Namespace) -> dict:
    endpoints, config_sha = load_endpoints(args.router_config)
    quota_value, quota_sha = read_json(args.quota)
    if not isinstance(quota_value, dict) or not quota_value:
        raise ValueError("quota file must map tenant IDs to positive token limits")
    ledger = TokenLedger({str(key): int(value) for key, value in quota_value.items()})
    workload = load_jsonl(args.workload)
    actual_models = {}
    for endpoint in endpoints:
        actual = discover_models(endpoint.url)
        actual_models[endpoint.name] = actual
        missing = endpoint.models - set(actual)
        if missing:
            raise PreconditionError(f"{endpoint.name} does not serve configured models: {', '.join(sorted(missing))}")
    if args.fail_endpoint:
        failed = next((item for item in endpoints if item.name == args.fail_endpoint), None)
        if failed is None:
            raise ValueError("--fail-endpoint is not in router config")
        failed.healthy = False
    router = SmartRouter(endpoints, affinity_weight=0.7)
    lock = threading.Lock()

    def send(item: WorkItem) -> dict:
        reserve = item.max_new_tokens
        with lock:
            accepted = ledger.reserve(item.tenant, item.request_id, reserve)
            if not accepted:
                return {"request_id": item.request_id, "tenant": item.tenant, "status": "quota_rejected", "ok": False, "slo_pass": False, "attempts": []}
            primary = router.choose(request_id=item.request_id, model=item.model, prefix_key=item.prefix_key, adapter=item.adapter)
        served_id = item.adapter or item.model
        primary_record = completion(primary.url, served_id, item.prompt, item.max_new_tokens, request_id=f"{item.request_id}/primary")
        with lock:
            router.complete(primary, latency_ms=primary_record.latency_ms, ok=primary_record.ok)
        attempts = [{"role": "primary", "endpoint": primary.name, "record": primary_record.json()}]
        final = primary_record
        if not primary_record.ok:
            try:
                with lock:
                    retry = router.choose(request_id=f"{item.request_id}/retry", model=item.model, prefix_key=item.prefix_key, adapter=item.adapter, excluded={primary.name})
                retry_record = completion(retry.url, served_id, item.prompt, item.max_new_tokens, request_id=f"{item.request_id}/retry")
                with lock:
                    router.complete(retry, latency_ms=retry_record.latency_ms, ok=retry_record.ok)
                attempts.append({"role": "retry", "endpoint": retry.name, "record": retry_record.json()})
                final = retry_record
            except RuntimeError as exc:
                attempts.append({"role": "retry", "error": str(exc)})
        actual = min(final.output_tokens or 0, reserve) if final.ok else 0
        with lock:
            ledger.settle(item.tenant, item.request_id, reserve, actual)
        end_to_end = sum(attempt.get("record", {}).get("latency_ms", 0) for attempt in attempts)
        return {
            "request_id": item.request_id,
            "tenant": item.tenant,
            "model": item.model,
            "adapter": item.adapter,
            "prefix_key": item.prefix_key,
            "status": "served" if final.ok else "failed",
            "ok": final.ok,
            "slo_pass": final.ok and end_to_end <= item.deadline_ms,
            "end_to_end_ms": round(end_to_end, 4),
            "attempts": attempts,
        }

    records = replay(workload, send, concurrency=args.concurrency, time_scale=args.time_scale)
    outstanding = {tenant: value for tenant, value in ledger.reserved.items() if value}
    if outstanding:
        raise RuntimeError(f"unsettled quota reservations: {outstanding}")
    failovers = [record for record in records if len(record.get("attempts", [])) > 1]
    for record in failovers:
        endpoint_names = [attempt.get("endpoint") for attempt in record["attempts"] if attempt.get("endpoint")]
        if len(endpoint_names) >= 2 and endpoint_names[0] == endpoint_names[1]:
            raise RuntimeError("failover retried the failed primary endpoint")
    evidence_urls = args.evidence_url or [item.url for item in endpoints]
    return {
        "config_sha256": config_sha,
        "quota_sha256": quota_sha,
        "workload_sha256": hashlib.sha256(Path(args.workload).read_bytes()).hexdigest(),
        "actual_models": actual_models,
        "records": records,
        "route_decisions": router.decisions,
        "endpoint_state": [item.json() for item in endpoints],
        "quota_events": ledger.events,
        "metrics": [metrics_evidence(url) for url in evidence_urls],
        "acceptance": {
            "all_reservations_settled": not outstanding,
            "failover_count": len(failovers),
            "quota_rejections": sum(record["status"] == "quota_rejected" for record in records),
            "served": sum(record["status"] == "served" for record in records),
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

模拟路径在 CPU 上连接兼容 API 入口、租户身份与配额、Token 预留结算、负载感知路由、KV Locality 路由、流式代理与取消，用离散事件或确定性状态机验证控制逻辑。模拟重点是因果方向、状态转换、容量边界和反例，不声称复刻真实 GPU 速度。输出记录 `fixture` 来源、工作负载、事件时间线、指标、故障和限制。

```bash
python project/03-smart-router/run.py
```

模拟验收至少运行基线、候选和过载三组场景。关闭候选后应回到基线；提高负载到容量以上时必须出现排队、拒绝或服务等级失守；非法状态转换和无效输入必须被拒绝。固定随机种子后，结构化报告应可重复生成。

## 7. 真实本地路径

真实工作流直接执行“执行租户配额预留、负载选路、Prefix 亲和、请求发送、失败反馈和一次故障转移。”。运行输入为 `at least two endpoints`、`tenant workload`、`quota JSON`；报告必须保留 `validated router config`、`decision log`、`primary/retry request records`、`quota ledger`。只有 `source=measured` 可以支撑性能或发布结论，`source=fixture` 只验证控制逻辑。

```bash
python project/03-smart-router/run.py --check-only

python project/03-smart-router/run.py --real --router-config data/project03_router.json --workload data/project03_workload.jsonl --quota data/project03_quotas.json
```

缺少 `at least two endpoints`、`tenant workload`、`quota JSON` 中任一真实前提时，脚本写入 `status=precondition_failed` 并以退出码 2 结束。真实路径没有 CPU fallback；性能报告只接受本次运行的 `source=measured` 记录。

## 8. 工作负载与指标

### 指标 1：correctness

correctness 随《生产级 AI Gateway 与 Smart Router》的原始事件保存，并注明定义、单位、采集点、时间窗口和分母。验收器可以重新计算聚合值；候选若以正确性、服务等级或恢复能力为代价，即使 correctness 改善也不通过。

### 指标 2：latency

项目为 latency 记录计算口径、单位、分母、采集位置和窗口。报告中的聚合值能够从《生产级 AI Gateway 与 Smart Router》事件重算，并与正确性、SLO 及故障恢复一同验收。

### 指标 3：throughput

评审 throughput 时使用《生产级 AI Gateway 与 Smart Router》当前运行的原始数据。定义、单位、采集点、时间范围和分母全部随报告提供；任何以错误率、服务等级或恢复退化换来的改善都被门禁拦截。

### 指标 4：reliability

《生产级 AI Gateway 与 Smart Router》把 reliability 作为一项可重算指标，而非单独结论。报告保存原始事件、口径、单位、分母与时间窗口，并同步检查输出正确性、服务等级和故障恢复。

### 指标 5：cost_efficiency

cost_efficiency 随《生产级 AI Gateway 与 Smart Router》的原始事件保存，并注明定义、单位、采集点、时间窗口和分母。验收器可以重新计算聚合值；候选若以正确性、服务等级或恢复能力为代价，即使 cost_efficiency 改善也不通过。

## 9. 故障注入与诊断

### 故障 1：配额预留未释放

主动制造“配额预留未释放”，记录检测、隔离、降级、回滚和渐进恢复。排查时核对《生产级 AI Gateway 与 Smart Router》任务身份、制品摘要、配置及负载，再沿组件事件定位故障。重新导流前确认在途任务、缓存、队列与资源稳定。

### 故障 2：热点缓存副本严重排队

“热点缓存副本严重排队”由故障注入器稳定复现。系统需要给出告警、影响隔离、可解释降级和回滚事件；诊断依据任务 ID、制品摘要、配置、工作负载与组件时间线。进程恢复后仍要检查队列、缓存和在途任务。

### 故障 3：回退模型能力不等价

在《生产级 AI Gateway 与 Smart Router》中注入“回退模型能力不等价”后，观察故障发现、隔离、降级、回退与恢复导流。证据链从任务身份和制品版本开始，经过配置、负载与组件事件，最后确认资源和在途工作回到稳定状态。

### 故障 4：客户端重试放大后端负载

本场景复现“客户端重试放大后端负载”。验收器检查发现时间、隔离范围、降级结果、回滚目标与恢复节奏，并用任务、制品、配置和负载定位根因。只有缓存、队列、资源及在途任务稳定后才算恢复完成。

## 10. 验收阈值

- 租户间配额和凭证严格隔离。
- 计量能够与请求完成状态对账。
- 热点超过阈值时允许牺牲缓存分流。
- 排空副本不再接收新请求。
- 指标可复现。
- 故障注入产生预期告警或降级。

## 11. 演示方法

先运行 `--check-only`，再执行 Fixture、真实路径、失败注入与报告验收。演示时明确区分 `source=fixture`、`source=measured` 和 `status=precondition_failed`；前提失败不能写成性能通过。

```bash
python project/03-smart-router/run.py
python project/03-smart-router/run.py --check-only
```

## 12. 交付物

- 源代码。
- 配置。
- 实验报告。
- 架构说明。
- 验收结果。

## 13. 项目小结

本项目把相关前序能力组合成一条可追踪工程链。交付说明架构决策、验证方法、结果限制与恢复路径，并以实际运行和故障注入记录支撑结论。

## 写在最后

Gateway 之后是多路复用的服务端：同一批 GPU 上同时承载多租户、多模型与多 Adapter。下一篇：[Multi-Tenant、Multi-Model 与 Multi-LoRA Serving](/source/AI-Infra/3-大模型推理优化工程/34-Multi-Tenant-Multi-Model与Multi-LoRAServing)。