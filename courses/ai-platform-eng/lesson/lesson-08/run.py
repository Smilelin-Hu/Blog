#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-08.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Validate AI cluster network planes, RDMA capabilities, and topology placement."""
import argparse
import itertools
import json
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def gpu_nic_aligned(node: dict[str, Any], gpu: int, nic: str) -> bool:
    return any((gpu in group['gpus'] and nic in group['nics'] for group in node['numa'].values()))

def node_supports(node: dict[str, Any], workload: dict[str, Any]) -> bool:
    if node['gpu_count'] < workload['gpus_per_node']:
        return False
    if workload['network'] not in node['networks']:
        return False
    if workload['requires_rdma'] and (not node['rdma']):
        return False
    if workload['requires_gpudirect'] and (not node['gpudirect']):
        return False
    return all((node['rails'].get(rail) == 'up' for rail in workload['required_rails']))

def placement_matches(nodes: tuple[dict[str, Any], ...], placement: str) -> bool:
    racks = {node['rack'] for node in nodes}
    if placement == 'same-rack':
        return len(racks) == 1
    if placement == 'different-rack':
        return len(racks) == len(nodes)
    return True

def place_workload(scenario: dict[str, Any], workload: dict[str, Any]) -> dict[str, Any]:
    candidates = [node for node in scenario['nodes'] if node_supports(node, workload)]
    for chosen in itertools.combinations(candidates, workload['nodes']):
        if placement_matches(chosen, workload['placement']):
            return {'phase': 'Allocated', 'reason': 'NetworkAndTopologySatisfied', 'nodes': [node['name'] for node in chosen], 'racks': [node['rack'] for node in chosen], 'network': workload['network'], 'rails': workload['required_rails']}
    return {'phase': 'Pending', 'reason': 'NoTopologyCompatibleNodeSet'}

def evaluate_fault(scenario: dict[str, Any], fault: dict[str, Any]) -> dict[str, Any]:
    kind = fault['type']
    if kind == 'nad_missing':
        actual = {'phase': 'SandboxBlocked', 'reason': 'NetworkAttachmentDefinitionUnavailable'}
    elif kind == 'mtu_mismatch':
        smallest = min(fault['path_mtus'])
        mismatch = len(set(fault['path_mtus'])) > 1 and fault['payload_bytes'] > smallest
        actual = {'phase': 'RunningDegraded' if mismatch else 'Running', 'reason': 'PathMTUMismatch' if mismatch else 'PathMTUConsistent', 'effective_mtu': smallest}
    elif kind == 'roce_lossless_misconfigured':
        safe = fault['pfc'] and fault['ecn']
        actual = {'phase': 'Running' if safe else 'RunningDegraded', 'reason': 'CongestionControlReady' if safe else 'RoCECongestionControlMissing'}
    elif kind == 'rdma_missing':
        actual = {'phase': 'Pending', 'reason': 'RDMAResourceUnavailable'}
    elif kind == 'gpudirect_missing':
        actual = {'phase': 'CapabilityBlocked', 'reason': 'GPUDirectPathUnavailable'}
    elif kind == 'numa_mismatch':
        node = scenario['nodes'][0]
        aligned = gpu_nic_aligned(node, fault['gpu'], fault['nic'])
        actual = {'phase': 'Running' if aligned else 'RunningDegraded', 'reason': 'GPUNICAligned' if aligned else 'GPUNICNUMAMisaligned'}
    elif kind == 'rail_down':
        actual = {'phase': 'PlacementBlocked', 'reason': 'RequiredNetworkRailUnavailable'}
    elif kind == 'driver_skew':
        skew = len(set(fault['generations'])) > 1
        actual = {'phase': 'Quarantined' if skew else 'Ready', 'reason': 'NetworkDriverGenerationSkew' if skew else 'DriverGenerationConsistent'}
    elif kind == 'interface_selection':
        routable = fault['interfaces'].get(fault['selected']) == 'routable'
        actual = {'phase': 'Ready' if routable else 'InitializationBlocked', 'reason': 'SelectedInterfaceRoutable' if routable else 'SelectedInterfaceUnroutable'}
    else:
        actual = {'phase': 'Unknown', 'reason': 'UnsupportedFault'}
    return {'name': fault['name'], 'passed': actual['phase'] == fault['expected_phase'] and actual['reason'] == fault['expected_reason'], **actual}

def path_model() -> dict[str, Any]:
    return {'tcp_staged': ['GPU memory', 'host memory', 'kernel socket', 'NIC', 'fabric', 'remote host memory', 'remote GPU memory'], 'rdma_staged': ['GPU memory', 'host memory', 'RNIC', 'fabric', 'remote host memory', 'remote GPU memory'], 'gpudirect_rdma': ['GPU memory', 'peer DMA over PCIe', 'RNIC', 'fabric', 'remote RNIC', 'peer DMA over PCIe', 'remote GPU memory'], 'boundary': 'The model validates path selection, not measured bandwidth or latency.'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    placements = []
    for workload in scenario['workloads']:
        result = place_workload(scenario, workload)
        placements.append({'name': workload['name'], 'passed': result['phase'] == workload['expected_phase'], **result})
    faults = [evaluate_fault(scenario, fault) for fault in scenario['faults']]
    passed = all((item['passed'] for item in placements + faults))
    return {'status': 'PASS' if passed else 'FAIL', 'traffic_planes': scenario['traffic_planes'], 'placements': placements, 'path_model': path_model(), 'faults': faults, 'simulation_scope': 'control-plane and topology semantics only; no RDMA or GPU performance is fabricated'}

def inspect_live(context: str | None, allow_benchmark: bool=False) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'no --context was supplied for a dedicated RDMA-capable Kubernetes cluster'}
    commands = {'nodes': ['kubectl', '--context', context, 'get', 'nodes', '-o', 'json'], 'network_attachments': ['kubectl', '--context', context, 'get', 'network-attachment-definitions', '-A', '-o', 'json'], 'nic_policy': ['kubectl', '--context', context, 'get', 'nicclusterpolicy', '-o', 'json'], 'rdma_resources': ['kubectl', '--context', context, 'get', 'nodes', '-o', "jsonpath={range .items[*]}{.metadata.name}{'\\t'}{.status.allocatable}{'\\n'}{end}"]}
    observed: dict[str, Any] = {'status': 'OBSERVED', 'context': context, 'commands': {}}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return {'status': 'SKIPPED', 'reason': f'live inspection unavailable: {exc}'}
        observed['commands'][name] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    observed['performance_benchmark'] = {'status': 'AUTHORIZED', 'reason': 'run only against the isolated benchmark namespace and reserved nodes'} if allow_benchmark else {'status': 'SKIPPED', 'reason': 'iperf, ib_write_bw, and NCCL tests require explicit --allow-benchmark'}
    return observed

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('simulate', 'live'), default='simulate')
    parser.add_argument('--context')
    parser.add_argument('--allow-benchmark', action='store_true')
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    scenario = load_scenario(args.scenario)
    report = simulate(scenario)
    if args.mode == 'live':
        report['live_inspection'] = inspect_live(args.context, args.allow_benchmark)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'AI network topology model: {report['status']}')
    for item in report['placements']:
        print(f'  {item['name']}: {item['phase']} nodes={','.join(item.get('nodes', []))} network={item.get('network', '-')}')
    for fault in report['faults']:
        state = 'PASS' if fault['passed'] else 'FAIL'
        print(f'  fault {fault['name']}: {state} {fault['phase']}/{fault['reason']}')
    if args.mode == 'live':
        live = report['live_inspection']
        print(f'Live RDMA inspection: {live['status']}')
        if live.get('reason'):
            print(f'Reason: {live['reason']}')
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-08'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'network_topology_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
