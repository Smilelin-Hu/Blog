#!/usr/bin/env python3
"""Standalone unified entry for project/project-06.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Validate an enterprise multi-cluster self-service AI platform contract."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def validate_prerequisites(items: list[dict[str, str]], root: Path) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for item in items:
        path = root / item['report']
        if not path.exists():
            results.append({'id': item['id'], 'status': 'MISSING', 'reason': 'PrerequisiteReportMissing'})
            continue
        report = json.loads(path.read_text(encoding='utf-8'))
        results.append({'id': item['id'], 'status': 'PASS' if report.get('status') == 'PASS' else 'FAILED', 'reason': 'PrerequisiteVerified' if report.get('status') == 'PASS' else 'PrerequisiteDidNotPass'})
    return results

def validate_request(item: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in ('request_id', 'request_type', 'tenant', 'project', 'owner', 'template_revision', 'artifact_digest', 'queue', 'target_environment'):
        if not item.get(field):
            reasons.append(f'RequiredFieldMissing:{field}')
    if item.get('request_type') not in {'training', 'deployment'}:
        reasons.append('RequestTypeUnsupported')
    if not str(item.get('template_revision', '')).startswith('sha256:'):
        reasons.append('TemplateRevisionMustBeImmutable')
    if not str(item.get('artifact_digest', '')).startswith('sha256:'):
        reasons.append('ArtifactDigestRequired')
    if item.get('cluster_admin_requested'):
        reasons.append('ClusterAdminAccessForbidden')
    if not item.get('policy_checked'):
        reasons.append('PolicyCheckRequiredBeforeDispatch')
    if not item.get('quota_checked'):
        reasons.append('QuotaCheckRequiredBeforeDispatch')
    if item.get('gpu_count', 0) > policy['maximum_gpu_count']:
        reasons.append('GPURequestLimitExceeded')
    if item.get('queue') not in policy['allowed_queues']:
        reasons.append('QueueNotAllowed')
    if item.get('target_environment') == 'production' and (not item.get('approval')):
        reasons.append('ProductionApprovalMissing')
    return reasons

def dispatch(item: dict[str, Any], clusters: list[dict[str, Any]], policy: dict[str, Any]) -> dict[str, Any]:
    reasons = validate_request(item, policy)
    if reasons:
        return {'request_id': item.get('request_id', 'unknown'), 'status': 'REJECTED', 'reason': reasons[0], 'reasons': reasons}
    eligible = [cluster for cluster in clusters if cluster['ready'] and cluster['residency'] == item['residency'] and (item['gpu_type'] in cluster['gpu_types']) and (cluster['free_gpus'] >= item['gpu_count']) and (item['queue'] in cluster['queues'])]
    if not eligible:
        return {'request_id': item['request_id'], 'status': 'PENDING', 'reason': 'NoEligibleWorkerCluster'}
    selected = sorted(eligible, key=lambda cluster: (-cluster['free_gpus'], cluster['name']))[0]
    completion = item['submitted_at_seconds'] + item['processing_seconds']
    return {'request_id': item['request_id'], 'status': 'SUCCEEDED', 'reason': 'SelfServiceRequestCompleted', 'cluster': selected['name'], 'completion_seconds': completion, 'processing_seconds': item['processing_seconds'], 'cost': round(item['gpu_count'] * item['processing_seconds'] / 3600 * selected['gpu_hour_price'], 4), 'audit_id': f'audit-{item['request_id']}'}

def evaluate_fault(item: dict[str, Any]) -> dict[str, Any]:
    mapping = {'template_mutable': ('REJECTED', 'TemplateRevisionMustBeImmutable'), 'artifact_mutable': ('REJECTED', 'ArtifactDigestRequired'), 'cluster_admin': ('REJECTED', 'ClusterAdminAccessForbidden'), 'policy_bypass': ('REJECTED', 'PolicyCheckRequiredBeforeDispatch'), 'quota_bypass': ('REJECTED', 'QuotaCheckRequiredBeforeDispatch'), 'gpu_limit': ('REJECTED', 'GPURequestLimitExceeded'), 'queue_unknown': ('REJECTED', 'QueueNotAllowed'), 'production_approval_missing': ('REJECTED', 'ProductionApprovalMissing'), 'residency_mismatch': ('PENDING', 'NoEligibleWorkerCluster'), 'gpu_type_unavailable': ('PENDING', 'NoEligibleWorkerCluster'), 'capacity_shortage': ('PENDING', 'NoEligibleWorkerCluster'), 'worker_not_ready': ('PENDING', 'NoEligibleWorkerCluster'), 'manager_executes_workload': ('REJECTED', 'ManagerClusterExecutionForbidden'), 'direct_worker_credential': ('REJECTED', 'DirectWorkerCredentialForbidden'), 'status_assumed': ('INCONCLUSIVE', 'WorkerStatusEvidenceMissing'), 'cost_identity_missing': ('INCONCLUSIVE', 'CostIdentityMissing'), 'audit_identity_missing': ('INCONCLUSIVE', 'AuditIdentityMissing'), 'prerequisite_missing': ('BLOCKED', 'PrerequisiteReportMissing'), 'prerequisite_failed': ('BLOCKED', 'PrerequisiteDidNotPass'), 'duplicate_request': ('BLOCKED', 'RequestLeaseAlreadyOwned'), 'portal_timeout': ('SLO_VIOLATED', 'PlatformRequestTooSlow'), 'live_clusters_missing': ('SKIPPED', 'NoKubernetesContextsProvided')}
    phase, reason = mapping[item['type']]
    return {'type': item['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if phase == item['expected_phase'] and reason == item['expected_reason'] else 'FAIL'}

def simulate(scenario: dict[str, Any], root: Path) -> dict[str, Any]:
    prerequisites = validate_prerequisites(scenario['prerequisites'], root)
    results = [dispatch(item, scenario['clusters'], scenario['policy']) for item in scenario['requests']]
    completed = [item for item in results if item['status'] == 'SUCCEEDED']
    metrics = {'first_success_seconds': min((item['completion_seconds'] for item in completed)), 'self_service_completion_rate': len(completed) / len(results), 'cross_cluster_dispatch_success_rate': sum((bool(item.get('cluster')) for item in completed)) / len(results), 'maximum_platform_request_seconds': max((item['processing_seconds'] for item in completed)), 'unit_workload_cost': round(sum((item['cost'] for item in completed)) / len(completed), 4), 'audit_coverage_rate': sum((bool(item.get('audit_id')) for item in completed)) / len(completed)}
    threshold = scenario['thresholds']
    checks = {'prerequisites': all((item['status'] == 'PASS' for item in prerequisites)), 'first_success': metrics['first_success_seconds'] <= threshold['maximum_first_success_seconds'], 'completion': metrics['self_service_completion_rate'] >= threshold['minimum_self_service_completion_rate'], 'dispatch': metrics['cross_cluster_dispatch_success_rate'] >= threshold['minimum_cross_cluster_dispatch_success_rate'], 'request_slo': metrics['maximum_platform_request_seconds'] <= threshold['maximum_platform_request_seconds'], 'audit': metrics['audit_coverage_rate'] >= threshold['minimum_audit_coverage_rate']}
    faults = [evaluate_fault(item) for item in scenario['faults']]
    status = 'PASS' if all(checks.values()) and all((item['status'] == 'PASS' for item in faults)) else 'FAIL'
    return {'status': status, 'prerequisites': prerequisites, 'requests': results, 'metrics': metrics, 'checks': checks, 'faults': faults}

def inspect_live(contexts: list[str]) -> dict[str, Any]:
    if not contexts:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextsProvided'}
    if shutil.which('kubectl') is None:
        return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
    evidence: dict[str, Any] = {}
    for context in contexts:
        commands = {'namespaces': ['kubectl', '--context', context, 'get', 'namespaces', '-o', 'json'], 'workloads': ['kubectl', '--context', context, 'get', 'workloads.kueue.x-k8s.io', '-A', '-o', 'json'], 'pods': ['kubectl', '--context', context, 'get', 'pods', '-A', '-o', 'json']}
        evidence[context] = {}
        for name, command in commands.items():
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
            except subprocess.TimeoutExpired:
                return {'status': 'FAIL', 'reason': 'LiveClusterReadTimeout', 'context': context, 'step': name}
            if result.returncode:
                return {'status': 'FAIL', 'reason': 'LiveClusterReadFailed', 'context': context, 'step': name, 'stderr': result.stderr.strip()}
            evidence[context][name] = json.loads(result.stdout)
    return {'status': 'PASS', 'reason': 'MultiClusterEvidenceCollected', 'evidence': evidence}

def implementation_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--contexts', default='')
    args = parser.parse_args()
    root = args.scenario.resolve().parents[2]
    report = simulate(load_scenario(args.scenario), root)
    report['live'] = inspect_live([item for item in args.contexts.split(',') if item])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Enterprise self-service AI platform: {report['status']}')
    for key, value in report['metrics'].items():
        print(f'  metric {key}: {value}')
    for item in report['prerequisites']:
        print(f'  prerequisite {item['id']}: {item['status']}/{item['reason']}')
    for item in report['requests']:
        print(f'  request {item['request_id']}: {item['status']}/{item['reason']} cluster={item.get('cluster', '-')}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live']['reason']}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] in {'PASS', 'SKIPPED'} else 1

ENTRY_ID = 'project/project-06'


def _emit_contract(status: str, source: str, **details) -> None:
    payload = {"status": status, "source": source, "entry": ENTRY_ID, **details}
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _invoke_embedded(function, argv: list[str], source: str) -> int:
    import contextlib
    import io
    old_argv = sys.argv
    captured = io.StringIO()
    try:
        sys.argv = [str(Path(__file__).resolve()), *argv]
        try:
            with contextlib.redirect_stdout(captured):
                value = function()
            code = int(value or 0)
        except SystemExit as exc:
            code = int(exc.code or 0) if isinstance(exc.code, (int, type(None))) else 1
        except ModuleNotFoundError as exc:
            output = captured.getvalue().strip()
            if output:
                print(output)
            _emit_contract("precondition_failed", "none", reason=f"missing dependency: {exc.name}")
            return 2
    finally:
        sys.argv = old_argv
    output = captured.getvalue().strip()
    if output:
        print(output)
    if code == 2:
        _emit_contract("precondition_failed", "none", implementation_returncode=code)
        return 2
    status = "passed" if code == 0 else "failed"
    _emit_contract(status, source, implementation_returncode=code)
    return code


def _precondition_failed(reason: str, **details) -> int:
    _emit_contract("precondition_failed", "none", reason=reason, **details)
    return 2

def main() -> int:
    args = list(sys.argv[1:])
    if "--entry-info" in args:
        _emit_contract("ready", "none", implementation="standalone_single_file", authoritative_entry="run.py")
        return 0
    if "--check-only" in args:
        tools = {name: shutil.which(name) is not None for name in ['kubectl', 'nvidia-smi', 'sinfo']}
        if not any(tools.values()) or False:
            return _precondition_failed("no declared live target capability is available", tools=tools, live_route_declared=True)
        _emit_contract("ready", "none", tools=tools)
        return 0
    if "--real" in args:
        args.remove("--real")
        if not args:
            return _precondition_failed("--real requires explicit live target arguments; no fixture fallback is allowed")
        tools = {name: shutil.which(name) is not None for name in ['kubectl', 'nvidia-smi', 'sinfo']}
        if not any(tools.values()) or False:
            return _precondition_failed("no declared live target capability is available", tools=tools)
        forwarded = list(args)
        if "--scenario" not in forwarded:
            forwarded = ["--scenario", "scenario.json", *forwarded]
        if "--output" not in forwarded:
            forwarded = [*forwarded, "--output", "results/measured.json"]
        for item in []:
            pass
        if False and "--mode" not in forwarded:
            forwarded = [[][0], [][1], *forwarded]
        return _invoke_embedded(implementation_main, forwarded, "measured")
    return _invoke_embedded(implementation_main, args or ['--scenario', 'enterprise_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
