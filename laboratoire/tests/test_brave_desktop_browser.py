"""No real browser, profile, account or network is opened by these tests."""
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch
from contextlib import ExitStack

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import brave_desktop_browser as module


def backend():
    return module.BraveDesktopBrowser(lambda: None)


@pytest.mark.parametrize('url', ['http://example.org/', 'file:///tmp/a', 'https://127.0.0.1/', 'https://user:pass@example.org/'])
def test_invalid_destination_has_no_navigation(url):
    b = backend(); b.page = Mock()
    b.navigation_requests = 17; b.requests = 23; b.navigations = 2
    with pytest.raises(ValueError):
        b._goto(url)
    b.page.goto.assert_not_called()
    assert (b.navigation_requests, b.requests, b.navigations) == (17, 23, 2)


def request_route(method='GET', kind='script'):
    return Mock(request=SimpleNamespace(method=method, resource_type=kind,
                                       url='https://example.org/a'))


def test_per_navigation_budget_allows_400_then_refuses_401():
    b = backend(); b._public = lambda value: value
    b.navigation_requests = 399; b.requests = 399
    last_allowed, refused = request_route(), request_route()
    b._route(last_allowed); b._route(refused)
    last_allowed.continue_.assert_called_once(); refused.abort.assert_called_once()
    assert b.requests == b.navigation_requests == 401


def test_global_budget_allows_1600_then_refuses_1601():
    b = backend(); b._public = lambda value: value
    b.requests = 1599; b.navigation_requests = 12
    last_allowed, refused = request_route(), request_route()
    b._route(last_allowed); b._route(refused)
    last_allowed.continue_.assert_called_once(); refused.abort.assert_called_once()
    assert b.requests == 1601 and b.navigation_requests == 14
    b.page = Mock()
    with pytest.raises(RuntimeError, match='request_budget_exhausted'):
        b._goto('https://example.org/')
    assert b.requests == 1601 and b.navigation_requests == 14
    b.page.goto.assert_not_called()


def test_navigation_resets_page_budget_only_and_tenth_is_last():
    b = backend(); b._public = lambda value: value
    b.page = Mock(url='https://example.org/'); b.page.goto.return_value = None
    b.requests = 123; b.navigation_requests = 400
    for _ in range(10):
        b._goto('https://example.org/')
        assert b.navigation_requests == 0 and b.requests == 123
        b.navigation_requests = 400
    with pytest.raises(RuntimeError, match='navigation_budget_exhausted'):
        b._goto('https://example.org/')
    assert b.navigations == 10 and b.page.goto.call_count == 10
    assert b.navigation_requests == 400 and b.requests == 123


@pytest.mark.parametrize('reason', ['method', 'resource', 'guard', 'dns'])
def test_refused_requests_consume_both_budgets(reason):
    b = backend(); b._public = Mock(return_value='https://example.org/a')
    if reason == 'guard':
        b.guard = Mock(side_effect=RuntimeError('guard'))
    if reason == 'dns':
        b._public.side_effect = ValueError('private')
    route = request_route(method='POST' if reason == 'method' else 'GET',
                          kind='media' if reason == 'resource' else 'script')
    b._route(route)
    assert b.requests == b.navigation_requests == b.blocked == 1
    route.abort.assert_called_once(); route.continue_.assert_not_called()


def test_search_submission_consumes_second_navigation_budget():
    b = backend(); b._public = lambda value: value
    b.page = Mock(url='https://search.brave.com/')
    b.page.goto.return_value = None
    field = b.page.locator.return_value
    field.count.return_value = 1; field.input_value.return_value = 'test'
    def fill(_query):
        b.navigation_requests = 392
        b.requests = 392
    field.fill.side_effect = fill
    field.press.side_effect = lambda _key: setattr(b.page, 'url', 'https://search.brave.com/search?q=test')
    b.search('test')
    assert b.navigations == 2 and b.navigation_requests == 0 and b.requests == 392


def test_observation_does_not_reset_budgets():
    b = backend(); b.target = 'https://example.org/'
    b.page = Mock(url=b.target)
    b.requests = 999; b.navigation_requests = 399; b.navigations = 3
    with patch.object(module, 'observe_page', return_value={}), \
         patch.object(module, 'observe_links', return_value={}):
        b.observe()
    assert (b.requests, b.navigation_requests, b.navigations) == (999, 399, 3)


SEARCH_URL = 'https://search.brave.com/search?q=test%0D%0A&source=web'


def searching_backend():
    b = backend(); b.target = SEARCH_URL
    b.page = Mock(url=SEARCH_URL)
    b._public = lambda value: value
    b._search_identity = module.search_identity(SEARCH_URL)
    b._search_active = True
    return b


def test_search_refresh_accepts_only_conversation_and_invalidates_old_observation():
    b = searching_backend()
    with patch.object(module, 'observe_page', side_effect=lambda *a, **kw: {'url': kw['expected_url']}), \
         patch.object(module, 'observe_links', side_effect=lambda *a, **kw: {'url': kw['expected_url']}):
        old = b.observe()
        b.page.url = SEARCH_URL + '&conversation=09c6e-123'
        fresh = b.observe()
    assert fresh['page']['url'] == b.target == b.page.url
    assert not b.current(old)
    assert ('q', 'test\r\n') in b._search_identity


@pytest.mark.parametrize('changed', [
    SEARCH_URL.replace('test%0D%0A', 'test'),
    SEARCH_URL + '&q=test%0D%0A', SEARCH_URL + '&country=fr',
    SEARCH_URL.replace('source=web', 'source=other'),
    SEARCH_URL.replace('search.brave.com', 'example.org'),
    SEARCH_URL.replace('/search?', '/other?'),
    SEARCH_URL + '&conversation=a&conversation=b',
    SEARCH_URL + '&conversation=', SEARCH_URL + '&conversation=' + 'a'*129,
    SEARCH_URL + '#fragment',
])
def test_search_refresh_rejects_changed_scope(changed):
    b = searching_backend(); b.page.url = changed
    with patch.object(module, 'observe_page') as observe:
        with pytest.raises(ValueError):
            b.observe()
    observe.assert_not_called()
    assert b.target == SEARCH_URL and b._issued is None


def test_search_refresh_retries_url_race_once_with_new_complete_snapshot():
    b = searching_backend()
    def page_observation(*args, **kwargs):
        if b.page.url == SEARCH_URL:
            b.page.url += '&conversation=abc'
            raise ValueError('rendered_scope_changed')
        return {'url': kwargs['expected_url']}
    with patch.object(module, 'observe_page', side_effect=page_observation) as observe, \
         patch.object(module, 'observe_links', return_value={}):
        snapshot = b.observe()
    assert observe.call_count == 2
    assert snapshot['page']['url'] == b.page.url


def test_search_refresh_is_bounded_and_does_not_issue_failed_snapshot():
    b = searching_backend(); calls = []
    def changing(*args, **kwargs):
        calls.append(1)
        b.page.url = SEARCH_URL + '&conversation=' + str(len(calls))
        raise ValueError('rendered_scope_changed')
    with patch.object(module, 'observe_page', side_effect=changing):
        with pytest.raises(ValueError, match='rendered_scope_changed'):
            b.observe()
    assert len(calls) == 3 and b._issued is None


def test_refresh_window_closes_on_source_and_reopens_only_on_explicit_search_return():
    b = searching_backend()
    def navigate(url, **kwargs):
        b.page.url = url
        return None
    b.page.goto.side_effect = navigate
    b._goto('https://example.org/')
    assert not b._search_active
    b.page.url = SEARCH_URL + '&conversation=abc'
    with pytest.raises(ValueError, match='brave_scope_changed'):
        b.observe()
    b._goto(SEARCH_URL)
    assert b._search_active
    b.page.url = SEARCH_URL + '&conversation=def'
    with patch.object(module, 'observe_page', return_value={}), \
         patch.object(module, 'observe_links', return_value={}):
        b.observe()
    assert b.target == b.page.url


@pytest.mark.parametrize('method,kind,navigation,allowed', [
    ('POST', 'fetch', True, False), ('GET', 'media', True, False),
    ('GET', 'document', False, False), ('GET', 'document', True, True),
    ('GET', 'script', False, True), ('GET', 'fetch', False, True)])
def test_native_route_policy(method, kind, navigation, allowed):
    b = backend(); b.page = SimpleNamespace(main_frame=object()); b._navigation = navigation
    b._public = Mock(return_value='https://example.org/')
    route = Mock(request=SimpleNamespace(method=method, resource_type=kind,
        url='https://example.org/', frame=b.page.main_frame))
    b._route(route)
    assert route.continue_.call_count == int(allowed)
    assert route.abort.call_count == int(not allowed)
    route.fulfill.assert_not_called()


def test_dns_private_refusal_aborts_browser_request():
    b = backend(); b.page = SimpleNamespace(main_frame=object())
    route = Mock(request=SimpleNamespace(method='GET', resource_type='script', url='https://example.org/a'))
    with patch.object(module, 'public_addresses', side_effect=ValueError('private')):
        b._route(route)
    route.abort.assert_called_once(); route.continue_.assert_not_called()


def test_search_really_fills_verifies_and_submits():
    b = backend(); b.start_url = Mock(); b.page = Mock(url='https://search.brave.com/search?q=test')
    b._public = lambda value: value
    field = b.page.locator.return_value
    field.count.return_value = 1; field.input_value.return_value = 'test'
    assert b.search('test') is b
    b.page.locator.assert_called_once_with('input[name="q"]:visible, textarea[name="q"]:visible')
    b.start_url.assert_called_once_with('https://search.brave.com/')
    field.fill.assert_called_once_with('test'); field.press.assert_called_once_with('Enter')
    assert not b._navigation


@pytest.mark.parametrize('count', [0, 2])
def test_search_refuses_missing_or_ambiguous_field(count):
    b = backend(); b.start_url = Mock(); b.page = Mock()
    field = b.page.locator.return_value
    field.count.return_value = count
    with pytest.raises(RuntimeError, match='missing_or_ambiguous'):
        b.search('test')
    field.fill.assert_not_called()
    field.press.assert_not_called()


def test_search_rejects_unverified_input():
    b = backend(); b.start_url = Mock(); b.page = Mock()
    field = b.page.locator.return_value; field.count.return_value = 1
    field.input_value.return_value = 'different'
    with pytest.raises(RuntimeError, match='not_verified'):
        b.search('test')
    field.press.assert_not_called()


def test_observed_cross_origin_link_is_frozen():
    b = backend(); b.target = 'https://search.brave.com/search?q=test'
    b.current = Mock(return_value=True); b._goto = Mock(return_value=b)
    snapshot = {'links': {'links': [{'href': 'https://example.org/article', 'label': 'article'}]}}
    assert b.open_observed(snapshot, 0) is b
    b.current.assert_called_once_with(snapshot)
    b._goto.assert_called_once_with('https://example.org/article')


@pytest.mark.parametrize('index,download,current', [(True, False, True), (1, False, True), (0, True, True), (0, False, False)])
def test_link_rejections_never_navigate(index, download, current):
    b = backend(); b.target = 'https://example.org/'
    b.current = Mock(return_value=current); b._goto = Mock()
    snapshot = {'links': {'links': [{'href': '/article', 'label': 'article', 'download': download}]}}
    with pytest.raises(ValueError):
        b.open_observed(snapshot, index)
    b._goto.assert_not_called()


def test_launch_gate_runs_before_discovery_or_playwright():
    b = module.BraveDesktopBrowser(lambda: None, launch_gate=Mock(side_effect=RuntimeError('game')))
    with patch.object(module, 'discover_brave') as discovery:
        with pytest.raises(RuntimeError, match='game'):
            b.start()
        discovery.assert_not_called()


def test_brave_discovery_uses_environment(tmp_path, monkeypatch):
    executable = tmp_path / 'BraveSoftware/Brave-Browser/Application/brave.exe'
    executable.parent.mkdir(parents=True); executable.touch()
    monkeypatch.setenv('PROGRAMFILES', str(tmp_path))
    assert module.discover_brave() == executable.resolve()


def test_timeout_uses_owned_stop_only():
    b = backend(); b.stop_owned = Mock()
    b._expire()
    assert b.timed_out
    b.stop_owned.assert_called_once()


def test_profile_is_retained_if_processes_not_confirmed_stopped():
    b = backend(); b._profile = Mock(); b._owner = [(123, 42)]
    with patch.object(module.BrowserDemo, 'close'), patch.object(module.psutil, 'Process') as process:
        process.return_value.create_time.return_value = 42
        b.close()
    b._profile.cleanup.assert_not_called()


@pytest.mark.parametrize('value', [None, 0, 1, 'true', Path('personal')])
def test_validation_profile_requires_explicit_boolean(value):
    with pytest.raises(ValueError, match='invalid_validation_profile'):
        module.BraveDesktopBrowser(lambda: None, validation_profile=value)


@pytest.mark.parametrize('split', [False, True])
def test_occupied_profile_refused_without_stopping_process(tmp_path, split):
    process = Mock()
    process.name.return_value = 'brave.exe'
    process.cmdline.return_value = (['brave.exe', '--user-data-dir', str(tmp_path)] if split
                                   else ['brave.exe', '--user-data-dir=' + str(tmp_path)])
    with patch.object(module.psutil, 'process_iter', return_value=[process]):
        with pytest.raises(RuntimeError, match='profile_in_use'):
            module.require_profile_available(tmp_path)
    process.terminate.assert_not_called(); process.kill.assert_not_called()


def test_profile_probe_ignores_other_profiles_and_unrelated_commands(tmp_path):
    other = Mock(); other.name.return_value = 'brave.exe'
    other.cmdline.return_value = ['brave.exe', '--user-data-dir=' + str(tmp_path / 'other')]
    unrelated = Mock(); unrelated.name.return_value = 'notepad.exe'
    with patch.object(module.psutil, 'process_iter', return_value=[other, unrelated]):
        module.require_profile_available(tmp_path)
    unrelated.cmdline.assert_not_called()


@pytest.mark.parametrize('error', [module.psutil.AccessDenied(123), None])
def test_profile_probe_refuses_unreadable_brave_command(tmp_path, error):
    process = Mock(); process.name.return_value = 'brave.exe'
    process.cmdline.side_effect = error; process.cmdline.return_value = []
    with patch.object(module.psutil, 'process_iter', return_value=[process]):
        with pytest.raises(RuntimeError, match='occupancy_unknown'):
            module.require_profile_available(tmp_path)


def test_occupied_validation_profile_refused_before_preparation():
    b = module.BraveDesktopBrowser(lambda: None, validation_profile=True, launch_gate=lambda: None)
    with patch.object(module, 'require_profile_available', side_effect=RuntimeError('profile_in_use')), \
         patch('brave_validation_profile.prepare_profile') as prepare, \
         patch.object(module, 'discover_brave') as discover:
        with pytest.raises(RuntimeError, match='profile_in_use'):
            b.start()
    prepare.assert_not_called(); discover.assert_not_called()


@pytest.fixture
def simulated_launch(tmp_path):
    """Fake the driver, browser and timers; only fictitious temp files are used."""
    driver = Mock(pid=321)
    driver.create_time.return_value = 42
    driver.name.return_value = 'node.exe'
    driver.cmdline.return_value = ['/fake/playwright/driver/node.exe']
    playwright = Mock()
    context = playwright.chromium.launch_persistent_context.return_value
    context.pages = [Mock(url='about:blank')]
    with ExitStack() as stack:
        stack.enter_context(patch.object(module, 'ROOT', tmp_path))
        stack.enter_context(patch.object(module, 'discover_brave', return_value=Path('brave.exe')))
        stack.enter_context(patch.object(module, 'secondary_bounds', return_value=(0, 0, 800, 600)))
        timer = stack.enter_context(patch.object(module.threading, 'Timer'))
        processes = stack.enter_context(patch.object(module.psutil, 'Process'))
        processes.return_value.children.side_effect = [[], [driver]]
        stack.enter_context(patch.object(module, 'require_profile_available'))
        sync = stack.enter_context(patch('playwright.sync_api.sync_playwright'))
        sync.return_value.start.return_value = playwright
        stack.enter_context(patch.object(module.BraveDesktopBrowser, '_record_descendants'))
        stack.enter_context(patch.object(module.BrowserDemo, 'close'))
        yield SimpleNamespace(root=tmp_path, playwright=playwright, context=context, timer=timer)


@pytest.mark.parametrize('persistent', [False, True])
def test_profile_mode_launch_guards_and_lifetime(simulated_launch, persistent):
    env = simulated_launch
    guard, gate = Mock(), Mock()
    b = module.BraveDesktopBrowser(guard, launch_gate=gate, validation_profile=persistent)
    b.start()
    args, kwargs = env.playwright.chromium.launch_persistent_context.call_args
    profile = Path(args[0])
    assert profile.is_dir()
    if persistent:
        from brave_validation_profile import RELATIVE_PROFILE
        assert profile == env.root / RELATIVE_PROFILE
        assert b.persistent_profile_path == profile
        assert b._profile is None
        assert kwargs['ignore_default_args'] == ['--disable-extensions']
        assert '--disable-extensions' not in kwargs['args']
    else:
        assert profile.parent == env.root / 'data/cache/brave'
        assert b.persistent_profile_path is None
        assert 'ignore_default_args' not in kwargs
        assert '--disable-extensions' in kwargs['args']
    assert kwargs['service_workers'] == 'block'
    assert kwargs['accept_downloads'] is False
    assert kwargs['chromium_sandbox'] is True
    assert kwargs['permissions'] == []
    for flag in ['--disable-gpu', '--disable-background-networking', '--mute-audio',
                 '--disable-sync', '--disable-component-update']:
        assert flag in kwargs['args']
    env.context.route.assert_called_once_with('**/*', b._route)
    env.context.route_web_socket.assert_called_once()
    env.timer.return_value.start.assert_called_once()
    assert guard.call_count >= 3 and gate.call_count == 2
    b._owner = []
    b.close()
    assert profile.exists() is persistent
    env.timer.return_value.cancel.assert_called_once()


def test_failed_validation_launch_preserves_profile(simulated_launch):
    env = simulated_launch
    env.playwright.chromium.launch_persistent_context.side_effect = RuntimeError('launch failed')
    b = module.BraveDesktopBrowser(lambda: None, launch_gate=lambda: None, validation_profile=True)
    with pytest.raises(RuntimeError, match='launch failed'):
        b.start()
    assert b._profile is None
    assert (b.persistent_profile_path / 'alice-validation-profile.json').is_file()
    env.timer.return_value.cancel.assert_called_once()


@pytest.mark.parametrize('fail_close', [False, True])
def test_validation_closes_owned_tabs_before_driver_even_on_error(simulated_launch, fail_close):
    env = simulated_launch
    b = module.BraveDesktopBrowser(lambda: None, launch_gate=lambda: None, validation_profile=True)
    b.start()
    first, second = env.context.pages[0], Mock()
    env.context.pages.append(second)
    order = []
    def close_first(**kwargs):
        order.append('first')
        if fail_close:
            raise RuntimeError('page close failed')
    first.close.side_effect = close_first
    second.close.side_effect = lambda **kwargs: order.append('second')
    with patch.object(module.BrowserDemo, 'close', side_effect=lambda: order.append('driver')):
        b.close()
    assert order == ['first', 'second', 'driver']
    first.close.assert_called_once_with(run_before_unload=False)
    second.close.assert_called_once_with(run_before_unload=False)
    assert b.validation_pages_close_failed is fail_close
    assert (b.persistent_profile_path / 'alice-validation-profile.json').is_file()


def test_validation_restored_page_refused_and_closed(simulated_launch):
    env = simulated_launch
    restored = Mock(url='https://search.brave.com/search?q=old')
    env.context.pages.append(restored)
    b = module.BraveDesktopBrowser(lambda: None, launch_gate=lambda: None, validation_profile=True)
    with pytest.raises(RuntimeError, match='restored_page_refused'):
        b.start()
    assert b.page is None
    restored.evaluate.assert_not_called()
    restored.content.assert_not_called()
    restored.close.assert_called_once_with(run_before_unload=False)
    env.context.pages[0].close.assert_called_once_with(run_before_unload=False)
    assert b.persistent_profile_path.is_dir()


def test_temporary_close_does_not_explicitly_close_tabs(simulated_launch):
    env = simulated_launch
    b = module.BraveDesktopBrowser(lambda: None, launch_gate=lambda: None)
    b.start()
    b._owner = []
    b.close()
    env.context.pages[0].close.assert_not_called()


def test_validation_page_enumeration_failure_still_closes_driver(simulated_launch):
    env = simulated_launch
    b = module.BraveDesktopBrowser(lambda: None, launch_gate=lambda: None, validation_profile=True)
    b.start()
    with patch.object(type(env.context), 'pages', new_callable=PropertyMock, create=True,
                      side_effect=RuntimeError('context already closed')), \
         patch.object(module.BrowserDemo, 'close') as close_driver:
        b.close()
    close_driver.assert_called_once()
    assert b.validation_pages_close_failed
    assert b.persistent_profile_path.is_dir()
