"""Read-only inventory of allowed desktop applications. No focus or input APIs."""
import ctypes
import sys

import psutil


def user32():
    if sys.platform!='win32': raise OSError('native_windows_required')
    api=ctypes.WinDLL('user32',use_last_error=True)
    api.IsWindowVisible.argtypes=[ctypes.c_void_p];api.IsWindowVisible.restype=ctypes.c_int
    api.GetWindowThreadProcessId.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_uint32)]
    api.GetWindowThreadProcessId.restype=ctypes.c_uint32
    api.GetWindowTextW.argtypes=[ctypes.c_void_p,ctypes.c_wchar_p,ctypes.c_int]
    api.GetWindowTextW.restype=ctypes.c_int
    api.EnumWindows.argtypes=[ctypes.c_void_p,ctypes.c_ssize_t];api.EnumWindows.restype=ctypes.c_int
    return api


class WindowCatalog:
    def __init__(self, allowed_processes, *, api=None, process_factory=psutil.Process):
        self.allowed=frozenset(name.casefold() for name in allowed_processes)
        self.api=user32() if api is None else api
        self.process_factory=process_factory

    def _identity(self,handle):
        pid=ctypes.c_uint32()
        if not self.api.GetWindowThreadProcessId(handle,ctypes.byref(pid)) or not pid.value:
            raise RuntimeError('native_window_gone')
        process=self.process_factory(pid.value)
        name=process.name().casefold()
        if name not in self.allowed: return None
        try:
            if not process.is_running(): raise RuntimeError('native_process_gone')
            created=process.create_time()
        except psutil.AccessDenied as error:
            raise RuntimeError('native_allowed_process_unverifiable') from error
        return {'hwnd':int(handle),'pid':pid.value,'created':created},name

    def validate(self,window):
        found=self._identity(window['hwnd'])
        if found is None or found[0]!=window or not self.api.IsWindowVisible(window['hwnd']):
            raise RuntimeError('native_window_identity_changed')
        return True

    def __call__(self):
        rows,errors=[],[]
        def visit(handle,_):
            try:
                if not self.api.IsWindowVisible(handle): return 1
                identity=self._identity(handle)
                if identity is None:return 1
                window,name=identity
                text=ctypes.create_unicode_buffer(2049)
                length=self.api.GetWindowTextW(handle,text,len(text))
                if length>=2048:raise RuntimeError('native_window_title_too_long')
                # Recheck ownership after obtaining the title.
                self.validate(window)
                rows.append({'window':window,'process_name':name,'title':text.value,'visible':True})
            except psutil.NoSuchProcess:
                return 1
            except psutil.AccessDenied:
                # An unreadable process must not become an eligible candidate.
                return 1
            except Exception as error:
                errors.append(error)
                return 0
            return 1
        callback_type=getattr(ctypes,'WINFUNCTYPE',ctypes.CFUNCTYPE)(ctypes.c_int,ctypes.c_void_p,ctypes.c_ssize_t)
        callback=callback_type(visit)
        success=self.api.EnumWindows(callback,0)
        if errors:raise errors[0]
        if not success:raise RuntimeError('native_window_inventory_failed')
        return rows
