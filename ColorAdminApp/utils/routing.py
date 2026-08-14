import math
import re
import requests
import unicodedata
from functools import lru_cache
from django.conf import settings


def normalize_text(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    return ' '.join(''.join(c for c in text if not unicodedata.combining(c)).upper().split())


def neighborhood_key(visit):
    """Chave territorial estável usada para impedir a fragmentação de bairros."""
    return normalize_text((visit or {}).get('setor')) or 'SEM BAIRRO'


def street_key(visit):
    """Normaliza a rua, removendo coordenadas, CEP e número do imóvel."""
    address = re.sub(r'^\s*\[.*?\]\s*', '', str((visit or {}).get('endereco_visitado') or (visit or {}).get('endereco') or ''))
    address = re.sub(r'\b\d{5}-?\d{3}\b', '', address)
    street = re.split(r'\s*[,\-]\s*\d+\b|\s+N[.º°]?\s*\d+\b', address, maxsplit=1, flags=re.IGNORECASE)[0]
    return normalize_text(street) or 'ENDERECO NAO INFORMADO'


def address_number(visit):
    address = re.sub(r'^\s*\[.*?\]\s*', '', str((visit or {}).get('endereco_visitado') or (visit or {}).get('endereco') or ''))
    match = re.search(r'(?:[,\-]\s*|\bN[.º°]?\s*)(\d+)\b', address, re.IGNORECASE)
    return int(match.group(1)) if match else float('inf')

def haversine_distance(coord1, coord2):
    """
    Calcula a distância em metros entre duas coordenadas (lat, lng) usando a fórmula de Haversine.
    """
    if not coord1 or not coord2:
        return float('inf')
        
    lat1, lon1 = coord1
    lat2, lon2 = coord2
    
    R = 6371000  # Raio da Terra em metros
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2.0)**2 + \
        math.cos(phi1) * math.cos(phi2) * \
        math.sin(delta_lambda / 2.0)**2
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

def extract_coords_from_address(address):
    """
    Extrai [lat, lng] do endereço se estiver no formato: [-23.123, -46.123] Rua X...
    """
    if not address:
        return None
    match = re.match(r'^\[([-.\d]+),\s*([-.\d]+)\]', address)
    if match:
        try:
            return (float(match.group(1)), float(match.group(2)))
        except:
            return None
    return None

@lru_cache(maxsize=1024)
def geocode_address_fallback(address):
    """
    Geocodifica um endereço usando Google Maps ou Nominatim como fallback.
    """
    if not address:
        return None
        
    # Limpa a string de coordenadas se houver
    clean_addr = re.sub(r'^\[.*?\]\s*', '', address)
    clean_addr += ", SP, Brasil"
    
    api_key = settings.GOOGLE_MAPS_API_KEY
    if api_key:
        try:
            response = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": clean_addr, "key": api_key, "language": "pt-BR"},
                timeout=5,
            )
            result = response.json()
            if result.get('status') == 'OK':
                location = result['results'][0]['geometry']['location']
                return (location['lat'], location['lng'])
        except (requests.RequestException, ValueError, KeyError, IndexError):
            pass

    # Fallback sem chave: mantém o roteiro operacional quando o Google estiver
    # sem faturamento, com cota bloqueada ou temporariamente indisponível.
    try:
        response = requests.get(
            "https://geocode.arcgis.com/arcgis/rest/services/World/GeocodeServer/findAddressCandidates",
            params={
                "SingleLine": clean_addr,
                "f": "json",
                "countryCode": "BRA",
                "maxLocations": 1,
                "outFields": "Match_addr",
            },
            timeout=8,
        )
        response.raise_for_status()
        candidates = response.json().get('candidates') or []
        if candidates and float(candidates[0].get('score') or 0) >= 60:
            location = candidates[0]['location']
            return (float(location['y']), float(location['x']))
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError):
        pass
        
    return None


@lru_cache(maxsize=256)
def get_common_coordinates(comum, cidade=''):
    """Geocodifica a própria comum, que é sempre o ponto inicial do roteiro."""
    if not comum:
        return None
    nome = re.sub(r'^BR-\d+(?:-\d+)?\s*-\s*', '', str(comum)).strip()
    consultas = [
        f"Congregação Cristã no Brasil {nome}, {cidade}, SP, Brasil",
        f"CCB {nome}, {cidade}, SP, Brasil",
    ]
    for consulta in consultas:
        coords = geocode_address_fallback(consulta)
        if coords:
            return coords
    return None


def discover_nearby_neighborhoods(comum, cidade='', data_referencia=None):
    """Agrupa os bairros cadastrados e os ordena a partir da comum."""
    url = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_IRMANDADE}"
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    response = requests.get(url, headers=headers, params={
        "select": "id,comum,setor,endereco,status", "comum": f"eq.{comum}", "order": "setor.asc"
    }, timeout=15)
    response.raise_for_status()
    membros = [row for row in response.json() if row.get('setor')]

    try:
        referencia = datetime.strptime(data_referencia, "%Y-%m-%d") if data_referencia else datetime.now()
    except (TypeError, ValueError):
        referencia = datetime.now()
    limite = (referencia - timedelta(days=15)).strftime("%Y-%m-%dT00:00:00")
    agenda_url = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_AGENDA}"
    agenda_response = requests.get(agenda_url, headers=headers, params={
        "select": "irmandade_id,status", "data_inicio": f"gte.{limite}"
    }, timeout=15)
    indisponiveis = set()
    if agenda_response.status_code == 200:
        indisponiveis = {
            str(item.get('irmandade_id')) for item in agenda_response.json()
            if item.get('irmandade_id') and item.get('status') != 'Cancelada'
        }
    membros = [item for item in membros if str(item.get('id')) not in indisponiveis]
    grupos = {}
    for membro in membros:
        bairro = str(membro.get('setor') or '').strip()
        if not bairro:
            continue
        chave = normalize_text(bairro)
        grupo = grupos.setdefault(chave, {"nome": bairro, "quantidade": 0, "coords": [], "enderecos": []})
        grupo["quantidade"] += 1
        coords = extract_coords_from_address(membro.get('endereco') or '')
        if coords:
            grupo["coords"].append(coords)
        elif membro.get('endereco'):
            grupo["enderecos"].append(membro.get('endereco'))

    centro = get_common_coordinates(comum, cidade)
    grupos_sem_coords = [grupo for grupo in grupos.values() if not grupo["coords"] and grupo["enderecos"]]
    if grupos_sem_coords:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            resultados = executor.map(
                lambda grupo: geocode_address_fallback(grupo["enderecos"][0]), grupos_sem_coords
            )
            for grupo, coords in zip(grupos_sem_coords, resultados):
                if coords:
                    grupo["coords"].append(coords)
    bairros = []
    for grupo in grupos.values():
        coords = None
        if grupo["coords"]:
            coords = (
                sum(item[0] for item in grupo["coords"]) / len(grupo["coords"]),
                sum(item[1] for item in grupo["coords"]) / len(grupo["coords"]),
            )
        distancia = haversine_distance(centro, coords) if centro and coords else None
        bairros.append({
            "nome": grupo["nome"],
            "quantidade": grupo["quantidade"],
            "distancia_metros": round(distancia) if distancia is not None else None,
        })
    bairros.sort(key=lambda item: (
        item["distancia_metros"] is None,
        item["distancia_metros"] if item["distancia_metros"] is not None else float('inf'),
        normalize_text(item["nome"]),
    ))
    return bairros

def get_visit_coordinates(visit):
    """
    Tenta obter coordenadas de uma visita.
    """
    addr = visit.get('endereco_visitado') or ''
    coords = extract_coords_from_address(addr)
    if coords:
        return coords
    
    coords = geocode_address_fallback(addr)
    return coords


def clean_visit_address(address):
    """Remove o prefixo técnico de coordenadas sem alterar o endereço cadastrado."""
    return re.sub(
        r'^\s*\[\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\]\s*',
        '', str(address or '')
    ).strip()


def route_address_key(visit, fallback=''):
    """Identifica uma casa pelo endereço, independentemente do morador."""
    clean_address = clean_visit_address(
        (visit or {}).get('endereco_visitado') or (visit or {}).get('endereco')
    )
    address_key = re.sub(r'[^A-Z0-9]+', ' ', normalize_text(clean_address)).strip()
    return address_key or str(fallback or '')


def group_route_visits_by_address(visits):
    """Consolida apenas a exibição do roteiro, sem criar vínculos entre cadastros."""
    grouped = []
    by_address = {}

    def unique_join(current, incoming):
        values = []
        for value in (current, incoming):
            value = ' '.join(str(value or '').strip().split())
            if value and value not in values:
                values.append(value)
        return ' | '.join(values)

    for position, source in enumerate(visits or []):
        visit = dict(source)
        address_key = route_address_key(visit)
        # Sem endereço confiável, cada cadastro continua sendo uma visita independente.
        key = address_key or f'__SEM_ENDERECO_{position}'
        existing = by_address.get(key)
        if existing is None:
            visit['_route_names'] = [str(visit.get('titulo') or '').strip()]
            by_address[key] = visit
            grouped.append(visit)
            continue

        # O prefixo [latitude, longitude] não é exibido no roteiro, mas precisa
        # continuar no dado interno para evitar geocodificação ambígua de ruas
        # homônimas. Se somente um dos moradores tiver coordenadas, use esse valor.
        existing_address = existing.get('endereco_visitado') or existing.get('endereco') or ''
        incoming_address = visit.get('endereco_visitado') or visit.get('endereco') or ''
        if not extract_coords_from_address(existing_address) and extract_coords_from_address(incoming_address):
            existing['endereco_visitado'] = incoming_address

        name = str(visit.get('titulo') or '').strip()
        if name and name not in existing['_route_names']:
            existing['_route_names'].append(name)
            existing['titulo'] = ' / '.join(filter(None, existing['_route_names']))

        existing_times = [value for value in (existing.get('data_inicio'), visit.get('data_inicio')) if value]
        if existing_times:
            existing['data_inicio'] = min(existing_times)
        for field in ('observacoes', 'apontamentos_restritos'):
            existing[field] = unique_join(existing.get(field), visit.get(field))

    for visit in grouped:
        visit.pop('_route_names', None)
    return grouped


def order_route_chronologically(visits, start_coords=None):
    """Ordena o roteiro pelo horário e recalcula distâncias na sequência exibida."""
    indexed = list(enumerate(visits or []))
    indexed.sort(key=lambda pair: (
        not bool(pair[1].get('data_inicio')),
        str(pair[1].get('data_inicio') or ''),
        pair[0],
    ))
    ordered = [visit for _, visit in indexed]
    current_loc = start_coords
    for visit in ordered:
        coords = get_visit_coordinates(visit)
        if coords:
            if current_loc:
                visit['distance_meters'] = haversine_distance(current_loc, coords)
            else:
                # Sem coordenada real da comum, não inventa distância para a
                # primeira parada. As próximas partem desta localização real.
                visit.pop('distance_meters', None)
            visit['lat'], visit['lng'] = coords
            current_loc = coords
        else:
            visit.pop('distance_meters', None)
    return ordered

def _optimize_route_nearest_neighbor_legacy(visits, start_coords=None):
    """
    Ordena uma lista de visitas usando o algoritmo Nearest Neighbor (Vizinho Mais Próximo).
    """
    if not visits:
        return []
        
    # Coordenadas padrão da igreja
    if not start_coords:
        start_coords = (-23.538263, -46.926524)
        
    enriched_visits = []
    for v in visits:
        coords = get_visit_coordinates(v)
        if coords:
            enriched_visits.append({
                'data': v,
                'coords': coords,
                'visited': False
            })
        else:
            enriched_visits.append({
                'data': v,
                'coords': None,
                'visited': False
            })

    valid_visits = [v for v in enriched_visits if v['coords'] is not None]
    invalid_visits = [v for v in enriched_visits if v['coords'] is None]

    if not valid_visits:
        return [v['data'] for v in invalid_visits]

    optimized_route = []
    current_loc = start_coords

    while True:
        unvisited = [v for v in valid_visits if not v['visited']]
        if not unvisited:
            break
            
        closest = None
        min_dist = float('inf')
        
        for v in unvisited:
            dist = haversine_distance(current_loc, v['coords'])
            if dist < min_dist:
                min_dist = dist
                closest = v
                
        if closest:
            closest['visited'] = True
            closest['data']['distance_meters'] = min_dist
            closest['data']['lat'] = closest['coords'][0]
            closest['data']['lng'] = closest['coords'][1]
            optimized_route.append(closest['data'])
            current_loc = closest['coords']
        else:
            break

    for v in invalid_visits:
        optimized_route.append(v['data'])

    return optimized_route


def optimize_route_by_territory(visits, start_coords=None):
    """Ordena bairro, rua e número sem permitir uma sequência A -> B -> A."""
    if not visits:
        return []
    current_loc = start_coords

    def group_coordinates(items):
        coords = [get_visit_coordinates(item) for item in items]
        coords = [coord for coord in coords if coord]
        if not coords:
            return None
        return (sum(c[0] for c in coords) / len(coords), sum(c[1] for c in coords) / len(coords))

    neighborhoods = {}
    for visit in visits:
        neighborhoods.setdefault(neighborhood_key(visit), []).append(visit)
    pending = [
        {'key': key, 'items': items, 'coords': group_coordinates(items)}
        for key, items in neighborhoods.items()
    ]
    route = []
    while pending:
        pending.sort(key=lambda group: (
            group['coords'] is None,
            haversine_distance(current_loc, group['coords']) if current_loc and group['coords'] else 0,
            group['key'],
        ))
        neighborhood = pending.pop(0)
        streets = {}
        for visit in neighborhood['items']:
            streets.setdefault(street_key(visit), []).append(visit)
        street_groups = [
            {'key': key, 'items': items, 'coords': group_coordinates(items)}
            for key, items in streets.items()
        ]
        while street_groups:
            street_groups.sort(key=lambda group: (
                group['coords'] is None,
                haversine_distance(current_loc, group['coords']) if current_loc and group['coords'] else 0,
                group['key'],
            ))
            street = street_groups.pop(0)
            houses = sorted(street['items'], key=lambda item: (
                address_number(item), normalize_text(item.get('titulo'))
            ))
            for visit in houses:
                coords = get_visit_coordinates(visit)
                if coords:
                    if current_loc:
                        visit['distance_meters'] = haversine_distance(current_loc, coords)
                    else:
                        visit.pop('distance_meters', None)
                    visit['lat'], visit['lng'] = coords
                    current_loc = coords
                else:
                    visit.pop('distance_meters', None)
                route.append(visit)
    return route


# Mantém a API existente enquanto aplica a estratégia territorial.
optimize_route = optimize_route_by_territory


def limit_daily_route(morning, afternoon, per_shift=5):
    """Entrega até dez casas, usando cinco por turno como referência."""
    morning = list(morning)
    afternoon = list(afternoon)
    total_limit = per_shift * 2
    # Uma vaga ociosa de um período pode ser ocupada pelo outro. Assim a
    # referência 5 + 5 não reduz um roteiro válido para menos de dez casas.
    morning_limit = min(len(morning), per_shift + max(0, per_shift - len(afternoon)))
    afternoon_limit = min(len(afternoon), total_limit - morning_limit)
    return morning[:morning_limit] + afternoon[:afternoon_limit]


from datetime import datetime, timedelta
import concurrent.futures

def auto_dispatch_visits(equipe, data_filtro, existing_visits=None, comum=None, cidade='', bairro=None):
    """
    Motor de Despacho Automático:
    1. Busca todos os irmãos.
    2. Busca visitas recentes (últimos 15 dias) ou futuras que não estão Canceladas.
    3. Filtra os irmãos que já receberam visita.
    4. Seleciona os N mais próximos da igreja (para inteirar 10).
    5. Salva na agenda para a equipe e retorna.
    """
    if existing_visits is None:
        existing_visits = []
        
    existing_address_keys = {
        route_address_key(visit, fallback=f"__EXISTENTE_{position}")
        for position, visit in enumerate(existing_visits)
    }
    num_to_generate = 10 - len(existing_address_keys)
    if num_to_generate <= 0:
        return []
    url_irmandade = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_IRMANDADE}"
    url_agenda = f"{settings.SUPABASE_URL}/rest/v1/{settings.SUPABASE_TABLE_VISITAS_AGENDA}"
    
    headers = {
        "apikey": settings.SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json"
    }
    
    # 1. Buscar todos os irmãos
    # Nunca carregue apontamentos_restritos neste fluxo compartilhado. A rota
    # operacional pode ser usada por Instrutores e não deve transportar dados sensíveis.
    safe_member_fields = (
        "id,nome,comum,setor,endereco,status,categoria,equipe_visita,ultima_visita,"
        "preferencia_periodo_visita,observacoes"
    )
    resp_irm = requests.get(url_irmandade, headers=headers, params=[("select", safe_member_fields)], timeout=10)
    if resp_irm.status_code != 200:
        return []
    todos_irmaos = resp_irm.json()
    if comum:
        todos_irmaos = [
            item for item in todos_irmaos
            if normalize_text(item.get('comum')) == normalize_text(comum)
        ]
    if bairro:
        todos_irmaos = [
            item for item in todos_irmaos
            if normalize_text(item.get('setor')) == normalize_text(bairro)
        ]
    todos_irmaos = [
        item for item in todos_irmaos
        if 'INATIV' not in normalize_text(item.get('status'))
    ]
    member_ids_da_comum = {str(item.get('id')) for item in todos_irmaos if item.get('id')}
    
    # 2. Buscar todo o histórico necessário para priorizar corretamente as
    # casas nunca visitadas e, depois, as visitas mais antigas.
    params_agenda = [
        ("select", "irmandade_id,status,setor,endereco_visitado,equipe_responsavel,data_inicio"),
        ("limit", "5000"),
    ]
    resp_agenda = requests.get(url_agenda, headers=headers, params=params_agenda, timeout=10)
    
    neighborhood_owners = {}
    occupied_day_addresses = set(existing_address_keys)
    scheduled_future_addresses = set()
    household_history = {}
    members_by_id = {str(item.get('id')): item for item in todos_irmaos if item.get('id')}
    if resp_agenda.status_code == 200:
        for v in resp_agenda.json():
            member_id = str(v.get('irmandade_id') or '')
            if member_id not in member_ids_da_comum:
                continue
            member = members_by_id.get(member_id) or {}
            address_key = route_address_key(
                v if v.get('endereco_visitado') else member,
                fallback=f"__MEMBRO_{member_id}",
            )
            visit_date = str(v.get('data_inicio') or '')
            status_key = normalize_text(v.get('status'))
            history = household_history.setdefault(address_key, {
                'latest_event_date': '',
                'latest_status': '',
                'realized_count': 0,
                'latest_realized_date': '',
            })
            if status_key == 'REALIZADA':
                history['realized_count'] += 1
                if visit_date > history['latest_realized_date']:
                    history['latest_realized_date'] = visit_date
            if visit_date and visit_date > history['latest_event_date']:
                history['latest_event_date'] = visit_date
                history['latest_status'] = status_key

            is_final = status_key in ('REALIZADA', 'CANCELADA', 'NAO REALIZADA')
            if visit_date[:10] >= data_filtro and not is_final:
                scheduled_future_addresses.add(address_key)
            if str(v.get('data_inicio') or '')[:10] == data_filtro and v.get('equipe_responsavel'):
                neighborhood_owners.setdefault(neighborhood_key(v), v.get('equipe_responsavel'))
                if not is_final:
                    occupied_day_addresses.add(address_key)
                
    # 3. Filtrar elegíveis e extrair coordenadas
    elegiveis = []
    sem_coords = []
    
    for irmao in todos_irmaos:
        addr = irmao.get('endereco') or ''
        coords = extract_coords_from_address(addr)
        address_key = route_address_key(
            irmao, fallback=f"__MEMBRO_{irmao.get('id')}"
        )
        history = household_history.get(address_key)
        if not history and irmao.get('ultima_visita'):
            history = {
                'latest_event_date': str(irmao.get('ultima_visita')),
                'latest_status': 'REALIZADA',
                'realized_count': 1,
                'latest_realized_date': str(irmao.get('ultima_visita')),
            }
        if not history:
            priority = (0, '', '')  # Nunca visitada
        elif history['latest_status'] in ('CANCELADA', 'NAO REALIZADA'):
            priority = (1, history['latest_event_date'], '')  # Retomada necessária
        elif history['realized_count']:
            # Equilibra primeiro a quantidade de visitas. Entre casas com a
            # mesma quantidade, atende quem está há mais tempo sem visita.
            priority = (
                2,
                history['realized_count'],
                history['latest_realized_date'],
            )
        else:
            priority = (1, history['latest_event_date'], '')  # Agendamento antigo/inconclusivo
        
        item = {
            'irmao': irmao,
            'coords': coords,
            'setor': irmao.get('setor') or '',
            'address_key': address_key,
            'priority': priority,
        }
        
        if coords:
            elegiveis.append(item)
        else:
            sem_coords.append(item)
            
    # Geocodificação paralela para quem não tem coordenada (com CEP se existir)
    if sem_coords:
        def fetch_geocode_and_update(item):
            cep = item['irmao'].get('cep') or ''
            addr = item['irmao'].get('endereco') or ''
            search_query = f"{cep} {addr}".strip()
            
            # Tentar geocodificar no Google Maps
            coords = geocode_address_fallback(search_query)
            
            if coords:
                # Disparar update no banco imediatamente e não bloquear
                novo_end = f"[{coords[0]}, {coords[1]}] {addr}"
                try:
                    requests.patch(
                        url_irmandade,
                        headers=headers,
                        params=[("id", f"eq.{item['irmao']['id']}")],
                        json={"endereco": novo_end},
                        timeout=3
                    )
                except:
                    pass
            return coords

        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            resultados = list(executor.map(fetch_geocode_and_update, sem_coords))
            
        for i, item in enumerate(sem_coords):
            item['coords'] = resultados[i]
            if item['coords']:
                elegiveis.append(item)
            else:
                # Falha geral de GPS, mas não descartamos
                item['dist'] = 999999
                elegiveis.append(item)
            
    # 4. Calcular distância real até a igreja
    igreja_coords = get_common_coordinates(comum, cidade) if comum else None
    for item in elegiveis:
        if item['coords'] and igreja_coords:
            item['dist'] = haversine_distance(igreja_coords, item['coords'])
        elif 'dist' not in item:
            item['dist'] = 999999 
            
    # Ordenar pela menor distância
    grupos_bairro = {}
    for item in elegiveis:
        key = neighborhood_key(item['irmao'])
        address_key = route_address_key(
            item['irmao'], fallback=f"__MEMBRO_{item['irmao'].get('id')}"
        )
        # Uma casa já atribuída a qualquer grupo nesta data não pode ser
        # consumida novamente por outro morador do mesmo endereço.
        if address_key in occupied_day_addresses or address_key in scheduled_future_addresses:
            continue
        bairro_group = grupos_bairro.setdefault(key, {})
        bairro_group.setdefault(address_key, []).append(item)

    bairros_atuais = {neighborhood_key(item) for item in existing_visits}
    household_options = []
    for neighborhood, households in grupos_bairro.items():
        for address_key, household in households.items():
            household_options.append((neighborhood, address_key, household))
    household_options.sort(key=lambda option: (
        min(item['priority'] for item in option[2]),
        option[0] not in bairros_atuais,
        bool(neighborhood_owners.get(option[0]) and neighborhood_owners.get(option[0]) != equipe),
        min(item['dist'] for item in option[2]),
        option[0],
        street_key(option[2][0]['irmao']),
        address_number(option[2][0]['irmao']),
    ))
    selected_households = [
        (address_key, household)
        for _, address_key, household in household_options[:num_to_generate]
    ]
    
    if not selected_households:
        return []
        
    # 5. Criar na Agenda
    novas_visitas = []
    
    # Prepara payload em lote (Supabase permite bulk insert)
    payload_bulk = []
    
    # Continuar índice baseado nos existentes
    start_index = len(existing_address_keys)
    
    for i, (_, household) in enumerate(selected_households):
        item = household[0]
        irmao = item['irmao']
        
        current_idx = start_index + i
        
        # Lógica de espaçamento: 15 minutos por visita
        # As 5 primeiras (0 a 4) são de manhã começando às 09:00
        # As 5 seguintes (5 a 9) são à tarde começando às 14:00
        if current_idx < 5:
            minutos_adicionais = current_idx * 15
            hora_inicio_base = datetime.strptime(f"{data_filtro} 09:00:00", "%Y-%m-%d %H:%M:%S")
        else:
            minutos_adicionais = (current_idx - 5) * 15
            hora_inicio_base = datetime.strptime(f"{data_filtro} 14:00:00", "%Y-%m-%d %H:%M:%S")
            
        hora_inicio = hora_inicio_base + timedelta(minutes=minutos_adicionais)
        hora_fim = hora_inicio + timedelta(minutes=15)
        
        # Forçando o Fuso de São Paulo (-03:00)
        str_inicio = f"{hora_inicio.strftime('%Y-%m-%dT%H:%M:%S')}-03:00"
        str_fim = f"{hora_fim.strftime('%Y-%m-%dT%H:%M:%S')}-03:00"
        
        visit = {
            'irmandade_id': irmao.get('id'),
            # Consolida visualmente os moradores elegíveis da casa sem criar
            # relacionamento permanente entre seus cadastros.
            'titulo': ' / '.join(dict.fromkeys(
                str(person['irmao'].get('nome') or '').strip()
                for person in household if person['irmao'].get('nome')
            )),
            'setor': irmao.get('setor'),
            'endereco_visitado': irmao.get('endereco'),
            'categoria': irmao.get('categoria') or 'GVI',
            'equipe_responsavel': equipe,
            'data_inicio': str_inicio,
            'data_fim': str_fim,
            'status': 'Marcada',
            'observacoes': ''
        }
        payload_bulk.append(visit)
        
    # Bulk insert
    post_headers = headers.copy()
    post_headers["Prefer"] = "return=representation"
    resp_post = requests.post(url_agenda, headers=post_headers, json=payload_bulk, timeout=10)
    
    if resp_post.status_code in [200, 201]:
        created = resp_post.json()
        # Campos apenas em memória para que a auditoria de escopo também funcione
        # enquanto a agenda mantém o vínculo territorial pelo irmandade_id.
        for visit in created:
            visit['comum'] = comum or ''
            visit['municipio'] = cidade or ''
        return created
        
    return []
