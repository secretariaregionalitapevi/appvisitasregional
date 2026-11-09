import json
from datetime import datetime
from io import BytesIO
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase
from django.template.loader import render_to_string
from django.http import QueryDict
from openpyxl import load_workbook
from pypdf import PdfReader

from ColorAdminApp.modules import darpe_atendimentos as attendance
from ColorAdminApp.modules import darpe_atendimentos_exports as reports
from ColorAdminApp.tests.tests_darpe import request_for


def sample():
    return {'id':'record', 'data':'2026-11-01','hora_inicio':'09:30','hora_fim':'11:00','setor':2,
            'local':'Unidade de atendimento','municipio':'ITAPEVI','comum':'CENTRAL',
            'equipe':[{'cadastro_id':'person','funcao':'atendente','nome':'Atendente de teste'},
                      {'cadastro_id':'music','funcao':'musico','nome':'Músico de teste'}],
            'hinos':[374,7],'palavra':'Atos 3','observacoes':'','participacao':'40 participantes',
            'pedidos_oracao':{'familias':'todas'},'whatsapp':'(11) 99999-1234',
            'telefone':'(11) 4141-1234','created_by_name':'Operador de teste',
            'created_at':'2026-11-01T15:00:00Z'}


class AdminAttendanceTests(SimpleTestCase):
    @patch.object(attendance.requests,'get',side_effect=AssertionError('Render não deve consultar Supabase'))
    def test_authenticated_admin_page_renders_without_fetching_records(self, get):
        req=request_for('/darpe/atendimentos/')
        req.session['user_profile'].update(role_id=1,access_level='global')
        response=attendance.page(req)
        self.assertEqual(response.status_code,200)
        self.assertIn(b'id="darpe-admin"',response.content)
        self.assertIn(b'id="daa-kpis"',response.content)
        self.assertIn(b'id="daa-records"',response.content)
        get.assert_not_called()

    @patch.object(attendance,'common_catalog',return_value=[
        {'cidade':'ITAPEVI','comum':'BR-01 - CENTRAL'},
        {'cidade':'ITAPEVI','comum':'BR-02 - JARDIM'},
        {'cidade':'JANDIRA','comum':'BR-03 - CENTRAL'},
    ])
    def test_catalog_available_without_any_attendances(self, catalog):
        req=request_for('/darpe/atendimentos/api/contexto/')
        with patch.object(attendance,'rows') as records:
            data=json.loads(attendance.api(req,'contexto').content)
        self.assertEqual({r['municipio'] for r in data['localidades']},{'ITAPEVI','JANDIRA'})
        self.assertEqual(len(data['localidades']),3)
        records.assert_not_called()

    @patch.object(attendance,'common_catalog',return_value=[
        {'cidade':'ITAPEVI','comum':'CENTRAL'},
        {'cidade':'ITAPEVI','comum':'JARDIM'},
        {'cidade':'JANDIRA','comum':'CENTRAL'},
    ])
    def test_localities_respect_municipal_and_local_scope(self, catalog):
        municipal={'level':'municipal','municipio':'ITAPEVI','comum':''}
        self.assertEqual(len(attendance.localities(municipal)),2)
        local={'level':'local','municipio':'ITAPEVI','comum':'CENTRAL'}
        self.assertEqual(attendance.localities(local),[{'municipio':'ITAPEVI','comum':'CENTRAL'}])

    def test_admin_is_a_management_dashboard_with_separate_editor(self):
        html=render_to_string('pages/darpe_atendimentos.html',{'scope':{'nivel':'global'}})
        for target in ['daa-kpis','daa-evolution','daa-sectors','daa-cities','daa-attendants',
                       'daa-year','daa-month','daa-start','daa-end','daa-city','daa-common',
                       'daa-sector','daa-records','daa-form-host','Novo lançamento',
                       'darpe-atendimentos-admin.js']:
            self.assertIn(target,html)

    def test_filters_match_period_locality_sector_and_responsible(self):
        row=sample()
        for params, count in [({'ano':'2026','mes':'11'},1),({'ano':'2025'},0),
                              ({'inicio':'2026-11-02'},0),({'fim':'2026-11-01'},1),
                              ({'setor':'3'},0),({'municipio':'itapevi','comum':'central'},1),
                              ({'q':'atendente teste'},1),({'q':'inexistente'},0)]:
            with self.subTest(params=params):
                self.assertEqual(len(attendance.filtered([row],params)),count)

    def test_multiple_municipalities_and_commons_in_api_and_report(self):
        rows=[sample(),{**sample(),'municipio':'JANDIRA','comum':'JARDIM'},
              {**sample(),'municipio':'COTIA','comum':'OUTRA'}]
        params=QueryDict('municipio=ITAPEVI&municipio=JANDIRA&comum=CENTRAL&comum=JARDIM')
        self.assertEqual(len(attendance.filtered(rows,params)),2)
        scope=reports.report_scope(params)
        for value in ['ITAPEVI','JANDIRA','CENTRAL','JARDIM']:
            self.assertIn(value,scope)

    def test_excel_standard_dates_printing_and_formula_safety(self):
        row=sample();row['local']='=HYPERLINK("invalid")'
        now=datetime(2026,11,7,18,30,tzinfo=ZoneInfo('America/Sao_Paulo'))
        sheet=load_workbook(BytesIO(reports.build_excel([row],'Itapevi', 'Operador',now))).active
        self.assertEqual(sheet['A1'].value,'CONGREGAÇÃO CRISTÃ NO BRASIL')
        self.assertEqual(sheet['A2'].value,'Regional Itapevi - São Paulo')
        self.assertEqual(sheet['A7'].value,'01/11/2026')
        self.assertEqual(sheet['E7'].data_type,'s')
        self.assertEqual(sheet['A6'].fill.fgColor.rgb[-6:],'1E4B7A')
        self.assertEqual(sheet.freeze_panes,'A7')
        self.assertEqual(sheet.page_setup.fitToWidth,1)
        self.assertEqual(sheet.max_column,9)
        self.assertEqual(sheet.print_title_rows,'$1:$6')

    def test_pdf_real_multiple_pages_and_repeated_header(self):
        now=datetime(2026,11,7,18,30,tzinfo=ZoneInfo('America/Sao_Paulo'))
        output=reports.build_pdf([sample() for _ in range(55)],'Itapevi', 'Operador',now)
        pages=PdfReader(BytesIO(output)).pages
        self.assertGreater(len(pages),1)
        for page in pages:
            text=page.extract_text()
            for value in ['CONGREGAÇÃO CRISTÃ NO BRASIL','Regional Itapevi - São Paulo',
                          'Atendimentos realizados','07/11/2026 18:30','Impresso por:', 'Página']:
                self.assertIn(value,text)
            self.assertAlmostEqual(float(page.mediabox.width),841.8898,places=2)

    def test_single_papeleta_pdf_contains_all_fields_and_standard_header(self):
        now=datetime(2026,11,7,18,30,tzinfo=ZoneInfo('America/Sao_Paulo'))
        output=reports.build_papeleta_pdf(sample(),'Operador de teste',now)
        reader=PdfReader(BytesIO(output))
        self.assertEqual(len(reader.pages),1)
        text=reader.pages[0].extract_text()
        for value in [
            'CONGREGAÇÃO CRISTÃ NO BRASIL', 'Regional Itapevi - São Paulo',
            'Papeleta de atendimento', '07/11/2026 18:30', 'Impresso por:',
            '01/11/2026', 'Unidade de atendimento', 'ITAPEVI', 'CENTRAL',
            'Atendente de teste', 'Músico de teste', '374, 7', 'Atos 3',
            '40 participantes', 'Todas',
            '(11) 99999-1234', '(11) 4141-1234',
            'ATENDIMENTO D.A.R.P.E.', 'Orações', 'Colaboradores',
            'Irmão da palavra', 'PEDIDOS DE ORAÇÃO', 'Enfermidade(s)',
            'Acidentado(s)', 'Tribulação(ões)', 'Testemunhado(s)',
        ]:
            self.assertIn(value,text)
        self.assertLess(text.index('Hinos'),text.index('Palavra'))
        self.assertLess(text.index('Palavra'),text.index('Irmão da palavra'))
        self.assertLess(text.index('Obs.'),text.index('PEDIDOS DE ORAÇÃO'))
        self.assertAlmostEqual(float(reader.pages[0].mediabox.width),595.2756,places=2)

    @patch.object(attendance,'visible_records',return_value=[sample()])
    def test_export_uses_the_same_filters_as_dashboard(self, visible):
        req=request_for('/darpe/atendimentos/api/exportar-excel/?setor=3')
        self.assertEqual(reports.export(req,'excel').status_code,400)
        req=request_for('/darpe/atendimentos/api/exportar-excel/?setor=2')
        response=reports.export(req,'excel')
        self.assertEqual(response.status_code,200)
        self.assertIn('Atendimentos_DARPE_',response['Content-Disposition'])
