from types import SimpleNamespace

from fps_guard import NativeGuard


def guard(fps=60):
    return NativeGuard(SimpleNamespace(), 'validation_brief_dips', minimum_fps=fps)


def test_single_hitch_recovers_and_does_not_accumulate_across_dips():
    g = guard()
    low, normal = {'average_fps': 54.5}, {'average_fps': 60}
    assert g.filter_brief_fps_dip('average_below_55fps', 10, low, low) is None
    assert g.filter_brief_fps_dip('average_below_55fps', 12, low, low) is None
    assert g.filter_brief_fps_dip(None, 13, normal, normal) is None
    assert g.filter_brief_fps_dip('average_below_55fps', 20, low, low) is None
    assert g.filter_brief_fps_dip('average_below_55fps', 26, low, low) == 'average_below_55fps'


def test_severe_fps_drop_and_nonfps_failures_are_immediate():
    g = guard()
    low, severe = {'average_fps': 54}, {'average_fps': 44}
    assert g.filter_brief_fps_dip('average_below_55fps', 0, low, severe) == 'average_below_55fps'
    for reason in ('windows_ram_headroom', 'frame_measurement_stale', 'insufficient_frame_measurement'):
        assert g.filter_brief_fps_dip(reason, 0, low, low) == reason


def test_historical_strict_fps_policies_stay_immediate():
    for fps in (90, 120):
        g = guard(fps)
        reason = f'average_below_{fps}fps'
        assert g.filter_brief_fps_dip(reason, 0, {'average_fps': fps-1}, {'average_fps': fps-1}) == reason
