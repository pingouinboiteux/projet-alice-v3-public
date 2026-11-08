"""Installed Brave in a dedicated visible window; no global mouse/keyboard input.

Native browser networking, not the static HTML proxy. DNS checks reject known
private destinations but do not pin Chromium's subsequent DNS resolution. The
launch gate refuses known games until focus behaviour has been measured.
"""
import copy
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import tempfile
import threading
import time
from urllib.parse import parse_qsl, urljoin, urlsplit

import psutil
from observer_browser import BrowserDemo, ROOT, fingerprint
from public_navigation import canonical_url
from rendered_observation import observe_page, check_snapshot
from rendered_links import observe_links, links_current
from web_reader import public_addresses

MAX_REQUESTS_PER_NAVIGATION = 400
MAX_TOTAL_REQUESTS = 1600
MAX_NAVIGATIONS = 10


def search_identity(url):
    """Only the measured conversation token may vary within a search."""
    parts = urlsplit(url)
    if (parts.scheme != 'https' or parts.netloc != 'search.brave.com'
            or parts.path != '/search' or parts.fragment or len(parts.query) > 4096):
        raise ValueError('brave_search_scope_changed')
    pairs = parse_qsl(parts.query, keep_blank_values=True, strict_parsing=True,
                      errors='strict', max_num_fields=20)
    queries = [value for key, value in pairs if key == 'q']
    tokens = [value for key, value in pairs if key == 'conversation']
    if len(queries) != 1 or not queries[0] or len(tokens) > 1:
        raise ValueError('brave_search_scope_changed')
    if tokens and (not 1 <= len(tokens[0]) <= 128
                   or any(not (c.isascii() and (c.isalnum() or c == '-')) for c in tokens[0])):
        raise ValueError('brave_search_scope_changed')
    return tuple(sorted((key, value) for key, value in pairs if key != 'conversation'))


def discover_brave():
    candidates = []
    for variable in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA'):
        if os.environ.get(variable):
            candidates.append(Path(os.environ[variable]) / 'BraveSoftware/Brave-Browser/Application/brave.exe')
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r'Software\Microsoft\Windows\CurrentVersion\App Paths\brave.exe') as key:
                    candidates.append(Path(winreg.QueryValueEx(key, '')[0].strip('"')))
            except OSError:
                pass
    for path in candidates:
        if path.name.lower() == 'brave.exe' and path.is_file():
            return path.resolve()
    raise RuntimeError('Brave installe introuvable. Aucun autre navigateur ne sera utilise.')


def safe_launch_gate():
    from chat import GAMES, processes
    if GAMES & processes():
        raise RuntimeError('Brave visible non qualifie pendant le jeu : lancement refuse.')


def secondary_bounds():
    """Work area of a non-primary monitor, or primary when only one exists."""
    if os.name != 'nt':
        raise RuntimeError('Le navigateur de bureau exige Windows.')
    class Info(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                    ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
    api = ctypes.WinDLL('user32', use_last_error=True)
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HANDLE,
                                      wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    api.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(Info)]
    api.EnumDisplayMonitors.argtypes = [wintypes.HDC, ctypes.POINTER(wintypes.RECT), callback_type, wintypes.LPARAM]
    monitors = []
    def visit(handle, _dc, _rect, _data):
        info = Info(); info.size = ctypes.sizeof(info)
        if api.GetMonitorInfoW(handle, ctypes.byref(info)):
            r = info.work
            monitors.append((bool(info.flags & 1), r.left, r.top, r.right-r.left, r.bottom-r.top))
        return True
    if not api.EnumDisplayMonitors(None, None, callback_type(visit), 0) or not monitors:
        raise RuntimeError('Disposition des ecrans indisponible.')
    _, x, y, width, height = sorted(monitors)[0]
    return (x, y, min(1100, width), min(800, height))


def require_profile_available(path):
    """Read only Brave commands; Chromium still arbitrates a concurrent launch."""
    expected = os.path.normcase(str(path.resolve()))
    for process in psutil.process_iter():
        try:
            if process.name().lower() not in ('brave', 'brave.exe'):
                continue
            command = process.cmdline()
            if not command:
                raise RuntimeError('brave_profile_occupancy_unknown')
            for index, argument in enumerate(command):
                if argument == '--user-data-dir':
                    if index + 1 >= len(command):
                        raise RuntimeError('brave_profile_occupancy_unknown')
                    value = command[index + 1]
                elif argument.startswith('--user-data-dir='):
                    value = argument.split('=', 1)[1]
                else:
                    continue
                value = value.strip('"')
                if not value or not Path(value).is_absolute():
                    raise RuntimeError('brave_profile_occupancy_unknown')
                if os.path.normcase(str(Path(value).resolve())) == expected:
                    raise RuntimeError('brave_validation_profile_in_use: close its window first')
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as error:
            raise RuntimeError('brave_profile_occupancy_unknown') from error


class BraveDesktopBrowser(BrowserDemo):
    def __init__(self, guard, *, budget_seconds=90, launch_gate=None, validation_profile=False):
        super().__init__(guard)
        if type(validation_profile) is not bool:
            raise ValueError('invalid_validation_profile')
        if type(budget_seconds) not in (int, float) or not 0 < budget_seconds <= 180:
            raise ValueError('invalid_brave_budget')
        self.budget_seconds = budget_seconds
        self.launch_gate = launch_gate or safe_launch_gate
        self.deadline = None
        self.target = None
        self.blocked = self.requests = 0
        self.navigation_requests = self.navigations = 0
        self.timed_out = False
        self._watchdog = self._profile = None
        self._navigation = False
        self.validation_profile = validation_profile
        self.persistent_profile_path = None
        self.validation_pages_close_failed = False
        self._search_identity = None
        self._search_active = False

    def _browser_args(self):
        args = super()._browser_args()
        if self.validation_profile:
            args.remove('--disable-extensions')
        return args

    def _check(self):
        self.guard()
        if self._stopping or self.closed:
            raise RuntimeError('brave_stopped')
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise TimeoutError('brave_deadline')

    def _expire(self):
        self.timed_out = True
        self.stop_owned()

    def _public(self, url):
        value = canonical_url(url)
        public_addresses(urlsplit(value).hostname)
        self._check()
        return value

    def _route(self, route):
        # Even refused requests consume both budgets, including guard failures.
        self.requests += 1
        self.navigation_requests += 1
        try:
            self._check()
            request = route.request
            if (self.requests > MAX_TOTAL_REQUESTS
                    or self.navigation_requests > MAX_REQUESTS_PER_NAVIGATION
                    or request.method != 'GET'):
                raise ValueError('brave_request_refused')
            self._public(request.url)
            if request.resource_type not in {'document', 'stylesheet', 'script', 'image', 'font', 'xhr', 'fetch'}:
                raise ValueError('brave_resource_refused')
            if request.resource_type == 'document':
                if not self._navigation or request.frame != self.page.main_frame:
                    raise ValueError('brave_navigation_refused')
            route.continue_()
        except Exception:
            self.blocked += 1
            route.abort()

    def _begin_navigation(self):
        """Called only after a local navigation's destination/input checks."""
        self._check()
        if self.navigations >= MAX_NAVIGATIONS:
            raise RuntimeError('brave_navigation_budget_exhausted')
        if self.requests >= MAX_TOTAL_REQUESTS:
            raise RuntimeError('brave_request_budget_exhausted')
        self.navigations += 1
        self.navigation_requests = 0
        self._issued = None
        self._navigation = True

    def start(self):
        if self.closed or self.context:
            raise RuntimeError('Brave cannot be restarted')
        self._check(); self.launch_gate()
        if self.validation_profile:
            # Lazy import avoids the setup helper's discovery import cycle.
            from brave_validation_profile import RELATIVE_PROFILE, prepare_profile
            require_profile_available(ROOT / RELATIVE_PROFILE)
            self.persistent_profile_path = prepare_profile(ROOT)
        executable = discover_brave()
        x, y, width, height = secondary_bounds()
        from playwright.sync_api import sync_playwright
        before = {(p.pid, p.create_time()) for p in psutil.Process().children(recursive=True)}
        self.deadline = time.monotonic() + self.budget_seconds
        self._watchdog = threading.Timer(self.budget_seconds, self._expire)
        self._watchdog.daemon = True; self._watchdog.start()
        try:
            if self.validation_profile:
                profile_path = str(self.persistent_profile_path)
            else:
                folder = ROOT / 'data/cache/brave'
                folder.mkdir(parents=True, exist_ok=True)
                self._profile = tempfile.TemporaryDirectory(prefix='validation_brave_', dir=folder)
                profile_path = self._profile.name
            self._playwright = sync_playwright().start()
            drivers = []
            for process in psutil.Process().children(recursive=True):
                identity = (process.pid, process.create_time())
                command = ' '.join(process.cmdline()).replace('\\', '/').lower()
                if identity not in before and process.name().lower() in ('node.exe', 'node') and '/playwright/driver/' in command:
                    drivers.append(identity)
            if len(drivers) != 1:
                raise RuntimeError('Cannot identify owned Brave driver')
            with self._lock:
                self._owner = drivers
            self._check(); self.launch_gate()
            if self.validation_profile:
                require_profile_available(self.persistent_profile_path)
            self.context = self._playwright.chromium.launch_persistent_context(
                profile_path, executable_path=str(executable), headless=False,
                no_viewport=True, service_workers='block', accept_downloads=False,
                permissions=[], chromium_sandbox=True,
                **({'ignore_default_args': ['--disable-extensions']} if self.validation_profile else {}),
                args=self._browser_args() + ['--no-first-run', '--no-default-browser-check',
                    '--disable-sync', '--disable-component-update',
                    '--force-webrtc-ip-handling-policy=disable_non_proxied_udp',
                    f'--window-position={x},{y}', f'--window-size={width},{height}'])
            self.browser = self.context.browser
            self._record_descendants(); self._check()
            self.context.clear_permissions()
            self.context.route('**/*', self._route)
            self.context.route_web_socket('**/*', lambda ws: ws.close())
            if self.validation_profile and any(page.url != 'about:blank' for page in self.context.pages):
                raise RuntimeError('brave_validation_restored_page_refused')
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.context.on('page', lambda page: page.close() if page != self.page else None)
            self.page.on('dialog', lambda dialog: dialog.dismiss())
            self.page.on('download', lambda download: download.cancel())
            self.page.set_default_timeout(5000)
            self._check()
            return self
        except BaseException:
            self.close()
            raise

    def start_url(self, url):
        self._public(url)
        if self.page is None:
            self.start()
        return self._goto(url)

    def _goto(self, url):
        url = self._public(url)
        self._begin_navigation()
        self._search_active = False
        if self._search_identity is not None:
            try:
                self._search_active = search_identity(url) == self._search_identity
            except ValueError:
                pass
        try:
            response = self.page.goto(url, wait_until='domcontentloaded', timeout=20000)
            self.target = self._public(self.page.url)
            if self._search_active:
                self._refresh_search_target()
            if response is not None and response.status >= 400:
                raise RuntimeError('brave_http_' + str(response.status))
            self._check()
            return self
        finally:
            self._navigation = False

    def search(self, query):
        if type(query) is not str or not query.strip() or len(query) > 1000 or any(ord(c) < 32 for c in query):
            raise ValueError('invalid_brave_query')
        self._search_identity = None
        self._search_active = False
        self.start_url('https://search.brave.com/')
        # Input is scoped to our own page; no OS keystrokes or focus activation.
        field = self.page.locator('input[name="q"]:visible, textarea[name="q"]:visible')
        if field.count() != 1:
            raise RuntimeError('brave_search_field_missing_or_ambiguous')
        field.fill(query)
        if field.input_value() != query:
            raise RuntimeError('brave_query_not_verified')
        self._public(self.page.url)
        self._begin_navigation()
        try:
            field.press('Enter')
            self.page.wait_for_url('https://search.brave.com/search?*', timeout=20000)
            self.page.wait_for_load_state('domcontentloaded', timeout=20000)
            self.target = self._public(self.page.url)
            # Bind to the URL actually submitted by the browser. Do not trim
            # or silently repair the observed query text here.
            self._search_identity = search_identity(self.page.url)
            self._search_active = True
            self._check()
            return self
        finally:
            self._navigation = False

    def _refresh_search_target(self):
        self._check()
        actual = self.page.url
        if (not self._search_active or self._search_identity is None
                or search_identity(self.target) != self._search_identity
                or search_identity(actual) != self._search_identity):
            raise ValueError('brave_search_scope_changed')
        if actual != self.target:
            self._issued = None
            self.target = self._public(actual)

    def observe(self):
        self._issued = None
        for attempt in range(3):
            self._check()
            if self._search_active:
                self._refresh_search_target()
            if not self.target or self.page.url != self.target:
                raise ValueError('brave_scope_changed')
            expected = self.target
            try:
                value = {'page': observe_page(self.page, self._check, expected_url=expected),
                         'links': observe_links(self.page, self._check, expected_url=expected)}
                if self.page.url != expected:
                    raise ValueError('brave_scope_changed')
            except Exception:
                self._check()
                # Retry only a measured search-URL race, never an arbitrary
                # observation failure or a changed source page.
                if not self._search_active or self.page.url == expected or attempt == 2:
                    raise
                self._refresh_search_target()
                continue
            self._issued = (fingerprint(value), copy.deepcopy(value))
            return value

    def current(self, snapshot):
        self._check()
        if not self._issued or fingerprint(snapshot) != self._issued[0]:
            return False
        return (check_snapshot(self.page, self._check, snapshot['page'], max_age=10, expected_url=self.target)
                and links_current(self.page, self._check, snapshot['links'], expected_url=self.target))

    def open_observed(self, snapshot, index):
        if not self.current(snapshot):
            raise ValueError('brave_observation_changed')
        links = snapshot['links']['links']
        if type(index) is not int or not 0 <= index < len(links):
            raise ValueError('brave_link_index_invalid')
        link = links[index]
        if link.get('download') or link['href'].strip().startswith('#'):
            raise ValueError('brave_link_refused')
        return self._goto(urljoin(self.target, link['href']))

    def screenshot(self):
        """Capture the owned page only, never another application or the desktop."""
        self._check()
        if not self.target or self.page.url != self.target:
            raise ValueError('brave_scope_changed')
        return self.page.screenshot(type='png')

    def close(self):
        if self._watchdog is not None:
            self._watchdog.cancel()
        try:
            try:
                if self.validation_profile and self.context is not None and not self._closed_once:
                    # Close only this driver's tabs, so persistent sessions do
                    # not intentionally retain the pages used by the test.
                    for page in list(self.context.pages):
                        try:
                            page.close(run_before_unload=False)
                        except Exception:
                            self.validation_pages_close_failed = True
            except Exception:
                self.validation_pages_close_failed = True
            finally:
                super().close()
        finally:
            if self._profile is not None and self.owned_stopped:
                self._profile.cleanup()
                self._profile = None
