import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from firststep.server import Store,Research,ROOT,make_handler
from firststep.engine import DEFAULT_CASE


class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.http=ThreadingHTTPServer(('127.0.0.1',0),make_handler(Store(Path(cls.tmp.name)/'state.sqlite'),Research(ROOT/'data'/'missing.sqlite')))
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join();cls.tmp.cleanup()

    def call(self,path,body=None,headers=None):
        req=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,
                    headers=headers or ({'Content-Type':'application/json'} if body is not None else {}))
        try:
            with urlopen(req) as r:return r.status,json.loads(r.read())
        except HTTPError as e:return e.code,json.loads(e.read())

    def test_end_to_end(self):
        code,p=self.call('/api/plans',DEFAULT_CASE)
        self.assertEqual(code,201)
        self.assertEqual(self.call('/api/plans/'+p['id']+'/confirm',{'consent':False})[0],400)
        self.assertEqual(self.call('/api/plans/'+p['id']+'/confirm',{'consent':True})[0],200)
        self.assertEqual(self.call('/api/plans/'+p['id']+'/outcome',{'kind':'transport_delay'})[0],200)
        code,learning=self.call('/api/learning/run',{})
        self.assertEqual(code,200)
        self.assertFalse(learning['result']['promoted'])
        self.assertIn('broader_check',learning['result'])

    def test_research_and_security(self):
        self.assertEqual(self.call('/api/research/areas?q=San%20Francisco')[0],200)
        self.assertEqual(self.call('/api/research/areas?level=bad')[0],400)
        self.assertEqual(self.call('/api/plans/no-such-plan')[0],404)
        self.assertEqual(self.call('/api/plans',DEFAULT_CASE,{'Content-Type':'application/json','Origin':'https://example.com'})[0],403)
        self.assertEqual(self.call('/api/plans',[],{'Content-Type':'application/json'})[0],400)
        self.assertEqual(self.call('/api/plans',{}, {'Content-Type':'text/plain'})[0],415)

    def test_static_page(self):
        with urlopen(self.base) as r:
            self.assertEqual(r.status,200)
            self.assertIn(b'Coordination studio',r.read())
            self.assertIn("frame-ancestors 'none'",r.headers['Content-Security-Policy'])

    def test_local_model_and_paired_simulator(self):
        code,model=self.call('/api/model')
        self.assertEqual(code,200)
        self.assertTrue(model['model']['synthetic_only'])
        code,result=self.call('/api/simulator/run',{'cases':10,'baseline_buffer':15,'candidate_buffer':15})
        self.assertEqual(code,200)
        self.assertEqual(result['baseline'],result['candidate'])
        self.assertEqual(self.call('/api/simulator')[1]['latest']['config']['cases'],10)
        self.assertEqual(self.call('/api/simulator/run',{'cases':100000})[0],400)
        code,result=self.call('/api/model/predict',{'case':DEFAULT_CASE})
        self.assertEqual(code,200)
        self.assertTrue(0<result['prediction']['probability']<1)
        self.assertEqual(self.call('/api/model/train',{'train_count':1})[0],400)
        code,trained=self.call('/api/model/train',{'train_count':200,'test_count':100,'seed':555})
        self.assertEqual(code,200)
        self.assertEqual(trained['model']['training']['train_rows'],200)


if __name__=='__main__':unittest.main()
