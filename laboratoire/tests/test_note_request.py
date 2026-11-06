from unittest.mock import Mock, patch
import pytest
from note_request import decide_note
from notes_dialogue import NotesDialogue
from observer_note_pending import PendingNoteReview

TARGET={'title':'validation_Courses','body':'pain et lait'}
TEXT='Cree une note titre validation_Courses texte pain et lait'

def session():
    value=Mock()
    value.ask.return_value=('{"decision":"execute"}',0,{})
    return value

@pytest.mark.parametrize('source',['text','voice'])
def test_grounded_local_creation_can_execute(source):
    s=session()
    assert decide_note(s,[TEXT],'create',{'target':TARGET},source)=='execute'
    s.ask.assert_called_once()

@pytest.mark.parametrize('text',[
    'Il a dit '+TEXT, 'Par exemple '+TEXT, '"'+TEXT+'"',
    'Ne fais rien : '+TEXT, TEXT+' puis stop', 'Cree une note sans contenu',
])
def test_structural_rejections_do_not_call_model(text):
    s=session()
    assert decide_note(s,[text],'create',{'target':TARGET},'voice')!='execute'
    s.ask.assert_not_called()

@pytest.mark.parametrize('raw',['{}','{"decision":"execute","decision":"discuss"}',
    '{"decision":"execute","extra":1}','null','not json'])
def test_invalid_judgement_never_authorizes(raw):
    s=session();s.ask.return_value=(raw,0,{})
    assert decide_note(s,[TEXT],'create',{'target':TARGET},'voice')=='clarify'

def test_external_source_never_classified():
    s=session()
    assert decide_note(s,[TEXT],'create',{'target':TARGET},'twitch')=='clarify'
    s.ask.assert_not_called()

def test_correction_cannot_reuse_old_value():
    s=session()
    assert decide_note(s,[TEXT,'Finalement remplace le texte par autre chose'],'create',{'target':TARGET},'text')=='clarify'
    s.ask.assert_not_called()

def test_completion_across_turns_and_quoted_stop():
    s=session();target={'title':'validation_Titre','body':'stop'}
    assert decide_note(s,['Cree une note','Titre validation_Titre texte "stop"'],
                       'create',{'target':target},'voice')=='execute'

def test_automatic_authorization_is_single_use_and_source_bound():
    p=PendingNoteReview();p.propose(TARGET,'voice');r=p.review()
    with pytest.raises(ValueError):p.authorize_request(r['ticket'],source='local_text')
    token=p.authorize_request(r['ticket'],source='voice')
    with pytest.raises(ValueError):p.authorize_request(r['ticket'],source='voice')
    assert p.claim(token)==TARGET
    with pytest.raises(ValueError):p.claim(token)

def test_automatic_request_can_expire_or_be_cancelled():
    now=[0.];p=PendingNoteReview(clock=lambda:now[0])
    p.propose(TARGET,'voice');r=p.review();now[0]=61
    with pytest.raises(ValueError):p.authorize_request(r['ticket'],source='voice')
    p.propose(TARGET,'voice');r=p.review();p.cancel()
    with pytest.raises(ValueError):p.authorize_request(r['ticket'],source='voice')

def make():
    s=session();backend=Mock();backend.title_exists.return_value=False
    backend.verify_persisted.return_value=True
    factory=Mock(return_value=backend)
    def executor(session,backend,target,claim):
        assert claim()==target
        return {'passed':True}
    c=NotesDialogue(s,factory=factory,planner=Mock(return_value={'status':'ready','target':TARGET}),executor=executor)
    return c,backend,factory

def test_real_gate_controller_saves_without_button():
    c,b,f=make();confirm=Mock(side_effect=AssertionError('button forbidden'))
    assert c.handle(TEXT,'voice',confirm,automatic=True)['status']=='saved'
    b.verify_persisted.assert_called_once_with(TARGET);confirm.assert_not_called()

def test_discussion_does_not_fall_back_to_button_or_open_store():
    c,b,f=make();c.session.ask.return_value=('{"decision":"discuss"}',0,{})
    confirm=Mock()
    assert c.handle(TEXT,'voice',confirm,automatic=True)['status']=='clarify'
    f.assert_not_called();confirm.assert_not_called()

def test_interruption_during_gate_prevents_store_open():
    c,b,f=make();stopped=[False]
    def ask(*args,**kwargs):stopped[0]=True;return ('{"decision":"execute"}',0,{})
    c.session.ask.side_effect=ask
    assert c.handle(TEXT,'voice',Mock(),lambda:stopped[0],automatic=True)['status']=='failed'
    f.assert_not_called()

def test_new_input_before_commit_prevents_save():
    c,b,f=make();b.prepare_new.side_effect=c.pending.cancel
    assert c.handle(TEXT,'voice',Mock(),automatic=True)['status']=='failed'
    b.verify_persisted.assert_not_called()

@pytest.mark.parametrize('suffix',[' demain',' plus tard',' mais ne le fais pas vraiment',
    ' quand je serai pret',' si je gagne',' sans enregistrer'])
def test_noncurrent_control_rejected_even_if_model_would_execute(suffix):
    s=session()
    assert decide_note(s,[TEXT+suffix],'create',{'target':TARGET},'voice')!='execute'
    s.ask.assert_not_called()

def test_future_in_unquoted_body_is_content():
    s=session();target={'title':'validation_A','body':'Acheter demain'}
    text='Cree une note titre validation_A texte Acheter demain'
    assert decide_note(s,[text],'create',{'target':target},'voice')=='execute'
