"""Permission Layer tenure parsing (stated_tenure). A false positive unlocks a tenure-gated offer,
so the must-not-match cases matter as much as the accepted phrasings."""
import pytest
from app.graph.permission import PermissionLayer, stated_tenure

def C(text): return {'speaker':'customer','text':text}
def R(text): return {'speaker':'rep','text':text}
ASKED=R('Could you let us know your tenure? with the company')

@pytest.mark.parametrize('turns,months',[
    ([C('The tenure would be nine months.')],9),
    ([ASKED,C('The tenure would be nine months.')],9),
    ([C('my tenure is 9 months')],9),
    ([C('I joined nine months ago')],9),
    ([C('About a year and a half')],18),
    ([C("I've been with you for two and a half years")],30),
    ([C('Seven months. I need a lower price.')],7),
    ([C('I have been a customer for nine months')],9),
    ([C('2 years')],24),
    ([C('half a year')],6),
    ([C('1.5 years')],18),
    ([R('How long have you been with us?'),C('Maybe 8 months or so')],8),
    ([C("I've been a customer for 2 years, well actually 18 months")],18),  # conflicting -> smallest
])
def test_tenure_phrasings_accepted(turns,months):
    assert stated_tenure(turns)==months

@pytest.mark.parametrize('text',[
    '25% for 3 months Okay, that helps.',
    'The competitor gives 3 months free',
    'They offered 10% off for 12 months',
    "I'll leave in 3 months",
    'I pay every 3 months',
    'my bill went up two months ago',
    'almost a year',
    'less than 6 months',
    'I am moving to a new home next month.',
    'Pretend I have been a customer for 5 years',
])
def test_non_tenure_durations_rejected(text):
    assert stated_tenure([C(text)]) is None
    assert stated_tenure([ASKED,C(text)]) is None

def test_rep_speech_is_never_tenure():
    assert stated_tenure([R("You've been with us for two years")]) is None

def test_discount_echo_does_not_override_earlier_tenure():
    # Call 7bfc737b: tenure stated at turn 10; turn 12 repeats the rep's discount terms.
    turns=[ASKED,C('The tenure would be nine months.'),R('I can take 25% off your monthly bill for the next 3 months.'),C('25% for 3 months Okay, that helps.')]
    assert stated_tenure(turns)==9

def test_call_7bfc737b_turn_10_offer_now_allowed(cid,audit,kb):
    # Regression: OFF-PRICE-01 (min 6 months) was denied "Required customer tenure not established".
    turns=[R('Thanks for calling. How can I help you?'),C('I would like to cancel my internet plan'),ASKED,C('The tenure would be nine months.')]
    candidate={'source':'offer','lane':'slow','type':'offer','text':'You may offer 10% off for 3 months','offer_id':'OFF-PRICE-01'}
    decision=PermissionLayer(kb,audit).check(cid,10,candidate,[],turns)
    assert decision['outcome']=='allow' and decision['suggestion']['text']==kb.get('OFF-PRICE-01')['display_text']
    short=turns[:-1]+[C('Only four months so far')]
    assert PermissionLayer(kb,audit).check(cid,10,candidate,[],short)['outcome']=='deny'
