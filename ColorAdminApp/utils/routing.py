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
            coords = (float(match.group(1)), float(match.group(2)))
            if all(math.isfinite(value) for value in coords) and -90 <= coords[0] <= 90 and -180 <= coords[1] <= 180:
                return coords
        except (ValueError, TypeError):
            return None
    return None

@lru_cache(maxsize=1024)
def geocode_address_fallback(address, city='', neighborhood=''):
    """
    Geocodifica usando Google Maps ou ArcGIS, exigindo o município informado.
    """
    if not address:
        return None
        
    # Limpa a string de coordenadas se houver
    clean_addr = re.sub(r'^\[.*?\]\s*', '', address)
    clean_addr = ', '.join(filter(None, (clean_addr, neighborhood, city, 'SP, Brasil')))

    def google_matches_city(candidate):
        if not city:
            return True
        components = candidate.get('address_components') or []
        cities = [c.get('long_name') for c in components
                  if {'locality', 'administrative_area_level_2'} & set(c.get('types') or [])]
        states = [c.get('short_name') for c in components if 'administrative_area_level_1' in (c.get('types') or [])]
        precise_types = {'street_address', 'premise', 'subpremise', 'establishment', 'point_of_interest'}
        if not re.search(r'\d', clean_visit_address(address)):
            precise_types.add('route')
        return (normalize_text(city) in {normalize_text(c) for c in cities}
                and 'SP' in states and not candidate.get('partial_match')
                and bool(precise_types & set(candidate.get('types') or [])))
    
    api_key = settings.GOOGLE_MAPS_API_KEY
    if api_key:
        try:
            response = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={"address": clean_addr, "key": api_key, "language": "pt-BR",
                        "components": "country:BR|administrative_area:SP"},
                timeout=5,
            )
            result = response.json()
            if result.get('status') == 'OK':
                for candidate in result.get('results') or []:
                    if google_matches_city(candidate):
                        location = candidate['geometry']['location']
                        return (float(location['lat']), float(location['lng']))
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
                "maxLocations": 5,
                "outFields": "Match_addr,City,RegionAbbr,Country,Addr_type",
            },
            timeout=8,
        )
        response.raise_for_status()
        candidates = response.json().get('candidates') or []
        for candidate in candidates:
            attributes = candidate.get('attributes') or {}
            if city and (normalize_text(attributes.get('City')) != normalize_text(city)
                         or attributes.get('RegionAbbr') != 'SP'
                         or attributes.get('Addr_type') not in {'PointAddress', 'StreetAddress', 'POI'}):
                continue
            if float(candidate.get('score') or 0) >= (85 if city else 60):
                location = candidate['location']
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
        coords = geocode_address_fallback(consulta, city=cidade)
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
        "select": "id,comum,setor,endereco,status", "comum": f"ilike.{comum}", "order": "setor.asc"
    }, timeout=15)
    response.raise_for_status()
    membros = [row for row in response.json() if row.get('setor') and normalize_text(row.get('comum')) == normalize_text(comum)]

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
    centro = get_common_coordinates(comum, cidade)
    grupos = {}
    for membro in membros:
        bairro = str(membro.get('setor') or '').strip()
        if not bairro:
            continue
        chave = normalize_text(bairro)
        grupo = grupos.setdefault(chave, {"nome": bairro, "quantidade": 0, "coords": [], "enderecos": []})
        grupo["quantidade"] += 1
        coords = extract_coords_from_address(membro.get('endereco') or '')
        if cidade and coords and (not centro or haversine_distance(centro, coords) > 15000):
            coords = None
        if coords:
            grupo["coords"].append(coords)
        elif membro.get('endereco'):
            grupo["enderecos"].append(clean_visit_address(membro.get('endereco')))

    grupos_sem_coords = [grupo for grupo in grupos.values() if not grupo["coords"] and grupo["enderecos"]]
    if grupos_sem_coords:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            resultados = executor.map(
                lambda grupo: geocode_address_fallback(grupo["enderecos"][0], city=cidade, neighborhood=grupo['nome']), grupos_sem_coords
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

def resolve_visit_coordinates(address, city='', neighborhood='', origin=None):
    """Rejeita coordenadas legadas incompatíveis com a área da congregação.

    O raio é uma barreira contra erros grosseiros, não prova de endereço.
    Não inventa coordenadas quando o geocodificador não confirma o município.
    """
    coords = extract_coords_from_address(address)
    if coords and (not city or (origin and haversine_distance(origin, coords) <= 15000)):
        return coords
    if city:
        coords = geocode_address_fallback(clean_visit_address(address), city=city, neighborhood=neighborhood)
        if coords and origin and haversine_distance(origin, coords) > 15000:
            return None
        return coords
    return geocode_address_fallback(address)


def get_visit_coordinates(visit):
    """
    Tenta obter coordenadas de uma visita.
    """
    addr = visit.get('endereco_visitado') or ''
    return resolve_visit_coordinates(addr, visit.get('municipio') or '',
                                     visit.get('setor') or '', visit.get('_route_origin'))


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


def update_route_distances(visits, start_coords=None):
    """Recalcula as distâncias sem desfazer a sequência geográfica escolhida."""
    ordered = list(visits or [])
    current_loc = start_coords
    for visit in ordered:
        coords = get_visit_coordinates(visit)
        if coords:
            if current_loc:
                visit['distance_meters'] = haversine_distance(current_loc, coords)
            else:
                visit.pop('distance_meters', None)
            visit['lat'], visit['lng'] = coords
            current_loc = coords
        else:
            for field in ('distance_meters', 'lat', 'lng'):
                visit.pop(field, None)
            current_loc = None
    return ordered


def optimize_linear_route(visits, start_coords=None):
    """Menor caminho aberto por coordenadas para até 12 casas, sem voltar à comum.

    Horários, letras de bairro e números de porta não substituem a geografia.
    Para roteiros maiores, melhora um caminho inicial com inversões de trechos.
    """
    located, missing = [], []
    for source in visits or []:
        visit = dict(source)
        coords = get_visit_coordinates(visit)
        (located if coords else missing).append((visit, coords))
    n = len(located)
    if n < 2:
        return update_route_distances([v for v, _ in located + missing], start_coords)
    distances = [[haversine_distance(a[1], b[1]) for b in located] for a in located]
    start_cost = [haversine_distance(start_coords, v[1]) if start_coords else 0 for v in located]
    if n <= 12:
        states = {(1 << i, i): (start_cost[i], -1, (i,)) for i in range(n)}
        for mask in range(1, 1 << n):
            for last in range(n):
                state = states.get((mask, last))
                if state is None:
                    continue
                for nxt in range(n):
                    if mask & (1 << nxt):
                        continue
                    key = (mask | (1 << nxt), nxt)
                    candidate = state[0] + distances[last][nxt]
                    path = state[2] + (nxt,)
                    if (key not in states or candidate < states[key][0] - 1e-6
                            or (abs(candidate - states[key][0]) <= 1e-6 and path < states[key][2])):
                        states[key] = (candidate, last, path)
        mask = (1 << n) - 1
        last = min(range(n), key=lambda i: (round(states[(mask, i)][0], 6), states[(mask, i)][2]))
        indices = []
        while last != -1:
            indices.append(last)
            previous = states[(mask, last)][1]
            mask ^= 1 << last
            last = previous
        indices.reverse()
    else:
        pending = set(range(n))
        indices = [min(pending, key=lambda i: (start_cost[i], i))]
        pending.remove(indices[0])
        while pending:
            nxt = min(pending, key=lambda i: (distances[indices[-1]][i], i))
            indices.append(nxt)
            pending.remove(nxt)
        def cost(path):
            return start_cost[path[0]] + sum(distances[a][b] for a, b in zip(path, path[1:]))
        improved = True
        while improved:
            improved = False
            for a in range(n - 1):
                for b in range(a + 1, n):
                    candidate = indices[:a] + indices[a:b + 1][::-1] + indices[b + 1:]
                    if cost(candidate) < cost(indices) - 1e-6:
                        indices, improved = candidate, True
    return update_route_distances([located[i][0] for i in indices] + [v for v, _ in missing], start_coords)


def plan_linear_schedule(visits, start_coords=None):
    """Distribui os horários sugeridos existentes pela sequência otimizada."""
    ordered = optimize_linear_route(visits, start_coords)
    slots = sorted(((v.get('data_inicio'), v.get('data_fim')) for v in visits if v.get('data_inicio')), key=lambda slot: str(slot[0]))
    if len(slots) != len(ordered):
        raise ValueError('Todas as casas precisam de horário para reorganizar o roteiro.')
    for visit, (start, end) in zip(ordered, slots):
        visit['data_inicio'], visit['data_fim'] = start, end
    return ordered


def order_route_chronologically(visits, start_coords=None):
    """Ordena pelo horário apenas nos fluxos que explicitamente o solicitam."""
    indexed = list(enumerate(visits or []))
    indexed.sort(key=lambda pair: (
        not bool(pair[1].get('data_inicio')),
        str(pair[1].get('data_inicio') or ''),
        pair[0],
    ))
    return update_route_distances([visit for _, visit in indexed], start_coords)

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



def route_selection_origin(existing_visits, common_origin=None):
    """Usa a primeira parada programada como marco zero temporário da equipe."""
    for visit in order_route_chronologically(list(existing_visits or [])):
        coords = get_visit_coordinates(visit)
        if coords:
            return coords
    return common_origin


def select_coherent_households(household_options, limit, origin=None, equipe='', neighborhood_owners=None):
    """Seleciona a rodada justa e percorre o terreno rua a rua."""
    options = list(household_options or [])
    if limit <= 0 or not options:
        return []

    neighborhood_owners = neighborhood_owners or {}

    def priority_for(option):
        return min(item['priority'] for item in option[2])

    def rotation_bucket(option):
        priority = priority_for(option)
        # Nunca visitadas formam a primeira rodada. Retomadas formam a segunda.
        # Depois, cada quantidade de visitas é uma rodada própria: ninguém com
        # duas visitas passa à frente de quem ainda recebeu apenas uma.
        if priority[0] == 2:
            return (2, priority[1])
        return (priority[0],)

    def coords_for(option):
        coords = [item.get('coords') for item in option[2] if item.get('coords')]
        if not coords:
            return None
        return (
            sum(coord[0] for coord in coords) / len(coords),
            sum(coord[1] for coord in coords) / len(coords),
        )

    def street_for(option):
        return street_key(option[2][0]['irmao'])

    def owner_penalty(option):
        owner = neighborhood_owners.get(option[0])
        return 1 if owner and owner != equipe else 0

    options.sort(key=lambda option: (
        rotation_bucket(option), priority_for(option), owner_penalty(option),
        coords_for(option) is None,
        haversine_distance(origin, coords_for(option)) if origin and coords_for(option) else 0,
        option[0], street_for(option), address_number(option[2][0]['irmao']),
    ))

    # Fecha uma rodada antes de entrar na seguinte. Se a rodada de menor
    # cobertura tem mais casas do que vagas, a escolha dentro dela será
    # territorial; casas de rodadas anteriores continuam obrigatórias.
    groups = {}
    for option in options:
        groups.setdefault(rotation_bucket(option), []).append(option)

    selected = []
    boundary = []
    for bucket in sorted(groups):
        group = groups[bucket]
        remaining = limit - len(selected)
        if remaining <= 0:
            break
        if len(group) <= remaining:
            selected.extend(group)
        else:
            boundary = group
            break

    def order_terrain(items, start_origin, initial_neighborhood='', initial_street=''):
        pending = list(items)
        ordered = []
        current = start_origin
        current_neighborhood = initial_neighborhood
        current_street = initial_street
        while pending:
            pending.sort(key=lambda option: (
                owner_penalty(option),
                bool(current_neighborhood and option[0] != current_neighborhood),
                bool(current_street and street_for(option) != current_street),
                coords_for(option) is None,
                haversine_distance(current, coords_for(option)) if current and coords_for(option) else 0,
                priority_for(option), option[0], street_for(option),
                address_number(option[2][0]['irmao']),
            ))
            chosen = pending.pop(0)
            ordered.append(chosen)
            current = coords_for(chosen) or current
            current_neighborhood = chosen[0]
            current_street = street_for(chosen)
        return ordered

    selected = order_terrain(selected, origin)
    remaining = limit - len(selected)
    if boundary and remaining > 0:
        current_origin = coords_for(selected[-1]) if selected else origin
        current_neighborhood = selected[-1][0] if selected else ''
        current_street = street_for(selected[-1]) if selected else ''
        selected.extend(order_terrain(
            boundary, current_origin, current_neighborhood, current_street
        )[:remaining])

    return order_terrain(selected, origin)

# Mantém a API existente enquanto aplica a estratégia territorial.
optimize_route = optimize_route_by_territory


def limit_daily_route(morning, afternoon, per_shift=5):
    """Mantém todas as casas; cinco por turno é somente referência operacional."""
    morning = list(morning)
    afternoon = list(afternoon)
    # Nunca descarte uma visita que já esteja programada. A meta de 5 + 5
    # orienta o despacho automático, mas excedentes devem aparecer no PDF para
    # que a equipe e a supervisão possam redistribuí-los conscientemente.
    return morning + afternoon


from datetime import datetime, timedelta
import concurrent.futures

def route_household_target(value=10):
    """Valida a quantidade de casas antes de qualquer consulta ou gravação."""
    if not re.fullmatch(r'\d+', str(value)) or not 1 <= int(value) <= 10:
        raise ValueError('Informe uma quantidade inteira de 1 a 10 casas.')
    return int(value)


def auto_dispatch_visits(equipe, data_filtro, existing_visits=None, comum=None, cidade='', bairro=None, equipe_id=None, equipe_tipo=None, target_houses=10):
    """
    Motor de Despacho Automático:
    1. Busca todos os irmãos.
    2. Busca visitas recentes (últimos 15 dias) ou futuras que não estão Canceladas.
    3. Filtra os irmãos que já receberam visita.
    4. Completa a quantidade de casas solicitada, contando endereços distintos.
    5. Salva na agenda para a equipe e retorna.
    """
    target_houses = route_household_target(target_houses)
    from .visit_participation import regional_team_confirmed
    if not regional_team_confirmed(equipe, data_filtro, cidade):
        return []
    if existing_visits is None:
        existing_visits = []
        
    existing_address_keys = {
        route_address_key(visit, fallback=f"__EXISTENTE_{position}")
        for position, visit in enumerate(existing_visits)
    }
    num_to_generate = target_houses - len(existing_address_keys)
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
        "id,nome,comum,setor,endereco,status,categoria,equipe_id,equipe_visita,ultima_visita,"
        "preferencia_periodo_visita,observacoes"
    )
    member_params = [("select", safe_member_fields), ("limit", "10000")]
    if comum:
        member_params.append(("comum", f"ilike.{comum}"))
    resp_irm = requests.get(url_irmandade, headers=headers, params=member_params, timeout=10)
    if resp_irm.status_code != 200:
        raise RuntimeError('Não foi possível consultar os cadastros para gravar o roteiro.')
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
    # Integrantes de equipes de visita não são destinos de atendimento. Muitos
    # usam o endereço da própria comum no cadastro e distorceriam o roteiro.
    todos_irmaos = [
        item for item in todos_irmaos
        if not str(item.get('equipe_id') or item.get('equipe_visita') or '').strip()
    ]
    member_ids_da_comum = {str(item.get('id')) for item in todos_irmaos if item.get('id')}
    
    # 2. Buscar todo o histórico necessário para priorizar corretamente as
    # casas nunca visitadas e, depois, as visitas mais antigas.
    params_agenda = [
        ("select", "irmandade_id,status,setor,endereco_visitado,equipe_responsavel,data_inicio"),
        ("limit", "5000"),
    ]
    resp_agenda = requests.get(url_agenda, headers=headers, params=params_agenda, timeout=10)
    if resp_agenda.status_code != 200:
        raise RuntimeError('Não foi possível conferir a agenda existente. Nenhuma nova visita foi atribuída.')
    
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
    igreja_coords = get_common_coordinates(comum, cidade) if comum else None
    elegiveis = []
    sem_coords = []
    
    for irmao in todos_irmaos:
        addr = irmao.get('endereco') or ''
        coords = extract_coords_from_address(addr)
        if cidade and coords and (not igreja_coords or haversine_distance(igreja_coords, coords) > 15000):
            coords = None
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
            return resolve_visit_coordinates(search_query, cidade, item['setor'], igreja_coords)

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
    # Quando a equipe já possui uma primeira parada, ela passa a ser o marco
    # zero temporário. Assim a expansão continua daquele ponto, sem obrigar um
    # retorno artificial à congregação antes de cobrir as ruas adjacentes.
    selection_origin = route_selection_origin(existing_visits, igreja_coords)
    selected_households = [
        (address_key, household)
        for _, address_key, household in select_coherent_households(
            household_options,
            num_to_generate,
            origin=selection_origin,
            equipe=equipe,
            neighborhood_owners=neighborhood_owners,
        )
    ]
    
    if not selected_households:
        return []
        
    # 5. Criar na Agenda
    novas_visitas = []
    
    # Prepara payload em lote (Supabase permite bulk insert)
    payload_bulk = []
    
    # Reserva os horários já ocupados, inclusive ao aumentar de 6 para 7 casas.
    # Distribui o total entre manhã e tarde sem mover agendamentos existentes.
    from dateutil import parser
    from zoneinfo import ZoneInfo
    occupied_times = set()
    for visit in existing_visits:
        if visit.get('data_inicio'):
            try:
                dt = parser.parse(visit['data_inicio'])
                if dt.tzinfo:
                    dt = dt.astimezone(ZoneInfo('America/Sao_Paulo'))
                occupied_times.add(dt.strftime('%Y-%m-%dT%H:%M:%S'))
            except (ValueError, TypeError):
                pass
    morning_target = (target_houses + 1) // 2
    available_times = []
    for slot in range(target_houses):
        hour, position = (9, slot) if slot < morning_target else (14, slot - morning_target)
        start = datetime.strptime(f'{data_filtro} {hour:02}:00:00', '%Y-%m-%d %H:%M:%S') + timedelta(minutes=15 * position)
        if start.strftime('%Y-%m-%dT%H:%M:%S') not in occupied_times:
            available_times.append(start)
    # Agendamentos legados podem ocupar vários horários para a mesma casa.
    # Preserve-os e encontre vagas adicionais em vez de reutilizar um horário.
    extra_position = target_houses - morning_target
    while len(available_times) < num_to_generate:
        start = datetime.strptime(f'{data_filtro} 14:00:00', '%Y-%m-%d %H:%M:%S') + timedelta(minutes=15 * extra_position)
        extra_position += 1
        if start.strftime('%Y-%m-%dT%H:%M:%S') not in occupied_times:
            available_times.append(start)
    
    for i, (_, household) in enumerate(selected_households):
        item = household[0]
        irmao = item['irmao']
        
        hora_inicio = available_times[i]
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
            'endereco_visitado': (
                f"[{item['coords'][0]}, {item['coords'][1]}] {clean_visit_address(irmao.get('endereco'))}"
                if item['coords'] else clean_visit_address(irmao.get('endereco'))
            ),
            'categoria': irmao.get('categoria') or 'GVI',
            'equipe_responsavel': equipe,
            'equipe_id': equipe_id,
            'equipe_tipo': equipe_tipo,
            'data_inicio': str_inicio,
            'data_fim': str_fim,
            'status': 'Marcada',
            'observacoes': ''
        }
        payload_bulk.append(visit)
    # Já grava novas casas na ordem espacial, antes de associar os horários.
    planning = [{**visit, 'municipio': cidade, '_route_origin': igreja_coords} for visit in payload_bulk]
    planned = plan_linear_schedule(planning, igreja_coords)
    payload_bulk = [{key: visit[key] for key in payload_bulk[0]} for visit in planned]

    # Bulk insert
    post_headers = headers.copy()
    post_headers["Prefer"] = "return=representation"
    resp_post = requests.post(url_agenda, headers=post_headers, json=payload_bulk, timeout=10)
    
    if resp_post.status_code in [200, 201]:
        created = resp_post.json()
        if not isinstance(created, list) or len(created) != len(payload_bulk):
            raise RuntimeError('A gravação do roteiro não foi confirmada integralmente. Consulte a agenda antes de tentar novamente.')
        # Campos apenas em memória para que a auditoria de escopo também funcione
        # enquanto a agenda mantém o vínculo territorial pelo irmandade_id.
        for visit in created:
            visit['comum'] = comum or ''
            visit['municipio'] = cidade or ''
        return created
        
    raise RuntimeError('Falha ao gravar o roteiro na agenda. Nenhuma visita foi confirmada; consulte a agenda antes de tentar novamente.')
