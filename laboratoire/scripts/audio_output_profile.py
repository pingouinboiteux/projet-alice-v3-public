"""Playback-only candidates; generated mono PCM is never changed in level."""
import array


def stereo_pcm(raw):
    mono = array.array('h'); mono.frombytes(raw)
    stereo = array.array('h', [0])*(len(mono)*2)
    stereo[::2] = mono; stereo[1::2] = mono
    return stereo.tobytes()


def stream_options(sd, profile):
    options = dict(samplerate=24000, channels=1, dtype='int16', blocksize=480, latency='high')
    if profile == 'mme_mono': return options
    options['channels'] = 2
    if profile == 'mme_stereo': return options
    if profile != 'wasapi_stereo': raise ValueError('Profil de sortie inconnu')
    current = sd.query_devices(kind='output')['name'].casefold()
    devices = sd.query_devices(); apis = sd.query_hostapis()
    matches = [i for i, device in enumerate(devices)
               if device['max_output_channels'] >= 2
               and apis[device['hostapi']]['name'] == 'Windows WASAPI'
               and (device['name'].casefold().startswith(current)
                    or current.startswith(device['name'].casefold()))]
    if len(matches) != 1:
        raise RuntimeError('Sortie WASAPI du casque non identifiee sans ambiguite')
    options.update(device=matches[0], extra_settings=sd.WasapiSettings(exclusive=False, auto_convert=True))
    sd.check_output_settings(device=matches[0], channels=2, dtype='int16', samplerate=24000,
                             extra_settings=options['extra_settings'])
    return options
