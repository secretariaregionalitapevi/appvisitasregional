"""Regras de cartas, independentes da interface e do Supabase."""
import re
from collections import Counter
from .music_exams import norm, regional_group, GROUPS, LEGACY_FIELDS

MODALITIES = {'rjm': 'RJM', 'culto': 'Culto Oficial', 'oficializacao': 'Oficialização',
              'troca_necessidade': 'Troca de instrumento · Necessidade',
              'troca_enfermidade': 'Troca de instrumento · Enfermidade'}
RESULTS = {'PENDENTE': 'Aguardando confirmação', 'APROVADO': 'Aprovado',
           'RETORNOU AO CICLO': 'Retornou ao ciclo', 'AUSENTE': 'Ausente'}
ROLES = {'anciao': 'Ancião / assistência', 'cooperador': 'Cooperador do Ofício',
         'regional': 'Encarregado regional', 'encarregado': 'Encarregado local'}

def common_code(value):
    match = re.search(r'BR-\d{2}-\d{4}', str(value or '').upper())
    return match[0] if match else ''

def ministry_workbook(workbook, source_hash):
    sheet = workbook.worksheets[0]
    result, duplicates = {}, []
    for number, row in enumerate(sheet.values, 1):
        if number == 1 or len(row) < 9:
            continue
        code = common_code(row[2])
        if not code:
            continue
        values = [str(value or '').strip() for value in row]
        # Relações fora das administrações atendidas são conservadas na fonte, sem atribuir município por suposição.
        city = norm(values[8])
        if not any(term in city for term in ('ITAPEVI', 'JANDIRA', 'COTIA', 'CAUCAIA', 'VARGEM GRANDE', 'SANTANA', 'PIRAPORA')):
            continue
        item = {'common_code': code, 'comum': values[2], 'municipio': values[8],
                'anciao': values[3], 'cooperador': values[4], 'regional': values[5],
                'encarregado': values[6], 'secretario': values[7],
                'source_file': 'RELAÇÃO_MINISTÉRIO_CARTAS', 'source_row': number, 'source_sha256': source_hash}
        if any(item[key] for key in ('anciao', 'regional', 'encarregado')) and not item['cooperador']:
            item['cooperador'] = 'Sem Cooperador do Ofício'
        if code in result:
            duplicates.append(code)
        result[code] = item
    if duplicates:
        raise ValueError('Comuns duplicadas na planilha: ' + ', '.join(sorted(set(duplicates))))
    return list(result.values())

def matches(row, filters):
    event = row.get('event_snapshot') or {}
    date = str(event.get('data') or '')[:10]
    text = norm(' '.join(str(row.get(k) or '') for k in ('nome', 'comum', 'municipio')))
    return (not filters.get('municipio') or regional_group(row.get('municipio')) == filters['municipio']) and \
        (not filters.get('comum') or norm(row.get('comum')) == norm(filters['comum'])) and \
        (not filters.get('ano') or date[:4] == filters['ano']) and \
        (not filters.get('tipo') or row.get('tipo') == filters['tipo']) and \
        (not filters.get('modalidade') or row.get('modalidade') == filters['modalidade']) and \
        (not filters.get('resultado') or row.get('review_result', 'PENDENTE') == filters['resultado']) and \
        (not filters.get('evento') or row.get('event_id') == filters['evento']) and \
        (not filters.get('mes') or date[5:7] == filters['mes']) and \
        (not filters.get('inicio') or date >= filters['inicio']) and \
        (not filters.get('fim') or date <= filters['fim']) and \
        all(term in text for term in norm(filters.get('busca')).split())

def field_for(row):
    musician = row.get('tipo') == 'musico'
    modality = row.get('modalidade')
    if musician and modality in {'troca_necessidade', 'troca_enfermidade'}:
        return 'musicos_troca_instrumento'
    return {('musico', 'culto'): 'musicos_culto_oficial', ('musico', 'oficializacao'): 'musicos_oficializacao',
            ('organista', 'rjm'): 'organistas_rjm', ('organista', 'culto'): 'organistas_culto_oficial',
            ('organista', 'oficializacao'): 'organistas_oficializacao'}.get((row.get('tipo'), modality))

def summarize(rows):
    groups = {name: {'grupo': name, 'cartas': 0, 'pendentes': 0, **{k: 0 for k in LEGACY_FIELDS}} for name in GROUPS}
    for row in rows:
        group = groups[regional_group(row.get('municipio'))]
        group['cartas'] += 1
        group['pendentes'] += row.get('review_result', 'PENDENTE') == 'PENDENTE'
        field = field_for(row)
        if row.get('review_result') == 'APROVADO' and field:
            group[field] += 1
    counts = Counter(row.get('review_result', 'PENDENTE') for row in rows)
    return list(groups.values()), {'cartas': len(rows), 'pendentes': counts['PENDENTE'],
                                   'aprovados': counts['APROVADO'], 'pdfs': sum(r.get('status') == 'ready' for r in rows)}

def exam_payload(letter, responsible):
    p, event = letter.get('payload') or {}, letter.get('event_snapshot') or {}
    if not p.get('pessoa_id'):
        raise ValueError('Esta carta não possui um candidato vinculado. Regularize o vínculo antes de confirmar.')
    kind = {'rjm': 'RJM', 'culto': 'CULTO OFICIAL', 'oficializacao': 'OFICIALIZACAO',
            'troca_necessidade': 'TROCA DE INSTRUMENTO', 'troca_enfermidade': 'TROCA DE INSTRUMENTO'}.get(letter.get('modalidade'))
    if not kind:
        raise ValueError('Modalidade sem correspondência no painel de exames.')
    return {'aluno_id': p['pessoa_id'], 'nome_aluno': letter['nome'], 'municipio': letter['municipio'],
            'comum': letter['comum'], 'instrumento': p.get('instrumento'),
            'categoria': 'ORGANISTA' if letter['tipo'] == 'organista' else 'MÚSICO',
            'data_exame': event['data'], 'tipo_exame': kind, 'lancado_por': responsible,
            'encarregado_local': ((letter.get('ministry_snapshot') or {}).get('encarregado') or {}).get('nome'),
            'agenda_evento_id': letter.get('event_id'), 'agenda_evento_titulo': event.get('evento'),
            'observacoes': 'Confirmação da carta ' + letter['id'], 'origem': 'PAINEL'}
