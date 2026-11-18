"""Mapa ficticio identificado para testes sem rede nem consumo de cota Google."""
import io
from PIL import Image,ImageDraw


def offline_map_data(group):
    image=Image.new('RGB',(640,640),'#eef3f8');draw=ImageDraw.Draw(image)
    for n in range(40,640,70):
        draw.line((n,0,n,640),fill='#ffffff',width=7);draw.line((0,n,640,n),fill='#ffffff',width=7)
    draw.text((20,20),'MAPA FICTICIO - TESTE OFFLINE',fill='#1e4b7a')
    output=io.BytesIO();image.save(output,format='PNG')
    points=([{'number':0,'coords':group['origin']}] if group.get('origin') else [])+[
        {'number':h['number'],'coords':h['coords']} for h in group['houses'] if h.get('coords')]
    center=points[0]['coords'] if points else [-23.54,-46.98]
    return {'image':output.getvalue(),'center':center,'zoom':13,'points':points,'route_available':True}
