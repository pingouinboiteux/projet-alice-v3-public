import pytest
from action_policy import validate_url

def test_web_file_filter_does_not_confuse_hostname_with_executable():
    for url in ['https://youtube.com','https://example.com','https://example.com/page?topic=installer.exe']:
        assert validate_url(url)==url
    for url in ['https://example.com/program.com','https://example.com/setup.exe?x=1',
                'https://example.com/setup%2Eexe','https://example.com/archive.zip/',
                'https://127.0.0.1','http://example.com','https://name:secret@example.com']:
        with pytest.raises(ValueError):validate_url(url)
