"""Owned reader/input lifecycle for one authorized window.

Optional focus callback is provided by the trusted local desktop boundary.
Without it, an already foreground window is required.
"""
from contextlib import contextmanager
from types import SimpleNamespace

from vision.laboratoire.native_uia_worker import UIAWorker
from vision.laboratoire.native_uia_observer import UIAObserver
from .native_win32_input import Win32Input


class NativeBackendFactory:
    def __init__(self,catalog,guard,*,reader_factory=UIAWorker,
                 observer_factory=UIAObserver,transport_factory=Win32Input,
                 typing_context_factory=None, focus=None):
        self.catalog,self.guard=catalog,guard
        self.reader_factory,self.observer_factory,self.transport_factory=reader_factory,observer_factory,transport_factory
        self.typing_context_factory=typing_context_factory
        self.focus=focus

    @contextmanager
    def __call__(self,window,*,cancelled):
        reader=transport=None
        try:
            self.guard()
            if cancelled():raise RuntimeError('native_backend_cancelled')
            self.catalog.validate(window)
            if self.focus is not None:
                self.focus(window,cancelled=cancelled)
            reader=self.reader_factory(window)
            observer=self.observer_factory(window,worker=reader)
            # Refuse absent foreground before making a transport available.
            state=observer.read()
            if state['window']!=window or state.get('foreground') is not True:
                raise RuntimeError('native_backend_focus_required')
            self.catalog.validate(window)
            self.guard()
            if cancelled():raise RuntimeError('native_backend_cancelled')
            transport=self.transport_factory()
            yield SimpleNamespace(observer=observer,transport=transport,
                                  typing_context_factory=self.typing_context_factory)
        finally:
            try:
                if transport is not None:transport.cancel()
            finally:
                if reader is not None:reader.close()
