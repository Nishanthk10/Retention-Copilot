import re
from uuid import uuid4
from app.masking import mask_pii

COMMERCIAL=re.compile(r'[$£€₹%]|\b(?:\d+|one|two|three|ten|twenty|hundred)\s*(?:percent|dollars?|rupees?|pounds?)\b|\b(?:offer|off|discount|waiv\w*|refund\w*|credit|free|complimentary|guarantee\w*|promise\w*|price|saving\w*|cheaper|match|pay|payment|rate|fee|cost|compensat\w*|reimburse\w*)\b|\b(?:we|I|you)\s+(?:will|can)\s+(?:give|provide|reduce|fix|resolve|apply|cancel|upgrade|extend)\b',re.I)

# Deterministic tenure parsing over raw customer speech. Never reads the LLM summary: a poisoned
# summary must not unlock tenure-gated offers. A false positive unlocks an offer, so ambiguous or
# promotional durations are rejected; a miss only denies (fail closed).
WORDS={'a':1,'an':1,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,
       'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20}
DURATION=re.compile(r"\b(?:(?P<half_year>half an? year)|(?P<num>\d{1,3}(?:\.\d+)?|"+'|'.join(sorted(WORDS,key=len,reverse=True))+
    r")(?P<half_before> and an? half)?[\s-]*(?P<unit>months?|mos?|years?|yrs?)\b(?P<half_after> and an? half)?)")
# Within ~30 characters before the duration, in the same sentence.
CUE=re.compile(r"\b(?:tenure|customer|member|with (?:you|us|the company|your company|them)|been|joined|signed up|subscribed|started|for)\b[^.!?]{0,30}$")
START=re.compile(r"^\W*(?:about|around|roughly|approximately|maybe|over|more than|at least|just over)?\s*$")
UPPER_BOUND=re.compile(r"\b(?:less than|under|almost|nearly|not even|not quite|barely|just under)\s*$")
FUTURE_OR_RATE=re.compile(r"\b(?:in|within|next|after|another|every|per|each)\s*$")
PROMO_BEFORE=re.compile(r"(?:%|\b(?:off|discount|free|deal|offer|promo|price|bill|pay|paying|cheaper|credit|refund)\b)[^.!?]{0,25}$")
PROMO_AFTER=re.compile(r"^\s*(?:free|off|discount|trial|contract|promo|notice|at\b|of free)")
START_VERB=re.compile(r"\b(?:joined|signed up|started|subscribed|switched|became|moved to you)\b")
ASKED=re.compile(r"tenure|how long|how many (?:months|years)|been (?:with|a customer)|when did you (?:join|sign up|start)")
HYPOTHETICAL=re.compile(r'ignore|system message|pretend|suppose|what if')

def durations(text,answering):
    """Tenure values (months, floored) stated in one customer turn."""
    found=[]
    for m in DURATION.finditer(text):
        before,after=text[:m.start()],text[m.end():]
        if UPPER_BOUND.search(before) or FUTURE_OR_RATE.search(before) or PROMO_BEFORE.search(before) or PROMO_AFTER.search(after): continue
        if after.lstrip().startswith('ago') and not START_VERB.search(before): continue
        if not (answering or CUE.search(before) or START.match(before)): continue
        if m.group('half_year'): value=6.0
        else:
            raw=m.group('num'); value=float(raw) if raw[0].isdigit() else float(WORDS[raw])
            if m.group('half_before') or m.group('half_after'): value+=0.5
            if m.group('unit').startswith('y'): value*=12
        found.append(int(value))
    return found

def stated_tenure(turns):
    """Most recent customer statement of tenure in months, or None. Conflicting values in one turn
    resolve to the smallest (conservative)."""
    for index in range(len(turns)-1,-1,-1):
        turn=turns[index]
        if turn['speaker']!='customer': continue
        text=turn['text'].lower()
        if HYPOTHETICAL.search(text): continue
        rep=next((t['text'].lower() for t in reversed(turns[:index]) if t['speaker']=='rep'),'')
        found=durations(text,bool(ASKED.search(rep)))
        if found: return min(found)
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
