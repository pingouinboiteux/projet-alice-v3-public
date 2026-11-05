"""Private pipe worker: exact Alice voice synthesis, no microphone or HTTP service."""
import contextlib
import json
import os
from pathlib import Path
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
os.environ['ALICE_ROOT'] = str(ROOT)
os.environ['ALICE_USER'] = 'validation_lab_voice'
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
for key, relative in {'XDG_CACHE_HOME': 'cache', 'HF_HOME': 'cache/huggingface',
                      'TORCH_HOME': 'cache/torch', 'MIOPEN_USER_DB_PATH': 'cache/miopen',
                      'MIOPEN_CUSTOM_CACHE_DIR': 'cache/miopen'}.items():
    os.environ[key] = str(ROOT / relative)
sys.path.insert(0, str(ROOT / 'src'))


def send(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def main():
    output = (ROOT / sys.argv[1]).resolve()
    if not output.is_relative_to(ROOT / 'logs') or not output.is_dir():
        raise RuntimeError('Invalid private output directory')
    os.environ['ALICE_LOG_DIRECTORY'] = str(output)
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import torch
        from alice.hardware import alice_pci_bus
        from alice.voice import service
        from alice.voice.text import chunks, sentences
        from voice_protocol import render
        from voice_loading import load_on_selected_device
        service.load_on_selected_device = load_on_selected_device
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        bus = alice_pci_bus()
        matches = [i for i in range(torch.cuda.device_count())
                   if int(getattr(torch.cuda.get_device_properties(i), 'pci_bus_id', -1)) == bus]
        if len(matches) != 1:
            raise RuntimeError('Voice GPU identity ambiguous')
        device = f'cuda:{matches[0]}'
        torch.cuda.set_device(matches[0])
        service.TORCH, service.NUMPY = torch, np
        start = time.monotonic()
        service._load_model(device)
    def measured_send(value):
        if value.get('status') in {'ready','audio_end','audio'}:
            value['gpu_memory']={'allocated_bytes':torch.cuda.memory_allocated(),
                'reserved_bytes':torch.cuda.memory_reserved(),
                'peak_allocated_bytes':torch.cuda.max_memory_allocated()}
        send(value)
    measured_send({'status': 'ready', 'sample_rate': service.SAMPLE_RATE,
          'device': device, 'pci_bus': bus, 'load_seconds': round(time.monotonic()-start, 3)})
    for line in sys.stdin:
        request = json.loads(line)
        text = request['text']
        identifier = request['id']
        if not isinstance(text, str) or not 1 <= len(text) <= 2000:
            send({'status': 'error', 'error': 'Texte vocal vide ou trop long'})
            continue
        if not isinstance(identifier, int) or identifier < 0:
            raise ValueError('Invalid request id')
        try:
            def synthesize(part):
                with contextlib.redirect_stdout(sys.stderr):
                    return service.synthesize(part)
            render(text,identifier,output,ROOT,synthesize,chunks,sentences,measured_send,
                   stream=request.get('stream') is True)
        except Exception as error:
            send({'status': 'error','id':identifier, 'error': str(error)})


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
