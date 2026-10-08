"""Pure HTTP/WebSocket client. Never imports graph, STT, or summariser code."""
import sys as _sys
from pathlib import Path as _Path
if __package__ in (None, ''): _sys.path.insert(0,str(_Path(__file__).resolve().parents[1]))
import argparse,asyncio,json,time,wave
from pathlib import Path
from uuid import uuid4
import httpx,websockets
from evals.check_recordings import check,ROOT

async def replay(scenario,url='http://127.0.0.1:8000',output=None,grace=40):
    timeline=check(scenario)
    output=Path(output or ROOT/'evals/reports/runs'/f'{scenario}-{uuid4()}.jsonl');output.parent.mkdir(parents=True,exist_ok=True)
    async with httpx.AsyncClient(base_url=url,timeout=10) as client:
        health=(await client.get('/health')).json()
        if not health.get('ready'): raise RuntimeError('Server is not ready')
        if health.get('test_mode'): raise RuntimeError('Audio evaluation requires TEST_MODE=false')
        r=await client.post('/calls');r.raise_for_status();cid=r.json()['call_id']
        wsurl=url.replace('http://','ws://').replace('https://','wss://')
        events=[];completed=asyncio.Event();listening=asyncio.Event()
        async def collect():
            async with websockets.connect(wsurl+'/ws/events?call_id='+cid) as ws:
                listening.set()
                async for raw in ws:
                    event=json.loads(raw);event['received_at']=time.time();events.append(event)
                    if event['type']=='call_ended': completed.set();break
        collector=asyncio.create_task(collect())
        failure=None
        try:
            await asyncio.wait_for(listening.wait(),10)
            async with websockets.connect(wsurl+'/ws/audio?call_id='+cid,max_size=2**20) as ws:
                async def role(value):
                    await ws.send(json.dumps({'type':'role','role':value}))
                    ack=json.loads(await asyncio.wait_for(ws.recv(),45))
                    if ack.get('role')!=value: raise RuntimeError('Role acknowledgement mismatch')
                for item in timeline['utterances']:
                    await asyncio.sleep(item['gap_before_s']);await role(item['role'])
                    with wave.open(str(ROOT/'evals/recordings'/scenario/item['file']),'rb') as wav:
                        while pcm:=wav.readframes(1600):
                            await ws.send(pcm);await asyncio.sleep(len(pcm)/32000)
                await role('none')
                # Wait for final customer graph to finish; do not terminate its retry chain early.
                deadline=time.monotonic()+grace
                customer_no=max(t['turn']['turn_no'] for t in events if t['type']=='transcript' and t['turn']['speaker']=='customer')
                while time.monotonic()<deadline:
                    logs=(await client.get('/api/logs/'+cid)).json()
                    if any(r['step']=='turn_committed' and r['turn_no']==customer_no for r in logs): break
                    await asyncio.sleep(.5)
                else: failure='Final turn did not commit before evaluation timeout'
        except Exception as exc: failure=type(exc).__name__
        finally:
            await client.post('/calls/'+cid+'/end')
            try: await asyncio.wait_for(completed.wait(),3)
            except asyncio.TimeoutError: pass
            collector.cancel();await asyncio.gather(collector,return_exceptions=True)
        logs_response=await client.get('/api/logs/'+cid);logs_response.raise_for_status()
        metadata={'type':'run_metadata','scenario':scenario,'call_id':cid,'variant':health['variant'],'failure':failure,'audio_path':'/ws/audio'}
        output.write_text('\n'.join(json.dumps(x) for x in [metadata,*events])+'\n')
        output.with_suffix('.trace.jsonl').write_text('\n'.join(json.dumps(x) for x in logs_response.json())+'\n')
        if failure: raise RuntimeError(f'{failure}; incomplete run saved to {output}')
        return output

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--scenario',default='S1',choices=['S1','S2','S3','S4','S5'])
    parser.add_argument('--url',default='http://127.0.0.1:8000');parser.add_argument('--output')
    parser.add_argument('--grace',type=float,default=120)
    parser.add_argument('--dry-transcript',action='store_true',help='Replay audio normally; print only transcript events afterward (requires real recordings).')
    args=parser.parse_args()
    try:
        path=asyncio.run(replay(args.scenario,args.url,args.output,args.grace))
        if args.dry_transcript:
            for line in path.read_text().splitlines():
                row=json.loads(line)
                if row['type']=='transcript': print(row['turn']['speaker'],row['turn']['text'])
        else: print(path)
    except (OSError,RuntimeError,httpx.HTTPError) as exc: parser.exit(1,'Replay failed: '+str(exc)+'\n')
if __name__=='__main__': main()
