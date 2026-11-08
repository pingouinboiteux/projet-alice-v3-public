from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_text_request import interpret


@pytest.mark.parametrize('utterance',[
    'Alice, peux-tu ecrire «Bonjour  Proprietaire» dans la fenetre «Notes - Bloc-notes» ?',
    'Ecris dans la fenetre «Notes - Bloc-notes» le texte «Bonjour  Proprietaire».',
    'Tape dans la fenetre "Notes - Bloc-notes" texte : Bonjour  Proprietaire',
])
def test_exact_text_and_named_window(utterance):
    result=interpret(utterance,'voice')
    assert result['status']=='ready'
    assert result['target']=={'window_hint':'Notes - Bloc-notes','text':'Bonjour  Proprietaire'}
    a,b=result['text_span']
    assert utterance[a:b]==result['target']['text']


def test_multiline_literal_is_preserved():
    result=interpret('Ecris dans le bloc-notes le texte : pain\npoires','text')
    assert result['target']=={'window_hint':'Bloc-notes','text':'pain\npoires'}


@pytest.mark.parametrize('utterance',[
    'Si je dis ecris dans le bloc-notes, que fais-tu ?',
    'Par exemple, tape dans le bloc-notes texte : hello',
    'Ne tape pas dans le bloc-notes texte : hello',
    'Cree une note intitulee courses avec du pain',
    'Comment ecrire dans la fenetre du bloc-notes ?',
])
def test_discussion_is_not_a_native_order(utterance):
    assert interpret(utterance,'text')['status']=='not_handled'


@pytest.mark.parametrize('utterance',[
    'Tape dans la fenetre le texte bonjour',
    'Tape «bonjour» dans la fenetre «Notes» puis envoie le message',
    'Tape dans le bloc-notes texte : «pas ferme',
    'Tape «bonjour» dans la fenetre «Notes» ou dans une autre',
    'Tape «bonjour\x00» dans la fenetre «Notes»',
])
def test_ambiguous_or_extra_actions_need_clarification(utterance):
    assert interpret(utterance,'text')['status']=='clarify'


@pytest.mark.parametrize('source',['twitch','discord','page','model'])
def test_external_sources_rejected(source):
    with pytest.raises(ValueError): interpret('Tape dans le bloc-notes texte : hello',source)
