from pathlib import Path
import os
import subprocess
import pytest
from private_output_path import private_output_path


def test_private_output_accepts_directory_and_rejects_escape(tmp_path):
    root=tmp_path/'validation_root'
    folder=root/'logs'/'validation_audio'
    folder.mkdir(parents=True)
    assert private_output_path(root,'logs/validation_audio')==folder.resolve()
    with pytest.raises(ValueError):private_output_path(root,'logs/missing')
    with pytest.raises(ValueError):private_output_path(root,'logs/../..')
    file=folder/'file.txt';file.write_text('test')
    with pytest.raises(ValueError):private_output_path(root,'logs/validation_audio/file.txt')


@pytest.mark.skipif(os.name!='nt',reason='Windows junction contract')
def test_junction_compatibility_and_external_redirection_rejected(tmp_path):
    root=tmp_path/'validation_root';root.mkdir()
    target=root/'data'/'logs';target.mkdir(parents=True)
    (target/'validation_audio').mkdir()
    link=root/'logs'
    # Paths come only from pytest's generated fixture, not from user input.
    def junction(destination):
        escaped=lambda p:str(p).replace("'","''")
        subprocess.run(['powershell','-NoProfile','-Command',
            f"New-Item -ItemType Junction -Path '{escaped(link)}' -Target '{escaped(destination)}' | Out-Null"],check=True)
    junction(target)
    try:
        assert private_output_path(root,'logs/validation_audio')==target/'validation_audio'
        assert private_output_path(root,'data/logs/validation_audio')==target/'validation_audio'
    finally:os.rmdir(link)
    external=tmp_path/'validation_outside';external.mkdir()
    junction(external)
    try:
        with pytest.raises(ValueError):private_output_path(root,'logs')
    finally:os.rmdir(link)
