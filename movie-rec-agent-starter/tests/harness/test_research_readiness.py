"""Governance-only fixtures: no dataset scan, EDA, training or live approval."""
import base64
import copy
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'movie-rec-agent-starter/scripts'))
import agentctl
import readiness


class PlanningContractTests(unittest.TestCase):
    def test_registry_preserves_schema_dependencies_and_no_cycles(self):
        tasks = agentctl.load_tasks()
        self.assertEqual([], agentctl.validate_tasks(tasks))
        self.assertEqual(28, len(tasks))
        self.assertEqual([f'DATA-{i:03}' for i in range(1, 7)], tasks['DATA-QUALITY-001']['dependencies'])
        self.assertEqual(['DATA-QUALITY-001'], tasks['RESEARCH-001']['dependencies'])
        self.assertEqual(['RESEARCH-001'], tasks['EDA-001']['dependencies'])
        self.assertEqual(['DATA-006', 'EDA-001'], tasks['SPLIT-001']['dependencies'])
        for tid in ('DATA-QUALITY-001', 'RESEARCH-001', 'EDA-001'):
            self.assertEqual('BLOCKED', tasks[tid]['status'])
        broken = copy.deepcopy(tasks)
        broken['DATA-001']['dependencies'].append('EDA-001')
        self.assertTrue(any('Cycle' in e for e in agentctl.validate_tasks(broken)))

    def test_index_contract_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / 'tasks'
            folder.mkdir()
            index = {'tasks': [{'id': 'LOCAL-001', 'file': 'LOCAL-001.yaml',
                                'dependencies': [], 'slides': [2], 'type': 'infra'}]}
            (folder / 'index.yaml').write_text(yaml.safe_dump(index), encoding='utf-8')
            (folder / 'LOCAL-001.yaml').write_text(yaml.safe_dump({
                'id': 'LOCAL-001', 'dependencies': ['OTHER-001'], 'source_slides': [2], 'type': 'infra'}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Index/contract mismatch'):
                agentctl.load_tasks(root)

    def test_twelve_hypotheses_complete_and_untested(self):
        registry = yaml.safe_load((ROOT / 'docs/research/HYPOTHESIS_REGISTRY.yaml').read_text(encoding='utf-8'))
        required = {'id', 'title', 'H0', 'H1', 'sources', 'formulas', 'required_features',
                    'cohorts', 'confounders', 'tests', 'metrics', 'uncertainty',
                    'potential_algorithms', 'evidence', 'status'}
        hypotheses = registry['hypotheses']
        self.assertEqual([f'H{i:02}' for i in range(1, 13)], [h['id'] for h in hypotheses])
        for h in hypotheses:
            self.assertTrue(required <= h.keys())
            for key in required - {'evidence'}:
                self.assertTrue(h[key], (h['id'], key))
            self.assertEqual([], h['evidence'])
            self.assertEqual('UNTESTED', h['status'])

    def test_feature_contracts_are_temporal_and_handle_missing_support(self):
        data = yaml.safe_load((ROOT / 'docs/research/FEATURE_RESEARCH_CATALOG.yaml').read_text(encoding='utf-8'))
        self.assertEqual('event_timestamp < T', data['global_rules']['history_filter'])
        ids = set()
        for feature in data['features']:
            self.assertNotIn(feature['id'], ids)
            ids.add(feature['id'])
            for key in ('hypotheses', 'sources', 'formula', 'availability', 'missing', 'shrinkage'):
                self.assertTrue(feature[key])
        self.assertTrue({'rating_bias', 'genre_affinity', 'semantic_affinity', 'movie_age_preference',
                         'recency_activity', 'preference_drift', 'collaborative_signal',
                         'diversity_novelty', 'history_confidence', 'availability_mask'} <= ids)
        known = ids | {'all_point_in_time_features'}
        hypotheses = yaml.safe_load((ROOT / 'docs/research/HYPOTHESIS_REGISTRY.yaml').read_text(encoding='utf-8'))
        for h in hypotheses['hypotheses']:
            self.assertTrue(set(h['required_features']) <= known)

    def test_planning_local_links_resolve(self):
        for file in (ROOT / 'docs/research').glob('*.md'):
            for target in re.findall(r'\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
                if '://' in target or target.startswith('#'):
                    continue
                self.assertTrue((file.parent / target.split('#')[0]).is_file(), (file.name, target))

    def test_empirical_acceptance_is_still_deferred(self):
        tasks = agentctl.load_tasks()
        for tid in ('DATA-QUALITY-001', 'RESEARCH-001', 'EDA-001'):
            with self.assertRaises(FileNotFoundError):
                agentctl.local_tests_for_task(tasks[tid])
        eda = ' '.join(a['description'] for a in tasks['EDA-001']['acceptance_criteria'])
        for concept in ('sparse', 'release', 'future leakage', 'malformed', 'manifest', 'consistent'):
            # Manifest is the task's prerequisite contract; the other terms are ACs.
            self.assertIn(concept, eda + ' ' + tasks['EDA-001']['description'])


class SignedEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        parent = Path(self.temp.name)
        self.root = parent / 'checkout'
        self.root.mkdir()
        self.tasks = agentctl.load_tasks()
        self.task_id = 'EDA-001'
        self.sha = 'a' * 40
        self.repo = 'https://github.com/example/fixture.git'
        self.clock = datetime(2026, 10, 31, 0, 30, tzinfo=timezone.utc)
        self.key = Ed25519PrivateKey.generate()
        key_file = parent / 'controller-public.pem'
        key_file.write_bytes(self.key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
        self.env = {'MOVIEREC_READINESS_PUBLIC_KEY_FILE': str(key_file)}
        gates = self.root / 'movie-rec-agent-starter/.agents/policies/quality_gates.yaml'
        gates.parent.mkdir(parents=True)
        gates.write_bytes((ROOT / 'movie-rec-agent-starter/.agents/policies/quality_gates.yaml').read_bytes())
        runtime = self.root / '.runtime'
        runtime.mkdir()
        report = runtime / 'fixture-report.txt'
        report.write_text('Synthetic controller evidence, not real acceptance.\n', encoding='utf-8')
        self.report = {'path': '.runtime/fixture-report.txt', 'sha256': readiness.digest(report)}
        entries = []
        for suffix, family in readiness.REQUIRED_SOURCES.items():
            path = self.root / 'dataset_linkage_work/raw' / suffix
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic source hash fixture\n')
            entries.append({'path': path.relative_to(self.root).as_posix(), 'sha256': readiness.digest(path),
                            'size_bytes': path.stat().st_size, 'source': family, 'source_version': 'fixture-v1',
                            'retrieved_at_utc': '2026-10-30T00:00:00Z'})
        self.manifest = {'schema_version': 1, 'raw_root': 'dataset_linkage_work/raw', 'files': entries}
        self.manifest_path = runtime / 'manifest.json'
        self.manifest_path.write_bytes(readiness.canonical(self.manifest))
        manifest_ref = {'path': '.runtime/manifest.json', 'sha256': readiness.digest(self.manifest_path)}
        self.payload = {'schema_version': 1, 'repository': self.repo, 'head_sha': self.sha,
                        'issued_at': '2026-10-31T00:00:00Z', 'expires_at': '2026-10-31T01:00:00Z',
                        'dataset_manifest': manifest_ref, 'tasks': {}, 'decisions': {}}
        deps = readiness.prerequisite_ids(self.tasks, self.task_id)
        for tid in deps:
            task = self.tasks[tid]
            infra = task['type'] == 'infra'
            self.payload['tasks'][tid] = {
                'status': 'VERIFIED', 'head_sha': self.sha, 'dataset_manifest_sha256': manifest_ref['sha256'],
                'acceptance': {a['id']: {'exit_code': 0, 'test_case': a['test_case'],
                                        'command': ['python', '-m', 'pytest', a['planned_test'] + '::' + a['test_case']],
                                        'report': dict(self.report)} for a in task['acceptance_criteria']},
                'review': {'decision': 'APPROVED', 'head_sha': self.sha, 'author_identity': 'fixture-author',
                           'reviewer_identity': 'fixture-reviewer', 'report': dict(self.report)},
                'ci': {'repository': self.repo, 'head_sha': self.sha,
                       'scope': 'agent_contract' if infra else 'product', 'checks': [{
                           'name': 'validate-contracts' if infra else 'test', 'head_sha': self.sha,
                           'status': 'completed', 'conclusion': 'success', 'id': 1,
                           'started_at': '2026-10-31T00:00:00Z', 'app_slug': 'github-actions',
                           'url': 'https://github.com/example/fixture/actions/runs/1'}]}}
        decisions = {d for tid in [self.task_id, *deps] for d in self.tasks[tid].get('blocked_on_decision', [])}
        self.payload['decisions'] = {d: {'status': 'APPROVED', 'head_sha': self.sha,
                                        'approved_by': 'fixture-owner', 'report': dict(self.report)} for d in decisions}
        # Committed source/contract fixtures, independent from real worktree.
        for source in (ROOT / 'movie-rec-agent-starter/tasks').glob('*.yaml'):
            dest = self.root / 'movie-rec-agent-starter/tasks' / source.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(source.read_bytes())
        for name in ('agentctl.py', 'readiness.py', 'github_ci.py'):
            dest = self.root / 'movie-rec-agent-starter/scripts' / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / 'movie-rec-agent-starter/scripts' / name).read_bytes())
        workflow = self.root / '.github/workflows/agent-contracts.yml'
        workflow.parent.mkdir(parents=True)
        workflow.write_bytes((ROOT / '.github/workflows/agent-contracts.yml').read_bytes())
        for tid in deps:
            for ac in self.tasks[tid]['acceptance_criteria']:
                dest = self.root / ac['planned_test']
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text('# fixture-only acceptance source\n', encoding='utf-8')
        self.source = self.root / 'src/recommender/data/fixture.py'
        self.source.parent.mkdir(parents=True)
        self.source.write_text('# fixture-only prerequisite implementation\n', encoding='utf-8')
        self.tracked = {p.relative_to(self.root).as_posix() for p in self.root.rglob('*')
                        if p.is_file() and not p.is_relative_to(runtime)
                        and not p.is_relative_to(self.root / 'dataset_linkage_work')}
        def git_fixture(_root, *args):
            if args == ('rev-parse', 'HEAD'): return self.sha
            if args == ('remote', 'get-url', 'origin'): return self.repo
            if args == ('ls-tree', '-r', '--name-only', 'HEAD'): return '\n'.join(sorted(self.tracked))
            if args[:5] == ('diff', '--no-ext-diff', '--quiet', 'HEAD', '--'): return ''
            raise AssertionError('Unexpected fixture git operation')
        self.git_patch = patch('readiness.git_value', side_effect=git_fixture)
        self.git_patch.start()
        self.addCleanup(self.git_patch.stop)
        self.payload['inputs'] = {p: readiness.digest(self.root / p)
                                  for p in readiness.required_inputs(self.tasks, self.task_id, self.root)}

    def sign(self):
        signature = self.key.sign(readiness.canonical(self.payload))
        envelope = {'payload': self.payload, 'signature': base64.b64encode(signature).decode('ascii')}
        path = self.root / '.runtime/trusted-readiness.json'
        path.write_bytes(readiness.canonical(envelope))
        return path

    def verify(self):
        return readiness.verify_readiness(self.tasks, self.task_id, self.root, environ=self.env, clock=self.clock)

    def reject(self):
        self.sign()
        with self.assertRaises(readiness.ReadinessError):
            self.verify()

    def test_complete_signed_fixture_is_accepted_without_writes(self):
        self.sign()
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(set(self.payload['decisions']), self.verify())
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_no_anchor_and_checkout_anchor_fail(self):
        self.env.clear()
        self.reject()
        anchor = self.root / '.runtime/key.pem'
        anchor.write_bytes(b'not a trusted external key')
        self.env['MOVIEREC_READINESS_PUBLIC_KEY_FILE'] = str(anchor)
        self.reject()

    def test_unsigned_tampered_and_wrong_signer_fail(self):
        path = self.sign()
        path.write_text(json.dumps({'payload': self.payload}), encoding='utf-8')
        with self.assertRaises(readiness.ReadinessError):
            self.verify()
        path = self.sign()
        changed = json.loads(path.read_text(encoding='utf-8'))
        changed['payload']['head_sha'] = 'b' * 40
        path.write_text(json.dumps(changed), encoding='utf-8')
        with self.assertRaises(readiness.ReadinessError):
            self.verify()
        self.key = Ed25519PrivateKey.generate()
        self.reject()

    def test_stale_sha_repo_expiry_future_and_naive_times_fail(self):
        original = copy.deepcopy(self.payload)
        cases = [('head_sha', 'b' * 40), ('repository', 'https://github.com/other/repo.git'),
                 ('expires_at', '2026-10-31T00:15:00Z'), ('issued_at', '2026-10-31T00:45:00Z'),
                 ('issued_at', '2026-10-31T00:00:00'), ('expires_at', '2026-11-02T00:00:00Z'),
                 ('expires_at', 'not a timestamp')]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.payload = copy.deepcopy(original)
                self.payload[key] = value
                self.reject()

    def test_transitive_status_manifest_and_acceptance_fail_closed(self):
        original = copy.deepcopy(self.payload)
        for modification in ('missing', 'status', 'sha', 'manifest', 'test_missing', 'test_failed', 'test_bool', 'test_name'):
            with self.subTest(modification=modification):
                self.payload = copy.deepcopy(original)
                proof = self.payload['tasks']['DATA-001']
                ac = next(iter(proof['acceptance']))
                if modification == 'missing': del self.payload['tasks']['DATA-001']
                elif modification == 'status': proof['status'] = 'LOCAL_VERIFIED'
                elif modification == 'sha': proof['head_sha'] = 'b' * 40
                elif modification == 'manifest': proof['dataset_manifest_sha256'] = 'b' * 64
                elif modification == 'test_missing': del proof['acceptance'][ac]
                elif modification == 'test_failed': proof['acceptance'][ac]['exit_code'] = 1
                elif modification == 'test_bool': proof['acceptance'][ac]['exit_code'] = False
                else: proof['acceptance'][ac]['test_case'] = 'test_some_other_case'
                self.reject()

    def test_review_requires_independence_and_current_sha(self):
        original = copy.deepcopy(self.payload)
        for field, value in [('decision', 'NOT_REVIEWED'), ('reviewer_identity', ' FIXTURE-AUTHOR '),
                             ('reviewer_identity', ''), ('head_sha', 'b' * 40)]:
            self.payload = copy.deepcopy(original)
            self.payload['tasks']['DATA-QUALITY-001']['review'][field] = value
            self.reject()

    def test_product_ci_cannot_be_contract_only_pending_failed_or_stale(self):
        original = copy.deepcopy(self.payload)
        for field, value in [('name', 'validate-contracts'), ('head_sha', 'b' * 40),
                             ('status', 'in_progress'), ('conclusion', 'failure'),
                             ('conclusion', 'skipped'), ('app_slug', 'untrusted-app'), ('url', '')]:
            with self.subTest(field=field, value=value):
                self.payload = copy.deepcopy(original)
                self.payload['tasks']['DATA-QUALITY-001']['ci']['checks'][0][field] = value
                self.reject()
        self.payload = copy.deepcopy(original)
        self.payload['tasks']['DATA-QUALITY-001']['ci']['scope'] = 'agent_contract'
        self.reject()

    def test_latest_failed_ci_attempt_overrides_old_success(self):
        checks = self.payload['tasks']['DATA-QUALITY-001']['ci']['checks']
        newer = dict(checks[0], id=2, started_at='2026-10-31T00:10:00Z', conclusion='failure')
        checks.append(newer)
        self.reject()

    def test_decisions_must_have_signed_approval_evidence(self):
        self.payload['decisions'].pop('D-04')
        self.reject()

    def test_changed_source_missing_source_and_manifest_rejected(self):
        self.sign()
        path = self.root / self.manifest['files'][0]['path']
        path.write_bytes(b'changed')
        with self.assertRaises(readiness.ReadinessError): self.verify()
        path.unlink()
        with self.assertRaises(readiness.ReadinessError): self.verify()
        self.manifest_path.unlink()
        with self.assertRaises(readiness.ReadinessError): self.verify()

    def test_manifest_shape_and_source_provenance_rejected(self):
        original = copy.deepcopy(self.manifest)
        for modification in ('empty', 'omitted_source', 'duplicate', 'bad_version', 'bad_timestamp', 'bad_size', 'wrong_family'):
            with self.subTest(modification=modification):
                self.manifest = copy.deepcopy(original)
                files = self.manifest['files']
                if modification == 'empty': self.manifest['files'] = []
                elif modification == 'omitted_source': files.pop()
                elif modification == 'duplicate': files.append(dict(files[0]))
                elif modification == 'bad_version': files[0]['source_version'] = ''
                elif modification == 'bad_timestamp': files[0]['retrieved_at_utc'] = 'not-time'
                elif modification == 'bad_size': files[0]['size_bytes'] += 1
                else: files[0]['source'] = 'other'
                self.manifest_path.write_bytes(readiness.canonical(self.manifest))
                self.payload['dataset_manifest']['sha256'] = readiness.digest(self.manifest_path)
                self.reject()

    def test_artifact_hash_and_traversal_rejected(self):
        original = copy.deepcopy(self.payload)
        ac = next(iter(self.payload['tasks']['DATA-001']['acceptance']))
        for reference in ({'path': '../outside', 'sha256': 'a' * 64},
                          {'path': 'C:/outside', 'sha256': 'a' * 64},
                          {'path': '.runtime/fixture-report.txt', 'sha256': 'a' * 64},
                          {'path': '.runtime/missing', 'sha256': 'a' * 64}):
            self.payload = copy.deepcopy(original)
            self.payload['tasks']['DATA-001']['acceptance'][ac]['report'] = reference
            self.reject()

    def test_duplicate_json_keys_rejected(self):
        path = self.sign()
        path.write_text('{"payload":{},"payload":{},"signature":""}', encoding='utf-8')
        with self.assertRaises(readiness.ReadinessError): self.verify()

    def test_same_head_contract_policy_and_prerequisite_code_drift_rejected(self):
        self.sign()
        paths = [self.root / 'movie-rec-agent-starter/tasks/EDA-001.yaml',
                 self.root / 'movie-rec-agent-starter/tasks/index.yaml',
                 self.root / 'movie-rec-agent-starter/.agents/policies/quality_gates.yaml', self.source]
        for path in paths:
            with self.subTest(path=path.name):
                original = path.read_bytes()
                path.write_bytes(original + b'\n# changed at same HEAD\n')
                with self.assertRaises(readiness.ReadinessError): self.verify()
                path.write_bytes(original)
        # Reproduce review attack: weaken the object and on-disk contract/index,
        # then replay a genuine previously signed envelope at the same SHA.
        self.tasks['EDA-001']['dependencies'] = []
        self.tasks['EDA-001']['blocked_on_decision'] = []
        task_file = self.root / 'movie-rec-agent-starter/tasks/EDA-001.yaml'
        task_file.write_text(yaml.safe_dump(self.tasks['EDA-001']), encoding='utf-8')
        index_file = self.root / 'movie-rec-agent-starter/tasks/index.yaml'
        index = yaml.safe_load(index_file.read_text(encoding='utf-8'))
        for item in index['tasks']:
            if item['id'] == 'EDA-001': item['dependencies'] = []
        index_file.write_text(yaml.safe_dump(index), encoding='utf-8')
        with self.assertRaises(readiness.ReadinessError): self.verify()

    def test_missing_signed_inputs_and_uncommitted_acceptance_rejected(self):
        original = copy.deepcopy(self.payload)
        del self.payload['inputs']
        self.reject()
        self.payload = original
        self.tracked.remove(self.tasks['DATA-001']['acceptance_criteria'][0]['planned_test'])
        self.reject()

    def test_in_memory_task_cannot_remove_acceptance_or_decisions(self):
        self.sign()
        self.tasks['DATA-001']['acceptance_criteria'].pop()
        with self.assertRaises(readiness.ReadinessError): self.verify()

    def test_signed_but_dirty_prerequisite_inputs_are_not_exact_sha_evidence(self):
        self.sign()
        original = readiness.git_value
        def dirty(root, *args):
            if args[:1] == ('diff',):
                raise RuntimeError('fixture dirty prerequisite at unchanged HEAD')
            return original(root, *args)
        with patch('readiness.git_value', side_effect=dirty):
            with self.assertRaises(readiness.ReadinessError): self.verify()


class EntryPointTests(unittest.TestCase):
    def setUp(self):
        self.tasks = agentctl.load_tasks()
        self.state = {'version': 1, 'tasks': {tid: {'status': 'VERIFIED'} for tid in self.tasks}}

    def test_next_never_trusts_local_verified_or_caller_approvals(self):
        for tid in readiness.PROTECTED_TASKS:
            self.state['tasks'][tid] = {'status': 'PLANNED'}
            with patch.dict(os.environ, {}, clear=True):
                self.assertNotIn(tid, agentctl.eligible_tasks(self.tasks, self.state, {'D-03','D-04','D-08','D-09'}))
            self.state['tasks'][tid] = {'status': 'VERIFIED'}

    def test_cli_start_and_resumed_run_local_reject_before_any_writes_or_tests(self):
        for tid in readiness.PROTECTED_TASKS:
            for action, status in [('start', 'PLANNED'), ('run-local', 'RUNNING')]:
                with self.subTest(tid=tid, action=action):
                    self.state['tasks'][tid] = {'status': status}
                    with patch.dict(os.environ, {}, clear=True), \
                         patch('agentctl.load_tasks', return_value=self.tasks), \
                         patch('agentctl.read_state', return_value=self.state), \
                         patch('agentctl.write_state') as write, \
                         patch('agentctl.subprocess.run') as run, \
                         patch('sys.stderr', new_callable=io.StringIO):
                        self.assertEqual(2, agentctl.main([action, tid]))
                        write.assert_not_called()
                        run.assert_not_called()
                    self.state['tasks'][tid] = {'status': 'VERIFIED'}

    def test_direct_runner_rejects_without_creating_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {}, clear=True), \
                 patch('agentctl.load_tasks', return_value=self.tasks), \
                 patch('agentctl.read_state', return_value=self.state):
                with self.assertRaises(readiness.ReadinessError):
                    agentctl.run_local(self.tasks['EDA-001'], root)
            self.assertFalse((root / '.runtime').exists())


if __name__ == '__main__':
    unittest.main()
