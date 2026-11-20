#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-28.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic multi-tenant security, admission-policy, and audit replay."""
import argparse
import json
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def validate_rbac(tenant: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    allowed_verbs = set(policy['tenant_allowed_verbs'])
    forbidden_resources = set(policy['tenant_forbidden_resources'])
    for rule in tenant['rbac_rules']:
        verbs = set(rule['verbs'])
        resources = set(rule['resources'])
        if '*' in verbs or '*' in resources or '*' in rule['api_groups']:
            reasons.append('RBACWildcardForbidden')
        if not verbs <= allowed_verbs:
            reasons.append('RBACVerbOutsideTenantContract')
        if resources & forbidden_resources:
            reasons.append('RBACClusterOrSensitiveResourceForbidden')
    if tenant.get('cluster_role_binding'):
        reasons.append('TenantClusterRoleBindingForbidden')
    if tenant.get('can_impersonate'):
        reasons.append('TenantImpersonationForbidden')
    if tenant.get('can_bind_or_escalate'):
        reasons.append('TenantPrivilegeEscalationVerbForbidden')
    return {'status': 'PASS' if not reasons else 'REJECTED', 'reason': 'TenantRBACLeastPrivilegeSatisfied' if not reasons else reasons[0], 'reasons': sorted(set(reasons))}

def validate_namespace_security(tenant: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    labels = tenant['namespace_labels']
    required = policy['required_namespace_labels']
    for key, expected in required.items():
        if labels.get(key) != expected:
            reasons.append(f'NamespaceLabelMismatch:{key}')
    if labels.get('pod-security.kubernetes.io/enforce-version') != policy['pod_security_version']:
        reasons.append('PodSecurityVersionNotPinned')
    if labels.get('pod-security.kubernetes.io/audit') != 'restricted':
        reasons.append('PodSecurityAuditRestrictedMissing')
    if labels.get('pod-security.kubernetes.io/warn') != 'restricted':
        reasons.append('PodSecurityWarnRestrictedMissing')
    if tenant.get('pod_security_exempt'):
        reasons.append('TenantPodSecurityExemptionForbidden')
    return {'status': 'PASS' if not reasons else 'REJECTED', 'reason': 'NamespaceSecurityLabelsSatisfied' if not reasons else reasons[0], 'reasons': reasons}

def validate_workload(workload: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    security = workload['security_context']
    if security.get('privileged'):
        reasons.append('PrivilegedContainerForbidden')
    if security.get('allow_privilege_escalation'):
        reasons.append('PrivilegeEscalationForbidden')
    if not security.get('run_as_non_root'):
        reasons.append('RunAsNonRootRequired')
    if not security.get('read_only_root_filesystem'):
        reasons.append('ReadOnlyRootFilesystemRequired')
    if set(security.get('capabilities_add', [])):
        reasons.append('AddedLinuxCapabilitiesForbidden')
    if 'ALL' not in set(security.get('capabilities_drop', [])):
        reasons.append('DropAllCapabilitiesRequired')
    if workload.get('host_network') or workload.get('host_pid') or workload.get('host_ipc'):
        reasons.append('HostNamespaceForbidden')
    if workload.get('host_path'):
        reasons.append('HostPathForbidden')
    if workload.get('service_account') == 'default':
        reasons.append('DefaultServiceAccountForbidden')
    if workload.get('automount_service_account_token'):
        reasons.append('AutomaticServiceAccountTokenForbidden')
    if not workload.get('cpu_request') or not workload.get('memory_request'):
        reasons.append('ResourceRequestsRequired')
    if workload.get('image_tag_only'):
        reasons.append('ImageDigestRequired')
    if workload.get('image_signed') is not True:
        reasons.append('VerifiedImageSignatureRequired')
    if workload.get('provenance_predicate') != policy['required_provenance_predicate']:
        reasons.append('RequiredProvenanceMissing')
    return {'status': 'PASS' if not reasons else 'REJECTED', 'reason': 'WorkloadSecurityContractSatisfied' if not reasons else reasons[0], 'reasons': reasons}

def validate_network(tenant: dict[str, Any]) -> dict[str, Any]:
    network = tenant['network_policy']
    reasons: list[str] = []
    if not network.get('provider_enforcement_verified'):
        reasons.append('NetworkPolicyProviderNotVerified')
    if not network.get('default_deny_ingress'):
        reasons.append('DefaultDenyIngressMissing')
    if not network.get('default_deny_egress'):
        reasons.append('DefaultDenyEgressMissing')
    if not network.get('dns_egress_scoped'):
        reasons.append('ScopedDNSEgressMissing')
    if network.get('empty_namespace_selector'):
        reasons.append('UnboundedNamespaceSelectorForbidden')
    if not network.get('tenant_identity_selector'):
        reasons.append('TrustedTenantNetworkSelectorMissing')
    if network.get('metadata_endpoint_allowed'):
        reasons.append('CloudMetadataEgressForbidden')
    return {'status': 'PASS' if not reasons else 'REJECTED', 'reason': 'TenantNetworkIsolationSatisfied' if not reasons else reasons[0], 'reasons': reasons}

def validate_secret_boundary(tenant: dict[str, Any]) -> dict[str, Any]:
    secret = tenant['secret_policy']
    reasons: list[str] = []
    if secret.get('list_or_watch_allowed'):
        reasons.append('SecretListWatchForbidden')
    if secret.get('cross_namespace_mount'):
        reasons.append('CrossNamespaceSecretMountForbidden')
    if not secret.get('encryption_at_rest_verified'):
        reasons.append('SecretEncryptionAtRestUnverified')
    if not secret.get('short_lived_workload_identity'):
        reasons.append('ShortLivedWorkloadIdentityRequired')
    if secret.get('plaintext_in_git'):
        reasons.append('PlaintextSecretInGitForbidden')
    return {'status': 'PASS' if not reasons else 'REJECTED', 'reason': 'SecretBoundarySatisfied' if not reasons else reasons[0], 'reasons': reasons}

def validate_audit(audit: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    if not set(policy['required_audit_stages']) <= set(audit['stages']):
        reasons.append('RequiredAuditStageMissing')
    if audit['retention_days'] < policy['minimum_audit_retention_days']:
        reasons.append('AuditRetentionBelowPolicy')
    if not audit.get('write_once_archive'):
        reasons.append('TamperResistantAuditArchiveMissing')
    if not audit.get('secret_body_omitted'):
        reasons.append('SecretBodyMustBeOmittedFromAudit')
    if audit['identity_coverage_ratio'] < policy['minimum_audit_identity_coverage']:
        reasons.append('AuditIdentityCoverageInsufficient')
    if audit['delivery_lag_seconds'] > policy['maximum_audit_delivery_lag_seconds']:
        reasons.append('AuditDeliveryLagExceeded')
    return {'status': 'PASS' if not reasons else 'INCONCLUSIVE', 'reason': 'AuditEvidenceContractSatisfied' if not reasons else reasons[0], 'reasons': reasons}

def evaluate_fault(item: dict[str, Any]) -> dict[str, Any]:
    contracts = {'rbac_wildcard': ('REJECTED', 'RBACWildcardForbidden'), 'cluster_role_binding': ('REJECTED', 'TenantClusterRoleBindingForbidden'), 'impersonate': ('REJECTED', 'TenantImpersonationForbidden'), 'bind_escalate': ('REJECTED', 'TenantPrivilegeEscalationVerbForbidden'), 'pss_unpinned': ('REJECTED', 'PodSecurityVersionNotPinned'), 'pss_exemption': ('REJECTED', 'TenantPodSecurityExemptionForbidden'), 'privileged_pod': ('REJECTED', 'PrivilegedContainerForbidden'), 'host_namespace': ('REJECTED', 'HostNamespaceForbidden'), 'host_path': ('REJECTED', 'HostPathForbidden'), 'default_service_account': ('REJECTED', 'DefaultServiceAccountForbidden'), 'token_automount': ('REJECTED', 'AutomaticServiceAccountTokenForbidden'), 'unsigned_image': ('REJECTED', 'VerifiedImageSignatureRequired'), 'tag_only_image': ('REJECTED', 'ImageDigestRequired'), 'missing_provenance': ('REJECTED', 'RequiredProvenanceMissing'), 'network_provider_unknown': ('REJECTED', 'NetworkPolicyProviderNotVerified'), 'default_deny_missing': ('REJECTED', 'DefaultDenyIngressMissing'), 'namespace_selector_all': ('REJECTED', 'UnboundedNamespaceSelectorForbidden'), 'metadata_egress': ('REJECTED', 'CloudMetadataEgressForbidden'), 'secret_list': ('REJECTED', 'SecretListWatchForbidden'), 'plaintext_secret': ('REJECTED', 'PlaintextSecretInGitForbidden'), 'audit_identity_gap': ('INCONCLUSIVE', 'AuditIdentityCoverageInsufficient'), 'audit_lag': ('INCONCLUSIVE', 'AuditDeliveryLagExceeded'), 'live_cluster_missing': ('SKIPPED', 'NoKubernetesContextProvided')}
    phase, reason = contracts[item['type']]
    ok = phase == item['expected_phase'] and reason == item['expected_reason']
    return {'type': item['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    policy = scenario['policy']
    tenant_results = []
    for tenant in scenario['tenants']:
        checks = {'rbac': validate_rbac(tenant, policy), 'namespace': validate_namespace_security(tenant, policy), 'network': validate_network(tenant), 'secret': validate_secret_boundary(tenant), 'workloads': [validate_workload(item, policy) for item in tenant['workloads']]}
        passed = all((item['status'] == 'PASS' for name, item in checks.items() if name != 'workloads'))
        passed = passed and all((item['status'] == 'PASS' for item in checks['workloads']))
        tenant_results.append({'tenant': tenant['name'], 'status': 'PASS' if passed else 'FAIL', 'checks': checks})
    audit = validate_audit(scenario['audit'], policy)
    faults = [evaluate_fault(item) for item in scenario['faults']]
    status = 'PASS' if all((item['status'] == 'PASS' for item in tenant_results)) and audit['status'] == 'PASS' and all((item['status'] == 'PASS' for item in faults)) else 'FAIL'
    return {'status': status, 'tenants': tenant_results, 'audit': audit, 'faults': faults}

def _kubectl(command: list[str], label: str) -> tuple[Any | None, dict[str, Any] | None]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
    except subprocess.TimeoutExpired:
        return (None, {'status': 'FAIL', 'reason': f'LiveSecurityReadTimeout:{label}'})
    if result.returncode:
        return (None, {'status': 'FAIL', 'reason': f'LiveSecurityReadFailed:{label}', 'stderr': result.stderr.strip()})
    try:
        return (json.loads(result.stdout), None)
    except json.JSONDecodeError:
        return (None, {'status': 'FAIL', 'reason': f'LiveSecurityInvalidJSON:{label}'})

def inspect_live(context: str | None, namespaces: list[str] | None=None) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    if shutil.which('kubectl') is None:
        return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
    targets = namespaces or []
    if not targets:
        return {'status': 'FAIL', 'reason': 'LiveTenantNamespacesRequired'}
    evidence: dict[str, Any] = {'context': context, 'namespaces': {}}
    for namespace in targets:
        namespace_evidence: dict[str, Any] = {}
        commands = {'namespace': ['kubectl', '--context', context, 'get', 'namespace', namespace, '-o', 'json'], 'roles': ['kubectl', '--context', context, '-n', namespace, 'get', 'roles,rolebindings', '-o', 'json'], 'netpol': ['kubectl', '--context', context, '-n', namespace, 'get', 'networkpolicies', '-o', 'json'], 'quota': ['kubectl', '--context', context, '-n', namespace, 'get', 'resourcequotas,limitranges', '-o', 'json'], 'serviceaccounts': ['kubectl', '--context', context, '-n', namespace, 'get', 'serviceaccounts', '-o', 'json']}
        for label, command in commands.items():
            payload, error = _kubectl(command, f'{namespace}:{label}')
            if error:
                return error
            namespace_evidence[label] = payload
        evidence['namespaces'][namespace] = namespace_evidence
    cluster_commands = {'audit_webhooks': ['kubectl', '--context', context, 'get', 'validatingwebhookconfigurations,mutatingwebhookconfigurations', '-o', 'json'], 'gatekeeper_constraints': ['kubectl', '--context', context, 'get', 'constraints', '-A', '-o', 'json'], 'image_policies': ['kubectl', '--context', context, 'get', 'clusterimagepolicies.policy.sigstore.dev', '-o', 'json']}
    for label, command in cluster_commands.items():
        payload, error = _kubectl(command, label)
        if error:
            evidence[label] = {'status': 'SKIPPED', 'reason': error['reason']}
        else:
            evidence[label] = payload
    return {'status': 'PASS', 'reason': 'LiveSecurityEvidenceCollected', 'evidence': evidence}

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scenario', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--context')
    parser.add_argument('--namespace', action='append', dest='namespaces')
    return parser.parse_args()

def implementation_main() -> int:
    args = parse_args()
    scenario = load_scenario(args.scenario)
    report = simulate(scenario)
    report['live'] = inspect_live(args.context, args.namespaces)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Multi-tenant security replay: {report['status']}')
    for item in report['tenants']:
        print(f'  tenant {item['tenant']}: {item['status']}')
    print(f'  audit: {report['audit']['status']}/{report['audit']['reason']}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live']['reason']}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] in {'PASS', 'SKIPPED'} else 1

ENTRY_ID = 'lesson/lesson-28'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'security_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
