from __future__ import annotations
import logging
import os
import time
from datetime import datetime
from pathlib import Path
import httpx
from .config import Settings
from .engine import Engine
from .storage import Store
from .terminal import Terminal

log=logging.getLogger(__name__)

class Telegram:
    def __init__(self,token:str):
        self.api=f'https://api.telegram.org/bot{token}/'
        self.client=httpx.Client(timeout=httpx.Timeout(50.0,connect=12.0))

    def call(self,method,payload=None):
        r=self.client.post(self.api+method,json=payload or {})
        r.raise_for_status()
        result=r.json()
        if not result.get('ok'):raise RuntimeError(f'Telegram {method}: API refused')
        return result['result']

    def say(self,chat_id:int,body:str):
        for offset in range(0,len(body),3700):
            self.call('sendMessage',{'chat_id':chat_id,'text':body[offset:offset+3700],
                                     'disable_web_page_preview':True})

    def file(self,chat_id:int,path:Path):
        with path.open('rb') as fp:
            r=self.client.post(self.api+'sendDocument',data={'chat_id':str(chat_id)},
                               files={'document':(path.name,fp,'application/pdf')})
        r.raise_for_status()
        if not r.json().get('ok'):raise RuntimeError('Telegram gagal mengirim PDF')

    def poll(self,offset):
        return self.call('getUpdates',{'offset':offset,'timeout':25,'limit':30,'allowed_updates':['message']})


def process_update(update:dict,tg:Telegram,engine:Engine,s:Settings,terminal:Terminal|None=None):
    msg=update.get('message') or {}
    if not msg:return
    user=msg.get('from') or {}
    chat=msg.get('chat') or {}
    chat_id=chat.get('id')
    user_id=user.get('id')
    text=str(msg.get('text') or '').strip()
    # Help owner identify the account without exposing any bot credentials.
    if text=='/myid' and chat.get('type')=='private' and user_id:
        tg.say(chat_id,f'Telegram user ID Anda: {user_id}\nIsikan nilai ini ke TELEGRAM_OWNER_ID di file konfigurasi.')
        return
    if user_id!=s.owner_id or chat.get('type')!='private':
        log.warning('rejected Telegram update from unauthorized user/chat')
        return
    if not text:
        tg.say(chat_id,'Untuk saat ini TosBot menerima pesan teks. Kirim /help untuk contoh.');return
    try:
        term_reply = terminal.handle(text) if terminal is not None else None
        if term_reply is not None:
            tg.say(chat_id,term_reply)
            # Best-effort removal of a one-time TOTP message after it is processed.
            # Telegram is cloud-based, so this does not guarantee full deletion.
            if text.startswith('/auth ') and msg.get('message_id'):
                try: tg.call('deleteMessage',{'chat_id':chat_id,'message_id':msg['message_id']})
                except Exception: pass
            return
        reply,doc=engine.handle(text)
        tg.say(chat_id,reply)
        if doc is not None:tg.file(chat_id,doc)
    except Exception:
        # Avoid logging exception strings/tracebacks containing bot-token URLs.
        log.error('handler error (details suppressed to protect Telegram token)')
        try: tg.say(chat_id,'Terjadi kendala internal. Admin bisa melihat journalctl -u tosbot-ai -n 50.')
        except Exception:pass


def run():
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(name)s %(message)s')
    # HTTPX logs full Telegram URLs, which contain the bot token. Never log them.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    s=Settings.load();s.validate()
    s.db_path.parent.mkdir(parents=True,exist_ok=True)
    s.out_dir.mkdir(parents=True,exist_ok=True)
    db=Store(s.db_path)
    engine=Engine(s,db)
    terminal=Terminal(s,db)
    tg=Telegram(s.token)
    offset=db.get_kv('telegram_offset',0)
    log.info('TosBot started; polling Telegram; private owner required')
    while True:
        try:
            for line in terminal.finished_jobs():
                tg.say(s.owner_id,line)
            for r in db.due_reminders():
                try:
                    when=datetime.fromtimestamp(r['due'],s.tz).strftime('%d/%m/%Y %H:%M WIB')
                    tg.say(r['owner'],f"⏰ Pengingat TosBot:\n{r['title']}\nWaktu: {when}")
                    db.mark_sent(r['id'])
                except Exception:
                    log.error('reminder delivery failed (details suppressed)')
            updates=tg.poll(offset)
            for update in updates:
                current=update['update_id']
                if current<offset:continue
                process_update(update,tg,engine,s,terminal)
                offset=current+1
                db.set_kv('telegram_offset',offset)
        except KeyboardInterrupt:raise
        except Exception as exc:
            code=getattr(getattr(exc,'response',None),'status_code',None)
            log.error('Telegram polling failed: %s, HTTP=%s; retry after backoff',type(exc).__name__,code)
            time.sleep(8)

if __name__=='__main__':run()
