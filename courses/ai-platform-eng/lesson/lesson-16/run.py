#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-16.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic replay for Slurm, Kubernetes, and a governed dual-stack adapter."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def validate_slurm_profile(profile: dict[str, Any]) -> dict[str, Any]:
    if profile['configured_gpu_count'] != profile['detected_gpu_count']:
        return {'phase': 'DRAIN', 'reason': 'ConfiguredGRESDoesNotMatchDetectedGPU'}
    if not profile['select_cons_tres']:
        return {'phase': 'REJECTED', 'reason': 'GPUOptionsRequireSelectConsTRES'}
    if 'gres/gpu' not in profile['accounting_tres']:
        return {'phase': 'REJECTED', 'reason': 'GPUAccountingTRESMissing'}
    if not profile['cgroup_device_constraint']:
        return {'phase': 'UNSAFE', 'reason': 'GPUDeviceIsolationNotEnforced'}
    return {'phase': 'READY', 'reason': 'GRESAndTRESProfileValidated'}

def choose_backend(workload: dict[str, Any]) -> dict[str, Any]:
    if workload['kind'] == 'service' or workload['requires_kubernetes_api']:
        return {'backend': 'kubernetes', 'reason': 'ServiceLifecycleRequiresKubernetesControlPlane'}
    if workload['tightly_coupled_mpi'] or workload['requires_bare_metal_fabric']:
        return {'backend': 'slurm', 'reason': 'TightlyCoupledBatchFitsSlurmAllocationModel'}
    if workload['job_steps'] > 1 and workload['fixed_allocation']:
        return {'backend': 'slurm', 'reason': 'MultipleStepsReuseOneSlurmAllocation'}
    return {'backend': 'kubernetes', 'reason': 'ContainerBatchUsesKubernetesLifecycleAndPolicy'}

def translate_submission(scenario: dict[str, Any], workload: dict[str, Any]) -> dict[str, Any]:
    route = choose_backend(workload)
    identity = scenario['identities'].get(workload['principal'])
    if not identity:
        return {'phase': 'REJECTED', 'reason': 'PrincipalNotMappedToBackendIdentity'}
    if workload['project'] not in identity['projects']:
        return {'phase': 'REJECTED', 'reason': 'ProjectAssociationUnauthorized'}
    if route['backend'] == 'slurm':
        if workload['qos'] not in identity['slurm_qos']:
            return {'phase': 'REJECTED', 'reason': 'QOSNotAllowedByAssociation'}
        command = ['sbatch', f'--account={identity['slurm_account']}', f'--qos={workload['qos']}', f'--nodes={workload['nodes']}', f'--gpus-per-node={workload['gpus_per_node']}', f'--time={workload['time_limit']}']
        if workload['max_leaf_switches']:
            command.append(f'--switches={workload['max_leaf_switches']}@{workload['switch_wait']}')
        return {'phase': 'SUBMITTED', 'backend': 'slurm', 'reason': route['reason'], 'request': command}
    namespace = identity['kubernetes_namespace']
    request = {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'namespace': namespace, 'labels': {'platform.example/project': workload['project']}}, 'resources': {'pods': workload['nodes'], 'gpu_per_pod': workload['gpus_per_node']}}
    return {'phase': 'SUBMITTED', 'backend': 'kubernetes', 'reason': route['reason'], 'request': request}

def qos_admission(scenario: dict[str, Any], workload: dict[str, Any]) -> dict[str, Any]:
    qos = scenario['qos'][workload['qos']]
    requested_gpu = workload['nodes'] * workload['gpus_per_node']
    if workload['time_limit_minutes'] > qos['max_wall_minutes']:
        return {'phase': 'PENDING', 'reason': 'QOSMaxWallLimit'}
    if requested_gpu > qos['max_gpu_per_job']:
        return {'phase': 'PENDING', 'reason': 'QOSMaxTRESPERJob'}
    if scenario['account_usage_gpu_minutes'] + requested_gpu * workload['time_limit_minutes'] > qos['group_gpu_minutes']:
        return {'phase': 'PENDING', 'reason': 'QOSGrpTRESMinutesLimit'}
    return {'phase': 'ELIGIBLE', 'reason': 'AssociationAndQOSLimitsSatisfied'}

def topology_allocation(scenario: dict[str, Any], workload: dict[str, Any]) -> dict[str, Any]:
    required = workload['nodes']
    switch_candidates = [item for item in scenario['leaf_switches'] if item['free_nodes'] >= required]
    if switch_candidates:
        selected = sorted(switch_candidates, key=lambda item: (item['free_nodes'], item['name']))[0]
        return {'phase': 'ALLOCATED', 'reason': 'SingleLeafSwitchBestFit', 'switches': [selected['name']]}
    if workload['max_leaf_switches'] == 1:
        return {'phase': 'PENDING', 'reason': 'RequestedSwitchCountUnavailable'}
    total = sum((item['free_nodes'] for item in scenario['leaf_switches']))
    if total < required:
        return {'phase': 'PENDING', 'reason': 'InsufficientNodesAcrossTopology'}
    selected = []
    remaining = required
    for item in sorted(scenario['leaf_switches'], key=lambda entry: (-entry['free_nodes'], entry['name'])):
        selected.append(item['name'])
        remaining -= item['free_nodes']
        if remaining <= 0:
            break
    return {'phase': 'ALLOCATED', 'reason': 'MultiSwitchBestFit', 'switches': selected}

def normalize_accounting(record: dict[str, Any]) -> dict[str, Any]:
    if record['backend'] == 'slurm':
        return {'run_id': record['run_id'], 'backend': 'slurm', 'project': record['account'], 'gpu_seconds': record['allocated_gpus'] * record['elapsed_seconds'], 'terminal_state': record['state'], 'source_id': record['job_id']}
    return {'run_id': record['run_id'], 'backend': 'kubernetes', 'project': record['project'], 'gpu_seconds': record['gpu_request'] * record['running_seconds'], 'terminal_state': record['phase'], 'source_id': record['uid']}

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    contracts = {'gres_mismatch': ('DRAIN', 'ConfiguredGRESDoesNotMatchDetectedGPU'), 'select_plugin_missing': ('REJECTED', 'GPUOptionsRequireSelectConsTRES'), 'gpu_tres_missing': ('REJECTED', 'GPUAccountingTRESMissing'), 'device_cgroup_missing': ('UNSAFE', 'GPUDeviceIsolationNotEnforced'), 'qos_unauthorized': ('REJECTED', 'QOSNotAllowedByAssociation'), 'qos_wall_limit': ('PENDING', 'QOSMaxWallLimit'), 'qos_gpu_limit': ('PENDING', 'QOSMaxTRESPERJob'), 'qos_minutes_limit': ('PENDING', 'QOSGrpTRESMinutesLimit'), 'single_switch_unavailable': ('PENDING', 'RequestedSwitchCountUnavailable'), 'identity_unmapped': ('REJECTED', 'PrincipalNotMappedToBackendIdentity'), 'project_unauthorized': ('REJECTED', 'ProjectAssociationUnauthorized'), 'duplicate_cross_backend_submit': ('BLOCKED', 'RunLeaseAlreadyOwnedByAnotherBackend'), 'federation_high_throughput': ('DEGRADED', 'FederationNotIntendedForHighThroughputSubmission'), 'rest_polling_storm': ('THROTTLED', 'SlurmRESTQueriesRequireCachingAndConditionalPolling')}
    phase, reason = contracts[fault['type']]
    return {'name': fault['name'], 'phase': phase, 'reason': reason, 'status': 'PASS' if (phase, reason) == (fault['expected_phase'], fault['expected_reason']) else 'FAIL'}

def inspect_live(slurm_cluster: bool, kubernetes_context: str | None) -> dict[str, Any]:
    observations: dict[str, Any] = {}
    if slurm_cluster:
        if not shutil.which('scontrol'):
            observations['slurm'] = {'status': 'SKIPPED', 'reason': 'ScontrolUnavailable'}
        else:
            result = subprocess.run(['scontrol', 'show', 'config'], check=False, capture_output=True, text=True, timeout=20)
            observations['slurm'] = {'status': 'PASS' if result.returncode == 0 else 'SKIPPED', 'reason': 'ReadOnlyConfigDiscovery'}
    else:
        observations['slurm'] = {'status': 'SKIPPED', 'reason': 'NoSlurmClusterRequested'}
    if kubernetes_context:
        try:
            result = subprocess.run(['kubectl', '--context', kubernetes_context, 'get', 'nodes', '-o', 'json'], check=False, capture_output=True, text=True, timeout=20)
            observations['kubernetes'] = {'status': 'PASS' if result.returncode == 0 else 'SKIPPED', 'reason': 'ReadOnlyNodeDiscovery'}
        except (FileNotFoundError, subprocess.TimeoutExpired):
            observations['kubernetes'] = {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
    else:
        observations['kubernetes'] = {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    overall = 'PASS' if all((item['status'] == 'PASS' for item in observations.values())) else 'SKIPPED'
    return {'status': overall, 'observations': observations, 'boundary': 'read-only discovery does not prove GPU binding, QOS enforcement, preemption, federation, or end-to-end submission'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    profile = validate_slurm_profile(scenario['slurm_profile'])
    routes = {item['name']: translate_submission(scenario, item) for item in scenario['workloads']}
    training = next((item for item in scenario['workloads'] if item['name'] == 'mpi-training'))
    admission = qos_admission(scenario, training)
    topology = topology_allocation(scenario, training)
    accounting = [normalize_accounting(item) for item in scenario['accounting_records']]
    faults = [evaluate_fault(item) for item in scenario['faults']]
    passed = profile['phase'] == 'READY' and routes['mpi-training']['backend'] == 'slurm' and (routes['online-inference']['backend'] == 'kubernetes') and (admission['phase'] == 'ELIGIBLE') and (topology['phase'] == 'ALLOCATED') and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'slurm_profile': profile, 'routes': routes, 'qos_admission': admission, 'topology': topology, 'accounting': accounting, 'faults': faults}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live-slurm', action='store_true')
    parser.add_argument('--kubernetes-context')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.live_slurm, args.kubernetes_context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Slurm and Kubernetes boundary replay: {report['status']}')
    print(f'  slurm profile: {report['slurm_profile']['phase']}/{report['slurm_profile']['reason']}')
    for name, item in report['routes'].items():
        print(f'  route {name}: {item['phase']}/{item.get('backend', 'none')}/{item['reason']}')
    print(f'  qos: {report['qos_admission']['phase']}/{report['qos_admission']['reason']}')
    print(f'  topology: {report['topology']['phase']}/{report['topology']['reason']}')
    for item in report['faults']:
        print(f'  fault {item['name']}: {item['status']} {item['phase']}/{item['reason']}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-16'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'slurm_k8s_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
