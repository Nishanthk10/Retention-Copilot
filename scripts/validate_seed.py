from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import yaml
from app.kb.loader import load_offers
from app.config import ROOT
offers=load_offers(ROOT/'kb/offers')
for path in (ROOT/'evals/scenarios').glob('*.yaml'):
    scenario=yaml.safe_load(path.read_text())
    assert scenario['labels']['expected_offer_id'] in offers
    assert [t['turn_no'] for t in scenario['turns']]==list(range(1,len(scenario['turns'])+1))
print(f'{len(offers)} offers and 5 scenario scripts validated.')
