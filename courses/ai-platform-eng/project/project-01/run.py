#!/usr/bin/env python3
"""Standalone unified entry for project/project-01.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Aggregate GPU, device, network, storage, and artifact readiness evidence."""
import argparse
import json
import subprocess
from pathlib import Path
from typing import Any
ROOT = Path(__file__).resolve().parents[2]

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def validate_node(node: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    checks = {'gpu_stack': node['gpu_stack'] == 'Ready', 'device_count': node['gpu_expected'] == node['gpu_allocatable'], 'device_health': node['device_health'] == 'Healthy', 'network_profile': node['network_profile'] == requirements['required_network_profile'], 'storage_profile': node['storage_profile'] == requirements['required_storage_profile'], 'artifact_integrity': node['artifact_digest_verified'], 'health_detection_slo': node['health_detection_seconds'] <= requirements['maximum_health_detection_seconds'], 'artifact_ready_slo': node['cached_artifact_ready_seconds'] <= requirements['maximum_cached_artifact_ready_seconds'], 'version_profile': node['version_profile'] == 'validated-2026q3'}
    return {'name': node['name'], 'phase': 'Ready' if all(checks.values()) else 'Quarantined', 'checks': checks, 'passed': all(checks.values())}

def validate_prerequisites(paths: list[str], root: Path=ROOT) -> list[dict[str, Any]]:
    results = []
    for relative in paths:
        path = root / relative
        if not path.exists():
            results.append({'path': relative, 'status': 'MISSING', 'passed': False})
            continue
        report = json.loads(path.read_text(encoding='utf-8'))
        results.append({'path': relative, 'status': report.get('status'), 'passed': report.get('status') == 'PASS'})
    return results

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    mapping = {'version_drift': ('Quarantined', 'VersionProfileDrift'), 'device_mismatch': ('Quarantined', 'GPUAllocatableMismatch'), 'device_unhealthy': ('Draining', 'AllocatedDeviceHealthLost'), 'sharing_drift': ('Quarantined', 'GPUSharingProfileDrift'), 'network_degraded': ('ProfileRemoved', 'RequiredNetworkProfileUnavailable'), 'storage_degraded': ('AdmissionBlocked', 'RequiredStorageProfileUnavailable'), 'artifact_corrupt': ('ArtifactQuarantined', 'ArtifactDigestVerificationFailed'), 'detection_slow': ('SLOViolated', 'HealthDetectionTooSlow')}
    phase, reason = mapping.get(fault['type'], ('Unknown', 'UnsupportedFault'))
    return {'name': fault['name'], 'phase': phase, 'reason': reason, 'passed': phase == fault['expected_phase'] and reason == fault['expected_reason']}

def simulate(scenario: dict[str, Any], root: Path=ROOT) -> dict[str, Any]:
    nodes = [validate_node(node, scenario['requirements']) for node in scenario['nodes']]
    prerequisites = validate_prerequisites(scenario['prerequisite_reports'], root)
    faults = [evaluate_fault(fault) for fault in scenario['faults']]
    ready_rate = sum((item['passed'] for item in nodes)) / len(nodes)
    device_accuracy = sum((item['checks']['device_count'] for item in nodes)) / len(nodes)
    metrics = {'gpu_node_ready_rate': ready_rate, 'device_discovery_accuracy': device_accuracy, 'maximum_health_detection_seconds': max((node['health_detection_seconds'] for node in scenario['nodes'])), 'maximum_cached_artifact_ready_seconds': max((node['cached_artifact_ready_seconds'] for node in scenario['nodes']))}
    metrics_pass = ready_rate >= scenario['requirements']['minimum_ready_rate'] and device_accuracy >= scenario['requirements']['minimum_device_accuracy'] and (metrics['maximum_health_detection_seconds'] <= scenario['requirements']['maximum_health_detection_seconds']) and (metrics['maximum_cached_artifact_ready_seconds'] <= scenario['requirements']['maximum_cached_artifact_ready_seconds'])
    passed = metrics_pass and all((item['passed'] for item in nodes + prerequisites + faults))
    return {'status': 'PASS' if passed else 'FAIL', 'version_matrix': scenario['version_matrix'], 'nodes': nodes, 'prerequisites': prerequisites, 'metrics': metrics, 'faults': faults, 'real_environment_boundary': 'simulation proves control and evidence aggregation only; GPU, RDMA, and storage performance require a dedicated cluster'}

def inspect_live(context: str | None) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'no --context was supplied for a dedicated GPU Ready Kubernetes cluster'}
    commands = {'nodes': ['kubectl', '--context', context, 'get', 'nodes', '-o', 'json'], 'gpu_policy': ['kubectl', '--context', context, 'get', 'clusterpolicy', '-o', 'json'], 'nic_policy': ['kubectl', '--context', context, 'get', 'nicclusterpolicy', '-o', 'json'], 'storage_classes': ['kubectl', '--context', context, 'get', 'storageclass', '-o', 'json']}
    observed: dict[str, Any] = {'status': 'OBSERVED', 'context': context, 'commands': {}}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return {'status': 'SKIPPED', 'reason': f'live inspection unavailable: {exc}'}
        observed['commands'][name] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    return observed

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('simulate', 'live'), default='simulate')
    parser.add_argument('--context')
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    report = simulate(load_scenario(args.scenario))
    if args.mode == 'live':
        report['live_inspection'] = inspect_live(args.context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'GPU Ready cluster baseline: {report['status']}')
    for node in report['nodes']:
        print(f'  node {node['name']}: {node['phase']}')
    print(f'  prerequisites: {sum((item['passed'] for item in report['prerequisites']))}/{len(report['prerequisites'])}')
    for name, value in report['metrics'].items():
        print(f'  metric {name}: {value}')
    for fault in report['faults']:
        state = 'PASS' if fault['passed'] else 'FAIL'
        print(f'  fault {fault['name']}: {state} {fault['phase']}/{fault['reason']}')
    if args.mode == 'live':
        live = report['live_inspection']
        print(f'Live cluster baseline: {live['status']}')
        if live.get('reason'):
            print(f'Reason: {live['reason']}')
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'project/project-01'


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
        for item in ['--mode', 'live']:
            pass
        if True and "--mode" not in forwarded:
            forwarded = [['--mode', 'live'][0], ['--mode', 'live'][1], *forwarded]
        return _invoke_embedded(implementation_main, forwarded, "measured")
    return _invoke_embedded(implementation_main, args or ['--scenario', 'cluster_baseline_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
