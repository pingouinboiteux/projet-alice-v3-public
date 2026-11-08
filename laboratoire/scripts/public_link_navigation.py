"""One-hop navigation to an explicitly named same-origin link.

Caller supplies only the local user's URL,
label and question. Page text cannot create another operation or a second hop.
"""
from public_navigation import PublicPage,read_rendered
from rendered_links import observe_links,links_current,select_link

def read_linked(session,url,label,question,*,source='text',factory=PublicPage,cancelled=lambda:False):
    if source not in ('text','voice'):raise ValueError('local_request_required')
    if type(label) is not str or not label.strip() or len(label)>200:raise ValueError('explicit_link_label_required')
    if type(question) is not str or not question.strip() or len(question)>2000:raise ValueError('explicit_question_required')
    def guard():
        session.check()
        if cancelled():raise ValueError('public_link_cancelled')
    guard();backend=factory(guard)
    previous=getattr(session,'browser_demo',None);session.browser_demo=backend
    try:
        backend.start_url(url)
        before=observe_links(backend.page,guard,expected_url=backend.target)
        stable=False;unchanged=0
        for _ in range(10):
            guard();backend.page.wait_for_timeout(150)
            after=observe_links(backend.page,guard,expected_url=backend.target)
            unchanged=unchanged+1 if after['revision']==before['revision'] else 0
            if unchanged>=3:stable=True;break
            before=after
        if not stable:return {'status':'unstable','reply':'Les liens de la page changent encore.'}
        try:target=select_link(after,label)
        except ValueError as error:
            choices=[]
            if str(error)=='link_missing_or_ambiguous' and not after['truncated']:
                for link in after['links']:
                    try:select_link(after,link['label'])
                    except ValueError:continue
                    if link['label'] not in choices:choices.append(link['label'])
                    if len(choices)>=8:break
            import json
            reply='Ce lien ne peut pas etre suivi de facon univoque dans cette page publique.'
            if choices:reply+=' Liens disponibles : '+', '.join(json.dumps(c,ensure_ascii=False) for c in choices)+'. Precise le nom du lien souhaite.'
            return {'status':'clarify','reason':str(error),'reply':reply,'choices':choices}
        guard()
        if not links_current(backend.page,guard,after,expected_url=backend.target):
            return {'status':'changed','reply':'Le lien a change. Aucune page de destination lue.'}
        source_url=backend.target
    except Exception as error:
        if isinstance(error,(ValueError,RuntimeError,OSError)):raise
        raise RuntimeError('La navigation par lien a ete interrompue.') from error
    finally:
        try:backend.close()
        finally:session.browser_demo=previous
    # A new isolated profile fetches the frozen href; never invoke page scripts
    # through a click. Transport revalidates/pins public DNS on the destination.
    guard()
    result=read_rendered(session,target,question,factory=factory,cancelled=cancelled)
    return {**result,'from_url':source_url,'requested_label':label,'followed_url':target,'hops':1}
