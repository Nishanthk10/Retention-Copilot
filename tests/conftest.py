from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace
import pytest
from app.logger import AuditLog
from app.kb.search import KnowledgeBase
from app.config import ROOT

@pytest.fixture
def cid(): return str(uuid4())
@pytest.fixture
def audit(tmp_path): return AuditLog(tmp_path,['test-secret-value'])
@pytest.fixture
def kb(): return KnowledgeBase(ROOT/'kb/offers',test_mode=True)
@pytest.fixture
def settings(tmp_path):
    return SimpleNamespace(data_dir=tmp_path,log_dir=tmp_path,variant='full',test_mode=True,eval_mode=False,prompt_guard=False,features={'permission':True,'summariser':True,'guardrails':True,'retries':True,'fastlane':True,'naive':False},only_provider='',groq_key='',gemini_key='',ollama_url='http://localhost:11434',ollama_model='qwen3:8b',gemini_model='gemini-2.5-flash')
