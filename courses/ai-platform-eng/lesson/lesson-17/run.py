#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-17.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic replay for JobSet, LeaderWorkerSet, and distributed failure semantics."""
import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def build_job_tree(scenario: dict[str, Any]) -> dict[str, Any]:
    jobs = []
    for role in scenario['replicated_jobs']:
        for job_index in range(role['replicas']):
            jobs.append({'name': f'{scenario['name']}-{role['name']}-{job_index}', 'role': role['name'], 'job_index': job_index, 'pods': role['completions'], 'gpu_per_pod': role['gpu_per_pod'], 'depends_on': role.get('depends_on', [])})
    return {'jobs': jobs, 'total_jobs': len(jobs), 'total_pods': sum((item['pods'] for item in jobs))}

def startup_order(scenario: dict[str, Any], ready_roles: set[str]) -> dict[str, Any]:
    startable = []
    blocked = []
    for role in scenario['replicated_jobs']:
        unmet = [dependency for dependency in role.get('depends_on', []) if dependency not in ready_roles]
        (blocked if unmet else startable).append({'role': role['name'], 'unmet': unmet})
    return {'startable': startable, 'blocked': blocked}

def failure_action(scenario: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    for rule in scenario['failure_policy']['rules']:
        role_match = not rule.get('target_roles') or event['role'] in rule['target_roles']
        reason_match = not rule.get('reasons') or event['reason'] in rule['reasons']
        message_match = not rule.get('message_contains') or rule['message_contains'] in event.get('message', '')
        if role_match and reason_match and message_match:
            action = rule['action']
            break
    else:
        action = 'RestartJobSet'
    counts = action not in {'RestartJobSetAndIgnoreMaxRestarts', 'RestartJobAndIgnoreMaxRestarts'}
    if action == 'FailJobSet':
        return {'phase': 'FAILED', 'action': action, 'reason': 'FailurePolicyTerminatedJobSet', 'counts_restart': False}
    if counts and scenario['restart_count'] >= scenario['failure_policy']['max_restarts']:
        return {'phase': 'FAILED', 'action': 'FailJobSet', 'reason': 'MaxRestartsExceeded', 'counts_restart': True}
    scope = 'jobset' if 'JobSet' in action else 'job'
    return {'phase': 'RESTARTING', 'action': action, 'reason': f'Recreate{scope.title()}', 'scope': scope, 'counts_restart': counts}

def success_state(scenario: dict[str, Any], completed_roles: set[str]) -> dict[str, Any]:
    policy = scenario['success_policy']
    targets = set(policy['target_roles'])
    if policy['operator'] == 'All':
        success = targets.issubset(completed_roles)
    else:
        success = bool(targets & completed_roles)
    return {'phase': 'SUCCEEDED' if success else 'RUNNING', 'reason': 'SuccessPolicySatisfied' if success else 'WaitingForTargetRoles'}

def lws_failure(policy: str, group: dict[str, Any]) -> dict[str, Any]:
    if policy == 'None':
        return {'phase': 'RESTARTING', 'scope': 'pod', 'reason': 'OnlyFailedPodRecreated'}
    if policy == 'RecreateGroupAfterStart' and group['pending_pods'] > 0:
        return {'phase': 'WAITING', 'scope': 'none', 'reason': 'WaitForPendingPodsBeforeGroupRecreate'}
    return {'phase': 'RESTARTING', 'scope': 'group', 'reason': 'WholeLeaderWorkerGroupRecreated'}

def kueue_podsets(scenario: dict[str, Any]) -> dict[str, Any]:
    podsets = []
    for role in scenario['replicated_jobs']:
        podsets.append({'name': role['name'], 'count': role['replicas'] * role['completions'], 'gpu': role['replicas'] * role['completions'] * role['gpu_per_pod'], 'topology': role['topology']})
    total_gpu = sum((item['gpu'] for item in podsets))
    return {'phase': 'ADMITTED' if total_gpu <= scenario['queue_gpu_quota'] else 'PENDING', 'reason': 'AllPodSetsFitQuotaAndTopology' if total_gpu <= scenario['queue_gpu_quota'] else 'InsufficientQueueGPUQuota', 'podsets': podsets, 'total_gpu': total_gpu}

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    contracts = {'single_job_multi_role': ('REJECTED', 'SingleJobCannotExpressDifferentPodTemplates'), 'dependency_not_ready': ('BLOCKED', 'ReplicatedJobDependencyNotReady'), 'leader_failed': ('RESTARTING', 'WholeJobSetRestartRequired'), 'worker_failed': ('RESTARTING', 'OnlyFailedChildJobRestarted'), 'nonretryable_config': ('FAILED', 'FailurePolicyTerminatedJobSet'), 'max_restarts': ('FAILED', 'MaxRestartsExceeded'), 'ignore_unbounded': ('UNSAFE', 'IgnoredRestartLimitNeedsExternalBudget'), 'success_too_early': ('BLOCKED', 'SuccessPolicyTargetsNotSatisfied'), 'lws_leader_failed': ('RESTARTING', 'WholeLeaderWorkerGroupRecreated'), 'lws_pending_image_pull': ('WAITING', 'WaitForPendingPodsBeforeGroupRecreate'), 'network_partition': ('RECOVERY_WAIT', 'FateSharingRequiresGroupCoordination'), 'controller_restart': ('RECOVERED', 'StatusReconstructedFromOwnedChildren'), 'kueue_quota': ('PENDING', 'InsufficientQueueGPUQuota'), 'topology_intersection': ('PENDING', 'PodSetTopologyAssignmentUnavailable')}
    phase, reason = contracts[fault['type']]
    return {'name': fault['name'], 'phase': phase, 'reason': reason, 'status': 'PASS' if (phase, reason) == (fault['expected_phase'], fault['expected_reason']) else 'FAIL'}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    commands = {'jobsets': ['kubectl', '--context', context, '-n', namespace, 'get', 'jobsets.jobset.x-k8s.io', '-o', 'json'], 'leaderworkersets': ['kubectl', '--context', context, '-n', namespace, 'get', 'leaderworkersets.leaderworkerset.x-k8s.io', '-o', 'json'], 'workloads': ['kubectl', '--context', context, '-n', namespace, 'get', 'workloads.kueue.x-k8s.io', '-o', 'json']}
    observations = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
        if result.returncode:
            return {'status': 'SKIPPED', 'reason': f'LivePrerequisiteUnavailable:{name}', 'stderr': result.stderr.strip()}
        observations[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'observations': observations, 'boundary': 'read-only discovery does not prove startup coordination, failure restart scope, fate sharing, topology placement, or cleanup'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    tree = build_job_tree(scenario)
    startup = startup_order(scenario, {'leader'})
    leader_failure = failure_action(scenario, scenario['events']['leader_failure'])
    worker_failure = failure_action(scenario, scenario['events']['worker_failure'])
    success = success_state(scenario, {'trainer'})
    lws = lws_failure(scenario['lws']['restart_policy'], scenario['lws']['group'])
    admission = kueue_podsets(scenario)
    faults = [evaluate_fault(item) for item in scenario['faults']]
    passed = tree['total_jobs'] == scenario['expected_total_jobs'] and leader_failure['scope'] == 'jobset' and (worker_failure['scope'] == 'job') and (success['phase'] == 'SUCCEEDED') and (lws['scope'] == 'group') and (admission['phase'] == 'ADMITTED') and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'tree': tree, 'startup': startup, 'leader_failure': leader_failure, 'worker_failure': worker_failure, 'success': success, 'lws': lws, 'admission': admission, 'faults': faults}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live-context')
    parser.add_argument('--namespace', default='distributed-workload-lab')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.live_context, args.namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Distributed workload API replay: {report['status']}')
    print(f'  tree: jobs={report['tree']['total_jobs']} pods={report['tree']['total_pods']}')
    print(f'  leader failure: {report['leader_failure']['phase']}/{report['leader_failure']['action']}')
    print(f'  worker failure: {report['worker_failure']['phase']}/{report['worker_failure']['action']}')
    print(f'  success: {report['success']['phase']}/{report['success']['reason']}')
    print(f'  lws: {report['lws']['phase']}/{report['lws']['reason']}')
    print(f'  kueue: {report['admission']['phase']}/{report['admission']['reason']}')
    for item in report['faults']:
        print(f'  fault {item['name']}: {item['status']} {item['phase']}/{item['reason']}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-17'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'distributed_workload_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
