"""Bounded, read-only UI Automation observation of one explicitly bound window.

The runner seam is subprocess.run-compatible; tests never inspect the desktop.
Provider errors and timeouts propagate. A snapshot cannot make desktop focus
atomic: the action adapter must independently recheck before dispatch.
"""
from copy import deepcopy
import json
import math
from pathlib import Path
import subprocess

import psutil


class UIAObserver:
    def __init__(self, window, runner=None, process_factory=None, worker=None):
        if (type(window) is not dict or set(window) != {'hwnd', 'pid', 'created'}
                or any(type(window[k]) is not int or window[k] <= 0 for k in ('hwnd', 'pid'))
                or type(window['created']) not in (int, float)
                or not math.isfinite(window['created']) or window['created'] <= 0):
            raise ValueError('invalid_native_window_identity')
        self.window = deepcopy(window)
        self._runner = runner or subprocess.run
        self._process = process_factory or psutil.Process
        self._worker = worker

    def _check_process(self):
        process = self._process(self.window['pid'])
        if not process.is_running() or process.create_time() != self.window['created']:
            raise RuntimeError('native_process_changed')

    @staticmethod
    def _rectangle(value):
        if (type(value) is not list or len(value) != 4
                or any(type(v) not in (int, float) or not math.isfinite(v) for v in value)
                or value[2] < 0 or value[3] < 0):
            raise ValueError('invalid_native_geometry')
        return value

    def _capture(self, extra=()):
        self._check_process()
        # Relative path is resolved with a controlled repository-root cwd.
        root = Path(__file__).resolve().parents[2]
        command = ['powershell.exe', '-NoLogo', '-NoProfile', '-NonInteractive',
                   '-File', 'vision/laboratoire/native_uia_snapshot.ps1',
                   '-WindowHandle', str(self.window['hwnd']),
                   '-ExpectedProcessId', str(self.window['pid']), *extra]
        if self._worker is not None:
            data = (self._worker.request('hit_test', x=int(extra[2]), y=int(extra[4]))
                    if extra else self._worker.request('read'))
        else:
            result = self._runner(command, cwd=root, capture_output=True, check=True,
                                  timeout=8, encoding='utf-8', errors='strict',
                                  creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            data = json.loads(result.stdout.lstrip('\ufeff'))
        self._check_process()
        for key in ('checks_before', 'checks_after'):
            check = data[key]
            if (check.get('hwnd') != self.window['hwnd'] or check.get('pid') != self.window['pid']
                    or check.get('available') is not True or check.get('foreground') is not True):
                raise RuntimeError('native_window_or_focus_changed')
        return data

    def read(self):
        data = self._capture()
        elements = data['elements']
        if type(elements) is not list or len(elements) > 200 or type(data['truncated']) is not bool:
            raise ValueError('invalid_native_snapshot')
        seen = set()
        for element in elements:
            if (type(element) is not dict or type(element.get('id')) is not str
                    or not element['id'] or element['id'] in seen
                    or any(type(element.get(k)) is not str for k in ('name', 'type'))
                    or any(type(element.get(k)) is not bool for k in ('enabled', 'visible', 'focused', 'password'))
                    or (element.get('parent_id') is not None and type(element['parent_id']) is not str)
                    or (element.get('value') is not None and type(element['value']) is not str)):
                raise ValueError('invalid_native_element')
            seen.add(element['id'])
            if 'editable' in element and type(element['editable']) is not bool:
                raise ValueError('invalid_native_editable_flag')
            element.setdefault('editable', False)
            if element.get('selected') is not None and type(element['selected']) is not bool:
                raise ValueError('invalid_native_selected_flag')
            element.setdefault('selected', None)
            self._rectangle(element['rect'])
            if element['password']:
                element['name'], element['value'] = '', None
            if len(element['name']) > 4000 or (element['value'] is not None and len(element['value']) > 4000):
                raise ValueError('native_text_too_large')
        for element in elements:
            parent = element.get('parent_id')
            if parent is not None and (parent not in seen or parent == element['id']):
                raise ValueError('invalid_native_parent')
        return {'window': deepcopy(self.window), 'foreground': True, 'available': True,
                'geometry': self._rectangle(data['geometry']), 'elements': elements,
                'truncated': data['truncated']}

    def hit_test(self, x, y):
        if any(type(v) is not int or not -(2**31) <= v < 2**31 for v in (x, y)):
            raise ValueError('invalid_native_point')
        data = self._capture(['-HitTest', '-PointX', str(x), '-PointY', str(y)])
        if type(data.get('hit_id')) is not str or not data['hit_id']:
            raise ValueError('native_hit_unavailable')
        return data['hit_id']
