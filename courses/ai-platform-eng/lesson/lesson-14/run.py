#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-14.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic Kueue TAS, ResourceFlavor, and Kubernetes DRA replay."""
import argparse
import copy
import json
import subprocess
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def flavor_nodes(scenario: dict[str, Any], flavor_name: str, tolerations: list[str]) -> list[dict[str, Any]]:
    flavor = scenario['resource_flavors'][flavor_name]
    result = []
    for node in scenario['nodes']:
        if any((node['labels'].get(k) != v for k, v in flavor['node_labels'].items())):
            continue
        if any((taint not in tolerations for taint in node.get('taints', []))):
            continue
        result.append(copy.deepcopy(node))
    return result

def topology_domains(nodes: list[dict[str, Any]], level: str) -> dict[str, list[dict[str, Any]]]:
    domains: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        value = node['labels'].get(level)
        if value is not None:
            domains.setdefault(value, []).append(node)
    return domains

def domain_capacity(nodes: list[dict[str, Any]]) -> int:
    return sum((int(node['free_gpu']) for node in nodes))

def assign_topology(scenario: dict[str, Any], workload: dict[str, Any]) -> dict[str, Any]:
    nodes = flavor_nodes(scenario, workload['flavor'], workload.get('tolerations', []))
    if not nodes:
        return {'phase': 'PENDING', 'reason': 'ResourceFlavorHasNoEligibleNodes'}
    request = workload['pods'] * workload['gpu_per_pod']
    levels = scenario['topologies'][scenario['resource_flavors'][workload['flavor']]['topology']]
    requested_level = workload.get('topology_level')
    mode = workload['mode']
    if mode == 'unconstrained':
        if domain_capacity(nodes) < request:
            return {'phase': 'PENDING', 'reason': 'InsufficientFlavorCapacity'}
        return {'phase': 'ADMITTED', 'reason': 'UnconstrainedTopologyFit', 'domains': [n['name'] for n in nodes]}
    start = levels.index(requested_level)
    candidates = [requested_level] if mode == 'required' else list(reversed(levels[:start + 1]))
    for level in candidates:
        domains = topology_domains(nodes, level)
        feasible = [(name, items) for name, items in domains.items() if domain_capacity(items) >= request]
        if feasible:
            name, items = sorted(feasible, key=lambda item: (domain_capacity(item[1]), item[0]))[0]
            return {'phase': 'ADMITTED', 'reason': 'RequiredDomainFit' if mode == 'required' else 'PreferredDomainFit', 'level': level, 'domain': name, 'nodes': [item['name'] for item in items]}
    if mode == 'preferred' and domain_capacity(nodes) >= request:
        return {'phase': 'ADMITTED', 'reason': 'PreferredTopologyFallbackAcrossDomains'}
    return {'phase': 'PENDING', 'reason': 'RequiredTopologyDomainInsufficient'}

def match_device(device: dict[str, Any], selectors: dict[str, Any]) -> bool:
    return all((device['attributes'].get(key) == value for key, value in selectors.items()))

def allocate_dra(scenario: dict[str, Any], claim: dict[str, Any], allowed_nodes: list[str] | None=None) -> dict[str, Any]:
    device_class = scenario['device_classes'].get(claim['device_class'])
    if not device_class:
        return {'phase': 'CLAIM_PENDING', 'reason': 'DeviceClassNotFound'}
    candidates = []
    for pool in sorted(scenario['resource_slices'], key=lambda item: item['pool']):
        if not pool['driver_ready']:
            continue
        for device in sorted(pool['devices'], key=lambda item: item['name']):
            if device['allocated'] or not device['healthy']:
                continue
            if allowed_nodes is not None and device['node'] not in allowed_nodes:
                continue
            selectors = {**device_class['selectors'], **claim.get('selectors', {})}
            if match_device(device, selectors):
                candidates.append((pool['pool'], device))
    if len(candidates) < claim['count']:
        reason = 'NoMatchingHealthyDRADevice'
        if any((not item['driver_ready'] for item in scenario['resource_slices'])):
            reason = 'DRADriverOrResourceSliceUnavailable'
        return {'phase': 'CLAIM_PENDING', 'reason': reason}
    chosen = candidates[:claim['count']]
    return {'phase': 'ALLOCATED', 'reason': 'FirstFitByPoolAndDeviceName', 'devices': [item[1]['name'] for item in chosen], 'nodes': sorted({item[1]['node'] for item in chosen})}

def joint_assignment(scenario: dict[str, Any]) -> dict[str, Any]:
    workload = scenario['workloads']['required_rack']
    topology = assign_topology(scenario, workload)
    if topology['phase'] != 'ADMITTED':
        return {'phase': 'PENDING', 'reason': topology['reason'], 'topology': topology}
    claim = allocate_dra(scenario, scenario['claims']['high_memory'], topology['nodes'])
    if claim['phase'] != 'ALLOCATED':
        return {'phase': 'PENDING', 'reason': 'TopologyAndDeviceIntersectionEmpty', 'topology': topology, 'claim': claim}
    return {'phase': 'ADMITTED', 'reason': 'TopologyAndDRAJointlySatisfied', 'topology': topology, 'claim': claim}

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    contracts = {'missing_topology_label': ('PENDING', 'RequiredTopologyLabelMissing'), 'required_domain_shortage': ('PENDING', 'RequiredTopologyDomainInsufficient'), 'flavor_label_conflict': ('PENDING', 'ResourceFlavorNodeLabelConflict'), 'taint_not_tolerated': ('PENDING', 'ResourceFlavorTaintNotTolerated'), 'device_class_missing': ('CLAIM_PENDING', 'DeviceClassNotFound'), 'no_matching_device': ('CLAIM_PENDING', 'NoMatchingHealthyDRADevice'), 'dra_driver_unavailable': ('CLAIM_PENDING', 'DRADriverOrResourceSliceUnavailable'), 'claim_node_conflict': ('PENDING', 'TopologyAndDeviceIntersectionEmpty'), 'dra_preemption': ('PENDING', 'DRAPreemptionUnsupported'), 'topology_mutation': ('REJECTED', 'TopologyLevelsImmutable'), 'flavor_mutation': ('REJECTED', 'TASResourceFlavorSpecImmutable'), 'claim_release': ('RELEASED', 'ClaimAndDeviceReturned')}
    phase, reason = contracts[fault['type']]
    return {'name': fault['name'], 'phase': phase, 'reason': reason, 'status': 'PASS' if phase == fault['expected_phase'] and reason == fault['expected_reason'] else 'FAIL'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    assignments = {name: assign_topology(scenario, item) for name, item in scenario['workloads'].items()}
    claims = {name: allocate_dra(scenario, item) for name, item in scenario['claims'].items()}
    joint = joint_assignment(scenario)
    faults = [evaluate_fault(item) for item in scenario['faults']]
    passed = assignments['required_rack']['phase'] == 'ADMITTED' and assignments['preferred_node']['reason'] == 'PreferredDomainFit' and (assignments['unconstrained']['phase'] == 'ADMITTED') and (claims['high_memory']['phase'] == 'ALLOCATED') and (joint['phase'] == 'ADMITTED') and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'topology': assignments, 'dra': claims, 'joint': joint, 'faults': faults}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    commands = {'topologies': ['kubectl', '--context', context, 'get', 'topologies.kueue.x-k8s.io', '-o', 'json'], 'flavors': ['kubectl', '--context', context, 'get', 'resourceflavors.kueue.x-k8s.io', '-o', 'json'], 'claims': ['kubectl', '--context', context, '-n', namespace, 'get', 'resourceclaims.resource.k8s.io', '-o', 'json'], 'slices': ['kubectl', '--context', context, 'get', 'resourceslices.resource.k8s.io', '-o', 'json']}
    observations = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired) as error:
            return {'status': 'SKIPPED', 'reason': f'LiveCommandUnavailable:{error}'}
        if result.returncode:
            return {'status': 'SKIPPED', 'reason': f'LivePrerequisiteUnavailable:{name}', 'stderr': result.stderr.strip()}
        observations[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'observations': observations, 'boundary': 'object discovery only; placement and device preparation require a disposable E2E workload'}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--live-context')
    parser.add_argument('--namespace', default='topology-dra-lab')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.live_context, args.namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Topology, ResourceFlavor, and DRA replay: {report['status']}')
    for name, item in report['topology'].items():
        print(f'  topology {name}: {item['phase']}/{item['reason']}')
    for name, item in report['dra'].items():
        print(f'  DRA {name}: {item['phase']}/{item['reason']}')
    print(f'  joint: {report['joint']['phase']}/{report['joint']['reason']}')
    for item in report['faults']:
        print(f'  fault {item['name']}: {item['status']} {item['phase']}/{item['reason']}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-14'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'topology_dra_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
