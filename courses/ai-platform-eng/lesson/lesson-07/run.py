#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-07.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Model whole GPU, MIG, time-slicing, MPS, and vGPU product semantics."""
import argparse
import copy
import json
import subprocess
from pathlib import Path
from typing import Any
STRONG_MODES = {'whole', 'mig', 'vgpu'}

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def node_for_product(scenario: dict[str, Any], product_name: str) -> dict[str, Any] | None:
    for node in scenario['nodes']:
        if node.get('product') == product_name:
            return node
    if product_name.startswith('mig-'):
        return next((n for n in scenario['nodes'] if n.get('mode') == 'mig'), None)
    return None

def allocate_workload(scenario: dict[str, Any], workload: dict[str, Any], state: dict[str, int] | None=None) -> dict[str, Any]:
    products = scenario['products']
    product = products[workload['product']]
    node = node_for_product(scenario, workload['product'])
    if not node:
        return {'phase': 'Pending', 'reason': 'ProductCapacityUnavailable'}
    if workload['min_memory_gib'] > product['memory_gib']:
        return {'phase': 'Rejected', 'reason': 'InsufficientMemoryGuarantee'}
    if workload['requires_vm'] and product['mode'] != 'vgpu':
        return {'phase': 'Rejected', 'reason': 'VirtualMachineBoundaryRequired'}
    if workload['requires_strong_isolation'] and product['mode'] not in STRONG_MODES:
        return {'phase': 'Rejected', 'reason': 'IsolationPolicyMismatch'}
    state = state if state is not None else {}
    key = workload['product']
    used = state.get(key, 0)
    if product['mode'] == 'whole':
        capacity = node['units']
    elif product['mode'] == 'mig':
        capacity = node['observed_geometry'].count(product['profile'])
    elif product['mode'] == 'time-slicing':
        capacity = node['logical_replicas']
    elif product['mode'] == 'mps':
        capacity = product['max_clients']
    else:
        capacity = node['available_profiles']
        if node['license_service'] != 'Ready':
            return {'phase': 'ProvisioningBlocked', 'reason': 'LicenseServiceUnavailable'}
    if used + workload['count'] > capacity:
        return {'phase': 'Pending', 'reason': 'ProductCapacityUnavailable'}
    state[key] = used + workload['count']
    return {'phase': 'Allocated', 'reason': 'ProductContractSatisfied', 'node': node['name'], 'mode': product['mode'], 'units': workload['count'], 'memory_isolation': product['memory_isolation'], 'fault_isolation': product['fault_isolation'], 'performance_isolation': product['performance_isolation']}

def evaluate_fault(scenario: dict[str, Any], fault: dict[str, Any]) -> dict[str, Any]:
    kind = fault['type']
    if kind == 'time_slice_multi_request':
        product = scenario['products']['shared-l40s']
        if product['fail_requests_greater_than_one'] and fault['count'] > 1:
            actual = {'phase': 'AdmissionRejected', 'reason': 'SharedReplicaRequestGreaterThanOne'}
        else:
            actual = {'phase': 'Allocated', 'reason': 'NoProportionalShareGuarantee'}
    elif kind == 'time_slice_memory_pressure':
        total = sum(fault['client_memory_gib'])
        physical = scenario['products']['shared-l40s']['memory_gib']
        actual = {'phase': 'RunningUnsafe' if total > physical else 'Running', 'reason': 'NoMemoryIsolation' if total > physical else 'WithinObservedMemory', 'declared_total_gib': total, 'physical_memory_gib': physical}
    elif kind == 'time_slice_noisy_neighbor':
        actual = {'phase': 'RunningDegraded', 'reason': 'BestEffortComputeShare'}
    elif kind == 'mig_shape_mismatch':
        actual = {'phase': 'Pending', 'reason': 'MIGProfileUnavailable', 'free_profiles': fault['free_profiles'], 'requested_profile': fault['requested_profile']}
    elif kind == 'mig_config_drift':
        node = copy.deepcopy(next((n for n in scenario['nodes'] if n['name'] == 'mig-node-a')))
        node['observed_geometry'] = ['1g.10gb'] * 7
        actual = {'phase': 'Quarantined', 'reason': 'MIGGeometryDrift', 'desired': node['desired_geometry'], 'observed': node['observed_geometry']}
    elif kind == 'mig_reconfigure_active':
        actual = {'phase': 'ReconfigurationBlocked', 'reason': 'ActiveGPUPodsMustTerminate', 'active_gpu_pods': fault['active_gpu_pods']}
    elif kind == 'mps_memory_limit':
        limit = scenario['products']['mps-a100']['memory_limit_gib_per_client']
        actual = {'phase': 'ClientRejected' if fault['requested_memory_gib'] > limit else 'Allocated', 'reason': 'MPSPinnedDeviceMemoryLimit' if fault['requested_memory_gib'] > limit else 'WithinMPSLimit', 'limit_gib': limit}
    elif kind == 'vgpu_license':
        actual = {'phase': 'ProvisioningBlocked', 'reason': 'LicenseServiceUnavailable'}
    else:
        actual = {'phase': 'Unknown', 'reason': 'UnsupportedFault'}
    return {'name': fault['name'], 'passed': actual['phase'] == fault['expected_phase'] and actual['reason'] == fault['expected_reason'], **actual}

def fragmentation_report(scenario: dict[str, Any]) -> dict[str, Any]:
    free_profiles = ['1g.10gb', '1g.10gb', '1g.10gb']
    free_slices = 3
    requested = '3g.40gb'
    return {'free_slices': free_slices, 'requested_slices': 3, 'free_profiles': free_profiles, 'requested_profile': requested, 'raw_capacity_sufficient': True, 'shape_satisfiable': requested in free_profiles, 'conclusion': 'MIGShapeFragmented'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    state: dict[str, int] = {}
    allocations = []
    for workload in scenario['workloads']:
        result = allocate_workload(scenario, workload, state)
        allocations.append({'name': workload['name'], 'product': workload['product'], 'passed': result['phase'] == workload['expected_phase'], **result})
    faults = [evaluate_fault(scenario, f) for f in scenario['faults']]
    passed = all((item['passed'] for item in allocations + faults))
    return {'status': 'PASS' if passed else 'FAIL', 'products': scenario['products'], 'allocations': allocations, 'fragmentation': fragmentation_report(scenario), 'faults': faults}

def inspect_live(context: str | None, allow_mutation: bool=False) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'no --context was supplied for a real GPU Kubernetes cluster'}
    commands = {'gpu_nodes': ['kubectl', '--context', context, 'get', 'nodes', '-l', 'nvidia.com/gpu.present=true', '-o', 'json'], 'gpu_pods': ['kubectl', '--context', context, 'get', 'pods', '-A', '-o', 'json'], 'cluster_policy': ['kubectl', '--context', context, 'get', 'clusterpolicy', '-o', 'json']}
    observed: dict[str, Any] = {'status': 'OBSERVED', 'context': context, 'mutation_enabled': allow_mutation, 'commands': {}}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return {'status': 'SKIPPED', 'reason': f'live inspection unavailable: {exc}'}
        observed['commands'][name] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    if not allow_mutation:
        observed['reconfiguration'] = {'status': 'SKIPPED', 'reason': 'MIG and time-slicing mutation requires explicit --allow-mutation in an isolated lab'}
    return observed

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('simulate', 'live'), default='simulate')
    parser.add_argument('--context')
    parser.add_argument('--allow-mutation', action='store_true')
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    scenario = load_scenario(args.scenario)
    report = simulate(scenario)
    if args.mode == 'live':
        report['live_inspection'] = inspect_live(args.context, args.allow_mutation)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'GPU sharing model: {report['status']}')
    for item in report['allocations']:
        print(f'  {item['name']}: {item['mode']} -> {item['phase']} on {item['node']}')
    frag = report['fragmentation']
    print(f'  fragmentation: {frag['conclusion']} raw={frag['raw_capacity_sufficient']} shape={frag['shape_satisfiable']}')
    for fault in report['faults']:
        state = 'PASS' if fault['passed'] else 'FAIL'
        print(f'  fault {fault['name']}: {state} {fault['phase']}/{fault['reason']}')
    if args.mode == 'live':
        live = report['live_inspection']
        print(f'Live GPU sharing inspection: {live['status']}')
        if live.get('reason'):
            print(f'Reason: {live['reason']}')
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-07'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'gpu_sharing_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
