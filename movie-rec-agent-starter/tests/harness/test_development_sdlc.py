"""Real local Git remotes and test processes; no keys, signatures or GitHub mocks."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
import agentctl as ctl
from git_preflight import check_safe_paths

class DevelopmentSDLC(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        base=Path(self.tmp.name);self.root=base/'checkout';self.root.mkdir()
        self.remote=base/'origin.git'
        subprocess.run(['git','init','--bare',str(self.remote)],check=True,capture_output=True)
        self.git('init','-b','feature/fixture')
        self.git('config','user.name','Fixture');self.git('config','user.email','fixture@example.invalid')
        self.git('config','core.autocrlf','false')
        self.git('remote','add','origin',str(self.remote))
        (self.root/'tasks').mkdir();(self.root/'tests').mkdir()
        self.task={'id':'TEST-001','title':'Fixture','type':'infra','source_slides':[2],
          'dependencies':[],'required_checks':['unit_tests','integration_tests'],
          'allowed_paths':['tasks/','tests/','.gitignore'],
          'acceptance_criteria':[{'id':'TEST-001-AC-01','planned_test':'tests/test_candidate.py','test_case':'test_candidate'}]}
        (self.root/'tasks/TEST-001.yaml').write_text(yaml.safe_dump(self.task),encoding='utf-8')
        (self.root/'tasks/index.yaml').write_text(yaml.safe_dump({'tasks':[{'id':'TEST-001','file':'TEST-001.yaml','dependencies':[],'slides':[2],'type':'infra'}]}),encoding='utf-8')
        (self.root/'tests/test_candidate.py').write_text('def test_candidate():\n    assert 2 + 2 == 4\n',encoding='utf-8')
        (self.root/'.gitignore').write_text('.runtime/\n__pycache__/\n.pytest_cache/\n',encoding='utf-8')
        self.git('add','tasks/TEST-001.yaml','tasks/index.yaml','tests/test_candidate.py','.gitignore')
        self.git('commit','-m','test: initial fixture [TEST-001]')
        self.tasks=ctl.load_tasks(self.root)
    def git(self,*args):return ctl.git(self.root,*args)
    def push(self):self.git('push','-u','origin','HEAD')
    def test_success_requires_tests_commit_and_real_remote(self):
        self.push();proof=ctl.complete(self.tasks,'TEST-001',self.root)
        self.assertEqual('DONE',proof['status'])
        self.assertEqual(proof,ctl.verify_completion(self.tasks,'TEST-001',self.root))
        self.assertEqual('DONE',ctl.read_state(self.root)['tasks']['TEST-001']['status'])
    def test_unpushed_branch_cannot_complete(self):
        with self.assertRaises(ValueError):ctl.complete(self.tasks,'TEST-001',self.root)
        self.assertFalse((self.root/'.runtime/evidence/TEST-001/completion.json').exists())
    def test_failed_tests_never_create_done(self):
        (self.root/'tests/test_candidate.py').write_text('def test_candidate():\n    assert False\n',encoding='utf-8')
        self.git('add','tests/test_candidate.py');self.git('commit','-m','test: failing fixture [TEST-001]');self.push()
        with self.assertRaisesRegex(ValueError,'tests failed'):ctl.complete(self.tasks,'TEST-001',self.root)
        self.assertFalse((self.root/'.runtime/evidence/TEST-001/completion.json').exists())
    def test_forged_runtime_state_never_unblocks(self):
        ctl.write_state({'tasks':{'TEST-001':{'status':'DONE'}}},self.root)
        child={'dependencies':['TEST-001']}
        with self.assertRaises((ValueError,OSError)):
            ctl.assert_ready({**self.tasks,'CHILD-001':child},'CHILD-001',ctl.read_state(self.root),root=self.root)
    def test_dirty_source_and_wrong_remote_sha_block_completion(self):
        self.push();file=self.root/'tests/test_candidate.py';file.write_text('changed',encoding='utf-8')
        with self.assertRaises(ValueError):ctl.complete(self.tasks,'TEST-001',self.root)
        file.write_text('def test_candidate():\n    assert True\n',encoding='utf-8')
        self.git('add','tests/test_candidate.py');self.git('commit','-m','test: second fixture [TEST-001]')
        with self.assertRaisesRegex(ValueError,'Remote SHA'):ctl.complete(self.tasks,'TEST-001',self.root)
    def test_report_or_log_tampering_blocks_dependency(self):
        self.push();proof=ctl.complete(self.tasks,'TEST-001',self.root)
        path=self.root/proof['report'];original=path.read_bytes()
        path.write_text('{}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'report changed'):ctl.verify_completion(self.tasks,'TEST-001',self.root)
        path.write_bytes(original);report=json.loads(original)
        (self.root/report['log_path']).write_text('changed',encoding='utf-8')
        with self.assertRaises(ValueError):ctl.verify_completion(self.tasks,'TEST-001',self.root)
    def test_branch_scope_and_task_message_are_required(self):
        self.push();self.git('switch','-c','main')
        with self.assertRaisesRegex(ValueError,'feature/'):ctl.complete(self.tasks,'TEST-001',self.root)
        self.git('switch','feature/fixture')
        (self.root/'unrelated.txt').write_text('unrelated',encoding='utf-8')
        self.git('add','unrelated.txt');self.git('commit','-m','test: unrelated [TEST-001]');self.push()
        with self.assertRaisesRegex(ValueError,'scope'):ctl.complete(self.tasks,'TEST-001',self.root)
    def test_unrelated_untracked_work_is_preserved(self):
        file=self.root/'owner-notes.txt';file.write_text('keep',encoding='utf-8')
        self.push();ctl.complete(self.tasks,'TEST-001',self.root)
        self.assertEqual('keep',file.read_text())
        self.assertIn('?? owner-notes.txt',self.git('status','--short'))
    def test_safe_paths_exclude_data_and_credentials(self):
        self.assertEqual([],check_safe_paths(['src/recommender/data/loader.py','tests/data/test_fixture.py']))
        for path in ('data/ratings.csv','dataset_linkage_work/raw/x','.env','.runtime/x','reviewer.key','model.pt'):
            self.assertEqual([path],check_safe_paths([path]))

if __name__=='__main__':unittest.main()
