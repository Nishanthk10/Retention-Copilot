import json
from concurrent.futures import ThreadPoolExecutor
import pytest
from app.masking import mask_pii
from app.graph.permission import PermissionLayer
from app.graph.context import assemble_context
from app.graph.agents import SearchArgs
from app.stt.streaming import AudioTurns
from app.stt.turns import close_turn

@pytest.mark.parametrize('value,marker',[
    ('4111 1111 1111 1111','[CARD]'),('four one one one one one one one one one one one one one one one','[CARD]'),
    ('+91 98765 43210','[PHONE]'),('555-123-4567','[PHONE]'),('person@example.com','[EMAIL]')])
def test_masking(value,marker):
    masked,_=mask_pii(value);assert marker in masked;assert value not in masked
def test_tenure_not_masked(): assert mask_pii("I've been here 7 months")[0]=="I've been here 7 months"
def test_audit_redaction_concurrent(cid,audit):
    with ThreadPoolExecutor() as ex:
        list(ex.map(lambda i:audit.write(cid,i,'test',input='test-secret-value gsk_1234567890'),range(30)))
    rows=audit.read(cid)
    assert len(rows)==30 and all(r['call_id']==cid for r in rows)
    assert 'test-secret-value' not in json.dumps(rows) and 'gsk_' not in json.dumps(rows)
def test_context_lag_no_gap():
    turns=[{'turn_no':i} for i in range(1,11)]
    assert len(assemble_context(turns,{'last_summarised_turn':2})['untrusted_turns'])==8
    assert len(assemble_context(turns,{'last_summarised_turn':10})['untrusted_turns'])==3
def candidate(**kw):
    return {'source':'offer','lane':'slow','type':'offer','text':'Give 100% off forever','offer_id':'OFF-PRICE-01',**kw}
def test_canonical_terms_and_tenure(cid,audit,kb):
    pl=PermissionLayer(kb,audit)
    assert pl.check(cid,2,candidate(),[],[])['outcome']=='deny'
    d=pl.check(cid,4,candidate(),[],[{'speaker':'customer','text':'Seven months.'}])
    assert d['outcome']=='allow' and '100%' not in d['suggestion']['text']
    assert d['suggestion']['text']==kb.get('OFF-PRICE-01')['display_text']
def test_unknown_offer_and_missing_id(cid,audit,kb):
    pl=PermissionLayer(kb,audit)
    for oid in ['HACK',None]:
        assert pl.check(cid,2,candidate(offer_id=oid),[],[])['outcome']=='deny'
def test_behaviour_mask(cid,audit,kb):
    d=PermissionLayer(kb,audit).check(cid,2,candidate(source='behaviour',type='calm',offer_id=None,text='Acknowledge their frustration and waive the fee.'),[],[])
    assert d['outcome']=='mask' and d['suggestion']['text']=='Acknowledge their frustration'
def test_permission_fail_closed(cid,audit,kb,monkeypatch):
    def fail(_): raise RuntimeError()
    monkeypatch.setattr(kb,'get',fail)
    d=PermissionLayer(kb,audit).check(cid,2,candidate(),[],[])
    assert d['error'] and d['suggestion'] is None
def test_duplicate(cid,audit,kb):
    d=PermissionLayer(kb,audit).check(cid,2,candidate(offer_id='OFF-MOVE-01'),[{'text':kb.get('OFF-MOVE-01')['display_text']}],[])
    assert d['outcome']=='deny'
def test_tool_schema():
    with pytest.raises(Exception): SearchArgs(query='x',k=100)
    with pytest.raises(Exception): SearchArgs(query='x',sql='DROP')
@pytest.mark.asyncio
async def test_role_flush_and_mask(cid,audit):
    class STT:
        async def transcribe(self,_): return 'My card is 4111 1111 1111 1111'
    turns=[]; starts=[]
    async def accept(role,text,start,end):
        turns.append(close_turn(cid,len(turns)+1,role,text,start,end,audit).as_dict())
    async def began(): starts.append(True)
    audio=AudioTurns(STT(),accept,began)
    await audio.feed(b'\0'*3200)
    assert not audio.buffer
    await audio.switch('rep');await audio.feed(b'\0'*3200);await audio.switch('customer')
    await audio.feed(b'\0'*3200);await audio.switch('none')
    assert [t['speaker'] for t in turns]==['rep','customer']
    assert starts and '[CARD]' in turns[0]['text']
    assert '4111' not in json.dumps(turns)
