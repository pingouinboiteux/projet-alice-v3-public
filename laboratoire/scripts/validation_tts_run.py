"""Own one voice worker, bound RAM/time, sample RAM/CPU, read GPU counters."""
import argparse
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time
import psutil
from chat import Job

ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'rapports/validation_tts_20261104'

def gpu_snapshot(pids):
    command="$g=@(Get-CimInstance Win32_PerfFormattedData_GPUPerformanceCounters_GPUProcessMemory | Where-Object {[long]$_.DedicatedUsage -gt 0} | Select-Object Name,DedicatedUsage,SharedUsage); ConvertTo-Json -InputObject $g -Compress"
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,text=True,
        timeout=25,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode: return {'error':result.stderr[:500]}
    values=json.loads(result.stdout or '[]')
    if isinstance(values,dict):values=[values]
    return {'counters':[v for v in values if any(v['Name'].startswith('pid_'+str(pid)+'_') for pid in pids)]}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('name',choices=['current','sopro','sopro_gpu','moss','qwen','qwen_native','sopro_quality'])
    parser.add_argument('--tag',default='')
    parser.add_argument('--sopro-steps',type=int,choices=[2,8,16],default=2)
    args=parser.parse_args();name=args.name
    target=FOLDER/(name+args.tag+'.json')
    if target.exists():raise RuntimeError('Preserve existing measurement; use a new tag')
    if psutil.virtual_memory().available<6*1024**3:raise RuntimeError('Need six GiB RAM free')
    env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',
        VALIDATION_TTS_TAG=args.tag,ALICE_LOG_DIRECTORY=str(FOLDER),
        VALIDATION_SOPRO_STEPS=str(args.sopro_steps),
        OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',OPENBLAS_NUM_THREADS='4',
        TEMP=str(ROOT/'cache/validation_tts_temp'),TMP=str(ROOT/'cache/validation_tts_temp'))
    python=ROOT/('.venv_voice' if name=='current' else '.venv_tts_validation')/'Scripts/python.exe'
    report={'name':name,'status':'running','rows':[],'samples':[],'audio_played':False,
        'microphone_opened':False,'private_memory_opened':False,'llm_loaded':False,
        'note':'Voice-only isolated comparison. GPU counters are sampled observations, not guaranteed peaks.'}
    messages=queue.Queue()
    process=None
    job=Job()
    def save():target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        with (FOLDER/(name+args.tag+'.log')).open('w',encoding='utf-8') as log:
            start=time.monotonic();last=start
            worker='scripts/validation_sopro_quality.py' if name=='sopro_quality' else 'scripts/validation_tts_candidate.py'
            process=subprocess.Popen([str(python),'-B',worker,name],
                cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,
                text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
            job.assign(process)
            parent=psutil.Process(process.pid)
            def reader():
                for line in process.stdout:messages.put(line)
                messages.put(None)
            threading.Thread(target=reader,daemon=True).start()
            samples=[]
            while True:
                try:
                    children=[parent]+parent.children(recursive=True)
                    infos=[p.memory_info() for p in children]
                    cpu=[p.cpu_times() for p in children]
                    sample={'elapsed':time.monotonic()-start,'rss':sum(i.rss for i in infos),
                        'private':sum(getattr(i,'private',0) for i in infos),
                        'os_peak_wset_sum':sum(getattr(i,'peak_wset',0) for i in infos),
                        'cpu_seconds':sum(i.user+i.system for i in cpu),
                        'free_ram':psutil.virtual_memory().available}
                    samples.append(sample)
                    if sample['free_ram']<6*1024**3:raise RuntimeError('Six GiB RAM validation guard')
                    if sample['rss']>9*1024**3:raise RuntimeError('Voice test RAM budget exceeded')
                    if time.monotonic()-last>300:raise TimeoutError('Worker stage exceeded five minutes')
                except psutil.NoSuchProcess:
                    if process.poll() is None:raise
                try:line=messages.get(timeout=.05)
                except queue.Empty:continue
                if line is None:break
                try:value=json.loads(line)
                except json.JSONDecodeError:
                    report.setdefault('non_json_output',[]).append(line[:500]);continue
                if value.get('event') in {'ready','row'}:
                    last=time.monotonic()
                    value['resource_samples']=samples
                    value['gpu_windows']=gpu_snapshot([p.pid for p in children])
                    samples=[]
                    if value['event']=='ready':report['ready']=value
                    else:report['rows'].append(value)
                    print(json.dumps({k:v for k,v in value.items() if k not in {'resource_samples','text','gpu_windows'}},ensure_ascii=True),flush=True)
                    save()
                    process.stdin.write('next\n');process.stdin.flush()
                elif value.get('event')=='complete':report['status']='complete'
            code=process.wait(timeout=15)
            report['exit_code']=code
            if code or report['status']!='complete':raise RuntimeError('Candidate failed; see its log')
    except Exception as error:
        report.update(status='failed',error=str(error))
        raise
    finally:
        if process:
            if process.poll() is None:
                for child in psutil.Process(process.pid).children(recursive=True):
                    try:child.terminate()
                    except psutil.NoSuchProcess:pass
                process.terminate();process.wait(timeout=15)
            report['owned_process_stopped']=process.poll() is not None
        job.close()
        save()

if __name__=='__main__':main()
