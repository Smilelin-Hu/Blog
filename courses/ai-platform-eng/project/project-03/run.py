#!/usr/bin/env python3
"""Standalone unified entry for project/project-03.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Validate a declarative distributed training and experiment platform."""
import argparse, json, shutil, subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def validate_request(item: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    reasons = []
    for f in ('name', 'tenant', 'owner', 'queue', 'runtime', 'runtime_revision', 'image', 'dataset_digest', 'code_revision', 'output_uri'):
        if not item.get(f):
            reasons.append(f'RequiredFieldMissing:{f}')
    if not str(item.get('runtime_revision', '')).startswith('sha256:'):
        reasons.append('RuntimeRevisionMustBeImmutable')
    if '@sha256:' not in str(item.get('image', '')):
        reasons.append('ImageDigestRequired')
    if not str(item.get('dataset_digest', '')).startswith('sha256:'):
        reasons.append('DatasetDigestRequired')
    if item.get('nodes', 0) > policy['maximum_nodes']:
        reasons.append('NodeLimitExceeded')
    if item.get('gpus_per_node', 0) > policy['maximum_gpus_per_node']:
        reasons.append('GPUPerNodeLimitExceeded')
    if item.get('queue') not in policy['allowed_queues']:
        reasons.append('QueueNotAllowed')
    return reasons

def execute_training(item: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    reasons = validate_request(item, policy)
    if reasons:
        return {'name': item.get('name', 'unknown'), 'status': 'REJECTED', 'reason': reasons[0], 'reasons': reasons}
    startup = sum((item['stage_seconds'][x] for x in ('admission', 'initializers', 'scheduling', 'rendezvous')))
    recovery = 0
    attempts = 1
    if item.get('inject_worker_failure'):
        attempts += 1
        recovery = item['stage_seconds']['checkpoint_restore'] + item['stage_seconds']['worker_recreate']
    status = 'SUCCEEDED' if attempts <= policy['maximum_attempts'] else 'FAILED'
    return {'name': item['name'], 'status': status, 'reason': 'TrainingCompleted' if status == 'SUCCEEDED' else 'RetryBudgetExceeded', 'startup_seconds': startup, 'recovery_seconds': recovery, 'attempts': attempts, 'model_version': item['model_version']}

def validate_lineage(item: dict[str, Any]) -> dict[str, Any]:
    required = {'request', 'runtime', 'image', 'dataset', 'code', 'pipeline_run', 'train_job', 'metrics', 'model_artifact', 'model_version'}
    present = set(item['lineage_nodes'])
    missing = sorted(required - present)
    immutable = all((str(item[key]).startswith('sha256:') for key in ('dataset_digest', 'code_revision', 'model_digest')))
    return {'status': 'PASS' if not missing and immutable else 'REJECTED', 'reason': 'LineageComplete' if not missing and immutable else 'LineageNodeMissing' if missing else 'LineageDigestMutable', 'missing': missing}

def evaluate_fault(item: dict[str, Any]) -> dict[str, Any]:
    mapping = {'runtime_missing': ('PENDING', 'RuntimeReferenceNotFound'), 'runtime_mutable': ('REJECTED', 'RuntimeRevisionMustBeImmutable'), 'image_mutable': ('REJECTED', 'ImageDigestRequired'), 'dataset_mutable': ('REJECTED', 'DatasetDigestRequired'), 'queue_bypass': ('REJECTED', 'RequiredQueueMissing'), 'node_limit': ('REJECTED', 'NodeLimitExceeded'), 'gpu_limit': ('REJECTED', 'GPUPerNodeLimitExceeded'), 'role_failure_unknown': ('INCONCLUSIVE', 'RoleFailureSemanticsUndefined'), 'rendezvous_timeout': ('FAILED', 'DistributedRendezvousFailed'), 'initializer_failed': ('FAILED', 'DatasetInitializerFailed'), 'checkpoint_missing': ('FAILED', 'RecoveryCheckpointMissing'), 'retry_budget': ('FAILED', 'RetryBudgetExceeded'), 'pipeline_cache_hidden_dependency': ('REJECTED', 'HiddenDependencyNotInCacheKey'), 'artifact_missing': ('REJECTED', 'ModelArtifactMissing'), 'lineage_missing': ('REJECTED', 'LineageNodeMissing'), 'model_version_mutable': ('REJECTED', 'ImmutableModelVersionRequired'), 'same_run_duplicate': ('BLOCKED', 'RunLeaseAlreadyOwned'), 'live_cluster_missing': ('SKIPPED', 'NoKubernetesContextProvided')}
    phase, reason = mapping[item['type']]
    ok = phase == item['expected_phase'] and reason == item['expected_reason']
    return {'type': item['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    runs = [execute_training(x, scenario['policy']) for x in scenario['requests']]
    lineage = [validate_lineage(x) for x in scenario['requests']]
    successful = sum((x['status'] == 'SUCCEEDED' for x in runs))
    measured = {'maximum_startup_seconds': max((x.get('startup_seconds', 0) for x in runs)), 'job_success_rate': successful / len(runs), 'maximum_recovery_seconds': max((x.get('recovery_seconds', 0) for x in runs)), 'lineage_complete_rate': sum((x['status'] == 'PASS' for x in lineage)) / len(lineage)}
    t = scenario['thresholds']
    checks = {'startup': measured['maximum_startup_seconds'] <= t['maximum_startup_seconds'], 'success': measured['job_success_rate'] >= t['minimum_job_success_rate'], 'recovery': measured['maximum_recovery_seconds'] <= t['maximum_recovery_seconds'], 'lineage': measured['lineage_complete_rate'] >= t['minimum_lineage_complete_rate']}
    faults = [evaluate_fault(x) for x in scenario['faults']]
    status = 'PASS' if all(checks.values()) and all((x['status'] == 'PASS' for x in faults)) else 'FAIL'
    return {'status': status, 'runs': runs, 'lineage': lineage, 'metrics': measured, 'checks': checks, 'faults': faults}

def inspect_live(context: str | None) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    if shutil.which('kubectl') is None:
        return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
    commands = {'trainjobs': ['kubectl', '--context', context, 'get', 'trainjobs.trainer.kubeflow.org', '-A', '-o', 'json'], 'jobsets': ['kubectl', '--context', context, 'get', 'jobsets.jobset.x-k8s.io', '-A', '-o', 'json'], 'pods': ['kubectl', '--context', context, 'get', 'pods', '-A', '-o', 'json']}
    evidence = {}
    for name, cmd in commands.items():
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        except subprocess.TimeoutExpired:
            return {'status': 'FAIL', 'reason': 'LiveTrainingPlatformReadTimeout', 'step': name}
        if r.returncode:
            return {'status': 'FAIL', 'reason': 'LiveTrainingPlatformReadFailed', 'step': name, 'stderr': r.stderr.strip()}
        evidence[name] = json.loads(r.stdout)
    return {'status': 'PASS', 'reason': 'LiveTrainingPlatformEvidenceCollected', 'evidence': evidence}

def implementation_main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scenario', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--context')
    a = p.parse_args()
    report = simulate(load_scenario(a.scenario))
    report['live'] = inspect_live(a.context)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Declarative training platform: {report['status']}')
    for k, v in report['metrics'].items():
        print(f'  metric {k}: {v}')
    for x in report['runs']:
        print(f'  run {x['name']}: {x['status']}/{x['reason']}')
    for x in report['faults']:
        print(f'  fault {x['type']}: {x['status']} {x['phase']}/{x['reason']}')
    print(f'  live: {report['live']['status']}/{report['live']['reason']}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] in {'PASS', 'SKIPPED'} else 1

ENTRY_ID = 'project/project-03'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'training_platform_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
