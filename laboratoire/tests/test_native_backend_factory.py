from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from native_backend_factory import NativeBackendFactory


WINDOW={'hwnd':1,'pid':2,'created':3}


def setup():
    catalog,reader,observer,transport=Mock(),Mock(),Mock(),Mock()
    observer.read.return_value={'window':WINDOW,'foreground':True}
    factory=NativeBackendFactory(catalog,lambda:None,reader_factory=Mock(return_value=reader),
        observer_factory=Mock(return_value=observer),transport_factory=Mock(return_value=transport))
    return factory,catalog,reader,observer,transport


def test_owned_reader_closes_and_input_stops_on_normal_exit():
    f,c,r,o,t=setup()
    with f(WINDOW,cancelled=lambda:False) as backend:
        assert backend.observer is o and backend.transport is t
    r.close.assert_called_once();t.cancel.assert_called_once()
    assert c.validate.call_count==2


def test_cancel_before_launch():
    f,c,r,o,t=setup()
    with pytest.raises(RuntimeError):
        with f(WINDOW,cancelled=lambda:True):pass
    f.reader_factory.assert_not_called();f.transport_factory.assert_not_called()


@pytest.mark.parametrize('fault',['focus','identity','timeout'])
def test_bad_observation_never_provides_input_transport(fault):
    f,c,r,o,t=setup()
    if fault=='focus':o.read.return_value['foreground']=False
    if fault=='identity':o.read.return_value['window']=dict(WINDOW,pid=99)
    if fault=='timeout':o.read.side_effect=TimeoutError()
    with pytest.raises(Exception):
        with f(WINDOW,cancelled=lambda:False):pass
    f.transport_factory.assert_not_called();r.close.assert_called_once()


def test_action_exception_still_closes_reader():
    f,c,r,o,t=setup()
    with pytest.raises(ValueError):
        with f(WINDOW,cancelled=lambda:False):raise ValueError('fixture')
    r.close.assert_called_once();t.cancel.assert_called_once()


@pytest.mark.parametrize('canonical_first', [False, True])
def test_backend_aliases_in_fresh_process(canonical_first):
    """Both import orders share classes, defaults and patched loader globals."""
    import subprocess
    code = r'''
import ctypes
import importlib
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
def forbidden(*args, **kwargs):
    raise AssertionError('Real DLL or worker launch forbidden')
ctypes.WinDLL = forbidden
subprocess.Popen = forbidden
names = ('native_backend_factory', 'native_window_catalog',
         'native_window_focus', 'native_win32_input')
if sys.argv[2] == 'True':
    modules = [importlib.import_module('controle.laboratoire.' + n) for n in names]
    assert str(root / 'laboratoire/scripts') not in sys.path
    sys.path.insert(0, str(root / 'laboratoire/scripts'))
    aliases = [importlib.import_module(n) for n in names]
else:
    sys.path.insert(0, str(root / 'laboratoire/scripts'))
    aliases = [importlib.import_module(n) for n in names]
    modules = [importlib.import_module('controle.laboratoire.' + n) for n in names]
for module, alias in zip(modules, aliases):
    assert module is alias
    for name, value in vars(module).items():
        assert getattr(alias, name) is value
factory, catalog, focus, transport = modules
import psutil
from vision.laboratoire.native_uia_worker import UIAWorker
from vision.laboratoire.native_uia_observer import UIAObserver
defaults = factory.NativeBackendFactory.__init__.__kwdefaults__
assert defaults['reader_factory'] is UIAWorker
assert defaults['observer_factory'] is UIAObserver
assert defaults['transport_factory'] is transport.Win32Input
assert catalog.WindowCatalog.__init__.__kwdefaults__['process_factory'] is psutil.Process
api = Mock()
aliases[1].user32 = lambda: api
assert catalog.WindowCatalog([], process_factory=Mock()).api is api
aliases[2]._load_user32 = lambda: api
assert focus.NativeWindowFocus(Mock(), Mock()).api is api
aliases[3]._load_user32 = lambda: api
assert transport.Win32Input()._api is api
'''
    subprocess.run([sys.executable, '-I', '-c', code,
                    str(Path(__file__).resolve().parents[2]), str(canonical_first)],
                   check=True, capture_output=True, text=True, timeout=30)
