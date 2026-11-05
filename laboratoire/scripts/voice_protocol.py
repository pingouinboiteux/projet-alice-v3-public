"""Publish only complete, validated audio files, preserving synthesis chunks."""
import time
import wave


def render(text,identifier,output,root,synthesize,chunks,sentences,send,stream=False):
    started=time.monotonic()
    parts=chunks(text)
    first=None
    frames=0
    files=[]
    try:
        if stream:
            # Keep the original synthesis boundaries; wait for the whole first
            # sentence before playback, not the shortened first synthesis chunk.
            sentence=sentences(text)[0]
            count=next((i for i in range(1,len(parts)+1) if ' '.join(parts[:i])==sentence),len(parts))
            groups=[parts[:count]]+[[part] for part in parts[count:]]
        else:
            groups=[parts]
        if not groups or len(groups)>128: raise RuntimeError('Trop de blocs vocaux')
        for index,group in enumerate(groups):
            path=output/f'validation_voice_{identifier}_{index}.wav'
            files.append(path)
            with wave.open(str(path),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000)
                for part in group:
                    pcm=synthesize(part)  # Existing EOS, duration and sample guards.
                    frames+=len(pcm)
                    if frames>24000*180: raise RuntimeError('Reponse vocale trop longue')
                    if first is None: first=time.monotonic()-started
                    wav.writeframes(pcm.tobytes())
            send({'status':'audio_part' if stream else 'audio','id':identifier,
                'file':path.relative_to(root).as_posix(),'part':index,'parts':len(groups),
                'chunks':len(parts),'first_chunk_seconds':round(first,3),
                'synthesis_seconds':round(time.monotonic()-started,3)})
        if stream:
            send({'status':'audio_end','id':identifier,'parts':len(groups),
                  'synthesis_seconds':round(time.monotonic()-started,3)})
    except Exception:
        # Earlier complete parts may already be playing. Only the unfinished
        # current file is unsafe; the parent owns cleanup of delivered parts.
        if files: files[-1].unlink(missing_ok=True)
        raise
