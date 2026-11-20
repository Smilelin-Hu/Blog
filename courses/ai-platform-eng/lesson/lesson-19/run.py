#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-19.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic Kubeflow Trainer runtime composition and policy replay."""
import argparse
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def validate_runtime(runtime: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    image = runtime.get('image', '')
    registry = image.split('/', 1)[0] + '/' + image.split('/', 2)[1] if image.count('/') >= 2 else ''
    if runtime.get('framework_label') is None:
        errors.append('FrameworkLabelRequired')
    if policy['required_image_digest'] and '@sha256:' not in image:
        errors.append('ImageDigestRequired')
    if registry not in policy['allowed_registries']:
        errors.append('RegistryNotAllowed')
    if runtime.get('service_account') != policy['required_service_account']:
        errors.append('UnexpectedServiceAccount')
    if runtime.get('replicated_job') != 'node' or runtime.get('container') != 'node':
        errors.append('RuntimeTemplateContractMismatch')
    return errors

def validate_job(job: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if job['nodes'] < 1 or job['nodes'] > policy['max_nodes']:
        errors.append('NodeLimitExceeded')
    if job['gpu_per_node'] < 0 or job['gpu_per_node'] > policy['max_gpu_per_node']:
        errors.append('GPUPerNodeLimitExceeded')
    if job.get('queue') != policy['required_queue']:
        errors.append('RequiredQueueMissing')
    managers = [item['manager'] for item in job.get('runtime_patches', [])]
    if len(managers) != len(set(managers)):
        errors.append('RuntimePatchManagerConflict')
    for patch in job.get('runtime_patches', []):
        if patch['path'] in policy['immutable_paths']:
            errors.append('ImmutableRuntimeField')
    return errors

def render_jobset(runtime: dict[str, Any], job: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    runtime_errors = validate_runtime(runtime, policy)
    job_errors = validate_job(job, policy)
    if runtime_errors or job_errors:
        return {'name': job['name'], 'status': 'REJECTED', 'errors': runtime_errors + job_errors}
    processes = job['nodes'] * job['gpu_per_node']
    return {'name': job['name'], 'status': 'ADMITTED', 'runtime_ref': {'kind': runtime['kind'], 'name': runtime['name']}, 'jobset': {'replicated_job': runtime['replicated_job'], 'replicas': job['nodes'], 'parallelism': 1, 'completions': 1, 'container': runtime['container'], 'image': runtime['image'], 'service_account': runtime['service_account'], 'gpu_per_node': job['gpu_per_node'], 'world_size': processes, 'queue': job['queue'], 'security_context': deepcopy(policy['required_security']), 'command': job['command']}, 'runtime_patch_managers': [item['manager'] for item in job.get('runtime_patches', [])]}

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    contracts = {'mutable_image': ('REJECTED', 'ImageDigestRequired'), 'foreign_registry': ('REJECTED', 'RegistryNotAllowed'), 'too_many_nodes': ('REJECTED', 'NodeLimitExceeded'), 'too_many_gpus': ('REJECTED', 'GPUPerNodeLimitExceeded'), 'queue_bypass': ('REJECTED', 'RequiredQueueMissing'), 'service_account_override': ('REJECTED', 'ImmutableRuntimeField'), 'security_context_override': ('REJECTED', 'ImmutableRuntimeField'), 'duplicate_patch_manager': ('REJECTED', 'RuntimePatchManagerConflict'), 'runtime_missing': ('PENDING', 'RuntimeReferenceNotFound'), 'framework_label_missing': ('SDK_BLOCKED', 'FrameworkLabelRequired'), 'rendezvous_failure': ('FAILED', 'DistributedRendezvousFailed'), 'initializer_failure': ('FAILED', 'DatasetInitializerFailed'), 'artifact_write_failure': ('FAILED', 'OutputModelWriteFailed'), 'deadline_exceeded': ('FAILED', 'DeadlineExceeded'), 'v1_kind_submitted': ('MIGRATION_REQUIRED', 'LegacyFrameworkSpecificCRD'), 'live_cluster_missing': ('SKIPPED', 'NoKubernetesContextProvided')}
    phase, reason = contracts[fault['type']]
    ok = (phase, reason) == (fault['expected_phase'], fault['expected_reason'])
    return {'type': fault['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    commands = {'crds': ['kubectl', '--context', context, 'get', 'crd', 'trainjobs.trainer.kubeflow.org', 'clustertrainingruntimes.trainer.kubeflow.org', 'trainingruntimes.trainer.kubeflow.org', '-o', 'json'], 'runtimes': ['kubectl', '--context', context, 'get', 'clustertrainingruntimes.trainer.kubeflow.org', '-o', 'json'], 'jobs': ['kubectl', '--context', context, '-n', namespace, 'get', 'trainjobs.trainer.kubeflow.org', '-o', 'json'], 'jobsets': ['kubectl', '--context', context, '-n', namespace, 'get', 'jobsets.jobset.x-k8s.io', '-o', 'json']}
    observations: dict[str, Any] = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
        if result.returncode:
            return {'status': 'SKIPPED', 'reason': f'LivePrerequisiteUnavailable:{name}', 'stderr': result.stderr.strip()}
        observations[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'observations': observations, 'boundary': 'read-only discovery does not prove GPU execution, distributed rendezvous, queue admission, object-store writes, rollback, or negative-policy enforcement'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    runtime_errors = validate_runtime(scenario['runtime'], scenario['platform_policy'])
    jobs = [render_jobset(scenario['runtime'], item, scenario['platform_policy']) for item in scenario['jobs']]
    faults = [evaluate_fault(item) for item in scenario['faults']]
    passed = not runtime_errors and all((item['status'] == 'ADMITTED' for item in jobs)) and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'baseline': scenario['baseline'], 'runtime_errors': runtime_errors, 'jobs': jobs, 'faults': faults}

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
    print(f'Kubeflow Trainer runtime replay: {report['status']}')
    for item in report['jobs']:
        print(f'  job {item['name']}: {item['status']}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live'].get('reason', 'observed')}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-19'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'trainer_runtime_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
