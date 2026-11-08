"""Filesystem-only profile tests; no browser or personal data."""
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from brave_validation_profile import prepare_profile,RELATIVE_PROFILE


def test_profile_is_reused_without_erasing_browser_data(tmp_path):
    profile=prepare_profile(tmp_path)
    (profile/'validation_sentinel').write_text('preserve',encoding='utf-8')
    assert prepare_profile(tmp_path)==profile
    assert (profile/'validation_sentinel').read_text(encoding='utf-8')=='preserve'


def test_existing_unmarked_directory_is_not_adopted(tmp_path):
    profile=tmp_path/RELATIVE_PROFILE;profile.mkdir(parents=True)
    (profile/'Preferences').write_text('{}',encoding='utf-8')
    with pytest.raises(ValueError,match='unmarked'):prepare_profile(tmp_path)
    assert not (profile/'alice-validation-profile.json').exists()


def test_wrong_marker_is_rejected_without_rewriting(tmp_path):
    profile=prepare_profile(tmp_path)
    marker=profile/'alice-validation-profile.json'
    marker.write_text(json.dumps({'purpose':'other'}),encoding='utf-8')
    with pytest.raises(ValueError,match='mismatch'):prepare_profile(tmp_path)
    assert json.loads(marker.read_text(encoding='utf-8'))=={'purpose':'other'}
