def assemble_context(turns, summary):
    last=int(summary.get('last_summarised_turn',0))
    first=min(next((i for i,t in enumerate(turns) if t['turn_no']>last),len(turns)),max(0,len(turns)-3))
    return {'summary':summary,'untrusted_turns':turns[first:]}
