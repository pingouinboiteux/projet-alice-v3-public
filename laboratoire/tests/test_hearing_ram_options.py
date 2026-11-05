from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys

def test_hearing_keeps_same_model_and_cpu_provider_without_arena(monkeypatch):
    from alice.hearing import service
    class Options:
        enable_cpu_mem_arena=True
        enable_mem_pattern=True
    options=Options()
    load=Mock(return_value=object())
    monkeypatch.setitem(sys.modules,'onnxruntime',SimpleNamespace(SessionOptions=lambda:options))
    monkeypatch.setitem(sys.modules,'onnx_asr',SimpleNamespace(load_model=load))
    monkeypatch.setenv('ALICE_HEARING_DML','0')
    path=Path('models/validation_hearing')
    settings=SimpleNamespace(value=lambda group,key,kind:'same-model' if key=='hearing_architecture' else 4,
                             path=lambda key:path)
    monkeypatch.setattr(service,'load_settings',lambda:settings)
    service.load_model()
    args=load.call_args
    assert args.args==('same-model',)
    assert args.kwargs['path']==str(path)
    assert args.kwargs['providers']==['CPUExecutionProvider']
    assert args.kwargs['sess_options'] is options
    assert options.enable_cpu_mem_arena is False
    assert options.enable_mem_pattern is True
    assert options.intra_op_num_threads==4
