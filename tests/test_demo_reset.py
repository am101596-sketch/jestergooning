import json
import tempfile
import unittest
from pathlib import Path

from firststep.engine import DEFAULT_CASE
from firststep.server import Store


class DemoResetTests(unittest.TestCase):
    def test_reset_restores_the_documented_first_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(Path(tmp) / 'state.sqlite')
            plan = store.prepare(DEFAULT_CASE)
            store.confirm(plan['id'], True)
            store.outcome(plan['id'], 'transport_delay')
            store.learning(run=True)
            store.record_setting('simulation', dict(cases=10), 'batch_simulated')
            with store.connect() as db:
                db.execute("UPDATE settings SET payload=? WHERE key='policy'",
                           (json.dumps(dict(version=2, arrival_buffer_minutes=15)),))
            self.assertEqual(store.prepare(DEFAULT_CASE)['selected']['weekly'], 285)
            store.reset()
            self.assertEqual(store.policy(), dict(version=1, arrival_buffer_minutes=0))
            self.assertEqual(store.events(), [])
            self.assertEqual(store.learning()['observed_delays'], [])
            self.assertIsNone(store.setting('simulation'))
            with self.assertRaises(LookupError):
                store.get(plan['id'])
            self.assertEqual(store.prepare(DEFAULT_CASE)['selected']['weekly'], 260)


if __name__ == '__main__':
    unittest.main()
