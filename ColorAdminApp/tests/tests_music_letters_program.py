import io
from unittest.mock import patch
from django.test import SimpleTestCase, RequestFactory
from openpyxl import load_workbook
from ColorAdminApp.modules import music_letters
from ColorAdminApp.modules.music_letters_program import assess_letters, program_summary
from ColorAdminApp.modules.music_letters_program_export import make_program_excel, make_program_pdf
from ColorAdminApp.modules.sam_program import assess_program

ID = '00000000-0000-4000-8000-000000000001'

def letter(**changes):
    return {'id': 'letter', 'tipo': 'musico', 'modalidade': 'culto', 'payload': {'pessoa_id': ID},
            'nome': '=NOME', 'municipio': 'ITAPEVI', 'comum': 'COMUM',
            'event_snapshot': {'data': '2026-11-28'}, **changes}

class LetterProgramTests(SimpleTestCase):
    def test_requested_stage_overrides_next_level(self):
        student = {'nivel': 'CULTO OFICIAL', 'instrumento': 'TROMPETE'}
        records = {'msa': [{'fase': '16'}], 'metodo': [{'metodo': 'Getchel', 'licao': '94'}],
                   'hinario': [{'hino': '1-480'}]}
        self.assertTrue(assess_program(student, records, target='culto')['eligible'])
        self.assertFalse(assess_program(student, records, target='oficializacao')['eligible'])

    @patch('ColorAdminApp.modules.music_letters_program.fetch_rows')
    def test_organists_and_instrument_changes_are_not_queried(self, fetch):
        rows = assess_letters([letter(tipo='organista'), letter(modalidade='troca_necessidade')])
        self.assertTrue(all(r['program_assessment'] is None for r in rows))
        fetch.assert_not_called()

    @patch('ColorAdminApp.modules.music_letters_program.fetch_rows')
    def test_missing_history_and_query_failure_are_not_noncompliance(self, fetch):
        fetch.side_effect = lambda table, ids, field: [{'id': ID, 'instrumento': 'VIOLINO'}] if field == 'id' else []
        rows = assess_letters([letter()])
        self.assertEqual(rows[0]['program_assessment']['status'], 'no_data')
        self.assertIsNone(program_summary(rows)['pending_percent'])
        import requests
        fetch.side_effect = requests.ConnectionError()
        self.assertEqual(assess_letters([letter()])[0]['program_assessment']['status'], 'unavailable')

    def test_denominator_deduplicates_student_stage(self):
        rows = [letter(program_assessment={'status': 'pending'}),
                letter(id='duplicate', program_assessment={'status': 'pending'}),
                letter(id='other', payload={'pessoa_id': 'second'}, program_assessment={'status': 'eligible'}),
                letter(id='unknown', payload={}, program_assessment={'status': 'unlinked'})]
        summary = program_summary(rows)
        self.assertEqual(summary['total'], 3)
        self.assertEqual(summary['pending_percent'], 50)

    @patch('ColorAdminApp.modules.music_letters_program.fetch_rows')
    def test_export_institutional_header_real_file_and_unknown_separation(self, fetch):
        fetch.side_effect = lambda table, ids, field: [{'id': ID, 'instrumento': 'VIOLINO'}] if field == 'id' else []
        content = make_program_excel(assess_letters([letter()]), 'Responsável', {})
        sheet = load_workbook(io.BytesIO(content)).active
        self.assertEqual(sheet['A1'].value, 'CONGREGAÇÃO CRISTÃ NO BRASIL')
        self.assertEqual(sheet['A7'].fill.fgColor.rgb[-6:], '1E4B7A')
        self.assertEqual(sheet['A8'].data_type, 's')
        self.assertEqual(sheet['E8'].value, '28/11/2026')
        self.assertEqual(sheet['F8'].value, 'Sem histórico no GEM')
        self.assertIn('Sem base avaliada', sheet['A5'].value)
        self.assertEqual(sheet.freeze_panes, 'A8')
        self.assertEqual(sheet.print_title_rows, '$1:$7')
        self.assertEqual(sheet.page_setup.fitToWidth, 1)
        self.assertEqual(sheet.auto_filter.ref, 'A7:J8')

    @patch.object(music_letters, 'can_open_module', return_value=False)
    def test_program_export_is_not_public(self, allowed):
        self.assertEqual(music_letters.export_program(RequestFactory().get('/')).status_code, 403)

    def test_pdf_repeats_institutional_header_and_keeps_requirements(self):
        from pypdf import PdfReader
        assessment = assess_program({'instrumento': 'VIOLINO'}, {
            'msa': [{'fase': '16.3', 'observacoes': 'Revisão'}],
            'metodo': [{'metodo': 'Britten', 'pagina': '56'}],
            'hinario': [{'hino': '1-480'}]}, target='oficializacao')
        assessment['checked_at'] = '06/11/2026 14:30'
        rows = [letter(id=str(i), nome='ALUNO ' + str(i), modalidade='oficializacao', program_assessment=assessment) for i in range(14)]
        reader = PdfReader(io.BytesIO(make_program_pdf(rows, 'Responsável teste', {})))
        self.assertGreater(len(reader.pages), 1)
        for page in reader.pages:
            text = page.extract_text()
            self.assertIn('CONGREGAÇÃO CRISTÃ NO BRASIL', text)
            self.assertIn('Regional Itapevi - São Paulo', text)
            self.assertIn('Impresso por:', text)
            self.assertIn('MÉTODO', text)
            self.assertIn('Exigido:', text)
            self.assertIn('Documentado:', text)
        all_text = '\n'.join(p.extract_text() for p in reader.pages)
        self.assertIn('100% sem comprovação completa', all_text)
        self.assertIn('28/11/2026', all_text)
        self.assertIn('Fase alcançada no histórico: 16.3', all_text)
        for i in range(14):
            self.assertIn('ALUNO ' + str(i), all_text)

    def test_empty_pdf_has_no_false_zero_percentage(self):
        from pypdf import PdfReader
        text = PdfReader(io.BytesIO(make_program_pdf([], 'Teste', {}))).pages[0].extract_text()
        self.assertIn('Sem base avaliada', text)
        self.assertIn('Nenhuma carta de músico', text)

    @patch.object(music_letters, 'can_open_module', return_value=True)
    @patch.object(music_letters, 'visible', return_value=[])
    @patch.object(music_letters, 'common_catalog', return_value=[])
    @patch.object(music_letters.music_exams, 'actor', return_value='Teste')
    def test_pdf_download_uses_pdf_content_and_extension(self, actor, catalog, visible, allowed):
        response = music_letters.export_program(RequestFactory().get('/'), file_format='pdf')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response['Content-Disposition'].endswith('.pdf"'))
        self.assertTrue(response.content.startswith(b'%PDF-'))
