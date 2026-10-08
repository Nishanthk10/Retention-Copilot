import json, re
from dataclasses import dataclass
from .schema import Summary

INJECTION=re.compile(r'ignore.{0,30}(rules|instructions)|you must|system message|developer message|reveal.{0,20}prompt|override',re.I)
MONEY=re.compile(r'(?:[$£€₹]\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*%)')
def detect_injection(text): return ['instruction_attempt'] if INJECTION.search(text) else []

@dataclass(frozen=True)
class ValidationResult:
    value: dict
    passed: bool
    guardrails_enabled: bool

def validate_summary(value,kb,guardrails=True):
    if not guardrails: return ValidationResult(value,True,False)
    Summary.model_validate(value)
    for offer in value['offers_discussed']:
        if offer['offer_id'] not in kb: raise ValueError('Unknown offer_id')
    for req in value['customer_requests']:
        if not req['reported_speech'].lower().startswith(('customer requested','customer asked','customer wanted')):
            raise ValueError('Request must use reported speech')
    text=json.dumps(value)
    if INJECTION.search(text): raise ValueError('Instruction wording in summary')
    allowed=set(MONEY.findall(json.dumps(kb)))
    if set(MONEY.findall(text))-allowed: raise ValueError('Non-KB price in summary')
    return ValidationResult(value,True,True)
