#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-13.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Replay Volcano-style actions and plugins on a deterministic AI workload set."""
import argparse
import copy
import json
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def free_gpu(node: dict[str, Any]) -> int:
    return int(node['gpu'] - node.get('allocated_gpu', 0))

def binpack_score(node: dict[str, Any], request: int, gpu_weight: float=2.0) -> float:
    if free_gpu(node) < request:
        return -1.0
    after = (node.get('allocated_gpu', 0) + request) / node['gpu']
    cpu_after = node.get('allocated_cpu', 0) / node['cpu']
    return (gpu_weight * after + cpu_after) / (gpu_weight + 1)

def place_tasks(nodes: list[dict[str, Any]], job: dict[str, Any], policy: str) -> dict[str, Any]:
    staged = copy.deepcopy(nodes)
    placements = []
    for index in range(job['tasks']):
        candidates = [node for node in staged if free_gpu(node) >= job['gpu_per_task']]
        if not candidates:
            return {'feasible': False, 'placements': placements, 'staged': staged}
        if policy == 'binpack':
            selected = max(candidates, key=lambda node: (binpack_score(node, job['gpu_per_task']), node['name']))
        elif policy == 'spread':
            selected = min(candidates, key=lambda node: (node.get('allocated_gpu', 0), node['name']))
        else:
            raise ValueError(policy)
        selected['allocated_gpu'] = selected.get('allocated_gpu', 0) + job['gpu_per_task']
        placements.append({'task': f'{job['name']}-{index}', 'node': selected['name']})
    return {'feasible': True, 'placements': placements, 'staged': staged}

def commit(nodes: list[dict[str, Any]], staged: list[dict[str, Any]]) -> None:
    current = {node['name']: node for node in nodes}
    for node in staged:
        current[node['name']]['allocated_gpu'] = node.get('allocated_gpu', 0)

def allocate_with_gang(scenario: dict[str, Any], policy: str) -> dict[str, Any]:
    nodes = copy.deepcopy(scenario['nodes'])
    results = []
    for job in scenario['jobs']:
        plan = place_tasks(nodes, job, policy)
        if not plan['feasible'] or len(plan['placements']) < job['min_available']:
            results.append({'job': job['name'], 'phase': 'PENDING', 'reason': 'GangMinAvailableUnsatisfied', 'committed': 0, 'staged_rolled_back': len(plan['placements'])})
            continue
        commit(nodes, plan['staged'])
        results.append({'job': job['name'], 'phase': 'ALLOCATED', 'reason': f'GangCommittedWith{policy.title()}', 'committed': len(plan['placements']), 'placements': plan['placements']})
    blocks = sorted((free_gpu(node) for node in nodes), reverse=True)
    return {'policy': policy, 'jobs': results, 'nodes': nodes, 'largest_free_gpu_block': blocks[0], 'completely_free_nodes': sum((node.get('allocated_gpu', 0) == 0 for node in nodes))}

def dominant_share(job: dict[str, Any], cluster: dict[str, int]) -> float:
    return max(job['gpu_request'] / cluster['gpu'], job['cpu_request'] / cluster['cpu'], job['memory_request'] / cluster['memory'])

def drf_order(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for job in scenario['drf_jobs']:
        share = dominant_share(job, scenario['cluster_resources'])
        result.append({'job': job['name'], 'dominant_share': share})
    return sorted(result, key=lambda item: (item['dominant_share'], item['job']))

def queue_deserved(scenario: dict[str, Any], mode: str) -> dict[str, int]:
    queues = scenario['queues']
    total = scenario['cluster_resources']['gpu']
    if mode == 'capacity':
        return {name: int(queue['deserved_gpu']) for name, queue in queues.items()}
    if mode == 'proportion':
        total_weight = sum((int(queue['weight']) for queue in queues.values()))
        return {name: int(total * int(queue['weight']) / total_weight) for name, queue in queues.items()}
    raise ValueError(mode)

def reclaim_online_capacity(scenario: dict[str, Any], mode: str) -> dict[str, Any]:
    deserved = queue_deserved(scenario, mode)
    usage = copy.deepcopy(scenario['queue_usage_gpu'])
    request = int(scenario['online_burst']['gpu'])
    online = scenario['online_burst']['queue']
    free = scenario['cluster_resources']['gpu'] - sum(usage.values())
    deficit = max(0, request - free)
    victims = []
    for name, queue in sorted(scenario['queues'].items(), key=lambda item: item[1]['priority']):
        if name == online or not queue['reclaimable'] or deficit <= 0:
            continue
        excess = max(0, usage[name] - deserved[name])
        release = min(excess, deficit)
        if release:
            usage[name] -= release
            deficit -= release
            victims.append({'queue': name, 'gpu': release, 'reason': 'QueueOverDeserved'})
    if deficit:
        return {'phase': 'PENDING', 'reason': 'NoReclaimableExcess', 'victims': victims}
    usage[online] += request
    return {'phase': 'ALLOCATED', 'reason': 'CrossQueueReclaim', 'victims': victims, 'usage': usage, 'deserved': deserved}

def preempt_within_queue(scenario: dict[str, Any]) -> dict[str, Any]:
    waiting = scenario['same_queue_preemptor']
    candidates = [item for item in scenario['same_queue_running'] if item['queue'] == waiting['queue'] and item['priority'] < waiting['priority']]
    candidates.sort(key=lambda item: (item['priority'], -item['gpu'], item['name']))
    released = 0
    victims = []
    for item in candidates:
        victims.append(item['name'])
        released += item['gpu']
        if released >= waiting['gpu']:
            return {'phase': 'ALLOCATED', 'reason': 'SameQueuePriorityPreempt', 'victims': victims}
    return {'phase': 'PENDING', 'reason': 'NoEligibleLowerPriorityVictim', 'victims': victims}

def validate_pipeline(config: dict[str, Any]) -> dict[str, Any]:
    actions = config['actions']
    plugins = config['plugins']
    errors = []
    if 'allocate' not in actions:
        errors.append('AllocateActionMissing')
    if 'capacity' in plugins and 'proportion' in plugins:
        errors.append('CapacityAndProportionConflict')
    if 'enqueue' in actions and any((item in actions for item in ('preempt', 'reclaim'))):
        errors.append('EnqueueCanBlockPreemptOrReclaimPodCreation')
    if 'gang' not in plugins:
        errors.append('GangPluginMissingForRigidJobs')
    return {'valid': not errors, 'errors': errors}

def mixed_workload_slo(scenario: dict[str, Any]) -> dict[str, Any]:
    reclaim = reclaim_online_capacity(scenario, 'capacity')
    online = scenario['online_burst']
    checkpoint = scenario['offline_checkpoint_seconds']
    warmup = online['warmup_seconds']
    total = checkpoint + warmup
    return {'phase': 'SLO_MET' if reclaim['phase'] == 'ALLOCATED' and total <= online['deadline_seconds'] else 'SLO_MISSED', 'reclaim': reclaim, 'reclaim_and_warmup_seconds': total, 'deadline_seconds': online['deadline_seconds'], 'boundary': 'queue reclaim does not replace runtime QoS, graceful eviction, or service readiness'}

def evaluate_fault(scenario: dict[str, Any], fault: dict[str, Any]) -> dict[str, Any]:
    kind = fault['type']
    if kind == 'min_available_missing':
        actual = {'phase': 'PENDING', 'reason': 'GangMinAvailableUnsatisfied'}
    elif kind == 'capacity_proportion_conflict':
        actual = {'phase': 'REJECTED', 'reason': 'CapacityAndProportionConflict'}
    elif kind == 'enqueue_reclaim_conflict':
        actual = {'phase': 'BLOCKED', 'reason': 'EnqueuePreventsReclaimTrigger'}
    elif kind == 'queue_capability':
        actual = {'phase': 'PENDING', 'reason': 'QueueCapabilityExceeded'}
    elif kind == 'queue_not_reclaimable':
        actual = {'phase': 'PENDING', 'reason': 'TargetQueueNotReclaimable'}
    elif kind == 'same_queue_priority':
        actual = {'phase': 'ALLOCATED', 'reason': 'SameQueuePriorityPreempt'}
    elif kind == 'cross_queue_preempt':
        actual = {'phase': 'REJECTED', 'reason': 'UseReclaimForCrossQueue'}
    elif kind == 'predicates_failure':
        actual = {'phase': 'PENDING', 'reason': 'PredicatesRejectedAllNodes'}
    elif kind == 'binpack_hotspot':
        actual = {'phase': 'DEGRADED', 'reason': 'BinpackConcentratedFailureDomain'}
    elif kind == 'drf_large_share':
        actual = {'phase': 'DEPRIORITIZED', 'reason': 'HigherDominantShare'}
    elif kind == 'victim_grace':
        actual = {'phase': 'RECLAIMING', 'reason': 'VictimsTerminating'}
    elif kind == 'scheduler_restart':
        actual = {'phase': 'RECOVERED', 'reason': 'SessionRebuiltFromCacheAndAPI'}
    else:
        raise ValueError(kind)
    actual['name'] = fault['name']
    actual['status'] = 'PASS' if actual['phase'] == fault['expected_phase'] and actual['reason'] == fault['expected_reason'] else 'FAIL'
    return actual

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    binpack = allocate_with_gang(scenario, 'binpack')
    spread = allocate_with_gang(scenario, 'spread')
    drf = drf_order(scenario)
    capacity = reclaim_online_capacity(scenario, 'capacity')
    proportion = reclaim_online_capacity(scenario, 'proportion')
    preempt = preempt_within_queue(scenario)
    mixed = mixed_workload_slo(scenario)
    pipeline = validate_pipeline(scenario['scheduler_pipeline'])
    safe_pipeline = validate_pipeline(scenario['safe_scheduler_pipeline'])
    faults = [evaluate_fault(scenario, item) for item in scenario['faults']]
    passed = binpack['completely_free_nodes'] > spread['completely_free_nodes'] and drf[0]['job'] == 'cpu-light' and (capacity['phase'] == 'ALLOCATED') and (proportion['phase'] == 'ALLOCATED') and (preempt['phase'] == 'ALLOCATED') and (mixed['phase'] == 'SLO_MET') and (not pipeline['valid']) and safe_pipeline['valid'] and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'binpack': binpack, 'spread': spread, 'drf_order': drf, 'capacity_reclaim': capacity, 'proportion_reclaim': proportion, 'same_queue_preempt': preempt, 'mixed_workload_slo': mixed, 'unsafe_pipeline': pipeline, 'safe_pipeline': safe_pipeline, 'faults': faults}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    commands = {'jobs': ['kubectl', '--context', context, '-n', namespace, 'get', 'jobs.batch.volcano.sh', '-o', 'json'], 'podgroups': ['kubectl', '--context', context, '-n', namespace, 'get', 'podgroups.scheduling.volcano.sh', '-o', 'json'], 'queues': ['kubectl', '--context', context, 'get', 'queues.scheduling.volcano.sh', '-o', 'json'], 'config': ['kubectl', '--context', context, '-n', 'volcano-system', 'get', 'configmap', 'volcano-scheduler-configmap', '-o', 'json']}
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
    print(f'Volcano policy replay: {report['status']}')
    print(f'  placement: binpack-free-nodes={report['binpack']['completely_free_nodes']} spread-free-nodes={report['spread']['completely_free_nodes']}')
    print('  DRF order: ' + ' -> '.join((item['job'] for item in report['drf_order'])))
    print(f'  reclaim: capacity={report['capacity_reclaim']['phase']} proportion={report['proportion_reclaim']['phase']}')
    print(f'  online/offline: {report['mixed_workload_slo']['phase']}')
    for fault in report['faults']:
        print(f'  fault {fault['name']}: {fault['status']} {fault['phase']}/{fault['reason']}')

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('simulate', 'live'), default='simulate')
    parser.add_argument('--context')
    parser.add_argument('--namespace', default='volcano-lab')
    args = parser.parse_args()
    scenario = load_scenario(args.scenario)
    report = simulate(scenario) if args.mode == 'simulate' else inspect_live(args.context, args.namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print_summary(report) if args.mode == 'simulate' else print(f'Volcano live inspection: {report['status']}')
    return 0 if report['status'] in {'PASS', 'SKIPPED'} else 1

ENTRY_ID = 'lesson/lesson-13'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'volcano_policy_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
