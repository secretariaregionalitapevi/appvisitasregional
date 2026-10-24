"""Painel impresso de participação por origem, com comparação entre os mesmos recortes."""
from collections import Counter
from datetime import date
from reportlab.lib import colors
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle
from .music_events_conductors import attendance_status


def dashboard(data, width):
    comparison = data.get('comparison') or {}
    current = comparison.get('current')
    if not current or not current['commons']:
        rows = data.get('rows', [])
        states = Counter(attendance_status(row) for row in data.get('conductors', {}).get('rows', []))
        origins = data.get('municipalities') or rows
        represented = sum(bool(row.get('MUSICO') or row.get('ORGANISTA') or attendance_status(row) == 'PRESENTE') for row in rows)
        current = {'date': str(next(iter(data.get('events', [])), {}).get('data_evento') or '')[:10],
                   'musicians': sum(row.get('MUSICO', 0) for row in origins),
                   'organists': sum(row.get('ORGANISTA', 0) for row in origins),
                   'leaders': states['PRESENTE'], 'total': sum(row.get('total', row.get('MUSICO', 0) + row.get('ORGANISTA', 0)) for row in origins),
                   'commons': len(rows), 'represented': represented, 'without_participation': len(rows) - represented, 'states': dict(states)}
        comparison = {'current': current, 'previous': None, 'series': [current]}
    previous = comparison.get('previous')
    d = Drawing(width, 410)
    navy, muted, border = '#1E4B7A', '#62788A', '#DAE4EC'

    def text(x, y, value, size=9, color=navy, bold=False, anchor='start'):
        d.add(String(x, y, str(value).upper(), fontName='Helvetica-Bold' if bold else 'Helvetica',
                     fontSize=size, fillColor=colors.HexColor(color), textAnchor=anchor))

    def box(x, y, w, h, fill='#FFFFFF', stroke=border, radius=7):
        d.add(Rect(x, y, w, h, rx=radius, ry=radius, fillColor=colors.HexColor(fill),
                   strokeColor=colors.HexColor(stroke) if stroke else None, strokeWidth=.6))

    def number(value):
        return f'{value:,}'.replace(',', '.')

    def day(value, short=False):
        try:
            return date.fromisoformat(value).strftime('%d/%m' if short else '%d/%m/%Y')
        except ValueError:
            return 'PERÍODO SELECIONADO'

    def variation(key):
        if not previous:
            return 'SEM COMPARAÇÃO ANTERIOR', muted
        change = current[key] - previous[key]
        if not previous[key]:
            return ('SEM ALTERAÇÃO' if not change else f'+{number(change)} NOVOS REGISTROS'), muted
        percent = f'{change / previous[key] * 100:+.1f}%'.replace('.', ',')
        return f'{percent} | ANTERIOR: {number(previous[key])}', '#20846C' if change > 0 else '#B75163' if change < 0 else muted

    cities = data.get('filters', {}).get('municipios', [])
    scope = ' / '.join(cities) if cities else 'MUNICÍPIOS SELECIONADOS'
    text(0, 394, 'PAINEL DE PARTICIPAÇÃO', 15, bold=True)
    text(0, 378, f'COMUNS DE ORIGEM: {scope}', 8, muted)
    text(width, 394, f'ATUAL: {day(current["date"])}', 9, bold=True, anchor='end')
    text(width, 378, f'ANTERIOR: {day(previous["date"])} | MESMAS COMUNS' if previous else 'PRIMEIRO ENSAIO DISPONÍVEL NO ANO',
         8, muted, anchor='end')

    metrics = [('MÚSICOS' + (f' DE {cities[0]}' if len(cities) == 1 else ''), 'musicians', '#2F80CF'),
               ('ORGANISTAS', 'organists', '#CB5685'), ('ENCARREGADOS PRESENTES', 'leaders', '#159981'),
               ('PARTICIPANTES DAS COMUNS', 'total', navy)]
    card_width = (width - 36) / 4
    for index, (label, key, color) in enumerate(metrics):
        x = index * (card_width + 12)
        box(x, 287, card_width, 77, '#F6F9FC')
        d.add(Rect(x + 12, 344, 3, 10, fillColor=colors.HexColor(color), strokeColor=None))
        text(x + 21, 346, label, 8, muted, True)
        text(x + 12, 316, number(current[key]), 26, color, True)
        delta, delta_color = variation(key)
        text(x + 12, 298, delta, 7.5, delta_color)

    left_width = width * .57
    box(0, 105, left_width, 167)
    right_x, right_width = left_width + 14, width - left_width - 14
    box(right_x, 105, right_width, 167)
    text(14, 254, 'COMPARATIVO COM O ENSAIO ANTERIOR', 9, bold=True)
    for label, key, color, y in [('MÚSICOS', 'musicians', '#2F80CF', 231), ('ORGANISTAS', 'organists', '#CB5685', 168)]:
        text(14, y, label, 8, bold=True)
        maximum = max(current[key], previous[key] if previous else 0, 1)
        bar_x, bar_width = 76, left_width - 130
        for offset, point, fill in [(20, current, color), (39, previous, '#B9CBDC')]:
            if point is None:
                text(14, y - offset + 2, 'SEM ENSAIO ANTERIOR DISPONÍVEL', 7, muted)
                continue
            text(14, y - offset + 2, day(point['date'], True), 8, muted)
            box(bar_x, y - offset, bar_width, 10, '#EEF3F7', None, 3)
            amount = point[key] / maximum * bar_width
            if amount:
                box(bar_x, y - offset, max(2, amount), 10, fill, None, 3)
            text(bar_x + amount + 6, y - offset + 1, number(point[key]), 9, color if point is current else muted, True)

    text(right_x + 14, 254, 'PRESENÇA ENCARREGADOS', 9, bold=True)
    statuses = [('PRESENTE', 'PRESENTE', '#159981'), ('JUSTIFICOU', 'JUSTIFICOU', '#65AA67'),
                ('NAO_JUSTIFICOU', 'NJ - NÃO JUSTIFICOU', '#CD6476'),
                ('SEM_ENCARREGADO', 'SEM ENCARREGADO', '#85A4DC'), ('ENFERMO', 'ENFERMO', '#D69743')]
    for index, (status, label, color) in enumerate(statuses):
        y = 231 - index * 26
        count = current['states'].get(status, 0)
        text(right_x + 14, y, label, 8, color, True)
        text(width - 14, y, f'{count} / {current["commons"]}', 8, color, True, 'end')
        box(right_x + 14, y - 9, right_width - 28, 4, '#EEF3F7', None, 2)
        if count and current['commons']:
            box(right_x + 14, y - 9, (right_width - 28) * count / current['commons'], 4, color, None, 2)

    box(0, 12, width, 78, '#F6F9FC')
    third = width / 3
    for x in [third, 2 * third]:
        d.add(Line(x, 24, x, 78, strokeColor=colors.HexColor(border), strokeWidth=.6))
    text(14, 73, 'COMUNS REPRESENTADAS', 8, muted, True)
    text(14, 45, f'{current["represented"]} / {current["commons"]}', 23, '#159981', True)
    text(14, 26, 'POR MÚSICOS, ORGANISTAS OU ENCARREGADO', 6.8, muted)
    text(third + 14, 73, 'SEM OS TRÊS PÚBLICOS', 8, muted, True)
    text(third + 14, 45, current['without_participation'], 23, '#B67D35' if current['without_participation'] else '#159981', True)
    text(third + 14, 26, 'COMUNS NO ENSAIO SELECIONADO', 7, muted)
    text(2 * third + 14, 73, 'EVOLUÇÃO DO PÚBLICO DO RECORTE', 8, muted, True)
    points = comparison.get('series', [current])[-4:]
    totals = [p['total'] for p in points]
    low, high = min(totals or [0]), max(totals or [1])
    coordinates = []
    for index, point in enumerate(points):
        x = 2 * third + 30 + index * (third - 60) / max(1, len(points) - 1)
        y = 37 + (point['total'] - low) / max(1, high - low) * 16
        coordinates.append((x, y))
        if len(coordinates) > 1:
            px, py = coordinates[-2]
            d.add(Line(px, py, x, y, strokeColor=colors.HexColor('#AFC7DC'), strokeWidth=2))
        d.add(Circle(x, y, 3, fillColor=colors.HexColor(navy), strokeColor=None))
        text(x, y + 7, number(point['total']), 7, navy, True, 'middle')
        text(x, 22, day(point['date'], True), 7, muted, anchor='middle')
    return d
