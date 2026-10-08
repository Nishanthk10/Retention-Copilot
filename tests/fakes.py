"""Mocked provider HTTP for router callers and tests. No real network calls are made."""
import json
import httpx

def provider_of(request):
    if request.url.host=='api.groq.com': return 'groq'
    if request.url.host=='generativelanguage.googleapis.com': return 'gemini'
    return 'ollama'

def ok(provider,text,headers=None):
    if provider=='groq': data={'choices':[{'message':{'content':text}}],'usage':{'total_tokens':3}}
    elif provider=='ollama': data={'message':{'content':text},'prompt_eval_count':1,'eval_count':2}
    else: data={'candidates':[{'content':{'parts':[{'text':text}]}}],'usageMetadata':{'totalTokenCount':3}}
    return httpx.Response(200,json=data,headers=headers)

class FakeProviders:
    """Routes each request to an async behaviour keyed by (provider, model), then provider, then
    default. A behaviour returns response text or an httpx.Response, or raises. Unmatched: HTTP 500."""
    def __init__(self,behaviours=None,default=None):
        self.behaviours=behaviours or {}; self.default=default; self.calls=[]
        self.transport=httpx.MockTransport(self.handle)
    async def handle(self,request):
        body=json.loads(request.content or b'{}'); provider=provider_of(request)
        model=request.url.path.rsplit('/',1)[-1].split(':generateContent')[0] if provider=='gemini' else body['model']
        self.calls.append((provider,model,body))
        behaviour=self.behaviours.get((provider,model)) or self.behaviours.get(provider) or self.default
        if behaviour is None: return httpx.Response(500)
        result=await behaviour(provider,model,body)
        return ok(provider,result) if isinstance(result,str) else result
    def models(self): return [(p,m) for p,m,_ in self.calls]
