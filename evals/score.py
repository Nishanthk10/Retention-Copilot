import argparse,json,re,statistics
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]

def words(text): return re.findall(r"\w+",text.lower())
def wer(reference,hypothesis):
    ref=words(reference);hyp=words(hypothesis);row=list(range(len(hyp)+1))
    for i,a in enumerate(ref,1):
        new=[i]
        for j,b in enumerate(hyp,1): new.append(min(new[-1]+1,row[j]+1,row[j-1]+(a!=b)))
        row=new
    return row[-1]/max(1,len(ref))

def score(events,trace,scenario,kb_ids):
    labels=scenario['labels'];expected=labels['expected_offer_id'];trigger=labels['trigger_turn']
    shown=[e['shown'] for e in trace if e.get('step')=='emit' and e.get('shown')]
    matching=[s for s in shown if s.get('offer_id')==expected and s['turn_no']>=trigger] if expected else []
    timing=min((s['turn_no']-trigger for s in matching),default=None)
    success=timing is not None and timing<=4 if expected else not any(s.get('offer_id') for s in shown)
    summaries=[r['summary'] for r in trace if r.get('step')=='summary_saved']
    hypotheses=' '.join(e['turn']['text'] for e in events if e.get('type')=='transcript')
    reference=' '.join(t['text'] for t in scenario['turns'])
    retrieval=[item for r in trace for tool in r.get('tool_calls') or [] for item in tool.get('result',[]) if isinstance(item,dict)]
    behaviours=[]
    for no,types in labels['behaviour'].items():
        behaviours.extend(any(s['turn_no']==int(no) and s['type']==kind for s in shown) for kind in types)
    sequence=[s['offer_id'] for s in shown if s.get('offer_id')]
    flip_flops=sum(sequence[i]==sequence[i-2] and sequence[i]!=sequence[i-1] for i in range(2,len(sequence)))
    counts={str(t['turn_no']):sum(s['turn_no']==t['turn_no'] for s in shown) for t in scenario['turns']}
    return {'scenario':scenario['id'],'success':bool(success),'turns_to_offer':timing,'non_kb_offers':sum(s.get('offer_id') not in kb_ids for s in shown if s.get('offer_id')),'unattributed_offer_items':sum(s.get('type')=='offer' and not s.get('offer_id') for s in shown),'flip_flops':flip_flops,'suggestions_per_turn':counts,'wer':wer(reference,hypotheses),'reason_accuracy':(sum(s.get('primary_reason')==scenario['primary_reason'] for s in summaries)/len(summaries)) if summaries else None,'kb_hit':any(x.get('offer_id')==expected for x in retrieval),'behaviour_match':sum(behaviours)/len(behaviours) if behaviours else None}

def score_file(path):
    events=[json.loads(x) for x in Path(path).read_text().splitlines()]
    meta=events[0];scenario=yaml.safe_load((ROOT/'evals/scenarios'/f"{meta['scenario']}.yaml").read_text())
    trace=[json.loads(x) for x in Path(path).with_suffix('.trace.jsonl').read_text().splitlines()]
    kb_ids={yaml.safe_load(p.read_text().split('---')[1])['offer_id'] for p in (ROOT/'kb/offers').glob('*.md')}
    result=score(events,trace,scenario,kb_ids);result['variant']=meta['variant'];result['incomplete']=bool(meta.get('failure'));result['file']=str(path)
    if result['incomplete']: result['success']=False
    return result

def report(results,path):
    lines=['# Audio evaluation results','','Only actual recorded WebSocket runs are included. Lower WER is better. Missing component evidence remains unavailable.','','| Scenario / variant | Runs | Success | Success spread | Worst success | Mean WER | Worst WER | Non-KB IDs |','|---|---:|---:|---:|---:|---:|---:|---:|']
    for key in sorted({(r['scenario'],r['variant']) for r in results}):
        rows=[r for r in results if (r['scenario'],r['variant'])==key];values=[int(r['success']) for r in rows]
        lines.append(f"| {' / '.join(key)} | {len(rows)} | {statistics.mean(values):.0%} | {max(values)-min(values)} | {min(values)} | {statistics.mean(r['wer'] for r in rows):.3f} | {max(r['wer'] for r in rows):.3f} | {sum(r['non_kb_offers'] for r in rows)} |")
    lines+=['','## Per-run trajectory and component evidence','','See the companion JSON for time-to-offer, flip-flops, per-turn suggestion counts, reason accuracy, retrieval hit and behaviour type-match. These are mechanical metrics, not a general proof of offer safety.']
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);path.write_text('\n'.join(lines)+'\n');path.with_suffix('.json').write_text(json.dumps(results,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('runs',nargs='+');parser.add_argument('--output',default='evals/reports/eval_report.md');args=parser.parse_args()
    report([score_file(p) for p in args.runs],args.output)
