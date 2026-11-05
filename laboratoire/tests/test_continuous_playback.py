import array
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import Mock, patch
import wave

import pytest

from continuous_playback import ContinuousPCM
from voice_link import Voice, ROOT


def packet(folder, index, frames):
    path = folder / f'validation_pcm_{index}.wav'
    raw = array.array('h', [(i % 30000) - 15000 for i in range(frames)]).tobytes()
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((1, 2, 24000, 0, 'NONE', 'not compressed'))
        wav.writeframes(raw)
    return path, raw


def test_packets_are_one_continuous_stream_with_exact_pcm_and_drained_tail(tmp_path):
    stream = Mock(); stream.write.return_value = False
    factory = Mock(return_value=stream)
    player = ContinuousPCM(Mock(), factory)
    expected = b''
    for index, frames in enumerate((12000, 36000, 6101)):
        path, raw = packet(tmp_path, index, frames)
        expected += raw
        player.write(path)
        stream.stop.assert_not_called()
        stream.abort.assert_not_called()
    player.close(complete=True)
    factory.assert_called_once()
    stream.start.assert_called_once()
    stream.stop.assert_called_once()
    stream.close.assert_called_once()
    assert b''.join(call.args[0] for call in stream.write.call_args_list) == expected
    assert max(len(call.args[0]) for call in stream.write.call_args_list) <= 960
    assert player.underflows == 0


def test_cancel_discards_pending_audio_and_closes_device(tmp_path):
    stream = Mock(); stream.write.return_value = False
    check = Mock(side_effect=[None, RuntimeError('cancel')])
    player = ContinuousPCM(check, Mock(return_value=stream))
    path, _ = packet(tmp_path, 0, 12000)
    with pytest.raises(RuntimeError, match='cancel'):
        try:
            player.write(path)
        finally:
            player.close()
    stream.abort.assert_called_once()
    stream.stop.assert_not_called()
    stream.close.assert_called_once()
    assert stream.write.call_count == 1


def test_starvation_is_observable_instead_of_reported_as_gapless(tmp_path):
    stream = Mock(); stream.write.side_effect = [False, True, False]
    player = ContinuousPCM(Mock(), Mock(return_value=stream))
    path, _ = packet(tmp_path, 0, 1440)
    player.write(path)
    player.close(complete=True)
    assert player.underflows == 1


def test_voice_failure_cleans_generator_subtitle_and_output(tmp_path):
    path, _ = packet(tmp_path, 0, 12000)
    session = Mock(); session.observer = None
    voice = Voice(session); voice.continuous_playback = True
    voice.subtitles = Mock(); voice.subtitles.show.return_value = 7
    def parts(_):
        try:
            yield path, {}
            raise RuntimeError('synthesis failure')
        finally:
            path.unlink()
    voice.audio_parts = parts
    with patch('continuous_playback.ContinuousPCM') as factory:
        with pytest.raises(RuntimeError, match='synthesis failure'):
            voice.speak('validation')
    factory.return_value.close.assert_called_once_with(complete=False)
    voice.subtitles.clear.assert_called_once_with(7)
    assert not path.exists()


@pytest.mark.parametrize('record', [False,True])
def test_real_parent_protocol_and_reader_forward_exact_worker_pcm_without_sound(record):
    from sopro_protocol import render_pcm
    from voice_capture import arm, begin, NAMES
    raw = array.array('h', [(i % 30000)-15000 for i in range(125001)]).tobytes()
    stream = Mock(); stream.write.return_value = False
    factory = Mock(return_value=stream)
    with tempfile.TemporaryDirectory(prefix='validation_voice_path_', dir=ROOT/'logs') as name:
        folder = Path(name)
        session = Mock(); session.observer = None; session.temp = SimpleNamespace(name=name)
        voice = Voice(session); voice.continuous_playback = True
        voice.profile_name = 'sopro_d'; voice.capture_allowed = record
        capture_folder = folder/'validation_capture'
        if record: arm(capture_folder)
        voice.process = Mock(); voice.process.poll.return_value = None
        def write(line):
            request = json.loads(line)
            render_pcm([raw[:13000], raw[13000:]], request['id'], folder, ROOT,
                       voice.messages.put, stream=True)
        voice.process.stdin.write.side_effect = write
        with patch.dict('sys.modules', sounddevice=SimpleNamespace(RawOutputStream=factory)), \
                patch('voice_capture.begin', side_effect=lambda profile:begin(profile,capture_folder)):
            voice.speak('Texte synthetique.')
        assert b''.join(c.args[0] for c in stream.write.call_args_list) == raw
        stream.start.assert_called_once()
        stream.stop.assert_called_once()
        stream.abort.assert_not_called()
        stream.close.assert_called_once()
        voice.process.terminate.assert_not_called()
        assert not list(folder.glob('*.wav'))
        if record:
            with wave.open(str(capture_folder/NAMES[1]),'rb') as wav:
                assert wav.readframes(wav.getnframes()) == raw


def test_loaded_voice_label_does_not_hide_engine_or_playback_mode():
    voice = Voice(Mock())
    assert voice.status_text() == 'Voix non chargee.'
    voice.profile_name = 'current'
    assert 'Chatterbox' in voice.status_text()
    voice.profile_name = 'sopro_d'
    assert "sample d'origine" in voice.status_text() and 'continue' in voice.status_text()
    voice.ready={'steps':2}
    assert '2 etapes' in voice.status_text()


@pytest.mark.parametrize('profile',['mme_stereo','wasapi_stereo'])
def test_stereo_reader_preserves_each_channel_across_packet_boundaries(tmp_path,profile):
    stream=Mock(); stream.write.return_value=False
    factory=Mock(return_value=stream)
    player=ContinuousPCM(Mock(),factory,output_profile=profile)
    source=b''
    for index,frames in enumerate((12001,6103)):
        path,raw=packet(tmp_path,index,frames); source+=raw; player.write(path)
    player.close(True)
    output=array.array('h'); output.frombytes(b''.join(c.args[0] for c in stream.write.call_args_list))
    mono=array.array('h'); mono.frombytes(source)
    assert output[::2]==mono and output[1::2]==mono
    assert factory.call_args.kwargs['channels']==2
    stream.start.assert_called_once(); stream.stop.assert_called_once()
