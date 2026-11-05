import array
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from audio_output_profile import stereo_pcm, stream_options


def test_stereo_is_two_exact_channels_without_gain_or_sample_rate_change():
    samples=array.array('h',[-32768,-1,0,1,32767])
    output=array.array('h'); output.frombytes(stereo_pcm(samples.tobytes()))
    assert output[::2] == samples and output[1::2] == samples


def test_wasapi_selects_same_headset_and_shared_mode_conversion():
    devices=[{'name':'Razer Headset','hostapi':0,'max_output_channels':2},
             {'name':'Razer Headset full name','hostapi':1,'max_output_channels':2},
             {'name':'Other device','hostapi':1,'max_output_channels':2}]
    sd=SimpleNamespace(query_devices=Mock(side_effect=lambda **kw:devices[0] if kw else devices),
                       query_hostapis=lambda:[{'name':'MME'},{'name':'Windows WASAPI'}],
                       WasapiSettings=Mock(),check_output_settings=Mock())
    options=stream_options(sd,'wasapi_stereo')
    assert options['device']==1 and options['channels']==2 and options['samplerate']==24000
    sd.WasapiSettings.assert_called_once_with(exclusive=False,auto_convert=True)
    sd.check_output_settings.assert_called_once()
    devices.append(devices[1].copy())
    with pytest.raises(RuntimeError,match='ambiguite'):stream_options(sd,'wasapi_stereo')
