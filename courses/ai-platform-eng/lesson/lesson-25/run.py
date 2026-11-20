#!/usr/bin/env python3
"""Standalone unified entry for lesson/lesson-25.

Default execution uses bundled fixture evidence. --check-only performs no workload;
--real is the only route allowed to label successful observations as measured.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

"""Deterministic CI/CD, provenance, signature, and admission-policy replay."""
import argparse
import hashlib
import hmac
import json
import re
import shutil
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Any
SHA256 = re.compile('^sha256:[0-9a-f]{64}$')
COMMIT = re.compile('^[0-9a-f]{40,64}$')
STATEMENT_TYPE = 'https://in-toto.io/Statement/v1'
PROVENANCE_TYPE = 'https://slsa.dev/provenance/v1'

def load_scenario(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))

def canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')

def digest_bytes(value: bytes) -> str:
    return 'sha256:' + hashlib.sha256(value).hexdigest()

def digest_text(value: str) -> str:
    return digest_bytes(value.encode('utf-8'))

def is_digest(value: str) -> bool:
    return bool(SHA256.fullmatch(value))

def pinned_reference(value: str) -> bool:
    return '@sha256:' in value and bool(re.search('@sha256:[0-9a-f]{64}$', value))

def build_outputs(scenario: dict[str, Any]) -> dict[str, Any]:
    build = scenario['build']
    return {'image': {'name': build['image_repository'], 'digest': digest_text(build['image_payload']), 'ref': f'{build['image_repository']}@{digest_text(build['image_payload'])}'}, 'model': {'name': build['model_repository'], 'digest': digest_text(build['model_payload']), 'ref': f'{build['model_repository']}@{digest_text(build['model_payload'])}'}}

def validate_build_definition(scenario: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    source = scenario['source']
    build = scenario['build']
    policy = scenario['policy']
    if not COMMIT.fullmatch(source.get('commit', '')):
        errors.append('ImmutableSourceRevisionRequired')
    if source.get('verified_pr') is not True:
        errors.append('SourceReviewEvidenceMissing')
    if any((not pinned_reference(ref) for ref in build.get('task_refs', []))):
        errors.append('PinnedTaskReferenceRequired')
    if policy['require_hermetic'] and build.get('network_access_during_build'):
        errors.append('HermeticBuildRequired')
    if build.get('service_account') not in policy['allowed_build_service_accounts']:
        errors.append('BuildIdentityNotAllowed')
    if build.get('privileged'):
        errors.append('PrivilegedBuildForbidden')
    if not build.get('reproducible_inputs'):
        errors.append('ReproducibleInputsRequired')
    return sorted(errors)

def generate_sbom(scenario: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    return {'bomFormat': 'CycloneDX', 'specVersion': scenario['sbom']['spec_version'], 'serialNumber': scenario['sbom']['serial_number'], 'version': 1, 'metadata': {'component': {'type': 'container', 'name': outputs['image']['name'], 'version': outputs['image']['digest'], 'bom-ref': outputs['image']['ref']}}, 'components': deepcopy(scenario['sbom']['components'])}

def generate_provenance(scenario: dict[str, Any], outputs: dict[str, Any]) -> dict[str, Any]:
    source = scenario['source']
    build = scenario['build']
    subjects = [{'name': outputs['image']['name'], 'digest': {'sha256': outputs['image']['digest'].split(':', 1)[1]}}, {'name': outputs['model']['name'], 'digest': {'sha256': outputs['model']['digest'].split(':', 1)[1]}}]
    return {'_type': STATEMENT_TYPE, 'subject': subjects, 'predicateType': PROVENANCE_TYPE, 'predicate': {'buildDefinition': {'buildType': build['build_type'], 'externalParameters': {'source': source['repository'], 'revision': source['commit'], 'pipeline': build['pipeline_ref']}, 'internalParameters': {}, 'resolvedDependencies': [{'uri': source['repository'], 'digest': {'gitCommit': source['commit']}}, *[{'uri': ref.rsplit('@', 1)[0], 'digest': {'sha256': ref.rsplit('@sha256:', 1)[1]}} for ref in build['task_refs']]]}, 'runDetails': {'builder': {'id': build['builder_id']}, 'metadata': {'invocationId': build['pipeline_run_uid'], 'startedOn': build['started_on'], 'finishedOn': build['finished_on']}, 'byproducts': [{'name': 'sbom', 'digest': {'sha256': ''}}, {'name': 'evaluation', 'digest': {'sha256': digest_bytes(canonical_json(scenario['evaluation'])).split(':', 1)[1]}}]}}}

def teaching_mac(statement: dict[str, Any], key: str) -> str:
    """Return a deterministic teaching MAC; this is not a Sigstore signature."""
    return hmac.new(key.encode('utf-8'), canonical_json(statement), hashlib.sha256).hexdigest()

def create_bundle(scenario: dict[str, Any], statement: dict[str, Any]) -> dict[str, Any]:
    signer = scenario['signer']
    return {'mediaType': 'application/vnd.dev.sigstore.bundle.v0.3+json', 'statement': deepcopy(statement), 'teaching_mac': teaching_mac(statement, signer['simulation_key']), 'certificate_identity': signer['identity'], 'certificate_oidc_issuer': signer['oidc_issuer'], 'transparency': {'included': signer['transparency_included'], 'log_index': signer['transparency_log_index']}, 'boundary': 'teaching_mac validates deterministic binding only; real signatures require Cosign and trusted Sigstore roots'}

def subject_digests(statement: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for subject in statement.get('subject', []):
        value = subject.get('digest', {}).get('sha256')
        if value:
            result.add('sha256:' + value)
    return result

def validate_release_evidence(scenario: dict[str, Any], outputs: dict[str, Any], sbom: dict[str, Any], provenance: dict[str, Any], bundle: dict[str, Any]) -> list[str]:
    errors = validate_build_definition(scenario)
    policy = scenario['policy']
    evaluation = scenario['evaluation']
    scan = scenario['scan']
    if sbom.get('bomFormat') != 'CycloneDX' or sbom.get('specVersion') != policy['required_sbom_version']:
        errors.append('RequiredSBOMFormatMissing')
    if sbom.get('metadata', {}).get('component', {}).get('bom-ref') != outputs['image']['ref']:
        errors.append('SBOMSubjectDigestMismatch')
    if len(sbom.get('components', [])) < policy['minimum_sbom_components']:
        errors.append('SBOMComponentInventoryIncomplete')
    if scan.get('critical', 0) > policy['maximum_critical_vulnerabilities']:
        errors.append('CriticalVulnerabilityGateFailed')
    if scan.get('high', 0) > policy['maximum_high_vulnerabilities']:
        errors.append('HighVulnerabilityGateFailed')
    if set(scan.get('licenses', [])) & set(policy['denied_licenses']):
        errors.append('DeniedLicenseDetected')
    if evaluation.get('status') != 'PASS':
        errors.append('ModelEvaluationGateFailed')
    if evaluation.get('model_digest') != outputs['model']['digest']:
        errors.append('EvaluationSubjectDigestMismatch')
    if provenance.get('_type') != STATEMENT_TYPE or provenance.get('predicateType') != PROVENANCE_TYPE:
        errors.append('ProvenancePredicateTypeMismatch')
    expected_subjects = {outputs['image']['digest'], outputs['model']['digest']}
    if subject_digests(provenance) != expected_subjects:
        errors.append('ProvenanceSubjectDigestMismatch')
    predicate = provenance.get('predicate', {})
    definition = predicate.get('buildDefinition', {})
    details = predicate.get('runDetails', {})
    if definition.get('buildType') not in policy['allowed_build_types']:
        errors.append('BuildTypeNotAllowed')
    if details.get('builder', {}).get('id') not in policy['allowed_builder_ids']:
        errors.append('BuilderIdentityNotAllowed')
    resolved = definition.get('resolvedDependencies', [])
    if not any((item.get('digest', {}).get('gitCommit') == scenario['source']['commit'] for item in resolved)):
        errors.append('SourceMaterialMissingFromProvenance')
    if bundle.get('statement') != provenance or not hmac.compare_digest(bundle.get('teaching_mac', ''), teaching_mac(provenance, scenario['signer']['simulation_key'])):
        errors.append('SignatureVerificationFailed')
    if bundle.get('certificate_identity') not in policy['allowed_signer_identities']:
        errors.append('SignerIdentityNotAllowed')
    if bundle.get('certificate_oidc_issuer') not in policy['allowed_oidc_issuers']:
        errors.append('OIDCIssuerNotAllowed')
    if policy['require_transparency'] and (not bundle.get('transparency', {}).get('included')):
        errors.append('TransparencyInclusionRequired')
    if scenario['admission']['policy_digest'] != policy['policy_digest']:
        errors.append('AdmissionPolicyDigestMismatch')
    return sorted(set(errors))

def evaluate_admission(scenario: dict[str, Any], outputs: dict[str, Any], evidence_errors: list[str]) -> dict[str, Any]:
    admission = scenario['admission']
    policy = scenario['policy']
    errors = list(evidence_errors)
    if not admission.get('namespace_opt_in'):
        errors.append('NamespacePolicyNotEnabled')
    if not pinned_reference(admission.get('image_ref', '').replace('$IMAGE_DIGEST', outputs['image']['digest'])):
        errors.append('DeploymentImageDigestRequired')
    if not admission.get('matching_policy'):
        errors.append('NoMatchingPolicyFailClosed')
    if admission.get('requested_image_repository') not in policy['allowed_image_repositories']:
        errors.append('ImageRepositoryNotAllowed')
    errors = sorted(set(errors))
    return {'status': 'ADMITTED' if not errors else 'REJECTED', 'reason': 'AllSupplyChainPoliciesPassed' if not errors else errors[0], 'errors': errors}

def validate_gitops_update(scenario: dict[str, Any], outputs: dict[str, Any], admission: dict[str, Any]) -> dict[str, Any]:
    promotion = scenario['promotion']
    errors: list[str] = []
    if admission['status'] != 'ADMITTED':
        errors.append('AdmissionEvidenceNotSatisfied')
    if promotion.get('image_ref') != '$IMAGE_REF':
        errors.append('GitOpsImageDigestMismatch')
    if promotion.get('model_ref') != '$MODEL_REF':
        errors.append('GitOpsModelDigestMismatch')
    if not promotion.get('signed_commit'):
        errors.append('PromotionCommitSignatureRequired')
    if promotion.get('evaluation_id') != scenario['evaluation']['evidence_id']:
        errors.append('PromotionEvaluationEvidenceMismatch')
    if promotion.get('source_pipeline_run_uid') != scenario['build']['pipeline_run_uid']:
        errors.append('PromotionBuildEvidenceMismatch')
    resolved = {'image_ref': outputs['image']['ref'], 'model_ref': outputs['model']['ref']}
    return {'status': 'PASS' if not errors else 'REJECTED', 'reason': 'DigestBoundGitOpsUpdate' if not errors else sorted(errors)[0], 'errors': sorted(errors), 'resolved': resolved}

def release_proof(scenario: dict[str, Any], outputs: dict[str, Any], sbom: dict[str, Any], provenance: dict[str, Any], bundle: dict[str, Any], admission: dict[str, Any], promotion: dict[str, Any]) -> dict[str, Any]:
    return {'release_id': scenario['release_id'], 'source_commit': scenario['source']['commit'], 'pipeline_run_uid': scenario['build']['pipeline_run_uid'], 'image_digest': outputs['image']['digest'], 'model_digest': outputs['model']['digest'], 'sbom_digest': digest_bytes(canonical_json(sbom)), 'provenance_digest': digest_bytes(canonical_json(provenance)), 'bundle_digest': digest_bytes(canonical_json(bundle)), 'policy_digest': scenario['policy']['policy_digest'], 'evaluation_id': scenario['evaluation']['evidence_id'], 'admission': admission['status'], 'promotion': promotion['status']}

def evaluate_fault(item: dict[str, Any]) -> dict[str, Any]:
    contracts = {'mutable_source': ('REJECTED', 'ImmutableSourceRevisionRequired'), 'unreviewed_source': ('REJECTED', 'SourceReviewEvidenceMissing'), 'unpinned_task': ('REJECTED', 'PinnedTaskReferenceRequired'), 'non_hermetic_build': ('REJECTED', 'HermeticBuildRequired'), 'privileged_builder': ('REJECTED', 'PrivilegedBuildForbidden'), 'mutable_image': ('REJECTED', 'DeploymentImageDigestRequired'), 'sbom_subject_mismatch': ('REJECTED', 'SBOMSubjectDigestMismatch'), 'sbom_empty': ('REJECTED', 'SBOMComponentInventoryIncomplete'), 'critical_vulnerability': ('REJECTED', 'CriticalVulnerabilityGateFailed'), 'denied_license': ('REJECTED', 'DeniedLicenseDetected'), 'evaluation_failed': ('REJECTED', 'ModelEvaluationGateFailed'), 'evaluation_subject_mismatch': ('REJECTED', 'EvaluationSubjectDigestMismatch'), 'provenance_subject_mismatch': ('REJECTED', 'ProvenanceSubjectDigestMismatch'), 'untrusted_builder': ('REJECTED', 'BuilderIdentityNotAllowed'), 'invalid_signature': ('REJECTED', 'SignatureVerificationFailed'), 'untrusted_signer': ('REJECTED', 'SignerIdentityNotAllowed'), 'transparency_missing': ('REJECTED', 'TransparencyInclusionRequired'), 'policy_digest_mismatch': ('REJECTED', 'AdmissionPolicyDigestMismatch'), 'namespace_not_opted_in': ('REJECTED', 'NamespacePolicyNotEnabled'), 'no_matching_policy': ('REJECTED', 'NoMatchingPolicyFailClosed'), 'direct_gitops_write': ('REJECTED', 'PromotionCommitSignatureRequired'), 'live_cluster_missing': ('SKIPPED', 'NoKubernetesContextProvided')}
    phase, reason = contracts[item['type']]
    ok = phase == item['expected_phase'] and reason == item['expected_reason']
    return {'type': item['type'], 'phase': phase, 'reason': reason, 'status': 'PASS' if ok else 'FAIL'}

def inspect_live(context: str | None, tekton_namespace: str, chains_namespace: str, policy_namespace: str) -> dict[str, Any]:
    if not context:
        return {'status': 'SKIPPED', 'reason': 'NoKubernetesContextProvided'}
    if not shutil.which('kubectl'):
        return {'status': 'SKIPPED', 'reason': 'KubectlUnavailable'}
    commands = {'pipelines': ['kubectl', '--context', context, '-n', tekton_namespace, 'get', 'pipelines.tekton.dev', '-o', 'json'], 'pipelineruns': ['kubectl', '--context', context, '-n', tekton_namespace, 'get', 'pipelineruns.tekton.dev', '-o', 'json'], 'chains': ['kubectl', '--context', context, '-n', chains_namespace, 'get', 'deployments', '-o', 'json'], 'policies': ['kubectl', '--context', context, 'get', 'clusterimagepolicies.policy.sigstore.dev', '-o', 'json'], 'policy_controller': ['kubectl', '--context', context, '-n', policy_namespace, 'get', 'deployments', '-o', 'json']}
    observations: dict[str, Any] = {}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=20, check=False)
        except subprocess.TimeoutExpired:
            return {'status': 'FAIL', 'reason': f'LiveSupplyChainReadTimeout:{name}'}
        if result.returncode:
            return {'status': 'FAIL', 'reason': f'LiveSupplyChainReadFailed:{name}', 'stderr': result.stderr.strip()}
        observations[name] = json.loads(result.stdout)
    return {'status': 'PASS', 'observations': observations, 'boundary': 'read-only listing proves API reachability and authorization only; it does not prove a real build, registry push, Cosign verification, transparency inclusion, SBOM quality, model evaluation, or admission denial'}

def simulate(scenario: dict[str, Any]) -> dict[str, Any]:
    outputs = build_outputs(scenario)
    sbom = generate_sbom(scenario, outputs)
    provenance = generate_provenance(scenario, outputs)
    provenance['predicate']['runDetails']['byproducts'][0]['digest']['sha256'] = digest_bytes(canonical_json(sbom)).split(':', 1)[1]
    bundle = create_bundle(scenario, provenance)
    evidence_errors = validate_release_evidence(scenario, outputs, sbom, provenance, bundle)
    admission = evaluate_admission(scenario, outputs, evidence_errors)
    promotion = validate_gitops_update(scenario, outputs, admission)
    faults = [evaluate_fault(item) for item in scenario['faults']]
    proof = release_proof(scenario, outputs, sbom, provenance, bundle, admission, promotion)
    passed = not evidence_errors and admission['status'] == 'ADMITTED' and (promotion['status'] == 'PASS') and all((item['status'] == 'PASS' for item in faults))
    return {'status': 'PASS' if passed else 'FAIL', 'outputs': outputs, 'sbom': sbom, 'provenance': provenance, 'signature_bundle': bundle, 'evidence_errors': evidence_errors, 'admission': admission, 'promotion': promotion, 'release_proof': proof, 'faults': faults}

def implementation_main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--scenario', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--live-context')
    parser.add_argument('--tekton-namespace', default='ai-build')
    parser.add_argument('--chains-namespace', default='tekton-chains')
    parser.add_argument('--policy-namespace', default='cosign-system')
    args = parser.parse_args()
    report = simulate(load_scenario(args.scenario))
    report['live'] = inspect_live(args.live_context, args.tekton_namespace, args.chains_namespace, args.policy_namespace)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'Supply-chain delivery replay: {report['status']}')
    print(f'  image: {report['outputs']['image']['digest']}')
    print(f'  model: {report['outputs']['model']['digest']}')
    print(f'  evidence: {('PASS' if not report['evidence_errors'] else 'REJECTED')}')
    print(f'  admission: {report['admission']['status']}/{report['admission']['reason']}')
    print(f'  promotion: {report['promotion']['status']}/{report['promotion']['reason']}')
    print(f'  release proof: {report['release_proof']['release_id']}')
    for item in report['faults']:
        print(f'  fault {item['type']}: {item['status']} {item['phase']}/{item['reason']}')
    print(f'  live: {report['live']['status']}/{report['live'].get('reason', 'observed')}')
    return 0 if report['status'] == 'PASS' and report['live']['status'] != 'FAIL' else 1

ENTRY_ID = 'lesson/lesson-25'


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
    return _invoke_embedded(implementation_main, args or ['--scenario', 'supply_chain_scenario.json', '--output', 'results/fixture.json'], "fixture")


if __name__ == "__main__":
    raise SystemExit(main())
