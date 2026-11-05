"""Audit the current install; optional GPU probe uses temporary validation data."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from chat import Session,ROOT
from model_profile import load_profile,verify_resources,relative_path

def resources():
    spec=load_profile();model,_=verify_resources(spec)
    with model.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=spec['sha256']:raise ValueError('Model hash mismatch')
    protected=[]
    for name in ['voice.lock.json','hearing.lock.json']:
        manifest=json.loads((ROOT/'config'/name).read_text(encoding='utf-8'))
        for relative,info in manifest['files'].items():
            path=relative_path(relative)
            if not path.is_file() or path.stat().st_size!=info['bytes']:raise ValueError('Protected resource changed: '+relative)
        protected.append({'manifest':name,'files_verified':len(manifest['files'])})
    return {'model':spec['name'],'weight':model.relative_to(ROOT).as_posix(),'protected_resources':protected}

def model_probe():
    from memory_backend import create_memory
    from persistent_memory import Search
    from intent_router import route
    from alice_desktop import SYSTEM,ROUTING_SYSTEM
    from codex_link import run_task
    session=Session(allow_game=True,fps_protection=False,context_window=16384)
    report={'memory':[],'actions':[],'private_memory_opened':False,'audio_played':False,'microphone_opened':False}
    try:
        session.start();report['device']=session.device;search=Search()
        for index,(text,question) in enumerate([
            ('Le cours commence samedi a 18 h 40. Je me suis trompe : le debut est a 17 h 10 et la fin a 18 h 40.','A quelle heure commence le cours ?'),
            ('Le colis contient trois tasses vertes et un bol orange. Le bol est pour Malik.','Que contient le colis et pour qui est le bol ?'),
            ('Ma soeur Lena deteste les noisettes. Moi je les aime.','Qui aime les noisettes et qui les deteste ?')]):
            with tempfile.TemporaryDirectory(prefix='validation_install_memory_',dir=ROOT/'logs') as folder:
                memory=create_memory(session,'validation_install_'+str(index),Path(folder)/'validation.db',search)
                try:
                    identity=memory.episodes.add('2026-01-15T12:00:00Z',[{'role':'user','content':text}]);before=memory.episodes.get(identity)
                    reply,_=memory.answer(question,[],SYSTEM,lambda _:False)
                    report['memory'].append({'question':question,'reply':reply,'source_preserved':before==memory.episodes.get(identity)})
                finally:memory.close()
            assert not Path(folder).exists()
        for text,expected in [('Le son est trop fort, reduis-le un peu.','volume_delta'),('Ne coupe pas le son.','chat')]:
            action,reply=route(session,[{'role':'system','content':ROUTING_SYSTEM}],text)
            report['actions'].append({'text':text,'expected':expected,'actual':action.kind,'passed':action.kind==expected,'reply':reply})
        with tempfile.TemporaryDirectory(prefix='validation_install_codex_',dir=ROOT/'atelier') as folder:
            result=run_task(session,'Cree uniquement validation.txt contenant ALICE_GEMMA_OK. Relis le fichier. Ne consulte aucun autre dossier.',Path(folder),timeout=120)
            path=Path(folder)/'validation.txt'
            report['codex']={'status':result['status'],'content_verified':path.is_file() and path.read_text(encoding='utf-8').strip()=='ALICE_GEMMA_OK'}
        assert not Path(folder).exists()
        report.update(status='complete',minimum_ram_gib=round(session.minimum_ram/1024**3,3))
    finally:
        session.close();report['owned_processes_stopped']=all(p.poll() is not None for p in session.children.values())
        report['temporary_data_removed']=not session.temp or not Path(session.temp.name).exists()
    return report

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--model',action='store_true');parser.add_argument('--report',default='rapports/verification_installation.json');args=parser.parse_args()
    target=relative_path(args.report)
    if target.exists():raise ValueError('Preserve the previous audit')
    report={'resources':resources()}
    if args.model:report['probe']=model_probe()
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True))

if __name__=='__main__':main()
