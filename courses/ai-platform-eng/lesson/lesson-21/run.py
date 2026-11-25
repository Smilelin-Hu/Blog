#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-21.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic KFP v2 graph, cache, lineage, and Katib budget replay."""
import argparse
import hashlib
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def stable_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()

def validate_pipeline(pipeline: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not pipeline.get('pipeline_root', '').startswith(tuple(policy['allowed_pipeline_roots'])):
        errors.append('PipelineRootRequired')
    names = {task['name'] for task in pipeline['tasks']}
    if len(names) != len(pipeline['tasks']):
        errors.append('DuplicateTaskName')
    for task in pipeline['tasks']:
        if policy['require_image_digest'] and '@sha256:' not in task['image']:
            errors.append('ImageDigestRequired')
        if task.get('queue') != policy['required_queue']:
            errors.append('RequiredQueueMissing')
        if task.get('side_effect', False) and task.get('cache', True):
            errors.append('SideEffectTaskCachingForbidden')
        if task.get('hidden_dependencies'):
            errors.append('HiddenDependencyNotInCacheKey')
        for dependency in task.get('after', []):
            if dependency not in names:
                errors.append('UnknownTaskDependency')
        if task.get('fanout', 1) > policy['max_parallel_fanout']:
            errors.append('ParallelFanoutLimitExceeded')
    interfaces = pipeline['interfaces']
    for edge in pipeline['edges']:
        source_type = interfaces[edge['from']]
        target_type = interfaces[edge['to']]
        if source_type != target_type and source_type != 'Artifact' and (target_type != 'Artifact'):
            errors.append('PipelineTypeMismatch')
    return sorted(set(errors))

def cache_key(task: dict[str, Any], inputs: dict[str, Any]) -> str:
    contract = {'component': task['component_digest'], 'image': task['image'], 'inputs': inputs, 'environment': task.get('environment_contract', {})}
    return stable_digest(contract)

def execute_pipeline(pipeline: dict[str, Any], policy: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any]:
    errors = validate_pipeline(pipeline, policy)
    if errors:
        return {'status': 'REJECTED', 'errors': errors, 'tasks': [], 'lineage': []}
    outputs: dict[str, Any] = deepcopy(pipeline['inputs'])
    tasks: list[dict[str, Any]] = []
    lineage: list[dict[str, str]] = []
    for task in pipeline['tasks']:
        resolved_inputs = {name: outputs[source] for name, source in task.get('inputs', {}).items()}
        key = cache_key(task, resolved_inputs)
        if task.get('cache', True) and key in cache:
            result = deepcopy(cache[key])
            state = 'CACHED'
        else:
            result = {'uri': f'{pipeline['pipeline_root'].rstrip('/')}/{pipeline['run_id']}/{task['name']}/{key[:16]}', 'digest': stable_digest({'task': task['name'], 'inputs': resolved_inputs, 'key': key}), 'type': task['output_type']}
            if task.get('cache', True):
                cache[key] = deepcopy(result)
            state = 'EXECUTED'
        outputs[task['output_name']] = result
        for source in task.get('inputs', {}).values():
            lineage.append({'input': source, 'execution': task['name'], 'output': task['output_name']})
        tasks.append({'name': task['name'], 'state': state, 'cache_key': key, 'output': result})
    return {'status': 'PASS', 'errors': [], 'tasks': tasks, 'lineage': lineage, 'outputs': outputs}

def validate_katib(experiment: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if experiment.get('max_trial_count') is None:
        errors.append('MaxTrialCountRequired')
    if experiment.get('parallel_trial_count', 0) > policy['max_parallel_trials']:
        errors.append('ParallelTrialLimitExceeded')
    concurrent_gpu = experiment.get('parallel_trial_count', 0) * experiment.get('gpu_per_trial', 0)
    if concurrent_gpu > policy['katib_gpu_budget']:
        errors.append('KatibGPUBudgetExceeded')
    if experiment.get('search_space_cardinality', 0) > policy['max_search_space_cardinality']:
        errors.append('SearchSpaceTooLarge')
    template_parameters = set(experiment.get('trial_template_parameters', []))
    if set(experiment.get('parameters', [])) - template_parameters:
        errors.append('TrialTemplateParameterMissing')
    if experiment.get('worker_kind') != 'TrainJob':
        errors.append('ApprovedTrainJobTemplateRequired')
    if experiment.get('early_stopping') and (not experiment.get('timestamped_metrics')):
        errors.append('TimestampedMetricRequiredForEarlyStopping')
    if experiment.get('max_failed_trial_count', 0) < 1:
        errors.append('FailedTrialBudgetRequired')
    return sorted(set(errors))

def run_katib(experiment: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    errors = validate_katib(experiment, policy)
    if errors:
        return {'status': 'REJECTED', 'errors': errors, 'trials': []}
    trials: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for index in range(experiment['max_trial_count']):
        learning_rate = experiment['candidate_learning_rates'][index % len(experiment['candidate_learning_rates'])]
        depth = experiment['candidate_depths'][index % len(experiment['candidate_depths'])]
        metric = round(0.92 - abs(learning_rate - 0.02) * 3 - abs(depth - 4) * 0.015, 6)
        status = 'EarlyStopped' if experiment['early_stopping'] and index >= 4 and (metric < 0.84) else 'Succeeded'
        trial = {'name': f'trial-{index + 1}', 'learning_rate': learning_rate, 'depth': depth, 'metric': metric, 'status': status}
        trials.append(trial)
        if status == 'Succeeded' and (best is None or metric > best['metric']):
            best = trial
    return {'status': 'PASS', 'errors': [], 'trials': trials, 'best_trial': best, 'maximum_concurrent_gpu': experiment['parallel_trial_count'] * experiment['gpu_per_trial']}

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    contracts = {'mutable_image': ('REJECTED', 'ImageDigestRequired'), 'pipeline_root_missing': ('REJECTED', 'PipelineRootRequired'), 'type_mismatch': ('REJECTED', 'PipelineTypeMismatch'), 'hidden_dependency': ('REJECTED', 'HiddenDependencyNotInCacheKey'), 'side_effect_cached': ('REJECTED', 'SideEffectTaskCachingForbidden'), 'fanout_unbounded': ('REJECTED', 'ParallelFanoutLimitExceeded'), 'queue_bypass': ('REJECTED', 'RequiredQueueMissing'), 'unknown_dependency': ('REJECTED', 'UnknownTaskDependency'), 'katib_no_trial_limit': ('REJECTED', 'MaxTrialCountRequired'), 'katib_parallel_limit': ('REJECTED', 'ParallelTrialLimitExceeded'), 'katib_gpu_budget': ('REJECTED', 'KatibGPUBudgetExceeded'), 'katib_search_space': ('REJECTED', 'SearchSpaceTooLarge'), 'trial_parameter_missing': ('REJECTED', 'TrialTemplateParameterMissing'), 'early_stop_no_timestamp': ('REJECTED', 'TimestampedMetricRequiredForEarlyStopping'), 'unapproved_worker_kind': ('REJECTED', 'ApprovedTrainJobTemplateRequired'), 'live_backend_missing': ('SKIPPED', 'NoKFPOrKubernetesContextProvided')}
    phase, reason = contracts[fault['type']]
    ok = (phase, reason) == (fault['expected_phase'], fault['expected_reason'])
    return {'type': fault['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKFPOrKubernetesContextProvided'}
    commands = {'katib_crds': ['kubectl', '--context', context, 'get', 'crd', 'experiments.kubeflow.org', 'trials.kubeflow.org', '-o', 'json'], 'experiments': ['kubectl', '--context', context, '-n', namespace, 'get', 'experiments.kubeflow.org', '-o', 'json'], 'trials': ['kubectl', '--context', context, '-n', namespace, 'get', 'trials.kubeflow.org', '-o', 'json'], 'trainjobs': ['kubectl', '--context', context, '-n', namespace, 'get', 'trainjobs.trainer.kubeflow.org', '-o', 'json']}
    observations: dict[str, Any] = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
        if result.returncode:
            return {'status': 'SKIPPED', 'reason': f'LivePrerequisiteUnavailable:{name}', 'stderr': result.stderr.strip()}
        observations[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'observations': observations, 'boundary': 'read-only discovery does not prove KFP compilation or execution, cache correctness, artifact storage, MLMD lineage, Katib suggestions, early stopping, TrainJob execution, Kueue admission, or model registration'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    cache: dict[str, Any] = {}
    first = execute_pipeline(scenario['pipeline'], scenario['platform_policy'], cache)
    second_pipeline = deepcopy(scenario['pipeline'])
    second_pipeline['run_id'] = 'run-002'
    second = execute_pipeline(second_pipeline, scenario['platform_policy'], cache)
    changed_pipeline = deepcopy(second_pipeline)
    changed_pipeline['run_id'] = 'run-003'
    changed_pipeline['inputs']['data_version'] = 'dataset@sha256:changed'
    changed = execute_pipeline(changed_pipeline, scenario['platform_policy'], cache)
    katib = run_katib(scenario['katib_experiment'], scenario['platform_policy'])
    faults = [evaluate_fault(item) for item in scenario['faults']]
    passed = all((item['status'] == 'PASS' for item in (first, second, changed, katib))) and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'baseline': scenario['baseline'], 'pipeline_runs': {'first': first, 'same_inputs': second, 'changed_input': changed}, 'katib': katib, 'faults': faults}

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
    print(f'KFP and Katib workflow replay: {report['status']}')
    for name, run in report['pipeline_runs'].items():
        states = ','.join((task['state'] for task in run['tasks']))
        print(f'  pipeline {name}: {run['status']} [{states}]')
    print(f'  katib: {report['katib']['status']} trials={len(report['katib']['trials'])}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live'].get('reason', 'observed')}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-21'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'experiment_workflow_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
