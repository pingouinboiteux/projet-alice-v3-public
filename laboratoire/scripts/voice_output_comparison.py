"""Manual comparison inside the actual Alice application, using one captured PCM."""
import hashlib
import json
from pathlib import Path
import tempfile
import wave

from continuous_playback import ContinuousPCM

FOLDER = Path(__file__).resolve().parents[1]/'logs/observation'
PROFILES = {'/sortie-a':'mme_mono','/sortie-b':'mme_stereo','/sortie-c':'wasapi_stereo',
            '/sortie-d':'mme_mono','/sortie-e':'mme_mono','/sortie-f':'mme_mono'}


def play(session, command, folder=FOLDER, factory=None):
    path=folder/'voice_capture.wav'
    expected=json.loads((folder/'voice_capture.json').read_text(encoding='utf-8'))
    with wave.open(str(path),'rb') as wav:
        raw=wav.readframes(wav.getnframes())
    digest=hashlib.sha256(raw).hexdigest()
    if digest != expected['pcm_sha256']: raise RuntimeError('Le fichier capture a change')
    profile=PROFILES[command]
    player=ContinuousPCM(session.check,factory,output_profile=profile)
    complete=False
    failure=None
    load=None
    try:
        if command in {'/sortie-e','/sortie-f'}:
            from voice_load_probe import SilentSynthesis
            load=SilentSynthesis(session); load.start()
        if command in {'/sortie-d','/sortie-f'}:
            from sopro_protocol import render_pcm
            # Same packetizer as the worker, then the same persistent player.
            # All PCM bytes stay identical, only delivery boundaries change.
            with tempfile.TemporaryDirectory(prefix='validation_packet_replay_',dir=folder) as name:
                temporary=Path(name)
                def send(event):
                    if event['status']=='audio_part': player.write(temporary/event['file'])
                render_pcm([raw],1,temporary,temporary,send,stream=True)
        else:
            player.write(path)
        complete=True
    except Exception as error:
        failure=type(error).__name__
        raise
    finally:
        try: player.close(complete)
        finally:
            try:
                if load: load.close()
            finally:
                report_path=folder/'voice_output_test.json'
                rows=json.loads(report_path.read_text(encoding='utf-8')) if report_path.exists() else {}
                rows[command]={'profile':profile, 'pcm_sha256':digest, 'complete':complete,
                               'underflows':player.underflows, 'output':player.output_info,
                               'error_type':failure, 'silent_generation':load.report if load else None}
                report_path.write_text(json.dumps(rows,indent=2),encoding='utf-8')


def open_window(app):
    import tkinter as tk
    window=tk.Toplevel(app.window); window.title('Comparer la sortie casque')
    window.geometry('650x350')
    tk.Label(window,text='Le meme enregistrement, dans la vraie Alice',font=('Segoe UI',13)).pack(pady=12)
    tk.Label(window,text='Clique une sortie, attends la fin, puis compare avec la suivante.\n'
             'Le fichier reste identique. Aucun nouveau texte n est genere.').pack(pady=5)
    def enqueue(command):
        app.inputs.put(command)
        if app.hearing: app.hearing.cancel()
    for label,command in [('A : fichier deja pret (temoin propre)','/sortie-a'),
                           ('D : memes petits paquets, sans generation','/sortie-d'),
                           ('E : fichier + generation muette en parallele','/sortie-e'),
                           ('F : petits paquets + generation muette','/sortie-f')]:
        tk.Button(window,text=label,width=46,command=lambda c=command:enqueue(c)).pack(pady=6)
