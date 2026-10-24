"""Grade do PDF fornecido pela Secretaria, com acompanhamento anual por município."""
import io
import re
from collections import Counter, defaultdict
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

from django.http import HttpResponse
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle, Paragraph,
                               Spacer, PageBreak, Image, Flowable)
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Circle
from .music_events_identity import normalized_city
from .music_events_import import norm
from .music_events_closing import closing_for
from .music_events_conductors import attendance_status, attendance_label

WIDTH, HEIGHT = landscape(A4)
USEFUL = WIDTH - 56
CITY_COLORS = {'CAUCAIA DO ALTO': '#FFE699', 'COTIA': '#BDD7EE',
               'VARGEM GRANDE PAULISTA': '#D9E6AE', 'ITAPEVI': '#BFE3DA',
               'JANDIRA': '#DDD0EA', 'PIRAPORA DO BOM JESUS': '#F4C7A8',
               'SANTANA DE PARNAÍBA': '#F6D8E2'}
STATUS = {'PRESENTE': 'PRESENTE', 'JUSTIFICOU': 'JUSTIFICOU', 'NAO_JUSTIFICOU': 'NJ',
          'SEM_ENCARREGADO': 'SE', 'ENFERMO': 'EF', 'NAO_INFORMADO': 'NÃO INFORMADO'}
STYLE = ParagraphStyle('model', fontName='Helvetica', fontSize=9, leading=10)
CENTER = ParagraphStyle('model-center', parent=STYLE, alignment=1)
BOLD = ParagraphStyle('model-bold', parent=CENTER, fontName='Helvetica-Bold')


def para(text, style=STYLE):
    return Paragraph(escape(str(text if text is not None else '—').upper()).replace('\n', '<br/>'), style)


def date_label(value):
    return datetime.strptime(str(value)[:10], '%Y-%m-%d').strftime('%d/%m/%Y')


def common_name(value):
    return re.sub(r'^BR-\d+-\d+\s*-\s*', '', value, flags=re.I)


def leader_on_list(row):
    return attendance_status(row) == 'PRESENTE'


def leader_text(row, locations=()):
    return {'PRESENTE': 'PRESENTE', 'JUSTIFICOU': 'J', 'NAO_JUSTIFICOU': 'NJ',
            'SEM_ENCARREGADO': 'SE', 'ENFERMO': 'EF'}[attendance_status(row)]


def presence_legend():
    text = Paragraph('<font color="#008000"><b>J - JUSTIFICOU</b></font> &nbsp; '
                     '<font color="#E00000"><b>NJ - NÃO JUSTIFICOU</b></font> &nbsp; '
                     '<font color="#85A4DC"><b>SE - SEM ENCARREGADO</b></font> &nbsp; '
                     '<font color="#C65B00"><b>EF - ENFERMO</b></font>',
                     ParagraphStyle('presence-legend', parent=CENTER, fontSize=8, leading=11))
    table = Table([[para('LEGENDA', BOLD), text]], colWidths=[sum(model_widths()[:3]), sum(model_widths()[3:])])
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#D9D9D9')),
                               ('GRID', (0, 0), (-1, -1), .4, colors.HexColor('#89949D')),
                               ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                               ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]))
    return table


def scoped_report(data):
    """Última barreira do PDF: nenhuma comum fora do município de origem escolhido."""
    selected = {normalized_city(city) for city in data.get('filters', {}).get('municipios', [])}
    rows = [row for row in data.get('rows', []) if not selected or normalized_city(row['municipio']) in selected]
    result = {**data, 'rows': rows}
    keys = {row.get('key') or row['comum'].split(' - ', 1)[0] for row in rows}
    if selected:
        result['conductors'] = {**data.get('conductors', {}), 'rows': [row for row in data.get('conductors', {}).get('rows', [])
            if normalized_city(row.get('municipio')) in selected or row.get('comum_chave') in keys]}
        if len(rows) != len(data.get('rows', [])):
            # Agregados sem origem nominal não podem sobreviver a um recorte aplicado aqui.
            result.update(instruments={}, roles={}, musician_families={})
    if data.get('municipalities'):
        result['municipalities'] = [row for row in data['municipalities'] if not selected or normalized_city(row['municipio']) in selected]
    else:
        municipalities = {}
        for row in rows:
            group = municipalities.setdefault(row['municipio'], {'municipio': row['municipio'], 'MUSICO': 0, 'ORGANISTA': 0, 'total': 0})
            group['MUSICO'] += row.get('MUSICO', 0); group['ORGANISTA'] += row.get('ORGANISTA', 0)
            group['total'] += row.get('total', sum(row.get(category, 0) for category in ['MUSICO', 'ORGANISTA', 'IRMANDADE', 'APOIO', 'MINISTERIO']))
        result['municipalities'] = list(municipalities.values())
    return result


def administrative_closing(data, date, place):
    origins = data.get('municipalities', [])
    origin_total = sum(row.get('total', 0) for row in origins)
    closing = closing_for(data)
    musicians = closing['musicians'] if closing else sum(row.get('MUSICO', 0) for row in origins)
    organists = closing['organists'] if closing else sum(row.get('ORGANISTA', 0) for row in origins)
    total = closing['total'] if closing else origin_total
    source = closing if closing else data
    conductor_count = sum(row['situacao'] == 'PRESENTE' for row in data.get('conductors', {}).get('rows', []))
    navy, pale = colors.HexColor('#1E4B7A'), colors.HexColor('#EAF2F8')
    heading = Paragraph('FECHAMENTO DO ENSAIO REGIONAL', ParagraphStyle('closing-title', parent=BOLD, fontSize=15, leading=19, textColor=navy))
    context = para(f'{place} | {date} | ' + ('PÚBLICO DO LOCAL - TODAS AS ORIGENS' if closing else 'RECORTE DAS COMUNS DE ORIGEM'), CENTER)
    cards = Table([[para(label, BOLD) for label in ['Músicos', 'Organistas', 'Total musical', 'TOTAL GERAL DO LOCAL' if closing else 'PÚBLICO DAS COMUNS']],
                   [para(value, ParagraphStyle('closing-value', parent=BOLD, fontSize=19, leading=25, textColor=navy))
                    for value in [musicians, organists, musicians + organists, total]]], colWidths=[USEFUL / 4] * 4)
    cards.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), pale),
        ('BOX', (0, 0), (-1, -1), .5, colors.HexColor('#D8DEE5')),
        ('INNERGRID', (0, 0), (-1, -1), .35, colors.white),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
    head_style = ParagraphStyle('closing-head', parent=BOLD, textColor=colors.white, fontSize=8, leading=10)
    cell_style = ParagraphStyle('closing-cell', parent=STYLE, fontSize=9, leading=11)
    def section(title, entries, width):
        body = [[para(title, head_style), para('Quantidade', head_style)]]
        body += [[para(label, cell_style), para(value, CENTER)] for label, value in entries]
        if len(body) == 1:body.append([para('Não informado', cell_style), para('—', CENTER)])
        table = Table(body, colWidths=[width - 78, 78])
        table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), navy),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F4F6F8')]),
            ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#D8DEE5')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2), ('BOTTOMPADDING', (0, 0), (-1, -1), 2)]))
        return table
    instruments = source.get('instruments', {})
    roles = sorted((name, count) for name, count in source.get('roles', {}).items()
                   if name.upper() not in {'MÚSICO', 'MUSICO', 'MUSICISTA', 'ORGANISTA', 'IRMANDADE', 'APOIO'})
    if closing and closing.get('declared'):
        roles = list(closing['roles'].items())
    instrument_table, family_entries = instrument_family_table(instruments, organists, 300)
    family_entries += list(source.get('support', {}).items()) if closing else [('Encarregados locais presentes', conductor_count), ('Demais participantes', total - musicians - organists)]
    columns = Table([[instrument_table, section('Ministério e cargos', roles, 240),
                      section('COMPOSIÇÃO DO LOCAL' if closing else 'COMPOSIÇÃO DAS COMUNS', family_entries, USEFUL - 564)]], colWidths=[312, 252, USEFUL - 564])
    columns.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 10)]))
    source_note = para(f'FONTE: {closing["source_label"]}.' if closing else 'BASE: LISTA DE PRESENÇAS DO ENSAIO.',
                       ParagraphStyle('closing-note', parent=STYLE, fontSize=8, leading=10))
    return [heading, Spacer(1, 4), context, Spacer(1, 8), cards, Spacer(1, 10), columns, Spacer(1, 8), source_note]


def instrument_family_table(counts, organists, width):
    families = [('', ['ORGANISTAS', 'ACORDEON'], '#FFFFFF'),
                ('CORDAS', ['VIOLINO', 'VIOLA', 'VIOLONCELO'], '#D9D9D9'),
                ('MADEIRAS', ['FLAUTA TRANSVERSAL', 'OBOÉ', "OBOÉ D'AMORE", 'CORNE INGLÊS', 'CLARINETE', 'CLARINETE ALTO',
                              'CLARINETE BAIXO (CLARONE)', 'CLARINETE CONTRA BAIXO', 'FAGOTE', 'SAXOFONE SOPRANO (RETO)',
                              'SAXOFONE SOPRANINO', 'SAXOFONE ALTO', 'SAXOFONE TENOR', 'SAXOFONE BARÍTONO', 'SAXOFONE BAIXO'], '#F6B45E'),
                ('METAIS', ['TROMPETE', 'CORNET', 'FLUGELHORN', 'TROMPA', 'TROMBONE', 'TROMBONITO', 'BARÍTONO (PISTO)', 'EUFÔNIO', 'TUBA'], '#E7CB55')]
    aliases = {'FLAUTA': 'FLAUTA TRANSVERSAL', 'ORGAO': 'ORGANISTAS', 'ORGANISTA': 'ORGANISTAS', 'EUPHONIUM': 'EUFÔNIO'}
    canonical = {norm(label): label for _, labels, _ in families for label in labels}
    merged = Counter()
    for name, value in counts.items():
        name = aliases.get(norm(name), name)
        merged[canonical.get(norm(name), str(name).upper())] += value
    merged['ORGANISTAS'] = organists
    known = {label for _, labels, _ in families for label in labels}
    unknown = sorted(set(merged) - known)
    if unknown:
        families.append(('OUTROS', unknown, '#EAF2F8'))
    cell = ParagraphStyle('instrument-cell', parent=STYLE, fontSize=8.5, leading=10.5)
    number = ParagraphStyle('instrument-number', parent=cell, alignment=1)
    head = ParagraphStyle('instrument-head', parent=BOLD, fontSize=8, leading=10, textColor=colors.white)
    body = [[para('INSTRUMENTOS POR FAMÍLIA', head), '', para('QUANTIDADE', head)]]
    styles = [('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E4B7A')),
              ('SPAN', (0, 0), (1, 0)),
              ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#C8D1DA')),
              ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 1.5),
              ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5), ('LEFTPADDING', (0, 0), (-1, -1), 3), ('RIGHTPADDING', (0, 0), (-1, -1), 3)]
    totals = []
    for family, labels, color in families:
        start = len(body)
        for label in labels:
            if label in merged:
                body.append(['', para(label, cell), para(merged[label], number)])
        end = len(body) - 1
        if end < start:
            continue
        if family:
            body[start][0] = FamilyLabel(family, (end - start + 1) * 13.5)
            styles += [('SPAN', (0, start), (0, end)), ('BACKGROUND', (0, start), (0, end), colors.HexColor(color))]
            totals.append((family, sum(merged[label] for label in labels)))
    table = Table(body, colWidths=[23, width - 83, 60])
    table.setStyle(TableStyle(styles))
    return table, totals


class FamilyLabel(Flowable):
    def __init__(self, label, height):
        super().__init__()
        self.width, self.height, self.label = 15, max(height, len(label) * 4 + 2), label

    def draw(self):
        self.canv.saveState()
        self.canv.translate(self.width / 2, self.height / 2)
        self.canv.rotate(90)
        self.canv.setFont('Helvetica-Bold', 7)
        self.canv.drawCentredString(0, -2, self.label)
        self.canv.restoreState()


class CityLabel(Flowable):
    def __init__(self, city, height):
        super().__init__()
        self.width, self.height = 14, max(8, height)
        self.text = city.replace(' DO ALTO', '').replace(' DO BOM JESUS', '')
        if len(self.text) * 4.5 > self.height:
            self.text = {'VARGEM GRANDE PAULISTA': 'VGP', 'SANTANA DE PARNAÍBA': 'FAZ'}.get(city, city[:3])

    def draw(self):
        self.canv.saveState()
        self.canv.translate(self.width / 2, self.height / 2)
        self.canv.rotate(90)
        self.canv.setFont('Helvetica', 8)
        self.canv.drawCentredString(0, -3, self.text)
        self.canv.restoreState()


def model_header(place, date, actor='SECRETARIA MUSICAL', now=None, page=1):
    title = [para('CONGREGAÇÃO CRISTÃ NO BRASIL', ParagraphStyle('report-entity', parent=BOLD, fontSize=15, leading=18)),
             para('REGIONAL ITAPEVI - SÃO PAULO', CENTER),
             para('ENSAIOS REGIONAIS', ParagraphStyle('report-module', parent=BOLD, fontSize=12, leading=16, textColor=colors.HexColor('#1E4B7A'))),
             para('RELATÓRIO UNIFICADO ENSAIO REGIONAL', CENTER)]
    emitted = f'{now:%d/%m/%Y %H:%M}' if now else '—'
    meta = para(f'PÁGINA: {page}\nMUNICÍPIO: {place}\nDATA DO ENSAIO: {date}\nEMISSÃO: {emitted}\nRESPONSÁVEL: {actor}',
                ParagraphStyle('report-context', parent=STYLE, alignment=2, fontSize=7, leading=10))
    institution = Table([['', title, meta]], colWidths=[190, USEFUL - 380, 190])
    institution.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'),
                                    ('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
    return Table([[institution], [Spacer(1, 10)]], colWidths=[USEFUL],
                 style=TableStyle([('LEFTPADDING', (0, 0), (-1, -1), 0), ('RIGHTPADDING', (0, 0), (-1, -1), 0),
                                   ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))


def model_widths():
    # Proporções extraídas da grade do PDF de 16/11/2025, ocupando toda a largura útil.
    ratios = [18, 180, 133, 46, 74, 68, 64, 64, 63, 75]
    return [USEFUL * value / sum(ratios) for value in ratios]


def footer(actor, now, context, page_numbers=True):
    def draw(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 6)
        canvas.setFillColor(colors.HexColor('#526371'))
        canvas.drawString(28, 16, f'REGIONAL ITAPEVI - SÃO PAULO | {context[:65]}'.upper())
        suffix = f' | PÁGINA {doc.page}' if page_numbers else ''
        canvas.drawRightString(WIDTH - 100 if not page_numbers else WIDTH - 28, 16, f'{now:%d/%m/%Y %H:%M} | {actor[:45].upper()}{suffix}')
        canvas.restoreState()
    return draw


def legacy_grid(rows):
    headers = ['', 'Comum', 'Encarregado Local', 'Músicos', 'Organistas', 'Total Geral',
               'Músicos', 'Organistas', '% Músicos', '% Organistas']
    head = ParagraphStyle('grid-head', parent=BOLD, textColor=colors.white, fontSize=8, leading=9)
    body = [['', '', para('PRESENTES NO ENSAIO', BOLD), '', '', '', para('CADASTRO SAM - COMUM DE ORIGEM', BOLD), '', '', ''], [para(h, head) for h in headers]]
    for row in rows:
        leader = leader_text(row, [row['encarregado_local']] if row.get('encarregado_local') else ())
        color = '#008000' if leader == 'J' else '#E00000' if leader == 'NJ' else '#85A4DC' if leader == 'SE' else '#C65B00' if leader == 'EF' else '#000000'
        leader_style = ParagraphStyle('model-state', parent=BOLD, textColor=colors.HexColor(color))
        bm, bo = row.get('cadastro_musicos'), row.get('cadastro_organistas')
        m, o = row['MUSICO'], row['ORGANISTA']
        pm = row.get('model_percent_m', 100 * m / bm if bm else None)
        po = row.get('model_percent_o', 100 * o / bo if bo else None)
        body.append(['', para(common_name(row['comum'])), para(leader, leader_style),
                     para(m, CENTER), para(o, CENTER), para(m + o, BOLD), para(bm, CENTER), para(bo, CENTER),
                     para(f'{pm:.0f}%' if pm is not None else '—', CENTER),
                     para(f'{po:.0f}%' if po is not None else '—', CENTER)])
    # 12 pt no modelo. Linhas crescem se nomes extensos precisarem de quebra.
    heights = [17, 22]
    for cells in body[2:]:
        heights.append(max(17, *(cell.wrap(width - 8, 100)[1] + 6 for cell, width in zip(cells[1:], model_widths()[1:]))))
    table = Table(body, colWidths=model_widths(), rowHeights=heights, repeatRows=2)
    styles = [('SPAN', (0, 0), (1, 0)), ('SPAN', (2, 0), (5, 0)), ('SPAN', (6, 0), (9, 0)), ('BACKGROUND', (2, 0), (5, 0), colors.HexColor('#BDD7EE')), ('BACKGROUND', (6, 0), (9, 0), colors.HexColor('#C6E0B4')), ('GRID', (0, 0), (-1, -1), .3, colors.HexColor('#D8DEE5')), ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#1E4B7A')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
              ('LEFTPADDING', (0, 0), (-1, -1), 2), ('RIGHTPADDING', (0, 0), (-1, -1), 2),
              ('TOPPADDING', (0, 0), (-1, -1), 0), ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]
    for index, row in enumerate(rows, 2):
        styles.append(('BACKGROUND', (1, index), (7, index), colors.HexColor('#F4F6F8') if index % 2 else colors.white))
    start = 0
    while start < len(rows):
        end, city = start, rows[start]['municipio']
        while end + 1 < len(rows) and rows[end + 1]['municipio'] == city:
            end += 1
        table._cellvalues[start + 2][0] = CityLabel(city, sum(heights[start + 2:end + 3]) - 2)
        styles += [('SPAN', (0, start + 2), (0, end + 2)),
                   ('BACKGROUND', (0, start + 2), (0, end + 2), colors.HexColor('#EAF2F8')),
                   ('ALIGN', (0, start + 2), (0, end + 2), 'CENTER')]
        start = end + 1
    for index, row in enumerate(rows, 2):
        missing_leader = not leader_on_list(row)
        if row['MUSICO'] == 0 and row['ORGANISTA'] == 0 and missing_leader:
            styles.append(('BACKGROUND', (1, index), (-1, index), colors.HexColor('#FFF7EB')))
        for column, missing in [(2, missing_leader), (3, row['MUSICO'] == 0), (4, row['ORGANISTA'] == 0)]:
            if missing:
                styles.append(('BACKGROUND', (column, index), (column, index), colors.HexColor('#FFF4E2')))
        # Percentuais mantêm a escala verde inclusive em linhas sem participação.
        for column, category, basefield, percentfield in [
                (8, 'MUSICO', 'cadastro_musicos', 'model_percent_m'),
                (9, 'ORGANISTA', 'cadastro_organistas', 'model_percent_o')]:
            base = row.get(basefield)
            percent = row.get(percentfield, 100 * row[category] / base if base else None)
            if percent is not None:
                shade = max(0, min(1, percent / 100))
                light, dark = colors.HexColor('#F1FAF5'), colors.HexColor('#63BE96')
                fill = colors.Color(*(low + (high - low) * shade for low, high in
                                      zip((light.red, light.green, light.blue), (dark.red, dark.green, dark.blue))))
                styles.append(('BACKGROUND', (column, index), (column, index), fill))
    table.setStyle(TableStyle(styles))
    return table


def bar_chart(title, groups, series, width=USEFUL / 2 - 16, height=240):
    d = Drawing(width, height)
    plot_bottom, plot_top, left, right = 64, height - 20, 30, width - 10
    max_value = max([value for _, values in groups for value in values] or [1]) or 1
    ceiling = max(5, (int(max_value / 5) + 1) * 5)
    for tick in range(6):
        y = plot_bottom + (plot_top - plot_bottom) * tick / 5
        d.add(Line(left, y, right, y, strokeColor=colors.HexColor('#CCCCCC'), strokeWidth=.4))
        d.add(String(left - 5, y - 3, str(round(ceiling * tick / 5)), fontSize=7, textAnchor='end'))
    slot = (right - left) / max(1, len(groups))
    for index, (label, values) in enumerate(groups):
        bar_width = min(42, slot / (len(series) + 1))
        for position, value in enumerate(values):
            x = left + index * slot + (slot - bar_width * len(series)) / 2 + position * bar_width
            h = value / ceiling * (plot_top - plot_bottom)
            d.add(Rect(x, plot_bottom, bar_width - 2, h, fillColor=colors.HexColor(series[position][1]), strokeColor=None))
            d.add(String(x + (bar_width - 2) / 2, plot_bottom + h + 4, str(value), fontSize=8, textAnchor='middle'))
        label = label.upper()[:max(5, min(22, int(slot / 3.5)))]
        d.add(String(left + (index + .5) * slot, plot_bottom - 12, label, fontSize=6.5, textAnchor='middle'))
    d.add(String(width / 2, 28, title, fontName='Helvetica-Bold', fontSize=9, textAnchor='middle'))
    for i, (name, color) in enumerate(series):
        x = 10 + i * width / len(series)
        d.add(Rect(x, 8, 7, 7, fillColor=colors.HexColor(color), strokeColor=None))
        d.add(String(x + 11, 8, name.upper(), fontSize=7))
    return d


def model_summary(data):
    from .music_events_summary import dashboard
    return [dashboard(data, USEFUL)]


def build_model_pdf(data, actor='Secretaria Musical', now=None, include_summary=True, page_numbers=True, include_original=False, page_offset=0):
    data = scoped_report(data)
    now = now or datetime.now(ZoneInfo('America/Sao_Paulo'))
    stream = io.BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=14, bottomMargin=30)
    event = next(iter(data.get('events', [])), {})
    date = date_label(event['data_evento']) if event.get('data_evento') else 'Período selecionado'
    selected_cities = data.get('filters', {}).get('municipios', [])
    place = ' E '.join(selected_cities) if selected_cities else ' E '.join(dict.fromkeys(x['nome'].upper() for x in data.get('locations', []))) or 'REGIONAL ITAPEVI'
    # O formato é por encontro: consolidado de vários encontros deve usar a visão anual.
    if len({e['data_evento'] for e in data.get('events', [])}) > 1:
        date = 'PERÍODO CONSOLIDADO'
    place = place.upper()
    rows = []
    current = not data.get('base_complete') and data.get('registry', {}).get('available')
    for original in data.get('rows', []):
        row = dict(original)
        if not current:
            row['cadastro_musicos'], row['cadastro_organistas'] = row.get('musicos_base'), row.get('organistas_base')
            row['model_percent_m'], row['model_percent_o'] = row.get('percentual_musicos'), row.get('percentual_organistas')
        if row.get('encarregado_situacao') and row['encarregado_situacao'] != 'PRESENTE':
            row['encarregado'] = STATUS.get(row['encarregado_situacao'], 'NÃO INFORMADO')
        rows.append(row)
    story, chunk, height = [], [], 0
    chunks = []
    for row in rows:
        # Paginação mede a altura real; não corta nomes nem força linhas altas para fora da página.
        row_height = legacy_grid([row]).wrap(USEFUL, HEIGHT)[1] - 39
        if chunk and height + row_height > 370:
            chunks.append(chunk)
            chunk, height = [], 0
        chunk.append(row)
        height += row_height
    chunks.append(chunk)
    for index, page_rows in enumerate(chunks):
        if index:
            story.append(PageBreak())
        story.extend([model_header(place, date, actor, now, page_offset + index + 1), legacy_grid(page_rows), presence_legend()])
    if include_summary:
        story.extend([PageBreak(), model_header(place, date, actor, now, page_offset + len(chunks) + 1), *model_summary(data)])
    if include_summary and data.get('instruments'):
        story.extend([PageBreak(), *administrative_closing(data, date, place)])
    draw = footer(actor, now, date, page_numbers)
    doc.build(story, onFirstPage=draw, onLaterPages=draw)
    content = stream.getvalue()
    return content


def session_report(data, session):
    from .music_events_annual import annual_comparison
    rows, locations, conductors, pending_by_city = [], {}, [], {}
    municipalities, instruments, roles, families = {}, Counter(), Counter(), Counter()
    for row in data['rows']:
        cell = next((c for c in row['cells'] if c['date'] == session['date'] and c['loaded']), None)
        if cell is None:
            continue
        leader = leader_text(cell, cell.get('leader_valid_locations', []))
        rows.append({**row, 'MUSICO': cell['musicians'], 'ORGANISTA': cell['organists'], 'encarregado': leader,
                     'encarregado_situacao': cell['leader_status']})
        rows[-1].update(encarregado_na_lista=cell.get('leader_on_list', False), leader_attendance=cell['leader_attendance'], encarregado_local=' / '.join(cell.get('leader_valid_locations', [])))
        conductors.append({'situacao': cell['leader_status'], 'locais': cell['leader_locations'],
                           'municipio': row['municipio'], 'comum_chave': row['key'], 'consta_lista': cell.get('leader_on_list', False), 'leader_attendance': cell['leader_attendance']})
        origin = municipalities.setdefault(row['municipio'], {'municipio': row['municipio'], 'MUSICO': 0, 'ORGANISTA': 0, 'total': 0})
        origin['MUSICO'] += cell['musicians']; origin['ORGANISTA'] += cell['organists']
        origin['total'] += cell['musicians'] + cell['organists'] + cell['others']
        instruments.update(cell.get('instruments', {})); roles.update(cell.get('roles', {})); families.update(cell.get('families', {}))
        pending_by_city[row['municipio']] = max(pending_by_city.get(row['municipio'], 0), cell['unresolved'])
        for name, counts in cell['attendance_by_location'].items():
            group = locations.setdefault(name, {'nome': name, 'MUSICO': 0, 'ORGANISTA': 0, 'total': 0})
            for key in ['MUSICO', 'ORGANISTA', 'total']:
                group[key] += counts.get(key, 0)
    pending = sum(pending_by_city.values())
    note = ('Base SAM atual na emissão, todos os níveis ativos. Percentual = presentes da comum / cadastro atual. '
            'Sem base ou população zero: —. Encarregado local: PRESENTE, J, NJ, SE (sem encarregado) ou EF (enfermo).')
    if pending:
        note += f' {pending} presenças com comum não conciliada neste município/recorte; conferir antes de concluir ausência.'
    return {'events': [{'data_evento': session['date'], 'tipo': 'ENSAIO_REGIONAL'}], 'rows': rows,
            'comparison': annual_comparison(data, session['date']),
            'locations': list(locations.values()), 'conductors': {'rows': conductors}, 'base_complete': False,
            'municipalities': list(municipalities.values()), 'instruments': dict(instruments),
            'roles': dict(roles), 'musician_families': dict(families),
            'allow_original': data.get('allow_original', False),
            'physical_closings': data.get('physical_closings', []),
            'registry': data['registry'], 'filters': {'municipios': data['selected_cities']}, 'base_note': note}


def annual_matrix_pdf(data, actor, now):
    stream = io.BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=landscape(A4), leftMargin=28, rightMargin=28, topMargin=84, bottomMargin=34)
    story = []
    for city in data['selected_cities']:
        rows = [row for row in data['rows'] if row['municipio'] == city]
        dates = sorted({cell['date'] for row in rows for cell in row['cells']})
        for start in range(0, max(1, len(dates)), 3):
            if story:
                story.append(PageBreak())
            block = dates[start:start + 3]
            loaded = max((row['loaded_sessions'] for row in rows), default=0)
            context = Table([[para(f'Município de origem\n{city}', BOLD),
                              para(f'Ano de acompanhamento\n{data["year"]}', BOLD),
                              para(f'Cobertura dos registros\n{loaded} de 3 ensaios carregados', BOLD)]],
                            colWidths=[USEFUL * .4, USEFUL * .25, USEFUL * .35])
            context.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EAF2F8')),
                                         ('BOX', (0, 0), (-1, -1), .4, colors.HexColor('#D8DEE5')),
                                         ('TOPPADDING', (0, 0), (-1, -1), 8), ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
            note_style = ParagraphStyle('matrix-note', parent=STYLE, fontSize=8, leading=11, textColor=colors.HexColor('#526371'))
            story.extend([context, Spacer(1, 8),
                          para('Base de comparação: cadastro SAM atual, com Ativo, Alerta e Concluído em todos os níveis. '
                               'Percentual de músicos e de organistas: presentes da comum divididos pelo respectivo cadastro.', note_style),
                          para('Leitura do acompanhamento: encontros sem dados carregados ficam pendentes. '
                               'Encarregado local: PRESENTE, JUSTIFICOU ou NJ; local validado é informação complementar.', note_style), Spacer(1, 10)])
            if data.get('unresolved_count'):
                pending_label = '1 presença ainda sem comum conciliada' if data['unresolved_count'] == 1 else f'{data["unresolved_count"]} presenças ainda sem comum conciliada'
                story.extend([para(f'Conferência cadastral: {pending_label} no recorte. '
                                   'Conferir a origem antes de concluir ausência.', note_style), Spacer(1, 8)])
            headers = ['Comum e encarregado local', 'Cadastro SAM atual'] + [date_label(day) for day in block] + ['Participação no ano']
            head_style = ParagraphStyle('matrix-heading', parent=BOLD, textColor=colors.white)
            body = [[para(label, head_style) for label in headers]]
            missing_cells = []
            missing_rows = []
            for row in rows:
                cells = {cell['date']: cell for cell in row['cells']}
                common_code = row.get('key') or row['comum'].split(' - ', 1)[0]
                common_details = Paragraph(f'<b>{escape(common_name(row["comum"]).upper())}</b><br/>'
                                           f'<font color="#526371" size="8">CÓDIGO: {escape(common_code)}</font><br/>'
                                           '<font color="#1E4B7A" size="8"><b>ENCARREGADO LOCAL CADASTRADO</b></font><br/>'
                                           f'{escape(row["encarregado_nome"].upper())}', STYLE)
                values = ['', f'Músicos: {row.get("cadastro_musicos") if row.get("cadastro_musicos") is not None else "—"}\n'
                              f'Organistas: {row.get("cadastro_organistas") if row.get("cadastro_organistas") is not None else "—"}']
                for day in block:
                    cell = cells.get(day)
                    if not cell or not cell['loaded']:
                        values.append('Sem dados carregados')
                        continue
                    pm = f'{cell["musician_percent"]:.0f}%' if cell['musician_percent'] is not None else '—'
                    po = f'{cell["organist_percent"]:.0f}%' if cell['organist_percent'] is not None else '—'
                    enc = leader_text(cell, cell.get('leader_valid_locations', []))
                    missing_leader = not cell.get('leader_on_list', False)
                    parts = [(f'MÚSICOS: {cell["musicians"]} ({pm})', cell['musicians'] == 0),
                             (f'ORGANISTAS: {cell["organists"]} ({po})', cell['organists'] == 0),
                             (f'ENCARREGADO LOCAL: {enc}', missing_leader)]
                    lines = [f'<font backColor="#FFF4E2" color="#805B28">{escape(label.upper())}</font>' if missing else escape(label.upper())
                             for label, missing in parts]
                    if all(missing for _, missing in parts):
                        missing_cells.append((len(values), len(body)))
                    values.append(Paragraph('<br/>'.join(lines), STYLE))
                values.append(f'{row["loaded_sessions"]} de 3 ensaios carregados\nCom músicos: {row["musician_sessions"]}\nCom organistas: {row["organist_sessions"]}\nCom encarregado local: {row["leader_sessions"]}\n{row["reading"]}')
                if row['no_participation']:
                    missing_rows.append(len(body))
                body.append([common_details] + [value if isinstance(value, Paragraph) else para(value) for value in values[1:]])
            date_width = (USEFUL - 200 - 100 - 165) / max(1, len(block))
            common_width = 200 if block else USEFUL - 265
            table = Table(body, colWidths=[common_width, 100] + [date_width] * len(block) + [165], repeatRows=1)
            table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E4B7A')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F4F6F8')]),
                ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#C8D1DA')), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
            highlights = [('BACKGROUND', (column, index), (column, index), colors.HexColor('#FFF7EB'))
                          for column, index in missing_cells]
            for index in missing_rows:
                highlights.extend([('BACKGROUND', (0, index), (0, index), colors.HexColor('#FFF7EB')),
                                   ('BACKGROUND', (-1, index), (-1, index), colors.HexColor('#FFF7EB'))])
            table.setStyle(TableStyle(highlights))
            story.append(table)
    if not story:
        story.append(para('Nenhuma comum disponível para os filtros e permissões selecionados.'))
    def header(canvas, document):
        canvas.saveState()
        center = [Paragraph('CONGREGAÇÃO CRISTÃ NO BRASIL', ParagraphStyle('entity', parent=BOLD, fontSize=15, leading=17)),
                  para('Regional Itapevi - São Paulo', CENTER),
                  Paragraph('ENSAIOS REGIONAIS', ParagraphStyle('module', parent=BOLD, fontSize=12, leading=17, textColor=colors.HexColor('#1E4B7A'))),
                  para('Acompanhamento anual por comum', CENTER)]
        recorte = ', '.join(data['selected_cities']) if len(data['selected_cities']) <= 2 else 'Regional / municípios selecionados'
        meta = para(f'Página: {document.page}\nAno: {data["year"]}\nEmissão: {now:%d/%m/%Y %H:%M}\nMunicípio: {recorte}\nResponsável: {actor}',
                    ParagraphStyle('metadata', parent=STYLE, alignment=2, fontSize=8, leading=11))
        heading = Table([['', center, meta]], colWidths=[190, USEFUL - 380, 190])
        heading.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                                    ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        _, height = heading.wrap(USEFUL, 90)
        heading.drawOn(canvas, 28, HEIGHT - 10 - height)
        canvas.restoreState()
        footer(actor, now, str(data['year']), False)(canvas, document)
    doc.build(story, onFirstPage=header, onLaterPages=header)
    return stream.getvalue()


def build_annual_pdf(data, actor, now, selected_date=None):
    if selected_date and not any(session['date'] == selected_date for session in data['sessions']):
        raise ValueError('Ensaio não encontrado no ano selecionado.')
    writer = PdfWriter()
    if not selected_date:
        writer.append(PdfReader(io.BytesIO(annual_matrix_pdf(data, actor, now))))
    for session in data['sessions']:
        if selected_date and session['date'] != selected_date:
            continue
        report = session_report(data, session)
        if report['rows']:
            writer.append(PdfReader(io.BytesIO(build_model_pdf(report, actor, now, page_numbers=False, include_original=False, page_offset=len(writer.pages)))))
    if not writer.pages:
        raise ValueError('Não há presenças carregadas para esse município e ensaio.')
    # Numeração final contínua, mesmo com vários municípios e encontros no mesmo arquivo.
    for index, page in enumerate(writer.pages, 1):
        from reportlab.pdfgen.canvas import Canvas
        overlay = io.BytesIO()
        canvas = Canvas(overlay, pagesize=landscape(A4))
        canvas.setFillColor(colors.white)
        canvas.rect(WIDTH - 92, 9, 70, 12, fill=1, stroke=0)
        canvas.setFillColor(colors.HexColor('#526371'))
        canvas.setFont('Helvetica', 6)
        canvas.drawRightString(WIDTH - 28, 16, f'PÁGINA {index} DE {len(writer.pages)}')
        canvas.save()
        page.merge_page(PdfReader(io.BytesIO(overlay.getvalue())).pages[0])
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


def export_response(data, request):
    now = datetime.now(ZoneInfo('America/Sao_Paulo'))
    profile = request.session.get('user_profile') or {}
    actor = profile.get('full_name') or profile.get('nome') or profile.get('name') or profile.get('email') or 'Usuário'
    content = build_annual_pdf(data, actor, now, request.GET.get('data'))
    cities = '_'.join(data['selected_cities']) or 'Regional'
    safe = re.sub(r'[^A-Za-z0-9_-]', '_', cities)
    response = HttpResponse(content, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Ensaios_Regionais_{data["year"]}_{safe}_{now:%d-%m-%Y_%H-%M}.pdf"'
    if request.GET.get('data'):
        from .music_events_filenames import presence_filename, download_header
        response['Content-Disposition'] = download_header(presence_filename(data['selected_cities'], [request.GET['data']]))
    response['Cache-Control'] = 'private, no-store'
    return response
