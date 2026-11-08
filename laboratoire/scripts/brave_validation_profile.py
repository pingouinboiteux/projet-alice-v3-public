"""Prepare a fixed, persistent test-only Brave profile. Never import user data."""
import argparse
import json
from pathlib import Path
import subprocess

from chat import ROOT, free_ram
from brave_desktop_browser import discover_brave, secondary_bounds

RELATIVE_PROFILE=Path('data/browser/validation_alice_brave')
MARKER={'purpose':'Alice browser validation only','version':1}


def prepare_profile(root=ROOT):
    root=Path(root).resolve()
    target=root/RELATIVE_PROFILE
    # Reject redirected ancestors, including Windows junctions.
    if target.resolve()!=target:
        raise ValueError('Validation profile path is redirected')
    target.mkdir(parents=True,exist_ok=True)
    marker=target/'alice-validation-profile.json'
    if marker.exists():
        if marker.is_symlink() or json.loads(marker.read_text(encoding='utf-8'))!=MARKER:
            raise ValueError('Validation profile marker mismatch')
    else:
        if any(target.iterdir()):
            raise ValueError('Refusing to adopt an existing unmarked profile')
        with marker.open('x',encoding='utf-8') as stream:
            json.dump(MARKER,stream)
    return target


def run():
    parser=argparse.ArgumentParser()
    parser.add_argument('--open-profile',action='store_true',
        help='Open the dedicated setup window; user installs/reviews official extension manually.')
    args=parser.parse_args()
    path=prepare_profile()
    print(path.relative_to(ROOT).as_posix(),flush=True)
    if args.open_profile:
        if free_ram()<6*1024**3: raise RuntimeError('Less than 6 GiB RAM free')
        x,y,width,height=secondary_bounds()
        command=[str(discover_brave()),'--user-data-dir='+str(path),
                 '--no-first-run','--no-default-browser-check','--disable-sync',
                 f'--window-position={x},{y}',f'--window-size={width},{height}',
                 '--new-window','about:blank']
        process=subprocess.Popen(command,cwd=ROOT)
        print('SETUP_WINDOW_REQUESTED',process.pid,flush=True)


if __name__=='__main__':run()
