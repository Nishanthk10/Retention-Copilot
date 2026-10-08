import asyncio, json, sqlite3, time
from uuid import uuid4
from app.stt.turns import close_turn
from summariser.runner import SummaryStore, BackgroundSummariser
from app.graph.agents import Agents
from app.graph.permission import PermissionLayer
from app.graph.build import build_graph, build_checkpoint_graph
from app.fastlane import FastLane
from app.providers.prompt_guard import PromptGuard
from app.providers.router import json_schema_format

class Runtime:
    def __init__(self,settings,kb,stt,router,audit,saver):
        self.settings=settings; self.kb=kb; self.stt=stt; self.router=router; self.audit=audit
        self.calls={}; self.listeners={}; self.audio_owners=set()
        self.db=sqlite3.connect(settings.data_dir/'calls.db',check_same_thread=False)
        self.db.execute('CREATE TABLE IF NOT EXISTS calls(call_id TEXT PRIMARY KEY,status TEXT,checkpoint TEXT,created_at REAL)')
        self.db.commit()
        self.summary_store=SummaryStore(settings.data_dir/'summaries.db',kb.offers,settings.features['guardrails'])
        self.prompt_guard=PromptGuard(settings,audit) if settings.prompt_guard else None
        self.summariser=BackgroundSummariser(self.summary_store,kb.offers,self.summarise_call,audit.write,self.publish,settings.features['guardrails'],self.prompt_guard.classify if self.prompt_guard else None)
        self.permission=PermissionLayer(kb,audit); self.agents=Agents(router,kb,audit); self.fastlane=FastLane(kb)
        self.graph=build_graph(self); self.checkpoints=build_checkpoint_graph(saver)
    async def summarise_call(self,cid,no,messages,schema):
        result=await self.router.complete(messages,'summariser',None,response_format=json_schema_format(schema),call_id=cid,turn_no=no)
        return json.loads(result['text'])
    def new_state(self,cid,status='live'):
        return {'call_id':cid,'status':status,'turns':[],'displayed':[],'generation':0,'cancel':asyncio.Event(),'task':None,'lock':asyncio.Lock(),'next_turn':1,'resumed':False}
    async def restore(self):
        for cid,status,checkpoint,_ in self.db.execute("SELECT * FROM calls WHERE status='live'").fetchall():
            call=self.new_state(cid)
            if checkpoint:
                snapshot=await self.checkpoints.aget_state(json.loads(checkpoint))
                call['turns']=snapshot.values.get('turns',[])
                call['displayed']=snapshot.values.get('displayed',[])
            # Keep turn numbers unique even for a cancelled/partially processed utterance.
            try: maximum=max((r['turn_no'] for r in self.audit.read(cid)),default=0)
            except FileNotFoundError: maximum=0
            call['next_turn']=maximum+1; call['resumed']=True; self.calls[cid]=call
            self.audit.write(cid,maximum,'resume',message='Possible missed turns during restart',checkpoint_turn=call['turns'][-1]['turn_no'] if call['turns'] else 0)
    def create(self):
        if any(c['status']=='live' for c in self.calls.values()): raise ValueError('A call is already live')
        cid=str(uuid4()); self.calls[cid]=self.new_state(cid)
        with self.db: self.db.execute('INSERT INTO calls VALUES(?,?,?,?)',(cid,'live',None,time.time()))
        self.audit.write(cid,0,'call_started',variant=self.settings.variant,test_mode=self.settings.test_mode)
        return cid
    async def publish(self,cid,event):
        event={'call_id':cid,**event}
        for q in list(self.listeners.get(cid,[])):
            if q.full():
                # Slow browser gets a fresh snapshot on reconnect; do not silently drop one item.
                self.listeners[cid].remove(q)
                while not q.empty(): q.get_nowait()
                q.put_nowait({'type':'reconnect_required','call_id':cid})
            else: q.put_nowait(event)
    def current(self,state):
        call=self.calls[state['call_id']]
        return call['status']=='live' and state['generation']==call['generation'] and not call['cancel'].is_set()
    async def cancel(self,cid):
        call=self.calls[cid]; call['generation']+=1; call['cancel'].set()
        if call['task']:
            call['task'].cancel()
            await asyncio.gather(call['task'],return_exceptions=True)
        call['task']=None; call['cancel']=asyncio.Event()
    async def customer_started(self,cid):
        await self.cancel(cid)
        self.audit.write(cid,self.calls[cid]['next_turn'],'customer_turn_started')
    async def accept(self,cid,speaker,raw,start,end,generation=None):
        call=self.calls[cid]
        if call['status']!='live': return
        # Redact configured credentials before constructing the masked Turn too.
        turn=close_turn(cid,call['next_turn'],speaker,self.audit.clean(raw),start,end,self.audit)
        if not turn: return
        call['next_turn']+=1; call['turns'].append(turn.as_dict())
        await self.publish(cid,{'type':'transcript','turn':turn.as_dict()})
        if self.settings.features['summariser']: self.summariser.submit(cid,call['turns'])
        if speaker=='customer':
            if generation is not None and generation!=call['generation']:
                self.audit.write(cid,turn.turn_no,'turn_superseded',reason='Newer customer audio already started')
                return
            if call['task'] and not call['task'].done(): await self.cancel(cid)
            call['task']=asyncio.create_task(self.run(cid,turn.turn_no,call['generation'],list(call['turns'])))
    async def permit(self,s,candidate,displayed=None):
        cid=s['call_id']; no=s['turn_no']
        if not self.current(s): return {'outcome':'deny','suggestion':None,'record':None}
        if not self.settings.features['permission']:
            item=dict(candidate,suggestion_id=str(uuid4()),call_id=cid,turn_no=no)
            record=self.audit.write(cid,no,'permission_bypassed',permission_outcome='bypass',suggestion_id=item['suggestion_id'])
            return {'outcome':'bypass','suggestion':item,'record':record}
        decision=self.permission.check(cid,no,candidate,self.calls[cid]['displayed'] if displayed is None else displayed,s['turns'])
        if decision['error']: await self.publish(cid,{'type':'status','message':'Handle the call until this is fixed'})
        return decision
    async def run(self,cid,no,generation,turns):
        state={'call_id':cid,'turn_no':no,'generation':generation,'turns':turns,'candidates':[],'permitted':[],'displayed':list(self.calls[cid]['displayed'])}
        try:
            result=await self.graph.ainvoke(state)
            if not self.current(state): return
            # aupdate_state may leave an orphan snapshot if cancellation occurs. Recovery
            # always uses the last atomically committed ID, never the latest orphan.
            config=await self.checkpoints.aupdate_state({'configurable':{'thread_id':cid}},result,as_node='completed_turn')
            if not self.current(state): return
            with self.db: self.db.execute('UPDATE calls SET checkpoint=? WHERE call_id=?',(json.dumps(config),cid))
            self.audit.write(cid,no,'turn_committed',checkpoint_id=config['configurable'].get('checkpoint_id'))
        except asyncio.CancelledError:
            self.audit.write(cid,no,'turn_cancelled')
            raise
        except Exception as exc:
            try: self.audit.write(cid,no,'turn_failed',reason=type(exc).__name__)
            except OSError: pass
            await self.publish(cid,{'type':'status','message':'Handle the call until this is fixed'})
    async def end(self,cid):
        call=self.calls[cid]
        call['status']='ended'
        await self.cancel(cid); await self.summariser.stop(cid)
        with self.db: self.db.execute('UPDATE calls SET status=? WHERE call_id=?',('ended',cid))
        saved=True
        try: self.audit.write(cid,call['next_turn']-1,'call_ended')
        except OSError: saved=False
        await self.publish(cid,{'type':'call_ended','log_saved':saved})
        return {'call_id':cid,'log_saved':saved}
    def snapshot(self,cid):
        call=self.calls[cid]
        return {'type':'snapshot','call_id':cid,'status':call['status'],'turns':call['turns'],'suggestions':call['displayed'],'summary':self.summary_store.get_latest(cid,max_turn=call['turns'][-1]['turn_no'] if call['turns'] else 0),'resumed':call['resumed']}
    async def close(self):
        for cid in self.calls:
            await self.cancel(cid); await self.summariser.stop(cid)
        self.summary_store.close(); self.db.close(); await self.router.close()
        if self.prompt_guard: await self.prompt_guard.close()
