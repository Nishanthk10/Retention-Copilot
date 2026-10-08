"""Validate real recorded inputs. Missing recordings are errors, never fabricated."""
import json,wave
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]

def check(sid):
    script=yaml.safe_load((ROOT/'evals/scenarios'/f'{sid}.yaml').read_text())
    folder=ROOT/'evals/recordings'/sid
    timeline=json.loads((folder/'timing.json').read_text())
    items=timeline['utterances']
    if len(items)!=len(script['turns']): raise ValueError('Utterance count differs from script')
    for index,(item,turn) in enumerate(zip(items,script['turns']),1):
        if item['role']!=turn['speaker']: raise ValueError('Role differs from script')
        if Path(item['file']).name!=item['file'] or not item['file'].endswith('.wav'): raise ValueError('Invalid WAV filename')
        if not isinstance(item['gap_before_s'],(int,float)) or item['gap_before_s']<0: raise ValueError('Invalid gap')
        with wave.open(str(folder/item['file']),'rb') as wav:
            if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(1,2,16000): raise ValueError('Expected 16 kHz mono PCM16')
            if wav.getnframes()<1600: raise ValueError('Recording is empty or too short')
    for key in ['trigger_turn','decision_turn','expected_offer_id','behaviour']:
        if key not in script['labels']: raise ValueError('Missing label '+key)
    return timeline

def main():
    failures=0
    for sid in ['S1','S2','S3','S4','S5']:
        try: check(sid);print(sid,'READY')
        except (OSError,ValueError,KeyError) as exc: failures+=1;print(sid,'NOT READY:',type(exc).__name__)
    return int(bool(failures))
if __name__=='__main__': raise SystemExit(main())
