#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-01.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Validate an AI platform reference architecture from a scenario JSON file."""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    with path.open('r', encoding='utf-8') as handle:
        return json.load(handle)

def index_unique(items: list[dict[str, Any]], item_type: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    index: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for item in items:
        item_id = item.get('id')
        if not item_id:
            errors.append(f'{item_type} contains an item without id')
            continue
        if item_id in index:
            errors.append(f'duplicate {item_type} id: {item_id}')
            continue
        index[item_id] = item
    return (index, errors)

def validate_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    roles, role_errors = index_unique(scenario.get('roles', []), 'role')
    capabilities, capability_errors = index_unique(scenario.get('capabilities', []), 'capability')
    components, component_errors = index_unique(scenario.get('components', []), 'component')
    workloads, workload_errors = index_unique(scenario.get('workloads', []), 'workload')
    errors.extend(role_errors + capability_errors + component_errors + workload_errors)
    implementations: dict[str, list[str]] = defaultdict(list)
    for component_id, component in components.items():
        if component.get('stateful') and (not component.get('state_store')):
            errors.append(f'stateful component {component_id} has no state_store')
        if not component.get('failure_domain'):
            errors.append(f'component {component_id} has no failure_domain')
        for capability_id in component.get('capabilities', []):
            if capability_id not in capabilities:
                errors.append(f'component {component_id} implements unknown capability {capability_id}')
            else:
                implementations[capability_id].append(component_id)
    for capability_id, capability in capabilities.items():
        owner = capability.get('owner')
        if owner not in roles:
            errors.append(f'capability {capability_id} has unknown owner {owner!r}')
        if not implementations.get(capability_id):
            errors.append(f'capability {capability_id} has no implementing component')
    total_requirements = 0
    covered_requirements = 0
    workload_coverage: dict[str, dict[str, Any]] = {}
    for workload_id, workload in workloads.items():
        missing: list[str] = []
        for capability_id in workload.get('requirements', []):
            total_requirements += 1
            if capability_id in capabilities and implementations.get(capability_id):
                covered_requirements += 1
            else:
                missing.append(capability_id)
        if missing:
            errors.append(f'workload {workload_id} has uncovered requirements: {', '.join(missing)}')
        workload_coverage[workload_id] = {'name': workload.get('name', workload_id), 'required': len(workload.get('requirements', [])), 'missing': missing}
    required_layers = set(scenario.get('required_layers', []))
    covered_layers = {capability.get('layer') for capability in capabilities.values()}
    missing_layers = sorted(required_layers - covered_layers)
    if missing_layers:
        errors.append(f'architecture has no capability in layers: {', '.join(missing_layers)}')
    expected_order = 1
    for step in sorted(scenario.get('request_path', []), key=lambda item: item.get('order', 0)):
        if step.get('order') != expected_order:
            errors.append(f'request path expected order {expected_order}, got {step.get('order')}')
        expected_order += 1
        capability_id = step.get('capability')
        component_id = step.get('component')
        if capability_id not in capabilities:
            errors.append(f'request step references unknown capability {capability_id}')
        if component_id not in components:
            errors.append(f'request step references unknown component {component_id}')
        elif capability_id not in components[component_id].get('capabilities', []):
            errors.append(f'request step component {component_id} does not implement {capability_id}')
    required_boundaries = {'training_data_plane', 'inference_data_plane', 'evaluation_input', 'platform_control_plane'}
    missing_boundaries = sorted(required_boundaries - set(scenario.get('boundaries', {})))
    if missing_boundaries:
        errors.append(f'missing course boundaries: {', '.join(missing_boundaries)}')
    owner_count = sum((1 for capability in capabilities.values() if capability.get('owner') in roles))
    failure_domains = sorted({component.get('failure_domain') for component in components.values() if component.get('failure_domain')})
    if len(failure_domains) < 3:
        warnings.append('architecture uses fewer than three failure domains')
    return {'status': 'PASS' if not errors else 'FAIL', 'organization': scenario.get('organization'), 'summary': {'roles': len(roles), 'workloads': len(workloads), 'capabilities': len(capabilities), 'components': len(components), 'request_steps': len(scenario.get('request_path', [])), 'requirements_total': total_requirements, 'requirements_covered': covered_requirements, 'owners_total': len(capabilities), 'owners_resolved': owner_count, 'layers_required': len(required_layers), 'layers_covered': len(required_layers & covered_layers), 'failure_domains': failure_domains}, 'workload_coverage': workload_coverage, 'errors': errors, 'warnings': warnings}

def failure_impact(scenario: dict[str, Any], failed_component: str) -> dict[str, Any]:
    components = {item['id']: item for item in scenario.get('components', [])}
    if failed_component not in components:
        raise ValueError(f'unknown component: {failed_component}')
    failed_capabilities = set(components[failed_component].get('capabilities', []))
    impacted_workloads = []
    for workload in scenario.get('workloads', []):
        overlap = sorted(failed_capabilities & set(workload.get('requirements', [])))
        if overlap:
            impacted_workloads.append({'id': workload['id'], 'name': workload['name'], 'blocked_by': overlap})
    return {'failed_component': failed_component, 'failure_domain': components[failed_component].get('failure_domain'), 'lost_capabilities': sorted(failed_capabilities), 'impacted_workloads': impacted_workloads}

def print_report(report: dict[str, Any], output_path: Path) -> None:
    summary = report['summary']
    print(f'Architecture validation: {report['status']}')
    print('Workloads: {workloads} | Capabilities: {capabilities} | Components: {components} | Request steps: {request_steps}'.format(**summary))
    print(f'Requirement coverage: {summary['requirements_covered']}/{summary['requirements_total']}')
    print(f'Owners resolved: {summary['owners_resolved']}/{summary['owners_total']}')
    print(f'Layers covered: {summary['layers_covered']}/{summary['layers_required']}')
    print(f'Failure domains: {len(summary['failure_domains'])}')
    if report['warnings']:
        print('Warnings:')
        for warning in report['warnings']:
            print(f'  - {warning}')
    if report['errors']:
        print('Errors:')
        for error in report['errors']:
            print(f'  - {error}')
    print(f'Report: {output_path}')

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True, help='Path to the scenario JSON')
    parser.add_argument('--output', type=Path, required=True, help='Path for the JSON report')
    parser.add_argument('--inject-failure', help='Optional component id for impact analysis')
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    scenario = load_scenario(args.scenario)
    report = validate_scenario(scenario)
    if args.inject_failure:
        report['failure_injection'] = failure_impact(scenario, args.inject_failure)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8') as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    print_report(report, args.output)
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-01'


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
        if not any(tools.values()) or True:
            return _precondition_failed("no declared live target capability is available", tools=tools, live_route_declared=False)
        _emit_contract("ready", "none", tools=tools)
        return 0
    if "--real" in args:
        args.remove("--real")
        if not args:
            return _precondition_failed("--real requires explicit live target arguments; no fixture fallback is allowed")
        tools = {name: shutil.which(name) is not None for name in ['kubectl', 'nvidia-smi', 'sinfo']}
        if not any(tools.values()) or True:
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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
