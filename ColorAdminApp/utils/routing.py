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
    current_loc = start_coords or (-23.538263, -46.926524)

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
            haversine_distance(current_loc, group['coords']) if group['coords'] else float('inf'),
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
                haversine_distance(current_loc, group['coords']) if group['coords'] else float('inf'),
                group['key'],
            ))
            street = street_groups.pop(0)
            houses = sorted(street['items'], key=lambda item: (
                address_number(item), normalize_text(item.get('titulo'))
            ))
            for visit in houses:
                coords = get_visit_coordinates(visit)
                if coords:
                    visit['distance_meters'] = haversine_distance(current_loc, coords)
                    visit['lat'], visit['lng'] = coords
                    current_loc = coords
                route.append(visit)
    return route


# Mantém a API existente enquanto aplica a estratégia territorial.
optimize_route = optimize_route_by_territory


def limit_daily_route(morning, afternoon, per_shift=5):
    """Mantém no máximo cinco visitas por turno e dez no roteiro diário."""
    return list(morning)[:per_shift] + list(afternoon)[:per_shift]


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
        
    num_to_generate = 10 - len(existing_visits)
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
    resp_irm = requests.get(url_irmandade, headers=headers, params=[("select", "*")], timeout=10)
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
    
    # 2. Buscar visitas recentes/futuras
    try:
        data_obj = datetime.strptime(data_filtro, "%Y-%m-%d")
    except:
        data_obj = datetime.now()
        
    limite_passado = (data_obj - timedelta(days=15)).strftime("%Y-%m-%dT00:00:00")
    
    params_agenda = [
        ("select", "irmandade_id,status,setor,endereco_visitado,equipe_responsavel,data_inicio"),
        ("data_inicio", f"gte.{limite_passado}")
    ]
    resp_agenda = requests.get(url_agenda, headers=headers, params=params_agenda, timeout=10)
    
    visitados_recentemente = set()
    neighborhood_owners = {}
    if resp_agenda.status_code == 200:
        for v in resp_agenda.json():
            if v.get('status') != 'Cancelada' and v.get('irmandade_id'):
                visitados_recentemente.add(str(v['irmandade_id']))
            if str(v.get('data_inicio') or '')[:10] == data_filtro and v.get('equipe_responsavel'):
                neighborhood_owners.setdefault(neighborhood_key(v), v.get('equipe_responsavel'))
                
    # 3. Filtrar elegíveis e extrair coordenadas
    elegiveis = []
    sem_coords = []
    
    for irmao in todos_irmaos:
        if str(irmao.get('id')) in visitados_recentemente:
            continue
            
        addr = irmao.get('endereco') or ''
        coords = extract_coords_from_address(addr)
        
        item = {
            'irmao': irmao,
            'coords': coords,
            'setor': irmao.get('setor') or ''
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
    if not igreja_coords:
        igreja_coords = (-23.538263, -46.926524)
    for item in elegiveis:
        if item['coords']:
            item['dist'] = haversine_distance(igreja_coords, item['coords'])
        elif 'dist' not in item:
            item['dist'] = 999999 
            
    # Ordenar pela menor distância
    grupos_bairro = {}
    for item in elegiveis:
        key = neighborhood_key(item['irmao'])
        owner = neighborhood_owners.get(key)
        if owner and owner != equipe:
            continue
        grupos_bairro.setdefault(key, []).append(item)

    bairros_atuais = {neighborhood_key(item) for item in existing_visits}
    grupos_ordenados = sorted(grupos_bairro.items(), key=lambda pair: (
        pair[0] not in bairros_atuais,
        min(item['dist'] for item in pair[1]),
        pair[0],
    ))
    selecionados = []
    for _, grupo in grupos_ordenados:
        if len(selecionados) >= num_to_generate:
            break
        grupo.sort(key=lambda item: (
            street_key(item['irmao']), address_number(item['irmao']), item['dist']
        ))
        vagas_restantes = num_to_generate - len(selecionados)
        selecionados.extend(grupo[:vagas_restantes])
    
    if not selecionados:
        return []
        
    # 5. Criar na Agenda
    novas_visitas = []
    
    # Prepara payload em lote (Supabase permite bulk insert)
    payload_bulk = []
    
    # Continuar índice baseado nos existentes
    start_index = len(existing_visits)
    
    for i, item in enumerate(selecionados):
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
            'titulo': irmao.get('nome'),
            'setor': irmao.get('setor'),
            'endereco_visitado': irmao.get('endereco'),
            'categoria': 'GVI',
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
