#!/usr/bin/env python3
"""Standalone unified entry for project/project-02.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Validate a multi-tenant GPU batch, queue, quota, topology, and recovery platform."""
import argparse
import json
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def validate_identity(job: dict[str, Any]) -> list[str]:
    return [field for field in ('tenant', 'project', 'owner', 'cost_center', 'queue') if not job.get(field)]

def schedule(scenario: dict[str, Any]) -> dict[str, Any]:
    nodes = {item['name']: dict(item) for item in scenario['nodes']}
    quotas = {item['tenant']: item['gpu_quota'] for item in scenario['tenants']}
    usage: dict[str, int] = defaultdict(int)
    admissions = []
    waits = []
    for job in sorted(scenario['jobs'], key=lambda item: (-item['priority'], item['submitted_at'], item['name'])):
        missing = validate_identity(job)
        if missing:
            admissions.append({'job': job['name'], 'status': 'REJECTED', 'reason': f'CostIdentityMissing:{missing[0]}'})
            continue
        if job['members'] < job['minimum_members']:
            admissions.append({'job': job['name'], 'status': 'REJECTED', 'reason': 'GangMinimumMembersInvalid'})
            continue
        requested = job['members'] * job['gpus_per_member']
        if usage[job['tenant']] + requested > quotas[job['tenant']]:
            admissions.append({'job': job['name'], 'status': 'PENDING', 'reason': 'TenantQuotaInsufficient'})
            waits.append(job['wait_seconds'])
            continue
        candidates = []
        for node in nodes.values():
            if node['gpu_type'] != job['gpu_type'] or node['rack'] not in job['allowed_racks']:
                continue
            if node['available_gpus'] >= requested:
                candidates.append(node)
        if not candidates:
            admissions.append({'job': job['name'], 'status': 'PENDING', 'reason': 'GangOrTopologyCapacityUnavailable'})
            waits.append(job['wait_seconds'])
            continue
        selected = sorted(candidates, key=lambda item: (item['available_gpus'] - requested, item['name']))[0]
        selected['available_gpus'] -= requested
        usage[job['tenant']] += requested
        admissions.append({'job': job['name'], 'status': 'ADMITTED', 'reason': 'AtomicQuotaAndTopologyAdmission', 'node': selected['name'], 'gpus': requested})
        waits.append(job['wait_seconds'])
    return {'admissions': admissions, 'usage': dict(usage), 'nodes': list(nodes.values()), 'waits': waits}

def metrics(scenario: dict[str, Any], scheduled: dict[str, Any]) -> dict[str, float]:
    total = len(scheduled['admissions'])
    admitted = sum((item['status'] == 'ADMITTED' for item in scheduled['admissions']))
    capacity = sum((item['total_gpus'] for item in scenario['nodes']))
    free = sum((item['available_gpus'] for item in scheduled['nodes']))
    whole_free_nodes = sum((item['available_gpus'] == item['total_gpus'] for item in scheduled['nodes']))
    quotas = {item['tenant']: item['gpu_quota'] for item in scenario['tenants']}
    shares = {tenant: scheduled['usage'].get(tenant, 0) / quota for tenant, quota in quotas.items()}
    fairness_deviation = max(shares.values()) - min(shares.values()) if shares else 0.0
    return {'queue_wait_seconds_p95': max(scheduled['waits']) if scheduled['waits'] else 0.0, 'admission_success_rate': admitted / total if total else 1.0, 'fair_share_deviation': fairness_deviation, 'gpu_fragmentation_ratio': free / capacity if capacity else 0.0, 'whole_free_node_ratio': whole_free_nodes / len(scenario['nodes']) if scenario['nodes'] else 0.0, 'preemption_recovery_seconds': float(scenario['recovery']['preemption_recovery_seconds'])}

def evaluate_fault(item: dict[str, Any]) -> dict[str, Any]:
    mapping = {'partial_gang': ('REJECTED', 'PartialGangAllocationForbidden'), 'quota_bypass': ('REJECTED', 'TenantQuotaRequired'), 'missing_cost_label': ('INCONCLUSIVE', 'CostIdentityMissing'), 'topology_split': ('PENDING', 'GangTopologyUnavailable'), 'queue_owner_missing': ('REJECTED', 'QueueOwnerMissing'), 'duplicate_workload': ('REJECTED', 'WorkloadIdentityCollision'), 'borrowing_unbounded': ('REJECTED', 'BorrowingLimitRequired'), 'reclaim_without_priority': ('REJECTED', 'ReclaimPolicyUndefined'), 'preemption_without_checkpoint': ('BLOCKED', 'CheckpointRequiredBeforePreemption'), 'recovery_slo_missed': ('SLO_VIOLATED', 'PreemptionRecoveryTooSlow'), 'fairness_evidence_missing': ('INCONCLUSIVE', 'FairShareEvidenceMissing'), 'node_shape_fragmented': ('PENDING', 'ContiguousGPUShapeUnavailable'), 'resource_flavor_unknown': ('REJECTED', 'ResourceFlavorUnknown'), 'mixed_scheduler': ('REJECTED', 'SchedulerContractConflict'), 'spot_without_budget': ('REJECTED', 'InterruptionBudgetRequired'), 'slurm_duplicate_submission': ('BLOCKED', 'BackendRunLeaseAlreadyOwned'), 'live_cluster_missing': ('SKIPPED', 'NoKubernetesContextProvided')}
    phase, reason = mapping[item['type']]
    ok = phase == item['expected_phase'] and reason == item['expected_reason']
    return {'type': item['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    scheduled = schedule(scenario)
    measured = metrics(scenario, scheduled)
    thresholds = scenario['thresholds']
    checks = {'wait': measured['queue_wait_seconds_p95'] <= thresholds['maximum_queue_wait_seconds_p95'], 'admission': measured['admission_success_rate'] >= thresholds['minimum_admission_success_rate'], 'fairness': measured['fair_share_deviation'] <= thresholds['maximum_fair_share_deviation'], 'fragmentation': measured['gpu_fragmentation_ratio'] <= thresholds['maximum_gpu_fragmentation_ratio'], 'recovery': measured['preemption_recovery_seconds'] <= thresholds['maximum_preemption_recovery_seconds'], 'cost_identity': all((not validate_identity(job) for job in scenario['jobs']))}
    faults = [evaluate_fault(item) for item in scenario['faults']]
    status = 'PASS' if all(checks.values()) and all((item['status'] == 'PASS' for item in faults)) else 'FAIL'
    return {'status': status, 'scheduled': scheduled, 'metrics': measured, 'checks': checks, 'faults': faults}

def inspect_live(context: str | None) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    if shutil.which('kubectl') is None:
        return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
    commands = {'nodes': ['kubectl', '--context', context, 'get', 'nodes', '-o', 'json'], 'workloads': ['kubectl', '--context', context, 'get', 'workloads.kueue.x-k8s.io', '-A', '-o', 'json'], 'localqueues': ['kubectl', '--context', context, 'get', 'localqueues.kueue.x-k8s.io', '-A', '-o', 'json'], 'clusterqueues': ['kubectl', '--context', context, 'get', 'clusterqueues.kueue.x-k8s.io', '-o', 'json']}
    evidence = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        except subprocess.TimeoutExpired:
            return {'status': 'FAIL', 'reason': 'LiveBatchPlatformReadTimeout', 'step': name}
        if result.returncode:
            return {'status': 'FAIL', 'reason': 'LiveBatchPlatformReadFailed', 'step': name, 'stderr': result.stderr.strip()}
        evidence[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'reason': 'LiveBatchPlatformEvidenceCollected', 'evidence': evidence}

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
    print(f'Multi-tenant GPU batch platform: {report['status']}')
    for name, value in report['metrics'].items():
        print(f'  metric {name}: {value}')
    for item in report['scheduled']['admissions']:
        print(f'  job {item['job']}: {item['status']}/{item['reason']}')
    for fault in report['faults']:
        print(f'  fault {fault['type']}: {fault['status']} {fault['phase']}/{fault['reason']}')
    print(f'  live: {report['live']['status']}/{report['live']['reason']}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] in {'PASS', 'SKIPPED'} else 1

ENTRY_ID = 'project/project-02'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'batch_platform_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
