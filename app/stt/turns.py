from dataclasses import dataclass, asdict
from app.masking import mask_pii

@dataclass(frozen=True)
class Turn:
    call_id: str
    turn_no: int
    speaker: str
    text: str
    stt_start: float
    stt_end: float
    def as_dict(self): return asdict(self)

# All application Turn construction is confined to this boundary.
def close_turn(call_id, turn_no, speaker, raw_text, start, end, audit):
    text,counts = mask_pii(raw_text)
    if not text.strip(): return None
    turn=Turn(call_id,turn_no,speaker,text.strip(),start,end)
    audit.write(call_id,turn_no,'transcription',input=turn.as_dict(),mask_counts=counts,latency_ms=(end-start)*1000)
    return turn
