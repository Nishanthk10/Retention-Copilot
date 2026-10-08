"""GET /api/calls and /logs (Task 6.2). Runs the real app on temporary data and log directories."""
import hashlib, json, shutil, sqlite3, time
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4
from fastapi.testclient import TestClient
from app.config import ROOT
from app.main import app

FIXTURES=ROOT/'tests/fixtures'
ENDED,RESUMED,LOG_ONLY,NO_END='11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222','33333333-3333-4333-8333-333333333333','44444444-4444-4444-8444-444444444444'

def seed_db(data,rows):
    data.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(data/'calls.db') as db:
        db.execute('CREATE TABLE IF NOT EXISTS calls(call_id TEXT PRIMARY KEY,status TEXT,checkpoint TEXT,created_at REAL)')
        db.executemany('INSERT INTO calls VALUES(?,?,?,?)',[(r['call_id'],r['status'],r.get('checkpoint'),r['created_at']) for r in rows])
    db.close()

@contextmanager
def server(tmp_path,monkeypatch,seeded=True):
    data,logs=tmp_path/'data',tmp_path/'logs'
    if seeded:
        shutil.copytree(FIXTURES/'logs',logs)
        seed_db(data,json.loads((FIXTURES/'calls.json').read_text()))
    monkeypatch.setenv('TEST_MODE','true');monkeypatch.setenv('DATA_DIR',str(data));monkeypatch.setenv('LOG_DIR',str(logs))
    with TestClient(app) as client:
        for _ in range(200):
            if client.get('/health').json()['ready']: break
            time.sleep(.02)
        yield client,data,logs

def by_id(calls): return {c['call_id']:c for c in calls}

def test_fixture_calls_newest_first(tmp_path,monkeypatch):
    with server(tmp_path,monkeypatch) as (client,_,_):
        calls=client.get('/api/calls').json()
    assert [c['call_id'] for c in calls]==[LOG_ONLY,RESUMED,ENDED,NO_END]
    assert all(set(c)=={'call_id','started_at','ended_at','status','suggestions_shown','mask_deny_count'} for c in calls)
    c=by_id(calls)
    assert (c[ENDED]['status'],c[ENDED]['ended_at'],c[ENDED]['suggestions_shown'],c[ENDED]['mask_deny_count'])==('ended','2026-10-08T09:01:00+00:00',2,2)
    assert c[ENDED]['started_at']==datetime(2026,10,8,9,tzinfo=timezone.utc).isoformat()
    assert (c[RESUMED]['status'],c[RESUMED]['suggestions_shown'],c[RESUMED]['mask_deny_count'])==('ended',1,0)

def test_log_only_call_without_end_is_interrupted(tmp_path,monkeypatch):
    with server(tmp_path,monkeypatch) as (client,_,_):
        call=by_id(client.get('/api/calls').json())[LOG_ONLY]
    # No calls.db row: started_at falls back to the log's call_started record.
    assert (call['status'],call['ended_at'],call['started_at'])==('interrupted',None,'2026-10-08T11:00:00+00:00')

def test_ended_row_without_call_ended_record(tmp_path,monkeypatch):
    with server(tmp_path,monkeypatch) as (client,_,_):
        call=by_id(client.get('/api/calls').json())[NO_END]
    assert (call['status'],call['ended_at'],call['suggestions_shown'])==('ended',None,1)

def test_live_row_that_is_not_the_current_call_is_interrupted(tmp_path,monkeypatch):
    with server(tmp_path,monkeypatch,seeded=False) as (client,data,logs):
        # Simulates a failed restore: added after startup, so the runtime never resumed it.
        cid=str(uuid4())
        seed_db(data,[{'call_id':cid,'status':'live','created_at':time.time()}])
        (logs/f'{cid}.jsonl').write_text(json.dumps({'ts':'2026-10-08T12:00:00+00:00','call_id':cid,'turn_no':0,'step':'call_started'})+'\n')
        assert by_id(client.get('/api/calls').json())[cid]['status']=='interrupted'

def test_current_live_call_is_in_progress(tmp_path,monkeypatch):
    with server(tmp_path,monkeypatch,seeded=False) as (client,_,_):
        cid=client.post('/calls').json()['call_id']
        call=by_id(client.get('/api/calls').json())[cid]
        assert (call['status'],call['ended_at'])==('live',None)
        client.post(f'/calls/{cid}/end')
        call=by_id(client.get('/api/calls').json())[cid]
        assert call['status']=='ended' and call['ended_at']

def test_checkpoint_column_never_returned(tmp_path,monkeypatch):
    checkpoint=json.dumps({'configurable':{'thread_id':ENDED,'checkpoint_ns':'','checkpoint_id':'1ef-checkpoint-pointer'}})
    with server(tmp_path,monkeypatch) as (client,data,_):
        with sqlite3.connect(data/'calls.db') as db: db.execute('UPDATE calls SET checkpoint=? WHERE call_id=?',(checkpoint,ENDED))
        db.close()
        body=client.get('/api/calls').text
    for field in ['checkpoint','thread_id','checkpoint_id','1ef-checkpoint-pointer']: assert field not in body

def test_relative_data_and_log_dirs(tmp_path,monkeypatch):
    # Regression: .env uses DATA_DIR=data / LOG_DIR=logs; a relative calls.db path crashed /api/calls.
    shutil.copytree(FIXTURES/'logs',tmp_path/'logs')
    seed_db(tmp_path/'data',json.loads((FIXTURES/'calls.json').read_text()))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('TEST_MODE','true');monkeypatch.setenv('DATA_DIR','data');monkeypatch.setenv('LOG_DIR','logs')
    with TestClient(app) as client:
        for _ in range(200):
            if client.get('/health').json()['ready']: break
            time.sleep(.02)
        response=client.get('/api/calls')
    assert response.status_code==200 and by_id(response.json())[ENDED]['status']=='ended'

def test_empty_log_directory(tmp_path,monkeypatch):
    with server(tmp_path,monkeypatch,seeded=False) as (client,_,_):
        assert client.get('/api/calls').json()==[]

def test_list_is_read_only(tmp_path,monkeypatch):
    def digest(paths): return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    with server(tmp_path,monkeypatch) as (client,data,logs):
        before=digest(sorted(logs.iterdir())+[data/'calls.db'])
        client.get('/api/calls');client.get('/logs');client.get('/api/logs/'+ENDED)
        assert digest(sorted(logs.iterdir())+[data/'calls.db'])==before

def test_non_call_files_ignored_and_pages_served(tmp_path,monkeypatch):
    with server(tmp_path,monkeypatch) as (client,_,logs):
        (logs/'notes.jsonl').write_text('not a call\n')
        assert len(client.get('/api/calls').json())==4
        for path in ['/logs','/logs/'+ENDED]:
            response=client.get(path)
            assert response.status_code==200 and 'id="list-view"' in response.text
