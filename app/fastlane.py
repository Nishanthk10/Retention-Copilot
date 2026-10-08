import re, yaml
from app.config import ROOT

class FastLane:
    def __init__(self, kb):
        self.kb = kb
        config = yaml.safe_load((ROOT/'config/fastlane.yaml').read_text())
        self.threshold=config['threshold']; self.tips=config['tips']
        self.vectors=kb.encode([t['example'] for t in self.tips]) if kb.model else None
    def suggest(self,text):
        tip = next((t for t in self.tips if any(re.search(r'\b'+re.escape(k)+r'\b',text,re.I) for k in t['keywords'])),None)
        if not tip and self.vectors is not None:
            scores=self.vectors @ self.kb.encode([text])[0]; i=int(scores.argmax())
            if float(scores[i])>=self.threshold: tip=self.tips[i]
        return dict(source='fastlane',lane='fast',type=tip['type'],text=tip['text'],offer_id=None) if tip else None
