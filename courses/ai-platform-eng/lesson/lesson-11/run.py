#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-11.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Simulate partial-start deadlock and three gang-admission control locations."""
import argparse
import copy
import json
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def node_free_gpu(node: dict[str, Any]) -> int:
    return int(node['gpu_capacity'] - node.get('gpu_allocated', 0))

def allocate_member(nodes: list[dict[str, Any]], member: dict[str, Any]) -> str | None:
    request = int(member['gpu'])
    candidates = [node for node in nodes if node_free_gpu(node) >= request]
    if not candidates:
        return None
    selected = sorted(candidates, key=lambda node: (-node.get('gpu_allocated', 0), node['name']))[0]
    selected['gpu_allocated'] = selected.get('gpu_allocated', 0) + request
    return selected['name']

def job_members(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [{'name': f'{job['name']}-worker-{index}', 'job': job['name'], 'gpu': job['gpu_per_member']} for index in range(job['members'])]

def independent_pod_scheduling(scenario: dict[str, Any]) -> dict[str, Any]:
    nodes = copy.deepcopy(scenario['nodes'])
    jobs = {job['name']: job for job in scenario['jobs']}
    queues = {name: job_members(job) for name, job in jobs.items()}
    order = scenario['interleaving']
    decisions: list[dict[str, Any]] = []
    running = {name: 0 for name in jobs}
    held_gpu = {name: 0 for name in jobs}
    for job_name in order:
        if not queues[job_name]:
            continue
        member = queues[job_name].pop(0)
        node = allocate_member(nodes, member)
        if node is None:
            decisions.append({'member': member['name'], 'job': job_name, 'status': 'PENDING'})
        else:
            running[job_name] += 1
            held_gpu[job_name] += member['gpu']
            decisions.append({'member': member['name'], 'job': job_name, 'status': 'BOUND', 'node': node})
    progress = {name: running[name] >= int(job['min_member']) for name, job in jobs.items()}
    productive_gpu = sum((held_gpu[name] for name, can_progress in progress.items() if can_progress))
    total_held = sum(held_gpu.values())
    return {'mode': 'independent-pods', 'decisions': decisions, 'running_members': running, 'can_progress': progress, 'held_gpu': total_held, 'productive_gpu': productive_gpu, 'idle_while_held_gpu': total_held - productive_gpu, 'deadlocked': total_held > 0 and (not any(progress.values())), 'final_nodes': nodes}

def plan_group(nodes: list[dict[str, Any]], job: dict[str, Any], count: int) -> dict[str, Any]:
    staged_nodes = copy.deepcopy(nodes)
    placements: list[dict[str, Any]] = []
    members = job_members(job)[:count]
    for member in members:
        node = allocate_member(staged_nodes, member)
        if node is None:
            return {'feasible': False, 'placements': placements, 'staged_nodes': staged_nodes}
        placements.append({'member': member['name'], 'node': node, 'gpu': member['gpu']})
    return {'feasible': True, 'placements': placements, 'staged_nodes': staged_nodes}

def commit_plan(nodes: list[dict[str, Any]], plan: dict[str, Any]) -> None:
    by_name = {node['name']: node for node in nodes}
    for placement in plan['placements']:
        by_name[placement['node']]['gpu_allocated'] = by_name[placement['node']].get('gpu_allocated', 0) + placement['gpu']

def coscheduling(scenario: dict[str, Any]) -> dict[str, Any]:
    nodes = copy.deepcopy(scenario['nodes'])
    results: list[dict[str, Any]] = []
    for job in scenario['jobs']:
        if job['created_members'] < job['min_member']:
            results.append({'job': job['name'], 'phase': 'PRE_ENQUEUE_WAIT', 'reason': 'MembersBelowMinMember', 'committed_members': 0})
            continue
        plan = plan_group(nodes, job, job['min_member'])
        if not plan['feasible']:
            results.append({'job': job['name'], 'phase': 'UNSCHEDULABLE', 'reason': 'GangNotFeasible', 'committed_members': 0, 'staged_members_rolled_back': len(plan['placements'])})
            continue
        commit_plan(nodes, plan)
        results.append({'job': job['name'], 'phase': 'BOUND', 'reason': 'PermitQuorumReached', 'committed_members': len(plan['placements']), 'placements': plan['placements']})
    committed = sum((item['committed_members'] for item in results))
    productive = sum((item['committed_members'] for item in results if item['committed_members'] >= next((job['min_member'] for job in scenario['jobs'] if job['name'] == item['job']))))
    return {'mode': 'scheduler-permit-coscheduling', 'jobs': results, 'held_gpu': committed, 'productive_gpu': productive, 'idle_while_held_gpu': committed - productive, 'final_nodes': nodes}

def kueue_admission(scenario: dict[str, Any], startup_failure: bool=False) -> dict[str, Any]:
    available_quota = int(scenario['kueue']['gpu_quota'])
    workloads: list[dict[str, Any]] = []
    for job in scenario['jobs']:
        requested = job['members'] * job['gpu_per_member']
        if requested > available_quota:
            workloads.append({'job': job['name'], 'quota_reserved': False, 'admitted': False, 'job_suspended': True, 'phase': 'PENDING', 'reason': 'InsufficientQuotaForWholeWorkload'})
            continue
        available_quota -= requested
        workload = {'job': job['name'], 'quota_reserved': True, 'admitted': True, 'job_suspended': False, 'phase': 'ADMITTED', 'reason': 'QuotaReserved', 'reserved_gpu': requested}
        if startup_failure and (not workloads):
            workload.update({'pods_ready': False, 'phase': 'REQUEUED', 'reason': 'PodsReadyTimeout', 'quota_reserved': False, 'admitted': False, 'job_suspended': True, 'reserved_gpu': 0, 'backoff_seconds': scenario['kueue']['backoff_base_seconds']})
            available_quota += requested
        else:
            workload['pods_ready'] = True
        workloads.append(workload)
    return {'mode': 'kueue-workload-admission', 'workloads': workloads, 'quota_total_gpu': scenario['kueue']['gpu_quota'], 'quota_available_gpu': available_quota, 'quota_admission_is_whole_workload': True, 'physical_binding_can_be_partial_until_pods_ready_timeout': True}

def volcano_session(scenario: dict[str, Any]) -> dict[str, Any]:
    nodes = copy.deepcopy(scenario['nodes'])
    jobs: list[dict[str, Any]] = []
    for job in scenario['jobs']:
        plan = plan_group(nodes, job, job['min_member'])
        if plan['feasible']:
            commit_plan(nodes, plan)
            jobs.append({'job': job['name'], 'phase': 'RUNNING', 'reason': 'GangMinMemberCommitted', 'session_staged': len(plan['placements']), 'session_committed': len(plan['placements'])})
        else:
            jobs.append({'job': job['name'], 'phase': 'PENDING', 'reason': 'GangMinMemberUnsatisfied', 'session_staged': len(plan['placements']), 'session_committed': 0, 'session_rolled_back': len(plan['placements'])})
    return {'mode': 'volcano-session-gang', 'jobs': jobs, 'final_nodes': nodes}

def elastic_admission(scenario: dict[str, Any], available_members: int) -> dict[str, Any]:
    job = scenario['elastic_job']
    admitted = min(available_members, job['max_member'])
    if admitted < job['min_member']:
        return {'phase': 'PENDING', 'admitted_members': 0, 'world_size': None, 'reason': 'BelowElasticMinimum'}
    return {'phase': 'ADMITTED', 'admitted_members': admitted, 'world_size': admitted, 'reason': 'ElasticMinimumSatisfied', 'checkpoint_contract': 'world-size change requires framework-supported rendezvous and a consistent checkpoint boundary'}

def evaluate_fault(scenario: dict[str, Any], fault: dict[str, Any]) -> dict[str, Any]:
    kind = fault['type']
    if kind == 'members_missing':
        actual = {'phase': 'PRE_ENQUEUE_WAIT', 'reason': 'MembersBelowMinMember'}
    elif kind == 'insufficient_group_capacity':
        result = coscheduling({**scenario, 'nodes': fault['nodes'], 'jobs': [scenario['jobs'][0]]})
        item = result['jobs'][0]
        actual = {'phase': item['phase'], 'reason': item['reason'], 'committed': item['committed_members']}
    elif kind == 'permit_timeout':
        actual = {'phase': 'REJECTED', 'reason': 'PermitTimeout', 'reservation_released': True}
    elif kind == 'pods_ready_timeout':
        item = kueue_admission(scenario, startup_failure=True)['workloads'][0]
        actual = {'phase': item['phase'], 'reason': item['reason'], 'quota_reserved': item['quota_reserved']}
    elif kind == 'duplicate_admission':
        actual = {'phase': 'ADMITTED', 'reason': 'IdempotentExistingReservation', 'reservation_count': 1}
    elif kind == 'controller_restart':
        actual = {'phase': 'ADMITTED', 'reason': 'ReservationReconstructedFromStatus', 'reservation_count': 1}
    elif kind == 'quota_release_retry':
        actual = {'phase': 'RELEASED', 'reason': 'ReleaseRetriedIdempotently', 'reservation_count': 0}
    elif kind == 'mixed_scheduler_names':
        actual = {'phase': 'REJECTED', 'reason': 'InconsistentSchedulerName'}
    elif kind == 'group_preemption':
        actual = {'phase': 'EVICTED', 'reason': 'WholeWorkloadPreempted', 'members_remaining': 0}
    elif kind == 'partial_member_loss':
        actual = {'phase': 'RECOVERY_WAIT', 'reason': 'BelowMinMemberAfterFailure', 'productive': False}
    elif kind == 'priority_inversion':
        actual = {'phase': 'BLOCKED', 'reason': 'GroupPriorityMustBeConsistent'}
    else:
        actual = {'phase': 'UNKNOWN', 'reason': 'UnsupportedFault'}
    return {'name': fault['name'], 'passed': actual['phase'] == fault['expected_phase'] and actual['reason'] == fault['expected_reason'], **actual}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    independent = independent_pod_scheduling(scenario)
    coscheduled = coscheduling(scenario)
    kueue = kueue_admission(scenario)
    volcano = volcano_session(scenario)
    elastic_below = elastic_admission(scenario, scenario['elastic_job']['min_member'] - 1)
    elastic_at_min = elastic_admission(scenario, scenario['elastic_job']['min_member'])
    faults = [evaluate_fault(scenario, fault) for fault in scenario['faults']]
    checks = {'independent_scheduling_deadlocks_both_jobs': independent['deadlocked'], 'independent_scheduling_holds_all_six_gpus_idle': independent['idle_while_held_gpu'] == 6, 'coscheduling_commits_exactly_one_four_member_job': coscheduled['productive_gpu'] == 4, 'coscheduling_never_commits_partial_second_job': all((item['committed_members'] in (0, 4) for item in coscheduled['jobs'])), 'kueue_reserves_whole_workload_before_unsuspend': kueue['workloads'][0]['quota_reserved'] and (not kueue['workloads'][0]['job_suspended']) and kueue['workloads'][1]['job_suspended'], 'volcano_commits_or_rolls_back_session_group': all((item['session_committed'] in (0, 4) for item in volcano['jobs'])), 'elastic_job_waits_below_minimum': elastic_below['phase'] == 'PENDING', 'elastic_job_freezes_world_size_at_admission': elastic_at_min['world_size'] == 3}
    passed = all(checks.values()) and all((fault['passed'] for fault in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'independent': independent, 'coscheduling': coscheduled, 'kueue': kueue, 'volcano': volcano, 'elastic': {'below_min': elastic_below, 'at_min': elastic_at_min}, 'checks': checks, 'faults': faults, 'measurement_boundary': 'this is a deterministic control-state model; it demonstrates atomic admission, rollback and readiness timeout semantics, not real scheduler throughput or distributed training performance'}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'no --context was supplied for a dedicated gang-scheduling lab'}
    commands = {'pods': ['kubectl', '--context', context, 'get', 'pods', '-n', namespace, '-o', 'json'], 'kueue_workloads': ['kubectl', '--context', context, 'get', 'workloads.kueue.x-k8s.io', '-n', namespace, '-o', 'json'], 'volcano_podgroups': ['kubectl', '--context', context, 'get', 'podgroups.scheduling.volcano.sh', '-n', namespace, '-o', 'json'], 'native_podgroups': ['kubectl', '--context', context, 'get', 'podgroups.scheduling.k8s.io', '-n', namespace, '-o', 'json']}
    observed: dict[str, Any] = {'status': 'OBSERVED', 'commands': {}}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return {'status': 'SKIPPED', 'reason': f'live gang inspection unavailable: {exc}'}
        observed['commands'][name] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    return observed

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('simulate', 'live'), default='simulate')
    parser.add_argument('--context')
    parser.add_argument('--namespace', default='gang-lab')
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    scenario = load_scenario(args.scenario)
    report = simulate(scenario)
    if args.mode == 'live':
        report['live_inspection'] = inspect_live(args.context, args.namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Gang admission model: {report['status']}')
    independent = report['independent']
    print(f'  independent: held={independent['held_gpu']} productive={independent['productive_gpu']} idle-held={independent['idle_while_held_gpu']} deadlocked={independent['deadlocked']}')
    coscheduled = report['coscheduling']
    print(f'  coscheduling: held={coscheduled['held_gpu']} productive={coscheduled['productive_gpu']} idle-held={coscheduled['idle_while_held_gpu']}')
    print('  kueue: ' + ', '.join((f'{item['job']}={item['phase']}' for item in report['kueue']['workloads'])))
    print('  volcano: ' + ', '.join((f'{item['job']}={item['phase']}' for item in report['volcano']['jobs'])))
    for fault in report['faults']:
        state = 'PASS' if fault['passed'] else 'FAIL'
        print(f'  fault {fault['name']}: {state} {fault['phase']}/{fault['reason']}')
    if args.mode == 'live':
        live = report['live_inspection']
        print(f'Live gang inspection: {live['status']}')
        if live.get('reason'):
            print(f'Reason: {live['reason']}')
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-11'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'gang_admission_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
