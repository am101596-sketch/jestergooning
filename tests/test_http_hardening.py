import json
import mimetypes
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from firststep.engine import DEFAULT_CASE
from firststep.server import ROOT, Research, Store, make_handler


class HardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.store = Store(Path(cls.tmp.name) / 'state.sqlite')
        cls.http = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(cls.store, Research(ROOT / 'data' / 'missing.sqlite')))
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        cls.tmp.cleanup()

    def test_assets_ignore_a_bad_windows_mime_registry(self):
        expected = {'/app.js': 'text/javascript', '/style.css': 'text/css', '/': 'text/html', '/favicon.svg': 'image/svg+xml'}
        with mock.patch.object(mimetypes, 'guess_type', return_value=('text/plain', None)):
            for path, kind in expected.items():
                with self.subTest(path=path), urlopen(self.base + path) as response:
                    self.assertEqual(response.headers['Content-Type'].split(';')[0], kind)

    def test_plan_route_rejects_extra_segments(self):
        plan = self.store.prepare(DEFAULT_CASE)
        with self.assertRaises(HTTPError) as caught:
            urlopen(f"{self.base}/api/plans/extra/{plan['id']}")
        self.assertEqual(caught.exception.code, 404)
        caught.exception.close()

    def test_csp_restricts_form_targets(self):
        with urlopen(self.base) as response:
            self.assertIn("form-action 'self'", response.headers['Content-Security-Policy'])

    def test_malformed_json_is_a_client_error(self):
        request = Request(self.base + '/api/plans', data=b'{bad', headers={'Content-Type': 'application/json'})
        with self.assertRaises(HTTPError) as caught:
            urlopen(request)
        self.assertEqual(caught.exception.code, 400)
        self.assertIn('error', json.loads(caught.exception.read()))
        caught.exception.close()


if __name__ == '__main__':
    unittest.main()
