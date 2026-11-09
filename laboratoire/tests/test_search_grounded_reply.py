from copy import deepcopy
from unittest.mock import Mock

from search_dialogue import SearchDialogue, run_search_turn


def result():
    return {'status':'found','reply':'Extrait original : open on Tuesday.',
            'sources':['https://example.org/'], 'partial':True,'relation':'single',
            'evidence':[{'url':'https://example.org/','status':'found',
                         'quotes':['Open on Tuesday.']}]}


def controller(data):
    return SearchDialogue(Mock(),planner=Mock(return_value={
        'status':'ready','target':{'question':'Quel jour ?'}}),reader=Mock(return_value=data))


def test_found_result_speaks_original_excerpts_without_extra_model_call():
    data=result();before=deepcopy(data)
    dialogue=controller(data)
    actual=dialogue.handle('/rechercher Quel jour ?', 'text')
    assert actual['reply']==before['reply']
    assert actual['answer_style']=='verified_quotes'
    assert actual['evidence']==before['evidence'] and data==before
    dialogue.session.ask.assert_not_called()


def test_semantic_inversion_cannot_be_spoken_as_verified_answer():
    data=result()
    data['reply']='Source 1 : « The museum is closed on Monday. »'
    data['evidence'][0]['quotes']=['The museum is closed on Monday.']
    actual=controller(data).handle('/rechercher Quel jour ?', 'text')
    assert actual['reply']==data['reply'] and actual['status']=='found'
    assert actual['answer_style']=='verified_quotes'
    assert 'open on Monday' not in actual['reply']


def test_ambiguous_evidence_is_not_rewritten_as_a_single_conclusion():
    data={**result(),'status':'ambiguous','relation':'conflicting'}
    actual=controller(data).handle('/rechercher Quel jour ?', 'text')
    assert actual['reply']==data['reply']
    assert actual['answer_style']=='verified_quotes'


def test_interface_emits_original_quotes_but_speaks_summary_only():
    data={**result(),'reply':'Le site indique mardi.','verified_excerpts':'Open on Tuesday.'}
    app=Mock();app.speech_epoch=3;app.session.voice.interruption_epoch=3
    app.stop.is_set.return_value=False;app.inputs.empty.return_value=True
    app.searches.handle.return_value=data
    run_search_turn(app,'Recherche sur internet quel jour ?', 'text')
    app.say.assert_called_once_with('Le site indique mardi.')
    assert (('text',('Extraits verifies','Open on Tuesday.')),) in [c.args for c in app.events.put.call_args_list]
