from app.kb.loader import load_offers

class KnowledgeBase:
    def __init__(self, directory, test_mode=False, offline=False):
        self.offers = load_offers(directory)
        self.items = list(self.offers.values())
        self.model = None; self.ready = False
        if not test_mode:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer('all-MiniLM-L6-v2',local_files_only=offline)
            self.vectors = self.encode([x['title']+' '+x['body']+' '+' '.join(x['reasons']) for x in self.items])
        self.ready = True
    def encode(self, texts):
        return self.model.encode(texts,normalize_embeddings=True)
    def get(self, offer_id): return self.offers.get(offer_id)
    def search(self, query, k=3, reasons=None):
        if self.model:
            scores = self.vectors @ self.encode([query])[0]
        else:
            words = set(query.lower().split())
            scores = [len(words & set((x['title']+' '+x['body']+' '+' '.join(x['reasons'])).lower().split())) for x in self.items]
        ranked = sorted(zip(scores,self.items),key=lambda x:float(x[0]),reverse=True)
        return [dict(x,score=float(s)) for s,x in ranked if not reasons or set(x['reasons']) & set(reasons)][:k]
