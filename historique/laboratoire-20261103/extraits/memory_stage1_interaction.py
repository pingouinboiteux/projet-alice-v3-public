"""Synthetic-only reading candidate. Historical interactions never execute tools."""
import copy
import json
from memory_stage1_deliberate import ReaderSession,MODEL_SHA
from memory_stage1_coverage import build_interaction,build_attributed,validate_interaction


class InteractionReaderSession(ReaderSession):
    reasoning_budget=2048
    cache_prompt=False

    def request(self,path,body=None,**kwargs):
        if path=='/v1/chat/completions':
            body=dict(body or {},reasoning_budget_tokens=self.reasoning_budget,cache_prompt=False)
        return super().request(path,body,**kwargs)


class DeepInteractionReaderSession(InteractionReaderSession):
    """Separate validation candidate; retained prompt with a larger reasoning cap."""
    reasoning_budget=7168


def read(session,profile,messages):
    return _read(session,profile,messages,build_interaction)


def read_attributed(session,profile,messages):
    return _read(session,profile,messages,build_attributed)


def read_deep(session,profile,messages):
    return _read(session,profile,messages,build_interaction,reasoning_budget=7168)


def _read(session,profile,messages,builder,reasoning_budget=2048):
    if not isinstance(profile,str) or not profile.startswith('validation_'):
        raise ValueError('Synthetic profile required')
    if getattr(session,'loaded_model_manifest',{}).get('sha256')!=MODEL_SHA:
        raise ValueError('Pinned candidate required')
    settings={'thinking':True,'budget':8192,'seed':42,'official_sampling':False,
        'reasoning_budget':reasoning_budget,'cache_prompt':False}
    if any(getattr(session,k,None)!=v for k,v in settings.items()):
        raise ValueError('Unmeasured reader configuration')
    original=copy.deepcopy(messages)
    wire,schema=builder(original)
    raw,seconds,usage=session.ask(wire,response_schema=schema)
    value=validate_interaction(json.loads(raw),original)
    return {'id':profile,'messages':original,'input':wire,'schema':schema,'value':value,
        'seconds':seconds,'usage':usage,'protocol_valid':True,'semantic_validated':False,
        'historical_only':True,'originals_preserved':True,'source_indices_are_advisory':True}
