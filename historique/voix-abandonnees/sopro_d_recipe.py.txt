"""Candidate D recipe: independent reproducible RNG streams, no text exceptions.

For the sequential private worker only. The reference, semantic sampler and
acoustic solver use independent state; acoustic draws cannot change sampling
of subsequent speech tokens. Nothing is cached as a predefined response.
"""
from contextlib import contextmanager

REFERENCE_SEED=5151
SEMANTIC_SEED=20261105
ACOUSTIC_SEED=6001


@contextmanager
def rng_scope(torch, device, seed=None, state=None):
    with torch.random.fork_rng(devices=[device]), torch.cuda.device(device):
        if state is None:
            torch.default_generator.manual_seed(seed)
            torch.cuda.manual_seed(seed)
        else:
            torch.set_rng_state(state[0]);torch.cuda.set_rng_state(state[1],device)
        yield


def isolated_semantics(original, torch, device):
    def stream(*args,**kwargs):
        with rng_scope(torch,device,SEMANTIC_SEED):
            iterator=iter(original(*args,**kwargs))
            state=(torch.get_rng_state(),torch.cuda.get_rng_state(device))
        try:
            while True:
                with rng_scope(torch,device,state=state):
                    try:chunk=next(iterator)
                    except StopIteration:return
                    state=(torch.get_rng_state(),torch.cuda.get_rng_state(device))
                # Never keep a changed global RNG state across a yield.
                yield chunk
        finally:
            with rng_scope(torch,device,state=state):
                close=getattr(iterator,'close',None)
                if close:close()
    return stream


class DRecipe:
    def __init__(self,model,reference,torch):
        self.model=model;self.reference=reference;self.torch=torch
        self.device=model.device.index
        self.original=model._semantic_stream
        self.semantic=isolated_semantics(self.original,torch,self.device)
        self.active=False
        reference.prompt_states.clear()
        with rng_scope(torch,self.device,REFERENCE_SEED):
            model._prompt_state(reference,8,model.generation.stream_chunk_frames)

    def stream(self,text,lang='fr'):
        if self.active:raise RuntimeError('Concurrent voice request')
        self.active=True
        previous=self.model._semantic_stream
        try:
            self.model._semantic_stream=self.semantic
            with rng_scope(self.torch,self.device,ACOUSTIC_SEED):
                yield from self.model.stream(text,ref=self.reference,lang=lang,steps=8)
        finally:
            self.model._semantic_stream=previous
            self.active=False
