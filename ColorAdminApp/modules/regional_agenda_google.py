"""Normalização do espelho Google; nunca concede aprovação nem altera eventos Google."""
from datetime import datetime
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

TZ = ZoneInfo('America/Sao_Paulo')


def normalize_events(events, calendar_id):
    if not isinstance(events, list) or len(events) > 3000:
        raise ValueError('Envie uma leitura completa de até 3000 eventos.')
    result, seen = [], set()
    for item in events:
        if not isinstance(item, dict):
            raise ValueError('Evento inválido na leitura.')
        if item.get('status') == 'cancelled':
            continue
        identity = item.get('id')
        if not isinstance(identity, str) or not identity or len(identity) > 1024 or identity in seen:
            raise ValueError('Identificador Google ausente ou duplicado.')
        seen.add(identity)
        dates = []
        all_day = bool(item.get('start', {}).get('date'))
        for key in ('start', 'end'):
            value = item.get(key) or {}
            if all_day:
                parsed = datetime.strptime(value['date'], '%Y-%m-%d').replace(tzinfo=TZ)
            else:
                parsed = datetime.fromisoformat(value['dateTime'])
                if parsed.tzinfo is None:
                    raise ValueError('Fuso ausente no evento Google.')
            dates.append(parsed)
        if dates[1] <= dates[0]:
            raise ValueError('Intervalo Google inválido.')
        result.append({'id': str(uuid5(NAMESPACE_URL, 'agenda-google|' + calendar_id + '|' + identity)),
                       'google_event_id': identity, 'titulo': str(item.get('summary') or 'Compromisso sem título')[:180],
                       'local': str(item.get('location') or '')[:300], 'inicio': dates[0].isoformat(),
                       'fim': dates[1].isoformat(), 'dia_inteiro': all_day,
                       'disponivel': item.get('transparency') == 'transparent'})
    return result


def presentation(row):
    return {**row, 'origem': 'google', 'somente_leitura': True,
            'status': 'GOOGLE_DISPONIVEL' if row['disponivel'] else 'GOOGLE',
            'categoria': 'Compromisso do Google Calendar', 'criado_por': None,
            'criado_por_nome': 'Google Calendar', 'versao': 0, 'conflitos': [], 'conflitos_externos': []}
