"""Distancias direcionais pelas ruas, em lotes pequenos e com cache."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from time import monotonic

import requests
from django.conf import settings
from .regional_route_geometry import cache, valid


def point_key(point):
    return ','.join(f'{float(value):.7f}' for value in point)


def road_key(start, end):
    return point_key(start)+'>'+point_key(end)


def road_matrix(points,deadline=None):
    points=sorted({point_key(point) for point in points if valid(point)})
    if len(points)<2 or len(points)>20:
        return {}
    identity='regional-roads-v1-'+hashlib.sha256('|'.join(points).encode()).hexdigest()
    saved=cache.get(identity)
    if saved is not None:return saved
    result={}
    # No maximo 100 elementos por requisicao; sem consultas por par de casas.
    batch_size=max(1,100//len(points))
    try:
        for offset in range(0,len(points),batch_size):
            if deadline is not None and monotonic()>=deadline:return {}
            origins=points[offset:offset+batch_size]
            response=requests.get('https://maps.googleapis.com/maps/api/distancematrix/json',params={
                'origins':'|'.join(origins),'destinations':'|'.join(points),
                'mode':'driving','language':'pt-BR','key':settings.GOOGLE_MAPS_API_KEY},timeout=(2,5))
            response.raise_for_status()
            data=response.json()
            if data.get('status')!='OK' or len(data.get('rows',[]))!=len(origins):return {}
            for start,row in zip(origins,data['rows']):
                if len(row.get('elements',[]))!=len(points):return {}
                for end,element in zip(points,row['elements']):
                    distance=element.get('distance',{}).get('value')
                    if element.get('status')!='OK' or not isinstance(distance,(int,float)) or distance<0:return {}
                    result[start+'>'+end]=distance
    except (requests.RequestException,ValueError,TypeError,KeyError):
        return {}
    cache.set(identity,result,timeout=86400)
    return result


def enrich_road_distances(plan):
    if not settings.GOOGLE_MAPS_API_KEY:
        plan['road_routing_fallback_groups']=[g['nome'] for g in plan['groups'] if sum(str(h['group_id'])==str(g['id']) for h in plan['houses'])>=2]
        return plan
    deadline=monotonic()+12
    def resolve(group):
        houses=[h for h in plan['houses'] if str(h['group_id'])==str(group['id'])]
        if len(houses)<2 or not all(valid(h.get('coords')) for h in houses):return {}
        points=[h['coords'] for h in houses]
        if valid(group.get('origin')):points.append(group['origin'])
        return road_matrix(points,deadline)
    with ThreadPoolExecutor(max_workers=3) as executor:
        matrices=list(executor.map(resolve,plan['groups']))
    plan['road_distances']={key:value for matrix in matrices for key,value in matrix.items()}
    plan['road_routing_groups']=sum(bool(matrix) for matrix in matrices)
    plan['road_routing_fallback_groups']=[g['nome'] for g,matrix in zip(plan['groups'],matrices)
        if not matrix and sum(str(h['group_id'])==str(g['id']) for h in plan['houses'])>=2]
    return plan
