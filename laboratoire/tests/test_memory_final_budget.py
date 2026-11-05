"""Final schema-inclusive fitting keeps complete, ranked evidence."""
import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from episodic_memory import Reader


def sources():
    # Relevance and chronological order deliberately disagree.
    return [{'id':identity,'date':date,'messages':[{'role':'user','content':text}]}
        for identity,date,text in [
            ('validation_best','2026-03-01','Je ne mange jamais de noix.'),
            ('validation_second','2026-01-01','Ma tasse est verte.'),
            ('validation_last','2026-02-01','Mon velo est bleu.')]]


def payload(messages):
    return json.loads(messages[1]['content'].split(' : ',1)[1])


def setup_reader(archives, count, **options):
    def ask(messages,response_schema):
        ids=response_schema['properties']['evidence_ids']['items'].get('enum',[])
        return json.dumps({'reply':'Reponse mesuree.','evidence_ids':ids}),0,{}
    session=SimpleNamespace(ask=Mock(side_effect=ask),ask_memory=Mock(side_effect=ask),
        count_tokens=Mock(return_value=100),count_response_tokens=Mock(side_effect=count))
    episodes=SimpleNamespace(version=lambda:1,retrieve=lambda *a,**k:copy.deepcopy(archives))
    return Reader(session,episodes,**options),session


def test_schema_growth_drops_lowest_rank_not_latest_date_and_rebinds_references():
    archives=sources();before=copy.deepcopy(archives)
    def count(messages,schema):
        ids=schema['properties']['evidence_ids']['items'].get('enum',[])
        return 5501 if len(ids)>2 else 5500
    reader,session=setup_reader(archives,count,query_kind='specific_fact')
    result=reader.answer('Que sais-tu ?')
    messages=session.ask.call_args.args[0]
    shown=payload(messages)['archives']
    assert [s['id'] for s in shown]==['validation_second','validation_best']
    assert shown[-1]['messages']==before[0]['messages']
    assert result['admitted_ids']==['validation_second','validation_best']
    assert [s['id'] for s in result['sources']]==result['admitted_ids']
    assert result['budget_omitted_sources']==1 and archives==before
    assert session.ask.call_args.kwargs['response_schema']['properties']['evidence_ids']['items']['enum']==result['admitted_ids']
    session.ask.assert_called_once()


def test_final_fitting_counts_resolved_provenance_view_without_changing_sources():
    archives=sources();before=copy.deepcopy(archives)
    def resolve(session,view,question):
        result=copy.deepcopy(view)
        for source in result:source['provenance_marker']='expanded view'
        return result,{'called':True,'hidden_assistant_turns':0}
    def count(messages,schema):
        shown=payload(messages)['archives']
        assert all(s['provenance_marker']=='expanded view' for s in shown)
        return 5501 if len(shown)>1 else 100
    reader,session=setup_reader(archives,count,query_kind='specific_fact',memory_reasoning=True)
    with patch('memory_source_provenance.resolve',side_effect=resolve):
        result=reader.answer('Que sais-tu ?')
    assert result['admitted_ids']==['validation_best'] and result['budget_omitted_sources']==2
    assert payload(session.ask_memory.call_args.args[0])['archives'][0]['messages']==before[0]['messages']
    assert archives==before and 'provenance_marker' not in result['sources'][0]
    session.ask_memory.assert_called_once();session.ask.assert_not_called()


def test_context_removed_before_proof_by_rank_with_consistent_reading_metadata():
    archives=sources()
    def count(messages,schema):
        data=payload(messages)
        return 5501 if len(data['contexte_non_probant'])>0 else 100
    reader,session=setup_reader(archives,count,query_kind='general_preference')
    with patch('episode_protocol._personal',side_effect=lambda session,view,question:
            ([next(s for s in view if s['id']=='validation_last')],{'requires_general_preference':True})):
        result=reader.answer('Quelle preference ?')
    attempts=[payload(call.args[0]) for call in session.count_response_tokens.call_args_list]
    assert [s['id'] for s in attempts[-2]['contexte_non_probant']]==['validation_best']
    data=payload(session.ask.call_args.args[0])
    assert data['etat_lecture']=={'sources_selectionnees':3,'sources_admises':1,'contextes_omis_pour_budget':2}
    assert result['admitted_ids']==['validation_last'] and result['budget_omitted_sources']==2


def test_no_evidence_left_rebinds_empty_schema_and_changes_generation_route():
    def count(messages,schema):
        return 5501 if payload(messages)['archives'] else 100
    reader,session=setup_reader(sources(),count,query_kind='specific_fact',memory_reasoning=True)
    result=reader.answer('Que sais-tu ?')
    assert result['admitted_ids']==[] and result['sources']==[] and result['budget_omitted_sources']==3
    session.ask_memory.assert_not_called();session.ask.assert_called_once()
    assert session.ask.call_args.kwargs['response_schema']['properties']['evidence_ids']['maxItems']==0


def test_preference_proof_omissions_remain_distinct_from_consulted_sources():
    def count(messages,schema):
        return 5501 if len(payload(messages)['archives'])>1 else 100
    reader,session=setup_reader(sources(),count,query_kind='general_preference')
    with patch('episode_protocol._personal',side_effect=lambda session,view,question:
            (view,{'requires_general_preference':True})):
        result=reader.answer('Quelle preference ?')
    assert result['admitted_ids']==['validation_best']
    assert payload(session.ask.call_args.args[0])['etat_lecture']=={
        'sources_selectionnees':3,'sources_admises':1,
        'contextes_omis_pour_budget':0,'preuves_omises_pour_budget':2}


def test_omitted_source_cannot_be_cited_even_if_model_returns_it():
    reader,session=setup_reader(sources(),lambda messages,schema:
        5501 if len(payload(messages)['archives'])>1 else 100,query_kind='specific_fact')
    session.ask.side_effect=None
    session.ask.return_value=('{"reply":"Reponse","evidence_ids":["validation_last"]}',0,{})
    with pytest.raises(ValueError,match='unsupported source reference'):
        reader.answer('Question')


def test_unfittable_fixed_input_fails_without_generating_or_mutating_archives():
    archives=sources();before=copy.deepcopy(archives)
    reader,session=setup_reader(archives,lambda *args:5501,query_kind='specific_fact')
    with pytest.raises(ValueError,match='Final memory reply exceeds'):
        reader.answer('Question volumineuse')
    session.ask.assert_not_called();session.ask_memory.assert_not_called()
    assert archives==before


@pytest.mark.parametrize('measurement',[-1,True,None,1.5])
def test_invalid_final_measurement_cannot_authorize_generation(measurement):
    reader,session=setup_reader(sources(),lambda *args:measurement,query_kind='specific_fact')
    with pytest.raises(ValueError,match='Invalid final reply token measurement'):
        reader.answer('Question')
    session.ask.assert_not_called();session.ask_memory.assert_not_called()
