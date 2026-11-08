"""Synthetic local requests; no browser, model process or personal data."""
import json
from unittest.mock import Mock
import pytest
from link_request import can_handle_link,is_link_followup,interpret_link

URL='https://example.org/page'
TEXT='Sur https://example.org/page, suis le lien "Tarifs" et dis-moi "Quel est le prix adulte ?"'
TARGET={'url':URL,'label':'Tarifs','question':'Quel est le prix adulte ?'}

def session(values=None):
    values=TARGET if values is None else values
    raw={'intent':'execute',**{k:{'turn':0,'quote':v} for k,v in values.items()}}
    s=Mock(ask=Mock(return_value=(json.dumps(raw),0,{})))
    s.decision_raw='{"decision":"execute"}'
    s.ask.side_effect=lambda *args,**kwargs: ((s.decision_raw,0,{})
        if 'decision' in kwargs['response_schema']['properties'] else s.ask.return_value)
    return s

@pytest.mark.parametrize('text',[
    TEXT,'Peux-tu suivre le lien Tarifs sur https://example.org/page pour savoir le prix adulte ?',
    'Alice, suis le lien Tarifs de https://example.org/page et trouve les horaires',
    'S il te plait clique le lien Tarifs sur https://example.org/page',
    '/suivre https://example.org/page | Tarifs | Prix ?',
])
def test_direct_candidate(text):assert can_handle_link(text)

@pytest.mark.parametrize('text',[
    'Par exemple '+TEXT, 'Il a dit '+TEXT, 'Si je dis '+TEXT,
    '"Suis le lien Tarifs"','Ne suis pas le lien Tarifs','Comment suivre le lien Tarifs ?',
    'Bonjour',None,'Suis le lien "Tarifs',
])
def test_nonrequest_not_candidate(text):assert not can_handle_link(text)

@pytest.mark.parametrize('text',[
    'Le lien est Tarifs','La question est Quel prix ?',"L adresse est https://example.org/",
    'Finalement le lien est Horaires','Remplace la question par Quel age ?', 'annule','stop',
])
def test_followups(text):assert is_link_followup(text)

@pytest.mark.parametrize('text',['Il a dit le lien est Tarifs','Bonjour','oui','"stop"'])
def test_unrelated_followup(text):assert not is_link_followup(text)

def test_grounded_request_and_exact_original_values():
    s=session();result=interpret_link(s,[TEXT],'voice')
    assert result['status']=='ready' and result['target']==TARGET
    assert result['sources']['label']['start']==TEXT.index('Tarifs')
    assert s.ask.call_count==2

def test_slash_command_does_not_need_model_or_rewrite():
    s=session();r=interpret_link(s,['/suivre '+URL+' | Tarifs | Quel est le prix adulte ?'],'text')
    assert r=={'status':'ready','target':TARGET};s.ask.assert_not_called()

@pytest.mark.parametrize('text',[
    '/suivre '+URL, '/suivre '+URL+' | Tarifs',
    '/suivre https://127.0.0.1/ | Tarifs | Prix ?',
    '/suivre '+URL+' | | Prix ?', '/suivre '+URL+' | Tarifs | Prix ? | autre',
])
def test_invalid_slash_command_never_ready(text):
    s=session();assert interpret_link(s,[text],'text')['status']=='clarify';s.ask.assert_not_called()

@pytest.mark.parametrize('source',['twitch','discord','system',None])
def test_only_local_sources(source):
    s=session();assert interpret_link(s,[TEXT],source)['status']=='clarify';s.ask.assert_not_called()

@pytest.mark.parametrize('raw',['null','{}','{"intent":"execute","intent":"discuss"}',
    '{"intent":"execute","url":{}}','not json'])
def test_invalid_model_response(raw):
    s=session();s.ask.return_value=(raw,0,{})
    assert interpret_link(s,[TEXT],'text')['status']=='clarify'

def test_invented_label_and_destination_are_refused():
    for key,new in [('label','Horaires'),('url','https://other.example/page')]:
        s=session({**TARGET,key:new});assert interpret_link(s,[TEXT],'text')['status']=='clarify'

def test_duplicate_literal_is_not_arbitrarily_selected():
    s=session();assert interpret_link(s,[TEXT+' Tarifs'],'text')['status']=='clarify'

@pytest.mark.parametrize('suffix',[' demain',' mais ne le fais pas vraiment',' quand je gagne',' si je le demande'])
def test_negative_or_future_reservation_outside_fields(suffix):
    s=session();assert interpret_link(s,[TEXT+suffix],'voice')['status']=='clarify'

def test_field_content_may_contain_temporal_words():
    q='Quel est le prix demain ?';s=session({**TARGET,'question':q})
    assert interpret_link(s,[TEXT.replace(TARGET['question'],q)],'voice')['status']=='ready'

def test_incomplete_then_field_completion():
    first='Suis le lien Tarifs sur '+URL
    second='La question est Quel est le prix adulte ?'
    s=session();value=json.loads(s.ask.return_value[0]);value['question']['turn']=1
    s.ask.return_value=(json.dumps(value),0,{})
    assert interpret_link(s,[first,second],'voice')['target']==TARGET

def test_correction_cannot_reuse_old_field():
    s=session();r=interpret_link(s,[TEXT,'Finalement le lien est Horaires'],'voice')
    assert r['status']=='clarify' and r['reason']=='superseded_label'
    raw=json.loads(s.ask.return_value[0]);raw['label']={'turn':1,'quote':'Horaires'}
    s.ask.return_value=(json.dumps(raw),0,{})
    assert interpret_link(s,[TEXT,'Finalement le lien est Horaires'],'voice')['target']['label']=='Horaires'

def test_words_inside_new_question_do_not_correct_other_fields():
    question='Quel site gere ces domaines et quel lien les decrit ?'
    s=session({**TARGET,'question':question})
    raw=json.loads(s.ask.return_value[0]);raw['question']['turn']=1
    s.ask.return_value=(json.dumps(raw),0,{})
    result=interpret_link(s,[TEXT,'La question est '+question],'voice')
    assert result['status']=='ready' and result['target']=={**TARGET,'question':question}

def test_cancellation_and_unrelated_followup_never_call_model():
    s=session();assert interpret_link(s,[TEXT,'stop'],'voice')['status']=='cancel'
    assert interpret_link(s,[TEXT,'Bonjour'],'voice')['status']=='clarify'
    s.ask.assert_not_called()

def test_nonrequest_and_budget_fail_closed_without_model():
    s=session()
    assert interpret_link(s,['Par exemple '+TEXT],'text')['status']=='discuss'
    assert interpret_link(s,[TEXT]*9,'text')['status']=='clarify'
    assert interpret_link(s,['x'*16001],'text')['status']=='clarify'
    s.ask.assert_not_called()

@pytest.mark.parametrize('intent',['discuss','cancel','clarify'])
def test_model_can_refuse_or_clarify_without_target(intent):
    s=session();s.ask.return_value=(json.dumps({'intent':intent}),0,{})
    assert interpret_link(s,[TEXT],'voice')=={'status':intent}

def test_semantic_check_sees_reservation_even_if_extracted_as_question():
    text='Suis le lien Tarifs sur '+URL+' pour trouver le prix adulte si je gagne.'
    s=session({'url':URL,'label':'Tarifs','question':'le prix adulte si je gagne'})
    s.decision_raw='{"decision":"clarify"}'
    assert interpret_link(s,[text],'voice')['status']=='clarify'
    payload=json.loads(s.ask.call_args.args[0][1]['content'])
    assert payload['tours_locaux']==[text]
    assert 'si je gagne' in payload['extraction_a_verifier']['question']

@pytest.mark.parametrize('raw',['{}','not json','{"decision":"execute","decision":"discuss"}',
    '{"decision":"execute","extra":1}','null'])
def test_invalid_semantic_check_never_authorizes(raw):
    s=session();s.decision_raw=raw
    assert interpret_link(s,[TEXT],'voice')['status']=='clarify'

@pytest.mark.parametrize('quoted',[False,True])
def test_url_sentence_punctuation_normalized_only_when_bare(quoted):
    url=URL+'.';literal='"'+url+'"' if quoted else url
    text='Suis le lien Tarifs pour trouver le prix adulte sur '+literal
    s=session({'url':url,'label':'Tarifs','question':'le prix adulte'})
    result=interpret_link(s,[text],'voice')
    assert result['status']=='ready'
    assert result['target']['url']==(url if quoted else URL)
    ref=result['sources']['url']
    assert text[ref['start']:ref['end']]==result['target']['url']

def test_model_may_not_drop_intentional_quoted_url_dot():
    text='Suis le lien Tarifs pour trouver le prix adulte sur "'+URL+'."'
    s=session({'url':URL,'label':'Tarifs','question':'le prix adulte'})
    assert interpret_link(s,[text],'voice')['status']=='clarify'

def test_latest_field_turns_are_exposed_separately():
    s=session();turns=[TEXT,'Le lien est Horaires.','La question est Quand le musee ouvre ?']
    raw={'intent':'execute','url':{'turn':0,'quote':URL},'label':{'turn':1,'quote':'Horaires'},
         'question':{'turn':2,'quote':'Quand le musee ouvre ?'}}
    s.ask.return_value=(json.dumps(raw),0,{})
    r=interpret_link(s,turns,'voice');assert r['status']=='ready'
    payload=json.loads(s.ask.call_args_list[0].args[0][1]['content'])
    assert payload['minimum_turn']=={'url':0,'label':1,'question':2}
    assert payload['derniers_tours_par_champ']['label']=={'turn':1,'text':turns[1]}

def test_explicit_corrected_url_overrides_obsolete_model_url():
    s=session();url='https://example.org/new'
    text='La page est '+url+'.'
    r=interpret_link(s,[TEXT,text],'voice')
    assert r['status']=='ready' and r['target']['url']==url
    ref=r['sources']['url'];assert ref['turn']==1
    assert text[ref['start']:ref['end']]==url

def test_ambiguous_corrected_url_never_chooses_one():
    s=session()
    r=interpret_link(s,[TEXT,'La page est https://example.org/a ou https://example.org/b'],'voice')
    assert r['status']=='clarify' and r['reason']=='ambiguous_corrected_url'
