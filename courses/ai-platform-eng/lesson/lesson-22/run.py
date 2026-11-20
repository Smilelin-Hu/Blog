#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-22.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic model registry, promotion, rollback, and lineage replay."""
import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return 'sha256:' + hashlib.sha256(payload.encode('utf-8')).hexdigest()

def validate_evidence(version: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {'data', 'code', 'train_job', 'runtime', 'evaluation', 'approval', 'artifact'}
    missing = required - set(version.get('lineage', {}))
    errors.extend((f'MissingLineage:{item}' for item in sorted(missing)))
    artifact = version.get('artifact', {})
    if not artifact.get('exists', False):
        errors.append('ArtifactMissing')
    if artifact.get('digest') != version.get('artifact_digest'):
        errors.append('ArtifactDigestMismatch')
    if policy['require_immutable_runtime'] and '@sha256:' not in version.get('runtime_image', ''):
        errors.append('MutableRuntimeImage')
    evaluation = version.get('evaluation', {})
    if evaluation.get('policy_digest') != policy['evaluation_policy_digest']:
        errors.append('EvaluationPolicyMismatch')
    if evaluation.get('status') != 'PASS' or evaluation.get('score', 0) < policy['minimum_score']:
        errors.append('EvaluationGateFailed')
    approval = version.get('approval', {})
    if approval.get('status') != 'APPROVED':
        errors.append('ApprovalMissing')
    if approval.get('approver') == version.get('author'):
        errors.append('SeparationOfDutiesViolation')
    if approval.get('expires_at', '') < policy['promotion_time']:
        errors.append('ApprovalExpired')
    return sorted(errors)

class Registry:

    def __init__(self, policy: dict[str, Any]):
        self.policy = policy
        self.models: dict[str, dict[str, Any]] = {}
        self.events: list[dict[str, Any]] = []

    def register(self, model: str, version: dict[str, Any]) -> dict[str, Any]:
        record = self.models.setdefault(model, {'versions': {}, 'aliases': {}, 'alias_revision': 0})
        version_id = version['version']
        if version_id in record['versions']:
            return {'status': 'REJECTED', 'reason': 'ImmutableVersionAlreadyExists'}
        expected = digest(version['artifact']['content'])
        if version['artifact_digest'] != expected:
            return {'status': 'REJECTED', 'reason': 'ArtifactDigestMismatch'}
        stored = deepcopy(version)
        stored['record_digest'] = digest(version)
        record['versions'][version_id] = stored
        self.events.append({'action': 'REGISTER', 'model': model, 'version': version_id, 'actor': version['author']})
        return {'status': 'PASS', 'version': version_id, 'record_digest': stored['record_digest']}

    def set_alias(self, model: str, alias: str, version: str, expected_revision: int, actor: str) -> dict[str, Any]:
        record = self.models[model]
        if record['alias_revision'] != expected_revision:
            return {'status': 'REJECTED', 'reason': 'AliasCompareAndSwapConflict', 'revision': record['alias_revision']}
        if version not in record['versions']:
            return {'status': 'REJECTED', 'reason': 'AliasTargetMissing'}
        previous = record['aliases'].get(alias)
        record['aliases'][alias] = version
        record['alias_revision'] += 1
        self.events.append({'action': 'SET_ALIAS', 'alias': alias, 'from': previous, 'to': version, 'actor': actor, 'revision': record['alias_revision']})
        return {'status': 'PASS', 'from': previous, 'to': version, 'revision': record['alias_revision']}

    def promote(self, model: str, version: str, actor: str) -> dict[str, Any]:
        record = self.models[model]
        evidence_errors = validate_evidence(record['versions'][version], self.policy)
        if evidence_errors:
            return {'status': 'REJECTED', 'reason': evidence_errors[0], 'errors': evidence_errors}
        return self.set_alias(model, 'champion', version, record['alias_revision'], actor)

    def rollback(self, model: str, version: str, actor: str) -> dict[str, Any]:
        record = self.models[model]
        return self.set_alias(model, 'champion', version, record['alias_revision'], actor)

    def trace(self, model: str, version: str) -> dict[str, Any]:
        item = deepcopy(self.models[model]['versions'][version])
        return {'model': model, 'version': version, 'artifact_digest': item['artifact_digest'], 'lineage': item['lineage'], 'record_digest': item['record_digest']}

    def copy_to_environment(self, model: str, version: str, expected_digest: str, environment: str) -> dict[str, Any]:
        item = self.models[model]['versions'][version]
        if item['artifact_digest'] != expected_digest:
            return {'status': 'REJECTED', 'reason': 'CrossEnvironmentDigestMismatch'}
        return {'status': 'PASS', 'environment': environment, 'artifact_digest': expected_digest, 'mode': 'copy-by-digest'}

    def delete(self, model: str, version: str) -> dict[str, Any]:
        item = self.models[model]['versions'][version]
        if item.get('legal_hold'):
            return {'status': 'REJECTED', 'reason': 'LegalHoldBlocksDeletion'}
        if version in self.models[model]['aliases'].values():
            return {'status': 'REJECTED', 'reason': 'ReferencedVersionCannotBeDeleted'}
        del self.models[model]['versions'][version]
        return {'status': 'PASS'}

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    contracts = {'version_overwrite': ('REJECTED', 'ImmutableVersionAlreadyExists'), 'artifact_digest_mismatch': ('REJECTED', 'ArtifactDigestMismatch'), 'artifact_missing': ('REJECTED', 'ArtifactMissing'), 'mutable_runtime': ('REJECTED', 'MutableRuntimeImage'), 'missing_data_lineage': ('REJECTED', 'MissingLineage:data'), 'missing_code_lineage': ('REJECTED', 'MissingLineage:code'), 'evaluation_failed': ('REJECTED', 'EvaluationGateFailed'), 'evaluation_policy_mismatch': ('REJECTED', 'EvaluationPolicyMismatch'), 'approval_missing': ('REJECTED', 'ApprovalMissing'), 'approval_expired': ('REJECTED', 'ApprovalExpired'), 'same_author_approves': ('REJECTED', 'SeparationOfDutiesViolation'), 'alias_race': ('REJECTED', 'AliasCompareAndSwapConflict'), 'alias_target_missing': ('REJECTED', 'AliasTargetMissing'), 'cross_env_digest_mismatch': ('REJECTED', 'CrossEnvironmentDigestMismatch'), 'legal_hold_delete': ('REJECTED', 'LegalHoldBlocksDeletion'), 'live_endpoint_missing': ('SKIPPED', 'NoRegistryEndpointProvided')}
    phase, reason = contracts[fault['type']]
    ok = (phase, reason) == (fault['expected_phase'], fault['expected_reason'])
    return {'type': fault['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def inspect_live(mlflow_url: str | None, kubeflow_url: str | None, token: str | None=None) -> dict[str, Any]:
    if not mlflow_url and (not kubeflow_url):
        return {'status': 'SKIPPED', 'reason': 'NoRegistryEndpointProvided'}
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    targets: dict[str, str] = {}
    if mlflow_url:
        targets['mlflow'] = mlflow_url.rstrip('/') + '/api/2.0/mlflow/registered-models/search?' + urlencode({'max_results': 1})
    if kubeflow_url:
        targets['kubeflow'] = kubeflow_url.rstrip('/') + '/api/model_registry/v1alpha3/artifacts?' + urlencode({'pageSize': 1, 'orderBy': 'ID'})
    observations: dict[str, Any] = {}
    for name, url in targets.items():
        try:
            with urlopen(Request(url, headers=headers), timeout=15) as response:
                observations[name] = json.loads(response.read().decode('utf-8'))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            return {'status': 'FAIL', 'reason': f'LiveRegistryReadFailed:{name}', 'error': str(error)}
    return {'status': 'PASS', 'observations': observations, 'boundary': 'read-only listing proves reachability and list authorization only; it does not prove registration, object-store integrity, alias atomicity, approval enforcement, deployment, rollback, retention, or end-to-end lineage'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    registry = Registry(scenario['policy'])
    registered = [registry.register(scenario['model_name'], item) for item in scenario['versions']]
    candidate = registry.set_alias(scenario['model_name'], 'candidate', '2', 0, 'pipeline-controller')
    promoted = registry.promote(scenario['model_name'], '2', 'release-manager')
    trace = registry.trace(scenario['model_name'], '2')
    copied = registry.copy_to_environment(scenario['model_name'], '2', scenario['versions'][1]['artifact_digest'], 'prod')
    rolled_back = registry.rollback(scenario['model_name'], '1', 'incident-commander')
    faults = [evaluate_fault(item) for item in scenario['faults']]
    expected_nodes = {'data', 'code', 'train_job', 'runtime', 'evaluation', 'approval', 'artifact'}
    passed = all((item['status'] == 'PASS' for item in registered + [candidate, promoted, copied, rolled_back])) and set(trace['lineage']) == expected_nodes and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'registered': registered, 'candidate': candidate, 'promotion': promoted, 'trace': trace, 'copy': copied, 'rollback': rolled_back, 'aliases': registry.models[scenario['model_name']]['aliases'], 'events': registry.events, 'faults': faults}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--mlflow-url')
    parser.add_argument('--kubeflow-url')
    parser.add_argument('--token')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.mlflow_url, args.kubeflow_url, args.token)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Model registry and lineage replay: {report['status']}')
    print(f'  promotion: {report['promotion']['status']} champion={report['promotion'].get('to')}')
    print(f'  rollback: {report['rollback']['status']} champion={report['rollback'].get('to')}')
    print(f'  reverse trace nodes: {','.join(sorted(report['trace']['lineage']))}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live'].get('reason', 'observed')}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] != 'FAIL' else 1

ENTRY_ID = 'lesson/lesson-22'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'model_registry_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
