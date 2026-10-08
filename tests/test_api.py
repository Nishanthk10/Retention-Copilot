import time
from fastapi.testclient import TestClient
from app.main import app

def test_api_and_single_call(tmp_path,monkeypatch):
    monkeypatch.setenv('TEST_MODE','true');monkeypatch.setenv('DATA_DIR',str(tmp_path/'data'));monkeypatch.setenv('LOG_DIR',str(tmp_path/'logs'))
    with TestClient(app) as client:
        for _ in range(100):
            if client.get('/health').json()['ready']: break
            time.sleep(.02)
        assert client.get('/health').json()['ready']
        assert client.get('/').status_code==200
        cid=client.post('/calls').json()['call_id']
        assert client.post('/calls').status_code==409
        with client.websocket_connect('/ws/events?call_id='+cid) as ws:
            assert ws.receive_json()['type']=='snapshot'
            assert ws.receive_json()['type']=='heartbeat'
        with client.websocket_connect('/ws/audio?call_id='+cid) as ws:
            ws.send_json({'type':'role','role':'customer'})
            assert ws.receive_json()['role']=='customer'
            ws.send_json({'type':'role','role':'none'})
            assert ws.receive_json()['role']=='none'
        assert client.post('/calls/'+cid+'/end').json()['log_saved']
        assert client.get('/api/logs/'+cid).status_code==200
        assert client.post('/calls',headers={'Origin':'https://wrong.example'}).status_code==403
