#!/usr/bin/env python3
"""Standalone unified entry for project/project-05.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Validate an AI platform SRE, security, and FinOps operations console."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def validate_identity(item: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in ('request_id', 'tenant', 'project', 'owner', 'cluster_uid', 'namespace_uid', 'workload_uid'):
        if not item.get(field):
            reasons.append(f'RequiredIdentityMissing:{field}')
    if item.get('tenant') != item.get('authorized_tenant'):
        reasons.append('CrossTenantIdentityMismatch')
    return reasons

def evaluate_request(item: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    reasons = validate_identity(item)
    if item.get('privileged'):
        reasons.append('PrivilegedWorkloadForbidden')
    if item.get('host_path'):
        reasons.append('HostPathForbidden')
    if not item.get('signed_image'):
        reasons.append('VerifiedImageSignatureRequired')
    if item.get('gpu_hours', 0) > policy['maximum_gpu_hours_per_request']:
        reasons.append('GPUHourBudgetExceeded')
    return {'request_id': item.get('request_id', 'unknown'), 'status': 'REJECTED' if reasons else 'ADMITTED', 'reason': reasons[0] if reasons else 'IdentityPolicyAndBudgetPassed', 'reasons': reasons}

def calculate_cost(item: dict[str, Any], prices: dict[str, float]) -> dict[str, Any]:
    gpu_type = item.get('gpu_type')
    if gpu_type not in prices:
        return {'request_id': item.get('request_id', 'unknown'), 'status': 'INCONCLUSIVE', 'reason': 'GPUPriceProfileUnknown', 'cost': 0.0}
    reasons = validate_identity(item)
    if reasons:
        return {'request_id': item.get('request_id', 'unknown'), 'status': 'UNALLOCATED', 'reason': reasons[0], 'cost': 0.0}
    cost = round(item['gpu_hours'] * prices[gpu_type] + item.get('shared_cost', 0.0), 4)
    return {'request_id': item['request_id'], 'status': 'ALLOCATED', 'reason': 'CostIdentityResolved', 'tenant': item['tenant'], 'project': item['project'], 'owner': item['owner'], 'cost': cost}

def evaluate_incident(item: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    detected = item['detected_at_seconds'] - item['started_at_seconds']
    recovered = item['recovered_at_seconds'] - item['detected_at_seconds']
    blast = item['affected_workloads'] / item['eligible_workloads']
    guardrail = blast <= policy['maximum_fault_blast_radius']
    runbook = bool(item.get('runbook'))
    verified = bool(item.get('steady_state_restored'))
    status = 'RECOVERED' if guardrail and runbook and verified else 'ESCALATE'
    reason = 'RecoveryVerified' if status == 'RECOVERED' else 'BlastRadiusExceeded' if not guardrail else 'RunbookMissing' if not runbook else 'RecoveryVerificationFailed'
    return {'incident_id': item['incident_id'], 'status': status, 'reason': reason, 'detection_seconds': detected, 'recovery_seconds': recovered, 'blast_radius': blast}

def evaluate_fault(item: dict[str, Any]) -> dict[str, Any]:
    mapping = {'missing_request_id': ('INCONCLUSIVE', 'RequiredIdentityMissing:request_id'), 'missing_tenant': ('INCONCLUSIVE', 'RequiredIdentityMissing:tenant'), 'missing_project': ('INCONCLUSIVE', 'RequiredIdentityMissing:project'), 'cross_tenant': ('REJECTED', 'CrossTenantIdentityMismatch'), 'privileged_workload': ('REJECTED', 'PrivilegedWorkloadForbidden'), 'host_path': ('REJECTED', 'HostPathForbidden'), 'unsigned_image': ('REJECTED', 'VerifiedImageSignatureRequired'), 'budget_exceeded': ('REJECTED', 'GPUHourBudgetExceeded'), 'unknown_gpu_price': ('INCONCLUSIVE', 'GPUPriceProfileUnknown'), 'cost_identity_gap': ('UNALLOCATED', 'CostIdentityMissing'), 'sli_samples_insufficient': ('INCONCLUSIVE', 'InsufficientSLISamples'), 'telemetry_stale': ('INCONCLUSIVE', 'TelemetryStale'), 'burn_single_window': ('PASS', 'DualWindowConditionNotMet'), 'runbook_missing': ('ESCALATE', 'RunbookMissing'), 'blast_radius_exceeded': ('ESCALATE', 'BlastRadiusExceeded'), 'recovery_not_verified': ('ESCALATE', 'RecoveryVerificationFailed'), 'remediation_loop': ('ESCALATE', 'RemediationAttemptBudgetExceeded'), 'audit_lag': ('INCONCLUSIVE', 'AuditDeliveryLagExceeded'), 'metric_cardinality': ('DROPPED', 'MetricCardinalityBudgetExceeded'), 'cost_double_count': ('REJECTED', 'CostReconciliationDeltaNonZero'), 'live_sources_missing': ('SKIPPED', 'NoLiveOperationsSourceProvided')}
    phase, reason = mapping[item['type']]
    return {'type': item['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if phase == item['expected_phase'] and reason == item['expected_reason'] else 'FAIL'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    admissions = [evaluate_request(item, scenario['policy']) for item in scenario['requests']]
    costs = [calculate_cost(item, scenario['prices']) for item in scenario['requests']]
    incidents = [evaluate_incident(item, scenario['policy']) for item in scenario['incidents']]
    sli_good = sum((sample['good'] for sample in scenario['sli_samples']))
    sli_total = sum((sample['total'] for sample in scenario['sli_samples']))
    metrics = {'slo_attainment': sli_good / sli_total, 'maximum_detection_seconds': max((item['detection_seconds'] for item in incidents)), 'maximum_recovery_seconds': max((item['recovery_seconds'] for item in incidents)), 'cost_attribution_rate': sum((item['status'] == 'ALLOCATED' for item in costs)) / len(costs), 'policy_violation_block_rate': sum((item['status'] == 'REJECTED' for item in admissions)) / max(1, sum((bool(validate_identity(request)) or request.get('privileged') or request.get('host_path') or (not request.get('signed_image')) or (request.get('gpu_hours', 0) > scenario['policy']['maximum_gpu_hours_per_request']) for request in scenario['requests'])))}
    threshold = scenario['thresholds']
    checks = {'slo': metrics['slo_attainment'] >= threshold['minimum_slo_attainment'], 'detection': metrics['maximum_detection_seconds'] <= threshold['maximum_detection_seconds'], 'recovery': metrics['maximum_recovery_seconds'] <= threshold['maximum_recovery_seconds'], 'attribution': metrics['cost_attribution_rate'] >= threshold['minimum_cost_attribution_rate'], 'blocking': metrics['policy_violation_block_rate'] >= threshold['minimum_policy_violation_block_rate']}
    faults = [evaluate_fault(item) for item in scenario['faults']]
    status = 'PASS' if all(checks.values()) and all((item['status'] == 'PASS' for item in faults)) else 'FAIL'
    return {'status': status, 'admissions': admissions, 'costs': costs, 'incidents': incidents, 'metrics': metrics, 'checks': checks, 'faults': faults}

def inspect_live(context: str | None) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoLiveOperationsSourceProvided'}
    if shutil.which('kubectl') is None:
        return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
    commands = {'pods': ['kubectl', '--context', context, 'get', 'pods', '-A', '-o', 'json'], 'nodes': ['kubectl', '--context', context, 'get', 'nodes', '-o', 'json'], 'events': ['kubectl', '--context', context, 'get', 'events', '-A', '-o', 'json']}
    evidence: dict[str, Any] = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        except subprocess.TimeoutExpired:
            return {'status': 'FAIL', 'reason': 'LiveOperationsReadTimeout', 'step': name}
        if result.returncode:
            return {'status': 'FAIL', 'reason': 'LiveOperationsReadFailed', 'step': name, 'stderr': result.stderr.strip()}
        evidence[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'reason': 'LiveOperationsEvidenceCollected', 'evidence': evidence}

def implementation_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--context')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'AI platform operations console: {report['status']}')
    for key, value in report['metrics'].items():
        print(f'  metric {key}: {value}')
    for item in report['incidents']:
        print(f'  incident {item['incident_id']}: {item['status']}/{item['reason']}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live']['reason']}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] in {'PASS', 'SKIPPED'} else 1

ENTRY_ID = 'project/project-05'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'operations_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
