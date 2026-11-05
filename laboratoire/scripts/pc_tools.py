"""Small Windows capabilities. No shell, arbitrary command, or elevation."""
import ctypes as C
from contextlib import contextmanager
import time
import json
import re
import subprocess
from dxgi import _Guid, _method
from dxgi import enumerate_adapters
from chat import free_ram, processes, GAMES, ROOT


def checked(result):
    if result < 0:
        raise OSError(result, 'Operation Windows refusee')


@contextmanager
def endpoint_volume():
    ole = C.OleDLL('ole32')
    ole.CoInitializeEx.argtypes = [C.c_void_p, C.c_uint32]
    ole.CoInitializeEx.restype = C.c_long
    hr = ole.CoInitializeEx(None, 0)
    checked(hr)
    pointers = []
    try:
        enum = C.c_void_p()
        create = ole.CoCreateInstance
        create.argtypes = [C.POINTER(_Guid), C.c_void_p, C.c_uint32, C.POINTER(_Guid), C.POINTER(C.c_void_p)]
        create.restype = C.c_long
        checked(create(C.byref(_Guid.parse('BCDE0395-E52F-467C-8E3D-C4579291692E')),
            None, 1, C.byref(_Guid.parse('A95664D2-9614-4F35-A746-DE8DB63617E6')), C.byref(enum)))
        pointers.append(enum)
        device = C.c_void_p()
        checked(_method(enum, 4, C.WINFUNCTYPE(C.c_long, C.c_void_p, C.c_int,
            C.c_int, C.POINTER(C.c_void_p)))(enum, 0, 1, C.byref(device)))
        pointers.append(device)
        volume = C.c_void_p()
        checked(_method(device, 3, C.WINFUNCTYPE(C.c_long, C.c_void_p, C.POINTER(_Guid),
            C.c_uint32, C.c_void_p, C.POINTER(C.c_void_p)))(device,
            C.byref(_Guid.parse('5CDF2C82-841E-4546-9722-0CF74078229A')), 23, None, C.byref(volume)))
        pointers.append(volume)
        yield volume
    finally:
        for p in reversed(pointers):
            _method(p, 2, C.WINFUNCTYPE(C.c_uint32, C.c_void_p))(p)
        ole.CoUninitialize()


def read_volume():
    with endpoint_volume() as p:
        value, mute = C.c_float(), C.c_int()
        checked(_method(p, 9, C.WINFUNCTYPE(C.c_long, C.c_void_p, C.POINTER(C.c_float)))(p, C.byref(value)))
        checked(_method(p, 15, C.WINFUNCTYPE(C.c_long, C.c_void_p, C.POINTER(C.c_int)))(p, C.byref(mute)))
        return {'percent': round(value.value * 100), 'muted': bool(mute.value)}


def set_volume(percent):
    if type(percent) is not int or not 0 <= percent <= 100:
        raise ValueError('Volume invalide')
    with endpoint_volume() as p:
        checked(_method(p, 7, C.WINFUNCTYPE(C.c_long, C.c_void_p, C.c_float, C.c_void_p))(p, percent/100, None))
    result = read_volume()
    if abs(result['percent'] - percent) > 1:
        raise RuntimeError('Windows ne confirme pas le volume demande')
    return result


def set_mute(muted):
    if type(muted) is not bool:
        raise ValueError('Etat muet invalide')
    with endpoint_volume() as p:
        checked(_method(p, 14, C.WINFUNCTYPE(C.c_long, C.c_void_p, C.c_int, C.c_void_p))(p, muted, None))
    result = read_volume()
    if result['muted'] != muted:
        raise RuntimeError('Windows ne confirme pas le mode muet')
    return result


class Monitor:
    def __init__(self):
        self.previous = None

    def sample(self):
        idle, kernel, user = C.c_uint64(), C.c_uint64(), C.c_uint64()
        if not C.windll.kernel32.GetSystemTimes(C.byref(idle), C.byref(kernel), C.byref(user)):
            raise C.WinError()
        total = kernel.value + user.value
        cpu = None
        if self.previous:
            dt = total - self.previous[0]
            if dt > 0:
                cpu = round(100 * (1 - (idle.value - self.previous[1]) / dt), 1)
        self.previous = total, idle.value
        names = processes()
        return {'measured_at': time.monotonic(), 'ram_free_gib': round(free_ram()/1024**3, 2),
                'cpu_percent': cpu, 'programs': sorted(names), 'games': sorted(names & GAMES),
                'gpu_usage': None}


def gpu_memory():
    """OS adapter totals, not a claim that every byte belongs to Alice."""
    completed = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
        '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'scripts/mesurer_entrainement_windows.ps1')],
        cwd=ROOT, capture_output=True, timeout=15, check=True,
        creationflags=subprocess.CREATE_NO_WINDOW)
    snapshot = json.loads(completed.stdout.decode('utf-8-sig'))
    adapters = {(a.luid_high & 0xffffffff, a.luid_low): a for a in enumerate_adapters()}
    rows = []
    for entry in snapshot['adapters']:
        match = re.search(r'luid_0x([0-9a-f]+)_0x([0-9a-f]+)', entry['Name'], re.I)
        if not match:
            continue
        adapter = adapters.get((int(match[1], 16), int(match[2], 16)))
        if adapter is None:
            continue
        rows.append({'name': adapter.name, 'alice_gpu': adapter.subsystem_id == 0x240E1458,
                     'dedicated_used_gib': round(int(entry['DedicatedUsage']) / 1024**3, 2),
                     'shared_used_gib': round(int(entry['SharedUsage']) / 1024**3, 2),
                     'capacity_gib': round(adapter.dedicated_video_memory / 1024**3, 2)})
    if sum(row['alice_gpu'] for row in rows) != 1:
        raise RuntimeError('Mesure GPU ambiguë ou absente')
    return rows
