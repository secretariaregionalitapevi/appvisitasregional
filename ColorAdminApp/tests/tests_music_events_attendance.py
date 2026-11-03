import io
from datetime import datetime

from django.test import SimpleTestCase
from openpyxl import load_workbook
from pypdf import PdfReader

from ColorAdminApp.modules.music_events_attendance import attendance_overview, general_report
from ColorAdminApp.modules.music_events_dashboard import aggregate
from ColorAdminApp.modules.music_events_registry import attach_registry
from ColorAdminApp.modules.music_events_reports import build_excel, build_pdf, sheets


class AttendanceOverviewTests(SimpleTestCase):
    def fixture(self):
        events=[{'id':'may','titulo':'Ensaio Regional · 17/05/2026','data_evento':'2026-05-17',
                 'tipo':'ENSAIO_REGIONAL','familia':'GERAL','status':'ABERTO','base_id':None}]
        sites=[{'id':'itapevi','evento_id':'may','nome':'ITAPEVI'},
               {'id':'pirapora','evento_id':'may','nome':'PIRAPORA'}]
        catalog=[{'comum':'BR-22-0673 - VILA DOUTOR CARDOSO','cidade':'ITAPEVI'},
                 {'comum':'BR-22-1000 - SEM PARTICIPACAO','cidade':'ITAPEVI'}]
        base={'evento_id':'may','local_id':'itapevi','situacao':'PRESENTE','familia':'CORDAS',
              'comum_informada':catalog[0]['comum'],'municipio_informado':'ITAPEVI'}
        records=[dict(base,id='musician',categoria='MUSICO',cargo='ANCIÃO',instrumento='VIOLINO'),
                 dict(base,id='organist',categoria='ORGANISTA',instrumento='ÓRGÃO'),
                 dict(base,id='visitor',categoria='IRMANDADE',municipio_informado='OSASCO',comum_informada='CENTRAL OSASCO'),
                 dict(base,id='pirapora',categoria='MUSICO',local_id='pirapora',instrumento='TUBA')]
        filters={'evento':'may','municipios':['ITAPEVI'],'comuns':['BR-22-0673'],'origem':'regional','local':''}
        return events,sites,catalog,records,filters

    def test_general_includes_visitors_and_does_not_add_ministry_roles(self):
        e,s,c,r,f=self.fixture()
        overview=attendance_overview(e,r,s,{**f,'municipios':[]},c)
        self.assertEqual(overview['totals']['total'],4)
        self.assertEqual(overview['totals']['MUSICO'],2)
        self.assertEqual(sum(overview['totals'].get(k,0) for k in ['MUSICO','ORGANISTA','MINISTERIO','APOIO','IRMANDADE']),4)
        closing=next(row for row in overview['closings'] if row['city']=='ITAPEVI')
        self.assertEqual(closing['total'],3)
        self.assertEqual(closing['declared_total'],2440)
        self.assertEqual(closing['difference'],2437)
        selected=attendance_overview(e,r,s,{**f,'municipios':['PIRAPORA'],'local':'pirapora'},c)
        self.assertEqual(selected['totals']['total'],1)
        self.assertEqual(len(selected['closings']),1)
        self.assertEqual(selected['closings'][0]['city'],'PIRAPORA DO BOM JESUS')

    def test_current_registry_percentages_and_zero_participation(self):
        e,s,c,r,f=self.fixture()
        data=aggregate(e,r,s,[],{**f,'comuns':[]},c)
        people=[{'id':str(i),'status':'ATIVO','instrumento':inst,'comum_congregacao':common['comum'],'municipio':'ITAPEVI'}
                for i,(common,inst) in enumerate([(c[0],'VIOLINO'),(c[0],'TUBA'),(c[0],'ÓRGÃO'),(c[1],'VIOLA')])]
        attach_registry(data,people,c,include_zero=True)
        first=next(row for row in data['rows'] if row['comum']==c[0]['comum'])
        self.assertEqual(first['percentual_cadastro_musicos'],100)
        self.assertEqual(first['percentual_cadastro_organistas'],100)
        self.assertIsNone(first['percentual_musicos'])
        absent=next(row for row in data['rows'] if row['comum']==c[1]['comum'])
        self.assertEqual(absent['percentual_cadastro_musicos'],0)
        self.assertIsNone(absent['percentual_cadastro_organistas'])
        self.assertEqual(data['totals']['total'],3)

    def test_general_exports_reconcile_categories_and_keep_institutional_headers(self):
        e,s,c,r,f=self.fixture()
        e[0]['data_evento']='2026-01-18'
        f['municipios']=[]
        data=aggregate(e,r,s,[],f,c)
        data['attendance_overview']=attendance_overview(e,r,s,f,c)
        report=general_report(data)
        now=datetime(2026,11,1,15,30)
        book=load_workbook(io.BytesIO(build_excel(report,'Operador de teste',now)))
        self.assertEqual(len(book.sheetnames),3)
        for sheet in book:
            self.assertEqual(sheet['A1'].value,'CONGREGAÇÃO CRISTÃ NO BRASIL')
            self.assertEqual(sheet['A1'].fill.fgColor.rgb[-6:],'1E4B7A')
            self.assertFalse(sheet.sheet_view.showGridLines)
            self.assertEqual(sheet.freeze_panes,'A10')
            self.assertEqual(sheet.page_setup.fitToWidth,1)
        self.assertEqual(sheets(report)[0][2][-1][-1],4)
        pdf=build_pdf(report,'Operador de teste',now)
        reader=PdfReader(io.BytesIO(pdf))
        text='\n'.join(page.extract_text() for page in reader.pages)
        self.assertIn('CONGREGAÇÃO CRISTÃ NO BRASIL',text)
        self.assertIn('OSASCO',text)
        self.assertIn('Conciliação do fechamento',text)
        self.assertIn('01/11/2026 15:30',text)

    def test_current_registry_does_not_report_a_false_consolidated_percentage(self):
        e,s,c,r,f=self.fixture()
        data=aggregate(e,r,s,[],{**f,'comuns':[]},c)
        people=[{'id':'registered','status':'ATIVO','instrumento':'VIOLINO',
                 'comum_congregacao':c[0]['comum'],'municipio':'ITAPEVI'}]
        attach_registry(data,people,c)
        row=data['rows'][0]
        self.assertEqual(row['percentual_cadastro_musicos'],200)
        self.assertTrue(row['cadastro_divergente'])
        data['events'].append(dict(e[0],id='other'))
        attach_registry(data,people,c)
        self.assertIsNone(row['percentual_cadastro_musicos'])
        # Duas presenças em datas diferentes não são 200% de participação
        # em um único evento. O relatório específico deve ser selecionado.
        frequency=sheets(data)[0][2]
        self.assertTrue(all(values[8] is None and values[9] is None for values in frequency))

    def test_municipality_limits_physical_sites_and_keeps_visitors(self):
        e,s,c,r,f=self.fixture()
        overview=attendance_overview(e,r,s,f,c)
        self.assertEqual([row['city'] for row in overview['closings']],['ITAPEVI'])
        self.assertEqual(overview['totals']['total'],3)
        self.assertEqual(overview['totals']['IRMANDADE'],1)
        self.assertEqual(len(overview['locations']),1)
        self.assertEqual(overview['locations'][0]['nome'],'ITAPEVI')
        conflict=attendance_overview(e,r,s,{**f,'local':'pirapora'},c)
        self.assertEqual(conflict['totals']['total'],0)
        self.assertEqual(conflict['closings'],[])

    def test_approved_historical_report_uses_exact_official_counts(self):
        e,s,c,r,f=self.fixture()
        overview=attendance_overview(e,r,s,f,c)
        self.assertTrue(overview['official_only'])
        self.assertEqual(overview['display_totals']['total'],2440)
        self.assertEqual(overview['display_totals']['MUSICO'],1201)
        self.assertEqual(overview['display_totals']['ORGANISTA'],320)
        self.assertEqual(overview['display_totals']['IRMANDADE'],830)
        self.assertEqual(overview['totals']['total'],3)  # Lista nominal preservada.
        data=aggregate(e,r,s,[],f,c)
        data['attendance_overview']=overview
        report=general_report(data)
        reports=sheets(report)
        self.assertEqual(reports[0][2][0][2:6],[1201,320,1521,2440])
        self.assertEqual(report['filters']['municipios'],['ITAPEVI'])
        pdf=build_pdf(report,'Operador de teste',datetime(2026,11,1,15,30))
        text='\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
        for value in ['2440','1201','320','830','Relatório oficial']:
            self.assertIn(value,text)
        self.assertNotIn('PIRAPORA',text)
        self.assertNotIn('Conciliação do fechamento',text)
        book=load_workbook(io.BytesIO(build_excel(report,'Operador de teste',datetime(2026,11,1,15,30))))
        self.assertEqual(book.worksheets[0]['F10'].value,2440)
        self.assertEqual(book.worksheets[0]['C10'].value,1201)

    def test_unfiltered_event_identifies_mixed_official_and_nominal_sources(self):
        e,s,c,r,f=self.fixture()
        overview=attendance_overview(e,r,s,{**f,'municipios':[]},c)
        self.assertFalse(overview['official_only'])
        self.assertTrue(overview['has_official'])
        self.assertEqual(overview['display_totals']['total'],2441)
        self.assertEqual(overview['totals']['total'],4)
