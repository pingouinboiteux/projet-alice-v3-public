"""Worker EventSub en lecture seule; aucun cerveau, outil ou souvenir."""
import asyncio
import json
import logging
import os
from pathlib import Path
import sys
import threading

PROJECT=Path(__file__).resolve().parents[2]
os.environ['ALICE_ROOT']=str(PROJECT)
sys.path.insert(0,str(PROJECT/'src'))
from alice.twitch import coffre, reglages

lock=threading.Lock()
def send(value):
    with lock:
        print(json.dumps(value,ensure_ascii=False),flush=True)


def chat_message(event):
    # This transport never posts chat, so the authenticated account cannot echo
    # our replies. It has exactly the same untrusted rights as every viewer.
    return {'kind':'chat','author':str(event.chatter_user_id),
            'display_name':str(event.chatter_user_name or '')[:80],
            'text':str(event.message.text)[:2000]}


async def run():
    from twitchAPI.twitch import Twitch
    from twitchAPI.helper import first
    from twitchAPI.type import AuthScope
    from twitchAPI.eventsub.websocket import EventSubWebsocket
    logging.disable(logging.CRITICAL)
    twitch=eventsub=None
    try:
        values={name:coffre.lire(name) for name in coffre.CIBLES}
        if not all(values.values()):
            send({'kind':'status','state':'not_configured'}); return
        twitch=await Twitch(values['client_id'],values['client_secret'],authenticate_app=False)
        async def refresh(token,refresh_token):
            coffre.enregistrer('jeton',token)
            coffre.enregistrer('rafraichissement',refresh_token)
        twitch.user_auth_refresh_callback=refresh
        await twitch.set_user_authentication(values['jeton'],[AuthScope.USER_READ_CHAT],values['rafraichissement'])
        me=await first(twitch.get_users())
        channel=reglages.lire_chaine()
        target=await first(twitch.get_users(logins=[channel])) if channel else me
        if me is None or target is None: raise ValueError('Compte absent')
        eventsub=EventSubWebsocket(twitch)
        eventsub.start()
        async def chat(data):
            event=data.event
            send(chat_message(event))
        await eventsub.listen_channel_chat_message(target.id,me.id,chat)
        send({'kind':'status','state':'ready'})
        # EOF is the owning desktop closing; do not survive it.
        await asyncio.to_thread(sys.stdin.readline)
    except Exception as error:
        send({'kind':'status','state':'error','error_type':type(error).__name__})
    finally:
        if eventsub is not None: await eventsub.stop()
        if twitch is not None: await twitch.close()


if __name__=='__main__':
    asyncio.run(run())
