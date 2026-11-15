#!/usr/bin/env python3
"""Basic no-network preflight for accidentally committed secrets/private artifacts.
Not a replacement for GitHub secret scanning or manual review.
"""
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
DENIED_NAMES={'admin-auth.json','tosbot.env','id_rsa','id_ed25519'}
DENIED_SUFFIX={'.pdf','.xlsx','.xls','.sqlite','.sqlite3','.db','.pem','.key','.p12','.pfx','.png','.jpg','.jpeg','.webp','.zip','.tar','.tgz'}
SECRET_PATTERNS=[
    re.compile(r'\b\d{7,12}:[A-Za-z0-9_-]{30,}\b'),  # Telegram bot token
    re.compile(r'\b(?:ghp_|github_pat_|gho_|ghu_|ghs_)[A-Za-z0-9_]{15,}\b'),
    re.compile(r'\bAIza[A-Za-z0-9_-]{20,}\b'),
    re.compile(r'-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----'),
    re.compile(r'(?im)^[ \t]*(?:TELEGRAM_BOT_TOKEN|GROQ_API_KEY|GEMINI_API_KEY|XAI_API_KEY)[ \t]*=[ \t]*(?!ISI_|YOUR_|REPLACE_)[^\s#]{16,}[ \t]*$'),
]
PRIVATE_MARKERS=[]  # add organization-specific forbidden values during private preflight if needed
fail=[]
for f in ROOT.rglob('*'):
    if not f.is_file() or any(p in {'.git','__pycache__','.venv','venv'} for p in f.relative_to(ROOT).parts):
        continue
    relative=str(f.relative_to(ROOT))
    if f.name in DENIED_NAMES or f.suffix.lower() in DENIED_SUFFIX or (f.name.startswith('.env') and f.name != '.env.example'):
        fail.append(f'Forbidden private or binary artifact: {relative}')
        continue
    try: content=f.read_text(encoding='utf-8')
    except UnicodeError:
        fail.append(f'Non-text source: {relative}')
        continue
    if any(p.search(content) for p in SECRET_PATTERNS) or any(marker.lower() in content.lower() for marker in PRIVATE_MARKERS):
        fail.append(f'Possible sensitive string: {relative} (value not shown)')
if fail:
    print('PUBLIC RELEASE CHECK: FAILED')
    print('\n'.join(fail))
    sys.exit(1)
print('PUBLIC RELEASE CHECK: PASS (heuristic only; manually review before public push)')
