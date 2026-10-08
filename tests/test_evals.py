import ast,json
from pathlib import Path
import pytest,yaml
from evals.score import score,wer
from app.config import ROOT,Settings
from app.graph.agents import Agents

def test_replay_isolation():
    for path in [ROOT/'evals/replay.py',ROOT/'evals/crash_resume.py']:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom):
                assert not (node.module or '').startswith(('app.graph','app.stt','summariser'))
    assert '/ws/audio' in (ROOT/'web/replay.js').read_text() or "socket.send" in (ROOT/'web/replay.js').read_text()
def test_standalone_package():
    for path in (ROOT/'summariser').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom): assert not (node.module or '').startswith('app')
def test_score_deadline():
    s=yaml.safe_load((ROOT/'evals/scenarios/S1.yaml').read_text());oid=s['labels']['expected_offer_id']
    def trace(no):return [{'step':'emit','shown':{'offer_id':oid,'turn_no':no,'type':'offer'}}]
    assert score([],trace(4),s,{oid})['success']
    assert not score([],trace(7),s,{oid})['success']
    assert score([],trace(4),s,set())['non_kb_offers']==1
    assert wer('one two','one two')==0 and wer('one two','one')==.5
def test_ablation_config(tmp_path,monkeypatch):
    monkeypatch.setenv('DATA_DIR',str(tmp_path));monkeypatch.setenv('LOG_DIR',str(tmp_path))
    for variant in ['full','naive','no_permission','no_summariser_guardrails','no_retries']:
        cfg=yaml.safe_load((ROOT/'evals/configs'/f'{variant}.yaml').read_text())
        assert cfg['pii_masking'] is True
    with pytest.raises(ValueError): Settings(variant='no_permission',eval_mode=False)
    assert Settings(variant='no_summariser_guardrails',eval_mode=True).features['guardrails'] is False
@pytest.mark.asyncio
async def test_tool_budget(cid,kb,audit):
    class Router:
        async def complete(self,*args,**kwargs):
            return {'text':json.dumps({'action':'search','query':'price','reasons':['price']})}
    agents=Agents(Router(),kb,audit)
    assert await agents.run(cid,2,{'turns':[]},'offer',None) is None
    records=audit.read(cid)
    assert len([r for r in records if r['step']=='before_tool'])==1
    assert any(r['step']=='tool_refused' for r in records)
