import io
from unittest.mock import patch
from django.test import SimpleTestCase
from openpyxl import load_workbook
from pypdf import PdfReader
from ColorAdminApp.modules.music_letters_activity import annotate_activity, activity_report_note, current_activity
from ColorAdminApp.modules.music_letters_exports import make_pdf, make_excel
from ColorAdminApp.modules.music_letters_program_export import make_program_pdf, make_program_excel
from ColorAdminApp.modules.sam_program import assess_program

ID = '00000000-0000-4000-8000-000000000001'

def row():
    assessment = assess_program({'instrumento': 'TROMPETE'}, {'msa': [{'fase': '15.1'}]}, target='culto')
    assessment['checked_at'] = '06/11/2026 14:00'
    return {'id': 'letter', 'nome': 'ALUNO INATIVO', 'tipo': 'musico', 'modalidade': 'culto',
            'municipio': 'ITAPEVI', 'comum': 'BR-22-2294 - JARDIM SANTA CECÍLIA',
            'payload': {'pessoa_id': ID, 'instrumento': 'TROMPETE',
                'student_activity': {'status': 'INATIVO', 'pending': True, 'last_activity_at': '2026-03-01'},
                'activity_review': {'status': 'pending', 'channel': 'internal'}},
            'event_snapshot': {'data': '2026-11-28', 'evento': 'Avaliação de Músicos'},
            'program_assessment': assessment}

class LettersActivityTests(SimpleTestCase):
    @patch('ColorAdminApp.modules.music_letters_activity.fetch_current')
    def test_emission_snapshot_is_preserved_without_new_query(self, fetch):
        result = annotate_activity([row()])[0]
        self.assertEqual(result['student_activity']['status'], 'INATIVO')
        self.assertEqual(result['activity_review']['status'], 'pending')
        fetch.assert_not_called()
        self.assertIn('Situação registrada na emissão', activity_report_note(result))

    @patch('ColorAdminApp.modules.music_letters_activity.fetch_current')
    def test_legacy_consultation_is_identified_and_does_not_change_payload(self, fetch):
        original = row()
        original['payload'] = {'pessoa_id': ID}
        fetch.return_value = {ID: current_activity({'inactive_days': 250, 'operational_status': 'INATIVO'})}
        result = annotate_activity([original])[0]
        self.assertTrue(result['student_activity']['pending'])
        self.assertIn('Consulta atual', activity_report_note(result))
        self.assertNotIn('student_activity', original['payload'])
        self.assertEqual(len(result['activity_review']['recipients']), 3)

    def test_exclusion_is_a_review_flag_not_a_delete(self):
        self.assertEqual(current_activity({'inactive_days': 366, 'operational_status': 'INATIVO'})['status'], 'EXCLUIR')
        self.assertEqual(current_activity({'inactive_days': 365, 'operational_status': 'INATIVO'})['status'], 'INATIVO')

    @patch('ColorAdminApp.modules.music_letters_activity.fetch_current')
    def test_organists_are_not_flagged(self, fetch):
        original = row();original['tipo'] = 'organista'
        result = annotate_activity([original])[0]
        self.assertIsNone(result['student_activity'])
        self.assertIsNone(result['activity_review'])
        fetch.assert_not_called()

    def test_general_reports_include_inactivity_and_internal_notice(self):
        record = row()
        text = ' '.join(' '.join(p.extract_text().split()) for p in PdfReader(io.BytesIO(make_pdf([record], 'Teste', {}))).pages)
        for expected in ['INATIVO', 'PENDENTE DE ANÁLISE REGIONAL', '01/03/2026', 'Alerta interno']:
            self.assertIn(expected, text)
        sheet = load_workbook(io.BytesIO(make_excel([record], 'Teste', {}))).active
        self.assertIn('INATIVO', sheet['E7'].value)
        self.assertIn('secretário da regional', sheet['E7'].value)

    def test_program_reports_include_inactivity_and_preserve_institutional_header(self):
        record = row()
        text = '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(make_program_pdf([record], 'Teste', {}))).pages)
        self.assertIn('INATIVO', text)
        self.assertIn('PENDENTE DE ANÁLISE REGIONAL', text)
        sheet = load_workbook(io.BytesIO(make_program_excel([record], 'Teste', {}))).active
        self.assertEqual(sheet['A1'].value, 'CONGREGAÇÃO CRISTÃ NO BRASIL')
        self.assertIn('INATIVO', sheet['F8'].value)
        self.assertIn('Alerta interno', sheet['F8'].value)


class LettersNotificationTests(SimpleTestCase):
    @patch('ColorAdminApp.modules.music_letters.can_open_module', return_value=False)
    @patch('ColorAdminApp.modules.music_letters.visible')
    def test_notification_count_requires_music_access(self, visible, allowed):
        from django.test import RequestFactory
        from ColorAdminApp.modules.music_letters import notifications
        response = notifications(RequestFactory().get('/'))
        self.assertEqual(response.status_code, 403)
        visible.assert_not_called()

    @patch('ColorAdminApp.modules.music_letters.can_open_module', return_value=True)
    @patch('ColorAdminApp.modules.music_letters.visible')
    def test_bell_counts_only_pending_visible_letters_without_exposing_names(self, visible, allowed):
        import json
        from django.test import RequestFactory
        from ColorAdminApp.modules.music_letters import notifications
        visible.return_value = [{'nome': 'PRIVATE', 'activity_review': {'status': 'pending'}}, {'activity_review': None}]
        response = notifications(RequestFactory().get('/'))
        self.assertEqual(json.loads(response.content), {'pending_count': 1})
        self.assertNotIn(b'PRIVATE', response.content)
