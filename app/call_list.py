"""Call Log List data for GET /api/calls. Read-only: never writes logs or calls.db.
Counts come from the masked, key-redacted log files (INV-01, INV-03); status and created_at come
from calls.db. The checkpoint column is never read."""
import sqlite3
from datetime import datetime, timezone
from app.logger import valid_id

def call_rows(db_path):
    if not db_path.exists(): return {}
    # DATA_DIR may be relative (.env default "data"); file URIs need an absolute path.
    db=sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro',uri=True)
    try: return {cid:(status,created_at) for cid,status,created_at in db.execute('SELECT call_id,status,created_at FROM calls')}
    finally: db.close()

def summarise(cid,records,row,live_ids):
    by_step={}
    for r in records: by_step.setdefault(r['step'],[]).append(r)
    ended=by_step.get('call_ended',[None])[-1]
    if row:
        status,created_at=row
        started_at=datetime.fromtimestamp(created_at,timezone.utc).isoformat()
        if status=='live': status='live' if cid in live_ids else 'interrupted'
    else:
        status='ended' if ended else 'interrupted'
        started_at=(by_step.get('call_started') or records or [{'ts':None}])[0]['ts']
    return {'call_id':cid,'started_at':started_at,
            'ended_at':ended['ts'] if ended and status=='ended' else None,'status':status,
            'suggestions_shown':len(by_step.get('emit',[])),
            'mask_deny_count':sum(r.get('permission_outcome') in ('mask','deny') for r in records)}

def list_calls(audit,db_path,live_ids):
    """Every call that has a log file, newest first."""
    rows=call_rows(db_path); calls=[]
    for path in audit.directory.glob('*.jsonl'):
        try: cid=valid_id(path.stem); records=audit.read(cid)
        except ValueError: continue  # not a call log, or a corrupt line; the viewer reports it
        calls.append(summarise(cid,records,rows.get(cid),live_ids))
    return sorted(calls,key=lambda c:c['started_at'] or '',reverse=True)
