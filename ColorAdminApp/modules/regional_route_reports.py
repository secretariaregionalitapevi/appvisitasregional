"""Navegacao e QR locais para os roteiros, sem enviar enderecos a terceiros."""
import base64
import io
import re
import unicodedata
from datetime import datetime
from html import escape
from urllib.parse import urlencode

from django.urls import reverse
from reportlab.graphics import renderSVG
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing


def actor_name(request):
    profile=request.session.get('user_profile') or {}
    return next((profile[k] for k in ('full_name','nome','name','username','email') if profile.get(k)), 'Usuário')


def route_filename(plan, group):
    """Nome estavel por grupo, usando as comuns efetivamente atendidas."""
    commons = list(dict.fromkeys(m['comum'] for h in group['houses'] for m in h['members']))
    def safe(value):
        value = re.sub(r'^BR-\d{2}-\d{4}\s*-\s*', '', str(value))
        value = unicodedata.normalize('NFKD', value).encode('ascii','ignore').decode()
        return re.sub(r'[^A-Z0-9]+','_',value.upper()).strip('_')
    place = '_E_'.join(safe(c) for c in commons) or safe(plan['city'])
    return f'ROTEIRO_VISITAS_{place[:135]}_{safe(group["nome"])}.pdf'


def decorate_groups(groups):
    """Adapta snapshots antigos sem consultar novamente os cadastros."""
    for group in groups:
        group['houses'].sort(key=lambda h: (str(h.get('start') or ''), h.get('number', 0)))
        for number, house in enumerate(group['houses'], 1):
            house['number'] = number
        group['commons'] = list(dict.fromkeys(m['comum'] for h in group['houses'] for m in h['members']))
        origins=group.get('origins') or {}
        group['origin_common']=(group.get('origin_common') if group.get('origin_common') in group['commons'] and origins.get(group.get('origin_common')) else
            next((c for c in group['commons'] if origins.get(c)),next(iter(group['commons']),'')))
        group['origin']=origins.get(group['origin_common'])
        previous_coords=group['origin']
        for index,house in enumerate(group['houses']):
            house.pop('distance_meters',None)
            if previous_coords and house.get('coords'):
                from ColorAdminApp.utils.routing import haversine_distance
                house['distance_meters']=haversine_distance(previous_coords,house['coords'])
            house['distance_from']='da congregação' if index==0 else 'do último ponto'
            house['distance_label']=(f'{house["distance_meters"]:.0f} m {house["distance_from"]}'
                if house.get('distance_meters') is not None else 'Distância indisponível - localização não confirmada')
            house['time'] = str(house.get('start',''))[11:16]
            house['period'] = 'Manhã' if house['time'] < '12:00' else 'Tarde'
            house['categories'] = list(dict.fromkeys(m.get('categoria') or 'GVI' for m in house['members']))
            house['preferences'] = list(dict.fromkeys(m.get('preferencia_periodo_visita') for m in house['members'] if m.get('preferencia_periodo_visita')))
            house['preference_label']=' / '.join('Prefere '+p.lower() for p in house['preferences']) if house['preferences'] else 'Sem preferência informada'
            previous_coords=house.get('coords')


def build_group_pdf(plan, group, request, historical=False, include_map=True):
    """PDF vetorial compacto, com os cartoes e hierarquia do roteiro original."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, KeepTogether, PageBreak
    from reportlab.platypus import HRFlowable
    from .regional_route_pdf_components import RoundedBadge,RoundedVisitCard,icon
    decorate_groups([group])
    buffer = io.BytesIO()
    blue=colors.HexColor('#1e4b7a'); pale=colors.HexColor('#eaf2f8')
    style=ParagraphStyle('route',fontName='Helvetica',fontSize=9,leading=12,textColor=colors.HexColor('#243746'))
    small=ParagraphStyle('small',parent=style,fontSize=7.5,leading=10)
    title=ParagraphStyle('title',parent=style,fontName='Helvetica-Bold',fontSize=11,leading=14)
    def para(value,st=style):return Paragraph(value,st)
    def e(value):return escape(str(value or ''))
    date_label='/'.join(reversed(plan['date'].split('-')))
    issued=plan.get('issued_at') or datetime.now().strftime('%d/%m/%Y %H:%M')
    width,height=A4
    margin=26; usable=width-2*margin
    # Lateral simetrica pequena preserva a largura do titulo em A4 retrato.
    side=106; center=usable-2*side
    header_height=94
    def page_header(canvas,doc):
        canvas.saveState()
        header=Table([['',para('<b>CONGREGAÇÃO CRISTÃ NO BRASIL</b><br/><font size="9">Regional Itapevi - São Paulo</font><br/><font size="12" color="#1e4b7a"><b>VISITAS</b></font><br/><font size="9">Roteiro Otimizado de Visitas</font>',ParagraphStyle('institution',parent=style,fontSize=15,leading=14,alignment=1)),
            para(f'Página {doc.page}<br/><b>Emissão:</b> {e(issued)}<br/><b>Localidade:</b> {e(plan["city"])}<br/><b>Data das visitas:</b> {date_label}<br/><b>Responsável:</b><br/>Grupo de Visitas Regional',ParagraphStyle('meta',parent=small,fontSize=6.8,leading=9.8,alignment=2))]],colWidths=[side,center,side])
        header.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0)]))
        _,hh=header.wrap(usable,110);header.drawOn(canvas,margin,height-24-hh)
        if doc.page>1:
            canvas.setStrokeColor(blue);canvas.line(margin,height-header_height,width-margin,height-header_height)
        canvas.setFont('Helvetica',7);canvas.setFillColor(blue)
        canvas.drawString(margin,19,f'Visitas - {plan["city"]} - {date_label}')
        footer=para(f'<b>Impresso por:</b> {e(actor_name(request))} - Página {doc.page}',ParagraphStyle('footer',parent=small,alignment=2))
        footer.wrap(usable,20);footer.drawOn(canvas,margin,18)
        canvas.restoreState()
    doc=SimpleDocTemplate(buffer,pagesize=A4,leftMargin=margin,rightMargin=margin,topMargin=header_height+6,bottomMargin=35,title=route_filename(plan,group)[:-4],author='Grupo de Visitas Regional')
    story=[]
    story.extend([para(f'Partida: {e(group["origin_common"])}',ParagraphStyle('departure',parent=style,alignment=1,fontSize=10)),Spacer(1,5)])
    badges=Table([[RoundedBadge(e(group['nome']),96,fill='#348fe2',color='#ffffff',border=None,symbol='users',size=10,padding=6,radius=3,center=True),'',RoundedBadge(date_label,112,fill='#303941',color='#ffffff',border=None,symbol='calendar',size=10,padding=6,radius=3,center=True)]],colWidths=[96,14,112],hAlign='CENTER')
    badges.setStyle(TableStyle([('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
    story.extend([badges,Spacer(1,5),para(f'<b>Coordenador:</b> {e(group.get("coordenador_nome"))}<br/><b>Comuns atendidas:</b> {e(" / ".join(group["commons"]))} &nbsp; | &nbsp; <b>{len(group["houses"])} famílias</b>',ParagraphStyle('route-context',parent=small,alignment=1)),Spacer(1,6),HRFlowable(width='100%',thickness=1.5,color=blue),Spacer(1,6)])
    if historical:story.extend([para('<b>HISTÓRICO SUBSTITUÍDO - não utilizar para novas visitas.</b>',small),Spacer(1,8)])
    if plan.get('export_preview'):story.extend([para('<b>PRÉVIA REORDENADA:</b> sequência calculada com GPS. Confirme o planejamento para atualizar a agenda.',small),Spacer(1,8)])
    last_period=None
    for house in group['houses']:
        block=[]
        if house['period']!=last_period:
            period_icon='sun' if house['period']=='Manhã' else 'coffee'
            divider=RoundedBadge(f'PERÍODO DA {house["period"].upper()}',usable,fill='#f0f4f8',color='#1e4b7a',border=None,symbol=period_icon,size=9,padding=5,radius=3,center=True,symbol_color='#f59c1a' if period_icon=='sun' else '#1e4b7a')
            block.extend([divider,Spacer(1,6)]);last_period=house['period']
        info=[]
        for member in house['members']:
            info.append(para(f'<b>{e(member["nome"])}</b>',title))
            info.append(para(f'<font color="#1e4b7a"><b>Comum do cadastro:</b> {e(member["comum"])}</font>',small))
        info.append(para(f'{icon("pin","#ff5b65")} &nbsp; {e(house["address"])}',ParagraphStyle('address',parent=small,fontSize=8,leading=11)))
        labels=[(house['time'],'#eef2f5','#243746')]+([('Setor: '+house['bairro'],'#eef2f5','#243746')] if house.get('bairro') else [])+[(v,'#348fe2','#ffffff') for v in house['categories']]+[('Prefere '+p.lower(),'#ffb43b','#342511') for p in house['preferences']]
        labels.append((house['distance_label'],'#f0fbff','#188aab'))
        if not house['preferences']:labels.insert(-1,('Sem preferência informada','#fff5df','#8b6518'))
        symbols=['clock']+(['map'] if house.get('bairro') else [])+['tag']*len(house['categories'])+['sun']*len(house['preferences'])+['route']
        if not house['preferences']:symbols.insert(-1,'sun')
        from reportlab.pdfbase.pdfmetrics import stringWidth
        tag_rows=[];current=[];used=0;max_width=usable-128
        for label,symbol in zip(labels,symbols):
            size=min(max_width,stringWidth(label[0],'Helvetica-Bold',6.8)+21)
            if current and used+size+3>max_width:tag_rows.append(current);current=[];used=0
            current.append((label,size,symbol));used+=size+4
        if current:tag_rows.append(current)
        for portion in tag_rows:
            cells=[];widths=[]
            for (text,bg,fg),size,symbol in portion:
                if cells:cells.append('');widths.append(4)
                border=('#348fe2' if symbol=='tag' else '#ffb43b' if symbol=='sun' else '#48b5db' if symbol=='route' else '#c8d1da')
                cells.append(RoundedBadge(e(text),size,fill=bg,color=fg,border=border,symbol=symbol,padding=3,radius=2))
                widths.append(size)
            tags=Table([cells],colWidths=widths,hAlign='LEFT')
            tags.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0)]))
            info.extend([Spacer(1,3),tags])
        if house.get('period_conflict') or any(m.get('apontamentos_restritos') for m in house['members']):
            info.append(Spacer(1,5))
        if house.get('period_conflict'):info.append(para('<font color="#c0392b"><b>Confirmar horário:</b> preferências diferentes neste endereço.</font>',small))
        for member in house['members']:
            if member.get('apontamentos_restritos'):info.append(para('<font color="#ff404b">'+icon('shield')+' <b>Apontamento especial:</b> '+e(member['apontamentos_restritos'])+'</font>',small))
        qr=QrCodeWidget(house['navigation_url']);bounds=qr.getBounds();drawing=Drawing(62,62,transform=[62/(bounds[2]-bounds[0]),0,0,62/(bounds[3]-bounds[1]),0,0]);drawing.add(qr)
        qr_block=Table([[drawing],[para('ESCANEAR E<br/>ESCOLHER GPS',ParagraphStyle('qr',parent=small,fontSize=5.8,leading=7,alignment=1))]],colWidths=[72])
        qr_block.setStyle(TableStyle([('ALIGN',(0,0),(-1,-1),'CENTER'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,1),(0,1),3)]))
        card=Table([[para(f'<font color="#1e4b7a"><b>#{house["number"]}</b></font>',ParagraphStyle('visit-number',parent=title,fontSize=9)),info,qr_block]],colWidths=[28,usable-112,84])
        card.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('TOPPADDING',(0,0),(-1,-1),8),('BOTTOMPADDING',(0,0),(-1,-1),8),
                                 ('LEFTPADDING',(2,0),(2,0),-6),('RIGHTPADDING',(2,0),(2,0),18)]))
        block.extend([RoundedVisitCard(card,usable,background='#f4f6f8' if house['number']%2==0 else '#fdfdfd',qr_width=84),Spacer(1,7)]);story.append(KeepTogether(block))
    if not group['houses']:story.append(para('Nenhuma família atribuída a este grupo nesta distribuição.'))
    story.extend([Spacer(1,10),para('Distâncias aproximadas em linha reta. A primeira parte da congregação indicada; as seguintes partem da casa anterior. O GPS calcula o trajeto pelas ruas.',small)])
    points=[{'number':h['number'],'coords':h['coords']} for h in group['houses'] if h.get('coords')]
    if include_map and points:
        from .regional_route_map import GoogleStreetMap,google_route_map
        map_data=google_route_map(group)
        story.extend([PageBreak(),para('Rota rodoviária Google Maps',title),Spacer(1,8),
            para(f'<b>{e(group["nome"])}</b> - {date_label}<br/><b>Coordenador:</b> {e(group.get("coordenador_nome"))}<br/>{e(" / ".join(group["commons"]))}',small),Spacer(1,12),
            GoogleStreetMap(map_data,usable),Spacer(1,9)])
        caption=('Percurso rodoviário calculado pelo Google na sequência dos cartões.' if map_data['route_available'] else
                 'Mapa de ruas Google. O traçado rodoviário não foi confirmado; utilize o GPS para o percurso.')
        story.append(para(caption+' Marco 0 = congregação de partida. Os demais números correspondem às casas.',small))
        if len(points)<len(group['houses']):story.append(para(f'<b>Atenção:</b> {len(group["houses"])-len(points)} endereço(s) sem localização confirmada não aparecem no mapa, mas permanecem no roteiro.',small))
    doc.build(story,onFirstPage=page_header,onLaterPages=page_header)
    return buffer.getvalue()


def build_workbook(plan, groups, request):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    book=Workbook();sheet=book.active;sheet.title='Roteiros por grupo'
    headers=['Grupo','Coordenador','Ordem','Família','Comum do cadastro','Endereço','Bairro','Data','Horário','Categoria','Preferência']
    rows=[['CONGREGAÇÃO CRISTÃ NO BRASIL'],['Regional Itapevi - São Paulo | Visitas'],['Roteiros de visitas - '+plan['city']+' - '+ '/'.join(reversed(plan['date'].split('-')))],['Responsável: Secretaria Regional da Música | Emissão: '+str(plan.get('issued_at') or '')],headers]
    for group in groups:
        for house in group['houses']:
            for member in house['members']:
                rows.append([group['nome'],group.get('coordenador_nome',''),house['number'],member['nome'],member['comum'],house['address'],house.get('bairro',''),datetime.fromisoformat(plan['date']),str(house.get('start',''))[11:16],member.get('categoria') or 'GVI',member.get('preferencia_periodo_visita','')])
    for row in rows:sheet.append(row)
    for row in range(1,5):sheet.merge_cells(start_row=row,start_column=1,end_row=row,end_column=len(headers))
    for row in (1,2,5):
        for cell in sheet[row]:cell.fill=PatternFill('solid',fgColor='1e4b7a');cell.font=Font(color='FFFFFF',bold=True)
    for row in sheet.iter_rows(min_row=6):
        for cell in row:
            if cell.data_type=='f':cell.data_type='s'
            cell.alignment=Alignment(vertical='top',wrap_text=True)
            if cell.row%2==0:cell.fill=PatternFill('solid',fgColor='f4f6f8')
        row[7].number_format='dd/mm/yyyy'
    for i,width in enumerate([16,30,9,32,38,45,25,14,12,16,16],1):sheet.column_dimensions[get_column_letter(i)].width=width
    sheet.freeze_panes='A6';sheet.auto_filter.ref=f'A5:K{sheet.max_row}';sheet.sheet_view.showGridLines=False
    sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A4;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0;sheet.sheet_properties.pageSetUpPr.fitToPage=True
    sheet.print_title_rows='1:5';sheet.print_options.horizontalCentered=True
    sheet.oddFooter.left.text='Regional Itapevi - Visitas';sheet.oddFooter.right.text='&BImpresso por:&B '+actor_name(request).replace('&','&&')+' - Página &P de &N'
    result=io.BytesIO();book.save(result);return result.getvalue()


def prepare_navigation(groups, city, request):
    base = request.build_absolute_uri(reverse('ColorAdminApp:visitasNavegar'))
    for group in groups:
        for house in group['houses']:
            coords = house.get('coords')
            params = {'lat':coords[0],'lng':coords[1]} if coords else {
                'endereco': ', '.join(filter(None,[house['address'],house.get('bairro'),city,'SP, Brasil']))[:300],
            }
            url = base + '?' + urlencode(params)
            widget = QrCodeWidget(url)
            bounds = widget.getBounds()
            drawing = Drawing(80,80,transform=[80/(bounds[2]-bounds[0]),0,0,80/(bounds[3]-bounds[1]),0,0])
            drawing.add(widget)
            svg = renderSVG.drawToString(drawing)
            house['navigation_url'] = url
            house['qr_data'] = 'data:image/svg+xml;base64,' + base64.b64encode(svg.encode()).decode()


def original_route_context(plan,group,request,map_mode='google',historical=False):
    """O mesmo template do roteiro anterior, adaptado ao snapshot por grupo."""
    from django.conf import settings
    decorate_groups([group])
    visits=[]
    for house in group['houses']:
        coords=house.get('coords')
        visits.append({'titulo':' / '.join(m['nome'] for m in house['members']),
            'comum':' / '.join(dict.fromkeys(m['comum'] for m in house['members'])),
            'endereco_exibicao':house['address'],'setor':house.get('bairro',''),
            'categoria':' / '.join(house['categories']),'data_inicio':house.get('start',''),
            'preferencia_periodo_visita':' / '.join(house['preferences']),
            'preferencia_exibicao':house['preference_label'],
            'apontamentos_restritos':' / '.join(m['apontamentos_restritos'] for m in house['members'] if m.get('apontamentos_restritos')),
            'distance_meters':house.get('distance_meters'),'distance_label':house['distance_label'],
            'route_number':house['number'],'route_period':'manha' if house['period']=='Manhã' else 'tarde',
            'qr_url':house['qr_data'],'lat':coords[0] if coords else None,'lng':coords[1] if coords else None})
    origin=group.get('origin')
    return {'roteiro':visits,'equipe':group['nome'],'comum':group['origin_common'],
        'data':'/'.join(reversed(plan['date'].split('-'))),'emissao_roteiro':plan.get('issued_at',''),
        'regional_snapshot':True,'regional_coordenador':group.get('coordenador_nome',''),
        'regional_common_names':' / '.join(group['commons']),'regional_historical':historical,
        'regional_printed_by':actor_name(request),'regional_city':plan['city'],
        'total_visitas_roteiro':len(visits),'meta_casas':len(visits),'meta_manha':sum(v['route_period']=='manha' for v in visits),
        'meta_tarde':sum(v['route_period']=='tarde' for v in visits),'route_map_mode':map_mode,
        'google_maps_api_key':settings.GOOGLE_MAPS_API_KEY if map_mode=='google' else '',
        'route_map_origin':{'lat':origin[0],'lng':origin[1]} if origin else None,
        'route_map_points':[{'number':v['route_number'],'title':v['titulo'],'address':v['endereco_exibicao'],'lat':v['lat'],'lng':v['lng']} for v in visits if v['lat'] is not None]}
