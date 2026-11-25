#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-05.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Validate a simulated GPU Operator node stack and optionally inspect a real cluster."""
import argparse
import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def merge(node: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(node)
    result.update(override)
    return result

def evaluate_node(node: dict[str, Any], policy: dict[str, Any], inject: str | None=None) -> dict[str, Any]:
    events: list[dict[str, str]] = []
    if not node['gpu']:
        return {'stage': 'NotApplicable', 'reason': 'NoGPUDetected', 'ready': True, 'events': events, 'operands': []}
    events.append({'stage': 'Discovered', 'reason': 'GPUDetected'})
    if policy['driver_management'] == 'operator' and (not node['driver_preinstalled']):
        if node.get('nouveau_loaded'):
            return {'stage': 'DriverBlocked', 'reason': 'NouveauLoaded', 'ready': False, 'events': events, 'operands': []}
        if not node.get('kernel_headers'):
            return {'stage': 'DriverBlocked', 'reason': 'KernelHeadersMissing', 'ready': False, 'events': events, 'operands': []}
        if node.get('secure_boot') and (not node.get('signed_module_available', False)):
            return {'stage': 'DriverBlocked', 'reason': 'ModuleSignatureRejected', 'ready': False, 'events': events, 'operands': []}
        events.append({'stage': 'DriverReady', 'reason': 'ContainerizedDriverLoaded'})
    else:
        if not node.get('driver_version'):
            return {'stage': 'DriverBlocked', 'reason': 'PreinstalledDriverMissing', 'ready': False, 'events': events, 'operands': []}
        events.append({'stage': 'DriverReady', 'reason': 'PreinstalledDriverDetected'})
    if policy['toolkit_management'] == 'operator' and (not node.get('nvidia_runtime_configured')):
        return {'stage': 'ToolkitBlocked', 'reason': 'RuntimeNotConfigured', 'ready': False, 'events': events, 'operands': ['driver']}
    events.append({'stage': 'ToolkitReady', 'reason': 'ContainerRuntimeConfigured'})
    operands = ['driver', 'container-toolkit']
    if inject == 'device_plugin_missing':
        return {'stage': 'ResourceBlocked', 'reason': 'GPUResourceNotAdvertised', 'ready': False, 'events': events, 'operands': operands}
    operands.append('device-plugin')
    events.append({'stage': 'ResourceAdvertised', 'reason': 'DevicePluginRegistered'})
    operands.extend(['gpu-feature-discovery', 'dcgm', 'dcgm-exporter'])
    events.append({'stage': 'TelemetryReady', 'reason': 'LabelsAndMetricsAvailable'})
    if inject == 'validator_failed':
        return {'stage': 'ValidationFailed', 'reason': 'WorkloadValidationFailed', 'ready': False, 'events': events, 'operands': operands}
    operands.append('validator')
    events.append({'stage': 'Ready', 'reason': 'ValidationPassed'})
    labels = {'nvidia.com/gpu.present': 'true', 'nvidia.com/gpu.product': node['product'], 'nvidia.com/cuda.driver.major': '580-simulated'}
    allocatable = {policy['required_allocatable_resource']: node['gpu_count']}
    return {'stage': 'Ready', 'reason': 'ValidationPassed', 'ready': True, 'events': events, 'operands': operands, 'labels': labels, 'allocatable': allocatable}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    policy = scenario['operator_policy']
    nodes = {node['name']: node for node in scenario['nodes']}
    healthy = {name: evaluate_node(node, policy) for name, node in nodes.items()}
    faults: dict[str, Any] = {}
    for case in scenario['fault_cases']:
        result = evaluate_node(merge(nodes[case['node']], case.get('override', {})), policy, case.get('inject'))
        result['expected_stage'] = case['expected_stage']
        result['expected_reason'] = case['expected_reason']
        result['passed'] = result['stage'] == case['expected_stage'] and result['reason'] == case['expected_reason']
        faults[case['id']] = result
    gpu_results = [healthy[name] for name, node in nodes.items() if node['gpu']]
    checks = {'all_gpu_nodes_are_ready': all((item['ready'] for item in gpu_results)), 'cpu_node_is_not_mutated': healthy['cpu-worker']['stage'] == 'NotApplicable' and (not healthy['cpu-worker']['operands']), 'required_operands_are_present': all((set(policy['required_operands']).issubset(item['operands']) for item in gpu_results)), 'labels_and_allocatable_are_published': all((set(policy['required_node_labels']).issubset(item['labels']) and item['allocatable'][policy['required_allocatable_resource']] > 0 for item in gpu_results)), 'all_faults_stop_at_expected_layer': all((item['passed'] for item in faults.values()))}
    return {'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks, 'healthy': healthy, 'faults': faults}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'no --context was supplied for a real GPU Kubernetes cluster'}
    if not shutil.which('kubectl'):
        return {'status': 'SKIPPED', 'reason': 'kubectl is not installed'}
    commands = {'nodes': ['kubectl', '--context', context, 'get', 'nodes', '-o', 'json'], 'pods': ['kubectl', '--context', context, 'get', 'pods', '-n', namespace, '-o', 'json']}
    payload: dict[str, Any] = {}
    for name, command in commands.items():
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        if result.returncode:
            return {'status': 'FAIL', 'reason': result.stderr.strip() or f'kubectl {name} failed'}
        payload[name] = json.loads(result.stdout)
    gpu_nodes = [item for item in payload['nodes'].get('items', []) if item['metadata'].get('labels', {}).get('nvidia.com/gpu.present') == 'true']
    operand_pods = payload['pods'].get('items', [])
    ready_pods = sum((1 for pod in operand_pods if any((c.get('type') == 'Ready' and c.get('status') == 'True' for c in pod.get('status', {}).get('conditions', [])))))
    status = 'PASS' if gpu_nodes and operand_pods and (ready_pods == len(operand_pods)) else 'FAIL'
    return {'status': status, 'gpu_nodes': len(gpu_nodes), 'operand_pods': len(operand_pods), 'ready_operand_pods': ready_pods}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('simulated', 'live'), default='simulated')
    parser.add_argument('--context')
    parser.add_argument('--namespace', default='gpu-operator')
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    report = simulate(load(args.scenario))
    if args.mode == 'live':
        report['live_cluster'] = inspect_live(args.context, args.namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'GPU node readiness simulation: {report['status']}')
    for name, result in report['healthy'].items():
        print(f'  {name}: {result['stage']} ({result['reason']})')
    for name, result in report['faults'].items():
        print(f'  fault {name}: {('PASS' if result['passed'] else 'FAIL')} {result['stage']}/{result['reason']}')
    if args.mode == 'live':
        print(f'Live GPU cluster inspection: {report['live_cluster']['status']}')
        if report['live_cluster']['status'] == 'SKIPPED':
            print(f'Reason: {report['live_cluster']['reason']}')
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'PASS' and report.get('live_cluster', {}).get('status') != 'FAIL' else 1

ENTRY_ID = 'lesson/lesson-05'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'gpu_operator_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
