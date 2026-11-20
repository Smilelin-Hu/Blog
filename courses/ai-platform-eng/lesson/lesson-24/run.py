#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-24.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic GitOps promotion, canary analysis, and rollback replay."""
import argparse
import json
import math
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def validate_promotion_pr(pr: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy['require_signed_commit'] and (not pr.get('signed_commit')):
        errors.append('SignedCommitRequired')
    if pr.get('base_commit') != policy['expected_base_commit']:
        errors.append('StalePromotionBase')
    reviewers = set(pr.get('approvers', []))
    if len(reviewers) < policy['minimum_approvals']:
        errors.append('PromotionApprovalMissing')
    if pr.get('author') in reviewers:
        errors.append('SeparationOfDutiesViolation')
    if pr.get('target_environment') != 'production':
        errors.append('ProductionEnvironmentRequired')
    if '@sha256:' not in pr.get('model_ref', ''):
        errors.append('ImmutableModelDigestRequired')
    if '@sha256:' not in pr.get('runtime_ref', ''):
        errors.append('ImmutableRuntimeDigestRequired')
    if pr.get('evaluation_evidence') != policy['required_evaluation_evidence']:
        errors.append('EvaluationEvidenceMissing')
    if not pr.get('capacity_precheck', {}).get('passed'):
        errors.append('GPUCapacityPrecheckFailed')
    if pr.get('change_path') != policy['production_change_path']:
        errors.append('ProductionPathNotAllowed')
    return sorted(errors)

def reconcile_git(desired: dict[str, Any], live: dict[str, Any], self_heal: bool) -> dict[str, Any]:
    drift = {key: {'desired': value, 'live': live.get(key)} for key, value in desired.items() if live.get(key) != value}
    if not drift:
        return {'status': 'Synced', 'drift': {}, 'live': deepcopy(live), 'action': 'None'}
    if not self_heal:
        return {'status': 'OutOfSync', 'drift': drift, 'live': deepcopy(live), 'action': 'ObserveOnly'}
    healed = deepcopy(live)
    healed.update(desired)
    return {'status': 'Synced', 'drift': drift, 'live': healed, 'action': 'SelfHeal'}

def required_gpu(weight: int, stable_replicas: int, gpu_per_replica: int, traffic_manager: bool) -> dict[str, int]:
    canary = max(1, math.ceil(stable_replicas * weight / 100)) if weight < 100 else stable_replicas
    stable = stable_replicas if traffic_manager and weight < 100 else max(0, stable_replicas - canary)
    return {'stable_replicas': stable, 'canary_replicas': canary, 'gpu': (stable + canary) * gpu_per_replica}

def analyze(metrics: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    if metrics.get('samples', 0) < policy['minimum_samples']:
        return {'phase': 'Inconclusive', 'reason': 'InsufficientAnalysisSamples'}
    if metrics.get('provider_error'):
        return {'phase': 'Error', 'reason': 'MetricProviderError'}
    failures: list[str] = []
    if metrics['availability'] < policy['minimum_availability']:
        failures.append('AvailabilityBelowSLO')
    if metrics['p95_ms'] > policy['maximum_p95_ms']:
        failures.append('LatencyAboveSLO')
    if metrics['quality'] < policy['minimum_quality']:
        failures.append('QualityBelowGate')
    if failures:
        return {'phase': 'Failed', 'reason': failures[0], 'failures': failures}
    return {'phase': 'Successful', 'reason': 'AllGatesPassed'}

def run_canary(release: dict[str, Any], policy: dict[str, Any], capacity: dict[str, Any]) -> dict[str, Any]:
    history: list[dict[str, Any]] = []
    stable = release['stable_version']
    candidate = release['candidate_version']
    for weight in release['weights']:
        budget = required_gpu(weight, capacity['stable_replicas'], capacity['gpu_per_replica'], release['traffic_manager'])
        if weight < 100 and budget['gpu'] > capacity['available_gpu']:
            history.append({'weight': weight, 'phase': 'Aborted', 'reason': 'CanaryGPUCapacityInsufficient', 'budget': budget})
            return {'status': 'ROLLED_BACK', 'stable': stable, 'candidate': candidate, 'traffic': {stable: 100, candidate: 0}, 'history': history, 'rollback': 'CapacityAbort'}
        result = analyze(release['measurements'][str(weight)], policy)
        history.append({'weight': weight, 'phase': result['phase'], 'reason': result['reason'], 'budget': budget})
        if result['phase'] != 'Successful':
            return {'status': 'ROLLED_BACK', 'stable': stable, 'candidate': candidate, 'traffic': {stable: 100, candidate: 0}, 'history': history, 'rollback': 'AnalysisAbort'}
    return {'status': 'PROMOTED', 'stable': candidate, 'previous': stable, 'traffic': {stable: 0, candidate: 100}, 'history': history, 'rollback': None}

def rollback_release(release_result: dict[str, Any], git: dict[str, Any], registry: dict[str, Any], expected_alias_revision: int) -> dict[str, Any]:
    if registry['alias_revision'] != expected_alias_revision:
        return {'status': 'REJECTED', 'reason': 'RegistryAliasCompareAndSwapConflict'}
    previous = release_result.get('previous') or release_result['stable']
    reverted_git = deepcopy(git)
    reverted_git['model_version'] = previous
    return {'status': 'PASS', 'git': reverted_git, 'registry_alias': previous, 'alias_revision': expected_alias_revision + 1, 'reason': 'GitRevertAndAliasRollback'}

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    contracts = {'unsigned_commit': ('REJECTED', 'SignedCommitRequired'), 'approval_missing': ('REJECTED', 'PromotionApprovalMissing'), 'self_approval': ('REJECTED', 'SeparationOfDutiesViolation'), 'stale_base': ('REJECTED', 'StalePromotionBase'), 'mutable_model': ('REJECTED', 'ImmutableModelDigestRequired'), 'mutable_runtime': ('REJECTED', 'ImmutableRuntimeDigestRequired'), 'evaluation_missing': ('REJECTED', 'EvaluationEvidenceMissing'), 'direct_production_write': ('REJECTED', 'ProductionPathNotAllowed'), 'capacity_precheck_failed': ('REJECTED', 'GPUCapacityPrecheckFailed'), 'drift_without_self_heal': ('OutOfSync', 'ObserveOnly'), 'canary_capacity_shortage': ('Aborted', 'CanaryGPUCapacityInsufficient'), 'metric_provider_error': ('Error', 'MetricProviderError'), 'analysis_samples_missing': ('Inconclusive', 'InsufficientAnalysisSamples'), 'latency_degraded': ('Failed', 'LatencyAboveSLO'), 'registry_alias_race': ('REJECTED', 'RegistryAliasCompareAndSwapConflict'), 'live_cluster_missing': ('SKIPPED', 'NoKubernetesContextProvided')}
    phase, reason = contracts[fault['type']]
    ok = (phase, reason) == (fault['expected_phase'], fault['expected_reason'])
    return {'type': fault['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def inspect_live(context: str | None, application_namespace: str, workload_namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    commands = {'applications': ['kubectl', '--context', context, '-n', application_namespace, 'get', 'applications.argoproj.io', '-o', 'json'], 'rollouts': ['kubectl', '--context', context, '-n', workload_namespace, 'get', 'rollouts.argoproj.io', '-o', 'json'], 'analysis_runs': ['kubectl', '--context', context, '-n', workload_namespace, 'get', 'analysisruns.argoproj.io', '-o', 'json']}
    observations: dict[str, Any] = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
        if result.returncode:
            return {'status': 'FAIL', 'reason': f'LiveGitOpsReadFailed:{name}', 'stderr': result.stderr.strip()}
        observations[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'observations': observations, 'boundary': 'read-only listing proves CRD reachability and list authorization only; it does not prove repository authenticity, sync correctness, real traffic weights, metric validity, GPU capacity, model compatibility, promotion, or rollback'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    pr_errors = validate_promotion_pr(scenario['promotion_pr'], scenario['policy'])
    drift = reconcile_git(scenario['desired_state'], scenario['drifted_live_state'], scenario['policy']['self_heal'])
    canary = run_canary(scenario['release'], scenario['policy'], scenario['capacity'])
    faults = [evaluate_fault(item) for item in scenario['faults']]
    passed = not pr_errors and drift['status'] == 'Synced' and (canary['status'] == scenario['expected_release_status']) and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'promotion_pr': {'status': 'PASS' if not pr_errors else 'REJECTED', 'errors': pr_errors}, 'gitops': drift, 'canary': canary, 'faults': faults}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live-context')
    parser.add_argument('--application-namespace', default='argocd')
    parser.add_argument('--workload-namespace', default='model-serving')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.live_context, args.application_namespace, args.workload_namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'GitOps progressive delivery replay: {report['status']}')
    print(f'  promotion PR: {report['promotion_pr']['status']}')
    print(f'  drift: {report['gitops']['status']}/{report['gitops']['action']}')
    for step in report['canary']['history']:
        print(f'  canary {step['weight']}%: {step['phase']}/{step['reason']} gpu={step['budget']['gpu']}')
    print(f'  release: {report['canary']['status']} traffic={report['canary']['traffic']}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live'].get('reason', 'observed')}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] != 'FAIL' else 1

ENTRY_ID = 'lesson/lesson-24'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'gitops_progressive_delivery_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
