"""Deterministic document-intent guards for TosBot v1.12.2.

This module does not contact LLMs and never finalizes or generates a document.
It only extracts explicit facts and repairs NLU fields without inventing facts.
"""
from __future__ import annotations
import re
from typing import Any
from decimal import Decimal, InvalidOperation


_NEW_DOC = re.compile(
    r"^\s*(?:(?:tolong|mohon|bisa|bantu|mas|pak)\s+){0,3}"
    r"(?:buatkan|buat|bikin|gawe(?:kno)?)\s+"
    r"(?:(?:surat|draft|rancangan|dokumen)\s+)?"
    r"(penawaran|quotation|invoice|faktur)\b", re.I,
)
_UNITS = r"(?:unit|unut|unot|unuit|unt|pcs|pc|buah|mesin|item|biji)"
_PLAIN_QTY = re.compile(r"^\s*(\d{1,5})\s*" + _UNITS + r"\s*[.!]?\s*$", re.I)
_ONLY_NUMBER = re.compile(r"^\s*(\d{1,5})\s*$")
_ADDR_START = re.compile(r"(?i)\b(?:jl\.?|jalan|jln\.?|jend\.?|komplek|kompleks|perum(?:ahan)?|dusun)\s+")
_ADDR_KEYWORD = re.compile(r"(?i)\balamat\b")
_BOUNDARY = re.compile(
    r"(?i)\s+(?:(?:dengan\s+)?rincian\b|(?:dengan\s+)?biaya\s+(?:service|servis|perbaikan)\b|"
    r"(?:kasih|beri|tambahkan|tambah|tolong|dengan)\s+keterangan\b|"
    r"\bketerangan\s*[:=]\s*|\bharga\s+(?:rp\s*)?\d|"
    r"\b(?:service|servis)\s+\d+\s*" + _UNITS + r"\b)", re.I,
)
_NOTE = re.compile(r"(?is)\b(?:kasih|beri|tambahkan|tambah|isi|tulis(?:kan)?)?\s*"
                   r"keterangan(?:\s+(?:barang|item|di\s+(?:kolom|tabel)))?\s*[:=]?\s*"
                   r"(.+?)(?:\s*$)")


def is_new_document_request(message: str) -> bool:
    """Only an EXPLICIT create phrase resets a previous draft.

    Support Telegram mention prefixes on messages not already normalized by bot.py.
    """
    clean = re.sub(r"^\s*@[-_\w]+\s+", "", message or "")
    return bool(_NEW_DOC.match(clean))


def single_quantity(message: str, *, allow_bare: bool = False) -> int | None:
    """Accept short replies with Indonesian unit misspellings; not money/model IDs."""
    msg = (message or "").strip()
    m = _PLAIN_QTY.fullmatch(msg)
    if not m and allow_bare:
        m = _ONLY_NUMBER.fullmatch(msg)
    n = int(m.group(1)) if m else None
    return n if n is not None and 1 <= n <= 10000 else None


def single_price_reply(message: str) -> int | None:
    """Read clear Rupiah follow-ups, e.g. 'Harga 1 unit 2juta'."""
    msg = (message or '').strip().lower().replace('\u00a0',' ')
    msg = re.sub(r'^harga\s*(?:(?:per|untuk)\s+)?(?:\d+\s*'+_UNITS+r'\s+)?', '', msg)
    msg = re.sub(r'^rp\.?\s*', '', msg).strip(' .')
    m = re.fullmatch(r'(\d[\d.,]*)(?:\s*)(juta|jt|ribu|rb)?', msg)
    if not m:
        return None
    raw, unit = m.groups()
    if unit:
        try:
            # Indonesian decimal: 1,5 juta = 1_500_000.
            # A dot followed by exactly three digits is a thousands grouping.
            clean = raw.replace('.', '').replace(',', '.') if re.match(r'^\d{1,3}(?:\.\d{3})+(?:,\d+)?$', raw) else raw.replace(',', '.')
            number = Decimal(clean)
        except InvalidOperation:
            return None
        result = int(number * (1000000 if unit in ('jt','juta') else 1000))
    else:
        try:
            result = int(raw.replace('.', '').replace(',', ''))
        except ValueError:
            return None
    return result if 0 < result <= 10**12 else None


def _clean_tail(raw: str) -> str:
    raw = raw.strip(" \t\n,:;-")
    # Treat a five-digit postal code as the end of the address, if present.
    post = re.search(r"(?<!\d)\d{5}(?!\d)", raw)
    if post:
        raw = raw[:post.end()]
    else:
        boundary = _BOUNDARY.search(raw)
        if boundary:
            raw = raw[:boundary.start()]
    return raw.strip(" \t\n,:;-").rstrip(".")[:500]


def customer_address(message: str) -> str | None:
    """Extract an explicitly requested recipient address, not business item notes.

    Supports 'alamat H8QV+MHJ, Jl...', 'alamat di bawah PT SGB. Jl...', and
    'tambahkan alamat ini: Jl ...'. Avoids addresses unrelated to documents
    unless the caller already established a document context.
    """
    msg = (message or "").replace("\u00a0", " ").strip()
    match = _ADDR_KEYWORD.search(msg)
    if not match:
        return None
    rest = msg[match.end():].lstrip(" \t\n:=-")
    road = _ADDR_START.search(rest)
    if not road:
        # 'Jl. Raya ..., Purbalingga 53371 tambahkan alamat ini' is valid.
        # The address precedes the instruction rather than following it.
        if re.search(r'(?i)\b(?:tambah(?:kan)?|masuk(?:kan)?|cantumkan)\s+alamat\b', msg):
            rest = msg[:match.start()]
            road = _ADDR_START.search(rest)
        if not road:
            return None
    raw = rest[road.start():]
    # Preserve optional Plus Code directly preceding the road name.
    plus = re.search(r"\b[A-Z0-9]{4}\+[A-Z0-9]{2,4}\b\s*,?\s*$", rest[:road.start()], re.I)
    if plus:
        raw = rest[plus.start():]
    value = _clean_tail(raw)
    # Do not treat a bare road keyword with no specific detail as a postal address.
    return value if len(value) >= 15 else None


def requested_item_note(message: str) -> str | None:
    """Read explicit 'keterangan selesai service' without stealing addresses."""
    text = (message or "").replace("\u00a0", " ").strip()
    m = _NOTE.search(text)
    if not m:
        return None
    note = m.group(1).strip()
    note = re.split(r'(?i)\s+(?:dan\s+)?(?:syarat|ketentuan|garansi|pembayaran|dp|waktu\s+pengerjaan)\b', note, maxsplit=1)[0]
    note = note.strip(".,:; ")[:400]
    # Never map a receiver address to an item note.
    if _ADDR_START.search(note) or re.search(r"\b(?:alamat|kode pos)\b", note, re.I):
        return None
    # 'keterangan dan ketentuan' is a document label, not an item note.
    if re.match(r"(?i)^(?:dan\s+ketentuan|ketentuan)\b", note):
        return None
    return note or None


def explicit_service(message: str) -> bool:
    return bool(re.search(r"\b(?:biaya\s+)?(?:service|servis|perbaikan)\b", message or "", re.I))


def scrub_address_from_items(items: Any, address: str | None) -> None:
    """Remove only demonstrably misclassified address fragments from item notes."""
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('note'), str):
            continue
        note = item['note'].strip()
        if address and address in note:
            note = note.replace(address, '').strip(' ;,.-')
        if re.match(r"(?is)^\s*alamat\s*[:=]", note):
            note = ''
        if _ADDR_START.search(note) and (not address or len(note) > 25):
            # Only discard if it appears to be an address, not a product name.
            if re.search(r"\b(?:kab(?:upaten)?|kec(?:amatan)?|jawa|\d{5})\b", note, re.I):
                note = ''
        item['note'] = note


# Document identifiers are different business fields, never aliases.
_PO_LABEL = r'(?:nomor\s+|no\.?\s+)?(?:po(?:\s+(?:customer|pelanggan))?|purchase\s+order(?:\s+customer)?)'
_INV_LABEL = r'(?:nomor|no\.?)\s+(?:invoice|faktur)'
_ID_VALUE = r'([A-Za-z0-9][A-Za-z0-9/_.-]{0,79})(?![A-Za-z0-9/_.-])'
_ID_SEP = r'\s*(?:[:=]\s*|(?:jadi|menjadi|adalah|ke)\s+|\s+)'


def _explicit_id(message: str, label: str) -> str | None:
    # Require a digit to avoid treating ordinary prose as an identifier.
    matches = re.finditer(r'(?i)\b' + label + _ID_SEP + _ID_VALUE, message or '')
    values = [m.group(1).rstrip('.') for m in matches
              if any(c.isdigit() for c in m.group(1))
              and not re.search(r'(?i)\b(?:tgl\.?|tanggal)\s+$', (message or '')[:m.start()])]
    return values[0] if len(set(values)) == 1 else None


def invoice_header_patch(message: str, old_draft: dict | None = None) -> dict:
    po = _explicit_id(message, _PO_LABEL)
    number = _explicit_id(message, _INV_LABEL)
    fields = {}
    if po:
        fields['po_number'] = po
        # Repair an active draft where this exact PO was placed in NO.
        if (old_draft or {}).get('number') == po and not number:
            fields['number'] = ''
    if number:
        fields['number'] = number
    elif re.search(r'(?i)\b' + _INV_LABEL + r'\s*(?:[:=]\s*)?(?:jadi\s+|menjadi\s+)?otomatis\b', message):
        fields['number'] = ''
    return fields


def invoice_header_only(message: str, old_draft: dict) -> dict | None:
    # Bypass the model for a simple, unambiguous header correction only.
    text = re.sub(r'^\s*@[-_\w]+\s+', '', message or '').strip()
    if re.fullmatch(r'(?i)(?:(?:tolong|koreksi|ganti|ubah|isi|masukkan|tambahkan|ralat|set)\s+)*'
                    + r'(?:' + _PO_LABEL + '|' + _INV_LABEL + ')' + _ID_SEP
                    + r'(?:' + _ID_VALUE + r'|otomatis)\s*[.!]?', text):
        return invoice_header_patch(text, old_draft) or None
    return None


def _company_and_pic(message: str) -> dict:
    # Limit parsing to the header, never use a company name in item notes.
    head = re.split(r'(?i)\balamat\b|\b\d+\s*(?:unit|pcs|buah)\b|\b(?:harga|seharga|rincian|biaya)\b', message, maxsplit=1)[0]
    company = re.search(r'(?i)\b(PT\.?\s+[\w][\w .&-]{1,90}?)(?=\s+(?:kepada|untuk|pic|attention|attn|dengan|nomor|no\.?\s|po\b)|[,;\n]|$)', head)
    pic = re.search(r'(?i)\b(mr|mrs|ms)\.?\s*([\w-]+(?:\s+[\w-]+){0,2}?)(?=\s+(?:di\s+)?PT\.?\s|\s+(?:pelanggan|customer|dengan|nomor|po)\b|[,;\n]|$)', head)
    fields = {}
    if company:
        fields['customer'] = company.group(1).strip(' .,')
    if pic:
        fields['attention'] = pic.group(1).title() + '. ' + pic.group(2).strip()
    return fields


def _guard_invoice_header(message: str, data: dict, old_draft: dict | None) -> None:
    explicit = invoice_header_patch(message, old_draft)
    # No model-generated internal serial or PO without explicit evidence.
    data.pop('number', None)
    data.pop('po_number', None)
    data.update(explicit)
    # Override NLU only when both recipient and company are explicit.
    recipient = _company_and_pic(message)
    if len(recipient) == 2:
        data.update(recipient)


def improve_document_nlu(message: str, parsed: dict, old_draft: dict | None) -> dict:
    """Enforce explicit customer address, service and note with conservative edits.

    No arbitrary new items, amounts or payment terms are introduced. Must be
    called after model interpretation and prior to Engine's document dispatch.
    """
    if not isinstance(parsed, dict):
        return parsed
    action = parsed.get('action')
    if action not in ('document_create', 'document_update'):
        return parsed
    address = customer_address(message)
    note = requested_item_note(message)
    new_doc = is_new_document_request(message)
    terms_explicit = bool(re.search(r'\b(?:ketentuan|syarat|pembayaran|dp|garansi|masa\s+berlaku|tempo)\b', message, re.I))
    data = parsed.setdefault('data', {})
    if not isinstance(data, dict):
        data = {}
        parsed['data'] = data
    if action == 'document_create':
        if data.get('doc_type') == 'invoice':
            _guard_invoice_header(message, data, None)
        if not terms_explicit:
            data.pop('terms', None)  # reject unrequested LLM-invented business terms
        if address:
            data['customer_address'] = address
        items = data.get('items') or []
        scrub_address_from_items(items, address)
        if isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict):
            item = items[0]
            if explicit_service(message) and not re.search(r"\b(?:service|servis|perbaikan)\b", str(item.get('name') or ''), re.I):
                item['name'] = 'service ' + str(item.get('name') or '').strip()
            if note:
                item['note'] = note
        return parsed

    patch = data.setdefault('patch', {})
    if not isinstance(patch, dict):
        patch = {}
        data['patch'] = patch
    if (old_draft or {}).get('type') == 'invoice':
        _guard_invoice_header(message, patch, old_draft)
    if not terms_explicit:
        patch.pop('terms', None)
        patch.pop('terms_add', None)
    if address:
        patch['customer_address'] = address
    # The model sometimes mistakes an address-only instruction for an item add.
    if address and not new_doc and not re.search(r"\b(?:\d+\s*" + _UNITS + r"|harga\s+(?:rp)?\s*\d+)\b", message, re.I):
        if 'items' in patch:
            patch['items'] = []
        if 'item_changes' in patch and isinstance(patch['item_changes'], dict):
            patch['item_changes'].pop('note', None)
            if not patch['item_changes']:
                patch.pop('item_changes', None)
    items = patch.get('items')
    scrub_address_from_items(items, address)
    existing = old_draft.get('items') or [] if isinstance(old_draft, dict) else []
    explicit_add = bool(re.search(r'(?i)\b(?:tambah(?:kan)?|tambahi|add|baris\s+baru|item\s+baru)\b', message))
    # When only ONE item is present, a normal correction must UPDATE it, not
    # append an additional row and silently double the total.
    if (isinstance(items, list) and len(items) == 1 and isinstance(items[0], dict)
            and len(existing) == 1 and not (old_draft or {}).get('pending_item')
            and not explicit_add and patch.get('item_mode') != 'replace'):
        changes = {k:v for k,v in items[0].items()
                   if k in ('name', 'qty', 'price', 'note', 'unit') and v not in (None, '')}
        patch.pop('items', None)
        if changes:
            patch['target_index'] = 1
            patch.setdefault('item_changes', {}).update(changes)
        items = None
    if note:
        if old_draft and len(old_draft.get('items') or []) == 1 and not old_draft.get('pending_item'):
            patch.pop('items', None) if items and all(not any(k in x for k in ('name', 'qty', 'price')) for x in items if isinstance(x, dict)) else None
            patch.setdefault('target_index', 1)
            patch.setdefault('item_changes', {})['note'] = note
        elif old_draft and old_draft.get('pending_item'):
            patch.setdefault('items', []).append({'note': note})
    # Avoid confusing single-field address edits with creating a second item.
    if patch.get('items') == []:
        patch.pop('items', None)
    return parsed


def fallback_simple_document(message: str) -> dict | None:
    """Conservative offline fallback for ONE-item offer/invoice requests.

    Returns the existing model's action/data schema only for requests with
    customer, item, qty, and price all explicitly present; otherwise None.
    Does not infer payment schedules, warranties, or any other commercial terms.
    """
    if not is_new_document_request(message):
        return None
    msg = re.sub(r'^\s*@[-_\w]+\s+', '', (message or '').replace('\u00a0', ' ')).strip()
    dtype = 'invoice' if re.search(r'(?i)\b(?:invoice|faktur)\b', msg[:55]) else 'offer'
    # Company name stops before address or before first work-item instruction.
    company = re.search(
        r'(?i)\b(PT\.?\s+[\w][\w .&-]{1,90}?)\s*'
        r'(?=(?:,?\s+(?:alamat|kepada|dengan|rincian|biaya|service|servis|\d+\s*unit)\b)|$)', msg)
    name = company.group(1).strip(' .,') if company else ''
    if not name:
        return None
    recipient = re.search(r'(?i)\b(?:kepada\s+)?(?:pak|bapak|bu|ibu)\s+([\w.-]{2,60})\b', msg)
    attention = ('Pak ' + recipient.group(1).strip(' .,') if recipient and re.search(r'(?i)\b(?:pak|bapak)\s+', recipient.group(0)) else
                 'Ibu ' + recipient.group(1).strip(' .,') if recipient else '')
    # Extract only the first line item; multi-item cases should use the LLM.
    item = re.search(r'(?i)\b(?:(biaya\s+)?(service|servis|perbaikan)\s+)?'
                     r'(\d{1,5})\s*(?:unit|unut|unot|pcs|buah)\s+'
                     r'(.+?)\s+(?:se)?harga\s+(?:rp\.?\s*)?(\d[\d.,]*\s*(?:juta|jt|ribu|rb)?)\b', msg)
    if not item:
        return None
    # Only a clearly single line item can bypass an unreliable LLM.
    if len(re.findall(r'(?i)\b(?:se)?harga\b', msg)) != 1:
        return None
    qty = int(item.group(3))
    price = single_price_reply('harga ' + item.group(5))
    desc = item.group(4).strip(' ,.:;')
    # No ambiguous multi-item requests: never accidentally omit a second item.
    if re.search(r'(?i)\b(?:dan\s+\d+\s*(?:unit|pcs)|ditambah\s+\d+\s*(?:unit|pcs))\b', msg[item.end():]):
        return None
    if not (1 <= qty <= 10000 and price and len(desc) >= 3):
        return None
    if item.group(2):
        desc = 'service ' + desc
    result = {'action':'document_create','data':{
        'doc_type':dtype, 'customer':name,
        'attention':attention,'items':[{'name':desc,'qty':qty,'unit':'UNIT','price':price}]
    }}
    addr = customer_address(msg)
    if addr:
        result['data']['customer_address'] = addr
    note = requested_item_note(msg)
    if note:
        result['data']['items'][0]['note'] = note
    if dtype == 'invoice':
        _guard_invoice_header(msg, result['data'], None)
    return result
