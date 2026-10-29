import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from github_ci import verify_checks
from git_preflight import check_allowed_paths

SHA='a'*40

def mk(name='test',sha=SHA,status='completed',conclusion='success',id=1):
    return {'name':name,'head_sha':sha,'status':status,'conclusion':conclusion,'id':id,'started_at':'2026-10-28T12:00:00Z'}

class CiReaderTests(unittest.TestCase):
    def test_required_check_passes_at_same_sha(self):
        self.assertEqual([],verify_checks([mk()],SHA,['test']))
    def test_fails_if_sha_is_wrong(self):
        self.assertTrue(verify_checks([mk(sha='b'*40)],SHA,['test']))
    def test_fails_if_pending(self):
        self.assertTrue(verify_checks([mk(status='in_progress',conclusion=None)],SHA,['test']))
    def test_fails_if_check_missing(self):
        self.assertTrue(verify_checks([mk()],SHA,['production-ci']))
    def test_path_allowlist(self):
        self.assertEqual(['.agents/policies/quality_gates.yaml'],check_allowed_paths(['src/recommender/a.py','.agents/policies/quality_gates.yaml'],['src/recommender/']))

if __name__=='__main__':unittest.main()
