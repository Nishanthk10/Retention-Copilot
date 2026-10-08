"""Per-role model fallback chains with 429 cooldowns, cancellation and audit (DEC-07, Task 5.1).
Hand-built: no SDK implicit retries, no LangGraph retry policies, no retry libraries."""
import asyncio, json, re, time
import httpx, yaml
from app.config import ROOT
from app.masking import mask_pii

CONFIG=ROOT/'config/providers.yaml'
ROLES={'offer_agent','behaviour_agent','summariser'}
PROVIDERS={'groq','ollama','gemini'}
# Classifiers / heavily rate-limited models are never chat fallbacks.
FORBIDDEN=re.compile(r'meta-llama/llama-prompt-guard-2-.*|openai/gpt-oss-safeguard-20b')
MAX_ROUNDS=3; MAX_ROUND_WAIT_S=10; DEFAULT_COOLDOWN_S=60
GROQ_URL='https://api.groq.com/openai/v1/chat/completions'
GEMINI_URL='https://generativelanguage.googleapis.com/v1beta/models'
JSON_INSTRUCTION='Respond with only a single valid JSON object, no other text.'

class AllProvidersFailed(RuntimeError):
    def __init__(self,attempts):
        super().__init__('All configured provider attempts failed'); self.attempts=attempts
class Cancelled(asyncio.CancelledError):
    """A new customer turn started (INV-08). Subclasses CancelledError so graph handling applies."""
class AttemptFailed(Exception):
    def __init__(self,cause,headers=None):
        super().__init__(cause); self.cause=cause; self.headers=headers or {}

def json_schema_format(schema):
    return {'type':'json_schema','json_schema':{'name':'response','strict':False,'schema':schema}}

def parse_duration(value):
    """Seconds from '30', '7.66s', '2m59.56s' or '500ms' (Groq reset headers); None if absent."""
    if value is None: return None
    try: return float(value)
    except ValueError: pass
    parts=re.findall(r'([\d.]+)(ms|h|m|s)',value)
    return sum(float(n)*{'h':3600,'m':60,'s':1,'ms':0.001}[u] for n,u in parts) if parts else None

def cooldown_seconds(headers):
    # retry-after wins; otherwise reset the limit that was hit (requests exhausted, else tokens).
    seconds=parse_duration(headers.get('retry-after'))
    if seconds is None:
        limit='requests' if headers.get('x-ratelimit-remaining-requests')=='0' else 'tokens'
        seconds=parse_duration(headers.get(f'x-ratelimit-reset-{limit}'))
    return DEFAULT_COOLDOWN_S if seconds is None else seconds

def load_chains(path,settings):
    # Only these variables are substituted, so a chain entry can never pull a key into logs (INV-03).
    env={'OLLAMA_MODEL':settings.ollama_model,'GEMINI_MODEL':settings.gemini_model}
    def substitute(m):
        if m.group(1) not in env: raise ValueError(f'Unsupported variable in providers.yaml: {m.group(1)}')
        return env[m.group(1)] or ''
    raw=yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    if set(raw)!=ROLES: raise ValueError('providers.yaml must define exactly: '+', '.join(sorted(ROLES)))
    chains={}
    for role,entries in raw.items():
        chain=[]
        for entry in entries or []:
            provider,sep,model=re.sub(r'\$\{(\w+)\}',substitute,str(entry)).partition(':')
            if not sep or provider not in PROVIDERS: raise ValueError(f'Invalid chain entry for {role}: {entry}')
            if FORBIDDEN.fullmatch(model): raise ValueError(f'{model} is not a chat model and cannot be in a chain')
            chain.append((provider,model))
        # Ablations pin one provider so every version uses the same model (DEC-21).
        if settings.only_provider: chain=[e for e in chain if e[0]==settings.only_provider]
        if not chain: raise ValueError(f'No models configured for {role}')
        chains[role]=chain
    return chains

class ProviderRouter:
    def __init__(self,settings,audit,transport=None,config_path=CONFIG):
        self.settings=settings; self.audit=audit
        self.chains=load_chains(config_path,settings)
        self.http=httpx.AsyncClient(transport=transport)
        # disabled: providers that returned 401/403; skipped for the rest of the process.
        self.cooldowns={}; self.skip_logged=set(); self.disabled=set()
    async def close(self): await self.http.aclose()
    def configured(self,provider,model):
        s=self.settings
        if provider=='groq': return bool(s.groq_key and model)
        if provider=='ollama': return bool(s.ollama_url and model)
        return bool(s.gemini_key and model)
    def cooling(self,entry): return self.cooldowns.get(entry,0)>time.monotonic()
    async def send(self,provider,model,messages,response_format,timeout_s):
        s=self.settings; kind=(response_format or {}).get('type')
        timeout=httpx.Timeout(timeout_s,connect=min(4,timeout_s))
        if provider=='groq':
            body={'model':model,'messages':messages,'temperature':0,'max_completion_tokens':1800}
            if response_format: body['response_format']=response_format
            r=await self.http.post(GROQ_URL,headers={'Authorization':'Bearer '+s.groq_key},json=body,timeout=timeout)
        elif provider=='ollama':
            body={'model':model,'messages':messages,'stream':False,'options':{'temperature':0}}
            if kind=='json_schema': body['format']=response_format['json_schema']['schema']
            elif kind=='json_object': body['format']='json'
            r=await self.http.post(s.ollama_url.rstrip('/')+'/api/chat',json=body,timeout=timeout)
        else:
            system='\n'.join(m['content'] for m in messages if m['role']=='system')
            contents=[{'role':'model' if m['role']=='assistant' else 'user','parts':[{'text':m['content']}]} for m in messages if m['role']!='system']
            config={'temperature':0}
            if kind: config['responseMimeType']='application/json'
            if kind=='json_schema': config['responseJsonSchema']=response_format['json_schema']['schema']
            r=await self.http.post(f'{GEMINI_URL}/{model}:generateContent',headers={'x-goog-api-key':s.gemini_key},json={'systemInstruction':{'parts':[{'text':system}]},'contents':contents,'generationConfig':config},timeout=timeout)
        if r.status_code==429: raise AttemptFailed('rate_limited',r.headers)
        if r.status_code==400: raise AttemptFailed('http_400',r.headers)
        if r.status_code in (401,403): raise AttemptFailed('auth_failed',r.headers)
        if r.status_code>=500: raise AttemptFailed('http_5xx',r.headers)
        if r.status_code>=300: raise AttemptFailed(f'http_{r.status_code}',r.headers)
        try:
            data=r.json()
            if provider=='groq': return data['choices'][0]['message']['content'],data.get('usage'),r.headers
            if provider=='ollama': return data['message']['content'],{'prompt_tokens':data.get('prompt_eval_count'),'completion_tokens':data.get('eval_count')},r.headers
            return ''.join(p.get('text','') for p in data['candidates'][0]['content']['parts']),data.get('usageMetadata'),r.headers
        except (ValueError,KeyError,IndexError,TypeError):
            raise AttemptFailed('bad_response',r.headers) from None
    async def attempt(self,provider,model,messages,response_format,timeout_s,cancel_event):
        """One request raced against cancel_event and timeout_s. Raises AttemptFailed or Cancelled."""
        work=asyncio.create_task(self.send(provider,model,messages,response_format,timeout_s))
        waiter=asyncio.create_task(cancel_event.wait()) if cancel_event else None
        tasks=[t for t in (work,waiter) if t]
        try:
            done,_=await asyncio.wait(tasks,timeout=timeout_s,return_when=asyncio.FIRST_COMPLETED)
            if waiter in done: raise Cancelled()
            if work not in done: raise AttemptFailed('timeout')
            try: text,tokens,headers=work.result()
            except AttemptFailed: raise
            except httpx.TimeoutException: raise AttemptFailed('timeout') from None
            except httpx.TransportError: raise AttemptFailed('connection_error') from None
            # Never log exception messages/URLs: they can contain credentials or response bodies.
            except Exception as exc: raise AttemptFailed(type(exc).__name__) from None
        finally:
            for t in tasks: t.cancel()
            await asyncio.gather(*tasks,return_exceptions=True)
        # Responses may echo PII or credentials supplied as untrusted speech.
        text=mask_pii(self.audit.clean(text))[0]
        if response_format:
            try: json.loads(text)
            except ValueError: raise AttemptFailed('invalid_json',headers) from None
        return text,tokens,headers
    async def sleep(self,seconds,cancel_event):
        if not cancel_event: return await asyncio.sleep(seconds)
        try: await asyncio.wait_for(cancel_event.wait(),seconds)
        except asyncio.TimeoutError: return
        raise Cancelled()
    async def complete(self,messages,role,cancel_event,response_format=None,timeout_s=8,*,call_id,turn_no):
        if role not in self.chains: raise ValueError('Unknown model role')
        # retries off (no_retries / naive ablations): the primary only, one attempt, no rounds.
        single=not self.settings.features['retries']
        chain=self.chains[role][:1] if single else self.chains[role]
        attempts=[]
        def log(step,**fields): self.audit.write(call_id,turn_no,step,model_role=role,**fields)
        def cancelled(provider=None,model=None):
            log('model_cancelled',provider=provider,model=model); return Cancelled()
        for round_no in range(1,(1 if single else MAX_ROUNDS)+1):
            entries=[]
            for entry in chain:
                if entry[0] in self.disabled: continue
                if self.configured(*entry): entries.append(entry)
                elif entry[0] not in self.skip_logged:
                    self.skip_logged.add(entry[0]); log('provider_skipped',provider=entry[0],cause='not_configured')
            if not entries: break
            waits=[self.cooldowns[e]-time.monotonic() for e in entries if self.cooling(e)]
            if not single and len(waits)==len(entries):
                if min(waits)>MAX_ROUND_WAIT_S:
                    log('round_ended',round=round_no,cause='all_cooling_down',wait_s=round(min(waits),3)); continue
                log('cooldown_wait',round=round_no,wait_s=round(min(waits),3))
                # Margin: the event loop may wake up to one clock tick early.
                try: await self.sleep(min(waits)+0.05,cancel_event)
                except Cancelled: raise cancelled() from None
            for provider,model in entries:
                if cancel_event and cancel_event.is_set(): raise cancelled(provider,model)
                if provider in self.disabled: continue
                if self.cooling((provider,model)):
                    if not single:
                        log('model_skipped',provider=provider,model=model,cause='cooldown'); continue
                    failure={'provider':provider,'model':model,'cause':'cooldown','latency_ms':0,'round':round_no}
                    attempts.append(failure); log('model_retry',provider=provider,model=model,retries=[failure])
                    continue
                fmt=response_format; msgs=messages
                while True:
                    log('model_attempt',provider=provider,model=model,round=round_no,attempt=len(attempts)+1,response_format=(fmt or {}).get('type'),input=msgs)
                    start=time.monotonic(); headers={}; cause=None
                    try: text,tokens,headers=await self.attempt(provider,model,msgs,fmt,timeout_s,cancel_event)
                    except Cancelled: raise cancelled(provider,model) from None
                    except AttemptFailed as exc: cause=exc.cause; headers=exc.headers
                    record={'provider':provider,'model':model,'cause':cause,'latency_ms':round((time.monotonic()-start)*1000,1),'round':round_no}
                    if provider=='groq':
                        record['remaining_tokens']=headers.get('x-ratelimit-remaining-tokens')
                        record['remaining_requests']=headers.get('x-ratelimit-remaining-requests')
                    attempts.append(record)
                    if cause is None:
                        try: value=json.loads(text) if fmt else None
                        except ValueError: value=None
                        log('model_result',provider=provider,model=model,tokens=tokens,cost=None,cost_status='not_available',retries=[a for a in attempts if a['cause']],latency_ms=record['latency_ms'],output=text,model_reasoning=value.get('rationale') if isinstance(value,dict) else None)
                        return {'text':text,'provider':provider,'model':model,'tokens':tokens,'latency_ms':record['latency_ms'],'attempts':attempts}
                    if cause=='rate_limited':
                        record['cooldown_s']=cooldown_seconds(headers)
                        self.cooldowns[(provider,model)]=time.monotonic()+record['cooldown_s']
                    log('model_retry',provider=provider,model=model,retries=[record])
                    if cause=='auth_failed' and provider not in self.disabled:
                        self.disabled.add(provider); log('provider_disabled',provider=provider,cause='auth_failed')
                    if cause=='http_400' and (fmt or {}).get('type')=='json_schema':
                        # Unsupported json_schema: same model once more in JSON mode; callers still validate.
                        schema=json.dumps(fmt['json_schema'].get('schema',{}))
                        fmt={'type':'json_object'}
                        msgs=[{'role':'system','content':JSON_INSTRUCTION+' It must match this JSON schema: '+schema}]+messages
                        if cancel_event and cancel_event.is_set(): raise cancelled(provider,model)
                        continue
                    break
        log('model_failed',retries=attempts)
        raise AllProvidersFailed(attempts)
