import asyncio, json
from urllib.parse import urlparse
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from app.stt.streaming import AudioTurns
from app.logger import valid_id

router=APIRouter()

def live(runtime,cid):
    try: valid_id(cid)
    except ValueError: raise HTTPException(404,'Call not found')
    if cid not in runtime.calls: raise HTTPException(404,'Call not found')
    if runtime.calls[cid]['status']!='live': raise HTTPException(409,'Call is not live')
    return runtime.calls[cid]

def same_origin(ws):
    origin=ws.headers.get('origin')
    return not origin or urlparse(origin).netloc==ws.headers.get('host')

@router.websocket('/ws/audio')
async def audio(ws:WebSocket,call_id:str):
    rt=ws.app.state.runtime
    if not rt or not same_origin(ws): return await ws.close(code=1008)
    try: live(rt,call_id)
    except HTTPException: return await ws.close(code=1008)
    if call_id in rt.audio_owners: return await ws.close(code=1008)
    rt.audio_owners.add(call_id)
    await ws.accept()
    queue=asyncio.Queue(maxsize=120)
    segment_generation=rt.calls[call_id]['generation']
    received_role='none'
    async def accept(role,text,start,end):
        await rt.accept(call_id,role,text,start,end,generation=segment_generation)
    async def already_signalled(): pass
    stream=AudioTurns(rt.stt,accept,already_signalled)
    async def consume():
        nonlocal segment_generation
        while True:
            kind,value,generation=await queue.get()
            if rt.calls[call_id]['status']!='live': return
            if kind=='audio': await stream.feed(value)
            else:
                await stream.switch(value)
                segment_generation=generation
                await ws.send_json({'type':'role_ack','role':stream.role})
    async def receive():
        nonlocal received_role
        while rt.calls[call_id]['status']=='live':
            packet=await ws.receive()
            if packet['type']=='websocket.disconnect': return
            if packet.get('bytes') is not None:
                if len(packet['bytes'])>64000 or len(packet['bytes'])%2: raise ValueError('Invalid PCM frame')
                queue.put_nowait(('audio',packet['bytes'],None))
            elif packet.get('text') is not None:
                message=json.loads(packet['text']);new_role=message.get('role')
                if message.get('type')!='role' or new_role not in {'rep','customer','none'}: raise ValueError('Unknown control message')
                # Cancellation happens at wire receipt, not after slow queued STT.
                if new_role=='customer' and received_role!='customer': await rt.customer_started(call_id)
                received_role=new_role
                queue.put_nowait(('role',new_role,rt.calls[call_id]['generation']))
    tasks=[asyncio.create_task(receive()),asyncio.create_task(consume())]
    try:
        done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
        for task in done: task.result()
    except WebSocketDisconnect: pass
    except Exception as exc:
        rt.audit.write(call_id,rt.calls[call_id]['next_turn'],'audio_error',reason=type(exc).__name__)
        await rt.publish(call_id,{'type':'status','message':'Speech recognition unavailable. Handle the call until this is fixed.'})
        try: await ws.close(code=1008)
        except RuntimeError: pass
    finally:
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks,return_exceptions=True)
        # A disconnect does not close the call. Buffered gap audio is discarded.
        rt.audio_owners.discard(call_id)
        if rt.calls[call_id]['status']=='live':
            rt.audit.write(call_id,rt.calls[call_id]['next_turn'],'audio_disconnected',message='Possible missed turns during reconnect')

@router.websocket('/ws/events')
async def events(ws:WebSocket,call_id:str):
    rt=ws.app.state.runtime
    if not rt or not same_origin(ws) or call_id not in rt.calls: return await ws.close(code=1008)
    await ws.accept()
    q=asyncio.Queue(maxsize=200); rt.listeners.setdefault(call_id,[]).append(q)
    try:
        await ws.send_json(rt.snapshot(call_id))
        while True:
            try: event=await asyncio.wait_for(q.get(),timeout=1)
            except asyncio.TimeoutError: event={'type':'heartbeat','call_id':call_id}
            await ws.send_json(event)
            if event['type'] in {'call_ended','reconnect_required'}: break
    except (WebSocketDisconnect,RuntimeError): pass
    finally:
        if q in rt.listeners.get(call_id,[]): rt.listeners[call_id].remove(q)
