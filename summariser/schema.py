from pathlib import Path
from copy import deepcopy
import yaml, jsonschema
from pydantic import RootModel, model_validator

CONFIG = yaml.safe_load(Path(__file__).with_name('config.yaml').read_text())
SCHEMA = CONFIG['schema']

def default_summary(): return deepcopy(CONFIG['default'])

def word_limits(value, schema):
    if isinstance(value,str) and len(value.split())>schema.get('x-max-words',10**6):
        raise ValueError('Word limit exceeded')
    if isinstance(value,dict):
        for k,v in value.items(): word_limits(v,schema.get('properties',{}).get(k,{}))
    if isinstance(value,list):
        for item in value: word_limits(item,schema.get('items',{}))

class Summary(RootModel[dict]):
    @model_validator(mode='after')
    def check_config(self):
        jsonschema.validate(self.root,SCHEMA)
        word_limits(self.root,SCHEMA)
        return self
