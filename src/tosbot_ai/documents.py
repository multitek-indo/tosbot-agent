"""Template-accurate PDF renderer for the user's two distinct Excel examples.

The original quotation is Times New Roman and includes a handwritten signature,
workshop/footer, discount and business terms. The original invoice is Calibri-like
and has a different header, table, remittance and unsigned name-only closing.

All amounts come from validated backend data; the language model never writes PDFs.
"""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any
import re
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from .config import Settings

W, H = A4


def currency(amount: int) -> str:
    return 'Rp' + f'{int(amount):,}'.replace(',', '.')


def valid_item(item: dict) -> dict | None:
    if not isinstance(item, dict):
        return None
    name = str(item.get('name') or '').strip()[:180]
    unit = str(item.get('unit') or 'UNIT').strip().upper()[:12]
    note = str(item.get('note') or '').strip()[:400]
    try:
        qty = int(item.get('qty'))
        price = int(item.get('price'))
    except (ValueError, TypeError):
        return None
    if not name or not (1 <= qty <= 100000) or not (0 <= price <= 10**12):
        return None
    return {'name': name, 'qty': qty, 'unit': unit, 'price': price, 'note': note}


def total(draft: dict) -> int:
    subtotal = sum(int(row['qty']) * int(row['price']) for row in draft.get('items', []))
    discount = max(0, int(draft.get('discount') or 0))
    return max(0, subtotal - discount)


def date_id(dt: datetime) -> str:
    month = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni',
             'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
    return f'{dt.day} {month[dt.month - 1]} {dt.year}'


def _fonts() -> dict:
    """Use open redistribution-safe Linux serif/sans substitutes for user samples."""
    choices = {
        'serif': '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
        'serif_bold': '/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf',
        'serif_italic': '/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf',
        'sans': '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        'sans_bold': '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    }
    fallback = {
        'serif': ('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf', 'Times-Roman'),
        'serif_bold': ('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf', 'Times-Bold'),
        'serif_italic': ('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf', 'Times-Italic'),
        'sans': ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 'Helvetica'),
        'sans_bold': ('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 'Helvetica-Bold'),
    }
    out = {}
    for name, fn in choices.items():
        candidate = next((x for x in (fn, fallback[name][0]) if Path(x).is_file()), None)
        if not candidate:
            out[name] = fallback[name][1]
            continue
        registered = f'Tosbot_{name}'
        if registered not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(registered, candidate))
        out[name] = registered
    return out


def _draw(c, value: Any, x: float, top: float, font: str, size: float,
          align: str = 'left'):
    c.setFont(font, size)
    c.setFillColor(colors.black)
    text = str(value or '').replace('\n', ' ')
    if align == 'right':
        c.drawRightString(x, H - top, text)
    elif align == 'center':
        c.drawCentredString(x, H - top, text)
    else:
        c.drawString(x, H - top, text)


def _wrap(text: Any, font: str, size: float, width: float) -> list[str]:
    """Wrap paragraphs at actual PDF font metrics, including long product codes."""
    lines = []
    for raw in str(text or '').splitlines() or ['']:
        if not raw.strip():
            lines.append('')
            continue
        current = ''
        for word in raw.split():
            candidate = (current + ' ' + word).strip()
            if pdfmetrics.stringWidth(candidate, font, size) <= width:
                current = candidate
                continue
            if current:
                lines.append(current)
                current = ''
            if pdfmetrics.stringWidth(word, font, size) <= width:
                current = word
                continue
            part = ''
            for ch in word:
                if pdfmetrics.stringWidth(part + ch, font, size) > width and part:
                    lines.append(part)
                    part = ch
                else:
                    part += ch
            current = part
        lines.append(current)
    return lines or ['']


def _text_block(c, text, x, baseline_top, width, font, size, leading,
                align='left') -> float:
    lines = _wrap(text, font, size, max(5, width))
    for i, line in enumerate(lines):
        anchor = x + width if align == 'right' else (x + width / 2 if align == 'center' else x)
        _draw(c, line, anchor, baseline_top + i * leading, font, size, align)
    return len(lines) * leading


def _hline(c, x1, x2, top, weight=.55):
    c.setStrokeColor(colors.black)
    c.setLineWidth(weight)
    c.line(x1, H - top, x2, H - top)


def _vline(c, x, top1, top2, weight=.55):
    c.setStrokeColor(colors.black)
    c.setLineWidth(weight)
    c.line(x, H - top1, x, H - top2)


def _grid(c, xs, top, row_heights, weight=.5):
    bottom = top + sum(row_heights)
    for x in xs:
        _vline(c, x, top, bottom, weight)
    y = top
    _hline(c, xs[0], xs[-1], y, weight)
    for h in row_heights:
        y += h
        _hline(c, xs[0], xs[-1], y, weight)
    return bottom


def _logo(c, cfg: Settings, x, y, width, height):
    if cfg.logo_path.is_file():
        c.drawImage(ImageReader(str(cfg.logo_path)), x, H - y - height,
                    width, height, preserveAspectRatio=True, anchor='c', mask='auto')


def _company_address(cfg: Settings):
    return str(cfg.address or 'Alamat belum dikonfigurasi')


def _offer_header(c, cfg, when, fonts, continuation=False):
    serif, bold = fonts['serif'], fonts['serif_bold']
    _logo(c, cfg, 21.5, 66, 54, 45)
    label = str(cfg.name).strip()
    font_size = 21
    while pdfmetrics.stringWidth(label, bold, font_size) > 490 and font_size > 13:
        font_size -= .5
    _draw(c, label, 81, 101, bold, font_size)
    _hline(c, 21, W - 21, 114, 2.2)
    _draw(c, f'{cfg.city}, {date_id(when)}', 534, 124, serif, 8.2, 'right')
    if continuation:
        _draw(c, 'LANJUTAN PENAWARAN HARGA', W/2, 167, bold, 11, 'center')


def _offer_details(c, draft, number, cfg, when, fonts):
    serif = fonts['serif']
    _draw(c, 'No', 23, 147, serif, 8.8)
    _draw(c, ':', 57, 147, serif, 8.8)
    _draw(c, number, 63, 147, serif, 8.8)
    _draw(c, 'Perihal', 23, 160, serif, 8.8)
    _draw(c, ':', 57, 160, serif, 8.8)
    _draw(c, 'Penawaran Harga', 63, 160, serif, 8.8)
    _draw(c, 'Kepada Yth.', 23, 193, serif, 9)
    attention = str(draft.get('attention') or '').strip()
    if attention:
        _text_block(c, attention, 23, 205, 455, serif, 9, 11)
    cust_y = 217 if attention else 205
    _text_block(c, draft.get('customer') or '', 23, cust_y, 500, serif, 9, 11)
    _draw(c, 'Adapun rinciannya sebagai berikut :', 23, 260, serif, 9)


def _offer_table(c, items, first_top, fonts, start_number=1):
    serif, bold = fonts['serif'], fonts['serif_bold']
    xs = [22, 43, 199, 235, 317, 410, 572]
    _grid(c, xs, first_top, [15])
    labels = ['NO', 'NAMA BARANG', 'QTY', 'HARGA PER UNIT', 'HARGA BARANG', 'KETERANGAN']
    for i, label in enumerate(labels):
        _draw(c, label, (xs[i] + xs[i+1])/2, first_top+11, bold, 8.4, 'center')
    y = first_top+15
    for count, item in enumerate(items):
        name_lines = _wrap(item['name'], serif, 8.4, xs[2] - xs[1] - 5)
        note_lines = _wrap(item.get('note', ''), serif, 8.1, xs[6] - xs[5] - 7)
        nlines = max(len(name_lines),len(note_lines),1)
        height = max(28, 9.7 * nlines + 12)
        _grid(c, xs, y, [height])
        rowmid = y + height/2 + 3
        _draw(c, start_number + count, (xs[0]+xs[1])/2, rowmid, serif, 8.2, 'center')
        _text_block(c, '\n'.join(name_lines), xs[1]+3, y + (height-(nlines-1)*10)/2 + 3,
                    xs[2]-xs[1]-6, serif, 8.4, 10)
        _draw(c, item['qty'], (xs[2]+xs[3])/2, rowmid, serif, 8.3, 'center')
        _draw(c, f'{item["price"]:,}', xs[4]-4, rowmid, serif, 8.2, 'right')
        _draw(c, 'Rp', xs[3]+3, rowmid, serif, 8.2)
        _draw(c, f'{item["qty"] * item["price"]:,.2f}', xs[5]-4, rowmid, serif, 8.1, 'right')
        _draw(c, 'Rp', xs[4]+3, rowmid, serif, 8.1)
        _text_block(c, '\n'.join(note_lines), xs[5]+3,
                    y + (height-(len(note_lines)-1)*10)/2 + 3,
                    xs[6]-xs[5]-6, serif, 8.1, 10)
        y += height
    return y


def _offer_totals(c, y, draft, fonts):
    serif,bold = fonts['serif'],fonts['serif_bold']
    # The example contains a blank extra item row and explicit DISCOUNT and TOTAL rows.
    _grid(c, [22,43,199,235,317,410,572], y, [20])
    y += 20
    _hline(c,22,410,y)
    _vline(c,22,y,y+20); _vline(c,235,y,y+40)
    _vline(c,317,y,y+40); _vline(c,410,y,y+40)
    _hline(c,22,410,y+20);_hline(c,22,410,y+40)
    _hline(c,235,317,y+40)
    _draw(c,'DISCOUNT',231,y+14,bold,8.8,'right')
    if int(draft.get('discount') or 0):
        _draw(c,'Rp', 321,y+14,serif,8.5)
        _draw(c,f'{int(draft["discount"]):,.2f}',406,y+14,serif,8.5,'right')
    _draw(c,'TOTAL HARGA DI KURANGI DISCOUNT',231,y+34,bold,8.7,'right')
    _draw(c,'Rp',321,y+34,serif,8.7)
    _draw(c,f'{total(draft):,.2f}',406,y+34,serif,8.7,'right')
    return y+40


def _offer_terms(c, draft, cfg, fonts, y):
    serif = fonts['serif']
    _draw(c, 'Keterangan dan ketentuan:',23,y+12,serif,8.9)
    y += 25
    raw = str(draft.get('terms') or '').strip()
    if raw:
        for line in raw.splitlines():
            if line.strip():
                h = _text_block(c,line.strip(),23,y,535,serif,8.6,11)
                y += max(11,h)
    y += 15
    y += _text_block(c,'Demikian penawaran ini kami buat. Atas kerjasamanya kami ucapkan terimakasih.',
                     23,y,545,serif,8.8,11)
    return y


def _offer_sign_and_footer(c, cfg, fonts, start_top):
    serif, italic = fonts['serif'],fonts['serif_italic']
    # Position closing like the customer's A4 Excel offer, not immediately
    # below the terms (which otherwise puts the signature/footer too high).
    y = max(start_top + 16, 558)
    _draw(c,'Hormat Saya,',409,y,serif,8.8)
    sign = getattr(cfg,'offer_signature_path',Path())
    if sign and Path(sign).is_file():
        # Signature originates from original OFFER spreadsheet; not fabricated.
        c.drawImage(ImageReader(str(sign)), 409, H-(y+36), 60, 34,
                    preserveAspectRatio=True,anchor='c',mask='auto')
    _draw(c,cfg.signer,409,y+45,serif,8.9)
    fy = max(y+100, 715)
    addr=f'Workshop  :  {_company_address(cfg)}'
    fy += _text_block(c,addr,23,fy,548,italic,8.4,10)
    fy += _text_block(c,f'Tlp/WA     :  {cfg.phone}',23,fy,548,italic,8.4,10)
    fy += _text_block(c,f'email         :  {cfg.email}',23,fy,548,serif,8.4,10)
    return fy


def _offer(c, draft, number, cfg, when, fonts):
    """Page-break only if content needs it; preserve familiar first-page geometry."""
    items = draft.get('items', [])
    idx = 0
    page = 0
    while True:
        page += 1
        _offer_header(c,cfg,when,fonts,continuation=page>1)
        if page == 1:
            _offer_details(c,draft,number,cfg,when,fonts)
            y = 267
        else:
            _draw(c,'No : '+number,23,190,fonts['serif'],8.5)
            _draw(c,'Kepada Yth. '+str(draft.get('customer') or ''),23,203,fonts['serif'],8.7)
            y = 215
        # Leave sufficient room for terms and final sign/footer on last page.
        # When several items exist, continuation gets a fresh repeating header.
        available = 520 if page==1 else 650
        chunk = []
        height = 0
        while idx < len(items):
            item = items[idx]
            count = max(len(_wrap(item['name'],fonts['serif'],8.4,150)),
                        len(_wrap(item.get('note',''),fonts['serif'],8.1,154)),1)
            estimated = max(28,9.7*count+12)
            # Always include at least one row; reserve 130px for totals/terms/sign when final.
            last_and_fit = (y+15+height+estimated+170 <= 730)
            if chunk and (y+15+height+estimated > available) and not last_and_fit:
                break
            chunk.append(item);idx+=1;height+=estimated
            if y+15+height > available:
                break
        y = _offer_table(c,chunk,y,fonts,start_number=idx-len(chunk)+1)
        if idx < len(items):
            _draw(c,'Bersambung ke halaman berikutnya',23,min(y+25,760),fonts['serif_italic'],8)
            c.showPage()
            continue
        # If terms are unusually long, place totals and terms on continuation.
        raw_terms=str(draft.get('terms') or '')
        n_term_lines = sum(max(1,len(_wrap(x,fonts['serif'],8.6,535))) for x in raw_terms.splitlines() if x.strip())
        projected_footer=y+60+25+n_term_lines*11+25+125
        if projected_footer>755:
            c.showPage()
            _offer_header(c,cfg,when,fonts,continuation=True)
            _draw(c,'Ringkasan penawaran : '+number,23,192,fonts['serif'],8.5)
            y=215
        y=_offer_totals(c,y,draft,fonts)
        y=_offer_terms(c,draft,cfg,fonts,y)
        # No overlap with page bottom even if terms overflow estimated size.
        if y+165 > H-30:
            c.showPage();_offer_header(c,cfg,when,fonts,continuation=True);y=210
            _draw(c,'Hormat dan keterangan penawaran '+number,23,190,fonts['serif'],8.5)
        _offer_sign_and_footer(c,cfg,fonts,y)
        return


def _invoice_header(c,cfg,fonts,continuation=False):
    sans,bold=fonts['sans'],fonts['sans_bold']
    _logo(c,cfg,77,55,52,57)
    label=str(cfg.name).strip()
    if label.upper().startswith('PT ') and not label.upper().startswith('PT. '):
        label = 'PT. '+label[3:]
    size=19.5
    while pdfmetrics.stringWidth(label,bold,size)>420 and size>13:
        size-=.5
    _draw(c,label,134,100,bold,size)
    addr=_company_address(cfg)
    # Source invoice puts address left below the logo and phone/email right.
    lines=_wrap(addr,sans,7.7,242)
    for i,line in enumerate(lines[:4]):
        _draw(c,line,44,128+10*i,bold,7.7)
    _draw(c,'Telp/Whatsapp',375,128,bold,7.9)
    _draw(c,':',450,128,sans,8)
    _draw(c,cfg.phone,459,128,sans,8)
    _draw(c,'Email',375,141,bold,7.9)
    _draw(c,':',450,141,sans,8)
    _draw(c,cfg.email,459,141,sans,7.7)
    _draw(c,'INVOICE' if not continuation else 'INVOICE (LANJUTAN)',W/2,184,bold,15,'center')


def _invoice_details(c,draft,number,when,fonts):
    sans,bold=fonts['sans'],fonts['sans_bold']
    _draw(c,'Kepada Yth :',44,199,bold,8)
    yy=211
    if draft.get('attention'):
        yy+=_text_block(c,draft['attention'],44,yy,290,sans,8,10)
    _text_block(c,draft.get('customer') or '',44,yy,310,bold,8,10)
    fields=[
        ('NO',number),('Tanggal',date_id(when)),
        ('PO Customer',draft.get('po_number') or ''),('Mata Uang',draft.get('currency') or 'IDR'),
        ('Tgl PO',draft.get('po_date') or ''),('Type Pembayaran',draft.get('payment_type') or 'Transfer')
    ]
    y=200
    for label,value in fields:
        _draw(c,label,375,y,bold,8)
        _draw(c,':',450,y,sans,8)
        _draw(c,value,465,y,sans,8)
        y+=13


def _invoice_table(c,items,top,fonts,start_number=1):
    sans,bold=fonts['sans'],fonts['sans_bold']
    xs=[44,57,184,210,253,315,374,565]
    _grid(c,xs,top,[14],.45)
    heads=['NO','NAMA BARANG','QTY','SATUAN','HARGA/UNIT','TOTAL','KETERANGAN']
    for i,label in enumerate(heads):
        _draw(c,label,(xs[i]+xs[i+1])/2,top+10,bold,7.1,'center')
    y=top+14
    for i,item in enumerate(items):
        name_lines=_wrap(item['name'],sans,7.5,xs[2]-xs[1]-5)
        note_lines=_wrap(item.get('note',''),sans,7.5,xs[7]-xs[6]-6)
        n=max(len(name_lines),len(note_lines),1)
        height=max(21,n*10+8)
        _grid(c,xs,y,[height],.45)
        basetop=y+11
        _draw(c,start_number+i,(xs[0]+xs[1])/2,basetop,sans,7.4,'center')
        _text_block(c,'\n'.join(name_lines),xs[1]+3,basetop,xs[2]-xs[1]-6,sans,7.5,9.5)
        _draw(c,item['qty'],(xs[2]+xs[3])/2,basetop,sans,7.3,'center')
        _draw(c,item.get('unit') or 'UNIT',(xs[3]+xs[4])/2,basetop,sans,7.3,'center')
        _draw(c,currency(item['price']),xs[5]-3,basetop,sans,7.3,'right')
        _draw(c,currency(item['qty']*item['price']),xs[6]-3,basetop,sans,7.3,'right')
        _text_block(c,'\n'.join(note_lines),xs[6]+4,basetop,xs[7]-xs[6]-8,sans,7.3,9.5)
        y+=height
    return y


def _invoice_totals(c,y,draft,fonts):
    sans,bold=fonts['sans'],fonts['sans_bold']
    # Source contains a blank row before TOTAL TAGIHAN, but only for table columns.
    _grid(c,[44,57,184,210,253,315,374,565],y,[13],.45)
    y+=13
    # Totals run beneath numeric columns; note column remains empty.
    subtotal=sum(x['qty']*x['price'] for x in draft.get('items',[]))
    disc=int(draft.get('discount') or 0)
    if disc:
        _grid(c,[253,315,374],y,[13],.5)
        _draw(c,'DISCOUNT',258,y+10,bold,7.2)
        _draw(c,'- '+currency(disc),371,y+10,sans,7.2,'right')
        y+=13
    _grid(c,[253,315,374],y,[14],.5)
    _draw(c,'TOTAL TAGIHAN',256,y+10,bold,7.2)
    _draw(c,currency(max(0,subtotal-disc)),371,y+10,bold,7.2,'right')
    return y+14


def _invoice_payment(c,cfg,fonts,y):
    sans,bold=fonts['sans'],fonts['sans_bold']
    _draw(c,'Pembayaran untuk invoice ini mohon untuk di transferkan ke',44,y,bold,8)
    _draw(c,f'Nomor rekening : {cfg.bank} {cfg.account}',44,y+13,bold,8)
    _draw(c,f'Atas nama {cfg.account_name}',44,y+26,bold,8)
    _draw(c,'Hormat Kami,',455,y+42,bold,8,'center')
    # Source invoice has a *typed signatory only*, no handwritten image.
    _draw(c,f'(   {cfg.signer}   )',455,y+85,bold,8,'center')
    return y+89


def _invoice(c,draft,number,cfg,when,fonts):
    items=draft.get('items',[])
    idx=0;page=0
    while True:
        page+=1
        _invoice_header(c,cfg,fonts,continuation=page>1)
        if page==1:
            _invoice_details(c,draft,number,when,fonts)
            y=281
        else:
            _draw(c,'NO  : '+number,375,211,fonts['sans'],7.9)
            _draw(c,'Kepada Yth : '+str(draft.get('customer') or ''),44,211,fonts['sans_bold'],7.9)
            y=240
        chunk=[];height=0
        while idx<len(items):
            item=items[idx]
            lines=max(len(_wrap(item['name'],fonts['sans'],7.5,121)),
                      len(_wrap(item.get('note',''),fonts['sans'],7.5,182)),1)
            row_height=max(21,lines*10+8)
            # Keep plenty of space for bank details and signature on final page.
            if chunk and y+14+height+row_height > 690:
                break
            chunk.append(item);idx+=1;height+=row_height
            if y+14+height > 690:
                break
        y=_invoice_table(c,chunk,y,fonts,start_number=idx-len(chunk)+1)
        if idx<len(items):
            _draw(c,'Bersambung ke halaman berikutnya',44,min(y+20,747),fonts['sans'],7.5)
            c.showPage();continue
        if y+13+14+40+89 > 785:
            c.showPage();_invoice_header(c,cfg,fonts,continuation=True)
            _draw(c,'Ringkasan tagihan '+number,44,223,fonts['sans'],8)
            y=240
        y=_invoice_totals(c,y,draft,fonts)
        _invoice_payment(c,cfg,fonts,max(y+44,366))
        return


def make_pdf(draft:dict,number:str,destination:Path,config:Settings,when:datetime|None=None):
    """Render immutable, template-specific business document after user confirmation."""
    when=when or datetime.now(config.tz)
    if draft.get('type') not in ('offer','invoice'):
        raise ValueError('Jenis dokumen tidak dikenal')
    destination=Path(destination)
    destination.parent.mkdir(parents=True,exist_ok=True)
    fonts=_fonts()
    c=canvas.Canvas(str(destination),pagesize=A4,
                    pageCompression=1, invariant=1,
                    title=f"{draft['type'].upper()} {number}",author=config.name)
    if draft['type']=='offer':
        if not config.offer_signature_path.is_file():
            raise FileNotFoundError('Tanda tangan referensi penawaran tidak tersedia')
        _offer(c,draft,number,config,when,fonts)
    else:
        _invoice(c,draft,number,config,when,fonts)
    c.save()
    destination.chmod(0o600)
    return destination
