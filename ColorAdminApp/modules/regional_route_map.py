"""Mapa Google de ruas para o PDF, com pins numerados e percurso rodoviario."""
import hashlib
import io
import math

import requests
from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable

from .regional_route_geometry import cache


def mercator(coords):
    lat,lng=coords
    sin=math.sin(math.radians(max(-85.05112878,min(85.05112878,lat))))
    return ((lng+180)/360,.5-math.log((1+sin)/(1-sin))/(4*math.pi))


def camera(points,size=640):
    projected=[mercator(p) for p in points]
    low_x=min(p[0] for p in projected);high_x=max(p[0] for p in projected)
    low_y=min(p[1] for p in projected);high_y=max(p[1] for p in projected)
    span=max(high_x-low_x,high_y-low_y)
    zoom=max(2,min(19,math.floor(math.log2((size-90)/(256*span))))) if span else 17
    x=(low_x+high_x)/2;y=(low_y+high_y)/2
    lat=math.degrees(math.atan(math.sinh(math.pi*(1-2*y))))
    return (lat,x*360-180),zoom


def google_route_map(group):
    key=settings.GOOGLE_MAPS_API_KEY
    if not key:raise ValueError('A chave Google Maps existente precisa estar configurada para incluir o mapa de ruas.')
    points=([{'number':0,'coords':group['origin']}] if group.get('origin') else [])+[
        {'number':h['number'],'coords':h['coords']} for h in group['houses'] if h.get('coords')]
    if not points:raise ValueError('Nenhum endereço teve localização confirmada para o mapa de ruas.')
    identity=hashlib.sha256(repr([(p['number'],p['coords']) for p in points]).encode()).hexdigest()
    saved=cache.get('street-map-v1-'+identity)
    if saved is not None:return saved
    paths=[];bounds=[];route_available=len(points)<=1
    # Mesma sequencia do roteiro, sem optimizeWaypoints nem retorno a igreja.
    for start in range(0,len(points)-1,10):
        batch=points[start:start+11]
        params={'origin':','.join(map(str,batch[0]['coords'])),'destination':','.join(map(str,batch[-1]['coords'])),
                'waypoints':'|'.join(','.join(map(str,p['coords'])) for p in batch[1:-1]),
                'mode':'driving','language':'pt-BR','key':key}
        try:
            response=requests.get('https://maps.googleapis.com/maps/api/directions/json',params=params,timeout=(3.05,20))
            response.raise_for_status();result=response.json()
            if result.get('status')!='OK' or not result.get('routes'):continue
            route=result['routes'][0]
            polyline=route.get('overview_polyline',{}).get('points')
            if polyline:paths.append('color:0x1e4b7aff|weight:4|enc:'+polyline)
            for corner in ('northeast','southwest'):
                value=route.get('bounds',{}).get(corner)
                if value:bounds.append([value['lat'],value['lng']])
        except (requests.RequestException,ValueError,KeyError):continue
    route_available=len(paths)==math.ceil((len(points)-1)/10) if len(points)>1 else True
    center,zoom=camera([p['coords'] for p in points]+bounds)
    params=[('center',','.join(map(str,center))),('zoom',str(zoom)),('size','640x640'),('scale','2'),
            ('maptype','roadmap'),('language','pt-BR'),('style','feature:poi.place_of_worship|element:labels.icon|visibility:off'),('key',key)]
    params.extend(('path',path) for path in paths)
    try:
        response=requests.get('https://maps.googleapis.com/maps/api/staticmap',params=params,timeout=(3.05,25))
        response.raise_for_status()
        if not response.headers.get('content-type','').startswith('image/'):
            raise ValueError('O Google Maps não retornou uma imagem de mapa de ruas.')
        result={'image':response.content,'center':center,'zoom':zoom,'points':points,'route_available':route_available}
    except requests.RequestException as exc:
        raise ValueError('Não foi possível carregar o mapa Google de ruas. Tente novamente ou exporte somente os cartões.') from None
    cache.set('street-map-v1-'+identity,result,timeout=900)
    return result


class GoogleStreetMap(Flowable):
    def __init__(self,data,width,height=None):
        super().__init__();self.data=data;self.width=width;self.height=height or width

    def draw(self):
        c=self.canv;c.saveState()
        c.drawImage(ImageReader(io.BytesIO(self.data['image'])),0,0,width=self.width,height=self.height,mask='auto')
        origin_x,origin_y=mercator(self.data['center']);world=256*2**self.data['zoom']
        positions=[]
        for point in self.data['points']:
            x,y=mercator(point['coords']);positions.append(((320+(x-origin_x)*world)/640*self.width,(320-(y-origin_y)*world)/640*self.height))
        display=list(positions);pending=set(range(len(positions)))
        while pending:
            first=min(pending);pending.remove(first);cluster=[first];queue=[first]
            while queue:
                current=queue.pop()
                for candidate in sorted(pending):
                    if math.dist(positions[current],positions[candidate])<26:
                        pending.remove(candidate);cluster.append(candidate);queue.append(candidate)
            if len(cluster)>1:
                cx=sum(positions[i][0] for i in cluster)/len(cluster);cy=sum(positions[i][1] for i in cluster)/len(cluster)
                radius=max(18,13/math.sin(math.pi/len(cluster)))
                for index,i in enumerate(cluster):
                    angle=-math.pi/2+index*2*math.pi/len(cluster);display[i]=(cx+radius*math.cos(angle),cy+radius*math.sin(angle))
        for point,actual,position in zip(self.data['points'],positions,display):
            px,py=position
            if actual!=position:
                c.setStrokeColor(colors.HexColor('#6c7a86'));c.setLineWidth(.5);c.line(*actual,px,py)
            py+=11
            # Pin neutro de localizacao; o mesmo numero do cartao, inclusive >9.
            c.setFillColor(colors.HexColor('#1e4b7a' if point['number']==0 else '#e53935'))
            c.setStrokeColor(colors.white);c.setLineWidth(1.2)
            path=c.beginPath();path.moveTo(px,py-11);path.curveTo(px-4,py-6,px-10,py,px-10,py+6)
            path.curveTo(px-10,py+19,px+10,py+19,px+10,py+6);path.curveTo(px+10,py,px+4,py-6,px,py-11);path.close()
            c.drawPath(path,fill=1,stroke=1)
            c.setFillColor(colors.white);c.setFont('Helvetica-Bold',8 if point['number']<100 else 6)
            c.drawCentredString(px,py+4,str(point['number']))
        c.restoreState()
