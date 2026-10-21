"""Conferência conservadora do DARPE com os dados de origem espelhados do SAM."""
import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from difflib import SequenceMatcher
from hashlib import sha256

import requests
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from .access_control import _norm, can_access, common_catalog, service_headers, user_scope
from .darpe import RESOURCES, _actor, _canonical_city, _denied, _read_all_rows, _resolve_import_common, _url
from .gem import INSTRUMENT_ORDER_ALIASES
from .module_access import MODULE_DARPE, can_access_module
from .music_events_identity import CommonResolver

LABELS = {
    'conferido': 'Dados conferidos', 'preencher': 'Instrumento ausente no DARPE',
    'divergente': 'Instrumento diferente do SAM', 'ambiguo': 'Correspondência não confirmada',
    'sem_sam': 'Sem correspondência no SAM', 'nao_oficializado': 'Não oficializado no SAM',
    'sam_sem_instrumento': 'Instrumento não informado no SAM',
    'nome_divergente': 'Possível correspondência · confira o nome',
    'ministerio': 'Cadastro ministerial · SAM não se aplica',
    'sem_funcao_musical': 'Sem função musical · SAM não se aplica',
}

# Identidade explicitamente confirmada pelo responsável, limitada à mesma comum.
CONFIRMED_NAMES = {
    ('DANIEL LUIZ DA SILVA SANTOS', 'BR-21-1020'): 'DANIEL LUIZ DA SILVA DOS SANTOS',
}
CONFIRMED_MINISTRIES = {
    ('ISRAEL FERNANDES GUILHERME', 'BR-22-0423'): 'Ancião',
}


def _name_parts(value):
    return tuple(part for part in _norm(value).split() if part not in {'DA', 'DE', 'DO', 'DAS', 'DOS', 'E'})


def instrument_key(value):
    aliases = {_norm(key): _norm(target) for key, target in INSTRUMENT_ORDER_ALIASES.items()}
    aliases['VIOLONCELLO'] = 'VIOLONCELO'
    return aliases.get(_norm(value), _norm(value))


def _official(row):
    return 'OFICIALIZAD' in _norm(row.get('nivel')) and 'NAO OFICIALIZAD' not in _norm(row.get('nivel'))


def reconcile(darpe, sources, catalog, scope):
    """Nunca usa instrumento, similaridade ou somente o nome para decidir identidade."""
    resolver = CommonResolver(catalog)
    @lru_cache(maxsize=None)
    def location(common, city):
        canonical = _resolve_import_common(resolver, common, city)
        code = re.match(r'^(BR-\d+-\d+)', (canonical or {}).get('comum', ''))
        return canonical, code.group(1) if code else None

    sam, targets = [], []
    linked_local_ids = {str(row.get('aluno_id')) for row in sources
                        if row.get('aluno_id') and row.get('source_kind') != 'sam_gem'}
    sources = sorted(sources, key=lambda row: row.get('source_kind') == 'sam_gem')
    source_keys = set()
    for original in sources:
        if original.get('missing_since'):
            continue
        payload = original.get('source_payload') or {}
        common = original.get('source_common') or payload.get('common_name')
        city = payload.get('city')
        canonical, code = location(common, city)
        city = (canonical or {}).get('cidade') or city
        if not _canonical_city(city) or not can_access(scope, {'comum': (canonical or {}).get('comum') or common, 'cidade': city}):
            continue
        name = str(original.get('source_name') or payload.get('name') or '').strip(' *')
        key = (_norm(name), code)
        if original.get('source_kind') == 'sam_gem' and (str(original['id']) in linked_local_ids or key in source_keys):
            continue
        if original.get('source_kind') != 'sam_gem':
            source_keys.add(key)
        sam.append({'id': original['id'], 'nome': name,
                    'comum': (canonical or {}).get('comum') or common or '', 'cidade': _canonical_city(city),
                    'codigo': code, 'instrumento': original.get('source_instrument') or payload.get('instrument') or '',
                    'nivel': original.get('source_level') or payload.get('level') or '',
                    'cargo': original.get('source_ministry') or payload.get('ministry') or '',
                    'origem': 'Cadastro SAM no GEM' if original.get('source_kind') == 'sam_gem' else 'Sincronização SAM',
                    'last_seen_at': original.get('last_seen_at')})
    for original in darpe:
        canonical, code = location(original.get('comum_congregacao'), original.get('cidade'))
        city = (canonical or {}).get('cidade') or original.get('cidade')
        common = (canonical or {}).get('comum') or original.get('comum_congregacao') or ''
        if not _canonical_city(city) or not can_access(scope, {'comum': common, 'cidade': city}):
            continue
        targets.append({**original, 'comum': common, 'codigo': code, 'cidade': _canonical_city(city)})
    by_name, by_key, by_common, target_keys = defaultdict(list), defaultdict(list), defaultdict(list), Counter()
    for row in sam:
        by_name[_norm(row['nome'])].append(row)
        if row['codigo']:
            by_key[(_norm(row['nome']), row['codigo'])].append(row)
            by_common[row['codigo']].append(row)
    for row in targets:
        key = (_norm(row.get('nome_completo')), row['codigo'])
        target_keys[(CONFIRMED_NAMES.get(key, key[0]), key[1])] += 1
    result = []
    for row in targets:
        name = _norm(row.get('nome_completo'))
        key = (name, row['codigo'])
        confirmed_name = CONFIRMED_NAMES.get(key, name)
        candidates = by_key.get((confirmed_name, row['codigo']), []) if row['codigo'] else []
        source = candidates[0] if len(candidates) == 1 and target_keys[(confirmed_name, row['codigo'])] == 1 else None
        suggestions = []
        status, evidence = 'sem_sam', 'Cadastro DARPE não localizado no SAM.'
        if by_name.get(name):
            status, evidence = 'ambiguo', 'Confira o nome e a comum antes de confirmar o cadastro.'
            suggestions = by_name[name][:3]
        musical = any(row.get(field) for field in ('darpe_musico', 'darpe_organista', 'darpe_musico_organista'))
        ministerial = bool(row.get('darpe_ministerio') and not musical)
        if not musical:
            source, suggestions = None, []
        if not source and musical and not suggestions and row['codigo']:
            parts = _name_parts(name)
            ranked = []
            for candidate in by_common.get(row['codigo'], []):
                other = _name_parts(candidate['nome'])
                score = SequenceMatcher(None, name, _norm(candidate['nome'])).ratio()
                first = SequenceMatcher(None, parts[0] if parts else '', other[0] if other else '').ratio()
                if parts == other or (score >= .78 and first >= .75):
                    ranked.append((score, candidate))
            suggestions = [candidate for _, candidate in sorted(ranked, key=lambda item: item[0], reverse=True)[:3]]
            if suggestions:
                status, evidence = 'nome_divergente', 'Possível cadastro na mesma comum. Confira o nome; nenhum dado será atribuído automaticamente.'
        if ministerial:
            status, evidence = 'ministerio', 'Cadastro ministerial sem função musical. Não exige correspondência no SAM.'
        elif not musical:
            status, evidence = 'sem_funcao_musical', 'Sem função de músico ou organista no DARPE. Conferência SAM não se aplica.'
        if source and musical:
            suggestions = []
            evidence = 'Instrumento DARPE igual ao instrumento oficial do SAM.'
            if not _official(source):
                status = 'nao_oficializado'
            elif instrument_key(source['instrumento']) in {'', 'A DEFINIR', 'NAO INFORMADO', '-'}:
                status = 'sam_sem_instrumento'
            elif not str(row.get('instrumento_oficializado') or '').strip():
                status = 'preencher'
            elif instrument_key(row['instrumento_oficializado']) == instrument_key(source['instrumento']):
                status = 'conferido'
            else:
                status = 'divergente'
            evidence = {
                'conferido': 'Instrumento DARPE igual ao instrumento oficial do SAM.',
                'preencher': 'O instrumento oficial pode ser preenchido no DARPE.',
                'divergente': 'Revise o instrumento DARPE conforme o instrumento oficial do SAM.',
                'nao_oficializado': 'O SAM não registra oficialização. Cadastro precisa de revisão.',
                'sam_sem_instrumento': 'Confira o instrumento no SAM antes de validar o DARPE.',
            }[status]
        display_source = source or (suggestions[0] if suggestions else None)
        cargo = (source or {}).get('cargo', '')
        encarregado_tipo = 'REGIONAL' if _norm(cargo) == 'ENCARREGADO REGIONAL' else 'LOCAL' if _norm(cargo) == 'ENCARREGADO LOCAL' else ''
        result.append({'id': row['id'], 'nome': row.get('nome_completo'), 'cidade': row['cidade'],
                       'comum': row['comum'], 'darpe_id': row['id'], 'darpe_status': row.get('status') or '',
                       'darpe_instrumento': row.get('instrumento_oficializado') or '',
                       'sam_id': source['id'] if source else None, 'sam_instrumento': display_source['instrumento'] if display_source else '',
                       'sam_nivel': display_source['nivel'] if display_source else '', 'situacao': status,
                       'sam_nome': display_source['nome'] if display_source else '',
                       'cargo_sam': cargo, 'encarregado_tipo': encarregado_tipo,
                       'ministerio_descricao': CONFIRMED_MINISTRIES.get(key, 'Ministério') if row.get('darpe_ministerio') else '',
                       'candidatos': [{'nome': candidate['nome'], 'comum': candidate['comum'], 'instrumento': candidate['instrumento'], 'nivel': candidate['nivel']} for candidate in suggestions],
                       'sam_origem': 'SAM' if source else '',
                       'correspondencia': 'Não se aplica' if not musical else 'Confirmada' if source else 'Não confirmada' if status in {'ambiguo', 'nome_divergente'} else 'Não encontrada',
                       'evidencia': evidence, 'updated_at': row.get('updated_at')})
    return sorted(result, key=lambda row: (row['cidade'], _norm(row['nome']))), max(
        (row['last_seen_at'] for row in sam if row.get('last_seen_at')), default=None)


def read_sam_sources(refresh=False):
    key = 'darpe:sam-reference:v3'
    cached = cache.get(key)
    if cached is not None and not refresh:
        return cached
    def sync_states():
        return _read_all_rows({'table': 'sam_student_sync_state'},
                             select='id,aluno_id,source_name,source_common,source_instrument,source_level,source_payload,last_seen_at,missing_since')
    # Consulta o cadastro completo para distinguir ausência de não oficialização.
    # Estados recentes e registros removidos da origem têm prioridade sobre a carga.
    def local_catalog():
        return _read_all_rows({'table': 'musica_acompanhamento_aluno'},
                               select='id,nome_aluno,comum_congregacao,municipio,instrumento,nivel,cargo_ministerio')
    with ThreadPoolExecutor(max_workers=2) as executor:
        states_future = executor.submit(sync_states)
        graduates_future = executor.submit(local_catalog)
        sources, graduates = states_future.result(), graduates_future.result()
    sources += [{'id': row['id'], 'source_name': row.get('nome_aluno'),
                 'source_common': row.get('comum_congregacao'), 'source_instrument': row.get('instrumento'),
                 'source_level': row.get('nivel'), 'source_payload': {'city': row.get('municipio')},
                 'source_ministry': row.get('cargo_ministerio'),
                 'source_kind': 'sam_gem'} for row in graduates]
    cache.set(key, sources, 300)
    return sources


def enrich_roles(rows):
    """Diferencia o cargo SAM sem transformar cargo musical em tipo ministerial."""
    wanted = set()
    for row in rows:
        code = re.match(r'^(BR-\d+-\d+)', row.get('comum_exibicao') or row.get('comum_congregacao') or '')
        key = (_norm(row.get('nome_completo')), code.group(1) if code else None)
        if row.get('darpe_encarregado') or key in CONFIRMED_NAMES:
            wanted.add(CONFIRMED_NAMES.get(key, key[0]))
        row['ministerio_descricao'] = CONFIRMED_MINISTRIES.get(key, 'Ministério') if row.get('darpe_ministerio') else ''
    if not wanted:
        return rows
    cache_key = 'darpe:musical-roles:v1:' + sha256('|'.join(sorted(wanted)).encode('utf-8')).hexdigest()
    sources = cache.get(cache_key)
    if sources is None:
        sources = _read_all_rows({'table': 'musica_acompanhamento_aluno'},
            select='id,nome_aluno,comum_congregacao,cargo_ministerio',
            filters={'nome_aluno': 'in.(' + ','.join(json.dumps(name) for name in sorted(wanted)) + ')'})
        cache.set(cache_key, sources, 300)
    for row in rows:
        code = re.match(r'^(BR-\d+-\d+)', row.get('comum_exibicao') or row.get('comum_congregacao') or '')
        if not code:
            continue
        name = CONFIRMED_NAMES.get((_norm(row.get('nome_completo')), code.group(1)), _norm(row.get('nome_completo')))
        matches = [source for source in sources if _norm(source.get('nome_aluno')) == name and
                   re.match(r'^' + re.escape(code.group(1)) + r'(?:\s|$)', source.get('comum_congregacao') or '')]
        if len(matches) == 1:
            role = _norm(matches[0].get('cargo_ministerio'))
            row['encarregado_tipo'] = 'LOCAL' if role == 'ENCARREGADO LOCAL' else 'REGIONAL' if role == 'ENCARREGADO REGIONAL' else ''
    return rows


def read_comparison(request):
    darpe = _read_all_rows(RESOURCES['cadastros'])
    sources = read_sam_sources(refresh=request.method == 'POST' or request.GET.get('refresh') == '1')
    return reconcile(darpe, sources, common_catalog(), user_scope(request))


def filtered(rows, params):
    query = _norm(params.get('q'))
    cities = params.getlist('cidade') if hasattr(params, 'getlist') else params.get('cidade', [])
    if isinstance(cities, str):
        cities = [cities]
    cities = set(filter(None, cities))
    return [row for row in rows if
            (not cities or row['cidade'] in cities) and
            (not params.get('comum') or row['comum'] == params['comum']) and
            (not params.get('situacao') or row['situacao'] == params['situacao']) and
            (not params.get('darpe_status') or _norm(row['darpe_status']) == _norm(params['darpe_status'])) and
            (not query or query in _norm(' '.join(str(row.get(key) or '') for key in
             ('nome', 'comum', 'cidade', 'darpe_instrumento', 'sam_instrumento'))))]


def fill_confirmed(rows, actor):
    groups = defaultdict(list)
    for row in rows:
        if row['situacao'] == 'preencher' and row.get('updated_at'):
            groups[row['sam_instrumento']].append(row)
    count = 0
    for instrument, items in groups.items():
        for start in range(0, len(items), 50):
            batch = items[start:start + 50]
            guards = ','.join(f'and(id.eq.{row["darpe_id"]},updated_at.eq.{json.dumps(row["updated_at"])})' for row in batch)
            response = requests.patch(_url(RESOURCES['cadastros']), headers=service_headers('return=representation'),
                params={'or': '(' + guards + ')', 'and': '(or(instrumento_oficializado.is.null,instrumento_oficializado.eq.""))',
                        'select': 'id'},
                json={'instrumento_oficializado': instrument, 'updated_by_user_id': actor['id'],
                      'updated_by_name': actor['name'] + ' · Conciliação SAM'}, timeout=30)
            response.raise_for_status()
            count += len(response.json())
    return count


def standardize_spellings(rows, actor):
    """Adota a grafia SAM somente para instrumentos comprovadamente equivalentes."""
    count = 0
    for row in rows:
        old, official = row.get('darpe_instrumento'), row.get('sam_instrumento')
        if (row['situacao'] != 'conferido' or not row.get('sam_id') or not row.get('updated_at')
                or not old or not official or _norm(old) == _norm(official)
                or instrument_key(old) != instrument_key(official)):
            continue
        response = requests.patch(_url(RESOURCES['cadastros']), headers=service_headers('return=representation'),
            params={'id': 'eq.' + str(row['darpe_id']), 'updated_at': 'eq.' + row['updated_at'],
                    'instrumento_oficializado': 'eq.' + old, 'select': 'id'},
            json={'instrumento_oficializado': official, 'updated_by_user_id': actor['id'],
                  'updated_by_name': actor['name'] + ' · Padronização da grafia SAM'}, timeout=30)
        response.raise_for_status()
        count += len(response.json())
    return count


@never_cache
def page(request):
    if not can_access_module(request, MODULE_DARPE):
        return render(request, 'pages/403.html', status=403)
    return render(request, 'pages/darpe_sam.html')


@never_cache
def api(request, action=None):
    if not can_access_module(request, MODULE_DARPE):
        return _denied()
    if request.method != ('POST' if action == 'preencher' else 'GET'):
        return JsonResponse({'error': 'Método não permitido.'}, status=405)
    try:
        rows, last_seen = read_comparison(request)
        view = filtered(rows, request.GET)
        if action == 'preencher':
            actor = _actor(request)
            if not actor['id']:
                return JsonResponse({'error': 'Sessão sem autoria válida.'}, status=401)
            return JsonResponse({'updated': fill_confirmed(view, actor)})
        page_number = max(1, int(request.GET.get('pagina', 1)))
        count = Counter(row['situacao'] for row in view)
        return JsonResponse({'items': view[(page_number - 1) * 100:page_number * 100], 'total': len(view),
                             'pagina': page_number, 'paginas': max(1, (len(view) + 99) // 100),
                             'counts': dict(count), 'labels': LABELS, 'last_seen_at': last_seen,
                             'cities': sorted({row['cidade'] for row in rows}),
                             'commons': sorted({row['comum'] for row in rows if not request.GET.getlist('cidade') or row['cidade'] in request.GET.getlist('cidade')})})
    except ValueError:
        return JsonResponse({'error': 'Parâmetros ou dados inválidos para a conferência.'}, status=400)
    except requests.RequestException:
        return JsonResponse({'error': 'Não foi possível consultar ou atualizar a conferência SAM. Tente novamente.'}, status=502)
