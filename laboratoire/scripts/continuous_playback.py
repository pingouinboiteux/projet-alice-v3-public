"""Keep one output stream for all PCM packets of a spoken reply."""
import wave


class ContinuousPCM:
    def __init__(self, check, factory=None, output_profile='mme_mono'):
        self.check = check
        self.factory = factory
        self.stream = None
        self.underflows = 0
        self.output_info = {}
        self.output_profile = output_profile

    def write(self, path):
        with wave.open(str(path), 'rb') as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
                raise RuntimeError('Format audio inattendu')
            if self.stream is None:
                if self.factory is None:
                    import sounddevice
                    from audio_output_profile import stream_options
                    options = stream_options(sounddevice, self.output_profile)
                    self.factory = sounddevice.RawOutputStream
                else:
                    options = dict(samplerate=24000, channels=1 if self.output_profile=='mme_mono' else 2,
                                   dtype='int16', blocksize=480, latency='high')
                self.stream = self.factory(**options)
                self.stream.start()
                if getattr(self.factory, '__module__', None) == 'sounddevice':
                    try:
                        import sounddevice
                        info = dict(sounddevice.query_devices(self.stream.device))
                        self.output_info = {'device_index':int(self.stream.device),
                            'name':info['name'], 'hostapi':sounddevice.query_hostapis(info['hostapi'])['name'],
                            'samplerate':float(self.stream.samplerate), 'latency':float(self.stream.latency)}
                    except Exception as error:
                        self.output_info = {'inventory_error':type(error).__name__}
            # Blocking writes maintain a bounded queue; cancellation is checked
            # every 20 ms of PCM, without stopping or padding between packets.
            while data := wav.readframes(480):
                self.check()
                if self.output_profile != 'mme_mono':
                    from audio_output_profile import stereo_pcm
                    data = stereo_pcm(data)
                self.underflows += bool(self.stream.write(data))

    def close(self, complete=False):
        if self.stream is not None:
            try:
                if complete:
                    # PortAudio stop drains pending samples; abort discards them.
                    self.stream.stop()
                else:
                    self.stream.abort()
            finally:
                self.stream.close()
