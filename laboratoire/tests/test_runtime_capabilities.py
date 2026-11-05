import sys,queue,threading,time
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock,MagicMock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from capability_state import channel_state,dialogue_context
from alice_desktop import Application

def test_connection_requires_live_process_and_ready_status():
    channels=NS(enabled={'twitch':True},processes={'twitch':Mock()},last_status={'twitch':'ready'})
    channels.processes['twitch'].poll.return_value=None
    assert channel_state(channels)=={'twitch':'ready','discord':'off'}
    channels.processes['twitch'].poll.return_value=1
    assert channel_state(channels)['twitch']=='unavailable'
    channels.processes['twitch'].poll.return_value=None
    channels.last_status['twitch']='UNTRUSTED_SENTINEL'
    assert channel_state(channels)['twitch']=='unknown'
    assert 'UNTRUSTED' not in dialogue_context(channels)
    assert channel_state(None)=={'twitch':'off','discord':'off'}

def test_confirmation_expires_without_ui_and_stale_approval_cannot_run():
    app=Application.__new__(Application)
    app.events=queue.Queue();app.stop=threading.Event();app.observation=MagicMock()
    with patch('alice_desktop.ACTION_CONFIRM_SECONDS',0.01):
        assert app.confirm('Ouvrir le site ?') is False
    kind,(_,event,result,deadline)=app.events.get_nowait()
    assert kind=='confirm' and event.is_set() and not result and time.monotonic()>deadline
    app.observation.emit.assert_any_call('confirmation.result',{'accepted':False,'expired':True})


def test_waiting_for_local_confirmation_can_serve_external_dialogue_without_approval():
    app=Application.__new__(Application)
    app.events=queue.Queue();app.stop=threading.Event();app.observation=MagicMock()
    app.channels=Mock();app.hearing=Mock();app.session=NS(voice=Mock())
    def external_turn(*args):
        _,(_,event,result,_)=app.events.get_nowait()
        assert not result and not event.is_set()
        # UI cancellation after one external turn. Never approve in this path.
        result.append(False);event.set()
        return True
    app.channels.handle_one.side_effect=external_turn
    with patch('alice_desktop.ACTION_CONFIRM_SECONDS',2):
        assert not app.confirm('Demande locale fictive')
    app.channels.handle_one.assert_called_once_with(app.hearing,app.session.voice)


def test_confirmation_that_expires_during_external_turn_is_not_accepted():
    app=Application.__new__(Application)
    app.events=queue.Queue();app.stop=threading.Event();app.observation=MagicMock()
    app.channels=Mock();app.hearing=Mock();app.session=NS(voice=Mock())
    clock=[100.0]
    def external_turn(*args):
        _,(_,event,result,_)=app.events.get_nowait()
        clock[0]=103.0
        result.append(True);event.set()
    app.channels.handle_one.side_effect=external_turn
    with patch('alice_desktop.time.monotonic',side_effect=lambda:clock[0]),patch('alice_desktop.ACTION_CONFIRM_SECONDS',2):
        assert not app.confirm('Demande locale fictive')

def test_remote_drop_reasons_do_not_store_viewer_text():
    from remote_channels import RemoteChannels
    from remote_dialogue import RemoteText
    session=Mock();session.observer=Mock()
    with patch('remote_channels.public_filter',return_value=lambda text:text):
        channels=RemoteChannels(session,queue.Queue())
    channels.enabled['twitch']=True
    channels.enqueue('twitch',0,RemoteText('twitch','validation_viewer','PRIVATE_SENTINEL'))
    assert not channels.handle_one(Mock(),Mock())
    session.observer.emit.assert_any_call('external.skipped',{'source':'twitch','reason':'not_addressed'})
    channels.pending.put(('twitch',0,time.monotonic()-121,RemoteText('twitch','validation_viewer','Alice PRIVATE_SENTINEL')))
    channels.next_remote=0
    assert channels.handle_one(Mock(),Mock())
    assert 'expired' in repr(session.observer.emit.call_args_list)
    assert 'PRIVATE_SENTINEL' not in repr(session.observer.emit.call_args_list)
    session.ask.assert_not_called()
