# 生产级 LLM Inference Platform

## 1. 工程目标

![项目全景](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l36_01.png)

*项目全景：从输入、关键组件到验收证据形成一条可回放路径。*

集成控制面、数据面、路由、生命周期、可靠性与推理经济学，形成可验收平台。项目按完整工程链验收：能够运行、采集证据、演示关键行为，并在故障后恢复。所有结果随输入、配置、环境和版本保存。

## 2. 知识范围

项目整合以下前序能力：《Reasoning LLM Serving：长思考与 Test-Time Scaling》《Agentic Inference：工具调用、Fan-out 与长会话》《Structured Output Serving：Grammar、FSM 与 XGrammar》《Multimodal Serving：Encoder、Media Cache 与异构流水》《Compound AI Serving：Embedding、Reranker、LLM 与工具链》《OpenAI-Compatible AI Gateway：计量、配额与租户治理》《Distributed Replica Routing：负载、队列与预计完成时间》《Prefix、Session 与 KV-Locality Routing》《Multi-LoRA Serving：Adapter 缓存与热切换》《Multi-Model Serving：热冷模型与稀疏流量》《Model Registry 与 Inference Deployment 生命周期》《Weight Distribution：大模型权重分发与启动关键路径》《Cold Start Optimization：缓存、Warm Pool 与 GPU Memory Service》《LLM Serving Control Plane：Ray Serve、KServe 与 Dynamo》《Heterogeneous GPU Placement：异构设备与拓扑亲和性》《GPU Bin Packing：并行组、碎片与放置算法》《LLM Autoscaling：Queue、Token 与 SLA-aware Planner》《Capacity Planning：流量预测、Headroom 与 GPU Fleet》《Observability 与 Reliability：Trace、Canary、Drain 与隔离》《Inference Economics：Cost per Token、SLO 与全局优化》。实现时允许复用已有模块，但必须重新验证跨模块接口、身份、截止时间、错误传播和观测字段。

## 3. 系统边界与架构

### 组件 1：AI Gateway

AI Gateway 与 Smart Router 之间使用结构化合同。任务 ID、模型或策略版本随输入传入，输出附带配置摘要、时间、指标和错误，使隔离、回放和追踪拥有同一身份链。

### 组件 2：Smart Router

Smart Router 接收带版本和任务身份的输入，并向推理工作器输出结构化状态。接口记录配置摘要、起止时间、核心指标与失败原因。客户身份和模型修订通过显式字段传递，便于故障回放和租户隔离。

### 组件 3：推理工作器

在这套架构中，推理工作器维护清晰的能力边界。输入携带任务及版本，输出由模型生命周期控制器直接消费；运行记录包含配置、时间、指标和错误。租户与模型身份不放入不可见的全局状态。

### 组件 4：模型生命周期控制器

模型生命周期控制器负责处理已绑定任务和版本的输入，将可验证状态交给 GPU Fleet Planner。组件对外提供配置摘要、开始结束事件、指标及失败原因，身份信息始终经过接口传播。

### 组件 5：GPU Fleet Planner

GPU Fleet Planner 与 Trace 与成本证据面之间使用结构化合同。任务 ID、模型或策略版本随输入传入，输出附带配置摘要、时间、指标和错误，使隔离、回放和追踪拥有同一身份链。

### 组件 6：Trace 与成本证据面

Trace 与成本证据面接收带版本和任务身份的输入，并向 AI Gateway 输出结构化状态。接口记录配置摘要、起止时间、核心指标与失败原因。客户身份和模型修订通过显式字段传递，便于故障回放和租户隔离。

## 4. 目录映射

可执行文件为 `project/06-inference-platform/run.py`。所需的 HTTP、CUDA、统计、报告或状态机原语已经合并到这一入口。下方代码展示入口中内嵌的可读核心实现；下载包不再单独提供内部源码库目录。默认运行 Fixture，加 `--real` 才进入实测路径。

**内嵌核心实现 → project/06-inference-platform/run.py**

```python
"""Project 06 — integrated inference platform release and recovery workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path

from phase3lab.shared.control_plane import DeploymentController, Replica
from phase3lab.shared.http_client import completion, discover_models, metrics_evidence
from phase3lab.shared.planner import Autoscaler
from phase3lab.shared.routing import EndpointState, SmartRouter
from phase3lab.shared.runner import LabSpec, PreconditionError, run_cli
from phase3lab.shared.stats import percentile
from phase3lab.shared.tenancy import TokenLedger
from phase3lab.shared.workload import load_jsonl

SPEC = LabSpec(
    lab_id="project-06-inference-platform",
    title="Project 06：Production LLM Inference Platform",
    goal="把版本注册、Canary、Gateway 选路、配额、故障回退、扩缩容和成本证据连接成一次完整运行。",
    real_evidence=("replica lifecycle events", "live endpoint calls", "shadow correctness pairs", "quota/autoscaler/cost evidence"),
    required_inputs=("stable/candidate endpoints", "platform config", "tenant workload"),
    outputs=("end-to-end trace", "release decision", "failure recovery", "capacity and cost report"),
    acceptance=("invalid lifecycle transitions fail", "candidate is shadow-compared", "failed candidate returns traffic to stable", "all reservations settle", "final state is explicit"),
)

def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--platform-config", default="data/project06_platform.json")
    parser.add_argument("--workload", default="data/project06_workload.jsonl")
    parser.add_argument("--failure-at", type=int, default=3, help="request index at which candidate is marked failed; use -1 to disable")

def read_json(path: str) -> tuple[dict, str]:
    target = Path(path)
    if not target.is_file():
        raise PreconditionError(f"configuration does not exist: {target}")
    raw = target.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("platform config must be a JSON object")
    return value, hashlib.sha256(raw).hexdigest()

def assignment(request_id: str, percent: int) -> str:
    if not 1 <= percent <= 99:
        raise ValueError("canary_percent must be in [1, 99]")
    bucket = int(hashlib.sha256(request_id.encode()).hexdigest()[:8], 16) % 100
    return "candidate" if bucket < percent else "stable"

def release_gate(pairs: list[dict], max_p95_ratio: float, candidate_failed: bool) -> dict:
    if not pairs:
        return {"passed": False, "reason": "no_candidate_shadow_pairs", "pairs": 0}
    candidate_ok = [pair["candidate"]["ok"] for pair in pairs]
    shadow_ok = [pair["stable_shadow"]["ok"] for pair in pairs]
    equal = [pair["outputs_equal"] for pair in pairs]
    candidate_latency = [pair["candidate"]["latency_ms"] for pair in pairs if pair["candidate"]["ok"]]
    shadow_latency = [pair["stable_shadow"]["latency_ms"] for pair in pairs if pair["stable_shadow"]["ok"]]
    ratio = percentile(candidate_latency, 0.95) / max(percentile(shadow_latency, 0.95), 1e-9) if candidate_latency and shadow_latency else float("inf")
    passed = all(candidate_ok) and all(shadow_ok) and all(equal) and ratio <= max_p95_ratio and not candidate_failed
    return {
        "passed": passed,
        "pairs": len(pairs),
        "all_candidate_success": all(candidate_ok),
        "all_shadow_success": all(shadow_ok),
        "all_outputs_equal": all(equal),
        "candidate_p95_ratio": round(ratio, 6),
        "max_p95_ratio": max_p95_ratio,
        "candidate_failed": candidate_failed,
    }

def fixture(args: argparse.Namespace) -> dict:
    controller = DeploymentController()
    controller.add(Replica("stable-0", "r1", "http://stable"))
    controller.add(Replica("candidate-0", "r2", "http://candidate"))
    for replica in ("stable-0", "candidate-0"):
        controller.transition(replica, "LOADING", reason="fixture deploy")
        controller.transition(replica, "READY", reason="fixture health probe")
    controller.transition("candidate-0", "FAILED", reason="fixture fault")
    pairs = [{"candidate": {"ok": True, "latency_ms": 90}, "stable_shadow": {"ok": True, "latency_ms": 100}, "outputs_equal": True}]
    gate = release_gate(pairs, 1.2, candidate_failed=True)
    return {"controller_events": controller.events, "release_gate": gate, "final_revision": "stable", "failure_recovered": not gate["passed"]}

def validate_config(config: dict) -> None:
    required = {"model", "stable", "candidate", "tenant_limits", "canary_percent", "max_candidate_p95_ratio", "capacity", "demand_windows_tps", "hourly_cost_usd"}
    missing = sorted(required - config.keys())
    if missing:
        raise ValueError(f"platform config is missing: {', '.join(missing)}")
    for role in ("stable", "candidate"):
        if not {"revision", "url"} <= config[role].keys():
            raise ValueError(f"{role} config requires revision and url")
    capacity = config["capacity"]
    evidence_sha = str(capacity.get("evidence_sha256", ""))
    if capacity.get("source") != "measured" or not re.fullmatch(r"[0-9a-f]{64}", evidence_sha) or set(evidence_sha) == {"0"} or float(capacity.get("tokens_per_second", 0)) <= 0:
        raise ValueError("capacity must be measured and carry a non-placeholder evidence SHA-256")
    if float(config["hourly_cost_usd"]) <= 0:
        raise ValueError("hourly_cost_usd must be positive")
    if not isinstance(config["tenant_limits"], dict) or not config["tenant_limits"] or any(int(value) < 1 for value in config["tenant_limits"].values()):
        raise ValueError("tenant_limits must map tenants to positive values")
    if len(config["demand_windows_tps"]) < 3 or any(float(value) < 0 for value in config["demand_windows_tps"]):
        raise ValueError("demand_windows_tps needs at least three non-negative windows")

def real(args: argparse.Namespace) -> dict:
    config, config_sha = read_json(args.platform_config)
    validate_config(config)
    workload_path = Path(args.workload)
    workload = load_jsonl(workload_path)
    workload_sha = hashlib.sha256(workload_path.read_bytes()).hexdigest()
    model = str(config["model"])
    stable_url = str(config["stable"]["url"]).rstrip("/")
    candidate_url = str(config["candidate"]["url"]).rstrip("/")
    if stable_url == candidate_url:
        raise ValueError("stable and candidate endpoints must be distinct")
    discovered = {"stable": discover_models(stable_url), "candidate": discover_models(candidate_url)}
    if any(model not in values for values in discovered.values()):
        raise PreconditionError("stable and candidate do not both serve the configured model")
    metrics_before = {"stable": metrics_evidence(stable_url), "candidate": metrics_evidence(candidate_url)}

    controller = DeploymentController()
    controller.add(Replica("stable-0", str(config["stable"]["revision"]), stable_url))
    controller.add(Replica("candidate-0", str(config["candidate"]["revision"]), candidate_url))
    for replica_id in ("stable-0", "candidate-0"):
        controller.transition(replica_id, "LOADING", reason="deployment requested")
        controller.transition(replica_id, "READY", reason="model discovery and metrics probe passed")

    endpoint_states = [EndpointState("stable", stable_url, {model}, capacity=int(config["stable"].get("capacity", 2))), EndpointState("candidate", candidate_url, {model}, capacity=int(config["candidate"].get("capacity", 1)))]
    router = SmartRouter(endpoint_states)
    ledger = TokenLedger({str(key): int(value) for key, value in config["tenant_limits"].items()})
    records = []
    shadow_pairs = []
    candidate_failed = False
    run_started = time.perf_counter()
    for index, item in enumerate(workload):
        reserved = item.max_new_tokens
        if not ledger.reserve(item.tenant, item.request_id, reserved):
            records.append({"request_id": item.request_id, "status": "quota_rejected", "tenant": item.tenant})
            continue
        desired = assignment(item.request_id, int(config["canary_percent"]))
        injected = args.failure_at >= 0 and index >= args.failure_at and desired == "candidate" and not candidate_failed
        selected_role = "stable" if desired == "candidate" and candidate_failed else desired
        excluded = {state.name for state in endpoint_states if state.name != selected_role}
        selected = router.choose(request_id=item.request_id, model=model, prefix_key=item.prefix_key, excluded=excluded)
        request_model = str(config.get("failure_model_id", model + "__phase3_missing_revision__")) if injected else model
        primary = completion(selected.url, request_model, item.prompt, item.max_new_tokens, request_id=f"{item.request_id}/{selected_role}")
        router.complete(selected, latency_ms=primary.latency_ms, ok=primary.ok)
        if injected:
            if primary.ok:
                raise RuntimeError("failure injection model unexpectedly succeeded; configure a guaranteed-missing failure_model_id")
            candidate_failed = True
            router.mark_health("candidate", False)
            controller.transition("candidate-0", "FAILED", reason=f"unknown-revision probe failed for {item.request_id}")
        attempts = [{"role": selected_role, "injected_model": request_model if injected else None, "record": primary.json()}]
        final = primary
        stable_retry = None
        if not primary.ok and selected_role == "candidate":
            stable_state = next(state for state in endpoint_states if state.name == "stable")
            stable_retry = completion(stable_state.url, model, item.prompt, item.max_new_tokens, request_id=f"{item.request_id}/stable-retry")
            attempts.append({"role": "stable-retry", "record": stable_retry.json()})
            final = stable_retry
        if desired == "candidate" and selected_role == "candidate":
            shadow = stable_retry or completion(stable_url, model, item.prompt, item.max_new_tokens, request_id=f"{item.request_id}/stable-shadow")
            shadow_pairs.append({"request_id": item.request_id, "candidate": primary.json(), "stable_shadow": shadow.json(), "outputs_equal": primary.ok and shadow.ok and primary.text_sha256 == shadow.text_sha256})
        actual = min(final.output_tokens or 0, reserved) if final.ok else 0
        ledger.settle(item.tenant, item.request_id, reserved, actual)
        records.append({
            "request_id": item.request_id,
            "tenant": item.tenant,
            "desired_revision": desired,
            "served_revision": selected_role,
            "failure_injected": injected,
            "status": "served" if final.ok else "failed",
            "attempts": attempts,
        })
    run_seconds = time.perf_counter() - run_started
    if any(ledger.reserved.values()):
        raise RuntimeError("quota reservations remain unsettled")
    gate = release_gate(shadow_pairs, float(config["max_candidate_p95_ratio"]), candidate_failed)
    if gate["passed"]:
        controller.transition("stable-0", "DRAINING", reason="candidate gate passed")
        controller.transition("stable-0", "STOPPED", reason="candidate promoted")
        final_revision = "candidate"
    else:
        candidate_replica = controller.replicas["candidate-0"]
        if candidate_replica.state == "READY":
            controller.transition("candidate-0", "DRAINING", reason="candidate gate failed")
            controller.transition("candidate-0", "STOPPED", reason="rollback complete")
        final_revision = "stable"

    capacity = float(config["capacity"]["tokens_per_second"])
    scaler = Autoscaler(minimum=int(config["capacity"].get("minimum_replicas", 1)), maximum=int(config["capacity"].get("maximum_replicas", 8)))
    autoscaler_events = [scaler.tick(index, demand_tps=float(demand), replica_capacity_tps=capacity, target_utilization=float(config["capacity"].get("target_utilization", 0.7)), startup_windows=int(config["capacity"].get("startup_windows", 2))) for index, demand in enumerate(config["demand_windows_tps"])]
    ready_during_run = 2
    run_cost = run_seconds / 3600 * ready_during_run * float(config["hourly_cost_usd"])
    return {
        "evidence": {"config_sha256": config_sha, "workload_sha256": workload_sha, "capacity_evidence_sha256": config["capacity"]["evidence_sha256"]},
        "discovered_models": discovered,
        "metrics_before": metrics_before,
        "metrics_after": {"stable": metrics_evidence(stable_url), "candidate": metrics_evidence(candidate_url)},
        "controller_events": controller.events,
        "route_decisions": router.decisions,
        "quota_events": ledger.events,
        "records": records,
        "shadow_pairs": shadow_pairs,
        "release_gate": gate,
        "final_revision": final_revision,
        "autoscaler_events": autoscaler_events,
        "cost": {"hourly_cost_usd_per_replica": config["hourly_cost_usd"], "ready_replicas_during_run": ready_during_run, "run_seconds": round(run_seconds, 6), "run_cost_usd": round(run_cost, 8), "billing_scope": "conservative two-ready-replica wall-clock window"},
        "acceptance": {
            "all_reservations_settled": not any(ledger.reserved.values()),
            "shadow_pairs": len(shadow_pairs),
            "failure_injected": candidate_failed,
            "failure_recovered_to_stable": candidate_failed and final_revision == "stable",
            "final_revision": final_revision,
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

模拟路径在 CPU 上连接 AI Gateway、Smart Router、推理工作器、模型生命周期控制器、GPU Fleet Planner、Trace 与成本证据面，用离散事件或确定性状态机验证控制逻辑。模拟重点是因果方向、状态转换、容量边界和反例，不声称复刻真实 GPU 速度。输出记录 `fixture` 来源、工作负载、事件时间线、指标、故障和限制。

```bash
python project/06-inference-platform/run.py
```

模拟验收至少运行基线、候选和过载三组场景。关闭候选后应回到基线；提高负载到容量以上时必须出现排队、拒绝或服务等级失守；非法状态转换和无效输入必须被拒绝。固定随机种子后，结构化报告应可重复生成。

## 7. 真实本地路径

真实工作流直接执行“把版本注册、Canary、Gateway 选路、配额、故障回退、扩缩容和成本证据连接成一次完整运行。”。运行输入为 `stable/candidate endpoints`、`platform config`、`tenant workload`；报告必须保留 `replica lifecycle events`、`live endpoint calls`、`shadow correctness pairs`、`quota/autoscaler/cost evidence`。只有 `source=measured` 可以支撑性能或发布结论，`source=fixture` 只验证控制逻辑。

```bash
python project/06-inference-platform/run.py --check-only

python project/06-inference-platform/run.py --real --platform-config data/project06_platform.json --workload data/project06_workload.jsonl --failure-at 3
```

缺少 `stable/candidate endpoints`、`platform config`、`tenant workload` 中任一真实前提时，脚本写入 `status=precondition_failed` 并以退出码 2 结束。真实路径没有 CPU fallback；性能报告只接受本次运行的 `source=measured` 记录。

## 8. 工作负载与指标

### 指标 1：correctness

《生产级 LLM Inference Platform》把 correctness 作为一项可重算指标，而非单独结论。报告保存原始事件、口径、单位、分母与时间窗口，并同步检查输出正确性、服务等级和故障恢复。

### 指标 2：latency

latency 随《生产级 LLM Inference Platform》的原始事件保存，并注明定义、单位、采集点、时间窗口和分母。验收器可以重新计算聚合值；候选若以正确性、服务等级或恢复能力为代价，即使 latency 改善也不通过。

### 指标 3：throughput

项目为 throughput 记录计算口径、单位、分母、采集位置和窗口。报告中的聚合值能够从《生产级 LLM Inference Platform》事件重算，并与正确性、SLO 及故障恢复一同验收。

### 指标 4：reliability

评审 reliability 时使用《生产级 LLM Inference Platform》当前运行的原始数据。定义、单位、采集点、时间范围和分母全部随报告提供；任何以错误率、服务等级或恢复退化换来的改善都被门禁拦截。

### 指标 5：cost_efficiency

《生产级 LLM Inference Platform》把 cost_efficiency 作为一项可重算指标，而非单独结论。报告保存原始事件、口径、单位、分母与时间窗口，并同步检查输出正确性、服务等级和故障恢复。

## 9. 故障注入与诊断

### 故障 1：工作器失联引发重试风暴

本场景复现“工作器失联引发重试风暴”。验收器检查发现时间、隔离范围、降级结果、回滚目标与恢复节奏，并用任务、制品、配置和负载定位根因。只有缓存、队列、资源及在途任务稳定后才算恢复完成。

### 故障 2：新修订进程健康但真实路径失败

主动制造“新修订进程健康但真实路径失败”，记录检测、隔离、降级、回滚和渐进恢复。排查时核对《生产级 LLM Inference Platform》任务身份、制品摘要、配置及负载，再沿组件事件定位故障。重新导流前确认在途任务、缓存、队列与资源稳定。

### 故障 3：控制面短暂不可用阻塞数据面

“控制面短暂不可用阻塞数据面”由故障注入器稳定复现。系统需要给出告警、影响隔离、可解释降级和回滚事件；诊断依据任务 ID、制品摘要、配置、工作负载与组件时间线。进程恢复后仍要检查队列、缓存和在途任务。

### 故障 4：局部优化改善吞吐却提高有效成本

在《生产级 LLM Inference Platform》中注入“局部优化改善吞吐却提高有效成本”后，观察故障发现、隔离、降级、回退与恢复导流。证据链从任务身份和制品版本开始，经过配置、负载与组件事件，最后确认资源和在途工作回到稳定状态。

## 10. 验收阈值

- 任务能够从入口追踪到模型与设备。
- 发布按制品校验、Canary、灰度和回滚推进。
- 故障注入触发隔离和渐进恢复。
- 最终报告同时包含质量、SLO、可靠性和成本。
- 指标可复现。
- 故障注入产生预期告警或降级。

## 11. 演示方法

先运行 `--check-only`，再执行 Fixture、真实路径、失败注入与报告验收。演示时明确区分 `source=fixture`、`source=measured` 和 `status=precondition_failed`；前提失败不能写成性能通过。

```bash
python project/06-inference-platform/run.py
python project/06-inference-platform/run.py --check-only
```

## 12. 交付物

- 源代码。
- 配置。
- 实验报告。
- 架构说明。
- 验收结果。

## 13. 项目小结

《生产级 LLM Inference Platform》的最终证据覆盖系统接口、状态变化、指标和恢复。需要说明取舍理由，重现候选收益，识别无效测量，并演示故障后的稳定恢复。

## 写在最后

三期从 Speculator 的性能边界一路走到可验收的推理平台：算法收益要用统一口径衡量，负载形态决定容量分母，路由与多路复用决定资源密度，生命周期与可靠性决定发布能否回退，经济性把这一切折算成每有效 Token 的成本。下一期转向承载这些服务的平台本身：[AI 平台工程](/source/AI-Infra/4-AI平台工程/README)。