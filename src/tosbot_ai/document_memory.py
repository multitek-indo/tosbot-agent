"""Local, explicit reuse of finalized document facts; never calls the LLM."""
from __future__ import annotations
import re
from .documents import valid_item
from .document_intent import single_price_reply

# Scope this parser to document creation, not server or shell commands.
_CREATE = re.compile(r'^\s*(?:@[-_\w]+\s+)?(?:(?:tolong|mohon|bantu)\s+)?(?:buatkan|buat|bikin|bikinkan|gawe|gawekno|gawekan|buatin)\s+(?:draft\s+|surat\s+)?(invoice|faktur|invoce|inovice|penawaran|quotation)\b', re.I)
_REUSE = re.compile(r'\b(?:seperti\s+(?:kemarin|sebelumnya|terakhir)|kayak\s+kemarin|kaya\s+kemarin|sama\s+seperti\s+kemarin|koyo\s+wingi|kaya\s+wingi|ulang(?:i)?\s+(?:yang\s+)?terakhir|(?:yang\s+)?terakhir)\b',re.I)

def normalize_create(text: str) -> str:
    m = _CREATE.match(text)
    if not m: return text
    kind = 'offer' if m[1].lower() in ('penawaran','quotation') else 'invoice'
    return ('buatkan penawaran' if kind == 'offer' else 'buatkan invoice') + text[m.end():]

def name_key(value: str) -> str:
    # Case, punctuation and common honorifics only; never fuzzy-match customers.
    value = re.sub(r'^(?:mr|mrs|ms|pak|bapak|bu|ibu)\b\.?\s*', '', str(value).casefold())
    return ' '.join(re.findall(r'\w+', value))

def reuse_request(text: str):
    """Return None for unrelated text; dict with error for unsupported reuse."""
    m = _CREATE.match(text)
    if not m: return None
    rest = text[m.end():].strip()
    ref = _REUSE.search(rest)
    if not ref: return None
    kind = 'offer' if m[1].lower() in ('penawaran','quotation') else 'invoice'
    before = rest[:ref.start()].strip(' ,')
    if before and not re.fullmatch(r'(?:untuk|kepada|kepad|buat)\s+[^,;\n]{1,150}', before, re.I):
        return {'error':'Sebutkan pelanggan sebelum "seperti kemarin", atau gunakan "buat invoice terakhir".'}
    recipient = re.sub(r'^(?:untuk|kepada|kepad|buat)\s+', '', before, flags=re.I)
    tail = rest[ref.end():].strip(' ,;.!')
    # Only explicitly supported edits; do not silently discard other requests.
    tail = re.sub(r'^(?:barangnya|itemnya|produknya)\s+sama\b\s*[, ]*', '', tail, flags=re.I)
    tail = re.sub(r'^(?:tapi|tetapi|namun|cuma)\s+', '', tail, flags=re.I)
    edits = {}
    for part in re.split(r'\s*[,;]\s*|\s+dan\s+(?=(?:po|nomor|jumlah|qty|harga)\b)', tail, flags=re.I) if tail else []:
        q = re.fullmatch(r'(?:jumlah(?:nya)?|qty)\s*(?:(?:jadi|menjadi)\s+|[:=]\s*)?(\d{1,5})\s*(?:unit|unut|unot|pcs|buah)?',part,re.I)
        p = re.fullmatch(r'(?:harga(?:nya)?(?:\s+per\s+unit)?)\s*(?:(?:jadi|menjadi)\s+|[:=]\s*)?(.+)',part,re.I)
        po = re.fullmatch(r'(?:nomor\s+|no\.?\s+)?po(?:\s+customer)?(?:\s+baru)?\s*[:=]?\s+([A-Za-z0-9][A-Za-z0-9/_.-]{0,79})',part,re.I)
        if q and 1 <= int(q[1]) <= 10000 and 'qty' not in edits: edits['qty']=int(q[1])
        elif p and 'price' not in edits and (price:=single_price_reply(p[1])) is not None: edits['price']=price
        elif po and kind=='invoice' and 'po_number' not in edits and any(c.isdigit() for c in po[1]): edits['po_number']=po[1]
        else: return {'error':'Perubahan belum jelas. Gunakan jumlah, harga, dan PO baru dipisahkan koma; perubahan lain dapat dilakukan pada draft.'}
    return {'kind':kind,'recipient':recipient,'edits':edits}

def snapshot(draft: dict) -> dict:
    # No old PO, serial, payment terms, discount or job-specific notes reused.
    return {'customer':draft['customer'], 'attention':draft.get('attention',''),
            'customer_address':draft.get('customer_address',''),
            'items':[dict(name=x['name'],qty=x['qty'],unit=x['unit'],price=x['price']) for x in draft['items']]}

def reuse_data(record: dict, request: dict) -> dict | None:
    data = snapshot(record)
    data['doc_type'] = request['kind']
    edits = request['edits']
    if ('qty' in edits or 'price' in edits) and len(data['items']) != 1: return None
    for key in ('qty','price'):
        if key in edits: data['items'][0][key]=edits[key]
    if not all(valid_item(x) for x in data['items']): return None
    if 'po_number' in edits: data['po_number']=edits['po_number']
    return data
