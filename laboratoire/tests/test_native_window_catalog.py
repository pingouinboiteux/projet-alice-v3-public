import ctypes
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_window_catalog import WindowCatalog


def setup():
    api=Mock()
    api.IsWindowVisible.return_value=1
    def pid(hwnd,pointer):
        ctypes.cast(pointer,ctypes.POINTER(ctypes.c_uint32))[0]=hwnd+10
        return 1
    api.GetWindowThreadProcessId.side_effect=pid
    def title(hwnd,buffer,size):buffer.value='Notes';return 5
    api.GetWindowTextW.side_effect=title
    def enum(callback,_):
        return int(all(callback(hwnd,0) for hwnd in (1,2)))
    api.EnumWindows.side_effect=enum
    def process(pid):
        p=Mock();p.name.return_value='notepad.exe' if pid==11 else 'brave.exe'
        p.create_time.return_value=100;p.is_running.return_value=True
        return p
    return WindowCatalog(['notepad.exe'],api=api,process_factory=process),api


def test_catalog_only_returns_allowed_processes_without_focus_api():
    c,a=setup()
    assert c()==[{'window':{'hwnd':1,'pid':11,'created':100},'process_name':'notepad.exe','title':'Notes','visible':True}]
    a.SetForegroundWindow.assert_not_called()
    a.GetWindowTextW.assert_called_once()


def test_process_identity_rechecked():
    c,a=setup()
    with pytest.raises(RuntimeError):c.validate({'hwnd':1,'pid':11,'created':99})


def test_enumeration_failure_is_not_empty_success():
    c,a=setup();a.EnumWindows.side_effect=None;a.EnumWindows.return_value=0
    with pytest.raises(RuntimeError):c()


def test_truncated_title_is_not_used():
    c,a=setup();a.GetWindowTextW.side_effect=None;a.GetWindowTextW.return_value=2048
    with pytest.raises(RuntimeError):c()
