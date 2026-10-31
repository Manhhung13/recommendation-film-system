"""Synthetic bootstrap verification only; no real trust provisioning or data."""
import base64
import copy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import agentctl
import bootstrap as boot
from readiness import ReadinessError, canonical, digest


class ExternalApprovalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        parent = Path(self.tmp.name)
        self.root = parent / 'checkout'
        self.root.mkdir()
        self.key = Ed25519PrivateKey.generate()
        self.key_file = parent / 'reviewer.pem'
        self.key_file.write_bytes(self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.rev = {'repository': 'https://github.com/example/repo.git', 'repo': 'example/repo',
                    'branch': 'feature/bootstrap', 'head_sha': 'a' * 40, 'tree_sha': 'b' * 40}
        self.ci = {'author_identities': ['github:author', 'email:author@example.test'],
                   'checks': [{'name': 'validate-contracts', 'head_sha': 'a' * 40,
                               'check_id': 3, 'run_id': 1, 'job_id': 2, 'url': 'https://github.com/example/repo/actions/runs/1/job/2'}]}
        tasks = agentctl.load_tasks()
        self.task = tasks[boot.TASK]
        self.selections = agentctl.local_tests_for_task(self.task)
        self.clock = datetime(2026, 10, 31, 0, 30, tzinfo=timezone.utc)
        self.config_path = parent / 'owner-trust.json'
        self.config = {'schema_version': 1, 'repository': self.rev['repository'], 'reviewers': {
            'github:reviewer': {'public_key_file': str(self.key_file), 'sha256': digest(self.key_file)}}}
        self.config_path.write_bytes(canonical(self.config))
        self.env = patch.dict(os.environ, {'MOVIEREC_BOOTSTRAP_TRUST_FILE': str(self.config_path)}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.contract_patch = patch('bootstrap.contract', return_value=(self.task, self.selections, ['validate-contracts']))
        self.contract_patch.start()
        self.addCleanup(self.contract_patch.stop)
        (self.root / boot.FOLDER).mkdir(parents=True)
        report = self.root / boot.FOLDER / 'fixture.log'
        report.write_text('Synthetic successful test-process log\n', encoding='utf-8')
        self.payload = {**self.rev, 'schema_version': 1, 'task_id': boot.TASK, 'purpose': 'integration-bootstrap-only',
                        'reviewer_identity': 'github:reviewer', 'decision': 'APPROVED',
                        'issued_at': '2026-10-31T00:00:00Z', 'expires_at': '2026-10-31T01:00:00Z',
                        'ci': copy.deepcopy(self.ci), 'acceptance_ids': [a['id'] for a in self.task['acceptance_criteria']],
                        'local_checks': [{'args': args, 'exit_code': 0, 'report': {
                            'path': report.relative_to(self.root).as_posix(), 'sha256': digest(report)}}
                                         for args in boot.test_commands(self.selections)]}
        self.envelope_path = self.root / boot.FOLDER / 'signed-review.json'

    def sign_fixture(self):
        envelope = {'payload': self.payload, 'signature': base64.b64encode(self.key.sign(canonical(self.payload))).decode()}
        self.envelope_path.write_bytes(canonical(envelope))
        return envelope

    def verify(self):
        return boot.signed_review(self.root, self.envelope_path, self.rev, self.ci, self.clock)

    def test_external_signature_validates_without_state_writes(self):
        expected = self.sign_fixture()
        self.assertEqual(expected, self.verify())
        self.assertFalse((self.root / '.runtime/state.json').exists())

    def test_missing_anchor_rejects_before_network_and_state(self):
        with patch.dict(os.environ, {}, clear=True), patch('bootstrap.live_ci') as network:
            with self.assertRaisesRegex(ReadinessError, 'not provisioned'):
                boot.verify_checkpoint(self.root)
            network.assert_not_called()
        self.assertFalse((self.root / '.runtime/state.json').exists())

    def test_self_approval_unknown_reviewer_and_checkout_anchor_rejected(self):
        for identity in ('github:author', 'email:author@example.test', 'github:unknown'):
            self.payload['reviewer_identity'] = identity
            self.sign_fixture()
            with self.assertRaises(ReadinessError): self.verify()
        inside = self.root / 'trust.json'
        inside.write_bytes(canonical(self.config))
        with patch.dict(os.environ, {'MOVIEREC_BOOTSTRAP_TRUST_FILE': str(inside)}):
            with self.assertRaises(ReadinessError): boot.trust(self.root)

    def test_bad_signature_tamper_and_key_fingerprint_rejected(self):
        envelope = self.sign_fixture()
        envelope['payload']['decision'] = 'NOT_REVIEWED'
        self.envelope_path.write_bytes(canonical(envelope))
        with self.assertRaises(Exception): self.verify()
        self.payload['decision'] = 'APPROVED'
        self.sign_fixture()
        self.key_file.write_bytes(b'wrong key bytes')
        with self.assertRaises(ReadinessError): self.verify()

    def test_scope_sha_tree_author_ci_and_time_mismatch_rejected(self):
        original = copy.deepcopy(self.payload)
        for key, value in [('head_sha', 'c' * 40), ('tree_sha', 'c' * 40), ('task_id', 'SETUP-001'),
                           ('purpose', 'data-readiness'), ('repository', 'https://github.com/other/repo.git'),
                           ('decision', 'NOT_REVIEWED'), ('expires_at', '2026-10-31T00:00:01Z'),
                           ('issued_at', '2026-10-31T00:40:00Z'), ('expires_at', '2026-11-03T00:00:00Z'),
                           ('issued_at', '2026-10-31T00:00:00'), ('ci', {})]:
            with self.subTest(key=key, value=value):
                self.payload = copy.deepcopy(original)
                self.payload[key] = value
                self.sign_fixture()
                with self.assertRaises(ReadinessError): self.verify()

    def test_missing_failed_wrong_or_changed_test_evidence_rejected(self):
        original = copy.deepcopy(self.payload)
        for mutation in ('acceptance', 'missing_check', 'wrong_command', 'failed', 'bool', 'bad_hash', 'traversal'):
            with self.subTest(mutation=mutation):
                self.payload = copy.deepcopy(original)
                if mutation == 'acceptance': self.payload['acceptance_ids'].pop()
                elif mutation == 'missing_check': self.payload['local_checks'].pop()
                elif mutation == 'wrong_command': self.payload['local_checks'][0]['args'] = ['-c', 'pass']
                elif mutation == 'failed': self.payload['local_checks'][0]['exit_code'] = 1
                elif mutation == 'bool': self.payload['local_checks'][0]['exit_code'] = False
                elif mutation == 'bad_hash': self.payload['local_checks'][0]['report']['sha256'] = 'c' * 64
                else: self.payload['local_checks'][0]['report']['path'] = '../outside'
                self.sign_fixture()
                with self.assertRaises(ReadinessError): self.verify()

    def test_finalize_requires_valid_external_evidence_and_is_idempotent(self):
        envelope = self.sign_fixture()
        with patch('bootstrap.verify_checkpoint', return_value=envelope):
            for _ in range(2):
                self.assertEqual(self.rev['head_sha'], boot.finalize(self.root, '.runtime/bootstrap/signed-review.json'))
        state = agentctl.read_state(self.root)
        self.assertEqual('VERIFIED', state['tasks'][boot.TASK]['status'])
        self.assertEqual(envelope, json.loads((self.root / boot.CHECKPOINT).read_text(encoding='utf-8')))
        before = (self.root / '.runtime/state.json').read_bytes()
        with patch('bootstrap.verify_checkpoint', side_effect=ReadinessError('fixture approval rejected')):
            with self.assertRaises(ReadinessError): boot.finalize(self.root, 'invalid.json')
        self.assertEqual(before, (self.root / '.runtime/state.json').read_bytes())
        self.assertFalse((self.root / boot.FOLDER / 'finalize.lock').exists())

    def test_finalize_lease_refuses_second_writer(self):
        with boot.lease(self.root):
            with self.assertRaises(FileExistsError):
                with boot.lease(self.root): pass


class LiveEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.rev = {'repository': 'https://github.com/example/repo.git', 'repo': 'example/repo',
                    'branch': 'feature/bootstrap', 'head_sha': 'a' * 40, 'tree_sha': 'b' * 40}
        self.check = {'id': 3, 'name': 'validate-contracts', 'head_sha': 'a' * 40,
                      'status': 'completed', 'conclusion': 'success', 'started_at': '2026-10-31T00:00:00Z',
                      'app': {'slug': 'github-actions', 'id': 15368}, 'check_suite': {'id': 4},
                      'details_url': 'https://github.com/example/repo/actions/runs/1/job/2'}
        self.run = {'id': 1, 'head_sha': 'a' * 40, 'path': boot.WORKFLOW, 'status': 'completed',
                    'conclusion': 'success', 'event': 'push', 'head_repository': {'full_name': 'example/repo'},
                    'check_suite_id': 4}
        self.job = {'id': 2, 'run_id': 1, 'head_sha': 'a' * 40, 'name': 'validate-contracts',
                    'status': 'completed', 'conclusion': 'success',
                    'check_run_url': 'https://api.github.com/repos/example/repo/check-runs/3'}
        self.ref = {'object': {'sha': 'a' * 40}}
        self.commit = {'sha': 'a' * 40, 'commit': {'tree': {'sha': 'b' * 40},
                                                'author': {'email': 'author@example.test'}}, 'author': {'login': 'Author'}}
        self.checks = [self.check]
        def get(path):
            if path.startswith('/git/ref/'): return self.ref
            if '/check-runs?' in path: return {'total_count': len(self.checks), 'check_runs': self.checks}
            if path.startswith('/commits/'): return self.commit
            if path.startswith('/actions/runs/'): return self.run
            if path.startswith('/actions/jobs/'): return self.job
            raise AssertionError(path)
        self.client = Mock(get=Mock(side_effect=get))

    def test_real_provenance_shape_is_required(self):
        result = boot.live_ci(self.rev, ['validate-contracts'], self.client)
        self.assertEqual(['email:author@example.test', 'github:author'], result['author_identities'])
        self.assertEqual(3, result['checks'][0]['check_id'])

    def test_latest_ci_not_old_success_and_full_workflow_identity(self):
        original = copy.deepcopy(self.check)
        for field, value in [('head_sha', 'c' * 40), ('status', 'in_progress'), ('conclusion', 'failure'),
                             ('conclusion', 'skipped'), ('app', {'slug': 'github-actions', 'id': 0})]:
            with self.subTest(field=field):
                self.check.clear(); self.check.update(copy.deepcopy(original)); self.check[field] = value
                with self.assertRaises(ReadinessError): boot.live_ci(self.rev, ['validate-contracts'], self.client)
        self.check.clear(); self.check.update(original)
        self.checks.append(dict(self.check, id=5, started_at='2026-10-31T00:10:00Z', conclusion='failure'))
        with self.assertRaises(ReadinessError): boot.live_ci(self.rev, ['validate-contracts'], self.client)

    def test_remote_ref_tree_workflow_fork_and_job_mismatch_rejected(self):
        for target, field, value in [(self.ref['object'], 'sha', 'c' * 40),
                                     (self.commit['commit']['tree'], 'sha', 'c' * 40),
                                     (self.run, 'path', 'untrusted.yml'), (self.run, 'event', 'pull_request'),
                                     (self.run['head_repository'], 'full_name', 'fork/repo'),
                                     (self.run, 'check_suite_id', 0), (self.job, 'run_id', 0),
                                     (self.job, 'check_run_url', 'https://example.test/not-a-check')]:
            with self.subTest(field=field):
                old = target[field]; target[field] = value
                with self.assertRaises(ReadinessError): boot.live_ci(self.rev, ['validate-contracts'], self.client)
                target[field] = old


class EntryAndIsolationTests(unittest.TestCase):
    def test_forged_runtime_verified_cannot_authorize_setup_or_direct_runner(self):
        tasks = agentctl.load_tasks()
        state = {'tasks': {boot.TASK: {'status': 'VERIFIED'}}}
        with patch.dict(os.environ, {}, clear=True):
            self.assertNotIn('SETUP-001', agentctl.eligible_tasks(tasks, state))
            with patch('agentctl.load_tasks', return_value=tasks), patch('agentctl.read_state', return_value=state):
                with self.assertRaises(ReadinessError): agentctl.run_local(tasks['SETUP-001'])

    def test_source_dirty_and_nonfeature_rejected(self):
        with patch('bootstrap.git', side_effect=subprocess.CalledProcessError(1, ['git'])):
            with self.assertRaises(subprocess.CalledProcessError): boot.revision(Path.cwd())
        with patch('bootstrap.git', side_effect=['', 'main']):
            with self.assertRaises(ReadinessError): boot.revision(Path.cwd())

    def test_snapshot_uses_only_archived_files_and_scrubs_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / boot.FOLDER).mkdir(parents=True)
            (root / 'raw-sentinel').write_text('must never be copied', encoding='utf-8')
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode='w') as tar:
                item = tarfile.TarInfo('tracked.txt'); item.size = 5
                tar.addfile(item, io.BytesIO(b'hello'))
            def run(command, *, cwd, env, **kwargs):
                self.assertTrue((cwd / 'tracked.txt').exists())
                self.assertFalse((cwd / 'raw-sentinel').exists())
                self.assertNotIn('GITHUB_TOKEN', env); self.assertNotIn('PYTHONPATH', env)
                self.assertEqual('1', env['PYTEST_DISABLE_PLUGIN_AUTOLOAD'])
                return subprocess.CompletedProcess(command, 0, b'synthetic subprocess success\n')
            with patch('bootstrap.subprocess.check_output', return_value=buffer.getvalue()), \
                 patch('bootstrap.subprocess.run', side_effect=run), \
                 patch.dict(os.environ, {'GITHUB_TOKEN': 'fixture-only', 'PYTHONPATH': 'untrusted'}):
                results = boot.snapshot_checks(root, ['test.py::test_a'], root / boot.FOLDER / 'evidence')
            self.assertEqual(2, len(results))
            self.assertEqual('must never be copied', (root / 'raw-sentinel').read_text(encoding='utf-8'))

    def test_archive_traversal_and_symlink_rejected_before_test_execution(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)]:
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); (root / boot.FOLDER).mkdir(parents=True)
                buffer = io.BytesIO()
                with tarfile.open(fileobj=buffer, mode='w') as tar:
                    item = tarfile.TarInfo(name); item.type = kind; item.linkname = '../escape'
                    tar.addfile(item)
                with patch('bootstrap.subprocess.check_output', return_value=buffer.getvalue()), \
                     patch('bootstrap.subprocess.run') as run:
                    with self.assertRaises(ReadinessError):
                        boot.snapshot_checks(root, [], root / boot.FOLDER / 'evidence')
                    run.assert_not_called()

    def test_runtime_redirection_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            raw = root / 'raw-sentinel'
            raw.write_text('unchanged', encoding='utf-8')
            target = root / boot.FOLDER / 'checkpoint.json'
            original = Path.resolve
            def redirected(path, *args, **kwargs):
                return raw if path == target else original(path, *args, **kwargs)
            with patch.object(Path, 'resolve', redirected):
                with self.assertRaises(ReadinessError): boot.save(root, target, {'status': 'untrusted'})
            self.assertEqual('unchanged', raw.read_text(encoding='utf-8'))
            self.assertFalse((root / '.runtime').exists())


if __name__ == '__main__':
    unittest.main()
