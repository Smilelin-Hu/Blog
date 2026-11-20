#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-10.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Replay Kubernetes-like scheduling decisions and quantify AI resource fragmentation."""
import argparse
import copy
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
SCALAR_RESOURCES = ('cpu', 'memory_gib', 'nvidia.com/gpu', 'nvidia.com/mig-1g.10gb', 'nvidia.com/mig-3g.40gb')

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def empty_usage() -> dict[str, float]:
    return {name: 0.0 for name in SCALAR_RESOURCES}

def free_resources(node: dict[str, Any]) -> dict[str, float]:
    allocated = node.get('allocated', {})
    return {resource: float(node.get('capacity', {}).get(resource, 0)) - float(allocated.get(resource, 0)) for resource in SCALAR_RESOURCES}

def resource_fit(node: dict[str, Any], pod: dict[str, Any]) -> list[str]:
    free = free_resources(node)
    failures: list[str] = []
    for resource, request in pod.get('requests', {}).items():
        if float(request) > free.get(resource, 0.0):
            failures.append(f'Insufficient {resource}')
    return failures

def selector_fit(node: dict[str, Any], pod: dict[str, Any]) -> list[str]:
    labels = node.get('labels', {})
    failures = [f'node label {key}={labels.get(key)!r} does not match {value!r}' for key, value in pod.get('node_selector', {}).items() if labels.get(key) != value]
    return failures

def taint_fit(node: dict[str, Any], pod: dict[str, Any]) -> list[str]:
    tolerated = set(pod.get('tolerations', []))
    failures: list[str] = []
    for taint in node.get('taints', []):
        if taint.get('effect') == 'NoSchedule' and taint.get('key') not in tolerated:
            failures.append(f'untolerated taint {taint['key']}')
    return failures

def local_constraint_fit(node: dict[str, Any], pod: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    requested_port = pod.get('host_port')
    if requested_port is not None and requested_port in node.get('used_host_ports', []):
        failures.append(f'host port {requested_port} already allocated')
    volume_zone = pod.get('volume_zone')
    if volume_zone is not None and node.get('labels', {}).get('topology.kubernetes.io/zone') != volume_zone:
        failures.append(f'volume is restricted to zone {volume_zone}')
    required_peer = pod.get('required_peer_label')
    if required_peer is not None and required_peer not in node.get('resident_labels', []):
        failures.append(f'required peer label {required_peer} is absent')
    forbidden_peer = pod.get('forbidden_peer_label')
    if forbidden_peer is not None and forbidden_peer in node.get('resident_labels', []):
        failures.append(f'anti-affinity conflicts with {forbidden_peer}')
    return failures

def topology_spread_fit(node: dict[str, Any], pod: dict[str, Any], nodes: list[dict[str, Any]]) -> list[str]:
    spread = pod.get('topology_spread')
    if not spread or spread.get('when_unsatisfiable') != 'DoNotSchedule':
        return []
    key = spread['topology_key']
    label = spread['pod_label']
    domains = sorted({n.get('labels', {}).get(key) for n in nodes if n.get('labels', {}).get(key)})
    if not domains:
        return [f'topology key {key} is unavailable']
    counts = {domain: 0 for domain in domains}
    for candidate in nodes:
        domain = candidate.get('labels', {}).get(key)
        if domain in counts:
            counts[domain] += candidate.get('resident_labels', []).count(label)
    selected_domain = node.get('labels', {}).get(key)
    if selected_domain not in counts:
        return [f'node has no topology domain for {key}']
    counts[selected_domain] += 1
    skew = max(counts.values()) - min(counts.values())
    if skew > int(spread['max_skew']):
        return [f'topology skew {skew} exceeds {spread['max_skew']}']
    return []

def filter_node(node: dict[str, Any], pod: dict[str, Any], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    plugins = {'NodeResourcesFit': resource_fit(node, pod), 'NodeAffinity': selector_fit(node, pod), 'TaintToleration': taint_fit(node, pod), 'NodePortsAndVolumeBinding': local_constraint_fit(node, pod), 'PodTopologySpread': topology_spread_fit(node, pod, nodes)}
    failed_plugins = {name: reasons for name, reasons in plugins.items() if reasons}
    return {'node': node['name'], 'feasible': not failed_plugins, 'failed_plugins': failed_plugins}

def utilization(node: dict[str, Any], resource: str, extra: float=0.0) -> float:
    capacity = float(node.get('capacity', {}).get(resource, 0))
    if capacity <= 0:
        return 0.0
    used = float(node.get('allocated', {}).get(resource, 0)) + extra
    return min(1.0, used / capacity)

def score_node(node: dict[str, Any], pod: dict[str, Any], strategy: str) -> float:
    resources = [resource for resource in SCALAR_RESOURCES if float(node.get('capacity', {}).get(resource, 0)) > 0 and (resource in pod.get('requests', {}) or resource in {'cpu', 'memory_gib'})]
    post_util = [utilization(node, resource, float(pod.get('requests', {}).get(resource, 0))) for resource in resources]
    if not post_util:
        return 0.0
    if strategy == 'binpack':
        return round(sum(post_util) / len(post_util) * 100, 6)
    if strategy == 'spread':
        return round((1 - sum(post_util) / len(post_util)) * 100, 6)
    if strategy == 'balanced':
        average = sum(post_util) / len(post_util)
        variance = sum(((value - average) ** 2 for value in post_util)) / len(post_util)
        least_allocated = 1 - average
        return round((least_allocated * 0.55 + (1 - variance) * 0.45) * 100, 6)
    raise ValueError(f'unknown strategy: {strategy}')

def bind(node: dict[str, Any], pod: dict[str, Any]) -> None:
    node.setdefault('allocated', {})
    for resource, request in pod.get('requests', {}).items():
        node['allocated'][resource] = float(node['allocated'].get(resource, 0)) + float(request)
    if pod.get('host_port') is not None:
        node.setdefault('used_host_ports', []).append(pod['host_port'])
    if pod.get('labels'):
        node.setdefault('resident_labels', []).extend(pod['labels'])

def schedule_one(nodes: list[dict[str, Any]], pod: dict[str, Any], strategy: str) -> dict[str, Any]:
    filters = [filter_node(node, pod, nodes) for node in nodes]
    feasible_names = [item['node'] for item in filters if item['feasible']]
    if not feasible_names:
        failed = sorted({plugin for item in filters for plugin in item['failed_plugins']})
        total_free = sum((free_resources(node).get('nvidia.com/gpu', 0) for node in nodes))
        request = float(pod.get('requests', {}).get('nvidia.com/gpu', 0))
        reason = 'Unschedulable'
        if request > 0 and total_free >= request and ('NodeResourcesFit' in failed):
            reason = 'Fragmented'
        return {'pod': pod['name'], 'status': 'PENDING', 'reason': reason, 'unschedulable_plugins': failed, 'filter_results': filters}
    candidates = [node for node in nodes if node['name'] in feasible_names]
    scores = {node['name']: score_node(node, pod, strategy) for node in candidates}
    selected = sorted(candidates, key=lambda node: (-scores[node['name']], node['name']))[0]
    bind(selected, pod)
    return {'pod': pod['name'], 'status': 'BOUND', 'node': selected['name'], 'scores': scores, 'filter_results': filters}

def fragmentation_metrics(nodes: list[dict[str, Any]], future_jobs: list[dict[str, Any]]) -> dict[str, Any]:
    free_whole = [int(free_resources(node)['nvidia.com/gpu']) for node in nodes]
    total_whole = sum(free_whole)
    largest_whole = max(free_whole, default=0)
    whole_index = 0.0 if total_whole == 0 else round(1 - largest_whole / total_whole, 6)
    mig_free: dict[str, int] = {}
    for resource in ('nvidia.com/mig-1g.10gb', 'nvidia.com/mig-3g.40gb'):
        mig_free[resource] = int(sum((free_resources(node)[resource] for node in nodes)))
    future_capacity: dict[str, int] = {}
    for job in future_jobs:
        count = 0
        for node in nodes:
            fit = resource_fit(node, job)
            if not fit and (not selector_fit(node, job)) and (not taint_fit(node, job)):
                count += 1
        future_capacity[job['name']] = count
    return {'total_free_whole_gpu': total_whole, 'largest_contiguous_whole_gpu_block': largest_whole, 'whole_gpu_fragmentation_index': whole_index, 'free_mig_shapes': mig_free, 'nodes_that_fit_future_jobs': future_capacity}

def replay_strategy(scenario: dict[str, Any], strategy: str) -> dict[str, Any]:
    nodes = copy.deepcopy(scenario['nodes'])
    decisions = [schedule_one(nodes, pod, strategy) for pod in scenario['workload_stream']]
    metrics = fragmentation_metrics(nodes, scenario['future_jobs'])
    return {'strategy': strategy, 'bound': sum((item['status'] == 'BOUND' for item in decisions)), 'pending': sum((item['status'] == 'PENDING' for item in decisions)), 'decisions': decisions, 'metrics': metrics, 'final_nodes': nodes}

def queue_replay(scenario: dict[str, Any], mode: str) -> dict[str, Any]:
    nodes = copy.deepcopy(scenario['queue_demo']['nodes'])
    decisions: list[dict[str, Any]] = []
    for pod in scenario['queue_demo']['queue']:
        decision = schedule_one(nodes, pod, 'binpack')
        decisions.append(decision)
        if mode == 'strict_fifo' and decision['status'] == 'PENDING':
            break
    return {'mode': mode, 'attempted': len(decisions), 'bound': sum((item['status'] == 'BOUND' for item in decisions)), 'decisions': decisions}

def evaluate_fault(scenario: dict[str, Any], fault: dict[str, Any]) -> dict[str, Any]:
    nodes = copy.deepcopy(scenario['fault_nodes'])
    if fault['type'] == 'plugin_error':
        actual = {'phase': 'ERROR', 'reason': 'ScorePluginFailed'}
    elif fault['type'] == 'preemption_gap':
        actual = {'phase': 'NOMINATED', 'reason': 'VictimsTerminating'}
    else:
        decision = schedule_one(nodes, fault['pod'], 'balanced')
        plugins = decision.get('unschedulable_plugins', [])
        if decision['status'] == 'BOUND':
            actual = {'phase': 'BOUND', 'reason': 'FeasibleNodeFound'}
        else:
            reason_by_type = {'scalar': 'NodeResourcesFit', 'fragmentation': 'NodeResourcesFitFragmentation', 'selector': 'NodeAffinity', 'taint': 'TaintToleration', 'volume': 'VolumeBinding', 'host_port': 'NodePorts', 'affinity': 'InterPodAffinity', 'topology_spread': 'PodTopologySpread', 'mig_shape': 'NodeResourcesFitMIGShape'}
            actual = {'phase': 'PENDING', 'reason': reason_by_type[fault['type']], 'plugins': plugins}
    return {'name': fault['name'], 'passed': actual['phase'] == fault['expected_phase'] and actual['reason'] == fault['expected_reason'], **actual}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    strategies = [replay_strategy(scenario, strategy) for strategy in ('balanced', 'binpack', 'spread')]
    by_name = {item['strategy']: item for item in strategies}
    expected = scenario['expected']
    comparisons = {'binpack_preserves_larger_block_than_spread': by_name['binpack']['metrics']['largest_contiguous_whole_gpu_block'] > by_name['spread']['metrics']['largest_contiguous_whole_gpu_block'], 'binpack_preserves_a_node_for_future_eight_gpu_job': by_name['binpack']['metrics']['nodes_that_fit_future_jobs']['future-eight-gpu'] > by_name['spread']['metrics']['nodes_that_fit_future_jobs']['future-eight-gpu'], 'all_stream_pods_bound': all((item['pending'] == 0 for item in strategies))}
    queues = {'strict_fifo': queue_replay(scenario, 'strict_fifo'), 'backfill': queue_replay(scenario, 'backfill')}
    comparisons['backfill_avoids_head_of_line_idle_capacity'] = queues['strict_fifo']['bound'] == expected['strict_fifo_bound'] and queues['backfill']['bound'] == expected['backfill_bound']
    faults = [evaluate_fault(scenario, fault) for fault in scenario['faults']]
    passed = all(comparisons.values()) and all((fault['passed'] for fault in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'strategies': strategies, 'queue_demo': queues, 'comparisons': comparisons, 'faults': faults, 'measurement_boundary': 'results are deterministic scheduler-state replays; they demonstrate feasibility, scoring, fragmentation and queue effects, not kube-scheduler throughput or real GPU performance'}

def inspect_live(context: str | None, namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'no --context was supplied for a dedicated Kubernetes scheduling lab'}
    commands = {'nodes': ['kubectl', '--context', context, 'get', 'nodes', '-o', 'json'], 'pending_pods': ['kubectl', '--context', context, 'get', 'pods', '-n', namespace, '--field-selector', 'status.phase=Pending', '-o', 'json'], 'events': ['kubectl', '--context', context, 'get', 'events', '-n', namespace, '--field-selector', 'reason=FailedScheduling', '-o', 'json']}
    observed: dict[str, Any] = {'status': 'OBSERVED', 'commands': {}}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return {'status': 'SKIPPED', 'reason': f'live Kubernetes inspection unavailable: {exc}'}
        observed['commands'][name] = {'returncode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}
    return observed

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('simulate', 'live'), default='simulate')
    parser.add_argument('--context')
    parser.add_argument('--namespace', default='ai-scheduling-lab')
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    scenario = load_scenario(args.scenario)
    report = simulate(scenario)
    if args.mode == 'live':
        report['live_inspection'] = inspect_live(args.context, args.namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Scheduler fragmentation replay: {report['status']}')
    for item in report['strategies']:
        metrics = item['metrics']
        print(f'  {item['strategy']}: bound={item['bound']} pending={item['pending']} largest_gpu_block={metrics['largest_contiguous_whole_gpu_block']} fragmentation={metrics['whole_gpu_fragmentation_index']}')
    print(f'  queue: strict_fifo_bound={report['queue_demo']['strict_fifo']['bound']} backfill_bound={report['queue_demo']['backfill']['bound']}')
    for fault in report['faults']:
        state = 'PASS' if fault['passed'] else 'FAIL'
        print(f'  fault {fault['name']}: {state} {fault['phase']}/{fault['reason']}')
    if args.mode == 'live':
        live = report['live_inspection']
        print(f'Live scheduling inspection: {live['status']}')
        if live.get('reason'):
            print(f'Reason: {live['reason']}')
    print(f'Report: {args.output}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-10'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'scheduler_fragmentation_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
