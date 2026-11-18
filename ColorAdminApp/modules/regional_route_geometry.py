"""Localizacao sob demanda, com cache em disco e sem Redis/Supabase."""
import hashlib
import math
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from django.core.cache.backends.filebased import FileBasedCache
from ColorAdminApp.utils.routing import geocode_address_fallback, get_common_coordinates, haversine_distance, normalize_text, church_origin_reference

cache=FileBasedCache(str(Path(tempfile.gettempdir())/'ccb-route-geolocation-v1'),{'OPTIONS':{'MAX_ENTRIES':10000}})


def valid(coords):
    return (isinstance(coords,(list,tuple)) and len(coords)==2 and
            all(isinstance(n,(int,float)) and math.isfinite(n) for n in coords) and
            -90<=coords[0]<=90 and -180<=coords[1]<=180)


def cached_coordinates(address, city, neighborhood='', common=False):
    reference=church_origin_reference(address,city) if common else None
    identity=(normalize_text(address),normalize_text(city),normalize_text(neighborhood),common)
    if reference:identity+=(normalize_text(reference['address']),)
    key=hashlib.sha256(repr(identity).encode()).hexdigest()
    saved=cache.get(key)
    if saved is not None:return saved['coords']
    coords=get_common_coordinates(address,city) if common else geocode_address_fallback(address,city=city,neighborhood=neighborhood)
    coords=list(coords) if valid(coords) else None
    cache.set(key,{'coords':coords},timeout=90*86400 if coords else 3600)
    return coords


def enrich_plan_geometry(plan):
    """Resolve faltantes sem excluir familias e sem alterar visitas no banco."""
    origins=dict(plan.get('origins') or {})
    for common in plan['commons']:
        if not valid(origins.get(common)):origins[common]=cached_coordinates(common,plan['city'],common=True)
    anchors=[c for c in origins.values() if valid(c)]
    def locate(house):
        coords=house.get('coords')
        if not valid(coords) or (anchors and min(haversine_distance(a,coords) for a in anchors)>20000):
            coords=cached_coordinates(house['address'],plan['city'],house.get('bairro',''))
        if coords and anchors and min(haversine_distance(a,coords) for a in anchors)>20000:coords=None
        house['coords']=list(coords) if valid(coords) else None
    with ThreadPoolExecutor(max_workers=4) as executor:list(executor.map(locate,plan['houses']))
    plan['origins']=origins
    plan['without_coordinates']=sum(not h.get('coords') for h in plan['houses'])
    return plan
