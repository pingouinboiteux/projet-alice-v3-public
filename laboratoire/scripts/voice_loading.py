"""Load identical voice weights one component at a time onto the selected GPU.

Unlike the original CPU-first whole-model loader this releases each checkpoint
before constructing the next component. No precision or voice parameter change.
"""
def load_on_selected_device(factory, path, device):
    import gc
    from pathlib import Path
    import torch
    from chatterbox import mtl_tts as m
    directory = Path(path)
    ve = m.VoiceEncoder()
    weights = torch.load(directory / 've.pt', map_location='cpu', weights_only=True, mmap=True)
    ve.load_state_dict(weights, strict=True)
    ve.to(device).eval()
    del weights
    gc.collect()
    t3 = m.T3(m.T3Config.multilingual())
    weights = m.load_safetensors(directory / m._resolve_multilingual_t3_model('v3'))
    if 'model' in weights:
        weights = weights['model'][0]
    t3.load_state_dict(weights, strict=True)
    t3.to(device).eval()
    del weights
    gc.collect()
    s3gen = m.S3Gen()
    weights = torch.load(directory / 's3gen.pt', map_location='cpu', weights_only=True, mmap=True)
    s3gen.load_state_dict(weights, strict=True)
    s3gen.to(device).eval()
    del weights
    gc.collect()
    tokenizer = m.MTLTokenizer(str(directory / 'grapheme_mtl_merged_expanded_v1.json'))
    conds = None
    if (directory / 'conds.pt').exists():
        conds = m.Conditionals.load(directory / 'conds.pt', map_location='cpu').to(device)
    return factory(t3, s3gen, ve, tokenizer, device, conds=conds)
