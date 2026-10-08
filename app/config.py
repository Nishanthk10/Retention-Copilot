from dataclasses import dataclass, field
from pathlib import Path
import os
import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')
def flag(name): return os.getenv(name, 'false').lower() == 'true'

@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv('DATA_DIR', ROOT / 'data')))
    log_dir: Path = field(default_factory=lambda: Path(os.getenv('LOG_DIR', ROOT / 'logs')))
    groq_key: str = field(default_factory=lambda: os.getenv('GROQ_API_KEY', ''), repr=False)
    gemini_key: str = field(default_factory=lambda: os.getenv('GEMINI_API_KEY', ''), repr=False)
    ollama_url: str = field(default_factory=lambda: os.getenv('OLLAMA_URL', 'http://localhost:11434'))
    ollama_model: str = field(default_factory=lambda: os.getenv('OLLAMA_MODEL', 'qwen3:8b'))
    gemini_model: str = field(default_factory=lambda: os.getenv('GEMINI_MODEL', 'gemini-2.5-flash'))
    test_mode: bool = field(default_factory=lambda: flag('TEST_MODE'))
    offline: bool = field(default_factory=lambda: flag('MODEL_OFFLINE'))
    prompt_guard: bool = field(default_factory=lambda: flag('PROMPT_GUARD_ENABLED'))
    prompt_guard_threshold: float = field(default_factory=lambda: float(os.getenv('PROMPT_GUARD_THRESHOLD', '0.5')))
    eval_mode: bool = field(default_factory=lambda: flag('EVAL_MODE'))
    variant: str = field(default_factory=lambda: os.getenv('EVAL_CONFIG', 'full'))
    only_provider: str = field(default_factory=lambda: os.getenv('MODEL_PROVIDER', ''))
    def __post_init__(self):
        if not 0 <= self.prompt_guard_threshold <= 1: raise ValueError('PROMPT_GUARD_THRESHOLD must be between 0 and 1')
        if self.variant not in {'full','naive','no_permission','no_summariser_guardrails','no_retries'}:
            raise ValueError('Unknown evaluation variant')
        if self.variant != 'full' and not self.eval_mode:
            raise ValueError('Ablations require EVAL_MODE=true and a separate local process')
        self.features = yaml.safe_load((ROOT/'evals/configs'/f'{self.variant}.yaml').read_text())
        if self.features.get('pii_masking') is not True: raise ValueError('PII masking cannot be disabled')
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
