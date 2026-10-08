async def emit(runtime,state,decision):
    call=runtime.calls[state['call_id']]
    if not runtime.current(state): return False
    item=decision.get('suggestion'); record=decision.get('record')
    if not item or not record or decision['outcome'] not in {'allow','mask','bypass'}: return False
    if decision['outcome']=='bypass' and not runtime.settings.eval_mode: return False
    if item.get('offer_id') and decision['outcome'] not in {'allow','bypass'}: return False
    item=dict(item,permission_outcome=decision['outcome'])
    # Synchronous audit + append before async delivery; no stale generation can interleave.
    runtime.audit.write(state['call_id'],state['turn_no'],'emit',shown=item,suggestion_id=item['suggestion_id'])
    call['displayed']=(call['displayed']+[item])[-3:]
    await runtime.publish(state['call_id'],{'type':'suggestion','suggestion':item})
    return True
