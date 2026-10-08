"""Prompt Guard 2 client, used only by summariser guardrail L2. Never a chat fallback (DEC-07).
Groq returns the injection probability as text, e.g. '0.9996024966239929'. classify never raises:
a failed or unparseable call is reported and L2 heuristics still run."""
import math
import httpx

MODEL='meta-llama/llama-prompt-guard-2-86m'

class PromptGuard:
    def __init__(self,settings,audit,transport=None):
        self.settings=settings; self.audit=audit; self.threshold=settings.prompt_guard_threshold
        self.http=httpx.AsyncClient(timeout=httpx.Timeout(35,connect=4),transport=transport)
    async def close(self): await self.http.aclose()
    async def classify(self,call_id,turn_no,text):
        """Returns {status: 'ok'|'unavailable'|'unparseable', score, flagged}."""
        self.audit.write(call_id,turn_no,'model_attempt',provider='groq',model=MODEL,model_role='prompt_guard')
        try:
            r=await self.http.post('https://api.groq.com/openai/v1/chat/completions',headers={'Authorization':'Bearer '+self.settings.groq_key},json={'model':MODEL,'messages':[{'role':'user','content':text}]})
            r.raise_for_status()
        except Exception as exc:
            # Never log exception messages/URLs: they can contain credentials.
            result={'status':'unavailable','score':None,'flagged':False}
            self.audit.write(call_id,turn_no,'classifier_unavailable',provider='groq',model=MODEL,model_role='prompt_guard',reason=type(exc).__name__,**result)
            return result
        try:
            score=float(r.json()['choices'][0]['message']['content'].strip())
            if not (math.isfinite(score) and 0<=score<=1): raise ValueError('Score out of range')
            result={'status':'ok','score':score,'flagged':score>=self.threshold}
        except (ValueError,KeyError,IndexError,TypeError,AttributeError):
            result={'status':'unparseable','score':None,'flagged':False}
        self.audit.write(call_id,turn_no,'model_result',provider='groq',model=MODEL,model_role='prompt_guard',threshold=self.threshold,source='classifier',**result)
        return result
