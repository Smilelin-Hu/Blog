#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-03.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Run a deterministic AIJob reconciliation and finalizer simulation."""
import argparse
import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
FINALIZER = 'platform.example.io/checkpoint-protection'

@dataclass
class MemoryAPI:
    aijob: dict[str, Any]
    faults: dict[str, int]
    child: dict[str, Any] | None = None
    external_checkpoint: bool = True
    events: list[dict[str, Any]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    resource_version: int = 1

    def update_job(self, mutate: Any, expected_resource_version: str) -> None:
        current = self.aijob['metadata']['resourceVersion']
        if current != expected_resource_version:
            raise ConflictError(f'expected resourceVersion {expected_resource_version}, found {current}')
        mutate(self.aijob)
        self.resource_version += 1
        self.aijob['metadata']['resourceVersion'] = str(self.resource_version)

    def event(self, reason: str, message: str) -> None:
        self.events.append({'reason': reason, 'message': message})

class ConflictError(RuntimeError):
    pass

class TransientError(RuntimeError):
    pass

def condition(condition_type: str, status: str, reason: str, message: str, generation: int) -> dict[str, Any]:
    return {'type': condition_type, 'status': status, 'reason': reason, 'message': message, 'observedGeneration': generation}

def desired_child(job: dict[str, Any]) -> dict[str, Any]:
    meta = job['metadata']
    spec = job['spec']
    return {'apiVersion': 'batch/v1', 'kind': 'Job', 'metadata': {'name': f'{meta['name']}-worker', 'namespace': meta['namespace'], 'ownerReferences': [{'apiVersion': job['apiVersion'], 'kind': job['kind'], 'name': meta['name'], 'uid': meta['uid'], 'controller': True, 'blockOwnerDeletion': True}], 'labels': {'platform.example.io/aijob': meta['name']}}, 'spec': {'parallelism': spec['replicas'], 'image': spec['image'], 'command': spec['command'], 'acceleratorClass': spec['acceleratorClass']}, 'status': {'phase': 'Pending'}}

def set_status(api: MemoryAPI, phase: str, conditions: list[dict[str, Any]]) -> None:
    rv = api.aijob['metadata']['resourceVersion']
    generation = api.aijob['metadata']['generation']

    def mutate(job: dict[str, Any]) -> None:
        job['status'] = {'phase': phase, 'observedGeneration': generation, 'conditions': conditions}
    api.update_job(mutate, rv)

def reconcile(api: MemoryAPI) -> dict[str, Any]:
    job = api.aijob
    meta = job['metadata']
    generation = meta['generation']
    if meta.get('deletionTimestamp'):
        if FINALIZER not in meta.get('finalizers', []):
            return {'result': 'deleted', 'requeue': False}
        if api.faults.get('cleanup_transient_failures', 0) > 0:
            api.faults['cleanup_transient_failures'] -= 1
            api.event('CleanupRetry', 'checkpoint cleanup returned a transient error')
            raise TransientError('checkpoint cleanup returned a transient error')
        api.external_checkpoint = False
        api.child = None
        rv = meta['resourceVersion']

        def remove_finalizer(current: dict[str, Any]) -> None:
            current['metadata']['finalizers'] = [item for item in current['metadata'].get('finalizers', []) if item != FINALIZER]
        api.update_job(remove_finalizer, rv)
        api.actions.extend(['delete-external-checkpoint', 'remove-child', 'remove-finalizer'])
        api.event('CleanupComplete', 'external checkpoint and child resources are cleaned')
        return {'result': 'finalized', 'requeue': False}
    if FINALIZER not in meta.get('finalizers', []):
        rv = meta['resourceVersion']

        def add_finalizer(current: dict[str, Any]) -> None:
            current['metadata'].setdefault('finalizers', []).append(FINALIZER)
        api.update_job(add_finalizer, rv)
        api.actions.append('add-finalizer')
        return {'result': 'finalizer-added', 'requeue': True}
    if api.child is None:
        if api.faults.get('create_child_transient_failures', 0) > 0:
            api.faults['create_child_transient_failures'] -= 1
            set_status(api, 'Pending', [condition('Progressing', 'False', 'ChildCreateRetry', 'child creation will be retried', generation)])
            api.event('ChildCreateRetry', 'child creation returned a transient error')
            raise TransientError('child creation returned a transient error')
        api.child = desired_child(job)
        api.actions.append('create-child')
        set_status(api, 'Pending', [condition('Progressing', 'True', 'ChildCreated', 'worker Job has been created', generation)])
        api.event('ChildCreated', 'worker Job has been created')
        return {'result': 'child-created', 'requeue': False}
    desired = desired_child(job)
    if api.child['spec'] != desired['spec']:
        api.child['spec'] = desired['spec']
        api.actions.append('update-child')
    child_phase = api.child['status']['phase']
    if child_phase == 'Succeeded':
        set_status(api, 'Succeeded', [condition('Ready', 'True', 'Completed', 'AIJob completed', generation)])
        return {'result': 'succeeded', 'requeue': False}
    if child_phase == 'Failed':
        set_status(api, 'Failed', [condition('Failed', 'True', 'ChildFailed', 'worker Job failed', generation)])
        return {'result': 'failed', 'requeue': False}
    if child_phase == 'Running':
        set_status(api, 'Running', [condition('Progressing', 'True', 'ChildRunning', 'AIJob is running', generation)])
        return {'result': 'running', 'requeue': False}
    set_status(api, 'Pending', [condition('Progressing', 'True', 'WaitingForChild', 'waiting for worker Job', generation)])
    return {'result': 'pending', 'requeue': False}

def reconcile_with_backoff(api: MemoryAPI, max_attempts: int=5) -> dict[str, Any]:
    delays: list[int] = []
    for attempt in range(max_attempts):
        try:
            result = reconcile(api)
            result['backoff_seconds'] = delays
            result['attempts'] = attempt + 1
            return result
        except TransientError:
            delays.append(min(2 ** attempt, 16))
    return {'result': 'retry-exhausted', 'requeue': True, 'backoff_seconds': delays, 'attempts': max_attempts}

def run_lifecycle(scenario: dict[str, Any]) -> dict[str, Any]:
    api = MemoryAPI(copy.deepcopy(scenario['aijob']), copy.deepcopy(scenario.get('faults', {})))
    checkpoints: list[dict[str, Any]] = []
    checkpoints.append({'step': 'add-finalizer', **reconcile_with_backoff(api)})
    checkpoints.append({'step': 'create', **reconcile_with_backoff(api)})
    child_identity = id(api.child)
    child_creations = api.actions.count('create-child')
    checkpoints.append({'step': 'duplicate-event', **reconcile_with_backoff(api)})
    duplicate_safe = id(api.child) == child_identity and api.actions.count('create-child') == child_creations
    api.child['status']['phase'] = 'Running'
    checkpoints.append({'step': 'child-running', **reconcile_with_backoff(api)})
    rv = api.aijob['metadata']['resourceVersion']

    def update_spec(job: dict[str, Any]) -> None:
        job['spec']['replicas'] = 8
        job['metadata']['generation'] += 1
    api.update_job(update_spec, rv)
    checkpoints.append({'step': 'spec-update', **reconcile_with_backoff(api)})
    api.child['status']['phase'] = 'Succeeded'
    checkpoints.append({'step': 'child-succeeded', **reconcile_with_backoff(api)})
    rv = api.aijob['metadata']['resourceVersion']

    def mark_deleted(job: dict[str, Any]) -> None:
        job['metadata']['deletionTimestamp'] = '2026-08-21T00:00:00Z'
    api.update_job(mark_deleted, rv)
    checkpoints.append({'step': 'delete', **reconcile_with_backoff(api)})
    owner_ref = desired_child(scenario['aijob'])['metadata']['ownerReferences'][0]
    checks = {'single_child_after_duplicate_event': duplicate_safe, 'owner_reference_points_to_aijob': owner_ref['uid'] == scenario['aijob']['metadata']['uid'], 'observed_generation_catches_up': api.aijob['status']['observedGeneration'] == api.aijob['metadata']['generation'], 'child_updated_after_spec_change': 'update-child' in api.actions, 'transient_create_was_retried': any((item['step'] == 'create' and item['attempts'] == 2 for item in checkpoints)), 'external_checkpoint_cleaned': not api.external_checkpoint, 'child_removed': api.child is None, 'finalizer_removed': FINALIZER not in api.aijob['metadata'].get('finalizers', []), 'cleanup_was_retried': any((item['step'] == 'delete' and item['attempts'] == 2 for item in checkpoints))}
    return {'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks, 'checkpoints': checkpoints, 'actions': api.actions, 'events': api.events, 'final_aijob': api.aijob}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    scenario = json.loads(args.scenario.read_text(encoding='utf-8'))
    report = run_lifecycle(scenario)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'AIJob controller simulation: {report['status']}')
    for name, passed in report['checks'].items():
        print(f'  {('PASS' if passed else 'FAIL')} {name}')
    print(f'Actions: {', '.join(report['actions'])}')
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-03'


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
        if not any(tools.values()) or True:
            return _precondition_failed("no declared live target capability is available", tools=tools, live_route_declared=False)
        _emit_contract("ready", "none", tools=tools)
        return 0
    if "--real" in args:
        args.remove("--real")
        if not args:
            return _precondition_failed("--real requires explicit live target arguments; no fixture fallback is allowed")
        tools = {name: shutil.which(name) is not None for name in ['kubectl', 'nvidia-smi', 'sinfo']}
        if not any(tools.values()) or True:
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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'controller_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
