"""Independent installed French synthesis sources, same installed ASR, no playback."""
import json
import subprocess
import time
from pathlib import Path
from observer_action_bench import ObserverSession
from observer_audio_diagnosis import PHRASES,compare_words
from hearing_link import Hearing
from vision_bench_runtime import save
from chat import ROOT

SCRIPT=r'''
param([string]$InputFile,[string]$OutputFolder)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Speech
$items=Get-Content -LiteralPath $InputFile -Raw -Encoding UTF8 | ConvertFrom-Json
$speaker=New-Object System.Speech.Synthesis.SpeechSynthesizer
$format=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
try {
    foreach($item in $items) {
        $speaker.SelectVoice($item.voice)
        $speaker.SetOutputToWaveFile((Join-Path $OutputFolder $item.file),$format)
        $speaker.Speak($item.text)
        $speaker.SetOutputToNull()
    }
} finally { $speaker.Dispose() }
'''

def run():
    session=ObserverSession();hearing=None
    report={'status':'starting','rows':[],'scope':'independent synthetic voices, not human microphone validation'}
    output=ROOT/'data/validation/validation_workflows_20261105'/('audio_sources_'+time.strftime('%H%M%S')+'.json')
    try:
        session.start();report['games_present']=session.games_present
        folder=Path(session.temp.name)
        items=[{'voice':voice,'text':text,'file':f'validation_native_{v}_{i}.wav'}
               for v,voice in enumerate(['Microsoft Hortense Desktop'])
               for i,text in enumerate(PHRASES)]
        source=folder/'validation_sources.json';source.write_text(json.dumps(items,ensure_ascii=False),encoding='utf-8')
        script=folder/'validation_synthesis.ps1';script.write_text(SCRIPT,encoding='ascii')
        proc=subprocess.Popen(['powershell.exe','-NoProfile','-NonInteractive','-File',str(script),
             '-InputFile',str(source),'-OutputFolder',str(folder)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
             creationflags=subprocess.CREATE_NO_WINDOW)
        session.children['native_tts']=proc;session.job.assign(proc)
        deadline=time.monotonic()+60
        while proc.poll() is None:
            session.check()
            if time.monotonic()>deadline:raise RuntimeError('Native synthesis timeout')
            time.sleep(.1)
        out,error=proc.communicate()
        if proc.returncode:raise RuntimeError(error.decode('utf-8',errors='replace'))
        missing=[item['file'] for item in items if not (folder/item['file']).is_file()]
        if missing:raise RuntimeError(f'Native synthesis missing files: {missing}')
        hearing=Hearing(session);hearing.start()
        for item in items:
            wav=folder/item['file']
            result=hearing.command('transcribe',file=wav.relative_to(ROOT).as_posix(),validate_capture=False)
            report['rows'].append({**item,'result':result,'comparison':compare_words(item['text'],result.get('text',''))})
            wav.unlink(missing_ok=True)
        report['status']='complete'
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:
        try:
            if hearing:hearing.close()
        finally:
            try:session.close()
            except Exception as error:report.update(status='cleanup_failed',cleanup_error=repr(error))
        report['minimum_free_ram']=session.minimum_ram
        report['owned_processes_stopped']=all(p.poll() is not None for p in session.children.values())
        if session.frame_guard:report['fps_guard_report']=str(session.frame_guard.report_path.relative_to(ROOT))
        save(output,report);print('REPORT',output.relative_to(ROOT),report['status'],flush=True)

if __name__=='__main__':run()
