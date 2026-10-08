"""Recorded-audio SIGKILL/restart experiment. No in-process graph shortcut."""
import sys as _sys
from pathlib import Path as _Path
if __package__ in (None, ''): _sys.path.insert(0,str(_Path(__file__).resolve().parents[1]))
import argparse,asyncio,json,os,subprocess,sys,time,wave
import httpx,websockets
from evals.check_recordings import check,ROOT
from evals.ablation import wait_ready

async def run(args):
    timeline=check(args.scenario)['utterances']
    if not 1<=args.kill_at_turn<len(timeline): raise ValueError('Kill turn must leave at least one utterance after restart')
    out=ROOT/'evals/reports/crash';out.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'EVAL_MODE':'false','EVAL_CONFIG':'full','TEST_MODE':'false','DATA_DIR':str(out/'data'),'LOG_DIR':str(out/'logs')}
    url=f'http://127.0.0.1:{args.port}';wsurl=url.replace('http:','ws:')
    server_log=(out/'server.log').open('w')
    def launch(): return subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(args.port)],cwd=ROOT,env=env,stdout=server_log,stderr=server_log)
    process=launch();socket=None
    try:
        await wait_ready(url,process)
        async with httpx.AsyncClient(base_url=url,timeout=15) as client:
            response=await client.post('/calls');response.raise_for_status();cid=response.json()['call_id']
            socket=await websockets.connect(wsurl+'/ws/audio?call_id='+cid)
            async def set_role(role):
                await socket.send(json.dumps({'type':'role','role':role}))
                return json.loads(await asyncio.wait_for(socket.recv(),90))
            before_commit=0;resume_turn=0
            for no,item in enumerate(timeline,1):
                await asyncio.sleep(item['gap_before_s']);await set_role(item['role'])
                with wave.open(str(ROOT/'evals/recordings'/args.scenario/item['file']),'rb') as wav:
                    while pcm:=wav.readframes(1600):
                        await socket.send(pcm);await asyncio.sleep(len(pcm)/32000)
                if no==args.kill_at_turn:
                    # Closing the turn starts customer graph, then kill while provider work is pending.
                    await set_role('none')
                    trace=(await client.get('/api/logs/'+cid)).json()
                    before_commit=max((r['turn_no'] for r in trace if r['step']=='turn_committed'),default=0)
                    process.kill();process.wait(timeout=10);await socket.close()
                    process=launch();await wait_ready(url,process)
                    active=(await client.get('/api/active-call')).json()
                    assert active['call_id']==cid,'Call identity changed'
                    resume_turn=max((t['turn_no'] for t in active['turns']),default=0)
                    assert resume_turn==before_commit,'Partial/uncommitted turn resumed'
                    socket=await websockets.connect(wsurl+'/ws/audio?call_id='+cid)
            await set_role('none')
            deadline=time.monotonic()+360
            while time.monotonic()<deadline:
                trace=(await client.get('/api/logs/'+cid)).json()
                if any(r['step']=='turn_committed' and r['turn_no']>args.kill_at_turn for r in trace): break
                await asyncio.sleep(1)
            await client.post('/calls/'+cid+'/end')
            trace=(await client.get('/api/logs/'+cid)).json()
            result={'same_call_id':cid,'last_commit_before_crash':before_commit,'restored_turn':resume_turn,'resume_marker':any(r['step']=='resume' for r in trace),'suggestions_after_resume':any(r['step']=='emit' and r['turn_no']>args.kill_at_turn for r in trace)}
            (ROOT/'evals/reports/crash_resume_result.md').write_text('# Recorded audio crash/resume evidence\n\n'+json.dumps(result,indent=2)+'\n')
            if not result['resume_marker'] or not result['suggestions_after_resume']: raise RuntimeError('Crash evidence incomplete; inspect report')
    finally:
        if socket: await socket.close()
        process.terminate()
        try: process.wait(timeout=10)
        except subprocess.TimeoutExpired: process.kill();process.wait()
        server_log.close()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--scenario',default='S5');parser.add_argument('--kill-at-turn',type=int,default=6);parser.add_argument('--port',type=int,default=8012)
    asyncio.run(run(parser.parse_args()))
