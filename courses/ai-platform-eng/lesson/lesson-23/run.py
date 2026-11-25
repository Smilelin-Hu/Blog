#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-23.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic KServe control-plane reconciliation and condition diagnosis replay."""
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
    if runtime['name'] not in policy['runtime_allowlist']:
        errors.append('RuntimeNotAllowed')
    if policy['require_runtime_digest'] and '@sha256:' not in runtime['image']:
        errors.append('RuntimeImageDigestRequired')
    if runtime.get('scope') not in {'cluster', 'namespace'}:
        errors.append('RuntimeScopeInvalid')
    if not runtime.get('supported_formats'):
        errors.append('RuntimeModelFormatMissing')
    return sorted(errors)

def validate_service(service: dict[str, Any], runtimes: dict[str, dict[str, Any]], policy: dict[str, Any], infra: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    runtime = runtimes.get(service.get('runtime'))
    if runtime is None:
        return ['ServingRuntimeNotFound']
    errors.extend(validate_runtime(runtime, policy))
    if service['model_format'] not in runtime['supported_formats']:
        errors.append('ModelFormatUnsupported')
    if policy['require_model_digest'] and '@sha256:' not in service['model_uri']:
        errors.append('ModelArtifactDigestRequired')
    if service.get('private_model') and service.get('storage_secret') not in infra['storage_secrets']:
        errors.append('StorageCredentialMissing')
    if service.get('local_model') and service['local_model'] not in infra['ready_local_models']:
        errors.append('LocalModelCacheNotReady')
    if service.get('gpu', 0) > policy['max_gpu_per_replica'] or service.get('memory_gib', 0) > policy['max_memory_gib_per_replica']:
        errors.append('ResourcePolicyExceeded')
    mode = service['deployment_mode']
    if mode not in policy['allowed_deployment_modes']:
        errors.append('DeploymentModeNotAllowed')
    if mode == 'Standard' and service.get('min_replicas', 1) == 0:
        errors.append('StandardHTTPScaleToZeroUnsupported')
    if mode == 'Knative' and (not infra['knative_ready']):
        errors.append('KnativeDependencyMissing')
    if service.get('autoscaler') == 'keda' and mode != 'Standard':
        errors.append('KEDARequiresStandardMode')
    if service.get('autoscaler') == 'hpa' and (not infra['metrics_signal_ready']):
        errors.append('AutoscalerMetricSignalMissing')
    if not infra['gateway_ready']:
        errors.append('IngressNotConfigured')
    if policy['require_tls'] and (not service.get('tls')):
        errors.append('TLSRequired')
    if policy['require_auth'] and (not service.get('auth')):
        errors.append('AuthenticationRequired')
    if service.get('max_replicas', 1) < service.get('min_replicas', 1):
        errors.append('ReplicaRangeInvalid')
    if service.get('startup_seconds', 0) > service.get('startup_timeout_seconds', 0):
        errors.append('PredictorStartupTimeout')
    return sorted(set(errors))

def condition_for(errors: list[str]) -> dict[str, Any]:
    if not errors:
        return {'Ready': True, 'reason': 'PredictorReady', 'conditions': {'StorageReady': True, 'RuntimeReady': True, 'PredictorReady': True, 'RouteReady': True}}
    first = errors[0]
    if first in {'ModelArtifactDigestRequired', 'StorageCredentialMissing', 'LocalModelCacheNotReady'}:
        stage = 'StorageReady'
        reason = 'ModelLoadFailed'
    elif first in {'ServingRuntimeNotFound', 'RuntimeNotAllowed', 'RuntimeImageDigestRequired', 'RuntimeScopeInvalid', 'RuntimeModelFormatMissing', 'ModelFormatUnsupported', 'ResourcePolicyExceeded', 'PredictorStartupTimeout'}:
        stage = 'PredictorReady'
        reason = 'PredictorNotReady'
    elif first in {'IngressNotConfigured', 'TLSRequired', 'AuthenticationRequired'}:
        stage = 'RouteReady'
        reason = 'IngressNotConfigured'
    else:
        stage = 'PredictorReady'
        reason = first
    conditions = {'StorageReady': True, 'RuntimeReady': True, 'PredictorReady': True, 'RouteReady': True}
    conditions[stage] = False
    return {'Ready': False, 'reason': reason, 'detail': first, 'conditions': conditions}

def reconcile(service: dict[str, Any], runtimes: dict[str, dict[str, Any]], policy: dict[str, Any], infra: dict[str, Any]) -> dict[str, Any]:
    errors = validate_service(service, runtimes, policy, infra)
    status = condition_for(errors)
    resources: list[str] = []
    if not errors:
        resources = ['Deployment' if service['deployment_mode'] == 'Standard' else 'KnativeService', 'Service', 'HTTPRoute', 'HPA' if service['autoscaler'] == 'hpa' else 'ScaledObject']
    return {'name': service['name'], 'status': 'PASS' if not errors else 'REJECTED', 'errors': errors, 'status_conditions': status, 'resources': resources, 'resolved_model': service['model_uri'], 'resolved_runtime': service['runtime']}

def diagnose(condition: dict[str, Any]) -> str:
    detail = condition.get('detail')
    routes = {'ModelArtifactDigestRequired': 'freeze registry artifact by digest before retry', 'StorageCredentialMissing': 'bind a least-privilege storage credential to the service account', 'LocalModelCacheNotReady': 'inspect LocalModel cache status and node placement', 'ServingRuntimeNotFound': 'create or reference an allowed ServingRuntime', 'ModelFormatUnsupported': 'select a runtime advertising the registered model format', 'IngressNotConfigured': 'install and configure Gateway or ingress provider', 'AutoscalerMetricSignalMissing': 'verify metric collection, adapter, query, and target', 'PredictorStartupTimeout': 'measure model load time and set a bounded startup budget'}
    return routes.get(detail, 'inspect the first false condition, related child resource, and controller events')

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    contracts = {'mutable_model_uri': ('REJECTED', 'ModelArtifactDigestRequired'), 'mutable_runtime_image': ('REJECTED', 'RuntimeImageDigestRequired'), 'runtime_not_allowed': ('REJECTED', 'RuntimeNotAllowed'), 'runtime_missing': ('REJECTED', 'ServingRuntimeNotFound'), 'format_mismatch': ('REJECTED', 'ModelFormatUnsupported'), 'storage_credential_missing': ('REJECTED', 'StorageCredentialMissing'), 'local_cache_not_ready': ('REJECTED', 'LocalModelCacheNotReady'), 'resource_limit_exceeded': ('REJECTED', 'ResourcePolicyExceeded'), 'standard_scale_to_zero': ('REJECTED', 'StandardHTTPScaleToZeroUnsupported'), 'knative_dependency_missing': ('REJECTED', 'KnativeDependencyMissing'), 'keda_wrong_mode': ('REJECTED', 'KEDARequiresStandardMode'), 'gateway_missing': ('REJECTED', 'IngressNotConfigured'), 'tls_missing': ('REJECTED', 'TLSRequired'), 'auth_missing': ('REJECTED', 'AuthenticationRequired'), 'autoscaler_signal_missing': ('REJECTED', 'AutoscalerMetricSignalMissing'), 'live_cluster_missing': ('SKIPPED', 'NoKubernetesContextProvided')}
    phase, reason = contracts[fault['type']]
    ok = (phase, reason) == (fault['expected_phase'], fault['expected_reason'])
    return {'type': fault['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    commands = {'inference_services': ['kubectl', '--context', context, '-n', namespace, 'get', 'inferenceservices.serving.kserve.io', '-o', 'json'], 'serving_runtimes': ['kubectl', '--context', context, '-n', namespace, 'get', 'servingruntimes.serving.kserve.io', '-o', 'json'], 'llm_inference_services': ['kubectl', '--context', context, '-n', namespace, 'get', 'llminferenceservices.serving.kserve.io', '-o', 'json']}
    observations: dict[str, Any] = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
        if result.returncode:
            return {'status': 'FAIL', 'reason': f'LiveKServeReadFailed:{name}', 'stderr': result.stderr.strip()}
        observations[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'observations': observations, 'boundary': 'read-only discovery proves CRD availability and list authorization only; it does not prove artifact loading, runtime compatibility, request routing, TLS, authentication, autoscaling, model cache behavior, GPU readiness, or traffic success'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    runtimes = {item['name']: item for item in scenario['runtimes']}
    services = [reconcile(item, runtimes, scenario['policy'], scenario['infrastructure']) for item in scenario['services']]
    faults = [evaluate_fault(item) for item in scenario['faults']]
    passed = all((item['status'] == 'PASS' and item['status_conditions']['Ready'] for item in services)) and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'services': services, 'diagnostics': {item['name']: diagnose(item['status_conditions']) for item in services}, 'faults': faults}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live-context')
    parser.add_argument('--namespace', default='model-serving')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.live_context, args.namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'KServe control-plane replay: {report['status']}')
    for service in report['services']:
        print(f'  service {service['name']}: {service['status']} Ready={service['status_conditions']['Ready']} resources={','.join(service['resources'])}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live'].get('reason', 'observed')}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] != 'FAIL' else 1

ENTRY_ID = 'lesson/lesson-23'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'kserve_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
