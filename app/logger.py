import json, re, threading
from datetime import datetime, timezone
from uuid import UUID

def valid_id(call_id):
    if str(UUID(call_id)) != call_id: raise ValueError('Invalid call ID')
    return call_id

class AuditLog:
    def __init__(self, directory, secrets=()):
        self.directory = directory
        self.secrets = [s for s in secrets if s]
        self.lock = threading.Lock()
    def clean(self, value):
        text = json.dumps(value, ensure_ascii=False, default=str)
        for secret in self.secrets: text = text.replace(secret, '[SECRET]')
        text = re.sub(r'(?:gsk_|AIza)[A-Za-z0-9_-]{8,}', '[SECRET]', text)
        return json.loads(text)
    def write(self, call_id, turn_no, step, **fields):
        record = dict.fromkeys(['input','tool_calls','model_reasoning','retries','provider','tokens','cost','permission_outcome','shown'])
        record.update(fields)
        record.update(ts=datetime.now(timezone.utc).isoformat(),call_id=valid_id(call_id),turn_no=turn_no,step=step)
        record = self.clean(record)
        with self.lock, (self.directory/f'{call_id}.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps(record,ensure_ascii=False)+'\n'); f.flush()
        return record
    def read(self, call_id):
        path = self.directory/f'{valid_id(call_id)}.jsonl'
        with self.lock: return [json.loads(line) for line in path.read_text().splitlines()]
