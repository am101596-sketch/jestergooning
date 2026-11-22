import math
import tempfile
import unittest
from pathlib import Path

from firststep.engine import DEFAULT_CASE,solve
from firststep.simulator import config,simulate,labeled_rows,OUTCOMES
from firststep.predictive import features,train,metrics,predict,save_model,load_model


class SimulatorTests(unittest.TestCase):
    def test_seed_reproduces_all_results(self):
        self.assertEqual(simulate({'cases':40,'seed':5}),simulate({'cases':40,'seed':5}))

    def test_identical_policies_share_identical_shocks(self):
        r=simulate({'cases':100,'baseline_buffer':15,'candidate_buffer':15})
        self.assertEqual(r['baseline'],r['candidate'])
        self.assertEqual(r['paired'],dict(improved=0,worsened=0,unchanged=100))
        self.assertEqual(r['paired_95pct_interval'],[0,0])

    def test_zero_disruptions_complete_every_feasible_plan(self):
        r=simulate({'cases':100,'delay_probability':0,'withdrawal_probability':0,'funding_failure_probability':0})
        for name in ['baseline','candidate']:
            self.assertEqual(r[name]['on_time'],r[name]['feasible'])
            self.assertEqual(sum(r[name][k] for k in OUTCOMES),100)

    def test_withdrawal_and_funding_failures_are_real_outcomes(self):
        for setting,label in [('withdrawal_probability','provider_withdrawal'),('funding_failure_probability','funding_failure')]:
            c=dict(cases=100,delay_probability=0,withdrawal_probability=0,funding_failure_probability=0)
            c[setting]=1
            r=simulate(c)
            for name in ['baseline','candidate']:
                self.assertEqual(r[name][label],r[name]['feasible'])

    def test_invalid_or_unbounded_requests_are_rejected(self):
        for c in [{'cases':True},{'cases':5001},{'delay_probability':float('nan')},{'seed':-1},{'candidate_buffer':61},{'bad':1}]:
            with self.subTest(c=c),self.assertRaises(ValueError):config(c)

    def test_decline_all_is_reported_not_counted_as_success(self):
        r=simulate({'cases':20,'baseline_buffer':60,'candidate_buffer':60})
        self.assertEqual(r['baseline']['declined'],20)
        self.assertEqual(r['baseline']['on_time_rate'],0)
        self.assertIsNone(r['baseline']['mean_feasible_weekly_cost'])


class PredictiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.model=train(800,300,seed=321,epochs=100)

    def test_known_metrics_and_tied_auc(self):
        perfect=metrics([0,1,0,1],[0,1,0,1])
        constant=metrics([0,1,0,1],[0.5]*4)
        self.assertEqual(perfect['brier'],0)
        self.assertEqual(perfect['auroc'],1)
        self.assertEqual(constant['brier'],0.25)
        self.assertEqual(constant['auroc'],0.5)

    def test_disjoint_synthetic_splits(self):
        a,b=labeled_rows(20,8),labeled_rows(20,9)
        self.assertFalse({r['id'] for r in a}&{r['id'] for r in b})
        self.assertTrue(all(r['plan']['feasible'] for r in a+b))

    def test_model_learns_against_constant_baseline(self):
        self.assertLess(self.model['evaluation']['brier'],self.model['baseline_evaluation']['brier'])
        self.assertGreater(self.model['evaluation']['auroc'],0.5)
        self.assertEqual(self.model['evaluation']['rows'],300)
        self.assertTrue(all(math.isfinite(v) for v in self.model['weights']))

    def test_prediction_persistence_and_refusal_outside_domain(self):
        plan=solve(DEFAULT_CASE)
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'model.json'
            save_model(self.model,p)
            recovered=load_model(p)
            before=predict(plan,model=self.model)
            self.assertEqual(before,predict(plan,model=recovered))
            self.assertGreater(before['probability'],0)
            self.assertLess(before['probability'],1)
        self.assertIsNone(predict(plan,{'delay_probability':1},self.model)['probability'])
        self.assertIsNone(predict(solve(dict(DEFAULT_CASE,shift_start='11:00')),model=self.model)['probability'])
        self.assertIsNone(predict(solve(dict(DEFAULT_CASE,weekly_budget=1)),model=self.model)['probability'])

    def test_training_rejects_bad_sizes(self):
        for args in [(10,100,0),(200,10,0),(200,100,-1)]:
            with self.assertRaises(ValueError):train(*args)


if __name__=='__main__':unittest.main()
