"""Dependency-free local server. All coordination side effects are simulated."""
import argparse
import csv
import io
import json
import os
import sqlite3
import threading
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import cached_property
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .engine import CARES, RIDES, DEFAULT_CASE, solve, assess_policy
from .simulator import simulate, DEFAULT_CONFIG
from .predictive import load_model, train, save_model, predict, TRAINING_LOCK

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / 'static'
INITIAL_POLICY = dict(version=1, arrival_buffer_minutes=0)
# Explicit because Python's mimetypes reads the Windows registry, which can map
# .js to text/plain; with nosniff the browser would then refuse to run the app.
ASSETS = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
    '/style.css': ('style.css', 'text/css; charset=utf-8'),
    '/favicon.svg': ('favicon.svg', 'image/svg+xml'),
    '/public-sans.woff2': ('public-sans.woff2', 'font/woff2'),
}


def fold(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c)).casefold()


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, at TEXT, kind TEXT, plan_id TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, payload TEXT);
            ''')
            db.execute("INSERT OR IGNORE INTO settings VALUES ('policy',?)", (json.dumps(INITIAL_POLICY),))

    def reset(self):
        with self.lock, self.connect() as db:
            db.execute('DELETE FROM plans')
            db.execute('DELETE FROM events')
            db.execute("DELETE FROM settings WHERE key<>'policy'")
            db.execute("UPDATE settings SET payload=? WHERE key='policy'", (json.dumps(INITIAL_POLICY),))

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path, timeout=20)
        try:
            with db:
                yield db
        finally:
            db.close()

    def event(self, db, kind, plan_id, payload):
        db.execute('INSERT INTO events(at,kind,plan_id,payload) VALUES (?,?,?,?)', (now(),kind,plan_id,json.dumps(payload)))

    def policy(self):
        with self.connect() as db:
            return json.loads(db.execute("SELECT payload FROM settings WHERE key='policy'").fetchone()[0])

    def save(self, db, plan):
        db.execute('INSERT OR REPLACE INTO plans VALUES (?,?)', (plan['id'], json.dumps(plan)))

    def get(self, plan_id):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM plans WHERE id=?', (plan_id,)).fetchone()
        if not row:
            raise LookupError('Plan not found.')
        return json.loads(row[0])

    def prepare(self, case, excluded=None, parent_id=None):
        with self.lock:
            plan = solve(case, self.policy(), excluded)
            plan.update(id=uuid.uuid4().hex, created_at=now(), status='prepared' if plan['feasible'] else 'blocked', parent_id=parent_id)
            plan['steps'] = [
                dict(label='Check job schedule and applicant constraints', state='verified'),
                dict(label='Find compatible childcare and transport offers', state='verified' if plan['feasible'] else 'blocked'),
                dict(label='Check deposit against demo bridge budget', state='verified' if plan['feasible'] else 'blocked'),
                dict(label='Request applicant consent', state='pending' if plan['feasible'] else 'blocked'),
                dict(label='Confirm the simulated arrangement', state='pending' if plan['feasible'] else 'blocked'),
            ]
            with self.connect() as db:
                self.save(db, plan)
                self.event(db, 'plan_prepared', plan['id'], dict(feasible=plan['feasible'],parent_id=parent_id))
            return plan

    def confirm(self, plan_id, consent):
        if consent is not True:
            raise ValueError('Explicit consent is required for simulated confirmation.')
        with self.lock:
            plan = self.get(plan_id)
            if plan['status'] == 'committed':
                return plan
            if plan['status'] != 'prepared':
                raise ValueError('Only a prepared, feasible plan can be confirmed.')
            plan['status'] = 'committed'
            for s in plan['steps']:
                s['state'] = 'verified'
            with self.connect() as db:
                self.save(db, plan)
                self.event(db, 'simulation_committed', plan_id, dict(consent=True, real_world_actions=False))
            return plan

    def outcome(self, plan_id, kind, delay=15):
        if kind not in ['transport_delay','provider_withdrawal','on_time']:
            raise ValueError('Unknown outcome.')
        if type(delay) is not int or not 1 <= delay <= 60:
            raise ValueError('Delay must be a whole number from 1 to 60 minutes.')
        with self.lock:
            plan = self.get(plan_id)
            if plan['status'] != 'committed':
                raise ValueError('Record outcomes only after simulated confirmation.')
            plan['status'] = 'completed' if kind=='on_time' else 'failed'
            plan['outcome'] = kind
            with self.connect() as db:
                self.save(db,plan)
                self.event(db, kind, plan_id, dict(delay_minutes=delay) if kind=='transport_delay' else {})
            if kind=='provider_withdrawal':
                excluded = plan['excluded'] + [plan['selected']['care']['id']]
                return dict(plan=plan, replacement=self.prepare(plan['case'], excluded, plan_id))
            return dict(plan=plan)

    def learning(self, run=False):
        with self.lock:
            policy = self.policy()
            with self.connect() as db:
                delays = [json.loads(r[0])['delay_minutes'] for r in db.execute("SELECT payload FROM events WHERE kind='transport_delay'")]
                if not run:
                    latest=db.execute("SELECT payload FROM events WHERE kind='policy_evaluated' ORDER BY id DESC LIMIT 1").fetchone()
                    return dict(policy=policy, observed_delays=delays, latest=json.loads(latest[0]) if latest else None)
                result=assess_policy(policy,delays)
                result['small_suite_passed']=result['promoted']
                if result['promoted']:
                    broader=simulate(dict(cases=500,seed=314159,baseline_buffer=policy['arrival_buffer_minutes'],
                                          candidate_buffer=result['proposed_policy']['arrival_buffer_minutes']))
                    result['broader_check']={k:broader[k] for k in ['config','baseline','candidate','paired','on_time_rate_difference']}
                    result['promoted']=(broader['candidate']['on_time']>=broader['baseline']['on_time']
                                        and broader['candidate']['late']<=broader['baseline']['late'])
                    result['reason']=('Passed both the fixed stress suite and the broader paired simulation.' if result['promoted']
                                      else 'The small suite passed, but the broader simulation showed fewer on-time starts or more late arrivals. Current policy retained.')
                    result['scope']='Five fixed stress cases plus 500 paired synthetic households. Neither establishes real-world impact.'
                if result['promoted']:
                    db.execute("UPDATE settings SET payload=? WHERE key='policy'",(json.dumps(result['proposed_policy']),))
                self.event(db,'policy_evaluated',None,result)
                return dict(policy=result['proposed_policy'] if result['promoted'] else policy, result=result)

    def events(self):
        with self.connect() as db:
            return [dict(id=r[0],at=r[1],kind=r[2],plan_id=r[3],payload=json.loads(r[4])) for r in
                    db.execute('SELECT id,at,kind,plan_id,payload FROM events ORDER BY id DESC LIMIT 50')]

    def setting(self,key):
        with self.connect() as db:
            row=db.execute('SELECT payload FROM settings WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None

    def record_setting(self,key,payload,kind):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(key,json.dumps(payload)))
            self.event(db,kind,None,dict(synthetic=True))


class Research:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('FIRSTSTEP_RESEARCH_DB', ROOT/'data'/'research.sqlite'))
        # The surrounding workspace already contains the full research database.
        if not self.path.exists() and not path and not os.environ.get('FIRSTSTEP_RESEARCH_DB'):
            sibling=ROOT.parent/'firststep_research.sqlite'
            if sibling.exists():
                self.path=sibling

    @contextmanager
    def connection(self):
        db=sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro', uri=True)
        try:
            yield db
        finally:
            db.close()

    def areas(self, q='', level='county', limit=30):
        if level not in ['county','tract','block_group']:
            raise ValueError('Unknown geographic level.')
        code={'county':'050','tract':'140','block_group':'150'}[level]
        q=' '.join(q.split())[:100]
        if self.path.exists():
            pattern='%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
            if q.isascii():
                # Plain LIKE covers ASCII names, so the slower fold() runs only on accented ones.
                where="(name LIKE ? ESCAPE '\\' OR (name GLOB '*[^ -~]*' AND fold(name) LIKE ? ESCAPE '\\'))"
                args=(code,pattern,fold(pattern),limit)
            else:
                where="fold(name) LIKE ? ESCAPE '\\'"
                args=(code,fold(pattern),limit)
            with self.connection() as db:
                db.row_factory=sqlite3.Row
                db.create_function('fold',1,fold,deterministic=True)
                rows=db.execute(f'SELECT * FROM area_profile WHERE summary_level=? AND {where} ORDER BY name LIMIT ?',args).fetchall()
                result=[dict(r) for r in rows]
            return dict(rows=result, full_database=True, period='2020-2024 ACS five-year estimates')
        needle=fold(q)
        rows=[row for key,row in self.counties if needle in key] if level=='county' else []
        return dict(rows=rows[:limit],full_database=False,period='2020-2024 ACS five-year estimates')

    @cached_property
    def counties(self):
        text=['geo_id','name','summary_level','state_fips','county_fips','tract_code','block_group']
        with (ROOT/'data'/'county_profiles.csv').open(encoding='utf-8-sig',newline='') as f:
            rows=[{k:v if k in text else int(v) if v else None for k,v in row.items()} for row in csv.DictReader(f)]
        return [(fold(r['name']),r) for r in sorted(rows,key=lambda r:r['name'])]

    @cached_property
    def licensed_centers(self):
        with (ROOT/'data'/'ca_childcare_centers.csv').open(encoding='utf-8-sig',newline='') as f:
            return [(fold(' '.join([r['county_name'],r['facility_city'],r['facility_name']])),r)
                    for r in csv.DictReader(f) if r['facility_status']=='LICENSED']

    def providers(self,q='San Francisco'):
        needle=fold(' '.join(q.split()))
        rows=[r for key,r in self.licensed_centers if needle in key]
        return dict(rows=rows[:50],matches=len(rows),file_date='2025-05-25',live_availability=False)

    def stats(self):
        m=json.loads((ROOT/'data'/'manifest.json').read_text())
        return dict(total_source_rows=m['total_source_data_rows'],geographies=m['counts']['geography'],
                    county_records=3222,provider_records=m['counts']['ca_childcare_centers'],
                    full_database=self.path.exists(),period=m['acs_period'])


def make_handler(store,research):
    model_path=store.path.parent/'model.json'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,fmt,*args):
            # Do not log query strings or applicant payloads.
            pass

        def send(self,status,data,content_type='application/json; charset=utf-8'):
            body=json.dumps(data).encode() if not isinstance(data,bytes) else data
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            try:
                if self.headers.get('Host') not in [f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}']:
                    return self.send(403,dict(error='Only loopback hostnames are accepted.'))
                u=urlparse(self.path)
                query=parse_qs(u.query)
                if u.path=='/api/bootstrap':
                    return self.send(200,dict(default_case=DEFAULT_CASE,cares=CARES,rides=RIDES,
                                              stats=research.stats(),learning=store.learning(),events=store.events()))
                if u.path=='/api/research/areas':
                    return self.send(200,research.areas(query.get('q',[''])[0],query.get('level',['county'])[0]))
                if u.path=='/api/research/providers':
                    return self.send(200,research.providers(query.get('q',['San Francisco'])[0]))
                if u.path=='/api/learning':
                    return self.send(200,store.learning())
                if u.path=='/api/events':
                    return self.send(200,store.events())
                if u.path=='/api/model':
                    return self.send(200,dict(model=load_model(model_path),local=True))
                if u.path=='/api/simulator':
                    return self.send(200,dict(defaults=DEFAULT_CONFIG,latest=store.setting('simulation')))
                if u.path.startswith('/api/plans/'):
                    parts=u.path.split('/')
                    if len(parts)!=4:
                        return self.send(404,dict(error='Not found.'))
                    return self.send(200,store.get(parts[3]))
                if u.path not in ASSETS:
                    return self.send(404,dict(error='Not found.'))
                name,content_type=ASSETS[u.path]
                return self.send(200,(STATIC/name).read_bytes(),content_type)
            except (ValueError,LookupError) as exc:
                return self.send(400 if isinstance(exc,ValueError) else 404,dict(error=str(exc)))
            except Exception:
                return self.send(500,dict(error='The request could not be completed. Check local data files.'))

        def do_POST(self):
            try:
                if self.headers.get('Host') not in [f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}']:
                    return self.send(403,dict(error='Only loopback hostnames are accepted.'))
                origin=self.headers.get('Origin')
                if origin and origin not in ['http://'+self.headers.get('Host','')]:
                    return self.send(403,dict(error='Cross-origin changes are not allowed.'))
                if self.headers.get('Content-Type','').split(';')[0]!='application/json':
                    return self.send(415,dict(error='Use application/json.'))
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=65536:
                    return self.send(413,dict(error='Request body must be between 1 and 65536 bytes.'))
                body=json.loads(self.rfile.read(n))
                if not isinstance(body,dict):
                    raise ValueError('Request body must be an object.')
                path=urlparse(self.path).path
                if path=='/api/plans':
                    return self.send(201,store.prepare(body))
                if path=='/api/learning/run':
                    return self.send(200,store.learning(run=True))
                if path=='/api/simulator/run':
                    result=simulate(body)
                    model=load_model(model_path)
                    for sample in result['samples']:
                        for name in ['baseline','candidate']:
                            plan=solve(sample['case'],dict(version=1,arrival_buffer_minutes=result['config'][name+'_buffer']))
                            sample[name]['prediction']=predict(plan,result['config'],model)['probability']
                    store.record_setting('simulation',result,'batch_simulated')
                    return self.send(200,result)
                if path=='/api/model/train':
                    if set(body)-{'train_count','test_count','seed'}:
                        raise ValueError('Unknown training setting.')
                    if not TRAINING_LOCK.acquire(blocking=False):
                        return self.send(409,dict(error='Another local training run is already in progress.'))
                    try:
                        model=train(body.get('train_count',4000),body.get('test_count',1000),body.get('seed',20261122))
                        save_model(model,model_path)
                        store.record_setting('model_training',dict(training=model['training'],evaluation=model['evaluation']),'model_trained')
                    finally:
                        TRAINING_LOCK.release()
                    return self.send(200,dict(model=model,local=True))
                if path=='/api/model/predict':
                    if set(body)-{'case','context'}:
                        raise ValueError('Unknown prediction setting.')
                    plan=solve(body.get('case',DEFAULT_CASE),store.policy())
                    return self.send(200,dict(prediction=predict(plan,body.get('context'),load_model(model_path)),plan=plan))
                parts=path.strip('/').split('/')
                if len(parts)==4 and parts[:2]==['api','plans']:
                    if parts[3]=='confirm':
                        return self.send(200,store.confirm(parts[2],body.get('consent')))
                    if parts[3]=='outcome':
                        return self.send(200,store.outcome(parts[2],body.get('kind'),body.get('delay_minutes',15)))
                return self.send(404,dict(error='Not found.'))
            except (ValueError,LookupError) as exc:
                return self.send(400 if isinstance(exc,ValueError) else 404,dict(error=str(exc)))
            except Exception:
                return self.send(500,dict(error='The change could not be completed.'))
    return Handler


def main():
    p=argparse.ArgumentParser(description='Run the FirstStep local coordination demo')
    p.add_argument('--port',type=int,default=8080)
    p.add_argument('--reset-demo',action='store_true',help='Clear saved demo plans, events, and the learned policy before starting')
    args=p.parse_args()
    if not (STATIC/'index.html').exists():
        raise SystemExit('FirstStep runs from a source checkout. Install it with: pip install -e .')
    store=Store(ROOT/'data'/'state.sqlite')
    if args.reset_demo:
        store.reset()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),make_handler(store,Research()))
    print(f'FirstStep: http://127.0.0.1:{args.port}',flush=True)
    print('Local simulation only. No live provider bookings or funding transactions.',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    main()
