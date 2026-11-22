import tempfile
import unittest
from pathlib import Path

from firststep.engine import DEFAULT_CASE, solve, assess_policy, evaluate
from firststep.server import Store, Research, ROOT


class PlannerTests(unittest.TestCase):
    def test_lowest_cost_feasible_plan(self):
        plan=solve(DEFAULT_CASE)
        self.assertTrue(plan['feasible'])
        self.assertEqual(plan['selected']['care']['id'],'garden')
        self.assertEqual(plan['selected']['weekly'],260)
        self.assertFalse(plan['selected']['reasons'])

    def test_budget_blocker_does_not_invent_funding(self):
        plan=solve(dict(DEFAULT_CASE,weekly_budget=100))
        self.assertFalse(plan['feasible'])
        self.assertIsNone(plan['selected'])
        self.assertTrue(any('budget' in reason for r in plan['rejected'] for reason in r['reasons']))

    def test_deposit_budget_and_pickup_are_constraints(self):
        self.assertFalse(solve(dict(DEFAULT_CASE,bridge_budget=0))['feasible'])
        self.assertFalse(solve(dict(DEFAULT_CASE,shift_end='20:00'))['feasible'])

    def test_withdrawn_provider_is_excluded(self):
        plan=solve(DEFAULT_CASE,excluded=['garden'])
        self.assertEqual(plan['selected']['care']['id'],'river')

    def test_age_and_location_require_real_offer(self):
        self.assertFalse(solve(dict(DEFAULT_CASE,child_age=0))['feasible'])
        with self.assertRaises(ValueError):solve(dict(DEFAULT_CASE,county='Oakland'))

    def test_invalid_values_rejected(self):
        for change in [dict(weekly_budget=-1),dict(weekly_budget=True),dict(child_age=3.5),dict(shift_start='25:00'),dict(shift_end='08:00')]:
            with self.subTest(change=change),self.assertRaises(ValueError):solve(dict(DEFAULT_CASE,**change))

    def test_learning_requires_evidence_and_independent_gain(self):
        with self.assertRaises(ValueError):assess_policy(dict(version=1,arrival_buffer_minutes=0),[])
        result=assess_policy(dict(version=1,arrival_buffer_minutes=0),[15])
        self.assertTrue(result['promoted'])
        self.assertEqual(result['baseline']['late'],2)
        self.assertEqual(result['candidate']['late'],0)
        self.assertEqual(result['candidate']['on_time'],3)
        self.assertEqual(result['candidate']['declined'],2)
        self.assertFalse(assess_policy(result['proposed_policy'],[15])['promoted'])

    def test_declining_everything_cannot_win(self):
        result=assess_policy(dict(version=1,arrival_buffer_minutes=0),[60])
        self.assertFalse(result['promoted'])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=Store(Path(self.tmp.name)/'state.sqlite')

    def tearDown(self):self.tmp.cleanup()

    def test_confirm_requires_consent_and_is_idempotent(self):
        p=self.store.prepare(DEFAULT_CASE)
        with self.assertRaises(ValueError):self.store.confirm(p['id'],False)
        self.store.confirm(p['id'],True)
        self.store.confirm(p['id'],True)
        self.assertEqual(sum(e['kind']=='simulation_committed' for e in self.store.events()),1)

    def test_withdrawal_replans_and_requires_new_consent(self):
        p=self.store.prepare(DEFAULT_CASE)
        self.store.confirm(p['id'],True)
        result=self.store.outcome(p['id'],'provider_withdrawal')
        replacement=result['replacement']
        self.assertEqual(replacement['status'],'prepared')
        self.assertEqual(replacement['selected']['care']['id'],'river')
        self.assertEqual(replacement['parent_id'],p['id'])
        with self.assertRaises(ValueError):self.store.outcome(p['id'],'on_time')

    def test_policy_survives_restart_and_changes_new_plans(self):
        p=self.store.prepare(DEFAULT_CASE)
        with self.assertRaises(ValueError):self.store.outcome(p['id'],'transport_delay')
        self.store.confirm(p['id'],True)
        self.store.outcome(p['id'],'transport_delay')
        self.assertTrue(self.store.learning(run=True)['result']['promoted'])
        restart=Store(self.store.path)
        self.assertEqual(restart.policy()['arrival_buffer_minutes'],15)
        self.assertEqual(restart.prepare(DEFAULT_CASE)['selected']['ride']['id'],'flex')


class ResearchTests(unittest.TestCase):
    def test_county_fallback_contains_real_source_records(self):
        r=Research(path=ROOT/'data'/'nonexistent.sqlite')
        found=r.areas('San Francisco')
        self.assertFalse(found['full_database'])
        self.assertEqual(len(found['rows']),1)
        self.assertEqual(found['rows'][0]['geo_id'],'0500000US06075')
        self.assertGreater(found['rows'][0]['population_estimate'],700000)
        self.assertEqual(r.areas('San Francisco','block_group')['rows'],[])

    def test_provider_results_are_historical_licensed_only(self):
        r=Research(path=ROOT/'data'/'nonexistent.sqlite').providers('San Francisco')
        self.assertGreater(r['matches'],0)
        self.assertTrue(all(p['facility_status']=='LICENSED' for p in r['rows']))
        self.assertFalse(r['live_availability'])


if __name__=='__main__':unittest.main()
