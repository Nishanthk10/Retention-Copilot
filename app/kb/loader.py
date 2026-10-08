from pathlib import Path
import yaml
REASONS = {'price','moving','not_using','competitor','service_issue'}

def load_offers(directory):
    offers = {}
    for path in sorted(Path(directory).glob('*.md')):
        _, header, body = path.read_text().split('---',2)
        item = yaml.safe_load(header)
        if item['offer_id'] in offers: raise ValueError('Duplicate offer_id')
        if not set(item['reasons']) <= REASONS: raise ValueError('Invalid reason')
        if not item.get('display_text') or not item.get('eligibility'): raise ValueError('Missing canonical text/rules')
        item['body'] = body.strip(); offers[item['offer_id']] = item
    if not offers: raise ValueError('Empty KB')
    return offers
