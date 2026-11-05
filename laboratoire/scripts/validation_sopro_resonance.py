"""Bounded Sopro controls with existing RAM/game guards and owned worker cleanup."""
import argparse
import json
import os
import queue
import subprocess
import threading
import time

from chat import ROOT, Session, Job, processes, GAMES


def arguments(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--allow-game-no-fps', action='store_true')
    parser.add_argument('--original-options', action='store_true', required=True)
    return parser.parse_args(argv)


def main():
    args = arguments()
    from validation_tts_run import gpu_snapshot
    folder = ROOT/'rapports/validation_sopro_original_20261105/native_options'
    folder.mkdir(parents=True,exist_ok=True)
    target = folder/'result.json'
    if target.exists(): raise RuntimeError('Preserve previous measurement')
    if GAMES & processes() and not args.allow_game_no_fps:
        raise RuntimeError('Validation waits until game is closed')
    if 'llama-server.exe' in processes(): raise RuntimeError('Close Alice before isolated voice validation')
    session = Session(allow_game=args.allow_game_no_fps, fps_protection=not args.allow_game_no_fps)
    if session.minimum_ram < 6*2**30: raise RuntimeError('Six GiB free RAM required')
    report = {'status':'running', 'rows':[], 'microphone_opened':False,
              'audio_played':False, 'private_memory_opened':False, 'default_changed':False,
              'fps_exception_user_authorized':args.allow_game_no_fps, 'ram_guard_gib':6}
    messages = queue.Queue()
    def save(): target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    session.job = Job()
    try:
        with (folder/'worker.log').open('w', encoding='utf-8') as log:
            env = dict(os.environ, PYTHONPATH='src', PYTHONIOENCODING='utf-8',
                       PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='4', MKL_NUM_THREADS='4')
            worker_script='scripts/validation_sopro_original_options_worker.py'
            command = [str(ROOT/'.venv_sopro/Scripts/python.exe'), '-B',worker_script]
            worker = subprocess.Popen(command, cwd=ROOT, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=log, text=True,
                encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
            session.children['voice_validation'] = worker
            session.job.assign(worker)
            session.thread = threading.Thread(target=session.watch, daemon=True); session.thread.start()
            def read():
                for line in worker.stdout: messages.put(line)
                messages.put(None)
            threading.Thread(target=read, daemon=True).start()
            deadline = time.monotonic()+300
            while True:
                session.check()
                if time.monotonic() > deadline: raise TimeoutError('Sopro diagnostic stage timeout')
                try: line = messages.get(timeout=.2)
                except queue.Empty: continue
                if line is None: break
                row = json.loads(line)
                if row['event'] == 'ready':
                    report['ready'] = row
                    report['gpu_windows'] = gpu_snapshot([worker.pid])
                elif row['event'] == 'row':
                    report['rows'].append(row)
                    print(json.dumps({k:row[k] for k in ('mode','index','first_pcm_seconds','total_seconds','prompt_unchanged','repeat_identical') if k in row}), flush=True)
                elif row['event'] == 'complete':
                    report['status'] = 'complete'; continue
                save(); deadline = time.monotonic()+180
                worker.stdin.write('next\n'); worker.stdin.flush()
            if worker.wait(timeout=15) != 0 or report['status'] != 'complete':
                raise RuntimeError('Diagnostic incomplete; inspect worker.log')
    except Exception as error:
        report.update(status='failed', error=str(error)); raise
    finally:
        session.close()
        report['minimum_ram_free_gib'] = session.minimum_ram/2**30
        report['owned_workers_stopped'] = all(p.poll() is not None for p in session.children.values())
        save()


if __name__ == '__main__': main()
