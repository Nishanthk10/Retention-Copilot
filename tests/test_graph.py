import asyncio,json
import httpx
import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.graph.runner import Runtime
from app.providers.router import ProviderRouter
from app.graph.emit import emit
from tests.fakes import FakeProviders

@pytest.mark.asyncio
async def test_commit_cancel_resume(settings,kb,audit):
    async def response(provider,model,body):
        # Summary fixture disabled: only agent (Decision schema) requests get an answer.
        if '"action"' not in json.dumps(body.get('format') or body.get('response_format')): return httpx.Response(500)
        return '{"action":"suggest","text":"Ask what matters most.","type":"rapport","offer_id":null,"rationale":"Clarify needs"}'
    async with AsyncSqliteSaver.from_conn_string(str(settings.data_dir/'checkpoint.db')) as saver:
        settings.features['summariser']=False
        fake=FakeProviders(default=response)
        provider=ProviderRouter(settings,audit,fake.transport)
        rt=Runtime(settings,kb,None,provider,audit,saver)
        cid=rt.create()
        await rt.customer_started(cid)
        await rt.accept(cid,'customer','It is too expensive',1,2)
        await rt.calls[cid]['task']
        rows=audit.read(cid);assert any(r['step']=='turn_committed' for r in rows)
        assert any(r['step']=='emit' for r in rows)
        checkpoint=rt.db.execute('SELECT checkpoint FROM calls WHERE call_id=?',(cid,)).fetchone()[0]
        entered=asyncio.Event()
        async def slow(*_): entered.set();await asyncio.sleep(100)
        fake.default=slow
        await rt.customer_started(cid)
        await rt.accept(cid,'customer','Please tell me more',3,4)
        await entered.wait();await rt.customer_started(cid)
        assert checkpoint==rt.db.execute('SELECT checkpoint FROM calls WHERE call_id=?',(cid,)).fetchone()[0]
        stale={'call_id':cid,'turn_no':1,'generation':0}
        assert not await emit(rt,stale,{'suggestion':{},'record':None})
        await rt.close()
        other=Runtime(settings,kb,None,ProviderRouter(settings,audit,FakeProviders(default=response).transport),audit,saver)
        await other.restore()
        assert cid in other.calls and other.calls[cid]['turns'][-1]['turn_no']==1
        assert other.calls[cid]['next_turn']>2
        assert any(r['step']=='resume' for r in audit.read(cid))
        await other.end(cid);await other.close()

@pytest.mark.asyncio
async def test_pii_absent_from_prompts_logs_and_checkpoints(settings,kb,audit):
    captured=[]
    async def response(provider,model,body):
        captured.extend(body['messages'])
        return '{"action":"nothing"}'
    settings.features['summariser']=False
    async with AsyncSqliteSaver.from_conn_string(str(settings.data_dir/'checkpoints.db')) as saver:
        rt=Runtime(settings,kb,None,ProviderRouter(settings,audit,FakeProviders(default=response).transport),audit,saver)
        cid=rt.create();await rt.customer_started(cid)
        raw='My card is 4111 1111 1111 1111 and email me at person@example.com'
        await rt.accept(cid,'customer',raw,1,2);await rt.calls[cid]['task']
        config=json.loads(rt.db.execute('SELECT checkpoint FROM calls WHERE call_id=?',(cid,)).fetchone()[0])
        saved=await rt.checkpoints.aget_state(config)
        downstream=json.dumps([captured,audit.read(cid),saved.values])
        assert '4111' not in downstream and 'person@example.com' not in downstream
        assert '[CARD]' in downstream and '[EMAIL]' in downstream
        await rt.end(cid);await rt.close()

@pytest.mark.asyncio
async def test_old_audio_cannot_restart_cancelled_guidance(settings,kb,audit):
    settings.features['summariser']=False
    async with AsyncSqliteSaver.from_conn_string(str(settings.data_dir/'checkpoints.db')) as saver:
        rt=Runtime(settings,kb,None,ProviderRouter(settings,audit),audit,saver)
        cid=rt.create();await rt.customer_started(cid)
        old_generation=rt.calls[cid]['generation']
        await rt.customer_started(cid)
        await rt.accept(cid,'customer','An older buffered sentence.',1,2,generation=old_generation)
        assert rt.calls[cid]['task'] is None
        assert any(r['step']=='turn_superseded' for r in audit.read(cid))
        await rt.end(cid);await rt.close()
