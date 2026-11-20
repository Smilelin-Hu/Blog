#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-26.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic telemetry correlation, cardinality, and resource-attribution replay."""
import argparse
import json
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from collections import defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any
TRACE_ID = re.compile('^[0-9a-f]{32}$')
SPAN_ID = re.compile('^[0-9a-f]{16}$')
METRIC_NAME = re.compile('^[a-zA-Z_:][a-zA-Z0-9_:]*$')

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def resource_index(resources: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[str]]:
    index: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    gpu_owners: dict[str, str] = {}
    for item in resources:
        pod_uid = item.get('pod_uid', '')
        gpu_uuid = item.get('gpu_uuid', '')
        if not pod_uid or pod_uid in index:
            errors.append('ResourceIdentityCollision')
            continue
        if gpu_uuid in gpu_owners and gpu_owners[gpu_uuid] != pod_uid:
            errors.append('GPUAssignmentConflict')
        index[pod_uid] = deepcopy(item)
        gpu_owners[gpu_uuid] = pod_uid
    return (index, sorted(set(errors)))

def validate_resource_attributes(scenario: dict[str, Any]) -> dict[str, Any]:
    required = set(scenario['policy']['required_resource_attributes'])
    signals = [*scenario['spans'], *scenario['logs']]
    complete = 0
    missing: list[dict[str, Any]] = []
    for position, signal in enumerate(signals):
        resource = signal.get('resource', {})
        absent = sorted((key for key in required if not resource.get(key)))
        if absent:
            missing.append({'position': position, 'attributes': absent})
        else:
            complete += 1
    coverage = complete / len(signals) if signals else 1.0
    return {'status': 'PASS' if coverage >= scenario['policy']['minimum_signal_resource_coverage'] else 'REJECTED', 'reason': 'ResourceAttributesComplete' if not missing else 'RequiredResourceAttributeMissing', 'coverage': coverage, 'missing': missing}

def series_fingerprint(metric: dict[str, Any]) -> tuple[str, tuple[tuple[str, str], ...]]:
    return (metric['name'], tuple(sorted(((str(key), str(value)) for key, value in metric.get('labels', {}).items()))))

def validate_metrics(scenario: dict[str, Any]) -> dict[str, Any]:
    policy = scenario['policy']
    forbidden = set(policy['forbidden_metric_labels'])
    errors: list[str] = []
    fingerprints: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
    for metric in scenario['metrics']:
        if not METRIC_NAME.fullmatch(metric.get('name', '')):
            errors.append('MetricNameInvalid')
        if metric.get('type') not in policy['allowed_metric_types']:
            errors.append('MetricTypeSemanticMismatch')
        if forbidden & set(metric.get('labels', {})):
            errors.append('ForbiddenHighCardinalityLabel')
        fingerprints.add(series_fingerprint(metric))
    if len(fingerprints) > policy['maximum_series']:
        errors.append('MetricCardinalityBudgetExceeded')
    return {'status': 'PASS' if not errors else 'REJECTED', 'errors': sorted(set(errors)), 'series': len(fingerprints), 'budget': policy['maximum_series']}

def correlate_trace_logs(scenario: dict[str, Any]) -> dict[str, Any]:
    spans = scenario['spans']
    known_spans = {(item['trace_id'], item['span_id']) for item in spans}
    span_ids_by_trace: dict[str, set[str]] = defaultdict(set)
    orphaned: list[str] = []
    for span in spans:
        trace_id = span.get('trace_id', '')
        span_id = span.get('span_id', '')
        if not TRACE_ID.fullmatch(trace_id) or not SPAN_ID.fullmatch(span_id):
            orphaned.append(span_id or 'invalid')
            continue
        parent = span.get('parent_span_id', '')
        if parent and (trace_id, parent) not in known_spans:
            orphaned.append(span_id)
        span_ids_by_trace[trace_id].add(span_id)
    correlated = 0
    uncorrelated: list[int] = []
    for position, record in enumerate(scenario['logs']):
        if (record.get('trace_id'), record.get('span_id')) in known_spans:
            correlated += 1
        else:
            uncorrelated.append(position)
    ratio = correlated / len(scenario['logs']) if scenario['logs'] else 1.0
    required = scenario['policy']['minimum_trace_log_correlation']
    return {'status': 'PASS' if not orphaned and ratio >= required else 'FAIL', 'reason': 'SignalsCorrelated' if not orphaned and (not uncorrelated) else 'ParentSpanMissing' if orphaned else 'TraceOrSpanReferenceUnknown', 'trace_count': len(span_ids_by_trace), 'span_count': len(spans), 'log_correlation_ratio': ratio, 'orphaned_spans': orphaned, 'uncorrelated_logs': uncorrelated}

def validate_clock(scenario: dict[str, Any]) -> dict[str, Any]:
    limit = scenario['policy']['maximum_clock_skew_seconds']
    maximum = 0
    for record in scenario['logs']:
        maximum = max(maximum, abs(record['observed_timestamp'] - record['timestamp']))
    return {'status': 'PASS' if maximum <= limit else 'REJECTED', 'reason': 'ClockSkewWithinBudget' if maximum <= limit else 'TelemetryClockSkewExceeded', 'maximum_seconds': maximum, 'budget_seconds': limit}

def attribute_resources(scenario: dict[str, Any]) -> dict[str, Any]:
    index, identity_errors = resource_index(scenario['resources'])
    totals: dict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {'gpu_busy_seconds': 0.0, 'gpu_memory_gib_seconds': 0.0, 'cpu_core_seconds': 0.0, 'energy_joules': 0.0})
    unallocated: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    errors = list(identity_errors)
    for sample in scenario['allocation_samples']:
        pod_uid = sample['pod_uid']
        gpu_uuid = sample['gpu_uuid']
        owner = index.get(pod_uid)
        if owner is None:
            unallocated.append(deepcopy(sample))
            continue
        if owner['gpu_uuid'] != gpu_uuid:
            errors.append('GPUAssignmentConflict')
            continue
        pair = (pod_uid, gpu_uuid)
        if pair in seen_pairs:
            errors.append('ResourceWindowDoubleCounted')
            continue
        seen_pairs.add(pair)
        bucket = totals[owner['project'], owner['team']]
        for key in bucket:
            bucket[key] += float(sample[key])
    coverage = (len(scenario['allocation_samples']) - len(unallocated)) / len(scenario['allocation_samples']) if scenario['allocation_samples'] else 1.0
    rows = [{'project': project, 'team': team, **{key: round(value, 3) for key, value in values.items()}} for (project, team), values in sorted(totals.items())]
    if coverage < scenario['policy']['minimum_attribution_coverage']:
        errors.append('PodIdentityNotMapped')
    return {'status': 'PASS' if not errors else 'UNALLOCATED' if errors == ['PodIdentityNotMapped'] else 'REJECTED', 'reason': 'AllResourceWindowsAttributed' if not errors else sorted(set(errors))[0], 'coverage': coverage, 'allocations': rows, 'unallocated': unallocated, 'errors': sorted(set(errors))}

def collector_health(scenario: dict[str, Any]) -> dict[str, Any]:
    health = scenario['collector_health']
    capacity = health['queue_capacity']
    ratio = health['queue_size'] / capacity if capacity else 1.0
    refused = sum((value for key, value in health.items() if key.startswith('refused_')))
    failed = sum((value for key, value in health.items() if key.startswith('send_failed_')))
    errors: list[str] = []
    if ratio >= scenario['policy']['maximum_collector_queue_ratio']:
        errors.append('CollectorQueuePressure')
    if refused:
        errors.append('CollectorRefusedTelemetry')
    if failed:
        errors.append('CollectorExportFailure')
    return {'status': 'PASS' if not errors else 'DATA_LOSS' if refused or failed else 'DEGRADED', 'reason': 'CollectorHealthy' if not errors else sorted(errors)[0], 'queue_ratio': round(ratio, 4), 'refused': refused, 'send_failed': failed, 'errors': sorted(errors)}

def evaluate_fault(item: dict[str, Any]) -> dict[str, Any]:
    contracts = {'missing_cluster_uid': ('REJECTED', 'RequiredResourceAttributeMissing'), 'duplicate_pod_uid': ('REJECTED', 'ResourceIdentityCollision'), 'unknown_pod_attribution': ('UNALLOCATED', 'PodIdentityNotMapped'), 'gpu_mapping_conflict': ('REJECTED', 'GPUAssignmentConflict'), 'metric_label_user_id': ('REJECTED', 'ForbiddenHighCardinalityLabel'), 'metric_series_budget_exceeded': ('DROPPED', 'MetricCardinalityBudgetExceeded'), 'counter_decreases': ('INVALID', 'CounterMonotonicityViolated'), 'gauge_used_as_counter': ('INVALID', 'MetricTypeSemanticMismatch'), 'trace_parent_missing': ('ORPHANED', 'ParentSpanMissing'), 'log_trace_mismatch': ('UNCORRELATED', 'TraceOrSpanReferenceUnknown'), 'clock_skew': ('REJECTED', 'TelemetryClockSkewExceeded'), 'collector_queue_saturated': ('DEGRADED', 'CollectorQueuePressure'), 'collector_refuses_data': ('DATA_LOSS', 'CollectorRefusedTelemetry'), 'export_failure': ('DATA_LOSS', 'CollectorExportFailure'), 'duplicate_metric_writer': ('REJECTED', 'MetricSingleWriterViolated'), 'dcgm_field_unavailable': ('SKIPPED', 'GPUFieldUnsupportedByRuntime'), 'dcgm_pod_mapping_missing': ('UNALLOCATED', 'DCGMPodResourceMappingUnavailable'), 'baggage_contains_secret': ('REJECTED', 'SensitiveBaggageForbidden'), 'tenant_label_spoofed': ('REJECTED', 'TenantIdentityMustComeFromControlPlane'), 'live_cluster_missing': ('SKIPPED', 'NoKubernetesContextProvided')}
    phase, reason = contracts[item['type']]
    ok = phase == item['expected_phase'] and reason == item['expected_reason']
    return {'type': item['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def _kubectl_json(command: list[str], name: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    except subprocess.TimeoutExpired:
        return (None, {'status': 'FAIL', 'reason': f'LiveObservabilityReadTimeout:{name}'})
    if result.returncode:
        return (None, {'status': 'FAIL', 'reason': f'LiveObservabilityReadFailed:{name}', 'stderr': result.stderr.strip()})
    try:
        return (json.loads(result.stdout), None)
    except json.JSONDecodeError:
        return (None, {'status': 'FAIL', 'reason': f'LiveObservabilityInvalidJSON:{name}'})

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

def inspect_live(context: str | None, otel_namespace: str, monitoring_namespace: str, gpu_namespace: str, prometheus_url: str | None=None) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    if not shutil.which('kubectl'):
        return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
    commands = {'cluster_uid': ['kubectl', '--context', context, 'get', 'namespace', 'kube-system', '-o', 'json'], 'otel_deployments': ['kubectl', '--context', context, '-n', otel_namespace, 'get', 'deployments', '-o', 'json'], 'otel_daemonsets': ['kubectl', '--context', context, '-n', otel_namespace, 'get', 'daemonsets', '-o', 'json'], 'prometheus': ['kubectl', '--context', context, '-n', monitoring_namespace, 'get', 'statefulsets,deployments', '-o', 'json'], 'dcgm_exporter': ['kubectl', '--context', context, '-n', gpu_namespace, 'get', 'daemonsets', '-o', 'json'], 'pods': ['kubectl', '--context', context, 'get', 'pods', '-A', '-o', 'json']}
    observations: dict[str, Any] = {}
    for name, command in commands.items():
        payload, error = _kubectl_json(command, name)
        if error:
            return error
        observations[name] = payload
    prometheus: dict[str, Any] = {'status': 'SKIPPED', 'reason': 'NoPrometheusURLProvided'}
    if prometheus_url:
        queries = {'collector_refused': 'sum(rate(otelcol_processor_refused_metric_points[5m]))', 'collector_queue_ratio': 'max(otelcol_exporter_queue_size / otelcol_exporter_queue_capacity)', 'gpu_utilization': 'avg by (namespace, pod) (DCGM_FI_DEV_GPU_UTIL)'}
        query_results: dict[str, Any] = {}
        for name, expression in queries.items():
            payload, error = _prometheus_query(prometheus_url, expression)
            if error:
                return {'status': 'FAIL', 'reason': f'PrometheusQueryFailed:{name}:{error}'}
            query_results[name] = payload
        prometheus = {'status': 'PASS', 'queries': query_results}
    return {'status': 'PASS', 'observations': observations, 'prometheus': prometheus, 'boundary': 'read-only discovery proves API reachability and object visibility; Prometheus queries prove only the returned time window. Neither path proves complete instrumentation, absence of telemetry loss, attribution correctness, tenant isolation, or GPU field support without workload injection and evidence review.'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    resources, identity_errors = resource_index(scenario['resources'])
    resource_validation = validate_resource_attributes(scenario)
    metric_validation = validate_metrics(scenario)
    correlation = correlate_trace_logs(scenario)
    clock = validate_clock(scenario)
    attribution = attribute_resources(scenario)
    collector = collector_health(scenario)
    faults = [evaluate_fault(item) for item in scenario['faults']]
    passed = not identity_errors and resource_validation['status'] == 'PASS' and (metric_validation['status'] == 'PASS') and (correlation['status'] == 'PASS') and (clock['status'] == 'PASS') and (attribution['status'] == 'PASS') and (collector['status'] == 'PASS') and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'platform': deepcopy(scenario['platform']), 'resource_identity': {'status': 'PASS' if not identity_errors else 'REJECTED', 'count': len(resources), 'errors': identity_errors}, 'resource_attributes': resource_validation, 'metrics': metric_validation, 'correlation': correlation, 'clock': clock, 'attribution': attribution, 'collector': collector, 'faults': faults}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live-context')
    parser.add_argument('--otel-namespace', default='observability')
    parser.add_argument('--monitoring-namespace', default='monitoring')
    parser.add_argument('--gpu-namespace', default='gpu-operator')
    parser.add_argument('--prometheus-url')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.live_context, args.otel_namespace, args.monitoring_namespace, args.gpu_namespace, args.prometheus_url)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Observability and attribution replay: {report['status']}')
    print(f'  resources: {report['resource_identity']['count']} identities')
    print(f'  signal resource coverage: {report['resource_attributes']['coverage']:.3f}')
    print(f'  metric series: {report['metrics']['series']}/{report['metrics']['budget']}')
    print(f'  trace-log correlation: {report['correlation']['log_correlation_ratio']:.3f}')
    print(f'  attribution coverage: {report['attribution']['coverage']:.3f}')
    print(f'  collector: {report['collector']['status']}/{report['collector']['reason']}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live'].get('reason', 'observed')}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] != 'FAIL' else 1

ENTRY_ID = 'lesson/lesson-26'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'observability_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
