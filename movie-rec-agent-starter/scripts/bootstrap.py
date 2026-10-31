"""Integration-only bootstrap: prepare evidence or import external approval.

No key generation, signing, force switch, owner impersonation or dataset access.
The external administrator must protect the trust config and runner environment.
"""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.parse
import urllib.request

import yaml
from github_ci import verify_checks
from readiness import ReadinessError, artifact, canonical, digest, local_path, read_json, require, utc

ROOT = Path(__file__).resolve().parents[2]
TASK = 'SDLC-INTEGRATION-001'
FOLDER = Path('.runtime/bootstrap')
CHECKPOINT = (FOLDER / 'checkpoint.json').as_posix()
WORKFLOW = '.github/workflows/agent-contracts.yml'


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE).decode('utf-8').strip()


def revision(root):
    # Tracked source must match reviewed HEAD. Unrelated untracked files are
    # preserved; tests run in an archive that cannot import those files or raw.
    git(root, 'diff', '--no-ext-diff', '--quiet', 'HEAD', '--')
    branch = git(root, 'branch', '--show-current')
    require(branch.startswith('feature/'), 'Bootstrap requires a feature branch')
    remote = git(root, 'remote', 'get-url', 'origin')
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?', remote)
    require(match is not None, 'Bootstrap requires an HTTPS github.com origin')
    return {'repository': remote, 'repo': match[1], 'branch': branch,
            'head_sha': git(root, 'rev-parse', 'HEAD'), 'tree_sha': git(root, 'rev-parse', 'HEAD^{tree}')}


class GitHub:
    def __init__(self, repo):
        self.repo = repo

    def get(self, suffix):
        require(suffix.startswith('/') and not suffix.startswith('//'), 'Invalid GitHub API path')
        headers = {'Accept': 'application/vnd.github+json', 'User-Agent': 'MovieRec-Bootstrap',
                   'X-GitHub-Api-Version': '2022-11-28'}
        token = os.environ.get('GITHUB_TOKEN')
        if token:
            headers['Authorization'] = 'Bearer ' + token
        request = urllib.request.Request('https://api.github.com/repos/' + self.repo + suffix, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)


def live_ci(rev, required, client):
    ref = client.get('/git/ref/heads/' + urllib.parse.quote(rev['branch'], safe=''))
    require(ref['object']['sha'] == rev['head_sha'], 'Remote branch is not synchronized')
    commit = client.get('/commits/' + rev['head_sha'])
    require(commit['sha'] == rev['head_sha'] and commit['commit']['tree']['sha'] == rev['tree_sha'],
            'Remote commit/tree mismatch')
    author = commit.get('author', {}).get('login') if commit.get('author') else None
    require(isinstance(author, str) and author, 'Authenticated GitHub commit author required')
    author_ids = {'github:' + author.casefold(), 'email:' + commit['commit']['author']['email'].casefold()}
    checks = []
    for page in range(1, 11):
        result = client.get('/commits/' + rev['head_sha'] + f'/check-runs?filter=all&per_page=100&page={page}')
        checks.extend(result['check_runs'])
        if len(checks) >= result['total_count']:
            break
    else:
        raise ReadinessError('Too many check runs to verify completely')
    require(isinstance(required, list) and bool(required), 'Required infra CI checks missing')
    require(not verify_checks(checks, rev['head_sha'], required), 'Required latest exact-SHA CI is not successful')
    evidence = []
    for name in required:
        matches = [c for c in checks if c.get('name') == name and c.get('head_sha') == rev['head_sha']]
        check = max(matches, key=lambda c: (c.get('started_at') or '', c.get('id') or 0))
        require(check.get('app', {}).get('slug') == 'github-actions'
                and check.get('app', {}).get('id') == 15368, 'CI producer is not GitHub Actions')
        pattern = r'https://github\.com/' + re.escape(rev['repo']) + r'/actions/runs/(\d+)/job/(\d+)'
        link = re.fullmatch(pattern, check.get('details_url', ''))
        require(link is not None, 'CI run identity missing')
        run = client.get('/actions/runs/' + link[1])
        require(run['head_sha'] == rev['head_sha'] and run['path'] == WORKFLOW
                and run['status'] == 'completed' and run['conclusion'] == 'success'
                and run['event'] == 'push' and run['head_repository']['full_name'] == rev['repo']
                and run['check_suite_id'] == check['check_suite']['id'], 'CI workflow provenance mismatch')
        job = client.get('/actions/jobs/' + link[2])
        require(job['run_id'] == run['id'] and job['head_sha'] == rev['head_sha']
                and job['name'] == name and job['status'] == 'completed' and job['conclusion'] == 'success'
                and job['check_run_url'].endswith('/check-runs/' + str(check['id'])), 'CI job/check mismatch')
        evidence.append({'name': name, 'check_id': check['id'], 'run_id': run['id'],
                         'job_id': job['id'], 'head_sha': rev['head_sha'], 'url': check['details_url']})
    return {'author_identities': sorted(author_ids), 'checks': evidence}


def contract(root):
    from agentctl import load_tasks, validate_tasks, local_tests_for_task
    tasks = load_tasks(root)
    require(not validate_tasks(tasks), 'Invalid task registry')
    task = tasks[TASK]
    require(task['type'] == 'infra' and task['dependencies'] == [], 'Bootstrap task contract changed')
    selections = local_tests_for_task(task, root)
    gates = yaml.safe_load((root / 'movie-rec-agent-starter/.agents/policies/quality_gates.yaml').read_text(encoding='utf-8'))
    require({'acceptance_tests', 'independent_review', 'remote_ci_sha_match'} <= set(gates['always_required']),
            'Mandatory verification policy missing')
    return task, selections, gates['agent_contract_ci_checks']


def test_commands(selections):
    return [['-m', 'pytest', '-q', '-p', 'no:cacheprovider', *selections],
            ['-m', 'unittest', 'discover', '-s', 'movie-rec-agent-starter/tests/harness', '-v']]


def runtime_path(root, path):
    root = root.resolve()
    require(path.is_absolute() and path.is_relative_to(root / '.runtime') and path.resolve() == path,
            'Runtime output path is redirected or outside .runtime')
    return path


def snapshot_checks(root, selections, output):
    runtime_path(root, output)
    archive = subprocess.check_output(['git', 'archive', '--format=tar', 'HEAD'], cwd=root, stderr=subprocess.PIPE)
    output.mkdir(parents=True, exist_ok=False)
    results = []
    with tempfile.TemporaryDirectory(prefix='snapshot-', dir=runtime_path(root, root / FOLDER)) as tmp:
        snapshot = Path(tmp)
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as stream:
            for item in stream.getmembers():
                require((snapshot / item.name).resolve().is_relative_to(snapshot.resolve())
                        and not item.issym() and not item.islnk()
                        and (item.isdir() or item.isfile()), 'Unsafe Git archive entry')
            stream.extractall(snapshot, filter='data')
        # Deliberate allowlist: no tokens, trust paths, home overrides, Python
        # injection, user pytest plugins, raw datasets or inherited CI secrets.
        env = {k: v for k, v in os.environ.items() if k.upper() in {
            'SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP', 'COMSPEC', 'PATHEXT', 'LANG', 'LC_ALL'}}
        env.update(PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
        for index, args in enumerate(test_commands(selections)):
            process = subprocess.run([sys.executable, '-X', 'utf8', '-B', *args], cwd=snapshot,
                                     env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=600)
            log = output / f'check-{index}.log'
            log.write_bytes(process.stdout)
            require(process.returncode == 0, 'Snapshot tests failed; see ' + str(log.relative_to(root)))
            results.append({'args': args, 'exit_code': process.returncode,
                            'report': {'path': log.relative_to(root).as_posix(), 'sha256': digest(log)}})
    return results


def save(root, path, value):
    runtime_path(root, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path(root, path)
    # Unique exclusive temporary file; never follow an author-created .tmp link.
    with tempfile.NamedTemporaryFile(prefix='.bootstrap-', suffix='.tmp', dir=path.parent, delete=False) as handle:
        temp = Path(handle.name)
        handle.write(canonical(value) + b'\n')
        handle.flush()
        os.fsync(handle.fileno())
    try:
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def prepare(root):
    rev = revision(root)
    task, selections, required = contract(root)
    ci = live_ci(rev, required, GitHub(rev['repo']))
    stamp = datetime.now(timezone.utc)
    output = root / FOLDER / (rev['head_sha'] + '-' + stamp.strftime('%Y%m%dT%H%M%S%fZ'))
    results = snapshot_checks(root, selections, output)
    require(revision(root) == rev, 'Source changed during preparation')
    payload = {**rev, 'schema_version': 1, 'task_id': TASK, 'purpose': 'integration-bootstrap-only',
               'issued_at': stamp.isoformat(), 'expires_at': (stamp + timedelta(hours=24)).isoformat(),
               'reviewer_identity': None, 'decision': 'NOT_REVIEWED', 'ci': ci,
               'acceptance_ids': [a['id'] for a in task['acceptance_criteria']], 'local_checks': results}
    path = output / 'request.json'
    save(root, path, payload)
    return path


def trust(root):
    configured = os.environ.get('MOVIEREC_BOOTSTRAP_TRUST_FILE')
    require(bool(configured), 'External owner-approved bootstrap trust config is not provisioned')
    path = Path(configured)
    require(path.is_absolute(), 'Trust config must be an absolute external path')
    path = path.resolve(strict=True)
    require(not path.is_relative_to(root.resolve()), 'Trust config must be outside checkout')
    config = read_json(path)
    require(config.get('schema_version') == 1 and isinstance(config.get('reviewers'), dict), 'Invalid trust config')
    return config


def signed_review(root, path, rev, current_ci, now=None):
    config = trust(root)
    require(config.get('repository') == rev['repository'], 'Trust config repository mismatch')
    envelope = read_json(path)
    payload = envelope['payload']
    reviewer = payload.get('reviewer_identity')
    require(isinstance(reviewer, str) and reviewer == reviewer.strip().casefold() and reviewer,
            'Reviewer identity must be canonical lowercase')
    require(reviewer not in current_ci['author_identities'], 'Author cannot approve own commit')
    approved = config['reviewers'].get(reviewer)
    require(isinstance(approved, dict), 'Reviewer is not approved by external owner')
    key_file = Path(approved['public_key_file'])
    require(key_file.is_absolute(), 'Reviewer key must use absolute external path')
    key_file = key_file.resolve(strict=True)
    require(not key_file.is_relative_to(root.resolve()) and digest(key_file) == approved.get('sha256'),
            'Reviewer key is inside checkout or fingerprint mismatch')
    from cryptography.hazmat.primitives.serialization import load_pem_public_key
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    key = load_pem_public_key(key_file.read_bytes())
    require(isinstance(key, Ed25519PublicKey), 'Reviewer key must be Ed25519')
    key.verify(base64.b64decode(envelope['signature'], validate=True), canonical(payload))
    require(type(payload.get('schema_version')) is int and payload['schema_version'] == 1
            and payload.get('task_id') == TASK and payload.get('purpose') == 'integration-bootstrap-only'
            and payload.get('decision') == 'APPROVED', 'Not an Integration bootstrap approval')
    for field in ('repository', 'repo', 'branch', 'head_sha', 'tree_sha'):
        require(payload.get(field) == rev[field], 'Review revision mismatch: ' + field)
    issued, expires = utc(payload.get('issued_at')), utc(payload.get('expires_at'))
    require(issued <= (now or datetime.now(timezone.utc)) < expires
            and timedelta(0) < expires - issued <= timedelta(hours=24), 'Review approval is stale or future-dated')
    require(payload.get('ci') == current_ci, 'Live CI/author evidence changed; request fresh approval')
    task, selections, _ = contract(root)
    require(payload.get('acceptance_ids') == [a['id'] for a in task['acceptance_criteria']], 'Acceptance scope mismatch')
    checks = payload.get('local_checks')
    require(isinstance(checks, list) and len(checks) == 2, 'Missing local test evidence')
    for check, expected in zip(checks, test_commands(selections)):
        require(check.get('args') == expected and type(check.get('exit_code')) is int
                and check['exit_code'] == 0, 'Wrong or failed local test command')
        artifact(root, check.get('report'))
    return envelope


def verify_checkpoint(root=ROOT, review_path=None):
    try:
        trust(root)  # No network or mutable state is consulted without a trust anchor.
        rev = revision(root)
        _, _, required = contract(root)
        ci = live_ci(rev, required, GitHub(rev['repo']))
        path = local_path(root, CHECKPOINT) if review_path is None else local_path(root, review_path)
        envelope = signed_review(root, path, rev, ci)
        require(revision(root) == rev, 'Source changed during verification')
        return envelope
    except ReadinessError:
        raise
    except Exception as exc:
        raise ReadinessError('Bootstrap evidence is missing or invalid (' + type(exc).__name__ + ')') from exc


@contextmanager
def lease(root):
    path = runtime_path(root, root / FOLDER / 'finalize.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    try:
        yield
    finally:
        os.close(fd)
        path.unlink()


def finalize(root, review_path):
    # No status setter is exposed. The signed checkpoint is authoritative;
    # hand-editing demo state cannot satisfy SETUP start/next/run-local.
    with lease(root):
        envelope = verify_checkpoint(root, review_path)
        runtime_path(root, root / '.runtime/state.json')
        save(root, root / CHECKPOINT, envelope)
        from agentctl import read_state
        state = read_state(root)
        entry = state.setdefault('tasks', {}).setdefault(TASK, {})
        entry.update(status='VERIFIED', head_sha=envelope['payload']['head_sha'],
                     verified_at=datetime.now(timezone.utc).isoformat(), checkpoint=CHECKPOINT)
        save(root, root / '.runtime/state.json', state)
    return envelope['payload']['head_sha']


def main(argv=None):
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest='action', required=True)
    sub.add_parser('prepare')
    sub.add_parser('verify')
    sub.add_parser('finalize').add_argument('--review', required=True, help='Repository-relative signed envelope')
    args = cli.parse_args(argv)
    try:
        if args.action == 'prepare':
            print('AWAITING_EXTERNAL_APPROVAL:', prepare(ROOT).relative_to(ROOT).as_posix())
        elif args.action == 'verify':
            verify_checkpoint(ROOT)
            print('PASS: signed bootstrap checkpoint and live exact-SHA CI')
        else:
            print(TASK, 'VERIFIED by external approval and checked evidence:', finalize(ROOT, args.review))
        return 0
    except Exception as exc:
        # Do not print HTTP headers, credential values, signed data or key bytes.
        message = str(exc) if isinstance(exc, ReadinessError) else type(exc).__name__
        print('BLOCKED:', message, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
