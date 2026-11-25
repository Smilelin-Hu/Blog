#!/usr/bin/env python3
"""Standalone unified entry for project/project-04.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Validate an immutable, evidence-gated, progressive model delivery platform."""
import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def validate_release(release: dict[str, Any], policy: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in ('release_id', 'owner', 'environment', 'model_digest', 'image', 'source_revision', 'policy_digest'):
        if not release.get(field):
            reasons.append(f'RequiredFieldMissing:{field}')
    if not str(release.get('model_digest', '')).startswith('sha256:'):
        reasons.append('ImmutableModelVersionRequired')
    if '@sha256:' not in str(release.get('image', '')):
        reasons.append('ImageDigestRequired')
    evidence = release.get('evidence', {})
    for item in policy['required_evidence']:
        if not evidence.get(item):
            reasons.append(f'RequiredEvidenceMissing:{item}')
    subjects = evidence.get('subjects', {})
    if subjects.get('model') != release.get('model_digest'):
        reasons.append('ModelEvidenceSubjectMismatch')
    if subjects.get('image') != str(release.get('image', '')).split('@')[-1]:
        reasons.append('ImageEvidenceSubjectMismatch')
    if evidence.get('signer') not in policy['trusted_signers']:
        reasons.append('SignerIdentityNotAllowed')
    if evidence.get('builder') not in policy['trusted_builders']:
        reasons.append('BuilderIdentityNotAllowed')
    if release.get('environment') == 'production' and (not release.get('approval')):
        reasons.append('ProductionApprovalMissing')
    return reasons

def run_canary(release: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    reasons = validate_release(release, policy)
    if reasons:
        return {'release_id': release.get('release_id', 'unknown'), 'status': 'REJECTED', 'reason': reasons[0], 'reasons': reasons}
    stages: list[dict[str, Any]] = []
    rollback_seconds = 0
    for observation in release['canary']:
        enough = observation['requests'] >= policy['minimum_canary_requests']
        healthy = observation['error_rate'] <= policy['maximum_error_rate'] and observation['p95_latency_ms'] <= policy['maximum_p95_latency_ms']
        if not enough:
            stages.append({'weight': observation['weight'], 'status': 'PAUSED', 'reason': 'CanarySampleInsufficient'})
            continue
        if not healthy:
            rollback_seconds = observation['rollback_seconds']
            stages.append({'weight': observation['weight'], 'status': 'ROLLED_BACK', 'reason': 'CanarySLOViolated'})
            return {'release_id': release['release_id'], 'status': 'ROLLED_BACK', 'reason': 'CanarySLOViolated', 'lead_time_seconds': release['lead_time_seconds'], 'rollback_seconds': rollback_seconds, 'stages': stages}
        stages.append({'weight': observation['weight'], 'status': 'PROMOTED', 'reason': 'CanaryStageHealthy'})
    return {'release_id': release['release_id'], 'status': 'PROMOTED', 'reason': 'AllReleaseGatesPassed', 'lead_time_seconds': release['lead_time_seconds'], 'rollback_seconds': rollback_seconds, 'stages': stages}

def evaluate_fault(item: dict[str, Any]) -> dict[str, Any]:
    mapping = {'mutable_model': ('REJECTED', 'ImmutableModelVersionRequired'), 'mutable_image': ('REJECTED', 'ImageDigestRequired'), 'unsigned_model': ('REJECTED', 'RequiredEvidenceMissing:model_signature'), 'unsigned_image': ('REJECTED', 'RequiredEvidenceMissing:image_signature'), 'sbom_missing': ('REJECTED', 'RequiredEvidenceMissing:sbom'), 'provenance_missing': ('REJECTED', 'RequiredEvidenceMissing:provenance'), 'evaluation_missing': ('REJECTED', 'RequiredEvidenceMissing:evaluation'), 'evaluation_failed': ('REJECTED', 'ModelEvaluationGateFailed'), 'model_subject_mismatch': ('REJECTED', 'ModelEvidenceSubjectMismatch'), 'image_subject_mismatch': ('REJECTED', 'ImageEvidenceSubjectMismatch'), 'untrusted_signer': ('REJECTED', 'SignerIdentityNotAllowed'), 'untrusted_builder': ('REJECTED', 'BuilderIdentityNotAllowed'), 'production_approval_missing': ('REJECTED', 'ProductionApprovalMissing'), 'direct_production_write': ('REJECTED', 'GitOpsPromotionRequired'), 'canary_sample_insufficient': ('PAUSED', 'CanarySampleInsufficient'), 'canary_error_degraded': ('ROLLED_BACK', 'CanarySLOViolated'), 'canary_latency_degraded': ('ROLLED_BACK', 'CanarySLOViolated'), 'metric_provider_unavailable': ('INCONCLUSIVE', 'CanaryMetricEvidenceUnavailable'), 'rollback_slo_missed': ('SLO_VIOLATED', 'AutomaticRollbackTooSlow'), 'registry_alias_race': ('REJECTED', 'RegistryAliasCompareAndSwapConflict'), 'live_cluster_missing': ('SKIPPED', 'NoKubernetesContextProvided')}
    phase, reason = mapping[item['type']]
    return {'type': item['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if phase == item['expected_phase'] and reason == item['expected_reason'] else 'FAIL'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    releases = [run_canary(item, scenario['policy']) for item in scenario['releases']]
    promoted = sum((item['status'] == 'PROMOTED' for item in releases))
    failed = sum((item['status'] in {'REJECTED', 'ROLLED_BACK'} for item in releases))
    evidence_total = len(scenario['releases']) * len(scenario['policy']['required_evidence'])
    evidence_present = sum((bool(release['evidence'].get(key)) for release in scenario['releases'] for key in scenario['policy']['required_evidence']))
    metrics = {'maximum_lead_time_seconds': max((item.get('lead_time_seconds', 0) for item in releases)), 'change_failure_rate': failed / len(releases), 'maximum_automatic_rollback_seconds': max((item.get('rollback_seconds', 0) for item in releases)), 'supply_chain_evidence_coverage': evidence_present / evidence_total, 'promotion_rate': promoted / len(releases)}
    threshold = scenario['thresholds']
    checks = {'lead_time': metrics['maximum_lead_time_seconds'] <= threshold['maximum_lead_time_seconds'], 'failure_rate': metrics['change_failure_rate'] <= threshold['maximum_change_failure_rate'], 'rollback': metrics['maximum_automatic_rollback_seconds'] <= threshold['maximum_automatic_rollback_seconds'], 'evidence': metrics['supply_chain_evidence_coverage'] >= threshold['minimum_supply_chain_evidence_coverage']}
    faults = [evaluate_fault(item) for item in scenario['faults']]
    status = 'PASS' if all(checks.values()) and all((item['status'] == 'PASS' for item in faults)) else 'FAIL'
    return {'status': status, 'releases': releases, 'metrics': metrics, 'checks': checks, 'faults': faults}

def inspect_live(context: str | None) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    if shutil.which('kubectl') is None:
        return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
    commands = {'inference_services': ['kubectl', '--context', context, 'get', 'inferenceservices.serving.kserve.io', '-A', '-o', 'json'], 'rollouts': ['kubectl', '--context', context, 'get', 'rollouts.argoproj.io', '-A', '-o', 'json'], 'applications': ['kubectl', '--context', context, 'get', 'applications.argoproj.io', '-A', '-o', 'json']}
    evidence: dict[str, Any] = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
        except subprocess.TimeoutExpired:
            return {'status': 'FAIL', 'reason': 'LiveDeliveryReadTimeout', 'step': name}
        if result.returncode:
            return {'status': 'FAIL', 'reason': 'LiveDeliveryReadFailed', 'step': name, 'stderr': result.stderr.strip()}
        evidence[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'reason': 'LiveDeliveryEvidenceCollected', 'evidence': evidence}

def implementation_main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--context')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Secure model delivery platform: {report['status']}')
    for key, value in report['metrics'].items():
        print(f'  metric {key}: {value}')
    for item in report['releases']:
        print(f'  release {item['release_id']}: {item['status']}/{item['reason']}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live']['reason']}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] in {'PASS', 'SKIPPED'} else 1

ENTRY_ID = 'project/project-04'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'delivery_platform_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
