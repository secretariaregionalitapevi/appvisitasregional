import io
from unittest.mock import patch
from django.test import SimpleTestCase, RequestFactory
from openpyxl import Workbook, load_workbook
from pypdf import PdfReader
from ColorAdminApp.modules import music_letters
from ColorAdminApp.modules.music_letters_domain import summarize, matches, ministry_workbook, exam_payload
from ColorAdminApp.modules.music_letters_exports import make_pdf, make_excel

def letter(**changes):
    row = {'id': '00000000-0000-4000-8000-000000000001', 'nome': 'CANDIDATO DE EXEMPLO',
           'comum': 'BR-22-2999 - VILA DAS CHÁCARAS', 'municipio': 'ITAPEVI', 'tipo': 'musico',
           'modalidade': 'oficializacao', 'review_result': 'PENDENTE', 'status': 'ready',
           'event_id': 'event', 'event_snapshot': {'data': '2026-11-28', 'evento': 'Avaliação de Músicos (Itapevi)'},
           'payload': {'pessoa_id': '00000000-0000-4000-8000-000000000002', 'instrumento': 'TROMPETE', 'tonalidade': 'SI BEMOL'},
           'ministry_snapshot': {}}
    row.update(changes)
    return row

class MusicLettersTests(SimpleTestCase):
    def test_pending_letters_do_not_count_as_approval(self):
        groups, totals = summarize([letter(), letter(id='second', tipo='organista', modalidade='rjm', review_result='APROVADO')])
        self.assertEqual(totals['cartas'], 2)
        self.assertEqual(totals['aprovados'], 1)
        self.assertEqual(groups[0]['musicos_oficializacao'], 0)
        self.assertEqual(groups[0]['organistas_rjm'], 1)

    def test_four_administrations_are_preserved(self):
        groups, totals = summarize([letter(municipio='Caucaia do Alto', modalidade='culto', review_result='APROVADO'),
                                   letter(municipio='Pirapora do Bom Jesus', review_result='APROVADO')])
        self.assertEqual(groups[2]['musicos_culto_oficial'], 1)
        self.assertEqual(groups[3]['musicos_oficializacao'], 1)

    def test_same_filters_apply_to_exports(self):
        self.assertTrue(matches(letter(), {'municipio': 'ITAPEVI', 'inicio': '2026-11-01', 'fim': '2026-11-30', 'busca': 'candidato exemplo'}))
        self.assertFalse(matches(letter(), {'resultado': 'APROVADO'}))
        self.assertFalse(matches(letter(), {'mes': '10'}))
        self.assertFalse(matches(letter(), {'ano': '2025'}))
        self.assertFalse(matches(letter(), {'comum': 'Outra comum'}))
        self.assertTrue(matches(letter(), {'ano': '2026', 'comum': letter()['comum']}))

    def test_assistance_is_taken_from_source_and_missing_cooperator_has_agreed_text(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(['COMUM_ALUNA', 'ID', 'CODIGO_ALUNA', 'ANCIÃO', 'COOPERADOR', 'REGIONAL', 'ENCARREGADO', 'SECRETÁRIO', 'CIDADE'])
        sheet.append(['Central', None, 'BR-21-1039 - CENTRAL', 'ANCIÃO QUE DÁ ASSISTÊNCIA', None, 'REGIONAL', 'LOCAL', 'SECRETÁRIO', 'ITAPEVI'])
        rows = ministry_workbook(workbook, 'source-hash')
        self.assertEqual(rows[0]['anciao'], 'ANCIÃO QUE DÁ ASSISTÊNCIA')
        self.assertEqual(rows[0]['cooperador'], 'Sem Cooperador do Ofício')
        self.assertEqual(rows[0]['source_row'], 2)
        sheet.append(list(next(iter(sheet.values))))
        sheet.append(['Central', None, 'BR-21-1039 - CENTRAL', 'OUTRO', None, 'REGIONAL', 'LOCAL', '', 'ITAPEVI'])
        with self.assertRaises(ValueError):
            ministry_workbook(workbook, 'source-hash')

    def test_confirmation_requires_stable_candidate(self):
        self.assertEqual(exam_payload(letter(), 'Secretário')['tipo_exame'], 'OFICIALIZACAO')
        with self.assertRaises(ValueError):
            exam_payload(letter(payload={}), 'Secretário')

    @patch.object(music_letters, 'can_review', return_value=False)
    def test_confirmation_denies_unprivileged_user_before_database(self, allowed):
        request = RequestFactory().post('/musica/cartas-exames/api/cartas/1/confirmar/', data='{}', content_type='application/json')
        request.session = {}
        with patch.object(music_letters, 'find') as lookup:
            self.assertEqual(music_letters.confirm(request, 'id').status_code, 403)
            lookup.assert_not_called()

    @patch.object(music_letters, 'can_open_module', return_value=False)
    def test_exports_are_not_public(self, allowed):
        request = RequestFactory().get('/musica/cartas-exames/exportar-pdf/')
        request.session = {}
        self.assertEqual(music_letters.export(request, 'pdf').status_code, 403)

    def test_export_pdf_and_excel_have_real_content_and_institutional_header(self):
        rows = [letter(), letter(id='second', nome='OUTRO CANDIDATO', modalidade='culto')]
        pdf = make_pdf(rows, 'Secretário de teste', {'municipio': 'ITAPEVI'})
        reader = PdfReader(io.BytesIO(pdf))
        text = '\n'.join(page.extract_text() for page in reader.pages)
        for value in ['CONGREGAÇÃO CRISTÃ NO BRASIL', 'Regional Itapevi', 'CANDIDATO DE EXEMPLO', 'OUTRO CANDIDATO', 'OBSERVAÇÃO']:
            self.assertIn(value, text)
        workbook = load_workbook(io.BytesIO(make_excel(rows, 'Secretário de teste', {})))
        sheet = workbook.active
        self.assertEqual(sheet['A1'].value, 'CONGREGAÇÃO CRISTÃ NO BRASIL')
        self.assertEqual(sheet['A6'].fill.fgColor.rgb[-6:], '1E4B7A')
        self.assertEqual(sheet.freeze_panes, 'A7')
        self.assertEqual(sheet.print_title_rows, '$1:$6')
        self.assertEqual(sheet['H7'].value, '28/11/2026')
        self.assertEqual(sheet.max_row, 8)

    def test_spreadsheet_does_not_execute_user_values_as_formulas(self):
        workbook = load_workbook(io.BytesIO(make_excel([letter(nome='=1+1')], 'Teste', {})))
        self.assertEqual(workbook.active['B7'].data_type, 's')
