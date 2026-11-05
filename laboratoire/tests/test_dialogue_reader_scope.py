"""Free dialogue length must never weaken the factual-reader boundary."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import pytest
from episode_protocol import READER,FACTUAL_STYLE,DIALOGUE_STYLE
from v5_context_memory import CarefulMemoryReader

@pytest.mark.parametrize('kind,route',[
    ('specific_fact','specific_fact'),('general_preference','general_preference'),
    ('general_discussion','general_discussion'),(None,'general')])
@pytest.mark.parametrize('has_source',[False,True])
def test_only_a_discussion_gets_free_length_with_or_without_an_archive(kind,route,has_source):
    source={'id':'validation_reading','date':'2026-01-01','messages':[{'role':'user','content':'Le carnet est bleu.'}]}
    sources=[source] if has_source else []
    store=SimpleNamespace(retrieve=lambda *a,**k:sources,version=lambda:1)
    fake=SimpleNamespace(ask=Mock(return_value=(json.dumps({'reply':'Texte','evidence_ids':[]}),0,{})),count_tokens=lambda _:1)
    with patch('episode_protocol._personal',return_value=([],{'requires_general_preference':False})),patch('episode_protocol.admit',return_value=([],{'route':route})):
        result=CarefulMemoryReader(fake,store,kind).answer('Demande de validation',system='validation_persona')
    content=fake.ask.call_args.args[0][0]['content']
    assert (DIALOGUE_STYLE in content)==(route in {'general','general_discussion'})
    assert (FACTUAL_STYLE in content)==(route not in {'general','general_discussion'})
    contract=fake.ask.call_args.kwargs['response_schema']
    assert ('phenomenon' in contract['required'])==(route in {'general','general_discussion'})
    assert result['decision']['route']==route

def test_factual_protocol_remains_exactly_the_previously_verified_one():
    original=Path(__file__).resolve().parents[1]/'rapports/initiative_diversite/avant/scripts/episode_protocol.py'
    node=next(n for n in ast.parse(original.read_text(encoding='utf-8')).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='READER' for t in n.targets))
    assert READER==ast.literal_eval(node.value)
