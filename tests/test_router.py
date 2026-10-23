"""Task 5.1 router tests. Every provider is mocked through httpx.MockTransport; no network calls."""
import asyncio, json, time
import httpx
import pytest
from app.providers.router import ProviderRouter,AllProvidersFailed,Cancelled
from tests.fakes import FakeProviders
from app.config import ROOT

# Behaviour tests use the fixed Task 5.1 chain; test_default_chains checks the live config.
SPEC=ROOT/'tests/fixtures/providers_spec.yaml'

G120,QWEN,G20='openai/gpt-oss-120b','qwen/qwen3.8-27b','openai/gpt-oss-20b'
SCHEMA={'type':'json_schema','json_schema':{'name':'response','strict':False,'schema':{'type':'object','properties':{'action':{'type':'string'}}}}}
ANSWER='{"action":"nothing"}'
MSGS=[{'role':'system','content':'Decide.'},{'role':'user','content':'hello'}]

@pytest.fixture
def keyed(settings):
    settings.groq_key='test-secret-value'; settings.gemini_key='gemini-test-key'
    return settings
async def answer(*_): return ANSWER
async def server_error(*_): return httpx.Response(503)
def write_config(tmp_path,chains):
    path=tmp_path/'providers.yaml'
    base={'offer_agent':[f'groq:{G120}'],'behaviour_agent':[f'groq:{G120}'],'summariser':[f'groq:{G20}']}
    base.update(chains); path.write_text(json.dumps(base)); return path
async def complete(router,cid,role='offer_agent',cancel=None,**kw):
    return await router.complete(MSGS,role,cancel,response_format=kw.pop('response_format',SCHEMA),call_id=cid,turn_no=2,**kw)
def steps(audit,cid,step): return [r for r in audit.read(cid) if r['step']==step]

def test_default_chains(keyed,audit):
    router=ProviderRouter(keyed,audit)
    agent=[('groq',G120),('groq',G20),('groq',QWEN),('ollama','qwen3:8b'),('gemini','gemini-2.5-flash')]
    assert router.chains['offer_agent']==agent and router.chains['behaviour_agent']==agent

def test_spec_chains(keyed,audit):
    # Task 5.1 order, used by the behaviour tests below.
    router=ProviderRouter(keyed,audit,config_path=SPEC)
    assert router.chains['offer_agent'][:3]==[('groq',G120),('groq',QWEN),('groq',G20)]
    assert router.chains['summariser']==[('groq',G20),('groq',QWEN),('groq',G120),('ollama','qwen3:8b'),('gemini','gemini-2.5-flash')]

# 1. 120b returns 429 with retry-after 30
async def test_429_retry_after_cools_model_down(cid,keyed,audit):
    async def limited(*_): return httpx.Response(429,headers={'retry-after':'30','x-ratelimit-remaining-tokens':'0','x-ratelimit-remaining-requests':'99'})
    fake=FakeProviders({('groq',G120):limited,('groq',QWEN):answer})
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    result=await complete(router,cid)
    assert (result['provider'],result['model'],result['text'])==('groq',QWEN,ANSWER)
    first=result['attempts'][0]
    assert (first['model'],first['cause'],first['cooldown_s'])==(G120,'rate_limited',30)
    assert (first['remaining_tokens'],first['remaining_requests'])==('0','99')
    assert 29<router.cooldowns[('groq',G120)]-time.monotonic()<=30
    second=await complete(router,cid)
    assert second['model']==QWEN and fake.models()==[('groq',G120),('groq',QWEN),('groq',QWEN)]
    assert any(r['model']==G120 and r['cause']=='cooldown' for r in steps(audit,cid,'model_skipped'))
    await router.close()

RESETS={'x-ratelimit-reset-tokens':'2m3.5s','x-ratelimit-reset-requests':'750ms'}
@pytest.mark.parametrize('headers,expected',[
    ({**RESETS,'x-ratelimit-remaining-requests':'0','x-ratelimit-remaining-tokens':'4000'},0.75),  # requests exhausted
    ({**RESETS,'x-ratelimit-remaining-requests':'12','x-ratelimit-remaining-tokens':'0'},123.5),   # tokens exhausted
    ({**RESETS,'x-ratelimit-remaining-requests':'0','retry-after':'7'},7),                         # retry-after wins
    ({},60)])
async def test_429_cooldown_from_reset_headers(cid,keyed,audit,headers,expected):
    async def limited(*_): return httpx.Response(429,headers=headers)
    router=ProviderRouter(keyed,audit,FakeProviders({('groq',G120):limited,('groq',QWEN):answer}).transport,config_path=SPEC)
    assert (await complete(router,cid))['attempts'][0]['cooldown_s']==pytest.approx(expected)
    await router.close()

# 2. All three Groq models time out
async def test_groq_timeouts_fall_back_to_ollama(cid,keyed,audit):
    async def hang(*_): await asyncio.sleep(10)
    fake=FakeProviders({'groq':hang,'ollama':answer})
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    result=await complete(router,cid,timeout_s=0.05)
    assert (result['provider'],result['model'])==('ollama','qwen3:8b')
    groq=[a for a in result['attempts'] if a['provider']=='groq']
    assert [(a['model'],a['cause']) for a in groq]==[(G120,'timeout'),(QWEN,'timeout'),(G20,'timeout')]
    assert result['attempts'][-1]['cause'] is None and fake.calls[-1][2]['format']==SCHEMA['json_schema']['schema']
    await router.close()

async def test_connection_error_and_invalid_json_move_on(cid,keyed,audit):
    async def down(*_): raise httpx.ConnectError('refused')
    async def prose(*_): return 'Sure! Here is my answer.'
    router=ProviderRouter(keyed,audit,FakeProviders({('groq',G120):down,('groq',QWEN):prose,('groq',G20):answer}).transport,config_path=SPEC)
    result=await complete(router,cid)
    assert [a['cause'] for a in result['attempts']]==['connection_error','invalid_json',None]
    await router.close()

# 3. Every model fails for 3 rounds
async def test_every_model_fails_three_rounds(cid,keyed,audit):
    fake=FakeProviders(default=server_error)
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    with pytest.raises(AllProvidersFailed) as failed: await complete(router,cid)
    attempts=failed.value.attempts
    assert len(attempts)==15 and len(fake.calls)==15
    assert [a['round'] for a in attempts]==[1]*5+[2]*5+[3]*5
    assert {a['cause'] for a in attempts}=={'http_5xx'}
    assert [(a['provider'],a['model']) for a in attempts[:5]]==router.chains['offer_agent']
    assert len(steps(audit,cid,'model_attempt'))==15 and steps(audit,cid,'model_failed')
    await router.close()

# 4. cancel_event set during the 2nd attempt
async def test_cancel_during_second_attempt(cid,keyed,audit):
    entered=asyncio.Event(); cancel=asyncio.Event()
    async def hang(*_): entered.set(); await asyncio.sleep(100)
    fake=FakeProviders({('groq',G120):server_error,('groq',QWEN):hang,('groq',G20):answer})
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    task=asyncio.create_task(complete(router,cid,cancel=cancel))
    await entered.wait(); cancel.set()
    with pytest.raises(Cancelled): await asyncio.wait_for(task,1)
    assert fake.models()==[('groq',G120),('groq',QWEN)]
    assert len(steps(audit,cid,'model_attempt'))==2
    assert steps(audit,cid,'model_cancelled')[0]['model']==QWEN
    assert issubclass(Cancelled,asyncio.CancelledError)
    await router.close()

async def test_cancel_before_start_makes_no_attempt(cid,keyed,audit):
    cancel=asyncio.Event(); cancel.set()
    fake=FakeProviders(default=answer)
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    with pytest.raises(Cancelled): await complete(router,cid,cancel=cancel)
    assert fake.calls==[] and not steps(audit,cid,'model_attempt')
    await router.close()

# 5. json_schema unsupported (400)
async def test_json_schema_400_retries_same_model_with_json_object(cid,keyed,audit):
    async def no_schema(provider,model,body):
        return httpx.Response(400) if body['response_format']['type']=='json_schema' else ANSWER
    fake=FakeProviders({('groq',G120):no_schema})
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    result=await complete(router,cid)
    assert result['model']==G120 and fake.models()==[('groq',G120)]*2
    retry=fake.calls[1][2]
    assert retry['response_format']=={'type':'json_object'}
    assert 'JSON' in retry['messages'][0]['content'] and retry['messages'][1:]==MSGS
    assert [a['cause'] for a in result['attempts']]==['http_400',None]
    await router.close()

async def test_other_400_is_not_retried(cid,keyed,audit):
    async def bad(*_): return httpx.Response(400)
    fake=FakeProviders({('groq',G120):bad,('groq',QWEN):answer})
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    result=await complete(router,cid,response_format=None)
    assert fake.models()==[('groq',G120),('groq',QWEN)] and result['attempts'][0]['cause']=='http_400'
    await router.close()

# 6. prompt-guard model listed in a chain
@pytest.mark.parametrize('model',['meta-llama/llama-prompt-guard-2-86m','meta-llama/llama-prompt-guard-2-22m','openai/gpt-oss-safeguard-20b'])
def test_classifier_model_in_chain_rejected_at_startup(tmp_path,keyed,audit,model):
    with pytest.raises(ValueError,match='not a chat model'):
        ProviderRouter(keyed,audit,config_path=write_config(tmp_path,{'summariser':[f'groq:{G20}',f'groq:{model}']}))

def test_config_cannot_substitute_other_env_vars(tmp_path,keyed,audit):
    with pytest.raises(ValueError,match='Unsupported variable'):
        ProviderRouter(keyed,audit,config_path=write_config(tmp_path,{'offer_agent':['groq:${GROQ_API_KEY}']}))

# 7. GEMINI_API_KEY missing
async def test_missing_gemini_key_skipped_and_logged_once(cid,tmp_path,keyed,audit):
    keyed.gemini_key=''
    config=write_config(tmp_path,{'offer_agent':[f'groq:{G120}','gemini:${GEMINI_MODEL}','ollama:${OLLAMA_MODEL}']})
    fake=FakeProviders({'groq':server_error,'ollama':answer})
    router=ProviderRouter(keyed,audit,fake.transport,config_path=config)
    for _ in range(2): assert (await complete(router,cid))['provider']=='ollama'
    assert all(p!='gemini' for p,_ in fake.models())
    skipped=steps(audit,cid,'provider_skipped')
    assert [(r['provider'],r['cause']) for r in skipped]==[('gemini','not_configured')]
    await router.close()

async def test_unconfigured_ollama_skipped(cid,keyed,audit):
    keyed.ollama_model=''
    fake=FakeProviders({'groq':server_error,'gemini':answer})
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    assert (await complete(router,cid))['provider']=='gemini'
    assert all(p!='ollama' for p,_ in fake.models())
    assert [r['provider'] for r in steps(audit,cid,'provider_skipped')]==['ollama']
    await router.close()

# 8. Primary changed in providers.yaml
async def test_primary_changed_in_config(cid,tmp_path,keyed,audit):
    config=write_config(tmp_path,{'offer_agent':[f'groq:{QWEN}',f'groq:{G120}']})
    fake=FakeProviders(default=answer)
    router=ProviderRouter(keyed,audit,fake.transport,config_path=config)
    assert (await complete(router,cid))['model']==QWEN and fake.models()==[('groq',QWEN)]
    await router.close()

async def test_all_models_cooling_waits_for_short_cooldown(cid,keyed,audit):
    fake=FakeProviders(default=answer)
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    soon=time.monotonic()+0.1
    for entry in router.chains['offer_agent']: router.cooldowns[entry]=soon
    result=await complete(router,cid)
    assert result['model']==G120 and steps(audit,cid,'cooldown_wait')
    await router.close()

async def test_all_models_cooling_beyond_ten_seconds_ends_rounds(cid,keyed,audit):
    fake=FakeProviders(default=answer)
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    for entry in router.chains['offer_agent']: router.cooldowns[entry]=time.monotonic()+30
    with pytest.raises(AllProvidersFailed): await complete(router,cid)
    assert fake.calls==[] and len(steps(audit,cid,'round_ended'))==3
    await router.close()

async def test_retries_off_uses_primary_once(cid,keyed,audit):
    keyed.features['retries']=False
    fake=FakeProviders(default=server_error)
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    with pytest.raises(AllProvidersFailed) as failed: await complete(router,cid)
    assert fake.models()==[('groq',G120)] and len(failed.value.attempts)==1
    router.cooldowns[('groq',G120)]=time.monotonic()+30
    with pytest.raises(AllProvidersFailed) as failed: await complete(router,cid)
    assert len(fake.calls)==1 and failed.value.attempts[0]['cause']=='cooldown'
    await router.close()

async def test_only_provider_filters_every_chain(cid,keyed,audit):
    keyed.only_provider='ollama'
    fake=FakeProviders(default=answer)
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    assert all(chain==[('ollama','qwen3:8b')] for chain in router.chains.values())
    for role in ['offer_agent','behaviour_agent','summariser']: await complete(router,cid,role)
    assert {p for p,_ in fake.models()}=={'ollama'}
    await router.close()

async def test_attempts_audited_without_keys(cid,keyed,audit):
    async def echo_key(*_): return '{"action":"nothing","rationale":"key test-secret-value gsk_abcdefghijk"}'
    fake=FakeProviders({('groq',G120):server_error,('groq',QWEN):echo_key})
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    result=await complete(router,cid)
    assert 'test-secret-value' not in result['text'] and 'gsk_' not in result['text']
    records=audit.read(cid)
    assert all(r['call_id']==cid and r['turn_no']==2 for r in records)
    assert [r['step'] for r in records]==['model_attempt','model_retry','model_attempt','model_result']
    log=(audit.directory/f'{cid}.jsonl').read_text()
    assert 'test-secret-value' not in log and 'gsk_abc' not in log
    await router.close()

async def test_auth_failure_disables_provider(cid,keyed,audit):
    async def unauthorised(*_): return httpx.Response(401)
    fake=FakeProviders({'groq':unauthorised,'ollama':answer})
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    result=await complete(router,cid)
    assert result['provider']=='ollama' and fake.models()==[('groq',G120),('ollama','qwen3:8b')]
    assert result['attempts'][0]['cause']=='auth_failed'
    assert (await complete(router,cid,'summariser'))['provider']=='ollama'
    assert [p for p,_ in fake.models()].count('groq')==1
    assert [(r['provider'],r['cause']) for r in steps(audit,cid,'provider_disabled')]==[('groq','auth_failed')]
    await router.close()

async def test_forbidden_disables_provider(cid,keyed,audit):
    async def forbidden(*_): return httpx.Response(403)
    fake=FakeProviders({'groq':server_error,'ollama':forbidden,'gemini':answer})
    router=ProviderRouter(keyed,audit,fake.transport,config_path=SPEC)
    assert (await complete(router,cid))['provider']=='gemini'
    assert 'ollama' in router.disabled and len(steps(audit,cid,'provider_disabled'))==1
    await router.close()
