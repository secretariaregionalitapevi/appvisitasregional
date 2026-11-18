"""Planejamento regional por casas, sem geocodificacao ou consultas externas."""
import hashlib
from statistics import median
from collections import defaultdict
from datetime import datetime, timedelta

from ColorAdminApp.utils.routing import (
    clean_visit_address, extract_coords_from_address, haversine_distance,
    normalize_text, route_address_key, street_key, address_number,
)


def household_key(member):
    address = route_address_key(member)
    # Complementos do endereco fazem parte da identidade da casa.
    return address or 'SEM_ENDERECO:' + str(member['id'])


def spatial_order(houses, origin=None):
    """Proximidade em linha reta com coordenadas existentes; rua/bairro sem GPS."""
    pending = sorted(houses, key=lambda h: (normalize_text(h['bairro']), street_key({'endereco': h['address']}),
                                          address_number({'endereco':h['address']}), h['key']))
    ordered = []
    while pending:
        current = ordered[-1]['coords'] if ordered else origin
        if current:
            next_house = min(pending, key=lambda h: (
                haversine_distance(current, h['coords']) if h['coords'] else float('inf'),
                normalize_text(h['bairro']), h['key']))
        else:
            next_house = pending[0]
        pending.remove(next_house)
        ordered.append(next_house)
    return ordered


def compact_balanced_groups(houses,origins=None):
    """Troca casas afastadas entre grupos, preservando exatamente as cotas."""
    located=[h for h in houses if h.get('coords')]
    if len(located)<3:return
    original={h['key']:h['group_id'] for h in houses}
    def travel():
        total=0
        for identity in {h['group_id'] for h in houses}:
            local=[h for h in houses if h['group_id']==identity]
            represented={m['comum'] for h in local for m in h.get('members',[])}
            candidates=[(haversine_distance(coords,h['coords']),coords) for common,coords in (origins or {}).items()
                        if coords and common in represented for h in local if h.get('coords')]
            current=min(candidates,key=lambda c:c[0])[1] if candidates else None
            for h in spatial_order(local,current):
                if current and h.get('coords'):total+=haversine_distance(current,h['coords'])
                current=h.get('coords')
        return total
    initial_travel=travel() if origins else None
    import math
    latitude=sum(h['coords'][0] for h in located)/len(located)
    scale=math.cos(math.radians(latitude))
    xy={h['key']:(h['coords'][1]*scale,h['coords'][0]) for h in located}
    clusters={}
    for h in located:
        v=clusters.setdefault(h['group_id'],[0.,0.,0]);x,y=xy[h['key']]
        v[0]+=x;v[1]+=y;v[2]+=1
    ordered=sorted(located,key=lambda h:(xy[h['key']],h['key']))
    for _ in range(3):
        changed=False
        for i,a in enumerate(ordered):
            # Recortes grandes usam vizinhos espaciais para limitar o custo.
            candidates=ordered[i+1:] if len(ordered)<=300 else ordered[i+1:i+31]
            for b in candidates:
                if a['group_id']==b['group_id']:continue
                av=clusters[a['group_id']];bv=clusters[b['group_id']]
                ax,ay=xy[a['key']];bx,by=xy[b['key']];dx=bx-ax;dy=by-ay
                gain=((2*(av[0]*dx+av[1]*dy)+dx*dx+dy*dy)/av[2]+
                      (-2*(bv[0]*dx+bv[1]*dy)+dx*dx+dy*dy)/bv[2])
                if gain>1e-12:
                    av[0]+=dx;av[1]+=dy;bv[0]-=dx;bv[1]-=dy
                    a['group_id'],b['group_id']=b['group_id'],a['group_id'];changed=True
        if not changed:break
    if initial_travel is not None and travel()>initial_travel+1e-6:
        for h in houses:h['group_id']=original[h['key']]


def original_route_order(houses,origin):
    """Reutiliza o otimizador do roteiro original a partir da primeira casa."""
    from ColorAdminApp.utils.routing import optimize_linear_route
    ordered=spatial_order(houses,origin)
    if len(ordered)<3 or len(ordered)>80:return ordered
    first=ordered[0]
    visits=[{'_route_coords':h.get('coords'),'_house_index':i} for i,h in enumerate(ordered[1:])]
    optimized=optimize_linear_route(visits,first.get('coords'))
    return [first]+[ordered[1:][v['_house_index']] for v in optimized]


def shortest_period_path(partitions, origin, travel_cost=None):
    """Caminho aberto completo, com todas as casas da manha antes da tarde."""
    combined = [(hour,h) for hour in (9,14) for h in sorted(partitions[hour],key=lambda h:h['key'])]
    n = len(combined)
    if not 0 < n <= 12 or not all(h.get('coords') for _,h in combined):
        return None
    morning_mask = (1 << len(partitions[9])) - 1
    travel_cost=travel_cost or haversine_distance
    distances = [[travel_cost(a['coords'],b['coords']) for _,b in combined] for _,a in combined]
    states = {}
    for index,(hour,house) in enumerate(combined):
        if hour == 9 or not morning_mask:
            states[(1 << index,index)] = (travel_cost(origin,house['coords']) if origin else 0,(index,))
    for mask in range(1,1 << n):
        for last in range(n):
            state = states.get((mask,last))
            if state is None:
                continue
            for nxt,(hour,_) in enumerate(combined):
                if mask & (1 << nxt) or (hour == 14 and (mask & morning_mask) != morning_mask):
                    continue
                key = (mask | (1 << nxt),nxt)
                candidate = (state[0]+distances[last][nxt],state[1]+(nxt,))
                if key not in states or candidate < states[key]:
                    states[key] = candidate
    distance,path = min(states[((1 << n)-1,last)] for last in range(n) if ((1 << n)-1,last) in states)
    return [combined[index] for index in path],distance


def period_route_order(houses, origin, morning_capacity, route_order=None, travel_cost=None):
    """Separa preferencias antes de otimizar o percurso de cada periodo."""
    optimize_transition = route_order is None or travel_cost is not None
    travel_cost=travel_cost or haversine_distance
    route_order = route_order or original_route_order
    periods = {9: [], 14: []}
    flexible = []
    for house in houses:
        preferences = {normalize_text(m.get('preferencia_periodo_visita')) for m in house['members']}
        house['period_conflict'] = {'MANHA', 'TARDE'} <= preferences
        if 'TARDE' in preferences:
            periods[14].append(house)
        elif 'MANHA' in preferences:
            periods[9].append(house)
        else:
            flexible.append(house)
    flexible = spatial_order(flexible, origin)
    explicit = {hour: list(items) for hour, items in periods.items()}
    morning_count = max(0, morning_capacity - len(periods[9]))
    periods[9].extend(flexible[:morning_count])
    periods[14].extend(flexible[morning_count:])
    def sequence(partitions):
        exact = shortest_period_path(partitions, origin, travel_cost) if optimize_transition else None
        if exact is not None:
            return exact
        ordered = []
        current = origin
        distance = 0
        for hour in (9, 14):
            local = route_order(partitions[hour], current)
            ordered.extend((hour, house) for house in local)
            for house in local:
                if current and house.get('coords'):
                    distance += travel_cost(current, house['coords'])
                current = house.get('coords') or current
        return ordered, distance
    best, best_distance = sequence(periods)
    # Sem preferencia, a casa pode acompanhar o bloco geografico mais proximo.
    # Mantem a divisao padrao quando todas as casas sao flexiveis.
    if (explicit[9] or explicit[14]) and 0 < len(flexible) <= 4:
        from itertools import product
        for choices in product((9,14), repeat=len(flexible)):
            candidate = {hour:list(items) for hour,items in explicit.items()}
            for house,hour in zip(flexible,choices):
                candidate[hour].append(house)
            ordered, distance = sequence(candidate)
            if distance < best_distance - 1e-6:
                best, best_distance = ordered, distance
    return best


def compact_period_groups(houses, groups, origins):
    """Troca ou transfere casas para reduzir trajetos mantendo o equilibrio."""
    if not origins or len(groups) < 2:
        return
    if sum(bool(h.get('coords')) for h in houses) > 300:
        return
    original = {h['key']: h['group_id'] for h in houses}
    def local(identity):
        return [h for h in houses if h['group_id'] == identity]
    cost_cache = {}
    def cost(items, origin, exact=False):
        cache_key = (tuple(sorted(h['key'] for h in items)), tuple(origin) if origin else None, exact)
        if cache_key in cost_cache:
            return cost_cache[cache_key]
        current = origin
        total = 0
        for _, house in period_route_order(items, origin, (len(items)+1)//2,
                                          route_order=None if exact else spatial_order):
            if current and house.get('coords'):
                total += haversine_distance(current, house['coords'])
            current = house.get('coords') or current
        cost_cache[cache_key] = total
        return total
    starts = {}
    for group in groups:
        identity = str(group['id'])
        items = local(identity)
        represented = {m['comum'] for h in items for m in h['members']}
        candidates = [(common, coords) for common, coords in origins.items() if coords and common in represented]
        if group.get('origin_common') in represented and origins.get(group['origin_common']):
            starts[identity] = origins[group['origin_common']]
        elif candidates:
            common, coords = min(candidates, key=lambda c: (cost(items, c[1]), c[0]))
            group['origin_common'], group['origin'] = common, coords
            starts[identity] = coords
        else:
            group['origin_common'] = next(iter(sorted(represented)), '')
            group['origin'] = None
            starts[identity] = None
    baseline = sum(cost(local(i), start, exact=True) for i, start in starts.items())
    located = sorted((h for h in houses if h.get('coords')), key=lambda h: (h['coords'], h['key']))
    # O agrupamento inicial continua disponivel em recortes muito grandes;
    # limita as trocas adicionais para nao bloquear a previa.
    if len(located) > 300:
        return
    from time import perf_counter
    search_deadline = perf_counter() + 1.5
    for _ in range(6):
        if perf_counter() >= search_deadline:
            break
        best = None
        items = {identity: local(identity) for identity in starts}
        current_cost = {identity: cost(local(identity), start) for identity, start in starts.items()}
        for index, first in enumerate(located):
            if perf_counter() >= search_deadline:
                break
            candidates = located[index+1:] if len(located)<=100 else located[index+1:index+31]
            for second in candidates:
                if perf_counter() >= search_deadline:
                    break
                a, b = first['group_id'], second['group_id']
                if a == b:
                    continue
                new_a = [h for h in items[a] if h is not first] + [second]
                new_b = [h for h in items[b] if h is not second] + [first]
                gain = current_cost[a] + current_cost[b] - cost(new_a, starts[a]) - cost(new_b, starts[b])
                if gain > 1e-6 and (best is None or gain > best[0] + 1e-6):
                    best = (gain, first, second, a, b)
            # Transferir uma casa de 7 para 6 preserva o equilibrio (6 e 7).
            a = first['group_id']
            for b in starts:
                if len(items[a]) != len(items[b]) + 1:
                    continue
                new_a = [h for h in items[a] if h is not first]
                new_b = items[b] + [first]
                gain = current_cost[a] + current_cost[b] - cost(new_a, starts[a]) - cost(new_b, starts[b])
                if gain > 1e-6 and (best is None or gain > best[0] + 1e-6):
                    best = (gain, first, None, a, b)
        if best is None:
            break
        _, first, second, a, b = best
        first['group_id'] = b
        if second is not None:
            second['group_id'] = a
    if sum(cost(local(i), start, exact=True) for i, start in starts.items()) > baseline + 1e-6:
        for house in houses:
            house['group_id'] = original[house['key']]


def build_plan(members, agenda, teams, day, city, commons, resolved_coordinates=None,route_origins=None):
    """Reequilibra somente visitas regionais marcadas das comuns selecionadas."""
    confirmed = [dict(t) for t in teams if t.get('ativo') and t.get('confirmado')]
    confirmed.sort(key=lambda t: t['nome'])
    if not confirmed:
        raise ValueError('Confirme ao menos um grupo e informe seu coordenador para esta data.')
    if any(not t.get('coordenador_nome', '').strip() for t in confirmed):
        raise ValueError('Informe o coordenador de cada grupo confirmado.')
    by_member = {str(m['id']): m for m in members}
    regional_ids = {str(t['id']) for t in teams}
    regional_names = {normalize_text(t['nome']) for t in teams}
    all_houses = {}
    for member in members:
        if member.get('comum') not in commons:
            continue
        if 'INATIV' in normalize_text(member.get('status')):
            continue
        if any(member.get(k) for k in ('equipe_id','equipe_visita','grupo_regional_id','grupo_regional_nome')):
            continue
        if not clean_visit_address(member.get('endereco')):
            continue
        key = household_key(member)
        h = all_houses.setdefault(key, {
            'key': hashlib.sha256(key.encode()).hexdigest()[:24], 'members': [], 'visit_ids': [],
            'address': clean_visit_address(member.get('endereco')), 'bairro': member.get('setor') or '',
            'coords': extract_coords_from_address(member.get('endereco')), 'last_visit': '',
        })
        h['members'].append({k: member.get(k) or '' for k in ('id','nome','comum','endereco','categoria','preferencia_periodo_visita','apontamentos_restritos')})
        if 'comum_cadastro' in member:
            h['members'][-1]['comum_cadastro'] = member['comum_cadastro']
        h['last_visit'] = max(h['last_visit'], str(member.get('ultima_visita') or '')[:10])
    blocked, fixed, fixed_times, fixed_windows = set(), defaultdict(set), defaultdict(set), defaultdict(list)
    team_by_name = {normalize_text(t['nome']): str(t['id']) for t in teams}
    for visit in agenda:
        member = by_member.get(str(visit.get('irmandade_id')))
        if not member:
            continue
        key = household_key({'id': member['id'], 'endereco': visit.get('endereco_visitado') or member.get('endereco')})
        visit_day = str(visit.get('local_date') or visit.get('data_inicio') or '')[:10]
        status = normalize_text(visit.get('status'))
        regional = str(visit.get('equipe_id')) in regional_ids or normalize_text(visit.get('equipe_responsavel')) in regional_names
        movable = (visit_day == day and status == 'MARCADA' and regional and key in all_houses)
        if movable:
            all_houses[key]['visit_ids'].append(str(visit['id']))
        elif status not in {'CANCELADA','NAO REALIZADA'}:
            if visit_day >= day or (status == 'REALIZADA' and visit_day >= (datetime.fromisoformat(day) - timedelta(days=15)).date().isoformat()):
                blocked.add(key)
                # Uma mudanca de endereco nao libera outra visita para a mesma
                # pessoa enquanto existe atendimento marcado ou recente.
                blocked.add(household_key(member))
            if visit_day == day:
                team_id = str(visit.get('equipe_id') or team_by_name.get(normalize_text(visit.get('equipe_responsavel')), ''))
                fixed[team_id].add(key)
                fixed_times[team_id].add(str(visit.get('data_inicio') or ''))
                fixed_windows[team_id].append([visit.get('data_inicio'),visit.get('data_fim')])
    eligible = [h for key,h in all_houses.items() if key not in blocked]
    # Visitas realizadas nos ultimos 15 dias nao entram de novo pelo campo legado.
    cutoff = (datetime.fromisoformat(day) - timedelta(days=15)).date().isoformat()
    eligible = [h for h in eligible if h['visit_ids'] or not h['last_visit'] or h['last_visit'] < cutoff]
    mandatory = [h for h in eligible if h['visit_ids']]
    pending = sorted((h for h in eligible if not h['visit_ids']), key=lambda h: (h['last_visit'], h['key']))
    # Toda familia elegivel participa. A quantidade resulta da divisao do
    # conjunto selecionado pelos grupos confirmados, sem teto por grupo.
    selected = mandatory + pending
    if resolved_coordinates is not None:
        for house in selected:
            if house['key'] in resolved_coordinates:house['coords']=resolved_coordinates[house['key']]
    loads = {str(t['id']): 0 for t in confirmed}
    located = [h['coords'] for h in selected if h['coords']]
    if len(located) >= 2:
        center = (median(c[0] for c in located), median(c[1] for c in located))
        for house in selected:
            # Coordenadas legadas muito afastadas do conjunto nao orientam o
            # percurso nem o QR. O endereco completo continua disponivel.
            if house['coords'] and haversine_distance(center, house['coords']) > 20000:
                house['coords'] = None
    quotas = {str(t['id']): 0 for t in confirmed}
    for _ in selected:
        team_id = min(loads, key=lambda key: (loads[key], key))
        loads[team_id] += 1
        quotas[team_id] += 1
    ordered = spatial_order(selected)
    position = 0
    for team in confirmed:
        identity = str(team['id'])
        for house in ordered[position:position + quotas[identity]]:
            house['group_id'] = identity
        position += quotas[identity]
        team['fixed_houses'] = len(fixed[identity])
        team['fixed_times'] = sorted(fixed_times[identity])
        team['fixed_windows'] = fixed_windows[identity]
    compact_balanced_groups(ordered,route_origins)
    compact_period_groups(ordered, confirmed, route_origins)
    coverage=[]
    for common in commons:
        records=[m for m in members if m.get('comum')==common]
        included=[m for h in ordered for m in h['members'] if m['comum']==common]
        coverage.append({'common':common,'records':len(records),'included_records':len(included),
            'families':sum(any(m['comum']==common for m in h['members']) for h in ordered),
            'inactive':sum('INATIV' in normalize_text(m.get('status')) for m in records),
            'team_members':sum(any(m.get(k) for k in ('equipe_id','equipe_visita','grupo_regional_id','grupo_regional_nome')) for m in records),
            'without_address':sum(not clean_visit_address(m.get('endereco')) for m in records)})
    return {'date': day, 'city': city, 'commons': commons, 'groups': confirmed,'coverage':coverage,
            'houses': ordered, 'records_in_plan':sum(len(h['members']) for h in ordered),
            'blocked': len(blocked),
            'without_coordinates': sum(not h['coords'] for h in selected)}


def finalize_plan(plan, assignments=None):
    """Valida os grupos dos ajustes manuais e calcula a sequencia completa."""
    groups = {str(t['id']): t for t in plan['groups']}
    if assignments is not None and (not isinstance(assignments, dict) or set(assignments) != {h['key'] for h in plan['houses']}):
        raise ValueError('A lista de casas mudou. Gere uma nova previa.')
    counts = {key: g.get('fixed_houses', 0) for key,g in groups.items()}
    for house in plan['houses']:
        identity = str(assignments[house['key']] if assignments is not None else house['group_id'])
        if identity not in groups:
            raise ValueError('Selecione somente grupos confirmados para esta data.')
        counts[identity] += 1
        house['group_id'] = identity
    for identity, group in groups.items():
        assigned=[h for h in plan['houses'] if h['group_id']==identity]
        origins=plan.get('origins') or {}
        represented={m['comum'] for h in assigned for m in h['members']}
        candidates=[(haversine_distance(coords,h['coords']),common,coords)
                    for common,coords in origins.items() if coords and common in represented
                    for h in assigned if h.get('coords')]
        if group.get('origin_common') in represented and origins.get(group['origin_common']):
            group['origin'] = origins[group['origin_common']]
        elif candidates:
            _,group['origin_common'],group['origin']=min(candidates,key=lambda c:(c[0],c[1]))
        else:
            group['origin_common'] = next(iter(sorted(represented)), '')
            group['origin'] = None
        group['origins']=origins
        morning_capacity = max(0, (counts[identity]+1)//2 - group.get('fixed_houses', 0))
        road_distances=plan.get('road_distances') or {}
        travel_cost=None
        route_order=None
        route_origin=group.get('origin')
        if not route_origin and assigned:
            first=min(assigned,key=lambda h:h.get('number',float('inf')))
            route_origin=first.get('coords')
        if road_distances and assigned:
            from .regional_route_roads import road_key
            points=[h.get('coords') for h in assigned]+([route_origin] if route_origin else [])
            if not all(points) or not all(road_key(a,b) in road_distances for a in points for b in points):
                road_distances={}
        if road_distances and assigned:
            from .regional_route_roads import road_key
            def travel_cost(start,end):
                return road_distances.get(road_key(start,end),haversine_distance(start,end))
            def route_order(items,start):
                pending=sorted(items,key=lambda h:h['key'])
                ordered=[]
                while pending:
                    house=min(pending,key=lambda h:(travel_cost(start,h['coords']) if start and h.get('coords') else float('inf'),h['key']))
                    ordered.append(house);pending.remove(house)
                    start=house.get('coords') or start
                return ordered
        period_houses = period_route_order(assigned, route_origin, morning_capacity,route_order=route_order,travel_cost=travel_cost)
        houses = [house for _, house in period_houses]
        occupied = []
        for beginning, ending in group.get('fixed_windows', []):
            if beginning:
                start_dt = datetime.fromisoformat(beginning.replace('Z','+00:00'))
                end_dt = datetime.fromisoformat(ending.replace('Z','+00:00')) if ending else start_dt+timedelta(minutes=15)
                occupied.append((start_dt,end_dt))
        # A distribuicao nova nao reutiliza horarios das visitas fixas.
        period_slots = {9: 0, 14: 0}
        for index, (hour, house) in enumerate(period_houses):
            delta = period_slots[hour]
            period_slots[hour] += 1
            start = datetime.fromisoformat(plan['date'] + f'T{hour:02}:00:00-03:00') + timedelta(minutes=15*delta)
            while any(start < end_dt and start+timedelta(minutes=15) > start_dt for start_dt,end_dt in occupied):
                start += timedelta(minutes=15)
            occupied.append((start,start+timedelta(minutes=15)))
            house['start'] = start.isoformat()
            house['end'] = (start+timedelta(minutes=15)).isoformat()
            house['number'] = index+1
        houses.sort(key=lambda h: h['start'])
        for number, house in enumerate(houses, 1):
            house['number'] = number
        group['max_leg_meters']=max((haversine_distance(
            group.get('origin') if i==0 else houses[i-1].get('coords'),h.get('coords'))
            for i,h in enumerate(houses) if h.get('coords') and (group.get('origin') if i==0 else houses[i-1].get('coords'))),default=0)
    plan['houses'].sort(key=lambda h: (h['group_id'], h['number']))
    return plan
