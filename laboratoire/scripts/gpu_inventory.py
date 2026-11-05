"""Read-only DXGI output mapping, independent of Windows adapter numbering."""
import ctypes as C
import json
from dxgi import _Guid,_method,_AdapterDescription,enumerate_adapters


class Rect(C.Structure):
    _fields_=[(key,C.c_long) for key in ('left','top','right','bottom')]


class OutputDescription(C.Structure):
    _fields_=[('name',C.c_wchar*32),('rect',Rect),('attached',C.c_int),
              ('rotation',C.c_uint),('monitor',C.c_void_p)]


def inventory():
    dll=C.WinDLL('dxgi.dll')
    create=dll.CreateDXGIFactory1
    create.argtypes=[C.POINTER(_Guid),C.POINTER(C.c_void_p)]
    create.restype=C.c_long
    factory=C.c_void_p()
    result=create(C.byref(_Guid.parse('770aae78-f26f-4dba-a829-253c83d1b387')),C.byref(factory))
    if result<0:raise OSError(result,'CreateDXGIFactory1')
    release=C.WINFUNCTYPE(C.c_uint,C.c_void_p)
    rows=[]
    try:
        for adapter in enumerate_adapters():
            pointer=C.c_void_p()
            hr=_method(factory,12,C.WINFUNCTYPE(C.c_long,C.c_void_p,C.c_uint,C.POINTER(C.c_void_p)))(factory,adapter.index,C.byref(pointer))
            if hr<0:raise OSError(hr,'EnumAdapters1')
            try:
                outputs=[]
                index=0
                while True:
                    output=C.c_void_p()
                    hr=_method(pointer,7,C.WINFUNCTYPE(C.c_long,C.c_void_p,C.c_uint,C.POINTER(C.c_void_p)))(pointer,index,C.byref(output))
                    if hr&0xffffffff==0x887A0002:break
                    if hr<0:raise OSError(hr,'EnumOutputs')
                    try:
                        desc=OutputDescription()
                        hr=_method(output,7,C.WINFUNCTYPE(C.c_long,C.c_void_p,C.POINTER(OutputDescription)))(output,C.byref(desc))
                        if hr<0:raise OSError(hr,'GetDesc')
                        outputs.append({'name':desc.name,'attached':bool(desc.attached)})
                    finally:_method(output,2,release)(output)
                    index+=1
                rows.append({'index':adapter.index,'name':adapter.name,
                    'subsystem':f'{adapter.subsystem_id:08X}',
                    'luid':f'{adapter.luid_high&0xffffffff:08X}:{adapter.luid_low:08X}',
                    'vram_bytes':adapter.dedicated_video_memory,'outputs':outputs})
            finally:_method(pointer,2,release)(pointer)
    finally:_method(factory,2,release)(factory)
    return rows


if __name__=='__main__':
    print(json.dumps(inventory(),ensure_ascii=False))
