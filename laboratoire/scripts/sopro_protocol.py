"""Publish complete bounded WAV packets without cutting or dropping PCM samples."""
import time
import wave

RATE=24000
MIN_BYTES=2400*2
MAX_BYTES=RATE*180*2

def render_pcm(blocks,identifier,output,root,send,stream=True):
    started=time.monotonic();pending=bytearray();total=0;index=0
    target=RATE  # 0.5 s initially, then 1.5 s: at most 121 files in 180 s.
    first=None
    def publish(raw):
        nonlocal index,first
        if len(raw)<MIN_BYTES:raise ValueError('Bloc vocal trop court')
        if index>=128:raise ValueError('Trop de blocs vocaux')
        path=output/f'validation_voice_{identifier}_{index}.wav'
        try:
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(RATE);wav.writeframes(raw)
        except Exception:
            path.unlink(missing_ok=True);raise
        if first is None:first=time.monotonic()-started
        send({'status':'audio_part' if stream else 'audio','id':identifier,
              'file':path.relative_to(root).as_posix(),'part':index,
              'parts':None if stream else 1,'first_chunk_seconds':round(first,3),
              'synthesis_seconds':round(time.monotonic()-started,3)})
        index+=1
    for raw in blocks:
        if len(raw)%2:raise ValueError('PCM tronque')
        total+=len(raw)
        if total>MAX_BYTES:raise ValueError('Reponse vocale trop longue')
        pending.extend(raw)
        if stream:
            # Hold 100 ms so a tiny final tail can never become an invalid WAV.
            while len(pending)>=target+MIN_BYTES:
                publish(bytes(pending[:target]));del pending[:target]
                target=RATE*3
    if not pending:raise ValueError('Audio vide')
    publish(bytes(pending))
    if stream:send({'status':'audio_end','id':identifier,'parts':index,
                    'synthesis_seconds':round(time.monotonic()-started,3)})
