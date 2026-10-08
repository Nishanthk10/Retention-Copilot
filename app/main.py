import asyncio
from contextlib import asynccontextmanager
from urllib.parse import urlparse
import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from app.config import Settings, ROOT
from app.logger import AuditLog, valid_id
from app.kb.search import KnowledgeBase
from app.stt.streaming import Transcriber
from app.providers.router import ProviderRouter
from app.graph.runner import Runtime
from app.call_list import list_calls
from app.ws import router, live

@asynccontextmanager
async def lifespan(app):
    settings=Settings(); app.state.settings=settings; app.state.runtime=None
    app.state.ready=False; app.state.error=None
    async with AsyncSqliteSaver.from_conn_string(str(settings.data_dir/'checkpoints.db')) as saver:
        async def initialise():
            try:
                kb=await asyncio.to_thread(KnowledgeBase,ROOT/'kb/offers',settings.test_mode,settings.offline)
                stt=None if settings.test_mode else await asyncio.to_thread(Transcriber,settings.offline)
                audit=AuditLog(settings.log_dir,[settings.groq_key,settings.gemini_key])
                rt=Runtime(settings,kb,stt,ProviderRouter(settings,audit),audit,saver)
                await rt.restore(); app.state.runtime=rt; app.state.ready=True
            except Exception as exc: app.state.error=type(exc).__name__
        task=asyncio.create_task(initialise())
        yield
        task.cancel(); await asyncio.gather(task,return_exceptions=True)
        if app.state.runtime: await app.state.runtime.close()

app=FastAPI(title='Retention Copilot',lifespan=lifespan)

@app.middleware('http')
async def local_boundary(request:Request,call_next):
    origin=request.headers.get('origin')
    if request.method in {'POST','PUT','DELETE'} and origin and urlparse(origin).netloc!=request.headers.get('host'):
        return JSONResponse({'detail':'Cross-origin action rejected'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='same-origin'
    return response

def runtime():
    if not app.state.ready: raise HTTPException(503,'Starting up or local models unavailable')
    return app.state.runtime

@app.get('/health')
async def health():
    s=app.state.settings
    return {'status':'ok' if app.state.ready else 'starting' if not app.state.error else 'error','ready':app.state.ready,'error':app.state.error,'test_mode':s.test_mode,'variant':s.variant}

@app.post('/calls')
async def start_call():
    rt=runtime()
    try: cid=rt.create()
    except ValueError as exc: raise HTTPException(409,str(exc))
    return {'call_id':cid,'status':'live'}

@app.get('/api/active-call')
async def active_call():
    rt=runtime()
    return next((rt.snapshot(cid) for cid,c in rt.calls.items() if c['status']=='live'),None)

@app.post('/calls/{cid}/end')
async def end_call(cid:str):
    rt=runtime(); live(rt,cid)
    return await rt.end(cid)

@app.get('/api/scenarios')
async def scenarios():
    from evals.check_recordings import check
    result=[]
    for path in sorted((ROOT/'evals/scenarios').glob('*.yaml')):
        scenario=yaml.safe_load(path.read_text()); folder=ROOT/'evals/recordings'/scenario['id']
        try: check(scenario['id']);recorded=True
        except (OSError,ValueError,KeyError): recorded=False
        result.append({'id':scenario['id'],'title':scenario['title'],'recorded':recorded})
    return result

@app.get('/api/calls')
async def get_calls():
    rt=runtime(); live_ids={cid for cid,c in rt.calls.items() if c['status']=='live'}
    return await asyncio.to_thread(list_calls,rt.audit,rt.settings.data_dir/'calls.db',live_ids)

@app.get('/api/logs/{cid}')
async def get_log(cid:str):
    try: valid_id(cid); return runtime().audit.read(cid)
    except (ValueError,FileNotFoundError): raise HTTPException(404,'Log not found for this call')

@app.get('/logs')
async def logs_list_page(): return FileResponse(ROOT/'web/logs.html')

@app.get('/logs/{cid}')
async def logs_page(cid:str):
    try: valid_id(cid)
    except ValueError: raise HTTPException(404,'Log not found for this call')
    return FileResponse(ROOT/'web/logs.html')

@app.get('/')
async def index(): return FileResponse(ROOT/'web/index.html')

app.include_router(router)
app.mount('/static',StaticFiles(directory=ROOT/'web'),name='static')
app.mount('/recordings',StaticFiles(directory=ROOT/'evals/recordings'),name='recordings')
