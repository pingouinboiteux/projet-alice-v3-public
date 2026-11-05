"""Microphone frame loop: public chat may wake silence, never discard speech."""
import time


def capture_input(stream,capture,vad,np,threshold,cancelled,yield_requested,started,
                  restart_capture=None):
    deadline=time.monotonic()+135
    speech_end=None
    consecutive_overflows=0
    while not cancelled.is_set() and time.monotonic()<deadline:
        raw,overflow=stream.read(480)
        if overflow:
            if restart_capture is None:
                raise RuntimeError('Capture micro incomplete; demande abandonnee')
            consecutive_overflows+=1
            if consecutive_overflows>=5:
                raise RuntimeError('Capture stop indisponible : debordements micro repetes')
            # Never recognise a phrase assembled across lost audio. The factory
            # replaces all state, including preroll from the incomplete fragment.
            capture=restart_capture()
            speech_end=None
            continue
        consecutive_overflows=0
        values=np.asarray(raw[:,0],dtype=np.int16)
        speaking=vad.predict(values,frame_size=480)>threshold
        if speaking:speech_end=time.monotonic()
        captured=capture.feed(values.astype(np.float32)/32768,speaking)
        if captured is not None:
            return captured.audio,captured.end_reason,speech_end
        if yield_requested.is_set() and not capture.active:break
        if not capture.active and time.monotonic()-started>10:break
    return None,None,speech_end
