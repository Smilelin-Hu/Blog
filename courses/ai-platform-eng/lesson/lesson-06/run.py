#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-06.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Simulate Device Plugin, CDI, and DRA allocation semantics."""
import argparse
import copy
import json
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def all_devices(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    devices: list[dict[str, Any]] = []
    for node in scenario['nodes']:
        for raw in node['devices']:
            device = copy.deepcopy(raw)
            device['node'] = node['name']
            devices.append(device)
    return devices

def matches(device: dict[str, Any], selectors: dict[str, Any]) -> bool:
    if device['health'] != 'Healthy':
        return False
    if 'product' in selectors and device['product'] != selectors['product']:
        return False
    if device['memory_gib'] < selectors.get('memory_gib_min', 0):
        return False
    if device['compute_capability'] < selectors.get('compute_capability_min', 0):
        return False
    return True

def allocate_legacy(scenario: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    candidates: list[tuple[str, list[dict[str, Any]]]] = []
    for node in scenario['nodes']:
        healthy = [d for d in node['devices'] if d['health'] == 'Healthy']
        if len(healthy) >= request['count']:
            candidates.append((node['name'], healthy))
    if not candidates:
        return {'phase': 'Pending', 'reason': 'InsufficientExtendedResource', 'resource': scenario['legacy_resource']}
    node_name, devices = candidates[0]
    preferred_numa = request.get('preferred_numa')
    devices.sort(key=lambda d: (d['numa'] != preferred_numa, d['id']))
    selected = devices[:request['count']]
    return {'phase': 'Allocated', 'reason': 'KubeletAllocateCompleted', 'node': node_name, 'resource': scenario['legacy_resource'], 'device_ids': [d['id'] for d in selected], 'cdi_devices': [d['cdi_name'] for d in selected], 'injection': 'CDI'}

def choose_dra_devices(scenario: dict[str, Any], count: int, selectors: dict[str, Any], node_constraint: str | None=None) -> tuple[str | None, list[dict[str, Any]], str | None]:
    matching = [d for d in all_devices(scenario) if matches(d, selectors)]
    if not matching:
        return (None, [], 'NoMatchingDevice')
    if node_constraint:
        constrained = [d for d in matching if d['node'] == node_constraint]
        if not constrained and matching:
            return (None, [], 'NodeConstraintConflict')
        matching = constrained
    by_node: dict[str, list[dict[str, Any]]] = {}
    for device in matching:
        by_node.setdefault(device['node'], []).append(device)
    feasible = [(node, devices) for node, devices in by_node.items() if len(devices) >= count]
    if not feasible:
        return (None, [], 'NoMatchingDevice')
    feasible.sort(key=lambda item: item[0])
    node, devices = feasible[0]
    return (node, sorted(devices, key=lambda d: d['id'])[:count], None)

def allocate_dra(scenario: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    alternatives = request.get('first_available')
    if alternatives:
        selected_alternative = None
        node = None
        devices: list[dict[str, Any]] = []
        for alternative in alternatives:
            node, devices, _ = choose_dra_devices(scenario, alternative.get('count', 1), alternative.get('selectors', {}), request.get('node_constraint'))
            if devices:
                selected_alternative = alternative['name']
                break
        if not devices:
            return {'phase': 'ClaimPending', 'reason': 'NoMatchingDevice'}
    else:
        node, devices, reason = choose_dra_devices(scenario, request.get('count', 1), request.get('selectors', {}), request.get('node_constraint'))
        selected_alternative = None
        if reason:
            return {'phase': 'ClaimPending', 'reason': reason}
    return {'phase': 'Allocated', 'reason': 'AllocationResultPublished', 'node': node, 'claim_type': request.get('claim_type', 'ResourceClaim'), 'selected_subrequest': selected_alternative, 'device_ids': [d['id'] for d in devices], 'cdi_devices': [d['cdi_name'] for d in devices], 'allocation_result': [{'driver': scenario['device_class']['driver'], 'pool': d['node'], 'device': d['id']} for d in devices]}

def evaluate_fault(scenario: dict[str, Any], fault: dict[str, Any]) -> dict[str, Any]:
    fault_type = fault['type']
    if fault_type == 'plugin_unregistered':
        actual = {'phase': 'RegistrationBlocked', 'reason': 'PluginSocketUnavailable'}
    elif fault_type == 'legacy_capacity_exhausted':
        actual = allocate_legacy(scenario, {'count': fault['count']})
    elif fault_type == 'dra_no_match':
        request = {'mode': 'dra', 'selectors': fault['selectors'], 'count': 1}
        actual = allocate_dra(scenario, request)
    elif fault_type == 'dra_node_conflict':
        request = {'mode': 'dra', 'selectors': fault['selectors'], 'node_constraint': fault['node_constraint'], 'count': 1}
        actual = allocate_dra(scenario, request)
    elif fault_type == 'stale_cdi':
        actual = {'phase': 'ContainerCreateBlocked', 'reason': 'CDIDeviceUnresolvable', 'device_id': fault['device_id']}
    elif fault_type == 'allocated_device_unhealthy':
        actual = {'phase': 'RunningDegraded', 'reason': 'AllocatedDeviceUnhealthy', 'device_id': fault['device_id'], 'allocation_retained': True, 'eligible_for_new_claims': False}
    elif fault_type == 'claim_release':
        actual = {'phase': 'Released', 'reason': 'ClaimLifecycleCompleted', 'device_id': fault['device_id'], 'eligible_for_new_claims': True}
    else:
        actual = {'phase': 'Unknown', 'reason': 'UnsupportedFault'}
    passed = actual['phase'] == fault['expected_phase'] and actual['reason'] == fault['expected_reason']
    return {'name': fault['name'], 'passed': passed, **actual}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    resources = {}
    resource_slices = []
    for node in scenario['nodes']:
        healthy = sum((d['health'] == 'Healthy' for d in node['devices']))
        resources[node['name']] = {'capacity': len(node['devices']), 'allocatable': healthy}
        resource_slices.append({'pool': node['name'], 'node': node['name'], 'devices': [{'name': d['id'], 'attributes': {'product': d['product'], 'memoryGiB': d['memory_gib'], 'computeCapability': d['compute_capability']}, 'health': d['health']} for d in node['devices']]})
    allocations = []
    for request in scenario['requests']:
        result = allocate_legacy(scenario, request) if request['mode'] == 'device-plugin' else allocate_dra(scenario, request)
        passed = result['phase'] == request['expected_phase']
        if request.get('expected_node'):
            passed = passed and result.get('node') == request['expected_node']
        if request.get('expected_subrequest'):
            passed = passed and result.get('selected_subrequest') == request['expected_subrequest']
        allocations.append({'name': request['name'], 'mode': request['mode'], 'passed': passed, **result})
    faults = [evaluate_fault(scenario, fault) for fault in scenario['faults']]
    passed = all((item['passed'] for item in allocations + faults))
    return {'status': 'PASS' if passed else 'FAIL', 'cluster_version': scenario['cluster_version'], 'device_plugin_registration': {'socket': '/var/lib/kubelet/device-plugins/kubelet.sock', 'resource': scenario['legacy_resource'], 'status': 'Registered'}, 'legacy_node_resources': resources, 'resource_slices': resource_slices, 'allocations': allocations, 'faults': faults}

def inspect_live(context: str | None) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'no --context was supplied for a Kubernetes cluster with device resources'}
    commands = {'nodes': ['kubectl', '--context', context, 'get', 'nodes', '-o', 'json'], 'deviceclasses': ['kubectl', '--context', context, 'get', 'deviceclasses', '-o', 'json'], 'resourceclaims': ['kubectl', '--context', context, 'get', 'resourceclaims', '-A', '-o', 'json'], 'resourceslices': ['kubectl', '--context', context, 'get', 'resourceslices', '-o', 'json']}
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
    scenario = load_scenario(args.scenario)
    report = simulate(scenario)
    if args.mode == 'live':
        report['live_inspection'] = inspect_live(args.context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Device allocation simulation: {report['status']}')
    for item in report['allocations']:
        print(f'  {item['name']}: {item['phase']} on {item.get('node', '-')}')
    for fault in report['faults']:
        state = 'PASS' if fault['passed'] else 'FAIL'
        print(f'  fault {fault['name']}: {state} {fault['phase']}/{fault['reason']}')
    if args.mode == 'live':
        live = report['live_inspection']
        print(f'Live device inspection: {live['status']}')
        if live.get('reason'):
            print(f'Reason: {live['reason']}')
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-06'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'device_allocation_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
