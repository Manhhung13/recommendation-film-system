import sys
from pathlib import Path
import tempfile
import unittest
import copy
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from agentctl import load_tasks, validate_tasks, eligible_tasks, local_tests_for_task


class AgentContractsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = load_tasks()

    def test_all_contracts_are_valid(self):
        self.assertEqual([], validate_tasks(self.tasks))

    def test_initial_eligible_task_is_integration_only(self):
        state={'version':1,'tasks':{}}
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(['SDLC-INTEGRATION-001'],eligible_tasks(self.tasks,state,root=Path(folder)))

    def test_forged_done_or_legacy_verified_does_not_unblock(self):
        for value in ('DONE','VERIFIED'):
            state={'tasks':{'SETUP-001':{'status':value}}}
            with tempfile.TemporaryDirectory() as folder:
                self.assertNotIn('DATA-001',eligible_tasks(self.tasks,state,root=Path(folder)))

    def test_unapproved_business_decision_blocks_task(self):
        with patch('agentctl.verify_completion'):
            self.assertNotIn('D-08', set())
            from agentctl import assert_ready
            with self.assertRaisesRegex(ValueError,'business decisions'):
                assert_ready(self.tasks,'DATA-004',{},approvals=set())
            assert_ready(self.tasks,'DATA-004',{},approvals={'D-08'})

    def test_cycle_is_detected(self):
        tasks=copy.deepcopy(self.tasks)
        tasks['SETUP-001']['dependencies']=['DATA-001']
        self.assertTrue(any('Cycle' in e for e in validate_tasks(tasks)))

    def test_missing_product_tests_do_not_silently_pass(self):
        task=self.tasks['HYBRID-001']
        with self.assertRaises(FileNotFoundError):
            local_tests_for_task(task)


if __name__=='__main__':
    unittest.main()
