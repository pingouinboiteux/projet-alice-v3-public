"""Model migration contracts: native template, input budget and source identity."""
import copy
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from model_profile import relative_path,template_settings
from source_references import bind_references
from test_memory_inference_contract import session_stub

def test_gemma_generation_and_count_use_same_non_thinking_template():
    session,requests=session_stub()
    session.model_spec={'family':'gemma4','expose_schema':True}
    original=[{'role':'system','content':'Consigne de confiance'},{'role':'user','content':'Question fictive'}]
    saved=copy.deepcopy(original)
    schema={'type':'object','properties':{'reply':{'type':'string'}},'required':['reply']}
    session.ask_memory(original,schema)
    rendered=next(body for path,body in requests if path=='/apply-template')
    generated=next(body for path,body in requests if path=='/v1/chat/completions')
    assert rendered['messages']==generated['messages']
    assert rendered['chat_template_kwargs']==generated['chat_template_kwargs']=={'enable_thinking':False}
    assert 'reasoning_effort' not in generated
    assert json.dumps(schema,ensure_ascii=False,separators=(',',':')) in generated['messages'][0]['content']
    assert original==saved

def test_schema_exposure_cannot_bypass_the_input_guard():
    session,requests=session_stub(5501);session.model_spec={'family':'gemma4','expose_schema':True}
    with pytest.raises(RuntimeError):session.ask([{'role':'user','content':'Fictif'}],{'type':'object'})
    assert not any(path=='/v1/chat/completions' for path,body in requests)

def test_source_contracts_exclude_unknown_ids_without_mutating_shared_schema():
    schema={'type':'object','properties':{'evidence_ids':{'type':'array','items':{'type':'string'}}}}
    bound=bind_references(schema,'evidence_ids',['validation_a','validation_b'])
    assert bound['properties']['evidence_ids']['items']['enum']==['validation_a','validation_b']
    empty=bind_references(schema,'evidence_ids',[])
    assert empty['properties']['evidence_ids']['maxItems']==0
    assert 'enum' not in schema['properties']['evidence_ids']['items']
    assert 'maxItems' not in schema['properties']['evidence_ids']

@pytest.mark.parametrize('path',['../Alice','C:/elsewhere/model.gguf','models/../../outside'])
def test_resource_paths_cannot_escape_the_laboratory(path):
    with pytest.raises(ValueError):relative_path(path)

def test_unknown_model_family_is_rejected():
    with pytest.raises(ValueError):template_settings({'family':'unknown'})
