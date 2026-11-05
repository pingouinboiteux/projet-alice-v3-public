"""Native Sopro with Alice's original sample; no microphone or memory access."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ.update(ALICE_ROOT=str(ROOT),ALICE_USER='validation_sopro_voice',HF_HUB_OFFLINE='1',
    TRANSFORMERS_OFFLINE='1',HF_HOME=str(ROOT/'cache/huggingface'),
    MIOPEN_USER_DB_PATH=str(ROOT/'cache/miopen'),MIOPEN_CUSTOM_CACHE_DIR=str(ROOT/'cache/miopen'),
    TORCH_HOME=str(ROOT/'cache/torch'))
sys.path.insert(0,str(ROOT/'src'))

def send(value):print(json.dumps(value,ensure_ascii=False),flush=True)

def main():
    from voice_profile import sopro_settings
    from sopro_protocol import render_pcm
    output=(ROOT/sys.argv[1]).resolve()
    if not output.is_relative_to(ROOT/'logs') or not output.is_dir():raise ValueError('Invalid voice output')
    config=sopro_settings()
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import torch
        from sopro import SoproTTS,__version__
        from alice.hardware import alice_pci_bus
        if __version__!='2.2.0':raise RuntimeError('Version Sopro non validee')
        torch.set_num_threads(4);torch.set_num_interop_threads(1)
        bus=alice_pci_bus()
        indices=[i for i in range(torch.cuda.device_count()) if int(torch.cuda.get_device_properties(i).pci_bus_id)==bus]
        if len(indices)!=1:raise RuntimeError('Carte vocale ambigue')
        torch.cuda.set_device(indices[0]);device=f'cuda:{indices[0]}'
        started=time.monotonic()
        # Avoid constructing a full CPU model before copying it onto the GPU.
        # Same FP32 state and bit-identical audio verified in isolated controls.
        with torch.device(device):
            model=SoproTTS.from_pretrained(ROOT/config['model'],device=device)
        model.generation.steps=config['steps']
        reference=model.prepare_reference(ref_audio_path=ROOT/config['reference'],
                                          seconds=config.get('reference_seconds',10),stream=True)
        original=model.model.stream_semantic_tokens
        def complete_semantics(*args,**kwargs):
            count=0
            for tokens in original(*args,**kwargs):
                count+=tokens.shape[-1]
                yield tokens
            if count>=kwargs['max_steps']:
                raise RuntimeError('Limite vocale atteinte avant la fin naturelle')
        model.model.stream_semantic_tokens=complete_semantics
        # Warm kernels before interactive use, without playback or memory access.
        with torch.inference_mode():
            for _ in model.stream('La voix est prête.',ref=reference,lang='fr'):pass
    def measured(value):
        if value['status'] in {'ready','audio_end','audio'}:
            value['gpu_memory']={'allocated_bytes':torch.cuda.memory_allocated(),
                'reserved_bytes':torch.cuda.memory_reserved(),'peak_allocated_bytes':torch.cuda.max_memory_allocated()}
        send(value)
    measured({'status':'ready','backend':'sopro_original','sample_rate':24000,'device':device,
              'pci_bus':bus,'steps':config['steps'],'load_seconds':round(time.monotonic()-started,3),
              'backend_version':__version__,
              'reference_file':config['reference'],
              'reference_window_seconds':config.get('reference_seconds',10),
              'reference_prepared_seconds':round(reference.mel.shape[-1]*model.vocoder.hop_length/24000,4),
              'reference_sha256':hashlib.sha256((ROOT/config['reference']).read_bytes()).hexdigest(),
              'prompt_noise_sha256':hashlib.sha256(reference.prompt_states[
                  (config['steps'],model.generation.stream_chunk_frames)].noise.detach().cpu().contiguous().numpy().tobytes()).hexdigest()})
    for line in sys.stdin:
        identifier=None
        try:
            request=json.loads(line);identifier=request.get('id');text=request.get('text')
            if type(identifier) is not int or identifier<0:raise ValueError('Invalid request id')
            if not isinstance(text,str) or not text.strip() or len(text)>2000:raise ValueError('Texte vocal vide ou trop long')
            def blocks():
                # Scope stdout redirection around next(), never across a yield.
                iterator=iter(model.stream(text,ref=reference,lang=config['language']))
                while True:
                    with contextlib.redirect_stdout(sys.stderr),torch.inference_mode():
                        try:block=next(iterator)
                        except StopIteration:return
                        values=block.squeeze().detach().cpu().numpy()
                    if values.ndim!=1 or not np.isfinite(values).all():raise ValueError('Audio invalide')
                    yield np.clip(values*32768,-32768,32767).astype('<i2').tobytes()
            render_pcm(blocks(),identifier,output,ROOT,measured,stream=request.get('stream') is True)
        except Exception as error:
            measured({'status':'error','id':identifier,'error':str(error)})

if __name__=='__main__':main()
