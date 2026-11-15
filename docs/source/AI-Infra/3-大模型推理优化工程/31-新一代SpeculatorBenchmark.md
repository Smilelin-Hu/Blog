# 新一代 Speculator Benchmark

## 1. 工程目标

![项目全景](https://raw.githubusercontent.com/swpucwf/MyBolgImage/main/img/aiinfra_y3_l31_01.png)

*项目全景：从输入、关键组件到验收证据形成一条可回放路径。*

比较 EAGLE-3、MTP、DFlash 系列及自适应验证策略，输出可复现 Pareto 前沿。交付物需要连通运行、测量、演示和故障恢复。每项结果都能追溯到输入、配置、环境及版本，并由实际执行产生。

## 2. 知识范围

项目整合以下前序能力：《经典 Speculative Decoding 之后的性能边界》《EAGLE-3：Training-Time Test 与直接 Token 预测》《P-EAGLE：并行 Drafter 与长上下文训练》《MTP Serving：原生多 Token 预测头的部署》《DFlash：Block Diffusion Speculative Decoding》《DFlare：Layer-wise Fusion 与 Drafter 扩容》《DDTree：Diffusion Draft Tree 与树验证》《DSpark：置信度调度与负载感知验证》《Speculator 工程化：训练、评测、发布与漂移》。实现时允许复用已有模块，但必须重新验证跨模块接口、身份、截止时间、错误传播和观测字段。

## 3. 系统边界与架构

### 组件 1：工作负载加载器

工作负载加载器负责处理已绑定任务和版本的输入，将可验证状态交给普通自回归基线。组件对外提供配置摘要、开始结束事件、指标及失败原因，身份信息始终经过接口传播。

### 组件 2：普通自回归基线

普通自回归基线与 Speculator 适配器之间使用结构化合同。任务 ID、模型或策略版本随输入传入，输出附带配置摘要、时间、指标和错误，使隔离、回放和追踪拥有同一身份链。

### 组件 3：Speculator 适配器

Speculator 适配器接收带版本和任务身份的输入，并向验证与接受统计输出结构化状态。接口记录配置摘要、起止时间、核心指标与失败原因。客户身份和模型修订通过显式字段传递，便于故障回放和租户隔离。

### 组件 4：验证与接受统计

在这套架构中，验证与接受统计维护清晰的能力边界。输入携带任务及版本，输出由 Pareto 分析器直接消费；运行记录包含配置、时间、指标和错误。租户与模型身份不放入不可见的全局状态。

### 组件 5：Pareto 分析器

Pareto 分析器负责处理已绑定任务和版本的输入，将可验证状态交给报告导出器。组件对外提供配置摘要、开始结束事件、指标及失败原因，身份信息始终经过接口传播。

### 组件 6：报告导出器

报告导出器与工作负载加载器之间使用结构化合同。任务 ID、模型或策略版本随输入传入，输出附带配置摘要、时间、指标和错误，使隔离、回放和追踪拥有同一身份链。

## 4. 目录映射

可执行文件为 `project/01-speculator-benchmark/run.py`。所需的 HTTP、CUDA、统计、报告或状态机原语已经合并到这一入口。下方代码展示入口中内嵌的可读核心实现；下载包不再单独提供内部源码库目录。默认运行 Fixture，加 `--real` 才进入实测路径。

**内嵌核心实现 → project/01-speculator-benchmark/run.py**

```python
"""Project 01 — attributed, paired Speculator A/B benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from phase3lab.shared.evidence import assert_no_unattributed_comparison, require_distinct_endpoints, summarize_records
from phase3lab.shared.http_client import RequestRecord, completion, discover_models, metrics_evidence
from phase3lab.shared.runner import LabSpec, PreconditionError, run_cli
from phase3lab.shared.stats import paired_delta
from phase3lab.shared.workload import load_jsonl

SPEC = LabSpec(
    lab_id="project-01-speculator-benchmark",
    title="Project 01：Next-Generation Speculator Benchmark",
    goal="用同一工作负载成对比较禁用与启用 Speculator 的独立端点，并校验输出等价和部署归因。",
    real_evidence=("workload SHA-256", "artifact/deployment evidence", "paired endpoint records", "metrics snapshots"),
    required_inputs=("baseline endpoint", "candidate endpoint", "workload JSONL", "artifact manifest", "deployment evidence"),
    outputs=("pair table", "correctness gate", "latency delta", "evidence manifest"),
    acceptance=("every request reaches both endpoints", "target/sampling/workload identities match", "candidate output equals baseline", "deployment evidence binds candidate to artifact"),
)

def add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workload", default="data/project01_workload.jsonl")
    parser.add_argument("--speculator-manifest", default="data/speculator_manifest.example.json")
    parser.add_argument("--deployment-evidence", default="")
    parser.add_argument("--max-p95-ratio", type=float, default=1.0)

def load_json(path: str, label: str) -> tuple[dict, bytes]:
    target = Path(path)
    if not target.is_file():
        raise PreconditionError(f"{label} file does not exist: {target}")
    raw = target.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value, raw

def validate_binding(manifest: dict, manifest_raw: bytes, deployment: dict, candidate_url: str) -> dict:
    manifest_required = {"artifact_id", "artifact_sha256", "target_model", "drafter_model", "revision"}
    deployment_required = {"endpoint", "manifest_sha256", "target_model", "launch_command_sha256"}
    for label, value, required in (("manifest", manifest, manifest_required), ("deployment evidence", deployment, deployment_required)):
        missing = sorted(required - value.keys())
        if missing:
            raise ValueError(f"{label} is missing: {', '.join(missing)}")
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    if deployment["endpoint"].rstrip("/") != candidate_url.rstrip("/"):
        raise ValueError("deployment evidence endpoint does not match candidate URL")
    if deployment["manifest_sha256"] != manifest_sha:
        raise ValueError("deployment evidence does not bind the supplied manifest")
    if deployment["target_model"] != manifest["target_model"]:
        raise ValueError("deployment and artifact target models differ")
    sha_pattern = re.compile(r"[0-9a-f]{64}")
    for field in ("artifact_sha256",):
        if not sha_pattern.fullmatch(str(manifest[field])) or set(str(manifest[field])) == {"0"}:
            raise ValueError(f"manifest {field} is not a non-placeholder SHA-256")
    launch_sha = str(deployment["launch_command_sha256"])
    if not sha_pattern.fullmatch(launch_sha) or set(launch_sha) == {"0"}:
        raise ValueError("launch_command_sha256 is not a non-placeholder SHA-256")
    return {"manifest_sha256": manifest_sha, "artifact_id": manifest["artifact_id"], "artifact_sha256": manifest["artifact_sha256"], "launch_command_sha256": deployment["launch_command_sha256"]}

def fixture(args: argparse.Namespace) -> dict:
    baseline = [100.0, 110.0, 105.0, 108.0]
    candidate = [82.0, 91.0, 88.0, 90.0]
    outputs = ["a", "b", "c", "d"]
    ratio = sorted(candidate)[-1] / sorted(baseline)[-1]
    return {
        "pairs": [{"pair_id": index, "baseline_output": value, "candidate_output": value} for index, value in enumerate(outputs)],
        "paired_delta": paired_delta(baseline, candidate),
        "gate": {"output_equivalence": True, "candidate_p95_ratio": round(ratio, 6), "passed": ratio <= args.max_p95_ratio},
        "binding": {"validated": True},
    }

def real(args: argparse.Namespace) -> dict:
    if len(args.base_url) != 2:
        raise PreconditionError("provide --base-url BASELINE then --base-url SPECULATOR")
    require_distinct_endpoints(args.base_url)
    workload_path = Path(args.workload)
    workload_raw = workload_path.read_bytes() if workload_path.is_file() else b""
    workload = load_jsonl(workload_path)
    manifest, manifest_raw = load_json(args.speculator_manifest, "Speculator manifest")
    deployment, _ = load_json(args.deployment_evidence, "deployment evidence")
    binding = validate_binding(manifest, manifest_raw, deployment, args.base_url[1])
    model_lists = [discover_models(url) for url in args.base_url]
    model = manifest["target_model"] if args.model == "auto" else args.model
    if model != manifest["target_model"] or any(model not in values for values in model_lists):
        raise PreconditionError("the manifest Target model must be served by both endpoints")
    workload_sha = hashlib.sha256(workload_raw).hexdigest()
    attribution = [
        {"endpoint": args.base_url[0], "model": model, "sampling": {"temperature": 0}, "workload_sha256": workload_sha},
        {"endpoint": args.base_url[1], "model": model, "sampling": {"temperature": 0}, "workload_sha256": workload_sha},
    ]
    assert_no_unattributed_comparison(attribution[0], attribution[1])
    evidence_urls = args.evidence_url or args.base_url
    if len(evidence_urls) != 2:
        raise ValueError("provide zero or exactly two --evidence-url values")
    metrics_before = [metrics_evidence(url) for url in evidence_urls]
    role_records: dict[str, list[RequestRecord]] = {"baseline": [], "candidate": []}
    pairs = []
    for index, item in enumerate(workload):
        order = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
        current = {}
        for role in order:
            endpoint = args.base_url[0 if role == "baseline" else 1]
            record = completion(endpoint, model, item.prompt, item.max_new_tokens, request_id=f"{item.request_id}-{role}")
            role_records[role].append(record)
            current[role] = record
        pairs.append({
            "pair_id": item.request_id,
            "kind": item.kind,
            "first": order[0],
            "outputs_equal": current["baseline"].text_sha256 == current["candidate"].text_sha256 and current["baseline"].ok and current["candidate"].ok,
            "baseline": current["baseline"].json(),
            "candidate": current["candidate"].json(),
        })
    metrics_after = [metrics_evidence(url) for url in evidence_urls]
    baseline_ok = [record for record in role_records["baseline"] if record.ok]
    candidate_ok = [record for record in role_records["candidate"] if record.ok]
    if not baseline_ok or not candidate_ok:
        raise RuntimeError("both endpoints need successful request evidence")
    baseline_p95 = summarize_records(role_records["baseline"])["latency"]["p95_ms"]
    candidate_p95 = summarize_records(role_records["candidate"])["latency"]["p95_ms"]
    p95_ratio = candidate_p95 / max(baseline_p95, 1e-9)
    output_equivalence = all(pair["outputs_equal"] for pair in pairs)
    all_success = len(baseline_ok) == len(workload) and len(candidate_ok) == len(workload)
    gate_result = {"all_requests_succeeded": all_success, "output_equivalence": output_equivalence, "candidate_p95_ratio": round(p95_ratio, 6), "max_p95_ratio": args.max_p95_ratio}
    gate_result["passed"] = all_success and output_equivalence and p95_ratio <= args.max_p95_ratio
    return {
        "binding": binding,
        "attribution": attribution,
        "model_lists": model_lists,
        "metrics_before": metrics_before,
        "metrics_after": metrics_after,
        "baseline": summarize_records(role_records["baseline"]),
        "candidate": summarize_records(role_records["candidate"]),
        "paired_delta": paired_delta([record.latency_ms for record in role_records["baseline"]], [record.latency_ms for record in role_records["candidate"]]),
        "pairs": pairs,
        "gate": gate_result,
    }

def main() -> None:
    run_cli(SPEC, add_arguments, real, fixture)

if __name__ == "__main__":
    main()
```

## 5. 配置与输入合同

每次运行读取显式配置并生成不可歧义的运行身份。输入必须说明随机种子、工作负载、模型或代理模型、并发、截止时间、硬件模式和输出目录。配置校验拒绝负容量、非法概率、不存在的文件和互相冲突的开关。敏感凭证只从运行环境读取，不写入配置、报告或日志。

## 6. 机制模拟

模拟路径在 CPU 上连接工作负载加载器、普通自回归基线、Speculator 适配器、验证与接受统计、Pareto 分析器、报告导出器，用离散事件或确定性状态机验证控制逻辑。模拟重点是因果方向、状态转换、容量边界和反例，不声称复刻真实 GPU 速度。输出记录 `fixture` 来源、工作负载、事件时间线、指标、故障和限制。

```bash
python project/01-speculator-benchmark/run.py
```

模拟验收至少运行基线、候选和过载三组场景。关闭候选后应回到基线；提高负载到容量以上时必须出现排队、拒绝或服务等级失守；非法状态转换和无效输入必须被拒绝。固定随机种子后，结构化报告应可重复生成。

## 7. 真实本地路径

真实工作流直接执行“用同一工作负载成对比较禁用与启用 Speculator 的独立端点，并校验输出等价和部署归因。”。运行输入为 `baseline endpoint`、`candidate endpoint`、`workload JSONL`、`artifact manifest`、`deployment evidence`；报告必须保留 `workload SHA-256`、`artifact/deployment evidence`、`paired endpoint records`、`metrics snapshots`。只有 `source=measured` 可以支撑性能或发布结论，`source=fixture` 只验证控制逻辑。

```bash
python project/01-speculator-benchmark/run.py --check-only

python project/01-speculator-benchmark/run.py --real --base-url http://127.0.0.1:8000 --base-url http://127.0.0.1:8001 --speculator-manifest data/speculator_manifest.json --deployment-evidence data/speculator_deployment_evidence.json
```

缺少 `baseline endpoint`、`candidate endpoint`、`workload JSONL`、`artifact manifest`、`deployment evidence` 中任一真实前提时，脚本写入 `status=precondition_failed` 并以退出码 2 结束。真实路径没有 CPU fallback；性能报告只接受本次运行的 `source=measured` 记录。

## 8. 工作负载与指标

### 指标 1：correctness

评审 correctness 时使用《新一代 Speculator Benchmark》当前运行的原始数据。定义、单位、采集点、时间范围和分母全部随报告提供；任何以错误率、服务等级或恢复退化换来的改善都被门禁拦截。

### 指标 2：latency

《新一代 Speculator Benchmark》把 latency 作为一项可重算指标，而非单独结论。报告保存原始事件、口径、单位、分母与时间窗口，并同步检查输出正确性、服务等级和故障恢复。

### 指标 3：throughput

throughput 随《新一代 Speculator Benchmark》的原始事件保存，并注明定义、单位、采集点、时间窗口和分母。验收器可以重新计算聚合值；候选若以正确性、服务等级或恢复能力为代价，即使 throughput 改善也不通过。

### 指标 4：reliability

项目为 reliability 记录计算口径、单位、分母、采集位置和窗口。报告中的聚合值能够从《新一代 Speculator Benchmark》事件重算，并与正确性、SLO 及故障恢复一同验收。

### 指标 5：cost_efficiency

评审 cost_efficiency 时使用《新一代 Speculator Benchmark》当前运行的原始数据。定义、单位、采集点、时间范围和分母全部随报告提供；任何以错误率、服务等级或恢复退化换来的改善都被门禁拦截。

## 9. 故障注入与诊断

### 故障 1：Drafter 与 Target 修订错配

在《新一代 Speculator Benchmark》中注入“Drafter 与 Target 修订错配”后，观察故障发现、隔离、降级、回退与恢复导流。证据链从任务身份和制品版本开始，经过配置、负载与组件事件，最后确认资源和在途工作回到稳定状态。

### 故障 2：采样配置不一致

本场景复现“采样配置不一致”。验收器检查发现时间、隔离范围、降级结果、回滚目标与恢复节奏，并用任务、制品、配置和负载定位根因。只有缓存、队列、资源及在途任务稳定后才算恢复完成。

### 故障 3：高并发下验证容量被耗尽

主动制造“高并发下验证容量被耗尽”，记录检测、隔离、降级、回滚和渐进恢复。排查时核对《新一代 Speculator Benchmark》任务身份、制品摘要、配置及负载，再沿组件事件定位故障。重新导流前确认在途任务、缓存、队列与资源稳定。

### 故障 4：短输出无法摊销启动成本

“短输出无法摊销启动成本”由故障注入器稳定复现。系统需要给出告警、影响隔离、可解释降级和回滚事件；诊断依据任务 ID、制品摘要、配置、工作负载与组件时间线。进程恢复后仍要检查队列、缓存和在途任务。

## 10. 验收阈值

- 所有策略使用同一请求集和采样合同。
- 错误与跳过状态可解释。
- Pareto 点能够从原始记录重新计算。
- 禁用候选后恢复基线。
- 指标可复现。
- 故障注入产生预期告警或降级。

## 11. 演示方法

先运行 `--check-only`，再执行 Fixture、真实路径、失败注入与报告验收。演示时明确区分 `source=fixture`、`source=measured` 和 `status=precondition_failed`；前提失败不能写成性能通过。

```bash
python project/01-speculator-benchmark/run.py
python project/01-speculator-benchmark/run.py --check-only
```

## 12. 交付物

- 源代码。
- 配置。
- 实验报告。
- 架构说明。
- 验收结果。

## 13. 项目小结

完成《新一代 Speculator Benchmark》后，应能从接口和状态追到指标与恢复动作。最终演示说明当前架构为何成立、收益如何复验、哪些结果无效，以及故障后怎样回到稳定路径。

## 写在最后

有了统一的 Speculator 评测口径，下一步需要一个能生成真实新型负载的基准平台。下一篇：[新型推理工作负载基准平台](/source/AI-Infra/3-大模型推理优化工程/32-新型推理工作负载基准平台)。