"""Bounded directory tools. Model proposes operations; backend validates each one."""
from __future__ import annotations
import json
import logging
import re
import subprocess
from typing import Any, TypedDict

log = logging.getLogger(__name__)
HOME_ROOT = '/home/tosbot'
DIR_ROOT = HOME_ROOT  # Starting directory; backwards compatible import name.
CONFIRMATIONS = {'ya','iya','iya buatkan','ya buatkan','oke','ok','yes','nggih','leres','iyo','y','betul','bener','benar','konfirmasi buat folder','buat sekarang','lanjut buat','silakan buat'}


class DirState(TypedDict, total=False):
    operation: str
    path: str
    authorized: bool
    error: str
    result: dict[str, Any]


def safe_path(value: str | None, cwd: str | None = None) -> str | None:
    raw = str(value or '').strip().strip('`"\' ').rstrip('/')
    if not raw or len(raw) > 240 or '\\' in raw or '\x00' in raw:
        return None
    low = raw.lower()
    alias = {'home': HOME_ROOT, 'tosbot': HOME_ROOT, 'dir home': HOME_ROOT,
             'script': HOME_ROOT + '/script', 'skrip': HOME_ROOT + '/script',
             '/script': HOME_ROOT + '/script', 'folder script': HOME_ROOT + '/script',
             'dir script': HOME_ROOT + '/script',
             'ai-agent': HOME_ROOT + '/script/ai-agent', 'agent': HOME_ROOT + '/script/ai-agent',
             'folder agent': HOME_ROOT + '/script/ai-agent'}
    if low in alias:
        raw = alias[low]
    elif raw == '.':
        raw = cwd or HOME_ROOT
    elif raw == '..':
        raw = (cwd or HOME_ROOT).rsplit('/', 1)[0]
    elif not raw.startswith('/'):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', raw):
            return None
        raw = (cwd or HOME_ROOT) + '/' + raw
    if raw != HOME_ROOT and not raw.startswith(HOME_ROOT + '/'):
        return None
    rest = raw[len(HOME_ROOT):].strip('/')
    parts = rest.split('/') if rest else []
    if len(parts) > 8 or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', p) or p in ('.', '..') for p in parts):
        return None
    return HOME_ROOT + ('/' + '/'.join(parts) if parts else '')


def parse_directory_command(text: str, cwd: str | None = None) -> tuple[str, str | None] | None:
    t = re.sub(r'\s+', ' ', str(text or '').lower()).strip()
    if not t:
        return None
    if re.search(r'\b(hapus|delete|rm|rename|ubah|pindah|move|chmod|chown|buat(?:kan)? folder|mkdir|ping)\b', t):
        return None
    has_dir = bool(re.search(r'\b(dir|direktori|directory|folder|path|skrip|script|ai-agent|home|tosbot)\b', t))
    verb = bool(re.search(r'\b(cek|lihat|tampil(?:kan)?|list|daftar|isi|berapa|hitung|jumlah|ls|rincian|struktur|tree|ono|ana|delok)\b', t))
    shell = bool(re.match(r'^ls(?:\s+(-[alh]+))?(?:\s+|$)', t))
    if not ((has_dir and verb) or shell):
        return None
    op = 'tree' if re.search(r'\b(tree|pohon|struktur)\b', t) else (
        'count' if re.search(r'\b(berapa|jumlah|hitung|pinten|piro|cacah)\b', t) else 'list')
    explicit = re.search(r'(/(?:home|root|etc|var)(?:/[A-Za-z0-9_.-]+)*)', t)
    if explicit:
        # Rejected paths MUST remain rejected; never silently redirect.
        return op, safe_path(explicit.group(1), cwd)
    if re.search(r'\b(root|/root)\b', t):
        return op, '/root'  # untrusted value rechecked and denied later
    if re.search(r'\b(ai-agent|agent)\b', t):
        return op, safe_path('ai-agent', cwd)
    if re.search(r'\b(script|skrip)\b', t):
        return op, safe_path('script', cwd)
    if re.search(r'\b(home|tosbot)\b', t):
        return op, HOME_ROOT
    # 'ls' and 'cek folder' use current directory when one is selected.
    if cwd:
        return op, safe_path('.', cwd)
    return op, None


class DirectoryAgent:
    """Validated finite operations; no unbounded shell command execution."""
    def __init__(self, runner=None):
        self.runner = runner or self._run_subprocess
        self.graph = None
        try:
            from langgraph.graph import StateGraph, START, END
            builder = StateGraph(DirState)
            builder.add_node('authorize', self._authorize)
            builder.add_node('execute_readonly_tool', self._execute)
            builder.add_edge(START, 'authorize')
            builder.add_conditional_edges('authorize', lambda s: 'execute_readonly_tool' if s.get('authorized') else END)
            builder.add_edge('execute_readonly_tool', END)
            self.graph = builder.compile()
            log.info('LangGraph directory tool graph enabled')
        except ImportError:
            log.warning('LangGraph unavailable: directory tool uses validated Python fallback')

    @staticmethod
    def _authorize(state: DirState) -> dict:
        path = safe_path(state.get('path'))
        if not path:
            return {'authorized': False, 'error': 'Direktori di luar izin. Saya bisa membaca /home/tosbot beserta subfolder non-rahasianya, tetapi tidak /root atau /etc.'}
        if state.get('operation') not in ('list', 'count', 'tree'):
            return {'authorized': False, 'error': 'Operasi tidak diizinkan.'}
        return {'authorized': True, 'path': path}

    def _execute(self, state: DirState) -> dict:
        try:
            result = self.runner(state['operation'], state['path'])
        except Exception as exc:
            log.warning('Directory tool error: %s', type(exc).__name__)
            result = {'ok': False, 'error': 'Tool folder gagal. Periksa bind mount/sudoers.'}
        return {'result': result}

    @staticmethod
    def _run_subprocess(op: str, path: str) -> dict:
        p = subprocess.run(['sudo','-n','/usr/local/sbin/tosbot-ai-fs-ctl',op,path],
                           capture_output=True, text=True, timeout=15, check=False)
        if not p.stdout.strip():
            return {'ok': False, 'error': f'Tool tidak berjalan (exit={p.returncode}).'}
        try:
            data = json.loads(p.stdout)
            return data if isinstance(data, dict) else {'ok': False, 'error': 'Output tidak valid.'}
        except ValueError:
            return {'ok': False, 'error': 'Output tool tidak valid.'}

    def mkdir(self, path: str) -> str:
        actual = safe_path(path)
        if not actual:
            return '⛔ Path tidak diizinkan.'
        try:
            response = self.runner('mkdir', actual)
        except Exception as exc:
            log.warning('mkdir tool failed: %s',type(exc).__name__)
            return '❌ Gagal menjalankan tool mkdir. Periksa izin folder dan systemd.'
        if not response.get('ok'):
            return '❌ Gagal membuat folder: '+str(response.get('error') or 'error')[:240]
        if response.get('exists'):
            return 'ℹ️ Folder sudah ada: '+actual
        return '✅ Folder berhasil dibuat: '+actual

    def run(self, operation: str, path: str) -> str:
        req: DirState = {'operation': operation, 'path': path}
        if self.graph:
            response = self.graph.invoke(req)
        else:
            response = {**req, **self._authorize(req)}
            if response.get('authorized'):
                response.update(self._execute(response))
        if not response.get('authorized'):
            return '⛔ '+str(response.get('error'))
        payload = response.get('result') or {}
        if not payload.get('ok'):
            return '❌ Gagal membaca folder: '+str(payload.get('error') or 'error')[:180]
        prefix = '📂 '+str(payload.get('path'))
        if operation == 'count':
            return f'{prefix}\nJumlah folder: {payload.get("directories",0)}\nJumlah file: {payload.get("files",0)}'
        if operation == 'tree':
            lines = payload.get('tree') or []
            return prefix+'\n'+ ('\n'.join(lines) if lines else '(kosong)')
        lines = []
        for e in (payload.get('entries') or []):
            if isinstance(e, dict):
                lines.append(('📁 ' if e.get('type') == 'directory' else '📄 ')+str(e.get('name') or '')[:120])
        result = prefix+'\n'+ ('\n'.join(lines) if lines else '(kosong)')
        if payload.get('truncated'):
            result += '\n… Daftar dipotong menjadi 75 entri.'
        return result
