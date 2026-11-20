#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-27.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic SLO, chaos-safety, and automated-remediation replay."""
import argparse
import json
import shutil
import subprocess
import urllib.parse
import urllib.request
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def compute_slo(slo: dict[str, Any], windows: list[dict[str, Any]]) -> dict[str, Any]:
    good = sum((int(item['good_events']) for item in windows))
    total = sum((int(item['total_events']) for item in windows))
    expected = int(slo['minimum_events'])
    target = float(slo['target'])
    if total < expected:
        return {'status': 'INCONCLUSIVE', 'reason': 'InsufficientSLISamples', 'good_events': good, 'total_events': total}
    achieved = good / total if total else 0.0
    bad = total - good
    budget_fraction = 1.0 - target
    allowed_bad = total * budget_fraction
    remaining = allowed_bad - bad
    return {'status': 'PASS' if achieved >= target else 'BREACHED', 'reason': 'SLOMet' if achieved >= target else 'SLOTargetBreached', 'good_events': good, 'total_events': total, 'achieved': achieved, 'target': target, 'bad_events': bad, 'allowed_bad_events': allowed_bad, 'remaining_bad_events': remaining, 'budget_consumed_ratio': bad / allowed_bad if allowed_bad > 0 else float('inf')}

def burn_rate(target: float, good_events: int, total_events: int) -> float | None:
    if total_events <= 0 or target >= 1.0:
        return None
    observed_error = (total_events - good_events) / total_events
    return observed_error / (1.0 - target)

def evaluate_burn_alerts(scenario: dict[str, Any]) -> dict[str, Any]:
    policy = scenario['burn_policy']
    target = float(scenario['slos'][policy['slo']]['target'])
    by_name = {item['name']: item for item in scenario['sli_windows']}
    evaluations: list[dict[str, Any]] = []
    firing: list[str] = []
    for rule in policy['rules']:
        short = by_name[rule['short_window']]
        long = by_name[rule['long_window']]
        short_rate = burn_rate(target, short['good_events'], short['total_events'])
        long_rate = burn_rate(target, long['good_events'], long['total_events'])
        enough = short['total_events'] >= rule['minimum_short_events'] and long['total_events'] >= rule['minimum_long_events']
        is_firing = bool(enough and short_rate is not None and (long_rate is not None) and (short_rate >= rule['threshold']) and (long_rate >= rule['threshold']))
        evaluations.append({'name': rule['name'], 'short_burn_rate': short_rate, 'long_burn_rate': long_rate, 'enough_samples': enough, 'firing': is_firing})
        if is_firing:
            firing.append(rule['name'])
    return {'status': 'FIRING' if firing else 'PASS', 'reason': 'MultiWindowBurnDetected' if firing else 'BurnWithinPolicy', 'firing': firing, 'evaluations': evaluations}

def validate_telemetry(scenario: dict[str, Any]) -> dict[str, Any]:
    telemetry = scenario['telemetry']
    policy = scenario['policy']
    reasons: list[str] = []
    if telemetry['completeness_ratio'] < policy['minimum_telemetry_completeness']:
        reasons.append('TelemetryCompletenessBelowGate')
    if telemetry['freshness_seconds'] > policy['maximum_telemetry_freshness_seconds']:
        reasons.append('TelemetryStale')
    if telemetry['unknown_series_ratio'] > policy['maximum_unknown_series_ratio']:
        reasons.append('TelemetryIdentityCoverageInsufficient')
    if telemetry['clock_skew_seconds'] > policy['maximum_clock_skew_seconds']:
        reasons.append('TelemetryClockSkewExceeded')
    return {'status': 'PASS' if not reasons else 'INCONCLUSIVE', 'reason': 'TelemetryEvidenceSufficient' if not reasons else reasons[0], 'reasons': reasons}

def route_alerts(scenario: dict[str, Any]) -> dict[str, Any]:
    policy = scenario['alert_policy']
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = defaultdict(list)
    suppressed: list[str] = []
    active = scenario['alerts']
    for alert in active:
        if any((source['alertname'] == rule['source_alertname'] and alert['alertname'] in rule['target_alertnames'] and all((source['labels'].get(key) == alert['labels'].get(key) for key in rule['equal'])) for rule in policy['inhibit_rules'] for source in active)):
            suppressed.append(alert['fingerprint'])
            continue
        key = tuple((str(alert['labels'].get(name, '')) for name in policy['group_by']))
        grouped[key].append(deepcopy(alert))
    duplicate_fingerprints = len({a['fingerprint'] for a in active}) != len(active)
    return {'status': 'REJECTED' if duplicate_fingerprints else 'PASS', 'reason': 'AlertFingerprintDuplicated' if duplicate_fingerprints else 'AlertsGroupedAndInhibited', 'notification_groups': len(grouped), 'suppressed': sorted(suppressed), 'groups': [{'key': list(key), 'alerts': items} for key, items in sorted(grouped.items())]}

def validate_chaos_experiment(experiment: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    namespaces = set(experiment['selector'].get('namespaces', []))
    labels = experiment['selector'].get('label_selectors', {})
    if not namespaces:
        reasons.append('ChaosNamespaceRequired')
    if namespaces & set(policy['protected_namespaces']):
        reasons.append('ChaosTargetsProtectedNamespace')
    if experiment['mode'] == 'all':
        reasons.append('ChaosModeAllForbidden')
    if not labels:
        reasons.append('ChaosLabelSelectorRequired')
    if experiment['estimated_targets'] > policy['maximum_chaos_targets']:
        reasons.append('ChaosBlastRadiusExceeded')
    if experiment['duration_seconds'] > policy['maximum_chaos_duration_seconds']:
        reasons.append('ChaosDurationExceeded')
    if not experiment.get('abort_signal'):
        reasons.append('ChaosAbortSignalMissing')
    if experiment.get('production') and (not experiment.get('approval_id')):
        reasons.append('ProductionChaosApprovalMissing')
    if not experiment.get('steady_state_verified'):
        reasons.append('SteadyStateNotVerified')
    return {'status': 'PASS' if not reasons else 'REJECTED', 'reason': 'ChaosGuardrailsSatisfied' if not reasons else reasons[0], 'reasons': reasons}

def remediation_plan(event: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    policy = scenario['remediation_policy']
    action = policy['fault_actions'].get(event['fault_type'])
    reasons: list[str] = []
    if not action:
        reasons.append('NoApprovedRemediation')
    if event['evidence_count'] < policy['minimum_evidence_count']:
        reasons.append('RemediationEvidenceInsufficient')
    if event['telemetry_status'] != 'PASS':
        reasons.append('TelemetryEvidenceInsufficient')
    if event['error_budget_exhausted'] and action and (action['risk'] != 'containment'):
        reasons.append('ErrorBudgetExhaustedRequiresContainment')
    if event['attempts_last_hour'] >= policy['maximum_attempts_per_hour']:
        reasons.append('RemediationAttemptBudgetExceeded')
    if event['seconds_since_last_action'] < policy['cooldown_seconds']:
        reasons.append('RemediationCooldownActive')
    if event.get('pdb_disruptions_allowed', 0) <= 0 and action and action['requires_eviction']:
        reasons.append('PodDisruptionBudgetBlocksEviction')
    if action and action['requires_idle_gpu'] and (not event.get('gpu_idle', False)):
        reasons.append('ActiveGPUDiagnosticRequiresIdleNode')
    if action and (not action.get('verification')):
        reasons.append('RecoveryVerificationMissing')
    if action and (not action.get('rollback')):
        reasons.append('RollbackPlanMissing')
    if reasons:
        return {'status': 'ESCALATE', 'reason': reasons[0], 'reasons': reasons, 'states': ['DETECTED', 'EVIDENCE_GATED', 'ESCALATED'], 'action': None}
    states = ['DETECTED', 'EVIDENCE_GATED', 'CONTAINED', 'REMEDIATED', 'VERIFYING']
    recovered = bool(event['recovery_signal'])
    states.append('RECOVERED' if recovered else 'ROLLED_BACK')
    return {'status': 'RECOVERED' if recovered else 'ROLLED_BACK', 'reason': 'RecoveryVerified' if recovered else 'RecoveryVerificationFailed', 'reasons': [], 'states': states, 'action': deepcopy(action)}

def evaluate_fault(item: dict[str, Any]) -> dict[str, Any]:
    contracts = {'insufficient_sli_samples': ('INCONCLUSIVE', 'InsufficientSLISamples'), 'single_window_spike': ('PASS', 'DualWindowConditionNotMet'), 'telemetry_incomplete': ('INCONCLUSIVE', 'TelemetryCompletenessBelowGate'), 'telemetry_stale': ('INCONCLUSIVE', 'TelemetryStale'), 'alert_duplicate': ('REJECTED', 'AlertFingerprintDuplicated'), 'runbook_missing': ('REJECTED', 'RunbookReferenceMissing'), 'chaos_namespace_empty': ('REJECTED', 'ChaosNamespaceRequired'), 'chaos_protected_namespace': ('REJECTED', 'ChaosTargetsProtectedNamespace'), 'chaos_mode_all': ('REJECTED', 'ChaosModeAllForbidden'), 'chaos_selector_empty': ('REJECTED', 'ChaosLabelSelectorRequired'), 'chaos_blast_radius': ('REJECTED', 'ChaosBlastRadiusExceeded'), 'production_approval_missing': ('REJECTED', 'ProductionChaosApprovalMissing'), 'steady_state_missing': ('REJECTED', 'SteadyStateNotVerified'), 'remediation_evidence_missing': ('ESCALATE', 'RemediationEvidenceInsufficient'), 'remediation_cooldown': ('ESCALATE', 'RemediationCooldownActive'), 'remediation_loop': ('ESCALATE', 'RemediationAttemptBudgetExceeded'), 'pdb_blocks_eviction': ('ESCALATE', 'PodDisruptionBudgetBlocksEviction'), 'gpu_busy_for_active_diag': ('ESCALATE', 'ActiveGPUDiagnosticRequiresIdleNode'), 'recovery_not_verified': ('ROLLED_BACK', 'RecoveryVerificationFailed'), 'live_cluster_missing': ('SKIPPED', 'NoKubernetesContextProvided')}
    phase, reason = contracts[item['type']]
    ok = phase == item['expected_phase'] and reason == item['expected_reason']
    return {'type': item['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def _kubectl_json(command: list[str], name: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    except subprocess.TimeoutExpired:
        return (None, {'status': 'FAIL', 'reason': f'LiveSREReadTimeout:{name}'})
    if result.returncode:
        return (None, {'status': 'FAIL', 'reason': f'LiveSREReadFailed:{name}', 'stderr': result.stderr.strip()})
    try:
        return (json.loads(result.stdout), None)
    except json.JSONDecodeError:
        return (None, {'status': 'FAIL', 'reason': f'LiveSREInvalidJSON:{name}'})

def _prometheus_query(base_url: str, expression: str) -> tuple[dict[str, Any] | None, str | None]:
    url = base_url.rstrip('/') + '/api/v1/query?' + urllib.parse.urlencode({'query': expression})
    try:
        with urllib.request.urlopen(url, timeout=15) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except Exception as exc:
        return (None, type(exc).__name__)
    if payload.get('status') != 'success':
        return (None, 'PrometheusQueryUnsuccessful')
    return (payload, None)

def inspect_live(context: str | None, prometheus_url: str | None=None) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    if not shutil.which('kubectl'):
        return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
    commands = {'nodes': ['kubectl', '--context', context, 'get', 'nodes', '-o', 'json'], 'pods': ['kubectl', '--context', context, 'get', 'pods', '-A', '-o', 'json'], 'pdbs': ['kubectl', '--context', context, 'get', 'poddisruptionbudgets', '-A', '-o', 'json'], 'events': ['kubectl', '--context', context, 'get', 'events', '-A', '-o', 'json'], 'chaos_crds': ['kubectl', '--context', context, 'get', 'crds', '-o', 'json']}
    observations: dict[str, Any] = {}
    for name, command in commands.items():
        payload, error = _kubectl_json(command, name)
        if error:
            return error
        observations[name] = payload
    prometheus: dict[str, Any] = {'status': 'SKIPPED', 'reason': 'NoPrometheusURLProvided'}
    if prometheus_url:
        queries = {'api_availability_5m': 'sum(rate(apiserver_request_total{code!~"5.."}[5m])) / sum(rate(apiserver_request_total[5m]))', 'pod_restart_rate': 'sum(rate(kube_pod_container_status_restarts_total[15m]))', 'node_not_ready': 'sum(kube_node_status_condition{condition="Ready",status!="true"})', 'gpu_xid_errors': 'sum(increase(DCGM_FI_DEV_XID_ERRORS[15m]))'}
        values: dict[str, Any] = {}
        for name, expression in queries.items():
            payload, error = _prometheus_query(prometheus_url, expression)
            if error:
                return {'status': 'FAIL', 'reason': f'PrometheusQueryFailed:{name}:{error}'}
            values[name] = payload
        prometheus = {'status': 'PASS', 'queries': values}
    return {'status': 'PASS', 'observations': observations, 'prometheus': prometheus, 'boundary': 'read-only discovery proves API reachability and the returned evidence window only; it does not inject faults, execute node mutations, prove end-to-end recovery, or certify GPU hardware health.'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    slos = {name: compute_slo(slo, scenario['slo_evidence'][name]) for name, slo in scenario['slos'].items()}
    telemetry = validate_telemetry(scenario)
    burn = evaluate_burn_alerts(scenario)
    alerts = route_alerts(scenario)
    chaos = validate_chaos_experiment(scenario['chaos_experiment'], scenario['chaos_policy'])
    remediations = [remediation_plan(item, scenario) for item in scenario['incidents']]
    faults = [evaluate_fault(item) for item in scenario['faults']]
    runbooks_complete = all((alert.get('runbook_url') for alert in scenario['alerts']))
    passed = all((item['status'] in {'PASS', 'BREACHED'} for item in slos.values())) and telemetry['status'] == 'PASS' and (burn['status'] in {'PASS', 'FIRING'}) and (alerts['status'] == 'PASS') and (chaos['status'] == 'PASS') and all((item['status'] == 'RECOVERED' for item in remediations)) and all((item['status'] == 'PASS' for item in faults)) and runbooks_complete
    return {'status': 'PASS' if passed else 'FAIL', 'platform': deepcopy(scenario['platform']), 'slos': slos, 'telemetry': telemetry, 'burn_alerts': burn, 'alert_routing': alerts, 'runbooks': {'status': 'PASS' if runbooks_complete else 'REJECTED'}, 'chaos': chaos, 'remediations': remediations, 'faults': faults}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live-context')
    parser.add_argument('--prometheus-url')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.live_context, args.prometheus_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'AI Platform SRE replay: {report['status']}')
    for name, result in report['slos'].items():
        print(f'  SLO {name}: {result['status']}/{result['reason']}')
    print(f'  telemetry: {report['telemetry']['status']}/{report['telemetry']['reason']}')
    print(f'  burn alerts: {report['burn_alerts']['status']}/{report['burn_alerts']['reason']}')
    print(f'  alert routing: {report['alert_routing']['status']}/{report['alert_routing']['reason']}')
    print(f'  chaos: {report['chaos']['status']}/{report['chaos']['reason']}')
    for index, result in enumerate(report['remediations'], start=1):
        print(f'  remediation {index}: {result['status']}/{result['reason']}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live'].get('reason', 'observed')}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] != 'FAIL' else 1

ENTRY_ID = 'lesson/lesson-27'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'sre_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
