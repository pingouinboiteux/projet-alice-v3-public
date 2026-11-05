"""Clock-controlled regressions; no network, model or sound."""
from unittest.mock import Mock,patch
from test_remote_channels import make_channels
from remote_dialogue import RemoteText
from capability_state import channel_state

def test_unaddressed_flood_does_not_displace_alice_requests():
    channels,session,_=make_channels()
    for _ in range(50):channels.enqueue('twitch',0,RemoteText('twitch','validation_viewer','Bonjour le stream'))
    channels.enqueue('twitch',0,RemoteText('twitch','validation_viewer','Alice bonjour'))
    assert channels.pending.qsize()==1
    channels.handle_one(Mock(),Mock())
    assert session.ask.call_count==1

def test_rate_limit_defers_fresh_message_instead_of_discarding_it():
    channels,session,_=make_channels()
    with patch('remote_channels.time.monotonic',return_value=100):
        channels.enqueue('twitch',0,RemoteText('twitch','validation_viewer','Alice bonjour'))
        assert channels.handle_one(Mock(),Mock())
    with patch('remote_channels.time.monotonic',return_value=103):
        channels.enqueue('twitch',0,RemoteText('twitch','validation_viewer','Alice une autre question'))
        assert not channels.handle_one(Mock(),Mock())
        assert channels.pending.qsize()==1
        assert session.ask.call_count==1
    with patch('remote_channels.time.monotonic',return_value=115):
        assert channels.handle_one(Mock(),Mock())
        assert channels.pending.empty()
        assert session.ask.call_count==2

def test_deferred_twitch_does_not_block_discord_and_expiry_stays_enforced():
    channels,session,_=make_channels()
    with patch('remote_channels.time.monotonic',return_value=100):
        channels.next_twitch=115
        channels.enqueue('twitch',0,RemoteText('twitch','validation_viewer','Alice première'))
        channels.enqueue('twitch',0,RemoteText('twitch','validation_viewer','Alice seconde'))
        marker=object()
        channels.enqueue('discord',0,marker)
        assert channels.take_ready()[3] is marker
        assert channels.pending.qsize()==2
    with patch('remote_channels.time.monotonic',return_value=115):
        assert channels.take_ready()[3].text=='Alice première'
    with patch('remote_channels.time.monotonic',return_value=221):
        assert channels.handle_one(Mock(),Mock())
        assert channels.pending.empty()
        session.ask.assert_not_called()


def test_twitch_survives_local_reply_and_wakes_idle_capture_only_when_ready():
    channels,session,_=make_channels()
    with patch('remote_channels.time.monotonic',return_value=100):
        channels.enqueue('twitch',0,RemoteText('twitch','validation_owner','Alice bonjour'))
        channels.next_twitch=115
        assert not channels.has_ready()
    with patch('remote_channels.time.monotonic',return_value=138):
        assert channels.has_ready()
        assert channels.handle_one(Mock(),Mock())
        assert session.ask.call_count==1
        assert not channels.has_ready()


def test_discord_still_expires_after_thirty_seconds():
    channels,session,_=make_channels()
    with patch('remote_channels.time.monotonic',return_value=100):
        channels.enqueue('discord',0,object())
    with patch('remote_channels.time.monotonic',return_value=131):
        assert channels.has_ready()
        assert channels.handle_one(Mock(),Mock())
        session.ask.assert_not_called()

def test_queue_warning_does_not_erase_transport_connection_state():
    channels,_,_=make_channels()
    process=Mock();process.poll.return_value=None
    channels.processes['twitch']=process
    channels.status('twitch','ready')
    channels.status('twitch','queue_full')
    assert channel_state(channels)['twitch']=='ready'
    channels.status('twitch','disconnected')
    assert channel_state(channels)['twitch']=='disconnected'
