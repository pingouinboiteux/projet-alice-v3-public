"""Bounded Discord PCM validation, before the shared recognizer."""
import base64


def voiced_audio(encoded,vad):
    import numpy as np
    if not isinstance(encoded,str) or len(encoded)>1280000:
        raise ValueError('Audio externe invalide')
    raw=base64.b64decode(encoded,validate=True)
    if not 16000<=len(raw)<=960000 or len(raw)%2:
        raise ValueError('Audio externe invalide')
    samples=np.frombuffer(raw,dtype='<i2')
    vad.reset_states()
    voiced=sum(float(vad.predict(samples[start:start+480],frame_size=480))>=.5
        for start in range(0,len(samples)-479,480))
    return samples.astype(np.float32)/32768 if voiced>=2 else None
