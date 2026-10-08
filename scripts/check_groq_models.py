"""Check that every Groq model in config/providers.yaml, plus Prompt Guard, is listed by Groq.

Usage: python scripts/check_groq_models.py   (reads GROQ_API_KEY from the environment or .env)
Exit code 0 if all are listed, 1 if any is missing, 2 if the check could not run.
The key is never printed (INV-03); errors report only the HTTP status or exception type.
"""
import os, sys
from pathlib import Path
import httpx, yaml
from dotenv import load_dotenv

ROOT=Path(__file__).resolve().parents[1]
PROMPT_GUARD='meta-llama/llama-prompt-guard-2-86m'

def configured_groq_models():
    chains=yaml.safe_load((ROOT/'config/providers.yaml').read_text(encoding='utf-8'))
    models=[]
    for entries in chains.values():
        for entry in entries:
            provider,_,model=str(entry).partition(':')
            if provider=='groq' and model not in models: models.append(model)
    return models+[PROMPT_GUARD]

def main():
    load_dotenv(ROOT/'.env')
    key=os.getenv('GROQ_API_KEY','')
    if not key: print('GROQ_API_KEY is not set'); return 2
    try: r=httpx.get('https://api.groq.com/openai/v1/models',headers={'Authorization':'Bearer '+key},timeout=15)
    except httpx.HTTPError as exc: print(f'Request failed: {type(exc).__name__}'); return 2
    if r.status_code!=200: print(f'Groq returned HTTP {r.status_code}'); return 2
    listed={m['id'] for m in r.json().get('data',[])}
    missing=0
    for model in configured_groq_models():
        found=model in listed; missing+=not found
        print(f"{'OK     ' if found else 'MISSING'}  {model}")
    print(f'{len(listed)} models listed by Groq; {missing} configured model(s) missing.')
    return 1 if missing else 0

if __name__=='__main__': sys.exit(main())
