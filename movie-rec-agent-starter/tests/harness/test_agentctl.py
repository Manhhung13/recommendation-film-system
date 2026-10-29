import sys
from pathlib import Path
import tempfile
import unittest
import copy

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
        self.assertEqual(['SDLC-INTEGRATION-001'],eligible_tasks(self.tasks,state))

    def test_dependency_is_blocked_until_verified(self):
        self.assertNotIn('DATA-001',eligible_tasks(self.tasks,{'tasks':{}}))
        self.assertIn('DATA-001',eligible_tasks(self.tasks,{'tasks':{'SETUP-001':{'status':'VERIFIED'}}}))

    def test_unapproved_business_decision_blocks_task(self):
        state={'tasks':{'SETUP-001':{'status':'VERIFIED'},'DATA-001':{'status':'VERIFIED'},'DATA-002':{'status':'VERIFIED'}}}
        self.assertNotIn('DATA-004',eligible_tasks(self.tasks,state))
        self.assertIn('DATA-004',eligible_tasks(self.tasks,state,{'D-08'}))

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
