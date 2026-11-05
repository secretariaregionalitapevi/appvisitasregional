from django.test import SimpleTestCase, RequestFactory
from django.template.loader import render_to_string
from unittest.mock import patch
import io
from openpyxl import load_workbook
from ColorAdminApp.modules import music_exams
from ColorAdminApp.modules.music_exams import query_filters, matches_filters


class MusicManagementTests(SimpleTestCase):
    def test_excel_summary_includes_confirmed_individual_records_in_common_slice(self):
        request = RequestFactory().get('/', {'comum': 'BR-21-1039'})
        request.session = {'user_profile': {'full_name': 'Teste'}}
        row = {'id': 'exam-1', 'comum': 'BR-21-1039', 'municipio': 'ITAPEVI',
               'data_exame': '2026-11-28', 'resultado': 'APROVADO', 'origem': 'PAINEL',
               'tipo_exame': 'OFICIALIZACAO', 'nome_aluno': 'Candidato de teste', 'instrumento': 'VIOLINO'}
        with patch.object(music_exams, 'can_open_module', return_value=True), \
             patch.object(music_exams, 'fetch_rows', return_value=[row]), \
             patch.object(music_exams, 'fetch_legacy', return_value=[]):
            response = music_exams.export_excel(request)
        sheet = load_workbook(io.BytesIO(response.content)).worksheets[0]
        self.assertEqual(sheet['C7'].value, 1)
        self.assertEqual(sheet['I11'].value, 1)

    def test_exam_year_event_and_common_filters_apply_to_the_same_slice(self):
        request = RequestFactory().get('/', {'ano': '2026', 'evento': 'date:2026-11-28', 'comum': 'BR-21-1039'})
        filters = query_filters(request)
        row = {'data_exame': '2026-11-28', 'comum': 'BR-21-1039'}
        self.assertTrue(matches_filters(row, filters))
        self.assertFalse(matches_filters(dict(row, data_exame='2025-11-28'), filters))
        self.assertFalse(matches_filters(dict(row, data_exame='2026-11-07'), filters))
        self.assertFalse(matches_filters(dict(row, comum='BR-22-2999'), filters))
        self.assertFalse(matches_filters(row, filters, legacy=True))

    def test_both_pages_use_header_scope_and_export_controls_before_metrics(self):
        scope = {'nivel': 'global', 'municipio': 'ITAPEVI', 'comum': 'BR-22-0673 - VILA DOUTOR CARDOSO'}
        for template, prefix, metric in [('pages/music_letters.html', 'letters-', 'letters-metrics'),
                                         ('pages/music_exams.html', 'op-', 'metrics')]:
            html = render_to_string(template, {'scope': scope, 'report_user': 'Teste', 'can_import': True})
            self.assertIn('Escopo desta visão', html)
            self.assertIn(scope['comum'], html)
            self.assertIn('music-management.css', html)
            self.assertIn('music-management.js', html)
            self.assertIn('id="' + prefix + 'year"', html)
            self.assertIn('id="' + prefix + 'common"', html)
            self.assertIn('id="' + prefix + 'event"', html)
            self.assertLess(html.index('management-hero'), html.index('management-controls'))
            self.assertLess(html.index('management-controls'), html.index('id="' + metric + '"'))
