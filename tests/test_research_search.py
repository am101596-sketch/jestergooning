import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from firststep.server import ROOT, Research


def bundled():
    return Research(path=ROOT / 'data' / 'missing.sqlite')


class BundledSearchTests(unittest.TestCase):
    def test_surrounding_and_repeated_spaces_are_ignored(self):
        self.assertEqual(len(bundled().areas('  San   Francisco ')['rows']), 1)
        research = bundled()
        self.assertEqual(research.providers(' San  Francisco ')['matches'], research.providers('San Francisco')['matches'])

    def test_accents_are_optional(self):
        rows = bundled().areas('Anasco')['rows']
        self.assertEqual([r['geo_id'] for r in rows], ['0500000US72011'])

    def test_csv_is_parsed_once(self):
        research = bundled()
        research.providers('Oakland')
        research.areas('Alameda')
        with mock.patch('csv.DictReader', side_effect=AssertionError('CSV parsed again')):
            research.providers('Berkeley')
            research.areas('Marin')


class DatabaseSearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        path = Path(self.tmp.name) / 'research.sqlite'
        db = sqlite3.connect(path)
        db.execute('CREATE TABLE area_profile(geo_id TEXT, name TEXT, summary_level TEXT)')
        db.executemany('INSERT INTO area_profile VALUES (?,?,?)', [
            ('1', 'Añasco Municipio, Puerto Rico', '050'),
            ('2', 'Alameda County, California', '050'),
            ('3', '100% Test County', '050'),
            ('4', 'Doña Ana County, New Mexico', '050'),
            ('5', 'McDonald County, Missouri', '050'),
        ])
        db.commit()
        db.close()
        self.research = Research(path)

    def tearDown(self):
        self.tmp.cleanup()

    def names(self, query):
        return [r['name'] for r in self.research.areas(query)['rows']]

    def test_like_wildcards_are_literal(self):
        self.assertEqual(self.names('%'), ['100% Test County'])
        self.assertEqual(self.names('_'), [])

    def test_accented_names_appear_beside_plain_matches(self):
        self.assertEqual(self.names('dona'), ['Doña Ana County, New Mexico', 'McDonald County, Missouri'])

    def test_accent_fallback_and_trim(self):
        self.assertEqual(self.names('  anasco '), ['Añasco Municipio, Puerto Rico'])
        self.assertEqual(self.names('Añasco'), ['Añasco Municipio, Puerto Rico'])


if __name__ == '__main__':
    unittest.main()
