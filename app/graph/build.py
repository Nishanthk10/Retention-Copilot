import asyncio
from langgraph.graph import StateGraph, START, END
from .state import GraphState
from .context import assemble_context
from .emit import emit
from .agents import KBFailure

def build_graph(runtime):
    async def context(s):
        summary=runtime.summary_store.get_latest(s['call_id'],max_turn=s['turn_no'])
        runtime.audit.write(s['call_id'],s['turn_no'],'context_assembly',summary_frontier=summary['last_summarised_turn'])
        return {'summary':summary,'context':assemble_context(s['turns'],summary,runtime.calls[s['call_id']]['displayed'])}
    async def fast_lane(s):
        if runtime.settings.features['fastlane']:
            tip=await asyncio.to_thread(runtime.fastlane.suggest,s['turns'][-1]['text'])
            if tip:
                decision=await runtime.permit(s,tip)
                await emit(runtime,s,decision)
        return {}
    async def agents(s):
        cancel=runtime.calls[s['call_id']]['cancel']
        if runtime.settings.features['naive']:
            jobs=[runtime.agents.naive(s['call_id'],s['turn_no'],s['turns'],cancel)]
        else:
            jobs=[runtime.agents.run(s['call_id'],s['turn_no'],s['context'],source,cancel) for source in ['offer','behaviour']]
        results=await asyncio.gather(*jobs,return_exceptions=True)
        candidates=[]; failed=0
        for result in results:
            if isinstance(result,BaseException):
                if isinstance(result,asyncio.CancelledError): raise result
                failed+=1
                if isinstance(result,KBFailure):
                    await runtime.publish(s['call_id'],{'type':'status','message':'Failed fetching docs'})
                runtime.audit.write(s['call_id'],s['turn_no'],'agent_failed',reason=type(result).__name__)
            elif result: candidates.append(result)
        if failed==len(jobs):
            await runtime.publish(s['call_id'],{'type':'status','message':'Handle the call until this is fixed'})
        elif not candidates:
            await runtime.publish(s['call_id'],{'type':'status','message':'Nothing new to suggest'})
        return {'candidates':candidates,'failures':failed}
    async def permission(s):
        staged=list(runtime.calls[s['call_id']]['displayed']);decisions=[]
        for candidate in s['candidates']:
            decision=await runtime.permit(s,candidate,staged);decisions.append(decision)
            if decision.get('suggestion'): staged.append(decision['suggestion'])
        return {'permitted':decisions}
    async def output(s):
        for decision in s['permitted']: await emit(runtime,s,decision)
        return {'displayed':list(runtime.calls[s['call_id']]['displayed'])}
    graph=StateGraph(GraphState)
    for name,node in [('context_assembly',context),('fast_lane',fast_lane),('offer_and_behaviour',agents),('permission_layer',permission),('emit',output)]: graph.add_node(name,node)
    graph.add_edge(START,'context_assembly')
    for a,b in [('context_assembly','fast_lane'),('fast_lane','offer_and_behaviour'),('offer_and_behaviour','permission_layer'),('permission_layer','emit'),('emit',END)]: graph.add_edge(a,b)
    return graph.compile()

def build_checkpoint_graph(saver):
    # The work graph runs without intermediate persistence. Only a fully completed state
    # is copied to this checkpoint graph via aupdate_state, then its ID is committed.
    graph=StateGraph(GraphState)
    graph.add_node('completed_turn',lambda s:s)
    graph.add_edge(START,'completed_turn'); graph.add_edge('completed_turn',END)
    return graph.compile(checkpointer=saver)
