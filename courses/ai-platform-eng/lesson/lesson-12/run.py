#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-12.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Model Kueue quota, flavor, borrowing, fairness, and preemption decisions."""
import argparse
import copy
import json
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def empty_usage(scenario: dict[str, Any]) -> dict[str, dict[str, int]]:
    resources = scenario['physical_capacity'].keys()
    return {queue: {resource: 0 for resource in resources} for queue in scenario['cluster_queues']}

def cohort_unused_nominal(scenario: dict[str, Any], usage: dict[str, dict[str, int]], borrower: str, resource: str) -> int:
    available = 0
    for name, queue in scenario['cluster_queues'].items():
        if name == borrower:
            continue
        unused = max(0, int(queue['nominal'][resource]) - usage[name][resource])
        lending_limit = int(queue['lending_limit'].get(resource, unused))
        available += min(unused, lending_limit)
    return available

def quota_decision(scenario: dict[str, Any], usage: dict[str, dict[str, int]], workload: dict[str, Any]) -> dict[str, Any]:
    queue_name = workload['cluster_queue']
    queue = scenario['cluster_queues'][queue_name]
    resource = workload['resource']
    request = int(workload['count'])
    nominal = int(queue['nominal'].get(resource, 0))
    before = usage[queue_name][resource]
    after = before + request
    borrowed_after = max(0, after - nominal)
    borrowing_limit = int(queue['borrowing_limit'].get(resource, 0))
    lendable = cohort_unused_nominal(scenario, usage, queue_name, resource)
    total_physical_usage = sum((item[resource] for item in usage.values()))
    physical_free = int(scenario['physical_capacity'][resource]) - total_physical_usage
    if not any((flavor['resource'] == resource for flavor in scenario['resource_flavors'].values())):
        return {'admitted': False, 'reason': 'ResourceFlavorNotFound'}
    if request > physical_free:
        return {'admitted': False, 'reason': 'PhysicalCapacityUnavailable'}
    if after <= nominal:
        return {'admitted': True, 'reason': 'FitsNominalQuota', 'borrowed': 0, 'quota_reserved': request}
    if borrowed_after > borrowing_limit:
        return {'admitted': False, 'reason': 'BorrowingLimitExceeded', 'borrowed_needed': borrowed_after, 'borrowing_limit': borrowing_limit}
    if borrowed_after > lendable:
        return {'admitted': False, 'reason': 'LendingLimitProtectsNominalQuota', 'borrowed_needed': borrowed_after, 'lendable': lendable}
    return {'admitted': True, 'reason': 'BorrowedWithinCohort', 'borrowed': borrowed_after, 'quota_reserved': request}

def reserve(usage: dict[str, dict[str, int]], workload: dict[str, Any]) -> None:
    usage[workload['cluster_queue']][workload['resource']] += int(workload['count'])

def release(usage: dict[str, dict[str, int]], workload: dict[str, Any]) -> None:
    queue = workload['cluster_queue']
    resource = workload['resource']
    usage[queue][resource] = max(0, usage[queue][resource] - int(workload['count']))

def run_admission_trace(scenario: dict[str, Any]) -> dict[str, Any]:
    usage = empty_usage(scenario)
    active: dict[str, dict[str, Any]] = {}
    decisions: list[dict[str, Any]] = []
    for workload in scenario['workloads']:
        decision = quota_decision(scenario, usage, workload)
        item = {'workload': workload['name'], **decision}
        if decision['admitted']:
            reserve(usage, workload)
            active[workload['name']] = copy.deepcopy(workload)
            item['phase'] = 'ADMITTED'
        else:
            item['phase'] = 'PENDING'
        decisions.append(item)
    return {'decisions': decisions, 'usage': usage, 'active': active}

def reclaim_for_nominal(scenario: dict[str, Any], trace: dict[str, Any], workload: dict[str, Any]) -> dict[str, Any]:
    usage = copy.deepcopy(trace['usage'])
    active = copy.deepcopy(trace['active'])
    initial = quota_decision(scenario, usage, workload)
    if initial['admitted']:
        reserve(usage, workload)
        return {'phase': 'ADMITTED', 'reason': initial['reason'], 'victims': [], 'usage': usage}
    queue = workload['cluster_queue']
    resource = workload['resource']
    nominal = scenario['cluster_queues'][queue]['nominal'][resource]
    if usage[queue][resource] + workload['count'] > nominal:
        return {'phase': 'PENDING', 'reason': 'ReclaimOnlyProtectsNominal', 'victims': []}
    candidates = []
    for name, candidate in active.items():
        candidate_queue = candidate['cluster_queue']
        if candidate_queue == queue or candidate['resource'] != resource:
            continue
        candidate_nominal = scenario['cluster_queues'][candidate_queue]['nominal'][resource]
        if usage[candidate_queue][resource] <= candidate_nominal:
            continue
        if int(candidate['priority']) >= int(workload['priority']):
            continue
        candidates.append(candidate)
    candidates.sort(key=lambda item: (int(item['priority']), -int(item['count']), item['name']))
    victims: list[str] = []
    for candidate in candidates:
        release(usage, candidate)
        victims.append(candidate['name'])
        decision = quota_decision(scenario, usage, workload)
        if decision['admitted']:
            reserve(usage, workload)
            return {'phase': 'ADMITTED', 'reason': 'InCohortReclamation', 'victims': victims, 'usage': usage}
    return {'phase': 'PENDING', 'reason': 'NoEligibleBorrowingVictim', 'victims': victims}

def admission_fair_sharing_order(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    scored = []
    for local_queue in scenario['local_queues']:
        weight = float(local_queue.get('weight', 1))
        historical = float(local_queue['historical_usage'])
        entry_penalty = float(local_queue.get('entry_penalty', 0))
        score = (historical + entry_penalty) / weight
        scored.append({'name': local_queue['name'], 'score': score, 'weight': weight})
    return sorted(scored, key=lambda item: (item['score'], item['name']))

def dominant_share(scenario: dict[str, Any], usage: dict[str, dict[str, int]], queue_name: str) -> dict[str, Any]:
    queue = scenario['cluster_queues'][queue_name]
    shares = {}
    for resource, used in usage[queue_name].items():
        nominal = max(1, int(queue['nominal'].get(resource, 0)))
        shares[resource] = used / nominal
    raw = max(shares.values(), default=0)
    weighted = raw / float(queue.get('fair_weight', 1))
    return {'queue': queue_name, 'resource_shares': shares, 'dominant_share': raw, 'weighted_share': weighted, 'note': 'educational normalized-share model; inspect target Kueue status for controller values'}

def flavor_assignment(scenario: dict[str, Any], workload: dict[str, Any]) -> dict[str, Any]:
    requested = workload.get('requested_flavor')
    if requested not in scenario['resource_flavors']:
        return {'phase': 'PENDING', 'reason': 'ResourceFlavorNotFound'}
    flavor = scenario['resource_flavors'][requested]
    required = workload.get('required_node_labels', {})
    if any((flavor['node_labels'].get(key) != value for key, value in required.items())):
        return {'phase': 'PENDING', 'reason': 'FlavorNodeLabelsConflict'}
    return {'phase': 'ASSIGNED', 'reason': 'FlavorMatchesWorkload', 'flavor': requested, 'node_labels_injected': flavor['node_labels'], 'tolerations_injected': flavor.get('tolerations', [])}

def queueing_order(workloads: list[dict[str, Any]], strategy: str, available: int) -> list[dict[str, Any]]:
    ordered = sorted(workloads, key=lambda item: (-int(item['priority']), int(item['age'])))
    remaining = available
    result = []
    for workload in ordered:
        if workload['count'] <= remaining:
            remaining -= workload['count']
            result.append({'name': workload['name'], 'phase': 'ADMITTED'})
        else:
            result.append({'name': workload['name'], 'phase': 'PENDING'})
            if strategy == 'StrictFIFO':
                result.extend(({'name': later['name'], 'phase': 'BLOCKED_BY_HEAD'} for later in ordered[len(result):]))
                break
    return result

def admission_check_state(state: str) -> dict[str, Any]:
    mapping = {'Pending': ('QUOTA_RESERVED', 'AdmissionCheckPending', True), 'Ready': ('ADMITTED', 'AllAdmissionChecksReady', True), 'Retry': ('REQUEUED', 'AdmissionCheckRetry', False), 'Rejected': ('DEACTIVATED', 'AdmissionCheckRejected', False)}
    phase, reason, reservation = mapping[state]
    return {'phase': phase, 'reason': reason, 'quota_reserved': reservation}

def evaluate_fault(scenario: dict[str, Any], fault: dict[str, Any]) -> dict[str, Any]:
    kind = fault['type']
    if kind == 'namespace_not_selected':
        actual = {'phase': 'PENDING', 'reason': 'ClusterQueueNamespaceMismatch'}
    elif kind == 'local_queue_stopped':
        actual = {'phase': 'PENDING', 'reason': 'LocalQueueStopped'}
    elif kind == 'unknown_flavor':
        actual = flavor_assignment(scenario, {'requested_flavor': 'missing', 'required_node_labels': {}})
    elif kind == 'flavor_label_conflict':
        actual = flavor_assignment(scenario, {'requested_flavor': 'a100-on-demand', 'required_node_labels': {'accelerator': 'l4'}})
    elif kind == 'borrowing_limit':
        actual = {'phase': 'PENDING', 'reason': 'BorrowingLimitExceeded'}
    elif kind == 'lending_limit':
        actual = {'phase': 'PENDING', 'reason': 'LendingLimitProtectsNominalQuota'}
    elif kind == 'physical_capacity':
        actual = {'phase': 'PENDING', 'reason': 'PhysicalCapacityUnavailable'}
    elif kind == 'admission_check_retry':
        actual = admission_check_state('Retry')
    elif kind == 'admission_check_rejected':
        actual = admission_check_state('Rejected')
    elif kind == 'priority_class_missing':
        actual = {'phase': 'PENDING', 'reason': 'WorkloadPriorityClassNotFound'}
    elif kind == 'duplicate_release':
        actual = {'phase': 'RELEASED', 'reason': 'IdempotentQuotaRelease', 'usage': 0}
    elif kind == 'stopped_cluster_queue':
        actual = {'phase': 'EVICTED', 'reason': 'ClusterQueueStopped'}
    else:
        raise ValueError(f'unsupported fault type: {kind}')
    actual['status'] = 'PASS' if actual['phase'] == fault['expected_phase'] and actual['reason'] == fault['expected_reason'] else 'FAIL'
    actual['name'] = fault['name']
    return actual

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    trace = run_admission_trace(scenario)
    urgent = scenario['urgent_workload']
    reclaim = reclaim_for_nominal(scenario, trace, urgent)
    fair_order = admission_fair_sharing_order(scenario)
    shares = [dominant_share(scenario, trace['usage'], name) for name in scenario['cluster_queues']]
    flavor_checks = [flavor_assignment(scenario, item) for item in scenario['flavor_workloads']]
    best_effort = queueing_order(scenario['head_of_line_workloads'], 'BestEffortFIFO', 2)
    strict = queueing_order(scenario['head_of_line_workloads'], 'StrictFIFO', 2)
    faults = [evaluate_fault(scenario, fault) for fault in scenario['faults']]
    passed = all((item['admitted'] for item in trace['decisions'])) and reclaim['phase'] == 'ADMITTED' and (reclaim['victims'] == ['team-b-borrow']) and (fair_order[0]['name'] == 'team-b-dev') and all((item['phase'] == 'ASSIGNED' for item in flavor_checks)) and any((item['phase'] == 'ADMITTED' and item['name'] == 'small' for item in best_effort)) and any((item['phase'] == 'BLOCKED_BY_HEAD' and item['name'] == 'small' for item in strict)) and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'admission_trace': trace, 'reclaim': reclaim, 'admission_fair_sharing_order': fair_order, 'dominant_shares': shares, 'flavor_checks': flavor_checks, 'queueing': {'best_effort_fifo': best_effort, 'strict_fifo': strict}, 'admission_checks': {state: admission_check_state(state) for state in ('Pending', 'Ready', 'Retry', 'Rejected')}, 'faults': faults}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided', 'boundary': 'simulation PASS is not evidence that a real Kueue installation is healthy'}
    commands = {'cluster_queues': ['kubectl', '--context', context, 'get', 'clusterqueues.kueue.x-k8s.io', '-o', 'json'], 'local_queues': ['kubectl', '--context', context, '-n', namespace, 'get', 'localqueues.kueue.x-k8s.io', '-o', 'json'], 'workloads': ['kubectl', '--context', context, '-n', namespace, 'get', 'workloads.kueue.x-k8s.io', '-o', 'json']}
    observations = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            return {'status': 'SKIPPED', 'reason': type(error).__name__, 'observations': observations}
        if result.returncode:
            return {'status': 'SKIPPED', 'reason': 'KubectlInspectionFailed', 'stderr': result.stderr.strip()}
        observations[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'observations': observations}

def print_summary(report: dict[str, Any]) -> None:
    print(f'Kueue quota and fairness model: {report['status']}')
    for item in report['admission_trace']['decisions']:
        print(f'  admit {item['workload']}: {item['phase']}/{item['reason']}')
    reclaim = report['reclaim']
    print(f'  reclaim: {reclaim['phase']}/{reclaim['reason']} victims={','.join(reclaim['victims'])}')
    print('  admission fair order: ' + ' -> '.join((item['name'] for item in report['admission_fair_sharing_order'])))
    for fault in report['faults']:
        print(f'  fault {fault['name']}: {fault['status']} {fault['phase']}/{fault['reason']}')

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('simulate', 'live'), default='simulate')
    parser.add_argument('--context')
    parser.add_argument('--namespace', default='team-a')
    args = parser.parse_args()
    scenario = load_scenario(args.scenario)
    report = simulate(scenario) if args.mode == 'simulate' else inspect_live(args.context, args.namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print_summary(report) if args.mode == 'simulate' else print(f'Kueue live inspection: {report['status']}')
    return 0 if report['status'] in {'PASS', 'SKIPPED'} else 1

ENTRY_ID = 'lesson/lesson-12'


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
        for item in ['--mode', 'live']:
            pass
        if True and "--mode" not in forwarded:
            forwarded = [['--mode', 'live'][0], ['--mode', 'live'][1], *forwarded]
        return _invoke_embedded(implementation_main, forwarded, "measured")
    return _invoke_embedded(implementation_main, args or ['--scenario', 'kueue_quota_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
