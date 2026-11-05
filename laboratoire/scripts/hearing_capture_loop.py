"""Microphone frame loop: public chat may wake silence, never discard speech."""
import time


def capture_input(stream,capture,vad,np,threshold,cancelled,yield_requested,started):
    deadline=time.monotonic()+135
    speech_end=None
    while not cancelled.is_set() and time.monotonic()<deadline:
        raw,overflow=stream.read(480)
        if overflow:raise RuntimeError('Capture micro incomplete; demande abandonnee')
        values=np.asarray(raw[:,0],dtype=np.int16)
        speaking=vad.predict(values,frame_size=480)>threshold
        if speaking:speech_end=time.monotonic()
        captured=capture.feed(values.astype(np.float32)/32768,speaking)
        if captured is not None:
            return captured.audio,captured.end_reason,speech_end
        if yield_requested.is_set() and not capture.active:break
        if not capture.active and time.monotonic()-started>10:break
    return None,None,speech_end
