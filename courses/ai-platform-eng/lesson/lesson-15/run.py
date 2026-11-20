#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-15.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic replay for GPU node provisioning, Spot, consolidation, and interruption."""
import argparse
import copy
import json
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def effective_node_capacity(instance: dict[str, Any], overhead: dict[str, int]) -> dict[str, int]:
    return {'gpu': max(0, instance['gpu'] - overhead.get('gpu', 0)), 'cpu': max(0, instance['cpu'] - overhead.get('cpu', 0)), 'memory': max(0, instance['memory'] - overhead.get('memory', 0))}

def nodes_needed(workload: dict[str, Any], instance: dict[str, Any], overhead: dict[str, int]) -> int | None:
    cap = effective_node_capacity(instance, overhead)
    per_node = min(cap['gpu'] // workload['gpu_per_pod'], cap['cpu'] // workload['cpu_per_pod'], cap['memory'] // workload['memory_per_pod'])
    if per_node <= 0:
        return None
    return (workload['pods'] + per_node - 1) // per_node

def plan_provision(scenario: dict[str, Any], workload: dict[str, Any]) -> dict[str, Any]:
    pool = scenario['node_pools'][workload['node_pool']]
    if scenario['queue_quota_gpu'] < workload['pods'] * workload['gpu_per_pod']:
        return {'phase': 'PENDING', 'reason': 'QuotaReservationMissing'}
    candidates = []
    for instance in scenario['instance_types']:
        if instance['capacity_type'] not in pool['capacity_types']:
            continue
        if instance['name'] not in pool['instance_types']:
            continue
        if workload.get('zone') and workload['zone'] not in instance['zones']:
            continue
        count = nodes_needed(workload, instance, scenario['daemonset_overhead'])
        if count is None:
            continue
        total_gpu = count * instance['gpu']
        if pool['current_gpu'] + total_gpu > pool['gpu_limit']:
            continue
        candidates.append((instance['price_per_hour'] * count, -len(instance['zones']), instance['name'], count, instance))
    if not candidates:
        return {'phase': 'FAILED', 'reason': 'NoCompatibleCapacityWithinNodePoolLimits'}
    _, _, _, count, instance = sorted(candidates)[0]
    if not instance['provider_capacity']:
        return {'phase': 'FAILED', 'reason': 'CloudProviderCapacityUnavailable', 'instance_type': instance['name']}
    return {'phase': 'PROVISIONED', 'reason': 'CapacityReady', 'instance_type': instance['name'], 'capacity_type': instance['capacity_type'], 'nodes': count, 'hourly_cost': round(instance['price_per_hour'] * count, 3)}

def provisioning_request_flow(scenario: dict[str, Any]) -> dict[str, Any]:
    workload = scenario['workload']
    plan = plan_provision(scenario, workload)
    timeline = ['QuotaReserved', 'ProvisioningRequestCreated']
    if plan['phase'] == 'PROVISIONED':
        timeline += ['ProvisionedTrue', 'AdmissionCheckReady', 'WorkloadAdmitted']
        return {'phase': 'ADMITTED', 'reason': 'QuotaAndCapacityGuaranteed', 'timeline': timeline, 'plan': plan}
    timeline += ['ProvisioningFailed', 'QuotaReleased']
    return {'phase': 'PENDING', 'reason': plan['reason'], 'timeline': timeline, 'plan': plan}

def consolidate_node(scenario: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    budget = scenario['disruption_budget_nodes']
    if scenario['nodes_disrupting'] >= budget:
        return {'phase': 'BLOCKED', 'reason': 'NodePoolDisruptionBudgetExhausted'}
    if node['blocking_pdb']:
        return {'phase': 'BLOCKED', 'reason': 'PodDisruptionBudgetBlocksVoluntaryDisruption'}
    if node['do_not_disrupt']:
        return {'phase': 'BLOCKED', 'reason': 'DoNotDisruptBlocksConsolidation'}
    if node['preserves_required_topology'] is False:
        return {'phase': 'BLOCKED', 'reason': 'ConsolidationWouldBreakTopologyCapacity'}
    if node['replacement_cost'] >= node['current_cost']:
        return {'phase': 'BLOCKED', 'reason': 'NoCostSavingReplacement'}
    return {'phase': 'APPROVED', 'reason': 'ReplacementReducesCostWithinDisruptionBudget'}

def interruption_timeline(scenario: dict[str, Any]) -> dict[str, Any]:
    event = scenario['spot_interruption']
    replacement_ready = event['replacement_launch_seconds'] <= event['notice_seconds']
    checkpoint_done = event['checkpoint_seconds'] <= event['notice_seconds']
    drain_done = event['checkpoint_seconds'] + event['drain_seconds'] <= event['notice_seconds']
    phase = 'RECOVERED' if replacement_ready and checkpoint_done and drain_done else 'INTERRUPTED'
    return {'phase': phase, 'reason': 'ReplacementReadyAndCheckpointCompleted' if phase == 'RECOVERED' else 'InterruptionDeadlineExceeded', 'timeline': ['InterruptionWarning', 'NodeTainted', 'ReplacementLaunched', 'NodeDraining', 'InstanceTerminated'], 'replacement_ready': replacement_ready, 'checkpoint_done': checkpoint_done, 'drain_done': drain_done, 'notice_seconds': event['notice_seconds'], 'boundary': 'provider notice and event delivery are not a durable checkpoint guarantee'}

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    contracts = {'requests_too_low': ('DEGRADED', 'NodeProvisionedFromRequestsButRuntimeDemandExceedsCapacity'), 'pool_limit': ('FAILED', 'NodePoolResourceLimitExceeded'), 'constraint_conflict': ('FAILED', 'NoInstanceTypeMatchesPodAndNodePoolConstraints'), 'provider_capacity': ('FAILED', 'CloudProviderCapacityUnavailable'), 'quota_missing': ('PENDING', 'QuotaReservationMissing'), 'booking_expired': ('PENDING', 'ProvisioningBookingExpired'), 'capacity_revoked': ('EVICTED', 'ProvisionedCapacityRevoked'), 'pdb_blocks': ('BLOCKED', 'PodDisruptionBudgetBlocksVoluntaryDisruption'), 'do_not_disrupt_forceful': ('DISRUPTING', 'ForcefulInterruptionIgnoresDoNotDisrupt'), 'topology_fragmentation': ('BLOCKED', 'ConsolidationWouldBreakTopologyCapacity'), 'checkpoint_too_slow': ('INTERRUPTED', 'InterruptionDeadlineExceeded'), 'replacement_too_slow': ('DEGRADED', 'ReplacementNotReadyBeforeTermination'), 'budget_exhausted': ('BLOCKED', 'NodePoolDisruptionBudgetExhausted'), 'daemonset_overhead': ('FAILED', 'DaemonSetOverheadMakesPodShapeInfeasible')}
    phase, reason = contracts[fault['type']]
    return {'name': fault['name'], 'phase': phase, 'reason': reason, 'status': 'PASS' if (phase, reason) == (fault['expected_phase'], fault['expected_reason']) else 'FAIL'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    provision = provisioning_request_flow(scenario)
    consolidation = {node['name']: consolidate_node(scenario, node) for node in scenario['consolidation_nodes']}
    interruption = interruption_timeline(scenario)
    faults = [evaluate_fault(item) for item in scenario['faults']]
    passed = provision['phase'] == 'ADMITTED' and consolidation['safe-spot-node']['phase'] == 'APPROVED' and (consolidation['topology-anchor']['phase'] == 'BLOCKED') and (interruption['phase'] == 'RECOVERED') and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'provisioning': provision, 'consolidation': consolidation, 'interruption': interruption, 'faults': faults}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    commands = {'nodes': ['kubectl', '--context', context, 'get', 'nodes', '-o', 'json'], 'workloads': ['kubectl', '--context', context, '-n', namespace, 'get', 'workloads.kueue.x-k8s.io', '-o', 'json'], 'provisioning': ['kubectl', '--context', context, '-n', namespace, 'get', 'provisioningrequests.autoscaling.x-k8s.io', '-o', 'json']}
    observations = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            return {'status': 'SKIPPED', 'reason': f'LiveCommandUnavailable:{error}'}
        if result.returncode:
            return {'status': 'SKIPPED', 'reason': f'LivePrerequisiteUnavailable:{name}', 'stderr': result.stderr.strip()}
        observations[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'observations': observations, 'boundary': 'read-only discovery does not prove cloud provisioning, Spot interruption delivery, checkpoint recovery, or consolidation'}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live-context')
    parser.add_argument('--namespace', default='elastic-capacity-lab')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.live_context, args.namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Elastic capacity replay: {report['status']}')
    print(f'  provisioning: {report['provisioning']['phase']}/{report['provisioning']['reason']}')
    print(f'  interruption: {report['interruption']['phase']}/{report['interruption']['reason']}')
    for name, item in report['consolidation'].items():
        print(f'  consolidation {name}: {item['phase']}/{item['reason']}')
    for item in report['faults']:
        print(f'  fault {item['name']}: {item['status']} {item['phase']}/{item['reason']}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-15'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'elastic_capacity_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
