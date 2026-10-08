"""Standalone persistence and coalescing worker; dependencies are injected."""
import asyncio, json, sqlite3
from .schema import default_summary
from .guardrails import ValidationResult, validate_summary
from .summariser import summarise

class SummaryStore:
    def __init__(self,path,kb,guardrails=True):
        self.db=sqlite3.connect(path,check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS summaries(call_id TEXT, version INTEGER, json TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(call_id,version))')
        self.kb=kb; self.guardrails=guardrails
    def get_latest(self,call_id,max_turn=None):
        rows=self.db.execute('SELECT json FROM summaries WHERE call_id=? ORDER BY version DESC',(call_id,)).fetchall()
        for row in rows:
            value=json.loads(row[0])
            if max_turn is None or value.get('last_summarised_turn',0)<=max_turn: return value
        return default_summary()
    def write(self,call_id,result):
        if not isinstance(result,ValidationResult) or not result.passed: raise ValueError('Validated summary required')
        result=validate_summary(result.value,self.kb,self.guardrails)
        current=self.get_latest(call_id)
        if result.value['last_summarised_turn']<=current['last_summarised_turn']: return False
        with self.db:
            self.db.execute('INSERT INTO summaries(call_id,version,json) VALUES(?,?,?)',(call_id,result.value['last_summarised_turn'],json.dumps(result.value)))
        return True
    def close(self): self.db.close()

class BackgroundSummariser:
    def __init__(self,store,kb,complete,log,publish,guardrails=True,classifier=None):
        self.store=store; self.kb=kb; self.complete=complete; self.log=log; self.publish=publish
        self.guardrails=guardrails; self.classifier=classifier; self.pending={}; self.tasks={}
    def submit(self,call_id,turns):
        self.pending[call_id]=list(turns)
        if call_id not in self.tasks or self.tasks[call_id].done():
            self.tasks[call_id]=asyncio.create_task(self._run(call_id))
    async def _run(self,call_id):
        while call_id in self.pending:
            turns=self.pending.pop(call_id); no=turns[-1]['turn_no']
            previous=self.store.get_latest(call_id,max_turn=no)
            async def complete(messages,schema):
                return await self.complete(call_id,no,messages,schema)
            def log(step,**fields): self.log(call_id,no,step,**fields)
            classifier=(lambda text:self.classifier(call_id,no,text)) if self.classifier else None
            result=await summarise(turns,previous,self.kb,complete,log,self.guardrails,classifier)
            if result and self.store.write(call_id,result):
                log('summary_saved',summary=result.value,guardrails=self.guardrails)
                await self.publish(call_id,{'type':'summary','summary':result.value})
    async def stop(self,call_id):
        self.pending.pop(call_id,None)
        task=self.tasks.pop(call_id,None)
        if task:
            task.cancel()
            await asyncio.gather(task,return_exceptions=True)
