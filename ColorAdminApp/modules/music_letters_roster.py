"""Relação de candidatos e recebimento físico das cartas, independente da emissão."""
import calendar
import csv
import hashlib
import io
import re
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from .music_letters_domain import common_code, MODALITIES, norm

MODES = {**MODALITIES, 'por_chance': 'Por chance'}
DELIVERY_LABELS = {'on_time': 'Entregue no prazo', 'late': 'Entregue em atraso', 'received': 'Entregue - sem prazo',
                   'unknown_date': 'Entregue - data não informada', 'pending': 'Aguardando entrega',
                   'overdue': 'Não entregue - prazo vencido', 'no_deadline': 'Aguardando - sem prazo'}


def parse_date(value, required=False):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    value = str(value or '').strip()
    if not value and not required:
        return None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    raise ValueError('Informe uma data válida (dd/mm/aaaa).')


def suggested_deadline(pre_date):
    pre_date = parse_date(pre_date, True)
    year, month = (pre_date.year, pre_date.month - 1) if pre_date.month > 1 else (pre_date.year - 1, 12)
    month_before = date(year, month, min(pre_date.day, calendar.monthrange(year, month)[1]))
    return month_before - timedelta(days=(month_before.weekday() - 4) % 7)


def is_pre_evaluation(event):
    return bool(re.search(r'\bPRE[\s-]*AVALIAC', norm(event.get('evento') or event.get('titulo'))))


def event_territory(event):
    text = norm(' '.join(str(event.get(k) or '') for k in ('municipio', 'evento', 'titulo', 'local')))
    if any(term in text for term in ('COTIA', 'CAUCAIA', 'VARGEM GRANDE', 'VGP')):
        return 'COTIA'
    if any(term in text for term in ('SANTANA', 'PIRAPORA', 'FAZENDINHA')):
        return 'SANTANA_PIRAPORA'
    if 'JANDIRA' in text:
        return 'JANDIRA'
    if 'ITAPEVI' in text:
        return 'ITAPEVI'
    return None


def event_audience(event):
    text = norm(event.get('evento') or event.get('titulo'))
    if 'ORGANISTA' in text and 'MUSICO' not in text:
        return 'organista'
    if 'MUSICO' in text and 'ORGANISTA' not in text:
        return 'musico'
    return None


def pre_evaluation_options(event, events):
    # The exam date is never substituted for a missing pre-evaluation date.
    if is_pre_evaluation(event):
        return [p for p in events if is_pre_evaluation(p) and p.get('data') == event.get('data')
                and event_territory(p) == event_territory(event) and event_audience(p) == event_audience(event)]
    territory, audience = event_territory(event), event_audience(event)
    if not territory or not audience:
        return []
    event_date = parse_date(event.get('data'), True)
    return sorted([p for p in events if is_pre_evaluation(p)
                   and event_territory(p) == territory and event_audience(p) == audience
                   and parse_date(p.get('data'), True) <= event_date],
                  key=lambda p: (p['data'], p['id']), reverse=True)


def effective_deadlines(events, saved, official_events=None):
    result, choices = {}, {}
    reference_events = events if official_events is None else official_events
    for event in events:
        options = pre_evaluation_options(event, reference_events)
        choices[event['id']] = options
        stored = saved.get(event['id'])
        confirmed = next((p for p in options if p['data'] == (stored or {}).get('pre_date')), None)
        if stored and confirmed:
            item = dict(stored)
            item.update(pre_event_id=confirmed['id'], pre_event_title=confirmed.get('evento'))
            item.update(source='manual', suggested_deadline=suggested_deadline(item['pre_date']).isoformat())
            result[event['id']] = item
        elif options:
            reference = options[0]
            result[event['id']] = {'event_id': event['id'], 'pre_date': reference['data'],
                                  'pre_event_id': reference['id'], 'pre_event_title': reference.get('evento'),
                                  'deadline': suggested_deadline(reference['data']).isoformat(),
                                  'source': 'automatic', 'version': (stored or {}).get('version', 0),
                                  'stale_reference': bool(stored)}
    return result, choices


def candidate_key(row):
    return hashlib.sha256('|'.join([str(row['event_id']), row['tipo'], row['modalidade'],
        re.sub(r'[^A-Z0-9]+', ' ', norm(row['nome'])).strip(), common_code(row['comum'])]).encode()).hexdigest()


def delivery_state(row, deadline=None, today=None):
    today = today or date.today()
    limit = parse_date((deadline or {}).get('deadline'))
    delivery = row.get('delivery') or {}
    received_on = parse_date(delivery.get('received_on'))
    if delivery.get('received'):
        return 'unknown_date' if not received_on else 'received' if not limit else 'on_time' if received_on <= limit else 'late'
    return 'no_deadline' if not limit else 'overdue' if today > limit else 'pending'


def merge_candidates(letters, registrations, deadlines, today):
    merged = {}
    for saved in registrations:
        item = dict(saved['data'])
        item.update(key=saved['candidate_key'], version=saved['version'], issued=False, letter_id=None)
        merged[item['key']] = item
    for letter in letters:
        key = candidate_key(letter)
        payload = letter.get('payload') or {}
        issued = {'nome': letter['nome'], 'comum': letter['comum'], 'municipio': letter['municipio'],
                  'tipo': letter['tipo'], 'modalidade': letter['modalidade'], 'event_id': letter['event_id'],
                  'event_snapshot': letter['event_snapshot'], 'pessoa_id': payload.get('pessoa_id'),
                  'instrumento': payload.get('instrumento') or ('ÓRGÃO' if letter['tipo'] == 'organista' else ''),
                  'tonalidade': payload.get('tonalidade') or '', 'observacao': letter.get('review_notes') or '',
                  'key': key, 'version': 0, 'delivery': {}, 'source': 'Carta emitida',
                  'activity_status': (letter.get('student_activity') or {}).get('status') if (letter.get('student_activity') or {}).get('pending') else '',
                  'activity_note': ('Situação GEM/SAM: ' + str((letter.get('student_activity') or {}).get('status')) + ' - Pendência regional') if (letter.get('student_activity') or {}).get('pending') else ''}
        existing = merged.get(key) or {}
        issued.update({k: v for k, v in existing.items() if k in ('delivery', 'version', 'source', 'observacao')})
        issued.update(issued=True, letter_id=letter['id'])
        merged[key] = issued
    for item in merged.values():
        item['delivery_status'] = delivery_state(item, deadlines.get(item['event_id']), today)
        item['delivery_label'] = DELIVERY_LABELS[item['delivery_status']]
    return sorted(merged.values(), key=lambda r: (r['event_snapshot'].get('data', ''), r['tipo'], r['modalidade'], r['comum'], r['nome']))


def delivery_summary(rows):
    counts = Counter(r.get('delivery_status') or delivery_state(r) for r in rows)
    delivered = sum(bool((r.get('delivery') or {}).get('received')) for r in rows)
    return {'total': len(rows), 'delivered': delivered, 'missing': len(rows) - delivered,
            'on_time': counts['on_time'], 'late': counts['late'], 'overdue': counts['overdue'],
            'unknown_date': counts['unknown_date'], 'no_deadline': counts['no_deadline'],
            'without_letter': sum(not r.get('issued') for r in rows)}


ALIASES = {'NOME': 'nome', 'NOME COMPLETO': 'nome', 'COMUM': 'comum', 'INSTRUMENTO': 'instrumento',
           'TONALIDADE': 'tonalidade', 'OBSERVACAO': 'observacao', 'OBSERVACOES': 'observacao',
           'TIPO': 'tipo', 'MODALIDADE': 'modalidade', 'CARTA ENTREGUE': 'received', 'ENTREGUE': 'received',
           'DATA ENTREGA': 'received_on', 'DATA DE ENTREGA': 'received_on', 'ID SAM': 'pessoa_id'}


def import_rows(content, filename):
    """Read only the first worksheet; accept exported institutional headers and plain CSV."""
    if filename.lower().endswith('.xlsx'):
        from openpyxl import load_workbook
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(f.file_size for f in archive.infolist()) > 30 * 1024 * 1024:
                    raise ValueError('Planilha descompactada excede 30 MB.')
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
            sheet = workbook.worksheets[0]
            if sheet.max_row > 1100 or sheet.max_column > 30:
                raise ValueError('Limite de 1.000 candidatos e 30 colunas por importação.')
            rows = []
            for line in sheet.iter_rows():
                if any(c.data_type == 'f' for c in line):
                    raise ValueError('Remova as fórmulas da planilha antes de importar.')
                rows.append([c.value for c in line])
            workbook.close()
        except (zipfile.BadZipFile, KeyError):
            raise ValueError('Arquivo Excel inválido.')
    elif filename.lower().endswith('.csv'):
        text = content.decode('utf-8-sig')
        dialect = csv.Sniffer().sniff(text[:5000], delimiters=',;\t')
        rows = list(csv.reader(io.StringIO(text), dialect))
    else:
        raise ValueError('Importe uma planilha .xlsx ou .csv usando o modelo disponível.')
    columns = None
    result = []
    for number, values in enumerate(rows, 1):
        mapped = {i: ALIASES[norm(v)] for i, v in enumerate(values) if norm(v) in ALIASES}
        if {'nome', 'comum'}.issubset(mapped.values()):
            columns = mapped
            continue
        if not columns or not any(values):
            continue
        item = {key: values[i] if i < len(values) else None for i, key in columns.items()}
        if not item.get('nome'):
            continue
        if not common_code(item.get('comum')):
            raise ValueError(f'Linha {number}: informe o código da comum (BR-00-0000).')
        item['source_row'] = number
        result.append(item)
    if not columns or not result or len(result) > 1000:
        raise ValueError('Informe Nome e Comum e entre 1 e 1.000 candidatos.')
    return result
