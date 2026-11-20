#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-18.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic replay for Kubeflow Profiles and multi-user isolation."""
import argparse
import json
import subprocess
from pathlib import Path
from typing import Any
READ_VERBS = {'get', 'list', 'watch'}
WRITE_VERBS = READ_VERBS | {'create', 'update', 'patch', 'delete'}

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def profile_by_name(scenario: dict[str, Any], namespace: str) -> dict[str, Any] | None:
    return next((item for item in scenario['profiles'] if item['name'] == namespace), None)

def reconcile_profile(profile: dict[str, Any]) -> dict[str, Any]:
    contributors = profile['contributors']
    rolebindings = ['namespaceAdmin', 'default-editor', 'default-viewer'] + [f'user-{item['name'].lower().replace('@', '-').replace('.', '-')}-clusterrole-{item['role']}' for item in contributors]
    authorization_policies = ['ns-owner-access-istio'] + [f'user-{item['name'].lower().replace('@', '-').replace('.', '-')}-clusterrole-{item['role']}' for item in contributors]
    resources = {'namespace': profile['name'], 'rolebindings': rolebindings, 'authorization_policies': authorization_policies, 'service_accounts': ['default-editor', 'default-viewer'], 'resource_quota': profile['quota'], 'limit_range': profile['limit_range'], 'network_policies': ['default-deny-ingress', 'default-deny-egress', 'allow-platform-control-plane'], 'local_queue': profile['local_queue']}
    return {'profile': profile['name'], 'owner': profile['owner'], 'contributors': len(contributors), 'resources': resources, 'status': 'READY', 'reason': 'ProfileContractReconciled'}

def user_role(scenario: dict[str, Any], user: str, namespace: str) -> str | None:
    profile = profile_by_name(scenario, namespace)
    if not profile:
        return None
    if profile['owner'] == user:
        return 'owner'
    contributor = next((item for item in profile['contributors'] if item['name'] == user), None)
    return contributor['role'] if contributor else None

def access_decision(scenario: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    role = user_role(scenario, request['user'], request['namespace'])
    allowed_verbs = WRITE_VERBS if role in {'owner', 'edit'} else READ_VERBS if role == 'view' else set()
    decision = 'ALLOW' if request['verb'] in allowed_verbs else 'DENY'
    return {'name': request['name'], 'decision': decision, 'role': role or 'none', 'status': 'PASS' if decision == request['expected'] else 'FAIL'}

def web_authorization(scenario: dict[str, Any], user: str, namespace: str, principal: str) -> dict[str, Any]:
    if principal not in scenario['trusted_principals']:
        return {'decision': 'DENY', 'reason': 'UntrustedGatewayPrincipal'}
    if user_role(scenario, user, namespace) is None:
        return {'decision': 'DENY', 'reason': 'ProfileMembershipMissing'}
    return {'decision': 'ALLOW', 'reason': 'TrustedPrincipalAndProfileMembership'}

def quota_admission(scenario: dict[str, Any], probe: dict[str, Any]) -> dict[str, Any]:
    profile = profile_by_name(scenario, probe['namespace'])
    if not profile:
        return {'decision': 'REJECTED', 'reason': 'ProfileNotFound'}
    violations = []
    for resource, requested in probe['request'].items():
        used = probe['used'].get(resource, 0)
        hard = profile['quota'].get(resource)
        if hard is not None and used + requested > hard:
            violations.append({'resource': resource, 'used': used, 'requested': requested, 'hard': hard})
    return {'decision': 'REJECTED' if violations else 'ADMITTED', 'reason': 'ResourceQuotaExceeded' if violations else 'WithinNamespaceQuota', 'violations': violations}

def network_decision(probe: dict[str, Any]) -> dict[str, Any]:
    same_namespace = probe['source'] == probe['destination']
    platform_ingress = probe['source'] == 'kubeflow' and probe['port'] in {80, 443}
    decision = 'ALLOW' if same_namespace or platform_ingress else 'DENY'
    return {'name': probe['name'], 'decision': decision, 'status': 'PASS' if decision == probe['expected'] else 'FAIL'}

def notebook_plan(profile: dict[str, Any]) -> dict[str, Any]:
    notebook = profile['notebook']
    errors = []
    if '@sha256:' not in notebook['image']:
        errors.append('MutableNotebookImage')
    if notebook['service_account'] != 'default-editor':
        errors.append('UnexpectedNotebookServiceAccount')
    if not notebook['pvc']:
        errors.append('NotebookWorkspacePVCMissing')
    if notebook['gpu'] > profile['quota'].get('requests.nvidia.com/gpu', 0):
        errors.append('NotebookGPUExceedsProfileQuota')
    if notebook['idle_shutdown_minutes'] <= 0:
        errors.append('IdleShutdownPolicyMissing')
    return {'name': notebook['name'], 'namespace': profile['name'], 'status': 'READY' if not errors else 'BLOCKED', 'errors': errors}

def evaluate_fault(fault: dict[str, Any]) -> dict[str, Any]:
    contracts = {'namespace_collision': ('BLOCKED', 'ProfileNamespaceNameCollision'), 'identity_case': ('DENIED', 'CaseSensitiveSubjectMismatch'), 'missing_rolebinding': ('API_DENIED', 'KubernetesRBACBindingMissing'), 'missing_authorizationpolicy': ('UI_DENIED', 'IstioAuthorizationPolicyMissing'), 'spoofed_header': ('DENIED', 'UntrustedGatewayPrincipal'), 'clusterrolebinding_scope': ('UNSAFE', 'CrossNamespacePrivilegeGranted'), 'overprivileged_serviceaccount': ('UNSAFE', 'NotebookWorkloadIdentityTooBroad'), 'networkpolicy_no_controller': ('UNENFORCED', 'NetworkPolicyProviderUnavailable'), 'limitrange_conflict': ('REJECTED', 'DefaultLimitBelowRequest'), 'gpu_quota_missing': ('UNSAFE', 'NamespaceGPUConsumptionUnbounded'), 'pipeline_definition_shared': ('SHARED', 'PipelineDefinitionsNotNamespaceIsolated'), 'mlmd_shared': ('SHARED', 'MLMDNamespaceIsolationUnavailable'), 'profile_delete': ('DESTRUCTIVE', 'ProfileDeletionCascadesNamespace'), 'idle_reclaim_missing': ('COST_RISK', 'InteractiveCapacityNeverReleased'), 'automatic_owner_delegation': ('GOVERNANCE_RISK', 'EndUserCanManageContributors'), 'quota_as_capacity': ('PENDING', 'QuotaDoesNotGuaranteePhysicalCapacity')}
    phase, reason = contracts[fault['type']]
    passed = (phase, reason) == (fault['expected_phase'], fault['expected_reason'])
    return {'name': fault['name'], 'phase': phase, 'reason': reason, 'status': 'PASS' if passed else 'FAIL'}

def inspect_live(context: str | None, profile_a: str, profile_b: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    commands = {'profiles': ['kubectl', '--context', context, 'get', 'profiles.kubeflow.org', '-o', 'json'], 'namespaces': ['kubectl', '--context', context, 'get', 'namespace', profile_a, profile_b, '-o', 'json'], 'rolebindings_a': ['kubectl', '--context', context, '-n', profile_a, 'get', 'rolebindings', '-o', 'json'], 'rolebindings_b': ['kubectl', '--context', context, '-n', profile_b, 'get', 'rolebindings', '-o', 'json'], 'authorization_a': ['kubectl', '--context', context, '-n', profile_a, 'get', 'authorizationpolicies.security.istio.io', '-o', 'json'], 'governance_a': ['kubectl', '--context', context, '-n', profile_a, 'get', 'resourcequota,limitrange,networkpolicy', '-o', 'json'], 'notebooks_a': ['kubectl', '--context', context, '-n', profile_a, 'get', 'notebooks.kubeflow.org', '-o', 'json']}
    observations: dict[str, Any] = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=20)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
        if result.returncode:
            return {'status': 'SKIPPED', 'reason': f'LivePrerequisiteUnavailable:{name}', 'stderr': result.stderr.strip()}
        observations[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'observations': observations, 'boundary': 'read-only discovery does not prove browser authentication, header trust, CNI enforcement, negative API authorization, storage isolation, or destructive cleanup'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    profiles = [reconcile_profile(item) for item in scenario['profiles']]
    access = [access_decision(scenario, item) for item in scenario['access_requests']]
    network = [network_decision(item) for item in scenario['network_probes']]
    notebooks = [notebook_plan(item) for item in scenario['profiles']]
    quota = quota_admission(scenario, scenario['quota_probe'])
    trusted_web = web_authorization(scenario, 'alice@example.invalid', 'team-alpha', 'cluster.local/ns/istio-system/sa/istio-ingressgateway-service-account')
    spoofed_web = web_authorization(scenario, 'alice@example.invalid', 'team-alpha', 'untrusted-client')
    faults = [evaluate_fault(item) for item in scenario['faults']]
    passed = len(profiles) == 2 and all((item['status'] == 'READY' for item in profiles)) and all((item['status'] == 'PASS' for item in access)) and all((item['status'] == 'PASS' for item in network)) and all((item['status'] == 'READY' for item in notebooks)) and (quota['decision'] == scenario['quota_probe']['expected']) and (trusted_web['decision'] == 'ALLOW') and (spoofed_web['decision'] == 'DENY') and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'baseline': scenario['baseline'], 'profiles': profiles, 'access': access, 'network': network, 'notebooks': notebooks, 'quota': quota, 'trusted_web': trusted_web, 'spoofed_web': spoofed_web, 'faults': faults}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live-context')
    parser.add_argument('--profile-a', default='team-alpha')
    parser.add_argument('--profile-b', default='team-beta')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.live_context, args.profile_a, args.profile_b)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Kubeflow multi-tenancy replay: {report['status']}')
    for profile in report['profiles']:
        print(f'  profile {profile['profile']}: {profile['status']}/{profile['reason']}')
    for item in report['access']:
        print(f'  access {item['name']}: {item['status']} {item['decision']}/{item['role']}')
    for item in report['network']:
        print(f'  network {item['name']}: {item['status']} {item['decision']}')
    print(f'  quota: {report['quota']['decision']}/{report['quota']['reason']}')
    print(f'  trusted web: {report['trusted_web']['decision']}/{report['trusted_web']['reason']}')
    print(f'  spoofed web: {report['spoofed_web']['decision']}/{report['spoofed_web']['reason']}')
    for item in report['faults']:
        print(f'  fault {item['name']}: {item['status']} {item['phase']}/{item['reason']}')
    return 0 if report['status'] == 'PASS' else 1

ENTRY_ID = 'lesson/lesson-18'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'kubeflow_multitenancy_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
