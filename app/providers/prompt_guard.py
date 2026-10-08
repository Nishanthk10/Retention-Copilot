"""Prompt Guard 2 client, used only by summariser guardrail L2. Never a chat fallback (DEC-07)."""
import httpx

class PromptGuard:
    def __init__(self,settings,audit):
        self.settings=settings; self.audit=audit
        self.http=httpx.AsyncClient(timeout=httpx.Timeout(35,connect=4))
    async def close(self): await self.http.aclose()
    async def classify(self,call_id,turn_no,text):
        self.audit.write(call_id,turn_no,'model_attempt',provider='groq',model_role='prompt_guard')
        try:
            r=await self.http.post('https://api.groq.com/openai/v1/chat/completions',headers={'Authorization':'Bearer '+self.settings.groq_key},json={'model':'meta-llama/llama-prompt-guard-2-86m','messages':[{'role':'user','content':text}]})
            r.raise_for_status()
            answer=r.json()['choices'][0]['message']['content']
            flags=['classifier_flag'] if any(x in answer.lower() for x in ['malicious','injection','jailbreak','1']) else []
            self.audit.write(call_id,turn_no,'model_result',provider='groq',model_role='prompt_guard',flags=flags)
            return flags
        except Exception as exc:
            self.audit.write(call_id,turn_no,'classifier_unavailable',reason=type(exc).__name__)
            return []
