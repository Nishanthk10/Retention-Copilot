import sys as _sys
from pathlib import Path as _Path
if __package__ in (None, ''): _sys.path.insert(0,str(_Path(__file__).resolve().parents[1]))
import argparse,asyncio,os,subprocess,sys,time
from pathlib import Path
import httpx
from evals.replay import replay,ROOT
from evals.score import score_file,report
from evals.check_recordings import check
VARIANTS=['naive','full','no_permission','no_summariser_guardrails','no_retries']

async def wait_ready(url,process,timeout=600):
    async with httpx.AsyncClient() as client:
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if process.poll() is not None: raise RuntimeError('Evaluation server exited; inspect server log')
            try:
                r=await client.get(url+'/health')
                if r.json().get('ready'): return
                if r.json().get('error'): raise RuntimeError('Model startup failed')
            except httpx.HTTPError: pass
            await asyncio.sleep(.5)
    raise RuntimeError('Model startup timed out')

async def run(args):
    scenarios=args.scenarios.split(',')
    for sid in scenarios: check(sid)
    variants=[Path(args.config).stem] if args.config else VARIANTS
    results=[];url=f'http://127.0.0.1:{args.port}'
    for variant in variants:
        directory=ROOT/'evals/reports'/variant;directory.mkdir(parents=True,exist_ok=True)
        env={**os.environ,'EVAL_MODE':'true','TEST_MODE':'false','EVAL_CONFIG':variant,'DATA_DIR':str(directory/'data'),'LOG_DIR':str(directory/'logs')}
        if args.model_provider: env['MODEL_PROVIDER']=args.model_provider
        with (directory/'server.log').open('w') as server_log:
            process=subprocess.Popen([sys.executable,'-m','uvicorn','app.main:app','--host','127.0.0.1','--port',str(args.port)],cwd=ROOT,env=env,stdout=server_log,stderr=server_log)
            try:
                await wait_ready(url,process)
                for sid in scenarios:
                    for index in range(args.runs):
                        path=await replay(sid,url,directory/f'{sid}-{index+1}.jsonl',grace=360)
                        results.append(score_file(path))
                        report(results,ROOT/'evals/reports/ablation_summary.md')
            finally:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill();process.wait()
    baseline=[r['success'] for r in results if r['variant']=='full']
    with (ROOT/'evals/reports/ablation_summary.md').open('a') as out:
        out.write('\n## Success-rate deltas versus full\n\n')
        for variant in variants:
            values=[r['success'] for r in results if r['variant']==variant]
            delta=sum(values)/len(values)-sum(baseline)/len(baseline) if baseline else None
            out.write(f"- {variant}: {delta if delta is not None else 'unavailable — full baseline not run'}\n")

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--config');parser.add_argument('--scenarios',default='S1,S2,S3,S4,S5');parser.add_argument('--runs',type=int,default=3);parser.add_argument('--model-provider',choices=['ollama','groq','gemini']);parser.add_argument('--port',type=int,default=8011)
    asyncio.run(run(parser.parse_args()))
