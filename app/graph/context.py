def assemble_context(turns, summary, displayed=()):
    last=int(summary.get('last_summarised_turn',0))
    first=min(next((i for i,t in enumerate(turns) if t['turn_no']>last),len(turns)),max(0,len(turns)-3))
    # Suggestions the rep can currently see, so agents do not repeat themselves.
    on_screen=[{k:d.get(k) for k in ('turn_no','source','type','offer_id','text')} for d in displayed]
    return {'summary':summary,'untrusted_turns':turns[first:],'on_screen':on_screen}
