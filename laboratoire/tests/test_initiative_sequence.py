import json
from types import SimpleNamespace
from unittest.mock import Mock

from conversation_initiative import Initiative, SCHEMA, speech_gap
from initiative_sequence import prepare


def message(text, role='assistant'):
    return {'role':role,'content':text}


def test_new_sequence_drops_old_prose_but_keeps_topic_titles():
    messages, schema = prepare('consigne',SCHEMA,[message('ANCIEN_ARGUMENT')],
                              'animation',3,['Jeux cooperatifs'],False)
    assert 'ANCIEN_ARGUMENT' not in repr(messages)
    assert 'Jeux cooperatifs' in messages[0]['content']
    assert 'subject' in schema['required']


def test_viewer_objection_retains_the_statement_it_refers_to():
    history=[message('ancien'),message('Les enigmes doivent etre justes.'),
             message('Pourquoi cette derniere idee ?', 'user')]
    messages,_=prepare('consigne',SCHEMA,history,'animation',1,[],True)
    assert json.loads(messages[-1]['content'])['historique']==history[-2:]


def test_conclusion_keeps_current_sequence_without_replaying_previous_one():
    history=[message('ancien'),message('intro'),message('exemple')]
    messages,_=prepare('consigne',SCHEMA,history,'animation',2,[],False)
    assert json.loads(messages[-1]['content'])['historique']==history[-2:]
    assert 'Conclue' in messages[0]['content']


def test_private_discussion_uses_whole_bounded_context_not_public_topic_archive():
    history=[message('demande privee','user')]
    messages,schema=prepare('consigne',SCHEMA,history,'discussion',2,['archive'],True)
    assert json.loads(messages[-1]['content'])['historique']==history
    assert 'archive' not in repr(messages) and schema==SCHEMA


def test_topics_advance_only_after_delivery_and_clear_when_mode_changes():
    now=[0]
    session=SimpleNamespace(ask_background=Mock(return_value=(json.dumps(
        {'subject':'validation sujet','choice':'topic','reply':'Une idee concrete.'}),0,{})))
    core=Initiative(session,clock=lambda:now[0])
    core.set_mode('animation');core.idle([],public=True);now[0]=5;core.tick()
    assert core.topics==[] and core.sequence_turn==0
    proposal=core.pop();core.delivered(proposal)
    assert core.topics==['validation sujet'] and core.sequence_turn==1
    core.active();core.idle([],public=True);now[0]=10;core.tick()
    stale=core.pop();core.active()
    assert not core.delivered(stale)
    assert core.topics==['validation sujet']
    core.set_mode('discussion')
    assert core.topics==[] and core.sequence_turn==0


def test_pauses_scale_with_length_and_leave_room_for_answers():
    assert speech_gap('animation',5,'mot '*48,1)==12
    assert speech_gap('animation',5,'Question ?',1)==18
    assert speech_gap('animation',5,'court',3)==8
    assert speech_gap('discussion',18,'court',1)==18
    assert speech_gap('discussion',18,'court',5)==45


def test_topic_archive_remains_bounded():
    messages,_=prepare('consigne',SCHEMA,[],'animation',0,
                       ['titre'+str(i) for i in range(20)],False)
    assert '"titre0"' not in messages[0]['content']
    assert 'titre19' in messages[0]['content']
