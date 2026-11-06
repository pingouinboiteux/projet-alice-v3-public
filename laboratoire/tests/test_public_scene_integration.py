"""Shared scene wiring without actual memory, audio, network or model."""
import json
import queue
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))

from public_scene import PublicScene
from remote_dialogue import RemoteDialogue, RemoteText
from remote_channels import RemoteChannels
from desktop_initiative import DesktopInitiative
from conversation_initiative import Initiative

def channels(scene):
    session=SimpleNamespace(ask=Mock(return_value=('{"reply":"Reponse publique."}',0,{})), check=lambda:None)
    with patch('remote_channels.public_filter',return_value=lambda text:text):
        value=RemoteChannels(session,queue.Queue(),scene=scene)
    value.enabled['twitch']=True
    return value,session

def adapter():
    session=SimpleNamespace(ask_background=Mock(return_value=(json.dumps({
        'subject':'validation sujet','choice':'continue','reply':'ARGUMENT_PUBLIC_ALICE'}),0,{})))
    with patch.object(Initiative,'start'):
        value=DesktopInitiative(session)
    clock=[0.]
    value.core.clock=lambda:clock[0]
    return value,session,clock

def test_delivered_animation_reaches_viewer_and_private_history_does_not():
    value,session,clock=adapter()
    remote,model=channels(value.scene)
    value.set_mode('animation')
    value.idle([{'role':'user','content':'PRIVATE_SENTINEL'}],remote)
    clock[0]=10;value.core.tick()
    assert value.deliver(lambda text:True, [],lambda:False)
    remote.enqueue('twitch',0,RemoteText('twitch','validation_a','Alice pourquoi cet argument ?'))
    remote.handle_one(Mock(),SimpleNamespace(interruption_epoch=0,speak=lambda text:True))
    payload=repr(model.ask.call_args)
    assert 'ARGUMENT_PUBLIC_ALICE' in payload and 'PRIVATE_SENTINEL' not in payload
    assert 'validation_a' in payload and 'interlocuteur_actuel' in payload
    assert value.scene.snapshot()[-1]['recipient']=='validation_a'
    value.idle([],remote);clock[0]=100;value.core.tick()
    assert 'Reponse publique.' in repr(session.ask_background.call_args)

def test_two_viewers_have_attributed_context_but_discord_is_separate():
    scene=PublicScene()
    scene.record_viewer(RemoteText('twitch','validation_lina','Je prefere le rouge.'))
    scene.record_viewer(RemoteText('twitch','validation_noe','Je prefere le bleu.'))
    model=Mock(return_value=('{"reply":"Reponse."}',0,{}))
    remote=RemoteDialogue(model,scene=scene)
    remote.answer(RemoteText('twitch','validation_lina','Qui prefere le bleu ?'))
    payload=repr(model.call_args)
    assert 'validation_lina' in payload and 'validation_noe' in payload
    remote.answer(RemoteText('discord','validation_lina','Bonjour.'))
    assert 'validation_noe' not in repr(model.call_args)
    assert 'Je prefere le rouge' not in repr(model.call_args)

def test_private_discussion_and_interrupted_animation_do_not_enter_scene():
    value,session,clock=adapter()
    value.set_mode('discussion');value.idle([{'role':'user','content':'PRIVATE_SENTINEL'}])
    clock[0]=100;value.core.tick()
    assert value.deliver(lambda text:True,[],lambda:False)
    assert value.scene.snapshot()==[]
    value.set_mode('animation');value.idle([])
    clock[0]=200;value.core.tick()
    assert not value.deliver(lambda text:False,[],lambda:False)
    assert value.scene.snapshot()==[]

def test_explicit_local_directive_reaches_animation_and_twitch_without_private_data():
    value,session,clock=adapter();remote,model=channels(value.scene)
    value.set_mode('animation')
    value.share_directive('Quitte les sujets tristes et parle de cuisine.',remote)
    value.idle([{'role':'assistant','content':'PRIVATE_SECRET'}],remote)
    clock[0]=100;value.core.tick()
    payload=repr(session.ask_background.call_args)
    assert 'cuisine' in payload and 'PRIVATE_SECRET' not in payload
    assert 'directive' in payload
    remote.dialogue.answer(RemoteText('twitch','validation_a','Alice quel sujet maintenant ?'))
    assert 'cuisine' in repr(model.ask.call_args)

def test_failed_remote_playback_is_not_shared_and_disconnect_clears_scene():
    scene=PublicScene();remote,model=channels(scene)
    remote.enqueue('twitch',0,RemoteText('twitch','validation_a','Alice bonjour'))
    remote.handle_one(Mock(),SimpleNamespace(interruption_epoch=0,speak=lambda text:False))
    assert all(e['kind']!='alice' for e in scene.snapshot())
    remote.disconnect('twitch')
    assert scene.snapshot()==[]

def test_new_viewer_invalidates_prepared_autonomous_reply():
    value,session,clock=adapter();remote,model=channels(value.scene)
    value.set_mode('animation');value.idle([],remote)
    clock[0]=100;value.core.tick();assert value.has_ready()
    remote.enqueue('twitch',0,RemoteText('twitch','validation_a','Alice change de sujet.'))
    value.refresh_public(remote)
    assert not value.has_ready()

def test_scene_expires_from_animation_and_viewer_context():
    value,session,clock=adapter()
    value.scene.clock=lambda:clock[0]
    remote,model=channels(value.scene)
    value.scene.record_alice('EXPIRED_PUBLIC_SENTINEL')
    value.set_mode('animation');value.idle([],remote)
    clock[0]=301;value.refresh_public(remote)
    clock[0]=310;value.core.tick()
    assert 'EXPIRED_PUBLIC_SENTINEL' not in repr(session.ask_background.call_args)
    remote.dialogue.answer(RemoteText('twitch','validation_a','Alice bonjour'))
    assert 'EXPIRED_PUBLIC_SENTINEL' not in repr(model.ask.call_args)

def test_disconnect_during_playback_cannot_repopulate_shared_scene():
    scene=PublicScene();remote,model=channels(scene)
    remote.enqueue('twitch',0,RemoteText('twitch','validation_a','Alice bonjour'))
    def speak(text):
        remote.disconnect('twitch')
        return True
    remote.handle_one(Mock(),SimpleNamespace(interruption_epoch=0,speak=speak))
    assert scene.snapshot()==[]
    assert remote.selection.history(0)==[]

def test_explicit_voice_command_bypasses_uncertain_recipient_without_model():
    from desktop_recipient import accept_speech
    app=Mock()
    assert accept_speech(app,{'text':'Alice pour le stream parle de cuisine'},[],Mock())
    app.stream_recipient.decide.assert_not_called()

def test_clear_scene_invalidates_ready_proposal_and_erases_context():
    value,session,clock=adapter()
    value.set_mode('animation');value.share_directive('EXPLICIT_PUBLIC_SENTINEL')
    clock[0]=10;value.core.tick();assert value.has_ready()
    value.clear_scene()
    assert not value.has_ready() and value.scene.snapshot()==[] and value.public==[]
