from copy import deepcopy
from unittest.mock import Mock, patch

import pytest

from search_dialogue import SearchDialogue, run_search_turn


def result():
    return {'status':'found','reply':'Extrait original : open on Tuesday.',
            'sources':['https://example.org/'], 'partial':True,'relation':'single',
            'evidence':[{'url':'https://example.org/','status':'found',
                         'quotes':['Open on Tuesday.']}]}


def controller(data):
    return SearchDialogue(Mock(),planner=Mock(return_value={
        'status':'ready','target':{'question':'Quel jour ?'}}),reader=Mock(return_value=data))


def test_summary_preserves_original_evidence_and_does_not_mutate_reader_result():
    data=result();before=deepcopy(data)
    with patch('search_dialogue.synthesize',return_value='Le site indique mardi. [S1]') as summarize:
        actual=controller(data).handle('/rechercher Quel jour ?', 'text')
    assert actual['reply']=='Le site indique mardi. [S1]'
    assert actual['verified_excerpts']==before['reply']
    assert actual['evidence']==before['evidence'] and data==before
    assert summarize.call_args.args[1:]==('Quel jour ?',data['evidence'],'single')


@pytest.mark.parametrize('error',[ValueError('unknown_reference'),RuntimeError('model_unavailable')])
def test_invalid_or_unavailable_summary_keeps_verified_quotes(error):
    data=result()
    with patch('search_dialogue.synthesize',side_effect=error):
        actual=controller(data).handle('/rechercher Quel jour ?', 'text')
    assert actual['reply']==data['reply'] and actual['status']=='found'
    assert actual['answer_style']=='verified_quotes'


def test_ambiguous_evidence_is_not_rewritten_as_a_single_conclusion():
    data={**result(),'status':'ambiguous','relation':'conflicting'}
    with patch('search_dialogue.synthesize') as summarize:
        assert controller(data).handle('/rechercher Quel jour ?', 'text')==data
    summarize.assert_not_called()


def test_interface_emits_original_quotes_but_speaks_summary_only():
    data={**result(),'reply':'Le site indique mardi.','verified_excerpts':'Open on Tuesday.'}
    app=Mock();app.speech_epoch=3;app.session.voice.interruption_epoch=3
    app.stop.is_set.return_value=False;app.inputs.empty.return_value=True
    app.searches.handle.return_value=data
    run_search_turn(app,'Recherche sur internet quel jour ?', 'text')
    app.say.assert_called_once_with('Le site indique mardi.')
    assert (('text',('Extraits verifies','Open on Tuesday.')),) in [c.args for c in app.events.put.call_args_list]
