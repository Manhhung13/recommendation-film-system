"""Read-only research prerequisite verification. No signing or approval endpoint.

The operator must provision an external controller's Ed25519 public key outside
the checkout and protect the runner environment. Local state is never evidence.
"""
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import yaml

PROTECTED_TASKS = frozenset({'DATA-QUALITY-001', 'RESEARCH-001', 'EDA-001', 'SPLIT-001'})
REQUIRED_SOURCES = {
    **{f'movielens/ml-25m/{n}': 'movielens' for n in (
        'ratings.csv', 'movies.csv', 'tags.csv', 'links.csv', 'genome-scores.csv', 'genome-tags.csv')},
    **{f'imdb/{n}.tsv.gz': 'imdb' for n in (
        'title.basics', 'title.crew', 'title.principals', 'name.basics')},
    **{f'tmdb/{n}.jsonl': 'tmdb' for n in ('movie_details', 'keywords', 'credits')},
}
SHA256 = re.compile(r'^[0-9a-f]{64}$')
SHA1 = re.compile(r'^[0-9a-f]{40}$')


class ReadinessError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReadinessError(message)


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False).encode('utf-8')


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON key')
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=_unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ReadinessError('Non-finite JSON')))


def utc(value):
    require(isinstance(value, str), 'Missing timestamp')
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    require(stamp.tzinfo is not None and stamp.utcoffset() == timedelta(0), 'Timestamp must be UTC')
    return stamp


def local_path(root, value):
    require(isinstance(value, str) and value and '\\' not in value and ':' not in value,
            'Invalid repository-relative evidence path')
    rel = PurePosixPath(value)
    require(not rel.is_absolute() and '..' not in rel.parts, 'Evidence path traversal')
    path = (root / value).resolve(strict=True)
    require(path.is_relative_to(root.resolve()) and path.is_file(), 'Evidence outside repository or missing')
    return path


def digest(path):
    hasher = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def artifact(root, reference):
    require(isinstance(reference, dict), 'Missing evidence artifact')
    expected = reference.get('sha256')
    require(isinstance(expected, str) and SHA256.fullmatch(expected), 'Invalid artifact digest')
    path = local_path(root, reference.get('path'))
    require(digest(path) == expected, 'Artifact changed: ' + reference['path'])
    return path


def prerequisite_ids(tasks, task_id):
    found = set()
    active = set()

    def visit(tid):
        require(tid in tasks and tid not in active, 'Invalid dependency graph')
        if tid in found:
            return
        active.add(tid)
        for dep in tasks[tid].get('dependencies', []):
            visit(dep)
            found.add(dep)
        active.remove(tid)

    visit(task_id)
    return sorted(found)


def verify_manifest(root, reference):
    manifest = read_json(artifact(root, reference))
    require(manifest.get('schema_version') == 1, 'Unsupported dataset manifest')
    require(manifest.get('raw_root') == 'dataset_linkage_work/raw', 'Unexpected raw root')
    entries = manifest.get('files')
    require(isinstance(entries, list) and entries, 'Empty dataset manifest')
    seen = set()
    for entry in entries:
        name = entry['path']
        require(name not in seen, 'Duplicate manifest path')
        seen.add(name)
        path = artifact(root, entry)
        require(path.is_relative_to((root / manifest['raw_root']).resolve()), 'Manifest source outside raw root')
        require(type(entry.get('size_bytes')) is int and entry['size_bytes'] > 0
                and path.stat().st_size == entry['size_bytes'], 'Source size mismatch')
        require(isinstance(entry.get('source_version'), str) and entry['source_version'].strip(),
                'Missing source version')
        utc(entry.get('retrieved_at_utc'))
    by_path = {entry['path']: entry for entry in entries}
    for suffix, family in REQUIRED_SOURCES.items():
        entry = by_path.get(manifest['raw_root'] + '/' + suffix, {})
        require(entry.get('source') == family, 'Missing required source: ' + suffix)


def git_value(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True, stderr=subprocess.PIPE).strip()


def governance_inputs(tasks):
    prefix = 'movie-rec-agent-starter/'
    required = {prefix + 'tasks/index.yaml', prefix + '.agents/policies/quality_gates.yaml',
                prefix + 'scripts/agentctl.py', prefix + 'scripts/readiness.py',
                prefix + 'scripts/github_ci.py', '.github/workflows/agent-contracts.yml'}
    required.update(prefix + 'tasks/' + tid + '.yaml' for tid in tasks)
    return required


def required_inputs(tasks, task_id, root):
    """Bind the current graph/policy and committed prerequisite implementation.

    New candidate implementation files are not prerequisites. Changes to files
    already covered by ancestor allowlists require renewed upstream evidence.
    """
    required = governance_inputs(tasks)
    tracked = set(git_value(root, 'ls-tree', '-r', '--name-only', 'HEAD').splitlines())
    for tid in prerequisite_ids(tasks, task_id):
        for rule in tasks[tid]['allowed_paths']:
            required.update(p for p in tracked if (p.startswith(rule) if rule.endswith('/') else p == rule))
        for ac in tasks[tid]['acceptance_criteria']:
            require(ac['planned_test'] in tracked, tid + ': acceptance test is not committed at HEAD')
            required.add(ac['planned_test'])
    require(required <= tracked, 'Readiness input is not committed at HEAD')
    return required


def verify_inputs(root, tasks, task_id, payload):
    inputs = payload.get('inputs')
    require(isinstance(inputs, dict) and bool(inputs), 'Missing signed prerequisite input hashes')
    governance = governance_inputs(tasks)
    require(governance <= set(inputs), 'Missing signed governance inputs')
    for name in sorted(governance):
        artifact(root, {'path': name, 'sha256': inputs[name]})
    # The direct Python entrypoint must not supply a weakened in-memory graph.
    for tid, task in tasks.items():
        file = local_path(root, 'movie-rec-agent-starter/tasks/' + tid + '.yaml')
        require(task == yaml.safe_load(file.read_text(encoding='utf-8')), 'Task object differs from bound contract')
    # Only after the graph/policy are authenticated may they select prerequisites.
    expected = required_inputs(tasks, task_id, root)
    require(set(inputs) == expected, 'Signed prerequisite input inventory changed')
    for name in sorted(expected - governance):
        artifact(root, {'path': name, 'sha256': inputs[name]})
    # Exact-SHA checks cannot certify dirty prerequisite code even if a controller
    # accidentally signs its current byte hashes. Git handles platform line endings.
    git_value(root, 'diff', '--no-ext-diff', '--quiet', 'HEAD', '--', *sorted(expected))


def signed_payload(root, environ):
    key_name = environ.get('MOVIEREC_READINESS_PUBLIC_KEY_FILE')
    require(bool(key_name), 'Trusted readiness public key is not configured')
    key_path = Path(key_name)
    require(key_path.is_absolute(), 'Trust anchor must use an absolute path')
    key_path = key_path.resolve(strict=True)
    require(not key_path.is_relative_to(root.resolve()), 'Trust anchor must be outside the checkout')
    # Import lazily: the existing CLI remains usable without the optional verifier
    # dependency, while guarded execution still fails closed.
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.exceptions import InvalidSignature
    key = load_pem_public_key(key_path.read_bytes())
    require(isinstance(key, Ed25519PublicKey), 'Trust anchor must be Ed25519')
    bundle_name = environ.get('MOVIEREC_READINESS_BUNDLE_FILE', '.runtime/trusted-readiness.json')
    bundle = read_json(local_path(root, bundle_name))
    payload = bundle['payload']
    require(isinstance(payload, dict), 'Invalid readiness payload')
    try:
        key.verify(base64.b64decode(bundle['signature'], validate=True), canonical(payload))
    except InvalidSignature as exc:
        raise ReadinessError('Invalid readiness signature') from exc
    return payload


def verify_readiness(tasks, task_id, root, *, environ=None, clock=None):
    """Return authenticated decision IDs, or reject without writing any state.

    A protected controller must attest real test artifacts, independent review,
    business approvals and GitHub check provenance. A signature from a caller's
    own key is not independent verification; key provisioning is external.
    """
    try:
        payload = signed_payload(root, os.environ if environ is None else environ)
        sha = git_value(root, 'rev-parse', 'HEAD')
        repo = git_value(root, 'remote', 'get-url', 'origin')
        require(SHA1.fullmatch(sha) and payload.get('schema_version') == 1, 'Invalid readiness version or SHA')
        require(payload.get('head_sha') == sha and payload.get('repository') == repo,
                'Readiness evidence is for a different repository or HEAD')
        current = clock or datetime.now(timezone.utc)
        issued, expires = utc(payload.get('issued_at')), utc(payload.get('expires_at'))
        require(issued <= current < expires and timedelta(0) < expires - issued <= timedelta(hours=24),
                'Readiness evidence is stale, future-dated or exceeds 24 hours')
        verify_inputs(root, tasks, task_id, payload)
        manifest = payload['dataset_manifest']
        verify_manifest(root, manifest)
        deps = prerequisite_ids(tasks, task_id)
        gates = yaml.safe_load(
            (root / 'movie-rec-agent-starter/.agents/policies/quality_gates.yaml').read_text(encoding='utf-8'))
        for tid in deps:
            proof = payload.get('tasks', {}).get(tid, {})
            require(proof.get('status') == 'VERIFIED' and proof.get('head_sha') == sha,
                    tid + ': no VERIFIED evidence for HEAD')
            require(proof.get('dataset_manifest_sha256') == manifest['sha256'], tid + ': manifest mismatch')
            for ac in tasks[tid]['acceptance_criteria']:
                test = proof.get('acceptance', {}).get(ac['id'], {})
                require(type(test.get('exit_code')) is int and test['exit_code'] == 0
                        and test.get('test_case') == ac['test_case']
                        and isinstance(test.get('command'), list) and bool(test['command'])
                        and all(isinstance(part, str) and part for part in test['command']),
                        tid + ': missing or failed acceptance test ' + ac['id'])
                artifact(root, test.get('report'))
            review = proof.get('review', {})
            require(review.get('decision') == 'APPROVED' and review.get('head_sha') == sha
                    and isinstance(review.get('author_identity'), str) and bool(review['author_identity'].strip())
                    and isinstance(review.get('reviewer_identity'), str) and bool(review['reviewer_identity'].strip())
                    and review['author_identity'].strip().casefold() != review['reviewer_identity'].strip().casefold(),
                    tid + ': independent review absent or stale')
            artifact(root, review.get('report'))
            ci = proof.get('ci', {})
            infra = tasks[tid]['type'] == 'infra'
            require(ci.get('head_sha') == sha and ci.get('repository') == repo
                    and ci.get('scope') == ('agent_contract' if infra else 'product'), tid + ': wrong CI scope or SHA')
            required_checks = gates['agent_contract_ci_checks' if infra else 'product_ci_checks']
            require(isinstance(required_checks, list) and bool(required_checks), 'Required CI checks missing')
            checks = ci.get('checks', [])
            from github_ci import verify_checks
            require(not verify_checks(checks, sha, required_checks), tid + ': required exact-SHA CI failed or pending')
            # Controller also verifies check app/workflow identity against its own
            # protected allowlist; a name-only local report is not trusted input.
            for name in required_checks:
                matches = [c for c in checks if c.get('name') == name and c.get('head_sha') == sha]
                latest = max(matches, key=lambda c: (c.get('started_at') or '', c.get('id') or 0))
                require(latest.get('app_slug') == 'github-actions'
                        and isinstance(latest.get('url'), str)
                        and latest['url'].startswith('https://github.com/'), tid + ': untrusted CI producer')
        decisions = set()
        needed = {d for tid in [task_id, *deps] for d in tasks[tid].get('blocked_on_decision', [])}
        for decision in needed:
            approval = payload.get('decisions', {}).get(decision, {})
            require(approval.get('status') == 'APPROVED' and approval.get('head_sha') == sha
                    and isinstance(approval.get('approved_by'), str) and bool(approval['approved_by'].strip()),
                    'Business decision is not approved: ' + decision)
            artifact(root, approval.get('report'))
            decisions.add(decision)
        return decisions
    except ReadinessError:
        raise
    except Exception as exc:
        # Never echo artifact content, key bytes or arbitrary JSON values.
        raise ReadinessError('Malformed, missing or unverifiable readiness evidence (' + type(exc).__name__ + ')') from exc
