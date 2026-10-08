import re
from uuid import uuid4
from app.masking import mask_pii

COMMERCIAL=re.compile(r'[$£€₹%]|\b(?:\d+|one|two|three|ten|twenty|hundred)\s*(?:percent|dollars?|rupees?|pounds?)\b|\b(?:offer|off|discount|waiv\w*|refund\w*|credit|free|complimentary|guarantee\w*|promise\w*|price|saving\w*|cheaper|match|pay|payment|rate|fee|cost|compensat\w*|reimburse\w*)\b|\b(?:we|I|you)\s+(?:will|can)\s+(?:give|provide|reduce|fix|resolve|apply|cancel|upgrade|extend)\b',re.I)

def stated_tenure(turns):
    words={'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12}
    for turn in reversed(turns):
        if turn['speaker']!='customer': continue
        text=turn['text'].lower()
        if re.search(r'ignore|system message|pretend|suppose|what if',text): continue
        m=re.search(r"(?:^|been.{0,25}|customer.{0,20}|for\s+)(\d{1,3}|"+'|'.join(words)+r")\s+(months?|years?)\b",text)
        if m:
            raw=m.group(1); value=int(raw) if raw.isdigit() else words[raw]
            return value*(12 if m.group(2).startswith('year') else 1)
    return None

class PermissionLayer:
    def __init__(self,kb,audit): self.kb=kb; self.audit=audit
    def check(self,call_id,turn_no,suggestion,displayed,turns):
        sid=str(uuid4()); outcome='allow'; reason='Validated guidance'; removed=''
        safe=dict(suggestion,suggestion_id=sid,call_id=call_id,turn_no=turn_no)
        try:
            safe['text']=mask_pii(self.audit.clean(str(safe.get('text',''))))[0][:500]
            source=safe['source']; oid=safe.get('offer_id')
            if source in {'behaviour','fastlane'}:
                pieces=re.split(r'(?<=[.!?])\s+|\s+and\s+|;\s*',safe['text'])
                removed=' '.join(s for s in pieces if COMMERCIAL.search(s))
                safe['text']=' '.join(s for s in pieces if not COMMERCIAL.search(s)).strip()
                safe['offer_id']=None
                if removed or oid:
                    outcome='mask'; reason='Removed commercial terms from behavioural guidance'
            elif oid:
                offer=self.kb.get(oid)
                if not offer: outcome='deny'; reason='Unknown offer_id'
                else:
                    minimum=offer['eligibility'].get('min_tenure_months',0)
                    tenure=stated_tenure(turns)
                    if minimum and (tenure is None or tenure<minimum):
                        outcome='deny'; reason='Required customer tenure not established'
                    else:
                        # ID validity alone is insufficient. Render exact approved policy wording.
                        safe['text']=offer['display_text']; safe['type']='offer'
                        reason='Canonical KB terms; tenure rule satisfied'
            elif safe.get('type')=='offer' or COMMERCIAL.search(safe['text']):
                outcome='deny'; reason='Commercial claim without a KB offer'
            if not safe['text']: outcome='deny'; reason='No safe content remains'
            if any(x['text'].casefold()==safe['text'].casefold() for x in displayed):
                outcome='deny'; reason='Duplicate currently displayed suggestion'
            record=self.audit.write(call_id,turn_no,'permission',suggestion_id=sid,permission_outcome=outcome,reason=reason,removed_text=removed,candidate=suggestion,approved=safe if outcome!='deny' else None)
            return {'outcome':outcome,'suggestion':safe if outcome!='deny' else None,'record':record,'error':False}
        except Exception as exc:
            # Even audit failure must fail closed.
            try: self.audit.write(call_id,turn_no,'permission_error',permission_outcome='deny',reason=type(exc).__name__,suggestion_id=sid)
            except Exception: pass
            return {'outcome':'deny','suggestion':None,'record':None,'error':True}
