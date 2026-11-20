#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-04.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Simulate AI workload lifecycle and optionally inspect a real kind cluster."""
import argparse
import copy
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key].update(value)
        else:
            result[key] = value
    return result

def tolerates(taint: dict[str, str], tolerations: list[dict[str, str]]) -> bool:
    for item in tolerations:
        if item.get('key') != taint.get('key') or item.get('effect') != taint.get('effect'):
            continue
        if 'value' not in taint or item.get('value') == taint.get('value'):
            return True
    return False

def simulate_workload(workload: dict[str, Any], scenario: dict[str, Any], inject: str | None=None) -> dict[str, Any]:
    events: list[dict[str, str]] = [{'phase': 'Admission', 'reason': 'Accepted', 'message': 'workload schema accepted'}]
    quota = scenario['namespaces'][workload['namespace']]['quota']
    total_cpu = workload['request']['cpu_m'] * workload['replicas']
    total_memory = workload['request']['memory_mib'] * workload['replicas']
    if total_cpu > quota['cpu_m'] or total_memory > quota['memory_mib'] or workload['replicas'] > quota['pods']:
        events.append({'phase': 'Rejected', 'reason': 'QuotaExceeded', 'message': 'aggregate requests exceed namespace quota'})
        return {'state': 'Rejected', 'reason': 'QuotaExceeded', 'events': events, 'node': None}
    pvc = workload.get('pvc')
    if pvc and scenario.get('pvcs', {}).get(f'{workload['namespace']}/{pvc}', {}).get('status') != 'Bound':
        events.append({'phase': 'Pending', 'reason': 'UnboundPVC', 'message': f'PVC {pvc} is not bound'})
        return {'state': 'Pending', 'reason': 'UnboundPVC', 'events': events, 'node': None}
    selectors = workload.get('nodeSelector', {})
    label_matches = [node for node in scenario['nodes'] if all((node['labels'].get(k) == v for k, v in selectors.items()))]
    if not label_matches:
        events.append({'phase': 'Pending', 'reason': 'NodeSelectorMismatch', 'message': 'no node matches all required labels'})
        return {'state': 'Pending', 'reason': 'NodeSelectorMismatch', 'events': events, 'node': None}
    candidates = [node for node in label_matches if all((tolerates(taint, workload.get('tolerations', [])) for taint in node.get('taints', [])))]
    if not candidates:
        events.append({'phase': 'Pending', 'reason': 'UntoleratedTaint', 'message': 'matching nodes repel the workload'})
        return {'state': 'Pending', 'reason': 'UntoleratedTaint', 'events': events, 'node': None}
    node = next((item for item in candidates if item['capacity']['cpu_m'] >= workload['request']['cpu_m'] and item['capacity']['memory_mib'] >= workload['request']['memory_mib']), None)
    if not node:
        events.append({'phase': 'Pending', 'reason': 'InsufficientResources', 'message': 'matching nodes lack requested CPU or memory'})
        return {'state': 'Pending', 'reason': 'InsufficientResources', 'events': events, 'node': None}
    events.append({'phase': 'Scheduled', 'reason': 'NodeBound', 'message': f'bound to {node['name']}'})
    if inject == 'image_pull':
        events.append({'phase': 'Waiting', 'reason': 'ImagePullBackOff', 'message': 'container image cannot be pulled'})
        return {'state': 'Waiting', 'reason': 'ImagePullBackOff', 'events': events, 'node': node['name']}
    events.append({'phase': 'ImageReady', 'reason': 'ImagePulled', 'message': 'container image is available'})
    if workload.get('initContainers'):
        events.append({'phase': 'Initialized', 'reason': 'InitContainersCompleted', 'message': 'all regular init containers completed'})
    events.append({'phase': 'Running', 'reason': 'ContainersStarted', 'message': 'application containers started'})
    if inject == 'oom':
        events.append({'phase': 'Failed', 'reason': 'OOMKilled', 'message': 'container exceeded its memory limit'})
        return {'state': 'Failed', 'reason': 'OOMKilled', 'events': events, 'node': node['name']}
    if inject == 'readiness':
        events.append({'phase': 'RunningNotReady', 'reason': 'ReadinessProbeFailed', 'message': 'container runs but is removed from service endpoints'})
        return {'state': 'RunningNotReady', 'reason': 'ReadinessProbeFailed', 'events': events, 'node': node['name']}
    if workload['kind'] == 'Job':
        events.append({'phase': 'Succeeded', 'reason': 'Completed', 'message': 'Job reached its completion target'})
        return {'state': 'Succeeded', 'reason': 'Completed', 'events': events, 'node': node['name']}
    events.append({'phase': 'Ready', 'reason': 'ReadinessProbePassed', 'message': 'desired replicas are available'})
    return {'state': 'Ready', 'reason': 'ReadinessProbePassed', 'events': events, 'node': node['name']}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    workloads = {item['id']: item for item in scenario['workloads']}
    healthy = {name: simulate_workload(item, scenario) for name, item in workloads.items()}
    faults: dict[str, Any] = {}
    for case in scenario['fault_cases']:
        item = merge(workloads[case['base']], case.get('override', {}))
        result = simulate_workload(item, scenario, case.get('inject'))
        result['expected_state'] = case['expected']
        result['expected_reason'] = case['reason']
        result['passed'] = result['state'] == case['expected'] and result['reason'] == case['reason']
        faults[case['id']] = result
    checks = {'healthy_workloads_reach_expected_terminal_state': all((result['state'] in {'Ready', 'Succeeded'} for result in healthy.values())), 'workload_types_are_distinct': {item['kind'] for item in workloads.values()} == {'Deployment', 'Job'}, 'training_uses_bound_pvc': healthy['training']['state'] == 'Succeeded' and workloads['training'].get('pvc') is not None, 'training_tolerates_dedicated_taint': healthy['training']['node'] == 'worker-training', 'all_fault_cases_are_explained': all((result['passed'] for result in faults.values()))}
    return {'status': 'PASS' if all(checks.values()) else 'FAIL', 'checks': checks, 'healthy': healthy, 'faults': faults}

def inspect_live(context: str | None) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'no --context was supplied for a real Kubernetes cluster'}
    if not shutil.which('kubectl'):
        return {'status': 'SKIPPED', 'reason': 'kubectl is not installed'}
    command = ['kubectl', '--context', context, 'get', 'pods', '-A', '-o', 'json']
    result = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
    if result.returncode:
        return {'status': 'FAIL', 'reason': result.stderr.strip() or 'kubectl failed'}
    data = json.loads(result.stdout)
    namespaces = {item['metadata']['namespace'] for item in data.get('items', [])}
    required = {'lab-notebook', 'lab-training', 'lab-serving'}
    missing = sorted(required - namespaces)
    return {'status': 'PASS' if not missing else 'FAIL', 'pod_count': len(data.get('items', [])), 'missing_namespaces': missing}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('simulated', 'live'), default='simulated')
    parser.add_argument('--context')
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    report = simulate(load(args.scenario))
    if args.mode == 'live':
        report['live_cluster'] = inspect_live(args.context)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'AI workload lifecycle simulation: {report['status']}')
    for name, result in report['healthy'].items():
        print(f'  {name}: {result['state']} on {result['node']}')
    for name, result in report['faults'].items():
        print(f'  fault {name}: {('PASS' if result['passed'] else 'FAIL')} {result['reason']}')
    if args.mode == 'live':
        print(f'Live cluster inspection: {report['live_cluster']['status']}')
        if report['live_cluster']['status'] == 'SKIPPED':
            print(f'Reason: {report['live_cluster']['reason']}')
    print(f'Report: {args.output}')
    live_failed = report.get('live_cluster', {}).get('status') == 'FAIL'
    return 0 if report['status'] == 'PASS' and (not live_failed) else 1

ENTRY_ID = 'lesson/lesson-04'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'workload_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
