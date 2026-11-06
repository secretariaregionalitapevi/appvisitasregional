"""Relação para Regionais/Examinadoras com coluna de entrega, conforme modelo fornecido."""
import io
from collections import defaultdict
from html import escape
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.pdfgen import canvas
from .music_letters_roster import MODES, delivery_summary
from .music_letters_exports import date_br

BLUE = '#1e4b7a'


def sections(rows):
    result = defaultdict(list)
    for row in rows:
        e = row['event_snapshot']
        result[(row['event_id'], e.get('data', ''), e.get('evento', ''), row['tipo'], row['modalidade'])].append(row)
    order = {'oficializacao': 0, 'culto': 1, 'rjm': 2, 'por_chance': 3, 'troca_necessidade': 4, 'troca_enfermidade': 5}
    return [(key, sorted(items, key=lambda r: (r['comum'], r['nome']))) for key, items in sorted(result.items(), key=lambda pair: (pair[0][1], pair[0][2], pair[0][3], order.get(pair[0][4], 9)))]


def section_title(key):
    mode = key[4]
    return {'oficializacao': 'PARA EXAME DE OFICIALIZA\u00c7\u00c3O', 'culto': 'PARA TESTE CULTO OFICIAL',
            'rjm': 'PARA TESTE RJM', 'por_chance': 'POR CHANCE',
            'troca_necessidade': 'TROCA DE INSTRUMENTO - NECESSIDADE',
            'troca_enfermidade': 'TROCA DE INSTRUMENTO - ENFERMIDADE'}.get(mode, mode.upper())


def section_context(key):
    _, dt, event, kind, _ = key
    return f'{"Organistas" if kind == "organista" else "M\u00fasicos"} | {date_br(dt)} - {event}'


def instrument(row):
    return ' - '.join(filter(None, [row.get('instrumento'), row.get('tonalidade')]))


def notes(row, deadlines):
    # Keep the observation short; delivery details have their own controls.
    import re
    status = row.get('activity_status') or (row.get('student_activity') or {}).get('status')
    if not status:
        match = re.search(r'\b(INATIVO|EXCLUIR)\b', row.get('activity_note') or '', re.I)
        status = match.group(1) if match else ''
    if status:
        return 'Status: ' + str(status).capitalize()
    return ' '.join(str(row.get('observacao') or '').split())



class DeliveryCheck(Flowable):
    def __init__(self, checked):
        Flowable.__init__(self); self.width = 10; self.height = 10; self.checked = checked
    def draw(self):
        self.canv.saveState()
        self.canv.setLineWidth(.7)
        self.canv.setStrokeColor(colors.black if self.checked else colors.red)
        self.canv.setFillColor(colors.black if self.checked else colors.white)
        self.canv.rect(1, 1, 8, 8, fill=int(self.checked), stroke=1)
        if self.checked:
            self.canv.setStrokeColor(colors.white)
            self.canv.setLineWidth(1.1)
            self.canv.line(2.5, 5, 4.3, 2.7)
            self.canv.line(4.3, 2.7, 7.7, 7.5)
        self.canv.restoreState()


def make_pdf(rows, responsible, deadlines, template=False):
    output = io.BytesIO(); pw, ph = landscape(A4); width = pw - 56
    stamp = timezone.localtime().strftime('%d/%m/%Y %H:%M')
    cell = ParagraphStyle('cell', fontName='Helvetica', fontSize=8, leading=10, textColor=colors.HexColor('#263238'))
    head = ParagraphStyle('head', parent=cell, fontName='Helvetica-Bold', textColor=colors.white, alignment=1)
    group = ParagraphStyle('group', parent=cell, fontName='Helvetica-Bold', textColor=colors.HexColor(BLUE), fontSize=9, leading=12, alignment=1)
    para = lambda value, style=cell: Paragraph(escape(str(value or '')).replace('\n', '<br/>'), style)
    class NumberedCanvas(canvas.Canvas):
        def __init__(self,*a,**kw):
            super().__init__(*a,**kw); self.states=[]
        def showPage(self):
            self.states.append(dict(self.__dict__)); self._startPage()
        def save(self):
            for state in self.states:
                self.__dict__.update(state)
                for text,size,font,y in [('CONGREGAÇÃO CRISTÃ NO BRASIL',15,'Helvetica-Bold',29),('Regional Itapevi - São Paulo',9,'Helvetica',43),('MÚSICA - CARTAS DE EXAMES',11,'Helvetica-Bold',59),('Relação de candidatos e controle de entrega',9,'Helvetica',73)]:
                    self.setFont(font,size); self.setFillColor(colors.HexColor(BLUE)); self.drawCentredString(pw/2,ph-y,text)
                meta = Paragraph(f'<b>Página:</b> {self._pageNumber} de {len(self.states)}<br/><b>Emissão:</b> {stamp}<br/><b>Recorte:</b> {len(rows)} candidatos<br/><b>Impresso por:</b> {escape(responsible)}', ParagraphStyle('meta',fontSize=7,leading=9,alignment=2))
                _,h=meta.wrap(180,70);meta.drawOn(self,pw-208,ph-18-h)
                self.setFillColor(colors.HexColor('#64748b'));self.setFont('Helvetica',7)
                self.drawString(28,18,'Cartas de exames - Relação para Regionais e Examinadoras')
                self.drawRightString(pw-28,18,f'Página {self._pageNumber} de {len(self.states)}')
                canvas.Canvas.showPage(self)
            canvas.Canvas.save(self)
    totals = delivery_summary(rows)
    body = [Table([[para(f'Inscrições: {totals["total"]}   |   Cartas entregues: {totals["delivered"]}   |   Cartas faltantes: {totals["missing"]}   |   Entregues em atraso: {totals["late"]}')]], colWidths=[width], style=[('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#eaf2f8')),('PADDING',(0,0),(-1,-1),7)]),Spacer(1,12)]
    for key,items in sections(rows):
        limit=deadlines.get(key[0]);title=section_title(key)+'\n'+section_context(key)+((' | Prazo de entrega: '+date_br(limit['deadline'])) if limit else ' | Prazo de entrega n\u00e3o definido')
        group_row=[para(title,group)]+['']*5
        headers=[para(label,head) for label in ['Nº','NOME','COMUM','INSTRUMENTO','OBSERVAÇÃO','CARTA']]
        values=[group_row,headers]
        for n,row in enumerate(items,1):
            received=bool((row.get('delivery') or {}).get('received'))
            row_style=ParagraphStyle('received' if received else 'missing',parent=cell,textColor=colors.black if received else colors.red)
            values.append([para(value,row_style) for value in [n,row['nome'],row['comum'],instrument(row),notes(row,deadlines)]]+[DeliveryCheck(received)])
        table=Table(values,colWidths=[width*x for x in (.035,.295,.29,.20,.125,.055)],repeatRows=2,splitByRow=1)
        table.setStyle(TableStyle([('SPAN',(0,0),(-1,0)),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf2f8')),('BACKGROUND',(0,1),(-1,1),colors.HexColor(BLUE)),('ROWBACKGROUNDS',(0,2),(-1,-1),[colors.white,colors.HexColor('#f4f6f8')]),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#c8d1da')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(-1,2),(-1,-1),'CENTER'),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
        body.extend([table,Spacer(1,12)])
    if not rows:body.append(para('Nenhum candidato no recorte selecionado.'))
    body.append(para(f'TOTAL DE INSCRIÇÕES: {totals["total"]}     TOTAL DE CARTAS ENTREGUES: {totals["delivered"]}     TOTAL DE CARTAS FALTANTES: {totals["missing"]}',group))
    SimpleDocTemplate(output,pagesize=landscape(A4),leftMargin=28,rightMargin=28,topMargin=100,bottomMargin=34).build(body,canvasmaker=NumberedCanvas)
    return output.getvalue()


def make_excel(rows, responsible, deadlines, template=False):
    workbook=Workbook();sheet=workbook.active;sheet.title='Candidatos'
    labels=['Nº','Nome','Comum','Instrumento','Tonalidade','Tipo','Modalidade','Observação','Data entrega','ID SAM','Carta entregue']
    end=get_column_letter(len(labels));stamp=timezone.localtime().strftime('%d/%m/%Y %H:%M')
    for n,text in enumerate(['CONGREGAÇÃO CRISTÃ NO BRASIL','Regional Itapevi - São Paulo','MÚSICA - Relação de candidatos e controle de entrega',f'Emissão: {stamp} - Impresso por: {responsible}'],1):
        sheet.merge_cells(f'A{n}:{end}{n}');c=sheet.cell(n,1,text);c.font=Font(size=15 if n==1 else 10,bold=n<4,color='FFFFFF' if n<3 else '1E4B7A');c.fill=PatternFill('solid',fgColor='1E4B7A' if n<3 else 'EAF2F8');c.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True);sheet.row_dimensions[n].height=24
    for i,label in enumerate(labels,1):
        c=sheet.cell(6,i,label);c.fill=PatternFill('solid',fgColor='1E4B7A');c.font=Font(bold=True,color='FFFFFF');c.alignment=Alignment(horizontal='center',vertical='center',wrap_text=True)
    for n,row in enumerate([r for _,items in sections(rows) for r in items],7):
        delivery=row.get('delivery') or {}
        from .music_letters_roster import parse_date
        values=[n-6,row['nome'],row['comum'],row.get('instrumento'),row.get('tonalidade'),row['tipo'],row['modalidade'],notes(row,deadlines),parse_date(delivery.get('received_on')),row.get('pessoa_id'),'Sim' if delivery.get('received') else 'Não']
        for i,value in enumerate(values,1):
            c=sheet.cell(n,i,value)
            if isinstance(value,str):c.data_type='s'
            c.font=Font(size=10,color='000000' if delivery.get('received') else 'FF0000');c.alignment=Alignment(vertical='center',wrap_text=True);c.fill=PatternFill('solid',fgColor='FFFFFF' if n%2 else 'F4F6F8');c.border=Border(bottom=Side(style='thin',color='D8DEE5'))
        sheet.cell(n,9).number_format='dd/mm/yyyy';sheet.row_dimensions[n].height=32
    for i,w in enumerate([6,38,43,24,12,13,23,35,15,38,16],1):sheet.column_dimensions[get_column_letter(i)].width=w
    for col,formula in [('F','"musico,organista"'),('G','"oficializacao,culto,rjm,por_chance,troca_necessidade,troca_enfermidade"'),('K','"Sim,Não"')]:
        validation=DataValidation(type='list',formula1=formula,allow_blank=True);validation.errorTitle='Valor inválido';validation.error='Selecione uma opção da lista.';validation.showErrorMessage=True;sheet.add_data_validation(validation);validation.add(f'{col}7:{col}1006')
    sheet.freeze_panes='A7';sheet.auto_filter.ref=f'A6:{end}{max(6,len(rows)+6)}';sheet.sheet_view.showGridLines=False
    sheet.sheet_properties.pageSetUpPr.fitToPage=True;sheet.page_setup.orientation='landscape';sheet.page_setup.paperSize=sheet.PAPERSIZE_A3;sheet.page_setup.fitToWidth=1;sheet.page_setup.fitToHeight=0;sheet.print_title_rows='1:6';sheet.print_options.horizontalCentered=True;sheet.print_area=f'A1:{end}{max(7,len(rows)+6)}';sheet.oddFooter.center.text='Regional Itapevi - Página &P de &N'
    info=workbook.create_sheet('Orientações');info.append(['Preenchimento e importação']);info.append(['Use a aba Candidatos. Nome e Comum são obrigatórios; preserve o código BR-00-0000.']);info.append(['Selecione o evento, o tipo e a modalidade no painel antes de importar.']);info.append(['Carta entregue: Sim ou Não. Data entrega: dd/mm/aaaa. Sim sem data fica como data não informada.']);info.append(['ID SAM é opcional; vínculos só são confirmados por nome, comum e tipo.']);info.append(['Registros já existentes são preservados; ajuste entregas diretamente no sistema.']);info.column_dimensions['A'].width=115;info.sheet_view.showGridLines=False
    for row in info:
        row[0].alignment=Alignment(wrap_text=True,vertical='center');info.row_dimensions[row[0].row].height=30
    info['A1'].font=Font(bold=True,color='FFFFFF');info['A1'].fill=PatternFill('solid',fgColor='1E4B7A')
    output=io.BytesIO();workbook.save(output);return output.getvalue()
