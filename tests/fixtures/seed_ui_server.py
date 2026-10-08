"""Seed a fresh copy of the fixture logs and calls.db for the Playwright :8001 server.
Usage: python tests/fixtures/seed_ui_server.py <target_dir>  -> <target>/logs and <target>/data.
The server reads and writes only the copy, never tests/fixtures itself."""
import json, shutil, sqlite3, sys
from pathlib import Path

FIXTURES=Path(__file__).resolve().parent

def seed(target):
    shutil.rmtree(target,ignore_errors=True)
    shutil.copytree(FIXTURES/'logs',target/'logs')
    (target/'data').mkdir(parents=True)
    db=sqlite3.connect(target/'data'/'calls.db')
    with db:
        db.execute('CREATE TABLE calls(call_id TEXT PRIMARY KEY,status TEXT,checkpoint TEXT,created_at REAL)')
        db.executemany('INSERT INTO calls VALUES(?,?,NULL,?)',[(c['call_id'],c['status'],c['created_at']) for c in json.loads((FIXTURES/'calls.json').read_text())])
    db.close()

if __name__=='__main__': seed(Path(sys.argv[1]))
