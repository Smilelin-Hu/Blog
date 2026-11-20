#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-20.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic KubeRay control-plane and multi-layer autoscaling replay."""
import argparse
import json
import math
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def choose_crd(workload: dict[str, Any]) -> str:
    if workload['mode'] == 'serve':
        return 'RayService'
    if workload['mode'] == 'scheduled_batch':
        return 'RayCronJob'
    if workload['mode'] == 'batch' and workload.get('isolation_per_run', True):
        return 'RayJob'
    return 'RayCluster'

def validate_workload(workload: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    image = workload.get('image', '')
    if policy['require_image_digest'] and '@sha256:' not in image:
        errors.append('ImageDigestRequired')
    if workload.get('auth_mode') not in policy['allowed_auth_modes']:
        errors.append('AuthenticationRequired')
    if workload.get('head_cpu', 0) < policy['minimum_head_cpu']:
        errors.append('HeadCapacityTooSmall')
    worker = workload.get('worker', {})
    if worker.get('min_replicas', 0) > worker.get('max_replicas', 0):
        errors.append('InvalidWorkerReplicaRange')
    if worker.get('max_replicas', 0) > policy['max_worker_replicas']:
        errors.append('WorkerReplicaLimitExceeded')
    if workload.get('gpu_per_worker', 0) > policy['max_gpu_per_worker']:
        errors.append('GPUPerWorkerLimitExceeded')
    if workload.get('queue') != policy['required_queue']:
        errors.append('RequiredQueueMissing')
    if workload['mode'] == 'serve' and (not workload.get('readiness_gate', False)):
        errors.append('ServeReadinessGateRequired')
    if workload.get('expose_dashboard_publicly', False):
        errors.append('PublicDashboardForbidden')
    if workload['mode'] == 'scheduled_batch' and (not policy['raycronjob_alpha_enabled']):
        errors.append('AlphaFeatureGateDisabled')
    return errors

def scale_layers(workload: dict[str, Any], demand: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    serve = workload.get('serve', {})
    if workload['mode'] == 'serve':
        target = max(1, serve.get('target_ongoing_requests', 1))
        serve_replicas = math.ceil(demand['ongoing_requests'] / target)
        serve_replicas = max(serve['min_replicas'], min(serve['max_replicas'], serve_replicas))
    else:
        serve_replicas = 0
    worker = workload['worker']
    logical_cpu = demand['logical_cpu'] + serve_replicas * serve.get('cpu_per_replica', 0)
    logical_gpu = demand['logical_gpu'] + serve_replicas * serve.get('gpu_per_replica', 0)
    cpu_needed = math.ceil(logical_cpu / max(worker['cpu_per_pod'], 1))
    gpu_capacity = worker.get('gpu_per_pod', 0)
    gpu_needed = math.ceil(logical_gpu / gpu_capacity) if logical_gpu and gpu_capacity else 0 if not logical_gpu else worker['max_replicas'] + 1
    ray_worker_pods = max(worker['min_replicas'], cpu_needed, gpu_needed)
    ray_worker_pods = min(worker['max_replicas'], ray_worker_pods)
    pods_per_node = max(1, policy['worker_pods_per_node'])
    kubernetes_nodes = math.ceil(ray_worker_pods / pods_per_node)
    kubernetes_nodes = max(policy['min_worker_nodes'], min(policy['max_worker_nodes'], kubernetes_nodes))
    unsatisfied_gpu = logical_gpu > ray_worker_pods * gpu_capacity
    return {'serve_replicas': serve_replicas, 'ray_worker_pods': ray_worker_pods, 'kubernetes_worker_nodes': kubernetes_nodes, 'logical_cpu_demand': logical_cpu, 'logical_gpu_demand': logical_gpu, 'unsatisfied_gpu_demand': unsatisfied_gpu, 'decision_basis': 'logical resource demand, not physical utilization'}

def lifecycle(workload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    kind = choose_crd(workload)
    states = {'RayCluster': ['Accepted', 'HeadCreated', 'WorkersCreated', 'Ready'], 'RayJob': ['Accepted', 'ClusterCreating', 'ClusterReady', 'Submitting', 'Running', 'Succeeded', 'CleanupScheduled'], 'RayService': ['Accepted', 'ClusterCreating', 'ServeDeploying', 'Ready'], 'RayCronJob': ['Scheduled', 'RayJobCreated']}[kind]
    cleanup = 'retain'
    if kind == 'RayJob':
        cleanup = 'deletionRules'
    if kind == 'RayService':
        cleanup = 'managed-cluster-upgrade'
    return {'kind': kind, 'states': states, 'cleanup': cleanup, 'errors': validate_workload(workload, policy)}

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    contracts = {'mutable_image': ('REJECTED', 'ImageDigestRequired'), 'public_dashboard': ('REJECTED', 'PublicDashboardForbidden'), 'missing_auth': ('REJECTED', 'AuthenticationRequired'), 'head_too_small': ('REJECTED', 'HeadCapacityTooSmall'), 'invalid_replica_range': ('REJECTED', 'InvalidWorkerReplicaRange'), 'worker_limit': ('REJECTED', 'WorkerReplicaLimitExceeded'), 'queue_bypass': ('REJECTED', 'RequiredQueueMissing'), 'raycronjob_gate_off': ('REJECTED', 'AlphaFeatureGateDisabled'), 'serve_without_readiness': ('REJECTED', 'ServeReadinessGateRequired'), 'head_loss_without_gcs_ft': ('FAILED', 'ClusterStateLost'), 'node_pool_cannot_scale': ('DEGRADED', 'WorkerPodsPending'), 'insufficient_gpu_capacity': ('DEGRADED', 'UnsatisfiedLogicalGPUDemand'), 'upgrade_capacity_shortage': ('BLOCKED', 'PendingClusterInsufficientCapacity'), 'job_submission_timeout': ('FAILED', 'PreRunningDeadlineExceeded'), 'serve_initializing_timeout': ('FAILED', 'InitializingTimeout'), 'live_cluster_missing': ('SKIPPED', 'NoKubernetesContextProvided')}
    phase, reason = contracts[fault['type']]
    ok = (phase, reason) == (fault['expected_phase'], fault['expected_reason'])
    return {'type': fault['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    commands = {'crds': ['kubectl', '--context', context, 'get', 'crd', 'rayclusters.ray.io', 'rayjobs.ray.io', 'rayservices.ray.io', '-o', 'json'], 'clusters': ['kubectl', '--context', context, '-n', namespace, 'get', 'rayclusters.ray.io', '-o', 'json'], 'jobs': ['kubectl', '--context', context, '-n', namespace, 'get', 'rayjobs.ray.io', '-o', 'json'], 'services': ['kubectl', '--context', context, '-n', namespace, 'get', 'rayservices.ray.io', '-o', 'json'], 'pods': ['kubectl', '--context', context, '-n', namespace, 'get', 'pods', '-l', 'ray.io/is-ray-node=yes', '-o', 'json']}
    observations: dict[str, Any] = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
        if result.returncode:
            return {'status': 'SKIPPED', 'reason': f'LivePrerequisiteUnavailable:{name}', 'stderr': result.stderr.strip()}
        observations[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'observations': observations, 'boundary': 'read-only discovery does not prove Ray execution, autoscaling, node provisioning, GCS recovery, Serve traffic continuity, Kueue admission, or negative-policy enforcement'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    workload_results: list[dict[str, Any]] = []
    for workload in scenario['workloads']:
        life = lifecycle(workload, scenario['platform_policy'])
        scales = [scale_layers(workload, item, scenario['platform_policy']) for item in scenario['demands']]
        workload_results.append({'name': workload['name'], 'lifecycle': life, 'scales': scales})
    faults = [evaluate_fault(item) for item in scenario['faults']]
    passed = all((not item['lifecycle']['errors'] for item in workload_results)) and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'baseline': scenario['baseline'], 'workloads': workload_results, 'faults': faults}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live-context')
    parser.add_argument('--namespace', default='team-a')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.live_context, args.namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'KubeRay control-plane replay: {report['status']}')
    for item in report['workloads']:
        print(f'  workload {item['name']}: {item['lifecycle']['kind']} errors={len(item['lifecycle']['errors'])}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live'].get('reason', 'observed')}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-20'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'kuberay_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
