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
from .terminal import Terminal, TrustedGroupTerminal
from .group import GroupAssistant
import re
from dataclasses import replace

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

    def say(self,chat_id:int,body:str,reply_to_message_id:int|None=None,
            message_thread_id:int|None=None):
        for offset in range(0,len(body),3700):
            payload={'chat_id':chat_id,'text':body[offset:offset+3700],
                     'disable_web_page_preview':True}
            if reply_to_message_id is not None:
                payload['reply_parameters']={'message_id':reply_to_message_id,
                                             'allow_sending_without_reply':True}
            if message_thread_id is not None:
                payload['message_thread_id']=message_thread_id
            self.call('sendMessage',payload)

    def file(self,chat_id:int,path:Path):
        with path.open('rb') as fp:
            r=self.client.post(self.api+'sendDocument',data={'chat_id':str(chat_id)},
                               files={'document':(path.name,fp,'application/pdf')})
        r.raise_for_status()
        if not r.json().get('ok'):raise RuntimeError('Telegram gagal mengirim PDF')

    def poll(self,offset):
        return self.call('getUpdates',{'offset':offset,'timeout':25,'limit':30,'allowed_updates':['message']})


def _group_addressed(text: str, entities: list, bot_username: str) -> tuple[bool,str]:
    """Recognize explicit @bot mention or /command@bot with UTF-16 offsets.

    A separate check in _process_group allows genuine replies to this bot.
    """
    username = str(bot_username or '').lstrip('@').strip()
    if not username or not re.fullmatch(r'[A-Za-z0-9_]{4,32}', username):
        return False, text
    target = username.casefold()
    spans=[]
    # Telegram normally supplies the entity. Also recognize a literal typed
    # mention for clients that omit entities; word boundaries avoid emails.
    pattern=re.compile(r'(?<![\w@])@'+re.escape(username)+r'(?![\w])',re.I)
    for m in pattern.finditer(text):
        spans.append((m.start(),m.end()))
    # A /command@bot is addressed too, while /command@otherbot is NOT.
    cmd_pattern=re.compile(r'(?<!\S)/([A-Za-z0-9_]+)@'+re.escape(username)+r'(?![\w])',re.I)
    for m in cmd_pattern.finditer(text):
        spans.append((m.start(0)+len(m.group(1))+1,m.end()))
    # Handle Telegram entity offsets, which count UTF-16 code units.
    utf16=text.encode('utf-16-le')
    for e in entities if isinstance(entities,list) else []:
        if not isinstance(e,dict) or e.get('type') not in ('mention','bot_command'):
            continue
        try:
            start_utf16=int(e.get('offset')); length_utf16=int(e.get('length'))
            if start_utf16 < 0 or length_utf16 <= 0:
                continue
            prefix=utf16[:start_utf16*2].decode('utf-16-le')
            raw=utf16[start_utf16*2:(start_utf16+length_utf16)*2].decode('utf-16-le')
        except (ValueError, TypeError, UnicodeDecodeError):
            continue
        start_cp=len(prefix)
        if raw.casefold()=='@'+target:
            spans.append((start_cp,start_cp+len(raw)))
        elif re.fullmatch(r'/[a-z0-9_]+@'+re.escape(target),raw.casefold()):
            at=raw.rfind('@')
            spans.append((start_cp+at,start_cp+len(raw)))
    if not spans:
        return False, text
    # Remove mentions from right to left. For commands retain /command.
    for start,end in sorted(set(spans), reverse=True):
        text=text[:start]+text[end:]
    return True, re.sub(r'\s+', ' ', text).strip()


def _reply_to_this_bot(message:dict, bot_user_id:int) -> bool:
    """Check Telegram-authenticated identity, not quoted text or username.

    Bot API reply_to_message.from.id is the original message author; forwarded
    messages and plain quote text must not count. Require same group/topic.
    """
    if not isinstance(bot_user_id,int) or bot_user_id <= 0:
        return False
    replied = message.get('reply_to_message')
    if not isinstance(replied,dict):
        return False
    sender=replied.get('from') or {}
    if (not isinstance(sender,dict) or sender.get('id') != bot_user_id or
        sender.get('is_bot') is not True):
        return False
    current_chat=(message.get('chat') or {}).get('id')
    quoted_chat=(replied.get('chat') or {}).get('id')
    if not isinstance(current_chat,int) or quoted_chat != current_chat:
        return False
    # A reply in another forum topic must not continue this topic's workflow.
    quoted_topic=replied.get('message_thread_id')
    current_topic=message.get('message_thread_id')
    if quoted_topic is not None and quoted_topic != current_topic:
        return False
    return True


def _process_group(update:dict,tg:Telegram,s:Settings,group_assistant:GroupAssistant|None,
                   bot_username:str,db:Store|None=None, trusted_routers:dict|None=None,
                   bot_user_id:int=0):
    msg=update.get('message') or {}
    chat=msg.get('chat') or {}
    user=msg.get('from') or {}
    chat_id=chat.get('id')
    if not (s.groups_enabled and group_assistant and isinstance(chat_id,int)):
        return
    if s.allowed_group_ids and chat_id not in s.allowed_group_ids:
        return
    # Reject anonymous admins, channels posting as users, and bot senders.
    if msg.get('sender_chat') or not isinstance(user.get('id'),int) or user.get('is_bot'):
        return
    text=msg.get('text')
    if not isinstance(text,str):
        return
    addressed, clean=_group_addressed(text, msg.get('entities') or [], bot_username)
    if not addressed:
        # Reply is an intentional way to address the bot, even without @mention.
        # Plain messages, replies to other members, and forwarded messages stay silent.
        if not _reply_to_this_bot(msg,bot_user_id):
            return
        clean=text.strip()
    reply_only = not addressed
    try:
        if s.trusted_group_admin and chat_id in s.allowed_group_ids and db is not None and trusted_routers is not None:
            if chat_id not in trusted_routers:
                trusted_routers[chat_id]=(TrustedGroupTerminal(s,db,chat_id),
                    Engine(replace(s,owner_id=chat_id),db))
            terminal, engine=trusted_routers[chat_id]
            doc=None
            if reply_only:
                # A conversational Reply may continue draft/PDF workflows, but
                # should not accidentally turn a quoted message into shell access.
                # Root/terminal commands require a fresh explicit @mention.
                if re.match(r'(?i)^\s*(?:/sudo|/sh|/auth|sudo|apt(?:-get)?|bash|sh|systemctl|rm|dd|chmod|chown|mkdir|reboot|shutdown)(?:\s|$)',clean):
                    reply='Untuk perintah terminal/admin, kirim lagi dengan @'+bot_username+' di awal pesan.'
                else:
                    reply,doc=engine.handle(clean)
            else:
                reply=terminal.handle(clean,user['id'])
                if reply is None:
                    reply,doc=engine.handle(clean)
            tg.say(chat_id,reply,reply_to_message_id=msg.get('message_id'),
                   message_thread_id=msg.get('message_thread_id'))
            if doc is not None:
                tg.file(chat_id,doc)
        else:
            reply=group_assistant.handle(clean,chat_id,user['id'],msg.get('message_thread_id'))
            tg.say(chat_id,reply,reply_to_message_id=msg.get('message_id'),
                   message_thread_id=msg.get('message_thread_id'))
    except Exception:
        log.error('group handler failed (details suppressed)')
        try: tg.say(chat_id,'Maaf, ada kendala memproses pesan grup.',
                    reply_to_message_id=msg.get('message_id'),
                    message_thread_id=msg.get('message_thread_id'))
        except Exception: pass


def process_update(update:dict,tg:Telegram,engine:Engine,s:Settings,terminal:Terminal|None=None,
                   group_assistant:GroupAssistant|None=None,bot_username:str='',
                   db:Store|None=None,trusted_routers:dict|None=None,bot_user_id:int=0):
    msg=update.get('message') or {}
    if not msg:return
    user=msg.get('from') or {}
    chat=msg.get('chat') or {}
    chat_id=chat.get('id')
    user_id=user.get('id')
    text=str(msg.get('text') or '').strip()
    if chat.get('type') in {'group','supergroup'}:
        _process_group(update,tg,s,group_assistant,bot_username,db,trusted_routers,bot_user_id)
        return
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
    group_assistant=GroupAssistant(s,db) if s.groups_enabled else None
    trusted_routers={}
    if s.trusted_group_admin:
        # Need these from startup to notify completed jobs even after restart.
        for group_id in s.allowed_group_ids:
            trusted_routers[group_id]=(TrustedGroupTerminal(s,db,group_id),
                                       Engine(replace(s,owner_id=group_id),db))
    tg=Telegram(s.token)
    # Verified Telegram identity. Never rely on hardcoded names or untrusted
    # group messages to tell us which @username belongs to this bot.
    bot_username=''
    bot_user_id=0
    if s.groups_enabled:
        me=tg.call('getMe')
        bot_username=str(me.get('username') or '')
        bot_user_id=int(me.get('id') or 0)
        if not bot_username or bot_user_id <= 0:
            raise RuntimeError('Telegram getMe tidak mengembalikan identitas bot yang valid')
    offset=db.get_kv('telegram_offset',0)
    log.info('TosBot started; Telegram group mode=%s, owner private commands unchanged',s.groups_enabled)
    while True:
        try:
            for line in terminal.finished_jobs():
                tg.say(s.owner_id,line)
            for group_id,(group_terminal,_) in trusted_routers.items():
                for line in group_terminal.finished_jobs():
                    tg.say(group_id,line)
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
                process_update(update,tg,engine,s,terminal,group_assistant,bot_username,db,trusted_routers,bot_user_id)
                offset=current+1
                db.set_kv('telegram_offset',offset)
        except KeyboardInterrupt:raise
        except Exception as exc:
            code=getattr(getattr(exc,'response',None),'status_code',None)
            log.error('Telegram polling failed: %s, HTTP=%s; retry after backoff',type(exc).__name__,code)
            time.sleep(8)

if __name__=='__main__':run()
