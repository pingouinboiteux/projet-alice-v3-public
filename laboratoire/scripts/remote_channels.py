"""Owned transports. Transport provenance never comes from message text."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import wave

from remote_bridge import DiscordBridgeClient
from remote_dialogue import RemoteDialogue, RemoteText
from remote_filter import Reglages, examiner_sortie

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parent
# Public text can wait through a complete local spoken reply. Discord audio
# remains short-lived so an old utterance is not answered out of conversation.
PENDING_SECONDS={'twitch':120,'discord':30}


def vault():
    # Only this credential module is loaded; no original service or memory.
    spec=importlib.util.spec_from_file_location('lab_discord_vault',PROJECT/'src/alice/discord_voice/coffre.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {name:module.lire(name) for name in module.CONNEXION}


def public_filter():
    path=PROJECT/'data/private/twitch_a_ne_jamais_dire.txt'
    secrets_set=set(); banned=set()
    if path.is_file():
        if path.stat().st_size>65536: raise ValueError('Filtre prive trop volumineux')
        for line in path.read_text(encoding='utf-8').splitlines():
            kind,sep,value=line.split('#',1)[0].partition(':')
            if sep and value.strip():
                if kind.strip().lower()=='secret': secrets_set.add(value.strip())
                if kind.strip().lower()=='interdit': banned.add(value.strip())
    rules=Reglages(frozenset(secrets_set),frozenset(banned))
    return lambda text: examiner_sortie(text,reglages=rules).texte


class RemoteChannels:
    def __init__(self,session,events,*,store=None,library=None):
        self.session=session
        self.events=events
        self.pending=queue.Queue(maxsize=16)
        self.pending_lock=threading.Lock()
        self.processes={}
        self.generations={'twitch':0,'discord':0}
        self.enabled={'twitch':False,'discord':False}
        self.bridge=None
        self.closed=False
        self.dialogue=RemoteDialogue(session.ask,public_filter(),store=store,library=library)
        self.next_twitch=0
        self.next_remote=0
        self.last_status={}
        self.connection_status={}

    def status(self,source,state):
        if state in {'ready','off','connecting','disconnected','not_configured'}:
            self.connection_status[source]=state
        if self.last_status.get(source)==state: return
        self.last_status[source]=state
        self.events.put(('remote_status',(source,state)))
        observer=getattr(self.session,'observer',None)
        if observer: observer.emit('external.status',{'source':source,'state':state})

    def enqueue(self,source,generation,payload):
        if self.closed or generation!=self.generations[source] or not self.enabled[source]: return
        if source=='twitch' and not re.search(r'\balice\b',payload.text,re.I):
            self.trace('external.skipped',source,reason='not_addressed');return
        with self.pending_lock:
            if self.closed or generation!=self.generations[source] or not self.enabled[source]:return
            try:
                self.pending.put_nowait((source,generation,time.monotonic(),payload))
                self.trace('external.received',source,queued=self.pending.qsize())
            except queue.Full:
                # Drop new traffic instead of allocating or delaying local requests.
                self.status(source,'queue_full')
                self.trace('external.skipped',source,reason='queue_full')

    def take_ready(self):
        """Keep throttled Twitch requests bounded; Discord may pass them."""
        now=time.monotonic()
        with self.pending_lock:
            # Scan once, preserving FIFO among deferred requests. Producers use
            # the same lock so reinsertion cannot exceed the bounded capacity.
            selected=None
            for _ in range(self.pending.qsize()):
                item=self.pending.get_nowait()
                source,generation,received,_=item
                stale=(generation!=self.generations[source] or not self.enabled[source] or now-received>PENDING_SECONDS[source])
                eligible=stale or source!='twitch' or now>=self.next_twitch
                if selected is None and eligible:selected=item
                else:self.pending.put_nowait(item)
            return selected

    def has_ready(self):
        """Wake idle microphone capture only for traffic that can be handled.

        No model, sound or dequeue here; safe to poll from the listening loop.
        Stale traffic is also ready for disposal, avoiding a stuck full queue.
        """
        now=time.monotonic()
        if now<self.next_remote:return False
        with self.pending_lock:
            with self.pending.mutex:
                return any(generation!=self.generations[source] or not self.enabled[source]
                    or now-received>PENDING_SECONDS[source] or source!='twitch'
                    or now>=self.next_twitch
                    for source,generation,received,_ in self.pending.queue)

    def trace(self,kind,source,**metrics):
        observer=getattr(self.session,'observer',None)
        if observer:observer.emit(kind,{'source':source,**metrics})

    def toggle(self,source):
        if source not in self.enabled: raise ValueError('Canal inconnu')
        if self.enabled[source]: self.disconnect(source); return
        if source in self.processes: self.disconnect(source)
        self.enabled[source]=True
        self.generations[source]+=1
        generation=self.generations[source]
        self.status(source,'connecting')
        try:
            if source=='twitch':
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8')
                process=subprocess.Popen([str(PROJECT/'.venvs/twitch/Scripts/python.exe'),'-B',
                    'scripts/twitch_reader.py'],cwd=ROOT,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,text=True,encoding='utf-8',creationflags=subprocess.CREATE_NO_WINDOW)
                self.processes[source]=process
                self.session.children['external_twitch']=process
                self.session.job.assign(process)
                threading.Thread(target=self.read_twitch,args=(process,generation),daemon=True).start()
            else:
                values=vault()
                if not all(values.values()): raise ValueError('Coffre Discord incomplet')
                node=shutil.which('node')
                if not node: raise ValueError('Node absent')
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                key=secrets.token_urlsafe(32)
                env=dict(os.environ,ALICE_DISCORD_TOKEN=values['token'],
                    ALICE_DISCORD_GUILD_ID=values['guild_id'],ALICE_DISCORD_CHANNEL_ID=values['channel_id'],
                    ALICE_DISCORD_BRIDGE_KEY=key,ALICE_DISCORD_BRIDGE_PORT=str(port))
                process=subprocess.Popen([node,'bridge/discord/src/main.mjs'],cwd=ROOT,env=env,
                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
                self.processes[source]=process
                self.session.children['external_discord']=process
                self.session.job.assign(process)
                self.bridge=DiscordBridgeClient(f'http://127.0.0.1:{port}',key)
                threading.Thread(target=self.read_discord,args=(process,self.bridge,generation),daemon=True).start()
        except Exception as error:
            self.disconnect(source)
            self.status(source,'error_'+type(error).__name__)

    def read_twitch(self,process,generation):
        try:
            while self.enabled['twitch'] and generation==self.generations['twitch']:
                line=process.stdout.readline(16385)
                if not line: break
                if generation!=self.generations['twitch']: break
                if len(line)>16384: raise ValueError('Message trop long')
                value=json.loads(line)
                if value.get('kind')=='chat':
                    self.enqueue('twitch',generation,RemoteText('twitch',value['author'],value['text'],value.get('display_name','')))
                elif value.get('kind')=='status': self.status('twitch',value['state'])
        except Exception:
            self.status('twitch','error')
        finally:
            if generation==self.generations['twitch']:
                self.enabled['twitch']=False
                if self.last_status.get('twitch') not in {'error','not_configured'}:
                    self.status('twitch','disconnected')

    def read_discord(self,process,bridge,generation):
        started=time.monotonic();ready=False
        try:
            while self.enabled['discord'] and generation==self.generations['discord']:
                if process.poll() is not None: break
                try:
                    health=bridge.health()
                    if health.get('ready'):
                        if not ready: self.status('discord','ready');ready=True
                        event=bridge.next()
                        if event and event.kind=='utterance' and not event.utterance.speaker.bot:
                            self.enqueue('discord',generation,event)
                    elif time.monotonic()-started>45: raise TimeoutError()
                except OSError:
                    if time.monotonic()-started>45: raise
                time.sleep(.15)
        except Exception:
            self.status('discord','error')
        finally:
            if generation==self.generations['discord']:
                self.enabled['discord']=False
                if self.last_status.get('discord')!='error': self.status('discord','disconnected')

    def disconnect(self,source):
        self.enabled[source]=False
        self.generations[source]+=1
        process=self.processes.pop(source,None)
        if process:
            if process.poll() is None: process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired: process.kill();process.wait(timeout=5)
            for name in ('stdin','stdout'):
                pipe=getattr(process,name,None)
                if pipe:
                    try: pipe.close()
                    except OSError: pass
        if source=='discord': self.bridge=None
        self.dialogue.clear()
        self.status(source,'off')

    def handle_one(self,hearing,voice):
        if time.monotonic()<self.next_remote: return False
        item=self.take_ready()
        if item is None:return False
        source,generation,received,payload=item
        if generation!=self.generations[source] or not self.enabled[source]:
            self.trace('external.skipped',source,reason='inactive_generation')
            return True
        if time.monotonic()-received>PENDING_SECONDS[source]:
            self.trace('external.skipped',source,reason='expired',age_seconds=round(time.monotonic()-received,2))
            return True
        bridge=None;epoch=None
        subtitle=getattr(voice,"subtitles",None);ticket=None
        try:
            self.session.check()
            if source=='twitch':
                message=payload
                self.events.put(('text',('Twitch (aucun droit d action)',message.text)))
                if not re.search(r'\balice\b',message.text,re.I):
                    self.trace('external.skipped',source,reason='not_addressed');return True
                self.next_twitch=time.monotonic()+15
            else:
                bridge=self.bridge;epoch=payload.human_epoch
                result=hearing.command('remote_audio',pcm=base64.b64encode(payload.utterance.pcm_s16le).decode('ascii'))
                if result.get('status')!='transcribed' or not result.get('accepted'): return True
                message=RemoteText('discord',payload.user_id,result['cleaned'][:2000],payload.utterance.speaker.display_name)
                self.events.put(('text',('Discord (aucun droit d action)',message.text)))
                if not bridge.reserve_reply(epoch): return True
            from observation import span,emit,Observation
            observer=getattr(self.session,'observer',None)
            if isinstance(observer,Observation):observer.begin_turn(message.text,source)
            emit(self.session,'external.turn',{'source':source,'action_access':False})
            with span(self.session,'external_dialogue'):
                answer=self.dialogue.answer(message)
            self.session.check()
            self.events.put(('text',('Alice vers '+source,answer)))
            if bridge:
                parts=voice.audio_parts(answer)
                reply_id=secrets.token_hex(16)
                playing=True
                duration=0
                try:
                    for index,(path,info) in enumerate(parts):
                        if not playing: continue  # Drain the request without sending more speech.
                        with wave.open(str(path),'rb') as wav:
                            if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(1,2,24000):
                                raise ValueError('Format vocal externe invalide')
                            pcm=wav.readframes(wav.getnframes())
                        if len(pcm)>24000*2*30: raise ValueError('Bloc Discord trop long')
                        duration+=len(pcm)/48000
                        playing=bridge.play_part(pcm,epoch,reply_id=reply_id,part_index=index,
                            final=index==info['parts']-1)
                        if playing and index==0 and subtitle: ticket=subtitle.show(answer)
                        if not playing:
                            bridge.stop()
                            self.status(source,'reply_cancelled')
                    if playing:
                        deadline=time.monotonic()+duration+5
                        while time.monotonic()<deadline:
                            self.session.check()
                            health=bridge.health()
                            if not health.get('playing') and not health.get('playback_active'): break
                            time.sleep(.15)
                except Exception:
                    bridge.stop()
                    raise
                finally: parts.close()
            else: voice.speak(answer)
            if self.dialogue.store and (not bridge or playing):
                self.dialogue.delivered(message,answer)
        except Exception as error:
            self.session.check()
            self.status(source,'error_'+type(error).__name__)
        finally:
            if subtitle and ticket is not None: subtitle.clear(ticket)
            self.next_remote=time.monotonic()+2
            if bridge and epoch is not None:
                try: bridge.release_reply(epoch)
                except OSError: pass
        return True

    def close(self):
        self.closed=True
        for source in self.enabled: self.disconnect(source)
        while not self.pending.empty():
            try: self.pending.get_nowait()
            except queue.Empty: break
