import unittest

from firststep.engine import assess_policy

START = dict(version=1, arrival_buffer_minutes=0)


class LearningGateTests(unittest.TestCase):
    def test_one_extreme_delay_does_not_block_a_safe_buffer(self):
        result = assess_policy(START, [15, 60])
        self.assertTrue(result['promoted'])
        self.assertEqual(result['proposed_policy']['arrival_buffer_minutes'], 15)

    def test_largest_delay_that_passes_is_adopted(self):
        result = assess_policy(START, [15, 20, 60])
        self.assertTrue(result['promoted'])
        self.assertEqual(result['proposed_policy']['arrival_buffer_minutes'], 20)

    def test_failed_evaluation_reports_largest_candidate(self):
        result = assess_policy(START, [40, 60])
        self.assertFalse(result['promoted'])
        self.assertEqual(result['proposed_policy']['arrival_buffer_minutes'], 60)

    def test_buffer_that_turns_away_more_families_is_rejected(self):
        result = assess_policy(START, [40])
        self.assertEqual(result['candidate']['late'], 0)
        self.assertGreater(result['candidate']['declined'], result['baseline']['declined'])
        self.assertFalse(result['promoted'])

    def test_buffer_never_shrinks(self):
        current = dict(version=2, arrival_buffer_minutes=20)
        result = assess_policy(current, [5, 15])
        self.assertFalse(result['promoted'])
        self.assertEqual(result['proposed_policy']['arrival_buffer_minutes'], 20)


if __name__ == '__main__':
    unittest.main()
